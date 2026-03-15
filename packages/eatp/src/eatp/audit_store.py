# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP Audit Store Implementation.

Provides append-only storage for audit records, enabling compliance
reporting and forensic analysis of agent actions.

Key Design Principles:
- APPEND-ONLY: No updates or deletes allowed (immutable audit trail)
- CRYPTOGRAPHIC: All records are signed for tamper detection
- QUERYABLE: Efficient queries by agent, action, time range
- CHAIN-LINKED: Actions linked via parent_anchor_id for causality

CARE-010: Append-Only Audit Constraints
- AppendOnlyAuditStore: In-memory implementation with integrity verification
- AuditRecord: Enhanced record with sequence numbers and linked hashing
- IntegrityVerificationResult: Result of chain integrity verification
"""

import hashlib
import hmac as hmac_mod
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from eatp.chain import ActionResult, AuditAnchor
from eatp.exceptions import TrustError


class AuditStoreError(TrustError):
    """Base exception for audit store operations."""

    pass


class AuditAnchorNotFoundError(AuditStoreError):
    """Raised when an audit anchor is not found."""

    def __init__(self, anchor_id: str):
        super().__init__(
            f"Audit anchor not found: {anchor_id}", details={"anchor_id": anchor_id}
        )
        self.anchor_id = anchor_id


class AuditStoreImmutabilityError(AuditStoreError):
    """
    Raised when attempting to modify or delete audit records.

    CARE-010: This exception enforces append-only semantics by blocking
    UPDATE and DELETE operations on audit records.

    Attributes:
        message: Description of the violation
        operation: The blocked operation (e.g., "update", "delete")
        record_id: Optional ID of the record that was targeted
    """

    def __init__(
        self,
        operation: str,
        message: Optional[str] = None,
        record_id: Optional[str] = None,
    ):
        if message is None:
            message = f"Audit records are immutable - {operation} not allowed"
        super().__init__(
            message,
            details={"operation": operation, "record_id": record_id},
        )
        self.operation = operation
        self.record_id = record_id


@dataclass
class AuditRecord:
    """
    Enhanced audit record with sequence numbers and integrity hashing.

    CARE-010: AuditRecord wraps an AuditAnchor with additional metadata
    for append-only store integrity verification:
    - Monotonically increasing sequence numbers
    - Linked hashing for tamper detection
    - Automatic timestamp on storage

    Attributes:
        record_id: Unique identifier for this record (auto-generated UUID)
        anchor: The underlying AuditAnchor being stored
        stored_at: Timestamp when the record was stored
        integrity_hash: Hash computed from anchor data for integrity verification
        previous_hash: Hash of the previous record for linked chain verification
        sequence_number: Monotonically increasing sequence number
    """

    anchor: AuditAnchor
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    stored_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    integrity_hash: str = ""
    previous_hash: Optional[str] = None
    sequence_number: int = 0

    def __post_init__(self):
        """Compute integrity hash if not provided."""
        if not self.integrity_hash:
            self.integrity_hash = self._compute_integrity_hash()

    def _compute_integrity_hash(self) -> str:
        """
        Compute SHA-256 hash of anchor data for integrity verification.

        Returns:
            Hex-encoded SHA-256 hash
        """
        # Build deterministic payload from anchor
        payload = self.anchor.to_signing_payload()
        # Add context if present
        if self.anchor.context:
            payload["context"] = self.anchor.context
        # Sort keys for determinism
        import json

        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def verify_integrity(self) -> bool:
        """
        Verify this record's integrity hash matches its content.

        Returns:
            True if integrity hash is valid, False otherwise
        """
        computed = self._compute_integrity_hash()
        return hmac_mod.compare_digest(computed, self.integrity_hash)


@dataclass
class IntegrityVerificationResult:
    """
    Result of audit chain integrity verification.

    CARE-010: Contains the outcome of verify_integrity() on an
    AppendOnlyAuditStore, with details about any detected issues.

    Attributes:
        valid: True if the entire chain is valid
        total_records: Total number of records in the store
        verified_records: Number of records successfully verified
        first_invalid_sequence: Sequence number of first invalid record (if any)
        errors: List of error messages describing issues found
    """

    valid: bool
    total_records: int
    verified_records: int
    first_invalid_sequence: Optional[int] = None
    errors: List[str] = field(default_factory=list)


class AppendOnlyAuditStore:
    """
    Audit store with append-only enforcement.

    CARE-010: Provides an in-memory audit store that enforces immutability
    at the application level. All audit records are stored with:
    - Monotonically increasing sequence numbers
    - Linked hashing for tamper detection
    - Blocked UPDATE/DELETE operations

    Security:
    - DELETE operations blocked
    - UPDATE operations blocked
    - Only INSERT/APPEND allowed
    - Integrity verification via linked hashing

    Example:
        >>> store = AppendOnlyAuditStore()
        >>>
        >>> # Append audit anchors
        >>> anchor = AuditAnchor(
        ...     id="aud-001",
        ...     agent_id="agent-001",
        ...     action="analyze_data",
        ...     timestamp=datetime.now(timezone.utc),
        ...     trust_chain_hash="abc123",
        ...     result=ActionResult.SUCCESS,
        ...     signature="sig",
        ... )
        >>> record = await store.append(anchor)
        >>>
        >>> # Verify chain integrity
        >>> result = await store.verify_integrity()
        >>> assert result.valid
    """

    def __init__(self):
        """Initialize an empty append-only audit store."""
        self._records: List[AuditRecord] = []
        self._index: Dict[str, AuditRecord] = {}  # record_id -> record
        self._anchor_index: Dict[str, AuditRecord] = {}  # anchor.id -> record
        self._sequence: int = 0

    async def append(self, anchor: AuditAnchor) -> AuditRecord:
        """
        Append an audit anchor (the ONLY write operation allowed).

        Creates an AuditRecord from the anchor with:
        - Auto-generated record_id (UUID)
        - Computed integrity_hash
        - Linked previous_hash from last record
        - Monotonically increasing sequence_number

        Args:
            anchor: The AuditAnchor to store

        Returns:
            The created AuditRecord

        Raises:
            AuditStoreError: If storage fails
        """
        try:
            # Get previous hash for linking
            previous_hash: Optional[str] = None
            if self._records:
                previous_hash = self._records[-1].integrity_hash

            # Increment sequence number
            self._sequence += 1

            # Create the audit record
            record = AuditRecord(
                anchor=anchor,
                sequence_number=self._sequence,
                previous_hash=previous_hash,
            )

            # Store in list and indices
            self._records.append(record)
            self._index[record.record_id] = record
            self._anchor_index[anchor.id] = record

            return record

        except Exception as e:
            raise AuditStoreError(
                f"Failed to append audit anchor {anchor.id}: {str(e)}"
            ) from e

    async def get(self, record_id: str) -> Optional[AuditRecord]:
        """
        Get an audit record by record ID.

        Args:
            record_id: The record ID to retrieve

        Returns:
            The AuditRecord if found, None otherwise
        """
        return self._index.get(record_id)

    async def get_by_anchor_id(self, anchor_id: str) -> Optional[AuditRecord]:
        """
        Get an audit record by its anchor ID.

        Args:
            anchor_id: The anchor ID to retrieve

        Returns:
            The AuditRecord if found, None otherwise
        """
        return self._anchor_index.get(anchor_id)

    async def get_by_sequence(self, sequence: int) -> Optional[AuditRecord]:
        """
        Get audit record by sequence number.

        Args:
            sequence: The sequence number (1-indexed)

        Returns:
            The AuditRecord if found, None otherwise
        """
        if sequence < 1 or sequence > len(self._records):
            return None
        return self._records[sequence - 1]

    async def list_records(
        self,
        agent_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditRecord]:
        """
        List audit records with optional filtering.

        Args:
            agent_id: Filter by agent ID (optional)
            action: Filter by action type (optional)
            limit: Maximum number of records to return (default: 100)
            offset: Number of records to skip (default: 0)

        Returns:
            List of matching AuditRecords
        """
        # Apply filters
        filtered = self._records
        if agent_id is not None:
            filtered = [r for r in filtered if r.anchor.agent_id == agent_id]
        if action is not None:
            filtered = [r for r in filtered if r.anchor.action == action]

        # Apply pagination
        return filtered[offset : offset + limit]

    async def update(self, *args: Any, **kwargs: Any) -> None:
        """
        BLOCKED: Updates not allowed on append-only store.

        Raises:
            AuditStoreImmutabilityError: Always raised
        """
        raise AuditStoreImmutabilityError(operation="update")

    async def delete(self, *args: Any, **kwargs: Any) -> None:
        """
        BLOCKED: Deletes not allowed on append-only store.

        Raises:
            AuditStoreImmutabilityError: Always raised
        """
        raise AuditStoreImmutabilityError(operation="delete")

    async def verify_integrity(self) -> IntegrityVerificationResult:
        """
        Verify the integrity of the entire audit chain.

        Performs the following checks:
        1. Sequence numbers are monotonically increasing with no gaps
        2. Linked hashes form a valid chain (each record's previous_hash
           matches the prior record's integrity_hash)
        3. Each record's integrity_hash matches its content

        Returns:
            IntegrityVerificationResult with validation outcome
        """
        if not self._records:
            return IntegrityVerificationResult(
                valid=True,
                total_records=0,
                verified_records=0,
            )

        errors: List[str] = []
        verified_count = 0
        first_invalid: Optional[int] = None

        for i, record in enumerate(self._records):
            expected_sequence = i + 1

            # Check 1: Sequence numbers are monotonically increasing
            if record.sequence_number != expected_sequence:
                if first_invalid is None:
                    first_invalid = record.sequence_number
                errors.append(
                    f"Sequence gap at position {i}: expected {expected_sequence}, "
                    f"got {record.sequence_number}"
                )
                continue

            # Check 2: Linked hashes form valid chain
            if i == 0:
                # First record should have no previous hash
                if record.previous_hash is not None:
                    if first_invalid is None:
                        first_invalid = record.sequence_number
                    errors.append(
                        f"First record (seq {record.sequence_number}) has "
                        f"unexpected previous_hash: {record.previous_hash}"
                    )
                    continue
            else:
                # Subsequent records must link to previous
                expected_previous = self._records[i - 1].integrity_hash
                if record.previous_hash != expected_previous:
                    if first_invalid is None:
                        first_invalid = record.sequence_number
                    errors.append(
                        f"Broken hash chain at sequence {record.sequence_number}: "
                        f"expected previous_hash {expected_previous[:16]}..., "
                        f"got {record.previous_hash[:16] if record.previous_hash else 'None'}..."
                    )
                    continue

            # Check 3: Each record's integrity hash matches its content
            if not record.verify_integrity():
                if first_invalid is None:
                    first_invalid = record.sequence_number
                errors.append(
                    f"Integrity hash mismatch at sequence {record.sequence_number}: "
                    f"record may have been tampered with"
                )
                continue

            verified_count += 1

        return IntegrityVerificationResult(
            valid=len(errors) == 0,
            total_records=len(self._records),
            verified_records=verified_count,
            first_invalid_sequence=first_invalid,
            errors=errors,
        )

    async def verify_record(self, record_id: str) -> bool:
        """
        Verify a single record's integrity.

        Args:
            record_id: The record ID to verify

        Returns:
            True if the record exists and its integrity hash is valid,
            False otherwise
        """
        record = self._index.get(record_id)
        if record is None:
            return False
        return record.verify_integrity()

    @property
    def count(self) -> int:
        """Number of records in store."""
        return len(self._records)

    @property
    def last_sequence(self) -> int:
        """Last sequence number (0 if empty)."""
        return self._sequence

    @staticmethod
    def get_postgres_trigger_sql(table_name: str = "audit_anchors") -> str:
        """
        Return SQL for PostgreSQL append-only trigger.

        This trigger can be applied to a PostgreSQL table to enforce
        append-only semantics at the database level, providing an
        additional layer of protection beyond application-level checks.

        Args:
            table_name: Name of the audit table (default: "audit_anchors")

        Returns:
            SQL string to create the trigger

        Example:
            >>> sql = AppendOnlyAuditStore.get_postgres_trigger_sql("my_audits")
            >>> # Execute sql against your PostgreSQL database
        """
        return f"""
-- CARE-010: Append-Only Audit Trigger
-- Prevents UPDATE and DELETE operations on the audit table

CREATE OR REPLACE FUNCTION prevent_audit_modification()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' OR TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Audit trail is append-only: % not allowed on %', TG_OP, TG_TABLE_NAME;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_append_only ON {table_name};
CREATE TRIGGER audit_append_only
BEFORE UPDATE OR DELETE ON {table_name}
FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();
"""


class AuditStore(ABC):
    """
    Abstract base class for audit storage.

    Defines the interface for storing and querying audit records.
    All implementations must enforce append-only semantics.
    """

    @abstractmethod
    async def append(self, anchor: AuditAnchor) -> str:
        """
        Append an audit anchor to the store.

        Args:
            anchor: The audit anchor to store

        Returns:
            The anchor ID

        Raises:
            AuditStoreError: If storage fails
        """
        pass

    @abstractmethod
    async def get(self, anchor_id: str) -> AuditAnchor:
        """
        Retrieve an audit anchor by ID.

        Args:
            anchor_id: The anchor ID to retrieve

        Returns:
            The AuditAnchor

        Raises:
            AuditAnchorNotFoundError: If not found
        """
        pass

    @abstractmethod
    async def get_agent_history(
        self,
        agent_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        actions: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditAnchor]:
        """
        Get audit history for an agent.

        Args:
            agent_id: Agent to query
            start_time: Filter by start time
            end_time: Filter by end time
            actions: Filter by action types
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of AuditAnchors
        """
        pass

    @abstractmethod
    async def get_action_chain(
        self,
        anchor_id: str,
    ) -> List[AuditAnchor]:
        """
        Get the full chain of related actions.

        Traverses parent_anchor_id links to build the complete
        chain of actions that led to this anchor.

        Args:
            anchor_id: Starting anchor ID

        Returns:
            List of AuditAnchors from root to anchor_id
        """
        pass

    @abstractmethod
    async def query_by_action(
        self,
        action: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        result: Optional[ActionResult] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditAnchor]:
        """
        Query audit records by action type.

        Args:
            action: Action type to query
            start_time: Filter by start time
            end_time: Filter by end time
            result: Filter by action result
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of matching AuditAnchors
        """
        pass

    @abstractmethod
    async def count_by_agent(
        self,
        agent_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """
        Count audit records for an agent.

        Args:
            agent_id: Agent to count
            start_time: Filter by start time
            end_time: Filter by end time

        Returns:
            Number of matching records
        """
        pass
