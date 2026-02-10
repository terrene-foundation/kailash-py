# Native CORS Configuration

## Status

**Specification Version**: 1.0.0
**Target Package**: kailash-nexus 1.3.0
**Depends On**: `01-public-middleware-api.md`
**Priority**: P0 (Most common middleware need)
**Estimated Effort**: 2-3h

## Problem Statement

### Current State (Broken Pattern)

CORS is the most commonly added middleware, yet every project uses the leaky abstraction:

```python
# Current pattern (from production projects)
from fastapi.middleware.cors import CORSMiddleware

app = Nexus()

# Accessing private attribute - breaks encapsulation
app._gateway.app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
```

### Evidence from Codebase

The gateway already configures CORS internally with `cors_origins=["*"]`:

```python
# apps/kailash-nexus/src/nexus/core.py:176
self._gateway = create_gateway(
    title="Kailash Nexus - Zero-Config Workflow Platform",
    server_type="enterprise",
    enable_durability=self._enable_durability,
    enable_resource_management=True,
    enable_async_execution=True,
    enable_health_checks=True,
    cors_origins=["*"],  # Hardcoded, cannot be customized
    max_workers=20,
)
```

Problems:

1. **Hardcoded Default**: `cors_origins=["*"]` cannot be changed without `_gateway.app`
2. **No Production Security**: Production should restrict origins, but current API doesn't support it
3. **Duplicate Configuration**: Users add CORS middleware that conflicts with gateway's CORS

### Desired State

```python
# Simple: Constructor parameter
app = Nexus(cors_origins=["http://localhost:3000", "https://app.example.com"])

# Advanced: Full configuration
app = Nexus(
    cors_origins=["https://app.example.com"],
    cors_allow_methods=["GET", "POST", "PUT", "DELETE"],
    cors_allow_headers=["Authorization", "Content-Type"],
    cors_allow_credentials=True,
    cors_max_age=600,  # Preflight cache
)

# Or programmatic configuration
app = Nexus()
app.configure_cors(
    allow_origins=["https://app.example.com"],
    allow_methods=["*"],
)
```

## Specification

### Constructor Parameters

Add these parameters to `Nexus.__init__`:

```python
def __init__(
    self,
    # ... existing parameters ...

    # CORS Configuration (NEW)
    cors_origins: Optional[List[str]] = None,
    cors_allow_methods: Optional[List[str]] = None,
    cors_allow_headers: Optional[List[str]] = None,
    cors_allow_credentials: bool = True,
    cors_expose_headers: Optional[List[str]] = None,
    cors_max_age: int = 600,
):
    """Initialize Nexus with optional CORS configuration.

    Args:
        cors_origins: Allowed origins for CORS. Defaults to ["*"] in development,
            must be explicitly set in production.
            - Pass ["*"] to allow all origins (development only)
            - Pass specific origins: ["https://app.example.com"]
            - Pass None to use environment-aware defaults
        cors_allow_methods: Allowed HTTP methods. Defaults to ["*"].
        cors_allow_headers: Allowed request headers. Defaults to ["*"].
        cors_allow_credentials: Allow cookies/auth headers. Defaults to True.
        cors_expose_headers: Headers exposed to browser. Defaults to None.
        cors_max_age: Preflight cache duration in seconds. Defaults to 600.
    """
```

### Environment-Aware Defaults

```python
def _get_cors_defaults(self) -> Dict[str, Any]:
    """Get environment-aware CORS defaults.

    Returns:
        CORS configuration dict with sensible defaults based on NEXUS_ENV.
    """
    nexus_env = os.getenv("NEXUS_ENV", "development").lower()

    if nexus_env == "production":
        # Production: No origins allowed by default - must be explicit
        return {
            "allow_origins": [],  # Require explicit configuration
            "allow_methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            "allow_headers": ["Authorization", "Content-Type", "X-Request-ID"],
            "allow_credentials": True,
            "expose_headers": ["X-Request-ID"],
            "max_age": 600,
        }
    else:
        # Development/staging: Permissive defaults
        return {
            "allow_origins": ["*"],
            "allow_methods": ["*"],
            "allow_headers": ["*"],
            "allow_credentials": True,
            "expose_headers": [],
            "max_age": 600,
        }
```

