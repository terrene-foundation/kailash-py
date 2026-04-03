# Data Fabric Engine — Reference Application

Minimal example demonstrating the three concepts the Data Fabric Engine adds to DataFlow.

## What it shows

| Concept     | API                                     | Purpose                                                                                                 |
| ----------- | --------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| **Source**  | `db.source("name", config_or_adapter)`  | Register an external data endpoint (REST API, file, cloud bucket, database, stream, or custom adapter). |
| **Product** | `@db.product("name", depends_on=[...])` | Define a derived data view that auto-refreshes when its dependencies change.                            |
| **Start**   | `await db.start(dev_mode=True)`         | Boot the fabric runtime: connect sources, elect a leader, pre-warm products, begin change detection.    |

## How it works

1. A `Task` model is defined in SQLite (the local database).
2. A `MockSource` named `"todos"` provides in-memory data that simulates an external REST API.
3. A `"dashboard"` product combines local tasks with external todos into a summary dict.
4. `await db.start(dev_mode=True)` connects everything and pre-warms the product cache.

## Prerequisites

```bash
pip install kailash-dataflow
```

No external services, API keys, or Docker containers are required. The example uses SQLite and MockSource.

## Run

```bash
python app.py
```

Expected output:

```
INFO  Fabric started (leader=True)
INFO  Sources: ['todos']  Products: ['dashboard']
INFO  Dashboard product info: {'name': 'dashboard', 'mode': 'materialized', ...}
INFO  Fabric stopped
```

## Replacing MockSource with a real source

To connect a real REST API instead of MockSource, swap the source registration:

```python
from dataflow.fabric import RestSourceConfig, BearerAuth

db.source("todos", RestSourceConfig(
    url="https://api.example.com",
    auth=BearerAuth(token_env="TODOS_API_TOKEN"),
    poll_interval=60,
))
```

The product function (`build_dashboard`) stays exactly the same — it reads through `ctx.source("todos")` regardless of the underlying adapter.

## File structure

```
fabric_reference/
    app.py      — The complete reference application
    README.md   — This file
```
