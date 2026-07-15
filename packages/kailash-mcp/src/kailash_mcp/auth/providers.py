"""Authentication framework for MCP servers and clients.

This module provides a comprehensive authentication system for Model Context Protocol
implementations, supporting multiple authentication methods and security features.

Features:
- Multiple auth methods: API Key, Bearer Token, Basic Auth, JWT, OAuth2
- Permission-based access control
- Rate limiting per client
- Session management
- Audit logging
- Token validation and refresh
- Custom authentication providers

Examples:
    API Key authentication:

    >>> auth = APIKeyAuth(keys=["secret123", "secret456"])
    >>> client = HTTPMCPClient(auth=auth.get_client_config())
    >>> server = HTTPMCPServer(auth_config=auth.get_server_config())

    JWT authentication:

    >>> auth = JWTAuth(
    ...     secret="my-secret",
    ...     algorithm="HS256",
    ...     audience="https://mcp.example.com",
    ... )
    >>> token = auth.create_token({"user": "alice", "permissions": ["read", "write"]})
"""

import base64
import binascii
import hmac
import inspect
import json
import logging
import os
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Union

try:
    import jwt
    from cryptography.exceptions import InvalidKey
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    _CRYPTO_AVAILABLE = True
except ImportError:
    jwt = None  # type: ignore[assignment]
    InvalidKey = None  # type: ignore[assignment, misc]
    hashes = None  # type: ignore[assignment]
    PBKDF2HMAC = None  # type: ignore[assignment, misc]
    _CRYPTO_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning(
        "JWT dependencies not available. Install with: pip install pyjwt cryptography"
    )

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Base exception for authentication errors."""

    def __init__(self, message: str, error_code: str = "AUTH_FAILED"):
        super().__init__(message)
        self.error_code = error_code


class PermissionError(AuthenticationError):
    """Exception for permission-related errors."""

    def __init__(self, message: str, required_permission: str = ""):
        super().__init__(message, "PERMISSION_DENIED")
        self.required_permission = required_permission


class RateLimitError(AuthenticationError):
    """Exception for rate limiting errors."""

    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message, "RATE_LIMITED")
        self.retry_after = retry_after


class AuthProvider(ABC):
    """Abstract base class for authentication providers."""

    @abstractmethod
    def authenticate(self, credentials: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Authenticate credentials and return user info.

        Args:
            credentials: Authentication credentials (string token or dict)

        Returns:
            Authentication context dict
        """
        pass

    @abstractmethod
    def get_client_config(self) -> Dict[str, Any]:
        """Get client-side authentication configuration."""
        pass

    @abstractmethod
    def get_server_config(self) -> Dict[str, Any]:
        """Get server-side authentication configuration."""
        pass


