from app.tools.code_search import search_code
from app.tools.file_reader import read_file
from app.tools.test_generator import generate_unit_test
from app.tools.file_lister import list_project_files


def test_tool_code_search():
    res = search_code("verify_password", top_k=2)
    assert isinstance(res, list)
    assert len(res) > 0


def test_tool_file_reader():
    res = read_file("auth.py", start_line=1, end_line=15)
    assert res["status"] == "success"
    assert "def" in res["content"] or "import" in res["content"]
    assert res["start_line"] == 1
    assert res["end_line"] == 15


def test_tool_test_generator():
    res = generate_unit_test("def add(a, b): return a + b", framework="pytest")
    assert res["status"] == "success"
    assert "pytest" in res["framework"]
    assert "instructions" in res


def test_tool_file_lister():
    files = list_project_files()
    assert isinstance(files, list)
    assert len(files) > 0
    paths = [f["path"] for f in files]
    assert any("auth.py" in p for p in paths)
