# EATP SDK Gap Implementation Plan

**Date**: 2026-03-14
**Workspace**: `eatp-gaps`
**Source**: Synthesized from all analyses + cross-SDK analysis + Rust team decisions (doc 08)

---

## Implementation Phases

### Phase 0: Specification Alignment (BLOCKING — 2-3 days)

Spec-only deliverables. Per Rust team decision D6: **no implementation coordination** — both teams implement from the spec independently. Phase 1 (production safety fixes) can proceed in parallel since those are internal bugfixes with no cross-SDK surface.

| Deliverable                | Content                                                                                     | Owner              |
| -------------------------- | ------------------------------------------------------------------------------------------- | ------------------ |
| Hook Specification         | `HookType` values (trust-native only), `HookResult` fields, abort semantics, priority rules | Both teams         |
| Proximity Defaults         | Canonical 80/95, "conservative" 70/90 preset                                                | Both teams         |
| Behavioral Scoring         | Factor names, weights, zero-data behavior, computation algorithm (spec concern per D4)      | Both teams         |
| SIEM Event Schema          | OCSF-aligned event definitions for all EATP operations                                      | Both teams         |
| Observability Metrics      | OpenTelemetry metric naming convention                                                      | Both teams         |
| EATP Scope ADR             | What belongs in eatp vs downstream — circuit breaker clearly out (D2)                       | Terrene Foundation |
| ReasoningTrace JSON Schema | Cross-MCP portable trace format for trust decision reasoning (NEW per D5)                   | Both teams         |

**Coordination model** (D6): Agree on spec, then each team prioritizes their own backlog independently. Reference implementations are prior art to study, not dependencies to track.

#### Gate 0 Checklist

- [ ] All 7 deliverables documented in shared spec addendum
- [ ] Both Python and Rust teams sign off on each deliverable
- [ ] Proximity defaults agreed: 80/95 canonical, 70/90 "conservative" preset
- [ ] HookType enum restricted to trust-native events only
- [ ] EATP scope ADR ratified by Terrene Foundation
- [ ] ReasoningTrace JSON schema defined and portable across MCP channels

---

### Phase 1: Production Safety & Pattern Learning (3-4 days)

Low-risk fixes that resolve active production issues and force reading core SDK modules. Each fix has clear precedent in existing code. **Can proceed in parallel with Phase 0.**

#### G5/G5+: Bounded Memory for Enforcers

**Files**: `enforce/shadow.py`, `enforce/strict.py`
**Pattern source**: `postures.py:209-232` (`PostureStateMachine._record_transition`)

- Add `maxlen: int = 10_000` parameter to `ShadowEnforcer.__init__()` and `StrictEnforcer.__init__()`
- Trim oldest 10% when `len(_records) >= maxlen`
- Apply same bound to `StrictEnforcer._review_queue`
- Add `change_rate` metric to `ShadowMetrics`
- Wrap shadow evaluation in try/except (shadow must never crash main path)

**Tests**: Verify bounded growth at 10K+ records, verify metrics accuracy after trimming, verify change_rate computation.

#### G8/G8+: Fix Deprecated get_event_loop()

**Files**: `enforce/decorators.py` (lines 94, 182, 262), `messaging/channel.py` (line 331), `mcp/server.py` (lines 1531, 1538, 1542)

- Replace `asyncio.get_event_loop()` with:
  ```python
  try:
      loop = asyncio.get_running_loop()
  except RuntimeError:
      loop = None
  if loop is not None:
      raise RuntimeError("Cannot use sync wrapper inside running event loop.")
  else:
      result = asyncio.run(coroutine)
  ```
- Apply consistently across all 8 call sites

**Tests**: Verify no DeprecationWarning on Python 3.12+. Verify RuntimeError when called inside running loop.

#### G9: Document Threading Model

**File**: `circuit_breaker.py`

- Add module-level docstring documenting async-only concurrency model
- Add `threading_mode` parameter documentation for future extension
- Leave asyncio.Lock as-is for v0.1.x (document the limitation)

**Tests**: None needed for documentation-only change.

#### G11/G11+: Fix Dimension Registry Mismatch

**Files**: `constraints/dimension.py`, `constraints/builtin.py`

