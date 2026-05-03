# Red Team — SPEC-05, SPEC-06, SPEC-08 Deep Audit

**Date**: 2026-04-08
**Workspace**: platform-architecture-convergence
**Phase**: 04 (validate) — second-look red team
**Validator**: analyst (deep specification compliance audit)
**Verdict**: FAIL — multiple CRITICAL and HIGH gaps

## Executive Summary

The prior red team report (`04-validate/02-implementation-redteam.md`) declared "PASS WITH MINOR NOTES" and "100% spec coverage (94/94)". This second-look audit finds that statement to be substantially overstated. The audit examined each spec line-by-line against actual source files and tests.

**Findings tally**:

- **CRITICAL**: 7 (security defenses missing, contract violations, false-security middleware)
- **HIGH**: 8 (incomplete migrations, wrong wrapper order, missing test classes)
- **MEDIUM**: 6 (deprecation/shim hygiene, observability)
- **LOW**: 4

The platform is NOT ready for the v3.0 envelope SPEC-05/06/08 promises. SPEC-05 §2 constructor contract is broken, SPEC-06 §2 PACTMiddleware does not exist, SPEC-08 §2 audit consolidation is partial — five of the six "old audit modules" still hold their own implementations and are not consuming the canonical store.

The prior MINOR-002 finding ("delegate internal modules preserved as full implementations") was dispositioned ACCEPTED on the grounds that file preservation is "pragmatically equivalent" to shimming. That disposition is incorrect: shim hygiene is a SECURITY defense (SPEC-05 §9.4 shim impersonation), not just a hygiene preference. Preserving the original files without DeprecationWarning, hash verification, and removal scheduling LEAVES the §9.4 attack surface fully open.

---

## SPEC-05: Delegate Engine Facade

### CRITICAL-05-01 — Constructor contract is broken: `signature=`, `mcp_servers=`, `inner_agent=` are missing

**Spec ref**: §2 lines 33-52
**Location**: `/Users/esperie/repos/loom/kailash-py/packages/kaizen-agents/src/kaizen_agents/delegate/delegate.py` lines 284-295

The spec mandates this constructor signature:

```python
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
    envelope: Optional[ConstraintEnvelope] = None, # NEW
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    inner_agent: Optional[BaseAgent] = None,       # NEW — escape hatch
):
```

Actual constructor in `delegate.py:284`:

```python
def __init__(
    self,
    model: str = "",
    *,
    tools: ToolRegistry | list[str] | None = None,
    system_prompt: str | None = None,
    max_turns: int = 50,
    budget_usd: float | None = None,
    adapter: StreamingChatAdapter | None = None,
    config: KzConfig | None = None,
    envelope: ConstraintEnvelope | None = None,
) -> None:
```

**Missing**: `signature`, `temperature`, `max_tokens`, `mcp_servers`, `api_key`, `base_url`, `inner_agent`.

**Impact**: The spec's _new capabilities_ — structured outputs (`signature=`), MCP server configuration through the facade, and the inner-agent escape hatch — are entirely impossible. The §7 test plan tests `Delegate(model="mock", signature=TestSig)` and `Delegate(model="mock", signature=TestSig, mcp_servers=[test_config()], budget_usd=1.0)` — these tests cannot exist because the parameters do not exist.

**Severity**: CRITICAL — primary user-facing API does not match spec.

---

### CRITICAL-05-02 — Wrapper stack order is reversed and `StreamingAgent` is not in the stack

**Spec ref**: §3 lines 78-119
**Location**: `delegate.py` lines 339-377

Spec target stack (innermost → outermost):

```
core BaseAgent → MonitoredAgent → L3GovernedAgent → StreamingAgent
```

Spec rationale: `MonitoredAgent` is "Learning + soft Guardrails" and goes innermost (per-call cost tracking happens before governance veto). `L3GovernedAgent` is "Hard Guardrails". `StreamingAgent` is "always outermost".

Actual stack in `delegate.py:339-377`:

```python
self._loop_agent: BaseAgent = _LoopAgent(self._loop, resolved_model)
# Stack L3GovernedAgent if envelope provided
if envelope is not None:
    self._governed = _Gov(self._loop_agent, envelope=envelope)
    self._loop_agent = self._governed
# Stack MonitoredAgent if budget provided
if budget_usd is not None:
    self._monitored = _Mon(self._loop_agent, budget_usd=budget_usd, model=resolved_model)
    self._loop_agent = self._monitored
```

This produces (innermost → outermost):

```
_LoopAgent → L3GovernedAgent → MonitoredAgent
```

Two structural defects:

1. **Reverse order**: `MonitoredAgent` and `L3GovernedAgent` are swapped. With `MonitoredAgent` outermost, governance now checks first AND budget-tracking wraps governance — meaning a `BLOCKED` action from L3 still flows back through cost accounting in a wrapper that thinks it's outermost. Worse, the outer `MonitoredAgent` evaluates a request that L3 has not yet vetoed, so its `budget_check` runs against requests that may never execute.
2. **`StreamingAgent` is not in the stack at all**. The Delegate facade ignores the `StreamingAgent` primitive that already exists at `packages/kaizen-agents/src/kaizen_agents/streaming_agent.py`. Instead it uses an internal `_LoopAgent` bridge that wraps the OLD `delegate.loop.AgentLoop` (the parallel implementation that the spec says to delete).

The streaming UX is therefore not delivered by the wrapper-composition pipeline — it is delivered by `_LoopAgent` calling into `delegate/loop.py` directly, bypassing every wrapper added on top.

**Impact**:

- L3 governance verdicts can be evaluated against cost-decorated requests instead of source-of-truth requests.
- Cost metering counts work that may then be vetoed.
- The streaming pipeline goes around the wrappers entirely — `MonitoredAgent.before_invoke()` never sees streaming traffic, `L3GovernedAgent.verify()` never sees streaming traffic.

**Severity**: CRITICAL — security and accounting invariants broken.

---

### CRITICAL-05-03 — Old parallel implementation files are NOT shimmed; `delegate/{loop,mcp,adapters,tools/hydrator}.py` still hold full implementations

**Spec ref**: §5 lines 155-167, §6 lines 168-178, §9.4 lines 257-266
**Locations**:

- `packages/kaizen-agents/src/kaizen_agents/delegate/loop.py` (821 LOC, full implementation)
- `packages/kaizen-agents/src/kaizen_agents/delegate/mcp.py` (509 LOC, full implementation)
- `packages/kaizen-agents/src/kaizen_agents/delegate/adapters/{openai_adapter,anthropic_adapter,google_adapter,ollama_adapter}.py` (1454 LOC total, full implementations)
- `packages/kaizen-agents/src/kaizen_agents/delegate/tools/hydrator.py` (still present alongside the new `kailash_mcp/tools/hydrator.py`)

Spec §5 says "MOVED to `kaizen/core/agent_loop.py`", "DELETED" (replaced by `kailash_mcp.MCPClient`), "DELETED" (replaced by `kaizen.providers.*`), "MOVED to `kailash_mcp/tools/hydrator.py`". Spec §6 step 5 says "Add backward-compat shim at `kaizen_agents/delegate/__init__.py`" and step 8 says "Delete old files after all tests pass".

