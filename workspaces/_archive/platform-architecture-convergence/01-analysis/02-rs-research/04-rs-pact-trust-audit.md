# kailash-rs PACT + EATP + Trust-Plane Audit — 2026-04-07

## Crate Overview

Rust has FOUR related crates for trust/governance:

| Crate                  | Role                                                 | Dependencies                                |
| ---------------------- | ---------------------------------------------------- | ------------------------------------------- |
| **eatp**               | Trust foundational (primitives)                      | Standalone (crypto only, zero kailash deps) |
| **trust-plane**        | Trust operational environment                        | `eatp`                                      |
| **kailash-governance** | PACT primitives (engine, envelopes, access)          | `eatp`                                      |
| **kailash-pact**       | PACT facade (re-exports governance + agent/mcp/yaml) | `kailash-governance`, `eatp`                |

**Dependency chain**:

```
kailash-pact → kailash-governance → eatp
             → eatp
trust-plane  → eatp
```

## Part A: eatp Crate (26 modules)

### Key Types

| Type                        | File                     | Purpose                                                   |
| --------------------------- | ------------------------ | --------------------------------------------------------- |
| `GenesisRecord`             | `eatp.rs`                | Root-of-trust proof                                       |
| `DelegationRecord`          | `delegation.rs:112`      | Delegation with constraint tightening, cascade revocation |
| `CapabilityAttestation`     | `types.rs`               | What an agent is authorized to do                         |
| `ConstraintEnvelope` (EATP) | `constraints/mod.rs:189` | **5D constraint space, OPTIONAL per-dimension**           |
| `Subject`                   | `constraints/mod.rs:120` | Entity a constraint applies to                            |
| `Dimensions`                | `constraints/mod.rs:135` | The 5-dimensional constraint space                        |
| `TrustBlock`                | `chain.rs`               | Append-only signed chain element                          |
| `EvidenceRecord`            | `eatp.rs:119`            | Cryptographically signed evidence                         |

### Store Backends

| Backend    | File                  | Feature flag                                        |
| ---------- | --------------------- | --------------------------------------------------- |
| In-memory  | `store/memory.rs`     | always available                                    |
| Filesystem | `store/filesystem.rs` | `filesystem` (requires age encryption, fs4 locking) |
| SQLite     | `store/sqlx.rs`       | `sqlx` (requires sqlx, tokio)                       |

Unified trait: `TrustStore` in `store/mod.rs`.

### Cryptographic Operations

- Ed25519 signing via `ed25519-dalek`
- SHA-256 hash chains (`chain.rs`, `canonical.rs`)
- Zeroization via `zeroize` crate
- Per-delegator public key in `DelegationRecord`

### MCP Server (eatp/src/mcp/)

Tools: `eatp_verify`, `eatp_status`, `eatp_audit_query`, `eatp_delegate`, `eatp_revoke`, `eatp_validate_multi_sig`

Resources: `eatp://authorities`, `eatp://agents/{id}`, `eatp://chains/{id}`, `eatp://constraints/{id}`

### Cargo Dependencies

```toml
# Core
serde, serde_json
ed25519-dalek, sha2, hex, zeroize
tokio, async-trait
tracing, thiserror

# Optional
age, fs4          # filesystem feature
sqlx              # sqlx feature
clap, dialoguer   # cli feature
hyper, hyper-util, tokio-stream  # mcp feature
```

**NO Kailash dependencies**. EATP is fully standalone.

## Part B: trust-plane Crate (30 modules)

### Key Files

- `project.rs` — Core `TrustProject` orchestrator
- `envelope.rs:23` — **ConstraintEnvelope (Trust-Plane variant, FLATTENED)**
- `enforcer.rs:61` — StrictEnforcer
- `shadow.rs` — ShadowEnforcer (non-blocking)
- `models.rs:24` — DecisionRecord
- `models.rs:108` — MilestoneRecord
- `delegation.rs` — Delegate management with review resolution
- `holds.rs` — Hold records
- `mcp/mod.rs:918` — Trust plane MCP server
- `mcp/proxy.rs:479` — TrustProxy (constraint enforcement wrapper)

