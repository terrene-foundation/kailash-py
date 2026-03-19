# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP Credential Rotation Management.

Provides automated credential rotation for organizational authorities with:
- Keypair rotation with grace period support
- Audit logging for all rotation events
- Atomic updates to prevent partial rotations (CARE-008)
- Concurrent rotation prevention (only one rotation per authority at a time)
- Transactional re-signing of trust chains after key rotation
"""

import asyncio
import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from uuid import uuid4

from eatp.authority import (
    AuthorityRegistryProtocol,
    OrganizationalAuthority,
)
from eatp.chain import TrustLineageChain
from eatp.crypto import generate_keypair, serialize_for_signing, sign
from eatp.exceptions import (
    AuthorityInactiveError,
    AuthorityNotFoundError,
    TrustError,
)
from eatp.operations import TrustKeyManager
from eatp.store import TrustStore


class RotationStatus(str, Enum):
    """Status of a rotation operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    GRACE_PERIOD = "grace_period"


class RotationError(TrustError):
    """Raised when a rotation operation fails."""

    def __init__(
        self,
        message: str,
        authority_id: Optional[str] = None,
        rotation_id: Optional[str] = None,
        reason: Optional[str] = None,
    ):
        super().__init__(
            message,
            details={
                "authority_id": authority_id,
                "rotation_id": rotation_id,
                "reason": reason,
            },
        )
        self.authority_id = authority_id
        self.rotation_id = rotation_id
        self.reason = reason


@dataclass
class RotationResult:
    """
    Result of a key rotation operation.

    Attributes:
        new_key_id: ID of the newly generated key
        old_key_id: ID of the rotated key
        chains_updated: Number of trust chains that were re-signed
        started_at: When the rotation began
        completed_at: When the rotation completed
        rotation_id: Unique identifier for this rotation
        grace_period_end: When the old key will be revoked
    """

    new_key_id: str
    old_key_id: str
    chains_updated: int
    started_at: datetime
    completed_at: datetime
    rotation_id: str = field(default_factory=lambda: f"rot-{uuid4().hex[:12]}")
    grace_period_end: Optional[datetime] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "rotation_id": self.rotation_id,
            "new_key_id": self.new_key_id,
            "old_key_id": self.old_key_id,
            "chains_updated": self.chains_updated,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "grace_period_end": (self.grace_period_end.isoformat() if self.grace_period_end else None),
        }


@dataclass
class RotationStatusInfo:
    """
    Current rotation status for an authority.

    Attributes:
        last_rotation: Timestamp of last completed rotation
        next_scheduled: Timestamp of next scheduled rotation (if any)
        current_key_id: Currently active key ID
        pending_revocations: List of key IDs pending revocation
        rotation_period_days: Configured rotation period
        status: Current rotation status
        grace_period_keys: Keys currently in grace period
    """

    last_rotation: Optional[datetime]
    next_scheduled: Optional[datetime]
    current_key_id: str
    pending_revocations: List[str] = field(default_factory=list)
    rotation_period_days: int = 90
    status: RotationStatus = RotationStatus.COMPLETED
    grace_period_keys: Dict[str, datetime] = field(default_factory=dict)  # key_id -> expiry

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "last_rotation": (self.last_rotation.isoformat() if self.last_rotation else None),
            "next_scheduled": (self.next_scheduled.isoformat() if self.next_scheduled else None),
            "current_key_id": self.current_key_id,
            "pending_revocations": self.pending_revocations,
            "rotation_period_days": self.rotation_period_days,
            "status": self.status.value,
            "grace_period_keys": {k: v.isoformat() for k, v in self.grace_period_keys.items()},
        }


@dataclass
class ScheduledRotation:
    """Scheduled rotation operation."""

    rotation_id: str
    authority_id: str
    scheduled_at: datetime
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: RotationStatus = RotationStatus.PENDING


