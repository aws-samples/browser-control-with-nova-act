#!/usr/bin/env python3
# Nova Act Simple Chatbot - Streamlined Version

import os
import asyncio
import time
import base64
from typing import Optional

import chainlit as cl
from chainlit.step import Step
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage

# Import browser management functions
from utils.browser_manager import (
    take_screenshot,
    close_browser,
    execute_action,
    get_current_url,
    get_page_title,
    start_browser_thread,
    is_browser_ready,
    get_browser_error
)
import logging
logger = logging.getLogger("nova_direct")

# Global variables
shutdown_in_progress = False

# Start browser thread immediately
start_browser_thread()

# Conversation history storage
conversation_history = []

# LLM Configuration
llm_config = {
    "model": "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "temperature": 0.2,
    "max_tokens": 1000,
    "region_name": "us-west-2" 
}

# Initialize the LLM client
llm = None
try:
    llm = ChatBedrockConverse(
        model=llm_config["model"],
        temperature=llm_config["temperature"],
        max_tokens=llm_config["max_tokens"],
        region_name=llm_config["region_name"]
    )
    print(f"LLM initialized with model {llm_config['model']}")
except Exception as e:
    print(f"Error initializing LLM: {str(e)}")
    llm = None

# Helper functions for LLM analysis
def add_to_conversation_history(role: str, content: str, screenshot_path: Optional[str] = None) -> None:
    """Add message to conversation history"""
    conversation_history.append({
        "role": role,
        "content": content,
        "timestamp": time.time(),
        "screenshot_path": screenshot_path
    })
    
    # Keep history manageable (last 10 entries)
    if len(conversation_history) > 10:
        conversation_history.pop(0)

def image_to_base64(image_path: str) -> Optional[str]:
    """Convert image file to base64 for LLM"""
    if not image_path:
        return None
        
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        print(f"Error converting image to base64: {str(e)}")
        return None

def get_llm_analysis(user_request: str, nova_response: str, screenshot_path: str) -> str:
    """Get LLM analysis of browser action with screenshot"""
    if not llm:
        return ""
    
    try:
        base64_image = image_to_base64(screenshot_path)
        if not base64_image:
            return ""
        
        else:
            prompt = f"User requested: '{user_request}'\n\nBrowser action result: {nova_response}\n\nPlease analyze what happened in the browser and provide a helpful explanation."
        
        messages = [
            HumanMessage(
                content=[
                    {"type": "text", "text": prompt}, 
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": base64_image},
                    },
                ],
            )
        ]
        
        # Get LLM response
        response = llm.invoke(messages)
        
        # Extract text content
        if hasattr(response, 'content'):
            content = response.content
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get('type') == 'text':
                        return item.get('text', '')
        
        return ""
    except Exception as e:
        print(f"Error in LLM analysis: {str(e)}")
        return ""

async def safe_close_browser() -> bool:
    """Safely close browser with timeout to prevent hanging"""
    global shutdown_in_progress
    
    if shutdown_in_progress:
        print("Browser close already in progress, ignoring duplicate request")
        return False
        
    shutdown_in_progress = True
    print("Starting safe browser shutdown sequence")
    
    try:
        # Send close command
        close_result = close_browser()
        
        # Wait a bit for browser to properly close
        await asyncio.sleep(1.0)
        print(f"Browser shutdown complete, result: {close_result}")
        return True
    except Exception as e:
        print(f"Error during browser shutdown: {str(e)}")
        return False

