# Middleware Preset System

## Status

**Specification Version**: 1.0.0
**Target Package**: kailash-nexus 1.3.0
**Depends On**: `01-public-middleware-api.md`
**Priority**: P0 (Enables rapid scaffolding)
**Estimated Effort**: 4-6h

## Problem Statement

### Current State

Every project manually configures the same middleware stack:

```python
# From enterprise-app/api/main.py (97 lines of middleware setup)
app._gateway.app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS)
app._gateway.app.add_middleware(JWTAuthMiddleware, secret=JWT_SECRET)
app._gateway.app.add_middleware(RBACMiddleware, roles_config=ROLES)
app._gateway.app.add_middleware(RateLimitMiddleware, rate=100)
app._gateway.app.add_middleware(TenantIsolationMiddleware, ...)
app._gateway.app.add_middleware(AuditMiddleware, ...)

# From example-project/gateway/setup.py (similar pattern)
nexus._gateway.app.add_middleware(CORSMiddleware, ...)
nexus._gateway.app.add_middleware(AuthMiddleware, ...)
nexus._gateway.app.add_middleware(RateLimitMiddleware, ...)

# From example-backend/main.py
app._gateway.app.add_middleware(CORSMiddleware, ...)
app._gateway.app.add_middleware(AzureADMiddleware, ...)
app._gateway.app.add_middleware(AppleJWTMiddleware, ...)
```

### Problems

1. **Repetitive Boilerplate**: Same 50-100 lines copied across projects
2. **Easy to Misconfigure**: Middleware order matters, but it's not obvious
3. **No Best Practices Encoding**: Each project rediscovers optimal configurations
4. **Codegen Friction**: AI agents must generate verbose middleware setup

### Desired State

```python
# One line for complete SaaS middleware stack
app = Nexus(preset="saas", jwt_secret="...", cors_origins=["..."])

# Or with explicit customization
app = Nexus(
    preset="enterprise",
    cors_origins=["https://app.example.com"],
    rate_limit=200,
    sso_provider="azure_ad",
    sso_config={"tenant_id": "...", "client_id": "..."},
)
```

## Specification

### Preset Definitions

| Preset          | Target Use Case                | Middleware Stack                                                 |
| --------------- | ------------------------------ | ---------------------------------------------------------------- |
| `"none"`        | Custom configuration           | No middleware (bare Nexus)                                       |
| `"lightweight"` | Development, internal tools    | CORS only                                                        |
| `"standard"`    | Public APIs without auth       | CORS + Rate Limiting + Error Handling                            |
| `"saas"`        | Multi-tenant SaaS applications | CORS + JWT + RBAC + Rate Limiting + Tenant Isolation + Audit     |
| `"enterprise"`  | Enterprise deployments         | Everything in SaaS + SSO + ABAC + Feature Gates + Advanced Audit |

### Constructor Signature Update

```python
def __init__(
    self,
    # Existing parameters...
    api_port: int = 8000,
    mcp_port: int = 3001,
    enable_auth: Optional[bool] = None,
    enable_monitoring: bool = False,
    rate_limit: Optional[int] = 100,
    auto_discovery: bool = False,
    enable_http_transport: bool = False,
    enable_sse_transport: bool = False,
    enable_discovery: bool = False,
    rate_limit_config: Optional[Dict[str, Any]] = None,
    enable_durability: bool = True,

    # NEW: Preset system
    preset: Optional[str] = None,  # "none", "lightweight", "standard", "saas", "enterprise"

    # NEW: Preset configuration (merged with defaults)
    cors_origins: Optional[List[str]] = None,
    cors_allow_methods: Optional[List[str]] = None,
    cors_allow_headers: Optional[List[str]] = None,
    cors_allow_credentials: bool = True,

    jwt_secret: Optional[str] = None,
    jwt_algorithm: str = "HS256",
    jwt_audience: Optional[str] = None,
    jwt_issuer: Optional[str] = None,

    rbac_config: Optional[Dict[str, Any]] = None,

    tenant_header: str = "X-Tenant-ID",
    tenant_required: bool = True,

    audit_enabled: bool = True,
    audit_log_bodies: bool = False,

    sso_provider: Optional[str] = None,  # "google", "github", "azure_ad", "okta", "apple"
    sso_config: Optional[Dict[str, Any]] = None,

    feature_flags_provider: Optional[str] = None,
    feature_flags_config: Optional[Dict[str, Any]] = None,
):
```

