# Task 3 Plan: The System Agent

## Overview

Task 3 extends the Documentation Agent (Task 2) with a new tool `query_api` that allows the agent to query the deployed backend API. This enables the agent to answer:

1. **Static system facts** - framework, ports, status codes (from source code)
2. **Data-dependent queries** - item count, scores, analytics (from live API)
3. **Bug diagnosis** - error analysis by combining API responses with source code reading

## Tool Definition: query_api

### Schema

```json
{
    "type": "function",
    "function": {
        "name": "query_api",
        "description": "Query the deployed backend API. Use this to get live data from the system.",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "description": "HTTP method (GET, POST, etc.)",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"]
                },
                "path": {
                    "type": "string",
                    "description": "API endpoint path (e.g., /items/, /analytics/completion-rate)"
                },
                "body": {
                    "type": "string",
                    "description": "JSON request body (optional, for POST/PUT)"
                }
            },
            "required": ["method", "path"]
        }
    }
}
```

### Implementation

```python
def query_api(method: str, path: str, body: str | None = None) -> str:
    """
    Query the deployed backend API.
    
    - Uses LMS_API_KEY for authentication
    - Reads AGENT_API_BASE_URL from environment (default: http://localhost:42002)
    - Returns JSON with status_code and response body
    """
```

## Authentication

### Two Distinct Keys

| Key | File | Purpose |
|-----|------|---------|
| `LLM_API_KEY` | `.env.agent.secret` | Authenticates with LLM provider (Qwen Code) |
| `LMS_API_KEY` | `.env.docker.secret` | Authenticates with backend API for `query_api` |

**Important:** Never mix these keys. The autochecker injects different values at runtime.

### Environment Variables

The agent reads from two files:

**`.env.agent.secret`:**

- `LLM_API_KEY` - LLM provider API key
- `LLM_API_BASE` - LLM API endpoint URL
- `LLM_MODEL` - Model name

**`.env.docker.secret`:**

- `LMS_API_KEY` - Backend API authentication key

**Optional:**

- `AGENT_API_BASE_URL` - Backend API base URL (default: `http://localhost:42002`)

## System Prompt Update

The system prompt must guide the LLM to choose the right tool:

```
You are a system agent with access to three types of tools:

1. list_files - Explore directory structure
2. read_file - Read file contents (wiki, source code)
3. query_api - Query the live backend API

When to use each tool:
- Use list_files/read_file for: wiki documentation, source code analysis, configuration files
- Use query_api for: live data (item counts, scores), API behavior (status codes), error diagnosis

For bug diagnosis:
1. First use query_api to reproduce the error
2. Then use read_file to examine the source code
3. Explain the root cause based on both the error and code

Always cite your source. For API queries, mention the endpoint. For code, mention the file path.
```

## Agentic Loop Changes

The loop remains the same as Task 2, but now with 3 tools:

```
1. Send question + all tool definitions to LLM
2. If tool_calls: execute tools (read_file, list_files, or query_api), append results, repeat
3. If text answer: extract answer and source, output JSON
4. Maximum 10 tool calls
```

## Benchmark Questions Analysis

| # | Question | Tool(s) Required | Strategy |
|---|----------|------------------|----------|
| 0 | Protect a branch (wiki) | read_file | Read wiki/git-workflow.md |
| 1 | SSH connection (wiki) | read_file | Read wiki/vm.md or wiki/ssh.md |
| 2 | Web framework (source) | read_file | Read backend/app/main.py or pyproject.toml |
| 3 | API router modules | list_files | List backend/app/routers/ |
| 4 | Items in database | query_api | GET /items/ |
| 5 | Status code without auth | query_api | GET /items/ without header |
| 6 | /analytics/completion-rate bug | query_api, read_file | Query API, then read source |
| 7 | /analytics/top-learners bug | query_api, read_file | Query API, then read source |
| 8 | Request lifecycle | read_file | Read docker-compose.yml, Dockerfile |
| 9 | ETL idempotency | read_file | Read backend/app/etl.py |

## Implementation Structure

```
agent.py
├── AgentConfig              - Updated with LMS_API_KEY, AGENT_API_BASE_URL
├── read_file()              - Existing tool
├── list_files()             - Existing tool
├── query_api()              - NEW: API query tool
├── get_tool_definitions()   - Updated with query_api schema
├── execute_tool()           - Updated dispatcher
├── call_llm_with_tools()    - Unchanged
├── run_agentic_loop()       - Unchanged (now with 3 tools)
└── main()                   - Updated to load both .env files
```

## Security Considerations

- `query_api` must only query the configured backend URL
- No arbitrary URL queries (prevent SSRF attacks)
- Validate HTTP method is in allowed list
- Sanitize path (prevent path traversal)

## Testing Strategy

**Test 1: Framework question**

- Question: "What framework does the backend use?"
- Expected: `read_file` in tool_calls, answer contains "FastAPI"

**Test 2: Database query**

- Question: "How many items are in the database?"
- Expected: `query_api` in tool_calls, answer contains a number > 0

## Benchmark Workflow

1. Run `uv run run_eval.py` to test all 10 questions
2. On failure, read the feedback hint
3. Fix the issue (improve prompt, fix tool, add error handling)
4. Re-run until all pass
5. Document lessons learned in AGENT.md

## Files to Modify/Create

1. `plans/task-3.md` - This plan (NEW)
2. `agent.py` - Add query_api tool, update config loading (UPDATE)
3. `AGENT.md` - Document query_api and benchmark results (UPDATE)
4. `tests/test_agent_task3.py` - Add 2 new tests (NEW)

## Initial Hypotheses

**Potential issues:**

1. LLM may not know when to use query_api vs read_file
2. API authentication may fail if LMS_API_KEY not loaded correctly
3. Error responses from API may need better formatting for LLM

**Iteration strategy:**

- Start with basic implementation
- Run benchmark, identify first failure
- Fix one issue at a time
- Document each iteration in this plan

## Benchmark Results

### Initial Test

**Command:** `uv run agent.py "What framework does the backend use?"`

**Result:** ✓ PASSED

The agent successfully:

1. Used `list_files` to explore `backend/` directory
2. Used `list_files` to explore `backend/app/` directory
3. Used `read_file` to read `backend/app/main.py`
4. Extracted "FastAPI" from the code
5. Cited source: `backend/app/main.py`

**Output:**

```json
{
  "answer": "The backend uses the **FastAPI** framework...",
  "source": "backend/app/main.py",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "backend"}, ...},
    {"tool": "list_files", "args": {"path": "backend/app"}, ...},
    {"tool": "read_file", "args": {"path": "backend/app/main.py"}, ...}
  ]
}
```

### Iteration Notes

1. **Fixed deprecation warning:** Changed from class-based Config to ConfigDict for pydantic-settings compatibility.

2. **Content limiting:** Added 10,000 character limit to file reads to prevent token overflow.

3. **Two .env files:** Implemented manual loading of both `.env.agent.secret` and `.env.docker.secret` to ensure LLM_API_KEY and LMS_API_KEY are both available.

4. **API base URL:** Default to `http://localhost:42002` (from CADDY_HOST_PORT) for query_api.

### Next Steps

1. Run full benchmark: `uv run run_eval.py`
2. Fix any failing questions
3. Document lessons learned in AGENT.md
