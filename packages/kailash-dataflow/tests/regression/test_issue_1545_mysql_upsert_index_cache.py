# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1545 — MySQL single-record upsert re-queried
``information_schema.statistics`` on EVERY call.

The #1537 conflict-target precheck reads a table's UNIQUE/PRIMARY index column-sets
from ``information_schema.statistics`` to decide whether ``conflict_on`` is backed
by a real key. That lookup ran on every single-record MySQL upsert. The fix caches
the per-table index column-sets on the DataFlow instance
(``engine._unique_index_cache``, a sibling of the ADR-001 schema cache), populated
once per table per process and invalidated by the same
``clear_schema_cache`` / ``clear_table_cache`` hooks schema changes use.

The fix is correctness-neutral: the precheck STILL raises
``UpsertConflictTargetError`` when ``conflict_on`` has no matching unique index,
whether the cache is cold, warm, or freshly invalidated after an index change.

The query count is measured by a real-infrastructure SPY that wraps the precheck
node's ``async_run`` and DELEGATES to the real MySQL call (NO mocking — every
counted call executes against the live database).

Test design note: these tests use ``auto_migrate=False`` + explicit test-fixture
DDL (permitted by ``schema-migration.md`` § scope-clarification) to create the
table with known indexes. This isolates the #1545 upsert index-cache behavior
under test from an UNRELATED pre-existing bug in the legacy
``auto_migration_system`` fallback path (which mis-detects ``mysql://`` as
PostgreSQL and emits Postgres-only migration-table DDL — ``TIMESTAMP WITH TIME
ZONE`` / ``JSONB`` / ``USING GIN`` — that syntax-errors on MySQL). That migration
bug is out of scope for #1545 and reported separately.

