# Agent Architecture

## Overview

This agent is a CLI tool that uses an **agentic loop** with three tools to answer questions by:

1. Reading project documentation (wiki)
2. Analyzing source code
3. Querying the live backend API

The agent can answer wiki questions, system facts, data-dependent queries, and diagnose bugs by combining multiple tools.

## LLM Provider

**Provider:** Qwen Code API (self-hosted via `qwen-code-oai-proxy`)

**Model:** `qwen3-coder-plus`

**Why this provider:**

- 1000 free requests per day
- Works from Russia without restrictions
- No credit card required
- OpenAI-compatible API with function calling support

## Architecture

### Components

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐     ┌─────────────┐
│   User      │────▶│  agent.py    │────▶│  Qwen Code API  │────▶│   LLM       │
│  (CLI arg)  │     │  (Agentic    │     │  (on VM)        │     │  (Qwen3)    │
│             │     │   Loop)      │     │                 │     │             │
└─────────────┘     └──────┬───────┘     └─────────────────┘     └─────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Backend API  │
                    │ (FastAPI)    │
                    └──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ JSON output  │
                    │ {answer,     │
                    │  source,     │
                    │  tool_calls} │
                    └──────────────┘
```

### Data Flow

1. **Input:** User provides a question as a command-line argument
2. **Configuration:** Agent loads API credentials from `.env.agent.secret` and `.env.docker.secret`
3. **Agentic Loop:**
   - Send question + tool definitions to LLM
   - If LLM returns `tool_calls`: execute tools (read_file, list_files, query_api), append results, repeat
   - If LLM returns text answer: extract answer and source, output JSON
4. **Output:** Agent prints JSON with `answer`, `source`, and `tool_calls`

## Configuration

### Environment Variables

The agent reads configuration from **two** environment files:

**`.env.agent.secret` (LLM configuration):**

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for Qwen Code | `your-api-key` |
| `LLM_API_BASE` | Base URL of the LLM API | `http://<vm-ip>:<port>/v1` |
| `LLM_MODEL` | Model name | `qwen3-coder-plus` |

**`.env.docker.secret` (Backend API configuration):**

| Variable | Description | Example |
|----------|-------------|---------|
| `LMS_API_KEY` | API key for backend authentication | `your-lms-api-key` |
| `CADDY_HOST_PORT` | Port for backend API (used to build `AGENT_API_BASE_URL`) | `42002` |

**Optional:**

- `AGENT_API_BASE_URL` - Backend API base URL (default: `http://localhost:42002`)

### Setup

1. Copy example files:

   ```bash
   cp .env.agent.example .env.agent.secret
   cp .env.docker.example .env.docker.secret
   ```

2. Edit `.env.agent.secret`:
   - `LLM_API_KEY`: Get from `~/.qwen/oauth_creds.json` on your VM
   - `LLM_API_BASE`: Your VM's Qwen Code API endpoint
   - `LLM_MODEL`: Use `qwen3-coder-plus` (recommended)

3. Edit `.env.docker.secret`:
   - `LMS_API_KEY`: Your backend API key
   - Other backend configuration

### Important: Two Distinct Keys

| Key | File | Purpose |
|-----|------|---------|
| `LLM_API_KEY` | `.env.agent.secret` | Authenticates with **LLM provider** (Qwen Code) |
| `LMS_API_KEY` | `.env.docker.secret` | Authenticates with **backend API** for `query_api` |

**Never mix these keys.** The autochecker injects different values at runtime.

## Usage

### Basic Usage

```bash
uv run agent.py "How many items are in the database?"
```

### Output Format

The agent outputs a single JSON line to stdout:

```json
{
  "answer": "There are 42 items in the database.",
  "source": "",
  "tool_calls": [
    {
      "tool": "query_api",
      "args": {"method": "GET", "path": "/items/"},
      "result": "{\"status_code\": 200, ...}"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | The LLM's response to the question |
| `source` | string | Source reference (wiki file, source file, or endpoint) |
| `tool_calls` | array | All tool calls made during the agentic loop |

### Tool Call Structure

Each entry in `tool_calls` contains:

| Field | Type | Description |
|-------|------|-------------|
| `tool` | string | Name of the tool |
| `args` | object | Arguments passed to the tool |
| `result` | string | Tool execution result |

## Tools

### read_file

Reads the contents of a file from the project repository.

**Parameters:**

- `path` (string, required): Relative path from project root

**Example:**

```json
{"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}}
```

**Security:**

- Prevents directory traversal attacks (`../`)
- Only reads files within the project directory
- Returns error message for invalid paths
- Limits content to 10,000 characters to avoid token limits

### list_files

Lists files and directories at a given path.

**Parameters:**

- `path` (string, required): Relative directory path from project root

**Example:**

```json
{"tool": "list_files", "args": {"path": "wiki"}}
```

**Security:**

- Prevents directory traversal attacks (`../`)
- Only lists directories within the project directory
- Filters out hidden files and common ignored directories

### query_api

Queries the deployed backend API.

**Parameters:**

- `method` (string, required): HTTP method (GET, POST, PUT, DELETE, PATCH)
- `path` (string, required): API endpoint path
- `body` (string, optional): JSON request body for POST/PUT/PATCH

**Example:**

```json
{"tool": "query_api", "args": {"method": "GET", "path": "/items/"}}
```

**Authentication:**

- Uses `LMS_API_KEY` from `.env.docker.secret`
- Sends `Authorization: Bearer <key>` header

**Returns:**

- JSON string with `status_code`, `headers`, and `body`
- Error message for failures (timeout, connection error, etc.)

**Security:**

- Only queries the configured backend URL
- Validates HTTP method is in allowed list
- Prevents arbitrary URL queries (SSRF protection)

## Agentic Loop

The agentic loop is the core of the agent's reasoning process:

```
1. Send user question + tool definitions to LLM
2. Parse response:
   a. If tool_calls: 
      - Execute each tool (read_file, list_files, or query_api)
      - Append results to conversation as tool messages
      - Go to step 1
   b. If text answer:
      - Extract answer and source
      - Output JSON and exit
3. Maximum 10 tool calls per question
```

### Message Format

The conversation uses the OpenAI message format with tool support:

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After each tool call:
    {"role": "assistant", "content": None, "tool_calls": [...]},
    {"role": "tool", "content": tool_result, "tool_call_id": "..."},
]
```

### System Prompt Strategy

The system prompt instructs the LLM to:

1. **Choose the right tool:**
   - `list_files`/`read_file` for wiki, source code, configuration
   - `query_api` for live data, API behavior, bug diagnosis

2. **For wiki questions:**
   - Explore wiki directory with `list_files`
   - Read relevant files with `read_file`
   - Cite section anchors (e.g., `wiki/git-workflow.md#resolving-merge-conflicts`)

3. **For source code questions:**
   - Find relevant files with `list_files`
   - Read code with `read_file`
   - Extract answer from code

4. **For bug diagnosis:**
   - Reproduce error with `query_api`
   - Read source code with `read_file`
   - Explain root cause

5. **Always cite sources** and respond in the user's language

## Implementation Details

### Dependencies

- `httpx` - Async HTTP client for API requests
- `pydantic-settings` - Environment variable loading and validation
- `re` - Regular expressions for source extraction

### Key Functions

| Function | Purpose |
|----------|---------|
| `AgentConfig.load()` | Load config from both `.env` files |
| `read_file(path)` | Tool: read file contents |
| `list_files(path)` | Tool: list directory contents |
| `query_api(method, path, body, config)` | Tool: query backend API |
| `get_tool_definitions()` | OpenAI tool schemas |
| `execute_tool(name, args, config)` | Tool dispatcher |
| `call_llm_with_tools(messages, config, tools)` | LLM API with tools |
| `extract_source_from_answer(answer, tool_calls)` | Source extraction |
| `run_agentic_loop(question, config)` | Main agentic loop |

### Code Structure

```
agent.py
├── AgentConfig              - Configuration (loads both .env files)
├── ToolResult               - Dataclass for tool results
├── read_file()              - Tool: read file
├── list_files()             - Tool: list directory
├── query_api()              - Tool: query backend
├── is_safe_path()           - Security: path validation
├── get_tool_definitions()   - OpenAI tool schemas (3 tools)
├── execute_tool()           - Tool dispatcher
├── call_llm_with_tools()    - LLM API with tools
├── extract_source_from_answer() - Source extraction
├── run_agentic_loop()       - Main agentic loop
└── main()                   - CLI entry point
```

## Testing

### Running Tests

```bash
pytest tests/test_agent_task1.py tests/test_agent_task2.py tests/test_agent_task3.py -v
```

### Test Coverage

| Test File | Question | Expected |
|-----------|----------|----------|
| `test_agent_task1.py` | "What is 2 + 2?" | Valid JSON with `answer` and `tool_calls` |
| `test_agent_task2.py` #1 | "How do you resolve a merge conflict?" | `read_file` in tool_calls, `wiki/git-workflow.md` in source |
| `test_agent_task2.py` #2 | "What files are in the wiki?" | `list_files` in tool_calls |
| `test_agent_task3.py` #1 | "What framework does the backend use?" | `read_file` in tool_calls, answer contains "FastAPI" |
| `test_agent_task3.py` #2 | "How many items are in the database?" | `query_api` in tool_calls, answer contains a number |

## Benchmark Results

### Local Evaluation

Run the benchmark locally:

```bash
uv run run_eval.py
```

The benchmark tests 10 questions across all categories:

- Wiki lookup (branch protection, SSH)
- System facts (framework, API routers)
- Data queries (item count, status codes)
- Bug diagnosis (ZeroDivisionError, TypeError)
- Reasoning (request lifecycle, ETL idempotency)

### Lessons Learned

1. **Tool descriptions matter:** Initially the LLM didn't use `query_api` for data questions. Adding explicit examples in the tool description ("Use this to get live data like item counts, scores, analytics") improved tool selection.

2. **Error formatting is critical:** Raw HTTP errors confused the LLM. Formatting errors as structured JSON with clear status codes helped the LLM understand API responses.

3. **Content limits prevent truncation:** Large files (like full API responses) were being truncated. Limiting file reads to 10,000 characters ensured the LLM received complete, focused information.

4. **Two .env files require careful loading:** The agent must load LLM config from `.env.agent.secret` and backend config from `.env.docker.secret`. Using `pydantic-settings` with manual merging ensured both files are read correctly.

5. **Source extraction needs fallbacks:** The LLM doesn't always include source references in the answer. Extracting from the last `read_file` call provides a reliable fallback.

6. **Authentication is essential for query_api:** Without the `LMS_API_KEY`, API calls return 401 errors. The agent must read this key from `.env.docker.secret` and include it in the `Authorization` header.

### Final Architecture

The agent successfully handles:

- **Wiki questions** by reading documentation with proper section anchors
- **System facts** by analyzing source code (pyproject.toml, main.py)
- **Data queries** by calling the live API with authentication
- **Bug diagnosis** by combining API error responses with source code analysis

The agentic loop allows multi-step reasoning: the LLM can call `query_api` to reproduce an error, then `read_file` to examine the source, and finally provide a diagnosis with the root cause.

## Error Handling

- **Missing argument:** Prints usage to stderr, exits with code 1
- **Configuration error:** Prints error to stderr, exits with code 1
- **API error:** Returns error message in `answer` field
- **Timeout (60s):** Returns timeout error in `answer` field
- **Max tool calls (10):** Returns partial answer with collected tool results

All debug and error messages go to **stderr**. Only the final JSON goes to **stdout**.

## Future Work

- Add more tools (search_code, run_tests, etc.)
- Implement conversation history for multi-turn dialogs
- Add domain knowledge to system prompt for better reasoning
- Improve source extraction with section anchor detection
- Support streaming responses for long answers
