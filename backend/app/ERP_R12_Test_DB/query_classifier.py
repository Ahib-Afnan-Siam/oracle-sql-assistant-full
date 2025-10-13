# ERP R12 Query Classifier
import re
import logging
from typing import Dict, List, Tuple, Optional
from enum import Enum
from dataclasses import dataclass
from datetime import datetime as _dt

# Import vector store to get dynamic schema information
from app.ERP_R12_Test_DB.vector_store_chroma import search_similar_schema

logger = logging.getLogger(__name__)
# Set logger level to INFO to reduce verbosity
logger.setLevel(logging.INFO)

VISUALIZATION_PATTERNS = {
    'keywords': ['graph', 'chart', 'plot', 'visualize', 'visualization', 'show me', 'display'],
    'chart_types': ['bar chart', 'line chart', 'pie chart', 'doughnut chart']
}

def has_visualization_intent(query: str) -> bool:
    """
    Detect if the query is requesting a visualization/chart.
    
    Args:
        query: The user's query string
        
    Returns:
        bool: True if visualization is requested, False otherwise
    """
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in VISUALIZATION_PATTERNS['keywords'])

class QueryIntent(Enum):
    """Query intent classification for ERP R12 routing decisions."""
    ORGANIZATION_QUERY = "organization_query"
    BUSINESS_GROUP_QUERY = "business_group_query"
    LEGAL_ENTITY_QUERY = "legal_entity_query"
    FINANCIAL_QUERY = "financial_query"
    INVENTORY_QUERY = "inventory_query"
    SIMPLE_LOOKUP = "simple_lookup"
    COMPLEX_ANALYTICS = "complex_analytics"
    GENERAL_QUERY = "general_query"
    DATABASE_QUERY = "database_query"

class ModelSelectionStrategy(Enum):
    """Model selection strategies based on query classification."""
    LOCAL_ONLY = "local_only"
    API_PREFERRED = "api_preferred"
    HYBRID_PARALLEL = "hybrid_parallel"
    BEST_AVAILABLE = "best_available"

@dataclass
class QueryClassification:
    """Result of query classification analysis."""
    intent: QueryIntent
    confidence: float
    strategy: ModelSelectionStrategy
    reasoning: str
    entities: Dict[str, List[str]]
    complexity_score: float
    
