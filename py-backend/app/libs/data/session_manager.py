import asyncio
import logging
from typing import Optional, List, Dict, Any, Set
from datetime import datetime, timedelta

from .session_models import SessionData, SessionState
from .session_store import SessionStore, MemorySessionStore

logger = logging.getLogger(__name__)


class SessionManager:
    
    def __init__(self, store: SessionStore, default_ttl: int = 3600):
        self.store = store
        self.default_ttl = default_ttl
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval = 300  
        self._resource_managers: Dict[str, Any] = {}
        
        self._start_cleanup_task()
    
    def _start_cleanup_task(self):
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
    
    async def _periodic_cleanup(self):
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self.cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")
    
    async def get_or_create_session(self, session_id: Optional[str] = None) -> SessionData:
        if session_id:
            session = await self.store.get(session_id)
            if session and not session.is_expired():
                session.refresh(self.default_ttl)
                await self.store.set(session)
                logger.info(f"Refreshed existing session: {session_id}")
                return session
            elif session and session.is_expired():
                await self._cleanup_session(session_id)
        
        session = SessionData.create_new(session_id, self.default_ttl)
        await self.store.set(session)
        logger.info(f"Created new session: {session.id}")
        return session
    
    async def validate_session(self, session_id: str) -> Optional[SessionData]:
        if not session_id:
            return None
        
        session = await self.store.get(session_id)
        if not session:
            logger.debug(f"Session not found: {session_id}")
            return None
        
        if session.is_expired():
            logger.debug(f"Session expired: {session_id}")
            await self._cleanup_session(session_id)
            return None
        
        if session.state != SessionState.ACTIVE:
            logger.debug(f"Session not active: {session_id} (state: {session.state})")
            return None
        
        session.refresh(self.default_ttl)
        await self.store.set(session)
        return session
    
    async def refresh_session(self, session_id: str, ttl: Optional[int] = None) -> bool:
        session = await self.store.get(session_id)
        if not session:
            return False
        
        session.refresh(ttl or self.default_ttl)
        return await self.store.set(session)
    
    async def terminate_session(self, session_id: str) -> bool:
        session = await self.store.get(session_id)
        if not session:
            return False
        
        session.terminate()
        await self.store.set(session)
        
        await self._cleanup_session(session_id)
        
        logger.info(f"Terminated session: {session_id}")
        return True
    
    async def get_session_data(self, session_id: str) -> Optional[SessionData]:
        return await self.store.get(session_id)
    
    async def update_session_metadata(self, session_id: str, metadata: Dict[str, Any]) -> bool:
        session = await self.store.get(session_id)
        if not session:
            return False
        
        session.metadata.update(metadata)
        session.refresh(self.default_ttl)
        return await self.store.set(session)
    
    async def add_session_resource(self, session_id: str, resource_id: str) -> bool:
        session = await self.store.get(session_id)
        if not session:
            return False
        
        session.add_resource(resource_id)
        return await self.store.set(session)
    
    async def remove_session_resource(self, session_id: str, resource_id: str) -> bool:
        session = await self.store.get(session_id)
        if not session:
            return False
        
        session.remove_resource(resource_id)
        return await self.store.set(session)
    
    async def register_resource_manager(self, resource_type: str, manager: Any):
        self._resource_managers[resource_type] = manager
    
    async def _cleanup_session(self, session_id: str):
        try:
            session = await self.store.get(session_id)
            if session and session.resources:
                cleanup_tasks = []
                for resource_id in session.resources:
                    for resource_type, manager in self._resource_managers.items():
                        if hasattr(manager, 'cleanup_resource'):
                            task = manager.cleanup_resource(resource_id, session_id)
                            cleanup_tasks.append(task)
                
                if cleanup_tasks:
                    await asyncio.gather(*cleanup_tasks, return_exceptions=True)
            
            await self.store.delete(session_id)
            
        except Exception as e:
            logger.error(f"Error cleaning up session {session_id}: {e}")
    
    async def cleanup_expired_sessions(self) -> int:
        try:
            cleanup_count = await self.store.cleanup_expired()
            if cleanup_count > 0:
                logger.info(f"Cleaned up {cleanup_count} expired sessions")
            return cleanup_count
        except Exception as e:
            logger.error(f"Error during session cleanup: {e}")
            return 0
    
    async def get_active_sessions(self) -> List[str]:
        return await self.store.list_active_sessions()
    
    async def get_session_stats(self) -> Dict[str, Any]:
        active_sessions = await self.get_active_sessions()
        return {
            "active_count": len(active_sessions),
            "sessions": active_sessions,
            "cleanup_interval": self._cleanup_interval,
            "default_ttl": self.default_ttl
        }
    
    async def shutdown(self):
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        active_sessions = await self.get_active_sessions()
        cleanup_tasks = [self._cleanup_session(session_id) for session_id in active_sessions]
        
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        
        logger.info("Session manager shut down")


_session_manager_instance: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _session_manager_instance
    
    if _session_manager_instance is None:
        store = MemorySessionStore()
        _session_manager_instance = SessionManager(store)
    
    return _session_manager_instance


def set_session_manager(manager: SessionManager):
    global _session_manager_instance
    _session_manager_instance = manager


def configure_session_manager(
    store_type: str = "memory",
    ttl: int = 3600,
    **store_kwargs
) -> SessionManager:
    from .session_store import MemorySessionStore, FileSessionStore
    
    if store_type == "memory":
        store = MemorySessionStore()
    elif store_type == "file":
        store = FileSessionStore(**store_kwargs)
    elif store_type == "redis":
        try:
            from .session_store import RedisSessionStore
            store = RedisSessionStore(**store_kwargs)
        except ImportError:
            logger.warning("Redis not available, falling back to memory store")
            store = MemorySessionStore()
    else:
        raise ValueError(f"Unknown store type: {store_type}")
    
    manager = SessionManager(store, ttl)
    set_session_manager(manager)
    
    logger.info(f"Configured session manager with {store_type} store (TTL: {ttl}s)")
    return manager