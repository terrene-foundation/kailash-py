# Universal Tool Integration Pattern

**Reference**: ADR-016 - Universal Tool Integration for All 25 Agents

## Overview

This guide provides the exact implementation pattern for adding tool support to all Kaizen agents. Follow this template for consistent, production-ready tool integration.

## Implementation Pattern

### Step 1: Modify `__init__()` Signature

Add two new parameters **after all existing parameters, before `**kwargs`**:

```python
from typing import Any, Dict, List, Optional
from kaizen.tools.registry import ToolRegistry

class YourAgent(BaseAgent):
    def __init__(
        self,
        # ============================================
        # EXISTING PARAMETERS (DO NOT MODIFY)
        # ============================================
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        # ... any other agent-specific parameters ...
        config: Optional[YourAgentConfig] = None,

        # ============================================
        # NEW: UNIVERSAL TOOL PARAMETERS
        # Position: After all existing params, before **kwargs
        # ============================================
        tool_registry: Optional[ToolRegistry] = None,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,

        # ============================================
        # **kwargs ALWAYS LAST
        # ============================================
        **kwargs,
    ):
```

**Rules**:
- ✅ Add `tool_registry` and `mcp_servers` AFTER all existing parameters
- ✅ Both parameters are `Optional` with default `None`
- ✅ Position before `**kwargs` (if present)
- ✅ Import `ToolRegistry` from `kaizen.tools.registry`
- ❌ Do NOT reorder existing parameters
- ❌ Do NOT make parameters required

### Step 2: Update Docstring

Add parameter documentation:

```python
    """
    Initialize YourAgent with optional tool calling.

    Args:
        # ============================================
        # EXISTING PARAMETER DOCS (DO NOT MODIFY)
        # ============================================
        llm_provider: Override default LLM provider
        model: Override default model
        temperature: Override default temperature
        # ... existing parameter docs ...

        # ============================================
        # NEW: TOOL PARAMETER DOCS
        # Copy this section exactly
        # ============================================
        tool_registry: Optional tool registry for autonomous tool execution.
            When provided, agent can discover and execute tools (file operations,
            HTTP requests, bash commands, web scraping). See ADR-016 for details.
        mcp_servers: Optional MCP server configurations for MCP tool access.
            List of dicts with 'command' and 'args' keys for stdio transport.
            Example: [{"command": "python", "args": ["-m", "mcp_server"]}]
        **kwargs: Additional arguments passed to BaseAgent

    Example:
        >>> # Without tools (backward compatible)
        >>> agent = YourAgent(llm_provider="openai", model="gpt-4")
        >>>
        >>> # With builtin tools
        >>> # Tools auto-configured via MCP
        >>>
        >>>
        >>>
        >>> # 12 builtin tools enabled via MCP
        >>>
        >>> agent = YourAgent(
        ...     llm_provider="openai",
        ...     model="gpt-4",
        ...     tools="all"  # Enable 12 builtin tools via MCP
        ... )
        >>>
        >>> # Agent can now execute tools autonomously
        >>> result = agent.run(...)
    """
```

### Step 3: Pass Parameters to BaseAgent

In the `super().__init__()` call, add the two new parameters:

```python
    # Build config from parameters (existing pattern)
    if config is None:
        config = YourAgentConfig()
        # ... apply parameter overrides ...

    # Initialize BaseAgent with tool support
    super().__init__(
        config=config,
        signature=YourAgentSignature(),
        strategy=your_strategy,  # if applicable

        # ============================================
        # NEW: Pass tool parameters to BaseAgent
        # ============================================
        tools="all"  # Enable tools via MCP
        mcp_servers=mcp_servers,

        **kwargs,
    )

    # Agent-specific initialization continues below
    # ...
```

**Rules**:
- ✅ Pass `tool_registry` directly (no modification)
- ✅ Pass `mcp_servers` directly (no modification)
- ✅ Position before `**kwargs`
- ❌ Do NOT validate or modify these parameters
- ❌ Do NOT store them in instance variables (BaseAgent handles this)

### Complete Example: SimpleQAAgent

**Before (without tools)**:
```python
class SimpleQAAgent(BaseAgent):
    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        config: Optional[SimpleQAConfig] = None,
        **kwargs,
    ):
        """Initialize SimpleQA agent."""
        if config is None:
            config = SimpleQAConfig()
            if llm_provider is not None:
                config = replace(config, llm_provider=llm_provider)
            # ... other overrides ...

        super().__init__(
            config=config,
            signature=QASignature(),
            **kwargs,
        )
```

