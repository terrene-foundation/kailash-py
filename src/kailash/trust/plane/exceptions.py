# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Trust-plane exception hierarchy.

All trust-plane exceptions inherit from TrustPlaneError so callers
can catch the entire family with a single except clause.

Every exception accepts an optional ``details`` dict per EATP convention,
enabling structured error context for audit trails and diagnostics.
"""

from __future__ import annotations

import logging
from typing import Any

from kailash.trust.exceptions import TrustError as _TrustError

logger = logging.getLogger(__name__)

__all__ = [
    # Base
    "TrustPlaneError",
    # Store
    "TrustPlaneStoreError",
    "RecordNotFoundError",
    "SchemaTooNewError",
    "SchemaMigrationError",
    "StoreConnectionError",
    "StoreQueryError",
    "StoreTransactionError",
    # Crypto / decryption
    "TrustDecryptionError",
    # Key manager
    "KeyManagerError",
    "KeyNotFoundError",
    "KeyExpiredError",
    "SigningError",
    "VerificationError",
    # Constraint / budget
    "ConstraintViolationError",
    "BudgetExhaustedError",
    # Identity / OIDC
    "IdentityError",
    "TokenVerificationError",
    "JWKSError",
    # RBAC
    "RBACError",
    # Archive
    "ArchiveError",
    # SIEM
    "TLSSyslogError",
    # Locking
    "LockTimeoutError",
]


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class TrustPlaneError(_TrustError):
    """Base exception for all trust-plane errors.

    Inherits from kailash.trust.exceptions.TrustError so that
    ``except TrustError`` catches both protocol and platform errors.

    Attributes:
        details: Structured context for audit trails and diagnostics.
    """

    def __init__(
        self,
        message: str = "",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)


# ---------------------------------------------------------------------------
# Store exceptions
# ---------------------------------------------------------------------------


class TrustPlaneStoreError(TrustPlaneError):
    """Base exception for store-related errors.

    All store backend failures MUST raise a subclass of this exception.
    Methods MUST NOT return None or False to signal errors
    (Store Security Contract requirement 6: NO_SILENT_FAILURES).
    """


class RecordNotFoundError(TrustPlaneStoreError, KeyError):
    """Raised when a requested record does not exist in the store."""

    def __init__(
        self,
        record_type: str,
        record_id: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.record_type = record_type
        self.record_id = record_id
        super().__init__(
            f"{record_type} not found: {record_id}",
            details=details or {"record_type": record_type, "record_id": record_id},
        )

    def __str__(self) -> str:
        return f"{self.record_type} not found: {self.record_id}"


class SchemaTooNewError(TrustPlaneStoreError):
    """Raised when the database schema is newer than the current code supports.

    This occurs when a database was created or migrated by a newer version
    of trust-plane. The user must upgrade trust-plane to open this database.
    """

    def __init__(
        self,
        db_version: int,
        current_version: int,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.db_version = db_version
        self.current_version = current_version
        super().__init__(
            f"Database schema version {db_version} is newer than this "
            f"trust-plane version supports ({current_version}). "
            f"Upgrade trust-plane.",
            details=details
            or {"db_version": db_version, "current_version": current_version},
        )


class SchemaMigrationError(TrustPlaneStoreError):
    """Raised when a schema migration fails.

    The failed migration is rolled back. The database is left at the
    version before the failed migration.
    """

    def __init__(
        self,
        target_version: int,
        reason: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.target_version = target_version
        self.reason = reason
        super().__init__(
            f"Migration to schema version {target_version} failed: {reason}",
            details=details or {"target_version": target_version, "reason": reason},
        )


class StoreConnectionError(TrustPlaneStoreError):
    """Raised when a store backend cannot connect to the database."""


class StoreQueryError(TrustPlaneStoreError):
    """Raised when a store query fails (syntax, constraint violation, etc.)."""


class StoreTransactionError(TrustPlaneStoreError):
    """Raised when a store transaction fails to commit or roll back."""


# ---------------------------------------------------------------------------
# Crypto / decryption
# ---------------------------------------------------------------------------


class TrustDecryptionError(TrustPlaneError):
    """Raised when decryption of a stored record fails.

    Common causes: wrong key, truncated ciphertext, tampered data.
    """


# ---------------------------------------------------------------------------
# Key manager exceptions
# ---------------------------------------------------------------------------


class KeyManagerError(TrustPlaneError):
    """Base exception for key manager errors.

    All key manager implementations MUST raise only subclasses of this
    exception for operational errors. Provider-specific exceptions
    (botocore, azure, hvac) MUST be caught and wrapped.

    Attributes:
        provider: Name of the key management provider (e.g. "aws_kms").
        key_id: The key identifier involved, if known.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str = "unknown",
        key_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.provider = provider
        self.key_id = key_id
        prefix = f"[{provider}]"
        if key_id:
            prefix += f" key={key_id}"
        super().__init__(
            f"{prefix} {message}",
            details=details or {"provider": provider, "key_id": key_id},
        )


class KeyNotFoundError(KeyManagerError):
    """Raised when a requested key does not exist in the provider."""


class KeyExpiredError(KeyManagerError):
    """Raised when a key exists but has expired or been disabled."""


class SigningError(KeyManagerError):
    """Raised when a signing operation fails."""


class VerificationError(KeyManagerError):
    """Raised when a signature verification operation fails."""


# ---------------------------------------------------------------------------
# Constraint / budget exceptions
# ---------------------------------------------------------------------------


class ConstraintViolationError(TrustPlaneError):
    """Raised when an action violates the constraint envelope."""


class BudgetExhaustedError(ConstraintViolationError):
    """Raised when an action would exceed the financial budget.

    Attributes:
        session_cost: Total cost accumulated so far in the session.
        budget_limit: The max_cost_per_session limit.
        action_cost: The cost of the action that caused the breach.
    """

    def __init__(
        self,
        message: str,
        *,
        session_cost: float = 0.0,
        budget_limit: float | None = None,
        action_cost: float = 0.0,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.session_cost = session_cost
        self.budget_limit = budget_limit
        self.action_cost = action_cost
        super().__init__(
            message,
            details=details
            or {
                "session_cost": session_cost,
                "budget_limit": budget_limit,
                "action_cost": action_cost,
            },
        )


# ---------------------------------------------------------------------------
# Identity / OIDC exceptions
# ---------------------------------------------------------------------------


class IdentityError(TrustPlaneError):
    """Raised for identity/OIDC-specific errors."""


class TokenVerificationError(IdentityError):
    """Raised when a JWT token fails verification."""


class JWKSError(IdentityError):
    """Raised when JWKS discovery or key retrieval fails."""


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


class RBACError(TrustPlaneError):
    """Raised for RBAC-specific errors."""


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------


class ArchiveError(TrustPlaneError):
    """Raised when an archive operation fails."""


# ---------------------------------------------------------------------------
# SIEM
# ---------------------------------------------------------------------------


class TLSSyslogError(TrustPlaneError):
    """Raised when TLS syslog connection or handshake fails.

    Security tool MUST NOT silently degrade to plaintext.
    """


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------


# Re-exported from shared location to avoid circular imports.
# _locking.py defines the class; plane.exceptions re-exports for backward compat.
from kailash.trust._locking import LockTimeoutError as LockTimeoutError  # noqa: F401
