from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from app.libs.thought_stream import thought_handler
import logging
import asyncio

logger = logging.getLogger("thought_stream_api")

router = APIRouter()

@router.get("/thoughts/{session_id}")
async def stream_thoughts(session_id: str):
    """Stream thought processes for a specific session"""
    try:
        logger.info(f"SSE connection request for session: {session_id}")
        if session_id not in thought_handler.queues:  
            logger.warning(f"SSE connection attempt for unknown session: {session_id}")
            logger.info(f"Auto-registering session: {session_id}")
            thought_handler.register_session(session_id)
            logger.info(f"Session {session_id} registered successfully")
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
