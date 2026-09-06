"""
Archive Security Module for CodeMate.
Safely validates and extracts repository archives.
Guards against:
- Zip Slip (path traversal)
- Archive Bombs (decompression ratio & total size limits)
- File count exhaustion (max files limit)
- Oversized individual files
- Symlink exploitation
"""

import os
import zipfile
import logging
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
from app.config import settings
from app.security.path_security import is_safe_path

logger = logging.getLogger(__name__)


class ArchiveSecurityError(Exception):
    """Raised when an archive violates security constraints."""
    pass


class ExtractionResult:
    """Holds results of safe archive extraction with skip statistics."""
    def __init__(
        self,
        root_dir: Path,
        total_files_extracted: int,
        total_bytes_extracted: int,
        files_discovered: int,
        files_skipped: int,
        skip_reasons: Dict[str, int]
    ):
        self.root_dir = root_dir
        self.total_files_extracted = total_files_extracted
        self.total_bytes_extracted = total_bytes_extracted
        self.files_discovered = files_discovered
        self.files_skipped = files_skipped
        self.skip_reasons = skip_reasons

    @property
    def root(self) -> Path:
        return self.root_dir

    @property
    def file_count(self) -> int:
        return self.total_files_extracted

    @property
    def byte_count(self) -> int:
        return self.total_bytes_extracted

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "files_discovered": self.files_discovered,
            "files_indexed": self.total_files_extracted,
            "files_skipped": self.files_skipped,
            "skip_reasons": self.skip_reasons
        }

    # Backward compatibility: allows unpacking as 3-tuple (root_dir, total_files, bytes_written)
    def __iter__(self):
        return iter((self.root_dir, self.total_files_extracted, self.total_bytes_extracted))

    def __getitem__(self, index):
        return (self.root_dir, self.total_files_extracted, self.total_bytes_extracted)[index]

    def __len__(self):
        return 3


def categorize_exclusion(raw_name: str, is_dir: bool = False) -> Optional[str]:
    """
    Evaluates whether an archive path or file path belongs to an excluded
    directory or file type. Returns the category name if excluded, or None if indexable.
    Categories:
      - 'Git metadata'
      - 'Dependencies'
      - 'Cache'
      - 'Build artifacts'
      - 'Binary / media'
      - 'Unsupported extension'
      - 'Excluded directory'
    """
    norm_name = raw_name.replace("\\", "/").strip("/")
    parts = [p for p in norm_name.split("/") if p]
    if not parts:
        return "Directory" if is_dir else None

    dir_parts = parts if is_dir else parts[:-1]
    filename = "" if is_dir else parts[-1]

    # Check directory components (case-insensitive)
    for part in dir_parts:
        part_lower = part.lower()

        # Git metadata
        if part_lower in {".git", ".svn", ".hg"}:
            return "Git metadata"

        # Dependencies
        if part_lower in {"node_modules", "vendor", ".venv", "venv", "env"}:
            return "Dependencies"

        # Cache
        if part_lower in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache"}:
            return "Cache"

        # Build artifacts
        if part_lower in {"dist", "build", "target", "coverage", "bin", "obj", ".idea", ".vscode"}:
            return "Build artifacts"

        # Settings ignored directories
        if part_lower in settings.IGNORED_DIRECTORIES:
            return "Excluded directory"

    if is_dir:
        return None

    # Evaluate filename
    filename_lower = filename.lower()

    # Git pack/idx files
    if filename_lower.endswith((".pack", ".idx")):
        return "Git metadata"

    # Security sensitive files
    if filename_lower == ".env" or (filename_lower.startswith(".env") and filename_lower != ".env.example"):
        return "Excluded configuration (.env)"

    _, ext = os.path.splitext(filename_lower)

    # Ignored binary/media extensions
    if ext in settings.IGNORED_EXTENSIONS:
        if ext in {".pack", ".idx"}:
            return "Git metadata"
        return "Binary / media"

    # Non-supported source extension
    if ext not in settings.ALLOWED_EXTENSIONS:
        return "Unsupported extension"

    return None


