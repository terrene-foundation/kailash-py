# ADR-007: Delegate as Composition Facade

**Status**: ACCEPTED (2026-04-07)
**Scope**: Kaizen (kaizen-agents)
**Deciders**: Platform Architecture Convergence workspace

## Context

Today, Python's `Delegate` (at `packages/kaizen-agents/src/kaizen_agents/delegate/delegate.py`) is a **parallel implementation** of autonomous agent execution. It has:

- Its own `AgentLoop` (TAOD loop)
- Its own multi-provider streaming adapters (4 files in `delegate/adapters/`)
- Its own `McpClient` (509 LOC in `delegate/mcp.py`)
- Its own `ToolRegistry` with callable executors
- Its own typed event stream (`DelegateEvent`)
- Its own budget tracking
- Its own hook system
- Its own tool hydration (BM25)

**It does NOT compose `BaseAgent`**. It lives in a separate package (`kaizen-agents`) and shares zero code with BaseAgent (which lives in `kailash-kaizen`). The architectural invariant in `delegate/loop.py:14-16` states:

> "Architectural invariant: the kz core loop MUST NOT use Kaizen Pipeline primitives."

This was an intentional decision when Delegate was built — BaseAgent's Node inheritance and workflow-oriented execution model are incompatible with streaming autonomous loops.

### The cost of the parallel stack

