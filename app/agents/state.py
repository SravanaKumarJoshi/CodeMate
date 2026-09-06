"""
LangGraph Agent State Definition for CodeMate.
Tracks the complete cognitive cycle: intent classification, reasoning, tool execution,
intermediate observations, source tracking, and grounded synthesis.
"""

from typing import TypedDict, List, Dict, Any, Optional


class AgentState(TypedDict, total=False):
    # Identifiers
    request_id: str
    repository_id: str
    user_id: str

    # User input
    query: str

    # Routing signal from scikit-learn intent classifier
    intent: str
    confidence: float

    # Agent reasoning and iteration control
    iteration: int
    max_iterations: int
    is_finished: bool
    reasoning_notes: List[str]

    # Tool invocation decisions and audit trail
    tools_to_run: List[Dict[str, Any]]
    tool_calls: List[Dict[str, Any]]
    tools_used: List[str]

    # Retrieved code context and citations
    retrieved_context: List[Dict[str, Any]]
    sources: List[Dict[str, Any]]  # [{"file": "auth.py", "start_line": 20, "end_line": 57}]

    # Final synthesized answer
    response: str
    error: Optional[str]
