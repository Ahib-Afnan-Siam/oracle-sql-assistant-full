"""
Service module for dashboard_feedback table operations.
"""
import logging
from typing import Any, Dict, List, Optional
from .base_service import BaseService

logger = logging.getLogger(__name__)

class FeedbackService(BaseService):
    """Service class for feedback-related database operations."""
    
    def create_feedback(self, chat_id: int, message_id: int, feedback_type: str,
                       feedback_score: int, feedback_comment: Optional[str] = None,
                       database_type: Optional[str] = None) -> Optional[int]:
        """
        Create a new feedback record.
        
        Args:
            chat_id: Chat identifier
            message_id: Message identifier
            feedback_type: Type of feedback (good, wrong, needs_improvement)
            feedback_score: Feedback score (1-5)
            feedback_comment: Feedback comment
            database_type: Database type (optional)
            
        Returns:
            Feedback ID of the newly created record or None
        """
        # Try to insert with full foreign key constraints first
        insert_query = """
            INSERT INTO dashboard_feedback 
            (chat_id, message_id, feedback_type, feedback_score, feedback_comment, submitted_at, database_type)
            VALUES (:chat_id, :message_id, :feedback_type, :feedback_score, :feedback_comment, CURRENT_TIMESTAMP, :database_type)
        """
        
        params = {
            "chat_id": chat_id,
            "message_id": message_id,
            "feedback_type": feedback_type,
            "feedback_score": feedback_score,
            "feedback_comment": feedback_comment,
            "database_type": database_type
        }
        
        try:
            self._execute_non_query(insert_query, params)
        except Exception as e:
            # If foreign key constraint violation, try inserting with chat_id and NULL message_id
            # but always preserve the chat_id relationship
            if "ORA-02291" in str(e):  # Foreign key constraint violation
                logger.warning(f"Foreign key constraint violation for chat_id={chat_id}, message_id={message_id}. Recording feedback with chat_id and NULL message_id.")
                try:
                    insert_query = """
                        INSERT INTO dashboard_feedback 
                        (chat_id, message_id, feedback_type, feedback_score, feedback_comment, submitted_at, database_type)
                        VALUES (:chat_id, NULL, :feedback_type, :feedback_score, :feedback_comment, CURRENT_TIMESTAMP, :database_type)
                    """
                    # Use only the parameters needed for this query, with message_id set to NULL
                    chat_params = {
                        "chat_id": chat_id,
                        "feedback_type": feedback_type,
                        "feedback_score": feedback_score,
                        "feedback_comment": feedback_comment,
                        "database_type": database_type
                    }
                    self._execute_non_query(insert_query, chat_params)
                except Exception as e2:
                    logger.error(f"Error inserting feedback with chat_id and NULL message_id: {str(e2)}")
                    return None
            else:
                logger.error(f"Error inserting feedback with full constraints: {str(e)}")
                return None
        
        # Get the ID of the newly inserted record
        # Use ROWNUM to get the most recently inserted record
        select_query = """
            SELECT feedback_id FROM (
                SELECT feedback_id FROM dashboard_feedback 
                ORDER BY submitted_at DESC, feedback_id DESC
            ) WHERE ROWNUM = 1
        """
        
        try:
            result = self._execute_query(select_query)
            return result[0]["feedback_id"] if result and len(result) > 0 and "feedback_id" in result[0] else None
        except Exception as e:
            logger.error(f"Error getting feedback ID: {str(e)}")
            return None
    
    def get_feedback_by_chat(self, chat_id: int) -> List[Dict[str, Any]]:
        """
        Get feedback records for a chat.
        
        Args:
            chat_id: Chat identifier
            
        Returns:
            List of feedback records
        """
        query = """
            SELECT feedback_id, chat_id, message_id, feedback_type, feedback_score, 
                   feedback_comment, submitted_at
            FROM dashboard_feedback 
            WHERE chat_id = :chat_id
            ORDER BY submitted_at DESC
        """
        
        return self._execute_query(query, {"chat_id": chat_id})
    
    def get_feedback_statistics(self) -> Dict[str, Any]:
        """
        Get feedback statistics.
        
        Returns:
            Dictionary with feedback statistics
        """
        query = """
            SELECT 
                COUNT(*) as total_feedback,
                COUNT(CASE WHEN feedback_type = 'good' THEN 1 END) as good_feedback,
                COUNT(CASE WHEN feedback_type = 'wrong' THEN 1 END) as wrong_feedback,
                COUNT(CASE WHEN feedback_type = 'needs_improvement' THEN 1 END) as needs_improvement_feedback,
                AVG(feedback_score) as avg_feedback_score
            FROM dashboard_feedback
        """
        
        result = self._execute_query(query)
        return result[0] if result and len(result) > 0 else {}
    
    def get_feedback_by_type(self) -> List[Dict[str, Any]]:
        """
        Get feedback aggregated by type.
        
        Returns:
            List of feedback statistics by type
        """
        query = """
            SELECT 
                feedback_type,
                COUNT(*) as count,
                AVG(feedback_score) as avg_score
            FROM dashboard_feedback
            GROUP BY feedback_type
            ORDER BY count DESC
        """
        
        return self._execute_query(query)