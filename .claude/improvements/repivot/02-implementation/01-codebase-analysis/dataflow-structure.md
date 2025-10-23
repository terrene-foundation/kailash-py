# DataFlow Structure Analysis

**Purpose:** Understand DataFlow architecture and identify extension points for repivot

---

## Overview

**DataFlow** = Zero-config database framework built on Core SDK
- **NOT an ORM** - generates workflow nodes from model definitions
- **Auto-generates 9 nodes per model** - CREATE, READ, UPDATE, DELETE, LIST, BULK_CREATE, BULK_UPDATE, BULK_DELETE, BULK_UPSERT
- **Multi-DB support** - PostgreSQL, MySQL, SQLite with 100% parity
- **Enterprise features** - Multi-tenancy, audit logging, encryption

**Version:** 0.6.5
**Location:** `apps/kailash-dataflow/`
**Main Module:** `src/dataflow/`

---

## Directory Structure

```
apps/kailash-dataflow/
├── src/dataflow/
│   ├── core/                    # Core engine
│   │   ├── engine.py           # DataFlow class (main entry point)
│   │   ├── config.py           # Configuration classes
│   │   ├── nodes.py            # NodeGenerator
│   │   └── model_registry.py  # Model persistence
│   │
│   ├── nodes/                  # Generated & specialized nodes
│   │   ├── bulk_create.py      # High-performance bulk operations
│   │   ├── bulk_update.py
│   │   ├── bulk_delete.py
│   │   ├── bulk_upsert.py
│   │   ├── mongodb_nodes.py    # MongoDB support
│   │   ├── vector_nodes.py     # Vector operations
│   │   └── ... (15+ specialized nodes)
│   │
│   ├── features/               # Enterprise features
│   │   ├── bulk.py            # BulkOperations manager
│   │   ├── transactions.py    # TransactionManager
│   │   └── multi_tenant.py    # MultiTenantManager
│   │
│   ├── migrations/            # Auto-migration system
│   │   ├── auto_migration_system.py
│   │   └── schema_state_manager.py
│   │
│   ├── database/             # Database adapters
│   │   └── query_builder.py  # Query construction
│   │
│   ├── utils/                # Utilities
│   │   └── connection.py     # ConnectionManager
│   │
│   ├── validation/           # Validation system
│   ├── optimization/         # Query optimization
│   └── configuration/        # Progressive configuration
│
├── examples/                 # Example usage
├── tests/                    # Comprehensive test suite
└── docs/                     # Documentation
```

---

## Key Components

### 1. DataFlow Engine (core/engine.py - 5157 lines)

**Main Class:** `DataFlow`

**Initialization:**
```python
def __init__(
    self,
    database_url: Optional[str] = None,
    config: Optional[DataFlowConfig] = None,
    pool_size: int = 20,
    multi_tenant: bool = False,
    audit_logging: bool = False,
    auto_migrate: bool = True,
    existing_schema_mode: bool = False,
    **kwargs
):
```

**Key Features:**
- Zero-config mode (uses DATABASE_URL env var)
- Progressive configuration (zero-config → basic → production → enterprise)
- Multi-database support (PostgreSQL, MySQL, SQLite)
- Connection pooling
- TDD mode for testing

**Core Method: @model Decorator:**
```python
@db.model
class User:
    id: str
    name: str
    email: str
```

**What it does:**
1. Registers model with DataFlow
2. Extracts field definitions from annotations
3. Generates 9 CRUD workflow nodes automatically
4. Sets up table mapping (lazy creation)
5. Adds multi-tenant support if enabled
6. Persists model in registry

### 2. Node Generation System (core/nodes.py)

**NodeGenerator Class:**
- Generates CRUD nodes dynamically from model definitions
- Nodes inherit from Core SDK's BaseNode
- Nodes execute via WorkflowBuilder + LocalRuntime
- Each node knows its DataFlow instance (context-aware)

