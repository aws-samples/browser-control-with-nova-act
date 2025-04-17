"""
Nova Act Browser Automation Tools

This module provides the tool implementations for browser automation.
"""

import os
import time
import json
import tempfile
from enum import Enum
from typing import Type, Dict, Any, List, Optional, Tuple, Union
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from langchain.tools import BaseTool
from langchain_core.tools import tool

# Import Nova Act related components
from nova_act import NovaAct, ActResult
from .browser_controller import BrowserController
from .config import DEFAULT_BROWSER_SETTINGS

# ------------------------------------------------------
# Input schemas for browser automation tools
# ------------------------------------------------------

# Input models for browser tools
class KeyboardBrowserInput(BaseModel):
    goal: str = Field(..., description="Objective to achieve with this keyboard action")
    action_type: str = Field(..., description="Type of keyboard action: 'search' or 'type'")
    text_input: str = Field(..., 
        description="""Text to enter: 
- For 'search': Complete search query including filters (e.g., \"white shirt under $30 with 4.5+ stars\")
- For 'type': Text to enter in the field (e.g., \"john.doe@example.com\" for email field).")
"""
    )
    target_description: str = Field(..., description="Description of the element to interact with (e.g., \"search box in top center\", \"email field in login form\")")

class MouseBrowserInput(BaseModel):
    goal: str = Field(..., description="Objective to achieve with this mouse action")
    action_type: str = Field(..., description="Type of mouse action: 'click', 'drag', 'scroll', 'select', 'hover'")
    target_description: str = Field(..., description="Description of the element to interact with (e.g., \"blue button in top right\", \"price slider\", \"target to find through scroll\"")
    action_parameter: str = Field("", description="Action parameter: click_type (single/double/right), drag distance/direction, scroll_direction (up/down), or option to select. (This parameter will be ignored for scroll)")

class ExtractElementInput(BaseModel):
    selector: Optional[str] = Field(None, description="CSS or XPath selector")
    text: Optional[str] = Field(None, description="Text content to find element by")
    description: Optional[str] = Field(None, description="Natural language description of element. Consider describing visual appearance, position, and nearby elements for better identification.")
    action: Optional[str] = Field(None, description="Action: click, hover, get_text, is_visible, get_attribute")
    attribute_name: Optional[str] = Field(None, description="Attribute name if action is get_attribute")
    
    @field_validator('description')
    def at_least_one_field_present(cls, v, values):
        if not v and not values.get('selector') and not values.get('text'):
            raise ValueError("At least one of 'selector', 'text', or 'description' must be provided")
        return v

class ExtractDataInput(BaseModel):
    description: str = Field(..., description="Description of data to extract. Consider specifying exact data needed (e.g., 'product prices with currency', 'only items on sale'")
    schema_type: str = Field(..., description="Schema type: product, search_result, form, navigation, bool, custom")
    custom_schema: Optional[Dict[str, Any]] = Field(None, description="Custom schema if schema_type is custom")
    
    @field_validator('custom_schema')
    def validate_custom_schema(cls, v, values):
        if values.get('schema_type') == 'custom' and not v:
            raise ValueError("custom_schema is required when schema_type is 'custom'")
        return v

class CollectResultInput(BaseModel):
    desired_results: str = Field(..., description="Description of desired results to collect")

class GoToURLInput(BaseModel):
    url: str = Field(..., 
    description="URL to navigate to. Use for direct navigation using search term in URL or necessary recovery when encountering verification challenges.")

# ------------------------------------------------------
# Web Task Planning Models
# ------------------------------------------------------

class WebTask(BaseModel):
    """
    Represents a single web automation task with its own starting point.
    """
    description: str = Field(
        ..., 
        description="Clear description of what this task should accomplish"
    )
    start_url: str = Field(
        DEFAULT_BROWSER_SETTINGS["start_url"], 
        description="""Optimal starting URL for this task, preferably with search parameters if applicable 
        """
    )
    sequence: int = Field(
        1, 
        description="Execution sequence number - tasks with the same number will execute in parallel. Group independent tasks (like those using different websites) under the same sequence value for concurrent execution"
    )

class WebTaskPlan(BaseModel):
    """
    Complete plan containing multiple web automation tasks.
    """
    tasks: List[WebTask] = Field(
        ..., 
        description="List of tasks to execute. Each task should have sequence number indicating execution order."
    )


