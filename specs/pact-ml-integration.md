# PACT × kailash-ml Integration — Governance Methods For The ML Lifecycle

Version: 1.0.0 (draft)
Package: `kailash-pact`
Target release: **kailash-pact 0.10.0** (shipping in the kailash-ml 1.0.0 wave)
Status: DRAFT at `workspaces/kailash-ml-audit/supporting-specs-draft/pact-ml-integration-draft.md`. Promotes to `specs/pact-ml-integration.md` after round-3 convergence.
Supersedes: none — this is a net-new governance surface on `PactEngine` / `GovernanceEngine`.
Parent domain: PACT (organizational governance — D/T/R clearance, envelopes, addressing).
Sibling specs: `specs/pact-absorb-capabilities.md`, `specs/pact-enforcement.md`, `specs/pact-envelopes.md`, `specs/pact-addressing.md`.

Origin: `workspaces/kailash-ml-audit/04-validate/approved-decisions.md` Decision 12 (cross-tenant admin export gated by PACT D/T/R), plus the engine-method clearance gap surfaced by round-1 theme T3 (tenant isolation absent from 13/13 ML engines) and round-2 closure Shard 4 (`ml-registry-draft.md` §5 mandates PACT `check_cross_tenant_op`).

---

## 1. Scope + Non-Goals

### 1.1 In Scope

Three new `GovernanceEngine` methods required by the kailash-ml 1.0.0 engine surface:

1. `check_trial_admission(...)` — pre-trial admission gate for `AutoMLEngine`, `HyperparameterSearch`, and agent-driven AutoML sweeps (budget, latency, fairness).
2. `check_engine_method_clearance(...)` — per-method D/T/R clearance gate that every `MLEngine` subclass calls at mutation entry points (fit / promote / delete / archive / rollback).
3. `check_cross_tenant_op(...)` — explicit cross-tenant gate for the `ml-registry-pact.md` post-1.0 cross-tenant export/import/mirror surface (Decision 12).

All three methods:

- Acquire `PactEngine._lock` / `GovernanceEngine._lock` (PACT MUST Rule 8 — thread-safety).
- Return a frozen dataclass (PACT MUST Rule 1 — frozen `GovernanceContext` discipline).
- Fail-CLOSED on any probe exception (PACT MUST Rule 4 — exception is NOT a pass).
- Audit the decision to the trust-plane audit chain with `tenant_id`, `actor_id`, and a `sha256:<8hex>` fingerprint of any classified payload field (per `rules/event-payload-classification.md` §2).

### 1.2 Out of Scope (Owned By Sibling Specs)

- Envelope resolution itself → `specs/pact-envelopes.md`.
- Audit-chain integrity verification → `specs/pact-absorb-capabilities.md` §1.
- Enforcement hook wiring into dataflow engine → `specs/pact-enforcement.md`.
- Addressing / role graph walks → `specs/pact-addressing.md`.
- ML engine internals (which methods exist, their signatures) → `ml-engines-v2-draft.md`.

### 1.3 Non-Goals

- **No new PACT primitive types.** These three methods reuse `ClearanceContext`, `ConstraintEnvelopeConfig`, and the D/T/R clearance grammar already specified in `specs/pact-envelopes.md`.
- **No policy DSL extensions.** Constraints are consumed as-is from the envelope.
- **No decision caching** — every call is evaluated fresh. Caching is a future optimization tracked at kailash-pact#TBD (post-1.0).

---

## 2. Public API

All three methods live on `kailash_pact.engines.GovernanceEngine` (re-exported from `kailash_pact.GovernanceEngine`).

### 2.1 `check_trial_admission`

```python
def check_trial_admission(
    self,
    *,
    tenant_id: str,
    actor_id: str,
    trial_config: Mapping[str, Any],
    budget_microdollars: int,
    latency_budget_ms: int,
    fairness_constraints: Optional[Mapping[str, Any]] = None,
) -> AdmissionDecision:
    """Pre-trial admission gate.

    Called by AutoMLEngine.run(), HyperparameterSearch.search(),
    and every agent-driven tuning sweep before a trial is scheduled.
    """
```

