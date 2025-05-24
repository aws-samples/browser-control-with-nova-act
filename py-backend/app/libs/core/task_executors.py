import logging
import traceback
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

from app.libs.core.agent_manager import AgentManager
from app.libs.utils.utils import setup_paths
from app.libs.utils.decorators import log_thought
from app.libs.core.browser_utils import BrowserUtils, BedrockClient
from app.libs.config.prompts import SUPERVISOR_PROMPT, SUPERVISOR_TOOL
from app.libs.config.config import BROWSER_HEADLESS, MAX_AGENT_TURNS, MAX_SUPERVISOR_TURNS
from app.libs.data.message import Message
from app.libs.utils.error_handler import error_handler

logger = logging.getLogger("task_executors")

class BaseTaskExecutor:
    def __init__(self, model_id: str, region: str, agent_manager: AgentManager = None):
        self.model_id = model_id
        self.region = region
        self.bedrock_client = BedrockClient(model_id, region)
        # Use provided agent_manager or get the global instance
        self.agent_manager = agent_manager or self._get_agent_manager()
    
    def _get_agent_manager(self):
        """Get the global agent manager instance"""
        from app.libs.core.agent_manager import get_agent_manager
        return get_agent_manager()
    
    async def get_browser_state(self, session_id: str) -> Dict[str, Any]:
        """Get browser state from agent manager"""
        if not self.agent_manager:
            logger.error("Agent manager is None - this should not happen after initialization")
            return {
                "browser_initialized": False,
                "current_url": "",
                "page_title": "",
                "screenshot": None
            }
        
        browser_manager = self.agent_manager._browser_managers.get(session_id)
        
        if not browser_manager:
            logger.warning(f"No browser manager found for session {session_id}")
            return {
                "browser_initialized": False,
                "current_url": "",
                "page_title": "",
                "screenshot": None
            }
        
        return await BrowserUtils.get_browser_state(browser_manager, session_id=session_id)
    
    async def _handle_exception(self, exception, session_id, start_time, browser_manager=None):
        # Use centralized error handler
        error_context = "task execution"
        error_dict = error_handler.log_error(exception, error_context, session_id)
        
        # Try to get browser screenshot 
        screenshot_data = None
        if browser_manager:
            try:
                result = await BrowserUtils.capture_screenshot(browser_manager, session_id)
                screenshot_data = result.get("screenshot")
            except Exception as screenshot_error:
                logger.warning(f"Failed to capture error screenshot: {screenshot_error}")
        
        # Log error as answer with timing information
        log_thought(
            session_id=session_id,
            type_name="answer",
            category="result",
            node="Answer",
            content=error_handler.format_user_error(error_dict)["message"],
            technical_details={
                "error": str(exception),
                "processing_time_sec": round((time.time() - start_time), 2)
            }
        )
        
        # Also log as error type
        log_thought(
            session_id=session_id,
            type_name="error",
            category="error",
            node="error",
            content=f"Error: {str(exception)}"
        )
        
        return {
            "type": "error",
            "error": error_message,
            "screenshot": screenshot_data
        }

