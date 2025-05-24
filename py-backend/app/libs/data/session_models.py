from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, List, Optional
import uuid


class SessionState(Enum):
    """Session state enumeration"""
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"


@dataclass
class SessionData:
    """Session data model"""
    id: str
    created_at: datetime
    last_accessed: datetime
    expires_at: datetime
    state: SessionState = SessionState.ACTIVE
    metadata: Dict[str, Any] = field(default_factory=dict)
    resources: List[str] = field(default_factory=list)
    
    @classmethod
    def create_new(cls, session_id: Optional[str] = None, ttl_seconds: int = 3600) -> 'SessionData':
        """Create new session data"""
        now = datetime.utcnow()
        return cls(
            id=session_id or str(uuid.uuid4()),
            created_at=now,
            last_accessed=now,
            expires_at=now + timedelta(seconds=ttl_seconds)
        )
    
    def is_expired(self) -> bool:
        """Check if session is expired"""
        return datetime.utcnow() > self.expires_at or self.state == SessionState.EXPIRED
    
    def refresh(self, ttl_seconds: int = 3600) -> None:
        """Refresh session expiration"""
        now = datetime.utcnow()
        self.last_accessed = now
        self.expires_at = now + timedelta(seconds=ttl_seconds)
        if self.state == SessionState.EXPIRED:
            self.state = SessionState.ACTIVE
    
    def add_resource(self, resource_id: str) -> None:
        """Add resource to session"""
        if resource_id not in self.resources:
            self.resources.append(resource_id)
    
    def remove_resource(self, resource_id: str) -> None:
        """Remove resource from session"""
        if resource_id in self.resources:
            self.resources.remove(resource_id)
    
    def terminate(self) -> None:
        """Terminate session"""
        self.state = SessionState.TERMINATED
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "state": self.state.value,
            "metadata": self.metadata,
            "resources": self.resources
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionData':
        """Restore from dictionary"""
        return cls(
            id=data["id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            last_accessed=datetime.fromisoformat(data["last_accessed"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            state=SessionState(data["state"]),
            metadata=data.get("metadata", {}),
            resources=data.get("resources", [])
        )