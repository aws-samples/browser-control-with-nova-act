import asyncio
import logging
from typing import Dict, Any, Optional

from app.act_agent.client.browser_manager import BrowserManager
from app.act_agent.client.agent_executor import AgentExecutor
from app.libs.core.browser_utils import BrowserUtils
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
        
        # Register with session manager as resource manager
        asyncio.create_task(self._register_with_session_manager())
    
    async def _register_with_session_manager(self):
        """Register as resource manager with session manager"""
        try:
            session_manager = get_session_manager()
            await session_manager.register_resource_manager("browser", self)
            logger.info("Registered AgentManager as browser resource manager")
        except Exception as e:
            logger.error(f"Failed to register with session manager: {e}")
    
    async def cleanup_resource(self, resource_id: str, session_id: str):
        """Cleanup resource callback for session manager"""
        if resource_id.startswith("browser:"):
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
        
        # Create new isolated browser manager
        logger.info(f"Creating new isolated browser manager for session {session_id}")
        
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
            type_name="browser_status",
            category="initialization",
            node="Browser",
            content="Initializing browser session, this may take a few moments...",
            technical_details={
                "status": "initializing",
                "url": init_url,
                "headless": headless
            }
        )
        
        await browser_manager.initialize_browser(headless=headless, url=init_url)
        
        # Send browser initialization complete callback
        log_thought(
            session_id=session_id,
            type_name="browser_status", 
            category="initialization",
            node="Browser",
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
        
        return browser_manager
    
    async def _is_manager_functional(self, manager: BrowserManager) -> bool:
        """Check if browser manager is still functional"""
        try:
            if not (manager.browser_initialized and manager.session):
                return False
                
            # Quick health check with timeout
            state_task = BrowserUtils.get_browser_state(manager)
            await asyncio.wait_for(state_task, timeout=2.0)
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
        
        # Remove resource from session manager
        session_manager = get_session_manager()
        await session_manager.remove_session_resource(session_id, f"browser:{session_id}")
            
        await self._cleanup_manager(session_id)
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