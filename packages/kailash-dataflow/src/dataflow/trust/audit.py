"""Cryptographically Signed Audit Records for DataFlow (CARE-020).

This module provides signed, chain-linked audit records for DataFlow database
operations, offering tamper evidence and non-repudiation using Ed25519 signatures
and SHA-256 hash chains.

Key Components:
    - SignedAuditRecord: Immutable audit record with cryptographic signature
    - DataFlowAuditStore: Storage and verification for audit records

Features:
    - Ed25519 digital signatures for non-repudiation
    - SHA-256 hash chain for tamper detection
    - Query parameter hashing for privacy
    - Graceful degradation when keys not available
    - Thread-safe sequence numbering

Example:
    >>> from dataflow.trust.audit import DataFlowAuditStore
    >>> from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    >>> from cryptography.hazmat.primitives import serialization
    >>>
    >>> # Generate keys
    >>> private_key = Ed25519PrivateKey.generate()
    >>> private_bytes = private_key.private_bytes(
    ...     encoding=serialization.Encoding.Raw,
    ...     format=serialization.PrivateFormat.Raw,
    ...     encryption_algorithm=serialization.NoEncryption(),
    ... )
    >>> public_bytes = private_key.public_key().public_bytes(
    ...     encoding=serialization.Encoding.Raw,
    ...     format=serialization.PublicFormat.Raw,
    ... )
    >>>
    >>> # Create audit store
    >>> store = DataFlowAuditStore(
    ...     signing_key=private_bytes,
    ...     verify_key=public_bytes,
    ... )
    >>>
    >>> # Record a query
    >>> record = store.record_query(
    ...     agent_id="agent-001",
    ...     model="User",
    ...     operation="SELECT",
    ...     row_count=10,
    ...     result="success",
    ... )
    >>>
    >>> # Verify the signature
    >>> is_valid = store.verify_record(record)

Version:
    Added in: v0.11.0
    Part of: CARE-020 signed audit implementation
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# === Signed Audit Record Dataclass ===


@dataclass
class SignedAuditRecord:
    """Cryptographically signed audit record for database operations.

    Each record contains a digital signature using Ed25519 and a hash link
    to the previous record for chain integrity verification.

    Attributes:
        record_id: Unique identifier (UUID format)
        timestamp: Operation timestamp in UTC
        agent_id: Agent that performed the operation
        human_origin_id: Human who authorized (from trust context), optional
        model: DataFlow model accessed
        operation: Operation type (SELECT, INSERT, UPDATE, DELETE)
        row_count: Number of rows affected/returned
        query_hash: SHA-256 hash of query params (16 chars for privacy)
        constraints_applied: List of constraint descriptions
        result: Operation result (success, failure, denied)
        signature: Ed25519 signature in base64
        previous_record_hash: SHA-256 hash of previous record (chain link)
        sequence_number: Sequential number for ordering

    Example:
        >>> record = SignedAuditRecord(
        ...     record_id="rec-001",
        ...     timestamp=datetime.now(timezone.utc),
        ...     agent_id="agent-001",
        ...     human_origin_id="alice@corp.com",
        ...     model="User",
        ...     operation="SELECT",
        ...     row_count=10,
        ...     query_hash="abc123def456ghij",
        ...     constraints_applied=["data_scope:department:finance"],
        ...     result="success",
        ...     signature="base64signature==",
        ...     previous_record_hash=None,
        ...     sequence_number=0,
        ... )
    """

    record_id: str
    timestamp: datetime
    agent_id: str
    human_origin_id: Optional[str]
    model: str
    operation: str
    row_count: int
    query_hash: str
    constraints_applied: List[str]
    result: str
    signature: str
    previous_record_hash: Optional[str]
    sequence_number: int

    def compute_hash(self) -> str:
        """Compute SHA-256 hash for chain linking.

        Creates a deterministic hash of critical fields for use in
        linking records together in a tamper-evident chain.

        Returns:
            64-character hex string (SHA-256 hash)

        Note:
            Uses sorted JSON keys for deterministic serialization.
        """
        data = {
            "record_id": self.record_id,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "human_origin_id": self.human_origin_id,
            "model": self.model,
            "operation": self.operation,
            "row_count": self.row_count,
            "query_hash": self.query_hash,
            "constraints_applied": self.constraints_applied,
            "result": self.result,
            "signature": self.signature,
            "previous_record_hash": self.previous_record_hash,
            "sequence_number": self.sequence_number,
        }
        serialized = json.dumps(data, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def to_signing_payload(self) -> bytes:
        """Create deterministic bytes for signing.

        Produces a canonical byte representation of the record's
        critical fields for cryptographic signing.

        Returns:
            UTF-8 encoded bytes of JSON-serialized payload

        Note:
            Excludes signature and previous_record_hash from payload
            since those are computed after signing.
        """
        payload = {
            "record_id": self.record_id,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "human_origin_id": self.human_origin_id,
            "model": self.model,
            "operation": self.operation,
            "row_count": self.row_count,
            "query_hash": self.query_hash,
            "constraints_applied": self.constraints_applied,
            "result": self.result,
            "sequence_number": self.sequence_number,
        }
        return json.dumps(payload, sort_keys=True).encode("utf-8")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary with all record fields, timestamp as ISO string
        """
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "human_origin_id": self.human_origin_id,
            "model": self.model,
            "operation": self.operation,
            "row_count": self.row_count,
            "query_hash": self.query_hash,
            "constraints_applied": list(self.constraints_applied),
            "result": self.result,
            "signature": self.signature,
            "previous_record_hash": self.previous_record_hash,
            "sequence_number": self.sequence_number,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SignedAuditRecord":
        """Deserialize from dictionary.

        Args:
            data: Dictionary with record fields

        Returns:
            SignedAuditRecord instance

        Raises:
            KeyError: If required fields are missing
            ValueError: If timestamp format is invalid
        """
        # Parse timestamp from ISO format
        timestamp_str = data["timestamp"]
        if isinstance(timestamp_str, str):
            # Handle ISO format with timezone
            if timestamp_str.endswith("Z"):
                timestamp_str = timestamp_str[:-1] + "+00:00"
            timestamp = datetime.fromisoformat(timestamp_str)
        else:
            timestamp = timestamp_str

        return cls(
            record_id=data["record_id"],
            timestamp=timestamp,
            agent_id=data["agent_id"],
            human_origin_id=data.get("human_origin_id"),
            model=data["model"],
            operation=data["operation"],
            row_count=data["row_count"],
            query_hash=data.get("query_hash", ""),
            constraints_applied=list(data.get("constraints_applied", [])),
            result=data["result"],
            signature=data["signature"],
            previous_record_hash=data.get("previous_record_hash"),
            sequence_number=data.get("sequence_number", 0),
        )


