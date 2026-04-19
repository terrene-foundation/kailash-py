# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""MCP authentication -- API Key, Bearer Token, JWT, Basic Auth, OAuth 2.1."""

from typing import Optional

from kailash_mcp.auth.providers import (
    APIKeyAuth,
    AuthManager,
    AuthProvider,
    BasicAuth,
    BearerTokenAuth,
    JWTAuth,
    PermissionManager,
    RateLimiter,
)

# OAuth 2.1 — requires the [auth-oauth] extra (aiohttp + PyJWT + cryptography).
# Gate the import so a base kailash-mcp install still imports `kailash_mcp.auth`
# cleanly, and raise a descriptive ImportError if a consumer tries to use an
# OAuth symbol without the extra installed. Silent `try/except ImportError: pass`
# is BLOCKED per rules/dependencies.md § "Declared = Gated Consistently".
try:
    from kailash_mcp.auth.oauth import (
        AccessToken,
        AuthorizationCode,
        AuthorizationServer,
        ClientStore,
        ClientType,
        GrantType,
        InMemoryClientStore,
        InMemoryTokenStore,
        JWTManager,
        OAuth2Client,
        OAuthClient,
        RefreshToken,
        ResourceServer,
        TokenStore,
        TokenType,
    )

    _OAUTH_AVAILABLE = True
    _OAUTH_IMPORT_ERROR: Optional[Exception] = None
except ImportError as _oauth_import_error:  # pragma: no cover
    _OAUTH_AVAILABLE = False
    _OAUTH_IMPORT_ERROR = _oauth_import_error


_OAUTH_EXPORTS = (
    "GrantType",
    "TokenType",
    "ClientType",
    "OAuthClient",
    "AccessToken",
    "RefreshToken",
    "AuthorizationCode",
    "ClientStore",
    "InMemoryClientStore",
    "TokenStore",
    "InMemoryTokenStore",
    "JWTManager",
    "AuthorizationServer",
    "ResourceServer",
    "OAuth2Client",
)


def __getattr__(name: str):
    """Raise a descriptive ImportError for OAuth symbols when the extra is missing."""
    if name in _OAUTH_EXPORTS and not _OAUTH_AVAILABLE:
        raise ImportError(
            f"kailash_mcp.auth.{name} requires the [auth-oauth] extra: "
            f"`pip install kailash-mcp[auth-oauth]` "
            f"(missing dependency: {_OAUTH_IMPORT_ERROR})"
        )
    raise AttributeError(f"module 'kailash_mcp.auth' has no attribute {name!r}")


__all__ = [
    # Core auth
    "AuthProvider",
    "APIKeyAuth",
    "BearerTokenAuth",
    "JWTAuth",
    "BasicAuth",
    "AuthManager",
    "PermissionManager",
    "RateLimiter",
    # OAuth 2.1 (requires [auth-oauth])
    *_OAUTH_EXPORTS,
]
