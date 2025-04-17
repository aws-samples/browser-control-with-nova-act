import logging
from typing import Dict, Any

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_aws import ChatBedrockConverse

from ..types import ProcessingType
from ..config import MODEL_CONFIG, DECISION_SYSTEM_PROMPT
from ..tools import create_decision_tools
from ..callbacks import queue_tool_call, queue_status, queue_text, queue_error

logger = logging.getLogger("nova_nodes.chat")

def chat_node(state) -> Dict[str, Any]:
    conversation_history = state.get("conversation_history", [])
    current_question = state.get("question", "")

    logger.info("Chat node processing query...")
    question = state.get("question", "")
    
    callback_handler = state.get("callback_handler")
    
    if callback_handler:
        callback_handler.set_active_node("chat")
    
    if not question:
        if callback_handler:
            queue_error("No question received", "chat")
        return {"answer": "Sorry, I didn't receive any question.", "complete": True}
    
    try:
        chat_model = ChatBedrockConverse(
            model=MODEL_CONFIG["decision_model"],
            region_name=MODEL_CONFIG["region"],
            temperature=MODEL_CONFIG["temperature"]["decision"]
        )
        
        llm_with_tools = chat_model.bind_tools(create_decision_tools())

        messages = [SystemMessage(content=DECISION_SYSTEM_PROMPT)]

        if conversation_history:
            for msg in conversation_history:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))
        
        messages.append(HumanMessage(content=f"Query: {question}"))
        
        callbacks = [callback_handler] if callback_handler else None
        response = llm_with_tools.invoke(
            messages,
            config={"callbacks": callbacks}
        )
        
        if hasattr(response, 'tool_calls') and response.tool_calls:
            for tool_call in response.tool_calls:
                tool_name = tool_call['name']
                args = tool_call['args']
                
                if callback_handler:
                    queue_tool_call(tool_name, args, "chat")
                
                if tool_name == 'direct_answer':
                    conversation_history = state.get("conversation_history", [])
                    response_text = args.get('response', "I couldn't generate a direct answer.")
                    conversation_history.append({
                        "role": "assistant",
                        "content": response_text
                    })
                    
                    logger.info("Providing direct answer")
                    return {
                        "answer": response_text,
                        "processing_type": ProcessingType.DIRECT_ANSWER.name,
                        "complete": True,
                        "node_status": "Direct answer ready",
                        "conversation_history": conversation_history  
                    }

                elif tool_name == 'browser_task':
                    logger.info("Query requires browser automation")
                    return {
                        "processing_type": ProcessingType.BROWSER_TASK.name,
                        "refined_question": args.get('refined_query', question),
                        "node_status": "Browser task identified",
                        "conversation_history": conversation_history
                    }
                    
                elif tool_name == 'follow_up_question':
                    conversation_history = state.get("conversation_history", [])
                    clarification_question = args.get('question', "Could you provide more details?")
                    conversation_history.append({
                        "role": "assistant",
                        "content": clarification_question
                    })
                    
                    logger.info("Requesting clarification")
                    return {
                        "answer": clarification_question,
                        "processing_type": ProcessingType.DIRECT_ANSWER.name,
                        "complete": True,
                        "node_status": "Clarification question ready",
                        "conversation_history": conversation_history 
                    }
        
        logger.info("No specific intent detected, defaulting to browser task")
        
        if callback_handler:
            queue_text("No specific intent detected, defaulting to browser task", "chat")
            
        return {
            "processing_type": ProcessingType.BROWSER_TASK.name,
            "node_status": "Browser task identified (default)",
            "conversation_history": conversation_history
        }
        
    except Exception as e:
        logger.exception(f"Error in chat node: {e}")
        
        if callback_handler:
            queue_error(f"Error in chat node: {str(e)}", "chat")
            
        return {
            "processing_type": ProcessingType.BROWSER_TASK.name,
            "error": str(e),
            "node_status": "Error occurred",
            "conversation_history": conversation_history
        }