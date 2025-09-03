# backend/quick_test_api.py
import asyncio
from app.openrouter_client import get_openrouter_client

async def quick_test():
    """Quick test to verify API is working."""
    print("🔌 Quick OpenRouter API Test...")
    
    try:
        client = get_openrouter_client()
        
        # Simple test
        response = await client.chat_completion(
            messages=[{"role": "user", "content": "Say 'Hello from OpenRouter!' and nothing else"}],
            model="deepseek/deepseek-chat",
            max_tokens=20
        )
        
        if response.success:
            print(f"✅ API is working!")
            print(f"   Response: {response.content}")
            print(f"   Model: {response.model}")
            print(f"   Time: {response.response_time:.2f}s")
        else:
            print(f"❌ API test failed: {response.error}")
            
    except Exception as e:
        print(f"❌ Test error: {e}")

if __name__ == "__main__":
    asyncio.run(quick_test())