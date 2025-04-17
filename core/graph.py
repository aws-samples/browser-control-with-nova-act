"""
LangGraph workflows and node implementations for browser automation

This module provides the graph nodes and workflow definitions for the LangGraph-based
browser automation system.
"""

import logging
from typing import Dict, Any, Callable

from langgraph.graph import StateGraph, START, END

# Import type definitions
from .types import ProcessingType, BrowserWorkflowState

# Import node implementations from their respective modules
from .nodes import (
    chat_node,
    plan_node,
    executor_node,
    answer_gen_node
)

# Configure logging
logger = logging.getLogger("nova_graph")

def create_browser_workflow() -> Callable:
    """Create the workflow graph with streamlined structure"""
    workflow = StateGraph(BrowserWorkflowState)
    logger.debug("Created LangGraph StateGraph")
    
    # Add nodes
    workflow.add_node("chat", chat_node)
    workflow.add_node("plan", plan_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("answer_gen", answer_gen_node)
    
    # Connect nodes conditionally
    workflow.add_conditional_edges(
        "chat",
        lambda state: "plan" if state.get("processing_type") == ProcessingType.BROWSER_TASK.name else END
    )
    
    # Connect remaining workflow
    workflow.add_edge("plan", "executor")
    
    workflow.add_conditional_edges(
        "executor",
        lambda state: "answer_gen" if state.get("complete", False) else "executor"
    )
    
    workflow.add_edge("answer_gen", END)
    
    # Set entry point
    workflow.set_entry_point("chat")
    
    return workflow.compile()