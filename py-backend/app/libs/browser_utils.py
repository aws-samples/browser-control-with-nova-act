import base64
import boto3
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger("browser_utils")

class BrowserUtils:
    @staticmethod
    async def get_browser_state(browser_agent, session_id=None, include_log=True):
        """
        Get browser state including URL, title, and screenshot using the take_screenshot tool
        """
        state = {
            "browser_initialized": False,
            "current_url": "",
            "page_title": "",
            "screenshot": None
        }
        
        if not browser_agent or not browser_agent.browser_initialized or not browser_agent.session:
            logger.warning("Cannot get browser state: browser not initialized")
            return state
        
        try:
            # Direct tool call for all browser state information
            result = await browser_agent.session.call_tool("take_screenshot", {})
            response_data = browser_agent.parse_response(result.content[0].text)
            
            if isinstance(response_data, dict):
                state["browser_initialized"] = True
                state["current_url"] = response_data.get("current_url", "")
                state["page_title"] = response_data.get("page_title", "")
                state["screenshot"] = response_data.get("screenshot")
                
                # Optional logging
                if include_log and session_id and state["screenshot"] and "data" in state["screenshot"]:
                    from app.libs.decorators import log_thought
                    log_thought(
                        session_id=session_id,
                        type_name="visualization",
                        category="screenshot",
                        node="Browser",
                        content="Browser state retrieved",
                        technical_details={
                            "screenshot": state["screenshot"],
                            "url": state["current_url"]
                        }
                    )
        except Exception as e:
            logger.error(f"Error getting browser state: {e}")
        
        return state
    
    @staticmethod
    def create_tool_result_with_screenshot(tool_use_id, response_data, screenshot_data=None):
        """
        Create a formatted tool result message with optional screenshot
        """
        from app.libs.message import Message
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
                logger.error(f"Error decoding screenshot: {e}")
        
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


class BedrockClient:
    def __init__(self, model_id, region):
        self.model_id = model_id
        self.region = region
        self.client = boto3.client('bedrock-runtime', region_name=region)
    
    def update_config(self, model_id=None, region=None):
        if model_id:
            self.model_id = model_id
        if region:
            self.region = region
            self.client = boto3.client('bedrock-runtime', region_name=region)
    
    def converse(self, messages, system_prompt, tools=None, temperature=0.1):
        # Filter messages for Bedrock API compatibility if needed
        from app.libs.conversation_manager import prepare_messages_for_bedrock
        filtered_messages = prepare_messages_for_bedrock(messages)
        
        request_params = {
            "modelId": self.model_id,
            "messages": filtered_messages,
            "system": [{'text': system_prompt}],
            "inferenceConfig": {"temperature": temperature}
        }
        
        if isinstance(tools, dict) and 'tools' in tools:
            request_params["toolConfig"] = {"tools": tools['tools']}
        else:
            request_params["toolConfig"] = {"tools": tools}
        
        return self.client.converse(**request_params)
