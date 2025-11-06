# Username Tracking in AI Training Data Recorder

This document explains how username tracking has been implemented in the AI Training Data Recorder system.

## Overview

To track which user is logging in and submitting queries, we've implemented username tracking in the AI training data recorder system. This allows us to associate each query with the user who submitted it, which is valuable for:

1. Usage analytics by user
2. Personalized model improvements
3. Auditing and compliance
4. User-specific query pattern analysis

## Implementation Details

### 1. Database Schema Changes

We've added a `USERNAME` column to the `AI_TRAINING_QUERIES` table:

```sql
ALTER TABLE AI_TRAINING_QUERIES ADD USERNAME VARCHAR2(100);
```

This column stores the username of the logged-in user who submitted each query.

### 2. Code Changes

#### Backend Changes

1. **AI Training Data Recorder**: 
   - Added `username` field to the [RecordingContext](file:///c%3A/Users/MIS/oracle-sql-assistant-full/backend/app/ai_training_data_recorder.py#L58-L69) dataclass
   - Modified [record_training_query](file:///c%3A/Users/MIS/oracle-sql-assistant-full/backend/app/ai_training_data_recorder.py#L255-L300) method to accept and store the username
   - Updated related methods to handle the username parameter

2. **Main Application**:
   - Added [_get_username_from_request](file:///c%3A/Users/MIS/oracle-sql-assistant-full/backend/app/main.py#L561-L582) function to extract username from authentication tokens
   - Modified the chat endpoint to extract username from requests and pass it in metadata

#### Frontend Changes

No frontend changes are required for this implementation. The username tracking is handled entirely on the backend.

### 3. How It Works

1. When a user logs in through the login endpoint, they receive an authentication token
2. When the user makes queries through the chat endpoint, the authentication token is sent in the request headers
3. The backend extracts the username from the authentication token using the [_get_username_from_request](file:///c%3A/Users/MIS/oracle-sql-assistant-full/backend/app/main.py#L561-L582) function
4. The username is passed through the metadata to the [insert_turn](file:///c%3A/Users/MIS/oracle-sql-assistant-full/backend/app/main.py#L120-L138) function
5. The [insert_turn](file:///c%3A/Users/MIS/oracle-sql-assistant-full/backend/app/main.py#L120-L138) function creates a [RecordingContext](file:///c%3A/Users/MIS/oracle-sql-assistant-full/backend/app/ai_training_data_recorder.py#L58-L69) with the username and passes it to the recorder
6. The recorder stores the username in the `AI_TRAINING_QUERIES` table

## Deployment Instructions

### For New Installations

For new installations, simply run the updated setup script:

```sql
@setup_ai_training_tables.sql
```

### For Existing Installations

For existing installations with data, run the upgrade script:

```sql
@upgrade_ai_training_tables.sql
```

This will add the USERNAME column to your existing `AI_TRAINING_QUERIES` table without affecting existing data.

## Future Enhancements

1. **Token Validation**: The current implementation uses a placeholder for username extraction. In a production environment, you should implement proper token validation to extract the actual username from JWT tokens or session stores.

2. **User Session Tracking**: Extend the system to track user sessions for more detailed analytics.

3. **Privacy Controls**: Implement privacy controls to allow users to opt out of tracking if required.

## Testing

To verify the implementation is working:

1. Make a request to the login endpoint to get an authentication token
2. Use that token to make a request to the chat endpoint
3. Check the `AI_TRAINING_QUERIES` table to verify the USERNAME column is populated

```sql
SELECT QUERY_ID, USERNAME, USER_QUERY_TEXT, TIMESTAMP 
FROM AI_TRAINING_QUERIES 
ORDER BY TIMESTAMP DESC;
```

You should see the username populated in the USERNAME column for recent queries.