# === DataFlow Audit Store ===


class DataFlowAuditStore:
    """Storage and verification for signed audit records.

    Manages a chain of signed audit records with hash-linking for
    tamper detection. Supports configurable verification strictness
    for different environments.

    Attributes:
        _records: Internal list of audit records
        _sequence_counter: Current sequence number
        _last_record_hash: Hash of most recent record for chain linking
        _signing_key: Ed25519 private key bytes (optional)
        _verify_key: Ed25519 public key bytes (optional)
        _enabled: Whether audit recording is enabled
        _strict_verification: Whether to fail-closed on missing keys

    Example:
        >>> store = DataFlowAuditStore(
        ...     signing_key=private_key_bytes,
        ...     verify_key=public_key_bytes,
        ... )
        >>> record = store.record_query(
        ...     agent_id="agent-001",
        ...     model="User",
        ...     operation="SELECT",
        ...     row_count=10,
        ... )
        >>> is_valid = store.verify_record(record)
    """

    def __init__(
        self,
        signing_key: Optional[bytes] = None,
        verify_key: Optional[bytes] = None,
        enabled: bool = True,
        strict_verification: bool = True,
    ) -> None:
        """Initialize DataFlowAuditStore.

        Args:
            signing_key: Ed25519 private key bytes (32 bytes), optional
            verify_key: Ed25519 public key bytes (32 bytes), optional
            enabled: Whether audit recording is enabled (default True)
            strict_verification: Whether to fail-closed when verify_key is
                missing or for unsigned records. When True (default, recommended
                for production), verification fails if keys are missing or
                records are unsigned. When False (development/testing only),
                graceful degradation is allowed.

        Note:
            If signing_key is None, records are created with "unsigned"
            signature for graceful degradation.

        Security:
            CARE-051: The strict_verification parameter defaults to True
            (fail-closed) to prevent silent bypass of integrity verification.
            Only set to False in development/testing environments where
            cryptographic keys are intentionally not configured.
        """
        self._records: List[SignedAuditRecord] = []
        self._sequence_counter: int = 0
        self._last_record_hash: Optional[str] = None
        self._signing_key = signing_key
        self._verify_key = verify_key
        self._enabled = enabled
        self._strict_verification = strict_verification
        self._lock = threading.Lock()

        # Log initialization status
        if not signing_key:
            logger.warning(
                "DataFlowAuditStore initialized without signing key. "
                "Records will be created with 'unsigned' signature."
            )

        # CARE-051: Warn about strict verification implications
        if strict_verification and not verify_key:
            logger.warning(
                "DataFlowAuditStore initialized with strict_verification=True "
                "but no verify_key. All signature verifications will fail. "
                "Set strict_verification=False for development/testing."
            )

    def _sign_payload(self, payload: bytes) -> str:
        """Sign a payload with Ed25519.

        Args:
            payload: Bytes to sign

        Returns:
            Base64-encoded signature, or "unsigned" if no key
        """
        if not self._signing_key:
            return "unsigned"

        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PrivateKey,
            )

            # Load private key from raw bytes
            private_key = Ed25519PrivateKey.from_private_bytes(self._signing_key)

            # Sign the payload
            signature = private_key.sign(payload)

            # Return base64-encoded signature
            return base64.b64encode(signature).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to sign audit record: {e}")
            return "unsigned"

    def _verify_signature(self, payload: bytes, signature_b64: str) -> bool:
        """Verify an Ed25519 signature.

        Args:
            payload: Original payload bytes
            signature_b64: Base64-encoded signature

        Returns:
            True if signature is valid, False otherwise

        Security:
            CARE-051: This method implements fail-closed behavior by default.
            When strict_verification=True (default):
            - Returns False for "unsigned" signatures
            - Returns False when no verify_key is configured
            This prevents silent bypass of integrity verification in production.

            When strict_verification=False (development/testing only):
            - Returns True for "unsigned" signatures (graceful degradation)
            - Returns True when no verify_key is configured
        """
        # CARE-051: Handle unsigned records based on strict_verification mode
        if signature_b64 == "unsigned":
            if self._strict_verification:
                logger.warning(
                    "CARE-051: Rejecting unsigned record in strict verification mode. "
                    "Set strict_verification=False for development/testing."
                )
                return False
            # Graceful degradation for development/testing
            return True

        # CARE-051: Handle missing verify_key based on strict_verification mode
        if not self._verify_key:
            if self._strict_verification:
                logger.warning(
                    "CARE-051: Cannot verify signature - no verify_key configured. "
                    "Returning False (fail-closed) in strict verification mode. "
                    "Set strict_verification=False for development/testing."
                )
                return False
            logger.warning(
                "Cannot verify signature: no public key configured. "
                "Returning True for graceful degradation (strict_verification=False)."
            )
            return True

        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )

            # Load public key from raw bytes
            public_key = Ed25519PublicKey.from_public_bytes(self._verify_key)

            # Decode signature from base64
            signature = base64.b64decode(signature_b64)

            # Verify signature (raises exception if invalid)
            public_key.verify(signature, payload)
            return True
        except Exception as e:
            logger.debug(f"Signature verification failed: {e}")
            return False

    def record_query(
        self,
        agent_id: str,
        model: str,
        operation: str,
        row_count: int,
        query_params: Optional[Dict[str, Any]] = None,
        constraints_applied: Optional[List[str]] = None,
        result: str = "success",
        human_origin_id: Optional[str] = None,
    ) -> Optional[SignedAuditRecord]:
        """Record a database query operation with signature and chain link.

        Args:
            agent_id: Agent that performed the operation
            model: DataFlow model accessed
            operation: Operation type (SELECT, INSERT, etc.)
            row_count: Number of rows affected/returned
            query_params: Query parameters (will be hashed)
            constraints_applied: List of constraint descriptions
            result: Operation result (success, failure, denied)
            human_origin_id: Human who authorized (optional)

        Returns:
            SignedAuditRecord if enabled, None if disabled
        """
        if not self._enabled:
            return None

        with self._lock:
            # Generate record ID
            record_id = str(uuid.uuid4())

            # Compute query hash
            query_hash = self.compute_query_hash(query_params or {})

            # Create record (without signature initially)
            record = SignedAuditRecord(
                record_id=record_id,
                timestamp=datetime.now(timezone.utc),
                agent_id=agent_id,
                human_origin_id=human_origin_id,
                model=model,
                operation=operation,
                row_count=row_count,
                query_hash=query_hash,
                constraints_applied=list(constraints_applied or []),
                result=result,
                signature="",  # Will be set below
                previous_record_hash=self._last_record_hash,
                sequence_number=self._sequence_counter,
            )

            # Sign the record
            payload = record.to_signing_payload()
            signature = self._sign_payload(payload)

            # Create final record with signature
            signed_record = SignedAuditRecord(
                record_id=record.record_id,
                timestamp=record.timestamp,
                agent_id=record.agent_id,
                human_origin_id=record.human_origin_id,
                model=record.model,
                operation=record.operation,
                row_count=record.row_count,
                query_hash=record.query_hash,
                constraints_applied=record.constraints_applied,
                result=record.result,
                signature=signature,
                previous_record_hash=record.previous_record_hash,
                sequence_number=record.sequence_number,
            )

            # Update chain state
            self._last_record_hash = signed_record.compute_hash()
            self._sequence_counter += 1
            self._records.append(signed_record)

            return signed_record

    def record_write(
        self,
        agent_id: str,
        model: str,
        operation: str,
        row_count: int,
        data: Optional[Dict[str, Any]] = None,
        result: str = "success",
        human_origin_id: Optional[str] = None,
    ) -> Optional[SignedAuditRecord]:
        """Record a database write operation.

        Args:
            agent_id: Agent that performed the operation
            model: DataFlow model accessed
            operation: Operation type (INSERT, UPDATE, DELETE)
            row_count: Number of rows affected
            data: Write data (will be hashed, not stored directly)
            result: Operation result (success, failure, denied)
            human_origin_id: Human who authorized (optional)

        Returns:
            SignedAuditRecord if enabled, None if disabled
        """
        return self.record_query(
            agent_id=agent_id,
            model=model,
            operation=operation,
            row_count=row_count,
            query_params=data,
            result=result,
            human_origin_id=human_origin_id,
        )

    def verify_record(self, record: SignedAuditRecord) -> bool:
        """Verify a single record's signature.

        Args:
            record: SignedAuditRecord to verify

        Returns:
            True if signature is valid, False otherwise
        """
        payload = record.to_signing_payload()
        return self._verify_signature(payload, record.signature)

    def verify_chain_integrity(self) -> Tuple[bool, Optional[str]]:
        """Verify the entire audit chain hasn't been tampered with.

        Checks:
            1. Each record's previous_record_hash matches computed hash
            2. Sequence numbers are contiguous
            3. All signatures are valid

        Returns:
            Tuple of (is_valid, error_message_if_invalid)
        """
        if not self._records:
            return True, None

        # Check first record
        if self._records[0].previous_record_hash is not None:
            return False, "First record should have no previous_record_hash"

        if self._records[0].sequence_number != 0:
            return False, "First record should have sequence_number 0"

        # Verify each record in the chain
        for i, record in enumerate(self._records):
            # Check sequence number
            if record.sequence_number != i:
                return (
                    False,
                    f"Sequence gap detected at position {i}: "
                    f"expected {i}, got {record.sequence_number}",
                )

            # Check chain link (for records after the first)
            if i > 0:
                expected_hash = self._records[i - 1].compute_hash()
                if record.previous_record_hash != expected_hash:
                    return (
                        False,
                        f"Chain integrity mismatch at record {i}: "
                        f"previous_record_hash does not match computed hash. "
                        f"Possible tampering detected.",
                    )

            # Verify signature
            if not self.verify_record(record):
                return (
                    False,
                    f"Signature verification failed for record {i} "
                    f"(id: {record.record_id})",
                )

        return True, None

    def get_records(self) -> List[SignedAuditRecord]:
        """Get all audit records.

        Returns:
            List of all SignedAuditRecord instances
        """
        return list(self._records)

    def get_records_by_agent(self, agent_id: str) -> List[SignedAuditRecord]:
        """Get records for a specific agent.

        Args:
            agent_id: Agent ID to filter by

        Returns:
            List of matching SignedAuditRecord instances
        """
        return [r for r in self._records if r.agent_id == agent_id]

    def get_records_by_model(self, model: str) -> List[SignedAuditRecord]:
        """Get records for a specific model.

        Args:
            model: Model name to filter by

        Returns:
            List of matching SignedAuditRecord instances
        """
        return [r for r in self._records if r.model == model]

    def clear_records(self) -> None:
        """Clear all records (testing only).

        Warning:
            This is intended for testing purposes only. In production,
            audit records should never be deleted.
        """
        with self._lock:
            self._records.clear()
            self._sequence_counter = 0
            self._last_record_hash = None
            logger.warning("Audit records cleared - this should only happen in tests")

    @staticmethod
    def compute_query_hash(params: Dict[str, Any]) -> str:
        """Compute SHA-256 hash of query params, truncated to 16 chars.

        Args:
            params: Query parameters dictionary

        Returns:
            16-character hex string hash

        Note:
            Truncation provides privacy while allowing duplicate detection.
        """
        if not params:
            return "0" * 16

        try:
            serialized = json.dumps(params, sort_keys=True, default=str)
            full_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
            return full_hash[:16]
        except Exception as e:
            logger.warning(f"Failed to compute query hash: {e}")
            return "0" * 16
