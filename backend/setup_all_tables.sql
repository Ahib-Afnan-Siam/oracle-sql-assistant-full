-- Main setup script to create all tables in the correct order
-- This script ensures referential integrity by creating referenced tables before referencing tables

-- Enable error handling
SET SERVEROUTPUT ON
SET VERIFY OFF

-- 1. Setup user access tables (referenced by dashboard tables)
PROMPT Creating user access tables...
@setup_user_access_tables.sql
PROMPT User access tables created successfully.

-- 2. Setup dashboard tables (with foreign key constraints to user_access_list)
PROMPT Creating dashboard tables...
@setup_dashboard_tables.sql
PROMPT Dashboard tables created successfully.

-- 3. Verify all tables were created
PROMPT Verifying table creation...
SELECT table_name FROM user_tables 
WHERE table_name IN (
    'USER_ACCESS_REQUEST', 'USER_ACCESS_LIST', 
    'DASHBOARD_CHATS', 'DASHBOARD_MESSAGES', 'DASHBOARD_TOKEN_USAGE', 
    'DASHBOARD_MODEL_STATUS', 'DASHBOARD_FEEDBACK', 'DASHBOARD_SERVER_METRICS',
    'DASHBOARD_ERROR_LOGS', 'DASHBOARD_API_ACTIVITY', 'DASHBOARD_USER_SESSIONS',
    'DASHBOARD_QUERY_HISTORY'
)
ORDER BY table_name;

PROMPT Setup completed successfully.