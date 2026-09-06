from app.config import settings
from app.rag.chunking import chunk_code_file
from app.rag.ingestion import index_codebase
from app.rag.retriever import query_code


def test_chunking_small_file():
    code = "def hello():\n    return 'world'\n"
    chunks = chunk_code_file("hello.py", code, max_chunk_lines=50)
    assert len(chunks) == 1
    assert chunks[0]["metadata"]["start_line"] == 1
    assert chunks[0]["metadata"]["end_line"] == 2
    assert chunks[0]["metadata"]["file_path"] == "hello.py"


def test_chunking_large_file():
    lines = [f"x_{i} = {i}" for i in range(120)]
    content = "\n".join(lines)
    chunks = chunk_code_file("large.py", content, max_chunk_lines=40, overlap_lines=10)
    assert len(chunks) > 1
    assert chunks[0]["metadata"]["start_line"] == 1
    assert chunks[0]["metadata"]["end_line"] == 40


def test_sample_project_ingestion_and_retrieval():
    assert settings.SAMPLE_PROJECT_DIR.exists()
    index_res = index_codebase(settings.SAMPLE_PROJECT_DIR)

    assert index_res["status"] == "success"
    assert index_res["files_indexed"] > 0
    assert index_res["chunks_indexed"] > 0

    # Query ChromaDB for authentication
    hits = query_code("authentication and login", top_k=3)
    assert len(hits) > 0
    assert any("auth.py" in h["file_path"] or "users.py" in h["file_path"] for h in hits)