Spec §9.4 (security) explicitly mandates each shim MUST emit `DeprecationWarning`, MUST verify hash, MUST be removed in v3.0, and the suspicious-import warning chain MUST be in place.

Verification of current state:

```
$ grep -i "DeprecationWarning\|deprecated" delegate/loop.py delegate/mcp.py
(no matches in either file)
```

No deprecation warning is emitted on import. No hash check. No removal date. The new `kailash-mcp` package exists at `packages/kailash-mcp/src/kailash_mcp/tools/hydrator.py`, but the old `kaizen_agents/delegate/tools/hydrator.py` is also still present — there are now TWO hydrator implementations.

The prior red team report MINOR-002 acknowledged this and dispositioned it ACCEPTED on the grounds that 188 subclasses depend on these import paths. That disposition treats this as a hygiene issue. It is a security issue:

- §9.4 shim impersonation defense is the entire point of the deprecation/hash story. Without DeprecationWarning, an attacker who typo-squats (`kaizen_agents_delegate_loop` on PyPI) can shadow imports without any signal.
- Two parallel hydrator implementations means a security fix to one is not picked up by consumers of the other.
- A v4.0 removal note in `docs/migration/v2-to-v3.md` is not a runtime defense.

**Severity**: CRITICAL — security defense (§9.4) is missing AND parallel implementations diverge silently.

---

### CRITICAL-05-04 — Constructor IO and `asyncio.run()` defenses are not implemented

**Spec ref**: §9.1 lines 224-234
**Location**: `delegate.py` constructor `__init__` (lines 284-378)

Spec mandates four mitigations:

1. Delegate MUST NOT call `asyncio.run()` in `__init__`. ✅ Verified — the facade constructor does not call `asyncio.run()` directly.
2. Delegate MUST detect running event loops via `asyncio.get_running_loop()` and refuse synchronous `run()` calls from within them, with an error message pointing at `run_async()` or the streaming variant.
3. Constructors MUST NOT make outbound network calls. Any IO in the constructor raises `ConstructorIOError`.
4. Rate-limit Delegate construction (default 100/sec) emitting `DelegateConstructionRateLimitExceeded`.

Actual:

- Mitigation 2: `run_sync()` (lines 547-596) detects a running loop and falls back to a `ThreadPoolExecutor` running `asyncio.run` instead of refusing. **It does the opposite of what the spec mandates** — instead of pointing the caller at `run_async()`, it silently fires up a background thread to wrap `asyncio.run`. This trades a clear error message for a deadlock/leak risk surface.
- Mitigation 3: `ConstructorIOError` does not exist anywhere in the repo. There is no constructor IO ban; nothing prevents a custom `inner_agent` (when added) from making outbound calls during composition.
- Mitigation 4: `DelegateConstructionRateLimitExceeded` does not exist. No rate limiter exists at any layer.

Additionally, `_LoopAgent.run()` (lines 165-198) is a sync method that internally calls `asyncio.run()` (lines 185, 188). When `_LoopAgent` is wrapped by `MonitoredAgent` or `L3GovernedAgent` whose `before_invoke()` hooks are sync, `_LoopAgent.run()` runs and the inner `asyncio.run()` fires from inside whatever loop the wrapper is on. This is the exact deadlock surface §9.1 is meant to prevent — the constructor moved its IO out, but the runtime path put it right back in.

**Severity**: CRITICAL — three of four §9.1 mitigations missing; fourth is implemented in the wrong direction.

---

### CRITICAL-05-05 — §9.2 credential-leakage defenses (SecretRef, scrub_secrets, inner_agent validation) entirely missing

**Spec ref**: §9.2 lines 236-244
**Location**: nowhere

Spec mitigations:

1. `MCPServerConfig` MUST store credentials separately from the URL.
2. Audit logger MUST use `scrub_secrets` filter on every log entry.
3. `inner_agent=` parameter MUST call `inner_agent.get_security_context()` and refuse the construction if any MCP server config has a credential-bearing URL in the non-scrubbed field.
4. Integration test uses `caplog` to verify no secret ever appears in log output.

Verification:

```
$ grep -r "SecretRef\|scrub_secrets\|get_security_context" packages/kaizen-agents/
(no matches)
```

None of the four mitigations exist. The `inner_agent` parameter itself does not exist (CRITICAL-05-01), so neither does its validator. There is no log filter wrapping the Delegate logger. There is no integration test for credential scrubbing. `MCPServerConfig` (in `kailash_mcp`) was not audited for the URL/credential split — the prior red team report does not mention §9.2 at all.

**Severity**: CRITICAL — credentials in MCP server configurations have no defined leakage defense.

---

### CRITICAL-05-06 — §9.3 tool registry poisoning defense (`ToolRegistryCollisionError`, server-name prefixing) entirely missing

**Spec ref**: §9.3 lines 246-256
**Location**: nowhere

Spec mitigations:

1. Delegate MUST merge MCP tool registrations with `inner/<name>` and `delegate/<name>` prefixing. Collisions raise `ToolRegistryCollisionError`.
2. Tool name collisions MUST be logged to the audit store before being rejected.
3. Wrappers proxy `get_tools()` from the inner agent (no re-registration).
4. Red-team test: construct a Delegate with benign `inner_agent` and malicious `mcp_servers` that duplicates tool names.

Verification:

```
$ grep -r "ToolRegistryCollisionError" packages/kaizen-agents/ src/kailash/
(no matches)
```

No collision class. No prefixing. The `_resolve_tools` helper mentioned in spec §3 step 1 does not exist on the facade. Because `mcp_servers=` and `inner_agent=` are themselves missing (CRITICAL-05-01), the entire tool-poisoning attack surface is effectively unmitigated whenever Delegate is used with externally registered tools.

**Severity**: CRITICAL — registry poisoning has no defense.

---

### HIGH-05-07 — `events.py` moved but `hooks.py` and `loop.py` were NOT moved per §5

**Spec ref**: §5 lines 156-166, §6 step 1, step 2, step 3
**Locations**:

- `events.py`: spec says `delegate/events.py → kaizen_agents/events.py`. Status: ✅ moved (file exists at `packages/kaizen-agents/src/kaizen_agents/events.py`).
- `hooks.py`: spec says `delegate/hooks.py → kaizen_agents/hooks.py`. Status: ❌ NOT moved. `kaizen_agents/hooks.py` does not exist.
- `loop.py`: spec says `delegate/loop.py → kaizen/core/agent_loop.py`. Status: ❌ NOT moved. `kaizen/core/agent_loop.py` exists, but it is a DIFFERENT file (the BaseAgent execution loop with TAOD model, ~50 LOC of dataclasses), NOT the moved Delegate AgentLoop. The original `delegate/loop.py` (821 LOC) still exists in its old home and is the file actually used by the Delegate facade.
- `tools/hydrator.py`: spec says `delegate/tools/hydrator.py → kailash_mcp/tools/hydrator.py`. Status: ⚠️ both files exist — moved but original not deleted (see CRITICAL-05-03).

**Severity**: HIGH — migration order in §6 is partially executed; the parts that matter most for code consolidation (loop.py, hooks.py) are not done.