### CORS Configuration in Gateway Initialization

Update `_initialize_gateway()` to use the CORS configuration:

```python
def _initialize_gateway(self):
    """Initialize the underlying SDK enterprise gateway."""
    # Build CORS configuration
    cors_config = self._build_cors_config()

    try:
        # CRITICAL: Pass cors_origins=None to gateway to prevent double CORS middleware.
        # Nexus will handle CORS natively via add_middleware() below with full configuration.
        # The gateway's built-in CORS only supports origins, not methods/headers/credentials.
        self._gateway = create_gateway(
            title="Kailash Nexus - Zero-Config Workflow Platform",
            server_type="enterprise",
            enable_durability=self._enable_durability,
            enable_resource_management=True,
            enable_async_execution=True,
            enable_health_checks=True,
            cors_origins=None,  # Nexus handles CORS natively - prevents double middleware
            max_workers=20,
        )

        # Apply full CORS middleware with all options
        # (gateway only supports cors_origins, we need full control)
        if cors_config["allow_origins"]:  # Only add if origins configured
            from starlette.middleware.cors import CORSMiddleware

            self._gateway.app.add_middleware(
                CORSMiddleware,
                allow_origins=cors_config["allow_origins"],
                allow_methods=cors_config["allow_methods"],
                allow_headers=cors_config["allow_headers"],
                allow_credentials=cors_config["allow_credentials"],
                expose_headers=cors_config["expose_headers"],
                max_age=cors_config["max_age"],
            )

        # ... rest of initialization ...

def _build_cors_config(self) -> Dict[str, Any]:
    """Build CORS configuration from constructor parameters and defaults."""
    defaults = self._get_cors_defaults()

    return {
        "allow_origins": self._cors_origins if self._cors_origins is not None else defaults["allow_origins"],
        "allow_methods": self._cors_allow_methods if self._cors_allow_methods is not None else defaults["allow_methods"],
        "allow_headers": self._cors_allow_headers if self._cors_allow_headers is not None else defaults["allow_headers"],
        "allow_credentials": self._cors_allow_credentials,
        "expose_headers": self._cors_expose_headers if self._cors_expose_headers is not None else defaults["expose_headers"],
        "max_age": self._cors_max_age,
    }
```

### Programmatic CORS Configuration

```python
def configure_cors(
    self,
    allow_origins: Optional[List[str]] = None,
    allow_methods: Optional[List[str]] = None,
    allow_headers: Optional[List[str]] = None,
    allow_credentials: Optional[bool] = None,
    expose_headers: Optional[List[str]] = None,
    max_age: Optional[int] = None,
) -> "Nexus":
    """Configure CORS middleware programmatically.

    This method can be called before or after start(). If called after
    the gateway is initialized, it will reconfigure the CORS middleware.

    Args:
        allow_origins: Allowed origins. If None, keeps current setting.
        allow_methods: Allowed methods. If None, keeps current setting.
        allow_headers: Allowed headers. If None, keeps current setting.
        allow_credentials: Allow credentials. If None, keeps current setting.
        expose_headers: Exposed headers. If None, keeps current setting.
        max_age: Preflight cache duration. If None, keeps current setting.

    Returns:
        self (for method chaining)

    Raises:
        ValueError: If called in production with allow_origins=["*"].

    Example:
        >>> app = Nexus()
        >>> app.configure_cors(
        ...     allow_origins=["https://app.example.com", "https://admin.example.com"],
        ...     allow_methods=["GET", "POST"],
        ... )
    """
    # Update stored configuration
    if allow_origins is not None:
        self._validate_cors_origins(allow_origins)
        self._cors_origins = allow_origins

    if allow_methods is not None:
        self._cors_allow_methods = allow_methods

    if allow_headers is not None:
        self._cors_allow_headers = allow_headers

    if allow_credentials is not None:
        self._cors_allow_credentials = allow_credentials

    if expose_headers is not None:
        self._cors_expose_headers = expose_headers

    if max_age is not None:
        self._cors_max_age = max_age

    # Apply if gateway already initialized
    if self._gateway is not None:
        self._apply_cors_middleware()

    logger.info(f"CORS configured: origins={self._cors_origins}")
    return self

def _validate_cors_origins(self, origins: List[str]) -> None:
    """Validate CORS origins configuration.

    Args:
        origins: List of origin strings to validate.

    Raises:
        ValueError: If configuration is insecure for production.
    """
    nexus_env = os.getenv("NEXUS_ENV", "development").lower()

    if nexus_env == "production" and "*" in origins:
        raise ValueError(
            "CORS allow_origins=['*'] is not allowed in production. "
            "Specify explicit origins: cors_origins=['https://app.example.com']"
        )

    # Validate origin format
    for origin in origins:
        if origin != "*" and not origin.startswith(("http://", "https://")):
            logger.warning(
                f"CORS origin '{origin}' may be invalid. "
                f"Origins should be full URLs like 'https://example.com'"
            )

def _apply_cors_middleware(self) -> None:
    """Apply or update CORS middleware on the gateway."""
    from starlette.middleware.cors import CORSMiddleware

    cors_config = self._build_cors_config()

    # Remove existing CORS middleware if present
    # Note: Starlette doesn't support removing middleware directly,
    # so we track and warn if reconfiguring
    if hasattr(self, "_cors_middleware_applied") and self._cors_middleware_applied:
        logger.warning(
            "Reconfiguring CORS after gateway initialization. "
            "For best results, configure CORS before calling start()."
        )

    # Add CORS middleware
    self._gateway.app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_config["allow_origins"],
        allow_methods=cors_config["allow_methods"],
        allow_headers=cors_config["allow_headers"],
        allow_credentials=cors_config["allow_credentials"],
        expose_headers=cors_config["expose_headers"],
        max_age=cors_config["max_age"],
    )

    self._cors_middleware_applied = True
```

