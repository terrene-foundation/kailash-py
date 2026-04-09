# Type System Enforcement

Patterns that catch bugs at compile time (Rust) or class-definition time (Python), before any code runs.

## Rust Patterns

### 1. `#[non_exhaustive]` on Public Enums

**Status in kailash-rs**: ABSENT. All public enums use default exhaustive matching.

**The problem**: When a new variant is added to an enum (e.g., `ProductMode::Streaming`), every `match` with a `_ =>` catchall silently swallows the new variant. The developer who added the variant has no way to find all the match sites that need updating. Found 11+ `_ =>` catchalls in kailash-rs bindings that would silently swallow new variants.

**The fix**: `#[non_exhaustive]` forces downstream crates to include a `_ =>` arm, but more importantly, it signals "this enum will grow" and makes catchall handling intentional rather than accidental.

```rust
// DO — new variants break downstream code at compile time
#[non_exhaustive]
pub enum ProductMode {
    Materialized,
    Parameterized,
    Virtual,
}

// Consumer MUST handle unknown variants explicitly
match mode {
    ProductMode::Materialized => ...,
    ProductMode::Parameterized => ...,
    ProductMode::Virtual => ...,
    _ => return Err(UnsupportedMode(mode)),  // intentional, not accidental
}

// DO NOT — new variants are silently swallowed
pub enum ProductMode {
    Materialized,
    Parameterized,
    Virtual,
}
// match mode { ... _ => () }  ← silent discard of future variants
```

**Scope**: All public enums across kailash-dataflow, kailash-nexus, kailash-auth, trust-plane, kaizen-agents. Estimated ~20-30 enum definitions.

**Effort**: 1 session. Zero runtime cost. Zero API breakage (adding the attribute is semver-compatible).

### 2. Typestate Builders for Mission-Critical Paths

**Status in kailash-rs**: ABSENT. All builders use `Option<T>` + runtime validation at `.build()`.

**The problem**: A developer can call `.build()` on a half-configured builder. The error surfaces at runtime, not compile time. Example: `DataFlowEngine::builder().build()` — no database URL set — panics at runtime.

**The fix**: Typestate pattern encodes "which fields have been set" in the type itself. `.build()` only exists on the type where all required fields are set.

```rust
// DO — compile-time enforcement
use std::marker::PhantomData;

struct Yes;
struct No;

struct DataFlowBuilder<HasUrl = No, HasPool = No> {
    url: Option<String>,
    pool_size: Option<u32>,
    _state: PhantomData<(HasUrl, HasPool)>,
}

impl DataFlowBuilder<No, No> {
    pub fn new() -> Self { /* ... */ }
}

impl<P> DataFlowBuilder<No, P> {
    pub fn url(self, url: &str) -> DataFlowBuilder<Yes, P> { /* ... */ }
}

impl<U> DataFlowBuilder<U, No> {
    pub fn pool_size(self, size: u32) -> DataFlowBuilder<U, Yes> { /* ... */ }
}

// .build() ONLY exists when both fields are set
impl DataFlowBuilder<Yes, Yes> {
    pub fn build(self) -> Result<DataFlow, ConfigError> { /* ... */ }
}

// DO NOT — runtime validation only
struct DataFlowBuilder {
    url: Option<String>,      // might be None at .build() time
    pool_size: Option<u32>,   // might be None at .build() time
}
impl DataFlowBuilder {
    pub fn build(self) -> Result<DataFlow, ConfigError> {
        let url = self.url.ok_or(ConfigError::MissingUrl)?;  // runtime panic
        // ...
    }
}
```

**Scope**: `DataFlowEngine::builder()`, `NexusApp::builder()`, trust envelope construction. ~4 builders.

**Effort**: 1-2 sessions. Requires new generic type parameters but no algorithm changes.

### 3. Newtype Wrappers in FFI Bindings

**Status in kailash-rs**: PARTIAL. Core SDK has `TenantId(String)`, `SecretString`. Bindings (PyO3, napi-rs, Magnus) use raw `String` — undoing the safety at the boundary.

**The problem**: A user calling from Python can pass `user_id` where `tenant_id` is expected. The Rust type system catches this in pure Rust, but the FFI boundary accepts raw strings.

```rust
// Core SDK — safe
pub fn with_tenant_id(&self, tenant_id: TenantId) -> Self { ... }
// Cannot pass UserId here — compiler error

// Binding — unsafe
#[pyfunction]
fn with_tenant_id(tenant_id: String) -> ... { ... }
// Can pass anything — no type safety
```

**The fix**: Introduce binding-level newtype wrappers.

```rust
// DO — PyO3 newtype
#[pyclass]
struct TenantIdPy(TenantId);

#[pymethods]
impl TenantIdPy {
    #[new]
    fn new(value: &str) -> PyResult<Self> {
        TenantId::try_from(value)
            .map(TenantIdPy)
            .map_err(|e| PyValueError::new_err(e.to_string()))
    }
}
```

