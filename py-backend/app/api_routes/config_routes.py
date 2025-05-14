"""API routes for runtime configuration"""

from fastapi import APIRouter, Body, HTTPException, Response
from typing import Dict, Any, Optional
import logging
import importlib

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/api/config/browser")
async def get_browser_config():
    """Get the current browser configuration"""
    try:
        from app.libs.config import BROWSER_HEADLESS, BROWSER_MAX_STEPS, BROWSER_TIMEOUT
        
        return {
            "headless": BROWSER_HEADLESS,
            "max_steps": BROWSER_MAX_STEPS,
            "timeout": BROWSER_TIMEOUT
        }
    except Exception as e:
        logger.error(f"Error getting browser config: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting browser config: {str(e)}")

@router.post("/api/config/browser/headless")
async def set_browser_headless(headless: bool = Body(..., embed=True), session_id: str = Body(None, embed=True)):
    """Set the browser headless mode and restart browser with the same URL"""
    try:
        from app.libs.agent_manager import agent_manager
        from app.libs.task_executors import BaseTaskExecutor
        import app.libs.config
        
        # Get the current browser state (URL) before closing
        current_url = None
        browser_state = None
        
        if session_id:
            # Create a temporary executor to access browser state methods
            base_executor = BaseTaskExecutor("dummy_model", "us-west-2")
            browser_state = await base_executor.get_browser_state(session_id)
            
            if browser_state and browser_state.get("browser_initialized", False):
                current_url = browser_state.get("current_url")
                logger.info(f"Captured current URL before restart: {current_url}")
            
        # Close all browser instances
        await agent_manager.close_all()
        logger.info("All browser instances have been closed")
        
        # Update the headless mode setting
        app.libs.config.BROWSER_HEADLESS = headless
        importlib.reload(app.libs.config)
        logger.info(f"Browser headless mode set to: {headless}")
        
        # Return the current URL so frontend can navigate back if needed
        return {
            "success": True, 
            "headless": headless,
            "current_url": current_url,
            "browser_state": browser_state
        }
    except Exception as e:
        logger.error(f"Error setting browser headless mode: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error setting browser headless mode: {str(e)}")

@router.post("/api/browser/restore_session")
async def restore_browser_session(session_id: str = Body(..., embed=True), url: str = Body(..., embed=True)):
    """Restore a browser session by navigating to the specified URL"""
    try:
        from app.libs.agent_manager import agent_manager
        from app.libs.utils import setup_paths
        from app.libs.config import BROWSER_HEADLESS
        
        # Setup browser agent
        paths = setup_paths()
        server_path = paths["server_path"]
        
        # Get or create browser agent
        browser_agent = await agent_manager.get_or_create_browser_agent(
            session_id=session_id,
            server_path=server_path,
            headless=BROWSER_HEADLESS
        )
        
        # Navigate to URL
        result = await browser_agent.session.call_tool("navigate", {"url": url})
        response_data = browser_agent.parse_response(result.content[0].text)
        
        return {
            "success": True,
            "url": response_data.get("current_url", url),
            "page_title": response_data.get("page_title", "")
        }
    except Exception as e:
        logger.error(f"Error restoring browser session: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error restoring browser session: {str(e)}")

@router.post("/api/config/browser/max_steps")
async def set_browser_max_steps(max_steps: int = Body(..., embed=True)):
    """Set the maximum browser steps"""
    try:
        if max_steps < 1 or max_steps > 10:
            raise ValueError("max_steps must be between 1 and 10")
            
        import app.libs.config
        app.libs.config.BROWSER_MAX_STEPS = max_steps
        importlib.reload(app.libs.config)
        
        logger.info(f"Browser max_steps set to: {max_steps}")
        return {"success": True, "max_steps": max_steps}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error setting browser max_steps: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error setting browser max_steps: {str(e)}")

@router.post("/api/config/conversation/storage_type")
async def set_conversation_storage_type(storage_type: str = Body(..., embed=True)):
    """Change the conversation storage type (memory or file)"""
    try:
        if storage_type not in ["memory", "file"]:
            raise HTTPException(status_code=400, detail="Storage type must be 'memory' or 'file'")
        
        import app.libs.config
        current_type = app.libs.config.CONVERSATION_STORAGE_TYPE
        
        # Only apply change if different from current setting
        if storage_type != current_type:
            app.libs.config.CONVERSATION_STORAGE_TYPE = storage_type
            importlib.reload(app.libs.config)
            logger.info(f"Conversation storage type changed from {current_type} to {storage_type}")
            
            # Note: Requires server restart to take effect for existing conversation store
            # We're just updating the config value here
            
        return {
            "success": True,
            "storage_type": storage_type,
            "message": "Storage type updated. Server restart required for changes to take effect."
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error setting conversation storage type: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error setting conversation storage type: {str(e)}")

@router.post("/api/config/conversation/max_turns")
async def set_max_turns(agent_turns: Optional[int] = None, supervisor_turns: Optional[int] = None):
    """Set the maximum turns for conversation"""
    try:
        import app.libs.config
        
        if agent_turns is not None:
            if agent_turns < 1 or agent_turns > 20:
                raise ValueError("agent_turns must be between 1 and 20")
            app.libs.config.MAX_AGENT_TURNS = agent_turns
            
        if supervisor_turns is not None:
            if supervisor_turns < 1 or supervisor_turns > 10:
                raise ValueError("supervisor_turns must be between 1 and 10")
            app.libs.config.MAX_SUPERVISOR_TURNS = supervisor_turns
            
        importlib.reload(app.libs.config)
        
        return {
            "success": True, 
            "agent_turns": app.libs.config.MAX_AGENT_TURNS,
            "supervisor_turns": app.libs.config.MAX_SUPERVISOR_TURNS
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error setting max turns: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error setting max turns: {str(e)}")