import uuid
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("session_service")

class SessionService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SessionService, cls).__new__(cls)
            cls._instance._sessions = {}
            cls._instance._initialize()
        return cls._instance
        
    def _initialize(self):
        logger.info("Session service initialized")
        
    def create_session(self) -> str:
        """Create a new session with UUID format"""
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = {
            "created_at": time.time(),
            "last_active": time.time(),
            "data": {},
            "browser_initialized": False
        }
        logger.info(f"Created new session: {session_id}")
        return session_id
        
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data if session exists"""
        if not session_id:
            return None
            
        if session_id in self._sessions:
            self._sessions[session_id]["last_active"] = time.time()
            return self._sessions[session_id]
        return None
        
    def store_session_data(self, session_id: str, key: str, value: Any) -> bool:
        """Store data in a session"""
        if session_id in self._sessions:
            self._sessions[session_id]["data"][key] = value
            return True
        return False
        
    def set_browser_initialized(self, session_id: str, value: bool = True) -> bool:
        """Mark a session as having an initialized browser"""
        if session_id in self._sessions:
            self._sessions[session_id]["browser_initialized"] = value
            return True
        return False
        
    def is_browser_initialized(self, session_id: str) -> bool:
        """Check if session has an initialized browser"""
        if session_id in self._sessions:
            return self._sessions[session_id].get("browser_initialized", False)
        return False

# Singleton instance
session_service = SessionService()
