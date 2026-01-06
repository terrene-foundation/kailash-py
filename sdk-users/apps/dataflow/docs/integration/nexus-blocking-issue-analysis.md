# DataFlow + Nexus Integration Solution

> **✅ RESOLVED IN v1.1.1+**: As of Nexus v1.1.1 (released October 24, 2025), the default for `auto_discovery` has been changed to `False` (P0-3 fix). This blocking issue no longer occurs by default. This document is retained for reference and for users on earlier versions.

## Problem Summary (Resolved in v1.1.1+)

**Historical Issue (v1.1.0 and earlier)**: When integrating DataFlow models with Nexus platform, the server initialization hangs indefinitely during DataFlow model registration if Nexus is initialized with `auto_discovery=True` (which was the default behavior in v1.1.0 and earlier).

**Resolution**: Nexus v1.1.1+ defaults to `auto_discovery=False`, eliminating this blocking issue automatically.

## Root Cause Analysis

### The Issue
1. **DataFlow Model Registration**: When DataFlow registers models using the `@db.model` decorator, it creates and registers workflow nodes globally (9 nodes per model: CRUD + bulk operations)

2. **Nexus Auto-Discovery**: When Nexus initializes with `auto_discovery=True`, it:
   - Scans the filesystem for Python files matching workflow patterns
   - Imports these files to discover workflows
   - This import process triggers DataFlow model registration again
   - Creates a blocking loop where model registration workflows execute repeatedly

3. **Blocking Behavior**: The combination causes:
   - DataFlow model registration workflows to execute during Nexus's discovery phase
   - LocalRuntime execution blocks within the discovery process
   - Server initialization never completes

### Technical Details
```python
# The problematic flow:
1. Import DataFlow models → Registers nodes globally
2. Create Nexus(auto_discovery=True) → Starts discovery
3. Discovery imports Python files → Re-triggers DataFlow registration
4. Registration workflows execute → Blocks in LocalRuntime
5. Server never completes initialization
```

## Solution

### Immediate Fix
Set `auto_discovery=False` when creating Nexus instances that will use DataFlow:

```python
from nexus import Nexus

app = Nexus(
    api_port=8002,
    mcp_port=3001,
    auto_discovery=False  # CRITICAL: Prevents blocking
)
```

### Why This Works
- Prevents Nexus from scanning and importing Python files during initialization
- Avoids re-triggering DataFlow model registration
- Allows manual, controlled workflow registration
- Server initializes quickly without blocking

## Best Practices Implementation

### 1. Recommended Initialization Order

```python
def create_production_app():
    # Step 1: Create Nexus FIRST with auto_discovery=False
    app = Nexus(
        api_port=8002,
        mcp_port=3001,
        auto_discovery=False,  # Prevents blocking
        enable_durability=True
    )

    # Step 2: Import DataFlow AFTER Nexus init
    from database.dataflow_models import db

    # Step 3: Register workflows manually
    register_workflows(app, db)

    return app
```

### 2. DataFlow Configuration

```python
from dataflow.core.engine import DataFlow

db = DataFlow(
    database_url="postgresql://user:pass@host:port/db",
    auto_migrate=False,              # Control migrations manually
    skip_migration=True,             # Skip auto-migration for faster startup
    enable_model_persistence=True,   # Enable model persistence for multi-app support
    connection_pool_size=20,
    enable_metrics=True,
    enable_caching=True
)
```

### 3. Model Registration Pattern

```python
def setup_dataflow_models():
    """Setup DataFlow models in a function scope."""
    from dataflow.core.engine import DataFlow

    db = DataFlow(...)

    @db.model
    class User:
        id: str
        email: str
        name: Optional[str] = None

    @db.model
    class Session:
        id: str
        user_id: str
        token: str

    return db
```

### 4. Workflow Registration

```python
def register_production_workflows(app: Nexus, db: DataFlow):
    """Register DataFlow-based workflows with Nexus."""
    from kailash.workflow.builder import WorkflowBuilder

    # User CRUD workflow
    user_workflow = WorkflowBuilder()
    user_workflow.add_node("UserCreateNode", "create_user", {
        "email": "{{email}}",
        "name": "{{name}}"
    })
    app.register("user_create", user_workflow.build())

    # Session management workflow
    session_workflow = WorkflowBuilder()
    session_workflow.add_node("SessionCreateNode", "create_session", {
        "user_id": "{{user_id}}",
        "token": "{{token}}"
    })
    app.register("session_create", session_workflow.build())
```

