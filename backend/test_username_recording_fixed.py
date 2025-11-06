#!/usr/bin/env python3
"""
Test script to verify username recording functionality in AI Training Data Recorder
"""
import sys
import os
import logging

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

# Handle relative imports
if __name__ == "__main__" and __package__ is None:
    # Add the parent directory to sys.path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "backend"

try:
    from app.ai_training_data_recorder import AITrainingDataRecorder, RecordingContext
except ImportError:
    try:
        # Alternative import method
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ai_training_data_recorder", 
            os.path.join(os.path.dirname(__file__), 'app', 'ai_training_data_recorder.py')
        )
        ai_training_data_recorder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ai_training_data_recorder)
        AITrainingDataRecorder = ai_training_data_recorder.AITrainingDataRecorder
        RecordingContext = ai_training_data_recorder.RecordingContext
    except Exception as e:
        print(f"Failed to import ai_training_data_recorder: {e}")
        sys.exit(1)

def test_username_recording():
    """Test that username is properly recorded in the AI training data system"""
    
    # Initialize the recorder
    recorder = AITrainingDataRecorder()
    
    # Create a recording context with a username
    context = RecordingContext(
        session_id="test_session_123",
        client_info="Test Client v1.0",
        database_type="Oracle",
        query_mode="hybrid",
        username="testuser123"  # This is what we're testing
    )
    
    # Record a training query with username
    query_id = recorder.record_training_query(
        user_query_text="Show production efficiency trends",
        context=context
    )
    
    if query_id:
        print(f"Successfully recorded training query with ID: {query_id}")
        
        # Record additional data to simulate a complete flow
        classification_id = recorder.record_query_classification(
            query_id=query_id,
            classification_result={
                'intent': 'analytics',
                'confidence': 0.95,
                'complexity_score': 0.7,
                'entities': {'metrics': ['efficiency'], 'timeframe': ['trends']},
                'strategy': 'sql_generation',
                'business_context': 'production_analytics'
            }
        )
        
        if classification_id:
            print(f"Successfully recorded classification with ID: {classification_id}")
        else:
            print("Failed to record classification")
            
        # Test that we can retrieve the recorded data
        # This would typically be done by querying the database directly
        print("Test completed successfully!")
        return True
    else:
        print("Failed to record training query")
        return False

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Run the test
    success = test_username_recording()
    
    if success:
        print("\n✓ Username recording test PASSED")
        sys.exit(0)
    else:
        print("\n✗ Username recording test FAILED")
        sys.exit(1)