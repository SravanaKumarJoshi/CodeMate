"""
Large Repository Ingestion Pipeline for CodeMate.
Safely extracts archives incrementally, filters files, generates AST chunks,
embeds in batches, and updates database progress without loading entire repos into RAM.
"""

import os
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Set, Optional

from app.config import settings
from app.rag.chunking import chunk_code_file, detect_language
from app.rag.retriever import add_chunks, delete_repository_chunks
from app.security.archive_security import validate_and_extract_zip, ArchiveSecurityError
from app.security.path_security import is_safe_path
from app.services.repo_service import (
    update_repository_progress,
    mark_repository_ready,
    mark_repository_failed,
    set_active_repository_id
)

logger = logging.getLogger(__name__)

# State tracking currently active project root
_ACTIVE_PROJECT_PATH: Path = settings.SAMPLE_PROJECT_DIR


def get_active_project_path() -> Path:
    """Returns the root directory of the currently active codebase."""
    return _ACTIVE_PROJECT_PATH


def set_active_project_path(path: Path) -> None:
    """Sets the root directory of the currently active codebase."""
    global _ACTIVE_PROJECT_PATH
    _ACTIVE_PROJECT_PATH = path


def extract_zip_safely(zip_path: Path, extract_to: Path) -> Path:
    """Compatibility wrapper that validates and extracts ZIP archives safely."""
    try:
        root, _, _ = validate_and_extract_zip(zip_path, extract_to)
        return root
    except ArchiveSecurityError as err:
        raise ValueError(f"Malicious path detected in ZIP archive: {err}")


def scan_eligible_files(root_dir: Path) -> List[Path]:
    """
    Discovers source and documentation files while strictly ignoring
    dependencies, build artifacts, caches, and binary files.
    """
    from app.security.archive_security import categorize_exclusion

    eligible: List[Path] = []

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Exclude ignored directories in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in settings.IGNORED_DIRECTORIES
            and not d.startswith(".")
            and categorize_exclusion(d, is_dir=True) is None
        ]

        for fname in filenames:
            rel_file = Path(dirpath, fname).relative_to(root_dir).as_posix()
            if categorize_exclusion(rel_file, is_dir=False) is not None:
                continue

            full_path = Path(dirpath) / fname
            try:
                # Check individual file size limit
                if full_path.stat().st_size > settings.max_file_bytes:
                    logger.warning("Skipping oversized file: %s", full_path)
                    continue
                eligible.append(full_path)
            except Exception:
                continue

    return sorted(eligible)


