import os
import time
import random
import string
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger("utils")

class PathManager:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PathManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._initialized = True
            self.current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.project_root = os.path.abspath(os.path.join(self.current_dir, "../"))
            self.act_agent_dir = os.path.join(self.project_root, "app/act_agent")
            self.server_path = os.path.join(self.project_root, "app/act_agent/server/nova-act-server/nova_act_server.py")
            
            logger.info(f"PathManager initialized: project_root={self.project_root}")
            
    def get_paths(self) -> Dict[str, str]:
        return {
            "current_dir": self.current_dir,
            "project_root": self.project_root,
            "act_agent_dir": self.act_agent_dir,
            "server_path": self.server_path
        }

def get_or_create_session_id(session_id: Optional[str] = None, prefix: str = "session") -> str:
    if session_id:
        return session_id
        
    random_suffix = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(10))
    new_session_id = f"{prefix}-{int(time.time())}-{random_suffix}"
    logger.info(f"Created new session ID: {new_session_id}")
    return new_session_id

def register_session_and_thought_handler(session_id: str) -> str:
    from app.libs.thought_stream import thought_handler
    thought_handler.register_session(session_id)
    logger.info(f"Registered session in thought handler: {session_id}")
    return session_id

def setup_paths():
    import sys
    path_manager = PathManager()
    paths = path_manager.get_paths()
    
    for path_name in ["project_root", "act_agent_dir"]:
        path = paths.get(path_name)
        if path and path not in sys.path:
            sys.path.insert(0, path)
            logger.debug(f"Added {path_name} to sys.path: {path}")
    
    return paths