class APIKeyAuth(AuthProvider):
    """API Key authentication provider.

    Supports multiple API keys with optional permissions and metadata.

    Args:
        keys: List of valid API keys or dict mapping keys to metadata
        header_name: HTTP header name for the API key
        permissions: Default permissions for all keys

    Examples:
        Simple API key auth:

        >>> auth = APIKeyAuth(keys=["secret123", "secret456"])

        API keys with permissions:

        >>> auth = APIKeyAuth(keys={
        ...     "admin_key": {"permissions": ["read", "write", "admin"]},
        ...     "read_key": {"permissions": ["read"]}
        ... })
    """

    def __init__(
        self,
        keys: Union[List[str], Dict[str, Dict[str, Any]]],
        header_name: str = "X-API-Key",
        permissions: Optional[List[str]] = None,
    ):
        """Initialize API key authentication."""
        self.header_name = header_name
        self.default_permissions = permissions or ["read"]

        # Normalize keys to dict format
        if isinstance(keys, list):
            self.keys = {key: {"permissions": self.default_permissions} for key in keys}
        else:
            self.keys = keys

        # Add default permissions to keys that don't have them
        for key_data in self.keys.values():
            if "permissions" not in key_data:
                key_data["permissions"] = self.default_permissions

        logger.info(f"Initialized API Key auth with {len(self.keys)} keys")

    def authenticate(self, credentials: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Authenticate API key credentials.

        Args:
            credentials: Either API key string or dict with 'api_key' field

        Returns:
            Authentication context dict

        Raises:
            AuthenticationError: If credentials are invalid or missing
        """
        # Handle both string and dict inputs for better developer experience
        if isinstance(credentials, str):
            api_key = credentials
        elif isinstance(credentials, dict):
            api_key = credentials.get("api_key")
            if not api_key:
                raise AuthenticationError(
                    "Expected dict with 'api_key' field, got dict without api_key"
                )
        else:
            raise AuthenticationError(
                f"Expected string or dict, got {type(credentials).__name__}"
            )

        if api_key not in self.keys:
            raise AuthenticationError("Invalid API key")

        key_data = self.keys[api_key]
        # Fingerprint (not password hash) used as an opaque user_id for
        # the request. The raw api_key was already verified against
        # ``self.keys`` above; this code path does NOT persist the
        # fingerprint for later credential verification. Routed through
        # the canonical ``fingerprint_secret`` helper (BLAKE2b) so
        # CodeQL's ``py/weak-sensitive-data-hashing`` does not flag this
        # as misused password hashing — see helper docstring for why
        # argon2-cffi / bcrypt would be wrong here.
        from kailash.utils.url_credentials import fingerprint_secret

        return {
            "user_id": f"api_key_{fingerprint_secret(api_key)}",
            "auth_type": "api_key",
            "permissions": key_data.get("permissions", []),
            "metadata": key_data,
        }

    def get_client_config(self) -> Dict[str, Any]:
        """Get client configuration."""
        # Return first key for client (in practice, client would specify which key to use)
        first_key = next(iter(self.keys.keys()))
        return {"type": "api_key", "key": first_key, "header": self.header_name}

    def get_server_config(self) -> Dict[str, Any]:
        """Get server configuration."""
        return {
            "type": "api_key",
            "header": self.header_name,
            "keys": list(self.keys.keys()),
            "key_metadata": self.keys,
        }


class BearerTokenAuth(AuthProvider):
    """Bearer token authentication provider.

    Supports JWT and opaque bearer tokens with validation.

    Args:
        tokens: List of valid tokens or dict mapping tokens to metadata
        validate_jwt: Whether to validate JWT tokens
        jwt_secret: Secret for JWT validation
        jwt_algorithm: Algorithm for JWT validation
        expected_issuer: When set, JWT validation requires the ``iss`` claim
            to be present AND equal to this value. When ``None`` (default),
            absent-iss tokens are accepted (existing behaviour preserved).
        expected_audience: The canonical resource URI this MCP server
            identifies as (a.k.a. the token audience). REQUIRED whenever
            ``validate_jwt=True`` — construction raises ``ValueError`` if it is
            absent (fail-closed, enforcement-surface parity with
            ``ResourceServer``). JWT validation then FAILS CLOSED on the
            audience dimension — it rejects BOTH audience-absent tokens
            (missing required ``aud``) AND foreign-audience tokens (``aud``
            mismatch), per the MCP 2025-11-25 spec. There is no fail-open
            default: the only way to skip audience validation is to not
            validate JWTs (``validate_jwt=False``).

    Examples:
        Simple bearer token:

        >>> auth = BearerTokenAuth(tokens=["bearer_token_123"])

        JWT bearer tokens (spec-compliant, audience fail-closed):

        >>> auth = BearerTokenAuth(
        ...     validate_jwt=True,
        ...     jwt_secret="my-secret",
        ...     jwt_algorithm="HS256",
        ...     expected_audience="https://mcp.example.com",
        ... )
    """

    def __init__(
        self,
        tokens: Optional[Union[List[str], Dict[str, Dict[str, Any]]]] = None,
        validate_jwt: bool = False,
        jwt_secret: Optional[str] = None,
        jwt_algorithm: str = "HS256",
        expected_issuer: Optional[str] = None,
        expected_audience: Optional[str] = None,
    ):
        """Initialize bearer token authentication."""
        self.validate_jwt = validate_jwt
        self.jwt_secret = jwt_secret
        self.jwt_algorithm = jwt_algorithm
        self.expected_issuer = expected_issuer
        self.expected_audience = expected_audience

        # Normalize tokens
        if tokens is None:
            self.tokens = {}
        elif isinstance(tokens, list):
            self.tokens = {token: {} for token in tokens}
        else:
            self.tokens = tokens

        if validate_jwt and not jwt_secret:
            raise ValueError("JWT secret required when validate_jwt=True")

        # Fail-closed audience guard (MCP 2025-11-25) — enforcement-surface
        # parity with ``ResourceServer`` (rules/security.md § Enforcement-Surface
        # Parity). A JWT-validating provider that does NOT pin an expected
        # audience cannot reject a foreign-audience token minted for a different
        # resource, so audience enforcement would silently be fail-OPEN. Rather
        # than warn-and-continue (the pre-fix behaviour that shipped the open
        # default), REFUSE construction — mirroring the ``jwt_secret`` guard
        # above. Every JWT-validating provider is now audience fail-closed by
        # construction; the only way to disable audience validation is to not
        # validate JWTs at all.
        if validate_jwt and not expected_audience:
            raise ValueError(
                "expected_audience is required when validate_jwt=True: the MCP "
                "2025-11-25 spec REQUIRES servers to validate the token audience "
                "fail-closed (reject audience-absent AND foreign-audience "
                "tokens). Pass expected_audience=<canonical resource URI> so a "
                "token minted for a different resource cannot be replayed here."
            )

        logger.info(f"Initialized Bearer Token auth (JWT: {validate_jwt})")

    def authenticate(self, credentials: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Authenticate bearer token credentials.

        Args:
            credentials: Either bearer token string or dict with 'token' field

        Returns:
            Authentication context dict
        """
        # Handle both string and dict inputs
        if isinstance(credentials, str):
            token = credentials
        elif isinstance(credentials, dict):
            token = credentials.get("token")
            if not token:
                raise AuthenticationError(
                    "Expected dict with 'token' field, got dict without token"
                )
        else:
            raise AuthenticationError(
                f"Expected string or dict, got {type(credentials).__name__}"
            )

        if self.validate_jwt:
            return self._validate_jwt_token(token)
        else:
            return self._validate_opaque_token(token)

    def _validate_jwt_token(self, token: str) -> Dict[str, Any]:
        """Validate JWT token.

        When ``expected_issuer`` is configured, this layers PyJWT's
        ``options={"require": ["exp", "iss"]}`` on top of the ``issuer=``
        equality check.

        Cross-SDK port of esperie/kailash-rs#599 (PR #602): jsonwebtoken's
        ``set_issuer`` (Rust) and PyJWT's ``issuer=`` (Python) only enforce
        equality when the ``iss`` claim is present in the token payload. A
        forged token that OMITS ``iss`` entirely passes the allowlist check
        unless ``iss`` is also added to the required-claims set. The require
        list closes that bypass.

        When ``expected_audience`` is configured, audience validation is
        FAIL-CLOSED per the MCP 2025-11-25 spec: ``audience=`` is passed to
        ``jwt.decode`` AND ``"aud"`` is added to the required-claims set, so
        PyJWT rejects BOTH audience-absent tokens (``MissingRequiredClaimError``)
        AND foreign-audience tokens (``InvalidAudienceError``). This is the
        same defence as the ``iss`` bypass above, applied to the ``aud``
        dimension — a token minted for a DIFFERENT resource, or one that omits
        ``aud`` entirely, is rejected. When ``expected_audience`` is ``None``
        the audience dimension is not validated (a WARNING was logged at
        construction).
        """
        if jwt is None:
            raise AuthenticationError("JWT validation not available")

        decode_kwargs: Dict[str, Any] = {
            "algorithms": [self.jwt_algorithm],
        }
        # Build the required-claims set incrementally so each opted-in
        # dimension (issuer / audience) contributes its own required claim.
        required_claims: List[str] = []
        if self.expected_issuer is not None:
            # Layer iss-required + issuer-allowlist when caller opted in.
            decode_kwargs["issuer"] = self.expected_issuer
            required_claims += ["exp", "iss"]
        if self.expected_audience is not None:
            # Layer aud-required + audience-allowlist: rejects audience-absent
            # (missing required `aud`) AND foreign-audience (`aud` mismatch).
            decode_kwargs["audience"] = self.expected_audience
            required_claims.append("aud")
        if required_claims:
            decode_kwargs["options"] = {"require": required_claims}

        try:
            payload = jwt.decode(  # type: ignore[union-attr]
                token,
                self.jwt_secret,
                **decode_kwargs,  # type: ignore[arg-type]
            )

            return {
                "user_id": payload.get("sub", payload.get("user", "unknown")),
                "auth_type": "jwt",
                "permissions": payload.get("permissions", ["read"]),
                "metadata": payload,
            }

        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token expired")
        except jwt.MissingRequiredClaimError as e:
            # PyJWT raises this for absent `iss` (require=[..,"iss"]) or absent
            # `aud` (require=[..,"aud"]). The claim NAME is not a secret, so
            # surface it; the token's actual claim VALUES are never touched.
            raise AuthenticationError(f"Invalid token: {e}")
        except jwt.InvalidAudienceError:
            # Foreign-audience token. Do NOT interpolate the exception — the
            # token's actual `aud` value MUST NOT leak into logs/messages
            # (security.md "no secrets in logs"). Fixed, typed message only.
            raise AuthenticationError("Invalid token audience")
        except jwt.InvalidIssuerError as e:
            raise AuthenticationError(f"Invalid token: {e}")
        except jwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid token: {e}")

    def _validate_opaque_token(self, token: str) -> Dict[str, Any]:
        """Validate opaque bearer token."""
        if token not in self.tokens:
            raise AuthenticationError("Invalid bearer token")

        token_data = self.tokens[token]
        # Fingerprint (not password hash) used as an opaque user_id.
        # The raw token was already verified against ``self.tokens``
        # above. See the api-key path's comment for the same rationale
        # and the ``fingerprint_secret`` docstring for why BLAKE2b is
        # correct here and argon2 would be wrong.
        from kailash.utils.url_credentials import fingerprint_secret

        return {
            "user_id": f"token_{fingerprint_secret(token)}",
            "auth_type": "bearer",
            "permissions": token_data.get("permissions", ["read"]),
            "metadata": token_data,
        }

    def get_client_config(self) -> Dict[str, Any]:
        """Get client configuration."""
        if self.tokens:
            first_token = next(iter(self.tokens.keys()))
            return {"type": "bearer", "token": first_token}
        return {"type": "bearer"}

    def get_server_config(self) -> Dict[str, Any]:
        """Get server configuration."""
        config = {"type": "bearer"}
        if self.validate_jwt:
            config.update(  # type: ignore[call-overload]
                {  # type: ignore[reportArgumentType]
                    "validate_jwt": True,
                    "jwt_secret": self.jwt_secret,
                    "jwt_algorithm": self.jwt_algorithm,
                    "expected_issuer": self.expected_issuer,
                    "expected_audience": self.expected_audience,
                }
            )
        else:
            config["tokens"] = list(self.tokens.keys())  # type: ignore[assignment]
        return config


class JWTAuth(BearerTokenAuth):
    """JWT-specific authentication provider with token creation.

    Extends BearerTokenAuth with JWT token creation capabilities.

    Args:
        secret: JWT signing secret
        algorithm: JWT algorithm
        expiration: Token expiration time in seconds
        issuer: Token issuer. Used both as the ``iss`` claim on tokens
            issued by :py:meth:`create_token` AND as the ``expected_issuer``
            allowlist on validation. When set, validation REQUIRES ``iss``
            to be present (cross-SDK port of esperie/kailash-rs#599).
        audience: The canonical resource URI this server identifies as.
            REQUIRED — ``JWTAuth`` always validates JWTs, so an absent
            ``audience`` raises ``ValueError`` at construction (fail-closed,
            enforcement-surface parity with ``ResourceServer``). Used both as
            the ``aud`` claim on tokens issued by :py:meth:`create_token` AND
            as the ``expected_audience`` allowlist on validation, which is
            FAIL-CLOSED on audience — it REQUIRES ``aud`` to be present AND
            equal to this value, per the MCP 2025-11-25 spec.

    Examples:
        Create JWT auth provider (spec-compliant, audience fail-closed):

        >>> auth = JWTAuth(
        ...     secret="my-secret",
        ...     expiration=3600,
        ...     audience="https://mcp.example.com",
        ... )
        >>> token = auth.create_token({"user": "alice", "permissions": ["read", "write"]})
    """

    def __init__(
        self,
        secret: str,
        algorithm: str = "HS256",
        expiration: int = 3600,
        issuer: str = "mcp-server",
        audience: Optional[str] = None,
    ):
        """Initialize JWT authentication."""
        super().__init__(
            validate_jwt=True,
            jwt_secret=secret,
            jwt_algorithm=algorithm,
            expected_issuer=issuer,
            expected_audience=audience,
        )
        self.expiration = expiration
        self.issuer = issuer
        self.audience = audience

    def create_token(
        self, payload: Dict[str, Any], expiration: Optional[int] = None
    ) -> str:
        """Create a JWT token.

        Args:
            payload: Token payload (should include 'user' and 'permissions')
            expiration: Custom expiration in seconds

        Returns:
            JWT token string

        Examples:
            >>> token = auth.create_token({
            ...     "user": "alice",
            ...     "permissions": ["read", "write"]
            ... })
        """
        if jwt is None:
            raise RuntimeError("JWT library not available")

        now = datetime.now(timezone.utc)
        exp_time = expiration or self.expiration

        jwt_payload = {
            "iss": self.issuer,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=exp_time)).timestamp()),
            "jti": str(uuid.uuid4()),
        }
        # Mint the `aud` claim when an audience is configured so tokens issued
        # by this provider pass its own fail-closed audience validation. The
        # caller's payload may override it explicitly.
        if self.audience is not None:
            jwt_payload["aud"] = self.audience
        jwt_payload.update(payload)

        return jwt.encode(jwt_payload, self.jwt_secret, algorithm=self.jwt_algorithm)  # type: ignore[union-attr, arg-type]


