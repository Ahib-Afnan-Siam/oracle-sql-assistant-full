# app/user_access.py
"""
User Access Control System for Oracle SQL Assistant
This module handles user registration, access requests, and authentication.
"""

import cx_Oracle
import logging
from typing import Dict, List, Optional, Tuple
from app.db_connector import _get_connection_pool
from app.config import FEEDBACK_DB_ID

logger = logging.getLogger(__name__)

# Use the feedback database for user access tables
USER_ACCESS_DB_ID = FEEDBACK_DB_ID

def get_db_connection():
    """Get a database connection from the pool."""
    pool = _get_connection_pool(USER_ACCESS_DB_ID)
    return pool.acquire()

def release_db_connection(conn):
    """Release a database connection back to the pool."""
    pool = _get_connection_pool(USER_ACCESS_DB_ID)
    pool.release(conn)

def create_user_access_request(user_data: Dict) -> bool:
    """
    Create a new user access request in the user_access_request table.
    
    Args:
        user_data: Dictionary containing user information
            - user_id: Employee ID
            - full_name: Full name of the user
            - email: Email address
            - designation: Job designation (optional)
            - department: Department name (optional)
    
    Returns:
        bool: True if successful, False otherwise
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Insert the user access request
        query = """
            INSERT INTO user_access_request 
            (user_id, full_name, email, designation, department, status)
            VALUES (:user_id, :full_name, :email, :designation, :department, 'pending')
        """
        
        cursor.execute(query, {
            'user_id': user_data['user_id'],
            'full_name': user_data['full_name'],
            'email': user_data['email'],
            'designation': user_data.get('designation', ''),
            'department': user_data.get('department', '')
        })
        
        conn.commit()
        cursor.close()
        return True
        
    except cx_Oracle.Error as e:
        logger.error(f"Database error creating user access request: {e}")
        return False
    except Exception as e:
        logger.error(f"Error creating user access request: {e}")
        return False
    finally:
        if conn:
            release_db_connection(conn)

def get_pending_access_requests() -> List[Dict]:
    """
    Get all pending user access requests.
    
    Returns:
        List[Dict]: List of pending access requests
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT id, user_id, full_name, email, designation, department, created_at
            FROM user_access_request
            WHERE status = 'pending'
            ORDER BY created_at DESC
        """
        
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        requests = []
        for row in rows:
            request_dict = dict(zip(columns, row))
            requests.append(request_dict)
        
        cursor.close()
        return requests
        
    except cx_Oracle.Error as e:
        logger.error(f"Database error fetching pending access requests: {e}")
        return []
    except Exception as e:
        logger.error(f"Error fetching pending access requests: {e}")
        return []
    finally:
        if conn:
            release_db_connection(conn)

def approve_user_access(request_id: int, added_by_admin: bool = False) -> bool:
    """
    Approve a user access request and move the user to the access list.
    
    Args:
        request_id: ID of the access request to approve
        added_by_admin: Whether the user was added directly by admin
    
    Returns:
        bool: True if successful, False otherwise
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # First, get the request details
        query = """
            SELECT user_id, full_name, email, designation, department
            FROM user_access_request
            WHERE id = :request_id
        """
        
        cursor.execute(query, {'request_id': request_id})
        row = cursor.fetchone()
        
        if not row:
            logger.error(f"Access request with ID {request_id} not found")
            return False
        
        user_id, full_name, email, designation, department = row
        
        # Insert into user_access_list with status = 'Y' by default
        insert_query = """
            INSERT INTO user_access_list 
            (user_id, full_name, email, designation, department, added_by_admin, status)
            VALUES (:user_id, :full_name, :email, :designation, :department, :added_by_admin, 'Y')
        """
        
        cursor.execute(insert_query, {
            'user_id': user_id,
            'full_name': full_name,
            'email': email,
            'designation': designation,
            'department': department,
            'added_by_admin': 1 if added_by_admin else 0
        })
        
        # Update the request status
        update_query = """
            UPDATE user_access_request
            SET status = 'approved'
            WHERE id = :request_id
        """
        
        cursor.execute(update_query, {'request_id': request_id})
        
        conn.commit()
        cursor.close()
        return True
        
    except cx_Oracle.IntegrityError as e:
        logger.error(f"User already exists in access list: {e}")
        return False
    except cx_Oracle.Error as e:
        logger.error(f"Database error approving user access: {e}")
        return False
    except Exception as e:
        logger.error(f"Error approving user access: {e}")
        return False
    finally:
        if conn:
            release_db_connection(conn)

