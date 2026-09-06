"""
Context Retrieval Tool for CodeMate.
Performs repository-aware RAG vector search across code and documentation.
"""

from typing import List, Dict, Any, Optional
from app.rag.retriever import query_code
from app.services.repo_service import get_active_repository_id


def retrieve_context(
    query: str,
    repository_id: Optional[str] = None,
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Retrieves semantic context chunks from ChromaDB for a given question or concept.
    Strictly filters results by repository_id to prevent cross-repo leakage.
    """
    if not query or not query.strip():
        return []

    repo_id = repository_id or get_active_repository_id()
    return query_code(query.strip(), repository_id=repo_id, top_k=top_k)
