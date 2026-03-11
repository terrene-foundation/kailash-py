# External Runtime Adapters

This guide covers the external runtime adapters that allow Kaizen agents to leverage specialized capabilities from different AI platforms.

## Overview

Kaizen provides a **Runtime Abstraction Layer** that allows autonomous agents to run on different backends. The external adapters delegate execution to specialized platforms while maintaining a consistent Kaizen interface.

### Available Adapters

| Adapter | Provider | Key Capabilities |
|---------|----------|------------------|
| **LocalKaizenAdapter** | Kaizen | Works with ANY LLM, full Kaizen tool registry |
| **ClaudeCodeAdapter** | Anthropic | Claude Code SDK native tools (Read, Write, Bash, etc.) |
| **OpenAICodexAdapter** | OpenAI | Code Interpreter (sandboxed Python), file search |
| **GeminiCLIAdapter** | Google | 1M context, code execution, multi-modal |

## When to Use Each Adapter

### LocalKaizenAdapter (Recommended)

**Use when:**
- You want to work with any LLM provider (OpenAI, Anthropic, Ollama, etc.)
- You need full control over tool definitions
- You want consistent behavior across different LLMs

```python
from kaizen.runtime.adapters import LocalKaizenAdapter
from kaizen.runtime.context import ExecutionContext

adapter = LocalKaizenAdapter(
    config=AutonomousConfig(
        model="gpt-4o",
        max_cycles=100,
    )
)

context = ExecutionContext(task="Analyze this codebase")
result = await adapter.execute(context)
```

### ClaudeCodeAdapter

**Use when:**
- You want Claude Code's native tools (Read, Write, Bash, Glob, Grep, etc.)
- You need deep IDE integration
- You're already using the Claude Code CLI

**Key Feature:** Delegates to Claude Code's full runtime - Claude Code handles everything using its own optimized tools.

```python
from kaizen.runtime.adapters.claude_code import ClaudeCodeAdapter

adapter = ClaudeCodeAdapter(
    working_directory="/path/to/project",
    model="claude-sonnet-4-20250514",
)

context = ExecutionContext(task="Fix the bug in src/main.py")
result = await adapter.execute(context)
print(result.output)
```

### OpenAICodexAdapter

**Use when:**
- You need sandboxed code execution (safer than local bash)
- You want to analyze data with pandas/numpy/matplotlib
- You need to process uploaded files securely

**Key Feature:** Code Interpreter provides a sandboxed Python environment with data science libraries.

```python
from kaizen.runtime.adapters.openai_codex import OpenAICodexAdapter

adapter = OpenAICodexAdapter(
    api_key=os.environ["OPENAI_API_KEY"],
    model="gpt-4o",
    enable_code_interpreter=True,
)

context = ExecutionContext(
    task="Analyze sales.csv and create a visualization"
)
result = await adapter.execute(context)
```

### GeminiCLIAdapter

**Use when:**
- You need very long context (up to 1M tokens)
- You're processing multi-modal content (images, audio, video)
- You want competitive pricing for high-volume tasks

**Key Feature:** 1M token context window for processing large documents.

```python
from kaizen.runtime.adapters.gemini_cli import GeminiCLIAdapter

adapter = GeminiCLIAdapter(
    api_key=os.environ["GOOGLE_API_KEY"],
    model="gemini-1.5-pro",
    enable_code_execution=True,
)

context = ExecutionContext(
    task="Summarize this 500-page document"
)
result = await adapter.execute(context)
```

## Tool Mapping

When you define custom tools in Kaizen format, each adapter converts them to the appropriate format:

### Kaizen Format (OpenAI Function Calling)

```python
kaizen_tool = {
    "type": "function",
    "function": {
        "name": "search_documents",
        "description": "Search through indexed documents",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        }
    }
}
```

### MCP Format (for ClaudeCodeAdapter)

```python
from kaizen.runtime.adapters import MCPToolMapper

mcp_tools = MCPToolMapper.to_mcp_format([kaizen_tool])
# Result: {"name": "search_documents", "description": ..., "inputSchema": {...}}
```

### Gemini Format

```python
from kaizen.runtime.adapters import GeminiToolMapper

gemini_tools = GeminiToolMapper.to_gemini_format([kaizen_tool])
# Result: {"name": "search_documents", ..., "parameters": {"type": "OBJECT", ...}}
```

