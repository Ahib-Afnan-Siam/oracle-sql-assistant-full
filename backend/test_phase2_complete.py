# backend/test_phase2_complete.py
import asyncio
import sys
import os

# Add the backend directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def run_complete_phase2_tests():
    """Run all Phase 2 tests in sequence."""
    
    print("🚀 PHASE 2: HYBRID AI SYSTEM - COMPLETE TESTING")
    print("=" * 70)
    print("Testing Query Classification System & Parallel Processing Engine")
    print("=" * 70)
    
    try:
        # Test 1: Query Classification System
        print("\n📋 STEP 1: Testing Query Classification System...")
        from test_query_classifier import test_query_classification
        test_query_classification()
        
        print("\n" + "✅" * 20)
        print("Query Classification System: PASSED")
        
        # Test 2: Hybrid Processor
        print("\n🔄 STEP 2: Testing Hybrid Processing Engine...")
        from test_hybrid_processor import test_hybrid_processor, test_parallel_processing_performance
        
        await test_hybrid_processor()
        await test_parallel_processing_performance()
        
        print("\n" + "✅" * 20)
        print("Hybrid Processing Engine: PASSED")
        
        # Final Summary
        print("\n" + "🎉" * 20)
        print("PHASE 2 COMPLETE: ALL TESTS PASSED!")
        print("🎯 Ready for Phase 3: Response Selection Intelligence")
        print("📈 Ready for Phase 4: RAG Integration")
        print("🔄 Ready for Phase 5: Training Data Collection")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import Error: {e}")
        print("💡 Make sure all required files are created and dependencies are installed")
        return False
    
    except Exception as e:
        print(f"❌ Test Error: {e}")
        print("💡 Check the error details above and fix any issues")
        return False

if __name__ == "__main__":
    success = asyncio.run(run_complete_phase2_tests())
    
    if success:
        print(f"\n🎯 NEXT STEPS:")
        print(f"1. ✅ Phase 1: OpenRouter API Integration - COMPLETE")
        print(f"2. ✅ Phase 2: Query Classification & Parallel Processing - COMPLETE")
        print(f"3. ➡️  Phase 3: Response Selection Intelligence")
        print(f"4. ➡️  Phase 4: RAG Integration")
        print(f"5. ➡️  Phase 5: Training Data Collection")
        print(f"6. ➡️  Phase 6: Continuous Learning Loop")
    else:
        print(f"\n⚠️  Fix the issues above before proceeding to Phase 3")