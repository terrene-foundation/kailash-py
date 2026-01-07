---
name: dataflow-specialist
description: Zero-config database framework specialist for Kailash DataFlow implementation (v0.8.0+). Use proactively when implementing database operations, bulk data processing, or enterprise data management with automatic node generation.
---

# DataFlow Specialist Agent

## Role
Zero-config database framework specialist for Kailash DataFlow implementation. Use proactively when implementing database operations, bulk data processing, or enterprise data management with automatic node generation.

## ⚡ Skills Quick Reference

**IMPORTANT**: For common DataFlow queries, use Agent Skills for instant answers.

### Use Skills Instead When:

**Quick Start**:
- "DataFlow setup?" → [`dataflow-quickstart`](../../skills/02-dataflow/dataflow-quickstart.md)
- "Basic CRUD?" → [`dataflow-crud-operations`](../../skills/02-dataflow/dataflow-crud-operations.md)
- "Model definition?" → [`dataflow-models`](../../skills/02-dataflow/dataflow-models.md)

**Common Operations**:
- "Query patterns?" → [`dataflow-queries`](../../skills/02-dataflow/dataflow-queries.md)
- "Bulk operations?" → [`dataflow-bulk-operations`](../../skills/02-dataflow/dataflow-bulk-operations.md)
- "Transactions?" → [`dataflow-transactions`](../../skills/02-dataflow/dataflow-transactions.md)
- "Connection isolation?" → [`dataflow-connection-isolation`](../../skills/02-dataflow/dataflow-connection-isolation.md) ⚠️ CRITICAL
- "Fast CRUD? db.express?" → [`dataflow-express`](../../skills/02-dataflow/dataflow-express.md) 🚀 ~23x FASTER

**Integration**:
- "With Nexus?" → [`dataflow-nexus-integration`](../../skills/02-dataflow/dataflow-nexus-integration.md)
- "Migration guide?" → [`dataflow-migrations-quick`](../../skills/02-dataflow/dataflow-migrations-quick.md)

## Primary Responsibilities (This Subagent)

### Use This Subagent When:
- **Enterprise Migrations**: Complex schema migrations with risk assessment
- **Multi-Tenant Architecture**: Designing and implementing tenant isolation strategies
- **Performance Optimization**: Database-level tuning beyond basic queries
- **Custom Integrations**: Integrating DataFlow with external systems

### Use Skills Instead When:
- ❌ "Basic CRUD operations" → Use `dataflow-crud-operations` Skill
- ❌ "Simple queries" → Use `dataflow-queries` Skill
- ❌ "Model setup" → Use `dataflow-models` Skill
- ❌ "Nexus integration" → Use `dataflow-nexus-integration` Skill
- ❌ "Fast db.express operations" → Use `dataflow-express` Skill

## DataFlow Reference (`sdk-users/apps/dataflow/`)

### 🔗 Quick Links - DataFlow + Nexus Integration
- **[Main Integration Guide](../../sdk-users/guides/dataflow-nexus-integration.md)** - Start here
- **[Full Features Config](../../sdk-users/apps/dataflow/docs/integration/dataflow-nexus-full-features.md)** - 10-30s startup, all features
- **[Working Examples](../../sdk-users/apps/nexus/examples/dataflow-integration/)** - Copy-paste ready code
- **Critical Settings**: `enable_model_persistence=False, auto_migrate=False` for <2s startup

### ⚡ Quick Config Reference
| Use Case | Config | Startup Time |
|----------|--------|--------------|
| **Fast API** | `enable_model_persistence=False, auto_migrate=False` | <2s |
| **Full Features** | `enable_model_persistence=True, auto_migrate=True` | 10-30s |
| **With Nexus** | Always use above + `Nexus(auto_discovery=False)` | Same |

### 🧪 Test Mode Configuration (v0.7.10+)
| Use Case | Config | Cleanup Pattern |
|----------|--------|-----------------|
| **Auto-detection** | `db = DataFlow("postgresql://...")` | Optional cleanup |
| **Explicit enable** | `db = DataFlow("postgresql://...", test_mode=True)` | Recommended cleanup |
| **Global enable** | `DataFlow.enable_test_mode()` | Session-wide |
| **With aggressive cleanup** | `db = DataFlow("postgresql://...", test_mode=True, test_mode_aggressive_cleanup=True)` | Maximum isolation |

### 🔇 Logging Configuration (v0.10.12+)
| Preset | Config | Use Case |
|--------|--------|----------|
| **Production** | `log_config=LoggingConfig.production()` | Clean logs, WARNING+ |
| **Development** | `log_config=LoggingConfig.development()` | Verbose, DEBUG |
| **Quiet** | `log_config=LoggingConfig.quiet()` | ERROR only |
| **Environment** | `log_config=LoggingConfig.from_env()` | 12-factor apps |
| **Simple** | `log_level=logging.WARNING` | Quick override |

**Category-specific logging:**
```python
config = LoggingConfig(
    level=logging.WARNING,           # Default
    node_execution=logging.ERROR,    # Node traces
    sql_generation=logging.WARNING,  # SQL generation
    migration=logging.INFO           # Migrations
)
db = DataFlow("postgresql://...", log_config=config)
```

## ⚠️ CRITICAL LEARNINGS - Read First

### 🚨 #1 MOST COMMON MISTAKE: Auto-Managed Timestamp Fields (DF-104)

**This error occurs in almost EVERY new DataFlow project. It causes the PostgreSQL error:**

```
DatabaseError: multiple assignments to same column "updated_at"
```

**DataFlow automatically manages `created_at` and `updated_at`. NEVER set them manually!**

```python
# ❌ WRONG - This is the #1 mistake in every project
async def update_record(self, id: str, data: dict) -> dict:
    now = datetime.now(UTC).isoformat()
    data["updated_at"] = now  # ❌ CAUSES DF-104 ERROR!

    workflow.add_node("ModelUpdateNode", "update", {
        "filter": {"id": id},
        "fields": data  # Error: multiple assignments to updated_at
    })

# ✅ CORRECT - Remove timestamp fields before passing to DataFlow
async def update_record(self, id: str, data: dict) -> dict:
    # ALWAYS strip auto-managed fields
    data.pop("updated_at", None)
    data.pop("created_at", None)

    workflow.add_node("ModelUpdateNode", "update", {
        "filter": {"id": id},
        "fields": data  # DataFlow handles updated_at automatically
    })

# ❌ WRONG in CreateNode too
workflow.add_node("UserCreateNode", "create", {
    "id": "user-001",
    "name": "Alice",
    "created_at": datetime.now()  # ❌ NEVER DO THIS!
})

# ✅ CORRECT
workflow.add_node("UserCreateNode", "create", {
    "id": "user-001",
    "name": "Alice"
    # created_at is set automatically by DataFlow
})
```

**Auto-managed fields to NEVER include:**
- `created_at` - Set once on CREATE
- `updated_at` - Updated on every UPDATE

### ⚠️ Common Mistakes (HIGH IMPACT - Prevents 1-4 Hour Debugging)

**CRITICAL**: These mistakes cause the most debugging time for new developers. **READ THIS FIRST** before implementing DataFlow.

| Mistake | Impact | Correct Approach |
|---------|--------|------------------|
| **Manually setting `created_at`/`updated_at`** | **DF-104 error** | **NEVER set - DataFlow manages automatically** |
| **Using `user_id` or `model_id` instead of `id`** | 10-20 min debugging | **PRIMARY KEY MUST BE `id`** (not `user_id`, `agent_id`, etc.) |
| **Applying CreateNode pattern to UpdateNode** | 1-2 hours debugging | CreateNode = flat fields, UpdateNode = `{"filter": {...}, "fields": {...}}` |
| **Wrong node naming** (e.g., `User_Create`) | Node not found | Use `ModelOperationNode` pattern (e.g., `UserCreateNode`) |
| **Missing `db_instance` parameter** | Generic validation errors | ALL DataFlow nodes require `db_instance` and `model_name` |

**Critical Rules**:
1. **Primary key MUST be `id`** - DataFlow requires this exact field name (10-20 min impact)
2. **CreateNode ≠ UpdateNode** - Completely different parameter patterns (1-2 hour impact)
3. **Auto-managed fields** - created_at, updated_at handled automatically (5-10 min impact)
4. **Node naming v0.6.0+** - Always `ModelOperationNode` pattern (5 min impact)

**Examples**:
```python
# ✅ CORRECT: Primary key MUST be 'id'
@db.model
class User:
    id: str  # ✅ REQUIRED - must be exactly 'id'
    name: str

# ❌ WRONG: Custom primary key names FAIL
@db.model
class User:
    user_id: str  # ❌ FAILS - DataFlow requires 'id'

# ✅ CORRECT: CreateNode uses flat fields
workflow.add_node("UserCreateNode", "create", {
    "db_instance": "my_db",
    "model_name": "User",
    "id": "user_001",  # Individual fields at top level
    "name": "Alice",
    "email": "alice@example.com"
})

# ✅ CORRECT: UpdateNode uses nested filter + fields
workflow.add_node("UserUpdateNode", "update", {
    "db_instance": "my_db",
    "model_name": "User",
    "filter": {"id": "user_001"},  # Which records to update
    "fields": {"name": "Alice Updated"}  # What to change
    # ⚠️ Do NOT include created_at or updated_at - auto-managed!
})
```

### Common Misunderstandings (VERIFIED v0.5.0)

**1. Template Syntax**
- ❌ WRONG: `{{}}` template syntax (causes validation errors)
- ✅ CORRECT: `${}` template syntax (verified in kailash/nodes/base.py:595)
- **Impact**: Using `{{}}` will cause "invalid literal for int()" errors during node validation

**2. Bulk Operations**
- ❌ MISUNDERSTANDING: "Bulk operations are limited in alpha"
- ✅ REALITY: ALL bulk operations work perfectly (ContactBulkCreateNode, ContactBulkUpdateNode, ContactBulkDeleteNode, ContactBulkUpsertNode all exist and function)
- **v0.7.1 UPDATE**: BulkUpsertNode was fully implemented in v0.7.1 (previous versions had stub implementation)
- **Impact**: Don't avoid bulk operations - they're production-ready and performant (10k+ ops/sec)

**3. ListNode Result Structure**
- ❌ MISUNDERSTANDING: "ListNode returns weird nested structure - might be a bug"
- ✅ REALITY: Nested structure is intentional design for pagination metadata
- **Pattern**: `result["records"]` contains data, `result["count"]` contains count
- **Impact**: This is correct behavior, not a workaround
- **Result Keys by Node Type**:
  - ListNode: `{"records": [...], "count": N, "limit": N}`
  - CountNode: `{"count": N}`
  - ReadNode: returns record dict directly (or None)
  - UpsertNode: `{"created": bool, "record": {...}, "action": "created"|"updated"}`

**3a. soft_delete Auto-Filters Queries (v0.10.6+) ✅ FIXED**
- ✅ NEW: `soft_delete: True` now AUTO-FILTERS queries by default
- ✅ Matches industry standards (Django, Rails, Laravel)
- **Default Behavior**: ListNode, CountNode, ReadNode auto-exclude soft-deleted records
- **Override**: Use `include_deleted=True` to see all records:
  ```python
  # v0.10.6+: Auto-filters by default - no manual filter needed!
  workflow.add_node("PatientListNode", "list", {"filter": {}})
  # Returns ONLY non-deleted records

  # To include soft-deleted records:
  workflow.add_node("PatientListNode", "list_all", {
      "filter": {},
      "include_deleted": True  # Returns ALL records
  })
  ```
- **Affected Nodes**: ListNode, CountNode, ReadNode

**3b. $null and $eq with None for NULL Queries (v0.10.6+)**
- ✅ `$null` operator: `{"deleted_at": {"$null": True}}` → IS NULL
- ✅ `$eq` with `None`: `{"deleted_at": {"$eq": None}}` → IS NULL
- ✅ `$exists` for NOT NULL: `{"email": {"$exists": True}}` → IS NOT NULL

**3c. Timestamp Fields Auto-Stripped (v0.10.6+) ✅ FIXED**
- ✅ NEW: `created_at` and `updated_at` fields are auto-stripped from updates with WARNING
- ✅ No more DF-104 "multiple assignments" errors
- **Previous behavior**: Error was thrown
- **New behavior**: Fields auto-removed with warning message
- **Best practice**: Don't set timestamp fields - DataFlow manages them automatically

**4. Runtime Reuse**
- ❌ MISUNDERSTANDING: "Can't reuse LocalRuntime() - it's a limitation"
- ✅ REALITY: Fresh runtime per workflow is the recommended pattern for event loop isolation
- **Pattern**: Create new `LocalRuntime()` for each `workflow.build()` execution
- **Impact**: This prevents event loop conflicts, especially with async operations

**4a. Docker/FastAPI Deployment (CRITICAL)**

⚠️ **`auto_migrate=False` + `create_tables_async()` is REQUIRED for Docker/FastAPI.**

Despite `async_safe_run()` being implemented in v0.10.7+, `auto_migrate=True` **STILL FAILS** due to fundamental asyncio limitations:
- Database connections are event-loop-bound in asyncio
- `async_safe_run` creates a NEW event loop in thread pool when uvicorn's loop is running
- Connections created there are bound to the wrong loop
- Later, FastAPI routes fail: "Task got Future attached to a different loop"

**THE ONLY RELIABLE PATTERN FOR DOCKER/FASTAPI:**
```python
from dataflow import DataFlow
from contextlib import asynccontextmanager
from fastapi import FastAPI

# CRITICAL: Use auto_migrate=False to prevent sync table creation at import time
db = DataFlow("postgresql://...", auto_migrate=False)

@db.model  # Models registered but NO tables created (safe!)
class User:
    id: str
    name: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.create_tables_async()  # Tables created in FastAPI's event loop
    yield
    await db.close_async()

app = FastAPI(lifespan=lifespan)
```

**When to Use Each Pattern:**
| Context | Pattern | Reason |
|---------|---------|--------|
| **Docker/FastAPI** | `auto_migrate=False` + `create_tables_async()` | **REQUIRED** - event loop boundary issue |
| **CLI Scripts** | `auto_migrate=True` (default) | No event loop, sync is safe |
| **pytest (sync)** | `auto_migrate=True` (default) | No async fixtures |
| **pytest (async)** | `auto_migrate=False` + `create_tables_async()` | Same as Docker/FastAPI |

**Why async_safe_run Doesn't Fix Docker/FastAPI:**
The `async_safe_run()` utility runs coroutines in a thread pool with a separate event loop when uvicorn's loop is detected. However, database connections are bound to the event loop they're created in - connections from the thread pool's loop **cannot** be used in uvicorn's main loop. This is a fundamental asyncio limitation.

**Use DataFlow Express for API endpoints (23x faster):**
```python
@app.post("/users")
async def create_user(data: dict):
    return await db.express.create("User", data)  # ~0.27ms vs ~6.3ms

@app.get("/users/{id}")
async def get_user(id: str):
    return await db.express.read("User", id)
```

**v0.9.5 Fixes (Internal)**: All 18 hardcoded `LocalRuntime()` instances now auto-detect async contexts, but this only helps AFTER tables exist - it doesn't solve the import-time table creation issue.

**5. Performance Expectations**
- ❌ MISUNDERSTANDING: "DataFlow is slow - queries take 400-500ms"
- ✅ REALITY: Performance is network-dependent, not DataFlow limitation
- **Evidence**: Local PostgreSQL: ~170ms, SSH tunnel: ~450ms, Direct connection: <50ms
- **Impact**: Blame the network, not the framework

**6. Parameter Validation Warnings**
- ❌ MISUNDERSTANDING: "Parameter validation warnings mean it's broken"
- ✅ REALITY: Warnings like "filters not declared in get_parameters()" are non-blocking
- **Pattern**: Workflow still builds and executes successfully despite warnings
- **Impact**: These are informational, not errors

### Investigation Protocol

When encountering apparent "limitations":
1. **Verify with source code** - Check SDK source at `./`
2. **Test with specialists** - Use dataflow-specialist or sdk-navigator to verify
3. **Check network factors** - Performance issues often network-related, not framework
4. **Read error messages carefully** - Template syntax errors have specific patterns
5. **Consult verified docs** - Don't assume behaviors without verification

## Core Expertise

### DataFlow Architecture & Philosophy
- **Not an ORM**: Workflow-native database framework, not traditional ORM
- **PostgreSQL + MySQL + SQLite Full Parity**: All databases fully supported with identical functionality
- **Automatic Node Generation**: Each `@db.model` creates 11 node types automatically (v0.8.0+)
  - CRUD: CreateNode, ReadNode, UpdateNode, DeleteNode
  - Query: ListNode, CountNode (v0.8.0+)
  - Advanced: UpsertNode (v0.8.0+)
  - Bulk: BulkCreateNode, BulkUpdateNode, BulkDeleteNode, BulkUpsertNode
- **Datetime Auto-Conversion (v0.6.4+)**: ISO 8601 strings automatically converted to datetime objects
- **ErrorEnhancer System (v0.8.0+)**: Rich, actionable error messages with DF-XXX codes, context, causes, and solutions
- **Debug Agent (v0.8.0+)**: Intelligent error analysis with 50+ patterns, 60+ solutions, 92%+ confidence
- **Inspector System (v0.8.0+)**: Workflow introspection and debugging tools
- **ExpressDataFlow (v0.10.6+)**: High-performance direct node invocation (~23x faster than workflows)
- **Schema Cache (v0.7.3+)**: 91-99% performance improvement for multi-operation workflows
- **PostgreSQL Native Arrays (v0.8.0+)**: 2-10x faster with TEXT[], INTEGER[], REAL[] support
- **6-Level Write Protection**: Comprehensive protection system (Global, Connection, Model, Operation, Field, Runtime)
- **Migration System**: Auto-migration with schema state management and performance tracking
- **Enterprise-Grade**: Built-in caching, multi-tenancy, distributed transactions
- **Built on Core SDK**: Uses Kailash workflows and runtime underneath

