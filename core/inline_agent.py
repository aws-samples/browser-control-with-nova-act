"""
Nova Act Inline Agent Module with advanced browser control capabilities
"""
import os
import json
import uuid
import logging
import mimetypes
import time
from typing import Dict, Any, List, Optional, Tuple, TypedDict

from langchain_aws.agents.types import InlineAgentConfiguration
from langchain_aws.agents import BedrockInlineAgentsRunnable
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from nova_act import NovaAct

from .callbacks import (
    queue_text,
    queue_thinking,
    queue_tool_call,
    queue_tool_result,
    queue_screenshot,
    queue_error,
    queue_status,
    queue_executor_result
)

from .browser_controller import BrowserController
from .config import MODEL_CONFIG, BROWSER_AGENT_INSTRUCTION, EXECUTION_CONFIG, DEFAULT_BROWSER_SETTINGS
from .tools import (
    MouseBrowserTool,
    KeyboardBrowserTool,
    ExtractElementTool,
    ExtractDataTool, 
    CollectResultTool,
    GoToURLTool
)

from botocore.config import Config
boto_config = Config(
    max_pool_connections=10,  
    connect_timeout=5,
    read_timeout=120,
    retries={"max_attempts": 3}
)

# Configure logging
logger = logging.getLogger("nova_inline_agent")

# BrowserState type definition
class BrowserState(TypedDict):
    query: str
    start_url: str
    headless: bool
    record_video: bool
    browser_initialized: bool
    current_url: Optional[str]
    page_title: Optional[str]
    result: Optional[str]
    screenshots: List[str]
    error: Optional[str]
    complete: bool
    current_image_path: Optional[str]
    callback_handler: Any
    task_id: Optional[str]

def initialize_browser_from_state(state: BrowserState) -> Tuple[Optional[NovaAct], Optional[BrowserController]]:
    url = state.get("start_url", DEFAULT_BROWSER_SETTINGS["start_url"])
    headless = DEFAULT_BROWSER_SETTINGS["headless"]
    record_video = DEFAULT_BROWSER_SETTINGS["record_video"]
    
    # Get timeout and max_steps from BROWSER_SETTINGS
    timeout = DEFAULT_BROWSER_SETTINGS.get("timeout", 300)
    max_steps = DEFAULT_BROWSER_SETTINGS.get("max_steps", 30)
    user_data_dir = DEFAULT_BROWSER_SETTINGS.get("user_data_dir")
    clone_user_data_dir = DEFAULT_BROWSER_SETTINGS.get("clone_user_data_dir", True)

    try:
        browser_id = str(uuid.uuid4())[:8]
        
        nova_args = {
            "starting_page": url,
            "headless": headless,
            "record_video": record_video
        }
        
        if user_data_dir:
            nova_args["user_data_dir"] = user_data_dir
            nova_args["clone_user_data_dir"] = clone_user_data_dir
        
        nova = NovaAct(**nova_args)
        
        nova.start()
        
        browser_controller = BrowserController(nova)
        
        return nova, browser_controller
    except Exception as e:
        logger.exception(f"Error initializing browser: {e}")
        return None, None

def create_browser_inline_agent(browser_controller):
    tools = []
    
    if browser_controller:
        tools = [
            KeyboardBrowserTool(browser_controller),
            MouseBrowserTool(browser_controller),
            GoToURLTool(browser_controller),
            ExtractDataTool(browser_controller)
        ]

    instruction = BROWSER_AGENT_INSTRUCTION

    agent_config = InlineAgentConfiguration(
        foundation_model=MODEL_CONFIG["browser_agent_model"], 
        instruction=instruction,
        tools=tools,
        enable_trace=True
    )

    inline_agent = BedrockInlineAgentsRunnable.create(
        region_name=MODEL_CONFIG["region"],  
        inline_agent_config=agent_config,
        config=boto_config 
    )

    return inline_agent

