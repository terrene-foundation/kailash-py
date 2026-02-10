# Public Middleware and Router API for Nexus

## Status

**Specification Version**: 1.0.0
**Target Package**: kailash-nexus 1.3.0
**Priority**: P0 (Blocking for 02-auth-package)
**Estimated Effort**: 8-12h

## Problem Statement

### Current State (Broken Abstraction)

All production projects access the private `_gateway.app` attribute to add FastAPI middleware and routers:

```python
# apps/kailash-nexus/tests/integration/test_security_features.py:60
self.client = TestClient(self.app._gateway.app)

# apps/kailash-nexus/tests/integration/test_sse_streaming.py:70
client = TestClient(self.app._gateway.app)

# Production usage observed in enterprise-app, example-project, example-backend:
app._gateway.app.add_middleware(CORSMiddleware, allow_origins=[...])
app._gateway.app.include_router(user_router, prefix="/api/users")
```

This pattern has three critical problems:

1. **Leaky Abstraction**: Internal implementation details exposed to users
2. **No Lifecycle Management**: Middleware added after `start()` may not apply correctly
3. **No Introspection**: Cannot list registered middleware or routers

### Evidence from Production Projects

| Project             | File                      | Pattern                                                  | Lines |
| ------------------- | ------------------------- | -------------------------------------------------------- | ----- |
| enterprise-app          | `api/main.py`             | `app._gateway.app.add_middleware(CORSMiddleware, ...)`   | 12    |
| enterprise-app          | `api/routers/__init__.py` | `app._gateway.app.include_router(...)` x 14              | 42    |
| example-project        | `gateway/setup.py`        | `nexus._gateway.app.add_middleware(...)` x 5             | 35    |
| example-backend | `main.py`                 | `app._gateway.app.add_middleware(TenantMiddleware, ...)` | 8     |

## Specification

### 1. `app.add_middleware(middleware_class, **kwargs)`

Add ASGI/Starlette middleware to the Nexus application.

#### Method Signature

```python
def add_middleware(
    self,
    middleware_class: type,
    **kwargs: Any
) -> "Nexus":
    """Add middleware to the Nexus application.

    Middleware executes in LIFO order (last added = outermost = runs first on request).
    This follows Starlette's onion model where middleware wraps inner middleware.
    Can be called before or after start() - if gateway not ready, middleware
    is queued and applied during initialization.

    Args:
        middleware_class: A valid ASGI/Starlette middleware class.
            Must be a class (not instance) that accepts `app` as first argument.
        **kwargs: Arguments passed to the middleware constructor.

    Returns:
        self (for method chaining)

    Raises:
        TypeError: If middleware_class is not a valid middleware type.
        ValueError: If middleware_class has already been added (duplicate detection).

    Example:
        >>> from starlette.middleware.cors import CORSMiddleware
        >>> app = Nexus()
        >>> app.add_middleware(
        ...     CORSMiddleware,
        ...     allow_origins=["http://localhost:3000"],
        ...     allow_methods=["*"],
        ...     allow_headers=["*"],
        ... )
    """
```

#### Implementation Requirements

1. **Validation**
   - Verify `middleware_class` is a class (not instance): `isinstance(middleware_class, type)`
   - Verify it has a callable that accepts `app` as first parameter
   - Warn (not error) on duplicate middleware class

2. **Queueing Before Gateway Ready**

   ```python
   # Internal state
   self._middleware_queue: List[Tuple[type, Dict[str, Any]]] = []
   self._middleware_stack: List[MiddlewareInfo] = []  # For introspection

   def add_middleware(self, middleware_class: type, **kwargs) -> "Nexus":
       # Validate
       if not isinstance(middleware_class, type):
           raise TypeError(
               f"middleware_class must be a class, got {type(middleware_class).__name__}. "
               f"Pass the class itself (e.g., CORSMiddleware), not an instance."
           )

       # Store for introspection
       info = MiddlewareInfo(
           middleware_class=middleware_class,
           kwargs=kwargs,
           added_at=datetime.now(UTC),
       )
       self._middleware_stack.append(info)

       # Apply or queue
       if self._gateway is not None:
           self._gateway.app.add_middleware(middleware_class, **kwargs)
           logger.info(f"Added middleware: {middleware_class.__name__}")
       else:
           self._middleware_queue.append((middleware_class, kwargs))
           logger.debug(f"Queued middleware: {middleware_class.__name__} (gateway not ready)")

       return self  # Enable chaining
   ```

