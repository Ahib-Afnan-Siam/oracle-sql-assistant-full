# backend/app/ai_training_data_recorder.py
"""
AI Training Data Recorder - New Implementation

This module implements a comprehensive data recording framework for capturing all aspects 
of the SQL generation process for training the local model from API model data and feedback.

The system records data at each stage of processing:
1. Query received → Record in AI_TRAINING_QUERIES
2. Classification done → Record in AI_QUERY_CLASSIFICATIONS
3. Schema retrieved → Record in AI_SCHEMA_CONTEXTS
4. Models process → Record in AI_MODEL_INTERACTIONS (both)
5. Selection made → Record in AI_RESPONSE_SELECTIONS
6. SQL validated → Record in AI_SQL_PROCESSING
7. SQL executed → Record in AI_EXECUTION_RESULTS
8. Fallback triggered → Record in AI_FALLBACK_EVENTS
9. User feedback → Record in AI_USER_FEEDBACK

Recording Mechanisms:
- Synchronous recording for critical data
- Asynchronous background tasks for non-critical data
- Buffering mechanism to handle high-volume scenarios
- Retry logic for recording failures
- Circuit breaker for recording system
- Health checks for recording system
"""

import json
import logging
import time
import threading
import queue
from typing import Dict, Any, Optional, List
from datetime import datetime
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from enum import Enum

from .db_connector import connect_feedback
from .utils import _json_dumps, _insert_with_returning

logger = logging.getLogger(__name__)

class RecordingMode(Enum):
    """Recording mode for different types of data."""
    SYNCHRONOUS = "synchronous"
    ASYNCHRONOUS = "asynchronous"
    BUFFERED = "buffered"

class DataPriority(Enum):
    """Priority levels for recorded data."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

@dataclass
class RecordingContext:
    """Context for recording operations."""
    session_id: Optional[str] = None
    client_info: Optional[str] = None
    database_type: Optional[str] = None
    query_mode: Optional[str] = None
    username: Optional[str] = None  # Add username field
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

class CircuitBreaker:
    """Circuit breaker for recording system to prevent cascading failures."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func, *args, **kwargs):
        """Call function with circuit breaker protection."""
        if self.state == "OPEN":
            if self.last_failure_time and (datetime.now().timestamp() - self.last_failure_time) > self.recovery_timeout:
                self.state = "HALF_OPEN"
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
    
    def _on_success(self):
        """Handle successful operation."""
        self.failure_count = 0
        self.state = "CLOSED"
    
    def _on_failure(self):
        """Handle failed operation."""
        self.failure_count += 1
        self.last_failure_time = datetime.now().timestamp()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"

