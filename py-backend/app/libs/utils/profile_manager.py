import os
import shutil
import tempfile
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("profile_manager")

class ProfileManager:
    """Manages browser profile directories for session isolation"""
    
    def __init__(self):
        self.session_profiles: Dict[str, str] = {}
        self.temp_dir = Path(tempfile.gettempdir()) / "nova_browser_sessions"
        self.temp_dir.mkdir(exist_ok=True)
    
    def get_profile_for_session(self, session_id: str, base_profile_dir: str, clone_enabled: bool = True) -> str:
        """
        Get profile directory for a session
        
        Args:
            session_id: Unique session identifier
            base_profile_dir: Base profile directory to clone from
            clone_enabled: If True, clone to temporary directory. If False, use base directly
            
        Returns:
            Path to profile directory for this session
        """
        if not clone_enabled:
            logger.info(f"Session {session_id}: Using base profile directly (no cloning)")
            return base_profile_dir
        
        if session_id in self.session_profiles:
            existing_profile = self.session_profiles[session_id]
            if os.path.exists(existing_profile):
                logger.info(f"Session {session_id}: Reusing existing cloned profile: {existing_profile}")
                return existing_profile
            else:
                logger.warning(f"Session {session_id}: Cached profile path no longer exists, creating new one")
        
        # Create session-specific temporary profile directory
        session_profile_dir = self.temp_dir / f"session_{session_id}"
        
        try:
            # Remove existing directory if it exists
            if session_profile_dir.exists():
                shutil.rmtree(session_profile_dir, ignore_errors=True)
            
            # Clone base profile if it exists and has content
            if os.path.exists(base_profile_dir) and os.listdir(base_profile_dir):
                logger.info(f"Session {session_id}: Cloning base profile from {base_profile_dir}")
                shutil.copytree(base_profile_dir, session_profile_dir)
                logger.info(f"Session {session_id}: Profile cloned to {session_profile_dir}")
            else:
                # Create empty profile directory
                session_profile_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Session {session_id}: Created empty profile directory: {session_profile_dir}")
            
            # Cache the profile path
            self.session_profiles[session_id] = str(session_profile_dir)
            return str(session_profile_dir)
            
        except Exception as e:
            logger.error(f"Session {session_id}: Failed to create profile directory: {e}")
            # Fallback to a basic temp directory
            fallback_dir = self.temp_dir / f"fallback_{session_id}"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            self.session_profiles[session_id] = str(fallback_dir)
            return str(fallback_dir)
    
    def cleanup_session_profile(self, session_id: str) -> bool:
        """
        Clean up temporary profile directory for a session
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if cleanup successful, False otherwise
        """
        if session_id not in self.session_profiles:
            logger.debug(f"Session {session_id}: No profile to cleanup")
            return True
        
        profile_path = self.session_profiles[session_id]
        
        try:
            if os.path.exists(profile_path):
                shutil.rmtree(profile_path, ignore_errors=True)
                logger.info(f"Session {session_id}: Cleaned up profile directory: {profile_path}")
            
            del self.session_profiles[session_id]
            return True
            
        except Exception as e:
            logger.error(f"Session {session_id}: Failed to cleanup profile directory {profile_path}: {e}")
            return False
    
    def cleanup_all_profiles(self):
        """Clean up all temporary profile directories"""
        logger.info("Cleaning up all session profiles...")
        
        for session_id in list(self.session_profiles.keys()):
            self.cleanup_session_profile(session_id)
        
        # Clean up the main temp directory if empty
        try:
            if self.temp_dir.exists() and not any(self.temp_dir.iterdir()):
                self.temp_dir.rmdir()
                logger.info("Removed empty temporary profiles directory")
        except Exception as e:
            logger.warning(f"Failed to remove temporary profiles directory: {e}")
    
    def get_active_sessions(self) -> list:
        """Get list of active session IDs with profiles"""
        return list(self.session_profiles.keys())

# Global instance
profile_manager = ProfileManager()