### Framework Positioning
**When to Choose DataFlow:**
- Database-first applications requiring CRUD operations
- Need automatic node generation from models (@db.model decorator)
- Bulk data processing (10k+ operations/sec)
- Multi-tenant SaaS applications
- Enterprise data management with write protection and audit trails
- PostgreSQL-based applications (full feature support)
- SQLite applications

**When NOT to Choose DataFlow:**
- Simple single-workflow tasks (use Core SDK directly)
- Multi-channel platform needs (use Nexus)
- No database operations required (use Core SDK)
- Need MySQL support (not available in alpha)
- Simple read-only database access (Core SDK nodes sufficient)

## Essential Patterns

> **Note**: For basic patterns (setup, CRUD, queries), see the [DataFlow Skills](../../skills/02-dataflow/) - 24 Skills covering common operations.

This section focuses on **enterprise-level patterns** and **production complexity**.

## 🚨 Error Handling with ErrorEnhancer (NEW in v0.4.7+)

DataFlow includes **ErrorEnhancer** to transform Python exceptions into rich, actionable error messages with solutions.

**Key Features**:
- **DF-XXX Error Codes**: Standardized error codes for quick lookup
- **Context-Aware Messages**: What, why, and how to fix
- **Multiple Solutions**: 3-5 possible fixes with code examples
- **Performance Modes**: FULL (development), MINIMAL (staging), DISABLED (production)
- **Pattern Caching**: 90%+ cache hit rate for repeated errors

**Example Enhanced Error**:
```python
# Code that triggers error
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice"  # Missing 'id' field
})

# Enhanced error output
DF-101: Missing Required Parameter

Error: Field 'id' is required for CREATE operations

Context:
- Node: UserCreateNode
- Operation: CREATE
- Model: User
- Missing Parameter: id

Causes:
1. Missing 'id' field in data dictionary
2. Typo in field name (e.g., 'user_id' instead of 'id')
3. Data structure doesn't match model schema

Solutions:
1. Add 'id' field to your data:
   data = {"id": "user-123", "name": "Alice"}

2. Check model definition for required fields
3. Use Inspector to validate workflow structure

Documentation: https://docs.kailash.dev/dataflow/errors/DF-101
```

**Performance Modes**:
```python
from dataflow import DataFlow

# Development: Full error enhancement (default)
db = DataFlow(url, error_enhancement_mode="FULL")

# Staging: Minimal overhead
db = DataFlow(url, error_enhancement_mode="MINIMAL")

# Production: Disabled for performance
db = DataFlow(url, error_enhancement_mode="DISABLED")
```

**Common Error Codes**:
- **DF-101**: Missing Required Parameter → Add missing field to data dictionary
- **DF-201**: Connection Type Mismatch → Check parameter types in connections
- **DF-301**: Migration Failed → Review schema changes and constraints
- **DF-401**: Database URL Invalid → Verify connection string format
- **DF-501**: Sync Method in Async Context → Use `create_tables_async()` instead of `create_tables()`
- **DF-601**: Primary Key Missing → Ensure model has 'id' field
- **DF-701**: Node Not Found → Check node name spelling and case
- **DF-801**: Workflow Build Failed → Validate all connections before .build()

**File Reference**: `src/dataflow/core/error_enhancer.py:1-756` (60+ methods)

## 🔄 DF-501: Async Context Lifecycle Methods (v0.10.7+)

### The Problem

When using DataFlow in async contexts (FastAPI lifespan, pytest async fixtures, async main functions), sync methods like `create_tables()` and `_ensure_migration_tables()` would fail with event loop conflicts:

```
RuntimeError: Cannot run sync method in running event loop
RuntimeError: Event loop is closed
```

### New Async Methods (v0.10.7+)

DataFlow v0.10.7 introduces proper async lifecycle methods that work correctly in async contexts:

| Sync Method | Async Alternative | Usage |
|-------------|-------------------|-------|
| `create_tables()` | `create_tables_async()` | Table creation in async contexts |
| `close()` | `close_async()` | Cleanup in async contexts |
| `_ensure_migration_tables()` | `_ensure_migration_tables_async()` | Internal migration tables |

### When to Use Each

**Use Async Methods When:**
- ✅ Inside FastAPI lifespan events (`@asynccontextmanager async def lifespan()`)
- ✅ Inside pytest async fixtures (`@pytest.fixture async def db()`)
- ✅ Inside async main functions (`async def main()`)
- ✅ Any code running in an async context with `asyncio.get_running_loop()`

**Use Sync Methods When:**
- ✅ CLI scripts and management commands
- ✅ Sync pytest tests (non-async)
- ✅ Any code NOT running in an async context

### FastAPI Integration Pattern (Recommended)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dataflow import DataFlow

db = DataFlow("postgresql://localhost/mydb")

@db.model
class User:
    id: str
    name: str
    email: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Use async version
    await db.create_tables_async()
    yield
    # Shutdown: Use async version
    await db.close_async()

app = FastAPI(lifespan=lifespan)

@app.get("/users/{user_id}")
async def get_user(user_id: str):
    # Normal async operations work
    pass
```

### Pytest Async Fixture Pattern (Recommended)

```python
import pytest
from dataflow import DataFlow

@pytest.fixture
async def db():
    """Async fixture with proper cleanup."""
    db = DataFlow("postgresql://...", test_mode=True)

    @db.model
    class User:
        id: str
        name: str

    # Use async version in async context
    await db.create_tables_async()

    yield db

    # Use async cleanup
    await db.close_async()

@pytest.mark.asyncio
async def test_user_creation(db):
    # Test with async db fixture
    pass
```

### Sync Context Detection

DataFlow sync methods now detect when they're called from an async context and raise a clear error:

```python
# In async context (e.g., async def main())
try:
    db.create_tables()  # Raises RuntimeError
except RuntimeError as e:
    print(e)
    # Output: Cannot use create_tables() in async context - use create_tables_async() instead.
    # See DF-501 for details.
```

### Error Message Examples

**DF-501 for create_tables():**
```
RuntimeError: Cannot use create_tables() in async context - use create_tables_async() instead.
See DF-501 for details.
```

**DF-501 for _ensure_migration_tables():**
```
RuntimeError: Cannot use _ensure_migration_tables() in async context - use _ensure_migration_tables_async() instead.
See DF-501 for details.
```

### Migration from Sync to Async

**Before (DF-501 Error):**
```python
# ❌ WRONG - Causes DF-501 in async context
@asynccontextmanager
async def lifespan(app: FastAPI):
    db = DataFlow("postgresql://...")

    @db.model
    class User:
        id: str
        name: str

    db.create_tables()  # ❌ DF-501 ERROR!
    yield
    db.close()  # ❌ May fail silently
```

**After (v0.10.7+ Fix):**
```python
# ✅ CORRECT - Use async methods in async context
@asynccontextmanager
async def lifespan(app: FastAPI):
    db = DataFlow("postgresql://...")

    @db.model
    class User:
        id: str
        name: str

    await db.create_tables_async()  # ✅ Works correctly
    yield
    await db.close_async()  # ✅ Proper cleanup
```

### close_async() Method Details

The `close_async()` method properly cleans up all DataFlow resources in async contexts:

```python
async def close_async(self):
    """Close database connections and clean up resources (async version)."""
    # Closes connection pool manager
    # Closes memory connections (SQLite)
    # Clears internal state
```

**Safe to Call Multiple Times:**
```python
await db.close_async()  # First call - cleans up
await db.close_async()  # Second call - no-op, safe
await db.close_async()  # Third call - no-op, safe
```

### Context Manager Support

DataFlow also supports sync context managers, which call `close()` automatically:

```python
# Sync context manager (for CLI/scripts)
with DataFlow("sqlite:///dev.db") as db:
    @db.model
    class User:
        id: str
        name: str

    db.create_tables()  # OK in sync context
    # Automatic cleanup when exiting context

# For async contexts, use the lifespan pattern above
```

### File References

- **Implementation**: `src/dataflow/core/engine.py:7180-7230` (close_async, close methods)
- **Async Table Creation**: `src/dataflow/core/engine.py:4100-4200` (create_tables_async)
- **Error Messages**: `src/dataflow/platform/errors.py:2757-2783` (DF-501 error codes)
- **Tests**: `tests/integration/test_dataflow_async_lifecycle.py` (16 comprehensive tests)

## 🚀 ExpressDataFlow - High-Performance CRUD (NEW in v0.10.6+)

Direct node invocation bypassing workflow overhead for simple CRUD operations.

**Performance**: ~23x faster than workflow-based operations

**Access**: `db.express.<operation>()` after `await db.initialize()`

**Operations**:
- **CRUD**: create, read, update, delete, list, count
- **Bulk**: bulk_create, bulk_update, bulk_delete, bulk_upsert

**Basic Usage**:
```python
from dataflow import DataFlow

db = DataFlow("postgresql://user:password@localhost/mydb")

@db.model
class User:
    id: str
    name: str
    email: str

await db.initialize()

# Direct node invocation - ~23x faster than workflows
user = await db.express.create("User", {"id": "user-001", "name": "Alice", "email": "alice@example.com"})
user = await db.express.read("User", "user-001")
updated = await db.express.update("User", {"id": "user-001"}, {"name": "Alice Updated"})
success = await db.express.delete("User", "user-001")
users = await db.express.list("User", filter={"active": True})
total = await db.express.count("User")
```

**When to Use**:
- Simple CRUD operations without workflow complexity
- High-throughput applications needing maximum performance
- Single-node operations

**When NOT to Use** (Use Traditional Workflows):
- Multi-node operations with data flow between nodes
- Conditional execution or branching logic
- Transaction management across operations

**Skill Reference**: See `dataflow-express` skill for complete API

## 🔍 Inspector - Workflow Introspection (NEW in v0.4.7+)

DataFlow includes **Inspector** for debugging and analyzing workflow structure before execution.

**Key Features**:
- **Connection Analysis**: List connections, find broken connections, trace chains
- **Parameter Tracing**: Trace parameters back to source, track transformations
- **Workflow Validation**: Validate connections and detect circular dependencies
- **Visual Inspection**: Rich formatted output for debugging
- **30+ Methods**: Comprehensive introspection API

**Basic Usage**:
```python
from dataflow.platform.inspector import Inspector
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"id": "user-123", "name": "Alice"})
workflow.add_node("UserReadNode", "read", {"id": "user-123"})
workflow.add_connection("create", "id", "read", "id")

# Inspect workflow structure
inspector = Inspector(workflow)

# List all connections
connections = inspector.connections()
print(f"Found {len(connections)} connections")

# Trace parameter back to source
trace = inspector.trace_parameter("read", "id")
print(trace.show())  # Shows: create.id → read.id

# Validate connections
validation = inspector.validate_connections()
if not validation["is_valid"]:
    print(f"Found {len(validation['errors'])} connection errors")
```

**Common Debugging Scenarios**:

**Scenario 1: Missing Data Parameter**
```python
# Problem: Parameter 'id' is None in node 'read'
inspector = Inspector(workflow)
trace = inspector.trace_parameter("read", "id")

# Inspector shows:
# create.id (source) → read.id (destination)
# Value: "user-123" (confirmed data flow)
# If value is None, Inspector shows where connection breaks
```

**Scenario 2: Broken Connection**
```python
# Problem: Connection not working as expected
inspector = Inspector(workflow)
broken = inspector.find_broken_connections()

# Shows all connections with type mismatches or missing sources
for conn in broken:
    print(f"Broken: {conn['source']} → {conn['target']}")
    print(f"Reason: {conn['error']}")
```

**Scenario 3: Circular Dependency**
```python
# Problem: Workflow hangs due to circular dependency
inspector = Inspector(workflow)
cycles = inspector.detect_cycles()

if cycles:
    print(f"Found {len(cycles)} circular dependencies:")
    for cycle in cycles:
        print(f"  Cycle: {' → '.join(cycle)}")
```

**File Reference**: `src/dataflow/platform/inspector.py:1-3540` (30+ methods)

**Quick Reference Guide**: `sdk-users/apps/dataflow/guides/inspector-debugging-guide.md` (12+ scenarios)

## 🔍 Debug Agent - Intelligent Error Analysis (NEW in v0.8.0+)

The **Debug Agent** is an intelligent error analysis system that automatically diagnoses DataFlow errors and provides ranked, actionable solutions with code examples.

**What It Does** (5-stage pipeline):
1. **Captures** error details with full stack traces
2. **Categorizes** errors into 5 categories using 50+ patterns
3. **Analyzes** workflow context using Inspector
4. **Suggests** ranked solutions with code examples (60+ solutions)
5. **Formats** results for terminal or JSON output

**Key Features**:
- **50+ Error Patterns**: Covers PARAMETER, CONNECTION, MIGRATION, RUNTIME, CONFIGURATION errors
- **60+ Solution Templates**: Ranked by relevance with code examples
- **Inspector Integration**: Context-aware analysis using workflow introspection
- **Multiple Output Formats**: CLI (ANSI colors), JSON (machine-readable), Dictionary (programmatic)
- **Performance**: 5-50ms execution time, 92%+ confidence for known patterns
- **Production-Ready**: Logging, batch analysis, custom patterns

**Quick Start**:
```python
from dataflow import DataFlow
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector

# Initialize DataFlow
db = DataFlow("postgresql://localhost/mydb")

@db.model
class User:
    id: str
    name: str

# Initialize Debug Agent (once - singleton pattern)
kb = KnowledgeBase(
    "src/dataflow/debug/patterns.yaml",
    "src/dataflow/debug/solutions.yaml"
)
inspector = Inspector(db)
debug_agent = DebugAgent(kb, inspector)

# Execute and debug
runtime = LocalRuntime()
try:
    results, _ = runtime.execute(workflow.build())
except Exception as e:
    # Debug error automatically
    report = debug_agent.debug(e, max_solutions=5, min_relevance=0.3)

    # Display rich CLI output
    print(report.to_cli_format())

    # Or access programmatically
    print(f"Category: {report.error_category.category}")
    print(f"Root Cause: {report.analysis_result.root_cause}")
    print(f"Solutions: {len(report.suggested_solutions)}")
```

**Error Categories**:
- **PARAMETER** (15 patterns): Missing `id`, type mismatch, invalid values, reserved fields
- **CONNECTION** (10 patterns): Missing source node, circular dependency, type incompatibility
- **MIGRATION** (8 patterns): Schema conflicts, missing table, constraint violations
- **RUNTIME** (10 patterns): Transaction timeout, event loop collision, node execution failed
- **CONFIGURATION** (7 patterns): Invalid database URL, missing environment variables, auth failed

**Common Scenario Example** (Missing Required 'id' Parameter):
```python
# Error
ValueError: Missing required parameter 'id' in CreateNode

# Debug Output
Category: PARAMETER (Confidence: 95%)
Root Cause: Node 'create' is missing required parameter 'id' (primary key)

[1] Add Missing 'id' Parameter (QUICK_FIX) - 95%
    workflow.add_node("UserCreateNode", "create", {
        "id": "user-123",  # Add missing parameter
        "name": "Alice"
    })

[2] Use UUID for Automatic ID Generation (BEST_PRACTICE) - 85%
    import uuid
    workflow.add_node("UserCreateNode", "create", {
        "id": str(uuid.uuid4()),  # Auto-generate UUID
        "name": "Alice"
    })
```

**Production Integration Patterns**:
```python
# Pattern 1: Global Error Handler
class DataFlowWithDebugAgent:
    def __init__(self, database_url: str):
        self.db = DataFlow(database_url)
        kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
        inspector = Inspector(self.db)
        self.debug_agent = DebugAgent(kb, inspector)

    def execute(self, workflow: WorkflowBuilder):
        runtime = LocalRuntime()
        try:
            results, _ = runtime.execute(workflow.build())
            return results
        except Exception as e:
            report = self.debug_agent.debug(e)
            print(report.to_cli_format())
            raise

# Pattern 2: Production Logging
import logging
logger = logging.getLogger(__name__)

try:
    runtime.execute(workflow.build())
except Exception as e:
    report = debug_agent.debug(e)
    logger.error("Workflow failed", extra={
        "category": report.error_category.category,
        "confidence": report.error_category.confidence,
        "root_cause": report.analysis_result.root_cause,
        "solutions_count": len(report.suggested_solutions),
        "report_json": report.to_json()
    })

# Pattern 3: Batch Error Analysis
from pathlib import Path
import json

def analyze_error_logs(log_file: Path, output_dir: Path):
    with open(log_file, "r") as f:
        error_lines = [line.strip() for line in f if "ERROR" in line]

    reports = []
    for i, error_message in enumerate(error_lines):
        report = agent.debug_from_string(error_message)
        reports.append(report.to_dict())

        output_file = output_dir / f"report_{i:03d}.json"
        with open(output_file, "w") as f:
            f.write(report.to_json())

    summary = {
        "total_errors": len(reports),
        "category_breakdown": {...},
        "average_execution_time_ms": ...
    }

    with open(output_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)
```

**Configuration Options**:
```python
# Tuning solution count
report = debug_agent.debug(exception, max_solutions=5)  # Default: 5
report = debug_agent.debug(exception, max_solutions=3)  # Faster: 20-30% speedup

# Tuning relevance threshold
report = debug_agent.debug(exception, min_relevance=0.3)  # Default: 30%
report = debug_agent.debug(exception, min_relevance=0.7)  # Faster: 40-50% speedup

# Disabling Inspector (faster but less context)
agent = DebugAgent(kb, inspector=None)  # 30-40% faster
```

**Extending Debug Agent** (Custom Patterns):
```yaml
# patterns.yaml
CUSTOM_001:
  name: "Your Custom Error Pattern"
  category: PARAMETER
  regex: ".*your custom regex.*"
  semantic_features:
    - error_type: [CustomError]
  severity: high
  related_solutions: [CUSTOM_SOL_001]

# solutions.yaml
CUSTOM_SOL_001:
  id: CUSTOM_SOL_001
  title: "Your Custom Solution"
  category: QUICK_FIX
  description: "Description of solution"
  code_example: |
    # Your code example
    workflow.add_node("Node", "id", {...})
  difficulty: easy
  estimated_time: 5