### TrustProject

```rust
pub struct TrustProject {
    // Orchestrator wrapping EATP primitives with:
    // - Dual-lock pattern (outer parking_lot::Mutex, inner per-file locks)
    // - File-backed state (via TrustPlaneStore trait)
    // - Constraint enforcement
    // - Delegation management
    // - Audit session tracking
    // - Verification bundles
    // - Conformance testing
    // - Decision/milestone recording
}
```

### ConstraintEnvelope (Trust-Plane Variant) — FLATTENED

```rust
pub struct ConstraintEnvelope {
    pub operational: OperationalConstraints,
    pub data_access: DataAccessConstraints,
    pub financial: FinancialConstraints,
    pub temporal: TemporalConstraints,
    pub communication: CommunicationConstraints,
    pub signed_by: Option<String>,
    pub signed_at: Option<DateTime<Utc>>,
}

impl ConstraintEnvelope {
    pub fn is_tighter_than(&self, other: &Self) -> bool;  // monotonic tightening check
}
```

**Difference from EATP's version**:

- EATP: `dimensions: Option<Dimensions>` (each dim is `Option<T>`, None = unconstrained)
- Trust-Plane: all 5 dimensions always present (flattened struct)

**NOT interoperable without conversion.**

### TrustProxy

```rust
pub struct TrustProxy {
    project: Arc<parking_lot::Mutex<TrustProject>>,
    call_log: VecDeque<ProxyCallLog>,  // bounded, max 10,000 entries
}

pub enum ProxyResponse {
    Blocked(String),
    Held(String),
    Forwarded(Value),
}
```

**Not actually an MCP server** — a constraint enforcement wrapper that logs calls and blocks/holds/forwards based on verdicts.

### Cargo Dependencies

```toml
eatp                         # local path
tokio, async-trait, parking_lot
fs4, globset, walkdir

# Optional
kailash-enterprise           # feature: "enterprise"
clap, colored                # cli feature
axum                         # mcp feature
```

**Trust-plane does NOT depend on kailash-core or kailash-value.** Standalone operational environment.

## Part C: kailash-governance Crate (PACT Primitives)

### Structure

```
crates/kailash-governance/src/
├── access.rs         — AccessDecision, 5-step enforcement algorithm
├── addressing.rs     — D/T/R grammar, Address type with validation
├── bridges.rs        — NEVER_DELEGATED_ACTIONS, bridge logic
├── clearance.rs      — ClassificationLevel, RoleClearance
├── compilation.rs    — OrgDefinition → CompiledOrg
├── context.rs        — GovernanceContext (frozen snapshot)
├── engine.rs         — GovernanceEngine (thread-safe facade)
├── envelopes.rs      — RoleEnvelope, TaskEnvelope, EffectiveEnvelopeSnapshot
├── error.rs
├── explain.rs        — explain_access, describe_address, explain_envelope
├── knowledge.rs      — KnowledgeItem
├── store.rs          — EnvelopeStore, ClearanceStore, AccessPolicyStore, OrgStore
├── types.rs
├── vacancy.rs        — Orphaned role detection
└── verdict.rs        — GovernanceVerdict (4-zone gradient)
```

### 3-Layer Envelope Model (Matches Python)

```rust
// Layer 1: Set by supervisor, constrains a role
pub struct RoleEnvelope {
    pub envelope: eatp::constraints::ConstraintEnvelope,  // USES EATP TYPE
    pub role_address: Address,
    pub version: u64,
}

// Layer 2: Per-task narrowing, must expire
pub struct TaskEnvelope {
    pub envelope: eatp::constraints::ConstraintEnvelope,  // USES EATP TYPE
    pub expires_at: DateTime<Utc>,
}

// Layer 3: Computed intersection of ancestor chain
pub struct EffectiveEnvelopeSnapshot {
    pub envelope: eatp::constraints::ConstraintEnvelope,  // USES EATP TYPE
    pub chain: Vec<Address>,
    pub version_hash: [u8; 32],
}
```

