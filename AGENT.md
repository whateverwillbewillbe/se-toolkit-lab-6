# Agent Architecture

## Overview

This agent is a simple CLI tool that connects to an LLM (Large Language Model) to answer questions. It forms the foundation for more advanced agent capabilities that will be added in subsequent tasks.

## LLM Provider

**Provider:** Qwen Code API (self-hosted via `qwen-code-oai-proxy`)

**Model:** `qwen3-coder-plus`

**Why this provider:**
- 1000 free requests per day
- Works from Russia without restrictions
- No credit card required
- OpenAI-compatible API endpoint

## Architecture

### Components

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐     ┌─────────────┐
│   User      │────▶│  agent.py    │────▶│  Qwen Code API  │────▶│   LLM       │
│  (CLI arg)  │     │  (CLI tool)  │     │  (on VM)        │     │  (Qwen3)    │
└─────────────┘     └──────────────┘     └─────────────────┘     └─────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ JSON output  │
                    │ {answer,     │
                    │  tool_calls} │
                    └──────────────┘
```

### Data Flow

1. **Input:** User provides a question as a command-line argument
2. **Configuration:** Agent loads API credentials from `.env.agent.secret`
3. **Request:** Agent sends HTTP POST to the LLM API endpoint
4. **Response:** LLM returns an answer
5. **Output:** Agent formats and prints JSON to stdout

## Configuration

### Environment Variables

The agent reads configuration from `.env.agent.secret` in the project root:

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for Qwen Code | `your-api-key` |
| `LLM_API_BASE` | Base URL of the API | `http://<vm-ip>:<port>/v1` |
| `LLM_MODEL` | Model name | `qwen3-coder-plus` |

### Setup

1. Copy the example file:
   ```bash
   cp .env.agent.example .env.agent.secret
   ```

2. Edit `.env.agent.secret` and fill in your values:
   - `LLM_API_KEY`: Get from `~/.qwen/oauth_creds.json` on your VM
   - `LLM_API_BASE`: Your VM's Qwen Code API endpoint
   - `LLM_MODEL`: Use `qwen3-coder-plus` (recommended)

## Usage

### Basic Usage

```bash
uv run agent.py "What does REST stand for?"
```

### Output Format

The agent outputs a single JSON line to stdout:

```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | The LLM's response to the question |
| `tool_calls` | array | Empty for Task 1 (populated in Task 2) |

### Error Handling

- **Missing argument:** Prints usage to stderr, exits with code 1
- **Configuration error:** Prints error to stderr, exits with code 1
- **API error:** Returns error message in `answer` field
- **Timeout (60s):** Returns timeout error in `answer` field

All debug and error messages go to **stderr**. Only the final JSON goes to **stdout**.

## Implementation Details

### Dependencies

- `httpx` - Async HTTP client for API requests
- `pydantic-settings` - Environment variable loading and validation

### Key Functions

| Function | Purpose |
|----------|---------|
| `load_config()` | Load and validate configuration from `.env.agent.secret` |
| `call_llm(question, config)` | Send request to LLM API, return answer |
| `main()` | Entry point: parse args, call LLM, output JSON |

### Code Structure

```
agent.py
├── AgentConfig (class)    - Configuration schema
├── load_config()          - Load config from environment
├── call_llm()             - Make API request
└── main()                 - CLI entry point
```

## Testing

Run the regression test:

```bash
pytest tests/test_agent_task1.py -v
```

The test:
1. Runs `agent.py` as a subprocess with a test question
2. Parses stdout as JSON
3. Asserts `answer` field exists and is non-empty
4. Asserts `tool_calls` field exists and is an empty array

## Future Work (Tasks 2-3)

- **Task 2:** Add tool support (file operations, API queries)
- **Task 3:** Add agentic loop for multi-step reasoning
- Expand system prompt with domain knowledge
- Add conversation history support
