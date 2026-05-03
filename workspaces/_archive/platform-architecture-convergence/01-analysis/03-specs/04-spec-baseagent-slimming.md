# SPEC-04: BaseAgent Slimming + Agent Consolidation

**Status**: DRAFT
**Implements**: ADR-001 (Composition over extension points), ADR-002 (BaseAgent keeps Node), ADR-010 (CO Five Layers)
**Cross-SDK issues**: TBD
**Priority**: Phase 3 — depends on SPEC-01 (kailash-mcp) and SPEC-02 (providers)

## §1 Overview

Slim `BaseAgent` from 3,698 lines to ~800-1,200 lines by:

1. **Extracting MCP code** to consume from `kailash_mcp` (per SPEC-01)
2. **Extracting provider code** to consume from `kaizen.providers` (per SPEC-02)
3. **Extracting tool system** to consume unified `ToolRegistry` from `kailash_mcp.tools` (per SPEC-01)
4. **Adding `posture` field** to `BaseAgentConfig` (per ADR-010)
5. **Deprecating 7 extension points** with `@deprecated` decorator (per ADR-001, ADR-009)
6. **Keeping Node inheritance** and all public API methods (per ADR-002)

### What changes vs what stays

| Aspect                    | Before                                                   | After                                                  |
| ------------------------- | -------------------------------------------------------- | ------------------------------------------------------ |
| **File size**             | 3,698 LOC                                                | ~800-1,200 LOC                                         |
| **Inheritance**           | `class BaseAgent(Node)`                                  | `class BaseAgent(Node)` — UNCHANGED                    |
| **`run() -> Dict`**       | Works                                                    | Works — UNCHANGED                                      |
| **`run_async() -> Dict`** | Works                                                    | Works — UNCHANGED                                      |
| **`get_parameters()`**    | Works                                                    | Works — UNCHANGED                                      |
| **`to_workflow()`**       | Works                                                    | Works — UNCHANGED                                      |
| **MCP client**            | Inline `from kailash.mcp_server.client import MCPClient` | `from kailash_mcp import MCPClient`                    |
| **Provider**              | Inline from `kaizen.nodes.ai.ai_providers`               | `from kaizen.providers import get_provider_for_model`  |
| **Tool registry**         | Separate JSON schema approach                            | `from kailash_mcp.tools import ToolRegistry` (unified) |
| **7 extension points**    | Active, used by 188 subclasses                           | **Deprecated** with `@deprecated`, still callable      |
| **Mixins (7)**            | Applied conditionally via config flags                   | **Deprecated** — capabilities moved to wrappers        |
| **Strategies**            | SingleShot, MultiCycle, etc.                             | **Kept** in v2.x — AgentLoop strategy via wrappers     |
| **`posture`**             | Not present                                              | NEW: `AgentPosture` field on config                    |
| **`signature`**           | Constructor param                                        | Constructor param — UNCHANGED                          |
| **`system_prompt`**       | Extension point `_generate_system_prompt()`              | Constructor param — extension point deprecated         |

## §2 API Contract

### §2.1 BaseAgentConfig (Updated)

```python
# packages/kailash-kaizen/src/kaizen/core/config.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional
from kailash.trust.posture import AgentPosture


@dataclass
class BaseAgentConfig:
    """Configuration for BaseAgent.

    All LLM model names MUST come from .env or explicit parameter,
    never hardcoded (per rules/env-models.md).
    """

    # ─── LLM Configuration ─────────────────────────────────────────────
    model: str = ""                              # resolved from DEFAULT_LLM_MODEL env var if empty
    llm_provider: Optional[str] = None           # "openai", "anthropic", etc. Auto-detected from model if None.
    temperature: Optional[float] = 0.1
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None          # replaces _generate_system_prompt() extension point

    # ─── Agent Identity ────────────────────────────────────────────────
    agent_id: Optional[str] = None
    name: str = "agent"
    description: str = ""

    # ─── CO Five Layers (ADR-010) ──────────────────────────────────────
    posture: AgentPosture = AgentPosture.TOOL    # NEW — default preserves backward compat

    # ─── Execution ─────────────────────────────────────────────────────
    execution_mode: str = "single_shot"          # "single_shot" | "multi_cycle" | "autonomous"
    max_cycles: int = 5                          # for multi_cycle mode

    # ─── Provider Config ───────────────────────────────────────────────
    api_key: Optional[str] = None                # BYOK per-request override
    base_url: Optional[str] = None               # BYOK per-request URL override
    response_format: Optional[dict] = None       # structured output config (auto-set from signature)

    # ─── DEPRECATED (v2.x only, removed in v3.0) ──────────────────────
    # These fields are kept for backward compat but emit warnings on access
    strategy_type: str = "single_shot"           # use execution_mode instead
    logging_enabled: bool = True                 # use MonitoredAgent wrapper instead
    performance_enabled: bool = True             # use MonitoredAgent wrapper instead
    error_handling_enabled: bool = True          # use wrapper instead
    batch_processing_enabled: bool = False       # use wrapper instead
    memory_enabled: bool = False                 # use wrapper instead
    transparency_enabled: bool = False           # use wrapper instead
    mcp_enabled: bool = False                    # use MCPClient.discover_and_register() instead
    hooks_enabled: bool = False                  # use HookManager via StreamingAgent instead

    def __post_init__(self):
        # Resolve model from env if empty
        if not self.model:
            import os
            self.model = os.environ.get("DEFAULT_LLM_MODEL", "")
```

