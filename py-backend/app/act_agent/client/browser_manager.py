import asyncio
import json
import logging
import os
import signal
import subprocess
import time
from contextlib import AsyncExitStack
from typing import Optional, Dict, Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger("browser_manager")

class BrowserManager:
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

    async def connect_to_server(self, server_url: str = None):
        """
        Connect to Nova Act server using streamable HTTP transport.
        
        Args:
            server_url: URL of the Nova Act server (e.g., 'http://localhost:8000/mcp/')
        """
        # Use default server URL if not provided
        if not server_url:
            server_url = "http://localhost:8001/mcp/"
        
        logger.info(f"Connecting to Nova Act server via streamable HTTP: {server_url}")
        
        # Initialize MCP client with streamable HTTP
        headers = {}
        if self.session_id:
            headers["X-Session-ID"] = self.session_id
            logger.info(f"Setting X-Session-ID header: {self.session_id}")
        
        transport = await self.exit_stack.enter_async_context(
            streamablehttp_client(server_url, headers=headers)
        )
        read_stream, write_stream, _ = transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        logger.info(f"Connected to server with tools: {[tool.name for tool in response.tools]}")

    def _terminate_server(self):
        """
        No server process termination needed for HTTP transport.
        The Nova Act server runs independently.
        """
        logger.info("HTTP transport - no server process to terminate")

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
                    # Force close session first
                    if hasattr(self.session, 'close'):
                        await self.session.close()
                except Exception as e:
                    print(f"Error closing session: {e}")
                
                try:
                    # Then close the exit stack
                    await self.exit_stack.aclose()
                except Exception as e:
                    print(f"Error closing MCP client: {e}")
                    # Try alternative cleanup
                    try:
                        self.exit_stack._async_cm_stack.clear()
                    except:
                        pass
        except Exception as e:
            print(f"Error closing browser: {e}")
        finally:
            self.browser_initialized = False
    
    async def close(self):
        """Close browser and cleanup resources - called by agent manager"""
        print(f"\nClosing browser manager for session {self.session_id}...")
        try:
            # Close browser first
            await self.close_browser()
            
            # Close MCP session
            if hasattr(self, 'exit_stack'):
                try:
                    await self.exit_stack.aclose()
                except Exception as e:
                    print(f"Error closing exit stack: {e}")
            
            # Terminate server process completely
            self._terminate_server()
            
            print(f"Browser manager closed for session {self.session_id}")
        except Exception as e:
            print(f"Error closing browser manager: {e}")

    async def initialize_browser(self, headless: bool = False, url: str = "https://www.google.com"):
        if not self.session:
            raise RuntimeError("Not connected to MCP server")
        
        # Check if we should preserve the current URL
        effective_url = url
        
        print(f"\nInitializing browser (headless: {headless}, url: {effective_url})...")
        result = await self.session.call_tool("initialize_browser", {"headless": headless, "url": effective_url})
        
        response_data = self.parse_response(result.content[0].text)
        self.initial_screenshot = None  # Will be captured when needed by agent
        
        # Update browser state with headless setting
        try:
            from app.libs.core.browser_state_manager import BrowserStateManager, BrowserStatus
            state_manager = BrowserStateManager()
            await state_manager.update_browser_state(
                session_id=self.session_id,
                status=BrowserStatus.INITIALIZED,
                is_headless=headless,
                current_url=effective_url
            )
        except Exception as e:
            print(f"Warning: Failed to update browser state: {e}")
        
        print(f"Browser initialized: {self.format_output(response_data)}")
        self.browser_initialized = True
        return response_data


    async def restart_browser(self, headless: bool = None, url: str = None, preserve_url: bool = True):
        """
        Restart browser while optionally preserving the current URL.
        
        Args:
            headless (bool, optional): Whether to run in headless mode
            url (str, optional): URL to navigate to after restart
            preserve_url (bool): Whether to preserve current URL if no url is provided
            
        Returns:
            dict: Status of the restart operation
        """
        if not self.session:
            raise RuntimeError("Not connected to MCP server")
        
        # Get current headless state if not specified
        current_headless = headless
        if current_headless is None:
            try:
                from app.libs.core.browser_state_manager import BrowserStateManager
                state_manager = BrowserStateManager()
                current_state = state_manager.get_browser_state(self.session_id)
                if current_state:
                    current_headless = current_state.is_headless
                else:
                    current_headless = False  # Default to non-headless if no state found
            except Exception as e:
                print(f"Error getting current headless state: {e}")
                current_headless = False
        
        # If we need to preserve the current URL and no URL was specified
        if preserve_url and url is None and self.browser_initialized:
            try:
                # Get the current browser state
                state_result = await self.session.call_tool("take_screenshot", {})
                browser_state = self.parse_response(state_result.content[0].text)
                current_url = browser_state.get("current_url", "")
                
                if current_url and current_url != "about:blank":
                    # Use current URL for restart
                    url = current_url
                    print(f"Will restart browser with current URL: {url}")
            except Exception as e:
                print(f"Error getting current URL for restart: {e}")
                # Continue with default URL
        
        print(f"\nRestarting browser (headless: {current_headless}, url: {url}, preserve_url: {preserve_url})...")
        try:
            result = await self.session.call_tool("restart_browser", {
                "headless": current_headless,
                "url": url
            })
            
            response_data = self.parse_response(result.content[0].text)
            
            # Update browser state with headless setting
            try:
                from app.libs.core.browser_state_manager import BrowserStateManager, BrowserStatus
                state_manager = BrowserStateManager()
                await state_manager.update_browser_state(
                    session_id=self.session_id,
                    status=BrowserStatus.INITIALIZED,
                    is_headless=current_headless,
                    current_url=url or ""
                )
            except Exception as e:
                print(f"Warning: Failed to update browser state: {e}")
                
            print(f"Browser restarted: {self.format_output(response_data)}")
            
            self.browser_initialized = True
            return response_data
        except Exception as e:
            print(f"Error restarting browser: {e}")
            self.browser_initialized = False
            return {
                "status": "error", 
                "message": f"Failed to restart browser: {str(e)}"
            }


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