# Keyboard browser tool implementation
class KeyboardBrowserTool(BaseTool):
    name: str = "Browser::keyboard"
    description: str = "Execute keyboard actions like typing text or performing searches"
    args_schema: Type[BaseModel] = KeyboardBrowserInput
    
    def __init__(self, browser_controller):
        super().__init__()
        self._browser = browser_controller
        
    def _run(self, goal: str, action_type: str, text_input: str, 
            target_description: str) -> str:
        try:
            prompt = f"Goal: {goal}\n"
            
            if action_type == "search":
                prompt += f"Search for: {text_input}\n"
            elif action_type == "type":
                prompt += f"Type this text: {text_input}\n"
            
            if target_description:
                prompt += f"Target: {target_description}\n"
            
            # Get default values from config
            max_steps = DEFAULT_BROWSER_SETTINGS.get("max_steps", 30)
            timeout = DEFAULT_BROWSER_SETTINGS.get("timeout", 300)
            
            result = self._browser.execute_action(prompt, max_steps=max_steps, timeout=timeout)
            screenshot_path = self._browser.take_screenshot()
            self._browser.update_graph_state_with_image(screenshot_path)
            
            if hasattr(result, 'parsed_response') and result.parsed_response:
                return json.dumps({
                    "status": "success" if result.parsed_response.get("success", False) else "error",
                    "goal": goal,
                    "action_type": action_type,
                    "message": result.parsed_response.get("details", "No details provided"),
                    "action_performed": result.parsed_response.get("action_performed", "unknown")
                })
            else:
                return json.dumps({
                    "status": "completed",
                    "goal": goal,
                    "action_type": action_type,
                    "message": "Action completed but no structured response available"
                })
        except Exception as e:
            return json.dumps({
                "status": "error",
                "message": str(e)
            })


class MouseBrowserTool(BaseTool):
    name: str = "Browser::mouse"
    description: str = "Execute mouse actions like clicking, dragging, scrolling, or selecting"
    args_schema: Type[BaseModel] = MouseBrowserInput
    
    def __init__(self, browser_controller):
        super().__init__()
        self._browser = browser_controller
    
    def _perform_fallback_scroll(self, action_parameter=""):
        scroll_distance = 400
        if action_parameter and action_parameter.lower() == "up":
            scroll_distance = -400
            
        script = f"window.scrollBy(0, {scroll_distance});"
        self._browser.nova.page.evaluate(script)
        
        from types import SimpleNamespace
        result = SimpleNamespace()
        result.parsed_response = {
            "success": True,
            "details": f"Used fallback scrolling mechanism ({action_parameter})",
            "action_performed": "direct_scroll"
        }
        return result
        
    def _run(self, goal: str, action_type: str, 
            target_description: str,
            action_parameter: str = "") -> str:
        result = None 
        try:
            prompt = f"Goal: {goal}\n"
            
            if action_type == "click":
                click_type = f" with {action_parameter} click" if action_parameter else ""
                prompt += f"Click{click_type} on: {target_description}"
            elif action_type == "drag":
                prompt += f"Drag {target_description} {action_parameter}"
            elif action_type == "scroll":
                prompt += f"Scroll down to find: {target_description}"
            elif action_type == "select":
                prompt += f"Select '{action_parameter}' from: {target_description}"
            elif action_type == "hover":
                prompt += f"Hover over: {target_description}"
            
            max_steps = DEFAULT_BROWSER_SETTINGS.get("max_steps", 30)
            timeout = DEFAULT_BROWSER_SETTINGS.get("timeout", 300)
            result = self._browser.execute_action(prompt, max_steps=max_steps, timeout=timeout)
            
            if action_type == "scroll" and (
                not hasattr(result, 'parsed_response') or 
                not result.parsed_response or
                not result.parsed_response.get("success", False)
            ):
                try:
                    result = self._perform_fallback_scroll(action_parameter)
                except Exception as scroll_error:
                    print(f"Fallback scrolling failed: {scroll_error}")
            
            screenshot_path = self._browser.take_screenshot()
            self._browser.update_graph_state_with_image(screenshot_path)
            
            if hasattr(result, 'parsed_response') and result.parsed_response:
                return json.dumps({
                    "status": "success" if result.parsed_response.get("success", False) else "error",
                    "goal": goal,
                    "action_type": action_type,
                    "message": result.parsed_response.get("details", "No details provided"),
                    "action_performed": result.parsed_response.get("action_performed", "unknown")
                })
            else:
                return json.dumps({
                    "status": "completed",
                    "goal": goal,
                    "action_type": action_type, 
                    "message": "Action completed but no structured response available"
                })
        except Exception as e:
            if action_type == "scroll":
                try:
                    result = self._perform_fallback_scroll(action_parameter)
                    screenshot_path = self._browser.take_screenshot()
                    self._browser.update_graph_state_with_image(screenshot_path)
                    
                    return json.dumps({
                        "status": "success",
                        "goal": goal,
                        "action_type": "scroll",
                        "message": f"Used emergency fallback scrolling after error",
                        "action_performed": "emergency_direct_scroll"
                    })
                except:
                    logger.debug(f"Ignored error: {e}")
            
            return json.dumps({
                "status": "error",
                "message": str(e)
            })



