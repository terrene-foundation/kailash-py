# JWT Middleware Specification

## Overview

This specification defines the JWT authentication middleware for NexusAuthPlugin. It handles token extraction from multiple sources, verification with multiple algorithms, and provides a standardized user context.

**Evidence from Production Projects:**

- **example-app**: `utils/jwt.py` (143 lines), `utils/azure_jwt.py` (301 lines), `utils/apple_jwt.py` (276 lines)
- **example-project**: `core/jwt_handler.py` (348 lines)
- **enterprise-app**: `middleware/auth.py` (180 lines)

---

## File Location

`/apps/kailash-nexus/src/nexus/auth/jwt.py`

---

## Token Extraction

### Extraction Priority Order

Tokens are extracted in the following order (first found wins):

1. **Authorization Header** (Bearer token) - Standard API authentication
2. **Cookie** - Browser-based authentication
3. **Query Parameter** - WebSocket connections, download links

### Implementation

```python
"""JWT Middleware for Nexus Authentication.

Provides:
    - Multi-source token extraction (header, cookie, query param)
    - Multi-algorithm verification (HS256, RS256, ES256, etc.)
    - JWK/JWKS support for SSO providers
    - Standardized user context

Evidence:
    - example-app: utils/jwt.py (143 lines), utils/azure_jwt.py (301 lines)
    - example-project: core/jwt_handler.py (348 lines)
    - enterprise-app: middleware/auth.py (180 lines)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union

import jwt
from jwt import PyJWKClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from nexus.auth.exceptions import (
    AuthenticationError,
    ExpiredTokenError,
    InvalidTokenError,
)
from nexus.auth.models import AuthenticatedUser

logger = logging.getLogger(__name__)


@dataclass
class JWTConfig:
    """JWT middleware configuration.

    Attributes:
        secret: Secret key for HS* algorithms
        algorithm: JWT algorithm (HS256, RS256, ES256, etc.)
        public_key: Public key for RS*/ES* algorithms
        private_key: Private key for token signing (optional)
        issuer: Expected token issuer (optional)
        audience: Expected token audience (optional)
        token_header: Header name for Bearer token (default: Authorization)
        token_cookie: Cookie name for token (optional)
        token_query_param: Query parameter for token (optional)
        exempt_paths: Paths exempt from authentication
        jwks_url: URL for JWKS endpoint (for SSO providers)
        jwks_cache_ttl: JWKS cache TTL in seconds (default: 3600)
        verify_exp: Verify token expiration (default: True)
        leeway: Leeway in seconds for exp/nbf claims (default: 0)
    """
    secret: Optional[str] = None
    algorithm: str = "HS256"
    public_key: Optional[str] = None
    private_key: Optional[str] = None
    issuer: Optional[str] = None
    audience: Optional[Union[str, List[str]]] = None
    token_header: str = "Authorization"
    token_cookie: Optional[str] = None
    token_query_param: Optional[str] = None
    exempt_paths: List[str] = field(default_factory=lambda: [
        "/health", "/metrics", "/docs", "/openapi.json", "/redoc",
        "/auth/login", "/auth/refresh", "/auth/sso/*"
    ])
    jwks_url: Optional[str] = None
    jwks_cache_ttl: int = 3600
    verify_exp: bool = True
    leeway: int = 0


class JWTMiddleware(BaseHTTPMiddleware):
    """JWT authentication middleware.

    Extracts JWT tokens from requests, verifies them, and populates
    request.state.user with an AuthenticatedUser instance.

    Usage:
        >>> from nexus.auth.jwt import JWTMiddleware, JWTConfig
        >>>
        >>> config = JWTConfig(
        ...     secret="your-secret-key",
        ...     algorithm="HS256",
        ...     exempt_paths=["/health", "/public/*"],
        ... )
        >>> app.add_middleware(JWTMiddleware, config=config)
        >>>
        >>> # In your endpoint:
        >>> @app.get("/protected")
        >>> async def protected(request: Request):
        ...     user = request.state.user  # AuthenticatedUser
        ...     return {"user_id": user.user_id}

    Evidence:
        Consolidates patterns from:
        - example-app/utils/jwt.py: Bearer token extraction
        - example-app/utils/azure_jwt.py: JWKS verification, audience validation
        - example-project/core/jwt_handler.py: Token creation and verification
        - enterprise-app/middleware/auth.py: Request middleware pattern
    """

    def __init__(
        self,
        app: Any,
        config: Optional[JWTConfig] = None,
        # Direct parameters (override config)
        secret: Optional[str] = None,
        algorithm: Optional[str] = None,
        public_key: Optional[str] = None,
        private_key: Optional[str] = None,
        issuer: Optional[str] = None,
        audience: Optional[Union[str, List[str]]] = None,
        token_header: Optional[str] = None,
        token_cookie: Optional[str] = None,
        token_query_param: Optional[str] = None,
        exempt_paths: Optional[List[str]] = None,
    ):
        """Initialize JWT middleware.

        Args:
            app: ASGI application
            config: JWTConfig instance (preferred)
            secret: Override config.secret
            algorithm: Override config.algorithm
            public_key: Override config.public_key
            private_key: Override config.private_key
            issuer: Override config.issuer
            audience: Override config.audience
            token_header: Override config.token_header
            token_cookie: Override config.token_cookie
            token_query_param: Override config.token_query_param
            exempt_paths: Override config.exempt_paths
        """
        super().__init__(app)

        # Start with config or defaults
        self.config = config or JWTConfig()

        # Override with direct parameters if provided
        if secret is not None:
            self.config.secret = secret
        if algorithm is not None:
            self.config.algorithm = algorithm
        if public_key is not None:
            self.config.public_key = public_key
        if private_key is not None:
            self.config.private_key = private_key
        if issuer is not None:
            self.config.issuer = issuer
        if audience is not None:
            self.config.audience = audience
        if token_header is not None:
            self.config.token_header = token_header
        if token_cookie is not None:
            self.config.token_cookie = token_cookie
        if token_query_param is not None:
            self.config.token_query_param = token_query_param
        if exempt_paths is not None:
            self.config.exempt_paths = exempt_paths

        # Validate configuration
        self._validate_config()

        # Initialize JWKS client if URL provided
        self._jwks_client: Optional[PyJWKClient] = None
        if self.config.jwks_url:
            self._jwks_client = PyJWKClient(
                self.config.jwks_url,
                cache_keys=True,
                lifespan=self.config.jwks_cache_ttl,
            )

        logger.info(f"JWTMiddleware initialized with algorithm={self.config.algorithm}")

    def _validate_config(self) -> None:
        """Validate JWT configuration."""
        symmetric = {"HS256", "HS384", "HS512"}
        asymmetric = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}

        if self.config.algorithm in symmetric:
            if not self.config.secret:
                raise ValueError(f"{self.config.algorithm} requires secret key")
        elif self.config.algorithm in asymmetric:
            if not self.config.public_key and not self.config.jwks_url:
                raise ValueError(
                    f"{self.config.algorithm} requires public_key or jwks_url"
                )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        """Process request and verify JWT token.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware or route handler

        Returns:
            Response from downstream or error response
        """
        # Check if path is exempt
        if self._is_path_exempt(request.url.path):
            return await call_next(request)

        # Extract token
        token = self._extract_token(request)
        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated", "error": "missing_token"},
            )

        # Verify token
        try:
            payload = self._verify_token(token)
            user = self._create_user_from_payload(payload)

            # Store user in request state
            request.state.user = user
            request.state.token = token
            request.state.token_payload = payload

            return await call_next(request)

        except ExpiredTokenError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Token has expired", "error": "token_expired"},
            )
        except InvalidTokenError as e:
            return JSONResponse(
                status_code=401,
                content={"detail": str(e), "error": "invalid_token"},
            )
        except Exception as e:
            logger.error(f"JWT verification failed: {e}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication failed", "error": "auth_error"},
            )

    def _is_path_exempt(self, path: str) -> bool:
        """Check if path is exempt from authentication.

        Supports exact matching and wildcard patterns (e.g., /auth/sso/*).

        Args:
            path: Request URL path

        Returns:
            True if path should skip authentication
        """
        for exempt_path in self.config.exempt_paths:
            if exempt_path.endswith("/*"):
                # Wildcard pattern
                prefix = exempt_path[:-1]  # Remove *
                base = exempt_path[:-2]    # Remove /*
                if path == base or path.startswith(prefix):
                    return True
            elif path == exempt_path:
                # Exact match
                return True
        return False

    def _extract_token(self, request: Request) -> Optional[str]:
        """Extract JWT token from request.

        Extraction priority:
        1. Authorization header (Bearer token)
        2. Cookie (if configured)
        3. Query parameter (if configured, for WebSocket)

        Args:
            request: HTTP request

        Returns:
            Token string or None if not found

        Evidence:
            - example-app: utils/jwt.py lines 45-67 (header extraction)
            - example-project: core/jwt_handler.py lines 89-110 (multi-source)
        """
        # 1. Authorization header
        auth_header = request.headers.get(self.config.token_header, "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]  # Remove "Bearer " prefix
        elif auth_header.startswith("bearer "):
            return auth_header[7:]  # Case-insensitive

        # 2. Cookie (for browser-based apps)
        if self.config.token_cookie:
            token = request.cookies.get(self.config.token_cookie)
            if token:
                return token

        # 3. Query parameter (for WebSocket connections)
        if self.config.token_query_param:
            token = request.query_params.get(self.config.token_query_param)
            if token:
                return token

        return None

    def _verify_token(self, token: str) -> Dict[str, Any]:
        """Verify and decode JWT token.

        Supports:
        - HS256/HS384/HS512 (symmetric, using secret)
        - RS256/RS384/RS512 (asymmetric RSA, using public key or JWKS)
        - ES256/ES384/ES512 (asymmetric ECDSA, using public key or JWKS)

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            ExpiredTokenError: Token has expired
            InvalidTokenError: Token is invalid

        Evidence:
            - example-app: utils/azure_jwt.py lines 120-180 (JWKS verification)
            - example-app: utils/apple_jwt.py lines 95-145 (ES256 verification)
            - example-project: core/jwt_handler.py lines 145-190 (HS256 verification)
        """
        try:
            # SECURITY: Prevent algorithm confusion attacks
            # 1. Reject 'none' algorithm explicitly
            # 2. Verify token's header algorithm matches our configured algorithm
            try:
                unverified_header = jwt.get_unverified_header(token)
            except jwt.exceptions.DecodeError as e:
                raise InvalidTokenError(f"Malformed token header: {e}")

            token_alg = unverified_header.get("alg", "").lower()

            # Explicitly reject 'none' algorithm (critical security check)
            if token_alg == "none":
                raise InvalidTokenError(
                    "Algorithm 'none' is not permitted - possible attack attempt"
                )

            # Verify algorithm matches configuration (prevents alg confusion attacks)
            if token_alg != self.config.algorithm.lower():
                raise InvalidTokenError(
                    f"Token algorithm '{unverified_header.get('alg')}' does not match "
                    f"configured algorithm '{self.config.algorithm}'"
                )

            # Determine verification key
            if self._jwks_client:
                # Use JWKS (for SSO providers like Azure AD, Google)
                signing_key = self._jwks_client.get_signing_key_from_jwt(token)
                key = signing_key.key
            elif self.config.algorithm.startswith("HS"):
                # Symmetric key
                key = self.config.secret
            else:
                # Asymmetric public key
                key = self.config.public_key

            # Build verification options
            options = {
                "verify_exp": self.config.verify_exp,
                "verify_iss": self.config.issuer is not None,
                "verify_aud": self.config.audience is not None,
            }

            # Decode and verify
            payload = jwt.decode(
                token,
                key,
                algorithms=[self.config.algorithm],
                issuer=self.config.issuer,
                audience=self.config.audience,
                leeway=self.config.leeway,
                options=options,
            )

            return payload

        except jwt.ExpiredSignatureError:
            raise ExpiredTokenError("Token has expired")
        except jwt.InvalidAudienceError:
            raise InvalidTokenError("Invalid token audience")
        except jwt.InvalidIssuerError:
            raise InvalidTokenError("Invalid token issuer")
        except jwt.InvalidTokenError as e:
            raise InvalidTokenError(f"Invalid token: {e}")

    def _create_user_from_payload(self, payload: Dict[str, Any]) -> AuthenticatedUser:
        """Create AuthenticatedUser from JWT payload.

        Normalizes different JWT claim formats into a standard user object.

        Standard claims mapping:
        - sub -> user_id
        - email -> email
        - roles / role -> roles
        - permissions / scope -> permissions
        - tenant_id / tid -> tenant_id
        - iss -> provider (mapped to provider name)

        Args:
            payload: Decoded JWT payload

        Returns:
            AuthenticatedUser instance

        Evidence:
            - example-app: utils/azure_jwt.py (Azure AD claims mapping)
            - example-app: utils/apple_jwt.py (Apple claims mapping)
            - example-project: core/jwt_handler.py (standard claims)
        """
        # Extract user_id (sub is standard, but some providers use different claims)
        user_id = payload.get("sub") or payload.get("user_id") or payload.get("uid")
        if not user_id:
            raise InvalidTokenError("Token missing user identifier (sub)")

        # Extract email
        email = payload.get("email") or payload.get("preferred_username")

        # Extract roles (handle array or single value)
        roles = payload.get("roles", [])
        if isinstance(roles, str):
            roles = [roles]
        # Also check for 'role' (singular) used by some providers
        role = payload.get("role")
        if role and role not in roles:
            roles.append(role)

        # Extract permissions (handle array or space-separated string)
        permissions = payload.get("permissions", [])
        if isinstance(permissions, str):
            permissions = permissions.split()
        # Also check 'scope' (OAuth2 standard)
        scope = payload.get("scope", "")
        if isinstance(scope, str):
            scope_perms = scope.split()
            permissions = list(set(permissions + scope_perms))

        # Extract tenant_id (multiple possible claims)
        tenant_id = (
            payload.get("tenant_id")
            or payload.get("tid")  # Azure AD
            or payload.get("organization_id")
        )

        # Determine provider from issuer
        issuer = payload.get("iss", "")
        provider = self._determine_provider(issuer)

        return AuthenticatedUser(
            user_id=user_id,
            email=email,
            roles=roles,
            permissions=permissions,
            tenant_id=tenant_id,
            provider=provider,
            raw_claims=payload,
        )

    def _determine_provider(self, issuer: str) -> str:
        """Determine auth provider from JWT issuer.

        Args:
            issuer: JWT issuer claim

        Returns:
            Provider name (local, azure, google, apple, etc.)
        """
        if not issuer:
            return "local"

        issuer_lower = issuer.lower()

        if "login.microsoftonline.com" in issuer_lower:
            return "azure"
        elif "accounts.google.com" in issuer_lower:
            return "google"
        elif "appleid.apple.com" in issuer_lower:
            return "apple"
        elif "github.com" in issuer_lower:
            return "github"
        else:
            return "local"

    # --- Token Creation Methods ---

    def create_access_token(
        self,
        user_id: str,
        email: Optional[str] = None,
        roles: Optional[List[str]] = None,
        permissions: Optional[List[str]] = None,
        tenant_id: Optional[str] = None,
        expires_minutes: int = 30,
        **extra_claims,
    ) -> str:
        """Create a new access token.

        Args:
            user_id: User identifier (becomes 'sub' claim)
            email: User email
            roles: User roles
            permissions: User permissions
            tenant_id: Tenant identifier
            expires_minutes: Token expiration in minutes
            **extra_claims: Additional claims to include

        Returns:
            Encoded JWT token

        Raises:
            ValueError: If private key not available for asymmetric algorithms

        Evidence:
            - example-project: core/jwt_handler.py lines 55-88
        """
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        exp = now + timedelta(minutes=expires_minutes)

        payload = {
            "sub": user_id,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "token_type": "access",
        }

        if email:
            payload["email"] = email
        if roles:
            payload["roles"] = roles
        if permissions:
            payload["permissions"] = permissions
        if tenant_id:
            payload["tenant_id"] = tenant_id
        if self.config.issuer:
            payload["iss"] = self.config.issuer
        if self.config.audience:
            payload["aud"] = self.config.audience

        payload.update(extra_claims)

        # Determine signing key
        if self.config.algorithm.startswith("HS"):
            key = self.config.secret
        else:
            if not self.config.private_key:
                raise ValueError(
                    f"Private key required to sign tokens with {self.config.algorithm}"
                )
            key = self.config.private_key

        return jwt.encode(payload, key, algorithm=self.config.algorithm)

    def create_refresh_token(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        expires_days: int = 7,
    ) -> str:
        """Create a refresh token.

        Args:
            user_id: User identifier
            tenant_id: Tenant identifier
            expires_days: Token expiration in days

        Returns:
            Encoded JWT refresh token
        """
        from datetime import timedelta
        import uuid

        now = datetime.now(timezone.utc)
        exp = now + timedelta(days=expires_days)

        payload = {
            "sub": user_id,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "jti": str(uuid.uuid4()),  # Unique token ID for revocation
            "token_type": "refresh",
        }

        if tenant_id:
            payload["tenant_id"] = tenant_id
        if self.config.issuer:
            payload["iss"] = self.config.issuer

        # Determine signing key
        if self.config.algorithm.startswith("HS"):
            key = self.config.secret
        else:
            if not self.config.private_key:
                raise ValueError("Private key required for refresh token")
            key = self.config.private_key

        return jwt.encode(payload, key, algorithm=self.config.algorithm)


# --- Standalone Functions ---

def create_access_token(
    plugin: Any,  # NexusAuthPlugin
    user_id: str,
    email: Optional[str] = None,
    roles: Optional[List[str]] = None,
    permissions: Optional[List[str]] = None,
    tenant_id: Optional[str] = None,
    expires_minutes: Optional[int] = None,
    **extra_claims,
) -> str:
    """Create access token using plugin configuration.

    Convenience function for creating tokens outside of middleware.

    Args:
        plugin: NexusAuthPlugin instance
        user_id: User identifier
        email: User email
        roles: User roles
        permissions: User permissions
        tenant_id: Tenant identifier
        expires_minutes: Override default expiration
        **extra_claims: Additional claims

    Returns:
        Encoded JWT token
    """
    if not hasattr(plugin, "_jwt_middleware") or not plugin._jwt_middleware:
        raise RuntimeError("JWT middleware not initialized")

    return plugin._jwt_middleware.create_access_token(
        user_id=user_id,
        email=email,
        roles=roles,
        permissions=permissions,
        tenant_id=tenant_id,
        expires_minutes=expires_minutes or plugin.access_token_expire_minutes,
        **extra_claims,
    )


async def refresh_access_token(
    refresh_token: str,
    plugin: Any,  # NexusAuthPlugin
) -> Dict[str, Any]:
    """Refresh an access token using a refresh token.

    Args:
        refresh_token: Valid refresh token
        plugin: NexusAuthPlugin instance

    Returns:
        Dict with access_token, refresh_token, token_type, expires_in

    Raises:
        InvalidTokenError: If refresh token is invalid
        ExpiredTokenError: If refresh token has expired
    """
    if not hasattr(plugin, "_jwt_middleware") or not plugin._jwt_middleware:
        raise RuntimeError("JWT middleware not initialized")

    middleware = plugin._jwt_middleware

    # Verify refresh token
    try:
        payload = middleware._verify_token(refresh_token)
    except ExpiredTokenError:
        raise ExpiredTokenError("Refresh token has expired")
    except InvalidTokenError:
        raise InvalidTokenError("Invalid refresh token")

    # Ensure it's a refresh token
    if payload.get("token_type") != "refresh":
        raise InvalidTokenError("Not a refresh token")

    # Create new token pair
    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")

    # TODO: Fetch user roles/permissions from database
    # For now, preserve from refresh token if present
    roles = payload.get("roles", [])
    permissions = payload.get("permissions", [])
    email = payload.get("email")

    new_access_token = middleware.create_access_token(
        user_id=user_id,
        email=email,
        roles=roles,
        permissions=permissions,
        tenant_id=tenant_id,
        expires_minutes=plugin.access_token_expire_minutes,
    )

    new_refresh_token = middleware.create_refresh_token(
        user_id=user_id,
        tenant_id=tenant_id,
        expires_days=plugin.refresh_token_expire_days,
    )

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": plugin.access_token_expire_minutes * 60,
    }


def parse_jwt_claims(payload: Dict[str, Any]) -> AuthenticatedUser:
    """Parse JWT claims into AuthenticatedUser.

    Standalone function for parsing JWT payloads.

    Args:
        payload: Decoded JWT payload

    Returns:
        AuthenticatedUser instance
    """
    user_id = payload.get("sub") or payload.get("user_id")
    if not user_id:
        raise InvalidTokenError("Token missing user identifier")

    email = payload.get("email")
    roles = payload.get("roles", [])
    if isinstance(roles, str):
        roles = [roles]

    permissions = payload.get("permissions", [])
    if isinstance(permissions, str):
        permissions = permissions.split()

    tenant_id = payload.get("tenant_id") or payload.get("tid")

    return AuthenticatedUser(
        user_id=user_id,
        email=email,
        roles=roles,
        permissions=permissions,
        tenant_id=tenant_id,
        provider="local",
        raw_claims=payload,
    )
```

