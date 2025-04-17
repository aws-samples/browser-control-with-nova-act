"""
Executor node for task execution
"""

import logging
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..types import BrowserWorkflowState
from ..config import DEFAULT_BROWSER_SETTINGS
from ..inline_agent import run_browser_agent_with_state
from ..callbacks import queue_tool_call, queue_tool_result, queue_thinking

logger = logging.getLogger("nova_nodes.executor")

def executor_node(state: BrowserWorkflowState) -> Dict[str, Any]:
    """Execute tasks sequentially or in parallel based on configuration"""
    
    logger.info("Executing tasks...")
    
    # Get callback handler from state
    callback_handler = state.get("callback_handler")
    if callback_handler:
        callback_handler.set_active_node("executor")
    
    # Check for tasks
    if not state.get("tasks", []):
        return {"error": "No tasks to execute", "answer": "No tasks to execute", "complete": True}
    
    # Get remaining tasks
    current_task_index = state.get("current_task_index", 0)
    remaining_tasks = state["tasks"][current_task_index:]
    if not remaining_tasks:
        return {"complete": True}
    
    # Group tasks by sequence and get current batch
    current_tasks = get_current_task_batch(remaining_tasks)
    
    # Prepare for execution
    all_results = []
    all_screenshots = []
    task_results = state.get("task_results", []).copy()
    tasks = state["tasks"].copy()
    
    # Configure execution mode
    execution_config = configure_execution_mode(state, current_tasks)
    
    # Use specific node_id for each task
    for task in current_tasks:
        task_id = str(task.get("id"))
        if callback_handler:
            callback_handler.set_active_node(f"executor_{task_id}")
    
    try:
        execution_results = execute_tasks(current_tasks, state, execution_config)
        
        # Update with structured results
        tasks, all_results, structured_results = process_execution_results(
            execution_results, tasks, state
        )
        
        # Determine if workflow is complete
        is_complete, next_task_index = check_workflow_completion(
            remaining_tasks, current_tasks, current_task_index
        )
        
        # Combine all results
        combined_result = format_combined_results(all_results, current_tasks)
        
        # Original task_results with added structured results
        updated_task_results = state.get("task_results", []).copy()
        updated_task_results.extend(structured_results)
        
        # Get conversation history to maintain throughout workflow
        conversation_history = state.get("conversation_history", [])
        
        return {
            "tasks": tasks,
            "current_result": combined_result,
            "task_results": updated_task_results,  # Include structured results
            "current_task_index": next_task_index,
            "complete": is_complete,
            "conversation_history": conversation_history  # Maintain conversation history
        }
    
    except Exception as e:
        logger.exception(f"Execution error: {e}")
        # Get conversation history to maintain throughout workflow
        conversation_history = state.get("conversation_history", [])
        
        return {
            "error": f"Error in execution: {str(e)}", 
            "complete": True, 
            "answer": f"An error occurred during execution: {str(e)}",
            "conversation_history": conversation_history  # Maintain conversation history
        }

def get_current_task_batch(remaining_tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group tasks by sequence and return the current batch to execute"""
    sequence_groups = {}
    for task in remaining_tasks:
        sequence = task.get("sequence", 1)
        if sequence not in sequence_groups:
            sequence_groups[sequence] = []
        sequence_groups[sequence].append(task)
    
    current_sequence = min(sequence_groups.keys())
    return sequence_groups[current_sequence]

def configure_execution_mode(state: Dict[str, Any], tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Configure parallel or sequential execution mode"""
    parallel_mode = state.get("parallel_mode", DEFAULT_BROWSER_SETTINGS["parallel_mode"])
    max_concurrent_browsers = DEFAULT_BROWSER_SETTINGS["max_concurrent_browsers"]
    max_workers = min(len(tasks), max_concurrent_browsers) if parallel_mode else 1
    
    return {"parallel_mode": parallel_mode, "max_workers": max_workers}

def execute_tasks(tasks: List[Dict[str, Any]], state: Dict[str, Any], 
                  execution_config: Dict[str, Any]) -> Dict[Any, Any]:
    """Execute tasks using ThreadPoolExecutor"""
    max_workers = execution_config["max_workers"]
    futures_to_tasks = {}
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Create futures for each task
        for task in tasks:
            task_id = str(task.get("id"))
            task_desc = task.get("description", "")
            task_url = task.get("start_url", state.get("start_url", DEFAULT_BROWSER_SETTINGS["start_url"]))
            
            # Browser state configuration
            browser_state = {
                "query": task_desc,
                "browser_initialized": False,
                "browser_controller": None,
                "screenshots": [],
                "collect_results": True,
                "start_url": task_url,
                "callback_handler": state.get("callback_handler"),
                "task_id": task_id,
                "tasks": state.get("tasks", []),  
                "task_results": state.get("task_results", []) 
            }
            
            future = executor.submit(run_browser_agent_with_state, browser_state)
            futures_to_tasks[future] = task
        
        return futures_to_tasks

def process_execution_results(execution_results: Dict[Any, Any], tasks: List[Dict[str, Any]], 
                             state: Dict[str, Any]) -> tuple:
    all_results = []
    structured_results = []  # Store structured results
    
    for future in as_completed(execution_results):
        task = execution_results[future]
        task_id = task.get("id")
        
        try:
            result_state = future.result()
            
            task_result = result_state.get("result", "")
            error = result_state.get("error")
            
            # Create structured result
            structured_result = {
                "task_id": task_id,
                "description": task.get("description", ""),
                "result": task_result,
                "source": {
                    "url": result_state.get("current_url", ""),
                    "title": result_state.get("page_title", "")
                },
                "error": error,
                "completed": error is None
            }
            
            structured_results.append(structured_result)
            
            if error:
                task_index = tasks.index(task)
                tasks[task_index] = {**task, "completed": False, "error": error}
            else:
                all_results.append(task_result)
                
                task_index = tasks.index(task)
                tasks[task_index] = {**task, "completed": True}
                
        except Exception as e:
            task_index = tasks.index(task)
            tasks[task_index] = {**task, "completed": False, "error": str(e)}
    
    return tasks, all_results, structured_results


def check_workflow_completion(remaining_tasks: List[Dict[str, Any]], 
                             current_tasks: List[Dict[str, Any]], 
                             current_task_index: int) -> tuple:
    """Check if workflow is complete and calculate next task index"""
    # Group tasks by sequence
    sequence_groups = {}
    for task in remaining_tasks:
        sequence = task.get("sequence", 1)
        if sequence not in sequence_groups:
            sequence_groups[sequence] = []
        sequence_groups[sequence].append(task)
    
    # Get the current sequence
    current_sequence = min(sequence_groups.keys())
    
    # Determine if workflow is complete
    more_sequences = [seq for seq in sequence_groups.keys() if seq > current_sequence]
    is_complete = len(more_sequences) == 0
    
    # Calculate next task index
    next_task_index = current_task_index + len(current_tasks)
    
    return is_complete, next_task_index

def format_combined_results(results: List[str], tasks: List[Dict[str, Any]]) -> str:
    """Format combined results from all tasks"""
    combined_result = "\n\n==== Task Results ====\n\n"
    for i, result in enumerate(results):
        if i < len(tasks):
            task = tasks[i]
            combined_result += f"--- {task.get('description', '')} ---\n{result}\n\n"
    
    return combined_result
