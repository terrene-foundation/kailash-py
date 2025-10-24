# Quick Mode Specification

**Purpose:** FastAPI-like simplicity layer that hides Kailash complexity for IT teams

**Priority:** 1 (Critical - Build after templates)
**Estimated Effort:** 160 hours
**Timeline:** Weeks 9-16

---

## Executive Summary

**What:** A simplified API that wraps Core SDK, DataFlow, and Nexus with FastAPI-like syntax

**Why:** IT teams want to start fast without understanding workflows, nodes, runtimes

**How:** Quick Mode translates simple syntax to full SDK code behind the scenes

**Success Criteria:** IT teams build working apps in <30 minutes without reading SDK docs

---

## The Problem Quick Mode Solves

### Current Developer Experience (Full SDK)

```python
# Requires understanding: WorkflowBuilder, nodes, runtime, connections, build()

from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from dataflow import DataFlow

db = DataFlow("postgresql://...")

@db.model
class User:
    name: str
    email: str

# Create workflow
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "email": "alice@example.com"
})

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())  # Must remember .build()
```

**Complexity:** 5 concepts (WorkflowBuilder, nodes, runtime, model, decorator)
**Time to understand:** 2+ hours reading docs
**Token cost for AI:** 20K+ tokens navigating docs

### Quick Mode Experience (Goal)

```python
# Requires understanding: app, db, decorators (familiar to FastAPI users)

from kailash.quick import app, db

@db.model
class User:
    name: str
    email: str

@app.post("/users")
def create_user(name: str, email: str):
    return db.users.create(name=name, email=email)

app.run()  # That's it!
```

**Complexity:** 2 concepts (app, db - familiar from FastAPI)
**Time to understand:** 5 minutes (looks like FastAPI)
**Token cost for AI:** <1K tokens (similar to FastAPI examples)

---

## Quick Mode Architecture

### Three-Layer Design

```
┌─────────────────────────────────────────┐
│   Layer 1: Quick Mode API (New)        │
│   - FastAPI-like syntax                 │
│   - Auto-validation                     │
│   - Friendly errors                     │
└────────────┬────────────────────────────┘
             │ Translates to
             ▼
┌─────────────────────────────────────────┐
│   Layer 2: Full Kailash SDK            │
│   - WorkflowBuilder                     │
│   - LocalRuntime                        │
│   - DataFlow, Nexus                     │
└────────────┬────────────────────────────┘
             │ Executes
             ▼
┌─────────────────────────────────────────┐
│   Layer 3: Infrastructure               │
│   - PostgreSQL, MySQL, SQLite           │
│   - FastAPI (via Nexus)                 │
│   - MCP server                          │
└─────────────────────────────────────────┘
```

### Component Breakdown

**1. Quick App (`kailash.quick.app`)**
- Wraps Nexus for API deployment
- FastAPI-style route decorators
- Auto-generates workflows from functions

**2. Quick DB (`kailash.quick.db`)**
- Wraps DataFlow for database operations
- Simplified CRUD operations
- Auto-validation

**3. Quick Workflow (`kailash.quick.workflow`)**
- Wraps WorkflowBuilder
- Function-to-workflow conversion
- Auto-connection inference

**4. Quick Validation (`kailash.quick.validation`)**
- Pre-execution validation
- Type checking
- Immediate error feedback

---

## API Design

### Module Structure

```python
kailash/
└── quick/
    ├── __init__.py          # Public exports: app, db, workflow
    ├── app.py               # QuickApp class (Nexus wrapper)
    ├── db.py                # QuickDB class (DataFlow wrapper)
    ├── workflow.py          # QuickWorkflow class
    ├── validation.py        # Auto-validation system
    ├── runtime.py           # Runtime management
    └── errors.py            # AI-friendly errors
```

### QuickApp API

