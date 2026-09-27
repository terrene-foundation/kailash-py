"""Registry SQL uses the captured Core policy without moving native resources."""

import asyncio
import threading
from types import SimpleNamespace

import pytest

from dataflow import DataFlow
from kailash.nodes.data.sql import SQLDatabaseNode
from kailash.runtime import AsyncLocalRuntime, LocalRuntime
from kailash.runtime.trust.context import RuntimeTrustContext, get_runtime_trust_context
from kailash.runtime.trust.verifier import TrustVerifier, TrustVerifierConfig
from kailash.sdk_exceptions import WorkflowExecutionError
from kailash.workflow.builder import WorkflowBuilder

pytestmark = [pytest.mark.regression, pytest.mark.asyncio]


def sql_workflow(url, query="SELECT 17 AS value"):
    workflow = WorkflowBuilder()
    workflow.add_node(
        "SQLDatabaseNode",
        "probe",
        {"connection_string": url, "database_type": "sqlite", "query": query},
    )
    return workflow


@pytest.mark.parametrize("loopless_caller", [False, True])
async def test_live_native_owner_survives_repeated_registry_bridge(
    tmp_path, monkeypatch, loopless_caller
):
    url = f"sqlite:///{tmp_path / 'owner.db'}"
    db = DataFlow(url)
    runtime = db.runtime
    assert runtime._externally_managed
    caller_loop = asyncio.get_running_loop()
    caller_thread = threading.get_ident()
    calls = []
    engines = []
    original = LocalRuntime._execute_async

    async def observe(self, workflow, **kwargs):
        calls.append((self, asyncio.get_running_loop(), threading.get_ident()))
        result = await original(self, workflow, **kwargs)
        engines.extend(
            engine
            for (connection_string, _), engine in SQLDatabaseNode._shared_pools.items()
            if connection_string == url
        )
        return result

    monkeypatch.setattr(LocalRuntime, "_execute_async", observe)
    try:
        # Native entry binds loop ownership before any registry execution.
        await runtime.execute_workflow_async(sql_workflow(url).build(), inputs={})
        assert runtime._native_loop is caller_loop
        semaphore = runtime._semaphore
        for _ in range(3):
            if loopless_caller:
                # Explicit override pins the same live owner in a worker caller.
                db.runtime = runtime
                results, run_id = await asyncio.to_thread(
                    db._model_registry._execute_workflow_sync_safe, sql_workflow(url)
                )
            else:
                results, run_id = db._model_registry._execute_workflow_sync_safe(
                    sql_workflow(url)
                )
            assert results["probe"]["data"] == [{"value": 17}]
            assert run_id
            assert runtime._native_loop is caller_loop
            assert runtime._semaphore is semaphore
        assert len(calls) == 3
        assert all(owner is runtime for owner, _, _ in calls)
        assert all(loop is not caller_loop for _, loop, _ in calls)
        if not loopless_caller:
            assert all(loop.is_closed() for _, loop, _ in calls)
        assert all(thread != caller_thread for _, _, thread in calls)
        # Sync SQL returns each connection to its real SQLAlchemy pool.
        assert engines
        assert all(engine.pool.checkedout() == 0 for engine in engines)
        assert not caller_loop.is_closed()
    finally:
        db.runtime = None
        await db.close_async()
        if runtime._close_task is not None:
            await runtime._close_task
    assert runtime._cleaned_up
    assert runtime.ref_count == 0
    assert all(loop.is_closed() for _, loop, _ in calls)
    assert not db._loop_runtime_cache


@pytest.mark.parametrize("mode", ["enforcing", "permissive", "disabled"])
async def test_registry_bridge_preserves_configured_trust(tmp_path, mode):
    class DeniedBackend:
        """Policy test input; the real verifier and SQL execution remain active."""

        def __init__(self):
            self.calls = []

        async def verify(self, **kwargs):
            self.calls.append((kwargs, get_runtime_trust_context()))
            return SimpleNamespace(
                valid=False,
                reason="registry policy denied",
                effective_constraints=[],
                capability_used=None,
            )

    backend = DeniedBackend()
    verifier = TrustVerifier(backend, TrustVerifierConfig(mode="enforcing"))
    context = RuntimeTrustContext(delegation_chain=["registry-agent"])
    db = DataFlow(f"sqlite:///{tmp_path / 'policy.db'}")
    url = db.config.database.url
    async with AsyncLocalRuntime(
        trust_verifier=verifier,
        trust_verification_mode=mode,
        trust_context=context,
    ) as runtime:
        # Explicit setter override must survive the registry's lazy resolution.
        db.runtime = runtime
        try:
            workflow = sql_workflow(url, "CREATE TABLE bridge_policy (id INTEGER)")
            if mode == "enforcing":
                with pytest.raises(
                    WorkflowExecutionError, match="Trust verification denied"
                ):
                    db._model_registry._execute_workflow_sync_safe(workflow)
                assert not (tmp_path / "policy.db").exists()
            else:
                results, _ = db._model_registry._execute_workflow_sync_safe(workflow)
                assert "probe" in results
                assert (tmp_path / "policy.db").exists()
            assert bool(backend.calls) is (mode != "disabled")
            if backend.calls:
                assert all(ctx is context for _, ctx in backend.calls)
            assert runtime._native_loop is asyncio.get_running_loop()
        finally:
            db.runtime = None  # Runtime context owns this explicit override.
            await db.close_async()


