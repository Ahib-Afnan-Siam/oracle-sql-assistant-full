"""
Dashboard Recorder for real-time data collection and storage.
This module integrates with the dashboard tables to record all real-time data accurately.
"""

import logging
import time
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.dashboard.dashboard_service import DashboardService

logger = logging.getLogger(__name__)

class DashboardRecorder:
    """Recorder class for dashboard data collection and storage."""
    
    def __init__(self):
        """Initialize the dashboard recorder."""
        self.dashboard_service = DashboardService()
        self.active_sessions = {}  # Track active sessions in memory
        
    def _get_database_type_from_chat(self, chat_id: int) -> Optional[str]:
        """
        Get database type from chat ID.
        
        Args:
            chat_id: Chat identifier
            
        Returns:
            Database type or None if not found
        """
        try:
            chat = self.dashboard_service.chats.get_chat_by_id(chat_id)
            return chat.get('database_type') if chat else None
        except Exception as e:
            logger.error(f"Error getting database type from chat {chat_id}: {str(e)}")
            return None
        
    def start_chat_session(self, session_id: str, user_id: str, username: str, 
                          database_type: Optional[str] = None, 
                          query_mode: Optional[str] = None) -> Optional[int]:
        """
        Start a new chat session and record it in the dashboard_chats table.
        If a chat already exists for this session, return the existing chat ID.
        
        Args:
            session_id: Unique session identifier
            user_id: User identifier from user_access.py
            username: Username from user_access.py
            database_type: Type of database being queried
            query_mode: Query mode (e.g., 'text', 'voice', 'file')
            
        Returns:
            Chat ID of the chat session or None if failed
        """
        try:
            # First check if there are existing chats for this session
            existing_chats = self.dashboard_service.chats.get_chats_by_session(session_id)
            if existing_chats and len(existing_chats) > 0 and 'chat_id' in existing_chats[0]:
                # Return the most recent chat ID
                chat_id = existing_chats[0]['chat_id']
                logger.info(f"Using existing chat session {chat_id} for user {username} (session: {session_id})")
                
                # Track active session if not already tracked
                if session_id not in self.active_sessions:
                    self.active_sessions[session_id] = {
                        'chat_id': chat_id,
                        'start_time': datetime.now(),
                        'user_id': user_id,
                        'username': username
                    }
                return chat_id
            
            # Create new chat session
            chat_id = self.dashboard_service.chats.create_chat(
                session_id=session_id,
                user_id=user_id,
                username=username,
                database_type=database_type,
                query_mode=query_mode
            )
            
            if chat_id:
                # Track active session
                self.active_sessions[session_id] = {
                    'chat_id': chat_id,
                    'start_time': datetime.now(),
                    'user_id': user_id,
                    'username': username
                }
                logger.info(f"Started chat session {chat_id} for user {username} (session: {session_id})")
                
            return chat_id
        except Exception as e:
            logger.error(f"Error starting chat session: {str(e)}")
            return None
    
    def end_chat_session(self, session_id: str, status: str = 'completed') -> bool:
        """
        End a chat session and update its end time and duration.
        
        Args:
            session_id: Session identifier
            status: Chat status ('completed', 'abandoned')
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if session_id in self.active_sessions and 'chat_id' in self.active_sessions[session_id]:
                chat_id = self.active_sessions[session_id]['chat_id']
                success = self.dashboard_service.chats.update_chat_end(chat_id, status)
                
                if success:
                    # Remove from active sessions
                    del self.active_sessions[session_id]
                    logger.info(f"Ended chat session {chat_id} with status: {status}")
                    
                return success
            else:
                logger.warning(f"Session {session_id} not found in active sessions")
                return False
        except Exception as e:
            logger.error(f"Error ending chat session: {str(e)}")
            return False
    
    def record_user_query(self, chat_id: int, content: str, 
                         processing_time_ms: Optional[int] = None,
                         tokens_used: Optional[int] = None,
                         model_name: Optional[str] = None) -> Optional[int]:
        """
        Record a user query message in the dashboard_messages table.
        
        Args:
            chat_id: Chat identifier
            content: User query content
            processing_time_ms: Processing time in milliseconds
            tokens_used: Number of tokens used
            model_name: Model name used
            
        Returns:
            Message ID of the newly created message or None if failed
        """
        try:
            # Get database type from chat
            database_type = self._get_database_type_from_chat(chat_id)
            
            message_id = self.dashboard_service.messages.create_message(
                chat_id=chat_id,
                message_type='user_query',
                content=content,
                processing_time_ms=processing_time_ms,
                tokens_used=tokens_used,
                model_name=model_name,
                database_type=database_type
            )
            
            if message_id:
                logger.info(f"Recorded user query message {message_id} for chat {chat_id}")
                
            return message_id
        except Exception as e:
            logger.error(f"Error recording user query: {str(e)}")
            return None
    
    def record_ai_response(self, chat_id: int, content: str,
                          processing_time_ms: Optional[int] = None,
                          tokens_used: Optional[int] = None,
                          model_name: Optional[str] = None,
                          status: str = 'success') -> Optional[int]:
        """
        Record an AI response message in the dashboard_messages table.
        
        Args:
            chat_id: Chat identifier
            content: AI response content
            processing_time_ms: Processing time in milliseconds
            tokens_used: Number of tokens used
            model_name: Model name used
            status: Message status ('success', 'error', 'timeout')
            
        Returns:
            Message ID of the newly created message or None if failed
        """
        try:
            # Get database type from chat
            database_type = self._get_database_type_from_chat(chat_id)
            
            message_id = self.dashboard_service.messages.create_message(
                chat_id=chat_id,
                message_type='ai_response',
                content=content,
                processing_time_ms=processing_time_ms,
                tokens_used=tokens_used,
                model_name=model_name,
                status=status,
                database_type=database_type
            )
            
            if message_id:
                logger.info(f"Recorded AI response message {message_id} for chat {chat_id}")
                
            return message_id
        except Exception as e:
            logger.error(f"Error recording AI response: {str(e)}")
            return None
    
    def record_system_message(self, chat_id: int, content: str,
                             status: str = 'success') -> Optional[int]:
        """
        Record a system message in the dashboard_messages table.
        
        Args:
            chat_id: Chat identifier
            content: System message content
            status: Message status ('success', 'error', 'timeout')
            
        Returns:
            Message ID of the newly created message or None if failed
        """
        try:
            # Get database type from chat
            database_type = self._get_database_type_from_chat(chat_id)
            
            message_id = self.dashboard_service.messages.create_message(
                chat_id=chat_id,
                message_type='system_message',
                content=content,
                status=status,
                database_type=database_type
            )
            
            if message_id:
                logger.info(f"Recorded system message {message_id} for chat {chat_id}")
                
            return message_id
        except Exception as e:
            logger.error(f"Error recording system message: {str(e)}")
            return None
    
    def record_token_usage(self, chat_id: int, message_id: Optional[int],
                          model_type: str, model_name: str,
                          prompt_tokens: int, completion_tokens: int,
                          total_tokens: int, cost_usd: float,
                          database_type: Optional[str] = None) -> Optional[int]:
        """
        Record token usage in the dashboard_token_usage table.
        
        Args:
            chat_id: Chat identifier
            message_id: Message identifier (optional)
            model_type: Model type ('api', 'local')
            model_name: Model name
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            total_tokens: Total number of tokens
            cost_usd: Cost in USD
            database_type: Database type (optional)
            
        Returns:
            Usage ID of the newly created record or None if failed
        """
        try:
            # Validate input parameters
            if chat_id is None or not isinstance(chat_id, int) or chat_id <= 0:
                logger.warning(f"Invalid chat_id provided for token usage recording: {chat_id}")
                return None
            
            if model_type not in ['api', 'local']:
                logger.warning(f"Invalid model_type provided for token usage recording: {model_type}")
                return None
            
            if not isinstance(model_name, str) or not model_name.strip():
                logger.warning(f"Invalid model_name provided for token usage recording: {model_name}")
                return None
            
            if not isinstance(prompt_tokens, int) or prompt_tokens < 0:
                logger.warning(f"Invalid prompt_tokens provided for token usage recording: {prompt_tokens}")
                return None
            
            if not isinstance(completion_tokens, int) or completion_tokens < 0:
                logger.warning(f"Invalid completion_tokens provided for token usage recording: {completion_tokens}")
                return None
            
            if not isinstance(total_tokens, int) or total_tokens < 0:
                logger.warning(f"Invalid total_tokens provided for token usage recording: {total_tokens}")
                return None
            
            if not isinstance(cost_usd, (int, float)) or cost_usd < 0:
                logger.warning(f"Invalid cost_usd provided for token usage recording: {cost_usd}")
                return None
            
            # Ensure total_tokens is consistent
            if total_tokens != prompt_tokens + completion_tokens:
                logger.debug(f"Total tokens ({total_tokens}) doesn't match sum of prompt ({prompt_tokens}) and completion ({completion_tokens}) tokens. Using calculated total.")
                total_tokens = prompt_tokens + completion_tokens
            
            usage_id = self.dashboard_service.token_usage.record_token_usage(
                chat_id=chat_id,
                message_id=message_id,
                model_type=model_type,
                model_name=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
                database_type=database_type
            )
            
            if usage_id:
                logger.info(f"Recorded token usage {usage_id} for chat {chat_id}: "
                           f"{prompt_tokens} prompt + {completion_tokens} completion = {total_tokens} tokens, "
                           f"cost: ${cost_usd:.6f}, model: {model_name} ({model_type})")
            else:
                logger.warning(f"Failed to record token usage for chat {chat_id}")
                
            return usage_id
        except Exception as e:
            logger.error(f"Error recording token usage for chat {chat_id}: {str(e)}", exc_info=True)
            return None
    
    def record_model_status(self, model_type: str, model_name: str,
                           status: str, response_time_ms: Optional[int] = None,
                           error_message: Optional[str] = None) -> Optional[int]:
        """
        Record model status in the dashboard_model_status table.
        
        Args:
            model_type: Model type ('api', 'local')
            model_name: Model name
            status: Model status ('available', 'unavailable', 'degraded')
            response_time_ms: Response time in milliseconds
            error_message: Error message if status is not 'available'
            
        Returns:
            Status ID of the newly created record or None if failed
        """
        try:
            status_id = self.dashboard_service.model_status.update_model_status(
                model_type=model_type,
                model_name=model_name,
                status=status,
                response_time_ms=response_time_ms,
                error_message=error_message
            )
            
            if status_id:
                logger.info(f"Recorded model status {status_id} for {model_name}")
                
            return status_id
        except Exception as e:
            logger.error(f"Error recording model status: {str(e)}")
            return None
    
    def record_feedback(self, chat_id: int, message_id: int,
                       feedback_type: str, feedback_score: int,
                       feedback_comment: Optional[str] = None) -> Optional[int]:
        """
        Record user feedback in the dashboard_feedback table.
        
        Args:
            chat_id: Chat identifier
            message_id: Message identifier
            feedback_type: Feedback type ('good', 'wrong', 'needs_improvement')
            feedback_score: Feedback score (1-5)
            feedback_comment: Feedback comment
            
        Returns:
            Feedback ID of the newly created record or None if failed
        """
        try:
            # Get database type from chat
            database_type = self._get_database_type_from_chat(chat_id)
            
            feedback_id = self.dashboard_service.feedback.create_feedback(
                chat_id=chat_id,
                message_id=message_id,
                feedback_type=feedback_type,
                feedback_score=feedback_score,
                feedback_comment=feedback_comment,
                database_type=database_type
            )
            
            if feedback_id:
                logger.info(f"Recorded feedback {feedback_id} for message {message_id}")
                
                # Update corresponding query history with feedback information
                try:
                    # Get session_id from chat
                    chat = self.dashboard_service.chats.get_chat_by_id(chat_id)
                    if chat and 'session_id' in chat:
                        session_id = chat['session_id']
                        
                        # Find the query in query history that corresponds to this session
                        # We'll update the most recent query for this session
                        queries = self.dashboard_service.query_history.get_queries_by_session(session_id, limit=1)
                        if queries and len(queries) > 0:
                            query_id = queries[0]['query_id']
                            
                            # Update query history with feedback information
                            success = self.dashboard_service.query_history.update_query_feedback(
                                query_id=query_id,
                                feedback_type=feedback_type,
                                feedback_comment=feedback_comment
                            )
                            
                            if success:
                                logger.info(f"Updated query history {query_id} with feedback for session {session_id}")
                            else:
                                logger.warning(f"Failed to update query history {query_id} with feedback")
                except Exception as update_error:
                    logger.error(f"Error updating query history with feedback: {str(update_error)}")
                
            return feedback_id
        except Exception as e:
            logger.error(f"Error recording feedback: {str(e)}")
            return None
    
    def record_server_metric(self, metric_name: str, metric_value: float,
                            metric_unit: str) -> Optional[int]:
        """
        Record a server metric in the dashboard_server_metrics table.
        
        Args:
            metric_name: Name of the metric
            metric_value: Value of the metric
            metric_unit: Unit of the metric
            
        Returns:
            Metric ID of the newly created record or None if failed
        """
        try:
            metric_id = self.dashboard_service.server_metrics.record_metric(
                metric_name=metric_name,
                metric_value=metric_value,
                metric_unit=metric_unit
            )
            
            if metric_id:
                logger.info(f"Recorded server metric {metric_id}: {metric_name} = {metric_value} {metric_unit}")
                
            return metric_id
        except Exception as e:
            logger.error(f"Error recording server metric: {str(e)}")
            return None
    
    def record_error_log(self, error_type: str, error_message: str,
                        error_details: Optional[str] = None,
                        severity: str = 'medium',
                        component: Optional[str] = None,
                        user_id: Optional[str] = None,
                        chat_id: Optional[int] = None) -> Optional[int]:
        """
        Record an error log in the dashboard_error_logs table.
        
        Args:
            error_type: Type of error
            error_message: Error message
            error_details: Detailed error information
            severity: Error severity ('low', 'medium', 'high', 'critical')
            component: Component where error occurred
            user_id: User identifier
            chat_id: Chat identifier
            
        Returns:
            Error ID of the newly created record or None if failed
        """
        try:
            error_id = self.dashboard_service.error_logs.log_error(
                error_type=error_type,
                error_message=error_message,
                error_details=error_details,
                severity=severity,
                component=component or '',  # Convert None to empty string
                user_id=user_id,
                chat_id=chat_id
            )
            
            if error_id:
                logger.info(f"Recorded error log {error_id}: {error_type} - {error_message}")
                
            return error_id
        except Exception as e:
            logger.error(f"Error recording error log: {str(e)}")
            return None
    
    def record_api_activity(self, api_endpoint: str, http_method: str,
                           response_status: int, response_time_ms: int,
                           user_id: Optional[str] = None,
                           ip_address: Optional[str] = None,
                           user_agent: Optional[str] = None) -> Optional[int]:
        """
        Record API activity in the dashboard_api_activity table.
        
        Args:
            api_endpoint: API endpoint
            http_method: HTTP method
            response_status: HTTP response status
            response_time_ms: Response time in milliseconds
            user_id: User identifier
            ip_address: IP address
            user_agent: User agent string
            
        Returns:
            Activity ID of the newly created record or None if failed
        """
        try:
            activity_id = self.dashboard_service.api_activity.log_api_call(
                api_endpoint=api_endpoint,
                http_method=http_method,
                response_status=response_status,
                response_time_ms=response_time_ms,
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            if activity_id:
                logger.info(f"Recorded API activity {activity_id}: {http_method} {api_endpoint} - {response_status}")
                
            return activity_id
        except Exception as e:
            logger.error(f"Error recording API activity: {str(e)}")
            return None
    
    def start_user_session(self, session_id: str, user_id: str, username: str,
                          ip_address: Optional[str] = None,
                          user_agent: Optional[str] = None) -> bool:
        """
        Start a user session in the dashboard_user_sessions table.
        If session already exists, update it instead of creating a new one.
        
        Args:
            session_id: Session identifier
            user_id: User identifier from user_access.py
            username: Username from user_access.py
            ip_address: IP address
            user_agent: User agent string
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # First check if session already exists
            existing_session = self.dashboard_service.user_sessions.get_session_by_id(session_id)
            
            if existing_session:
                # Session already exists, no need to create a new one
                logger.info(f"User session {session_id} already exists for user {username}")
                return True
            else:
                # Create new session
                success = self.dashboard_service.user_sessions.create_session(
                    session_id=session_id,
                    user_id=user_id,
                    username=username,
                    ip_address=ip_address,
                    user_agent=user_agent
                )
                
                if success:
                    logger.info(f"Started user session {session_id} for user {username}")
                    
                return success
        except Exception as e:
            logger.error(f"Error starting user session: {str(e)}")
            return False
    
    def end_user_session(self, session_id: str) -> bool:
        """
        End a user session and update its logout time and duration.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            success = self.dashboard_service.user_sessions.update_session_logout(session_id)
            
            if success:
                logger.info(f"Ended user session {session_id}")
                
            return success
        except Exception as e:
            logger.error(f"Error ending user session: {str(e)}")
            return False
    
    def record_query_history(self, user_id: Optional[str], session_id: str,
                            user_query: str, final_sql: str,
                            execution_status: str = 'success',
                            execution_time_ms: Optional[int] = None,
                            row_count: Optional[int] = None,
                            database_type: Optional[str] = None,
                            query_mode: Optional[str] = None,
                            feedback_type: Optional[str] = None,
                            feedback_comment: Optional[str] = None) -> Optional[int]:
        """
        Record query history in the dashboard_query_history table.
        
        Args:
            user_id: User identifier from user_access.py
            session_id: Session identifier (required, cannot be None or empty)
            user_query: User's natural language query
            final_sql: Generated SQL query
            execution_status: Execution status ('success', 'error', 'timeout') - NOT 'pending'
            execution_time_ms: Execution time in milliseconds
            row_count: Number of rows returned
            database_type: Type of database
            query_mode: Query mode
            feedback_type: Feedback type ('good', 'wrong', 'needs_improvement')
            feedback_comment: Feedback comment
            
        Returns:
            Query ID of the newly created record or None if failed
        """
        # Ensure session_id is provided and not empty
        if not session_id:
            logger.warning("Session ID is required for query history recording, generating a temporary one")
            import uuid
            session_id = f"temp_{str(uuid.uuid4())}"
        
        try:
            query_id = self.dashboard_service.query_history.insert_query_record(
                user_id=user_id,
                session_id=session_id,
                user_query=user_query,
                final_sql=final_sql,
                execution_status=execution_status,
                execution_time_ms=execution_time_ms,
                row_count=row_count,
                database_type=database_type,
                query_mode=query_mode,
                feedback_type=feedback_type,
                feedback_comment=feedback_comment
            )
            
            if query_id:
                logger.info(f"Recorded query history {query_id} for user {user_id}")
                
            return query_id
        except Exception as e:
            logger.error(f"Error recording query history: {str(e)}")
            return None

# Global instance of the dashboard recorder
_dashboard_recorder = None

def get_dashboard_recorder() -> DashboardRecorder:
    """
    Get the global dashboard recorder instance.
    
    Returns:
        DashboardRecorder instance
    """
    global _dashboard_recorder
    if _dashboard_recorder is None:
        _dashboard_recorder = DashboardRecorder()
    return _dashboard_recorder