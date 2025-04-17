"""
Type definitions for browser automation workflows

This module defines types used across the codebase to prevent circular imports.
"""

from enum import Enum, auto
from typing import Dict, Any, List, Optional, TypedDict, Union

from .browser_controller import BrowserController
from nova_act import NovaAct

class ProcessingType(Enum):
    """Type of processing required for the query"""
    DIRECT_ANSWER = auto()  # Can answer directly without browser
    BROWSER_TASK = auto()   # Requires browser automation
    FINAL_ANSWER = auto()   # Processing completed answer

# Define the graph state type for the browser automation workflow
class BrowserWorkflowState(TypedDict):
    question: str
    processing_type: str
    direct_answer: str
    refined_question: str
    
    tasks: List[Dict[str, Any]] 
    start_url: str
    headless: bool
    record_video: bool
    parallel_mode: bool
    is_casual: bool
    
    current_task_index: int
    current_task: Dict[str, Any]
    current_result: str
    task_results: List[Dict[str, Any]]  # List to store all task results
    
    browser_initialized: bool
    browser_controller: BrowserController
    nova_instance: NovaAct
    
    answer: str
    screenshots: List[str]  
    error: Optional[str]
    complete: bool
    conversation_history: List[Dict[str, Any]]

    callback_handler: Any
