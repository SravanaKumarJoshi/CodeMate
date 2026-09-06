"""
Repository Service for CodeMate.
Handles repository metadata, ownership validation, active repository selection,
and thread-safe progress updates during large indexing jobs.
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.db_models import RepositoryModel
from app.services.database import SessionLocal

logger = logging.getLogger(__name__)

# In-memory tracking of currently active repository per session
_ACTIVE_REPOSITORY_ID: str = "repo_sample_project"


def get_active_repository_id() -> str:
    global _ACTIVE_REPOSITORY_ID
    return _ACTIVE_REPOSITORY_ID


def set_active_repository_id(repo_id: str):
    global _ACTIVE_REPOSITORY_ID
    _ACTIVE_REPOSITORY_ID = repo_id


def create_repository(
    db: Session,
    repo_id: str,
    name: str,
    owner_id: str,
    root_path: str,
    is_sample: bool = False,
    size_bytes: int = 0
) -> RepositoryModel:
    repo = RepositoryModel(
        id=repo_id,
        name=name,
        owner_id=owner_id,
        status="indexing",
        total_files=0,
        processed_files=0,
        files_discovered=0,
        files_skipped=0,
        skip_reasons="{}",
        total_chunks=0,
        indexing_progress=0,
        languages_detected="[]",
        size_bytes=size_bytes,
        root_path=root_path,
        is_sample=is_sample
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


def get_repository(db: Session, repo_id: str) -> Optional[RepositoryModel]:
    return db.query(RepositoryModel).filter(RepositoryModel.id == repo_id).first()


def list_user_repositories(db: Session, user_id: str) -> List[RepositoryModel]:
    """Returns repositories owned by user plus any public sample repositories."""
    return db.query(RepositoryModel).filter(
        (RepositoryModel.owner_id == user_id) | (RepositoryModel.is_sample == True)
    ).order_by(RepositoryModel.created_at.desc()).all()


def update_repository_progress(
    repo_id: str,
    processed_files: int,
    total_files: int,
    total_chunks: int,
    progress: int,
    status: str = "indexing",
    error_message: Optional[str] = None,
    languages: Optional[List[str]] = None,
    files_discovered: Optional[int] = None,
    files_skipped: Optional[int] = None,
    skip_reasons: Optional[Dict[str, int]] = None
):
    """Thread-safe update called during background indexing steps."""
    with SessionLocal() as db:
        repo = db.query(RepositoryModel).filter(RepositoryModel.id == repo_id).first()
        if repo:
            repo.processed_files = processed_files
            repo.total_files = total_files
            if files_discovered is not None:
                repo.files_discovered = files_discovered
            elif repo.files_discovered == 0 and total_files > 0:
                repo.files_discovered = total_files
            if files_skipped is not None:
                repo.files_skipped = files_skipped
            if skip_reasons is not None:
                repo.skip_reasons = json.dumps(skip_reasons)
            repo.total_chunks = total_chunks
            repo.indexing_progress = max(0, min(100, progress))
            repo.status = status
            if error_message:
                repo.error_message = error_message
            if languages is not None:
                repo.languages_detected = json.dumps(languages)
            repo.updated_at = datetime.now(timezone.utc)
            db.commit()


def mark_repository_ready(
    repo_id: str,
    total_files: int,
    total_chunks: int,
    languages: List[str],
    files_discovered: Optional[int] = None,
    files_skipped: Optional[int] = None,
    skip_reasons: Optional[Dict[str, int]] = None
):
    update_repository_progress(
        repo_id=repo_id,
        processed_files=total_files,
        total_files=total_files,
        total_chunks=total_chunks,
        progress=100,
        status="ready",
        languages=languages,
        files_discovered=files_discovered,
        files_skipped=files_skipped,
        skip_reasons=skip_reasons
    )


def mark_repository_failed(repo_id: str, error_message: str):
    update_repository_progress(
        repo_id=repo_id,
        processed_files=0,
        total_files=0,
        total_chunks=0,
        progress=0,
        status="failed",
        error_message=error_message
    )


def verify_repository_access(db: Session, repo_id: str, user_id: str) -> RepositoryModel:
    """Enforces server-side repository authorization."""
    repo = get_repository(db, repo_id)
    if not repo:
        raise ValueError(f"Repository '{repo_id}' not found.")
    if repo.owner_id != user_id and not repo.is_sample:
        raise PermissionError(f"User '{user_id}' does not have permission to access repository '{repo_id}'.")
    return repo