---

## Token Verification Matrix

### Supported Algorithms

| Algorithm | Type      | Key Required     | Use Case                    |
| --------- | --------- | ---------------- | --------------------------- |
| HS256     | Symmetric | `jwt_secret`     | Simple apps, single service |
| HS384     | Symmetric | `jwt_secret`     | Higher security symmetric   |
| HS512     | Symmetric | `jwt_secret`     | Highest symmetric security  |
| RS256     | RSA       | `jwt_public_key` | Multi-service, SSO          |
| RS384     | RSA       | `jwt_public_key` | Higher security RSA         |
| RS512     | RSA       | `jwt_public_key` | Highest RSA security        |
| ES256     | ECDSA     | `jwt_public_key` | Apple Sign-In, compact      |
| ES384     | ECDSA     | `jwt_public_key` | Higher security ECDSA       |
| ES512     | ECDSA     | `jwt_public_key` | Highest ECDSA security      |

### JWKS Support

For SSO providers (Azure AD, Google, Apple), tokens are verified using JWKS (JSON Web Key Set):

```python
# Azure AD JWKS URL
jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"

# Google JWKS URL
jwks_url = "https://www.googleapis.com/oauth2/v3/certs"

# Apple JWKS URL
jwks_url = "https://appleid.apple.com/auth/keys"

# Usage with JWTMiddleware
config = JWTConfig(
    algorithm="RS256",
    jwks_url=jwks_url,
    jwks_cache_ttl=3600,  # Cache keys for 1 hour
    issuer="https://login.microsoftonline.com/{tenant_id}/v2.0",
    audience=client_id,
)
```

