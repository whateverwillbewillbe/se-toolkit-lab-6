"""
Regression tests for Task 2: The Documentation Agent

Tests verify that agent.py:
1. Uses tools (read_file, list_files) to answer questions
2. Outputs valid JSON with required fields: answer, source, tool_calls
3. Correctly cites wiki sources
"""

import json
import subprocess
import sys
from pathlib import Path


def run_agent(question: str) -> dict:
    """
    Run agent.py with a question and return parsed output.

    Args:
        question: The question to ask the agent

    Returns:
        Parsed JSON output from agent

    Raises:
        AssertionError: If agent fails or outputs invalid JSON
    """
    # Path to agent.py (project root)
    project_root = Path(__file__).parent.parent
    agent_path = project_root / "agent.py"

    # Run agent.py as subprocess
    result = subprocess.run(
        [sys.executable, "-m", "uv", "run", str(agent_path), question],
        capture_output=True,
        text=True,
        timeout=120,  # Longer timeout for agentic loop
    )

    # Print stderr for debugging (won't affect test result)
    if result.stderr:
        print(f"Agent stderr:\n{result.stderr}", file=sys.stderr)

    # Assert exit code is 0
    assert result.returncode == 0, f"Agent exited with code {result.returncode}: {result.stderr}"

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


def test_merge_conflict_question():
    """
    Test that agent uses read_file to answer a merge conflict question.

    Expected behavior:
    - Agent uses list_files to explore wiki directory
    - Agent uses read_file to read git-workflow.md
    - Source references wiki/git-workflow.md
    """
    question = "How do you resolve a merge conflict?"

    output = run_agent(question)
    validate_output(output)

    # Check that tool_calls is not empty (agent should use tools)
    assert len(output["tool_calls"]) > 0, "Agent should use tools for this question"

    # Check that read_file was used
    tool_names = [tc.get("tool") for tc in output["tool_calls"]]
    assert "read_file" in tool_names, "Agent should use read_file tool"

    # Check that source references git-workflow.md
    source = output["source"].lower()
    assert "git-workflow" in source or "git" in source, (
        f"Source should reference git-workflow.md, got: {output['source']}"
    )


def test_wiki_listing_question():
    """
    Test that agent uses list_files to answer a wiki listing question.

    Expected behavior:
    - Agent uses list_files to explore wiki directory
    - tool_calls contains list_files with path "wiki"
    """
    question = "What files are in the wiki?"

    output = run_agent(question)
    validate_output(output)

    # Check that tool_calls is not empty
    assert len(output["tool_calls"]) > 0, "Agent should use tools for this question"

    # Check that list_files was used
    tool_names = [tc.get("tool") for tc in output["tool_calls"]]
    assert "list_files" in tool_names, "Agent should use list_files tool"

    # Check that list_files was called with wiki path
    list_files_calls = [tc for tc in output["tool_calls"] if tc.get("tool") == "list_files"]
    wiki_paths = [tc.get("args", {}).get("path", "") for tc in list_files_calls]
    assert any("wiki" in path for path in wiki_paths), (
        f"list_files should be called with wiki path, got: {wiki_paths}"
    )


if __name__ == "__main__":
    print("Running Task 2 tests...")
    test_merge_conflict_question()
    print("✓ test_merge_conflict_question passed")
    test_wiki_listing_question()
    print("✓ test_wiki_listing_question passed")
    print("All Task 2 tests passed!")
