-- Setup script for Uttoron Admin Dashboard and Monitoring Tables
-- Connect to the appropriate database/schema

-- Drop existing dashboard tables if they exist (for clean setup)
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE dashboard_query_history CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE dashboard_feedback CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE dashboard_token_usage CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE dashboard_model_status CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE dashboard_messages CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE dashboard_chats CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE dashboard_server_metrics CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE dashboard_error_logs CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE dashboard_api_activity CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE dashboard_user_sessions CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

-- Create dashboard_chats table (main chat sessions)
CREATE TABLE dashboard_chats (
    chat_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id VARCHAR2(100) NOT NULL,
    user_id VARCHAR2(100),
    username VARCHAR2(100),
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    duration_seconds NUMBER,
    status VARCHAR2(20) DEFAULT 'active' CHECK (status IN ('active', 'completed', 'abandoned')),
    database_type VARCHAR2(50),
    query_mode VARCHAR2(50)
);

-- Create dashboard_messages table (individual messages within chats)
CREATE TABLE dashboard_messages (
    message_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chat_id NUMBER REFERENCES dashboard_chats(chat_id) ON DELETE CASCADE,
    message_type VARCHAR2(20) CHECK (message_type IN ('user_query', 'ai_response', 'system_message')),
    content CLOB,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processing_time_ms NUMBER,
    tokens_used NUMBER,
    model_name VARCHAR2(100),
    status VARCHAR2(20) DEFAULT 'success' CHECK (status IN ('success', 'error', 'timeout')),
    database_type VARCHAR2(50)
);

-- Create dashboard_token_usage table (token consumption tracking)
CREATE TABLE dashboard_token_usage (
    usage_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chat_id NUMBER REFERENCES dashboard_chats(chat_id) ON DELETE CASCADE,
    message_id NUMBER REFERENCES dashboard_messages(message_id) ON DELETE CASCADE,
    model_type VARCHAR2(10) CHECK (model_type IN ('api', 'local')),
    model_name VARCHAR2(100),
    prompt_tokens NUMBER,
    completion_tokens NUMBER,
    total_tokens NUMBER,
    cost_usd NUMBER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    database_type VARCHAR2(50)
);

-- Create dashboard_model_status table (model availability and performance)
CREATE TABLE dashboard_model_status (
    status_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_type VARCHAR2(10) CHECK (model_type IN ('api', 'local')),
    model_name VARCHAR2(100),
    status VARCHAR2(20) CHECK (status IN ('available', 'unavailable', 'degraded')),
    response_time_ms NUMBER,
    last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error_message CLOB,
    database_type VARCHAR2(50)
);

-- Create dashboard_feedback table (user feedback on responses)
CREATE TABLE dashboard_feedback (
    feedback_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chat_id NUMBER REFERENCES dashboard_chats(chat_id) ON DELETE CASCADE,
    message_id NUMBER REFERENCES dashboard_messages(message_id) ON DELETE CASCADE,
    feedback_type VARCHAR2(20) CHECK (feedback_type IN ('good', 'wrong', 'needs_improvement')),
    feedback_score NUMBER(1,0) CHECK (feedback_score BETWEEN 1 AND 5),
    feedback_comment CLOB,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    database_type VARCHAR2(50)
);

-- Create dashboard_server_metrics table (system performance metrics)
CREATE TABLE dashboard_server_metrics (
    metric_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    metric_name VARCHAR2(100),
    metric_value NUMBER,
    metric_unit VARCHAR2(20),
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    database_type VARCHAR2(50)
);

-- Create dashboard_error_logs table (system error tracking)
CREATE TABLE dashboard_error_logs (
    error_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    error_type VARCHAR2(50),
    error_message CLOB,
    error_details CLOB,
    severity VARCHAR2(10) CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    component VARCHAR2(100),
    user_id VARCHAR2(100),
    chat_id NUMBER REFERENCES dashboard_chats(chat_id) ON DELETE SET NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    database_type VARCHAR2(50)
);

-- Create dashboard_api_activity table (API usage tracking)
CREATE TABLE dashboard_api_activity (
    activity_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    api_endpoint VARCHAR2(200),
    http_method VARCHAR2(10),
    response_status NUMBER,
    response_time_ms NUMBER,
    user_id VARCHAR2(100),
    ip_address VARCHAR2(45),
    user_agent CLOB,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    database_type VARCHAR2(50)
);

-- Create dashboard_user_sessions table (user session tracking)
CREATE TABLE dashboard_user_sessions (
    session_id VARCHAR2(100) PRIMARY KEY,
    user_id VARCHAR2(100),
    username VARCHAR2(100),
    login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    logout_time TIMESTAMP,
    session_duration_seconds NUMBER,
    ip_address VARCHAR2(45),
    user_agent CLOB,
    status VARCHAR2(20) DEFAULT 'active' CHECK (status IN ('active', 'completed', 'expired')),
    database_type VARCHAR2(50)
);