Note: Gemini uses UPPERCASE types (STRING, OBJECT, ARRAY).

## Adding Custom Tools

### To Claude Code (via MCP)

Claude Code already has native tools. To add custom tools:

```python
adapter = ClaudeCodeAdapter(
    custom_tools=[{
        "type": "function",
        "function": {
            "name": "query_database",  # Custom tool
            "description": "Query the project database",
            "parameters": {"type": "object", "properties": {...}}
        }
    }]
)
```

**Important:** Don't use reserved names (Read, Write, Bash, etc.) - they conflict with Claude Code's native tools.

### To OpenAI Codex

```python
adapter = OpenAICodexAdapter(
    enable_code_interpreter=True,  # Built-in
    custom_tools=[my_custom_tool],  # Your additions
)
```

### To Gemini

```python
adapter = GeminiCLIAdapter(
    enable_code_execution=True,  # Built-in
    custom_tools=[my_custom_tool],  # Your additions
)
```

## Streaming Output

All adapters support streaming:

```python
async for chunk in adapter.stream(context):
    print(chunk, end="", flush=True)
```

## Interruption

```python
# Start execution in background
task = asyncio.create_task(adapter.execute(context))

# Later, interrupt gracefully
success = await adapter.interrupt(
    session_id=context.session_id,
    mode="graceful"  # or "immediate"
)
```

## Error Handling

All adapters return `ExecutionResult` with consistent status:

```python
result = await adapter.execute(context)

if result.status == ExecutionStatus.COMPLETE:
    print(f"Success: {result.output}")
elif result.status == ExecutionStatus.ERROR:
    print(f"Error: {result.error_message}")
elif result.status == ExecutionStatus.TIMEOUT:
    print(f"Timed out after {adapter.timeout_seconds}s")
```

## Health Checks

Check if an adapter's backend is available:

```python
from kaizen.runtime.adapters.claude_code import is_claude_code_available
from kaizen.runtime.adapters.openai_codex import is_openai_available
from kaizen.runtime.adapters.gemini_cli import is_gemini_available

if await is_claude_code_available():
    adapter = ClaudeCodeAdapter()
elif await is_openai_available():
    adapter = OpenAICodexAdapter(api_key="...")
else:
    adapter = LocalKaizenAdapter()  # Fallback
```

## Comparison Table

| Feature | LocalKaizen | ClaudeCode | OpenAICodex | Gemini |
|---------|-------------|------------|-------------|--------|
| Works with any LLM | ✅ | ❌ | ❌ | ❌ |
| Native file access | Via tools | ✅ | Via upload | ❌ |
| Code execution | Via Bash | ✅ Bash | ✅ Python sandbox | ✅ Python sandbox |
| Streaming | ✅ | ✅ | ✅ | ✅ |
| Vision | LLM-dependent | ✅ | ✅ | ✅ |
| Audio | LLM-dependent | ❌ | ❌ | ✅ |
| Max context | LLM-dependent | 200K | 128K | 1M |
| Internet access | Via tools | Via tools | ❌ Sandboxed | ❌ Sandboxed |

## Best Practices

1. **Start with LocalKaizenAdapter** - It's the most flexible and works with any LLM.

2. **Use ClaudeCodeAdapter for IDE tasks** - Its native tools are optimized for code editing.

3. **Use OpenAICodexAdapter for data analysis** - Code Interpreter has pandas, numpy, matplotlib built-in.

4. **Use GeminiCLIAdapter for long documents** - 1M token context handles large files.

5. **Always handle errors** - External services can fail; have fallback strategies.

6. **Set appropriate timeouts** - Different tasks need different time limits.

```python
adapter = OpenAICodexAdapter(
    timeout_seconds=600,  # 10 minutes for data analysis
)
```

## Migration Guide

### From Direct API Calls to Adapters

Before:
```python
from openai import AsyncOpenAI
client = AsyncOpenAI()
response = await client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": task}],
    tools=[...],
)
```

After:
```python
from kaizen.runtime.adapters.openai_codex import OpenAICodexAdapter
adapter = OpenAICodexAdapter(model="gpt-4o")
result = await adapter.execute(ExecutionContext(task=task, tools=[...]))
```

Benefits:
- Consistent interface across providers
- Built-in error handling
- Easy switching between backends
- Integration with Kaizen's RuntimeSelector
