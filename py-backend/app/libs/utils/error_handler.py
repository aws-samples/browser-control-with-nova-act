import logging
import traceback
from typing import Dict, Any, Optional
from app.libs.utils.decorators import log_thought

logger = logging.getLogger("error_handler")

class ErrorHandler:
    """Centralized error handling for the application.
    
    This class provides consistent error logging and response formatting
    to avoid code duplication across the codebase.
    """
    
    @staticmethod
    def log_error(e: Exception, context: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Log an error with consistent formatting and return a standard error response."""
        error_message = f"Error in {context}: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        
        if session_id:
            log_thought(
                session_id=session_id,
                type_name="error",
                category="error",
                node="System",
                content=error_message
            )
        
        return {
            "status": "error",
            "error": str(e),
            "context": context
        }
    
    @staticmethod
    def format_user_error(error_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Format an error response suitable for end users with appropriate messaging."""
        user_friendly_message = "An error occurred while processing your request."
        
        context = error_dict.get("context", "")
        if "browser" in context.lower():
            user_friendly_message = "There was an issue with the browser operation. Please try again."
        elif "connect" in context.lower():
            user_friendly_message = "Could not connect to the required service. Please check your connection."
        elif "timeout" in str(error_dict.get("error", "")).lower():
            user_friendly_message = "The operation timed out. Please try again or try with a simpler request."
        
        return {
            "status": "error",
            "message": user_friendly_message,
            "technical_details": error_dict.get("error", "Unknown error")
        }
    
    @staticmethod
    def handle_conversation_error(e: Exception, session_id: str, conversation_store=None) -> Dict[str, Any]:
        """Handle errors in conversation flow and update conversation history if available."""
        error_dict = ErrorHandler.log_error(e, "conversation processing", session_id)
        
        # Try to update conversation history if store is available
        if conversation_store:
            try:
                error_response = {
                    "role": "assistant",
                    "content": [{"text": f"I'm sorry, an error occurred: {str(e)}"}]
                }
                conversation_store.save_message(session_id, error_response)
            except Exception as save_error:
                logger.error(f"Failed to save error to conversation: {save_error}")
        
        return ErrorHandler.format_user_error(error_dict)
    
    @staticmethod
    def handle_browser_error(e: Exception, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Handle browser-specific errors with appropriate error information."""
        error_dict = ErrorHandler.log_error(e, "browser operation", session_id)
        
        # Add screenshot if possible
        screenshot_data = None
        try:
            from app.libs.browser_utils import BrowserUtils
            from app.libs.agent_manager_instance import get_agent_manager
            
            agent_manager = get_agent_manager()
            if session_id in agent_manager._browser_managers:
                browser_manager = agent_manager._browser_managers[session_id]
                if browser_manager.browser_initialized and browser_manager.session:
                    # Attempt to capture screenshot of error state
                    screenshot_data = BrowserUtils.capture_screenshot_sync(browser_manager)
        except Exception:
            pass
        
        error_response = ErrorHandler.format_user_error(error_dict)
        
        if screenshot_data:
            error_response["screenshot"] = screenshot_data
            
        return error_response

# Singleton instance for easy import
error_handler = ErrorHandler()