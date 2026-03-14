#!/usr/bin/env python3
"""
Agent CLI - Task 2: The Documentation Agent

An agent that uses tools (read_file, list_files) to navigate the project wiki
and answer questions with source references.

Usage:
    uv run agent.py "How do you resolve a merge conflict?"

Output:
    {
      "answer": "...",
      "source": "wiki/git-workflow.md#resolving-merge-conflicts",
      "tool_calls": [...]
    }
"""

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from pydantic_settings import BaseSettings


# =============================================================================
# Configuration
# =============================================================================


class AgentConfig(BaseSettings):
    """Configuration for the agent, loaded from environment variables."""

    llm_api_key: str
    llm_api_base: str
    llm_model: str = "qwen3-coder-plus"

    class Config:
        env_file = Path(__file__).parent / ".env.agent.secret"
        env_file_encoding = "utf-8"


def load_config() -> AgentConfig:
    """Load agent configuration from environment file."""
    try:
        return AgentConfig()
    except Exception as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        sys.exit(1)


# =============================================================================
# Tool Definitions
# =============================================================================


@dataclass
class ToolResult:
    """Result of executing a tool."""

    tool: str
    args: dict[str, Any]
    result: str


def is_safe_path(base: Path, requested: Path) -> bool:
    """
    Ensure requested path is within base directory.

    Prevents directory traversal attacks (../).
    """
    try:
        base_resolved = base.resolve()
        requested_resolved = (base / requested).resolve()
        return requested_resolved.is_relative_to(base_resolved)
    except ValueError:
        return False


def read_file(path: str) -> str:
    """
    Read a file from the project repository.

    Args:
        path: Relative path from project root

    Returns:
        File contents or error message
    """
    project_root = Path(__file__).parent

    # Validate path
    requested = Path(path)
    if not is_safe_path(project_root, requested):
        return f"Error: Access denied - path '{path}' is outside project directory"

    file_path = project_root / requested

    if not file_path.exists():
        return f"Error: File not found: {path}"

    if not file_path.is_file():
        return f"Error: Not a file: {path}"

    try:
        return file_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading file: {e}"


def list_files(path: str) -> str:
    """
    List files and directories at a given path.

    Args:
        path: Relative directory path from project root

    Returns:
        Newline-separated listing or error message
    """
    project_root = Path(__file__).parent

    # Validate path
    requested = Path(path)
    if not is_safe_path(project_root, requested):
        return f"Error: Access denied - path '{path}' is outside project directory"

    dir_path = project_root / requested

    if not dir_path.exists():
        return f"Error: Directory not found: {path}"

    if not dir_path.is_dir():
        return f"Error: Not a directory: {path}"

    try:
        entries = sorted(dir_path.iterdir())
        # Filter out hidden files and common ignored directories
        names = [
            e.name
            for e in entries
            if not e.name.startswith(".")
            and e.name not in ("node_modules", "__pycache__", ".venv", ".direnv")
        ]
        return "\n".join(names)
    except Exception as e:
        return f"Error listing directory: {e}"


# =============================================================================
# Tool Schemas for LLM Function Calling
# =============================================================================


def get_tool_definitions() -> list[dict[str, Any]]:
    """
    Get tool definitions in OpenAI function-calling format.

    Returns:
        List of tool schemas for the LLM API
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file from the project repository. Use this to read wiki documentation or source code files.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files and directories in a directory. Use this to explore the project structure.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative directory path from project root (e.g., 'wiki')",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
    ]


def execute_tool(tool_name: str, args: dict[str, Any]) -> str:
    """
    Execute a tool by name with given arguments.

    Args:
        tool_name: Name of the tool to execute
        args: Tool arguments

    Returns:
        Tool result as string
    """
    print(f"Executing tool: {tool_name}({args})", file=sys.stderr)

    if tool_name == "read_file":
        return read_file(args.get("path", ""))
    elif tool_name == "list_files":
        return list_files(args.get("path", ""))
    else:
        return f"Error: Unknown tool '{tool_name}'"


# =============================================================================
# System Prompt
# =============================================================================

SYSTEM_PROMPT = """You are a documentation agent that answers questions by reading the project wiki.

You have access to two tools:
1. list_files - List files in a directory
2. read_file - Read contents of a file

To answer questions:
1. First use list_files to explore the wiki directory structure
2. Then use read_file to read relevant wiki files
3. Find the specific section that answers the question
4. Include the source reference in format: wiki/filename.md#section-anchor

Section anchors are lowercase with hyphens instead of spaces (e.g., "resolving-merge-conflicts").

Always cite your source. If you cannot find the answer in the wiki, say so honestly.
Respond in the same language as the user's question."""


# =============================================================================
# LLM Communication with Tool Support
# =============================================================================


