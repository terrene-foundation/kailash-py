# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
CARE-005: HSM/KMS Integration for EATP Trust Module.

Provides an abstracted KeyManager interface supporting pluggable backends:
- InMemoryKeyManager: For development and testing
- AWSKMSKeyManager: Stub for production AWS KMS integration

The KeyManagerInterface is a superset of the original TrustKeyManager,
maintaining backward compatibility while enabling enterprise key management.

Example:
    from eatp.key_manager import InMemoryKeyManager, KeyMetadata

    # Create key manager
    key_manager = InMemoryKeyManager()

    # Generate a keypair
    private_ref, public_key = await key_manager.generate_keypair("agent-001")

    # Sign a payload
    signature = await key_manager.sign("payload", "agent-001")

    # Verify signature
    is_valid = await key_manager.verify("payload", signature, public_key)

    # Key rotation
    new_private_ref, new_public_key = await key_manager.rotate_key("agent-001")

    # Key revocation
    await key_manager.revoke_key("agent-001")
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from eatp.crypto import generate_keypair, sign, verify_signature
from eatp.exceptions import TrustError


class KeyManagerError(TrustError):
    """
    Exception for key management operations.

    Raised when:
    - Key not found
    - Key already exists
    - Key revoked
    - HSM/KMS operation fails
    """

    def __init__(
        self,
        message: str,
        key_id: Optional[str] = None,
        operation: Optional[str] = None,
    ):
        super().__init__(
            message,
            details={
                "key_id": key_id,
                "operation": operation,
            },
        )
        self.key_id = key_id
        self.operation = operation


@dataclass
class KeyMetadata:
    """
    Metadata for a cryptographic key.

    Attributes:
        key_id: Unique identifier for the key
        algorithm: Cryptographic algorithm (default: Ed25519)
        created_at: When the key was created
        expires_at: When the key expires (None = no expiry)
        is_hardware_backed: Whether the key is stored in HSM
        hsm_slot: HSM slot identifier (if hardware backed)
        is_revoked: Whether the key has been revoked
        revoked_at: When the key was revoked
        rotated_from: Key ID this was rotated from (if any)
    """

    key_id: str
    algorithm: str = "Ed25519"
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_hardware_backed: bool = False
    hsm_slot: Optional[str] = None
    is_revoked: bool = False
    revoked_at: Optional[datetime] = None
    rotated_from: Optional[str] = None

    def __post_init__(self):
        """Set default created_at if not provided."""
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

    def is_active(self) -> bool:
        """Check if key is currently active (not expired and not revoked)."""
        if self.is_revoked:
            return False
        if self.expires_at is not None:
            return datetime.now(timezone.utc) < self.expires_at
        return True


class KeyManagerInterface(ABC):
    """
    Abstract interface for cryptographic key management.

    Provides a pluggable backend for key operations, enabling:
    - In-memory storage for development/testing
    - AWS KMS integration for production
    - HSM integration for high-security environments

    All methods are async to support network-based backends (KMS, HSM).
    """

    @abstractmethod
    async def generate_keypair(self, key_id: str) -> Tuple[str, str]:
        """
        Generate a new Ed25519 keypair.

        Args:
            key_id: Unique identifier for the key

        Returns:
            Tuple of (private_key_reference, public_key)
            - private_key_reference: Handle to private key (actual key or KMS ARN)
            - public_key: Base64-encoded public key

        Raises:
            KeyManagerError: If key_id already exists or generation fails
        """
        pass

    @abstractmethod
    async def sign(self, payload: str, key_id: str) -> str:
        """
        Sign a payload using the specified key.

        Args:
            payload: Data to sign
            key_id: Key identifier to use for signing

        Returns:
            Base64-encoded signature

        Raises:
            KeyManagerError: If key not found or revoked
        """
        pass

    @abstractmethod
    async def verify(self, payload: str, signature: str, public_key: str) -> bool:
        """
        Verify a signature against a payload.

        Args:
            payload: Original data that was signed
            signature: Base64-encoded signature to verify
            public_key: Base64-encoded public key

        Returns:
            True if signature is valid, False otherwise
        """
        pass

    @abstractmethod
    async def rotate_key(self, key_id: str) -> Tuple[str, str]:
        """
        Rotate a key, generating a new keypair.

        The old key is retained (with metadata indicating rotation)
        for a grace period to allow verification of existing signatures.

        Args:
            key_id: Key identifier to rotate

        Returns:
            Tuple of (new_private_key_reference, new_public_key)

        Raises:
            KeyManagerError: If key not found
        """
        pass

    @abstractmethod
    async def revoke_key(self, key_id: str) -> None:
        """
        Revoke a key, preventing further signing operations.

        Revoked keys cannot be used for signing but may still be used
        for verification of historical signatures.

        Args:
            key_id: Key identifier to revoke

        Raises:
            KeyManagerError: If key not found
        """
        pass

    @abstractmethod
    async def get_key_metadata(self, key_id: str) -> Optional[KeyMetadata]:
        """
        Get metadata for a key.

        Args:
            key_id: Key identifier

        Returns:
            KeyMetadata if key exists, None otherwise
        """
        pass

    @abstractmethod
    async def list_keys(self, active_only: bool = True) -> List[KeyMetadata]:
        """
        List all keys managed by this key manager.

        Args:
            active_only: If True, only return non-revoked, non-expired keys

        Returns:
            List of KeyMetadata for matching keys
        """
        pass


