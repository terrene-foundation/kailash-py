# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Migration utilities for TrustPlane project upgrades.

Handles conversion from pre-v0.2.1 (InMemoryTrustStore) projects to the
FilesystemStore format with parent-chained anchors, and from filesystem-backed
projects to SQLite-backed storage.

Usage:
    from trustplane.migrate import migrate_project, migrate_to_sqlite
    result = await migrate_project("workspaces/my-project/trust-plane")
    result = migrate_to_sqlite("workspaces/my-project/trust-plane")
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from eatp import CapabilityRequest, TrustKeyManager, TrustOperations
from eatp.authority import AuthorityPermission, OrganizationalAuthority
from eatp.chain import AuthorityType, CapabilityType
from eatp.store.filesystem import FilesystemStore

from trustplane._locking import atomic_write, safe_read_json, validate_id
from trustplane.project import _AuthorityRegistry, _load_keys

logger = logging.getLogger(__name__)

__all__ = ["migrate_project", "migrate_to_sqlite"]

MIGRATION_MARKER = "migrated_to_filesystem_store"


async def migrate_project(trust_dir: str | Path) -> dict:
    """Migrate a pre-v0.2.1 project to FilesystemStore format.

    Performs the following:
    1. Reads genesis.json and keys/ to reconstruct identity
    2. Creates chains/ directory with FilesystemStore
    3. Establishes the chain in FilesystemStore using original genesis data
    4. Adds parent_anchor_id links to existing anchor files
    5. Writes migration marker to manifest.json

    Args:
        trust_dir: Path to the trust-plane directory

    Returns:
        Migration result dict with status and details

    Raises:
        FileNotFoundError: If no project exists at the path
    """
    trust_path = Path(trust_dir)
    manifest_path = trust_path / "manifest.json"
    genesis_path = trust_path / "genesis.json"

    if not manifest_path.exists():
        raise FileNotFoundError(f"No project found at {trust_path}")

    # Check if already migrated
    manifest_data = safe_read_json(manifest_path)

    if manifest_data.get("metadata", {}).get(MIGRATION_MARKER):
        return {
            "status": "already_migrated",
            "project_name": manifest_data["project_name"],
            "message": "Project already uses FilesystemStore.",
        }

    # Check if chains/ already exists with data (created by new load())
    chains_dir = trust_path / "chains"
    if chains_dir.exists() and any(chains_dir.iterdir()):
        # Already has FilesystemStore data — just mark as migrated
        manifest_data.setdefault("metadata", {})[MIGRATION_MARKER] = True
        atomic_write(manifest_path, manifest_data)
        return {
            "status": "marked",
            "project_name": manifest_data["project_name"],
            "message": "FilesystemStore already present. Migration marker added.",
        }

    # Verify genesis exists (needed for chain validity)
    if not genesis_path.exists():
        return {
            "status": "error",
            "message": "genesis.json missing — cannot migrate.",
        }

    # Reconstruct EATP infrastructure
    chains_dir.mkdir(parents=True, exist_ok=True)
    store = FilesystemStore(str(chains_dir))
    await store.initialize()

    key_mgr = TrustKeyManager()
    project_id = manifest_data["project_id"]
    key_id = f"key-{project_id}"

    keys_dir = trust_path / "keys"
    try:
        private_key, public_key = _load_keys(keys_dir)
    except FileNotFoundError:
        return {
            "status": "error",
            "message": "keys/ directory missing — cannot migrate without signing keys.",
        }

    key_mgr.register_key(key_id, private_key)

    # F4: Remove private key from local scope after registration
    del private_key

    authority_id = f"author-{project_id}"
    registry = _AuthorityRegistry()
    registry.register(
        OrganizationalAuthority(
            id=authority_id,
            name=manifest_data["author"],
            authority_type=AuthorityType.HUMAN,
            public_key=public_key,
            signing_key_id=key_id,
            permissions=[
                AuthorityPermission.CREATE_AGENTS,
                AuthorityPermission.DELEGATE_TRUST,
                AuthorityPermission.GRANT_CAPABILITIES,
            ],
        )
    )

    ops = TrustOperations(
        authority_registry=registry,
        key_manager=key_mgr,
        trust_store=store,
    )

    agent_id = f"trust-agent-{project_id}"

    # Establish chain in FilesystemStore
    chain = await ops.establish(
        agent_id=agent_id,
        authority_id=authority_id,
        capabilities=[
            CapabilityRequest(
                capability="draft_content",
                capability_type=CapabilityType.ACTION,
                constraints=["audit_required"],
            ),
            CapabilityRequest(
                capability="record_decision",
                capability_type=CapabilityType.ACTION,
                constraints=["audit_required"],
            ),
            CapabilityRequest(
                capability="cross_reference",
                capability_type=CapabilityType.ACCESS,
            ),
        ],
        constraints=manifest_data.get("constraints", []),
    )

    # Update manifest with new genesis/chain info from the new store
    manifest_data["genesis_id"] = chain.genesis.id
    manifest_data["chain_hash"] = chain.hash()

    # Add parent_anchor_id links to existing anchors
    anchors_dir = trust_path / "anchors"
    anchors_updated = 0
    if anchors_dir.exists():
        anchor_files = sorted(anchors_dir.glob("*.json"))
        parent_id = None
        for af in anchor_files:
            data = safe_read_json(af)

            # Only update if parent_anchor_id is missing
            has_parent = "parent_anchor_id" in data
            if not has_parent:
                data["parent_anchor_id"] = parent_id
                # Also update context if present
                if "context" in data:
                    data["context"]["parent_anchor_id"] = parent_id
                atomic_write(af, data)
                anchors_updated += 1

            parent_id = data.get("anchor_id", af.stem)

    # Mark manifest as migrated
    manifest_data.setdefault("metadata", {})[MIGRATION_MARKER] = True
    atomic_write(manifest_path, manifest_data)

    logger.info(
        "Migrated project '%s' to FilesystemStore (%d anchors updated)",
        manifest_data["project_name"],
        anchors_updated,
    )

    return {
        "status": "migrated",
        "project_name": manifest_data["project_name"],
        "anchors_updated": anchors_updated,
        "message": f"Migration complete. {anchors_updated} anchor(s) updated with parent chain links.",
    }


