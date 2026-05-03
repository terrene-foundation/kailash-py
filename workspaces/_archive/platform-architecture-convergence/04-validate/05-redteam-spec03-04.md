# Red Team — SPEC-03 (Composition Wrappers) and SPEC-04 (BaseAgent Slimming)

**Date**: 2026-04-08
**Workspace**: platform-architecture-convergence
**Phase**: 04 (validate)
**Validator**: analyst (deep audit)
**Branch**: feat/platform-architecture-convergence
**Verdict**: NOT READY — multiple CRITICAL gaps; spec coverage claims (`.spec-coverage`) are factually wrong on at least 4 items.

## Executive Summary

The previous Implementation Red Team Round 1 (`02-implementation-redteam.md`) declared "PASS — 0 CRITICAL, 0 HIGH, 4 MINOR". This deeper audit shows that judgement was unsafe. **Five Critical and three High findings exist** that the prior pass missed because the audit relied on file existence rather than spec semantics or test coverage.

The new wrapper files exist on disk and import cleanly, but:

1. The `posture` field that anchors ADR-010 is **completely absent** from `BaseAgentConfig` and BaseAgent.
2. `BaseAgentConfig` is **not frozen** despite SPEC-04 §10.3 mandating it.
3. The 7 extension points are **not decorated** with `@deprecated` despite SPEC-04 §2.3 mandating it (the decorator exists; it is simply never applied).
4. The new wrappers (`StreamingAgent`, `MonitoredAgent`, `L3GovernedAgent`, `WrapperBase`) have **zero test coverage** — no test file imports any of them.
5. SPEC-03 §2.4 / §2.5 `SupervisorAgent` and `WorkerAgent` composition wrappers and `LLMBased` routing strategy **do not exist**. The legacy `patterns/runtime.py` semantic router uses Jaccard string similarity, which **violates `rules/agent-reasoning.md` MUST Rule 5**.
6. The new `kaizen.core.agent_loop.AgentLoop` is **not the TAOD streaming loop** SPEC-03 §6 specifies — it is a wrapper around the existing strategy execution path, with no `run_stream` method, no token streaming, and no budget callback. The actual TAOD loop still lives at `kaizen_agents/delegate/loop.py` (821 LOC, untouched). SPEC-03's "moved primitive" did not happen.
7. `StreamingAgent.run_stream()` is a **synthetic stream** — it calls `inner.run_async()` once and synthesises one `TextDelta` + one `TurnComplete` from the result dict. There is no incremental token delivery, no tool-call streaming, no TAOD iteration count. This is not what ADR-003 / SPEC-03 §3.2 describe.
8. `BaseAgent` still imports `from kailash.mcp_server.client import MCPClient` directly instead of `from kailash_mcp import MCPClient` — SPEC-04 §1 / SPEC-01 migration is not finished.
9. None of the security mitigations in SPEC-03 §11 / SPEC-04 §10 are implemented (shadow drill warn-on-N, posture poisoning guard, `_DEPRECATED_PARAMETERS` allowlist, `_deferred_mcp` `__setattr__` guard, `_build_messages` signature-aware key selection — all missing).

The `.spec-coverage` file at `workspaces/platform-architecture-convergence/.spec-coverage` reports SPEC-03 8/8 and SPEC-04 9/9 (100%). At minimum the following entries are factually wrong: "BaseAgentConfig frozen | implemented", "7 extension points deprecated | implemented", "StreamingAgent integration | implemented", and the SPEC-03 §2.4/§2.5 omission. The audit table is more aspiration than evidence.

**Complexity**: Complex — fixing requires re-touching every wrapper, base agent, config, the delegate stack, the routing layer, the AgentLoop primitive, and adding ~6 missing test modules and the security mitigations.

## Risk Register

| ID      | Severity | Risk                                                                                                                                                                                                                                                                                                                      | Likelihood | Impact   |
| ------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | -------- |
| CRIT-01 | Critical | `BaseAgentConfig.posture` field is missing entirely. ADR-010 / SPEC-04 §2.1 require it. All posture-aware behaviour cascades from it.                                                                                                                                                                                     | Certain    | Critical |
| CRIT-02 | Critical | `BaseAgentConfig` is not `@dataclass(frozen=True)`. SPEC-04 §10.3 mandate. Allows runtime mutation of posture/budget/strategy after construction.                                                                                                                                                                         | Certain    | Critical |
| CRIT-03 | Critical | None of the 7 extension points has `@deprecated` applied. SPEC-04 §2.3 / §3.3 / §10.4 mandate. Decorator exists in `deprecation.py` but is never imported by `base_agent.py`.                                                                                                                                             | Certain    | High     |
| CRIT-04 | Critical | Wrappers (`StreamingAgent`, `MonitoredAgent`, `L3GovernedAgent`, `WrapperBase`) have ZERO test coverage. Spec §8 mandates per-wrapper unit tests + stacking integration tests.                                                                                                                                            | Certain    | High     |
| CRIT-05 | Critical | `StreamingAgent.run_stream()` is a fake stream — emits one synthesised `TextDelta` plus one `TurnComplete` from a single `inner.run_async()` call. ADR-003 / SPEC-03 §3.2 + §6 require a TAOD loop with incremental tokens, tool-call streaming, and budget callback.                                                     | Certain    | High     |
| HIGH-01 | High     | SPEC-03 §2.4 `SupervisorAgent` and §2.5 `WorkerAgent` wrappers do not exist. The legacy `patterns/runtime.py` uses Jaccard string similarity for "semantic" routing — violates `rules/agent-reasoning.md` MUST Rule 5. R2-001 (LLM routing fix) is not implemented.                                                       | Certain    | High     |
| HIGH-02 | High     | SPEC-03 §6 says AgentLoop moves to `kaizen.core.agent_loop` and becomes the streaming primitive. The new file is a different class (no `run_stream`, no streaming) that wraps the existing strategy executor. The real loop at `kaizen_agents/delegate/loop.py` is untouched. There is no shared primitive.               | Certain    | High     |
| HIGH-03 | High     | None of the SPEC-03 §11 / SPEC-04 §10 security mitigations are implemented: no shadow drill warn-on-N, no posture poisoning guard, no `_DEPRECATED_PARAMETERS` allowlist, no `_deferred_mcp` `__setattr__` guard, no signature-aware key selection in `_build_messages`.                                                  | Certain    | High     |
| MED-01  | Medium   | `AgentPosture` enum (in `kailash.trust.envelope`) is `(str, Enum)` not `IntEnum`. Names are `PSEUDO_AGENT/SUPERVISED/SHARED_PLANNING/CONTINUOUS_INSIGHT/DELEGATED` — none of `TOOL`, `AUTONOMOUS`, `DELEGATING` exist. SPEC-04 §2.2 spec divergence.                                                                      | Certain    | Medium   |
| MED-02  | Medium   | `BaseAgent` still imports `from kailash.mcp_server.client import MCPClient` instead of `from kailash_mcp import MCPClient`. SPEC-04 §1 / SPEC-01 import migration incomplete.                                                                                                                                             | Certain    | Medium   |
| MED-03  | Medium   | Two parallel event systems: `kaizen_agents/events.py` (frozen, base `StreamEvent`, used by wrappers) and `kaizen_agents/delegate/events.py` (mutable `@dataclass`, base `DelegateEvent`, used by Delegate). SPEC-03 §5 / §7 step 1 said one canonical module + shim.                                                      | Certain    | Medium   |
| MED-04  | Medium   | StreamingAgent constructor parameter is `buffer_size` (default 256), spec §11.6 says `max_buffered_events` (default 100). No `budget_check` callback is accepted (spec §3.2 requires it).                                                                                                                                 | Certain    | Medium   |
| MED-05  | Medium   | `WrapperBase._inner_called` flag exists but is never asserted by anything. The "wrappers MUST call `_inner.run()`" invariant is documented but unenforced.                                                                                                                                                                | Certain    | Medium   |
| MED-06  | Medium   | The new wrappers are not exported from `kaizen_agents/__init__.py`. Users must import via the full path; the canonical entry stays the legacy `Delegate` / `GovernedSupervisor`.                                                                                                                                          | Certain    | Medium   |
| MED-07  | Medium   | Permission system fields (`budget_limit_usd`, `allowed_tools`, `denied_tools`, `permission_rules`) and 7 mixin feature flags remain on `BaseAgentConfig` with active `_apply_*_mixin()` paths in BaseAgent `__init__`. SPEC-04 §3.1 says these moved to wrappers. They have not.                                          | Certain    | Medium   |
| MED-08  | Medium   | `_ProtectedInnerProxy` blocks calls to `_inner` but `WrapperBase.inner` returns the raw `_inner` directly (line 122). `L3GovernedAgent.inner` overrides to return the proxy — but a caller can still walk `governed.innermost` (defined on `WrapperBase`) and reach the raw inner agent without going through governance. | Certain    | High     |
| MIN-01  | Minor    | `.spec-coverage` reports 100% on items that are demonstrably absent. The artifact is unsafe to use as a release gate.                                                                                                                                                                                                     | Certain    | Medium   |

