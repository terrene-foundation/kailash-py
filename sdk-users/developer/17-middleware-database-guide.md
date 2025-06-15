# Using the Middleware Database Layer

## Overview

The Kailash SDK provides a comprehensive middleware database layer that eliminates the need to write boilerplate SQLAlchemy code. This guide shows how to use these components effectively.

## Quick Start

Instead of writing hundreds of lines of database code, use the middleware components:

```python
from kailash.middleware.database import (
    DatabaseManager,
    BaseWorkflowModel,
    BaseExecutionModel,
    BaseTemplateModel
)

# Define your app's models by extending base models
class MyWorkflow(BaseWorkflowModel):
    __tablename__ = "my_workflows"
    # All common fields are inherited!

# Initialize database
db_manager = DatabaseManager("postgresql+asyncpg://localhost/myapp")
await db_manager.create_tables()

# Use it
async with db_manager.get_session("tenant123") as session:
    workflow = MyWorkflow(name="My Flow", tenant_id="tenant123")
    session.add(workflow)
    await session.commit()
```

## Base Models Available

### 1. BaseWorkflowModel
Provides all enterprise workflow features:
- Multi-tenant isolation (`tenant_id`)
- Version control (`version`)
- Soft deletes (`deleted_at`, `deleted_by`)
- Audit trail (`created_at`, `updated_at`, `created_by`, `updated_by`)
- Security classification
- Compliance tracking
- Session management

```python
from kailash.middleware.database import BaseWorkflowModel

class StudioWorkflow(BaseWorkflowModel):
    __tablename__ = "studio_workflows"
    
    # Only add app-specific fields
    # All standard fields are inherited
```

### 2. BaseExecutionModel
Complete execution tracking:
- Progress monitoring (`progress_percentage`, `completed_nodes`)
- Error handling (`error_message`, `error_details`)
- Performance metrics (`runtime_seconds`, `resource_usage`)
- Detailed logging (`logs`, `debug_info`)

```python
from kailash.middleware.database import BaseExecutionModel

class MyExecution(BaseExecutionModel):
    __tablename__ = "my_executions"
    
    # Inherited methods:
    # - start(started_by)
    # - complete(outputs)
    # - fail(error_message)
```

### 3. BaseTemplateModel
Template management with analytics:
- Usage tracking (`usage_count`, `last_used`)
- Rating system (`rating_average`, `rating_count`)
- Certification levels
- Multi-tenant sharing (`is_public`)

### 4. Security Models
- `BaseSecurityEventModel` - Comprehensive security monitoring
- `BaseAuditLogModel` - Tamper-proof audit trails
- `BaseComplianceModel` - Compliance assessments

## Database Manager

The `DatabaseManager` provides enterprise features out-of-the-box:

```python
from kailash.middleware.database import DatabaseManager

# Initialize with connection pooling
db_manager = DatabaseManager(
    database_url="postgresql+asyncpg://localhost/myapp",
    pool_size=20,
    max_overflow=40
)

# Get tenant-scoped session
async with db_manager.get_session(tenant_id="acme_corp") as session:
    # All queries automatically filtered by tenant!
    workflows = await session.execute(
        select(MyWorkflow)  # No need to add tenant filter
    )
```

## Repository Pattern

Use repositories for common operations:

```python
from kailash.middleware.database import BaseRepository

# Create repository for your model
workflow_repo = BaseRepository(MyWorkflow)

async with db_manager.get_session() as session:
    # CRUD operations with audit trail
    workflow = await workflow_repo.create(
        session,
        name="New Workflow",
        tenant_id="tenant123"
    )
    
    # Find by tenant (soft-deleted excluded automatically)
    workflows = await workflow_repo.find_by_tenant(session, "tenant123")
    
    # Soft delete with audit
    await workflow_repo.soft_delete(session, workflow, "user123")
```

## Common Enums

Use standard enums across all apps:

```python
from kailash.middleware.database.enums import (
    WorkflowStatus,      # DRAFT, ACTIVE, ARCHIVED, etc.
    ExecutionStatus,     # PENDING, RUNNING, COMPLETED, etc.
    NodeType,           # AI_ML, DATA_PROCESSING, etc.
    SecurityEventType,   # AUTHENTICATION, AUTHORIZATION, etc.
    ComplianceFramework  # GDPR, SOC2, ISO27001, etc.
)

# Use in your models or queries
workflow.status = WorkflowStatus.ACTIVE
```

## Migration Example: Studio App

The Studio app was refactored from 900+ lines to ~400 lines:

### Before (Manual Implementation):
```python
# 150+ lines of boilerplate
class StudioWorkflow(Base):
    workflow_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    tenant_id = Column(String, index=True)
    created_at = Column(DateTime, default=func.now())
    # ... 20+ more fields
    
    # Manual indexes
    __table_args__ = (
        Index("idx_tenant_status", "tenant_id", "status"),
        # ... more indexes
    )
    
    # Manual validation
    @validates('name')
    def validate_name(self, key, name):
        # ... validation logic
```

### After (Using Middleware):
```python
# 10 lines!
from kailash.middleware.database import BaseWorkflowModel

class StudioWorkflow(BaseWorkflowModel):
    __tablename__ = "studio_workflows"
    
    # All fields inherited!
    # Only add Studio-specific customizations
```

## Best Practices

### 1. Always Extend Base Models
Don't create models from scratch:
```python
# ❌ Wrong
class MyModel(Base):
    # Reinventing the wheel
    
# ✅ Correct  
class MyModel(BaseWorkflowModel):
    # Inherit enterprise features
```

### 2. Use Repository Pattern
Don't write raw queries for common operations:
```python
# ❌ Wrong
workflow = await session.execute(
    select(Workflow).where(
        and_(
            Workflow.id == id,
            Workflow.tenant_id == tenant,
            Workflow.deleted_at.is_(None)
        )
    )
)

# ✅ Correct
workflow = await workflow_repo.get(session, id)
```

### 3. Let Middleware Handle Security
Don't manually implement multi-tenancy:
```python
# ❌ Wrong
query = select(Model).where(Model.tenant_id == tenant_id)

# ✅ Correct
async with db_manager.get_session(tenant_id) as session:
    # Automatic tenant filtering!
```

## Advanced Features

### 1. Event Listeners
Middleware provides automatic audit trails:
```python
# Automatic on all base models
@event.listens_for(BaseWorkflowModel, 'before_update')
def before_update(mapper, connection, target):
    target.updated_at = datetime.now(timezone.utc)
```

### 2. Performance Optimization
Built-in connection pooling and query optimization:
```python
# Automatic indexes on common patterns
- tenant_id + status
- created_at  
- session_id
```

### 3. Compliance Features
GDPR, SOC2, ISO27001 support built-in:
```python
# Automatic soft deletes
workflow.soft_delete("user123")  # Preserves data for compliance

# Audit trails
Every operation logged automatically

# Data retention
cleanup_old_data(days=2555)  # 7 years for compliance
```

## SDK Enhancement Roadmap

Based on Studio's patterns, these features are coming to middleware:

1. **Automatic Statistics** - `db_manager.get_stats(tenant_id)`
2. **Bulk Operations** - `db_manager.bulk_insert(models)`
3. **Data Export** - `db_manager.export_for_compliance()`
4. **Performance Monitoring** - Built-in query analysis

## Summary

The middleware database layer provides:
- ✅ 80% less code to write
- ✅ Enterprise features out-of-the-box
- ✅ Consistent patterns across apps
- ✅ Performance optimizations
- ✅ Security and compliance built-in

Stop reinventing the wheel - use the middleware database layer!