### §2.2 AgentPosture (in kailash.trust.posture — kept together per user decision)

```python
# src/kailash/trust/posture/agent_posture.py

from __future__ import annotations
from enum import IntEnum


class AgentPosture(IntEnum):
    """Agent posture levels mapping to PACT/EATP trust progression.

    Determines instruction enforcement semantics (per ADR-010):
    - PSEUDO/TOOL: Output schema is hard contract (strict validation)
    - SUPERVISED: Output schema is moderate (retry on failure)
    - AUTONOMOUS/DELEGATING: Output schema is guidance (soft validation)

    IntEnum so posture levels can be compared: TOOL < SUPERVISED < AUTONOMOUS.
    Envelopes can LOWER posture (posture_ceiling) but never raise it.

    Maps to:
    - EATP TrustPosture states
    - PACT verification gradient zones
    - CO Five Layers instruction enforcement spectrum
    """
    PSEUDO = 1       # L1: Not a real agent — direct API call
    TOOL = 2         # L2: Deterministic invocation (default)
    SUPERVISED = 3   # L3: Agent with human oversight
    AUTONOMOUS = 4   # L4: Independent within envelope
    DELEGATING = 5   # L5: Can delegate to other agents

    @classmethod
    def from_string(cls, s: str) -> AgentPosture:
        """Parse from string (case-insensitive)."""
        mapping = {
            "pseudo": cls.PSEUDO,
            "tool": cls.TOOL,
            "supervised": cls.SUPERVISED,
            "autonomous": cls.AUTONOMOUS,
            "delegating": cls.DELEGATING,
        }
        return mapping[s.lower()]

    def instruction_enforcement(self) -> str:
        """Return the instruction enforcement mode for this posture.

        Per ADR-010 CO Five Layers mapping:
        - TOOL: strict (missing fields = rejected)
        - SUPERVISED: moderate (retry with correction, then warn)
        - AUTONOMOUS: soft (accept partial, note missing in metadata)
        """
        if self <= AgentPosture.TOOL:
            return "strict"
        elif self == AgentPosture.SUPERVISED:
            return "moderate"
        else:
            return "soft"
```

### §2.3 BaseAgent (Slimmed)