```python
# kailash/quick/app.py

from typing import Callable, Optional, Any
from nexus import Nexus
from .workflow import QuickWorkflow

class QuickApp:
    """Quick Mode application - FastAPI-like interface for Kailash."""

    def __init__(
        self,
        name: str = "quick-app",
        debug: bool = True,
        auto_reload: bool = True
    ):
        """Initialize Quick Mode app.

        Args:
            name: Application name
            debug: Enable debug mode (detailed errors)
            auto_reload: Auto-reload on file changes
        """
        self.name = name
        self.debug = debug
        self.auto_reload = auto_reload

        # Initialize Nexus with Quick Mode defaults
        self.nexus = Nexus.for_development() if debug else Nexus.for_production()

        # Track registered routes
        self._routes = {}

    def get(self, path: str):
        """Register GET endpoint (decorator).

        Example:
            @app.get("/users/{user_id}")
            def get_user(user_id: str):
                return db.users.read(id=user_id)
        """
        def decorator(func: Callable):
            workflow = self._function_to_workflow(func, method="GET", path=path)
            self.nexus.register(f"get_{func.__name__}", workflow)
            self._routes[path] = {"method": "GET", "func": func}
            return func
        return decorator

    def post(self, path: str):
        """Register POST endpoint (decorator).

        Example:
            @app.post("/users")
            def create_user(name: str, email: str):
                return db.users.create(name=name, email=email)
        """
        def decorator(func: Callable):
            workflow = self._function_to_workflow(func, method="POST", path=path)
            self.nexus.register(f"post_{func.__name__}", workflow)
            self._routes[path] = {"method": "POST", "func": func}
            return func
        return decorator

    def workflow(self, name: str):
        """Register workflow (not HTTP endpoint).

        Example:
            @app.workflow("send_email")
            def send_email(to: str, subject: str, body: str):
                # Send email logic
                return {"status": "sent"}
        """
        def decorator(func: Callable):
            workflow = self._function_to_workflow(func)
            self.nexus.register(name, workflow)
            return func
        return decorator

    def run(self, host: str = "0.0.0.0", port: int = 8000):
        """Start the application.

        Args:
            host: Host to bind to
            port: Port to bind to
        """
        print(f"🚀 Quick Mode: {self.name}")
        print(f"📡 API: http://{host}:{port}")
        print(f"🤖 MCP: stdio://localhost:3001")

        if self.debug:
            print(f"🐛 Debug mode: ON")
            print(f"🔄 Auto-reload: {'ON' if self.auto_reload else 'OFF'}")

        print(f"\n✅ {len(self._routes)} endpoints registered")

        # Start Nexus
        self.nexus.start()

    def _function_to_workflow(
        self,
        func: Callable,
        method: str = None,
        path: str = None
    ) -> 'Workflow':
        """Convert Python function to Kailash workflow.

        This is the magic that makes Quick Mode work.
        """
        from kailash.workflow.builder import WorkflowBuilder
        import inspect

        # Get function signature
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())

        # Create workflow
        builder = WorkflowBuilder()

        # Add PythonCodeNode that executes the function
        builder.add_node("PythonCodeNode", "execute", {
            "code": self._generate_code_for_function(func, params),
            "inputs": {param: f"{{{{ {param} }}}}" for param in params}
        })

        return builder.build()

    def _generate_code_for_function(self, func: Callable, params: list) -> str:
        """Generate code string for PythonCodeNode."""
        # Get function source
        import inspect
        source = inspect.getsource(func)

        # Extract function body
        lines = source.split('\n')
        # Skip decorator and def line
        body_lines = [line for line in lines[2:] if line.strip()]

        # Generate code
        code = f"""
# Auto-generated from Quick Mode function: {func.__name__}

def execute({', '.join(params)}):
{chr(10).join('    ' + line for line in body_lines)}

# Execute function
result = execute({', '.join(f"inputs['{p}']" for p in params)})

# Return result
return result if isinstance(result, dict) else {{'result': result}}
"""
        return code
```

### QuickDB API

