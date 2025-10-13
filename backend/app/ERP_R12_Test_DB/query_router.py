# ERP R12 Query Router
import logging
import re
from typing import Dict, Any, List
# Import from ERP-specific query_classifier instead of SOS
from app.ERP_R12_Test_DB.query_classifier import QueryClassifier
# Import vector store for dynamic schema retrieval
from app.ERP_R12_Test_DB.vector_store_chroma import search_similar_schema

logger = logging.getLogger(__name__)
# Set logger level to INFO to reduce verbosity
logger.setLevel(logging.INFO)

# Initialize query classifier
query_classifier = QueryClassifier()

def get_erp_schema_info() -> Dict[str, Any]:
    """
    Dynamically retrieve ERP schema information from the vector store.
    
    Returns:
        Dictionary containing table and column information
    """
    try:
        # Search for schema information about our key tables
        hr_ou_docs = search_similar_schema("HR_OPERATING_UNITS", "source_db_2", top_k=20)
        org_def_docs = search_similar_schema("ORG_ORGANIZATION_DEFINITIONS", "source_db_2", top_k=20)
        
        # Extract table and column information from schema documents
        erp_tables = {}
        
        # Process HR_OPERATING_UNITS documents
        hr_columns = []
        for doc in hr_ou_docs:
            if 'document' in doc and 'metadata' in doc:
                # Check if this document is about columns
                if doc['metadata'].get('kind') == 'column' and doc['metadata'].get('source_table') == 'HR_OPERATING_UNITS':
                    column_name = doc['metadata'].get('column')
                    if column_name and column_name not in hr_columns:
                        hr_columns.append(column_name)
        
        erp_tables["HR_OPERATING_UNITS"] = {
            "columns": hr_columns,
            "description": "Contains operating unit definitions with business group associations. ONLY use these actual columns: " + ", ".join(hr_columns[:20])
        }
        
        # Process ORG_ORGANIZATION_DEFINITIONS documents
        org_columns = []
        for doc in org_def_docs:
            if 'document' in doc and 'metadata' in doc:
                # Check if this document is about columns
                if doc['metadata'].get('kind') == 'column' and doc['metadata'].get('source_table') == 'ORG_ORGANIZATION_DEFINITIONS':
                    column_name = doc['metadata'].get('column')
                    if column_name and column_name not in org_columns:
                        org_columns.append(column_name)
        
        erp_tables["ORG_ORGANIZATION_DEFINITIONS"] = {
            "columns": org_columns,
            "description": "Defines organizations with their codes and relationships to operating units. ONLY use these actual columns: " + ", ".join(org_columns[:20])
        }
        
        return erp_tables
    except Exception as e:
        logger.warning(f"Failed to retrieve dynamic schema info: {e}. Using fallback approach.")
        # Fallback to a more general approach
        return get_erp_schema_fallback()

def get_erp_schema_fallback() -> Dict[str, Any]:
    """
    Fallback method to get ERP schema information.
    
    Returns:
        Dictionary containing table and column information
    """
    # Search for general schema information
    schema_docs = search_similar_schema("ERP R12 schema", "source_db_2", top_k=10)
    
    # Extract tables and columns from documents
    tables = {}
    for doc in schema_docs:
        if 'document' in doc and 'metadata' in doc:
            table_name = doc['metadata'].get('source_table')
            if table_name:
                if table_name not in tables:
                    tables[table_name] = {
                        "columns": [],
                        "description": doc['document'][:200] if 'document' in doc else ""
                    }
                # If this is a column document, add the column
                if doc['metadata'].get('kind') == 'column':
                    column_name = doc['metadata'].get('column')
                    if column_name and column_name not in tables[table_name]["columns"]:
                        tables[table_name]["columns"].append(column_name)
    
    return tables

def get_erp_relationships() -> Dict[str, str]:
    """
    Dynamically retrieve ERP table relationships from the vector store.
    
    Returns:
        Dictionary containing relationship information
    """
    try:
        # Search for relationship information
        relationship_docs = search_similar_schema("relationship between HR_OPERATING_UNITS and ORG_ORGANIZATION_DEFINITIONS", "source_db_2", top_k=3)
        
        relationships = {}
        for doc in relationship_docs:
            if 'document' in doc:
                # Look for relationship information in the document text
                if 'organization_id' in doc['document'].lower() and 'operating_unit' in doc['document'].lower():
                    relationships["HR_OPERATING_UNITS.ORGANIZATION_ID"] = "ORG_ORGANIZATION_DEFINITIONS.OPERATING_UNIT"
        
        return relationships
    except Exception as e:
        logger.warning(f"Failed to retrieve dynamic relationships: {e}. Using empty relationships.")
        return {}

