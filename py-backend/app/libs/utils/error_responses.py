"""
Standardized error response schemas and utilities for consistent error handling
across all API layers.
"""
import logging
from enum import Enum
from typing import Dict, Any, Optional, Union
from pydantic import BaseModel
from fastapi import HTTPException
from app.libs.utils.decorators import log_thought

logger = logging.getLogger(__name__)

class ErrorCode(str, Enum):
    """Standard error codes for the application"""
    # General errors
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    
    # Browser/Agent errors
    BROWSER_INITIALIZATION_ERROR = "BROWSER_INITIALIZATION_ERROR"
    BROWSER_CONNECTION_ERROR = "BROWSER_CONNECTION_ERROR"
    BROWSER_NAVIGATION_ERROR = "BROWSER_NAVIGATION_ERROR"
    BROWSER_ACTION_ERROR = "BROWSER_ACTION_ERROR"
    AGENT_TIMEOUT_ERROR = "AGENT_TIMEOUT_ERROR"
    
    # Session/Task errors
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    TASK_CLASSIFICATION_ERROR = "TASK_CLASSIFICATION_ERROR"
    TASK_EXECUTION_ERROR = "TASK_EXECUTION_ERROR"
    
    # Server/Infrastructure errors
    SERVER_CONNECTION_ERROR = "SERVER_CONNECTION_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"

class ErrorSeverity(str, Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class StandardErrorResponse(BaseModel):
    """Standard error response schema"""
    success: bool = False
    error_code: ErrorCode
    message: str
    details: Optional[str] = None
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    session_id: Optional[str] = None
    timestamp: Optional[str] = None
    request_id: Optional[str] = None
    retry_after: Optional[int] = None  # For rate limiting

class ErrorResponse:
    """Utility class for creating standardized error responses"""
    
    @staticmethod
    def create_error_response(
        error_code: ErrorCode,
        message: str,
        details: Optional[str] = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        session_id: Optional[str] = None,
        retry_after: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a standardized error response dictionary"""
        from datetime import datetime
        
        response = {
            "success": False,
            "error_code": error_code.value,
            "message": message,
            "severity": severity.value,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if details:
            response["details"] = details
        if session_id:
            response["session_id"] = session_id
        if retry_after:
            response["retry_after"] = retry_after
            
        return response
    
    @staticmethod
    def create_http_exception(
        status_code: int,
        error_code: ErrorCode,
        message: str,
        details: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> HTTPException:
        """Create a FastAPI HTTPException with standardized error format"""
        error_response = ErrorResponse.create_error_response(
            error_code=error_code,
            message=message,
            details=details,
            session_id=session_id
        )
        
        return HTTPException(
            status_code=status_code,
            detail=error_response
        )
    
    @staticmethod
    def log_and_create_error(
        exception: Exception,
        error_code: ErrorCode,
        context: str,
        session_id: Optional[str] = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM
    ) -> Dict[str, Any]:
        """Log an exception and create a standardized error response"""
        
        # Log the error with appropriate level
        error_message = f"{context}: {str(exception)}"
        
        if severity == ErrorSeverity.CRITICAL:
            logger.critical(error_message, exc_info=True)
        elif severity == ErrorSeverity.HIGH:
            logger.error(error_message, exc_info=True)
        elif severity == ErrorSeverity.MEDIUM:
            logger.warning(error_message, exc_info=True)
        else:
            logger.info(error_message, exc_info=True)
        
        # Log to thought stream if session provided
        if session_id:
            try:
                log_thought(
                    session_id=session_id,
                    type_name="error",
                    category="system_error",
                    node="ErrorHandler",
                    content=error_message
                )
            except Exception as thought_error:
                logger.debug(f"Failed to log error to thought stream: {thought_error}")
        
        return ErrorResponse.create_error_response(
            error_code=error_code,
            message=_get_user_friendly_message(error_code),
            details=str(exception),
            severity=severity,
            session_id=session_id
        )

def _get_user_friendly_message(error_code: ErrorCode) -> str:
    """Get user-friendly error message for error codes"""
    messages = {
        ErrorCode.UNKNOWN_ERROR: "An unexpected error occurred. Please try again.",
        ErrorCode.VALIDATION_ERROR: "The request contains invalid data. Please check your input.",
        ErrorCode.AUTHENTICATION_ERROR: "Authentication failed. Please verify your credentials.",
        ErrorCode.AUTHORIZATION_ERROR: "You don't have permission to perform this action.",
        
        ErrorCode.BROWSER_INITIALIZATION_ERROR: "Failed to initialize browser. Please try again.",
        ErrorCode.BROWSER_CONNECTION_ERROR: "Could not connect to browser. Please check your connection.",
        ErrorCode.BROWSER_NAVIGATION_ERROR: "Failed to navigate to the requested page.",
        ErrorCode.BROWSER_ACTION_ERROR: "Browser action could not be completed.",
        ErrorCode.AGENT_TIMEOUT_ERROR: "The operation timed out. Please try again with a simpler request.",
        
        ErrorCode.SESSION_NOT_FOUND: "Session not found. Please start a new session.",
        ErrorCode.SESSION_EXPIRED: "Your session has expired. Please start a new session.",
        ErrorCode.TASK_CLASSIFICATION_ERROR: "Unable to understand your request. Please be more specific.",
        ErrorCode.TASK_EXECUTION_ERROR: "Failed to execute the requested task.",
        
        ErrorCode.SERVER_CONNECTION_ERROR: "Server connection failed. Please try again later.",
        ErrorCode.SERVICE_UNAVAILABLE: "Service is temporarily unavailable. Please try again later.",
        ErrorCode.RATE_LIMIT_EXCEEDED: "Too many requests. Please slow down and try again.",
        ErrorCode.RESOURCE_EXHAUSTED: "System resources are exhausted. Please try again later."
    }
    
    return messages.get(error_code, "An error occurred while processing your request.")

class ErrorMapper:
    """Maps common exceptions to standardized error codes and responses"""
    
    @staticmethod
    def map_exception_to_error_code(exception: Exception) -> ErrorCode:
        """Map Python exceptions to our standard error codes"""
        import asyncio
        from pydantic import ValidationError
        
        if isinstance(exception, ValidationError):
            return ErrorCode.VALIDATION_ERROR
        elif isinstance(exception, asyncio.TimeoutError):
            return ErrorCode.AGENT_TIMEOUT_ERROR
        elif isinstance(exception, ConnectionError):
            return ErrorCode.SERVER_CONNECTION_ERROR
        elif isinstance(exception, PermissionError):
            return ErrorCode.AUTHORIZATION_ERROR
        elif "browser" in str(exception).lower():
            return ErrorCode.BROWSER_ACTION_ERROR
        elif "session" in str(exception).lower():
            return ErrorCode.SESSION_NOT_FOUND
        else:
            return ErrorCode.UNKNOWN_ERROR
    
    @staticmethod
    def get_severity_for_exception(exception: Exception) -> ErrorSeverity:
        """Determine severity level based on exception type"""
        import asyncio
        from pydantic import ValidationError
        
        if isinstance(exception, (ConnectionError, OSError)):
            return ErrorSeverity.HIGH
        elif isinstance(exception, (ValidationError, ValueError)):
            return ErrorSeverity.LOW
        elif isinstance(exception, asyncio.TimeoutError):
            return ErrorSeverity.MEDIUM
        else:
            return ErrorSeverity.MEDIUM