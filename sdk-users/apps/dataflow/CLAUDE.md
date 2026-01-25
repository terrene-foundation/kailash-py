# Kailash DataFlow - Complete Function Access Guide (v0.10.15 Stable)

**Current Version: v0.10.15 - Production Ready**
- **🔇 LOGGING CONFIGURATION (v0.10.12)**: `LoggingConfig` for centralized log level control - 524 noisy warnings eliminated
- **✅ DOCKER/FASTAPI (v0.10.15+)**: `auto_migrate=True` NOW WORKS! Uses `SyncDDLExecutor` with psycopg2/sqlite3 for DDL, bypassing event loop issues
- **⚠️ IN-MEMORY SQLITE**: `:memory:` databases skip sync DDL and use lazy table creation (sync DDL requires separate connection = different database)
- **🚀 SOFT DELETE AUTO-FILTER (v0.10.6)**: soft_delete models now auto-filter queries - use `include_deleted=True` to override
- **🚀 TIMESTAMP AUTO-STRIP (v0.10.6)**: `created_at`/`updated_at` now auto-stripped with warning (no more DF-104 errors!)
- **PYTEST COMPATIBILITY**: Fixed model registration race condition (v0.9.7)
- **MYSQL SUPPORT**: Full MySQL support with 100% feature parity (aiomysql driver)
- **THREE DATABASES**: PostgreSQL, MySQL, and SQLite with identical 11 nodes per model
- DateTime serialization issues resolved
- PostgreSQL parameter type casting improved
- VARCHAR(255) limits removed (now TEXT with unlimited content)
- Workflow connection parameter order fixed
- **STRING ID SUPPORT**: No more forced integer conversion - string IDs preserved
- **MULTI-INSTANCE ISOLATION**: Multiple DataFlow instances with proper context isolation
- **DEFERRED SCHEMA OPERATIONS**: Synchronous registration, async table creation
- **CONTEXT-AWARE TABLE CREATION**: Node-instance coupling for context preservation

**🔮 Coming Soon: Vector & Document Database Support**
- **pgvector** (Next release): PostgreSQL vector similarity search for RAG/AI applications
- **MongoDB**: Document database with PyMongo Async API for flexible schema applications
- **Qdrant**: Dedicated vector database for billion-scale semantic search
- **Neo4j**: Graph database for relationship-heavy data models

## 🚨 #1 MOST COMMON MISTAKE: Auto-Managed Timestamp Fields ✅ FIXED in v0.10.6

**v0.10.6+ automatically handles this! Fields are auto-stripped with warning.**

```python
# v0.10.6+: This now WORKS (with warning) instead of failing
async def update_record(self, id: str, data: dict):
    now = datetime.now(UTC).isoformat()
    data["updated_at"] = now  # ⚠️ Auto-stripped with warning

    workflow.add_node("ModelUpdateNode", "update", {
        "filter": {"id": id},
        "fields": data  # ✅ Works! updated_at is auto-removed
    })
```

**Warning message logged:**
```
⚠️ AUTO-STRIPPED: Fields ['updated_at'] removed from update. DataFlow automatically
manages created_at/updated_at timestamps. Remove these fields from your code.
```

**Best Practice (avoid warning):**
```python
# ✅ BEST - Don't set timestamps at all
async def update_record(self, id: str, data: dict):
    # DataFlow handles timestamps automatically - no need to set them
    workflow.add_node("ModelUpdateNode", "update", {
        "filter": {"id": id},
        "fields": data
    })
```

## ⚠️ Common Mistakes (Critical)

| Mistake | Impact | Solution |
|---------|--------|----------|
| **Manually setting `created_at`/`updated_at`** | ⚠️ Warning | **v0.10.6+ auto-strips with warning** - remove from code to avoid warning |
| **Using `user_id` or `model_id` instead of `id`** | 10-20 min debugging | **MUST use `id`** (not `user_id`, `agent_id`, etc.) |
| **Applying CreateNode pattern to UpdateNode** | 1-2 hours debugging | CreateNode = flat fields, UpdateNode = `{"filter": {...}, "fields": {...}}` |
| **Wrong node naming** | Node not found | Use `ModelOperationNode` (e.g., `UserCreateNode`) |
| **Wrong result key for ListNode** | Empty results | ListNode → `records`, CountNode → `count`, ReadNode → direct dict |

**Critical Rules**:
1. **Timestamp fields (v0.10.6+)** - Auto-stripped with warning; don't set them for clean logs
2. **Primary key MUST be `id`** - DataFlow requires this exact name
3. **CreateNode ≠ UpdateNode** - Different parameter patterns
4. **Node naming** - Always `ModelOperationNode` pattern (v0.6.0+)
5. **soft_delete (v0.10.6+)** - Auto-filters queries! Use `include_deleted=True` to see deleted records
6. **Result keys** - ListNode: `records`, CountNode: `count`, ReadNode: direct record

## 🔍 Query Operators for NULL Checking (v0.10.6+)

```python
# Filter for NULL values (e.g., non-deleted records in soft-delete pattern)
workflow.add_node("PatientListNode", "active", {
    "filter": {"deleted_at": {"$null": True}}  # WHERE deleted_at IS NULL
})

# Filter for NOT NULL values
workflow.add_node("PatientListNode", "deleted", {
    "filter": {"deleted_at": {"$exists": True}}  # WHERE deleted_at IS NOT NULL
})

# Alternative: $eq with None (v0.10.6+)
workflow.add_node("PatientListNode", "active", {
    "filter": {"deleted_at": {"$eq": None}}  # Also generates IS NULL
})
```

**⚠️ Important**: `soft_delete: True` in model config ONLY affects DeleteNode operations. It does NOT auto-filter queries. You MUST manually add `deleted_at` filters to ListNode/ReadNode queries.

## 🔇 CENTRALIZED LOGGING CONFIGURATION (v0.10.12 - NEW)

Control log verbosity with `LoggingConfig` for cleaner output. Eliminates 524+ noisy diagnostic messages that were incorrectly logged at WARNING level.

### Quick Usage
```python
import logging
from dataflow import DataFlow, LoggingConfig

# Option 1: Simple log level (quick control)
db = DataFlow("postgresql://...", log_level=logging.WARNING)

# Option 2: Full configuration object
config = LoggingConfig.production()  # Only WARNING and above
db = DataFlow("postgresql://...", log_config=config)

# Option 3: Environment variables (12-factor app pattern)
# Set in .env or shell:
# DATAFLOW_LOG_LEVEL=WARNING
# DATAFLOW_NODE_EXECUTION_LOG_LEVEL=ERROR
# DATAFLOW_SQL_GENERATION_LOG_LEVEL=WARNING
config = LoggingConfig.from_env()
db = DataFlow("postgresql://...", log_config=config)
```

### Configuration Presets

| Preset | Behavior | Use Case |
|--------|----------|----------|
| `LoggingConfig.production()` | Only WARNING+ | Production deployments |
| `LoggingConfig.development()` | DEBUG for all | Local development |
| `LoggingConfig.quiet()` | Only ERROR+ | Testing with minimal output |
| `LoggingConfig.from_env()` | Environment-based | Docker/Kubernetes |

### Category-Specific Logging

Fine-grained control over different subsystems:

```python
import logging
from dataflow import LoggingConfig

config = LoggingConfig(
    level=logging.WARNING,           # Default for all categories
    node_execution=logging.ERROR,    # Node execution traces (only errors)
    sql_generation=logging.WARNING,  # SQL generation diagnostics
    list_operations=logging.WARNING, # ListNode field ordering info
    migration=logging.INFO,          # Migration operations
    core=logging.WARNING             # Core DataFlow operations
)
```

### Sensitive Value Masking

Automatic security for logged data:

```python
from dataflow import LoggingConfig, mask_sensitive

config = LoggingConfig(
    mask_sensitive_values=True,
    sensitive_patterns=["password", "api_key", "secret", "token", "authorization"]
)

# Usage
data = {"username": "alice", "password": "secret123", "api_key": "sk-xxx"}
masked = mask_sensitive(data, config)
# Result: {'username': 'alice', 'password': '***MASKED***', 'api_key': '***MASKED***'}
```

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATAFLOW_LOG_LEVEL` | Default level | `WARNING`, `INFO`, `DEBUG` |
| `DATAFLOW_NODE_EXECUTION_LOG_LEVEL` | Node execution | `ERROR` |
| `DATAFLOW_SQL_GENERATION_LOG_LEVEL` | SQL generation | `WARNING` |
| `DATAFLOW_LIST_OPERATIONS_LOG_LEVEL` | List operations | `WARNING` |
| `DATAFLOW_MIGRATION_LOG_LEVEL` | Migrations | `INFO` |
| `DATAFLOW_CORE_LOG_LEVEL` | Core operations | `WARNING` |
| `DATAFLOW_MASK_SENSITIVE` | Enable masking | `true`, `1` |

### Programmatic Control

```python
from dataflow import configure_dataflow_logging, restore_dataflow_logging

# Apply configuration manually (useful for testing)
configure_dataflow_logging(LoggingConfig.quiet())

# Restore original logging levels
restore_dataflow_logging()
```

---

## 🛠️ DEVELOPER EXPERIENCE TOOLS (v0.8.0 - NEW)

### ErrorEnhancer: Actionable Error Messages

Automatic error enhancement with context, causes, and solutions:

```python
from dataflow import DataFlow

db = DataFlow("postgresql://...")

# ErrorEnhancer automatically integrated - no setup needed
# Enhanced errors show:
# - Error code (DF-101, DF-102, etc.)
# - Context (node, parameters, workflow state)
# - Root causes with probability scores
# - Actionable solutions with code templates
# - Documentation links
```

**Common Error Codes**:
- **DF-101**: Missing required parameter → Shows which connection to add
- **DF-102**: Type mismatch → Shows expected vs received types
- **DF-103**: Auto-managed field conflict → **Remove `created_at`/`updated_at` from your data!**
- **DF-104**: UpdateNode parameter error → **Most often caused by manually setting `updated_at`!**
- **DF-105**: Primary key 'id' missing → Explains 'id' requirement
- **DF-201**: Invalid connection → Shows correct output names
- **DF-301**: Migration failed → Provides safe recovery steps

**See**: `sdk-users/apps/dataflow/troubleshooting/top-10-errors.md` for complete guide

---

### Inspector API: Self-Service Debugging

Introspection API for debugging workflows without reading source code:

```python
from dataflow.platform.inspector import Inspector

inspector = Inspector(dataflow_instance)
inspector.workflow_obj = workflow.build()

# Connection Analysis (5 methods)
connections = inspector.connections()  # List all connections
broken = inspector.find_broken_connections()  # Find issues
is_valid, issues = inspector.validate_connections()  # Check validity

# Parameter Tracing (5 methods)
trace = inspector.trace_parameter("create_user", "data")
print(f"Parameter originates from: {trace.source_node}")
deps = inspector.parameter_dependencies("create_user")  # All dependencies

