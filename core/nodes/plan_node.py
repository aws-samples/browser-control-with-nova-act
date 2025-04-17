import json
import logging
import time
from typing import Dict, Any

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_aws import ChatBedrockConverse
from datetime import datetime
import pytz

from ..types import BrowserWorkflowState
from ..config import MODEL_CONFIG, PLANNER_SYSTEM_PROMPT, DEFAULT_BROWSER_SETTINGS
from ..tools import WebTaskPlanTool
from ..callbacks import queue_tool_call, queue_status, queue_text, queue_error, queue_thinking

logger = logging.getLogger("nova_nodes.plan")

def create_planning_llm():
    try:
        model = ChatBedrockConverse(
            model=MODEL_CONFIG["planner_model"],
            region_name=MODEL_CONFIG["region"],
            temperature=MODEL_CONFIG["temperature"]["planner"]
        )
        
        llm_with_tools = model.bind_tools([WebTaskPlanTool()])
        
        return llm_with_tools
    except Exception as e:
        logger.exception(f"Error in create_planning_llm: {e}")
        raise

def plan_node(state: BrowserWorkflowState) -> Dict[str, Any]:
    logger.info("Planning task execution...")
    
    # Get conversation history from state
    conversation_history = state.get("conversation_history", [])
    
    # Use refined question if available
    question = state.get("refined_question", state.get("question", ""))
    logger.info(f"Planning query: {question}")
    
    # Get callback handler from state
    callback_handler = state.get("callback_handler")
    if callback_handler:
        callback_handler.set_active_node("plan")
    
    try:
        planning_llm = create_planning_llm()
        if callback_handler:
            queue_thinking(f"Planning execution for task: {question}", "plan")
            
        current_date = datetime.now(pytz.UTC).strftime("%Y-%m-%d %A %H:%M:%S UTC")

        # Build messages with conversation history for context
        messages = [SystemMessage(content=PLANNER_SYSTEM_PROMPT)]
        
        # Add conversation history to provide context
        if conversation_history:
            for msg in conversation_history[:-1]:  # Exclude the latest user query
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))
        
        # Add the current query
        messages.append(HumanMessage(content=f"""Plan the following web automation task: {question}
Current date: {current_date}
Create a structured plan with tasks and optimal starting URLs. Don't use Markdown formatting."""))
        
        # Add callback for streaming if available
        callbacks = [callback_handler] if callback_handler else None
        
        # Add retry logic for API calls
        max_retries = 3
        retry_delay = 2  # seconds
        retry_count = 0
        
        while True:
            try:
                response = planning_llm.invoke(
                    messages,
                    config={"callbacks": callbacks}
                )
                break  # Success, exit retry loop
            except Exception as api_error:
                retry_count += 1
                error_message = str(api_error)
                
                # Check if this is a retryable error
                is_retryable = (
                    "Response ended prematurely" in error_message or
                    "internalServerException" in error_message or
                    "service unavailable" in error_message.lower() or
                    "timeout" in error_message.lower() or
                    "ProtocolError" in error_message or
                    "ConnectionError" in error_message
                )
                
                if is_retryable and retry_count < max_retries:
                    wait_time = retry_delay * (2 ** (retry_count - 1))  # Exponential backoff
                    logger.warning(f"API error (retry {retry_count}/{max_retries}): {error_message}. Retrying in {wait_time}s...")
                    if callback_handler:
                        queue_text(f"Encountered a temporary service error. Retrying... ({retry_count}/{max_retries})", "plan")
                    time.sleep(wait_time)
                else:
                    # Not retryable or max retries exceeded
                    logger.error(f"API error (final): {error_message}")
                    raise  # Re-raise the exception
        
        # Process tool calls from response
        if hasattr(response, 'tool_calls') and response.tool_calls:
            for tool_call in response.tool_calls:
                if tool_call['name'] == 'create_web_tasks':
                    tool_args = tool_call['args']
                    logger.debug(f"Tool args: {json.dumps(tool_args, indent=2) if isinstance(tool_args, dict) else str(tool_args)}")
                    
                    # Use unified callback system for tool call
                    if callback_handler:
                        queue_tool_call('create_web_tasks', tool_args, "plan")
                    
                    # Process simple query response
                    if isinstance(tool_args, dict) and "query" in tool_args and len(tool_args) == 1:
                        return create_simple_task_plan(tool_args["query"])
                    
                    # Process structured tasks
                    if isinstance(tool_args, dict) and "tasks" in tool_args:
                        result = create_structured_task_plan(tool_args["tasks"], state)
                        result["conversation_history"] = conversation_history
                        return result
        
        # Fallback: Use original user request as direct task
        logger.warning("No valid tasks extracted. Using original request as direct task.")
        if callback_handler:
            queue_status("Using original request as direct task", "plan")
        result = create_direct_task_plan(question, state)
        result["conversation_history"] = conversation_history
        return result
        
    except Exception as e:
        logger.exception(f"Planning error: {e}")
        if callback_handler:
            queue_error(f"Planning error: {str(e)}", "plan")
            queue_status("Falling back to direct task execution", "plan")
        result = create_direct_task_plan(question, state)
        result["conversation_history"] = conversation_history
        return result