class ExtractElementTool(BaseTool):
    name: str = "Browser::extract"
    description: str = "Find specific UI elements and interact with them"
    args_schema: Type[BaseModel] = ExtractElementInput
    
    def __init__(self, browser_controller):
        super().__init__()
        self._browser = browser_controller
        
    def _run(self, 
             selector: Optional[str] = None, 
             text: Optional[str] = None, 
             description: Optional[str] = None,
             action: Optional[str] = None,
             attribute_name: Optional[str] = None) -> str:
        try:
            if not self._browser.is_initialized():
                return json.dumps({"status": "error", "message": "Browser not initialized"})
            
            element_found = False
            element_result = {}
            
            if description:
                action_result = self._browser.nova.act(f"Find {description}")
                element_found = True
                element_result["description_result"] = getattr(action_result, "response", "Element found")
            
            if selector:
                is_visible = self._browser.nova.page.is_visible(selector)
                element_found = is_visible
                element_result["selector_visible"] = is_visible
                
                if is_visible and action:
                    if action == "click":
                        self._browser.nova.page.click(selector)
                        element_result["action_result"] = "Element clicked"
                    elif action == "hover":
                        self._browser.nova.page.hover(selector)
                        element_result["action_result"] = "Element hovered"
                    elif action == "get_text":
                        text_content = self._browser.nova.page.text_content(selector)
                        element_result["text"] = text_content
                    elif action == "get_attribute" and attribute_name:
                        attribute_value = self._browser.nova.page.get_attribute(selector, attribute_name)
                        element_result["attribute"] = {attribute_name: attribute_value}
            
            if text:
                text_selector = f"text={text}"
                is_visible = self._browser.nova.page.is_visible(text_selector)
                element_found = element_found or is_visible
                element_result["text_visible"] = is_visible
                
                if is_visible and action:
                    if action == "click":
                        self._browser.nova.page.click(text_selector)
                        element_result["action_result"] = "Element clicked"
                    elif action == "hover":
                        self._browser.nova.page.hover(text_selector)
                        element_result["action_result"] = "Element hovered"
                    elif action == "get_text":
                        text_content = self._browser.nova.page.text_content(text_selector)
                        element_result["text"] = text_content
            
            screenshot_path = self._browser.take_screenshot()
            self._browser.update_graph_state_with_image(screenshot_path)

            if element_found:
                return json.dumps({
                    "status": "success",
                    "message": "Element operation completed",
                    "details": element_result
                })
            else:
                return json.dumps({
                    "status": "error",
                    "message": "Element not found",
                    "details": element_result
                })
                
        except Exception as e:
            return json.dumps({
                "status": "error",
                "message": str(e)
            })

class ExtractDataTool(BaseTool):
    name: str = "Browser::data"
    description: str = "Extract structured data from the current page using a schema"
    args_schema: Type[BaseModel] = ExtractDataInput
    
    def __init__(self, browser_controller):
        super().__init__()
        self._browser = browser_controller
        
    def _run(self, description: str, schema_type: str, custom_schema: Optional[Dict[str, Any]] = None) -> str:
        try:
            if not self._browser.is_initialized():
                return json.dumps({"status": "error", "message": "Browser not initialized"})
            
            schema = None
            if schema_type == "custom" and custom_schema:
                if isinstance(custom_schema, str):
                    schema = json.loads(custom_schema) 
                else:
                    schema = custom_schema
            elif schema_type == "product":
                from .schemas import ProductSchema
                schema = ProductSchema.model_json_schema()
            elif schema_type == "search_result":
                from .schemas import SearchResultSchema
                schema = SearchResultSchema.model_json_schema()
            elif schema_type == "form":
                from .schemas import FormFieldsSchema
                schema = FormFieldsSchema.model_json_schema()
            elif schema_type == "navigation":
                from .schemas import NavigationSchema
                schema = NavigationSchema.model_json_schema()
            elif schema_type == "bool":
                from .schemas import BoolSchema
                schema = BoolSchema.model_json_schema()
            else:
                return json.dumps({
                    "status": "error",
                    "message": f"Unknown schema type: {schema_type}"
                })
            
            # Clear, direct prompt with the extraction task
            prompt = f"{description} from the current webpage"
            
            # Execute with schema
            # Get default values from config
            max_steps = DEFAULT_BROWSER_SETTINGS.get("max_steps", 30)
            timeout = DEFAULT_BROWSER_SETTINGS.get("timeout", 300)
            
            result = self._browser.nova.act(
                prompt, 
                schema=schema, 
                max_steps=max_steps,
                timeout=timeout
            )
            
            screenshot_path = self._browser.take_screenshot()
            self._browser.update_graph_state_with_image(screenshot_path)
            
            # Handle structured response properly
            if hasattr(result, 'parsed_response') and result.parsed_response:
                return json.dumps({
                    "status": "success",
                    "data": result.parsed_response,
                    "message": "Data extracted successfully"
                })
            else:
                # Fallback for unstructured response
                return json.dumps({
                    "status": "partial_success",
                    "data": getattr(result, "response", {}),
                    "message": "Data extraction completed but structured response not available"
                })
                
        except Exception as e:
            return json.dumps({
                "status": "error",
                "message": str(e)
            })