class InMemoryKeyManager(KeyManagerInterface):
    """
    In-memory implementation of KeyManagerInterface.

    Suitable for development, testing, and non-production environments.
    Uses the eatp.crypto module for actual cryptographic operations.

    Key storage is in-memory and will be lost when the process exits.
    For production use, consider AWSKMSKeyManager or a persistent backend.

    SECURITY WARNING:
        This class stores private keys in memory. While protective measures
        are in place to prevent accidental exposure via repr(), str(),
        and serialization (pickle), the keys ARE accessible via direct
        attribute access (e.g., instance._keys). This is intentional to
        allow the class to function, but means you should:
        - Never log or print the key manager instance
        - Never serialize the key manager
        - Never expose the key manager to untrusted code
        - Use AWSKMSKeyManager for production environments

    Example:
        key_manager = InMemoryKeyManager()

        # Generate and use keys
        private_ref, public_key = await key_manager.generate_keypair("my-key")
        signature = await key_manager.sign("data", "my-key")
        is_valid = await key_manager.verify("data", signature, public_key)
    """

    def __init__(self):
        """Initialize the in-memory key manager."""
        # key_id -> private_key (base64)
        self._keys: Dict[str, str] = {}
        # key_id -> public_key (base64)
        self._public_keys: Dict[str, str] = {}
        # key_id -> KeyMetadata
        self._metadata: Dict[str, KeyMetadata] = {}
        # Rotated keys: old_key_id -> new_key_id
        self._rotated_to: Dict[str, str] = {}
        # Revoked keys kept for verification grace period
        self._revoked_keys: Dict[str, str] = {}

    async def generate_keypair(self, key_id: str) -> Tuple[str, str]:
        """
        Generate a new Ed25519 keypair.

        Args:
            key_id: Unique identifier for the key

        Returns:
            Tuple of (private_key, public_key) both base64-encoded

        Raises:
            KeyManagerError: If key_id already exists
        """
        if key_id in self._keys:
            raise KeyManagerError(
                f"Key already exists: {key_id}",
                key_id=key_id,
                operation="generate_keypair",
            )

        private_key, public_key = generate_keypair()

        self._keys[key_id] = private_key
        self._public_keys[key_id] = public_key
        self._metadata[key_id] = KeyMetadata(
            key_id=key_id,
            algorithm="Ed25519",
            created_at=datetime.now(timezone.utc),
            is_hardware_backed=False,
        )

        return private_key, public_key

    async def sign(self, payload: str, key_id: str) -> str:
        """
        Sign a payload using the specified key.

        Args:
            payload: Data to sign
            key_id: Key identifier to use for signing

        Returns:
            Base64-encoded signature

        Raises:
            KeyManagerError: If key not found or revoked
        """
        # Check if key was rotated
        if key_id in self._rotated_to:
            key_id = self._rotated_to[key_id]

        # Check if key exists
        if key_id not in self._keys:
            raise KeyManagerError(
                f"Key not found: {key_id}",
                key_id=key_id,
                operation="sign",
            )

        # Check if key is revoked
        metadata = self._metadata.get(key_id)
        if metadata and metadata.is_revoked:
            raise KeyManagerError(
                f"Key is revoked: {key_id}",
                key_id=key_id,
                operation="sign",
            )

        private_key = self._keys[key_id]
        return sign(payload, private_key)

    async def verify(self, payload: str, signature: str, public_key: str) -> bool:
        """
        Verify a signature against a payload.

        Args:
            payload: Original data that was signed
            signature: Base64-encoded signature to verify
            public_key: Base64-encoded public key

        Returns:
            True if signature is valid, False otherwise
        """
        return verify_signature(payload, signature, public_key)

    async def rotate_key(self, key_id: str) -> Tuple[str, str]:
        """
        Rotate a key, generating a new keypair.

        The old key is retained for verification of existing signatures.
        The old key's metadata is updated to indicate rotation.

        Args:
            key_id: Key identifier to rotate

        Returns:
            Tuple of (new_private_key, new_public_key)

        Raises:
            KeyManagerError: If key not found
        """
        if key_id not in self._keys:
            raise KeyManagerError(
                f"Key not found: {key_id}",
                key_id=key_id,
                operation="rotate_key",
            )

        # Generate new keypair
        new_private_key, new_public_key = generate_keypair()

        # Preserve old key for verification grace period
        old_key_id = f"{key_id}:rotated:{datetime.now(timezone.utc).isoformat()}"
        self._revoked_keys[old_key_id] = self._keys[key_id]

        # Update the key
        self._keys[key_id] = new_private_key
        self._public_keys[key_id] = new_public_key

        # Update metadata
        old_metadata = self._metadata.get(key_id)
        self._metadata[key_id] = KeyMetadata(
            key_id=key_id,
            algorithm="Ed25519",
            created_at=datetime.now(timezone.utc),
            is_hardware_backed=False,
            rotated_from=old_key_id if old_metadata else None,
        )

        # Track rotation
        self._rotated_to[old_key_id] = key_id

        return new_private_key, new_public_key

    async def revoke_key(self, key_id: str) -> None:
        """
        Revoke a key, preventing further signing operations.

        The key is kept for potential verification of historical signatures.

        Args:
            key_id: Key identifier to revoke

        Raises:
            KeyManagerError: If key not found
        """
        if key_id not in self._keys:
            raise KeyManagerError(
                f"Key not found: {key_id}",
                key_id=key_id,
                operation="revoke_key",
            )

        # Update metadata to mark as revoked
        metadata = self._metadata.get(key_id)
        if metadata:
            metadata.is_revoked = True
            metadata.revoked_at = datetime.now(timezone.utc)
        else:
            self._metadata[key_id] = KeyMetadata(
                key_id=key_id,
                is_revoked=True,
                revoked_at=datetime.now(timezone.utc),
            )

    async def get_key_metadata(self, key_id: str) -> Optional[KeyMetadata]:
        """
        Get metadata for a key.

        Args:
            key_id: Key identifier

        Returns:
            KeyMetadata if key exists, None otherwise
        """
        return self._metadata.get(key_id)

    async def list_keys(self, active_only: bool = True) -> List[KeyMetadata]:
        """
        List all keys managed by this key manager.

        Args:
            active_only: If True, only return non-revoked, non-expired keys

        Returns:
            List of KeyMetadata for matching keys
        """
        result = []
        for metadata in self._metadata.values():
            if active_only:
                if metadata.is_active():
                    result.append(metadata)
            else:
                result.append(metadata)
        return result

    # Additional helper methods for backward compatibility

    def register_key(self, key_id: str, private_key: str) -> None:
        """
        Register an existing private key (for backward compatibility).

        This method provides compatibility with the original TrustKeyManager.

        Args:
            key_id: Identifier for the key
            private_key: Base64-encoded private key
        """
        self._keys[key_id] = private_key
        self._metadata[key_id] = KeyMetadata(
            key_id=key_id,
            algorithm="Ed25519",
            created_at=datetime.now(timezone.utc),
        )

    def get_key(self, key_id: str) -> Optional[str]:
        """
        Get a private key by ID (for backward compatibility).

        Args:
            key_id: Identifier for the key

        Returns:
            The private key or None if not found
        """
        return self._keys.get(key_id)

    def get_public_key(self, key_id: str) -> Optional[str]:
        """
        Get a public key by ID.

        Args:
            key_id: Identifier for the key

        Returns:
            The public key or None if not found
        """
        return self._public_keys.get(key_id)

    # Security methods to prevent accidental key exposure

    def __repr__(self) -> str:
        """
        Return a safe representation without exposing key material.

        Returns:
            String representation showing key count but not key values
        """
        return f"InMemoryKeyManager(keys=<{len(self._keys)} keys>)"

    def __str__(self) -> str:
        """
        Return a safe string representation without exposing key material.

        Returns:
            String representation showing key count but not key values
        """
        return f"InMemoryKeyManager(keys=<{len(self._keys)} keys>)"

    def __reduce__(self):
        """
        Prevent pickle serialization to protect private keys.

        Raises:
            TypeError: Always raised to prevent serialization
        """
        raise TypeError(
            "InMemoryKeyManager cannot be pickled to protect private key material. "
            "Use a persistent backend like AWSKMSKeyManager for serializable key management."
        )

    def __reduce_ex__(self, protocol: int):
        """
        Prevent pickle serialization (all protocols) to protect private keys.

        Args:
            protocol: Pickle protocol version

        Raises:
            TypeError: Always raised to prevent serialization
        """
        raise TypeError(
            "InMemoryKeyManager cannot be pickled to protect private key material. "
            "Use a persistent backend like AWSKMSKeyManager for serializable key management."
        )

    def __getstate__(self):
        """
        Prevent state serialization to protect private keys.

        Raises:
            TypeError: Always raised to prevent serialization
        """
        raise TypeError(
            "InMemoryKeyManager state cannot be serialized to protect private key material. "
            "Use a persistent backend like AWSKMSKeyManager for serializable key management."
        )

    def __setstate__(self, state):
        """
        Prevent state deserialization.

        Args:
            state: State dict (unused)

        Raises:
            TypeError: Always raised to prevent deserialization
        """
        raise TypeError(
            "InMemoryKeyManager cannot be deserialized. "
            "Use a persistent backend like AWSKMSKeyManager for serializable key management."
        )