def process_image_for_agent(current_image_path: str):
    if not current_image_path or not os.path.exists(current_image_path):
        return None
    
    try:
        with open(current_image_path, "rb") as f:
            image_bytes = f.read()
        
        media_type = mimetypes.guess_type(current_image_path)[0] or "image/jpeg"
        
        return {
            "files": [
                {
                    "name": "current_image",
                    "source": {
                        "byteContent": {
                            "data": image_bytes,
                            "mediaType": media_type
                        },
                        "sourceType": "BYTE_CONTENT"
                    },
                    "useCase": "CHAT"
                }
            ]
        }
    except Exception as e:
        logger.error(f"Error processing image: {e}")
        return None

def print_message_summary(messages, turn_number=None):
    print(f"\n--- Message Summary (Turn {turn_number if turn_number is not None else 'Unknown'}) ---")
    for i, msg in enumerate(messages):
        msg_type = type(msg).__name__
        content_preview = ""
        
        if hasattr(msg, 'content'):
            if isinstance(msg.content, str):
                content_preview = msg.content[:50] + "..." if len(msg.content) > 50 else msg.content
            elif isinstance(msg.content, dict) and "status" in msg.content:
                content_preview = f"Status: {msg.content.get('status', 'unknown')}"
        
        tool_info = ""
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            tools = [t['name'] for t in msg.tool_calls]
            tool_info = f" | Tools: {', '.join(tools)}"
        
        print(f"[{i}] {msg_type}{tool_info}: {content_preview}")
    print("--- End Summary ---\n")