class GoToURLTool(BaseTool):
    name: str = "Browser::go_to_url"
    description: str = "Navigate browser to a specified URL"
    args_schema: Type[BaseModel] = GoToURLInput
    
    def __init__(self, browser_controller):
        super().__init__()
        self._browser = browser_controller
        
    def _run(self, url: str) -> str:
        try:
            if not self._browser.is_initialized():
                return json.dumps({
                    "status": "error",
                    "message": "Browser not initialized"
                })
                
            # Use go_to_url method from browser controller
            self._browser.go_to_url(url)
            
            # Take screenshot and update state
            screenshot_path = self._browser.take_screenshot()
            self._browser.update_graph_state_with_image(screenshot_path)
            
            # Get current URL and page title for verification
            current_url = self._browser.get_current_url()
            page_title = self._browser.get_page_title()
            
            return json.dumps({
                "status": "success",
                "message": f"Navigated to {url}",
                "current_url": current_url,
                "page_title": page_title,
                "screenshot": screenshot_path
            })
            
        except Exception as e:
            return json.dumps({
                "status": "error",
                "message": f"Failed to navigate to URL: {str(e)}"
            })


class CollectResultTool(BaseTool):
    name: str = "Browser::collect"
    description: str = "Collect final results"
    args_schema: Type[BaseModel] = CollectResultInput
    
    def __init__(self, browser_controller):
        super().__init__()
        self._browser = browser_controller
        
    def _run(self, desired_results: str) -> str:
        try:
            screenshot_path = self._browser.take_screenshot()
            self._browser.update_graph_state_with_image(screenshot_path)
            
            current_url = self._browser.get_current_url()
            page_title = self._browser.get_page_title()
            
            additional_info = {}
            if "content" in desired_results.lower():
                content_sample = self._browser.get_page_content()[:500] + "..."
                additional_info["content_sample"] = content_sample
                
            return json.dumps({
                "status": "success",
                "screenshot": screenshot_path,
                "url": current_url,
                "title": page_title,
                "additional_info": additional_info,
                "message": f"Results collected for: {desired_results}"
            })
        except Exception as e:
            return json.dumps({
                "status": "error",
                "message": str(e)
            })


# ------------------------------------------------------
# Decision Making Tools 
# ------------------------------------------------------

@tool
def direct_answer(response: str) -> str:
    """
    Provide a direct answer to a question without browser automation.
    
    Args:
        response: Complete, helpful response to the user's question
        
    Returns:
        The formatted response
    """
    return response

@tool
def browser_task(refined_query: str) -> str:
    """
    Process a query that requires browser automation.
    
    Args:
        refined_query: Refined version of the user query, clarified for automation
        
    Returns:
        The refined query to pass to the planner
    """
    return refined_query

@tool
def follow_up_question(question: str) -> str:
    """
    Ask a follow-up question when the user's request is unclear.
    
    Args:
        question: Question to ask the user for clarification
        
    Returns:
        The follow-up question
    """
    return question


class WebTaskPlanTool(BaseTool):
    name: str = "create_web_tasks"
    description: str = """
    Create a structured plan for web automation with tasks in sequence.
    
    Separate tasks when they involve:
    - Different websites or services
    - Distinct logical operations
    - Independent workflows
    
    IMPORTANT: Always include ALL key constraints from the original query in your task descriptions.
    """
    
    # Schema definition for the tool input
    args_schema: Type[BaseModel] = WebTaskPlan
    
    def _run(self, tasks: List[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """Implementation required by BaseTool"""
        if not tasks:
            tasks = [{"description": "Placeholder task"}]
        return {"tasks": tasks}

# ------------------------------------------------------
# Factory Functions
# ------------------------------------------------------

def create_decision_tools():
    """Create tools for decision making in chat node"""
    return [direct_answer, browser_task, follow_up_question]