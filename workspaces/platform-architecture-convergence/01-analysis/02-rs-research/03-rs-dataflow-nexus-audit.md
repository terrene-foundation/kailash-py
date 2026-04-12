# kailash-rs DataFlow + Nexus Audit — 2026-04-07

## Verdict: Correct Composition — Matches Python Pattern

Both `DataFlowEngine` and `NexusEngine` in Rust follow the correct composition pattern (engine takes primitive as constructor input).

## Part A: kailash-dataflow Crate

### Structure

```
crates/kailash-dataflow/src/
├── lib.rs
├── engine.rs         — DataFlowEngine (builder pattern wrapper)
├── connection.rs     — DataFlow primitive (core connection manager)
├── express.rs        — DataFlowExpress (convenience CRUD API)
├── fabric.rs         — DataFabricEngine (highest abstraction)
├── model.rs          — ModelDefinition (schema builder)
├── nodes/
│   ├── crud.rs       — 7 CRUD node factories
│   └── bulk.rs       — 4 bulk operation factories
├── tenancy/          — Multi-tenant query interception
├── validation.rs     — Field-level validation rules
├── classification.rs — Data classification + retention
├── query_engine.rs   — Query performance monitoring
└── transaction.rs    — ACID transaction management
```

**Cargo.toml**: Depends on `kailash-core`, `kailash-value`, `sqlx`. **Zero dependencies** on eatp, trust-plane, kailash-pact, kailash-governance.

### DataFlow Primitive

```rust
pub struct DataFlow {
    pool: AnyPool,
    dialect: QueryDialect,
    config: DataFlowConfig,
    pub(crate) models: Vec<Arc<ModelDefinition>>,
    monitor: std::sync::Mutex<Option<PoolMonitorHandle>>,
    leak_detector: std::sync::Mutex<Option<LeakDetectorHandle>>,
    cache: Option<Arc<QueryCache>>,
    lightweight_pool: Option<AnyPool>,
    owns_pool: bool,
    validation_layer: ValidationLayer,
    pub(crate) derived_model_defs: Vec<Arc<DerivedModelDefinition>>,
    replica_pool: Option<AnyPool>,
    replica_healthy: Arc<AtomicBool>,
    replica_health_handle: Mutex<Option<JoinHandle<()>>>,
}

impl DataFlow {
    pub async fn new(database_url: &str) -> Result<Self, DataFlowError>;
    pub async fn from_env() -> Result<Self, DataFlowError>;
    pub async fn from_config(config: DataFlowConfig) -> Result<Self, DataFlowError>;

    pub fn register_model(&self, model: ModelDefinition) -> Result<(), DataFlowError>;
    pub async fn execute_raw(&self, sql: &str) -> Result<u64, DataFlowError>;
    pub async fn health_check(&self) -> HealthStatus;
    pub fn pool(&self) -> &AnyPool;
    pub fn dialect(&self) -> QueryDialect;
}
```

### DataFlowEngine (Composition Verified)

```rust
pub struct DataFlowEngine {
    dataflow: DataFlow,                               // COMPOSED PRIMITIVE
    validation: Option<Arc<ValidationLayer>>,
    classification: Option<Arc<DataClassificationPolicy>>,
    query_engine: QueryEngine,
}

impl DataFlowEngine {
    pub fn builder(database_url: &str) -> DataFlowEngineBuilder;
    pub fn dataflow(&self) -> &DataFlow;              // access the composed primitive
    pub fn validation(&self) -> Option<&ValidationLayer>;
    pub fn classification(&self) -> Option<&DataClassificationPolicy>;
    pub fn query_engine(&self) -> &QueryEngine;
    pub fn register_model(&self, registry: &mut NodeRegistry, model: Arc<ModelDefinition>);
    pub async fn health_check(&self) -> HealthStatus;
    pub async fn close(&self);
}

pub struct DataFlowEngineBuilder {
    database_url: String,
    validation: Option<Arc<ValidationLayer>>,
    classification: Option<Arc<DataClassificationPolicy>>,
    slow_query_threshold: Duration,
}

impl DataFlowEngineBuilder {
    pub async fn build(self) -> Result<DataFlowEngine, DataFlowError> {
        let dataflow = DataFlow::new(&self.database_url).await?;   // CREATE primitive
        Ok(DataFlowEngine {
            dataflow,                                              // WRAP primitive
            validation: self.validation,
            classification: self.classification,
            query_engine: QueryEngine::new(self.slow_query_threshold),
        })
    }
}
```

**Composition verdict**: ✓ Pure composition. DataFlowEngine **delegates** all database operations to the wrapped DataFlow.

### Auto-Generated Nodes (11 per model)

