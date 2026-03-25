# External Runtime Adapters Developer Guide

External Runtime Adapters delegate execution to specialized AI platforms while maintaining a consistent Kaizen interface. This guide covers implementation details and best practices.

## Available Adapters

| Adapter | Provider | Key Capabilities |
|---------|----------|------------------|
| **LocalKaizenAdapter** | Kaizen | Works with ANY LLM, full Kaizen tool registry |
| **ClaudeCodeAdapter** | Anthropic | Claude Code SDK native tools (Read, Write, Bash, etc.) |
| **OpenAICodexAdapter** | OpenAI | Code Interpreter (sandboxed Python), file search |
| **GeminiCLIAdapter** | Google | 1M context, code execution, multi-modal |

## ClaudeCodeAdapter

Delegates to Claude Code's native runtime via the CLI.

### Usage

```python
from kaizen.runtime.adapters.claude_code import ClaudeCodeAdapter

adapter = ClaudeCodeAdapter(
    working_directory="/path/to/project",
    model="claude-sonnet-4-20250514",
    timeout_seconds=600,
)

context = ExecutionContext(task="Fix the bug in src/main.py")
result = await adapter.execute(context)
```

### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `working_directory` | str | cwd | Project directory |
| `model` | str | claude-sonnet-4-20250514 | Model to use |
| `timeout_seconds` | float | 300 | Execution timeout |
| `custom_tools` | List[Dict] | [] | Additional tools |
| `max_turns` | int | None | Max conversation turns |

### Native Tools

Claude Code provides these native tools automatically:

- **Read** - Read file contents
- **Write** - Create/overwrite files
- **Edit** - Edit file sections
- **Bash** - Execute shell commands
- **Glob** - Find files by pattern
- **Grep** - Search file contents
- **LS** - List directory contents
- **WebFetch** - Fetch web content
- **WebSearch** - Search the web
- **Task** - Launch subagents
- **TodoWrite** - Manage todos
- **NotebookEdit** - Edit Jupyter notebooks

### Adding Custom Tools

```python
adapter = ClaudeCodeAdapter(
    custom_tools=[{
        "type": "function",
        "function": {
            "name": "query_database",  # Must NOT conflict with native tools
            "description": "Query the project database",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL query"}
                },
                "required": ["sql"]
            }
        }
    }]
)
```

### Implementation Details

The adapter uses the Claude Code CLI:

```python
async def execute(self, context: ExecutionContext) -> ExecutionResult:
    # Build command
    cmd = ["claude", "--print", "-p", context.task]

    if self.model:
        cmd.extend(["--model", self.model])

    if self.max_turns:
        cmd.extend(["--max-turns", str(self.max_turns)])

    # Execute via subprocess
    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=self.working_directory,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await asyncio.wait_for(
        process.communicate(),
        timeout=self.timeout_seconds
    )

    # Parse and return result
    return ExecutionResult(
        output=stdout.decode(),
        status=ExecutionStatus.COMPLETE if process.returncode == 0 else ExecutionStatus.ERROR,
        runtime_name="claude_code",
    )
```

## OpenAICodexAdapter

Uses OpenAI's Responses API with Code Interpreter capability.

### Usage

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

### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api_key` | str | env | OpenAI API key |
| `model` | str | gpt-4o | Model to use |
| `enable_code_interpreter` | bool | False | Enable Python sandbox |
| `enable_file_search` | bool | False | Enable file search |
| `custom_tools` | List[Dict] | [] | Additional tools |
| `temperature` | float | 0.7 | Sampling temperature |
| `max_output_tokens` | int | 4096 | Max response tokens |
| `timeout_seconds` | float | 300 | Execution timeout |

### Code Interpreter

When enabled, provides a sandboxed Python environment with:

- pandas, numpy, matplotlib
- File upload/download
- Data visualization
- Code execution

```python
adapter = OpenAICodexAdapter(
    enable_code_interpreter=True,
)

context = ExecutionContext(
    task="Create a bar chart of the top 10 products by sales",
    files=["sales_data.csv"]  # Files to upload
)

result = await adapter.execute(context)
# result.files_created contains generated images
```

### Implementation Details

```python
async def execute(self, context: ExecutionContext) -> ExecutionResult:
    await self.ensure_initialized()

    # Build tools list
    tools = []
    if self.enable_code_interpreter:
        tools.append({"type": "code_interpreter"})
    if self.enable_file_search:
        tools.append({"type": "file_search"})
    if self.custom_tools:
        tools.extend(self.custom_tools)

    # Create response
    response = await self._client.responses.create(
        model=self.model,
        input=context.task,
        tools=tools if tools else None,
        temperature=self.temperature,
        max_output_tokens=self.max_output_tokens,
    )

    return ExecutionResult(
        output=self._extract_output(response),
        status=ExecutionStatus.COMPLETE,
        tokens_used=response.usage.total_tokens,
        runtime_name="openai_codex",
    )
```

## GeminiCLIAdapter

Uses Google's Generative AI SDK for Gemini models.

### Usage

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

### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api_key` | str | env | Google AI API key |
| `model` | str | gemini-1.5-pro | Model to use |
| `enable_code_execution` | bool | False | Enable Python execution |
| `custom_tools` | List[Dict] | [] | Additional tools |
| `temperature` | float | 0.7 | Sampling temperature |
| `max_output_tokens` | int | 8192 | Max response tokens |
| `timeout_seconds` | float | 300 | Execution timeout |
| `safety_settings` | Dict | None | Safety configuration |

### Key Feature: 1M Token Context

Gemini 1.5 models support up to 1 million tokens of context:

```python
adapter = GeminiCLIAdapter(
    model="gemini-1.5-pro",  # 1M context
)

# Process very large documents
context = ExecutionContext(
    task="Analyze this entire codebase and identify security vulnerabilities",
    files=["src/**/*.py"]  # Large file set
)
```

### Multi-Modal Support

```python
adapter = GeminiCLIAdapter(
    model="gemini-1.5-pro",
)

# Vision (images)
context = ExecutionContext(
    task="Describe what's in this image",
    files=["screenshot.png"]
)

# Audio (Gemini 1.5+)
context = ExecutionContext(
    task="Transcribe this audio file",
    files=["meeting.mp3"]
)
```

### Implementation Details

```python
async def execute(self, context: ExecutionContext) -> ExecutionResult:
    await self.ensure_initialized()

    # Build tools configuration
    tools = self._build_tools(context)

    # Generate content
    if tools:
        response = await asyncio.to_thread(
            self._generative_model.generate_content,
            context.task,
            tools=tools,
        )
    else:
        response = await asyncio.to_thread(
            self._generative_model.generate_content,
            context.task,
        )

    return ExecutionResult(
        output=self._extract_output(response),
        status=ExecutionStatus.COMPLETE,
        tokens_used=self._extract_token_usage(response),
        runtime_name="gemini_cli",
    )
```

## Streaming Support

All adapters support streaming output:

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

Note: Not all adapters support true interruption:
- **ClaudeCodeAdapter**: Kills subprocess
- **OpenAICodexAdapter**: Cancels request
- **GeminiCLIAdapter**: Limited support (logs warning)

## Health Checks

```python
from kaizen.runtime.adapters.claude_code import is_claude_code_available
from kaizen.runtime.adapters.openai_codex import is_openai_available
from kaizen.runtime.adapters.gemini_cli import is_gemini_available

# Check availability
if await is_claude_code_available():
    print("Claude Code CLI is installed and working")

if await is_openai_available():
    print("OpenAI API is accessible")

if await is_gemini_available():
    print("Gemini API is accessible")
```

## Comparison Table

| Feature | LocalKaizen | ClaudeCode | OpenAICodex | Gemini |
|---------|-------------|------------|-------------|--------|
| Works with any LLM | Yes | No | No | No |
| Native file access | Via tools | Yes | Via upload | No |
| Code execution | Via Bash | Yes (Bash) | Yes (Python) | Yes (Python) |
| Streaming | Yes | Yes | Yes | Yes |
| Vision | LLM-dependent | Yes | Yes | Yes |
| Audio | LLM-dependent | No | No | Yes |
| Max context | LLM-dependent | 200K | 128K | 1M |
| Internet access | Via tools | Via tools | No | No |

## When to Use Each Adapter

### LocalKaizenAdapter (Recommended Default)

- You want to work with any LLM provider
- You need full control over tool definitions
- You want consistent behavior across different LLMs

### ClaudeCodeAdapter

- You want Claude Code's native tools (Read, Write, Bash, etc.)
- You need deep IDE integration
- You're already using the Claude Code CLI

### OpenAICodexAdapter

- You need sandboxed code execution (safer than local bash)
- You want to analyze data with pandas/numpy/matplotlib
- You need to process uploaded files securely

### GeminiCLIAdapter

- You need very long context (up to 1M tokens)
- You're processing multi-modal content (images, audio, video)
- You want competitive pricing for high-volume tasks

## Error Handling

All adapters return consistent `ExecutionResult` with status:

```python
result = await adapter.execute(context)

if result.status == ExecutionStatus.COMPLETE:
    print(f"Success: {result.output}")
elif result.status == ExecutionStatus.ERROR:
    print(f"Error: {result.error_message}")
elif result.status == ExecutionStatus.TIMEOUT:
    print(f"Timed out after {adapter.timeout_seconds}s")
elif result.status == ExecutionStatus.INTERRUPTED:
    print("Execution was interrupted")
```

## Best Practices

1. **Start with LocalKaizenAdapter** - It's the most flexible and works with any LLM
2. **Use ClaudeCodeAdapter for IDE tasks** - Its native tools are optimized for code editing
3. **Use OpenAICodexAdapter for data analysis** - Code Interpreter has pandas, numpy, matplotlib built-in
4. **Use GeminiCLIAdapter for long documents** - 1M token context handles large files
5. **Always handle errors** - External services can fail; have fallback strategies
6. **Set appropriate timeouts** - Different tasks need different time limits

```python
# Good: Appropriate timeout for the task
adapter = OpenAICodexAdapter(
    timeout_seconds=600,  # 10 minutes for data analysis
)

adapter = ClaudeCodeAdapter(
    timeout_seconds=60,  # 1 minute for quick tasks
)
```
