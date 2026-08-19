---
name: dataflow-derived-models
description: "DerivedModelEngine -- application-layer materialized views for DataFlow. Use when asking about 'derived model', 'materialized view', '@db.derived_model', 'computed model', 'scheduled refresh', 'on_source_change', or 'DerivedModelEngine'."
---

# DataFlow Derived Models

Application-layer materialized views that compute derived data from source models with scheduled, manual, or event-driven refresh.

> **Skill Metadata**
> Category: `dataflow`
> Priority: `MEDIUM`
> Related Skills: [`dataflow-events`](dataflow-events.md), [`dataflow-express`](dataflow-express.md)
> Related Subagents: `dataflow-specialist`

## Quick Reference

| Concept         | Details                                                                           |
| --------------- | --------------------------------------------------------------------------------- |
| Decorator       | `@db.derived_model(sources=["Model1"], refresh="scheduled", schedule="every 6h")` |
| Refresh modes   | `scheduled`, `manual`, `on_source_change`                                         |
| Status API      | `db.derived_model_status()`                                                       |
| Manual refresh  | `await db.refresh_derived("ModelName")`                                           |
| Cycle detection | Automatic at `db.initialize()` time                                               |
| Limitation      | Loads all source records into memory (use SQL views for huge tables)              |

## Usage

### Scheduled Refresh

```python
from dataflow import DataFlow

db = DataFlow("sqlite:///app.db")

@db.model
class Order:
    id: str
    customer_id: str
    total: float
    created_at: str

@db.derived_model(
    sources=["Order"],
    refresh="scheduled",
    schedule="every 6h",  # or cron: "0 */6 * * *"
)
class OrderSummary:
    id: str
    customer_id: str
    order_count: int
    total_spent: float

    @staticmethod
    def compute(sources: dict) -> list[dict]:
        """Transform source data into derived records."""
        orders = sources["Order"]
        by_customer: dict = {}
        for order in orders:
            cid = order["customer_id"]
            if cid not in by_customer:
                by_customer[cid] = {"count": 0, "total": 0.0}
            by_customer[cid]["count"] += 1
            by_customer[cid]["total"] += order["total"]

        return [
            {
                "id": cid,
                "customer_id": cid,
                "order_count": data["count"],
                "total_spent": data["total"],
            }
            for cid, data in by_customer.items()
        ]
```

### Manual Refresh

```python
@db.derived_model(sources=["Order"], refresh="manual")
class AdHocReport:
    id: str
    metric: float

    @staticmethod
    def compute(sources):
        # ...
        return [{"id": "summary", "metric": 42.0}]

# Trigger manually
result = await db.refresh_derived("AdHocReport")
# result.records_upserted, result.duration_ms, result.sources_queried
```

### On Source Change (Event-Driven)

```python
@db.derived_model(
    sources=["Order"],
    refresh="on_source_change",
    debounce_ms=200,  # Debounce window (default: 100ms)
)
class LiveOrderStats:
    id: str
    total_orders: int

    @staticmethod
    def compute(sources):
        return [{"id": "live", "total_orders": len(sources["Order"])}]
```

When any write operation (create, update, delete, upsert, bulk\_\*) occurs on `Order`, a debounced async refresh fires automatically. Uses Core SDK EventBus integration (see `dataflow-events.md`).

## Schedule Formats

| Format          | Example                                   | Requires               |
| --------------- | ----------------------------------------- | ---------------------- |
| Fixed interval  | `"every 5m"`, `"every 6h"`, `"every 30s"` | Nothing                |
| Cron expression | `"0 */6 * * *"`                           | `pip install croniter` |

## Status Monitoring

```python
status = db.derived_model_status()
for name, meta in status.items():
    print(f"{name}: {meta.status} (last: {meta.last_refreshed})")
    # status values: "pending", "refreshing", "ok", "error"
    # meta.last_error shows the most recent failure reason
```

## RefreshResult

```python
result = await db.refresh_derived("OrderSummary")
result.model_name       # "OrderSummary"
result.records_upserted # Number of records written
result.duration_ms      # Execution time
result.sources_queried  # {"Order": 1500} — record counts per source
result.error            # None or error message
```

## Circular Dependency Detection

At `db.initialize()`, the engine runs DFS cycle detection across all derived model source dependencies. If model A sources model B and model B sources model A (transitively), a `CircularDependencyError` is raised.

## Caveats

- **Memory**: All source records are loaded into memory via `db.express.list(src, limit=None)`. For tables exceeding available RAM, use SQL materialized views directly.
- **Consistency**: Refresh is eventually consistent. The `on_source_change` mode has a configurable debounce window (default 100ms) to batch rapid writes.
- **Compute function**: Must be a static method returning `list[dict]`. Each dict must include an `id` field.

## Source Code

- the dataflow package (`src/dataflow/features/derived.py`) -- DerivedModelEngine, scheduler, cycle detection
- the dataflow package (`tests/unit/test_derived_model.py`) -- Unit tests
