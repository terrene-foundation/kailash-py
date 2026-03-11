# Phase 6: Autonomous Execution Layer - Developer Overview

This document provides a comprehensive overview of the Phase 6 Autonomous Execution Layer implementation for Kaizen developers.

## Architecture Summary

Phase 6 delivers the core autonomous execution capabilities that enable Kaizen agents to operate independently for extended periods. The architecture consists of 7 interconnected components:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Unified Agent API (TODO-195)                 │
│     AgentCapabilities, CapabilityPresets, Agent class           │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│               Runtime Abstraction Layer (TODO-191)              │
│   RuntimeAdapter, RuntimeCapabilities, RuntimeSelector          │
└─────────────────────────────────────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────────────┐
│LocalKaizen    │    │ External      │    │ Multi-LLM Routing     │
│Adapter        │    │ Adapters      │    │ (TODO-194)            │
│(TODO-192)     │    │ (TODO-196)    │    │ LLMRouter, TaskAnalyzer│
│TAOD Loop      │    │ Claude/OpenAI │    └───────────────────────┘
└───────────────┘    │ /Gemini       │
        │            └───────────────┘
        ▼
┌───────────────┐    ┌───────────────┐
│Native Tools   │    │Memory Provider│
│(TODO-190)     │    │(TODO-193)     │
│BaseTool,      │    │Hierarchical   │
│Registry       │    │Memory         │
└───────────────┘    └───────────────┘
```

## Component Summary

| Component | TODO | Tests | Primary Purpose |
|-----------|------|-------|-----------------|
| Native Tool System | TODO-190 | - | File, Bash, Search tools |
| Runtime Abstraction | TODO-191 | 371 | Adapter interface, selector |
| LocalKaizenAdapter | TODO-192 | 371 | TAOD autonomous loop |
| Memory Provider | TODO-193 | 112 | Hot/Warm/Cold memory |
| Multi-LLM Routing | TODO-194 | 145 | Task-based LLM selection |
| Unified Agent API | TODO-195 | 217 | Developer-facing API |
| External Adapters | TODO-196 | 77 | Claude/OpenAI/Gemini |

**Total Tests**: 922+

## Key Concepts

### 1. RuntimeAdapter Interface

All execution backends implement the `RuntimeAdapter` interface:

```python
from kaizen.runtime.adapter import BaseRuntimeAdapter
from kaizen.runtime.context import ExecutionContext, ExecutionResult

class MyAdapter(BaseRuntimeAdapter):
    async def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute a task and return results."""
        ...

    async def stream(self, context: ExecutionContext) -> AsyncIterator[str]:
        """Stream output as it's generated."""
        ...

    async def interrupt(self, session_id: str, mode: str) -> bool:
        """Interrupt an ongoing execution."""
        ...

    def map_tools(self, tools: List[Dict]) -> List[Dict]:
        """Convert Kaizen tools to runtime-specific format."""
        ...
```

### 2. TAOD Loop (LocalKaizenAdapter)

The Think-Act-Observe-Decide loop is the core autonomous execution pattern:

```
┌─────────────────────────────────────────────────┐
│                  TAOD Loop                       │
│                                                  │
│   ┌──────┐    ┌─────┐    ┌─────────┐    ┌──────┐│
│   │Think │───▶│ Act │───▶│ Observe │───▶│Decide││
│   └──────┘    └─────┘    └─────────┘    └──────┘│
│       ▲                                    │     │
│       └────────────────────────────────────┘     │
│                  (if not converged)              │
└─────────────────────────────────────────────────┘
```

- **Think**: Analyze current state, plan next action
- **Act**: Execute tools or generate response
- **Observe**: Process tool results, update state
- **Decide**: Determine if task is complete or continue

### 3. Memory Tiers

The HierarchicalMemory system uses temperature-based access:

| Tier | Access Pattern | Retention | Use Case |
|------|----------------|-----------|----------|
| Hot | Immediate | Current session | Recent context |
| Warm | Fast | Hours-days | Related sessions |
| Cold | Slower | Permanent | Long-term knowledge |

### 4. Tool Mapping

Kaizen uses OpenAI function calling format internally, but adapters convert to provider-specific formats:

```python
# Kaizen format (OpenAI-compatible)
kaizen_tool = {
    "type": "function",
    "function": {
        "name": "search_docs",
        "description": "Search documentation",
        "parameters": {...}
    }
}

# Adapters convert automatically
from kaizen.runtime.adapters import MCPToolMapper, GeminiToolMapper

