from typing import Dict, Any, Optional, Union, List
from enum import Enum
import asyncio
import json
import logging
from queue import Queue
import threading
from langchain_core.callbacks.base import AsyncCallbackHandler
import chainlit as cl

# Configure logging
logger = logging.getLogger("nova_callbacks")

class EventType(Enum):
    TEXT = "text"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SCREENSHOT = "screenshot"
    ERROR = "error"
    STATUS = "status"
    EXECUTOR_RESULT = "executor_result"

class CallbackMessage:
    def __init__(
        self, 
        event_type: EventType, 
        content: str, 
        node_id: str = "default", 
        extra: Optional[Dict[str, Any]] = None
    ):
        self.event_type = event_type
        self.content = content
        self.node_id = node_id
        self.extra = extra or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.event_type.value,
            "text": self.content if self.event_type == EventType.TEXT else "",
            "content": self.content,
            "node_id": self.node_id,
            "extra": self.extra
        }

event_queue = Queue()
queue_lock = threading.Lock()
is_processing = False

class BedrockCompatibleCallback(AsyncCallbackHandler):
    def __init__(self, active_node: str = ""):
        super().__init__()
        self.active_node = active_node
        self.token_buffer = ""
        self.node_steps = {}
        self.final_message = None
        self.current_elements = {}
        self.tool_steps = {}
        logger.debug(f"Callback initialized with node: {self.active_node}")
    
    def set_active_node(self, node_name: str) -> None:
        """Set the active node for the callback handler"""
        if self.active_node != node_name:
            logger.debug(f"Setting active node: {self.active_node} -> {node_name}")
            self.active_node = node_name
    
    async def on_chat_model_start(self, serialized: Dict[str, Any], messages: List[List[Dict[str, Any]]], **kwargs: Any) -> None:
        self.token_buffer = ""
        logger.debug(f"Chat model started, node: {self.active_node}")
    
    async def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> None:
        self.token_buffer = ""
        logger.debug(f"LLM started, node: {self.active_node}")
    
    async def _ensure_node_step(self, node_id: str) -> cl.Step:
        """Get or create a step for the specified node"""
        if node_id not in self.node_steps:
            step = cl.Step(name=f"{node_id.upper()}", type="thinking")
            await step.send()
            self.node_steps[node_id] = step
            self.current_elements[node_id] = []
        return self.node_steps[node_id]
    
    async def process_text_token(self, text: str, node_id: str) -> None:
        """Process a text token"""
        if not node_id:
            node_id = self.active_node
        
        if node_id == "__start__":
            node_id = "chat"
            
        # Special handling for executor and answer_gen nodes based on text content
        if any(marker in text.lower() for marker in [
            "task complete", "collecting final results", 
            "continuing task execution", "turn", "browser closed"
        ]):
            if node_id == "executor" and "executor_" not in node_id:
                if hasattr(self, "last_task_node") and self.last_task_node.startswith("executor_"):
                    node_id = self.last_task_node
                else:
                    node_id = "executor_1"
        
        elif node_id == "answer_gen" or any(marker in text.lower() for marker in [
            "based on the information", "here's what i found", "the answer is", 
            "final answer", "in conclusion", "to summarize", "comprehensive answer"
        ]):
            node_id = "answer_gen"
            self.last_answer_node = "answer_gen"
        
        elif "executor results:" in text.lower():
            if not node_id.startswith("executor_"):
                # Default to executor_1 if we don't have a specific task node
                if hasattr(self, "last_task_node") and self.last_task_node.startswith("executor_"):
                    node_id = self.last_task_node
                else:
                    node_id = "executor_1"
        
        self.token_buffer += text
        step = await self._ensure_node_step(node_id)
        await step.stream_token(text)
        
        if node_id.startswith("executor_"):
            self.last_task_node = node_id
    
    async def process_image_token(self, token: Dict[str, Any]) -> None:
        """Process an image token"""
        node_id = token.get("node_id", self.active_node)
        if node_id == "__start__":
            node_id = "chat"
            
        step = await self._ensure_node_step(node_id)
        image_path = token["path"]
        image_name = token.get("name", f"image_{len(self.current_elements.get(node_id, []))}")
        image_element = cl.Image(path=image_path, name=image_name, display="inline")
        self.current_elements[node_id].append(image_element)
        step.elements = self.current_elements[node_id].copy()
        await step.update()
    
    async def process_tool_call_token(self, token: Dict[str, Any]) -> None:
        """Process a tool call token"""
        node_id = token.get("node_id", self.active_node)
        if node_id == "__start__":
            node_id = "chat"
            
        step = await self._ensure_node_step(node_id)
        tool_name = token.get("tool_name", "unknown_tool")
        
        args = token.get("args", {})
        
        if isinstance(args, str):
            try:
                if args.startswith('{') or args.startswith('['):
                    args = json.loads(args)
            except:
                logger.debug(f"Ignored error: {e}")
        
        args_text = json.dumps(args, indent=2) if isinstance(args, dict) else str(args)
        
        formatted_text = f"\n\n**Tool Call: {tool_name}**\n```json\n{args_text}\n```\n"
        await step.stream_token(formatted_text)
    
    async def process_tool_result_token(self, token: Dict[str, Any]) -> None:
        """Process a tool result token"""
        node_id = token.get("node_id", self.active_node)
        if node_id == "__start__":
            node_id = "chat"
            
        step = await self._ensure_node_step(node_id)
        
        content = token.get("content", "")
        
        try:
            if isinstance(content, str) and (content.startswith('{') or content.startswith('[')):
                result_data = json.loads(content)
                result_text = json.dumps(result_data, indent=2)
            else:
                result_text = str(content)
        except Exception as e:
            logger.error(f"Error parsing tool result: {e}")
            result_text = str(content)
        
        formatted_text = f"\n\n**Tool Result:**\n```json\n{result_text}\n```\n"
        await step.stream_token(formatted_text)
    
    async def process_thinking_token(self, token: Dict[str, Any]) -> None:
        """Process a thinking token"""
        node_id = token.get("node_id", self.active_node)
        if node_id == "__start__":
            node_id = "chat"
            
        step = await self._ensure_node_step(node_id)
        
        content = token.get("content", "")
        thinking_text = str(content)
        if node_id in self.current_elements:
            step.elements = self.current_elements[node_id].copy()
            await step.update()

        formatted_text = f"\n\n**Thinking:**\n```\n{thinking_text}\n```\n"
        await step.stream_token(formatted_text)
    
    async def on_llm_new_token(self, token: Any, **kwargs: Any) -> None:
        """Process a new token from the LLM"""
        try:
            # Dispatch to appropriate handler based on token type
            if isinstance(token, dict):
                if "type" in token:
                    token_type = token["type"]
                    
                    if token_type == "image" and "path" in token:
                        await self.process_image_token(token)
                        return
                    
                    elif token_type == "tool_call":
                        await self.process_tool_call_token(token)
                        return
                    
                    elif token_type == "tool_result":
                        await self.process_tool_result_token(token)
                        return
                    
                    elif token_type == "thinking":
                        await self.process_thinking_token(token)
                        return
                
                # For plain text tokens with explicit node_id
                if "text" in token:
                    text = token["text"]
                    node_id = token.get("node_id", None)
                    await self.process_text_token(text, node_id)
                    return
            
            # Handle string tokens
            elif isinstance(token, str):
                await self.process_text_token(token, None)
                return
            
            # Handle list tokens
            elif isinstance(token, list):
                text = ""
                node_id = None
                for item in token:
                    if isinstance(item, dict):
                        if item.get("type") == "text" and "text" in item:
                            text += item["text"]
                            # Use item's node_id if available
                            if "node_id" in item and node_id is None:
                                node_id = item["node_id"]
                
                if text:
                    await self.process_text_token(text, node_id)
                    return
                    
        except Exception as e:
            logger.error(f"Error in on_llm_new_token: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def on_llm_end(self, response, **kwargs) -> None:
        """Handle LLM completion"""
        node_id = self.active_node if self.active_node != "__start__" else "chat"
        if node_id in self.node_steps:
            try:
                step = self.node_steps[node_id]
                step.type = "complete"
                await step.update()
            except Exception as e:
                logger.error(f"Error updating step: {str(e)}")
    
    async def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        self.token_buffer = ""
    
    async def set_final_answer(self, content: str, elements: List = None):
        """Set the final answer message"""
        if self.final_message:
            self.final_message.content = content
            if elements:
                self.final_message.elements = elements
            await self.final_message.update()
        else:
            self.final_message = cl.Message(content=content, elements=elements if elements else [])
            await self.final_message.send()
        
    async def add_image(self, image_path: str, node_id: str = None, name: str = None, description: str = None, position: str = "bottom"):
        """Add an image to a node step"""
        node = node_id or self.active_node
        if node == "__start__":
            node = "chat"
        if not node:
            logger.error("Cannot add image: no active node specified")
            return
            
        step = await self._ensure_node_step(node)
        image_name = name or f"image_{len(self.current_elements.get(node, []))}"
        image_element = cl.Image(path=image_path, name=image_name, display="inline")
        
        if position == "top":
            self.current_elements[node].insert(0, image_element)
        else:
            self.current_elements[node].append(image_element)
        
        step.elements = self.current_elements[node].copy()
        
        if description:
            await step.stream_token(f"\n*{description}*\n")
            
        await step.update()

def queue_event(event: CallbackMessage) -> bool:
    """Queue a callback event for processing"""
    try:
        with queue_lock:
            event_queue.put(event)
        logger.debug(f"Event queued: {event.event_type.value} - {event.content[:30]}..." 
              if len(event.content) > 30 else f"Event queued: {event.event_type.value} - {event.content}")
        return True
    except Exception as e:
        logger.error(f"Error queueing event: {str(e)}")
        return False

def queue_text(content: str, node_id: str = "default") -> bool:
    """Queue a text event"""
    return queue_event(CallbackMessage(EventType.TEXT, content, node_id))

def queue_thinking(content: str, node_id: str = "default") -> bool:
    """Queue a thinking event"""
    return queue_event(CallbackMessage(EventType.THINKING, content, node_id))

def queue_tool_call(tool_name: str, args: Dict[str, Any], node_id: str = "default") -> bool:
    """Queue a tool call event"""
    try:
        if isinstance(args, str):
            try:
                if args.startswith('{') or args.startswith('['):
                    args = json.loads(args)
            except:
                logger.debug(f"Ignored error: {e}")
                
        args_json = json.dumps(args, indent=2) if isinstance(args, dict) else str(args)
        logger.debug(f"TOOL CALL: {tool_name}, ARGS: {args_json[:100]}")
        
        return queue_event(CallbackMessage(
            EventType.TOOL_CALL, 
            f"Calling tool: {tool_name}", 
            node_id, 
            {"tool_name": tool_name, "args": args}
        ))
    except Exception as e:
        logger.error(f"Error in queue_tool_call: {e}")
        return False

def queue_tool_result(result: str, node_id: str = "default") -> bool:
    """Queue a tool result event"""
    try:
        logger.debug(f"TOOL RESULT: {result[:100]}")
        
        return queue_event(CallbackMessage(
            EventType.TOOL_RESULT, 
            result,
            node_id,
            {}
        ))
    except Exception as e:
        logger.error(f"Error in queue_tool_result: {e}")
        return False

def queue_screenshot(image_path: str, description: Optional[str] = None, 
                    node_id: str = "default", extra: Optional[Dict[str, Any]] = None) -> bool:
    """Queue a screenshot event"""
    extra_data = extra or {}
    return queue_event(CallbackMessage(
        EventType.SCREENSHOT, 
        description or "Browser screenshot", 
        node_id, 
        {
            "path": image_path, 
            "name": f"img_{hash(image_path) % 10000}", 
            "description": description,
            "thinking_related": extra_data.get("thinking_related", False)
        }
    ))

def queue_error(error_message: str, node_id: str = "default") -> bool:
    """Queue an error event"""
    return queue_event(CallbackMessage(EventType.ERROR, error_message, node_id))

def queue_status(status_message: str, node_id: str = "default") -> bool:
    """Queue a status event"""
    return queue_event(CallbackMessage(EventType.STATUS, status_message, node_id))

def queue_executor_result(result: Dict[str, Any], node_id: str = "default") -> bool:
    """Queue an executor result event with structured data"""
    try:
        result_text = json.dumps(result, indent=2) if isinstance(result, dict) else str(result)
        logger.debug(f"EXECUTOR RESULT for {node_id}")
        
        return queue_event(CallbackMessage(
            EventType.EXECUTOR_RESULT, 
            result_text,
            node_id,
            result
        ))
    except Exception as e:
        logger.error(f"Error in queue_executor_result: {e}")
        return False

async def process_callback(callback_handler, event: CallbackMessage) -> None:
    """Process a single callback event"""
    if not callback_handler:
        return
        
    try:
        logger.debug(f"PROCESSING EVENT: {event.event_type.value}, NODE: {event.node_id}")
        
        # Direct process for specific event types
        if event.event_type == EventType.SCREENSHOT and hasattr(callback_handler, "add_image"):
            thinking_related = event.extra.get("thinking_related", False)
            node_id = event.node_id
            
            await callback_handler.add_image(
                event.extra["path"], 
                node_id, 
                event.extra.get("name", "screenshot"),
                event.extra.get("description", "Browser screenshot")
            )
            
            if thinking_related and node_id in callback_handler.node_steps:
                step = callback_handler.node_steps[node_id]
                step.elements = callback_handler.current_elements[node_id].copy()
                await step.update()
                
        # Unified approach for other event types using token format
        elif hasattr(callback_handler, "on_llm_new_token"):
            # Convert events to appropriate token format for each event type
            if event.event_type == EventType.EXECUTOR_RESULT:
                result_data = event.extra
                node_id = event.node_id
                step = await callback_handler._ensure_node_step(node_id)

                # Extract key information
                url = result_data.get("current_url", result_data.get("url", "N/A"))
                title = result_data.get("page_title", result_data.get("title", "N/A"))
                task_desc = result_data.get("description", "Task execution")
                
                # Format a nice summary
                formatted_text = f"\n\n**Execution Result:**\n"  
                formatted_text += f"**Task:** {task_desc}\n"
                formatted_text += f"**URL:** {url}\n"
                formatted_text += f"**Page Title:** {title}\n\n"
                
                # Add the actual result
                if "result" in result_data:
                    result_content = result_data["result"]
                    formatted_text += f"**Result:**\n```\n{result_content}\n```\n"
                    
                await step.stream_token(formatted_text)
                
            elif event.event_type == EventType.TOOL_CALL:
                args = event.extra.get("args", {})
                
                if isinstance(args, str):
                    try:
                        if args.startswith('{') or args.startswith('['):
                            args = json.loads(args)
                    except:
                        logger.debug(f"Ignored error: {e}")
                
                await callback_handler.on_llm_new_token({
                    "type": "tool_call",
                    "tool_name": event.extra.get("tool_name", "unknown_tool"),
                    "args": args,
                    "node_id": event.node_id
                })
            elif event.event_type == EventType.TOOL_RESULT:
                await callback_handler.on_llm_new_token({
                    "type": "tool_result",
                    "content": event.content,
                    "node_id": event.node_id
                })
            elif event.event_type == EventType.THINKING:
                await callback_handler.on_llm_new_token({
                    "type": "thinking",
                    "content": event.content,
                    "node_id": event.node_id
                })
            elif event.event_type == EventType.ERROR:
                await callback_handler.on_llm_new_token({
                    "type": "error",
                    "content": event.content,
                    "node_id": event.node_id
                })
            else:
                # For TEXT and other event types
                token_data = {
                    "text": event.content,
                    "node_id": event.node_id
                }
                await callback_handler.on_llm_new_token(token_data)
    except Exception as e:
        logger.error(f"Error processing callback: {e}")
        import traceback
        traceback.print_exc()

async def process_event_queue(callback_handler) -> None:
    """Process all events in the queue"""
    global is_processing
    
    if is_processing:
        return
    
    is_processing = True
    try:
        events_processed = 0
        events_count = event_queue.qsize()
        if events_count > 0:
            logger.debug(f"Processing {events_count} events from queue")
        
        while not event_queue.empty():
            try:
                with queue_lock:
                    if event_queue.empty():
                        break
                    event = event_queue.get()
                
                if callback_handler:
                    await process_callback(callback_handler, event)
                
                events_processed += 1
                
                # Periodic yield to event loop
                if events_processed % 5 == 0:
                    await asyncio.sleep(0.05)
                    
            except Exception as e:
                logger.error(f"Error processing event: {e}")
                import traceback
                traceback.print_exc()
    finally:
        is_processing = False

async def event_processing_loop(callback_handler):
    """Main event processing loop"""
    while True:
        await process_event_queue(callback_handler)
        await asyncio.sleep(0.2)
