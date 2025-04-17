import time
import base64
from typing import Dict, Any, List, Optional

# Global conversation history storage
_conversation_history = []
_temp_backup_history = []


def add_to_conversation_history(role: str, content: str, screenshot_path: Optional[str] = None):
    """Add a message to the global conversation history"""
    global _conversation_history
    message = {"role": role, "content": content}
    if screenshot_path:
        message["screenshot"] = screenshot_path
    _conversation_history.append(message)


def get_initial_conversation_history():
    """Return a copy of the backup conversation history"""
    global _temp_backup_history
    return _temp_backup_history.copy()


def backup_conversation_history(history: list):
    """Update both the backup and current conversation histories"""
    global _temp_backup_history, _conversation_history
    _temp_backup_history = history.copy()
    _conversation_history = history.copy()


def get_conversation_history_for_llm(max_messages: int = 10):
    """Get recent conversation history limited to max_messages"""
    global _conversation_history
    return _conversation_history[-max_messages:] if max_messages else _conversation_history