```python
# kailash/quick/db.py

from typing import Any, Optional
from dataflow import DataFlow
from .validation import QuickValidator

class QuickDB:
    """Quick Mode database - simplified DataFlow interface."""

    def __init__(
        self,
        url: Optional[str] = None,
        auto_migrate: bool = True
    ):
        """Initialize Quick Mode database.

        Args:
            url: Database URL (uses DATABASE_URL env var if not provided)
            auto_migrate: Automatically run migrations
        """
        # Initialize DataFlow with Quick Mode defaults
        self.dataflow = DataFlow(
            database_url=url,
            auto_migrate=auto_migrate,
            multi_tenant=False,  # Quick Mode: single tenant by default
            audit_logging=False,  # Quick Mode: minimal overhead
            debug=True  # Quick Mode: verbose errors
        )

        self.validator = QuickValidator(self.dataflow)
        self._model_operations = {}

    def model(self, cls):
        """Decorator to register a model.

        Example:
            @db.model
            class User:
                name: str
                email: str
        """
        # Validate model
        errors = self.validator.validate_model(cls)
        if errors:
            raise ValueError(
                f"Model validation errors:\n" +
                "\n".join(f"  - {err}" for err in errors)
            )

        # Register with DataFlow
        cls = self.dataflow.model(cls)

        # Create model operations accessor
        model_name = cls.__name__
        self._model_operations[model_name.lower() + 's'] = ModelOperations(
            self.dataflow,
            model_name,
            self.validator
        )

        return cls

    def __getattr__(self, name: str):
        """Dynamic model access (e.g., db.users, db.products)."""
        if name in self._model_operations:
            return self._model_operations[name]

        raise AttributeError(
            f"No model registered for '{name}'. "
            f"Available: {', '.join(self._model_operations.keys())}"
        )


class ModelOperations:
    """CRUD operations for a model - simplified interface."""

    def __init__(self, dataflow, model_name: str, validator):
        self.dataflow = dataflow
        self.model_name = model_name
        self.validator = validator

    def create(self, **kwargs) -> dict:
        """Create a record.

        Example:
            user = db.users.create(name="Alice", email="alice@example.com")
        """
        # Validate before creating
        errors = self.validator.validate_create(self.model_name, kwargs)
        if errors:
            raise ValueError(
                f"Validation errors:\n" +
                "\n".join(f"  - {err}" for err in errors)
            )

        # Execute via workflow
        from kailash.workflow.builder import WorkflowBuilder
        from kailash.runtime.local import LocalRuntime

        workflow = WorkflowBuilder()
        workflow.add_node(f"{self.model_name}CreateNode", "create", kwargs)

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        return results["create"]

    def read(self, id: str) -> Optional[dict]:
        """Read a record by ID.

        Example:
            user = db.users.read(id="user-123")
        """
        from kailash.workflow.builder import WorkflowBuilder
        from kailash.runtime.local import LocalRuntime

        workflow = WorkflowBuilder()
        workflow.add_node(f"{self.model_name}ReadNode", "read", {"id": id})

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        return results.get("read")

    def update(self, id: str, **kwargs) -> dict:
        """Update a record.

        Example:
            user = db.users.update(id="user-123", name="Alice Updated")
        """
        # Validate
        errors = self.validator.validate_update(self.model_name, kwargs)
        if errors:
            raise ValueError(
                f"Validation errors:\n" +
                "\n".join(f"  - {err}" for err in errors)
            )

        # Execute
        from kailash.workflow.builder import WorkflowBuilder
        from kailash.runtime.local import LocalRuntime

        workflow = WorkflowBuilder()
        workflow.add_node(f"{self.model_name}UpdateNode", "update", {
            "filter": {"id": id},
            "fields": kwargs
        })

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        return results["update"]

    def delete(self, id: str) -> bool:
        """Delete a record.

        Example:
            success = db.users.delete(id="user-123")
        """
        from kailash.workflow.builder import WorkflowBuilder
        from kailash.runtime.local import LocalRuntime

        workflow = WorkflowBuilder()
        workflow.add_node(f"{self.model_name}DeleteNode", "delete", {"id": id})

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        return results.get("delete", {}).get("success", False)

    def list(self, **filters) -> list:
        """List records with optional filters.

        Example:
            active_users = db.users.list(is_active=True)
        """
        from kailash.workflow.builder import WorkflowBuilder
        from kailash.runtime.local import LocalRuntime

        workflow = WorkflowBuilder()
        workflow.add_node(f"{self.model_name}ListNode", "list", {
            "filters": filters
        })

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        return results.get("list", [])
```

### QuickValidator API

