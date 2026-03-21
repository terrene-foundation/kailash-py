# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""SQLite-backed governance store implementations.

Provides durable implementations of the four governance store protocols
(OrgStore, EnvelopeStore, ClearanceStore, AccessPolicyStore) plus an
append-only audit log with hash chain integrity.

Thread safety: Uses threading.Lock on every public method.
Security: All queries use parameterized ``?`` placeholders.
         All external IDs validated with ``_validate_id()``.
         Database file permissions set to 0o600 on POSIX.

Schema version tracking via pact_schema_version table.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import stat
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pact.build.config.schema import ConfidentialityLevel, ConstraintEnvelopeConfig
from pact.governance.access import KnowledgeSharePolicy, PactBridge
from pact.governance.clearance import RoleClearance, VettingStatus
from pact.governance.compilation import CompiledOrg, OrgNode
from pact.governance.envelopes import RoleEnvelope, TaskEnvelope
from pact.governance.store import MAX_STORE_SIZE

logger = logging.getLogger(__name__)

__all__ = [
    "PACT_SCHEMA_VERSION",
    "SqliteAccessPolicyStore",
    "SqliteAuditLog",
    "SqliteClearanceStore",
    "SqliteEnvelopeStore",
    "SqliteOrgStore",
    "_validate_id",
]

PACT_SCHEMA_VERSION: int = 1
"""Current governance schema version. Increment on DDL changes."""

_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_id(value: str) -> None:
    """Validate an external ID to prevent path traversal and injection.

    Args:
        value: The ID string to validate.

    Raises:
        ValueError: If the ID contains invalid characters.
    """
    if not value or not _ID_RE.match(value):
        raise ValueError(
            f"Invalid ID '{value!r}': must be non-empty and match [a-zA-Z0-9_-]+. "
            f"Path traversal, spaces, slashes, and special characters are rejected."
        )


# ---------------------------------------------------------------------------
# Shared SQLite connection helper
# ---------------------------------------------------------------------------


