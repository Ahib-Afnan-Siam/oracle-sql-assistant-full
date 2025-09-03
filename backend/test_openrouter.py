# backend/test_openrouter.py
import asyncio
import logging
import json
from datetime import datetime as _dt
from app.openrouter_client import get_openrouter_client, test_all_models, OpenRouterError
from app.config import API_MODELS, OPENROUTER_ENABLED

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_api_configuration():
    """Test API configuration and basic connectivity."""
    print("🔧 Testing OpenRouter API Configuration...")
    
    try:
        if not OPENROUTER_ENABLED:
            print("❌ OpenRouter is not enabled. Check your .env configuration.")
            return False
        
        client = get_openrouter_client()
        print(f"✅ Client initialized successfully")
        print(f"   - Timeout: {client.timeout}s")
        print(f"   - Max retries: {client.max_retries}")
        print(f"   - Retry delay: {client.retry_delay}s")
        return True
        
    except OpenRouterError as e:
        print(f"❌ OpenRouter configuration error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

async def test_model_availability():
    """Test availability of all configured models."""
    print("\n📋 Testing Model Availability...")
    
    try:
        results = await test_all_models()
        
        total_models = 0
        available_models = 0
        
        for model_type, model_results in results.items():
            print(f"\n  🔍 {model_type.upper()} Models:")
            
            for result in model_results:
                total_models += 1
                priority = result.metadata.get("priority", "unknown")
                
                if result.available:
                    available_models += 1
                    print(f"    ✅ {priority}: {result.model}")
                    print(f"       Response time: {result.response_time:.2f}s")
                    print(f"       Test response: '{result.test_response}'")
                else:
                    print(f"    ❌ {priority}: {result.model}")
                    print(f"       Error: {result.error}")
        
        print(f"\n📊 Summary: {available_models}/{total_models} models available")
        return available_models > 0
        
    except Exception as e:
        print(f"❌ Model availability test failed: {e}")
        return False

async def test_sql_generation():
    """Test SQL generation with different query types."""
    print("\n🔍 Testing SQL Generation...")
    
    client = get_openrouter_client()
    
    test_cases = [
        {
            "name": "Production Query (DeepSeek)",
            "model_type": "production",
            "query": "Show me total production quantity and defect quantity for CAL company in August 2025",
            "schema": "Table: T_PROD_DAILY (COMPANY VARCHAR2(50), FLOOR_NAME VARCHAR2(100), PRODUCTION_QTY NUMBER, DEFECT_QTY NUMBER, PROD_DATE DATE)"
        },
        {
            "name": "HR Query (Llama)",
            "model_type": "hr",
            "query": "Find all employees with president role and their salaries",
            "schema": "Table: EMP (EMP_ID NUMBER, FULL_NAME VARCHAR2(100), JOB_TITLE VARCHAR2(50), SALARY NUMBER)"
        },
        {
            "name": "TNA Query (DeepSeek)",
            "model_type": "tna",
            "query": "Show all PP Approval tasks for job number CTL-25-01175",
            "schema": "Table: T_TNA_STATUS (JOB_NO VARCHAR2(20), TASK_SHORT_NAME VARCHAR2(100), TASK_FINISH_DATE DATE, ACTUAL_FINISH_DATE DATE, BUYER_NAME VARCHAR2(100))"
        }
    ]
    
    successful_tests = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n  🧪 Test {i}: {test_case['name']}")
        print(f"     Query: {test_case['query']}")
        
        try:
            response = await client.get_sql_response(
                user_query=test_case['query'],
                schema_context=test_case['schema'],
                model_type=test_case['model_type']
            )
            
            if response.success:
                successful_tests += 1
                print(f"     ✅ Success!")
                print(f"     Model: {response.model}")
                print(f"     Response time: {response.response_time:.2f}s")
                print(f"     Generated SQL:")
                # Format SQL for better readability
                sql_lines = response.content.strip().split('\n')
                for line in sql_lines:
                    print(f"       {line}")
                
                if response.usage:
                    print(f"     Token usage: {response.usage}")
            else:
                print(f"     ❌ Failed: {response.error}")
                
        except Exception as e:
            print(f"     ❌ Exception: {e}")
    
    print(f"\n📊 SQL Generation: {successful_tests}/{len(test_cases)} tests passed")
    return successful_tests == len(test_cases)

async def test_fallback_mechanism():
    """Test fallback mechanism when primary model fails."""
    print("\n🔄 Testing Fallback Mechanism...")
    
    client = get_openrouter_client()
    
    # Test with a query that should work with fallback
    test_query = "Show production data for last month"
    schema_context = "Table: T_PROD_DAILY (COMPANY VARCHAR2(50), PRODUCTION_QTY NUMBER, PROD_DATE DATE)"
    
    try:
        response = await client.get_model_with_fallback(
            model_type="production",
            user_query=test_query,
            schema_context=schema_context
        )
        
        if response.success:
            print(f"  ✅ Fallback mechanism working")
            print(f"     Final model used: {response.model}")
            print(f"     Fallback used: {response.metadata.get('fallback_used', False)}")
            print(f"     Model priority: {response.metadata.get('model_priority', 'unknown')}")
            return True
        else:
            print(f"  ❌ All models failed: {response.error}")
            return False
            
    except Exception as e:
        print(f"  ❌ Fallback test failed: {e}")
        return False

async def test_rate_limiting():
    """Test rate limiting and concurrent requests."""
    print("\n⏱️  Testing Rate Limiting...")
    
    client = get_openrouter_client()
    
    # Send multiple concurrent requests
    tasks = []
    for i in range(3):
        task = client.chat_completion(
            messages=[{"role": "user", "content": f"Say 'Test {i+1}' and nothing else"}],
            model="deepseek/deepseek-chat",
            max_tokens=10
        )
        tasks.append(task)
    
    try:
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful_requests = 0
        for i, response in enumerate(responses):
            if isinstance(response, Exception):
                print(f"  Request {i+1}: ❌ Exception - {response}")
            elif response.success:
                successful_requests += 1
                print(f"  Request {i+1}: ✅ Success - '{response.content}' ({response.response_time:.2f}s)")
            else:
                print(f"  Request {i+1}: ❌ Failed - {response.error}")
        
        print(f"  📊 Rate limiting: {successful_requests}/{len(tasks)} requests successful")
        return successful_requests > 0
        
    except Exception as e:
        print(f"  ❌ Rate limiting test failed: {e}")
        return False

async def run_comprehensive_test():
    """Run all tests and provide summary."""
    print("🚀 Starting Comprehensive OpenRouter API Tests")
    print("=" * 60)
    
    test_results = {}
    
    # Run all tests
    test_results['configuration'] = await test_api_configuration()
    
    if test_results['configuration']:
        test_results['model_availability'] = await test_model_availability()
        test_results['sql_generation'] = await test_sql_generation()
        test_results['fallback_mechanism'] = await test_fallback_mechanism()
        test_results['rate_limiting'] = await test_rate_limiting()
    else:
        print("\n❌ Skipping other tests due to configuration failure")
        return
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 TEST SUMMARY")
    print("=" * 60)
    
    passed_tests = sum(1 for result in test_results.values() if result)
    total_tests = len(test_results)
    
    for test_name, result in test_results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name.replace('_', ' ').title()}")
    
    print(f"\n🎯 Overall Result: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("🎉 All tests passed! OpenRouter integration is ready.")
        print("\n🚀 Next steps:")
        print("   1. ✅ Configuration complete")
        print("   2. ✅ API connectivity verified")  
        print("   3. ✅ Model availability confirmed")
        print("   4. ✅ SQL generation working")
        print("   5. ➡️  Ready for Phase 2: Hybrid Processing Engine")
    else:
        print("⚠️  Some tests failed. Please check the errors above.")
        if not test_results.get('configuration'):
            print("   🔧 Fix configuration issues first")
        if not test_results.get('model_availability'):
            print("   🤖 Check model availability and API limits")

if __name__ == "__main__":
    asyncio.run(run_comprehensive_test())