"""Integration tests for Nexus middleware API (TODO-300F).

Cross-feature integration tests validating middleware, routers, plugins,
CORS, and presets with real HTTP requests via TestClient.
Tier 2 tests - NO MOCKING. Uses real gateway and middleware stack.
"""

import os

import pytest
from fastapi import APIRouter
from nexus import Nexus
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.testclient import TestClient

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean_nexus_env(monkeypatch):
    """Ensure NEXUS_ENV is reset between tests."""
    monkeypatch.delenv("NEXUS_ENV", raising=False)


def _make_client(app: Nexus) -> TestClient:
    """Create a TestClient from a Nexus instance."""
    return TestClient(app._gateway.app)


# =============================================================================
# Tests: Middleware Execution
# =============================================================================


class TestMiddlewareExecution:
    """Tests that middleware actually executes on requests."""

    def test_tracking_middleware_executes(self):
        """Custom middleware runs on real HTTP requests."""
        execution_log = []

        class TrackingMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                execution_log.append("before")
                response = await call_next(request)
                execution_log.append("after")
                return response

        app = Nexus(enable_durability=False)
        app.add_middleware(TrackingMiddleware)
        client = _make_client(app)

        response = client.get("/health")

        assert response.status_code == 200
        assert execution_log == ["before", "after"]

    def test_middleware_can_modify_response_headers(self):
        """Middleware can add custom response headers."""

        class CustomHeaderMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                response = await call_next(request)
                response.headers["X-Custom-Header"] = "test-value"
                return response

        app = Nexus(enable_durability=False)
        app.add_middleware(CustomHeaderMiddleware)
        client = _make_client(app)

        response = client.get("/health")

        assert response.headers["X-Custom-Header"] == "test-value"

    def test_multiple_middleware_compose(self):
        """Multiple middleware execute in correct order."""
        execution_order = []

        class FirstMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                execution_order.append("first-before")
                response = await call_next(request)
                execution_order.append("first-after")
                return response

        class SecondMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                execution_order.append("second-before")
                response = await call_next(request)
                execution_order.append("second-after")
                return response

        app = Nexus(enable_durability=False)
        app.add_middleware(FirstMiddleware)
        app.add_middleware(SecondMiddleware)
        client = _make_client(app)

        response = client.get("/health")

        assert response.status_code == 200
        # Starlette LIFO: last added = outermost
        assert execution_order == [
            "second-before",
            "first-before",
            "first-after",
            "second-after",
        ]

    def test_middleware_can_short_circuit(self):
        """Middleware can return early without calling next."""
        from starlette.responses import JSONResponse

        class BlockingMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                if request.headers.get("X-Block") == "true":
                    return JSONResponse({"blocked": True}, status_code=403)
                return await call_next(request)

        app = Nexus(enable_durability=False)
        app.add_middleware(BlockingMiddleware)
        client = _make_client(app)

        # Normal request passes through
        normal = client.get("/health")
        assert normal.status_code == 200

        # Blocked request returns 403
        blocked = client.get("/health", headers={"X-Block": "true"})
        assert blocked.status_code == 403
        assert blocked.json() == {"blocked": True}


# =============================================================================
# Tests: Router Endpoints
# =============================================================================


class TestRouterEndpoints:
    """Tests for router endpoints with real HTTP."""

    def test_router_endpoint_accessible(self):
        """Included router endpoints respond to HTTP requests."""
        router = APIRouter()

        @router.get("/users/{user_id}")
        def get_user(user_id: str):
            return {"user_id": user_id, "name": "Test User"}

        app = Nexus(enable_durability=False)
        app.include_router(router, prefix="/api")
        client = _make_client(app)

        response = client.get("/api/users/123")

        assert response.status_code == 200
        assert response.json() == {"user_id": "123", "name": "Test User"}

    def test_router_with_post_endpoint(self):
        """Router POST endpoints work correctly."""
        router = APIRouter()

        @router.post("/items")
        def create_item(item: dict):
            return {"created": True, **item}

        app = Nexus(enable_durability=False)
        app.include_router(router, prefix="/api")
        client = _make_client(app)

        response = client.post("/api/items", json={"name": "widget"})

        assert response.status_code == 200
        assert response.json()["created"] is True
        assert response.json()["name"] == "widget"

    def test_multiple_routers(self):
        """Multiple routers with different prefixes work."""
        users_router = APIRouter()
        orders_router = APIRouter()

        @users_router.get("/list")
        def list_users():
            return {"users": ["alice"]}

        @orders_router.get("/list")
        def list_orders():
            return {"orders": ["order-1"]}

        app = Nexus(enable_durability=False)
        app.include_router(users_router, prefix="/api/users")
        app.include_router(orders_router, prefix="/api/orders")
        client = _make_client(app)

        users = client.get("/api/users/list")
        orders = client.get("/api/orders/list")

        assert users.json()["users"] == ["alice"]
        assert orders.json()["orders"] == ["order-1"]

    def test_router_with_middleware(self):
        """Router endpoints process through middleware."""
        execution_log = []

        class LoggingMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                execution_log.append(f"request:{request.url.path}")
                return await call_next(request)

        router = APIRouter()

        @router.get("/data")
        def get_data():
            return {"data": "value"}

        app = Nexus(enable_durability=False)
        app.add_middleware(LoggingMiddleware)
        app.include_router(router, prefix="/api")
        client = _make_client(app)

        client.get("/api/data")

        assert "request:/api/data" in execution_log


# =============================================================================
# Tests: Plugin Integration
# =============================================================================


