# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: ``nodes/bulk_upsert.py`` must BIND its dialect (#1971).

``DataFlowBulkUpsertNode`` holds its engine explicitly — ``database_type`` is
a constructor parameter, and BOTH identifier-validating methods materialise it
into a local ``dialect`` before validating anything. Both passed the unknown
sentinel anyway, so a single upsert emitted five WARN lines ::

    identifier.unknown_dialect_budget: .../nodes/bulk_upsert.py:654 ...
    identifier.unknown_dialect_budget: .../nodes/bulk_upsert.py:658 ...
    identifier.unknown_dialect_budget: .../nodes/bulk_upsert.py:660 ...
    identifier.unknown_dialect_budget: .../nodes/bulk_upsert.py:662 ...
    identifier.unknown_dialect_budget: .../nodes/bulk_upsert.py:916 ...

The noise is the least of it. The sentinel is SQLite's 128, the LOOSEST
budget, so on PostgreSQL a 64..128-char identifier passed validation here and
was then truncated server-side at 63 — silently aliasing two distinct models
onto one physical table. This node is the workflow-side twin of
``features/bulk.py``, which was bound for the same reason in #1971c.

Both poles are asserted deliberately, plus the payload. A silence-only test
passes just as well if the warning were deleted or the code path broken, so
these tests additionally pin (a) that a GENUINELY unknown dialect still warns
at the real in-file call site, and (b) that each silent path still returns
real SQL / a real count.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from dataflow.nodes.bulk_upsert import DataFlowBulkUpsertNode
from kailash.db.dialect import (
    _UNKNOWN_BUDGET_WARNED_SITES,
    MYSQL_MAX_IDENTIFIER_LENGTH,
    POSTGRES_MAX_IDENTIFIER_LENGTH,
    SQLITE_MAX_IDENTIFIER_LENGTH,
    IdentifierError,
)
from kailash.sdk_exceptions import NodeValidationError

_MARKER = "identifier.unknown_dialect_budget"
_DIALECT_LOGGER = "kailash.db.dialect"


@pytest.fixture(autouse=True)
def _clear_warn_memo():
    """The memo is process-global and once-per-SITE; clear it both sides.

    Without this, a sibling test that already tripped one of these lines would
    make every silence assertion below pass for the wrong reason — the memo,
    not the fix, would be doing the suppressing.
    """
    _UNKNOWN_BUDGET_WARNED_SITES.clear()
    yield
    _UNKNOWN_BUDGET_WARNED_SITES.clear()


def _node(**overrides) -> DataFlowBulkUpsertNode:
    kwargs = {
        "name": "bulk_upsert_under_test",
        "table_name": "users",
        "database_type": "postgresql",
        "conflict_columns": ["email"],
    }
    kwargs.update(overrides)
    return DataFlowBulkUpsertNode(**kwargs)


def _budget_warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if _MARKER in r.getMessage()]


def test_module_under_test_is_the_in_tree_copy():
    """Guard the import trap that makes every other assertion here worthless.

    ``dataflow`` is also installed into site-packages. A run that resolved the
    installed copy would exercise code this file never touched, and both poles
    below would report on the wrong module while looking perfectly green. Pin
    the import to the checkout this test file itself lives in.
    """
    import dataflow.nodes.bulk_upsert as module_under_test

    package_src = Path(__file__).resolve().parents[2] / "src"
    assert (
        Path(module_under_test.__file__).resolve().is_relative_to(package_src)
    ), f"testing {module_under_test.__file__}, not the copy under {package_src}"


# ---------------------------------------------------------------------------
# Pole 1 — a KNOWN dialect falls silent, and still produces real output.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "database_type,placeholder",
    [("postgresql", "$1"), ("mysql", "%s"), ("sqlite", "?")],
)
def test_build_upsert_query_binds_known_dialect(caplog, database_type, placeholder):
    """``_build_upsert_query`` resolves ``dialect`` before it validates.

    Four validate calls live in that method (table_name, columns, conflict_on,
    version_field); ``version_control`` is on so the fourth is reached too.
    """
    node = _node(
        database_type=database_type, version_control=True, version_field="version"
    )

    with caplog.at_level(logging.WARNING, logger=_DIALECT_LOGGER):
        sql, params = node._build_upsert_query(
            batch=[{"email": "a@b.c", "name": "A", "version": 1}],
            columns=["email", "name", "version"],
            column_names="email, name, version",
            return_records=False,
            merge_strategy="update",
            conflict_on=["email"],
        )

    assert _budget_warnings(caplog) == []
    # The path is not merely silent — it still emits the real statement, so a
    # broken/short-circuited code path cannot pass as a clean result.
    assert "INSERT INTO users (email, name, version)" in sql
    assert placeholder in sql
    assert params == ["a@b.c", "A", 1]