---

### HIGH-05-08 — `core_agent` and `streaming_agent` properties are missing from the public API

**Spec ref**: §2 lines 65-74
**Location**: `delegate.py` lines 400-435

Spec mandates two new properties:

```python
@property
def core_agent(self) -> BaseAgent: ...          # NEW — access inner BaseAgent
@property
def streaming_agent(self) -> StreamingAgent: ... # NEW — access outermost wrapper
```

Actual: `delegate.py` exposes `loop`, `tool_registry`, `budget_usd`, `consumed_usd`, `budget_remaining`, and `wrapper_stack` (lines 400-435). It does NOT expose `core_agent` or `streaming_agent`. The closest equivalent is `wrapper_stack`, which returns `self._loop_agent` (the bridge wrapper, not a real `BaseAgent`).

**Impact**: External code following the spec contract cannot reach the inner BaseAgent or the streaming wrapper. The spec's "Layer 3 access" pattern is undeliverable.

**Severity**: HIGH — public-API gap.

---

### HIGH-05-09 — `_LoopAgent` is a sham wrapper: it bridges to the old AgentLoop and bypasses the wrappers it claims to live inside

**Spec ref**: §3 (the entire composition story)
**Location**: `delegate.py` lines 141-216 (the `_LoopAgent` class) and lines 488-545 (the `run()` method)

The wrapper-composition pattern depends on the wrappers actually intercepting calls. `_LoopAgent` is a `BaseAgent` subclass whose `run()` method calls `_loop.run_turn()` (the OLD AgentLoop). When the Delegate facade's `run()` method (line 436) wants to stream, it does NOT call `self._loop_agent.run_async()` (which would go through `MonitoredAgent` and `L3GovernedAgent`). Instead it calls `self._loop.run_turn(prompt)` directly (line 498), bypassing every wrapper in the stack.

The wrappers are constructed but never invoked through the streaming path. They only get exercised in the `run_sync()` path (line 547) — and even there, only via the `_LoopAgent.run()` bridge that does its own `asyncio.run`.

**Impact**: The composition facade is not actually composing. The wrappers are dead weight in the streaming path — the path the spec calls "the primary entry point".

**Severity**: HIGH — the architectural premise of SPEC-05 is not realized in the streaming path.

---

### MEDIUM-05-10 — Cost-estimation table is hardcoded in the facade and includes commercial product names

**Spec ref**: SPEC-05 §4 (Layers) and `rules/independence.md`, `rules/env-models.md`
**Location**: `delegate.py` lines 77-97

The facade hardcodes a cost table keyed on prefixes including `"claude-"`, `"gpt-4o"`, `"gpt-4"`, `"gpt-5"`, `"o1"`, `"o3"`, `"o4"`, `"gemini-"`. These are commercial product names, in violation of `rules/independence.md` "No proprietary product names". `rules/env-models.md` also requires model names to come from `.env`.

Even setting aside the policy violation, hardcoded prices drift from reality and silently undercount budget after vendor price changes. This is the exact "naive fallback" pattern that `rules/zero-tolerance.md` Rule 4 forbids ("No workarounds for core SDK issues" — here, missing the canonical CostTracker integration).

**Severity**: MEDIUM — drives wrong budget enforcement and violates two rules.

---

## SPEC-06: Nexus Auth/Audit Migration + PACTMiddleware

### CRITICAL-06-01 — `PACTMiddleware` does not exist (entire §2 is undelivered)

**Spec ref**: §2 lines 39-140, §3 Phase 5c
**Location**: should be at `packages/kailash-nexus/src/nexus/middleware/governance.py` — does not exist

```
$ ls packages/kailash-nexus/src/nexus/middleware/
csrf.py  security_headers.py  cache.py  __init__.py
```

No `governance.py`. No `PACTMiddleware` class anywhere in the codebase outside the spec doc itself. No tests for PACT-Nexus integration. No wiring into NexusEngine's enterprise middleware stack. SPEC-06 §3 Phase 5c (steps 18, 19, 20) is entirely undelivered.

**Spec §1 framing**: "PACT governance: **MISSING** | `kailash.trust.pact.GovernanceEngine` | **BUILD** `nexus/middleware/governance.py`". The "BUILD" task was not done.

**Impact**: The "missing Nexus→PACT integration" identified in the audit is still missing. Nexus has no PACT enforcement at the request boundary. Every request enters Nexus, bypasses PACT, hits handlers — exactly the gap SPEC-06 was written to close.

**Severity**: CRITICAL — entire Phase 5c missing.

---

### CRITICAL-06-02 — `_evaluate()` constraint check ordering is undocumented and unimplemented

**Spec ref**: §8.3 lines 230-240
**Location**: nowhere (the middleware does not exist)

Spec §8.3 mitigation #3: "The constraint check order MUST be documented explicitly in §2 of this spec before implementation begins (R2-005 fix): financial → temporal → operational → data_access → communication."

Verification: §2 of the spec STILL contains the placeholder `return "AUTO_APPROVED"  # placeholder — full implementation per GovernanceEngine API`. The R2-005 fix was a precondition to implementation. The constraint order is not documented. The middleware is not implemented. The §8.3 mitigation #1 ("MUST NOT return `AUTO_APPROVED` unconditionally in any production code path") is satisfied only by the absence of the middleware altogether — there is no production code, so it cannot violate the rule by existing.

**Severity**: CRITICAL — the false-security risk identified in §8.3 is not closed because the precondition (documenting order in §2) was not done.

---

### CRITICAL-06-03 — `SecretRotationHandle` and JWT secret rotation defenses missing

**Spec ref**: §8.4 lines 242-250
**Location**: nowhere

Spec §8.4 mitigations:

1. JWT secret rotation MUST use `kailash.trust.auth.SecretRotationHandle`.
2. Nexus's auth module MUST proxy every secret read through `kailash.trust.auth.get_jwt_secret(tenant_id)`.
3. A `jti` blocklist shared between Nexus and trust.
4. Observability: `JWTSecretRotated` events emitted with key fingerprints and time delta.

Verification:

```
$ grep -r "SecretRotationHandle\|get_jwt_secret\|jti.*blocklist\|JWTSecretRotated" \
    src/kailash/trust/ packages/kailash-nexus/
(no matches in any source file — only in the spec document itself)
```

None of the four mitigations exist. JWT secrets are still in `JWTConfig` instances and read by callers as instance attributes. There is no per-tenant secret resolution, no rotation primitive, no observability for rotations.

**Impact**: Multi-tenant JWT secrets are not isolated per tenant by a rotation primitive — TenantContext exists (good), but secret rotation across the trust/Nexus boundary is undefined.

**Severity**: CRITICAL — §8.4 entirely missing.

---

### CRITICAL-06-04 — SSO providers do NOT validate `state` through `SessionStore`

**Spec ref**: §8.5 lines 252-261
**Location**: `src/kailash/trust/auth/sso/{google,azure,github,apple}.py`, `src/kailash/trust/auth/sso/base.py`

Spec §8.5 mitigation #2: "SSO token exchange MUST validate the `state` parameter against a per-session nonce stored in `kailash.trust.session.SessionStore`. Validation happens in trust, not at the Nexus boundary."