- **Capability fragmentation**: BaseAgent has structured outputs (Signatures). Delegate has streaming + working MCP. Users can't have both.
- **Two LLM provider implementations**: the monolith in `ai_providers.py` (BaseAgent) and clean adapters in `delegate/adapters/` (Delegate).
- **Two MCP clients**: the production-grade one in `kailash.mcp_server.client` (BaseAgent, broken via #339) and the 509-line stdio-only one in `delegate/mcp.py` (Delegate, working).
- **Two tool registries**: JSON schemas (BaseAgent) and callable executors (Delegate).
- **Bug #340**: Delegate calls Gemini with `response_format + tools`, crashes on Gemini 2.5 because there's no mutual-exclusion check. The equivalent check exists in BaseAgent's provider but not in Delegate's.

### Rust's approach

Rust has `DelegateEngine` in `crates/kaizen-agents/src/delegate_engine.rs`. It **composes** existing primitives:

```rust
pub struct DelegateEngine {
    agent: Option<Agent>,                   // concrete BaseAgent impl
    taod: Option<TaodRunner>,               // TAOD execution loop
    supervisor: Option<GovernedSupervisor>, // execution-plane governance
    pact: Option<PactEngine>,               // policy-plane governance
    llm_client: Option<Arc<LlmClient>>,     // shared LLM
    hydrator: Option<Arc<dyn ToolHydrator>>,// progressive tool disclosure
}
```

`Agent` is a primitive that implements BaseAgent. `TaodRunner` is the autonomous loop. Both use the ONE `LlmClient` from `kailash-kaizen::llm::client`. The ONE `McpClient` from `kailash-kaizen::mcp::client`. No duplication.

`DelegateEngine.run()` delegates to `TaodRunner.run()`, which uses `Agent`'s configured LLM + tools + memory. **Streaming comes from composing `StreamingAgent(Agent)`**. Governance comes from composing `L3GovernedAgent(Agent)` or wrapping in `GovernedSupervisor`. Budget comes from composing `MonitoredAgent(Agent)`. Everything is composition.

## Decision

**Python's `Delegate` becomes a thin composition facade that internally constructs a stack of primitives: `BaseAgent` (the core) wrapped with `MonitoredAgent` / `L3GovernedAgent` / `StreamingAgent` as needed. It shares zero code with a parallel implementation because it IS the composition. The user-facing `Delegate(...)` API is preserved.**

### Target implementation

```python
# packages/kaizen-agents/src/kaizen_agents/delegate.py

from __future__ import annotations
from typing import AsyncGenerator, Optional, Any
import os

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import Signature
from kaizen.core.agent_loop import AgentLoop, AgentLoopConfig
from kaizen_agents.streaming_agent import StreamingAgent
from kaizen_agents.monitored_agent import MonitoredAgent
from kaizen_agents.l3_governed_agent import L3GovernedAgent
from kaizen_agents.events import (
    DelegateEvent, TextDelta, ToolCallStart, ToolCallEnd,
    TurnComplete, BudgetExhausted, ErrorEvent,
)
from kailash.trust import ConstraintEnvelope
from kailash_mcp import MCPClient, MCPServerConfig


class Delegate:
    """Engine facade for autonomous AI execution.

    Delegate composes the kaizen primitive stack:

        BaseAgent (core primitive)
          → MonitoredAgent (budget tracking wrapper)
            → L3GovernedAgent (PACT envelope wrapper)
              → StreamingAgent (event stream wrapper)

    The user-facing API is unchanged from v2.x. The internal implementation
    is a composition of wrappers rather than a parallel stack.

    Progressive disclosure layers (preserved from v2.x):

    Layer 1 — minimal::

        delegate = Delegate(model="claude-sonnet-4-5")
        async for event in delegate.run(prompt="hello"):
            print(event)

    Layer 2 — configured::

        delegate = Delegate(
            model="claude-sonnet-4-5",
            signature=MyOutputSignature,   # NEW: structured outputs work now
            tools=[file_read, file_write],
            system_prompt="You are a code reviewer.",
            max_turns=20,
        )

    Layer 3 — governed::

        delegate = Delegate(
            model="claude-sonnet-4-5",
            signature=MyOutputSignature,
            mcp_servers=[
                MCPServerConfig(name="fs", command="npx", args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
            ],
            budget_usd=10.0,                  # MonitoredAgent wrapper
            envelope=my_envelope,             # L3GovernedAgent wrapper
        )
    """

    def __init__(
        self,
        model: str = "",
        *,
        # Core agent config
        signature: Optional[type[Signature]] = None,
        tools: Optional[list[Any]] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_turns: int = 50,

        # MCP integration
        mcp_servers: Optional[list[MCPServerConfig]] = None,

        # Governance wrappers
        budget_usd: Optional[float] = None,
        envelope: Optional[ConstraintEnvelope] = None,

        # Provider config
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,

        # Advanced escape hatch
        inner_agent: Optional[BaseAgent] = None,
    ):
        """Create a Delegate.

        Args:
            model: LLM model name. Falls back to DEFAULT_LLM_MODEL env var.
            signature: Optional Signature class for structured outputs.
                When provided, TurnComplete.structured carries the typed result.
            tools: List of callable tools or ToolDef instances.
            system_prompt: Override default system prompt.
            temperature: LLM temperature.
            max_tokens: Max tokens per turn.
            max_turns: Max TAOD iterations per run().
            mcp_servers: MCP server configs for tool discovery.
            budget_usd: Optional USD budget cap. When set, wraps inner
                agent in MonitoredAgent (cost tracked via kailash.trust.BudgetTracker).
            envelope: Optional PACT constraint envelope. When set, wraps
                inner agent in L3GovernedAgent.
            api_key: Per-request API key override (BYOK multi-tenant).
            base_url: Per-request base URL override.
            inner_agent: Advanced: provide a pre-constructed BaseAgent.
                Bypasses the default construction. Used for testing and
                for users who need extension beyond what Delegate exposes.
        """
        # Resolve model from env if not provided
        resolved_model = model or os.environ.get("DEFAULT_LLM_MODEL", "")
        if not resolved_model:
            raise ValueError(
                "model is required. Pass explicitly or set DEFAULT_LLM_MODEL env var."
            )

        # ─── Build the primitive stack ───

        if inner_agent is not None:
            # Advanced user provided a pre-built agent
            core = inner_agent
        else:
            # Default: construct from config
            config = BaseAgentConfig(
                model=resolved_model,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=api_key,
                base_url=base_url,
            )

            core = BaseAgent(
                config=config,
                signature=signature,
                tools=self._resolve_tools(tools),
            )

            # MCP servers integrate via shared kailash-mcp client
            if mcp_servers:
                core.configure_mcp(mcp_servers)  # adds tools from MCP servers

        # ─── Wrap with capabilities (outer → inner stacking order) ───

        current: BaseAgent = core

        if budget_usd is not None:
            current = MonitoredAgent(current, budget_usd=budget_usd)

        if envelope is not None:
            current = L3GovernedAgent(current, envelope=envelope)

        # Streaming wrapper is ALWAYS outermost — it provides the run_stream() API
        self._streaming = StreamingAgent(
            current,
            loop_config=AgentLoopConfig(
                max_turns=max_turns,
                streaming=True,
            ),
        )

        # Keep reference to the inner (unwrapped) agent for introspection
        self._core = core

    # ─── Public API (v2.x preserved) ───────────────────────────────────

    async def run(
        self,
        prompt: Optional[str] = None,
        **inputs: Any,
    ) -> AsyncGenerator[DelegateEvent, None]:
        """Execute autonomously, yielding typed events.

        Args:
            prompt: Simple prompt (equivalent to inputs={"prompt": prompt}).
            **inputs: Named inputs matching the signature (if one is provided).

        Yields:
            DelegateEvent instances. Pattern-match on event type:
            - TextDelta(text): incremental text tokens
            - ToolCallStart(call_id, name, arguments): tool invocation beginning
            - ToolCallEnd(call_id, name, result, error): tool invocation complete
            - TurnComplete(text, usage, structured): turn ended naturally;
              structured field carries Signature-parsed result if signature was provided
            - BudgetExhausted(budget_usd, consumed_usd): budget cap hit
            - ErrorEvent(error, details): exception during execution

        Examples:

            async for event in delegate.run(prompt="Summarize this file."):
                match event:
                    case TextDelta(text=t):
                        print(t, end="", flush=True)
                    case TurnComplete(text=t, structured=None):
                        print("\\n[done]")
                    case TurnComplete(text=t, structured=result):
                        print(f"\\n[done] result: {result}")
                    case BudgetExhausted(consumed_usd=c):
                        print(f"\\n[budget] spent ${c}")
                    case ErrorEvent(error=e):
                        print(f"\\n[error] {e}")
        """
        # Normalize inputs
        if prompt is not None and not inputs:
            inputs = {"prompt": prompt}
        elif prompt is not None and inputs:
            inputs = {"prompt": prompt, **inputs}

        async for event in self._streaming.run_stream(**inputs):
            yield event

    def run_sync(self, prompt: Optional[str] = None, **inputs: Any) -> str:
        """Blocking execution — returns final text.

        For users who just want the string result without handling the
        event stream.
        """
        import asyncio

        async def _collect():
            final = ""
            async for event in self.run(prompt=prompt, **inputs):
                if isinstance(event, TextDelta):
                    final += event.text
                elif isinstance(event, TurnComplete):
                    return event.text
                elif isinstance(event, ErrorEvent):
                    raise DelegateError(event.error)
            return final

        return asyncio.run(_collect())

    def interrupt(self) -> None:
        """Request graceful interrupt of running execution."""
        self._streaming._loop.request_interrupt()

    def close(self) -> None:
        """Release MCP subprocesses, HTTP connections, etc."""
        self._core.close()

    # ─── Introspection ─────────────────────────────────────────────────

    @property
    def core_agent(self) -> BaseAgent:
        """The innermost (unwrapped) BaseAgent. Advanced use."""
        return self._core

    @property
    def streaming_agent(self) -> StreamingAgent:
        """The outermost wrapper (streaming-enabled). Advanced use."""
        return self._streaming

    @property
    def consumed_usd(self) -> Optional[float]:
        """Total USD consumed so far. None if budget tracking is disabled."""
        return self._get_monitored().consumed_usd if self._has_wrapper(MonitoredAgent) else None

    @property
    def budget_remaining(self) -> Optional[float]:
        return self._get_monitored().budget_remaining if self._has_wrapper(MonitoredAgent) else None

    def _has_wrapper(self, wrapper_cls: type[BaseAgent]) -> bool:
        current = self._streaming
        while current is not None:
            if isinstance(current, wrapper_cls):
                return True
            current = getattr(current, '_inner', None)
        return False

    def _get_monitored(self) -> MonitoredAgent:
        current = self._streaming
        while current is not None:
            if isinstance(current, MonitoredAgent):
                return current
            current = getattr(current, '_inner', None)
        raise RuntimeError("No MonitoredAgent in stack")
```

### Deleted files (after this ADR)

- `packages/kaizen-agents/src/kaizen_agents/delegate/loop.py` → **moved** to `packages/kailash-kaizen/src/kaizen/core/agent_loop.py` (and made a shared primitive)
- `packages/kaizen-agents/src/kaizen_agents/delegate/mcp.py` → **deleted** (consumers use `kailash_mcp.MCPClient`)
- `packages/kaizen-agents/src/kaizen_agents/delegate/adapters/` → **deleted** (consumers use `kaizen.providers.*`)
- `packages/kaizen-agents/src/kaizen_agents/delegate/tools/hydrator.py` → **moved** to `packages/kailash-mcp/src/kailash_mcp/tools/hydrator.py`

### Preserved files

- `packages/kaizen-agents/src/kaizen_agents/delegate/events.py` → renamed/moved to `packages/kaizen-agents/src/kaizen_agents/events.py` (same DelegateEvent dataclass hierarchy)
- `packages/kaizen-agents/src/kaizen_agents/delegate/hooks.py` → moved to `packages/kaizen-agents/src/kaizen_agents/hooks.py`
- Public API `Delegate(...)` constructor — **IDENTICAL** to v2.x plus new `signature=` and `envelope=` parameters

## Rationale

1. **Eliminates the parallel stack.** Delegate is no longer a separate implementation — it's a composition of existing primitives. ~1,500 LOC of duplication removed.

2. **Resolves capability fragmentation.** Users can now get:
   - Streaming (via StreamingAgent wrapper)
   - Structured outputs (via Signature on inner BaseAgent)
   - MCP tools (via shared kailash_mcp.MCPClient)
   - Budget tracking (via MonitoredAgent wrapper)
   - PACT governance (via L3GovernedAgent wrapper)
   - ... all at the same time, in a single `Delegate(...)` call.

3. **Matches Rust's DelegateEngine pattern exactly.** Rust already has this composition — Python converges.

4. **Fixes #339 as side-effect.** Delegate's MCP works through the shared `kailash_mcp.MCPClient`, not through the broken BaseAgent MCP path.

5. **Fixes #340 as side-effect.** The Gemini provider's mutual-exclusion check (for structured_output + tools) lives in `kaizen.providers.google`, used by BaseAgent. Delegate now uses the same provider.

6. **Preserves the v2.x public API.** Users who call `Delegate(model="...", tools=[...], budget_usd=10.0)` get identical behavior. The `run()` method still yields `DelegateEvent` instances. Progressive disclosure layers (L1/L2/L3) are preserved.

7. **`inner_agent` escape hatch** gives advanced users a way to bypass Delegate's default construction if they need a pre-built BaseAgent (e.g., for testing, or for users who extended BaseAgent in unusual ways).

8. **The AgentLoop "architectural invariant" is preserved**, just rehomed. AgentLoop now lives in `kailash-kaizen` as `kaizen.core.agent_loop`. It still MUST NOT use workflow primitives — but "workflow primitives" now means `WorkflowBuilder` / `LocalRuntime`, not "anything in kailash-kaizen." The invariant is clearer after the move.

## Consequences

### Positive

- ✅ **One implementation** of autonomous execution (composition of primitives)
- ✅ **Structured outputs + streaming** both work (case 2 from user question resolved)
- ✅ **Working MCP + structured outputs** both work simultaneously
- ✅ **Budget + streaming + MCP + governance** all compose in one Delegate call
- ✅ Bug #339 fixed as side-effect
- ✅ Bug #340 fixed as side-effect
- ✅ v2.x public API preserved — no user-facing breakage
- ✅ ~1,500 LOC of duplication removed (Delegate loop, adapters, MCP client)
- ✅ Matches Rust architecture (cross-SDK parity)
- ✅ New `signature=` parameter gives Delegate users structured outputs (new capability)
- ✅ New `envelope=` parameter gives Delegate users PACT governance (new capability)

### Negative

- ❌ `delegate/loop.py` has to be moved to `kaizen.core.agent_loop` — import path breaking. Backward-compat shim at old location with deprecation warning.
- ❌ `delegate/adapters/` deleted — internal refactor, not publicly exposed, but any test that directly imports from `delegate.adapters.*` will break.
- ❌ `delegate/mcp.py` deleted — tests that use Delegate's McpClient directly will break (they should migrate to `kailash_mcp.MCPClient`).
- ❌ `delegate/tools/hydrator.py` moved — import path breaking.
- ❌ Full Delegate test suite (~100+ tests per delegate-audit) must be verified against the new composition stack. Any test that relied on internal behavior of the old loop/adapter/MCP code will need rewriting.
- ❌ Advanced users who constructed their own `AgentLoop` directly (bypassing Delegate) have to update imports.

### Neutral

- `DelegateEvent` hierarchy unchanged (the existing dataclasses are re-used).
- `HookManager` from `delegate/hooks.py` moves to `kaizen_agents/hooks.py` but semantics unchanged.
- `GovernedSupervisor` (the PACT wrapper) still works — it's now consumed by `L3GovernedAgent` rather than living inside Delegate directly.

## Alternatives Considered

### Alternative 1: Keep Delegate as parallel stack, fix its bugs independently

**Rejected**. Maintains capability fragmentation forever. Users still have to pick BaseAgent (signatures) or Delegate (streaming). Does not fix the fundamental architectural problem.

### Alternative 2: Make Delegate a subclass of BaseAgent

**Rejected**. Violates ADR-001 (composition over extension points). Would reintroduce the inheritance trap we're eliminating elsewhere.

### Alternative 3: Delete Delegate entirely, users use StreamingAgent directly

**Rejected**. Breaks v2.x public API. Many users have `Delegate(...)` calls in production code. The facade pattern lets us preserve the familiar API while refactoring internals.

### Alternative 4: Rename Delegate to DelegateEngine (match Rust)

**Considered**. But `Delegate` is already the v2.x class name in Python. Renaming is a v3.0 decision (tracked separately). For now, keep `Delegate` as the public name, internally refactor to composition.

## Implementation Notes

### Migration order (per SPEC-05)

1. **Move `AgentLoop`** from `kaizen_agents/delegate/loop.py` to `kaizen/core/agent_loop.py`
2. **Move `DelegateEvent` hierarchy** from `kaizen_agents/delegate/events.py` to `kaizen_agents/events.py`
3. **Move `HookManager`** from `kaizen_agents/delegate/hooks.py` to `kaizen_agents/hooks.py`
4. **Create `StreamingAgent`** (per ADR-003) in `kaizen_agents/streaming_agent.py`
5. **Create `MonitoredAgent`** (per ADR-001) in `kaizen_agents/monitored_agent.py`
6. **Create `L3GovernedAgent`** (per ADR-001) in `kaizen_agents/l3_governed_agent.py`
7. **Rewrite `Delegate` class** in `kaizen_agents/delegate.py` as the composition facade
8. **Delete** `kaizen_agents/delegate/mcp.py` (consumers use `kailash_mcp.MCPClient`)
9. **Delete** `kaizen_agents/delegate/adapters/` (consumers use `kaizen.providers.*`)
10. **Move** `kaizen_agents/delegate/tools/hydrator.py` to `kailash_mcp/tools/hydrator.py`
11. **Add backward-compat shims** at old import paths with deprecation warnings
12. **Run existing Delegate test suite** and fix any regressions
13. **Add new tests** for signature + streaming, envelope + streaming, budget + streaming (capability combinations that weren't possible before)

### Backward compatibility shims

```python
# packages/kaizen-agents/src/kaizen_agents/delegate/__init__.py
import warnings

warnings.warn(
    "kaizen_agents.delegate subpackage is deprecated. "
    "Import Delegate from kaizen_agents directly: `from kaizen_agents import Delegate`. "
    "This shim will be removed in v3.0.",
    DeprecationWarning,
    stacklevel=2,
)

from kaizen_agents.delegate import Delegate  # re-export for compat
from kaizen_agents.events import (
    DelegateEvent, TextDelta, ToolCallStart, ToolCallEnd,
    TurnComplete, BudgetExhausted, ErrorEvent,
)


# packages/kaizen-agents/src/kaizen_agents/delegate/loop.py (compat shim)
import warnings
warnings.warn(
    "kaizen_agents.delegate.loop is deprecated. "
    "Use `from kaizen.core.agent_loop import AgentLoop` instead. "
    "This shim will be removed in v3.0.",
    DeprecationWarning,
)
from kaizen.core.agent_loop import AgentLoop, AgentLoopConfig
```

### Test migration

- `packages/kaizen-agents/tests/unit/delegate/test_delegate.py` — verify public API unchanged
- `packages/kaizen-agents/tests/unit/delegate/test_loop.py` — migrate to `tests/unit/test_agent_loop.py` (moved location)
- `packages/kaizen-agents/tests/unit/delegate/test_mcp.py` — delete (replaced by `kailash-mcp` tests)
- `packages/kaizen-agents/tests/unit/delegate/test_tool_hydration.py` — move to `kailash-mcp/tests/`

New tests to add:

```python
async def test_delegate_with_signature_and_streaming():
    """The capability combination that was impossible before."""
    class Summary(Signature):
        summary: str = OutputField(...)
        confidence: float = OutputField(...)

    delegate = Delegate(model="claude-sonnet-4-5", signature=Summary)

    async for event in delegate.run(prompt="Summarize: quick brown fox"):
        match event:
            case TurnComplete(structured=result):
                assert isinstance(result.summary, str)
                assert isinstance(result.confidence, float)


async def test_delegate_with_mcp_and_signature_and_budget():
    """Full stack composition test."""
    class Output(Signature):
        answer: str = OutputField(...)

    delegate = Delegate(
        model="claude-sonnet-4-5",
        signature=Output,
        mcp_servers=[test_mcp_server_config()],
        budget_usd=1.0,
    )

    events = []
    async for event in delegate.run(prompt="use the filesystem to find file.txt"):
        events.append(event)

    # MCP tool was called
    assert any(isinstance(e, ToolCallEnd) for e in events)
    # Structured output was parsed
    final = [e for e in events if isinstance(e, TurnComplete)][-1]
    assert isinstance(final.structured.answer, str)
    # Budget was tracked
    assert delegate.consumed_usd is not None
    assert delegate.consumed_usd <= 1.0


async def test_delegate_budget_exhausted():
    delegate = Delegate(model="...", budget_usd=0.0001)  # tiny budget

    events = []
    async for event in delegate.run(prompt="expensive prompt"):
        events.append(event)

    # Should terminate with BudgetExhausted
    assert any(isinstance(e, BudgetExhausted) for e in events)
```

## Related ADRs

- **ADR-001**: Composition over extension points (provides the wrapper pattern)
- **ADR-002**: BaseAgent keeps Node inheritance (Delegate composes this BaseAgent)
- **ADR-003**: Streaming as wrapper primitive (Delegate uses StreamingAgent)
- **ADR-004**: kailash-mcp package boundary (Delegate uses kailash_mcp.MCPClient)
- **ADR-005**: Provider capability protocol split (Delegate uses kaizen.providers.\*)
- **ADR-006**: Single ConstraintEnvelope (Delegate's envelope= parameter uses canonical type)

## Related Research

- `01-research/08-delegate-audit.md` — Delegate's current internals and capability matrix
- `02-rs-research/07-rs-agents-audit.md` — Rust's DelegateEngine composition pattern

## Related Issues

- Python #339 — fixed via shared `kailash_mcp.MCPClient`
- Python #340 — fixed via shared `kaizen.providers.google` with mutual exclusion guard