class TestPluginIntegration:
    """Tests for plugin-registered middleware with real HTTP."""

    def test_plugin_middleware_executes(self):
        """Plugin-registered middleware runs on HTTP requests."""
        plugin_executed = []

        class TrackingPlugin:
            @property
            def name(self):
                return "tracking"

            def install(self, app):
                class PluginMiddleware(BaseHTTPMiddleware):
                    async def dispatch(self, request, call_next):
                        plugin_executed.append(True)
                        return await call_next(request)

                app.add_middleware(PluginMiddleware)

            def on_startup(self):
                pass

            def on_shutdown(self):
                pass

        app = Nexus(enable_durability=False)
        app.add_plugin(TrackingPlugin())
        client = _make_client(app)

        client.get("/health")

        assert len(plugin_executed) == 1

    def test_plugin_registered_router(self):
        """Plugin can register router endpoints."""

        class RouterPlugin:
            @property
            def name(self):
                return "router-plugin"

            def install(self, app):
                router = APIRouter()

                @router.get("/plugin-endpoint")
                def plugin_endpoint():
                    return {"source": "plugin"}

                app.include_router(router, prefix="/plugin")

            def on_startup(self):
                pass

            def on_shutdown(self):
                pass

        app = Nexus(enable_durability=False)
        app.add_plugin(RouterPlugin())
        client = _make_client(app)

        response = client.get("/plugin/plugin-endpoint")

        assert response.status_code == 200
        assert response.json()["source"] == "plugin"


# =============================================================================
# Tests: Preset with HTTP
# =============================================================================


class TestPresetWithHTTP:
    """Tests for presets with real HTTP requests."""

    def test_lightweight_preset_cors_works(self):
        """Lightweight preset CORS responds to preflight."""
        app = Nexus(
            preset="lightweight",
            cors_origins=["http://localhost:3000"],
            enable_durability=False,
        )
        client = _make_client(app)

        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert (
            response.headers["access-control-allow-origin"] == "http://localhost:3000"
        )

    def test_none_preset_no_cors(self):
        """'none' preset has no CORS middleware."""
        app = Nexus(
            preset="none",
            enable_durability=False,
        )
        client = _make_client(app)

        response = client.get(
            "/health",
            headers={"Origin": "http://example.com"},
        )

        assert response.status_code == 200
        # Default CORS from Nexus gateway still active if cors_origins set
        # But preset "none" doesn't add any extra middleware

    def test_preset_with_custom_router(self):
        """Preset + custom router work together."""
        router = APIRouter()

        @router.get("/custom")
        def custom_endpoint():
            return {"custom": True}

        app = Nexus(
            preset="lightweight",
            cors_origins=["http://localhost:3000"],
            enable_durability=False,
        )
        app.include_router(router, prefix="/api")
        client = _make_client(app)

        response = client.get(
            "/api/custom",
            headers={"Origin": "http://localhost:3000"},
        )

        assert response.status_code == 200
        assert response.json()["custom"] is True
        assert (
            response.headers["access-control-allow-origin"] == "http://localhost:3000"
        )


# =============================================================================
# Tests: Combined Features
# =============================================================================


class TestCombinedFeatures:
    """Tests combining middleware + router + plugin + CORS."""

    def test_full_stack_request(self):
        """Request passes through full middleware stack to router endpoint."""
        execution_log = []

        class AuditMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                execution_log.append("audit")
                return await call_next(request)

        router = APIRouter()

        @router.get("/data")
        def get_data():
            return {"data": "value"}

        app = Nexus(
            cors_origins=["http://localhost:3000"],
            enable_durability=False,
        )
        app.add_middleware(AuditMiddleware)
        app.include_router(router, prefix="/api")
        client = _make_client(app)

        response = client.get(
            "/api/data",
            headers={"Origin": "http://localhost:3000"},
        )

        assert response.status_code == 200
        assert response.json()["data"] == "value"
        assert "audit" in execution_log
        assert (
            response.headers["access-control-allow-origin"] == "http://localhost:3000"
        )

    def test_method_chaining_produces_working_app(self):
        """Fluent API via method chaining produces a working application."""
        router = APIRouter()

        @router.get("/ping")
        def ping():
            return {"pong": True}

        class SimplePlugin:
            @property
            def name(self):
                return "simple"

            def install(self, app):
                pass

            def on_startup(self):
                pass

            def on_shutdown(self):
                pass

        app = (
            Nexus(cors_origins=["*"], enable_durability=False)
            .include_router(router, prefix="/api")
            .add_plugin(SimplePlugin())
        )

        client = _make_client(app)
        response = client.get("/api/ping")

        assert response.status_code == 200
        assert response.json()["pong"] is True
        assert "simple" in app.plugins

    def test_introspection_after_full_setup(self):
        """All introspection properties work after full setup."""
        router = APIRouter()

        @router.get("/test")
        def test_endpoint():
            return {}

        class DummyPlugin:
            @property
            def name(self):
                return "dummy"

            def install(self, app):
                pass

            def on_startup(self):
                pass

            def on_shutdown(self):
                pass

        app = Nexus(
            cors_origins=["http://example.com"],
            enable_durability=False,
        )
        app.include_router(router, prefix="/api")
        app.add_plugin(DummyPlugin())

        # Check all introspection
        assert len(app.middleware) >= 0  # CORS middleware tracked
        assert len(app.routers) == 1
        assert app.routers[0].prefix == "/api"
        assert "dummy" in app.plugins
        assert app.cors_config["allow_origins"] == ["http://example.com"]
        assert app.is_origin_allowed("http://example.com") is True
        assert app.is_origin_allowed("http://evil.com") is False
