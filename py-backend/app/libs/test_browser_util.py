#!/usr/bin/env python
import asyncio
import sys
import os
import json
import time

# Add project root to path to ensure imports work correctly
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))  # py-backend directory
sys.path.insert(0, project_root)

from app.libs.agent_manager import agent_manager
from app.libs.browser_utils import BrowserUtils

async def test_browser_utils():
    print("Starting BrowserUtils test...")
    
    # Nova Act server path - using correct path from your directory structure
    server_path = os.path.join(project_root, "app", "act_agent", "server", "nova-act-server", "nova_act_server.py")
    
    if not os.path.exists(server_path):
        print(f"ERROR: Server script not found at path: {server_path}")
        return
        
    print(f"Using server path: {server_path}")
    
    # Initialize browser agent
    print("\n1. Initializing browser agent...")
    try:
        browser_agent = await agent_manager.get_or_create_browser_agent(
            session_id="test-session",
            server_path=server_path,
            headless=True,
            url="https://www.amazon.com"  # Test with Amazon
        )
        
        # Wait for page to load
        print("   Waiting for page to load...")
        await asyncio.sleep(3)
        
        # Test 1: capture_screenshot
        print("\n2. Testing capture_screenshot...")
        screenshot_result = await BrowserUtils.capture_screenshot(
            browser_agent=browser_agent,
            session_id="test-session",
            include_log=True
        )
        
        has_screenshot = (
            screenshot_result["screenshot"] and 
            isinstance(screenshot_result["screenshot"], dict) and 
            "data" in screenshot_result["screenshot"]
        )
        
        if has_screenshot:
            print(f"   ✅ Screenshot captured successfully")
            print(f"   Current URL: {screenshot_result['current_url']}")
            data_preview = screenshot_result["screenshot"]["data"][:30] + "..." if screenshot_result["screenshot"]["data"] else "None"
            print(f"   Screenshot data preview: {data_preview}")
        else:
            print(f"   ❌ Failed to capture screenshot")
            print(f"   Result: {screenshot_result}")
        
        # Test 2: get_browser_state
        print("\n3. Testing get_browser_state...")
        start_time = time.time()
        state_result = await BrowserUtils.get_browser_state(
            browser_agent=browser_agent,
            session_id="test-session",
            retries=2
        )
        duration = time.time() - start_time
        
        print(f"   Duration: {duration:.2f} seconds")
        print(f"   Browser initialized: {state_result['browser_initialized']}")
        print(f"   Current URL: {state_result['current_url']}")
        print(f"   Page title: {state_result['page_title']}")
        
        has_screenshot_in_state = (
            state_result["screenshot"] and 
            isinstance(state_result["screenshot"], dict) and 
            "data" in state_result["screenshot"]
        )
        
        if has_screenshot_in_state:
            print(f"   ✅ Screenshot included in state")
            data_preview = state_result["screenshot"]["data"][:30] + "..." 
            print(f"   Screenshot data preview: {data_preview}")
        else:
            print(f"   ❌ No screenshot in state")
        
        # Test 3: create_tool_result_with_screenshot
        print("\n4. Testing create_tool_result_with_screenshot...")
        response_data = {
            "message": "Test successful",
            "current_url": state_result["current_url"]
        }
        
        tool_result = BrowserUtils.create_tool_result_with_screenshot(
            tool_use_id="test-tool-use-id",
            response_data=response_data,
            screenshot_data=state_result["screenshot"]
        )
        
        message_dict = tool_result.to_dict()
        print(f"   Role: {message_dict['role']}")
        
        # Check for image in message content
        has_image = False
        for item in message_dict['content']:
            if "toolResult" in item and "content" in item["toolResult"]:
                for content_item in item["toolResult"]["content"]:
                    if "image" in content_item:
                        has_image = True
                        break
        
        print(f"   Contains image: {'✅ Yes' if has_image else '❌ No'}")
        
    except Exception as e:
        import traceback
        print(f"Error during test: {e}")
        traceback.print_exc()
    finally:
        # Clean up
        print("\n5. Cleaning up...")
        try:
            await agent_manager.close_agent("test-session")
            print("   Browser agent closed")
        except Exception as e:
            print(f"   Error during cleanup: {e}")
    
    print("\nTest completed!")

if __name__ == "__main__":
    asyncio.run(test_browser_utils())