class AWSKMSKeyManager(KeyManagerInterface):
    """
    AWS KMS implementation of KeyManagerInterface (STUB).

    This is a stub implementation that raises NotImplementedError for all
    operations. It documents the AWS KMS APIs that would be used in a
    production implementation.

    Production implementation would use:
    - boto3.client('kms') for KMS operations
    - CreateKey for key generation
    - Sign/Verify for cryptographic operations
    - ScheduleKeyDeletion for revocation
    - GetKeyPolicy/PutKeyPolicy for access control

    Example (future implementation):
        import boto3

        kms_client = boto3.client('kms', region_name='us-east-1')
        key_manager = AWSKMSKeyManager(kms_client)

        # This would create a KMS key
        key_ref, public_key = await key_manager.generate_keypair("agent-001")

        # This would use KMS Sign API
        signature = await key_manager.sign("data", "agent-001")
    """

    def __init__(self, kms_client: Optional[Any] = None):
        """
        Initialize AWS KMS key manager.

        Args:
            kms_client: boto3 KMS client (optional, for future implementation)
                       If None, operations will raise NotImplementedError.

        AWS KMS APIs that would be used:
        - kms.create_key(): Create asymmetric signing key
        - kms.sign(): Sign data with CMK
        - kms.verify(): Verify signature
        - kms.get_public_key(): Retrieve public key
        - kms.schedule_key_deletion(): Revoke/delete key
        - kms.describe_key(): Get key metadata
        - kms.list_keys(): List available keys
        """
        self._kms_client = kms_client
        # key_id -> KMS key ARN
        self._key_arns: Dict[str, str] = {}
        # key_id -> KeyMetadata
        self._metadata: Dict[str, KeyMetadata] = {}

    async def generate_keypair(self, key_id: str) -> Tuple[str, str]:
        """
        Generate a new asymmetric key pair in AWS KMS.

        Would use kms.create_key() with:
        - KeyUsage: 'SIGN_VERIFY'
        - KeySpec: 'ECC_NIST_P256' (Ed25519 not supported, P-256 as alternative)
        - Origin: 'AWS_KMS'

        Args:
            key_id: Unique identifier for the key

        Returns:
            Tuple of (kms_key_arn, public_key_pem)

        Raises:
            NotImplementedError: AWS KMS integration not yet implemented
        """
        raise NotImplementedError(
            "AWS KMS integration not yet implemented. "
            "This stub documents the intended API. "
            "Implementation would use boto3.client('kms').create_key() "
            "with KeyUsage='SIGN_VERIFY' and retrieve public key via "
            "kms.get_public_key()."
        )

    async def sign(self, payload: str, key_id: str) -> str:
        """
        Sign payload using AWS KMS.

        Would use kms.sign() with:
        - KeyId: CMK ARN
        - Message: payload bytes
        - MessageType: 'RAW'
        - SigningAlgorithm: 'ECDSA_SHA_256'

        Args:
            payload: Data to sign
            key_id: Key identifier

        Returns:
            Base64-encoded signature

        Raises:
            NotImplementedError: AWS KMS integration not yet implemented
        """
        raise NotImplementedError(
            "AWS KMS integration not yet implemented. "
            "This stub documents the intended API. "
            "Implementation would use boto3.client('kms').sign() "
            "with SigningAlgorithm='ECDSA_SHA_256'."
        )

    async def verify(self, payload: str, signature: str, public_key: str) -> bool:
        """
        Verify signature using AWS KMS.

        Would use kms.verify() with:
        - KeyId: CMK ARN
        - Message: payload bytes
        - Signature: signature bytes
        - SigningAlgorithm: 'ECDSA_SHA_256'

        Note: Verification can also be done locally using the public key
        without calling KMS, which is more efficient.

        Args:
            payload: Original data
            signature: Signature to verify
            public_key: Public key (or KMS key ARN)

        Returns:
            True if valid, False otherwise

        Raises:
            NotImplementedError: AWS KMS integration not yet implemented
        """
        raise NotImplementedError(
            "AWS KMS integration not yet implemented. "
            "This stub documents the intended API. "
            "Implementation would use boto3.client('kms').verify() "
            "or local verification with the public key for efficiency."
        )

    async def rotate_key(self, key_id: str) -> Tuple[str, str]:
        """
        Rotate a KMS key.

        AWS KMS supports automatic key rotation for symmetric keys.
        For asymmetric keys (signing), manual rotation is required:
        1. Create new key with create_key()
        2. Update application to use new key
        3. Schedule old key for deletion with schedule_key_deletion()

        Args:
            key_id: Key identifier to rotate

        Returns:
            Tuple of (new_kms_key_arn, new_public_key)

        Raises:
            NotImplementedError: AWS KMS integration not yet implemented
        """
        raise NotImplementedError(
            "AWS KMS integration not yet implemented. "
            "This stub documents the intended API. "
            "For asymmetric keys, rotation requires creating a new key "
            "and scheduling the old key for deletion via "
            "kms.schedule_key_deletion()."
        )

    async def revoke_key(self, key_id: str) -> None:
        """
        Revoke a KMS key.

        Would use kms.schedule_key_deletion() with:
        - KeyId: CMK ARN
        - PendingWindowInDays: 7-30 (configurable grace period)

        Note: KMS key deletion is scheduled, not immediate.
        During the pending period, the key cannot be used but
        deletion can be cancelled.

        Args:
            key_id: Key identifier to revoke

        Raises:
            NotImplementedError: AWS KMS integration not yet implemented
        """
        raise NotImplementedError(
            "AWS KMS integration not yet implemented. "
            "This stub documents the intended API. "
            "Implementation would use kms.schedule_key_deletion() "
            "with a configurable pending window (7-30 days)."
        )

    async def get_key_metadata(self, key_id: str) -> Optional[KeyMetadata]:
        """
        Get KMS key metadata.

        Would use kms.describe_key() to retrieve:
        - KeyId (ARN)
        - CreationDate
        - KeyState (Enabled, Disabled, PendingDeletion, etc.)
        - KeySpec
        - KeyUsage

        Args:
            key_id: Key identifier

        Returns:
            KeyMetadata if key exists

        Raises:
            NotImplementedError: AWS KMS integration not yet implemented
        """
        raise NotImplementedError(
            "AWS KMS integration not yet implemented. "
            "This stub documents the intended API. "
            "Implementation would use kms.describe_key() "
            "to retrieve key metadata and state."
        )

    async def list_keys(self, active_only: bool = True) -> List[KeyMetadata]:
        """
        List KMS keys.

        Would use kms.list_keys() and kms.describe_key() for each to filter:
        - Active: KeyState == 'Enabled'
        - Including disabled: KeyState in ('Enabled', 'Disabled')

        Args:
            active_only: If True, only return enabled keys

        Returns:
            List of KeyMetadata

        Raises:
            NotImplementedError: AWS KMS integration not yet implemented
        """
        raise NotImplementedError(
            "AWS KMS integration not yet implemented. "
            "This stub documents the intended API. "
            "Implementation would use kms.list_keys() with pagination "
            "and kms.describe_key() for metadata filtering."
        )
