# Trust Plane -- Posture, Budget, Stores, and Audit

Parent domain: Kailash Trust Plane. This sub-spec covers the TrustPosture state machine, BudgetTracker, PostureStore, the audit store (SPEC-08), and audit anchors. See `trust-eatp.md` for the EATP protocol, trust chain data structures, constraint envelopes, and delegation. See `trust-crypto.md` for Ed25519 signing, AES-256-GCM encryption, store backends, RBAC, and interop.

---

## 5. TrustPosture

### 5.1 Posture Levels

Five graduated trust postures per EATP Decision 007:

| Posture      | Autonomy Level | Description                                            |
| ------------ | -------------- | ------------------------------------------------------ |
| `AUTONOMOUS` | 5              | Agent operates with full autonomy; remote monitoring   |
| `DELEGATING` | 4              | Agent executes, human monitors in real-time            |
| `SUPERVISED` | 3              | Agent proposes actions, human approves each one        |
| `TOOL`       | 2              | Human and agent co-plan; agent executes approved plans |
| `PSEUDO`     | 1              | Agent is interface only; human performs all reasoning  |

Backward-compatible aliases are accepted: `DELEGATED` -> `AUTONOMOUS`, `CONTINUOUS_INSIGHT` -> `DELEGATING`, `SHARED_PLANNING` -> `SUPERVISED`, `PSEUDO_AGENT` -> `PSEUDO`. These resolve via `_missing_()` for serialized data compatibility.

Postures support comparison operators (`<`, `<=`, `>`, `>=`) based on autonomy level.

### 5.2 PostureStateMachine

Manages posture transitions with guard-based validation.

```python
class PostureStateMachine:
    def transition(self, request: PostureTransitionRequest) -> TransitionResult
    def add_guard(self, guard: TransitionGuard) -> None
```

**Transition types**: `UPGRADE`, `DOWNGRADE`, `MAINTAIN`, `EMERGENCY_DOWNGRADE`.

**Guards**: `TransitionGuard` objects validate transitions. Each guard has a `check_fn`, an `applies_to` list of transition types, and a `reason_on_failure`. If any guard returns `False`, the transition is blocked and the result includes `blocked_by` with the guard name.

### 5.3 PostureEvidence

Quantitative evidence supporting posture transition decisions:

```python
@dataclass
class PostureEvidence:
    observation_count: int
    success_rate: float           # 0.0 to 1.0, validated finite
    time_at_current_posture_hours: float
    anomaly_count: int
    source: str
```

All numeric fields are validated for finiteness and non-negativity.

### 5.4 PostureConstraints

Configurable thresholds for automatic posture transitions:

- `min_observation_count`: Minimum observations before upgrade allowed
- `min_success_rate`: Minimum success rate for upgrade
- `min_time_at_posture_hours`: Minimum time at current posture before upgrade
- `max_anomaly_count`: Maximum anomalies before downgrade triggered
- `max_anomaly_rate`: Maximum anomaly rate threshold

---

## 6. BudgetTracker

Located in `kailash.trust.constraints.budget_tracker`. Thread-safe atomic budget accounting with two-phase reserve/record semantics.

### 6.1 Architecture

Uses integer **microdollars** (1 USD = 1,000,000 microdollars) to avoid floating-point precision issues. All operations are guarded by `threading.Lock`.

### 6.2 Two-Phase Protocol

```python
# Phase 1: Reserve before work
if tracker.reserve(estimated_cost_microdollars):
    # Phase 2: Do work, then record actual cost
    tracker.record(
        reserved_microdollars=estimated_cost,
        actual_microdollars=real_cost,
    )
```

### 6.3 API

| Method                     | Purpose                                             | Thread-safe | Mutates state        |
| -------------------------- | --------------------------------------------------- | ----------- | -------------------- |
| `reserve(microdollars)`    | Reserve budget; returns `bool`                      | Yes         | Yes                  |
| `record(reserved, actual)` | Finalize reservation with actual cost               | Yes         | Yes                  |
| `remaining_microdollars()` | Query remaining budget                              | Yes         | No                   |
| `check(estimated)`         | Non-mutating fit check; returns `BudgetCheckResult` | Yes         | No                   |
| `snapshot()`               | Capture serializable state                          | Yes         | No                   |
| `from_snapshot(snapshot)`  | Restore from serialized state                       | N/A         | N/A                  |
| `on_threshold(callback)`   | Register threshold callback                         | No          | Yes (callbacks list) |
| `on_record(callback)`      | Register post-record callback                       | No          | Yes (callbacks list) |

### 6.4 Contracts

- **Fail-closed**: Invalid input (negative, non-integer) to `reserve()` returns `False`. Invalid input to `record()` raises `BudgetTrackerError`.
- **Saturating arithmetic**: `_reserved` never goes below 0. `_committed` can exceed `_allocated` to track real overspend.
- **Safe direction**: Between the two atomic operations in `record()`, `remaining()` briefly over-reports. This may allow a reservation that would be denied (safe) but never denies one that should be allowed.
- **Threshold callbacks**: Fire at 80%, 95%, and 100% utilization. Each threshold fires at most once. Callbacks execute OUTSIDE the lock to prevent deadlock.
- **Bounded transaction log**: `deque(maxlen=10_000)` per EATP bounded collection rules.
- **Persistence**: Optional `BudgetStore` for auto-save after each `record()`. Snapshots exclude in-flight reservations (they are transient).