```

**Critical Patterns**:
1. **Initialize Once** (singleton): Create DebugAgent once and reuse (20-50ms overhead if initialized every time)
2. **Store Reports**: Save JSON reports for later analysis and metrics tracking
3. **Custom Formatters**: Format reports for Slack, email, or other notification systems

**File References**:
- Core: `src/dataflow/debug/debug_agent.py:1-487` (5-stage pipeline)
- Knowledge Base: `src/dataflow/debug/knowledge_base.py:1-312` (pattern/solution management)
- Patterns: `src/dataflow/debug/patterns.yaml` (50+ patterns)
- Solutions: `src/dataflow/debug/solutions.yaml` (60+ solutions)

**Comprehensive Documentation**:
- **User Guide**: `docs/guides/debug-agent-user-guide.md` (2513 lines, 15 scenarios)
- **Developer Guide**: `docs/guides/debug-agent-developer-guide.md` (2003 lines, extension guide)
- **Examples**: `examples/debug_agent/` (5 working examples)
- **E2E Tests**: `tests/integration/test_debug_agent_e2e.py` (18 tests, 100% passing)

**Version Requirements**: DataFlow v0.8.0+, Python 3.10+

---

## 🔒 Strict Mode Validation System (NEW in v0.8.0+, Week 9)

**Location**: `apps/kailash-dataflow/src/dataflow/validation/`

DataFlow v0.8.0+ introduces **Strict Mode** - an opt-in validation system that provides comprehensive parameter, connection, and model validation with fail-fast and verbose modes.

### What is Strict Mode?

Strict Mode is a 4-layer validation system that catches errors **before** workflow execution:

**Layer 1**: Model schema validation (field types, constraints, relationships)
**Layer 2**: Parameter validation (types, values, required fields)
**Layer 3**: Connection validation (type compatibility, parameter contracts)
**Layer 4**: Workflow validation (structure, cycles, dependencies)

**Key Features**:
- **3-tier priority system**: Per-model > Global > Environment variable
- **Fail-fast mode**: Stop at first validation error (default)
- **Verbose mode**: Collect all validation errors before failing
- **Zero runtime overhead**: Validation only at workflow build time
- **Backward compatible**: Opt-in via configuration or decorator

### Configuration Priority (Highest to Lowest)

```python
from dataflow import DataFlow

# Priority 1: Environment variable (lowest)
# export DATAFLOW_STRICT_MODE=true
db = DataFlow("postgresql://...")

# Priority 2: Global DataFlow configuration (medium)
db = DataFlow("postgresql://...", strict_mode=True)

# Priority 3: Per-model configuration (highest)
@db.model
class User:
    id: str
    email: str
    name: str

    __dataflow__ = {
        'strict_mode': True  # Overrides global and env var
    }
```

### Strict Mode Options

```python
from dataflow.validation.strict_mode import StrictModeConfig

# Enable strict mode with default settings
db = DataFlow("postgresql://...", strict_mode=True)

# Custom strict mode configuration
db = DataFlow(
    "postgresql://...",
    strict_mode=StrictModeConfig(
        enabled=True,
        fail_fast=False,  # Collect all errors before failing
        verbose=True,     # Detailed error messages
        validate_models=True,
        validate_parameters=True,
        validate_connections=True,
        validate_workflows=True
    )
)

# Disable specific validation layers
db = DataFlow(
    "postgresql://...",
    strict_mode=StrictModeConfig(
        enabled=True,
        validate_parameters=True,  # Keep parameter validation
        validate_connections=False,  # Skip connection validation
        validate_workflows=False    # Skip workflow validation
    )
)
```

**File Reference**: `src/dataflow/validation/strict_mode.py:1-156` (StrictModeConfig class)

### Layer 1: Model Validation

**Location**: `src/dataflow/validation/model_validator.py:1-248`

Validates DataFlow model schemas before node generation.

**Validation Checks**:
- Primary key 'id' field presence and type
- Field type annotations (str, int, float, bool, List, Dict)
- Reserved field names (created_at, updated_at)
- List field type constraints (List[str], List[int], List[float] only)
- PostgreSQL native array validation
- Field naming conventions

**Usage**:
```python
from dataflow.validation.model_validator import ModelValidator
from dataflow import DataFlow

db = DataFlow("postgresql://...", strict_mode=True)

# Invalid model - will raise validation error
@db.model
class BadUser:
    user_id: str  # ❌ Missing 'id' field
    created_at: str  # ❌ Reserved field
    tags: List[dict]  # ❌ Unsupported List element type

# Validation error raised BEFORE node generation:
# ModelValidationError: Model 'BadUser' validation failed:
#   - Missing required primary key field 'id'
#   - Reserved field 'created_at' cannot be manually defined
#   - Unsupported List element type: dict (use List[str], List[int], or List[float])

# Valid model
@db.model
class GoodUser:
    id: str  # ✅ Required primary key
    name: str
    email: str
    tags: List[str]  # ✅ Supported List type
```

**ModelValidator API**:
```python
from dataflow.validation.model_validator import ModelValidator

validator = ModelValidator()

# Validate model class
errors = validator.validate_model(User, model_name="User")
# Returns: List[str] - validation error messages

# Validate primary key
errors = validator.validate_primary_key(User, model_name="User")
# Checks: 'id' field exists and is str type

# Validate field types
errors = validator.validate_field_types(User, model_name="User")
# Checks: All fields have valid type annotations

# Validate reserved fields
errors = validator.validate_reserved_fields(User, model_name="User")
# Checks: created_at, updated_at not manually defined
```

**Error Messages**:
```
ModelValidationError: Model 'User' validation failed:
  - Missing required primary key field 'id'
  - Primary key field 'id' must be of type str, got int
  - Field 'created_at' is reserved and auto-managed by DataFlow
  - Field 'tags' has unsupported List element type: dict
  - Field 'metadata' requires type annotation
```

### Layer 2: Parameter Validation

**Location**: `src/dataflow/validation/parameter_validator.py:1-312`

Validates node parameters before workflow execution.

**Validation Checks**:
- Required parameter presence
- Parameter type matching (str, int, float, bool, list, dict)
- Value constraints (range, format, length)
- Special node parameter structures:
  - CreateNode: flat field structure
  - UpdateNode: filter + fields structure
  - ListNode: filters, limit, offset
  - BulkCreateNode: data list with records

**Usage**:
```python
from dataflow.validation.parameter_validator import ParameterValidator
from dataflow import DataFlow

db = DataFlow("postgresql://...", strict_mode=True)

@db.model
class User:
    id: str
    email: str
    name: str

# Invalid CreateNode - missing 'id'
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice"  # ❌ Missing required 'id' field
})

# Validation error raised at workflow.build():
# ParameterValidationError: Node 'create' parameter validation failed:
#   - Missing required parameter 'id' for CREATE operation
#   - Required parameter type: str

# Valid CreateNode
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",  # ✅ Required parameter
    "name": "Alice",
    "email": "alice@example.com"
})

# Invalid UpdateNode - wrong structure
workflow.add_node("UserUpdateNode", "update", {
    "name": "Alice Updated"  # ❌ Missing 'filter' and 'fields' structure
})

# Validation error:
# ParameterValidationError: Node 'update' parameter validation failed:
#   - UPDATE operation requires 'filter' field
#   - UPDATE operation requires 'fields' field

# Valid UpdateNode
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},  # ✅ Which records to update
    "fields": {"name": "Alice Updated"}  # ✅ What to change
})
```

**ParameterValidator API**:
```python
from dataflow.validation.parameter_validator import ParameterValidator

validator = ParameterValidator()

# Validate node parameters
errors = validator.validate_parameters(
    node_id="create",
    node_type="UserCreateNode",
    parameters={"name": "Alice"},
    model_schema=user_schema
)
# Returns: List[str] - validation error messages

# Validate parameter types
errors = validator.validate_parameter_types(
    parameters={"id": "user-123", "age": "25"},
    expected_types={"id": str, "age": int}
)
# Checks: Parameter types match expected types

# Validate required parameters
errors = validator.validate_required_parameters(
    parameters={"name": "Alice"},
    required_params=["id", "name", "email"]
)
# Checks: All required parameters are present
```

**Error Messages**:
```
ParameterValidationError: Node 'create' parameter validation failed:
  - Missing required parameter 'id' for CREATE operation
  - Parameter 'age' type mismatch: expected int, got str
  - Parameter 'email' invalid format: 'notanemail'
  - UPDATE operation requires 'filter' field
  - UPDATE operation requires 'fields' field
```

### Layer 3: Connection Validation

**Location**: `src/dataflow/validation/connection_validator.py:1-285`

Validates workflow connections for type compatibility and parameter contracts.

**Validation Checks**:
- Source node existence
- Target node existence
- Parameter type compatibility (str → str, int → int, dict → dict)
- Connection contract validation (source output matches target input)
- Circular dependency detection
- Self-connection prevention

**Usage**:
```python
from dataflow.validation.connection_validator import ConnectionValidator
from dataflow import DataFlow

db = DataFlow("postgresql://...", strict_mode=True)

@db.model
class User:
    id: str
    name: str

# Invalid connection - source node doesn't exist
workflow.add_node("UserReadNode", "read", {"id": "user-123"})
workflow.add_connection("nonexistent_node", "id", "read", "id")

# Validation error at workflow.build():
# ConnectionValidationError: Connection validation failed:
#   - Source node 'nonexistent_node' not found in workflow
#   - Add source node before creating connection

# Valid connection
workflow.add_node("UserCreateNode", "create", {"id": "user-123", "name": "Alice"})
workflow.add_node("UserReadNode", "read", {})
workflow.add_connection("create", "id", "read", "id")  # ✅ Valid connection

# Invalid connection - type mismatch
workflow.add_node("UserCountNode", "count", {})  # Returns int count
workflow.add_connection("count", "count", "read", "id")  # ❌ int → str mismatch

# Validation error:
# ConnectionValidationError: Connection validation failed:
#   - Type mismatch: source outputs int, target expects str
#   - Connection: count.count → read.id
```

**ConnectionValidator API**:
```python
from dataflow.validation.connection_validator import ConnectionValidator

validator = ConnectionValidator()

# Validate connection
errors = validator.validate_connection(
    source_node="create",
    source_param="id",
    target_node="read",
    target_param="id",
    workflow=workflow
)
# Returns: List[str] - validation error messages

# Validate connection type compatibility
errors = validator.validate_connection_types(
    source_type=str,
    target_type=int,
    connection_id="create.id → read.id"
)
# Checks: Source and target types are compatible

# Detect circular dependencies
errors = validator.detect_circular_dependencies(
    workflow=workflow
)
# Checks: No circular dependencies in workflow graph
```

**Error Messages**:
```
ConnectionValidationError: Connection validation failed:
  - Source node 'create' not found in workflow
  - Target node 'read' not found in workflow
  - Type mismatch: source outputs int, target expects str
  - Circular dependency detected: create → read → create
  - Self-connection not allowed: node 'create' connects to itself
```

### Layer 4: Workflow Validation

**Location**: `src/dataflow/validation/validators.py:1-198`

Orchestrates all validation layers and provides workflow-level validation.

**Validation Checks**:
- Workflow structure integrity
- Node registration completeness
- Connection graph validity
- Dependency resolution
- Cyclic workflow validation

**Usage**:
```python
from dataflow.validation.validators import WorkflowValidator
from dataflow import DataFlow

db = DataFlow("postgresql://...", strict_mode=True)

@db.model
class User:
    id: str
    name: str

# Build workflow
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"id": "user-123", "name": "Alice"})
workflow.add_node("UserReadNode", "read", {"id": "user-123"})
workflow.add_connection("create", "id", "read", "id")

# Validate workflow before execution
validator = WorkflowValidator(db)
errors = validator.validate_workflow(workflow)

if errors:
    print(f"Workflow validation failed:")
    for error in errors:
        print(f"  - {error}")
else:
    # Safe to execute
    results, _ = runtime.execute(workflow.build())
```

**WorkflowValidator API**:
```python
from dataflow.validation.validators import WorkflowValidator

validator = WorkflowValidator(db)

# Validate complete workflow
errors = validator.validate_workflow(workflow)
# Returns: List[str] - all validation errors

# Validate workflow structure
errors = validator.validate_structure(workflow)
# Checks: Workflow has valid structure (nodes, connections)

# Validate workflow dependencies
errors = validator.validate_dependencies(workflow)
# Checks: All dependencies can be resolved

# Validate cyclic workflows
errors = validator.validate_cycles(workflow)
# Checks: Cyclic workflows have valid convergence conditions
```

**Error Messages**:
```
WorkflowValidationError: Workflow validation failed:
  - Workflow structure invalid: no nodes defined
  - Unresolved dependency: node 'read' depends on non-existent node 'create'
  - Cyclic workflow missing convergence condition
  - Multiple validation errors found (see details above)
```

### Fail-Fast vs Verbose Mode

```python
# Fail-Fast Mode (default) - stops at first error
db = DataFlow(
    "postgresql://...",
    strict_mode=StrictModeConfig(
        enabled=True,
        fail_fast=True  # Stop at first validation error
    )
)

# Error output (single error):
# ModelValidationError: Model 'User' validation failed:
#   - Missing required primary key field 'id'

# Verbose Mode - collects all errors
db = DataFlow(
    "postgresql://...",
    strict_mode=StrictModeConfig(
        enabled=True,
        fail_fast=False,  # Collect all errors
        verbose=True      # Detailed error messages
    )
)

# Error output (all errors):
# ModelValidationError: Model 'User' validation failed:
#   - Missing required primary key field 'id'
#   - Field 'created_at' is reserved and auto-managed
#   - Field 'tags' has unsupported List element type: dict
#   - Field 'metadata' requires type annotation
```

### Integration Tests

**Location**: `apps/kailash-dataflow/tests/integration/`

Comprehensive integration tests verify strict mode behavior across all validation layers.

**Test Coverage**:
- Model validation integration: `test_model_validation_integration.py:1-187`
- Parameter validation integration: `test_parameter_validation_integration.py:1-215`
- Connection validation integration: `test_connection_validation_integration.py:1-198`
- End-to-end validation workflows: All tests passing (100% coverage)

**Running Integration Tests**:
```bash
# Run all strict mode integration tests
pytest apps/kailash-dataflow/tests/integration/test_*_validation_integration.py -v

# Run specific validation layer tests
pytest apps/kailash-dataflow/tests/integration/test_model_validation_integration.py -v
pytest apps/kailash-dataflow/tests/integration/test_parameter_validation_integration.py -v
pytest apps/kailash-dataflow/tests/integration/test_connection_validation_integration.py -v
```

### Architecture Decision Record

**Location**: `apps/kailash-dataflow/docs/architecture/ADR-003-STRICT-MODE.md`

Comprehensive architectural documentation for Strict Mode system design.

**Sections**:
- Design rationale and alternatives considered
- 3-tier priority system justification
- Validation layer architecture
- Performance considerations
- Integration with existing ErrorEnhancer
- Backward compatibility guarantees

### User Guide

**Location**: `apps/kailash-dataflow/docs/guides/strict-mode-validation.md`

Complete user guide with configuration, usage patterns, and examples.

**Sections**:
- Quick start guide
- Configuration priority system
- Validation layer details
- Common validation scenarios
- Troubleshooting validation errors
- Best practices for production use

### Production Best Practices

**1. Enable Strict Mode in Development** (catch errors early):
```python
# Development
db = DataFlow("postgresql://...", strict_mode=True)
```

**2. Disable Strict Mode in Production** (zero overhead):
```python
# Production
db = DataFlow("postgresql://...", strict_mode=False)
```

**3. Use Verbose Mode for Debugging** (collect all errors):
```python
# Debugging
db = DataFlow(
    "postgresql://...",
    strict_mode=StrictModeConfig(
        enabled=True,
        fail_fast=False,  # Collect all errors
        verbose=True      # Detailed messages
    )
)
```

**4. Per-Model Strict Mode** (selective validation):
```python
# Enable strict mode only for critical models
@db.model
class CriticalUser:
    id: str
    email: str

    __dataflow__ = {'strict_mode': True}

# Disable for less critical models
@db.model
class LogEntry:
    id: str
    message: str

    __dataflow__ = {'strict_mode': False}
```

### Performance Impact

**Validation Overhead**:
- Model validation: <1ms per model (one-time at registration)
- Parameter validation: <1ms per node (at workflow build)
- Connection validation: <1ms per connection (at workflow build)
- Workflow validation: <5ms for 100-node workflows

**Production Recommendation**: Disable in production to eliminate overhead.

**Development Recommendation**: Enable in development to catch errors before execution.

### File References (Complete)

**Core Implementation**:
- `src/dataflow/validation/strict_mode.py:1-156` - StrictModeConfig class
- `src/dataflow/validation/model_validator.py:1-248` - Layer 1 validation
- `src/dataflow/validation/parameter_validator.py:1-312` - Layer 2 validation
- `src/dataflow/validation/connection_validator.py:1-285` - Layer 3 validation
- `src/dataflow/validation/validators.py:1-198` - Layer 4 orchestration

**Testing**:
- `tests/unit/test_model_validator.py:1-156` - Model validation unit tests
- `tests/unit/test_parameter_validation.py:1-187` - Parameter validation unit tests
- `tests/unit/test_connection_validation.py:1-165` - Connection validation unit tests
- `tests/integration/test_model_validation_integration.py:1-187` - Model integration tests
- `tests/integration/test_parameter_validation_integration.py:1-215` - Parameter integration tests
- `tests/integration/test_connection_validation_integration.py:1-198` - Connection integration tests

**Documentation**:
- `docs/architecture/ADR-003-STRICT-MODE.md` - Architecture decision record
- `docs/guides/strict-mode-validation.md` - User guide

---

## 🐛 Debug Agent - 5-Stage Pipeline Deep Dive (NEW in v0.8.0+, Week 10)

**Location**: `apps/kailash-dataflow/src/dataflow/debug/`

The Debug Agent implements a **5-stage error analysis pipeline** for intelligent error diagnosis with 50+ patterns, 60+ solutions, and 92%+ confidence.

### Architecture Overview

The Debug Agent processes errors through 5 sequential stages:

**Stage 1**: Error Capture → Extract stacktrace, message, context
**Stage 2**: Error Categorization → Match against 50+ patterns
**Stage 3**: Context Analysis → Use Inspector for workflow context
**Stage 4**: Solution Generation → Rank 60+ solutions by relevance
**Stage 5**: Result Formatting → Output CLI, JSON, or dictionary

Each stage builds upon the previous stage's output, creating a pipeline that progressively enriches error information.

### Stage 1: Error Capture

**Location**: `src/dataflow/debug/error_capture.py:1-312`

Captures comprehensive error information including stacktrace, context, and metadata.

**CapturedError Class**:
```python
from dataflow.debug.error_capture import ErrorCapture, CapturedError

