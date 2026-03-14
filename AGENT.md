# Agent Architecture

## Overview

This agent is a CLI tool that uses an **agentic loop** with tools to navigate the project wiki and answer questions with source references. Unlike a simple chatbot, this agent can:

1. **Use tools** - `read_file` and `list_files` to explore the codebase
2. **Reason iteratively** - Make multiple tool calls to gather information
3. **Cite sources** - Reference the specific wiki section that answers the question

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
└─────────────┘     └──────────────┘     └─────────────────┘     └─────────────┘
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
2. **Configuration:** Agent loads API credentials from `.env.agent.secret`
3. **Agentic Loop:**
   - Send question + tool definitions to LLM
   - If LLM returns `tool_calls`: execute tools, append results, repeat
   - If LLM returns text answer: extract answer and source, output JSON
4. **Output:** Agent prints JSON with `answer`, `source`, and `tool_calls`

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
uv run agent.py "How do you resolve a merge conflict?"
```

### Output Format

The agent outputs a single JSON line to stdout:

```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "..."
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | The LLM's response to the question |
| `source` | string | Wiki section reference (e.g., `wiki/git-workflow.md#section`) |
| `tool_calls` | array | All tool calls made during the agentic loop |

### Tool Call Structure

Each entry in `tool_calls` contains:

| Field | Type | Description |
|-------|------|-------------|
| `tool` | string | Name of the tool (`read_file` or `list_files`) |
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

## Agentic Loop

The agentic loop is the core of the agent's reasoning process:

```
1. Send user question + tool definitions to LLM
2. Parse response:
   a. If tool_calls: 
      - Execute each tool
      - Append results to conversation
      - Go to step 1
   b. If text answer:
      - Extract answer and source
      - Output JSON and exit
3. Maximum 10 tool calls per question
```

### Message Format

The conversation uses the OpenAI message format:

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After each tool call:
    {"role": "assistant", "content": None, "tool_calls": [...]},
    {"role": "tool", "content": tool_result, "tool_call_id": "..."},
]
```

### System Prompt

The system prompt instructs the LLM to:

1. Use `list_files` to explore the wiki directory structure
2. Use `read_file` to read relevant wiki files
3. Find the specific section that answers the question
4. Include the source reference in format: `wiki/filename.md#section-anchor`
5. Respond in the same language as the user's question

## Implementation Details

### Dependencies

- `httpx` - Async HTTP client for API requests
- `pydantic-settings` - Environment variable loading and validation
- `re` - Regular expressions for source extraction

### Key Functions

| Function | Purpose |
|----------|---------|
| `load_config()` | Load configuration from `.env.agent.secret` |
| `read_file(path)` | Tool: read file contents |
| `list_files(path)` | Tool: list directory contents |
| `get_tool_definitions()` | OpenAI function-calling schemas |
| `execute_tool(name, args)` | Dispatch tool calls |
| `call_llm_with_tools(messages, config, tools)` | LLM API call with tool support |
| `run_agentic_loop(question, config)` | Main loop: call LLM, execute tools |
| `extract_source_from_answer(answer)` | Extract source reference from LLM text |

### Code Structure

```
agent.py
├── AgentConfig           - Configuration class
├── ToolResult            - Dataclass for tool results
├── read_file()           - Tool: read file
├── list_files()          - Tool: list directory
├── is_safe_path()        - Security: path validation
├── get_tool_definitions() - OpenAI tool schemas
├── execute_tool()        - Tool dispatcher
├── call_llm_with_tools() - LLM API with tools
├── extract_source_from_answer() - Source extraction
├── run_agentic_loop()    - Main agentic loop
└── main()                - CLI entry point
```

## Testing

### Running Tests

```bash
pytest tests/test_agent_task1.py tests/test_agent_task2.py -v
```

### Test Coverage

| Test | Question | Expected |
|------|----------|----------|
| Task 1 | "What is 2 + 2?" | Valid JSON with `answer` and `tool_calls` |
| Task 2 #1 | "How do you resolve a merge conflict?" | `read_file` in tool_calls, `wiki/git-workflow.md` in source |
| Task 2 #2 | "What files are in the wiki?" | `list_files` in tool_calls |

## Error Handling

- **Missing argument:** Prints usage to stderr, exits with code 1
- **Configuration error:** Prints error to stderr, exits with code 1
- **API error:** Returns error message in `answer` field
- **Timeout (60s):** Returns timeout error in `answer` field
- **Max tool calls (10):** Returns partial answer with collected tool results

All debug and error messages go to **stderr**. Only the final JSON goes to **stdout**.

## Future Work (Task 3)

- Add more tools (query_api, search_code, etc.)
- Implement conversation history
- Add domain knowledge to system prompt
- Support multi-turn conversations
- Improve source extraction accuracy
