"""
LangGraph Agent Workflow Assembly for CodeMate.
Coordinates cognitive nodes into an iterative, cyclic directed state machine:
classify_intent -> reason <-> execute_tools -> generate_response -> END
"""

import uuid
import time
import logging
from typing import Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from app.agents.state import AgentState
from app.agents.nodes import (
    classify_intent_node,
    reasoning_node,
    execute_tools_node,
    generate_response_node,
    should_continue
)
from app.services.repo_service import get_active_repository_id
from app.services.workflow_service import (
    start_workflow_trace,
    complete_workflow_trace
)

logger = logging.getLogger(__name__)


def build_agent_graph():
    """Builds and compiles the cyclic CodeMate LangGraph state machine."""
    workflow = StateGraph(AgentState)

    # 1. Register workflow nodes
    workflow.add_node("classify_intent", classify_intent_node)
    workflow.add_node("reason", reasoning_node)
    workflow.add_node("execute_tools", execute_tools_node)
    workflow.add_node("generate_response", generate_response_node)

    # 2. Wire edges and conditional loops
    workflow.add_edge(START, "classify_intent")
    workflow.add_edge("classify_intent", "reason")

    # Conditional decision from reasoning
    workflow.add_conditional_edges(
        "reason",
        should_continue,
        {
            "execute_tools": "execute_tools",
            "generate_response": "generate_response"
        }
    )

    # Loop back from tool execution to reasoning for inspection
    workflow.add_edge("execute_tools", "reason")

    # Final response terminates graph
    workflow.add_edge("generate_response", END)

    # 3. Compile runnable
    return workflow.compile()


# Compiled singleton graph
agent_executor = build_agent_graph()


def run_agent(
    query: str,
    repository_id: Optional[str] = None,
    user_id: str = "usr_demo",
    request_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executes the full agent graph on a user question.

    Returns:
        Dict containing request_id, repository_id, answer, intent, confidence, sources,
        tools_used, duration_ms, and workflow trace.
    """
    req_id = request_id or f"req_{uuid.uuid4().hex[:12]}"
    repo_id = repository_id or get_active_repository_id()

    start_time = time.time()
    start_workflow_trace(req_id, repo_id, user_id, query)

    initial_state: AgentState = {
        "request_id": req_id,
        "repository_id": repo_id,
        "user_id": user_id,
        "query": query,
        "iteration": 0,
        "max_iterations": 4,
        "is_finished": False,
        "tools_to_run": [],
        "tool_calls": [],
        "tools_used": [],
        "retrieved_context": [],
        "sources": []
    }

    try:
        result = agent_executor.invoke(initial_state)
    except Exception as err:
        logger.error("Error executing agent graph: %s", err, exc_info=True)
        duration_ms = int((time.time() - start_time) * 1000)
        error_msg = f"Agent encountered an internal error: {str(err)}"
        complete_workflow_trace(req_id, "GENERAL_QUERY", error_msg, [], [], duration_ms)
        return {
            "request_id": req_id,
            "repository_id": repo_id,
            "answer": error_msg,
            "intent": "GENERAL_QUERY",
            "confidence": 0.5,
            "sources": [],
            "tools_used": [],
            "tool_calls": [],
            "duration_ms": duration_ms
        }

    duration_ms = int((time.time() - start_time) * 1000)
    answer = result.get("response", "")
    intent = result.get("intent", "GENERAL_QUERY")
    confidence = result.get("confidence", 1.0)
    sources = result.get("sources", [])
    tools_used = result.get("tools_used", [])
    tool_calls = result.get("tool_calls", [])

    complete_workflow_trace(req_id, intent, answer, sources, tools_used, duration_ms)

    return {
        "request_id": req_id,
        "repository_id": repo_id,
        "answer": answer,
        "intent": intent,
        "confidence": confidence,
        "sources": sources,
        "tools_used": tools_used,
        "tool_calls": tool_calls,
        "duration_ms": duration_ms
    }