### CORS Introspection

```python
@property
def cors_config(self) -> Dict[str, Any]:
    """Current CORS configuration.

    Returns:
        Dictionary with current CORS settings.
    """
    return self._build_cors_config()

def is_origin_allowed(self, origin: str) -> bool:
    """Check if an origin is allowed by current CORS configuration.

    Args:
        origin: Origin URL to check (e.g., "https://app.example.com")

    Returns:
        True if origin is allowed, False otherwise.

    Example:
        >>> app = Nexus(cors_origins=["https://app.example.com"])
        >>> app.is_origin_allowed("https://app.example.com")  # True
        >>> app.is_origin_allowed("https://evil.com")  # False
    """
    origins = self._cors_origins or self._get_cors_defaults()["allow_origins"]

    if "*" in origins:
        return True

    return origin in origins
```

## Usage Examples

### Development (Permissive)

```python
# Default development configuration - allows all origins
app = Nexus()  # cors_origins defaults to ["*"] in development
```

### Production (Explicit Origins)

```python
# Production requires explicit origins
os.environ["NEXUS_ENV"] = "production"

app = Nexus(
    cors_origins=[
        "https://app.example.com",
        "https://admin.example.com",
    ]
)

# This would raise ValueError in production:
# app = Nexus(cors_origins=["*"])  # ValueError!
```

### Frontend Development with Hot Reload

```python
# Allow multiple development origins
app = Nexus(
    cors_origins=[
        "http://localhost:3000",      # React dev server
        "http://localhost:5173",      # Vite dev server
        "http://127.0.0.1:3000",      # Alternative localhost
    ],
    cors_allow_credentials=True,      # For session cookies
)
```

### API with Restricted Methods

```python
# Public read-only API
app = Nexus(
    cors_origins=["*"],
    cors_allow_methods=["GET", "OPTIONS"],  # Read-only
    cors_allow_headers=["Content-Type"],     # Minimal headers
    cors_allow_credentials=False,            # No auth
)
```

### Programmatic Configuration

```python
app = Nexus()

# Configure CORS based on environment
if os.getenv("ENVIRONMENT") == "production":
    app.configure_cors(
        allow_origins=[os.getenv("FRONTEND_URL")],
        allow_credentials=True,
    )
else:
    app.configure_cors(
        allow_origins=["*"],
    )
```

### With Preset System Integration

```python
# When using presets, CORS is auto-configured
app = Nexus(
    preset="saas",
    cors_origins=["https://app.example.com"],  # Overrides preset default
)
```

## Testing Requirements

### Unit Tests

Location: `apps/kailash-nexus/tests/unit/test_cors_config.py`