def migrate_to_sqlite(
    trust_dir: str | Path,
    *,
    dry_run: bool = False,
    confirm_delete: bool = False,
) -> dict[str, Any]:
    """Migrate a filesystem-backed TrustPlane project to SQLite storage.

    Reads all records from ``FileSystemTrustPlaneStore`` and writes them
    into a ``SqliteTrustPlaneStore`` at ``<trust_dir>/trust.db``.

    The migration is atomic: if any record write fails, the SQLite
    database is rolled back and no data is persisted. Filesystem data
    is NOT deleted unless ``confirm_delete=True`` is passed and the
    migration succeeds.

    Args:
        trust_dir: Path to the trust-plane directory.
        dry_run: If True, count records without writing. No database
            is created.
        confirm_delete: If True, delete filesystem record subdirectories
            and ``manifest.json`` after a successful migration.

    Returns:
        A dict with counts per record type and migration status::

            {
                "status": "migrated" | "dry_run" | "already_sqlite" | "error",
                "counts": {"decisions": 3, "milestones": 1, ...},
                "message": "...",
            }

    Raises:
        FileNotFoundError: If no project exists at *trust_dir*.
    """
    from trustplane.store.filesystem import FileSystemTrustPlaneStore
    from trustplane.store.sqlite import SqliteTrustPlaneStore

    trust_path = Path(trust_dir)
    manifest_path = trust_path / "manifest.json"

    if not manifest_path.exists():
        raise FileNotFoundError(f"No project found at {trust_path}")

    manifest_data = safe_read_json(manifest_path)

    # Check if already using SQLite
    if manifest_data.get("metadata", {}).get("store") == "sqlite":
        return {
            "status": "already_sqlite",
            "counts": {},
            "message": "Project already uses SQLite store.",
        }

    # Open the filesystem store and read all records
    fs_store = FileSystemTrustPlaneStore(trust_path)
    fs_store.initialize()

    # Use very large limit to avoid truncating records during migration
    _MIGRATION_LIMIT = 1_000_000
    decisions = fs_store.list_decisions(limit=_MIGRATION_LIMIT)
    milestones = fs_store.list_milestones(limit=_MIGRATION_LIMIT)
    holds = fs_store.list_holds(limit=_MIGRATION_LIMIT)
    delegates = fs_store.list_delegates(active_only=False, limit=_MIGRATION_LIMIT)
    reviews = fs_store.list_reviews(limit=_MIGRATION_LIMIT)
    anchors = fs_store.list_anchors(limit=_MIGRATION_LIMIT)
    wal = fs_store.get_wal()

    # Read manifest from filesystem store if it exists
    try:
        manifest = fs_store.get_manifest()
    except KeyError:
        manifest = None

    counts: dict[str, int] = {
        "decisions": len(decisions),
        "milestones": len(milestones),
        "holds": len(holds),
        "delegates": len(delegates),
        "reviews": len(reviews),
        "anchors": len(anchors),
        "manifest": 1 if manifest is not None else 0,
        "wal": 1 if wal is not None else 0,
    }

    if dry_run:
        return {
            "status": "dry_run",
            "counts": counts,
            "message": "Dry run complete. No changes made.",
        }

    # Create the SQLite store
    db_path = trust_path / "trust.db"
    sqlite_store = SqliteTrustPlaneStore(db_path)
    sqlite_store.initialize()

    # Write all records atomically using raw SQL on a single connection.
    # We must NOT call store_*() methods because each internally calls
    # conn.commit(), which would break the enclosing transaction.
    conn = sqlite_store._get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")

        for record in decisions:
            validate_id(record.decision_id)
            conn.execute(
                "INSERT OR REPLACE INTO decisions (decision_id, data) VALUES (?, ?)",
                (record.decision_id, json.dumps(record.to_dict(), default=str)),
            )
        for record in milestones:
            validate_id(record.milestone_id)
            conn.execute(
                "INSERT OR REPLACE INTO milestones (milestone_id, data) VALUES (?, ?)",
                (record.milestone_id, json.dumps(record.to_dict(), default=str)),
            )
        for record in holds:
            validate_id(record.hold_id)
            conn.execute(
                "INSERT OR REPLACE INTO holds (hold_id, status, data) VALUES (?, ?, ?)",
                (
                    record.hold_id,
                    record.status,
                    json.dumps(record.to_dict(), default=str),
                ),
            )
        for delegate in delegates:
            validate_id(delegate.delegate_id)
            conn.execute(
                "INSERT OR REPLACE INTO delegates (delegate_id, status, data) VALUES (?, ?, ?)",
                (
                    delegate.delegate_id,
                    delegate.status.value,
                    json.dumps(delegate.to_dict(), default=str),
                ),
            )
        for review in reviews:
            validate_id(review.hold_id)
            validate_id(review.delegate_id)
            review_key = f"{review.hold_id}-{review.delegate_id}"
            conn.execute(
                "INSERT OR REPLACE INTO reviews (review_key, hold_id, delegate_id, data) VALUES (?, ?, ?, ?)",
                (
                    review_key,
                    review.hold_id,
                    review.delegate_id,
                    json.dumps(review.to_dict(), default=str),
                ),
            )
        for anchor_data in anchors:
            anchor_id = anchor_data.get("anchor_id", "")
            if anchor_id:
                validate_id(anchor_id)
                conn.execute(
                    "INSERT OR REPLACE INTO anchors (anchor_id, data) VALUES (?, ?)",
                    (anchor_id, json.dumps(anchor_data, default=str)),
                )
        if manifest is not None:
            conn.execute(
                "INSERT OR REPLACE INTO manifest (id, data) VALUES ('manifest', ?)",
                (json.dumps(manifest.to_dict(), default=str),),
            )
        if wal is not None:
            conn.execute(
                "INSERT OR REPLACE INTO delegates_wal (id, data) VALUES ('wal', ?)",
                (json.dumps(wal, default=str),),
            )

        conn.commit()
    except Exception as exc:
        conn.rollback()
        sqlite_store.close()
        logger.error("Migration to SQLite failed: %s", exc)
        return {
            "status": "error",
            "counts": counts,
            "message": f"Migration failed: {exc}",
        }

    # Update manifest metadata to indicate SQLite store
    manifest_data.setdefault("metadata", {})["store"] = "sqlite"
    atomic_write(manifest_path, manifest_data)

    sqlite_store.close()
    fs_store.close()

    # Optionally delete filesystem data
    if confirm_delete:
        _delete_filesystem_records(trust_path)

    logger.info(
        "Migrated project to SQLite: %s (decisions=%d, milestones=%d, "
        "holds=%d, delegates=%d, reviews=%d, anchors=%d)",
        manifest_data.get("project_name", "unknown"),
        counts["decisions"],
        counts["milestones"],
        counts["holds"],
        counts["delegates"],
        counts["reviews"],
        counts["anchors"],
    )

    return {
        "status": "migrated",
        "counts": counts,
        "message": "Migration to SQLite complete.",
    }


def _delete_filesystem_records(trust_path: Path) -> None:
    """Remove filesystem-backed record directories after migration.

    Deletes the six record subdirectories (decisions/, milestones/,
    holds/, delegates/, reviews/, anchors/) but leaves keys/, chains/,
    genesis.json, manifest.json, and the SQLite database intact.
    """
    subdirs = ("decisions", "milestones", "holds", "delegates", "reviews", "anchors")
    for subdir in subdirs:
        target = trust_path / subdir
        if target.is_dir():
            shutil.rmtree(target)
            logger.info("Deleted filesystem records: %s", target)
