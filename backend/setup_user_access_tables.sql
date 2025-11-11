-- Setup script for User Access Control Tables
-- Connect to the appropriate database/schema

-- Drop existing user access tables if they exist (for clean setup)
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE user_access_list CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE user_access_request CASCADE CONSTRAINTS';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF;
END;
/

-- Create user_access_request table (for pending access requests)
CREATE TABLE user_access_request (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id VARCHAR2(100) NOT NULL,
    full_name VARCHAR2(200) NOT NULL,
    email VARCHAR2(200) NOT NULL,
    designation VARCHAR2(200),
    department VARCHAR2(200),
    status VARCHAR2(20) DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create user_access_list table (for approved users)
CREATE TABLE user_access_list (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id VARCHAR2(100) NOT NULL UNIQUE,
    full_name VARCHAR2(200) NOT NULL,
    email VARCHAR2(200) NOT NULL,
    designation VARCHAR2(200),
    department VARCHAR2(200),
    status CHAR(1) DEFAULT 'Y' CHECK (status IN ('Y', 'N')),
    added_by_admin NUMBER(1) DEFAULT 0 CHECK (added_by_admin IN (0, 1)),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better query performance
CREATE INDEX IDX_USER_ACCESS_REQUEST_USER_ID ON user_access_request(user_id);
CREATE INDEX IDX_USER_ACCESS_REQUEST_STATUS ON user_access_request(status);
CREATE INDEX IDX_USER_ACCESS_LIST_USER_ID ON user_access_list(user_id);
CREATE INDEX IDX_USER_ACCESS_LIST_STATUS ON user_access_list(status);
-- Note: user_id in user_access_list is already indexed as it's a PRIMARY KEY

-- Verify tables were created
SELECT table_name FROM user_tables WHERE table_name IN ('USER_ACCESS_REQUEST', 'USER_ACCESS_LIST') ORDER BY table_name;