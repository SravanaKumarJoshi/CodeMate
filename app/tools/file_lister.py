"""
File Lister Tool for CodeMate.
Lists all accessible files and directories within the authorized repository root.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
from app.rag.ingestion import get_active_project_path
from app.config import settings
from app.services.database import SessionLocal
from app.services.repo_service import get_repository


def list_project_files(repository_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns a list of all source and documentation files in the repository,
    including file path, line count, and file size.
    """
    project_root = get_active_project_path()
    if repository_id:
        try:
            with SessionLocal() as db:
                repo = get_repository(db, repository_id)
                if repo and repo.root_path and Path(repo.root_path).exists():
                    project_root = Path(repo.root_path)
        except Exception:
            pass

    if not project_root.exists():
        return []

    files_list: List[Dict[str, Any]] = []

    for path in project_root.rglob("*"):
        if path.is_file():
            # Check ignored directories
            parts = set(path.relative_to(project_root).parts)
            if any(
                ignored in parts or any(p.startswith(".venv") or p.startswith("venv") for p in parts)
                for ignored in settings.IGNORED_DIRECTORIES
            ):
                continue
            if path.suffix.lower() not in settings.ALLOWED_EXTENSIONS:
                continue
            if path.suffix.lower() in settings.IGNORED_EXTENSIONS:
                continue
            if path.name == ".env":
                continue

            try:
                rel_path = path.relative_to(project_root).as_posix()
                content = path.read_text(encoding="utf-8", errors="replace")
                lines_count = len(content.splitlines())
                size_bytes = path.stat().st_size

                files_list.append({
                    "path": rel_path,
                    "name": path.name,
                    "extension": path.suffix.lower(),
                    "lines": lines_count,
                    "size_bytes": size_bytes
                })
            except Exception:
                continue

    return sorted(files_list, key=lambda x: x["path"])
