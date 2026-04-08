# Observability Primitives

Patterns that make silence impossible. Every operation either emits telemetry automatically or fails to compile/run.

## Principles

1. **Observable by default, silent by opt-in** — telemetry emits without developer action; `disable_telemetry=True` is the escape hatch
2. **Partial failure is WARN, not DEBUG** — any operation that completes with non-zero failures auto-escalates
3. **Every data fetch logs its source mode** — `mode=real|fake|cached` distinguishes real from synthetic data in every log line

## Patterns

### 1. Auto-Telemetry on Every Public Method

**Status**: ABSENT in both SDKs. Developers must manually add log lines to every endpoint.

**The problem**: A new `express.bulk_create()` method ships without any log line. In production, a bulk op processes 10,663 rows, 10,663 fail silently, and the first signal is a user reporting "my data isn't there." No log line exists to diagnose what happened.

**The fix**: A decorator/middleware that wraps every public method with structured telemetry.

```python
# DO — auto-instrumented
from dataflow.observability import auto_instrument

@auto_instrument(component="express")
async def create(self, model_name: str, data: dict) -> ModelResult:
    ...
    return result

# Automatically emits:
# INFO express.create.start model=User request_id=abc-123 tenant_id=t-456
# INFO express.create.ok    model=User request_id=abc-123 duration_ms=42 rows_affected=1
# ERROR express.create.error model=User request_id=abc-123 duration_ms=12 error=IntegrityError

# DO NOT — manual, optional, frequently forgotten
async def create(self, model_name: str, data: dict) -> ModelResult:
    # developer has to remember to add logging
    # new methods ship without it
    return await self._engine.create(model_name, data)
```

```rust
// Rust equivalent — tracing spans
use tracing::instrument;

#[instrument(skip(self), fields(model = %model_name))]
pub async fn create(&self, model_name: &str, data: Value) -> Result<Value, DataFlowError> {
    // tracing::Span automatically records entry, exit, duration, errors
    ...
}
```

**Industry precedent**: Rails logs every request with method/path/status/duration — zero config. OpenTelemetry auto-instrumentation patches HTTP clients and DB drivers without code changes. Phoenix (Elixir) emits `:telemetry` events from every Ecto query automatically.

**Scope**: All `express.*` methods, all Nexus endpoint handlers, all Kaizen agent.run() calls, all DataFlow migration steps.

**Contract**: Every instrumented method emits exactly 2 log lines (start + ok/error) with: component, operation, model/resource, correlation_id, tenant_id (if multi-tenant), duration_ms. Error lines add: error_type, error_message (NOT full stack — that goes to ERROR-level structured exception handler).

### 2. BulkResult Auto-WARN on Partial Failure

**Status**: CONFIRMED ABSENT by source audit. `bulk_create.py:496-498` has `except Exception: continue` with zero logging. `bulk_upsert.py:347` uses `print()` instead of a structured logger.

**The problem**: `BulkCreate` processes 10,663 rows. Each per-row exception is caught and silently discarded. The result dict contains `{"failed": 10663}` but no WARN log line fires. The operator's alerting pipeline (which watches WARN+ entries) sees nothing.

**The fix**: `BulkResult` auto-emits WARN when `failed > 0`.

```python
# DO — auto-WARN on construction
@dataclass(frozen=True, slots=True)
class BulkResult:
    operation: str
    model: str
    attempted: int
    succeeded: int
    failed: int
    errors: list[BulkError]
    correlation_id: str | None = None

    def __post_init__(self):
        if self.failed > 0:
            logger.warning(
                "bulk_op.partial_failure",
                operation=self.operation,
                model=self.model,
                attempted=self.attempted,
                succeeded=self.succeeded,
                failed=self.failed,
                first_error=str(self.errors[0]) if self.errors else "unknown",
                correlation_id=self.correlation_id,
            )

    def raise_if_any_failed(self) -> None:
        """Raise BulkPartialFailureError if any rows failed."""
        if self.failed > 0:
            raise BulkPartialFailureError(self)

# DO NOT — silent result dict
def bulk_create(...) -> dict:
    return {"attempted": n, "succeeded": s, "failed": f}
    # f=10663 and nobody knows
```

```rust
// Rust equivalent — #[must_use] + auto-warn
#[must_use = "bulk results with failures must be handled"]
pub struct BulkResult {
    pub attempted: u64,
    pub succeeded: u64,
    pub failed: u64,
    pub errors: Vec<BulkError>,
}

impl BulkResult {
    pub fn new(attempted: u64, succeeded: u64, failed: u64, errors: Vec<BulkError>) -> Self {
        let result = Self { attempted, succeeded, failed, errors };
        if result.failed > 0 {
            tracing::warn!(
                attempted = result.attempted,
                failed = result.failed,
                "bulk operation partial failure"
            );
        }
        result
    }
}
```

**Related rule**: `rules/observability.md` § 5 (log triage gate) catches WARN entries at phase boundaries. This primitive ensures the WARN entry exists for the gate to catch.

