#!/usr/bin/env python3

import os
import sys
import json
import asyncio
import logging
import greenlet
import threading
from typing import Dict, Any, Optional, List, Union

import chainlit as cl
from nova_act import NovaAct, ActResult
from langgraph.graph import StateGraph
from langchain_aws import ChatBedrockConverse

from core.types import ProcessingType
from core import create_browser_workflow
from core.config import MODEL_CONFIG, DEFAULT_BROWSER_SETTINGS
from core.callbacks import (
    BedrockCompatibleCallback,
    process_event_queue,
    event_processing_loop
)

from utils.browser_manager import (
    take_screenshot,
    close_browser,
    config,
    is_browser_ready,
    get_browser_controller
)

from utils.chat_utils import (
    add_to_conversation_history,
    get_conversation_history_for_llm
)

# Configure logging
logger = logging.getLogger("nova_chatbot")
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Set default log level - can be adjusted via environment variable
log_level = os.environ.get("NOVA_LOG_LEVEL", "INFO").upper()
logger.setLevel(getattr(logging, log_level))

# Handle greenlet errors gracefully
original_excepthook = sys.excepthook

def custom_excepthook(exctype, value, traceback, original_hook=original_excepthook):
    if exctype == greenlet.error and "Cannot switch to a different thread" in str(value):
        logger.debug("Ignoring greenlet thread switching error during shutdown (expected)")
        return
    original_hook(exctype, value, traceback)

sys.excepthook = custom_excepthook

# Initialize workflow
workflow = None
try:
    workflow = create_browser_workflow()
    logger.info("LangGraph workflow initialized successfully")
except Exception as e:
    logger.error(f"Error initializing LangGraph workflow: {str(e)}")

# Initialize language model
llm = None
try:
    llm = ChatBedrockConverse(
        model=MODEL_CONFIG["planner_model"],
        region_name=MODEL_CONFIG["region"],
        temperature=MODEL_CONFIG["temperature"]["planner"]
    )
    logger.info(f"LLM initialized with model {MODEL_CONFIG['planner_model']}")
except Exception as e:
    logger.error(f"Error initializing LLM: {str(e)}")

def prepare_workflow_state(user_query: str) -> Dict[str, Any]:
    callback_handler = BedrockCompatibleCallback("chat")
    logger.debug(f"Created new callback handler for workflow")
    
    from utils.chat_utils import get_initial_conversation_history
    conversation_history = get_initial_conversation_history()

    conversation_history.append({
        "role": "user",
        "content": user_query
    })

    return {
        "question": user_query,
        "tasks": [],
        "start_url": "",
        "current_task_index": 0,
        "current_task": {},
        "current_result": "",
        "task_results": [],
        "browser_initialized": False,
        "browser_controller": get_browser_controller(),
        "nova_instance": None,
        "answer": "",
        "screenshots": [],
        "error": None,
        "complete": False,
        "is_casual": False,
        "processing_type": "",
        "direct_answer": "",
        "conversation_history": conversation_history,
        "headless": config["headless"],
        "record_video": DEFAULT_BROWSER_SETTINGS["record_video"],
        "parallel_mode": DEFAULT_BROWSER_SETTINGS["parallel_mode"],
        "callback_handler": callback_handler 
    }

@cl.on_chat_start
async def on_chat_start():
    logger.debug("Chat start event triggered")
    
    await cl.Message(content=f"### Welcome to Nova Act Agent Chatbot!\n\n"
                     f"Type your question or task, and I'll help you accomplish it using browser automation and intelligent planning.").send()

async def handle_workflow_events(workflow, initial_state: Dict[str, Any]) -> Dict[str, Any]:
    """Process workflow events and update state"""
    callback_handler = initial_state.get("callback_handler")
    final_state = initial_state.copy()
    
    # Set up answer_gen node step early to ensure it exists
    if callback_handler:
        # No need to manually create the step - callback system will handle it
        callback_handler.set_active_node("answer_gen")
    
    # Start event processing loop
    event_processing_task = asyncio.create_task(event_processing_loop(callback_handler))
    
    try:
        async for output in workflow.astream_events(
            initial_state,
            version="v2",
            config={"callbacks": [callback_handler] if callback_handler else None, "recursion_limit": 100}
        ):
            # Process node completion events
            if output["event"] == "on_chain_end" and output["name"] in workflow.nodes.keys():
                node_name = output["name"]
                logger.debug(f"Node completed: {node_name}")
                
                # Update state with node output
                node_output = output["data"]["output"]
                for key, value in node_output.items():
                    if isinstance(value, (str, bool, int, float)) or value is None:
                        final_state[key] = value
                    elif isinstance(value, list):
                        if key not in final_state:
                            final_state[key] = []
                        final_state[key] += value
                    elif isinstance(value, dict):
                        if key not in final_state:
                            final_state[key] = {}
                        final_state[key].update(value)
            
            # Process any pending UI events
            await process_event_queue(callback_handler)
            
            # Brief pause to allow UI to update
            await asyncio.sleep(0.05)
    
    finally:
        # Cancel the event processing task
        event_processing_task.cancel()
        try:
            await event_processing_task
        except asyncio.CancelledError:
            logger.debug("Event processing task cancelled")
        
        # Process any remaining events
        await process_event_queue(callback_handler)
    
    return final_state