class QueryClassifier:
    """Intelligent query classification for ERP R12 hybrid AI routing."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._init_patterns()
    
    def _init_patterns(self):
        """Initialize regex patterns for different ERP query types based on actual schema."""
        # Get schema information dynamically from vector store
        self._load_schema_patterns()
        
    def _load_schema_patterns(self):
        """Load patterns dynamically from the actual ERP schema."""
        try:
            # Search for schema information about key ERP concepts with higher top_k
            org_docs = search_similar_schema("organization", "source_db_2", top_k=5)
            bg_docs = search_similar_schema("business group", "source_db_2", top_k=5)
            le_docs = search_similar_schema("legal entity", "source_db_2", top_k=5)
            fin_docs = search_similar_schema("financial", "source_db_2", top_k=5)
            inv_docs = search_similar_schema("inventory", "source_db_2", top_k=5)
            active_docs = search_similar_schema("active usable", "source_db_2", top_k=5)
            
            # Extract relevant terms from documents
            org_terms = self._extract_terms_from_docs(org_docs)
            bg_terms = self._extract_terms_from_docs(bg_docs)
            le_terms = self._extract_terms_from_docs(le_docs)
            fin_terms = self._extract_terms_from_docs(fin_docs)
            inv_terms = self._extract_terms_from_docs(inv_docs)
            active_terms = self._extract_terms_from_docs(active_docs)
            
            # Organization patterns based on actual schema
            self.organization_patterns = [
                r'\b(organization|org)\b',
                r'\b(org_organization_definitions)\b',
                r'\b(inventory organization|inventory org)\b',
                r'\b(organization name|organization code)\b'
            ]
            # Add patterns for organization-related terms from actual schema
            for term in org_terms:
                # Only add terms that are likely to be relevant
                if len(term) > 2 and not term.isdigit():  # Filter out single characters and pure numbers
                    self.organization_patterns.append(rf'\b{re.escape(term.lower())}\b')
            
            # Business Group patterns based on actual schema
            self.business_group_patterns = [
                r'\b(business group|bg)\b',
                r'\b(hr_operating_units)\b',
                r'\b(business unit|bu)\b',
                r'\b(operating unit)\b'
            ]
            # Add patterns for business group-related terms from actual schema
            for term in bg_terms:
                # Only add terms that are likely to be relevant
                if len(term) > 2 and not term.isdigit():  # Filter out single characters and pure numbers
                    self.business_group_patterns.append(rf'\b{re.escape(term.lower())}\b')
            
            # Legal Entity patterns
            self.legal_entity_patterns = [
                r'\b(legal entity|le)\b'
            ]
            # Add legal entity related terms from actual schema
            for term in le_terms:
                # Only add terms that are likely to be relevant
                if len(term) > 2 and not term.isdigit():  # Filter out single characters and pure numbers
                    self.legal_entity_patterns.append(rf'\b{re.escape(term.lower())}\b')
            
            # Financial patterns
            self.financial_patterns = [
                r'\b(financial|accounting|ledger)\b',
                r'\b(set of books|chart of accounts)\b'
            ]
            # Add financial related terms from actual schema
            for term in fin_terms:
                # Only add terms that are likely to be relevant
                if len(term) > 2 and not term.isdigit():  # Filter out single characters and pure numbers
                    self.financial_patterns.append(rf'\b{re.escape(term.lower())}\b')
            
            # Inventory patterns
            self.inventory_patterns = [
                r'\b(inventory|inv)\b',
                r'\b(inventory enabled)\b'
            ]
            # Add inventory related terms from actual schema
            for term in inv_terms:
                # Only add terms that are likely to be relevant
                if len(term) > 2 and not term.isdigit():  # Filter out single characters and pure numbers
                    self.inventory_patterns.append(rf'\b{re.escape(term.lower())}\b')
            
            # Active/Usable patterns
            self.active_patterns = [
                r'\b(active|usable|enabled)\b',
                r'\b(currently active|currently usable)\b'
            ]
            # Add active/usable related terms from actual schema
            for term in active_terms:
                # Only add terms that are likely to be relevant
                if len(term) > 2 and not term.isdigit():  # Filter out single characters and pure numbers
                    self.active_patterns.append(rf'\b{re.escape(term.lower())}\b')
            
            # Simple lookup patterns
            self.simple_patterns = [
                r'^\s*(list|show)\s+(organization|org|business group|bg|legal entity|le)s?\s*$',
                r'^\s*(organization|org|business group|bg|legal entity|le)\s+(list|data)\s*$',
                r'^\s*\w+\s+(id|code)\s+\d+\s*$',
                r'^\s*(what\s+is|who\s+is|show\s+me)\s+\w+\s*$'
            ]
            
            # Complex analytics patterns
            self.complex_patterns = [
                r'\b(trend|analysis|compare|correlation|prediction)\b',
                r'\b(average|median|variance|standard\s+deviation)\b',
                r'\b(group\s+by|order\s+by|having|window\s+function)\b',
                r'\b(last\s+\d+\s+(months|years|days|weeks)|year\s+over\s+year)\b',
                r'\b(monthly|weekly|daily|quarterly)\b',
                r'\b(over\s+time|time\s+series)\b',
                r'\b(highest|lowest|top|bottom)\b',
                r'\b(growth|decline|increase|decrease)\b',
                r'\b(ranking|rank\s+by)\b'
            ]
            
            # Database system query patterns
            self.database_patterns = [
                r'\b(invalid\s+objects|dba\s+users|sql\s+session|database\s+schema|tablespace|table\s+list)\b',
                r'\b(total\s+invalid\s+objects|total\s+dba\s+users|top\s+sql\s+session)\b',
                r'\b(show\s+me.*schema|list.*schema\s+users|tablespace\s+summary)\b',
                r'\b(free\s+and\s+used|percentage\s+of\s+free|percentage\s+of\s+used)\b'
            ]

            # Entity extraction patterns for ERP
            self.entity_patterns = {
                'organizations': r'\b(?:[A-Z0-9]{2,10}[_\-][A-Z0-9]{2,10}|[A-Z]{2,}_ORG)\b',
                'business_groups': r'\b(?:[A-Z0-9]{2,10}[_\-]BG|[A-Z]{2,}_BUSINESS_GROUP)\b',
                'legal_entities': r'\b(?:[A-Z0-9]{2,10}[_\-]LE|[A-Z]{2,}_LEGAL_ENTITY)\b',
                'dates': r'\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}-[A-Z]{3}-\d{2,4}|[A-Z]{3}-\d{2,4})\b',
                'ordering_directions': r'\b(asc|ascending|desc|descending)\b',
                'aggregations': r'\b(avg|average|sum|total|count|max|min)\b',
                'trend_indicators': r'\b(trend|analysis|compare|correlation|monthly|weekly|daily|over\s+time)\b',
                'database_entities': r'\b(invalid\s+objects|dba\s+users|sql\s+sessions?|schema|tablespace|tables?)\b',
                'status_indicators': r'\b(active|usable|enabled|disabled|inventory\s+enabled)\b'
            }
            
        except Exception as e:
            logger.warning(f"Failed to load dynamic schema patterns: {e}. Using default patterns.")
            # Fallback to default patterns if dynamic loading fails
            self._init_default_patterns()
    
    def _init_default_patterns(self):
        """Initialize with default patterns if dynamic loading fails."""
        # Organization patterns
        self.organization_patterns = [
            r'\b(organization|org|organization_name|organization_code)\b',
            r'\b(org_organization_definitions)\b',
            r'\b(inventory organization|inventory org)\b',
            r'\b(organization_id|org_id)\b'
        ]
        
        # Business Group patterns
        self.business_group_patterns = [
            r'\b(business group|bg|business_group_id)\b',
            r'\b(hr_operating_units)\b',
            r'\b(business unit|bu)\b'
        ]
        
        # Legal Entity patterns
        self.legal_entity_patterns = [
            r'\b(legal entity|le|legal_entity)\b',
            r'\b(default_legal_context_id)\b'
        ]
        
        # Financial patterns
        self.financial_patterns = [
            r'\b(set of books|sob|set_of_books_id)\b',
            r'\b(chart of accounts|chart_of_accounts_id)\b',
            r'\b(financial|accounting|ledger)\b'
        ]
        
        # Inventory patterns
        self.inventory_patterns = [
            r'\b(inventory|inv|inventory_enabled_flag)\b',
            r'\b(stock|warehouse|locator)\b'
        ]
        
        # Simple lookup patterns
        self.simple_patterns = [
            r'^\s*(list|show)\s+(organization|org|business group|bg|legal entity|le)s?\s*$',
            r'^\s*(organization|org|business group|bg|legal entity|le)\s+(list|data)\s*$',
            r'^\s*\w+\s+(id|code)\s+\d+\s*$',
            r'^\s*(what\s+is|who\s+is|show\s+me)\s+\w+\s*$'
        ]
        
        # Complex analytics patterns
        self.complex_patterns = [
            r'\b(trend|analysis|compare|correlation|prediction)\b',
            r'\b(average|median|variance|standard\s+deviation)\b',
            r'\b(group\s+by|order\s+by|having|window\s+function)\b',
            r'\b(last\s+\d+\s+(months|years|days|weeks)|year\s+over\s+year)\b',
            r'\b(monthly|weekly|daily|quarterly)\b',
            r'\b(over\s+time|time\s+series)\b',
            r'\b(highest|lowest|top|bottom)\b',
            r'\b(growth|decline|increase|decrease)\b',
            r'\b(ranking|rank\s+by)\b'
        ]
        
        # Database system query patterns
        self.database_patterns = [
            r'\b(invalid\s+objects|dba\s+users|sql\s+session|database\s+schema|tablespace|table\s+list)\b',
            r'\b(total\s+invalid\s+objects|total\s+dba\s+users|top\s+sql\s+session)\b',
            r'\b(show\s+me.*schema|list.*schema\s+users|tablespace\s+summary)\b',
            r'\b(free\s+and\s+used|percentage\s+of\s+free|percentage\s+of\s+used)\b'
        ]

        # Entity extraction patterns for ERP
        self.entity_patterns = {
            'organizations': r'\b(?:[A-Z0-9]{2,10}[_\-][A-Z0-9]{2,10}|[A-Z]{2,}_ORG)\b',
            'business_groups': r'\b(?:[A-Z0-9]{2,10}[_\-]BG|[A-Z]{2,}_BUSINESS_GROUP)\b',
            'legal_entities': r'\b(?:[A-Z0-9]{2,10}[_\-]LE|[A-Z]{2,}_LEGAL_ENTITY)\b',
            'dates': r'\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}-[A-Z]{3}-\d{2,4}|[A-Z]{3}-\d{2,4})\b',
            'ordering_directions': r'\b(asc|ascending|desc|descending)\b',
            'aggregations': r'\b(avg|average|sum|total|count|max|min)\b',
            'trend_indicators': r'\b(trend|analysis|compare|correlation|monthly|weekly|daily|over\s+time)\b',
            'database_entities': r'\b(invalid\s+objects|dba\s+users|sql\s+sessions?|schema|tablespace|tables?)\b'
        }
    
    def _extract_terms_from_docs(self, docs: List[Dict]) -> List[str]:
        """Extract relevant terms from schema documents."""
        terms = []
        for doc in docs:
            if 'document' in doc:
                # Extract potential terms from the document
                # Look for terms in quotes or emphasized patterns
                quoted_terms = re.findall(r"['\"]([^'\"]+)['\"]", doc['document'])
                terms.extend(quoted_terms)
                
                # Look for column names specifically
                column_matches = re.findall(r"Column '([^']+)'", doc['document'])
                terms.extend(column_matches)
                
                # Look for table names
                table_matches = re.findall(r"Table '([^']+)'", doc['document'])
                terms.extend(table_matches)
        return list(set(terms))  # Remove duplicates
    
    def classify_query(self, query: str) -> QueryClassification:
        """
        Classify an ERP R12 user query and determine the best processing strategy.
        
        Args:
            query: User's natural language query
            
        Returns:
            QueryClassification with intent, confidence, and strategy
        """
        query_lower = query.lower()
        entities = self._extract_entities(query)
        
        # Calculate pattern matches for each intent
        intent_scores = {
            QueryIntent.ORGANIZATION_QUERY: self._calculate_pattern_score(query_lower, self.organization_patterns),
            QueryIntent.BUSINESS_GROUP_QUERY: self._calculate_pattern_score(query_lower, self.business_group_patterns),
            QueryIntent.LEGAL_ENTITY_QUERY: self._calculate_pattern_score(query_lower, self.legal_entity_patterns),
            QueryIntent.FINANCIAL_QUERY: self._calculate_pattern_score(query_lower, self.financial_patterns),
            QueryIntent.INVENTORY_QUERY: self._calculate_pattern_score(query_lower, self.inventory_patterns),
            QueryIntent.SIMPLE_LOOKUP: self._calculate_pattern_score(query, self.simple_patterns),
            QueryIntent.COMPLEX_ANALYTICS: self._calculate_pattern_score(query_lower, self.complex_patterns),
            QueryIntent.DATABASE_QUERY: self._calculate_pattern_score(query_lower, self.database_patterns)
        }
        
        # Add active/usable pattern scoring
        active_score = self._calculate_pattern_score(query_lower, self.active_patterns)
        # Boost organization and business group scores if active patterns are found
        if active_score > 0.5:
            intent_scores[QueryIntent.ORGANIZATION_QUERY] += 0.2
            intent_scores[QueryIntent.BUSINESS_GROUP_QUERY] += 0.2
        
        # Determine primary intent
        primary_intent = max(intent_scores.keys(), key=lambda k: intent_scores[k])
        confidence = intent_scores[primary_intent]
        
        # Fallback to general query if no strong match
        if confidence < 0.3:
            primary_intent = QueryIntent.GENERAL_QUERY
            confidence = 0.5  # Default confidence for general queries
        
        # Calculate complexity score
        complexity_score = self._calculate_complexity(query, entities)
        
        # Determine processing strategy
        strategy = self._determine_strategy(primary_intent, confidence, complexity_score)
        
        # Generate reasoning
        reasoning = self._generate_reasoning(primary_intent, confidence, complexity_score, entities)
        
        classification = QueryClassification(
            intent=primary_intent,
            confidence=confidence,
            strategy=strategy,
            reasoning=reasoning,
            entities=entities,
            complexity_score=complexity_score
        )
        
        self.logger.info(f"ERP Query classified: {primary_intent.value} (confidence: {confidence:.2f}, strategy: {strategy.value})")
        
        return classification
    
    def _calculate_pattern_score(self, text: str, patterns: List[str]) -> float:
        """Calculate pattern matching score for given text."""
        matches = 0
        total_patterns = len(patterns)
        
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                matches += 1
        
        return matches / total_patterns if total_patterns > 0 else 0.0
    
    def _extract_entities(self, query: str) -> Dict[str, List[str]]:
        """Extract relevant entities from the query."""
        entities = {}
        
        for entity_type, pattern in self.entity_patterns.items():
            matches = re.findall(pattern, query, re.IGNORECASE)
            if matches:
                # Handle both string matches and tuple matches from multiple capturing groups
                processed_matches = []
                for match in matches:
                    if isinstance(match, tuple):
                        # Join tuple elements, filtering out empty strings
                        joined = ''.join(filter(None, match))
                        if joined:
                            processed_matches.append(joined)
                    else:
                        processed_matches.append(match)
                
                # Remove duplicates while preserving order
                unique_matches = []
                for match in processed_matches:
                    if match not in unique_matches:
                        unique_matches.append(match)
                entities[entity_type] = unique_matches
        
        return entities
    
    def _calculate_complexity(self, query: str, entities: Dict[str, List[str]]) -> float:
        """Calculate query complexity score."""
        complexity_factors = 0
        
        # Length factor
        if len(query.split()) > 15:
            complexity_factors += 0.3
        
        # Multiple entities factor
        if len(entities) > 2:
            complexity_factors += 0.2
        
        # Date range queries
        if len(entities.get('dates', [])) > 1:
            complexity_factors += 0.2
        
        # Complex SQL operations (detected from natural language)
        complex_operations = ['group by', 'sum', 'average', 'count', 'max', 'min', 'trend', 'compare']
        for op in complex_operations:
            if op in query.lower():
                complexity_factors += 0.1
        
        # Multi-field queries
        multi_field_indicators = ['vs', 'versus', 'compare', ' and ', '&', ' with ', 'vs.']
        if any(ind in query.lower() for ind in multi_field_indicators):
            complexity_factors += 0.25
        
        # Time-series analysis
        time_series_indicators = ['monthly', 'weekly', 'daily', 'quarterly', 'over time', 'trend']
        if any(ind in query.lower() for ind in time_series_indicators):
            complexity_factors += 0.25
        
        # Trend analysis indicators
        if entities.get('trend_indicators'):
            complexity_factors += 0.2
        
        # Aggregation complexity
        if len(entities.get('aggregations', [])) > 1:
            complexity_factors += 0.15
            
        # Ordering complexity
        if entities.get('ordering_directions'):
            complexity_factors += 0.1
        
        return min(complexity_factors, 1.0)  # Cap at 1.0

    def _determine_strategy(self, intent: QueryIntent, confidence: float, complexity: float) -> ModelSelectionStrategy:
        """Determine the best processing strategy based on classification."""
        
        # High confidence simple lookups can use local model only
        if intent == QueryIntent.SIMPLE_LOOKUP and confidence > 0.8 and complexity < 0.3:
            return ModelSelectionStrategy.LOCAL_ONLY
        
        # Complex analytics should use best available models
        if intent == QueryIntent.COMPLEX_ANALYTICS or complexity > 0.7:
            return ModelSelectionStrategy.BEST_AVAILABLE
        
        # Organization and business group queries benefit from API models
        if intent in [QueryIntent.ORGANIZATION_QUERY, QueryIntent.BUSINESS_GROUP_QUERY] and confidence > 0.5:
            return ModelSelectionStrategy.API_PREFERRED
        
        # Financial and inventory queries can use parallel processing for better accuracy
        if intent in [QueryIntent.FINANCIAL_QUERY, QueryIntent.INVENTORY_QUERY] and confidence > 0.6:
            return ModelSelectionStrategy.HYBRID_PARALLEL
        
        # Database queries should use API models for better accuracy with system metadata
        if intent == QueryIntent.DATABASE_QUERY:
            return ModelSelectionStrategy.API_PREFERRED
        
        # Default to hybrid parallel for balanced performance
        return ModelSelectionStrategy.HYBRID_PARALLEL

    def _generate_reasoning(self, intent: QueryIntent, confidence: float, complexity: float, entities: Dict[str, List[str]]) -> str:
        """Generate human-readable reasoning for the classification."""
        reasoning_parts = []
        
        reasoning_parts.append(f"Classified as {intent.value} with {confidence:.1%} confidence")
        
        if entities:
            entity_summary = []
            for entity_type, values in entities.items():
                entity_summary.append(f"{entity_type}: {', '.join(values[:3])}")
            reasoning_parts.append(f"Detected entities: {'; '.join(entity_summary)}")
        
        if complexity > 0.5:
            reasoning_parts.append(f"High complexity ({complexity:.1%}) detected")
        
        return ". ".join(reasoning_parts)

class ConfidenceThresholdManager:
    """Manages confidence thresholds for ERP R12 hybrid processing decisions."""
    
    def __init__(self, config):
        self.local_confidence_threshold = config.LOCAL_CONFIDENCE_THRESHOLD
        self.skip_api_threshold = config.SKIP_API_THRESHOLD
        self.force_hybrid_threshold = config.FORCE_HYBRID_THRESHOLD
        self.logger = logging.getLogger(__name__)
    
    def should_skip_api(self, local_confidence: float, classification: QueryClassification) -> bool:
        """Determine if API call should be skipped based on local confidence."""
        
        # Always skip API for simple lookups with high local confidence
        if (classification.intent == QueryIntent.SIMPLE_LOOKUP and 
            local_confidence > self.skip_api_threshold):
            self.logger.info(f"Skipping API: Simple lookup with high confidence ({local_confidence:.2f})")
            return True
        
        # Skip API for very high confidence local responses
        if local_confidence > self.skip_api_threshold:
            self.logger.info(f"Skipping API: High local confidence ({local_confidence:.2f})")
            return True
        
        return False
    
    def should_force_hybrid(self, local_confidence: float, classification: QueryClassification) -> bool:
        """Determine if hybrid processing should be forced."""
        
        # Force hybrid for complex analytics regardless of local confidence
        if classification.intent == QueryIntent.COMPLEX_ANALYTICS:
            self.logger.info("Forcing hybrid: Complex analytics query")
            return True
        
        # Force hybrid for low local confidence
        if local_confidence < self.force_hybrid_threshold:
            self.logger.info(f"Forcing hybrid: Low local confidence ({local_confidence:.2f})")
            return True
        
        # Force hybrid for organization queries (critical business data)
        if (classification.intent in [QueryIntent.ORGANIZATION_QUERY, QueryIntent.BUSINESS_GROUP_QUERY] and 
            classification.confidence > 0.6):
            self.logger.info("Forcing hybrid: Critical organization query")
            return True
        
        return False
    
    def get_processing_decision(self, local_confidence: float, classification: QueryClassification) -> Dict[str, any]:
        """Get comprehensive processing decision."""
        
        decision = {
            'use_local': True,  # Always use local as baseline
            'use_api': True,    # Default to using API
            'processing_mode': 'hybrid_parallel',
            'reasoning': []
        }
        
        # Check for API skip conditions
        if self.should_skip_api(local_confidence, classification):
            decision['use_api'] = False
            decision['processing_mode'] = 'local_only'
            decision['reasoning'].append('High local confidence allows skipping API')
        
        # Check for forced hybrid conditions
        elif self.should_force_hybrid(local_confidence, classification):
            decision['use_api'] = True
            decision['processing_mode'] = 'forced_hybrid'
            decision['reasoning'].append('Low confidence or complex query requires hybrid processing')
        
        # Apply strategy from classification
        if classification.strategy == ModelSelectionStrategy.LOCAL_ONLY:
            decision['use_api'] = False
            decision['processing_mode'] = 'local_only'
            decision['reasoning'].append('Classification suggests local-only processing')
        
        elif classification.strategy == ModelSelectionStrategy.API_PREFERRED:
            decision['processing_mode'] = 'api_preferred'
            decision['reasoning'].append('Classification prefers API model')
        
        return decision