Permanent regression tests — NEVER delete (``rules/testing.md`` Regression).
"""

from __future__ import annotations

import os
import time

import pytest

from dataflow import DataFlow
from dataflow.core.exceptions import UpsertConflictTargetError

# aiomysql surfaces MySQL's Note 1051 ("Unknown table") as a Python Warning on an
# idempotent ``DROP TABLE IF EXISTS`` of an already-absent table (the defensive
# drop-before-create in the fixtures below). This is a benign driver quirk, not a
# test defect — the ``IF EXISTS`` guard is correct. Filter it so the suite is
# WARN-clean per ``observability.md`` Rule 5.
pytestmark = pytest.mark.filterwarnings("ignore:.*Unknown table.*")

MYSQL_URL = os.getenv(
    "TEST_MYSQL_URL", "mysql://kailash_test:test_password@localhost:3307/kailash_test"
)


def _uid(prefix: str = "u") -> str:
    return f"{prefix}-{int(time.time() * 1_000_000)}"


async def _run_ddl(sql: str) -> None:
    """Execute a DDL statement on real MySQL (test-fixture DDL is permitted by
    ``schema-migration.md`` § scope-clarification)."""
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    node = AsyncSQLDatabaseNode(
        connection_string=MYSQL_URL,
        database_type="mysql",
        query=sql,
        validate_queries=False,
    )
    await node.async_run()
    await node.cleanup()


class _InfoSchemaCounter:
    """Real-infra spy: counts information_schema.statistics round-trips by wrapping
    the cached precheck node's ``async_run`` and delegating to the real call. This
    is NOT a mock — the wrapped call hits the live MySQL database."""

    def __init__(self, node):
        self._node = node
        self._orig = node.async_run
        self.count = 0
        node.async_run = self._counting

    async def _counting(self, *args, **kwargs):
        # Faithfully delegate BOTH positional and keyword args to the real call.
        query = kwargs.get("query") or (args[0] if args else "") or ""
        if isinstance(query, str) and "information_schema.statistics" in query:
            self.count += 1
        return await self._orig(*args, **kwargs)

    def uninstall(self):
        self._node.async_run = self._orig


# ---------------------------------------------------------------------------
# Tier-2: real MySQL — precheck queries information_schema at most once/table
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_mysql_upsert_precheck_queries_information_schema_at_most_once():
    """AC: the conflict-target precheck queries information_schema AT MOST once per
    table per process (warm cache serves subsequent upserts), the cache is
    invalidated on an index change, and ``UpsertConflictTargetError`` STILL raises
    with the cache warm — measured by a real-DB round-trip counter (no mocking)."""
    table = "issue1545_caches"
    await _run_ddl(f"DROP TABLE IF EXISTS {table}")
    await _run_ddl(
        f"CREATE TABLE {table} "
        f"(id VARCHAR(255) PRIMARY KEY, tag VARCHAR(255), body VARCHAR(255))"
    )

    db = DataFlow(MYSQL_URL, auto_migrate=False)

    @db.model
    class Issue1545Cache:
        id: str
        tag: str  # NOT unique — the precheck must reject conflict_on=["tag"]
        body: str

    # Wrap the cached precheck node so the counter sees every information_schema
    # round-trip the upsert path makes.
    precheck_node = db._get_or_create_async_sql_node("mysql")
    counter = _InfoSchemaCounter(precheck_node)

    try:
        # (1) Cold cache → 1 information_schema query; conflict_on non-unique raises.
        with pytest.raises(UpsertConflictTargetError):
            await db.express.upsert(
                "Issue1545Cache",
                {"id": _uid("r"), "tag": "t", "body": "one"},
                conflict_on=["tag"],
            )
        assert counter.count == 1
        # Cache populated on the instance.
        assert any(k.endswith(f":{table}") for k in db._unique_index_cache)

        # (2) Warm cache → NO additional information_schema query; STILL raises.
        with pytest.raises(UpsertConflictTargetError):
            await db.express.upsert(
                "Issue1545Cache",
                {"id": _uid("r"), "tag": "t", "body": "two"},
                conflict_on=["tag"],
            )
        assert counter.count == 1  # at most once per table per process

        # (3) Index change: add a UNIQUE index on tag, then invalidate the cache
        # through the documented schema-change hook.
        await _run_ddl(f"ALTER TABLE {table} ADD UNIQUE INDEX uq_tag (tag)")
        db.clear_table_cache("Issue1545Cache")
        assert not any(k.endswith(f":{table}") for k in db._unique_index_cache)

        # (4) After invalidation the precheck RE-READS information_schema (count
        # increments) and now sees tag as unique → the upsert SUCCEEDS. Proves
        # the cache was invalidated (not stale) AND correctness is preserved.
        tag = _uid("tag")
        await db.express.upsert(
            "Issue1545Cache",
            {"id": _uid("r"), "tag": tag, "body": "three"},
            conflict_on=["tag"],
        )
        assert counter.count == 2  # exactly one re-read after invalidation
        rows = await db.express.list("Issue1545Cache", {"tag": tag})
        assert len(rows) == 1 and rows[0]["body"] == "three"
    finally:
        counter.uninstall()
        await _run_ddl(f"DROP TABLE IF EXISTS {table}")
        db.close()


@pytest.mark.regression
@pytest.mark.integration
async def test_mysql_clear_schema_cache_invalidates_index_cache():
    """AC: ``clear_schema_cache()`` (the full external-schema-change hook) also
    clears the unique-index cache — the next upsert re-reads information_schema."""
    table = "issue1545_fulls"
    await _run_ddl(f"DROP TABLE IF EXISTS {table}")
    await _run_ddl(
        f"CREATE TABLE {table} "
        f"(id VARCHAR(255) PRIMARY KEY, tag VARCHAR(255), body VARCHAR(255))"
    )

    db = DataFlow(MYSQL_URL, auto_migrate=False)

    @db.model
    class Issue1545Full:
        id: str
        tag: str
        body: str

    try:
        with pytest.raises(UpsertConflictTargetError):
            await db.express.upsert(
                "Issue1545Full",
                {"id": _uid("r"), "tag": "t", "body": "one"},
                conflict_on=["tag"],
            )
        assert any(k.endswith(f":{table}") for k in db._unique_index_cache)

        db.clear_schema_cache()
        assert db._unique_index_cache == {}
    finally:
        await _run_ddl(f"DROP TABLE IF EXISTS {table}")
        db.close()
