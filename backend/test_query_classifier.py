# backend/test_query_classifier.py
import asyncio
from app.query_classifier import QueryClassifier, QueryIntent, ModelSelectionStrategy
from app.config import LOCAL_CONFIDENCE_THRESHOLD, SKIP_API_THRESHOLD, FORCE_HYBRID_THRESHOLD

def test_query_classification():
    """Test query classification system with real manufacturing queries."""
    
    print("🔍 Testing Query Classification System...")
    
    classifier = QueryClassifier()
    
    # Test cases with expected results
    test_queries = [
        {
            "query": "Show floor-wise production summary for CAL company in August 2025",
            "expected_intent": QueryIntent.PRODUCTION_QUERY,
            "expected_strategy": ModelSelectionStrategy.API_PREFERRED
        },
        {
            "query": "What is the salary of the president?",
            "expected_intent": QueryIntent.HR_EMPLOYEE_QUERY,
            "expected_strategy": ModelSelectionStrategy.HYBRID_PARALLEL
        },
        {
            "query": "CTL-25-01175 give me PP Approval task information",
            "expected_intent": QueryIntent.TNA_TASK_QUERY,
            "expected_strategy": ModelSelectionStrategy.API_PREFERRED
        },
        {
            "query": "employee list",
            "expected_intent": QueryIntent.SIMPLE_LOOKUP,
            "expected_strategy": ModelSelectionStrategy.LOCAL_ONLY
        },
        {
            "query": "Show production trend analysis for last 6 months with efficiency correlation",
            "expected_intent": QueryIntent.COMPLEX_ANALYTICS,
            "expected_strategy": ModelSelectionStrategy.BEST_AVAILABLE
        }
    ]
    
    print(f"\n📊 Configuration:")
    print(f"   Local Confidence Threshold: {LOCAL_CONFIDENCE_THRESHOLD}")
    print(f"   Skip API Threshold: {SKIP_API_THRESHOLD}")
    print(f"   Force Hybrid Threshold: {FORCE_HYBRID_THRESHOLD}")
    
    successful_tests = 0
    
    for i, test in enumerate(test_queries, 1):
        print(f"\n🧪 Test {i}: {test['query']}")
        
        classification = classifier.classify_query(test['query'])
        
        print(f"   Intent: {classification.intent.value}")
        print(f"   Confidence: {classification.confidence:.2f}")
        print(f"   Strategy: {classification.strategy.value}")
        print(f"   Complexity: {classification.complexity_score:.2f}")
        print(f"   Entities: {classification.entities}")
        print(f"   Reasoning: {classification.reasoning}")
        
        # Check if classification matches expectations
        intent_match = classification.intent == test['expected_intent']
        strategy_match = classification.strategy == test['expected_strategy']
        
        if intent_match and strategy_match:
            print(f"   ✅ Classification correct")
            successful_tests += 1
        else:
            print(f"   ⚠️  Classification differs from expected")
            if not intent_match:
                print(f"      Expected intent: {test['expected_intent'].value}")
            if not strategy_match:
                print(f"      Expected strategy: {test['expected_strategy'].value}")
    
    print(f"\n📊 Classification Results: {successful_tests}/{len(test_queries)} tests passed")
    
    # Test confidence threshold manager
    print(f"\n🎯 Testing Confidence Threshold System...")
    test_confidence_scenarios(classifier)
    
    print(f"\n🎉 Query Classification System tested!")

def test_confidence_scenarios(classifier):
    """Test confidence threshold decision making."""
    from app.query_classifier import ConfidenceThresholdManager
    import app.config as config
    
    threshold_manager = ConfidenceThresholdManager(config)
    
    scenarios = [
        {
            "query": "employee list",
            "local_confidence": 0.9,
            "expected_decision": "local_only"
        },
        {
            "query": "Show complex production trend analysis",
            "local_confidence": 0.8,
            "expected_decision": "forced_hybrid"
        },
        {
            "query": "What is total production for CAL?",
            "local_confidence": 0.4,
            "expected_decision": "forced_hybrid"
        }
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        classification = classifier.classify_query(scenario['query'])
        decision = threshold_manager.get_processing_decision(
            scenario['local_confidence'], 
            classification
        )
        
        print(f"   Scenario {i}: {scenario['query'][:50]}...")
        print(f"      Local confidence: {scenario['local_confidence']}")
        print(f"      Decision: {decision['processing_mode']}")
        print(f"      Reasoning: {'; '.join(decision['reasoning'])}")
        
        expected_ok = scenario['expected_decision'] in decision['processing_mode']
        print(f"      {'✅' if expected_ok else '⚠️'} {'Expected' if expected_ok else 'Unexpected'} result")

if __name__ == "__main__":
    test_query_classification()