Verification:

```
$ grep -n "SessionStore\|validate_and_consume" \
    src/kailash/trust/auth/sso/base.py \
    src/kailash/trust/auth/sso/google.py \
    src/kailash/trust/auth/sso/azure.py \
    src/kailash/trust/auth/sso/github.py \
    src/kailash/trust/auth/sso/apple.py
(no matches in any SSO provider)
```

`SessionStore` exists at `src/kailash/trust/auth/session.py` with `InMemorySessionStore`, but the SSO providers do not use it. The Google provider takes a `state` parameter and forwards it to the OAuth URL but never validates it on the callback. Validation is left to the caller — which means the spec §8.5 promise ("Validation happens in trust, not at the Nexus boundary") is not delivered. Each consumer must remember to validate.

**Impact**: A CSRF attack on the SSO callback path is not blocked at the trust layer.

**Severity**: CRITICAL — primary SSO security defense is consumer-opt-in instead of mandatory.

---

### CRITICAL-06-05 — `nexus.auth.*` paths do NOT emit `DeprecationWarning` and do NOT shim from `kailash.trust.auth`

**Spec ref**: §4 lines 173-186
**Location**: `packages/kailash-nexus/src/nexus/auth/__init__.py`

Spec §4 example:

```python
# packages/kailash-nexus/src/nexus/auth/__init__.py (v2.x shim)
import warnings
warnings.warn(
    "nexus.auth submodules are deprecated since v2.next. "
    "Use `from kailash.trust.auth import ...` instead.",
    DeprecationWarning, stacklevel=2,
)
from kailash.trust.auth.jwt import JWTAuth, JWTConfig
from kailash.trust.auth.rbac import RBACManager, Permission
from kailash.trust.auth.api_key import APIKeyAuth
```

Actual `nexus/auth/__init__.py` (lines 1-63):

- No `import warnings`, no `warnings.warn(..., DeprecationWarning, ...)`.
- Imports come from `nexus.auth.jwt`, `nexus.auth.rbac`, `nexus.auth.tenant`, etc. — NOT from `kailash.trust.auth.*`.
- Re-exports `NexusAuthPlugin` and middleware classes that still live in Nexus.

The migration from "Nexus auth" to "kailash.trust.auth" is partial: the JWTValidator and config did move (`nexus/auth/jwt.py` does import from `kailash.trust.auth.jwt`), but the `__init__.py` does not signal the deprecation, and no test asserts that importing the old paths emits a warning.

**Severity**: CRITICAL — migration deprecation contract not delivered. Consumers have no signal that the import path will move.

---

### HIGH-06-06 — `AuthMiddlewareChain` enforces a different ordering than the spec (Audit moved to outermost; chain is mutable)

**Spec ref**: §8.2 lines 220-228
**Location**: `src/kailash/trust/auth/chain.py` lines 34-168

Spec §8.2 mitigation #2 ("rate limit → JWT → RBAC → session → audit"):

```
canonical = rate_limit → JWT → RBAC → session → audit
```

This puts `audit` last so unauthenticated requests do not fill the audit store, and `rate_limit` first so a flood of garbage tokens is rejected before JWT verification burns CPU.

Actual `chain.py` lines 40-56:

```python
class MiddlewareSlot(str, Enum):
    AUDIT = "audit"  # 1 - outermost
    RATE_LIMIT = "rate_limit"  # 2
    JWT = "jwt"  # 3
    TENANT = "tenant"  # 4
    RBAC = "rbac"  # 5 - innermost
```

The implementation puts `audit` FIRST (outermost), not last. From the docstring (line 9): "Audit (captures everything)" — this is the OPPOSITE of the spec rationale. With audit outermost, every garbage request lands in the audit store BEFORE rate limiting drops it. This is the storage DoS surface §8.2 is meant to prevent.

Also missing:

- §8.2 mitigation #2: "MUST raise `MiddlewareOrderError`". Actual code raises `ValueError` (line 96), not a typed `MiddlewareOrderError`.
- §8.2 mitigation #4: "Chain is frozen at module load — no runtime modification". Actual chain has `add()` and `remove()` methods (lines 86-110) that allow runtime modification.
- The spec includes a `session` slot. The actual implementation has a `tenant` slot instead, with no `session` ordering position.

**Impact**:

- Audit-store DoS via unauthenticated traffic floods.
- Mutable chain at runtime can reorder middleware after startup.
- The wrong exception type breaks the spec's structured catch-block contract.

**Severity**: HIGH — ordering invariant inverted; mutability not enforced.

---

### HIGH-06-07 — `RedisBackend` is implemented but not exported from `kailash.trust.rate_limit`

**Spec ref**: §1 row "Rate limiting (Redis)" line 27
**Location**: `src/kailash/trust/rate_limit/__init__.py` (lines 23-35) vs `src/kailash/trust/rate_limit/backends/redis.py`

`RedisBackend` is implemented but `__init__.py` only exports `InMemoryBackend`. Consumers cannot do `from kailash.trust.rate_limit import RedisBackend` — they must reach into `backends.redis` directly. Spec §1 expects production rate limiting to be available through the canonical import.

**Severity**: HIGH — production backend is implemented but not surfaced.

---

### MEDIUM-06-08 — Migration order amendment from §8.1 was not honoured

**Spec ref**: §8.1 lines 208-218 ("Migration order in §3 is amended: step 1 is 'introduce TenantContext into kailash.trust.auth.' No Nexus code moves until tenant isolation exists in trust.")