def test_count_existing_conflicts_binds_known_dialect(caplog):
    """The second site (``_count_existing_conflicts``) binds too."""
    node = _node(database_type="postgresql")

    async def _fake_execute_query(query, params=None, **kwargs):
        assert "SELECT COUNT(*) AS match_count FROM users" in query
        return {"result": {"data": [{"match_count": 2}]}}

    node._execute_query = _fake_execute_query

    with caplog.at_level(logging.WARNING, logger=_DIALECT_LOGGER):
        count = asyncio.run(
            node._count_existing_conflicts(
                batch=[{"email": "a@b.c"}, {"email": "d@e.f"}],
                conflict_on=["email"],
            )
        )

    assert _budget_warnings(caplog) == []
    assert count == 2  # real data, not a silently-short-circuited zero


# ---------------------------------------------------------------------------
# Pole 2 — CONTROL. A genuinely unknown dialect must STILL warn, at the real
# in-file call site. This is what distinguishes "bound correctly" from "the
# warning was deleted" or "the capture never worked".
# ---------------------------------------------------------------------------


def test_count_existing_conflicts_unknown_dialect_still_warns(caplog):
    """``_count_existing_conflicts`` does NOT allowlist-check its dialect.

    It falls through to ``?`` placeholders for anything non-PG/MySQL, so an
    unrecognised ``database_type`` genuinely cannot name its engine here — and
    the resolver returns the sentinel, which keeps the warning firing. That is
    the signal the warning exists to carry, and it must survive this fix.
    """
    node = _node(database_type="oracle")

    async def _fake_execute_query(query, params=None, **kwargs):
        return {"result": {"data": [{"match_count": 0}]}}

    node._execute_query = _fake_execute_query

    with caplog.at_level(logging.WARNING, logger=_DIALECT_LOGGER):
        asyncio.run(
            node._count_existing_conflicts(
                batch=[{"email": "a@b.c"}], conflict_on=["email"]
            )
        )

    warnings = _budget_warnings(caplog)
    assert len(warnings) == 1, warnings
    assert "nodes/bulk_upsert.py" in warnings[0]


def test_build_upsert_query_rejects_unknown_dialect_loudly():
    """The first site cannot reach the sentinel: it raises on an unknown type.

    ``_SUPPORTED_DIALECTS`` is checked before any validation, so binding there
    is total — there is no unknown-dialect path left for it to warn from.
    """
    node = _node(database_type="oracle")

    with pytest.raises(NodeValidationError, match="Unsupported database_type"):
        node._build_upsert_query(
            batch=[{"email": "a@b.c"}],
            columns=["email"],
            column_names="email",
            return_records=False,
            merge_strategy="update",
            conflict_on=["email"],
        )


# ---------------------------------------------------------------------------
# The defect itself — the budget actually applied is now the ENGINE's, not
# SQLite's 128. This is the behaviour change the silence is a proxy for.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "database_type,budget",
    [
        ("postgresql", POSTGRES_MAX_IDENTIFIER_LENGTH),
        ("mysql", MYSQL_MAX_IDENTIFIER_LENGTH),
        ("sqlite", SQLITE_MAX_IDENTIFIER_LENGTH),
    ],
)
def test_identifier_over_engine_budget_is_rejected_client_side(database_type, budget):
    """A name one char past the ENGINE's budget is now refused here.

    Before the fix every engine was measured against 128, so a 64-char column
    sailed through on PostgreSQL and was truncated at 63 server-side. The
    ``budget``-length name must still pass, or the test would also pass if the
    validator simply rejected everything.
    """
    node = _node(database_type=database_type)
    at_limit = "c" + "x" * (budget - 1)
    over_limit = "c" + "x" * budget

    sql, _ = node._build_upsert_query(
        batch=[{"email": "a@b.c", at_limit: 1}],
        columns=["email", at_limit],
        column_names=f"email, {at_limit}",
        return_records=False,
        merge_strategy="update",
        conflict_on=["email"],
    )
    assert at_limit in sql

    with pytest.raises(IdentifierError, match=f"exceeds {budget}-char limit"):
        node._build_upsert_query(
            batch=[{"email": "a@b.c", over_limit: 1}],
            columns=["email", over_limit],
            column_names=f"email, {over_limit}",
            return_records=False,
            merge_strategy="update",
            conflict_on=["email"],
        )


def test_postgres_rejects_what_sqlite_accepts():
    """The engines are now measured DIFFERENTLY — the whole point of #1971.

    A 100-char identifier is legal on SQLite and illegal on PostgreSQL. Before
    the fix both were measured against SQLite's 128 and both accepted it.
    """
    name = "c" + "x" * 99
    assert len(name) == 100

    sql, _ = _node(database_type="sqlite")._build_upsert_query(
        batch=[{"email": "a@b.c", name: 1}],
        columns=["email", name],
        column_names=f"email, {name}",
        return_records=False,
        merge_strategy="update",
        conflict_on=["email"],
    )
    assert name in sql

    with pytest.raises(IdentifierError, match="exceeds 63-char limit"):
        _node(database_type="postgresql")._build_upsert_query(
            batch=[{"email": "a@b.c", name: 1}],
            columns=["email", name],
            column_names=f"email, {name}",
            return_records=False,
            merge_strategy="update",
            conflict_on=["email"],
        )
