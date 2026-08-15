"""
SDK-based Authentication Manager for Kailash Middleware

This module provides authentication management using SDK security nodes
instead of manual JWT handling and custom implementations.

Moved from middleware/auth.py to resolve directory/file confusion.
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

# `jwt`, `fastapi`, and `starlette` are OPTIONAL dependencies. PyJWT ships with
# both the `server` extra (middleware needs it) and the `trust` extra (SSO
# needs it); fastapi/starlette ship only with `server`. Per
# `rules/dependencies.md` § "Declared = Imported": optional-extra imports MUST
# raise loudly with an actionable error naming the extra.
try:
    import jwt
    from fastapi import Depends
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from starlette.exceptions import HTTPException
    from starlette.requests import Request
except ImportError as exc:  # pragma: no cover — covered by structural invariant test
    raise ImportError(
        "kailash.middleware.auth.auth_manager requires server dependencies "
        "(PyJWT, fastapi, starlette). "
        "Install with: pip install 'kailash[server]'"
    ) from exc

from ...nodes.admin import PermissionCheckNode
from ...nodes.data import AsyncSQLDatabaseNode
from ...nodes.security import (
    AuditLogNode,
    CredentialManagerNode,
    RotatingCredentialNode,
    SecurityEventNode,
)
from ...nodes.transform import DataTransformer
from ...utils.http_errors import safe_http_detail
from .api_keys import (
    APIKeyRecord,
    APIKeyStore,
    InMemoryAPIKeyStore,
    derive_secret_digest,
    generate_api_key,
    generate_salt,
    split_api_key,
)
from .revocation import InMemoryTokenRevocationStore, TokenRevocationStore

logger = logging.getLogger(__name__)


class AuthLevel(Enum):
    """Authentication levels for different security requirements."""

    PUBLIC = "public"
    BASIC = "basic"
    STANDARD = "standard"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class MiddlewareAuthManager:
    """
    Authentication manager using SDK security nodes.

    Provides:
    - JWT token management with revocation via ``TokenRevocationStore``
    - API key issue/verify/revoke via ``APIKeyStore`` (keys stored hashed)
    - Permission checking with PermissionCheckNode
    - Security event logging with SecurityEventNode
    - Audit trail with AuditLogNode

    This replaces manual JWT handling with SDK components for better
    security, performance, and consistency.

    Note:
        The API-key methods do NOT go through ``CredentialManagerNode``, and
        the earlier claim that they did was the defect in issue #2108: that node
        **fetches** credentials from the environment, a file, or a vault, and has
        no write path -- so no key could be issued, and its return dict has no
        ``success`` key, so no key could verify either. Issued keys live in an
        :class:`~kailash.middleware.auth.api_keys.APIKeyStore`.
    """

    def __init__(
        self,
        secret_key: Optional[str] = None,
        token_expiry_hours: int = 24,
        enable_api_keys: bool = True,
        enable_audit: bool = True,
        database_url: Optional[str] = None,
        enable_blacklist: bool = True,
        revocation_store: Optional[TokenRevocationStore] = None,
        api_key_store: Optional[APIKeyStore] = None,
    ):
        """
        Initialize SDK Auth Manager.

        Args:
            secret_key: Secret key for JWT signing (will use CredentialManager)
            token_expiry_hours: Token expiration time in hours
            enable_api_keys: Enable API key authentication
            enable_audit: Enable audit logging
            database_url: Database URL for persistence
            enable_blacklist: Enable token revocation. When True (default) a
                ``TokenRevocationStore`` is held and ``verify_token`` rejects
                revoked tokens; when False no store is held and revocation is a
                no-op (issue #1356 sibling).
            revocation_store: Backend that records and checks token revocation.
                When ``enable_blacklist`` is True and this is omitted, a
                process-local :class:`InMemoryTokenRevocationStore` is used —
                revocations are visible only within this worker. In a
                multi-worker deployment supply a shared backend (Redis, database,
                distributed cache) implementing :class:`TokenRevocationStore` so
                revocation propagates to every worker. Ignored when
                ``enable_blacklist`` is False.
            api_key_store: Backend holding issued API keys (issue #2108). When
                ``enable_api_keys`` is True and this is omitted, a process-local
                :class:`~kailash.middleware.auth.api_keys.InMemoryAPIKeyStore`
                is used -- keys issued through one worker are unknown to the
                others, which REFUSES them (fail-closed) rather than granting
                anything. Supply a shared
                :class:`~kailash.middleware.auth.api_keys.APIKeyStore` (Redis,
                database, distributed cache) to issue keys usable across every
                worker. Ignored when ``enable_api_keys`` is False.
        """
        self.token_expiry_hours = token_expiry_hours
        self.enable_api_keys = enable_api_keys
        self.enable_audit = enable_audit
        self.enable_blacklist = enable_blacklist

        # Token revocation backend (issue #1356 sibling — MiddlewareAuthManager).
        # When blacklisting is enabled, use the injected shared store if provided,
        # else a process-local default. A SHARED store propagates revocation across
        # every worker that shares it; the default InMemoryTokenRevocationStore is
        # process-local. When disabled, no store is held and revocation is a no-op.
        self._revocation_store: Optional[TokenRevocationStore] = None
        if enable_blacklist:
            self._revocation_store = revocation_store or InMemoryTokenRevocationStore()

        # Issued API keys (issue #2108). Held only when the feature is enabled,
        # so `enable_api_keys=False` cannot leave a store that nothing writes to
        # and nothing reads from. Process-local by default; see the constructor
        # docstring for why that direction is fail-CLOSED.
        self._api_key_store: Optional[APIKeyStore] = None
        if enable_api_keys:
            self._api_key_store = api_key_store or InMemoryAPIKeyStore()

        # Initialize SDK security nodes
        self._initialize_security_nodes(secret_key or "", database_url or "")

        # FastAPI security scheme
        self.bearer_scheme = HTTPBearer(auto_error=False)

    def _initialize_security_nodes(self, secret_key: str, database_url: str):
        """Initialize all SDK security nodes."""

        # Store the secret key in memory for JWT operations
        self.secret_key = secret_key

        # Credential manager for fetching other credentials (not for JWT secret)
        # In production, JWT secret would come from environment or vault
        self.credential_manager = CredentialManagerNode(
            credential_name="api_credentials",
            credential_type="api_key",
            name="jwt_credential_manager",
        )

        # Rotating credentials for API keys
        if self.enable_api_keys:
            self.api_key_manager = RotatingCredentialNode(
                name="api_key_rotator"
                # Note: RotatingCredentialNode doesn't require credential_name or rotation_interval_days in __init__
                # These are passed during execution
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

    def _emit_security_event(
        self, event_type: str, severity: str, details: Dict[str, Any]
    ) -> None:
        """Emit a security event best-effort — observability MUST NOT break auth.

        The auth decision is made by the caller (which raises the 401); security
        logging is a side effect. If ``SecurityEventNode`` raises (bad input,
        backend down), swallow it and record a fallback line via the module
        logger so a logging failure can NEVER convert the caller's deliberate
        401 into a 500. Pairs with the revoked/verification-failed call sites,
        which raise their own ``HTTPException`` after this returns.
        """
        try:
            self.security_logger.execute(
                event_type=event_type, severity=severity, details=details
            )
        except Exception:  # pragma: no cover - logging failure must not break auth
            logger.warning("security event logging failed for %s", event_type)

    async def create_access_token(
        self,
        user_id: str,
        permissions: List[str] | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> str:
        """
        Create JWT access token using SDK nodes.

        Args:
            user_id: User identifier
            permissions: List of permissions
            metadata: Additional metadata

        Returns:
            JWT token string
        """
        # Create token payload
        payload = {
            "user_id": user_id,
            "permissions": permissions or [],
            "metadata": metadata or {},
            # jti (JWT ID) is the canonical revocation identity a shared
            # TokenRevocationStore keys on, so revocation propagates across
            # workers (issue #1356 sibling).
            "jti": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc)
            + timedelta(hours=self.token_expiry_hours),
            "iat": datetime.now(timezone.utc),
        }

        # Create JWT token
        # In production, this would use a more sophisticated approach
        # For now, we'll use the JWT library directly
        try:
            token = jwt.encode(payload, self.secret_key, algorithm="HS256")
            token_result = {"token": token}
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=safe_http_detail(e, logger=logger, context="create token"),
            ) from e

        # Log token creation
        if self.enable_audit:
            self.audit_logger.execute(
                user_id=user_id,
                action="create_token",
                resource_type="jwt_token",
                resource_id=user_id,
                details={"permissions": permissions},
            )

        return token_result.get("token") or ""

    async def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify and decode JWT token using SDK nodes.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            HTTPException: If token is invalid
        """
        try:
            # Verify JWT token
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])

            # Reject revoked tokens (issue #1356 sibling). Checked AFTER decode so
            # the revocation identity (jti) is available — the key a shared store
            # uses so revocation propagates across workers. Pass BOTH jti AND token:
            # revoke() keys on `jti or token`, so a token revoked before its jti
            # was known (decode-failure path) is keyed by raw token; dropping
            # `token=` here would silently stop enforcing those revocations.
            if (
                self._revocation_store is not None
                and self._revocation_store.is_revoked(
                    jti=payload.get("jti"), token=token
                )
            ):
                self._emit_security_event(
                    "token_revoked",
                    "MEDIUM",
                    {"reason": "token presented after revocation"},
                )
                raise HTTPException(status_code=401, detail="Token has been revoked")

            # Check expiration
            if payload.get("exp", 0) < datetime.now(timezone.utc).timestamp():
                raise HTTPException(status_code=401, detail="Token has expired")

            return payload

        except HTTPException:
            # A deliberate auth rejection (revoked / expired) already carries its
            # own status + detail + security-event log — propagate it as-is rather
            # than masking it as a generic "Invalid authentication token".
            raise
        except Exception as e:
            # Log security event (best-effort — never lets logging break the 401).
            self._emit_security_event(
                "token_verification_failed", "MEDIUM", {"error": str(e)}
            )
            raise HTTPException(status_code=401, detail="Invalid authentication token")

    async def revoke_token(self, token: str) -> None:
        """
        Revoke an access token so subsequent ``verify_token`` calls reject it.

        With a shared :class:`TokenRevocationStore` this propagates to every
        worker that shares it; with the default in-memory store it is
        process-local (issue #1356 sibling — MiddlewareAuthManager). When
        ``enable_blacklist`` is False this is a no-op.

        Args:
            token: JWT token string to revoke. A malformed/expired token is still
                recorded (by raw token string) so a token presented for
                revocation is never silently ignored.
        """
        if self._revocation_store is None:
            return

        user_id: Optional[str] = None
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            user_id = payload.get("user_id")
            jti = payload.get("jti")
            exp = payload.get("exp")
            expires_at = datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None
            self._revocation_store.revoke(jti=jti, token=token, expires_at=expires_at)
        except Exception:
            # Even if verification fails, revoke by raw token string so a
            # malformed/expired token presented for revocation is still recorded.
            # Bound the entry's TTL so an attacker spamming revoke with unique
            # invalid strings cannot grow the store without limit. The longest a
            # legitimately-issued access token can remain presentable is
            # token_expiry_hours; cap the entry there so a FORGED far-future `exp`
            # in an unverified token cannot extend the entry's lifetime beyond it
            # (no presentable token outlives the cap, so the entry self-purges
            # without ever evicting a still-valid token).
            ttl_cap = datetime.now(timezone.utc) + timedelta(
                hours=self.token_expiry_hours
            )
            expires_at = ttl_cap
            try:
                unverified = jwt.decode(
                    token, options={"verify_signature": False, "verify_exp": False}
                )
                exp = unverified.get("exp")
                if exp:
                    expires_at = min(
                        datetime.fromtimestamp(exp, tz=timezone.utc), ttl_cap
                    )
            except Exception:
                expires_at = ttl_cap
            self._revocation_store.revoke(jti=None, token=token, expires_at=expires_at)

        # Audit log
        if self.enable_audit:
            self.audit_logger.execute(
                user_id=user_id or "unknown",
                action="revoke_token",
                resource_type="jwt_token",
                resource_id=user_id or "unknown",
                details={"revoked": True},
            )

    async def create_api_key(
        self,
        user_id: str,
        key_name: str,
        permissions: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Issue an API key and record it in the API key store.

        The plaintext key is returned HERE AND ONLY HERE. Only its SHA-256
        digest is stored, so it cannot be recovered from the store, a log, or a
        backup -- a lost key is reissued, never looked up.

        Args:
            user_id: User identifier the key authenticates as
            key_name: Human-readable name for the API key
            permissions: List of permissions granted to bearers of this key
            expires_at: Optional expiry; after it the key fails verification
            metadata: Free-form data carried through verification

        Returns:
            The plaintext API key string.

        Raises:
            HTTPException: API keys are disabled (400), or the store rejected
                the write (500).
        """
        if not self.enable_api_keys or self._api_key_store is None:
            raise HTTPException(status_code=400, detail="API keys are disabled")

        # `sk_<key_id>.<secret>`, both halves from `secrets.token_urlsafe` and
        # therefore ASCII, which keeps the key presentable through the header
        # path that rejects non-ASCII (#2114). Only the secret authorizes, and
        # only its salted digest is stored.
        api_key, key_id, secret = generate_api_key()
        salt = generate_salt()

        record = APIKeyRecord(
            user_id=user_id,
            key_name=key_name,
            secret_digest=derive_secret_digest(secret, salt),
            salt=salt,
            permissions=list(permissions or []),
            expires_at=expires_at,
            metadata=dict(metadata or {}),
        )

        try:
            self._api_key_store.store(key_id=key_id, record=record)
        except Exception as e:
            # A store that refused the write has NOT issued a key. Returning the
            # plaintext anyway would hand the caller a credential that can never
            # authenticate -- the shape this whole change exists to remove.
            self._emit_security_event(
                "api_key_creation_failed", "HIGH", {"error": type(e).__name__}
            )
            raise HTTPException(
                status_code=500,
                detail=safe_http_detail(e, logger=logger, context="create API key"),
            ) from e

        # Audit log
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
        """
        Verify an API key against the issued-key store.

        Args:
            api_key: API key string as presented by the caller

        Returns:
            The key's record as a dict, with ``user_id`` and ``permissions`` at
            the top level -- which is what
            :meth:`get_current_user_dependency` reads to build the principal.

        Raises:
            HTTPException: API keys are disabled (400), or the key is unknown,
                revoked, or expired (401).
        """
        if not self.enable_api_keys or self._api_key_store is None:
            raise HTTPException(status_code=400, detail="API keys are disabled")

        parts = split_api_key(api_key)
        record = None
        if parts is not None:
            key_id, secret = parts
            try:
                record = self._api_key_store.lookup(key_id=key_id)
            except Exception as e:
                # A store failure is not an authentication. Fail CLOSED and
                # record it: a backend outage must never widen access.
                self._emit_security_event(
                    "api_key_verification_failed", "MEDIUM", {"error": type(e).__name__}
                )
                raise HTTPException(status_code=401, detail="Invalid API key") from e

        # A malformed key, an unknown one, a revoked one (dropped from the
        # store), an expired one, and a well-formed key_id presented with the
        # WRONG secret are all the same answer to the caller: no principal.
        # Distinguishing them in the response would tell an anonymous prober
        # which of its guesses named a real key.
        #
        # `record.verify_secret` is the load-bearing check, and finding a record
        # is NOT authentication: the key_id half is public, so a caller who
        # learns one from a log could otherwise present it with any secret.
        if (
            parts is None
            or record is None
            or record.is_expired()
            or not record.verify_secret(parts[1])
        ):
            self._emit_security_event(
                "api_key_verification_failed",
                "MEDIUM",
                {"reason": "malformed, unknown, revoked, expired, or wrong secret"},
            )
            raise HTTPException(status_code=401, detail="Invalid API key")

        # The digest and salt are deliberately NOT in the returned dict: this
        # value flows to application code and into any log that records the
        # principal, and a verifier has no use for verification material.
        return record.to_dict()

    async def revoke_api_key(self, api_key: str) -> bool:
        """
        Revoke an issued API key so subsequent verification rejects it.

        With a shared :class:`~kailash.middleware.auth.api_keys.APIKeyStore`
        this propagates to every worker sharing it; with the default in-memory
        store it is process-local.

        Args:
            api_key: The plaintext key to revoke.

        Returns:
            True if a key was present and is now revoked; False if the key was
            already unknown (which is not an error -- the end state is the same).

        Raises:
            HTTPException: API keys are disabled (400).
        """
        if not self.enable_api_keys or self._api_key_store is None:
            raise HTTPException(status_code=400, detail="API keys are disabled")

        parts = split_api_key(api_key)
        if parts is None:
            # A malformed key was never issued, so there is nothing to revoke.
            # Reported as "no key removed" rather than raised: the end state the
            # caller asked for already holds.
            return False

        key_id, secret = parts
        record = self._api_key_store.lookup(key_id=key_id)

        # Revocation requires proving possession of the SECRET, not merely
        # naming a key_id. The id half is public and may appear in an audit log,
        # so revoking on the id alone would let anyone who read that log revoke
        # another principal's key -- a denial-of-service with no credential.
        if record is None or not record.verify_secret(secret):
            return False

        revoked = self._api_key_store.revoke(key_id=key_id)

        if revoked and self.enable_audit:
            self.audit_logger.execute(
                user_id=record.user_id if record else "unknown",
                action="revoke_api_key",
                resource_type="api_key",
                resource_id=record.key_name if record else "unknown",
                details={"revoked": True},
            )

        return revoked

    async def check_permission(
        self, user_id: str, permission: str, resource: Optional[Dict[str, Any]] = None  # type: ignore[assignment]
    ) -> bool:
        """
        Check user permission using PermissionCheckNode.

        Args:
            user_id: User identifier
            permission: Permission to check
            resource: Optional resource context

        Returns:
            True if permission is granted
        """
        result = self.permission_checker.execute(
            user_context={"user_id": user_id},
            permission=permission,
            resource=resource or {},
        )

        granted = result.get("authorized", False)

        # Audit permission check
        if self.enable_audit:
            self.audit_logger.execute(
                user_id=user_id,
                action="check_permission",
                resource_type="permission",
                resource_id=permission,
                details={"granted": granted, "resource": resource},
            )

        return granted

    def get_current_user_dependency(self, required_permissions: List[str] = None):  # type: ignore[reportArgumentType]
        """
        Create FastAPI dependency for user authentication.

        Args:
            required_permissions: List of required permissions

        Returns:
            FastAPI dependency function
        """

        async def verify_user(
            request: Request,
            credentials: HTTPAuthorizationCredentials = Depends(self.bearer_scheme),
        ) -> Dict[str, Any]:
            """Verify user from request."""

            # Try bearer token first
            if credentials and credentials.credentials:
                try:
                    payload = await self.verify_token(credentials.credentials)
                    user_id = payload.get("user_id")

                    # Check permissions if required
                    if required_permissions:
                        user_permissions = payload.get("permissions", [])
                        for perm in required_permissions:
                            if perm not in user_permissions:
                                # Check using permission node
                                if not await self.check_permission(user_id, perm):  # type: ignore[reportArgumentType]
                                    raise HTTPException(
                                        status_code=403,
                                        detail=f"Missing required permission: {perm}",
                                    )

                    return {
                        "user_id": user_id,
                        "permissions": payload.get("permissions", []),
                        "metadata": payload.get("metadata", {}),
                    }
                except HTTPException:
                    pass

            # Try API key from header
            api_key = request.headers.get("X-API-Key")
            if api_key:
                try:
                    metadata = await self.verify_api_key(api_key)
                    user_id = metadata.get("user_id")

                    # Check permissions
                    if required_permissions:
                        key_permissions = metadata.get("permissions", [])
                        for perm in required_permissions:
                            if perm not in key_permissions:
                                if not await self.check_permission(user_id, perm):  # type: ignore[reportArgumentType]
                                    raise HTTPException(
                                        status_code=403,
                                        detail=f"Missing required permission: {perm}",
                                    )

                    return {
                        "user_id": user_id,
                        "permissions": metadata.get("permissions", []),
                        "metadata": metadata,
                    }
                except HTTPException:
                    pass

            # No valid authentication
            raise HTTPException(status_code=401, detail="Not authenticated")

        return verify_user
