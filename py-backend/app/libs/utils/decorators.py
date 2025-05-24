import logging
import functools
import asyncio
import time
from typing import Dict, Callable, Any, Optional, Type, Union
from app.libs.utils.thought_stream import thought_handler

logger = logging.getLogger(__name__)

def with_thought_callback(category: str, node_name: Optional[str] = None):
    def decorator(func: Callable):
        func_node_name = node_name or func.__name__
        is_async = asyncio.iscoroutinefunction(func)
        
        if is_async:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                session_id = kwargs.get('session_id', 'global')
                
                _send_thought(
                    session_id=session_id,
                    type_name="process",
                    category=category,
                    node=func_node_name,
                    content=f"Processing in {func_node_name}"
                )
                
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    _send_thought(
                        session_id=session_id,
                        type_name="error",
                        category="error",
                        node=func_node_name,
                        content=f"Error in {func_node_name}: {str(e)}",
                        technical_details={"error": str(e)}
                    )
                    raise
            
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                session_id = kwargs.get('session_id', 'global')
                
                _send_thought(
                    session_id=session_id,
                    type_name="process",
                    category=category,
                    node=func_node_name,
                    content=f"Processing in {func_node_name}"
                )
                
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    _send_thought(
                        session_id=session_id,
                        type_name="error",
                        category="error",
                        node=func_node_name,
                        content=f"Error in {func_node_name}: {str(e)}",
                        technical_details={"error": str(e)}
                    )
                    raise
            
            return sync_wrapper
    
    return decorator

def _send_thought(session_id: Optional[str], type_name: str, category: str, node: str, 
                 content: Union[str, Dict[str, Any]], **kwargs) -> None:
    if not session_id:
        return
        
    thought_cb = thought_handler.get_callback(session_id)
    if thought_cb:
        thought = {
            "type": type_name, 
            "category": category,
            "node": node,
            "content": content
        }
        thought.update(kwargs)
        thought_cb(thought)
        
        # Task start event
        if node == "Supervisor" and type_name == "processing" and category == "status":
            task_status_event = {
                "type": "task_status",
                "status": "start",
                "session_id": session_id
            }
            thought_cb(task_status_event)
        
        # Task completion event
        is_final_answer = (
            (node == "Answer" and category == "result") or 
            kwargs.get("final_answer") == True
        )
        
        if is_final_answer:
            task_status_event = {
                "type": "task_status",
                "status": "complete",
                "session_id": session_id,
                "final_answer": True
            }
            thought_cb(task_status_event)



def log_thought(session_id: Optional[str], type_name: str, category: str, node: str, 
               content: Union[str, Dict[str, Any]], **kwargs) -> None:
    _send_thought(session_id, type_name, category, node, content, **kwargs)
