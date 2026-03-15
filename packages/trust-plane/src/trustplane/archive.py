# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Store archival/cleanup for old trust-plane records.

Moves old decisions, milestones, and holds to ZIP bundles in
``{trust_dir}/archives/``, keeping them verifiable via a manifest
that includes SHA-256 hashes of all archived record IDs.

Archive bundles contain:
- ``manifest.json`` -- record counts, date range, SHA-256 of contents
- ``decisions.json`` -- archived decision records
- ``milestones.json`` -- archived milestone records
- ``holds.json`` -- archived hold records (resolved only)

Security notes:
- All bundle IDs are validated via ``validate_id()`` before use.
- ZIP files are written atomically (temp file + rename) to prevent
  partial writes on crash.
- Manifest includes SHA-256 of all archived record IDs for chain
  integrity verification.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from trustplane._locking import validate_id
from trustplane.exceptions import TrustPlaneError
from trustplane.holds import HoldRecord
from trustplane.models import DecisionRecord, MilestoneRecord
from trustplane.store import TrustPlaneStore

logger = logging.getLogger(__name__)

__all__ = [
    "ArchiveBundle",
    "ArchiveError",
    "create_archive",
    "list_archives",
    "restore_archive",
]


class ArchiveError(TrustPlaneError):
    """Raised when an archive operation fails."""


