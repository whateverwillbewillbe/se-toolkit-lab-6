#!/usr/bin/env python3
"""
Agent CLI - Task 3: The System Agent

An agent that uses tools (read_file, list_files, query_api) to answer questions
by reading documentation, source code, and querying the live backend API.

Usage:
    uv run agent.py "How many items are in the database?"

Output:
    {
      "answer": "...",
      "source": "...",
      "tool_calls": [...]
    }
"""

import json
import os
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

    # LLM configuration
    llm_api_key: str = ""
    llm_api_base: str = ""
    llm_model: str = "qwen3-coder-plus"

    # Backend API configuration
    lms_api_key: str = ""
    agent_api_base_url: str = "http://localhost:42002"

    class Config:
        # Load from both .env.agent.secret and .env.docker.secret
        env_file = ".env.agent.secret"
        env_file_encoding = "utf-8"

    @classmethod
    def load(cls) -> "AgentConfig":
        """Load configuration from both .env files."""
        # First, try to load .env.docker.secret for LMS_API_KEY
        docker_env = Path(__file__).parent / ".env.docker.secret"
        if docker_env.exists():
            for line in docker_env.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key == "LMS_API_KEY" and value:
                    os.environ["LMS_API_KEY"] = value
                elif key == "CADDY_HOST_PORT" and value:
                    # Default API base URL from Caddy port
                    if not os.environ.get("AGENT_API_BASE_URL"):
                        os.environ["AGENT_API_BASE_URL"] = f"http://localhost:{value}"

        # Then load .env.agent.secret
        agent_env = Path(__file__).parent / ".env.agent.secret"
        if agent_env.exists():
            for line in agent_env.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                # Map old names to new names
                if key == "LLM_API_KEY" and value:
                    os.environ["LLM_API_KEY"] = value
                elif key == "LLM_API_BASE" and value:
                    os.environ["LLM_API_BASE"] = value
                elif key == "LLM_MODEL" and value:
                    os.environ["LLM_MODEL"] = value

        try:
            return cls()
        except Exception as e:
            print(f"Error loading configuration: {e}", file=sys.stderr)
            sys.exit(1)


def load_config() -> AgentConfig:
    """Load agent configuration from environment files."""
    return AgentConfig.load()


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
        content = file_path.read_text(encoding="utf-8")
        # Limit content size to avoid token limits
        max_chars = 10000
        if len(content) > max_chars:
            content = content[:max_chars] + "\n... [truncated]"
        return content
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


def query_api(
    method: str, path: str, body: str | None = None, config: AgentConfig | None = None
) -> str:
    """
    Query the deployed backend API.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API endpoint path
        body: Optional JSON request body
        config: Agent configuration (for API key and base URL)

    Returns:
        JSON string with status_code and response body, or error message
    """
    if config is None:
        config = load_config()

    # Validate method
    allowed_methods = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
    if method.upper() not in allowed_methods:
        return f"Error: Invalid HTTP method '{method}'. Allowed: {', '.join(allowed_methods)}"

    # Build URL
    base_url = config.agent_api_base_url.rstrip("/")
    url = f"{base_url}{path}"

    # Prepare headers
    headers = {}
    if config.lms_api_key:
        headers["Authorization"] = f"Bearer {config.lms_api_key}"

    # Prepare request
    try:
        with httpx.Client(timeout=30.0) as client:
            print(f"Querying API: {method} {url}", file=sys.stderr)

            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            elif method.upper() == "POST":
                json_body = json.loads(body) if body else None
                response = client.post(url, headers=headers, json=json_body)
            elif method.upper() == "PUT":
                json_body = json.loads(body) if body else None
                response = client.put(url, headers=headers, json=json_body)
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers)
            elif method.upper() == "PATCH":
                json_body = json.loads(body) if body else None
                response = client.patch(url, headers=headers, json=json_body)
            else:
                response = client.request(method, url, headers=headers, data=body)

            # Return response as JSON
            result = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response.text,
            }

            # Try to parse body as JSON for cleaner output
            try:
                result["body_json"] = response.json()
            except json.JSONDecodeError, ValueError:
                pass

            return json.dumps(result, indent=2)

    except httpx.TimeoutException:
        return f"Error: API request timed out (30s)"
    except httpx.ConnectError as e:
        return f"Error: Cannot connect to API at {url}: {e}"
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP error {e.response.status_code}: {e.response.text}"
    except httpx.RequestError as e:
        return f"Error: Request failed: {e}"
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON body: {e}"
    except Exception as e:
        return f"Error: Unexpected error: {e}"


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
                "description": "Read the contents of a file from the project repository. Use this to read wiki documentation, source code files, or configuration files.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path from project root (e.g., 'wiki/git-workflow.md', 'backend/app/main.py')",
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
                "description": "List files and directories in a directory. Use this to explore the project structure, find API routers, or discover wiki files.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative directory path from project root (e.g., 'wiki', 'backend/app/routers')",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_api",
                "description": "Query the deployed backend API. Use this to get live data from the system (item counts, scores, analytics), check API behavior (status codes, error responses), or diagnose bugs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "description": "HTTP method (GET, POST, PUT, DELETE, PATCH)",
                            "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                        },
                        "path": {
                            "type": "string",
                            "description": "API endpoint path (e.g., '/items/', '/analytics/completion-rate', '/analytics/top-learners')",
                        },
                        "body": {
                            "type": "string",
                            "description": "JSON request body (optional, for POST/PUT/PATCH requests)",
                        },
                    },
                    "required": ["method", "path"],
                },
            },
        },
    ]


