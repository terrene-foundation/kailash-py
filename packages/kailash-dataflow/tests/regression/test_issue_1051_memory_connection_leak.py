"""Regression: aiosqlite :memory: Connection leaked on DataFlow close (#1051).

Root cause was multi-sited (all in core SDK
`kailash.nodes.data.async_sql` + `dataflow.core.engine`):

- A: `SQLiteAdapter._get_connection()` created a fresh `aiosqlite.connect()`
  per `:memory:` query and never closed it (`disconnect()` only closed
  `self._pool`, which is None for `:memory:`).
- B: `ProductionSQLiteAdapter.disconnect()` short-circuited on the
  `_enterprise_pool` branch and never reached `super().disconnect()`, so
  the inherited `:memory:` connection was never closed.
- C: a node could create several adapters; only the last was torn down.
- D: the per-execute DDL-wrapper node was discarded without teardown.
- E (keystone): `engine.py` close()/close_async() guarded the cached-node
  teardown on `hasattr(node, "close")` — but `AsyncSQLDatabaseNode`'s
  teardown method is `cleanup()`, NOT `close()` (close lives on
  `EnterpriseConnectionPool`). The guard was always False, so the
  teardown — and C's `_owned_adapters` disconnect — never ran. Fixed by
  resolving `cleanup()` first.

Every per-query / cached `:memory:` connection survived to GC where
`aiosqlite.Connection.__del__` emitted
`ResourceWarning: ... was deleted before being closed`.

These tests pin the acceptance criterion the #1045 close() regression
test deliberately omitted as out-of-scope.

Tier-2 — NO MOCKING. Real DataFlow / ProtectedDataFlow, real `:memory:`,
real `runtime.execute()`, real GC. Structural assertion (live
aiosqlite.Connection count via gc) — not lexical scanning of the warning
text (probe-driven-verification.md Rule 3).
"""

import gc
import warnings

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


def _live_aiosqlite_connections():
    """Structural probe: count live aiosqlite Connection objects."""
    return [
        o
        for o in gc.get_objects()
        if type(o).__module__ == "aiosqlite.core" and type(o).__name__ == "Connection"
    ]


@pytest.mark.regression
def test_issue_1051_dataflow_memory_no_aiosqlite_resourcewarning():
    """DataFlow(:memory:) + workflow + close() leaks zero aiosqlite conns."""
    from dataflow import DataFlow

    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)

        db = DataFlow("sqlite:///:memory:")

        @db.model
        class Widget1051:
            name: str

        wf = WorkflowBuilder()
        wf.add_node("Widget1051CreateNode", "c", {"name": "alpha"})
        # The leak fires regardless of whether the query itself succeeds;
        # tolerate query-level failure so the test pins ONLY the leak.
        # Context-managed runtime — avoids the LocalRuntime deprecation
        # warning and is the documented resource-clean pattern.
        try:
            with LocalRuntime() as runtime:
                runtime.execute(wf.build())
        except Exception:
            pass

        db.close()
        del db, Widget1051
        gc.collect()  # ResourceWarning->error escalates here if leak present

    leaked = _live_aiosqlite_connections()
    assert not leaked, (
        f"{len(leaked)} aiosqlite Connection(s) leaked past DataFlow.close() "
        f"(#1051). _get_connection() must reuse one tracked :memory: "
        f"connection and disconnect() must await-close it."
    )


@pytest.mark.regression
def test_issue_1051_protecteddataflow_memory_no_aiosqlite_resourcewarning():
    """ProtectedDataFlow(:memory:) + workflow + close() — the #1045-omitted AC.

    ProtectedDataFlow lives at dataflow.core.protected_engine (the issue
    body's `from dataflow import ProtectedDataFlow` was wrong).
    """
    from dataflow.core.protected_engine import ProtectedDataFlow

    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)

        db = ProtectedDataFlow("sqlite:///:memory:")

        @db.model
        class Gadget1051:
            name: str

        wf = WorkflowBuilder()
        wf.add_node("Gadget1051CreateNode", "c", {"name": "beta"})
        try:
            with LocalRuntime() as runtime:
                runtime.execute(wf.build())
        except Exception:
            pass

        db.close()
        del db, Gadget1051
        gc.collect()

    leaked = _live_aiosqlite_connections()
    assert not leaked, (
        f"{len(leaked)} aiosqlite Connection(s) leaked past "
        f"ProtectedDataFlow.close() (#1051)."
    )


@pytest.mark.regression
def test_issue_1051_node_teardown_method_name_invariant():
    """Structural invariant pinning the Change-E keystone.

    The #1051 keystone bug: engine.py guarded cached-node teardown on
    `hasattr(node, "close")`, but `AsyncSQLDatabaseNode`'s async teardown
    method is `cleanup()` — `close()` is a *different class*
    (`EnterpriseConnectionPool`). The guard was always False, so teardown
    never ran. The fix resolves `getattr(cleanup) or getattr(close)`.

    This test fails loudly if a future refactor renames `cleanup` (which
    would re-break the teardown silently) — refactor-invariants discipline
    + cross-sdk-inspection.md §3a structural-invariant pattern.
    """
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    # The node's teardown method is `cleanup` (async). If this name
    # changes, engine.py's `getattr(node, "cleanup", ...)` resolution
    # silently breaks and the #1051 leak returns.
    assert hasattr(AsyncSQLDatabaseNode, "cleanup"), (
        "AsyncSQLDatabaseNode.cleanup() is gone — engine.py's #1051 "
        "cached-node teardown resolves `cleanup` first; a rename re-opens "
        "the aiosqlite :memory: leak silently. Update both together."
    )
    assert callable(getattr(AsyncSQLDatabaseNode, "cleanup")), (
        "AsyncSQLDatabaseNode.cleanup is not callable — #1051 teardown "
        "contract broken."
    )

    # Mirror the EXACT resolution engine.py close()/close_async() use, so
    # this test pins the contract the production teardown depends on.
    # Construction alone opens no connection (no execute() call), so no
    # teardown is needed here — this probe pins only the method-name
    # resolution engine.py's teardown depends on.
    node = AsyncSQLDatabaseNode(
        node_id="invariant_probe",
        connection_string="sqlite:///:memory:",
        database_type="sqlite",
        query="SELECT 1",
        fetch_mode="all",
        validate_queries=False,
    )
    teardown = getattr(node, "cleanup", None) or getattr(node, "close", None)
    assert callable(teardown), (
        "engine.py's `getattr(node,'cleanup') or getattr(node,'close')` "
        "resolves to a non-callable for AsyncSQLDatabaseNode — the "
        "#1051 cached-node teardown is a silent no-op again."
    )