3. **Apply Queued Middleware in `_initialize_gateway()`**

   ```python
   def _initialize_gateway(self):
       # ... existing gateway creation ...

       # Apply queued middleware in order added.
       # Starlette's add_middleware() uses LIFO internally (last added = outermost),
       # so we do NOT reverse - middleware is applied in the order the user added them,
       # and Starlette handles the wrapping order correctly.
       for middleware_class, kwargs in self._middleware_queue:
           self._gateway.app.add_middleware(middleware_class, **kwargs)
           logger.info(f"Applied queued middleware: {middleware_class.__name__}")

       self._middleware_queue.clear()
   ```

4. **Introspection Data Class**

   ```python
   @dataclass
   class MiddlewareInfo:
       """Information about registered middleware."""
       middleware_class: type
       kwargs: Dict[str, Any]
       added_at: datetime

       @property
       def name(self) -> str:
           return self.middleware_class.__name__
   ```

### 2. `app.include_router(router, prefix="", tags=None, dependencies=None)`

Include a FastAPI router in the Nexus application.

#### Method Signature

```python
def include_router(
    self,
    router: "APIRouter",
    prefix: str = "",
    tags: Optional[List[str]] = None,
    dependencies: Optional[List["Depends"]] = None,
    **kwargs: Any
) -> "Nexus":
    """Include a FastAPI router in the Nexus application.

    Routers provide a way to organize endpoints into logical groups.
    Can be called before or after start() - if gateway not ready, router
    is queued and included during initialization.

    Args:
        router: A FastAPI APIRouter instance.
        prefix: URL prefix for all routes in this router (e.g., "/api/users").
        tags: OpenAPI tags for all routes (for documentation grouping).
        dependencies: Dependencies to apply to all routes in this router.
        **kwargs: Additional arguments passed to FastAPI's include_router().

    Returns:
        self (for method chaining)

    Raises:
        TypeError: If router is not an APIRouter instance.
        ValueError: If prefix conflicts with existing Nexus routes.

    Example:
        >>> from fastapi import APIRouter
        >>>
        >>> user_router = APIRouter()
        >>> @user_router.get("/{user_id}")
        >>> async def get_user(user_id: str):
        ...     return {"user_id": user_id}
        >>>
        >>> app = Nexus()
        >>> app.include_router(user_router, prefix="/api/users", tags=["Users"])
    """
```

#### Implementation Requirements

1. **Validation**

   ```python
   from fastapi import APIRouter

   def include_router(self, router, prefix="", tags=None, dependencies=None, **kwargs):
       if not isinstance(router, APIRouter):
           raise TypeError(
               f"router must be a FastAPI APIRouter, got {type(router).__name__}"
           )

       # Warn on potential route conflicts (non-blocking)
       if prefix and self._has_route_conflict(prefix):
           logger.warning(
               f"Router prefix '{prefix}' may conflict with existing routes"
           )
   ```

2. **Queueing Pattern** (same as middleware)

   ```python
   self._router_queue: List[Tuple[APIRouter, Dict[str, Any]]] = []
   self._routers: List[RouterInfo] = []

   def include_router(self, router, prefix="", tags=None, dependencies=None, **kwargs):
       # ... validation ...

       router_kwargs = {
           "prefix": prefix,
           "tags": tags or [],
           "dependencies": dependencies or [],
           **kwargs
       }

       info = RouterInfo(
           router=router,
           prefix=prefix,
           tags=tags or [],
           added_at=datetime.now(UTC),
       )
       self._routers.append(info)

       if self._gateway is not None:
           self._gateway.app.include_router(router, **router_kwargs)
           logger.info(f"Included router with prefix: {prefix or '/'}")
       else:
           self._router_queue.append((router, router_kwargs))
           logger.debug(f"Queued router: {prefix or '/'} (gateway not ready)")

       return self
   ```

3. **Introspection Data Class**

   ```python
   @dataclass
   class RouterInfo:
       """Information about included routers."""
       router: "APIRouter"
       prefix: str
       tags: List[str]
       added_at: datetime

       @property
       def routes(self) -> List[str]:
           """Get all route paths in this router."""
           return [route.path for route in self.router.routes]
   ```

### 3. `app.add_plugin(plugin)`

Install a plugin that can register middleware, routers, and lifecycle hooks.

