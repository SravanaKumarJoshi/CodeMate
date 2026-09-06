from app.ml.classifier import classify_intent


def test_classifier_core_scenarios():
    test_cases = [
        ("Where is authentication implemented?", "CODE_SEARCH"),
        ("Explain how authentication works in this project", "CODE_EXPLANATION"),
        ("Why could the login endpoint return a 401 error?", "BUG_ANALYSIS"),
        ("Generate unit tests for this function", "TEST_GENERATION"),
        ("What database is being used in this project?", "ARCHITECTURE"),
        ("What is CodeMate?", "GENERAL_QUERY"),
    ]

    for query, expected_intent in test_cases:
        res = classify_intent(query)
        assert res["intent"] == expected_intent, f"Query '{query}' predicted {res['intent']}, expected {expected_intent}"
        assert 0.0 <= res["confidence"] <= 1.0
        assert isinstance(res["probabilities"], dict)


def test_classifier_empty_string():
    res = classify_intent("")
    assert res["intent"] == "GENERAL_QUERY"
    assert res["confidence"] == 1.0


def test_classifier_whitespace():
    res = classify_intent("   \n\t  ")
    assert res["intent"] == "GENERAL_QUERY"
