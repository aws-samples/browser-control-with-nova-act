import asyncio
import logging
import time
from typing import Dict, Any, Callable

from app.act_agent.client.browser_manager import BrowserManager
from app.act_agent.client.agent_executor import AgentExecutor
from app.libs.core.browser_utils import BrowserUtils
from app.libs.core.browser_state_manager import BrowserStateManager, BrowserStatus
from app.libs.config.config import BROWSER_HEADLESS
from app.libs.data.session_manager import get_session_manager

logger = logging.getLogger(__name__)

class AgentManager:
    """
    Simplified agent manager that creates isolated agents per session.
    Removes complex global agent reuse to prevent session conflicts.
    """
    
    def __init__(self):
        self._browser_managers: Dict[str, BrowserManager] = {}
        self._session_urls: Dict[str, str] = {}
        self._cleanup_timeouts = 30.0  # Configurable timeout
        
        
        # Thread-safe stop flag management
        self._stop_flags: Dict[str, bool] = {}
        self._processing_lock = asyncio.Lock()
        
        # Get browser state manager instance
        self._browser_state_manager = BrowserStateManager()
        self._BrowserStatus = BrowserStatus
        
        # Register with session manager as resource manager - defer until event loop is available
        self._session_manager_registered = False
        
        # Add browser state change callback for logging
        self._browser_state_manager.add_event_callback(self._on_browser_state_change)
    
    def add_browser_state_callback(self, callback: Callable):
        """Add callback for browser state changes"""
        self._browser_state_manager.add_event_callback(callback)
    
    async def update_browser_state(self, session_id: str, status: BrowserStatus = None, 
                                  current_url: str = None, page_title: str = None,
                                  error_message: str = None, has_screenshot: bool = None,
                                  is_headless: bool = None):
        """Update browser state for a session - delegates to BrowserStateManager"""
        await self._browser_state_manager.update_browser_state(
            session_id=session_id,
            status=status,
            current_url=current_url,
            page_title=page_title,
            error_message=error_message,
            has_screenshot=has_screenshot,
            is_headless=is_headless
        )
                
    def get_browser_state(self, session_id: str):
        """Get browser state for a session - delegates to BrowserStateManager"""
        return self._browser_state_manager.get_browser_state(session_id)
        
    async def remove_browser_state(self, session_id: str):
        """Remove browser state for a session - delegates to BrowserStateManager"""
        await self._browser_state_manager.remove_session(session_id)
    
    async def take_control(self, session_id: str) -> bool:
        """Take manual control of browser by switching from headless to visible mode"""
        logger.info(f"Taking control of browser for session {session_id}")
        
        # Send initial callback with current screenshot
        try:
            from app.libs.utils.decorators import log_thought
            
            # Try to get current screenshot before switching
            screenshot_data = None
            try:
                browser_manager = self.get_browser_manager(session_id)
                if browser_manager and browser_manager.browser_initialized:
                    screenshot_result = await browser_manager.session.call_tool("take_screenshot", {})
                    screenshot_response = browser_manager.parse_response(screenshot_result.content[0].text)
                    if screenshot_response.get("status") == "success" and screenshot_response.get("screenshot"):
                        screenshot_data = screenshot_response["screenshot"]
            except Exception as screenshot_e:
                logger.warning(f"Failed to get initial screenshot for take control: {screenshot_e}")
            
            log_thought(
                session_id=session_id,
                type_name="user_control",
                category="user_control",
                node="User Control",
                content="Starting take control process - switching browser to visible mode",
                technical_details={"operation": "take_control", "step": "starting"},
                screenshot=screenshot_data
            )
        except Exception as e:
            logger.error(f"Error sending initial take control callback: {e}")
        
        try:
            # Get current URL before restarting
            current_url = None
            browser_manager = self.get_browser_manager(session_id)
            logger.info(f"Browser manager found: {browser_manager is not None}")
            if browser_manager:
                logger.info(f"Browser initialized: {browser_manager.browser_initialized}")
            
            if browser_manager and browser_manager.browser_initialized:
                try:
                    from app.libs.core.browser_utils import BrowserUtils
                    browser_state = await BrowserUtils.get_browser_state(browser_manager)
                    current_url = browser_state.get("current_url", "")
                    logger.info(f"Current URL before take control: {current_url}")
                    
                        
                except Exception as e:
                    logger.warning(f"Failed to get current URL: {e}")
            
            # Update browser state to non-headless
            await self.update_browser_state(
                session_id=session_id,
                is_headless=False
            )
            
            # Restart browser in non-headless mode with preserved state
            if browser_manager and browser_manager.browser_initialized:
                try:
                    logger.info(f"Restarting browser in visible mode for session {session_id}")
                    
                    
                    result = await browser_manager.session.call_tool("restart_browser", {
                        "headless": False, 
                        "url": current_url
                    })
                    response_data = browser_manager.parse_response(result.content[0].text)
                    
                    if response_data.get("status") == "success":
                        logger.info(f"Browser restarted in visible mode successfully")
                        
                        # Send success callback with screenshot
                        try:
                            from app.libs.utils.decorators import log_thought
                            
                            # Try to get screenshot
                            screenshot_data = None
                            try:
                                screenshot_result = await browser_manager.session.call_tool("take_screenshot", {})
                                screenshot_response = browser_manager.parse_response(screenshot_result.content[0].text)
                                if screenshot_response.get("status") == "success" and screenshot_response.get("screenshot"):
                                    screenshot_data = screenshot_response["screenshot"]
                            except Exception as screenshot_e:
                                logger.warning(f"Failed to get screenshot for take control callback: {screenshot_e}")
                            
                            log_thought(
                                session_id=session_id,
                                type_name="user_control",
                                category="user_control",
                                node="User Control",
                                content="✅ Take control completed successfully! Browser is now visible and ready for manual interaction.",
                                technical_details={"operation": "take_control", "step": "completed", "status": "success"},
                                screenshot=screenshot_data
                            )
                        except Exception as e:
                            logger.error(f"Error sending success callback: {e}")
                        
                        return True
                    else:
                        logger.error(f"Failed to restart browser in visible mode: {response_data.get('message', 'Unknown error')}")
                        
                        # Send failure callback
                        try:
                            from app.libs.utils.decorators import log_thought
                            log_thought(
                                session_id=session_id,
                                type_name="user_control",
                                category="user_control",
                                node="User Control",
                                content=f"❌ Take control failed: {response_data.get('message', 'Unknown error')}",
                                technical_details={"operation": "take_control", "step": "failed", "error": response_data.get('message', 'Unknown error')}
                            )
                        except Exception as e:
                            logger.error(f"Error sending failure callback: {e}")
                        
                        return False
                except Exception as e:
                    logger.error(f"Exception during browser restart to visible mode: {e}")
                    
                    # Send exception callback
                    try:
                        from app.libs.utils.decorators import log_thought
                        log_thought(
                            session_id=session_id,
                            type_name="user_control",
                            category="user_control",
                            node="User Control",
                            content=f"❌ Take control failed with exception: {str(e)}",
                            technical_details={"operation": "take_control", "step": "exception", "error": str(e)}
                        )
                    except Exception as cb_e:
                        logger.error(f"Error sending exception callback: {cb_e}")
                    
                    return False
            else:
                logger.warning(f"No active browser manager found for session {session_id}")
                
                # Send no browser manager callback
                try:
                    from app.libs.utils.decorators import log_thought
                    log_thought(
                        session_id=session_id,
                        type_name="user_control",
                        category="user_control",
                        node="User Control",
                        content="❌ Take control failed: No active browser session found",
                        technical_details={"operation": "take_control", "step": "no_browser", "error": "No active browser manager"}
                    )
                except Exception as e:
                    logger.error(f"Error sending no browser callback: {e}")
                
                return False
                
        except Exception as e:
            logger.error(f"Error taking control of browser for session {session_id}: {e}")
            
            # Send general error callback
            try:
                from app.libs.utils.decorators import log_thought
                log_thought(
                    session_id=session_id,
                    type_name="user_control",
                    category="user_control",
                    node="User Control",
                    content=f"❌ Take control failed with error: {str(e)}",
                    technical_details={"operation": "take_control", "step": "general_error", "error": str(e)}
                )
            except Exception as cb_e:
                logger.error(f"Error sending general error callback: {cb_e}")
            
            return False
    
    async def _on_browser_state_change(self, session_id: str, state):
        """Handle browser state changes for logging"""
        try:
            from app.libs.utils.decorators import log_thought
            
            # Only send callbacks for final/important states
            callback_states = [
                self._BrowserStatus.ERROR,
                self._BrowserStatus.CLOSED
            ]
            
            if state.status not in callback_states:
                return
            
            status_messages = {
                self._BrowserStatus.ERROR: f"Browser error: {state.error_message}",
                self._BrowserStatus.CLOSED: "Browser has been closed directly"
            }
            
            message = status_messages.get(state.status, f"Browser status: {state.status}")
            
            log_thought(
                session_id=session_id,
                type_name="others",
                category="browser_status", 
                node="Others",
                content=message,
                technical_details=state.to_dict()
            )
        except Exception as e:
            logger.error(f"Error in browser state change callback: {e}")
    
    async def _ensure_session_manager_registered(self):
        """Ensure session manager registration is done (called lazily)"""
        if not self._session_manager_registered:
            try:
                session_manager = get_session_manager()
                await session_manager.register_resource_manager("browser", self._browser_state_manager)
                logger.info("Registered BrowserStateManager as browser resource manager")
                self._session_manager_registered = True
            except Exception as e:
                logger.error(f"Failed to register browser state manager with session manager: {e}")
    
    async def _register_with_session_manager(self):
        """Register browser state manager as resource manager with session manager"""
        await self._ensure_session_manager_registered()
    
    async def cleanup_browser_manager(self, session_id: str):
        """Cleanup browser manager for session - called by browser state manager"""
        await self._cleanup_manager(session_id)
        
    async def get_or_create_browser_manager(
        self, 
        session_id: str, 
        server_path: str, 
        headless: bool = BROWSER_HEADLESS, 
        model_id: str = None, 
        region: str = None, 
        url: str = None
    ) -> BrowserManager:
        """
        Get existing browser manager for session or create a new isolated one.
        Each session gets its own browser manager to avoid conflicts.
        """
        # Ensure session manager is registered
        await self._ensure_session_manager_registered()
        
        # Validate session first
        session_manager = get_session_manager()
        session = await session_manager.validate_session(session_id)
        if not session:
            raise ValueError(f"Invalid session: {session_id}")
        # Return existing manager if available
        if session_id in self._browser_managers:
            logger.info(f"Reusing existing browser manager for session {session_id}")
            manager = self._browser_managers[session_id]
            
            # Verify manager is still functional
            if await self._is_manager_functional(manager):
                return manager
            else:
                logger.warn(f"Browser manager for session {session_id} is not functional, creating new one")
                await self._cleanup_manager(session_id)
        
        # Update state to initializing
        await self.update_browser_state(
            session_id, status=self._BrowserStatus.INITIALIZING
        )
        
        # Create new isolated browser manager
        logger.info(f"Creating new isolated browser manager for session {session_id}")
        
        try:
            server_config = {"session_id": session_id}
            if model_id:
                server_config["model_id"] = model_id
            if region:
                server_config["region"] = region
                
            browser_manager = BrowserManager(server_config=server_config)
            await browser_manager.connect_to_server(server_path)
            
            # Initialize with URL preference
            init_url = url or self._session_urls.get(session_id, "https://www.google.com")
            logger.info(f"Initializing browser for session {session_id} with URL: {init_url}")
        
            # Send browser initialization status callback
            from app.libs.utils.decorators import log_thought
            log_thought(
                session_id=session_id,
                type_name="others",
                category="initialization",
                node="Others",
                content="Initializing browser session, this may take a few moments...",
                technical_details={
                    "status": "initializing",
                    "url": init_url,
                    "headless": headless
                }
            )
            
            await browser_manager.initialize_browser(headless=headless, url=init_url)
            
            # Update state to initialized with URL
            await self.update_browser_state(
                session_id=session_id,
                status=self._BrowserStatus.INITIALIZED,
                current_url=init_url,
                is_headless=headless
            )
            
            # Send browser initialization complete callback
            log_thought(
                session_id=session_id,
                type_name="others", 
                category="initialization",
                node="Others",
                content="Browser initialization completed successfully",
                technical_details={
                    "status": "initialized",
                    "url": init_url,
                    "headless": headless
            }
            )
            
            # Register the new manager
            self._browser_managers[session_id] = browser_manager
            self._session_urls[session_id] = init_url
            
            # Register browser as a resource in session manager
            await session_manager.add_session_resource(session_id, f"browser:{session_id}")
            
            # Browser monitoring disabled to prevent thread conflicts
            
            return browser_manager
            
        except Exception as e:
            # Update state to error
            await self.update_browser_state(
                session_id=session_id,
                status=self._BrowserStatus.ERROR,
                error_message=str(e)
            )
            logger.error(f"Failed to create browser manager for session {session_id}: {e}")
            raise
    
    async def _is_manager_functional(self, manager: BrowserManager) -> bool:
        """Check if browser manager is still functional"""
        try:
            if not (manager.browser_initialized and manager.session):
                logger.debug("Browser manager not functional: not initialized or no session")
                return False
                
            # Quick health check with timeout
            state_task = BrowserUtils.get_browser_state(manager)
            browser_state = await asyncio.wait_for(state_task, timeout=5.0)
            
            # Check if browser is actually functional by validating URL
            current_url = browser_state.get("current_url", "")
            if not current_url or current_url.lower() in ["", "unknown", "error getting url"]:
                logger.debug(f"Browser manager not functional: invalid URL '{current_url}'")
                return False
                
            logger.debug(f"Browser manager functional with URL: {current_url}")
            return True
            
        except Exception as e:
            logger.debug(f"Browser manager health check failed: {e}")
            return False
    
    def get_agent_executor(self, browser_manager: BrowserManager) -> AgentExecutor:
        """Create agent executor for the browser manager"""
        return AgentExecutor(browser_manager)
    
    async def close_manager(self, session_id: str) -> bool:
        """Close and cleanup browser manager for session"""
        if session_id not in self._browser_managers:
            logger.debug(f"No browser manager found for session {session_id}")
            return False
        
        # Update state to closing
        await self.update_browser_state(
            session_id, status=self._BrowserStatus.CLOSING
        )
        
        # Remove resource from session manager
        session_manager = get_session_manager()
        await session_manager.remove_session_resource(session_id, f"browser:{session_id}")
            
        await self._cleanup_manager(session_id)
        
        # Remove browser state
        await self.remove_browser_state(session_id)
        
        return True
    
    async def _cleanup_manager(self, session_id: str):
        """Clean up browser manager resources with timeout protection"""
        if session_id not in self._browser_managers:
            return
            
        manager = self._browser_managers[session_id]
        
        try:
            # Save current URL for potential reuse
            if manager.browser_initialized and manager.session:
                try:
                    state_task = BrowserUtils.get_browser_state(manager)
                    browser_state = await asyncio.wait_for(state_task, timeout=1.0)
                    
                    if browser_state and browser_state.get("current_url"):
                        self._session_urls[session_id] = browser_state["current_url"]
                        
                except asyncio.TimeoutError:
                    logger.debug(f"Timeout getting browser state for session {session_id}")
                except Exception as e:
                    logger.debug(f"Error saving browser state for session {session_id}: {e}")
            
            # Cleanup manager with timeout
            if hasattr(manager, 'close') and callable(manager.close):
                cleanup_task = manager.close()
                await asyncio.wait_for(cleanup_task, timeout=self._cleanup_timeouts)
                
        except asyncio.TimeoutError:
            logger.warning(f"Browser manager cleanup timeout for session {session_id}")
        except Exception as e:
            logger.error(f"Error during browser manager cleanup for session {session_id}: {e}")
        finally:
            # Always remove from tracking
            self._browser_managers.pop(session_id, None)
            # Update state to closed
            await self.update_browser_state(
                session_id, status=self._BrowserStatus.CLOSED
            )
    
    async def close_all_managers(self):
        """Close all browser managers - used for application shutdown"""
        logger.info("Closing all browser managers")
        
        # Get list of session IDs to avoid dictionary changed during iteration
        session_ids = list(self._browser_managers.keys())
        
        # Close all managers concurrently with timeout
        cleanup_tasks = [self._cleanup_manager(session_id) for session_id in session_ids]
        
        try:
            await asyncio.wait_for(
                asyncio.gather(*cleanup_tasks, return_exceptions=True),
                timeout=self._cleanup_timeouts
            )
        except asyncio.TimeoutError:
            logger.warning("Some browser managers failed to close within timeout")
        
        # Clear all tracking
        self._browser_managers.clear()
        self._session_urls.clear()
        
        logger.info("All browser managers closed")
    
    def get_active_session_count(self) -> int:
        """Get number of active browser sessions"""
        return len(self._browser_managers)
    
    def get_session_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about active sessions for monitoring"""
        info = {}
        for session_id, manager in self._browser_managers.items():
            info[session_id] = {
                "initialized": manager.browser_initialized if hasattr(manager, 'browser_initialized') else False,
                "has_session": bool(manager.session) if hasattr(manager, 'session') else False,
                "url": self._session_urls.get(session_id, "unknown")
            }
        return info
    
    def get_browser_manager(self, session_id: str):
        """Get browser manager for session (public interface)"""
        return self._browser_managers.get(session_id)
    
    def has_browser_manager(self, session_id: str) -> bool:
        """Check if browser manager exists for session"""
        return session_id in self._browser_managers
    
    # Agent processing state management methods removed - managed by frontend events
    
    async def request_agent_stop(self, session_id: str) -> bool:
        """Thread-safe request to stop agent processing for session"""
        async with self._processing_lock:
            # Always set stop flag - let the execution loop decide if it's valid
            self._stop_flags[session_id] = True
            logger.info(f"Stop requested for session {session_id}")
            return True
    
    def is_agent_stop_requested(self, session_id: str) -> bool:
        """Thread-safe check if agent stop is requested for session"""
        return self._stop_flags.get(session_id, False)
    
    def clear_stop_flag(self, session_id: str):
        """Clear stop flag for session (called when processing completes)"""
        self._stop_flags.pop(session_id, None)
    
    # get_agent_processing_info removed - status managed via ThoughtProcess events


# Global instance for convenience
_agent_manager_instance = None

def get_agent_manager() -> AgentManager:
    """Get or create the global agent manager instance"""
    global _agent_manager_instance
    
    if _agent_manager_instance is None:
        _agent_manager_instance = AgentManager()
    
    return _agent_manager_instance

def set_agent_manager(manager: AgentManager) -> None:
    """Set the global agent manager instance (for testing or custom initialization)"""
    global _agent_manager_instance
    _agent_manager_instance = manager

# Convenience alias
agent_manager = get_agent_manager()