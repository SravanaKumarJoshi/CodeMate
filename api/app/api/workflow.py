"""
Workflow API for CodeMate.
Exposes runtime execution timelines for individual chat queries
and architecture specifications for the interactive /workflow page.
"""

from fastapi import APIRouter, HTTPException, status
from app.services.workflow_service import get_workflow_trace

router = APIRouter(prefix="/workflow", tags=["Workflow"])

ARCHITECTURE_NODES = {
    "user": {
        "title": "User",
        "description": "Developer posing natural-language inquiries about repository architecture, bugs, authentication, or dependencies.",
        "input": "Natural language query",
        "output": "HTTP Request"
    },
    "frontend": {
        "title": "Frontend UI",
        "description": "Interactive developer interface with repository explorer, syntax-highlighted code viewer, chat stream, and live workflow visualization.",
        "tech": "HTML5, Vanilla CSS, Modern JavaScript",
        "endpoints": ["POST /api/chat", "GET /api/workflow/{id}", "POST /api/repositories/upload"]
    },
    "fastapi": {
        "title": "FastAPI Gateway",
        "description": "High-performance REST API with asynchronous endpoints, Pydantic validation, CORS protection, and background task dispatch.",
        "tech": "FastAPI + Uvicorn (ASGI)",
        "security": "JWT bearer auth, path traversal sanitization, archive bomb defense"
    },
    "intent_classifier": {
        "title": "Intent Classifier (ML)",
        "description": "Traditional ML classifier acting as an initial routing signal for query intention.",
        "tech": "scikit-learn (TF-IDF Vectorizer + Logistic Regression)",
        "classes": ["CODE_SEARCH", "CODE_EXPLANATION", "BUG_ANALYSIS", "TEST_GENERATION", "ARCHITECTURE", "GENERAL_QUERY"],
        "role": "Routing signal only — never restricts open-ended developer inquiries"
    },
    "langgraph_agent": {
        "title": "LangGraph Agent Machine",
        "description": "Cyclic state machine coordinating multi-step cognitive cycles: reason -> tool decision -> tool execution -> inspection -> response generation.",
        "tech": "LangGraph StateGraph",
        "guardrails": ["MAX_AGENT_ITERATIONS=4", "MAX_TOOL_CALLS=6", "MAX_RETRIEVED_CHUNKS=8"]
    },
    "tools": {
        "title": "Agent Tool Suite",
        "description": "Narrow, strictly validated tools for codebase inspection.",
        "available_tools": [
            {"name": "search_code", "role": "Vector semantic search in ChromaDB"},
            {"name": "read_file", "role": "Path-safe file content reading with line numbers"},
            {"name": "list_project_files", "role": "Directory file tree inspection"},
            {"name": "search_symbols", "role": "AST class/function symbol lookup"},
            {"name": "retrieve_context", "role": "Multi-query RAG retrieval"},
            {"name": "generate_unit_test", "role": "pytest/unittest scaffolding generator"}
        ],
        "security": "Strictly no arbitrary shell/command execution"
    },
    "rag_chromadb": {
        "title": "RAG & ChromaDB",
        "description": "High-performance vector database indexing AST code chunks with repository isolation.",
        "tech": "ChromaDB (Persistent HNSW Cosine Index)",
        "embeddings": "Deterministic normalized 384-dim dense vectors / OpenAI text-embedding-3-small",
        "isolation": "where={'repository_id': repo_id}"
    },
    "llm_synthesis": {
        "title": "LLM Response Synthesizer",
        "description": "Produces grounded technical responses with source citations, protected against prompt injection.",
        "engine": "OpenAI GPT-4o-mini / Local Grounded Deterministic Synthesizer",
        "grounding": "Mandatory file path and line citations; honest fallback when evidence is absent"
    }
}


@router.get("/architecture")
def get_architecture():
    """Returns technical component details for interactive workflow node inspection."""
    return ARCHITECTURE_NODES


@router.get("/{request_id}")
def get_request_workflow(request_id: str):
    """
    Returns the live step-by-step execution timeline for a specific chat request.
    Powers the real-time request visualizer on the /workflow page.
    """
    trace = get_workflow_trace(request_id)
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow trace for request '{request_id}' not found."
        )
    return trace