```python
# packages/kailash-kaizen/src/kaizen/core/base_agent.py

from __future__ import annotations
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import logging
import os

from kailash.nodes.base import Node, NodeParameter
from kailash.workflow.builder import WorkflowBuilder
from kailash.trust.posture import AgentPosture

if TYPE_CHECKING:
    from kaizen.signatures import Signature
    from kailash_mcp import MCPClient, MCPServerConfig
    from kailash_mcp.tools import ToolRegistry

from .config import BaseAgentConfig

logger = logging.getLogger(__name__)

__all__ = ["BaseAgent", "BaseAgentConfig"]


class BaseAgent(Node):
    """Minimal workflow-composable agent primitive.

    Inherits from Node for workflow composition (to_workflow, get_parameters,
    NodeRegistry integration). See ADR-002 for why Node inheritance is preserved.

    CO Five Layers mapping (ADR-010):
    - Intent: signature= parameter (InputField defines request, OutputField defines response)
    - Context: _memory, _tools, MCP discovery
    - Guardrails: via L3GovernedAgent wrapper (not in BaseAgent itself)
    - Instructions: system_prompt=, signature= (enforcement varies by posture)
    - Learning: via MonitoredAgent wrapper (not in BaseAgent itself)

    For streaming / autonomous execution, wrap in StreamingAgent:
        streaming = StreamingAgent(base_agent)
        async for event in streaming.run_stream(prompt):
            ...

    For cost tracking, wrap in MonitoredAgent.
    For PACT governance, wrap in L3GovernedAgent.
    For multi-agent coordination, use SupervisorAgent/WorkerAgent.

    Extension points (DEPRECATED in v2.x, removed in v3.0):
    - _default_signature() → pass signature= parameter instead
    - _default_strategy() → use config.execution_mode instead
    - _generate_system_prompt() → pass system_prompt= parameter instead
    - _validate_signature_output() → automatic based on posture
    - _pre_execution_hook() → use composition wrappers
    - _post_execution_hook() → use composition wrappers
    - _handle_error() → use composition wrappers
    """

    def __init__(
        self,
        config: BaseAgentConfig,
        *,
        signature: Optional[type[Signature]] = None,
        tools: Optional[ToolRegistry] = None,
        memory: Optional[Any] = None,
        llm: Optional[Any] = None,
        # ─── Deprecated params (v2.x compat) ──────────
        strategy: Optional[Any] = None,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        **legacy_kwargs,
    ):
        """Create a BaseAgent.

        Args:
            config: Agent configuration (model, posture, system_prompt, etc.)
            signature: Optional Signature class for structured input/output.
                When provided, output validation uses posture-aware enforcement.
            tools: Optional ToolRegistry with pre-registered tools.
                Tools can also be added later via configure_mcp().
            memory: Optional AgentMemory instance for conversation history.
            llm: Optional pre-constructed LLM provider instance.
                If None, auto-resolved from config.model via get_provider_for_model().
        """
        # Node initialization (preserves workflow composition)
        super().__init__()

        self._config = config
        self._signature = signature

        # Resolve LLM provider (from SPEC-02)
        if llm is not None:
            self._llm = llm
        else:
            from kaizen.providers.registry import get_provider_for_model
            self._llm = get_provider_for_model(config.model) if config.model else None

        # Tool registry (from SPEC-01 — unified JSON + callable)
        if tools is not None:
            self._tools = tools
        else:
            from kailash_mcp.tools import ToolRegistry
            self._tools = ToolRegistry()

        # Memory
        self._memory = memory

        # Structured output (posture-aware, from ADR-010)
        self._structured_output = None
        if signature is not None:
            from kaizen.core.structured_output import StructuredOutput
            self._structured_output = StructuredOutput.from_signature(
                signature,
                posture=config.posture,
            )
            # Auto-set response_format on config if not already set
            if config.response_format is None and self._llm:
                from kaizen.providers.base import StructuredOutputProvider
                if isinstance(self._llm, StructuredOutputProvider):
                    schema = self._structured_output.to_json_schema()
                    config.response_format = self._llm.format_response_schema(schema)

        # Handle deprecated params
        if strategy is not None:
            import warnings
            warnings.warn(
                "BaseAgent(strategy=...) is deprecated since v2.next. "
                "Strategy selection is automatic based on config.execution_mode.",
                DeprecationWarning, stacklevel=2,
            )

        if mcp_servers is not None:
            import warnings
            warnings.warn(
                "BaseAgent(mcp_servers=...) is deprecated since v2.next. "
                "Use agent.configure_mcp(servers) after construction.",
                DeprecationWarning, stacklevel=2,
            )
            # Still honor it for backward compat
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                # Can't block in async context — defer to first run()
                self._deferred_mcp = mcp_servers
            except RuntimeError:
                asyncio.run(self._setup_mcp(mcp_servers))

        if legacy_kwargs:
            import warnings
            warnings.warn(
                f"BaseAgent got unknown kwargs: {list(legacy_kwargs.keys())}. "
                f"These may be legacy extension point parameters.",
                DeprecationWarning, stacklevel=2,
            )

    # ─── Core execution ────────────────────────────────────────────────

    def run(self, **inputs) -> Dict[str, Any]:
        """Execute agent synchronously.

        Returns:
            Dict with at least 'text' key. If signature is configured,
            also includes 'structured' key with posture-aware parsed result.
            May include 'usage' (token counts) and 'tool_calls' (list).
        """
        import asyncio
        return asyncio.run(self.run_async(**inputs))

    async def run_async(self, **inputs) -> Dict[str, Any]:
        """Execute agent asynchronously.

        The execution flow:
        1. Build messages from inputs + system_prompt + conversation history
        2. Call LLM provider (sync or async based on provider capability)
        3. If tool calls in response → execute tools → append → loop (if multi_cycle)
        4. Parse structured output (if signature configured, posture-aware)
        5. Return result dict
        """
        # Handle deferred MCP setup (from deprecated constructor param)
        if hasattr(self, '_deferred_mcp'):
            await self._setup_mcp(self._deferred_mcp)
            del self._deferred_mcp

        # Call deprecated extension points if subclass overrides them
        # (v2.x backward compat — these emit deprecation warnings)
        signature = self._signature
        if signature is None:
            sig = self._default_signature()
            if sig is not None:
                signature = sig

        system_prompt = self._config.system_prompt
        if system_prompt is None:
            prompt = self._generate_system_prompt()
            if prompt:
                system_prompt = prompt

        # Build messages
        messages = self._build_messages(inputs, system_prompt)

        # Call LLM
        from kaizen.providers.base import AsyncLLMProvider, LLMProvider
        kwargs: Dict[str, Any] = {
            "model": self._config.model,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
        }
        if self._config.response_format:
            kwargs["response_format"] = self._config.response_format
        if self._tools.count() > 0:
            kwargs["tools"] = self._tools.get_openai_tools()
        if self._config.api_key:
            kwargs["api_key"] = self._config.api_key
        if self._config.base_url:
            kwargs["base_url"] = self._config.base_url

        if isinstance(self._llm, AsyncLLMProvider):
            response = await self._llm.chat_async(messages, **kwargs)
        elif isinstance(self._llm, LLMProvider):
            response = self._llm.chat(messages, **kwargs)
        else:
            raise RuntimeError(f"Provider {self._llm} does not support chat")

        # Handle tool calls
        if response.tool_calls:
            tool_results = await self._execute_tool_calls(response.tool_calls)
            # For multi-cycle: append tool results and call LLM again
            # For single-shot: include tool results in response
            # (simplified here — full multi-cycle logic inherited from strategies)

        # Parse structured output (posture-aware)
        structured = None
        if self._structured_output and response.content:
            validation_result = self._structured_output.validate_output(response.content)
            structured = validation_result.parsed if validation_result.success else None

        # Build result
        result: Dict[str, Any] = {
            "text": response.content,
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            "structured": structured,
            "finish_reason": response.finish_reason,
        }

        # Call deprecated post-execution hook
        result = self._post_execution_hook(result)

        return result

    # ─── MCP configuration ─────────────────────────────────────────────

    async def configure_mcp(
        self,
        servers: list[Any],
    ) -> list[Any]:
        """Discover tools from MCP servers and register into ToolRegistry.

        Uses kailash_mcp.MCPClient (the single canonical client per SPEC-01).

        Args:
            servers: List of MCPServerConfig dicts or objects.

        Returns:
            List of discovered McpToolInfo instances.
        """
        return await self._setup_mcp(servers)

    async def _setup_mcp(self, servers: list) -> list:
        from kailash_mcp import MCPClient
        from kailash_mcp.transports import StdioTransport

        all_tools = []
        for server_config in servers:
            if isinstance(server_config, dict):
                transport = StdioTransport(
                    command=server_config["command"],
                    args=server_config.get("args", []),
                    env=server_config.get("env", {}),
                )
                name_prefix = f"{server_config.get('name', 'mcp')}_"
            else:
                transport = StdioTransport(
                    command=server_config.command,
                    args=server_config.args,
                    env=getattr(server_config, 'env', {}),
                )
                name_prefix = f"{server_config.name}_"

            client = MCPClient(transport=transport)
            await client.start()
            tools = await client.discover_and_register(
                self._tools,
                name_prefix=name_prefix,
            )
            all_tools.extend(tools)

        return all_tools

    # ─── Message building ──────────────────────────────────────────────

    def _build_messages(self, inputs: dict, system_prompt: Optional[str]) -> list:
        from kaizen.providers.types import Message

        messages = []
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))

        # Add user input
        if "prompt" in inputs:
            messages.append(Message(role="user", content=str(inputs["prompt"])))
        elif "query" in inputs:
            messages.append(Message(role="user", content=str(inputs["query"])))
        elif "message" in inputs:
            messages.append(Message(role="user", content=str(inputs["message"])))
        else:
            # Build from all inputs
            content = "\n".join(f"{k}: {v}" for k, v in inputs.items())
            messages.append(Message(role="user", content=content))

        return messages

    # ─── Tool execution ────────────────────────────────────────────────

    async def _execute_tool_calls(self, tool_calls: list) -> list:
        """Execute tool calls via the unified ToolRegistry."""
        import asyncio
        import json

        results = []
        for tc in tool_calls:
            name = tc.function.name if hasattr(tc, 'function') else tc.get("function", {}).get("name", "")
            args_str = tc.function.arguments if hasattr(tc, 'function') else tc.get("function", {}).get("arguments", "{}")

            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
                result = await self._tools.execute(name, args)
                results.append({"tool": name, "result": result, "success": True})
            except Exception as e:
                logger.error("Tool execution failed: %s: %s", name, e)
                results.append({"tool": name, "error": str(e), "success": False})

        return results

    # ─── Node interface (workflow composition) ─────────────────────────

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Return parameters for workflow integration."""
        params = {}
        if self._signature:
            from kaizen.signatures import InputField
            for field_name, field_obj in self._signature.__fields__.items():
                if isinstance(field_obj, InputField):
                    params[field_name] = NodeParameter(
                        name=field_name,
                        type="string",
                        required=True,
                        description=getattr(field_obj, 'desc', ''),
                    )
        return params

    def to_workflow(self):
        """Convert agent to a Core SDK Workflow for integration."""
        builder = WorkflowBuilder()
        # ... workflow construction from signature/tools ...
        return builder.build()

    # ─── DEPRECATED extension points (v2.x only) ──────────────────────
    # These methods are preserved for backward compat with 188 subclasses.
    # Each emits DeprecationWarning when called.
    # Removed in v3.0.

    from kailash._deprecation import deprecated

    @deprecated(
        since="2.next", removed_in="3.0",
        use_instead="pass signature= parameter to BaseAgent.__init__",
    )
    def _default_signature(self) -> Optional[Any]:
        """DEPRECATED: Provide agent-specific signature."""
        return None

    @deprecated(
        since="2.next", removed_in="3.0",
        use_instead="use config.execution_mode parameter",
    )
    def _default_strategy(self) -> Optional[Any]:
        """DEPRECATED: Select execution strategy."""
        return None

    @deprecated(
        since="2.next", removed_in="3.0",
        use_instead="pass system_prompt= parameter to BaseAgent.__init__",
    )
    def _generate_system_prompt(self) -> str:
        """DEPRECATED: Customize LLM system prompt."""
        return ""

    @deprecated(
        since="2.next", removed_in="3.0",
        use_instead="signature validation is automatic based on posture (ADR-010)",
    )
    def _validate_signature_output(self, output: Dict[str, Any]) -> bool:
        """DEPRECATED: Validate LLM output against schema."""
        return True

    @deprecated(
        since="2.next", removed_in="3.0",
        use_instead="use L3GovernedAgent or MonitoredAgent wrapper",
    )
    def _pre_execution_hook(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """DEPRECATED: Custom pre-execution logic."""
        return inputs

    @deprecated(
        since="2.next", removed_in="3.0",
        use_instead="use MonitoredAgent or custom wrapper",
    )
    def _post_execution_hook(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """DEPRECATED: Custom post-execution logic."""
        return result

    @deprecated(
        since="2.next", removed_in="3.0",
        use_instead="use custom error-handling wrapper",
    )
    def _handle_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """DEPRECATED: Custom error handling."""
        raise error

    # ─── Introspection ─────────────────────────────────────────────────

    @property
    def config(self) -> BaseAgentConfig:
        return self._config

    @property
    def signature(self) -> Optional[Any]:
        return self._signature

    @property
    def tools(self) -> ToolRegistry:
        return self._tools

    @property
    def posture(self) -> AgentPosture:
        return self._config.posture

    def close(self) -> None:
        """Release resources (MCP connections, HTTP clients, etc.)."""
        # Cleanup MCP clients if any
        pass
```