- Align `BUILTIN_DIMENSIONS` set with actual registered dimension class names
- Add `data_access` and `communication` to the set
- Remove `geo_restrictions`, `budget_limit`, `max_delegation_depth`, `allowed_actions` (no implementations)
- Optionally add `eatp_category` property to `ConstraintDimension` ABC mapping to spec ConstraintType

**Tests**: Assert `BUILTIN_DIMENSIONS == set(register_builtin_dimensions().keys())`.

#### PS1: Cross-Process File Locking (NEW — CRITICAL)

**File**: `FilesystemStore` (store implementation)
**Prior art**: kailash-rs `fs4` locking

- Upgrade `FilesystemStore` from `threading.RLock` to `fcntl.flock` for all disk writes
- Keep `RLock` as fast path for single-process use (thread contention within same process)
- `fcntl.flock` acquired for all ESTABLISH, DELEGATE, VERIFY, AUDIT operations that touch filesystem
- Prevents TOCTOU race: two processes reading same parent as "active", one revokes, other creates child under revoked parent

**Tests**: Concurrent subprocess writes to same store directory. Verify no corruption under contention. Verify lock acquisition/release lifecycle.

#### PS2: Export Locking Utility (NEW — HIGH)

- Export `file_lock()` as public context manager, or
- Make `FilesystemStore.transaction()` work for filesystem (currently `TransactionContext` only supports `InMemoryTrustStore`)
- TrustPlane and future SDK consumers use SDK's locking, not their own

**Tests**: Context manager acquire/release. Shared vs exclusive locks. Timeout behavior.

#### PS3: Path Traversal Prevention (NEW — HIGH, Security)

**Files**: All store/filesystem code that constructs paths from ID parameters
**Prior art**: kailash-rs validates IDs against `[a-zA-Z0-9_-]` and canonicalizes paths

- Add `validate_id()` function: IDs must match `[a-zA-Z0-9_-]+`
- Apply to all ID parameters before filesystem path construction (agent_id, key_id, delegation_id, etc.)
- Same vulnerability class just fixed in TrustPlane — exists in the SDK

**Tests**: Path traversal attempts (`../`, `../../etc/passwd`, null bytes). Valid ID acceptance. Error messages.

#### Gate 1 Checklist

- [ ] Bounded memory matches PostureStateMachine pattern exactly
- [ ] No `asyncio.get_event_loop()` calls remain
- [ ] BUILTIN_DIMENSIONS aligns with registered dimensions
- [ ] Cross-process file locking active on all FilesystemStore writes
- [ ] Public locking utility exported
- [ ] Path traversal prevention on all ID parameters
- [ ] All changes carry SPDX header, `__all__`, `from __future__ import annotations`
- [ ] Tests follow existing class organization pattern
- [ ] Security review on PS3 path traversal fix

---

### Phase 2: Core Trust Model Completion (3 days)

**Requires Phase 0 completion** (proximity defaults from spec alignment).

Extend existing enforcement and circuit breaker systems. Medium risk — security-critical changes to verdict classification.

#### G2: Constraint Proximity Thresholds

**Files**: New `enforce/proximity.py`, modify `enforce/strict.py`, `enforce/shadow.py`
**ADR**: ADR-003 (Standalone ProximityScanner)

New module:

```python
@dataclass
class ProximityConfig:
    flag_threshold: float = 0.80   # Cross-SDK aligned (was 0.70)
    hold_threshold: float = 0.95   # Cross-SDK aligned (was 0.90)
    dimension_overrides: Dict[str, Tuple[float, float]] = field(default_factory=dict)

# Conservative preset for gradual rollout
CONSERVATIVE_PROXIMITY = ProximityConfig(flag_threshold=0.70, hold_threshold=0.90)

@dataclass
class ProximityAlert:
    dimension: str
    usage_ratio: float
    used: float
    limit: float
    escalated_verdict: Verdict
    original_verdict: Verdict

class ProximityScanner:
    def __init__(self, config: Optional[ProximityConfig] = None): ...
    def scan(self, results: Dict[str, ConstraintCheckResult]) -> List[ProximityAlert]: ...
    def escalate_verdict(self, base_verdict: Verdict, alerts: List[ProximityAlert]) -> Verdict: ...
```

Integration points:

- `StrictEnforcer`: After `classify()`, run proximity scan and escalate if needed
- `ShadowEnforcer`: Log proximity alerts without escalating