@dataclass
class ArchiveBundle:
    """Metadata for an archive bundle.

    Attributes:
        bundle_id: Unique identifier for the archive (alphanumeric, hyphens,
            underscores only).
        created_at: When the archive was created (UTC).
        record_counts: Mapping of record type to count archived.
        date_range: Tuple of (earliest, latest) record timestamps in the
            archive as ISO-8601 strings.
        sha256_hash: SHA-256 hex digest of all archived record IDs
            (sorted, JSON-encoded) for chain integrity verification.
    """

    bundle_id: str
    created_at: datetime
    record_counts: dict[str, int]
    date_range: tuple[str, str]
    sha256_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "created_at": self.created_at.isoformat(),
            "record_counts": self.record_counts,
            "date_range": list(self.date_range),
            "sha256_hash": self.sha256_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArchiveBundle":
        for field_name in (
            "bundle_id",
            "created_at",
            "record_counts",
            "date_range",
            "sha256_hash",
        ):
            if field_name not in data:
                raise ValueError(
                    f"ArchiveBundle.from_dict: missing required field '{field_name}'"
                )
        dr = data["date_range"]
        if not isinstance(dr, (list, tuple)) or len(dr) != 2:
            raise ValueError(
                "ArchiveBundle.from_dict: 'date_range' must be a list of two ISO strings"
            )
        return cls(
            bundle_id=data["bundle_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            record_counts=data["record_counts"],
            date_range=(str(dr[0]), str(dr[1])),
            sha256_hash=data["sha256_hash"],
        )


def _archives_dir(trust_dir: str | Path) -> Path:
    """Return the archives subdirectory, creating it if needed."""
    d = Path(trust_dir) / "archives"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _collect_old_records(
    store: TrustPlaneStore, cutoff: datetime
) -> tuple[list[dict], list[dict], list[dict]]:
    """Collect records older than *cutoff* from the store.

    Returns:
        (decisions, milestones, holds) as lists of dicts.
    """
    decisions_raw = store.list_decisions(limit=100_000)
    milestones_raw = store.list_milestones(limit=100_000)
    holds_raw = store.list_holds(limit=100_000)

    old_decisions = [d.to_dict() for d in decisions_raw if d.timestamp < cutoff]
    old_milestones = [m.to_dict() for m in milestones_raw if m.timestamp < cutoff]
    # Only archive resolved holds (not pending ones)
    old_holds = [
        h.to_dict()
        for h in holds_raw
        if h.created_at < cutoff and h.status != "pending"
    ]
    return old_decisions, old_milestones, old_holds


def _delete_records_from_store(
    store: TrustPlaneStore,
    decisions: list[dict],
    milestones: list[dict],
    holds: list[dict],
) -> None:
    """Delete archived records from the store.

    Handles both SQLite and filesystem backends.
    """
    from trustplane.store.sqlite import SqliteTrustPlaneStore

    if isinstance(store, SqliteTrustPlaneStore):
        conn = store._get_connection()
        for d in decisions:
            conn.execute(
                "DELETE FROM decisions WHERE decision_id = ?",
                (d["decision_id"],),
            )
        for m in milestones:
            conn.execute(
                "DELETE FROM milestones WHERE milestone_id = ?",
                (m["milestone_id"],),
            )
        for h in holds:
            conn.execute(
                "DELETE FROM holds WHERE hold_id = ?",
                (h["hold_id"],),
            )
        conn.commit()
    else:
        # FileSystemTrustPlaneStore: delete JSON files from subdirectories
        from trustplane.store.filesystem import FileSystemTrustPlaneStore

        if isinstance(store, FileSystemTrustPlaneStore):
            base = store._dir
            for d in decisions:
                p = base / "decisions" / f"{d['decision_id']}.json"
                if p.exists():
                    p.unlink()
            for m in milestones:
                p = base / "milestones" / f"{m['milestone_id']}.json"
                if p.exists():
                    p.unlink()
            for h in holds:
                p = base / "holds" / f"{h['hold_id']}.json"
                if p.exists():
                    p.unlink()
        else:
            raise ArchiveError(
                f"Unsupported store backend for archival: {type(store).__name__}"
            )


def _compute_integrity_hash(
    decisions: list[dict], milestones: list[dict], holds: list[dict]
) -> str:
    """Compute SHA-256 of all archived record IDs for chain integrity."""
    all_ids: list[str] = []
    for d in decisions:
        all_ids.append(d["decision_id"])
    for m in milestones:
        all_ids.append(m["milestone_id"])
    for h in holds:
        all_ids.append(h["hold_id"])
    all_ids.sort()
    payload = json.dumps(all_ids, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _find_date_range(
    decisions: list[dict], milestones: list[dict], holds: list[dict]
) -> tuple[str, str]:
    """Find the earliest and latest timestamps across all records."""
    timestamps: list[str] = []
    for d in decisions:
        timestamps.append(d["timestamp"])
    for m in milestones:
        timestamps.append(m["timestamp"])
    for h in holds:
        timestamps.append(h["created_at"])
    if not timestamps:
        now = datetime.now(timezone.utc).isoformat()
        return (now, now)
    timestamps.sort()
    return (timestamps[0], timestamps[-1])


def _generate_bundle_id() -> str:
    """Generate a unique bundle ID based on timestamp."""
    now = datetime.now(timezone.utc)
    return f"archive-{now.strftime('%Y%m%d-%H%M%S')}"


def create_archive(
    store: TrustPlaneStore,
    trust_dir: str | Path,
    max_age_days: int = 365,
) -> ArchiveBundle:
    """Create an archive of records older than *max_age_days*.

    Collects old decisions, milestones, and resolved holds from the store,
    writes them to a ZIP bundle in ``{trust_dir}/archives/``, and deletes
    them from the live store.

    Args:
        store: The trust-plane store to archive from (SQLite or filesystem).
        trust_dir: Trust plane directory (archives go in ``archives/`` subdir).
        max_age_days: Archive records older than this many days (default 365).

    Returns:
        An ``ArchiveBundle`` describing what was archived.

    Raises:
        ArchiveError: If no records qualify for archival or the write fails.
    """
    if max_age_days < 1:
        raise ArchiveError("max_age_days must be at least 1")

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    decisions, milestones, holds = _collect_old_records(store, cutoff)

    total = len(decisions) + len(milestones) + len(holds)
    if total == 0:
        raise ArchiveError(
            f"No records older than {max_age_days} days found to archive"
        )

    bundle_id = _generate_bundle_id()
    validate_id(bundle_id)

    integrity_hash = _compute_integrity_hash(decisions, milestones, holds)
    date_range = _find_date_range(decisions, milestones, holds)
    created_at = datetime.now(timezone.utc)

    record_counts = {
        "decisions": len(decisions),
        "milestones": len(milestones),
        "holds": len(holds),
    }

    manifest_data = {
        "bundle_id": bundle_id,
        "created_at": created_at.isoformat(),
        "record_counts": record_counts,
        "date_range": list(date_range),
        "sha256_hash": integrity_hash,
        "archive_format": "zip",
        "max_age_days": max_age_days,
        "cutoff_date": cutoff.isoformat(),
    }

    # Write ZIP atomically: temp file + rename
    archives = _archives_dir(trust_dir)
    zip_path = archives / f"{bundle_id}.zip"

    fd, tmp_path = tempfile.mkstemp(
        dir=str(archives),
        prefix=f".{bundle_id}.",
        suffix=".tmp",
    )
    try:
        os.close(fd)
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "manifest.json",
                json.dumps(manifest_data, indent=2, default=str),
            )
            zf.writestr(
                "decisions.json",
                json.dumps(decisions, indent=2, default=str),
            )
            zf.writestr(
                "milestones.json",
                json.dumps(milestones, indent=2, default=str),
            )
            zf.writestr(
                "holds.json",
                json.dumps(holds, indent=2, default=str),
            )
        os.replace(tmp_path, str(zip_path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    # Delete archived records from the live store
    _delete_records_from_store(store, decisions, milestones, holds)

    logger.info(
        "Created archive %s: %d decisions, %d milestones, %d holds",
        bundle_id,
        len(decisions),
        len(milestones),
        len(holds),
    )

    return ArchiveBundle(
        bundle_id=bundle_id,
        created_at=created_at,
        record_counts=record_counts,
        date_range=date_range,
        sha256_hash=integrity_hash,
    )


def list_archives(trust_dir: str | Path) -> list[ArchiveBundle]:
    """List all archive bundles in ``{trust_dir}/archives/``.

    Args:
        trust_dir: Trust plane directory.

    Returns:
        List of ``ArchiveBundle`` objects sorted by creation time (oldest first).
    """
    archives = _archives_dir(trust_dir)
    bundles: list[ArchiveBundle] = []

    for zip_path in sorted(archives.glob("archive-*.zip")):
        try:
            with zipfile.ZipFile(str(zip_path), "r") as zf:
                manifest_bytes = zf.read("manifest.json")
                manifest = json.loads(manifest_bytes)
                bundles.append(ArchiveBundle.from_dict(manifest))
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("Skipping corrupt archive %s: %s", zip_path.name, exc)

    return bundles


def restore_archive(
    store: TrustPlaneStore,
    trust_dir: str | Path,
    bundle_id: str,
) -> int:
    """Restore records from an archive bundle back into the live store.

    The archive ZIP is deleted after successful restoration.

    Args:
        store: The trust-plane store to restore into (SQLite or filesystem).
        trust_dir: Trust plane directory.
        bundle_id: The bundle identifier to restore.

    Returns:
        Number of records restored.

    Raises:
        ArchiveError: If the bundle is not found, corrupt, or integrity
            verification fails.
        ValueError: If the bundle_id fails validation.
    """
    validate_id(bundle_id)

    archives = _archives_dir(trust_dir)
    zip_path = archives / f"{bundle_id}.zip"

    if not zip_path.exists():
        raise ArchiveError(f"Archive bundle not found: {bundle_id}")

    try:
        with zipfile.ZipFile(str(zip_path), "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            decisions = json.loads(zf.read("decisions.json"))
            milestones = json.loads(zf.read("milestones.json"))
            holds = json.loads(zf.read("holds.json"))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        raise ArchiveError(f"Corrupt archive bundle {bundle_id}: {exc}") from exc

    # Verify integrity hash (constant-time comparison — Pattern 8)
    import hmac as hmac_mod

    computed_hash = _compute_integrity_hash(decisions, milestones, holds)
    expected_hash = manifest.get("sha256_hash", "")
    if not hmac_mod.compare_digest(computed_hash, expected_hash):
        raise ArchiveError(
            f"Integrity verification failed for {bundle_id}: "
            f"expected {expected_hash}, computed {computed_hash}"
        )

    # Restore records to the store
    restored = 0
    for d_dict in decisions:
        record = DecisionRecord.from_dict(d_dict)
        store.store_decision(record)
        restored += 1

    for m_dict in milestones:
        record = MilestoneRecord.from_dict(m_dict)
        store.store_milestone(record)
        restored += 1

    for h_dict in holds:
        record = HoldRecord.from_dict(h_dict)
        store.store_hold(record)
        restored += 1

    # Remove the archive ZIP after successful restore
    os.unlink(str(zip_path))

    logger.info("Restored %d records from archive %s", restored, bundle_id)
    return restored