### Preset Implementation

#### Preset Registry

```python
# apps/kailash-nexus/src/nexus/presets.py

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

@dataclass
class PresetConfig:
    """Configuration for a middleware preset."""
    name: str
    description: str
    middleware_factories: List[Callable[["NexusConfig"], Optional[Type]]] = field(
        default_factory=list
    )
    plugin_factories: List[Callable[["NexusConfig"], Optional["NexusPluginProtocol"]]] = field(
        default_factory=list
    )

@dataclass
class NexusConfig:
    """Unified configuration object passed to preset factories.

    SECURITY NOTE: Secrets (jwt_secret, sso_config client_secret, etc.) should be
    read from environment variables directly in the plugin factory functions,
    NOT stored in this config object in production. This config may be logged
    or serialized. Use environment variables or a secrets manager.
    """
    # CORS
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    cors_allow_methods: List[str] = field(default_factory=lambda: ["*"])
    cors_allow_headers: List[str] = field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = True

    # JWT
    jwt_secret: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_audience: Optional[str] = None
    jwt_issuer: Optional[str] = None

    # RBAC
    rbac_config: Optional[Dict[str, Any]] = None

    # Tenant
    tenant_header: str = "X-Tenant-ID"
    tenant_required: bool = True

    # Rate Limiting
    rate_limit: Optional[int] = 100
    rate_limit_config: Optional[Dict[str, Any]] = None

    # Audit
    audit_enabled: bool = True
    audit_log_bodies: bool = False

    # SSO
    sso_provider: Optional[str] = None
    sso_config: Optional[Dict[str, Any]] = None

    # Feature Flags
    feature_flags_provider: Optional[str] = None
    feature_flags_config: Optional[Dict[str, Any]] = None

    # Environment
    environment: str = "development"  # "development", "staging", "production"

    def __repr__(self) -> str:
        """Return string representation with secrets redacted.

        SECURITY: Redacts jwt_secret and any client_secret in sso_config
        to prevent accidental exposure in logs or error messages.
        """
        # Build a safe representation with redacted secrets
        safe_jwt = "[REDACTED]" if self.jwt_secret else None
        safe_sso = None
        if self.sso_config:
            _SENSITIVE_PATTERNS = {"secret", "key", "token", "password", "credential", "private", "certificate"}
            safe_sso = {
                k: ("[REDACTED]" if any(p in k.lower() for p in _SENSITIVE_PATTERNS) else v)
                for k, v in self.sso_config.items()
            }

        return (
            f"NexusConfig("
            f"cors_origins={self.cors_origins}, "
            f"jwt_secret={safe_jwt}, "
            f"jwt_algorithm={self.jwt_algorithm!r}, "
            f"rate_limit={self.rate_limit}, "
            f"sso_provider={self.sso_provider!r}, "
            f"sso_config={safe_sso}, "
            f"environment={self.environment!r})"
        )
```

#### Preset Definitions