---

## AuthenticatedUser Model

### Location

`/apps/kailash-nexus/src/nexus/auth/models.py`

### Implementation

```python
"""Authentication models for Nexus.

Provides standardized user representation across different auth providers.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AuthenticatedUser:
    """Standardized authenticated user.

    After JWT verification, the payload is normalized into this structure
    regardless of the authentication provider (local, Azure, Google, Apple).

    Attributes:
        user_id: Unique user identifier (from 'sub' claim)
        email: User email address (if available)
        roles: List of user roles
        permissions: List of specific permissions
        tenant_id: Multi-tenant identifier (if applicable)
        provider: Auth provider (local, azure, google, apple)
        raw_claims: Original JWT payload for provider-specific claims

    Usage:
        >>> # In endpoint after JWTMiddleware
        >>> @app.get("/profile")
        >>> async def get_profile(request: Request):
        ...     user: AuthenticatedUser = request.state.user
        ...     return {
        ...         "id": user.user_id,
        ...         "email": user.email,
        ...         "roles": user.roles,
        ...     }

    Evidence:
        Consolidates user models from:
        - enterprise-app: middleware/auth.py CurrentUser
        - example-project: core/models.py AuthenticatedUser
        - example-app: models/user.py UserContext
    """
    user_id: str
    email: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    tenant_id: Optional[str] = None
    provider: str = "local"  # local, azure, google, apple, github
    raw_claims: Dict[str, Any] = field(default_factory=dict)

    def has_role(self, role: str) -> bool:
        """Check if user has a specific role.

        Args:
            role: Role name to check

        Returns:
            True if user has the role
        """
        return role in self.roles

    def has_any_role(self, *roles: str) -> bool:
        """Check if user has any of the specified roles.

        Args:
            *roles: Role names to check

        Returns:
            True if user has at least one of the roles
        """
        return bool(set(roles) & set(self.roles))

    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission.

        Supports wildcard matching:
        - "read:*" matches "read:users", "read:articles", etc.
        - "*" matches everything

        Args:
            permission: Permission to check (e.g., "read:users")

        Returns:
            True if user has the permission
        """
        # Check for super admin
        if "*" in self.permissions:
            return True

        # Exact match
        if permission in self.permissions:
            return True

        # Wildcard match
        action, _, resource = permission.partition(":")
        if resource:
            # Check for action wildcard (e.g., "read:*")
            if f"{action}:*" in self.permissions:
                return True

        return False

    def has_any_permission(self, *permissions: str) -> bool:
        """Check if user has any of the specified permissions.

        Args:
            *permissions: Permissions to check

        Returns:
            True if user has at least one permission
        """
        return any(self.has_permission(p) for p in permissions)

    def get_claim(self, claim: str, default: Any = None) -> Any:
        """Get a claim from the original JWT payload.

        Args:
            claim: Claim name
            default: Default value if claim not found

        Returns:
            Claim value or default
        """
        return self.raw_claims.get(claim, default)

    @property
    def is_admin(self) -> bool:
        """Check if user has admin role."""
        return self.has_any_role("admin", "super_admin", "administrator")

    @property
    def display_name(self) -> str:
        """Get display name for user."""
        # Try various claims
        return (
            self.raw_claims.get("name")
            or self.raw_claims.get("preferred_username")
            or self.email
            or self.user_id
        )
```

