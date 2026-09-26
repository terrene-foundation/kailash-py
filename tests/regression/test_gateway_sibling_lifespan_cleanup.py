"""Gateway lifespan owners release their resources on every exit path."""

import asyncio
from pathlib import Path

import httpx
import pytest

from kailash.api import gateway as workflow_gateway
from kailash.gateway import api as enhanced_api
from kailash.gateway.enhanced_gateway import EnhancedDurableAPIGateway
from kailash.middleware.gateway.durable_gateway import DurableAPIGateway
from kailash.middleware.gateway.durable_request import DurableRequest, RequestState
from kailash.middleware.gateway.event_store import EventStore
from kailash.trust.auth.jwt import JWTConfig, JWTValidator
from kailash.workflow.builder import WorkflowBuilder

pytestmark = [pytest.mark.regression, pytest.mark.asyncio]


@pytest.fixture(autouse=True)
def source_and_environment(monkeypatch, tmp_path):
    root = Path(__file__).resolve().parents[2]
    assert (
        Path(workflow_gateway.__file__).resolve() == root / "src/kailash/api/gateway.py"
    )
    assert Path(enhanced_api.__file__).resolve() == root / "src/kailash/gateway/api.py"
    monkeypatch.setenv(
        "KAILASH_ENCRYPTION_KEY", "lifespan-test-encryption-key-at-least-32-bytes"
    )
    monkeypatch.setattr(
        enhanced_api, "_gateway_instance", enhanced_api._gateway_instance
    )
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize("stage", ["startup", "body", "shutdown", "proxy_close"])
async def test_workflow_gateway_releases_each_owner_after_lifespan_failure(
    stage, monkeypatch
):
    gateway = workflow_gateway.WorkflowAPIGateway(
        auth_config={"secret": "gateway-lifespan-auth-secret-at-least-32-bytes"}
    )
    builder = WorkflowBuilder()
    builder.add_node(
        "DataTransformer", "n", {"data": {"ran": True}, "transformations": []}
    )
    gateway.register_workflow("probe", builder.build())
    api = gateway._workflow_apis["probe"]
    runtime = api.runtime
    client = httpx.AsyncClient()
    gateway._proxy_client = client
    close_client = client.aclose
    failure = RuntimeError(f"controlled {stage} failure")
    reached = []

    async def fail():
        reached.append(stage)
        raise failure

    if stage == "startup":
        gateway.app.router.on_startup.append(fail)
    elif stage == "shutdown":
        gateway.app.router.on_shutdown.append(fail)
    elif stage == "proxy_close":
        monkeypatch.setattr(client, "aclose", fail)
    try:
        assert (
            gateway.executor.submit(lambda: "worker alive").result() == "worker alive"
        )
        with pytest.raises(RuntimeError) as error:
            async with gateway.app.router.lifespan_context(gateway.app):
                if stage == "body":
                    await fail()
        assert error.value is failure
        assert reached == [stage]
        assert api.runtime is None
        assert runtime.ref_count == 0
        if stage != "proxy_close":
            assert client.is_closed
        with pytest.raises(RuntimeError, match="cannot schedule new futures"):
            gateway.executor.submit(lambda: None)
    finally:
        await close_client()
        gateway.close()
        gateway.executor.shutdown(wait=True)


async def test_enhanced_app_lifespan_closes_its_own_gateway_even_after_second_app():
    config = {"secret": "enhanced-lifespan-auth-secret-at-least-32-bytes"}
    first_app = enhanced_api.create_gateway_app(auth_config=config)
    first = enhanced_api._gateway_instance
    second_app = enhanced_api.create_gateway_app(auth_config=config)
    second = enhanced_api._gateway_instance
    try:
        async with first_app.router.lifespan_context(first_app):
            assert first._runtime.ref_count == 1
        assert first._runtime.ref_count == 0
        assert first.event_store._flush_task.done()
        assert second._runtime.ref_count == 1
        with pytest.raises(asyncio.CancelledError):
            async with second_app.router.lifespan_context(second_app):
                raise asyncio.CancelledError("consumer cancellation")
        assert second._runtime.ref_count == 0
        assert second.event_store._flush_task.done()
    finally:
        await first.shutdown()
        await second.shutdown()