## §3 Semantics

### §3.1 What Was Removed (Moved to Primitives/Wrappers)

| Removed from BaseAgent                                 | Moved to                              | Lines saved |
| ------------------------------------------------------ | ------------------------------------- | ----------- |
| MCP client initialization + tool discovery             | `kailash_mcp.MCPClient` (SPEC-01)     | ~800 LOC    |
| `convert_mcp_to_openai_tools()` + tool formatting      | `kailash_mcp.tools.ToolRegistry`      | ~200 LOC    |
| `_execute_mcp_tool_call()` + `_execute_regular_tool()` | `ToolRegistry.execute()`              | ~200 LOC    |
| `_execute_tool_calls()` dispatcher (mcp vs regular)    | Unified in `ToolRegistry.execute()`   | ~150 LOC    |
| Provider initialization (OpenAI, Anthropic, etc.)      | `kaizen.providers.registry` (SPEC-02) | ~300 LOC    |
| Mixin application (7 mixins)                           | Composition wrappers (SPEC-03)        | ~100 LOC    |
| Strategy selection + delegation                        | Config-driven + wrappers              | ~200 LOC    |
| A2A agent card generation                              | Separate utility (not in core path)   | ~150 LOC    |
| Observability setup                                    | MonitoredAgent wrapper                | ~100 LOC    |
| Permission system                                      | L3GovernedAgent wrapper               | ~200 LOC    |
| Hook system                                            | StreamingAgent + HookManager          | ~100 LOC    |

