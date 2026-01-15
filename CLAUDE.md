# Important Directives 📜
1. Always use kailash SDK with its frameworks to implement.
2. Always use the specialist subagents (nexus-specialist, dataflow-specialist, mcp-specialist, kaizen-specialist) when working with the frameworks.
3. Never attempt to write codes from scratch before checking the frameworks with the specialist subagents.
   - Instead of using direct SQL, SQLAlchemy, Django ORM, always check with the dataflow-specialist on how to do it with the dataflow framework
   - Instead of building your own API gateway or use FastAPI, always check with the nexus-specialist on how to do it with the nexus framework
   - Instead of building your own MCP server/client, always check with the mcp-specialist on how to do it with the mcp_server module inside the core SDK
   - Instead of building your own agentic platform, always check with the kaizen-specialist on how to do it with the kaizen framework
4. **CRITICAL: ALWAYS load environment variables from .env before ANY operation**
   - **For pytest**: ALWAYS prefix with environment variables OR use pytest-dotenv.
   - **For Docker**: ALWAYS use docker-compose with env_file OR pass --env-file.
   - **For Python scripts**: Load dotenv at top of file.
   - **NEVER run tests/scripts without checking .env first** - assume ALL API keys exist there

## 🏗️ Documentation

### Core SDK (`sdk-users/`)
**Foundational building blocks** for workflow automation:
- **Purpose**: Custom workflows, fine-grained control, integrations
- **Components**: WorkflowBuilder, LocalRuntime, 110+ nodes, MCP integration
- **Usage**: Direct workflow construction with full programmatic control
- **Install**: `pip install kailash`

### DataFlow (`sdk-users/apps/dataflow/`)
**Zero-config database framework** built on Core SDK:
- **Purpose**: Database operations with automatic model-to-node generation
- **Features**: @db.model decorator generates 11 nodes per model automatically:
  - CRUD: CREATE, READ, UPDATE, DELETE, LIST, UPSERT, COUNT
  - Bulk: BULK_CREATE, BULK_UPDATE, BULK_DELETE, BULK_UPSERT
  - DataFlow IS NOT AN ORM!
- **Usage**: Database-first applications with enterprise features
- **Install**: `pip install kailash-dataflow`
- **Import**: `from dataflow import DataFlow`

### Nexus (`sdk-users/apps/nexus/`)
**Multi-channel platform** built on Core SDK:
- **Purpose**: Deploy workflows as API + CLI + MCP simultaneously
- **Features**: Unified sessions, zero-config platform deployment
- **Usage**: Platform applications requiring multiple access methods
- **Install**: `pip install kailash-nexus`
- **Import**: `from nexus import Nexus`

### Kaizen (`sdk-users/apps/kaizen/`)
**AI agent framework** built on Core SDK:
- **Purpose**: Production-ready AI agents with multi-modal processing, multi-agent coordination, and enterprise features built on Kailash SDK
- **Features**: Signature-based programming, BaseAgent architecture, automatic optimization, error handling, audit trails
- **Usage**: Agentic applications requiring robust AI capabilities
- **Install**: `pip install kailash-kaizen`
- **Import**: `from kaizen.* import ...`

### Critical Relationships
- **DataFlow, Nexus, and Kaizen are built ON Core SDK** - they don't replace it
- **Framework choice affects development patterns** - different approaches for each
- **All use the same underlying workflow execution** - `runtime.execute(workflow.build())`

## 🎯 Specialized Subagents

### Analysis & Planning
- **ultrathink-analyst** → Deep failure analysis, complexity assessment
- **requirements-analyst** → Requirements breakdown, ADR creation
- **sdk-navigator** → Find patterns before coding, resolve errors during development
- **framework-advisor** → Choose Core SDK, DataFlow, or Nexus; coordinates with specialists

### Framework Implementation
- **nexus-specialist** → Multi-channel platform implementation (API/CLI/MCP)
- **dataflow-specialist** → Database operations with auto-generated nodes. String IDs preserved, multi-instance isolation, deferred schema ops (PostgreSQL + SQLite)

### Core Implementation
- **pattern-expert** → Workflow patterns, nodes, parameters
- **tdd-implementer** → Test-first development
- **intermediate-reviewer** → Review after todos and implementation
- **gold-standards-validator** → Compliance checking

### Testing & Validation
- **testing-specialist** → 3-tier strategy with real infrastructure
- **documentation-validator** → Test code examples, ensure accuracy

