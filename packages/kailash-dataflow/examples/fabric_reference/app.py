# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Data Fabric Engine — Reference Application

Demonstrates the three new concepts that the Data Fabric Engine adds to
DataFlow:

1. db.source()    — Register external data sources (REST APIs, files,
                     cloud storage, databases, streams, or custom adapters).
2. @db.product()  — Define derived data products that auto-refresh when
                     their dependencies (models or sources) change.
3. await db.start() — Start the fabric runtime: connects sources, elects
                       a leader, pre-warms products, and begins change
                       detection.

This example uses MockSource so it runs with just ``pip install kailash-dataflow``
and SQLite — no external credentials or services required.
"""

from __future__ import annotations

import asyncio
import logging

from dataflow import DataFlow
from dataflow.fabric.testing import MockSource

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


# ── 1. Set up DataFlow with a SQLite database ─────────────────────────
db = DataFlow("sqlite:///fabric_reference.db")


# ── 2. Define a model (stored in SQLite) ──────────────────────────────
@db.model
class Task:
    """A simple task tracked in the local database."""

    title: str
    status: str
    assignee: str


# ── 3. Register an external source ───────────────────────────────────
#
#    In production you would use a config object:
#
#        from dataflow.fabric import RestSourceConfig, BearerAuth
#        db.source("todos", RestSourceConfig(
#            url="https://jsonplaceholder.typicode.com",
#            auth=BearerAuth(token_env="TODOS_API_TOKEN"),
#        ))
#
#    For this reference app we use MockSource so nothing external is needed.

todo_source = MockSource(
    name="todos",
    data={
        # Default path ("") returns the full payload
        "": {
            "items": [
                {"id": 1, "title": "Write docs", "done": False},
                {"id": 2, "title": "Ship v1", "done": True},
                {"id": 3, "title": "Plan roadmap", "done": False},
            ]
        },
    },
)

db.source("todos", todo_source)


# ── 4. Define a data product ─────────────────────────────────────────
#
#    Products are declarative data transformations. This one combines
#    local database records with external source data into a single
#    dashboard view.
#
#    - mode="materialized" (the default) means the result is pre-computed
#      and cached.  It refreshes automatically when Task records change
#      or the "todos" source reports new data.
#    - depends_on lists every model and source the product reads from.


@db.product("dashboard", depends_on=["Task", "todos"])
async def build_dashboard(ctx):
    """Combine local tasks with external todos into a dashboard summary.

    Args:
        ctx: A FabricContext providing:
            - ctx.express  — the DataFlow Express API for model CRUD
            - ctx.source() — handles for registered external sources
    """
    # Read local tasks from SQLite via Express API
    tasks = await ctx.express.list("Task")

    # Read external todos via the source handle
    todos_payload = await ctx.source("todos").read()
    todo_items = todos_payload.get("items", [])

    open_tasks = [t for t in tasks if t.get("status") != "done"]
    done_todos = [t for t in todo_items if t.get("done")]

    return {
        "local_tasks_total": len(tasks),
        "local_tasks_open": len(open_tasks),
        "external_todos_total": len(todo_items),
        "external_todos_done": len(done_todos),
        "summary": (
            f"{len(open_tasks)} open tasks locally, "
            f"{len(done_todos)}/{len(todo_items)} external todos completed"
        ),
    }


# ── 5. Run the fabric ────────────────────────────────────────────────


async def main() -> None:
    """Start the fabric, seed data, and inspect the dashboard product."""

    # Seed some local task records via the Express API
    await db.express.create(
        "Task",
        {
            "title": "Implement login",
            "status": "in_progress",
            "assignee": "Alice",
        },
    )
    await db.express.create(
        "Task",
        {
            "title": "Fix bug #42",
            "status": "done",
            "assignee": "Bob",
        },
    )
    await db.express.create(
        "Task",
        {
            "title": "Deploy staging",
            "status": "open",
            "assignee": "Alice",
        },
    )

    # Start the fabric runtime in dev mode.
    # dev_mode=True skips leader election, uses in-memory caching, and
    # reduces poll intervals — ideal for local development.
    fabric = await db.start(dev_mode=True)

    logger.info("Fabric started (leader=%s)", fabric.is_leader)

    # Inspect the runtime status
    status = fabric.status()
    logger.info(
        "Sources: %s  Products: %s",
        list(status["sources"].keys()),
        status["products"],
    )

    # Read the dashboard product result.
    # After start(), materialized products have been pre-warmed so the
    # cached result is immediately available.
    info = fabric.product_info("dashboard")
    logger.info("Dashboard product info: %s", info)

    # Graceful shutdown
    await db.stop()
    logger.info("Fabric stopped")


if __name__ == "__main__":
    asyncio.run(main())
