# SPEC-08: Core SDK Audit/Registry Consolidation

**Status**: DRAFT
**Implements**: Core synergy audit recommendations (01-research/11-core-synergy-audit.md)
**Cross-SDK issues**: TBD
**Priority**: Phase 5 — cleanup, can parallelize with Nexus migration

## §1 Overview

Consolidate the duplicated audit, budget, and registry implementations scattered across `src/kailash/` into canonical locations under `kailash.trust.*`. This reduces the 5+ audit implementations to 1, the 2 budget trackers to 1, and establishes single sources of truth.

## §2 Audit Consolidation

### Current state: 5+ implementations

| Implementation            | Location                       | Used by           |
| ------------------------- | ------------------------------ | ----------------- |
| `AppendOnlyAuditStore`    | `trust/audit_store.py`         | TrustOperations   |
| `AuditQueryService`       | `trust/audit_service.py`       | Compliance export |
| `ImmutableAuditLog`       | `trust/immutable_audit_log.py` | Hash-chain audit  |
| `EnterpriseAuditLogNode`  | `nodes/admin/audit_log.py`     | Workflow nodes    |
| `RuntimeAuditGenerator`   | `runtime/trust/audit.py`       | Runtime execution |
| `AuditEvent` (3 variants) | Three different files          | Various           |

### Target: 1 canonical store

```python
# src/kailash/trust/audit_store.py (canonical — enhanced)

class AuditStore(Protocol):
    """Canonical audit store protocol. All consumers use this."""

    async def append(self, event: AuditEvent) -> str: ...
    async def query(self, filter: AuditFilter) -> list[AuditEvent]: ...
    async def verify_chain(self) -> ChainVerificationResult: ...

class InMemoryAuditStore(AuditStore):
    """In-memory, append-only. For testing and short-lived processes."""
    ...

class SqliteAuditStore(AuditStore):
    """NEW: Persistent SQLite backend. WAL mode, append-only (CARE-010)."""
    ...

@dataclass(frozen=True)
class AuditEvent:
    """Canonical audit event type. Replaces 3 previous variants."""
    event_id: str
    timestamp: datetime
    actor: str                    # agent ID or human ID
    action: str                   # what was done
    resource: str                 # what it was done to
    outcome: str                  # success | failure | held | blocked
    parent_anchor_id: Optional[str] = None  # causality chain (from hash-chain audit)
    duration_ms: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

### Migration

1. Enhance `trust/audit_store.py` with `SqliteAuditStore`
2. Define canonical `AuditEvent` (merge fields from all 3 variants)
3. `nodes/admin/audit_log.py` → consumes `AuditStore`, writes via `AuditEvent`
4. `runtime/trust/audit.py` → consumes `AuditStore`, emits `AuditEvent`
5. `trust/immutable_audit_log.py` → hash-chain verification moves into `AuditStore.verify_chain()`
6. Delete redundant `AuditEvent` type variants
7. Add backward-compat re-exports at old import paths

## §3 Budget Consolidation

### Current state: 2 implementations

| Implementation                 | Location                              | Used by                            |
| ------------------------------ | ------------------------------------- | ---------------------------------- |
| `BudgetTracker`                | `trust/constraints/budget_tracker.py` | PACT execution (via kaizen-agents) |
| `AgentBudget` / `SpendTracker` | `trust/constraints/spend_tracker.py`  | Agent budget metadata              |

### Target: 1 canonical tracker

`BudgetTracker` is the primary implementation (microdollar precision, thread-safe, SQLite persistence via `BudgetStore`). `AgentBudget` is a metadata wrapper — fold its fields into `BudgetTracker`.

### Migration

1. Merge `AgentBudget` fields into `BudgetTracker` (or make AgentBudget a thin wrapper)
2. Wire `BudgetTracker` into `LocalRuntime` as optional config:
   ```python
   runtime = LocalRuntime(budget_store=SqliteBudgetStore("budget.db"), budget_limit_usd=1000.0)
   ```
3. Wire `PostureStore` into `TrustProject` as default (per trust audit recommendation)
4. Enable `ShadowEnforcer` by env var (`TRUST_ENFORCEMENT_MODE=shadow`)

## §4 Registry Consolidation

7+ registry implementations scattered across Core SDK. Low priority — document canonical patterns rather than forcibly merge.

### Canonical registry pattern

```python
class Registry(Protocol[T]):
    """Generic registry for discoverable components."""
    def register(self, name: str, item: T) -> None: ...
    def get(self, name: str) -> Optional[T]: ...
    def list_all(self) -> dict[str, T]: ...
