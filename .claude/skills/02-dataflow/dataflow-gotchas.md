---
name: dataflow-gotchas
description: "Common DataFlow mistakes and misunderstandings. Use when DataFlow issues, gotchas, common mistakes DataFlow, troubleshooting DataFlow, or DataFlow problems."
---

# DataFlow Common Gotchas

Common misunderstandings and mistakes when using DataFlow, with solutions.

> **Skill Metadata**
> Category: `dataflow`
> Priority: `HIGH`
> SDK Version: `0.9.25+ / DataFlow 0.6.0`
> Related Skills: [`dataflow-models`](#), [`dataflow-crud-operations`](#), [`dataflow-nexus-integration`](#)
> Related Subagents: `dataflow-specialist` (complex troubleshooting)

## Quick Reference

- **NOT an ORM**: DataFlow is workflow-native, not like SQLAlchemy
- **Template Syntax**: DON'T use `${}` - conflicts with PostgreSQL
- **Connections**: Use connections, NOT template strings
- **Result Access**: `results["node"]["result"]`, not `results["node"]`

## Critical Gotchas

### 1. DataFlow is NOT an ORM

```python
# WRONG - Models are not instantiable
from dataflow import DataFlow
db = DataFlow()

@db.model
class User:
    name: str

user = User(name="John")  # FAILS - not supported by design
user.save()  # FAILS - no save() method
```

**Why**: DataFlow is workflow-native, not object-oriented. Models are schemas, not classes.

**Fix: Use Workflow Nodes**
```python
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "name": "John"  # Correct pattern
})
```

### 2. Template Syntax Conflicts with PostgreSQL

```python
# WRONG - ${} conflicts with PostgreSQL
workflow.add_node("OrderCreateNode", "create", {
    "customer_id": "${create_customer.id}"  # FAILS with PostgreSQL
})
```

**Fix: Use Workflow Connections**
```python
workflow.add_node("OrderCreateNode", "create", {
    "total": 100.0
})
workflow.add_connection("create_customer", "id", "create", "customer_id")
```

### 3. Nexus Integration Blocks Startup

```python
# WRONG - Blocks Nexus for minutes
db = DataFlow()  # Default auto_migrate=True
nexus = Nexus(dataflow_config={"integration": db})
```

**Fix: Critical Configuration**
```python
db = DataFlow(
    auto_migrate=False,
    skip_registry=True,
    existing_schema_mode=True
)
nexus = Nexus(dataflow_config={
    "integration": db,
    "auto_discovery": False  # CRITICAL
})
```

### 4. Wrong Result Access Pattern

```python
# WRONG - missing 'result' key
results, run_id = runtime.execute(workflow.build())
user_data = results["create_user"]  # Returns metadata, not data
user_id = user_data["id"]  # FAILS
```

**Fix: Access Through 'result'**
```python
results, run_id = runtime.execute(workflow.build())
user_data = results["create_user"]["result"]  # Correct
user_id = user_data["id"]  # Works
```

### 5. String IDs Forced to Integer (Pre-v0.4.0)

```python
# OLD ISSUE (pre-v0.4.0)
@db.model
class Session:
    id: str  # String IDs were converted to int

workflow.add_node("SessionReadNode", "read", {
    "id": "session-uuid-string"  # Failed - converted to int
})
```

**Fix: Upgrade to v0.4.0+**
```python
# Fixed in v0.4.0+ - string IDs preserved
@db.model
class Session:
    id: str  # Fully supported now

workflow.add_node("SessionReadNode", "read", {
    "id": "session-uuid-string"  # Works perfectly
})
```

### 6. VARCHAR(255) Content Limits (Pre-v0.4.0)

```python
# OLD ISSUE (pre-v0.4.0)
@db.model
class Article:
    content: str  # Was VARCHAR(255) - truncated!

# Long content failed or got truncated
```

**Fix: Automatic in v0.4.0+**
```python
# Fixed in v0.4.0+ - now TEXT type
@db.model
class Article:
    content: str  # Unlimited content - TEXT type
```

### 7. DateTime Serialization Issues (Pre-v0.4.0)

```python
# OLD ISSUE (pre-v0.4.0)
from datetime import datetime

workflow.add_node("OrderCreateNode", "create", {
    "due_date": datetime.now().isoformat()  # String failed validation
})
```

**Fix: Use Native datetime (v0.4.0+)**
```python
from datetime import datetime

workflow.add_node("OrderCreateNode", "create", {
    "due_date": datetime.now()  # Native datetime works
})
```

### 8. Multi-Instance Context Leaks (Pre-v0.4.0)

```python
# OLD ISSUE (pre-v0.4.0)
db_dev = DataFlow("sqlite:///dev.db")
db_prod = DataFlow("postgresql://...")

@db_dev.model
class DevModel:
    name: str

# Model leaked to db_prod instance!
```

**Fix: Fixed in v0.4.0+ (Context Isolation)**
```python
# Fixed in v0.4.0+ - proper isolation
db_dev = DataFlow("sqlite:///dev.db")
db_prod = DataFlow("postgresql://...")

@db_dev.model
class DevModel:
    name: str
# Only in db_dev, not in db_prod
```

## Documentation References

### Primary Sources
- **DataFlow Specialist**: [`.claude/skills/dataflow-specialist.md`](../../dataflow-specialist.md#L28-L72)
- **README**: [`sdk-users/apps/dataflow/README.md`](../../../../sdk-users/apps/dataflow/README.md)
- **DataFlow CLAUDE**: [`sdk-users/apps/dataflow/CLAUDE.md`](../../../../sdk-users/apps/dataflow/CLAUDE.md)

### Related Documentation
- **Troubleshooting**: [`sdk-users/apps/dataflow/docs/production/troubleshooting.md`](../../../../sdk-users/apps/dataflow/docs/production/troubleshooting.md)
- **Nexus Blocking Analysis**: [`sdk-users/apps/dataflow/docs/integration/nexus-blocking-issue-analysis.md`](../../../../sdk-users/apps/dataflow/docs/integration/nexus-blocking-issue-analysis.md)

## Related Patterns

- **For models**: See [`dataflow-models`](#)
- **For result access**: See [`dataflow-result-access`](#)
- **For Nexus integration**: See [`dataflow-nexus-integration`](#)
- **For connections**: See [`param-passing-quick`](#)

## When to Escalate to Subagent

Use `dataflow-specialist` when:
- Complex workflow debugging
- Performance optimization issues
- Migration failures
- Multi-database problems

## Quick Tips

- DataFlow is workflow-native, NOT an ORM
- Use connections, NOT `${}` template syntax
- Enable critical config for Nexus integration
- Access results via `results["node"]["result"]`
- v0.4.0+ fixes: string IDs, TEXT type, datetime, multi-instance

## Version Notes

- **v0.4.0+**: String ID support, TEXT type, datetime fix, multi-instance isolation
- **v0.9.4+**: Password special character support
- **v0.9.25+**: Threading fixes for Docker

## Keywords for Auto-Trigger

<!-- Trigger Keywords: DataFlow issues, gotchas, common mistakes DataFlow, troubleshooting DataFlow, DataFlow problems, DataFlow errors, not working, DataFlow bugs -->
