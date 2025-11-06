# backend/app/utils.py
"""
Utility functions for the AI training data recorder.
"""

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

def _json_dumps(obj: Any) -> str:
    """
    Serialize object to JSON string.
    
    Args:
        obj: Object to serialize
        
    Returns:
        JSON string representation of the object
    """
    try:
        return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    except Exception as e:
        logger.warning(f"Failed to serialize object to JSON: {e}")
        return "{}"

def _insert_with_returning(cursor, sql: str, params: Dict[str, Any]) -> int:
    """
    Execute INSERT statement with RETURNING clause and return the generated ID.
    
    Args:
        cursor: Database cursor
        sql: SQL INSERT statement with RETURNING clause
        params: Parameters for the SQL statement
        
    Returns:
        Generated ID from the RETURNING clause
    """
    # Create a variable to hold the returned ID
    new_id = cursor.var(int)
    
    # Add the new_id variable to the parameters
    params_with_return = params.copy()
    params_with_return['new_id'] = new_id
    
    # Execute the statement
    cursor.execute(sql, params_with_return)
    
    # Get the returned ID
    returned_id = new_id.getvalue()
    
    # Handle different return types
    if isinstance(returned_id, list):
        return returned_id[0] if returned_id else 0
    elif isinstance(returned_id, (int, float)):
        return int(returned_id)
    else:
        return 0