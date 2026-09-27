"""Generated transaction reads bypass the shared committed-state query cache."""

import logging
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from dataflow import DataFlow
from dataflow.core import nodes as subject
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

pytestmark = [pytest.mark.regression, pytest.mark.asyncio]


@pytest.fixture
async def query_database(tmp_path, caplog):
    root = Path(__file__).resolve().parents[4]
    assert Path(subject.__file__).resolve() == (
        root / "packages/kailash-dataflow/src/dataflow/core/nodes.py"
    )
    path = tmp_path / "transaction-cache.db"
    db = DataFlow(f"sqlite:///{path}", cache_enabled=True)
    try:

        @db.model
        class TransactionCacheItem:
            id: str
            name: str

        assert await db.initialize()
        with LocalRuntime() as runtime:

            async def run(operation, parameters=None, scope=None):
                workflow = WorkflowBuilder()
                workflow.add_node(
                    f"TransactionCacheItem{operation}Node", "query", parameters or {}
                )
                context = {"dataflow_instance": db}
                if scope is not None:
                    context["active_transaction"] = scope
                results, _ = await runtime.execute_async(
                    workflow.build(), parameters={"workflow_context": context}
                )
                return results["query"]

            await run("Create", {"id": "a", "name": "committed"})
            adapter = await db._get_or_create_async_sql_node("sqlite")._get_adapter()
            assert db._cache_integration is not None
            assert [
                r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING
            ] == [
                "DataFlow: Test mode enabled (auto-detected pytest environment)",
                "DataFlow: Aggressive pool cleanup enabled for test mode",
            ]
            caplog.clear()
            yield path, db, adapter, run
            assert not [
                r for r in caplog.get_records("call") if r.levelno >= logging.WARNING
            ]
    finally:
        await db.close_async()


class RollbackProbe(Exception):
    pass


def _assert_rows(result, count_only, expected):
    assert result["count"] == len(expected)
    if not count_only:
        assert sorted(row["id"] for row in result["records"]) == expected


@pytest.mark.parametrize("count_only", [False, True])
async def test_transaction_ignores_warmed_committed_cache(query_database, count_only):
    path, db, adapter, run = query_database
    parameters = {"count_only": count_only}
    first = await run("List", parameters)
    assert first["_cache"]["hit"] is False
    warm = await run("List", parameters)
    assert warm["_cache"]["hit"] is True
    _assert_rows(warm, count_only, ["a"])

    with pytest.raises(RollbackProbe, match="discard b"):
        async with adapter.transaction() as scope:
            await run("Create", {"id": "b", "name": "uncommitted"}, scope)
            # Restore the actual committed query snapshot under its exact key
            # after write invalidation, as a concurrent committed reader could.
            # This is the real cache backend, not a replacement for its API.
            cache = db._cache_integration.cache_manager
            cache_key = warm["_cache"]["key"]
            assert await cache.set(cache_key, warm)
            committed = await run("List", parameters)
            assert committed["_cache"]["key"] == cache_key
            assert committed["_cache"]["hit"] is True
            _assert_rows(committed, count_only, ["a"])
            local = await run("List", parameters, scope)
            _assert_rows(local, count_only, ["a", "b"])
            assert "_cache" not in local
            # The transaction-local read must not replace the committed entry.
            shared = await run("List", parameters)
            assert shared["_cache"]["hit"] is True
            _assert_rows(shared, count_only, ["a"])
            raise RollbackProbe("discard b")

    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute(
            "SELECT id FROM transaction_cache_items"
        ).fetchall() == [("a",)]
    _assert_rows(await run("List", parameters), count_only, ["a"])


@pytest.mark.parametrize("count_only", [False, True])
async def test_transaction_cache_miss_never_publishes_rolled_back_rows(
    query_database, count_only
):
    path, db, adapter, run = query_database
    parameters = {"count_only": count_only}
    await db._cache_integration.cache_manager.clear()
    with pytest.raises(RollbackProbe, match="discard b"):
        async with adapter.transaction() as scope:
            await run("Create", {"id": "b", "name": "uncommitted"}, scope)
            local = await run("List", parameters, scope)
            _assert_rows(local, count_only, ["a", "b"])
            assert "_cache" not in local
            # READ and standalone COUNT share the connection contract but do
            # not use ListNode's query cache at all.
            assert (await run("Read", {"id": "b"}, scope))["name"] == "uncommitted"
            assert (await run("Count", {}, scope))["count"] == 2
            raise RollbackProbe("discard b")

    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute(
            "SELECT id FROM transaction_cache_items"
        ).fetchall() == [("a",)]
    after = await run("List", parameters)
    _assert_rows(after, count_only, ["a"])
    assert after["_cache"]["hit"] is False
    assert after["_cache"]["source"] == "database"
    assert (await run("List", parameters))["_cache"]["hit"] is True


async def test_filtered_transaction_count_preserves_alias_and_zero(query_database):
    _, _, adapter, run = query_database
    parameters = {"count_only": True, "filter": {"name": "uncommitted"}}
    assert (await run("List", parameters))["count"] == 0
    with pytest.raises(RollbackProbe, match="discard b"):
        async with adapter.transaction() as scope:
            await run("Create", {"id": "b", "name": "uncommitted"}, scope)
            assert (await run("List", parameters, scope))["count"] == 1
            raise RollbackProbe("discard b")
    assert (await run("List", parameters))["count"] == 0