@cl.on_chat_start
async def on_chat_start():
    """Initialize chat session"""
    global shutdown_in_progress
    shutdown_in_progress = False
    
    await cl.Message(content="Initializing browser for Nova Act...").send()
    
    # Wait for browser to initialize
    max_wait_time = 15  # seconds
    wait_time = 0
    wait_increment = 0.5
    
    while not is_browser_ready() and not get_browser_error() and wait_time < max_wait_time:
        await asyncio.sleep(wait_increment)
        wait_time += wait_increment
    
    if not is_browser_ready():
        error_msg = get_browser_error() or "Browser initialization timed out"
        await cl.Message(content=f"Error: {error_msg}\nPlease try restarting the application.").send()
        return
    
    # Get initial screenshot
    try:
        screenshot_path = take_screenshot()
        current_url = get_current_url()
        
        await cl.Message(
            content=f"Browser is ready! Current URL: {current_url}\n\nType your browser automation request:",
            elements=[cl.Image(path=screenshot_path, name="initial_screenshot")]
        ).send()
    except Exception as e:
        await cl.Message(content=f"Error setting up browser: {str(e)}").send()

@cl.on_message
async def on_message(message: cl.Message):
    """Process user messages"""
    if shutdown_in_progress:
        await cl.Message(content="Shutdown in progress, cannot process requests. Please wait...").send()
        return
        
    user_request = message.content.strip()
    add_to_conversation_history("user", user_request)
    
    # Check if browser is ready
    if not is_browser_ready():
        await cl.Message(content="Browser is not initialized. Please restart the application.").send()
        return
    
    # Process user request
    async with cl.Step(name="Browser Action", type="tool") as step:
        step.input = f"Executing: {user_request}"
        
        try:
            # Execute user request directly with Nova Act
            result = execute_action(user_request)
            
            # Get result text
            if hasattr(result, 'response'):
                response_text = result.response
            else:
                response_text = "Action completed but no detailed response available."
            
            step.output = "Action completed successfully"
            
            # Take screenshot of result
            screenshot_path = take_screenshot()
            current_url = get_current_url()
            page_title = get_page_title()
            
            # Get LLM analysis if available
            llm_analysis = ""
            if llm:
                llm_analysis = get_llm_analysis(user_request, response_text, screenshot_path)
            
            # Build response message
            content = f"Action completed!\n\n"
            if response_text:
                content += f"**Browser response:**\n```\n{response_text}\n```\n\n"
            
            content += f"**Current page:** {page_title}\n**URL:** {current_url}"
            
            if llm_analysis:
                content += f"\n\n**Analysis:**\n{llm_analysis}"
            
            # Send response with screenshot
            add_to_conversation_history("assistant", content, screenshot_path)
            
            await cl.Message(
                content=content,
                elements=[cl.Image(path=screenshot_path, name="result_screenshot")]
            ).send()
            
        except Exception as e:
            step.output = f"Error: {str(e)}"
            
            # Try to get screenshot of error state
            screenshot_path = None
            try:
                screenshot_path = take_screenshot()
            except:
                logger.debug(f"Ignored error: {e}")
            
            # Format error message
            error_message = f"Error: {str(e)}"
            
            # Get error analysis if possible
            if llm and screenshot_path:
                error_type = e.__class__.__name__
                error_details = f"Error Type: {error_type}\nError Message: {str(e)}"
                error_analysis = get_llm_analysis(
                    f"{user_request} (failed)", 
                    error_details,
                    screenshot_path
                )
                
                if error_analysis:
                    error_message += f"\n\n**Error Analysis:**\n{error_analysis}"
            
            # Send error message with screenshot if available
            elements = []
            if screenshot_path:
                elements.append(cl.Image(path=screenshot_path, name="error_screenshot"))
            
            add_to_conversation_history("system", f"Error: {str(e)}", screenshot_path)
            await cl.Message(content=error_message, elements=elements).send()

@cl.on_chat_end
async def on_chat_end():
    """Clean up resources when chat ends"""
    print("Chat end event detected - initiating safe shutdown")
    
    if is_browser_ready() and not shutdown_in_progress:
        shutdown_task = asyncio.create_task(safe_close_browser())
        
        try:
            await cl.Message(
                content="Browser shutdown initiated. Goodbye!"
            ).send()
        except:
            # Ignore any errors with final message
            logger.debug(f"Ignored error: {e}")
    else:
        print("Skipping browser close - browser not active or shutdown already in progress")
        
    print("Chat end handler complete")