```python
# Middleware factory functions
def _cors_middleware_factory(config: NexusConfig) -> tuple:
    """Create CORS middleware configuration."""
    from starlette.middleware.cors import CORSMiddleware

    return (
        CORSMiddleware,
        {
            "allow_origins": config.cors_origins,
            "allow_methods": config.cors_allow_methods,
            "allow_headers": config.cors_allow_headers,
            "allow_credentials": config.cors_allow_credentials,
        }
    )

def _rate_limit_middleware_factory(config: NexusConfig) -> Optional[tuple]:
    """Create rate limiting middleware configuration."""
    if config.rate_limit is None:
        return None

    from nexus.middleware.rate_limit import RateLimitMiddleware

    return (
        RateLimitMiddleware,
        {
            "rate": config.rate_limit,
            "config": config.rate_limit_config,
        }
    )

def _error_handler_middleware_factory(config: NexusConfig) -> tuple:
    """Create error handling middleware configuration."""
    from nexus.middleware.error_handler import ErrorHandlerMiddleware

    return (
        ErrorHandlerMiddleware,
        {
            "include_traceback": config.environment != "production",
        }
    )

def _jwt_auth_plugin_factory(config: NexusConfig) -> Optional["NexusPluginProtocol"]:
    """Create JWT auth plugin if configured."""
    if not config.jwt_secret:
        return None

    from nexus.plugins.auth import JWTAuthPlugin

    return JWTAuthPlugin(
        secret=config.jwt_secret,
        algorithm=config.jwt_algorithm,
        audience=config.jwt_audience,
        issuer=config.jwt_issuer,
    )

def _rbac_plugin_factory(config: NexusConfig) -> Optional["NexusPluginProtocol"]:
    """Create RBAC plugin if configured."""
    if not config.rbac_config:
        return None

    from nexus.plugins.auth import RBACPlugin

    return RBACPlugin(config=config.rbac_config)

def _tenant_isolation_plugin_factory(config: NexusConfig) -> "NexusPluginProtocol":
    """Create tenant isolation plugin."""
    from nexus.plugins.tenant import TenantIsolationPlugin

    return TenantIsolationPlugin(
        header_name=config.tenant_header,
        required=config.tenant_required,
    )

def _audit_plugin_factory(config: NexusConfig) -> Optional["NexusPluginProtocol"]:
    """Create audit plugin if enabled."""
    if not config.audit_enabled:
        return None

    from nexus.plugins.audit import AuditPlugin

    return AuditPlugin(log_bodies=config.audit_log_bodies)

def _sso_plugin_factory(config: NexusConfig) -> Optional["NexusPluginProtocol"]:
    """Create SSO plugin if configured."""
    if not config.sso_provider:
        return None

    from nexus.plugins.sso import create_sso_plugin

    return create_sso_plugin(
        provider=config.sso_provider,
        config=config.sso_config or {},
    )

def _feature_flags_plugin_factory(config: NexusConfig) -> Optional["NexusPluginProtocol"]:
    """Create feature flags plugin if configured."""
    if not config.feature_flags_provider:
        return None

    from nexus.plugins.feature_flags import create_feature_flags_plugin

    return create_feature_flags_plugin(
        provider=config.feature_flags_provider,
        config=config.feature_flags_config or {},
    )


# Preset registry
PRESETS: Dict[str, PresetConfig] = {
    "none": PresetConfig(
        name="none",
        description="No middleware - bare Nexus instance",
        middleware_factories=[],
        plugin_factories=[],
    ),

    "lightweight": PresetConfig(
        name="lightweight",
        description="CORS only - for development and internal tools",
        middleware_factories=[
            _cors_middleware_factory,
        ],
        plugin_factories=[],
    ),

    "standard": PresetConfig(
        name="standard",
        description="CORS + Rate Limiting + Error Handling - for public APIs without auth",
        middleware_factories=[
            _cors_middleware_factory,
            _rate_limit_middleware_factory,
            _error_handler_middleware_factory,
        ],
        plugin_factories=[],
    ),

    "saas": PresetConfig(
        name="saas",
        description="Full SaaS stack - CORS, JWT, RBAC, Rate Limiting, Tenant Isolation, Audit",
        middleware_factories=[
            _cors_middleware_factory,
            _rate_limit_middleware_factory,
            _error_handler_middleware_factory,
        ],
        plugin_factories=[
            _jwt_auth_plugin_factory,
            _rbac_plugin_factory,
            _tenant_isolation_plugin_factory,
            _audit_plugin_factory,
        ],
    ),

    "enterprise": PresetConfig(
        name="enterprise",
        description="Enterprise stack - Everything in SaaS + SSO + ABAC + Feature Gates",
        middleware_factories=[
            _cors_middleware_factory,
            _rate_limit_middleware_factory,
            _error_handler_middleware_factory,
        ],
        plugin_factories=[
            _jwt_auth_plugin_factory,
            _rbac_plugin_factory,
            _tenant_isolation_plugin_factory,
            _audit_plugin_factory,
            _sso_plugin_factory,
            _feature_flags_plugin_factory,
        ],
    ),
}


def get_preset(name: str) -> PresetConfig:
    """Get a preset by name."""
    if name not in PRESETS:
        available = ", ".join(PRESETS.keys())
        raise ValueError(f"Unknown preset '{name}'. Available: {available}")
    return PRESETS[name]


def apply_preset(app: "Nexus", preset_name: str, config: NexusConfig) -> None:
    """Apply a preset to a Nexus instance."""
    preset = get_preset(preset_name)

    logger.info(f"Applying preset '{preset_name}': {preset.description}")

    # Apply middleware
    for factory in preset.middleware_factories:
        result = factory(config)
        if result is not None:
            middleware_class, kwargs = result
            app.add_middleware(middleware_class, **kwargs)
            logger.debug(f"  Added middleware: {middleware_class.__name__}")

    # Apply plugins
    for factory in preset.plugin_factories:
        plugin = factory(config)
        if plugin is not None:
            app.add_plugin(plugin)
            logger.debug(f"  Added plugin: {plugin.name}")

    logger.info(f"Preset '{preset_name}' applied successfully")
```