class HealthChecker:
    """Health checker for recording system."""
    
    def __init__(self, recorder):
        self.recorder = recorder
        self.last_check_time = None
        self.last_check_result = None
        self.check_interval = 300  # 5 minutes
    
    def is_healthy(self) -> bool:
        """Check if the recording system is healthy."""
        current_time = datetime.now()
        
        # If we haven't checked recently, perform a health check
        if (not self.last_check_time or 
            (current_time - self.last_check_time).seconds > self.check_interval):
            self.last_check_result = self._perform_health_check()
            self.last_check_time = current_time
        
        return self.last_check_result if self.last_check_result is not None else True
    
    def _perform_health_check(self) -> bool:
        """Perform actual health check by testing database connection."""
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                # Simple query to test connection
                cur.execute("SELECT 1 FROM DUAL")
                result = cur.fetchone()
                return result is not None
        except Exception as e:
            self.recorder.logger.error(f"Health check failed: {e}")
            return False
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get detailed health status."""
        return {
            'is_healthy': self.is_healthy(),
            'last_check_time': self.last_check_time.isoformat() if self.last_check_time else None,
            'circuit_breaker_state': self.recorder.circuit_breaker.state,
            'circuit_breaker_failures': self.recorder.circuit_breaker.failure_count
        }

class RecordingBuffer:
    """Buffer for batching recording operations."""
    
    def __init__(self, max_size: int = 100, flush_interval: int = 30):
        self.max_size = max_size
        self.flush_interval = flush_interval
        self.buffer = []
        self.last_flush = datetime.now()
        self.lock = threading.Lock()
    
    def add(self, record: Dict[str, Any]):
        """Add a record to the buffer."""
        with self.lock:
            self.buffer.append(record)
            if len(self.buffer) >= self.max_size:
                self.flush()
            elif (datetime.now() - self.last_flush).seconds >= self.flush_interval:
                self.flush()
    
    def flush(self):
        """Flush the buffer to database."""
        with self.lock:
            if self.buffer:
                try:
                    self._batch_insert(self.buffer)
                    self.buffer.clear()
                    self.last_flush = datetime.now()
                except Exception as e:
                    logger.error(f"Failed to flush recording buffer: {e}")
    
    def _batch_insert(self, records: List[Dict[str, Any]]):
        """Batch insert records to database."""
        # This would be implemented based on specific table structures
        pass

class RetryHandler:
    """Handler for retrying failed recording operations."""
    
    def __init__(self, max_retries: int = 3, backoff_factor: float = 1.0):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.failed_records = queue.Queue()
        self.retry_thread = threading.Thread(target=self._retry_worker, daemon=True)
        self.retry_thread.start()
    
    def record_failure(self, record: Dict[str, Any], error: Exception):
        """Record a failed operation for retry."""
        self.failed_records.put({
            'record': record,
            'error': str(error),
            'attempt': 1,
            'timestamp': datetime.now()
        })
    
    def _retry_worker(self):
        """Worker thread for retrying failed operations."""
        while True:
            try:
                failed_record = self.failed_records.get(timeout=1)
                self._retry_record(failed_record)
            except queue.Empty:
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"Error in retry worker: {e}")
    
    def _retry_record(self, failed_record: Dict[str, Any]):
        """Retry a failed record."""
        # Implementation would depend on the specific recording function
        pass

class AITrainingDataRecorder:
    """Main class for recording AI training data."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.circuit_breaker = CircuitBreaker()
        self.buffer = RecordingBuffer()
        self.retry_handler = RetryHandler()
        self.health_checker = HealthChecker(self)
        self._test_database_connection()
    
    def _test_database_connection(self):
        """Test database connection and verify training data tables exist."""
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                
                # Check if new training data tables exist
                training_tables = [
                    'AI_TRAINING_QUERIES', 'AI_QUERY_CLASSIFICATIONS', 'AI_SCHEMA_CONTEXTS',
                    'AI_MODEL_INTERACTIONS', 'AI_RESPONSE_SELECTIONS', 'AI_SQL_PROCESSING',
                    'AI_EXECUTION_RESULTS', 'AI_FALLBACK_EVENTS', 'AI_USER_FEEDBACK'
                ]
                
                for table in training_tables:
                    try:
                        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE ROWNUM = 1")
                        self.logger.debug(f"[TRAINING_DATA] Table {table} exists and is accessible")
                    except Exception as e:
                        self.logger.warning(f"[TRAINING_DATA] Table {table} not accessible: {e}")
                        
        except Exception as e:
            self.logger.error(f"[TRAINING_DATA] Database connection test failed: {e}")
    
    def record_training_query(self, 
                            user_query_text: str,
                            context: RecordingContext) -> int:
        """
        Record a training query in AI_TRAINING_QUERIES table.
        
        Args:
            user_query_text: The user's query text
            context: Recording context with session info
            
        Returns:
            ID of created record
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                query_id = _insert_with_returning(
                    cur,
                    """
                    INSERT INTO AI_TRAINING_QUERIES
                      (USER_QUERY_TEXT, TIMESTAMP, SESSION_ID, CLIENT_INFO, DATABASE_TYPE, QUERY_MODE, USERNAME)
                    VALUES
                      (:user_query, :timestamp, :session_id, :client_info, :database_type, :query_mode, :username)
                    RETURNING QUERY_ID INTO :new_id
                    """,
                    {
                        "user_query": user_query_text,
                        "timestamp": context.timestamp,
                        "session_id": context.session_id,
                        "client_info": context.client_info,
                        "database_type": context.database_type,
                        "query_mode": context.query_mode,
                        "username": context.username  # Add username parameter
                    }
                )
                conn.commit()
                self.logger.debug(f"Recorded training query {query_id}")
                return query_id
                
        except Exception as e:
            self.logger.error(f"Failed to record training query: {e}")
            self.retry_handler.record_failure({
                'operation': 'record_training_query',
                'user_query_text': user_query_text,
                'context': asdict(context)
            }, e)
            return 0
    
    def record_query_classification(self,
                                  query_id: int,
                                  classification_result: Dict[str, Any]) -> int:
        """
        Record query classification in AI_QUERY_CLASSIFICATIONS table.
        
        Args:
            query_id: Reference to AI_TRAINING_QUERIES table
            classification_result: Classification result data
            
        Returns:
            ID of created record
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                classification_id = _insert_with_returning(
                    cur,
                    """
                    INSERT INTO AI_QUERY_CLASSIFICATIONS
                      (QUERY_ID, INTENT, CONFIDENCE_SCORE, COMPLEXITY_SCORE, 
                       ENTITIES_JSON, PROCESSING_STRATEGY, BUSINESS_CONTEXT, CLASSIFICATION_TIMESTAMP)
                    VALUES
                      (:query_id, :intent, :confidence, :complexity, 
                       :entities, :strategy, :business_context, :classification_time)
                    RETURNING CLASSIFICATION_ID INTO :new_id
                    """,
                    {
                        "query_id": query_id,
                        "intent": classification_result.get('intent'),
                        "confidence": classification_result.get('confidence'),
                        "complexity": classification_result.get('complexity_score'),
                        "entities": _json_dumps(classification_result.get('entities', {})),
                        "strategy": classification_result.get('strategy'),
                        "business_context": classification_result.get('business_context', ''),
                        "classification_time": classification_result.get('classification_timestamp', datetime.now())
                    }
                )
                conn.commit()
                self.logger.debug(f"Recorded query classification {classification_id} for query {query_id}")
                return classification_id
                
        except Exception as e:
            self.logger.error(f"Failed to record query classification for query {query_id}: {e}")
            self.retry_handler.record_failure({
                'operation': 'record_query_classification',
                'query_id': query_id,
                'classification_result': classification_result
            }, e)
            return 0
    
    def record_schema_context(self,
                            query_id: int,
                            schema_info: Dict[str, Any]) -> int:
        """
        Record schema context in AI_SCHEMA_CONTEXTS table.
        
        Args:
            query_id: Reference to AI_TRAINING_QUERIES table
            schema_info: Schema context information
            
        Returns:
            ID of created record
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                context_id = _insert_with_returning(
                    cur,
                    """
                    INSERT INTO AI_SCHEMA_CONTEXTS
                      (QUERY_ID, SCHEMA_DEFINITION_JSON, TABLES_USED_JSON, COLUMN_MAPPING_JSON, RETRIEVAL_TIMESTAMP)
                    VALUES
                      (:query_id, :schema_definition, :tables_used, :column_mapping, :retrieval_timestamp)
                    RETURNING CONTEXT_ID INTO :new_id
                    """,
                    {
                        "query_id": query_id,
                        "schema_definition": _json_dumps(schema_info.get('schema_definition', {})),
                        "tables_used": _json_dumps(schema_info.get('tables_used', [])),
                        "column_mapping": _json_dumps(schema_info.get('column_mapping', {})),
                        "retrieval_timestamp": schema_info.get('retrieval_timestamp', datetime.now())
                    }
                )
                conn.commit()
                self.logger.debug(f"Recorded schema context {context_id} for query {query_id}")
                return context_id
                
        except Exception as e:
            self.logger.error(f"Failed to record schema context for query {query_id}: {e}")
            self.retry_handler.record_failure({
                'operation': 'record_schema_context',
                'query_id': query_id,
                'schema_info': schema_info
            }, e)
            return 0
    
    def record_model_interaction(self,
                               query_id: int,
                               model_type: str,  # 'api' or 'local'
                               model_details: Dict[str, Any]) -> int:
        """
        Record model interaction in AI_MODEL_INTERACTIONS table.
        
        Args:
            query_id: Reference to AI_TRAINING_QUERIES table
            model_type: 'api' or 'local'
            model_details: Model interaction details
            
        Returns:
            ID of created record
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                interaction_id = _insert_with_returning(
                    cur,
                    """
                    INSERT INTO AI_MODEL_INTERACTIONS
                      (QUERY_ID, MODEL_TYPE, MODEL_NAME, PROVIDER, PROMPT_TEXT,
                       RESPONSE_TEXT, RESPONSE_TIME_MS, CONFIDENCE_SCORE, TOKEN_COUNT, COST_USD, ERROR_MESSAGE, STATUS, INTERACTION_TIMESTAMP)
                    VALUES
                      (:query_id, :model_type, :model_name, :provider, :prompt,
                       :response, :response_time, :confidence, :token_count, :cost_usd, :error_message, :status, :interaction_time)
                    RETURNING INTERACTION_ID INTO :new_id
                    """,
                    {
                        "query_id": query_id,
                        "model_type": model_type,
                        "model_name": model_details.get('model_name'),
                        "provider": model_details.get('provider', ''),
                        "prompt": model_details.get('prompt_text', ''),
                        "response": model_details.get('response_text', ''),
                        "response_time": model_details.get('response_time_ms', 0),
                        "confidence": model_details.get('confidence_score', 0.0),
                        "token_count": model_details.get('token_count', 0),
                        "cost_usd": model_details.get('cost_usd', 0.0),
                        "error_message": model_details.get('error_message', ''),
                        "status": model_details.get('status', 'unknown'),
                        "interaction_time": model_details.get('interaction_timestamp', datetime.now())
                    }
                )
                conn.commit()
                self.logger.debug(f"Recorded model interaction {interaction_id} for query {query_id}")
                return interaction_id
                
        except Exception as e:
            self.logger.error(f"Failed to record model interaction for query {query_id}: {e}")
            self.retry_handler.record_failure({
                'operation': 'record_model_interaction',
                'query_id': query_id,
                'model_type': model_type,
                'model_details': model_details
            }, e)
            return 0
    
    def record_response_selection(self,
                                query_id: int,
                                selection_details: Dict[str, Any]) -> int:
        """
        Record response selection in AI_RESPONSE_SELECTIONS table.
        
        Args:
            query_id: Reference to AI_TRAINING_QUERIES table
            selection_details: Response selection details
            
        Returns:
            ID of created record
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                selection_id = _insert_with_returning(
                    cur,
                    """
                    INSERT INTO AI_RESPONSE_SELECTIONS
                      (QUERY_ID, SELECTED_MODEL_TYPE, SELECTION_CRITERIA_JSON, SCORE_COMPARISON_JSON, FINAL_RESPONSE_TEXT, SELECTION_REASONING, SELECTION_TIMESTAMP)
                    VALUES
                      (:query_id, :selected_model, :selection_criteria, :score_comparison, :final_response, :reasoning, :selection_time)
                    RETURNING SELECTION_ID INTO :new_id
                    """,
                    {
                        "query_id": query_id,
                        "selected_model": selection_details.get('selected_model_type'),
                        "selection_criteria": _json_dumps(selection_details.get('selection_criteria', {})),
                        "score_comparison": _json_dumps(selection_details.get('score_comparison', {})),
                        "final_response": selection_details.get('final_response_text', ''),
                        "reasoning": selection_details.get('selection_reasoning', ''),
                        "selection_time": selection_details.get('selection_timestamp', datetime.now())
                    }
                )
                conn.commit()
                self.logger.debug(f"Recorded response selection {selection_id} for query {query_id}")
                return selection_id
                
        except Exception as e:
            self.logger.error(f"Failed to record response selection for query {query_id}: {e}")
            self.retry_handler.record_failure({
                'operation': 'record_response_selection',
                'query_id': query_id,
                'selection_details': selection_details
            }, e)
            return 0
    
    def record_sql_processing(self,
                            query_id: int,
                            processing_details: Dict[str, Any]) -> int:
        """
        Record SQL processing in AI_SQL_PROCESSING table.
        
        Args:
            query_id: Reference to AI_TRAINING_QUERIES table
            processing_details: SQL processing details
            
        Returns:
            ID of created record
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                processing_id = _insert_with_returning(
                    cur,
                    """
                    INSERT INTO AI_SQL_PROCESSING
                      (QUERY_ID, EXTRACTED_SQL, VALIDATION_STATUS, VALIDATION_ERRORS_JSON,
                       OPTIMIZATION_SUGGESTIONS_JSON, FINAL_SQL, PROCESSING_TIMESTAMP)
                    VALUES
                      (:query_id, :extracted_sql, :validation_status, :validation_errors,
                       :optimization_suggestions, :final_sql, :processing_time)
                    RETURNING PROCESSING_ID INTO :new_id
                    """,
                    {
                        "query_id": query_id,
                        "extracted_sql": processing_details.get('extracted_sql'),
                        "validation_status": processing_details.get('validation_status'),
                        "validation_errors": _json_dumps(processing_details.get('validation_errors', [])),
                        "optimization_suggestions": _json_dumps(processing_details.get('optimization_suggestions', [])),
                        "final_sql": processing_details.get('final_sql'),
                        "processing_time": processing_details.get('processing_timestamp', datetime.now())
                    }
                )
                conn.commit()
                self.logger.debug(f"Recorded SQL processing {processing_id} for query {query_id}")
                return processing_id
                
        except Exception as e:
            self.logger.error(f"Failed to record SQL processing for query {query_id}: {e}")
            self.retry_handler.record_failure({
                'operation': 'record_sql_processing',
                'query_id': query_id,
                'processing_details': processing_details
            }, e)
            return 0
    
    def record_execution_result(self,
                              query_id: int,
                              execution_details: Dict[str, Any]) -> int:
        """
        Record execution result in AI_EXECUTION_RESULTS table.
        
        Args:
            query_id: Reference to AI_TRAINING_QUERIES table
            execution_details: Execution result details
            
        Returns:
            ID of created record
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                execution_id = _insert_with_returning(
                    cur,
                    """
                    INSERT INTO AI_EXECUTION_RESULTS
                      (QUERY_ID, EXECUTION_TIME_MS, ROW_COUNT,
                       EXECUTION_STATUS, ERROR_MESSAGE)
                    VALUES
                      (:query_id, :execution_time, :row_count,
                       :execution_status, :error_details)
                    RETURNING RESULT_ID INTO :new_id
                    """,
                    {
                        "query_id": query_id,
                        "execution_time": execution_details.get('execution_time_ms', 0),
                        "row_count": execution_details.get('row_count', 0),
                        "execution_status": execution_details.get('execution_status', 'unknown'),
                        "error_details": execution_details.get('error_message', '')
                    }
                )
                conn.commit()
                self.logger.debug(f"Recorded execution result {execution_id} for query {query_id}")
                return execution_id
                
        except Exception as e:
            self.logger.error(f"Failed to record execution result for query {query_id}: {e}")
            self.retry_handler.record_failure({
                'operation': 'record_execution_result',
                'query_id': query_id,
                'execution_details': execution_details
            }, e)
            return 0
    
    def record_fallback_event(self,
                            query_id: int,
                            fallback_details: Dict[str, Any]) -> int:
        """
        Record fallback event in AI_FALLBACK_EVENTS table.
        
        Args:
            query_id: Reference to AI_TRAINING_QUERIES table
            fallback_details: Fallback event details
            
        Returns:
            ID of created record
        """
        try:
            with connect_feedback() as conn:
                cur = conn.cursor()
                fallback_id = _insert_with_returning(
                    cur,
                    """
                    INSERT INTO AI_FALLBACK_EVENTS
                      (QUERY_ID, TRIGGER_REASON, FALLBACK_MODEL_TYPE, FALLBACK_RESPONSE_TEXT, RECOVERY_STATUS, EVENT_TIMESTAMP)
                    VALUES
                      (:query_id, :fallback_reason, :fallback_model_type, :fallback_response, :recovery_status, :fallback_time)
                    RETURNING EVENT_ID INTO :new_id
                    """,
                    {
                        "query_id": query_id,
                        "fallback_reason": fallback_details.get('trigger_reason', ''),
                        "fallback_model_type": fallback_details.get('fallback_model_type', ''),
                        "fallback_response": fallback_details.get('fallback_response_text', ''),
                        "recovery_status": fallback_details.get('recovery_status', ''),
                        "fallback_time": fallback_details.get('event_timestamp', datetime.now())
                    }
                )
                conn.commit()
                self.logger.debug(f"Recorded fallback event {fallback_id} for query {query_id}")
                return fallback_id
                
        except Exception as e:
            self.logger.error(f"Failed to record fallback event for query {query_id}: {e}")
            self.retry_handler.record_failure({
                'operation': 'record_fallback_event',
                'query_id': query_id,
                'fallback_details': fallback_details
            }, e)
            return 0
    
    def record_user_feedback(self,
                           query_id: int,
                           feedback_details: Dict[str, Any]) -> int:
        """
        Record user feedback in AI_USER_FEEDBACK table.
        
        Args:
            query_id: Reference to AI_TRAINING_QUERIES table
            feedback_details: User feedback details
            
        Returns:
            ID of created record
        """
        try:
            feedback_type = feedback_details.get('feedback_type')
            feedback_comment = feedback_details.get('feedback_comment', '')
            source = feedback_details.get('source', '')
            
            self.logger.debug(f"Storing user feedback - Query ID: {query_id}, Type: {feedback_type}, Source: {source}")
            if feedback_comment:
                self.logger.debug(f"Feedback comment: {feedback_comment[:100]}{'...' if len(feedback_comment) > 100 else ''}")
            
            with connect_feedback() as conn:
                cur = conn.cursor()
                feedback_id = _insert_with_returning(
                    cur,
                    """
                    INSERT INTO AI_USER_FEEDBACK
                      (QUERY_ID, FEEDBACK_TYPE, FEEDBACK_SCORE, 
                       FEEDBACK_COMMENT, SOURCE, SUBMISSION_TIMESTAMP)
                    VALUES
                      (:query_id, :feedback_type, :feedback_score, 
                       :feedback_comment, :source, :submission_timestamp)
                    RETURNING FEEDBACK_ID INTO :new_id
                    """,
                    {
                        "query_id": query_id,
                        "feedback_type": feedback_type,
                        "feedback_score": feedback_details.get('feedback_score', 0),
                        "feedback_comment": feedback_comment,
                        "source": source,
                        "submission_timestamp": feedback_details.get('submission_timestamp', datetime.now())
                    }
                )
                conn.commit()
                self.logger.debug(f"Successfully stored user feedback - Feedback ID: {feedback_id}, Query ID: {query_id}, Type: {feedback_type}, Source: {source}")
                return feedback_id
                
        except Exception as e:
            self.logger.error(f"Failed to record user feedback for query {query_id}: {e}")
            self.retry_handler.record_failure({
                'operation': 'record_user_feedback',
                'query_id': query_id,
                'feedback_details': feedback_details
            }, e)
            return 0

    def record_with_mode(self, 
                        operation: str,
                        data: Dict[str, Any],
                        mode: RecordingMode = RecordingMode.SYNCHRONOUS,
                        priority: DataPriority = DataPriority.MEDIUM) -> int:
        """
        Record data with specified mode (synchronous, asynchronous, buffered).
        
        Args:
            operation: The recording operation name
            data: Data to record
            mode: Recording mode
            priority: Data priority level
            
        Returns:
            ID of created record or 0 if failed
        """
        if mode == RecordingMode.SYNCHRONOUS:
            return self._record_synchronously(operation, data)
        elif mode == RecordingMode.ASYNCHRONOUS:
            return self._record_asynchronously(operation, data)
        elif mode == RecordingMode.BUFFERED:
            return self._record_buffered(operation, data, priority)
        else:
            raise ValueError(f"Unknown recording mode: {mode}")
    
    def _record_synchronously(self, operation: str, data: Dict[str, Any]) -> int:
        """Record data synchronously."""
        try:
            return self._execute_recording_operation(operation, data)
        except Exception as e:
            self.logger.error(f"Synchronous recording failed for {operation}: {e}")
            self.retry_handler.record_failure({
                'operation': operation,
                'data': data
            }, e)
            return 0
    
    def _record_asynchronously(self, operation: str, data: Dict[str, Any]) -> int:
        """Record data asynchronously using a thread pool."""
        def async_record():
            try:
                self._execute_recording_operation(operation, data)
            except Exception as e:
                self.logger.error(f"Asynchronous recording failed for {operation}: {e}")
                self.retry_handler.record_failure({
                    'operation': operation,
                    'data': data
                }, e)
        
        # Submit to thread pool for asynchronous execution
        thread = threading.Thread(target=async_record, daemon=True)
        thread.start()
        return -1  # Indicate asynchronous operation
    
    def _record_buffered(self, operation: str, data: Dict[str, Any], priority: DataPriority) -> int:
        """Record data using buffering mechanism."""
        record = {
            'operation': operation,
            'data': data,
            'priority': priority.value,
            'timestamp': datetime.now()
        }
        
        self.buffer.add(record)
        return -2  # Indicate buffered operation
    
    def _execute_recording_operation(self, operation: str, data: Dict[str, Any]) -> int:
        """Execute a specific recording operation."""
        operation_map = {
            'record_training_query': self._execute_record_training_query,
            'record_query_classification': self._execute_record_query_classification,
            'record_schema_context': self._execute_record_schema_context,
            'record_model_interaction': self._execute_record_model_interaction,
            'record_response_selection': self._execute_record_response_selection,
            'record_sql_processing': self._execute_record_sql_processing,
            'record_execution_result': self._execute_record_execution_result,
            'record_fallback_event': self._execute_record_fallback_event,
            'record_user_feedback': self._execute_record_user_feedback
        }
        
        if operation in operation_map:
            return operation_map[operation](data)
        else:
            raise ValueError(f"Unknown recording operation: {operation}")
    
    def _execute_record_training_query(self, data: Dict[str, Any]) -> int:
        """Execute recording of training query."""
        context = RecordingContext(
            session_id=data.get('session_id'),
            client_info=data.get('client_info'),
            database_type=data.get('database_type'),
            query_mode=data.get('query_mode'),
            username=data.get('username'),  # Add username parameter
            timestamp=data.get('timestamp')
        )
        return self.record_training_query(data['user_query_text'], context)
    
    def _execute_record_query_classification(self, data: Dict[str, Any]) -> int:
        """Execute recording of query classification."""
        return self.record_query_classification(data['query_id'], data['classification_result'])
    
    def _execute_record_schema_context(self, data: Dict[str, Any]) -> int:
        """Execute recording of schema context."""
        return self.record_schema_context(data['query_id'], data['schema_info'])
    
    def _execute_record_model_interaction(self, data: Dict[str, Any]) -> int:
        """Execute recording of model interaction."""
        return self.record_model_interaction(data['query_id'], data['model_type'], data['model_details'])
    
    def _execute_record_response_selection(self, data: Dict[str, Any]) -> int:
        """Execute recording of response selection."""
        return self.record_response_selection(data['query_id'], data['selection_details'])
    
    def _execute_record_sql_processing(self, data: Dict[str, Any]) -> int:
        """Execute recording of SQL processing."""
        return self.record_sql_processing(data['query_id'], data['processing_details'])
    
    def _execute_record_execution_result(self, data: Dict[str, Any]) -> int:
        """Execute recording of execution result."""
        return self.record_execution_result(data['query_id'], data['execution_details'])
    
    def _execute_record_fallback_event(self, data: Dict[str, Any]) -> int:
        """Execute recording of fallback event."""
        return self.record_fallback_event(data['query_id'], data['fallback_details'])
    
    def _execute_record_user_feedback(self, data: Dict[str, Any]) -> int:
        """Execute recording of user feedback."""
        return self.record_user_feedback(data['query_id'], data['feedback_details'])
    
    def record_complete_processing_flow(self, processing_data: Dict[str, Any]) -> Dict[str, int]:
        """
        Record complete processing flow according to the data flow mapping:
        
        Query received → Record in TRAINING_QUERIES
        Classification done → Record in QUERY_CLASSIFICATIONS
        Schema retrieved → Record in SCHEMA_CONTEXTS
        Models process → Record in MODEL_INTERACTIONS (both)
        Selection made → Record in RESPONSE_SELECTIONS
        SQL validated → Record in SQL_PROCESSING
        SQL executed → Record in EXECUTION_RESULTS
        Fallback triggered → Record in FALLBACK_EVENTS (if applicable)
        
        Args:
            processing_data: Complete processing data
            
        Returns:
            Dictionary with IDs of all created records
        """
        recorded_ids = {}
        
        try:
            # 1. Query received → Record in TRAINING_QUERIES
            context = RecordingContext(
                session_id=processing_data.get('session_id'),
                client_info=processing_data.get('client_info'),
                database_type=processing_data.get('database_type'),
                query_mode=processing_data.get('query_mode'),
                username=processing_data.get('username')  # Add username parameter
            )
            
            query_id = self.record_training_query(
                user_query_text=processing_data['user_query_text'],
                context=context
            )
            recorded_ids['query_id'] = query_id
            
            if not query_id:
                self.logger.error("Failed to record training query, aborting flow")
                return recorded_ids
            
            # 2. Classification done → Record in QUERY_CLASSIFICATIONS
            if 'classification_result' in processing_data:
                classification_id = self.record_query_classification(
                    query_id=query_id,
                    classification_result=processing_data['classification_result']
                )
                recorded_ids['classification_id'] = classification_id
            
            # 3. Schema retrieved → Record in SCHEMA_CONTEXTS
            if 'schema_info' in processing_data:
                schema_id = self.record_schema_context(
                    query_id=query_id,
                    schema_info=processing_data['schema_info']
                )
                recorded_ids['schema_id'] = schema_id
            
            # 4. Models process → Record in MODEL_INTERACTIONS (both)
            if 'model_interactions' in processing_data:
                interaction_ids = []
                for model_interaction in processing_data['model_interactions']:
                    interaction_id = self.record_model_interaction(
                        query_id=query_id,
                        model_type=model_interaction['model_type'],
                        model_details=model_interaction['model_details']
                    )
                    interaction_ids.append(interaction_id)
                recorded_ids['model_interaction_ids'] = interaction_ids
            
            # 5. Selection made → Record in RESPONSE_SELECTIONS
            if 'selection_details' in processing_data:
                selection_id = self.record_response_selection(
                    query_id=query_id,
                    selection_details=processing_data['selection_details']
                )
                recorded_ids['selection_id'] = selection_id
            
            # 6. SQL validated → Record in SQL_PROCESSING
            if 'sql_processing' in processing_data:
                processing_id = self.record_sql_processing(
                    query_id=query_id,
                    processing_details=processing_data['sql_processing']
                )
                recorded_ids['processing_id'] = processing_id
            
            # 7. SQL executed → Record in EXECUTION_RESULTS
            if 'execution_result' in processing_data:
                execution_id = self.record_execution_result(
                    query_id=query_id,
                    execution_details=processing_data['execution_result']
                )
                recorded_ids['execution_id'] = execution_id
            
            # 8. Fallback triggered → Record in FALLBACK_EVENTS (if applicable)
            if 'fallback_event' in processing_data:
                fallback_id = self.record_fallback_event(
                    query_id=query_id,
                    fallback_details=processing_data['fallback_event']
                )
                recorded_ids['fallback_id'] = fallback_id
            
            # 9. User feedback → Record in USER_FEEDBACK (if available)
            if 'user_feedback' in processing_data:
                feedback_id = self.record_user_feedback(
                    query_id=query_id,
                    feedback_details=processing_data['user_feedback']
                )
                recorded_ids['feedback_id'] = feedback_id
                
            self.logger.info(f"Successfully recorded complete processing flow with {len(recorded_ids)} records")
            return recorded_ids
            
        except Exception as e:
            self.logger.error(f"Failed to record complete processing flow: {e}")
            return recorded_ids
    
    def record_with_error_handling(self, 
                                 operation: str,
                                 data: Dict[str, Any],
                                 mode: RecordingMode = RecordingMode.SYNCHRONOUS) -> int:
        """
        Record data with comprehensive error handling.
        
        Args:
            operation: The recording operation name
            data: Data to record
            mode: Recording mode
            
        Returns:
            ID of created record or 0 if failed
        """
        # Check system health before proceeding
        if not self.health_checker.is_healthy():
            self.logger.warning("Recording system is not healthy, skipping recording")
            return 0
        
        # Use circuit breaker to prevent cascading failures
        try:
            return self.circuit_breaker.call(
                self.record_with_mode, 
                operation, 
                data, 
                mode
            )
        except Exception as e:
            self.logger.error(f"Recording failed with circuit breaker protection: {e}")
            # Don't retry here as circuit breaker will handle it
            return 0
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status."""
        return {
            'health': self.health_checker.get_health_status(),
            'buffer_size': len(self.buffer.buffer),
            'retry_queue_size': self.retry_handler.failed_records.qsize() if hasattr(self.retry_handler.failed_records, 'qsize') else 0
        }