#### Plugin Protocol

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class NexusPluginProtocol(Protocol):
    """Protocol for Nexus plugins.

    Plugins provide a composable way to add functionality to Nexus.
    They can register middleware, routers, and respond to lifecycle events.
    """

    @property
    def name(self) -> str:
        """Unique plugin name."""
        ...

    def install(self, app: "Nexus") -> None:
        """Install the plugin.

        Called during add_plugin(). Use this to:
        - Register middleware via app.add_middleware()
        - Include routers via app.include_router()
        - Store references for lifecycle callbacks

        Args:
            app: The Nexus instance to install into.
        """
        ...

    def on_startup(self) -> None:
        """Called when Nexus starts.

        Optional lifecycle hook for:
        - Establishing connections
        - Warming caches
        - Starting background tasks
        """
        ...

    def on_shutdown(self) -> None:
        """Called when Nexus stops.

        Optional lifecycle hook for:
        - Closing connections
        - Flushing buffers
        - Cleanup tasks
        """
        ...
```

#### Method Signature

```python
def add_plugin(
    self,
    plugin: NexusPluginProtocol,
) -> "Nexus":
    """Install a plugin into the Nexus application.

    Plugins are a composable way to add cross-cutting functionality.
    The plugin's install() method is called immediately, and lifecycle
    hooks (on_startup, on_shutdown) are registered for later invocation.

    Args:
        plugin: An object implementing the NexusPluginProtocol.

    Returns:
        self (for method chaining)

    Raises:
        TypeError: If plugin does not implement required methods.
        ValueError: If a plugin with the same name is already installed.

    Example:
        >>> from nexus.plugins.auth import JWTAuthPlugin
        >>>
        >>> app = Nexus()
        >>> app.add_plugin(JWTAuthPlugin(
        ...     secret="your-secret-key",
        ...     algorithm="HS256",
        ... ))
    """
```

#### Implementation Requirements

```python
def add_plugin(self, plugin) -> "Nexus":
    # Validate plugin protocol
    if not hasattr(plugin, "name") or not hasattr(plugin, "install"):
        raise TypeError(
            f"Plugin must implement NexusPluginProtocol (requires 'name' and 'install'). "
            f"Got: {type(plugin).__name__}"
        )

    # Check for duplicate
    plugin_name = plugin.name
    if plugin_name in self._plugins:
        raise ValueError(f"Plugin '{plugin_name}' is already installed")

    # Store plugin
    self._plugins[plugin_name] = plugin

    # Call install immediately
    logger.info(f"Installing plugin: {plugin_name}")
    plugin.install(self)

    # Register lifecycle hooks if present
    if hasattr(plugin, "on_startup") and callable(plugin.on_startup):
        self._startup_hooks.append(plugin.on_startup)

    if hasattr(plugin, "on_shutdown") and callable(plugin.on_shutdown):
        self._shutdown_hooks.append(plugin.on_shutdown)

    logger.info(f"Plugin installed: {plugin_name}")
    return self
```

### 4. Introspection Properties

```python
@property
def middleware(self) -> List[MiddlewareInfo]:
    """List of registered middleware in application order."""
    return self._middleware_stack.copy()

@property
def routers(self) -> List[RouterInfo]:
    """List of included routers."""
    return self._routers.copy()

@property
def plugins(self) -> Dict[str, NexusPluginProtocol]:
    """Dictionary of installed plugins by name."""
    return self._plugins.copy()
```

### 5. Internal State Changes to `__init__`

```python
def __init__(self, ...):
    # ... existing initialization ...

    # Middleware and router management (NEW)
    self._middleware_queue: List[Tuple[type, Dict[str, Any]]] = []
    self._middleware_stack: List[MiddlewareInfo] = []
    self._router_queue: List[Tuple[APIRouter, Dict[str, Any]]] = []
    self._routers: List[RouterInfo] = []

    # Plugin management (NEW)
    self._plugins: Dict[str, NexusPluginProtocol] = {}
    self._startup_hooks: List[Callable[[], None]] = []
    self._shutdown_hooks: List[Callable[[], None]] = []

    # ... rest of initialization ...
```

### 6. Lifecycle Hook Integration

Update `start()` and `stop()` to call plugin lifecycle hooks:

```python
def start(self):
    # ... existing start logic ...

    # Call startup hooks
    for hook in self._startup_hooks:
        try:
            if asyncio.iscoroutinefunction(hook):
                asyncio.get_event_loop().run_until_complete(hook())
            else:
                hook()
        except Exception as e:
            logger.error(f"Startup hook failed: {e}")

    # ... rest of start ...

def stop(self):
    # Call shutdown hooks (reverse order)
    for hook in reversed(self._shutdown_hooks):
        try:
            if asyncio.iscoroutinefunction(hook):
                asyncio.get_event_loop().run_until_complete(hook())
            else:
                hook()
        except Exception as e:
            logger.error(f"Shutdown hook failed: {e}")

    # ... existing stop logic ...