def deny_user_access(request_id: int) -> bool:
    """
    Deny a user access request.
    
    Args:
        request_id: ID of the access request to deny
    
    Returns:
        bool: True if successful, False otherwise
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            UPDATE user_access_request
            SET status = 'denied'
            WHERE id = :request_id
        """
        
        cursor.execute(query, {'request_id': request_id})
        conn.commit()
        cursor.close()
        return True
        
    except cx_Oracle.Error as e:
        logger.error(f"Database error denying user access: {e}")
        return False
    except Exception as e:
        logger.error(f"Error denying user access: {e}")
        return False
    finally:
        if conn:
            release_db_connection(conn)

def add_user_directly(user_data: Dict) -> bool:
    """
    Add a user directly to the access list (admin action).
    
    Args:
        user_data: Dictionary containing user information
            - user_id: Employee ID
            - full_name: Full name of the user
            - email: Email address
            - designation: Job designation (optional)
            - department: Department name (optional)
    
    Returns:
        bool: True if successful, False otherwise
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            INSERT INTO user_access_list 
            (user_id, full_name, email, designation, department, added_by_admin, status)
            VALUES (:user_id, :full_name, :email, :designation, :department, 1, 'Y')
        """
        
        cursor.execute(query, {
            'user_id': user_data['user_id'],
            'full_name': user_data['full_name'],
            'email': user_data['email'],
            'designation': user_data.get('designation', ''),
            'department': user_data.get('department', '')
        })
        
        conn.commit()
        cursor.close()
        return True
        
    except cx_Oracle.IntegrityError as e:
        logger.error(f"User already exists in access list: {e}")
        return False
    except cx_Oracle.Error as e:
        logger.error(f"Database error adding user directly: {e}")
        return False
    except Exception as e:
        logger.error(f"Error adding user directly: {e}")
        return False
    finally:
        if conn:
            release_db_connection(conn)

def is_user_authorized(user_id: str) -> bool:
    """
    Check if a user is authorized to access the system and has active status.
    
    Args:
        user_id: Employee ID to check
    
    Returns:
        bool: True if user is authorized and active, False otherwise
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT COUNT(*) 
            FROM user_access_list 
            WHERE user_id = :user_id AND status = 'Y'
        """
        
        cursor.execute(query, {'user_id': user_id})
        count = cursor.fetchone()[0]
        cursor.close()
        return count > 0
        
    except cx_Oracle.Error as e:
        logger.error(f"Database error checking user authorization: {e}")
        return False
    except Exception as e:
        logger.error(f"Error checking user authorization: {e}")
        return False
    finally:
        if conn:
            release_db_connection(conn)

def get_authorized_users() -> List[Dict]:
    """
    Get all authorized users.
    
    Returns:
        List[Dict]: List of authorized users
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT id, user_id, full_name, email, designation, department, added_by_admin, status, created_at
            FROM user_access_list
            ORDER BY created_at DESC
        """
        
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        
        # Convert to list of dictionaries
        users = []
        for row in rows:
            user_dict = dict(zip(columns, row))
            users.append(user_dict)
        
        cursor.close()
        return users
        
    except cx_Oracle.Error as e:
        logger.error(f"Database error fetching authorized users: {e}")
        return []
    except Exception as e:
        logger.error(f"Error fetching authorized users: {e}")
        return []
    finally:
        if conn:
            release_db_connection(conn)

def disable_user_access(user_id: str) -> bool:
    """
    Disable a user's access by setting status to 'N'.
    
    Args:
        user_id: Employee ID of the user to disable
    
    Returns:
        bool: True if successful, False otherwise
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            UPDATE user_access_list
            SET status = 'N'
            WHERE user_id = :user_id
        """
        
        cursor.execute(query, {'user_id': user_id})
        rows_affected = cursor.rowcount
        conn.commit()
        cursor.close()
        
        return rows_affected > 0
        
    except cx_Oracle.Error as e:
        logger.error(f"Database error disabling user access: {e}")
        return False
    except Exception as e:
        logger.error(f"Error disabling user access: {e}")
        return False
    finally:
        if conn:
            release_db_connection(conn)

