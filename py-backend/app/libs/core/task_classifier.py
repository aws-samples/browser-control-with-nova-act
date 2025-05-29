import logging
import json
import traceback
import re
from typing import Dict, Any, Optional, List
import boto3
from app.libs.config.prompts import get_router_prompt, ROUTER_TOOL

logger = logging.getLogger("task_classifier")

class TaskClassifier:
    """Responsible for classifying user tasks into appropriate execution types."""
    
    def __init__(self, model_id: str, region: str):
        self.model_id = model_id
        self.region = region
        self.bedrock = boto3.client(service_name='bedrock-runtime', region_name=region)
    
    def extract_json_from_text(self, text: str) -> Optional[Dict]:
        """Extract properly formatted JSON from text, improved to avoid false positives."""
        try:
            # First look for JSON in code blocks
            json_pattern = r'```json\s*({[\s\S]*?})\s*```'
            matches = re.findall(json_pattern, text, re.DOTALL)
            
            # If no code blocks, look for JSON with more strict pattern
            if not matches:
                json_pattern = r'({[\s\n]*"type"[\s\n]*:[\s\n]*"(navigate|act|agent)"[\s\S]*?})'
                matches = re.findall(json_pattern, text, re.DOTALL)
                matches = [m[0] for m in matches] if matches else []
            
            for potential_json in matches:
                try:
                    parsed_json = json.loads(potential_json.strip())
                    # Schema validation: check for type field with valid value
                    if "type" in parsed_json and parsed_json["type"] in ["navigate", "act", "agent"]:
                        # For navigate type, ensure url field exists
                        if parsed_json["type"] == "navigate":
                            if "url" not in parsed_json:
                                parsed_json["url"] = "https://www.google.com"
                        return parsed_json
                except json.JSONDecodeError:
                    continue
            return None
        except Exception as e:
            logger.error(f"Error in extract_json_from_text: {str(e)}")
            return None

    async def classify(self, user_message: str, session_id: str, conversation_history: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Classify a user message into an appropriate task type.
        
        Args:
            user_message: The current user message to classify
            session_id: The session identifier
            conversation_history: Optional conversation history for context
            
        Returns:
            Classification result with type and other relevant information
        """
        try:            
            # Get browser context if available
            browser_context = await self._get_browser_context(session_id)
            
            # Prepare messages with browser context
            filtered_messages = self._prepare_messages_with_context(
                user_message, conversation_history, browser_context
            )
            
            # Clean up images from conversation history (preserve current browser screenshot)
            self._cleanup_conversation_images(filtered_messages)
            # Call model with Nova-optimized parameters
            inference_config = {"temperature": 0.1, "maxTokens": 1000}
            
            # Add greedy decoding parameters for Nova models
            if "nova" in self.model_id.lower():
                inference_config.update({
                    "temperature": 0.0,
                    "topP": 1.0
                })
                # Add additional model request fields for Nova
                additional_fields = {"inferenceConfig": {"topK": 1}}
            else:
                additional_fields = {}
            
            converse_params = {
                "modelId": self.model_id,
                "system": [{"text": get_router_prompt()}],
                "messages": filtered_messages,
                "inferenceConfig": inference_config,
                "toolConfig": {
                    **ROUTER_TOOL,
                    "toolChoice": {"auto": {}}
                }
            }
            
            # Add Nova-specific parameters if using Nova model
            if additional_fields:
                converse_params["additionalModelRequestFields"] = additional_fields
            
            response = self.bedrock.converse(**converse_params)

            # Get direct response text first
            direct_response = ""
            for item in response['output']['message']['content']:
                if 'text' in item:
                    direct_response = item['text']
                    break
            
            # Default classification with user message
            classification = {
                "user_message": user_message,
                "type": "conversation",  
                "answer": direct_response 
            }
            
            # Check for Tool Use
            if response['stopReason'] == 'tool_use':
                for item in response['output']['message']['content']:
                    if 'toolUse' in item:
                        tool_info = item['toolUse']
                        tool_name = tool_info['name']
                        
                        if tool_name == "classifyRequest":
                            tool_input = tool_info.get('input', {})
                            classification_type = tool_input.get('type')
                            
                            if classification_type in ["navigate", "act", "agent"]:
                                classification["type"] = classification_type
                                
                                if classification_type == "navigate" and "url" in tool_input:
                                    classification["details"] = tool_input["url"]
                        elif tool_name in ["navigate", "act", "agent"]:
                            classification["type"] = tool_name
                            
                            if tool_name == "navigate":
                                input_data = tool_info.get('input', {})
                                if isinstance(input_data, dict):
                                    for key, value in input_data.items():
                                        if key in ["url", "details"] and isinstance(value, str) and value.startswith("http"):
                                            classification["details"] = value
                                            break
                
                return classification
            
            # If no tool use, check for JSON in text
            extracted_json = self.extract_json_from_text(direct_response)
            if extracted_json and "type" in extracted_json:
                classification["type"] = extracted_json["type"]
                
                if extracted_json["type"] == "navigate" and "url" in extracted_json:
                    url = extracted_json["url"]
                    if url and isinstance(url, str) and len(url) > 0:
                        classification["details"] = url
                
                return classification
            
            # Return conversational response
            return classification
                
        except Exception as e:
            logger.error(f"Error during task classification: {e}")
            
            return {
                "type": "conversation",
                "answer": f"I encountered an error, but I'll try to help: {str(e)}",
                "user_message": user_message
            }

    def _prepare_messages_with_context(self, user_message: str, conversation_history: List[Dict[str, Any]], browser_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Prepare messages with browser context enhancement."""
        if conversation_history:
            from app.libs.data.conversation_manager import prepare_messages_for_bedrock
            filtered_messages = prepare_messages_for_bedrock(conversation_history)
            
            # Enhance the last user message with browser context if available
            if browser_context["has_browser"] and filtered_messages:
                self._enhance_last_user_message(filtered_messages, user_message, browser_context)
            else:
                # Add current user message if not already present
                self._add_current_user_message_if_needed(filtered_messages, user_message)
        else:
            # No conversation history - create user message with browser context if available
            filtered_messages = self._create_user_message_with_context(user_message, browser_context)
            
        return filtered_messages
    
    def _enhance_last_user_message(self, messages: List[Dict[str, Any]], user_message: str, browser_context: Dict[str, Any]) -> None:
        """Enhance the last user message with browser context."""
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                # Get original text from the last user message  
                original_text = user_message
                if messages[i]["content"] and isinstance(messages[i]["content"], list):
                    for content_item in messages[i]["content"]:
                        if isinstance(content_item, dict) and "text" in content_item:
                            original_text = content_item["text"]
                            break
                
                # Create enhanced content with browser context
                context_text = f"Current browser context:\n- URL: {browser_context['current_url']}\n- Page: {browser_context['page_title']}\n\nUser request: {original_text}"
                enhanced_content = [{"text": context_text}]
                
                # Add screenshot if available
                if browser_context.get("screenshot_bytes"):
                    enhanced_content.append({
                        "image": {
                            "format": browser_context.get("screenshot_format", "jpeg"),
                            "source": {"bytes": browser_context["screenshot_bytes"]}
                        }
                    })
                
                # Replace the content of the last user message
                messages[i]["content"] = enhanced_content
                break
    
    def _add_current_user_message_if_needed(self, messages: List[Dict[str, Any]], user_message: str) -> None:
        """Add current user message if not already present."""
        if not messages or messages[-1]["role"] != "user" or \
           (messages[-1]["content"] and messages[-1]["content"][0].get("text") != user_message):
            messages.append({
                "role": "user",
                "content": [{"text": user_message}]
            })
    
    def _create_user_message_with_context(self, user_message: str, browser_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create user message with browser context if available."""
        if browser_context["has_browser"]:
            # Create enhanced content with browser context
            context_text = f"Current browser context:\n- URL: {browser_context['current_url']}\n- Page: {browser_context['page_title']}\n\nUser request: {user_message}"
            enhanced_content = [{"text": context_text}]
            
            # Add screenshot if available
            if browser_context.get("screenshot_bytes"):
                enhanced_content.append({
                    "image": {
                        "format": browser_context.get("screenshot_format", "jpeg"),
                        "source": {"bytes": browser_context["screenshot_bytes"]}
                    }
                })
            
            return [{"role": "user", "content": enhanced_content}]
        else:
            # Simple user message without browser context
            return [{"role": "user", "content": [{"text": user_message}]}]
    
    def _cleanup_conversation_images(self, messages: List[Dict[str, Any]]) -> None:
        """Remove images from conversation history but preserve current browser screenshot."""
        for i, message in enumerate(messages):
            if "content" in message and isinstance(message["content"], list):
                # Clean up tool result images
                for content_item in message["content"]:
                    if isinstance(content_item, dict) and "toolResult" in content_item:
                        tool_result = content_item["toolResult"]
                        if "content" in tool_result and isinstance(tool_result["content"], list):
                            tool_result["content"] = [
                                item for item in tool_result["content"]
                                if isinstance(item, dict) and "image" not in item
                            ]
                            # Add placeholder if tool result becomes empty
                            if not tool_result["content"]:
                                tool_result["content"] = [{"text": "Screenshot processed"}]
                
                # Remove message-level images, except for the last user message (current context)
                is_last_user_message = (i == len(messages) - 1 and message["role"] == "user")
                if not is_last_user_message:
                    message["content"] = [
                        content_item for content_item in message["content"]
                        if not (isinstance(content_item, dict) and "image" in content_item)
                    ]
    
    async def _get_browser_context(self, session_id: str) -> Dict[str, Any]:
        """Get browser context including screenshot if browser is initialized."""
        context = {"has_browser": False}
        
        try:
            # Use BaseTaskExecutor to get browser state
            from app.libs.core.task_executors import BaseTaskExecutor
            base_executor = BaseTaskExecutor(self.model_id, self.region)
            browser_state = await base_executor.get_browser_state(session_id)
            
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
                        logger.warning(f"Failed to process screenshot for classification: {e}")
        
        except Exception as e:
            logger.debug(f"Could not get browser context: {e}")
            
        return context

    def update_model(self, model_id: Optional[str] = None, region: Optional[str] = None):
        """Update the model ID and/or region for classification."""
        if model_id:
            self.model_id = model_id
        if region:
            self.region = region
            self.bedrock = boto3.client(service_name='bedrock-runtime', region_name=region)