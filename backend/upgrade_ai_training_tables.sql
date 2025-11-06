-- Upgrade script for AI Training Data Tables
-- This script adds the USERNAME column to existing AI_TRAINING_QUERIES table

-- Add USERNAME column to AI_TRAINING_QUERIES table
ALTER TABLE AI_TRAINING_QUERIES ADD USERNAME VARCHAR2(100);

-- Add a comment to describe the new column
COMMENT ON COLUMN AI_TRAINING_QUERIES.USERNAME IS 'Username of the logged-in user who submitted the query';

-- Verify the column was added
SELECT column_name, data_type, data_length 
FROM user_tab_columns 
WHERE table_name = 'AI_TRAINING_QUERIES' AND column_name = 'USERNAME';