```

Implementations:

- `ToolRegistry` (in kailash-mcp) — tools
- `NodeRegistry` (in kailash-core) — workflow nodes
- `ModelRegistry` (in kailash-ml) — ML models
- `ProviderRegistry` (in kaizen.providers) — LLM providers
- `ServiceRegistry` (in kailash-mcp) — MCP servers

These are domain-specific and should NOT be forcibly unified. Document the pattern; don't merge.

## §5 Migration Order

1. Create `SqliteAuditStore` in `trust/audit_store.py`
2. Define canonical `AuditEvent` dataclass
3. Migrate `nodes/admin/audit_log.py` to use canonical store
4. Migrate `runtime/trust/audit.py` to use canonical store
5. Merge `ImmutableAuditLog` hash-chain verification into `AuditStore.verify_chain()`
6. Merge `AgentBudget` into `BudgetTracker`
7. Wire `BudgetTracker` into `LocalRuntime` (optional)
8. Wire `PostureStore` into `TrustProject` default
9. Enable `ShadowEnforcer` by env var
10. Run full test suite

## §6 Related Specs

- **SPEC-06**: Nexus migration (Nexus audit moves to canonical `AuditStore`)
- **SPEC-07**: ConstraintEnvelope (budget limits in envelope use the canonical `BudgetTracker`)
- **SPEC-03**: MonitoredAgent (uses `CostTracker` for agent-level cost, which feeds into `BudgetTracker` for system-level budget)

## §7 Security Considerations

Core SDK consolidation is an internal-facing refactor, but the primitives it consolidates (audit stores, budget trackers, registries) are governance-critical: every audit event in the platform lands in the consolidated store, and every agent's cost flows through the consolidated tracker. A vulnerability here compromises the entire trust chain.

### §7.1 Audit Log Integrity After Consolidation

**Threat**: Before consolidation, the platform has 5+ audit implementations. Each stores events in its own format, and the redundancy sometimes catches tampering (a discrepancy between Nexus's audit log and trust's audit log is a signal). After consolidation there is ONE store — tampering leaves no cross-reference to detect it. An attacker who gains write access to the canonical `AuditStore` can rewrite history.

**Mitigations**:

1. `AuditStore` MUST use append-only semantics. The storage backend (SQLite, Postgres, or a WAL file) rejects any operation other than INSERT at the schema level.
2. Every audit entry MUST carry a `prev_hash` field — a hash of the previous entry. This creates a Merkle chain. Tampering with any entry breaks the chain.
3. Chain verification runs on every system startup and on an interval (configurable, default every 10k entries). Verification failure raises `AuditChainBrokenError` and triggers a trust-plane posture escalation to BLOCKED.
4. Migration from the 5 old stores MUST rehash existing entries into the chain — old entries get chain positions, new entries continue. Migration is one-time and logged.
5. Regression tests include a tamper scenario: modify one entry, verify chain detection catches it.

### §7.2 Registry Poisoning (NodeRegistry, AuditStore, ProviderRegistry)

**Threat**: Consolidation creates a single `Registry(Protocol[T])` pattern used by multiple subsystems. A single poisoned registry entry (malicious `Node` subclass, fake `AuditStore` backend, trojaned `LLMProvider`) is now used by everyone. In the current multi-registry world, a poisoned Nexus registry is contained to Nexus; after consolidation, everything shares the registry.

**Mitigations**:

1. `Registry.register(key, value)` MUST validate the value against a registration schema:
   - For `NodeRegistry`: the value MUST be a class that subclasses `Node` directly or via a documented path. Subclass chain is verified.
   - For `AuditStore` backends: the value MUST implement the `AppendOnlyStore` protocol AND carry a cryptographic attestation (a signature over the class definition hash).
   - For `LLMProvider`: the value MUST come from a module under an allowlisted package path (`kaizen.providers.*`, `kailash.providers.*`).
2. Registry entries are IMMUTABLE after registration. `register()` raises `AlreadyRegisteredError` on re-registration attempts.
3. Registry operations are audit-logged with the caller's module path (via stack inspection) and a timestamp.
4. A "registration freeze" hook runs at startup — after initial registrations, the registry enters a frozen state where further registrations require explicit `Registry.unfreeze(secret_token)`.

### §7.3 Budget Tracker Double-Counting During Consolidation

**Threat**: Before consolidation, `MonitoredAgent` tracks agent-level cost, `TrustPlane` tracks system-level cost, and `PACT GovernanceEngine` tracks envelope-level cost. After consolidation, all flow through `BudgetTracker`. If the consolidation accidentally wires the same cost event through two code paths (MonitoredAgent → TrustPlane → BudgetTracker AND MonitoredAgent → BudgetTracker directly), the same LLM call is counted twice. Budget enforcement hits the ceiling at 50% of actual spend.

**Mitigations**:

1. `BudgetTracker.record(event: CostEvent)` MUST deduplicate on `event.call_id`. Duplicate call_ids are rejected (logged, not summed).
2. Every `CostEvent` carries a canonical source identifier: `source: Literal["monitored_agent", "trust_plane", "pact_engine", "direct"]`. Only ONE source per call_id is allowed.
3. Migration code path MUST document which source each legacy tracker maps to — no two legacy trackers feed the same event through different sources.
4. Integration test constructs a `MonitoredAgent` inside a `TrustPlane` with an envelope-governed `PACT` engine, runs a known-cost mock LLM call, and verifies `BudgetTracker.total` equals the mock's cost (not 2x or 3x).

### §7.4 Runtime Budget Wiring (BudgetTracker in LocalRuntime)

**Threat**: Wiring `BudgetTracker` into `LocalRuntime` means every workflow run consumes budget. If a workflow is scheduled in a loop (cron, retry handler, supervisor delegation), a misconfigured budget can silently exhaust and block legitimate work. An attacker who controls workflow scheduling could intentionally drain budgets by triggering many cheap workflows.

**Mitigations**:

1. `LocalRuntime.execute()` MUST accept an explicit `budget: Optional[BudgetTracker]` parameter. If `None`, no budget enforcement runs and no budget events are recorded (opt-in model).
2. When a budget IS provided, `LocalRuntime` MUST check the budget BEFORE execution starts and emit `BudgetPreCheckEvent` — this prevents work from starting when budget is already exhausted.
3. Budget exhaustion during a workflow run raises `BudgetExhaustedError` and tears down the workflow cleanly. In-flight tool calls are canceled, not abandoned.
4. Rate limiting on `LocalRuntime.execute()` calls per budget — default 1000 executions per budget per minute, configurable. This caps the drain rate.

### §7.5 Cross-SDK Audit Event Format Drift

**Threat**: Python's `AuditEvent` dataclass and Rust's `AuditEvent` struct must serialize to identical JSON (per SPEC-09). If one side adds a field without updating the other, audit logs written in one language cannot be verified in the other. An attacker who can inject events via the mismatched side creates events the "authoritative" side cannot parse, effectively hiding malicious activity behind parse failures.

**Mitigations**:

1. `AuditEvent` schema is defined in SPEC-09 §2 (cross-ref from here). Changes require spec update on Python AND Rust sides atomically.
2. Python's `AuditEvent.to_dict()` uses the canonical JSON format (sorted keys, explicit None vs missing distinction, no extras allowed).
3. CI includes cross-language round-trip tests: Python writes, Rust reads, Rust writes, Python reads. Any schema mismatch fails CI.
4. `AuditEvent` deserialization in both languages REJECTS unknown fields (no forward-compatibility silent acceptance).
