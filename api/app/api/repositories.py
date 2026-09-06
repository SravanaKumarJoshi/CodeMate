"""
Repositories API for CodeMate.
Handles streaming uploads of large repository ZIPs (up to 2GB),
background incremental indexing, progress polling, and multi-repo isolation.
"""

import os
import uuid
import shutil
import logging
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.orm import Session
from app.config import settings
from app.services.database import get_db, SessionLocal
from app.security.auth import get_current_user
from app.security.archive_security import validate_and_extract_zip, ArchiveSecurityError
from app.security.path_security import sanitize_filename
from app.rag.ingestion import index_codebase_incrementally
from app.rag.retriever import delete_repository_chunks
from app.services.repo_service import (
    create_repository,
    get_repository,
    list_user_repositories,
    set_active_repository_id,
    get_active_repository_id,
    mark_repository_failed
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repositories", tags=["Repositories"])


def _background_index_job(
    zip_path: Optional[Path],
    extract_target: Path,
    repo_id: str,
    repo_name: str,
    is_sample: bool = False
):
    """Worker function executed asynchronously in background."""
    try:
        if is_sample:
            extracted_dir = settings.SAMPLE_PROJECT_DIR
            archive_stats = {}
        else:
            if not zip_path or not zip_path.exists():
                raise ArchiveSecurityError(f"Temporary archive not found: {zip_path}")
            extract_result = validate_and_extract_zip(zip_path, extract_target)
            extracted_dir = extract_result.root
            archive_stats = getattr(extract_result, "stats", {})

        # Incrementally parse, chunk, and embed
        index_codebase_incrementally(
            source_dir=extracted_dir,
            repository_id=repo_id,
            repository_name=repo_name,
            archive_stats=archive_stats
        )

    except Exception as err:
        logger.error("Background indexing job failed for %s: %s", repo_id, err, exc_info=True)
        mark_repository_failed(repo_id, str(err))
    finally:
        # Clean up temporary archive file
        if zip_path and zip_path.exists():
            try:
                zip_path.unlink()
            except Exception:
                pass


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_repository(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    use_sample: bool = Form(False),
    repository_name: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Stream and index a software repository.
    Accepts up to 2 GB archives without buffering the entire file into RAM.
    Returns immediately with repository_id and 'indexing' status.
    """
    user_id = current_user.get("id", "usr_demo")

    # Option A: Load bundled sample project
    if use_sample or (file is None and settings.SAMPLE_PROJECT_DIR.exists()):
        repo_id = "repo_sample_project"
        name = "Sample E-Commerce Store"

        existing = get_repository(db, repo_id)
        if not existing:
            create_repository(
                db=db,
                repo_id=repo_id,
                name=name,
                owner_id=user_id,
                root_path=str(settings.SAMPLE_PROJECT_DIR),
                is_sample=True
            )

        background_tasks.add_task(
            _background_index_job,
            zip_path=None,
            extract_target=settings.SAMPLE_PROJECT_DIR,
            repo_id=repo_id,
            repo_name=name,
            is_sample=True
        )

        set_active_repository_id(repo_id)
        return {
            "repository_id": repo_id,
            "repository_name": name,
            "status": "indexing"
        }

    # Option B: Streaming large file upload
    if file is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a .zip file or set use_sample=true."
        )

    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported archive format. Only .zip files are accepted."
        )

    repo_id = f"repo_{uuid.uuid4().hex[:10]}"
    clean_name = repository_name or sanitize_filename(Path(file.filename).stem)
    extract_target = settings.UPLOAD_DIR / repo_id
    temp_zip = settings.DATA_DIR / f"{repo_id}_upload.zip"

    # Stream upload in 64 KB chunks directly to disk
    total_bytes_streamed = 0
    try:
        with open(temp_zip, "wb") as buffer:
            while chunk := await file.read(settings.UPLOAD_CHUNK_SIZE_KB * 1024):
                total_bytes_streamed += len(chunk)
                if total_bytes_streamed > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Archive exceeds maximum size limit ({settings.MAX_UPLOAD_SIZE_MB} MB)."
                    )
                buffer.write(chunk)
    except HTTPException:
        if temp_zip.exists():
            temp_zip.unlink()
        raise
    except Exception as err:
        if temp_zip.exists():
            temp_zip.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stream upload: {str(err)}"
        )

    # Register in DB with indexing status
    create_repository(
        db=db,
        repo_id=repo_id,
        name=clean_name,
        owner_id=user_id,
        root_path=str(extract_target),
        is_sample=False,
        size_bytes=total_bytes_streamed
    )

    # Launch background indexing job
    background_tasks.add_task(
        _background_index_job,
        zip_path=temp_zip,
        extract_target=extract_target,
        repo_id=repo_id,
        repo_name=clean_name,
        is_sample=False
    )

    set_active_repository_id(repo_id)

    return {
        "repository_id": repo_id,
        "repository_name": clean_name,
        "status": "indexing"
    }


@router.get("/{repository_id}/status")
def get_indexing_status(
    repository_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Poll indexing status and progress for a repository.
    Returns files_processed, files_indexed, files_discovered, files_skipped, skip_reasons, chunks_created, progress %, and status.
    """
    repo = get_repository(db, repository_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{repository_id}' not found."
        )

    skip_reasons = {}
    if getattr(repo, "skip_reasons", None):
        try:
            import json
            skip_reasons = json.loads(repo.skip_reasons)
        except Exception:
            skip_reasons = {}

    discovered = getattr(repo, "files_discovered", repo.total_files) or repo.total_files
    skipped = getattr(repo, "files_skipped", 0) or 0

    return {
        "repository_id": repo.id,
        "repository_name": repo.name,
        "status": repo.status,
        "files_processed": repo.processed_files,
        "files_indexed": repo.processed_files,
        "files_discovered": discovered,
        "files_skipped": skipped,
        "skip_reasons": skip_reasons,
        "total_files": repo.total_files,
        "chunks_created": repo.total_chunks,
        "progress": repo.indexing_progress,
        "error_message": repo.error_message
    }


@router.get("")
def list_repositories(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all repositories available to the authenticated user."""
    user_id = current_user.get("id", "usr_demo")
    repos = list_user_repositories(db, user_id)
    active_id = get_active_repository_id()

    return {
        "active_repository_id": active_id,
        "repositories": [
            {
                "id": r.id,
                "name": r.name,
                "status": r.status,
                "total_files": r.total_files,
                "files_indexed": r.processed_files,
                "files_discovered": getattr(r, "files_discovered", r.total_files) or r.total_files,
                "files_skipped": getattr(r, "files_skipped", 0) or 0,
                "total_chunks": r.total_chunks,
                "progress": r.indexing_progress,
                "is_sample": r.is_sample,
                "size_bytes": r.size_bytes,
                "is_active": r.id == active_id
            }
            for r in repos
        ]
    }


@router.post("/{repository_id}/activate")
def activate_repository(
    repository_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Sets the active repository for queries."""
    repo = get_repository(db, repository_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{repository_id}' not found."
        )

    set_active_repository_id(repo.id)
    return {"message": f"Switched active repository to '{repo.name}'", "repository_id": repo.id}


@router.delete("/{repository_id}")
def delete_repository(
    repository_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deletes a repository and cleans up its files and vector embeddings."""
    repo = get_repository(db, repository_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{repository_id}' not found."
        )

    user_id = current_user.get("id", "usr_demo")
    if repo.owner_id != user_id and not current_user.get("is_demo"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this repository."
        )

    # 1. Clean ChromaDB chunks
    delete_repository_chunks(repo.id)

    # 2. Clean extracted files if not sample project
    if not repo.is_sample and Path(repo.root_path).exists():
        shutil.rmtree(repo.root_path, ignore_errors=True)

    # 3. Remove from DB
    db.delete(repo)
    db.commit()

    return {"message": f"Repository '{repo.name}' deleted successfully."}