---

## FastAPI Dependencies

### Location

`/apps/kailash-nexus/src/nexus/auth/dependencies.py`

### Implementation

```python
"""FastAPI dependencies for authentication.

Provides dependency functions for endpoint-level authentication checks.
"""

from typing import List, Optional

from fastapi import Depends, HTTPException, Request

from nexus.auth.exceptions import (
    AuthenticationError,
    InsufficientPermissionError,
    InsufficientRoleError,
)
from nexus.auth.models import AuthenticatedUser


def get_current_user(request: Request) -> AuthenticatedUser:
    """Get the current authenticated user.

    Must be used after JWTMiddleware has processed the request.

    Args:
        request: FastAPI request

    Returns:
        AuthenticatedUser from request state

    Raises:
        HTTPException: 401 if user not authenticated

    Usage:
        >>> @app.get("/profile")
        >>> async def get_profile(user: AuthenticatedUser = Depends(get_current_user)):
        ...     return {"user_id": user.user_id}
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_user(request: Request) -> Optional[AuthenticatedUser]:
    """Get the current user if authenticated, None otherwise.

    Useful for endpoints that work for both authenticated and anonymous users.

    Args:
        request: FastAPI request

    Returns:
        AuthenticatedUser or None

    Usage:
        >>> @app.get("/content")
        >>> async def get_content(user: Optional[AuthenticatedUser] = Depends(get_optional_user)):
        ...     if user:
        ...         return {"content": "premium", "user": user.user_id}
        ...     return {"content": "free"}
    """
    return getattr(request.state, "user", None)


def require_auth(request: Request) -> AuthenticatedUser:
    """Require authentication (alias for get_current_user).

    Args:
        request: FastAPI request

    Returns:
        AuthenticatedUser

    Raises:
        HTTPException: 401 if not authenticated

    Usage:
        >>> @app.post("/action")
        >>> async def do_action(user: AuthenticatedUser = Depends(require_auth)):
        ...     # User is guaranteed to be authenticated
        ...     ...
    """
    return get_current_user(request)


class RequireRole:
    """Dependency that requires specific roles.

    Usage:
        >>> @app.get("/admin")
        >>> async def admin_endpoint(
        ...     user: AuthenticatedUser = Depends(RequireRole("admin", "super_admin"))
        ... ):
        ...     return {"admin": True}
    """

    def __init__(self, *roles: str):
        """Initialize with required roles.

        Args:
            *roles: One or more roles (user must have at least one)
        """
        self.roles = roles

    def __call__(self, request: Request) -> AuthenticatedUser:
        """Check roles and return user.

        Args:
            request: FastAPI request

        Returns:
            AuthenticatedUser if role check passes

        Raises:
            HTTPException: 401 if not authenticated, 403 if insufficient role
        """
        user = get_current_user(request)

        if not user.has_any_role(*self.roles):
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of roles: {', '.join(self.roles)}",
            )

        return user


class RequirePermission:
    """Dependency that requires specific permissions.

    Usage:
        >>> @app.post("/articles")
        >>> async def create_article(
        ...     user: AuthenticatedUser = Depends(RequirePermission("write:articles"))
        ... ):
        ...     return {"created": True}
    """

    def __init__(self, *permissions: str):
        """Initialize with required permissions.

        Args:
            *permissions: One or more permissions (user must have at least one)
        """
        self.permissions = permissions

    def __call__(self, request: Request) -> AuthenticatedUser:
        """Check permissions and return user.

        Args:
            request: FastAPI request

        Returns:
            AuthenticatedUser if permission check passes

        Raises:
            HTTPException: 401 if not authenticated, 403 if insufficient permission
        """
        user = get_current_user(request)

        if not user.has_any_permission(*self.permissions):
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of permissions: {', '.join(self.permissions)}",
            )

        return user


# Convenience functions that return dependencies

def require_role(*roles: str) -> RequireRole:
    """Create a role requirement dependency.

    Args:
        *roles: Required roles (user must have at least one)

    Returns:
        RequireRole dependency

    Usage:
        >>> @app.get("/admin")
        >>> async def admin_only(user = Depends(require_role("admin"))):
        ...     ...
    """
    return RequireRole(*roles)


def require_permission(*permissions: str) -> RequirePermission:
    """Create a permission requirement dependency.

    Args:
        *permissions: Required permissions (user must have at least one)

    Returns:
        RequirePermission dependency

    Usage:
        >>> @app.delete("/users/{user_id}")
        >>> async def delete_user(user = Depends(require_permission("delete:users"))):
        ...     ...
    """
    return RequirePermission(*permissions)
```