# Node Analysis (5 methods)
order = inspector.execution_order()  # Topological sort
deps = inspector.node_dependencies("create_user")  # Upstream nodes
schema = inspector.node_schema("create_user")  # Input/output schema

# Workflow Validation (3 methods)
report = inspector.workflow_validation_report()
if not report['is_valid']:
    print(f"Errors: {report['errors']}")
    print(f"Warnings: {report['warnings']}")
    print(f"Suggestions: {report['suggestions']}")
```

**Inspector Commands for Common Issues**:
- **"Missing parameter" error**: `inspector.trace_parameter(node_id, param)` → Find source
- **Connection not working**: `inspector.find_broken_connections()` → Identify issues
- **Node not executing**: `inspector.node_dependencies(node_id)` → Check upstream
- **Wrong execution order**: `inspector.execution_order()` → See actual sequence
- **Workflow validation**: `inspector.workflow_validation_report()` → Full diagnosis

**Performance**: <1ms per method call (cached operations)

---

### Build-Time Validation: Catch Errors Early

Build-time validation catches 80% of common configuration errors at model registration time (not runtime).

**Validation Modes**:
- **OFF**: No validation (use `skip_validation=True`)
- **WARN**: Default mode - warns but allows (backward compatible)
- **STRICT**: Raises errors on validation failures (recommended for new projects)

**Usage**:
```python
from dataflow import DataFlow

db = DataFlow()

# Default: WARN mode (backward compatible)
@db.model
class User:
    id: str  # ✅ Validates: primary key named 'id'
    name: str
    # Auto-validates but only warns on issues

# Strict mode: Raises errors immediately
@db.model(strict=True)
class Product:
    id: str  # ✅ Required primary key
    name: str
    price: float
    # Raises ModelValidationError on any validation failure

# Skip validation: For edge cases
@db.model(skip_validation=True)
class LegacyModel:
    pk: str  # ❌ Wrong primary key name, but validation skipped
    data: str
```

**Validation Checks**:
- **VAL-002**: Missing primary key (error) → Add `id` field to model
- **VAL-003**: Primary key not named 'id' (warning) → Rename to `id`
- **VAL-004**: Auto-managed field conflict (error) → Remove `created_at`/`updated_at`
- **VAL-005**: Invalid field type (warning) → Use SQLAlchemy-compatible types
- **VAL-006**: Reserved field name (error) → Avoid `type`, `class`, `def`
- **VAL-007**: Invalid naming convention (warning) → Use snake_case
- **VAL-008**: Circular relationship (error) → Fix relationship definitions
- **VAL-009**: Missing relationship target (error) → Ensure target model exists
- **VAL-010**: Invalid relationship configuration (warning) → Check relationship parameters

**Error Messages with Context**:
```python
# Example: Missing primary key
@db.model(strict=True)
class Order:
    customer_id: str  # ❌ Missing 'id' field
    total: float

# Raises:
# ModelValidationError: [VAL-002] Primary key 'id' is required
#   Model: Order
#   Issue: No primary key field found
#   Solution: Add 'id' field as primary key
#   Example:
#     @db.model
#     class Order:
#         id: str
#         customer_id: str
#         total: float
```

**When to Use Each Mode**:
- **OFF**: Legacy codebases, custom primary keys (advanced)
- **WARN**: Existing projects, gradual migration
- **STRICT**: New projects, strict validation requirements

**Time Saved**: 10-30 minutes per validation error (caught at registration vs runtime)

---

### CLI Tools: Industry-Standard Workflow Validation

Command-line validation and debugging tools matching pytest/mypy patterns for CI/CD integration.

**Available Commands**:
- **dataflow-validate**: Validate workflow structure, connections, and parameters
- **dataflow-analyze**: Workflow metrics, complexity analysis, and execution order
- **dataflow-generate**: Generate reports, diagrams (ASCII), and documentation
- **dataflow-debug**: Interactive debugging with breakpoints and node inspection
- **dataflow-perf**: Performance profiling, bottleneck detection, and recommendations

**Installation**:
```bash
pip install kailash-dataflow
# CLI tools installed automatically as dataflow-validate, dataflow-analyze, etc.
```

**Usage Examples**:

**1. Workflow Validation**:
```bash
# Validate workflow structure
dataflow-validate my_workflow.py

# Validate with detailed output
dataflow-validate my_workflow.py --output text

# Auto-fix common issues
dataflow-validate my_workflow.py --fix

# JSON output for CI/CD
dataflow-validate my_workflow.py --output json > validation.json
```

**2. Workflow Analysis**:
```bash
# Analyze workflow metrics
dataflow-analyze my_workflow.py

# Detailed analysis with verbosity
dataflow-analyze my_workflow.py --verbosity 2

# JSON output
dataflow-analyze my_workflow.py --format json
```

**3. Generate Reports**:
```bash
# Generate HTML report
dataflow-generate my_workflow.py report --output-dir ./reports

# Generate ASCII workflow diagram
dataflow-generate my_workflow.py diagram

# Generate markdown documentation
dataflow-generate my_workflow.py docs --output-dir ./docs
```

**4. Interactive Debugging**:
```bash
# Debug with breakpoint at node
dataflow-debug my_workflow.py --breakpoint create_user

# Inspect specific node
dataflow-debug my_workflow.py --inspect-node create_user

# Step-by-step execution
dataflow-debug my_workflow.py --step

# Interactive mode
dataflow-debug my_workflow.py --interactive
```

**5. Performance Profiling**:
```bash
# Profile workflow execution
dataflow-perf my_workflow.py

# Detect bottlenecks
dataflow-perf my_workflow.py --bottlenecks

# Get optimization recommendations
dataflow-perf my_workflow.py --recommend

