"""
Files API for CodeMate.
Provides repository file tree enumeration and secure file content retrieval.
"""

from typing import Optional
from fastapi import APIRouter, Query, HTTPException, status
from app.tools.file_lister import list_project_files
from app.tools.file_reader import read_file
from app.rag.retriever import get_indexed_files

router = APIRouter(tags=["Files"])


@router.get("/files")
def get_files(repository_id: Optional[str] = Query(None, description="Optional target repository ID")):
    """Return all indexed files in the active codebase with line counts and file sizes."""
    files = list_project_files(repository_id=repository_id)
    indexed = get_indexed_files(repository_id=repository_id)
    return {
        "repository_id": repository_id or "active",
        "total_files": len(files),
        "files": files,
        "indexed_in_vectordb": indexed
    }


@router.get("/files/content")
def get_file_content(
    file_path: str = Query(..., description="Relative path to file in project"),
    start_line: Optional[int] = Query(None, description="1-based start line"),
    end_line: Optional[int] = Query(None, description="1-based end line"),
    repository_id: Optional[str] = Query(None, description="Optional target repository ID")
):
    """Securely fetch the full or partial content of a project file for viewing."""
    result = read_file(file_path, start_line=start_line, end_line=end_line, repository_id=repository_id)
    if result.get("status") != "success":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Failed to read file")
        )
    return result
