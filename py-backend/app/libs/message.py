import base64
from typing import Dict, List, Any
from dataclasses import dataclass

@dataclass
class Message:
    role: str
    content: List[Dict[str, Any]]

    @classmethod
    def user(cls, text: str) -> 'Message':
        return cls(role="user", content=[{"text": text}])

    @classmethod
    def assistant(cls, text: str) -> 'Message':
        return cls(role="assistant", content=[{"text": text}])

    @classmethod
    def tool_result(cls, tool_use_id: str, content: dict) -> 'Message':
        message_content = []
        
        # Create a clean version of content without screenshot for JSON
        if isinstance(content, dict):
            clean_content = content.copy()
            if "screenshot" in clean_content:
                del clean_content["screenshot"]
            message_content.append({"json": clean_content})
            
            # Add screenshot as a separate image component
            if "screenshot" in content and isinstance(content["screenshot"], dict) and "data" in content["screenshot"]:
                try:
                    screenshot_data = content["screenshot"]
                    screenshot_bytes = base64.b64decode(screenshot_data["data"])
                    message_content.append({
                        "image": {
                            "format": screenshot_data.get("format", "jpeg"),
                            "source": {
                                "bytes": screenshot_bytes
                            }
                        }
                    })
                except Exception as e:
                    print(f"Error decoding screenshot: {e}")
        
        return cls(
            role="user",
            content=[{
                "toolResult": {
                    "toolUseId": tool_use_id,
                    "content": message_content,
                    "status": "success"
                }
            }]
        )

    @classmethod
    def tool_request(cls, tool_use_id: str, name: str, input_data: dict) -> 'Message':
        return cls(
            role="assistant",
            content=[{
                "toolUse": {
                    "toolUseId": tool_use_id,
                    "name": name,
                    "input": input_data
                }
            }]
        )

    @staticmethod
    def to_bedrock_format(tools_list: List[Dict]) -> List[Dict]:
        results = []
        for tool in tools_list:
            tool_spec = {
                "toolSpec": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": tool["input_schema"]["properties"],
                        }
                    }
                }
            }
            
            if "required" in tool["input_schema"] and tool["input_schema"]["required"]:
                tool_spec["toolSpec"]["inputSchema"]["json"]["required"] = tool["input_schema"]["required"]
            
            results.append(tool_spec)
        return results

    def to_dict(self):
        return {
            "role": self.role,
            "content": self.content
        }