**Generated Nodes (per model):**
1. `{Model}CreateNode` - Single record creation
2. `{Model}ReadNode` - Single record retrieval
3. `{Model}UpdateNode` - Single record update
4. `{Model}DeleteNode` - Single record deletion
5. `{Model}ListNode` - Query multiple records
6. `{Model}BulkCreateNode` - Batch creation
7. `{Model}BulkUpdateNode` - Batch updates
8. `{Model}BulkDeleteNode` - Batch deletions
9. `{Model}BulkUpsertNode` - Batch upserts

**Example Usage:**
```python
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
})
```

### 3. Feature Managers

**BulkOperations (features/bulk.py):**
- High-performance batch operations
- Optimized query generation
- Transaction support

**TransactionManager (features/transactions.py):**
- ACID transactions
- Savepoints
- Rollback support

**MultiTenantManager (features/multi_tenant.py):**
- Automatic tenant isolation
- tenant_id injection
- Row-level security

### 4. Migration System (migrations/)

**AutoMigrationSystem:**
- Automatic schema migrations
- Column additions/removals
- Type changes
- Index management
- Concurrent migration locks

**SchemaStateManager:**
- Tracks schema state
- Detects changes
- Generates migration plans

**Key Design:**
- **Deferred table creation** - Tables created lazily on first access (not at registration)
- **Prevents "Event loop is closed" errors** - Separates sync registration from async migration
- **Safe mode** - existing_schema_mode for production databases

### 5. Connection Management (utils/connection.py)

**ConnectionManager:**
- Connection pooling (configurable size, overflow)
- Connection recycling
- Health checks
- TDD mode support (use test connections)

---

## Extension Points for Repivot

### High Priority: Validation Helpers

**Problem:** Users hit type errors (datetime.isoformat() vs datetime.now())

**Solution:** Add field validation helpers in new package `kailash-dataflow-utils`

**Implementation:**
```python
# New file: packages/kailash-dataflow-utils/dataflow_utils/fields.py

from datetime import datetime
from typing import Any, Optional
import json

class TimestampField:
    """Helper for datetime fields - prevents isoformat() errors."""

    @staticmethod
    def now() -> datetime:
        """Return current datetime (not string)."""
        return datetime.now()

    @staticmethod
    def validate(value: Any) -> datetime:
        """Validate and convert to datetime."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        raise ValueError(f"Expected datetime, got {type(value)}")

class JSONField:
    """Helper for JSON fields - handles serialization."""

    @staticmethod
    def dumps(data: dict) -> str:
        """Serialize to JSON string."""
        return json.dumps(data)

    @staticmethod
    def loads(data: str) -> dict:
        """Deserialize from JSON string."""
        return json.loads(data)

    @staticmethod
    def validate(value: Any) -> dict:
        """Validate and convert to dict."""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return json.loads(value)
        raise ValueError(f"Expected dict or JSON string, got {type(value)}")

class UUIDField:
    """Helper for UUID fields - ensures string format."""

    @staticmethod
    def generate() -> str:
        """Generate new UUID string."""
        import uuid
        return str(uuid.uuid4())

    @staticmethod
    def validate(value: Any) -> str:
        """Validate UUID format."""
        import uuid
        if isinstance(value, str):
            uuid.UUID(value)  # Validates format
            return value
        raise ValueError(f"Expected UUID string, got {type(value)}")
```

**Integration with DataFlow:**
```python
# In template code
from dataflow import DataFlow
from kailash_dataflow_utils import TimestampField, UUIDField

db = DataFlow("postgresql://...")

@db.model
class Session:
    id: str  # Use UUIDField.generate()
    created_at: datetime  # Use TimestampField.now()

# In workflow
workflow.add_node("SessionCreateNode", "create", {
    "id": UUIDField.generate(),  # ✅ Correct type
    "created_at": TimestampField.now()  # ✅ Not .isoformat()
})
```

**Changes Needed:**
- **New package:** `kailash-dataflow-utils` (separate PyPI package)
- **No DataFlow core changes** - external helper package
- **Templates use by default** - prevent common errors

### Medium Priority: Auto-Validation Mode

**Problem:** Errors surface after execution (48-hour debugging sessions)

**Solution:** Add pre-execution validation in Quick Mode

