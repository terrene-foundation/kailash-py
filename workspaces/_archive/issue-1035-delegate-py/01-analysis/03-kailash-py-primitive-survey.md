# kailash-py Primitive Survey for Delegate Composition Surface (Issue #1035)

**Date:** 2026-05-21
**Scope:** kailash-py CWD only (per `rules/repo-scope-discipline.md` — no cross-repo reads)
**Goal:** Enumerate primitives the Delegate composition surface (`Connector × Signature × Envelope × Executor`, per `#1035`) can REUSE vs. those that need fresh implementation. Drive the layout decision (`src/kailash/delegate/` vs `packages/kailash-delegate/`).
**Frame:** The Delegate Spec v0 (issue #1035 body / `/Users/esperie/repos/dev/unicorn-focus/drafts/02-delegate-spec-v0-outline.md` per `01-external-spec-extraction.md`) describes a composition primitive whose call site looks like `Delegate.compose(connector=..., signature=..., envelope=..., executor=..., pact_engine=engine)`. The acceptance bar is "py-emitted EATP chain verifies under the rs verifier."

---

## TL;DR (one-paragraph)

kailash-py has **deep, production-grade implementations** of every primitive the Delegate composition surface needs to compose with — except (a) the Delegate composition primitive itself, (b) a `kailash.delegate.Connector` ABC, and (c) the Delegate-specific conformance vector set. PACT engine, EATP audit chain (with cross-SDK byte-canonical JSON), `ConstraintEnvelope` (with monotonic `intersect()`), tenant scoping, and a conformance-vector pattern that is already cross-SDK-byte-equality-validated against kailash-rs all exist in shippable form. The kaizen-agents `Delegate` is a separately-named class (LLM execution facade) that does NOT occupy the issue #1035 composition surface; near-miss only.

---

## 1. PACT engine — composition target

**Path:** `/Users/esperie/repos/loom/kailash-py/packages/kailash-pact/src/pact/engine.py`
**Class:** `PactEngine` (file line 126; 1413 LOC total)
**Public constructor signature** (`engine.py:151-162`):

```python
class PactEngine:
    def __init__(
        self,
        org: str | Path | dict[str, Any],
        *,
        model: str | None = None,
        budget_usd: float | None = None,
        clearance: str = "restricted",
        store_backend: str = "memory",
        cost_model: Any | None = None,
        on_held: HeldActionCallback | None = None,
        enforcement_mode: EnforcementMode = EnforcementMode.ENFORCE,
    ) -> None: ...
```

**What the Delegate's `pact_engine=engine` parameter gets:**

- `engine.submit(objective, role, context)` (`engine.py:212`) — async governed execution entry point; lock-protected check-remaining → execute → record-cost (`engine.py:239`).
- `engine.governance` property — read-only `_ReadOnlyGovernanceWrapper` (`engine.py:1366-1391`) per `rules/pact-governance.md` MUST Rule 1 (agents NEVER receive raw `GovernanceEngine`).
- `engine.costs` property — `CostTracker` (`pact/costs.py`).
- `engine.events` property — `EventBus(maxlen=10000)` (`engine.py:191`).
- Default `GovernanceCallback` (`engine.py:85-122`) — per-node verification: HELD → `GovernanceHeldError`, BLOCKED → `PactError`, AUTO_APPROVED → proceed.

**Lifecycle a Delegate would need:** construct once → wire as `pact_engine=` constructor arg on `Delegate.compose(...)` → Delegate calls `engine.governance.verify_action(role_address, action, context)` BEFORE every Connector pull; on AUTO_APPROVED, execute; on HELD/BLOCKED, surface verdict + halt.

**Reuse verdict:** **REUSE AS-IS.** The Delegate's contract — "every execution step authorized by PACT" — is exactly what `PactEngine.submit()` already enforces. The Delegate wraps a lower-level loop and calls `engine.governance.verify_action()` per step, OR delegates the loop itself to `engine.submit()` if the work is single-objective.

---

## 2. EATP audit-chain primitive — cross-SDK contract owner

**Wire format owner:** `/Users/esperie/repos/loom/kailash-py/src/kailash/trust/chain.py` (1443 LOC)

**Core dataclasses** (per `chain.py` grep):

| Class                     | Line | Has `to_dict` / `from_dict` |
| ------------------------- | ---- | --------------------------- |
| `GenesisRecord`           | 121  | yes (`@dataclass`)          |
| `DelegationRecord`        | 222  | line 325 / 359              |
| `AuditAnchor`             | 509  | line 575 / 605              |
| `ChainConstraintEnvelope` | 442  | yes                         |
| `CapabilityAttestation`   | 419  | yes                         |
| `TrustLineageChain`       | 672  | line 997 / 1053             |
| `LinkedHashChain`         | 1122 | line 1377 / 1398            |

`TrustLineageChain.hash(previous_hash=None)` (`chain.py:701-755`) — produces the cross-SDK hash via `kailash.trust.signing.crypto.hash_trust_chain_state` (unsalted backward-compatible mode) OR `hash_trust_chain_state_salted` (linked-hash mode). Five canonical CARE constraint dimensions enumerated at `chain.py:33-35` (`financial, operational, temporal, data_access, communication`) — matches kailash-rs and `pact.config.ConstraintDimension`.

**Canonical JSON encoder** (cross-SDK byte-equality):

- `/Users/esperie/repos/loom/kailash-py/src/kailash/trust/_json.py:65` — `canonical_json_loads(text)` with `DuplicateKeyError`.
- `/Users/esperie/repos/loom/kailash-py/src/kailash/trust/_json.py:99` — `canonical_json_dumps(obj)` deterministic sorted-key encoder.
- Also re-implemented for cross-SDK shape parity in `/Users/esperie/repos/loom/kailash-py/packages/kailash-pact/src/pact/conformance/vectors.py:80` (`canonical_json_dumps`) with field-ordered separators `(",", ":")` matching `serde_json::to_string` exactly, insertion-order keys, `ensure_ascii=False`. The module's docstring at `vectors.py:21-37` is explicit: "The canonical JSON shape is a CROSS-SDK contract. It mirrors the Rust serde output."

**Sync EATP emission protocol:** `/Users/esperie/repos/loom/kailash-py/src/kailash/trust/pact/eatp_emitter.py:28` — `PactEatpEmitter(Protocol)` with three methods (`emit_genesis`, `emit_delegation`, `emit_capability`) + `InMemoryPactEmitter` ref implementation (`eatp_emitter.py:53`). GovernanceEngine drives these per-event.

**Already byte-canonical-verified against kailash-rs:** The PACT N4 / N5 conformance runner (`packages/kailash-pact/src/pact/conformance/runner.py:1-44`) explicitly states it is "the Python-side analog of the Rust `conformance_vectors.rs::all_vectors_load_and_pass` test" and asserts `event.canonical_json() == expected.canonical_json` byte-for-byte. The cross-SDK contract source-of-truth file cited at `vectors.py:36-37` is `kailash-rs/crates/kailash-pact/tests/conformance_vectors.rs`.

**Reuse verdict:** **REUSE AS-IS.** The acceptance bar "py-emitted chain verifies under rs verifier" is already passing for the N4/N5 contract surface. Delegate's emitted EATP records (Genesis + Delegation + Capability + Audit) MUST flow through `chain.py` dataclasses and `_json.py::canonical_json_dumps` — NOT a fresh implementation. The conformance-vector pattern (see §8) is the structural defense that keeps the byte-equality contract green as the Delegate emits its own records.

---

## 3. Connector base / ABC — fresh authoring, but pattern templates exist

**No `class.*Connector` base or ABC exists under `src/kailash/`.** The `nodes/api/` directory contains concrete protocol clients (`auth.py`, `http.py`, `rest.py`, `graphql.py`, `monitoring.py`, `rate_limiting.py`, `security.py`) but no abstract Connector base. Verified by `grep -rln "class.*Connector" /Users/esperie/repos/loom/kailash-py/src/kailash/` → zero hits.

**Closest existing pattern — `StreamingChatAdapter`** at `/Users/esperie/repos/loom/kailash-py/packages/kaizen-agents/src/kaizen_agents/delegate/adapters/protocol.py:60`:

```python
@runtime_checkable
class StreamingChatAdapter(Protocol):
    """Protocol for LLM provider adapters."""
    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        ...
    ) -> AsyncGenerator[StreamEvent, None]: ...
```

Also: `RetryStrategy(ABC)` at `/packages/kailash-mcp/src/kailash_mcp/errors.py:272` (1 abstract method); `MCPServerBase(ABC)` at `/packages/kailash-mcp/src/kailash_mcp/server.py:100`; `ClientStore(ABC)` / `TokenStore(ABC)` at `/packages/kailash-mcp/src/kailash_mcp/auth/oauth.py:340, 400`. These are framework-internal ABCs, not general-purpose connector bases.

**Recommendation:** Author a fresh `kailash.delegate.Connector` ABC that mirrors the rs trait (pull / normalize / capabilities). Use the `typing.Protocol` + `@runtime_checkable` pattern from `StreamingChatAdapter` for the duck-typed surface AND export an `abc.ABC` subclass with `@abstractmethod` decorators for the explicit-inheritance surface (per `rules/testing.md` § "Protocol-Satisfying Deterministic Adapters" exception — Protocol satisfaction is NOT a mock; canonical for test deterministic-adapters).

**Reuse verdict:** **FRESH AUTHORING.** Pattern templates exist in `StreamingChatAdapter` (Protocol form) and `MCPServerBase` (ABC form). The Delegate Connector ABC should follow Protocol form for duck-typing flexibility + ABC subclass for default behavior inheritance.

---

## 4. Signature / Executor types — application-supplied, but overlap exists

**Signature primitive (Kaizen-owned):** `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/signatures/core.py`

- `class InputField` (line 47) — field declaration
- `class OutputField` (line 88) — field declaration
- `class SignatureMeta(type)` (line 118) — metaclass
- `class Signature(metaclass=SignatureMeta)` (line 249) — base class
- `class SignatureParser` (line 642), `SignatureValidator` (line 863), `SignatureCompiler` (line 1015), `SignatureTemplate` (line 1735), `SignatureOptimizer` (line 1814)

**Signature pattern example** (`kaizen/signatures/core.py`):

```python
class TriageSignature(Signature):
    ticket: str = InputField(description="Support ticket content")
    priority: str = OutputField(description="urgent, high, normal, low")
```

**Executor:** No single canonical `Executor` class exists. Closest surfaces: `LocalRuntime` / `AsyncLocalRuntime` (`src/kailash/runtime/local.py`), kaizen-agents `AgentLoop` (`delegate/loop.py`), and the application's own ReAct/multi-cycle loops. The issue #1035 spec text says Signature/Executor are **application-supplied** — the Delegate surface accepts them as opaque types and composes them.

**Recommendation:** Use `typing.Protocol` (NOT inheritance) for `kailash.delegate.Signature` and `kailash.delegate.Executor` so application-supplied types can pass without being forced to import a Delegate-specific base. The Kaizen `Signature` and any other application-supplied callable that matches the Protocol shape can be passed unchanged.

**Reuse verdict:** **PROTOCOL ACCEPTANCE, NO FRESH IMPL.** Kaizen's `Signature` exists and is fully featured (~2000 LOC of validation, compilation, optimization). Define Delegate's Signature/Executor as Protocols and Kaizen's Signature satisfies the surface by structural typing.

---

## 5. ConstraintEnvelope — REUSE the canonical SPEC-07 type

**Path:** `/Users/esperie/repos/loom/kailash-py/src/kailash/trust/envelope.py` (1645 LOC)
**Status:** Already canonical, already cross-SDK-aligned, already monotonic-tightening-enforced.

**SPEC-07 ConstraintEnvelope** (`envelope.py:1-26`):

> "Canonical ConstraintEnvelope — SINGLE source of truth for constraint envelopes. SPEC-07: ConstraintEnvelope Unification. This module defines the canonical `ConstraintEnvelope` type that replaces the three previously scattered implementations: 1. `kailash.trust.chain.ConstraintEnvelope` — EATP lineage chain (generic bag) 2. `kailash.trust.plane.models.ConstraintEnvelope` — TrustPlane 5-dimension type 3. `kailash.trust.pact.config.ConstraintEnvelopeConfig` — PACT governance config. The canonical type is a frozen dataclass superset with: Five constraint dimensions (financial, operational, temporal, data_access, communication), Gradient thresholds for verification gradient classification, Posture ceiling per ADR-010, Monotonic tightening via `intersect()`, Deterministic canonical JSON for cross-SDK compatibility, HMAC-SHA256 signing via `SecretRef`, NaN/Inf protection on all numeric fields."

**Key Delegate-relevant surfaces:**

- `ConstraintEnvelope.intersect(other)` (`envelope.py:838-865`) — **the tighten-only operator the issue body needs.** Commutative + associative. Per-dimension intersection: numeric `min()`, allow-lists set-intersection, block-lists set-union, booleans OR.
- `ConstraintEnvelope.is_tighter_than(other)` (`envelope.py:867`) — predicate for verifying "child envelope is ≤ parent".
- `ConstraintEnvelope.to_canonical_json()` (`envelope.py:1029`) — cross-SDK byte-canonical encoder.
- `ConstraintEnvelope.envelope_hash()` (`envelope.py:806`) — SHA-256 of constraint content; tamper detection.
- `sign_envelope(envelope, secret_ref)` (`envelope.py:1424`) / `verify_envelope(...)` (`envelope.py:1489`) — HMAC-SHA256 round-trip.
- `from_plane_envelope(...)` / `to_plane_envelope(...)` — adapters for legacy plane callers.
- Frozen dataclass — `rules/pact-governance.md` MUST Rule 6 and `rules/trust-plane-security.md` MUST Rule 4 enforced.

**Already imported by kaizen-agents Delegate** (`packages/kaizen-agents/src/kaizen_agents/delegate/delegate.py:63`):

```python
from kailash.trust.envelope import ConstraintEnvelope
```

The existing kaizen-agents `Delegate(... envelope: ConstraintEnvelope | None = None ...)` (`delegate.py:359`) already passes the canonical type to its `L3GovernedAgent` wrapper.

**Reuse verdict:** **REUSE AS-IS.** The Delegate composition surface MUST import `from kailash.trust.envelope import ConstraintEnvelope`. The rs type-state "tighten-only never widen" maps to py's `intersect()` + `is_tighter_than()` predicate guard. No fresh frozen-dataclass needed.

---

## 6. Tenant isolation primitive — exists in dataflow/tenancy/, no general-purpose `TenantScopedCascade`

**Closest match:** `/Users/esperie/repos/loom/kailash-py/packages/kailash-dataflow/src/dataflow/tenancy/`

```
tenancy/
  __init__.py
  exceptions.py
  interceptor.py
  security.py
```

This is DataFlow-coupled tenant isolation (query interceptor + tenant-aware security checks). It is NOT a free-standing primitive on the Trust Plane or PACT surface.

**Other tenant references:**

- `grep -rln "TenantContext\|tenant_id"` across `src/kailash/trust/` and `packages/kailash-pact/src/` shows tenant_id flows through audit records (`audit_store.py`), JWT auth context (`trust/auth/jwt.py`, `trust/auth/context.py`, `trust/auth/models.py`), and AWS SSO (`trust/auth/sso/azure.py`).
- PACT engine has tenant_id touch points in `pact/engine.py` and `pact/ml/__init__.py`.

**No `class TenantScopedCascade` analog exists** in the trust plane or PACT package. The rs side's `TenantScopedCascade` (per #1035 issue body context) does not have a 1:1 py equivalent.

**Recommendation:** The Delegate's tenant isolation should be enforced at the PACT envelope layer — `ConstraintEnvelope` already carries `data_access` constraints that include tenant scope (per `envelope.py` `DataAccessConstraint`). For the cascade-style "every connector call carries tenant scope down to the audit record" pattern, author a **fresh thin wrapper** `kailash.delegate.TenantScope(tenant_id, envelope)` that (a) injects `tenant_id` into the audit context dict before every `pact_engine.governance.verify_action()` call, and (b) emits `tenant_id` in every EATP record per `chain.py` dataclass field. This is a ~30 LOC composition primitive, not a fresh subsystem.

**Reuse verdict:** **MOSTLY FRESH AUTHORING (~30 LOC composition wrapper).** Underlying tenant tracking exists in DataFlow + audit_store + JWT auth context, but a Trust-Plane-level `TenantScopedCascade` does not.

---

## 7. Lifecycle state machine pattern — workflow has them, Delegate can mirror

**State-machine patterns in kailash-py** (from `grep -l "class.*State\|StateMachine"` across `src/kailash/workflow/`):

- `workflow/builder.py`
- `workflow/cycle_state.py` — cycle execution state
- `workflow/cyclic_runner.py` — cycle runner with state transitions
- `workflow/edge_infrastructure.py`
- `workflow/state.py` — workflow state base
- `workflow/runner.py` — main runner
- `nodes/transaction/saga_state_storage.py` — saga state persistence (canonical typed-state pattern)
- `core/resilience/health_monitor.py` — health state transitions
- `nodes/alerts/base.py` — alert lifecycle

**Most relevant pattern: `kailash.trust.plane.delegation::DelegateStatus`** at `src/kailash/trust/plane/delegation.py:65`:

```python
class DelegateStatus(Enum):
    ...  # typed enum-state transitions
```

And the kaizen-agents `Delegate` (`packages/kaizen-agents/src/kaizen_agents/delegate/delegate.py:270`) uses a wrapper-stack composition (AgentLoop → L3GovernedAgent → MonitoredAgent) rather than a state machine.

**EATP-side state machine:** `rules/eatp.md` "Monotonic escalation only: AUTO_APPROVED → FLAGGED → HELD → BLOCKED (never downgrade)". Same shape applies to Delegate execution states.

**Recommendation:** Use `enum.Enum` (str-backed per `rules/eatp.md` SDK convention) for Delegate lifecycle states: `INIT → AUTHORIZED → EXECUTING → COMPLETED | BLOCKED | HELD | FAILED`. Mirror the monotonic-escalation rule. No new state-machine framework needed — Python's enum + a tiny transition guard table is the canonical pattern across kailash.

**Reuse verdict:** **PATTERN REUSE.** No need to import a state-machine framework; enum + transition guard inside Delegate's loop matches kailash-wide convention.

---

## 8. Conformance-test infrastructure — PACT N4/N5 is the canonical template

**Direct template:** `/Users/esperie/repos/loom/kailash-py/packages/kailash-pact/src/pact/conformance/`

```
conformance/
  __init__.py
  cli.py          # CLI runner
  runner.py       # ConformanceRunner, RunnerReport, VectorOutcome, VectorStatus
  vectors.py      # ConformanceVector schema + parse + canonical_json_dumps
```

**Why this is exactly the template Delegate needs:**

1. **Cross-SDK byte-equality contract** — `runner.py:11-13` "It is deliberately framework-agnostic: it does NOT touch `GovernanceEngine` or any production governance hot path. Its sole responsibility is the cross-SDK byte-equality contract."
2. **JSON vector format** — vectors live as `*.json` files; `load_vectors_from_dir(path)` (`vectors.py:64`) discovers + parses + sorts by `id`.
3. **Failure mode is fail-LOUD** — malformed vector raises `ConformanceVectorError`; per-vector mismatch records expected + actual + SHA-256 fingerprints for cross-SDK diff (`runner.py:30-44`).
4. **Already implements `cross-sdk-inspection.md` MUST Rule 4 + 4a** — pins byte vectors empirically derived from kailash-rs serde output; vendored canonical JSON files.

**Secondary template:** `/Users/esperie/repos/loom/kailash-py/src/kailash/trust/plane/conformance/__init__.py`

- `ConformanceLevel(Enum)` — COMPATIBLE / CONFORMANT / COMPLETE (`__init__.py:38`)
- `ConformanceTest(@dataclass)` — single test with `RequirementLevel` (MUST / SHOULD / MAY) (`__init__.py:61`)
- `ConformanceReport` (`__init__.py:86`)
- `ConformanceSuite` (`__init__.py:215`) — drives a test set against an implementation
- This is the **EATP TrustPlane suite** (RFC-2119-style requirements testing) — heavier than PACT's byte-canonical vectors.

**Recommendation:** Use **PACT conformance/ as the template** for `kailash.delegate.conformance/`. Same module layout (`vectors.py`, `runner.py`, `cli.py`), same `canonical_json_dumps` byte-equality contract, same `VectorStatus.PASSED|FAILED|UNSUPPORTED` shape. Add Delegate-specific contract names (e.g. `D1` = Connector capabilities canonical, `D2` = audit-chain emission canonical, etc.). Vectors live as `*.json` files vendored from kailash-rs per `rules/cross-sdk-inspection.md` Rule 4a (sibling-canonical fixtures vendored, NOT re-authored).

**Reuse verdict:** **PATTERN-CLONE FROM `pact/conformance/`.** Do NOT re-invent the conformance harness. The PACT cross-SDK byte-equality contract is the working reference; Delegate's contract is structurally identical (different fields, same byte-canonical-vs-vendored-vectors discipline).

---

## 9. Package layout decision — `src/kailash/delegate/` (per issue #1035, confirmed by convention)

**Existing layout convention** (`ls /Users/esperie/repos/loom/kailash-py/src/kailash/` shows 40+ subpackages):

```
src/kailash/{access_control, adapters, analysis, api, channels, client, config,
             core, database, db, diagnostics, edge, events, gateway,
             infrastructure, integrations, manifest.py, middleware, migration,
             ml, monitoring, nodes, observability, planning, resources, runtime,
             security.py, servers, testing, tracking, trust, utils,
             visualization, workflow}
```

**Versus `packages/` (separate-installable sub-packages):**

```
packages/{kailash-align, kailash-dataflow, kailash-kaizen, kailash-mcp,
          kailash-ml, kailash-nexus, kailash-pact, kaizen-agents}
```

**The decision rule** (from `rules/framework-first.md` + `pyproject.toml` analysis):

- `src/kailash/<sub>/` is for **first-class subsystems shipped with `pip install kailash`** — workflow runtime, trust plane, governance primitives, observability. These all live in the core `kailash` package (version `2.23.0` per `pyproject.toml`).
- `packages/kailash-<X>/` is for **opinionated framework packages** with their own version cadence, optional extras, and standalone install (e.g. `pip install kailash-pact`).

**Issue #1035 says `from kailash.delegate import ...`.** That import path REQUIRES `src/kailash/delegate/` — not `packages/kailash-delegate/`. Confirmed by the existing `src/kailash/trust/`, `src/kailash/workflow/`, `src/kailash/runtime/` subpackage convention (all shipped under the `kailash` top-level).

**Recommendation:** **`src/kailash/delegate/` per #1035 issue body.** This places Delegate alongside `src/kailash/trust/` (envelope + chain), `src/kailash/runtime/` (executors), and `src/kailash/workflow/` (lifecycle) — exactly the primitives Delegate composes. A separate `packages/kailash-delegate/` would (a) break the documented import path, (b) require a new pypi name + version cadence, (c) duplicate the dependency on `kailash.trust` and `kailash-pact` that core `kailash` already carries. Per `rules/dependencies.md` § "Latest Versions Always" and `python-environment.md` § "Monorepo Sub-Packages MUST Be Installed Editable", the cost of a new sub-package is real; the benefit (separate version cadence) is not needed for a composition primitive that lives directly on top of trust+pact.

**Reuse verdict:** **`src/kailash/delegate/` per #1035 issue body.** Single source of truth, no new sub-package.

---

## 10. No-existing-Delegate confirmation — kaizen-agents `Delegate` is a different concept (near-miss documented)

**Grep results** (`grep -rn "class Delegate\|from kailash.delegate\|import kailash.delegate"`):

| Hit                                                                 | Type                                           | Significance                                             |
| ------------------------------------------------------------------- | ---------------------------------------------- | -------------------------------------------------------- |
| `src/kailash/trust/plane/delegation.py:65`                          | `class DelegateStatus(Enum)`                   | Enum, not the composition surface                        |
| `src/kailash/trust/export/siem.py:157`                              | `class DelegateEvent(SIEMEvent)`               | SIEM event subclass, not the composition surface         |
| `packages/kaizen-agents/src/kaizen_agents/delegate/delegate.py:270` | **`class Delegate:`**                          | **NEAR-MISS — different concept** (LLM execution facade) |
| `packages/kaizen-agents/src/kaizen_agents/delegate/events.py:46`    | `class DelegateEvent:`                         | Event type for the kaizen-agents Delegate                |
| `packages/kailash-mcp/.venv/.../pandas/.../test_constructors.py:60` | `class Delegate(PandasDelegate, PandasObject)` | Vendored pandas test — irrelevant                        |

**Critical near-miss: `kaizen_agents.delegate.Delegate`** (`packages/kaizen-agents/src/kaizen_agents/delegate/delegate.py:270`, 711 LOC):

- **Purpose:** "Facade composing a wrapper stack for autonomous AI execution" (`delegate.py:271`). Composes `AgentLoop → [L3GovernedAgent] → [MonitoredAgent]`.
- **Constructor takes** (`delegate.py:351-359`):
  ```python
  Delegate(
      model: str,                              # LLM model name
      signature: type[Signature] | None,        # Kaizen Signature class
      tools: list | ToolRegistry,
      system_prompt: str,
      max_turns: int,
      mcp_servers: list,
      budget_usd: float | None,
      envelope: ConstraintEnvelope | None,      # IMPORTS THE CANONICAL TYPE
      ...
  )
  ```
- **No `compose()` classmethod.** No `connector=`, no `pact_engine=`, no `executor=`. It is an LLM-execution facade, NOT the composition surface issue #1035 describes.

**How they relate:** The kaizen-agents `Delegate` is one POSSIBLE Executor implementation that the new `kailash.delegate.Delegate.compose(... executor=kaizen_agents.Delegate(...) ...)` could wire. They sit at different layers:

- `kailash.delegate.Delegate` (new, issue #1035) = composition primitive (Connector × Signature × Envelope × Executor × PactEngine)
- `kaizen_agents.delegate.Delegate` (existing) = one specific Executor (LLM agent loop with wrapper stack)

**Naming risk:** Both classes named `Delegate` will create import-path confusion. Two options:

- (a) Rename the new one (e.g. `Composition`, `ComposedDelegate`, `DelegateComposition`) — breaks #1035's documented `from kailash.delegate import Delegate` import.
- (b) Keep both names; document the disambiguation in `kailash/delegate/__init__.py` and update kaizen-agents docs to reference its Delegate as `kaizen_agents.Delegate`.

**Recommendation:** Option (b). The two classes live in different packages (`kailash.delegate.Delegate` vs `kaizen_agents.Delegate`) so the import statement disambiguates. Per `rules/recommendation-quality.md` MUST-3 — cons: import-collision risk in user code that does `from kailash.delegate import Delegate` AND `from kaizen_agents import Delegate` in the same file. Mitigation: a one-line note in the SPEC v0 (when it lands) calling out the namespace split.

**Reuse verdict:** **NO EXISTING IMPLEMENTATION OF THE ISSUE-#1035 COMPOSITION SURFACE.** Near-miss documented; namespace collision risk flagged for the spec.

---

## Cross-cutting reuse table

| Delegate dependency               | kailash-py primitive                                                     | Path                                                                                         | Reuse?                                                                     |
| --------------------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| PACT engine                       | `PactEngine`                                                             | `packages/kailash-pact/src/pact/engine.py:126`                                               | **Reuse as-is**                                                            |
| EATP audit chain                  | `TrustLineageChain` + records                                            | `src/kailash/trust/chain.py:672`                                                             | **Reuse as-is**                                                            |
| Cross-SDK canonical JSON          | `canonical_json_dumps`                                                   | `src/kailash/trust/_json.py:99` + `packages/kailash-pact/src/pact/conformance/vectors.py:80` | **Reuse as-is**                                                            |
| EATP sync emitter                 | `PactEatpEmitter` Protocol                                               | `src/kailash/trust/pact/eatp_emitter.py:28`                                                  | **Reuse as-is**                                                            |
| ConstraintEnvelope (tighten-only) | Canonical SPEC-07 `ConstraintEnvelope`                                   | `src/kailash/trust/envelope.py`                                                              | **Reuse as-is**                                                            |
| Envelope `intersect()`            | `ConstraintEnvelope.intersect()`                                         | `src/kailash/trust/envelope.py:838`                                                          | **Reuse as-is**                                                            |
| Envelope tightening predicate     | `ConstraintEnvelope.is_tighter_than()`                                   | `src/kailash/trust/envelope.py:867`                                                          | **Reuse as-is**                                                            |
| Envelope HMAC sign/verify         | `sign_envelope` / `verify_envelope`                                      | `src/kailash/trust/envelope.py:1424, 1489`                                                   | **Reuse as-is**                                                            |
| Connector ABC                     | none — fresh authoring                                                   | (new: `src/kailash/delegate/connector.py`)                                                   | **Fresh (~50 LOC; template from `StreamingChatAdapter` Protocol pattern)** |
| Signature (application-supplied)  | Kaizen `Signature` (Protocol-satisfies)                                  | `packages/kailash-kaizen/src/kaizen/signatures/core.py:249`                                  | **Protocol acceptance**                                                    |
| Executor (application-supplied)   | Application-defined; kaizen-agents Delegate, `LocalRuntime`, etc.        | (Protocol acceptance)                                                                        | **Protocol acceptance**                                                    |
| Tenant scoping wrapper            | DataFlow `tenancy/` + audit/JWT tenant_id flow; no Trust-Plane primitive | `packages/kailash-dataflow/src/dataflow/tenancy/` + scattered                                | **Mostly fresh (~30 LOC wrapper)**                                         |
| Lifecycle state machine           | enum + transition guard (kailash convention)                             | `src/kailash/trust/plane/delegation.py:65` `DelegateStatus` enum pattern                     | **Pattern reuse, no fresh framework**                                      |
| Conformance suite                 | PACT N4/N5 conformance runner + vectors                                  | `packages/kailash-pact/src/pact/conformance/`                                                | **Pattern-clone (template)**                                               |
| Layout: package home              | `src/kailash/delegate/`                                                  | (new)                                                                                        | **Per #1035 spec**                                                         |
| `Delegate` class itself           | NONE                                                                     | (new)                                                                                        | **Fresh authoring**                                                        |

---

## Suggested fresh-authoring footprint (orientation only — not a plan)

The Delegate composition surface authoring is bounded to roughly:

1. `src/kailash/delegate/__init__.py` — public surface, `__all__` per `rules/orphan-detection.md` Rule 6
2. `src/kailash/delegate/connector.py` — `Connector` ABC + Protocol (~50 LOC)
3. `src/kailash/delegate/delegate.py` — `Delegate` + `Delegate.compose(...)` classmethod (~300-500 LOC, composition logic; no business logic — wires PactEngine + ConstraintEnvelope + Connector + Signature + Executor)
4. `src/kailash/delegate/tenant.py` — `TenantScope` wrapper (~30 LOC)
5. `src/kailash/delegate/state.py` — `DelegateState` enum + transition guard (~50 LOC)
6. `src/kailash/delegate/conformance/{vectors.py, runner.py, cli.py}` — cloned from `pact/conformance/` (~400-600 LOC, mostly schema + runner; vectors live as JSON files vendored from kailash-rs)
7. `tests/integration/test_delegate_wiring.py` per `rules/facade-manager-detection.md` Rule 2 — Tier 2 test exercising Delegate end-to-end through the framework facade
8. `tests/regression/test_issue_1035_delegate_cross_sdk_byte_parity.py` per `rules/cross-sdk-inspection.md` Rule 4 — pin ≥3 byte vectors from kailash-rs

Total: ~900-1200 LOC of new authoring, plus vendored conformance vectors from kailash-rs. Comfortably within one shard's per-session capacity budget per `rules/autonomous-execution.md` § Per-Session Capacity Budget if the conformance vectors are scoped as a separate shard (load-bearing logic is the composition layer + Connector ABC; conformance vectors are mostly boilerplate-stamping).

---

## Notes on framing for #1035 implementation

- The `01-external-spec-extraction.md` (companion in this workspace) flagged that the source document is "Pre-draft scaffold. Not the spec." (`02-delegate-spec-v0-outline.md:3`). The kailash-py primitive landscape is therefore the harder constraint than the spec text: every Delegate decision MUST compose with the existing PACT/EATP/ConstraintEnvelope/conformance surface above, OR explicitly justify a fresh implementation that diverges.
- Per `rules/cross-sdk-inspection.md` MUST Rule 3 (EATP D6 compliance) — implementation details may differ between py and rs, but **semantics MUST match**. The canonical JSON encoder + the N4/N5 conformance pattern is the structural defense that keeps this true.
- Per `rules/orphan-detection.md` MUST Rule 1 — every public Delegate facade attribute MUST have a production call site in the framework's hot path within 5 commits. The Delegate is at risk of orphan-pattern (downstream consumers import it but the framework never invokes it on the data path) UNLESS it is wired into kaizen-agents' Delegate (Executor) and PACT's submit() path as the canonical composition entry.

---

## Survey complete

Report file: `/Users/esperie/repos/loom/kailash-py/workspaces/issue-1035-delegate-py/01-analysis/03-kailash-py-primitive-survey.md`