---

## Path Exemption Patterns

### Supported Patterns

| Pattern     | Matches                                            | Does Not Match             |
| ----------- | -------------------------------------------------- | -------------------------- |
| `/health`   | `/health`                                          | `/health/`, `/healthy`     |
| `/auth/*`   | `/auth/login`, `/auth/refresh`, `/auth/sso/google` | `/auth`, `/authentication` |
| `/api/v1/*` | `/api/v1/users`, `/api/v1/articles/123`            | `/api/v2/users`            |
| `/public`   | `/public`                                          | `/public/files`            |

### Default Exempt Paths

```python
exempt_paths = [
    "/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/auth/login",
    "/auth/refresh",
    "/auth/sso/*",
]
```

---

## Error Responses

### 401 Unauthorized

```json
{
  "detail": "Not authenticated",
  "error": "missing_token"
}
```

```json
{
  "detail": "Token has expired",
  "error": "token_expired"
}
```

```json
{
  "detail": "Invalid token: Signature verification failed",
  "error": "invalid_token"
}
```

### 403 Forbidden

```json
{
  "detail": "Requires one of roles: admin, super_admin",
  "error": "insufficient_role"
}
```

```json
{
  "detail": "Requires permission: delete:users",
  "error": "insufficient_permission"
}
```

---