### Release & Operations
- **todo-manager** → Task management and project tracking
- **mcp-specialist** → MCP server implementation and integration
- **git-release-specialist** → Git workflows, CI validation, releases

### Success Factors
- **What Worked Well** ✅
  1. Systematic Task Completion - Finishing each task completely before moving on
  2. Test-First Development: Writing all tests before implementation prevented bugs
  3. Comprehensive Testing: Catching issues early with comprehensive tests
  4. Real Infrastructure Testing - NO MOCKING policy found real-world issues
  5. Evidence-Based Tracking: Clear audit trail with file:line references made progress clear
  6. Comprehensive Documentation: Guides provide clear path for users and prevent future support questions
  7. Subagent Specialization - Right agent for each task type
  8. Manual Verification: Running all examples caught integration issues
  9. Design System Foundation: Creating comprehensive design system FIRST prevented inconsistencies
  10. Institutional Directives: Documented design patterns as mandatory guides for future work
  11. Component Reusability: Building 16 reusable components eliminated redundant work
  12. Responsive-First Design: Building responsive patterns from the start prevented mobile/desktop divergence
  13. Dark Mode Built-In: Supporting dark mode in all components from day 1 avoided retrofitting
  14. Design Token System: Using centralized tokens (colors, spacing, typography) enabled easy theme changes

- **Lessons Learned** 🎓
  1. Documentation Early: Writing guides after implementation is easier
  2. Pattern Consistency: Following same structure across examples reduces errors
  3. Incremental Validation: Verifying tests pass immediately prevents compounding issues
  4. Comprehensive Coverage: Detailed documentation prevents future questions
  5. Design System as Foundation: Create design system BEFORE features to enforce consistency
  6. Mandatory Guides: Institutionalizing design patterns as "must follow" directives prevents drift
  7. Single Import Pattern: Consolidating all design system exports into one file (design_system.dart) simplifies usage
  8. Component Showcase: Building live demo app while developing components catches UX issues early
  9. Deprecation Fixes: Address all deprecations immediately to prevent tech debt accumulation
  10. Real Device Testing: Testing on actual trackpad/touch reveals issues that simulators miss
  11. Pointer Events for Touch: Low-level pointer events (PointerDownEvent, PointerMoveEvent) handle trackpad/touch better than high-level gestures alone
  12. Responsive Testing: Test at all three breakpoints (mobile/tablet/desktop) for every feature

## ⚡ Essential Pattern (All Frameworks)

### For Docker/FastAPI Deployment (RECOMMENDED)
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime  # Docker-optimized runtime

workflow = WorkflowBuilder()
workflow.add_node("NodeName", "id", {"param": "value"})  # String-based
runtime = AsyncLocalRuntime()  # Async-first, no threading
results, run_id = await runtime.execute_workflow_async(workflow.build(), inputs={})  # Same return as LocalRuntime!
```

### For CLI/Scripts (Sync Contexts)
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("NodeName", "id", {"param": "value"})  # String-based
runtime = LocalRuntime()  # Inherits from BaseRuntime with 3 mixins
results, run_id = runtime.execute(workflow.build())  # ALWAYS .build()
```

### Auto-Detection (Simplest)
```python
from kailash.runtime import get_runtime

# Automatically selects AsyncLocalRuntime for Docker/FastAPI,
# LocalRuntime for CLI/scripts
runtime = get_runtime()  # Defaults to "async" context
```

### Runtime Architecture (Internal)
Both LocalRuntime and AsyncLocalRuntime inherit from BaseRuntime and use shared mixins:

**BaseRuntime Foundation**:
- 29 configuration parameters (debug, enable_cycles, conditional_execution, connection_validation, etc.)
- Execution metadata management (run IDs, workflow caching)
- Common initialization and validation modes (strict, warn, off)

**Shared Mixins**:
- **CycleExecutionMixin**: Cycle execution delegation to CyclicWorkflowExecutor with validation and error wrapping
- **ValidationMixin**: Workflow structure validation (5 methods)
  - validate_workflow(): Checks workflow structure, node connections, parameter mappings
  - _validate_connection_contracts(): Validates connection parameter contracts
  - _validate_conditional_execution_prerequisites(): Validates conditional execution setup
  - _validate_switch_results(): Validates switch node results
  - _validate_conditional_execution_results(): Validates conditional execution results
- **ConditionalExecutionMixin**: Conditional execution and branching logic with SwitchNode support
  - Pattern detection and cycle detection
  - Node skipping and hierarchical execution
  - Conditional workflow orchestration

