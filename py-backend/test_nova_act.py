#!/usr/bin/env python3

import asyncio
import json
from contextlib import AsyncExitStack
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def test_browser_initialization():
    """Test Nova Act browser initialization directly"""
    
    async with AsyncExitStack() as exit_stack:
        # Connect to Nova Act server with unique session ID
        import uuid
        session_id = f"test-session-{uuid.uuid4().hex[:8]}"
        headers = {"X-Session-ID": session_id}
        print(f"Using session ID: {session_id}")
        
        print("Connecting to Nova Act server...")
        transport = await exit_stack.enter_async_context(
            streamablehttp_client("http://localhost:8001/mcp/", headers=headers)
        )
        read_stream, write_stream, _ = transport
        session = await exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()
        
        print("Connected! Available tools:")
        response = await session.list_tools()
        for tool in response.tools:
            print(f"  - {tool.name}")
        
        print("\nTesting browser initialization...")
        try:
            # Test browser initialization
            result = await session.call_tool("initialize_browser", {
                "headless": True, 
                "url": "https://www.google.com"
            })
            
            print("Raw result:")
            print(json.dumps(result.content[0].text, indent=2))
            
            # Parse response
            try:
                response_data = json.loads(result.content[0].text)
                print(f"\nStatus: {response_data.get('status')}")
                print(f"Message: {response_data.get('message')}")
            except json.JSONDecodeError:
                print(f"Response: {result.content[0].text}")
                
        except Exception as e:
            print(f"Error during browser initialization: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_browser_initialization())