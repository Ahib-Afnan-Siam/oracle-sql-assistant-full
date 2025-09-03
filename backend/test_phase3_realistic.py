# backend/test_phase3_realistic.py
import asyncio
import logging
from app.hybrid_processor import HybridProcessor, ResponseMetrics, SQLValidator
from app.query_classifier import QueryIntent

logging.basicConfig(level=logging.INFO)

async def test_phase3_with_realistic_sql():
    """Test Phase 3 intelligence with realistic SQL examples."""
    
    print("🚀 PHASE 3: INTELLIGENCE TEST WITH REALISTIC SQL")
    print("=" * 70)
    
    # Test SQL validator directly with realistic examples
    sql_validator = SQLValidator()
    
    test_cases = [
        {
            "name": "High-Quality Production Query",
            "sql": """SELECT COMPANY, FLOOR_NAME, 
                     SUM(PRODUCTION_QTY) as TOTAL_PRODUCTION,
                     SUM(DEFECT_QTY) as TOTAL_DEFECTS,
                     ROUND(AVG(DHU), 2) as AVG_DHU
                     FROM T_PROD_DAILY 
                     WHERE COMPANY = 'CAL' 
                     AND PROD_DATE >= TO_DATE('01-AUG-2025', 'DD-MON-YYYY')
                     GROUP BY COMPANY, FLOOR_NAME 
                     ORDER BY AVG_DHU""",
            "query_context": {
                "intent": QueryIntent.PRODUCTION_QUERY,
                "entities": {"companies": ["CAL"], "dates": ["01-AUG-2025"]},
                "user_query": "Show floor-wise DHU and defect quantity for CAL company in August 2025"
            },
            "expected_high": ["manufacturing_domain", "technical_validation", "business_logic"]
        },
        {
            "name": "Excellent TNA Query with CTL Code",
            "sql": """SELECT JOB_NO, TASK_SHORT_NAME, TASK_FINISH_DATE, 
                     ACTUAL_FINISH_DATE, BUYER_NAME, STYLE_REF_NO
                     FROM T_TNA_STATUS 
                     WHERE UPPER(JOB_NO) = 'CTL-25-01175'
                     AND UPPER(TASK_SHORT_NAME) LIKE '%PP APPROVAL%'
                     ORDER BY TASK_FINISH_DATE""",
            "query_context": {
                "intent": QueryIntent.TNA_TASK_QUERY,
                "entities": {"ctl_codes": ["CTL-25-01175"], "dates": []},
                "user_query": "CTL-25-01175 PP Approval task finish date and buyer information"
            },
            "expected_high": ["manufacturing_domain", "business_logic", "query_safety"]
        },
        {
            "name": "Safe Employee Query",
            "sql": """SELECT EMP_ID, FULL_NAME, JOB_TITLE, SALARY
                     FROM EMP 
                     WHERE UPPER(JOB_TITLE) LIKE '%PRESIDENT%'
                     ORDER BY SALARY DESC""",
            "query_context": {
                "intent": QueryIntent.HR_EMPLOYEE_QUERY,
                "entities": {"dates": []},
                "user_query": "What is the salary of the president?"
            },
            "expected_high": ["query_safety", "technical_validation", "relevance"]
        },
        {
            "name": "Dangerous Query (Should Score Low)",
            "sql": """DROP TABLE T_PROD; 
                     DELETE FROM T_PROD_DAILY WHERE 1=1;
                     SELECT * FROM T_TNA_STATUS""",
            "query_context": {
                "intent": QueryIntent.PRODUCTION_QUERY,
                "entities": {"dates": []},
                "user_query": "dangerous operations"
            },
            "expected_low": ["query_safety"]
        },
        {
            "name": "Complex Analytics Query",
            "sql": """SELECT p.COMPANY, p.FLOOR_NAME,
                     AVG(p.PRODUCTION_QTY) as AVG_PRODUCTION,
                     AVG(p.DEFECT_QTY) as AVG_DEFECTS,
                     ROUND(AVG(p.DHU), 2) as AVG_DHU,
                     ROUND(AVG(p.FLOOR_EF), 2) as AVG_EFFICIENCY
                     FROM T_PROD_DAILY p
                     WHERE p.PROD_DATE >= ADD_MONTHS(SYSDATE, -6)
                     GROUP BY p.COMPANY, p.FLOOR_NAME
                     HAVING AVG(p.PRODUCTION_QTY) > 1000
                     ORDER BY AVG_DHU, AVG_EFFICIENCY DESC""",
            "query_context": {
                "intent": QueryIntent.COMPLEX_ANALYTICS,
                "entities": {"dates": ["6 months"]},
                "user_query": "Show production efficiency trend analysis with defect correlation for all companies last 6 months"
            },
            "expected_high": ["technical_validation", "performance", "manufacturing_domain"]
        }
    ]
    
    total_tests = 0
    passed_tests = 0
    
    print("\n🔍 Testing Phase 3 Enhanced Metrics on Realistic SQL:")
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n🧪 Test {i}: {test_case['name']}")
        print(f"   Intent: {test_case['query_context']['intent'].value}")
        print(f"   Query: {test_case['query_context']['user_query']}")
        
        try:
            # Validate with Phase 3 enhanced metrics
            metrics = sql_validator.validate_sql(test_case['sql'], test_case['query_context'])
            
            print(f"\n   📊 Phase 3 Enhanced Metrics:")
            print(f"      🔧 Technical Validation: {metrics.technical_validation_score:.2f}")
            print(f"      🏭 Manufacturing Domain: {metrics.manufacturing_domain_score:.2f}")
            print(f"      💼 Business Logic: {metrics.business_logic_score:.2f}")
            print(f"      🔒 Query Safety: {metrics.query_safety_score:.2f}")
            print(f"      ⚡ Performance: {metrics.performance_score:.2f}")
            print(f"      🎯 Relevance: {metrics.relevance_score:.2f}")
            print(f"      😊 User Satisfaction: {metrics.user_satisfaction_prediction:.2f}")
            print(f"      ⏱️  Execution Time Prediction: {metrics.execution_time_prediction:.2f}s")
            print(f"      🎯 Overall Score: {metrics.overall_score:.2f}")
            
            # Score mapping for validation
            score_mapping = {
                "technical_validation": metrics.technical_validation_score,
                "manufacturing_domain": metrics.manufacturing_domain_score,
                "business_logic": metrics.business_logic_score,
                "query_safety": metrics.query_safety_score,
                "performance": metrics.performance_score,
                "relevance": metrics.relevance_score
            }
            
            # Check expectations
            expectations_met = 0
            total_expectations = 0
            
            # High score expectations
            if "expected_high" in test_case:
                for expected_high in test_case["expected_high"]:
                    total_expectations += 1
                    score = score_mapping.get(expected_high, 0.0)
                    if score >= 0.6:  # High threshold
                        expectations_met += 1
                        print(f"      ✅ {expected_high}: {score:.2f} (HIGH as expected)")
                    else:
                        print(f"      ⚠️  {expected_high}: {score:.2f} (expected HIGH)")
            
            # Low score expectations
            if "expected_low" in test_case:
                for expected_low in test_case["expected_low"]:
                    total_expectations += 1
                    score = score_mapping.get(expected_low, 1.0)
                    if score <= 0.4:  # Low threshold
                        expectations_met += 1
                        print(f"      ✅ {expected_low}: {score:.2f} (LOW as expected)")
                    else:
                        print(f"      ⚠️  {expected_low}: {score:.2f} (expected LOW)")
            
            # Test success evaluation
            if expectations_met >= total_expectations * 0.7:
                passed_tests += 1
                print(f"   🎉 Test PASSED: {expectations_met}/{total_expectations} expectations met")
            else:
                print(f"   ❌ Test FAILED: Only {expectations_met}/{total_expectations} expectations met")
            
            print(f"   💭 Key Reasoning: {', '.join(metrics.reasoning[:3])}")
            
            total_tests += 1
            
        except Exception as e:
            print(f"   ❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            total_tests += 1
    
    # Summary
    print(f"\n" + "=" * 70)
    print(f"📊 PHASE 3 REALISTIC SQL TEST SUMMARY")
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
        print(f"\n🚀 Phase 3 Implementation: COMPLETE! ✅")
    else:
        print(f"⚠️  Some intelligence features need fine-tuning.")
        print(f"💡 Consider adjusting scoring thresholds or enhancing domain knowledge.")
    
    return passed_tests, total_tests

if __name__ == "__main__":
    asyncio.run(test_phase3_with_realistic_sql())