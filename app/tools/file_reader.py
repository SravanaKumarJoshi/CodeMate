"""
File Reader Tool for CodeMate.
Securely reads contents of a file within the authorized repository root,
with strict path traversal protection and line range slicing.
"""

from pathlib import Path
from typing import Optional, Dict, Any
from app.rag.ingestion import get_active_project_path
from app.security.path_security import is_safe_path, resolve_safe_path
from app.services.database import SessionLocal
from app.services.repo_service import get_repository


def read_file(
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    repository_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Safely read contents of a file inside the authorized repository codebase.

    Args:
        file_path: Relative path to the file within the repository.
        start_line: Optional 1-based start line.
        end_line: Optional 1-based end line.
        repository_id: Target repository ID.

    Returns:
        Dict with status, file_path, content, lines, and total_lines.
    """
    # Determine base directory
    project_root = get_active_project_path()
    if repository_id:
        try:
            with SessionLocal() as db:
                repo = get_repository(db, repository_id)
                if repo and repo.root_path and Path(repo.root_path).exists():
                    project_root = Path(repo.root_path)
        except Exception:
            pass

    try:
        target_path = resolve_safe_path(project_root, file_path)
    except ValueError as val_err:
        return {
            "status": "error",
            "error": f"Access denied: Path traversal attempt or path outside project workspace. ({str(val_err)})",
            "file_path": file_path,
            "content": ""
        }

    if not target_path.exists() or not target_path.is_file():
        return {
            "status": "error",
            "error": f"File not found: {file_path}",
            "file_path": file_path,
            "content": ""
        }

    try:
        raw_text = target_path.read_text(encoding="utf-8", errors="replace")
        lines = raw_text.splitlines()
        total_lines = len(lines)

        s_idx = max(1, start_line) if start_line is not None else 1
        e_idx = min(total_lines, end_line) if end_line is not None else total_lines

        selected_lines = lines[s_idx - 1:e_idx]
        sliced_content = "\n".join(selected_lines)

        return {
            "status": "success",
            "file_path": file_path,
            "content": sliced_content,
            "start_line": s_idx,
            "end_line": e_idx,
            "total_lines": total_lines
        }
    except Exception as err:
        return {
            "status": "error",
            "error": f"Failed to read file: {str(err)}",
            "file_path": file_path,
            "content": ""
        }