def run_browser_agent_with_state(state: BrowserState) -> BrowserState:
    query = state.get("query", "")
    task_desc = query  # Store query as task description for later use
    max_turns = state.get("max_turns", EXECUTION_CONFIG["max_turns"])
    collect_results = state.get("collect_results", EXECUTION_CONFIG["collect_results"])
    current_image_path = state.get("current_image_path")
    callback_handler = state.get("callback_handler")
    task_id = state.get("task_id", "default")
    
    node_id = f"executor_{task_id}"
    result = ""
    screenshots = []
    error = None
    current_url = ""
    page_title = ""
    turn_result = ""
    
    browser_controller = None
    nova_instance = None
    
    try:
        nova_instance, browser_controller = initialize_browser_from_state(state)
        if browser_controller:
            browser_controller.set_graph_state(state)
            screenshot_path = browser_controller.take_screenshot()
            screenshots.append(screenshot_path)
            queue_screenshot(screenshot_path, "Initial page state", node_id)
            current_image_path = screenshot_path
            state["current_image_path"] = screenshot_path
            current_url = browser_controller.get_current_url()
            page_title = browser_controller.get_page_title()

        if not nova_instance or not browser_controller:
            return {**state, "error": "Failed to initialize browser", "complete": True}
            
    except Exception as e:
        return {**state, "error": f"Browser initialization error: {str(e)}", "complete": True}
    
    try:
        agent = create_browser_inline_agent(browser_controller)
        messages = []
        
        if BROWSER_AGENT_INSTRUCTION:
            messages.append(SystemMessage(content=BROWSER_AGENT_INSTRUCTION))
        
        # Gather previous sequence results as context
        previous_results_context = ""
        current_sequence = None
        
        # Try to determine current task's sequence number
        for task in state.get("tasks", []):
            if task.get("description") == query:  # Match the current task
                current_sequence = task.get("sequence")
                break
        
        # If we found the current sequence and it's greater than 1, gather previous results
        if current_sequence and current_sequence > 1:
            previous_results = []
            for task_result in state.get("task_results", []):
                task_seq = None
                # Find the sequence of this completed task
                for task in state.get("tasks", []):
                    if task.get("description") == task_result.get("description"):
                        task_seq = task.get("sequence")
                        break
                        
                # If this is from a previous sequence, add it to context
                if task_seq and task_seq < current_sequence:
                    result_desc = task_result.get("description", "")
                    result_content = task_result.get("result", "")
                    if result_desc and result_content:
                        previous_results.append(f"Previous Task: {result_desc}\nResult: {result_content}")
            
            if previous_results:
                previous_results_context = "\n\n### Previous Task Results:\n" + "\n\n".join(previous_results) + "\n\n"
        
        context_prefix = f"Current URL: {current_url}\nPage Title: {page_title}\n\n{previous_results_context}"
        full_prompt = f"{context_prefix}### Goal: {query}"
        
        messages.append(HumanMessage(content=full_prompt))
        
        image_data = None
        if current_image_path and os.path.exists(current_image_path):
            image_data = process_image_for_agent(current_image_path)
        
        try:
            response = agent.invoke(messages, image_data=image_data) if image_data else agent.invoke(messages)
            messages.append(response)
            
            turn_result = response.content if hasattr(response, 'content') else ""
            if turn_result:
                queue_text(turn_result, node_id)
                
            extract_thinking_from_trace(response, node_id, messages)
                
        except Exception as api_error:
            error_msg = f"API error during initial agent invocation: {str(api_error)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from api_error
        
        turn = 1
        while turn < max_turns:
            if not hasattr(response, 'tool_calls') or not response.tool_calls:
                logger.info("No tool calls, task may be complete")
                result = response.content if hasattr(response, 'content') else ""
                break
            
            for tool_call in response.tool_calls:
                tool_name = tool_call['name']
                args = tool_call['args']
                tool_call_id = tool_call['id']
                
                queue_tool_call(tool_name, args, node_id)
                
                tool_result = ""
                screenshot_path = None
                
                try:
                    if tool_name == "Browser::keyboard":
                        tool = KeyboardBrowserTool(browser_controller)
                        tool_result = tool._run(**args)
                    elif tool_name == "Browser::mouse":
                        tool = MouseBrowserTool(browser_controller)
                        tool_result = tool._run(**args)
                    elif tool_name == "Browser::go_to_url":
                        tool = GoToURLTool(browser_controller)
                        tool_result = tool._run(**args)
                    elif tool_name == "Browser::data":
                        tool = ExtractDataTool(browser_controller)
                        tool_result = tool._run(**args)
                    else:
                        tool_result = json.dumps({
                            "status": "error",
                            "message": f"Unknown tool: {tool_name}"
                        })
                    
                    if browser_controller and browser_controller.is_initialized():
                        current_url = browser_controller.get_current_url()
                        page_title = browser_controller.get_page_title()
                        screenshot_path = browser_controller.take_screenshot()
                        screenshots.append(screenshot_path)
                        queue_screenshot(screenshot_path, f"After {tool_name}", node_id)
                        current_image_path = screenshot_path
                        
                except Exception as e:
                    error_message = str(e)
                    tool_result = json.dumps({
                        "status": "error",
                        "message": f"Tool execution error: {error_message}"
                    })
                
                queue_tool_result(tool_result, node_id)
                
                messages.append(ToolMessage(
                    content=tool_result,
                    tool_call_id=tool_call_id,
                    name=tool_name.split("::")[-1] if "::" in tool_name else tool_name
                ))
            
            image_data = None
            if current_image_path and os.path.exists(current_image_path):
                image_data = process_image_for_agent(current_image_path)
            
            if turn == max_turns - 1:
                final_turn_instructions = (
                    "\n### IMPORTANT: FINAL TURN INSTRUCTIONS\n"
                    "This was your final turn. Please provide a comprehensive answer based on all information collected so far. "
                    "DO NOT make any more tool calls. Instead, summarize your findings and provide a complete response to the original task. "
                    "Include relevant details from your browser exploration and any important information you've discovered."
                )
                
                if messages and isinstance(messages[-1], ToolMessage): 
                    if isinstance(messages[-1].content, str):
                        try:
                            tool_content = json.loads(messages[-1].content)
                            tool_content["message"] += final_turn_instructions
                            messages[-1].content = json.dumps(tool_content)
                        except json.JSONDecodeError:
                            messages[-1].content = f"{messages[-1].content}\n{final_turn_instructions}"
                else:
                    messages.append(HumanMessage(content=final_turn_instructions))
                    
                logger.info("Added final turn instructions to prevent further tool calls")
                queue_thinking("This is the final turn - providing conclusive answer", node_id)
            
            try:
                response = agent.invoke(messages, image_data=image_data) if image_data else agent.invoke(messages)
                messages.append(response)
                
                turn_result = response.content if hasattr(response, 'content') else ""
                if turn_result:
                    queue_text(turn_result, node_id)
                
                extract_thinking_from_trace(response, node_id, messages)
                    
            except Exception as api_error:
                error_msg = f"API error during agent invocation: {str(api_error)}"
                logger.error(error_msg)
                raise RuntimeError(error_msg) from api_error
            
            turn += 1
        
        result = turn_result or result
        
        if collect_results and browser_controller:
            final_results = collect_final_results(browser_controller, node_id)
            
            if final_results:
                current_url = final_results.get("url", "")
                page_title = final_results.get("title", "")
                
                if "screenshot" in final_results and final_results["screenshot"] not in screenshots:
                    screenshots.append(final_results["screenshot"])
                    queue_screenshot(final_results["screenshot"], "Final state", node_id)
                
                # Create a structured result for better display
                result += f"\nExecutor Results:\n- URL: {current_url}\n- Title: {page_title}\n- Screenshot: {final_results.get('screenshot', 'Not available')}"
                
                # Use the new executor_result event for better UI display
                executor_result_data = {
                    "description": task_desc,
                    "current_url": current_url,
                    "page_title": page_title,
                    "result": result,
                    "timestamp": time.time()
                }
                
                queue_executor_result(executor_result_data, node_id)
        
    except Exception as e:
        error = f"Error during browser automation: {str(e)}"
        logger.exception(error)
    
    cleanup_browser(nova_instance, query, node_id)
    
    return {
        **state,
        "result": result,
        "screenshots": screenshots,
        "current_url": current_url,
        "page_title": page_title,
        "error": error,
        "browser_initialized": nova_instance is not None,
        "complete": True,
        "current_image_path": current_image_path,
    }

