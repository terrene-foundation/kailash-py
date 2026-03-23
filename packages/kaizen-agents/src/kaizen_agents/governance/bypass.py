# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Emergency Bypass -- authorized override of envelope constraints.

Per PACT Section 9: an authorized human can temporarily bypass envelope
constraints in emergency situations. All bypass actions are logged with
CRITICAL severity, including reason, authorizer, and duration. Bypasses
expire automatically after the configured duration.
"""

from __future__ import annotations

import logging
import math
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "BypassManager",
    "BypassRecord",
]


@dataclass(frozen=True)
class BypassRecord:
    """A record of an emergency bypass.

    Attributes:
        bypass_id: Unique identifier for this bypass.
        agent_id: The agent whose constraints are bypassed.
        reason: Human-provided justification for the bypass.
        authorizer: Who authorized the bypass (human identity).
        granted_at: Monotonic timestamp when bypass was granted.
        duration_seconds: How long the bypass lasts.
        original_envelope: The envelope before bypass (for restoration).
        expired: Whether the bypass has expired.
        revoked: Whether the bypass was manually revoked.
    """

    bypass_id: str
    agent_id: str
    reason: str
    authorizer: str
    granted_at: float
    duration_seconds: float
    original_envelope: dict[str, Any] = field(default_factory=dict)
    expired: bool = False
    revoked: bool = False

    @property
    def is_active(self) -> bool:
        """Whether the bypass is currently active (not expired, not revoked)."""
        if self.expired or self.revoked:
            return False
        elapsed = time.monotonic() - self.granted_at
        return elapsed < self.duration_seconds


class BypassManager:
    """Manages emergency bypass operations for agent envelopes.

    Thread-safe. Bounded history (maxlen=10000).

    All bypass operations are logged at CRITICAL severity because they
    represent deliberate circumvention of governance controls.

    Usage:
        mgr = BypassManager()
        record = mgr.grant_bypass(
            agent_id="agent-001",
            reason="Production incident P-123",
            authorizer="human@example.com",
            duration_seconds=300.0,
            original_envelope=current_envelope,
        )
        # ... agent operates without envelope constraints ...
        if not mgr.is_bypassed("agent-001"):
            # bypass expired, original constraints restored
            pass
    """

    def __init__(self, maxlen: int = 10000) -> None:
        if maxlen <= 0:
            raise ValueError(f"maxlen must be positive, got {maxlen}")
        self._lock = threading.Lock()
        self._active_bypasses: dict[str, BypassRecord] = {}  # agent_id -> active bypass
        self._history: deque[BypassRecord] = deque(maxlen=maxlen)

    def grant_bypass(
        self,
        agent_id: str,
        reason: str,
        authorizer: str,
        duration_seconds: float,
        original_envelope: dict[str, Any] | None = None,
    ) -> BypassRecord:
        """Grant an emergency bypass for an agent.

        Args:
            agent_id: The agent to bypass.
            reason: Human-provided justification.
            authorizer: Who authorized the bypass.
            duration_seconds: How long the bypass lasts (must be positive).
            original_envelope: The current envelope (saved for restoration).

        Returns:
            The BypassRecord.

        Raises:
            ValueError: If duration_seconds is non-positive or not finite.
            ValueError: If reason or authorizer is empty.
        """
        if not reason:
            raise ValueError("reason must not be empty")
        if not authorizer:
            raise ValueError("authorizer must not be empty")
        if (
            not isinstance(duration_seconds, (int, float))
            or not math.isfinite(float(duration_seconds))
            or duration_seconds <= 0
        ):
            raise ValueError(
                f"duration_seconds must be finite and positive, got {duration_seconds}"
            )

        with self._lock:
            # R1-09: Prevent bypass stacking — reject if agent already has active bypass
            if agent_id in self._active_bypasses:
                existing = self._active_bypasses[agent_id]
                if existing.is_active:
                    raise ValueError(
                        f"Agent '{agent_id}' already has an active bypass "
                        f"(bypass_id={existing.bypass_id}). Revoke it first."
                    )

            record = BypassRecord(
                bypass_id=str(uuid.uuid4()),
                agent_id=agent_id,
                reason=reason,
                authorizer=authorizer,
                granted_at=time.monotonic(),
                duration_seconds=float(duration_seconds),
                original_envelope=original_envelope or {},
            )

            self._active_bypasses[agent_id] = record
            self._history.append(record)

            logger.critical(
                "EMERGENCY BYPASS GRANTED: agent=%s reason='%s' authorizer=%s duration=%ds",
                agent_id,
                reason,
                authorizer,
                duration_seconds,
            )

            return record

    def is_bypassed(self, agent_id: str) -> bool:
        """Check if an agent currently has an active bypass.

        Also handles auto-expiration: if the bypass has expired, it is
        moved from active to expired and this returns False.

        Args:
            agent_id: The agent to check.

        Returns:
            True if the agent has an active (non-expired) bypass.
        """
        with self._lock:
            record = self._active_bypasses.get(agent_id)
            if record is None:
                return False

            if not record.is_active:
                self._expire_bypass(agent_id)
                return False

            return True

    def revoke_bypass(self, agent_id: str) -> BypassRecord | None:
        """Manually revoke an active bypass before expiration.

        Args:
            agent_id: The agent whose bypass to revoke.

        Returns:
            The revoked BypassRecord, or None if no active bypass.
        """
        with self._lock:
            record = self._active_bypasses.pop(agent_id, None)
            if record is None:
                return None

            revoked = BypassRecord(
                bypass_id=record.bypass_id,
                agent_id=record.agent_id,
                reason=record.reason,
                authorizer=record.authorizer,
                granted_at=record.granted_at,
                duration_seconds=record.duration_seconds,
                original_envelope=record.original_envelope,
                revoked=True,
            )

            # Update history
            self._history.append(revoked)

            logger.critical(
                "EMERGENCY BYPASS REVOKED: agent=%s bypass_id=%s",
                agent_id,
                record.bypass_id,
            )

            return revoked

    def get_original_envelope(self, agent_id: str) -> dict[str, Any] | None:
        """Get the original envelope saved when bypass was granted.

        Used to restore constraints after bypass expires.

        Args:
            agent_id: The agent whose original envelope to retrieve.

        Returns:
            The original envelope dict, or None if not found.
        """
        with self._lock:
            # Check active bypasses first
            record = self._active_bypasses.get(agent_id)
            if record is not None:
                return record.original_envelope

            # Check history (most recent first)
            for rec in reversed(self._history):
                if rec.agent_id == agent_id:
                    return rec.original_envelope

            return None

    def check_expirations(self) -> list[BypassRecord]:
        """Check all active bypasses for expiration.

        Call this periodically to enforce time limits.

        Returns:
            List of newly expired BypassRecords.
        """
        with self._lock:
            expired: list[BypassRecord] = []

            for agent_id in list(self._active_bypasses.keys()):
                record = self._active_bypasses[agent_id]
                if not record.is_active:
                    expired_record = self._expire_bypass(agent_id)
                    if expired_record is not None:
                        expired.append(expired_record)

            return expired

    def get_history(self) -> list[BypassRecord]:
        """Return the full bypass history.

        Returns:
            List of all BypassRecords (active, expired, and revoked).
        """
        with self._lock:
            return list(self._history)

    @property
    def active_count(self) -> int:
        """Number of currently active bypasses."""
        with self._lock:
            return sum(1 for r in self._active_bypasses.values() if r.is_active)

    def _expire_bypass(self, agent_id: str) -> BypassRecord | None:
        """Mark a bypass as expired. Caller must hold lock.

        Returns:
            The expired BypassRecord, or None if not found.
        """
        record = self._active_bypasses.pop(agent_id, None)
        if record is None:
            return None

        expired = BypassRecord(
            bypass_id=record.bypass_id,
            agent_id=record.agent_id,
            reason=record.reason,
            authorizer=record.authorizer,
            granted_at=record.granted_at,
            duration_seconds=record.duration_seconds,
            original_envelope=record.original_envelope,
            expired=True,
        )

        self._history.append(expired)

        logger.critical(
            "EMERGENCY BYPASS EXPIRED: agent=%s bypass_id=%s",
            agent_id,
            record.bypass_id,
        )

        return expired
