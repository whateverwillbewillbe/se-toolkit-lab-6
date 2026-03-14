#!/usr/bin/env python3
"""
Agent CLI - Task 1: Call an LLM from Code

A simple CLI agent that takes a question, sends it to an LLM,
and returns a structured JSON answer.

Usage:
    uv run agent.py "What does REST stand for?"

Output:
    {"answer": "Representational State Transfer.", "tool_calls": []}
"""

import json
import sys
from pathlib import Path

import httpx
from pydantic_settings import BaseSettings


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


def call_llm(question: str, config: AgentConfig) -> str:
    """
    Send a question to the LLM and return the answer.

    Args:
        question: The user's question
        config: Agent configuration with API details

    Returns:
        The LLM's answer as a string
    """
    print(f"Sending question to LLM: {question}", file=sys.stderr)

    url = f"{config.llm_api_base}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.llm_api_key}",
    }
    payload = {
        "model": config.llm_model,
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant. Answer questions concisely and accurately.",
            },
            {"role": "user", "content": question},
        ],
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            print(f"POST {url}", file=sys.stderr)
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()

            data = response.json()
            answer = data["choices"][0]["message"]["content"]

            print(f"Received response from LLM", file=sys.stderr)
            return answer

    except httpx.TimeoutException:
        print("Error: LLM request timed out (60s)", file=sys.stderr)
        return "Error: Request timed out. Please try again."
    except httpx.HTTPStatusError as e:
        print(f"Error: HTTP error {e.response.status_code}: {e.response.text}", file=sys.stderr)
        return f"Error: API returned status code {e.response.status_code}"
    except httpx.RequestError as e:
        print(f"Error: Request failed: {e}", file=sys.stderr)
        return f"Error: Could not connect to LLM API"
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"Error: Failed to parse LLM response: {e}", file=sys.stderr)
        return "Error: Invalid response from LLM"


def main() -> None:
    """Main entry point for the agent CLI."""
    # Parse command-line arguments
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py <question>", file=sys.stderr)
        print("Example: uv run agent.py \"What does REST stand for?\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]
    print(f"Agent received question: {question}", file=sys.stderr)

    # Load configuration
    config = load_config()
    print(f"Using model: {config.llm_model}", file=sys.stderr)
    print(f"API base: {config.llm_api_base}", file=sys.stderr)

    # Call LLM and get answer
    answer = call_llm(question, config)

    # Prepare output
    output = {
        "answer": answer,
        "tool_calls": [],
    }

    # Output JSON to stdout (only valid JSON, no extra whitespace)
    print(json.dumps(output, separators=(",", ":")))

    # Exit successfully
    sys.exit(0)


if __name__ == "__main__":
    main()