**Tests**: Agent at 81% → FLAGGED. Agent at 96% → HELD. Agent at 100% → BLOCKED. Agent at 79% → AUTO_APPROVED. Monotonic escalation (never downgrade). Float comparison edge cases. Multi-dimension simultaneous proximity. Conservative preset at 71%/91%.

#### G4: Per-Agent Circuit Breaker Registry

**File**: `circuit_breaker.py` (extend existing module)

```python
class CircuitBreakerRegistry:
    def __init__(self, default_config: Optional[CircuitBreakerConfig] = None): ...
    def get_or_create(self, agent_id: str, config: Optional[CircuitBreakerConfig] = None) -> PostureCircuitBreaker: ...
    def get_all_open(self) -> Dict[str, CircuitState]: ...
    def get_all_half_open(self) -> Dict[str, CircuitState]: ...
    def reset_agent(self, agent_id: str) -> None: ...
    def remove_agent(self, agent_id: str) -> None: ...
    def get_status_summary(self) -> Dict[str, int]: ...
```

**Note (D2)**: Circuit breaker stays in Python's `eatp` package — this is acknowledged as **pragmatic, not principled**. Per the Rust team's litmus test: "If you removed all circuit breaker code, would EATP still be a complete trust protocol? Yes." The canonical placement per EATP spec is in the agent framework (kailash-kaizen). Must add explicit documentation of this divergence. The `orchestration/` sub-package should be marked for migration to `kailash-kaizen` in v0.2.0.

**Tests**: Lazy creation, isolation between agents, bulk status query, cleanup.

#### Gate 2 Checklist

- [ ] Proximity thresholds use 80/95 defaults (cross-SDK aligned)
- [ ] Conservative preset (70/90) available
- [ ] Proximity escalation is monotonic: AUTO_APPROVED → FLAGGED → HELD → BLOCKED
- [ ] All utilization dimensions covered
- [ ] No bypass paths around proximity escalation
- [ ] Circuit breaker registry creates isolated breakers
- [ ] Circuit breaker boundary rationale documented
- [ ] Security review passed on G2 threshold bypass scenarios

---

### Phase 3: Architectural Extensibility + Cascade Revocation (3-4 days)

**Requires Phase 0 completion** (hook specification from spec alignment).

New module — highest design risk. Requires deep enforcement understanding from Phases 1-2.

#### G3: EATP Lifecycle Hooks (NARROWED SCOPE)

**File**: New `hooks.py` module
**ADR**: ADR-002 (Protocol-based with priority registry)

```python
class HookType(str, Enum):
    # Trust-native events ONLY (cross-SDK aligned)
    PRE_DELEGATION = "pre_delegation"
    POST_DELEGATION = "post_delegation"
    PRE_VERIFICATION = "pre_verification"
    POST_VERIFICATION = "post_verification"
    # REMOVED: PRE_TOOL_USE, POST_TOOL_USE, SUBAGENT_SPAWN
    # Orchestration events belong in kailash-kaizen

@dataclass
class HookContext:
    agent_id: str
    action: str
    hook_type: HookType
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

@dataclass
class HookResult:
    allow: bool  # False = abort the operation (fail-closed)
    reason: Optional[str] = None
    modified_context: Optional[Dict[str, Any]] = None

class EATPHook(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    @property
    @abstractmethod
    def event_types(self) -> Set[HookType]: ...
    @property
    def priority(self) -> int: return 100  # Lower = earlier execution
    @abstractmethod
    async def __call__(self, context: HookContext) -> HookResult: ...

class HookRegistry:
    def __init__(self, timeout_seconds: float = 5.0): ...
    def register(self, hook: EATPHook) -> None: ...
    def unregister(self, hook_name: str) -> None: ...
    async def execute(self, hook_type: HookType, context: HookContext) -> HookResult: ...
    def list_hooks(self, hook_type: Optional[HookType] = None) -> List[str]: ...
```

**Design constraints**:

- HookType restricted to 4 trust-native events (cross-SDK aligned)
- Hooks execute in priority order (lowest first)
- Any hook returning `allow=False` aborts the chain (fail-closed)
- Hook timeout prevents DoS (default 5s)
- Hook crash = block the action (fail-closed, not fail-open)
- Hooks complement decorators — both are needed
- Sync compatibility via async-first with sync wrapper

**Tests**: Priority ordering, abort semantics, timeout enforcement, crash handling, concurrent registration.