**Total removed**: ~2,500 LOC → BaseAgent shrinks from 3,698 to ~1,200 LOC

### §3.2 What Was Added

| New in BaseAgent                    | Purpose                                              | Lines   |
| ----------------------------------- | ---------------------------------------------------- | ------- |
| `posture` field on config           | CO Five Layers instruction enforcement (ADR-010)     | ~20 LOC |
| `configure_mcp()` method            | Replaces inline MCP setup with kailash_mcp.MCPClient | ~30 LOC |
| Posture-aware `StructuredOutput`    | Auto-sets validation mode from posture               | ~20 LOC |
| Deprecation decorators on 7 methods | `@deprecated` with migration guidance                | ~50 LOC |

### §3.3 How Subclass Extension Points Still Work

The 188 existing subclasses override methods like:

```python
class ReActAgent(BaseAgent):
    def _default_strategy(self):
        return MultiCycleStrategy(max_cycles=10)

    def _generate_system_prompt(self):
        return "You are a ReAct agent. Think step by step..."
```

After slimming, these STILL WORK in v2.x:

1. `BaseAgent.__init__` checks `self._default_signature()` — if the subclass overrides it, the override runs (with deprecation warning)
2. The returned signature is used to configure `StructuredOutput`
3. Similarly for `_generate_system_prompt()` — if overridden, the custom prompt is used (with warning)
4. Similarly for `_default_strategy()` — if overridden, the custom strategy is applied (with warning)

