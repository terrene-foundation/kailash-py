# ADR-016 Quick Reference Card

**Universal Tool Integration for All 25 Kaizen Agents**

## TL;DR

Add 2 parameters to every agent's `__init__()`:
```python
tool_registry: Optional[ToolRegistry] = None,
mcp_servers: Optional[List[Dict[str, Any]]] = None,
```

Pass them to `super().__init__()`. Done.

## 3-Step Implementation

### 1️⃣ Import
```python
from typing import Any, Dict, List, Optional
from kaizen.tools.registry import ToolRegistry
```

### 2️⃣ Add Parameters
```python
def __init__(
    self,
    # ... existing params ...
    config: Optional[Config] = None,
    tool_registry: Optional[ToolRegistry] = None,       # ADD
    mcp_servers: Optional[List[Dict[str, Any]]] = None, # ADD
    **kwargs,
):
```

### 3️⃣ Pass to BaseAgent
```python
super().__init__(
    config=config,
    signature=signature,
    tools="all"  # Enable tools via MCP
    mcp_servers=mcp_servers,       # ADD
    **kwargs,
)
```

## 3-Test Template

### Test 1: Discovery (Tier 1)
```python
def test_tool_discovery(self):

    # 12 builtin tools enabled via MCP
    agent = Agent(tools="all"  # Enable 12 builtin tools via MCP
    assert agent.has_tool_support()
    tools = asyncio.run(agent.discover_tools())
    assert len(tools) == 12
```

### Test 2: Execution (Tier 2)
```python
@pytest.mark.tier2
def test_tool_execution(self, tmp_path):

    # 12 builtin tools enabled via MCP
    agent = Agent(llm_provider="ollama", model="llama2", tools="all"  # Enable 12 builtin tools via MCP
    result = agent.run("task")
    assert result is not None
```

### Test 3: Backward Compatible (Tier 1)
```python
def test_no_tools(self):
    agent = Agent(llm_provider="mock", model="mock")
    assert not agent.has_tool_support()
    result = agent.run("task")
    assert result is not None
```

## 4 Phases

| Phase | Week | Agents | Tests | Priority |
|-------|------|--------|-------|----------|
| 1 | 1 | 3 | 9 | High-value (ReAct, RAG, CodeGen) |
| 2 | 2 | 8 | 24 | All specialized |
| 3 | 3 | 3 | 9 | Multi-modal (Vision, Audio) |
| 4 | 4 | 11 | 33 | Coordination (Supervisor, etc.) |

## Validation Checklist

- [ ] Added 2 parameters after existing params, before `**kwargs`
- [ ] Both parameters `Optional` with default `None`
- [ ] Passed both to `super().__init__()`
- [ ] Updated docstring with tool parameter docs
- [ ] Added import for `ToolRegistry`
- [ ] Wrote 3 tests (discovery, execution, backward compat)
- [ ] All tests pass
- [ ] No breaking changes (existing tests still pass)

## Common Mistakes

❌ **Wrong position**: `tool_registry` before agent params
✅ **Correct**: After all agent params, before `**kwargs`

❌ **Modifying parameters**: Validation, storing separately
✅ **Correct**: Pass through unchanged to BaseAgent

❌ **Missing imports**: `ToolRegistry` not imported
✅ **Correct**: `from kaizen.tools.registry import ToolRegistry`

❌ **No async execution**: `agent.discover_tools()` instead of `asyncio.run(...)`
✅ **Correct**: `asyncio.run(agent.discover_tools())`

## Test Execution

```bash
# Run all tool integration tests
pytest tests/unit/agents/test_*_tool_integration.py -v

# Run Tier 1 only (fast, mocked)
pytest tests/unit/agents/test_*_tool_integration.py -m "not tier2 and not tier3"

# Run Tier 2 (real Ollama, requires Ollama running)
pytest tests/unit/agents/test_*_tool_integration.py -m tier2

# Run specific agent tests
pytest tests/unit/agents/test_react_tool_integration.py -v
```

## Usage Examples

### Without Tools (Backward Compatible)
```python
from kaizen.agents import ReActAgent

agent = ReActAgent(llm_provider="openai", model="gpt-4")
result = agent.solve_task("Calculate tax")
```

### With Tools (Opt-In)
```python
from kaizen.agents import ReActAgent
# Tools auto-configured via MCP



# 12 builtin tools enabled via MCP

agent = ReActAgent(
    llm_provider="openai",
    model="gpt-4",
    tools="all"  # Enable 12 builtin tools via MCP
)

result = agent.solve_task("Read data.txt and sum numbers")
# Agent can now autonomously execute file tools
```

## Files Modified per Agent

**Implementation** (~10 lines):
```
src/kaizen/agents/{module}/{agent_name}.py
```

**Tests** (~65 lines):
```
tests/unit/agents/test_{agent_name}_tool_integration.py
```

**Example** (~50 lines):
```
examples/autonomy/tools/{agent_name}_with_tools.py
```

**Total**: ~125 lines per agent × 25 agents = 3,125 lines

## Timeline

**Total**: 4 weeks (14 days implementation + 7 days testing)

- Week 1: Phase 1 (3 agents, high-value)
- Week 2: Phase 2 (8 agents, specialized)
- Week 3: Phase 3 (3 agents, multi-modal)
- Week 4: Phase 4 (11 agents, coordination)

## Success Criteria

✅ 25 agents support `tool_registry` parameter
✅ 75 tests passing (3 per agent)
✅ 100% backward compatibility (no breaking changes)
✅ 25 examples demonstrating tool usage
✅ All existing tests still pass

## Documentation

**Full Docs**:
- ADR-016: `/docs/architecture/adr/ADR-016-universal-tool-integration-all-agents.md`
- Implementation: `/docs/guides/universal-tool-integration-pattern.md`
- Testing: `/docs/guides/universal-tool-integration-testing.md`
- Summary: `/docs/architecture/adr/ADR-016-IMPLEMENTATION-SUMMARY.md`

**Quick Links**:
- BaseAgent Tool Integration: `docs/features/baseagent-tool-integration.md`
- Tool Examples: `examples/autonomy/tools/`
- Tool Tests: `tests/unit/tool_integration/`

## Support

**Questions**: See full ADR-016 or ask in team discussions
**Examples**: Check `examples/autonomy/tools/` for working code
**Tests**: See `tests/unit/agents/test_*_tool_integration.py` for patterns

---

**Reference**: ADR-016 - Universal Tool Integration for All 25 Agents
**Status**: Ready for Implementation
**Date**: 2025-10-22
