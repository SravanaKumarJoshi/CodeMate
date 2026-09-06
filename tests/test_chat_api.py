from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_chat_api_authentication_search():
    response = client.post("/api/chat", json={"message": "Where is authentication implemented?"})
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "CODE_SEARCH"
    assert "search_code" in data["tools_used"]
    assert len(data["sources"]) > 0
    assert "auth.py" in data["answer"].lower() or any("auth.py" in s for s in data["sources"])


def test_chat_api_login_explanation():
    response = client.post("/api/chat", json={"message": "Explain how login works in this application."})
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "CODE_EXPLANATION"
    assert len(data["answer"]) > 50


def test_chat_api_test_generation():
    response = client.post("/api/chat", json={"message": "Generate unit tests for the login function."})
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "TEST_GENERATION"
    assert "generate_unit_test" in data["tools_used"]
    assert "pytest" in data["answer"].lower() or "test" in data["answer"].lower()


def test_chat_api_401_bug_analysis():
    response = client.post("/api/chat", json={"message": "Why could the login endpoint return a 401 error?"})
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "BUG_ANALYSIS"
    assert "401" in data["answer"]


def test_chat_empty_query_rejected():
    response = client.post("/api/chat", json={"message": ""})
    assert response.status_code == 422