#### MG1: Cascade Revocation

**Files**: New `revocation.py` or extend `delegation.py`
**Rationale**: Core EATP spec requirement, 0% implemented in both Python and Rust SDKs.

```python
@dataclass
class RevocationEvent:
    revoked_agent_id: str
    revoked_by: str
    reason: str
    cascade: bool = True
    timestamp: datetime = field(default_factory=datetime.utcnow)

async def cascade_revoke(
    agent_id: str,
    store: TrustStore,
    reason: str,
    revoked_by: str,
) -> List[RevocationEvent]: ...
```

**Design constraints**:

- Revocation must walk the delegation chain and revoke all downstream delegations
- Must be atomic — partial revocation is not acceptable
- Must produce audit trail (RevocationEvents)
- Must handle circular delegation chains gracefully

**Tests**: Linear chain revocation, branching tree revocation, circular chain handling, audit trail completeness, idempotent re-revocation.

#### Gate 3 Checklist

- [ ] HookType contains ONLY trust-native events (4 values)
- [ ] Hooks complement decorators (not replace)
- [ ] Hook abort = fail-closed
- [ ] Hook timeout prevents DoS
- [ ] Hook crash = block action
- [ ] Cascade revocation walks full delegation chain
- [ ] Revocation is atomic with audit trail
- [ ] `__init__.py` updated with new public exports
- [ ] Security review completed

---

### Phase 4: Trust Scoring Enrichment + ReasoningTrace Parity (4 days)

**Requires Phase 0 completion** (behavioral scoring factor names/weights from spec alignment).

New scoring capability + ReasoningTrace feature parity with Rust. Requires G4 and G5 patterns established in earlier phases.

#### G1: Behavioral Trust Scoring

**File**: `scoring.py` (extend existing module)
**ADR**: ADR-001 (Complementary scoring model)

New types:

```python
@dataclass
class BehavioralData:
    total_actions: int = 0
    approved_actions: int = 0
    denied_actions: int = 0
    error_count: int = 0
    posture_transitions: int = 0
    time_at_current_posture_seconds: float = 0.0
    observation_window_seconds: float = 0.0

@dataclass
class BehavioralScore:
    score: int  # 0-100
    breakdown: Dict[str, float]
    grade: str
    computed_at: datetime
    agent_id: str

BEHAVIORAL_WEIGHTS: Dict[str, int] = {
    "approval_rate": 30,
    "error_rate": 25,
    "posture_stability": 20,
    "time_at_posture": 15,
    "interaction_volume": 10,
}
```

New functions:

```python
def compute_behavioral_score(agent_id: str, data: BehavioralData) -> BehavioralScore: ...
async def compute_combined_trust_score(
    agent_id: str, store: TrustStore,
    behavioral_data: Optional[BehavioralData] = None,
    posture_machine: Optional[PostureStateMachine] = None,
    structural_weight: float = 0.6,
    behavioral_weight: float = 0.4,
) -> CombinedTrustScore: ...
```

**Critical conventions**:

- Zero-data agent → behavioral score 0, grade F (fail-safe)
- `@dataclass` only (no Pydantic)
- Pure Python math (no numpy)
- Score clamped: `max(0, min(100, int(round(total))))`
- Behavioral is complementary, never overrides structural
- Factor names aligned with Rust's `track_record_score()` model

**Tests**: Each factor independently with known inputs. Zero-data edge case. Boundary values. Weight normalization. Combined blending. Gaming resistance (agent only does safe actions).

#### ReasoningTrace Feature Parity (bundle with G1)

**File**: `reasoning.py` (extend existing module)
**Rationale**: Python's `ReasoningTrace` exists but lacks several Rust features. Bundle with Phase 4 since both touch scoring.

Enhancements:

