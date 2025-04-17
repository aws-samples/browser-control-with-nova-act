import os
import time
import json
import tempfile
from typing import Dict, Any, Optional, List
from datetime import datetime
from nova_act import NovaAct, ActResult
from .config import DEFAULT_BROWSER_SETTINGS

class BrowserController:
    """Browser controller class for Nova Act interactions"""
    
    def __init__(self, nova_act_instance: NovaAct):
        self.nova = nova_act_instance
        self._screenshot_dir = tempfile.mkdtemp(prefix=DEFAULT_BROWSER_SETTINGS["screenshot_dir_prefix"])
        self.graph_state = None
        print(f"Browser controller initialized with screenshot dir: {self._screenshot_dir}")

    def is_initialized(self) -> bool:
        """Check if the browser is properly initialized"""
        try:
            # Check if the nova object exists and has an accessible page property
            return self.nova is not None and hasattr(self.nova, 'page') and self.nova.page is not None
        except Exception as e:
            print(f"Checking browser initialization error: {e}")
            return False
        
    def execute_action(self, request: str, max_steps: int = None, timeout: int = None) -> ActResult:
        if not self.is_initialized():
            raise ValueError("Browser not initialized")
        
        # Get default values from config if not provided
        max_steps = DEFAULT_BROWSER_SETTINGS.get("max_steps", 30)    
        timeout = DEFAULT_BROWSER_SETTINGS.get("timeout", 300)
        
        schema = {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "action_performed": {"type": "string"},
                "details": {"type": "string"}
            },
            "required": ["success", "action_performed", "details"]
        }
        result = self.nova.act(request, schema=schema, max_steps=max_steps, timeout=timeout)
        return result
        
    def extract_structured_data(self, schema: Dict[str, Any], prompt: str = "", max_steps: int = None, timeout: int = None) -> ActResult:
        if not self.is_initialized():
            raise ValueError("Browser not initialized")
        
        # Get default values from config if not provided
        if max_steps is None:
            max_steps = DEFAULT_BROWSER_SETTINGS.get("max_steps", 30)
            
        if timeout is None:
            timeout = DEFAULT_BROWSER_SETTINGS.get("timeout", 300)
        
        # Add prompt to schema description if provided
        if prompt:
            schema_with_prompt = {
                **schema,
                "description": prompt
            }
        else:
            schema_with_prompt = schema
            
        result = self.nova.act(schema_with_prompt, max_steps=max_steps, timeout=timeout)
        return result
        
    def take_screenshot(self) -> str:
        """
        Capture a screenshot of the current page
        """
        if not self.is_initialized():
            raise ValueError("Browser not initialized")
            
        # Generate screenshot file path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(self._screenshot_dir, f"screenshot_{timestamp}.png")
        
        # Capture screenshot
        self.nova.page.screenshot(path=screenshot_path)
        return screenshot_path
        
    def go_to_url(self, url: str) -> bool:
        """
        Navigate to the specified URL
        """
        if not self.is_initialized():
            raise ValueError("Browser not initialized")
            
        try:
            self.nova.go_to_url(url)
            return True
        except Exception as e:
            print(f"Navigation error: {e}")
            return False
            
    def get_page_content(self) -> str:
        """
        Get the HTML content of the current page
        """
        if not self.is_initialized():
            raise ValueError("Browser not initialized")
            
        return self.nova.page.content()
        
    def get_page_title(self) -> str:
        """
        Get the title of the current page
        """
        if not self.is_initialized():
            raise ValueError("Browser not initialized")
            
        return self.nova.page.title()
        
    def get_current_url(self) -> str:
        """
        Get the URL of the current page
        """
        if not self.is_initialized():
            raise ValueError("Browser not initialized")
            
        return self.nova.page.url

    
    def update_graph_state_with_image(self, screenshot_path):
        """Update graph state with the latest screenshot"""
        if hasattr(self, 'graph_state') and self.graph_state:
            self.graph_state["current_image_path"] = screenshot_path
            return True
        return False
    
    def set_graph_state(self, state):
        """Set the current graph state reference"""
        self.graph_state = state