# JSON output for analysis
dataflow-perf my_workflow.py --format json > perf.json
```

**CI/CD Integration**:
```yaml
# .github/workflows/validate.yml
name: Validate DataFlow Workflows
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Install dependencies
        run: pip install kailash-dataflow
      - name: Validate workflows
        run: |
          dataflow-validate workflows/*.py --output json > validation.json
      - name: Analyze workflows
        run: |
          dataflow-analyze workflows/*.py --format json > analysis.json
```

**Exit Codes**:
- **0**: Success (validation passed, no errors)
- **1**: Validation errors found
- **2**: Tool error (invalid arguments, file not found)

**Use Cases**:
- Pre-commit validation hooks
- CI/CD pipeline integration
- Pre-deployment validation
- Performance profiling and optimization
- Documentation generation
- Interactive debugging sessions

**Time Saved**: 5-15 minutes per validation check (automated vs manual inspection)

---

### CreateNode vs UpdateNode Guide
**Time Saved**: 1-2 hours per mistake (most common error)

**Quick Reference**:
- **CreateNode**: Flat fields → `{"id": "123", "name": "Alice"}`
- **UpdateNode**: Nested structure → `{"filter": {"id": "123"}, "fields": {"name": "Alice"}}`

**See**: `sdk-users/apps/dataflow/guides/create-vs-update.md` for complete side-by-side comparison with 10+ examples

---

### Top 10 Errors Quick Fix Guide
**Coverage**: 90% of user issues
**Time Saved**: 30-120 minutes per error

**See**: `sdk-users/apps/dataflow/troubleshooting/top-10-errors.md`

**Quick Diagnosis**:
1. "Missing parameter" → DF-101 → Add connection or parameter
2. "Type mismatch" → DF-102 → Check parameter types
3. "Auto-managed field" → DF-103 → Remove created_at/updated_at
4. "Missing 'filter'" → DF-104 → Use UpdateNode pattern
5. "Primary key error" → DF-105 → Use 'id' not 'user_id'
6. "Connection error" → DF-201 → Check output names
7. "Migration failed" → DF-301 → Check schema conflicts

---

## 🔧 STRING ID & CONTEXT-AWARE PATTERNS (NEW)

### String ID Support (No More Forced Integer Conversion)
```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

db = DataFlow()

# Model with string primary key - fully supported
@db.model
class SsoSession:
    id: str  # String IDs now preserved throughout workflow
    user_id: str
    state: str = 'active'

# String IDs work seamlessly in all operations
workflow = WorkflowBuilder()

# ✅ CORRECT: String ID preserved (no integer conversion)
session_id = "session-80706348-0456-468b-8851-329a756a3a93"
workflow.add_node("SsoSessionReadNode", "read_session", {
    "id": session_id  # String preserved as-is
})

# ✅ ALTERNATIVE: Use filter for explicit type preservation (v0.6.0+ API)
workflow.add_node("SsoSessionReadNode", "read_session_alt", {
    "filter": {"id": session_id},  # v0.6.0+ API - explicit type preservation
    "raise_on_not_found": True
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Multi-Instance DataFlow with Context Isolation
```python
# Instance 1: Development database with auto-migration
db_dev = DataFlow(
    database_url="sqlite:///dev.db",
    auto_migrate=True,           # Allow schema changes
    existing_schema_mode=False   # Full development mode
)

# Instance 2: Production database with safety locks
db_prod = DataFlow(
    database_url="postgresql://user:pass@localhost/prod",
    auto_migrate=False,          # No automatic migrations
    existing_schema_mode=True    # Maximum safety - no schema changes
)

# Context isolation - models registered on one instance don't affect the other
@db_dev.model
class DevModel:
    id: str
    name: str
    # This model only exists in dev instance

@db_prod.model
class ProdModel:
    id: str
    name: str
    # This model only exists in prod instance

# Each instance maintains its own context and schema operations
print(f"Dev models: {list(db_dev.models.keys())}")    # ['DevModel']
print(f"Prod models: {list(db_prod.models.keys())}")  # ['ProdModel']
```

### Deferred Schema Operations (Synchronous Registration, Async Table Creation)
```python
# Schema operations are deferred until workflow execution
db = DataFlow(auto_migrate=True)

# Model registration is synchronous and immediate
@db.model
class User:
    id: str
    name: str
    # Model registered immediately in memory

# Table creation is deferred until needed
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {
    "id": "user-001",
    "name": "John Doe"
})

# Actual table creation happens during execution (if needed)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
# Tables created on-demand during workflow execution
```

## 🚀 PRODUCTION DEPLOYMENT (v0.8.0 - NEW)

Production-ready features for Docker, Kubernetes, and enterprise deployments.

### AsyncLocalRuntime: Production-Ready Async Execution

AsyncLocalRuntime provides production features for FastAPI/Docker deployments.

**Key Features**:
- Execution timeouts (prevent hanging)
- Automatic cleanup (connection/task management)
- Context manager support
- Metrics tracking

**Basic Usage**:
```python
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Create runtime with timeout
runtime = AsyncLocalRuntime(execution_timeout=60)  # 60 second timeout

# Execute workflow
workflow = WorkflowBuilder()
workflow.add_node("User_Create", "create", {"name": "Alice"})

results, run_id = await runtime.execute_workflow_async(workflow.build(), inputs={})
```

**Configuration**:
```python
# Via constructor
runtime = AsyncLocalRuntime(
    execution_timeout=30,  # Timeout in seconds (default: 300)
    debug=True,
    enable_cycles=True
)

# Via environment variable
# export DATAFLOW_EXECUTION_TIMEOUT=120
runtime = AsyncLocalRuntime()  # Uses 120s from environment
```

**FastAPI Integration**:
```python
from fastapi import FastAPI, HTTPException
from kailash.runtime import AsyncLocalRuntime
import asyncio

app = FastAPI()
runtime = AsyncLocalRuntime(execution_timeout=30)

@app.post("/execute")
async def execute_workflow(data: dict):
    try:
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(),
            inputs=data
        )
        return {"status": "success", "results": results, "run_id": run_id}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail="Workflow exceeded 30s timeout")
    finally:
        # Automatic cleanup handled by runtime
        pass
```

**Context Manager Support**:
```python
from kailash.runtime.async_local import ExecutionContext

# Automatic resource cleanup
async with ExecutionContext() as ctx:
    # Connections acquired automatically
    results = await execute_with_context(workflow, ctx)
    # Automatic cleanup on exit
```

---

### Connection Pooling: Scalable Database Access

Connection pooling enables 100-1000+ concurrent users by reusing database connections.

**Key Features**:
- Per-database connection pools (PostgreSQL, MySQL, SQLite)
- Configurable pool sizes (default: pool_size=10, max_overflow=20)
- Connection health checking (pre_ping)
- Pool metrics and monitoring

**Basic Usage**:
```python
from dataflow import DataFlow

# Enable connection pooling (enabled by default)
db = DataFlow(
    "postgresql://user:password@localhost/db",
    enable_connection_pooling=True,  # Default: True
    pool_size=10,          # Connection pool size (default: 10)
    max_overflow=20        # Max overflow connections (default: 20)
)
```

**Configuration Options**:
```python
# 1. Environment variables
# export DATAFLOW_POOL_SIZE=25
# export DATAFLOW_MAX_OVERFLOW=50
db = DataFlow("postgresql://...")  # Uses environment values

# 2. Per-database override
db = DataFlow(
    "sqlite:///default.db",
    pool_size=10,  # Default for all databases
    pools={
        "postgresql://prod-db/main": {
            "pool_size": 50,       # Override for production database
            "max_overflow": 100
        }
    }
)

# 3. Disable pooling (for testing)
db = DataFlow("postgresql://...", enable_connection_pooling=False)
```

**Pool Metrics**:
```python
# Get pool metrics for monitoring
metrics = db._pool_manager.get_pool_metrics(database_url)
print(f"Pool size: {metrics['size']}")
print(f"Checked out: {metrics['checked_out']}")
print(f"Utilization: {metrics['utilization_percent']}%")
print(f"Is exhausted: {metrics['is_exhausted']}")
```

**Scalability**:
- Without pooling: ~50 concurrent users (connection exhaustion)
- With pooling (default): 100-1000+ concurrent users
- Production recommended: pool_size=25-50, max_overflow=50-100

---

### Health Monitoring: Kubernetes-Ready Probes

Health monitoring provides /health, /ready, and /metrics endpoints for Kubernetes deployments.

**Key Features**:
- Kubernetes liveness and readiness probes
- Component health checks (database, cache, pool)
- Prometheus metrics integration
- Configurable endpoint paths

**FastAPI Integration**:
```python
from fastapi import FastAPI
from dataflow import DataFlow
from dataflow.platform import HealthMonitor, add_health_endpoints

app = FastAPI()
db = DataFlow("postgresql://...")

# Add health endpoints
monitor = HealthMonitor(db)
add_health_endpoints(app, monitor)

# Endpoints created:
# GET /health - Health check (200 if healthy/degraded, 503 if unhealthy)
# GET /ready - Readiness check (200 if ready, 503 if not ready)
# GET /metrics - Prometheus metrics
```

**Manual Health Checks**:
```python
from dataflow.platform import HealthMonitor

monitor = HealthMonitor(db)

# Check overall health
health = await monitor.health_check()
print(f"Status: {health.status.value}")  # healthy/degraded/unhealthy
print(f"Details: {health.details}")

# Check readiness (Kubernetes)
is_ready = await monitor.readiness_check()
if not is_ready:
    logger.warning("Not ready for traffic")
```

**Environment Configuration**:
```python
# Customize endpoint paths
# export DATAFLOW_HEALTH_ENDPOINT=/healthz
# export DATAFLOW_READINESS_ENDPOINT=/readyz
# export DATAFLOW_METRICS_ENDPOINT=/prometheus

monitor = HealthMonitor(db)
# Endpoints will use custom paths from environment
```

**Component Health Checks**:
- **Database**: Connection health and query execution
- **Schema Cache**: Hit rate monitoring (degraded if <50%)
- **Connection Pool**: Utilization monitoring (degraded if >80%)

---

### Retry & Circuit Breaking: Production Resilience

Automatic retry for transient failures and circuit breaking for failing dependencies.

**Key Features**:
- Exponential backoff with jitter (prevents thundering herd)
- Circuit breaker with three states (CLOSED/OPEN/HALF_OPEN)
- Configurable thresholds and timeouts
- Metrics tracking

**Retry Configuration**:
```python
from dataflow.platform import RetryConfig, RetryHandler

# Configure retry policy
config = RetryConfig(
    max_attempts=3,      # Retry up to 3 times
    base_delay=0.1,      # Start with 100ms delay
    max_delay=5.0,       # Cap at 5 seconds
    multiplier=2.0,      # Exponential backoff (2x each retry)
    jitter=0.5           # 50-100% jitter (prevents thundering herd)
)

handler = RetryHandler(config)

# Execute with retry
result = await handler.execute_with_retry(database_operation, arg1, arg2)
```

**Circuit Breaker Configuration**:
```python
from dataflow.platform import CircuitBreakerConfig, CircuitBreaker

# Configure circuit breaker
config = CircuitBreakerConfig(
    failure_threshold=5,    # Open circuit after 5 failures
    success_threshold=2,    # Close circuit after 2 successes (in HALF_OPEN)
    timeout=60.0           # Test recovery after 60 seconds
)

breaker = CircuitBreaker(config)

# Execute with circuit breaker
result = await breaker.execute(external_api_call, arg1, arg2)
```

**Combined Usage** (Recommended):
```python
# Combine retry + circuit breaker for maximum resilience
async def protected_database_call():
    return await circuit_breaker.execute(database_operation)

result = await retry_handler.execute_with_retry(protected_database_call)
```

**Metrics**:
```python
# Retry metrics
retry_metrics = handler.get_metrics()
print(f"Total attempts: {retry_metrics['total_attempts']}")
print(f"Successes: {retry_metrics['total_successes']}")

# Circuit breaker metrics
breaker_metrics = breaker.get_metrics()
print(f"State: {breaker_metrics['state']}")  # CLOSED/OPEN/HALF_OPEN
print(f"Failures: {breaker_metrics['failure_count']}")
print(f"Rejected: {breaker_metrics['rejected_requests']}")
```

---

### Docker Deployment

**Dockerfile Example**:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Environment variables
ENV DATAFLOW_EXECUTION_TIMEOUT=60
ENV DATAFLOW_POOL_SIZE=25
ENV DATAFLOW_MAX_OVERFLOW=50

# Expose port
EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

**docker-compose.yml Example**:
```yaml
version: '3.8'

services:
  dataflow-app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:password@db:5432/dataflow
      - DATAFLOW_EXECUTION_TIMEOUT=60
      - DATAFLOW_POOL_SIZE=25
      - DATAFLOW_MAX_OVERFLOW=50
    depends_on:
      - db
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  db:
    image: postgres:15
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=dataflow
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

---

### Kubernetes Deployment

**Deployment YAML**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dataflow-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: dataflow-app
  template:
    metadata:
      labels:
        app: dataflow-app
    spec:
      containers:
      - name: dataflow-app
        image: your-registry/dataflow-app:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: dataflow-secrets
              key: database-url
        - name: DATAFLOW_EXECUTION_TIMEOUT
          value: "60"
        - name: DATAFLOW_POOL_SIZE
          value: "25"
        - name: DATAFLOW_MAX_OVERFLOW
          value: "50"

        # Liveness probe (is app responsive?)
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3

        # Readiness probe (is app ready for traffic?)
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3

        # Startup probe (initial startup check)
        startupProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 0
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 30

        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"

---
apiVersion: v1
kind: Service
metadata:
  name: dataflow-service
spec:
  selector:
    app: dataflow-app
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: LoadBalancer
```

**Secrets Configuration**:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: dataflow-secrets
type: Opaque
stringData:
  database-url: "postgresql://user:password@postgres-service:5432/dataflow"
```

---

### Production Best Practices

**1. Always Set Execution Timeouts**:
```python
# Prevent workflows from hanging indefinitely
runtime = AsyncLocalRuntime(execution_timeout=60)
```

**2. Enable Connection Pooling**:
```python
# Scale to 1000+ concurrent users
db = DataFlow("postgresql://...", pool_size=25, max_overflow=50)
```

**3. Add Health Monitoring**:
```python
# Enable Kubernetes orchestration
monitor = HealthMonitor(db)
add_health_endpoints(app, monitor)
```

**4. Use Retry + Circuit Breaking**:
```python
# Automatic resilience for transient failures
async def protected_call():
    return await circuit_breaker.execute(database_operation)

result = await retry_handler.execute_with_retry(protected_call)
```

**5. Monitor Metrics**:
```python
# Track pool utilization, circuit breaker state, retry attempts
pool_metrics = db._pool_manager.get_pool_metrics(url)
breaker_metrics = breaker.get_metrics()
retry_metrics = handler.get_metrics()
```

**6. Set Resource Limits**:
```yaml
# Kubernetes resource limits prevent resource exhaustion
resources:
  requests:
    memory: "256Mi"
    cpu: "250m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

**7. Use Environment Variables**:
```bash
# Configurable per environment
export DATAFLOW_EXECUTION_TIMEOUT=60
export DATAFLOW_POOL_SIZE=25
export DATAFLOW_MAX_OVERFLOW=50
export DATAFLOW_HEALTH_ENDPOINT=/healthz
```

---

## 📚 EXAMPLE GALLERY (v0.8.0 - NEW)

Complete, production-ready examples demonstrating DataFlow in real-world integrations.

### Payment Processing - Stripe Subscription

Complete Stripe integration with customer creation and webhook handling.

```python
from dataflow import DataFlow
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Create DataFlow instance
db = DataFlow(":memory:")

@db.model
class StripeCustomer:
    email: str
    name: str
    stripe_customer_id: str

# Create customer workflow
workflow = WorkflowBuilder()
workflow.add_node("ReadNode", "check_existing", {
    "model": "StripeCustomer",
    "filter": {"email": "alice@example.com"}
})

workflow.add_node("SwitchNode", "customer_exists", {
    "condition": "{{check_existing.result}} != None"
})

workflow.add_node("PythonCodeNode", "create_stripe_customer", {
    "code": """
import stripe
stripe.api_key = os.environ['STRIPE_API_KEY']
customer = stripe.Customer.create(
    email=input_data['email'],
    name=input_data['name']
)
output_data = {'stripe_customer_id': customer.id}
"""
})

workflow.add_node("StripeCustomerCreateNode", "store_customer", {
    "email": "alice@example.com",
    "name": "Alice Smith",
    "stripe_customer_id": "{{create_stripe_customer.stripe_customer_id}}"
})

# Connect nodes
workflow.add_connection("customer_exists", "false_output", "create_stripe_customer", "input_data")
workflow.add_connection("create_stripe_customer", "stripe_customer_id", "store_customer", "stripe_customer_id")

# Execute
runtime = AsyncLocalRuntime(execution_timeout=30)
results, run_id = await runtime.execute_workflow_async(workflow.build(), inputs={
    "email": "alice@example.com",
    "name": "Alice Smith"
})
```

**Environment Variables**:
- `STRIPE_API_KEY`: Your Stripe API key

**Usage**: `examples/payment/stripe_subscription.py`

---

### Email Integration - SendGrid

Transactional and bulk email workflows with SendGrid API.

```python
from dataflow import DataFlow
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

db = DataFlow(":memory:")

@db.model
class EmailLog:
    recipient: str
    subject: str
    status: str
    sent_at: str

# Send transactional email workflow
workflow = WorkflowBuilder()

workflow.add_node("PythonCodeNode", "render_template", {
    "code": """
template = "Hello {{name}}, welcome to our platform!"
output_data = {
    'body': template.replace('{{name}}', input_data['name']),
    'subject': 'Welcome to DataFlow'
}
"""
})

workflow.add_node("APINode", "send_email", {
    "url": "https://api.sendgrid.com/v3/mail/send",
    "method": "POST",
    "headers": {
        "Authorization": "Bearer {{env.SENDGRID_API_KEY}}",
        "Content-Type": "application/json"
    },
    "body": {
        "personalizations": [{
            "to": [{"email": "{{render_template.recipient}}"}],
            "subject": "{{render_template.subject}}"
        }],
        "from": {"email": "noreply@example.com"},
        "content": [{
            "type": "text/plain",
            "value": "{{render_template.body}}"
        }]
    }
})

workflow.add_node("EmailLogCreateNode", "log_email", {
    "recipient": "alice@example.com",
    "subject": "{{render_template.subject}}",
    "status": "sent",
    "sent_at": "{{now}}"
})

# Execute
runtime = AsyncLocalRuntime(execution_timeout=30)
results, run_id = await runtime.execute_workflow_async(workflow.build(), inputs={
    "recipient": "alice@example.com",
    "name": "Alice"
})
```

**Environment Variables**:
- `SENDGRID_API_KEY`: Your SendGrid API key

**Usage**: `examples/email/sendgrid_transactional.py`

---

### AI/LLM Integration - OpenAI

Chat completion and streaming workflows with OpenAI API.

```python
from dataflow import DataFlow
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

db = DataFlow(":memory:")

@db.model
class ChatCompletion:
    prompt: str
    response: str
    model: str
    tokens_used: int

# Chat completion workflow
workflow = WorkflowBuilder()

workflow.add_node("PythonCodeNode", "prepare_prompt", {
    "code": """
output_data = {
    'messages': [
        {'role': 'system', 'content': 'You are a helpful assistant.'},
        {'role': 'user', 'content': input_data['prompt']}
    ],
    'model': 'gpt-4'
}
"""
})

workflow.add_node("PythonCodeNode", "call_openai", {
    "code": """
import openai
openai.api_key = os.environ['OPENAI_API_KEY']

response = openai.ChatCompletion.create(
    model=input_data['model'],
    messages=input_data['messages']
)

output_data = {
    'response': response.choices[0].message.content,
    'tokens_used': response.usage.total_tokens
}
"""
})

workflow.add_node("ChatCompletionCreateNode", "store_completion", {
    "prompt": "{{prepare_prompt.input_data.prompt}}",
    "response": "{{call_openai.response}}",
    "model": "gpt-4",
    "tokens_used": "{{call_openai.tokens_used}}"
})

# Connect nodes
workflow.add_connection("prepare_prompt", "messages", "call_openai", "messages")
workflow.add_connection("call_openai", "response", "store_completion", "response")

# Execute with timeout
runtime = AsyncLocalRuntime(execution_timeout=60)  # LLM calls can be slow
results, run_id = await runtime.execute_workflow_async(workflow.build(), inputs={
    "prompt": "Explain DataFlow in 3 sentences"
})
```

**Environment Variables**:
- `OPENAI_API_KEY`: Your OpenAI API key

**Usage**: `examples/ai/openai_chat.py`

---

### File Storage - AWS S3

Single and batch file upload workflows with S3.

```python
from dataflow import DataFlow
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

db = DataFlow(":memory:")

@db.model
class FileMetadata:
    filename: str
    s3_key: str
    bucket: str
    size_bytes: int
    uploaded_at: str

# Single file upload workflow
workflow = WorkflowBuilder()

workflow.add_node("PythonCodeNode", "validate_file", {
    "code": """
import os
file_path = input_data['file_path']
if not os.path.exists(file_path):
    raise FileNotFoundError(f"File not found: {file_path}")

output_data = {
    'filename': os.path.basename(file_path),
    'size': os.path.getsize(file_path),
    'valid': True
}
"""
})

workflow.add_node("PythonCodeNode", "upload_to_s3", {
    "code": """
import boto3
s3 = boto3.client('s3')

bucket = os.environ['S3_BUCKET']
s3_key = f"uploads/{input_data['filename']}"

s3.upload_file(input_data['file_path'], bucket, s3_key)

output_data = {
    's3_key': s3_key,
    'bucket': bucket,
    'url': f"https://{bucket}.s3.amazonaws.com/{s3_key}"
}
"""
})

workflow.add_node("FileMetadataCreateNode", "store_metadata", {
    "filename": "{{validate_file.filename}}",
    "s3_key": "{{upload_to_s3.s3_key}}",
    "bucket": "{{upload_to_s3.bucket}}",
    "size_bytes": "{{validate_file.size}}",
    "uploaded_at": "{{now}}"
})

# Execute with connection pooling
runtime = AsyncLocalRuntime(
    execution_timeout=60,
    max_concurrent_nodes=10  # Parallel uploads
)
results, run_id = await runtime.execute_workflow_async(workflow.build(), inputs={
    "file_path": "document.pdf"
})
```

**Environment Variables**:
- `AWS_ACCESS_KEY_ID`: Your AWS access key
- `AWS_SECRET_ACCESS_KEY`: Your AWS secret key
- `S3_BUCKET`: Your S3 bucket name

**Usage**: `examples/storage/s3_upload.py`

---

### Authentication - JWT & OAuth2

JWT token generation/validation and OAuth2 code exchange workflows.

```python
from dataflow import DataFlow
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

db = DataFlow(":memory:")

@db.model
class User:
    email: str
    name: str
    hashed_password: str

@db.model
class AuthToken:
    user_id: str
    token_type: str  # 'access' or 'refresh'
    token: str
    expires_at: str

# JWT authentication workflow
workflow = WorkflowBuilder()

workflow.add_node("PythonCodeNode", "hash_password", {
    "code": """
import bcrypt
password = input_data['password'].encode('utf-8')
hashed = bcrypt.hashpw(password, bcrypt.gensalt())
output_data = {'hashed_password': hashed.decode('utf-8')}
"""
})

workflow.add_node("UserCreateNode", "create_user", {
    "email": "{{hash_password.input_data.email}}",
    "name": "{{hash_password.input_data.name}}",
    "hashed_password": "{{hash_password.hashed_password}}"
})

workflow.add_node("PythonCodeNode", "generate_jwt", {
    "code": """
import jwt
import datetime

user_id = input_data['user_id']
secret = os.environ['JWT_SECRET']

# Generate access token (1 hour)
access_payload = {
    'user_id': user_id,
    'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)
}
access_token = jwt.encode(access_payload, secret, algorithm='HS256')

# Generate refresh token (30 days)
refresh_payload = {
    'user_id': user_id,
    'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
}
refresh_token = jwt.encode(refresh_payload, secret, algorithm='HS256')

output_data = {
    'access_token': access_token,
    'refresh_token': refresh_token
}
"""
})

workflow.add_node("AuthTokenBulkCreateNode", "store_tokens", {
    "data": [
        {
            "user_id": "{{create_user.id}}",
            "token_type": "access",
            "token": "{{generate_jwt.access_token}}",
            "expires_at": "{{now + 1h}}"
        },
        {
            "user_id": "{{create_user.id}}",
            "token_type": "refresh",
            "token": "{{generate_jwt.refresh_token}}",
            "expires_at": "{{now + 30d}}"
        }
    ]
})

# Execute
runtime = AsyncLocalRuntime(execution_timeout=30)
results, run_id = await runtime.execute_workflow_async(workflow.build(), inputs={
    "email": "alice@example.com",
    "name": "Alice Smith",
    "password": "secure_password_123"
})
```

**Environment Variables**:
- `JWT_SECRET`: Secret key for JWT signing

**Usage**: `examples/auth/jwt_oauth2.py`

---

### Example Gallery Features

All examples demonstrate:
- **Phase 1 Features**: ErrorEnhancer, Inspector API, build-time validation
- **Phase 2 Features**: AsyncLocalRuntime, connection pooling, health monitoring, retry logic
- **DataFlow Best Practices**: @db.model patterns, workflow connections, error handling

**Location**: `examples/` directory with complete, runnable code

---

## 🗄️ DATABASE SUPPORT (ALL DATABASES 100% FEATURE PARITY)

DataFlow supports **PostgreSQL, MySQL, and SQLite** with identical functionality. All databases provide:
- ✅ **9 nodes per model** - Full CRUD + bulk operations
- ✅ **Async operations** - All database operations are async-first
- ✅ **Connection pooling** - Efficient connection management
- ✅ **Transaction support** - Full ACID compliance
- ✅ **Enterprise features** - Multi-tenancy, soft deletes, audit logging

### PostgreSQL (asyncpg driver)
```python
# Production-grade database with advanced features
db = DataFlow("postgresql://user:password@localhost:5432/mydb")

# With SSL/TLS
db = DataFlow("postgresql://user:password@localhost:5432/mydb?sslmode=require")

# With connection pool configuration
db = DataFlow(
    "postgresql://user:password@localhost:5432/mydb",
    pool_size=20,
    max_overflow=30,
    pool_recycle=3600
)
```

**Best for:** Enterprise production, PostGIS spatial data, complex analytics, JSONB operations

### MySQL (aiomysql driver)
```python
# Web hosting and MySQL ecosystem
db = DataFlow("mysql://user:password@localhost:3306/mydb")

# With charset and collation
db = DataFlow("mysql://user:password@localhost:3306/mydb?charset=utf8mb4&collation=utf8mb4_unicode_ci")

# With SSL/TLS and connection pool
db = DataFlow(
    "mysql://user:password@localhost:3306/mydb",
    ssl_ca="/path/to/ca.pem",
    ssl_cert="/path/to/cert.pem",
    ssl_key="/path/to/key.pem",
    pool_size=15,
    max_overflow=25,
    charset="utf8mb4"
)
```

**Best for:** Web hosting environments, existing MySQL infrastructure, read-heavy workloads

### SQLite (aiosqlite + custom pooling)
```python
# Fast local development and testing
db = DataFlow(":memory:")  # In-memory database

# File-based database
db = DataFlow("sqlite:///path/to/database.db")

# With WAL mode for better concurrency
db = DataFlow(
    "sqlite:///path/to/database.db",
    enable_wal=True,
    cache_size_mb=64,
    pool_size=5
)
```

**Best for:** Development/testing, mobile apps, edge computing, serverless functions

### Database Feature Comparison

| Feature | PostgreSQL | MySQL | SQLite |
|---------|------------|-------|--------|
| **Driver** | asyncpg | aiomysql | aiosqlite + custom pooling |
| **ACID Transactions** | ✅ | ✅ InnoDB | ✅ |
| **Connection Pooling** | ✅ Native | ✅ Native | ✅ Custom |
| **DataFlow Nodes** | ✅ All 9 | ✅ All 9 | ✅ All 9 |
| **JSON Support** | ✅ JSONB | ✅ 5.7+ | ✅ JSON1 |
| **Full-Text Search** | ✅ | ✅ | ✅ FTS5 |
| **Window Functions** | ✅ | ✅ 8.0+ | ✅ 3.25+ |
| **Spatial Data** | ✅ PostGIS | ✅ Native | ✅ R-Tree |
| **Best For** | Production | Web apps | Development, Mobile |

### Multi-Database Workflows
```python
# Development: Fast SQLite
dev_db = DataFlow(":memory:")

# Staging: MySQL for web hosting
staging_db = DataFlow("mysql://user:pass@staging:3306/staging_db")

# Production: PostgreSQL for enterprise
prod_db = DataFlow("postgresql://user:pass@prod:5432/prod_db")

# Same models work across ALL databases
@dev_db.model
@staging_db.model
@prod_db.model
class User:
    name: str
    email: str
    active: bool = True

# Identical 9 nodes generated for each database:
# UserCreateNode, UserReadNode, UserUpdateNode, UserDeleteNode,
# UserListNode, UserBulkCreateNode, UserBulkUpdateNode,
# UserBulkDeleteNode, UserBulkUpsertNode
```

## 🚀 IMMEDIATE SUCCESS PATTERNS

### Zero-Config Basic Pattern (30 seconds)
```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# 1. Zero-config initialization
db = DataFlow()  # Development: SQLite automatic, Production: PostgreSQL or MySQL
# NOTE: All three databases (PostgreSQL, MySQL, SQLite) have 100% feature parity (v0.5.6+)
# RECENT FIXES: DateTime handling, parameter types, content limits, connection order

# 2. Define model - generates 9 nodes automatically
@db.model
class User:
    name: str
    email: str
    active: bool = True

# 3. Use generated nodes immediately
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice", "email": "alice@example.com"
})
workflow.add_node("UserListNode", "list", {
    "filter": {"active": True}
})
workflow.add_connection("create", "result", "list", "input")

# 4. Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Production Pattern (Database Connection)
```python
# Environment-based (recommended) - works with any database
# DATABASE_URL=postgresql://user:pass@localhost/db
# DATABASE_URL=mysql://user:pass@localhost/db
# DATABASE_URL=sqlite:///path/to/db.db
db = DataFlow()

# PostgreSQL production
db = DataFlow(
    database_url="postgresql://user:pass@localhost:5432/db",
    pool_size=20,
    pool_max_overflow=30,
    pool_recycle=3600,
    monitoring=True,
    echo=False
)

# MySQL production
db = DataFlow(
    database_url="mysql://user:pass@localhost:3306/db",
    pool_size=15,
    max_overflow=25,
    pool_recycle=3600,
    charset="utf8mb4",
    echo=False
)

# SQLite production (edge/mobile)
db = DataFlow(
    database_url="sqlite:///app/data/production.db",
    enable_wal=True,
    cache_size_mb=128,
    pool_size=10
)
```

### Configuration Patterns (Complete Access)
```python
# Database configuration
db_config = {
    "database_url": "postgresql://user:pass@localhost/db",
    "pool_size": 20,
    "pool_max_overflow": 30,
    "pool_recycle": 3600,
    "pool_pre_ping": True,
    "echo": False,
    "monitoring": True,
    "slow_query_threshold": 100,  # ms
    "query_cache_enabled": True,
    "cache_ttl": 300  # seconds
}

# Multi-tenant configuration
tenant_config = {
    "multi_tenant": True,
    "tenant_isolation": "strict",
    "tenant_id_header": "X-Tenant-ID",
    "tenant_database_prefix": "tenant_"
}

# Security configuration
security_config = {
    "encryption_enabled": True,
    "encryption_key": "from_env",
    "audit_logging": True,
    "gdpr_compliance": True,
    "data_retention_days": 90
}

# Performance configuration
performance_config = {
    "bulk_batch_size": 1000,
    "async_operations": True,
    "connection_pool_size": 50,
    "read_replica_enabled": True,
    "cache_backend": "redis"
}

# Complete initialization
db = DataFlow(**db_config, **tenant_config, **security_config, **performance_config)
```

### Enterprise Pattern (Multi-Tenant + Audit)
```python
@db.model
class Order:
    customer_id: int
    total: float
    status: str = 'pending'

    # Enterprise features
    __dataflow__ = {
        'multi_tenant': True,     # Adds tenant_id field
        'soft_delete': True,      # Adds deleted_at field
        'versioned': True,        # Adds version field for optimistic locking
        'audit_log': True         # Tracks all changes
    }

    # Performance optimization
    __indexes__ = [
        {'name': 'idx_tenant_status', 'fields': ['tenant_id', 'status']},
        {'name': 'idx_customer_date', 'fields': ['customer_id', 'created_at']}
    ]
```

---

## 🎯 COMPLETE FUNCTION ACCESS MATRIX

### Generated Nodes (Per Model)
Every `@db.model` class automatically generates these 9 nodes:

| Node Type | Function | Use Case | Performance |
|-----------|----------|----------|-------------|
| **{Model}CreateNode** | Single insert | User registration | <1ms |
| **{Model}ReadNode** | Single select by ID | Profile lookup | <1ms |
| **{Model}UpdateNode** | Single update | Profile edit | <1ms |
| **{Model}DeleteNode** | Single delete | Account removal | <1ms |
| **{Model}ListNode** | Query with filters | Search/pagination | <10ms |
| **{Model}BulkCreateNode** | Bulk insert | Data import | 1000/sec |
| **{Model}BulkUpdateNode** | Bulk update | Price updates | 5000/sec |
| **{Model}BulkDeleteNode** | Bulk delete | Cleanup | 10000/sec |
| **{Model}BulkUpsertNode** | Insert or update | Sync operations | 3000/sec |

### Enterprise Features Access
```python
# Multi-tenant operations
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "email": "alice@example.com",
    "tenant_id": "tenant_123"  # Automatic isolation
})

# Soft delete operations
workflow.add_node("UserDeleteNode", "soft_delete", {
    "id": 123,
    "soft_delete": True  # Sets deleted_at, preserves data
})

# Versioned updates (optimistic locking)
workflow.add_node("UserUpdateNode", "update", {
    "id": 123,
    "name": "Alice Updated",
    "version": 1  # Prevents concurrent modification conflicts
})

# Audit trail queries
workflow.add_node("UserAuditNode", "audit", {
    "record_id": 123,
    "action_type": "update",
    "date_range": {"start": "2025-01-01", "end": "2025-01-31"}
})
```

### Bulk Operations (High Performance)
```python
# Bulk create with conflict resolution
workflow.add_node("ProductBulkCreateNode", "import", {
    "data": [
        {"name": "Product A", "price": 100.0},
        {"name": "Product B", "price": 200.0}
    ],
    "batch_size": 1000,  # Optimal batch size
    "conflict_resolution": "upsert",  # skip, error, upsert
    "return_ids": True  # Get created IDs
})

# Bulk update with conditions
workflow.add_node("ProductBulkUpdateNode", "price_update", {
    "filter": {"category": "electronics"},
    "update": {"price": {"$multiply": 0.9}},  # 10% discount
    "limit": 5000  # Process in batches
})

# Bulk delete with safety
workflow.add_node("ProductBulkDeleteNode", "cleanup", {
    "filter": {"deleted_at": {"$not": None}},
    "soft_delete": True,  # Preserves data
    "confirmation_required": True  # Prevents accidents
})
```

### Advanced Query Patterns
```python
# Complex filtering with MongoDB-style operators
workflow.add_node("OrderListNode", "search", {
    "filter": {
        "status": {"$in": ["pending", "processing"]},
        "total": {"$gte": 100.0},
        "created_at": {"$gte": "2025-01-01"},
        "customer": {
            "email": {"$regex": ".*@enterprise.com"}
        }
    },
    "sort": [{"created_at": -1}],
    "limit": 100,
    "offset": 0
})

# Aggregation operations
workflow.add_node("OrderAggregateNode", "analytics", {
    "group_by": ["status", "customer_id"],
    "aggregate": {
        "total_amount": {"$sum": "total"},
        "order_count": {"$count": "*"},
        "avg_order": {"$avg": "total"}
    },
    "having": {"total_amount": {"$gt": 1000}}
})
```

### Transaction Management
```python
# Distributed transaction with compensation
workflow.add_node("TransactionManagerNode", "payment_flow", {
    "transaction_type": "saga",  # or "two_phase_commit"
    "steps": [
        {
            "node": "PaymentCreateNode",
            "compensation": "PaymentRollbackNode"
        },
        {
            "node": "OrderUpdateNode",
            "compensation": "OrderRevertNode"
        },
        {
            "node": "InventoryUpdateNode",
            "compensation": "InventoryRestoreNode"
        }
    ],
    "timeout": 30,  # seconds
    "retry_attempts": 3
})

# ACID transaction scope
workflow.add_node("TransactionScopeNode", "atomic_operation", {
    "isolation_level": "READ_COMMITTED",
    "timeout": 10,
    "rollback_on_error": True
})
```

### Performance Optimization
```python
# Connection pooling configuration
db = DataFlow(
    pool_size=20,              # Base connections
    pool_max_overflow=30,      # Extra connections
    pool_recycle=3600,         # Recycle after 1 hour
    pool_pre_ping=True,        # Validate connections
    pool_reset_on_return="commit"  # Clean state
)

# Query caching
workflow.add_node("UserListNode", "cached_search", {
    "filter": {"active": True},
    "cache_key": "active_users",
    "cache_ttl": 300,  # 5 minutes
    "cache_invalidation": ["user_create", "user_update"]
})

# Read/write splitting
workflow.add_node("UserReadNode", "profile", {
    "id": 123,
    "read_preference": "secondary"  # Use read replica
})
```

### Change Data Capture (CDC)
```python
# Monitor database changes
workflow.add_node("CDCListenerNode", "order_changes", {
    "table": "orders",
    "operations": ["INSERT", "UPDATE", "DELETE"],
    "filter": {"status": "completed"},
    "webhook_url": "https://api.example.com/webhooks/orders"
})

# Event-driven workflows
workflow.add_node("EventTriggerNode", "order_processor", {
    "event_type": "order_created",
    "workflow_id": "order_fulfillment",
    "async_execution": True
})
```

### Multi-Database Support
```python
# Primary database - PostgreSQL for production
db_primary = DataFlow("postgresql://primary/db")

# MySQL for web hosting
db_mysql = DataFlow("mysql://web-host/db")

# SQLite for edge computing
db_sqlite = DataFlow("sqlite:///local/data.db")

# Use different databases in same workflow
workflow.add_node("OrderCreateNode", "create", {
    "database": "primary"  # Uses PostgreSQL
})
workflow.add_node("OrderAnalyticsNode", "analytics", {
    "database": "mysql"  # Uses MySQL
})
workflow.add_node("OrderCacheNode", "cache", {
    "database": "sqlite"  # Uses SQLite
})

# All three databases support identical operations
# Same 9 nodes available across all databases
```

### Security & Compliance
```python
# Encryption at rest
@db.model
class SensitiveData:
    user_id: int
    encrypted_data: str

    __dataflow__ = {
        'encryption': {
            'fields': ['encrypted_data'],
            'key_rotation': True,
            'algorithm': 'AES-256-GCM'
        }
    }

# GDPR compliance
workflow.add_node("GDPRExportNode", "data_export", {
    "user_id": 123,
    "include_deleted": True,
    "format": "json",
    "anonymize_fields": ["ip_address", "device_id"]
})

workflow.add_node("GDPRDeleteNode", "right_to_be_forgotten", {
    "user_id": 123,
    "cascade_delete": True,
    "retention_period": 0
})
```

### Monitoring & Observability
```python
# Performance monitoring
workflow.add_node("MonitoringNode", "perf_tracker", {
    "metrics": ["query_time", "connection_count", "cache_hit_rate"],
    "thresholds": {
        "query_time": 100,  # ms
        "connection_count": 80  # % of pool
    },
    "alerts": {
        "slack_webhook": "https://hooks.slack.com/...",
        "email": "admin@example.com"
    }
})

# Slow query detection
workflow.add_node("SlowQueryDetectorNode", "query_analyzer", {
    "threshold": 1000,  # ms
    "log_level": "warning",
    "auto_optimize": True
})
```

---

## ⚠️ CRITICAL: Parameter Validation Patterns

### Dynamic Parameter Resolution
```python
# ❌ WRONG: Template string syntax causes validation errors
workflow.add_node("OrderCreateNode", "create_order", {
    "customer_id": "${create_customer.id}",  # FAILS: conflicts with PostgreSQL
    "total": 100.0
})

# ✅ CORRECT: Use workflow connections for dynamic values
workflow.add_node("OrderCreateNode", "create_order", {
    "total": 100.0  # customer_id provided via connection
})
workflow.add_connection("create_customer", "id", "create_order", "customer_id")

# ✅ CORRECT: DateTime parameters use native objects
workflow.add_node("OrderCreateNode", "create_order", {
    "due_date": datetime.now(),      # Native datetime
    # NOT: datetime.now().isoformat() # String fails validation
})
```

### Nexus Integration Parameters
```python
# ✅ CORRECT: Double braces for Nexus parameter templates ONLY
nexus_workflow.add_node("ProductCreateNode", "create", {
    "name": "{{product_name}}",    # Nexus replaces at runtime
    "price": "{{product_price}}"   # Only in Nexus context
})
```

## 🏗️ ARCHITECTURE INTEGRATION

### DataFlow + Nexus Integration
```python
from dataflow import DataFlow
from nexus import Nexus

# Initialize DataFlow
db = DataFlow()

@db.model
class Product:
    name: str
    price: float

# Create Nexus with DataFlow integration
nexus = Nexus(
    title="E-commerce Platform",
    enable_api=True,
    enable_cli=True,
    enable_mcp=True,
    dataflow_integration=db  # Auto-generates API endpoints
)

# All DataFlow nodes available through:
# - REST API: POST /api/workflows/ProductCreateNode/execute
# - CLI: nexus execute ProductCreateNode --name "Test" --price 100
# - MCP: Available to AI agents for data operations
```

### Gateway API Generation
```python
from kailash.servers.gateway import create_gateway

# Auto-generate REST API from DataFlow models
gateway = create_gateway(
    title="Product API",
    server_type="enterprise",
    dataflow_integration=db,
    auto_generate_endpoints=True,  # Creates CRUD endpoints
    authentication_required=True
)

# Automatically creates:
# GET /api/products - List products
# POST /api/products - Create product
# GET /api/products/{id} - Get product
# PUT /api/products/{id} - Update product
# DELETE /api/products/{id} - Delete product
```

### Complete Nexus Integration Pattern
```python
from nexus import Nexus
from dataflow import DataFlow

# Initialize DataFlow with models
db = DataFlow()

@db.model
class Order:
    customer_id: int
    total: float
    status: str = 'pending'
    __dataflow__ = {
        'multi_tenant': True,
        'audit_log': True
    }

# Create Nexus platform with full DataFlow integration
nexus = Nexus(
    title="E-commerce Platform",
    enable_api=True,
    enable_cli=True,
    enable_mcp=True,
    channels_synced=True,

    # DataFlow integration configuration
    dataflow_config={
        "integration": db,
        "auto_generate_endpoints": True,
        "auto_generate_cli_commands": True,
        "auto_generate_mcp_tools": True,
        "expose_bulk_operations": True,
        "expose_analytics": True
    },

    # Enterprise features
    auth_config={
        "providers": ["oauth2", "saml"],
        "rbac_enabled": True
    },

    # Monitoring
    monitoring_config={
        "prometheus_enabled": True,
        "track_database_metrics": True
    }
)

# All DataFlow operations now available through all Nexus channels:
# - API: Full CRUD + bulk operations + analytics
# - CLI: nexus orders create --customer-id 123 --total 250.00
# - MCP: AI agents can perform database operations
# - WebSocket: Real-time database change notifications
```

### Event-Driven Architecture
```python
# Database events trigger workflows
workflow.add_node("EventSourceNode", "order_events", {
    "source": "database",
    "table": "orders",
    "event_types": ["INSERT", "UPDATE"]
})

workflow.add_node("EventProcessorNode", "order_processor", {
    "event_filter": {"status": "completed"},
    "target_workflow": "order_fulfillment"
})
```

---

## 📊 PERFORMANCE BENCHMARKS

### Throughput Metrics
- **Single operations**: 1,000+ ops/sec
- **Bulk create**: 10,000+ records/sec
- **Bulk update**: 50,000+ records/sec
- **Query operations**: 5,000+ queries/sec
- **Transaction throughput**: 500+ txns/sec

### Memory Usage
- **Base overhead**: <10MB
- **Per model**: <1MB
- **Connection pool**: 2MB per connection
- **Cache overhead**: 50MB per 1M records

### Latency Targets
- **Single CRUD**: <1ms
- **Bulk operations**: <10ms per 1000 records
- **Complex queries**: <100ms
- **Transaction commit**: <5ms

---

## 🎯 DECISION MATRIX

| Use Case | Best Pattern | Performance | Complexity |
|----------|-------------|-------------|------------|
| **Single record CRUD** | Basic nodes | <1ms | Low |
| **Bulk data import** | BulkCreateNode | 10k/sec | Medium |
| **Complex queries** | ListNode + filters | <100ms | Medium |
| **Multi-tenant app** | Enterprise features | Variable | High |
| **Real-time updates** | CDC + Events | <10ms | High |
| **Analytics queries** | Read replicas | <1sec | Medium |
| **Distributed systems** | Saga transactions | <100ms | High |

---

## 🔧 ADVANCED MIGRATION PATTERNS

### Complete Migration Workflow (Enterprise)
```python
from dataflow.migrations.integrated_risk_assessment_system import IntegratedRiskAssessmentSystem

async def enterprise_migration_workflow(
    operation_type: str,
    table_name: str,
    migration_details: dict,
    connection_manager
):
    """Complete enterprise migration workflow with all safety systems."""

    # Step 1: Comprehensive Risk Assessment
    risk_system = IntegratedRiskAssessmentSystem(connection_manager)

    comprehensive_assessment = await risk_system.perform_complete_assessment(
        operation_type=operation_type,
        table_name=table_name,
        operation_details=migration_details,
        include_performance_analysis=True,
        include_dependency_analysis=True,
        include_fk_analysis=True
    )

    print(f"Risk Assessment Complete:")
    print(f"  Overall Risk: {comprehensive_assessment.overall_risk_level}")
    print(f"  Risk Score: {comprehensive_assessment.risk_score}/100")

    # Step 2: Generate Mitigation Strategies
    mitigation_plan = await risk_system.generate_comprehensive_mitigation_plan(
        assessment=comprehensive_assessment,
        business_requirements={
            "max_downtime_minutes": 5,
            "rollback_time_limit": 10,
            "data_consistency_critical": True
        }
    )

    print(f"Mitigation Strategies: {len(mitigation_plan.strategies)}")

    # Step 3: Create Staging Environment
    staging_manager = StagingEnvironmentManager(connection_manager)
    staging_env = await staging_manager.create_staging_environment(
        environment_name=f"migration_{int(time.time())}",
        data_sampling_strategy={"strategy": "representative", "sample_percentage": 5}
    )

    try:
        # Step 4: Test Migration in Staging
        staging_test = await staging_manager.test_migration_in_staging(
            staging_env,
            migration_plan={
                "operation": operation_type,
                "table": table_name,
                "details": migration_details
            },
            validation_checks=True
        )

        if not staging_test.success:
            print(f"Staging test failed: {staging_test.failure_reason}")
            return False

        # Step 5: Acquire Migration Lock for Production
        lock_manager = MigrationLockManager(connection_manager)

        async with lock_manager.acquire_migration_lock(
            lock_scope="table_modification",
            timeout_seconds=600,
            operation_description=f"{operation_type} on {table_name}"
        ) as migration_lock:

            # Step 6: Execute with Validation Checkpoints
            validation_manager = ValidationCheckpointManager(connection_manager)

            validation_result = await validation_manager.execute_with_validation(
                migration_operation=lambda: execute_actual_migration(
                    operation_type, table_name, migration_details
                ),
                checkpoints=[
                    {"stage": "pre", "validators": ["integrity", "fk_consistency"]},
                    {"stage": "post", "validators": ["data_integrity", "performance"]}
                ],
                rollback_on_failure=True
            )

            if validation_result.all_checkpoints_passed:
                print("✓ Enterprise migration completed successfully")
                return True
            else:
                print(f"✗ Migration failed: {validation_result.failure_details}")
                return False

    finally:
        # Step 7: Cleanup Staging Environment
        await staging_manager.cleanup_staging_environment(staging_env)

# Usage example
success = await enterprise_migration_workflow(
    operation_type="add_not_null_column",
    table_name="users",
    migration_details={
        "column_name": "account_status",
        "data_type": "VARCHAR(20)",
        "default_value": "active"
    },
    connection_manager=your_connection_manager
)
```

### Migration Decision Matrix

| Migration Type | Risk Level | Required Tools | Recommended Pattern |
|---------------|------------|----------------|---------------------|
| **Add Column (nullable)** | LOW | Basic validation | Direct execution |
| **Add NOT NULL Column** | MEDIUM | NotNullHandler + Validation | Plan → Validate → Execute |
| **Drop Column** | HIGH | DependencyAnalyzer + Risk Assessment | Full enterprise workflow |
| **Rename Table** | CRITICAL | TableRenameAnalyzer + FK Analysis | Staging → Lock → Validate |
| **Change Column Type** | HIGH | Risk Assessment + Mitigation | Staging test required |
| **Drop Table** | CRITICAL | Full risk assessment + Staging | Maximum safety protocol |

## 🔧 ADVANCED DEVELOPMENT

### Custom Node Development
```python
from dataflow.nodes import BaseDataFlowNode

class CustomAnalyticsNode(BaseDataFlowNode):
    def __init__(self, node_id, custom_query):
        self.custom_query = custom_query
        super().__init__(node_id)

    def execute(self, input_data):
        # Custom analytics logic
        return self.run_custom_query(self.custom_query)

# Register custom node
db.register_node(CustomAnalyticsNode)
```

### Advanced Migration System (v0.4.5+)

DataFlow includes a comprehensive enterprise-grade migration system with 8 specialized engines for safe schema evolution:

#### 1. Risk Assessment Engine
```python
from dataflow.migrations.risk_assessment_engine import RiskAssessmentEngine, RiskCategory

# Initialize risk assessment
risk_engine = RiskAssessmentEngine(connection_manager)

# Assess migration risks across multiple dimensions
risk_assessment = await risk_engine.assess_operation_risk(
    operation_type="drop_column",
    table_name="users",
    column_name="legacy_field",
    dependencies=dependency_report
)

print(f"Overall Risk Level: {risk_assessment.overall_risk_level}")  # CRITICAL/HIGH/MEDIUM/LOW
print(f"Risk Score: {risk_assessment.overall_score}/100")

# Detailed risk breakdown
for category, risk in risk_assessment.category_risks.items():
    print(f"{category.name}: {risk.risk_level.name} ({risk.score}/100)")
    for factor in risk.risk_factors:
        print(f"  - {factor.description}")
```

#### 2. Mitigation Strategy Engine
```python
from dataflow.migrations.mitigation_strategy_engine import MitigationStrategyEngine

# Generate comprehensive mitigation strategies
mitigation_engine = MitigationStrategyEngine(risk_engine)

# Get mitigation roadmap based on risk assessment
strategy_plan = await mitigation_engine.generate_mitigation_plan(
    risk_assessment=risk_assessment,
    operation_context={
        "table_size": 1000000,
        "production_environment": True,
        "maintenance_window": 30  # minutes
    }
)

print(f"Recommended mitigation strategies:")
for strategy in strategy_plan.recommended_strategies:
    print(f"  {strategy.category.name}: {strategy.description}")
    print(f"  Effectiveness: {strategy.effectiveness_score}/100")
    print(f"  Implementation cost: {strategy.implementation_cost}")
```

#### 3. Foreign Key Analyzer (FK-Aware Operations)
```python
from dataflow.migrations.foreign_key_analyzer import ForeignKeyAnalyzer, FKOperationType

# Comprehensive FK impact analysis
fk_analyzer = ForeignKeyAnalyzer(connection_manager)

# Analyze FK implications of table operations
fk_impact = await fk_analyzer.analyze_fk_impact(
    operation=FKOperationType.DROP_COLUMN,
    table_name="users",
    column_name="department_id",
    include_cascade_analysis=True
)

print(f"FK Impact Level: {fk_impact.impact_level}")
print(f"Affected FK constraints: {len(fk_impact.affected_constraints)}")
print(f"Cascade operations: {len(fk_impact.cascade_operations)}")

# FK-safe migration execution
if fk_impact.is_safe_to_proceed:
    fk_safe_plan = await fk_analyzer.generate_fk_safe_migration_plan(
        fk_impact, preferred_strategy="minimal_downtime"
    )
    result = await fk_analyzer.execute_fk_safe_migration(fk_safe_plan)
else:
    print("Operation blocked by FK dependencies - manual intervention required")
```

#### 4. Table Rename Analyzer
```python
from dataflow.migrations.table_rename_analyzer import TableRenameAnalyzer

# Safe table renaming with dependency tracking
rename_analyzer = TableRenameAnalyzer(connection_manager)

# Comprehensive dependency analysis for table rename
rename_impact = await rename_analyzer.analyze_rename_impact(
    current_name="user_accounts",
    new_name="users"
)

print(f"Dependencies found: {len(rename_impact.total_dependencies)}")
print(f"Views to update: {len(rename_impact.view_dependencies)}")
print(f"FK constraints to update: {len(rename_impact.fk_dependencies)}")
print(f"Stored procedures affected: {len(rename_impact.procedure_dependencies)}")

# Execute coordinated rename with dependency updates
if rename_impact.can_rename_safely:
    rename_plan = await rename_analyzer.create_rename_plan(
        rename_impact,
        include_dependency_updates=True,
        backup_strategy="full_backup"
    )
    result = await rename_analyzer.execute_coordinated_rename(rename_plan)
```

#### 5. Staging Environment Manager
```python
from dataflow.migrations.staging_environment_manager import StagingEnvironmentManager

# Create staging environment for safe migration testing
staging_manager = StagingEnvironmentManager(connection_manager)

# Replicate production schema with sample data
staging_env = await staging_manager.create_staging_environment(
    environment_name="migration_test_001",
    data_sampling_strategy={
        "strategy": "representative",
        "sample_percentage": 10,
        "preserve_referential_integrity": True
    },
    resource_limits={
        "max_storage_gb": 50,
        "max_duration_hours": 2
    }
)

print(f"Staging environment: {staging_env.environment_id}")
print(f"Database URL: {staging_env.connection_info.database_url}")

# Test migration in staging
test_result = await staging_manager.test_migration_in_staging(
    staging_env,
    migration_plan=your_migration_plan,
    validation_checks=True
)

print(f"Staging test result: {test_result.success}")
print(f"Performance impact: {test_result.performance_metrics}")

# Cleanup staging environment
await staging_manager.cleanup_staging_environment(staging_env)
```

#### 6. Migration Lock Manager
```python
from dataflow.migrations.concurrent_access_manager import MigrationLockManager

# Prevent concurrent migrations
lock_manager = MigrationLockManager(connection_manager)

# Acquire exclusive migration lock
async with lock_manager.acquire_migration_lock(
    lock_scope="schema_modification",
    timeout_seconds=300,
    operation_description="Add NOT NULL column to users table"
) as lock:

    print(f"Migration lock acquired: {lock.lock_id}")

    # Execute migration safely - no other migrations can run
    migration_result = await execute_your_migration()

    print(f"Migration completed under lock protection")
    # Lock is automatically released when context exits
```

#### 7. Validation Checkpoint Manager
```python
from dataflow.migrations.validation_checkpoints import ValidationCheckpointManager

# Multi-stage validation system
validation_manager = ValidationCheckpointManager(connection_manager)

# Define validation checkpoints
checkpoints = [
    {
        "stage": "pre_migration",
        "validators": ["schema_integrity", "foreign_key_consistency", "data_quality"]
    },
    {
        "stage": "during_migration",
        "validators": ["transaction_health", "performance_monitoring"]
    },
    {
        "stage": "post_migration",
        "validators": ["schema_validation", "data_integrity", "constraint_validation"]
    }
]

# Execute migration with checkpoint validation
validation_result = await validation_manager.execute_with_validation(
    migration_operation=your_migration_function,
    checkpoints=checkpoints,
    rollback_on_failure=True
)

if validation_result.all_checkpoints_passed:
    print("Migration completed - all validation checkpoints passed")
else:
    print(f"Migration failed at checkpoint: {validation_result.failed_checkpoint}")
    print(f"Rollback executed: {validation_result.rollback_completed}")
```

#### 8. Schema State Manager
```python
from dataflow.migrations.schema_state_manager import SchemaStateManager

# Track and manage schema evolution
schema_manager = SchemaStateManager(connection_manager)

# Create schema snapshot before major changes
snapshot = await schema_manager.create_schema_snapshot(
    description="Before user table restructuring",
    include_data_checksums=True
)

print(f"Schema snapshot created: {snapshot.snapshot_id}")
print(f"Tables captured: {len(snapshot.table_definitions)}")
print(f"Constraints tracked: {len(snapshot.constraint_definitions)}")

# Track schema changes during migration
change_tracker = await schema_manager.start_change_tracking(
    baseline_snapshot=snapshot
)

# Execute your migration
migration_result = await your_migration_function()

# Generate schema evolution report
evolution_report = await schema_manager.generate_evolution_report(
    from_snapshot=snapshot,
    to_current_state=True,
    include_impact_analysis=True
)

print(f"Schema changes detected: {len(evolution_report.schema_changes)}")
for change in evolution_report.schema_changes:
    print(f"  - {change.change_type}: {change.description}")
    print(f"    Impact level: {change.impact_level}")
```

### Advanced Query Optimization
```python
# Query optimization patterns
workflow.add_node("QueryOptimizerNode", "optimize", {
    "analyze_execution_plan": True,
    "suggest_indexes": True,
    "auto_create_indexes": True,
    "query_rewrite": True
})

# Database performance tuning
workflow.add_node("PerformanceTunerNode", "tune", {
    "analyze_table_statistics": True,
    "vacuum_analyze": True,
    "optimize_connections": True,
    "cache_warm_up": True
})
```

### Testing Patterns
```python
# Test database setup
test_db = DataFlow(":memory:")  # In-memory SQLite (100% feature parity with PostgreSQL and MySQL)

# Test data generation
workflow.add_node("TestDataGeneratorNode", "generate", {
    "model": "User",
    "count": 1000,
    "distribution": "normal"
})

# Performance testing
workflow.add_node("PerformanceTestNode", "benchmark", {
    "operation": "bulk_create",
    "record_count": 10000,
    "measure": ["latency", "throughput", "memory"]
})
```

### Production Database Management
```python
# Database backup and restore
workflow.add_node("DatabaseBackupNode", "backup", {
    "backup_type": "incremental",
    "compression": "gzip",
    "encryption": True,
    "destination": "s3://backups/dataflow/"
})

# Point-in-time recovery
workflow.add_node("DatabaseRestoreNode", "restore", {
    "restore_point": "2025-01-10T12:00:00Z",
    "verify_integrity": True,
    "test_restore": True
})

# Database monitoring
workflow.add_node("DatabaseMonitorNode", "monitor", {
    "metrics": ["connections", "queries_per_sec", "slow_queries"],
    "alert_thresholds": {
        "connections": 80,  # % of max
        "slow_queries": 10  # per minute
    }
})
```

---

## 🚨 CRITICAL SUCCESS FACTORS

### ✅ ALWAYS DO
- Use `@db.model` decorator for automatic node generation
- Leverage bulk operations for >100 records
- Enable multi-tenancy for SaaS applications
- Use soft deletes for audit trails
- Configure connection pooling for production
- Implement proper error handling and retries
- Use workflow connections for dynamic parameter passing
- Test with TEXT fields for unlimited content (fixed VARCHAR(255) limits)
- **STRING ID SUPPORT: Use string IDs directly in node parameters - no conversion needed**
- **MULTI-INSTANCE: Isolate DataFlow instances for different environments (dev/prod)**
- **DEFERRED SCHEMA: Let DataFlow handle table creation during workflow execution**
- **NEW: Use appropriate migration safety level for your environment**
- **NEW: Perform risk assessment for schema changes in production**
- **NEW: Test migrations in staging environment before production**
- **NEW: Use migration locks to prevent concurrent schema modifications**

### ❌ NEVER DO
- Direct database session management
- Manual transaction handling
- Raw SQL queries without query builder
- Skip connection pooling configuration
- Ignore soft delete for important data
- Use single operations for bulk data
- Use `${}` syntax in node parameters (conflicts with PostgreSQL)
- Use `.isoformat()` for datetime parameters (serialize before passing to workflows)
- Assume VARCHAR(255) limits still exist (now TEXT with unlimited content)
- **FORCE INTEGER CONVERSION on string IDs (now automatically preserved)**
- **MIX DataFlow instances** between environments (each should be isolated)
- **MANUALLY CREATE TABLES** before defining models (let deferred schema handle it)
- **NEW: Skip migration risk assessment in production environments**
- **NEW: Execute high-risk migrations without staging tests**
- **NEW: Ignore foreign key dependencies during schema changes**
- **NEW: Run concurrent migrations without lock coordination**

### 🔧 MAJOR BUG FIXES COMPLETED (v0.9.11 & v0.4.0 → v0.5.6)
- **✅ MySQL Support**: Full MySQL support with 100% feature parity (v0.5.6)
- **✅ DateTime Serialization**: Fixed datetime objects being converted to strings
- **✅ PostgreSQL Parameter Types**: Added explicit type casting for parameter determination
- **✅ Content Size Limits**: Changed VARCHAR(255) to TEXT for unlimited content
- **✅ Workflow Connections**: Fixed parameter order in workflow connections
- **✅ Parameter Naming**: Fixed conflicts with Core SDK internal fields
- **✅ Data Access Patterns**: Corrected list node result access
- **✅ SERIAL Column Generation**: Fixed duplicate DEFAULT clauses in PostgreSQL
- **✅ TIMESTAMP Defaults**: Fixed quoting of SQL functions in schema generation
- **✅ Schema Inspection**: Fixed bounds checking errors
- **✅ Test Fixtures**: Improved migration test configuration
- **✅ auto_migrate=False**: Fixed tables being created despite disabled auto-migration
- **✅ String ID Preservation**: No more forced integer conversion - IDs preserve original type**
- **✅ Multi-Instance Isolation**: Proper context separation between DataFlow instances**
- **✅ Deferred Schema Operations**: Table creation deferred until workflow execution**
- **✅ Context-Aware Table Creation**: Node-instance coupling for proper isolation**

### 🎯 OPTIMIZATION CHECKLIST
- [ ] Connection pool sized for workload
- [ ] Indexes defined for query patterns
- [ ] Bulk operations for high-volume data
- [ ] Caching enabled for frequent queries
- [ ] Monitoring configured for performance
- [ ] Backup strategy implemented
- [ ] Security measures in place

---

## 📚 COMPLETE NAVIGATION

### **🔗 Hierarchical Navigation Path**
1. **Start**: [Root CLAUDE.md](../../../CLAUDE-archive.md) → Essential patterns
2. **SDK Guidance**: [SDK Users](../../../sdk-users/) → Complete SDK navigation
3. **This Guide**: DataFlow-specific complete function access
4. **Integration**: [Nexus CLAUDE.md](../../kailash-nexus/CLAUDE.md) → Multi-channel platform

### **Quick Start**
- [Installation Guide](docs/getting-started/installation.md)
- [First App in 5 Minutes](docs/getting-started/quickstart.md)
- [Core Concepts](docs/getting-started/concepts.md)

### **Development**
- [Model Definition](docs/development/models.md)
- [Generated Nodes](docs/development/nodes.md)
- [Bulk Operations](docs/development/bulk-operations.md)
- [Relationships](docs/development/relationships.md)
- [Custom Development](docs/development/custom-nodes.md)

### **Enterprise**
- [Multi-Tenancy](docs/enterprise/multi-tenant.md)
- [Security](docs/enterprise/security.md)
- [Audit & Compliance](docs/enterprise/compliance.md)
- [Performance](docs/enterprise/performance.md)

### **Production**
- [Deployment Guide](docs/production/deployment.md)
- [Monitoring](docs/production/monitoring.md)
- [Backup & Recovery](docs/production/backup.md)
- [Troubleshooting](docs/production/troubleshooting.md)

### **Integration**
- [Nexus Integration](docs/integration/nexus.md)
- [Gateway APIs](docs/integration/gateway.md)
- [Event-Driven Architecture](docs/integration/events.md)

---

## 🔧 MIGRATION SYSTEM REFERENCE

### Migration Engine Components (v0.4.5+)

| Component | Purpose | Performance | Use Cases |
|-----------|---------|-------------|----------|
| **Risk Assessment Engine** | Multi-dimensional risk analysis | <100ms analysis | Pre-migration risk evaluation |
| **Mitigation Strategy Engine** | Automated risk reduction plans | <200ms generation | Risk mitigation planning |
| **Foreign Key Analyzer** | FK-aware operations & integrity | <30s for 1000+ FKs | FK dependency analysis |
| **Table Rename Analyzer** | Safe table renaming with deps | <5s analysis | Table restructuring |
| **Staging Environment Manager** | Safe migration testing | <5min setup | Production-like testing |
| **Migration Lock Manager** | Concurrent migration prevention | <10ms lock ops | Multi-instance safety |
| **Validation Checkpoint Manager** | Multi-stage validation | <1s validation | Migration quality assurance |
| **Schema State Manager** | Schema evolution tracking | <2s snapshot | Change history & rollback |

### Migration Safety Levels

#### Level 1: Basic (Development)
```python
db = DataFlow(auto_migrate=True)  # Default behavior
# ✅ Safe: auto_migrate preserves existing data on repeat runs
# ✅ Verified: No data loss on second+ executions
```

#### Level 2: Production-Safe
```python
db = DataFlow(
    auto_migrate=False,         # No automatic changes
    existing_schema_mode=True    # Use existing schema only
)
# ✅ Maximum safety for existing databases
# ✅ No accidental schema modifications
```

#### Level 3: Enterprise (Full Migration System)
```python
from dataflow.migrations.integrated_risk_assessment_system import IntegratedRiskAssessmentSystem

# Full enterprise migration workflow with all safety systems
async def enterprise_migration():
    risk_system = IntegratedRiskAssessmentSystem(connection_manager)

    # Complete risk assessment with mitigation
    assessment = await risk_system.perform_complete_assessment(
        operation_type="add_not_null_column",
        table_name="users",
        operation_details={"column": "status", "default": "active"}
    )

    # Only proceed if risk is acceptable
    if assessment.overall_risk_level in ["LOW", "MEDIUM"]:
        return await execute_with_full_safety_protocol(assessment)
    else:
        return await require_manual_approval(assessment)
```

### Migration Operation Reference

| Operation | Risk Level | Required Tools | Example Usage |
|-----------|------------|----------------|---------------|
| **Add Nullable Column** | LOW | Basic validation | `ALTER TABLE users ADD COLUMN phone TEXT` |
| **Add NOT NULL Column** | MEDIUM | NotNullHandler + constraints | Safe default value strategies |
| **Drop Column** | HIGH | DependencyAnalyzer + Risk Assessment | Full dependency impact analysis |
| **Rename Column** | MEDIUM | Dependency analysis | Update all references |
| **Change Column Type** | HIGH | Risk assessment + validation | Data conversion safety |
| **Rename Table** | CRITICAL | TableRenameAnalyzer + FK Analysis | Coordinate all dependencies |
| **Drop Table** | CRITICAL | Full enterprise workflow | Maximum safety protocol |
| **Add Foreign Key** | MEDIUM | FK analyzer + validation | Referential integrity checks |
| **Drop Foreign Key** | HIGH | FK impact analysis | Cascade safety analysis |

### Complete API Reference

#### Core Migration Classes
```python
# Risk Assessment
from dataflow.migrations.risk_assessment_engine import RiskAssessmentEngine, RiskLevel
from dataflow.migrations.mitigation_strategy_engine import MitigationStrategyEngine

# Specialized Analyzers
from dataflow.migrations.foreign_key_analyzer import ForeignKeyAnalyzer, FKOperationType
from dataflow.migrations.table_rename_analyzer import TableRenameAnalyzer
from dataflow.migrations.dependency_analyzer import DependencyAnalyzer, ImpactLevel

# Environment Management
from dataflow.migrations.staging_environment_manager import StagingEnvironmentManager
from dataflow.migrations.concurrent_access_manager import MigrationLockManager

# Validation & State Management
from dataflow.migrations.validation_checkpoints import ValidationCheckpointManager
from dataflow.migrations.schema_state_manager import SchemaStateManager

# Column Operations
from dataflow.migrations.not_null_handler import NotNullColumnHandler, ColumnDefinition
from dataflow.migrations.column_removal_manager import ColumnRemovalManager

# Integrated Systems
from dataflow.migrations.integrated_risk_assessment_system import IntegratedRiskAssessmentSystem
```

#### Migration Best Practices Checklist

##### Pre-Migration (Required)
- [ ] **Risk Assessment**: Analyze potential impact and risks
- [ ] **Dependency Analysis**: Identify all affected database objects
- [ ] **Backup Strategy**: Ensure recovery options are available
- [ ] **Staging Test**: Validate migration in production-like environment
- [ ] **Lock Acquisition**: Prevent concurrent migrations

##### During Migration (Required)
- [ ] **Validation Checkpoints**: Multi-stage validation throughout process
- [ ] **Performance Monitoring**: Track execution metrics
- [ ] **Rollback Readiness**: Prepared rollback procedures if needed
- [ ] **Progress Logging**: Detailed execution logging for audit

##### Post-Migration (Required)
- [ ] **Integrity Validation**: Verify data and referential integrity
- [ ] **Performance Validation**: Check query performance impact
- [ ] **Schema Documentation**: Update schema documentation
- [ ] **Lock Release**: Clean up migration locks
- [ ] **Monitoring**: Enhanced monitoring for migration impact

---

**DataFlow: Zero-config database framework with enterprise-grade migration system. Every function accessible, every pattern optimized, every scale supported with maximum safety.** 🚀
