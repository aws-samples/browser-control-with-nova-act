from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.api_routes import thought_stream, router, mcp_servers
from app.libs.agent_manager import agent_manager
from app.libs.utils import PathManager, setup_paths, register_session_and_thought_handler
from app.libs.thought_stream import thought_handler
from app.libs.config import BROWSER_HEADLESS, BROWSER_USER_DATA_DIR

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
    level=logging.WARNING,
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

nova_act_instance = None

mcp_processes = {}

app.include_router(thought_stream.router, prefix="/api/assistant", tags=["Thought Stream"])
app.include_router(router.router, prefix="/api/router", tags=["Router"])
app.include_router(mcp_servers.router, prefix="/api/mcp-servers", tags=["MCP Servers"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.on_event("shutdown")
async def shutdown_event():
    global mcp_processes
    logger.info("Shutting down Nova Act Agent and all MCP servers...")

    try:
        await agent_manager.close_all()
        logger.info("Successfully closed all ActAgent instances")
    except Exception as e:
        logger.error(f"Error closing ActAgent instances: {str(e)}")
        logger.error(traceback.format_exc())

    for server_name, process in mcp_processes.items():
        if process and process.poll() is None: 
            try:
                logger.info(f"Terminating {server_name} MCP server")
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    logger.warning(f"{server_name} server didn't terminate gracefully, forcing...")
                    process.kill()
                    process.wait(timeout=1)
                logger.info(f"{server_name} server terminated")
            except Exception as e:
                logger.error(f"Error terminating {server_name} server: {str(e)}")
    
    mcp_processes = {}
    logger.info("Nova Act Agent and MCP servers shutdown complete")

@app.on_event("startup")
async def startup_event():
    global_session_id = "global-startup"
    try:
        logger.info("Initializing Nova Act Agent on server startup...")
        
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
            logger.info(f"Starting Nova Act Server from {server_path}")
            
            global mcp_processes
            server_process = subprocess.Popen(
                [sys.executable, server_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, 
                bufsize=0,
                start_new_session=True  
            )
            
            mcp_processes["nova-act-server-main"] = server_process
            logger.info(f"Nova Act Server started with PID {server_process.pid}")
            
            await asyncio.sleep(1)
        except Exception as e:
            error_msg = f"Failed to start Nova Act Server: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            raise RuntimeError(error_msg)
        
        global nova_act_instance
        # Default values for model_id and region for the global agent
        nova_act_instance = await agent_manager.initialize_global_agent(
            server_path=paths["server_path"], 
            headless=BROWSER_HEADLESS,
            model_id=None,  
            region="us-west-2" 
        )
        
        logger.info("Nova Act Agent initialized and ready")
        
    except Exception as e:
        error_msg = f"Error initializing Nova Act Agent: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.app:app", host="0.0.0.0", port=8000, reload=True)