### 6.5 Conversion Helpers

```python
usd_to_microdollars(1.50)   # -> 1_500_000
microdollars_to_usd(1_500_000)  # -> 1.50
```

`usd_to_microdollars` validates finiteness; NaN/Inf raises `BudgetTrackerError`.

---

## 7. PostureStore

### 7.1 SQLitePostureStore

Located in `kailash.trust.posture.posture_store`. Persistent storage for agent posture state and transition history.

**API**:

| Method                           | Purpose                                                 |
| -------------------------------- | ------------------------------------------------------- |
| `get_posture(agent_id)`          | Get current posture (default: SUPERVISED)               |
| `set_posture(agent_id, posture)` | Upsert current posture                                  |
| `record_transition(result)`      | Persist transition in history                           |
| `get_history(agent_id, limit)`   | Get transition history (newest first, capped at 10,000) |

**Security properties**:

- Path traversal protection on `db_path` (rejects `..`, null bytes, symlinks)
- File permissions `0o600` on POSIX
- WAL journal mode for concurrent reads
- All queries parameterized (`?` placeholders)
- Agent ID validation: `^[a-zA-Z0-9_-]+$`
- History queries bounded to max 10,000 rows

**Schema** (auto-migrated):

- `postures` table: `agent_id TEXT PRIMARY KEY, posture TEXT, updated_at TEXT`
- `transitions` table: `id INTEGER PRIMARY KEY, agent_id TEXT, from_posture TEXT, to_posture TEXT, success INTEGER, timestamp TEXT, metadata TEXT, transition_type TEXT`

---

## 8. Audit Store (SPEC-08)

### 8.1 Canonical Audit Store

Located in `kailash.trust.audit_store`. Consolidates 5+ scattered audit implementations into one canonical module.

**Core type**:

```python
@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    event_type: AuditEventType
    actor: str
    action: str
    resource: str
    outcome: AuditOutcome
    timestamp: datetime
    parent_anchor_id: str | None
    metadata: Dict[str, Any]
    hash: str                # SHA-256 Merkle chain link
```

**Event types** (`AuditEventType`): `DECISION`, `EXECUTION`, `DELEGATION`, `VERIFICATION`, `ESCALATION`, `INTERVENTION`, `CONSTRAINT_CHECK`, `POSTURE_CHANGE`, `BUDGET_EVENT`, `SYSTEM`.

**Outcomes** (`AuditOutcome`): `SUCCESS`, `FAILURE`, `DENIED`, `PARTIAL`, `PENDING`, `SKIPPED`.

### 8.2 Store Protocol

```python
@runtime_checkable
class AuditStoreProtocol(Protocol):
    async def append(self, event: AuditEvent) -> str
    async def get(self, event_id: str) -> AuditEvent
    async def query(self, filter: AuditFilter) -> list[AuditEvent]
    async def verify_chain(self) -> bool
    async def count(self, filter: AuditFilter | None = None) -> int
```

### 8.3 Implementations

- **InMemoryAuditStore**: `deque(maxlen=10_000)` with oldest-10% eviction. For testing and Level 0.
- **SqliteAuditStore**: Persistent store using `AsyncSQLitePool`.

### 8.4 Hash Chain

Every event is linked to the previous via SHA-256: `hash(event_data + prev_hash)`. The genesis sentinel is `"0" * 64`. Hash comparisons use `hmac.compare_digest()` for constant-time comparison (preventing timing side-channel attacks).

### 8.5 Append-Only Audit Storage

Append-only audit storage for trust events is provided by `kailash.trust.audit_store` (`InMemoryAuditStore` for tests, persistent stores for production). The prior `kailash.trust.immutable_audit_log.ImmutableAuditLog` was a deque-based reference implementation with no production consumers — removed in kailash 2.8.12 (issue #573) after the cross-SDK orphan-check flagged it as the Python sibling of kailash-rs's canonical-anchor orphan (kailash-rs#461, PR #466). Users requiring an in-memory bounded chain use `InMemoryAuditStore` directly; the hash-chain properties (SHA-256 `hash(event_data + prev_hash)`, `"0" * 64` genesis, constant-time compare) are preserved there.

---

## 9. Audit Anchor

`AuditAnchor` (in `kailash.trust.chain`) records what an agent has done within its trust chain. Each anchor includes:

- The action performed and its result
- A hash of the chain state at recording time (tamper detection)
- Optional reasoning trace explaining WHY the action was taken
- Timestamp for temporal ordering

The chain hash is computed via `hash_trust_chain_state()` which produces a deterministic SHA-256 over the chain's genesis, capabilities, delegations, and existing anchors.

---
