#!/usr/bin/env python3

import asyncio
import json
import time
from contextlib import AsyncExitStack
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def test_single_browser(session_id: str, url: str = "https://www.google.com"):
    """Test single browser initialization"""
    
    try:
        async with AsyncExitStack() as exit_stack:
            # Connect to Nova Act server with unique session ID
            headers = {"X-Session-ID": session_id}
            
            print(f"[{session_id}] Connecting to Nova Act server...")
            transport = await exit_stack.enter_async_context(
                streamablehttp_client("http://localhost:8001/mcp/", headers=headers)
            )
            read_stream, write_stream, _ = transport
            session = await exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            
            print(f"[{session_id}] Connected successfully!")
            
            # Test browser initialization
            start_time = time.time()
            result = await session.call_tool("initialize_browser", {
                "headless": True, 
                "url": url
            })
            end_time = time.time()
            
            # Parse response
            try:
                response_data = json.loads(result.content[0].text)
                status = response_data.get('status')
                message = response_data.get('message')
                
                print(f"[{session_id}] Status: {status} (took {end_time - start_time:.2f}s)")
                print(f"[{session_id}] Message: {message}")
                
                if status == "success":
                    # Take a screenshot to verify browser is working
                    screenshot_result = await session.call_tool("take_screenshot", {})
                    screenshot_data = json.loads(screenshot_result.content[0].text)
                    print(f"[{session_id}] Screenshot status: {screenshot_data.get('status')}")
                
                return status == "success"
                
            except json.JSONDecodeError:
                print(f"[{session_id}] Raw response: {result.content[0].text}")
                return False
                
    except Exception as e:
        print(f"[{session_id}] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_concurrent_browsers(num_sessions: int = 3):
    """Test multiple browser sessions concurrently"""
    
    print(f"=== Testing {num_sessions} concurrent browser sessions ===\n")
    
    # Create concurrent tasks
    tasks = []
    session_urls = [
        ("session-1", "https://www.google.com"),
        ("session-2", "https://www.amazon.com"),
        ("session-3", "https://www.github.com"),
        ("session-4", "https://www.stackoverflow.com"),
        ("session-5", "https://www.reddit.com"),
    ]
    
    for i in range(min(num_sessions, len(session_urls))):
        session_id, url = session_urls[i]
        task = asyncio.create_task(test_single_browser(session_id, url))
        tasks.append(task)
    
    # Wait for all tasks to complete
    start_time = time.time()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    end_time = time.time()
    
    # Analyze results
    successful = sum(1 for result in results if result is True)
    failed = len(results) - successful
    
    print(f"\n=== Results ===")
    print(f"Total time: {end_time - start_time:.2f}s")
    print(f"Successful: {successful}/{len(results)}")
    print(f"Failed: {failed}/{len(results)}")
    
    if failed > 0:
        print(f"Success rate: {successful/len(results)*100:.1f}%")
        print("❌ Some sessions failed - there's a concurrency issue!")
    else:
        print("✅ All sessions succeeded!")
    
    return successful, failed

async def test_sequential_vs_concurrent():
    """Compare sequential vs concurrent execution"""
    
    print("=== Sequential Test (should always work) ===")
    sequential_start = time.time()
    seq_results = []
    for i in range(3):
        result = await test_single_browser(f"seq-session-{i+1}", "https://www.google.com")
        seq_results.append(result)
    sequential_time = time.time() - sequential_start
    seq_success = sum(seq_results)
    
    print(f"Sequential: {seq_success}/3 successful in {sequential_time:.2f}s")
    
    print(f"\n{'='*50}")
    
    print("=== Concurrent Test (may have issues) ===")
    concurrent_start = time.time()
    con_success, con_failed = await test_concurrent_browsers(3)
    concurrent_time = time.time() - concurrent_start
    
    print(f"Concurrent: {con_success}/3 successful in {concurrent_time:.2f}s")
    
    if con_failed > 0 and seq_success == 3:
        print(f"\n🚨 CONCURRENCY ISSUE DETECTED!")
        print(f"Sequential works fine, but concurrent execution fails")
        print(f"This confirms there's a resource conflict between sessions")

if __name__ == "__main__":
    print("Testing Nova Act concurrent browser initialization...")
    print("Make sure Nova Act server is running on localhost:8001\n")
    
    asyncio.run(test_sequential_vs_concurrent())