"""Unit tests for Nexus public router API (TODO-300B).

Tests for include_router() method on Nexus class.
Tier 1 tests - mocking allowed for isolated unit testing.
"""

import logging
from datetime import UTC, datetime

import pytest
from fastapi import APIRouter
from nexus import Nexus
from nexus.core import RouterInfo

# =============================================================================
# Test Fixtures
# =============================================================================


def _make_router(path="/test"):
    """Create a simple APIRouter with one route for testing."""
    router = APIRouter()

    @router.get(path)
    async def test_endpoint():
        return {"ok": True}

    return router


# =============================================================================
# Tests: include_router() - Validation
# =============================================================================


class TestIncludeRouterValidation:
    """Tests for include_router() input validation."""

    def test_rejects_non_router_dict(self):
        """TypeError when passing a dict."""
        app = Nexus(enable_durability=False)

        with pytest.raises(TypeError, match="must be a FastAPI APIRouter"):
            app.include_router({"not": "a router"})

    def test_rejects_non_router_string(self):
        """TypeError when passing a string."""
        app = Nexus(enable_durability=False)

        with pytest.raises(TypeError, match="must be a FastAPI APIRouter"):
            app.include_router("not a router")

    def test_rejects_non_router_class(self):
        """TypeError when passing a class instead of instance."""
        app = Nexus(enable_durability=False)

        with pytest.raises(TypeError, match="must be a FastAPI APIRouter"):
            app.include_router(APIRouter)  # Class, not instance

    def test_accepts_valid_router(self):
        """No error when passing a valid APIRouter instance."""
        app = Nexus(enable_durability=False)
        router = _make_router()

        # Should not raise
        app.include_router(router, prefix="/api")

        assert len(app._routers) == 1


# =============================================================================
# Tests: include_router() - Queueing
# =============================================================================


class TestIncludeRouterQueueing:
    """Tests for router queueing before gateway initialization."""

    def test_queues_when_gateway_not_ready(self):
        """Router is queued when gateway is None."""
        app = Nexus.__new__(Nexus)
        app._gateway = None
        app._router_queue = []
        app._routers = []

        router = _make_router()
        app.include_router(router, prefix="/api")

        assert len(app._router_queue) == 1
        assert app._router_queue[0][0] is router
        assert app._router_queue[0][1]["prefix"] == "/api"

    def test_applies_immediately_when_gateway_ready(self):
        """Router applied directly when gateway exists."""
        app = Nexus(enable_durability=False)
        router = _make_router()

        app.include_router(router, prefix="/api")

        assert len(app._routers) == 1
        # Verify routes actually exist in FastAPI app
        route_paths = [getattr(r, "path", "") for r in app._gateway.app.routes]
        assert any("/api/test" in p for p in route_paths)


# =============================================================================
# Tests: include_router() - Method Chaining
# =============================================================================


class TestIncludeRouterChaining:
    """Tests for method chaining support."""

    def test_returns_self(self):
        """include_router() returns self for method chaining."""
        app = Nexus(enable_durability=False)
        router = _make_router()

        result = app.include_router(router, prefix="/api")

        assert result is app

    def test_chain_multiple(self):
        """Multiple routers can be chained."""
        app = Nexus(enable_durability=False)
        router1 = _make_router("/users")
        router2 = _make_router("/orders")

        result = app.include_router(router1, prefix="/api/v1").include_router(
            router2, prefix="/api/v2"
        )

        assert result is app
        assert len(app._routers) == 2


# =============================================================================
# Tests: include_router() - Prefix and Tags
# =============================================================================


class TestIncludeRouterPrefixTags:
    """Tests for prefix and tags handling."""

    def test_prefix_stored_in_info(self):
        """Prefix is preserved in RouterInfo."""
        app = Nexus(enable_durability=False)
        router = _make_router()

        app.include_router(router, prefix="/api/users")

        assert app._routers[0].prefix == "/api/users"

    def test_tags_stored_in_info(self):
        """Tags are preserved in RouterInfo."""
        app = Nexus(enable_durability=False)
        router = _make_router()

        app.include_router(router, prefix="/api", tags=["Users", "Admin"])

        assert app._routers[0].tags == ["Users", "Admin"]

    def test_default_tags_empty(self):
        """Tags default to empty list."""
        app = Nexus(enable_durability=False)
        router = _make_router()

        app.include_router(router, prefix="/api")

        assert app._routers[0].tags == []

    def test_default_prefix_empty(self):
        """Prefix defaults to empty string."""
        app = Nexus(enable_durability=False)
        router = _make_router()

        app.include_router(router)

        assert app._routers[0].prefix == ""


# =============================================================================
# Tests: Introspection
# =============================================================================


class TestRouterIntrospection:
    """Tests for router introspection property."""

    def test_routers_property_returns_list(self):
        """routers property returns list of RouterInfo."""
        app = Nexus(enable_durability=False)
        router = _make_router()
        app.include_router(router, prefix="/api")

        routers_list = app.routers

        assert isinstance(routers_list, list)
        assert len(routers_list) == 1

    def test_router_info_prefix(self):
        """RouterInfo.prefix returns the prefix."""
        app = Nexus(enable_durability=False)
        router = _make_router()
        app.include_router(router, prefix="/api/users")

        assert app.routers[0].prefix == "/api/users"

    def test_router_info_timestamp(self):
        """RouterInfo.added_at is a datetime."""
        app = Nexus(enable_durability=False)
        router = _make_router()
        app.include_router(router, prefix="/api")

        assert isinstance(app.routers[0].added_at, datetime)

    def test_routers_property_returns_copy(self):
        """routers property returns a copy, not the internal list."""
        app = Nexus(enable_durability=False)
        router = _make_router()
        app.include_router(router, prefix="/api")

        list1 = app.routers
        list2 = app.routers

        assert list1 is not list2
        assert list1 is not app._routers

    def test_router_info_routes_property(self):
        """RouterInfo.routes returns route paths."""
        app = Nexus(enable_durability=False)
        router = _make_router("/items")
        app.include_router(router, prefix="/api")

        routes = app.routers[0].routes
        assert "/items" in routes


