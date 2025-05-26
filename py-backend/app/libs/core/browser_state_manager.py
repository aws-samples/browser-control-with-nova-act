import asyncio
import logging
import time
from typing import Dict, Any, Optional, Callable, List
from enum import Enum
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)

class BrowserStatus(Enum):
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    NAVIGATING = "navigating"
    ERROR = "error"
    CLOSING = "closing"
    CLOSED = "closed"

@dataclass
class BrowserState:
    session_id: str
    status: BrowserStatus = BrowserStatus.UNINITIALIZED
    current_url: str = ""
    page_title: str = ""
    last_updated: float = 0.0
    error_message: str = ""
    has_screenshot: bool = False
    initialization_time: Optional[float] = None
    is_headless: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            'status': self.status.value,
            'last_updated_iso': datetime.fromtimestamp(self.last_updated).isoformat(),
            'browser_initialized': self.status in [BrowserStatus.INITIALIZED, BrowserStatus.NAVIGATING],
            'has_active_session': self.status in [BrowserStatus.INITIALIZED, BrowserStatus.NAVIGATING]
        }

class BrowserStateManager:
    """
    Global singleton manager for tracking browser state across all sessions.
    Provides real-time state updates and efficient querying capabilities.
    """
    
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
            
        self._states: Dict[str, BrowserState] = {}
        self._event_callbacks: List[Callable[[str, BrowserState], None]] = []
        self._initialized = True
        logger.info("Browser State Manager initialized")
    
    # State Management Methods
    
    async def update_browser_state(
        self, 
        session_id: str, 
        status: BrowserStatus = None,
        current_url: str = None,
        page_title: str = None,
        error_message: str = None,
        has_screenshot: bool = None,
        is_headless: bool = None
    ) -> BrowserState:
        """Update browser state and notify callbacks"""
        async with self._lock:
            # Get or create state
            if session_id not in self._states:
                self._states[session_id] = BrowserState(session_id=session_id)
            
            state = self._states[session_id]
            
            # Update fields if provided
            if status is not None:
                state.status = status
                if status == BrowserStatus.INITIALIZED and state.initialization_time is None:
                    state.initialization_time = time.time()
            if current_url is not None:
                state.current_url = current_url
            if page_title is not None:
                state.page_title = page_title
            if error_message is not None:
                state.error_message = error_message
            if has_screenshot is not None:
                state.has_screenshot = has_screenshot
            if is_headless is not None:
                state.is_headless = is_headless
                
            state.last_updated = time.time()
            
            # Notify callbacks
            await self._notify_callbacks(session_id, state)
            
            return state
    
    def get_browser_state(self, session_id: str) -> Optional[BrowserState]:
        """Get current browser state for session"""
        return self._states.get(session_id)
    
    def get_all_states(self) -> Dict[str, BrowserState]:
        """Get all browser states"""
        return self._states.copy()
    
    def get_active_sessions(self) -> List[str]:
        """Get list of sessions with initialized browsers"""
        return [
            session_id for session_id, state in self._states.items()
            if state.status == BrowserStatus.INITIALIZED
        ]
    
    async def remove_session(self, session_id: str) -> bool:
        """Remove session from state tracking"""
        async with self._lock:
            if session_id in self._states:
                # Set to closed status first (without triggering callbacks to avoid recursion)
                state = self._states[session_id]
                state.status = BrowserStatus.CLOSED
                state.last_updated = __import__('time').time()
                
                # Remove from tracking
                del self._states[session_id]
                logger.info(f"Removed session {session_id} from browser state tracking")
                return True
            return False
    
    # Event System
    
    def add_event_callback(self, callback: Callable[[str, BrowserState], None]):
        """Add callback for browser state change events"""
        self._event_callbacks.append(callback)
        logger.info(f"Added browser state event callback: {callback.__name__}")
    
    def remove_event_callback(self, callback: Callable[[str, BrowserState], None]):
        """Remove event callback"""
        if callback in self._event_callbacks:
            self._event_callbacks.remove(callback)
            logger.info(f"Removed browser state event callback: {callback.__name__}")
    
    async def _notify_callbacks(self, session_id: str, state: BrowserState):
        """Notify all registered callbacks about state change"""
        for callback in self._event_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(session_id, state)
                else:
                    callback(session_id, state)
            except Exception as e:
                logger.error(f"Error in browser state callback {callback.__name__}: {e}")
    
    # Resource Manager Integration
    
    async def cleanup_resource(self, resource_id: str, session_id: str):
        """Cleanup resource callback for session manager"""
        if resource_id.startswith("browser:"):
            # First cleanup the browser manager
            try:
                from app.libs.core.agent_manager import get_agent_manager
                agent_manager = get_agent_manager()
                await agent_manager.cleanup_browser_manager(session_id)
            except Exception as e:
                logger.error(f"Error cleaning up browser manager for session {session_id}: {e}")
            
            # Then remove from state tracking
            await self.remove_session(session_id)
            logger.info(f"Cleaned up browser resource for session {session_id}")
    
    # Integration Methods
    
    async def initialize_from_agent_manager(self, agent_manager) -> None:
        """Initialize state from existing AgentManager browser managers"""
        try:
            for session_id, browser_manager in agent_manager._browser_managers.items():
                if hasattr(browser_manager, 'browser_initialized') and browser_manager.browser_initialized:
                    # Try to get current state
                    try:
                        from app.libs.core.browser_utils import BrowserUtils
                        browser_state = await BrowserUtils.get_browser_state(browser_manager)
                        await self.update_browser_state(
                            session_id=session_id,
                            status=BrowserStatus.INITIALIZED,
                            current_url=browser_state.get("current_url", ""),
                            page_title=browser_state.get("page_title", ""),
                            has_screenshot=bool(browser_state.get("screenshot"))
                        )
                    except Exception as e:
                        logger.warning(f"Could not get state for session {session_id}: {e}")
                        await self.update_browser_state(
                            session_id=session_id,
                            status=BrowserStatus.INITIALIZED
                        )
                else:
                    await self.update_browser_state(
                        session_id=session_id,
                        status=BrowserStatus.UNINITIALIZED
                    )
            logger.info(f"Initialized browser state manager with {len(self._states)} sessions")
        except Exception as e:
            logger.error(f"Error initializing browser state manager from agent manager: {e}")

# # Global instance
# _browser_state_manager = None

# def get_browser_state_manager() -> BrowserStateManager:
#     """Get or create the global browser state manager instance"""
#     global _browser_state_manager
#     if _browser_state_manager is None:
#         _browser_state_manager = BrowserStateManager()
#     return _browser_state_manager