def call_llm_with_tools(
    messages: list[dict[str, Any]], config: AgentConfig, tools: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Call the LLM API with tool support.

    Args:
        messages: Conversation history
        config: Agent configuration
        tools: Tool definitions

    Returns:
        Parsed LLM response
    """
    url = f"{config.llm_api_base}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.llm_api_key}",
    }
    payload = {
        "model": config.llm_model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
    }

    print(f"POST {url}", file=sys.stderr)

    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    return data["choices"][0]["message"]


def extract_source_from_answer(answer: str) -> str:
    """
    Extract source reference from the LLM answer.

    Looks for patterns like: wiki/filename.md#section or wiki/filename.md

    Args:
        answer: LLM response text

    Returns:
        Source reference string
    """
    # Pattern: wiki/something.md#anchor or wiki/something.md
    pattern = r"wiki/[\w-]+\.md(?:#[\w-]+)?"
    matches = re.findall(pattern, answer)

    if matches:
        return matches[-1]  # Return last match (most likely the main source)

    return ""


def find_section_anchor(content: str, topic: str) -> str:
    """
    Find a section anchor in file content based on topic keywords.

    Args:
        content: File contents
        topic: Topic to search for

    Returns:
        Section anchor string (e.g., "resolving-merge-conflicts")
    """
    # Look for markdown headers that might contain the topic
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("#") and topic.lower() in line.lower():
            # Convert header to anchor format
            header_text = line.lstrip("#").strip()
            anchor = (
                header_text.lower().replace(" ", "-").replace(",", "").replace(":", "")
            )
            return anchor

    return ""


# =============================================================================
# Agentic Loop
# =============================================================================


def run_agentic_loop(question: str, config: AgentConfig) -> dict[str, Any]:
    """
    Run the agentic loop: call LLM, execute tools, repeat until answer.

    Args:
        question: User's question
        config: Agent configuration

    Returns:
        Final output with answer, source, and tool_calls
    """
    max_tool_calls = 10
    tool_calls_log: list[dict[str, Any]] = []

    # Initialize conversation
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    tools = get_tool_definitions()

    print(f"Starting agentic loop for question: {question}", file=sys.stderr)

    while len(tool_calls_log) < max_tool_calls:
        # Call LLM
        print(f"--- Iteration {len(tool_calls_log) + 1} ---", file=sys.stderr)
        response = call_llm_with_tools(messages, config, tools)

        # Check for tool calls
        tool_calls = response.get("tool_calls", [])

        if not tool_calls:
            # No tool calls - LLM provided final answer
            print("LLM provided final answer (no tool calls)", file=sys.stderr)
            answer = response.get("content", "")

            # Try to extract source from answer
            source = extract_source_from_answer(answer)

            # If no source found, try to infer from last tool result
            if not source and tool_calls_log:
                last_tool = tool_calls_log[-1]
                if last_tool["tool"] == "read_file":
                    path = last_tool["args"].get("path", "")
                    if path.startswith("wiki/"):
                        source = path

            return {
                "answer": answer,
                "source": source,
                "tool_calls": tool_calls_log,
            }

        # Execute tool calls
        for tool_call in tool_calls:
            tool_id = tool_call["id"]
            function = tool_call["function"]
            tool_name = function["name"]

            try:
                tool_args = json.loads(function["arguments"])
            except json.JSONDecodeError:
                tool_args = {}

            # Execute tool
            tool_result = execute_tool(tool_name, tool_args)

            # Log tool call
            tool_calls_log.append(
                {
                    "tool": tool_name,
                    "args": tool_args,
                    "result": tool_result,
                }
            )

            # Append assistant message with tool call
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [tool_call],
                }
            )

            # Append tool result
            messages.append(
                {
                    "role": "tool",
                    "content": tool_result,
                    "tool_call_id": tool_id,
                }
            )

            print(
                f"Tool {tool_name} executed, result length: {len(tool_result)}",
                file=sys.stderr,
            )

    # Max tool calls reached
    print("Max tool calls (10) reached", file=sys.stderr)
    return {
        "answer": "I reached the maximum number of tool calls (10) without finding a complete answer.",
        "source": "",
        "tool_calls": tool_calls_log,
    }


# =============================================================================
# Main Entry Point
# =============================================================================


def main() -> None:
    """Main entry point for the agent CLI."""
    # Parse command-line arguments
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py <question>", file=sys.stderr)
        print(
            'Example: uv run agent.py "How do you resolve a merge conflict?"',
            file=sys.stderr,
        )
        sys.exit(1)

    question = sys.argv[1]
    print(f"Agent received question: {question}", file=sys.stderr)

    # Load configuration
    config = load_config()
    print(f"Using model: {config.llm_model}", file=sys.stderr)
    print(f"API base: {config.llm_api_base}", file=sys.stderr)

    # Run agentic loop
    output = run_agentic_loop(question, config)

    # Output JSON to stdout (only valid JSON, no extra whitespace)
    print(json.dumps(output, separators=(",", ":")))

    # Exit successfully
    sys.exit(0)


if __name__ == "__main__":
    main()
