# DataFlow Shared Model Pattern for Multi-Application Environments

## Overview

DataFlow stores model definitions in volatile memory, which means each application instance must register its models at startup. For multi-application environments accessing the same database, the **Shared Model Pattern** provides a workable solution.

## The Challenge

- DataFlow models exist only in Python memory (`self._models = {}`)
- Each DataFlow instance starts with empty model registry
- No built-in model persistence or discovery mechanism
- Multiple applications need consistent model definitions

## The Solution: Shared Model Pattern

### Step 1: Create a Shared Model Module

Create a centralized Python module containing all shared model definitions:

```python
# shared_models.py
"""
Shared DataFlow models for multi-application use.
All applications using the shared database should import this module.
"""

def register_shared_models(dataflow_instance):
    """
    Register all shared models with a DataFlow instance.

    Args:
        dataflow_instance: DataFlow instance to register models with

    Returns:
        dataflow_instance: The same instance with models registered
    """

    @dataflow_instance.model
    class User:
        name: str
        email: str
        active: bool = True
        created_at: datetime = None

    @dataflow_instance.model
    class Project:
        project_name: str
        description: str
        owner_id: int
        status: str = "active"
        budget: float = 0.0

    @dataflow_instance.model
    class Task:
        task_name: str
        project_id: int
        assigned_to: int
        due_date: datetime
        completed: bool = False
        priority: str = "medium"

    # Add more models as needed

    return dataflow_instance
```

### Step 2: Use in Each Application

Each application imports and uses the shared models:

```python
# application_a.py
from dataflow import DataFlow
from shared_models import register_shared_models

# CRITICAL: Disable auto-migration for existing databases
db = DataFlow(
    database_url="postgresql://user:pass@localhost/shared_db",
    auto_migrate=False,  # Prevent destructive migrations
    existing_schema_mode=True  # Safe mode for existing data
)

# Register shared models
db = register_shared_models(db)

# Now use the models normally
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice",
    "email": "alice@example.com"
})
```

```python
# application_b.py
from dataflow import DataFlow
from shared_models import register_shared_models

# Same configuration
db = DataFlow(
    database_url="postgresql://user:pass@localhost/shared_db",
    auto_migrate=False,
    existing_schema_mode=True
)

# Register the same models
db = register_shared_models(db)

# Use models consistently
workflow = WorkflowBuilder()
workflow.add_node("UserListNode", "list_users", {
    "filter": {"active": True}
})
```

## Best Practices

### 1. Version Control

Keep the shared model module in version control and ensure all applications use the same version:

```python
# shared_models.py
__version__ = "1.0.0"

def check_version(required_version):
    """Ensure model compatibility."""
    if __version__ != required_version:
        raise ValueError(f"Model version mismatch: {__version__} != {required_version}")
```

### 2. Schema Migration Coordination

Since each application could trigger migrations, coordinate schema changes:

```python
# migration_controller.py
class MigrationController:
    """Centralized migration control for multi-app environments."""

    @staticmethod
    def apply_migrations(db, dry_run=True):
        """Apply migrations with safety checks."""
        if not dry_run:
            # Only one designated app should apply migrations
            if not os.environ.get("ALLOW_MIGRATIONS") == "true":
                raise PermissionError("This application is not authorized to run migrations")

        success, migrations = db.auto_migrate(
            dry_run=dry_run,
            max_risk_level="MEDIUM",
            data_loss_protection=True
        )

        return success, migrations
```

### 3. Model Registry Validation

Add validation to ensure models are consistent:

```python
def validate_model_consistency(db, expected_models):
    """Validate that all expected models are registered."""
    registered = set(db.get_models().keys())
    expected = set(expected_models)

    missing = expected - registered
    extra = registered - expected

    if missing:
        raise ValueError(f"Missing models: {missing}")
    if extra:
        logger.warning(f"Extra models registered: {extra}")

    return True

# Usage
validate_model_consistency(db, ["User", "Project", "Task"])
```

### 4. Environment-Specific Configuration

Use environment variables for configuration:

```python
# config.py
import os

DATAFLOW_CONFIG = {
    "database_url": os.environ.get("DATABASE_URL"),
    "auto_migrate": os.environ.get("DATAFLOW_AUTO_MIGRATE", "false").lower() == "true",
    "existing_schema_mode": os.environ.get("DATAFLOW_SAFE_MODE", "true").lower() == "true",
    "pool_size": int(os.environ.get("DATAFLOW_POOL_SIZE", "20"))
}

# Usage
db = DataFlow(**DATAFLOW_CONFIG)
```

## Limitations and Considerations

### Current Limitations

1. **Manual Coordination Required**: Teams must coordinate model changes
2. **No Automatic Drift Detection**: Model changes aren't automatically detected
3. **No Model Discovery**: Can't discover models from existing database
4. **No Versioning**: No built-in model version tracking

### When This Pattern Works Well

- Small to medium teams with good communication
- Well-defined database schemas
- Controlled deployment processes
- Microservices with clear boundaries

### When to Consider Alternatives

- Large teams with frequent schema changes
- Ad-hoc database access requirements
- Legacy database integration
- Highly dynamic schemas

## Example: Complete Multi-App Setup

Here's a complete example of a multi-application setup:

```python
# shared_infrastructure.py
"""Shared infrastructure for all DataFlow applications."""

from dataflow import DataFlow
from shared_models import register_shared_models
import logging

logger = logging.getLogger(__name__)

def create_dataflow_instance(app_name, allow_migrations=False):
    """
    Create a configured DataFlow instance for multi-app use.

    Args:
        app_name: Name of the application (for logging)
        allow_migrations: Whether this app can run migrations

    Returns:
        Configured DataFlow instance with shared models
    """
    logger.info(f"Initializing DataFlow for {app_name}")

    # Create instance with safety settings
    db = DataFlow(
        database_url=os.environ.get("DATABASE_URL"),
        auto_migrate=False,  # Never auto-migrate
        existing_schema_mode=True,  # Always safe mode
        pool_size=20,
        echo=False
    )

    # Register shared models
    db = register_shared_models(db)

    # Validate models
    expected_models = ["User", "Project", "Task"]
    validate_model_consistency(db, expected_models)

    # Handle migrations if authorized
    if allow_migrations and os.environ.get("RUN_MIGRATIONS") == "true":
        logger.info(f"{app_name} is applying migrations...")
        success, migrations = db.auto_migrate(
            dry_run=False,
            auto_confirm=True,
            max_risk_level="MEDIUM"
        )
        if not success:
            raise RuntimeError("Migration failed")

    logger.info(f"DataFlow ready for {app_name}")
    return db

# Usage in applications
# app_a.py
db = create_dataflow_instance("Application A", allow_migrations=True)

# app_b.py
db = create_dataflow_instance("Application B", allow_migrations=False)
```

## Migration Path

This pattern is a workaround until DataFlow implements persistent model registry. When that feature is available:

1. Run migration tool to persist current models
2. Update applications to use model discovery
3. Remove shared model module
4. Enable automatic model synchronization

## Conclusion

The Shared Model Pattern makes DataFlow viable for multi-application environments despite its volatile model storage. While requiring manual coordination, it provides a workable solution that aligns with common microservices patterns and shared library approaches.
