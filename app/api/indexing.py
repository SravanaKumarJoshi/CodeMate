"""
Indexing API router for CodeMate.
Maintains backward compatibility with /api/index while delegating to the
scalable repository ingestion pipeline.
"""

import uuid
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, status
from sqlalchemy.orm import Session
from app.config import settings
from app.services.database import get_db
from app.security.auth import get_current_user
from app.security.archive_security import validate_and_extract_zip, ArchiveSecurityError
from app.rag.ingestion import index_codebase_incrementally
from app.services.repo_service import create_repository, set_active_repository_id, get_repository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Indexing"])


@router.post("/index")
async def index_project(
    file: Optional[UploadFile] = File(None),
    use_sample: bool = Form(False),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Ingest and index a codebase synchronously.
    Accepts either an uploaded ZIP archive or a flag to index the bundled sample_project.
    """
    user_id = current_user.get("id", "usr_demo")

    # Option A: Index bundled sample project
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

        result = index_codebase_incrementally(
            source_dir=settings.SAMPLE_PROJECT_DIR,
            repository_id=repo_id,
            repository_name=name
        )

        set_active_repository_id(repo_id)
        return {
            "message": "Sample project indexed successfully into ChromaDB.",
            "data": result
        }

    # Option B: Uploaded ZIP file
    if file is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either upload a project ZIP file or set use_sample=true."
        )

    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Please upload a .zip archive."
        )

    repo_id = f"repo_{uuid.uuid4().hex[:10]}"
    target_extract_dir = settings.UPLOAD_DIR / repo_id
    temp_zip_path = settings.DATA_DIR / f"{repo_id}_upload.zip"

    try:
        # Stream file to disk in 64 KB chunks
        total_streamed = 0
        with open(temp_zip_path, "wb") as buffer:
            while chunk := await file.read(settings.UPLOAD_CHUNK_SIZE_KB * 1024):
                total_streamed += len(chunk)
                if total_streamed > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Archive exceeds maximum size limit ({settings.MAX_UPLOAD_SIZE_MB} MB)."
                    )
                buffer.write(chunk)

        extract_result = validate_and_extract_zip(temp_zip_path, target_extract_dir)
        extracted_dir = extract_result.root
        archive_stats = getattr(extract_result, "stats", {})

        create_repository(
            db=db,
            repo_id=repo_id,
            name=Path(file.filename).stem,
            owner_id=user_id,
            root_path=str(extracted_dir),
            is_sample=False,
            size_bytes=total_streamed
        )

        result = index_codebase_incrementally(
            source_dir=extracted_dir,
            repository_id=repo_id,
            repository_name=Path(file.filename).stem,
            archive_stats=archive_stats
        )

        set_active_repository_id(repo_id)

        return {
            "message": f"Successfully extracted and indexed '{file.filename}'.",
            "data": result
        }
    except ArchiveSecurityError as sec_err:
        logger.error("ZIP security rejection: %s", sec_err)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(sec_err)
        )
    except HTTPException:
        raise
    except Exception as err:
        logger.error("Ingestion failure: %s", err, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process archive: {str(err)}"
        )
    finally:
        if temp_zip_path.exists():
            try:
                temp_zip_path.unlink()
            except Exception:
                pass
