import os
import sys
import asyncio
import logging
import traceback
import base64
import json
from typing import Dict, Any, Optional, List
from fastmcp import FastMCP
from browser_controller import BrowserController
from nova_act_config import DEFAULT_BROWSER_SETTINGS

logging.basicConfig(
    level=logging.INFO,
    format='[MCP] %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("browser_mcp")

mcp = FastMCP("browser-automation", version="0.1.0")

_browser_controller = None

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

def get_browser_controller() -> BrowserController:
    global _browser_controller
    if _browser_controller is None:
        _browser_controller = BrowserController()
    return _browser_controller

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
        browser = get_browser_controller()
        
        if not await asyncio.to_thread(browser.is_initialized):
            return {"status": "error", "message": "Browser not initialized"}
            
        result = await asyncio.to_thread(browser.go_to_url, url)
        
        response = {
            "status": "success",
            "message": f"Navigated to {url}",
            "current_url": result["current_url"],
            "page_title": await asyncio.to_thread(browser.get_page_title),
            "screenshot": result["screenshot"]
        }
        
        logger.info(f"Navigation result: {format_log_response(response)}")
        return response
    except Exception as e:
        return create_error_response(e, "navigate to URL")

@mcp.tool()
async def act(instruction: str, max_steps: Optional[int] = 3) -> Dict[str, Any]:
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
        
        max_steps: (Optional) Maximum number of steps to execute (default: 3)
                  Use values >3 for multi-step actions like:
                  - Filling multiple form fields (max_steps=8)
                  - Extensive scrolling (max_steps=5)
                  - Sequential interactions (max_steps=3)
    """
    try:
        browser = get_browser_controller()
        
        if not await asyncio.to_thread(browser.is_initialized):
            return {"status": "error", "message": "Browser not initialized"}
        
        max_steps = DEFAULT_BROWSER_SETTINGS.get("max_steps", 30)
        timeout = DEFAULT_BROWSER_SETTINGS.get("timeout", 300)
        
        result = await asyncio.to_thread(
            browser.execute_action, 
            instruction,
            max_steps=max_steps, 
            timeout=timeout
        )
        
        screenshot_data = await asyncio.to_thread(browser.take_screenshot)
        current_url = await asyncio.to_thread(browser.get_current_url)
        page_title = await asyncio.to_thread(browser.get_page_title)
        
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
            browser = get_browser_controller()
            if await asyncio.to_thread(browser.is_initialized):
                screenshot_data = await asyncio.to_thread(browser.take_screenshot)
                current_url = await asyncio.to_thread(browser.get_current_url)
                page_title = await asyncio.to_thread(browser.get_page_title)
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
async def extract_data(
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
        browser = get_browser_controller()
        
        if not await asyncio.to_thread(browser.is_initialized):
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
        
        result = await asyncio.to_thread(
            browser.execute_action, 
            prompt, 
            schema=schema,
            max_steps=max_steps, 
            timeout=timeout
        )
        
        screenshot_data = await asyncio.to_thread(browser.take_screenshot)
        current_url = await asyncio.to_thread(browser.get_current_url)
        page_title = await asyncio.to_thread(browser.get_page_title)
        
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
        browser = get_browser_controller()
        
        if await asyncio.to_thread(browser.is_initialized):
            screenshot_data = await asyncio.to_thread(browser.take_screenshot)
            
            response = {
                "status": "already_initialized",
                "message": "Browser was already initialized",
                "current_url": await asyncio.to_thread(browser.get_current_url),
                "page_title": await asyncio.to_thread(browser.get_page_title),
                "screenshot": screenshot_data
            }
            logger.info(f"Browser status: {format_log_response(response)}")
            return response
        
        success, screenshot_data = await asyncio.to_thread(
            browser.initialize_browser,
            headless=headless,
            starting_url=url
        )
        
        if not success:
            return {
                "status": "error",
                "message": "Failed to initialize browser"
            }
        
        current_url = await asyncio.to_thread(browser.get_current_url)
        page_title = await asyncio.to_thread(browser.get_page_title)
        
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
        browser = get_browser_controller()
        
        if not await asyncio.to_thread(browser.is_initialized):
            return {
                "status": "not_initialized",
                "message": "Browser was not initialized"
            }
        
        success = await asyncio.to_thread(browser.close)
        
        global _browser_controller
        _browser_controller = None
        
        return {
            "status": "success" if success else "error",
            "message": "Browser closed successfully" if success else "Error closing browser"
        }
    except Exception as e:
        return create_error_response(e, "close browser")

@mcp.tool()
async def restart_browser(headless: bool = True, url: str = "about:blank") -> Dict[str, Any]:
    """
    Close and restart the browser. Use when browser state becomes problematic or when facing CAPTCHA/verification challenges.
    
    Args:
        headless: Whether to run the restarted browser in headless mode
        url: Starting URL for the new browser session
    """
    try:
        close_result = await close_browser()
        init_result = await initialize_browser(headless=headless, url=url)
        
        return {
            "status": "success" if init_result.get("status") == "success" else "error",
            "message": "Browser restarted successfully" if init_result.get("status") == "success" else "Failed to restart browser",
            "close_result": close_result,
            "initialize_result": init_result,
            "screenshot": init_result.get("screenshot")
        }
    except Exception as e:
        return create_error_response(e, "restart browser")

@mcp.tool()
async def take_screenshot(max_width: int = 800, quality: int = 70) -> Dict[str, Any]:
    """
    Take a screenshot of the current browser state.
    
    Args:
        max_width: Maximum width of the screenshot in pixels
        quality: JPEG quality (1-100)
    """
    try:
        browser = get_browser_controller()
        
        if not await asyncio.to_thread(browser.is_initialized):
            return {
                "status": "error", 
                "message": "Browser not initialized",
                "screenshot": None
            }
            
        screenshot_data = await asyncio.to_thread(browser.take_screenshot, max_width, quality)
        current_url = await asyncio.to_thread(browser.get_current_url)
        page_title = await asyncio.to_thread(browser.get_page_title)
        
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

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Browser Automation MCP Server")
    parser.add_argument("--transport", type=str, default="stdio", choices=["stdio", "http"],
                        help="Transport protocol (stdio or http)")
    parser.add_argument("--host", type=str, default="localhost",
                        help="Host to bind to (for HTTP transport)")
    parser.add_argument("--port", type=int, default=8000,
                        help="Port to bind to (for HTTP transport)")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.INFO)
    
    try:
        if args.transport == "stdio":
            mcp.run(transport="stdio")
        else:
            mcp.run(transport="http", host=args.host, port=args.port)
    except Exception as e:
        logger.error(f"Error running MCP server: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