The deprecation warnings guide users to migrate:

```
DeprecationWarning: ReActAgent._default_strategy is deprecated since v2.next.
Use instead: use config.execution_mode parameter.
Removed in v3.0.
```

### §3.4 Posture-Aware Structured Output

When `signature` is provided and `posture` is set:

```python
agent = BaseAgent(
    config=BaseAgentConfig(model="claude-sonnet-4-5", posture=AgentPosture.AUTONOMOUS),
    signature=FinancialReport,
)
```

The `StructuredOutput.from_signature(FinancialReport, posture=AgentPosture.AUTONOMOUS)` creates a validator that uses **soft enforcement**:

- Missing fields → accepted with metadata warning
- Type mismatches → best-effort coercion
- Extra fields → kept (agent may produce useful context beyond schema)

Versus the default `TOOL` posture:

```python
agent = BaseAgent(
    config=BaseAgentConfig(model="claude-sonnet-4-5"),  # posture defaults to TOOL
    signature=ContentUpdate,
)
```

Creates a validator with **strict enforcement**:

- Missing fields → `SignatureValidationError` (rejected)
- Type mismatches → `SignatureValidationError`
- Extra fields → stripped

## §4 Backward Compatibility

### Import path preservation

```python
# The canonical import stays:
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

# These also work (no path change):
from kaizen.core.config import BaseAgentConfig
```

### Constructor backward compat

The constructor accepts deprecated params via `**legacy_kwargs`:

```python
# Old code (v1.x / v2.x):
agent = BaseAgent(
    config=cfg,
    strategy=MultiCycleStrategy(),        # deprecated, warns
    mcp_servers=[...],                     # deprecated, warns
)

# New code (v2.next+):
agent = BaseAgent(
    config=BaseAgentConfig(model="...", execution_mode="multi_cycle"),
    signature=MySig,
)
agent.configure_mcp([...])
```

### Extension point backward compat

```python
# Old subclass code (still works in v2.x, deprecated):
class MyAgent(BaseAgent):
    def _default_signature(self):          # emits DeprecationWarning
        return MySignature
    def _generate_system_prompt(self):     # emits DeprecationWarning
        return "Custom prompt"

# New equivalent (v2.next+):
agent = BaseAgent(
    config=cfg,
    signature=MySignature,
    system_prompt="Custom prompt",
)
```

## §5 Migration Order

1. **Add `AgentPosture` to `kailash.trust.posture`** (alongside existing `TrustPosture`)
2. **Add `posture` field to `BaseAgentConfig`** (default `TOOL` — zero impact on existing code)
3. **Update `StructuredOutput.from_signature()`** to accept `posture` parameter
4. **Add `@deprecated` decorator** to `kailash/_deprecation.py`
5. **Apply `@deprecated`** to all 7 extension points in BaseAgent
6. **Refactor BaseAgent constructor** to use `kaizen.providers.registry.get_provider_for_model()` (depends on SPEC-02 complete)
7. **Refactor BaseAgent MCP setup** to use `kailash_mcp.MCPClient.discover_and_register()` (depends on SPEC-01 complete)
8. **Replace inline ToolRegistry** with `kailash_mcp.tools.ToolRegistry` (depends on SPEC-01 complete)
9. **Remove mixin application code** (mixins deprecated, capabilities moved to wrappers)
10. **Remove inline strategy selection** (execution_mode drives behavior instead)
11. **Remove inline observability/permission/hook setup** (moved to wrappers)
12. **Add `configure_mcp()` public method** (replaces deprecated `mcp_servers=` param)
13. **Run full BaseAgent test suite** (~600 tests) — verify zero regressions
14. **Run 188 subclass tests** — verify deprecated extension points still work with warnings
15. **Add new tests** for posture-aware validation, new constructor params, configure_mcp()

## §6 Test Plan

### Existing tests (~600)

All must pass unchanged. Expected new output: `DeprecationWarning` messages for any test that exercises extension points or deprecated params. Tests are NOT modified — only the warnings appear.

### Subclass compatibility tests

