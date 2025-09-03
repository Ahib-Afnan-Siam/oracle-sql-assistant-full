# backend/test_manufacturing_queries.py
import asyncio
from app.openrouter_client import get_openrouter_client

async def test_manufacturing_sql():
    """Test SQL generation for manufacturing-specific queries."""
    
    print("🏭 Testing Manufacturing Domain SQL Generation...")
    
    client = get_openrouter_client()
    
    # Real manufacturing queries from your domain
    manufacturing_tests = [
        {
            "query": "Show floor-wise production and defect summary for CAL company in August 2025",
            "expected_keywords": ["T_PROD", "CAL", "FLOOR", "SUM", "AUG", "2025"]
        },
        {
            "query": "What is the total defect qty of Sewing CAL-2A on 22/08/2025?",
            "expected_keywords": ["T_PROD_DAILY", "DEFECT_QTY", "SEWING", "CAL-2A", "22-AUG-25"]
        },
        {
            "query": "CTL-25-01175 give me information about PP Approval tasks",
            "expected_keywords": ["T_TNA_STATUS", "CTL-25-01175", "PP APPROVAL", "JOB_NO"]
        },
        {
            "query": "What is the salary of the president?",
            "expected_keywords": ["EMP", "SALARY", "PRESIDENT", "JOB"]
        }
    ]
    
    schema_context = """
    Tables:
    - T_PROD_DAILY: COMPANY, FLOOR_NAME, PRODUCTION_QTY, DEFECT_QTY, PROD_DATE
    - T_TNA_STATUS: JOB_NO, TASK_SHORT_NAME, TASK_FINISH_DATE, BUYER_NAME, STYLE_REF_NO
    - EMP: EMP_ID, FULL_NAME, JOB_TITLE, SALARY, EMAIL_ADDRESS
    """
    
    for i, test in enumerate(manufacturing_tests, 1):
        print(f"\n🧪 Test {i}: {test['query']}")
        
        response = await client.get_sql_response(
            user_query=test['query'],
            schema_context=schema_context,
            model_type="production"
        )
        
        if response.success:
            sql = response.content.upper()
            print(f"✅ Generated SQL:")
            print(f"   {response.content}")

            # Check for expected keywords
            found_keywords = [kw for kw in test['expected_keywords'] if kw in sql]
            missing_keywords = [kw for kw in test['expected_keywords'] if kw not in sql]
            
            if len(found_keywords) >= len(test['expected_keywords']) // 2:
                print(f"✅ SQL contains expected elements: {found_keywords}")
            else:
                print(f"⚠️  Missing some elements: {missing_keywords}")
        else:
            print(f"❌ Failed: {response.error}")
    
    print("\n🎯 Manufacturing SQL generation test completed!")

if __name__ == "__main__":
    asyncio.run(test_manufacturing_sql())