# Capture exception
capture = ErrorCapture()
captured_error = capture.capture(exception)

# CapturedError attributes:
captured_error.exception_type  # e.g., "ValueError"
captured_error.message         # Error message string
captured_error.stacktrace      # List of StackFrame objects
captured_error.context         # Dict with node_id, parameters, etc.
captured_error.timestamp       # When error was captured
```

**Stacktrace Analysis**:
```python
# Access stacktrace frames
for frame in captured_error.stacktrace:
    print(f"File: {frame.filename}")
    print(f"Line: {frame.line_number}")
    print(f"Function: {frame.function_name}")
    print(f"Code: {frame.code_context}")
```

**Context Extraction**:
```python
# Error context includes:
context = captured_error.context
context["node_id"]          # Which node failed
context["parameters"]       # Node parameters
context["error_location"]   # File:line where error occurred
context["workflow_info"]    # Workflow metadata
```

**ErrorCapture API**:
```python
from dataflow.debug.error_capture import ErrorCapture

capture = ErrorCapture()

# Capture exception
captured = capture.capture(exception)
# Returns: CapturedError with full context

# Capture from string (for log parsing)
captured = capture.capture_from_string(
    error_message="ValueError: Missing required parameter 'id'"
)
# Returns: CapturedError with limited context

# Extract stacktrace
frames = capture.extract_stacktrace(exception)
# Returns: List[StackFrame]

# Extract context
context = capture.extract_context(exception)
# Returns: Dict with error context
```

**File Reference**: `src/dataflow/debug/error_capture.py:1-312` (ErrorCapture, CapturedError, StackFrame)

### Stage 2: Error Categorization

**Location**: `src/dataflow/debug/error_categorizer.py:1-426`

Matches captured errors against 50+ patterns across 5 categories using regex and semantic features.

**ErrorCategory Class**:
```python
from dataflow.debug.error_categorizer import ErrorCategorizer, ErrorCategory

categorizer = ErrorCategorizer(knowledge_base)
category = categorizer.categorize(captured_error)

# ErrorCategory attributes:
category.category       # "PARAMETER", "CONNECTION", "MIGRATION", etc.
category.pattern_id     # "PARAM_001", "CONN_002", etc.
category.confidence     # 0.0-1.0 confidence score
category.pattern_name   # Human-readable pattern name
category.features       # Matched semantic features
```

**Pattern Matching Algorithm**:
```python
# Two-phase matching:
# Phase 1: Regex matching on error message
# Phase 2: Semantic feature matching (error type, stacktrace location, context)

# Example: Missing 'id' parameter
# Regex: ".*[Mm]issing.*'id'.*"
# Semantic features:
#   - error_type: [KeyError, ValueError]
#   - stacktrace_location: [CreateNode, UpdateNode]
#   - missing_field: "id"
# Result: PARAM_001 with 95% confidence
```

**Category Distribution** (50 patterns):
- **PARAMETER** (15 patterns): Field validation, type mismatches, missing parameters
- **CONNECTION** (10 patterns): Node connections, circular dependencies, type compatibility
- **MIGRATION** (8 patterns): Schema changes, table/column issues, constraints
- **RUNTIME** (10 patterns): Execution errors, timeouts, resource exhaustion
- **CONFIGURATION** (7 patterns): Database URLs, environment variables, authentication

**ErrorCategorizer API**:
```python
from dataflow.debug.error_categorizer import ErrorCategorizer

categorizer = ErrorCategorizer(knowledge_base)

# Categorize error
category = categorizer.categorize(captured_error)
# Returns: ErrorCategory with matched pattern

# Calculate confidence score
confidence = categorizer.calculate_confidence(
    regex_match=True,
    semantic_match_score=0.85
)
# Returns: float (0.0-1.0)

# Match semantic features
match_score = categorizer.match_semantic_features(
    error_features={"error_type": "ValueError", "missing_field": "id"},
    pattern_features={"error_type": ["ValueError", "KeyError"], "missing_field": "id"}
)
# Returns: float (0.0-1.0)
```

**Pattern Structure** (from `patterns.yaml`):
```yaml
PARAM_001:
  name: "Missing Required Parameter 'id'"
  category: PARAMETER
  regex: ".*[Mm]issing.*'id'.*"
  semantic_features:
    - error_type: [KeyError, ValueError]
    - stacktrace_location: [CreateNode, UpdateNode]
    - missing_field: "id"
  severity: high
  related_solutions: [SOL_001, SOL_002]
```

**File Reference**: `src/dataflow/debug/error_categorizer.py:1-426` (ErrorCategorizer, ErrorCategory)

### Stage 3: Context Analysis

**Location**: `src/dataflow/debug/context_analyzer.py:1-768`

Extracts workflow context using Inspector API to provide detailed root cause analysis.

**AnalysisResult Class**:
```python
from dataflow.debug.context_analyzer import ContextAnalyzer, AnalysisResult

analyzer = ContextAnalyzer(inspector)
analysis = analyzer.analyze(captured_error, category)

# AnalysisResult attributes:
analysis.root_cause          # Human-readable root cause
analysis.affected_nodes      # List of affected node IDs
analysis.affected_connections  # List of affected connections
analysis.affected_models     # List of affected models
analysis.context_data        # Dict with detailed context
analysis.suggestions         # List of suggested fixes
```

**Category-Specific Analysis Methods**:
```python
# Each error category has specialized analysis:

# PARAMETER errors → _analyze_parameter_error()
# Extracts:
#   - Model schema from Inspector
#   - Missing parameter name
#   - Field type and constraints
#   - is_primary_key, is_nullable flags

# CONNECTION errors → _analyze_connection_error()
# Extracts:
#   - Missing source/target nodes
#   - Available nodes in workflow
#   - Similar node names (typo suggestions)
#   - Connection parameter details

# MIGRATION errors → _analyze_migration_error()
# Extracts:
#   - Table name from error message
#   - Existing tables list
#   - Similar table names (typo suggestions)

# CONFIGURATION errors → _analyze_configuration_error()
# Extracts:
#   - Configuration parameter that failed
#   - Expected format
#   - Environment variable references

# RUNTIME errors → _analyze_runtime_error()
# Extracts:
#   - Runtime issue type (timeout, deadlock, resource)
#   - Query information
#   - Resource usage indicators
```

**Inspector Integration**:
```python
# Context analyzer uses Inspector API for workflow introspection:

# Get model schema
model_info = inspector.model("User")
model_info.schema           # Field definitions
model_info.table_name       # Database table name

# Get workflow nodes
workflow = inspector._get_workflow()
available_nodes = list(workflow.nodes.keys())

# Find similar node names (typo suggestions)
similar_nodes = analyzer._find_similar_strings(
    target="user_create",
    candidates=available_nodes
)
# Returns: [("UserCreateNode", 0.85), ...]
```

**Context Data Structure**:
```python
# For PARAMETER errors:
context_data = {
    "node_id": "create",
    "node_type": "UserCreateNode",
    "model_name": "User",
    "model_schema": {...},        # Full schema from Inspector
    "missing_parameter": "id",
    "field_type": "str",
    "is_primary_key": True,
    "is_nullable": False,
    "provided_parameters": {"name": "Alice"},
    "table_name": "users"
}

# For CONNECTION errors:
context_data = {
    "source_node": "create",
    "target_node": "nonexistent_node",
    "missing_node": "nonexistent_node",
    "available_nodes": ["create", "read", "update"],
    "similar_nodes": [("read", 0.65)],  # Typo suggestions
    "connection_details": {"source_param": "id", "target_param": "id"}
}
```

**ContextAnalyzer API**:
```python
from dataflow.debug.context_analyzer import ContextAnalyzer

analyzer = ContextAnalyzer(inspector)

# Analyze error with workflow context
analysis = analyzer.analyze(captured_error, category)
# Returns: AnalysisResult with root cause and suggestions

# Find similar strings (typo suggestions)
similar = analyzer._find_similar_strings(
    target="usr_create",
    candidates=["user_create", "user_update"],
    threshold=0.5
)
# Returns: [('user_create', 0.85), ('user_update', 0.65)]

# Extract model name from node ID
model_name = analyzer._extract_model_name("UserCreateNode")
# Returns: "User"

# Extract parameter name from error message
param_name = analyzer._extract_parameter_name("Missing parameter 'id'")
# Returns: "id"
```

**File Reference**: `src/dataflow/debug/context_analyzer.py:1-768` (ContextAnalyzer, AnalysisResult)

### Stage 4: Solution Generation

**Location**: `src/dataflow/debug/solution_generator.py:1-797`

Ranks 60+ solution templates by relevance, customizes with error context, and returns top N solutions.

**SuggestedSolution Class**:
```python
from dataflow.debug.solution_generator import SolutionGenerator, SuggestedSolution

generator = SolutionGenerator(knowledge_base)
solutions = generator.generate_solutions(
    analysis=analysis_result,
    category=error_category,
    max_solutions=5,
    min_relevance=0.3
)

# SuggestedSolution attributes:
solution.solution_id      # "SOL_001"
solution.title            # "Add Missing 'id' Parameter"
solution.category         # "QUICK_FIX"
solution.description      # Short description
solution.code_example     # Customized code example
solution.explanation      # Detailed explanation
solution.relevance_score  # 0.0-1.0 relevance score
solution.confidence       # 0.0-1.0 confidence from categorizer
solution.difficulty       # "easy", "medium", "hard"
solution.estimated_time   # Minutes to implement
```

**Relevance Scoring Algorithm**:
```python
# Scoring formula (0.0-1.0):
# relevance_score = (pattern_confidence * 0.5) + (context_match * 0.5) + category_bonus
#
# Components:
# 1. Pattern confidence (0.0-1.0): From ErrorCategorizer
# 2. Context match (0.0-1.0):
#    - Solution addresses affected_nodes? +0.3
#    - Solution addresses affected_models? +0.3
#    - Solution references context_data fields? +0.4
# 3. Category bonus:
#    - QUICK_FIX for PARAMETER/CONNECTION? +0.2
#    - CODE_REFACTORING for MIGRATION/RUNTIME? +0.1

# Example:
# pattern_confidence = 0.95
# context_match = 0.85 (addresses node, model, missing parameter)
# category_bonus = 0.2 (QUICK_FIX for PARAMETER)
# relevance_score = min(0.95*0.5 + 0.85*0.5 + 0.2, 1.0) = 1.0
```

**Solution Customization**:
```python
# Generic solution template:
code_example = '''
workflow.add_node("${node_type}", "create", {
    "${parameter_name}": "value"
})
'''

# Customized with error context:
code_example = '''
workflow.add_node("UserCreateNode", "create", {
    "id": "value"  # Replaced ${parameter_name} → "id"
})
'''

# Customization placeholders:
# ${parameter_name} → context_data["missing_parameter"]
# ${model_name} → context_data["model_name"]
# ${node_type} → context_data["node_type"]
# ${missing_node} → context_data["missing_node"]
# ${suggested_node} → context_data["similar_nodes"][0][0]
# ${table_name} → context_data["table_name"]
```

**Category-Specific Filters**:
```python
# Each error category has specialized solution filtering:

# PARAMETER errors → _filter_parameter_solutions()
# Boosts:
#   - Solutions mentioning specific missing parameter: +0.15
#   - Solutions for primary key parameters: +0.1

# CONNECTION errors → _filter_connection_solutions()
# Boosts:
#   - Solutions mentioning typos/similar nodes: +0.2
#   - Solutions for specific missing node: +0.15

# MIGRATION errors → _filter_migration_solutions()
# Boosts:
#   - Solutions for table name issues: +0.1
#   - Solutions mentioning schema/migration: +0.1
```

**Fallback Solutions** (for UNKNOWN category):
```python
# When no pattern matches (category == UNKNOWN):
# Generate 5 generic but actionable fallback solutions:

# 1. Examine Error Message and Stack Trace (relevance: 0.5)
# 2. Verify Configuration of Affected Components (relevance: 0.45)
# 3. Follow Context-Specific Recommendations (relevance: 0.55)
# 4. Enable Debug Logging for More Information (relevance: 0.4)
# 5. Consult DataFlow Documentation and Patterns (relevance: 0.35)
```

**SolutionGenerator API**:
```python
from dataflow.debug.solution_generator import SolutionGenerator

generator = SolutionGenerator(knowledge_base)

# Generate ranked solutions
solutions = generator.generate_solutions(
    analysis=analysis_result,
    category=error_category,
    max_solutions=5,
    min_relevance=0.3
)
# Returns: List[SuggestedSolution] sorted by relevance

# Calculate relevance score
score = generator._calculate_relevance_score(
    solution=solution_dict,
    analysis=analysis_result,
    category=error_category
)
# Returns: float (0.0-1.0)

# Customize solution template
customized = generator._customize_solution(
    solution=solution_dict,
    analysis=analysis_result,
    solution_id="SOL_001"
)
# Returns: Dict with customized code examples
```

**Solution Structure** (from `solutions.yaml`):
```yaml
SOL_001:
  id: SOL_001
  title: "Add Missing 'id' Parameter to CreateNode"
  category: QUICK_FIX
  description: "Add required 'id' field to CREATE operation"
  code_example: |
    workflow.add_node("${node_type}", "create", {
        "${parameter_name}": "user-123",  # Required parameter
        "name": "Alice"
    })
  explanation: |
    DataFlow requires all models to have an 'id' field as primary key.
    This field must be explicitly provided in CREATE operations.
  difficulty: easy
  estimated_time: 1
  references:
    - https://docs.dataflow.dev/models
```

**File Reference**: `src/dataflow/debug/solution_generator.py:1-797` (SolutionGenerator, SuggestedSolution)

### Stage 5: Result Formatting

**Location**: `src/dataflow/debug/debug_agent.py:1-487`

Formats debug results into CLI (ANSI colors), JSON (machine-readable), or dictionary (programmatic access).

**DebugReport Class**:
```python
from dataflow.debug.debug_agent import DebugAgent, DebugReport

# Execute debug agent
report = debug_agent.debug(exception, max_solutions=5, min_relevance=0.3)

# DebugReport attributes:
report.captured_error     # CapturedError from Stage 1
report.error_category     # ErrorCategory from Stage 2
report.analysis_result    # AnalysisResult from Stage 3
report.suggested_solutions  # List[SuggestedSolution] from Stage 4
report.execution_time_ms  # Debug pipeline execution time
```

**Output Format 1: CLI (ANSI Colors)**:
```python
# Rich terminal output with box drawing and colors
print(report.to_cli_format())

# Example output:
# ╔═══════════════════════════════════════════════════════════════╗
# ║                    DataFlow Debug Report                      ║
# ╚═══════════════════════════════════════════════════════════════╝
#
# Error Category: PARAMETER (Confidence: 95%)
# Root Cause: Node 'create' is missing required parameter 'id' (primary key)
#
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Suggested Solutions (5)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# [1] Add Missing 'id' Parameter to CreateNode (QUICK_FIX) - 95%
#
#     workflow.add_node("UserCreateNode", "create", {
#         "id": "user-123",  # Add missing parameter
#         "name": "Alice"
#     })
#
#     Difficulty: easy | Estimated time: 1 minute
#
# [2] Use UUID for Automatic ID Generation (BEST_PRACTICE) - 85%
#     ...
```

**Output Format 2: JSON (Machine-Readable)**:
```python
# Structured JSON for logging/monitoring
json_output = report.to_json()

# Example output:
{
  "error_category": {
    "category": "PARAMETER",
    "pattern_id": "PARAM_001",
    "confidence": 0.95,
    "pattern_name": "Missing Required Parameter 'id'"
  },
  "analysis_result": {
    "root_cause": "Node 'create' is missing required parameter 'id' (primary key)",
    "affected_nodes": ["create"],
    "affected_models": ["User"],
    "context_data": {
      "missing_parameter": "id",
      "model_name": "User",
      "is_primary_key": true
    }
  },
  "suggested_solutions": [
    {
      "solution_id": "SOL_001",
      "title": "Add Missing 'id' Parameter to CreateNode",
      "category": "QUICK_FIX",
      "code_example": "...",
      "relevance_score": 0.95,
      "difficulty": "easy",
      "estimated_time": 1
    }
  ],
  "execution_time_ms": 47.3
}
```

**Output Format 3: Dictionary (Programmatic)**:
```python
# Direct field access for custom processing
data = report.to_dict()

# Access fields:
category = data["error_category"]["category"]
root_cause = data["analysis_result"]["root_cause"]
solutions = data["suggested_solutions"]

# Example usage:
if category == "PARAMETER":
    missing_param = data["analysis_result"]["context_data"]["missing_parameter"]
    print(f"Add parameter: {missing_param}")
```

**DebugAgent API**:
```python
from dataflow.debug.debug_agent import DebugAgent

agent = DebugAgent(knowledge_base, inspector)

# Debug exception
report = agent.debug(
    exception=e,
    max_solutions=5,      # Top N solutions
    min_relevance=0.3     # Minimum relevance threshold
)
# Returns: DebugReport with 5-stage pipeline results

# Debug from string (log parsing)
report = agent.debug_from_string(
    error_message="ValueError: Missing parameter 'id'"
)
# Returns: DebugReport with limited context
```

**File Reference**: `src/dataflow/debug/debug_agent.py:1-487` (DebugAgent, DebugReport)

### Knowledge Base Management

**Location**: `src/dataflow/debug/knowledge_base.py:1-221`

Centralized storage and retrieval of error patterns and solution templates.

**KnowledgeBase Class**:
```python
from dataflow.debug.knowledge_base import KnowledgeBase