def validate_and_extract_zip(zip_path: Path, extract_to: Path) -> ExtractionResult:
    """
    Safely inspects and extracts a ZIP archive into extract_to directory.
    Enforces:
      1. Path normalization & Zip Slip / traversal protection.
      2. Symlink rejection.
      3. Exclusion filtering BEFORE single-file size checking.
         Excluded files (.git/, node_modules/, *.pack) are skipped without error.
      4. Single file limit (50 MB) on eligible source/doc files.
      5. Total extracted size & decompression ratio limits.
      6. Streamed chunked extraction of indexable files.
    Returns ExtractionResult (unpacks as 3-tuple for full backward compatibility).
    """
    if not zip_path.exists():
        raise ArchiveSecurityError(f"Archive file not found: {zip_path}")

    compressed_size = zip_path.stat().st_size
    if compressed_size == 0:
        raise ArchiveSecurityError("Archive is empty (0 bytes).")

    if compressed_size > settings.max_upload_bytes:
        raise ArchiveSecurityError(
            f"Archive exceeds max upload size ({settings.MAX_UPLOAD_SIZE_MB} MB)."
        )

    extract_to.mkdir(parents=True, exist_ok=True)
    resolved_extract_to = extract_to.resolve()

    files_discovered = 0
    files_skipped = 0
    skip_reasons: Dict[str, int] = {
        "Git metadata": 0,
        "Dependencies": 0,
        "Cache": 0,
        "Build artifacts": 0,
        "Binary / media": 0,
        "Unsupported extension": 0,
    }

    indexable_members = []
    total_uncompressed_size = 0

    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            infolist = archive.infolist()

            # 1. Archive File Count Check
            if len(infolist) > settings.MAX_ARCHIVE_FILES:
                raise ArchiveSecurityError(
                    f"Archive contains too many files ({len(infolist)} > {settings.MAX_ARCHIVE_FILES})."
                )

            # 2. Pre-scan metadata: Zip Slip & Bomb check with pre-filtering
            for member in infolist:
                # Reject symlinks and hardlinks
                mode = member.external_attr >> 16
                if mode & 0o120000 == 0o120000:
                    raise ArchiveSecurityError(f"Symlinks are disallowed: {member.filename}")

                # Path normalization and traversal checks
                raw_name = member.filename.replace("\\", "/")
                target_dest = (resolved_extract_to / raw_name).resolve()

                if not is_safe_path(resolved_extract_to, target_dest):
                    raise ArchiveSecurityError(f"Zip Slip path traversal detected: {member.filename}")

                if member.is_dir():
                    continue

                files_discovered += 1

                # 3. Determine whether the path is excluded
                exclusion_reason = categorize_exclusion(raw_name, is_dir=False)

                # 4. If excluded -> SKIP (Do NOT apply 50 MB single file limit!)
                if exclusion_reason:
                    files_skipped += 1
                    skip_reasons[exclusion_reason] = skip_reasons.get(exclusion_reason, 0) + 1
                    continue

                # 5. If not excluded -> validate single file size limit
                if member.file_size > settings.max_file_bytes:
                    raise ArchiveSecurityError(
                        f"File '{member.filename}' exceeds single file limit ({settings.MAX_FILE_SIZE_MB} MB)."
                    )

                total_uncompressed_size += member.file_size
                indexable_members.append(member)

                # Archive Bomb: Max decompressed size check for indexable source
                if total_uncompressed_size > settings.max_extracted_bytes:
                    raise ArchiveSecurityError(
                        f"Archive decompressed size exceeds safety limit ({settings.MAX_EXTRACTED_SIZE_MB} MB)."
                    )

            # Archive Bomb: Decompression ratio check on indexable source
            if compressed_size > 0 and total_uncompressed_size > 50 * 1024 * 1024:
                ratio = total_uncompressed_size / compressed_size
                if ratio > settings.MAX_DECOMPRESSION_RATIO:
                    raise ArchiveSecurityError(
                        f"Decompression ratio ({ratio:.1f}x) exceeds safe threshold ({settings.MAX_DECOMPRESSION_RATIO}x)."
                    )

            # 3. Safe Extraction: Stream file by file for indexable files only
            bytes_written = 0
            for member in indexable_members:
                raw_name = member.filename.replace("\\", "/")
                target_dest = (resolved_extract_to / raw_name).resolve()

                if not is_safe_path(resolved_extract_to, target_dest):
                    raise ArchiveSecurityError(f"Path escape during extraction: {member.filename}")

                target_dest.parent.mkdir(parents=True, exist_ok=True)

                # Write incrementally in 64KB blocks
                with archive.open(member) as src, open(target_dest, "wb") as dst:
                    while chunk := src.read(settings.UPLOAD_CHUNK_SIZE_KB * 1024):
                        dst.write(chunk)
                        bytes_written += len(chunk)

    except zipfile.BadZipFile as err:
        raise ArchiveSecurityError(f"Corrupted or invalid ZIP archive: {err}")

    # Check for single top-level directory wrapper
    top_entries = [p for p in extract_to.iterdir() if p.name not in settings.IGNORED_DIRECTORIES]
    if len(top_entries) == 1 and top_entries[0].is_dir():
        extracted_root = top_entries[0]
    else:
        extracted_root = extract_to

    clean_skip_reasons = {k: v for k, v in skip_reasons.items() if v > 0}

    logger.info(
        "Extracted %d eligible files (%d bytes uncompressed, %d skipped) safely to %s",
        len(indexable_members), bytes_written, files_skipped, extracted_root
    )

    return ExtractionResult(
        root_dir=extracted_root,
        total_files_extracted=len(indexable_members),
        total_bytes_extracted=bytes_written,
        files_discovered=files_discovered,
        files_skipped=files_skipped,
        skip_reasons=clean_skip_reasons
    )