## Complete Integration Example

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
from typing import Optional

class DataFlowNexusApp:
    """Production-ready DataFlow + Nexus integration."""

    def __init__(self):
        # Initialize Nexus FIRST with auto_discovery=False
        self.app = Nexus(
            api_port=8002,
            mcp_port=3001,
            auto_discovery=False  # Critical for DataFlow integration
        )

        # Setup DataFlow AFTER Nexus
        self._setup_dataflow()

        # Register workflows
        self._register_workflows()

    def _setup_dataflow(self):
        """Setup DataFlow models."""
        from dataflow.core.engine import DataFlow

        self.db = DataFlow(
            database_url="postgresql://kailash:kailash@localhost:5432/prod",
            auto_migrate=False,
            skip_migration=True,
            enable_model_persistence=True
        )

        # Define models
        @self.db.model
        class User:
            id: str
            email: str
            full_name: Optional[str] = None
            created_at: str
            active: bool = True

        @self.db.model
        class Session:
            id: str
            user_id: str
            token: str
            created_at: str
            expires_at: str

    def _register_workflows(self):
        """Register workflows with Nexus."""
        # User creation workflow
        user_create = WorkflowBuilder()
        user_create.add_node("UserCreateNode", "create", {
            "email": "{{email}}",
            "full_name": "{{full_name}}"
        })
        self.app.register("create_user", user_create.build())

        # Session creation workflow
        session_create = WorkflowBuilder()
        session_create.add_node("SessionCreateNode", "create", {
            "user_id": "{{user_id}}",
            "token": "{{token}}"
        })
        self.app.register("create_session", session_create.build())

    def start(self):
        """Start the application."""
        self.app.start()

# Usage
if __name__ == "__main__":
    app = DataFlowNexusApp()
    app.start()
```

## Performance Considerations

### With Fix Applied
- Nexus initialization: ~1-2 seconds
- DataFlow model registration: ~5-10 seconds (depends on model count)
- Total startup time: ~10-15 seconds for typical application
- No blocking or hanging

### Without Fix (auto_discovery=True)
- Server hangs indefinitely
- Must be terminated with Ctrl+C
- Production deployment impossible

## Migration Guide

### For Existing Applications

1. **Update Nexus Initialization**:
   ```python
   # OLD (blocks with DataFlow)
   app = Nexus(api_port=8002)

   # NEW (works with DataFlow)
   app = Nexus(api_port=8002, auto_discovery=False)
   ```

2. **Reorganize Imports**:
   ```python
   # OLD (DataFlow imported globally)
   from database.dataflow_models import db
   app = Nexus()  # Blocks here

   # NEW (DataFlow imported after Nexus)
   app = Nexus(auto_discovery=False)
   from database.dataflow_models import db
   ```

3. **Manual Workflow Registration**:
   ```python
   # Since auto_discovery is off, register workflows manually
   app.register("workflow_name", workflow_instance)
   ```

## Troubleshooting

### Issue: Server Still Hangs
- Verify `auto_discovery=False` is set
- Check for global DataFlow imports before Nexus creation
- Ensure no other code triggers workflow discovery

### Issue: Workflows Not Found
- With `auto_discovery=False`, workflows must be registered manually
- Use `app.register()` for each workflow
- Verify workflow names match your API calls

### Issue: DataFlow Models Not Available
- Import DataFlow models AFTER Nexus initialization
- Ensure database connection is configured correctly
- Check model registration completes before starting server

## Future Improvements

### Planned SDK Enhancements
1. **Lazy Model Registration**: DataFlow models register only when first used
2. **Discovery Isolation**: Run discovery in separate process/thread
3. **Smart Discovery**: Exclude DataFlow model files from discovery
4. **Configuration Option**: Add `dataflow_compatible` mode to Nexus

### Workaround Until Fix
Use the `auto_discovery=False` pattern as documented above. This is the recommended approach for all DataFlow + Nexus integrations.

## Summary

The DataFlow + Nexus integration issue occurs because:
1. DataFlow model registration creates workflows that execute during import
2. Nexus auto_discovery imports Python files, triggering model registration
3. This creates a blocking loop that prevents server initialization

The solution is simple and effective:
- Set `auto_discovery=False` when creating Nexus instances
- Initialize Nexus BEFORE importing DataFlow models
- Register workflows manually after model setup

This pattern ensures reliable, fast server startup while maintaining all DataFlow and Nexus features.
