# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""MCP authentication -- API Key, Bearer Token, JWT, Basic Auth, OAuth 2.1."""

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

# OAuth 2.1 (requires aiohttp + jwt + cryptography)
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
except ImportError:
    pass

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
    # OAuth 2.1
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
]
