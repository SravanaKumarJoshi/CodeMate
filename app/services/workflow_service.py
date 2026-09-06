"""
Workflow Service for CodeMate.
Records request lifecycle execution timelines, tool actions, and step statuses.
Powers the live visualization on the /workflow page.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.models.db_models import WorkflowEventModel
from app.services.database import SessionLocal

logger = logging.getLogger(__name__)

# In-memory recent cache for instant polling during live queries
_RECENT_WORKFLOWS: Dict[str, Dict[str, Any]] = {}


def start_workflow_trace(request_id: str, repository_id: str, user_id: str, query: str) -> Dict[str, Any]:
    """Initializes a workflow trace record."""
    trace = {
        "request_id": request_id,
        "repository_id": repository_id,
        "user_id": user_id,
        "query": query,
        "intent": "PENDING",
        "status": "running",
        "start_time": datetime.now(timezone.utc).isoformat(),
        "steps": [
            {
                "name": "user_request",
                "status": "completed",
                "detail": "Received HTTP POST /api/chat",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ],
        "tools_used": [],
        "sources": []
    }
    _RECENT_WORKFLOWS[request_id] = trace
    return trace


def add_workflow_step(
    request_id: str,
    step_name: str,
    status: str = "completed",
    detail: str = "",
    data: Optional[Dict[str, Any]] = None
):
    """Appends an execution step to the active trace."""
    trace = _RECENT_WORKFLOWS.get(request_id)
    if not trace:
        return

    step = {
        "name": step_name,
        "status": status,
        "detail": detail,
        "data": data or {},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    trace["steps"].append(step)


def complete_workflow_trace(
    request_id: str,
    intent: str,
    answer: str,
    sources: List[Any],
    tools_used: List[str],
    duration_ms: int
):
    """Finalizes trace and commits to database for persistent retrieval."""
    trace = _RECENT_WORKFLOWS.get(request_id)
    if not trace:
        return

    trace["intent"] = intent
    trace["status"] = "completed"
    trace["answer"] = answer
    trace["sources"] = sources
    trace["tools_used"] = tools_used
    trace["duration_ms"] = duration_ms
    trace["end_time"] = datetime.now(timezone.utc).isoformat()

    add_workflow_step(request_id, "response_synthesis", status="completed", detail="Formatted grounded response")
    add_workflow_step(request_id, "http_response", status="completed", detail=f"Returned 200 OK ({duration_ms}ms)")

    # Save to database
    try:
        with SessionLocal() as db:
            event = WorkflowEventModel(
                request_id=request_id,
                repository_id=trace["repository_id"],
                user_id=trace["user_id"],
                query=trace["query"],
                intent=intent,
                duration_ms=duration_ms,
                steps_json=json.dumps(trace["steps"]),
                tools_used=json.dumps(tools_used),
                sources_json=json.dumps(sources)
            )
            db.add(event)
            db.commit()
    except Exception as err:
        logger.warning("Could not persist workflow event: %s", err)


def get_workflow_trace(request_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves workflow trace from cache or database."""
    if request_id in _RECENT_WORKFLOWS:
        return _RECENT_WORKFLOWS[request_id]

    with SessionLocal() as db:
        event = db.query(WorkflowEventModel).filter(WorkflowEventModel.request_id == request_id).first()
        if event:
            return {
                "request_id": event.request_id,
                "repository_id": event.repository_id,
                "user_id": event.user_id,
                "query": event.query,
                "intent": event.intent,
                "status": "completed",
                "duration_ms": event.duration_ms,
                "steps": json.loads(event.steps_json or "[]"),
                "tools_used": json.loads(event.tools_used or "[]"),
                "sources": json.loads(event.sources_json or "[]"),
                "created_at": event.created_at.isoformat() if event.created_at else None
            }
    return None
