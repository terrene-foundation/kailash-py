# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
CARE-011: Multi-Signature Genesis Records for EATP Trust Module.

Provides M-of-N multi-signature support for critical agent establishment.
Example: 3-of-5 board members must approve before an AI agent receives
financial authority.

Key Components:
- MultiSigPolicy: Defines M-of-N signing requirements
- PendingMultiSig: Tracks ongoing multi-signature operations
- MultiSigManager: Orchestrates the multi-signature workflow
- verify_multi_sig: Verifies combined multi-signatures

Example:
    from kailash.trust.signing.multi_sig import (
        MultiSigPolicy,
        MultiSigManager,
        verify_multi_sig,
    )
    from kailash.trust.key_manager import InMemoryKeyManager

    # Create key manager and generate keys for signers
    key_manager = InMemoryKeyManager()
    signer_keys = {}
    for signer_id in ["alice", "bob", "carol", "dave", "eve"]:
        _, public_key = await key_manager.generate_keypair(signer_id)
        signer_keys[signer_id] = public_key

    # Define 3-of-5 policy
    policy = MultiSigPolicy(
        required_signatures=3,
        total_signers=5,
        signer_public_keys=signer_keys,
        expiry_hours=24,
    )

    # Create manager and initiate signing
    manager = MultiSigManager(key_manager=key_manager)
    pending = manager.initiate_genesis_signing(genesis_payload, policy)

    # Collect signatures
    for signer_id in ["alice", "bob", "carol"]:
        signature = await key_manager.sign(genesis_payload, signer_id)
        manager.add_signature(pending.operation_id, signer_id, signature)

    # Complete when quorum reached
    combined_sig = manager.complete_genesis_signing(pending.operation_id)

    # Later verification
    is_valid = verify_multi_sig(genesis_payload, combined_sig, policy, key_manager)
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from kailash.trust.signing.crypto import serialize_for_signing, verify_signature
from kailash.trust.key_manager import KeyManagerInterface

logger = logging.getLogger(__name__)


