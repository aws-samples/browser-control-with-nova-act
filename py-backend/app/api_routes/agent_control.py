from fastapi import APIRouter, HTTPException
from app.libs.core.agent_manager import get_agent_manager
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Status endpoint removed - status is now managed via ThoughtProcess events

@router.post("/agent/stop/{session_id}")
async def stop_agent(session_id: str):
    """Request to stop agent processing for session"""
    try:
        agent_manager = get_agent_manager()
        
        # Check if agent is currently processing
        if not agent_manager.is_agent_processing(session_id):
            raise HTTPException(
                status_code=400, 
                detail="No agent processing to stop for this session"
            )
        
        # Request stop
        success = agent_manager.request_agent_stop(session_id)
        
        if success:
            logger.info(f"Stop requested for agent in session {session_id}")
            return {
                "session_id": session_id,
                "status": "stop_requested",
                "message": "Agent stop has been requested"
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to request agent stop"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping agent for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))