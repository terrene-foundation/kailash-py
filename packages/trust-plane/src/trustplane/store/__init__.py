# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""TrustPlane Store Protocol.

Defines the abstract interface (``typing.Protocol``) for trust-plane
record persistence.  The protocol uses **Option A** — the store is
scoped to a single ``trust_dir`` at construction time, so individual
methods do not take ``trust_dir``.

All implementations MUST satisfy the **Store Security Contract**
(see ``packages/trust-plane/CLAUDE.md``):

1. **ATOMIC_WRITES** — every record write is all-or-nothing.
2. **INPUT_VALIDATION** — every ID is validated before filesystem/SQL use.
3. **BOUNDED_RESULTS** — every list method honours a ``limit`` parameter.
4. **PERMISSION_ISOLATION** — records from other projects are invisible.
5. **CONCURRENT_SAFETY** — concurrent reads/writes must not corrupt data.
6. **NO_SILENT_FAILURES** — errors raise named exceptions, never return None.

Concrete implementations:
- ``FileSystemTrustPlaneStore`` (``trustplane.store.filesystem``) — JSON files
- ``SqliteTrustPlaneStore`` (``trustplane.store.sqlite``) — SQLite database
- ``PostgresTrustPlaneStore`` (``trustplane.store.postgres``) — PostgreSQL (requires psycopg3)
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from trustplane.delegation import Delegate, ReviewResolution
from trustplane.holds import HoldRecord
from trustplane.models import DecisionRecord, MilestoneRecord, ProjectManifest

logger = logging.getLogger(__name__)

__all__ = ["TrustPlaneStore", "SqliteTrustPlaneStore", "PostgresTrustPlaneStore"]


@runtime_checkable
class TrustPlaneStore(Protocol):
    """Abstract store protocol for trust-plane records.

    The store is initialised with a ``trust_dir`` at construction
    and all methods operate within that directory scope.

    Implementations MUST satisfy the Store Security Contract
    documented in ``packages/trust-plane/CLAUDE.md``.
    """

    # --- Decision Records ---

    def store_decision(self, record: DecisionRecord) -> None:
        """Persist a decision record.

        Args:
            record: The DecisionRecord to store.

        Raises:
            ValueError: If the decision_id fails validation.
        """
        ...

    def get_decision(self, decision_id: str) -> DecisionRecord:
        """Retrieve a decision record by ID.

        Args:
            decision_id: The decision identifier.

        Returns:
            The matching DecisionRecord.

        Raises:
            KeyError: If the decision is not found.
            ValueError: If the decision_id fails validation.
        """
        ...

    def list_decisions(self, limit: int = 1000) -> list[DecisionRecord]:
        """List decision records, bounded by *limit*.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of DecisionRecord instances (sorted by filename).
        """
        ...

    # --- Milestone Records ---

    def store_milestone(self, record: MilestoneRecord) -> None:
        """Persist a milestone record.

        Raises:
            ValueError: If the milestone_id fails validation.
        """
        ...

    def get_milestone(self, milestone_id: str) -> MilestoneRecord:
        """Retrieve a milestone record by ID.

        Raises:
            KeyError: If the milestone is not found.
            ValueError: If the milestone_id fails validation.
        """
        ...

    def list_milestones(self, limit: int = 1000) -> list[MilestoneRecord]:
        """List milestone records, bounded by *limit*."""
        ...

    # --- Hold Records ---

    def store_hold(self, record: HoldRecord) -> None:
        """Persist a hold record.

        Raises:
            ValueError: If the hold_id fails validation.
        """
        ...

    def get_hold(self, hold_id: str) -> HoldRecord:
        """Retrieve a hold record by ID.

        Raises:
            KeyError: If the hold is not found.
            ValueError: If the hold_id fails validation.
        """
        ...

    def list_holds(
        self, status: str | None = None, limit: int = 1000
    ) -> list[HoldRecord]:
        """List hold records, optionally filtered by *status*.

        Args:
            status: If provided, only return holds with this status.
            limit: Maximum number of records to return.
        """
        ...

    def update_hold(self, record: HoldRecord) -> None:
        """Update an existing hold record (e.g. after resolution).

        Raises:
            ValueError: If the hold_id fails validation.
        """
        ...

    # --- Delegate Records ---

    def store_delegate(self, delegate: Delegate) -> None:
        """Persist a delegate record.

        Raises:
            ValueError: If the delegate_id fails validation.
        """
        ...

    def get_delegate(self, delegate_id: str) -> Delegate:
        """Retrieve a delegate by ID.

        Raises:
            KeyError: If the delegate is not found.
            ValueError: If the delegate_id fails validation.
        """
        ...

    def list_delegates(
        self, active_only: bool = True, limit: int = 1000
    ) -> list[Delegate]:
        """List delegates, optionally filtered by active status.

        Args:
            active_only: If True, exclude revoked/expired delegates.
            limit: Maximum number of records to return.
        """
        ...

    def update_delegate(self, delegate: Delegate) -> None:
        """Update an existing delegate record (e.g. after revocation).

        Raises:
            ValueError: If the delegate_id fails validation.
        """
        ...

    # --- Review Records ---

    def store_review(self, review: ReviewResolution) -> None:
        """Persist a review resolution."""
        ...

    def list_reviews(
        self, hold_id: str | None = None, limit: int = 1000
    ) -> list[ReviewResolution]:
        """List review resolutions, optionally filtered by *hold_id*.

        Args:
            hold_id: If provided, only return reviews for this hold.
            limit: Maximum number of records to return.
        """
        ...

    # --- Manifest ---

    def store_manifest(self, manifest: ProjectManifest) -> None:
        """Persist the project manifest."""
        ...

    def get_manifest(self) -> ProjectManifest:
        """Retrieve the project manifest.

        Raises:
            KeyError: If the manifest has not been stored yet.
        """
        ...

    # --- Anchor JSON (raw dict, not deserialized) ---

    def store_anchor(self, anchor_id: str, data: dict) -> None:
        """Persist an EATP Audit Anchor as raw JSON.

        Args:
            anchor_id: The anchor identifier (validated).
            data: The anchor dict to store.

        Raises:
            ValueError: If the anchor_id fails validation.
        """
        ...

    def get_anchor(self, anchor_id: str) -> dict:
        """Retrieve an anchor by ID.

        Raises:
            KeyError: If the anchor is not found.
            ValueError: If the anchor_id fails validation.
        """
        ...

    def list_anchors(self, limit: int = 1000) -> list[dict]:
        """List anchors, bounded by *limit*."""
        ...

    # --- WAL (Write-Ahead Log for cascade revocation) ---

    def store_wal(self, wal_data: dict) -> None:
        """Persist the cascade-revocation WAL."""
        ...

    def get_wal(self) -> dict | None:
        """Retrieve the WAL if it exists, or None."""
        ...

    def delete_wal(self) -> None:
        """Delete the WAL file.  No-op if absent."""
        ...

    # --- Lifecycle ---

    def initialize(self) -> None:
        """Create any required directories or tables."""
        ...

    def close(self) -> None:
        """Release resources.  No-op for filesystem."""
        ...


# Deferred import to avoid circular dependency — Protocol must be defined first.
from trustplane.store.sqlite import SqliteTrustPlaneStore  # noqa: E402, F401

# Conditional import — PostgreSQL backend requires psycopg3.
try:
    from trustplane.store.postgres import PostgresTrustPlaneStore  # noqa: E402, F401
except ImportError:
    pass  # psycopg not installed — PostgresTrustPlaneStore unavailable
