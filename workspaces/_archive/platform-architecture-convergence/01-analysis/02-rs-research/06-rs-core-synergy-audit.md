# kailash-rs Core + Cross-Crate Synergy Audit — 2026-04-07

## Crate Count: 48 (43 core + 5 language bindings)

## Primitive Layer (Zero Kailash Dependencies)

| Crate                     | Dependencies                                | Purpose                            |
| ------------------------- | ------------------------------------------- | ---------------------------------- |
| **kailash-value**         | `serde`, `serde_json`, `bytes`, `base64`    | Universal data type (`Value` enum) |
| **eatp**                  | `ed25519-dalek`, `sha2`, `zeroize`, `tokio` | Trust protocol primitives          |
| **kailash-rl**            | `ndarray`, `rand`                           | RL primitives (tabular, bandits)   |
| **kailash-plugin-macros** | `syn`, `quote`, `proc-macro2`               | Proc macros for plugin SDK         |

**Verdict**: Clean primitive layer. kailash-value is pure (0 kailash deps). eatp is foundational (0 kailash deps). These are the **true primitives** per framework-first.

## Core Engine Layer

### kailash-core

```rust
// Public API (from lib.rs)
pub use node::Node;                  // Node trait
pub use workflow::{Workflow, WorkflowBuilder};
pub use runtime::Runtime;            // level-based parallel execution via tokio
pub use registry::NodeRegistry;
pub use params::{ParamDef, ParamType};
pub use context::ExecutionContext;
```

**Built-in nodes**: NoOpNode, LogNode, HandlerNode, control_flow nodes, transform nodes

**Cargo.toml**:

```toml
[dependencies]
kailash-value                        # hard
petgraph                             # DAG
parking_lot                          # sync
serde, serde_json
tokio
opentelemetry, tracing
eatp = { optional = true }           # trust feature

[features]
yaml = []
trust = ["eatp"]
durability = ["sqlite", "postgres"]
telemetry = ["opentelemetry"]
```

**Verdict**: Only depends on kailash-value at core. `eatp` is optional via `trust` feature. Clean primitive layer.

## Node Extension Layer

### kailash-nodes (139+ nodes, 22 categories)

Categories:

- `http`, `file`, `ai`, `sql`, `admin`, `alerts`, `auth`, `monitoring`, `transaction`, `security`, `edge`, `enterprise`, `logic`, `cache`, `code`, `rag`, `kafka`, `redis`, `streaming`, `transform`, `vector`, `graph_db`, `document_store`

**CRITICAL VIOLATION**: `kailash-nodes` has a **HARD dependency on `kailash-enterprise`**:

```toml
[dependencies]
kailash-value
kailash-core
kailash-enterprise  # <-- INVERTED DEPENDENCY
```

This is because admin nodes (`admin/role_management.rs`, `admin/permission_check.rs`, `admin/audit_log.rs`) use enterprise features directly. Extension nodes should NOT hard-depend on enterprise — it breaks the layering.

**Fix options**:

- **A**: Create `kailash-nodes-enterprise` crate that depends on both kailash-nodes + kailash-enterprise
- **B**: Move admin node implementations to kailash-enterprise as node factories
- **C**: Make kailash-enterprise depend on kailash-nodes and provide admin node registration

**Recommendation**: Option A (cleanest separation)

## Framework Layer

```
kailash-dataflow      → kailash-core, kailash-value (NO trust/pact/governance)
kailash-nexus         → kailash-core, kailash-value (NO trust/pact/governance)
kailash-kaizen        → kailash-core, kailash-value, eatp (optional), kailash-enterprise (optional),
                        trust-plane (optional), kailash-pact (optional)
kaizen-agents         → kailash-core, kailash-value, kailash-kaizen, kailash-pact, eatp, trust-plane
```