```python
def test_subclass_with_deprecated_extension_points_still_works():
    """v2.x backward compat: subclasses that override extension points."""

    class OldStyleAgent(BaseAgent):
        def _default_signature(self):
            return TestSignature

        def _generate_system_prompt(self):
            return "Custom prompt for test"

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        agent = OldStyleAgent(config=BaseAgentConfig(model="mock"))
        result = agent.run(query="test")

        # Works — extension points were called
        assert result is not None

        # Deprecation warnings were emitted
        dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
        assert len(dep_warnings) >= 2  # at least signature + prompt
```

### New tests

```python
def test_posture_aware_strict_validation():
    agent = BaseAgent(
        config=BaseAgentConfig(model="mock", posture=AgentPosture.TOOL),
        signature=StrictSig,
    )
    # Mock LLM returns incomplete output
    with pytest.raises(SignatureValidationError):
        agent.run(query="test")

def test_posture_aware_soft_validation():
    agent = BaseAgent(
        config=BaseAgentConfig(model="mock", posture=AgentPosture.AUTONOMOUS),
        signature=SoftSig,
    )
    # Mock LLM returns incomplete output — accepted with warning
    result = agent.run(query="test")
    assert result["structured"] is not None  # partial result accepted
    assert "_validation_warnings" in result.get("metadata", {})

def test_configure_mcp_registers_tools():
    agent = BaseAgent(config=BaseAgentConfig(model="mock"))
    # configure_mcp discovers tools and registers with callable executors
    tools = asyncio.run(agent.configure_mcp([test_mcp_server_config()]))
    assert len(tools) > 0
    assert agent.tools.count() > 0
    assert agent.tools.has_executor(tools[0].name)

def test_posture_default_is_tool():
    config = BaseAgentConfig(model="test")
    assert config.posture == AgentPosture.TOOL

def test_posture_from_envelope_ceiling():
    """L3GovernedAgent can lower posture via envelope."""
    agent = BaseAgent(
        config=BaseAgentConfig(model="mock", posture=AgentPosture.AUTONOMOUS),
    )
    envelope = ConstraintEnvelope(posture_ceiling=AgentPosture.SUPERVISED)
    governed = L3GovernedAgent(agent, envelope=envelope)
    # Posture lowered to SUPERVISED (envelope ceiling < AUTONOMOUS)
    assert governed._config.posture == AgentPosture.SUPERVISED
```

## §7 Related Specs

- **SPEC-01** (kailash-mcp): MCPClient + ToolRegistry consumed by BaseAgent
- **SPEC-02** (Provider layer): `get_provider_for_model()` consumed by BaseAgent constructor
- **SPEC-03** (Composition wrappers): wrappers stack on top of BaseAgent
- **SPEC-05** (Delegate facade): Delegate constructs BaseAgent as the inner primitive
- **SPEC-07** (ConstraintEnvelope): gains `posture_ceiling` field (consumed by L3GovernedAgent)

## §8 Rust Parallel

Rust's `BaseAgent` is already minimal (2 methods). The convergence adds:

1. `AgentPosture` (or expand `ExecutionMode` to full posture spectrum) on `AgentConfig`
2. Posture-aware structured output validation in `StructuredOutput::process()`

These are additive changes to Rust — no refactoring needed because Rust never had the 7-extension-point pattern.

## §9 Cross-SDK Semantic Parity

| Aspect              | Python                                                 | Rust                                                        |
| ------------------- | ------------------------------------------------------ | ----------------------------------------------------------- |
| BaseAgent interface | `run(**inputs) -> Dict`, `run_async(**inputs) -> Dict` | `run(input: &str) -> Result<AgentResult>`                   |
| Node inheritance    | Yes (`class BaseAgent(Node)`)                          | No (trait-based, separate `AgentAsNode` adapter)            |
| Posture             | `AgentPosture` IntEnum on `BaseAgentConfig`            | `ExecutionMode` (expand to full spectrum) on `AgentConfig`  |
| Structured output   | `StructuredOutput.from_signature(sig, posture=)`       | `StructuredOutput::process()` with posture-aware validation |
| Extension points    | 7 deprecated methods (v2.x)                            | None (Rust never had them)                                  |
| Tool registry       | `kailash_mcp.tools.ToolRegistry`                       | `kailash_kaizen::agent::tools::ToolRegistry`                |
| MCP integration     | `configure_mcp() → MCPClient.discover_and_register()`  | `McpClient::discover_and_register()`                        |

## §10 Security Considerations

BaseAgent is the primitive every agent in the platform stacks on top of. Vulnerabilities here propagate to every wrapper, multi-agent pattern, and Delegate consumer. Five threat surfaces are specific to the slimming work in this spec.

### §10.1 Deferred MCP Configuration Window

