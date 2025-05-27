import logging
import asyncio
import traceback
import time
from typing import Dict, Any, Optional

from app.libs.config.prompts import DEFAULT_MODEL_ID
from app.libs.utils.decorators import log_thought
from app.libs.core.task_classifier import TaskClassifier
from app.libs.core.task_executors import NavigationExecutor, ActionExecutor, AgentOrchestrator
from app.libs.data.conversation_store import ConversationStore, MemoryConversationStore
from app.libs.data.conversation_manager import ConversationManager
from app.libs.core.agent_manager import AgentManager

# Set up logger with more verbose level for debugging
logger = logging.getLogger("task_supervisor")
logger.setLevel(logging.DEBUG)

class TaskSupervisor:
    """Coordinates the task classification and execution process.
    
    This class acts as the central coordinator for processing user requests.
    It delegates to specialized components for task classification, execution,
    and conversation management.
    """
    
    def __init__(self, 
                 model_id: str = DEFAULT_MODEL_ID, 
                 region: str = "us-west-2",
                 conversation_store: Optional[ConversationStore] = None,
                 agent_manager: Optional[AgentManager] = None):
        
        self.model_id = model_id
        self.region = region
        
        # Initialize components
        self.task_classifier = TaskClassifier(model_id, region)
        self.navigation_executor = NavigationExecutor(model_id, region, agent_manager)
        self.action_executor = ActionExecutor(model_id, region, agent_manager)
        self.agent_orchestrator = AgentOrchestrator(model_id, region, agent_manager)
        
        # Set default conversation store if none provided
        self.conversation_store = conversation_store or MemoryConversationStore()
        
        # Initialize conversation manager
        self.conversation_manager = ConversationManager(self.conversation_store)
    
    async def navigate_execute(self, classification: Dict[str, Any], session_id: str, 
                             model_id: Optional[str] = None, region: Optional[str] = None) -> Dict[str, Any]:
        """Execute a navigation task."""
        url = classification.get("details", "https://www.google.com")
        
        # Add user navigation request to conversation history
        await self.conversation_manager.add_user_message(
            session_id=session_id, 
            content=f"Navigate to {url}"
        )
        
        tool_use_id = await self.conversation_manager.add_tool_usage(
            session_id=session_id,
            tool_name="navigate",
            tool_args={"url": url}
        )
    
        # Execute navigation
        result = await self.navigation_executor.execute(classification, session_id, model_id, region)
        
        result_for_history = result.copy()  
        status = "success" if "error" not in result else "error"
        
        await self.conversation_manager.add_tool_result(
            session_id=session_id,
            tool_use_id=tool_use_id,
            result=result_for_history,
            status=status
        )
        
        response_message = result.get("answer", result.get("message", ""))
        await self.conversation_manager.add_assistant_message(
            session_id=session_id,
            content=response_message,
            source="navigation_result"
        )
        
        return result
        
    async def act_execute(self, classification: Dict[str, Any], session_id: str, 
                        model_id: Optional[str] = None, region: Optional[str] = None) -> Dict[str, Any]:
        """Execute a browser action task."""
        user_message = classification.get("user_message", "")
        
        tool_use_id = await self.conversation_manager.add_tool_usage(
            session_id=session_id,
            tool_name="act",
            tool_args={"instruction": user_message}
        )

        # Execute action
        result = await self.action_executor.execute(classification, session_id, model_id, region)
        result_for_history = result.copy() 
        status = "success" if "error" not in result else "error"
        
        await self.conversation_manager.add_tool_result(
            session_id=session_id,
            tool_use_id=tool_use_id,
            result=result_for_history,
            status=status
        )
        
        # Record final response
        response_message = result.get("answer", result.get("message", ""))
        await self.conversation_manager.add_assistant_message(
            session_id=session_id,
            content=response_message,
            source="action_result"
        )
        
        return result
    
    async def orchestrate_agent_task(self, user_message: str, session_id: str, 
                                    model_id: Optional[str] = None, region: Optional[str] = None) -> Dict[str, Any]:
        """Execute a complex agent task."""
        # User message already stored in process_request() to avoid duplication
        
        # Execute agent task - orchestrator handles conversation history recording
        result = await self.agent_orchestrator.execute(user_message, session_id, model_id, region)
        
        return result
    
    async def process_request(self, user_message: str, session_id: str, model_id: Optional[str] = None, region: Optional[str] = None):
        try:
            start_time = time.time()
            
            # Ensure conversation session exists and add user message
            await self.conversation_manager.ensure_session(session_id)
            await self.conversation_manager.add_user_message(session_id, user_message)  

            # Log processing status without unnecessary sleep
            log_thought(
                session_id=session_id,
                type_name="processing", 
                category="status",
                node="Supervisor",
                content=f"Processing user request..."
            )

            await asyncio.sleep(0.5)
            
            # Update model and region if provided
            if model_id:
                self.model_id = model_id
                self.task_classifier.update_model(model_id)
            
            if region:
                self.region = region
                self.task_classifier.update_model(region=region)
            
            # Classify the task
            messages = await self.conversation_manager.get_conversation_history(session_id)
            classification = await self.task_classifier.classify(user_message, session_id, messages)
            execution_type = classification.get("type", "agent")
            
            # Handle conversation type differently
            if execution_type == "conversation":
                # Extract the actual response text
                answer = classification.get("answer", "I'm not sure how to respond to that.")
                
                # Add the direct model response to conversation history
                await self.conversation_manager.add_assistant_message(
                    session_id=session_id,
                    content=answer,
                    source="conversation_response"  # Mark this as a direct response
                )
                
                # Log for frontend
                log_thought(
                    session_id=session_id,
                    type_name="answer",
                    category="result",
                    node="Answer",
                    content=answer,
                    technical_details={
                        "processing_time_sec": round((time.time() - start_time), 2)
                    }
                )
                
                return {
                    "type": "conversation",
                    "answer": answer
                }
            
            # For non-conversation types, add classification message
            if execution_type != "agent":  # Skip for agent tasks
                classification_message = f"I'll handle this as a {execution_type} task."
                await self.conversation_manager.add_assistant_message(
                    session_id=session_id, 
                    content=classification_message, 
                    source="classification"
                )
                
            log_thought(
                session_id=session_id,
                type_name="reasoning", 
                category="analysis",
                node="Supervisor",
                content=f"I've analyzed the request and determined it to be a {execution_type} task."
            )
            
            
            # Execute appropriate task type
            result = None
            browser_url = None
            browser_state = None
            try:
                from app.libs.core.task_executors import BaseTaskExecutor
                base_executor = BaseTaskExecutor(model_id or self.model_id, region or self.region)
                browser_state = await base_executor.get_browser_state(session_id)
                if browser_state and browser_state.get("browser_initialized", False):
                    browser_url = browser_state.get("current_url", "")

                    from app.libs.core.agent_manager import get_agent_manager
                    agent_manager = get_agent_manager()
                    if session_id and browser_url:
                        agent_manager._session_urls[session_id] = browser_url

            except Exception as e:
                logger.error(f"Error getting browser state: {str(e)}")
            
            if execution_type == "navigate":
                result = await self.navigate_execute(classification, session_id, model_id, region)
            elif execution_type == "act":
                result = await self.act_execute(classification, session_id, model_id, region)
            else:
                result = await self.orchestrate_agent_task(user_message, session_id, model_id, region)
            
            if result is None:
                log_thought(
                    session_id=session_id,
                    type_name="error",
                    category="error",
                    node="Supervisor",
                    content=f"Execution method for {execution_type} returned None"
                )
                
                error_message = {
                    "role": "assistant",
                    "content": [{"text": "I'm sorry, something went wrong while processing your request."}]
                }
                messages = await self.conversation_store.load(session_id)
                messages.append(error_message)
                await self.conversation_store.save(session_id, messages)
                
                result = {
                    "type": execution_type,
                    "error": f"Execution method for {execution_type} returned None",
                    "answer": "I'm sorry, something went wrong while processing your request."
                }
            
            return result
            
        except Exception as e:
            error_message = f"Error in process_request: {str(e)}"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            
            # Add error to conversation history
            try:
                messages = await self.conversation_store.load(session_id)
                error_response = {
                    "role": "assistant",
                    "content": [{"text": f"Error processing request: {str(e)}"}]
                }
                messages.append(error_response)
                await self.conversation_store.save(session_id, messages)
            except Exception as e2:
                logger.error(f"Failed to save error to conversation: {e2}")
            
            log_thought(
                session_id=session_id,
                type_name="error",
                category="error",
                node="Supervisor",
                content=f"Error processing request: {str(e)}"
            )
            
            return {
                "type": "error",
                "error": str(e),
                "answer": "I'm sorry, I encountered an error while processing your request."
            }