-- Create dashboard_query_history table (combined table for storing final SQL and queries)
CREATE TABLE dashboard_query_history (
    query_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id VARCHAR2(100) REFERENCES user_access_list(user_id) ON DELETE SET NULL,
    session_id VARCHAR2(100),
    user_query CLOB,
    final_sql CLOB,
    execution_status VARCHAR2(20) DEFAULT 'success' CHECK (execution_status IN ('success', 'error', 'timeout')),
    execution_time_ms NUMBER,
    row_count NUMBER,
    database_type VARCHAR2(50),
    query_mode VARCHAR2(50),
    feedback_type VARCHAR2(20) CHECK (feedback_type IN ('good', 'wrong', 'needs_improvement')),
    feedback_comment CLOB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Add foreign key constraints to link user_id fields to user_access_list table
ALTER TABLE dashboard_chats 
ADD CONSTRAINT fk_chats_user_id 
FOREIGN KEY (user_id) REFERENCES user_access_list(user_id) ON DELETE SET NULL;

ALTER TABLE dashboard_error_logs 
ADD CONSTRAINT fk_error_logs_user_id 
FOREIGN KEY (user_id) REFERENCES user_access_list(user_id) ON DELETE SET NULL;

ALTER TABLE dashboard_api_activity 
ADD CONSTRAINT fk_api_activity_user_id 
FOREIGN KEY (user_id) REFERENCES user_access_list(user_id) ON DELETE SET NULL;

ALTER TABLE dashboard_user_sessions 
ADD CONSTRAINT fk_user_sessions_user_id 
FOREIGN KEY (user_id) REFERENCES user_access_list(user_id) ON DELETE SET NULL;

-- Create indexes for better query performance
CREATE INDEX IDX_DASHBOARD_CHATS_SESSION_ID ON dashboard_chats(session_id);
CREATE INDEX IDX_DASHBOARD_CHATS_USER_ID ON dashboard_chats(user_id);
CREATE INDEX IDX_DASHBOARD_CHATS_START_TIME ON dashboard_chats(start_time);
CREATE INDEX IDX_DASHBOARD_CHATS_STATUS ON dashboard_chats(status);

CREATE INDEX IDX_DASHBOARD_MESSAGES_CHAT_ID ON dashboard_messages(chat_id);
CREATE INDEX IDX_DASHBOARD_MESSAGES_TIMESTAMP ON dashboard_messages(timestamp);
CREATE INDEX IDX_DASHBOARD_MESSAGES_TYPE ON dashboard_messages(message_type);

CREATE INDEX IDX_DASHBOARD_TOKEN_USAGE_CHAT_ID ON dashboard_token_usage(chat_id);
CREATE INDEX IDX_DASHBOARD_TOKEN_USAGE_MODEL ON dashboard_token_usage(model_name);
CREATE INDEX IDX_DASHBOARD_TOKEN_USAGE_TIMESTAMP ON dashboard_token_usage(timestamp);

CREATE INDEX IDX_DASHBOARD_MODEL_STATUS_MODEL ON dashboard_model_status(model_name);
CREATE INDEX IDX_DASHBOARD_MODEL_STATUS_CHECKED ON dashboard_model_status(last_checked);

CREATE INDEX IDX_DASHBOARD_FEEDBACK_CHAT_ID ON dashboard_feedback(chat_id);
CREATE INDEX IDX_DASHBOARD_FEEDBACK_TYPE ON dashboard_feedback(feedback_type);
CREATE INDEX IDX_DASHBOARD_FEEDBACK_SUBMITTED ON dashboard_feedback(submitted_at);

CREATE INDEX IDX_DASHBOARD_SERVER_METRICS_NAME ON dashboard_server_metrics(metric_name);
CREATE INDEX IDX_DASHBOARD_SERVER_METRICS_RECORDED ON dashboard_server_metrics(recorded_at);

CREATE INDEX IDX_DASHBOARD_ERROR_LOGS_TYPE ON dashboard_error_logs(error_type);
CREATE INDEX IDX_DASHBOARD_ERROR_LOGS_SEVERITY ON dashboard_error_logs(severity);
CREATE INDEX IDX_DASHBOARD_ERROR_LOGS_TIMESTAMP ON dashboard_error_logs(timestamp);

CREATE INDEX IDX_DASHBOARD_API_ACTIVITY_ENDPOINT ON dashboard_api_activity(api_endpoint);
CREATE INDEX IDX_DASHBOARD_API_ACTIVITY_TIMESTAMP ON dashboard_api_activity(timestamp);
CREATE INDEX IDX_DASHBOARD_API_ACTIVITY_USER_ID ON dashboard_api_activity(user_id);

CREATE INDEX IDX_DASHBOARD_USER_SESSIONS_USER_ID ON dashboard_user_sessions(user_id);
CREATE INDEX IDX_DASHBOARD_USER_SESSIONS_LOGIN ON dashboard_user_sessions(login_time);
CREATE INDEX IDX_DASHBOARD_USER_SESSIONS_STATUS ON dashboard_user_sessions(status);

-- Create indexes for the new query history table
CREATE INDEX IDX_DASHBOARD_QUERY_HISTORY_USER_ID ON dashboard_query_history(user_id);
CREATE INDEX IDX_DASHBOARD_QUERY_HISTORY_SESSION_ID ON dashboard_query_history(session_id);
CREATE INDEX IDX_DASHBOARD_QUERY_HISTORY_CREATED_AT ON dashboard_query_history(created_at);
CREATE INDEX IDX_DASHBOARD_QUERY_HISTORY_STATUS ON dashboard_query_history(execution_status);
CREATE INDEX IDX_DASHBOARD_QUERY_HISTORY_FEEDBACK ON dashboard_query_history(feedback_type);

-- Verify tables were created
SELECT table_name FROM user_tables WHERE table_name LIKE 'DASHBOARD_%' ORDER BY table_name;