**Implementation:**
```python
# New file: src/dataflow/validation/pre_execution.py

class PreExecutionValidator:
    """Validate node parameters before execution."""

    def __init__(self, dataflow: 'DataFlow'):
        self.dataflow = dataflow

    def validate_node(self, node_class: str, params: dict) -> List[str]:
        """
        Validate node parameters against model schema.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Extract model name from node class (e.g., "UserCreateNode" -> "User")
        if not node_class.endswith("Node"):
            return errors

        # Determine operation
        for op in ["Create", "Update", "Delete", "Read", "List"]:
            if node_class.endswith(f"{op}Node"):
                model_name = node_class[:-len(f"{op}Node")]
                operation = op.lower()
                break
        else:
            return errors

        # Get model schema
        model_info = self.dataflow._models.get(model_name)
        if not model_info:
            errors.append(f"Model '{model_name}' not found")
            return errors

        fields = model_info["fields"]

        # Validate parameters
        if operation == "create":
            errors.extend(self._validate_create(params, fields))
        elif operation == "update":
            errors.extend(self._validate_update(params, fields))

        return errors

    def _validate_create(self, params: dict, fields: dict) -> List[str]:
        """Validate create operation parameters."""
        errors = []

        for field_name, field_info in fields.items():
            # Check required fields
            if field_info["required"] and field_name not in params:
                if field_name not in ["created_at", "updated_at"]:  # Auto-managed
                    errors.append(f"Required field '{field_name}' missing")

            # Check types
            if field_name in params:
                value = params[field_name]
                expected_type = field_info["type"]

                # Check for common mistakes
                if expected_type == datetime:
                    if isinstance(value, str):
                        errors.append(
                            f"Field '{field_name}' expects datetime, got string. "
                            f"Did you use .isoformat()? Use datetime.now() instead."
                        )

                if expected_type == dict:
                    if isinstance(value, str):
                        errors.append(
                            f"Field '{field_name}' expects dict, got string. "
                            f"Did you use json.dumps()? Pass dict directly."
                        )

        # Check for auto-managed fields
        if "created_at" in params:
            errors.append("created_at is auto-managed - remove from parameters")
        if "updated_at" in params:
            errors.append("updated_at is auto-managed - remove from parameters")

        return errors

    def _validate_update(self, params: dict, fields: dict) -> List[str]:
        """Validate update operation parameters."""
        errors = []

        # UpdateNode requires specific structure
        if "filter" not in params:
            errors.append("UpdateNode requires 'filter' parameter")
        if "fields" not in params:
            errors.append("UpdateNode requires 'fields' parameter")

        # Validate fields being updated
        if "fields" in params:
            for field_name in params["fields"]:
                if field_name not in fields:
                    errors.append(f"Unknown field '{field_name}'")

                # Check auto-managed
                if field_name in ["created_at", "updated_at"]:
                    errors.append(f"'{field_name}' is auto-managed - cannot update manually")

        return errors
```

**Integration with Quick Mode:**
```python
# In kailash/quick/workflow.py (new file)

class QuickWorkflowBuilder:
    """Quick Mode workflow builder with auto-validation."""

    def __init__(self, dataflow: 'DataFlow'):
        self.dataflow = dataflow
        self.validator = PreExecutionValidator(dataflow)
        self.builder = WorkflowBuilder()

    def add_node(self, node_class: str, node_id: str, params: dict):
        """Add node with validation."""
        # Validate before adding
        errors = self.validator.validate_node(node_class, params)

        if errors:
            # Immediate feedback
            error_msg = f"Validation errors for {node_class}:\n"
            error_msg += "\n".join(f"  - {err}" for err in errors)
            raise ValueError(error_msg)

        # Add to workflow
        self.builder.add_node(node_class, node_id, params)
        return self

    def build(self):
        return self.builder.build()
```

**Changes Needed:**
- **New validation module:** `dataflow/validation/pre_execution.py` (~200 lines)
- **Quick Mode integration:** Use validator in Quick Mode workflow builder
- **Optional for full SDK:** Validation only in Quick Mode (not forced on developers)
- **Better error messages:** AI-friendly, actionable suggestions

