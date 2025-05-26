# app/api_routes/router.py

from fastapi import APIRouter, Request, BackgroundTasks, HTTPException, Depends
import logging

from app.libs.utils.thought_stream import thought_handler
from app.libs.data.session_manager import get_session_manager
from app.libs.utils.decorators import with_thought_callback, log_thought
from app.libs.core.task_supervisor import TaskSupervisor
from app.libs.data.conversation_store import FileConversationStore, MemoryConversationStore
from app.libs.data.conversation_manager import ConversationManager
from app.libs.config.config import CONVERSATION_STORAGE_TYPE, CONVERSATION_FILE_TTL_DAYS, CONVERSATION_CLEANUP_INTERVAL
from app.libs.utils.error_responses import ErrorResponse, ErrorCode, ErrorSeverity, ErrorMapper
from pathlib import Path


# Set up logger with more verbose level for debugging
logger = logging.getLogger("router_api")
logger.setLevel(logging.DEBUG)
router = APIRouter()


# Initialize conversation storage based on configuration
if CONVERSATION_STORAGE_TYPE == "file":
    # Create a data directory for conversation storage
    data_dir = Path("./data/conversations")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a conversation store with file persistence
    conversation_store = FileConversationStore(
        str(data_dir), 
        ttl_days=CONVERSATION_FILE_TTL_DAYS, 
        cleanup_interval=CONVERSATION_CLEANUP_INTERVAL
    )
    logger.info(f"Using file-based conversation store at {data_dir} with {CONVERSATION_FILE_TTL_DAYS} days TTL")
else:
    # Create memory-based conversation store
    conversation_store = MemoryConversationStore()
    logger.info("Using memory-based conversation store")

# Create conversation manager
conversation_manager = ConversationManager(conversation_store)

# Import agent manager from instance module to avoid circular imports
from app.libs.core.agent_manager import get_agent_manager

# Singleton instance of TaskSupervisor shared across requests with persistent storage
task_supervisor = TaskSupervisor(conversation_store=conversation_store, agent_manager=get_agent_manager())

# Log application startup information
if CONVERSATION_STORAGE_TYPE == "file":
    logger.info(f"Router initialized with file conversation store at {data_dir}")
else:
    logger.info("Router initialized with memory-based conversation store")

@router.get("/health")
async def router_health_check():
    return {"status": "healthy", "message": "Router API is working"}

@router.get("/validate-session/{session_id}")
async def validate_session(session_id: str):
    """Validate if a session exists and is active"""
    try:
        session_manager = get_session_manager()
        session = await session_manager.validate_session(session_id)
        
        if session:
            return {
                "valid": True,
                "message": "Session is valid",
                "session_id": session_id,
                "expires_at": session.expires_at.isoformat()
            }
        else:
            return {
                "valid": False,
                "message": "Session not found or expired",
                "session_id": session_id
            }
    except Exception as e:
        logger.error(f"Error validating session {session_id}: {e}")
        return {
            "valid": False,
            "message": f"Validation error: {str(e)}",
            "session_id": session_id
        }



@router.post("/")
async def router_api(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
        
        # Extract request data with debugging
        messages = data.get("messages", [])
        model = data.get("model", "")
        region = data.get("region", "")
        
        # Session handling: validate existing or create new using new session manager
        session_manager = get_session_manager()
        input_session_id = data.get("session_id")
        session_data = await session_manager.get_or_create_session(input_session_id)
        session_id = session_data.id
        
        # Register session in thought handler
        thought_handler.register_session(session_id)
        
        if not messages or not isinstance(messages, list):
            logger.error(f"Invalid messages format: {messages}")
            raise HTTPException(status_code=400, detail="Messages are required and must be a non-empty array")
        
        # Extract the user message
        user_message = ""
        for i, msg in enumerate(reversed(messages)):
            if msg.get('role') == 'user':
                if isinstance(msg.get('content'), str):
                    user_message = msg.get('content')
                elif isinstance(msg.get('content'), list):
                    for content_item in msg.get('content', []):
                        if isinstance(content_item, dict) and 'text' in content_item:
                            user_message = content_item['text']
                            break
                break
        
        if not user_message:
            logger.error("No user message found in the request")
            raise HTTPException(status_code=400, detail="No user message found")
        
        background_tasks.add_task(
            process_request,
            message=user_message,
            session_id=session_id,
            model_id=model,
            region=region
        )
        
        return {
            "name": "session_initiated",
            "input": {
                "answering_tool": "task_supervisor",
                "direct_answer": "processing",
                "session_id": session_id
            }
        }
    
    except Exception as e:
        error_code = ErrorMapper.map_exception_to_error_code(e)
        severity = ErrorMapper.get_severity_for_exception(e)
        
        error_response = ErrorResponse.log_and_create_error(
            exception=e,
            error_code=error_code,
            context="router_api_processing",
            session_id=session_id,
            severity=severity
        )
        
        status_code = 500 if severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL] else 400
        raise HTTPException(status_code=status_code, detail=error_response)

@with_thought_callback(category="request_processing", node_name="process_request")
async def process_request(message: str, session_id: str, model_id: str = None, region: str = None):
    """Process requests through TaskSupervisor"""
    try:
        
        # Use the global task supervisor instance
        global task_supervisor
        
        # Process the request
        result = await task_supervisor.process_request(message, session_id, model_id, region)
        
        # Extract outcome data
        error = result.get("error", None)
                
        # Handle errors
        if error:
            log_thought(
                session_id=session_id,
                type_name="error",
                category="error",
                node="Router",
                content=f"Error during processing: {error}"
            )
        
        # No need for artificial delay at the end of processing
        
    except Exception as e:
        
        error_code = ErrorMapper.map_exception_to_error_code(e)
        severity = ErrorMapper.get_severity_for_exception(e)
        
        error_response = ErrorResponse.log_and_create_error(
            exception=e,
            error_code=error_code,
            context="task_processing",
            session_id=session_id,
            severity=severity
        )
        
        # Log error thought for user visibility
        log_thought(
            session_id=session_id,
            type_name="error",
            category="execution_error",
            node="TaskProcessor",
            content=f"Task processing failed: {error_response['message']}",
            error_dict=error_response
        )

@router.delete("/session/{session_id}")
async def terminate_session(session_id: str):
    """Terminate a session and clean up associated resources"""
    try:
        session_manager = get_session_manager()
        success = await session_manager.terminate_session(session_id)
        
        if success:
            logger.info(f"Session terminated successfully: {session_id}")
            return {"status": "success", "message": f"Session {session_id} terminated"}
        else:
            logger.warning(f"Session not found for termination: {session_id}")
            return {"status": "not_found", "message": f"Session {session_id} not found"}
            
    except Exception as e:
        logger.error(f"Error terminating session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to terminate session: {str(e)}")

@router.post("/session/{session_id}/terminate")
async def terminate_session_post(session_id: str):
    """Terminate a session via POST (for sendBeacon compatibility)"""
    try:
        session_manager = get_session_manager()
        success = await session_manager.terminate_session(session_id)
        
        if success:
            logger.info(f"Session terminated successfully via POST: {session_id}")
            return {"status": "success", "message": f"Session {session_id} terminated"}
        else:
            logger.warning(f"Session not found for termination via POST: {session_id}")
            return {"status": "not_found", "message": f"Session {session_id} not found"}
            
    except Exception as e:
        logger.error(f"Error terminating session {session_id} via POST: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to terminate session: {str(e)}")
        