def enable_user_access(user_id: str) -> bool:
    """
    Enable a user's access by setting status to 'Y'.
    
    Args:
        user_id: Employee ID of the user to enable
    
    Returns:
        bool: True if successful, False otherwise
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            UPDATE user_access_list
            SET status = 'Y'
            WHERE user_id = :user_id
        """
        
        cursor.execute(query, {'user_id': user_id})
        rows_affected = cursor.rowcount
        conn.commit()
        cursor.close()
        
        return rows_affected > 0
        
    except cx_Oracle.Error as e:
        logger.error(f"Database error enabling user access: {e}")
        return False
    except Exception as e:
        logger.error(f"Error enabling user access: {e}")
        return False
    finally:
        if conn:
            release_db_connection(conn)

def get_user_statistics() -> Dict[str, int]:
    """
    Get user statistics including total users and active users.
    
    Returns:
        Dict[str, int]: Dictionary containing total_users and active_users counts
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get total users count
        total_query = """
            SELECT COUNT(*) 
            FROM user_access_list
        """
        
        cursor.execute(total_query)
        total_users = cursor.fetchone()[0]
        
        # Get active users count
        active_query = """
            SELECT COUNT(*) 
            FROM user_access_list
            WHERE status = 'Y'
        """
        
        cursor.execute(active_query)
        active_users = cursor.fetchone()[0]
        
        cursor.close()
        
        return {
            "total_users": total_users,
            "active_users": active_users
        }
        
    except cx_Oracle.Error as e:
        logger.error(f"Database error fetching user statistics: {e}")
        return {
            "total_users": 0,
            "active_users": 0
        }
    except Exception as e:
        logger.error(f"Error fetching user statistics: {e}")
        return {
            "total_users": 0,
            "active_users": 0
        }
    finally:
        if conn:
            release_db_connection(conn)

def is_user_admin(user_id: str) -> bool:
    """
    Check if a user has admin access.
    
    Args:
        user_id: Employee ID to check
        
    Returns:
        bool: True if user has admin access, False otherwise
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT COUNT(*) 
            FROM user_access_list 
            WHERE user_id = :user_id AND admin_access = 'Y' AND status = 'Y'
        """
        
        cursor.execute(query, {'user_id': user_id})
        count = cursor.fetchone()[0]
        cursor.close()
        return count > 0
        
    except cx_Oracle.Error as e:
        logger.error(f"Database error checking user admin access: {e}")
        return False
    except Exception as e:
        logger.error(f"Error checking user admin access: {e}")
        return False
    finally:
        if conn:
            release_db_connection(conn)


def grant_admin_access(user_id: str) -> bool:
    """
    Grant admin access to a user.
    
    Args:
        user_id: Employee ID to grant admin access to
        
    Returns:
        bool: True if successful, False otherwise
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            UPDATE user_access_list
            SET admin_access = 'Y'
            WHERE user_id = :user_id AND status = 'Y'
        """
        
        cursor.execute(query, {'user_id': user_id})
        rows_affected = cursor.rowcount
        conn.commit()
        cursor.close()
        
        return rows_affected > 0
        
    except cx_Oracle.Error as e:
        logger.error(f"Database error granting admin access: {e}")
        return False
    except Exception as e:
        logger.error(f"Error granting admin access: {e}")
        return False
    finally:
        if conn:
            release_db_connection(conn)


def revoke_admin_access(user_id: str) -> bool:
    """
    Revoke admin access from a user.
    
    Args:
        user_id: Employee ID to revoke admin access from
        
    Returns:
        bool: True if successful, False otherwise
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            UPDATE user_access_list
            SET admin_access = 'N'
            WHERE user_id = :user_id AND status = 'Y'
        """
        
        cursor.execute(query, {'user_id': user_id})
        rows_affected = cursor.rowcount
        conn.commit()
        cursor.close()
        
        return rows_affected > 0
        
    except cx_Oracle.Error as e:
        logger.error(f"Database error revoking admin access: {e}")
        return False
    except Exception as e:
        logger.error(f"Error revoking admin access: {e}")
        return False
    finally:
        if conn:
            release_db_connection(conn)