**LocalRuntime-Specific Features**:
- Enhanced error messages via _generate_enhanced_validation_error()
- Connection context building via _build_connection_context()
- Public validation API: get_validation_metrics(), reset_validation_metrics()

**ParameterHandlingMixin Not Used**:
LocalRuntime uses WorkflowParameterInjector for enterprise parameter handling instead of ParameterHandlingMixin (architectural boundary for complex workflows).

**Usage**:
```python
# Configuration from BaseRuntime (29 parameters)
runtime = LocalRuntime(
    debug=True,
    enable_cycles=True,                    # CycleExecutionMixin
    conditional_execution="skip_branches",  # ConditionalExecutionMixin
    connection_validation="strict"          # ValidationMixin (strict/warn/off)
)
results, run_id = runtime.execute(workflow.build())

# Validation metrics (LocalRuntime public API)
metrics = runtime.get_validation_metrics()
runtime.reset_validation_metrics()
```

This architecture ensures consistent behavior between sync and async runtimes with no API changes.

**AsyncLocalRuntime-Specific Features**:
AsyncLocalRuntime extends LocalRuntime with async-optimized execution:
- **WorkflowAnalyzer**: Analyzes workflows to determine optimal execution strategy
- **ExecutionContext**: Async execution context with integrated resource access
- **Execution Strategies**: Automatically selects pure async, mixed, or sync-only execution
- **Level-Based Parallelism**: Executes independent nodes concurrently within dependency levels
- **Thread Pool**: Executes sync nodes without blocking async loop
- **Semaphore Control**: Limits concurrent executions to prevent resource exhaustion

Inherits all LocalRuntime capabilities through MRO:
- All 29 BaseRuntime configuration parameters
- All mixin methods (cycle execution, validation, conditional execution)
- Enhanced error messages and validation metrics

**Usage**:
```python
from kailash.runtime import AsyncLocalRuntime

# Same configuration as LocalRuntime
runtime = AsyncLocalRuntime(
    debug=True,
    enable_cycles=True,                    # CycleExecutionMixin
    conditional_execution="skip_branches",  # ConditionalExecutionMixin
    connection_validation="strict",         # ValidationMixin
    max_concurrent_nodes=10                 # AsyncLocalRuntime-specific
)
results, run_id = await runtime.execute_workflow_async(workflow.build(), inputs={})

# All inherited methods available
runtime.validate_workflow(workflow)  # ValidationMixin
metrics = runtime.get_validation_metrics()  # LocalRuntime
```

This inheritance ensures 100% feature parity between sync and async runtimes, including identical return structures.

## ⚠️ Critical Rules
- ALWAYS: `runtime.execute(workflow.build())`
- NEVER: `workflow.execute(runtime)`
- String-based nodes: `workflow.add_node("NodeName", "id", {})`
- Real infrastructure: NO MOCKING in Tiers 2-3 tests
- **Return Structure**: Both LocalRuntime and AsyncLocalRuntime return `(results, run_id)` - identical structure
- **Docker/FastAPI**: Use `AsyncLocalRuntime()` or `WorkflowAPI()` (defaults to async)
- **CLI/Scripts**: Use `LocalRuntime()` for synchronous execution

## 🚨 DataFlow Critical Rules (MUST READ)

**These 3 mistakes cause 90% of DataFlow debugging time. READ THIS BEFORE WRITING ANY DataFlow CODE:**

### 1. NEVER Manually Set `created_at` or `updated_at` (DF-104 Error)

DataFlow **automatically manages** timestamp fields. Manually setting them causes PostgreSQL errors:

```
DatabaseError: multiple assignments to same column "updated_at"
```

```python
# ❌ WRONG - Causes DF-104 error
async def update_user(self, id: str, data: dict) -> dict:
    now = datetime.now(UTC).isoformat()
    data["updated_at"] = now  # ❌ NEVER DO THIS!

    workflow.add_node("UserUpdateNode", "update", {
        "filter": {"id": id},
        "fields": data  # Error: multiple assignments to updated_at
    })

# ✅ CORRECT - Let DataFlow handle timestamps
async def update_user(self, id: str, data: dict) -> dict:
    # Remove any timestamp fields if present
    data.pop("updated_at", None)
    data.pop("created_at", None)

    workflow.add_node("UserUpdateNode", "update", {
        "filter": {"id": id},
        "fields": data  # DataFlow sets updated_at automatically
    })
```

