import logging
import json
import time
import base64
from typing import Dict, List, Any, Optional, Union
from datetime import datetime

from app.libs.conversation_store import ConversationStore
from app.libs.message import Message

logger = logging.getLogger("conversation_manager")

def prepare_messages_for_bedrock(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter conversation messages to only include fields accepted by Bedrock API.
    
    Args:
        messages: The original conversation messages with possible extra fields
        
    Returns:
        Filtered messages with only 'role' and 'content' fields
    """
    filtered_messages = []
    for msg in messages:
        filtered_msg = {
            "role": msg["role"],
            "content": msg["content"]
        }
        filtered_messages.append(filtered_msg)
    
    logger.debug(f"Prepared {len(filtered_messages)} messages for Bedrock API")
    return filtered_messages

class ConversationManager:
    """Manages conversation history with consistent message formatting for all interaction types.
    This class provides methods to add various types of messages to the conversation history.
    """
    
    def __init__(self, store: ConversationStore):
        """Initialize the conversation manager with a storage backend."""
        self.store = store
    
    async def ensure_session(self, session_id: str) -> bool:
        """Ensure a session exists in the store.
        
        Args:
            session_id: The session identifier
            
        Returns:
            True if session exists or was created, False on error
        """
        try:
            if not await self.store.exists(session_id):
                logger.info(f"Initializing new conversation for session: {session_id}")
                return await self.store.save(session_id, [])
            return True
        except Exception as e:
            logger.error(f"Failed to ensure session {session_id}: {e}")
            return False
    
    async def add_user_message(self, session_id: str, content: str) -> bool:
        """Add a user message to the conversation.
        
        Args:
            session_id: The session identifier
            content: The message content
            
        Returns:
            True if successful, False otherwise
        """
        try:
            await self.ensure_session(session_id)
            messages = await self.store.load(session_id)
            
            message = {
                "role": "user",
                "content": [{"text": content}],
                "timestamp": datetime.now().isoformat()
            }
            
            messages.append(message)
            logger.debug(f"Adding user message to session {session_id}: {content[:50]}...")
            return await self.store.save(session_id, messages)
        except Exception as e:
            logger.error(f"Failed to add user message for session {session_id}: {e}")
            return False
    
    async def add_assistant_message(self, session_id: str, content: str, source: str = "direct_response") -> bool:
        """Add an assistant message to the conversation.
        
        Args:
            session_id: The session identifier
            content: The message content
            source: The source of the message (optional)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            await self.ensure_session(session_id)
            messages = await self.store.load(session_id)
            
            message = {
                "role": "assistant",
                "content": [{"text": content}],
                "timestamp": datetime.now().isoformat(),
                "metadata": {"source": source}
            }
            
            messages.append(message)
            logger.debug(f"Adding assistant message to session {session_id} from {source}: {content[:50]}...")
            return await self.store.save(session_id, messages)
        except Exception as e:
            logger.error(f"Failed to add assistant message for session {session_id}: {e}")
            return False
    
    async def add_tool_usage(self, session_id: str, tool_name: str, tool_args: Dict, tool_use_id: str = None) -> str:
        """Add a tool usage message to the conversation.
        
        Args:
            session_id: The session identifier
            tool_name: The name of the tool being used
            tool_args: The arguments provided to the tool
            tool_use_id: Optional tool use ID (generated if not provided)
            
        Returns:
            The tool use ID
        """
        try:
            await self.ensure_session(session_id)
            messages = await self.store.load(session_id)
            
            # Generate tool use ID if not provided
            if tool_use_id is None:
                tool_use_id = f"{tool_name}-{int(time.time())}"
            
            # Use Message class for consistency
            message = Message.tool_request(tool_use_id, tool_name, tool_args)
            message_dict = message.to_dict()
            message_dict["timestamp"] = datetime.now().isoformat()
            
            messages.append(message_dict)
            logger.debug(f"Adding tool usage for {tool_name} to session {session_id}, tool_use_id: {tool_use_id}")
            await self.store.save(session_id, messages)
            return tool_use_id
        except Exception as e:
            logger.error(f"Failed to add tool usage for session {session_id}: {e}")
            return ""
    
    async def add_tool_result(self, session_id: str, tool_use_id: str, result: Dict[str, Any], status: str = "success") -> None:
        """Add a tool result to the conversation."""
        messages = await self.store.load(session_id)
        
        # Use Message class for consistency
        tool_result_message = Message.tool_result(tool_use_id, result)
        message_dict = tool_result_message.to_dict()
        message_dict["timestamp"] = datetime.now().isoformat()
        
        # Add to conversation history
        messages.append(message_dict)
        await self.store.save(session_id, messages)

    
    async def get_conversation_history(self, session_id: str, max_messages: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get the conversation history for a session.
        
        Args:
            session_id: The session identifier
            max_messages: Optional maximum number of messages to return
            
        Returns:
            List of message objects
        """
        try:
            if not await self.store.exists(session_id):
                return []
                
            messages = await self.store.load(session_id)
            
            if max_messages and len(messages) > max_messages:
                logger.debug(f"Trimming conversation history from {len(messages)} to {max_messages} messages")
                messages = messages[-max_messages:]
                
            return messages
        except Exception as e:
            logger.error(f"Failed to get conversation history for session {session_id}: {e}")
            return []
    
    async def clear_conversation(self, session_id: str) -> bool:
        """Clear the conversation history for a session.
        
        Args:
            session_id: The session identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not await self.store.exists(session_id):
                return True
                
            logger.info(f"Clearing conversation for session {session_id}")
            return await self.store.save(session_id, [])
        except Exception as e:
            logger.error(f"Failed to clear conversation for session {session_id}: {e}")
            return False