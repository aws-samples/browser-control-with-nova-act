#!/usr/bin/env python3
"""
Browser management utilities for Nova Act Chatbot.

This module handles all browser thread operations including command
queuing, thread management, and basic browser control functions.
"""

import os
import time
import queue
import tempfile
import threading
from typing import Any, Tuple, Optional

from nova_act import NovaAct
from core.browser_controller import BrowserController
from core.config import DEFAULT_BROWSER_SETTINGS

# Command types for browser thread
CMD_EXECUTE_ACTION = "execute_action"
CMD_TAKE_SCREENSHOT = "take_screenshot"
CMD_GET_URL = "get_url"
CMD_GET_TITLE = "get_title"
CMD_CLOSE = "close"

# Thread-safe communication queues
command_queue = queue.Queue()
result_queue = queue.Queue()

# Global variables
browser_thread = None
screenshot_dir = None
browser_ready = False
browser_error = None
browser_controller = None

# Browser configuration
config = {
    "max_steps": 10, 
    "headless": DEFAULT_BROWSER_SETTINGS["headless"],
    "user_data_dir": DEFAULT_BROWSER_SETTINGS["user_data_dir"],
    "clone_user_data_dir": DEFAULT_BROWSER_SETTINGS["clone_user_data_dir"],
}

def browser_thread_func():
    """Main function for the browser thread - all Playwright operations happen here"""
    global browser_ready, browser_error, screenshot_dir, browser_controller
    
    nova_instance = None
    screenshot_dir = tempfile.mkdtemp(prefix="nova_act_screenshots_")
    print(f"Screenshot directory: {screenshot_dir}")
    
    try:
        # Initialize NovaAct
        print("Initializing NovaAct in browser thread...")
        print(f"Using configuration: headless={config['headless']}, max_steps={config['max_steps']}")
        
        # Prepare NovaAct initialization arguments
        nova_args = {
            "starting_page": DEFAULT_BROWSER_SETTINGS["start_url"],
            "headless": config["headless"],
            "record_video": DEFAULT_BROWSER_SETTINGS["record_video"]
        }
        
        # Add user_data_dir if specified
        if "user_data_dir" in config and config["user_data_dir"]:
            nova_args["user_data_dir"] = config["user_data_dir"]
            print(f"Using user_data_dir: {config['user_data_dir']}")
            
            # Add clone_user_data_dir if specified
            if "clone_user_data_dir" in config:
                nova_args["clone_user_data_dir"] = config["clone_user_data_dir"]
                print(f"clone_user_data_dir set to: {config['clone_user_data_dir']}")
        
        nova_instance = NovaAct(**nova_args)
        
        # Start browser
        nova_instance.start()
        
        # Check initialization
        if hasattr(nova_instance, 'page') and nova_instance.page is not None:
            current_url = nova_instance.page.url
            print(f"Browser initialized successfully! Current URL: {current_url}")
            # Create browser controller for higher-level functions
            browser_controller = BrowserController(nova_instance)
            browser_ready = True
            browser_error = None
        else:
            print("Browser initialization failed - page object not available")
            browser_error = "Failed to initialize browser page"
            browser_ready = False
            return
            
    except Exception as e:
        import traceback
        print(f"Error initializing Nova Act: {str(e)}")
        traceback.print_exc()
        browser_error = f"Error initializing browser: {str(e)}"
        browser_ready = False
        return
    
    # Main command processing loop
    try:
        while True:
            try:
                # Get command from queue
                cmd_type, cmd_args = command_queue.get(timeout=0.5)
                
                # Process command
                if cmd_type == CMD_EXECUTE_ACTION:
                    if len(cmd_args) == 2:
                        request, max_steps = cmd_args
                        timeout = DEFAULT_BROWSER_SETTINGS.get("timeout", 300)
                    else:  #
                        request, max_steps, timeout = cmd_args
                        
                    try:
                        result = nova_instance.act(request, max_steps=max_steps, timeout=timeout)
                        result_queue.put((True, result))
                    except Exception as e:
                        result_queue.put((False, str(e)))
                
                elif cmd_type == CMD_TAKE_SCREENSHOT:
                    try:
                        timestamp = time.strftime("%Y%m%d_%H%M%S")
                        screenshot_path = os.path.join(screenshot_dir, f"screenshot_{timestamp}.png")
                        nova_instance.page.screenshot(path=screenshot_path)
                        result_queue.put((True, screenshot_path))
                    except Exception as e:
                        result_queue.put((False, str(e)))
                
                elif cmd_type == CMD_GET_URL:
                    try:
                        url = nova_instance.page.url
                        result_queue.put((True, url))
                    except Exception as e:
                        result_queue.put((False, str(e)))
                
                elif cmd_type == CMD_GET_TITLE:
                    try:
                        title = nova_instance.page.title()
                        result_queue.put((True, title))
                    except Exception as e:
                        result_queue.put((False, str(e)))
                
                elif cmd_type == CMD_CLOSE:
                    # Close browser and exit thread
                    break
                
                # Mark command as done
                command_queue.task_done()
                
            except queue.Empty:
                # No commands, continue waiting
                continue
                
    except Exception as e:
        print(f"Error in browser thread: {str(e)}")
    
    finally:
        # Clean up
        if nova_instance:
            try:
                nova_instance.__exit__(None, None, None)
                print("Browser closed successfully")
            except Exception as e:
                print(f"Error closing browser: {str(e)}")

