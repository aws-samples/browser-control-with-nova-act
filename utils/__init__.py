"""
Nova Act Chatbot utilities package.

Provides browser management and chat utilities for the Nova Act Chatbot.
"""

from .browser_manager import (
    execute_action,
    take_screenshot,
    get_current_url,
    get_page_title,
    close_browser,
    start_browser_thread,
    get_browser_controller,
    is_browser_ready,
    get_browser_error,
    config
)

from .chat_utils import (
    add_to_conversation_history,
    get_conversation_history_for_llm,
    get_initial_conversation_history,
    backup_conversation_history
)

__all__ = [
    # Browser management
    'execute_action',
    'take_screenshot',
    'get_current_url',
    'get_page_title',
    'close_browser',
    'start_browser_thread',
    'get_browser_controller',
    'is_browser_ready',
    'get_browser_error',
    'config',
    
    # Chat utilities
    'add_to_conversation_history',
    'get_conversation_history_for_llm',
    'get_initial_conversation_history',
    'backup_conversation_history'
]