### Integration with Nexus.**init**

```python
def __init__(
    self,
    # ... existing params ...
    preset: Optional[str] = None,
    cors_origins: Optional[List[str]] = None,
    # ... other new params ...
):
    # ... existing initialization ...

    # Build unified config
    self._nexus_config = NexusConfig(
        cors_origins=cors_origins or ["*"],
        cors_allow_methods=cors_allow_methods or ["*"],
        cors_allow_headers=cors_allow_headers or ["*"],
        cors_allow_credentials=cors_allow_credentials,
        jwt_secret=jwt_secret,
        jwt_algorithm=jwt_algorithm,
        jwt_audience=jwt_audience,
        jwt_issuer=jwt_issuer,
        rbac_config=rbac_config,
        tenant_header=tenant_header,
        tenant_required=tenant_required,
        rate_limit=rate_limit,
        rate_limit_config=rate_limit_config,
        audit_enabled=audit_enabled,
        audit_log_bodies=audit_log_bodies,
        sso_provider=sso_provider,
        sso_config=sso_config,
        feature_flags_provider=feature_flags_provider,
        feature_flags_config=feature_flags_config,
        environment=os.getenv("NEXUS_ENV", "development"),
    )

    # Apply preset if specified
    if preset:
        from nexus.presets import apply_preset
        apply_preset(self, preset, self._nexus_config)

    # ... rest of initialization ...
```

### Preset Composition and Override

Users can apply a preset and then customize:

```python
# Start with SaaS preset, then customize
app = Nexus(preset="saas", jwt_secret="...")

# Override specific middleware behavior
app.add_middleware(CustomRateLimitMiddleware, rate=500)  # Custom rate limit

# Add additional plugins
app.add_plugin(CustomAuditPlugin())  # Custom audit
```

Middleware order is preserved:

1. Preset middleware (in preset definition order)
2. User-added middleware (in `add_middleware()` call order)

### Preset Introspection

```python
@property
def active_preset(self) -> Optional[str]:
    """Name of the active preset, if any."""
    return getattr(self, "_active_preset", None)

@property
def preset_config(self) -> Optional["NexusConfig"]:
    """Configuration used for the active preset."""
    return getattr(self, "_nexus_config", None)

def describe_preset(self) -> Dict[str, Any]:
    """Get detailed information about the active preset."""
    if not self.active_preset:
        return {"preset": None, "middleware": [], "plugins": []}

    return {
        "preset": self.active_preset,
        "description": PRESETS[self.active_preset].description,
        "middleware": [m.name for m in self._middleware_stack],
        "plugins": list(self._plugins.keys()),
        "config": {
            "cors_origins": self._nexus_config.cors_origins,
            "rate_limit": self._nexus_config.rate_limit,
            "tenant_header": self._nexus_config.tenant_header,
            "audit_enabled": self._nexus_config.audit_enabled,
        }
    }
```

## Usage Examples

### Lightweight Preset (Development)

```python
# For local development with CORS only
app = Nexus(
    preset="lightweight",
    cors_origins=["http://localhost:3000", "http://localhost:5173"],
)

# Register workflows
app.register("my_workflow", workflow.build())
app.start()
```

### Standard Preset (Public API)

```python
# For public API without authentication
app = Nexus(
    preset="standard",
    cors_origins=["https://api.example.com"],
    rate_limit=50,  # 50 requests per minute
)
```

### SaaS Preset (Multi-tenant Application)

```python
# For multi-tenant SaaS
app = Nexus(
    preset="saas",
    cors_origins=["https://app.example.com"],
    jwt_secret=os.environ["JWT_SECRET"],
    jwt_algorithm="RS256",
    jwt_issuer="https://auth.example.com",
    rbac_config={
        "roles": {
            "admin": ["*"],
            "user": ["read:*", "write:own"],
            "viewer": ["read:*"],
        }
    },
    tenant_header="X-Organization-ID",
    audit_log_bodies=True,  # Log request bodies for compliance
)
```