async def render_final_response(state: Dict[str, Any]) -> None:
    answer = state.get("answer", "")
    screenshots = state.get("screenshots", [])
    error = state.get("error")
    processing_type = state.get("processing_type", "")
    conversation_history = state.get("conversation_history", [])
    
    response_content = ""
    elements = []
            
    if error:
        response_content = f"Error: {error}"
    elif processing_type == ProcessingType.DIRECT_ANSWER.name:
        response_content = answer
    else:
        response_content = answer
        
        if screenshots:
            latest_screenshot = screenshots[-1]
            elements.append(cl.Image(path=latest_screenshot, name="result_screenshot"))
    
    # Get callback handler and use it to finalize the answer_gen step
    callback_handler = state.get("callback_handler")
    if callback_handler:
        callback_handler.set_active_node("answer_gen")
        
        # Send final answer through callback system
        if response_content:
            final_answer_text = f"\n\n**Final Answer:**\n\n{response_content}"
            from core.callbacks import queue_text, queue_screenshot
            
            # Add any screenshots to the elements
            if screenshots and len(screenshots) > 0:
                queue_screenshot(screenshots[-1], "Final result", "answer_gen")
                
            # Send the final text
            queue_text(final_answer_text, "answer_gen")
            
            # Process the events
            await process_event_queue(callback_handler)
            
            # Mark as complete
            if "answer_gen" in callback_handler.node_steps:
                step = callback_handler.node_steps["answer_gen"]
                step.type = "complete"
                await step.update()

    # State-based conversation history update
    conversation_history.append({
        "role": "assistant",
        "content": response_content,
        "screenshot": screenshots[-1] if screenshots else None
    })
    
    # Also update global history for state persistence
    from utils.chat_utils import backup_conversation_history
    backup_conversation_history(conversation_history)

    # Send final answer as regular message
    final_msg = cl.Message(content=response_content, elements=elements)
    await final_msg.send()

@cl.on_message
async def on_message(message: cl.Message):
    global workflow
    
    user_request = message.content.strip()
    
    if not workflow:
        await cl.Message(content="Sorry, the workflow system is not available. Please try again later.").send()
        return
        
    try:
        # Initialize workflow state
        initial_state = prepare_workflow_state(user_request)
        logger.info(f"Processing query: {user_request}")
        
        # Process workflow events and get final state
        final_state = await handle_workflow_events(workflow, initial_state)
        
        # Render final response
        await render_final_response(final_state)
                              
    except Exception as e:
        logger.exception(f"Workflow error: {str(e)}")
        
        # Try to capture error screenshot
        screenshot_path = ""
        try:
            screenshot_path = take_screenshot()
        except Exception as ss_err:
            logger.error(f"Could not take error screenshot: {ss_err}")
            
        # Send error message to user
        error_msg = f"An error occurred while processing your request: {str(e)}"
        elements = []
        if screenshot_path:
            elements.append(cl.Image(path=screenshot_path, name="error_screenshot"))
            
        await cl.Message(content=error_msg, elements=elements).send()
        add_to_conversation_history("system", f"Error occurred: {str(e)}", screenshot_path)

@cl.on_chat_end
async def on_chat_end():
    logger.debug("Chat end event triggered")
    
    if is_browser_ready():
        try:
            close_result = close_browser()
            await asyncio.sleep(1.5)
            
            try:
                if close_result:
                    await cl.Message(content="Browser closed. Thanks for using Nova Act Agent Chatbot!").send()
                else:
                    await cl.Message(content="Failed to close browser properly. Please check the logs for details.").send()
            except Exception as msg_err:
                logger.debug(f"Error sending cleanup message (safe to ignore): {msg_err}")
        except Exception as e:
            logger.debug(f"Normal cleanup threading conflict (safe to ignore): {e}")
    
    logger.info("Browser state reset complete")
