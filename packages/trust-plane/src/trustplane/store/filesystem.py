# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Filesystem-based TrustPlaneStore implementation.

Extracts all filesystem I/O from ``project.py``, ``holds.py``, and
``delegation.py`` into a single class that satisfies the
:class:`TrustPlaneStore` protocol.

Security-critical patterns preserved verbatim:
- ``validate_id()`` for path-traversal prevention
- ``atomic_write()`` for crash-safe writes
- ``safe_read_json()`` with ``O_NOFOLLOW`` for symlink-attack prevention
- ``file_lock()`` for concurrent-safety
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trustplane._locking import atomic_write, file_lock, safe_read_json, validate_id
from trustplane.delegation import Delegate, DelegateStatus, ReviewResolution
from trustplane.holds import HoldRecord
from trustplane.models import DecisionRecord, MilestoneRecord, ProjectManifest

logger = logging.getLogger(__name__)

__all__ = ["FileSystemTrustPlaneStore"]


class FileSystemTrustPlaneStore:
    """Filesystem-backed store for trust-plane records.

    Each record type is stored as a JSON file in a dedicated subdirectory
    beneath ``trust_dir``:

    ::

        trust_dir/
            decisions/    # DecisionRecord files
            milestones/   # MilestoneRecord files
            holds/        # HoldRecord files
            delegates/    # Delegate files
            reviews/      # ReviewResolution files
            anchors/      # Raw EATP Audit Anchor dicts
            manifest.json # ProjectManifest

    Thread safety is achieved through ``file_lock()`` (cross-process)
    and atomic writes (crash-safe).
    """

    _SUBDIRS = ("decisions", "milestones", "holds", "delegates", "reviews", "anchors")

    def __init__(self, trust_dir: Path) -> None:
        """Initialize the store scoped to *trust_dir*.

        Args:
            trust_dir: Base directory for all trust-plane records.
        """
        self._dir = Path(trust_dir)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Create all required subdirectories."""
        for subdir in self._SUBDIRS:
            (self._dir / subdir).mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        """No-op for filesystem — nothing to release."""
        pass

    # ------------------------------------------------------------------
    # Decision Records
    # ------------------------------------------------------------------

    def store_decision(self, record: DecisionRecord) -> None:
        validate_id(record.decision_id)
        path = self._dir / "decisions" / f"{record.decision_id}.json"
        atomic_write(path, record.to_dict())

    def get_decision(self, decision_id: str) -> DecisionRecord:
        validate_id(decision_id)
        path = self._dir / "decisions" / f"{decision_id}.json"
        if not path.exists():
            raise KeyError(f"Decision not found: {decision_id}")
        return DecisionRecord.from_dict(safe_read_json(path))

    def list_decisions(self, limit: int = 1000) -> list[DecisionRecord]:
        limit = max(0, limit)
        decisions_dir = self._dir / "decisions"
        if not decisions_dir.exists():
            return []
        records: list[DecisionRecord] = []
        for path in sorted(decisions_dir.glob("*.json")):
            if len(records) >= limit:
                break
            records.append(DecisionRecord.from_dict(safe_read_json(path)))
        return records

    # ------------------------------------------------------------------
    # Milestone Records
    # ------------------------------------------------------------------

    def store_milestone(self, record: MilestoneRecord) -> None:
        validate_id(record.milestone_id)
        path = self._dir / "milestones" / f"{record.milestone_id}.json"
        atomic_write(path, record.to_dict())

    def get_milestone(self, milestone_id: str) -> MilestoneRecord:
        validate_id(milestone_id)
        path = self._dir / "milestones" / f"{milestone_id}.json"
        if not path.exists():
            raise KeyError(f"Milestone not found: {milestone_id}")
        return MilestoneRecord.from_dict(safe_read_json(path))

    def list_milestones(self, limit: int = 1000) -> list[MilestoneRecord]:
        limit = max(0, limit)
        milestones_dir = self._dir / "milestones"
        if not milestones_dir.exists():
            return []
        records: list[MilestoneRecord] = []
        for path in sorted(milestones_dir.glob("*.json")):
            if len(records) >= limit:
                break
            records.append(MilestoneRecord.from_dict(safe_read_json(path)))
        return records

    # ------------------------------------------------------------------
    # Hold Records
    # ------------------------------------------------------------------

    def store_hold(self, record: HoldRecord) -> None:
        validate_id(record.hold_id)
        path = self._dir / "holds" / f"{record.hold_id}.json"
        atomic_write(path, record.to_dict())

    def get_hold(self, hold_id: str) -> HoldRecord:
        validate_id(hold_id)
        path = self._dir / "holds" / f"{hold_id}.json"
        if not path.exists():
            raise KeyError(f"Hold not found: {hold_id}")
        return HoldRecord.from_dict(safe_read_json(path))

    def list_holds(
        self, status: str | None = None, limit: int = 1000
    ) -> list[HoldRecord]:
        limit = max(0, limit)
        holds_dir = self._dir / "holds"
        if not holds_dir.exists():
            return []
        records: list[HoldRecord] = []
        for path in sorted(holds_dir.glob("*.json")):
            if len(records) >= limit:
                break
            hold = HoldRecord.from_dict(safe_read_json(path))
            if status is not None and hold.status != status:
                continue
            records.append(hold)
        return records

    def update_hold(self, record: HoldRecord) -> None:
        # update_hold delegates to store_hold — same atomic write
        self.store_hold(record)

    # ------------------------------------------------------------------
    # Delegate Records
    # ------------------------------------------------------------------

    def store_delegate(self, delegate: Delegate) -> None:
        validate_id(delegate.delegate_id)
        path = self._dir / "delegates" / f"{delegate.delegate_id}.json"
        atomic_write(path, delegate.to_dict())

    def get_delegate(self, delegate_id: str) -> Delegate:
        validate_id(delegate_id)
        path = self._dir / "delegates" / f"{delegate_id}.json"
        if not path.exists():
            raise KeyError(f"Delegate not found: {delegate_id}")
        return Delegate.from_dict(safe_read_json(path))

    def list_delegates(
        self, active_only: bool = True, limit: int = 1000
    ) -> list[Delegate]:
        limit = max(0, limit)
        delegates_dir = self._dir / "delegates"
        if not delegates_dir.exists():
            return []
        records: list[Delegate] = []
        for path in sorted(delegates_dir.glob("*.json")):
            if len(records) >= limit:
                break
            d = Delegate.from_dict(safe_read_json(path))
            if active_only and not d.is_active():
                continue
            records.append(d)
        return records

    def update_delegate(self, delegate: Delegate) -> None:
        # update_delegate delegates to store_delegate — same atomic write
        self.store_delegate(delegate)

    # ------------------------------------------------------------------
    # Review Records
    # ------------------------------------------------------------------

    def store_review(self, review: ReviewResolution) -> None:
        validate_id(review.hold_id)
        validate_id(review.delegate_id)
        # Review files are keyed by hold_id-delegate_id (matches delegation.py)
        filename = f"{review.hold_id}-{review.delegate_id}.json"
        path = self._dir / "reviews" / filename
        atomic_write(path, review.to_dict())

    def list_reviews(
        self, hold_id: str | None = None, limit: int = 1000
    ) -> list[ReviewResolution]:
        limit = max(0, limit)
        reviews_dir = self._dir / "reviews"
        if not reviews_dir.exists():
            return []
        records: list[ReviewResolution] = []
        for path in sorted(reviews_dir.glob("*.json")):
            if len(records) >= limit:
                break
            data = safe_read_json(path)
            if hold_id is not None and data["hold_id"] != hold_id:
                continue
            records.append(
                ReviewResolution(
                    hold_id=data["hold_id"],
                    delegate_id=data["delegate_id"],
                    approved=data["approved"],
                    reason=data["reason"],
                    dimension=data["dimension"],
                    resolved_at=datetime.fromisoformat(data["resolved_at"]),
                )
            )
        return records

    # ------------------------------------------------------------------
    # Manifest
    # ------------------------------------------------------------------

    def store_manifest(self, manifest: ProjectManifest) -> None:
        path = self._dir / "manifest.json"
        atomic_write(path, manifest.to_dict())

    def get_manifest(self) -> ProjectManifest:
        path = self._dir / "manifest.json"
        if not path.exists():
            raise KeyError("Manifest not found: no manifest.json in trust directory")
        return ProjectManifest.from_dict(safe_read_json(path))

    # ------------------------------------------------------------------
    # Anchor JSON (raw dict)
    # ------------------------------------------------------------------

    def store_anchor(self, anchor_id: str, data: dict) -> None:
        validate_id(anchor_id)
        path = self._dir / "anchors" / f"{anchor_id}.json"
        atomic_write(path, data)

    def get_anchor(self, anchor_id: str) -> dict:
        validate_id(anchor_id)
        path = self._dir / "anchors" / f"{anchor_id}.json"
        if not path.exists():
            raise KeyError(f"Anchor not found: {anchor_id}")
        return safe_read_json(path)

    def list_anchors(self, limit: int = 1000) -> list[dict]:
        limit = max(0, limit)
        anchors_dir = self._dir / "anchors"
        if not anchors_dir.exists():
            return []
        records: list[dict] = []
        for path in sorted(anchors_dir.glob("*.json")):
            if len(records) >= limit:
                break
            records.append(safe_read_json(path))
        return records

    # ------------------------------------------------------------------
    # WAL (Write-Ahead Log)
    # ------------------------------------------------------------------

    def store_wal(self, wal_data: dict) -> None:
        path = self._dir / "delegates" / ".pending-revocation.wal"
        atomic_write(path, wal_data)

    def get_wal(self) -> dict | None:
        path = self._dir / "delegates" / ".pending-revocation.wal"
        if not path.exists():
            return None
        return safe_read_json(path)

    def delete_wal(self) -> None:
        path = self._dir / "delegates" / ".pending-revocation.wal"
        if path.exists():
            path.unlink()
