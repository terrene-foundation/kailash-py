# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Level 1: Durable database-backed persistence.

The same workflow as Level 0, but with KAILASH_DATABASE_URL set.
All stores automatically switch to database-backed backends.

Usage:
    export KAILASH_DATABASE_URL=postgresql://kailash:kailash@localhost:5432/kailash
    python level1_app.py

Or with SQLite for local testing:
    export KAILASH_DATABASE_URL=sqlite:///kailash_level1.db
    python level1_app.py
"""

import asyncio
import os

from kailash import WorkflowBuilder, LocalRuntime
from kailash.infrastructure import StoreFactory


def build_workflow():
    """Build the same workflow used at every level."""
    builder = WorkflowBuilder()

    builder.add_node(
        "PythonCodeNode",
        "generate",
        {
            "code": (
                "import datetime\n"
                "now = datetime.datetime.now(datetime.timezone.utc)\n"
                "output = f'Report generated at {now.isoformat()}'\n"
            ),
            "output_type": "str",
        },
    )

    builder.add_node(
        "PythonCodeNode",
        "transform",
        {
            "code": "output = text.upper().replace(' ', '_')",
            "inputs": {"text": "str"},
            "output_type": "str",
        },
    )

    builder.connect("generate", "transform", mapping={"output": "text"})

    return builder.build()


async def show_infrastructure_status() -> None:
    """Show which infrastructure level is active."""
    db_url = os.environ.get("KAILASH_DATABASE_URL") or os.environ.get("DATABASE_URL")

    if db_url is None:
        print("Infrastructure: Level 0 (no database URL set)")
        print("  Stores: SQLite/in-memory defaults")
        return

    # Mask credentials in the URL for display
    safe_url = db_url.split("@")[-1] if "@" in db_url else db_url
    print(f"Infrastructure: Level 1 (database: {safe_url})")

    factory = StoreFactory()
    print(f"  Level 0 mode: {factory.is_level0}")

    if not factory.is_level0:
        # Initialize and show store types
        event_store = await factory.create_event_store()
        exec_store = await factory.create_execution_store()
        idempotency = await factory.create_idempotency_store()

        print(f"  EventStore: {type(event_store).__name__}")
        print(f"  ExecutionStore: {type(exec_store).__name__}")
        print(
            f"  IdempotencyStore: {type(idempotency).__name__ if idempotency else 'None'}"
        )

        await factory.close()


def main() -> None:
    # Show infrastructure status
    asyncio.run(show_infrastructure_status())

    # Build and execute -- identical to Level 0
    wf = build_workflow()

    runtime = LocalRuntime()
    results, run_id = runtime.execute(wf)

    print(f"\nRun ID: {run_id}")
    print(f"Generate output: {results.get('generate', {})}")
    print(f"Transform output: {results.get('transform', {})}")


if __name__ == "__main__":
    main()
