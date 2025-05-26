# app/api_routes/browser_control.py

from fastapi import APIRouter, Request, HTTPException
import logging

from app.libs.data.session_manager import get_session_manager

logger = logging.getLogger("browser_control_api")
logger.setLevel(logging.WARNING)
router = APIRouter()

@router.get("/session/{session_id}/browser-status")
async def get_browser_status(session_id: str):
    """Get browser status for a session"""
    try:
        session_manager = get_session_manager()
        session = await session_manager.validate_session(session_id)
        
        if not session:
            return {
                "status": "error",
                "message": "Session not found or expired",
                "browser_initialized": False,
                "has_active_session": False
            }
        
        # Get state from browser state manager
        from app.libs.core.browser_state_manager import BrowserStateManager
        browser_state_manager = BrowserStateManager()
        browser_state = browser_state_manager.get_browser_state(session_id)
        
        if browser_state:
            state_dict = browser_state.to_dict()
            result = {
                "status": "success",
                "session_id": session_id,
                "browser_status": state_dict["status"],
                "browser_initialized": state_dict["browser_initialized"],
                "has_active_session": state_dict["has_active_session"],
                "current_url": state_dict["current_url"],
                "page_title": state_dict["page_title"],
                "error_message": state_dict["error_message"],
                "has_screenshot": state_dict["has_screenshot"],
                "last_updated": state_dict["last_updated"],
                "last_updated_iso": state_dict["last_updated_iso"],
                "initialization_time": state_dict["initialization_time"],
                "is_headless": state_dict["is_headless"],  # Add headless info to top level
                "browser_state": state_dict,  # Include full browser state
                "message": "Browser status retrieved from state manager"
            }
            logger.info(f"Browser status API response: {result}")
            return result
        else:
            result = {
                "status": "success", 
                "session_id": session_id,
                "browser_initialized": False,
                "has_active_session": False,
                "current_url": "",
                "message": "No browser state found"
            }
            logger.info(f"Browser status API response: {result}")
            return result
            
    except Exception as e:
        logger.error(f"Error getting browser status for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get browser status: {str(e)}")

