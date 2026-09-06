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
