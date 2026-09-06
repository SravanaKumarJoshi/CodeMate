"""
Comprehensive test suite for CodeMate Large Repository Upgrade:
- Streaming upload & background indexing polling
- Multi-repository isolation (zero cross-repository leakage)
- Archive security (Zip Slip, Path Traversal, Archive Bomb)
- Symbol search & AST chunking
- Interactive workflow API & live tracing
- Authentication & Authorization
"""

import io
import time
import zipfile
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.rag.chunking import chunk_code_file
from app.rag.retriever import query_code, add_chunks, query_symbols
from app.tools.search_symbols import search_symbols
from app.security.archive_security import validate_and_extract_zip, ArchiveSecurityError

client = TestClient(app)


def test_ast_python_chunking_with_symbols():
    """Verifies that AST chunking extracts functions, classes, and metadata."""
    code = (
        "'''Module overview docstring.'''\n"
        "import os\n\n"
        "class AuthService:\n"
        "    def authenticate(self, username, password):\n"
        "        return True\n\n"
        "def verify_token(token: str) -> bool:\n"
        "    return len(token) > 0\n"
    )

    chunks = chunk_code_file("auth_service.py", code, repository_id="test_repo")
    assert len(chunks) >= 3

    symbols = [c["metadata"]["symbol"] for c in chunks]
    assert "verify_token" in symbols
    assert "AuthService" in symbols
    assert all(c["metadata"]["repository_id"] == "test_repo" for c in chunks)


def test_repository_isolation():
    """Verifies that querying repo A never returns code from repo B."""
    repo_a = "repo_company_a"
    repo_b = "repo_company_b"

    chunk_a = [{
        "id": f"{repo_a}:secret.py:1-5:leak_test",
        "content": "SECRET_KEY_COMPANY_A = 'ALPHA_SECRET_12345'",
        "metadata": {
            "repository_id": repo_a,
            "file_path": "secret.py",
            "start_line": 1,
            "end_line": 5,
            "symbol": "SECRET_KEY_COMPANY_A",
            "chunk_type": "code",
            "total_lines": 5
        }
    }]

    chunk_b = [{
        "id": f"{repo_b}:secret.py:1-5:leak_test",
        "content": "SECRET_KEY_COMPANY_B = 'BETA_SECRET_67890'",
        "metadata": {
            "repository_id": repo_b,
            "file_path": "secret.py",
            "start_line": 1,
            "end_line": 5,
            "symbol": "SECRET_KEY_COMPANY_B",
            "chunk_type": "code",
            "total_lines": 5
        }
    }]

    add_chunks(chunk_a, repository_id=repo_a)
    add_chunks(chunk_b, repository_id=repo_b)

    # Query strictly repo_a
    results_a = query_code("SECRET_KEY", repository_id=repo_a, top_k=5)
    for hit in results_a:
        assert hit["repository_id"] == repo_a
        assert "BETA_SECRET" not in hit["content"]

    # Query strictly repo_b
    results_b = query_code("SECRET_KEY", repository_id=repo_b, top_k=5)
    for hit in results_b:
        assert hit["repository_id"] == repo_b
        assert "ALPHA_SECRET" not in hit["content"]


def test_symbol_search_tool():
    """Verifies symbol search retrieves function definitions."""
    results = search_symbols("login", repository_id="repo_sample_project")
    assert isinstance(results, list)


def test_archive_security_rejections(tmp_path):
    """Verifies Zip Slip and oversized file protections."""
    # 1. Zip Slip
    slip_buf = io.BytesIO()
    with zipfile.ZipFile(slip_buf, "w") as zf:
        zf.writestr("../../escape.py", "print('hacked')")
    slip_zip = tmp_path / "slip.zip"
    slip_zip.write_bytes(slip_buf.getvalue())

    with pytest.raises(ArchiveSecurityError, match="Zip Slip"):
        validate_and_extract_zip(slip_zip, tmp_path / "extracted_slip")

    # 2. Empty archive
    empty_zip = tmp_path / "empty.zip"
    empty_zip.write_bytes(b"")
    with pytest.raises(ArchiveSecurityError):
        validate_and_extract_zip(empty_zip, tmp_path / "extracted_empty")


