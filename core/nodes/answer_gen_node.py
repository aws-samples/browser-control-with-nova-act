"""
Answer generation node

This module provides functionality to generate final answers based on
the collected information from browser automation tasks.
"""

import json
import logging
import asyncio
from typing import Dict, Any, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_aws import ChatBedrockConverse

from ..callbacks import queue_text, queue_status, queue_tool_result
from ..types import BrowserWorkflowState
from ..config import MODEL_CONFIG

# Configure logging
logger = logging.getLogger("nova_nodes.answer_gen")

def answer_gen_node(state: BrowserWorkflowState) -> Dict[str, Any]:
    logger.info("Generating final answer...")
    
    node_id = "answer_gen"
    callback_handler = state.get("callback_handler")
    
    if callback_handler:
        callback_handler.set_active_node(node_id)
    
    original_question = state.get("question", "")
    task_results = state.get("task_results", [])
    current_result = state.get("current_result", "")
    
    conversation_history = state.get("conversation_history", [])
    
    collected_data, errors = extract_task_data(task_results, current_result)
    
    if callback_handler:
        if current_result:
            queue_text("**Execution Results:**", node_id)
            queue_tool_result(current_result, node_id)
    
    browser_info = get_browser_info(state)
    prompt = generate_answer_prompt(original_question, collected_data, browser_info, errors)

    try:
        chat_model = ChatBedrockConverse(
            model=MODEL_CONFIG["decision_model"],
            region_name=MODEL_CONFIG["region"],
            temperature=MODEL_CONFIG["temperature"]["decision"]
        )
        
        messages = [
            SystemMessage(content="You are a helpful assistant providing clear answers based on web information."),
            HumanMessage(content=prompt)
        ]
        
        callbacks = [callback_handler] if callback_handler else None
        
        response = chat_model.invoke(
            messages,
            config={"callbacks": callbacks, "streaming": True}
        )
        
        answer = response.content
        
        sources_text = format_source_urls(collected_data)
        if sources_text:
            answer = f"{answer}\n\n{sources_text}"
        
        conversation_history.append({
            "role": "assistant",
            "content": answer
        })

    except Exception as e:
        logger.exception(f"Error generating answer: {e}")
        answer = f"I encountered an issue while processing your request: {str(e)}"

        conversation_history.append({
            "role": "assistant",
            "content": answer
        })

    return {
        "answer": answer, 
        "complete": True,
        "conversation_history": conversation_history 
    }

def format_source_urls(collected_data: List[Dict[str, Any]]) -> str:
    """Format source URLs for displaying in the answer"""
    urls = []
    seen_urls = set()  # To avoid duplicates
    
    for item in collected_data:
        url = item.get("url", "")
        title = item.get("title", "")
        source = item.get("source", "")
        
        if url and url not in seen_urls:
            seen_urls.add(url)
            display_text = title if title else url
            if source and source != title:
                urls.append(f"- [{source}] {display_text}: {url}")
            else:
                urls.append(f"- {display_text}: {url}")
    
    if urls:
        return "**Sources:**\n" + "\n".join(urls)
    return ""


def extract_task_data(task_results: List[Dict[str, Any]], current_result: str) -> tuple:
    collected_data = []
    errors = []
    
    if task_results:
        for result_item in task_results:
            # Check if this is a structured result
            is_structured = all(key in result_item for key in ["description", "result", "completed"])
            
            if is_structured:
                task_desc = result_item.get("description", "")
                task_result = result_item.get("result", "")
                error_msg = result_item.get("error")
                source_info = result_item.get("source", {})
                
                if error_msg:
                    errors.append(f"Error in task '{task_desc}': {error_msg}")
                
                if task_result:
                    data_item = {
                        "source": task_desc,
                        "raw_text": task_result,
                    }
                    
                    # Add source information if available
                    if source_info:
                        data_item["url"] = source_info.get("url", "")
                        data_item["title"] = source_info.get("title", "")
                    
                    collected_data.append(data_item)
            else:
                # Handle legacy format
                task_desc = result_item.get("description", "")
                task_result = result_item.get("result", "")
                error_msg = result_item.get("error")
                
                if error_msg:
                    errors.append(f"Error in task '{task_desc}': {error_msg}")
                
                if task_result:
                    collected_data.append({
                        "source": task_desc,
                        "raw_text": task_result
                    })
    
    elif current_result:
        collected_data.append({
            "source": "Task execution",
            "raw_text": current_result
        })
    
    return collected_data, errors

