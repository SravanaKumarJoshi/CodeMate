import io
import zipfile
import pytest
from pathlib import Path
from app.tools.file_reader import read_file
from app.rag.ingestion import extract_zip_safely, is_safe_path


def test_file_reader_path_traversal_blocked():
    # Attempt to read outside project root
    res = read_file("../../etc/passwd")
    assert res["status"] == "error"
    assert "Path traversal attempt" in res["error"]

    res = read_file("../../../secret.env")
    assert res["status"] == "error"
    assert "Path traversal attempt" in res["error"]


def test_is_safe_path():
    base = Path("/safe/project/dir")
    safe_child = Path("/safe/project/dir/sub/file.py")
    unsafe_child = Path("/safe/project/dir/../../etc/passwd")

    assert is_safe_path(base, safe_child) is True
    assert is_safe_path(base, unsafe_child) is False


def test_zip_slip_prevention(tmp_path):
    # Construct an in-memory zip archive with a malicious traversal member
    zip_bytes = io.BytesIO()
    with zipfile.ZipFile(zip_bytes, "w") as zf:
        zf.writestr("../evil.py", "malicious_code()")

    zip_file_path = tmp_path / "evil.zip"
    zip_file_path.write_bytes(zip_bytes.getvalue())

    target_dir = tmp_path / "extracted"

    with pytest.raises(ValueError, match="Malicious path detected"):
        extract_zip_safely(zip_file_path, target_dir)


def test_env_example_has_no_secrets():
    env_example = Path(".env.example").read_text(encoding="utf-8")
    # Must not contain any compromised secret values
    assert "codemate-enterprise-secret-jwt-key-38472910" not in env_example
    # Must contain placeholder
    assert "JWT_SECRET_KEY=CHANGE_ME_TO_A_RANDOM_SECRET" in env_example
    # OpenAI key must be blank
    assert "OPENAI_API_KEY=\n" in env_example or "OPENAI_API_KEY=" in env_example


def test_gitignore_protects_env_and_sensitive_dirs():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    # Verify mandatory rules
    assert ".env" in gitignore
    assert ".env.*" in gitignore
    assert "!.env.example" in gitignore
    assert "pycache/" in gitignore or "__pycache__/" in gitignore
    assert "repositories/" in gitignore
    assert "storage/" in gitignore
    assert "uploads/" in gitignore
    assert "tmp/" in gitignore
    assert "temp/" in gitignore
    assert "chroma/" in gitignore or "chromadb/" in gitignore
    assert "*.db" in gitignore
    assert "*.sqlite" in gitignore
    assert "*.log" in gitignore


def test_jwt_secret_rotation_and_auth():
    import jwt
    from app.config import settings
    from app.security.auth import create_access_token, decode_access_token

    # Ensure current secret is not empty and not the compromised one
    assert settings.JWT_SECRET_KEY
    assert settings.JWT_SECRET_KEY != "codemate-enterprise-secret-jwt-key-38472910"

    # Create token with current secret
    token = create_access_token({"sub": "sec_test_user", "role": "admin"})
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "sec_test_user"

    # Verify that a token minted with the old compromised secret is REJECTED
    compromised_secret = "codemate-enterprise-secret-jwt-key-38472910"
    compromised_token = jwt.encode({"sub": "attacker"}, compromised_secret, algorithm="HS256")
    rejected_payload = decode_access_token(compromised_token)
    assert rejected_payload is None, "Old compromised token must be rejected after secret rotation"


def test_git_metadata_and_sensitive_files_excluded_during_ingestion():
    from app.security.archive_security import categorize_exclusion

    # Git metadata must be rejected
    assert categorize_exclusion(".git/objects/pack/pack-123.pack") == "Git metadata"
    assert categorize_exclusion(".git/HEAD") == "Git metadata"
    assert categorize_exclusion(".git/config") == "Git metadata"
    assert categorize_exclusion("main.py") is None  # standard python file allowed

    # Sensitive files must be excluded
    assert categorize_exclusion(".env") == "Excluded configuration (.env)"
    assert categorize_exclusion(".env.local") == "Excluded configuration (.env)"

    # Ignored binary/media extensions
    assert categorize_exclusion("image.png") == "Binary / media"
    assert categorize_exclusion("repo.zip") == "Binary / media"


def test_no_secrets_in_health_or_workflow_api():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.config import settings

    client = TestClient(app)

    # Check /api/health endpoint
    h_res = client.get("/api/health")
    assert h_res.status_code == 200
    h_text = h_res.text
    assert settings.JWT_SECRET_KEY not in h_text
    assert "codemate-enterprise-secret-jwt-key-38472910" not in h_text
    if settings.OPENAI_API_KEY:
        assert settings.OPENAI_API_KEY not in h_text

    # Check /api/workflow/architecture endpoint
    w_res = client.get("/api/workflow/architecture")
    assert w_res.status_code == 200
    w_text = w_res.text
    assert settings.JWT_SECRET_KEY not in w_text
    assert "codemate-enterprise-secret-jwt-key-38472910" not in w_text

