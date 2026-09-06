import pytest
from app.config import settings
from app.rag.ingestion import index_codebase
from app.rag.retriever import get_collection


@pytest.fixture(scope="session", autouse=True)
def setup_test_codebase():
    """Ensure the sample project is indexed into ChromaDB before running any tests."""
    coll = get_collection()
    if coll.count() == 0:
        index_codebase(settings.SAMPLE_PROJECT_DIR)
