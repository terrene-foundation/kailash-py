# SPEC-05: Delegate Engine Facade

**Status**: DRAFT
**Implements**: ADR-007 (Delegate as composition facade), ADR-010 (CO Five Layers)
**Cross-SDK issues**: TBD
**Priority**: Phase 4 — depends on SPEC-01 through SPEC-04

## §1 Overview

Rewrite `Delegate` from a parallel implementation (own loop, own adapters, own MCP) to a **thin composition facade** that internally constructs a stack of primitives and wrappers. The user-facing API (`Delegate(model=..., ...)`, `async for event in delegate.run(...)`) is **unchanged**.

### Before vs After

| Aspect             | Before (parallel stack)               | After (composition facade)                            |
| ------------------ | ------------------------------------- | ----------------------------------------------------- |
| Internal loop      | `delegate/loop.py` (own AgentLoop)    | `StreamingAgent` wrapping BaseAgent                   |
| MCP client         | `delegate/mcp.py` (own McpClient)     | `kailash_mcp.MCPClient` via BaseAgent.configure_mcp() |
| LLM providers      | `delegate/adapters/` (own 4 adapters) | `kaizen.providers.*` via BaseAgent                    |
| Tool registry      | `delegate/loop.py:ToolRegistry` (own) | `kailash_mcp.tools.ToolRegistry` via BaseAgent        |
| Budget tracking    | Inline in Delegate                    | `MonitoredAgent` wrapper                              |
| Governance         | GovernedSupervisor wrapping Delegate  | `L3GovernedAgent` wrapper                             |
| Structured outputs | **Not supported**                     | **Now supported** via BaseAgent signature             |
| Events             | `delegate/events.py`                  | `kaizen_agents/events.py` (same types, moved)         |
| Hooks              | `delegate/hooks.py`                   | `kaizen_agents/hooks.py` (same, moved)                |
| Lines of code      | ~1,500 LOC (delegate/ directory)      | ~200 LOC (delegate.py single file)                    |

## §2 API Contract

The full API contract is defined in ADR-007 §Decision. Key points:

### Constructor (unchanged + new params)

```python
class Delegate:
    def __init__(
        self,
        model: str = "",
        *,
        signature: Optional[type[Signature]] = None,   # NEW — enables structured outputs
        tools: Optional[list[Any]] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_turns: int = 50,
        mcp_servers: Optional[list[MCPServerConfig]] = None,
        budget_usd: Optional[float] = None,
        envelope: Optional[ConstraintEnvelope] = None,  # NEW — enables PACT governance
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        inner_agent: Optional[BaseAgent] = None,        # NEW — escape hatch
    ):
```

### Public methods (unchanged)

```python
async def run(self, prompt=None, **inputs) -> AsyncGenerator[DelegateEvent, None]: ...
def run_sync(self, prompt=None, **inputs) -> str: ...
def interrupt(self) -> None: ...
def close(self) -> None: ...
```

### Properties (unchanged + new)

```python
@property
def consumed_usd(self) -> Optional[float]: ...
@property
def budget_remaining(self) -> Optional[float]: ...
@property
def core_agent(self) -> BaseAgent: ...          # NEW — access inner BaseAgent
@property
def streaming_agent(self) -> StreamingAgent: ... # NEW — access outermost wrapper
```

## §3 Internal Stack Construction

```python
def __init__(self, model, *, signature=None, tools=None, mcp_servers=None,
             budget_usd=None, envelope=None, ...):

    # 1. Build core BaseAgent (Intent + Context + Instructions)
    config = BaseAgentConfig(
        model=model,
        posture=AgentPosture.AUTONOMOUS,  # Delegate default
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    if inner_agent is not None:
        core = inner_agent
    else:
        core = BaseAgent(config=config, signature=signature, tools=self._resolve_tools(tools))
        if mcp_servers:
            asyncio.run(core.configure_mcp(mcp_servers))

    # 2. Stack wrappers (innermost → outermost)
    current: BaseAgent = core

    # Learning + soft Guardrails
    monitored = None
    if budget_usd is not None:
        monitored = MonitoredAgent(current, budget_usd=budget_usd)
        current = monitored

    # Hard Guardrails
    if envelope is not None:
        current = L3GovernedAgent(current, envelope=envelope)

    # Streaming (always outermost)
    self._streaming = StreamingAgent(
        current,
        loop_config=AgentLoopConfig(max_turns=max_turns),
        budget_check=monitored.budget_check if monitored else None,
    )

    self._core = core
```

## §4 Progressive Disclosure Layers (Preserved)

**Layer 1 — Minimal** (~10 LOC):

```python
delegate = Delegate(model="claude-sonnet-4-5")
async for event in delegate.run(prompt="hello"):
    print(event)
```

