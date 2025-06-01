import logging
import traceback
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

from app.libs.core.agent_manager import AgentManager
# removed setup_paths import as we now use HTTP transport
from app.libs.utils.decorators import log_thought
from app.libs.core.browser_utils import BrowserUtils, BedrockClient
from app.libs.config.prompts import get_supervisor_prompt, SUPERVISOR_TOOL
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

class NavigationExecutor(BaseTaskExecutor):
    """Executor for navigation tasks."""
    
    async def execute(self, classification: Dict[str, Any], session_id: str, model_id: str = None, region: str = None) -> Dict[str, Any]:
        start_time = time.time()
        try:
            # Initialize browser manager with HTTP connection
            browser_manager = await self.agent_manager.get_or_create_browser_manager(
                session_id=session_id,
                server_url="http://localhost:8001/mcp/",  # Nova Act server URL
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
            
            # Update browser state through agent manager
            from app.libs.core.browser_state_manager import BrowserStatus
            await self.agent_manager.update_browser_state(
                session_id=session_id,
                status=BrowserStatus.NAVIGATING,
                current_url=response_data.get("current_url", url),
                page_title=response_data.get("page_title", ""),
                has_screenshot=bool(response_data.get("screenshot"))
            )
            
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
            # Initialize browser manager with HTTP connection
            browser_manager = await self.agent_manager.get_or_create_browser_manager(
                session_id=session_id,
                server_url="http://localhost:8001/mcp/",  # Nova Act server URL
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
                
                # Update browser state through agent manager
                from app.libs.core.browser_state_manager import BrowserStatus
                from app.libs.core.agent_manager import get_agent_manager
                agent_manager = get_agent_manager()
                await agent_manager.update_browser_state(
                    session_id=session_id,
                    status=BrowserStatus.INITIALIZED,  # Actions don't change URL, so keep as initialized
                    current_url=response_data.get("current_url", ""),
                    page_title=response_data.get("page_title", ""),
                    has_screenshot=bool(response_data.get("screenshot"))
                )
                
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
                    "screenshot": None  # No screenshot available when import fails
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
            # Agent processing state is now managed via ThoughtProcess events
            
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
            
            # Enhance user message with browser context if available
            if conversation_messages:
                browser_context = await self._get_initial_browser_context(session_id)
                self._enhance_user_message_with_context(conversation_messages, user_message, browser_context, current_date)
            else:
                # Create initial message if no conversation history
                conversation_messages.append({
                    "role": "user",
                    "content": [{"text": f"Today's date: {current_date}\n\nUser request: {user_message}"}]
                })
                await task_supervisor.conversation_store.save(session_id, conversation_messages)
            
            # Initialize browser manager with HTTP connection
            browser_manager = await self.agent_manager.get_or_create_browser_manager(
                session_id=session_id,
                server_url="http://localhost:8001/mcp/",  # Nova Act server URL
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
                # Check for stop request at beginning of each iteration
                if self.agent_manager.is_agent_stop_requested(session_id):
                    # Send stopping state notification to UI
                    log_thought(
                        session_id=session_id,
                        type_name="task_status",
                        category="status",
                        node="System",
                        content="Agent is gracefully stopping - please wait...",
                        technical_details={"status": "stopping"}
                    )
                    
                    # Handle graceful stop with early termination logic
                    final_answer = await self._handle_early_stop(
                        session_id=session_id,
                        conversation_messages=conversation_messages,
                        turn_count=turn_count,
                        user_message=user_message
                    )
                    break
                
                # Send task_status start event after first stop check (stop button now active)
                if turn_count == 0:
                    log_thought(
                        session_id=session_id,
                        type_name="task_status",
                        category="status",
                        node="System",
                        content="Supervisor processing started - Stop button now active",
                        technical_details={"status": "start"}
                    )
                
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
                
                # Debug logging for message structure
                logger.debug(f"Supervisor processing turn {turn_count} with {len(filtered_messages)} messages")
                
                # Call model
                response = self.bedrock_client.converse(
                    messages=filtered_messages,
                    system_prompt=get_supervisor_prompt(),
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
                            
                            if tool_name == 'agentExecutor':
                                # Create tool request message using Message class
                                tool_request = Message.tool_request(tool_use_id, "agentExecutor", tool_input)
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
                                
                                # Log that we're continuing to get supervisor's analysis of the results
                                log_thought(
                                    session_id=session_id,
                                    type_name="reasoning",
                                    category="analysis",
                                    node="Supervisor",
                                    content="Analyzing agent results to provide comprehensive answer..."
                                )
                    
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
                    
                    # Try to extract the actual content or generate a meaningful summary
                    content_text = ""
                    if response['output']['message']['content'] and len(response['output']['message']['content']) > 0:
                        if 'text' in response['output']['message']['content'][0]:
                            content_text = response['output']['message']['content'][0]['text']
                    
                    # If we have meaningful content, use it; otherwise generate a summary
                    if content_text and len(content_text.strip()) > 10 and not content_text.strip().lower().startswith("action completed"):
                        final_answer = content_text
                    else:
                        # Generate a summary based on conversation history
                        final_answer = await self._generate_final_summary(
                            conversation_messages, 
                            model_id or self.model_id, 
                            session_id
                        )
                    
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
            
            # Send task_status complete event after exiting supervisor while loop
            log_thought(
                session_id=session_id,
                type_name="task_status",
                category="status",
                node="System",
                content="Supervisor processing completed - Stop button now inactive",
                technical_details={"status": "complete"}
            )
            
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
        finally:
            # Clear stop flag when processing completes
            if session_id:
                self.agent_manager.clear_stop_flag(session_id)
                
                # Ensure task_status complete event is sent when exiting finally block
                try:
                    log_thought(
                        session_id=session_id,
                        type_name="task_status",
                        category="status",
                        node="System",
                        content="Supervisor execution ended - Stop button deactivated",
                        technical_details={"status": "complete", "cleanup": True}
                    )
                except Exception as e:
                    logger.error(f"Failed to send task completion event: {e}")

    
    async def _get_initial_browser_context(self, session_id: str) -> Dict[str, Any]:
        """Get browser context for initial message if browser is already initialized."""
        context = {"has_browser": False}
        
        try:
            # Check if browser is already initialized
            browser_state = await self.get_browser_state(session_id)
            
            if browser_state and browser_state.get("browser_initialized"):
                context.update({
                    "has_browser": True,
                    "current_url": browser_state.get("current_url", ""),
                    "page_title": browser_state.get("page_title", "")
                })
                
                # Process screenshot if available
                screenshot_data = browser_state.get("screenshot")
                if screenshot_data and isinstance(screenshot_data, dict) and "data" in screenshot_data:
                    try:
                        import base64
                        screenshot_bytes = base64.b64decode(screenshot_data["data"])
                        context.update({
                            "screenshot_bytes": screenshot_bytes,
                            "screenshot_format": screenshot_data.get("format", "jpeg")
                        })
                    except Exception as e:
                        logger.error(f"Error processing screenshot for agent context: {e}")
        
        except Exception as e:
            logger.debug(f"Could not get browser context for agent: {e}")
            
        return context
    
    async def _generate_final_summary(self, messages, model_id, session_id):
        """Generate final summary when max turns are reached or incomplete responses."""
        log_thought(
            session_id=session_id,
            type_name="summary_generation",
            category="analysis",
            node="Supervisor",
            content="Generating comprehensive summary of completed tasks..."
        )
        
        # Extract agent results from conversation for better summary
        agent_results = []
        for msg in messages:
            if msg.get("role") == "user" and "content" in msg:
                for content_item in msg["content"]:
                    if isinstance(content_item, dict) and "toolResult" in content_item:
                        tool_result = content_item["toolResult"]
                        if "content" in tool_result:
                            for result_content in tool_result["content"]:
                                if isinstance(result_content, dict) and "json" in result_content:
                                    json_data = result_content["json"]
                                    if "answer" in json_data:
                                        agent_results.append(json_data["answer"])
        
        # Generate final summary
        summary_prompt = "Please provide a comprehensive summary of what you've accomplished. "
        if agent_results:
            summary_prompt += f"The following results were obtained from agent executions: {' | '.join(agent_results[:3])}"
        summary_prompt += " Provide a clear, detailed answer to the user's original request based on all available information."
        
        summary_request = {
            "role": "user", 
            "content": [{"text": summary_prompt}]
        }
        messages.append(summary_request)
        
        # Send request to Bedrock
        from app.libs.data.conversation_manager import prepare_messages_for_bedrock
        filtered_messages = prepare_messages_for_bedrock(messages)
        
        try:
            final_response = self.bedrock_client.converse(
                messages=filtered_messages,
                system_prompt=get_supervisor_prompt(),
                tools=None  # No tools for final summary
            )
            
            if 'output' in final_response and 'message' in final_response['output']:
                content = final_response['output']['message']['content']
                if content and len(content) > 0 and 'text' in content[0]:
                    return content[0]['text']
        except Exception as e:
            logger.error(f"Error generating final summary: {e}")
        
        # Fallback summary if API call fails
        if agent_results:
            return f"I completed the requested tasks and obtained the following results: {' | '.join(agent_results)}. Please let me know if you need more specific information about any of these findings."
        else:
            return "I worked on your request but encountered some issues in generating a complete response. Please let me know if you'd like me to try again or if you need clarification on any specific aspect."

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
            
            # Debug logging for agent execution
            logger.debug(f"Executing agent mission with {len(additional_params)} parameters")
            
            # Execute agent with provided state
            result = await agent_executor.execute(mission, session_id=session_id, max_turns=MAX_AGENT_TURNS, **additional_params)
            
            # Update browser state after agent execution through agent manager
            from app.libs.core.browser_state_manager import BrowserStatus
            await self.agent_manager.update_browser_state(
                session_id=session_id,
                status=BrowserStatus.INITIALIZED,
                current_url=result.get("current_url", ""),
                page_title=result.get("page_title", ""),
                has_screenshot=bool(result.get("screenshot"))
            )
            
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
    
    async def _handle_early_stop(self, session_id: str, conversation_messages: List[Dict[str, Any]], 
                                turn_count: int, user_message: str) -> str:

        # Send immediate acknowledgment that stop request was received
        log_thought(
            session_id=session_id,
            type_name="stop_notification",
            category="status", 
            node="Supervisor",
            content="Stop request received - Preparing graceful termination...",
            technical_details={
                "stop_acknowledged": True,
                "turn_count": turn_count,
                "reason": "user_request"
            }
        )
        
        # Send explicit task_status stopped event
        log_thought(
            session_id=session_id,
            type_name="task_status",
            category="status",
            node="System",
            content="Agent stopped by user request - Stop button now inactive",
            technical_details={"status": "stopped"}
        )
        
        # Generate comprehensive summary of work completed so far
        final_answer = await self._generate_supervisor_summary(
            session_id=session_id,
            conversation_messages=conversation_messages,
            turn_count=turn_count,
            user_message=user_message
        )
        
        return final_answer
    
    async def _generate_supervisor_summary(self, session_id: str, conversation_messages: List[Dict[str, Any]], 
                                          turn_count: int, user_message: str) -> str:
        try:
            # Get current browser state for context
            browser_state = await self.get_browser_state(session_id)
            current_url = browser_state.get("current_url", "")
            page_title = browser_state.get("page_title", "")
            screenshot = browser_state.get("screenshot")
            
            # Create summary request that focuses on the full context
            browser_context = ""
            if current_url:
                browser_context = f"\n\nCurrent browser context:\n- URL: {current_url}\n- Page: {page_title}"
            
            summary_request = {
                "role": "user",
                "content": [{
                    "text": f"The user has requested to stop the current task. Please provide a comprehensive summary that includes:\n\n1. What specific progress was made toward the original request: '{user_message}'\n2. What agent actions were executed and their results\n3. Any insights, findings, or partial results discovered\n4. Current status and what remains to be done{browser_context}\n\nBe specific and actionable in your summary."
                }]
            }
            
            # Add screenshot to summary request if available
            if screenshot and isinstance(screenshot, dict) and "data" in screenshot:
                try:
                    import base64
                    screenshot_bytes = base64.b64decode(screenshot["data"])
                    summary_request["content"].append({
                        "image": {
                            "format": screenshot.get("format", "jpeg"),
                            "source": {"bytes": screenshot_bytes}
                        }
                    })
                except Exception as e:
                    logger.error(f"Error processing screenshot for summary: {e}")
            
            # Prepare messages for summary (include key conversation elements)
            summary_messages = []
            
            # Add original user request context
            summary_messages.append({
                "role": "user", 
                "content": [{"text": f"Original user request: {user_message}"}]
            })
            
            # Include key supervisor reasoning and agent results, but filter properly
            agent_results = []
            supervisor_reasoning = []
            pending_tool_uses = set()
            
            for msg in conversation_messages:
                role = msg.get("role", "")
                content = msg.get("content", [])
                
                if role == "assistant":
                    # Process assistant message - include only text, track tool uses
                    for item in content:
                        if isinstance(item, dict):
                            if "text" in item:
                                text = item["text"]
                                if len(text) > 50:  # Only meaningful reasoning
                                    supervisor_reasoning.append(text[:500])  # Truncate for summary
                            elif "toolUse" in item:
                                tool_use_id = item["toolUse"].get("toolUseId")
                                if tool_use_id:
                                    pending_tool_uses.add(tool_use_id)
                                
                elif role == "user":
                    # Look for tool results from agents
                    for item in content:
                        if isinstance(item, dict) and "toolResult" in item:
                            tool_result = item["toolResult"]
                            tool_use_id = tool_result.get("toolUseId")
                            if tool_use_id:
                                pending_tool_uses.discard(tool_use_id)
                            
                            tool_content = tool_result.get("content", [])
                            # Extract agent results
                            for result_item in tool_content:
                                if isinstance(result_item, dict) and "json" in result_item:
                                    json_data = result_item["json"]
                                    if "answer" in json_data:
                                        agent_results.append(json_data["answer"][:300])  # Truncate
            
            # Add collected context to summary messages (only if no pending tool uses)
            if supervisor_reasoning:
                summary_messages.append({
                    "role": "assistant",
                    "content": [{"text": "Key supervisor analysis:\n" + "\n\n".join(supervisor_reasoning[-3:])}]  # Last 3 reasoning steps
                })
                
            if agent_results:
                summary_messages.append({
                    "role": "user", 
                    "content": [{"text": "Agent execution results:\n" + "\n\n".join(agent_results[-3:])}]  # Last 3 agent results
                })
            
            # Add summary request
            summary_messages.append(summary_request)
            
            # Generate summary using bedrock
            from app.libs.data.conversation_manager import prepare_messages_for_bedrock
            filtered_messages = prepare_messages_for_bedrock(summary_messages)
            
            summary_response = self.bedrock_client.converse(
                messages=filtered_messages,
                system_prompt=get_supervisor_prompt(),
                tools=None  # No tools for summary
            )
            
            if summary_response.get('stopReason') == 'end_turn':
                summary_text = summary_response['output']['message']['content'][0]['text']
                return f"Task stopped by user request.\n\nSupervisor Summary:\n{summary_text}"
            else:
                # Fallback if AI summary fails
                return self._create_supervisor_fallback_summary(
                    user_message, turn_count, agent_results, supervisor_reasoning,
                    current_url, page_title
                )
                
        except Exception as e:
            logger.error(f"Error generating supervisor summary: {str(e)}")
            return self._create_supervisor_fallback_summary(
                user_message, turn_count, [], [], "", ""
            )
    
    def _create_supervisor_fallback_summary(self, user_message: str, turn_count: int, 
                                           agent_results: List[str], supervisor_reasoning: List[str],
                                           current_url: str = "", page_title: str = "") -> str:
        summary_parts = [
            "Task stopped by user request.",
            f"\nOriginal request: {user_message}",
            f"\nProgress: {turn_count} supervisor turns completed"
        ]
        
        # Add browser context if available
        if current_url:
            summary_parts.append(f"\nCurrent browser state:")
            summary_parts.append(f"  - URL: {current_url}")
            summary_parts.append(f"  - Page: {page_title}")
        
        if agent_results:
            summary_parts.append(f"\nAgent results ({len(agent_results)} executions):")
            for i, result in enumerate(agent_results[:3], 1):
                summary_parts.append(f"  {i}. {result[:150]}..." if len(result) > 150 else f"  {i}. {result}")
                
        if supervisor_reasoning:
            summary_parts.append(f"\nKey analysis points:")
            for reasoning in supervisor_reasoning[:2]:
                summary_parts.append(f"  - {reasoning[:100]}..." if len(reasoning) > 100 else f"  - {reasoning}")
                
        if not agent_results and not supervisor_reasoning:
            summary_parts.append("\nTask was stopped in early planning stages.")
            
        return "\n".join(summary_parts)

    def _enhance_user_message_with_context(self, conversation_messages: List[Dict[str, Any]], user_message: str, browser_context: Dict[str, Any], current_date: str) -> None:
        """Enhance the latest user message with browser context and date information."""
        if browser_context["has_browser"]:
            # Find and enhance the last user message with browser context
            for i in range(len(conversation_messages) - 1, -1, -1):
                if conversation_messages[i]["role"] == "user":
                    original_text = user_message
                    if conversation_messages[i]["content"] and isinstance(conversation_messages[i]["content"], list):
                        for content_item in conversation_messages[i]["content"]:
                            if isinstance(content_item, dict) and "text" in content_item:
                                original_text = content_item["text"]
                                break
                    
                    # Create enhanced message with browser context
                    enhanced_text = f"Today's date: {current_date}\n\nCurrent browser context:\n- URL: {browser_context['current_url']}\n- Page: {browser_context['page_title']}\n\nUser request: {original_text}"
                    enhanced_content = [{"text": enhanced_text}]
                    
                    # Add screenshot if available
                    if browser_context.get("screenshot_bytes"):
                        enhanced_content.append({
                            "image": {
                                "format": browser_context.get("screenshot_format", "jpeg"),
                                "source": {"bytes": browser_context["screenshot_bytes"]}
                            }
                        })
                    
                    conversation_messages[i]["content"] = enhanced_content
                    break
        else:
            # Add date to the last user message without browser context
            for i in range(len(conversation_messages) - 1, -1, -1):
                if conversation_messages[i]["role"] == "user":
                    original_text = user_message
                    if conversation_messages[i]["content"] and isinstance(conversation_messages[i]["content"], list):
                        for content_item in conversation_messages[i]["content"]:
                            if isinstance(content_item, dict) and "text" in content_item:
                                original_text = content_item["text"]
                                break
                    
                    enhanced_text = f"Today's date: {current_date}\n\nUser request: {original_text}"
                    conversation_messages[i]["content"] = [{"text": enhanced_text}]
                    break