```python
# kailash/quick/validation.py

from typing import List
from datetime import datetime

class QuickValidator:
    """Auto-validation for Quick Mode - catch errors before execution."""

    def __init__(self, dataflow):
        self.dataflow = dataflow

    def validate_model(self, cls) -> List[str]:
        """Validate model definition."""
        errors = []

        # Check for required 'id' field
        if not hasattr(cls, '__annotations__'):
            errors.append("Model must have type annotations")
            return errors

        annotations = cls.__annotations__

        if 'id' not in annotations:
            errors.append(
                "Model must have 'id' field. "
                "Add: id: str"
            )

        # Check for common mistakes
        if 'created_at' in annotations:
            errors.append(
                "created_at is auto-managed by DataFlow. Remove from model."
            )

        if 'updated_at' in annotations:
            errors.append(
                "updated_at is auto-managed by DataFlow. Remove from model."
            )

        return errors

    def validate_create(self, model_name: str, params: dict) -> List[str]:
        """Validate create operation parameters."""
        errors = []

        # Get model schema
        model_info = self.dataflow._models.get(model_name)
        if not model_info:
            errors.append(f"Model '{model_name}' not found")
            return errors

        fields = model_info["fields"]

        # Check required fields
        for field_name, field_info in fields.items():
            if field_info.get("required", False):
                if field_name not in params:
                    # Skip auto-managed fields
                    if field_name not in ["created_at", "updated_at", "id"]:
                        errors.append(f"Required field '{field_name}' missing")

        # Check types
        for field_name, value in params.items():
            if field_name not in fields:
                errors.append(f"Unknown field '{field_name}'")
                continue

            field_type = fields[field_name]["type"]

            # Common type mistakes
            if field_type == datetime:
                if isinstance(value, str):
                    errors.append(
                        f"Field '{field_name}' expects datetime, got string. "
                        f"Did you use .isoformat()? Use datetime.now() instead."
                    )

            if field_type == dict:
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

    def validate_update(self, model_name: str, params: dict) -> List[str]:
        """Validate update operation parameters."""
        errors = []

        model_info = self.dataflow._models.get(model_name)
        if not model_info:
            errors.append(f"Model '{model_name}' not found")
            return errors

        fields = model_info["fields"]

        # Check fields being updated
        for field_name in params:
            if field_name not in fields:
                errors.append(f"Unknown field '{field_name}'")

            # Check auto-managed
            if field_name in ["created_at", "updated_at", "id"]:
                errors.append(
                    f"'{field_name}' cannot be updated (auto-managed or primary key)"
                )

        return errors
```

---

## Usage Examples

### Example 1: Simple CRUD API

```python
# app.py

from kailash.quick import app, db

# Define model
@db.model
class User:
    name: str
    email: str
    is_active: bool = True

# Create endpoints
@app.post("/users")
def create_user(name: str, email: str):
    """Create a new user."""
    return db.users.create(name=name, email=email)

@app.get("/users/{user_id}")
def get_user(user_id: str):
    """Get user by ID."""
    user = db.users.read(id=user_id)
    if not user:
        return {"error": "User not found"}, 404
    return user

@app.post("/users/{user_id}")
def update_user(user_id: str, name: str = None, email: str = None):
    """Update user."""
    updates = {}
    if name:
        updates["name"] = name
    if email:
        updates["email"] = email

    return db.users.update(id=user_id, **updates)

@app.delete("/users/{user_id}")
def delete_user(user_id: str):
    """Delete user."""
    success = db.users.delete(id=user_id)
    return {"success": success}

@app.get("/users")
def list_users(is_active: bool = None):
    """List users."""
    filters = {}
    if is_active is not None:
        filters["is_active"] = is_active

    return {"users": db.users.list(**filters)}

# Run
if __name__ == "__main__":
    app.run()
```

**Run:**
```bash
python app.py

# Output:
# 🚀 Quick Mode: quick-app
# 📡 API: http://0.0.0.0:8000
# 🤖 MCP: stdio://localhost:3001
# 🐛 Debug mode: ON
# ✅ 5 endpoints registered
```

**Test:**
```bash
# Create user
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com"}'

# Response: {"id": "...", "name": "Alice", "email": "alice@example.com", "is_active": true}
```

### Example 2: Business Logic Workflow

