# backend/app/query_classifier.py
import re
import logging
from typing import Dict, List, Tuple, Optional
from enum import Enum
from dataclasses import dataclass
from datetime import datetime as _dt

logger = logging.getLogger(__name__)

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
    """Query intent classification for routing decisions."""
    PRODUCTION_QUERY = "production_query"
    HR_EMPLOYEE_QUERY = "hr_employee_query"
    TNA_TASK_QUERY = "tna_task_query"
    SIMPLE_LOOKUP = "simple_lookup"
    COMPLEX_ANALYTICS = "complex_analytics"
    GENERAL_QUERY = "general_query"

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
    """Intelligent query classification for hybrid AI routing."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._init_patterns()
    
    def _init_patterns(self):
        """Initialize regex patterns for different query types."""
        
        # Production/Manufacturing patterns
        self.production_patterns = [
            r'\b(production|produce|manufacturing|floor|defect|dhu|efficiency)\b',
            r'\b(CAL|Winner|BIP)\b',
            r'\b(sewing|cutting|finishing|washing|packing)\b',
            r'\b(T_PROD|T_PROD_DAILY)\b',
            r'\b(floor.{0,10}wise|summary|total|qty|quantity)\b'
        ]
        
        # HR/Employee patterns
        self.hr_patterns = [
            r'\b(employee|staff|worker|president|manager|supervisor)\b',
            r'\b(salary|wage|department|designation|job.?title)\b',
            r'\b(EMP|EMPLOYEE|HR)\b',
            r'\b(who\s+is|employee\s+list|staff\s+list)\b'
        ]
        
        # TNA Task patterns
        self.tna_patterns = [
            r'\bCTL-\d{2}-\d{5,6}\b',
            r'\b(PP\s+Approval|task|TNA|approval)\b',
            r'\b(T_TNA_STATUS|finish\s+date|task\s+status)\b',
            r'\b(job\s+no|po\s+number|buyer|style\s+ref)\b'
        ]
        
        # Simple lookup patterns (enhanced)
        self.simple_patterns = [
            r'^\s*(list|show)\s+(employee|staff|worker)s?\s*$',
            r'^\s*(employee|staff|worker)\s+(list|data)\s*$',
            r'^\s*\w+\s+(id|number|code)\s+\d+\s*$',
            r'^\s*(what\s+is|who\s+is|show\s+me)\s+\w+\s*$'
        ]
        
        # Complex analytics patterns
        self.complex_patterns = [
            r'\b(trend|analysis|compare|correlation|prediction)\b',
            r'\b(average|median|variance|standard\s+deviation)\b',
            r'\b(group\s+by|order\s+by|having|window\s+function)\b',
            r'\b(last\s+\d+\s+(months|years)|year\s+over\s+year)\b'
        ]

        # Entity extraction patterns
        self.entity_patterns = {
            'companies': r'\b(CAL|Winner|BIP|Chorka\s+Apparel)\b',
            'floors': r'\b(?:Sewing|Cutting|Finishing).{0,20}(?:Floor|F\d+|\d+[A-Z]?)\b',
            'dates': r'\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}-[A-Z]{3}-\d{2,4}|[A-Z]{3}-\d{2,4})\b',
            'ctl_codes': r'\bCTL-\d{2}-\d{5,6}\b',
            'metrics': r'\b(production|defect|efficiency|DHU|qty|quantity)\b'
        }
    def classify_query(self, query: str) -> QueryClassification:
        """
        Classify a user query and determine the best processing strategy.
        
        Args:
            query: User's natural language query
            
        Returns:
            QueryClassification with intent, confidence, and strategy
        """
        query_lower = query.lower()
        entities = self._extract_entities(query)
        
        # Calculate pattern matches for each intent
        intent_scores = {
            QueryIntent.PRODUCTION_QUERY: self._calculate_pattern_score(query_lower, self.production_patterns),
            QueryIntent.HR_EMPLOYEE_QUERY: self._calculate_pattern_score(query_lower, self.hr_patterns),
            QueryIntent.TNA_TASK_QUERY: self._calculate_pattern_score(query_lower, self.tna_patterns),
            QueryIntent.SIMPLE_LOOKUP: self._calculate_pattern_score(query, self.simple_patterns),
            QueryIntent.COMPLEX_ANALYTICS: self._calculate_pattern_score(query_lower, self.complex_patterns)
        }
        
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
        
        self.logger.info(f"Query classified: {primary_intent.value} (confidence: {confidence:.2f}, strategy: {strategy.value})")
        
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
        
        return min(complexity_factors, 1.0)  # Cap at 1.0

    def _determine_strategy(self, intent: QueryIntent, confidence: float, complexity: float) -> ModelSelectionStrategy:
        """Determine the best processing strategy based on classification."""
        
        # High confidence simple lookups can use local model only
        if intent == QueryIntent.SIMPLE_LOOKUP and confidence > 0.8 and complexity < 0.3:
            return ModelSelectionStrategy.LOCAL_ONLY
        
        # Complex analytics should use best available models
        if intent == QueryIntent.COMPLEX_ANALYTICS or complexity > 0.7:
            return ModelSelectionStrategy.BEST_AVAILABLE
        
        # Production and TNA queries benefit from API models (lowered threshold)
        if intent in [QueryIntent.PRODUCTION_QUERY, QueryIntent.TNA_TASK_QUERY] and confidence > 0.4:
            return ModelSelectionStrategy.API_PREFERRED
        
        # HR queries can use parallel processing for better accuracy
        if intent == QueryIntent.HR_EMPLOYEE_QUERY and confidence > 0.5:
            return ModelSelectionStrategy.HYBRID_PARALLEL
        
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
    """Manages confidence thresholds for hybrid processing decisions."""
    
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
        
        # Force hybrid for production queries (critical business data)
        if (classification.intent == QueryIntent.PRODUCTION_QUERY and 
            classification.confidence > 0.7):
            self.logger.info("Forcing hybrid: Critical production query")
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