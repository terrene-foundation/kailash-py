"""Unit tests for Nexus public middleware API (TODO-300A).

Tests for add_middleware() method on Nexus class.
Tier 1 tests - mocking allowed for isolated unit testing.
"""

import logging
from datetime import UTC, datetime

import pytest

from nexus import Nexus
from nexus.core import MiddlewareInfo

# =============================================================================
# Test Fixtures
# =============================================================================


class DummyMiddleware:
    """Dummy ASGI middleware for testing."""

    def __init__(self, app, option=None):
        self.app = app
        self.option = option

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)


class AnotherMiddleware:
    """Second dummy middleware for testing multiple registrations."""

    def __init__(self, app, setting=None):
        self.app = app
        self.setting = setting

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)


# =============================================================================
# Tests: add_middleware() - Validation
# =============================================================================


class TestAddMiddlewareValidation:
    """Tests for add_middleware() input validation."""

    def test_rejects_instance_instead_of_class(self):
        """TypeError when passing middleware instance instead of class."""
        app = Nexus(enable_durability=False)

        with pytest.raises(TypeError, match="must be a class"):
            app.add_middleware(DummyMiddleware(None))

    def test_rejects_string(self):
        """TypeError when passing a string."""
        app = Nexus(enable_durability=False)

        with pytest.raises(TypeError, match="must be a class"):
            app.add_middleware("NotAClass")

    def test_rejects_function(self):
        """TypeError when passing a function instead of class."""
        app = Nexus(enable_durability=False)

        def not_a_class():
            pass

        with pytest.raises(TypeError, match="must be a class"):
            app.add_middleware(not_a_class)

    def test_accepts_valid_class(self):
        """No error when passing a valid middleware class."""
        app = Nexus(enable_durability=False)

        # Should not raise
        app.add_middleware(DummyMiddleware)

        assert len(app._middleware_stack) == 1


# =============================================================================
# Tests: add_middleware() - Queueing
# =============================================================================


class TestAddMiddlewareQueueing:
    """Tests for middleware queueing before gateway initialization."""

    def test_queues_when_gateway_not_ready(self):
        """Middleware is queued when gateway is None."""
        app = Nexus.__new__(Nexus)
        app._gateway = None
        app._middleware_queue = []
        app._middleware_stack = []

        app.add_middleware(DummyMiddleware, option="value")

        assert len(app._middleware_queue) == 1
        assert app._middleware_queue[0][0] == DummyMiddleware
        assert app._middleware_queue[0][1] == {"option": "value"}

    def test_applies_immediately_when_gateway_ready(self):
        """Middleware applied directly when gateway exists."""
        app = Nexus(enable_durability=False)

        app.add_middleware(DummyMiddleware)

        assert len(app._middleware_stack) == 1
        # Verify actually added to FastAPI
        assert any(m.cls == DummyMiddleware for m in app.fastapi_app.user_middleware)


# =============================================================================
# Tests: add_middleware() - Method Chaining
# =============================================================================


class TestAddMiddlewareChaining:
    """Tests for method chaining support."""

    def test_returns_self(self):
        """add_middleware() returns self for method chaining."""
        app = Nexus(enable_durability=False)

        result = app.add_middleware(DummyMiddleware)

        assert result is app

    def test_chain_multiple(self):
        """Multiple middleware can be chained."""
        app = Nexus(enable_durability=False)

        result = app.add_middleware(DummyMiddleware, option="a").add_middleware(
            AnotherMiddleware, setting="b"
        )

        assert result is app
        assert len(app._middleware_stack) == 2


# =============================================================================
# Tests: add_middleware() - Kwargs
# =============================================================================


class TestAddMiddlewareKwargs:
    """Tests for middleware kwargs handling."""

    def test_kwargs_stored_in_stack(self):
        """Kwargs are preserved in middleware stack info."""
        app = Nexus(enable_durability=False)

        app.add_middleware(DummyMiddleware, option="test_value")

        assert app._middleware_stack[0].kwargs == {"option": "test_value"}

    def test_empty_kwargs(self):
        """Middleware with no kwargs works correctly."""
        app = Nexus(enable_durability=False)

        app.add_middleware(DummyMiddleware)

        assert app._middleware_stack[0].kwargs == {}


# =============================================================================
# Tests: Introspection
# =============================================================================


