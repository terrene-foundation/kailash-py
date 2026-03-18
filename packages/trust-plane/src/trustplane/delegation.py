# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Multi-stakeholder delegation for TrustPlane.

Implements EATP delegation chains so multiple humans can share
oversight responsibilities. Each delegate receives a subset of
constraint dimensions they can review and approve.

.. security:: Uses hmac.compare_digest() for all hash comparisons
   to prevent timing side-channel attacks on tamper detection.

Architecture:
  Project Owner (Genesis Record)
    +-- Delegate: Senior Dev (operational, data_access)
    +-- Delegate: Security Lead (communication)
    +-- Delegate: Team Lead (all dimensions, backup)

Delegation follows EATP rules:
- Monotonic tightening: delegates cannot expand permissions
- Depth limit: configurable maximum delegation chain depth (EATP spec default: 10)
- Cascade revocation: revoking a delegate revokes all sub-delegates
- Human origin tracing: every delegation traces back to the human
"""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import json
import logging
import secrets
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from trustplane._locking import (
    atomic_write,
    compute_wal_hash,
    file_lock,
    safe_read_json,
    validate_id,
)
from trustplane.exceptions import RecordNotFoundError
from trustplane.holds import HoldRecord

if TYPE_CHECKING:
    from trustplane.store import TrustPlaneStore

logger = logging.getLogger(__name__)

# Valid constraint dimensions a delegate can be scoped to
VALID_DIMENSIONS = frozenset(
    {"operational", "data_access", "financial", "temporal", "communication"}
)

DEFAULT_MAX_DELEGATION_DEPTH = (
    10  # EATP spec default: prevent unbounded delegation chains
)


class DelegateStatus(Enum):
    """Status of a delegate."""

    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass
class Delegate:
    """A delegate authorized to review actions in specific dimensions."""

    delegate_id: str
    name: str
    dimensions: list[str]
    delegated_by: str  # ID of the delegator (owner or parent delegate)
    status: DelegateStatus = DelegateStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    depth: int = 0  # 0 = directly delegated by owner

    def is_active(self) -> bool:
        """Check if delegate is currently active."""
        if self.status != DelegateStatus.ACTIVE:
            return False
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return False
        return True

    def can_review(self, dimension: str) -> bool:
        """Check if delegate can review actions in a given dimension."""
        if not self.is_active():
            return False
        return dimension in self.dimensions

    def to_dict(self) -> dict[str, Any]:
        return {
            "delegate_id": self.delegate_id,
            "name": self.name,
            "dimensions": self.dimensions,
            "delegated_by": self.delegated_by,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "depth": self.depth,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Delegate:
        for field_name in (
            "delegate_id",
            "name",
            "dimensions",
            "delegated_by",
            "created_at",
        ):
            if field_name not in data:
                raise ValueError(
                    f"Delegate.from_dict: missing required field '{field_name}'"
                )
        depth = data.get("depth", 0)
        if not isinstance(depth, int) or depth < 0:
            raise ValueError(
                f"Delegate.from_dict: 'depth' must be a non-negative integer, got {depth!r}"
            )
        return cls(
            delegate_id=data["delegate_id"],
            name=data["name"],
            dimensions=data["dimensions"],
            delegated_by=data["delegated_by"],
            status=DelegateStatus(data.get("status", "active")),
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=(
                datetime.fromisoformat(data["expires_at"])
                if data.get("expires_at")
                else None
            ),
            revoked_at=(
                datetime.fromisoformat(data["revoked_at"])
                if data.get("revoked_at")
                else None
            ),
            depth=depth,
        )


@dataclass
class ReviewResolution:
    """Result of a delegate reviewing a held action."""

    hold_id: str
    delegate_id: str
    approved: bool
    reason: str
    dimension: str
    resolved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "hold_id": self.hold_id,
            "delegate_id": self.delegate_id,
            "approved": self.approved,
            "reason": self.reason,
            "dimension": self.dimension,
            "resolved_at": self.resolved_at.isoformat(),
        }


class DelegationManager:
    """Manages delegates and their review authority.

    Persists delegates to disk and enforces EATP delegation rules:
    - Only valid constraint dimensions
    - Monotonic tightening (subset of delegator's dimensions)
    - Maximum delegation depth
    - Cascade revocation with Audit Anchor per EATP spec

    Accepts an optional ``store`` parameter (any object satisfying the
    :class:`~trustplane.store.TrustPlaneStore` protocol).  When *store*
    is ``None`` (the default), a :class:`FileSystemTrustPlaneStore` is
    created internally for backward compatibility.
    """

    def __init__(
        self,
        trust_dir: Path,
        audit_callback: Callable[[str, str, dict[str, Any]], None] | None = None,
        max_depth: int = DEFAULT_MAX_DELEGATION_DEPTH,
        store: TrustPlaneStore | None = None,
    ) -> None:
        """Initialize delegation manager.

        Args:
            trust_dir: Path to trust-plane directory
            audit_callback: Optional callback for creating Audit Anchors.
                Called as audit_callback(action, resource, context_data)
                for each revocation during cascade. If None, revocations
                are persisted but no Audit Anchors are created.
            max_depth: Maximum delegation chain depth (default: 10 per EATP spec).
                A depth of 0 means only direct owner delegation, no sub-delegation.
            store: Optional TrustPlaneStore implementation. If None, a
                FileSystemTrustPlaneStore is created for backward compatibility.
        """
        from trustplane.store.filesystem import FileSystemTrustPlaneStore

        if store is not None:
            self._store = store
        else:
            self._store = FileSystemTrustPlaneStore(trust_dir)
            self._store.initialize()
        self._delegates_dir = trust_dir / "delegates"
        self._delegates_dir.mkdir(parents=True, exist_ok=True)
        self._reviews_dir = trust_dir / "reviews"
        self._reviews_dir.mkdir(parents=True, exist_ok=True)
        self._lock_path = self._delegates_dir / ".lock"
        self._reviews_lock_path = self._reviews_dir / ".lock"
        self._audit_callback = audit_callback
        self._max_depth = max_depth

    def add_delegate(
        self,
        name: str,
        dimensions: list[str],
        delegated_by: str = "owner",
        expires_at: datetime | None = None,
        parent_delegate_id: str | None = None,
    ) -> Delegate:
        """Add a new delegate with specific dimension scope.

        Args:
            name: Human-readable name for the delegate
            dimensions: List of constraint dimensions this delegate can review
            delegated_by: ID of the delegator
            expires_at: Optional expiry for the delegation
            parent_delegate_id: If sub-delegating, the parent delegate's ID

        Returns:
            The created Delegate

        Raises:
            ValueError: If dimensions are invalid or depth exceeded
        """
        # Validate dimensions (can do outside lock — static check)
        invalid = set(dimensions) - VALID_DIMENSIONS
        if invalid:
            raise ValueError(
                f"Invalid dimensions: {invalid}. Valid: {sorted(VALID_DIMENSIONS)}"
            )

        if not dimensions:
            raise ValueError("At least one dimension required")

        # Lock for parent validation + save (prevents TOCTOU: parent
        # revoked between validation and delegate creation)
        with file_lock(self._lock_path):
            depth = 0
            if parent_delegate_id:
                parent = self.get_delegate(parent_delegate_id)
                if not parent.is_active():
                    raise ValueError(
                        f"Parent delegate '{parent_delegate_id}' is not active"
                    )
                parent_dims = set(parent.dimensions)
                if not set(dimensions).issubset(parent_dims):
                    raise ValueError(
                        f"Dimensions {set(dimensions) - parent_dims} not in "
                        f"parent delegate's scope {parent_dims}"
                    )
                depth = parent.depth + 1
                delegated_by = parent_delegate_id

            if depth >= self._max_depth:
                raise ValueError(
                    f"Delegation depth {depth} exceeds maximum {self._max_depth}"
                )

            now = datetime.now(timezone.utc)
            nonce = secrets.token_hex(4)
            content = f"delegate:{name}:{now.isoformat()}:{nonce}"
            delegate_id = f"del-{hashlib.sha256(content.encode()).hexdigest()[:12]}"

            delegate = Delegate(
                delegate_id=delegate_id,
                name=name,
                dimensions=dimensions,
                delegated_by=delegated_by,
                expires_at=expires_at,
                depth=depth,
            )
            self._store.store_delegate(delegate)

        logger.info(
            "Added delegate '%s' (id: %s) for dimensions: %s",
            name,
            delegate_id,
            dimensions,
        )
        return delegate

    def get_delegate(self, delegate_id: str) -> Delegate:
        """Get a delegate by ID."""
        return self._store.get_delegate(delegate_id)

    def list_delegates(self, active_only: bool = True) -> list[Delegate]:
        """List all delegates."""
        return self._store.list_delegates(active_only=active_only)

    def find_reviewers(self, dimension: str) -> list[Delegate]:
        """Find active delegates who can review a given dimension."""
        return [d for d in self.list_delegates() if d.can_review(dimension)]

    def revoke_delegate(self, delegate_id: str, reason: str = "") -> list[str]:
        """Revoke a delegate and cascade to all sub-delegates.

        Implements EATP cascade revocation — revoking a delegate
        automatically revokes everyone they delegated to.

        Uses a write-ahead log (WAL) so that if the process crashes
        mid-cascade, recovery can complete the revocation.

        Returns:
            List of all revoked delegate IDs (including cascaded)
        """
        with file_lock(self._lock_path):
            # 1. Build the revocation plan
            plan = self._build_revocation_plan(delegate_id)

            # 2. Write WAL before executing (with content hash for tamper detection)
            wal_data = {
                "root_delegate_id": delegate_id,
                "planned_revocations": plan,
                "reason": reason,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            wal_data["content_hash"] = compute_wal_hash(wal_data)
            self._store.store_wal(wal_data)

            # 3. Execute cascade
            revoked_ids: list[str] = []
            self._cascade_revoke(delegate_id, revoked_ids)

            # 4. Clear WAL on success
            self._store.delete_wal()

        logger.info(
            "Revoked delegate %s (cascade: %d total)",
            delegate_id,
            len(revoked_ids),
        )
        return revoked_ids

    def _build_revocation_plan(self, delegate_id: str) -> list[str]:
        """Find all delegates in the revocation cascade (iterative).

        Uses a work queue instead of recursion to prevent stack overflow
        on deep or corrupted delegation chains. Tracks visited IDs to
        prevent infinite loops from circular chains (defensive —
        add_delegate prevents these, but a corrupted delegate file
        could create one).
        """
        visited: set[str] = set()
        plan: list[str] = []
        queue: deque[str] = deque([delegate_id])
        while queue:
            did = queue.popleft()
            if did in visited:
                continue
            visited.add(did)
            plan.append(did)
            for d in self._all_delegates():
                if d.delegated_by == did and d.status == DelegateStatus.ACTIVE:
                    if d.delegate_id not in visited:
                        queue.append(d.delegate_id)
        return plan

    def recover_pending_revocations(self) -> list[str]:
        """Resume any incomplete cascade revocations.

        Call on startup or after crash recovery. If a previous revocation
        was interrupted (WAL file exists), completes the cascade.

        Returns:
            List of delegate IDs revoked during recovery (empty if no WAL)
        """
        with file_lock(self._lock_path):
            try:
                wal = self._store.get_wal()
            except (json.JSONDecodeError, OSError) as e:
                # WAL file exists but contains invalid JSON — corrupted
                logger.critical(
                    "WAL file corrupted (%s); removing to unblock operations. "
                    "Manual review of delegate states may be needed.",
                    e,
                )
                self._store.delete_wal()
                return []

            if wal is None:
                return []

            try:
                # Verify WAL content hash to detect tampering.
                # All WALs created by TrustPlane include content_hash.
                # A missing hash means either tampering (attacker stripped it)
                # or a WAL from a pre-hash version. We reject missing hashes
                # because all TrustPlane WALs have always included them since
                # the feature was added — there is no legitimate pre-hash WAL
                # in production.
                stored_hash = wal.get("content_hash")
                if stored_hash is None:
                    logger.critical(
                        "WAL missing content_hash (possible tampering); "
                        "removing WAL. Manual review of delegate states needed.",
                    )
                    self._store.delete_wal()
                    return []
                expected_hash = compute_wal_hash(wal)
                if not hmac_mod.compare_digest(stored_hash, expected_hash):
                    logger.critical(
                        "WAL content hash mismatch (tampering detected); "
                        "removing WAL. Manual review of delegate states needed.",
                    )
                    self._store.delete_wal()
                    return []

                revoked_ids: list[str] = []
                for did in wal["planned_revocations"]:
                    try:
                        d = self.get_delegate(did)
                        if d.status == DelegateStatus.ACTIVE:
                            d.status = DelegateStatus.REVOKED
                            d.revoked_at = datetime.now(timezone.utc)
                            self._store.update_delegate(d)
                            revoked_ids.append(did)
                    except RecordNotFoundError:
                        pass  # Already gone

                self._store.delete_wal()

            except (json.JSONDecodeError, OSError) as e:
                # Corrupted WAL — log and remove to unblock future operations
                logger.critical(
                    "WAL file corrupted (%s); removing to unblock operations. "
                    "Manual review of delegate states may be needed.",
                    e,
                )
                self._store.delete_wal()
                return []

        if revoked_ids:
            logger.info(
                "Recovered pending revocation: %d delegates revoked",
                len(revoked_ids),
            )
        return revoked_ids

    def _cascade_revoke(self, delegate_id: str, revoked_ids: list[str]) -> None:
        """Iteratively revoke a delegate and all sub-delegates.

        Uses a work queue instead of recursion to prevent stack overflow
        on deep or corrupted delegation chains.

        Per EATP spec: records an Audit Anchor for each revocation
        via the audit_callback (if provided).
        """
        visited: set[str] = set()
        queue: deque[str] = deque([delegate_id])

        while queue:
            did = queue.popleft()
            if did in visited:
                continue
            visited.add(did)

            try:
                delegate = self.get_delegate(did)
            except RecordNotFoundError:
                continue

            if delegate.status == DelegateStatus.REVOKED:
                continue

            delegate.status = DelegateStatus.REVOKED
            delegate.revoked_at = datetime.now(timezone.utc)
            self._store.update_delegate(delegate)
            revoked_ids.append(did)

            # Record Audit Anchor for this revocation (EATP spec requirement)
            if self._audit_callback is not None:
                try:
                    self._audit_callback(
                        "revoke_delegate",
                        f"delegate/{did}",
                        {
                            "delegate_id": did,
                            "delegate_name": delegate.name,
                            "dimensions": delegate.dimensions,
                            "depth": delegate.depth,
                            "cascade": len(revoked_ids) > 1,
                        },
                    )
                except Exception:
                    logger.warning(
                        "Audit callback failed for delegate %s; revocation proceeds",
                        did,
                        exc_info=True,
                    )

            # Queue sub-delegates for revocation
            for d in self._all_delegates():
                if d.delegated_by == did and d.status == DelegateStatus.ACTIVE:
                    if d.delegate_id not in visited:
                        queue.append(d.delegate_id)

    def resolve_hold(
        self,
        hold: HoldRecord,
        delegate_id: str,
        approved: bool,
        reason: str,
        dimension: str = "operational",
    ) -> ReviewResolution:
        """Resolve a held action as a delegate.

        Args:
            hold: The HoldRecord to resolve
            delegate_id: ID of the resolving delegate
            approved: True to approve, False to deny
            reason: Explanation for the resolution
            dimension: Which constraint dimension this falls under

        Returns:
            ReviewResolution record

        Raises:
            ValueError: If delegate cannot review this dimension
            KeyError: If delegate not found
        """
        # Validate delegate AND persist review under the SAME lock scope.
        # This prevents TOCTOU: delegate revoked between validation and
        # resolution write. We use the delegates lock (not reviews lock)
        # because the critical invariant is delegate status.
        with file_lock(self._lock_path):
            delegate = self.get_delegate(delegate_id)

            if not delegate.is_active():
                raise ValueError(
                    f"Delegate '{delegate.name}' is not active "
                    f"(status: {delegate.status.value})"
                )

            if not delegate.can_review(dimension):
                raise ValueError(
                    f"Delegate '{delegate.name}' cannot review dimension "
                    f"'{dimension}'. Authorized for: {delegate.dimensions}"
                )

            resolution = ReviewResolution(
                hold_id=hold.hold_id,
                delegate_id=delegate_id,
                approved=approved,
                reason=reason,
                dimension=dimension,
            )

            # Persist the review inside the same lock scope
            self._store.store_review(resolution)

        logger.info(
            "Delegate '%s' %s hold %s (dimension: %s)",
            delegate.name,
            "approved" if approved else "denied",
            hold.hold_id,
            dimension,
        )
        return resolution

    def get_reviews(self, hold_id: str | None = None) -> list[ReviewResolution]:
        """Get review resolutions, optionally filtered by hold ID."""
        return self._store.list_reviews(hold_id=hold_id)

    def _all_delegates(self) -> list[Delegate]:
        """List all delegates including inactive ones."""
        return self.list_delegates(active_only=False)
