import asyncio
import os
import json
from typing import Optional, Dict, Any
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import signal
import subprocess
import time
import logging

logger = logging.getLogger("browser_agent")
class BrowserAgent:
    def __init__(self, server_config=None):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.browser_initialized = False
        self.initial_screenshot = None
        self.server_config = server_config or {}
        self.session_id = self.server_config.get("session_id")
    
    def parse_response(self, response_text):
        if isinstance(response_text, str):
            try:
                return json.loads(response_text)
            except json.JSONDecodeError:
                return {"status": "unknown", "message": response_text}
        elif isinstance(response_text, dict):
            return response_text
        else:
            return {"status": "unknown", "message": str(response_text)}
    
    def format_output(self, data):
        if not isinstance(data, dict):
            return str(data)
            
        simplified = {
            "status": data.get("status", "unknown"),
            "message": data.get("message", "")
        }
        
        if "current_url" in data:
            simplified["current_url"] = data["current_url"]
        if "page_title" in data:
            simplified["page_title"] = data["page_title"]
            
        return json.dumps(simplified, indent=2)

    async def connect_to_server(self, server_script_path: str):
        env = os.environ.copy()
        if self.server_config:
            env["BROWSER_CONFIG"] = json.dumps(self.server_config)
        
        command = "python" if server_script_path.endswith('.py') else "node"
        server_params = StdioServerParameters(
            command=command, 
            args=[server_script_path], 
            env=env
        )
        
        # Start server process
        self._server_process = subprocess.Popen(
            [command, server_script_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            start_new_session=True 
        )
        
        # Register process with session ID instead of generated ID
        try:
            from app.app import mcp_processes
            
            # Use the provided session_id or fall back to generated ID
            server_id = self.server_config.get("session_id") or f"nova-act-server-{id(self)}"
            mcp_processes[server_id] = self._server_process
            logger.info(f"Registered server process with ID: {server_id}")
            
        except ImportError:
            import atexit
            atexit.register(self._terminate_server)

        # Initialize MCP client
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        logger.info(f"Connected to server with tools: {[tool.name for tool in response.tools]}")

    def _terminate_server(self):
        if not hasattr(self, '_server_process') or not self._server_process:
            return
            
        try:
            if self._server_process.poll() is not None:
                return  # Already terminated
                
            print("\nTerminating server process...")
            
            # Remove from global registry if applicable
            try:
                from app.app import mcp_processes
                
                server_id = None
                for sid, proc in list(mcp_processes.items()):
                    if proc == self._server_process:
                        server_id = sid
                        break
                        
                if server_id and server_id in mcp_processes:
                    print(f"Removing server process {server_id} from global registry")
                    del mcp_processes[server_id]
            except ImportError:
                pass
                
            # Unix-specific termination (handles process groups)
            if hasattr(os, 'killpg'):
                try:
                    pgid = os.getpgid(self._server_process.pid)
                    os.killpg(pgid, signal.SIGTERM)
                    
                    for i in range(10): 
                        if self._server_process.poll() is not None:
                            break 
                        time.sleep(0.1)
                            
                    if self._server_process.poll() is None:
                        os.killpg(pgid, signal.SIGKILL)
                            
                except (ProcessLookupError, PermissionError) as e:
                    print(f"Process already terminated: {e}")
            else:  # Windows
                self._server_process.terminate()
                
                try:
                    self._server_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    if self._server_process.poll() is None:
                        self._server_process.kill()
                        
            print("Server process terminated.")
        except Exception as e:
            print(f"Error terminating server process: {e}")
            import traceback
            traceback.print_exc()

    async def close_browser(self):
        if not self.session or not self.browser_initialized:
            return
        
        print("\nClosing browser...")
        try:
            result = await self.session.call_tool("close_browser", {})
            response_data = self.parse_response(result.content[0].text)
            print(f"Browser closed: {self.format_output(response_data)}")
            
            if hasattr(self, 'session'):
                try:
                    await self.exit_stack.aclose()
                except Exception as e:
                    print(f"Error closing MCP client: {e}")
        except Exception as e:
            print(f"Error closing browser: {e}")
        finally:
            self.browser_initialized = False

    async def initialize_browser(self, headless: bool = False, url: str = "https://www.google.com"):
        if not self.session:
            raise RuntimeError("Not connected to MCP server")
        
        # Check if we should preserve the current URL
        effective_url = url
        
        # if url == "https://www.google.com":
        #     try:
        #         if self.browser_initialized and self.session:
        #             status_result = await self.session.call_tool("get_browser_info", {})
        #             browser_info = self.parse_response(status_result.content[0].text)
        #             current_url = browser_info.get("current_url", "")
        #             if current_url:
        #                 effective_url = current_url
        #                 print(f"Preserving current browser URL: {current_url} (ignoring default URL)")
        #     except Exception as e:
        #         print(f"Error checking current URL: {e}")
        
        print(f"\nInitializing browser (headless: {headless}, url: {effective_url})...")
        result = await self.session.call_tool("initialize_browser", {"headless": headless, "url": effective_url})
        
        response_data = self.parse_response(result.content[0].text)
        self.initial_screenshot = None  # Will be captured when needed by agent
        
        print(f"Browser initialized: {self.format_output(response_data)}")
        self.browser_initialized = True
        return response_data

    async def cleanup(self):
        print("\nCleaning up resources...")
        
        try:
            await self.close_browser()
        except Exception as e:
            print(f"Error during browser cleanup: {e}")
        await asyncio.sleep(0.5)

        try:
            if hasattr(self, 'session') and self.session:
                await self.exit_stack.aclose()
        except Exception as e:
            print(f"Error closing MCP client: {e}")

        self._terminate_server()
        await asyncio.sleep(0.5)
        
        print("Cleanup complete.")