**Threat**: The `_deferred_mcp: Optional[List[MCPServerConfig]]` pattern stores server configurations on the agent instance between construction and the first `run()` call. Any code path with access to the agent instance during this window (decorators, middleware, fixtures, `__init_subclass__` hooks) can mutate the deferred list to add an attacker-controlled MCP server. The agent then connects to that server on first run, fetches and registers malicious tools, and the LLM calls them as if they were legitimate.

**Mitigations**:

1. `_deferred_mcp` MUST be stored as a `tuple`, not `list`, making mutation require explicit replacement.
2. The field is prefixed `_` — BaseAgent MUST raise `AttributeError` on external write attempts via a `__setattr__` guard that allows `_deferred_mcp` to be set only from within `configure_mcp()` or `__init__()`.
3. On first `run()`, BaseAgent MUST log the full list of deferred MCP server URLs to the audit store before connecting. An audit trail of what was connected provides post-hoc detection.
4. `configure_mcp()` after the first run MUST raise `RuntimeError("MCP configuration is frozen after first run")` — no late addition.

### §10.2 `**legacy_kwargs` Catch-All Accepting Unsafe Parameters

**Threat**: BaseAgent accepts `**legacy_kwargs` to preserve backward compatibility with 188 existing subclasses. An attacker who can influence agent construction (e.g., a factory that builds agents from user config) could pass arbitrary keyword arguments that silently reach deprecated-but-still-honored code paths (e.g., `enable_raw_tool_calls=True`, `trust_external_tool_results=True`, or a renamed internal flag from the v1 codebase).

**Mitigations**:

1. `legacy_kwargs` MUST be filtered through an explicit allowlist — any key not in the allowlist raises `UnknownParameterError`.
2. The allowlist is defined in `kaizen.core.base_agent._DEPRECATED_PARAMETERS: frozenset[str]` and is frozen at module load.
3. Each allowlisted key emits a `DeprecationWarning` on use, so subclass authors migrate.
4. Every accepted legacy key is recorded in the agent's `construction_audit` attribute for post-hoc security review.

### §10.3 Posture Field Tampering

**Threat**: `BaseAgentConfig.posture` determines validation strictness (PSEUDO/TOOL → strict, AUTONOMOUS/DELEGATING → soft). If an attacker can flip an agent's posture from TOOL to DELEGATING after construction (via direct `agent._config.posture = ...`), the signature validation softens and malformed LLM output (potentially injected) is accepted.

**Mitigations**:

1. `BaseAgentConfig` MUST be a frozen dataclass (`@dataclass(frozen=True)`). Any mutation attempt raises `FrozenInstanceError`.
2. BaseAgent MUST store the posture at `self._posture: AgentPosture` as a private copy; the `_config` reference is read-only.
3. Integration tests verify `agent._posture` cannot be changed after construction.
4. SPEC-07 §9.1 enforces posture validation at deserialization (the related entry point).

### §10.4 Extension Point Deprecation Shadow Hooks

**Threat**: The 7 deprecated extension points (`before_llm_call`, `after_llm_call`, etc.) are kept for v2.x backward compatibility via the `@deprecated` decorator. An attacker who can subclass BaseAgent in user code can override a deprecated hook and intercept every LLM call silently — the hook runs despite the deprecation warning.

**Mitigations**:

1. Deprecated hooks MUST NOT have access to the raw LLM request/response bodies — the hook signature passes only a read-only `HookContext` with `prompt_hash`, `model_name`, `call_id`. No content.
2. Hook execution is recorded in the audit store with the subclass name, so subclass overrides are visible.
3. The `@deprecated` decorator MUST raise (not warn) when the agent's posture is PSEUDO or TOOL — tight postures refuse any deprecated path.
4. In v3.0 the hooks are removed entirely; v2.x retention is short-lived.

### §10.5 `_build_messages()` Input Key Fallback

**Threat** (related to R2-009): The input-key fallback chain (`prompt` → `query` → `message` → stringified dict) was designed for developer ergonomics but means a signature-less agent accepts any input shape. An attacker who can influence the `inputs` dict (e.g., via a Nexus channel that passes user data straight to `agent.run(**body)`) could bypass intended input validation by using a key the agent silently forwards.

**Mitigations**:

1. When a Signature is configured, `_build_messages()` MUST use ONLY the Signature's InputField names — the `prompt`/`query`/`message` fallback applies only to signature-less agents.
2. Signature-less agents MUST emit a `DeprecationWarning` on every `run()` call that uses the fallback, encouraging signature adoption.
3. Nexus channels (SPEC-06) that forward request bodies to agents MUST require a signature; signature-less passthrough is refused at the channel boundary.
4. Regression test reproduces the ambiguity case: `agent.run(prompt="A", query="B")` MUST raise `AmbiguousInputError` when both keys are present and no signature disambiguates.