@pytest.mark.parametrize("shutdown", ["aclose", "cleanup"])
@pytest.mark.parametrize("loopless_caller", [False, True])
async def test_closed_registry_owner_rejects_sql_before_io(
    tmp_path, shutdown, loopless_caller
):
    path = tmp_path / "closed.db"
    db = DataFlow(f"sqlite:///{path}")
    runtime = db.runtime
    db.runtime = runtime
    try:
        await getattr(runtime, shutdown)()
        assert runtime._cleaned_up
        assert runtime.ref_count == (0 if shutdown == "aclose" else 1)
        with pytest.raises(RuntimeError, match="closed runtime"):
            runtime.acquire()
        workflow = sql_workflow(
            str(db.config.database.url), "CREATE TABLE denied (id INTEGER)"
        )
        with pytest.raises(RuntimeError, match="closed runtime"):
            if loopless_caller:
                await asyncio.to_thread(
                    db._model_registry._execute_workflow_sync_safe, workflow
                )
            else:
                db._model_registry._execute_workflow_sync_safe(workflow)
        assert not path.exists()
    finally:
        db.runtime = None
        await db.close_async()
        await runtime.aclose()


async def test_registry_retains_native_owner_until_active_bridge_finishes(
    tmp_path, monkeypatch
):
    db = DataFlow(f"sqlite:///{tmp_path / 'active.db'}")
    runtime = db.runtime
    db.runtime = runtime
    entered = threading.Event()
    release = threading.Event()
    original = LocalRuntime._execute_async

    async def gated(self, *args, **kwargs):
        if self is runtime:
            entered.set()
            assert release.wait(10), "test must release the admitted worker"
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(LocalRuntime, "_execute_async", gated)
    async with runtime:
        task = asyncio.create_task(
            asyncio.to_thread(
                db._model_registry._execute_workflow_sync_safe,
                sql_workflow(str(db.config.database.url)),
            )
        )
        try:
            assert await asyncio.to_thread(entered.wait, 10)
            assert runtime.ref_count == 2
            runtime.close()  # Creator releases while registry still owns its lease.
            assert runtime.ref_count == 1
            assert not getattr(runtime, "_cleaned_up", False)
            release.set()
            results, _ = await task
            assert results["probe"]["data"] == [{"value": 17}]
            await runtime.aclose()
            assert runtime.ref_count == 0
            assert runtime._cleaned_up
            assert (
                runtime._persistent_loop is None or runtime._persistent_loop.is_closed()
            )
        finally:
            release.set()
            await task
            db.runtime = None
            await db.close_async()


async def test_registry_releases_temporary_owner_after_trust_denial(tmp_path):
    class DeniedBackend:
        async def verify(self, **kwargs):
            return SimpleNamespace(
                valid=False,
                reason="denied",
                effective_constraints=[],
                capability_used=None,
            )

    verifier = TrustVerifier(DeniedBackend(), TrustVerifierConfig(mode="enforcing"))
    db = DataFlow(f"sqlite:///{tmp_path / 'denied.db'}")
    async with AsyncLocalRuntime(
        trust_verifier=verifier,
        trust_verification_mode="enforcing",
        trust_context=RuntimeTrustContext(),
    ) as runtime:
        db.runtime = runtime
        try:
            with pytest.raises(
                WorkflowExecutionError, match="Trust verification denied"
            ):
                db._model_registry._execute_workflow_sync_safe(
                    sql_workflow(str(db.config.database.url))
                )
            assert runtime.ref_count == 1
            assert not getattr(runtime, "_cleaned_up", False)
        finally:
            db.runtime = None
            await db.close_async()