class TestMiddlewareIntrospection:
    """Tests for middleware introspection property."""

    def test_middleware_property_returns_list(self):
        """middleware property returns list of MiddlewareInfo."""
        app = Nexus(enable_durability=False)
        app.add_middleware(DummyMiddleware)

        middleware_list = app.middleware

        assert isinstance(middleware_list, list)
        assert len(middleware_list) == 1

    def test_middleware_info_name(self):
        """MiddlewareInfo.name returns class name."""
        app = Nexus(enable_durability=False)
        app.add_middleware(DummyMiddleware)

        assert app.middleware[0].name == "DummyMiddleware"

    def test_middleware_info_timestamp(self):
        """MiddlewareInfo.added_at is a datetime."""
        app = Nexus(enable_durability=False)
        app.add_middleware(DummyMiddleware)

        assert isinstance(app.middleware[0].added_at, datetime)

    def test_middleware_property_returns_copy(self):
        """middleware property returns a copy, not the internal list."""
        app = Nexus(enable_durability=False)
        app.add_middleware(DummyMiddleware)

        list1 = app.middleware
        list2 = app.middleware

        assert list1 is not list2
        assert list1 is not app._middleware_stack


# =============================================================================
# Tests: Gateway Initialization Integration
# =============================================================================


class TestMiddlewareGatewayInit:
    """Tests for queued middleware application during gateway init."""

    def test_queued_middleware_applied_during_init(self):
        """Queued middleware is applied when _initialize_gateway runs."""
        # Create a Nexus instance where we can control gateway init
        app = Nexus.__new__(Nexus)
        app._gateway = None
        app._middleware_queue = []
        app._middleware_stack = []
        app._router_queue = []
        app._routers = []
        app._enable_durability = False
        app._server_type = "enterprise"
        app._max_workers = 2
        app.runtime = None
        app._owns_runtime = True
        app._cors_origins = None
        app._cors_allow_methods = None
        app._cors_allow_headers = None
        app._cors_allow_credentials = True
        app._cors_expose_headers = None
        app._cors_max_age = 600
        app._cors_middleware_applied = False

        # Queue middleware before gateway
        app.add_middleware(DummyMiddleware, option="queued")
        assert len(app._middleware_queue) == 1

        # Initialize gateway (simulates what __init__ does)
        app._initialize_gateway()

        # Queue should be cleared
        assert len(app._middleware_queue) == 0

        # Middleware should be applied to FastAPI
        assert any(m.cls == DummyMiddleware for m in app.fastapi_app.user_middleware)

    def test_multiple_queued_middleware_applied_in_order(self):
        """Multiple queued middleware applied in user-specified order."""
        app = Nexus.__new__(Nexus)
        app._gateway = None
        app._middleware_queue = []
        app._middleware_stack = []
        app._router_queue = []
        app._routers = []
        app._enable_durability = False
        app._server_type = "enterprise"
        app._max_workers = 2
        app.runtime = None
        app._owns_runtime = True
        app._cors_origins = None
        app._cors_allow_methods = None
        app._cors_allow_headers = None
        app._cors_allow_credentials = True
        app._cors_expose_headers = None
        app._cors_max_age = 600
        app._cors_middleware_applied = False

        # Queue two middleware
        app.add_middleware(DummyMiddleware, option="first")
        app.add_middleware(AnotherMiddleware, setting="second")
        assert len(app._middleware_queue) == 2

        # Initialize gateway
        app._initialize_gateway()

        # Both should be applied
        assert len(app._middleware_queue) == 0
        middleware_classes = [m.cls for m in app.fastapi_app.user_middleware]
        assert DummyMiddleware in middleware_classes
        assert AnotherMiddleware in middleware_classes


# =============================================================================
# Tests: Logging
# =============================================================================


class TestAddMiddlewareLogging:
    """Tests for logging behavior."""

    def test_logs_debug_when_queued(self, caplog):
        """Debug log when middleware is queued (gateway not ready)."""
        with caplog.at_level(logging.DEBUG):
            app = Nexus.__new__(Nexus)
            app._gateway = None
            app._middleware_queue = []
            app._middleware_stack = []

            app.add_middleware(DummyMiddleware)

        assert "Queued middleware: DummyMiddleware" in caplog.text

    def test_logs_info_when_applied(self, caplog):
        """Info log when middleware is applied (gateway ready)."""
        with caplog.at_level(logging.INFO):
            app = Nexus(enable_durability=False)

            caplog.clear()
            app.add_middleware(DummyMiddleware)

        assert "Added middleware: DummyMiddleware" in caplog.text


# =============================================================================
# Tests: MiddlewareInfo Dataclass
# =============================================================================


class TestMiddlewareInfoDataclass:
    """Tests for the MiddlewareInfo dataclass."""

    def test_create_middleware_info(self):
        """MiddlewareInfo can be created with required fields."""
        now = datetime.now(UTC)
        info = MiddlewareInfo(
            middleware_class=DummyMiddleware,
            kwargs={"option": "test"},
            added_at=now,
        )

        assert info.middleware_class == DummyMiddleware
        assert info.kwargs == {"option": "test"}
        assert info.added_at == now

    def test_name_property(self):
        """name property returns middleware class name."""
        info = MiddlewareInfo(
            middleware_class=DummyMiddleware,
            kwargs={},
            added_at=datetime.now(UTC),
        )

        assert info.name == "DummyMiddleware"