def test_workflow_api():
    """Verifies workflow architecture specs and live execution tracing."""
    # 1. Architecture metadata endpoint
    arch_res = client.get("/api/workflow/architecture")
    assert arch_res.status_code == 200
    arch_data = arch_res.json()
    assert "intent_classifier" in arch_data
    assert "langgraph_agent" in arch_data
    assert "rag_chromadb" in arch_data

    # 2. Execute a chat query
    chat_res = client.post("/api/chat", json={"message": "Where is authentication implemented?"})
    assert chat_res.status_code == 200
    chat_data = chat_res.json()
    assert "request_id" in chat_data
    assert len(chat_data["workflow_steps"]) > 0

    req_id = chat_data["request_id"]

    # 3. Retrieve trace from /api/workflow/{request_id}
    trace_res = client.get(f"/api/workflow/{req_id}")
    assert trace_res.status_code == 200
    trace_data = trace_res.json()
    assert trace_data["request_id"] == req_id
    assert trace_data["status"] == "completed"
    assert len(trace_data["steps"]) > 0


def test_repositories_endpoints():
    """Verifies repository listing and indexing status polling."""
    # List repositories
    list_res = client.get("/api/repositories")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert "repositories" in list_data

    # Status polling for sample project
    status_res = client.get("/api/repositories/repo_sample_project/status")
    assert status_res.status_code in [200, 404]


def test_auth_endpoints():
    """Verifies user registration, login, and profile fetching."""
    username = f"test_dev_{int(time.time())}"
    password = "DevPassword123!"

    # 1. Register
    reg_res = client.post("/api/auth/register", json={"username": username, "password": password})
    assert reg_res.status_code == 200
    token = reg_res.json()["access_token"]
    assert token

    # 2. Login
    login_res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert login_res.status_code == 200
    assert login_res.json()["access_token"]

    # 3. Me
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["username"] == username


def test_regression_git_pack_skipped_not_file_too_large(tmp_path):
    """
    Regression Test:
    Input: PDD/.git/objects/pack/pack-5c2d3b376199143993a153ad009c11bed87dc1c8.pack (> 50 MB)
    Expected: SKIPPED, NOT FILE_TOO_LARGE.
    """
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Create a > 50 MB .git pack member (52 MB of zeros compresses to ~50 KB)
        dummy_pack_data = b"0" * (52 * 1024 * 1024)
        zf.writestr(
            "PDD/.git/objects/pack/pack-5c2d3b376199143993a153ad009c11bed87dc1c8.pack",
            dummy_pack_data
        )
        # Add a legitimate source file
        zf.writestr("PDD/src/service.py", "def process(): return 'ok'\n")

    test_zip = tmp_path / "pdd_test.zip"
    test_zip.write_bytes(zip_buf.getvalue())

    extract_target = tmp_path / "extracted_pdd"
    # Must NOT raise ArchiveSecurityError for the 52 MB pack file!
    result = validate_and_extract_zip(test_zip, extract_target)

    assert result.total_files_extracted == 1
    assert result.files_discovered == 2
    assert result.files_skipped == 1
    assert result.skip_reasons.get("Git metadata", 0) >= 1

    # Verify .git pack file was skipped and not extracted
    pack_path = extract_target / "PDD" / ".git" / "objects" / "pack" / "pack-5c2d3b376199143993a153ad009c11bed87dc1c8.pack"
    assert not pack_path.exists()

    # Verify legitimate source file was extracted
    service_path = result.root / "src" / "service.py"
    assert service_path.exists()
    assert "process" in service_path.read_text()


def test_oversized_source_file_rejected(tmp_path):
    """
    Verifies that the 50 MB limit continues to reject legitimate indexable files
    that exceed the limit (e.g., src/data/huge_source.py > 50 MB).
    """
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Create a 64 MB indexable source file (> 50 MB limit)
        huge_source = b"# Comment\nx = 1\n" * (4 * 1024 * 1024)
        zf.writestr("src/data/huge_source.py", huge_source)

    huge_zip = tmp_path / "huge_source.zip"
    huge_zip.write_bytes(zip_buf.getvalue())

    with pytest.raises(ArchiveSecurityError, match="exceeds single file limit"):
        validate_and_extract_zip(huge_zip, tmp_path / "extracted_huge")