**Auto-managed fields (NEVER include in CreateNode or UpdateNode):**
- `created_at` - Set automatically on record creation
- `updated_at` - Set automatically on every modification

### 2. CreateNode vs UpdateNode Have DIFFERENT Parameter Patterns

```python
# CreateNode: FLAT fields at top level
workflow.add_node("UserCreateNode", "create", {
    "id": "user-001",
    "name": "Alice",
    "email": "alice@example.com"
})

# UpdateNode: NESTED filter + fields structure
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-001"},      # Which records
    "fields": {"name": "Alice Updated"}  # What to change
})
```

### 3. Primary Key MUST Be Named `id`

```python
# ❌ WRONG - Will fail
@db.model
class User:
    user_id: str  # DataFlow requires 'id', not 'user_id'

# ✅ CORRECT
@db.model
class User:
    id: str  # Must be exactly 'id'
    name: str
```

### 4. `soft_delete` Only Affects DELETE, NOT Queries

```python
# soft_delete config ONLY converts DELETE to UPDATE deleted_at
@db.model
class Patient:
    id: str
    deleted_at: Optional[str] = None
    __dataflow__ = {"soft_delete": True}  # Only affects DeleteNode!

# ❌ WRONG ASSUMPTION - Queries do NOT auto-filter
workflow.add_node("PatientListNode", "list", {"filter": {}})
# Returns ALL patients INCLUDING soft-deleted ones!

# ✅ CORRECT - Manually filter for non-deleted records
workflow.add_node("PatientListNode", "list", {
    "filter": {"deleted_at": {"$null": True}}  # WHERE deleted_at IS NULL
})
```

### 5. Query Operators for NULL Checking (v0.10.6+)

```python
# $null operator for IS NULL
workflow.add_node("PatientListNode", "active", {
    "filter": {"deleted_at": {"$null": True}}
})

# $exists operator for IS NOT NULL
workflow.add_node("PatientListNode", "deleted", {
    "filter": {"deleted_at": {"$exists": True}}
})

# $eq with None also works (v0.10.6+)
workflow.add_node("PatientListNode", "active", {
    "filter": {"deleted_at": {"$eq": None}}
})
```

### 6. Result Keys by Node Type

| Node Type | Result Key | Access Pattern |
|-----------|------------|----------------|
| ListNode | `records` | `results["list"]["records"]` |
| CountNode | `count` | `results["count"]["count"]` |
| ReadNode | (direct) | `results["read"]` → dict |
| UpsertNode | `record`, `created` | `results["upsert"]["record"]` |

## 🐳 Docker Deployment
- WorkflowAPI now defaults to AsyncLocalRuntime (async-first, no threads).

### WorkflowAPI (Recommended for Docker)
```python
from kailash.api.workflow_api import WorkflowAPI

# WorkflowAPI automatically uses AsyncLocalRuntime
api = WorkflowAPI(my_workflow)  # Docker-optimized by default
api.run(port=8000)  # No hanging, 10-100x faster
```

### Manual Runtime Selection
```python
from kailash.runtime import AsyncLocalRuntime, LocalRuntime

# For Docker/FastAPI (async contexts)
runtime = AsyncLocalRuntime()

# For CLI/scripts (sync contexts)
runtime = LocalRuntime()

# Or use helper
from kailash.runtime import get_runtime
runtime = get_runtime("async")  # or "sync"
```

## 🐳 DataFlow Docker Deployment

### ✅ auto_migrate=True Now Works in Docker/FastAPI (v0.10.15+)

**FIXED**: As of v0.10.15, `auto_migrate=True` works in Docker/FastAPI for file-based databases (PostgreSQL, SQLite file).

**How it works**: DataFlow uses `SyncDDLExecutor` with synchronous drivers (psycopg2, sqlite3) for DDL. No event loop involvement - works in any context.

### ✅ Zero-Config Pattern (RECOMMENDED for file-based databases)

```python
from dataflow import DataFlow
from fastapi import FastAPI

# auto_migrate=True (default) works for PostgreSQL and SQLite file databases!
db = DataFlow("postgresql://...")

@db.model  # Tables created immediately via sync DDL
class User:
    id: str
    name: str
    email: str

app = FastAPI()

@app.post("/users")
async def create_user(data: dict):
    return await db.express.create("User", data)
```

### ⚠️ Limitation: In-Memory SQLite

