"""
Symbol Search Tool for CodeMate.
Searches for classes, functions, methods, endpoints, and definitions across the codebase.
"""

from typing import List, Dict, Any, Optional
from app.rag.retriever import query_symbols
from app.services.repo_service import get_active_repository_id


def search_symbols(
    symbol_name: str,
    repository_id: Optional[str] = None,
    limit: int = 6
) -> List[Dict[str, Any]]:
    """
    Locates code definitions (functions, classes, models, routes) matching the given symbol.

    Args:
        symbol_name: The identifier, function name, class name, or method name.
        repository_id: Target repository ID.
        limit: Max results to return.

    Returns:
        List of matching code chunks with file paths, line ranges, and symbols.
    """
    if not symbol_name or not symbol_name.strip():
        return []

    repo_id = repository_id or get_active_repository_id()
    return query_symbols(symbol_name.strip(), repository_id=repo_id, limit=limit)