class BasicAuth(AuthProvider):
    """Basic HTTP authentication provider.

    Supports username/password authentication with secure password hashing.

    Args:
        users: Dict mapping usernames to password hashes or user data
        hash_passwords: Whether to hash plain text passwords

    Examples:
        Basic auth with plaintext passwords (for development):

        >>> auth = BasicAuth(users={
        ...     "admin": "password123",
        ...     "user": "secret456"
        ... }, hash_passwords=True)

        Basic auth with pre-hashed passwords:

        >>> auth = BasicAuth(users={
        ...     "admin": {
        ...         "password_hash": "hashed_password",
        ...         "permissions": ["read", "write", "admin"]
        ...     }
        ... })
    """

    def __init__(
        self, users: Dict[str, Union[str, Dict[str, Any]]], hash_passwords: bool = False
    ):
        """Initialize basic authentication."""
        self.users = {}

        # Normalize user data
        for username, user_data in users.items():
            if isinstance(user_data, str):
                # Plain password
                password = user_data
                if hash_passwords:
                    password_hash = self._hash_password(password)
                else:
                    password_hash = password

                self.users[username] = {
                    "password_hash": password_hash,
                    "permissions": ["read"],
                }
            else:
                # User data dict
                self.users[username] = user_data
                if hash_passwords and "password" in user_data:
                    self.users[username]["password_hash"] = self._hash_password(
                        user_data["password"]
                    )
                    del self.users[username]["password"]

        logger.info(f"Initialized Basic Auth with {len(self.users)} users")

    def _hash_password(self, password: str) -> str:
        """Hash a password using PBKDF2."""
        salt = os.urandom(32)
        kdf = PBKDF2HMAC(  # type: ignore[operator]
            algorithm=hashes.SHA256(),  # type: ignore[union-attr]
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = kdf.derive(password.encode())
        return base64.b64encode(salt + key).decode()

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against its hash (PBKDF2 or plaintext).

        Attempts PBKDF2 verification first. If the stored hash is not valid
        PBKDF2 data (e.g., plaintext from hash_passwords=False), falls back
        to timing-safe comparison via hmac.compare_digest.

        Security: Uses hmac.compare_digest for ALL comparisons to prevent
        timing side-channel attacks. Never uses == for password comparison.
        """
        # Try PBKDF2 verification first (preferred path)
        if _CRYPTO_AVAILABLE:
            try:
                decoded = base64.b64decode(password_hash.encode())
                if len(decoded) >= 64:  # salt (32) + key (32)
                    salt = decoded[:32]
                    stored_key = decoded[32:]

                    kdf = PBKDF2HMAC(  # type: ignore[operator]
                        algorithm=hashes.SHA256(),  # type: ignore[union-attr]
                        length=32,
                        salt=salt,
                        iterations=100000,
                    )

                    kdf.verify(password.encode(), stored_key)
                    return True
            except InvalidKey:  # type: ignore[misc]
                # Password does not match the PBKDF2 hash
                return False
            except (binascii.Error, ValueError):
                # Not valid base64/PBKDF2 — fall through to plaintext comparison
                pass

        # Timing-safe plaintext comparison (for hash_passwords=False mode)
        return hmac.compare_digest(password.encode(), password_hash.encode())

    def authenticate(self, credentials: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Authenticate basic auth credentials.

        Args:
            credentials: Dict with 'username' and 'password' fields (string not supported for BasicAuth)

        Returns:
            Authentication context dict
        """
        if isinstance(credentials, str):
            raise AuthenticationError(
                "BasicAuth requires dict with 'username' and 'password' fields, not string"
            )
        elif not isinstance(credentials, dict):
            raise AuthenticationError(
                f"Expected dict, got {type(credentials).__name__}"
            )

        username = credentials.get("username")
        password = credentials.get("password")

        if not username or not password:
            raise AuthenticationError("Missing username or password")

        if username not in self.users:
            raise AuthenticationError("Invalid username")

        user_data = self.users[username]
        password_hash = user_data.get("password_hash", "")

        if not self._verify_password(password, password_hash):
            raise AuthenticationError("Invalid password")

        return {
            "user_id": username,
            "auth_type": "basic",
            "permissions": user_data.get("permissions", ["read"]),
            "metadata": user_data,
        }

    def get_client_config(self) -> Dict[str, Any]:
        """Get client configuration."""
        # Return first user for client config (in practice, client specifies credentials)
        first_user = next(iter(self.users.keys()))
        return {
            "type": "basic",
            "username": first_user,
            "password": "***",  # Client should provide actual password
        }

    def get_server_config(self) -> Dict[str, Any]:
        """Get server configuration."""
        return {"type": "basic", "users": list(self.users.keys())}


class PermissionManager:
    """Permission management for authenticated users.

    Provides role-based and permission-based access control.

    Args:
        roles: Dict mapping role names to permissions
        default_permissions: Default permissions for all users

    Examples:
        Create permission manager:

        >>> pm = PermissionManager(roles={
        ...     "admin": ["read", "write", "delete", "manage"],
        ...     "editor": ["read", "write"],
        ...     "viewer": ["read"]
        ... })
        >>> pm.check_permission(user_info, "write")
    """

    def __init__(
        self,
        roles: Optional[Dict[str, List[str]]] = None,
        default_permissions: Optional[List[str]] = None,
    ):
        """Initialize permission manager."""
        self.roles = roles or {
            "admin": ["read", "write", "delete", "manage"],
            "editor": ["read", "write"],
            "viewer": ["read"],
        }
        self.default_permissions = default_permissions or ["read"]

    def check_permission(self, user_info: Dict[str, Any], permission: str) -> bool:
        """Check if user has specific permission.

        Args:
            user_info: User information from authentication
            permission: Permission to check

        Returns:
            True if user has permission

        Raises:
            PermissionError: If user lacks permission
        """
        user_permissions = self._get_user_permissions(user_info)

        if permission in user_permissions:
            return True

        raise PermissionError(
            f"User lacks required permission: {permission}",
            required_permission=permission,
        )

    def _get_user_permissions(self, user_info: Dict[str, Any]) -> List[str]:
        """Get all permissions for a user."""
        permissions = set(user_info.get("permissions", self.default_permissions))

        # Add role-based permissions
        roles = user_info.get("roles", [])
        for role in roles:
            if role in self.roles:
                permissions.update(self.roles[role])

        return list(permissions)


class RateLimiter:
    """Rate limiting for authenticated users.

    Implements token bucket algorithm for rate limiting.

    Args:
        default_limit: Default requests per minute
        burst_limit: Maximum burst requests
        per_user_limits: Custom limits per user

    Examples:
        Create rate limiter:

        >>> limiter = RateLimiter(default_limit=60, burst_limit=10)
        >>> limiter.check_rate_limit(user_info)
    """

    def __init__(
        self,
        default_limit: int = 60,  # requests per minute
        burst_limit: int = 10,
        per_user_limits: Optional[Dict[str, int]] = None,
    ):
        """Initialize rate limiter."""
        self.default_limit = default_limit
        self.burst_limit = burst_limit
        self.per_user_limits = per_user_limits or {}

        # Token buckets per user
        self._buckets: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"tokens": self.burst_limit, "last_refill": time.time()}
        )

    def check_rate_limit(self, user_info: Dict[str, Any]) -> bool:
        """Check if user is within rate limits.

        Args:
            user_info: User information from authentication

        Returns:
            True if request is allowed

        Raises:
            RateLimitError: If rate limit exceeded
        """
        user_id = user_info.get("user_id", "anonymous")
        limit = self.per_user_limits.get(user_id, self.default_limit)

        bucket = self._buckets[user_id]
        now = time.time()

        # Refill tokens
        time_passed = now - bucket["last_refill"]
        tokens_to_add = (time_passed / 60.0) * limit  # per minute
        bucket["tokens"] = min(self.burst_limit, bucket["tokens"] + tokens_to_add)
        bucket["last_refill"] = now

        # Check if request allowed
        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True
        else:
            retry_after = int(60.0 / limit)  # seconds until next token
            raise RateLimitError(
                f"Rate limit exceeded for user {user_id}", retry_after=retry_after
            )