**Layer 2 — Configured** (~15 LOC):

```python
delegate = Delegate(
    model="claude-sonnet-4-5",
    signature=MyOutputSchema,           # NEW: structured outputs
    tools=[file_read, file_write],
    system_prompt="You are a code reviewer.",
    max_turns=20,
)
```

**Layer 3 — Governed** (~25 LOC):

```python
delegate = Delegate(
    model="claude-sonnet-4-5",
    signature=MyOutputSchema,
    mcp_servers=[MCPServerConfig(name="fs", command="npx", args=[...])],
    budget_usd=10.0,                    # MonitoredAgent
    envelope=cfo_envelope,              # L3GovernedAgent
)
```

## §5 Deleted Files (After Migration)

| File                                       | Action                                   | Replacement                  |
| ------------------------------------------ | ---------------------------------------- | ---------------------------- |
| `kaizen_agents/delegate/loop.py`           | MOVED to `kaizen/core/agent_loop.py`     | `AgentLoop` shared primitive |
| `kaizen_agents/delegate/mcp.py`            | DELETED                                  | `kailash_mcp.MCPClient`      |
| `kaizen_agents/delegate/adapters/`         | DELETED                                  | `kaizen.providers.*`         |
| `kaizen_agents/delegate/tools/hydrator.py` | MOVED to `kailash_mcp/tools/hydrator.py` | Shared primitive             |
| `kaizen_agents/delegate/events.py`         | MOVED to `kaizen_agents/events.py`       | Same types, top-level        |
| `kaizen_agents/delegate/hooks.py`          | MOVED to `kaizen_agents/hooks.py`        | Same HookManager             |
| `kaizen_agents/delegate/config/`           | Simplified into Delegate constructor     | Config is transient          |
| `kaizen_agents/delegate/compact.py`        | KEPT or simplified                       | Context compaction           |

## §6 Migration Order

1. Move events.py, hooks.py to top-level `kaizen_agents/`
2. Move loop.py to `kaizen/core/agent_loop.py`
3. Move hydrator.py to `kailash_mcp/tools/`
4. Create new `kaizen_agents/delegate.py` (the composition facade)
5. Add backward-compat shim at `kaizen_agents/delegate/__init__.py`
6. Verify existing Delegate tests pass against new implementation
7. Add new tests: signature + streaming, envelope + streaming, budget + streaming
8. Delete old files after all tests pass

## §7 Test Plan

### Preserved tests (~100+ Delegate tests)

All existing `async for event in delegate.run(...)` tests MUST pass unchanged. The internal implementation changes; the observable behavior does not.

### New capability tests

```python
async def test_delegate_with_signature():
    """Previously impossible: structured outputs + streaming."""
    delegate = Delegate(model="mock", signature=TestSig)
    events = [e async for e in delegate.run(prompt="test")]
    final = [e for e in events if isinstance(e, TurnComplete)][-1]
    assert final.structured is not None

async def test_delegate_with_envelope():
    """Previously required separate GovernedSupervisor wrapping."""
    delegate = Delegate(model="mock", envelope=test_envelope)
    events = [e async for e in delegate.run(prompt="test")]
    assert not any(isinstance(e, ErrorEvent) for e in events)

async def test_delegate_with_mcp_and_signature_and_budget():
    """Full stack — the target use case."""
    delegate = Delegate(
        model="mock", signature=TestSig,
        mcp_servers=[test_config()], budget_usd=1.0,
    )
    events = [e async for e in delegate.run(prompt="use filesystem")]
    assert any(isinstance(e, ToolCallEnd) for e in events)
    assert delegate.consumed_usd > 0
```

## §8 Related Specs

