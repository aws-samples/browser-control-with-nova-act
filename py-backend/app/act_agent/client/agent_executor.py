import asyncio
import base64
import json
import time
from typing import Dict, List, Any
import boto3
from app.libs.prompts import NOVA_ACT_AGENT_PROMPT, DEFAULT_MODEL_ID
from app.libs.decorators import log_thought
from app.libs.message import Message
from app.libs.browser_utils import BrowserUtils, BedrockClient

EXCLUDED_TOOLS = ["close_browser", "initialize_browser", "restart_browser", "take_screenshot"]

class AgentExecutor:
    def __init__(self, browser_agent):
        self.browser_agent = browser_agent
        region = (self.browser_agent.server_config or {}).get("region", "us-west-2")
        self.bedrock_client = BedrockClient(
            self.browser_agent.server_config.get("model_id", DEFAULT_MODEL_ID), 
            region
        )
        
    def _make_bedrock_request(self, messages: List[Dict], tools: List[Dict]) -> Dict:
        model_id = self.browser_agent.server_config.get("model_id", DEFAULT_MODEL_ID)
        return self.bedrock_client.converse(
            messages=messages, 
            system_prompt=NOVA_ACT_AGENT_PROMPT,
            tools=tools
        )
    
    async def execute(self, request: str, session_id: str = None, max_turns: int = 10, 
                    current_url: str = None, supervisor_screenshot: dict = None, **kwargs):
        """Execute method with screenshot handling"""
        if not self.browser_agent.session:
            raise ValueError("Not connected to MCP server")
                
        if not self.browser_agent.browser_initialized:
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
                
            # Sync browser URL if needed
            # if current_url and current_url.startswith("http"):
            #     try:
            #         status_result = await self.browser_agent.session.call_tool("get_browser_info", {})
            #         browser_info = self.browser_agent.parse_response(status_result.content[0].text)
            #         browser_url = browser_info.get("current_url", "")
                    
            #         if browser_url != current_url:
            #             print(f"Synchronizing browser state to URL: {current_url}")
            #             await self.browser_agent.session.call_tool("navigate", {"url": current_url})
            #             await asyncio.sleep(0.5)  # Brief delay after navigation
            #     except Exception as e:
            #         print(f"URL sync failed: {e}")
            
            # Prepare message content
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
                    print(f"Error processing supervisor screenshot: {e}")
            else:
                print(f"No supervisor screenshot available, continuing without it")
            
            # Create message and prepare tools
            messages = [{"role": "user", "content": message_content}]
            
            response = await self.browser_agent.session.list_tools()
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
            final_state = await BrowserUtils.get_browser_state(self.browser_agent, session_id)
            
            return {
                "answer": result.get("answer", ""),
                "screenshot": final_state.get("screenshot"),
                "current_url": final_state.get("current_url", ""),
                "page_title": final_state.get("page_title", "")
            }
            
        except Exception as e:
            # Try to get state even on error
            error_state = await BrowserUtils.get_browser_state(self.browser_agent, session_id=None)
            
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

            print(f"Error executing chat task: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                "error": str(e),
                "screenshot": error_state.get("screenshot"),
                "current_url": error_state.get("current_url", ""),
                "page_title": error_state.get("page_title", "")
            }
    
    async def _sync_browser_url(self, target_url):
        try:
            status_result = await self.browser_agent.session.call_tool("get_browser_info", {})
            browser_info = self.browser_agent.parse_response(status_result.content[0].text)
            browser_url = browser_info.get("current_url", "")
            
            if browser_url != target_url:
                print(f"\nSynchronizing browser state to URL: {target_url}")
                await self.browser_agent.session.call_tool("navigate", {"url": target_url})
        except Exception as e:
            print(f"\nError synchronizing browser URL: {e}")
            
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
            result = await self.browser_agent.session.call_tool(tool_name, tool_args)
            response_data = self.browser_agent.parse_response(result.content[0].text)
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
            
            error_state = await BrowserUtils.capture_screenshot(self.browser_agent, session_id, include_log=False)
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
        messages.append(tool_result_msg.to_dict())
        
        return [f"[Tool {tool_name} completed]"]

    async def _capture_error_screenshot(self, error, session_id):
        """Attempt to capture a screenshot when an error occurs"""
        screenshot_data = None
        try:
            if self.browser_agent.browser_initialized and self.browser_agent.session:
                status_result = await self.browser_agent.session.call_tool("get_browser_info", {"include_screenshot": True})
                browser_info = self.browser_agent.parse_response(status_result.content[0].text)
                
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
            print(f"Failed to capture error screenshot: {sc_error}")
        
        return screenshot_data

    def _format_instruction_text(self, tool_name, tool_args):
        """Format user-friendly instruction text based on tool name and arguments"""
        if tool_name == "act" and "instruction" in tool_args:
            return f"Instructing browser: \"{tool_args['instruction']}\""
        elif tool_name == "navigate" and "url" in tool_args:
            return f"Navigating to: {tool_args['url']}"
        elif tool_name == "extract_data" and "description" in tool_args:
            return f"Extracting data: {tool_args['description']}"
        else:
            return f"Calling tool: {tool_name}"

        
    def _create_tool_result_with_screenshot(self, tool_use_id: str, response_data: dict, screenshot_data: dict = None) -> Message:
        message_content = []
        
        # Create a clean version of response_data without screenshot
        clean_data = response_data.copy() if response_data else {}
        if "screenshot" in clean_data:
            del clean_data["screenshot"]
            
        if clean_data:
            message_content.append({"json": clean_data})
        
        # Add screenshot as separate image component
        if screenshot_data and isinstance(screenshot_data, dict) and 'data' in screenshot_data:
            try:
                screenshot_bytes = base64.b64decode(screenshot_data['data'])
                message_content.append({
                    "image": {
                        "format": screenshot_data.get('format', 'jpeg'),
                        "source": {
                            "bytes": screenshot_bytes
                        }
                    }
                })
            except Exception as e:
                print(f"Error decoding screenshot: {e}")
        
        return Message(
            role="user",
            content=[{
                "toolResult": {
                    "toolUseId": tool_use_id,
                    "content": message_content,
                    "status": "success"
                }
            }]
        )
        
    async def _process_response(self, response: Dict, messages: List[Dict], bedrock_tools: List[Dict], session_id: str = None, max_turns: int = 10) -> Dict[str, str]:
        thinking_text = []
        final_answer = ""
        turn_count = 0

        while True:
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