class _SqliteBase:
    """Base class for SQLite governance stores.

    Manages per-instance connections (thread-safe via shared-cache for
    :memory: databases, or WAL mode for file-backed databases).
    """

    _instance_counter_lock = threading.Lock()
    _instance_counter = 0

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = str(db_path)
        if self._db_path == ":memory:":
            with _SqliteBase._instance_counter_lock:
                _SqliteBase._instance_counter += 1
                self._memory_id = _SqliteBase._instance_counter
        else:
            self._memory_id = 0

        self._local = threading.local()
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._init_lock = threading.Lock()
        self._tables_created = False

        # Set file permissions on POSIX before opening
        if self._db_path != ":memory:":
            p = Path(self._db_path)
            if not p.exists():
                p.touch(mode=0o600)
            try:
                os.chmod(self._db_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                logger.debug("Could not set file permissions on %s", self._db_path)

        # Initialize on the calling thread
        self._ensure_tables(self._get_connection())

    def _get_connection(self) -> sqlite3.Connection:
        """Return a per-thread SQLite connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            if self._db_path == ":memory:":
                conn = sqlite3.connect(
                    f"file:pact_gov_memdb_{self._memory_id}?mode=memory&cache=shared",
                    uri=True,
                )
            else:
                conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA journal_size_limit=67108864")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
            self._ensure_tables(conn)
        return self._local.conn

    def _ensure_tables(self, conn: sqlite3.Connection) -> None:
        """Create tables exactly once (double-checked locking)."""
        if not self._tables_created:
            with self._init_lock:
                if not self._tables_created:
                    self._create_tables(conn)
                    self._tables_created = True

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        """Override in subclasses to create store-specific tables."""
        raise NotImplementedError

    def close(self) -> None:
        """Close the current thread's database connection."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None


# ---------------------------------------------------------------------------
# SqliteOrgStore
# ---------------------------------------------------------------------------


class SqliteOrgStore(_SqliteBase):
    """SQLite-backed OrgStore.

    Stores compiled organizations as JSON blobs. Nodes are reconstructed
    from the JSON on load. All public methods are thread-safe.
    """

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pact_orgs (
                    org_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    compiled_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pact_schema_version (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    version INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO pact_schema_version (id, version) VALUES (1, ?)",
                (PACT_SCHEMA_VERSION,),
            )

    def save_org(self, org: CompiledOrg) -> None:
        """Save a compiled organization as a JSON blob."""
        _validate_id(org.org_id)
        now = datetime.now(UTC).isoformat()

        # Serialize org to JSON
        nodes_dict: dict[str, Any] = {}
        for addr, node in org.nodes.items():
            nodes_dict[addr] = {
                "address": node.address,
                "node_type": node.node_type.value,
                "name": node.name,
                "node_id": node.node_id,
                "parent_address": node.parent_address,
                "children_addresses": list(node.children_addresses),
                "is_vacant": node.is_vacant,
                "is_external": node.is_external,
            }

        compiled_json = json.dumps(
            {"org_id": org.org_id, "nodes": nodes_dict},
            default=str,
        )

        conn = self._get_connection()
        with self._write_lock, conn:
            conn.execute(
                """INSERT OR REPLACE INTO pact_orgs
                   (org_id, name, compiled_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (org.org_id, "", compiled_json, now, now),
            )
        logger.info("Saved org '%s' (%d nodes)", org.org_id, len(org.nodes))

    def load_org(self, org_id: str) -> CompiledOrg | None:
        """Load a compiled organization by ID."""
        _validate_id(org_id)
        conn = self._get_connection()
        with self._lock:
            row = conn.execute(
                "SELECT compiled_json FROM pact_orgs WHERE org_id = ?",
                (org_id,),
            ).fetchone()
        if row is None:
            return None

        data = json.loads(row[0])
        return self._deserialize_org(data)

    def get_node(self, org_id: str, address: str) -> OrgNode | None:
        """Look up a single node by org_id and address."""
        org = self.load_org(org_id)
        if org is None:
            return None
        return org.nodes.get(address)

    def query_by_prefix(self, org_id: str, prefix: str) -> list[OrgNode]:
        """Return all nodes whose address starts with the given prefix."""
        org = self.load_org(org_id)
        if org is None:
            return []
        results = []
        for addr, node in org.nodes.items():
            if addr == prefix or addr.startswith(prefix + "-"):
                results.append(node)
        return results

    @staticmethod
    def _deserialize_org(data: dict[str, Any]) -> CompiledOrg:
        """Reconstruct a CompiledOrg from serialized JSON data."""
        from pact.governance.addressing import NodeType

        org = CompiledOrg(org_id=data["org_id"])
        for addr, node_data in data.get("nodes", {}).items():
            node = OrgNode(
                address=node_data["address"],
                node_type=NodeType(node_data["node_type"]),
                name=node_data["name"],
                node_id=node_data["node_id"],
                parent_address=node_data.get("parent_address"),
                children_addresses=tuple(node_data.get("children_addresses", [])),
                is_vacant=node_data.get("is_vacant", False),
                is_external=node_data.get("is_external", False),
            )
            org.nodes[addr] = node
        return org


# ---------------------------------------------------------------------------
# SqliteEnvelopeStore
# ---------------------------------------------------------------------------


class SqliteEnvelopeStore(_SqliteBase):
    """SQLite-backed EnvelopeStore.

    Role envelopes are keyed by target_role_address (UNIQUE constraint).
    Task envelopes are keyed by task_id. All public methods are thread-safe.
    """

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pact_role_envelopes (
                    id TEXT PRIMARY KEY,
                    target_role_address TEXT NOT NULL UNIQUE,
                    defining_role_address TEXT NOT NULL,
                    envelope_json TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    modified_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_role_env_target
                ON pact_role_envelopes(target_role_address)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pact_task_envelopes (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    parent_envelope_id TEXT NOT NULL,
                    envelope_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def save_role_envelope(self, envelope: RoleEnvelope) -> None:
        """Save a role envelope. Increments version if target already exists."""
        _validate_id(envelope.id)
        now = datetime.now(UTC).isoformat()

        envelope_json = json.dumps(envelope.envelope.model_dump(), default=str)

        conn = self._get_connection()
        with self._write_lock:
            # Check existing version
            row = conn.execute(
                "SELECT version FROM pact_role_envelopes WHERE target_role_address = ?",
                (envelope.target_role_address,),
            ).fetchone()
            new_version = (row[0] + 1) if row is not None else 1

            with conn:
                # Delete existing entry for this target (if any) then insert
                conn.execute(
                    "DELETE FROM pact_role_envelopes WHERE target_role_address = ?",
                    (envelope.target_role_address,),
                )
                conn.execute(
                    """INSERT INTO pact_role_envelopes
                       (id, target_role_address, defining_role_address,
                        envelope_json, version, created_at, modified_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        envelope.id,
                        envelope.target_role_address,
                        envelope.defining_role_address,
                        envelope_json,
                        new_version,
                        envelope.created_at.isoformat(),
                        now,
                    ),
                )

        logger.info(
            "Saved role envelope '%s' for target '%s' (v%d)",
            envelope.id,
            envelope.target_role_address,
            new_version,
        )

    def get_role_envelope(self, target_role_address: str) -> RoleEnvelope | None:
        """Get a role envelope by target role address."""
        conn = self._get_connection()
        with self._lock:
            row = conn.execute(
                """SELECT id, target_role_address, defining_role_address,
                          envelope_json, version, created_at, modified_at
                   FROM pact_role_envelopes
                   WHERE target_role_address = ?""",
                (target_role_address,),
            ).fetchone()
        if row is None:
            return None

        envelope_config = ConstraintEnvelopeConfig.model_validate(json.loads(row["envelope_json"]))
        return RoleEnvelope(
            id=row["id"],
            defining_role_address=row["defining_role_address"],
            target_role_address=row["target_role_address"],
            envelope=envelope_config,
            version=row["version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            modified_at=datetime.fromisoformat(row["modified_at"]),
        )

    def save_task_envelope(self, envelope: TaskEnvelope) -> None:
        """Save a task envelope."""
        _validate_id(envelope.id)
        _validate_id(envelope.task_id)

        envelope_json = json.dumps(envelope.envelope.model_dump(), default=str)

        conn = self._get_connection()
        with self._write_lock, conn:
            conn.execute(
                """INSERT OR REPLACE INTO pact_task_envelopes
                   (id, task_id, parent_envelope_id, envelope_json,
                    expires_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    envelope.id,
                    envelope.task_id,
                    envelope.parent_envelope_id,
                    envelope_json,
                    envelope.expires_at.isoformat(),
                    envelope.created_at.isoformat(),
                ),
            )

        logger.info(
            "Saved task envelope '%s' for task '%s'",
            envelope.id,
            envelope.task_id,
        )

    def get_active_task_envelope(self, role_address: str, task_id: str) -> TaskEnvelope | None:
        """Get an active (non-expired) task envelope by task_id."""
        _validate_id(task_id)
        conn = self._get_connection()
        with self._lock:
            row = conn.execute(
                """SELECT id, task_id, parent_envelope_id, envelope_json,
                          expires_at, created_at
                   FROM pact_task_envelopes
                   WHERE task_id = ?""",
                (task_id,),
            ).fetchone()
        if row is None:
            return None

        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at < datetime.now(UTC):
            logger.debug("Task envelope '%s' is expired", row["id"])
            return None

        envelope_config = ConstraintEnvelopeConfig.model_validate(json.loads(row["envelope_json"]))
        return TaskEnvelope(
            id=row["id"],
            task_id=row["task_id"],
            parent_envelope_id=row["parent_envelope_id"],
            envelope=envelope_config,
            expires_at=expires_at,
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def get_ancestor_envelopes(self, role_address: str) -> dict[str, RoleEnvelope]:
        """Return all RoleEnvelopes for addresses that are ancestors of role_address."""
        conn = self._get_connection()
        with self._lock:
            rows = conn.execute(
                """SELECT id, target_role_address, defining_role_address,
                          envelope_json, version, created_at, modified_at
                   FROM pact_role_envelopes""",
            ).fetchall()

        result: dict[str, RoleEnvelope] = {}
        for row in rows:
            addr = row["target_role_address"]
            # addr is ancestor if role_address starts with addr
            if role_address == addr or role_address.startswith(addr + "-"):
                envelope_config = ConstraintEnvelopeConfig.model_validate(
                    json.loads(row["envelope_json"])
                )
                result[addr] = RoleEnvelope(
                    id=row["id"],
                    defining_role_address=row["defining_role_address"],
                    target_role_address=addr,
                    envelope=envelope_config,
                    version=row["version"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    modified_at=datetime.fromisoformat(row["modified_at"]),
                )
        return result


# ---------------------------------------------------------------------------
# SqliteClearanceStore
# ---------------------------------------------------------------------------


class SqliteClearanceStore(_SqliteBase):
    """SQLite-backed ClearanceStore.

    Clearances are keyed by role_address. All public methods are thread-safe.
    """

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pact_clearances (
                    role_address TEXT PRIMARY KEY,
                    max_clearance TEXT NOT NULL,
                    compartments_json TEXT NOT NULL DEFAULT '[]',
                    granted_by TEXT NOT NULL,
                    vetting_status TEXT NOT NULL DEFAULT 'active',
                    review_at TEXT,
                    nda_signed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )

    def grant_clearance(self, clearance: RoleClearance) -> None:
        """Grant or update a clearance for a role address."""
        now = datetime.now(UTC).isoformat()

        compartments_json = json.dumps(sorted(clearance.compartments))
        review_at = clearance.review_at.isoformat() if clearance.review_at else None

        conn = self._get_connection()
        with self._write_lock, conn:
            conn.execute(
                """INSERT OR REPLACE INTO pact_clearances
                   (role_address, max_clearance, compartments_json, granted_by,
                    vetting_status, review_at, nda_signed, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    clearance.role_address,
                    clearance.max_clearance.value,
                    compartments_json,
                    clearance.granted_by_role_address,
                    clearance.vetting_status.value,
                    review_at,
                    1 if clearance.nda_signed else 0,
                    now,
                ),
            )

        logger.info(
            "Granted clearance '%s' to role '%s'",
            clearance.max_clearance.value,
            clearance.role_address,
        )

    def get_clearance(self, role_address: str) -> RoleClearance | None:
        """Get the clearance for a role address."""
        conn = self._get_connection()
        with self._lock:
            row = conn.execute(
                """SELECT role_address, max_clearance, compartments_json,
                          granted_by, vetting_status, review_at, nda_signed
                   FROM pact_clearances
                   WHERE role_address = ?""",
                (role_address,),
            ).fetchone()
        if row is None:
            return None

        compartments = frozenset(json.loads(row["compartments_json"]))
        review_at = datetime.fromisoformat(row["review_at"]) if row["review_at"] else None

        return RoleClearance(
            role_address=row["role_address"],
            max_clearance=ConfidentialityLevel(row["max_clearance"]),
            compartments=compartments,
            granted_by_role_address=row["granted_by"],
            vetting_status=VettingStatus(row["vetting_status"]),
            review_at=review_at,
            nda_signed=bool(row["nda_signed"]),
        )

    def revoke_clearance(self, role_address: str) -> None:
        """Revoke clearance for a role address. No-op if not found."""
        conn = self._get_connection()
        with self._write_lock, conn:
            conn.execute(
                "DELETE FROM pact_clearances WHERE role_address = ?",
                (role_address,),
            )
        logger.info("Revoked clearance for role '%s'", role_address)


# ---------------------------------------------------------------------------
# SqliteAccessPolicyStore
# ---------------------------------------------------------------------------


class SqliteAccessPolicyStore(_SqliteBase):
    """SQLite-backed AccessPolicyStore.

    KSPs keyed by id. Bridges keyed by id. All public methods are thread-safe.
    """

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pact_ksps (
                    id TEXT PRIMARY KEY,
                    source_unit_address TEXT NOT NULL,
                    target_unit_address TEXT NOT NULL,
                    max_classification TEXT NOT NULL,
                    compartments_json TEXT NOT NULL DEFAULT '[]',
                    conditions_json TEXT NOT NULL DEFAULT '{}',
                    created_by TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    expires_at TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pact_bridges (
                    id TEXT PRIMARY KEY,
                    role_a_address TEXT NOT NULL,
                    role_b_address TEXT NOT NULL,
                    bridge_type TEXT NOT NULL DEFAULT 'standing',
                    max_classification TEXT NOT NULL DEFAULT 'restricted',
                    operational_scope_json TEXT NOT NULL DEFAULT '[]',
                    financial_authority INTEGER NOT NULL DEFAULT 0,
                    bilateral INTEGER NOT NULL DEFAULT 1,
                    standing INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'active',
                    expires_at TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

    # ---- KSP operations ----

    def save_ksp(self, ksp: KnowledgeSharePolicy) -> None:
        """Save a Knowledge Share Policy."""
        _validate_id(ksp.id)
        now = datetime.now(UTC).isoformat()

        compartments_json = json.dumps(sorted(ksp.compartments))
        expires_at = ksp.expires_at.isoformat() if ksp.expires_at else None

        conn = self._get_connection()
        with self._write_lock, conn:
            conn.execute(
                """INSERT OR REPLACE INTO pact_ksps
                   (id, source_unit_address, target_unit_address,
                    max_classification, compartments_json, created_by,
                    active, expires_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ksp.id,
                    ksp.source_unit_address,
                    ksp.target_unit_address,
                    ksp.max_classification.value,
                    compartments_json,
                    ksp.created_by_role_address,
                    1 if ksp.active else 0,
                    expires_at,
                    now,
                ),
            )

        logger.info(
            "Saved KSP '%s': %s -> %s",
            ksp.id,
            ksp.source_unit_address,
            ksp.target_unit_address,
        )

    def find_ksp(self, source_prefix: str, target_prefix: str) -> KnowledgeSharePolicy | None:
        """Find a KSP matching source and target prefixes (directional)."""
        conn = self._get_connection()
        with self._lock:
            row = conn.execute(
                """SELECT id, source_unit_address, target_unit_address,
                          max_classification, compartments_json, created_by,
                          active, expires_at
                   FROM pact_ksps
                   WHERE source_unit_address = ? AND target_unit_address = ?
                   LIMIT 1""",
                (source_prefix, target_prefix),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_ksp(row)

    def list_ksps(self) -> list[KnowledgeSharePolicy]:
        """Return all stored KSPs."""
        conn = self._get_connection()
        with self._lock:
            rows = conn.execute(
                """SELECT id, source_unit_address, target_unit_address,
                          max_classification, compartments_json, created_by,
                          active, expires_at
                   FROM pact_ksps""",
            ).fetchall()
        return [self._row_to_ksp(row) for row in rows]

    @staticmethod
    def _row_to_ksp(row: sqlite3.Row) -> KnowledgeSharePolicy:
        compartments = frozenset(json.loads(row["compartments_json"]))
        expires_at = datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None
        return KnowledgeSharePolicy(
            id=row["id"],
            source_unit_address=row["source_unit_address"],
            target_unit_address=row["target_unit_address"],
            max_classification=ConfidentialityLevel(row["max_classification"]),
            compartments=compartments,
            created_by_role_address=row["created_by"],
            active=bool(row["active"]),
            expires_at=expires_at,
        )

    # ---- Bridge operations ----

    def save_bridge(self, bridge: PactBridge) -> None:
        """Save a Cross-Functional Bridge."""
        _validate_id(bridge.id)
        now = datetime.now(UTC).isoformat()

        scope_json = json.dumps(list(bridge.operational_scope))
        expires_at = bridge.expires_at.isoformat() if bridge.expires_at else None

        conn = self._get_connection()
        with self._write_lock, conn:
            conn.execute(
                """INSERT OR REPLACE INTO pact_bridges
                   (id, role_a_address, role_b_address, bridge_type,
                    max_classification, operational_scope_json, bilateral,
                    standing, status, expires_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    bridge.id,
                    bridge.role_a_address,
                    bridge.role_b_address,
                    bridge.bridge_type,
                    bridge.max_classification.value,
                    scope_json,
                    1 if bridge.bilateral else 0,
                    1 if bridge.bridge_type == "standing" else 0,
                    "active" if bridge.active else "inactive",
                    expires_at,
                    now,
                ),
            )

        logger.info(
            "Saved bridge '%s': %s <-> %s (%s)",
            bridge.id,
            bridge.role_a_address,
            bridge.role_b_address,
            bridge.bridge_type,
        )

    def find_bridge(self, role_a_address: str, role_b_address: str) -> PactBridge | None:
        """Find a bridge connecting two role addresses (symmetric lookup)."""
        conn = self._get_connection()
        with self._lock:
            row = conn.execute(
                """SELECT id, role_a_address, role_b_address, bridge_type,
                          max_classification, operational_scope_json, bilateral,
                          status, expires_at
                   FROM pact_bridges
                   WHERE (role_a_address = ? AND role_b_address = ?)
                      OR (role_a_address = ? AND role_b_address = ?)
                   LIMIT 1""",
                (role_a_address, role_b_address, role_b_address, role_a_address),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_bridge(row)

    def list_bridges(self) -> list[PactBridge]:
        """Return all stored bridges."""
        conn = self._get_connection()
        with self._lock:
            rows = conn.execute(
                """SELECT id, role_a_address, role_b_address, bridge_type,
                          max_classification, operational_scope_json, bilateral,
                          status, expires_at
                   FROM pact_bridges""",
            ).fetchall()
        return [self._row_to_bridge(row) for row in rows]

    @staticmethod
    def _row_to_bridge(row: sqlite3.Row) -> PactBridge:
        scope = tuple(json.loads(row["operational_scope_json"]))
        expires_at = datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None
        return PactBridge(
            id=row["id"],
            role_a_address=row["role_a_address"],
            role_b_address=row["role_b_address"],
            bridge_type=row["bridge_type"],
            max_classification=ConfidentialityLevel(row["max_classification"]),
            operational_scope=scope,
            bilateral=bool(row["bilateral"]),
            expires_at=expires_at,
            active=row["status"] == "active",
        )


# ---------------------------------------------------------------------------
# SqliteAuditLog -- append-only with hash chain
# ---------------------------------------------------------------------------


class SqliteAuditLog(_SqliteBase):
    """Append-only audit log with cryptographic hash chain.

    Each entry:
    - content_hash = SHA-256 of details_json (sorted keys for determinism)
    - chain_hash = SHA-256 of (previous_chain_hash + content_hash)

    No UPDATE or DELETE allowed through public API. Triggers enforce
    immutability at the database level.
    """

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pact_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    chain_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def append(self, action: str, details: dict[str, Any]) -> None:
        """Append an audit entry with hash chain linking.

        Args:
            action: The audit action name.
            details: Structured details dict (will be JSON-serialized).
        """
        now = datetime.now(UTC).isoformat()
        details_json = json.dumps(details, sort_keys=True)
        content_hash = hashlib.sha256(details_json.encode()).hexdigest()

        conn = self._get_connection()
        with self._write_lock:
            # Get the chain_hash of the last entry
            row = conn.execute(
                "SELECT chain_hash FROM pact_audit_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            prev_chain = row["chain_hash"] if row is not None else ""

            chain_hash = hashlib.sha256((prev_chain + content_hash).encode()).hexdigest()

            with conn:
                conn.execute(
                    """INSERT INTO pact_audit_log
                       (action, details_json, content_hash, chain_hash, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (action, details_json, content_hash, chain_hash, now),
                )

        logger.debug("Audit log: appended '%s' (chain=%s...)", action, chain_hash[:12])

    def get_all_entries(self) -> list[dict[str, Any]]:
        """Return all audit entries in order."""
        conn = self._get_connection()
        with self._lock:
            rows = conn.execute(
                """SELECT id, action, details_json, content_hash, chain_hash, created_at
                   FROM pact_audit_log ORDER BY id"""
            ).fetchall()

        entries = []
        for row in rows:
            entries.append(
                {
                    "id": row["id"],
                    "action": row["action"],
                    "details": json.loads(row["details_json"]),
                    "content_hash": row["content_hash"],
                    "chain_hash": row["chain_hash"],
                    "created_at": row["created_at"],
                }
            )
        return entries

    def verify_integrity(self) -> tuple[bool, str | None]:
        """Walk the hash chain and verify all entries.

        Returns:
            A tuple (is_valid, error_message). is_valid is True if the chain
            is intact. error_message describes the first violation found, or
            None if the chain is valid.
        """
        conn = self._get_connection()
        with self._lock:
            rows = conn.execute(
                """SELECT id, action, details_json, content_hash, chain_hash
                   FROM pact_audit_log ORDER BY id"""
            ).fetchall()

        if not rows:
            return (True, None)

        prev_chain = ""
        for row in rows:
            entry_id = row["id"]
            details_json = row["details_json"]
            stored_content_hash = row["content_hash"]
            stored_chain_hash = row["chain_hash"]

            # Verify content_hash
            expected_content_hash = hashlib.sha256(details_json.encode()).hexdigest()
            if stored_content_hash != expected_content_hash:
                return (
                    False,
                    f"Tamper detected at entry {entry_id}: content_hash mismatch. "
                    f"Expected {expected_content_hash}, found {stored_content_hash}",
                )

            # Verify chain_hash
            expected_chain_hash = hashlib.sha256(
                (prev_chain + expected_content_hash).encode()
            ).hexdigest()
            if stored_chain_hash != expected_chain_hash:
                return (
                    False,
                    f"Tamper detected at entry {entry_id}: chain_hash mismatch. "
                    f"Expected {expected_chain_hash}, found {stored_chain_hash}",
                )

            prev_chain = stored_chain_hash

        return (True, None)