```

## Migration Guide

### Before (Current Pattern)

```python
from fastapi.middleware.cors import CORSMiddleware
from fastapi import APIRouter
from nexus import Nexus

app = Nexus()

# Leaky abstraction - accessing private attribute
app._gateway.app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
)

# More leaky abstraction
user_router = APIRouter()
app._gateway.app.include_router(user_router, prefix="/api/users")
```

### After (New Pattern)

```python
from fastapi.middleware.cors import CORSMiddleware
from fastapi import APIRouter
from nexus import Nexus

app = Nexus()

# Clean public API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
)

# Clean public API
user_router = APIRouter()
app.include_router(user_router, prefix="/api/users")

# Method chaining supported
app.add_middleware(RateLimitMiddleware, rate=100) \
   .add_middleware(AuditMiddleware) \
   .include_router(health_router, prefix="/health")
```

## Testing Requirements

### Unit Tests (Tier 1)

Location: `apps/kailash-nexus/tests/unit/test_middleware_api.py`

```python
class TestAddMiddleware:
    def test_add_middleware_before_gateway(self):
        """Middleware queued when gateway not ready."""
        app = Nexus.__new__(Nexus)  # Create without __init__
        app._gateway = None
        app._middleware_queue = []
        app._middleware_stack = []

        app.add_middleware(DummyMiddleware, option="value")

        assert len(app._middleware_queue) == 1
        assert app._middleware_queue[0][0] == DummyMiddleware

    def test_add_middleware_after_gateway(self):
        """Middleware applied immediately when gateway ready."""
        app = Nexus(enable_durability=False)

        app.add_middleware(DummyMiddleware)

        assert len(app._middleware_stack) == 1
        # Verify actually added to FastAPI
        assert any(
            m.cls == DummyMiddleware
            for m in app._gateway.app.user_middleware
        )

    def test_add_middleware_rejects_instance(self):
        """TypeError when passing instance instead of class."""
        app = Nexus(enable_durability=False)

        with pytest.raises(TypeError, match="must be a class"):
            app.add_middleware(DummyMiddleware())  # Instance, not class

    def test_add_middleware_chaining(self):
        """Method chaining works."""
        app = Nexus(enable_durability=False)

        result = app.add_middleware(DummyMiddleware)

        assert result is app


class TestIncludeRouter:
    def test_include_router_basic(self):
        """Router included with prefix."""
        app = Nexus(enable_durability=False)
        router = APIRouter()

        @router.get("/test")
        def test_endpoint():
            return {"ok": True}

        app.include_router(router, prefix="/api")

        assert len(app._routers) == 1
        assert app._routers[0].prefix == "/api"

    def test_include_router_rejects_non_router(self):
        """TypeError when passing non-router."""
        app = Nexus(enable_durability=False)

        with pytest.raises(TypeError, match="must be a FastAPI APIRouter"):
            app.include_router({"not": "a router"})


class TestAddPlugin:
    def test_plugin_install_called(self):
        """Plugin.install() called on add_plugin()."""
        app = Nexus(enable_durability=False)
        plugin = DummyPlugin()

        app.add_plugin(plugin)

        assert plugin.install_called
        assert "dummy" in app._plugins

    def test_plugin_duplicate_rejected(self):
        """ValueError on duplicate plugin name."""
        app = Nexus(enable_durability=False)
        plugin = DummyPlugin()

        app.add_plugin(plugin)

        with pytest.raises(ValueError, match="already installed"):
            app.add_plugin(plugin)
```

### Integration Tests (Tier 2 - NO MOCKING)

Location: `apps/kailash-nexus/tests/integration/test_middleware_api_integration.py`

```python
class TestMiddlewareIntegration:
    def test_middleware_executes_on_request(self):
        """Middleware actually processes HTTP requests."""
        app = Nexus(enable_durability=False)

        # Track middleware execution
        execution_log = []

        class TrackingMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                execution_log.append("before")
                response = await call_next(request)
                execution_log.append("after")
                return response

        app.add_middleware(TrackingMiddleware)

        # Register a workflow so we have an endpoint
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "test", {"code": "result = {'ok': True}"})
        app.register("test", workflow.build())

        # Make real HTTP request
        client = TestClient(app._gateway.app)
        response = client.post("/workflows/test/execute", json={})

        assert response.status_code == 200
        assert execution_log == ["before", "after"]

    def test_cors_middleware_headers(self):
        """CORS middleware adds correct headers."""
        app = Nexus(enable_durability=False)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        client = TestClient(app._gateway.app)

        # Preflight request
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )

        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_router_endpoints_accessible(self):
        """Included router endpoints are accessible."""
        app = Nexus(enable_durability=False)

        router = APIRouter()
        @router.get("/users/{user_id}")
        def get_user(user_id: str):
            return {"user_id": user_id, "name": "Test User"}

        app.include_router(router, prefix="/api")

        client = TestClient(app._gateway.app)
        response = client.get("/api/users/123")

        assert response.status_code == 200
        assert response.json() == {"user_id": "123", "name": "Test User"}


