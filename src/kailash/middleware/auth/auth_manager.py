"""SDK-based authentication manager for Kailash middleware.

This module provides authentication management using SDK security nodes
instead of manual JWT handling and custom implementations.

Migration note (#445 Wave 1)
----------------------------
This module previously imported FastAPI (``Depends``, ``HTTPException``,
``HTTPBearer``) to expose auth as a FastAPI dependency. Per the
framework-first policy (only the adapter/transport layer may touch raw
HTTP libraries), the auth manager now exposes a transport-agnostic
``authenticate_request`` method and raises Kailash trust-auth exceptions
(``AuthenticationError``, ``AuthorizationError``, ...) rather than
``fastapi.HTTPException``. The Nexus transport layer / NexusAuthPlugin
middleware is responsible for mapping those exceptions to HTTP status
codes via the ``status_code`` attribute on
:class:`~kailash.trust.auth.exceptions.AuthError`.

The removed ``get_current_user_dependency`` helper and the non-functional
``require_auth`` stub have been deleted; they had no production callers
and ``NotImplementedError`` stubs are BLOCKED by the zero-tolerance
policy (rules/zero-tolerance.md Rule 2).
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import jwt

from ...nodes.admin import PermissionCheckNode
from ...nodes.data import AsyncSQLDatabaseNode
from ...nodes.security import (
    AuditLogNode,
    CredentialManagerNode,
    RotatingCredentialNode,
    SecurityEventNode,
)
from ...nodes.transform import DataTransformer
from ...trust.auth.exceptions import (
    AuthenticationError,
    AuthError,
    AuthorizationError,
    ExpiredTokenError,
    InsufficientPermissionError,
    InvalidTokenError,
)

logger = logging.getLogger(__name__)


class AuthLevel(Enum):
    """Authentication levels for different security requirements."""

    PUBLIC = "public"
    BASIC = "basic"
    STANDARD = "standard"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class MiddlewareAuthManager:
    """Authentication manager using SDK security nodes.

    Provides:
        * JWT token management with :class:`CredentialManagerNode`
        * API key rotation with :class:`RotatingCredentialNode`
        * Permission checking with :class:`PermissionCheckNode`
        * Security event logging with :class:`SecurityEventNode`
        * Audit trail with :class:`AuditLogNode`

    The manager is transport-agnostic. It raises Kailash
    :class:`~kailash.trust.auth.exceptions.AuthError` subclasses (whose
    ``status_code`` attribute carries the HTTP semantic: 401 for
    authentication failures, 403 for authorization failures). The Nexus
    transport layer / :class:`nexus.auth.plugin.NexusAuthPlugin` middleware
    maps these to HTTP responses.
    """

    def __init__(
        self,
        secret_key: Optional[str] = None,
        token_expiry_hours: int = 24,
        enable_api_keys: bool = True,
        enable_audit: bool = True,
        database_url: Optional[str] = None,
    ):
        """Initialize the middleware auth manager.

        Args:
            secret_key: Secret key for JWT signing. In production, JWT
                secrets should come from the environment or a secrets
                manager (vault), not from configuration.
            token_expiry_hours: Token expiration time in hours.
            enable_api_keys: Enable API key authentication.
            enable_audit: Enable audit logging.
            database_url: Database URL for persistence.
        """
        self.token_expiry_hours = token_expiry_hours
        self.enable_api_keys = enable_api_keys
        self.enable_audit = enable_audit

        # Initialize SDK security nodes
        self._initialize_security_nodes(secret_key or "", database_url or "")

    def _initialize_security_nodes(self, secret_key: str, database_url: str):
        """Initialize all SDK security nodes."""
        # Store the secret key in memory for JWT operations
        self.secret_key = secret_key

        # Credential manager for fetching other credentials (not for JWT secret).
        # In production, JWT secret would come from environment or vault.
        self.credential_manager = CredentialManagerNode(
            credential_name="api_credentials",
            credential_type="api_key",
            name="jwt_credential_manager",
        )

        # Rotating credentials for API keys
        if self.enable_api_keys:
            self.api_key_manager = RotatingCredentialNode(
                name="api_key_rotator"
                # RotatingCredentialNode doesn't require credential_name or
                # rotation_interval_days in __init__; they're passed at execute.
            )

        # Permission checker
        self.permission_checker = PermissionCheckNode(
            name="middleware_permission_checker"
        )

        # Security event logger
        self.security_logger = SecurityEventNode(name="middleware_security_events")

        # Audit logger
        if self.enable_audit:
            self.audit_logger = AuditLogNode(name="middleware_audit")

        # Data transformer for token operations
        self.token_transformer = DataTransformer(name="token_transformer")

        # Database node for user storage
        if database_url:
            self.db_node = AsyncSQLDatabaseNode(
                name="auth_database", connection_string=database_url
            )

    async def create_access_token(
        self,
        user_id: str,
        permissions: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a JWT access token.

        Args:
            user_id: User identifier.
            permissions: List of permissions.
            metadata: Additional metadata.

        Returns:
            JWT token string.

        Raises:
            AuthError: If the token cannot be signed (e.g. misconfigured
                secret).
        """
        payload = {
            "user_id": user_id,
            "permissions": permissions or [],
            "metadata": metadata or {},
            "exp": datetime.now(timezone.utc)
            + timedelta(hours=self.token_expiry_hours),
            "iat": datetime.now(timezone.utc),
        }

        try:
            token = jwt.encode(payload, self.secret_key, algorithm="HS256")
        except Exception as e:
            logger.error("create_access_token.failed", extra={"error": str(e)})
            raise AuthError(f"Failed to create token: {e}") from e

        # Audit token creation
        if self.enable_audit:
            self.audit_logger.execute(
                user_id=user_id,
                action="create_token",
                resource_type="jwt_token",
                resource_id=user_id,
                details={"permissions": permissions},
            )

        return token

    async def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify and decode a JWT token.

        Args:
            token: JWT token string.

        Returns:
            Decoded token payload.

        Raises:
            ExpiredTokenError: If the token has expired.
            InvalidTokenError: If the token signature or structure is
                invalid.
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
        except jwt.ExpiredSignatureError as e:
            self.security_logger.execute(
                event_type="token_expired",
                severity="warning",
                details={"error": str(e)},
            )
            raise ExpiredTokenError("Token has expired") from e
        except Exception as e:
            self.security_logger.execute(
                event_type="token_verification_failed",
                severity="warning",
                details={"error": str(e)},
            )
            raise InvalidTokenError("Invalid authentication token") from e

        # Defensive expiration check (PyJWT already validates exp; this
        # preserves the original behavior for payloads decoded via paths
        # that somehow bypass the library check).
        exp = payload.get("exp", 0)
        if exp and exp < datetime.now(timezone.utc).timestamp():
            raise ExpiredTokenError("Token has expired")

        return payload

    async def create_api_key(
        self,
        user_id: str,
        key_name: str,
        permissions: Optional[List[str]] = None,
    ) -> str:
        """Create an API key using :class:`CredentialManagerNode`.

        Args:
            user_id: User identifier.
            key_name: Human-readable name for the API key.
            permissions: List of permissions.

        Returns:
            The generated API key string.

        Raises:
            AuthError: If API keys are disabled or storage fails.
        """
        if not self.enable_api_keys:
            raise AuthError("API keys are disabled")

        api_key = f"sk_{secrets.token_urlsafe(32)}"

        result = self.credential_manager.execute(
            operation="store_credential",
            credential_name=api_key,
            credential_data={
                "user_id": user_id,
                "key_name": key_name,
                "permissions": permissions or [],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "api_key": api_key,
            },
        )

        if not result.get("success", False):
            raise AuthError("Failed to create API key")

        if self.enable_audit:
            self.audit_logger.execute(
                user_id=user_id,
                action="create_api_key",
                resource_type="api_key",
                resource_id=key_name,
                details={"permissions": permissions},
            )

        return api_key

    async def verify_api_key(self, api_key: str) -> Dict[str, Any]:
        """Verify an API key.

        Args:
            api_key: API key string.

        Returns:
            API key metadata (``user_id``, ``permissions``, ...).

        Raises:
            AuthenticationError: If API keys are disabled or the key is
                invalid.
        """
        if not self.enable_api_keys:
            raise AuthError("API keys are disabled")

        try:
            result = self.credential_manager.execute(
                operation="get_credential", credential_name=api_key
            )
        except Exception as e:
            self.security_logger.execute(
                event_type="api_key_verification_failed",
                severity="warning",
                details={"error": str(e)},
            )
            raise AuthenticationError("Invalid API key") from e

        if not result.get("success", False):
            raise AuthenticationError("Invalid API key")

        credential_data = result.get("credential", {})
        return credential_data.get("metadata", {})

    async def check_permission(
        self,
        user_id: str,
        permission: str,
        resource: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Check whether *user_id* holds *permission*.

        Args:
            user_id: User identifier.
            permission: Permission to check.
            resource: Optional resource context.

        Returns:
            ``True`` if the permission is granted.
        """
        result = self.permission_checker.execute(
            user_context={"user_id": user_id},
            permission=permission,
            resource=resource or {},
        )

        granted = result.get("authorized", False)

        if self.enable_audit:
            self.audit_logger.execute(
                user_id=user_id,
                action="check_permission",
                resource_type="permission",
                resource_id=permission,
                details={"granted": granted, "resource": resource},
            )

        return granted

    async def authenticate_request(
        self,
        authorization_header: Optional[str] = None,
        api_key_header: Optional[str] = None,
        required_permissions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Authenticate a request and return the resolved user context.

        Transport-agnostic replacement for the old FastAPI
        ``get_current_user_dependency``. Nexus middleware (or any HTTP
        adapter) should call this with the raw header values and handle
        the resulting exceptions by mapping them to HTTP status codes via
        the ``status_code`` attribute on
        :class:`~kailash.trust.auth.exceptions.AuthError`.

        Args:
            authorization_header: Value of the ``Authorization`` header
                (e.g. ``"Bearer <token>"``).
            api_key_header: Value of the ``X-API-Key`` header.
            required_permissions: Permissions the caller must hold.

        Returns:
            Dict with ``user_id``, ``permissions``, and ``metadata``.

        Raises:
            AuthenticationError: No valid credentials were supplied.
            InsufficientPermissionError: Credentials are valid but lack a
                required permission.
        """
        last_auth_error: Optional[AuthError] = None

        # Try bearer token first.
        bearer_token = _extract_bearer_token(authorization_header)
        if bearer_token:
            try:
                payload = await self.verify_token(bearer_token)
                user_id = payload.get("user_id")
                token_permissions = payload.get("permissions", [])
                await self._enforce_permissions(
                    user_id, token_permissions, required_permissions
                )
                return {
                    "user_id": user_id,
                    "permissions": token_permissions,
                    "metadata": payload.get("metadata", {}),
                }
            except AuthorizationError:
                # Authorization failures are terminal — don't silently
                # fall through to API keys when a valid token is present
                # but lacks a permission (that would mask the real reason).
                raise
            except AuthError as e:
                last_auth_error = e

        # Try API key from header.
        if api_key_header:
            try:
                metadata = await self.verify_api_key(api_key_header)
                user_id = metadata.get("user_id")
                key_permissions = metadata.get("permissions", [])
                await self._enforce_permissions(
                    user_id, key_permissions, required_permissions
                )
                return {
                    "user_id": user_id,
                    "permissions": key_permissions,
                    "metadata": metadata,
                }
            except AuthorizationError:
                raise
            except AuthError as e:
                last_auth_error = e

        # No valid authentication — surface the most specific error if we
        # have one, otherwise a generic authentication failure.
        if last_auth_error is not None:
            raise last_auth_error
        raise AuthenticationError("Not authenticated")

    async def _enforce_permissions(
        self,
        user_id: Optional[str],
        held_permissions: List[str],
        required_permissions: Optional[List[str]],
    ) -> None:
        """Raise :class:`InsufficientPermissionError` if any required
        permission is missing, falling back to the permission node when
        the held-permissions list is incomplete.
        """
        if not required_permissions:
            return
        for perm in required_permissions:
            if perm in held_permissions:
                continue
            if user_id is None or not await self.check_permission(user_id, perm):
                raise InsufficientPermissionError(
                    f"Missing required permission: {perm}"
                )


def _extract_bearer_token(authorization_header: Optional[str]) -> Optional[str]:
    """Extract the token from an ``Authorization: Bearer <token>`` header.

    Returns ``None`` if the header is missing, malformed, or uses a
    different scheme. Case-insensitive on the scheme name per RFC 7235.
    """
    if not authorization_header:
        return None
    parts = authorization_header.strip().split(None, 1)
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != "bearer":
        return None
    token = token.strip()
    return token or None


__all__ = [
    "AuthLevel",
    "MiddlewareAuthManager",
]