**Key invariant**: TaskEnvelope can only narrow, never widen. Enforced via `pass-through intersection` semantics.

**ConstraintEnvelope inside these wrappers = EATP's optional-per-dimension type.** So kailash-governance **composes** EATP's envelope type rather than duplicating it.

### FiniteF64 NaN Protection

All numeric fields use `FiniteF64` type that validates `math.isfinite()` at construction — prevents NaN/Inf injection attacks.

### GovernanceEngine

```rust
pub struct GovernanceEngine {
    // Thread-safe facade for:
    // - Org compilation (OrgDefinition → CompiledOrg)
    // - Envelope computation (RoleEnvelope → EffectiveEnvelopeSnapshot via intersection)
    // - Access verification (5-step algorithm)
    // - Verdict emission (AutoApproved → Flagged → Held → Blocked)
}
```

**Anti-self-modification**: Agents receive `GovernanceContext(frozen=true)`, NEVER the engine directly.

## Part D: kailash-pact Crate (Facade)

### Structure

```
crates/kailash-pact/src/
├── lib.rs         — Re-exports kailash-governance primitives
├── agent.rs       — PactGovernedAgent
├── mcp.rs         — PactMcpBridge (governance policy evaluator for MCP)
├── yaml.rs        — Config loader
└── stores/
    └── sqlite.rs  — Optional SQLite persistence
```

### Re-Export Pattern

`lib.rs` re-exports from `kailash-governance`:

- `access`, `addressing`, `bridges`, `clearance`, `compilation`, `context`, `engine`, `envelopes`, `error`, `explain`, `knowledge`, `store`, `types`, `vacancy`, `verdict`
- Top-level types: `Address`, `GovernanceEngine`, `ClassificationLevel`, `RoleEnvelope`, `TaskEnvelope`, `EffectiveEnvelopeSnapshot`, etc.

### PactMcpBridge

```rust
pub struct PactMcpBridge { ... }

pub enum McpVerdict {
    AutoApproved { tool_name: String },
    Flagged { tool_name: String, reason: String },
    Held { tool_name: String, reason: String },
    Blocked { tool_name: String, reason: String },
}

impl PactMcpBridge {
    pub fn evaluate_tool_call(&self, tool_name: &str, args: &Value, context: &GovernanceContext) -> McpVerdict;
}
```

**NOT a server or client** — a policy engine. Upstream MCP servers call it to decide whether to allow tool execution.

**Evaluation**: default-deny (unregistered tools blocked), clearance check, financial check, never-delegated check.

**Depends on**: `kailash-governance` (for verdict types), `eatp` (clearance levels).

### Cargo.toml

```toml
[dependencies]
kailash-governance = { path = "../kailash-governance" }
eatp = { path = "../eatp" }
serde, serde_json, chrono, uuid, sha2, hex
parking_lot, thiserror
serde_yaml = { optional = true }
sqlx = { optional = true, features = ["runtime-tokio", "sqlite"] }
tokio = { optional = true }

[features]
default = ["yaml", "sqlite", "mcp"]
```

## Critical Finding: THREE ConstraintEnvelope Types in Rust

