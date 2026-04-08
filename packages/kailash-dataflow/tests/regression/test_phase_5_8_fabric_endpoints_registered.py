# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for Phase 5.8 — fabric endpoint registration into Nexus.

Before this phase, ``FabricRuntime.start()`` accepted a Nexus instance,
stored it in ``self._nexus``, and never used it. ~1,555 LOC of fabric
endpoint code (``FabricServingLayer.get_routes``,
``FabricHealthManager.get_health_handler``, ``WebhookReceiver``,
``MCPIntegration``) was orphan: no requests ever reached it because
nothing called ``nexus.register_endpoint(...)``.

These tests lock in the contract that after Phase 5.8:

1. ``Nexus.register_endpoint(path, methods, handler)`` exists, accepts
   pre-start registrations (queued on the HTTPTransport), and rejects
   missing methods / missing transport.
2. ``dataflow.fabric.nexus_adapter.fabric_handler_to_fastapi`` wraps
   the fabric handler convention (dict with ``_status``, ``_headers``,
   ``_stream`` sentinels) into a FastAPI-style coroutine that returns
   ``JSONResponse`` or ``StreamingResponse``.
4. ``register_route_dicts`` registers a list of fabric route dicts
   onto a Nexus instance and returns descriptors of what was wired.
5. ``FabricRuntime._make_webhook_route`` builds a route dict that
   exposes ``WebhookReceiver.handle_webhook`` as
   ``POST /fabric/webhook/{source_name}``.
6. When ``FabricRuntime`` is constructed without a Nexus, the runtime
   logs a clear warning and stays in "background only" mode — the
   ``_registered_nexus_routes`` list is empty.