@router.post("/session/{session_id}/browser/{tool_name}")
async def execute_browser_tool(session_id: str, tool_name: str, request: Request):
    """Execute browser tool directly without chat message processing"""
    
    try:
        # Validate session
        session_manager = get_session_manager()
        session = await session_manager.validate_session(session_id)
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found or expired")
        
        # Get browser manager
        from app.libs.core.agent_manager import get_agent_manager
        agent_manager = get_agent_manager()
        browser_manager = agent_manager.get_browser_manager(session_id)
        
        if not browser_manager:
            raise HTTPException(status_code=404, detail="No browser instance found for session")
        
        # Get tool arguments from request body
        try:
            body = await request.json()
            tool_args = body.get('args', {})
        except:
            tool_args = {}
        
        logger.info(f"Executing browser tool: {tool_name} with args: {tool_args}")
        
        # Execute the MCP tool directly
        result = await browser_manager.session.call_tool(tool_name, tool_args)
        response_data = browser_manager.parse_response(result.content[0].text)
        
        # Update browser state based on tool execution
        from app.libs.core.browser_state_manager import BrowserStateManager, BrowserStatus
        browser_state_manager = BrowserStateManager()
        
        if tool_name == 'close_browser':
            await browser_state_manager.update_browser_state(
                session_id=session_id,
                status=BrowserStatus.CLOSED
            )
        elif tool_name == 'navigate':
            await browser_state_manager.update_browser_state(
                session_id=session_id,
                status=BrowserStatus.NAVIGATING,
                current_url=response_data.get("current_url", "")
            )
        elif response_data.get("current_url"):
            # Update URL for any tool that returns current_url
            await browser_state_manager.update_browser_state(
                session_id=session_id,
                current_url=response_data.get("current_url", ""),
                page_title=response_data.get("page_title", ""),
                has_screenshot=bool(response_data.get("screenshot"))
            )
        
        logger.info(f"Browser tool {tool_name} executed successfully")
        return {
            "status": "success",
            "tool": tool_name,
            "session_id": session_id,
            "result": response_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing browser tool {tool_name} for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to execute browser tool: {str(e)}")

@router.post("/session/{session_id}/close-browser")
async def close_browser(session_id: str):
    """Close browser for a specific session"""
    try:
        # Execute close_browser tool
        request_body = {"args": {}}
        
        # Create a mock request object
        class MockRequest:
            async def json(self):
                return request_body
        
        mock_request = MockRequest()
        
        # Call the execute_browser_tool function with close_browser
        result = await execute_browser_tool(session_id, "close_browser", mock_request)
        
        return {
            "status": "success",
            "session_id": session_id,
            "message": "Browser closed successfully",
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Error closing browser for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to close browser: {str(e)}")

@router.post("/session/{session_id}/navigate")
async def navigate_browser(session_id: str, request: Request):
    """Navigate browser to a specific URL"""
    try:
        body = await request.json()
        url = body.get('url')
        
        if not url:
            raise HTTPException(status_code=400, detail="URL is required")
        
        # Execute navigate tool
        request_body = {"args": {"url": url}}
        
        # Create a mock request object
        class MockRequest:
            async def json(self):
                return request_body
        
        mock_request = MockRequest()
        
        # Call the execute_browser_tool function with navigate
        result = await execute_browser_tool(session_id, "navigate", mock_request)
        
        return {
            "status": "success",
            "session_id": session_id,
            "url": url,
            "message": "Navigation initiated successfully",
            "result": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error navigating browser for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to navigate browser: {str(e)}")

@router.post("/session/{session_id}/screenshot")
async def take_screenshot(session_id: str):
    """Take a screenshot of the current browser page"""
    try:
        # Execute screenshot tool
        request_body = {"args": {}}
        
        # Create a mock request object
        class MockRequest:
            async def json(self):
                return request_body
        
        mock_request = MockRequest()
        
        # Call the execute_browser_tool function with screenshot
        result = await execute_browser_tool(session_id, "screenshot", mock_request)
        
        return {
            "status": "success",
            "session_id": session_id,
            "message": "Screenshot taken successfully",
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Error taking screenshot for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to take screenshot: {str(e)}")

@router.post("/session/{session_id}/take-control")
async def take_control(session_id: str):
    """Take manual control of browser by switching from headless to visible mode"""
    logger.info(f"=== TAKE CONTROL API CALLED for session: {session_id} ===")
    try:
        # Validate session
        session_manager = get_session_manager()
        session = await session_manager.validate_session(session_id)
        
        if not session:
            logger.error(f"Session validation failed for {session_id}")
            raise HTTPException(status_code=404, detail="Session not found or expired")
        
        logger.info(f"Session validated successfully for {session_id}")
        
        # Get agent manager and execute take control
        from app.libs.core.agent_manager import get_agent_manager
        agent_manager = get_agent_manager()
        
        logger.info(f"Calling agent_manager.take_control for session {session_id}")
        try:
            success = await agent_manager.take_control(session_id)
            logger.info(f"take_control result: {success} for session {session_id}")
        except Exception as e:
            logger.error(f"Exception in agent_manager.take_control: {e}")
            import traceback
            logger.error(f"take_control traceback: {traceback.format_exc()}")
            success = False
        
        if success:
            result = {
                "status": "success",
                "session_id": session_id,
                "message": "Successfully took manual control of browser. Browser is now visible and ready for manual interaction."
            }
            logger.info(f"Take control API success response: {result}")
            return result
        else:
            result = {
                "status": "error",
                "session_id": session_id,
                "message": "Failed to take control of browser. Please check browser state and try again."
            }
            logger.error(f"Take control API error response: {result}")
            return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Exception in take_control API for session {session_id}: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to take control of browser: {str(e)}")

@router.post("/session/{session_id}/release-control")
async def release_control(session_id: str):
    """Release manual control of browser by switching from visible to headless mode"""
    logger.info(f"=== RELEASE CONTROL API CALLED for session: {session_id} ===")
    try:
        # Validate session
        session_manager = get_session_manager()
        session = await session_manager.validate_session(session_id)
        
        if not session:
            logger.error(f"Session validation failed for {session_id}")
            raise HTTPException(status_code=404, detail="Session not found or expired")
        
        logger.info(f"Session validated successfully for {session_id}")
        
        # Send initial release control callback (without screenshot to avoid thread conflicts)
        try:
            from app.libs.utils.decorators import log_thought
            
            log_thought(
                session_id=session_id,
                type_name="user_control",
                category="user_control",
                node="User Control",
                content="Starting release control process - switching browser to headless mode",
                technical_details={"operation": "release_control", "step": "starting"}
            )
        except Exception as e:
            logger.error(f"Error sending initial release control callback: {e}")
        
        # Get agent manager and use its browser state manager
        from app.libs.core.browser_state_manager import BrowserStatus
        from app.libs.core.agent_manager import get_agent_manager
        
        agent_manager = get_agent_manager()
        
        # Update state to headless mode through agent manager
        await agent_manager.update_browser_state(
            session_id=session_id,
            is_headless=True
        )
        
        logger.info(f"Browser state updated to headless=True for session {session_id}")
        
        # If we have an active browser manager, restart it in headless mode
        browser_manager = agent_manager.get_browser_manager(session_id)
        if browser_manager and browser_manager.browser_initialized:
            try:
                # Get current URL before restarting
                current_url = None
                try:
                    from app.libs.core.browser_utils import BrowserUtils
                    browser_state = await BrowserUtils.get_browser_state(browser_manager)
                    current_url = browser_state.get("current_url", "")
                    logger.info(f"Current URL before release control: {current_url}")
                    
                        
                except Exception as e:
                    logger.warning(f"Failed to get current URL: {e}")
                
                logger.info(f"Restarting browser in headless mode for session {session_id}")
                
                result = await browser_manager.session.call_tool("restart_browser", {
                    "headless": True, 
                    "url": current_url
                })
                response_data = browser_manager.parse_response(result.content[0].text)
                
                # Check if restart actually succeeded
                if response_data.get("status") == "success":
                    logger.info(f"Browser restarted in headless mode successfully")
                    
                    # Send success callback (without screenshot to avoid thread conflicts)
                    try:
                        from app.libs.utils.decorators import log_thought
                        
                        log_thought(
                            session_id=session_id,
                            type_name="user_control",
                            category="user_control",
                            node="User Control",
                            content="✅ Release control completed successfully! Browser is now running in headless mode.",
                            technical_details={"operation": "release_control", "step": "completed", "status": "success"}
                        )
                    except Exception as e:
                        logger.error(f"Error sending success callback: {e}")
                    
                    # Update state to reflect successful restart
                    await agent_manager.update_browser_state(
                        session_id=session_id,
                        is_headless=True,
                        status=BrowserStatus.INITIALIZED
                    )
                else:
                    logger.error(f"Browser restart failed: {response_data.get('message', 'Unknown error')}")
                    
                    # For initialization timeouts, try to continue with current session
                    if "Timeout" in response_data.get('message', '') or "timeout" in response_data.get('message', '').lower():
                        logger.warning("Browser initialization timeout detected, attempting to continue with existing session")
                        
                        # Send warning callback instead of failure
                        try:
                            from app.libs.utils.decorators import log_thought
                            log_thought(
                                session_id=session_id,
                                type_name="user_control",
                                category="user_control",
                                node="User Control",
                                content="🟡 Release control completed with timeout warning. Browser may still be functional in headless mode.",
                                technical_details={"operation": "release_control", "step": "timeout_warning", "error": response_data.get('message', 'Unknown error')}
                            )
                        except Exception as e:
                            logger.error(f"Error sending warning callback: {e}")
                        
                        # Update state to headless but keep as initialized if browser manager exists
                        await agent_manager.update_browser_state(
                            session_id=session_id,
                            is_headless=True,
                            status=BrowserStatus.INITIALIZED,  # Keep as initialized
                            error_message=None  # Clear error message
                        )
                    else:
                        # Send failure callback for non-timeout errors
                        try:
                            from app.libs.utils.decorators import log_thought
                            log_thought(
                                session_id=session_id,
                                type_name="user_control",
                                category="user_control",
                                node="User Control",
                                content=f"❌ Release control failed: {response_data.get('message', 'Unknown error')}",
                                technical_details={"operation": "release_control", "step": "failed", "error": response_data.get('message', 'Unknown error')}
                            )
                        except Exception as e:
                            logger.error(f"Error sending failure callback: {e}")
                        
                        # Force update state to headless with error
                        await agent_manager.update_browser_state(
                            session_id=session_id,
                            is_headless=True,
                            status=BrowserStatus.ERROR,
                            error_message=f"Failed to restart in headless mode: {response_data.get('message', 'Unknown error')}"
                        )
            except Exception as e:
                logger.error(f"Exception during browser restart: {e}")
                
                # Send exception callback
                try:
                    from app.libs.utils.decorators import log_thought
                    log_thought(
                        session_id=session_id,
                        type_name="user_control",
                        category="user_control",
                        node="User Control",
                        content=f"❌ Release control failed with exception: {str(e)}",
                        technical_details={"operation": "release_control", "step": "exception", "error": str(e)}
                    )
                except Exception as cb_e:
                    logger.error(f"Error sending exception callback: {cb_e}")
                
                # Force update state to headless even if restart failed
                await agent_manager.update_browser_state(
                    session_id=session_id,
                    is_headless=True,
                    status=BrowserStatus.ERROR,
                    error_message=f"Exception during restart: {str(e)}"
                )
        
        result = {
            "status": "success",
            "session_id": session_id,
            "message": "Successfully released manual control. Browser is now running in headless mode."
        }
        
        logger.info(f"Release control API success response: {result}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Exception in release_control API for session {session_id}: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to release control of browser: {str(e)}")