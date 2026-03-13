# Kaizen + Enterprise-App Integration Guide

## Executive Summary

Kaizen provides **full Claude Code parity** for autonomous agent workflows, enabling developers to build enterprise applications using **Claude Code, Codex, Gemini CLI, or local Kaizen** with consistent capabilities.

**Key Capability Matrix:**

| Capability | Claude Code | Kaizen (LocalKaizenAdapter) | Status |
|------------|-------------|----------------------------|--------|
| File Operations | 5 tools | 7 tools (Read, Write, Edit, Glob, Grep, List, Exists) | **Exceeds** |
| Bash Execution | Native | Sandboxed with security patterns | **Parity** |
| Web Access | 2 tools | 2 tools (WebSearch, WebFetch) | **Parity** |
| Plan Mode | Enter/Exit | EnterPlanMode/ExitPlanMode | **Parity** |
| Task Management | TodoWrite | TodoWrite with session awareness | **Parity** |
| Notebook Editing | NotebookEdit | NotebookEdit (code/markdown cells) | **Parity** |
| User Questions | AskUserQuestion | AskUserQuestion with multi-select | **Parity** |
| Process Management | KillShell, TaskOutput | KillShell, TaskOutput | **Parity** |
| Agent Spawning | Task tool | Task/Skill tools | **Parity** |
| LLM Support | Claude only | **Any LLM** (OpenAI, Anthropic, Ollama, Azure, Google) | **Exceeds** |
| Memory | Session-based | Hierarchical 3-tier (Hot/Warm/Cold) | **Exceeds** |

---

## Part 1: .claude Directory Structure for Claude Code

### Where to Place Files

For **Claude Code** to work autonomously with your project, create the following structure:

```
your-project/
├── CLAUDE.md                     # REQUIRED: Project instructions
├── .claude/
│   ├── settings.local.json       # Local Claude Code settings
│   ├── agents/                   # Subagent/specialist definitions
│   │   ├── README.md
│   │   └── my-specialist.md      # Custom specialist
│   ├── skills/                   # Domain knowledge blocks
│   │   ├── 01-my-domain/
│   │   │   ├── SKILL.md          # Skill manifest
│   │   │   └── patterns.md       # Skill content
│   │   └── ...
│   └── guides/                   # Context engineering
│       └── my-guide.md
└── src/
    └── ... your code
```

### CLAUDE.md Format (Required)

```markdown
# Project Name

## Important Directives
1. Use Kailash SDK frameworks (DataFlow, Nexus, Kaizen)
2. Always use specialist subagents for framework questions
3. Load environment variables from .env before ANY operation

## Specialized Subagents
- **kaizen-specialist**: AI agent implementation
- **nexus-specialist**: Multi-channel platform
- **dataflow-specialist**: Database operations
- **mcp-specialist**: MCP server development

## Essential Patterns
```python
# Your critical code patterns here
from kaizen import Agent
agent = Agent(model="gpt-4", agent_type="autonomous")
result = await agent.run("task")
```

## Critical Rules
- ALWAYS: `runtime.execute(workflow.build())`
- NEVER: Skip .env loading
- DataFlow: Never manually set created_at/updated_at
```

### settings.local.json

```json
{
  "model": "claude-sonnet-4-20250514",
  "maxTokens": 16384,
  "permissions": {
    "allow": [
      "Bash(pytest*)",
      "Bash(git *)",
      "Write(src/**)",
      "Edit(src/**)"
    ],
    "deny": [
      "Bash(rm -rf /)",
      "Write(.env*)"
    ]
  }
}
```

---

## Part 2: Using Kaizen with Any LLM (LocalKaizenAdapter)

### Basic Usage

```python
from kaizen import Agent

# Zero-config - works immediately with defaults
agent = Agent(model="gpt-4")
result = await agent.run("Analyze the codebase structure")
print(result.text)
```

### Autonomous Mode with TAOD Loop

```python
from kaizen import Agent

agent = Agent(
    model="gpt-4",
    agent_type="autonomous",    # Enables TAOD loop
    memory_turns=50,            # Remember last 50 turns
    tools="all",                # All 19 native tools
    budget_limit_usd=10.0,      # Cost control
    enable_checkpointing=True,  # Resume capability
)

# Autonomous execution - agent decides when complete
result = await agent.run(
    "Refactor the user authentication module to use JWT tokens"
)
```

### Using Specific Runtime Adapters

