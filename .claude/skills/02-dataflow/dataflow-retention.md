---
name: dataflow-retention
description: "Data retention policies for DataFlow models -- archive, delete, and partition. Use when asking about 'retention policy', 'data retention', 'archive old data', 'delete old records', 'partition policy', 'RetentionEngine', or 'data lifecycle'."
---

# DataFlow Retention Policies

Automated data retention via archive, delete, or partition policies declared on models.

## Quick Reference

| Feature     | Details                                                                |
| ----------- | ---------------------------------------------------------------------- |
| Policies    | `archive`, `delete`, `partition`                                       |
| Declaration | `__dataflow__ = {"retention": {"policy": "delete", "after_days": 90}}` |
| Access      | `db.retention` after `db.initialize()`                                 |
| Execution   | `await db.retention.run()` or `db.retention.run_sync()`                |
| Dry run     | `await db.retention.run(dry_run=True)`                                 |

## Policy Types

### Delete Policy

Hard-delete records older than the cutoff:

```python
@db.model
class AuditLog:
    id: str
    action: str
    created_at: str  # DataFlow auto-manages this

    __dataflow__ = {
        "retention": {
            "policy": "delete",
            "after_days": 90,
            "cutoff_field": "created_at",  # default
        }
    }
```

### Archive Policy

Move old records to an archive table (INSERT + DELETE in a single transaction):

```python
@db.model
class Order:
    id: str
    total: float
    created_at: str

    __dataflow__ = {
        "retention": {
            "policy": "archive",
            "after_days": 365,
            "archive_table": "orders_archive",  # Target table
        }
    }
```

### Partition Policy

PostgreSQL range partitioning (raises on non-PostgreSQL databases):

```python
@db.model
class Event:
    id: str
    event_type: str
    created_at: str

    __dataflow__ = {
        "retention": {
            "policy": "partition",
            "after_days": 30,
        }
    }
```

## Running Retention

```python
# Execute all registered policies
results = await db.retention.run()
for result in results:
    print(f"{result.model_name}: {result.affected_rows} rows affected")

# Dry run (preview without executing)
results = await db.retention.run(dry_run=True)
for result in results:
    print(f"[DRY RUN] {result.model_name}: {result.affected_rows} would be affected")

# Run a single model's policy
result = await db.retention.execute("AuditLog")
```

## RetentionResult

```python
result.model_name     # "AuditLog"
result.policy         # "delete"
result.affected_rows  # Total rows affected
result.archived_rows  # Rows moved to archive (archive policy only)
result.deleted_rows   # Rows deleted
result.dry_run        # True if dry run
result.error          # None or error message
```

## Security

- All table names validated against `[a-zA-Z_][a-zA-Z0-9_]*` regex (SQL injection prevention)
- Cutoff field name also validated
- Archive table name validated at registration time

## Source Code

- `packages/kailash-dataflow/src/dataflow/features/retention.py` -- RetentionEngine
- `packages/kailash-dataflow/tests/unit/test_retention_engine.py` -- Unit tests