- Add `reasoning_completeness_score(trace, signature_verified)` function (0-100, mirrors Rust's scoring)
- Add `.redact()` → `(redacted_trace, original_hash)` and `.is_redacted()` methods
- Add `.content_hash()` → `bytes` and `.content_hash_hex()` → `str` methods to `ReasoningTrace`
- Add `EvidenceReference` dataclass (structured evidence vs current untyped dicts)

**Design constraints**:

- Completeness scoring factors aligned with Rust: trace present (30), alternatives (20), evidence (15), methodology (15), confidence calibrated (10), signature verified (10)
- Redaction uses `"[REDACTED]"` sentinel values (match Rust)
- Content hash uses SHA-256 (match Rust's `content_hash()`)
- `EvidenceReference` fields: `evidence_type: str`, `reference: str`, `summary: Optional[str]`
- Backward compatible — existing `Dict[str, Any]` evidence still accepted

**Tests**: Completeness scoring with all/partial/no fields. Redaction round-trip. Content hash determinism. EvidenceReference serialization. Backward compatibility with dict evidence.

---

### Phase 5: Production Hardening (4-5 days)

Cryptographic extensions requiring focused security attention.

#### G6: Dual-Signature on Audit Anchors

**ADR**: ADR-004 (Optional HMAC overlay)

```python
@dataclass
class DualSignature:
    ed25519_signature: bytes
    hmac_signature: Optional[bytes] = None
    hmac_algorithm: str = "sha256"
```

- HMAC optional, Ed25519-only default
- HMAC key management separate from Ed25519
- Audit records indicate signature type used
- HMAC never sufficient alone for external verification

#### G7: AWS KMS Implementation

**File**: `key_manager.py` (replace stub)

- Implement all 7 `KeyManagerInterface` methods with boto3 KMS
- `boto3` as optional dependency (`pip install eatp[aws-kms]`)
- Graceful ImportError message when boto3 not installed
- Handle KMS unreachable with fail-closed (never fall back to in-memory)
- Use ECDSA P-256 (KMS limitation — document algorithm mismatch with Ed25519)

**Tests**: End-to-end with moto (AWS mock for testing) or real AWS in CI.

---

### Phase 5b: Enterprise Readiness (3-4 days) — NEW

Enterprise-facing gaps identified by the Rust value audit. Require Phase 0 event schema and metrics convention.

#### VA1: SIEM Export (CEF/OCSF)

**Severity**: CRITICAL
**Files**: New `export/siem.py`

- Structured export for Splunk/QRadar/Sentinel
- `SecurityAuditLogger` exists but lacks standard format export
- CEF and OCSF serializers for all EATP operations
- Event schema from Phase 0 spec alignment

**Note**: SIEM export is an integration concern, not core trust protocol. Per the Rust red team's recommendation, this should live in a separate `eatp-enterprise` package or adapter module, not in the core `eatp` package. However, for Python `pip install` ergonomics, it may ship as `eatp[siem]` extra.

#### VA2: SOC 2 / ISO 27001 Evidence

**Severity**: HIGH

- Compliance artifact generation
- Map EATP operations to control objectives
- Build on existing `SecurityAuditLogger` infrastructure

#### VA3: Fleet Observability (OTel/Prometheus)

**Severity**: HIGH

- Trust health metrics for production fleets
- `eatp/metrics.py` exists but needs standard export
- OpenTelemetry metric naming from Phase 0 convention

#### Gate 5b Checklist

- [ ] SIEM events match Phase 0 event schema exactly
- [ ] CEF and OCSF formats both supported
- [ ] Metrics use Phase 0 OTel naming convention
- [ ] SOC 2 evidence maps to specific control objectives
- [ ] All export modules are optional (extras, not core deps)

---

### Phase 6: Ecosystem Alignment (1-2 days)

#### G10: Vocabulary Documentation

- EATP SDK portion: Add machine-readable vocabulary descriptions to dimension and posture modules
- Downstream: Adapter modules belong in CARE Platform or bridge package (not EATP SDK)

#### VA4: Role-Based Trust Access

**Severity**: MEDIUM

- `TrustRole` enum + guard on `TrustOperations`
- Currently all-or-nothing access to trust operations
- "Who can see what?" is a procurement question

---

## Anti-Amnesia: Pattern Reference Card

Inject into every implementation session:

```
EATP SDK Conventions:
- @dataclass for data classes (NOT Pydantic)
- ABC with @abstractmethod for extension points
- str-backed Enum for type classifications
- async module-level functions for public API
- Zero/pessimistic defaults when data missing
- Score range: int 0-100, clamped max(0, min(100, int(round(total))))
- File header: Copyright 2026 Terrene Foundation + SPDX Apache-2.0
- Explicit __all__ at end of every module
- Bounded collections: maxlen=10000, oldest-10% trim
- Error hierarchy: inherit from TrustError, .details dict
- IDs as str parameters (agent_id: str, key_id: str)
- Serialization: to_dict() method on dataclasses

Cross-SDK Alignment (D1-D6):
- Proximity defaults: 80/95 (not 70/90) — D1
- HookType: trust-native events only (4 values) — D3
- Behavioral factor names defined in spec, not per-SDK — D4
- ReasoningTrace: JSON schema, cross-MCP portable — D5
- SIEM event schema must be identical across SDKs
- Circuit breaker NOT in EATP spec (Python keeps for pragmatic reasons) — D2
- Both SDKs implement from spec, not from each other — D6
```

---

## Decisions for Human Review

### Closed by Rust Team Decisions (doc 08)

| #   | Decision             | Resolution                                                                   |
| --- | -------------------- | ---------------------------------------------------------------------------- |
| 2   | Proximity defaults   | **CLOSED**: 80/95 canonical, 70/90 conservative preset (D1)                  |
| 8   | Phase 0 investment   | **CLOSED**: YES, 2-3 days spec-only, no impl coordination (D6)               |
| 12  | Cross-SDK governance | **CLOSED**: Terrene Foundation owns spec; teams implement independently (D6) |

### Still Open (9)

| #   | Decision                           | Recommendation                                           |
| --- | ---------------------------------- | -------------------------------------------------------- |
| 1   | Structural/behavioral weight ratio | 60/40 — may be decided by spec factor definition (D4)    |
| 3   | Hook error policy                  | Fail-closed — both teams lean this way                   |
| 4   | KMS algorithm                      | Accept P-256 (Python-specific)                           |
| 5   | Threading model                    | Async-only for v0.1.x (Python-specific)                  |
| 6   | Adapter ownership                  | Vocab docs + downstream bridge                           |
| 7   | MG1/MG2 scope                      | Include MG1 in Phase 3 (core EATP spec, 0% in both SDKs) |
| 9   | SIEM priority                      | Accept as CRITICAL — enterprise SOC integration          |
| 10  | Value audit gaps scope (VA1-VA4)   | VA1-VA3 in Phase 5b; VA4 in Phase 6                      |
| 11  | Cascade revocation in Phase 3      | YES — core EATP spec requirement                         |

---

## Effort Summary

| Phase     | Gaps                           | Theme                | Effort       | Dependency                   |
| --------- | ------------------------------ | -------------------- | ------------ | ---------------------------- |
| **0**     | Shared spec (7 deliverables)   | Spec alignment       | 2-3 days     | BLOCKING (spec-only per D6)  |
| **1**     | G5/G5+, G8/G8+, G9, G11, PS1-3 | Production safety    | 3-4 days     | None (parallel with Phase 0) |
| **2**     | G2, G4                         | Core trust model     | 3 days       | Phase 0                      |
| **3**     | G3, MG1                        | Hooks + revocation   | 3-4 days     | Phase 0                      |
| **4**     | G1 + ReasoningTrace parity     | Scoring + traces     | 4 days       | Phase 0                      |
| **5**     | G6, G7                         | Production hardening | 4-5 days     | Phase 2                      |
| **5b**    | VA1, VA2, VA3                  | Enterprise readiness | 3-4 days     | Phase 0                      |
| **6**     | G10, VA4                       | Ecosystem alignment  | 1-2 days     | Phase 5b                     |
| **Total** |                                |                      | **~26 days** |                              |

---

## Documents Index

| #   | Document                          | Content                                                           |
| --- | --------------------------------- | ----------------------------------------------------------------- |
| 01  | `01-gap-details.md`               | Detailed gap descriptions G1-G6                                   |
| 02  | `02-risk-analysis.md`             | Risk register, hidden risks, dependency graph                     |
| 03  | `03-spec-alignment-evaluation.md` | Spec alignment, boundary analysis, missing gaps                   |
| 04  | `04-requirements-breakdown.md`    | Requirements, ADRs, API surfaces, tests                           |
| 05  | `05-coc-assessment.md`            | Three fault lines, anti-amnesia, quality gates                    |
| 06  | `06-synthesis.md`                 | Original synthesis (pre-Rust findings)                            |
| 07  | `07-cross-sdk-analysis.md`        | Cross-SDK comparison, boundary resolution, updated plan           |
| 08  | `08-rust-team-decisions.md`       | Rust team decisions D1-D6, impact analysis, closed/open decisions |
