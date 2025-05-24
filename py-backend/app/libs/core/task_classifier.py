import logging
import json
import traceback
import re
from typing import Dict, Any, Optional, List
import boto3
from app.libs.config.prompts import ROUTER_PROMPT, ROUTER_TOOL

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
        """Classify a user message into an appropriate task type."""
        try:            
            # Prepare messages once - no double filtering
            if conversation_history:
                from app.libs.data.conversation_manager import prepare_messages_for_bedrock
                filtered_messages = prepare_messages_for_bedrock(conversation_history)
            else:
                filtered_messages = [{"role": "user", "content": [{"text": user_message}]}]

            # Call model
            response = self.bedrock.converse(
                modelId=self.model_id,
                system=[{"text": ROUTER_PROMPT}],
                messages=filtered_messages,
                inferenceConfig={"temperature": 0.1, "maxTokens": 1000},
                toolConfig=ROUTER_TOOL
            )

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
                        
                        if tool_name == "classify_request":
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
            logger.error(traceback.format_exc())
            
            return {
                "type": "conversation",
                "answer": f"I encountered an error, but I'll try to help: {str(e)}",
                "user_message": user_message
            }


    def update_model(self, model_id: Optional[str] = None, region: Optional[str] = None):
        """Update the model ID and/or region for classification."""
        if model_id:
            self.model_id = model_id
        if region:
            self.region = region
            self.bedrock = boto3.client(service_name='bedrock-runtime', region_name=region)