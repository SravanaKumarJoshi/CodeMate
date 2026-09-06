"""
Health & Diagnostic Endpoint for CodeMate.
Reports service status, ChromaDB vector metrics, ML classifier readiness,
and active LLM operational mode (Online vs Offline Demo).
"""

from fastapi import APIRouter
from app.config import settings
from app.rag.retriever import get_collection
from app.ml.model_loader import is_model_loaded
from app.services.llm_service import is_online_mode
from app.services.repo_service import get_active_repository_id

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    """Returns application health and operational parameters."""
    chroma_count = 0
    try:
        coll = get_collection()
        chroma_count = coll.count()
    except Exception:
        pass

    llm_mode = "online" if is_online_mode() else "offline_demo"

    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "environment": settings.APP_ENV,
        "ml_model": {
            "status": "ready" if is_model_loaded() else "not_found",
            "type": "TF-IDF + LogisticRegression"
        },
        "ml_model_loaded": is_model_loaded(),
        "vectordb": {
            "status": "connected",
            "indexed_chunks": chroma_count,
            "collection": settings.CHROMA_COLLECTION_NAME
        },
        "vector_db": {
            "status": "connected",
            "indexed_chunks": chroma_count,
            "collection": settings.CHROMA_COLLECTION_NAME
        },
        "llm_mode": llm_mode,
        "active_repository_id": get_active_repository_id(),
        "max_upload_size_mb": settings.MAX_UPLOAD_SIZE_MB
    }
