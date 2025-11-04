from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api_routes import thought_stream, router, mcp_servers, browser_control, agent_control
from app.libs.utils.utils import setup_paths, register_session_and_thought_handler
from app.libs.config.config import BROWSER_USER_DATA_DIR
from app.libs.utils.shutdown_manager import shutdown_manager
from app.libs.core.agent_manager import get_agent_manager
from app.libs.data.session_manager import configure_session_manager

import logging
import sys
import os
import subprocess
import asyncio
from pathlib import Path
import traceback

log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / "app.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("app")
logging.getLogger('router_api').setLevel(logging.WARNING)
logging.getLogger('act_agent_api').setLevel(logging.WARNING)
logging.getLogger('thought_stream').setLevel(logging.WARNING)

app = FastAPI(title="Nova Act Agent API")

# Dictionary for tracking MCP processes - needs to be global
mcp_processes = {}

app.include_router(thought_stream.router, prefix="/api/assistant", tags=["Thought Stream"])
app.include_router(router.router, prefix="/api/router", tags=["Router"])
app.include_router(browser_control.router, prefix="/api/browser", tags=["Browser Control"])
app.include_router(mcp_servers.router, prefix="/api/mcp-servers", tags=["MCP Servers"])
app.include_router(agent_control.router, prefix="/api", tags=["Agent Control"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Enhanced health check that verifies Nova Act server"""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            # Test Nova Act server connectivity
            response = await client.head("http://localhost:8001/mcp", timeout=3.0)
            if response.status_code in [200, 405]:  # 405 = Method Not Allowed is OK
                return {
                    "status": "healthy", 
                    "service": "nova-act-main-app",
                    "mcp_server": "healthy"
                }
            else:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "unhealthy", 
                        "service": "nova-act-main-app",
                        "mcp_server": f"error_{response.status_code}"
                    }
                )
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": "nova-act-main-app", 
                "mcp_server": f"error_{str(e)}"
            }
        )

@app.api_route("/mcp", methods=["GET", "POST", "DELETE", "HEAD"])
async def proxy_mcp_to_nova_act(request: Request):
    """Proxy MCP requests to Nova Act server"""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=request.method,
                url="http://localhost:8001/mcp",
                headers=dict(request.headers),
                content=await request.body(),
                timeout=30.0
            )
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"error": f"MCP proxy error: {str(e)}"}
        )

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutting down - cleaning up resources...")
    try:
        await shutdown_manager.graceful_shutdown()
    except Exception as e:
        logger.error(f"Error during graceful shutdown: {e}")
        shutdown_manager.force_cleanup()

async def safe_shutdown():
    try:
        await asyncio.wait_for(get_agent_manager().close_all_managers(), timeout=3.0)
    except asyncio.TimeoutError:
        logger.warning("Agent manager close timed out")
    
    for process_id, process in list(mcp_processes.items()):
        try:
            if process and process.poll() is None:
                process.terminate()
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(process.wait), 
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"Process {process_id} termination timed out, killing")
                    process.kill()  
        except Exception as e:
            logger.error(f"Error terminating process {process_id}: {str(e)}")

@app.on_event("startup")
async def startup_event():
    global_session_id = "global-startup"
    try:
        logger.info("Initializing Nova Act Agent on server startup...")
        
        # Check and setup browser profile path configuration
        if BROWSER_USER_DATA_DIR == "/path/to/chromium/profile":
            logger.info("Browser profile path not configured. Creating default base directory.")
            default_base_dir = os.path.expanduser("~/.nova_browser_profiles/base")
            os.makedirs(default_base_dir, exist_ok=True)
            os.environ["NOVA_BROWSER_USER_DATA_DIR"] = default_base_dir
            logger.info(f"Created and set browser base profile directory: {default_base_dir}")
        else:
            # Ensure the configured directory exists
            os.makedirs(BROWSER_USER_DATA_DIR, exist_ok=True)
            logger.info(f"Using browser base profile directory: {BROWSER_USER_DATA_DIR}")
        
        # Configure session manager
        session_manager = configure_session_manager(
            store_type="file",  # Use file store for persistence
            ttl=7200,  # 2 hours default TTL
            storage_dir="./data/sessions"
        )
        logger.info("Session manager configured")
        
        # Initialize the shutdown manager with references
        shutdown_manager.register_mcp_processes(mcp_processes)
        shutdown_manager.register_agent_manager(get_agent_manager())
        shutdown_manager.register_session_manager(session_manager)
        
        # Register profile manager for cleanup
        from app.libs.utils.profile_manager import profile_manager
        shutdown_manager.register_profile_manager(profile_manager)
        
        # Setup signal handlers and exit handler
        shutdown_manager.setup_signal_handlers()
        shutdown_manager.register_exit_handler()
        
        paths = setup_paths()
        try:
            register_session_and_thought_handler(global_session_id)
        except Exception as reg_error:
            logger.error(f"Failed to register session: {reg_error}")
        
        if not os.path.exists(paths["server_path"]):
            error_msg = f"Server script not found at: {paths['server_path']}"
            logger.error(error_msg)
            return
        
        try:
            server_path = paths["server_path"]
            logger.info(f"Starting Nova Act Server (streamable HTTP) from {server_path}")
            
            # Start Nova Act server with streamable HTTP transport on port 8001
            server_process = subprocess.Popen(
                [sys.executable, server_path, "--transport", "streamable-http", "--port", "8001"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, 
                bufsize=0,
                start_new_session=True  
            )
            
            mcp_processes["nova-act-server-main"] = server_process
            logger.info(f"Nova Act Server (streamable HTTP) started with PID {server_process.pid}")
            
            # Wait a bit and check if server started successfully
            await asyncio.sleep(2)  
            
            # Check if process is still running
            if server_process.poll() is not None:
                # Process has terminated, read error output
                stdout, stderr = server_process.communicate()
                error_msg = f"Nova Act Server failed to start. Return code: {server_process.returncode}"
                if stderr:
                    error_msg += f"\nStderr: {stderr.decode()}"
                if stdout:
                    error_msg += f"\nStdout: {stdout.decode()}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            else:
                logger.info("Nova Act Server is running successfully")
        except Exception as e:
            error_msg = f"Failed to start Nova Act Server: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            raise RuntimeError(error_msg)
        
        logger.info("Nova Act Server started and ready for session-based agents")
        
    except Exception as e:
        error_msg = f"Error initializing Nova Act Agent: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.app:app", host="0.0.0.0", port=8000, reload=False)
