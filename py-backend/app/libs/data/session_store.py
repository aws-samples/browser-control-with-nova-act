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
    """세션 저장소 추상 인터페이스"""
    
    @abstractmethod
    async def get(self, session_id: str) -> Optional[SessionData]:
        """세션 데이터 조회"""
        pass
    
    @abstractmethod
    async def set(self, session_data: SessionData) -> bool:
        """세션 데이터 저장"""
        pass
    
    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """세션 데이터 삭제"""
        pass
    
    @abstractmethod
    async def list_active_sessions(self) -> List[str]:
        """활성 세션 ID 목록 반환"""
        pass
    
    @abstractmethod
    async def cleanup_expired(self) -> int:
        """만료된 세션 정리, 정리된 개수 반환"""
        pass


class MemorySessionStore(SessionStore):
    """메모리 기반 세션 저장소"""
    
    def __init__(self):
        self._sessions: Dict[str, SessionData] = {}
        self._lock = asyncio.Lock()
    
    async def get(self, session_id: str) -> Optional[SessionData]:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session and not session.is_expired():
                return session
            elif session and session.is_expired():
                # 만료된 세션 자동 제거
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
    """파일 기반 세션 저장소"""
    
    def __init__(self, storage_dir: str = "sessions"):
        self.storage_dir = storage_dir
        self._lock = asyncio.Lock()
        
        # 저장 디렉토리 생성
        os.makedirs(storage_dir, exist_ok=True)
    
    def _get_session_file_path(self, session_id: str) -> str:
        """세션 파일 경로 반환"""
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
                    # 만료된 세션 파일 삭제
                    await self.delete(session_id)
                    return None
                
                return session
                
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.error(f"Error loading session {session_id}: {e}")
                # 손상된 파일 삭제
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
                    session_id = filename[:-5]  # .json 제거
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
                        # 손상된 파일도 정리
                        try:
                            os.remove(file_path)
                            cleanup_count += 1
                        except OSError:
                            pass
            
            logger.info(f"Cleaned up {cleanup_count} expired session files")
            return cleanup_count


# Redis 세션 저장소 (선택적 구현)
try:
    import redis.asyncio as redis
    
    class RedisSessionStore(SessionStore):
        """Redis 기반 분산 세션 저장소"""
        
        def __init__(self, redis_url: str = "redis://localhost:6379", key_prefix: str = "session:"):
            self.redis_url = redis_url
            self.key_prefix = key_prefix
            self._redis: Optional[redis.Redis] = None
        
        async def _get_redis(self) -> redis.Redis:
            if self._redis is None:
                self._redis = redis.from_url(self.redis_url)
            return self._redis
        
        def _get_key(self, session_id: str) -> str:
            return f"{self.key_prefix}{session_id}"
        
        async def get(self, session_id: str) -> Optional[SessionData]:
            r = await self._get_redis()
            key = self._get_key(session_id)
            
            try:
                data = await r.get(key)
                if not data:
                    return None
                
                session_dict = json.loads(data)
                session = SessionData.from_dict(session_dict)
                
                if session.is_expired():
                    await self.delete(session_id)
                    return None
                
                return session
                
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.error(f"Error loading session {session_id} from Redis: {e}")
                await self.delete(session_id)
                return None
        
        async def set(self, session_data: SessionData) -> bool:
            r = await self._get_redis()
            key = self._get_key(session_data.id)
            
            try:
                data = json.dumps(session_data.to_dict())
                ttl = int((session_data.expires_at - datetime.utcnow()).total_seconds())
                
                if ttl > 0:
                    await r.setex(key, ttl, data)
                    return True
                else:
                    return False
                    
            except Exception as e:
                logger.error(f"Error saving session {session_data.id} to Redis: {e}")
                return False
        
        async def delete(self, session_id: str) -> bool:
            r = await self._get_redis()
            key = self._get_key(session_id)
            
            try:
                result = await r.delete(key)
                return result > 0
                
            except Exception as e:
                logger.error(f"Error deleting session {session_id} from Redis: {e}")
                return False
        
        async def list_active_sessions(self) -> List[str]:
            r = await self._get_redis()
            pattern = f"{self.key_prefix}*"
            
            try:
                keys = await r.keys(pattern)
                return [key.decode('utf-8')[len(self.key_prefix):] for key in keys]
                
            except Exception as e:
                logger.error(f"Error listing active sessions from Redis: {e}")
                return []
        
        async def cleanup_expired(self) -> int:
            # Redis는 TTL로 자동 만료되므로 명시적 정리 불필요
            return 0

except ImportError:
    logger.info("Redis not available, RedisSessionStore disabled")
    
    class RedisSessionStore:
        def __init__(self, *args, **kwargs):
            raise ImportError("Redis package not installed. Install with: pip install redis")