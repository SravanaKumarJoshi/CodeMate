"""
AST-Aware Code Chunking Engine for CodeMate.
Extracts semantic structures (classes, functions, methods, imports, docstrings)
for Python via AST parsing, with structural block parsers for JavaScript,
TypeScript, Go, Rust, Java, SQL, and documentation formats.
"""

import ast
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

EXTENSION_LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".md": "markdown",
    ".txt": "text",
    ".sh": "bash"
}


def detect_language(file_path: str) -> str:
    """Detects programming language from file extension."""
    for ext, lang in EXTENSION_LANGUAGE_MAP.items():
        if file_path.lower().endswith(ext):
            return lang
    return "text"


def chunk_code_file(
    file_path: str,
    content: str,
    repository_id: str = "default_repo",
    max_chunk_lines: int = 50,
    overlap_lines: int = 10
) -> List[Dict[str, Any]]:
    """
    Intelligently splits a file into semantic chunks based on its language.
    Uses AST for Python, structural block matching for other languages,
    and sliding window fallback for raw text/config files.
    """
    if not content or not content.strip():
        return []

    lines = content.splitlines()
    total_lines = len(lines)
    language = detect_language(file_path)

    # 1. Python AST-Aware Chunking
    if language == "python":
        ast_chunks = _chunk_python_ast(file_path, content, lines, repository_id, max_chunk_lines, overlap_lines)
        if ast_chunks:
            return ast_chunks

    # 2. Structural Regex Chunking (JS/TS/Go/Java/Rust/SQL)
    if language in {"javascript", "typescript", "java", "go", "rust", "cpp", "c", "sql"}:
        structural_chunks = _chunk_structural_code(file_path, content, lines, language, repository_id)
        if structural_chunks:
            return structural_chunks

    # 3. Line-based Sliding Window Fallback
    return _chunk_sliding_window(file_path, lines, language, repository_id, max_chunk_lines, overlap_lines)


def _chunk_python_ast(
    file_path: str,
    content: str,
    lines: List[str],
    repository_id: str,
    max_chunk_lines: int = 50,
    overlap_lines: int = 10
) -> List[Dict[str, Any]]:
    """Extracts classes, functions, async functions, imports, and docstrings using Python AST."""
    chunks: List[Dict[str, Any]] = []
    total_lines = len(lines)

    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError as err:
        logger.debug("AST parse failed for %s (%s); falling back to sliding window", file_path, err)
        return []

    # Module docstring
    module_doc = ast.get_docstring(tree)
    if module_doc:
        doc_lines = len(module_doc.splitlines())
        chunks.append({
            "id": f"{repository_id}:{file_path}:1-{doc_lines}:module_docstring",
            "content": f"# Module Documentation for {file_path}\n{module_doc}",
            "metadata": {
                "repository_id": repository_id,
                "file_path": file_path,
                "language": "python",
                "start_line": 1,
                "end_line": doc_lines,
                "symbol": "module_docstring",
                "chunk_type": "docstring",
                "total_lines": total_lines
            }
        })

    # Group top-level imports
    import_nodes = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    if import_nodes:
        first_imp = min(node.lineno for node in import_nodes)
        last_imp = max(getattr(node, "end_lineno", node.lineno) for node in import_nodes)
        imp_text = "\n".join(lines[first_imp - 1:last_imp])
        if imp_text.strip():
            chunks.append({
                "id": f"{repository_id}:{file_path}:{first_imp}-{last_imp}:imports",
                "content": f"# Dependencies for {file_path}\n{imp_text}",
                "metadata": {
                    "repository_id": repository_id,
                    "file_path": file_path,
                    "language": "python",
                    "start_line": first_imp,
                    "end_line": last_imp,
                    "symbol": "imports",
                    "chunk_type": "imports",
                    "total_lines": total_lines
                }
            })

    # Top-level functions and classes
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            s_line = node.lineno
            e_line = getattr(node, "end_lineno", s_line)
            fn_text = "\n".join(lines[s_line - 1:e_line])
            fn_symbol = node.name

            chunks.append({
                "id": f"{repository_id}:{file_path}:{s_line}-{e_line}:{fn_symbol}",
                "content": fn_text,
                "metadata": {
                    "repository_id": repository_id,
                    "file_path": file_path,
                    "language": "python",
                    "start_line": s_line,
                    "end_line": e_line,
                    "symbol": fn_symbol,
                    "chunk_type": "function",
                    "total_lines": total_lines
                }
            })

        elif isinstance(node, ast.ClassDef):
            class_s_line = node.lineno
            class_e_line = getattr(node, "end_lineno", class_s_line)
            class_symbol = node.name

            # Class header & docstring
            class_text = "\n".join(lines[class_s_line - 1:class_e_line])
            chunks.append({
                "id": f"{repository_id}:{file_path}:{class_s_line}-{class_e_line}:{class_symbol}",
                "content": class_text,
                "metadata": {
                    "repository_id": repository_id,
                    "file_path": file_path,
                    "language": "python",
                    "start_line": class_s_line,
                    "end_line": class_e_line,
                    "symbol": class_symbol,
                    "chunk_type": "class",
                    "total_lines": total_lines
                }
            })

            # Also index individual methods for granular search
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    m_s = item.lineno
                    m_e = getattr(item, "end_lineno", m_s)
                    m_text = "\n".join(lines[m_s - 1:m_e])
                    method_symbol = f"{class_symbol}.{item.name}"
                    chunks.append({
                        "id": f"{repository_id}:{file_path}:{m_s}-{m_e}:{method_symbol}",
                        "content": m_text,
                        "metadata": {
                            "repository_id": repository_id,
                            "file_path": file_path,
                            "language": "python",
                            "start_line": m_s,
                            "end_line": m_e,
                            "symbol": method_symbol,
                            "chunk_type": "method",
                            "total_lines": total_lines
                        }
                    })

    # If file was small or had mostly top-level script statements, ensure whole file is represented
    if not chunks:
        return _chunk_sliding_window(file_path, lines, "python", repository_id, max_chunk_lines, overlap_lines)

    return chunks