class AuthManager:
    """Comprehensive authentication manager.

    Combines authentication providers with permission and rate limiting.

    Args:
        provider: Authentication provider
        permission_manager: Permission manager
        rate_limiter: Rate limiter
        enable_audit: Enable audit logging

    Examples:
        Create full auth manager:

        >>> auth_provider = APIKeyAuth(keys=["secret123"])
        >>> manager = AuthManager(
        ...     provider=auth_provider,
        ...     permission_manager=PermissionManager(),
        ...     rate_limiter=RateLimiter(default_limit=100)
        ... )
    """

    def __init__(
        self,
        provider: AuthProvider,
        permission_manager: Optional[PermissionManager] = None,
        rate_limiter: Optional[RateLimiter] = None,
        enable_audit: bool = True,
    ):
        """Initialize auth manager."""
        self.provider = provider
        self.permission_manager = permission_manager or PermissionManager()
        self.rate_limiter = rate_limiter
        self.enable_audit = enable_audit

        # Audit log
        self._audit_log: List[Dict[str, Any]] = []

    def authenticate_and_authorize(
        self, credentials: Dict[str, Any], required_permission: Optional[str] = None
    ) -> Dict[str, Any]:
        """Authenticate credentials and check authorization (SYNC path).

        Use this from a synchronous dispatch context. For an ASYNC provider
        (one whose ``authenticate`` is a coroutine function, e.g.
        ``ResourceServer``) call :py:meth:`authenticate_and_authorize_async`
        from an async context instead — a coroutine cannot be awaited here.

        Args:
            credentials: Authentication credentials
            required_permission: Required permission for the operation

        Returns:
            User information dict

        Raises:
            AuthenticationError: If authentication fails, OR if the configured
                provider is async and therefore cannot run on the sync path.
            PermissionError: If user lacks required permission
            RateLimitError: If rate limit exceeded
        """
        result = self.provider.authenticate(credentials)
        if inspect.isawaitable(result):
            # An async provider reached the SYNC auth path. Fail CLOSED with a
            # typed AuthenticationError rather than letting the un-awaited
            # coroutine leak downstream into an opaque AttributeError -> 500.
            # Close the coroutine so no "was never awaited" RuntimeWarning
            # fires at GC.
            result.close()  # type: ignore[union-attr]
            raise AuthenticationError(
                "authentication provider is async; call "
                "authenticate_and_authorize_async from an async dispatch "
                "context (async tool handler / WebSocket dispatch)"
            )
        return self._authorize(result, required_permission)

    async def authenticate_and_authorize_async(
        self, credentials: Dict[str, Any], required_permission: Optional[str] = None
    ) -> Dict[str, Any]:
        """Authenticate credentials and check authorization (ASYNC-aware path).

        Awaits the provider's ``authenticate`` when it is async (e.g.
        ``ResourceServer.authenticate``), and calls it directly when it is a
        plain sync provider — so a sync ``AuthProvider`` subclass works
        unchanged through this path too. This is the path the server's async
        tool dispatch (WebSocket) uses so an async ``auth_provider`` is
        actually reachable through the documented server wiring rather than
        crashing on an un-awaited coroutine.

        Args:
            credentials: Authentication credentials
            required_permission: Required permission for the operation

        Returns:
            User information dict

        Raises:
            AuthenticationError: If authentication fails
            PermissionError: If user lacks required permission
            RateLimitError: If rate limit exceeded
        """
        result = self.provider.authenticate(credentials)
        if inspect.isawaitable(result):
            user_info = await result
        else:
            user_info = result
        return self._authorize(user_info, required_permission)

    def _authorize(
        self, user_info: Dict[str, Any], required_permission: Optional[str]
    ) -> Dict[str, Any]:
        """Post-authentication rate-limit + permission + audit gate.

        Shared by both the sync and async authenticate paths so the
        authorization semantics are identical regardless of dispatch context.
        """
        # Check rate limits
        if self.rate_limiter:
            self.rate_limiter.check_rate_limit(user_info)

        # Check permissions
        if required_permission:
            self.permission_manager.check_permission(user_info, required_permission)

        # Audit log
        if self.enable_audit:
            self._log_auth_event("success", user_info, required_permission)

        return user_info

    def _log_auth_event(
        self,
        event_type: str,
        user_info: Dict[str, Any],
        permission: Optional[str] = None,
    ):
        """Log authentication event."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "user_id": user_info.get("user_id"),
            "auth_type": user_info.get("auth_type"),
            "permission": permission,
        }
        self._audit_log.append(event)

        # Keep only last 1000 events
        if len(self._audit_log) > 1000:
            self._audit_log = self._audit_log[-1000:]

    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get audit log entries.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of audit log entries
        """
        return self._audit_log[-limit:]
