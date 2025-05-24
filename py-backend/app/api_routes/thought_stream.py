from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from app.libs.utils.thought_stream import thought_handler
from app.libs.data.session_manager import get_session_manager
import logging

logger = logging.getLogger("thought_stream_api")

router = APIRouter()

@router.get("/thoughts/{session_id}")
async def stream_thoughts(session_id: str):
    """Stream thought processes for a specific session"""
    try:
        logger.info(f"SSE connection request for session: {session_id}")
        
        # Create session if it doesn't exist (simple prototype approach)
        session_manager = get_session_manager()
        await session_manager.get_or_create_session(session_id)
        logger.info(f"Session ready for SSE: {session_id}")
            
        # Register session in thought handler if needed
        if session_id not in thought_handler.queues:  
            logger.info(f"Registering valid session: {session_id}")
            thought_handler.register_session(session_id)
        else:
            logger.info(f"Valid session found with {thought_handler.queues[session_id].qsize()} thoughts queued") 
        
        return StreamingResponse(
            thought_handler.stream_generator(session_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET",
                "Access-Control-Allow-Headers": "Content-Type"
            }
        )
    except Exception as e:
        logger.error(f"Error setting up thought stream: {e}")
        raise HTTPException(status_code=500, detail=f"Error setting up thought stream: {str(e)}")
