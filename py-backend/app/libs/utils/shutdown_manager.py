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
    
    def force_cleanup(self):
        if self._mcp_processes:
            for process_id, process in list(self._mcp_processes.items()):
                try:
                    if process and process.poll() is None:
                        process.kill()
                except Exception:
                    pass  
        
        try:
            import gc
            gc.collect()
        except Exception:
            pass

# Singleton instance
shutdown_manager = ShutdownManager()