class TestPluginIntegration:
    def test_plugin_middleware_works(self):
        """Plugin-registered middleware executes."""

        class AuthPlugin:
            name = "auth"

            def install(self, app):
                app.add_middleware(self.AuthMiddleware)

            class AuthMiddleware(BaseHTTPMiddleware):
                async def dispatch(self, request, call_next):
                    request.state.authenticated = True
                    return await call_next(request)

            def on_startup(self):
                pass

            def on_shutdown(self):
                pass

        app = Nexus(enable_durability=False)
        app.add_plugin(AuthPlugin())

        # Verify middleware was added
        assert len(app._middleware_stack) == 1
        assert app._middleware_stack[0].name == "AuthMiddleware"
```

### E2E Tests (Tier 3 - Real Everything)

Location: `apps/kailash-nexus/tests/e2e/test_middleware_api_e2e.py`

```python
class TestMiddlewareE2E:
    def test_full_middleware_stack(self):
        """Complete middleware stack processes request correctly."""
        app = Nexus(enable_durability=False)

        # Add multiple middleware (order matters)
        app.add_middleware(CORSMiddleware, allow_origins=["*"])
        app.add_middleware(GZipMiddleware, minimum_size=500)

        # Add router
        router = APIRouter()
        @router.get("/data")
        def get_data():
            return {"data": "x" * 1000}  # Large enough for gzip

        app.include_router(router, prefix="/api")

        # Real HTTP request
        client = TestClient(app._gateway.app)
        response = client.get(
            "/api/data",
            headers={
                "Origin": "http://example.com",
                "Accept-Encoding": "gzip",
            }
        )

        assert response.status_code == 200
        # CORS header present
        assert "access-control-allow-origin" in response.headers
        # Content-Encoding may be gzip if response large enough
```

## Files to Modify

| File                                                                      | Changes                                                            |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `apps/kailash-nexus/src/nexus/core.py`                                    | Add `add_middleware()`, `include_router()`, `add_plugin()` methods |
| `apps/kailash-nexus/src/nexus/core.py`                                    | Add `_middleware_queue`, `_router_queue`, `_plugins` attributes    |
| `apps/kailash-nexus/src/nexus/core.py`                                    | Update `_initialize_gateway()` to apply queued items               |
| `apps/kailash-nexus/src/nexus/core.py`                                    | Update `start()` and `stop()` for lifecycle hooks                  |
| `apps/kailash-nexus/src/nexus/__init__.py`                                | Export `MiddlewareInfo`, `RouterInfo`, `NexusPluginProtocol`       |
| `apps/kailash-nexus/tests/unit/test_middleware_api.py`                    | New file - unit tests                                              |
| `apps/kailash-nexus/tests/integration/test_middleware_api_integration.py` | New file - integration tests                                       |
| `apps/kailash-nexus/tests/e2e/test_middleware_api_e2e.py`                 | New file - E2E tests                                               |

## Backward Compatibility

The existing `_gateway.app` pattern will continue to work. Users who access `app._gateway.app.add_middleware()` will not break, but IDE warnings about accessing private attributes will encourage migration.

A deprecation warning should be added in a future version (1.4.0) when accessing `_gateway` directly:

```python
@property
def _gateway(self):
    import warnings
    warnings.warn(
        "Direct access to _gateway is deprecated. "
        "Use app.add_middleware() and app.include_router() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return self.__gateway
```

## Success Criteria

1. All three methods (`add_middleware`, `include_router`, `add_plugin`) implemented
2. Queueing works correctly for calls before gateway initialization
3. Introspection properties return accurate information
4. Unit tests pass (100%)
5. Integration tests pass with real HTTP requests (NO MOCKING)
6. E2E tests demonstrate full middleware stack processing
7. Existing tests in `test_security_features.py` continue to pass
8. No breaking changes to existing `_gateway.app` pattern