```python
from kaizen.runtime.adapters import (
    LocalKaizenAdapter,      # Any LLM provider
    ClaudeCodeAdapter,       # Claude Code SDK
    GeminiCLIAdapter,        # Google Gemini
    OpenAICodexAdapter,      # OpenAI Codex
)
from kaizen.runtime import ExecutionContext, RuntimeSelector

# Direct adapter usage
adapter = LocalKaizenAdapter(
    config=AutonomousConfig(
        model="gpt-4o",
        max_cycles=100,
        planning_strategy=PlanningStrategy.PEV,
    )
)

context = ExecutionContext(task="Your task here")
result = await adapter.execute(context)

# Or use RuntimeSelector for automatic selection
selector = RuntimeSelector()
adapter = selector.select(task="complex coding task")
result = await adapter.execute(context)
```

---

## Part 3: 19 Native Tools Available

### File Tools (7)

```python
from kaizen.tools.native import (
    ReadFileTool,        # Read file with pagination
    WriteFileTool,       # Write with auto-directory creation
    EditFileTool,        # String replacement editing
    GlobTool,            # Pattern file discovery
    GrepTool,            # Regex content search
    ListDirectoryTool,   # Directory listing
    FileExistsTool,      # Path existence check
)
```

### Bash Tool (1)

```python
from kaizen.tools.native import BashTool

# Sandboxed execution with security patterns
tool = BashTool()
result = await tool.execute(
    command="pytest tests/ -v",
    timeout=120000,           # 2 min timeout
    run_in_background=False,  # Optional background execution
)
```

### Search Tools (2)

```python
from kaizen.tools.native import WebSearchTool, WebFetchTool

# Web search
search = WebSearchTool()
results = await search.execute(query="Python async patterns")

# Fetch and process URL
fetch = WebFetchTool()
content = await fetch.execute(
    url="https://docs.python.org/3/library/asyncio.html",
    prompt="Extract the key concepts"
)
```

### Agent Tools (2)

```python
from kaizen.tools.native import TaskTool, SkillTool

# Spawn subagent
task = TaskTool()
result = await task.execute(
    prompt="Analyze database schema",
    subagent_type="dataflow-specialist",
    run_in_background=True,
)

# Invoke skill
skill = SkillTool()
result = await skill.execute(
    skill="12-testing-strategies",
    args="unit tests for UserService"
)
```

### Interaction Tools (3)

```python
from kaizen.tools.native import (
    TodoWriteTool,
    AskUserQuestionTool,
    NotebookEditTool,
)

# Task management
todo = TodoWriteTool()
await todo.execute(todos=[
    {"content": "Implement auth", "status": "in_progress", "activeForm": "Implementing auth"},
    {"content": "Write tests", "status": "pending", "activeForm": "Writing tests"},
])

# User questions
ask = AskUserQuestionTool(user_callback=my_callback)
answer = await ask.execute(questions=[{
    "question": "Which database?",
    "header": "Database",
    "options": [
        {"label": "PostgreSQL", "description": "Production-ready"},
        {"label": "SQLite", "description": "Local development"},
    ],
    "multiSelect": False,
}])

# Notebook editing
notebook = NotebookEditTool()
await notebook.execute(
    notebook_path="/path/to/notebook.ipynb",
    cell_id="cell-001",
    new_source="print('Updated!')",
    cell_type="code",
    edit_mode="replace",
)
```

### Planning Tools (2)

```python
from kaizen.tools.native import PlanModeManager

manager = PlanModeManager()
enter_tool = manager.create_enter_tool()
exit_tool = manager.create_exit_tool()

# Enter planning mode
await enter_tool.execute()

# ... planning phase ...

# Exit with permissions
await exit_tool.execute(
    allowedPrompts=[
        {"tool": "Bash", "prompt": "run tests"},
        {"tool": "Write", "prompt": "update config"},
    ]
)
```

### Process Tools (2)

```python
from kaizen.tools.native import ProcessManager, KillShellTool, TaskOutputTool

pm = ProcessManager()
kill_tool = KillShellTool(process_manager=pm)
output_tool = TaskOutputTool(process_manager=pm)

# Get background task output
result = await output_tool.execute(
    task_id="shell-001",
    block=True,       # Wait for completion
    timeout=30000,    # 30 second max wait
)

# Kill if needed
await kill_tool.execute(shell_id="shell-001")
```

---

## Part 4: Multi-LLM Routing

### Automatic Model Selection

```python
from kaizen.llm.routing import LLMRouter, TaskAnalyzer, RoutingRule

# Create router with capabilities
router = LLMRouter(
    strategy="balanced",  # cost + quality + specialty
)

# Add routing rules
router.add_rule(RoutingRule(
    name="code-tasks",
    condition=lambda ctx: "code" in ctx.task.lower(),
    target_model="claude-sonnet-4",
    priority=10,
))

# Analyze and route
analyzer = TaskAnalyzer()
analysis = analyzer.analyze("Implement a REST API endpoint")
decision = router.route(context, analysis)
print(f"Selected model: {decision.model}")  # e.g., claude-sonnet-4
```