def _chunk_structural_code(
    file_path: str,
    content: str,
    lines: List[str],
    language: str,
    repository_id: str
) -> List[Dict[str, Any]]:
    """Detects function/class/method definitions in C-style, Go, and SQL code."""
    chunks: List[Dict[str, Any]] = []
    total_lines = len(lines)

    # Patterns for functions, classes, and endpoints
    definition_regex = re.compile(
        r'^(?:export\s+)?(?:async\s+)?(?:function|class|const|let|var|def|type|struct|func|interface)\s+([a-zA-Z0-9_$]+)',
        re.MULTILINE
    )

    matches = list(definition_regex.finditer(content))
    if not matches:
        return []

    # Map character indices to line numbers
    line_offsets = []
    curr_offset = 0
    for l in lines:
        line_offsets.append(curr_offset)
        curr_offset += len(l) + 1  # newline

    def offset_to_line(offset: int) -> int:
        for idx, start_pos in enumerate(line_offsets):
            if offset < start_pos:
                return max(1, idx)
        return len(lines)

    for i, m in enumerate(matches):
        symbol = m.group(1)
        s_line = offset_to_line(m.start())
        if i + 1 < len(matches):
            e_line = max(s_line, offset_to_line(matches[i + 1].start()) - 1)
        else:
            e_line = total_lines

        # Bound chunk length to ~60 lines
        e_line = min(s_line + 60, e_line)
        chunk_text = "\n".join(lines[s_line - 1:e_line])

        if chunk_text.strip():
            chunks.append({
                "id": f"{repository_id}:{file_path}:{s_line}-{e_line}:{symbol}",
                "content": chunk_text,
                "metadata": {
                    "repository_id": repository_id,
                    "file_path": file_path,
                    "language": language,
                    "start_line": s_line,
                    "end_line": e_line,
                    "symbol": symbol,
                    "chunk_type": "definition",
                    "total_lines": total_lines
                }
            })

    return chunks


def _chunk_sliding_window(
    file_path: str,
    lines: List[str],
    language: str,
    repository_id: str,
    max_chunk_lines: int = 50,
    overlap_lines: int = 10
) -> List[Dict[str, Any]]:
    """Standard sliding window chunker for general code and documentation."""
    total_lines = len(lines)
    if total_lines == 0:
        return []

    if total_lines <= max_chunk_lines:
        return [{
            "id": f"{repository_id}:{file_path}:1-{total_lines}:full",
            "content": "\n".join(lines),
            "metadata": {
                "repository_id": repository_id,
                "file_path": file_path,
                "language": language,
                "start_line": 1,
                "end_line": total_lines,
                "symbol": Path(file_path).stem,
                "chunk_type": "full_file",
                "total_lines": total_lines
            }
        }]

    chunks: List[Dict[str, Any]] = []
    start = 0
    step = max(1, max_chunk_lines - overlap_lines)

    while start < total_lines:
        end = min(start + max_chunk_lines, total_lines)
        chunk_lines = lines[start:end]
        chunk_text = "\n".join(chunk_lines)

        chunk_id = f"{repository_id}:{file_path}:{start + 1}-{end}:block"
        chunks.append({
            "id": chunk_id,
            "content": chunk_text,
            "metadata": {
                "repository_id": repository_id,
                "file_path": file_path,
                "language": language,
                "start_line": start + 1,
                "end_line": end,
                "symbol": Path(file_path).stem,
                "chunk_type": "block",
                "total_lines": total_lines
            }
        })

        if end >= total_lines:
            break
        start += step

    return chunks
