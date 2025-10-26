"""
Browser cleanup utilities to prevent profile conflicts and process issues
"""
import os
import logging
import subprocess
from pathlib import Path
from typing import List

logger = logging.getLogger("browser_cleanup")

class BrowserCleanup:
    """Utilities for cleaning up browser processes and profiles"""
    
    @staticmethod
    def kill_nova_browser_processes() -> int:
        """
        Kill all Chrome/Chromium processes using Nova Act profiles
        
        Returns:
            Number of processes killed
        """
        killed_count = 0
        
        try:
            # Find processes using nova_browser_profiles
            result = subprocess.run(
                ["ps", "aux"], 
                capture_output=True, 
                text=True, 
                check=True
            )
            
            nova_processes = []
            for line in result.stdout.split('\n'):
                if 'nova_browser_profiles' in line and ('chrome' in line.lower() or 'chromium' in line.lower()):
                    parts = line.split()
                    if len(parts) > 1:
                        try:
                            pid = int(parts[1])
                            nova_processes.append(pid)
                        except ValueError:
                            continue
            
            # Kill the processes
            for pid in nova_processes:
                try:
                    os.kill(pid, 9)  # SIGKILL
                    killed_count += 1
                    logger.info(f"Killed Nova Act browser process: {pid}")
                except ProcessLookupError:
                    logger.debug(f"Process {pid} already terminated")
                except PermissionError:
                    logger.warning(f"Permission denied killing process {pid}")
                except Exception as e:
                    logger.error(f"Error killing process {pid}: {e}")
            
            if killed_count > 0:
                logger.info(f"Killed {killed_count} Nova Act browser processes")
            else:
                logger.debug("No Nova Act browser processes found to kill")
                
        except Exception as e:
            logger.error(f"Error finding Nova Act browser processes: {e}")
        
        return killed_count
    
    @staticmethod
    def remove_profile_locks(profile_base_dir: str = None) -> int:
        """
        Remove browser profile lock files
        
        Args:
            profile_base_dir: Base profile directory. If None, uses default
            
        Returns:
            Number of lock files removed
        """
        if profile_base_dir is None:
            profile_base_dir = os.path.expanduser("~/.nova_browser_profiles")
        
        removed_count = 0
        
        try:
            profile_path = Path(profile_base_dir)
            if not profile_path.exists():
                logger.debug(f"Profile directory does not exist: {profile_path}")
                return 0
            
            # Find and remove lock files
            lock_files = [
                "SingletonLock",
                "lockfile",
                ".lock"
            ]
            
            for lock_file in lock_files:
                for lock_path in profile_path.rglob(lock_file):
                    try:
                        lock_path.unlink()
                        removed_count += 1
                        logger.info(f"Removed lock file: {lock_path}")
                    except FileNotFoundError:
                        pass  # Already removed
                    except Exception as e:
                        logger.warning(f"Failed to remove lock file {lock_path}: {e}")
            
            if removed_count > 0:
                logger.info(f"Removed {removed_count} profile lock files")
            else:
                logger.debug("No profile lock files found to remove")
                
        except Exception as e:
            logger.error(f"Error removing profile locks: {e}")
        
        return removed_count
    
    @staticmethod
    def cleanup_temp_profiles() -> int:
        """
        Clean up temporary session profile directories
        
        Returns:
            Number of directories cleaned up
        """
        from app.libs.utils.profile_manager import profile_manager
        
        try:
            active_sessions = profile_manager.get_active_sessions()
            logger.info(f"Cleaning up {len(active_sessions)} temporary profiles")
            
            profile_manager.cleanup_all_profiles()
            return len(active_sessions)
            
        except Exception as e:
            logger.error(f"Error cleaning up temporary profiles: {e}")
            return 0
    
    @staticmethod
    def cleanup_session_browser(session_id: str) -> dict:
        """
        Clean up browser processes and profiles for a specific session only
        
        Args:
            session_id: Session identifier to clean up
            
        Returns:
            Dictionary with cleanup results
        """
        logger.info(f"Starting session-specific browser cleanup for: {session_id}")
        
        results = {
            "session_id": session_id,
            "processes_killed": 0,
            "locks_removed": 0,
            "session_profile_cleaned": False,
            "success": True,
            "errors": []
        }
        
        try:
            # Kill only browser processes for this specific session
            results["processes_killed"] = BrowserCleanup._kill_session_browser_processes(session_id)
            
            # Remove lock files only for this session's profile
            results["locks_removed"] = BrowserCleanup._remove_session_profile_locks(session_id)
            
            # Clean up only this session's temporary profile
            results["session_profile_cleaned"] = BrowserCleanup._cleanup_session_temp_profile(session_id)
            
            logger.info(f"Session cleanup completed for {session_id}: {results}")
            
        except Exception as e:
            results["success"] = False
            results["errors"].append(str(e))
            logger.error(f"Error during session cleanup for {session_id}: {e}")
        
        return results
    
    @staticmethod
    def _kill_session_browser_processes(session_id: str) -> int:
        """Kill browser processes for a specific session"""
        killed_count = 0
        
        try:
            # Find processes using this session's profile directory
            result = subprocess.run(
                ["ps", "aux"], 
                capture_output=True, 
                text=True, 
                check=True
            )
            
            session_processes = []
            session_profile_pattern = f"session_{session_id}"
            
            for line in result.stdout.split('\n'):
                if (session_profile_pattern in line and 
                    ('chrome' in line.lower() or 'chromium' in line.lower())):
                    parts = line.split()
                    if len(parts) > 1:
                        try:
                            pid = int(parts[1])
                            session_processes.append(pid)
                        except ValueError:
                            continue
            
            # Kill only this session's processes
            for pid in session_processes:
                try:
                    os.kill(pid, 9)  # SIGKILL
                    killed_count += 1
                    logger.info(f"Killed session {session_id} browser process: {pid}")
                except ProcessLookupError:
                    logger.debug(f"Process {pid} already terminated")
                except Exception as e:
                    logger.error(f"Error killing session process {pid}: {e}")
                    
        except Exception as e:
            logger.error(f"Error finding session browser processes for {session_id}: {e}")
        
        return killed_count
    
    @staticmethod
    def _remove_session_profile_locks(session_id: str) -> int:
        """Remove profile locks for a specific session"""
        removed_count = 0
        
        try:
            from app.libs.utils.profile_manager import profile_manager
            
            # Get the session's profile directory
            if session_id in profile_manager.session_profiles:
                session_profile_path = Path(profile_manager.session_profiles[session_id])
                
                if session_profile_path.exists():
                    lock_files = ["SingletonLock", "lockfile", ".lock"]
                    
                    for lock_file in lock_files:
                        for lock_path in session_profile_path.rglob(lock_file):
                            try:
                                lock_path.unlink()
                                removed_count += 1
                                logger.info(f"Removed session {session_id} lock file: {lock_path}")
                            except FileNotFoundError:
                                pass
                            except Exception as e:
                                logger.warning(f"Failed to remove session lock {lock_path}: {e}")
                                
        except Exception as e:
            logger.error(f"Error removing session profile locks for {session_id}: {e}")
        
        return removed_count
    
    @staticmethod
    def _cleanup_session_temp_profile(session_id: str) -> bool:
        """Clean up temporary profile for a specific session"""
        try:
            from app.libs.utils.profile_manager import profile_manager
            return profile_manager.cleanup_session_profile(session_id)
        except Exception as e:
            logger.error(f"Error cleaning up session temp profile for {session_id}: {e}")
            return False
    
    @staticmethod
    def full_cleanup(profile_base_dir: str = None) -> dict:
        """
        Perform complete browser cleanup
        
        Args:
            profile_base_dir: Base profile directory. If None, uses default
            
        Returns:
            Dictionary with cleanup results
        """
        logger.info("Starting full browser cleanup...")
        
        results = {
            "processes_killed": 0,
            "locks_removed": 0,
            "temp_profiles_cleaned": 0,
            "success": True,
            "errors": []
        }
        
        try:
            # Kill browser processes
            results["processes_killed"] = BrowserCleanup.kill_nova_browser_processes()
            
            # Remove lock files
            results["locks_removed"] = BrowserCleanup.remove_profile_locks(profile_base_dir)
            
            # Clean up temporary profiles
            results["temp_profiles_cleaned"] = BrowserCleanup.cleanup_temp_profiles()
            
            logger.info(f"Full cleanup completed: {results}")
            
        except Exception as e:
            results["success"] = False
            results["errors"].append(str(e))
            logger.error(f"Error during full cleanup: {e}")
        
        return results

# Convenience functions
def cleanup_session_browser(session_id: str):
    """Session-specific browser cleanup (RECOMMENDED)"""
    return BrowserCleanup.cleanup_session_browser(session_id)

def cleanup_browser_processes():
    """Quick cleanup of ALL browser processes (USE WITH CAUTION)"""
    return BrowserCleanup.kill_nova_browser_processes()

def cleanup_profile_locks():
    """Quick cleanup of profile locks"""
    return BrowserCleanup.remove_profile_locks()

def full_browser_cleanup():
    """Complete browser cleanup (USE WITH CAUTION - affects all sessions)"""
    return BrowserCleanup.full_cleanup()