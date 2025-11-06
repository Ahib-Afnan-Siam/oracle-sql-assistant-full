-- SQL script to verify username recording in AI_TRAINING_QUERIES table

-- Check if USERNAME column exists
SELECT column_name, data_type, data_length 
FROM user_tab_columns 
WHERE table_name = 'AI_TRAINING_QUERIES' 
AND column_name = 'USERNAME';

-- Check recent queries with usernames
SELECT QUERY_ID, USERNAME, USER_QUERY_TEXT, TIMESTAMP
FROM AI_TRAINING_QUERIES 
WHERE USERNAME IS NOT NULL 
ORDER BY TIMESTAMP DESC 
FETCH FIRST 10 ROWS ONLY;

-- Count total queries with usernames
SELECT COUNT(*) as queries_with_usernames
FROM AI_TRAINING_QUERIES 
WHERE USERNAME IS NOT NULL;

-- Show distribution of usernames
SELECT USERNAME, COUNT(*) as query_count
FROM AI_TRAINING_QUERIES 
WHERE USERNAME IS NOT NULL
GROUP BY USERNAME
ORDER BY query_count DESC;