**Returns:**

```python
@dataclass(frozen=True)
class AdmissionDecision:
    admitted: bool
    reason: str                           # human-readable rationale
    binding_constraint: Optional[str]     # name of the envelope constraint that decided
    tenant_id: str
    actor_id: str
    decided_at: datetime                  # UTC, ISO-8601
    decision_id: str                      # UUID4, logged to audit chain
```

**Invariants:**

- Acquires `self._lock` for the entire resolution-plus-audit window.
- `budget_microdollars` and `latency_budget_ms` MUST be non-negative finite ints; negative values raise `ValueError` BEFORE the lock is acquired.
- `fairness_constraints` is a free-form mapping that the envelope's `pact.ml.fairness` constraint (if declared) consumes; if no such constraint is declared the mapping is ignored (not a rejection).
- Fails CLOSED: if any constraint-probe raises, returns `AdmissionDecision(admitted=False, reason=f"probe exception: {type(e).__name__}", binding_constraint=None, ...)`. The exception is NEVER swallowed silently — it is logged at WARN with the fingerprint, and the returned `reason` string identifies the probe that raised.
- Audit row is appended BEFORE the return statement, under the lock.
- `decision_id` is a fresh UUID4 per call — callers that want to correlate to a trial log the id.
- `trial_config` MUST NOT appear verbatim in the audit row — classified fields in the config are hashed to `sha256:<8hex>` via `kailash_pact.classification.fingerprint()`.

### 2.2 `check_engine_method_clearance`

```python
def check_engine_method_clearance(
    self,
    *,
    tenant_id: str,
    actor_id: str,
    engine_name: str,
    method_name: str,
    clearance_required: Literal["D", "T", "R", "DTR"],
) -> ClearanceDecision:
    """Per-engine-method clearance gate.

    Every MLEngine mutation entry point (fit, predict, promote, delete,
    archive, rollback) calls this BEFORE it performs the mutation.
    """
```

**Returns:**

```python
@dataclass(frozen=True)
class ClearanceDecision:
    cleared: bool
    reason: str
    missing_dimensions: tuple[str, ...]   # subset of ("D", "T", "R") that the actor lacks
    tenant_id: str
    actor_id: str
    engine_name: str
    method_name: str
    decided_at: datetime
    decision_id: str
```

**Invariants:**

- `engine_name` MUST match `^[a-zA-Z_][a-zA-Z0-9_]*$` — rejected with `ValueError` on mismatch (prevents identifier-injection into audit rows, aligns with `rules/dataflow-identifier-safety.md` §2).
- `method_name` MUST match the same regex.
- `clearance_required` MUST be one of the four literal strings; any other value raises `ValueError`.
- `"DTR"` means ALL THREE dimensions are required.
- `missing_dimensions` is the tuple of dimensions the actor lacks; empty tuple when `cleared=True`.
- `_lock`-guarded; audit-written.

### 2.3 `check_cross_tenant_op`

```python
def check_cross_tenant_op(
    self,
    *,
    actor_id: str,
    src_tenant_id: str,
    dst_tenant_id: str,
    operation: Literal["export", "import", "mirror"],
    clearance_required: Literal["D", "T", "R", "DTR"],
) -> CrossTenantDecision:
    """Cross-tenant operation gate.

    Called by the post-1.0 cross-tenant surface specified in
    `ml-registry-pact.md` (Decision 12). A cross-tenant op requires
    BOTH source-tenant clearance AND destination-tenant clearance.
    """
```

**Returns:**

```python
@dataclass(frozen=True)
class CrossTenantDecision:
    admitted: bool
    reason: str
    src_clearance: ClearanceDecision      # clearance check against src tenant
    dst_clearance: ClearanceDecision      # clearance check against dst tenant
    operation: Literal["export", "import", "mirror"]
    actor_id: str
    decided_at: datetime
    decision_id: str
```

