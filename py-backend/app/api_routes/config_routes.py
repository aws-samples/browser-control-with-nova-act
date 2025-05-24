"""API routes for runtime configuration"""

from fastapi import APIRouter, Body, HTTPException, Response
from typing import Dict, Any, Optional
import logging
import importlib

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/config/browser")
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

@router.post("/config/browser/headless")
async def set_browser_headless(headless: bool = Body(..., embed=True), session_id: str = Body(None, embed=True)):
    """Set the browser headless mode and restart browser with the same URL"""
    try:
        from app.libs.agent_manager_instance import get_agent_manager
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
        await get_agent_manager().close_all_managers()
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

@router.post("/browser/restore_session")
async def restore_browser_session(session_id: str = Body(..., embed=True), url: str = Body(..., embed=True)):
    """Restore a browser session by navigating to the specified URL"""
    try:
        from app.libs.agent_manager_instance import get_agent_manager
        from app.libs.utils import setup_paths
        from app.libs.config import BROWSER_HEADLESS
        
        # Setup browser agent
        paths = setup_paths()
        server_path = paths["server_path"]
        
        # Get or create browser agent
        browser_manager = await get_agent_manager().get_or_create_browser_manager(
            session_id=session_id,
            server_path=server_path,
            headless=BROWSER_HEADLESS
        )
        
        # Navigate to URL
        result = await browser_manager.session.call_tool("navigate", {"url": url})
        response_data = browser_manager.parse_response(result.content[0].text)
        
        return {
            "success": True,
            "url": response_data.get("current_url", url),
            "page_title": response_data.get("page_title", "")
        }
    except Exception as e:
        logger.error(f"Error restoring browser session: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error restoring browser session: {str(e)}")

@router.post("/config/browser/max_steps")
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

@router.post("/config/conversation/storage_type")
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

@router.post("/config/conversation/max_turns")
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
    
@router.post("/browser/restart")
async def restart_browser(
    session_id: str = Body(..., embed=True),
    url: Optional[str] = Body(None, embed=True),
    preserve_url: bool = Body(True, embed=True),
    headless: Optional[bool] = Body(None, embed=True)
):
    """
    Restart the browser while optionally preserving the current URL.
    
    Parameters:
    - session_id: Session identifier
    - url: Optional URL to navigate to after restart
    - preserve_url: Whether to preserve current URL if no URL provided
    - headless: Optional headless mode override
    """
    try:
        from app.libs.agent_manager_instance import get_agent_manager
        from app.libs.utils import setup_paths
        from app.services.session_service import session_service
        from app.libs.decorators import log_thought
        
        # Setup paths
        paths = setup_paths()
        if not paths or "server_path" not in paths:
            raise HTTPException(status_code=500, detail="Server path not found")
        
        # Log restart operation
        if session_id:
            log_thought(
                session_id=session_id,
                type_name="processing",
                category="status",
                node="Browser",
                content=f"Restarting browser" + 
                        (f" with URL: {url}" if url else " with current URL" if preserve_url else "")
            )
        
        # Close existing agent and create new one (simulating restart)
        await get_agent_manager().close_manager(session_id)
        
        # Determine URL for new agent
        restart_url = url if url else (current_url if preserve_url and current_url else "https://www.google.com")
        
        # Create new agent
        browser_manager = await get_agent_manager().get_or_create_browser_manager(
            session_id=session_id,
            server_path=server_path,
            headless=headless,
            url=restart_url
        )
        
        result = {
            "success": True,
            "headless": headless,
            "current_url": restart_url,
            "browser_initialized": True
        }
        
        # Update session service browser initialization status
        if session_service:
            session_service.set_browser_initialized(
                session_id, 
                value=result.get("status") not in ["error", "failure"]
            )
        
        # Log the result
        if session_id:
            status = "success" if result.get("status") not in ["error", "failure"] else "error"
            log_thought(
                session_id=session_id,
                type_name="processing" if status == "success" else "error",
                category="status",
                node="Browser",
                content=f"Browser restart {status}: {result.get('message', '')}"
            )
        
        return {
            "status": "success" if result.get("status") not in ["error", "failure"] else "error",
            "message": result.get("message", "Browser restarted successfully"),
            "current_url": result.get("current_url", ""),
            "page_title": result.get("page_title", ""),
            "browser_initialized": result.get("status") not in ["error", "failure"]
        }
    except Exception as e:
        logger.error(f"Error restarting browser: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error restarting browser: {str(e)}")