## Findings

### CRIT-01 — Posture field is completely absent from BaseAgentConfig

**Location**: `packages/kailash-kaizen/src/kaizen/core/config.py:35-110`
**Spec ref**: SPEC-04 §2.1, §2.2, §3.4; ADR-010 (CO Five Layers)

`BaseAgentConfig` defines no `posture` field and the file does not import `AgentPosture`. `grep -n posture` against both `config.py` and `base_agent.py` returns zero matches.

```
$ grep -rn "posture" packages/kailash-kaizen/src/kaizen/core
(empty)
```

Consequences:

1. There is no way for a user to set posture on an agent. ADR-010's CO Five Layers / instruction enforcement spectrum is unrealisable from the agent surface.
2. `StructuredOutput` (`kaizen/core/structured_output.py`) has zero posture-awareness — `grep posture structured_output.py` returns nothing. SPEC-04 §3.4 (strict / moderate / soft validation) is not implementable.
3. `L3GovernedAgent._evaluate_posture_ceiling()` does posture clamping against `self._posture`, but `self._posture` is only populated when the user explicitly passes `posture=...` to the wrapper constructor. There is no upstream source for it because `BaseAgentConfig` has no posture field. The mitigation path is wired to nothing.
4. `BaseAgent.posture` property described in SPEC-04 §2.3 line 610-611 does not exist.

### CRIT-02 — BaseAgentConfig is not frozen

**Location**: `packages/kailash-kaizen/src/kaizen/core/config.py:35` — `@dataclass` (no `frozen=True`)
**Spec ref**: SPEC-04 §10.3 mitigation 1; SPEC-03 §11.3; `rules/trust-plane-security.md` "Frozen Constraint Dataclasses"

The threat described in SPEC-04 §10.3 (posture/budget tampering after construction) is wide open. The `posture_ceiling` integer-poisoning attack in SPEC-03 §11.3 is also unmitigated for the same reason: `agent._config.budget_limit_usd = math.nan` will succeed silently.

Worse: `L3GovernedAgent.__init__` reads `inner.config` and stores a reference. Because the config is mutable, an attacker holding the inner BaseAgent can flip `inner._config.budget_limit_usd` after the wrapper has captured it; the wrapper sees the new value on the next call.

### CRIT-03 — @deprecated decorator is never applied to the 7 extension points

**Location**: `packages/kailash-kaizen/src/kaizen/core/base_agent.py:497-633`
**Spec ref**: SPEC-04 §2.3 (every method shows `@deprecated(...)`), §3.3, §10.4

`base_agent.py` does not even import `from kaizen.core.deprecation import deprecated`. The 7 extension points (`_default_signature`, `_default_strategy`, `_generate_system_prompt`, `_validate_signature_output`, `_pre_execution_hook`, `_post_execution_hook`, `_handle_error`) are bare methods at lines 503, 514, 536, 593, 609, 617, 624. The docstring at line 499 says "Deprecated in v2.5.0" — but no warning is ever emitted at runtime when a subclass overrides them.