The tests use a thin stub Nexus rather than a real one to keep the
suite Tier-1 and avoid spinning up a FastAPI server.
"""

import asyncio
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.responses import JSONResponse, StreamingResponse

from dataflow.fabric.nexus_adapter import (
    fabric_handler_to_fastapi,
    register_route_dict,
    register_route_dicts,
)
from dataflow.fabric.runtime import FabricRuntime

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Stub Nexus that records register_endpoint calls
# ---------------------------------------------------------------------------


class _StubNexus:
    def __init__(self) -> None:
        self.endpoints: List[Dict[str, Any]] = []

    def register_endpoint(
        self, path: str, methods: List[str], handler: Any, **kwargs: Any
    ) -> None:
        self.endpoints.append(
            {
                "path": path,
                "methods": methods,
                "handler": handler,
                "kwargs": kwargs,
            }
        )


# ---------------------------------------------------------------------------
# 1. Nexus.register_endpoint contract
# ---------------------------------------------------------------------------


def test_nexus_register_endpoint_exists_pre_start():
    """``Nexus.register_endpoint`` is callable before the gateway starts."""
    from nexus import Nexus

    n = Nexus(api_port=18081)

    async def handler() -> Dict[str, Any]:
        return {"ok": True}

    # Should not raise even though the gateway has not been started.
    n.register_endpoint("/_test_pre_start", ["GET"], handler)


def test_nexus_register_endpoint_rejects_empty_methods():
    from nexus import Nexus

    n = Nexus(api_port=18082)

    async def handler() -> Dict[str, Any]:
        return {"ok": True}

    with pytest.raises(ValueError):
        n.register_endpoint("/_bad", [], handler)


# ---------------------------------------------------------------------------
# 2. fabric_handler_to_fastapi adapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_translates_dict_to_json_response():
    async def fabric_handler(request: Any = None, **_kwargs: Any) -> Dict[str, Any]:
        return {"_status": 201, "ok": True}

    wrapped = fabric_handler_to_fastapi(fabric_handler)
    request = MagicMock()
    response = await wrapped(request)
    assert isinstance(response, JSONResponse)
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_adapter_unwraps_data_envelope():
    async def fabric_handler(**_kwargs: Any) -> Dict[str, Any]:
        return {"_status": 200, "data": {"healthy": True}}

    wrapped = fabric_handler_to_fastapi(fabric_handler)
    request = MagicMock()
    response = await wrapped(request)
    assert isinstance(response, JSONResponse)
    assert response.status_code == 200
    # Body bytes carry the unwrapped data dict, not the envelope.
    assert b'"healthy"' in response.body
    assert b'"data"' not in response.body


@pytest.mark.asyncio
async def test_adapter_routes_streaming_handler():
    async def stream_gen():
        yield b"data: hello\n\n"
        yield b"data: world\n\n"

    async def fabric_handler(**_kwargs: Any) -> Dict[str, Any]:
        return {
            "_status": 200,
            "_headers": {"Content-Type": "text/event-stream"},
            "_stream": stream_gen(),
        }

    wrapped = fabric_handler_to_fastapi(fabric_handler)
    request = MagicMock()
    response = await wrapped(request)
    assert isinstance(response, StreamingResponse)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_adapter_passes_path_kwargs():
    captured: Dict[str, Any] = {}

    async def fabric_handler(product: str = "", **_kwargs: Any) -> Dict[str, Any]:
        captured["product"] = product
        return {"_status": 200, "data": {}}

    wrapped = fabric_handler_to_fastapi(fabric_handler)
    request = MagicMock()
    await wrapped(request, product="users")
    assert captured["product"] == "users"


@pytest.mark.asyncio
async def test_adapter_handler_without_request_kwarg():
    """Handlers that omit ``request=`` are still called correctly."""

    async def fabric_handler(product: str = "") -> Dict[str, Any]:
        return {"_status": 200, "data": {"name": product}}

    wrapped = fabric_handler_to_fastapi(fabric_handler)
    request = MagicMock()
    response = await wrapped(request, product="alpha")
    assert isinstance(response, JSONResponse)
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# 3. register_route_dict / register_route_dicts
# ---------------------------------------------------------------------------


def test_register_route_dict_calls_nexus_register_endpoint():
    nexus = _StubNexus()

    async def handler(**_: Any) -> Dict[str, Any]:
        return {"_status": 200, "data": {}}

    route = {
        "method": "GET",
        "path": "/fabric/products",
        "handler": handler,
        "metadata": {"product": "all"},
    }
    descriptor = register_route_dict(nexus, route)

    assert len(nexus.endpoints) == 1
    assert nexus.endpoints[0]["path"] == "/fabric/products"
    assert nexus.endpoints[0]["methods"] == ["GET"]
    assert descriptor["path"] == "/fabric/products"
    assert descriptor["method"] == "GET"


def test_register_route_dicts_registers_all():
    nexus = _StubNexus()

    async def handler(**_: Any) -> Dict[str, Any]:
        return {"_status": 200, "data": {}}

    routes = [
        {
            "method": "GET",
            "path": f"/fabric/p{i}",
            "handler": handler,
            "metadata": {},
        }
        for i in range(3)
    ]
    descriptors = register_route_dicts(nexus, routes)
    assert len(descriptors) == 3
    assert {ep["path"] for ep in nexus.endpoints} == {
        "/fabric/p0",
        "/fabric/p1",
        "/fabric/p2",
    }


# ---------------------------------------------------------------------------
# 4. FabricRuntime._register_with_nexus
# ---------------------------------------------------------------------------


def _make_runtime_for_register(
    nexus: Any, products: Dict[str, Any] = None
) -> FabricRuntime:
    """Build a barely-initialised FabricRuntime suitable for testing
    just the ``_register_with_nexus`` method.

    We avoid calling ``start()`` (which would touch a real database)
    by constructing the runtime, then attaching the subsystem stubs
    that ``_register_with_nexus`` reads.
    """
    runtime = FabricRuntime(
        dataflow=MagicMock(),
        sources={},
        products=products or {},
        nexus=nexus,
    )
    return runtime


def test_register_with_nexus_logs_warning_when_absent(caplog):
    runtime = _make_runtime_for_register(nexus=None)
    with caplog.at_level("WARNING", logger="dataflow.fabric.runtime"):
        runtime._register_with_nexus()
    assert any("fabric.nexus.absent" in r.message for r in caplog.records)
    assert runtime._registered_nexus_routes == []


def test_register_with_nexus_registers_serving_routes():
    nexus = _StubNexus()
    runtime = _make_runtime_for_register(nexus=nexus)

    async def product_handler(**_: Any) -> Dict[str, Any]:
        return {"_status": 200, "data": {}}

    serving = MagicMock()
    serving.get_routes.return_value = [
        {
            "method": "GET",
            "path": "/fabric/users",
            "handler": product_handler,
            "metadata": {"product": "users"},
        },
        {
            "method": "GET",
            "path": "/fabric/_batch",
            "handler": product_handler,
            "metadata": {"type": "batch"},
        },
    ]
    runtime._serving = serving

    # Health manager mocked to return route dicts.
    health = MagicMock()
    health.get_health_handler.return_value = {
        "method": "GET",
        "path": "/fabric/_health",
        "handler": product_handler,
        "metadata": {},
    }
    health.get_trace_handler.return_value = {
        "method": "GET",
        "path": "/fabric/_trace/{product}",
        "handler": product_handler,
        "metadata": {},
    }
    runtime._health_manager = health

    # Webhook receiver mocked.
    receiver = MagicMock()
    receiver.handle_webhook = AsyncMock(return_value={"accepted": True})
    runtime._webhook_receiver = receiver

    runtime._register_with_nexus()

    paths = {ep["path"] for ep in nexus.endpoints}
    assert "/fabric/users" in paths
    assert "/fabric/_batch" in paths
    assert "/fabric/_health" in paths
    assert "/fabric/_trace/{product}" in paths
    assert "/fabric/webhook/{source_name}" in paths
    assert len(runtime._registered_nexus_routes) == 5


def test_register_with_nexus_skips_subsystems_that_failed():
    """If serving raises, health/webhook still register."""
    nexus = _StubNexus()
    runtime = _make_runtime_for_register(nexus=nexus)

    serving = MagicMock()
    serving.get_routes.side_effect = RuntimeError("boom")
    runtime._serving = serving

    async def handler(**_: Any) -> Dict[str, Any]:
        return {"_status": 200, "data": {}}

    health = MagicMock()
    health.get_health_handler.return_value = {
        "method": "GET",
        "path": "/fabric/_health",
        "handler": handler,
        "metadata": {},
    }
    health.get_trace_handler.return_value = {
        "method": "GET",
        "path": "/fabric/_trace/{product}",
        "handler": handler,
        "metadata": {},
    }
    runtime._health_manager = health

    runtime._register_with_nexus()

    paths = {ep["path"] for ep in nexus.endpoints}
    assert "/fabric/_health" in paths
    # Serving routes are missing because get_routes raised.
    assert not any(p.startswith("/fabric/users") for p in paths)


# ---------------------------------------------------------------------------
# 5. _make_webhook_route end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_route_invokes_handle_webhook():
    runtime = _make_runtime_for_register(nexus=_StubNexus())
    receiver = MagicMock()
    receiver.handle_webhook = AsyncMock(return_value={"accepted": True, "reason": "ok"})
    runtime._webhook_receiver = receiver

    route = runtime._make_webhook_route()
    assert route["method"] == "POST"
    assert route["path"] == "/fabric/webhook/{source_name}"

    request = MagicMock()
    request.body = AsyncMock(return_value=b'{"event": "ping"}')
    request.headers = {"X-Signature": "abc"}
    result = await route["handler"](source_name="github", request=request)

    assert result["_status"] == 200
    assert result["accepted"] is True
    receiver.handle_webhook.assert_awaited_once()
    call = receiver.handle_webhook.await_args
    assert call.kwargs["source_name"] == "github"
    assert call.kwargs["body"] == b'{"event": "ping"}'
    assert call.kwargs["headers"]["x-signature"] == "abc"


@pytest.mark.asyncio
async def test_webhook_route_rejects_missing_source_name():
    runtime = _make_runtime_for_register(nexus=_StubNexus())
    receiver = MagicMock()
    receiver.handle_webhook = AsyncMock(return_value={"accepted": True})
    runtime._webhook_receiver = receiver

    route = runtime._make_webhook_route()
    request = MagicMock()
    request.body = AsyncMock(return_value=b"")
    request.headers = {}
    result = await route["handler"](source_name="", request=request)
    assert result["_status"] == 400
    receiver.handle_webhook.assert_not_called()
