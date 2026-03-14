# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
CARE-005: HSM/KMS Integration for EATP Trust Module.

Provides an abstracted KeyManager interface supporting pluggable backends:
- InMemoryKeyManager: For development and testing
- AWSKMSKeyManager: Production AWS KMS integration (ECDSA P-256)

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

import base64
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from eatp.crypto import generate_keypair, serialize_for_signing, sign, verify_signature
from eatp.exceptions import TrustError

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    boto3 = None  # type: ignore[assignment]
    ClientError = Exception  # type: ignore[assignment,misc]
    BotoCoreError = Exception  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


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
    AWS KMS implementation of KeyManagerInterface.

    Uses AWS Key Management Service (KMS) for enterprise-grade key management
    with hardware-backed key storage. All private key operations (signing)
    happen within KMS -- private keys never leave the HSM boundary.

    IMPORTANT -- Algorithm Mismatch:
        AWS KMS does NOT support Ed25519. This implementation uses ECDSA with
        the NIST P-256 curve (ECC_NIST_P256 / ECDSA_SHA_256). Signatures
        produced by AWSKMSKeyManager are NOT compatible with the Ed25519-based
        verify_signature() function in eatp.crypto. Verification must use
        either KMS Verify API (via this class) or local ECDSA P-256
        verification with the ``cryptography`` library.

    Fail-Closed Behavior:
        All KMS errors raise KeyManagerError. This class NEVER falls back
        to in-memory key generation or local signing when KMS is unreachable.
        This is a deliberate security decision -- silent degradation to
        software keys would undermine the trust guarantees of HSM-backed keys.

    Requirements:
        - boto3 and botocore must be installed: ``pip install boto3``
        - Valid AWS credentials configured (IAM role, env vars, or profile)
        - KMS permissions: kms:CreateKey, kms:Sign, kms:Verify,
          kms:GetPublicKey, kms:DescribeKey, kms:ScheduleKeyDeletion,
          kms:ListKeys, kms:ListResourceTags, kms:TagResource

    Example:
        import boto3

        kms_client = boto3.client('kms', region_name='us-east-1')
        key_manager = AWSKMSKeyManager(kms_client=kms_client)

        # Generate an ECDSA P-256 key pair in KMS
        arn, public_key = await key_manager.generate_keypair("agent-001")

        # Sign using KMS (private key never leaves HSM)
        signature = await key_manager.sign("payload data", "agent-001")

        # Verify using KMS
        is_valid = await key_manager.verify("payload data", signature, public_key)
    """

    # KMS error code -> human-readable message prefix mapping
    _ERROR_MESSAGES: Dict[str, str] = {
        "AccessDeniedException": "Access denied to KMS key",
        "NotFoundException": "KMS key not found",
        "KMSInternalException": "KMS service error",
        "DisabledException": "KMS key is disabled",
        "InvalidKeyUsageException": "Invalid key usage for this operation",
        "KeyUnavailableException": "KMS key is unavailable",
        "KMSInvalidStateException": "KMS key is in an invalid state",
        "DependencyTimeoutException": "KMS dependency timeout",
    }

    def __init__(
        self,
        kms_client: Optional[Any] = None,
        region_name: Optional[str] = None,
        pending_deletion_days: int = 7,
    ):
        """
        Initialize AWS KMS key manager.

        Args:
            kms_client: Pre-configured boto3 KMS client. If provided, used
                directly (enables dependency injection for testing). If None,
                a new client is created using boto3.client('kms').
            region_name: AWS region for KMS operations (e.g., 'us-east-1').
                Only used when kms_client is None and a new client is created.
            pending_deletion_days: Number of days before a revoked/rotated key
                is permanently deleted (7-30, default 7). Maps to KMS
                ScheduleKeyDeletion PendingWindowInDays parameter.

        Raises:
            ImportError: If boto3 is not installed and no kms_client is provided.
        """
        if kms_client is not None:
            self._kms_client = kms_client
        else:
            if not BOTO3_AVAILABLE:
                raise ImportError(
                    "boto3 is required for AWS KMS key management. "
                    "Install with: pip install boto3"
                )
            self._kms_client = boto3.client("kms", region_name=region_name)

        self._pending_deletion_days = pending_deletion_days
        # key_id -> KMS key ARN
        self._key_arns: Dict[str, str] = {}
        # key_id -> base64-encoded public key
        self._public_keys: Dict[str, str] = {}
        # key_id -> KeyMetadata
        self._metadata: Dict[str, KeyMetadata] = {}

    def _handle_kms_error(
        self,
        error: Exception,
        operation: str,
        key_id: Optional[str] = None,
    ) -> KeyManagerError:
        """
        Map a boto3 ClientError or BotoCoreError to a KeyManagerError.

        Extracts the AWS error code and produces a clear, actionable error
        message. Logs a warning with full context for debugging.

        Args:
            error: The caught boto3 exception (ClientError or BotoCoreError).
            operation: Name of the KMS operation that failed (e.g., 'sign').
            key_id: EATP key_id involved, if known.

        Returns:
            A KeyManagerError with a descriptive message.
        """
        error_code = "Unknown"
        error_message = str(error)

        if hasattr(error, "response"):
            error_info = error.response.get("Error", {})
            error_code = error_info.get("Code", "Unknown")
            error_message = error_info.get("Message", str(error))

        prefix = self._ERROR_MESSAGES.get(error_code, f"KMS error ({error_code})")
        full_message = f"{prefix}: {error_message}"

        logger.warning(
            "KMS %s failed for key_id=%s: [%s] %s",
            operation,
            key_id,
            error_code,
            error_message,
        )

        return KeyManagerError(
            message=full_message,
            key_id=key_id,
            operation=operation,
        )

    def _payload_to_bytes(self, payload: Union[str, dict, bytes]) -> bytes:
        """
        Convert a payload to bytes for KMS signing/verification.

        Args:
            payload: Data to convert. Dicts are serialized deterministically
                via serialize_for_signing, strings are UTF-8 encoded, bytes
                are passed through.

        Returns:
            Payload as bytes.
        """
        if isinstance(payload, dict):
            return serialize_for_signing(payload).encode("utf-8")
        elif isinstance(payload, str):
            return payload.encode("utf-8")
        elif isinstance(payload, bytes):
            return payload
        else:
            raise KeyManagerError(
                message=f"Unsupported payload type: {type(payload).__name__}. "
                "Expected str, dict, or bytes.",
                operation="payload_conversion",
            )

    async def generate_keypair(self, key_id: str) -> Tuple[str, str]:
        """
        Generate a new ECDSA P-256 key pair in AWS KMS.

        Creates a KMS asymmetric signing key with ECC_NIST_P256 spec,
        retrieves the public key, and stores the key_id -> ARN mapping.

        Note: AWS KMS does NOT support Ed25519. This method uses ECDSA P-256.

        Args:
            key_id: Unique EATP identifier for the key. Stored as a KMS tag
                (eatp_key_id) for later discovery.

        Returns:
            Tuple of (kms_key_arn, base64_encoded_public_key)

        Raises:
            KeyManagerError: If key_id already exists or KMS operation fails.
        """
        if key_id in self._key_arns:
            raise KeyManagerError(
                f"Key already exists: {key_id}",
                key_id=key_id,
                operation="generate_keypair",
            )

        try:
            # Create the asymmetric signing key in KMS
            create_response = self._kms_client.create_key(
                KeyUsage="SIGN_VERIFY",
                KeySpec="ECC_NIST_P256",
                Tags=[
                    {"TagKey": "eatp_key_id", "TagValue": key_id},
                ],
            )

            key_metadata = create_response["KeyMetadata"]
            arn = key_metadata["Arn"]

            # Retrieve the public key (DER-encoded)
            pub_response = self._kms_client.get_public_key(KeyId=arn)
            public_key_bytes = pub_response["PublicKey"]
            public_key_b64 = base64.b64encode(public_key_bytes).decode("utf-8")

            # Store mappings
            self._key_arns[key_id] = arn
            self._public_keys[key_id] = public_key_b64
            self._metadata[key_id] = KeyMetadata(
                key_id=key_id,
                algorithm="ECDSA_P256",
                created_at=key_metadata.get("CreationDate", datetime.now(timezone.utc)),
                is_hardware_backed=True,
                hsm_slot=arn,
            )

            logger.info(
                "Generated KMS key for eatp_key_id=%s, arn=%s",
                key_id,
                arn,
            )

            return arn, public_key_b64

        except (ClientError, BotoCoreError) as e:
            raise self._handle_kms_error(e, "generate_keypair", key_id) from e

    async def sign(self, payload: Union[str, dict, bytes], key_id: str) -> str:
        """
        Sign a payload using AWS KMS ECDSA P-256.

        The payload is converted to bytes and sent to KMS for signing.
        The private key never leaves the KMS HSM boundary.

        Note: Signatures produced here use ECDSA_SHA_256, NOT Ed25519.
        They cannot be verified by eatp.crypto.verify_signature().

        Args:
            payload: Data to sign (str, dict, or bytes). Dicts are serialized
                deterministically via serialize_for_signing.
            key_id: EATP key identifier to use for signing.

        Returns:
            Base64-encoded ECDSA P-256 signature.

        Raises:
            KeyManagerError: If key not found, key is revoked, or KMS
                operation fails. NEVER falls back to local signing.
        """
        if key_id not in self._key_arns:
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

        arn = self._key_arns[key_id]
        payload_bytes = self._payload_to_bytes(payload)

        try:
            response = self._kms_client.sign(
                KeyId=arn,
                Message=payload_bytes,
                MessageType="RAW",
                SigningAlgorithm="ECDSA_SHA_256",
            )

            signature_bytes = response["Signature"]
            return base64.b64encode(signature_bytes).decode("utf-8")

        except (ClientError, BotoCoreError) as e:
            raise self._handle_kms_error(e, "sign", key_id) from e

    async def verify(
        self, payload: Union[str, dict, bytes], signature: str, public_key: str
    ) -> bool:
        """
        Verify an ECDSA P-256 signature using AWS KMS Verify API.

        Uses the KMS Verify API with the first available key ARN. The
        public_key parameter is used to look up the corresponding KMS key
        ARN. If no matching ARN is found, the first registered key ARN
        is used (KMS will reject if the signature doesn't match).

        Note: This verifies ECDSA P-256 signatures only. Ed25519 signatures
        from eatp.crypto.sign() cannot be verified here.

        Args:
            payload: Original data that was signed.
            signature: Base64-encoded ECDSA P-256 signature.
            public_key: Base64-encoded public key (used for ARN lookup).

        Returns:
            True if the signature is valid, False otherwise.

        Raises:
            KeyManagerError: If KMS operation fails (not for invalid
                signatures, which return False).
        """
        payload_bytes = self._payload_to_bytes(payload)
        signature_bytes = base64.b64decode(signature)

        # Find the ARN associated with this public key
        arn = None
        for kid, pub in self._public_keys.items():
            if pub == public_key:
                arn = self._key_arns.get(kid)
                break

        # Fall back to first available ARN if no public key match
        if arn is None and self._key_arns:
            arn = next(iter(self._key_arns.values()))

        if arn is None:
            raise KeyManagerError(
                message="No KMS key ARN available for verification. "
                "Generate or register a key first.",
                operation="verify",
            )

        try:
            response = self._kms_client.verify(
                KeyId=arn,
                Message=payload_bytes,
                MessageType="RAW",
                Signature=signature_bytes,
                SigningAlgorithm="ECDSA_SHA_256",
            )

            return response.get("SignatureValid", False)

        except (ClientError, BotoCoreError) as e:
            raise self._handle_kms_error(e, "verify") from e

    async def rotate_key(self, key_id: str) -> Tuple[str, str]:
        """
        Rotate a KMS key by creating a new key and scheduling old key deletion.

        AWS KMS does not support automatic rotation for asymmetric keys.
        This method performs manual rotation:
        1. Saves the old key ARN
        2. Creates a new KMS key via generate_keypair (reuses key_id)
        3. Schedules the old key for deletion
        4. Updates metadata with rotation provenance

        Args:
            key_id: EATP key identifier to rotate.

        Returns:
            Tuple of (new_kms_key_arn, new_base64_public_key)

        Raises:
            KeyManagerError: If key not found or KMS operation fails.
        """
        if key_id not in self._key_arns:
            raise KeyManagerError(
                f"Key not found: {key_id}",
                key_id=key_id,
                operation="rotate_key",
            )

        old_arn = self._key_arns[key_id]
        old_key_label = f"{key_id}:rotated:{datetime.now(timezone.utc).isoformat()}"

        # Remove the old key_id so generate_keypair won't raise "already exists"
        del self._key_arns[key_id]
        old_metadata = self._metadata.pop(key_id, None)
        self._public_keys.pop(key_id, None)

        try:
            # Create new key
            new_arn, new_public_key = await self.generate_keypair(key_id)

            # Update metadata with rotation provenance
            if key_id in self._metadata:
                self._metadata[key_id].rotated_from = old_key_label

            # Schedule old key for deletion
            try:
                self._kms_client.schedule_key_deletion(
                    KeyId=old_arn,
                    PendingWindowInDays=self._pending_deletion_days,
                )
                logger.info(
                    "Scheduled deletion of old KMS key %s (pending %d days)",
                    old_arn,
                    self._pending_deletion_days,
                )
            except (ClientError, BotoCoreError) as e:
                # Log but don't fail rotation -- the new key is already active
                logger.warning(
                    "Failed to schedule deletion of old KMS key %s: %s",
                    old_arn,
                    e,
                )

            return new_arn, new_public_key

        except KeyManagerError:
            # Restore old state on failure
            self._key_arns[key_id] = old_arn
            if old_metadata is not None:
                self._metadata[key_id] = old_metadata
            raise

    async def revoke_key(self, key_id: str) -> None:
        """
        Revoke a KMS key by scheduling it for deletion.

        Calls KMS ScheduleKeyDeletion with the configured pending window.
        During the pending period the key cannot be used for signing but
        deletion can be cancelled if needed.

        Args:
            key_id: EATP key identifier to revoke.

        Raises:
            KeyManagerError: If key not found or KMS operation fails.
        """
        if key_id not in self._key_arns:
            raise KeyManagerError(
                f"Key not found: {key_id}",
                key_id=key_id,
                operation="revoke_key",
            )

        arn = self._key_arns[key_id]

        try:
            self._kms_client.schedule_key_deletion(
                KeyId=arn,
                PendingWindowInDays=self._pending_deletion_days,
            )
        except (ClientError, BotoCoreError) as e:
            raise self._handle_kms_error(e, "revoke_key", key_id) from e

        # Update local metadata
        metadata = self._metadata.get(key_id)
        if metadata:
            metadata.is_revoked = True
            metadata.revoked_at = datetime.now(timezone.utc)
        else:
            self._metadata[key_id] = KeyMetadata(
                key_id=key_id,
                algorithm="ECDSA_P256",
                is_revoked=True,
                revoked_at=datetime.now(timezone.utc),
                is_hardware_backed=True,
                hsm_slot=arn,
            )

        logger.info(
            "Revoked KMS key %s (arn=%s), pending deletion in %d days",
            key_id,
            arn,
            self._pending_deletion_days,
        )

    async def get_key_metadata(self, key_id: str) -> Optional[KeyMetadata]:
        """
        Get metadata for a KMS key.

        Calls KMS DescribeKey to refresh the metadata from KMS and updates
        the local cache. Returns None if key_id is not tracked locally.

        Args:
            key_id: EATP key identifier.

        Returns:
            KeyMetadata if key exists in this manager, None otherwise.
        """
        if key_id not in self._key_arns:
            return None

        arn = self._key_arns[key_id]

        try:
            response = self._kms_client.describe_key(KeyId=arn)
            kms_meta = response["KeyMetadata"]

            # Update local metadata from KMS state
            key_state = kms_meta.get("KeyState", "Unknown")
            is_revoked = key_state in ("PendingDeletion", "PendingReplicaDeletion")
            is_disabled = key_state == "Disabled"

            metadata = self._metadata.get(key_id)
            if metadata:
                metadata.is_revoked = is_revoked or metadata.is_revoked
                if is_revoked and metadata.revoked_at is None:
                    metadata.revoked_at = datetime.now(timezone.utc)
            else:
                metadata = KeyMetadata(
                    key_id=key_id,
                    algorithm="ECDSA_P256",
                    created_at=kms_meta.get("CreationDate"),
                    is_hardware_backed=True,
                    hsm_slot=arn,
                    is_revoked=is_revoked,
                )
                self._metadata[key_id] = metadata

            return metadata

        except (ClientError, BotoCoreError) as e:
            logger.warning(
                "Failed to describe KMS key %s (arn=%s): %s",
                key_id,
                arn,
                e,
            )
            # Return cached metadata if KMS call fails
            return self._metadata.get(key_id)

    async def list_keys(self, active_only: bool = True) -> List[KeyMetadata]:
        """
        List all keys managed by this AWSKMSKeyManager instance.

        Returns metadata from the local cache of tracked keys. Keys are
        filtered by active status (non-revoked, non-expired) when
        active_only is True.

        Args:
            active_only: If True, only return non-revoked, non-expired keys.

        Returns:
            List of KeyMetadata for matching keys.
        """
        result = []
        for metadata in self._metadata.values():
            if active_only:
                if metadata.is_active():
                    result.append(metadata)
            else:
                result.append(metadata)
        return result

    def __repr__(self) -> str:
        """
        Return a safe representation without exposing ARNs.

        Returns:
            String representation showing key count.
        """
        return f"AWSKMSKeyManager(keys=<{len(self._key_arns)} keys>)"

    def __str__(self) -> str:
        """
        Return a safe string representation.

        Returns:
            String representation showing key count.
        """
        return f"AWSKMSKeyManager(keys=<{len(self._key_arns)} keys>)"