| Location                              | Type                 | Design                                                   | Used By                               |
| ------------------------------------- | -------------------- | -------------------------------------------------------- | ------------------------------------- |
| `eatp/src/constraints/mod.rs:189`     | `ConstraintEnvelope` | Optional per-dimension (None = unconstrained)            | PACT governance layers, serialization |
| `trust-plane/src/envelope.rs:23`      | `ConstraintEnvelope` | Flattened 5D (all always present)                        | File-backed trust records             |
| `kailash-governance/src/envelopes.rs` | (wraps EATP's type)  | N/A — uses EATP's type inside Role/Task/Effective layers | Governance computation                |

**Key insight**: kailash-governance **does** compose EATP's envelope (correct composition). But trust-plane has a **parallel flattened variant** that's not interoperable.

**Same problem as Python** (which also has 3 envelope types). Must unify in lockstep.

## MCP Architecture — THREE Parallel Systems

1. **EATP MCP server** (`eatp/src/mcp/`) — standalone server exposing trust operations
2. **trust-plane MCP proxy** (`trust-plane/src/mcp/proxy.rs`) — NOT a server, wraps TrustProject to enforce constraints before forwarding tool calls
3. **PACT MCP bridge** (`kailash-pact/src/mcp.rs`) — bridge/evaluator called by upstream MCP servers

These are orthogonal concerns but each uses different JSON-RPC types and patterns. Fragmentation to be addressed via `kailash-mcp` crate extraction.

## Recent Security Fixes Verified (Python Issue Numbers)

| Python Issue                      | Title                                              | Rust Status                         |
| --------------------------------- | -------------------------------------------------- | ----------------------------------- |
| #276                              | ReadOnlyGovernanceView blocklist                   | ✅ Matched in kailash-governance    |
| #234-241                          | Enforcement modes, envelope adapter, HELD handling | ✅ Matched                          |
| #199                              | EATP record emission in GovernanceEngine           | ✅ EvidenceRecord in eatp           |
| #168-202                          | Vacancy handling                                   | ✅ vacancy.rs in kailash-governance |
| Monotonic tightening + NaN guards | M7 rules                                           | ✅ FiniteF64 everywhere             |
| Thread safety                     | parking_lot locks                                  | ✅ Verified                         |

## Cross-SDK Parity

| Concern                                                                      | Rust                 | Python                | Parity              |
| ---------------------------------------------------------------------------- | -------------------- | --------------------- | ------------------- |
| D/T/R grammar                                                                | ✓ Address type       | ✓ Address type        | ✓                   |
| 3-layer envelopes (Role/Task/Effective)                                      | ✓                    | ✓                     | ✓                   |
| 5D constraints (Financial, Operational, Temporal, DataAccess, Communication) | ✓                    | ✓                     | ✓                   |
| GovernanceEngine facade                                                      | ✓ kailash-governance | ✓ kailash.trust.pact  | ✓                   |
| Frozen GovernanceContext (anti-self-modification)                            | ✓                    | ✓                     | ✓                   |
| NaN/Inf protection                                                           | ✓ FiniteF64          | ✓ \_validate_finite() | ✓                   |
| Default-deny tools                                                           | ✓ PactMcpBridge      | ✓                     | ✓                   |
| **ConstraintEnvelope proliferation**                                         | ⚠ 3 types            | ⚠ 3 types             | ⚠ BOTH BROKEN       |
| Trust-plane as separate layer                                                | ✓ separate crate     | ⚠ submodule           | Different structure |

## Convergence Recommendations

### Priority 1 (Critical — Both SDKs)

1. **Unify ConstraintEnvelope types**
   - Canonical: EATP's optional-per-dimension design (more flexible, matches spec)
   - Migrate trust-plane's flattened variant to derive from EATP type (Rust)
   - Migrate Python's 3 envelope types to single canonical form
   - Adds field-by-field compatibility adapter for serialization

2. **Extract `kailash-mcp`** (same target as other audits)
   - Consolidate EATP MCP server, nexus MCP server, trust-plane proxy, pact bridge onto a shared base
   - Define canonical JSON-RPC types once

### Priority 2 (Important — Both SDKs)

3. **Cross-SDK issue verification sweep**
   - Confirm all security fixes (#234-241, #199, #168-202) present in BOTH
   - File any missing fixes as `cross-sdk` issues

4. **Trust-plane layer clarification**
   - Rust: trust-plane is a separate crate from kailash-governance (intentional)
   - Python: kailash.trust.plane is a submodule of kailash.trust
   - Document why and align where possible

### No Refactor Needed

- GovernanceEngine ✓
- Addressing ✓
- 3-layer envelope model ✓ (wrappers are correct)
- 5-step access enforcement ✓
- Security fixes ✓
- PACT as engine composing primitives ✓

**PACT is the reference architecture in BOTH SDKs.** DataFlow, PACT, and the Kaizen composition-wrapper pattern are the three correct patterns.
