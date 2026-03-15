# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Hold/Approve workflow for HELD actions.

When trust_check returns HELD, a HoldRecord is created. The human
resolves it via CLI (approve/deny), creating an audit anchor.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from trustplane._locking import file_lock

if TYPE_CHECKING:
    from trustplane.store import TrustPlaneStore

logger = logging.getLogger(__name__)


@dataclass
class HoldRecord:
    """A held action awaiting human resolution."""

    hold_id: str
    action: str
    resource: str
    context: dict
    reason: str
    status: str = "pending"  # pending / approved / denied
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    resolution_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "hold_id": self.hold_id,
            "action": self.action,
            "resource": self.resource,
            "context": self.context,
            "reason": self.reason,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
            "resolution_reason": self.resolution_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HoldRecord":
        return cls(
            hold_id=data["hold_id"],
            action=data["action"],
            resource=data["resource"],
            context=data.get("context", {}),
            reason=data["reason"],
            status=data.get("status", "pending"),
            created_at=datetime.fromisoformat(data["created_at"]),
            resolved_at=(
                datetime.fromisoformat(data["resolved_at"])
                if data.get("resolved_at")
                else None
            ),
            resolved_by=data.get("resolved_by"),
            resolution_reason=data.get("resolution_reason"),
        )


def generate_hold_id(action: str, resource: str) -> str:
    """Generate a unique hold ID with random nonce to prevent collisions."""
    now = datetime.now(timezone.utc).isoformat()
    nonce = secrets.token_hex(4)
    content = f"hold:{action}:{resource}:{now}:{nonce}"
    return f"hold-{hashlib.sha256(content.encode()).hexdigest()[:12]}"


class HoldManager:
    """Manages held actions in the trust plane directory.

    Accepts an optional ``store`` parameter (any object satisfying the
    :class:`~trustplane.store.TrustPlaneStore` protocol).  When *store*
    is ``None`` (the default), a :class:`FileSystemTrustPlaneStore` is
    created internally for backward compatibility.
    """

    def __init__(
        self,
        trust_dir: Path,
        store: "TrustPlaneStore | None" = None,
    ) -> None:
        from trustplane.store.filesystem import FileSystemTrustPlaneStore

        if store is not None:
            self._store = store
        else:
            self._store = FileSystemTrustPlaneStore(trust_dir)
            self._store.initialize()
        self._holds_dir = trust_dir / "holds"
        self._holds_dir.mkdir(parents=True, exist_ok=True)
        self._lock_path = self._holds_dir / ".lock"

    def create_hold(
        self, action: str, resource: str, reason: str, context: dict | None = None
    ) -> HoldRecord:
        """Create a new hold for a HELD action."""
        hold = HoldRecord(
            hold_id=generate_hold_id(action, resource),
            action=action,
            resource=resource,
            context=context or {},
            reason=reason,
        )
        with file_lock(self._lock_path):
            self._store.store_hold(hold)
        logger.info("Created hold %s for action '%s'", hold.hold_id, action)
        return hold

    def resolve(
        self, hold_id: str, approved: bool, resolved_by: str, reason: str
    ) -> HoldRecord:
        """Resolve a pending hold."""
        # Lock for status check + save (prevents TOCTOU: two processes
        # both see "pending" and both resolve the same hold)
        with file_lock(self._lock_path):
            hold = self.get(hold_id)
            if hold.status != "pending":
                raise ValueError(f"Hold {hold_id} is already {hold.status}")

            hold.status = "approved" if approved else "denied"
            hold.resolved_at = datetime.now(timezone.utc)
            hold.resolved_by = resolved_by
            hold.resolution_reason = reason
            self._store.update_hold(hold)
        logger.info("Resolved hold %s: %s by %s", hold_id, hold.status, resolved_by)
        return hold

    def get(self, hold_id: str) -> HoldRecord:
        """Get a hold by ID."""
        return self._store.get_hold(hold_id)

    def list_pending(self) -> list[HoldRecord]:
        """List all pending holds."""
        return self._store.list_holds(status="pending")

    def list_all(self) -> list[HoldRecord]:
        """List all holds (pending and resolved)."""
        return self._store.list_holds()
