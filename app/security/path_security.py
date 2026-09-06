"""
Path traversal and filesystem security utilities for CodeMate.
Ensures repository access is strictly contained within designated boundaries.
"""

import re
from pathlib import Path


def is_safe_path(base_dir: Path, target_path: Path) -> bool:
    """Verifies that target_path is strictly contained within base_dir."""
    try:
        resolved_base = base_dir.resolve()
        resolved_target = target_path.resolve()
        return resolved_base in resolved_target.parents or resolved_base == resolved_target
    except Exception:
        return False


def resolve_safe_path(base_dir: Path, relative_path: str) -> Path:
    """
    Safely resolves a relative path against base_dir.
    Raises ValueError if path traversal or escape is detected.
    """
    if not relative_path or not relative_path.strip():
        raise ValueError("Path cannot be empty.")

    cleaned_rel = relative_path.replace("\\", "/").strip().lstrip("/")
    
    # Check for path traversal patterns
    parts = Path(cleaned_rel).parts
    if ".." in parts:
        raise ValueError(f"Path traversal detected: {relative_path}")

    target = (base_dir / cleaned_rel).resolve()
    if not is_safe_path(base_dir, target):
        raise ValueError(f"Path escape attempt detected: {relative_path}")

    return target


def sanitize_filename(filename: str) -> str:
    """Sanitizes user-provided filenames to prevent filesystem injection."""
    cleaned = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', filename)
    return cleaned.strip('._') or "unnamed_file"