**After (with tools)**:
```python
from typing import Any, Dict, List, Optional
from kaizen.tools.registry import ToolRegistry

class SimpleQAAgent(BaseAgent):
    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        config: Optional[SimpleQAConfig] = None,
        tool_registry: Optional[ToolRegistry] = None,  # NEW
        mcp_servers: Optional[List[Dict[str, Any]]] = None,  # NEW
        **kwargs,
    ):
        """
        Initialize SimpleQA agent with optional tool calling.

        Args:
            llm_provider: Override default LLM provider
            model: Override default model
            temperature: Override default temperature
            max_tokens: Override default max tokens
            config: Full config object (overrides individual params)
            tool_registry: Optional tool registry for autonomous tool execution
            mcp_servers: Optional MCP server configurations
            **kwargs: Additional arguments passed to BaseAgent
        """
        if config is None:
            config = SimpleQAConfig()
            if llm_provider is not None:
                config = replace(config, llm_provider=llm_provider)
            # ... other overrides ...

        super().__init__(
            config=config,
            signature=QASignature(),
            tools="all"  # Enable tools via MCP
            mcp_servers=mcp_servers,       # NEW
            **kwargs,
        )
```

**Changes**:
1. ✅ Added 2 parameters to `__init__()`
2. ✅ Updated docstring with tool parameter docs
3. ✅ Passed 2 parameters to `super().__init__()`
4. ✅ Added import for `ToolRegistry`

**Total Lines Changed**: ~10 lines (minimal impact)

## Agent-Specific Patterns

### For Iterative Agents (ReAct, ChainOfThought, RAG)

Tool execution happens automatically in MultiCycleStrategy. No additional code needed:

```python
class ReActAgent(BaseAgent):
    def solve_task(self, task: str) -> Dict[str, Any]:
        """Execute ReAct cycles with automatic tool calling."""

        # Execute via BaseAgent with MultiCycleStrategy
        result = self.run(
            task=task,
            available_tools=self.available_tools,  # Optional: discovered tools
        )

        # MultiCycleStrategy automatically:
        # 1. Checks result["tool_calls"] for objective convergence
        # 2. Executes tools via self.execute_tool_chain() if present
        # 3. Feeds results back to LLM in next cycle
        # 4. Continues until tool_calls is empty (converged)

        return result
```

**Key Point**: MultiCycleStrategy handles tool execution loops. Agent just passes tools to context.

### For Single-Shot Agents (SimpleQA, Vision, Transcription)

Tools available but optional. No code changes needed:

```python
class SimpleQAAgent(BaseAgent):
    def ask(self, question: str) -> Dict[str, Any]:
        """Answer question with optional tool support."""

        # AsyncSingleShotStrategy automatically:
        # 1. Passes available tools to LLM context
        # 2. Executes tools if LLM requests them (tool_calls field)
        # 3. Returns result with tool execution outcomes

        result = self.run(question=question)
        return result
```

**Key Point**: AsyncSingleShotStrategy handles tool execution. No agent code changes needed.

### For Coordination Agents (Supervisor, Worker, Coordinator)

Tools provide additional context for coordination:

```python
class SupervisorAgent(BaseAgent):
    def delegate_tasks(self, request: str) -> List[Dict[str, Any]]:
        """Delegate tasks with optional tool support for analysis."""

        # Tools useful for:
        # - Task complexity analysis (code/document inspection)
        # - Resource availability checking (file existence, API health)
        # - Schema validation (JSON/YAML parsing)

        result = self.run(request=request, num_tasks=3)
        return result
```

**Key Point**: Tools enhance coordination, not required for basic functionality.

## Tool Discovery Pattern (Optional)

Agents can optionally discover and expose tools in their context:

```python
class RAGResearchAgent(BaseAgent):
    def __init__(self, ..., tools="all"  # Enable tools via MCP
        super().__init__(..., tools="all"  # Enable tools via MCP

        # Optional: Discover relevant tools for LLM context
        if self.has_tool_support():
            self.available_tools = asyncio.run(
                self.discover_tools(
                    category=ToolCategory.NETWORK,  # Only web/HTTP tools
                    safe_only=False  # Include all danger levels
                )
            )
        else:
            self.available_tools = []

    def research(self, query: str) -> Dict[str, Any]:
        """Research with tool-augmented retrieval."""
        result = self.run(
            query=query,
            available_tools=self.available_tools  # Pass discovered tools
        )
        return result
```

