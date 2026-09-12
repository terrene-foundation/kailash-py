"""Regression: the single-record upsert node must BIND its dialect (#1971).

``dataflow/core/nodes.py`` — ``DataFlowNode.async_run``'s ``upsert`` branch —
validates ``table_name`` plus every interpolated column name before handing
them to ``SQLDialectFactory``. Those two ``_validate_identifier`` calls passed
``DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH``, the unknown-dialect sentinel.

They were never dialect-less. ``database_type`` is resolved roughly eighty
lines above them on BOTH branches (an explicit ``database_url`` kwarg goes
through ``ConnectionParser.detect_database_type``, otherwise
``DataFlow._detect_database_type()``), and is consumed immediately BELOW them
by ``SQLDialectFactory.get_dialect(database_type)`` to pick the engine the SQL
is built for. Passing the sentinel anyway is fail-OPEN: it is SQLite's 128, the
LOOSEST budget, so on PostgreSQL a 64..128-char identifier passes client-side
validation and is then TRUNCATED SERVER-SIDE at 63 — silently aliasing two
models onto one physical table. This is the #1971 defect itself, reachable
through the generated ``{Model}UpsertNode`` every DataFlow user gets.

This is the single-record sibling of ``test_issue_1971c_dataflow_sites_bind_dialect``
(which covers ``features/bulk.py`` and ``migrations/sync_ddl_executor.py``).

Both poles are asserted deliberately. A silence-only test passes just as well
if the warning were deleted or the code path broken, so:

* Pole 1 asserts silence AND that the upsert returned the real row.
* Pole 2 is the CONTROL: a db type the dialect registry genuinely does not
  know still reaches the sentinel and still warns, naming ``core/nodes.py``.
* Pole 3 pins that the bound budget is the REAL one (PostgreSQL's 63), not
  merely a different symbol: a 70-char table name is now REJECTED client-side
  on PostgreSQL and still ACCEPTED on SQLite.

NO MOCKING — real file-backed SQLite (Tier 2 discipline). Poles 2 and 3 need
no live server: the identifier validation runs before any connection is opened.
"""

from __future__ import annotations

import logging
import pathlib

import pytest

import dataflow.core.nodes as _df_nodes
import kailash.db.dialect as _k_dialect
from dataflow import DataFlow
from kailash.db.dialect import _UNKNOWN_BUDGET_WARNED_SITES, IdentifierError
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

_MARKER = "identifier.unknown_dialect_budget"

# <root>/packages/kailash-dataflow/tests/regression/<this file>
_ROOT = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def _clear_warn_memo():
    """The warn memo is process-global and fires once per ``(file, lineno)``.

    Without clearing it, a sibling test that already tripped this site would
    make Pole 1's silence assertion pass for entirely the wrong reason.
    """
    _UNKNOWN_BUDGET_WARNED_SITES.clear()
    yield
    _UNKNOWN_BUDGET_WARNED_SITES.clear()


@pytest.mark.regression
def test_modules_under_test_are_the_worktree_copies():
    """Guard the known worktree trap: pytest silently imports site-packages.

    The fix under test lives in the worktree. A run that imported an installed
    ``kailash`` / ``dataflow`` would exercise entirely different code, so every
    verdict below would be about the wrong files. Assert provenance IN-PROCESS
    rather than trusting the invocation.
    """
    assert pathlib.Path(_k_dialect.__file__).resolve() == (
        _ROOT / "src" / "kailash" / "db" / "dialect.py"
    ), f"kailash.db.dialect came from {_k_dialect.__file__}, not the worktree"
    assert pathlib.Path(_df_nodes.__file__).resolve() == (
        _ROOT
        / "packages"
        / "kailash-dataflow"
        / "src"
        / "dataflow"
        / "core"
        / "nodes.py"
    ), f"dataflow.core.nodes came from {_df_nodes.__file__}, not the worktree"


# ---------------------------------------------------------------------------
# Pole 1 — the real single-record upsert path is silent, and still works
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_single_upsert_binds_its_detected_dialect(tmp_path, caplog):
    """``{Model}UpsertNode`` resolves ``database_type`` before it validates."""
    db = DataFlow(f"sqlite:///{tmp_path / 'upsert_bind.db'}")

    @db.model
    class Widget:
        id: str
        name: str

    workflow = WorkflowBuilder()
    workflow.add_node(
        "WidgetUpsertNode",
        "up",
        {
            "where": {"id": "w1"},
            "update": {"name": "beta"},
            "create": {"id": "w1", "name": "alpha"},
        },
    )

    with caplog.at_level(logging.WARNING, logger="kailash.db.dialect"):
        results, _ = await AsyncLocalRuntime().execute_workflow_async(
            workflow.build(), inputs={}
        )

    # The path must still WORK, not merely fall silent: a broken path would
    # emit no warning either.
    record = results["up"]["record"]
    assert record["id"] == "w1", f"upsert did not return the row: {record}"
    assert record["name"] == "alpha", f"upsert did not return the row: {record}"

    assert _MARKER not in caplog.text, (
        "the single-record upsert node validated identifiers against the "
        "unknown-dialect budget although database_type was already resolved "
        f"and is used immediately below to pick the dialect: {caplog.text!r}"
    )