```python
class TestCorsDefaults:
    def test_development_defaults(self):
        """Development defaults allow all origins."""
        os.environ["NEXUS_ENV"] = "development"
        app = Nexus(enable_durability=False)

        config = app.cors_config
        assert config["allow_origins"] == ["*"]
        assert config["allow_methods"] == ["*"]

    def test_production_defaults_require_explicit(self):
        """Production defaults have no origins."""
        os.environ["NEXUS_ENV"] = "production"

        # Without explicit origins, defaults to empty
        app = Nexus(enable_auth=False, enable_durability=False)
        config = app.cors_config
        assert config["allow_origins"] == []

    def test_production_rejects_wildcard(self):
        """Production rejects wildcard origin."""
        os.environ["NEXUS_ENV"] = "production"

        with pytest.raises(ValueError, match="not allowed in production"):
            app = Nexus(
                cors_origins=["*"],
                enable_auth=False,
                enable_durability=False
            )


class TestCorsConfiguration:
    def test_cors_origins_parameter(self):
        """cors_origins parameter is applied."""
        app = Nexus(
            cors_origins=["http://example.com"],
            enable_durability=False,
        )

        assert app.cors_config["allow_origins"] == ["http://example.com"]

    def test_cors_methods_parameter(self):
        """cors_allow_methods parameter is applied."""
        app = Nexus(
            cors_allow_methods=["GET", "POST"],
            enable_durability=False,
        )

        assert app.cors_config["allow_methods"] == ["GET", "POST"]

    def test_configure_cors_updates_config(self):
        """configure_cors() updates configuration."""
        app = Nexus(enable_durability=False)

        app.configure_cors(allow_origins=["http://new.example.com"])

        assert app.cors_config["allow_origins"] == ["http://new.example.com"]


class TestCorsIntrospection:
    def test_is_origin_allowed_explicit(self):
        """is_origin_allowed() checks explicit origins."""
        app = Nexus(
            cors_origins=["http://allowed.com"],
            enable_durability=False,
        )

        assert app.is_origin_allowed("http://allowed.com") is True
        assert app.is_origin_allowed("http://denied.com") is False

    def test_is_origin_allowed_wildcard(self):
        """is_origin_allowed() with wildcard allows all."""
        app = Nexus(
            cors_origins=["*"],
            enable_durability=False,
        )

        assert app.is_origin_allowed("http://any.com") is True
```

### Integration Tests (NO MOCKING)

Location: `apps/kailash-nexus/tests/integration/test_cors_integration.py`

```python
class TestCorsIntegration:
    def test_cors_preflight_request(self):
        """CORS preflight request returns correct headers."""
        app = Nexus(
            cors_origins=["http://localhost:3000"],
            cors_allow_methods=["GET", "POST"],
            enable_durability=False,
        )

        client = TestClient(app._gateway.app)

        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            }
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert "POST" in response.headers["access-control-allow-methods"]

    def test_cors_actual_request(self):
        """CORS headers present on actual request."""
        app = Nexus(
            cors_origins=["http://localhost:3000"],
            enable_durability=False,
        )

        client = TestClient(app._gateway.app)

        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"}
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"

    def test_cors_blocked_origin(self):
        """Requests from non-allowed origins are blocked."""
        app = Nexus(
            cors_origins=["http://allowed.com"],
            enable_durability=False,
        )

        client = TestClient(app._gateway.app)

        response = client.get(
            "/health",
            headers={"Origin": "http://evil.com"}
        )

        # Request still succeeds (CORS is browser-enforced)
        # but no CORS headers present
        assert "access-control-allow-origin" not in response.headers

    def test_cors_credentials(self):
        """CORS credentials header present when configured."""
        app = Nexus(
            cors_origins=["http://localhost:3000"],
            cors_allow_credentials=True,
            enable_durability=False,
        )

        client = TestClient(app._gateway.app)

        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            }
        )

        assert response.headers["access-control-allow-credentials"] == "true"
```

### E2E Tests

Location: `apps/kailash-nexus/tests/e2e/test_cors_e2e.py`