kb = KnowledgeBase(
    patterns_path="src/dataflow/debug/patterns.yaml",
    solutions_path="src/dataflow/debug/solutions.yaml"
)

# Get pattern by ID
pattern = kb.get_pattern("PARAM_001")
# Returns: Dict with pattern details

# Get all patterns for category
param_patterns = kb.get_patterns_by_category("PARAMETER")
# Returns: List[Dict] with 15 PARAMETER patterns

# Get solution by ID
solution = kb.get_solution("SOL_001")
# Returns: Dict with solution template

# Get solutions for pattern
solutions = kb.get_solutions_for_pattern("PARAM_001")
# Returns: List[Dict] with related solutions

# Reload from disk (hot reload)
kb.reload_patterns()
kb.reload_solutions()
```

**Pattern Database** (`patterns.yaml`):
- 50+ error patterns across 5 categories
- Regex patterns for message matching
- Semantic features for context matching
- Severity levels (low, medium, high, critical)
- Related solutions mapping

**Solution Database** (`solutions.yaml`):
- 60+ solution templates across 4 categories
- Code examples with placeholders
- Detailed explanations
- Difficulty ratings (easy, medium, hard)
- Estimated implementation time

**File Reference**: `src/dataflow/debug/knowledge_base.py:1-221` (KnowledgeBase)

### Performance Optimization

**Execution Time Breakdown**:
```
Stage 1 (Capture):        5-10ms
Stage 2 (Categorize):     10-20ms (pattern matching + semantic features)
Stage 3 (Analyze):        10-15ms (Inspector API calls)
Stage 4 (Generate):       15-25ms (solution ranking + customization)
Stage 5 (Format):         5-10ms (string formatting)
Total:                    45-80ms (average: 50ms)
```

**Optimization Strategies**:

**1. Reduce max_solutions** (20-30% speedup):
```python
# Default: 5 solutions
report = agent.debug(e, max_solutions=5)  # 50ms

# Optimized: 3 solutions
report = agent.debug(e, max_solutions=3)  # 35ms (30% faster)
```

**2. Increase min_relevance** (40-50% speedup):
```python
# Default: 30% minimum relevance
report = agent.debug(e, min_relevance=0.3)  # 50ms

# Optimized: 70% minimum relevance
report = agent.debug(e, min_relevance=0.7)  # 25ms (50% faster)
```

**3. Disable Inspector** (30-40% speedup):
```python
# With Inspector (full context)
agent = DebugAgent(kb, inspector)
report = agent.debug(e)  # 50ms

# Without Inspector (limited context)
agent = DebugAgent(kb, inspector=None)
report = agent.debug(e)  # 30ms (40% faster)
```

**4. Singleton Pattern** (avoid repeated initialization):
```python
# ✅ CORRECT - Initialize once, reuse
kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
inspector = Inspector(db)
agent = DebugAgent(kb, inspector)

for workflow in workflows:
    try:
        runtime.execute(workflow.build())
    except Exception as e:
        report = agent.debug(e)  # 50ms per error

# ❌ WRONG - Initialize every time
for workflow in workflows:
    try:
        runtime.execute(workflow.build())
    except Exception as e:
        kb = KnowledgeBase(...)  # 20ms overhead
        agent = DebugAgent(...)  # 10ms overhead
        report = agent.debug(e)  # 50ms + 30ms overhead = 80ms
```

### Testing Coverage

**Unit Tests**:
- `tests/unit/test_error_capture.py` - ErrorCapture, CapturedError, StackFrame
- `tests/unit/test_error_categorizer.py` - ErrorCategorizer, pattern matching
- `tests/unit/test_context_analyzer.py` - ContextAnalyzer, Inspector integration
- `tests/unit/test_solution_generator.py` - SolutionGenerator, relevance scoring
- `tests/unit/test_debug_agent.py` - DebugAgent, pipeline orchestration
- `tests/unit/test_knowledge_base.py` - KnowledgeBase, pattern/solution loading

**Integration Tests**:
- `tests/integration/test_debug_agent_e2e.py:1-687` - 18 end-to-end scenarios
  - Missing 'id' parameter (PARAM_001)
  - CreateNode vs UpdateNode confusion (PARAM_005/PARAM_006)
  - Source node not found (CONN_001)
  - Type mismatch in connections (CONN_007)
  - Table not found (MIG_002)
  - Invalid database URL (CONFIG_001)
  - Event loop closed (RUNTIME_005)
  - And 11 more scenarios...
- **100% passing** (all 18 tests pass)

### Documentation

**User Guide**: `docs/guides/debug-agent-user-guide.md:1-2513`
- Quick start (20 lines of code)
- 15 common error scenarios with solutions
- Production integration patterns
- Configuration tuning guide
- Troubleshooting common issues

**Developer Guide**: `docs/guides/debug-agent-developer-guide.md:1-2003`
- 5-stage pipeline architecture
- Custom pattern creation
- Custom solution templates
- Extending categorizer
- Performance profiling

**Examples**: `examples/debug_agent/`
- `01_basic_error_handling.py` - Basic usage
- `02_production_logging.py` - Logging integration
- `03_batch_error_analysis.py` - Batch processing
- `04_custom_pattern_example.py` - Custom patterns
- `05_performance_monitoring.py` - Performance tracking

### File References (Complete)

**Core Implementation**:
- `src/dataflow/debug/debug_agent.py:1-487` - DebugAgent orchestrator
- `src/dataflow/debug/error_capture.py:1-312` - Stage 1: Capture
- `src/dataflow/debug/error_categorizer.py:1-426` - Stage 2: Categorize
- `src/dataflow/debug/context_analyzer.py:1-768` - Stage 3: Analyze
- `src/dataflow/debug/solution_generator.py:1-797` - Stage 4: Suggest
- `src/dataflow/debug/knowledge_base.py:1-221` - Pattern/solution database
- `src/dataflow/debug/patterns.yaml:1-723` - 50+ error patterns
- `src/dataflow/debug/solutions.yaml:1-895` - 60+ solution templates

**Supporting Classes**:
- `src/dataflow/debug/analysis_result.py` - AnalysisResult data class
- `src/dataflow/debug/suggested_solution.py` - SuggestedSolution data class
- `src/dataflow/debug/cli.py` - CLI interface (python -m dataflow.debug.cli)

**Testing**:
- `tests/unit/test_debug_agent.py` - Unit tests for all stages
- `tests/integration/test_debug_agent_e2e.py:1-687` - 18 E2E scenarios (100% passing)

**Documentation**:
- `docs/guides/debug-agent-user-guide.md:1-2513` - Complete user guide
- `docs/guides/debug-agent-developer-guide.md:1-2003` - Developer guide

---

## 🔧 CLI Commands (NEW in v0.4.7+)

DataFlow includes 5 CLI commands for workflow analysis, debugging, and generation.

**Available Commands**:
1. **analyze**: Analyze workflow structure and dependencies
2. **debug**: Debug workflow issues with detailed diagnostics
3. **generate**: Generate node code from models
4. **perf**: Performance analysis and profiling
5. **validate**: Validate workflow structure before execution

**Command 1: Analyze**
```bash
# Analyze workflow structure
dataflow analyze my_workflow.py

# Output:
# Workflow Analysis Report
# - Nodes: 15
# - Connections: 23
# - Cycles: 0
# - Validation: PASSED
# - Estimated Runtime: ~2.5s
```

**Command 2: Debug**
```bash
# Debug workflow with detailed diagnostics
dataflow debug my_workflow.py --node "user_create"

# Output:
# Node Debug Report: user_create
# - Type: UserCreateNode
# - Parameters: id, name, email
# - Connections: 3 outgoing, 0 incoming
# - Validation: PASSED
# - Potential Issues: None
```

**Command 3: Generate**
```bash
# Generate node code from model
dataflow generate User --output nodes/

# Generates:
# - nodes/user_create_node.py
# - nodes/user_read_node.py
# - nodes/user_update_node.py
# - nodes/user_delete_node.py
# - nodes/user_list_node.py
```

**Command 4: Perf**
```bash
# Analyze workflow performance
dataflow perf my_workflow.py --profile

# Output:
# Performance Analysis Report
# - Total Runtime: 1.8s
# - Node Timings:
#   - user_create: 0.5s (28%)
#   - user_read: 0.3s (17%)
#   - email_send: 1.0s (55%)
# - Bottlenecks: email_send (optimize email API calls)
```

**Command 5: Validate**
```bash
# Validate workflow before execution
dataflow validate my_workflow.py --strict