- **SPEC-01**: kailash-mcp (Delegate uses MCPClient via BaseAgent)
- **SPEC-02**: Providers (Delegate uses providers via BaseAgent)
- **SPEC-03**: Composition wrappers (Delegate stacks them internally)
- **SPEC-04**: BaseAgent (Delegate's inner core)
- **SPEC-10**: Multi-agent patterns (SupervisorAgent can wrap Delegate)

## §9 Security Considerations

Delegate is the primary user-facing API for agent execution — for most users, it IS the agent. That makes it the highest-leverage attack surface: a single Delegate vulnerability compromises every consumer. The rewrite as a composition facade introduces three Delegate-specific threats on top of the BaseAgent and wrapper threats inherited from SPEC-03 and SPEC-04.

### §9.1 `asyncio.run()` in Constructor Deadlock and Side-Effect Injection

**Threat**: The simplest implementation of Delegate's MCP setup would call `asyncio.run(mcp_client.discover_and_register(...))` in `__init__()`. This has two problems. First, `asyncio.run()` creates and tears down an event loop — if called from inside a running loop (FastAPI request handler, Jupyter notebook, Nexus channel), it raises `RuntimeError: asyncio.run() cannot be called from a running event loop`. Second, the constructor window is a point where the MCP discovery makes real outbound HTTP calls; an attacker who can make Delegate constructors fire in a loop (e.g., by feeding a worker pool a stream of malformed configurations) can turn Delegate into an unwitting HTTP scanner or a reflected-traffic amplifier.

**Mitigations**:

1. Delegate MUST NOT call `asyncio.run()` or any form of synchronous event loop execution in `__init__`. MCP discovery is deferred to the first `run()` call using the `_deferred_mcp` pattern from SPEC-04 §10.1.
2. Delegate MUST detect running event loops via `asyncio.get_running_loop()` and refuse synchronous `run()` calls from within them — the error message points at `run_async()` or the streaming variant.
3. Constructors MUST NOT make outbound network calls. Any IO in the constructor raises `ConstructorIOError`.
4. Rate-limit Delegate construction per process at the BaseAgent layer (configurable, default 100/sec). A burst above the limit emits `DelegateConstructionRateLimitExceeded` to the audit store for post-hoc review.

### §9.2 Progressive Disclosure Layer Credential Leakage

**Threat**: Delegate's API progressively exposes complexity: `Delegate(model=...)` → `Delegate(model=..., signature=...)` → `Delegate(model=..., signature=..., envelope=..., mcp_servers=..., inner_agent=...)`. The `inner_agent=` parameter accepts a fully constructed BaseAgent. A caller may pass an inner agent that has `configure_mcp()` already called with MCP servers containing auth tokens in their URLs (`https://token@server/mcp`). Delegate wraps this agent with wrappers that log tool calls — which would log the URL including the token.

**Mitigations**:

1. `MCPServerConfig` MUST store credentials separately from the URL. The URL stored on the object is the bare URL; credentials are in a secret-bearing field that never serializes to logs.
2. Delegate's audit logger MUST use a `scrub_secrets` filter on every log entry. The filter uses a regex that strips `user:pass@` and `?token=` query parameters and known header names.
3. `inner_agent=` parameter MUST be validated: Delegate calls `inner_agent.get_security_context()` (a new method added in SPEC-04) and refuses the construction if any MCP server config has a credential-bearing URL in the non-scrubbed field.
4. Integration test uses `caplog` to verify no secret ever appears in log output for a Delegate constructed with a credentialed MCP server.

### §9.3 MCP Tool Registry Poisoning via Construction Order

**Threat**: When Delegate is constructed with both `mcp_servers=[...]` and `inner_agent=pre_configured_agent`, the order in which tool registrations happen matters. If Delegate's own MCP discovery runs after the inner agent has been configured, the inner agent's tool registry can be overwritten. A malicious `mcp_servers` list could shadow legitimate tool names: register a `search_database` tool that points at an attacker-controlled server while the inner agent's real `search_database` tool is displaced.

**Mitigations**:

1. Delegate MUST merge MCP tool registrations by prefixing them with the server name: the inner agent's `search_database` becomes `inner/search_database`, and a Delegate-level registration becomes `delegate/search_database`. Collisions raise `ToolRegistryCollisionError`.
2. Tool name collisions MUST be logged to the audit store before being rejected, so post-hoc analysis can detect attempted poisoning.
3. The internal wrapper stack MUST NOT re-register tools when wrapping. Wrappers proxy `get_tools()` from the inner agent.
4. Red-team test: construct a Delegate with a benign inner_agent and a malicious mcp_servers list that duplicates tool names; verify the second registration is rejected.

### §9.4 Backward-Compatibility Shim Impersonation

**Threat**: The migration plan keeps `kaizen_agents.delegate.loop`, `kaizen_agents.delegate.adapters`, and `kaizen_agents.delegate.mcp` as backward-compatibility shims during the v2.x → v3.0 transition (ADR-009 Layer 2). A malicious package on PyPI named `kaizen_agents_delegate_loop` (or a typo-squat) could be shadowed by user imports and intercept `Delegate` construction without obvious signal.

**Mitigations**:

1. Each shim module MUST emit a `DeprecationWarning` with a stable message format at import time, identifying the canonical replacement path.
2. Delegate's `__init__` MUST verify the call stack's origin module is either `kaizen_agents` or a known test harness; unknown origins trigger a `SuspiciousImportWarning`.
3. A hash of the shim module files is published in the package metadata; CI verifies the hashes match on every release.
4. Shim modules are REMOVED in v3.0, not kept indefinitely — the attack surface is time-bounded.