def index_codebase_incrementally(
    source_dir: Path,
    repository_id: str,
    repository_name: str = "Project",
    archive_stats: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Scalable, memory-bounded repository indexing pipeline:
    1. Discovers files incrementally
    2. Parses & chunks file-by-file
    3. Batches embeddings into ChromaDB
    4. Tracks progress in DB
    5. Recovers gracefully if a single file has malformed syntax
    """
    logger.info("Starting incremental indexing for repo %s at %s", repository_id, source_dir)

    try:
        # Clear existing vectors for this repo to avoid duplicate chunk IDs
        delete_repository_chunks(repository_id)

        all_files = scan_eligible_files(source_dir)
        total_files = len(all_files)

        files_discovered = total_files
        files_skipped = 0
        skip_reasons = {}

        if archive_stats:
            files_discovered = archive_stats.get("files_discovered", total_files)
            files_skipped = archive_stats.get("files_skipped", 0)
            skip_reasons = archive_stats.get("skip_reasons", {})

        if total_files == 0:
            mark_repository_ready(
                repo_id=repository_id,
                total_files=0,
                total_chunks=0,
                languages=[],
                files_discovered=files_discovered,
                files_skipped=files_skipped,
                skip_reasons=skip_reasons
            )
            return {
                "status": "ready",
                "repository_id": repository_id,
                "files_processed": 0,
                "files_indexed": 0,
                "files_discovered": files_discovered,
                "files_skipped": files_skipped,
                "skip_reasons": skip_reasons,
                "total_files": 0,
                "total_chunks": 0,
                "progress": 100
            }

        update_repository_progress(
            repo_id=repository_id,
            processed_files=0,
            total_files=total_files,
            total_chunks=0,
            progress=5,
            status="indexing",
            files_discovered=files_discovered,
            files_skipped=files_skipped,
            skip_reasons=skip_reasons
        )

        total_chunks = 0
        processed_files_count = 0
        languages_detected: Set[str] = set()
        chunk_buffer: List[Dict[str, Any]] = []

        for idx, file_path in enumerate(all_files):
            try:
                rel_path = file_path.relative_to(source_dir).as_posix()
                lang = detect_language(rel_path)
                languages_detected.add(lang)

                content = file_path.read_text(encoding="utf-8", errors="replace")
                file_chunks = chunk_code_file(
                    file_path=rel_path,
                    content=content,
                    repository_id=repository_id,
                    max_chunk_lines=settings.CHUNK_SIZE // 10,
                    overlap_lines=settings.CHUNK_OVERLAP // 10
                )

                chunk_buffer.extend(file_chunks)
                total_chunks += len(file_chunks)
                processed_files_count += 1

                # Flush chunks in batches to ChromaDB to bound memory
                if len(chunk_buffer) >= settings.EMBEDDING_BATCH_SIZE:
                    add_chunks(chunk_buffer, repository_id=repository_id)
                    chunk_buffer = []

                # Update progress periodically (every 10 files or on completion)
                if (idx + 1) % 10 == 0 or (idx + 1) == total_files:
                    progress_pct = int(10 + (85 * (idx + 1) / total_files))
                    update_repository_progress(
                        repo_id=repository_id,
                        processed_files=processed_files_count,
                        total_files=total_files,
                        total_chunks=total_chunks,
                        progress=progress_pct,
                        status="indexing",
                        languages=sorted(list(languages_detected)),
                        files_discovered=files_discovered,
                        files_skipped=files_skipped,
                        skip_reasons=skip_reasons
                    )

            except Exception as file_err:
                logger.warning("Error indexing file %s: %s; continuing indexing", file_path, file_err)
                processed_files_count += 1

        # Flush any remaining chunks
        if chunk_buffer:
            add_chunks(chunk_buffer, repository_id=repository_id)

        # Mark repository ready
        lang_list = sorted(list(languages_detected))
        mark_repository_ready(
            repo_id=repository_id,
            total_files=processed_files_count,
            total_chunks=total_chunks,
            languages=lang_list,
            files_discovered=files_discovered,
            files_skipped=files_skipped,
            skip_reasons=skip_reasons
        )

        set_active_project_path(source_dir)
        set_active_repository_id(repository_id)

        logger.info(
            "Repository %s indexed successfully: %d files, %d chunks",
            repository_id, processed_files_count, total_chunks
        )

        return {
            "status": "ready",
            "repository_id": repository_id,
            "files_processed": processed_files_count,
            "files_indexed": processed_files_count,
            "files_discovered": files_discovered,
            "files_skipped": files_skipped,
            "skip_reasons": skip_reasons,
            "total_files": total_files,
            "total_chunks": total_chunks,
            "progress": 100,
            "languages": lang_list
        }

    except Exception as err:
        logger.error("Failed to index repository %s: %s", repository_id, err, exc_info=True)
        mark_repository_failed(repository_id, str(err))
        raise


def index_codebase(source_dir: Path, repository_id: str = "repo_sample_project") -> Dict[str, Any]:
    """Compatibility wrapper for synchronous indexing calls."""
    res = index_codebase_incrementally(source_dir, repository_id=repository_id)
    res["status"] = "success"
    res["files_indexed"] = res.get("files_processed", 0)
    res["chunks_indexed"] = res.get("total_chunks", 0)
    return res