# =============================================================================
# Tests: Gateway Initialization Integration
# =============================================================================


class TestRouterGatewayInit:
    """Tests for queued router application during gateway init."""

    def test_queued_router_applied_during_init(self):
        """Queued router is applied when _initialize_gateway runs."""
        app = Nexus.__new__(Nexus)
        app._gateway = None
        app._middleware_queue = []
        app._middleware_stack = []
        app._router_queue = []
        app._routers = []
        app._enable_durability = False
        app._cors_origins = None
        app._cors_allow_methods = None
        app._cors_allow_headers = None
        app._cors_allow_credentials = True
        app._cors_expose_headers = None
        app._cors_max_age = 600
        app._cors_middleware_applied = False

        router = _make_router()
        app.include_router(router, prefix="/api")
        assert len(app._router_queue) == 1

        # Initialize gateway
        app._initialize_gateway()

        # Queue should be cleared
        assert len(app._router_queue) == 0

        # Router should be included in gateway
        route_paths = [getattr(r, "path", "") for r in app._gateway.app.routes]
        assert any("/api/test" in p for p in route_paths)

    def test_multiple_queued_routers_applied(self):
        """Multiple queued routers applied during gateway initialization."""
        app = Nexus.__new__(Nexus)
        app._gateway = None
        app._middleware_queue = []
        app._middleware_stack = []
        app._router_queue = []
        app._routers = []
        app._enable_durability = False
        app._cors_origins = None
        app._cors_allow_methods = None
        app._cors_allow_headers = None
        app._cors_allow_credentials = True
        app._cors_expose_headers = None
        app._cors_max_age = 600
        app._cors_middleware_applied = False

        router1 = _make_router("/users")
        router2 = _make_router("/orders")
        app.include_router(router1, prefix="/api/v1")
        app.include_router(router2, prefix="/api/v2")
        assert len(app._router_queue) == 2

        # Initialize gateway
        app._initialize_gateway()

        # Queue should be cleared
        assert len(app._router_queue) == 0

        # Both routers should be included
        route_paths = [getattr(r, "path", "") for r in app._gateway.app.routes]
        assert any("/api/v1/users" in p for p in route_paths)
        assert any("/api/v2/orders" in p for p in route_paths)


# =============================================================================
# Tests: Route Conflict Detection
# =============================================================================


class TestRouteConflictDetection:
    """Tests for route conflict warning."""

    def test_warns_on_duplicate_prefix(self, caplog):
        """Warning logged on potential prefix conflict."""
        with caplog.at_level(logging.WARNING):
            app = Nexus(enable_durability=False)
            router1 = _make_router("/a")
            router2 = _make_router("/b")

            app.include_router(router1, prefix="/api")
            app.include_router(router2, prefix="/api")  # Duplicate prefix

        assert "may conflict" in caplog.text

    def test_no_warning_on_different_prefix(self, caplog):
        """No warning when prefixes are different."""
        with caplog.at_level(logging.WARNING):
            app = Nexus(enable_durability=False)
            router1 = _make_router("/a")
            router2 = _make_router("/b")

            caplog.clear()
            app.include_router(router1, prefix="/api/users")
            app.include_router(router2, prefix="/api/orders")

        assert "may conflict" not in caplog.text


# =============================================================================
# Tests: Logging
# =============================================================================


class TestIncludeRouterLogging:
    """Tests for logging behavior."""

    def test_logs_debug_when_queued(self, caplog):
        """Debug log when router is queued (gateway not ready)."""
        with caplog.at_level(logging.DEBUG):
            app = Nexus.__new__(Nexus)
            app._gateway = None
            app._router_queue = []
            app._routers = []

            router = _make_router()
            app.include_router(router, prefix="/api")

        assert "Queued router" in caplog.text

    def test_logs_info_when_applied(self, caplog):
        """Info log when router is applied (gateway ready)."""
        with caplog.at_level(logging.INFO):
            app = Nexus(enable_durability=False)

            caplog.clear()
            router = _make_router()
            app.include_router(router, prefix="/api")

        assert "Included router" in caplog.text


# =============================================================================
# Tests: RouterInfo Dataclass
# =============================================================================


class TestRouterInfoDataclass:
    """Tests for the RouterInfo dataclass."""

    def test_create_router_info(self):
        """RouterInfo can be created with required fields."""
        router = _make_router()
        now = datetime.now(UTC)
        info = RouterInfo(
            router=router,
            prefix="/api",
            tags=["Users"],
            added_at=now,
        )

        assert info.router is router
        assert info.prefix == "/api"
        assert info.tags == ["Users"]
        assert info.added_at == now

    def test_routes_property(self):
        """routes property returns route paths from the router."""
        router = _make_router("/items")
        info = RouterInfo(
            router=router,
            prefix="/api",
            tags=[],
            added_at=datetime.now(UTC),
        )

        assert "/items" in info.routes