def get_erp_keywords_and_patterns(erp_tables: Dict[str, Any], erp_relationships: Dict[str, str]) -> tuple:
    """
    Dynamically generate ERP keywords and patterns based on schema information.
    
    Args:
        erp_tables: Dictionary containing table and column information
        erp_relationships: Dictionary containing relationship information
        
    Returns:
        Tuple of (keywords_set, patterns_list)
    """
    keywords = set()
    patterns = []
    
    # Add table names as keywords and patterns
    for table_name in erp_tables.keys():
        table_name_lower = table_name.lower()
        keywords.add(table_name_lower)
        
        # Add pattern for table name with possible separators
        patterns.append(rf"\b{table_name_lower.replace('_', r'[_\s]')}\b")
        
        # Add variations
        if 'operating' in table_name_lower:
            patterns.append(r"\boperating[_\s]units?\b")
        if 'organization' in table_name_lower:
            patterns.append(r"\borgani[sz]ations?\b")
    
    # Add column names as keywords and patterns
    all_columns = []
    for table_info in erp_tables.values():
        all_columns.extend(table_info.get("columns", []))
    
    for column in all_columns:
        column_lower = column.lower()
        keywords.add(column_lower)
        
        # Add pattern for column name with possible separators
        patterns.append(rf"\b{column_lower.replace('_', r'[_\s]')}\b")
    
    # Add business terms dynamically based on schema context
    business_terms = [
        "business_group", "operating_unit", "organization", "legal_entity", 
        "set_of_books", "erp", "r12", "chart_of_accounts", "inventory_enabled",
        "active", "currently active", "enabled", "disabled", "inventory enabled",
        "business group", "operating unit", "organization name", "organization code",
        "short code", "legal entity", "set of books", "chart of accounts",
        "usable", "currently usable", "usable flag", "join", "link", "connect", "both"
    ]
    keywords.update(business_terms)
    
    # Add relationship patterns dynamically
    for left, right in erp_relationships.items():
        patterns.append(rf"\b{left.lower().replace('.', r'\.').replace('_', r'[_\s]')}\b")
        patterns.append(rf"\b{right.lower().replace('.', r'\.').replace('_', r'[_\s]')}\b")
    
    # Add general relationship patterns dynamically
    patterns.extend([
        r"\b(join|link|connect|relate)\b.*\b(operating\s+unit|organization)\b",
        r"\b(operating\s+unit).*\b(organization)\b",
        r"\bcurrently\s+active\b",
        r"\benabled\s+after\b",
        r"\bno\s+inventory\b",
        r"\bwithout\s+legal\s+entity\b",
        r"\bset\s+of\s+books\b",
        r"\bchart\s+of\s+accounts\b",
        r"\busable\s+flag\b",
        r"\binventory\s+enabled\s+flag\b"
    ])
    
    return keywords, patterns

def extract_erp_entities(user_query: str) -> Dict[str, List[str]]:
    """
    Extract ERP-specific entities from the user query using dynamic schema information.
    
    Args:
        user_query: The user's natural language query
        
    Returns:
        Dictionary of extracted entities by type
    """
    entities = {}
    
    # Get dynamic schema information
    erp_tables = get_erp_schema_info()
    erp_relationships = get_erp_relationships()
    
    # Convert to lowercase for matching
    query_lower = user_query.lower()
    
    # Extract table references
    table_matches = []
    for table in erp_tables.keys():
        if table.lower() in query_lower:
            table_matches.append(table)
    if table_matches:
        entities["tables"] = table_matches
    
    # Extract column references
    column_matches = []
    all_columns = []
    for table_info in erp_tables.values():
        all_columns.extend(table_info.get("columns", []))
    
    for column in all_columns:
        if column.lower() in query_lower:
            column_matches.append(column)
    if column_matches:
        entities["columns"] = column_matches
    
    # Extract relationship references
    if "join" in query_lower or "link" in query_lower or "connect" in query_lower:
        entities["relationships"] = ["table_join"]
    
    return entities

