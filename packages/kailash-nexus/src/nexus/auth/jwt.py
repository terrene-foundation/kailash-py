"""JWT Middleware for Nexus Authentication.

Provides:
    - Multi-source token extraction (header, cookie, query param)
    - Multi-algorithm verification (HS256, RS256, ES256, etc.)
    - JWK/JWKS support for SSO providers
    - Standardized user context via AuthenticatedUser
    - Token creation (access + refresh)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Union

import jwt
from nexus.auth.exceptions import ExpiredTokenError, InvalidTokenError
from nexus.auth.models import AuthenticatedUser
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# Supported algorithm sets
_SYMMETRIC_ALGORITHMS = {"HS256", "HS384", "HS512"}
_ASYMMETRIC_ALGORITHMS = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}


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
    exempt_paths: List[str] = field(
        default_factory=lambda: [
            "/health",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/auth/login",
            "/auth/refresh",
            "/auth/sso/*",
        ]
    )
    jwks_url: Optional[str] = None
    jwks_cache_ttl: int = 3600
    verify_exp: bool = True
    leeway: int = 0

    # GH #226: API key authentication
    api_key_header: str = "X-API-Key"
    api_key_enabled: bool = False
    api_key_validator: Optional[Callable[[str], Any]] = None

    # GH #226: Absolute token age check (independent of exp claim)
    max_token_age_seconds: Optional[int] = None

    # GH #226: Post-validation hook for stale detection / audit
    on_token_validated: Optional[Callable[[Dict[str, Any]], Any]] = None

    # Minimum secret length for symmetric algorithms (NIST SP 800-117 recommends
    # key length >= hash output size: 256 bits = 32 bytes for HS256)
    MIN_SECRET_LENGTH: int = 32

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.algorithm in _SYMMETRIC_ALGORITHMS:
            if not self.secret:
                raise ValueError(f"{self.algorithm} requires secret key")
            if len(self.secret) < self.MIN_SECRET_LENGTH:
                raise ValueError(
                    f"JWT secret must be at least {self.MIN_SECRET_LENGTH} characters "
                    f"for {self.algorithm} (got {len(self.secret)}). "
                    f"Short secrets are vulnerable to brute-force attacks."
                )
        elif self.algorithm in _ASYMMETRIC_ALGORITHMS:
            if not self.public_key and not self.jwks_url:
                raise ValueError(f"{self.algorithm} requires public_key or jwks_url")


class JWTMiddleware(BaseHTTPMiddleware):
    """JWT authentication middleware.

    Extracts JWT tokens from requests, verifies them, and populates
    request.state.user with an AuthenticatedUser instance.

    Usage:
        config = JWTConfig(
            secret="your-secret-key",
            algorithm="HS256",
            exempt_paths=["/health", "/public/*"],
        )
        app.add_middleware(JWTMiddleware, config=config)
    """

    def __init__(
        self,
        app: Any,
        config: Optional[JWTConfig] = None,
        *,
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
        jwks_url: Optional[str] = None,
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
            jwks_url: Override config.jwks_url
        """
        super().__init__(app)

        # Start with config or build from parameters
        if config:
            self.config = config
        else:
            # Build config from individual parameters
            kwargs: Dict[str, Any] = {}
            if secret is not None:
                kwargs["secret"] = secret
            if algorithm is not None:
                kwargs["algorithm"] = algorithm
            if public_key is not None:
                kwargs["public_key"] = public_key
            if private_key is not None:
                kwargs["private_key"] = private_key
            if issuer is not None:
                kwargs["issuer"] = issuer
            if audience is not None:
                kwargs["audience"] = audience
            if token_header is not None:
                kwargs["token_header"] = token_header
            if token_cookie is not None:
                kwargs["token_cookie"] = token_cookie
            if token_query_param is not None:
                kwargs["token_query_param"] = token_query_param
            if exempt_paths is not None:
                kwargs["exempt_paths"] = exempt_paths
            if jwks_url is not None:
                kwargs["jwks_url"] = jwks_url
            self.config = JWTConfig(**kwargs)

        # Initialize JWKS client if URL provided
        self._jwks_client = None
        if self.config.jwks_url:
            try:
                from jwt import PyJWKClient

                self._jwks_client = PyJWKClient(
                    self.config.jwks_url,
                    cache_keys=True,
                    lifespan=self.config.jwks_cache_ttl,
                )
            except ImportError:
                logger.warning(
                    "PyJWKClient not available. Install pyjwt[crypto] for JWKS support."
                )

        logger.info(f"JWTMiddleware initialized with algorithm={self.config.algorithm}")

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        """Process request and verify JWT token."""
        # Check if path is exempt
        if self._is_path_exempt(request.url.path):
            return await call_next(request)

        # Extract token
        token = self._extract_token(request)
        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated", "error": "missing_token"},
                headers={"WWW-Authenticate": 'Bearer realm="api"'},
            )

        # GH #226: Handle API key authentication
        if token.startswith("__apikey__") and self.config.api_key_enabled:
            api_key = token[len("__apikey__") :]
            if self.config.api_key_validator:
                try:
                    import asyncio
                    import inspect

                    result = self.config.api_key_validator(api_key)
                    if inspect.isawaitable(result):
                        result = await result
                    if not result:
                        return JSONResponse(
                            status_code=401,
                            content={
                                "detail": "Invalid API key",
                                "error": "invalid_api_key",
                            },
                        )
                    # api_key_validator can return a user dict or True
                    if isinstance(result, dict):
                        user = self._create_user_from_payload(result)
                    else:
                        user = AuthenticatedUser(user_id="apikey", roles=["api"])
                    request.state.user = user
                    request.state.token = api_key
                    request.state.token_payload = {"type": "api_key"}
                    return await call_next(request)
                except Exception as e:
                    logger.warning("API key validation failed: %s", e)
                    return JSONResponse(
                        status_code=401,
                        content={
                            "detail": "API key validation error",
                            "error": "api_key_error",
                        },
                    )
            else:
                return JSONResponse(
                    status_code=500,
                    content={
                        "detail": "API key auth enabled but no validator configured"
                    },
                )

        # Verify JWT token
        try:
            payload = self._verify_token(token)

            # GH #226: Absolute token age check (kailash-rs#145)
            if self.config.max_token_age_seconds is not None:
                iat = payload.get("iat")
                if iat is not None:
                    import math

                    iat_float = float(iat)
                    if not math.isfinite(iat_float):
                        return JSONResponse(
                            status_code=401,
                            content={
                                "detail": "Invalid iat claim",
                                "error": "invalid_token",
                            },
                        )
                    token_age = int(datetime.now(timezone.utc).timestamp()) - int(
                        iat_float
                    )
                    if token_age < 0:
                        return JSONResponse(
                            status_code=401,
                            content={
                                "detail": "Token issued in the future",
                                "error": "invalid_token",
                            },
                        )
                    if token_age > self.config.max_token_age_seconds:
                        return JSONResponse(
                            status_code=401,
                            content={
                                "detail": "Token too old",
                                "error": "token_too_old",
                            },
                        )

            user = self._create_user_from_payload(payload)

            # Store user in request state
            request.state.user = user
            request.state.token = token
            request.state.token_payload = payload

            # GH #226: Post-validation hook (kailash-rs#145)
            if self.config.on_token_validated:
                try:
                    import asyncio
                    import inspect

                    result = self.config.on_token_validated(payload)
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    logger.exception("on_token_validated hook failed")

            return await call_next(request)

        except ExpiredTokenError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Token has expired", "error": "token_expired"},
                headers={
                    "WWW-Authenticate": 'Bearer realm="api", error="invalid_token"'
                },
            )
        except InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token", "error": "invalid_token"},
                headers={
                    "WWW-Authenticate": 'Bearer realm="api", error="invalid_token"'
                },
            )
        except Exception as e:
            logger.error(f"JWT verification failed: {e}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication failed", "error": "auth_error"},
                headers={"WWW-Authenticate": 'Bearer realm="api"'},
            )

    def _is_path_exempt(self, path: str) -> bool:
        """Check if path is exempt from authentication.

        Supports exact matching and wildcard patterns (e.g., /auth/sso/*).
        """
        for exempt_path in self.config.exempt_paths:
            if exempt_path.endswith("/*"):
                # Wildcard pattern
                prefix = exempt_path[:-1]  # Remove *
                base = exempt_path[:-2]  # Remove /*
                if path == base or path.startswith(prefix):
                    return True
            elif path == exempt_path:
                return True
        return False

    def _extract_token(self, request: Request) -> Optional[str]:
        """Extract JWT token or API key from request.

        Extraction priority:
        1. API key header (if api_key_enabled)
        2. Authorization header (Bearer token)
        3. Cookie (if configured)
        4. Query parameter (if configured)
        """
        # 0. API key (GH #226: kailash-rs#144)
        if self.config.api_key_enabled:
            api_key = request.headers.get(self.config.api_key_header, "")
            if api_key:
                # Store API key marker — dispatch() will handle validation
                request.state._fabric_api_key = api_key
                return f"__apikey__{api_key}"

        # 1. Authorization header
        auth_header = request.headers.get(self.config.token_header, "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        elif auth_header.startswith("bearer "):
            return auth_header[7:]

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

        Includes algorithm confusion attack prevention.

        Raises:
            ExpiredTokenError: Token has expired
            InvalidTokenError: Token is invalid
        """
        try:
            # SECURITY: Prevent algorithm confusion attacks
            try:
                unverified_header = jwt.get_unverified_header(token)
            except jwt.exceptions.DecodeError as e:
                logger.debug("Malformed token header: %s", e)
                raise InvalidTokenError("Malformed token")

            token_alg = unverified_header.get("alg", "").lower()

            # Explicitly reject 'none' algorithm
            if token_alg == "none":
                raise InvalidTokenError(
                    "Algorithm 'none' is not permitted - possible attack attempt"
                )

            # Verify algorithm matches configuration
            if token_alg != self.config.algorithm.lower():
                # SECURITY: Don't reveal configured algorithm to potential attacker
                logger.warning(
                    "Algorithm mismatch: token=%s, configured=%s",
                    unverified_header.get("alg"),
                    self.config.algorithm,
                )
                raise InvalidTokenError("Token algorithm mismatch")

            # Determine verification key
            if self._jwks_client:
                signing_key = self._jwks_client.get_signing_key_from_jwt(token)
                key = signing_key.key
            elif self.config.algorithm in _SYMMETRIC_ALGORITHMS:
                key = self.config.secret
            else:
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

            # SECURITY: Reject refresh tokens used as access tokens
            token_type = payload.get("token_type")
            if token_type == "refresh":
                raise InvalidTokenError(
                    "Refresh tokens cannot be used for API authentication"
                )

            return payload

        except ExpiredTokenError:
            raise
        except InvalidTokenError:
            raise
        except jwt.ExpiredSignatureError:
            raise ExpiredTokenError("Token has expired")
        except jwt.InvalidAudienceError:
            raise InvalidTokenError("Invalid token audience")
        except jwt.InvalidIssuerError:
            raise InvalidTokenError("Invalid token issuer")
        except jwt.InvalidTokenError as e:
            logger.debug("JWT decode error: %s", e)
            raise InvalidTokenError("Invalid token")

    def _create_user_from_payload(self, payload: Dict[str, Any]) -> AuthenticatedUser:
        """Create AuthenticatedUser from JWT payload.

        Normalizes different JWT claim formats into a standard user object.
        """
        # Extract user_id
        user_id = payload.get("sub") or payload.get("user_id") or payload.get("uid")
        if not user_id:
            raise InvalidTokenError("Token missing user identifier (sub)")

        # Extract email
        email = payload.get("email") or payload.get("preferred_username")

        # Extract roles
        roles = payload.get("roles", [])
        if isinstance(roles, str):
            roles = [roles]
        role = payload.get("role")
        if role and role not in roles:
            roles.append(role)

        # Extract permissions
        permissions = payload.get("permissions", [])
        if isinstance(permissions, str):
            permissions = permissions.split()
        scope = payload.get("scope", "")
        if isinstance(scope, str) and scope:
            scope_perms = scope.split()
            permissions = list(set(permissions + scope_perms))

        # Extract tenant_id
        tenant_id = (
            payload.get("tenant_id")
            or payload.get("tid")
            or payload.get("organization_id")
        )

        # Determine provider
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
        """Determine auth provider from JWT issuer."""
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
        **extra_claims: Any,
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
        """
        now = datetime.now(timezone.utc)
        exp = now + timedelta(minutes=expires_minutes)

        payload: Dict[str, Any] = {
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

        # SECURITY: Prevent extra_claims from overriding security-critical claims
        _reserved = {
            "sub",
            "iat",
            "exp",
            "iss",
            "aud",
            "token_type",
            "roles",
            "permissions",
            "tenant_id",
        }
        unsafe_overrides = set(extra_claims.keys()) & _reserved
        if unsafe_overrides:
            logger.warning(
                "Ignoring reserved claims in extra_claims: %s",
                unsafe_overrides,
            )
            extra_claims = {k: v for k, v in extra_claims.items() if k not in _reserved}
        payload.update(extra_claims)

        # Determine signing key
        if self.config.algorithm in _SYMMETRIC_ALGORITHMS:
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
        now = datetime.now(timezone.utc)
        exp = now + timedelta(days=expires_days)

        payload: Dict[str, Any] = {
            "sub": user_id,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "jti": str(uuid.uuid4()),
            "token_type": "refresh",
        }

        if tenant_id:
            payload["tenant_id"] = tenant_id
        if self.config.issuer:
            payload["iss"] = self.config.issuer

        # Determine signing key
        if self.config.algorithm in _SYMMETRIC_ALGORITHMS:
            key = self.config.secret
        else:
            if not self.config.private_key:
                raise ValueError("Private key required for refresh token")
            key = self.config.private_key

        return jwt.encode(payload, key, algorithm=self.config.algorithm)