def process_task_result(result_item: Dict[str, Any], collected_data: List[Dict[str, Any]], errors: List[str]):
    """Process a single task result to extract structured data"""
    task_desc = result_item.get("description", "")
    task_result = result_item.get("result", "")
    error_msg = result_item.get("error")
    
    if error_msg:
        errors.append(f"Error in task '{task_desc}': {error_msg}")
    
    # Extract structured data
    try:
        # Find JSON in the result
        if task_result:
            extract_json_from_text(task_result, task_desc, collected_data)
        
        # Also add raw text results if no JSON found
        if not any(item["source"] == task_desc for item in collected_data) and task_result:
            collected_data.append({
                "source": task_desc,
                "raw_text": task_result
            })
            
    except Exception as e:
        logger.error(f"Error processing task result: {e}")

def extract_json_from_text(text: str, source: str, collected_data: List[Dict[str, Any]]):
    """Extract JSON objects from text"""
    json_start = text.find('{')
    while json_start >= 0:
        # Track brace depth to find matching closing brace
        brace_count = 1
        json_end = json_start + 1
        while json_end < len(text) and brace_count > 0:
            if text[json_end] == '{':
                brace_count += 1
            elif text[json_end] == '}':
                brace_count -= 1
            json_end += 1
        
        if brace_count == 0:
            json_str = text[json_start:json_end]
            try:
                data = json.loads(json_str)
                if isinstance(data, dict):
                    # Check if data is in a nested structure
                    if "data" in data and isinstance(data["data"], dict):
                        collected_data.append({
                            "source": source,
                            "data": data["data"]
                        })
                    elif "status" in data and data.get("status") == "success":
                        # Check for other valuable data
                        valuable_data = {k: v for k, v in data.items() 
                                      if k not in ["status", "message"] and v}
                        if valuable_data:
                            collected_data.append({
                                "source": source,
                                "data": valuable_data
                            })
            except json.JSONDecodeError:
                logger.debug(f"Ignored error: {e}")
        
        # Look for next JSON object
        json_start = text.find('{', json_end)

def get_browser_info(state: Dict[str, Any]) -> Dict[str, Any]:
    browser_info = {}
    browser_controller = state.get("browser_controller")
    if browser_controller:
        try:
            browser_info = {
                "current_url": browser_controller.get_current_url(),
                "page_title": browser_controller.get_page_title()
            }
        except Exception:
            logger.debug(f"Ignored error: {e}")
    return browser_info

def generate_answer_prompt(question: str, collected_data: List[Dict[str, Any]], 
                          browser_info: Dict[str, Any], errors: List[str]) -> str:
    prompt = f"""
Original question: {question}

I've collected the following information:
"""
    
    for item in collected_data:
        source = item['source']
        content = item.get('raw_text', '')
        url = item.get('url', '')
        title = item.get('title', '')
        
        prompt += f"\n\nFrom {source}:"
        if url and title:
            prompt += f" (URL: {url}, Title: {title})"
        prompt += f"\n{content}"
    
    if browser_info:
        prompt += f"\n\nFinal browser state:\n"
        prompt += f"URL: {browser_info.get('current_url', 'N/A')}\n"
        prompt += f"Title: {browser_info.get('page_title', 'N/A')}\n"
    
    if errors:
        prompt += f"\nErrors encountered:\n"
        for error in errors:
            prompt += f"- {error}\n"
    
    prompt += """
Based on this information, please provide a comprehensive answer to the original question.
If the information is insufficient, please mention what's missing. If there were errors, acknowledge them briefly.
Focus on directly answering the question with the available information. Don't use Markdown Formatting.
"""
    return prompt