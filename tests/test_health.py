from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "CodeMate"
    assert "ml_model" in data
    assert data["ml_model"]["status"] == "ready"
    assert "vectordb" in data