**Invariants:**

- Both `src_tenant_id` and `dst_tenant_id` MUST be non-empty strings; identical src/dst raises `ValueError("cross-tenant op requires distinct src_tenant_id and dst_tenant_id")`. Self-loops are not cross-tenant and would bypass audit intent.
- Both underlying `check_engine_method_clearance` calls happen under a SINGLE acquisition of `self._lock` (not two). Two separate acquisitions would produce split-brain audit rows where one tenant's state is captured at t0 and the other at t1.
- `admitted` is the logical AND of `src_clearance.cleared AND dst_clearance.cleared`.
- On `admitted=False`, `reason` enumerates both sides: e.g. `"src=DENIED (missing T) + dst=CLEARED"`.
- Audit row carries BOTH tenant ids for forensic queries ("show every cross-tenant op touching tenant_a this quarter").

---

## 3. Error Taxonomy

All errors inherit from `kailash_pact.exceptions.PactError` — the existing base. New errors:

```python
class PactError(Exception):
    """Base for every PACT exception."""

class GovernanceAdmissionError(PactError):
    """Raised only for programmer-error inputs (negative budgets, etc.).
    A denial is NOT an error — it is an AdmissionDecision(admitted=False)."""

class GovernanceClearanceError(PactError):
    """Same discipline: raised only for programmer-error inputs. A denied
    clearance returns ClearanceDecision(cleared=False)."""

class GovernanceCrossTenantError(PactError):
    """Raised only for programmer-error inputs (identical src/dst tenant, etc.).
    A denied cross-tenant op returns CrossTenantDecision(admitted=False)."""
```

**Discipline:** Denials are DATA, not exceptions. Programmer errors (invalid inputs, regex-failures, negative budgets) are exceptions. This mirrors `PactEngine.verify_audit_chain` — a chain break returns `is_valid=False`, never raises.

**Why:** Exceptions-as-denial is fail-OPEN on the catch path (a caller who writes `try: engine.check_trial_admission(...); proceed() except Exception: proceed()` silently bypasses governance). Data-as-denial forces the caller to inspect the result.

---

## 4. Thread-Safety Contract

Every method:

1. Acquires `self._lock` BEFORE any state read.
2. Holds the lock for the entire duration of constraint resolution + audit append.
3. Releases the lock only after the frozen result is constructed.

Callers MUST NOT hold external locks across these calls (would invert lock order and risk deadlock against `PactEngine.submit`).

---

## 5. Audit Contract

Every call appends ONE audit row to the PACT audit chain with schema:

| Column                | Type        | Value                                                                                     |
| --------------------- | ----------- | ----------------------------------------------------------------------------------------- |
| `decision_id`         | `TEXT`      | UUID4, primary key                                                                        |
| `method`              | `TEXT`      | `"check_trial_admission"` / `"check_engine_method_clearance"` / `"check_cross_tenant_op"` |
| `tenant_id`           | `TEXT`      | per `rules/tenant-isolation.md` §5 (indexed)                                              |
| `actor_id`            | `TEXT`      | JWT sub or equivalent                                                                     |
| `engine_name`         | `TEXT`      | NULL unless method = `check_engine_method_clearance`                                      |
| `method_name`         | `TEXT`      | NULL unless method = `check_engine_method_clearance`                                      |
| `operation`           | `TEXT`      | NULL unless method = `check_cross_tenant_op`                                              |
| `src_tenant_id`       | `TEXT`      | NULL unless method = `check_cross_tenant_op`                                              |
| `dst_tenant_id`       | `TEXT`      | NULL unless method = `check_cross_tenant_op`                                              |
| `admitted_or_cleared` | `INTEGER`   | 0 or 1                                                                                    |
| `binding_constraint`  | `TEXT`      | nullable                                                                                  |
| `reason`              | `TEXT`      | human-readable                                                                            |
| `decided_at`          | `TIMESTAMP` | UTC, ISO-8601                                                                             |
| `payload_fingerprint` | `TEXT`      | `sha256:<8hex>` fingerprint of serialized classified-field payload                        |

