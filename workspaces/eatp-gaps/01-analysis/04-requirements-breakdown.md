# EATP SDK Gaps -- Requirements Breakdown & Architecture Decision Records

**Date**: 2026-03-14
**Package**: `packages/eatp/src/eatp/` (v0.1.0, ~15,300 lines, 45 modules)
**Author**: requirements-analyst

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Requirements Breakdown (G1-G11)](#requirements-breakdown)
3. [Architecture Decision Records (ADR-001 through ADR-004)](#architecture-decision-records)
4. [Dependency Graph](#dependency-graph)
5. [Implementation Phases](#implementation-phases)
6. [Risk Assessment](#risk-assessment)

---

## Executive Summary

| Metric                    | Value                                                |
| ------------------------- | ---------------------------------------------------- |
| Total gaps                | 11                                                   |
| New modules required      | 2 (hooks, adapters)                                  |
| Existing modules modified | 7                                                    |
| Estimated total effort    | 18-24 days                                           |
| Risk level                | Medium (well-defined API surfaces, clear boundaries) |
| Backward compatibility    | Required for all changes                             |

### Priority-Ordered Summary

| Priority | Gap                                | Type         | Effort (days) | Risk   |
| -------- | ---------------------------------- | ------------ | ------------- | ------ |
| CRITICAL | G1 - Behavioral scoring            | New module   | 3             | Medium |
| CRITICAL | G2 - Proximity thresholds          | Extension    | 2             | Low    |
| CRITICAL | G3 - Lifecycle hooks               | New module   | 3-4           | Medium |
| HIGH     | G4 - Circuit breaker registry      | Extension    | 1             | Low    |
| HIGH     | G5 - ShadowEnforcer bounded memory | Fix          | 0.5           | Low    |
| HIGH     | G6 - Dual-signature                | Extension    | 2-3           | Medium |
| MEDIUM   | G7 - KMS implementation            | Replace stub | 2-3           | High   |
| MEDIUM   | G8 - Deprecated async              | Fix          | 0.5           | Low    |
| MEDIUM   | G9 - Threading lock                | Extension    | 0.5           | Low    |
| MEDIUM   | G10 - Adapters                     | New module   | 1-2           | Low    |
| LOW      | G11 - Dimension naming             | Fix          | 0.5           | Low    |

---

## Requirements Breakdown

### G1: Behavioral Trust Scoring

**Severity**: CRITICAL
**Location**: New class in `packages/eatp/src/eatp/scoring.py`

#### Functional Requirements

| ID       | Requirement                               | Input                            | Output                  | Business Logic                                  | Edge Cases                                       |
| -------- | ----------------------------------------- | -------------------------------- | ----------------------- | ----------------------------------------------- | ------------------------------------------------ |
| G1-FR-01 | Compute behavioral trust score            | agent_id, BehavioralData         | BehavioralScore (0-100) | Weighted sum of 5 behavioral factors            | Zero-data agent scores 0 (fail-safe)             |
| G1-FR-02 | Track interaction history                 | agent_id, action, outcome        | Updated history record  | Append to bounded history per agent             | First interaction; history overflow              |
| G1-FR-03 | Compute approval rate factor              | agent_id                         | float (0.0-1.0)         | approved_count / total_count                    | No interactions = 0.0                            |
| G1-FR-04 | Compute error rate factor                 | agent_id                         | float (0.0-1.0)         | 1.0 - (error_count / total_count)               | No interactions = 0.0                            |
| G1-FR-05 | Compute posture stability factor          | agent_id, PostureStateMachine    | float (0.0-1.0)         | 1.0 - (transition_count / max_transitions)      | No transitions = 1.0 (stable)                    |
| G1-FR-06 | Compute time-at-posture factor            | agent_id, PostureStateMachine    | float (0.0-1.0)         | Exponential growth toward 1.0 based on duration | Just transitioned = 0.0                          |
| G1-FR-07 | Compute combined trust score              | agent_id, store, posture_machine | CombinedTrustScore      | Weighted blend of structural + behavioral       | Missing behavioral data; missing structural data |
| G1-FR-08 | Expose behavioral breakdown in TrustScore | -                                | Dict[str, float]        | Per-factor weighted contributions               | -                                                |

#### Non-Functional Requirements

- **Thread safety**: BehavioralData storage must be thread-safe (use lock or asyncio.Lock matching G9 decision)
- **Memory**: Bounded history per agent (max 10,000 interactions, trim oldest 10%)
- **Performance**: Score computation in <1ms for typical agent (5 factors, bounded data)
- **Backward compatibility**: Existing `compute_trust_score()` signature unchanged; behavioral scoring is opt-in via new parameter or separate function

#### Acceptance Criteria

- [ ] `BehavioralScorer` class with `compute_behavioral_score(agent_id, data) -> BehavioralScore`
- [ ] Zero-data agent returns score 0, grade F
- [ ] Each factor independently testable with known inputs/outputs
- [ ] Behavioral weights are configurable (default sum to 100)
- [ ] `compute_combined_trust_score()` blends structural + behavioral with configurable ratio (default 60/40)
- [ ] Bounded history with trim-on-overflow matching PostureStateMachine pattern
- [ ] Integration test: agent with good behavior scores higher than agent with poor behavior

#### API Surface

```python
# New dataclasses
@dataclass
class BehavioralData:
    """Runtime behavioral data for an agent."""
    total_actions: int = 0
    approved_actions: int = 0
    denied_actions: int = 0
    error_count: int = 0
    posture_transitions: int = 0
    time_at_current_posture_seconds: float = 0.0
    observation_window_seconds: float = 0.0

@dataclass
class BehavioralScore:
    """Computed behavioral trust score."""
    score: int  # 0-100
    breakdown: Dict[str, float]
    grade: str
    computed_at: datetime
    agent_id: str

@dataclass
class CombinedTrustScore:
    """Combined structural + behavioral trust score."""
    overall_score: int  # 0-100
    structural_score: TrustScore
    behavioral_score: BehavioralScore
    structural_weight: float  # e.g., 0.6
    behavioral_weight: float  # e.g., 0.4
    grade: str
    computed_at: datetime
    agent_id: str

# New constants
BEHAVIORAL_WEIGHTS: Dict[str, int] = {
    "approval_rate": 30,
    "error_rate": 25,
    "posture_stability": 20,
    "time_at_posture": 15,
    "interaction_volume": 10,
}

# New functions
def compute_behavioral_score(agent_id: str, data: BehavioralData) -> BehavioralScore: ...
async def compute_combined_trust_score(
    agent_id: str,
    store: TrustStore,
    behavioral_data: Optional[BehavioralData] = None,
    posture_machine: Optional[PostureStateMachine] = None,
    structural_weight: float = 0.6,
    behavioral_weight: float = 0.4,
) -> CombinedTrustScore: ...
```

#### Test Requirements

- Unit: Each factor computation with known inputs
- Unit: Zero-data edge cases
- Unit: Boundary values (all approved, all denied, all errors)
- Unit: Weight normalization (weights sum to 100)
- Integration: Combined score blending
- Property: behavioral_score + structural_score weights = 1.0

---

### G2: Constraint Proximity Thresholds

**Severity**: CRITICAL
**Location**: `packages/eatp/src/eatp/enforce/` (new proximity scanner or extension of `StrictEnforcer`)

#### Functional Requirements

| ID       | Requirement                            | Input                      | Output                          | Business Logic                                                    | Edge Cases                                         |
| -------- | -------------------------------------- | -------------------------- | ------------------------------- | ----------------------------------------------------------------- | -------------------------------------------------- |
| G2-FR-01 | Scan constraint utilization ratios     | ConstraintCheckResult      | ProximityAlert                  | Compute used/limit ratio per dimension                            | No limit set (skip); limit is 0 (division by zero) |
| G2-FR-02 | Escalate verdict based on proximity    | ratio, thresholds          | Verdict                         | FLAG at flag_threshold, HELD at hold_threshold, BLOCKED at 1.0    | Ratio exactly at threshold boundary                |
| G2-FR-03 | Configure thresholds per dimension     | dimension_name, thresholds | -                               | Override default thresholds for specific dimensions               | Unknown dimension (use defaults)                   |
| G2-FR-04 | Integrate with StrictEnforcer.classify | VerificationResult         | Verdict (potentially escalated) | After base classification, check proximity and escalate if needed | Already BLOCKED (no further escalation)            |

#### Non-Functional Requirements

- **Performance**: Proximity check adds <0.1ms per dimension (simple ratio computation)
- **Backward compatibility**: Default thresholds produce same behavior as current code (no proximity escalation unless explicitly configured)
- **Configurability**: Per-dimension threshold overrides

#### Acceptance Criteria

- [ ] `ProximityConfig` dataclass with `flag_threshold` (default 0.70), `hold_threshold` (default 0.90)
- [ ] `ProximityScanner` class or method that accepts `Dict[str, ConstraintCheckResult]` and returns proximity alerts
- [ ] Verdict escalation: AUTO_APPROVED -> FLAGGED when ratio >= flag_threshold
- [ ] Verdict escalation: FLAGGED/AUTO_APPROVED -> HELD when ratio >= hold_threshold
- [ ] Already-BLOCKED verdicts are never downgraded
- [ ] Per-dimension threshold configuration
- [ ] Integration point in enforcement pipeline (see ADR-003)

#### API Surface

```python
@dataclass
class ProximityConfig:
    """Configuration for constraint proximity thresholds."""
    flag_threshold: float = 0.70  # Usage ratio that triggers FLAGGED
    hold_threshold: float = 0.90  # Usage ratio that triggers HELD
    # Per-dimension overrides: dimension_name -> (flag, hold)
    dimension_overrides: Dict[str, Tuple[float, float]] = field(default_factory=dict)

@dataclass
class ProximityAlert:
    """Alert generated when constraint usage approaches limits."""
    dimension: str
    usage_ratio: float
    used: float
    limit: float
    severity: Verdict  # FLAGGED or HELD based on threshold
    message: str

class ProximityScanner:
    """Scans constraint check results for proximity to limits."""
    def __init__(self, config: Optional[ProximityConfig] = None): ...
    def scan(self, results: Dict[str, ConstraintCheckResult]) -> List[ProximityAlert]: ...
    def escalate_verdict(self, base_verdict: Verdict, alerts: List[ProximityAlert]) -> Verdict: ...
```

#### Test Requirements

- Unit: Ratio computation with known used/limit values
- Unit: Threshold boundary tests (exactly at 0.70, 0.90, 1.00)
- Unit: Per-dimension overrides
- Unit: Verdict escalation logic (never downgrade BLOCKED)
- Unit: Division by zero when limit is 0
- Unit: No limit set (skip dimension)
- Integration: End-to-end with StrictEnforcer producing escalated verdicts

---

### G3: EATP Lifecycle Hooks

**Severity**: CRITICAL
**Location**: New module `packages/eatp/src/eatp/hooks.py`

#### Functional Requirements

| ID       | Requirement                     | Input                                  | Output           | Business Logic                                                               | Edge Cases                                 |
| -------- | ------------------------------- | -------------------------------------- | ---------------- | ---------------------------------------------------------------------------- | ------------------------------------------ |
| G3-FR-01 | Define hook event types         | -                                      | Enum             | PRE_TOOL_USE, POST_TOOL_USE, SUBAGENT_SPAWN, PRE_DELEGATION, POST_DELEGATION | -                                          |
| G3-FR-02 | Define hook protocol            | -                                      | Protocol/ABC     | Hooks implement `__call__(event) -> HookResult`                              | -                                          |
| G3-FR-03 | Register hooks at runtime       | hook, event_type, priority             | -                | Add to registry with priority ordering                                       | Duplicate hook name                        |
| G3-FR-04 | Unregister hooks                | hook_name                              | bool             | Remove from registry                                                         | Hook not found                             |
| G3-FR-05 | Execute hooks in priority order | event_type, context                    | List[HookResult] | Call each hook in priority order; abort on ABORT result                      | No hooks registered; hook raises exception |
| G3-FR-06 | Support abort semantics         | -                                      | -                | If any hook returns ABORT, stop execution and return abort result            | Multiple hooks, first aborts               |
| G3-FR-07 | Async-first with sync compat    | -                                      | -                | Hooks can be async or sync; registry handles both                            | Mixed async/sync hooks                     |
| G3-FR-08 | Hook context passing            | event_type, agent_id, action, metadata | HookContext      | Immutable context passed to each hook                                        | -                                          |

#### Non-Functional Requirements

- **Performance**: Hook dispatch overhead <0.5ms for 10 hooks
- **Error isolation**: A failing hook must not crash the main execution path (log error, continue or abort depending on configuration)
- **Thread safety**: Registry operations must be safe for concurrent access
- **Backward compatibility**: No changes to existing decorator-based enforcement

#### Acceptance Criteria

- [ ] `HookEventType` enum with 5 event types
- [ ] `EATPHook` protocol with `__call__` method
- [ ] `HookRegistry` with `register()`, `unregister()`, `execute()`, `list_hooks()`
- [ ] Priority ordering: lower number = higher priority (default 100)
- [ ] Abort semantics: `HookResult(action=HookAction.ABORT)` stops execution
- [ ] Error handling: hook exceptions caught, logged, configurable behavior (skip or abort)
- [ ] Both async and sync hooks supported
- [ ] Integration test: hook aborts tool use, preventing action

#### API Surface

```python
class HookEventType(str, Enum):
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    SUBAGENT_SPAWN = "subagent_spawn"
    PRE_DELEGATION = "pre_delegation"
    POST_DELEGATION = "post_delegation"

class HookAction(str, Enum):
    CONTINUE = "continue"  # Proceed with execution
    ABORT = "abort"        # Stop execution (fail-closed)
    SKIP = "skip"          # Skip this hook, continue with next

@dataclass
class HookContext:
    """Immutable context passed to hooks."""
    event_type: HookEventType
    agent_id: str
    action: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class HookResult:
    """Result returned by a hook."""
    action: HookAction = HookAction.CONTINUE
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

class EATPHook(Protocol):
    """Protocol for EATP lifecycle hooks."""
    @property
    def name(self) -> str: ...
    @property
    def event_types(self) -> List[HookEventType]: ...
    @property
    def priority(self) -> int: ...  # Lower = higher priority
    async def __call__(self, context: HookContext) -> HookResult: ...

class HookRegistry:
    def __init__(self, on_error: str = "log_and_continue"): ...
    def register(self, hook: EATPHook) -> None: ...
    def unregister(self, hook_name: str) -> bool: ...
    async def execute(self, context: HookContext) -> List[HookResult]: ...
    def list_hooks(self, event_type: Optional[HookEventType] = None) -> List[str]: ...
    def clear(self) -> None: ...
```

#### Test Requirements

- Unit: Hook registration and unregistration
- Unit: Priority ordering (hooks execute in correct order)
- Unit: Abort semantics (subsequent hooks not called after abort)
- Unit: Error handling (exception in hook does not crash pipeline)
- Unit: Async and sync hook dispatch
- Integration: Hook registry with enforcement pipeline
- Integration: PRE_TOOL_USE hook preventing tool execution

---

### G4: Per-Agent Circuit Breaker Registry

**Severity**: HIGH
**Location**: `packages/eatp/src/eatp/circuit_breaker.py`

#### Functional Requirements

| ID       | Requirement                | Input                          | Output                  | Business Logic                                    | Edge Cases                             |
| -------- | -------------------------- | ------------------------------ | ----------------------- | ------------------------------------------------- | -------------------------------------- |
| G4-FR-01 | Lazy creation of breakers  | agent_id                       | PostureCircuitBreaker   | Create on first access, reuse thereafter          | Concurrent access to same agent_id     |
| G4-FR-02 | Per-agent config overrides | agent_id, CircuitBreakerConfig | -                       | Override default config for specific agents       | Override after breaker already created |
| G4-FR-03 | Bulk status query          | -                              | Dict[str, CircuitState] | Return state of all tracked agents                | No agents tracked                      |
| G4-FR-04 | Cleanup idle breakers      | idle_threshold_seconds         | int (count removed)     | Remove breakers with no activity past threshold   | All breakers idle; threshold is 0      |
| G4-FR-05 | List agents by state       | CircuitState                   | List[str]               | Filter agents in OPEN, HALF_OPEN, or CLOSED state | No agents in requested state           |

#### Non-Functional Requirements

- **Thread safety**: Registry operations must be safe for concurrent access (matching G9 decision)
- **Memory**: Cleanup mechanism prevents unbounded growth
- **Performance**: get_or_create in <0.1ms (dict lookup + optional construction)
- **Backward compatibility**: Existing PostureCircuitBreaker unchanged

#### Acceptance Criteria

- [ ] `CircuitBreakerRegistry` class with `get_or_create(agent_id)` method
- [ ] Lazy creation: breaker created on first call, returned on subsequent calls
- [ ] Default config applied to all breakers; per-agent overrides supported
- [ ] `get_all_states()` returns dict of agent_id to CircuitState
- [ ] `cleanup_idle(threshold_seconds)` removes inactive breakers
- [ ] `get_agents_by_state(state)` filters agents
- [ ] Thread-safe operations

#### API Surface

```python
class CircuitBreakerRegistry:
    def __init__(
        self,
        posture_machine: PostureStateMachine,
        default_config: Optional[CircuitBreakerConfig] = None,
    ): ...

    def get_or_create(self, agent_id: str) -> PostureCircuitBreaker: ...
    def set_agent_config(self, agent_id: str, config: CircuitBreakerConfig) -> None: ...
    def get_all_states(self) -> Dict[str, CircuitState]: ...
    def get_agents_by_state(self, state: CircuitState) -> List[str]: ...
    def cleanup_idle(self, idle_threshold_seconds: float = 3600) -> int: ...
    def remove(self, agent_id: str) -> bool: ...
    def __len__(self) -> int: ...
    def __contains__(self, agent_id: str) -> bool: ...
```

#### Test Requirements

- Unit: Lazy creation returns same instance on subsequent calls
- Unit: Per-agent config overrides
- Unit: Bulk status query
- Unit: Idle cleanup
- Unit: Thread safety with concurrent access

---

### G5: ShadowEnforcer Bounded Memory

**Severity**: HIGH
**Location**: `packages/eatp/src/eatp/enforce/shadow.py`

#### Functional Requirements

| ID       | Requirement                  | Input                        | Output          | Business Logic                                                 | Edge Cases                                   |
| -------- | ---------------------------- | ---------------------------- | --------------- | -------------------------------------------------------------- | -------------------------------------------- |
| G5-FR-01 | Cap records list             | max_records (default 10,000) | -               | Trim oldest 10% when cap exceeded                              | Exactly at cap; far above cap                |
| G5-FR-02 | Add change_rate metric       | -                            | float (0.0-1.0) | Count decision flips / total evaluations in window             | No evaluations; all same verdict             |
| G5-FR-03 | Add fail-safe error handling | -                            | -               | try/except around shadow evaluation; errors logged, not raised | Classification throws; metrics update throws |

#### Non-Functional Requirements

- **Memory**: Hard cap at configurable maxlen (default 10,000)
- **Backward compatibility**: Existing `check()` API unchanged
- **Performance**: Trim operation is O(n) but infrequent (every ~1,000 calls)

#### Acceptance Criteria

- [ ] `_records` list capped at `max_records` (configurable in constructor)
- [ ] Trim strategy: remove oldest 10% when cap exceeded (matching PostureStateMachine)
- [ ] `change_rate` property on `ShadowMetrics` computing decision flip frequency
- [ ] `check()` wrapped in try/except -- errors logged, verdict defaults to AUTO_APPROVED
- [ ] Report includes change_rate
- [ ] Existing tests continue to pass without modification

#### API Surface

```python
class ShadowEnforcer:
    def __init__(self, flag_threshold: int = 1, max_records: int = 10_000): ...
    # check() signature unchanged

class ShadowMetrics:
    # Existing fields unchanged
    @property
    def change_rate(self) -> float: ...  # New property
```

#### Test Requirements

- Unit: Records trimmed at cap
- Unit: change_rate computation with known sequences
- Unit: Error in classification does not raise
- Unit: max_records=0 (immediate trim every call)

---

### G6: Dual-Signature on Audit Anchors

**Severity**: HIGH
**Location**: `packages/eatp/src/eatp/crypto.py` and new signer abstraction

#### Functional Requirements

| ID       | Requirement              | Input                                       | Output           | Business Logic                                       | Edge Cases                     |
| -------- | ------------------------ | ------------------------------------------- | ---------------- | ---------------------------------------------------- | ------------------------------ |
| G6-FR-01 | HMAC-SHA256 signing      | payload, key                                | signature_hex    | hmac.new(key, payload, sha256).hexdigest()           | Empty payload; empty key       |
| G6-FR-02 | HMAC-SHA256 verification | payload, signature, key                     | bool             | Constant-time comparison                             | Invalid signature format       |
| G6-FR-03 | Dual-sign operation      | payload, ed25519_key, hmac_key              | DualSignature    | Sign with both, return composite                     | HMAC key absent (Ed25519-only) |
| G6-FR-04 | Dual-verify operation    | payload, dual_sig, ed25519_pubkey, hmac_key | DualVerifyResult | Verify both; internal can use HMAC fast-path         | Only one signature present     |
| G6-FR-05 | HMAC key management      | -                                           | -                | Separate from Ed25519; stored in KeyManagerInterface | Key rotation                   |

#### Non-Functional Requirements

- **Performance**: HMAC verification <0.01ms (symmetric); Ed25519 verification <0.5ms
- **Security**: HMAC uses constant-time comparison; HMAC key separate from Ed25519 key
- **Backward compatibility**: Ed25519-only is default; HMAC is opt-in

#### Acceptance Criteria

- [ ] `hmac_sign()` and `hmac_verify()` functions in `crypto.py`
- [ ] `DualSignature` dataclass with `ed25519_signature` and optional `hmac_signature`
- [ ] `dual_sign()` and `dual_verify()` functions
- [ ] HMAC key management via `KeyManagerInterface` (new method or separate interface)
- [ ] Default behavior: Ed25519-only (backward compatible)
- [ ] Internal verification fast-path: HMAC only when both signatures present

#### API Surface

```python
@dataclass
class DualSignature:
    ed25519_signature: str  # Base64-encoded
    hmac_signature: Optional[str] = None  # Hex-encoded, optional

@dataclass
class DualVerifyResult:
    ed25519_valid: bool
    hmac_valid: Optional[bool] = None  # None if no HMAC signature
    overall_valid: bool = False

def hmac_sign(payload: str, key: bytes) -> str: ...
def hmac_verify(payload: str, signature: str, key: bytes) -> bool: ...
def dual_sign(payload: str, ed25519_private_key: str, hmac_key: Optional[bytes] = None) -> DualSignature: ...
def dual_verify(payload: str, signature: DualSignature, ed25519_public_key: str, hmac_key: Optional[bytes] = None) -> DualVerifyResult: ...
```

#### Test Requirements

- Unit: HMAC sign/verify roundtrip
- Unit: Dual sign produces both signatures when HMAC key provided
- Unit: Dual sign produces Ed25519-only when no HMAC key
- Unit: Dual verify with both signatures
- Unit: Dual verify with Ed25519-only (backward compat)
- Unit: Constant-time comparison (no timing side-channel)
- Unit: Invalid signature handling

---

### G7: AWSKMSKeyManager Implementation

**Severity**: MEDIUM
**Location**: `packages/eatp/src/eatp/key_manager.py`

#### Functional Requirements

| ID       | Requirement                | Input                          | Output                    | Business Logic                                         | Edge Cases                        |
| -------- | -------------------------- | ------------------------------ | ------------------------- | ------------------------------------------------------ | --------------------------------- |
| G7-FR-01 | Generate KMS keypair       | key_id                         | (arn, public_key)         | Create asymmetric signing key via KMS API              | Key already exists; KMS API error |
| G7-FR-02 | Sign with KMS              | payload, key_id                | signature                 | Use KMS Sign API with ECDSA_SHA_256                    | Key revoked; key not found        |
| G7-FR-03 | Verify with KMS            | payload, signature, public_key | bool                      | Local verification with public key (fast path)         | Invalid public key format         |
| G7-FR-04 | Rotate KMS key             | key_id                         | (new_arn, new_public_key) | Create new key, schedule old for deletion              | Grace period configuration        |
| G7-FR-05 | Revoke KMS key             | key_id                         | -                         | Schedule key deletion with configurable pending window | Already revoked                   |
| G7-FR-06 | List and describe KMS keys | active_only                    | List[KeyMetadata]         | Paginated KMS list with describe                       | No keys; pagination               |

#### Non-Functional Requirements

- **Dependencies**: `boto3` as optional dependency (not required for non-AWS users)
- **Error handling**: KMS API errors wrapped in `KeyManagerError` with actionable messages
- **Security**: No credential storage; relies on AWS credential chain
- **Testing**: Mocked KMS client for unit tests; real KMS for integration tests (Tier 2)

#### Acceptance Criteria

- [ ] `AWSKMSKeyManager` implements all `KeyManagerInterface` methods
- [ ] `boto3` imported lazily (no import error if not installed)
- [ ] `KMS_KEY_SPEC = "ECC_NIST_P256"` (Ed25519 not supported by KMS)
- [ ] Algorithm mapping: Ed25519 (local) vs ECDSA_SHA_256 (KMS) documented
- [ ] `pending_deletion_days` configurable (default 7)
- [ ] All KMS errors wrapped in `KeyManagerError`
- [ ] Graceful fallback when boto3 not installed (raise ImportError with clear message)

#### API Surface

```python
class AWSKMSKeyManager(KeyManagerInterface):
    def __init__(
        self,
        kms_client: Optional[Any] = None,  # boto3 KMS client
        region_name: Optional[str] = None,
        pending_deletion_days: int = 7,
    ): ...
    # All KeyManagerInterface methods implemented
```

#### Test Requirements

- Unit: All methods with mocked boto3 client
- Unit: boto3 not installed raises clear ImportError
- Unit: KMS error wrapping
- Integration (Tier 2): Real KMS key lifecycle (create, sign, verify, rotate, revoke)

---

### G8: Deprecated `get_event_loop()` Fix

**Severity**: MEDIUM
**Location**: `packages/eatp/src/eatp/enforce/decorators.py`

#### Functional Requirements

| ID       | Requirement                               | Input | Output | Business Logic                                | Edge Cases                                        |
| -------- | ----------------------------------------- | ----- | ------ | --------------------------------------------- | ------------------------------------------------- |
| G8-FR-01 | Replace get_event_loop() in sync wrappers | -     | -      | Use asyncio.run() or new event loop creation  | Called from within existing event loop            |
| G8-FR-02 | Handle nested event loop scenarios        | -     | -      | Detect running loop, use appropriate strategy | FastAPI/Django async context calling sync wrapper |

#### Non-Functional Requirements

- **Python compatibility**: Must work on Python 3.10, 3.11, 3.12, 3.13
- **No new dependencies**: Do not add `nest_asyncio` or similar
- **Backward compatibility**: Decorated functions behave identically

#### Acceptance Criteria

- [ ] No `asyncio.get_event_loop()` calls in production code
- [ ] Sync wrappers use `asyncio.run()` when no loop is running
- [ ] When a loop IS running, raise a clear error message directing users to use the async version
- [ ] No DeprecationWarning on Python 3.12+
- [ ] All existing decorator tests pass

#### API Surface

No API changes. Internal implementation fix only.

#### Test Requirements

- Unit: Sync decorator works without running event loop (asyncio.run path)
- Unit: Sync decorator raises clear error when event loop already running
- Unit: No DeprecationWarning emitted on Python 3.12+
- Unit: Async decorator unchanged

---

### G9: Threading Lock for Circuit Breaker

**Severity**: MEDIUM
**Location**: `packages/eatp/src/eatp/circuit_breaker.py`

#### Functional Requirements

| ID       | Requirement                         | Input                 | Output | Business Logic                                                     | Edge Cases                  |
| -------- | ----------------------------------- | --------------------- | ------ | ------------------------------------------------------------------ | --------------------------- |
| G9-FR-01 | Support threading.Lock mode         | lock_mode="threading" | -      | Use threading.Lock instead of asyncio.Lock                         | Mixed async/threaded access |
| G9-FR-02 | Support asyncio.Lock mode (default) | lock_mode="asyncio"   | -      | Keep current behavior                                              | -                           |
| G9-FR-03 | Auto-detect mode                    | -                     | -      | If running in async context, use asyncio.Lock; else threading.Lock | Detection accuracy          |

#### Non-Functional Requirements

- **Thread safety**: threading.Lock mode must be safe for multi-threaded access
- **Backward compatibility**: Default behavior unchanged (asyncio.Lock)
- **Documentation**: Clear documentation on when to use which mode

#### Acceptance Criteria

- [ ] `PostureCircuitBreaker.__init__` accepts optional `lock_mode` parameter
- [ ] `lock_mode="asyncio"` (default) uses `asyncio.Lock` -- current behavior
- [ ] `lock_mode="threading"` uses `threading.Lock` with sync method variants
- [ ] time.monotonic() used instead of datetime for duration checks in threading mode
- [ ] Existing async tests pass unchanged

#### API Surface

```python
class PostureCircuitBreaker:
    def __init__(
        self,
        posture_machine: PostureStateMachine,
        config: Optional[CircuitBreakerConfig] = None,
        lock_mode: str = "asyncio",  # "asyncio" or "threading"
    ): ...
```

#### Test Requirements

- Unit: asyncio.Lock mode (existing tests)
- Unit: threading.Lock mode with concurrent threads
- Unit: Invalid lock_mode raises ValueError

---

### G10: Posture/Constraint Dimension Adapter Modules

**Severity**: MEDIUM
**Location**: New module `packages/eatp/src/eatp/adapters.py`

#### Functional Requirements

| ID        | Requirement                                      | Input               | Output                   | Business Logic                                 | Edge Cases                 |
| --------- | ------------------------------------------------ | ------------------- | ------------------------ | ---------------------------------------------- | -------------------------- |
| G10-FR-01 | Map CARE posture labels to EATP TrustPosture     | care_label (str)    | TrustPosture             | Bidirectional canonical mapping                | Unknown label              |
| G10-FR-02 | Map CARE dimension names to EATP dimension names | care_name (str)     | eatp_name (str)          | Bidirectional mapping with safe defaults       | Unknown name (passthrough) |
| G10-FR-03 | Provide safe conversion defaults                 | unknown_label       | default_value            | Return configurable default instead of raising | -                          |
| G10-FR-04 | Bulk conversion                                  | Dict of CARE labels | Dict of EATP equivalents | Convert all keys/values in a dict              | Mixed known/unknown        |

#### Non-Functional Requirements

- **No external dependencies**: Pure Python mapping
- **Extensibility**: Custom mappings can be registered
- **Backward compatibility**: No changes to existing modules

#### Acceptance Criteria

- [ ] `PostureAdapter` with `to_eatp(care_label) -> TrustPosture` and `from_eatp(posture) -> str`
- [ ] `DimensionAdapter` with `to_eatp(care_name) -> str` and `from_eatp(eatp_name) -> str`
- [ ] Unknown labels return configurable default (not raise)
- [ ] Bulk conversion method for dictionaries
- [ ] All CARE posture labels and dimension names documented in mapping

#### API Surface

```python
class PostureAdapter:
    # Default mapping: CARE -> EATP
    CARE_TO_EATP: Dict[str, TrustPosture] = { ... }
    EATP_TO_CARE: Dict[TrustPosture, str] = { ... }

    def to_eatp(self, care_label: str, default: Optional[TrustPosture] = None) -> TrustPosture: ...
    def from_eatp(self, posture: TrustPosture, default: Optional[str] = None) -> str: ...

class DimensionAdapter:
    CARE_TO_EATP: Dict[str, str] = { ... }
    EATP_TO_CARE: Dict[str, str] = { ... }

    def to_eatp(self, care_name: str, default: Optional[str] = None) -> str: ...
    def from_eatp(self, eatp_name: str, default: Optional[str] = None) -> str: ...
    def convert_constraints(self, care_constraints: Dict[str, Any]) -> Dict[str, Any]: ...
```

#### Test Requirements

- Unit: All known mappings roundtrip correctly
- Unit: Unknown label with default
- Unit: Unknown label without default raises ValueError
- Unit: Bulk conversion with mixed known/unknown

---

### G11: Built-In Dimension Registry Naming

**Severity**: LOW
**Location**: `packages/eatp/src/eatp/constraints/dimension.py`

#### Functional Requirements

| ID        | Requirement                    | Input              | Output   | Business Logic                                                 | Edge Cases                          |
| --------- | ------------------------------ | ------------------ | -------- | -------------------------------------------------------------- | ----------------------------------- |
| G11-FR-01 | Align BUILTIN_DIMENSIONS names | -                  | Set[str] | Update names to match CARE canonical vocabulary or add aliases | Existing code referencing old names |
| G11-FR-02 | Add alias support              | old_name, new_name | -        | Accept both old and new names for backward compat              | -                                   |

#### Non-Functional Requirements

- **Backward compatibility**: Old dimension names must continue to work
- **Documentation**: Mapping between old and new names documented

#### Acceptance Criteria

- [ ] `BUILTIN_DIMENSIONS` set updated or alias mechanism added
- [ ] Old names still work (backward compat)
- [ ] Dimension registry `.get()` accepts both old and new names
- [ ] G10 adapters use the aligned names

#### API Surface

```python
class ConstraintDimensionRegistry:
    BUILTIN_DIMENSIONS: Set[str] = { ... }  # Updated or aliased
    # Optional: add alias support
    def register_alias(self, alias: str, canonical: str) -> None: ...
```

#### Test Requirements

- Unit: Old names still resolve
- Unit: New/canonical names resolve
- Unit: Alias registration and lookup

---

## Architecture Decision Records

### ADR-001: Behavioral Scoring Model

**Status**: Proposed

#### Context

The EATP SDK currently computes trust scores using only structural factors (chain completeness, delegation depth, constraint coverage, posture level, chain recency). These factors describe the quality of the trust chain but say nothing about how the agent actually behaves at runtime.

Behavioral scoring evaluates agents based on their runtime track record: approval rate, error rate, posture stability, and time-at-posture. The question is how behavioral scoring relates to the existing structural scoring.

Three integration models are possible:

1. **Complementary** (separate scores, combined optionally)
2. **Combined** (single score with both structural and behavioral factors)
3. **Replacement** (behavioral replaces structural)

#### Decision

**Complementary model with optional combination**.

Behavioral scoring is implemented as a separate `BehavioralScorer` class that produces an independent `BehavioralScore`. A `compute_combined_trust_score()` function blends both scores with configurable weights (default 60% structural, 40% behavioral).

Rationale:

- **Separation of concerns**: Structural scoring is deterministic from chain data. Behavioral scoring requires runtime data. They have different data sources, update frequencies, and failure modes.
- **Incremental adoption**: Existing consumers of `compute_trust_score()` are unaffected. Behavioral scoring is opt-in.
- **Diagnostic clarity**: When investigating trust decisions, operators can see which component (structural or behavioral) drove the score.
- **Zero-data safety**: A new agent with no behavioral history gets behavioral_score=0. In the combined model, the structural score still provides a baseline. In the replacement model, the agent would have zero trust despite a perfect chain.
- **Weight tuning**: Different deployments can weight structural vs behavioral differently. An organization just starting with EATP might use 90/10; a mature deployment might use 50/50.

#### Consequences

**Positive**:

- Existing `compute_trust_score()` API unchanged
- Clear mental model: chain quality vs agent behavior
- Configurable blend supports diverse deployment scenarios
- Independent testing and validation of each scorer

**Negative**:

- Two score types to explain to users (vs one combined number)
- `CombinedTrustScore` dataclass adds API surface
- Consumers must decide whether to use structural, behavioral, or combined

#### Alternatives Considered

**Option A: Combined Model (single function, 11 factors)**

- Pros: Single score, single API
- Cons: Mixes static and dynamic factors; zero behavioral data drags down score of well-structured chains; harder to debug; breaks backward compat of TrustScore breakdown
- Rejected: Breaking backward compatibility and mixing concerns

**Option B: Replacement Model (behavioral replaces structural)**

- Pros: Simplest API
- Cons: Loses chain quality information entirely; new agents with no history have zero trust
- Rejected: Violates fail-safe principle; loses valuable structural information

---

### ADR-002: Hook System Design

**Status**: Proposed

#### Context

The EATP SDK needs an extensibility mechanism for intercepting agent lifecycle events (tool use, sub-agent spawning, delegation) without modifying the functions being intercepted. Three approaches are viable:

1. **Protocol-based**: Python Protocol defining the hook interface
2. **Event bus**: Pub-sub event system with event types and handlers
3. **Decorator extension**: Extend existing `@verified`/`@audited` decorators with hook points

#### Decision

**Protocol-based hook system with a priority-ordered registry**.

Hooks implement the `EATPHook` Protocol with a `name`, `event_types`, `priority`, and `__call__` method. A `HookRegistry` manages registration, ordering, and execution.

Rationale:

- **Type safety**: Protocol gives IDE support and type checking without inheritance burden
- **Priority ordering**: Critical security hooks (low number) execute before optional logging hooks (high number)
- **Abort semantics**: Any hook can return `ABORT` to fail-closed, matching EATP security posture
- **Composability**: Hooks layer independently with decorators -- they are complementary, not competing
- **Framework integration**: Kaizen can implement concrete hooks (e.g., `KaizenToolUseHook`) that plug into the registry without EATP knowing about Kaizen
- **Testing**: Each hook is independently testable; the registry is independently testable

#### Consequences

**Positive**:

- Clean separation: EATP defines protocol, frameworks implement
- Priority ordering enables security-first execution
- Abort semantics support fail-closed trust model
- No coupling to specific frameworks (Kaizen, CARE)
- Async-first with sync compatibility via `asyncio.iscoroutinefunction`

**Negative**:

- New module and API surface to maintain
- Developers must understand hook priority and abort semantics
- Performance overhead of dispatching through hook chain (mitigated by design: <0.5ms for 10 hooks)

#### Alternatives Considered

**Option A: Event Bus (pub-sub)**

- Pros: Familiar pattern; decoupled publishers and subscribers
- Cons: No priority ordering; no abort semantics (pub-sub is fire-and-forget); harder to reason about execution order; does not support fail-closed
- Rejected: Lack of abort semantics violates EATP fail-closed requirement

**Option B: Decorator Extension (add hook points to @verified/@audited)**

- Pros: Reuses existing pattern; minimal new API
- Cons: Hooks tied to decorated functions (no interception of undecorated code); cannot intercept sub-agent spawning (not a function call pattern); no standalone hook execution
- Rejected: Does not address the core need (intercepting agent runtime events independently of decorated functions)

---

### ADR-003: Proximity Threshold Integration Point

**Status**: Proposed

#### Context

Constraint proximity thresholds (G2) detect when an agent's constraint usage approaches limits and escalate the enforcement verdict (e.g., AUTO_APPROVED to FLAGGED at 70% utilization). The question is where in the enforcement pipeline this scanning occurs:

1. **Enforcement layer** (in StrictEnforcer.classify or a wrapper)
2. **Constraint evaluator** (in MultiDimensionEvaluator.evaluate)
3. **Standalone scanner** (separate module consulted by either layer)

#### Decision

**Standalone ProximityScanner consumed by the enforcement layer**.

The `ProximityScanner` is a standalone class that accepts `Dict[str, ConstraintCheckResult]` and returns `List[ProximityAlert]`. The enforcement layer (StrictEnforcer or its wrapper) calls the scanner after constraint evaluation and uses the alerts to potentially escalate the verdict.

Rationale:

- **Single responsibility**: The constraint evaluator checks if constraints are satisfied. The proximity scanner checks how close to limits. These are distinct concerns.
- **Reusability**: The scanner can be used by StrictEnforcer, ShadowEnforcer, and any custom enforcer independently.
- **Configurability**: ProximityConfig is independent of evaluator configuration.
- **Testing**: Scanner is independently testable with synthetic ConstraintCheckResult data.
- **Existing anti-gaming**: The MultiDimensionEvaluator already has anti-gaming detection at 0.95. Proximity thresholds at 0.70 and 0.90 are enforcement-level concerns (what verdict to assign), not evaluation-level concerns (is the constraint satisfied). Keeping them separate avoids conflating these.

Integration point:

```
ConstraintEvaluator.evaluate()
    |
    v
ConstraintCheckResults (per dimension: satisfied, used, limit, remaining)
    |
    v
ProximityScanner.scan(results) -> List[ProximityAlert]
    |
    v
StrictEnforcer.classify(result) -> base Verdict
    |
    v
ProximityScanner.escalate_verdict(base_verdict, alerts) -> final Verdict
```

#### Consequences

**Positive**:

- Clean separation of evaluation, proximity detection, and enforcement
- Reusable across all enforcer types
- Independently configurable thresholds
- No modification to MultiDimensionEvaluator internals
- Testable in isolation

**Negative**:

- One additional class in the pipeline
- Enforcement must explicitly wire the scanner (not automatic)
- Risk of users forgetting to wire proximity scanning

#### Alternatives Considered

**Option A: Integration in MultiDimensionEvaluator**

- Pros: Automatic for all evaluations; single configuration point
- Cons: Mixes evaluation (is constraint satisfied?) with enforcement (what verdict?); EvaluationResult would need verdict concepts; evaluator becomes aware of enforcement semantics
- Rejected: Violates separation between evaluation and enforcement layers

**Option B: Integration in StrictEnforcer.classify directly**

- Pros: Automatic for strict enforcement; one call
- Cons: classify() currently takes VerificationResult (no constraint details); would need to change signature or add state; not reusable by ShadowEnforcer
- Rejected: Would require breaking the classify() API and not reusable across enforcers

---

### ADR-004: Dual-Signature Approach

**Status**: Proposed

#### Context

The EATP architecture describes dual signing for audit anchors: HMAC-SHA256 for fast internal verification and Ed25519 for external non-repudiation. The question is how to add HMAC support:

1. **Optional HMAC overlay**: Add HMAC functions alongside existing Ed25519, combine in DualSignature
2. **Pluggable signer interface**: Abstract signer protocol with Ed25519 and HMAC implementations
3. **AuditAnchor-level integration**: Modify AuditAnchor to carry both signatures

#### Decision

**Optional HMAC overlay with DualSignature dataclass**.

Add `hmac_sign()` and `hmac_verify()` to `crypto.py`, plus `dual_sign()` and `dual_verify()` convenience functions that produce/consume a `DualSignature` dataclass. HMAC is always optional (Ed25519-only by default).

Rationale:

- **Simplicity**: HMAC functions are 5-10 lines each. No need for a pluggable interface when there are exactly two algorithms.
- **Opt-in**: Default behavior is unchanged. HMAC only produced when an HMAC key is provided.
- **Performance**: Internal verification uses HMAC fast-path (~100x faster than Ed25519 verify). External verification uses Ed25519 for non-repudiation.
- **Key separation**: HMAC key (symmetric) and Ed25519 key (asymmetric) are fundamentally different. Keeping them separate is clearer than a generic signer interface that would abstract away this distinction.
- **Composition**: `DualSignature` dataclass is serializable and can be stored in audit anchors without changing the AuditAnchor schema (store as metadata or extend).

#### Consequences

**Positive**:

- Minimal code addition (~50 lines)
- No new abstractions or interfaces
- Backward compatible (HMAC is opt-in)
- Clear performance path for internal vs external verification
- DualSignature is a simple dataclass, easy to serialize

**Negative**:

- Only two algorithms supported (HMAC-SHA256 + Ed25519). If a third is needed, a pluggable interface may be warranted.
- HMAC key management is separate from Ed25519 key management (two key stores)
- DualSignature dataclass adds to API surface

#### Alternatives Considered

**Option A: Pluggable Signer Interface**

- Pros: Supports arbitrary algorithms; extensible
- Cons: Over-engineering for two known algorithms; introduces interface/protocol overhead; abstracts away the fundamental symmetric/asymmetric distinction; makes it less clear which algorithm provides which security property
- Rejected: YAGNI -- two algorithms are well-defined; pluggable interface adds complexity without benefit

**Option B: AuditAnchor-Level Integration**

- Pros: Signatures live directly on AuditAnchor; no separate dataclass
- Cons: Requires modifying AuditAnchor schema (breaking change); couples signing strategy to data model; not usable for non-audit signing
- Rejected: Modifying AuditAnchor is a breaking change; dual signing may be used beyond audit anchors

---

## Dependency Graph

```
G11 (dimension naming)
 |
 v
G10 (adapters) --uses--> G11 names

G8 (deprecated async) -- independent, no dependencies
G9 (threading lock) -- independent, no dependencies

G5 (shadow memory) -- independent, no dependencies

G7 (KMS stub) -- independent, depends on KeyManagerInterface (already exists)

G2 (proximity thresholds) --depends-on--> ConstraintCheckResult (already exists)
 |
 v
G3 (lifecycle hooks) --can-use--> G2 (hooks can trigger proximity scans)

G4 (circuit breaker registry) --depends-on--> PostureCircuitBreaker (already exists)
                               --depends-on--> G9 (threading safety, if implemented first)

G1 (behavioral scoring) --depends-on--> PostureStateMachine (already exists)
                         --benefits-from--> G3 (hooks can feed behavioral data)

G6 (dual-signature) --depends-on--> crypto.py (already exists)
                     --benefits-from--> G7 (KMS can manage HMAC keys)
```

### Direct Dependencies (must be done first)

| Gap | Hard Dependencies                   | Soft Dependencies (benefits from) |
| --- | ----------------------------------- | --------------------------------- |
| G1  | None (PostureStateMachine exists)   | G3 (hooks feed behavioral data)   |
| G2  | None (ConstraintCheckResult exists) | None                              |
| G3  | None                                | G2 (proximity can be a hook)      |
| G4  | None (PostureCircuitBreaker exists) | G9 (threading safety)             |
| G5  | None                                | None                              |
| G6  | None (crypto.py exists)             | G7 (KMS for HMAC keys)            |
| G7  | None (KeyManagerInterface exists)   | None                              |
| G8  | None                                | None                              |
| G9  | None                                | None                              |
| G10 | G11 (naming alignment)              | None                              |
| G11 | None                                | None                              |

---

## Implementation Phases

### Phase 1: Quick Wins & Foundations (4-5 days)

Fix low-effort issues that unblock later work or have immediate production impact.

| Day | Gap | Description                                | Output                                  |
| --- | --- | ------------------------------------------ | --------------------------------------- |
| 1   | G5  | ShadowEnforcer bounded memory              | Modified `shadow.py`, add `change_rate` |
| 1   | G8  | Fix deprecated `get_event_loop()`          | Modified `decorators.py`                |
| 2   | G9  | Add threading.Lock mode to circuit breaker | Modified `circuit_breaker.py`           |
| 2   | G11 | Align dimension naming                     | Modified `dimension.py`                 |
| 3   | G4  | Per-agent circuit breaker registry         | Extended `circuit_breaker.py`           |
| 4-5 | G2  | Proximity threshold scanner                | New `ProximityScanner` class            |

**Gate**: All existing tests pass + new tests for modified modules.

### Phase 2: Core New Capabilities (6-8 days)

Build the two new major modules and the scoring extension.

| Day   | Gap | Description            | Output                                |
| ----- | --- | ---------------------- | ------------------------------------- |
| 6-8   | G3  | Lifecycle hooks system | New `hooks.py` module                 |
| 9-11  | G1  | Behavioral scoring     | Extended `scoring.py`                 |
| 12-13 | G6  | Dual-signature support | Extended `crypto.py`, new dataclasses |

**Gate**: Full test suite passes + new feature tests + integration tests between hooks and enforcement.

### Phase 3: Production Readiness & Ecosystem (5-7 days)

Production backends and cross-system integration.

| Day   | Gap | Description                                | Output                            |
| ----- | --- | ------------------------------------------ | --------------------------------- |
| 14-16 | G7  | AWS KMS implementation                     | Replaced stub in `key_manager.py` |
| 17-18 | G10 | Adapter modules                            | New `adapters.py` module          |
| 19-20 | -   | Integration testing, documentation, review | Cross-module integration tests    |

**Gate**: Full test suite + KMS integration tests (Tier 2) + documentation review.

### Phase Summary

| Phase | Gaps                    | Effort   | Risk              | Dependencies Met                  |
| ----- | ----------------------- | -------- | ----------------- | --------------------------------- |
| 1     | G5, G8, G9, G11, G4, G2 | 4-5 days | Low               | Foundations for G3, G4            |
| 2     | G3, G1, G6              | 6-8 days | Medium            | G9 done for G4; G2 done for hooks |
| 3     | G7, G10                 | 5-7 days | Medium-High (KMS) | G11 done for G10                  |

---

## Risk Assessment

### High Probability, High Impact (Critical)

1. **G7: AWS KMS API version drift**
   - Risk: KMS API may have changed since last documentation; boto3 version compatibility
   - Mitigation: Research current KMS API before implementation; pin boto3 version range
   - Prevention: Integration tests against real KMS (Tier 2)

2. **G1: Behavioral score gaming**
   - Risk: Agents could artificially inflate behavioral scores by performing many low-risk actions
   - Mitigation: Interaction volume factor has lowest weight (10%); anti-gaming detection in evaluator already exists
   - Prevention: Document in security considerations; add anomaly detection in future iteration

### Medium Probability, Medium Impact (Monitor)

3. **G3: Hook execution overhead in hot paths**
   - Risk: Hook dispatch adds latency to every tool call
   - Mitigation: Priority ordering lets critical hooks run first; CONTINUE hooks are near-zero overhead
   - Prevention: Benchmark hook dispatch; document performance characteristics

4. **G6: HMAC key distribution**
   - Risk: HMAC keys must be shared between internal parties; distribution mechanism not specified
   - Mitigation: HMAC is opt-in; organizations can use existing key distribution
   - Prevention: Document key distribution requirements clearly

5. **G9: Mixed async/threading modes**
   - Risk: Users configure wrong lock mode for their runtime, causing deadlocks or race conditions
   - Mitigation: Default to asyncio.Lock (most common EATP usage); document clearly
   - Prevention: Validate lock mode against runtime context where possible

### Low Probability, Low Impact (Accept)

6. **G10: CARE vocabulary changes**
   - Risk: CARE canonical names change after adapters are built
   - Mitigation: Adapters have configurable mappings
   - Prevention: Version the mapping; document CARE spec version it targets

7. **G11: Old dimension names in serialized data**
   - Risk: Previously serialized data uses old names
   - Mitigation: Alias support ensures both old and new names work
   - Prevention: Never remove old names, only add aliases

---

## Success Criteria

- [ ] All 11 gaps implemented with no stubs or TODOs
- [ ] All existing tests pass without modification (backward compatibility)
- [ ] Each gap has dedicated test coverage (unit + integration where applicable)
- [ ] No `asyncio.get_event_loop()` in production code (G8)
- [ ] No unbounded lists in production code (G5)
- [ ] No `raise NotImplementedError` in production code (G7)
- [ ] ADR decisions implemented as specified
- [ ] Performance: behavioral scoring <1ms, proximity scanning <0.1ms/dimension, hook dispatch <0.5ms for 10 hooks
- [ ] Thread safety: circuit breaker registry and hook registry safe for concurrent access
- [ ] Documentation: all new public APIs have docstrings with examples