```python
# app.py

from kailash.quick import app, db

@db.model
class Order:
    customer_name: str
    product: str
    quantity: int
    status: str = "pending"

@db.model
class Notification:
    order_id: str
    message: str
    sent_at: datetime

@app.workflow("process_order")
def process_order(order_id: str):
    """Process an order - multi-step workflow."""

    # 1. Get order
    order = db.orders.read(id=order_id)
    if not order:
        return {"error": "Order not found"}

    # 2. Update status
    db.orders.update(id=order_id, status="processing")

    # 3. Send notification
    notification = db.notifications.create(
        order_id=order_id,
        message=f"Order {order_id} is being processed",
        sent_at=datetime.now()
    )

    # 4. Update status to completed
    db.orders.update(id=order_id, status="completed")

    return {
        "order": order,
        "notification": notification,
        "status": "completed"
    }

@app.post("/orders")
def create_order(customer_name: str, product: str, quantity: int):
    """Create and process order."""

    # Create order
    order = db.orders.create(
        customer_name=customer_name,
        product=product,
        quantity=quantity
    )

    # Trigger processing workflow
    result = app.execute_workflow("process_order", order_id=order["id"])

    return result

app.run()
```

### Example 3: Quick Mode → Full SDK Upgrade

**Before (Quick Mode):**
```python
from kailash.quick import app, db

@db.model
class User:
    name: str

@app.post("/users")
def create_user(name: str):
    return db.users.create(name=name)

app.run()
```

**After (Full SDK) - Auto-generated by `kailash upgrade`:**
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from dataflow import DataFlow
from nexus import Nexus

# Initialize
db = DataFlow("postgresql://...")
nexus = Nexus()

# Model
@db.model
class User:
    name: str

# Workflow
def create_user_workflow():
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "name": "{{ name }}"
    })
    return workflow.build()

# Register
nexus.register("create_user", create_user_workflow())

# Run
if __name__ == "__main__":
    nexus.start()
```

**Upgrade command:**
```bash
kailash upgrade --to=standard

# Output:
# 🔄 Upgrading from Quick Mode to Standard SDK
# ✅ Converted app.py to full SDK
# ✅ Created workflows/ directory
# ✅ Updated requirements.txt
# ✅ Backup saved to .kailash/backup/
#
# Next steps:
#   1. Review generated code in workflows/
#   2. Test: python main.py
#   3. Commit changes
```

---

## Error Handling

### Auto-Validation Errors (Immediate Feedback)

**Example: Type Mismatch**
```python
from kailash.quick import db
from datetime import datetime

@db.model
class Session:
    user_id: str
    created_at: datetime

# ❌ Wrong: Using .isoformat()
db.sessions.create(
    user_id="user-123",
    created_at=datetime.now().isoformat()  # String, not datetime
)

# Output (immediate, before execution):
# ❌ Validation Error:
#
# Field 'created_at' expects datetime, got string.
# Did you use .isoformat()? Use datetime.now() instead.
#
# ✅ Fix:
# db.sessions.create(
#     user_id="user-123",
#     created_at=datetime.now()  # ← Correct
# )
```

**Example: Required Field Missing**
```python
@db.model
class Product:
    name: str
    price: float

# ❌ Missing required field
db.products.create(name="Widget")  # price missing

# Output:
# ❌ Validation Error:
#
# Required field 'price' missing
#
# ✅ Fix:
# db.products.create(name="Widget", price=9.99)
```

### AI-Friendly Error Messages

**Traditional Error:**
```
Traceback (most recent call last):
  File "app.py", line 15, in <module>
    db.users.create(name=name, email=email)
  File "kailash/quick/db.py", line 123, in create
    runtime.execute(workflow.build())
  File "kailash/runtime/local.py", line 456, in execute
    result = node.execute(params)
  ...
kailash.sdk_exceptions.WorkflowExecutionError: Node 'create' execution failed
```

**Quick Mode Error:**
```
❌ Database Operation Failed

Operation: Create User
Error: Duplicate email address

Details:
  Email 'alice@example.com' already exists
  Database constraint: unique_email

Suggestions:
  1. Check if user already exists: db.users.list(email="alice@example.com")
  2. Update existing user instead: db.users.update(id="...", name="...")
  3. Use a different email address

Code Location:
  File: app.py:15
  Function: create_user
  Line: return db.users.create(name=name, email=email)