### Low Priority: Better Error Messages

**Problem:** Error messages are technical (stack traces), not AI-friendly

**Solution:** Enhance error messages in nodes

**Implementation:**
```python
# In generated nodes (core/nodes.py modification)

class GeneratedCreateNode(BaseNode):
    """Auto-generated create node."""

    def execute(self, params: dict) -> dict:
        try:
            # Existing execution logic
            result = self._execute_create(params)
            return result
        except Exception as e:
            # Enhanced error handling
            error_context = self._build_error_context(e, params)
            raise DataFlowExecutionError(error_context) from e

    def _build_error_context(self, error: Exception, params: dict) -> dict:
        """Build AI-friendly error context."""
        context = {
            "node_class": self.__class__.__name__,
            "model": self.model_name,
            "operation": "create",
            "original_error": str(error),
            "parameters": params,
            "suggestions": []
        }

        # Pattern matching for common errors
        error_str = str(error).lower()

        if "operator does not exist: text = integer" in error_str:
            context["suggestions"].append(
                "Type mismatch detected. Check for:"
                "  - datetime.now().isoformat() → use datetime.now() instead"
                "  - str(number) → use number directly"
                "  - json.dumps(dict) → use dict directly"
            )
            context["likely_cause"] = "Type mismatch in parameters"
            context["fix_pattern"] = "Check parameter types match model definition"

        elif "required" in error_str:
            context["suggestions"].append(
                f"Required field missing. Model '{self.model_name}' requires: {list(self.fields.keys())}"
            )

        elif "created_at" in error_str or "updated_at" in error_str:
            context["suggestions"].append(
                "created_at and updated_at are auto-managed by DataFlow."
                "Remove these from your parameters."
            )

        return context
```

**Changes Needed:**
- **Enhance node execution:** ~100 lines in `core/nodes.py`
- **New exception class:** `DataFlowExecutionError` with structured context
- **Error message templates:** Common patterns with fixes
- **Backward compatible:** Existing error handling still works

---

## DataFlow-Specific Repivot Components

### 1. Template Integration

**How templates will use DataFlow:**
```python
# In templates/saas-starter/models.py

from dataflow import DataFlow
from kailash_dataflow_utils import TimestampField, UUIDField

# AI INSTRUCTION: To add a new model, copy this pattern:
# 1. Use @db.model decorator
# 2. Define fields with type hints
# 3. Auto-generated nodes: {Model}CreateNode, {Model}ReadNode, etc.

db = DataFlow("postgresql://...")  # From env: DATABASE_URL

@db.model
class User:
    """User model with multi-tenancy.

    AI: This generates 9 workflow nodes automatically:
    - UserCreateNode, UserReadNode, UserUpdateNode, etc.

    Usage in workflow:
    workflow.add_node("UserCreateNode", "create_user", {
        "id": UUIDField.generate(),
        "name": "Alice",
        "email": "alice@example.com"
    })
    """
    id: str
    name: str
    email: str
    active: bool = True
    # tenant_id added automatically in multi-tenant mode

@db.model
class Session:
    """Session model for auth.

    AI: Note the field helpers:
    - UUIDField.generate() for id
    - TimestampField.now() for created_at
    """
    id: str
    user_id: str
    token: str
    created_at: datetime
    expires_at: datetime
```

**Template will pre-configure:**
- Database connection (from env)
- Multi-tenancy enabled
- Audit logging enabled
- Common models (User, Session, etc.)

### 2. Quick Mode Integration