In-memory databases (`:memory:`) do NOT use sync DDL because each connection gets a separate database. For in-memory SQLite, use the lifespan pattern:

```python
db = DataFlow(":memory:", auto_migrate=False)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.create_tables_async()  # Uses shared connection
    yield
```

### Pattern Summary

| Context | Pattern | Notes |
|---------|---------|-------|
| **PostgreSQL** | `auto_migrate=True` (default) | ✅ Uses sync DDL (psycopg2) |
| **SQLite file** | `auto_migrate=True` (default) | ✅ Uses sync DDL (sqlite3) |
| **SQLite :memory:** | `auto_migrate=False` + `create_tables_async()` | ⚠️ Sync DDL not supported |
| **CLI Scripts** | `auto_migrate=True` (default) | Always worked |
| **pytest (async)** | `auto_migrate=True` (default) | ✅ Uses sync DDL |

### DataFlow Express (23x Faster CRUD)

For high-performance API endpoints, use `db.express` instead of workflows:

```python
# Express API: Direct node invocation, 23x faster than workflows
user = await db.express.create("User", {"id": "user-123", "name": "Alice"})
user = await db.express.read("User", "user-123")  # Primary key lookup
user = await db.express.find_one("User", {"email": "alice@example.com"})  # Non-PK lookup (v0.10.13+)
users = await db.express.list("User", filter={"status": "active"}, limit=100)
count = await db.express.count("User", filter={"status": "active"})
user = await db.express.update("User", "user-123", {"name": "Alice Updated"})
deleted = await db.express.delete("User", "user-123")

# Performance: ~0.27ms vs ~6.3ms per operation
```

**read() vs find_one():**
- `read(model, id)` - Lookup by primary key (fast, direct)
- `find_one(model, filter)` - Lookup by any field(s) using MongoDB-style filter

### Complete FastAPI + DataFlow Example

```python
from dataflow import DataFlow
from fastapi import FastAPI

# Zero-config: auto_migrate=True works for file-based databases!
db = DataFlow("postgresql://user:pass@localhost:5432/mydb")

@db.model  # Tables created immediately
class User:
    id: str
    name: str
    email: str

app = FastAPI()

# Step 4: Use Express for CRUD endpoints
@app.post("/users")
async def create_user(data: dict):
    return await db.express.create("User", data)

@app.get("/users/{id}")
async def get_user(id: str):
    return await db.express.read("User", id)

@app.get("/users")
async def list_users(limit: int = 100):
    return await db.express.list("User", limit=limit)
```

## 🔧 DataFlow Centralized Logging (v0.10.12+)

Control log verbosity with LoggingConfig for cleaner output:

```python
from dataflow import DataFlow, LoggingConfig
import logging

# Option 1: Simple log level
db = DataFlow("postgresql://...", log_level=logging.WARNING)

# Option 2: Full configuration with presets
db = DataFlow("postgresql://...", log_config=LoggingConfig.production())

# Option 3: Environment variables (12-factor app)
# DATAFLOW_LOG_LEVEL=WARNING
# DATAFLOW_NODE_EXECUTION_LOG_LEVEL=ERROR
config = LoggingConfig.from_env()
```

### Logging Presets

| Preset | Use Case |
|--------|----------|
| `LoggingConfig.production()` | Clean production logs (WARNING+) |
| `LoggingConfig.development()` | Verbose debugging (DEBUG) |
| `LoggingConfig.quiet()` | Minimal output (ERROR only) |
| `LoggingConfig.from_env()` | Environment variable configuration |

### Category-Specific Logging

```python
config = LoggingConfig(
    level=logging.WARNING,           # Default for all categories
    node_execution=logging.ERROR,    # Node execution only errors
    sql_generation=logging.WARNING,  # SQL generation
    migration=logging.INFO           # Migration operations
)
```

### Sensitive Value Masking

```python
from dataflow import LoggingConfig, mask_sensitive

config = LoggingConfig(mask_sensitive_values=True)
data = {"password": "secret123", "api_key": "sk-xxx"}
masked = mask_sensitive(data, config)
# {'password': '***MASKED***', 'api_key': '***MASKED***'}
```

## 🔧 Async-Safe Utilities (v0.10.6+)

For custom sync→async bridging, use `async_safe_run`:

```python
from dataflow.core.async_utils import async_safe_run

# Works in both sync contexts (CLI) and async contexts (FastAPI)
async def my_async_op():
    return await some_async_call()

result = async_safe_run(my_async_op())  # Works everywhere!
```