| CRUD (7)      | Bulk (4)          |
| ------------- | ----------------- |
| Create{Model} | BulkCreate{Model} |
| Read{Model}   | BulkUpdate{Model} |
| Update{Model} | BulkDelete{Model} |
| Delete{Model} | BulkUpsert{Model} |
| List{Model}   |                   |
| Upsert{Model} |                   |
| Count{Model}  |                   |

Registration via runtime builder API (no proc macros). Matches Python's pattern.

### DataFabricEngine (Rust Has This!)

**File**: `crates/kailash-dataflow/src/fabric.rs`

Highest-abstraction layer that composes DataFlow + Express + QueryEngine + classification + retention. Features:

- Source adapter registration with circuit breaker
- Automatic retry and fallback logic
- Event bus integration
- Per-model retention policy enforcement

**Parity with Python**: Full (Python's Data Fabric Engine is NOT Python-only).

## Part B: kailash-nexus Crate

### Structure

```
crates/kailash-nexus/src/
├── lib.rs
├── engine.rs           — NexusEngine (builder pattern wrapper)
├── nexus.rs            — Nexus primitive (multi-channel handler registry)
├── handler/            — Handler trait + ClosureHandler
├── api/                — HTTP channel (axum routes)
├── cli/                — CLI channel (clap commands)
├── mcp/                — MCP channel (86KB server.rs + transports)
├── auth/               — Auth system (jwt, rbac, api_key, saml, rate_limit, plugin)
├── middleware/         — audit_mw, metrics_mw, csrf, security_headers
├── session/            — Session management
├── websocket.rs        — WebSocket support
├── events/             — Event bus system
├── health/             — K8s probes + health checks
└── scheduler.rs        — Scheduled task execution
```

**Cargo.toml**: Depends on `kailash-core`, `kailash-value`, `axum`, `tokio`, `tower`, `jsonwebtoken`. **Zero dependencies** on eatp, trust-plane, kailash-pact, kailash-governance.

### Nexus Primitive

```rust
pub struct Nexus {
    handlers: Vec<Arc<HandlerDef>>,
    endpoints: Vec<Arc<EndpointDef>>,
    config: NexusConfig,
    middleware: MiddlewareConfig,
    plugins: Vec<Arc<dyn NexusPlugin>>,
    workflow_registry: WorkflowRegistry,
    event_bus: EventBus,
    custom_routers: Vec<(Router, String, Vec<String>)>,
    k8s_probes: Option<(K8sProbeConfig, K8sProbeState)>,
    background_services: BackgroundServiceRegistry,
    session_store: Option<(Arc<dyn SessionStore>, SessionConfig)>,
    ws_routes: Vec<(String, Router)>,
    event_listeners: Vec<(Option<String>, EventListenerFn)>,
    pending_scheduled_tasks: Vec<ScheduledTask>,
    has_auth_plugin: bool,
}

impl Nexus {
    pub fn new() -> Self;
    pub fn handler(&mut self, name: &str, func: impl HandlerFn + 'static) -> &mut Self;
    pub fn handler_with_description(&mut self, name: &str, desc: &str, func: impl HandlerFn) -> &mut Self;
    pub fn with_config(mut self, config: NexusConfig) -> Self;
    pub fn preset(mut self, preset: Preset) -> Self;
    pub fn middleware(mut self, config: MiddlewareConfig) -> Self;
    pub fn handler_count(&self) -> usize;
    pub fn set_auth_plugin(&mut self, plugin: Arc<dyn NexusPlugin>);
}
```

### NexusEngine (Composition Verified)

```rust
pub struct NexusEngine {
    nexus: Nexus,                                     // COMPOSED PRIMITIVE
    enterprise_config: Option<EnterpriseMiddlewareConfig>,
    bind_addr: String,
}

impl NexusEngine {
    pub fn builder() -> NexusEngineBuilder;
    pub fn nexus(&self) -> &Nexus;
    pub fn nexus_mut(&mut self) -> &mut Nexus;
    pub fn bind_addr(&self) -> &str;
    pub fn enterprise_config(&self) -> Option<&EnterpriseMiddlewareConfig>;
}

pub struct NexusEngineBuilder {
    preset: Preset,
    enterprise_config: Option<EnterpriseMiddlewareConfig>,
    bind_addr: String,
    nexus_config: NexusConfig,
}

impl NexusEngineBuilder {
    pub fn build(self) -> NexusEngine {
        let middleware_config = MiddlewareConfig::from_preset(self.preset);
        let mut nexus = Nexus::new().with_config(self.nexus_config);
        nexus.set_middleware(middleware_config);

        NexusEngine {
            nexus,                                    // WRAP primitive
            enterprise_config: self.enterprise_config,
            bind_addr: self.bind_addr,
        }
    }
}
```

**Composition verdict**: ✓ Pure composition.

## Nexus Auth System (Native, Not Consuming External Crates)

**Same pattern as Python Nexus** — Nexus implements its own auth/audit/rate_limit natively:

| Module                     | File                                             | Duplicates What Should Be in Trust? |
| -------------------------- | ------------------------------------------------ | ----------------------------------- |
| `auth/jwt.rs`              | JWT (HS256, RS256, claims)                       | Yes (same problem as Python)        |
| `auth/rbac.rs`             | Role-based access control                        | Yes                                 |
| `auth/api_key.rs`          | API key validation                               | Yes                                 |
| `auth/rate_limit.rs`       | Token bucket per user/IP                         | Yes                                 |
| `auth/saml.rs`             | SAML SSO                                         | Yes                                 |
| `auth/plugin.rs`           | Auth plugin interface                            | (extensibility point)               |
| `middleware/audit_mw.rs`   | Audit logging (actor, action, outcome, duration) | Yes                                 |
| `middleware/metrics_mw.rs` | Prometheus metrics                               | No (ecosystem-specific)             |
| `middleware/csrf.rs`       | CSRF protection                                  | Ecosystem-specific                  |

**Verdict**: Rust Nexus has the **same architectural duplication as Python Nexus**. Both should migrate to consume from `kailash.trust.*` (Python) / `eatp` + shared auth crate (Rust).

## PACT Integration in Nexus

**Zero PACT integration in Rust Nexus** (grep confirms no references to `pact`, `governance`, `envelope`, `operating`). Same gap as Python.

## MCP Integration in Nexus

Nexus has a built-in MCP server in `crates/kailash-nexus/src/mcp/`:

- `server.rs` (86KB) — Transport-agnostic MCP JSON-RPC 2.0 server
- `sse.rs`, `stdio.rs`, `http_transport.rs` — Transport handlers
- `auth.rs` — MCP-specific auth

**Relationship to kailash-kaizen MCP**:

- `kailash-kaizen` owns the MCP **client** (`src/mcp/client.rs`)
- `kailash-nexus` owns an MCP **server** (`src/mcp/server.rs`)
- Both define their own JSON-RPC types (**duplication**)
- kailash-mcp crate does NOT exist

Same fragmentation as Python. Both SDKs need `kailash-mcp` extraction.

## Dependency Graph Summary

```
kailash-dataflow
├── kailash-core
├── kailash-value
├── sqlx
└── [NO eatp, trust-plane, kailash-pact, kailash-governance]

kailash-nexus
├── kailash-core
├── kailash-value
├── axum + tower + tokio
├── jsonwebtoken
└── [NO eatp, trust-plane, kailash-pact, kailash-governance]
```

## Same Problems as Python? Per-Area Verdict

| Area                                       | Rust                           | Python                      | Parity                    |
| ------------------------------------------ | ------------------------------ | --------------------------- | ------------------------- |
| DataFlowEngine composition                 | ✓ correct                      | ✓ correct                   | ✓ MATCH                   |
| NexusEngine composition                    | ✓ correct                      | ✓ correct                   | ✓ MATCH                   |
| Auto-generated CRUD nodes (11)             | ✓                              | ✓                           | ✓ MATCH                   |
| Express API (fast CRUD)                    | ✓                              | ✓                           | ✓ MATCH                   |
| Data Fabric Engine                         | ✓                              | ✓                           | ✓ MATCH                   |
| Multi-tenancy                              | ✓ native tenancy module        | ✓ native tenancy            | ✓ MATCH                   |
| Validation layer                           | ✓ native                       | ✓ native                    | ✓ MATCH                   |
| Nexus auth (JWT/RBAC/SSO/rate_limit/audit) | ⚠ native (duplicates trust)    | ⚠ native (duplicates trust) | ⚠ BOTH BROKEN             |
| PACT integration in Nexus                  | ❌ missing                     | ❌ missing                  | ❌ BOTH MISSING           |
| MCP client                                 | 1 (kailash-kaizen)             | 2 (parallel)                | Python worse              |
| MCP server                                 | 3+ (fragmented JSON-RPC types) | 7+ (fragmented)             | Both broken, Python worse |

## Convergence Implications

1. **DataFlow and Nexus engine composition stays as-is** in both SDKs — they're already correct
2. **Auth/audit migration** must happen in BOTH SDKs in lockstep:
   - Python: Migrate `nexus/auth/*` to consume `kailash.trust.*`
   - Rust: Create shared auth crate (or move into eatp/trust-plane), migrate `kailash-nexus/src/auth/*` to consume it
3. **PACT middleware** must be added to BOTH:
   - Python: `nexus/middleware/governance.py` with PACTMiddleware
   - Rust: `kailash-nexus/src/middleware/governance.rs` with PACT bridge
4. **MCP consolidation** in BOTH via `kailash-mcp` package/crate