**Scope**: BulkCreate, BulkUpdate, BulkDelete, BulkUpsert — all nodes that process rows individually and continue past per-row failures.

### 3. Silent Exception Handler Detection

**Status**: kailash-py has ~1367 `except` clauses across 250 files. ~30% are silent (no log call after the catch). kailash-rs error handling is strong (per-crate error enums with `thiserror`).

**The problem**: `except Exception: continue` is the #1 cause of "it looked fine but data was corrupted" incidents. The exception fires, the handler swallows it, the operation appears to succeed.

**The fix (linter rule)**: A custom ruff rule or pre-commit hook that flags `except` blocks without a `logger.*` call.

```python
# FLAGGED BY LINTER — except without logging
try:
    process_row(row)
except Exception:
    continue  # ← linter: "exception caught without logging"

# PASSES LINTER — except with logging
try:
    process_row(row)
except Exception as e:
    logger.warning("row_processing.error", row_id=row.id, error=str(e))
    continue

# EXEMPT — cleanup paths (annotated)
try:
    temp_file.unlink()
except OSError:
    pass  # noqa: DQ001 — cleanup, failure expected
```

**Industry precedent**: Java's SpotBugs flags empty catch blocks. Go's `errcheck` linter flags ignored error returns. Rust's compiler warns on unused `Result` (no linter needed — it's built into the language).

**Scope**: Custom ruff rule or pre-commit check for kailash-py. Rust's `#[must_use]` on `Result` covers kailash-rs.

### 4. Metric Cardinality Limits

**Status**: ABSENT. No cardinality enforcement on Prometheus labels.

**The problem**: `requests_total.labels(tenant_id=tenant_id).inc()` — with 10,000 tenants, this creates 10,000 time series per metric. Prometheus OOMs at ~100K series on a typical instance. The metric system crashes right when you need it most — during traffic spikes.

**The fix**: Bounded label helper.

```python
# DO — bounded cardinality
class BoundedLabels:
    """Label helper that caps cardinality."""
    def __init__(self, max_unique: int = 100):
        self._max = max_unique
        self._seen: set[str] = set()

    def label(self, value: str) -> str:
        if len(self._seen) >= self._max and value not in self._seen:
            return "_other"
        self._seen.add(value)
        return value

tenant_labels = BoundedLabels(max_unique=100)
requests_total.labels(
    tenant_id=tenant_labels.label(tenant_id)
).inc()

# DO NOT — unbounded
requests_total.labels(tenant_id=tenant_id).inc()
# 10K tenants → 10K series → Prometheus OOM
```

**Related rule**: `rules/tenant-isolation.md` § 4 already mandates bounded cardinality. This primitive enforces it.

### 5. Correlation ID Propagation

**Status**: PARTIAL. `rules/observability.md` § MUST 2 mandates correlation IDs. Not auto-propagated.

**The problem**: A request enters Nexus, triggers a DataFlow query, which triggers a Kaizen agent call. Each component logs its own correlation ID (or none). Tracing the request across components requires manually correlating timestamps.

**The fix**: Context-variable-based auto-propagation.

```python
# DO — auto-propagation via contextvars
import contextvars

_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id")

def get_correlation_id() -> str:
    return _correlation_id.get("unset")

# Nexus middleware sets it once
@app.middleware("http")
async def correlation_middleware(request, call_next):
    cid = request.headers.get("x-request-id", str(uuid4()))
    token = _correlation_id.set(cid)
    try:
        response = await call_next(request)
        response.headers["x-request-id"] = cid
        return response
    finally:
        _correlation_id.reset(token)

# Every logger call picks it up automatically
logger = structlog.get_logger()
# structlog processor extracts _correlation_id from contextvars
# Every log line across DataFlow, Kaizen, Nexus carries the same ID
```

```rust
// Rust equivalent — tracing spans
use tracing::Span;

// Set at request entry
let span = tracing::info_span!("request", correlation_id = %cid);
let _guard = span.enter();

// All child spans inherit correlation_id automatically
// tracing::info!("query.start");  ← correlation_id is present
```

**Scope**: Nexus request middleware, DataFlow query executor, Kaizen agent loop, MCP tool dispatcher.

## Priority Ranking

| Rank | Pattern                             | SDK    | Effort     | Safety impact                                 |
| ---- | ----------------------------------- | ------ | ---------- | --------------------------------------------- |
| 1    | BulkResult auto-WARN                | py, rs | 1 session  | Eliminates silent bulk failure class entirely |
| 2    | Auto-telemetry decorator            | py, rs | 2 sessions | Makes every public method observable          |
| 3    | Silent exception detection (linter) | py     | 1 session  | Catches swallowed exceptions at commit time   |
| 4    | Correlation ID propagation          | py, rs | 1 session  | Makes cross-component tracing automatic       |
| 5    | Metric cardinality limits           | py, rs | 1 session  | Prevents Prometheus OOM at scale              |