**When to discover tools**:
- ✅ Agent has specific tool categories it uses (file, network, data)
- ✅ Want to filter tools by danger level or keyword
- ✅ Need to show tools in LLM context for better selection

**When NOT to discover tools**:
- ❌ Agent doesn't use tools actively (tools still available on-demand)
- ❌ Want to minimize initialization time
- ❌ BaseAgent auto-discovery sufficient

## Testing Pattern

Every agent needs 3 tests (see `docs/guides/universal-tool-integration-testing.md`):

1. **Test Tool Discovery**: Verify agent discovers tools when registry provided
2. **Test Tool Execution**: Verify agent executes tools in workflow (Tier 2, real LLM)
3. **Test Backward Compatibility**: Verify agent works without tools

## Validation Checklist

Before submitting your implementation:

- [ ] Added `tool_registry` parameter after existing params, before `**kwargs`
- [ ] Added `mcp_servers` parameter after `tool_registry`, before `**kwargs`
- [ ] Both parameters are `Optional[...]` with default `None`
- [ ] Updated docstring with tool parameter documentation
- [ ] Added usage example showing tool-enabled initialization
- [ ] Passed both parameters to `super().__init__()`
- [ ] Did NOT modify existing parameters or their order
- [ ] Did NOT add custom tool handling logic (BaseAgent handles it)
- [ ] Added import: `from kaizen.tools.registry import ToolRegistry`
- [ ] Added type hints: `List`, `Dict`, `Any` from `typing`
- [ ] Wrote 3 tests (discovery, execution, backward compatibility)
- [ ] All existing tests still pass
- [ ] Created example in `examples/autonomy/tools/{agent_name}_example.py`

## Common Mistakes

### ❌ Wrong Parameter Position

```python
# WRONG: tool_registry before agent-specific parameters
def __init__(
    self,
    tool_registry: Optional[ToolRegistry] = None,  # TOO EARLY
    llm_provider: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs,
):
```

```python
# CORRECT: tool_registry after all agent-specific parameters
def __init__(
    self,
    llm_provider: Optional[str] = None,
    model: Optional[str] = None,
    config: Optional[Config] = None,
    tool_registry: Optional[ToolRegistry] = None,  # CORRECT POSITION
    mcp_servers: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
):
```

### ❌ Missing Type Hints

```python
# WRONG: No type hints
def __init__(self, ..., tools="all"  # Enable tools via MCP
```

```python
# CORRECT: Full type hints
from typing import Any, Dict, List, Optional
from kaizen.tools.registry import ToolRegistry

def __init__(
    self,
    ...,
    tool_registry: Optional[ToolRegistry] = None,
    mcp_servers: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
):
```

### ❌ Modifying Tool Parameters

```python
# WRONG: Validating or storing tool parameters
def __init__(self, ..., tools="all"  # Enable tools via MCP
    if tool_registry:
        # Validate registry
        if not isinstance(tool_registry, ToolRegistry):
            raise ValueError("Invalid registry")

    self._my_tool_registry = tool_registry  # Don't store separately

    super().__init__(..., tools="all"  # Enable tools via MCP
```

```python
# CORRECT: Pass through unchanged
def __init__(self, ..., tools="all"  # Enable tools via MCP
    # No validation, no storage
    super().__init__(..., tools="all"  # Enable tools via MCP
```

### ❌ Missing Import

```python
# WRONG: No import for ToolRegistry
from typing import Optional

def __init__(self, ..., tool_registry: Optional[ToolRegistry] = None, **kwargs):
    #                                            ^^^^^^^^^^^^
    # NameError: ToolRegistry not defined
```

```python
# CORRECT: Import ToolRegistry
from typing import Optional
from kaizen.tools.registry import ToolRegistry  # ADD THIS

def __init__(self, ..., tool_registry: Optional[ToolRegistry] = None, **kwargs):
```

## Migration Scripts

For bulk migration, use search-replace with caution:

### Search Pattern
```regex
def __init__\(\s*self,\s*(.*?),\s*\*\*kwargs,\s*\):
```

### Replace Pattern
```python
def __init__(
    self,
    \1,
    tool_registry: Optional[ToolRegistry] = None,
    mcp_servers: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
):
```

**Warning**: This is a starting point. Manual review REQUIRED for:
- Agents without `**kwargs`
- Agents with complex parameter patterns
- Docstring updates
- Import statements

## Support

**Questions**: See ADR-016 or ask in team discussions

**Examples**: Check `examples/autonomy/tools/` for working implementations

**Tests**: See `tests/unit/agents/test_*_tool_integration.py` for test patterns
