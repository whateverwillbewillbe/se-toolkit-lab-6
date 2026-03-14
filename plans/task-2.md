# Task 2 Plan: The Documentation Agent

## Overview

Task 2 transforms the simple CLI from Task 1 into a true **agent** by adding:
1. **Tools** - `read_file` and `list_files` for navigating the project wiki
2. **Agentic loop** - iterative tool calling until the LLM provides a final answer
3. **Source tracking** - identifying which wiki section answers the question

## Tool Definitions

### read_file

**Purpose:** Read contents of a file from the project repository.

**Schema:**
```python
{
    "name": "read_file",
    "description": "Read a file from the project repository",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path from project root"}
        },
        "required": ["path"]
    }
}
```

**Implementation:**
- Use `Path.read_text()` to read file contents
- Security: validate path doesn't contain `../` traversal
- Return error message if file doesn't exist

### list_files

**Purpose:** List files and directories at a given path.

**Schema:**
```python
{
    "name": "list_files",
    "description": "List files and directories in a directory",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative directory path from project root"}
        },
        "required": ["path"]
    }
}
```

**Implementation:**
- Use `Path.iterdir()` to list directory contents
- Security: validate path doesn't escape project root
- Return newline-separated list of entries

## Path Security

Both tools must prevent directory traversal attacks:

```python
def is_safe_path(base: Path, requested: Path) -> bool:
    """Ensure requested path is within base directory."""
    try:
        # Resolve to absolute paths
        base_resolved = base.resolve()
        requested_resolved = (base / requested).resolve()
        # Check if requested is under base
        return requested_resolved.is_relative_to(base_resolved)
    except ValueError:
        return False
```

## Agentic Loop

The loop continues until the LLM provides a text answer or we hit the limit:

```
1. Send user question + tool definitions to LLM
2. Parse response:
   - If tool_calls: execute each tool, append results, go to step 1
   - If text answer: extract answer + source, return JSON
3. Maximum 10 tool calls per question
```

**Message format:**
```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After each tool call:
    {"role": "assistant", "content": None, "tool_calls": [...]},
    {"role": "tool", "content": tool_result, "tool_call_id": "..."},
]
```

## System Prompt Strategy

The system prompt will instruct the LLM to:

1. Use `list_files` to discover wiki directory structure
2. Use `read_file` to read relevant wiki files
3. Find the specific section that answers the question
4. Include the source reference in format: `wiki/filename.md#section-anchor`
5. Only provide final answer after gathering sufficient information

**Example system prompt:**
```
You are a documentation agent. You have access to two tools:
- list_files: List files in a directory
- read_file: Read contents of a file

To answer questions:
1. First use list_files to explore the wiki directory
2. Then use read_file to read relevant files
3. Find the exact section that answers the question
4. Include the source as: wiki/filename.md#section-name

Always cite your source. If you don't find the answer, say so.
```

## Output Format

```json
{
    "answer": "The answer text from LLM",
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

## Implementation Structure

```
agent.py
├── AgentConfig          - Configuration class
├── ToolResult           - Dataclass for tool execution results
├── read_file()          - Tool implementation
├── list_files()         - Tool implementation
├── get_tool_definitions() - OpenAI function-calling schemas
├── execute_tool()       - Dispatch tool calls
├── call_llm_with_tools() - LLM API call with tool support
├── run_agentic_loop()   - Main loop: call LLM, execute tools
└── main()               - CLI entry point
```

## Testing Strategy

**Test 1: Merge conflict question**
- Question: "How do you resolve a merge conflict?"
- Expected: `read_file` in tool_calls, `wiki/git-workflow.md` in source

**Test 2: Wiki listing question**
- Question: "What files are in the wiki?"
- Expected: `list_files` in tool_calls

## Files to Modify/Create

1. `plans/task-2.md` - This plan (NEW)
2. `agent.py` - Add tools and agentic loop (UPDATE)
3. `AGENT.md` - Document new architecture (UPDATE)
4. `tests/test_agent_task1.py` - Keep existing test
5. `tests/test_agent_task2.py` - Add 2 new tests (NEW)
