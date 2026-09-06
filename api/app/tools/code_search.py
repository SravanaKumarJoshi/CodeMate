"""
Code Search Tool for CodeMate.
Retrieves relevant code chunks from ChromaDB using semantic similarity search
and repository-aware filtering.
"""

from typing import List, Dict, Any, Optional
from app.rag.retriever import query_code
from app.services.repo_service import get_active_repository_id


def search_code(
    query: str,
    repository_id: Optional[str] = None,
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Search the indexed codebase for snippets and symbols matching the given query.

    Args:
        query: Natural language question or code identifier to search for.
        repository_id: Optional repository ID; defaults to currently active repo.
        top_k: Number of most relevant code chunks to return.

    Returns:
        List of dictionaries with file_path, start_line, end_line, similarity, symbol, and content.
    """
    if not query or not query.strip():
        return []

    repo_id = repository_id or get_active_repository_id()
    return query_code(query.strip(), repository_id=repo_id, top_k=top_k)
