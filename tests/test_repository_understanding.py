"""
Tests for CodeMate Repository Understanding Workflow.
Verifies that broad queries (such as 'What is my project?', 'What does this project do?',
'Explain my project', 'Give me a complete overview', etc.) return synthesized,
grounded natural-language explanations rather than raw retrieval dumps.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.agents.graph import run_agent
from app.agents.repo_analyzer import is_broad_repo_query, get_repo_query_subtype

client = TestClient(app)

REQUIRED_QUERIES = [
    "What is my project?",
    "What does my project do?",
    "Explain my project.",
    "Give me a complete overview.",
    "What are the main features?",
    "What technology stack does this project use?",
    "Explain the architecture.",
    "Explain the data flow."
]


def test_broad_repo_query_classification():
    """Verify that broad questions are correctly identified by the analyzer."""
    for q in REQUIRED_QUERIES:
        assert is_broad_repo_query(q) is True, f"Failed to classify '{q}' as broad repo query"

    # Verify query subtypes
    assert get_repo_query_subtype("What is my project?") == "overview"
    assert get_repo_query_subtype("What does my project do?") == "overview"
    assert get_repo_query_subtype("Explain my project.") == "overview"
    assert get_repo_query_subtype("Give me a complete overview.") == "overview"
    assert get_repo_query_subtype("What are the main features?") == "features"
    assert get_repo_query_subtype("What technology stack does this project use?") == "tech_stack"
    assert get_repo_query_subtype("Explain the architecture.") == "architecture"
    assert get_repo_query_subtype("Explain the data flow.") == "data_flow"


@pytest.mark.parametrize("query", REQUIRED_QUERIES)
def test_sample_project_understanding_execution(query):
    """
    Verifies that broad questions on the sample project execute through LangGraph,
    inspect the repository, and return rich natural-language explanations.
    """
    result = run_agent(query, repository_id="repo_sample_project")
    answer = result.get("answer", "")

    # Must produce a substantial, synthesized explanation
    assert len(answer) > 100
    assert "ShopFlow" in answer or "FastAPI" in answer or "SQLite" in answer or "architecture" in answer.lower()

    # Must NOT be a raw list of file definitions or uninterpreted dump
    assert "The codebase contains relevant definitions and implementations addressing this query:" not in answer

    # Verify tools were exercised
    assert len(result.get("tools_used", [])) > 0
    assert "list_project_files" in result.get("tools_used", [])

    # Sources must be present
    assert len(result.get("sources", [])) > 0


@pytest.mark.parametrize("query", REQUIRED_QUERIES)
def test_polysaccharide_project_understanding_execution(query):
    """
    Verifies that broad questions on repo_4375d3f634 (PolysaccharideProject)
    produce domain-accurate synthesized explanations covering the Android app,
    polysaccharide properties, data flow, and technologies.
    """
    result = run_agent(query, repository_id="repo_4375d3f634")
    answer = result.get("answer", "")

    # Must produce a substantial explanation
    assert len(answer) > 150

    # Must mention core domain evidence
    assert any(term in answer.lower() for term in ["polysaccharide", "biopolymer", "android", "screening", "dataset"])

    # Must NOT be a raw retrieval dump
    assert "The codebase contains relevant definitions and implementations addressing this query:" not in answer

    # Verify tools and sources
    assert "list_project_files" in result.get("tools_used", [])
    assert len(result.get("sources", [])) > 0


def test_chat_endpoint_broad_query():
    """Verifies that the /api/chat endpoint returns structured repository explanations."""
    response = client.post("/api/chat", json={"message": "What is my project?"})
    assert response.status_code == 200

    data = response.json()
    assert "answer" in data
    assert "### Project Overview" in data["answer"]
    assert "### Technology Stack" in data["answer"]
    assert "### Sources" in data["answer"]
    assert len(data["sources"]) > 0
    assert "list_project_files" in data["tools_used"]
