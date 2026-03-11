"""
Security utilities for hooks system.

Provides authentication, authorization, redaction, secure loading, and isolation.
"""

from .authorization import (
    ADMIN_ROLE,
    DEVELOPER_ROLE,
    SERVICE_ROLE,
    VIEWER_ROLE,
    AuthorizedHookManager,
    HookPermission,
    HookPrincipal,
    HookRole,
)
from .isolation import IsolatedHookExecutor, IsolatedHookManager, ResourceLimits
from .metrics_auth import MetricsAuthConfig, MetricsEndpoint, SecureMetricsEndpoint
from .rate_limiting import RateLimitedHookManager, RateLimiter, RateLimitError
from .redaction import (
    DataRedactor,
    RedactionConfig,
    SecureLoggingHook,
    SensitiveDataRedactor,
)
from .secure_loader import HookSignature, SecureHookLoader, SecureHookManager
from .validation import ValidatedHookContext, ValidationConfig, validate_hook_context

__all__ = [
    # Authorization
    "HookPermission",
    "HookRole",
    "HookPrincipal",
    "AuthorizedHookManager",
    "ADMIN_ROLE",
    "DEVELOPER_ROLE",
    "SERVICE_ROLE",
    "VIEWER_ROLE",
    # Redaction
    "SensitiveDataRedactor",
    "SecureLoggingHook",
    "DataRedactor",
    "RedactionConfig",
    # Secure loading
    "HookSignature",
    "SecureHookLoader",
    "SecureHookManager",
    # Metrics authentication
    "SecureMetricsEndpoint",
    "MetricsAuthConfig",
    "MetricsEndpoint",
    # Rate limiting
    "RateLimitedHookManager",
    "RateLimitError",
    "RateLimiter",
    # Input validation
    "ValidatedHookContext",
    "validate_hook_context",
    "ValidationConfig",
    # Hook execution isolation
    "ResourceLimits",
    "IsolatedHookExecutor",
    "IsolatedHookManager",
]
