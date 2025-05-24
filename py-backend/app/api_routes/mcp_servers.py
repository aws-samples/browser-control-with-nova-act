from fastapi import APIRouter, HTTPException, Body
from typing import List, Dict, Optional, Any
import json
import os
import logging
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

# Path to store server configuration
MCP_SERVER_CONFIG_PATH = "mcp_server_config.json"

# Model for server information
class MCPServer(BaseModel):
    id: str
    name: str
    hostname: str
    isActive: bool
    isConnected: Optional[bool] = None

class ServerTestRequest(BaseModel):
    hostname: str

# Initial default values
DEFAULT_SERVERS = [
    {
        "id": "default-mcp-1",
        "name": "MCP Server (Local)",
        "hostname": "localhost:8000",
        "isActive": True,
        "isConnected": True
    }
]

def load_server_config() -> List[Dict[str, Any]]:
    try:
        if os.path.exists(MCP_SERVER_CONFIG_PATH):
            with open(MCP_SERVER_CONFIG_PATH, "r") as f:
                return json.load(f)
        else:
            # Save default values if config file doesn't exist
            save_server_config(DEFAULT_SERVERS)
            return DEFAULT_SERVERS
    except Exception as e:
        logger.error("Error loading MCP server config", extra={"error": str(e)})
        return DEFAULT_SERVERS

def save_server_config(servers: List[Dict[str, Any]]) -> None:
    try:
        with open(MCP_SERVER_CONFIG_PATH, "w") as f:
            json.dump(servers, f, indent=2)
    except Exception as e:
        logger.error("Error saving MCP server config", extra={"error": str(e)})

@router.get("/", response_model=List[MCPServer])
async def get_mcp_servers():
    """Returns the currently configured MCP server list."""
    return load_server_config()

@router.post("/", response_model=List[MCPServer])
async def update_mcp_servers(servers: List[MCPServer] = Body(...)):
    """Updates the MCP server list."""
    server_data = [server.dict() for server in servers]
    save_server_config(server_data)
    return server_data

@router.post("/test", response_model=Dict[str, Any])
async def test_mcp_server(request: ServerTestRequest = Body(...)):
    """Tests connection to a specific MCP server."""
    import asyncio
    
    try:
        # Test server connection with 3 second timeout
        hostname = request.hostname
        if not hostname.startswith('http'):
            hostname = f"http://{hostname}"
            
        # Add a health endpoint if not present
        if not hostname.endswith('/health'):
            if hostname.endswith('/'):
                hostname = f"{hostname}health"
            else:
                hostname = f"{hostname}/health"
        
        async with asyncio.timeout(3):
            from httpx import AsyncClient
            async with AsyncClient() as client:
                response = await client.get(hostname)
                return {"success": response.status_code < 400}
    except Exception as e:
        logger.error("MCP server connection test failed", extra={"error": str(e), "hostname": hostname})
        return {"success": False, "error": str(e)}