"""Nexus Preset System - Pre-configured middleware stacks.

Provides ready-to-use middleware presets that encode best practices into
one-line configurations. Eliminates boilerplate for common patterns.

Usage:
    app = Nexus(preset="lightweight")    # CORS only
    app = Nexus(preset="standard")       # CORS + rate limiting + error handling
    app = Nexus(preset="saas")           # Full SaaS stack
    app = Nexus(preset="enterprise")     # Enterprise features
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_SENSITIVE_PATTERNS = {
    "secret",
    "key",
    "token",
    "password",
    "credential",
    "private",
    "certificate",
}


@dataclass
class NexusConfig:
    """Unified configuration object passed to preset factories.

    SECURITY NOTE: Secrets (jwt_secret, sso_config client_secret, etc.) should
    be read from environment variables in plugin factories, NOT stored in this
    config in production. This config may be logged or serialized.
    """

    # CORS
    # SECURITY: credentials=False by default; wildcard origins + credentials=True
    # is rejected by browsers and is a misconfiguration. Set explicit origins when
    # enabling credentials.
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    cors_allow_methods: List[str] = field(default_factory=lambda: ["*"])
    cors_allow_headers: List[str] = field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = False

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
    environment: str = "development"

    def __repr__(self) -> str:
        """Return string representation with secrets redacted."""
        safe_jwt = "[REDACTED]" if self.jwt_secret else None
        safe_sso = None
        if self.sso_config:
            safe_sso = {
                k: (
                    "[REDACTED]"
                    if any(p in k.lower() for p in _SENSITIVE_PATTERNS)
                    else v
                )
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


@dataclass
class PresetConfig:
    """Configuration for a middleware preset."""

    name: str
    description: str
    middleware_factories: List[Callable[["NexusConfig"], Optional[tuple]]] = field(
        default_factory=list
    )
    plugin_factories: List[Callable[["NexusConfig"], Optional[Any]]] = field(
        default_factory=list
    )


# =============================================================================
# Middleware Factory Functions
# =============================================================================


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
        },
    )


# NOTE: Placeholder factories for WS02 auth package.
# These will be replaced with real implementations when auth package is complete.


def _rate_limit_middleware_factory(config: NexusConfig) -> Optional[tuple]:
    """Placeholder: Create rate limiting middleware configuration."""
    if config.rate_limit is None:
        return None

    logger.warning(
        "Rate limiting middleware not yet implemented. "
        "Install with: pip install kailash-nexus[auth] (coming in WS02)"
    )
    return None


def _error_handler_middleware_factory(config: NexusConfig) -> Optional[tuple]:
    """Placeholder: Create error handling middleware configuration."""
    logger.debug("Error handler middleware not yet implemented (coming in WS02)")
    return None


# =============================================================================
# Plugin Factory Functions
# =============================================================================


def _jwt_auth_plugin_factory(config: NexusConfig) -> Optional[Any]:
    """Placeholder: Create JWT auth plugin if configured."""
    if not config.jwt_secret:
        return None

    logger.warning(
        "JWT auth plugin not yet implemented. "
        "Install with: pip install kailash-nexus[auth] (coming in WS02)"
    )
    return None


def _rbac_plugin_factory(config: NexusConfig) -> Optional[Any]:
    """Placeholder: Create RBAC plugin if configured."""
    if not config.rbac_config:
        return None

    logger.warning(
        "RBAC plugin not yet implemented. "
        "Install with: pip install kailash-nexus[auth] (coming in WS02)"
    )
    return None


def _tenant_isolation_plugin_factory(config: NexusConfig) -> Optional[Any]:
    """Placeholder: Create tenant isolation plugin."""
    logger.warning(
        "Tenant isolation plugin not yet implemented. "
        "Install with: pip install kailash-nexus[auth] (coming in WS02)"
    )
    return None


def _audit_plugin_factory(config: NexusConfig) -> Optional[Any]:
    """Placeholder: Create audit plugin if enabled."""
    if not config.audit_enabled:
        return None

    logger.warning(
        "Audit plugin not yet implemented. "
        "Install with: pip install kailash-nexus[auth] (coming in WS02)"
    )
    return None


def _sso_plugin_factory(config: NexusConfig) -> Optional[Any]:
    """Placeholder: Create SSO plugin if configured."""
    if not config.sso_provider:
        return None

    logger.warning(
        "SSO plugin not yet implemented. "
        "Install with: pip install kailash-nexus[auth] (coming in WS02)"
    )
    return None


def _feature_flags_plugin_factory(config: NexusConfig) -> Optional[Any]:
    """Placeholder: Create feature flags plugin if configured."""
    if not config.feature_flags_provider:
        return None

    logger.warning(
        "Feature flags plugin not yet implemented. "
        "Install with: pip install kailash-nexus[auth] (coming in WS02)"
    )
    return None


# =============================================================================
# Preset Registry
# =============================================================================

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
    """Get a preset configuration by name.

    Args:
        name: Preset name (none, lightweight, standard, saas, enterprise).

    Returns:
        PresetConfig for the named preset.

    Raises:
        ValueError: If the preset name is unknown.
    """
    if name not in PRESETS:
        available = ", ".join(PRESETS.keys())
        raise ValueError(f"Unknown preset '{name}'. Available: {available}")
    return PRESETS[name]


def apply_preset(app: Any, preset_name: str, config: NexusConfig) -> None:
    """Apply a preset to a Nexus instance.

    Args:
        app: The Nexus application instance.
        preset_name: Name of the preset to apply.
        config: NexusConfig with configuration values.
    """
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