`TenantContext` does exist at `src/kailash/trust/auth/context.py` and is imported by Nexus tenant middleware. The amendment WAS honoured for tenant context. But there is no integration test verifying that "a request arriving on tenant A's channel cannot access tenant B's JWT secret even if the code path references the global trust module" (mitigation #3). The defense exists by construction; the test that validates the construction is missing.

**Severity**: MEDIUM — defense in place, but unverified.

---

### MEDIUM-06-09 — No cross-language audit roundtrip test (SPEC-08 §7.5 cross-ref)

**Spec ref**: SPEC-08 §7.5 mitigation #3 (CI cross-language round-trip), referenced from SPEC-06 §6
**Location**: `tests/trust/integration/test_wire_format.py` exists but does not include a cross-SDK audit event roundtrip.

The audit event format is meant to be byte-identical between Python and Rust. No CI test reads a Rust-generated `AuditEvent` JSON and verifies Python parses it identically. Without this, format drift is silent until users hit it.

**Severity**: MEDIUM — wire format stability is unverified.

---

## SPEC-08: Core SDK Audit/Registry Consolidation

### CRITICAL-08-01 — Five of six "old audit modules" still hold their own implementations and are NOT consuming the canonical store

**Spec ref**: §2 lines 13-69 (5+ implementations to consolidate to 1)
**Locations**:

| Module                         | State                             | Imports canonical AuditEvent? |
| ------------------------------ | --------------------------------- | ----------------------------- |
| `trust/audit_store.py`         | ✅ canonical, well-implemented    | n/a (this IS the canonical)   |
| `trust/audit_service.py`       | ✅ imports canonical              | yes (line 22)                 |
| `trust/immutable_audit_log.py` | ❌ own implementation             | NO                            |
| `trust/pact/audit.py`          | ❌ own `AuditAnchor`/`AuditChain` | NO                            |
| `runtime/trust/audit.py`       | ❌ own `AuditEvent` (line 108)    | NO                            |
| `nodes/admin/audit_log.py`     | ❌ own `AuditEventType` enum      | NO                            |
| `nodes/security/audit_log.py`  | ❌ own implementation             | NO                            |

Spec §2 migration steps:

- Step 3: "`nodes/admin/audit_log.py` → consumes `AuditStore`, writes via `AuditEvent`". NOT done.
- Step 4: "`runtime/trust/audit.py` → consumes `AuditStore`, emits `AuditEvent`". NOT done.
- Step 5: "`trust/immutable_audit_log.py` → hash-chain verification moves into `AuditStore.verify_chain()`". NOT done.
- Step 6: "Delete redundant `AuditEvent` type variants". NOT done.
- Step 7: "Add backward-compat re-exports at old import paths". NOT done.

The canonical store is well-built, but consolidation is partial. There are now SIX audit implementations instead of one, with no shim layer telling consumers which is canonical.

**Impact**:

- Audit events emitted by `runtime/trust/audit.py` do NOT enter the canonical Merkle chain.
- Audit events emitted by `nodes/admin/audit_log.py` do NOT enter the canonical Merkle chain.
- Tampering detection (§7.1) only protects events that landed in the canonical store, which is a small fraction of total audit traffic.
- The "single source of truth" promise is broken.

**Severity**: CRITICAL — consolidation goal not achieved; the §7.1 integrity defense applies only to events that happen to be written through the canonical path.

---

### HIGH-08-02 — `AuditStoreProtocol` exists but the protocol contract diverges from the spec

**Spec ref**: §2 lines 27-43
**Location**: `src/kailash/trust/audit_store.py` lines 298-324

Spec contract:

```python
class AuditStore(Protocol):
    async def append(self, event: AuditEvent) -> str: ...
    async def query(self, filter: AuditFilter) -> list[AuditEvent]: ...
    async def verify_chain(self) -> ChainVerificationResult: ...
```

Actual:

```python
class AuditStoreProtocol(Protocol):
    async def append(self, event: AuditEvent) -> None: ...      # returns None, not str
    async def query(self, filter: AuditFilter) -> List[AuditEvent]: ...
    async def verify_chain(self) -> bool: ...                    # returns bool, not ChainVerificationResult
    async def close(self) -> None: ...                           # extra
```

Two divergences:

1. `append()` returns `None` instead of an event ID string. Callers cannot tell what the assigned `event_id` was after the append (they have to read it back from the event object they passed in — which works only because `AuditEvent` is constructed before the call, but breaks the spec's "store assigns and returns" contract).
2. `verify_chain()` returns `bool` instead of a structured `ChainVerificationResult`. Callers get true/false but no information about WHICH event broke the chain — defeating the §7.1 mitigation #3 ("Chain verification ... raises `AuditChainBrokenError` and triggers a trust-plane posture escalation") because there is no escalation hook and no break-point information.

`AuditChainBrokenError` does not exist in the codebase — `verify_chain()` returns False silently.

**Severity**: HIGH — protocol shape diverges; tamper detection has no escalation path.

---

### HIGH-08-03 — `CostEvent` deduplication and source-tracking entirely missing

**Spec ref**: §7.3 lines 165-174
**Location**: `src/kailash/trust/constraints/budget_tracker.py`

Spec §7.3 mitigations:

1. `BudgetTracker.record(event: CostEvent)` MUST deduplicate on `event.call_id`.
2. Every `CostEvent` carries a canonical source identifier: `source: Literal["monitored_agent", "trust_plane", "pact_engine", "direct"]`.
3. Migration code path MUST document which source each legacy tracker maps to.
4. Integration test verifies `BudgetTracker.total` equals the mock's cost, not 2x or 3x.

Verification:

```
$ grep -n "class CostEvent\|call_id\|dedup" src/kailash/trust/constraints/budget_tracker.py
(no matches)
```

`CostEvent` does not exist as a dataclass. `BudgetTracker` uses `record()`/`reserve()` semantics on raw integer microdollars without per-call-id deduplication. No `source` field. No double-counting integration test. The double-counting defense is completely absent.

**Impact**: When the wrapper stack composes (MonitoredAgent → L3GovernedAgent → Delegate.consumed_usd as in the current bug from CRITICAL-05-02), cost can be recorded twice — once by `_record_usage` on Delegate (line 390) and once by `_monitored._record_usage` (line 543). Read the actual code:

```python
# Update budget tracking with latest usage delta
self._record_usage(usage_dict)

# If MonitoredAgent is in the stack, record usage there too
if self._monitored is not None:
    self._monitored._record_usage({"usage": usage_dict})
```

These two writes are NOT deduped — both `Delegate._consumed_usd` and `MonitoredAgent`'s tracker increment for the same call. The double-counting bug §7.3 was meant to prevent IS PRESENT in the current Delegate facade.

**Severity**: HIGH — concrete double-counting bug present in the facade.

---

### HIGH-08-04 — `LocalRuntime` budget integration not implemented (§3 step 7)

**Spec ref**: §3 lines 86-92, §7.4 lines 176-185
**Location**: `src/kailash/runtime/local.py`

```
$ grep -i "budget\|BudgetTracker" src/kailash/runtime/local.py
(no matches)
```

`LocalRuntime.execute()` does not accept a `budget` parameter. There is no `BudgetPreCheckEvent`. No `BudgetExhaustedError` raised mid-run. No rate limiting on `LocalRuntime.execute()` calls per budget. §7.4 entire section is undelivered.

**Severity**: HIGH — runtime-level budget enforcement does not exist.

---

### HIGH-08-05 — Registry hardening (`AlreadyRegisteredError`, freeze hook, attestations) entirely missing

**Spec ref**: §7.2 lines 152-164
**Location**: nowhere

Spec §7.2 mitigations:

1. `Registry.register(key, value)` MUST validate against a registration schema (subclass chain for nodes, attestation for AuditStore backends, allowlist for LLMProvider).
2. Registry entries IMMUTABLE after registration. `register()` raises `AlreadyRegisteredError`.
3. Registry operations are audit-logged with the caller's module path.
4. "Registration freeze" hook runs at startup; further registrations require `Registry.unfreeze(secret_token)`.

Verification:

```
$ grep -rn "AlreadyRegisteredError\|Registry.unfreeze\|registration_freeze" src/kailash/
(no matches)
```

`AgentAlreadyRegisteredError` exists at `src/kailash/trust/registry/exceptions.py` but is specific to the agent registry, not the canonical Registry pattern. Other registries (NodeRegistry, ProviderRegistry, ToolRegistry, ServiceRegistry) do not have an `AlreadyRegisteredError`, do not freeze, do not validate caller modules, and do not have an unfreeze token mechanism.

The canonical registry pattern from §4 is documented but not enforced. The §7.2 hardening mitigations do not exist.

**Severity**: HIGH — registry poisoning has no defense at the canonical-pattern layer.

---

### MEDIUM-08-06 — `prev_hash` chain works in InMemoryAuditStore but `parent_anchor_id` semantics are unverified

**Spec ref**: §2 line 54 (`parent_anchor_id: Optional[str] = None  # causality chain`)
**Location**: `src/kailash/trust/audit_store.py` lines 199-201

The canonical `AuditEvent` includes `parent_anchor_id` but no test verifies that consumers actually use it for causality chains. The legacy `pact/audit.py` `AuditAnchor` and `runtime/trust/audit.py` `AuditEvent` both have their own causality models. After consolidation, only one causality model should remain. Currently three coexist.

**Severity**: MEDIUM — causality chains are non-uniform across audit emitters.

---

### MEDIUM-08-07 — `PostureStore` wiring into `TrustProject` not verified (§3 step 8)

**Spec ref**: §3 step 8 line 89
**Location**: `src/kailash/trust/plane/project.py`

`PostureStore` exists in `src/kailash/trust/posture/posture_store.py`, but no source file imports it from `plane/project.py`. Step 8 ("Wire PostureStore into TrustProject as default") is undelivered.

```
$ grep -n "PostureStore" src/kailash/trust/plane/project.py
(no matches)
```

**Severity**: MEDIUM — default posture store not wired.

---

### MEDIUM-08-08 — `ShadowEnforcer` env var integration not verified (§3 step 9)

**Spec ref**: §3 step 9 line 90 ("Enable `ShadowEnforcer` by env var (`TRUST_ENFORCEMENT_MODE=shadow`)")
**Location**: `src/kailash/trust/enforce/shadow.py` exists; env var dispatch unverified

```
$ grep -rn "TRUST_ENFORCEMENT_MODE" src/kailash/trust/
(no matches)
```

The env var name is not referenced anywhere in the trust module. `ShadowEnforcer` exists as a class but is never opted into by the documented env var.

**Severity**: MEDIUM — opt-in mechanism not present.

---

### LOW-08-09 — Genesis hash uses sentinel `"0" * 64` rather than a domain-separated value

**Spec ref**: §7.1 mitigation #2 (Merkle chain)
**Location**: `src/kailash/trust/audit_store.py` line 61 `_GENESIS_HASH = "0" * 64`

A genesis sentinel of `"0" * 64` is colliding-prone — any audit event whose actual SHA-256 happens to be all-zero (cosmically improbable but not zero) breaks the chain validator. Use a domain-separated genesis (e.g., `sha256(b"kailash:audit:v1:genesis").hexdigest()`).

**Severity**: LOW — defensive hardening; not a current bug.

---

### LOW-08-10 — `SqliteAuditStore.create_event` and `InMemoryAuditStore.create_event` are duplicated implementations

**Spec ref**: spirit of consolidation
**Location**: `src/kailash/trust/audit_store.py` lines 363-425 and 793-...

Both stores expose `create_event()` with identical signatures and identical semantics (compute prev_hash, hash, return frozen `AuditEvent`). Any future change must touch both copies. Extract a shared `_build_event()` helper.

**Severity**: LOW — maintenance smell.

---

## Compliance Matrix Summary

### SPEC-05 Delegate Engine

| §   | Item                                                            | Status                                                               |
| --- | --------------------------------------------------------------- | -------------------------------------------------------------------- |
| 2   | Constructor `signature=`                                        | MISSING (CRITICAL-05-01)                                             |
| 2   | Constructor `mcp_servers=`                                      | MISSING (CRITICAL-05-01)                                             |
| 2   | Constructor `inner_agent=`                                      | MISSING (CRITICAL-05-01)                                             |
| 2   | `temperature`, `max_tokens`, `api_key`, `base_url`              | MISSING                                                              |
| 2   | `core_agent` property                                           | MISSING (HIGH-05-08)                                                 |
| 2   | `streaming_agent` property                                      | MISSING (HIGH-05-08)                                                 |
| 3   | Wrapper order MonitoredAgent → L3GovernedAgent → StreamingAgent | REVERSED + StreamingAgent absent (CRITICAL-05-02)                    |
| 5   | `delegate/loop.py` MOVED                                        | NOT MOVED (CRITICAL-05-03 / HIGH-05-07)                              |
| 5   | `delegate/mcp.py` DELETED                                       | NOT DELETED (CRITICAL-05-03)                                         |
| 5   | `delegate/adapters/` DELETED                                    | NOT DELETED (CRITICAL-05-03)                                         |
| 5   | `delegate/tools/hydrator.py` MOVED                              | DUPLICATED (both exist)                                              |
| 5   | `delegate/events.py` MOVED                                      | ✅                                                                   |
| 5   | `delegate/hooks.py` MOVED                                       | NOT MOVED (HIGH-05-07)                                               |
| 7   | `test_delegate_with_signature`                                  | CANNOT EXIST (no `signature=`)                                       |
| 7   | `test_delegate_with_envelope`                                   | CANNOT EXIST in spec form (StreamingAgent absent from stack)         |
| 7   | `test_delegate_with_mcp_and_signature_and_budget`               | CANNOT EXIST (no `mcp_servers=`, no `signature=`)                    |
| 9.1 | `ConstructorIOError`                                            | MISSING (CRITICAL-05-04)                                             |
| 9.1 | Refuse sync `run()` from running loop                           | INVERTED — falls back to thread instead of refusing (CRITICAL-05-04) |
| 9.1 | Construction rate limiter                                       | MISSING (CRITICAL-05-04)                                             |
| 9.2 | `SecretRef` on `MCPServerConfig`                                | MISSING (CRITICAL-05-05)                                             |
| 9.2 | `scrub_secrets` log filter                                      | MISSING (CRITICAL-05-05)                                             |
| 9.2 | `inner_agent.get_security_context()` validation                 | MISSING (CRITICAL-05-05)                                             |
| 9.3 | Server-name prefixing                                           | MISSING (CRITICAL-05-06)                                             |
| 9.3 | `ToolRegistryCollisionError`                                    | MISSING (CRITICAL-05-06)                                             |
| 9.4 | `DeprecationWarning` on shim modules                            | MISSING (CRITICAL-05-03)                                             |
| 9.4 | Shim hash verification                                          | MISSING                                                              |
| 9.4 | `SuspiciousImportWarning`                                       | MISSING                                                              |

**SPEC-05 score**: ~3/27 items delivered (11%).

---

### SPEC-06 Nexus Auth Migration

| §   | Item                                            | Status                                                          |
| --- | ----------------------------------------------- | --------------------------------------------------------------- |
| 1   | JWT extracted to `kailash.trust.auth.jwt`       | ✅                                                              |
| 1   | RBAC extracted to `kailash.trust.auth.rbac`     | ✅                                                              |
| 1   | API key extracted                               | partial — file exists, not audited deeply                       |
| 1   | SSO providers extracted                         | ✅ (Google, Azure, GitHub, Apple all present)                   |
| 1   | Rate limit Memory extracted                     | ✅                                                              |
| 1   | Rate limit Redis extracted                      | ✅ implemented, NOT exported (HIGH-06-07)                       |
| 1   | Audit logging via canonical store               | partial — see SPEC-08                                           |
| 1   | EATP headers extracted                          | not audited                                                     |
| 1   | Trust middleware extracted                      | not audited                                                     |
| 1   | Session trust extracted                         | partial — `SessionStore` exists but unused (CRITICAL-06-04)     |
| 2   | `PACTMiddleware` class                          | DOES NOT EXIST (CRITICAL-06-01)                                 |
| 3   | Phase 5a auth extraction                        | partial                                                         |
| 3   | Phase 5b Nexus consumes trust                   | partial — `nexus/auth/__init__.py` not shimmed (CRITICAL-06-05) |
| 3   | Phase 5c PACT integration                       | UNDELIVERED (CRITICAL-06-01)                                    |
| 4   | Backward compat shims                           | MISSING (CRITICAL-06-05)                                        |
| 5   | New PACT integration test                       | MISSING                                                         |
| 5   | New `SqliteAuditStore` persistence test         | ✅ exists                                                       |
| 8.1 | `TenantContext`                                 | ✅                                                              |
| 8.1 | Multi-tenant secret isolation test              | MISSING (MEDIUM-06-08)                                          |
| 8.2 | `AuthMiddlewareChain` ordering matches spec     | INVERTED (HIGH-06-06)                                           |
| 8.2 | `MiddlewareOrderError` raised                   | uses `ValueError` instead (HIGH-06-06)                          |
| 8.2 | Chain frozen at module load                     | MUTABLE at runtime (HIGH-06-06)                                 |
| 8.3 | `_evaluate()` constraint order documented in §2 | NOT DOCUMENTED (CRITICAL-06-02)                                 |
| 8.3 | `_evaluate()` not returning AUTO_APPROVED       | trivially true (no impl)                                        |
| 8.4 | `SecretRotationHandle`                          | MISSING (CRITICAL-06-03)                                        |
| 8.4 | `get_jwt_secret(tenant_id)`                     | MISSING (CRITICAL-06-03)                                        |
| 8.4 | `jti` blocklist                                 | MISSING (CRITICAL-06-03)                                        |
| 8.4 | `JWTSecretRotated` audit event                  | MISSING (CRITICAL-06-03)                                        |
| 8.5 | SSO state validated through `SessionStore`      | NOT WIRED (CRITICAL-06-04)                                      |

**SPEC-06 score**: ~9/29 items delivered (~31%).

---

### SPEC-08 Core SDK Audit Consolidation

| §   | Item                                                    | Status                                                      |
| --- | ------------------------------------------------------- | ----------------------------------------------------------- |
| 2   | Canonical `AuditEvent` dataclass                        | ✅ (with frozen, to_dict, from_dict, hash chain)            |
| 2   | `AuditStoreProtocol`                                    | ✅ exists, contract slightly diverges (HIGH-08-02)          |
| 2   | `InMemoryAuditStore`                                    | ✅                                                          |
| 2   | `SqliteAuditStore`                                      | ✅                                                          |
| 2   | `AuditFilter`                                           | ✅                                                          |
| 2   | Migration step 3: nodes/admin/audit_log → canonical     | NOT DONE (CRITICAL-08-01)                                   |
| 2   | Migration step 4: runtime/trust/audit → canonical       | NOT DONE (CRITICAL-08-01)                                   |
| 2   | Migration step 5: ImmutableAuditLog merged              | NOT DONE (CRITICAL-08-01)                                   |
| 2   | Migration step 6: delete redundant AuditEvent variants  | NOT DONE (CRITICAL-08-01)                                   |
| 2   | Migration step 7: backward-compat re-exports            | NOT DONE (CRITICAL-08-01)                                   |
| 3   | Merge `AgentBudget` into `BudgetTracker`                | partial                                                     |
| 3   | Wire `BudgetTracker` into `LocalRuntime`                | NOT DONE (HIGH-08-04)                                       |
| 3   | Wire `PostureStore` into `TrustProject`                 | NOT DONE (MEDIUM-08-07)                                     |
| 3   | `ShadowEnforcer` env var                                | NOT DONE (MEDIUM-08-08)                                     |
| 4   | Registry pattern documented                             | spec-only                                                   |
| 7.1 | Append-only INSERT-only schema                          | ✅ (SqliteAuditStore)                                       |
| 7.1 | Merkle hash chain                                       | ✅                                                          |
| 7.1 | `verify_chain()` returns structured result + escalation | RETURNS BOOL — no escalation (HIGH-08-02)                   |
| 7.1 | Migration rehashing existing entries                    | NOT DONE (because steps 3-5 not done)                       |
| 7.1 | Tamper test                                             | ✅ (test_in_memory_audit_store.py:100, 231)                 |
| 7.2 | Registry value validation schema                        | MISSING (HIGH-08-05)                                        |
| 7.2 | Registry entries IMMUTABLE                              | MISSING (HIGH-08-05)                                        |
| 7.2 | `AlreadyRegisteredError`                                | exists only for AgentRegistry (HIGH-08-05)                  |
| 7.2 | Registration freeze hook                                | MISSING (HIGH-08-05)                                        |
| 7.3 | `CostEvent.call_id` deduplication                       | MISSING + ACTUAL DOUBLE-COUNT BUG (HIGH-08-03)              |
| 7.3 | `CostEvent.source` field                                | MISSING (HIGH-08-03)                                        |
| 7.3 | Double-count integration test                           | MISSING                                                     |
| 7.4 | `LocalRuntime.execute(budget=...)`                      | MISSING (HIGH-08-04)                                        |
| 7.4 | `BudgetPreCheckEvent`                                   | MISSING                                                     |
| 7.4 | `BudgetExhaustedError` rate limiting                    | MISSING                                                     |
| 7.5 | Cross-language round-trip CI test                       | MISSING (MEDIUM-06-09)                                      |
| 7.5 | `AuditEvent.to_dict()` canonical JSON form              | partial — `to_dict()` exists but no canonical-form contract |

**SPEC-08 score**: ~10/30 items delivered (~33%).

---

## Risk Register

| Risk                                                          | Likelihood | Impact   | Mitigation                                                                               |
| ------------------------------------------------------------- | ---------- | -------- | ---------------------------------------------------------------------------------------- |
| Delegate budget double-counted (CRITICAL-05-02 + HIGH-08-03)  | High       | High     | Implement `CostEvent.call_id` dedup; fix wrapper order; remove duplicate `_record_usage` |
| PACT bypass at Nexus boundary (CRITICAL-06-01)                | High       | Critical | Build `nexus/middleware/governance.py`; document constraint order in §2                  |
| Audit storage DoS via unauthenticated traffic (HIGH-06-06)    | High       | High     | Reverse audit slot to innermost; add rate-limit slot in front                            |
| SSO CSRF via unvalidated state (CRITICAL-06-04)               | High       | Critical | Wire `SessionStore.validate_and_consume()` into all SSO providers                        |
| Tampering invisible to consolidated chain (CRITICAL-08-01)    | Medium     | Critical | Migrate runtime/admin/immutable audit modules to canonical store                         |
| Shim impersonation attack (CRITICAL-05-03 + 06-05)            | Medium     | High     | Add DeprecationWarning + hash check + removal date to all old paths                      |
| JWT secret rotation drift across trust/Nexus (CRITICAL-06-03) | Medium     | High     | Implement `SecretRotationHandle` and `get_jwt_secret(tenant_id)`                         |
| Registry poisoning at scale (HIGH-08-05)                      | Medium     | High     | Add registration schema + freeze hook to canonical Registry pattern                      |
| Constructor IO from inner_agent (CRITICAL-05-05)              | Medium     | Medium   | Add `ConstructorIOError`, validate `inner_agent.get_security_context()`                  |
| Cross-language audit format drift (MEDIUM-06-09)              | Low        | High     | Add CI roundtrip test                                                                    |

---

## Cross-Reference Audit

The prior red team report `04-validate/02-implementation-redteam.md` claims:

| Claim                                         | Reality                                                         |
| --------------------------------------------- | --------------------------------------------------------------- |
| "100% spec coverage (94/94)"                  | SPEC-05 ~11%, SPEC-06 ~31%, SPEC-08 ~33%                        |
| "Phase 4 delegate composition: 3/3 checks"    | Stack order is reversed; StreamingAgent not in stack            |
| "Phase 5: 12/12 checks pass"                  | PACTMiddleware undelivered; 5/6 audit modules not migrated      |
| "TenantContext isolates multi-tenant secrets" | TenantContext exists but no integration test verifies isolation |
| "JWT tokens via kailash.trust.auth.jwt"       | True for `nexus/auth/jwt.py`; not via deprecation shim          |
| "Posture ceiling enforced before LLM cost"    | Backwards in current `delegate.py` wrapper order                |
| "no security findings"                        | This audit identifies 7 critical security findings              |

The discrepancy is large. The most likely cause is that the prior verification used a `convergence-verify.py` script that checked file existence (e.g., "does `kailash.trust.audit_store.AuditEvent` exist?") rather than spec-clause compliance (e.g., "is every emitter in the codebase consuming the canonical AuditEvent?"). Existence checks pass; consolidation does not.

---

## Implementation Roadmap (autonomous execution cycles)

### Cycle 1 — Critical security gaps

1. SPEC-06 §2: Build `nexus/middleware/governance.py` with documented constraint order (financial → temporal → operational → data_access → communication).
2. SPEC-06 §8.5: Wire `SessionStore.validate_and_consume()` into all four SSO provider callback paths.
3. SPEC-06 §8.2: Reverse `AuthMiddlewareChain` ordering (audit innermost, rate_limit outermost). Rename exception to `MiddlewareOrderError`. Freeze chain at module load.
4. SPEC-05 §9.4: Add `DeprecationWarning` to `delegate/{loop,mcp,adapters,tools/hydrator}.py` with stable message format.
5. SPEC-05 §3: Reverse wrapper stack order to MonitoredAgent → L3GovernedAgent → StreamingAgent.

### Cycle 2 — Contract completion

6. SPEC-05 §2: Add `signature=`, `mcp_servers=`, `inner_agent=`, `temperature=`, `max_tokens=`, `api_key=`, `base_url=` to Delegate constructor.
7. SPEC-05 §2: Add `core_agent` and `streaming_agent` properties.
8. SPEC-05 §3: Wire `StreamingAgent` as outermost wrapper. Delete `_LoopAgent`. Stream through wrappers, not around them.
9. SPEC-08 §7.3: Define `CostEvent` with `call_id` and `source` fields. Migrate `BudgetTracker.record()` to take `CostEvent`. Add dedup. Remove duplicate `_record_usage` in Delegate.
10. SPEC-08 §2: Migrate `runtime/trust/audit.py`, `nodes/admin/audit_log.py`, `nodes/security/audit_log.py`, `trust/immutable_audit_log.py`, `trust/pact/audit.py` to canonical store. Add backward-compat re-exports.

### Cycle 3 — Hardening + observability

11. SPEC-06 §8.4: Build `SecretRotationHandle`, `get_jwt_secret(tenant_id)`, `jti` blocklist, `JWTSecretRotated` audit emission.
12. SPEC-05 §9.1: Add `ConstructorIOError`; refuse sync `run()` from running loops with explicit error pointing at `run_async()`; add construction rate limiter.
13. SPEC-05 §9.2: Add `SecretRef` to `MCPServerConfig`; add `scrub_secrets` log filter.
14. SPEC-05 §9.3: Add server-name prefixing and `ToolRegistryCollisionError`.
15. SPEC-08 §7.2: Add registration schema, immutability, freeze hook to canonical Registry pattern.
16. SPEC-08 §7.4: Wire `BudgetTracker` into `LocalRuntime` with `BudgetPreCheckEvent`.
17. SPEC-08 §3: Wire `PostureStore` into `TrustProject` default; add `TRUST_ENFORCEMENT_MODE=shadow` env var.

### Cycle 4 — Tests and verification

18. SPEC-05 §7: New tests for `Delegate(signature=...)`, `Delegate(envelope=..., signature=...)`, `Delegate(mcp_servers=..., signature=..., budget_usd=...)`. Tamper-impersonation test.
19. SPEC-06 §5: PACT-Nexus integration test; SSO CSRF rejection test.
20. SPEC-08 §7.5: Cross-language audit roundtrip CI test.
21. Multi-tenant secret isolation integration test (SPEC-06 §8.1 mitigation #3).
22. Double-count integration test (SPEC-08 §7.3 mitigation #4).

---

## Success Criteria

- [ ] All seven CRITICAL findings resolved with paired tests
- [ ] All eight HIGH findings resolved with paired tests
- [ ] `convergence-verify.py` rewritten to check spec-clause compliance (not file existence). Each spec section has at least one assertion bound to source-line range.
- [ ] Cross-language audit roundtrip test passes between Python and Rust
- [ ] No raw `asyncio.run()` calls in any wrapper or facade `__init__`/`run` path
- [ ] All `nexus.auth.*` imports emit `DeprecationWarning` with hash verification
- [ ] All Delegate parallel modules emit `DeprecationWarning` with hash verification
- [ ] `BudgetTracker.total` integration test verifies single-count under composed wrapper stack
- [ ] PACTMiddleware blocks at least one mock-`BLOCKED` envelope verdict in integration test
- [ ] All five constraint dimensions (Financial, Temporal, Operational, DataAccess, Communication) tested in `_evaluate()` with documented order

---

## Notes

- The canonical `AuditEvent` and `SqliteAuditStore` implementations in `src/kailash/trust/audit_store.py` are HIGH QUALITY work. The defects are in the ecosystem of consumers that did not migrate, not in the canonical store itself.
- The `AgentPosture` enum and `PostureStore` are correctly placed at `src/kailash/trust/posture/`. The audit task's expected level names ("PSEUDO/TOOL/SUPERVISED/AUTONOMOUS/DELEGATED") differ from the actual EATP-aligned levels ("PSEUDO_AGENT/SUPERVISED/SHARED_PLANNING/CONTINUOUS_INSIGHT/DELEGATED") — the implementation matches the spec, the audit task's expected names are stale.
- `TenantContext` extraction is well-done and matches §8.1 well.
- The `AuthMiddlewareChain` defect (§8.2 inverted ordering) is the highest-leverage fix in the report — one file change reverses an active DoS surface.
