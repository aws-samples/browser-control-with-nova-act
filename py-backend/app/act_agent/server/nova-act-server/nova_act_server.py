import os
import sys
import asyncio
import logging
import traceback
import json
import signal
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Any, Optional
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers
from browser_controller import BrowserController
from nova_act_config import DEFAULT_BROWSER_SETTINGS

# Session-based ThreadPools for Nova Act operations (recommended by Nova Act SDK)
_session_thread_pools = {}  # Dict[session_id, ThreadPoolExecutor]
_max_concurrent_browsers = 10  # Maximum concurrent browser sessions


# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Find .env file in py-backend directory
    env_path = Path(__file__).parent.parent.parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logging.info(f"Loaded .env from: {env_path}")
    else:
        logging.warning(f".env file not found at: {env_path}")
except ImportError:
    logging.warning("python-dotenv not available, skipping .env file loading")

logging.basicConfig(
    level=logging.DEBUG,
    format='[MCP] %(levelname)s - %(name)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("browser_mcp")
logger.setLevel(logging.DEBUG)

mcp = FastMCP("browser-automation", version="0.1.0")

# Multiple browser controllers for different sessions (HTTP mode)
_browser_controllers = {}  # Dict[session_id, BrowserController]
_shutdown_event = None
_is_shutting_down = False

def _nova_thread_initializer():
    """Initialize Nova Act thread with isolated asyncio context"""
    import asyncio
    try:
        # Remove any existing event loop
        asyncio.set_event_loop(None)
    except:
        pass
    
    try:
        # Create a fresh event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.debug("Nova Act thread initialized with fresh event loop")
    except Exception as e:
        logger.warning(f"Failed to initialize Nova Act thread: {e}")

def get_session_thread_pool(session_id: str) -> ThreadPoolExecutor:
    """Get or create a dedicated ThreadPoolExecutor for a specific session"""
    global _session_thread_pools
    
    if session_id not in _session_thread_pools:
        _session_thread_pools[session_id] = ThreadPoolExecutor(
            max_workers=1,  # Nova Act recommends single thread per session
            thread_name_prefix=f"nova-session-{session_id}-",
            initializer=_nova_thread_initializer
        )
        logger.info(f"Created dedicated ThreadPool for session {session_id}")
    
    return _session_thread_pools[session_id]

def shutdown_session_thread_pool(session_id: str):
    """Shutdown ThreadPoolExecutor for a specific session"""
    global _session_thread_pools
    
    if session_id in _session_thread_pools:
        executor = _session_thread_pools[session_id]
        executor.shutdown(wait=True)
        del _session_thread_pools[session_id]
        logger.info(f"Shut down ThreadPool for session {session_id}")

def shutdown_all_session_thread_pools():
    """Shutdown all session ThreadPoolExecutors"""
    global _session_thread_pools
    
    for session_id in list(_session_thread_pools.keys()):
        shutdown_session_thread_pool(session_id)
    
    _session_thread_pools.clear()
    logger.info("All session ThreadPools shut down")

async def run_in_session_thread(session_id: str, func, *args, **kwargs):
    """Execute function in dedicated session thread (Nova Act SDK recommended approach)"""
    executor = get_session_thread_pool(session_id)
    loop = asyncio.get_event_loop()
    
    def wrapper():
        return func(*args, **kwargs)
    
    logger.debug(f"Executing {func.__name__} in session {session_id} thread")
    return await loop.run_in_executor(executor, wrapper)

def format_log_response(response_data):
    if isinstance(response_data, dict):
        simplified = {
            "status": response_data.get("status", "unknown"),
            "message": response_data.get("message", "")
        }
        if "current_url" in response_data:
            simplified["current_url"] = response_data["current_url"]
        if "page_title" in response_data:
            simplified["page_title"] = response_data["page_title"]
        return json.dumps(simplified)
    return str(response_data)

def get_session_id_from_context() -> str:
    """Extract session ID from current context"""
    try:
        headers = get_http_headers()
        session_id = headers.get("x-session-id") or headers.get("X-Session-ID")
        if session_id:
            logger.debug(f"Got session ID from HTTP header: {session_id}")
            return session_id
        else:
            logger.warning(f"No session ID in headers. Available headers: {list(headers.keys())}")
    except Exception as e:
        logger.warning(f"Failed to get HTTP headers: {e}")
        # Not in HTTP context, try environment variable
        session_id = os.environ.get("BROWSER_SESSION_ID")
        if session_id:
            return session_id
    
    logger.warning("No session ID provided - using default session")
    return "default"

def get_browser_controller(session_id: str = None) -> BrowserController:
    global _browser_controllers
    
    if _is_shutting_down:
        return None
    
    # Get session_id from context if not provided
    if not session_id:
        session_id = get_session_id_from_context()
    
    # Create or get controller for this session
    if session_id not in _browser_controllers:
        logger.info(f"Creating new browser controller for session: {session_id}")
        _browser_controllers[session_id] = BrowserController(session_id=session_id)
    else:
        logger.debug(f"Reusing existing browser controller for session: {session_id}")
    
    return _browser_controllers[session_id]

def create_error_response(e: Exception, context: str) -> Dict[str, Any]:
    logger.error(f"Error in {context}: {str(e)}")
    return {
        "status": "error",
        "message": f"Failed to {context}: {str(e)}"
    }

@mcp.tool()
async def navigate(url: str) -> Dict[str, Any]:
    """
    Navigate browser to a specified URL.
    
    Args:
        url: Complete URL to navigate to (e.g., 'https://www.amazon.com' or 'https://www.google.com/search?q=shoes')
              URLs without protocol will automatically have 'https://' added
    """
    try:
        session_id = get_session_id_from_context()
        browser = get_browser_controller(session_id)
        
        if not await run_in_session_thread(session_id, browser.is_initialized):
            return {"status": "error", "message": "Browser not initialized"}
            
        result = await run_in_session_thread(session_id, browser.go_to_url, url)
        
        response = {
            "status": "success",
            "message": f"Navigated to {url}",
            "current_url": result["current_url"],
            "page_title": await run_in_session_thread(session_id, browser.get_page_title),
            "screenshot": result["screenshot"]
        }
        
        logger.info(f"Navigation result: {format_log_response(response)}")
        return response
    except Exception as e:
        return create_error_response(e, "navigate to URL")

@mcp.tool()
async def act(instruction: str, max_steps: Optional[int] = 2) -> Dict[str, Any]:
    """
    Execute browser actions using natural language instructions focused on visible elements.
    
    Args:
        instruction: Natural language description of what to do with CURRENTLY VISIBLE elements.
                   Be specific about visual characteristics like color, text, position, and size.
                   For scrolling, always specify where to hover first.
                   
                   Good examples:
                   - "Click the blue 'Sign Up' button in the top right corner"
                   - "Type 'hiking boots' into the search box with placeholder 'Search products'"
                   - "Hover over the results container, then scroll down to see 'Best Seller' button"
                   - "Click the 'State' dropdown, then type 'California'" (for long dropdowns)
        
        max_steps: (Optional) Maximum number of steps to execute (default: 2)
                  Use values >3 for multi-step actions like:
                  - Filling multiple form fields (max_steps=8)
                  - Extensive scrolling (max_steps=5)
                  - Sequential interactions (max_steps=2)
    """
    try:
        session_id = get_session_id_from_context()
        browser = get_browser_controller(session_id)
        
        if not await run_in_session_thread(session_id, browser.is_initialized):
            return {"status": "error", "message": "Browser not initialized"}
        
        max_steps = DEFAULT_BROWSER_SETTINGS.get("max_steps", 30)
        timeout = DEFAULT_BROWSER_SETTINGS.get("timeout", 300)
        
        result = await run_in_session_thread(
            session_id,
            browser.execute_action, 
            instruction,
            max_steps=max_steps, 
            timeout=timeout
        )
        
        screenshot_data = await run_in_session_thread(session_id, browser.take_screenshot)
        current_url = await run_in_session_thread(session_id, browser.get_current_url)
        page_title = await run_in_session_thread(session_id, browser.get_page_title)
        
        if hasattr(result, 'parsed_response') and result.parsed_response:
            return {
                "status": "success" if result.parsed_response.get("success", False) else "error",
                "message": result.parsed_response.get("details", "No details provided"),
                "instruction": instruction,
                "current_url": current_url,
                "page_title": page_title,
                "screenshot": {
                    **screenshot_data,
                    "url": current_url
                }
            }
        else:
            return {
                "status": "completed",
                "message": "Action completed",
                "instruction": instruction,
                "current_url": current_url,
                "page_title": page_title,
                "screenshot": {
                    **screenshot_data,
                    "url": current_url
                }
            }
    except Exception as e:
        error_str = str(e)
        screenshot_data = {}
        current_url = ""
        page_title = ""
        
        try:
            session_id = get_session_id_from_context()
            browser = get_browser_controller(session_id)
            if await run_in_session_thread(session_id, browser.is_initialized):
                screenshot_data = await run_in_session_thread(session_id, browser.take_screenshot)
                current_url = await run_in_session_thread(session_id, browser.get_current_url)
                page_title = await run_in_session_thread(session_id, browser.get_page_title)
        except:
            pass
            
        if "ActExceededMaxStepsError" in error_str:
            return {
                "status": "in_progress",
                "message": "I'm still analyzing the page to find what you're looking for. Here's what I see so far.",
                "technical_details": error_str,
                "instruction": instruction,
                "current_url": current_url,
                "page_title": page_title,
                "screenshot": {
                    **screenshot_data,
                    "url": current_url
                } if screenshot_data else {}
            }
        
        return create_error_response(e, f"perform action: {instruction}")

@mcp.tool()
async def extract(
    description: str,
    schema_type: str = "custom",
    custom_schema: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Extract data from the current page based on the provided description and schema.
    
    Args:
        description: Detailed description of the data to extract
        schema_type: Type of schema to use ('custom', 'product', 'search_result', 'form', 'navigation', 'bool')
        custom_schema: Custom JSON schema when schema_type is 'custom'
    """
    try:
        session_id = get_session_id_from_context()
        browser = get_browser_controller(session_id)
        
        if not await run_in_session_thread(session_id, browser.is_initialized):
            return {"status": "error", "message": "Browser not initialized"}
        
        schema = None
        if schema_type == "custom" and custom_schema:
            if isinstance(custom_schema, str):
                schema = json.loads(custom_schema)
            else:
                schema = custom_schema
        elif schema_type == "product":
            from schemas import ProductSchema
            schema = ProductSchema.model_json_schema()
        elif schema_type == "search_result":
            from schemas import SearchResultSchema
            schema = SearchResultSchema.model_json_schema()
        elif schema_type == "form":
            from schemas import FormFieldsSchema
            schema = FormFieldsSchema.model_json_schema()
        elif schema_type == "navigation":
            from schemas import NavigationSchema
            schema = NavigationSchema.model_json_schema()
        elif schema_type == "bool":
            from schemas import BoolSchema
            schema = BoolSchema.model_json_schema()
        else:
            return {
                "status": "error",
                "message": "Custom schema type requires 'custom_schema' parameter with a valid JSON schema"
            }
        
        prompt = f"{description} from the current webpage"
        
        max_steps = DEFAULT_BROWSER_SETTINGS.get("max_steps", 30)
        timeout = DEFAULT_BROWSER_SETTINGS.get("timeout", 300)
        
        result = await run_in_session_thread(
            session_id,
            browser.execute_action, 
            prompt, 
            schema=schema,
            max_steps=max_steps, 
            timeout=timeout
        )
        
        screenshot_data = await run_in_session_thread(session_id, browser.take_screenshot)
        current_url = await run_in_session_thread(session_id, browser.get_current_url)
        page_title = await run_in_session_thread(session_id, browser.get_page_title)
        
        if hasattr(result, 'parsed_response') and result.parsed_response:
            return {
                "status": "success",
                "data": result.parsed_response,
                "message": "Data extracted successfully",
                "schema_type": schema_type,
                "current_url": current_url,
                "page_title": page_title,
                "screenshot": {
                    **screenshot_data,
                    "url": current_url
                }
            }
        else:
            return {
                "status": "partial_success",
                "data": getattr(result, "response", {}),
                "message": "Data extraction completed but structured response not available",
                "schema_type": schema_type,
                "current_url": current_url,
                "page_title": page_title,
                "screenshot": {
                    **screenshot_data,
                    "url": current_url
                }
            }
    except Exception as e:
        return create_error_response(e, "extract data")


@mcp.tool()
async def initialize_browser(headless: bool = False, url: str = None) -> Dict[str, Any]:
    """
    Initialize or reset the browser with specified options. Use to start a fresh browser session.
    
    Args:
        headless: Whether to run the browser in headless mode (no visible UI)
        url: Optional starting URL for the browser session
    """
    try:
        # Get session ID from context
        session_id = get_session_id_from_context()
        browser = get_browser_controller(session_id)
        
        logger.info(f"Initializing browser for session {session_id} using dedicated ThreadPool")
        
        # Check if already initialized (using session thread)
        if await run_in_session_thread(session_id, browser.is_initialized):
            screenshot_data = await run_in_session_thread(session_id, browser.take_screenshot)
            
            response = {
                "status": "already_initialized",
                "message": "Browser was already initialized",
                "current_url": await run_in_session_thread(session_id, browser.get_current_url),
                "page_title": await run_in_session_thread(session_id, browser.get_page_title),
                "screenshot": screenshot_data
            }
            logger.info(f"Browser status: {format_log_response(response)}")
            return response
        
        # Initialize browser in session thread
        success, screenshot_data, error_msg = await run_in_session_thread(
            session_id,
            browser.initialize_browser,
            headless=headless,
            starting_url=url
        )
        
        if not success:
            detailed_error = error_msg or 'Unknown error'
            logger.error(f"Browser initialization failed for session {session_id}: {detailed_error}")
            return {
                "status": "error",
                "message": f"Failed to initialize browser: {detailed_error}"
            }
        
        # Get additional info from same session thread
        current_url = await run_in_session_thread(session_id, browser.get_current_url)
        page_title = await run_in_session_thread(session_id, browser.get_page_title)
        
        response = {
            "status": "success",
            "message": "Browser initialized successfully",
            "current_url": current_url,
            "page_title": page_title,
            "screenshot": screenshot_data
        }
        logger.info(f"Browser initialized: {format_log_response(response)}")
        return response
    except Exception as e:
        return create_error_response(e, "initialize browser")

@mcp.tool()
async def close_browser() -> Dict[str, Any]:
    """
    Close the browser and clean up resources.
    """
    try:
        session_id = get_session_id_from_context()
        browser = get_browser_controller(session_id)
        
        if not await run_in_session_thread(session_id, browser.is_initialized):
            return {
                "status": "not_initialized",
                "message": "Browser was not initialized"
            }

        success = await run_in_session_thread(session_id, browser.close)
        
        # Clean up session resources
        global _browser_controllers
        if browser.session_id in _browser_controllers:
            del _browser_controllers[browser.session_id]
        
        # Shutdown session ThreadPool
        shutdown_session_thread_pool(session_id)
        
        await asyncio.sleep(0.5)
        
        return {
            "status": "success" if success else "error",
            "message": "Browser closed successfully" if success else "Error closing browser"
        }
    except Exception as e:
        return create_error_response(e, "close browser")


@mcp.tool()
async def restart_browser(headless: bool = False, url: str = None):
    """Tool to restart the browser.
    
    Args:
        - headless (bool): Whether to start in headless mode
        - url (str): URL to navigate to after restarting
    
    Returns:
        dict: Status of the restart operation
    """
    try:
        await close_browser()
        return await initialize_browser(headless, url)
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to restart browser: {str(e)}"
        }

@mcp.tool()
async def take_screenshot(max_width: int = 800, quality: int = 70) -> Dict[str, Any]:
    """
    Take a screenshot of the current browser state.
    
    Args:
        max_width: Maximum width of the screenshot in pixels
        quality: JPEG quality (1-100)
    """
    try:
        session_id = get_session_id_from_context()
        browser = get_browser_controller(session_id)
        
        if not await run_in_session_thread(session_id, browser.is_initialized):
            return {
                "status": "error", 
                "message": "Browser not initialized",
                "screenshot": None
            }
            
        screenshot_data = await run_in_session_thread(session_id, browser.take_screenshot, max_width, quality)
        current_url = await run_in_session_thread(session_id, browser.get_current_url)
        page_title = await run_in_session_thread(session_id, browser.get_page_title)
        
        return {
            "status": "success",
            "message": "Screenshot captured successfully",
            "current_url": current_url,
            "page_title": page_title,
            "screenshot": screenshot_data
        }
    except Exception as e:
        logger.error(f"Error taking screenshot: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to take screenshot: {str(e)}",
            "screenshot": None
        }

def cleanup_resources_sync():
    """
    Comprehensive shutdown process - prevent resource leaks through reference cleanup
    """
    global _browser_controllers, _is_shutting_down
    _is_shutting_down = True
    
    if _browser_controllers:
        try:
            logger.info("Closing all browser resources...")
            
            # Close all session browser controllers
            for session_id, controller in list(_browser_controllers.items()):
                try:
                    if controller:
                        logger.info(f"Closing browser for session {session_id}")
                        controller.close()
                except Exception as e:
                    logger.error(f"Error closing browser for session {session_id}: {e}")
            
            # Clear all references
            _browser_controllers.clear()
            
            # Force terminate any remaining Chrome processes
            try:
                import psutil
                import os
                
                current_pid = os.getpid()
                parent_process = psutil.Process(current_pid)
                
                # Find all Chrome/Chromium child processes
                chrome_processes = []
                for child in parent_process.children(recursive=True):
                    try:
                        if child.name().lower() in ['chrome', 'chromium', 'google chrome']:
                            chrome_processes.append(child)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                
                if chrome_processes:
                    logger.info(f"Force terminating {len(chrome_processes)} remaining Chrome processes")
                    
                    # Terminate all Chrome processes
                    for proc in chrome_processes:
                        try:
                            logger.info(f"Terminating Chrome process {proc.pid}")
                            proc.terminate()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                    
                    # Wait and kill if still running
                    import time
                    time.sleep(1.0)
                    
                    for proc in chrome_processes:
                        try:
                            if proc.is_running():
                                logger.warning(f"Force killing Chrome process {proc.pid}")
                                proc.kill()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                            
            except ImportError:
                logger.warning("psutil not available for process cleanup")
            except Exception as e:
                logger.error(f"Error in process cleanup: {e}")
            
            # Shutdown all session ThreadPools
            shutdown_all_session_thread_pools()
            
            # Force garbage collection
            import gc
            gc.collect()
            
            logger.info("Resource cleanup completed")
        except Exception as e:
            # Log errors but continue shutdown process
            logger.error(f"Error during cleanup: {str(e)}")
    
    # Continue shutdown process

# Use ThreadPoolExecutor for timeout-safe shutdown
async def shutdown_server(timeout=5.0):
    """
    Gracefully shutdown the server and clean up resources with timeout
    """
    global _browser_controllers, _is_shutting_down, _shutdown_event
    import threading
    logger.info(f"Shutdown starting in thread ID: {threading.get_ident()}")

    if _is_shutting_down:
        logger.info("Shutdown already in progress, skipping")
        return
        
    logger.info(f"Starting graceful shutdown with {timeout}s timeout...")
    _is_shutting_down = True
    
    # First try to cancel all running tasks
    cancelled_tasks = 0
    try:
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        logger.info(f"Cancelling {len(tasks)} running tasks")
        
        for task in tasks:
            task.cancel()
            cancelled_tasks += 1
        
        # Give tasks some time to cancel
        if tasks:
            try:
                await asyncio.wait(tasks, timeout=min(2.0, timeout/2))
            except (asyncio.CancelledError, Exception):
                pass
    except Exception as e:
        logger.error(f"Error cancelling tasks: {str(e)}")
    
    logger.info(f"Cancelled {cancelled_tasks} tasks")
    
    # Now close all browsers
    if _browser_controllers:
        try:
            logger.info("Closing all browsers...")
            try:
                # First try to close all controllers directly
                for session_id, controller in list(_browser_controllers.items()):
                    try:
                        if controller and hasattr(controller, 'close'):
                            result = controller.close()
                            logger.info(f"Direct browser close result for {session_id}: {result}")
                    except Exception as direct_error:
                        logger.error(f"Direct browser close failed for {session_id}: {direct_error}")
                
                # Then try with executor as backup
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(cleanup_resources_sync)
                    try:
                        await asyncio.wait_for(
                            asyncio.wrap_future(future),
                            timeout=min(3.0, timeout * 0.6)  # Use shorter timeout for browser close
                        )
                    except (asyncio.TimeoutError, Exception) as e:
                        logger.warning(f"Browser close through executor had issues: {str(e)}")
            except Exception as close_error:
                logger.error(f"Error in browser close routine: {close_error}")
        finally:
            # Always clear all controller references
            _browser_controllers.clear()
    
    # Shutdown all session ThreadPools
    shutdown_all_session_thread_pools()
    
    # Set shutdown event
    if _shutdown_event:
        try:
            _shutdown_event.set()
        except Exception as e:
            logger.error(f"Error setting shutdown event: {e}")
    
    # Force garbage collection
    try:
        import gc
        gc.collect()
    except:
        pass
    
    logger.info("Shutdown completed")

def register_exit_handlers():
    def sync_signal_handler(signum, _):
        global _is_shutting_down
        if _is_shutting_down:
            logger.info("Already shutting down, ignoring signal")
            return
            
        logger.info(f"Received signal {signum}, cleaning up synchronously")
        _is_shutting_down = True
        
        cleanup_resources_sync()
        
        if signum == signal.SIGINT:
            logger.info("Exit due to SIGINT")
            sys.exit(130)  # 128 + 2 (SIGINT)
        elif signum == signal.SIGTERM:
            logger.info("Exit due to SIGTERM")
            sys.exit(143)  # 128 + 15 (SIGTERM)
    
    signal.signal(signal.SIGINT, sync_signal_handler)
    signal.signal(signal.SIGTERM, sync_signal_handler)

async def async_main(args):
    # Create shutdown event
    global _shutdown_event
    _shutdown_event = asyncio.Event()
    
    # Register synchronous cleanup handlers
    register_exit_handlers()
    
    # Set up asyncio signal handlers for graceful shutdown
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda _=sig: asyncio.create_task(
                    shutdown_server(timeout=1.0)
                )
            )
    except NotImplementedError:
        # Signal handlers not available on this platform (e.g., Windows)
        logger.warning("Asyncio signal handlers not available on this platform")
    except Exception as e:
        logger.error(f"Error setting up signal handlers: {str(e)}")
    
    try:
        logger.info("Starting MCP server...")
        if args.transport == "stdio":
            # Run in stdio mode with short timeout
            await asyncio.wait_for(
                mcp.run_async(transport="stdio"),
                timeout=None  # No timeout for the main task
            )
        else:
            # Run in HTTP mode with short timeout
            await asyncio.wait_for(
                mcp.run_async(transport="http", host=args.host, port=args.port),
                timeout=None  # No timeout for the main task
            )
    except asyncio.CancelledError:
        logger.info("MCP server operation cancelled")
    except asyncio.TimeoutError:
        logger.warning("MCP server startup timed out")
    except Exception as e:
        logger.error(f"Error running MCP server: {str(e)}")
        return 1
    finally:
        # Quick shutdown with very short timeout
        try:
            await asyncio.wait_for(shutdown_server(timeout=0.5), timeout=0.8)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            logger.info("Shutdown procedure timed out or was cancelled")
            cleanup_resources_sync()  # Fall back to sync cleanup
        except Exception as e:
            logger.error(f"Error during shutdown: {str(e)}")
            cleanup_resources_sync()  # Fall back to sync cleanup
    
    return 0

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Browser Automation MCP Server")
    parser.add_argument("--transport", type=str, default="streamable-http", choices=["stdio", "http", "streamable-http"],
                        help="Transport protocol (stdio, http, or streamable-http)")
    parser.add_argument("--host", type=str, default="localhost",
                        help="Host to bind to (for HTTP transport)")
    parser.add_argument("--port", type=int, default=8000,
                        help="Port to bind to (for HTTP transport)")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.INFO)
    
    # Use asyncio.run with very short timeout for the entire operation
    try:
        if args.transport == "streamable-http":
            # Use streamable HTTP transport (recommended for production)
            logger.info("Starting MCP server with Streamable HTTP transport...")
            mcp.run(transport="streamable-http", host=args.host, port=args.port)
        else:
            # Handle KeyboardInterrupt before it reaches asyncio.run()
            exit_code = asyncio.run(async_main(args))
            sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt detected")
        cleanup_resources_sync()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}")
        traceback.print_exc()
        cleanup_resources_sync()
        sys.exit(1)

if __name__ == "__main__":
    main()