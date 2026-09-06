"""
Test Generator Tool for CodeMate.
Synthesizes structured unit test scaffolding and test cases based on retrieved code.
IMPORTANT: Generated tests are returned strictly as text and NEVER automatically executed.
"""

from typing import Dict, Any


def generate_unit_test(
    code: str,
    framework: str = "pytest",
    test_type: str = "unit"
) -> Dict[str, Any]:
    """
    Prepares test generation specifications and template scaffolding for target code snippet.

    Args:
        code: Source code of function/class to be tested.
        framework: Testing framework (pytest or unittest).
        test_type: Scope of tests (unit, integration, edge cases).

    Returns:
        Dict with status, framework, target_code, and generation guidelines.
    """
    return {
        "status": "success",
        "framework": framework,
        "test_type": test_type,
        "target_code": code,
        "instructions": (
            f"Generate comprehensive {framework} test cases covering:\n"
            "- Happy path inputs and expected outputs\n"
            "- Boundary conditions, edge cases, and empty inputs\n"
            "- Error handling, invalid credentials/parameters, and exception assertions (pytest.raises)\n"
            "- Mocking external dependencies, database sessions, and network calls\n"
            "- Note: Generated tests are strictly for developer reference and not executed automatically."
        )
    }