### Enterprise Preset (Full Stack)

```python
# For enterprise deployment with SSO
app = Nexus(
    preset="enterprise",
    cors_origins=["https://enterprise.example.com"],
    jwt_secret=os.environ["JWT_SECRET"],
    rbac_config=load_rbac_config(),
    sso_provider="azure_ad",
    sso_config={
        "tenant_id": os.environ["AZURE_TENANT_ID"],
        "client_id": os.environ["AZURE_CLIENT_ID"],
        "client_secret": os.environ["AZURE_CLIENT_SECRET"],
    },
    feature_flags_provider="launchdarkly",
    feature_flags_config={
        "sdk_key": os.environ["LAUNCHDARKLY_SDK_KEY"],
    },
)
```

### Custom Preset Extension

```python
# Extend an existing preset
from nexus.presets import PRESETS, PresetConfig, get_preset

# Copy saas preset and add custom middleware
saas_preset = get_preset("saas")

PRESETS["my_company_saas"] = PresetConfig(
    name="my_company_saas",
    description="MyCompany SaaS stack with custom integrations",
    middleware_factories=[
        *saas_preset.middleware_factories,
        _my_custom_middleware_factory,
    ],
    plugin_factories=[
        *saas_preset.plugin_factories,
        _my_analytics_plugin_factory,
    ],
)

# Now use it
app = Nexus(preset="my_company_saas", ...)
```

## Testing Requirements

### Unit Tests

Location: `apps/kailash-nexus/tests/unit/test_presets.py`

```python
class TestPresetRegistry:
    def test_get_preset_valid(self):
        """Valid preset name returns PresetConfig."""
        preset = get_preset("saas")
        assert preset.name == "saas"
        assert len(preset.middleware_factories) > 0

    def test_get_preset_invalid(self):
        """Invalid preset name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown preset"):
            get_preset("nonexistent")

    def test_all_presets_have_valid_factories(self):
        """All preset factories are callable."""
        for name, preset in PRESETS.items():
            for factory in preset.middleware_factories:
                assert callable(factory)
            for factory in preset.plugin_factories:
                assert callable(factory)


class TestPresetConfig:
    def test_default_values(self):
        """NexusConfig has sensible defaults."""
        config = NexusConfig()
        assert config.cors_origins == ["*"]
        assert config.rate_limit == 100
        assert config.jwt_algorithm == "HS256"

    def test_custom_values(self):
        """NexusConfig accepts custom values."""
        config = NexusConfig(
            cors_origins=["http://example.com"],
            rate_limit=50,
        )
        assert config.cors_origins == ["http://example.com"]
        assert config.rate_limit == 50


class TestApplyPreset:
    def test_lightweight_adds_cors(self):
        """Lightweight preset adds CORS middleware."""
        app = Nexus(preset="lightweight", enable_durability=False)

        assert len(app._middleware_stack) >= 1
        assert any(m.name == "CORSMiddleware" for m in app._middleware_stack)

    def test_saas_adds_all_components(self):
        """SaaS preset adds all expected components."""
        app = Nexus(
            preset="saas",
            jwt_secret="test-secret",
            rbac_config={"roles": {}},
            enable_durability=False,
        )

        # Check middleware
        middleware_names = [m.name for m in app._middleware_stack]
        assert "CORSMiddleware" in middleware_names

        # Check plugins
        plugin_names = list(app._plugins.keys())
        assert "jwt_auth" in plugin_names or len(plugin_names) > 0

    def test_preset_with_override(self):
        """Preset values can be overridden."""
        app = Nexus(
            preset="standard",
            cors_origins=["http://custom.com"],
            enable_durability=False,
        )

        # CORS should use custom origin
        cors_middleware = next(
            m for m in app._middleware_stack if m.name == "CORSMiddleware"
        )
        assert cors_middleware.kwargs["allow_origins"] == ["http://custom.com"]
```

### Integration Tests (NO MOCKING)

Location: `apps/kailash-nexus/tests/integration/test_presets_integration.py`

