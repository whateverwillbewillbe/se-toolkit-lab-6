"""
Regression tests for Task 3: The System Agent

Tests verify that agent.py:
1. Uses appropriate tools (read_file, query_api) for system questions
2. Outputs valid JSON with required fields: answer, source, tool_calls
3. Correctly identifies sources for different question types
"""

import json
import subprocess
import sys
from pathlib import Path


def run_agent(question: str, timeout: int = 120) -> dict:
    """
    Run agent.py with a question and return parsed output.

    Args:
        question: The question to ask the agent
        timeout: Timeout in seconds (default 120 for agentic loop)

    Returns:
        Parsed JSON output from agent

    Raises:
        AssertionError: If agent fails or outputs invalid JSON
    """
    # Path to agent.py (project root)
    project_root = Path(__file__).parent.parent
    agent_path = project_root / "agent.py"

    # Run agent.py as subprocess using uv
    # Use "uv run agent.py" directly (uv handles the Python interpreter)
    result = subprocess.run(
        ["uv", "run", str(agent_path), question],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    # Print stderr for debugging (won't affect test result)
    if result.stderr:
        print(f"Agent stderr:\n{result.stderr}", file=sys.stderr)

    # Assert exit code is 0
    assert result.returncode == 0, (
        f"Agent exited with code {result.returncode}: {result.stderr}"
    )

    # Parse stdout as JSON
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(f"Agent output is not valid JSON: {result.stdout}") from e

    return output


def validate_output(output: dict) -> None:
    """
    Validate that output has required fields with correct types.

    Args:
        output: Parsed agent output
    """
    # Assert 'answer' field exists and is non-empty
    assert "answer" in output, "Output missing 'answer' field"
    assert isinstance(output["answer"], str), "'answer' field must be a string"
    assert len(output["answer"]) > 0, "'answer' field is empty"

    # Assert 'source' field exists
    assert "source" in output, "Output missing 'source' field"
    assert isinstance(output["source"], str), "'source' field must be a string"

    # Assert 'tool_calls' field exists and is a list
    assert "tool_calls" in output, "Output missing 'tool_calls' field"
    assert isinstance(output["tool_calls"], list), "'tool_calls' field must be an array"


def test_framework_question():
    """
    Test that agent uses read_file to answer a framework question.

    Expected behavior:
    - Agent uses list_files or read_file to explore backend structure
    - Agent reads pyproject.toml or backend/app/main.py
    - Answer contains "FastAPI"
    - Source references a backend file
    """
    question = "What framework does the backend use?"

    output = run_agent(question)
    validate_output(output)

    # Check that tool_calls is not empty (agent should use tools)
    assert len(output["tool_calls"]) > 0, "Agent should use tools for this question"

    # Check that read_file was used
    tool_names = [tc.get("tool") for tc in output["tool_calls"]]
    assert "read_file" in tool_names, "Agent should use read_file tool"

    # Check that answer contains FastAPI
    answer_lower = output["answer"].lower()
    assert "fastapi" in answer_lower, (
        f"Answer should mention FastAPI, got: {output['answer']}"
    )

    # Check that source references backend or pyproject.toml
    source = output["source"].lower()
    assert "backend" in source or "pyproject" in source, (
        f"Source should reference backend file, got: {output['source']}"
    )


def test_query_api_question():
    """
    Test that agent uses query_api to answer a data question.

    Expected behavior:
    - Agent uses query_api to get data from backend
    - tool_calls contains query_api with GET method
    - Answer contains a number (item count, etc.)
    """
    question = "How many items are in the database?"

    output = run_agent(question)
    validate_output(output)

    # Check that tool_calls is not empty
    assert len(output["tool_calls"]) > 0, "Agent should use tools for this question"

    # Check that query_api was used
    tool_names = [tc.get("tool") for tc in output["tool_calls"]]
    assert "query_api" in tool_names, "Agent should use query_api tool"

    # Check that query_api was called with GET method
    query_api_calls = [
        tc for tc in output["tool_calls"] if tc.get("tool") == "query_api"
    ]
    methods = [tc.get("args", {}).get("method", "") for tc in query_api_calls]
    assert any(m.upper() == "GET" for m in methods), (
        f"query_api should be called with GET method, got: {methods}"
    )

    # Check that answer contains a number
    import re

    numbers = re.findall(r"\d+", output["answer"])
    assert len(numbers) > 0, f"Answer should contain a number, got: {output['answer']}"


if __name__ == "__main__":
    print("Running Task 3 tests...")
    test_framework_question()
    print("✓ test_framework_question passed")
    test_query_api_question()
    print("✓ test_query_api_question passed")
    print("All Task 3 tests passed!")
