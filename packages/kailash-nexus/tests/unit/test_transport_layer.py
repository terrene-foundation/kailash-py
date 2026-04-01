# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for NTR-010/011/012: Transport layer.

Tests the Transport ABC, HTTPTransport, and MCPTransport.
"""

from __future__ import annotations

import pytest

from nexus import Nexus
from nexus.registry import HandlerDef, HandlerParam, HandlerRegistry
from nexus.transports.base import Transport
from nexus.transports.http import HTTPTransport
from nexus.transports.mcp import MCPTransport


# ---------------------------------------------------------------------------
# Transport ABC tests
# ---------------------------------------------------------------------------


class TestTransportABC:
    """Tests for the Transport abstract base class."""

    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            Transport()

    def test_concrete_subclass(self):
        class Dummy(Transport):
            @property
            def name(self) -> str:
                return "dummy"

            async def start(self, registry):
                pass

            async def stop(self):
                pass

            @property
            def is_running(self) -> bool:
                return False

        t = Dummy()
        assert t.name == "dummy"
        assert t.is_running is False

    def test_on_handler_registered_default_noop(self):
        """Default on_handler_registered is a no-op."""

        class Dummy(Transport):
            @property
            def name(self) -> str:
                return "dummy"

            async def start(self, registry):
                pass

            async def stop(self):
                pass

            @property
            def is_running(self) -> bool:
                return False

        t = Dummy()
        hd = HandlerDef(name="test")
        t.on_handler_registered(hd)  # Should not raise

    def test_requires_all_abstract_methods(self):
        class Incomplete(Transport):
            @property
            def name(self) -> str:
                return "inc"

            # Missing start, stop, is_running

        with pytest.raises(TypeError):
            Incomplete()


# ---------------------------------------------------------------------------
# HTTPTransport tests
# ---------------------------------------------------------------------------


class TestHTTPTransport:
    """Tests for the HTTPTransport class."""

    def test_defaults(self):
        t = HTTPTransport()
        assert t.name == "http"
        assert t.port == 8000
        assert t.is_running is False
        assert t.app is None  # No gateway yet
        assert t.gateway is None

    def test_custom_port(self):
        t = HTTPTransport(port=9090)
        assert t.port == 9090

    def test_middleware_queued_before_gateway(self):
        """Middleware added before gateway creation is queued."""
        t = HTTPTransport()

        class DummyMiddleware:
            pass

        t.add_middleware(DummyMiddleware, key="value")
        assert len(t._middleware_queue) == 1
        assert t._middleware_queue[0].middleware_class is DummyMiddleware
        assert t._middleware_queue[0].kwargs == {"key": "value"}

    def test_router_queued_before_gateway(self):
        """Routers included before gateway creation are queued."""
        t = HTTPTransport()
        router = object()
        t.include_router(router, prefix="/api")
        assert len(t._router_queue) == 1

    def test_endpoint_queued_before_gateway(self):
        """Endpoints registered before gateway creation are queued."""
        t = HTTPTransport()

        def handler():
            pass

        t.register_endpoint("/test", ["GET"], handler)
        assert len(t._endpoint_queue) == 1

    def test_health_check(self):
        t = HTTPTransport(port=8888)
        health = t.health_check()
        assert health["transport"] == "http"
        assert health["running"] is False
        assert health["port"] == 8888
        assert health["gateway"] is False

    def test_register_workflow_noop_without_gateway(self):
        """register_workflow is a no-op when gateway is None."""
        t = HTTPTransport()
        t.register_workflow("test", object())  # Should not raise

    def test_on_handler_registered_noop_when_not_running(self):
        """on_handler_registered is a no-op when transport is not running."""
        t = HTTPTransport()
        hd = HandlerDef(name="test", metadata={"workflow": object()})
        t.on_handler_registered(hd)  # Should not raise


# ---------------------------------------------------------------------------
# MCPTransport tests
# ---------------------------------------------------------------------------


class TestMCPTransport:
    """Tests for the MCPTransport class."""

    def test_defaults(self):
        t = MCPTransport()
        assert t.name == "mcp"
        assert t.port == 3001
        assert t.is_running is False

    def test_custom_config(self):
        t = MCPTransport(port=4000, namespace="myapp", server_name="my-server")
        assert t.port == 4000
        assert t._namespace == "myapp"
        assert t._server_name == "my-server"

    def test_health_check(self):
        t = MCPTransport(port=5000)
        health = t.health_check()
        assert health["transport"] == "mcp"
        assert health["running"] is False
        assert health["port"] == 5000
        assert health["server"] is False

    def test_on_handler_registered_noop_without_server(self):
        """on_handler_registered is a no-op when server is None."""
        t = MCPTransport()
        hd = HandlerDef(name="test", func=lambda: None)
        t.on_handler_registered(hd)  # Should not raise


# ---------------------------------------------------------------------------
# Nexus transport integration
# ---------------------------------------------------------------------------


class TestNexusTransportIntegration:
    """Tests for transport management via the Nexus class."""

    def test_add_transport(self):
        """Custom transports can be added to Nexus."""

        class DummyTransport(Transport):
            @property
            def name(self) -> str:
                return "dummy"

            async def start(self, registry):
                pass

            async def stop(self):
                pass

            @property
            def is_running(self) -> bool:
                return False

        with Nexus(enable_durability=False) as app:
            t = DummyTransport()
            result = app.add_transport(t)
            assert result is app  # Chaining
            assert t in app._transports

    def test_http_transport_auto_created(self):
        """Nexus creates an HTTPTransport automatically."""
        with Nexus(enable_durability=False) as app:
            assert app._http_transport is not None
            assert isinstance(app._http_transport, HTTPTransport)
            assert app._http_transport in app._transports

    def test_fastapi_app_property(self):
        """app.fastapi_app returns the underlying FastAPI app."""
        with Nexus(enable_durability=False) as app:
            fastapi = app.fastapi_app
            # Gateway is created during __init__, so fastapi_app should not be None
            assert fastapi is not None

    def test_health_check_includes_http_transport(self):
        """health_check() includes HTTP transport health."""
        with Nexus(enable_durability=False) as app:
            health = app.health_check()
            assert "http_transport" in health
            assert health["http_transport"]["transport"] == "http"
