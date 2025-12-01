"""
Service module for dashboard_messages table operations.
"""
import logging
from typing import Any, Dict, List, Optional
from .base_service import BaseService

logger = logging.getLogger(__name__)

class MessagesService(BaseService):
    """Service class for message-related database operations."""
    
    def create_message(self, chat_id: int, message_type: str, content: str,
                      processing_time_ms: Optional[int] = None, tokens_used: Optional[int] = None,
                      model_name: Optional[str] = None, status: str = 'success',
                      database_type: Optional[str] = None) -> Optional[int]:
        """
        Create a new message.
        
        Args:
            chat_id: Chat identifier
            message_type: Type of message (user_query, ai_response, system_message)
            content: Message content
            processing_time_ms: Processing time in milliseconds
            tokens_used: Number of tokens used
            model_name: Model name
            status: Message status
            database_type: Database type
            
        Returns:
            Message ID of the newly created message or None
        """
        insert_query = """
            INSERT INTO dashboard_messages 
            (chat_id, message_type, content, processing_time_ms, tokens_used, model_name, status, timestamp, database_type)
            VALUES (:chat_id, :message_type, :content, :processing_time_ms, :tokens_used, :model_name, :status, CURRENT_TIMESTAMP, :database_type)
        """
        
        params = {
            "chat_id": chat_id,
            "message_type": message_type,
            "content": content,
            "processing_time_ms": processing_time_ms,
            "tokens_used": tokens_used,
            "model_name": model_name,
            "status": status,
            "database_type": database_type
        }
        
        self._execute_non_query(insert_query, params)
        
        # Get the ID of the newly inserted message
        # Use ROWNUM to get the most recently inserted record for this chat
        select_query = """
            SELECT message_id FROM (
                SELECT message_id FROM dashboard_messages 
                WHERE chat_id = :chat_id 
                ORDER BY timestamp DESC, message_id DESC
            ) WHERE ROWNUM = 1
        """
        
        result = self._execute_query(select_query, {"chat_id": chat_id})
        return result[0]["message_id"] if result and len(result) > 0 and "message_id" in result[0] else None
    
    def get_messages_by_chat(self, chat_id: int) -> List[Dict[str, Any]]:
        """
        Get all messages for a chat.
        
        Args:
            chat_id: Chat identifier
            
        Returns:
            List of message details
        """
        query = """
            SELECT message_id, chat_id, message_type, content, timestamp, 
                   processing_time_ms, tokens_used, model_name, status, database_type
            FROM dashboard_messages 
            WHERE chat_id = :chat_id
            ORDER BY timestamp ASC
        """
        
        return self._execute_query(query, {"chat_id": chat_id})
    
    def get_message_by_id(self, message_id: int) -> Optional[Dict[str, Any]]:
        """
        Get message details by ID.
        
        Args:
            message_id: Message identifier
            
        Returns:
            Message details or None if not found
        """
        query = """
            SELECT message_id, chat_id, message_type, content, timestamp, 
                   processing_time_ms, tokens_used, model_name, status, database_type
            FROM dashboard_messages 
            WHERE message_id = :message_id
        """
        
        result = self._execute_query(query, {"message_id": message_id})
        return result[0] if result and len(result) > 0 else None
    
    def update_message_status(self, message_id: int, status: str, 
                             processing_time_ms: Optional[int] = None) -> bool:
        """
        Update message status and processing time.
        
        Args:
            message_id: Message identifier
            status: New status
            processing_time_ms: Processing time in milliseconds
            
        Returns:
            True if successful, False otherwise
        """
        query = """
            UPDATE dashboard_messages 
            SET status = :status,
                processing_time_ms = COALESCE(:processing_time_ms, processing_time_ms)
            WHERE message_id = :message_id
        """
        
        params = {
            "message_id": message_id,
            "status": status,
            "processing_time_ms": processing_time_ms
        }
        
        rows_affected = self._execute_non_query(query, params)
        return rows_affected > 0
    
    def get_message_statistics(self) -> Dict[str, Any]:
        """
        Get message statistics.
        
        Returns:
            Dictionary with message statistics
        """
        query = """
            SELECT 
                COUNT(*) as total_messages,
                COUNT(CASE WHEN message_type = 'user_query' THEN 1 END) as user_queries,
                COUNT(CASE WHEN message_type = 'ai_response' THEN 1 END) as ai_responses,
                COUNT(CASE WHEN message_type = 'system_message' THEN 1 END) as system_messages,
                COUNT(CASE WHEN status = 'success' THEN 1 END) as successful_messages,
                COUNT(CASE WHEN status = 'error' THEN 1 END) as error_messages,
                COUNT(CASE WHEN status = 'timeout' THEN 1 END) as timeout_messages,
                AVG(processing_time_ms) as avg_processing_time_ms,
                AVG(tokens_used) as avg_tokens_used
            FROM dashboard_messages
        """
        
        result = self._execute_query(query)
        return result[0] if result and len(result) > 0 else {}