# Helper functions to send commands to browser thread
def execute_action(request, max_steps=None, timeout=None):
    """Execute browser action via command queue"""
    if max_steps is None:
        max_steps = DEFAULT_BROWSER_SETTINGS.get("max_steps", 30)
    
    if timeout is None:
        timeout = DEFAULT_BROWSER_SETTINGS.get("timeout", 300)
    
    print(f"Executing action with max_steps={max_steps}, timeout={timeout}: {request}")
    command_queue.put((CMD_EXECUTE_ACTION, (request, max_steps, timeout)))
    success, result = result_queue.get()
    if not success:
        raise Exception(result)
    return result

def take_screenshot():
    """Take screenshot via command queue"""
    command_queue.put((CMD_TAKE_SCREENSHOT, ()))
    success, result = result_queue.get()
    if not success:
        raise Exception(result)
    return result

def get_current_url():
    """Get URL via command queue"""
    command_queue.put((CMD_GET_URL, ()))
    success, result = result_queue.get()
    if not success:
        raise Exception(result)
    return result

def get_page_title():
    """Get page title via command queue"""
    command_queue.put((CMD_GET_TITLE, ()))
    success, result = result_queue.get()
    if not success:
        raise Exception(result)
    return result

def close_browser():
    """Close browser via command queue"""
    try:
        command_queue.put((CMD_CLOSE, ()))
        time.sleep(1.5)  
        return True
    except Exception as e:
        print(f"Warning: Error during browser close (safe to ignore): {e}")
        return False

def start_browser_thread():
    """Start the browser thread"""
    global browser_thread
    browser_thread = threading.Thread(target=browser_thread_func)
    browser_thread.daemon = True
    browser_thread.start()
    print("Browser thread started")
    
def get_browser_controller():
    """Get the current browser controller"""
    global browser_controller
    return browser_controller

def is_browser_ready():
    """Check if the browser is ready"""
    global browser_ready
    return browser_ready

def get_browser_error():
    """Get browser error if any"""
    global browser_error
    return browser_error
    
def get_config():
    """Get the current browser configuration"""
    global config
    return config.copy()
    
def is_browser_ready():
    """Check if the browser is ready"""
    global browser_ready
    return browser_ready

def get_browser_error():
    """Get browser error if any"""
    global browser_error
    return browser_error