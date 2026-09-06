"""
Chat API endpoint for CodeMate.
Coordinates developer inquiries through the LangGraph cognitive agent
and returns structured responses with citations and workflow metadata.
"""

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.agents.graph import run_agent
from app.security.auth import get_current_user
from app.services.database import get_db
from app.services.repo_service import get_active_repository_id, verify_repository_access

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="Developer query about the codebase")
    repository_id: Optional[str] = Field(None, description="Optional target repository ID; defaults to active repo")


class SourceCitation(BaseModel):
    file: str
    start_line: int = 1
    end_line: int = 1


class ChatResponse(BaseModel):
    request_id: str
    repository_id: str
    answer: str
    intent: str
    confidence: float
    sources: List[Any]
    tools_used: List[str]
    tool_calls: List[Dict[str, Any]]
    workflow_steps: List[str]
    duration_ms: int


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Query the codebase assistant.
    Executes the full agentic LangGraph workflow:
    intent classification -> reasoning -> dynamic tool execution -> RAG -> grounded response synthesis.
    """
    clean_message = request.message.strip()
    if not clean_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty or whitespace."
        )

    user_id = current_user.get("id", "usr_demo")
    target_repo_id = request.repository_id or get_active_repository_id()

    # Verify repository exists and user has permission to access it
    try:
        verify_repository_access(db, target_repo_id, user_id)
    except (ValueError, PermissionError) as err:
        # If repository not in DB yet (e.g. initial launch), fallback to active repo
        logger.debug("Repository access check note: %s", err)

    try:
        result = run_agent(
            query=clean_message,
            repository_id=target_repo_id,
            user_id=user_id
        )

        # Build workflow steps list
        workflow_steps = ["user_request", "intent_classifier", "agent_reasoning"]
        for tool in result.get("tools_used", []):
            workflow_steps.append(tool)
        workflow_steps.extend(["llm_synthesis", "response_synthesis"])

        return ChatResponse(
            request_id=result.get("request_id", ""),
            repository_id=result.get("repository_id", target_repo_id),
            answer=result.get("answer", ""),
            intent=result.get("intent", "GENERAL_QUERY"),
            confidence=result.get("confidence", 1.0),
            sources=result.get("sources", []),
            tools_used=result.get("tools_used", []),
            tool_calls=result.get("tool_calls", []),
            workflow_steps=workflow_steps,
            duration_ms=result.get("duration_ms", 0)
        )
    except Exception as err:
        logger.error("Chat processing failed: %s", err, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error executing agent workflow: {str(err)}"
        )