async def test_enhanced_app_authentication_and_requests_share_the_same_owner():
    apps = []
    owners = []
    tokens = []
    try:
        for label in ("first", "second"):
            secret = f"{label}-application-independent-secret-at-least-32-bytes"
            app = enhanced_api.create_gateway_app(auth_config={"secret": secret})
            owner = enhanced_api._gateway_instance
            apps.append(app)
            owners.append(owner)
            tokens.append(
                JWTValidator(JWTConfig(secret=secret)).create_access_token(
                    user_id=label
                )
            )
            builder = WorkflowBuilder()
            builder.add_node(
                "DataTransformer",
                "n",
                {"data": {"owner": label}, "transformations": []},
            )
            owner.register_workflow(label, builder.build())

        for index, app in enumerate(apps):
            label = ("first", "second")[index]
            other = ("second", "first")[index]
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://owner.test"
            ) as client:
                assert (await client.get("/api/v1/workflows")).status_code == 401
                wrong = await client.get(
                    "/api/v1/workflows",
                    headers={"Authorization": f"Bearer {tokens[1-index]}"},
                )
                assert wrong.status_code == 401
                headers = {"Authorization": f"Bearer {tokens[index]}"}
                own = await client.get("/api/v1/workflows", headers=headers)
                assert own.status_code == 200
                assert set(own.json()) == {label}
                assert (
                    await client.get(f"/api/v1/workflows/{other}", headers=headers)
                ).status_code == 404
    finally:
        for owner in owners:
            await owner.shutdown()


@pytest.mark.parametrize(
    "failed_owner", ["checkpoint_manager", "deduplicator", "event_store"]
)
async def test_durable_close_releases_later_components_and_parent_after_failure(
    failed_owner, monkeypatch
):
    gateway = EnhancedDurableAPIGateway(
        auth_config={"secret": "durable-owner-test-secret-at-least-32-bytes"},
        event_store=EventStore(storage_backend="memory"),
    )
    builder = WorkflowBuilder()
    builder.add_node("DataTransformer", "n", {"data": {}, "transformations": []})
    gateway.register_workflow("probe", builder.build())
    mounted = gateway._workflow_apis["probe"]
    reached = []
    originals = {}
    failure = RuntimeError("component close failure")
    for name in ("checkpoint_manager", "deduplicator", "event_store"):
        owner = getattr(gateway, name)
        originals[name] = owner.close

        async def close(name=name):
            reached.append(name)
            if name == failed_owner:
                raise failure
            await originals[name]()

        monkeypatch.setattr(owner, "close", close)
    try:
        with pytest.raises(RuntimeError) as error:
            await gateway.shutdown()
        assert error.value is failure
        assert reached == ["checkpoint_manager", "deduplicator", "event_store"]
        assert mounted.runtime is None
        assert gateway._runtime.ref_count == 0
        with pytest.raises(RuntimeError, match="cannot schedule new futures"):
            gateway.executor.submit(lambda: None)
    finally:
        for name, original in originals.items():
            monkeypatch.setattr(getattr(gateway, name), "close", original)
        await gateway.shutdown()


async def test_cancellation_during_active_request_wait_drains_background_owner():
    gateway = DurableAPIGateway(
        auth_config={"secret": "active-wait-owner-secret-at-least-32-bytes"},
        event_store=EventStore(storage_backend="memory"),
    )
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def background():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    worker = asyncio.create_task(background())
    gateway._background_tasks.append(worker)
    request = DurableRequest(request_id="active-wait-probe")
    gateway.active_requests[request.id] = request
    shutdown = None
    try:
        await asyncio.wait_for(started.wait(), 2)
        shutdown = asyncio.create_task(gateway.close(shutdown_timeout=10))
        await asyncio.sleep(0)
        assert shutdown.get_coro().cr_await.cr_code.co_name == "sleep"
        shutdown.cancel("active-request wait cancelled")
        with pytest.raises(
            asyncio.CancelledError, match="active-request wait cancelled"
        ):
            await shutdown
        assert worker.done()
        assert stopped.is_set()
        assert gateway._background_tasks == []
        assert gateway.event_store._flush_task.done()
        with pytest.raises(RuntimeError, match="cannot schedule new futures"):
            gateway.executor.submit(lambda: None)
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        if shutdown is not None and not shutdown.done():
            shutdown.cancel()
            await asyncio.gather(shutdown, return_exceptions=True)
        gateway.active_requests.clear()
        await gateway.close()


