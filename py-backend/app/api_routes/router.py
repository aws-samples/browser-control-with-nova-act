# app/api_routes/router.py

from fastapi import APIRouter, Request, BackgroundTasks, HTTPException, Depends
import asyncio
import time
import logging
import traceback

from app.libs.thought_stream import thought_handler
from app.services.session_service import session_service
from app.libs.decorators import with_thought_callback, log_thought
from app.libs.task_supervisor import TaskSupervisor
from app.libs.conversation_store import FileConversationStore, MemoryConversationStore
from app.libs.conversation_manager import ConversationManager
from app.libs.config import CONVERSATION_STORAGE_TYPE, CONVERSATION_FILE_TTL_DAYS, CONVERSATION_CLEANUP_INTERVAL
from pathlib import Path

from app.api_routes.config_routes import router as config_router

# Set up logger with more verbose level for debugging
logger = logging.getLogger("router_api")
logger.setLevel(logging.DEBUG)
router = APIRouter()

# Include the configuration routes
router.include_router(config_router)

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

# Singleton instance of TaskSupervisor shared across requests with persistent storage
task_supervisor = TaskSupervisor(conversation_store=conversation_store)

# Log application startup information
if CONVERSATION_STORAGE_TYPE == "file":
    logger.info(f"Router initialized with file conversation store at {data_dir}")
else:
    logger.info("Router initialized with memory-based conversation store")

@router.get("/health")
async def router_health_check():
    return {"status": "healthy", "message": "Router API is working"}

@router.post("/")
async def router_api(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
        
        # Extract request data with debugging
        messages = data.get("messages", [])
        model = data.get("model", "")
        region = data.get("region", "")
        
        # Session handling: validate existing or create new
        input_session_id = data.get("session_id")
        if input_session_id and session_service.get_session(input_session_id):
            session_id = input_session_id
            logger.info(f"Using existing session: {session_id}")
        else:
            session_id = session_service.create_session()
            logger.info(f"Created new session: {session_id}")
        
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
        logger.error(f"Router API error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@with_thought_callback(category="request_processing", node_name="process_request")
async def process_request(message: str, session_id: str, model_id: str = None, region: str = None):
    """Process requests through TaskSupervisor"""
    try:
        
        # Use the global task supervisor instance
        global task_supervisor
        
        # Check if conversation exists before processing
        exists = await task_supervisor.conversation_store.exists(session_id)
        
        if exists:
            messages = await task_supervisor.conversation_store.load(session_id)
        
        # Process the request
        result = await task_supervisor.process_request(message, session_id, model_id, region)
        
        # Extract outcome data
        execution_type = result.get("type", "unknown")
        answer = result.get("answer", "")
        error = result.get("error", None)    
        
        # Check conversation after processing
        exists_after = await task_supervisor.conversation_store.exists(session_id)
        
        if exists_after:
            messages_after = await task_supervisor.conversation_store.load(session_id)
                
        # Handle errors
        if error:
            log_thought(
                session_id=session_id,
                type_name="error",
                category="error",
                node="Router",
                content=f"Error during {execution_type}: {error}"
            )
        
        # Final completion log
        if not error:
            log_thought(
                session_id=session_id,
                type_name="command_complete",
                category="completion",
                node="complete",
                content=f"Request completed via {execution_type}",
                command_id=f"req-{execution_type}-{int(time.time())}"
            )
        
        await asyncio.sleep(1)
        
    except Exception as e:
        error_message = f"Error processing request: {str(e)}"
        logger.error(error_message)
        logger.error(f"Exception details: {traceback.format_exc()}")
        
