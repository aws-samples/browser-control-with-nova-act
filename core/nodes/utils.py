"""
Utility functions for graph node operations

This module provides helper functions used across different graph nodes.
"""

import json
from typing import Dict, Any

from ..config import DEFAULT_BROWSER_SETTINGS
from ..types import BrowserWorkflowState

def handle_text_response(state: BrowserWorkflowState, content: str) -> Dict[str, Any]:
    """
    Extract a plan from unstructured text response when the tool call approach fails
    
    Args:
        state: Current workflow state
        content: Text content from LLM response
        
    Returns:
        Updated workflow state with task plan
    """
    # Check if this might be a casual response
    if len(content) < 200 and ("I can help" in content or "Hello" in content or "Hi" in content):
        return {
            "answer": content,
            "is_casual": True,
            "complete": True
        }
    
    try:
        # Look for JSON block in response
        json_start = content.find('{')
        json_end = content.rfind('}') + 1
        
        if json_start >= 0 and json_end > json_start:
            plan_json = content[json_start:json_end]
            plan = json.loads(plan_json)
            
            formatted_tasks = []
            raw_tasks = plan.get("tasks", [])
            
            for i, task in enumerate(raw_tasks):
                if isinstance(task, dict) and "description" in task:
                    formatted_tasks.append({
                        "id": i + 1,
                        "description": task["description"],
                        "completed": False
                    })
                elif isinstance(task, str):
                    formatted_tasks.append({
                        "id": i + 1,
                        "description": task,
                        "completed": False
                    })
            
            return {
                "tasks": formatted_tasks,
                "start_url": plan.get("start_url", DEFAULT_BROWSER_SETTINGS["start_url"]),
                "current_task_index": 0,
                "browser_initialized": False,
                "headless": state.get("headless", DEFAULT_BROWSER_SETTINGS["headless"]),
                "parallel_mode": state.get("parallel_mode", DEFAULT_BROWSER_SETTINGS["parallel_mode"]),
                "is_casual": False
            }
    except:
        logger.debug(f"Ignored error: {e}")
    
    # Create a simple plan from the text response
    tasks = []
    lines = content.split('\n')
    
    for i, line in enumerate(lines):
        if (line.strip().startswith(str(i+1) + ".") or 
            line.strip().startswith("-") or 
            line.strip().startswith("*") or
            "task" in line.lower() or 
            "step" in line.lower()):
            
            # Extract the task description
            parts = line.strip().split(".", 1)
            if len(parts) > 1:
                task_desc = parts[1].strip()
            else:
                task_desc = line.strip().lstrip("-*").strip()
                
            if task_desc:
                tasks.append({
                    "id": i + 1,
                    "description": task_desc,
                    "completed": False
                })
    
    # If no tasks were found, create a single task
    if not tasks:
        tasks = [{"id": 1, "description": f"Complete task: {state['question']}", "completed": False}]
    
    # Extract URL if mentioned
    start_url = DEFAULT_BROWSER_SETTINGS["start_url"]
    for line in lines:
        if 'http://' in line or 'https://' in line:
            for word in line.split():
                if word.startswith('http'):
                    start_url = word.strip('.,;:()"\'')
                    break
    
    return {
        "tasks": tasks,
        "start_url": start_url,
        "current_task_index": 0,
        "browser_initialized": False,
        "is_casual": False
    }