class NavigationExecutor(BaseTaskExecutor):
    """Executor for navigation tasks."""
    
    async def execute(self, classification: Dict[str, Any], session_id: str, model_id: str = None, region: str = None) -> Dict[str, Any]:
        start_time = time.time()
        try:
            # Setup and initialize
            paths = setup_paths()
            server_path = paths["server_path"]
            
            browser_manager = await self.agent_manager.get_or_create_browser_manager(
                session_id=session_id,
                server_path=server_path,
                headless=BROWSER_HEADLESS,  # Use global configuration
                model_id=model_id or self.model_id,
                region=region or self.region
            )
            
            url = classification.get("details", "https://www.google.com")
            
            # Log navigation intent
            log_thought(
                session_id=session_id,
                type_name="navigation",
                category="execution",
                node="Navigation",
                content=f"Navigating to URL: {url}"
            )
            
            # Execute navigation
            result = await browser_manager.session.call_tool("navigate", {"url": url})
            response_data = browser_manager.parse_response(result.content[0].text)
            
            # Process screenshot if available
            screenshot = None
            if isinstance(response_data, dict) and "screenshot" in response_data:
                screenshot = response_data["screenshot"]
                    
                if screenshot and isinstance(screenshot, dict) and "data" in screenshot:
                    log_thought(
                        session_id=session_id,
                        type_name="visualization",
                        category="screenshot",
                        node="Browser",
                        content=f"Navigation result for: {url}",
                        technical_details={
                            "screenshot": screenshot,
                            "url": response_data.get("current_url", url)
                        }
                    )
                    
            # Create response message
            response_message = f"Successfully navigated to {url}. The page title is: {response_data.get('page_title', 'Unknown')}"
                    
            # Log completion
            log_thought(
                session_id=session_id,
                type_name="answer",
                category="result",
                node="Answer",
                content=response_message,
                technical_details={
                    "current_url": response_data.get("current_url", url),
                    "page_title": response_data.get("page_title", ""),
                    "processing_time_sec": round((time.time() - start_time), 2)
                }
            )
            
            
            return {
                "type": "navigate",
                "message": response_data.get("message", ""),
                "current_url": response_data.get("current_url", ""),
                "page_title": response_data.get("page_title", ""),
                "answer": response_message,
                "screenshot": screenshot
            }
                
        except Exception as e:
            logger.error(f"Error in navigation execution: {e}")
            logger.error(traceback.format_exc())
            # Log error as answer to frontend
            log_thought(
                session_id=session_id,
                type_name="answer",
                category="result",
                node="Answer",
                content=f"Navigation error: {str(e)}",
                technical_details={
                    "error": str(e),
                    "processing_time_sec": round((time.time() - start_time), 2)
                }
            )
            
            log_thought(
                session_id=session_id,
                type_name="error",
                category="error",
                node="error",
                content=f"Navigation error: {str(e)}"
            )
            
            return {
                "type": "error",
                "error": str(e),
            }


class ActionExecutor(BaseTaskExecutor):
    """Executor for browser action tasks."""
    
    async def execute(self, classification: Dict[str, Any], session_id: str, model_id: str = None, region: str = None) -> Dict[str, Any]:
        start_time = time.time()
        browser_manager = None
        
        try:
            # Setup and initialize
            paths = setup_paths()
            server_path = paths["server_path"]
            
            browser_manager = await self.agent_manager.get_or_create_browser_manager(
                session_id=session_id,
                server_path=server_path,
                headless=BROWSER_HEADLESS,  # Use global configuration
                model_id=model_id or self.model_id,
                region=region or self.region
            )
            
            user_message = classification.get("user_message", "")
            
            # Log execution start
            log_thought(
                session_id=session_id,
                type_name="act_execution",
                category="execution",
                node="Action",
                content=f"Executing browser action: {user_message}"
            )
            
            # Execute action with dedicated error handling
            try:
                result = await browser_manager.session.call_tool("act", {"instruction": user_message})
                response_data = browser_manager.parse_response(result.content[0].text)
                
                # Process successful response
                screenshot = None
                if isinstance(response_data, dict) and "screenshot" in response_data:
                    screenshot = response_data["screenshot"]
                        
                    if screenshot and isinstance(screenshot, dict) and "data" in screenshot:
                        log_thought(
                            session_id=session_id,
                            type_name="visualization",
                            category="screenshot",
                            node="Browser",
                            content="Action result",
                            technical_details={
                                "screenshot": screenshot,
                                "url": response_data.get("current_url", "")
                            }
                        )
                
                # Create response message
                action_response = response_data.get("message", "Action completed successfully")
                
                # Send completion response
                log_thought(
                    session_id=session_id,
                    type_name="answer",
                    category="result",
                    node="Answer",
                    content=action_response,
                    technical_details={
                        "current_url": response_data.get("current_url", ""),
                        "page_title": response_data.get("page_title", ""),
                        "processing_time_sec": round((time.time() - start_time), 2)
                    }
                )
                
                # Action completed - no additional log needed as answer was already sent
                
                return {
                    "type": "act",
                    "message": action_response,
                    "current_url": response_data.get("current_url", ""),
                    "page_title": response_data.get("page_title", ""),
                    "answer": action_response,
                }
                
            except Exception as act_error:
                # Handle Nova Act specific errors
                error_message = f"Error performing action: {str(act_error)}"
                logger.error(error_message)
                
                # Send error response to frontend
                log_thought(
                    session_id=session_id,
                    type_name="answer", 
                    category="result",
                    node="Answer",
                    content=f"I couldn't complete the action: {str(act_error)}",
                    technical_details={
                        "error": str(act_error),
                        "processing_time_sec": round((time.time() - start_time), 2)
                    }
                )
                
                # Log error details
                log_thought(
                    session_id=session_id,
                    type_name="error",
                    category="error",
                    node="Action",
                    content=f"Action error: {str(act_error)}"
                )
                
                return {
                    "type": "act",
                    "error": str(act_error),
                    "message": error_message,
                    "answer": f"Error: {error_message}",
                    "screenshot": screenshot
                }
                
        except Exception as e:
            # Handle initialization/general errors
            logger.error(f"Error in action execution: {e}")
            logger.error(traceback.format_exc())
            
            # Send error response to frontend
            log_thought(
                session_id=session_id,
                type_name="answer",
                category="result",
                node="Answer",
                content=f"Action error: {str(e)}",
                technical_details={
                    "error": str(e),
                    "processing_time_sec": round((time.time() - start_time), 2)
                }
            )
            
            return {
                "type": "error",
                "error": str(e),
            }