mcp_tools = MCPToolMapper.to_mcp_format([kaizen_tool])
gemini_tools = GeminiToolMapper.to_gemini_format([kaizen_tool])
```

## Getting Started

### Basic Usage

```python
from kaizen.runtime.adapters import LocalKaizenAdapter
from kaizen.runtime.context import ExecutionContext
from kaizen.runtime.config import AutonomousConfig

# Create adapter with configuration
adapter = LocalKaizenAdapter(
    config=AutonomousConfig(
        model="gpt-4o",
        max_cycles=100,
        budget_limit=10.0,
    )
)

# Execute a task
context = ExecutionContext(task="Analyze this codebase and suggest improvements")
result = await adapter.execute(context)

print(f"Status: {result.status}")
print(f"Output: {result.output}")
print(f"Tokens used: {result.tokens_used}")
```

### With Unified Agent API

```python
from kaizen.agent import Agent

# Using capability presets
agent = Agent.with_preset("developer")
result = await agent.run("Fix the bug in src/main.py")

# Or manual configuration
agent = Agent(
    execution_mode="autonomous",
    memory_depth="session",
    tool_access="full",
)
result = await agent.run("Refactor this module")
```

### With Runtime Selector

```python
from kaizen.runtime.selector import RuntimeSelector

selector = RuntimeSelector()

# Automatic selection based on task
adapter = await selector.select_for_task(
    task="Process this 500-page document",
    requirements={"context_window": "large"}
)

# Or explicit selection
adapter = await selector.get_adapter("gemini_cli")  # 1M context
```

## File Organization

```
src/kaizen/runtime/
├── adapter.py              # BaseRuntimeAdapter interface
├── capabilities.py         # RuntimeCapabilities dataclass
├── context.py              # ExecutionContext, ExecutionResult
├── config.py               # AutonomousConfig
├── selector.py             # RuntimeSelector
│
├── adapters/
│   ├── __init__.py         # Public exports
│   ├── local_kaizen.py     # LocalKaizenAdapter (TAOD)
│   ├── claude_code.py      # ClaudeCodeAdapter
│   ├── openai_codex.py     # OpenAICodexAdapter
│   ├── gemini_cli.py       # GeminiCLIAdapter
│   │
│   ├── tool_mapping/
│   │   ├── base.py         # ToolMapper ABC
│   │   ├── mcp.py          # MCPToolMapper
│   │   ├── openai.py       # OpenAIToolMapper
│   │   └── gemini.py       # GeminiToolMapper
│   │
│   └── docs/
│       ├── external_adapters.md
│       └── developers/     # This documentation
│
├── memory/
│   ├── provider.py         # MemoryProvider ABC
│   ├── buffer.py           # BufferMemoryAdapter
│   └── hierarchical.py     # HierarchicalMemory
│
└── routing/
    ├── router.py           # LLMRouter
    ├── analyzer.py         # TaskAnalyzer
    ├── rules.py            # RoutingRule
    └── fallback.py         # FallbackRouter
```

## Testing

Run Phase 6 tests:

```bash
# All Phase 6 tests
pytest tests/runtime/ -v

# Specific components
pytest tests/runtime/adapters/test_tool_mapping.py -v  # 41 tests
pytest tests/runtime/adapters/test_external_adapters.py -v  # 36 tests
pytest tests/runtime/test_selector.py -v
pytest tests/runtime/test_memory_provider.py -v  # 112 tests
pytest tests/runtime/test_routing.py -v  # 145 tests
pytest tests/agent/test_unified_api.py -v  # 217 tests
```

## Related Documentation

- `01-runtime-abstraction.md` - Runtime Abstraction Layer deep dive
- `02-tool-mapping.md` - Tool mapping infrastructure
- `03-external-adapters.md` - External adapter usage
- `04-unified-agent-api.md` - Agent API reference
- `05-memory-providers.md` - Memory system guide
- `06-multi-llm-routing.md` - LLM routing patterns

## Phase 6 Completion Evidence

| TODO | Component | Tests | Status |
|------|-----------|-------|--------|
| TODO-190 | Native Tool System | - | COMPLETE |
| TODO-191 | Runtime Abstraction | 371 | COMPLETE |
| TODO-192 | LocalKaizenAdapter | 371 | COMPLETE |
| TODO-193 | Memory Provider | 112 | COMPLETE |
| TODO-194 | Multi-LLM Routing | 145 | COMPLETE |
| TODO-195 | Unified Agent API | 217 | COMPLETE |
| TODO-196 | External Adapters | 77 | COMPLETE |

**Total**: 922+ tests passing, 100% completion