def extract_thinking_from_trace(response, node_id, messages=None):
    """
    Extract thinking process from trace log and add it to messages history
    """
    if hasattr(response, 'additional_kwargs') and 'trace_log' in response.additional_kwargs:
        try:
            trace_data = json.loads(response.additional_kwargs['trace_log'])
            thinking_content = None
            for entry in trace_data:
                if ('trace' in entry and 'orchestrationTrace' in entry['trace'] and 
                    'modelInvocationOutput' in entry['trace']['orchestrationTrace']):
                    
                    model_output = entry['trace']['orchestrationTrace']['modelInvocationOutput']
                    if 'rawResponse' in model_output and 'content' in model_output['rawResponse']:
                        try:
                            raw_content = json.loads(model_output['rawResponse']['content'])
                            
                            if ('output' in raw_content and 'message' in raw_content['output'] and 
                                'content' in raw_content['output']['message']):
                                
                                content_items = raw_content['output']['message']['content']
                                for item in content_items:
                                    if 'text' in item and item['text']:
                                        thinking_content = item['text']
                                        break
                        except json.JSONDecodeError as json_err:
                            logger.debug(f"JSON parsing error in trace content: {json_err}")
            
            if thinking_content:
                queue_thinking(thinking_content, node_id)
                
                if messages is not None:
                    thinking_message = AIMessage(
                        content=f"THINKING: {thinking_content}",
                        additional_kwargs={"is_thinking": True}
                    )
                    messages.append(thinking_message)
                
                return thinking_content
                
        except Exception as e:
            logger.error(f"Error parsing trace for thinking: {e}")
    
    return None

def collect_final_results(browser_controller, node_id):
    try:
        collect_tool = CollectResultTool(browser_controller)
        collect_result = collect_tool._run("final results with screenshot and URL")
        
        try:
            result_data = json.loads(collect_result)
                
            return result_data
        except json.JSONDecodeError:
            logger.error("Failed to parse final results JSON")
            return None
            
    except Exception as e:
        logger.exception(f"Error collecting final results: {e}")
        return None

def cleanup_browser(nova_instance, query, node_id):
    if nova_instance:
        try:
            nova_instance.__exit__(None, None, None)
        except Exception as e:
            logger.exception(f"Error closing browser: {e}")