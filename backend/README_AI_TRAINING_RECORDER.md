# AI Training Data Recorder System

## Overview

The AI Training Data Recorder is a comprehensive system designed to capture all aspects of the SQL generation process for training the local model from API model data and feedback. This system replaces the previous hybrid data recording approach with a more structured and complete data collection mechanism.

## System Architecture

The recorder implements a complete data flow mapping:

1. **Query received** → Record in `AI_TRAINING_QUERIES`
2. **Classification done** → Record in `AI_QUERY_CLASSIFICATIONS`
3. **Schema retrieved** → Record in `AI_SCHEMA_CONTEXTS`
4. **Models process** → Record in `AI_MODEL_INTERACTIONS` (both API and local)
5. **Selection made** → Record in `AI_RESPONSE_SELECTIONS`
6. **SQL validated** → Record in `AI_SQL_PROCESSING`
7. **SQL executed** → Record in `AI_EXECUTION_RESULTS`
8. **Fallback triggered** → Record in `AI_FALLBACK_EVENTS`
9. **User feedback** → Record in `AI_USER_FEEDBACK`

## Key Features

### Recording Mechanisms
- **Synchronous recording** for critical data
- **Asynchronous background tasks** for non-critical data
- **Buffering mechanism** to handle high-volume scenarios
- **Retry logic** for recording failures

### Error Handling
- **Circuit breaker** pattern to prevent cascading failures
- **Health checks** for recording system monitoring
- **Comprehensive logging** for debugging and monitoring

### Data Flow Integration
The system integrates seamlessly with the existing hybrid processing pipeline, recording data at each stage of the processing flow without impacting user experience.

## Database Schema

The system uses 9 core tables with proper foreign key relationships:

1. `AI_TRAINING_QUERIES` - Base table for all user queries
2. `AI_QUERY_CLASSIFICATIONS` - Query classification results
3. `AI_SCHEMA_CONTEXTS` - Retrieved schema context information
4. `AI_MODEL_INTERACTIONS` - API and Local model interactions
5. `AI_RESPONSE_SELECTIONS` - Model response selection decisions
6. `AI_SQL_PROCESSING` - SQL validation and processing
7. `AI_EXECUTION_RESULTS` - SQL execution results
8. `AI_FALLBACK_EVENTS` - Fallback scenario tracking
9. `AI_USER_FEEDBACK` - User feedback on responses

The `AI_TRAINING_QUERIES` table includes a `USERNAME` column to track which user submitted each query.

## Implementation Files

- `backend/app/ai_training_data_recorder.py` - Main recorder implementation
- `backend/test_ai_training_recorder.py` - Test script
- `backend/demo_ai_training_integration.py` - Integration demonstration
- Database schema in existing setup files

## Usage Examples

### Basic Recording
```python
from app.ai_training_data_recorder import AITrainingDataRecorder, RecordingContext

recorder = AITrainingDataRecorder()

context = RecordingContext(
    session_id="session_123",
    client_info="Web Client v1.0",
    database_type="Oracle",
    query_mode="hybrid"
)

query_id = recorder.record_training_query(
    user_query_text="Show production efficiency trends",
    context=context
)
```

### Complete Processing Flow
```python
# Record complete processing flow
processing_data = {
    'user_query_text': "Show production efficiency trends",
    'session_id': "session_123",
    'client_info': "Web Client v1.0",
    'database_type': "Oracle",
    'query_mode': "hybrid",
    # ... other processing data
}

recorded_ids = recorder.record_complete_processing_flow(processing_data)
```

### Recording with Different Modes
```python
from app.ai_training_data_recorder import RecordingMode

# Synchronous recording (default)
result = recorder.record_with_mode(
    operation='record_training_query',
    data=test_data,
    mode=RecordingMode.SYNCHRONOUS
)

# Asynchronous recording
result = recorder.record_with_mode(
    operation='record_training_query',
    data=test_data,
    mode=RecordingMode.ASYNCHRONOUS
)

# Buffered recording
result = recorder.record_with_mode(
    operation='record_training_query',
    data=test_data,
    mode=RecordingMode.BUFFERED
)
```

## Integration with Existing System

The recorder is designed to integrate with the existing hybrid processing system through:

1. **Minimal intrusion** - Recording happens in the background
2. **Error isolation** - Recording failures don't impact user experience
3. **Flexible modes** - Different recording strategies for different data types
4. **Comprehensive coverage** - All processing stages are recorded

## Testing

Run the test scripts to verify functionality:

```bash
# Test basic recording functionality
python backend/test_ai_training_recorder.py

# Demonstrate integration with hybrid processing
python backend/demo_ai_training_integration.py
```

## Monitoring and Maintenance

The system includes built-in health checks and monitoring:

```python
# Check system status
status = recorder.get_system_status()
print(f"Healthy: {status['health']['is_healthy']}")
print(f"Circuit Breaker State: {status['health']['circuit_breaker_state']}")
```

## Future Enhancements

1. **Advanced analytics** on recorded training data
2. **Automated dataset creation** for model fine-tuning
3. **Performance optimization** for high-volume scenarios
4. **Enhanced error recovery** mechanisms
5. **Integration with ML pipeline** for automated model training

## Troubleshooting

Common issues and solutions:

1. **Database connection failures** - Check Oracle connectivity and table permissions
2. **Recording failures** - Check circuit breaker state and logs
3. **Performance issues** - Consider using buffered or asynchronous modes
4. **Data integrity** - Verify foreign key relationships in recorded data

## Contributing

To extend the recording system:

1. Add new recording methods for additional data types
2. Extend the `RecordingContext` with new fields as needed
3. Implement new recording modes or error handling strategies
4. Add new health check metrics
5. Enhance the buffering and retry mechanisms

## License

This system is part of the Oracle SQL Assistant project and follows the same licensing terms.