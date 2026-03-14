"""
Regression tests for Task 1: Call an LLM from Code

Tests verify that agent.py:
1. Runs successfully as a subprocess
2. Outputs valid JSON to stdout
3. Contains required fields: answer and tool_calls
"""

import json
import subprocess
import sys
from pathlib import Path


def run_agent_basic(question: str) -> dict:
    """
    Run agent.py with a question and return parsed output.

    Args:
        question: The question to ask the agent

    Returns:
        Parsed JSON output from agent
    """
    # Path to agent.py (project root)
    project_root = Path(__file__).parent.parent
    agent_path = project_root / "agent.py"

    # Run agent.py as subprocess
    result = subprocess.run(
        [sys.executable, "-m", "uv", "run", str(agent_path), question],
        capture_output=True,
        text=True,
        timeout=120,
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


def test_agent_outputs_valid_json():
    """
    Test that agent.py outputs valid JSON with required fields.

    This test:
    1. Runs agent.py as a subprocess with a simple question
    2. Parses stdout as JSON
    3. Asserts 'answer' field exists and is non-empty
    4. Asserts 'tool_calls' field exists and is an array
    """
    # Test question
    question = "What is 2 + 2?"

    output = run_agent_basic(question)

    # Assert 'answer' field exists and is non-empty
    assert "answer" in output, "Output missing 'answer' field"
    assert isinstance(output["answer"], str), "'answer' field must be a string"
    assert len(output["answer"]) > 0, "'answer' field is empty"

    # Assert 'tool_calls' field exists and is an array
    assert "tool_calls" in output, "Output missing 'tool_calls' field"
    assert isinstance(output["tool_calls"], list), "'tool_calls' field must be an array"

    # Assert 'source' field exists (Task 2 requirement, but good to check)
    assert "source" in output, "Output missing 'source' field"
    assert isinstance(output["source"], str), "'source' field must be a string"


if __name__ == "__main__":
    test_agent_outputs_valid_json()
    print("All Task 1 tests passed!")