def create_simple_task_plan(query_text: str) -> Dict[str, Any]:
    start_url = DEFAULT_BROWSER_SETTINGS["start_url"]
    
    tasks = [{
        "id": 1,
        "description": query_text,
        "start_url": start_url,
        "sequence": 1,
        "completed": False
    }]
    
    logger.debug(f"Created simple task plan: {query_text}")
    
    return {
        "tasks": tasks,
        "start_url": start_url,
        "current_task_index": 0
    }

def create_structured_task_plan(raw_tasks: list, state: Dict[str, Any]) -> Dict[str, Any]:
    tasks = []
    
    for i, task in enumerate(raw_tasks):
        if isinstance(task, dict):
            task_desc = task.get("description", "Unknown task")
            task_url = task.get("start_url", DEFAULT_BROWSER_SETTINGS["start_url"])
            task_sequence = task.get("sequence", task.get("priority", i+1)) 
            
            # Create dict structure
            tasks.append({
                "id": i + 1,
                "description": task_desc,
                "start_url": task_url, 
                "sequence": task_sequence,
                "completed": False
            })
        else:
            # Fallback for unexpected format
            tasks.append({
                "id": i + 1,
                "description": str(task),
                "start_url": DEFAULT_BROWSER_SETTINGS["start_url"],
                "sequence": i+1,
                "completed": False
            })
    
    # Sort tasks by sequence
    tasks.sort(key=lambda t: t.get("sequence", 999))
    
    # If we have tasks, determine first task's start_url
    if tasks:
        first_task_url = tasks[0].get("start_url", DEFAULT_BROWSER_SETTINGS["start_url"])
        
        result = {
            "tasks": tasks,
            "start_url": first_task_url,  
            "current_task_index": 0,
            "headless": state.get("headless", DEFAULT_BROWSER_SETTINGS["headless"]),
            "parallel_mode": state.get("parallel_mode", DEFAULT_BROWSER_SETTINGS["parallel_mode"])
        }
        
        logger.debug(f"Created structured plan with {len(tasks)} tasks")
        return result
    
    # No tasks found, use original request
    return create_direct_task_plan(state.get("question", ""), state)

def create_direct_task_plan(question: str, state: Dict[str, Any]) -> Dict[str, Any]:
    result = {
        "tasks": [{
            "id": 1, 
            "description": question, 
            "start_url": DEFAULT_BROWSER_SETTINGS["start_url"],
            "sequence": 1,
            "completed": False
        }],
        "start_url": DEFAULT_BROWSER_SETTINGS["start_url"],
        "current_task_index": 0,
        "headless": state.get("headless", DEFAULT_BROWSER_SETTINGS["headless"]),
        "parallel_mode": state.get("parallel_mode", DEFAULT_BROWSER_SETTINGS["parallel_mode"])
    }
    
    logger.info(f"Created direct task plan with original request: '{question}'")
    return result