Audit rows are IMMUTABLE (Decision 2 — GDPR erasure deletes run/artifact/model content, NEVER an audit row).

---

## 6. Test Contract

Per `rules/facade-manager-detection.md` §2 — every manager-shape method needs a Tier 2 wiring test.

### 6.1 Tier 1 (unit, mocks-allowed)

- `test_admission_invalid_budget_raises.py` — `budget_microdollars=-1` → `ValueError`.
- `test_admission_fair_constraint_passes.py` — a passing envelope.
- `test_admission_probe_exception_fails_closed.py` — patched probe raises → `admitted=False`, WARN log line emitted.
- Parallel set for `check_engine_method_clearance` and `check_cross_tenant_op`.

### 6.2 Tier 2 (integration, real PactEngine)

File naming per `rules/facade-manager-detection.md` §2:

- `tests/integration/test_check_trial_admission_wiring.py`
- `tests/integration/test_check_engine_method_clearance_wiring.py`
- `tests/integration/test_check_cross_tenant_op_wiring.py`

Each test MUST:

1. Construct a real `PactEngine` + `GovernanceEngine` against real infra (in-memory SQLite is acceptable for audit store).
2. Set up a real envelope with a real D/T/R clearance configuration.
3. Call the method end-to-end.
4. Assert the decision dataclass fields.
5. Assert the audit row exists in the audit chain via `engine.verify_audit_chain(...).verified_count >= 1`.
6. Assert the audit row carries the expected `tenant_id`, `actor_id`, `decision_id`.
7. For `check_cross_tenant_op` — assert the audit row carries BOTH tenant ids.

### 6.3 Cross-SDK parity test

`tests/integration/test_pact_ml_cross_sdk_parity.py` — asserts that a decision written by kailash-pact and read by a hypothetical kailash-rs consumer would deserialize the same dataclass fields. For 1.0.0 this is a JSON-round-trip test against the documented serialization.

---

## 7. Cross-SDK Parity Requirements

PACT's `GovernanceEngine` exists in kailash-rs at `crates/kailash-pact/src/engines/governance.rs`. The three new methods MUST be added there in kailash-pact v0.10.0-rs with byte-identical:

- Method signatures (arg names, types).
- Returned dataclass field names and types.
- Audit row column names and types.
- `sha256:<8hex>` fingerprint format (per `rules/event-payload-classification.md` §2).

Cross-SDK follow-up is deferred until kailash-rs scopes a Rust-side PACT ML hook surface. The parity contract above (method signatures + audit row shape + fingerprint format) is the baseline. kailash-pact 0.10.0 shipped 2026-04-21 on the Python side; a Rust-side parity issue will be filed if/when the Rust surface is proposed.

**Why:** PACT is a Terrene Foundation peer standard (per `rules/terrene-naming.md` § "Canonical Terminology"). A Python `check_trial_admission` decision MUST correlate byte-identically with a Rust `check_trial_admission` decision so cross-SDK audit queries return consistent results.

---

## 8. Industry Comparison

| Capability                             | kailash-pact 0.10.0 | Tecton gate   | SageMaker Clarify | OpenPolicyAgent (OPA) |
| -------------------------------------- | ------------------- | ------------- | ----------------- | --------------------- |
| Pre-trial admission (budget + latency) | Y                   | N (no budget) | N                 | Y (requires policy)   |
| Per-method D/T/R clearance             | Y                   | N (RBAC only) | N                 | Partial (no D/T/R)    |
| Cross-tenant op gate                   | Y                   | N             | N                 | Y (requires policy)   |
| Frozen decision dataclass              | Y                   | N             | N                 | N (opaque JSON)       |
| Audit row with fingerprinted payload   | Y                   | N             | Partial           | N                     |
| Fail-CLOSED on probe exception         | Y                   | Unspecified   | Unspecified       | Y                     |
| Thread-safe under `_lock`              | Y                   | N/A           | N/A               | N/A (stateless)       |