Consequence: the 188 existing subclasses receive zero migration signal. The "v2.x deprecation window" SPEC-04 §1 advertises does not exist. `test_subclass_with_custom_signature` and `test_subclass_with_custom_strategy` in `test_base_agent_slimming.py` explicitly assert no warnings (they don't use `pytest.warns`). The deprecation tests (`TestDeprecationDecorator`) only verify the decorator works in isolation; they never check that BaseAgent's methods carry it.

### CRIT-04 — Wrappers have zero test coverage

**Location**: `packages/kaizen-agents/tests/**` — no file imports any wrapper module.
**Spec ref**: SPEC-03 §8 (full per-wrapper unit suite + stacking integration suite)

```
$ grep -r "from kaizen_agents.wrapper_base\|streaming_agent\|monitored_agent\|governed_agent" packages/kaizen-agents/tests
(empty)
```

The only consumer is `delegate.py`, which uses fallback `try/except ImportError` so the wrappers being broken would silently degrade to the Delegate's own code path. There is no test that asserts:

- Stacking order rejects duplicates (`DuplicateWrapperError`)
- `_inner_called` flag is set after every successful run
- `MonitoredAgent` raises `BudgetExhaustedError` on a finite budget
- `L3GovernedAgent` rejects on financial / operational / posture constraint
- `_ProtectedInnerProxy` blocks `governed.inner._inner.run(...)`
- `StreamingAgent` emits any specific event sequence
- `BudgetExhaustedError` from inner is converted to `BudgetExhausted` event
- The full canonical stack (BaseAgent → L3Gov → Monitored → Streaming) yields a working result

The 5 wrapper invariants in SPEC-03 §3.4 and the 6 security mitigations in §11 are entirely unverified.

### CRIT-05 — StreamingAgent does not actually stream

**Location**: `packages/kaizen-agents/src/kaizen_agents/streaming_agent.py:84-195`
**Spec ref**: SPEC-03 §2.1, §3.2, §6.1; ADR-003

The implementation:

```python
result = await asyncio.wait_for(
    self._inner.run_async(**kwargs),
    timeout=self._timeout_seconds,
)

# Extract text from common result keys
for key in ("answer", "response", "text", "output", "content"):
    if key in result and isinstance(result[key], str):
        text = result[key]
        break

if text:
    yield TextDelta(text=text)
yield TurnComplete(text=text, usage=usage, structured=structured, iterations=1)
```

There is one `TextDelta` (the entire response, not a delta), one `TurnComplete` (always `iterations=1`), no `ToolCallStart`/`ToolCallEnd`, no incremental tokens, no budget callback, no TAOD loop. The spec event contract (§2.1: "1. Zero or more TextDelta events (tokens as they arrive) ... 2. Zero or more ToolCallStart -> ToolCallEnd pairs ... 3. Exactly one terminal event") is violated by construction.

Worse: the text-key fallback chain (`answer`, `response`, `text`, `output`, `content`) silently picks any of these — not posture-aware, not signature-driven, and fragile across providers.

The actual TAOD streaming loop (in `kaizen_agents/delegate/loop.py`, 821 LOC) is not used here. SPEC-03 §6.1 says "The move makes AgentLoop a shared primitive accessible from both `kailash-kaizen` (for BaseAgent) and `kaizen-agents` (for StreamingAgent, Delegate)." That move did not happen — see HIGH-02.

### HIGH-01 — SupervisorAgent / WorkerAgent / LLMBased are missing; legacy router violates LLM-first rule

**Location**:

- Missing: `packages/kaizen-agents/src/kaizen_agents/supervisor_agent.py`, `worker_agent.py`
- Legacy router: `packages/kaizen-agents/src/kaizen_agents/patterns/runtime.py:545-599`, `_simple_text_similarity` at `:619`

**Spec ref**: SPEC-03 §2.4, §2.5; SPEC-03 §11.5; `rules/agent-reasoning.md` MUST Rule 5

SPEC-03 §2.4/§2.5 specify wrapper-style `SupervisorAgent` and `WorkerAgent` that hold `capability_card` properties and use `LLMBased(config=BaseAgentConfig)` routing — the LLM reads each worker's card and reasons about a match. The R2-001 fix.

Reality:

- No `supervisor_agent.py` or `worker_agent.py` files exist.
- `supervisor.py` is a different `GovernedSupervisor` (PACT-style L3 progressive disclosure facade) — not the SPEC-03 wrapper.
- `kaizen_agents/patterns/runtime.py` is the active multi-agent runtime. Its `RoutingStrategy` enum is `SEMANTIC | ROUND_ROBIN | RANDOM | LEAST_LOADED`. `LLMBased` does not exist.
- `_route_semantic()` (line 554) iterates worker cards and calls `_simple_text_similarity(task.lower(), cap.lower())` — Jaccard word-set similarity. This is keyword routing inside an agent decision path. **Direct violation of `rules/agent-reasoning.md` MUST Rule 5** ("Router Agents Use LLM Routing, Not Dispatch Tables") and MUST NOT Rule 2 ("MUST NOT Use Keyword/Regex Matching on Agent Inputs").

The "R2-001 fix" the convergence analysis claimed is not in the codebase.

Spec §11.5 (capability card sanitisation, prompt injection guard, audit trail of routing decision) is moot because the LLM-based router does not exist.

### HIGH-02 — AgentLoop is not the shared streaming primitive SPEC-03 §6 promises

**Location**:

- New: `packages/kailash-kaizen/src/kaizen/core/agent_loop.py` (449 LOC) — strategy executor with `AgentLoop.run_sync(agent, **inputs)` and `AgentLoop.run_async(agent, **inputs)` — no `run_stream`, no streaming.
- Old: `packages/kaizen-agents/src/kaizen_agents/delegate/loop.py` (821 LOC) — the actual TAOD loop with `run_turn` async generator, OpenAI streaming adapter, tool-hydrator integration. UNTOUCHED.

**Spec ref**: SPEC-03 §6.1, §6.3

SPEC-03 §6.1 says the loop moves from `delegate/loop.py` to `kailash-kaizen/src/kaizen/core/agent_loop.py` and becomes accessible from both packages. SPEC-03 §6.3 preserves the architectural invariant that the loop must not depend on workflow primitives.

Implementation reality:

- The "new" `agent_loop.py` is a completely different class. It is the strategy execution path extracted from BaseAgent's old inline `run()` body. Its `AgentLoopConfig` has fields `max_cycles / temperature / max_tokens` — not `max_turns / timeout / streaming` like SPEC-03 §6.2 specifies.
- The "old" `delegate/loop.py` is still 821 LOC and still does the streaming work.
- StreamingAgent imports neither — it just calls `inner.run_async()`.
- Delegate still imports `from kaizen_agents.delegate.loop import AgentLoop` (different class, same name).

Cross-SDK parity (SPEC-03 §10) is broken: Rust's `kaizen-agents/src/streaming/agent.rs` actually owns a TAOD loop. Python claims convergence but did not converge.

### HIGH-03 — Security mitigations from §11 / §10 are entirely missing

**Spec refs**:

| Mitigation                                          | Spec            | Status                                                                                                                                                                                                                                                                           |
| --------------------------------------------------- | --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `_ProtectedInnerProxy` blocks `.inner._inner`       | SPEC-03 §11.1   | Partial — proxy exists but `WrapperBase.innermost` (line 126-131) walks the stack via `_inner` chain and returns the raw inner agent, bypassing the proxy.                                                                                                                       |
| Wrapper invariant raises `WrapperInvariantError`    | SPEC-03 §11.1.2 | Missing — `_inner_called` is set, never asserted.                                                                                                                                                                                                                                |
| Shadow mode warn-on-N + `enforcement="shadow"` tag  | SPEC-03 §11.2   | Missing — `enforcement_mode` parameter is missing from `L3GovernedAgent.__init__` entirely.                                                                                                                                                                                      |
| Shadow mode env-var rejection                       | SPEC-03 §11.2.2 | Moot — feature absent.                                                                                                                                                                                                                                                           |
| Posture ceiling type guard in deserialization       | SPEC-03 §11.3   | Missing — `BaseAgentConfig` has no posture field at all.                                                                                                                                                                                                                         |
| `L3GovernedAgent(envelope=None)` raises             | SPEC-03 §11.4.1 | Missing — `envelope` is positional-required, but a `None` value would crash later inside `_evaluate_*` with `AttributeError`, not the spec'd `ValueError`.                                                                                                                       |
| `describe_stack()` introspection                    | SPEC-03 §11.4.2 | Missing.                                                                                                                                                                                                                                                                         |
| LLMBased capability card sanitisation               | SPEC-03 §11.5.1 | Moot — `LLMBased` and `WorkerAgent` are absent.                                                                                                                                                                                                                                  |
| `max_buffered_events` + `StreamBufferOverflow`      | SPEC-03 §11.6.1 | Partial — implementation has `buffer_size=256` (spec says `max_buffered_events=100`) and emits `StreamBufferOverflow` only after the single synthetic event has been counted. Backpressure cannot occur in practice because there is exactly one event.                          |
| `stream_timeout_s` raising `StreamTimeoutError`     | SPEC-03 §11.6.3 | Partial — `timeout_seconds=300.0` exists but timeout fires only on the inner `run_async()`, not on consumer drainage.                                                                                                                                                            |
| `_deferred_mcp` is `tuple` not `list`               | SPEC-04 §10.1.1 | Missing — no `_deferred_mcp` plumbing exists at all.                                                                                                                                                                                                                             |
| `__setattr__` guard on `_deferred_mcp`              | SPEC-04 §10.1.2 | Missing.                                                                                                                                                                                                                                                                         |
| MCP audit log on first run                          | SPEC-04 §10.1.3 | Missing.                                                                                                                                                                                                                                                                         |
| `configure_mcp()` frozen after first run            | SPEC-04 §10.1.4 | Missing — no `configure_mcp()` public method exists; MCP is auto-discovered on first call inside `AgentLoop.run_sync` (`agent_loop.py:321`).                                                                                                                                     |
| `_DEPRECATED_PARAMETERS` allowlist                  | SPEC-04 §10.2.1 | Missing — `BaseAgent.__init__(**kwargs)` accepts everything and forwards to `Node.__init__`. `mcp_servers=` is a documented param and not an allowlist entry.                                                                                                                    |
| `construction_audit` attribute                      | SPEC-04 §10.2.4 | Missing.                                                                                                                                                                                                                                                                         |
| Frozen `BaseAgentConfig`                            | SPEC-04 §10.3.1 | Missing — see CRIT-02.                                                                                                                                                                                                                                                           |
| `self._posture` private copy                        | SPEC-04 §10.3.2 | Missing — see CRIT-01.                                                                                                                                                                                                                                                           |
| `HookContext` (no body access) for deprecated hooks | SPEC-04 §10.4.1 | Missing — `_pre_execution_hook(inputs)` / `_post_execution_hook(result)` see full payloads at lines 609-622.                                                                                                                                                                     |
| Deprecated hooks refuse on PSEUDO/TOOL postures     | SPEC-04 §10.4.3 | Missing — see CRIT-01.                                                                                                                                                                                                                                                           |
| Signature-aware key selection in `_build_messages`  | SPEC-04 §10.5.1 | Not applicable: `_build_messages` is a SPEC-04 §2.3 design artefact; the actual BaseAgent does not have it. The current code routes through `AgentLoop._execute_strategy(...)` to a strategy class. The "input key fallback" (R2-009) lives unmodified in the legacy strategies. |

### MED-01 — AgentPosture enum diverges from spec

**Location**: `src/kailash/trust/envelope.py:549-584`
**Spec ref**: SPEC-04 §2.2

Spec mandates:

```python
class AgentPosture(IntEnum):
    PSEUDO = 1
    TOOL = 2
    SUPERVISED = 3
    AUTONOMOUS = 4
    DELEGATING = 5
```

with `from_string()` and `instruction_enforcement()` methods.

Implementation:

```python
class AgentPosture(str, Enum):
    PSEUDO_AGENT = "pseudo_agent"
    SUPERVISED = "supervised"
    SHARED_PLANNING = "shared_planning"
    CONTINUOUS_INSIGHT = "continuous_insight"
    DELEGATED = "delegated"
```

`TOOL`, `AUTONOMOUS`, and `DELEGATING` are missing entirely; the spec's enum / string mismatch is unresolvable. The instruction enforcement table (§2.2 / §3.3) cannot be implemented because the enum has no `instruction_enforcement()` method and the canonical names do not exist.

Cross-SDK parity is also at risk: Rust's `ExecutionMode` is being expanded to the spec's posture spectrum (per SPEC-04 §8); Python is diverging instead of converging.

### MED-02 — BaseAgent imports MCPClient from the wrong canonical path

**Location**: `packages/kailash-kaizen/src/kaizen/core/base_agent.py:32`

```python
from kailash.mcp_server.client import MCPClient
```

SPEC-01 / SPEC-04 §1 require migration to `from kailash_mcp import MCPClient`. The new `kailash_mcp` package exists at `packages/kailash-mcp/` but BaseAgent ignores it. SPEC-04 §3.1 line "MCP client initialization + tool discovery → kailash_mcp.MCPClient (SPEC-01) | ~800 LOC saved" — the saving was achieved by extracting to a mixin, not by switching to the new package.

### MED-03 — Two parallel event systems

**Location**:

- `packages/kaizen-agents/src/kaizen_agents/events.py` (172 LOC, frozen, base `StreamEvent`, used by wrappers).
- `packages/kaizen-agents/src/kaizen_agents/delegate/events.py` (mutable, base `DelegateEvent`, used by Delegate and `delegate/loop.py`).

**Spec ref**: SPEC-03 §5.1, §7 step 1

SPEC-03 §7 step 1 says "Create `kaizen_agents/events.py` (move from `delegate/events.py`)". Spec §5.1 names the base class `DelegateEvent`, not `StreamEvent`. Implementation made a separate file with a renamed base class and left the old file in place. They diverge in:

- Frozen vs mutable
- Base class name
- Default field semantics (`event_type` discriminator differs)
- `TurnComplete.iterations` is added in the new file but the old file has the field with the same name and a different default

Pattern matching code in user-space that expects `case TextDelta(...)` from the spec won't work with both — `isinstance` will be false across them and `match` will route to the wrong handler. SPEC-03's promise of a single canonical event hierarchy is broken.

### MED-04 — StreamingAgent constructor parameters diverge from spec

**Location**: `packages/kaizen-agents/src/kaizen_agents/streaming_agent.py:42-71`

| Spec parameter (§2.1 / §11.6)      | Implementation parameter         | Notes                                           |
| ---------------------------------- | -------------------------------- | ----------------------------------------------- |
| `loop_config: AgentLoopConfig`     | (absent)                         | StreamingAgent does not own a loop              |
| `budget_check: Callable[[], bool]` | (absent)                         | Spec §3.2 mandates this for the canonical stack |
| `max_buffered_events: int = 100`   | `buffer_size: int = 256`         | Different name + default                        |
| `stream_timeout_s: float = 300.0`  | `timeout_seconds: float = 300.0` | Different name                                  |

Anything that follows the spec's example code (`StreamingAgent(monitored, budget_check=monitored.budget_check)`) raises `TypeError`.

### MED-05 — `_inner_called` invariant is documented but unenforced

**Location**: `packages/kaizen-agents/src/kaizen_agents/wrapper_base.py:14, 84, 108, 117`
**Spec ref**: SPEC-03 §3.4 invariant 6, §11.1.2

`WrapperBase._inner_called` is set to `True` in every wrapper's `run` / `run_async` path. Nothing ever reads it. There is no `assert self._inner_called` after the call, no `WrapperInvariantError` raised when it stays `False`. A buggy subclass that forgets to call `_inner.run()` will silently produce a "successful" empty result. The flag is decorative.

### MED-06 — New wrappers are not exported

**Location**: `packages/kaizen-agents/src/kaizen_agents/__init__.py:19-85`

`__all__` exports `Delegate, GovernedSupervisor, SupervisorResult, Agent, ReActAgent, Pipeline, BaseMultiAgentPattern, SupervisorWorkerPattern, ConsensusPattern, DebatePattern, HandoffPattern, SequentialPipelinePattern` and `create_*` factories. `WrapperBase, StreamingAgent, MonitoredAgent, L3GovernedAgent, BudgetExhaustedError, GovernanceRejectedError, DuplicateWrapperError` are absent. Users have to import them via the full module path.

This is partly why no tests import them — they are not part of the discoverable surface.

### MED-07 — Mixin / permission feature flags still active inside BaseAgent

**Location**:

- `config.py:69-99` (feature flags + permission system fields)
- `base_agent.py:133-208` (inline mixin application + permission policy creation)

**Spec ref**: SPEC-04 §3.1 lines "Mixin application (7 mixins) → Composition wrappers (SPEC-03), ~100 LOC saved" and "Permission system → L3GovernedAgent wrapper, ~200 LOC saved"

The 7 mixin flags are still on the config (`logging_enabled`, `performance_enabled`, `error_handling_enabled`, `batch_processing_enabled`, `memory_enabled`, `transparency_enabled`, `mcp_enabled`). BaseAgent's `__init__` still applies them via `_apply_logging_mixin`, etc. The permission system (`ExecutionContext`, `PermissionPolicy`, `ToolApprovalManager`) is constructed inline at lines 133-152.

The "extraction" claimed in §3.1 is partial. The mixins were extracted into mixin classes (good) but the application path is still inline in BaseAgent and is still controlled by config flags (not via wrappers). SPEC-04 §1 row "Mixins (7) ... DEPRECATED — capabilities moved to wrappers" is contradicted by the live code.

### MED-08 — Inner proxy can be bypassed via `WrapperBase.innermost`

**Location**:

- `packages/kaizen-agents/src/kaizen_agents/wrapper_base.py:125-131`
- `packages/kaizen-agents/src/kaizen_agents/governed_agent.py:144-147`

```python
# wrapper_base.py
@property
def innermost(self) -> BaseAgent:
    """Walk the wrapper stack to find the innermost (non-wrapper) agent."""
    current = self._inner
    while isinstance(current, WrapperBase):
        current = current._inner
    return current
```

`L3GovernedAgent.inner` correctly returns the `_ProtectedInnerProxy`. But it inherits `WrapperBase.innermost`, which walks `self._inner` (the raw, ungated reference) and returns the underlying BaseAgent. A caller can do:

```python
governed = L3GovernedAgent(base, envelope=env)
governed.innermost.run(query="...")  # bypasses governance entirely
```

This re-opens the SPEC-03 §11.1 envelope-bypass threat. The mitigation in §11.1.1 only protected `inner._inner`; the implementation introduced a second escape hatch (`innermost`) and did not gate it.

### MIN-01 — `.spec-coverage` reports false 100% on items that are absent

**Location**: `workspaces/platform-architecture-convergence/.spec-coverage:62-91`

| Claim                                                       | Reality                                                                                           |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "BaseAgentConfig frozen                                     | implemented"                                                                                      | Not frozen — `@dataclass` (CRIT-02).                                                                                                                                                            |
| "7 extension points deprecated                              | implemented"                                                                                      | No `@deprecated` applied (CRIT-03).                                                                                                                                                             |
| "StreamingAgent integration                                 | implemented"                                                                                      | StreamingAgent is not in the Delegate stack; Delegate stops at MonitoredAgent.                                                                                                                  |
| "Stacking order: BaseAgent → L3Gov → Monitored → Streaming" | Wrappers stack to MonitoredAgent in `delegate.py:340-376`; StreamingAgent never enters the chain. |
| "20 line-count enforcement tests                            | implemented"                                                                                      | One line-count test exists (`test_base_agent_under_1000_lines`) plus ~17 mixin/MRO tests. The "20" count includes happy-path unit tests, none of which assert SPEC-04 §10 security mitigations. |

The audit table is treated as a release gate (`scripts/convergence-verify.py`). Because it is wrong, the gate is signing off non-compliant code.

## Spec-Item Audit Table — SPEC-03

| Spec section / item                                                                  | Status               | Evidence / file                                                                                                                                                                                                                                                                                                                                                                                        |
| ------------------------------------------------------------------------------------ | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| §2.1 `StreamingAgent` file                                                           | Present, broken      | `streaming_agent.py` exists; no TAOD loop, no `loop_config` / `budget_check` (CRIT-05, MED-04).                                                                                                                                                                                                                                                                                                        |
| §2.1 owns TAOD loop + typed events                                                   | NOT MET              | Calls `inner.run_async()` once and synthesises events.                                                                                                                                                                                                                                                                                                                                                 |
| §2.2 `MonitoredAgent` file                                                           | Present              | `monitored_agent.py`. Cost tracking via `CostTracker` works.                                                                                                                                                                                                                                                                                                                                           |
| §2.2 BudgetExhausted propagation through StreamingAgent                              | Partially MET        | Implemented as exception → event in `streaming_agent.py:182-188`, but only fires if `inner.run_async()` raised after cost tracking — never tested.                                                                                                                                                                                                                                                     |
| §2.3 `L3GovernedAgent` file                                                          | Present              | `governed_agent.py` (named `governed_agent.py`, not `l3_governed_agent.py` as spec §2.3 line 347 says — minor path drift, acceptable).                                                                                                                                                                                                                                                                 |
| §2.3 `_ProtectedInnerProxy`                                                          | Present              | Lines 63-97. But bypassed by `WrapperBase.innermost` (MED-08).                                                                                                                                                                                                                                                                                                                                         |
| §2.3 envelope evaluation (financial / operational / temporal / data / communication) | Partially MET        | Financial + operational + posture ceiling implemented; temporal / data access / communication are stubs (`pass` placeholders in spec §2.3 line 489-512 — implementation also leaves them as no-ops, so faithful but incomplete).                                                                                                                                                                       |
| §2.3 `enforcement_mode` (enforce / shadow / disabled)                                | NOT MET              | Parameter absent. No shadow mode at all.                                                                                                                                                                                                                                                                                                                                                               |
| §2.3 posture ceiling lowering                                                        | Wired-but-orphaned   | Mechanism exists but no posture field on config to lower (CRIT-01).                                                                                                                                                                                                                                                                                                                                    |
| §2.4 `SupervisorAgent` wrapper                                                       | NOT PRESENT          | No `supervisor_agent.py` (HIGH-01).                                                                                                                                                                                                                                                                                                                                                                    |
| §2.4 `RoutingStrategy` base + `RoundRobin` + `LLMBased`                              | NOT PRESENT          | None of these classes exist; legacy `runtime.py` uses Jaccard similarity (HIGH-01).                                                                                                                                                                                                                                                                                                                    |
| §2.4 LLM-based routing R2-001 fix                                                    | NOT MET              | Routing is keyword/Jaccard.                                                                                                                                                                                                                                                                                                                                                                            |
| §2.5 `WorkerAgent` wrapper + `capability_card` property                              | NOT PRESENT          | No `worker_agent.py`.                                                                                                                                                                                                                                                                                                                                                                                  |
| §3.1 Canonical stacking order                                                        | Documented + partial | `wrapper_base.py:8-10` documents it. `delegate.py:343-376` only stacks L3Gov + Monitored. StreamingAgent never enters.                                                                                                                                                                                                                                                                                 |
| §3.2 Streaming sees budget via callback                                              | NOT MET              | No `budget_check` callback (MED-04).                                                                                                                                                                                                                                                                                                                                                                   |
| §3.3 Posture-aware validation table (PSEUDO/TOOL → strict, etc.)                     | NOT MET              | No posture field, no posture-aware validator (CRIT-01).                                                                                                                                                                                                                                                                                                                                                |
| §3.4 Wrapper invariants (1-7)                                                        | Partial              | (1) wrapper inherits BaseAgent ✓; (2) `_inner` ✓; (3) `get_parameters` proxy ✓; (4) `to_workflow` proxy + StreamingAgent override ✓; (5) "do not modify inner state" ✓; (6) "MUST call `_inner`" — flag exists but unenforced (MED-05); (7) error → event conversion partial (only `BudgetExhaustedError` is converted; `GovernanceRejectedError` is not — falls into the generic `Exception` branch). |
| §5.1 Frozen events module at `kaizen_agents/events.py`                               | Present + diverged   | File exists, frozen ✓, but base class renamed `StreamEvent` and old `delegate/events.py` still active (MED-03).                                                                                                                                                                                                                                                                                        |
| §5.1 `StreamBufferOverflow`, `StreamTimeoutError`, `TurnComplete.iterations`         | Present              | All in `events.py:154-171` and `events.py:117`.                                                                                                                                                                                                                                                                                                                                                        |
| §6 AgentLoop moved to `kaizen.core.agent_loop`                                       | NOT MET              | A different class with the same name was added; the actual streaming loop is still in `delegate/loop.py` (HIGH-02).                                                                                                                                                                                                                                                                                    |
| §6.2 `AgentLoopConfig.from_agent`                                                    | Diverged             | Implementation has `max_cycles / temperature / max_tokens`. Spec has `max_turns / timeout / streaming`.                                                                                                                                                                                                                                                                                                |
| §6.3 Architectural invariant preserved                                               | Trivially true       | The new `agent_loop.py` does not import workflow primitives.                                                                                                                                                                                                                                                                                                                                           |
| §7 Migration order step 8 (backward-compat shims at old paths)                       | NOT MET              | `delegate/events.py` and `delegate/loop.py` still hold their original implementations, not shims.                                                                                                                                                                                                                                                                                                      |
| §7 step 9 (`posture` field)                                                          | NOT MET              | CRIT-01.                                                                                                                                                                                                                                                                                                                                                                                               |
| §7 step 10 (posture-aware StructuredOutput)                                          | NOT MET              | `structured_output.py` has zero posture references.                                                                                                                                                                                                                                                                                                                                                    |
| §7 step 11 (per-wrapper unit tests)                                                  | NOT MET              | CRIT-04.                                                                                                                                                                                                                                                                                                                                                                                               |
| §7 step 12 (stacking integration tests)                                              | NOT MET              | CRIT-04.                                                                                                                                                                                                                                                                                                                                                                                               |
| §7 step 13 (Delegate uses wrapper stack)                                             | Partial              | Yes for L3Gov + Monitored, never for StreamingAgent.                                                                                                                                                                                                                                                                                                                                                   |
| §11.1 envelope bypass mitigations                                                    | Partial / broken     | `_ProtectedInnerProxy` exists but `innermost` bypasses it (MED-08).                                                                                                                                                                                                                                                                                                                                    |
| §11.2 shadow mode mitigations                                                        | NOT MET              | Shadow mode absent (HIGH-03).                                                                                                                                                                                                                                                                                                                                                                          |
| §11.3 posture poisoning mitigations                                                  | NOT MET              | No posture field, no IntEnum, no deserialization guard.                                                                                                                                                                                                                                                                                                                                                |
| §11.4 stacking order attacks                                                         | Partial              | Duplicate detection ✓; `envelope=None` validation absent; `describe_stack()` absent.                                                                                                                                                                                                                                                                                                                   |
| §11.5 LLMBased prompt injection                                                      | Moot                 | Feature absent.                                                                                                                                                                                                                                                                                                                                                                                        |
| §11.6 backpressure DoS                                                               | Partial              | Buffer + timeout exist with wrong defaults; impossible to overflow because only one event is ever produced.                                                                                                                                                                                                                                                                                            |

## Spec-Item Audit Table — SPEC-04

| Spec section / item                                                             | Status         | Evidence                                                                                                                                                 |
| ------------------------------------------------------------------------------- | -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| §1 BaseAgent < 1000 LOC                                                         | MET            | 891 LOC at `base_agent.py`.                                                                                                                              |
| §2.1 `posture: AgentPosture` on BaseAgentConfig                                 | NOT MET        | CRIT-01.                                                                                                                                                 |
| §2.1 Frozen BaseAgentConfig                                                     | NOT MET        | CRIT-02.                                                                                                                                                 |
| §2.1 Deprecated mixin / strategy / mcp / hooks fields                           | Partial        | Fields still present, not marked deprecated, BaseAgent still applies them.                                                                               |
| §2.2 `AgentPosture` IntEnum with `PSEUDO/TOOL/SUPERVISED/AUTONOMOUS/DELEGATING` | NOT MET        | Enum is `(str, Enum)` with different names (MED-01).                                                                                                     |
| §2.2 `from_string()` / `instruction_enforcement()` methods                      | NOT MET        | Methods absent.                                                                                                                                          |
| §2.3 7 extension points carry `@deprecated`                                     | NOT MET        | CRIT-03.                                                                                                                                                 |
| §2.3 BaseAgent uses `kailash_mcp.MCPClient`                                     | NOT MET        | Uses `kailash.mcp_server.client.MCPClient` (MED-02).                                                                                                     |
| §2.3 BaseAgent uses `kailash_mcp.tools.ToolRegistry`                            | NOT MET        | No use of unified ToolRegistry; the mixin owns its own discovery dicts (`_discovered_mcp_tools`).                                                        |
| §2.3 `configure_mcp()` public method                                            | NOT MET        | No method; MCP setup happens implicitly inside `AgentLoop.run_sync` on first call.                                                                       |
| §2.3 Posture-aware StructuredOutput auto-config                                 | NOT MET        | CRIT-01 dependency.                                                                                                                                      |
| §2.3 BaseAgent.posture property                                                 | NOT MET        | Property absent.                                                                                                                                         |
| §3.1 Mixins moved to wrappers                                                   | NOT MET        | Mixins live on (MED-07).                                                                                                                                 |
| §3.1 Permission system moved to L3GovernedAgent                                 | NOT MET        | Permission system still inline in BaseAgent (`base_agent.py:133-152`).                                                                                   |
| §3.1 Hook system moved to StreamingAgent                                        | NOT MET        | HookManager still inline; AgentLoop calls `_trigger_hook_sync` directly.                                                                                 |
| §3.3 Subclass extension points work via deprecated path                         | Trivially MET  | They work; they just don't warn (CRIT-03).                                                                                                               |
| §3.4 Posture-aware structured output examples                                   | NOT MET        | Spec example code references `posture=AgentPosture.AUTONOMOUS` — not constructible.                                                                      |
| §4 Constructor backward compat with `**legacy_kwargs`                           | Partial        | `**kwargs` accepted but no allowlist, no warning, no audit.                                                                                              |
| §5 Migration order step 1 (`AgentPosture`)                                      | Diverged       | Different names + Enum kind (MED-01).                                                                                                                    |
| §5 step 2 (`posture` on config)                                                 | NOT MET        | CRIT-01.                                                                                                                                                 |
| §5 step 3 (`StructuredOutput.from_signature(... posture=)`)                     | NOT MET        | No posture parameter on StructuredOutput.                                                                                                                |
| §5 step 4 (`@deprecated` decorator)                                             | MET            | `kaizen/core/deprecation.py` exists.                                                                                                                     |
| §5 step 5 (apply `@deprecated`)                                                 | NOT MET        | CRIT-03.                                                                                                                                                 |
| §5 step 6 (use `get_provider_for_model`)                                        | Partial        | `_simple_execute_async` (`base_agent.py:320`) hardcodes `OpenAIProvider(use_async=True)` and bypasses the registry.                                      |
| §5 step 7 (use `MCPClient.discover_and_register`)                               | NOT MET        | MED-02.                                                                                                                                                  |
| §5 step 8 (replace inline ToolRegistry)                                         | NOT MET        | Custom dict-based registry in MCPMixin.                                                                                                                  |
| §5 step 9 (remove mixin application)                                            | NOT MET        | MED-07.                                                                                                                                                  |
| §5 step 11 (remove inline observability/permission/hook setup)                  | NOT MET        | All three still inline.                                                                                                                                  |
| §5 step 12 (`configure_mcp()` public)                                           | NOT MET        | Absent.                                                                                                                                                  |
| §5 step 13 (existing test suite zero regressions)                               | Claimed MET    | `.test-results` not re-run by this audit; per `02-implementation-redteam.md` it passes — but zero new posture / wrapper tests added.                     |
| §5 step 14 (188 subclass tests)                                                 | Trivially MET  | Subclass tests pass because nothing changed for them — including the `_default_signature` etc. paths.                                                    |
| §5 step 15 (new tests for posture / configure_mcp)                              | NOT MET        | None of these tests exist.                                                                                                                               |
| §6 Subclass compatibility tests                                                 | Partial        | `test_base_agent_slimming.py` has `test_subclass_with_custom_signature` and `test_subclass_with_custom_strategy` — neither asserts deprecation warnings. |
| §6 New posture-aware tests (`test_posture_aware_strict_validation`, etc.)       | NOT MET        | None present.                                                                                                                                            |
| §6 `test_configure_mcp_registers_tools`                                         | NOT MET        | No `configure_mcp()` exists.                                                                                                                             |
| §6 `test_posture_default_is_tool`                                               | NOT MET        | No posture field.                                                                                                                                        |
| §6 `test_posture_from_envelope_ceiling`                                         | NOT MET        | Mechanism is wired but unreachable from config.                                                                                                          |
| §10.1 Deferred MCP window mitigations                                           | NOT MET        | Whole `_deferred_mcp` flow absent.                                                                                                                       |
| §10.2 `_DEPRECATED_PARAMETERS` allowlist                                        | NOT MET        | Absent.                                                                                                                                                  |
| §10.3 Frozen config + `_posture` private copy                                   | NOT MET        | Both absent.                                                                                                                                             |
| §10.4 Hook context restriction + posture refusal                                | NOT MET        | Hooks see full payloads.                                                                                                                                 |
| §10.5 Signature-aware key selection in `_build_messages`                        | Not applicable | Method does not exist in current BaseAgent.                                                                                                              |

## Cross-Reference Audit

- `.spec-coverage` line 64-75 — multiple false claims (MIN-01).
- `02-implementation-redteam.md` line 7 "0 CRITICAL, 0 HIGH" — superseded by this audit; the prior pass did not exercise the wrappers, did not check posture, did not verify deprecation application, did not look for the missing Supervisor/Worker classes, and did not run the LLM-first routing rule against `runtime.py`.
- `scripts/convergence-verify.py 39/39 PASS` — verifies file existence + import success only. None of the SPEC-03 / SPEC-04 invariants the script claims to validate are actually re-runnable from this audit's evidence.
- ADR-001 / ADR-003 / ADR-010 — ADR-001 (composition over extension points) is half-honoured (wrappers exist, extension points still active without warnings). ADR-003 (streaming as wrapper) is structurally honoured (file exists) but functionally defeated (single non-streaming call). ADR-010 (CO Five Layers) is unrealised because posture is absent.

## Implementation Roadmap (to fix)

### Phase A — Block release (Critical / High)

1. Add `posture: AgentPosture = AgentPosture.TOOL` to `BaseAgentConfig`. Either expand the existing `(str, Enum)` enum to include the spec names (with both legacy and new names as aliases) or introduce a new `IntEnum` and a translation table to the legacy string enum. Either way, `BaseAgent.posture` property must work.
2. Make `BaseAgentConfig` `@dataclass(frozen=True)`. Move post-init normalization to `object.__setattr__`. Update `__post_init__` accordingly. Re-run the existing config tests for breakage. Add a test that mutation raises `FrozenInstanceError`.
3. Apply `@deprecated(...)` to all 7 extension points in `base_agent.py`. Add a test that asserts each method raises `DeprecationWarning` when overridden by a subclass.
4. Implement the SPEC-03 §8 / SPEC-04 §6 test suites:
   - `tests/unit/test_wrapper_base.py` — duplicate detection, `_inner_called` enforcement, `innermost` proxy enforcement.
   - `tests/unit/test_streaming_agent.py` — TAOD events sequence, BudgetExhausted conversion, governance rejection conversion, timeout, buffer overflow, sync `run()` path.
   - `tests/unit/test_monitored_agent.py` — cost tracking, budget exhaustion (pre and post check), `_record_usage` paths.
   - `tests/unit/test_governed_agent.py` — financial / operational / posture rejection, shadow mode, audit log, `enforcement_mode` parameter.
   - `tests/integration/test_wrapper_stacking.py` — full canonical stack with mock LLM.
5. Replace `StreamingAgent.run_stream()` with a real TAOD loop that consumes from `kaizen.core.agent_loop.AgentLoop` (after the loop is moved per item 9). Add `loop_config`, `budget_check`, `max_buffered_events`, `stream_timeout_s` parameters per spec.
6. Implement `SupervisorAgent` (`kaizen_agents/supervisor_agent.py`) and `WorkerAgent` (`kaizen_agents/worker_agent.py`) per SPEC-03 §2.4 / §2.5. Implement `RoutingStrategy` base + `RoundRobin` + `LLMBased` with the internal BaseAgent + `_WorkerRoutingSignature`. Delete or re-route the legacy `_route_semantic` Jaccard path so the LLM-first rule is no longer violated. Add tests for `test_supervisor_routes_via_llm_based` and `test_supervisor_rejects_keyword_routing_strategies`.
7. Move the actual TAOD loop from `kaizen_agents/delegate/loop.py` to `kaizen/core/agent_loop.py`. Update `AgentLoopConfig` to the SPEC-03 §6.2 fields. Either rename the existing `kaizen/core/agent_loop.py` (the strategy executor) or merge the two responsibilities under one cleanly-separated module. Add a backward-compat shim at the old import path.
8. Implement SPEC-03 §11.1 enforcement: gate `WrapperBase.innermost` behind a `_ProtectedInnerProxy` when any wrapper in the chain owns governance. Make `_inner_called` raise `WrapperInvariantError` if a non-blocked wrapper exits without setting it.
9. Implement SPEC-03 §11.2 shadow mode: `enforcement_mode: Literal["enforce", "shadow", "disabled"]`, warn-on-N audit signals, refuse env-var override.
10. Implement SPEC-03 §11.4: raise `ValueError` on `L3GovernedAgent(envelope=None)`; add `describe_stack()`.
11. Implement SPEC-04 §10.1 — `_deferred_mcp` plumbing (frozen tuple, `__setattr__` guard, audit log on first run, `configure_mcp()` post-init lock).
12. Implement SPEC-04 §10.2 — `_DEPRECATED_PARAMETERS` frozenset, `**legacy_kwargs` allowlist, per-key warning, `construction_audit` attribute.

### Phase B — Tighten (Medium)

13. Migrate `BaseAgent` to `from kailash_mcp import MCPClient` and `from kailash_mcp.tools import ToolRegistry`. Replace `_discovered_mcp_*` dicts with the unified registry.
14. Collapse the two event modules: keep `kaizen_agents/events.py` as canonical, convert `delegate/events.py` to a `from kaizen_agents.events import *` shim, retire the `DelegateEvent` rename in favour of the spec name.
15. Move mixin application + permission system + hook system out of BaseAgent and into the wrapper stack. Mark the config flags `@deprecated` (or remove them).
16. Export `WrapperBase, StreamingAgent, MonitoredAgent, L3GovernedAgent, SupervisorAgent, WorkerAgent, BudgetExhaustedError, GovernanceRejectedError` from `kaizen_agents/__init__.py`.

### Phase C — Cleanup

17. Rewrite `.spec-coverage` to reflect actual coverage. Add a CI check that asserts coverage is 100% AND that the verification script validates spec semantics, not just file existence.
18. Update `02-implementation-redteam.md` to retract the round-1 PASS verdict.
19. File cross-SDK issue against kailash-rs to track Python parity gaps for `posture` IntEnum naming, R2-001 LLM routing, and the StreamingAgent TAOD parity.

## Success Criteria

- [ ] `BaseAgentConfig` is `@dataclass(frozen=True)` and includes `posture: AgentPosture = AgentPosture.TOOL`.
- [ ] All 7 extension points in `BaseAgent` carry `@deprecated(..., since="2.5.0")` and a regression test asserts the warning fires for each.
- [ ] Wrapper test suite (`test_wrapper_base.py`, `test_streaming_agent.py`, `test_monitored_agent.py`, `test_governed_agent.py`, `test_wrapper_stacking.py`) exists with > 30 tests covering all SPEC-03 §8 cases.
- [ ] `StreamingAgent.run_stream()` yields incremental tokens from a real TAOD loop, accepts `budget_check`, and emits `ToolCallStart`/`ToolCallEnd` for tool executions.
- [ ] `SupervisorAgent` + `WorkerAgent` + `LLMBased` exist; `_route_semantic` Jaccard path is deleted; `test_supervisor_rejects_keyword_routing_strategies` passes.
- [ ] `kaizen.core.agent_loop.AgentLoop` is the TAOD loop; `kaizen_agents/delegate/loop.py` is a `from kaizen.core.agent_loop import *` shim.
- [ ] All security mitigations from SPEC-03 §11.1-§11.6 and SPEC-04 §10.1-§10.5 are implemented and have tests.
- [ ] `BaseAgent` imports `MCPClient` and `ToolRegistry` from `kailash_mcp`.
- [ ] `.spec-coverage` is rewritten and audited per the new evidence rules; `convergence-verify.py` validates semantics.

## Cross-SDK Notes

Per `rules/cross-sdk-inspection.md`, the following Python gaps map to required Rust action:

- AgentPosture IntEnum names (`PSEUDO/TOOL/SUPERVISED/AUTONOMOUS/DELEGATING`) — verify Rust's `ExecutionMode` expansion uses the same names.
- LLM-based routing in SupervisorAgent — Rust `kaizen-agents/src/orchestration/supervisor.rs` already uses LLM routing per audit notes; Python must catch up.
- StreamingAgent TAOD loop — Rust `kaizen-agents/src/streaming/agent.rs` is canonical; Python must mirror.

A cross-SDK alignment issue should be filed once Phase A items are scheduled.
