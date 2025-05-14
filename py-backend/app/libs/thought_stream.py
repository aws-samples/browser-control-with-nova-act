import asyncio
import json
import logging
import time
from queue import Queue
from threading import Event
from typing import Dict, Any, Callable, AsyncIterator, Optional

logger = logging.getLogger("thought_stream")

class ThoughtHandler:
    def __init__(self):
        self.queues = {}
        self.events = {}
        self.callbacks = {}
    
    def register_session(self, session_id: str) -> Queue:
        """Register a new session for thought streaming"""
        logger.info(f"Registering thought stream session: {session_id}")
        if session_id in self.queues:
            return self.queues[session_id]
        
        self.queues[session_id] = Queue()
        self.events[session_id] = Event()
        return self.queues[session_id]
    
    def unregister_session(self, session_id: str):
        """Remove a session and clean up resources"""
        if session_id in self.queues:
            del self.queues[session_id]
        if session_id in self.events:
            del self.events[session_id]
        if session_id in self.callbacks:
            del self.callbacks[session_id]
    
    def get_callback(self, session_id: str) -> Callable[[Dict[str, Any]], None]:
        """Get or create a callback for the given session"""
        if session_id not in self.callbacks:
            def _callback(thought: Dict[str, Any]) -> None:
                thought_type = thought.get('type', 'unknown')
                
                # Log thought details (shortened for clarity)
                content = thought.get('content', {})
                content_summary = str(content)[:100] + "..." if len(str(content)) > 100 else str(content)
                logger.info(f"Received thought for session {session_id}: Type={thought_type}, Content={content_summary}")
                
                # Add thought to the queue for streaming
                if session_id in self.queues:
                    self.queues[session_id].put(thought)
                else:
                    logger.warning(f"Attempted to add thought to non-existent session: {session_id}")
            
            self.callbacks[session_id] = _callback
        
        return self.callbacks[session_id]
    
    def add_thought(self, session_id: str, thought: Dict[str, Any]):
        """Add a thought to a session's queue"""
        if session_id in self.queues:
            logger.debug(f"Adding thought to queue for session {session_id}")
            self.queues[session_id].put(thought)
        else:
            logger.warning(f"Attempted to add thought to non-existent session: {session_id}")
    
    def add_special_callback(self, session_id: str, event_data: Dict[str, Any]):
        """Add a special event like task_status to the queue"""
        self.add_thought(session_id, event_data)
    
    def mark_session_complete(self, session_id: str):
        """Mark a session as completed"""
        if session_id in self.events:
            logger.debug(f"Marking session complete: {session_id}")
            self.events[session_id].set()
        else:
            logger.warning(f"Attempted to mark non-existent session as complete: {session_id}")
    
    def is_session_complete(self, session_id: str) -> bool:
        """Check if a session is marked as complete"""
        return session_id in self.events and self.events[session_id].is_set()
    
    async def stream_generator(self, session_id: str) -> AsyncIterator[str]:
        """Generate an SSE stream for the given session"""
        logger.info(f"Setting up SSE stream generator for session: {session_id}")
        
        # Register session if not already registered
        if session_id not in self.queues:
            self.register_session(session_id)
        
        queue = self.queues[session_id]
        
        def format_sse(data: dict) -> str:
            return f"data: {json.dumps(data)}\n\n"
        
        # Send initial connection message
        yield format_sse({"type": "connected", "message": "Thought process stream connected"})
        await asyncio.sleep(0.01)
        
        # Send any cached thoughts
        thought_count = 0
        while not queue.empty():
            try:
                thought = queue.get_nowait()
                thought_count += 1
                if "id" not in thought:
                    thought["id"] = f"{session_id}-thought-{thought_count}"
                yield format_sse(thought)
                await asyncio.sleep(0.01)
            except:
                break
        
        # Stream new thoughts as they arrive
        ping_count = 0
        while not self.is_session_complete(session_id) or not queue.empty():
            try:
                if not queue.empty():
                    thought = queue.get_nowait()
                    thought_count += 1
                    
                    if "id" not in thought:
                        thought["id"] = f"{session_id}-thought-{thought_count}"
                    
                    logger.info(f"Streaming thought #{thought_count} for session {session_id}: {thought.get('type', 'unknown')}")
                    yield format_sse(thought)
                    await asyncio.sleep(0.01)
                else:
                    ping_count += 1
                    if ping_count >= 10:
                        ping_count = 0
                        yield format_sse({"type": "ping", "timestamp": f"{time.time()}"})
                    
                    await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Error in thought stream for session {session_id}: {e}")
                yield format_sse({"type": "error", "message": str(e)})
                await asyncio.sleep(0.5)
        
        # Send completion message
        yield format_sse({"type": "complete", "message": "Thought process complete"})
        
        # Clean up resources
        self.unregister_session(session_id)

# Create a singleton instance
thought_handler = ThoughtHandler()
