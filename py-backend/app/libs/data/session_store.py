import json
import os
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Set
from datetime import datetime
import logging

from .session_models import SessionData, SessionState

logger = logging.getLogger(__name__)


class SessionStore(ABC):
    
    @abstractmethod
    async def get(self, session_id: str) -> Optional[SessionData]:
        pass
    
    @abstractmethod
    async def set(self, session_data: SessionData) -> bool:
        pass
    
    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        pass
    
    @abstractmethod
    async def list_active_sessions(self) -> List[str]:
        pass
    
    @abstractmethod
    async def cleanup_expired(self) -> int:
        pass


class MemorySessionStore(SessionStore):
    
    def __init__(self):
        self._sessions: Dict[str, SessionData] = {}
        self._lock = asyncio.Lock()
    
    async def get(self, session_id: str) -> Optional[SessionData]:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session and not session.is_expired():
                return session
            elif session and session.is_expired():
                del self._sessions[session_id]
            return None
    
    async def set(self, session_data: SessionData) -> bool:
        async with self._lock:
            self._sessions[session_data.id] = session_data
            return True
    
    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False
    
    async def list_active_sessions(self) -> List[str]:
        async with self._lock:
            return [
                session_id for session_id, session in self._sessions.items()
                if not session.is_expired()
            ]
    
    async def cleanup_expired(self) -> int:
        async with self._lock:
            expired_sessions = [
                session_id for session_id, session in self._sessions.items()
                if session.is_expired()
            ]
            
            for session_id in expired_sessions:
                del self._sessions[session_id]
            
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
            return len(expired_sessions)


class FileSessionStore(SessionStore):

    def __init__(self, storage_dir: str = "sessions"):
        self.storage_dir = storage_dir
        self._lock = asyncio.Lock()
        
        os.makedirs(storage_dir, exist_ok=True)
    
    def _get_session_file_path(self, session_id: str) -> str:
        return os.path.join(self.storage_dir, f"{session_id}.json")
    
    async def get(self, session_id: str) -> Optional[SessionData]:
        async with self._lock:
            file_path = self._get_session_file_path(session_id)
            
            if not os.path.exists(file_path):
                return None
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                session = SessionData.from_dict(data)
                
                if session.is_expired():
                    await self.delete(session_id)
                    return None
                
                return session
                
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.error(f"Error loading session {session_id}: {e}")
                await self.delete(session_id)
                return None
    
    async def set(self, session_data: SessionData) -> bool:
        async with self._lock:
            file_path = self._get_session_file_path(session_data.id)
            
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(session_data.to_dict(), f, indent=2)
                return True
                
            except (OSError, json.JSONEncodeError) as e:
                logger.error(f"Error saving session {session_data.id}: {e}")
                return False
    
    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            file_path = self._get_session_file_path(session_id)
            
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    return True
                return False
                
            except OSError as e:
                logger.error(f"Error deleting session {session_id}: {e}")
                return False
    
    async def list_active_sessions(self) -> List[str]:
        async with self._lock:
            active_sessions = []
            
            if not os.path.exists(self.storage_dir):
                return active_sessions
            
            for filename in os.listdir(self.storage_dir):
                if filename.endswith('.json'):
                    session_id = filename[:-5]
                    session = await self.get(session_id)
                    if session and not session.is_expired():
                        active_sessions.append(session_id)
            
            return active_sessions
    
    async def cleanup_expired(self) -> int:
        async with self._lock:
            cleanup_count = 0
            
            if not os.path.exists(self.storage_dir):
                return cleanup_count
            
            for filename in os.listdir(self.storage_dir):
                if filename.endswith('.json'):
                    session_id = filename[:-5]
                    file_path = self._get_session_file_path(session_id)
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        session = SessionData.from_dict(data)
                        
                        if session.is_expired():
                            os.remove(file_path)
                            cleanup_count += 1
                            
                    except (json.JSONDecodeError, KeyError, ValueError, OSError):
                        try:
                            os.remove(file_path)
                            cleanup_count += 1
                        except OSError:
                            pass
            
            logger.info(f"Cleaned up {cleanup_count} expired session files")
            return cleanup_count