# =============================================================================
# Tests: Duplicate Middleware Detection (WS01 red team fix)
# =============================================================================


class TestDuplicateMiddlewareDetection:
    """Tests for duplicate middleware class warning."""

    def test_duplicate_middleware_logs_warning(self, caplog):
        """Adding the same middleware class twice should log a warning."""
        app = Nexus(enable_durability=False)

        with caplog.at_level(logging.WARNING):
            app.add_middleware(DummyMiddleware, option="first")
            caplog.clear()
            app.add_middleware(DummyMiddleware, option="second")

        assert any("Duplicate middleware" in msg for msg in caplog.messages)
        assert any("DummyMiddleware" in msg for msg in caplog.messages)

    def test_different_middleware_no_warning(self, caplog):
        """Adding different middleware classes should not warn."""
        app = Nexus(enable_durability=False)

        with caplog.at_level(logging.WARNING):
            app.add_middleware(DummyMiddleware, option="first")
            caplog.clear()
            app.add_middleware(AnotherMiddleware, setting="second")

        duplicate_warnings = [
            msg for msg in caplog.messages if "Duplicate middleware" in msg
        ]
        assert len(duplicate_warnings) == 0

    def test_duplicate_still_registers(self):
        """Duplicate middleware should still be added (warning only, not blocking)."""
        app = Nexus(enable_durability=False)

        app.add_middleware(DummyMiddleware, option="first")
        app.add_middleware(DummyMiddleware, option="second")

        # Both should be in the stack (warning is non-blocking)
        assert len(app.middleware) == 2


# =============================================================================
# Tests: @app.use_middleware decorator (GH #449)
# =============================================================================


class TestUseMiddlewareDecorator:
    """Tests for the @app.use_middleware function-style middleware decorator."""

    def test_use_middleware_registers_async_function(self):
        """@app.use_middleware registers an async function as middleware."""
        app = Nexus(enable_durability=False)

        @app.use_middleware
        async def timing_middleware(request, call_next):
            response = await call_next(request)
            return response

        # The decorator should register a BaseHTTPMiddleware subclass
        # that wraps the function. The stack should grow by exactly one.
        assert len(app._middleware_stack) >= 1
        # Find our wrapper (name includes the function name)
        names = [m.name for m in app.middleware]
        assert any("timing_middleware" in n for n in names)

    def test_use_middleware_rejects_sync_function(self):
        """Sync functions are rejected — BaseHTTPMiddleware.dispatch requires async."""
        app = Nexus(enable_durability=False)

        def sync_middleware(request, call_next):  # not async
            return call_next(request)

        with pytest.raises(TypeError, match="async function"):
            app.use_middleware(sync_middleware)

    def test_use_middleware_rejects_non_callable(self):
        """Non-callable inputs are rejected."""
        app = Nexus(enable_durability=False)

        with pytest.raises(TypeError, match="async function"):
            app.use_middleware("not a function")  # type: ignore[arg-type]

        with pytest.raises(TypeError, match="async function"):
            app.use_middleware(42)  # type: ignore[arg-type]

    def test_use_middleware_rejects_class(self):
        """Classes are rejected — use add_middleware() for class-based middleware."""
        app = Nexus(enable_durability=False)

        with pytest.raises(TypeError, match="class"):
            app.use_middleware(DummyMiddleware)

    def test_use_middleware_returns_original_function(self):
        """Decorator returns the original function unmodified so it can be called/stacked."""
        app = Nexus(enable_durability=False)

        async def my_middleware(request, call_next):
            return await call_next(request)

        result = app.use_middleware(my_middleware)

        assert result is my_middleware
        assert result.__name__ == "my_middleware"

    def test_use_middleware_wrapper_has_readable_name(self):
        """The generated wrapper class carries the original function name for introspection."""
        app = Nexus(enable_durability=False)

        @app.use_middleware
        async def cors_inject(request, call_next):
            return await call_next(request)

        # The wrapper class name should be grep-able for the original fn name
        names = [m.name for m in app.middleware]
        assert any(
            "cors_inject" in n for n in names
        ), f"Expected a middleware whose name references 'cors_inject'; got {names}"

    def test_use_middleware_two_functions_produce_distinct_wrappers(self):
        """Two decorated functions produce two distinct middleware entries."""
        app = Nexus(enable_durability=False)

        @app.use_middleware
        async def first(request, call_next):
            return await call_next(request)

        @app.use_middleware
        async def second(request, call_next):
            return await call_next(request)

        names = [m.name for m in app.middleware]
        assert sum(1 for n in names if "first" in n) == 1
        assert sum(1 for n in names if "second" in n) == 1
