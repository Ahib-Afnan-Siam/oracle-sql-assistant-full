# AI Training Data Recorder - Deployment Instructions

## Overview

This document provides instructions for deploying the new AI Training Data Recorder system with the correct database schema.

## Current Status

We have successfully implemented:

1. **Complete AI Training Data Recorder** - [app/ai_training_data_recorder.py](file://c:\Users\MIS\oracle-sql-assistant-full\backend\app\ai_training_data_recorder.py)
2. **New Database Schema** - [setup_ai_training_tables.sql](file://c:\Users\MIS\oracle-sql-assistant-full\backend\setup_ai_training_tables.sql)
3. **Test Scripts** - [test_ai_training_recorder.py](file://c:\Users\MIS\oracle-sql-assistant-full\backend\test_ai_training_recorder.py)
4. **Integration Demo** - [demo_ai_training_integration.py](file://c:\Users\MIS\oracle-sql-assistant-full\backend\demo_ai_training_integration.py)
5. **Mock Database Tests** - [test_ai_recorder_with_mock_db.py](file://c:\Users\MIS\oracle-sql-assistant-full\backend\test_ai_recorder_with_mock_db.py)

## Deployment Steps

### 1. Deploy the New Database Schema

Connect to your Oracle database and run the new schema setup:

```sql
-- Using SQL*Plus
sqlplus username/password@database @setup_ai_training_tables.sql

-- Or using any Oracle client
@setup_ai_training_tables.sql
```

This will:
- Drop any existing AI training tables (if they exist)
- Create 9 new tables with the correct schema:
  - `AI_TRAINING_QUERIES`
  - `AI_QUERY_CLASSIFICATIONS`
  - `AI_SCHEMA_CONTEXTS`
  - `AI_MODEL_INTERACTIONS`
  - `AI_RESPONSE_SELECTIONS`
  - `AI_SQL_PROCESSING`
  - `AI_EXECUTION_RESULTS`
  - `AI_FALLBACK_EVENTS`
  - `AI_USER_FEEDBACK`

### 2. Verify Schema Deployment

After running the schema setup, verify that all tables were created correctly:

```sql
-- Check that all tables exist
SELECT table_name FROM user_tables WHERE table_name LIKE 'AI_%' ORDER BY table_name;

-- Verify column structure for key tables
DESCRIBE AI_TRAINING_QUERIES;
DESCRIBE AI_QUERY_CLASSIFICATIONS;
DESCRIBE AI_MODEL_INTERACTIONS;
```

### 3. Update Database Connection (if needed)

Ensure your database connection in [app/db_connector.py](file://c:\Users\MIS\oracle-sql-assistant-full\backend\app\db_connector.py) points to the correct database where you deployed the new schema.

### 4. Run Verification Tests

After deploying the schema, run the verification tests:

```bash
# Test basic functionality
python test_ai_training_recorder.py

# Test with mock database (no database connection needed)
python test_ai_recorder_with_mock_db.py

# Test integration
python demo_ai_training_integration.py
```

## Key Features of the New Schema

### Table Relationships
All tables are properly linked with foreign key relationships to [AI_TRAINING_QUERIES](file://c:\Users\MIS\oracle-sql-assistant-full\backend\setup_training_tables.sql#L105-L113).QUERY_ID:

```
AI_TRAINING_QUERIES (QUERY_ID - Primary Key)
├── AI_QUERY_CLASSIFICATIONS (QUERY_ID - Foreign Key)
├── AI_SCHEMA_CONTEXTS (QUERY_ID - Foreign Key)
├── AI_MODEL_INTERACTIONS (QUERY_ID - Foreign Key)
├── AI_RESPONSE_SELECTIONS (QUERY_ID - Foreign Key)
├── AI_SQL_PROCESSING (QUERY_ID - Foreign Key)
├── AI_EXECUTION_RESULTS (QUERY_ID - Foreign Key)
├── AI_FALLBACK_EVENTS (QUERY_ID - Foreign Key)
└── AI_USER_FEEDBACK (QUERY_ID - Foreign Key)
```

### Column Names Fixed
All column names have been corrected to match Oracle naming conventions and avoid reserved keywords:

- `BUSINESS_CONTEXT` instead of `business_context`
- `CONTEXT_ID` instead of `context_id`
- `COST_USD` instead of `cost_usd`
- `FINAL_RESPONSE_TEXT` instead of `final_response_text`
- `PROCESSING_ID` instead of `processing_id`
- `RESULT_ID` instead of `result_id`
- `SUBMISSION_TIMESTAMP` instead of `submission_timestamp`

## Integration with Existing System

To integrate with your existing hybrid processing system:

1. **Import the recorder**:
   ```python
   from app.ai_training_data_recorder import AITrainingDataRecorder, RecordingContext
   ```

2. **Initialize the recorder**:
   ```python
   recorder = AITrainingDataRecorder()
   ```

3. **Record at each processing stage**:
   ```python
   # At query receipt
   context = RecordingContext(session_id="session_123", database_type="Oracle")
   query_id = recorder.record_training_query("Show production efficiency", context)
   
   # After classification
   recorder.record_query_classification(query_id, classification_result)
   
   # After schema retrieval
   recorder.record_schema_context(query_id, schema_info)
   
   # After model processing
   recorder.record_model_interaction(query_id, "api", api_response_details)
   recorder.record_model_interaction(query_id, "local", local_response_details)
   
   # After selection
   recorder.record_response_selection(query_id, selection_details)
   
   # After SQL processing
   recorder.record_sql_processing(query_id, processing_details)
   
   # After execution
   recorder.record_execution_result(query_id, execution_details)
   
   # After fallback (if triggered)
   recorder.record_fallback_event(query_id, fallback_details)
   
   # After user feedback (when received)
   recorder.record_user_feedback(query_id, feedback_details)
   ```

## Troubleshooting

### Common Issues

1. **ORA-00904: Invalid Identifier**
   - Cause: Using old schema with incorrect column names
   - Solution: Deploy the new schema from [setup_ai_training_tables.sql](file://c:\Users\MIS\oracle-sql-assistant-full\backend\setup_ai_training_tables.sql)

2. **Foreign Key Constraint Violations**
   - Cause: Referencing non-existent QUERY_ID
   - Solution: Ensure [AI_TRAINING_QUERIES](file://c:\Users\MIS\oracle-sql-assistant-full\backend\setup_training_tables.sql#L105-L113) record is created before other records

3. **Connection Issues**
   - Cause: Incorrect database credentials or connection string
   - Solution: Verify database connection in [app/db_connector.py](file://c:\Users\MIS\oracle-sql-assistant-full\backend\app\db_connector.py)

### Testing Without Database

Use the mock database test to verify functionality without a database connection:

```bash
python test_ai_recorder_with_mock_db.py
```

## Benefits of the New System

1. **Complete Data Coverage** - Records every aspect of the SQL generation process
2. **Robust Error Handling** - Circuit breaker, retry logic, and graceful degradation
3. **Flexible Recording** - Synchronous, asynchronous, and buffered recording modes
4. **Performance Optimized** - Minimal impact on user experience
5. **Training Data Ready** - Structured data for model training and improvement
6. **Easy Integration** - Drop-in replacement for existing recording systems

## Next Steps

1. Deploy the new schema to your database
2. Run verification tests
3. Integrate with your existing hybrid processing system
4. Monitor for any issues and adjust as needed
5. Begin collecting training data for local model improvement

## Support

For any issues with deployment or integration, refer to:
- [README_AI_TRAINING_RECORDER.md](file://c:\Users\MIS\oracle-sql-assistant-full\backend\README_AI_TRAINING_RECORDER.md) - Complete documentation
- [AI_TRAINING_SYSTEM_SUMMARY.md](file://c:\Users\MIS\oracle-sql-assistant-full\backend\AI_TRAINING_SYSTEM_SUMMARY.md) - Implementation summary
- [verify_ai_training_setup.py](file://c:\Users\MIS\oracle-sql-assistant-full\backend\verify_ai_training_setup.py) - Setup verification script