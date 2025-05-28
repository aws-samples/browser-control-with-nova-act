from fastapi import APIRouter, HTTPException
from app.libs.core.agent_manager import get_agent_manager
import logging
import time

logger = logging.getLogger(__name__)

router = APIRouter()

# Status endpoint removed - status is now managed via ThoughtProcess events

@router.post("/agent/stop/{session_id}")
async def stop_agent(session_id: str):
    """Request to stop agent processing for session"""
    try:
        agent_manager = get_agent_manager()
        
        # Request stop (now async) - no pre-validation needed
        success = await agent_manager.request_agent_stop(session_id)
        
        if success:
            logger.info(f"Stop requested for agent in session {session_id}")
            
            # Send immediate callback that stop request was accepted
            # Use a dedicated event type that doesn't interfere with thinking state
            from app.libs.utils.decorators import log_thought
            log_thought(
                session_id=session_id,
                type_name="stop_notification",
                category="status",
                node="System",
                content="🛑 Stop request accepted - Agent will terminate gracefully",
                technical_details={
                    "stop_request_accepted": True,
                    "timestamp": time.time()
                }
            )
            
            return {
                "session_id": session_id,
                "status": "stop_requested", 
                "message": "Agent stop has been requested"
            }
        else:
            # No active processing found, but not an error
            logger.info(f"No active processing found for session {session_id}")
            return {
                "session_id": session_id,
                "status": "no_processing",
                "message": "No active processing to stop"
            }
            
    except Exception as e:
        logger.error(f"Error stopping agent for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))