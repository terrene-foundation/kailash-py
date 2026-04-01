# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shadow enforcement storage protocols and implementations.

Provides persistent storage for ShadowEnforcer enforcement records and
metrics. Two implementations:

- MemoryShadowStore: in-memory with bounded deque (default)
- SqliteShadowStore: SQLite persistence with time-windowed metrics

Per trust-plane-security.md:
- SQLite files get 0o600 permissions (POSIX)
- All queries use parameterized SQL
- Collections are bounded (maxlen / LIMIT)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import stat
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from kailash.trust.enforce.strict import EnforcementRecord, Verdict

logger = logging.getLogger(__name__)

__all__ = [
    "MemoryShadowStore",
    "ShadowStore",
    "SqliteShadowStore",
]

# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ShadowStore(Protocol):
    """Protocol for shadow enforcement record persistence."""

    def append_record(self, record: EnforcementRecord) -> None:
        """Append an enforcement record to the store."""
        ...

    def get_records(
        self,
        *,
        limit: int = 1000,
        since: Optional[datetime] = None,
        agent_id: Optional[str] = None,
    ) -> List[EnforcementRecord]:
        """Retrieve records with optional filters.

        Args:
            limit: Maximum number of records to return.
            since: Only records after this timestamp.
            agent_id: Only records for this agent.

        Returns:
            List of EnforcementRecord, newest first.
        """
        ...

    def get_metrics(
        self,
        *,
        since: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get aggregated metrics.

        Args:
            since: Only count records after this timestamp.

        Returns:
            Dict with total_checks, auto_approved_count, flagged_count,
            held_count, blocked_count, and time window info.
        """
        ...

    def clear(self) -> None:
        """Remove all records from the store."""
        ...


# ---------------------------------------------------------------------------
# In-Memory Implementation
# ---------------------------------------------------------------------------


class MemoryShadowStore:
    """In-memory shadow store using bounded deque.

    Thread-safe via threading.Lock. Bounded to maxlen entries
    per trust-plane-security.md rule 4.
    """

    def __init__(self, maxlen: int = 10_000) -> None:
        self._lock = threading.Lock()
        self._records: deque[EnforcementRecord] = deque(maxlen=maxlen)

    def append_record(self, record: EnforcementRecord) -> None:
        """Append a record. Auto-evicts oldest when at capacity."""
        with self._lock:
            self._records.append(record)

    def get_records(
        self,
        *,
        limit: int = 1000,
        since: Optional[datetime] = None,
        agent_id: Optional[str] = None,
    ) -> List[EnforcementRecord]:
        """Retrieve records, newest first, with optional filters."""
        with self._lock:
            results: List[EnforcementRecord] = []
            for record in reversed(self._records):
                if since is not None and record.timestamp < since:
                    continue
                if agent_id is not None and record.agent_id != agent_id:
                    continue
                results.append(record)
                if len(results) >= limit:
                    break
            return results

    def get_metrics(
        self,
        *,
        since: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Aggregate metrics from in-memory records."""
        with self._lock:
            total = 0
            auto_approved = 0
            flagged = 0
            held = 0
            blocked = 0
            first_ts: Optional[datetime] = None
            last_ts: Optional[datetime] = None

            for record in self._records:
                if since is not None and record.timestamp < since:
                    continue
                total += 1
                if first_ts is None or record.timestamp < first_ts:
                    first_ts = record.timestamp
                if last_ts is None or record.timestamp > last_ts:
                    last_ts = record.timestamp

                if record.verdict == Verdict.AUTO_APPROVED:
                    auto_approved += 1
                elif record.verdict == Verdict.FLAGGED:
                    flagged += 1
                elif record.verdict == Verdict.HELD:
                    held += 1
                elif record.verdict == Verdict.BLOCKED:
                    blocked += 1

            return {
                "total_checks": total,
                "auto_approved_count": auto_approved,
                "flagged_count": flagged,
                "held_count": held,
                "blocked_count": blocked,
                "first_check": first_ts.isoformat() if first_ts else None,
                "last_check": last_ts.isoformat() if last_ts else None,
                "window_start": since.isoformat() if since else None,
            }

    def clear(self) -> None:
        """Clear all records."""
        with self._lock:
            self._records.clear()


# ---------------------------------------------------------------------------
# SQLite Implementation
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS shadow_records (
    id INTEGER PRIMARY KEY,
    agent_id TEXT NOT NULL,
    action TEXT NOT NULL,
    verdict TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    violations_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}'
)
"""


class SqliteShadowStore:
    """SQLite-backed shadow store with time-windowed metrics.

    Thread-safe via threading.Lock + SQLite WAL mode.
    File permissions set to 0o600 per trust-plane-security.md rule 6.
    All queries use parameterized SQL per trust-plane-security.md rule 5.
    """

    def __init__(
        self,
        db_path: str,
        max_records: int = 100_000,
    ) -> None:
        self._db_path = db_path
        self._max_records = max_records
        self._lock = threading.Lock()

        # Set file permissions on POSIX (trust-plane-security.md rule 6)
        if not db_path.startswith(":memory:"):
            if not os.path.exists(db_path):
                # Create with restrictive permissions
                open(db_path, "a").close()
            try:
                os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                logger.warning(
                    "Could not set permissions on %s (non-POSIX system?)", db_path
                )

        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute(_CREATE_TABLE_SQL)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_shadow_timestamp "
            "ON shadow_records(timestamp)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_shadow_agent " "ON shadow_records(agent_id)"
        )
        self._conn.commit()

    def append_record(self, record: EnforcementRecord) -> None:
        """Persist a record to SQLite."""
        violations_json = json.dumps(
            [
                {"field": v.get("field", ""), "message": v.get("message", "")}
                for v in (record.verification_result.violations or [])
            ]
            if record.verification_result and record.verification_result.violations
            else []
        )
        metadata_json = json.dumps(record.metadata or {})
        reason = record.verification_result.reason if record.verification_result else ""

        with self._lock:
            self._conn.execute(
                "INSERT INTO shadow_records "
                "(agent_id, action, verdict, timestamp, reason, violations_json, metadata_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record.agent_id,
                    record.action,
                    record.verdict.value,
                    record.timestamp.isoformat(),
                    reason,
                    violations_json,
                    metadata_json,
                ),
            )
            self._conn.commit()

            # Bounded: trim oldest records when exceeding max
            row = self._conn.execute("SELECT COUNT(*) FROM shadow_records").fetchone()
            if row and row[0] > self._max_records:
                excess = row[0] - self._max_records
                self._conn.execute(
                    "DELETE FROM shadow_records WHERE id IN "
                    "(SELECT id FROM shadow_records ORDER BY id ASC LIMIT ?)",
                    (excess,),
                )
                self._conn.commit()

    def get_records(
        self,
        *,
        limit: int = 1000,
        since: Optional[datetime] = None,
        agent_id: Optional[str] = None,
    ) -> List[EnforcementRecord]:
        """Retrieve records from SQLite, newest first."""
        from kailash.trust.chain import VerificationResult

        conditions: List[str] = []
        params: List[Any] = []

        if since is not None:
            conditions.append("timestamp >= ?")
            params.append(since.isoformat())
        if agent_id is not None:
            conditions.append("agent_id = ?")
            params.append(agent_id)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        query = (
            f"SELECT agent_id, action, verdict, timestamp, reason, "
            f"violations_json, metadata_json "
            f"FROM shadow_records {where_clause} "
            f"ORDER BY id DESC LIMIT ?"
        )
        params.append(limit)

        with self._lock:
            cursor = self._conn.execute(query, params)
            rows = cursor.fetchall()

        results: List[EnforcementRecord] = []
        for row in rows:
            agent_id_val, action, verdict_str, ts_str, reason, viol_json, meta_json = (
                row
            )
            violations = json.loads(viol_json) if viol_json else []
            metadata = json.loads(meta_json) if meta_json else {}
            ts = datetime.fromisoformat(ts_str)

            vr = VerificationResult(
                valid=verdict_str != "blocked",
                reason=reason,
                violations=violations,
            )
            results.append(
                EnforcementRecord(
                    agent_id=agent_id_val,
                    action=action,
                    verdict=Verdict(verdict_str),
                    verification_result=vr,
                    timestamp=ts,
                    metadata=metadata,
                )
            )
        return results

    def get_metrics(
        self,
        *,
        since: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Aggregate metrics from SQLite with optional time window."""
        conditions: List[str] = []
        params: List[Any] = []

        if since is not None:
            conditions.append("timestamp >= ?")
            params.append(since.isoformat())

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        query = (
            f"SELECT verdict, COUNT(*) FROM shadow_records "
            f"{where_clause} GROUP BY verdict"
        )

        ts_query = (
            f"SELECT MIN(timestamp), MAX(timestamp) FROM shadow_records "
            f"{where_clause}"
        )

        with self._lock:
            cursor = self._conn.execute(query, params)
            verdict_counts = dict(cursor.fetchall())

            ts_cursor = self._conn.execute(ts_query, params)
            ts_row = ts_cursor.fetchone()

        total = sum(verdict_counts.values())
        first_check = ts_row[0] if ts_row and ts_row[0] else None
        last_check = ts_row[1] if ts_row and ts_row[1] else None

        return {
            "total_checks": total,
            "auto_approved_count": verdict_counts.get("auto_approved", 0),
            "flagged_count": verdict_counts.get("flagged", 0),
            "held_count": verdict_counts.get("held", 0),
            "blocked_count": verdict_counts.get("blocked", 0),
            "first_check": first_check,
            "last_check": last_check,
            "window_start": since.isoformat() if since else None,
        }

    def clear(self) -> None:
        """Delete all records."""
        with self._lock:
            self._conn.execute("DELETE FROM shadow_records")
            self._conn.commit()

    def close(self) -> None:
        """Close the SQLite connection."""
        with self._lock:
            self._conn.close()