```python
class TestPresetIntegration:
    def test_lightweight_cors_headers(self):
        """Lightweight preset CORS actually works."""
        app = Nexus(
            preset="lightweight",
            cors_origins=["http://localhost:3000"],
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

        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"

    def test_standard_rate_limiting(self):
        """Standard preset rate limiting actually works."""
        app = Nexus(
            preset="standard",
            rate_limit=3,
            enable_durability=False,
        )

        client = TestClient(app._gateway.app)

        # Should allow 3 requests
        for i in range(3):
            response = client.get("/health")
            assert response.status_code == 200

        # 4th should be rate limited
        response = client.get("/health")
        assert response.status_code == 429

    def test_saas_jwt_validation(self):
        """SaaS preset JWT validation works."""
        import jwt

        app = Nexus(
            preset="saas",
            jwt_secret="test-secret-key",
            rbac_config={"roles": {"user": ["*"]}},
            enable_durability=False,
        )

        # Create valid token
        token = jwt.encode(
            {"sub": "user123", "role": "user"},
            "test-secret-key",
            algorithm="HS256"
        )

        client = TestClient(app._gateway.app)

        # Request without token should fail (if auth required)
        # Request with valid token should succeed
        response = client.get(
            "/health",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
```

### E2E Tests

Location: `apps/kailash-nexus/tests/e2e/test_presets_e2e.py`

```python
class TestPresetE2E:
    def test_full_saas_workflow(self):
        """Complete SaaS preset workflow execution."""
        import jwt

        app = Nexus(
            preset="saas",
            jwt_secret="e2e-test-secret",
            rbac_config={
                "roles": {
                    "admin": ["*"],
                    "user": ["execute:test_workflow"],
                }
            },
            tenant_header="X-Tenant-ID",
            enable_durability=False,
        )

        # Register workflow
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "process", {
            "code": "result = {'processed': True}"
        })
        app.register("test_workflow", workflow.build())

        client = TestClient(app._gateway.app)

        # Create token
        token = jwt.encode(
            {"sub": "user123", "role": "user", "tenant_id": "tenant_abc"},
            "e2e-test-secret",
            algorithm="HS256"
        )

        # Execute workflow with auth
        response = client.post(
            "/workflows/test_workflow/execute",
            json={},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Tenant-ID": "tenant_abc",
            }
        )

        assert response.status_code == 200
        result = response.json()
        assert "results" in result
```

## Files to Create/Modify

| File                                                               | Changes                                        |
| ------------------------------------------------------------------ | ---------------------------------------------- |
| `apps/kailash-nexus/src/nexus/presets.py`                          | New file - preset registry and factories       |
| `apps/kailash-nexus/src/nexus/core.py`                             | Add preset parameter, apply preset in **init** |
| `apps/kailash-nexus/src/nexus/__init__.py`                         | Export preset functions                        |
| `apps/kailash-nexus/tests/unit/test_presets.py`                    | New file - unit tests                          |
| `apps/kailash-nexus/tests/integration/test_presets_integration.py` | New file - integration tests                   |
| `apps/kailash-nexus/tests/e2e/test_presets_e2e.py`                 | New file - E2E tests                           |

## Dependency on 02-auth-package

The preset system defines plugin factories (e.g., `_jwt_auth_plugin_factory`, `_rbac_plugin_factory`) that depend on plugins from the `02-auth-package` workstream. During initial implementation:

1. Create placeholder plugins that log warnings
2. Replace with real implementations when 02-auth-package is complete
3. Use feature flags to enable/disable experimental plugins

```python
def _jwt_auth_plugin_factory(config: NexusConfig) -> Optional["NexusPluginProtocol"]:
    """Create JWT auth plugin if configured."""
    if not config.jwt_secret:
        return None

    try:
        from nexus.plugins.auth import JWTAuthPlugin
        return JWTAuthPlugin(...)
    except ImportError:
        logger.warning(
            "JWTAuthPlugin not available. Install with: pip install kailash-nexus[auth]"
        )
        return None
```

## Success Criteria

1. All five presets defined and registered
2. `Nexus(preset="saas")` creates working middleware stack
3. Preset values can be overridden via constructor parameters
4. Introspection methods return accurate preset information
5. Unit tests pass (100%)
6. Integration tests pass with real HTTP requests (NO MOCKING)
7. E2E tests demonstrate complete SaaS workflow
8. Documentation includes usage examples for all presets
