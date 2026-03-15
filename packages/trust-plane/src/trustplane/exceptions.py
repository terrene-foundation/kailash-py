# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Trust-plane exception hierarchy.

All trust-plane exceptions inherit from TrustPlaneError so callers
can catch the entire family with a single except clause.
"""

import logging

logger = logging.getLogger(__name__)

__all__ = [
    "TrustPlaneError",
    "TrustPlaneStoreError",
    "TrustDecryptionError",
    "RecordNotFoundError",
    "SchemaTooNewError",
    "SchemaMigrationError",
    "KeyManagerError",
    "KeyNotFoundError",
    "KeyExpiredError",
    "SigningError",
    "VerificationError",
    "StoreConnectionError",
    "StoreQueryError",
    "StoreTransactionError",
]


class TrustPlaneError(Exception):
    """Base exception for all trust-plane errors."""


class TrustPlaneStoreError(TrustPlaneError):
    """Base exception for store-related errors.

    All store backend failures MUST raise a subclass of this exception.
    Methods MUST NOT return None or False to signal errors
    (Store Security Contract requirement 6: NO_SILENT_FAILURES).
    """


class TrustDecryptionError(TrustPlaneError):
    """Raised when decryption of a stored record fails.

    Common causes: wrong key, truncated ciphertext, tampered data.
    """


class RecordNotFoundError(TrustPlaneStoreError):
    """Raised when a requested record does not exist in the store."""

    def __init__(self, record_type: str, record_id: str) -> None:
        self.record_type = record_type
        self.record_id = record_id
        super().__init__(f"{record_type} not found: {record_id}")


class SchemaTooNewError(TrustPlaneStoreError):
    """Raised when the database schema is newer than the current code supports.

    This occurs when a database was created or migrated by a newer version
    of trust-plane. The user must upgrade trust-plane to open this database.
    """

    def __init__(self, db_version: int, current_version: int) -> None:
        self.db_version = db_version
        self.current_version = current_version
        super().__init__(
            f"Database schema version {db_version} is newer than this "
            f"trust-plane version supports ({current_version}). "
            f"Upgrade trust-plane."
        )


class SchemaMigrationError(TrustPlaneStoreError):
    """Raised when a schema migration fails.

    The failed migration is rolled back. The database is left at the
    version before the failed migration.
    """

    def __init__(self, target_version: int, reason: str) -> None:
        self.target_version = target_version
        self.reason = reason
        super().__init__(
            f"Migration to schema version {target_version} failed: {reason}"
        )


class StoreConnectionError(TrustPlaneStoreError):
    """Raised when a store backend cannot connect to the database."""


class StoreQueryError(TrustPlaneStoreError):
    """Raised when a store query fails (syntax, constraint violation, etc.)."""


class StoreTransactionError(TrustPlaneStoreError):
    """Raised when a store transaction fails to commit or roll back."""


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
    ) -> None:
        self.provider = provider
        self.key_id = key_id
        prefix = f"[{provider}]"
        if key_id:
            prefix += f" key={key_id}"
        super().__init__(f"{prefix} {message}")


class KeyNotFoundError(KeyManagerError):
    """Raised when a requested key does not exist in the provider."""


class KeyExpiredError(KeyManagerError):
    """Raised when a key exists but has expired or been disabled."""


class SigningError(KeyManagerError):
    """Raised when a signing operation fails."""


class VerificationError(KeyManagerError):
    """Raised when a signature verification operation fails."""