**Position:** PACT is the only framework offering D/T/R clearance semantics in a production-grade governance engine with a frozen-dataclass decision API and a forensic audit chain. Budget + fairness constraints at admission time are unique to the Kailash ML stack.

---

## 9. Migration Path (kailash-pact 0.9.x → 0.10.0)

`kailash-pact 0.9.x` users get these methods as ADDITIONS — no existing method signature changes. The only user-visible change is the new dependency declaration:

```toml
# kailash-ml 1.0.0 pyproject
dependencies = [
    "kailash-pact>=0.10.0",  # was >=0.9.0; bumped for the three new methods
]
```

0.9.x users who do NOT use kailash-ml are unaffected. No deprecations, no shims.

---

## 10. Release Coordination Notes

This spec is ONE of SEVEN in the kailash-ml 1.0.0 "wave release":

- kailash-pact 0.10.0 (this spec)
- kailash-nexus 2.2.0 (`nexus-ml-integration-draft.md`)
- kailash-kaizen 2.12.0 (`kaizen-ml-integration-draft.md`)
- kailash-align 0.5.0 (`align-ml-integration-draft.md`)
- kailash 2.9.0 (`kailash-core-ml-integration-draft.md`)
- kailash-dataflow 2.1.0 (`dataflow-ml-integration-draft.md`)
- kailash-ml 1.0.0 (the 15 existing `ml-*-draft.md` specs)

**Release order (structural constraint):**

1. kailash 2.9.0 — all downstream packages depend on the new `src/kailash/ml/errors.py` hierarchy and `src/kailash/diagnostics/protocols.py` expansions.
2. kailash-pact 0.10.0, kailash-nexus 2.2.0, kailash-kaizen 2.12.0, kailash-dataflow 2.1.0 — independent of each other, release in parallel.
3. kailash-align 0.5.0 — depends on kailash-ml's `RLLifecycleProtocol`, which is a kailash-ml symbol — so align depends on ml.
4. kailash-ml 1.0.0 — depends on kailash-pact 0.10.0 + kailash-kaizen 2.12.0 + kailash-dataflow 2.1.0 + kailash 2.9.0.

**Parallel-worktree package ownership coordination** (`rules/agents.md` MUST rule): kailash-pact 0.10.0 version bump + CHANGELOG owner is the pact-specialist agent; every other agent's prompt MUST exclude `packages/kailash-pact/pyproject.toml`, `packages/kailash-pact/src/kailash_pact/__init__.py::__version__`, and `packages/kailash-pact/CHANGELOG.md` from their edit scope.

---

## 11. Cross-References

- kailash-ml specs consuming these methods:
  - `ml-automl-draft.md` §3 — `AutoMLEngine.run()` calls `check_trial_admission` before every trial.
  - `ml-engines-v2-draft.md` §4 — every `MLEngine.fit` / `.predict` / `.promote` / `.delete` / `.archive` / `.rollback` calls `check_engine_method_clearance`.
  - `ml-registry-draft.md` §5 + `ml-registry-pact.md` (post-1.0) — cross-tenant export/import/mirror calls `check_cross_tenant_op`.
- PACT companion specs:
  - `specs/pact-absorb-capabilities.md` — the 5 existing absorbed methods (same discipline applied here).
  - `specs/pact-envelopes.md` — envelope resolution and D/T/R clearance grammar.
  - `specs/pact-enforcement.md` — dataflow engine hook wiring.
- Rule references:
  - `rules/tenant-isolation.md` §1, §5 — tenant_id on every cache key / audit row.
  - `rules/event-payload-classification.md` §2 — `sha256:<8hex>` fingerprint format.
  - `rules/facade-manager-detection.md` §2 — Tier 2 wiring test per new manager-shape method.
  - `rules/dataflow-identifier-safety.md` §2 — regex validation on every user-influenced identifier that reaches the audit row.