## Testing

### Unit Test Examples

```python
# tests/unit/auth/test_jwt_extraction.py
"""Unit tests for JWT token extraction."""

import pytest
from starlette.testclient import TestClient
from nexus.auth.jwt import JWTMiddleware, JWTConfig


def test_extract_bearer_token():
    """Test extraction from Authorization header."""
    from unittest.mock import MagicMock

    request = MagicMock()
    request.headers = {"Authorization": "Bearer test-token-123"}
    request.cookies = {}
    request.query_params = {}

    config = JWTConfig(secret="test-secret")
    middleware = JWTMiddleware.__new__(JWTMiddleware)
    middleware.config = config

    token = middleware._extract_token(request)
    assert token == "test-token-123"


def test_extract_from_cookie():
    """Test extraction from cookie."""
    from unittest.mock import MagicMock

    request = MagicMock()
    request.headers = {}
    request.cookies = {"auth_token": "cookie-token-456"}
    request.query_params = {}

    config = JWTConfig(secret="test-secret", token_cookie="auth_token")
    middleware = JWTMiddleware.__new__(JWTMiddleware)
    middleware.config = config

    token = middleware._extract_token(request)
    assert token == "cookie-token-456"


def test_path_exemption_exact_match():
    """Test exact path exemption."""
    config = JWTConfig(secret="test", exempt_paths=["/health"])
    middleware = JWTMiddleware.__new__(JWTMiddleware)
    middleware.config = config

    assert middleware._is_path_exempt("/health") is True
    assert middleware._is_path_exempt("/healthy") is False


def test_path_exemption_wildcard():
    """Test wildcard path exemption."""
    config = JWTConfig(secret="test", exempt_paths=["/auth/*"])
    middleware = JWTMiddleware.__new__(JWTMiddleware)
    middleware.config = config

    assert middleware._is_path_exempt("/auth/login") is True
    assert middleware._is_path_exempt("/auth/sso/google") is True
    assert middleware._is_path_exempt("/authentication") is False
```