**Scope**: TenantId, UserId, CorrelationId, RequestId across PyO3, napi-rs, Magnus bindings.

**Effort**: 2-3 sessions. Requires FFI specialist.

### 4. Sealed Traits for Security-Sensitive Types

**Status in kailash-rs**: PARTIAL. Trust envelope construction uses sealed patterns. Audit types do not.

**The problem**: A downstream consumer can construct a fake `AuditEntry` and insert it into the audit store, bypassing the governance layer.

**The fix**: Private `Sealed` trait prevents external implementations.

```rust
// DO — only internal types can create audit entries
pub trait AuditEvent: private::Sealed { ... }

mod private {
    pub trait Sealed {}
    impl Sealed for super::QueryAudit {}
    impl Sealed for super::MutationAudit {}
    // External types CANNOT implement Sealed
}

// DO NOT — anyone can implement AuditEvent
pub trait AuditEvent { ... }
// struct FakeAudit; impl AuditEvent for FakeAudit { ... }  ← undetectable
```

**Scope**: AuditEntry, PolicyEnvelope, TrustToken, GovernanceDecision.

## Python Patterns

### 5. `__init_subclass__` Contract Validation

**Status in kailash-py**: ABSENT. Extension points validated only at runtime method call.

**The problem**: A developer subclasses `BaseAgent` and misspells `handle` as `handel`. The typo is not caught until the agent is invoked at runtime.

**The fix**: `__init_subclass__` validates contracts when the class is defined.

```python
# DO — catch at class definition time
class BaseAgent:
    _required_methods = {"handle", "get_tools"}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        missing = cls._required_methods - {
            name for name, val in vars(cls).items()
            if callable(val)
        }
        if missing:
            raise TypeError(
                f"{cls.__name__} must implement: {', '.join(sorted(missing))}"
            )

# class BadAgent(BaseAgent):
#     def handel(self, msg): ...  # TypeError raised HERE, not at runtime

# DO NOT — validated only when called
class BaseAgent:
    def handle(self, msg):
        raise NotImplementedError  # only surfaces when agent is invoked
```

**Scope**: BaseAgent, BaseAdapter, BaseProvider, SignatureBase, BaseStrategy.

### 6. Structured Return Types (No Raw Dicts)

**Status in kailash-py**: PARTIAL. 25 files return `-> Dict[str, Any]`. 56 files use frozen dataclasses.

**The problem**: A caller accesses `result["stauts"]` (typo) on a `Dict[str, Any]` return — no error until runtime KeyError, possibly in production.

**The fix**: Replace raw dict returns with `@dataclass` or `TypedDict`.

```python
# DO — typed, discoverable, IDE-completable
@dataclass(frozen=True, slots=True)
class BulkResult:
    attempted: int
    succeeded: int
    failed: int
    errors: list[BulkError]

    @property
    def has_failures(self) -> bool:
        return self.failed > 0

# result.stauts  ← AttributeError at definition-time with pyright/mypy

# DO NOT — opaque, no IDE support, typos are silent
def bulk_create(...) -> Dict[str, Any]:
    return {"attempted": n, "succeeded": s, "failed": f, "errors": errs}
# result["stauts"]  ← KeyError at runtime in production
```

**Scope**: BulkResult, QueryResult, MigrationResult, EngineStats, SchemaInfo. ~25 return sites.

### 7. Frozen Configs by Default

**Status in kailash-py**: PARTIAL. 56 files use `frozen=True`. BaseAgentConfig, DataFlowEngine config are mutable.

**The problem**: Config object mutated after engine construction — engine uses stale config silently.

```python
# DO — immutable after creation
@dataclass(frozen=True, slots=True)
class DataFlowConfig:
    url: str
    pool_size: int = 10
    read_timeout: float = 30.0

# config.pool_size = 50  ← FrozenInstanceError

# DO NOT — mutable config
@dataclass
class DataFlowConfig:
    url: str
    pool_size: int = 10
# config.pool_size = 50  ← silent, engine still uses old value
```

**Scope**: All `*Config` dataclasses. Use `dataclasses.replace()` for derived configs.

## Priority Ranking

| Rank | Pattern                                | SDK | Effort     | Safety impact                                          |
| ---- | -------------------------------------- | --- | ---------- | ------------------------------------------------------ |
| 1    | `#[non_exhaustive]` on public enums    | rs  | 1 session  | Prevents silent variant swallowing across SDK versions |
| 2    | Structured return types (no raw dicts) | py  | 2 sessions | Eliminates KeyError-in-production class                |
| 3    | `__init_subclass__` validation         | py  | 1 session  | Catches extension-point typos at definition time       |
| 4    | Typestate builders                     | rs  | 2 sessions | Compile-time enforcement of required config            |
| 5    | Frozen configs by default              | py  | 1 session  | Prevents silent mutation                               |
| 6    | Newtype wrappers in bindings           | rs  | 3 sessions | Type safety across FFI boundary                        |
| 7    | Sealed traits for audit types          | rs  | 1 session  | Prevents fake audit entries                            |
