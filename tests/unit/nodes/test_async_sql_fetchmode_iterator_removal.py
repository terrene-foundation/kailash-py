"""Regression: FetchMode.ITERATOR removed; adapters reject unknown modes loudly.

The ``iterator`` fetch mode was a category error — a lazily-yielding async stream
cannot be a materializing fetch *return value* (ONE/ALL/MANY all return a value).
It was never implemented: it raised ``NotImplementedError`` on PostgreSQL and
silently returned ``None`` (MySQL) / ``[]`` (SQLite). It is removed in favour of a
dedicated streaming API (``stream()``); the per-adapter fetch dispatch now raises a
typed ``ValueError`` for any unrecognized mode instead of falling through silently
(``zero-tolerance.md`` Rule 3 — no silent fallbacks).

Guards against (a) the dead enum member returning, (b) the node silently accepting
``fetch_mode="iterator"`` again, and (c) the adapter silent-fallback behaviour
(``None``/``[]``) re-appearing.

Lives under ``tests/unit/nodes/`` (alongside the other ``async_sql`` unit tests,
which also exercise real in-memory SQLite) so it runs in the blocking Tier-1 CI
lane; ``tests/regression/`` is not currently executed by the core CI workflow.

Inventory: ``STUB-MARKER-INVENTORY.md`` gaps #1/#2 (issue #1406 follow-up).
"""

from typing import cast

import pytest

from kailash.nodes.base import NodeConfigurationError
from kailash.nodes.data.async_sql import (
    AsyncSQLDatabaseNode,
    DatabaseConfig,
    DatabaseType,
    FetchMode,
    SQLiteAdapter,
)


@pytest.mark.regression
def test_fetchmode_has_no_iterator_member():
    """FetchMode is exactly {one, all, many} — the dead ITERATOR member is gone."""
    assert [m.value for m in FetchMode] == ["one", "all", "many"]
    assert not hasattr(FetchMode, "ITERATOR")


@pytest.mark.regression
def test_iterator_fetch_mode_rejected_at_node_validation():
    """Constructing a node with fetch_mode='iterator' fails loudly, not silently."""
    with pytest.raises(NodeConfigurationError, match="Invalid fetch_mode: iterator"):
        AsyncSQLDatabaseNode(
            name="iterator_removed",
            database_type="postgresql",
            host="localhost",
            database="d",
            user="u",
            password="p",
            fetch_mode="iterator",
        )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_adapter_raises_on_unknown_fetch_mode_no_silent_fallback():
    """An unrecognized fetch mode raises ValueError instead of returning None/[].

    Pre-fix, an unhandled mode fell through the SQLite dispatch to ``result = []``
    (and ``None`` on MySQL), masking the unimplemented path as an empty result.
    The terminal ``else`` now raises, so a future unhandled mode can never silently
    return a wrong-but-plausible value. Exercised against real in-memory SQLite.
    """
    adapter = SQLiteAdapter(
        DatabaseConfig(type=DatabaseType.SQLITE, database=":memory:")
    )
    await adapter.connect()
    try:
        await adapter.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
        await adapter.execute("INSERT INTO t (name) VALUES ('alice')")

        # ALL is a normal materializing read (sanity that the table is populated).
        rows = await adapter.execute("SELECT * FROM t", fetch_mode=FetchMode.ALL)
        assert rows == [{"id": 1, "name": "alice"}]

        # A mode the dispatch does not handle MUST raise, not silently return [].
        # cast() passes a deliberately-invalid value past the type checker to
        # exercise the runtime defensive guard (the whole point of the test).
        with pytest.raises(ValueError, match="Unsupported fetch_mode"):
            await adapter.execute(
                "SELECT * FROM t", fetch_mode=cast(FetchMode, "iterator")
            )
    finally:
        await adapter.disconnect()