Need help? See: https://docs.kailash.dev/quick-mode/errors/duplicate-key
```

---

## Upgrade Path

### Three Modes

**Level 1: Quick Mode** (Simplest)
```python
from kailash.quick import app, db

@db.model
class User:
    name: str

@app.post("/users")
def create_user(name: str):
    return db.users.create(name=name)

app.run()
```

**Level 2: Hybrid Mode** (Some control)
```python
from kailash.quick import app, db
from kailash.workflow.builder import WorkflowBuilder

# Still use Quick Mode for simple operations
@db.model
class User:
    name: str

# But drop down to full SDK when needed
@app.workflow("complex_user_creation")
def complex_user_creation():
    workflow = WorkflowBuilder()
    # ... complex workflow with multiple steps
    return workflow.build()

app.run()
```

**Level 3: Full SDK** (Complete control)
```python
# No Quick Mode imports
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from dataflow import DataFlow
from nexus import Nexus

# Full SDK - complete control
# ... (standard Kailash code)
```

### Upgrade Command

```bash
# Analyze current project
kailash upgrade --analyze

# Output:
# 📊 Project Analysis
#
# Current mode: Quick Mode
# Quick Mode usage: 15 endpoints, 3 models
# Complexity: Low
#
# Upgrade benefits:
#   ✅ Full workflow control
#   ✅ Advanced error handling
#   ✅ Custom middleware
#   ✅ Performance optimization
#
# Upgrade cost:
#   ⚠️  More code to maintain
#   ⚠️  Steeper learning curve
#
# Recommendation: Stay in Quick Mode
# Reason: Current usage is simple, no complex workflows needed

# Force upgrade if desired
kailash upgrade --to=standard --force

# Generates:
# - main.py (Nexus setup)
# - workflows/ directory (converted from Quick Mode functions)
# - models/ directory (DataFlow models)
# - Backup of Quick Mode code in .kailash/backup/
```

---

## Testing Strategy

### Unit Tests

```python
# tests/quick/test_quick_app.py

def test_quick_app_creates_endpoint():
    """Test that @app.post creates an endpoint."""
    from kailash.quick import QuickApp

    app = QuickApp("test-app")

    @app.post("/test")
    def test_endpoint(value: str):
        return {"echo": value}

    assert "/test" in app._routes
    assert app._routes["/test"]["method"] == "POST"

def test_function_to_workflow_conversion():
    """Test that Python functions convert to workflows correctly."""
    from kailash.quick import QuickApp

    app = QuickApp()

    def my_func(x: int, y: int):
        return x + y

    workflow = app._function_to_workflow(my_func)

    # Workflow should have PythonCodeNode
    assert len(workflow.nodes) == 1
    assert workflow.nodes[0].node_class == "PythonCodeNode"
```

### Integration Tests

```python
# tests/integration/test_quick_mode_integration.py

def test_quick_mode_crud_operations():
    """Test that Quick Mode CRUD operations work end-to-end."""
    from kailash.quick import QuickDB

    db = QuickDB("sqlite:///test.db")

    @db.model
    class TestModel:
        name: str
        value: int

    # Create
    record = db.testmodels.create(name="test", value=42)
    assert record["name"] == "test"
    assert record["value"] == 42

    # Read
    fetched = db.testmodels.read(id=record["id"])
    assert fetched["name"] == "test"

    # Update
    updated = db.testmodels.update(id=record["id"], value=100)
    assert updated["value"] == 100

    # Delete
    success = db.testmodels.delete(id=record["id"])
    assert success is True

def test_quick_mode_validation_catches_errors():
    """Test that validation catches errors before execution."""
    from kailash.quick import QuickDB
    from datetime import datetime

    db = QuickDB("sqlite:///test.db")

    @db.model
    class Session:
        user_id: str
        created_at: datetime

    # Should raise validation error
    with pytest.raises(ValueError, match="expects datetime, got string"):
        db.sessions.create(
            user_id="user-123",
            created_at=datetime.now().isoformat()  # Wrong: string
        )
```

### E2E Tests

```python
# tests/e2e/test_quick_mode_e2e.py

