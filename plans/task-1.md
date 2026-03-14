# Task 1 Plan: Call an LLM from Code

## LLM Provider and Model

**Provider:** Qwen Code API (self-hosted on VM via qwen-code-oai-proxy)

**Model:** `qwen3-coder-plus`

**Reasons for this choice:**
- 1000 free requests per day
- Works from Russia without restrictions
- No credit card required
- OpenAI-compatible API endpoint
- Already set up on the VM

## Architecture

### Components

1. **Environment Configuration** (`.env.agent.secret`)
   - `LLM_API_KEY` - API key for Qwen Code
   - `LLM_API_BASE` - Base URL of the Qwen Code API (e.g., `http://<vm-ip>:<port>/v1`)
   - `LLM_MODEL` - Model name (`qwen3-coder-plus`)

2. **Agent CLI** (`agent.py`)
   - Reads command-line argument (the question)
   - Loads environment variables from `.env.agent.secret`
   - Makes HTTP POST request to the LLM API
   - Parses the response
   - Outputs JSON to stdout

### Data Flow

```
User input (CLI arg) 
    → agent.py 
    → HTTP POST /v1/chat/completions 
    → Qwen Code API 
    → Response 
    → JSON output {answer, tool_calls}
```

### Implementation Details

**Dependencies:**
- `httpx` - async HTTP client (already in pyproject.toml)
- `pydantic-settings` - for loading environment variables (already in pyproject.toml)
- `sys` - for stdout/stderr handling

**Key Functions:**
1. `load_config()` - Load LLM configuration from environment
2. `call_llm(question)` - Send request to LLM API, return response
3. `main()` - Entry point, parse args, call LLM, format output

**Error Handling:**
- HTTP errors → return error message in answer field
- Timeout (60 seconds) → return timeout error
- Missing config → exit with error message to stderr

**Output Format:**
```json
{"answer": "<llm response>", "tool_calls": []}
```

All debug/logging output goes to `stderr`. Only the final JSON goes to `stdout`.

## Testing Strategy

**Single regression test:**
- Run `agent.py` as subprocess with a test question
- Parse stdout as JSON
- Assert `answer` field exists and is non-empty
- Assert `tool_calls` field exists and is an empty array

## Files to Create

1. `plans/task-1.md` - This plan
2. `.env.agent.secret` - Environment configuration (copy from example)
3. `agent.py` - Main agent CLI
4. `AGENT.md` - Documentation
5. `tests/test_agent_task1.py` - Regression test
