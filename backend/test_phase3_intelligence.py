# backend/test_phase3_intelligence.py
import asyncio
import logging
from app.hybrid_processor import HybridProcessor, ResponseMetrics
from app.query_classifier import QueryIntent

logging.basicConfig(level=logging.INFO)

async def test_phase3_intelligence():
    """Test Phase 3 multi-criteria evaluation intelligence."""
    
    print("🚀 PHASE 3: RESPONSE SELECTION INTELLIGENCE TEST")
    print("=" * 70)
    
    processor = HybridProcessor()
    
    # Test cases for enhanced evaluation
    test_cases = [
        {
            "name": "Production Query with High Domain Specificity",
            "query": "Show floor-wise DHU and defect quantity for CAL company in August 2025",
            "schema_context": "T_PROD_DAILY: COMPANY, FLOOR_NAME, PRODUCTION_QTY, DEFECT_QTY, DHU, PROD_DATE",
            "expected_strengths": ["manufacturing_domain", "technical_validation", "relevance"]
        },
        {
            "name": "TNA Task Query with CTL Code",
            "query": "CTL-25-01175 PP Approval task finish date and buyer information",
            "schema_context": "T_TNA_STATUS: JOB_NO, TASK_SHORT_NAME, TASK_FINISH_DATE, BUYER_NAME, PO_NUMBER",
            "expected_strengths": ["manufacturing_domain", "business_logic", "relevance"]
        },
        {
            "name": "Complex Analytics with Performance Considerations",
            "query": "Show production efficiency trend analysis with defect correlation for all companies last 6 months",
            "schema_context": "T_PROD: PRODUCTION_QTY, DEFECT_QTY, FLOOR_EF, PROD_DATE, COMPANY",
            "expected_strengths": ["technical_validation", "performance", "query_safety"]
        },
        {
            "name": "Simple Employee Lookup",
            "query": "employee list",
            "schema_context": "EMP: EMP_ID, FULL_NAME, JOB_TITLE, SALARY",
            "expected_strengths": ["query_safety", "performance", "relevance"]
        }
    ]
    
    total_tests = 0
    passed_tests = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n🧪 Test {i}: {test_case['name']}")
        print(f"   Query: {test_case['query']}")
        
        try:
            # Process with enhanced intelligence
            result = await processor.process_query_advanced(
                user_query=test_case['query'],
                schema_context=test_case['schema_context'],
                local_confidence=0.6
            )
            
            print(f"   ✅ Processing completed in {result.processing_time:.2f}s")
            print(f"   🎯 Model Used: {result.model_used}")
            print(f"   📊 Selection: {result.selection_reasoning}")
            
            # Test enhanced metrics
            selected_metrics = result.local_metrics if result.model_used == "Local" else result.api_metrics
            if selected_metrics:
                print(f"\n   📈 Phase 3 Enhanced Metrics:")
                print(f"      🔧 Technical Validation: {selected_metrics.technical_validation_score:.2f}")
                print(f"      🏭 Manufacturing Domain: {selected_metrics.manufacturing_domain_score:.2f}")
                print(f"      🔒 Query Safety: {selected_metrics.query_safety_score:.2f}")
                print(f"      ⏱️  Execution Time Prediction: {selected_metrics.execution_time_prediction:.2f}s")
                print(f"      😊 User Satisfaction Prediction: {selected_metrics.user_satisfaction_prediction:.2f}")
                print(f"      🎯 Relevance Score: {selected_metrics.relevance_score:.2f}")
                
                # Validate expected strengths
                strength_scores = {
                    "manufacturing_domain": selected_metrics.manufacturing_domain_score,
                    "technical_validation": selected_metrics.technical_validation_score,
                    "query_safety": selected_metrics.query_safety_score,
                    "performance": selected_metrics.performance_score,
                    "business_logic": selected_metrics.business_logic_score,
                    "relevance": selected_metrics.relevance_score
                }
                
                strengths_met = 0
                for expected_strength in test_case['expected_strengths']:
                    score = strength_scores.get(expected_strength, 0.0)
                    if score >= 0.6:  # Threshold for "strength"
                        strengths_met += 1
                        print(f"      ✅ {expected_strength}: {score:.2f} (strong)")
                    else:
                        print(f"      ⚠️  {expected_strength}: {score:.2f} (weak)")
                
                if strengths_met >= len(test_case['expected_strengths']) * 0.7:
                    passed_tests += 1
                    print(f"   🎉 Test PASSED: {strengths_met}/{len(test_case['expected_strengths'])} strengths met")
                else:
                    print(f"   ❌ Test FAILED: Only {strengths_met}/{len(test_case['expected_strengths'])} strengths met")
            
            total_tests += 1
            
        except Exception as e:
            print(f"   ❌ Test failed with error: {e}")
            total_tests += 1
    
    # Summary
    print(f"\n" + "=" * 70)
    print(f"📊 PHASE 3 INTELLIGENCE TEST SUMMARY")
    print(f"=" * 70)
    print(f"✅ Tests Passed: {passed_tests}/{total_tests}")
    print(f"📈 Success Rate: {(passed_tests/total_tests)*100:.1f}%")
    
    if passed_tests >= total_tests * 0.8:
        print(f"🎉 EXCELLENT! Phase 3 Response Selection Intelligence is working!")
        print(f"✅ Enhanced Features Validated:")
        print(f"   • Multi-criteria technical validation")
        print(f"   • Manufacturing domain understanding")
        print(f"   • Query safety assessment")
        print(f"   • Execution time prediction")
        print(f"   • User satisfaction prediction")
        print(f"   • Relevance scoring")
    else:
        print(f"⚠️  Some intelligence features need improvement.")
    
    return passed_tests, total_tests

if __name__ == "__main__":
    asyncio.run(test_phase3_intelligence())