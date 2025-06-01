import asyncio
import logging
import signal
import time
import sys
import atexit
import traceback
from typing import Dict, Any, List, Optional, Callable

logger = logging.getLogger("shutdown_manager")

class ShutdownManager:
    """
    Centralized manager for handling graceful application shutdown.
    
    This class provides methods to register shutdown handlers, cleanup resources,
    and ensure proper termination of processes and tasks.
    """
    
    def __init__(self):
        self.is_shutting_down = False
        self._mcp_processes = {}  # Reference to be filled later
        self._agent_manager = None  # Reference to be filled later
        self._session_manager = None  # Reference to be filled later
        self._registered_handlers = []
        
    def register_mcp_processes(self, processes_dict: Dict):
        """Register MCP processes to be terminated during shutdown"""
        self._mcp_processes = processes_dict
        
    def register_agent_manager(self, agent_manager):
        """Register agent manager for browser cleanup"""
        self._agent_manager = agent_manager
    
    def register_profile_manager(self, profile_manager):
        """Register profile manager for cleanup"""
        self._profile_manager = profile_manager
    
    def register_session_manager(self, session_manager):
        """Register session manager for session cleanup during shutdown"""
        self._session_manager = session_manager
        
    def register_shutdown_handler(self, handler: Callable):
        """Register additional shutdown handler"""
        if handler not in self._registered_handlers:
            self._registered_handlers.append(handler)
    
    def setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown"""
        try:
            loop = asyncio.get_event_loop()
            
            # Handle SIGINT and SIGTERM
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(
                        sig,
                        lambda s=sig: asyncio.create_task(
                            self.graceful_shutdown(signal.Signals(s).name)
                        )
                    )
                    logger.info(f"Registered signal handler for {signal.Signals(sig).name}")
                except NotImplementedError:
                    # Signal handlers not supported on this platform
                    logger.warning(f"Signal handlers not supported for {signal.Signals(sig).name}")
                except Exception as e:
                    logger.error(f"Error setting up signal handler for {signal.Signals(sig).name}: {e}")
        except Exception as e:
            logger.error(f"Failed to setup signal handlers: {e}")
    
    def register_exit_handler(self):
        """Register exit handler for interpreter shutdown"""
        atexit.register(self.exit_handler)
        logger.info("Registered Python exit handler")
        
    def exit_handler(self):
        """Handle cleanup when Python interpreter is exiting"""
        if self.is_shutting_down:
            return
            
        logger.info("Python interpreter exiting, cleaning up resources")
        self.is_shutting_down = True
        
        try:
            # Call registered handlers
            for handler in self._registered_handlers:
                try:
                    handler()
                except Exception as e:
                    logger.error(f"Error in custom exit handler: {e}")
            
            # Clean up processes
            if self._mcp_processes:
                for process_id, process in list(self._mcp_processes.items()):
                    try:
                        if process and process.poll() is None:
                            logger.info(f"Terminating process {process_id} at exit")
                            try:
                                process.terminate()
                                # Give it a brief moment to terminate
                                for _ in range(3):
                                    if process.poll() is not None:
                                        break
                                    time.sleep(0.1)
                                    
                                if process.poll() is None:
                                    logger.warning(f"Process {process_id} did not terminate, killing")
                                    process.kill()
                            except Exception as e:
                                logger.error(f"Error terminating process: {e}")
                    except Exception as e:
                        logger.error(f"Error handling process {process_id}: {e}")
            
            # Force cleanup Chrome processes synchronously 
            self._sync_cleanup_chrome_processes()
            
        except Exception as e:
            logger.error(f"Error in exit handler: {e}")
    
    async def graceful_shutdown(self, signal_name: Optional[str] = None):
        """Simplified shutdown logic"""
        if self.is_shutting_down:
            return
            
        self.is_shutting_down = True
        logger.info(f"Initiating shutdown{f' due to {signal_name}' if signal_name else ''}")
        
        try:
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            
            if tasks:
                for task in tasks:
                    task.cancel()
        except Exception:
            pass  
        
        if self._session_manager:
            try:
                await asyncio.wait_for(self._session_manager.shutdown(), timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass 
        
        if self._agent_manager:
            try:
                try:
                    await asyncio.wait_for(self._agent_manager.close_all_managers(), timeout=1.0)
                except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                    pass  
            except Exception:
                pass
        
        # Clean up profile manager
        if hasattr(self, '_profile_manager') and self._profile_manager:
            try:
                self._profile_manager.cleanup_all_profiles()
            except Exception as e:
                logger.error(f"Error cleaning up profiles: {e}")
        
        # Force cleanup remaining Chrome processes
        try:
            await self._force_cleanup_chrome_processes()
        except Exception as e:
            logger.error(f"Error in Chrome process cleanup: {e}")
        
        if self._mcp_processes:
            for process_id, process in list(self._mcp_processes.items()):
                try:
                    if process and process.poll() is None:
                        process.terminate()
                        
                        time.sleep(0.3)
                        if process.poll() is None:
                            process.kill()
                except Exception:
                    pass  
        
        try:
            import gc
            gc.collect()
        except Exception:
            pass
            
        logger.info("Shutdown complete")
    
    async def _force_cleanup_chrome_processes(self):
        """Force cleanup of all Chrome processes"""
        try:
            import psutil
            import os
            
            # Get current process
            current_pid = os.getpid()
            logger.info(f"Cleaning up Chrome processes spawned by PID {current_pid}")
            
            # Find all Chrome processes that might be related to our application
            chrome_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'ppid', 'cmdline']):
                try:
                    proc_info = proc.info
                    proc_name = proc_info['name'].lower() if proc_info['name'] else ""
                    
                    # Look for Chrome/Chromium processes
                    if any(chrome_name in proc_name for chrome_name in ['chrome', 'chromium']):
                        # Check if it's related to our Nova Act usage (look for typical Nova Act command line args)
                        cmdline = proc_info.get('cmdline', [])
                        if cmdline and any('--remote-debugging-port' in arg or '--user-data-dir' in arg for arg in cmdline):
                            chrome_processes.append(proc)
                            logger.info(f"Found Chrome process to cleanup: PID {proc_info['pid']} - {proc_name}")
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            if chrome_processes:
                logger.info(f"Force terminating {len(chrome_processes)} Chrome processes")
                
                # First, try to terminate gracefully
                for proc in chrome_processes:
                    try:
                        logger.info(f"Terminating Chrome process {proc.pid}")
                        proc.terminate()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                
                # Wait a bit for graceful termination
                await asyncio.sleep(2.0)
                
                # Then force kill any remaining processes
                for proc in chrome_processes:
                    try:
                        if proc.is_running():
                            logger.warning(f"Force killing Chrome process {proc.pid}")
                            proc.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                        
                logger.info("Chrome process cleanup completed")
            else:
                logger.info("No Chrome processes found to cleanup")
                
        except ImportError:
            logger.warning("psutil not available for Chrome process cleanup")
        except Exception as e:
            logger.error(f"Error in Chrome process cleanup: {e}")
    
    def _sync_cleanup_chrome_processes(self):
        """Synchronous version of Chrome process cleanup for exit handler"""
        try:
            import psutil
            import time
            
            logger.info("Synchronous Chrome process cleanup starting")
            
            # Find all Chrome processes that might be related to our application
            chrome_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'ppid', 'cmdline']):
                try:
                    proc_info = proc.info
                    proc_name = proc_info['name'].lower() if proc_info['name'] else ""
                    
                    # Look for Chrome/Chromium processes
                    if any(chrome_name in proc_name for chrome_name in ['chrome', 'chromium']):
                        # Check if it's related to our Nova Act usage (look for typical Nova Act command line args)
                        cmdline = proc_info.get('cmdline', [])
                        if cmdline and any('--remote-debugging-port' in arg or '--user-data-dir' in arg for arg in cmdline):
                            chrome_processes.append(proc)
                            logger.info(f"Found Chrome process to cleanup: PID {proc_info['pid']} - {proc_name}")
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            if chrome_processes:
                logger.info(f"Force terminating {len(chrome_processes)} Chrome processes")
                
                # First, try to terminate gracefully
                for proc in chrome_processes:
                    try:
                        logger.info(f"Terminating Chrome process {proc.pid}")
                        proc.terminate()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                
                # Wait a bit for graceful termination
                time.sleep(1.0)
                
                # Then force kill any remaining processes
                for proc in chrome_processes:
                    try:
                        if proc.is_running():
                            logger.warning(f"Force killing Chrome process {proc.pid}")
                            proc.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                        
                logger.info("Synchronous Chrome process cleanup completed")
            else:
                logger.info("No Chrome processes found to cleanup")
                
        except ImportError:
            logger.warning("psutil not available for Chrome process cleanup")
        except Exception as e:
            logger.error(f"Error in synchronous Chrome process cleanup: {e}")
    
    def force_cleanup(self):
        if self._mcp_processes:
            for process_id, process in list(self._mcp_processes.items()):
                try:
                    if process and process.poll() is None:
                        process.kill()
                except Exception:
                    pass  
        
        # Force cleanup Chrome processes
        self._sync_cleanup_chrome_processes()
        
        try:
            import gc
            gc.collect()
        except Exception:
            pass

# Singleton instance
shutdown_manager = ShutdownManager()