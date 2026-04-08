# Trust / EATP Plane Audit — 2026-04-07

**Audit scope**: Map every Trust primitive, every consumer, and identify integration gaps and bypasses.

## Scale

- **276 Python files** in `src/kailash/trust/`
- **16 major submodules**
- **~70 public exports** in `kailash.trust.__init__`
- All crypto functions lazy-loaded (PyNaCl required)
- Core types available without dependencies

## Trust Primitive Layer

### Core primitives (no PyNaCl required)

| Primitive                   | Location                        | Purpose                                                |
| --------------------------- | ------------------------------- | ------------------------------------------------------ |
| `GenesisRecord`             | `chain.py`                      | Establishes agent authorization root-of-trust          |
| `DelegationRecord`          | `chain.py`                      | Tracks trust delegation across agent lineages          |
| `ConstraintEnvelope`        | `chain.py` (base)               | Structured constraints across 5 EATP dimensions        |
| `TrustPosture`              | `posture/postures.py`           | Agent trust state machine                              |
| `PostureStore`              | `posture/posture_store.py`      | Persistent posture state (SQLite)                      |
| `AuditAnchor`               | `chain.py`                      | Audit trail with parent linking for causality          |
| `BudgetTracker`             | `constraints/budget_tracker.py` | Thread-safe two-phase budget accounting (microdollars) |
| `BudgetStore`               | `constraints/budget_store.py`   | SQLite persistence for BudgetTracker snapshots         |
| `AuditStore`                | `audit_store.py`                | Append-only immutable audit trail (CARE-010)           |
| `ConfidentialityLevel`      | `reasoning/traces.py`           | PUBLIC → INTERNAL → CONFIDENTIAL → SECRET              |
| `ReasoningTrace`            | `reasoning/traces.py`           | Reasoning evidence + completeness scoring (v2.2)       |
| `ShadowEnforcer`            | `enforce/shadow.py`             | Non-blocking enforcement with metrics                  |
| `StrictEnforcer`            | `enforce/strict.py`             | Blocking enforcement                                   |
| `TrustRole`                 | `roles.py`                      | RBAC enum with permission matrix                       |
| `HookRegistry` / `EATPHook` | `hooks.py`                      | Pre/post-operation hooks                               |

### Public API exports (selected from `__init__.py`)

```python
# Chain infrastructure
ALL_DIMENSIONS, VALID_DIMENSION_NAMES,
AuthorityType, CapabilityType, ActionResult, ConstraintType, VerificationLevel,
DelegationLimits, GenesisRecord, CapabilityAttestation, DelegationRecord,
Constraint, ConstraintEnvelope, AuditAnchor, VerificationResult,
TrustLineageChain, LinkedHashEntry, LinkedHashChain,

# Operations
TrustOperations, TrustKeyManager, CapabilityRequest,

# Stores
TrustStore, InMemoryTrustStore,

# Posture
TrustPosture, PostureStateMachine, PostureEvidence, PostureStore,
TrustPostureMapper, map_verification_to_posture, get_posture_for_action,

# Reasoning (v2.2)
ConfidentialityLevel, ReasoningTrace, EvidenceReference,
reasoning_completeness_score,

# Hooks, Roles, Vocabulary, Crypto (lazy-loaded)
```

## Trust Engine Layer (TrustPlane)

**Location**: `src/kailash/trust/plane/`

**TrustPlane is a pattern, not a single class.** Composition of:

1. **TrustProject** (orchestrator, ~130 lines, async)
2. **TrustOperations** (establish/delegate/verify/audit)
3. **TrustPlaneStore** (FilesystemTrustPlaneStore OR SqliteTrustPlaneStore)
4. **StrictEnforcer** / **ShadowEnforcer** (policy enforcement)

**Key files**:

- `project.py` — Async project lifecycle, decision/milestone recording
- `models.py` (~500 lines) — 5D constraint envelope domain models
- `store/sqlite.py` — Single-file WAL-mode persistent store, schema v1
- `store/filesystem.py` — Git-friendly JSON file backend (6 subdirs)
- `rbac.py` — RBAC matrix export (#81, #89, #100, CAP-007)
- `delegation.py` — Delegate management with cross-process review resolution
- `holds.py` — Hold records (escalation/intervention)

## EATP Record Types (per Spec D6)

| Record Type             | Location               | Purpose                              |
| ----------------------- | ---------------------- | ------------------------------------ |
| `GenesisRecord`         | `chain.py:122-165`     | Root-of-trust proof                  |
| `CapabilityAttestation` | `chain.py`             | What an agent is authorized to do    |
| `DelegationRecord`      | `chain.py`             | Transfer of trust down chain         |
| `ConstraintEnvelope`    | `chain.py:443-500`     | 5D constraint set                    |
| `Constraint`            | `chain.py`             | Individual constraint                |
| `AuditAnchor`           | `chain.py`             | Audit event with parent linking      |
| `TrustLineageChain`     | `chain.py`             | Complete chain                       |
| `DecisionRecord`        | `plane/models.py:382+` | Domain decision with reasoning trace |
| `MilestoneRecord`       | `plane/models.py`      | Versioned checkpoint                 |
| `ProjectManifest`       | `plane/models.py`      | Project metadata + envelope          |

**Not found in Python SDK** (likely Rust-only or named differently):

- VetGrant
- BudgetReserve (called `BudgetSnapshot` in Python)
- ConstraintSnapshot (implicit in stores)

## Store Backends

| Type               | Backend                   | File                            |
| ------------------ | ------------------------- | ------------------------------- |
| BudgetTracker      | In-memory deque           | `constraints/budget_tracker.py` |
| BudgetTracker      | SQLite (WAL)              | `constraints/budget_store.py`   |
| PostureStore       | SQLite (WAL)              | `posture/posture_store.py`      |
| AuditStore         | In-memory append-only     | `audit_store.py`                |
| AuditStore         | **NO PERSISTENT BACKEND** | (gap)                           |
| TrustLineageChain  | In-memory                 | `chain_store/memory.py`         |
| TrustLineageChain  | Filesystem (JSON)         | `chain_store/filesystem.py`     |
| TrustLineageChain  | SQLite                    | `chain_store/sqlite.py`         |
| TrustPlane Project | Filesystem (6 subdirs)    | `plane/store/filesystem.py`     |
| TrustPlane Project | SQLite (single .db)       | `plane/store/sqlite.py`         |
| ShadowEnforcer     | In-memory deque (10K)     | `enforce/shadow_store.py`       |
| ShadowEnforcer     | SQLite                    | `enforce/shadow_store.py`       |
| PACT Envelope      | In-memory                 | `pact/store.py`                 |
| PACT Envelope      | SQLite                    | `pact/stores/sqlite.py`         |

**Critical gap**: `AuditStore` has no persistent backend. Audit trail lost on restart unless using one of the other audit implementations (which is the duplication problem — see core-synergy audit).

## THE CONSUMER MAP (Critical Output)

### Internal trust subsystem consumers

| Consumer                | Trust Primitive                                      | How                                                               |
| ----------------------- | ---------------------------------------------------- | ----------------------------------------------------------------- |
| TrustProject            | GenesisRecord, DelegationRecord, AuditAnchor         | Create/verify trust chains                                        |
| TrustProject            | ConstraintEnvelope, ConfidentialityLevel             | Enforce envelope on decisions via StrictEnforcer + ShadowEnforcer |
| TrustProject            | PostureStore                                         | Track agent posture transitions                                   |
| TrustProject            | ReasoningTrace                                       | Records reasoning in DecisionRecord                               |
| TrustOperations         | TrustLineageChain, TrustStore                        | ESTABLISH/DELEGATE/VERIFY/AUDIT                                   |
| StrictEnforcer          | VerificationResult, ConstraintEnvelope               | Evaluate actions against constraints                              |
| ShadowEnforcer          | StrictEnforcer (composes)                            | Non-blocking shadow mode wrapper                                  |
| ConstraintEvaluator     | Constraint, ConstraintEnvelope                       | Multi-dimension evaluation                                        |
| BudgetTracker           | BudgetStore                                          | Persist snapshots and transactions                                |
| PostureStateMachine     | PostureStore                                         | Persist state transitions                                         |
| PactBridge (PACT)       | Constraint, ConstraintEnvelope, ConfidentialityLevel | Knowledge access gating                                           |
| GovernanceEngine (PACT) | ReasoningTrace (optional)                            | Audit emissions include reasoning                                 |
| RBACExporter            | TrustRole, AuditAnchor                               | RBAC matrix export (CAP-007)                                      |
| AuditLogger             | AuditAnchor                                          | Chain verification (#80, #88)                                     |

### Runtime layer (workflow execution)

| Consumer            | Trust Primitive | Status                    |
| ------------------- | --------------- | ------------------------- |
| `LocalRuntime`      | TrustOperations | **Optional, NOT default** |
| `AsyncLocalRuntime` | TrustOperations | **Optional, NOT default** |
| `BaseRuntime`       | None            | No direct consumption     |

### Kaizen / agent framework

**Critical finding**: Kaizen agents in kailash-py are NOT direct consumers of Trust primitives.

- Agents reference `TrustContext` abstraction (not raw `TrustOperations`)
- `TrustedAgent` wrapper exists at `trust/agents/trusted_agent.py` but is NOT in public API
- No evidence of per-agent budget tracking, per-agent posture state, or per-agent reasoning traces in core Kaizen
- `GovernedSupervisor` (in kaizen-agents) wraps Trust constructs but agents themselves don't consume Trust directly

### MCP servers

| Consumer       | Trust Primitive                   | How                                                                            |
| -------------- | --------------------------------- | ------------------------------------------------------------------------------ |
| TrustPlane MCP | TrustProject + ConstraintEnvelope | 5 tools: trust_check, trust_record, trust_envelope, trust_status, trust_verify |
| Platform MCP   | (lightweight read-only)           | trust_status reads manifest.json only                                          |

### PACT governance integration

| Consumer             | Trust Primitive                                                            | How                                             |
| -------------------- | -------------------------------------------------------------------------- | ----------------------------------------------- |
| GovernanceEngine     | ConfidentialityLevel                                                       | Envelope config uses ConfidentialityLevel       |
| GovernanceEngine     | **ConstraintEnvelopeConfig (PACT-specific, NOT chain.ConstraintEnvelope)** | PACT uses its own envelope type                 |
| PactBridge           | Constraint (knowledge scope)                                               | Enforces access constraints                     |
| EnvelopeStore (PACT) | RoleEnvelope, TaskEnvelope                                                 | PACT's own envelope types, independent of chain |

### Data/export layer

| Consumer             | Trust Primitive             | How                                  |
| -------------------- | --------------------------- | ------------------------------------ |
| SIEM Exporter        | AuditAnchor                 | Export audit trail to SIEM           |
| Compliance Reporter  | AuditAnchor, DecisionRecord | RBAC matrix, hash chain verification |
| OpenTelemetry tracer | ReasoningTrace              | Emit reasoning spans                 |

## Critical Gaps

### 1. Kaizen agents have no Trust integration

- BudgetTracker NOT consumed by kaizen agents
- Per-agent posture tracking NOT implemented
- `TrustedAgent` wrapper exists but is NOT public-facing
- **Impact**: Agents have no spend budget governance

### 2. BudgetTracker NOT wired into runtime

- `BudgetTracker` and `SQLiteBudgetStore` exist but `LocalRuntime` does not instantiate or track budgets
- Persistence works but is never called from the workflow execution path
- **Impact**: Budget state lost on process restart, no enforcement during workflow execution

### 3. Three different ConstraintEnvelope types

- `chain.ConstraintEnvelope` (in `trust/chain.py`)
- `plane.ConstraintEnvelope` (in `trust/plane/models.py`)
- `pact.ConstraintEnvelopeConfig` (in `trust/pact/config.py`, Pydantic, not dataclass)

**These are NOT interoperable**. PACT envelopes can't be intersected with chain envelopes. **EATP D6 violation** — semantic divergence within the same SDK.

### 4. Shadow enforcement NOT wired to runtime

- `ShadowEnforcer` exists with full metrics
- NOT integrated into `LocalRuntime`
- Metrics collection NOT enabled by default
- **Impact**: Cannot run shadow mode for gradual rollout

### 5. AuditStore has no persistent backend

- Only in-memory `AppendOnlyAuditStore` (CARE-010 compliance)
- No SQLite or filesystem backend
- **Impact**: Audit trail lost on restart

### 6. PostureStore NOT auto-wired

- Exists as module
- NOT integrated into TrustProject by default
- Manual initialization required
- **Impact**: Agent posture state not tracked automatically

## Verified Fixes (from CHANGELOG)

| Issue            | Title                                         | Status   | Evidence                                                               |
| ---------------- | --------------------------------------------- | -------- | ---------------------------------------------------------------------- |
| #145             | BudgetTracker over-budget reservations        | ✅ FIXED | Saturating arithmetic + bounds checking in `budget_tracker.py:123-140` |
| #146             | ShadowEnforcer missing                        | ✅ FIXED | `enforce/shadow.py:82-180` implemented                                 |
| #147             | intersect_constraints / envelope intersection | ✅ FIXED | `pact/envelopes.py:320-402` implements `intersect_envelopes()`         |
| #191             | 'pseudo' posture rejected                     | ✅ FIXED | `posture/postures.py` has `_missing_` aliasing                         |
| #284             | AuditStore abstract methods are pass stubs    | ✅ FIXED | `AppendOnlyAuditStore` has real implementations                        |
| #80 / #88        | ImmutableAuditLog + hash-chain audit          | ✅ FIXED | `immutable_audit_log.py` + `chain.py` HMAC verification                |
| #81 / #89 / #100 | RBAC Matrix Export (CAP-007)                  | ✅ FIXED | `plane/rbac.py`                                                        |
| #97              | Cross-SDK naming alignment (EATP D6)          | ✅ FIXED | `plane/delegation.py` renames                                          |
| #84 / #92        | OpenTelemetry tracing (CAP-010)               | ✅ FIXED | `reasoning/traces.py`                                                  |

## TrustPlane MCP Server (Why It's the Cleanest)

**Location**: `src/kailash/trust/plane/mcp_server.py`

**Design principles**:

1. **Minimal responsibilities** — Only gating decisions, NOT replicating full TrustProject logic
2. **Double-checked locking** — Manifest mtime-based reload (lines 91-145) prevents thundering herd
3. **Thread-safe caching** — `_project_lock` protects global state
4. **5 simple tools** — `trust_check`, `trust_record`, `trust_envelope`, `trust_status`, `trust_verify`
5. **No business logic in MCP** — All logic delegated to TrustProject
6. **Lazy loading** — Project loaded on first call, cached until manifest changes

**This sets the pattern** for how other framework-specific MCP servers should be structured. Trust gates → MCP tool. Logic → primitive class. MCP server is a thin shim.

## Cross-SDK EATP D6 Compliance

| Feature               | kailash-py                                    | kailash-rs      | Status                                  |
| --------------------- | --------------------------------------------- | --------------- | --------------------------------------- |
| GenesisRecord         | ✅                                            | ✅ (EATP crate) | Matching (both ed25519 + expire_at)     |
| BudgetTracker         | ✅ Microdollar                                | ✅ Equivalent   | Matching (saturating arithmetic)        |
| PostureStore          | ✅ SQLite + in-memory                         | ✅ Equivalent   | Matching (5 states aligned)             |
| Reasoning Trace       | ✅ v2.2                                       | ✅ v2.2         | Matching (ConfidentialityLevel aligned) |
| ConstraintEnvelope    | ⚠️ **THREE versions**                         | Likely unified  | **DIVERGING**                           |
| AuditAnchor           | ✅                                            | ✅              | Matching                                |
| Envelope Intersection | ✅                                            | ✅              | Matching                                |
| Delegation Naming     | ✅ Renames Delegate→DelegationRecipient (#97) | TBD             | Cross-reference needed                  |

**Critical D6 violation**: Python has 3 ConstraintEnvelope types. Must consolidate to single canonical type matching Rust's single envelope.

## Recommendations

### IMMEDIATE (next minor release)

1. **Wire BudgetTracker to LocalRuntime**

   ```python
   runtime = LocalRuntime(
       budget_store=SQLiteBudgetStore("./budget.db"),
       budget_limit_usd=1000.0
   )
   ```

2. **Wire PostureStore to TrustProject by default**

   ```python
   project = await TrustProject.create(
       ...,
       posture_store=SQLitePostureStore(trust_dir / "postures.db")
   )
   ```

3. **Enable shadow mode by env var**
   ```python
   enforcer = os.environ.get("TRUST_ENFORCEMENT_MODE", "strict") == "shadow"
   ```

### SHORT TERM (next major release)

1. **Unify ConstraintEnvelope**
   - Merge `chain.ConstraintEnvelope` + `plane.ConstraintEnvelope` + `pact.ConstraintEnvelopeConfig`
   - Single canonical type with optional fields for PACT extensions
   - **Restores EATP D6 semantic matching**

2. **Public TrustedAgent API**
   - Export `TrustedAgent`, `PseudoAgent`, `PostureAgent` in main `__init__`
   - Document agent trust patterns (isolation, posture tracking)
   - **Makes Kaizen agents first-class Trust consumers**

3. **Persistent AuditStore**
   - Add `SqliteAuditStore` alongside in-memory version
   - CARE-010 compliance preserved (still append-only)
   - Enables audit trail retention across restarts

4. **Document PACT vs Trust boundary**
   - Currently implicit
   - Formalize: which uses which primitives

## Architecture Boundaries (What Stays, What Moves)

**Trust stays in `kailash.trust`**:

- Chain data structures
- Cryptographic operations
- Posture state machines
- Budget accounting
- Audit anchors

**PACT stays in `kailash.trust.pact`** (already correct per #63):

- Organizational compilation (D/T/R)
- Role envelopes + task envelopes
- Knowledge access bridges
- GovernanceEngine

**TrustPlane stays in `kailash.trust.plane`**:

- Project-scoped orchestration
- Persistent stores
- Delegation management
- Holds and escalations
- MCP server

**Kaizen agents should consume**:

- TrustOperations (establish, delegate, verify)
- ConstraintEnvelope (single type) for boundary spec
- ReasoningTrace for decision documentation
- PostureStore for agent state tracking
- BudgetTracker for spend governance

## Status

**Trust convergence is ~75% complete.** The final 25% is integration wiring (budgets to runtime, postures to project, kaizen consumption) plus envelope unification. No new primitive code needed — just wiring and consolidation.