### Fallback Chains

```python
from kaizen.llm.routing import FallbackRouter

fallback = FallbackRouter(
    primary="gpt-4o",
    fallbacks=["claude-sonnet-4", "gpt-4-turbo", "ollama/llama3"],
    on_error="next_fallback",  # or "retry", "fail"
)

result = await fallback.route_with_fallback(context)
```

---

## Part 5: Memory System (3-Tier Hierarchical)

### Hot/Warm/Cold Architecture

```python
from kaizen.memory.providers import HierarchicalMemory

memory = HierarchicalMemory(
    hot_config={
        "max_entries": 100,      # Recent, fast access (<1ms)
        "ttl_seconds": 3600,     # 1 hour hot storage
    },
    warm_config={
        "backend": "dataflow",   # Database storage (10-50ms)
        "connection": "postgresql://...",
    },
    cold_config={
        "backend": "archive",    # Long-term storage (100ms+)
        "connection": "s3://bucket/archive",
    },
)

# Automatic tier promotion/demotion
await memory.store("key", {"data": "important"}, importance=0.9)
item = await memory.retrieve("key")  # Auto-promotes to hot if accessed
```

### Learning Memory

```python
from kaizen.memory.learning import (
    PatternRecognition,
    PreferenceLearning,
    ErrorCorrection,
    MemoryPromotion,
)

# Agent learns from execution patterns
pattern_learner = PatternRecognition()
patterns = await pattern_learner.detect_patterns(execution_history)

# Learns user preferences
pref_learner = PreferenceLearning()
preferences = await pref_learner.update(user_feedback)
```

---

## Part 6: Streaming for Enterprise-App

### 10 Event Types

```python
from kaizen.runtime.streaming import StreamingExecutor

executor = StreamingExecutor()

async for event in executor.execute_stream(context):
    match event.type:
        case "started":
            print(f"Execution started: {event.execution_id}")
        case "thinking":
            print(f"Agent reasoning: {event.content}")
        case "message":
            print(f"Agent response: {event.content}")
        case "tool_use":
            print(f"Calling tool: {event.tool_name}")
        case "tool_result":
            print(f"Tool result: {event.result}")
        case "subagent_spawn":
            print(f"Spawned subagent: {event.subagent_type}")
        case "cost_update":
            print(f"Cost: ${event.cost_usd:.4f}")
        case "progress":
            print(f"Progress: {event.step}/{event.total}")
        case "completed":
            print(f"Done! Cycles: {event.cycles}, Cost: ${event.total_cost_usd:.4f}")
        case "error":
            print(f"Error: {event.error}")
```

### WebSocket Integration

```python
from fastapi import FastAPI, WebSocket
from kaizen.runtime.streaming import StreamingExecutor

app = FastAPI()

@app.websocket("/agent/stream")
async def agent_stream(websocket: WebSocket, task: str):
    await websocket.accept()

    executor = StreamingExecutor()
    context = ExecutionContext(task=task)

    async for event in executor.execute_stream(context):
        await websocket.send_json(event.to_dict())

    await websocket.close()
```

---

## Part 7: Specialist System (ADR-013)

### Using Built-in Specialists

```python
from kaizen.runtime.adapters import LocalKaizenAdapter
from kaizen.core import KaizenOptions

# Load specialists from .kaizen/ directories
options = KaizenOptions(setting_sources=["project", "user"])
adapter = LocalKaizenAdapter(kaizen_options=options)

# List available specialists
specialists = adapter.list_specialists()
# ['dataflow-specialist', 'nexus-specialist', 'kaizen-specialist', ...]

# List available skills
skills = adapter.list_skills()
# ['01-core-sdk', '02-dataflow', '03-nexus', '04-kaizen', ...]
```

### Creating Custom Specialists

Create `.kaizen/specialists/my-specialist.md`:

```markdown
---
name: my-domain-specialist
description: Expert in my specific domain
triggers:
  - "my-domain"
  - "domain-specific"
skills:
  - my-domain-patterns
  - my-domain-testing
---

# My Domain Specialist

You are an expert in [my domain]. Your responsibilities:

1. Analyze domain requirements
2. Implement domain-specific patterns
3. Ensure compliance with domain rules

## Key Patterns

```python
# Domain pattern examples
...
```
```

---

## Part 8: Trust & Governance (EATP)

For enterprise enterprise deployments:

```python
from kaizen.trust import TrustOperations, TrustedAgent, TrustChainVerifier

# Verify trust before autonomous actions
async def eatp_pre_tool_hook(context):
    verifier = TrustChainVerifier()
    verification = await verifier.verify(
        trust_chain_id=context.metadata["trust_chain_id"],
        action=context.data["tool_name"],
        parameters=context.data["tool_input"],
    )

    if not verification.allowed:
        return {"should_continue": False, "message": verification.reason}

    return {"should_continue": True}

# Create trusted agent
agent = TrustedAgent(
    base_agent=Agent(model="gpt-4", agent_type="autonomous"),
    trust_context=trust_context,
    pre_tool_hook=eatp_pre_tool_hook,
)
```

---

## Part 9: Complete Integration Example

```python
"""
Full Enterprise-App Integration with Kaizen
"""
from kaizen import Agent
from kaizen.runtime.adapters import LocalKaizenAdapter, RuntimeSelector
from kaizen.runtime import ExecutionContext
from kaizen.tools.native import KaizenToolRegistry
from kaizen.memory.providers import HierarchicalMemory
from kaizen.llm.routing import LLMRouter, TaskAnalyzer

# 1. Configure tool registry
registry = KaizenToolRegistry()
registry.register_defaults(categories=[
    "file", "bash", "search", "agent",
    "interaction", "planning", "process"
])  # 19 tools

# 2. Configure memory
memory = HierarchicalMemory(
    hot_config={"max_entries": 100},
    warm_config={"backend": "dataflow", "connection": "postgresql://..."},
)

# 3. Configure LLM routing
router = LLMRouter(strategy="balanced")
analyzer = TaskAnalyzer()

# 4. Create adapter
adapter = LocalKaizenAdapter(
    tool_registry=registry,
    memory_provider=memory,
    llm_router=router,
)

# 5. Execute autonomous task
context = ExecutionContext(
    task="Build a REST API for user management with full CRUD operations",
    session_id="session-123",
    max_cycles=100,
    timeout_seconds=600,
)

result = await adapter.execute(context)

print(f"Completed in {result.cycles} cycles")
print(f"Cost: ${result.cost_usd:.4f}")
print(f"Output: {result.output}")
```

---

## Part 10: Deployment Patterns

### CLI Mode

```python
from kaizen import Agent

agent = Agent(model="gpt-4", agent_type="autonomous")

# Interactive CLI
async def cli_loop():
    while True:
        task = input("Task> ")
        if task == "exit":
            break
        result = await agent.run(task)
        print(result.text)

asyncio.run(cli_loop())
```

### API Mode (FastAPI + Nexus)

```python
from nexus import Nexus
from kaizen import Agent

nexus = Nexus(enable_monitoring=True)
agent = Agent(model="gpt-4", agent_type="autonomous")

@nexus.workflow
async def execute_task(task: str) -> dict:
    result = await agent.run(task)
    return {"output": result.text, "cost": result.cost_usd}

# Auto-deploys as: API + CLI + MCP
nexus.run(port=8000)
```

### Claude Code SDK Integration

```python
from kaizen.runtime.adapters import ClaudeCodeAdapter
from kaizen.runtime import ExecutionContext

# Delegate to Claude Code's native runtime
adapter = ClaudeCodeAdapter(
    working_directory="/path/to/project",
    custom_tools=[my_kaizen_tool],  # Extend with Kaizen tools via MCP
    model="claude-sonnet-4-20250514",
)

context = ExecutionContext(task="Analyze codebase and fix bugs")
result = await adapter.execute(context)
```

---

## Verification Checklist

### Claude Code Parity (19/19 Tools)

- [x] ReadFileTool - with pagination, line numbers
- [x] WriteFileTool - with auto-directory creation
- [x] EditFileTool - string replacement
- [x] GlobTool - pattern matching
- [x] GrepTool - regex search with context
- [x] ListDirectoryTool - directory listing
- [x] FileExistsTool - existence check
- [x] BashTool - sandboxed execution
- [x] WebSearchTool - web search
- [x] WebFetchTool - URL content extraction
- [x] TaskTool - subagent spawning
- [x] SkillTool - skill invocation
- [x] TodoWriteTool - task management
- [x] AskUserQuestionTool - user communication
- [x] NotebookEditTool - Jupyter editing
- [x] EnterPlanModeTool - plan mode entry
- [x] ExitPlanModeTool - plan mode exit
- [x] KillShellTool - process termination
- [x] TaskOutputTool - background output

### Extended Capabilities

- [x] Multi-LLM routing (Claude, OpenAI, Gemini, Ollama, Azure)
- [x] Hierarchical memory (Hot/Warm/Cold)
- [x] Learning memory (patterns, preferences, errors)
- [x] 10 streaming event types
- [x] EATP trust integration
- [x] Specialist system (ADR-013)
- [x] Checkpoint/resume
- [x] Cost tracking with budget enforcement

---

**Version**: 1.0.0b1
**Last Updated**: 2026-01-24
**Tests**: 451 native tool tests + 922 autonomous tests