```python
class TestCorsE2E:
    def test_cors_with_workflow_execution(self):
        """CORS works with workflow execution endpoint."""
        app = Nexus(
            cors_origins=["http://localhost:3000"],
            enable_durability=False,
        )

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "test", {"code": "result = {'ok': True}"})
        app.register("test_workflow", workflow.build())

        client = TestClient(app._gateway.app)

        # Preflight for POST request
        response = client.options(
            "/workflows/test_workflow/execute",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            }
        )
        assert response.status_code == 200

        # Actual POST request
        response = client.post(
            "/workflows/test_workflow/execute",
            json={},
            headers={
                "Origin": "http://localhost:3000",
                "Content-Type": "application/json",
            }
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"

    def test_cors_environment_switching(self):
        """CORS configuration changes with environment."""
        # Development
        os.environ["NEXUS_ENV"] = "development"
        dev_app = Nexus(enable_durability=False)
        assert dev_app.cors_config["allow_origins"] == ["*"]

        # Production (explicit origins required)
        os.environ["NEXUS_ENV"] = "production"
        prod_app = Nexus(
            cors_origins=["https://prod.example.com"],
            enable_auth=False,
            enable_durability=False,
        )
        assert prod_app.cors_config["allow_origins"] == ["https://prod.example.com"]
```

## Files to Modify

| File                                                            | Changes                                              |
| --------------------------------------------------------------- | ---------------------------------------------------- |
| `apps/kailash-nexus/src/nexus/core.py`                          | Add CORS constructor parameters                      |
| `apps/kailash-nexus/src/nexus/core.py`                          | Add `configure_cors()` method                        |
| `apps/kailash-nexus/src/nexus/core.py`                          | Add `cors_config` property and `is_origin_allowed()` |
| `apps/kailash-nexus/src/nexus/core.py`                          | Update `_initialize_gateway()` to use CORS config    |
| `apps/kailash-nexus/tests/unit/test_cors_config.py`             | New file - unit tests                                |
| `apps/kailash-nexus/tests/integration/test_cors_integration.py` | New file - integration tests                         |
| `apps/kailash-nexus/tests/e2e/test_cors_e2e.py`                 | New file - E2E tests                                 |

## Migration Guide

### Before (Current Pattern)

```python
from fastapi.middleware.cors import CORSMiddleware
from nexus import Nexus

app = Nexus()

# Leaky abstraction
app._gateway.app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
```

### After (New Pattern)

```python
from nexus import Nexus

# Option 1: Constructor parameters
app = Nexus(
    cors_origins=["http://localhost:3000"],
    cors_allow_methods=["*"],
    cors_allow_headers=["*"],
    cors_allow_credentials=True,
)

# Option 2: Programmatic configuration
app = Nexus()
app.configure_cors(
    allow_origins=["http://localhost:3000"],
)

# Option 3: Using preset (includes CORS)
app = Nexus(
    preset="saas",
    cors_origins=["http://localhost:3000"],
)
```

## Security Considerations

1. **Production Wildcard Rejection**: `cors_origins=["*"]` raises `ValueError` in production
2. **Origin Validation**: Warn on malformed origins (missing protocol)
3. **Credentials Warning**: Log warning if `allow_credentials=True` with `allow_origins=["*"]`
4. **Audit Logging**: Log CORS configuration changes for security audit

```python
def _validate_cors_security(self) -> None:
    """Validate CORS configuration for security issues."""
    origins = self._cors_origins or []
    credentials = self._cors_allow_credentials

    # Warn about credentials with wildcard (browser security risk)
    if "*" in origins and credentials:
        logger.warning(
            "SECURITY: allow_credentials=True with allow_origins=['*'] "
            "is a browser security risk. Browsers will reject this configuration. "
            "Use explicit origins when credentials are needed."
        )

    # Log configuration for audit
    logger.info(
        f"CORS configured: origins={origins}, credentials={credentials}"
    )
```

## Success Criteria

1. `cors_origins` constructor parameter configures CORS
2. `configure_cors()` method updates CORS configuration
3. Environment-aware defaults (permissive in dev, restricted in prod)
4. Production rejects `cors_origins=["*"]`
5. `cors_config` property returns current configuration
6. `is_origin_allowed()` helper method works
7. Unit tests pass (100%)
8. Integration tests pass with real HTTP requests (NO MOCKING)
9. E2E tests demonstrate CORS with workflow execution
10. Existing CORS tests continue to pass