# Output:
# Workflow Validation Report
# - Structure: PASSED
# - Connections: PASSED (23 connections)
# - Parameters: PASSED (all required parameters present)
# - Types: PASSED (all type constraints satisfied)
# - Cycles: PASSED (no circular dependencies)
# - Overall: PASSED ✓
```

**File Reference**: `src/dataflow/cli/*.py` (5 command files)

## 🔄 UpsertNode with Custom Conflict Fields (v0.8.0+)

### What is UpsertNode?

**UpsertNode** performs "upsert" operations (INSERT if record doesn't exist, UPDATE if it does) in a single atomic operation. **v0.8.0+** adds `conflict_on` parameter for custom conflict detection.

### Key Features
- **Atomic operation**: Single database query for INSERT or UPDATE
- **Custom conflict fields**: Specify any unique field(s) for conflict detection (v0.8.0+)
- **Cross-database**: Works identically on PostgreSQL, MySQL, and SQLite
- **Natural keys**: Use email, SKU, or composite keys instead of just `id`
- **Return metadata**: Tells you whether INSERT or UPDATE occurred

### Basic Usage

```python
from dataflow import DataFlow
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

db = DataFlow("postgresql://...")

@db.model
class User:
    id: str
    email: str
    name: str

workflow = WorkflowBuilder()
workflow.add_node("UserUpsertNode", "upsert", {
    "where": {"id": "user-123"},
    "update": {"name": "Alice Updated"},
    "create": {"id": "user-123", "email": "alice@example.com", "name": "Alice"}
})

runtime = AsyncLocalRuntime()
results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

# Check what happened
print(results["upsert"]["created"])  # True = inserted, False = updated
print(results["upsert"]["action"])   # "created" or "updated"
```

### Custom Conflict Fields (v0.8.0+)

**Use any unique field(s) for conflict detection**, not just `id`. Perfect for natural keys like email, SKU, or composite keys.

**Single Field Conflict**
```python
# Upsert based on email (natural key)
@db.model
class User:
    id: str
    email: str  # Unique field
    name: str

workflow.add_node("UserUpsertNode", "upsert", {
    "where": {"email": "alice@example.com"},
    "conflict_on": ["email"],  # NEW: Conflict on email
    "update": {"name": "Alice Updated"},
    "create": {
        "id": "user-123",
        "email": "alice@example.com",
        "name": "Alice"
    }
})

# First run: INSERT (email doesn't exist)
# Second run: UPDATE (email exists)
```

**Composite Key Conflict**
```python
# Upsert based on multiple fields (composite key)
@db.model
class OrderItem:
    id: str
    order_id: str
    product_id: str
    quantity: int

workflow.add_node("OrderItemUpsertNode", "upsert", {
    "where": {"order_id": "order-123", "product_id": "prod-456"},
    "conflict_on": ["order_id", "product_id"],  # Composite key
    "update": {"quantity": 10},
    "create": {
        "id": "item-789",
        "order_id": "order-123",
        "product_id": "prod-456",
        "quantity": 5
    }
})
```

### Parameter Reference

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `where` | dict | Yes | Fields to identify the record |
| `update` | dict | No | Fields to update if record exists |
| `create` | dict | No | Fields to create if record doesn't exist |
| `conflict_on` | list | No | Fields for conflict detection (defaults to `where` keys) |

### Common Patterns

**Pattern 1: Email-based User Upsert**
```python
# Ensure user exists with updated data
workflow.add_node("UserUpsertNode", "upsert", {
    "where": {"email": user_email},
    "conflict_on": ["email"],
    "update": {"last_login": datetime.now(), "name": user_name},
    "create": {"id": user_id, "email": user_email, "name": user_name}
})
```

**Pattern 2: Idempotent API Requests**
```python
# Ensure request is only processed once
workflow.add_node("RequestUpsertNode", "upsert", {
    "where": {"request_id": req_id},
    "conflict_on": ["request_id"],
    "update": {},  # Don't update if exists
    "create": {"id": id, "request_id": req_id, "data": req_data}
})

if results["upsert"]["created"]:
    # Process the request
    pass
else:
    # Request already processed
    pass
```

## 🔢 CountNode - Efficient Count Queries (v0.8.0+)

### What is CountNode?

**CountNode** performs efficient `SELECT COUNT(*) FROM table WHERE filters` queries without fetching actual records. Automatically generated for all SQL models.

### Key Features
- **High performance**: 10-50x faster than ListNode workaround (1-5ms vs 20-50ms)
- **No data transfer**: Only count value returned, no records
- **Filter support**: Supports MongoDB-style filters (same as ListNode)
- **Cross-database**: Works identically on PostgreSQL, MySQL, and SQLite
- **Zero overhead**: Minimal memory usage (<1KB)

### Basic Usage

```python
from dataflow import DataFlow
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

db = DataFlow("postgresql://...")

@db.model
class User:
    id: str
    email: str
    name: str
    active: bool

# Count all records
workflow = WorkflowBuilder()
workflow.add_node("UserCountNode", "count_all", {})

runtime = AsyncLocalRuntime()
results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
print(results["count_all"]["count"])  # 1523
```

### Count with Filters

```python
# Count active users
workflow.add_node("UserCountNode", "count_active", {
    "filter": {"active": True}
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
print(results["count_active"]["count"])  # 842

# Count with complex filters
workflow.add_node("UserCountNode", "count_complex", {
    "filter": {
        "active": True,
        "email": {"$like": "%@example.com"}
    }
})
```

### Performance Comparison

**ListNode Workaround** (Deprecated):
```python
# ❌ SLOW: Fetches all records to count (20-50ms)
workflow.add_node("UserListNode", "count_users", {"limit": 10000})
results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
count = len(results["count_users"])  # Fetched 10,000 records!
```

**CountNode** (Recommended):
```python
# ✅ FAST: Uses COUNT(*) query (1-5ms)
workflow.add_node("UserCountNode", "count_users", {})
results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
count = results["count_users"]["count"]  # Only count value
```

**Performance Metrics**:
- Query time: 1-5ms (vs. 20-50ms with ListNode)
- Memory usage: <1KB (vs. 1-10MB with ListNode)
- Network transfer: 8 bytes (vs. 100KB-10MB with ListNode)

### Common Patterns

**Pattern 1: Session Statistics**
```python
# Count active sessions for each user
workflow.add_node("SessionCountNode", "count_sessions", {
    "filter": {"user_id": user_id, "active": True}
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
if results["count_sessions"]["count"] > 5:
    print(f"Warning: {results['count_sessions']['count']} active sessions")
```

**Pattern 2: Metrics Dashboard**
```python
# Build real-time dashboard metrics
workflow.add_node("OrderCountNode", "total_orders", {})
workflow.add_node("OrderCountNode", "pending_orders", {
    "filter": {"status": "pending"}
})
workflow.add_node("OrderCountNode", "completed_orders", {
    "filter": {"status": "completed"}
})

results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
metrics = {
    "total": results["total_orders"]["count"],
    "pending": results["pending_orders"]["count"],
    "completed": results["completed_orders"]["count"]
}
```

## 🔢 PostgreSQL Native Arrays (v0.8.0+)

### What Are Native Arrays?

PostgreSQL native arrays (TEXT[], INTEGER[], REAL[]) provide **2-10x faster performance** compared to JSON string storage, with built-in indexing support (GIN/GiST) and PostgreSQL-specific operators.

### Key Features
- **Native PostgreSQL arrays**: TEXT[], INTEGER[], REAL[] instead of JSONB
- **Opt-in feature flag**: Backward compatible, enable per-model with `__dataflow__`
- **Cross-database validated**: Error if used on MySQL/SQLite
- **Performance gains**: 2-10x faster queries with native array operators
- **Index support**: GIN/GiST indexes for array columns

### Basic Usage

```python
from dataflow import DataFlow
from typing import List

db = DataFlow("postgresql://...")

@db.model
class AgentMemory:
    id: str
    tags: List[str]
    scores: List[int]
    ratings: List[float]

    __dataflow__ = {
        'use_native_arrays': True  # Opt-in to PostgreSQL native arrays
    }

# Generates PostgreSQL schema:
# CREATE TABLE agent_memorys (
#     id TEXT PRIMARY KEY,
#     tags TEXT[],      -- Native array instead of JSONB
#     scores INTEGER[],  -- Native array
#     ratings REAL[]     -- Native array
# )
```

### Supported Array Types

| Python Type | PostgreSQL Type | Element Type |
|-------------|-----------------|--------------|
| `List[str]` | `TEXT[]` | Text strings |
| `List[int]` | `INTEGER[]` | Integers |
| `List[float]` | `REAL[]` | Floating point |
| `Optional[List[str]]` | `TEXT[] NULL` | Nullable arrays |

**Unsupported** (defaults to JSONB):
- `List[dict]`, `List[List[...]]` (nested), custom types

### CRUD Operations

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime

workflow = WorkflowBuilder()

# Create with array values
workflow.add_node("AgentMemoryCreateNode", "create", {
    "id": "mem-001",
    "tags": ["medical", "urgent", "ai"],
    "scores": [85, 92, 78],
    "ratings": [4.5, 4.8, 4.2]
})

# Update array values
workflow.add_node("AgentMemoryUpdateNode", "update", {
    "filter": {"id": "mem-001"},
    "fields": {
        "tags": ["medical", "urgent", "ai", "reviewed"]
    }
})

# Query with array operators
workflow.add_node("AgentMemoryListNode", "find", {
    "filter": {"tags": {"$contains": "medical"}}
})

runtime = AsyncLocalRuntime()
results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
```

### PostgreSQL Array Operators

DataFlow provides MongoDB-style syntax for PostgreSQL array operators:

**Contains Operator (@>)**
```python
# Find records where tags contain "medical"
workflow.add_node("AgentMemoryListNode", "find_medical", {
    "filter": {"tags": {"$contains": "medical"}}
})
# SQL: WHERE tags @> ARRAY['medical']
```

**Overlap Operator (&&)**
```python
# Find records where tags overlap with ["medical", "urgent"]
workflow.add_node("AgentMemoryListNode", "find_urgent", {
    "filter": {"tags": {"$overlap": ["medical", "urgent"]}}
})
# SQL: WHERE tags && ARRAY['medical', 'urgent']
```

**Any Operator (= ANY)**
```python
# Find records where any score is >= 90
workflow.add_node("AgentMemoryListNode", "high_scores", {
    "filter": {"scores": {"$any": {"$gte": 90}}}
})
# SQL: WHERE 90 <= ANY(scores)
```

### Performance Optimization

**Query Performance**

**Before (JSON string storage)**:
```python
tags: str  # Manual encoding: ",".join(tags)
# Query: WHERE tags LIKE '%medical%'  # Slow, no index
# Time: ~50ms for 10k rows
```

**After (Native arrays)**:
```python
tags: List[str]  # Native PostgreSQL array
# Query: WHERE tags @> ARRAY['medical']  # Fast, GIN index
# Time: ~5ms for 10k rows (10x faster!)
```

### Best Practices

**When to Use Native Arrays**:
- ✅ PostgreSQL production databases
- ✅ Large tables (>10k rows) with frequent array queries
- ✅ Need for array-specific operators (@>, &&, ANY)
- ✅ Performance-critical applications

**When NOT to Use Native Arrays**:
- ❌ Cross-database compatibility required (MySQL, SQLite)
- ❌ Small tables (<1k rows) with infrequent queries
- ❌ Nested arrays or complex element types
- ❌ Development phase (use default JSONB for flexibility)

## 🚀 Schema Cache (v0.7.3+)

### What It Is

The schema cache is a thread-safe table existence cache that eliminates redundant migration checks, providing **91-99% performance improvement** for multi-operation workflows.

### Key Features
- **Thread-safe**: RLock protection for multi-threaded apps (FastAPI, Flask, Gunicorn)
- **Configurable**: TTL, size limits, and validation
- **Automatic invalidation**: Cache cleared on schema changes
- **Low overhead**: <1KB per cached table

### Performance Characteristics
- **Cache miss** (first check): ~1500ms
- **Cache hit** (subsequent): ~1ms
- **Improvement**: 91-99% faster for multi-operation workflows

### Configuration

```python
from dataflow import DataFlow

# Default (cache enabled, no TTL)
db = DataFlow("postgresql://...")

# Custom configuration
db = DataFlow(
    "postgresql://...",
    schema_cache_enabled=True,      # Enable/disable cache
    schema_cache_ttl=300,            # TTL in seconds (None = no expiration)
    schema_cache_max_size=10000,    # Max cached tables
    schema_cache_validation=False,  # Schema checksum validation
)

# Disable cache (for debugging)
db = DataFlow("postgresql://...", schema_cache_enabled=False)
```

### Usage (Automatic)

```python
# Cache works automatically - no code changes needed
db = DataFlow("postgresql://...")

@db.model
class User:
    id: str
    name: str

# First operation: Cache miss (~1500ms)
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-1",
    "name": "Alice"
})
runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

# Subsequent operations: Cache hit (~1ms)
workflow2 = WorkflowBuilder()
workflow2.add_node("UserCreateNode", "create2", {
    "id": "user-2",
    "name": "Bob"
})
results2, _ = runtime.execute(workflow2.build())  # 99% faster!
```

### Cache Methods (Advanced)

```python
# Clear all cache entries
db._schema_cache.clear()

# Get cache performance statistics
metrics = db._schema_cache.get_metrics()
print(f"Hits: {metrics['hits']}")
print(f"Misses: {metrics['misses']}")
print(f"Hit rate: {metrics['hit_rate']:.2%}")
print(f"Cached tables: {metrics['cached_tables']}")
```

### Thread Safety

The schema cache is fully thread-safe for multi-threaded applications:

```python
from dataflow import DataFlow
from concurrent.futures import ThreadPoolExecutor

db = DataFlow("postgresql://...")

@db.model
class User:
    id: str
    name: str

def create_user(user_id: str):
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": user_id,
        "name": f"User {user_id}"
    })
    runtime = LocalRuntime()
    return runtime.execute(workflow.build())

# Safe for concurrent execution
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(create_user, f"user-{i}") for i in range(100)]
    results = [f.result() for f in futures]
```

All cache operations are protected by RLock, ensuring safe concurrent access from FastAPI endpoints, Flask workers, or Gunicorn processes.

## 🔧 String ID Preservation & Multi-Instance Isolation (v0.4.7+)

### String ID Preservation

**No forced integer conversion** - String/UUID IDs preserved exactly.

```python
# ✅ CORRECT - String IDs preserved
@db.model
class Session:
    id: str  # Explicitly string
    user_id: str

# Creates with string ID preserved
workflow.add_node("SessionCreateNode", "create", {
    "id": "sess-uuid-123",  # Stays as string
    "user_id": "user-456"
})
```

### Multi-Instance Isolation

Each DataFlow instance maintains separate context - nodes are bound to the correct instance.

```python
# Each instance is independent
dev_db = DataFlow("sqlite:///dev.db")
prod_db = DataFlow("postgresql://prod...")

@dev_db.model
class User:
    name: str

@prod_db.model
class User:  # Same name, different instance - works!
    name: str
    email: str

# Nodes bound to correct instance
dev_node = dev_db._nodes["UserCreateNode"]()
prod_node = prod_db._nodes["UserCreateNode"]()
# dev_node.dataflow_instance is dev_db ✓
# prod_node.dataflow_instance is prod_db ✓
```

### Automatic Datetime Conversion (v0.6.4+)

DataFlow automatically converts ISO 8601 datetime strings to Python datetime objects across ALL CRUD nodes. This enables seamless integration with PythonCodeNode and external data sources.

**Supported ISO 8601 Formats:**
- Basic: `2024-01-01T12:00:00`
- With microseconds: `2024-01-01T12:00:00.123456`
- With timezone Z: `2024-01-01T12:00:00Z`
- With timezone offset: `2024-01-01T12:00:00+05:30`

**Example: PythonCodeNode → CreateNode**
```python
# PythonCodeNode outputs ISO string
workflow.add_node("PythonCodeNode", "generate_timestamp", {
    "code": """
from datetime import datetime
result = {"created_at": datetime.now().isoformat()}
    """
})

# CreateNode automatically converts to datetime
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "created_at": "{{generate_timestamp.created_at}}"  # ISO string → datetime
})
```

**Backward Compatibility:**
```python
from datetime import datetime

# Existing code with datetime objects still works
workflow.add_node("UserCreateNode", "create", {
    "name": "Bob",
    "created_at": datetime.now()  # Still works!
})
```

**Applies To:** CreateNode, UpdateNode, BulkCreateNode, BulkUpdateNode, BulkUpsertNode

### Dynamic Updates with PythonCodeNode Multi-Output (Core SDK v0.9.28+)

**NEW**: Core SDK v0.9.28+ enables **BOTH** PythonCodeNode and AsyncPythonCodeNode to export multiple variables directly, making dynamic DataFlow updates natural and intuitive.

**IMPORTANT**: AsyncPythonCodeNode achieved full feature parity with PythonCodeNode in v0.9.30 - both work identically for multi-output patterns!

**Before v0.9.28 (nested result pattern):**
```python
# OLD: Forced to nest everything in 'result'
workflow.add_node("PythonCodeNode", "prepare", {
    "code": """
result = {
    "filter": {"id": summary_id},
    "fields": {"summary_markdown": updated_text}
}
    """
})
# Complex nested path connections required
workflow.add_connection("prepare", "result.filter", "update", "filter")
workflow.add_connection("prepare", "result.fields", "update", "fields")
```

**After v0.9.28 (multi-output pattern):**
```python
# NEW: Natural variable definitions
workflow.add_node("PythonCodeNode", "prepare", {
    "code": """
filter_data = {"id": summary_id}
summary_markdown = updated_text
edited_by_user = True
    """
})

# Clean, direct connections
workflow.add_node("ConversationSummaryUpdateNode", "update", {})
workflow.add_connection("prepare", "filter_data", "update", "filter")
workflow.add_connection("prepare", "summary_markdown", "update", "summary_markdown")
workflow.add_connection("prepare", "edited_by_user", "update", "edited_by_user")
```

**Benefits:**
- ✅ Natural variable naming
- ✅ Matches developer mental model
- ✅ Less nesting, cleaner code
- ✅ Full DataFlow benefits retained (no SQL needed!)
- ✅ Works with both PythonCodeNode AND AsyncPythonCodeNode (v0.9.30+)

**AsyncPythonCodeNode Example (v0.9.30+):**
```python
# Async operations with multi-output - identical to sync!
workflow.add_node("AsyncPythonCodeNode", "async_prepare", {
    "code": """
import asyncio

# Simulate async data fetching
async def fetch_user_data(user_id):
    await asyncio.sleep(0.1)  # Simulate I/O
    return {"id": user_id, "verified": True}

user_data = await fetch_user_data(user_id)

# Export multiple variables for DataFlow nodes
filter_data = {"id": user_data["id"]}
verification_status = user_data["verified"]
updated_by_system = True
    """
})

# Works identically with DataFlow nodes!
workflow.add_node("UserUpdateNode", "update", {})
workflow.add_connection("async_prepare", "filter_data", "update", "filter")
workflow.add_connection("async_prepare", "verification_status", "update", "verified")
workflow.add_connection("async_prepare", "updated_by_system", "update", "updated_by_system")
```

**Backward Compatibility:** Old patterns with `result = {...}` continue to work 100%.

**Requirements:** Core SDK >= v0.9.30 (for AsyncPythonCodeNode multi-output), DataFlow >= v0.6.6

**See Also:** [dataflow-dynamic-updates](../../skills/02-dataflow/dataflow-dynamic-updates.md) skill for complete examples

### Event Loop Isolation

AsyncSQLDatabaseNode now automatically isolates connection pools per event loop, preventing "Event loop is closed" errors in sequential workflows and FastAPI applications.

**Benefits** (automatic, no code changes):
- Stronger isolation between DataFlow instances
- Sequential operations work reliably
- FastAPI requests properly isolated
- <5% performance overhead

**What Changed**: Pool keys now include event loop ID (`{loop_id}|{db}|...`) ensuring different event loops get separate pools. Stale pools from closed loops are automatically cleaned up.

### Connection Pooling Best Practices
```python
# ⚠️ DataFlow uses AsyncSQL with connection pooling internally

# ❌ AVOID: Multiple runtime.execute() calls create separate event loops
for i in range(10):
    runtime = LocalRuntime()
    results = runtime.execute(workflow.build())  # New event loop = no pool sharing

# ✅ RECOMMENDED: Use persistent runtime for proper connection pooling
runtime = LocalRuntime(persistent_mode=True)
for i in range(10):
    results = await runtime.execute_async(workflow.build())  # Shared pool

# ✅ ALTERNATIVE: Configure DataFlow pool settings
db = DataFlow(
    "postgresql://...",
    pool_size=20,           # Initial pool size
    max_overflow=10,        # Allow 10 extra connections under load
    pool_timeout=30         # Wait up to 30s for connection
)
```

### Safe Existing Database Connection
```python
# Connect to existing database without schema changes
db = DataFlow(
    "postgresql://user:pass@localhost/db",
    auto_migrate=False,        # Won't create missing tables
    existing_schema_mode=True   # Uses existing schema as-is
)

# VERIFIED BEHAVIOR (v0.4.6+):
# - auto_migrate=True NEVER drops existing tables (safe for repeated runs)
# - auto_migrate=True on second run preserves all data
# - auto_migrate=False won't create missing tables (fails safely)
# - existing_schema_mode=True uses existing schema without modifications
```

### Dynamic Model Registration
```python
# Option 1: Register discovered tables as models
schema = db.discover_schema(use_real_inspection=True)
result = db.register_schema_as_models(tables=['users', 'orders'])

# Option 2: Reconstruct models from registry (cross-session)
models = db.reconstruct_models_from_registry()

# Use generated nodes without @db.model decorator
workflow.add_node(result['generated_nodes']['User']['create'], 'create_user', {...})
```

## Generated Nodes & Query Patterns

> **See Skills**: [`dataflow-crud-operations`](../../skills/02-dataflow/dataflow-crud-operations.md) and [`dataflow-queries`](../../skills/02-dataflow/dataflow-queries.md) for complete CRUD and query examples.

Quick reference: **11 nodes auto-generated per model** (v0.8.0+):
- **CRUD**: CreateNode, ReadNode, UpdateNode, DeleteNode
- **Query**: ListNode, CountNode (v0.8.0+)
- **Advanced**: UpsertNode (v0.8.0+)
- **Bulk**: BulkCreateNode, BulkUpdateNode, BulkDeleteNode, BulkUpsertNode

**v0.7.1 Update - BulkUpsertNode:**
- Fully implemented in v0.7.1 (previous versions had stub implementation)
- Parameters: `data` (required), `conflict_resolution` ("update" or "skip"/"ignore")
- Conflict column: Always `id` (DataFlow standard, auto-inferred)
- No `unique_fields` parameter - conflict detection uses `id` field only

### 🔑 CRITICAL: Template Syntax
**Kailash uses `${}` NOT `{{}}`** - See [`dataflow-queries`](../../skills/02-dataflow/dataflow-queries.md) for examples.

## Enterprise Features Overview

> **See Skills**: [`dataflow-bulk-operations`](../../skills/02-dataflow/dataflow-bulk-operations.md) and [`dataflow-transactions`](../../skills/02-dataflow/dataflow-transactions.md) for standard patterns.

This section focuses on **advanced enterprise features** unique to production scenarios.

## Enterprise Migration System

DataFlow includes a comprehensive 8-component enterprise migration system for production-grade schema operations:

### 1. Risk Assessment Engine
```python
from dataflow.migrations.risk_assessment_engine import RiskAssessmentEngine, RiskLevel

# Multi-dimensional risk analysis
risk_engine = RiskAssessmentEngine(connection_manager)

# Comprehensive risk assessment
risk_assessment = await risk_engine.assess_operation_risk(
    operation_type="drop_column",
    table_name="users",
    column_name="deprecated_field",
    dependencies=dependency_report  # From DependencyAnalyzer
)

print(f"Overall Risk: {risk_assessment.overall_risk_level}")  # CRITICAL/HIGH/MEDIUM/LOW
print(f"Risk Score: {risk_assessment.overall_score}/100")

# Risk breakdown by category
for category, risk in risk_assessment.category_risks.items():
    print(f"{category.name}: {risk.risk_level.name} ({risk.score}/100)")
    for factor in risk.risk_factors:
        print(f"  - {factor.description} (Impact: {factor.impact_score})")
```

### 2. Mitigation Strategy Engine
```python
from dataflow.migrations.mitigation_strategy_engine import MitigationStrategyEngine

# Generate comprehensive mitigation strategies
mitigation_engine = MitigationStrategyEngine(risk_engine)

# Get targeted mitigation plan
strategy_plan = await mitigation_engine.generate_mitigation_plan(
    risk_assessment=risk_assessment,
    operation_context={
        "table_size": 1000000,
        "production_environment": True,
        "maintenance_window": 30  # minutes
    }
)

print(f"Mitigation strategies ({len(strategy_plan.recommended_strategies)}):")
for strategy in strategy_plan.recommended_strategies:
    print(f"  {strategy.category.name}: {strategy.description}")
    print(f"  Effectiveness: {strategy.effectiveness_score}/100")
    print(f"  Implementation: {strategy.implementation_steps}")

# Risk reduction estimation
print(f"Estimated risk reduction: {strategy_plan.estimated_risk_reduction}%")
```

### 3. Foreign Key Analyzer
```python
from dataflow.migrations.foreign_key_analyzer import ForeignKeyAnalyzer, FKOperationType

# Comprehensive FK impact analysis
fk_analyzer = ForeignKeyAnalyzer(connection_manager)

# Analyze FK implications
fk_impact = await fk_analyzer.analyze_fk_impact(
    operation=FKOperationType.DROP_COLUMN,
    table_name="users",
    column_name="department_id",
    include_cascade_analysis=True  # Analyze CASCADE effects
)

print(f"FK Impact Level: {fk_impact.impact_level}")
print(f"Affected FK constraints: {len(fk_impact.affected_constraints)}")
print(f"Potential cascade operations: {len(fk_impact.cascade_operations)}")

# FK-safe migration execution
if fk_impact.is_safe_to_proceed:
    fk_safe_plan = await fk_analyzer.generate_fk_safe_migration_plan(
        fk_impact,
        preferred_strategy="minimal_downtime"
    )
    result = await fk_analyzer.execute_fk_safe_migration(fk_safe_plan)
    print(f"FK-safe migration: {result.success}")
else:
    print("⚠️ Operation blocked by FK dependencies - manual intervention required")
```

### 4. Table Rename Analyzer
```python
from dataflow.migrations.table_rename_analyzer import TableRenameAnalyzer

# Safe table renaming with dependency tracking
rename_analyzer = TableRenameAnalyzer(connection_manager)

# Comprehensive dependency analysis
rename_impact = await rename_analyzer.analyze_rename_impact(
    current_name="user_accounts",
    new_name="users"
)

print(f"Total dependencies: {len(rename_impact.total_dependencies)}")
print(f"Views to update: {len(rename_impact.view_dependencies)}")
print(f"FK constraints: {len(rename_impact.fk_dependencies)}")
print(f"Stored procedures: {len(rename_impact.procedure_dependencies)}")
print(f"Triggers: {len(rename_impact.trigger_dependencies)}")

# Execute coordinated rename
if rename_impact.can_rename_safely:
    rename_plan = await rename_analyzer.create_rename_plan(
        rename_impact,
        include_dependency_updates=True,
        backup_strategy="full_backup"
    )
    result = await rename_analyzer.execute_coordinated_rename(rename_plan)
    print(f"Coordinated rename: {result.success}")
```

### 5. Staging Environment Manager
```python
from dataflow.migrations.staging_environment_manager import StagingEnvironmentManager

# Create production-like staging environment
staging_manager = StagingEnvironmentManager(connection_manager)

# Replicate production schema with sample data
staging_env = await staging_manager.create_staging_environment(
    environment_name="migration_test_001",
    data_sampling_strategy={
        "strategy": "representative",  # or "random", "stratified"
        "sample_percentage": 10,
        "preserve_referential_integrity": True,
        "max_rows_per_table": 100000
    },
    resource_limits={
        "max_storage_gb": 50,
        "max_duration_hours": 2
    }
)

print(f"Staging environment: {staging_env.environment_id}")
print(f"Connection: {staging_env.connection_info.database_url}")

try:
    # Test migration in staging
    test_result = await staging_manager.test_migration_in_staging(
        staging_env,
        migration_plan=your_migration_plan,
        validation_checks=True,
        performance_monitoring=True
    )

    print(f"Staging test: {test_result.success}")
    print(f"Performance impact: {test_result.performance_metrics}")
    print(f"Data integrity: {test_result.data_integrity_check}")

finally:
    # Always cleanup (automatic timeout protection)
    await staging_manager.cleanup_staging_environment(staging_env)
```

### 6. Migration Lock Manager (NEW)
```python
from dataflow.migrations.concurrent_access_manager import MigrationLockManager

# Prevent concurrent migrations
lock_manager = MigrationLockManager(connection_manager)

# Acquire exclusive migration lock
async with lock_manager.acquire_migration_lock(
    lock_scope="schema_modification",  # or "table_modification", "data_modification"
    timeout_seconds=300,
    operation_description="Add NOT NULL column to users table",
    lock_metadata={"table": "users", "operation": "add_column"}
) as migration_lock:

    print(f"🔒 Migration lock acquired: {migration_lock.lock_id}")
    print(f"Lock scope: {migration_lock.scope}")

    # Execute migration safely - no other migrations can interfere
    migration_result = await execute_your_migration()

    print("✅ Migration completed under lock protection")
    # Lock automatically released when context exits

# Lock status monitoring
active_locks = await lock_manager.get_active_locks()
print(f"Active migration locks: {len(active_locks)}")
for lock in active_locks:
    print(f"  - {lock.operation_description} (acquired: {lock.acquired_at})")
```

### 7. Validation Checkpoint Manager
```python
from dataflow.migrations.validation_checkpoints import ValidationCheckpointManager

# Multi-stage validation system
validation_manager = ValidationCheckpointManager(connection_manager)

# Define comprehensive validation checkpoints
checkpoints = [
    {
        "stage": "pre_migration",
        "validators": [
            "schema_integrity",
            "foreign_key_consistency",
            "data_quality",
            "performance_baseline"
        ],
        "required": True
    },
    {
        "stage": "during_migration",
        "validators": [
            "transaction_health",
            "performance_monitoring",
            "connection_stability"
        ],
        "required": True
    },
    {
        "stage": "post_migration",
        "validators": [
            "schema_validation",
            "data_integrity",
            "constraint_validation",
            "performance_regression_check"
        ],
        "required": True
    }
]

# Execute migration with checkpoint validation
validation_result = await validation_manager.execute_with_validation(
    migration_operation=your_migration_function,
    checkpoints=checkpoints,
    rollback_on_failure=True,
    detailed_reporting=True
)

if validation_result.all_checkpoints_passed:
    print("✅ Migration completed - all validation checkpoints passed")
    print(f"Total checkpoints: {len(validation_result.checkpoint_results)}")
else:
    print(f"❌ Migration failed at: {validation_result.failed_checkpoint}")
    print(f"Failure reason: {validation_result.failure_reason}")
    print(f"Rollback executed: {validation_result.rollback_completed}")
```

### 8. Schema State Manager
```python
from dataflow.migrations.schema_state_manager import SchemaStateManager

# Track and manage schema evolution
schema_manager = SchemaStateManager(connection_manager)

# Create comprehensive schema snapshot
snapshot = await schema_manager.create_schema_snapshot(
    description="Before user table restructuring migration",
    include_data_checksums=True,
    include_performance_metrics=True,
    include_constraint_validation=True
)

print(f"📸 Schema snapshot: {snapshot.snapshot_id}")
print(f"Tables captured: {len(snapshot.table_definitions)}")
print(f"Constraints tracked: {len(snapshot.constraint_definitions)}")
print(f"Indexes captured: {len(snapshot.index_definitions)}")

# Track schema changes during migration
change_tracker = await schema_manager.start_change_tracking(
    baseline_snapshot=snapshot,
    track_performance_impact=True
)

# Execute your migration
migration_result = await your_migration_function()

# Generate comprehensive evolution report
evolution_report = await schema_manager.generate_evolution_report(
    from_snapshot=snapshot,
    to_current_state=True,
    include_impact_analysis=True,
    include_recommendations=True
)

print(f"📊 Schema changes detected: {len(evolution_report.schema_changes)}")
for change in evolution_report.schema_changes:
    print(f"  - {change.change_type}: {change.description}")
    print(f"    Impact level: {change.impact_level}")
    print(f"    Affected objects: {len(change.affected_objects)}")

# Schema rollback capability
if need_rollback:
    rollback_result = await schema_manager.rollback_to_snapshot(snapshot)
    print(f"Schema rollback: {rollback_result.success}")
```

### NOT NULL Column Addition
```python
from dataflow.migrations.not_null_handler import NotNullColumnHandler, ColumnDefinition, DefaultValueType

# Enhanced NOT NULL column handler with 6 strategies
handler = NotNullColumnHandler(connection_manager)

# Strategy 1: Static Default (fastest)
static_column = ColumnDefinition(
    name="status",
    data_type="VARCHAR(20)",
    default_value="active",
    default_type=DefaultValueType.STATIC
)

# Strategy 2: Computed Default (business logic)
computed_column = ColumnDefinition(
    name="user_tier",
    data_type="VARCHAR(10)",
    default_expression="CASE WHEN account_value > 10000 THEN 'premium' ELSE 'standard' END",
    default_type=DefaultValueType.COMPUTED
)

# Strategy 3: Function-based (system values)
function_column = ColumnDefinition(
    name="created_at",
    data_type="TIMESTAMP",
    default_expression="CURRENT_TIMESTAMP",
    default_type=DefaultValueType.FUNCTION
)

# Comprehensive planning with risk assessment
plan = await handler.plan_not_null_addition("users", computed_column)
print(f"Execution strategy: {plan.execution_strategy}")
print(f"Estimated duration: {plan.estimated_duration:.2f}s")
print(f"Risk level: {plan.risk_assessment.risk_level}")

# Multi-level validation
validation = await handler.validate_addition_safety(plan)
if validation.is_safe:
    result = await handler.execute_not_null_addition(plan)
    print(f"Column added in {result.execution_time:.2f}s")
    print(f"Rows affected: {result.affected_rows}")
else:
    print(f"Validation failed: {validation.issues}")
    for mitigation in validation.suggested_mitigations:
        print(f"  Suggestion: {mitigation}")
```

### Column Removal
```python
from dataflow.migrations.column_removal_manager import ColumnRemovalManager, BackupStrategy

# Enhanced column removal with comprehensive dependency analysis
removal_manager = ColumnRemovalManager(connection_manager)

# Plan removal with full dependency analysis
plan = await removal_manager.plan_column_removal(
    table="users",
    column="legacy_field",
    backup_strategy=BackupStrategy.COLUMN_ONLY,
    dependency_resolution_strategy="automatic",  # or "manual", "skip_unsafe"
    include_impact_analysis=True
)

print(f"Dependencies found: {len(plan.dependencies)}")
print(f"Removal stages: {len(plan.removal_stages)}")
print(f"Estimated duration: {plan.estimated_duration:.2f}s")

# Advanced safety validation
validation = await removal_manager.validate_removal_safety(plan)
if not validation.is_safe:
    print(f"❌ Blocked by {len(validation.blocking_dependencies)} dependencies:")
    for dep in validation.blocking_dependencies:
        print(f"  - {dep.object_name} ({dep.dependency_type.value})")
        print(f"    Impact: {dep.impact_level.value}")
    return

# Production-safe execution
plan.confirmation_required = True
plan.stop_on_warning = True
plan.validate_after_each_stage = True
plan.stage_timeout = 1800  # 30 minutes per stage
plan.backup_strategy = BackupStrategy.TABLE_SNAPSHOT

result = await removal_manager.execute_safe_removal(plan)
if result.result == RemovalResult.SUCCESS:
    print(f"✅ Column removed successfully")
    print(f"Stages completed: {len(result.stages_completed)}")
    print(f"Total duration: {result.total_duration:.2f}s")
else:
    print(f"❌ Removal failed: {result.error_message}")
    if result.rollback_executed:
        print("🔄 Automatic rollback completed")
```

## Complete Enterprise Migration Workflow

```python
from dataflow.migrations.integrated_risk_assessment_system import IntegratedRiskAssessmentSystem

async def enterprise_migration_workflow(
    operation_type: str,
    table_name: str,
    migration_details: dict,
    connection_manager
) -> bool:
    """Complete enterprise migration with all safety systems."""

    # Step 1: Integrated Risk Assessment
    risk_system = IntegratedRiskAssessmentSystem(connection_manager)

    comprehensive_assessment = await risk_system.perform_complete_assessment(
        operation_type=operation_type,
        table_name=table_name,
        operation_details=migration_details,
        include_performance_analysis=True,
        include_dependency_analysis=True,
        include_fk_analysis=True
    )

    print(f"🎯 Risk Assessment:")
    print(f"  Overall Risk: {comprehensive_assessment.overall_risk_level}")
    print(f"  Risk Score: {comprehensive_assessment.risk_score}/100")

    # Step 2: Generate Comprehensive Mitigation Plan
    mitigation_plan = await risk_system.generate_comprehensive_mitigation_plan(
        assessment=comprehensive_assessment,
        business_requirements={
            "max_downtime_minutes": 5,
            "rollback_time_limit_minutes": 10,
            "data_consistency_critical": True,
            "performance_degradation_acceptable": 5  # 5% max
        }
    )

    print(f"🛡️ Mitigation strategies: {len(mitigation_plan.strategies)}")

    # Step 3: Create and Test in Staging Environment
    staging_manager = StagingEnvironmentManager(connection_manager)
    staging_env = await staging_manager.create_staging_environment(
        environment_name=f"migration_{int(time.time())}",
        data_sampling_strategy={"strategy": "representative", "sample_percentage": 5}
    )

    try:
        # Test migration in staging
        staging_test = await staging_manager.test_migration_in_staging(
            staging_env,
            migration_plan={
                "operation": operation_type,
                "table": table_name,
                "details": migration_details
            },
            validation_checks=True,
            performance_monitoring=True
        )

        if not staging_test.success:
            print(f"❌ Staging test failed: {staging_test.failure_reason}")
            return False

        print(f"✅ Staging test passed - safe to proceed")
        print(f"📊 Performance impact: {staging_test.performance_metrics}")

        # Step 4: Acquire Migration Lock for Production
        lock_manager = MigrationLockManager(connection_manager)

        async with lock_manager.acquire_migration_lock(
            lock_scope="table_modification",
            timeout_seconds=600,
            operation_description=f"{operation_type} on {table_name}"
        ) as migration_lock:

            print(f"🔒 Migration lock acquired: {migration_lock.lock_id}")

            # Step 5: Execute with Multi-Stage Validation
            validation_manager = ValidationCheckpointManager(connection_manager)

            validation_result = await validation_manager.execute_with_validation(
                migration_operation=lambda: execute_actual_migration(
                    operation_type, table_name, migration_details
                ),
                checkpoints=[
                    {
                        "stage": "pre_migration",
                        "validators": ["schema_integrity", "fk_consistency", "data_quality"]
                    },
                    {
                        "stage": "during_migration",
                        "validators": ["transaction_health", "performance_monitoring"]
                    },
                    {
                        "stage": "post_migration",
                        "validators": ["data_integrity", "performance_validation", "constraint_validation"]
                    }
                ],
                rollback_on_failure=True
            )

            if validation_result.all_checkpoints_passed:
                print("✅ Enterprise migration completed successfully")
                return True
            else:
                print(f"❌ Migration failed: {validation_result.failure_details}")
                print(f"🔄 Rollback executed: {validation_result.rollback_completed}")
                return False

    finally:
        # Step 6: Cleanup Staging Environment
        await staging_manager.cleanup_staging_environment(staging_env)

# Usage Example
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

print(f"Migration result: {'SUCCESS' if success else 'FAILED'}")
```

## TDD Mode & Testing (v0.7.10+)

> **See Skill**: [`dataflow-testing`](../../skills/02-dataflow/dataflow-testing.md) for TDD patterns and test fixtures.

### Test Mode API Overview

DataFlow v0.7.10+ provides a comprehensive Test Mode API for production-grade async testing with automatic connection pool management and cleanup.

**Key Features**:
- **Auto-detection**: Automatically enables test mode when pytest is detected
- **Global control**: Enable/disable test mode across all instances
- **Connection cleanup**: Graceful pool cleanup methods with metrics
- **Thread-safe**: Full concurrency support with RLock protection
- **Zero overhead**: <150ms per test with aggressive cleanup

### Test Mode Configuration

**Three-Level Priority System**:
1. **Explicit parameter** (highest priority)
   ```python
   db = DataFlow("postgresql://...", test_mode=True)
   ```

2. **Global class method** (medium priority)
   ```python
   DataFlow.enable_test_mode()  # All instances use test mode
   db = DataFlow("postgresql://...")
   ```

3. **Auto-detection** (lowest priority, default)
   ```python
   db = DataFlow("postgresql://...")  # Detects pytest automatically
   ```

### Cleanup Methods (Async)

**cleanup_stale_pools()**: Remove pools from closed event loops
```python
metrics = await db.cleanup_stale_pools()
# Returns: {
#   'stale_pools_found': 2,
#   'stale_pools_cleaned': 2,
#   'cleanup_failures': 0,
#   'cleanup_errors': [],
#   'cleanup_duration_ms': 45.2
# }
```

**cleanup_all_pools()**: Remove all connection pools (teardown)
```python
metrics = await db.cleanup_all_pools(force=False)
# Returns: {
#   'total_pools': 5,
#   'pools_cleaned': 5,
#   'cleanup_failures': 0,
#   'cleanup_errors': [],
#   'cleanup_duration_ms': 98.1,
#   'forced': False
# }
```

**get_cleanup_metrics()**: Get pool lifecycle metrics (sync)
```python
metrics = db.get_cleanup_metrics()
# Returns: {
#   'active_pools': 3,
#   'total_pools_created': 10,
#   'test_mode_enabled': True,
#   'aggressive_cleanup_enabled': True,
#   'pool_keys': [...],
#   'event_loop_ids': [...]
# }
```

### Recommended Fixture Pattern

```python
# tests/conftest.py
import pytest
from dataflow import DataFlow

@pytest.fixture(scope="function")
async def db():
    """DataFlow with automatic cleanup."""
    db = DataFlow("postgresql://...", test_mode=True)
    yield db
    await db.cleanup_all_pools()

# tests/test_user.py
@pytest.mark.asyncio
async def test_user_create(db):
    @db.model
    class User:
        id: str
        name: str

    # Test operations...
    # Cleanup automatic via fixture
```

### Global Test Mode Pattern

```python
# tests/conftest.py
@pytest.fixture(scope="session", autouse=True)
def enable_test_mode():
    DataFlow.enable_test_mode()
    yield
    DataFlow.disable_test_mode()

# All tests inherit test mode automatically
```

### Performance Impact

| Operation | Overhead | Frequency |
|-----------|----------|-----------|
| Test mode detection | <1ms | Once per instance |
| `cleanup_stale_pools()` | <50ms | Per fixture |
| `cleanup_all_pools()` | <100ms | Per fixture |
| `get_cleanup_metrics()` | <1ms | As needed |

**Total Impact**: <150ms per test (acceptable for test suites)

### AsyncSQLDatabaseNode Enhancements

**_cleanup_closed_loop_pools()** (async, class method):
```python
# Automatically removes pools from closed event loops
count = await AsyncSQLDatabaseNode._cleanup_closed_loop_pools()
# Returns: Number of pools cleaned
```

**clear_shared_pools()** (async, enhanced with metrics):
```python
# Clear all shared pools with detailed metrics
metrics = await AsyncSQLDatabaseNode.clear_shared_pools(graceful=True)
# Returns: {
#   'total_pools': 10,
#   'pools_cleaned': 10,
#   'cleanup_failures': 0,
#   'cleanup_errors': []
# }
```

### Troubleshooting Common Issues

**Issue: "Event loop is closed" errors**
```python
# Solution: Use function-scoped fixture with cleanup
@pytest.fixture(scope="function")
async def db():
    db = DataFlow("postgresql://...", test_mode=True)
    yield db
    await db.cleanup_all_pools()
```

**Issue: Pool leaks between tests**
```python
# Solution: Check cleanup metrics
metrics = await db.cleanup_all_pools()
if metrics['cleanup_failures'] > 0:
    print(f"⚠️ Failed cleanups: {metrics['cleanup_errors']}")
```

**Issue: "Pool attached to different loop"**
```python
# Solution: Use fresh event loop per test
@pytest.fixture(scope="function")
def event_loop():
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
```

### See Also
- **Complete Testing Guide**: `/apps/kailash-dataflow/docs/testing/README.md`
- **Fixture Patterns**: `/apps/kailash-dataflow/docs/testing/fixture-patterns.md`
- **ADR-017 Quick Reference**: `/apps/kailash-dataflow/adr/ADR-017-API-QUICK-REFERENCE.md`

## 📊 Performance Characteristics (Updated v0.4.7+)

DataFlow Phase 1A/1B improvements significantly reduce overhead while maintaining functionality.

**Instance Creation**:
- **Before v0.4.7**: ~700ms per DataFlow instance
- **After v0.4.7**: <50ms per instance (14x faster)
- **Improvement**: 93% reduction via schema cache and deferred operations

**CRUD Operations**:
- **First operation** (cache miss): ~1500ms with migration checks
- **Subsequent operations** (cache hit): ~1ms (99% faster)
- **Improvement**: 91-99% via schema cache (v0.7.3+)

**Memory Overhead**:
- **Per instance**: ~20MB with models + <1KB per cached table
- **Schema cache**: <1KB per cached table
- **Connection pools**: Shared across instances (event loop isolated)

**Schema Operations**:
- **Model registration**: Synchronous, instant
- **Table creation**: Deferred to first use (not registration)
- **Migration checks**: Cached, 91-99% improvement after first check

**Error Enhancement Overhead**:
- **FULL mode**: <5ms per error (development)
- **MINIMAL mode**: <1ms per error (staging)
- **DISABLED mode**: 0ms (production)

**Inspector Overhead**:
- **Workflow analysis**: <10ms for 100-node workflows
- **Parameter tracing**: <1ms per trace
- **Connection validation**: <5ms for 500 connections

**CLI Commands Overhead**:
- **analyze**: <50ms for complex workflows
- **debug**: <100ms with full diagnostics
- **validate**: <25ms for structure checks

## 🐛 Debugging Tips (Updated v0.4.7+)

DataFlow Phase 1A/1B introduces enhanced debugging tools beyond basic inspection.

**Step 1: Use Inspector First**
```python
from dataflow.platform.inspector import Inspector

# ALWAYS start with Inspector
inspector = Inspector(workflow)

# Quick health check
validation = inspector.validate_connections()
if not validation["is_valid"]:
    print(f"Found {len(validation['errors'])} errors")
    for error in validation["errors"]:
        print(f"  - {error}")
```

**Step 2: Check Error Codes**
```python
# Enhanced errors show DF-XXX codes
try:
    results = runtime.execute(workflow.build())
except Exception as e:
    if "DF-" in str(e):
        # Extract error code and lookup solution
        error_code = str(e).split(":")[0]
        print(f"Error code: {error_code}")
        print(f"Documentation: https://docs.kailash.dev/dataflow/errors/{error_code}")
```

**Step 3: Use CLI Commands**
```bash
# Validate workflow structure
dataflow validate my_workflow.py --strict

# Debug specific node
dataflow debug my_workflow.py --node "problematic_node"

# Analyze performance bottlenecks
dataflow perf my_workflow.py --profile
```

**Step 4: Verify Node-Instance Coupling**
```python
# Check node-instance coupling (rare issue)
node = db._nodes["UserCreateNode"]()
print(f"Bound to: {node.dataflow_instance}")
print(f"Correct: {node.dataflow_instance is db}")
```

**Step 5: Verify String ID Preservation**
```python
# Verify string ID preservation (rare issue)
results = runtime.execute(workflow.build())
print(f"ID type: {type(results['create_user']['id'])}")
print(f"ID value: {results['create_user']['id']}")
```

**Common Debugging Patterns**:

**Pattern 1: Connection Issues**
```python
# Use Inspector to trace parameter flow
inspector = Inspector(workflow)
trace = inspector.trace_parameter("target_node", "missing_param")

if trace.source is None:
    print("Parameter not connected! Add connection:")
    print(f"  workflow.add_connection(source_node, 'param', 'target_node', 'missing_param')")
```

**Pattern 2: Type Mismatches**
```python
# Inspector shows type mismatches in connections
validation = inspector.validate_connections()
for error in validation["errors"]:
    if "type mismatch" in error["reason"].lower():
        print(f"Type mismatch: {error['from_node']}.{error['from_param']} → {error['to_node']}.{error['to_param']}")
        print(f"Expected: {error['expected_type']}, Got: {error['actual_type']}")
```

**Pattern 3: Performance Issues**
```bash
# Use CLI perf command to identify bottlenecks
dataflow perf my_workflow.py --profile --output report.json

# Analyze report:
# - Long-running nodes
# - Network-bound operations
# - Database query optimization opportunities
```

## Critical Limitations & Workarounds

### PostgreSQL Array Types (v0.8.0+ - FULLY SUPPORTED!)
```python
# ✅ SUPPORTED (v0.8.0+) - Native PostgreSQL arrays with opt-in flag
@db.model
class BlogPost:
    title: str
    content: str
    tags: List[str]  # Fully supported with __dataflow__ flag!

    __dataflow__ = {
        'use_native_arrays': True  # Opt-in for PostgreSQL native arrays
    }

# ⚠️ For cross-database compatibility (MySQL, SQLite)
@db.model
class BlogPost:
    title: str
    content: str
    tags_json: Dict[str, Any] = {}  # Use JSON for cross-DB support
```

### JSON Field Behavior
```python
# ❌ WRONG - JSON fields are returned as strings, not parsed objects
result = results["create_config"]
config = result["config"]["database"]["host"]  # FAILS - config is a string

# ✅ CORRECT - Handle JSON as string or parse if needed
result = results["create_config"]
config_str = result["config"]  # This is a string representation
if isinstance(config_str, str):
    import json
    config = json.loads(config_str)  # Parse if needed
```

### Result Access Patterns
```python
# Results can vary between direct access and wrapper access
result = results[node_id]

# Check both patterns:
if isinstance(result, dict) and "output" in result:
    data = result["output"]  # Wrapper format
else:
    data = result  # Direct format
```

## Production Configuration Patterns

### Development vs Production Setup
```python
# Development (auto-migration safe)
db = DataFlow(auto_migrate=True)  # Default, preserves existing data

# Production (explicit control)
db = DataFlow(
    auto_migrate=False,
    existing_schema_mode=True  # Use existing schema
)
```

## 🔧 Troubleshooting Common Issues (NEW in v0.4.7+)

DataFlow Phase 1A/1B provides diagnostic tools to resolve issues quickly.

**Issue 1: Workflow Builds But Produces No Results**

**Symptoms**: `runtime.execute(workflow.build())` succeeds but results are empty or None.

**Solution**:
```python
# Step 1: Use Inspector to validate connections
inspector = Inspector(workflow)
validation = inspector.validate_connections()

if not validation["is_valid"]:
    print("Connection errors found:")
    for error in validation["errors"]:
        print(f"  - {error}")

# Step 2: Use CLI validate command
# dataflow validate my_workflow.py --strict
```

**Issue 2: Missing Parameter Error (DF-101)**

**Symptoms**: Error shows "DF-101: Missing Required Parameter"

**Solution**:
```python
# ErrorEnhancer shows exactly which parameter is missing
# Follow the 3 solutions provided in error message:

# Solution 1: Add missing parameter
data = {
    "id": "user-123",  # <- ADD THIS
    "name": "Alice",
    "email": "alice@example.com"
}

# Solution 2: Check model definition
# Verify all required fields are present

# Solution 3: Use Inspector to validate
inspector = Inspector(workflow)
trace = inspector.trace_parameter("create", "id")
```

**Issue 3: Slow First Operation**

**Symptoms**: First database operation takes ~1500ms, subsequent operations are fast.

**Solution**:
```python
# This is expected behavior! Schema cache causes this pattern:
# - First operation: Cache miss (~1500ms) - includes migration checks
# - Subsequent operations: Cache hit (~1ms) - 99% faster

# To verify schema cache is working:
metrics = db._schema_cache.get_metrics()
print(f"Hit rate: {metrics['hit_rate']:.2%}")  # Should be >90% after warm-up
```

**Issue 4: Event Loop Closed Errors**

**Symptoms**: "Event loop is closed" or "Pool attached to different loop"

**Solution**:
```python
# Use test mode with automatic cleanup
db = DataFlow("postgresql://...", test_mode=True)

# In pytest fixture:
@pytest.fixture(scope="function")
async def db():
    db = DataFlow("postgresql://...", test_mode=True)
    yield db
    await db.cleanup_all_pools()  # Clean up after each test
```

**Issue 5: Connection Type Mismatch (DF-201)**

**Symptoms**: Error shows "DF-201: Connection Type Mismatch"

**Solution**:
```python
# ErrorEnhancer shows expected vs actual types
# Use Inspector to trace the issue:

inspector = Inspector(workflow)
validation = inspector.validate_connections()

for error in validation["errors"]:
    if "type mismatch" in error["reason"].lower():
        print(f"Mismatch: {error['from_node']}.{error['from_param']}")
        print(f"Expected: {error['expected_type']}")
        print(f"Got: {error['actual_type']}")
        # Fix the type in the source node
```

**Quick Diagnostic Commands**:
```bash
# Full workflow validation
dataflow validate my_workflow.py --strict

# Debug specific node
dataflow debug my_workflow.py --node "problematic_node"

# Analyze performance
dataflow perf my_workflow.py --profile

# Check workflow structure
dataflow analyze my_workflow.py
```

**Troubleshooting Flowchart**:
1. **Start**: Is workflow executing at all? → NO → Check error message for DF-XXX code
2. **Results empty?** → YES → Use Inspector to validate connections
3. **Slow performance?** → YES → Use `dataflow perf` to identify bottlenecks
4. **Type errors?** → YES → Use Inspector to check connection types
5. **Event loop errors?** → YES → Enable test_mode with cleanup

## Key Rules

### Always
- Use PostgreSQL for production, SQLite for development (both fully supported)
- Set `existing_schema_mode=True` for existing databases (CRITICAL SAFETY)
- Use `use_real_inspection=True` for real schema discovery (PostgreSQL only)
- Use bulk operations for >100 records
- Use connections for dynamic values
- Follow 3-tier testing: Unit/Integration/E2E with real infrastructure
- Enable `tdd_mode=True` for <100ms test execution with automatic rollback
- Use TDD fixtures (`tdd_dataflow`, `tdd_test_context`) for test isolation
- Trust that auto_migrate=True preserves data (verified safe)
- **NEW: Perform risk assessment for all schema modifications in production**
- **NEW: Use appropriate migration safety level based on operation risk**
- **NEW: Test high-risk migrations in staging environments**
- **NEW: Use migration locks for concurrent migration prevention**
- **NEW: Validate dependencies before column/table operations**
- **NEW: Monitor migration performance and rollback capabilities**

### Never
- Instantiate models directly (`User()`)
- Use `${}` template syntax
- Worry about datetime conversion - now automatic (v0.6.4+)
- Skip safety checks in production
- Expect MySQL execution in alpha (SQLite works fine!)
- Use mocking in Tier 2-3 tests (NO MOCKING policy enforced)
- Use DROP SCHEMA CASCADE for test cleanup (use TDD savepoints instead)
- Use PostgreSQL array types (`List[str]` fields) - causes parameter type issues
- Assume JSON fields are returned as parsed objects - they return as strings
- Worry about auto_migrate=True dropping tables (it won't)
- **NEW: Skip risk assessment for CRITICAL or HIGH risk migrations**
- **NEW: Execute schema changes without dependency analysis**
- **NEW: Run concurrent migrations without lock coordination**
- **NEW: Drop columns/tables without checking foreign key dependencies**
- **NEW: Ignore staging test failures in enterprise workflows**
- **NEW: Skip validation checkpoints for production migrations**

## Migration Decision Matrix

| Migration Type | Risk Level | Required Tools | Recommended Pattern | Safety Level |
|---------------|------------|----------------|---------------------|-------------|
| **Add nullable column** | LOW | Basic validation | Direct execution | Level 1 |
| **Add NOT NULL column** | MEDIUM | NotNullHandler + validation | Plan → Validate → Execute | Level 2 |
| **Drop column** | HIGH | DependencyAnalyzer + RiskEngine | Full enterprise workflow | Level 3 |
| **Rename column** | MEDIUM | Dependency analysis + validation | Staging test + validation | Level 2 |
| **Change column type** | HIGH | Risk assessment + mitigation | Staging + enterprise workflow | Level 3 |
| **Rename table** | CRITICAL | TableRenameAnalyzer + FK analysis | Full enterprise protocol | Level 3 |
| **Drop table** | CRITICAL | All migration systems | Maximum safety protocol | Level 3 |
| **Add foreign key** | MEDIUM | FK analyzer + validation | FK-aware pattern | Level 2 |
| **Drop foreign key** | HIGH | FK impact analysis + risk engine | Enterprise workflow | Level 3 |
| **Add index** | LOW | Performance validation | Basic execution | Level 1 |
| **Drop index** | MEDIUM | Dependency + performance analysis | Validation required | Level 2 |

## Core Decision Matrix

| Need | Use |
|------|-----|
| Simple CRUD | Basic nodes |
| Bulk import | BulkCreateNode |
| Complex queries | ListNode + MongoDB filters |
| Existing database | existing_schema_mode=True |
| Dynamic models | register_schema_as_models() |
| Cross-session models | reconstruct_models_from_registry() |
| **Schema changes** | **Enterprise migration system** |
| **Risk assessment** | **RiskAssessmentEngine** |
| **Safe migrations** | **Complete enterprise workflow** |
| **FK operations** | **ForeignKeyAnalyzer** |
| **Table restructuring** | **TableRenameAnalyzer + staging** |

## Documentation Quick Links

> **For detailed capabilities, API reference, and examples**: See [DataFlow README](../../sdk-users/apps/dataflow/README.md) and [complete documentation](../../sdk-users/apps/dataflow/docs/).

### Integration Points

#### With Nexus (CRITICAL UPDATE - v0.4.6+)

**⚠️ CRITICAL: Prevent blocking and slow startup when integrating with Nexus**

```python
# CORRECT: Fast, non-blocking integration pattern
from nexus import Nexus
from dataflow import DataFlow

# Step 1: Create Nexus FIRST with auto_discovery=False
app = Nexus(
    api_port=8000,
    mcp_port=3001,
    auto_discovery=False  # CRITICAL: Prevents infinite blocking
)

# Step 2: Create DataFlow with optimized settings
db = DataFlow(
    database_url="postgresql://...",
    enable_model_persistence=False,  # No workflow execution during init
    auto_migrate=False,
    enable_caching=True,  # Keep performance features
    enable_metrics=True
)

# Step 3: Register models (now instant!)
@db.model
class User:
    id: str
    email: str

# Step 4: Manually register workflows
from kailash.workflow.builder import WorkflowBuilder
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"email": "{{email}}"})
app.register("create_user", workflow.build())
```

**Why These Settings Are Critical:**
- `auto_discovery=False`: Prevents Nexus from re-importing DataFlow models (causes infinite loop)
- `enable_model_persistence=False`: Prevents database writes during initialization
- `auto_migrate=False`: Skips migration checks during startup

**What You Keep:**
- ✅ All CRUD operations work normally
- ✅ All 11 generated nodes per model
- ✅ Connection pooling, caching, metrics
- ✅ Multi-channel access (API, CLI, MCP)

**What You Lose:**
- ❌ Model persistence across restarts
- ❌ Automatic migration tracking
- ❌ Runtime model discovery

**Integration Documentation:**
- 📚 [Main Integration Guide](../../sdk-users/guides/dataflow-nexus-integration.md) - Comprehensive guide with 8 use cases
- 🚀 [Full Features Configuration](../../sdk-users/apps/dataflow/docs/integration/dataflow-nexus-full-features.md) - All features enabled (10-30s startup)
- 🔍 [Blocking Issue Analysis](../../sdk-users/apps/dataflow/docs/integration/nexus-blocking-issue-analysis.md) - Root cause analysis
- 💡 [Technical Solution](../../sdk-users/apps/nexus/docs/technical/dataflow-integration-solution.md) - Complete solution details
- 🧪 [Working Examples](../../sdk-users/apps/nexus/examples/dataflow-integration/) - Tested code examples

#### With Core SDK
- All DataFlow nodes are Kailash nodes
- Use in standard WorkflowBuilder patterns
- Compatible with all SDK features
- See: [SDK Integration Patterns](../../sdk-users/guides/dataflow-sdk-integration.md)

## Enterprise Migration Checklist

### Pre-Migration Assessment (Required)
- [ ] **Risk Analysis**: Use RiskAssessmentEngine for comprehensive risk scoring
- [ ] **Dependency Check**: Run DependencyAnalyzer to identify all affected database objects
- [ ] **FK Analysis**: Use ForeignKeyAnalyzer for referential integrity impact assessment
- [ ] **Mitigation Planning**: Generate risk reduction strategies with MitigationStrategyEngine
- [ ] **Staging Environment**: Create production-like staging environment for validation
- [ ] **Performance Baseline**: Capture current performance metrics for comparison

### Migration Execution (Required)
- [ ] **Lock Acquisition**: Acquire appropriate migration lock scope to prevent conflicts
- [ ] **Staging Test**: Validate complete migration workflow in staging first
- [ ] **Validation Checkpoints**: Execute with multi-stage validation and rollback capability
- [ ] **Performance Monitoring**: Track execution metrics and resource utilization
- [ ] **Progress Logging**: Maintain detailed audit trail throughout migration
- [ ] **Rollback Readiness**: Ensure rollback procedures are tested and available

### Post-Migration Validation (Required)
- [ ] **Schema Integrity**: Verify all table structures, constraints, and relationships
- [ ] **Data Integrity**: Check referential integrity and data consistency
- [ ] **Performance Validation**: Compare query performance against baseline metrics
- [ ] **Application Testing**: Validate application functionality with new schema
- [ ] **Documentation Update**: Update schema documentation and migration history
- [ ] **Resource Cleanup**: Release migration locks and cleanup staging environments
- [ ] **Monitoring Setup**: Enhanced monitoring for post-migration performance tracking

---

## For Basic Patterns

See the [DataFlow Skills](../../skills/02-dataflow/) for:
- Quick start guides ([`dataflow-quickstart`](../../skills/02-dataflow/dataflow-quickstart.md))
- Basic CRUD operations ([`dataflow-crud-operations`](../../skills/02-dataflow/dataflow-crud-operations.md))
- Simple queries ([`dataflow-queries`](../../skills/02-dataflow/dataflow-queries.md))
- Standard configurations ([`dataflow-models`](../../skills/02-dataflow/dataflow-models.md))
- Common patterns ([`dataflow-bulk-operations`](../../skills/02-dataflow/dataflow-bulk-operations.md), [`dataflow-transactions`](../../skills/02-dataflow/dataflow-transactions.md))
- Nexus integration ([`dataflow-nexus-integration`](../../skills/02-dataflow/dataflow-nexus-integration.md))
does
