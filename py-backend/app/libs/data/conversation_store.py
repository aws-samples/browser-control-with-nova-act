import json
import logging
import time
import os
from pathlib import Path
import asyncio
from typing import Dict, List, Any, Optional

# Set up logger with more verbose level for debugging
logger = logging.getLogger("conversation_store")
logger.setLevel(logging.DEBUG)

class ConversationStore:
    """Interface for conversation storage implementations."""
    
    async def save(self, session_id: str, messages: List[Dict[str, Any]]) -> bool:
        """Save conversation for a session."""
        raise NotImplementedError("Subclass must implement save()")
        
    async def load(self, session_id: str) -> List[Dict[str, Any]]:
        """Load conversation for a session."""
        raise NotImplementedError("Subclass must implement load()")
        
    async def exists(self, session_id: str) -> bool:
        """Check if conversation exists for session."""
        raise NotImplementedError("Subclass must implement exists()")
        
    async def clear(self, session_id: str) -> bool:
        """Clear conversation for a session."""
        raise NotImplementedError("Subclass must implement clear()")


class MemoryConversationStore(ConversationStore):
    """In-memory implementation of conversation storage with TTL."""
    
    def __init__(self, ttl_seconds: int = 3600, cleanup_interval: int = 300):
        self.conversations = {}
        self.last_accessed = {}
        self.ttl_seconds = ttl_seconds
        self.cleanup_interval = cleanup_interval
        self._cleanup_task = None
        self._start_cleanup_task()
    
    def _start_cleanup_task(self):
        """Start background task to clean up expired conversations."""
        try:
            # Only create task if event loop is running
            loop = asyncio.get_running_loop()
            self._cleanup_task = loop.create_task(self._cleanup_loop())
        except RuntimeError:
            # No event loop running, skip cleanup task
            logger.debug("No event loop running, skipping cleanup task initialization")
    
    async def _cleanup_loop(self):
        """Periodically clean up expired conversations."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_expired()
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
    
    async def _cleanup_expired(self):
        """Remove expired conversation entries."""
        now = time.time()
        expired_sessions = []
        
        for session_id, last_accessed in self.last_accessed.items():
            if now - last_accessed > self.ttl_seconds:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            await self.clear(session_id)
            logger.info(f"Removed expired conversation for session: {session_id}")
    
    async def save(self, session_id: str, messages: List[Dict[str, Any]]) -> bool:
        """Save conversation for a session in memory."""
        try:
            msg_count = len(messages) if messages else 0
            self.conversations[session_id] = messages
            self.last_accessed[session_id] = time.time()
            return True
        except Exception as e:
            logger.error(f"Failed to save conversation for session {session_id}: {e}")
            return False
    
    async def load(self, session_id: str) -> List[Dict[str, Any]]:
        """Load conversation for a session from memory."""
        if session_id in self.conversations:
            self.last_accessed[session_id] = time.time()
            msg_count = len(self.conversations[session_id])
            return self.conversations[session_id]
        return []
    
    async def exists(self, session_id: str) -> bool:
        """Check if conversation exists for session in memory."""
        exists = session_id in self.conversations
        return exists
    
    async def clear(self, session_id: str) -> bool:
        """Clear conversation for a session from memory."""
        try:
            if session_id in self.conversations:
                del self.conversations[session_id]
            if session_id in self.last_accessed:
                del self.last_accessed[session_id]
            return True
        except Exception as e:
            logger.error(f"Failed to clear conversation for session {session_id}: {e}")
            return False
    
    async def shutdown(self):
        """Shutdown the conversation store and cleanup background tasks."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                logger.debug("Cleanup task cancelled successfully")


class FileConversationStore(ConversationStore):
    """File-based implementation of conversation storage."""
    
    def __init__(self, base_path: str = "./data/conversations", ttl_days: int = 7, cleanup_interval: int = 3600):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_days * 24 * 3600
        self.cleanup_interval = cleanup_interval
        self._start_cleanup_task()
    
    def _start_cleanup_task(self):
        """Start background task to clean up old conversation files."""
        asyncio.create_task(self._cleanup_loop())
    
    async def _cleanup_loop(self):
        """Periodically clean up old conversation files."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_old_files()
            except Exception as e:
                logger.error(f"Error in file cleanup task: {e}")
    
    async def _cleanup_old_files(self):
        """Remove conversation files older than TTL."""
        now = time.time()
        try:
            for file_path in self.base_path.glob("*.json"):
                if file_path.is_file():
                    file_mtime = file_path.stat().st_mtime
                    if now - file_mtime > self.ttl_seconds:
                        file_path.unlink()
                        logger.info(f"Removed expired conversation file: {file_path.name}")
        except Exception as e:
            logger.error(f"Error cleaning up old conversation files: {e}")
    
    def _get_session_path(self, session_id: str) -> Path:
        return self.base_path / f"{session_id}.json"
    
    async def save(self, session_id: str, messages: List[Dict[str, Any]]) -> bool:
        """Save conversation for a session to file."""
        try:
            path = self._get_session_path(session_id)
            msg_count = len(messages) if messages else 0
                        
            with open(path, 'w') as f:
                json.dump(messages, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save conversation to file for session {session_id}: {e}")
            return False
    
    async def load(self, session_id: str) -> List[Dict[str, Any]]:
        """Load conversation for a session from file."""
        path = self._get_session_path(session_id)
        if not path.exists():
            return []
        
        try:
            with open(path, 'r') as f:
                messages = json.load(f)
                msg_count = len(messages) if messages else 0                        
                return messages
        except Exception as e:
            logger.error(f"Failed to load conversation from file for session {session_id}: {e}")
            return []
    
    async def exists(self, session_id: str) -> bool:
        """Check if conversation exists for session in file system."""
        path = self._get_session_path(session_id)
        exists = path.exists()
        return exists
    
    async def clear(self, session_id: str) -> bool:
        """Clear conversation for a session by removing its file."""
        try:
            path = self._get_session_path(session_id)
            if path.exists():
                path.unlink()
            return True
        except Exception as e:
            logger.error(f"Failed to clear conversation file for session {session_id}: {e}")
            return False

default_conversation_store = MemoryConversationStore()