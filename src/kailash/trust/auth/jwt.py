# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""JWT validation and token creation -- framework-agnostic.

Extracted from ``nexus.auth.jwt`` (SPEC-06). Provides stateless JWT validation
and creation that works independently of any HTTP framework.

The ``JWTValidator`` class handles:
    - Multi-algorithm verification (HS256, RS256, ES256, etc.)
    - Algorithm confusion attack prevention
    - JWK/JWKS support for SSO providers
    - Token creation (access + refresh)
    - Normalized user extraction from claims

The Starlette/FastAPI ``JWTMiddleware`` remains in Nexus and delegates
to ``JWTValidator`` for the actual crypto work.
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Union

import jwt

from kailash.trust.auth.exceptions import ExpiredTokenError, InvalidTokenError
from kailash.trust.auth.models import AuthenticatedUser

logger = logging.getLogger(__name__)

# Supported algorithm sets
_SYMMETRIC_ALGORITHMS = {"HS256", "HS384", "HS512"}
_ASYMMETRIC_ALGORITHMS = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}

__all__ = [
    "JWTConfig",
    "JWTValidator",
]


@dataclass
class JWTConfig:
    """JWT validation configuration.

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

    # API key authentication
    api_key_header: str = "X-API-Key"
    api_key_enabled: bool = False
    api_key_validator: Optional[Callable[[str], Any]] = None

    # Absolute token age check (independent of exp claim)
    max_token_age_seconds: Optional[int] = None

    # Post-validation hook for stale detection / audit
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


class JWTValidator:
    """Stateless JWT token verification and creation.

    Framework-agnostic JWT processor that handles token verification,
    user extraction, and token creation. HTTP middleware (e.g., Nexus
    JWTMiddleware) delegates to this class for the actual crypto work.

    Usage:
        >>> config = JWTConfig(secret="your-secret-key-at-least-32-chars!")
        >>> validator = JWTValidator(config)
        >>> payload = validator.verify_token(token_string)
        >>> user = validator.create_user_from_payload(payload)
    """

    def __init__(self, config: JWTConfig):
        """Initialize JWT validator.

        Args:
            config: JWTConfig instance
        """
        self.config = config

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

        logger.info("JWTValidator initialized with algorithm=%s", self.config.algorithm)

    def is_path_exempt(self, path: str) -> bool:
        """Check if path is exempt from authentication.

        Supports exact matching and wildcard patterns (e.g., /auth/sso/*).
        """
        for exempt_path in self.config.exempt_paths:
            if exempt_path.endswith("/*"):
                prefix = exempt_path[:-1]  # Remove *
                base = exempt_path[:-2]  # Remove /*
                if path == base or path.startswith(prefix):
                    return True
            elif path == exempt_path:
                return True
        return False

    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify and decode JWT token.

        Includes algorithm confusion attack prevention.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

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

    def check_token_age(self, payload: Dict[str, Any]) -> Optional[str]:
        """Check absolute token age if max_token_age_seconds is configured.

        Args:
            payload: Decoded JWT payload

        Returns:
            None if OK, error string if token is too old or invalid
        """
        if self.config.max_token_age_seconds is None:
            return None

        iat = payload.get("iat")
        if iat is None:
            return None

        iat_float = float(iat)
        if not math.isfinite(iat_float):
            return "Invalid iat claim"

        token_age = int(datetime.now(timezone.utc).timestamp()) - int(iat_float)
        if token_age < 0:
            return "Token issued in the future"
        if token_age > self.config.max_token_age_seconds:
            return "Token too old"

        return None

    def create_user_from_payload(self, payload: Dict[str, Any]) -> AuthenticatedUser:
        """Create AuthenticatedUser from JWT payload.

        Normalizes different JWT claim formats into a standard user object.

        Args:
            payload: Decoded JWT payload

        Returns:
            AuthenticatedUser instance

        Raises:
            InvalidTokenError: If required claims are missing
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
