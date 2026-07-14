# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1560 — the ``$11`` param-type-cast retry inside
``core/nodes.py`` create ``async_run`` leaked an ``AsyncSQLDatabaseNode``.

When a PostgreSQL create raised "could not determine data type of parameter
$11", the create path built a FRESH (non-pooled) ``AsyncSQLDatabaseNode`` and
awaited ``async_run`` on it to retry with a ``$11::integer`` cast — but never
called ``cleanup()``. Each retry leaked one connection
(``ResourceWarning: AsyncSQLDatabaseNode GC'd while still connected``). This is
the same leak class the 2.13.15 fixes closed in
``bulk_upsert._execute_query`` and ``BulkCreatePoolNode._process_direct``; the
retry node was the last un-cleaned throwaway. The fix wraps the retry
``async_run`` in ``try/finally: await sql_node.cleanup()``.

The retry branch is a defensive legacy path: current DataFlow INSERTs anchor
every ``$N`` to its target column, so real PostgreSQL no longer emits the
"$11" type-inference error through the public create API. These Tier-2 tests
therefore reproduce the EXACT node lifecycle the fix governs against the real
PostgreSQL container (``tests/CLAUDE.md`` Tier-2, NO mocking): a fresh
throwaway ``AsyncSQLDatabaseNode`` runs the ``$11::integer`` retry query
(real writes, read-back verified) under the fix's ``try/finally`` cleanup and
emits ZERO ``AsyncSQLDatabaseNode GC'd while still connected`` warnings — plus
a source pin tying that cleanup pattern to the retry site. The GC-warning
sentinel only fires when a node is finalized WHILE still connected, so a clean
run proves ``cleanup()`` closed the connection (the leak the fix removes).

Permanent regression tests — NEVER delete (``rules/testing.md`` Regression).
"""

from __future__ import annotations

import gc
import os
import time
import warnings
from pathlib import Path

import pytest
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

PG_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://test_user:test_password@localhost:5432/astra_test",
)

_GC_LEAK_SENTINEL = "AsyncSQLDatabaseNode GC'd while still connected"


async def _make_retry_table() -> str:
    """Create the real 11-column PG table the retry query targets; return its name."""
    table = f"df1560_retry_{int(time.time() * 1_000_000)}"
    cols = ", ".join(f"f{i} INTEGER" for i in range(1, 12))
    ddl = AsyncSQLDatabaseNode(
        connection_string=PG_URL,
        database_type="postgresql",
        query=f"CREATE TABLE {table} (id SERIAL PRIMARY KEY, {cols})",
        validate_queries=False,
    )
    try:
        await ddl.async_run()
    finally:
        await ddl.cleanup()
    return table


async def _drop_table(table: str) -> None:
    drop = AsyncSQLDatabaseNode(
        connection_string=PG_URL,
        database_type="postgresql",
        query=f"DROP TABLE IF EXISTS {table}",
        validate_queries=False,
    )
    try:
        await drop.async_run()
    finally:
        await drop.cleanup()


def _retry_query(table: str) -> str:
    """The exact shape the #1560 retry builds: a ``$11::integer`` cast RETURNING."""
    placeholders = ", ".join(
        f"${i}" if i != 11 else "$11::integer" for i in range(1, 12)
    )
    cols = ", ".join(f"f{i}" for i in range(1, 12))
    return f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) RETURNING id"


# ---------------------------------------------------------------------------
# Tier-2: real PostgreSQL — the retry node lifecycle is leak-free WITH cleanup
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_retry_node_cleanup_emits_no_resourcewarning():
    """AC (#1560 fix): the retry node lifecycle the fix wraps — a fresh
    ``AsyncSQLDatabaseNode`` -> ``async_run`` (``$11::integer`` cast) ->
    ``cleanup()`` — emits ZERO ``AsyncSQLDatabaseNode GC'd while still
    connected`` warnings on real PostgreSQL."""
    table = await _make_retry_table()
    query = _retry_query(table)
    values = list(range(1, 12))
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for _ in range(3):
                # Mirror nodes.py:2127-2147 exactly.
                sql_node = AsyncSQLDatabaseNode(
                    connection_string=PG_URL, database_type="postgresql"
                )
                try:
                    result = await sql_node.async_run(
                        query=query,
                        params=values,
                        fetch_mode="one",
                        validate_queries=False,
                        transaction_mode="auto",
                    )
                finally:
                    await sql_node.cleanup()
                assert result and "result" in result
                del sql_node
            gc.collect()  # force finalizers; a leaked node would warn here
        leaks = [str(w.message) for w in caught if _GC_LEAK_SENTINEL in str(w.message)]
        assert leaks == [], f"retry node leaked connections: {leaks}"

        # Read-back: all three retry inserts landed (real writes, real infra).
        probe = AsyncSQLDatabaseNode(
            connection_string=PG_URL,
            database_type="postgresql",
            query=f"SELECT COUNT(*) AS n FROM {table}",
            validate_queries=False,
        )
        try:
            rows = (await probe.async_run())["result"]["data"]
        finally:
            await probe.cleanup()
        assert rows[0]["n"] == 3
    finally:
        await _drop_table(table)


# ---------------------------------------------------------------------------
# Source pin: the retry site wraps async_run in try/finally cleanup (#1560)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_retry_site_wraps_async_run_in_cleanup():
    """Complement to the behavioral tests above: pin that the ``$11`` retry block
    in ``core/nodes.py`` cleans up its throwaway node, so a future refactor cannot
    silently drop the fix. Not a sole assertion — the Tier-2 tests above prove the
    runtime contract (``rules/testing.md`` Behavioral Regression)."""
    src = Path(__file__).resolve().parents[2] / "src/dataflow/core/nodes.py"
    text = src.read_text()
    # Locate the $11 retry block, then the throwaway (non-pooled) node it
    # constructs. #1581 routes the in-scope retry through the POOLED node (the
    # pool owns that connection's lifecycle, so it needs no explicit cleanup);
    # only the no-scope path builds a fresh AsyncSQLDatabaseNode, and THAT is the
    # node the #1560 leak-fix must clean up. Anchor on the fresh-node
    # construction so a legitimate scope-branch insertion above it (as #1581 did)
    # cannot silently slide the cleanup out of a fixed char window.
    anchor = text.index("PARAM $11 FIX: Detected parameter $11 issue")
    # Anchor the tail on the fresh-node construction ITSELF (absolute index),
    # windowed to the construction->cleanup span plus margin. The prior form
    # sliced ``text[anchor:anchor+4000]`` then took the tail from the
    # construction, so the effective window was bounded by the DISTANT $11
    # marker — a legitimate kwarg insertion INTO the construction (the #1741
    # credential_provider) slid the cleanup past anchor+4000 even though it is
    # still present (line ~2248). Following the construction realizes this
    # test's stated intent robustly; the behavioral Tier-2 tests above prove
    # the runtime leak-free contract, this is only the source pin.
    node_pos = text.index("sql_node = AsyncSQLDatabaseNode(", anchor)
    tail = text[node_pos : node_pos + 2600]
    assert "await sql_node.cleanup()" in tail, (
        "the #1560 retry node is no longer cleaned up — the throwaway "
        "AsyncSQLDatabaseNode leak has been reintroduced"
    )
    assert "finally:" in tail