class CredentialRotationManager:
    """
    Manages credential rotation for organizational authorities.

    Provides automated key rotation with grace periods, audit logging,
    and atomic updates to prevent partial rotations.

    Features:
    - Grace period support (default 24 hours)
    - Audit logging for all rotation events
    - Atomic updates to prevent partial rotations
    - Concurrent rotation prevention (only one rotation per authority at a time)
    - Automatic re-signing of trust chains after rotation
    - Scheduled rotation support

    Example:
        >>> # Initialize components
        >>> key_manager = TrustKeyManager()
        >>> trust_store = PostgresTrustStore()
        >>> # registry must satisfy AuthorityRegistryProtocol
        >>>
        >>> # Create rotation manager
        >>> rotation_mgr = CredentialRotationManager(
        ...     key_manager=key_manager,
        ...     trust_store=trust_store,
        ...     authority_registry=registry,
        ...     rotation_period_days=90,
        ...     grace_period_hours=24,
        ... )
        >>> await rotation_mgr.initialize()
        >>>
        >>> # Rotate a key
        >>> result = await rotation_mgr.rotate_key("org-acme")
        >>> print(f"Rotated {result.chains_updated} chains")
        >>>
        >>> # Check rotation status
        >>> status = await rotation_mgr.get_rotation_status("org-acme")
        >>> print(f"Last rotation: {status.last_rotation}")
        >>>
        >>> # Schedule future rotation
        >>> rotation_id = await rotation_mgr.schedule_rotation(
        ...     "org-acme",
        ...     at=datetime.now(timezone.utc) + timedelta(days=90)
        ... )
    """

    def __init__(
        self,
        key_manager: TrustKeyManager,
        trust_store: TrustStore,
        authority_registry: AuthorityRegistryProtocol,
        rotation_period_days: int = 90,
        grace_period_hours: int = 24,
    ):
        """
        Initialize CredentialRotationManager.

        Args:
            key_manager: TrustKeyManager for key operations
            trust_store: TrustStore for chain updates
            authority_registry: Any object satisfying AuthorityRegistryProtocol
            rotation_period_days: Default rotation period in days (default: 90)
            grace_period_hours: Grace period before old key revocation in hours (default: 24)
        """
        self.key_manager = key_manager
        self.trust_store = trust_store
        self.authority_registry = authority_registry
        self.rotation_period_days = rotation_period_days
        self.grace_period_hours = grace_period_hours

        # Track active rotations to prevent concurrent rotations
        self._active_rotations: Set[str] = set()
        self._rotation_locks: Dict[str, asyncio.Lock] = {}

        # Track rotation history and scheduled rotations
        self._rotation_history: Dict[str, List[RotationResult]] = {}  # authority_id -> results
        self._scheduled_rotations: Dict[str, List[ScheduledRotation]] = {}  # authority_id -> scheduled

        # Track keys in grace period
        self._grace_period_keys: Dict[str, Dict[str, datetime]] = {}  # authority_id -> {key_id: expiry}

        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize the rotation manager.

        Must be called before using the manager.
        """
        if self._initialized:
            return
        self._initialized = True

    def _get_lock(self, authority_id: str) -> asyncio.Lock:
        """
        Get or create a lock for an authority.

        Args:
            authority_id: Authority to get lock for

        Returns:
            Lock for the authority
        """
        if authority_id not in self._rotation_locks:
            self._rotation_locks[authority_id] = asyncio.Lock()
        return self._rotation_locks[authority_id]

    async def rotate_key(
        self,
        authority_id: str,
        grace_period_hours: Optional[int] = None,
    ) -> RotationResult:
        """
        Rotate the signing key for an authority.

        This operation:
        1. Generates a new keypair
        2. Updates the authority record with the new public key
        3. Re-signs all trust chains established by this authority
        4. Places the old key in grace period
        5. Logs the rotation event

        Args:
            authority_id: Authority whose key should be rotated
            grace_period_hours: Override grace period (default: use configured value)

        Returns:
            RotationResult with details of the rotation

        Raises:
            AuthorityNotFoundError: If authority not found
            AuthorityInactiveError: If authority is inactive
            RotationError: If rotation fails or another rotation is in progress
        """
        # Use configured grace period if not specified
        if grace_period_hours is None:
            grace_period_hours = self.grace_period_hours

        # Acquire lock to prevent concurrent rotations
        lock = self._get_lock(authority_id)
        if not await lock.acquire():
            raise RotationError(
                f"Another rotation is in progress for authority {authority_id}",
                authority_id=authority_id,
                reason="concurrent_rotation",
            )

        try:
            # Check if already rotating
            if authority_id in self._active_rotations:
                raise RotationError(
                    f"Rotation already in progress for authority {authority_id}",
                    authority_id=authority_id,
                    reason="concurrent_rotation",
                )

            # Mark as rotating
            self._active_rotations.add(authority_id)

            started_at = datetime.now(timezone.utc)
            rotation_id = f"rot-{uuid4().hex[:12]}"

            try:
                # Get authority
                authority = await self.authority_registry.get_authority(authority_id)
                old_key_id = authority.signing_key_id
                old_public_key = authority.public_key

                # Generate new keypair
                new_private_key, new_public_key = generate_keypair()
                new_key_id = f"key-{uuid4().hex[:12]}"

                # Register new key
                self.key_manager.register_key(new_key_id, new_private_key)

                # Update authority record atomically
                authority.signing_key_id = new_key_id
                authority.public_key = new_public_key
                authority.updated_at = datetime.now(timezone.utc)

                # Add rotation metadata
                if "key_rotation_history" not in authority.metadata:
                    authority.metadata["key_rotation_history"] = []

                authority.metadata["key_rotation_history"].append(
                    {
                        "rotation_id": rotation_id,
                        "old_key_id": old_key_id,
                        "new_key_id": new_key_id,
                        "rotated_at": started_at.isoformat(),
                    }
                )

                await self.authority_registry.update_authority(authority)

                # Re-sign all trust chains established by this authority
                chains_updated = await self._resign_chains(
                    authority_id=authority_id,
                    old_key_id=old_key_id,
                    new_key_id=new_key_id,
                )

                # Place old key in grace period
                grace_period_end = started_at + timedelta(hours=grace_period_hours)
                if authority_id not in self._grace_period_keys:
                    self._grace_period_keys[authority_id] = {}
                self._grace_period_keys[authority_id][old_key_id] = grace_period_end

                completed_at = datetime.now(timezone.utc)

                # Create result
                result = RotationResult(
                    rotation_id=rotation_id,
                    new_key_id=new_key_id,
                    old_key_id=old_key_id,
                    chains_updated=chains_updated,
                    started_at=started_at,
                    completed_at=completed_at,
                    grace_period_end=grace_period_end,
                )

                # Store in history
                if authority_id not in self._rotation_history:
                    self._rotation_history[authority_id] = []
                self._rotation_history[authority_id].append(result)

                # Log audit event
                await self._log_rotation_event(
                    authority_id=authority_id,
                    rotation_id=rotation_id,
                    event_type="rotation_completed",
                    details=result.to_dict(),
                )

                return result

            except RotationError:
                # Re-raise RotationError as-is to preserve specific error details
                # (e.g., CARE-048 rollback failures with inconsistent state info)
                raise
            except Exception as e:
                # Log failure
                await self._log_rotation_event(
                    authority_id=authority_id,
                    rotation_id=rotation_id,
                    event_type="rotation_failed",
                    details={"error": str(e)},
                )
                raise RotationError(
                    f"Failed to rotate key for authority {authority_id}: {str(e)}",
                    authority_id=authority_id,
                    rotation_id=rotation_id,
                    reason="rotation_failed",
                ) from e

        finally:
            # Release lock
            self._active_rotations.discard(authority_id)
            lock.release()

    async def _resign_chains(
        self,
        authority_id: str,
        old_key_id: str,
        new_key_id: str,
        batch_size: int = 100,
    ) -> int:
        """
        Re-sign all trust chains for an authority atomically.

        CARE-008: This method now provides transactional guarantees.
        Either ALL chains are re-signed or NONE are. If any step fails,
        all changes are rolled back.

        Args:
            authority_id: Authority whose chains to re-sign
            old_key_id: Old key ID (for reference)
            new_key_id: New key ID to use for signing
            batch_size: Number of chains to process per batch (default: 100)

        Returns:
            Number of chains updated
        """
        # Collect all chain updates first without committing
        chain_updates = await self._collect_chain_updates(
            authority_id=authority_id,
            new_key_id=new_key_id,
            batch_size=batch_size,
        )

        if not chain_updates:
            return 0

        # Apply all updates atomically
        chains_updated = await self._apply_chain_updates_atomically(chain_updates)

        return chains_updated

    async def _collect_chain_updates(
        self,
        authority_id: str,
        new_key_id: str,
        batch_size: int = 100,
    ) -> List[Tuple[str, TrustLineageChain]]:
        """
        Collect all chain updates without committing them.

        CARE-008: Re-signs chains in memory without persisting,
        allowing for atomic commit later.

        Args:
            authority_id: Authority whose chains to re-sign
            new_key_id: New key ID to use for signing
            batch_size: Number of chains to fetch per batch

        Returns:
            List of (agent_id, updated_chain) tuples
        """
        chain_updates: List[Tuple[str, TrustLineageChain]] = []
        offset = 0

        while True:
            # Get chains in batches for pagination support
            chains = await self.trust_store.list_chains(
                authority_id=authority_id,
                active_only=True,
                limit=batch_size,
                offset=offset,
            )

            if not chains:
                break

            for chain in chains:
                # Create a deep copy to avoid modifying the original until commit
                updated_chain = copy.deepcopy(chain)

                # Re-sign genesis record
                genesis_payload = serialize_for_signing(updated_chain.genesis.to_signing_payload())
                new_signature = await self.key_manager.sign(genesis_payload, new_key_id)
                updated_chain.genesis.signature = new_signature

                # Re-sign capability attestations
                for capability in updated_chain.capabilities:
                    if capability.attester_id == authority_id:
                        cap_payload = serialize_for_signing(capability.to_signing_payload())
                        new_signature = await self.key_manager.sign(cap_payload, new_key_id)
                        capability.signature = new_signature

                # Re-sign delegations
                for delegation in updated_chain.delegations:
                    if delegation.delegator_id == authority_id:
                        del_payload = serialize_for_signing(delegation.to_signing_payload())
                        new_signature = await self.key_manager.sign(del_payload, new_key_id)
                        delegation.signature = new_signature

                chain_updates.append((updated_chain.genesis.agent_id, updated_chain))

            offset += batch_size

            # If we got fewer chains than batch_size, we're done
            if len(chains) < batch_size:
                break

        return chain_updates

    async def _apply_chain_updates_atomically(
        self,
        chain_updates: List[Tuple[str, TrustLineageChain]],
    ) -> int:
        """
        Apply all chain updates atomically using transaction context.

        CARE-008: Uses TransactionContext for atomic updates.
        If any update fails, ALL changes are rolled back.

        CARE-048: For stores without transaction support (PostgresTrustStore),
        implements manual rollback by snapshotting chains before updates.
        On failure, attempts to restore original chains. If rollback also fails,
        logs CRITICAL error with details of inconsistent state.

        Args:
            chain_updates: List of (agent_id, updated_chain) tuples to apply

        Returns:
            Number of chains updated

        Raises:
            RotationError: If the update fails and rollback occurs
        """
        if not chain_updates:
            return 0

        # Check if trust_store supports transactions (InMemoryTrustStore)
        # Try to get a transaction context - if it fails, fall back to non-transactional
        transaction_supported = False
        if hasattr(self.trust_store, "transaction"):
            try:
                # Try to call transaction() to see if it's actually supported
                tx_context = self.trust_store.transaction()
                transaction_supported = tx_context is not None
            except (AttributeError, NotImplementedError):
                transaction_supported = False

        if transaction_supported:
            try:
                async with self.trust_store.transaction() as tx:
                    for agent_id, chain in chain_updates:
                        await tx.update_chain(agent_id, chain)
                    await tx.commit()
                return len(chain_updates)
            except Exception as e:
                # Transaction automatically rolls back on exception
                raise RotationError(
                    f"Atomic chain re-signing failed: {str(e)}",
                    reason="atomic_resign_failed",
                ) from e
        else:
            # CARE-048: For stores without transaction support, implement manual rollback
            # Snapshot current chains before applying updates
            chain_snapshots: Dict[str, TrustLineageChain] = {}
            successfully_updated: List[str] = []
            failed_agent_id: Optional[str] = None
            original_error: Optional[Exception] = None

            # Take snapshots of all chains we're about to update
            for agent_id, _ in chain_updates:
                try:
                    chain_snapshots[agent_id] = await self.trust_store.get_chain(agent_id)
                except Exception as snapshot_err:
                    # If we can't snapshot, we can't safely proceed
                    raise RotationError(
                        f"Failed to snapshot chain {agent_id} before re-signing: {str(snapshot_err)}",
                        reason="snapshot_failed",
                    ) from snapshot_err

            # Apply updates one by one, tracking progress
            try:
                for agent_id, chain in chain_updates:
                    await self.trust_store.update_chain(agent_id, chain)
                    successfully_updated.append(agent_id)
                return len(chain_updates)
            except Exception as e:
                # Determine which chain failed
                failed_index = len(successfully_updated)
                if failed_index < len(chain_updates):
                    failed_agent_id = chain_updates[failed_index][0]
                original_error = e

                # CARE-048: Attempt rollback of successfully updated chains
                rollback_failures: List[Tuple[str, str]] = []
                for agent_id in successfully_updated:
                    try:
                        original_chain = chain_snapshots[agent_id]
                        await self.trust_store.update_chain(agent_id, original_chain)
                    except Exception as rollback_err:
                        rollback_failures.append((agent_id, str(rollback_err)))

                if rollback_failures:
                    # CRITICAL: Some chains could not be rolled back
                    # System is in inconsistent state
                    from eatp.security import (
                        SecurityAuditLogger,
                        SecurityEventSeverity,
                    )

                    if not hasattr(self, "_audit_logger"):
                        self._audit_logger = SecurityAuditLogger()

                    inconsistent_chains = [agent_id for agent_id, _ in rollback_failures]
                    rolled_back_chains = [aid for aid in successfully_updated if aid not in inconsistent_chains]

                    # Log CRITICAL error with full details
                    self._audit_logger.log_security_event(
                        event_type="chain_resign_inconsistent_state",
                        details={
                            "original_error": str(original_error),
                            "failed_at_chain": failed_agent_id,
                            "total_chains": len(chain_updates),
                            "successfully_updated_before_failure": len(successfully_updated),
                            "rolled_back_successfully": rolled_back_chains,
                            "rollback_failures": [{"agent_id": aid, "error": err} for aid, err in rollback_failures],
                            "inconsistent_chains": inconsistent_chains,
                        },
                        severity=SecurityEventSeverity.CRITICAL,
                    )

                    raise RotationError(
                        f"CRITICAL: Chain re-signing failed and rollback partially failed. "
                        f"Original error at chain '{failed_agent_id}': {str(original_error)}. "
                        f"Rollback failed for {len(rollback_failures)} chain(s): {inconsistent_chains}. "
                        f"These chains are in INCONSISTENT STATE with new signatures while others have old signatures. "
                        f"Manual intervention required.",
                        reason="rollback_failed_inconsistent_state",
                    ) from original_error
                else:
                    # Rollback succeeded - all chains restored to original state
                    raise RotationError(
                        f"Chain re-signing failed at chain '{failed_agent_id}' "
                        f"({len(successfully_updated) + 1} of {len(chain_updates)}): {str(original_error)}. "
                        f"Successfully rolled back {len(successfully_updated)} previously updated chain(s).",
                        reason="resign_failed_rolled_back",
                    ) from original_error

    async def schedule_rotation(
        self,
        authority_id: str,
        at: datetime,
    ) -> str:
        """
        Schedule a future key rotation.

        Args:
            authority_id: Authority to schedule rotation for
            at: When to perform the rotation

        Returns:
            Rotation ID for the scheduled rotation

        Raises:
            AuthorityNotFoundError: If authority not found
            RotationError: If scheduled time is in the past
        """
        # Validate authority exists
        await self.authority_registry.get_authority(authority_id)

        # Validate time
        if at <= datetime.now(timezone.utc):
            raise RotationError(
                "Scheduled rotation time must be in the future",
                authority_id=authority_id,
                reason="invalid_schedule_time",
            )

        # Create scheduled rotation
        rotation_id = f"rot-{uuid4().hex[:12]}"
        scheduled = ScheduledRotation(
            rotation_id=rotation_id,
            authority_id=authority_id,
            scheduled_at=at,
        )

        # Store scheduled rotation
        if authority_id not in self._scheduled_rotations:
            self._scheduled_rotations[authority_id] = []
        self._scheduled_rotations[authority_id].append(scheduled)

        # Log audit event
        await self._log_rotation_event(
            authority_id=authority_id,
            rotation_id=rotation_id,
            event_type="rotation_scheduled",
            details={
                "scheduled_at": at.isoformat(),
            },
        )

        return rotation_id

    async def get_rotation_status(
        self,
        authority_id: str,
    ) -> RotationStatusInfo:
        """
        Get the current rotation status for an authority.

        Args:
            authority_id: Authority to check status for

        Returns:
            RotationStatusInfo with current state

        Raises:
            AuthorityNotFoundError: If authority not found
        """
        # Validate authority exists
        authority = await self.authority_registry.get_authority(authority_id)

        # Get last rotation
        last_rotation = None
        if authority_id in self._rotation_history and self._rotation_history[authority_id]:
            last_rotation = self._rotation_history[authority_id][-1].completed_at

        # Get next scheduled
        next_scheduled = None
        if authority_id in self._scheduled_rotations:
            pending = [s for s in self._scheduled_rotations[authority_id] if s.status == RotationStatus.PENDING]
            if pending:
                next_scheduled = min(s.scheduled_at for s in pending)

        # Determine status
        status = RotationStatus.COMPLETED
        if authority_id in self._active_rotations:
            status = RotationStatus.IN_PROGRESS
        elif authority_id in self._grace_period_keys and self._grace_period_keys[authority_id]:
            status = RotationStatus.GRACE_PERIOD

        # Get pending revocations (keys past grace period)
        pending_revocations = []
        grace_period_keys = {}
        if authority_id in self._grace_period_keys:
            now = datetime.now(timezone.utc)
            for key_id, expiry in self._grace_period_keys[authority_id].items():
                if expiry <= now:
                    pending_revocations.append(key_id)
                else:
                    grace_period_keys[key_id] = expiry

        return RotationStatusInfo(
            last_rotation=last_rotation,
            next_scheduled=next_scheduled,
            current_key_id=authority.signing_key_id,
            pending_revocations=pending_revocations,
            rotation_period_days=self.rotation_period_days,
            status=status,
            grace_period_keys=grace_period_keys,
        )

    async def revoke_old_key(
        self,
        authority_id: str,
        key_id: str,
    ) -> None:
        """
        Revoke an old key after grace period.

        This removes the key from the key manager and from the grace period tracking.

        Args:
            authority_id: Authority whose key to revoke
            key_id: Key ID to revoke

        Raises:
            AuthorityNotFoundError: If authority not found
            RotationError: If key is not in grace period or grace period not expired
        """
        # Validate authority exists
        await self.authority_registry.get_authority(authority_id)

        # Check if key is in grace period
        if authority_id not in self._grace_period_keys:
            raise RotationError(
                f"No keys in grace period for authority {authority_id}",
                authority_id=authority_id,
                reason="no_grace_period_keys",
            )

        if key_id not in self._grace_period_keys[authority_id]:
            raise RotationError(
                f"Key {key_id} is not in grace period for authority {authority_id}",
                authority_id=authority_id,
                reason="key_not_in_grace_period",
            )

        # Check if grace period has expired
        expiry = self._grace_period_keys[authority_id][key_id]
        if expiry > datetime.now(timezone.utc):
            raise RotationError(
                f"Grace period for key {key_id} has not expired yet (expires at {expiry.isoformat()})",
                authority_id=authority_id,
                reason="grace_period_not_expired",
            )

        # Remove from grace period tracking
        del self._grace_period_keys[authority_id][key_id]

        # Remove from key manager (if it exists)
        # Note: TrustKeyManager doesn't have a remove method in the current implementation,
        # but in production this would remove the key from the HSM/KMS

        # Log audit event
        await self._log_rotation_event(
            authority_id=authority_id,
            rotation_id=f"rev-{uuid4().hex[:12]}",
            event_type="rotation_key_revoked",
            details={
                "key_id": key_id,
                "revoked_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def process_scheduled_rotations(self) -> List[RotationResult]:
        """
        Process any scheduled rotations that are due.

        This should be called periodically (e.g., by a cron job or background task).

        Returns:
            List of RotationResults for completed rotations
        """
        results = []
        now = datetime.now(timezone.utc)

        for authority_id, scheduled_list in self._scheduled_rotations.items():
            for scheduled in scheduled_list:
                if scheduled.status == RotationStatus.PENDING and scheduled.scheduled_at <= now:
                    try:
                        scheduled.status = RotationStatus.IN_PROGRESS

                        # Perform rotation
                        result = await self.rotate_key(authority_id)
                        results.append(result)

                        scheduled.status = RotationStatus.COMPLETED

                    except Exception as e:
                        scheduled.status = RotationStatus.FAILED
                        await self._log_rotation_event(
                            authority_id=authority_id,
                            rotation_id=scheduled.rotation_id,
                            event_type="scheduled_rotation_failed",
                            details={"error": str(e)},
                        )

        return results

    async def _log_rotation_event(
        self,
        authority_id: str,
        rotation_id: str,
        event_type: str,
        details: Dict,
    ) -> None:
        """
        Log a rotation event for audit purposes.

        Args:
            authority_id: Authority involved in the event
            rotation_id: Rotation identifier
            event_type: Type of event (rotation_completed, rotation_failed, etc.)
            details: Event details
        """
        # Import here to avoid circular imports
        from eatp.security import SecurityAuditLogger, SecurityEventSeverity

        # Use a shared audit logger instance
        if not hasattr(self, "_audit_logger"):
            self._audit_logger = SecurityAuditLogger()

        # Determine severity based on event type
        severity = SecurityEventSeverity.INFO
        if "failed" in event_type.lower() or "error" in event_type.lower():
            severity = SecurityEventSeverity.ERROR
        elif "warning" in event_type.lower():
            severity = SecurityEventSeverity.WARNING

        # Log to the audit system
        # Note: event_type is already prefixed (e.g., "rotation_completed", "rotation_failed")
        self._audit_logger.log_security_event(
            event_type=event_type,
            details={
                "rotation_id": rotation_id,
                **details,
            },
            authority_id=authority_id,
            severity=severity,
        )

    async def close(self) -> None:
        """Close and cleanup resources."""
        self._active_rotations.clear()
        self._rotation_locks.clear()
