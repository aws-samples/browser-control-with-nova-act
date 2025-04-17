"""
Nova Act App Core Module

This module provides core functionality for browser automation using Nova Act.
"""

# Import types first to avoid circular imports
from .types import ProcessingType, BrowserWorkflowState

from .browser_controller import BrowserController
from .tools import create_decision_tools
from .schemas import (
    BoolSchema,
    ProductSchema,
    SearchResultSchema,
    FormFieldsSchema,
    NavigationSchema
)
from .inline_agent import (
    initialize_browser_from_state,
    create_browser_inline_agent,
    run_browser_agent_with_state,
    BrowserState,
    MouseBrowserTool,
    KeyboardBrowserTool,
    ExtractElementTool,
    ExtractDataTool,
    CollectResultTool
)

from .callbacks import (
    BedrockCompatibleCallback,
    queue_text,
    queue_thinking,
    queue_tool_call,
    queue_tool_result,
    queue_screenshot,
    queue_error,
    queue_status,
    process_event_queue,
    event_processing_loop
)

# Import workflow functions after types
from .graph import create_browser_workflow

# Import node functions
from .nodes import (
    chat_node,
    plan_node, 
    executor_node, 
    answer_gen_node
)

__all__ = [
    # Types
    'ProcessingType',
    'BrowserWorkflowState',
    
    # Browser controller
    'BrowserController',
    
    # Tools
    'create_decision_tools',
    
    # Schemas
    'BoolSchema',
    'ProductSchema',
    'SearchResultSchema',
    'FormFieldsSchema',
    'NavigationSchema',
    
    # Inline agent
    'initialize_browser_from_state',
    'create_browser_inline_agent',
    'run_browser_agent_with_state',
    'BrowserState',
    'MouseBrowserTool',
    'KeyboardBrowserTool',
    'DirectControlBrowserTool',
    'ExtractElementTool',
    'ExtractDataTool',
    'CollectResultTool',
    
    # LangGraph workflow
    'create_browser_workflow',
    'chat_node',
    'plan_node',
    'executor_node',   
    'answer_gen_node',

    # Callbacks
    'BedrockCompatibleCallback',
    'queue_text',
    'queue_thinking',
    'queue_tool_call',
    'queue_tool_result',
    'queue_screenshot',
    'queue_error',
    'queue_status',
    'process_event_queue',
    'event_processing_loop'
]