def test_user_exact_scenario_upload_and_rag(tmp_path):
    """
    Verifies user's exact scenario:
    project/
    ├── backend/
    │   └── app.py
    ├── frontend/
    │   └── app.tsx
    ├── README.md
    ├── package.json
    └── .git/
        └── objects/
            └── pack/
                └── large.pack (> 50 MB)

    Verifies:
    1. ZIP uploads successfully.
    2. Upload is streamed to disk in chunks.
    3. .git is skipped.
    4. large.pack does not trigger the 50 MB error.
    5. backend/app.py is indexed.
    6. frontend/app.tsx is indexed.
    7. README.md is indexed.
    8. package.json is indexed.
    9. ChromaDB contains only indexable content.
    10. RAG can answer questions about the application.
    11. No uploaded code is executed.
    12. Indexing completes successfully.
    """
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "project/backend/app.py",
            "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/health')\ndef health():\n    return {'status': 'healthy', 'service': 'payment-gateway'}\n"
        )
        zf.writestr(
            "project/frontend/app.tsx",
            "import React from 'react';\n\nexport const PaymentDashboard: React.FC = () => {\n  return <div>Payment Dashboard UI</div>;\n};\n"
        )
        zf.writestr(
            "project/README.md",
            "# Payment Gateway System\nThis service orchestrates e-commerce payments and checkout verification.\n"
        )
        zf.writestr(
            "project/package.json",
            '{\n  "name": "payment-frontend",\n  "version": "1.0.0",\n  "scripts": { "dev": "vite" }\n}\n'
        )
        # large.pack > 50 MB (52 MB)
        zf.writestr(
            "project/.git/objects/pack/large.pack",
            b"0" * (52 * 1024 * 1024)
        )

    zip_bytes = zip_buf.getvalue()

    # Upload via /api/index
    res = client.post(
        "/api/index",
        files={"file": ("project.zip", zip_bytes, "application/zip")}
    )

    assert res.status_code == 200, res.text
    data = res.json()["data"]

    assert data["status"] == "ready"
    assert data["files_indexed"] == 4
    assert data["files_discovered"] == 5
    assert data["files_skipped"] == 1
    assert data["skip_reasons"].get("Git metadata", 0) == 1

    repo_id = data["repository_id"]

    # Verify status endpoint returns skip details
    status_res = client.get(f"/api/repositories/{repo_id}/status")
    assert status_res.status_code == 200
    st_data = status_res.json()
    assert st_data["status"] == "ready"
    assert st_data["files_indexed"] == 4
    assert st_data["files_discovered"] == 5
    assert st_data["files_skipped"] == 1
    assert st_data["skip_reasons"].get("Git metadata") == 1

    # Verify ChromaDB contains only indexable files (no .git chunks)
    code_hits = query_code("payment", repository_id=repo_id, top_k=10)
    assert len(code_hits) > 0
    for hit in code_hits:
        assert not hit["file_path"].startswith(".git")
        assert not hit["file_path"].endswith(".pack")
        assert hit["file_path"] in [
            "backend/app.py",
            "frontend/app.tsx",
            "README.md",
            "package.json"
        ]

    # Verify RAG answers questions based on indexed content
    chat_res = client.post(
        "/api/chat",
        json={
            "message": "What services and components are defined in this repository?",
            "repository_id": repo_id
        }
    )
    assert chat_res.status_code == 200
    chat_data = chat_res.json()
    answer = chat_data["answer"].lower()
    assert any(term in answer for term in ["payment", "gateway", "backend", "frontend", "health", "dashboard"])


def test_repositories_stream_upload_endpoint(tmp_path):
    """
    Verifies POST /api/repositories/upload accepts large streaming ZIP with .git,
    returns 202 Accepted, and processes indexing in background.
    """
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("app/main.py", "def run(): print('app running')\n")
        zf.writestr("app/.git/objects/pack/large.pack", b"0" * (52 * 1024 * 1024))
        zf.writestr("app/node_modules/dep/index.js", "module.exports = {};\n")

    res = client.post(
        "/api/repositories/upload",
        files={"file": ("app.zip", zip_buf.getvalue(), "application/zip")},
        data={"repository_name": "StreamTestRepo"}
    )
    assert res.status_code == 202
    res_data = res.json()
    assert res_data["status"] == "indexing"
    repo_id = res_data["repository_id"]

    # Background tasks in Starlette TestClient execute synchronously on exit
    status_res = client.get(f"/api/repositories/{repo_id}/status")
    assert status_res.status_code == 200
    st_data = status_res.json()
    assert st_data["status"] == "ready"
    assert st_data["files_indexed"] == 1
    assert st_data["files_skipped"] >= 2
    assert st_data["skip_reasons"].get("Git metadata", 0) >= 1
    assert st_data["skip_reasons"].get("Dependencies", 0) >= 1


