# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Rejected gateway configuration must not acquire an uncloseable runtime."""

import asyncio
import inspect
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kailash.middleware.communication import api_gateway as subject
from kailash.utils.server_auth import ServerAuthNotConfiguredError

pytestmark = pytest.mark.regression


@pytest.fixture
def clean_auth_environment(monkeypatch):
    monkeypatch.setenv(
        "KAILASH_ENCRYPTION_KEY", "gateway-test-encryption-key-at-least-32-bytes"
    )
    for name in tuple(os.environ):
        if name.startswith(("KAILASH_JWT_", "KAILASH_API_KEY_")) or name in {
            "KAILASH_API_GATEWAY_SECRET",
            "KAILASH_AUTH_EXEMPT_PATHS",
        }:
            monkeypatch.delenv(name)
    expected = (
        Path(__file__).resolve().parents[2]
        / "src/kailash/middleware/communication/api_gateway.py"
    )
    assert Path(subject.__file__).resolve() == expected
    return monkeypatch


@pytest.mark.parametrize(
    "secret,kwargs,error,message",
    [
        (None, {}, RuntimeError, "requires KAILASH_API_GATEWAY_SECRET"),
        ("short", {}, ValueError, "at least 32 bytes"),
        (
            None,
            {"enable_auth": False, "require_auth": True},
            ServerAuthNotConfiguredError,
            None,
        ),
    ],
)
def test_invalid_auth_is_rejected_before_gateway_resources(
    clean_auth_environment, secret, kwargs, error, message
):
    monkeypatch = clean_auth_environment
    if secret is not None:
        monkeypatch.setenv("KAILASH_API_GATEWAY_SECRET", secret)

    def allocation_reached(*args, **kw):
        raise AssertionError("invalid authentication reached resource initialization")

    monkeypatch.setattr(subject.APIGateway, "_init_sdk_nodes", allocation_reached)
    monkeypatch.setattr(subject, "AgentUIMiddleware", allocation_reached)
    with pytest.raises(error, match=message):
        subject.APIGateway(**kwargs)


def test_valid_auth_initializes_gateway_and_preserves_request_gate(
    clean_auth_environment,
):
    clean_auth_environment.setenv(
        "KAILASH_API_GATEWAY_SECRET",
        "gateway-resource-ownership-secret-at-least-32-bytes",
    )
    gateway = subject.APIGateway()
    with TestClient(gateway.app) as client:
        assert client.get("/api/workflows").status_code == 401
        token = gateway.auth_manager.create_access_token(user_id="resource-test")
        token = token if isinstance(token, str) else token.access_token
        accepted = client.get(
            "/api/workflows", headers={"Authorization": f"Bearer {token}"}
        )
        assert accepted.status_code == 200
    assert gateway.agent_ui.runtime is None


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["startup", "startup_log", "body", "shutdown"])
async def test_gateway_lifespan_releases_owner_on_exception(
    clean_auth_environment, stage
):
    clean_auth_environment.setenv(
        "KAILASH_API_GATEWAY_SECRET", "gateway-lifespan-secret-at-least-32-bytes"
    )
    gateway = subject.APIGateway()
    reached = []

    async def fail():
        reached.append(stage)
        raise RuntimeError(f"controlled {stage} failure")

    if stage == "startup":
        gateway.app.router.on_startup.append(fail)
    elif stage == "startup_log":
        clean_auth_environment.setattr(gateway, "_log_startup", fail)
    elif stage == "shutdown":
        gateway.app.router.on_shutdown.append(fail)
    try:
        with pytest.raises(RuntimeError, match=f"controlled {stage} failure"):
            async with gateway.app.router.lifespan_context(gateway.app):
                if stage == "body":
                    await fail()
        assert reached == [stage]
        assert gateway.agent_ui.runtime is None
    finally:
        await gateway._cleanup()


@pytest.mark.asyncio
async def test_enhanced_shutdown_releases_owners_when_request_drain_is_cancelled(
    clean_auth_environment, tmp_path
):
    from kailash.gateway.enhanced_gateway import EnhancedDurableAPIGateway
    from kailash.middleware.gateway.event_store import EventStore

    clean_auth_environment.chdir(tmp_path)
    gateway = EnhancedDurableAPIGateway(
        auth_config={"secret": "enhanced-gateway-ownership-secret-at-least-32-bytes"},
        event_store=EventStore(storage_backend="memory"),
    )
    unwinding = asyncio.Event()
    started = asyncio.Event()

    async def request_cleanup():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            unwinding.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(request_cleanup())
    gateway._cleanup_tasks.append(task)
    shutdown = None
    try:
        await asyncio.wait_for(started.wait(), 2)
        shutdown = asyncio.create_task(gateway.shutdown())
        await asyncio.wait_for(unwinding.wait(), 2)
        shutdown.cancel()
        with pytest.raises(asyncio.CancelledError):
            await shutdown
        assert task.done()
        assert gateway._cleanup_tasks == []
        assert gateway._runtime._ref_count == 0
        assert gateway._runtime.thread_pool is None
        assert gateway.event_store._flush_task.done()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if shutdown is not None and not shutdown.done():
            shutdown.cancel()
            await asyncio.gather(shutdown, return_exceptions=True)
        await gateway.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, RuntimeError, asyncio.CancelledError])
async def test_enhanced_shutdown_releases_runtime_and_parent_even_on_cleanup_failure(
    clean_auth_environment, tmp_path, failure
):
    from kailash.gateway.enhanced_gateway import EnhancedDurableAPIGateway
    from kailash.middleware.gateway.event_store import EventStore

    assert Path(inspect.getfile(EnhancedDurableAPIGateway)).resolve() == (
        Path(__file__).resolve().parents[2] / "src/kailash/gateway/enhanced_gateway.py"
    )
    clean_auth_environment.chdir(tmp_path)
    gateway = EnhancedDurableAPIGateway(
        auth_config={"secret": "enhanced-gateway-ownership-secret-at-least-32-bytes"},
        event_store=EventStore(storage_backend="memory"),
    )
    runtime = gateway._runtime
    flush_task = gateway.event_store._flush_task
    original_cleanup = runtime.cleanup
    reached = []

    async def failed_cleanup():
        reached.append(True)
        raise failure("cleanup failure control")

    try:
        if failure is None:
            await gateway.shutdown()
            await gateway.shutdown()
        else:
            clean_auth_environment.setattr(runtime, "cleanup", failed_cleanup)
            with pytest.raises(failure, match="cleanup failure control"):
                await gateway.shutdown()
            assert reached == [True]
        assert runtime._ref_count == 0
        assert runtime.thread_pool is None
        assert flush_task.done()
    finally:
        clean_auth_environment.setattr(runtime, "cleanup", original_cleanup)
        await original_cleanup()
        runtime.close()
        await gateway.event_store.close()
