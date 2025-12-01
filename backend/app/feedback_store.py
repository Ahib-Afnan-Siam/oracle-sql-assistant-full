"""
Feedback store module with dummy implementations for backward compatibility.
This module provides the functions that main.py expects to import.
"""
import logging

logger = logging.getLogger(__name__)

def insert_turn(source_db_id, client_ip, user_question, schema_context_text=None, schema_context_ids=None, meta=None):
    """
    Dummy implementation of insert_turn for backward compatibility.
    """
    logger.debug("insert_turn called with source_db_id=%s, user_question=%s", source_db_id, user_question)
    return 1  # Return a dummy turn_id

def insert_sql_sample(turn_id, model_name, prompt_text=None, sql_text=None, display_mode=None):
    """
    Dummy implementation of insert_sql_sample for backward compatibility.
    """
    logger.debug("insert_sql_sample called with turn_id=%s, model_name=%s", turn_id, model_name)
    return 1  # Return a dummy sql_sample_id

def update_sql_sample(sql_sample_id, **cols):
    """
    Dummy implementation of update_sql_sample for backward compatibility.
    """
    logger.debug("update_sql_sample called with sql_sample_id=%s", sql_sample_id)
    pass

def insert_summary_sample(turn_id, model_name, prompt_text=None, data_snapshot=None, sql_used=None, display_mode=None):
    """
    Dummy implementation of insert_summary_sample for backward compatibility.
    """
    logger.debug("insert_summary_sample called with turn_id=%s, model_name=%s", turn_id, model_name)
    return 1  # Return a dummy summary_sample_id

def update_summary_sample(summary_sample_id, **cols):
    """
    Dummy implementation of update_summary_sample for backward compatibility.
    """
    logger.debug("update_summary_sample called with summary_sample_id=%s", summary_sample_id)
    pass

def insert_feedback(**kwargs):
    """
    Dummy implementation of insert_feedback for backward compatibility.
    """
    logger.debug("insert_feedback called with kwargs=%s", kwargs)
    return 1  # Return a dummy feedback_id