# ---------------------------------------------------------------------------
# Pole 2 — CONTROL: a genuinely unknown dialect STILL warns, from this site
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_genuinely_unknown_dialect_still_warns_from_core_nodes(tmp_path, caplog):
    """``mongodb`` is a type ``ConnectionParser`` emits and the registry lacks.

    ``identifier_budget_for`` returns the sentinel for it by design, so the
    warning this rule exists to carry MUST still fire — otherwise the fix would
    have silenced the signal rather than bound the budget.
    """
    db = DataFlow(f"sqlite:///{tmp_path / 'upsert_unknown.db'}")

    @db.model
    class Gadget:
        id: str
        name: str

    workflow = WorkflowBuilder()
    workflow.add_node(
        "GadgetUpsertNode",
        "up",
        {
            "database_url": "mongodb://localhost:27017/nowhere",
            "where": {"id": "g1"},
            "update": {"name": "beta"},
            "create": {"id": "g1", "name": "alpha"},
        },
    )

    with caplog.at_level(logging.WARNING, logger="kailash.db.dialect"):
        with pytest.raises(Exception):
            # The dialect factory rejects "mongodb" AFTER the identifier
            # validation above it has already run — which is the point.
            await AsyncLocalRuntime().execute_workflow_async(
                workflow.build(), inputs={}
            )

    assert _MARKER in caplog.text, (
        "a db type the dialect registry does not know reached the identifier "
        "validator without warning — the unbound-budget signal was silenced "
        f"rather than bound: {caplog.text!r}"
    )
    assert "core/nodes.py" in caplog.text, (
        "the warning fired but was attributed to another call site, so it is "
        f"not evidence about the site under test: {caplog.text!r}"
    )


# ---------------------------------------------------------------------------
# Pole 3 — the bound budget is the REAL one: PostgreSQL 63, SQLite 128
# ---------------------------------------------------------------------------

_LONG_TABLE = "t" + "a" * 69  # 70 chars: > PostgreSQL's 63, < SQLite's 128


@pytest.mark.regression
@pytest.mark.asyncio
async def test_postgres_budget_rejects_identifier_sqlite_accepts(tmp_path, caplog):
    """A 70-char table name: legal on SQLite, over budget on PostgreSQL.

    Pre-fix BOTH engines got the sentinel's 128 and BOTH accepted it — and on
    PostgreSQL the server then truncated it at 63. Post-fix the two engines
    disagree, which is the only observation that proves a real per-dialect
    budget is in play rather than a differently-spelled 128.

    No live PostgreSQL is needed: identifier validation runs before the
    connection is opened, which is exactly where the defect lived.
    """
    db = DataFlow(f"sqlite:///{tmp_path / 'upsert_budget.db'}")

    @db.model
    class Doohickey:
        __tablename__ = _LONG_TABLE

        id: str
        name: str

    assert db._get_table_name("Doohickey") == _LONG_TABLE
    assert len(_LONG_TABLE) == 70

    def _wf(database_url: str | None):
        workflow = WorkflowBuilder()
        params = {
            "where": {"id": "d1"},
            "update": {"name": "beta"},
            "create": {"id": "d1", "name": "alpha"},
        }
        if database_url is not None:
            params["database_url"] = database_url
        workflow.add_node("DoohickeyUpsertNode", "up", params)
        return workflow.build()

    # PostgreSQL: 70 > 63 → rejected client-side instead of silently truncated.
    with pytest.raises(Exception) as excinfo:
        await AsyncLocalRuntime().execute_workflow_async(
            _wf("postgresql://u:p@127.0.0.1:5432/nowhere"), inputs={}
        )
    chain, err = [], excinfo.value
    while err is not None and err not in chain:
        chain.append(err)
        err = err.__cause__ or err.__context__
    assert any(isinstance(e, IdentifierError) for e in chain), (
        "a 70-char table name was NOT rejected against PostgreSQL's 63-char "
        f"budget; raised chain was {[type(e).__name__ for e in chain]}: {chain[0]!r}"
    )
    assert any(
        "63-char limit" in str(e) for e in chain
    ), f"rejected, but not against PostgreSQL's budget: {chain!r}"

    # SQLite: 70 < 128 → still accepted, and still returns the real row.
    with caplog.at_level(logging.WARNING, logger="kailash.db.dialect"):
        results, _ = await AsyncLocalRuntime().execute_workflow_async(
            _wf(None), inputs={}
        )
    assert results["up"]["record"]["id"] == "d1", (
        "binding the dialect budget broke the SQLite path, which legally "
        f"allows a 70-char identifier: {results['up']!r}"
    )
    assert _MARKER not in caplog.text, caplog.text