def test_complete_quick_mode_application():
    """Test complete Quick Mode application end-to-end."""

    # Create Quick Mode app
    code = """
from kailash.quick import app, db

@db.model
class User:
    name: str
    email: str

@app.post("/users")
def create_user(name: str, email: str):
    return db.users.create(name=name, email=email)

@app.get("/users/{user_id}")
def get_user(user_id: str):
    return db.users.read(id=user_id)

if __name__ == "__main__":
    app.run()
"""

    # Write to file
    Path("test_app.py").write_text(code)

    # Run app in background
    process = subprocess.Popen(
        ["python", "test_app.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Wait for startup
    time.sleep(3)

    try:
        # Test create
        response = requests.post("http://localhost:8000/users", json={
            "name": "Alice",
            "email": "alice@example.com"
        })
        assert response.status_code == 200
        user = response.json()
        assert user["name"] == "Alice"

        # Test read
        response = requests.get(f"http://localhost:8000/users/{user['id']}")
        assert response.status_code == 200
        fetched = response.json()
        assert fetched["email"] == "alice@example.com"

    finally:
        process.terminate()
```

---

## Documentation

### Quick Start Guide

```markdown
# Quick Mode: Get Started in 5 Minutes

## 1. Install Kailash

```bash
pip install kailash
```

## 2. Create app.py

```python
from kailash.quick import app, db

@db.model
class User:
    name: str
    email: str

@app.post("/users")
def create_user(name: str, email: str):
    return db.users.create(name=name, email=email)

@app.get("/users/{user_id}")
def get_user(user_id: str):
    return db.users.read(id=user_id)

if __name__ == "__main__":
    app.run()
```

## 3. Set up database

```bash
# Create .env file
echo "DATABASE_URL=sqlite:///app.db" > .env
```

## 4. Run

```bash
python app.py
```

## 5. Test

```bash
# Create user
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com"}'
```

**That's it! You have a working API with database.**

## Next Steps

- [Add more models](docs/quick-mode/models.md)
- [Add business logic](docs/quick-mode/workflows.md)
- [Deploy to production](docs/quick-mode/deployment.md)
- [Upgrade to Full SDK](docs/quick-mode/upgrade.md)
```

---

## Success Metrics

**1. Time-to-First-API**
- Target: <10 minutes (from install to working API)
- Measure: Time from `pip install` to first successful request
- Current (Full SDK): 2+ hours

**2. Adoption Rate**
- Target: 60% of IT teams use Quick Mode (vs Full SDK)
- Measure: % of new projects using Quick Mode imports
- Baseline: 0% (doesn't exist yet)

**3. Upgrade Rate**
- Target: 30% eventually upgrade to Full SDK
- Measure: % of Quick Mode projects that run `kailash upgrade`
- Goal: Users start simple, upgrade when needed

**4. Error Resolution Time**
- Target: <5 minutes (vs 48 hours currently)
- Measure: Time from error to fix
- With auto-validation: Immediate feedback

**5. AI Assistant Effectiveness**
- Target: 90% of Quick Mode code generations work first try
- Measure: Code generated by Claude Code that runs without modification
- Reason: Quick Mode is simpler, less room for error

---

## Implementation Timeline

**Week 9-10: Core API Design**
- Implement QuickApp class
- Implement QuickDB class
- Function-to-workflow conversion

**Week 11-12: Validation System**
- Implement QuickValidator
- Add type checking
- Add AI-friendly errors

**Week 13-14: Integration**
- Integrate with Nexus
- Integrate with DataFlow
- End-to-end testing

**Week 15-16: Upgrade Path**
- Implement `kailash upgrade` command
- Code generation from Quick Mode to Full SDK
- Beta testing

---

## Key Takeaways

**Quick Mode solves the "blank canvas" problem:**
- Familiar syntax (FastAPI-like)
- Immediate validation
- AI-friendly errors
- Clear upgrade path

**Success depends on:**
- Simplicity (don't expose SDK complexity)
- Validation (catch errors immediately)
- Documentation (clear examples)
- Upgrade path (can grow into Full SDK)

**If IT teams adopt Quick Mode, the repivot succeeds. If they don't, we need to understand why and iterate.**

---

**Next:** See `03-golden-patterns.md` for the 10 essential patterns that Quick Mode and templates use