class AgentOrchestrator(BaseTaskExecutor):

    async def execute(self, user_message: str, session_id: str, model_id: str = None, region: str = None) -> Dict[str, Any]:
        start_time = time.time()
        browser_manager = None
        
        try:
            # Get current date
            current_date = datetime.now().strftime("%Y-%m-%d")
            
            # Log start of task
            log_thought(
                session_id=session_id,
                type_name="planning",
                category="status",
                node="Supervisor",
                content=f"Received request from user: '{user_message}'. Creating execution plan..."
            )

            # Initialize conversation manager with proper store
            from app.libs.data.conversation_manager import ConversationManager
            from app.api_routes.router import task_supervisor
            conversation_manager = ConversationManager(task_supervisor.conversation_store)
            
            # Get conversation history directly from store
            conversation_messages = await task_supervisor.conversation_store.load(session_id)
            
            # Add initial message if needed
            if not conversation_messages:
                initial_message = {
                    "role": "user",
                    "content": [{"text": f"Today's date: {current_date}\n\nUser request: {user_message}"}]
                }
                conversation_messages.append(initial_message)
                await task_supervisor.conversation_store.save(session_id, conversation_messages)
            
            # Setup browser agent
            paths = setup_paths()
            server_path = paths["server_path"]
            browser_manager = await self.agent_manager.get_or_create_browser_manager(
                session_id=session_id,
                server_path=server_path,
                headless=BROWSER_HEADLESS,
                model_id=model_id or self.model_id,
                region=region or self.region
            )
            
            # Create agent executor
            agent_executor = self.agent_manager.get_agent_executor(browser_manager)
            
            # Main conversation loop
            turn_count = 0
            final_answer = ""

            while True:
                if turn_count >= MAX_SUPERVISOR_TURNS:
                    final_answer = await self._generate_final_summary(
                        conversation_messages, 
                        model_id or self.model_id, 
                        session_id
                    )
                    break
                
                # Prepare messages for model
                from app.libs.data.conversation_manager import prepare_messages_for_bedrock
                filtered_messages = prepare_messages_for_bedrock(conversation_messages)
                
                # Call model
                response = self.bedrock_client.converse(
                    messages=filtered_messages,
                    system_prompt=SUPERVISOR_PROMPT,
                    tools=SUPERVISOR_TOOL
                )
                
                # Process the response
                if response['stopReason'] == 'tool_use':
                    for item in response['output']['message']['content']:
                        if 'text' in item:
                            # Add reasoning to conversation history
                            assistant_message = {
                                "role": "assistant",
                                "content": [{"text": item['text']}]
                            }
                            conversation_messages.append(assistant_message)
                            await task_supervisor.conversation_store.save(session_id, conversation_messages)
                            
                            log_thought(
                                session_id=session_id,
                                type_name="reasoning",
                                category="analysis",
                                node="Supervisor",
                                content=item['text']
                            )
                        
                        elif 'toolUse' in item:
                            # Process tool use
                            tool_info = item['toolUse']
                            tool_use_id = tool_info['toolUseId']
                            tool_name = tool_info['name']
                            tool_input = tool_info['input']
                            
                            if tool_name == 'agent_executor':
                                # Create tool request message using Message class
                                tool_request = Message.tool_request(tool_use_id, "agent_executor", tool_input)
                                # Add tool request directly to conversation store
                                conversation_messages.append(tool_request.to_dict())
                                await task_supervisor.conversation_store.save(session_id, conversation_messages)

                                # Extract mission parameters
                                mission = tool_input.get('mission', '')
                                task_context = tool_input.get('task_context', '')
                                
                                log_thought(
                                    session_id=session_id,
                                    type_name="agent_mission",
                                    category="execution",
                                    node="Supervisor",
                                    content=f"Executing mission: {mission}",
                                    technical_details={
                                        "mission": mission,
                                        "task_context": task_context
                                    }
                                )
                                
                                # Execute mission
                                result = await self._execute_mission(
                                    browser_manager=browser_manager,
                                    agent_executor=agent_executor,
                                    mission=mission,
                                    task_context=task_context,
                                    tool_use_id=tool_use_id,
                                    session_id=session_id
                                )
                                
                                # Add result to conversation - no need for additional filtering
                                tool_result_message = result["message"]
                                conversation_messages.append(tool_result_message)
                                await task_supervisor.conversation_store.save(session_id, conversation_messages)
                    
                elif response['stopReason'] == 'end_turn':
                    # Direct answer from supervisor
                    final_answer = response['output']['message']['content'][0]['text']
                    
                    # Add final answer to conversation
                    assistant_message = {
                        "role": "assistant",
                        "content": [{"text": final_answer}]
                    }
                    conversation_messages.append(assistant_message)
                    await task_supervisor.conversation_store.save(session_id, conversation_messages)
                    break
                    
                elif response['stopReason'] in ['max_tokens', 'stop_sequence', 'content_filtered']:
                    log_thought(
                        session_id=session_id,
                        type_name="warning",
                        category="limit",
                        node="Supervisor",
                        content=f"Conversation ended with stop reason: {response['stopReason']}"
                    )
                    final_answer = response['output']['message']['content'][0]['text'] if 'text' in response['output']['message']['content'][0] else "Task completed."
                    
                    # Add final answer to conversation
                    assistant_message = {
                        "role": "assistant", 
                        "content": [{"text": final_answer}]
                    }
                    conversation_messages.append(assistant_message)
                    await task_supervisor.conversation_store.save(session_id, conversation_messages)
                    break
                    
                # Increment turn count
                turn_count += 1
            
            # Get final browser state and return results
            browser_state = await BrowserUtils.get_browser_state(browser_manager)
            
            # Log final answer
            log_thought(
                session_id=session_id,
                type_name="answer",
                category="result",
                node="Answer",
                content=final_answer,
                technical_details={
                    "current_url": browser_state.get("current_url", ""),
                    "page_title": browser_state.get("page_title", ""),
                    "processing_time_sec": round((time.time() - start_time), 2)
                }
            )
            
            # Task execution completed - no additional log needed as answer was already sent
                        
            return {
                "type": "agent",
                "answer": final_answer,
                "current_url": browser_state.get("current_url", ""),
                "page_title": browser_state.get("page_title", ""),
                "screenshot": browser_state.get("screenshot"),
                "processing_time_sec": round((time.time() - start_time), 2)
            }
        
        except Exception as e:
            return await self._handle_exception(e, session_id, start_time, browser_manager)

    
    async def _generate_final_summary(self, messages, model_id, session_id):
        """Generate final summary when max turns are reached."""
        log_thought(
            session_id=session_id,
            type_name="warning",
            category="limit",
            node="Supervisor",
            content=f"Reached maximum turns limit ({MAX_SUPERVISOR_TURNS})"
        )
        
        # Generate final summary
        summary_request = {
            "role": "user", 
            "content": [{
                "text": "Please provide a final summary of what you've accomplished and what answer you can provide to the original request."
            }]
        }
        messages.append(summary_request)
        
        # Send request to Bedrock
        from app.libs.data.conversation_manager import prepare_messages_for_bedrock
        filtered_messages = prepare_messages_for_bedrock(messages)
        
        final_response = self.bedrock_client.converse(
            messages=filtered_messages,
            system_prompt=SUPERVISOR_PROMPT,
            tools=SUPERVISOR_TOOL
        )
        
        return final_response['output']['message']['content'][0]['text']

    async def _execute_mission(self, browser_manager, agent_executor, mission, task_context, tool_use_id, session_id):
        """Execute a specific mission using the agent executor and return results in tool_result format."""
        from app.api_routes.router import task_supervisor
        
        logger.info(f"Starting mission execution with tool_use_id: {tool_use_id}")
        logger.info(f"Mission: {mission[:100]}...")
        
        try:
            # Get browser state using unified method
            browser_state = await BrowserUtils.get_browser_state(browser_manager, session_id)
            current_url = browser_state.get("current_url", "")
            
            if current_url:
                logger.info(f"Current browser URL before mission: {current_url}")
            
            # Set additional parameters for agent execution
            additional_params = {}
            if task_context:
                additional_params['context'] = task_context
            if current_url:
                additional_params['current_url'] = current_url
            if browser_state.get("screenshot"):
                additional_params['supervisor_screenshot'] = browser_state.get("screenshot")
            
            # Execute agent with provided state
            result = await agent_executor.execute(mission, session_id=session_id, max_turns=MAX_AGENT_TURNS, **additional_params)
            
            # Process result
            answer = result.get("answer", "Task completed without specific answer")
            
            # Prepare result data for tool_result message
            result_data = {
                "answer": answer,
                "current_url": result.get("current_url", ""),
                "page_title": result.get("page_title", "")
            }
            
            # Include screenshot if available
            if "screenshot" in result and result["screenshot"]:
                result_data["screenshot"] = result["screenshot"]
            
            log_thought(
                session_id=session_id,
                type_name="agent_result",
                category="intermediate_answer",
                node="Agent",
                content=f"Mission completed: {answer[:200]}" + ("..." if len(answer) > 200 else "")
            )
            
            # Create tool result message using Message class
            tool_result_message = Message.tool_result(tool_use_id, result_data)
            
            # Return message dictionary
            return {"message": tool_result_message.to_dict()}
            
        except Exception as e:
            logger.error(f"Error during mission execution: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Create error result
            error_data = {
                "answer": f"Error executing mission: {str(e)}",
                "error": str(e),
                "current_url": "",
                "page_title": ""
            }
            
            # Try to get current browser state even in error case
            try:
                error_browser_state = await BrowserUtils.get_browser_state(browser_manager, session_id)
                if error_browser_state:
                    error_data["current_url"] = error_browser_state.get("current_url", "")
                    error_data["page_title"] = error_browser_state.get("page_title", "")
                    if "screenshot" in error_browser_state:
                        error_data["screenshot"] = error_browser_state["screenshot"]
            except Exception:
                pass
                
            # Log error
            log_thought(
                session_id=session_id,
                type_name="error",
                category="execution_error",
                node="Agent",
                content=f"Error during mission execution: {str(e)}"
            )
            
            # Create error tool result - tool saving happens in the execute method
            error_message = Message.tool_result(tool_use_id, error_data)
            return {"message": error_message.to_dict()}


    async def _handle_exception(self, exception, session_id, start_time, browser_manager=None):
        """Handle exceptions during task orchestration."""
        error_message = f"Error orchestrating task: {str(exception)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())

        # Log error as answer
        log_thought(
            session_id=session_id,
            type_name="answer",
            category="result",
            node="Answer",
            content=f"Error orchestrating task: {str(exception)}",
            technical_details={
                "error": str(exception),
                "processing_time_sec": round((time.time() - start_time), 2)
            }
        )
        
        return {
            "type": "error",
            "error": error_message,
        }