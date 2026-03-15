# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""AuditSession — session-scoped EATP audit context.

Application-layer convenience that brackets EATP operations. Creates
session-start and session-complete anchors, auto-chains anchors via
parent_anchor_id within the session.

This is NOT a protocol extension — it uses existing EATP AUDIT operation
with disciplined context_data.

Usage:
    session = await project.start_session()
    # ... record decisions within the session ...
    await project.end_session()
"""

import hashlib
import logging
import os
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def _hash_file(path: Path) -> str:
    """SHA-256 hash of a file's contents (symlink-safe)."""
    import errno as _errno

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(path), flags)
    except OSError as e:
        if e.errno == _errno.ELOOP:
            raise OSError(f"Refusing to hash symlink (possible attack): {path}") from e
        raise
    try:
        f = os.fdopen(fd, "rb")
    except Exception:
        os.close(fd)
        raise
    h = hashlib.sha256()
    with f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


_MAX_SNAPSHOT_FILES = 10_000


def _snapshot_files(tracked_paths: list[Path]) -> dict[str, str]:
    """Build a {relative_path: sha256} map for all files under tracked paths.

    Skips symlinks during traversal to prevent following symlinked directories
    outside the intended tree. Individual file hashing uses O_NOFOLLOW.
    Capped at _MAX_SNAPSHOT_FILES to prevent unbounded I/O.
    """
    snapshot: dict[str, str] = {}
    for base in tracked_paths:
        if not base.exists() or base.is_symlink():
            continue
        if base.is_file():
            snapshot[str(base)] = _hash_file(base)
        else:
            for f in sorted(base.rglob("*")):
                if len(snapshot) >= _MAX_SNAPSHOT_FILES:
                    logger.warning(
                        "Snapshot limit reached (%d files), skipping remaining",
                        _MAX_SNAPSHOT_FILES,
                    )
                    return snapshot
                if f.is_symlink():
                    continue
                if f.is_file():
                    snapshot[str(f)] = _hash_file(f)
    return snapshot


def _git_head() -> str | None:
    """Get current git HEAD hash, or None if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def compute_diff(start: dict[str, str], end: dict[str, str]) -> dict[str, list[str]]:
    """Compute file diff between two snapshots."""
    added = [p for p in end if p not in start]
    deleted = [p for p in start if p not in end]
    modified = [p for p in start if p in end and start[p] != end[p]]
    return {
        "added": sorted(added),
        "modified": sorted(modified),
        "deleted": sorted(deleted),
    }


class AuditSession:
    """Session-scoped audit context for TrustPlane.

    Tracks session start/end, action counts, and provides a session_id
    that appears in all anchors created during the session.
    """

    def __init__(
        self,
        session_id: str | None = None,
        tracked_paths: list[Path] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        self.session_id = session_id or self._generate_id(now)
        self.started_at = now
        self.ended_at: datetime | None = None
        self.action_count = 0
        self.decision_count = 0
        self.milestone_count = 0
        self._active = True

        # File change tracking
        self._tracked_paths = tracked_paths or []
        self._start_snapshot: dict[str, str] = {}
        self._end_snapshot: dict[str, str] = {}
        self.git_head_start: str | None = None
        self.git_head_end: str | None = None
        self.files_changed: dict[str, list[str]] | None = None

        if self._tracked_paths:
            self._start_snapshot = _snapshot_files(self._tracked_paths)
            self.git_head_start = _git_head()

    @staticmethod
    def _generate_id(now: datetime) -> str:
        nonce = secrets.token_hex(4)
        content = f"session:{now.isoformat()}:{nonce}"
        return f"sess-{hashlib.sha256(content.encode()).hexdigest()[:12]}"

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def duration_seconds(self) -> float:
        end = self.ended_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()

    def record_action(self, action_type: str) -> None:
        """Track an action within this session."""
        self.action_count += 1
        if action_type == "record_decision":
            self.decision_count += 1
        elif action_type == "create_milestone":
            self.milestone_count += 1

    def end(self) -> None:
        """Mark session as ended and compute file diffs."""
        self.ended_at = datetime.now(timezone.utc)
        self._active = False

        if self._tracked_paths:
            self._end_snapshot = _snapshot_files(self._tracked_paths)
            self.files_changed = compute_diff(self._start_snapshot, self._end_snapshot)
            self.git_head_end = _git_head()

    def context_data(self) -> dict:
        """Session metadata to include in anchor context_data."""
        return {
            "session_id": self.session_id,
            "session_action_count": self.action_count,
        }

    def summary(self) -> dict:
        """Session summary for the session-complete anchor."""
        result: dict = {
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "total_actions": self.action_count,
            "decisions": self.decision_count,
            "milestones": self.milestone_count,
        }
        if self.files_changed is not None:
            result["files_changed"] = self.files_changed
        if self.git_head_start is not None:
            result["git_head_start"] = self.git_head_start
        if self.git_head_end is not None:
            result["git_head_end"] = self.git_head_end
        return result

    def to_dict(self) -> dict:
        d: dict = {
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "active": self._active,
            "action_count": self.action_count,
            "decision_count": self.decision_count,
            "milestone_count": self.milestone_count,
        }
        if self._tracked_paths:
            d["tracked_paths"] = [str(p) for p in self._tracked_paths]
            d["start_snapshot"] = self._start_snapshot
        if self.git_head_start is not None:
            d["git_head_start"] = self.git_head_start
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AuditSession":
        tracked = [Path(p) for p in data.get("tracked_paths", [])]
        session = cls(session_id=data["session_id"], tracked_paths=tracked)
        session.started_at = datetime.fromisoformat(data["started_at"])
        if data.get("ended_at"):
            session.ended_at = datetime.fromisoformat(data["ended_at"])
        session._active = data.get("active", True)
        session.action_count = data.get("action_count", 0)
        session.decision_count = data.get("decision_count", 0)
        session.milestone_count = data.get("milestone_count", 0)
        session._start_snapshot = data.get("start_snapshot", {})
        session.git_head_start = data.get("git_head_start")
        return session