### Integration Test Examples

```python
# tests/integration/auth/test_jwt_verification.py
"""Integration tests for JWT verification."""

import pytest
import jwt
from datetime import datetime, timedelta, timezone


@pytest.fixture
def jwt_secret():
    return "test-secret-key-at-least-32-characters"


def test_hs256_token_verification(jwt_secret):
    """Test HS256 token creation and verification."""
    from nexus.auth.jwt import JWTMiddleware, JWTConfig

    config = JWTConfig(secret=jwt_secret, algorithm="HS256")
    middleware = JWTMiddleware.__new__(JWTMiddleware)
    middleware.config = config
    middleware._jwks_client = None

    # Create token
    token = middleware.create_access_token(
        user_id="user-123",
        email="user@example.com",
        roles=["admin"],
    )

    # Verify token
    payload = middleware._verify_token(token)
    assert payload["sub"] == "user-123"
    assert payload["email"] == "user@example.com"
    assert payload["roles"] == ["admin"]


def test_expired_token_rejected(jwt_secret):
    """Test that expired tokens are rejected."""
    from nexus.auth.jwt import JWTMiddleware, JWTConfig
    from nexus.auth.exceptions import ExpiredTokenError

    config = JWTConfig(secret=jwt_secret, algorithm="HS256")
    middleware = JWTMiddleware.__new__(JWTMiddleware)
    middleware.config = config
    middleware._jwks_client = None

    # Create expired token
    payload = {
        "sub": "user-123",
        "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
    }
    token = jwt.encode(payload, jwt_secret, algorithm="HS256")

    with pytest.raises(ExpiredTokenError):
        middleware._verify_token(token)
```