**How Quick Mode will use DataFlow:**
```python
# In kailash/quick/db.py (new file)

from dataflow import DataFlow
from .validation import QuickModeValidator

class QuickDB:
    """Quick Mode database abstraction."""

    def __init__(self, url: str = None):
        # Use Quick Mode defaults
        self.dataflow = DataFlow(
            database_url=url,
            auto_migrate=True,
            multi_tenant=False,  # Quick Mode: simple by default
            audit_logging=False,  # Quick Mode: minimal overhead
        )
        self.validator = QuickModeValidator(self.dataflow)

    def model(self, cls):
        """Decorator with validation."""
        # Validate model definition
        errors = self.validator.validate_model(cls)
        if errors:
            raise ValueError(f"Model validation errors:\n" + "\n".join(errors))

        # Register with DataFlow
        return self.dataflow.model(cls)

    # Add convenience methods
    @property
    def users(self):
        """Access User model operations."""
        return ModelOperations(self.dataflow, "User")

    # Dynamic model access
    def __getattr__(self, name):
        """Dynamic model operations (e.g., db.products)."""
        model_name = name.capitalize()
        if model_name in self.dataflow._models:
            return ModelOperations(self.dataflow, model_name)
        raise AttributeError(f"No model '{model_name}' registered")

class ModelOperations:
    """Quick Mode model operations."""

    def __init__(self, dataflow, model_name):
        self.dataflow = dataflow
        self.model_name = model_name

    def create(self, **kwargs):
        """Create a record."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()
        workflow.add_node(f"{self.model_name}CreateNode", "create", kwargs)

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())
        return results["create"]

    def read(self, id: str):
        """Read a record by ID."""
        # Similar implementation
        pass

    def update(self, id: str, **kwargs):
        """Update a record."""
        # Similar implementation
        pass

    def delete(self, id: str):
        """Delete a record."""
        # Similar implementation
        pass
```

**Usage in Quick Mode:**
```python
from kailash.quick import app, db

# Quick Mode: Simple syntax
@db.model
class Product:
    name: str
    price: float

# Automatic operations
db.products.create(name="Widget", price=9.99)
product = db.products.read(id="123")
db.products.update(id="123", price=12.99)
```

### 3. Component Marketplace Integration

**Package: kailash-dataflow-utils**
```
packages/kailash-dataflow-utils/
├── dataflow_utils/
│   ├── __init__.py
│   ├── fields.py         # TimestampField, JSONField, UUIDField
│   ├── validators.py     # Common validators
│   └── mixins.py         # Common model mixins
├── tests/
├── README.md
└── setup.py
```

**Other marketplace components using DataFlow:**
- `kailash-rbac`: Role-based access control (defines Role, Permission models)
- `kailash-audit`: Audit logging (defines AuditLog model)
- `kailash-admin`: Admin dashboard (queries DataFlow models)

---

## Changes Summary

### No Changes Needed
- ✅ Core DataFlow engine (stable, well-designed)
- ✅ Node generation system (works perfectly)
- ✅ Migration system (handles lazy table creation)
- ✅ Connection management (robust)

### New Components (External Packages)
- 📦 `kailash-dataflow-utils` - Field helpers, validators
- 📦 Quick Mode integration - `kailash/quick/db.py`
- 📦 Templates - Pre-configured DataFlow setup

### Minor Enhancements
- 🔧 Error message improvements (~100 lines in `core/nodes.py`)
- 🔧 Validation system (~200 lines in `validation/pre_execution.py`)
- 🔧 Quick Mode defaults (~50 lines configuration)

### Documentation
- 📝 IT teams guide - "DataFlow for Quick Mode"
- 📝 Developer guide - "DataFlow advanced features"
- 📝 Common mistakes - Expanded with validation patterns

---

## Backward Compatibility

**100% backward compatible:**
- All existing DataFlow code continues to work
- New validation is opt-in (Quick Mode only)
- Field helpers are external package
- Error message enhancements preserve original errors

**Version Strategy:**
- Current: 0.6.5
- With enhancements: 0.7.0 (minor version bump)
- No breaking changes

---

## Key Takeaways

**DataFlow is Excellent:**
- Zero-config works brilliantly
- Node generation is elegant
- Enterprise features are production-ready

**What It Needs:**
- Better error messages (AI-friendly)
- Field validation helpers (prevent type errors)
- Quick Mode abstraction (hide complexity for IT teams)

**How to Add:**
- External packages (no core changes)
- Opt-in validation (Quick Mode)
- Enhanced errors (backward compatible)

**DataFlow doesn't need a rewrite - it needs better packaging and error handling for IT teams using AI assistants.**