def is_erp_query(user_query: str) -> bool:
    """
    Determine if a query should be routed to ERP R12 based on dynamic schema information.
    
    Args:
        user_query: The user's natural language query
        
    Returns:
        True if the query should be routed to ERP R12, False otherwise
    """
    query_lower = user_query.lower()
    
    # Get dynamic schema information
    erp_tables = get_erp_schema_info()
    erp_relationships = get_erp_relationships()
    erp_keywords, erp_patterns = get_erp_keywords_and_patterns(erp_tables, erp_relationships)
    
    # Check for ERP-specific keywords
    for keyword in erp_keywords:
        if keyword in query_lower:
            return True
    
    # Check for ERP entity patterns
    for pattern in erp_patterns:
        if re.search(pattern, query_lower):
            return True
    
    # Check for relationship queries
    # Looking for queries that mention joining/linking operating units and organizations
    if any(term in query_lower for term in ["join", "link", "connect", "relate"]) and \
       any(term in query_lower for term in ["operating unit", "organization"]):
        return True
    
    # Check for business context from sample questions
    business_context_terms = [
        "active", "currently active", "enabled", "disabled", "inventory enabled",
        "business group", "operating unit", "organization name", "organization code",
        "short code", "legal entity", "set of books", "chart of accounts",
        "usable", "currently usable", "usable flag", "inventory enabled flag"
    ]
    context_matches = sum(1 for term in business_context_terms if term in query_lower)
    if context_matches >= 2:  # If at least 2 business context terms are found
        return True
    
    return False

def route_query(user_query: str, selected_db: str = "", mode: str = "General") -> Dict[str, Any]:
    """
    Route queries to the appropriate module (SOS or ERP R12) using dynamic schema information.
    
    Args:
        user_query: The user's natural language query
        selected_db: Selected database ID
        mode: Processing mode (General, SOS, ERP)
        
    Returns:
        Dictionary containing routing information with confidence and reasoning
    """
    # If mode is explicitly set to ERP, route to ERP
    if mode.upper() == "ERP":
        return {
            "module": "ERP_R12",
            "db_id": "source_db_2",
            "confidence": 1.0,
            "reason": "Explicit ERP mode selected"
        }
    
    # If mode is explicitly set to SOS, route to SOS
    if mode.upper() == "SOS":
        return {
            "module": "SOS",
            "db_id": "source_db_1",
            "confidence": 1.0,
            "reason": "Explicit SOS mode selected"
        }
    
    # If selected_db is explicitly set, use that
    if selected_db:
        if selected_db == "source_db_2":
            return {
                "module": "ERP_R12",
                "db_id": "source_db_2",
                "confidence": 0.95,
                "reason": "source_db_2 (ERP R12) explicitly selected"
            }
        elif selected_db == "source_db_1":
            return {
                "module": "SOS",
                "db_id": "source_db_1",
                "confidence": 0.95,
                "reason": "source_db_1 (SOS) explicitly selected"
            }
    
    # Use query classification for intelligent routing
    try:
        classification = query_classifier.classify_query(user_query)
        intent = classification.intent
        confidence = classification.confidence
        entities = classification.entities
        
        logger.info(f"Query classified as {intent.value} with confidence {confidence:.2f}")
        
        # Extract ERP entities for additional context
        erp_entities = extract_erp_entities(user_query)
        
        # High confidence routing for ERP-specific intents
        erp_intents = [
            "organization_query", "business_group_query", "legal_entity_query", 
            "financial_query", "inventory_query", "database_query"
        ]
        
        if intent.value in erp_intents and confidence > 0.7:
            reasoning = f"High confidence ERP classification ({intent.value}) with confidence {confidence:.2f}"
            if erp_entities:
                reasoning += f". Detected ERP entities: {list(erp_entities.keys())}"
            
            return {
                "module": "ERP_R12",
                "db_id": "source_db_2",
                "confidence": min(confidence + 0.1, 1.0),  # Boost confidence slightly
                "reason": reasoning
            }
            
        # Medium confidence routing based on entity detection
        if erp_entities and confidence > 0.5:
            entity_types = list(erp_entities.keys())
            return {
                "module": "ERP_R12",
                "db_id": "source_db_2",
                "confidence": min(confidence + 0.05, 1.0),
                "reason": f"ERP entities detected ({', '.join(entity_types)}) with classification confidence {confidence:.2f}"
            }
            
    except Exception as e:
        logger.warning(f"Query classification failed: {e}")
    
    # Fallback to keyword-based detection
    if is_erp_query(user_query):
        erp_entities = extract_erp_entities(user_query)
        reasoning = "ERP keywords, patterns, or entities detected in query"
        if erp_entities:
            reasoning += f": {list(erp_entities.keys())}"
            
        return {
            "module": "ERP_R12",
            "db_id": "source_db_2",
            "confidence": 0.85,
            "reason": reasoning
        }
    
    # Default to SOS for general queries
    return {
        "module": "SOS",
        "db_id": "source_db_1",
        "confidence": 0.6,
        "reason": "Default routing to SOS for general queries"
    }

# Test code removed for production use,
