# Kaizen v1.0 Features (2026-01-25)

Production-ready features for performance optimization, specialist system, and GPT-5 compatibility.

## Deprecation Notes

| Feature | Status | Migration |
|---------|--------|-----------|
| `ToolRegistry`, `ToolExecutor` | **REMOVED** | Use MCP via `BaseAgent.execute_mcp_tool()` or `KaizenToolRegistry` for native tools |
| `kaizen.agents.coordination` | **DEPRECATED** (removal in v0.5.0) | Use `kaizen.orchestration.patterns` |
| `max_tokens` (OpenAI providers) | **DEPRECATED** | Use `max_completion_tokens` instead |

## Performance Optimization (TODO-199)

The `kaizen.performance` module provides production-ready optimizations for the TAOD loop:

| Component | Optimization | Speedup |
|-----------|-------------|---------|
| `SchemaCache` | Tool schema caching | 10-50x |
| `EmbeddingCache` | Embedding vector caching | 100x+ (API calls saved) |
| `PromptCache` | System prompt caching | 10-20x |
| `MemoryContextCache` | Incremental context building | 5-10x |
| `HookBatchExecutor` | Parallel hook execution | 8x |
| `BackgroundCheckpointWriter` | Non-blocking I/O | Eliminates blocking |
| `ParallelToolExecutor` | Parallel tool execution | 4-5x |

```python
from kaizen.performance import (
    SchemaCache, EmbeddingCache, PromptCache, MemoryContextCache,
    HookBatchExecutor, BackgroundCheckpointWriter,
    get_schema_cache, get_embedding_cache,  # Global singletons
)

# Example: Schema caching
cache = get_schema_cache()
schema = cache.get_or_compute("tool_name", lambda: generate_schema())
print(f"Hit rate: {cache.get_metrics().hit_rate:.1%}")  # 95%+
```

## Specialist System (ADR-013)

Claude Code-style specialists and skills:

```python
from kaizen.core import KaizenOptions, SpecialistDefinition
from kaizen.runtime.adapters import LocalKaizenAdapter

# Programmatic specialists
specialists = {
    "code-reviewer": SpecialistDefinition(
        description="Expert code reviewer",
        system_prompt="You are a senior code reviewer...",
        available_tools=["Read", "Glob", "Grep"],
        model="gpt-4o",
        temperature=0.2,
    ),
}

options = KaizenOptions(specialists=specialists)
adapter = LocalKaizenAdapter(kaizen_options=options)
reviewer = adapter.for_specialist("code-reviewer")
```

**Directory Structure** for filesystem-based specialists:
```
.kaizen/
├── specialists/
│   └── code-reviewer.md
└── skills/
    └── python-patterns/
        ├── SKILL.md
        └── patterns.md
```

## Native Tool System

TAOD loop integration with danger-level approval.

> **IMPORTANT**: The old `ToolRegistry` and `ToolExecutor` classes have been REMOVED and migrated to MCP.
> - **Old API (REMOVED)**: `from kaizen.tools import ToolRegistry, ToolExecutor`
> - **New API**: Use `BaseAgent.execute_mcp_tool()` for MCP-based tools, or `KaizenToolRegistry` for native tools

```python
from kaizen.tools import BaseTool, NativeToolResult, KaizenToolRegistry

class MyTool(BaseTool):
    name = "my_tool"
    description = "Does something useful"
    danger_level = "LOW"  # SAFE, LOW, MEDIUM, HIGH, CRITICAL

    def execute(self, **params) -> NativeToolResult:
        return NativeToolResult(success=True, output={"result": "done"})

registry = KaizenToolRegistry()
registry.register(MyTool())
```

## Multi-LLM Routing

Intelligent routing with 5 strategies:

```python
from kaizen.llm import LLMRouter, RoutingStrategy

router = LLMRouter(strategy=RoutingStrategy.BALANCED)
# Strategies: RULES, TASK_COMPLEXITY, COST_OPTIMIZED, QUALITY_OPTIMIZED, BALANCED
```

## GPT-5 Compatibility (CRITICAL)

**GPT-5 models require `temperature=1.0`** - this is enforced automatically:

```python
# Provider auto-handles GPT-5 temperature requirement
config = AgentConfig(
    llm_provider="openai",
    model="gpt-5-nano-2025-08-07",  # or gpt-5-2025-08-07
    temperature=1.0,  # REQUIRED for GPT-5 - auto-enforced
    max_tokens=8000,  # Increased for GPT-5 reasoning tokens
)
```

## Claude Code Parity Tools (TODO-207)

Seven tools for autonomous workflows:

| Tool | Purpose |
|------|---------|
| `TodoWriteTool` | Task list management |
| `NotebookEditTool` | Jupyter notebook editing |
| `AskUserQuestionTool` | Bidirectional communication |
| `EnterPlanModeTool` | Enter planning phase |
| `ExitPlanModeTool` | Exit planning phase |
| `KillShellTool` | Terminate background processes |
| `TaskOutputTool` | Retrieve task output |

## Task/Skill Tools (TODO-203)

Subagent spawning and knowledge injection:

```python
from kaizen.tools import TaskTool, SkillTool

# Spawn subagent
task_tool = TaskTool(agent_registry=registry)
result = task_tool.execute(
    subagent_type="code-reviewer",
    prompt="Review this code...",
)

# Inject knowledge
skill_tool = SkillTool(skill_registry=skill_registry)
context = skill_tool.execute(skill="python-patterns")
```

## Developer Documentation

Full v1.0 documentation in `apps/kailash-kaizen/src/kaizen/docs/developers/`:

| Guide | Description |
|-------|-------------|
| `00-native-tools-guide.md` | Native tool system |
| `01-runtime-abstraction-guide.md` | Runtime abstraction layer |
| `02-local-kaizen-adapter-guide.md` | TAOD loop implementation |
| `03-memory-provider-guide.md` | Memory provider interface |
| `04-multi-llm-routing-guide.md` | Multi-LLM routing |
| `05-unified-agent-api-guide.md` | Unified Agent API |
| `06-specialist-system-guide.md` | Specialist system (ADR-013) |
| `07-task-skill-tools-guide.md` | Task/Skill tools |
| `08-claude-code-parity-tools-guide.md` | Claude Code parity tools |
| `09-performance-optimization-guide.md` | Performance optimization |

## Reference

- Specialist guide: `apps/kailash-kaizen/src/kaizen/docs/developers/06-specialist-system-guide.md`
- TAOD loop: `apps/kailash-kaizen/src/kaizen/docs/developers/02-local-kaizen-adapter-guide.md`
- Performance: `apps/kailash-kaizen/src/kaizen/docs/developers/09-performance-optimization-guide.md`