class MultiSigError(Exception):
    """Base exception for multi-signature operations."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message


class InsufficientSignaturesError(MultiSigError):
    """Raised when attempting to complete signing without enough signatures."""

    def __init__(self, current: int, required: int, operation_id: str):
        super().__init__(
            f"Insufficient signatures: {current}/{required}",
            details={
                "current": current,
                "required": required,
                "operation_id": operation_id,
            },
        )
        self.current = current
        self.required = required
        self.operation_id = operation_id


class SigningOperationExpiredError(MultiSigError):
    """Raised when a signing operation has expired."""

    def __init__(self, operation_id: str, expired_at: datetime):
        super().__init__(
            f"Signing operation expired at {expired_at.isoformat()}",
            details={
                "operation_id": operation_id,
                "expired_at": expired_at.isoformat(),
            },
        )
        self.operation_id = operation_id
        self.expired_at = expired_at


class UnauthorizedSignerError(MultiSigError):
    """Raised when a signer is not authorized for an operation."""

    def __init__(self, signer_id: str, operation_id: str):
        super().__init__(
            f"Signer not authorized: {signer_id}",
            details={
                "signer_id": signer_id,
                "operation_id": operation_id,
            },
        )
        self.signer_id = signer_id
        self.operation_id = operation_id


class DuplicateSignatureError(MultiSigError):
    """Raised when a signer attempts to sign more than once."""

    def __init__(self, signer_id: str, operation_id: str):
        super().__init__(
            f"Duplicate signature from signer: {signer_id}",
            details={
                "signer_id": signer_id,
                "operation_id": operation_id,
            },
        )
        self.signer_id = signer_id
        self.operation_id = operation_id


class OperationNotFoundError(MultiSigError):
    """Raised when a signing operation is not found."""

    def __init__(self, operation_id: str):
        super().__init__(
            f"Signing operation not found: {operation_id}",
            details={"operation_id": operation_id},
        )
        self.operation_id = operation_id


@dataclass(frozen=True)
class MultiSigPolicy:
    """
    Policy defining M-of-N multi-signature requirements.

    Attributes:
        required_signatures: Number of signatures required (M)
        total_signers: Total number of authorized signers (N)
        signer_public_keys: Mapping of signer_id to public key (base64)
        expiry_hours: Hours until pending operations expire (default: 24)
    """

    required_signatures: int
    total_signers: int
    signer_public_keys: Dict[str, str]
    expiry_hours: int = 24

    def __post_init__(self):
        """Validate policy parameters."""
        if self.required_signatures > self.total_signers:
            raise ValueError(
                f"required_signatures ({self.required_signatures}) cannot exceed total_signers ({self.total_signers})"
            )
        if self.required_signatures < 1:
            raise ValueError("required_signatures must be at least 1")
        if len(self.signer_public_keys) != self.total_signers:
            raise ValueError(
                f"Number of signer_public_keys ({len(self.signer_public_keys)}) "
                f"must equal total_signers ({self.total_signers})"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize policy to dictionary."""
        return {
            "required_signatures": self.required_signatures,
            "total_signers": self.total_signers,
            "signer_public_keys": self.signer_public_keys,
            "expiry_hours": self.expiry_hours,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MultiSigPolicy":
        """Deserialize policy from dictionary."""
        return cls(
            required_signatures=data["required_signatures"],
            total_signers=data["total_signers"],
            signer_public_keys=data["signer_public_keys"],
            expiry_hours=data.get("expiry_hours", 24),
        )


@dataclass
class PendingMultiSig:
    """
    Represents a pending multi-signature operation.

    Tracks the state of an ongoing signing ceremony, including
    collected signatures and expiration.

    Attributes:
        operation_id: Unique identifier for this operation
        payload: Serialized genesis payload to be signed
        policy: MultiSigPolicy defining signing requirements
        signatures: Collected signatures (signer_id -> signature)
        created_at: When the operation was initiated
        expires_at: When the operation expires
    """

    operation_id: str
    payload: str
    policy: MultiSigPolicy
    signatures: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None

    def __post_init__(self):
        """Calculate expiry time from policy if not set."""
        if self.expires_at is None:
            self.expires_at = self.created_at + timedelta(hours=self.policy.expiry_hours)

    def is_complete(self) -> bool:
        """Check if enough signatures have been collected."""
        return len(self.signatures) >= self.policy.required_signatures

    def is_expired(self) -> bool:
        """Check if the operation has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def remaining_signatures(self) -> int:
        """Get number of signatures still needed."""
        return max(0, self.policy.required_signatures - len(self.signatures))

    def pending_signers(self) -> Set[str]:
        """Get set of signers who haven't signed yet."""
        all_signers = set(self.policy.signer_public_keys.keys())
        signed = set(self.signatures.keys())
        return all_signers - signed

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "operation_id": self.operation_id,
            "payload": self.payload,
            "policy": self.policy.to_dict(),
            "signatures": self.signatures,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PendingMultiSig":
        """Deserialize from dictionary."""
        return cls(
            operation_id=data["operation_id"],
            payload=data["payload"],
            policy=MultiSigPolicy.from_dict(data["policy"]),
            signatures=data.get("signatures", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=(datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None),
        )


class MultiSigManager:
    """
    Manages multi-signature genesis signing ceremonies.

    Orchestrates the collection of M-of-N signatures required
    for critical agent establishment operations.

    Attributes:
        key_manager: Optional key manager for cryptographic verification
    """

    def __init__(self, key_manager: Optional[KeyManagerInterface] = None):
        """
        Initialize the multi-signature manager.

        Args:
            key_manager: Optional key manager for signature verification.
                        If None, signatures are collected but not verified.
        """
        self._key_manager = key_manager
        self._pending: Dict[str, PendingMultiSig] = {}

    def initiate_genesis_signing(
        self,
        genesis_payload: str,
        policy: MultiSigPolicy,
    ) -> PendingMultiSig:
        """
        Initiate a new multi-signature genesis signing operation.

        Args:
            genesis_payload: Serialized genesis record payload to be signed
            policy: MultiSigPolicy defining signing requirements

        Returns:
            PendingMultiSig tracking the signing operation
        """
        # Generate unique operation ID
        operation_id = f"msig-{uuid.uuid4().hex[:12]}"

        pending = PendingMultiSig(
            operation_id=operation_id,
            payload=genesis_payload,
            policy=policy,
        )

        self._pending[operation_id] = pending
        return pending

    def add_signature(
        self,
        operation_id: str,
        signer_id: str,
        signature: str,
    ) -> PendingMultiSig:
        """
        Add a signature to a pending operation.

        Args:
            operation_id: ID of the pending operation
            signer_id: ID of the signer
            signature: Base64-encoded signature

        Returns:
            Updated PendingMultiSig

        Raises:
            OperationNotFoundError: If operation doesn't exist
            SigningOperationExpiredError: If operation has expired
            UnauthorizedSignerError: If signer is not in policy
            DuplicateSignatureError: If signer already signed
            ValueError: If signature verification fails
        """
        # Check operation exists
        if operation_id not in self._pending:
            raise OperationNotFoundError(operation_id)

        pending = self._pending[operation_id]

        # Check not expired
        if pending.is_expired():
            raise SigningOperationExpiredError(
                operation_id,
                pending.expires_at,  # type: ignore
            )

        # Check signer is authorized
        if signer_id not in pending.policy.signer_public_keys:
            raise UnauthorizedSignerError(signer_id, operation_id)

        # Check for duplicate signature
        if signer_id in pending.signatures:
            raise DuplicateSignatureError(signer_id, operation_id)

        # Verify signature if key manager available
        if self._key_manager is not None:
            public_key = pending.policy.signer_public_keys[signer_id]
            # Use synchronous verification (key_manager.verify is async but
            # verify_signature from crypto module is sync)
            try:
                is_valid = verify_signature(pending.payload, signature, public_key)
                if not is_valid:
                    raise ValueError(f"Invalid signature from signer {signer_id}: signature verification failed")
            except Exception as e:
                # Re-raise as ValueError for consistent error handling
                raise ValueError(f"Invalid signature from signer {signer_id}: {e}") from e

        # Store signature
        pending.signatures[signer_id] = signature

        return pending

    def complete_genesis_signing(self, operation_id: str) -> str:
        """
        Complete a multi-signature operation and return combined signature.

        Args:
            operation_id: ID of the pending operation

        Returns:
            JSON string containing combined multi-signature

        Raises:
            OperationNotFoundError: If operation doesn't exist
            InsufficientSignaturesError: If quorum not met
        """
        # Check operation exists
        if operation_id not in self._pending:
            raise OperationNotFoundError(operation_id)

        pending = self._pending[operation_id]

        # Check quorum
        current = len(pending.signatures)
        required = pending.policy.required_signatures
        if current < required:
            raise InsufficientSignaturesError(current, required, operation_id)

        # Create combined signature
        combined = {
            "type": "multisig",
            "threshold": f"{required}/{pending.policy.total_signers}",
            "signatures": pending.signatures,
        }

        # Remove from pending
        del self._pending[operation_id]

        return json.dumps(combined, sort_keys=True, separators=(",", ":"))

    def get_pending(self, operation_id: str) -> Optional[PendingMultiSig]:
        """
        Get a pending operation by ID.

        Args:
            operation_id: ID of the operation

        Returns:
            PendingMultiSig if found, None otherwise
        """
        return self._pending.get(operation_id)

    def list_pending(self) -> List[PendingMultiSig]:
        """
        List all pending operations.

        Returns:
            List of all pending multi-signature operations
        """
        return list(self._pending.values())

    def cancel(self, operation_id: str) -> bool:
        """
        Cancel a pending operation.

        Args:
            operation_id: ID of the operation to cancel

        Returns:
            True if operation was cancelled, False if not found
        """
        if operation_id in self._pending:
            del self._pending[operation_id]
            return True
        return False

    def cleanup_expired(self) -> int:
        """
        Remove all expired pending operations.

        Returns:
            Number of operations removed
        """
        expired_ids = [op_id for op_id, pending in self._pending.items() if pending.is_expired()]

        for op_id in expired_ids:
            del self._pending[op_id]

        return len(expired_ids)


def verify_multi_sig(
    payload: str,
    combined_signature: str,
    policy: MultiSigPolicy,
    key_manager: Optional[KeyManagerInterface] = None,
    skip_verification: bool = False,
) -> bool:
    """
    Verify a combined multi-signature against a payload.

    Args:
        payload: Original payload that was signed
        combined_signature: JSON string of combined signature
        policy: MultiSigPolicy to verify against
        key_manager: Optional key manager for cryptographic verification
        skip_verification: If True and key_manager is None, returns True with
            warning log. Callers must explicitly opt-in to skip verification.
            This should ONLY be used in testing scenarios.

    Returns:
        True if M valid signatures are found, False otherwise

    Security Note:
        CARE-050: This function implements fail-closed behavior. When key_manager
        is None and skip_verification is False (default), the function returns
        False and logs a CRITICAL warning. This prevents silent bypass of
        signature verification in production code.

        To explicitly skip verification for testing, callers must set
        skip_verification=True, which will log a warning but return True.
    """
    # CARE-050: Fail-closed behavior - do not silently bypass verification
    if key_manager is None:
        if skip_verification:
            # Explicit opt-in for testing - warn but allow
            logger.warning(
                "CARE-050: verify_multi_sig called with key_manager=None and "
                "skip_verification=True. Signature verification is being skipped. "
                "This should ONLY be used in testing scenarios."
            )
            return True
        else:
            # Fail-closed: reject verification when no key_manager provided
            logger.critical(
                "CARE-050: verify_multi_sig called with key_manager=None. "
                "Signature verification cannot be performed without a key manager. "
                "Returning False (fail-closed). If this is intentional for testing, "
                "set skip_verification=True explicitly."
            )
            return False

    try:
        combined = json.loads(combined_signature)
    except json.JSONDecodeError:
        return False

    # Verify structure
    if combined.get("type") != "multisig":
        return False

    signatures = combined.get("signatures", {})
    if not isinstance(signatures, dict):
        return False

    # Count valid signatures
    valid_count = 0
    for signer_id, signature in signatures.items():
        # Verify signer is in policy
        if signer_id not in policy.signer_public_keys:
            continue

        public_key = policy.signer_public_keys[signer_id]

        # Verify signature
        try:
            if verify_signature(payload, signature, public_key):
                valid_count += 1
        except Exception:
            # Invalid signature, skip
            continue

    return valid_count >= policy.required_signatures


def create_genesis_payload(genesis_data: Dict[str, Any]) -> str:
    """
    Create a serialized genesis payload for signing.

    This helper function ensures consistent serialization of genesis
    data for multi-signature operations.

    Args:
        genesis_data: Genesis record data to serialize

    Returns:
        Deterministically serialized JSON string
    """
    return serialize_for_signing(genesis_data)