@pytest.mark.parametrize(
    "gateway_class", [DurableAPIGateway, EnhancedDurableAPIGateway]
)
@pytest.mark.parametrize("cancel_body", [False, True])
async def test_native_app_lifespan_releases_every_inherited_owner(
    gateway_class, cancel_body
):
    gateway = gateway_class(
        auth_config={"secret": "native-app-owner-secret-at-least-32-bytes"},
        event_store=EventStore(storage_backend="memory"),
    )
    builder = WorkflowBuilder()
    builder.add_node("DataTransformer", "n", {"data": {}, "transformations": []})
    gateway.register_workflow("probe", builder.build())
    mounted = gateway._workflow_apis["probe"]
    runtime = mounted.runtime
    try:

        async def run_lifespan():
            async with gateway.app.router.lifespan_context(gateway.app):
                if cancel_body:
                    raise asyncio.CancelledError("native consumer cancellation")

        if cancel_body:
            with pytest.raises(
                asyncio.CancelledError, match="native consumer cancellation"
            ):
                await run_lifespan()
        else:
            await run_lifespan()
        assert mounted.runtime is None
        assert runtime.ref_count == 0
        assert gateway.event_store._flush_task.done()
        if isinstance(gateway, EnhancedDurableAPIGateway):
            assert gateway._runtime.ref_count == 0
        with pytest.raises(RuntimeError, match="cannot schedule new futures"):
            gateway.executor.submit(lambda: None)
    finally:
        await gateway.close()


async def test_enhanced_public_close_forwards_timeout_and_releases_runtime(caplog):
    gateway = EnhancedDurableAPIGateway(
        auth_config={"secret": "public-close-owner-secret-at-least-32-bytes"},
        event_store=EventStore(storage_backend="memory"),
    )
    request = DurableRequest(request_id="timeout-probe")
    gateway.active_requests[request.id] = request
    try:
        await asyncio.wait_for(gateway.close(shutdown_timeout=0), 2)
        assert request.state is RequestState.CANCELLED
        assert gateway._runtime.ref_count == 0
        assert gateway.event_store._flush_task.done()
        assert [r.getMessage() for r in caplog.records if r.levelno >= 30] == [
            "Shutdown timeout reached with 1 requests still active: ['timeout-probe']"
        ]
    finally:
        gateway.active_requests.clear()
        await gateway.shutdown()


async def test_durable_background_drain_cancellation_preserves_cleanup():
    gateway = EnhancedDurableAPIGateway(
        auth_config={"secret": "durable-owner-test-secret-at-least-32-bytes"},
        event_store=EventStore(storage_backend="memory"),
    )
    started = asyncio.Event()
    unwinding = asyncio.Event()

    async def background():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            unwinding.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(background())
    gateway._background_tasks.append(task)
    shutdown = None
    try:
        await asyncio.wait_for(started.wait(), 2)
        shutdown = asyncio.create_task(gateway.shutdown())
        await asyncio.wait_for(unwinding.wait(), 2)
        shutdown.cancel("caller cancellation")
        with pytest.raises(asyncio.CancelledError, match="caller cancellation"):
            await shutdown
        assert task.done()
        assert gateway._background_tasks == []
        assert gateway.event_store._flush_task.done()
        with pytest.raises(RuntimeError, match="cannot schedule new futures"):
            gateway.executor.submit(lambda: None)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if shutdown is not None and not shutdown.done():
            shutdown.cancel()
            await asyncio.gather(shutdown, return_exceptions=True)
        await gateway.shutdown()
