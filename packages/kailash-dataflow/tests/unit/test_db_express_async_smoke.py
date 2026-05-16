"""Tier-1 smoke test for the canonical ``db.express`` async CRUD surface.

Issue #998 (B-4 of #979 Workstream-B). Value-anchor — issue #979 brief
AC#6 verbatim (``workspaces/issue-979-dataflow-unit-triage/briefs/
00-brief.md:51-52``):

    "After moves: `pytest packages/kailash-dataflow/tests/unit -x`
    exits 0 in <=2 min without `[fabric]` / PostgreSQL."

S6 verified the tier-1 contract holds (52s on CI py3.11). This file
closes a coverage gap: ``db.express`` create / read / list / update /
count / delete were exercised only by the integration tier (real
PostgreSQL). This adds a Tier-1 smoke that exercises the same canonical
surface against SQLite, with read-back verification of every mutation
(``rules/testing.md`` § State Persistence Verification — assert the
persisted value, not the mutation's return value).

Fixture choice — why ``file_test_suite``, not ``memory_dataflow``:
``db.express`` async CRUD dispatches across the runtime's thread-pool
executor. SQLite ``:memory:`` has thread-affinity (each thread gets a
SEPARATE in-memory database — DataFlow emits an explicit runtime
warning about this), so a table created on the fixture connection is
invisible to express's executor thread. ``specs/testing-tiers.md``
§ Tier-1 sanctions BOTH memory AND file SQLite and lists
``file_test_suite`` for "tests requiring persistence across
operations" — async express CRUD is exactly that. The table is created
through the sanctioned ``file_test_suite`` infrastructure connection
(test-fixture schema DDL is permitted per ``schema-migration.md``
Rule 1 scope clarification + ``testing-tiers.md`` Rule 2 — this is NOT
ad-hoc ``DataFlow(...)`` instantiation; the DataFlow instance comes
from the standardized ``dataflow_harness``).

Tier-1: file SQLite only, no Docker / PostgreSQL / Redis, no deps
beyond ``[dev]``, well under the <2 min suite budget.
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_db_express_async_crud_roundtrip(file_test_suite):
    """Exercise the full canonical ``db.express`` async CRUD surface with
    read-back verification of every mutation.

    Canonical surface (repo ``CLAUDE.md`` § Critical Execution Rules):
    ``create`` / ``read`` / ``list`` / ``update`` / ``count`` /
    ``delete``. Each mutation is followed by an independent ``read`` (or
    ``list`` / ``count``) that asserts the PERSISTED state — not the
    mutation call's return value (``rules/testing.md`` § State
    Persistence Verification).
    """
    harness = file_test_suite.dataflow_harness
    # Test-fixture schema (sanctioned: schema-migration.md Rule 1 scope
    # clarification — DDL is permitted in test fixtures that create/tear
    # down test schemas). Table name matches DataFlow's pluralization of
    # the model class name (``Widget`` -> ``widgets``).
    async with harness.infrastructure.connection() as conn:
        await conn.execute(
            """
            CREATE TABLE widgets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await conn.commit()

    db = harness.create_dataflow()
    try:

        @db.model
        class Widget:
            id: str
            name: str
            email: str
            active: bool = True

        await db.initialize()

        # ---- CREATE -------------------------------------------------
        created = await db.express.create(
            "Widget",
            {
                "id": "w-1",
                "name": "alpha",
                "email": "alpha@example.com",
                "active": True,
            },
        )
        assert created is not None
        assert created["id"] == "w-1"
        # Read-back: the row actually persisted, independent of the
        # create() return value.
        persisted = await db.express.read("Widget", "w-1")
        assert persisted is not None
        assert persisted["name"] == "alpha"
        assert persisted["email"] == "alpha@example.com"

        # ---- READ (miss) -------------------------------------------
        missing = await db.express.read("Widget", "does-not-exist")
        assert missing is None

        # ---- LIST + COUNT ------------------------------------------
        await db.express.create(
            "Widget",
            {"id": "w-2", "name": "beta", "email": "beta@example.com", "active": False},
        )
        active_rows = await db.express.list("Widget", {"active": True})
        assert [r["id"] for r in active_rows] == ["w-1"]
        assert await db.express.count("Widget", {}) == 2
        assert await db.express.count("Widget", {"active": True}) == 1

        # ---- UPDATE -------------------------------------------------
        await db.express.update("Widget", "w-1", {"name": "alpha-renamed"})
        # Read-back: the persisted row reflects the update.
        after_update = await db.express.read("Widget", "w-1")
        assert after_update["name"] == "alpha-renamed"
        # The non-updated field is unchanged.
        assert after_update["email"] == "alpha@example.com"

        # ---- DELETE -------------------------------------------------
        deleted = await db.express.delete("Widget", "w-1")
        assert deleted is True
        # Read-back: the row is gone; count + list reflect the deletion.
        assert await db.express.read("Widget", "w-1") is None
        assert await db.express.count("Widget", {}) == 1
        assert [r["id"] for r in await db.express.list("Widget", {})] == ["w-2"]
    finally:
        await db.close_async()
