import logging
import re
from typing import Dict, Any, List, Tuple, Optional
from app.ERP_R12_Test_DB.vector_store_chroma import search_similar_schema

logger = logging.getLogger(__name__)

class QueryClassifier:
    """
    Enhanced dynamic query classifier for ERP R12 that uses vector store
    to understand query context and intent.
    """
    
    def __init__(self):
        # ERP R12 business domains
        self.domains = {
            "HR": ["employee", "staff", "worker", "job", "position", "department", "location", "salary", "compensation"],
            "FIN": ["ledger", "account", "gl", "general ledger", "invoice", "payment", "supplier", "customer", "ar", "ap"],
            "INV": ["inventory", "item", "product", "stock", "onhand", "subinventory", "warehouse", "mtl"],
            "PO": ["purchase order", "po", "supplier", "vendor", "requisition"],
            "OM": ["sales order", "order", "customer", "so", "shipment", "delivery"],
            "FA": ["asset", "fa", "depreciation", "fixed asset"],
            "CST": ["cost", "cst", "item cost", "material cost"],
            "BOM": ["bom", "bill of material", "recipe", "formula"],
            "WIP": ["wip", "work in process", "job", "work order"],
            "PROJ": ["project", "task", "expenditure", "budget"]
        }
        
        # Query complexity levels
        self.complexity_indicators = {
            "SIMPLE": ["list", "show", "get", "find", "count"],
            "MODERATE": ["sum", "total", "average", "avg", "group by", "order by"],
            "COMPLEX": ["join", "correlation", "trend", "analysis", "compare", "relationship"]
        }
        
        # Query intent categories
        self.intent_categories = {
            "REPORTING": ["report", "summary", "dashboard", "view"],
            "ANALYTICS": ["analysis", "trend", "pattern", "insight", "metric"],
            "OPERATIONAL": ["create", "update", "delete", "process", "execute"],
            "INFORMATIONAL": ["what", "how", "when", "where", "which", "who"]
        }
    
    def classify_query(self, query: str, schema_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Dynamically classify a query based on content and schema context.
        
        Args:
            query: The user's natural language query
            schema_context: Optional schema context from vector store
            
        Returns:
            Classification results with domain, complexity, and intent
        """
        query_lower = query.lower()
        
        # Get dynamic schema context if not provided
        if schema_context is None:
            schema_context = self._get_dynamic_schema_context(query)
        
        # Determine business domain
        domain = self._classify_domain(query_lower, schema_context)
        
        # Determine complexity level
        complexity = self._classify_complexity(query_lower)
        
        # Determine intent category
        intent = self._classify_intent(query_lower)
        
        # Determine confidence level
        confidence = self._calculate_confidence(query_lower, domain, complexity, intent)
        
        # Extract key entities
        entities = self._extract_entities(query_lower, schema_context)
        
        return {
            "domain": domain,
            "complexity": complexity,
            "intent": intent,
            "confidence": confidence,
            "entities": entities,
            "schema_context": schema_context
        }
    
    def _get_dynamic_schema_context(self, query: str) -> Dict[str, Any]:
        """
        Dynamically retrieve schema context from vector store based on query.
        
        Args:
            query: The user's query
            
        Returns:
            Schema context information
        """
        try:
            # Search for schema information related to the query
            schema_docs = search_similar_schema(query, "source_db_2", top_k=20)
            
            # Extract relevant information
            tables = set()
            columns = set()
            
            for doc in schema_docs:
                if 'metadata' in doc:
                    meta = doc['metadata']
                    if meta.get('kind') == 'table':
                        table_name = meta.get('table')
                        if table_name:
                            tables.add(table_name)
                    elif meta.get('kind') == 'column':
                        column_name = meta.get('column')
                        table_name = meta.get('source_table')
                        if column_name:
                            columns.add(f"{table_name}.{column_name}" if table_name else column_name)
            
            return {
                "tables": list(tables),
                "columns": list(columns),
                "document_count": len(schema_docs)
            }
        except Exception as e:
            logger.warning(f"Failed to get dynamic schema context: {e}")
            return {"tables": [], "columns": [], "document_count": 0}
    
    def _classify_domain(self, query: str, schema_context: Dict[str, Any]) -> str:
        """
        Classify the business domain of the query.
        
        Args:
            query: Lowercase query string
            schema_context: Schema context information
            
        Returns:
            Business domain classification
        """
        # Check schema context first
        schema_tables = schema_context.get("tables", [])
        for table in schema_tables:
            table_upper = table.upper()
            if any(prefix in table_upper for prefix in ["HR_", "PER_", "PAY_"]):
                return "HR"
            elif any(prefix in table_upper for prefix in ["GL_", "AP_", "AR_", "FA_", "XLA_"]):
                return "FIN"
            elif any(prefix in table_upper for prefix in ["MTL_", "INV_"]):
                return "INV"
            elif any(prefix in table_upper for prefix in ["PO_"]):
                return "PO"
            elif any(prefix in table_upper for prefix in ["OE_", "WSH_"]):
                return "OM"
            elif any(prefix in table_upper for prefix in ["CST_"]):
                return "CST"
            elif any(prefix in table_upper for prefix in ["BOM_", "FM_"]):
                return "BOM"
            elif any(prefix in table_upper for prefix in ["WIP_"]):
                return "WIP"
            elif any(prefix in table_upper for prefix in ["PA_"]):
                return "PROJ"
        
        # Check query content
        for domain, keywords in self.domains.items():
            matches = sum(1 for keyword in keywords if keyword in query)
            if matches >= 2:  # At least 2 keywords match
                return domain
        
        # Default to most common domain
        return "INV"
    
    def _classify_complexity(self, query: str) -> str:
        """
        Classify the complexity level of the query.
        
        Args:
            query: Lowercase query string
            
        Returns:
            Complexity level classification
        """
        # Count complexity indicators
        simple_matches = sum(1 for keyword in self.complexity_indicators["SIMPLE"] if keyword in query)
        moderate_matches = sum(1 for keyword in self.complexity_indicators["MODERATE"] if keyword in query)
        complex_matches = sum(1 for keyword in self.complexity_indicators["COMPLEX"] if keyword in query)
        
        # Determine complexity based on matches
        if complex_matches >= 2:
            return "COMPLEX"
        elif moderate_matches >= 2:
            return "MODERATE"
        elif simple_matches >= 1:
            return "SIMPLE"
        else:
            # Default based on query length
            if len(query.split()) > 20:
                return "COMPLEX"
            elif len(query.split()) > 10:
                return "MODERATE"
            else:
                return "SIMPLE"
    
    def _classify_intent(self, query: str) -> str:
        """
        Classify the intent category of the query.
        
        Args:
            query: Lowercase query string
            
        Returns:
            Intent category classification
        """
        # Count intent indicators
        reporting_matches = sum(1 for keyword in self.intent_categories["REPORTING"] if keyword in query)
        analytics_matches = sum(1 for keyword in self.intent_categories["ANALYTICS"] if keyword in query)
        operational_matches = sum(1 for keyword in self.intent_categories["OPERATIONAL"] if keyword in query)
        informational_matches = sum(1 for keyword in self.intent_categories["INFORMATIONAL"] if keyword in query)
        
        # Determine intent based on matches
        intent_scores = {
            "REPORTING": reporting_matches,
            "ANALYTICS": analytics_matches,
            "OPERATIONAL": operational_matches,
            "INFORMATIONAL": informational_matches
        }
        
        # Return the intent with highest score
        max_score = -1
        max_intent = "REPORTING"
        for intent, score in intent_scores.items():
            if score > max_score:
                max_score = score
                max_intent = intent
        
        if max_score > 0:
            return max_intent
        else:
            # Default to informational for questions
            if any(q_word in query for q_word in ["what", "how", "when", "where", "which", "who"]):
                return "INFORMATIONAL"
            else:
                return "REPORTING"
    
    def _calculate_confidence(self, query: str, domain: str, complexity: str, intent: str) -> float:
        """
        Calculate confidence level for the classification.
        
        Args:
            query: Lowercase query string
            domain: Classified domain
            complexity: Classified complexity
            intent: Classified intent
            
        Returns:
            Confidence level (0.0 to 1.0)
        """
        # Base confidence
        confidence = 0.5
        
        # Adjust based on query characteristics
        query_length = len(query.split())
        
        # Longer queries generally have more context
        if query_length > 15:
            confidence += 0.1
        elif query_length < 5:
            confidence -= 0.1
        
        # Check for clear domain indicators
        domain_keywords = self.domains.get(domain, [])
        domain_matches = sum(1 for keyword in domain_keywords if keyword in query)
        if domain_matches >= 3:
            confidence += 0.2
        elif domain_matches >= 1:
            confidence += 0.1
        
        # Check for clear intent indicators
        intent_keywords = self.intent_categories.get(intent, [])
        intent_matches = sum(1 for keyword in intent_keywords if keyword in query)
        if intent_matches >= 2:
            confidence += 0.15
        
        # Ensure confidence is within bounds
        return max(0.0, min(1.0, confidence))
    
    def _extract_entities(self, query: str, schema_context: Dict[str, Any]) -> List[str]:
        """
        Extract key entities from the query.
        
        Args:
            query: Lowercase query string
            schema_context: Schema context information
            
        Returns:
            List of extracted entities
        """
        entities = []
        
        # Extract potential entity names (quoted strings)
        quoted_entities = re.findall(r'"([^"]*)"', query)
        entities.extend(quoted_entities)
        
        # Extract potential IDs (numeric patterns)
        id_patterns = re.findall(r'\b\d+[a-zA-Z]*\b', query)
        entities.extend(id_patterns)
        
        # Extract column/table names from schema context
        entities.extend(schema_context.get("columns", [])[:5])  # Limit to top 5
        
        # Remove duplicates and return
        return list(set(entities))