Note: kaizen-agents **correctly depends on kailash-kaizen** (matches Python's target convergence).

## Trust/Governance Layer

```
eatp                  → standalone (0 kailash deps)
trust-plane           → eatp, kailash-enterprise (optional)
kailash-governance    → eatp
kailash-pact          → kailash-governance, eatp
```

## Enterprise Layer

```
kailash-enterprise    → kailash-value, kailash-core
```

Provides: RBAC, audit logging, multi-tenancy, SSO (OIDC, SAML).

## ML Layer (19 crates)

(See `05-rs-ml-audit.md` for full detail.)

## Plugin System

```
kailash-plugin         → kailash-value, kailash-core (WASM + native runtime)
kailash-plugin-guest   → kailash-plugin-macros (publishable SDK, cdylib + rlib)
kailash-plugin-macros  → proc-macro (0 kailash deps)
kailash-marketplace    → kailash-value, kailash-core, kailash-plugin
```

WASM-based plugins via `wasmtime` + `wasmtime-wasi`. Native plugins via `libloading`.

## C API Layer

```
kailash-capi          → kailash-core, kailash-nodes, kailash-value, kailash-dataflow,
                        kailash-enterprise, kailash-kaizen
                        (optional: trust-plane, eatp, kailash-pact, kaizen-agents,
                                   kailash-governance, kailash-nexus)
```

Provides C ABI bindings for C/C++/Go/C#/Ruby callers. Feature-gated for advanced capabilities.

## CLI Layer

```
kailash-cli           → kailash-core, kailash-value, kailash-nexus, kailash-nodes, kailash-plugin
                        (binary: `kailash`)
kz                    → kaizen-agents, kailash-kaizen, clap, crossterm, globset, regex, walkdir
                        (binary: `kz`)
```

**Key distinction**: `kailash-cli` is the general platform CLI; `kz` is a specialized L3 agent for code generation with governance. Per workspace Cargo.toml comments, `kz` was extracted to `terrene-foundation/kaizen-cli-rs` (Layer 2 separation).

## Language Bindings

```
kailash-python (PyO3)  → kailash-core, kailash-nodes, kailash-value, kailash-dataflow,
                          kailash-nexus, kailash-kaizen, kailash-enterprise, kailash-plugin,
                          eatp, trust-plane, kailash-governance (opt), kailash-pact (opt),
                          kaizen-agents (opt), kailash-align-serving (opt),
                          kailash-ml + 15 sub-crates (opt, full)
kailash-node (NAPI)    → kailash-core, kailash-dataflow, kailash-enterprise, kailash-kaizen,
                          kailash-governance, kailash-nexus, kailash-nodes, kailash-value,
                          trust-plane, eatp, kailash-pact (opt), kaizen-agents (opt)
kailash-ruby (FFI)     → similar to kailash-node
kailash-wasm           → kailash-value ONLY (lightweight)
```

**kailash-wasm is the model**: lightweight binding with a single dependency. Other bindings are heavy (12+ direct dependencies).

## Inverted/Circular Dependencies

| Issue                                                         | Severity     | Recommendation                                    |
| ------------------------------------------------------------- | ------------ | ------------------------------------------------- |
| **kailash-nodes → kailash-enterprise (HARD)**                 | **CRITICAL** | Extract admin nodes to `kailash-nodes-enterprise` |
| kailash-kaizen → kailash-enterprise (OPTIONAL, feature-gated) | Low          | OK — intentional                                  |
| trust-plane → kailash-enterprise (OPTIONAL)                   | Low          | OK — intentional                                  |
| kailash-capi multi-feature facade                             | Low          | OK — design pattern                               |

**No circular dependencies detected.** Only ONE critical issue: kailash-nodes hard dependency on kailash-enterprise.

## Cross-SDK Hierarchy Comparison

| Layer                         | Python                               | Rust                                                              |
| ----------------------------- | ------------------------------------ | ----------------------------------------------------------------- |
| **Specs**                     | CARE, EATP, CO, PACT                 | CARE, EATP, CO, PACT                                              |
| **Primitives**                | `kailash` (Core SDK: zero hard deps) | `kailash-value` + `eatp` + `kailash-rl` (all zero kailash deps)   |
| **Core engine**               | `kailash`                            | `kailash-core`                                                    |
| **Nodes**                     | Built into `kailash.nodes` (140+)    | `kailash-nodes` (139+, inverted dep)                              |
| **DataFlow**                  | `kailash-dataflow`                   | `kailash-dataflow`                                                |
| **Nexus**                     | `kailash-nexus`                      | `kailash-nexus`                                                   |
| **Kaizen L1 (SDK)**           | `kailash-kaizen`                     | `kailash-kaizen`                                                  |
| **Kaizen L2 (orchestration)** | `kaizen-agents`                      | `kaizen-agents`                                                   |
| **Enterprise**                | (absorbed into other packages)       | `kailash-enterprise` (standalone)                                 |
| **Trust**                     | `kailash.trust.*` (submodules)       | `eatp` + `trust-plane` + `kailash-governance` (3 separate crates) |
| **PACT**                      | `kailash-pact` (package)             | `kailash-pact` + `kailash-governance`                             |
| **ML**                        | `kailash-ml` (monolithic package)    | 19 separate crates (meta-crate + 18 algorithm crates)             |
| **Plugin system**             | (none explicit)                      | `kailash-plugin` + WASM + native                                  |
| **C API**                     | (via ctypes)                         | `kailash-capi`                                                    |
| **CLI**                       | (via dev tooling)                    | `kailash-cli` + `kz`                                              |
| **Language bindings**         | (native)                             | Python/Node/Ruby/WASM                                             |

**Key differences**:

1. **Rust is more modular**: Separate crates for value, trust, governance, ML, plugin
2. **Python is simpler**: Fewer boundaries, more integrated
3. **Rust trust stack is standalone**: `eatp` can be used without kailash-core
4. **Python's inversion is BETTER**: Node definitions don't hard-depend on enterprise features
5. **Rust's ML framework is native**: Python integrates scikit-learn

## Architectural Health Verdict

**Rust is MORE CORRECT in structure**, except for:

- **kailash-nodes → kailash-enterprise inversion** (critical)
- **Heavy binding facades** (kailash-python pulls in 12+ direct + 15 optional deps)
- **3 ConstraintEnvelope types** (same problem as Python)
- **3 MCP systems** (same fragmentation as Python)
- **ML gaps** (no domain agents, drift monitor, fine-tuning pipeline)

**Python is SIMPLER** but less modular:

- Core SDK has no external framework dependencies (verified)
- Fewer crate boundaries to manage
- Weaker separation of concerns for trust (all in kailash.trust submodules)

## Convergence Recommendations

### For Rust (kailash-rs)

1. **FIX CRITICAL INVERSION**: Extract admin nodes from kailash-nodes
2. **Reduce binding complexity**: Split kailash-python into `_kailash_core` (thin) and `_kailash_full` (facade)
3. **Unify 3 ConstraintEnvelope types** (in lockstep with Python)
4. **Extract `kailash-mcp` crate** (in lockstep with Python)
5. **Fill ML gaps** (kailash-ml-agents, kailash-ml-drift, kailash-align-training, complete kailash-ml-python bindings)
6. **Fix zero-tolerance violations**:
   - `kailash-nodes/src/enterprise/mcp_executor.rs` (simulated execution)
   - `kz/src/mcp_bridge.rs` (stubbed integration)

### For Python (kailash-py)

1. **Extract `packages/kailash-mcp/`** (in lockstep with Rust)
2. **Split `ai_providers.py` monolith** → `kaizen/providers/` per-provider modules
3. **Add composition wrappers** (StreamingAgent, MonitoredAgent, L3GovernedAgent)
4. **Slim BaseAgent + deprecate 7 extension points** (Option B confirmed)
5. **Consolidate audit implementations** (5+ → 1 canonical `kailash.trust.AuditStore`)
6. **Unify 3 ConstraintEnvelope types** (in lockstep with Rust)
7. **Migrate Nexus auth to `kailash.trust`** (lockstep with Rust's equivalent)

### Cross-SDK Alignment (Lockstep)

1. **Cross-reference every convergence issue** — file `cross-sdk` labels on both repos
2. **Define canonical types ONCE** — JSON-RPC, ConstraintEnvelope, BaseAgent trait, Provider interface
3. **Implement in both SDKs with matching semantics** (per EATP D6)
4. **Cross-validate via integration tests** that round-trip messages between Python client and Rust server

## Summary: Full 48-Crate Dependency DAG

```
LAYER 0: PRIMITIVES (zero kailash deps)
├── kailash-value
├── eatp
├── kailash-rl
└── kailash-plugin-macros

LAYER 1: CORE + PLUGINS
├── kailash-core → kailash-value, eatp (opt)
├── kailash-plugin → kailash-value, kailash-core
├── kailash-plugin-guest → kailash-plugin-macros
└── kailash-macros → (proc-macro only)

LAYER 2: EXTENSION NODES + DATA
├── kailash-nodes → kailash-value, kailash-core, kailash-enterprise (★ INVERTED)
├── kailash-dataflow → kailash-value, kailash-core
└── kailash-marketplace → kailash-value, kailash-core, kailash-plugin

LAYER 3: FRAMEWORKS
├── kailash-nexus → kailash-value, kailash-core
├── kailash-kaizen → kailash-value, kailash-core, eatp (opt), trust-plane (opt), kailash-pact (opt)
└── kaizen-agents → kailash-value, kailash-core, kailash-kaizen, kailash-pact, eatp, trust-plane

LAYER 4: ENTERPRISE
└── kailash-enterprise → kailash-value, kailash-core

LAYER 5: TRUST + GOVERNANCE
├── trust-plane → eatp
├── kailash-governance → eatp
└── kailash-pact → kailash-governance, eatp

LAYER 6: ML (19 crates)
└── kailash-ml + sub-crates (see 05-rs-ml-audit.md)

LAYER 7: C API
└── kailash-capi → kailash-core, kailash-nodes, ...

LAYER 8: CLI
├── kailash-cli → kailash-core, kailash-nexus, kailash-nodes, kailash-plugin
└── kz → kaizen-agents, kailash-kaizen

LAYER 9: LANGUAGE BINDINGS
├── kailash-python (PyO3) — heavy facade
├── kailash-node (NAPI) — heavy facade
├── kailash-ruby (FFI) — heavy facade
└── kailash-wasm — lightweight (value only)
```

## Cross-SDK Action Items

| Action                    | Python                                                      | Rust                                            |
| ------------------------- | ----------------------------------------------------------- | ----------------------------------------------- |
| Extract `kailash-mcp`     | Create `packages/kailash-mcp/`                              | Create `crates/kailash-mcp/`                    |
| Unify ConstraintEnvelope  | Merge 3 types into 1                                        | Merge 3 types into 1                            |
| Consolidate audit         | Use `kailash.trust.AuditStore` canonical                    | Use `eatp::audit` canonical                     |
| Fix admin nodes inversion | N/A (Python has no inversion)                               | Extract `kailash-nodes-enterprise`              |
| Fix zero-tolerance stubs  | Fix #339 (BaseAgent MCP)                                    | Fix `mcp_executor.rs` simulated execution       |
| ML gaps                   | Stay as-is (Python is complete)                             | Add ml-agents, ml-drift, align-training         |
| Provider modularization   | Split ai_providers.py                                       | Add Ollama/Cohere/HF/Perplexity/Docker adapters |
| Composition wrappers      | Add StreamingAgent/MonitoredAgent/L3GovernedAgent in Python | Already has them (canonical pattern)            |
| Binding reduction         | N/A                                                         | Split kailash-python into core + full           |
