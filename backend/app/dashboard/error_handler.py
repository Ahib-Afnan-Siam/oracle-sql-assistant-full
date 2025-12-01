"""
Centralized error handling and logging framework for the dashboard module.
"""
import logging
import traceback
from typing import Any, Dict, Optional
from datetime import datetime

# Configure logger for dashboard module
logger = logging.getLogger(__name__)

class DashboardError(Exception):
    """Base exception class for dashboard-related errors."""
    
    def __init__(self, message: str, error_code: Optional[str] = None, 
                 details: Optional[Dict[str, Any]] = None):
        """
        Initialize dashboard error.
        
        Args:
            message: Error message
            error_code: Error code (optional)
            details: Additional error details (optional)
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.timestamp = datetime.now()

class DatabaseError(DashboardError):
    """Exception for database-related errors."""
    pass

class ValidationError(DashboardError):
    """Exception for data validation errors."""
    pass

class ServiceError(DashboardError):
    """Exception for service-related errors."""
    pass

class ErrorHandler:
    """Centralized error handling and logging framework."""
    
    @staticmethod
    def log_error(error: Exception, context: Optional[Dict[str, Any]] = None) -> None:
        """
        Log an error with context.
        
        Args:
            error: Exception to log
            context: Additional context information (optional)
        """
        error_info = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "timestamp": datetime.now().isoformat(),
            "traceback": traceback.format_exc()
        }
        
        if context:
            error_info["context"] = str(context)
        
        # Log with appropriate level based on error type
        if isinstance(error, (DatabaseError, ServiceError)):
            logger.error(f"Dashboard Error: {error_info}")
        elif isinstance(error, ValidationError):
            logger.warning(f"Dashboard Validation Error: {error_info}")
        else:
            logger.exception(f"Dashboard Unexpected Error: {error_info}")
    
    @staticmethod
    def handle_error(error: Exception, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Handle an error and return a formatted response.
        
        Args:
            error: Exception to handle
            context: Additional context information (optional)
            
        Returns:
            Formatted error response
        """
        # Log the error
        ErrorHandler.log_error(error, context)
        
        # Determine error code and message
        if isinstance(error, DashboardError):
            error_code = error.error_code
            message = error.message
        else:
            error_code = "INTERNAL_ERROR"
            message = "An unexpected error occurred"
        
        # Create error response
        response = {
            "status": "error",
            "data": None,
            "message": message,
            "error_code": error_code,
            "timestamp": datetime.now().isoformat()
        }
        
        # Include details for debugging in development
        if context and context.get("include_details", False):
            response["details"] = {
                "error_type": type(error).__name__,
                "traceback": traceback.format_exc()
            }
        
        return response
    
    @staticmethod
    def create_validation_error(field: str, message: str, value: Any = None) -> ValidationError:
        """
        Create a validation error.
        
        Args:
            field: Field name that failed validation
            message: Validation error message
            value: Invalid value (optional)
            
        Returns:
            ValidationError instance
        """
        details = {"field": field}
        if value is not None:
            details["value"] = value
            
        return ValidationError(
            message=f"Validation failed for field '{field}': {message}",
            error_code="VALIDATION_ERROR",
            details=details
        )
    
    @staticmethod
    def create_database_error(operation: str, message: str, 
                            query: Optional[str] = None) -> DatabaseError:
        """
        Create a database error.
        
        Args:
            operation: Database operation that failed
            message: Error message
            query: SQL query (optional)
            
        Returns:
            DatabaseError instance
        """
        details = {"operation": operation}
        if query:
            details["query"] = query
            
        return DatabaseError(
            message=f"Database operation '{operation}' failed: {message}",
            error_code="DATABASE_ERROR",
            details=details
        )
    
    @staticmethod
    def create_service_error(service: str, operation: str, message: str) -> ServiceError:
        """
        Create a service error.
        
        Args:
            service: Service name
            operation: Operation that failed
            message: Error message
            
        Returns:
            ServiceError instance
        """
        return ServiceError(
            message=f"Service '{service}' operation '{operation}' failed: {message}",
            error_code="SERVICE_ERROR",
            details={"service": service, "operation": operation}
        )

# Context manager for error handling
class ErrorContext:
    """Context manager for handling errors in a specific context."""
    
    def __init__(self, operation: str, context: Optional[Dict[str, Any]] = None):
        """
        Initialize error context.
        
        Args:
            operation: Operation being performed
            context: Additional context information (optional)
        """
        self.operation = operation
        self.context = context or {}
        self.context["operation"] = operation
    
    def __enter__(self):
        """Enter the context."""
        return self
    
    def __exit__(self, exc_type, exc_value, exc_traceback):
        """Exit the context and handle any exceptions."""
        if exc_type is not None:
            # An exception occurred, log and handle it
            ErrorHandler.log_error(exc_value, self.context)
        return False  # Don't suppress the exception