def execute_tool(tool_name: str, args: dict[str, Any], config: AgentConfig) -> str:
    """
    Execute a tool by name with given arguments.

    Args:
        tool_name: Name of the tool to execute
        args: Tool arguments
        config: Agent configuration

    Returns:
        Tool result as string
    """
    print(f"Executing tool: {tool_name}({args})", file=sys.stderr)

    if tool_name == "read_file":
        return read_file(args.get("path", ""))
    elif tool_name == "list_files":
        return list_files(args.get("path", ""))
    elif tool_name == "query_api":
        return query_api(
            args.get("method", "GET"),
            args.get("path", ""),
            args.get("body"),
            config,
        )
    else:
        return f"Error: Unknown tool '{tool_name}'"


# =============================================================================
# System Prompt
# =============================================================================

SYSTEM_PROMPT = """You are a system agent that answers questions by reading documentation, source code, and querying the live backend API.

You have access to three tools:
1. list_files - List files in a directory (explore project structure)
2. read_file - Read contents of a file (wiki, source code, configuration)
3. query_api - Query the live backend API (get data, check behavior, diagnose bugs)

When to use each tool:
- Use list_files/read_file for: wiki documentation, source code analysis, configuration files, Docker files
- Use query_api for: live data (item counts, scores, analytics), API behavior (status codes, error responses), bug diagnosis

For bug diagnosis questions:
1. First use query_api to reproduce the error
2. Then use read_file to examine the source code
3. Explain the root cause based on both the error and code

For wiki questions:
1. Use list_files to explore the wiki directory
2. Use read_file to read relevant wiki files
3. Find the specific section that answers the question

For source code questions:
1. Use list_files to find relevant source files
2. Use read_file to read the code
3. Extract the answer from the code

Source references:
- For wiki: wiki/filename.md#section-anchor (anchors are lowercase with hyphens)
- For source code: path/to/file.py
- For API queries: mention the endpoint (e.g., GET /items/)

Always cite your source. If you cannot find the answer, say so honestly.
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
    if not config.llm_api_base or not config.llm_api_key:
        raise ValueError("LLM_API_BASE and LLM_API_KEY must be configured")

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


def extract_source_from_answer(
    answer: str, tool_calls_log: list[dict[str, Any]]
) -> str:
    """
    Extract source reference from the LLM answer or tool calls.

    Args:
        answer: LLM response text
        tool_calls_log: List of tool calls made

    Returns:
        Source reference string
    """
    # Pattern: wiki/something.md#anchor or wiki/something.md
    pattern = r"wiki/[\w-]+\.md(?:#[\w-]+)?"
    matches = re.findall(pattern, answer)

    if matches:
        return matches[-1]  # Return last match (most likely the main source)

    # Try to infer from last read_file call
    if tool_calls_log:
        last_read = None
        for tc in reversed(tool_calls_log):
            if tc["tool"] == "read_file":
                last_read = tc
                break

        if last_read:
            path = last_read["args"].get("path", "")
            if path.startswith("wiki/") or path.startswith("backend/"):
                return path

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

        try:
            response = call_llm_with_tools(messages, config, tools)
        except Exception as e:
            print(f"Error calling LLM: {e}", file=sys.stderr)
            return {
                "answer": f"Error: Failed to call LLM: {e}",
                "source": "",
                "tool_calls": tool_calls_log,
            }

        # Check for tool calls
        tool_calls = response.get("tool_calls", [])

        if not tool_calls:
            # No tool calls - LLM provided final answer
            print("LLM provided final answer (no tool calls)", file=sys.stderr)
            answer = response.get("content") or ""

            # Extract source
            source = extract_source_from_answer(answer, tool_calls_log)

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
            tool_result = execute_tool(tool_name, tool_args, config)

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
    print(f"LLM API base: {config.llm_api_base}", file=sys.stderr)
    print(f"Agent API base URL: {config.agent_api_base_url}", file=sys.stderr)

    # Run agentic loop
    output = run_agentic_loop(question, config)

    # Output JSON to stdout (only valid JSON, no extra whitespace)
    print(json.dumps(output, separators=(",", ":")))

    # Exit successfully
    sys.exit(0)


if __name__ == "__main__":
    main()
