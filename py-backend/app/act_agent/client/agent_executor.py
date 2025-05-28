import base64
import logging
import time
from typing import Dict, List

from app.libs.core.browser_utils import BrowserUtils, BedrockClient
from app.libs.utils.decorators import log_thought
from app.libs.data.message import Message
from app.libs.config.prompts import NOVA_ACT_AGENT_PROMPT, DEFAULT_MODEL_ID

logger = logging.getLogger(__name__)

EXCLUDED_TOOLS = ["close_browser", "initialize_browser", "restart_browser", "take_screenshot"]

class AgentExecutor:
    def __init__(self, browser_manager):
        self.browser_manager = browser_manager
        region = (self.browser_manager.server_config or {}).get("region", "us-west-2")
        self.bedrock_client = BedrockClient(
            self.browser_manager.server_config.get("model_id", DEFAULT_MODEL_ID), 
            region
        )
        
    def _make_bedrock_request(self, messages: List[Dict], tools: List[Dict]) -> Dict:
        model_id = self.browser_manager.server_config.get("model_id", DEFAULT_MODEL_ID)
        return self.bedrock_client.converse(
            messages=messages, 
            system_prompt=NOVA_ACT_AGENT_PROMPT,
            tools=tools
        )
    
    async def execute(self, request: str, session_id: str = None, max_turns: int = 10, 
                    supervisor_screenshot: dict = None, **kwargs):
        """Execute method with screenshot handling"""
        if not self.browser_manager.session:
            raise ValueError("Not connected to MCP server")
                
        if not self.browser_manager.browser_initialized:
            raise ValueError("Browser is not initialized")
        
        start_time = time.time()
        
        try:
            if session_id:
                log_thought(
                    session_id=session_id,
                    type_name="processing", 
                    category="status",
                    node="Agent",
                    content=f"Received request from Supervisor: '{request}'"
                )
               
            message_content = [{"text": request}]
            
            # Add screenshot to message if available
            if supervisor_screenshot and isinstance(supervisor_screenshot, dict) and "data" in supervisor_screenshot:
                try:
                    screenshot_bytes = base64.b64decode(supervisor_screenshot["data"])
                    message_content.append({
                        "image": {
                            "format": supervisor_screenshot.get("format", "jpeg"),
                            "source": {
                                "bytes": screenshot_bytes
                            }
                        }
                    })
                except Exception as e:
                    logger.error("Error processing supervisor screenshot", extra={"error": str(e)})
            else:
                logger.debug("No supervisor screenshot available, continuing without it")
            
            # Create message and prepare tools
            messages = [{"role": "user", "content": message_content}]
            
            response = await self.browser_manager.session.list_tools()
            available_tools = [{
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema
            } for tool in response.tools 
            if tool.name not in EXCLUDED_TOOLS]

            bedrock_tools = Message.to_bedrock_format(available_tools)
                
            response = self._make_bedrock_request(messages, bedrock_tools)
            result = await self._process_response(response, messages, bedrock_tools, session_id, max_turns)
            
            # Get final state for complete result
            final_state = await BrowserUtils.get_browser_state(self.browser_manager, session_id)
            
            return {
                "answer": result.get("answer", ""),
                "screenshot": final_state.get("screenshot"),
                "current_url": final_state.get("current_url", ""),
                "page_title": final_state.get("page_title", "")
            }
            
        except Exception as e:
            # Try to get state even on error
            error_state = await BrowserUtils.get_browser_state(self.browser_manager, session_id=None)
            
            if session_id:
                log_thought(
                    session_id=session_id,
                    type_name="error",
                    category="error",
                    node="Agent",
                    content=f"Error: {str(e)}"
                )
                
                log_thought(
                    session_id=session_id,
                    type_name="answer",
                    category="result",
                    node="Answer",
                    content=f"I'm sorry, an error occurred while processing your request: {str(e)}",
                    technical_details={
                        "error": str(e),
                        "processing_time_sec": round((time.time() - start_time), 2)
                    }
                )

            logger.error("Error executing chat task", extra={"error": str(e)}, exc_info=True)
            
            return {
                "error": str(e),
                "screenshot": error_state.get("screenshot"),
                "current_url": error_state.get("current_url", ""),
                "page_title": error_state.get("page_title", "")
            }
    
    async def _handle_tool_call(self, tool_info: Dict, messages: List[Dict], session_id: str = None) -> List[str]:
        tool_name = tool_info['name']
        tool_args = tool_info['input']
        tool_use_id = tool_info['toolUseId']
        response_data = {}
        screenshot_data = None

        if session_id:
            instruction_text = self._format_instruction_text(tool_name, tool_args)
            log_thought(
                session_id=session_id,
                type_name="tool_call",
                category="tool",
                node="Agent",
                content=instruction_text,
                technical_details={"tool_name": tool_name, "arguments": tool_args}
            )
        
        try:
            result = await self.browser_manager.session.call_tool(tool_name, tool_args)
            response_data = self.browser_manager.parse_response(result.content[0].text)
            success = True
        except Exception as e:
            success = False
            original_error = str(e)
            
            user_friendly_message = f"Couldn't complete the requested action"
            response_data = {
                "error": original_error,
                "message": user_friendly_message,
                "status": "error"
            }
            
            error_state = await BrowserUtils.capture_screenshot(self.browser_manager, session_id, include_log=False)
            screenshot_data = error_state.get("screenshot")
        
        status = response_data.get("status", "unknown")
        
        if session_id:
            if status == "in_progress":
                progress_message = response_data.get("message", "I'm analyzing the page to find what you're looking for")
                log_thought(
                    session_id=session_id,
                    type_name="tool_result",
                    category="tool",
                    node="NovaAct",
                    content=progress_message,
                    technical_details={
                        "tool_name": tool_name,
                        "execution_state": "in_progress",
                        "technical_details": response_data.get("technical_details", "")
                    }
                )
            elif status == "error" or not success:
                technical_error = response_data.get("technical_details", response_data.get("error", "Unknown error"))
                user_message = response_data.get("message", "Operation couldn't be completed")
                
                log_thought(
                    session_id=session_id,
                    type_name="tool_result",
                    category="error",
                    node="NovaAct",
                    content=user_message,
                    technical_details={
                        "tool_name": tool_name,
                        "arguments": tool_args,
                        "error": technical_error
                    }
                )
            else:
                result_message = response_data.get("message", "") 
                log_thought(
                    session_id=session_id,
                    type_name="tool_result",
                    category="tool",
                    node="NovaAct",
                    content=result_message or f"Tool {tool_name} execution complete",
                    technical_details={
                        "tool_name": tool_name,
                        "result": response_data,
                        "url": response_data.get("current_url", "")
                    }
                )
        
        if success and isinstance(response_data, dict) and "screenshot" in response_data:
            screenshot_data = response_data.pop("screenshot")
            
            if session_id and screenshot_data and "data" in screenshot_data:
                current_url = response_data.get("current_url", "")
                log_thought(
                    session_id=session_id,
                    type_name="visualization",
                    category="screenshot",
                    node="Browser",
                    content="Browser screenshot",
                    technical_details={
                        "screenshot": screenshot_data,
                        "url": current_url
                    }
                )
        
        messages.append(Message.tool_request(tool_use_id, tool_name, tool_args).to_dict())
        tool_result_msg = BrowserUtils.create_tool_result_with_screenshot(tool_use_id, response_data, screenshot_data)
        
        # Debug logging for tool result
        tool_result_dict = tool_result_msg.to_dict()
        logger.debug(f"Tool {tool_name} completed with ID {tool_use_id}")
        
        messages.append(tool_result_dict)
        
        return [f"[Tool {tool_name} completed]"]

    async def _capture_error_screenshot(self, error, session_id):
        """Attempt to capture a screenshot when an error occurs"""
        screenshot_data = None
        try:
            if self.browser_manager.browser_initialized and self.browser_manager.session:
                status_result = await self.browser_manager.session.call_tool("get_browser_info", {"include_screenshot": True})
                browser_info = self.browser_manager.parse_response(status_result.content[0].text)
                
                if isinstance(browser_info, dict):
                    screenshot_data = browser_info.get("screenshot")
                    current_url = browser_info.get("current_url", "")
                    
                    if session_id and screenshot_data and "data" in screenshot_data:
                        log_thought(
                            session_id=session_id,
                            type_name="visualization",
                            category="screenshot",
                            node="Browser",
                            content="Error state captured",
                            technical_details={
                                "screenshot": screenshot_data,
                                "url": current_url,
                                "error": str(error)
                            }
                        )
        except Exception as sc_error:
            logger.error("Failed to capture error screenshot", extra={"error": str(sc_error)})
        
        return screenshot_data

    def _format_instruction_text(self, tool_name, tool_args):
        """Format user-friendly instruction text based on tool name and arguments"""
        if tool_name == "act" and "instruction" in tool_args:
            return f"Instructing browser: \"{tool_args['instruction']}\""
        elif tool_name == "navigate" and "url" in tool_args:
            return f"Navigating to: {tool_args['url']}"
        elif tool_name == "extract" and "description" in tool_args:
            return f"Extracting data: {tool_args['description']}"
        else:
            return f"Calling tool: {tool_name}"

        
    async def _process_response(self, response: Dict, messages: List[Dict], bedrock_tools: List[Dict], session_id: str = None, max_turns: int = 10) -> Dict[str, str]:
        thinking_text = []
        final_answer = ""
        turn_count = 0

        while True:
            # Check for stop request at beginning of each iteration
            if session_id:
                from app.libs.core.agent_manager import get_agent_manager
                agent_manager = get_agent_manager()
                if agent_manager.is_agent_stop_requested(session_id):
                    # Handle graceful stop with early summary
                    early_stop_result = await self._handle_early_stop(
                        session_id=session_id,
                        messages=messages,
                        thinking_text=thinking_text,
                        turn_count=turn_count
                    )
                    return early_stop_result
            if response['stopReason'] == 'tool_use':
                for item in response['output']['message']['content']:
                    if 'text' in item:
                        thinking_text.append(f"{item['text']}")
                        messages.append(Message.assistant(item['text']).to_dict())
                    
                        if session_id:
                            log_thought(
                                session_id=session_id,
                                type_name="reasoning",
                                category="analysis",
                                node="Agent",
                                content=item['text']
                            )    

                    elif 'toolUse' in item:
                        tool_info = item['toolUse']
                        result = await self._handle_tool_call(tool_info, messages, session_id)
                        thinking_text.extend(result)
                        
                        response = self._make_bedrock_request(messages, bedrock_tools)
            elif response['stopReason'] == 'max_tokens':
                thinking_text.append("[Max tokens reached, ending conversation.]")
                break
            elif response['stopReason'] == 'stop_sequence':
                thinking_text.append("[Stop sequence reached, ending conversation.]")
                break
            elif response['stopReason'] == 'content_filtered':
                thinking_text.append("[Content filtered, ending conversation.]")
                break
            elif response['stopReason'] == 'end_turn':
                final_answer = response['output']['message']['content'][0]['text']
                break

            turn_count += 1
            if turn_count >= max_turns:
                thinking_text.append("\n[Max tool interactions reached. Generating final response...]")
                summary_request = {
                    "role": "user", 
                    "content": [{
                        "text": "Please provide a final summary and response based on the information gathered so far. What conclusions can you draw and what answer can you provide to my original question?"
                    }]
                }
                messages.append(summary_request)

                try:
                    final_response = self.bedrock_client.converse(
                        messages=messages,
                        system_prompt=NOVA_ACT_AGENT_PROMPT,
                        tools=bedrock_tools
                    )
                    
                    if final_response['stopReason'] == 'end_turn':
                        final_answer = final_response['output']['message']['content'][0]['text']
                    else:
                        thinking_text.append("\n[Unable to generate final summary]")
                except Exception as e:
                    thinking_text.append(f"\n[Error generating final summary: {str(e)}]")
                
                break
            
        return {
            "thinking": "\n\n".join(thinking_text),
            "answer": final_answer
        }
    
    async def _handle_early_stop(self, session_id: str, messages: List[Dict], 
                                thinking_text: List[str], turn_count: int) -> Dict[str, str]:
        """
        Handle early stop request from user at agent level.
        
        This method analyzes the current conversation state and tool interactions
        to provide a meaningful summary of work completed so far.
        
        Args:
            session_id: Current session identifier
            messages: Current conversation messages
            thinking_text: Accumulated reasoning text
            turn_count: Number of turns completed
            
        Returns:
            Dict with thinking and answer summary
        """
        
        # Send immediate stop acknowledgment
        log_thought(
            session_id=session_id,
            type_name="stop_notification",
            category="status",
            node="Agent", 
            content="Agent received stop request - Preparing work summary...",
            technical_details={
                "stop_acknowledged": True,
                "turn_count": turn_count,
                "level": "agent"
            }
        )
        
        # Generate summary of work completed so far
        summary_text = await self._generate_work_summary(messages, thinking_text, turn_count)
        
        # Add stop context to thinking text
        thinking_text.append("\n[Task stopped by user request]")
        thinking_text.append(f"\n[Work completed in {turn_count} steps]")
        
        # Return summary result
        return {
            "thinking": "\n\n".join(thinking_text),
            "answer": summary_text
        }
    
    async def _generate_work_summary(self, messages: List[Dict], thinking_text: List[str], turn_count: int) -> str:
        """
        Generate a summary of work completed so far based on conversation history.
        
        Args:
            messages: Current conversation messages
            thinking_text: Accumulated reasoning text  
            turn_count: Number of turns completed
            
        Returns:
            str: Summary of work completed
        """
        
        try:
            # Get current browser state for context
            try:
                from app.libs.core.browser_utils import BrowserUtils
                browser_state = await BrowserUtils.get_browser_state(self.browser_manager, session_id)
                current_url = browser_state.get("current_url", "")
                page_title = browser_state.get("page_title", "")
                screenshot = browser_state.get("screenshot")
            except Exception as e:
                logger.error(f"Error getting browser state for summary: {e}")
                current_url = ""
                page_title = ""
                screenshot = None
            
            # Create summary request message with browser context
            browser_context = ""
            if current_url:
                browser_context = f"\n\nCurrent browser state:\n- URL: {current_url}\n- Page: {page_title}"
            
            summary_request = {
                "role": "user",
                "content": [{
                    "text": f"The user has requested to stop the current task. Please provide a concise summary of what you've accomplished so far, any insights you've gathered, and what progress has been made toward the original goal. Be specific about what actions were completed and what information was discovered.{browser_context}"
                }]
            }
            
            # Add screenshot to summary request if available
            if screenshot and isinstance(screenshot, dict) and "data" in screenshot:
                try:
                    screenshot_bytes = base64.b64decode(screenshot["data"])
                    summary_request["content"].append({
                        "image": {
                            "format": screenshot.get("format", "jpeg"),
                            "source": {"bytes": screenshot_bytes}
                        }
                    })
                except Exception as e:
                    logger.error(f"Error processing screenshot for agent summary: {e}")
            
            # Create messages for summary generation - filter to avoid tool_use without tool_result
            summary_messages = []
            pending_tool_uses = set()
            
            for msg in messages:
                role = msg.get("role", "")
                content = msg.get("content", [])
                
                if role == "user":
                    # Check if this is a tool result message
                    is_tool_result = False
                    tool_use_id = None
                    
                    for item in content:
                        if isinstance(item, dict) and "toolResult" in item:
                            is_tool_result = True
                            tool_use_id = item["toolResult"].get("toolUseId")
                            break
                    
                    if is_tool_result and tool_use_id:
                        # This is a tool result - remove from pending if exists
                        pending_tool_uses.discard(tool_use_id)
                        continue  # Skip tool result messages for summary
                    elif not is_tool_result:
                        # Include original user messages (but not tool results)
                        summary_messages.append(msg)
                        
                elif role == "assistant":
                    # Check for tool use in assistant message
                    has_tool_use = False
                    tool_use_ids = []
                    clean_content = []
                    
                    for item in content:
                        if isinstance(item, dict):
                            if "toolUse" in item:
                                has_tool_use = True
                                tool_use_id = item["toolUse"].get("toolUseId")
                                if tool_use_id:
                                    tool_use_ids.append(tool_use_id)
                                    pending_tool_uses.add(tool_use_id)
                            elif "text" in item:
                                # Include only text content (reasoning)
                                clean_content.append(item)
                    
                    # Only include assistant message if it has meaningful text content
                    if clean_content:
                        summary_messages.append({
                            "role": "assistant",
                            "content": clean_content
                        })
            
            # Add summary request
            summary_messages.append(summary_request)
            
            # Generate summary using bedrock client
            summary_response = self.bedrock_client.converse(
                messages=summary_messages,
                system_prompt=NOVA_ACT_AGENT_PROMPT,
                tools=None  # No tools for summary generation
            )
            
            if summary_response.get('stopReason') == 'end_turn':
                summary_text = summary_response['output']['message']['content'][0]['text']
                return f"Task stopped by user request.\n\nWork Summary:\n{summary_text}"
            else:
                # Fallback if summary generation fails
                return self._create_fallback_summary(thinking_text, turn_count, current_url, page_title)
                
        except Exception as e:
            logger.error(f"Error generating work summary: {str(e)}")
            return self._create_fallback_summary(thinking_text, turn_count, "", "")
    
    def _create_fallback_summary(self, thinking_text: List[str], turn_count: int, 
                                current_url: str = "", page_title: str = "") -> str:
        """
        Create a fallback summary when AI-generated summary fails.
        
        Args:
            thinking_text: Accumulated reasoning text
            turn_count: Number of turns completed
            current_url: Current browser URL
            page_title: Current page title
            
        Returns:
            str: Fallback summary
        """
        
        # Extract key information from thinking text
        actions_completed = []
        insights_found = []
        
        for text in thinking_text:
            if "Tool" in text and "completed" in text:
                actions_completed.append(f"- {text}")
            elif any(keyword in text.lower() for keyword in ["found", "discovered", "identified", "located"]):
                insights_found.append(f"- {text[:100]}..." if len(text) > 100 else f"- {text}")
        
        summary_parts = [
            "Task stopped by user request.",
            f"\nProgress: Completed {turn_count} interaction steps"
        ]
        
        # Add browser context if available
        if current_url:
            summary_parts.append(f"\nCurrent browser state:")
            summary_parts.append(f"  - URL: {current_url}")
            summary_parts.append(f"  - Page: {page_title}")
        
        if actions_completed:
            summary_parts.append(f"\nActions completed:\n" + "\n".join(actions_completed[:5]))
            
        if insights_found:
            summary_parts.append(f"\nKey findings:\n" + "\n".join(insights_found[:3]))
            
        if not actions_completed and not insights_found:
            summary_parts.append("\nThe task was in early stages when stopped.")
            
        return "\n".join(summary_parts)