# Global instance for easy access
ai_training_data_recorder = AITrainingDataRecorder()

# Convenience functions for direct import
def record_training_query(user_query_text: str, context: RecordingContext) -> int:
    """Convenience function to record a training query."""
    return ai_training_data_recorder.record_training_query(user_query_text, context)

def record_query_classification(query_id: int, classification_result: Dict[str, Any]) -> int:
    """Convenience function to record query classification."""
    return ai_training_data_recorder.record_query_classification(query_id, classification_result)

def record_schema_context(query_id: int, schema_info: Dict[str, Any]) -> int:
    """Convenience function to record schema context."""
    return ai_training_data_recorder.record_schema_context(query_id, schema_info)

def record_model_interaction(query_id: int, model_type: str, model_details: Dict[str, Any]) -> int:
    """Convenience function to record model interaction."""
    return ai_training_data_recorder.record_model_interaction(query_id, model_type, model_details)

def record_response_selection(query_id: int, selection_details: Dict[str, Any]) -> int:
    """Convenience function to record response selection."""
    return ai_training_data_recorder.record_response_selection(query_id, selection_details)

def record_sql_processing(query_id: int, processing_details: Dict[str, Any]) -> int:
    """Convenience function to record SQL processing."""
    return ai_training_data_recorder.record_sql_processing(query_id, processing_details)

def record_execution_result(query_id: int, execution_details: Dict[str, Any]) -> int:
    """Convenience function to record execution result."""
    return ai_training_data_recorder.record_execution_result(query_id, execution_details)

def record_fallback_event(query_id: int, fallback_details: Dict[str, Any]) -> int:
    """Convenience function to record fallback event."""
    return ai_training_data_recorder.record_fallback_event(query_id, fallback_details)

def record_user_feedback(query_id: int, feedback_details: Dict[str, Any]) -> int:
    """Convenience function to record user feedback."""
    feedback_type = feedback_details.get('feedback_type', 'unknown')
    source = feedback_details.get('source', 'unknown')
    logger.debug(f"Recording user feedback via wrapper - Query ID: {query_id}, Type: {feedback_type}, Source: {source}")
    result = ai_training_data_recorder.record_user_feedback(query_id, feedback_details)
    logger.debug(f"User feedback recording completed - Feedback ID: {result}")
    return result


