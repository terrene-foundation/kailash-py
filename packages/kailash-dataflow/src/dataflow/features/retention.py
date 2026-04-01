# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""RetentionEngine -- data retention policies for DataFlow models.

Supports three policies declared via ``__dataflow__["retention"]``:

* **archive** -- move old records to an archive table (INSERT + DELETE
  in a single transaction).
* **delete** -- hard-delete records older than a cutoff.
* **partition** -- PostgreSQL range partitioning (raises on non-PG).

Access via ``db.retention`` after ``db.initialize()``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Literal, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "RetentionEngine",
    "RetentionPolicy",
    "RetentionResult",
]

# ---------------------------------------------------------------------------
# Table name validation (mirrors kailash.db.dialect._validate_identifier)
# ---------------------------------------------------------------------------

_TABLE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_table_name(name: str) -> None:
    """Raise ``ValueError`` if *name* is not a safe SQL identifier."""
    if not _TABLE_NAME_RE.match(name):
        raise ValueError(
            f"Invalid table name '{name}': must match [a-zA-Z_][a-zA-Z0-9_]*"
        )


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RetentionPolicy:
    """Configuration for a single model's retention policy."""

    model_name: str
    table_name: str
    policy: Literal["archive", "delete", "partition"]
    after_days: int
    archive_table: Optional[str] = None
    cutoff_field: str = "created_at"
    last_run: Optional[datetime] = None


@dataclass
class RetentionResult:
    """Outcome of executing a retention policy on one model."""

    model_name: str
    policy: str
    affected_rows: int
    archived_rows: int = 0
    deleted_rows: int = 0
    dry_run: bool = False
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DataFlowConfigError(Exception):
    """Raised when a retention configuration is invalid."""

    pass


# ---------------------------------------------------------------------------
# RetentionEngine
# ---------------------------------------------------------------------------


class RetentionEngine:
    """Manages data retention policies for DataFlow models.

    Policies are registered during ``@db.model`` decoration when
    ``__dataflow__["retention"]`` is present.  Manual execution via
    ``await db.retention.run()`` or ``db.retention.run_sync()``.
    """

    def __init__(self, dataflow_instance: Any) -> None:
        self._db = dataflow_instance
        self._policies: Dict[str, RetentionPolicy] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, policy: RetentionPolicy) -> None:
        """Register a retention policy for a model.

        Validates all table names before storing.
        """
        _validate_table_name(policy.table_name)
        _validate_table_name(
            policy.cutoff_field
        )  # Prevent SQL injection via field name
        if policy.archive_table:
            _validate_table_name(policy.archive_table)
        self._policies[policy.model_name] = policy
        logger.info(
            "Registered retention policy '%s' for model %s (after %d days)",
            policy.policy,
            policy.model_name,
            policy.after_days,
        )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def run(self, dry_run: bool = False) -> Dict[str, RetentionResult]:
        """Execute all registered retention policies.

        Args:
            dry_run: If ``True``, report affected row counts without mutating.

        Returns:
            ``{model_name: RetentionResult}`` for every registered policy.
        """
        results: Dict[str, RetentionResult] = {}
        for name, policy in self._policies.items():
            try:
                results[name] = await self._execute_policy(policy, dry_run)
            except Exception as exc:
                logger.error(
                    "Retention policy '%s' for %s failed: %s",
                    policy.policy,
                    name,
                    exc,
                )
                results[name] = RetentionResult(
                    model_name=name,
                    policy=policy.policy,
                    affected_rows=0,
                    error=str(exc),
                )
        return results

    def run_sync(self, dry_run: bool = False) -> Dict[str, RetentionResult]:
        """Synchronous wrapper for :meth:`run`."""
        from dataflow.core.async_utils import async_safe_run

        return async_safe_run(self.run(dry_run))

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Dict[str, Any]]:
        """Return policy configuration and last-run timestamp per model."""
        return {
            name: {
                "policy": p.policy,
                "after_days": p.after_days,
                "cutoff_field": p.cutoff_field,
                "archive_table": p.archive_table,
                "last_run": p.last_run.isoformat() if p.last_run else None,
            }
            for name, p in self._policies.items()
        }

    # ------------------------------------------------------------------
    # Internal: policy dispatch
    # ------------------------------------------------------------------

    async def _execute_policy(
        self, policy: RetentionPolicy, dry_run: bool
    ) -> RetentionResult:
        """Execute a single retention policy."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=policy.after_days)

        if dry_run:
            return await self._dry_run(policy, cutoff)

        if policy.policy == "archive":
            return await self._archive(policy, cutoff)
        elif policy.policy == "delete":
            return await self._delete(policy, cutoff)
        elif policy.policy == "partition":
            return await self._partition(policy, cutoff)
        else:
            raise DataFlowConfigError(
                f"Unknown retention policy '{policy.policy}'. "
                f"Supported: archive, delete, partition."
            )

    # ------------------------------------------------------------------
    # Archive
    # ------------------------------------------------------------------

    async def _archive(
        self, policy: RetentionPolicy, cutoff: datetime
    ) -> RetentionResult:
        """INSERT INTO archive + DELETE in one transaction."""
        archive_table = policy.archive_table or f"{policy.table_name}_archive"
        _validate_table_name(archive_table)

        conn = self._db._connection_manager

        async with conn.transaction() as tx:
            # Auto-create archive table with same schema
            await tx.execute(
                f"CREATE TABLE IF NOT EXISTS {archive_table} "
                f"AS SELECT * FROM {policy.table_name} WHERE 1=0"
            )

            # INSERT into archive
            await tx.execute(
                f"INSERT INTO {archive_table} "
                f"SELECT * FROM {policy.table_name} "
                f"WHERE {policy.cutoff_field} < ?",
                cutoff.isoformat(),
            )

            # DELETE from main table
            result = await tx.execute(
                f"DELETE FROM {policy.table_name} " f"WHERE {policy.cutoff_field} < ?",
                cutoff.isoformat(),
            )
            deleted = result.rowcount if hasattr(result, "rowcount") else 0

        policy.last_run = datetime.now(timezone.utc)
        return RetentionResult(
            model_name=policy.model_name,
            policy="archive",
            affected_rows=deleted,
            archived_rows=deleted,
            deleted_rows=deleted,
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def _delete(
        self, policy: RetentionPolicy, cutoff: datetime
    ) -> RetentionResult:
        """Hard-delete records older than cutoff."""
        conn = self._db._connection_manager

        async with conn.transaction() as tx:
            result = await tx.execute(
                f"DELETE FROM {policy.table_name} " f"WHERE {policy.cutoff_field} < ?",
                cutoff.isoformat(),
            )
            deleted = result.rowcount if hasattr(result, "rowcount") else 0

        policy.last_run = datetime.now(timezone.utc)
        return RetentionResult(
            model_name=policy.model_name,
            policy="delete",
            affected_rows=deleted,
            deleted_rows=deleted,
        )

    # ------------------------------------------------------------------
    # Partition (PostgreSQL only)
    # ------------------------------------------------------------------

    async def _partition(
        self, _policy: RetentionPolicy, _cutoff: datetime
    ) -> RetentionResult:
        """PostgreSQL range partitioning. Raises on non-PG adapters."""
        # Check adapter type
        db_url = getattr(self._db.config.database, "url", "") or ""
        if not db_url.startswith("postgresql"):
            raise DataFlowConfigError(
                f"Partition retention policy requires PostgreSQL. "
                f"Current database URL starts with "
                f"'{db_url.split('://')[0] if '://' in db_url else 'unknown'}'. "
                f"Use 'archive' or 'delete' policy for non-PostgreSQL databases."
            )

        # Partition implementation is PostgreSQL-specific and reserved for v2.
        # For now, raise a clear error if someone configures it.
        raise DataFlowConfigError(
            "Partition retention policy is not yet implemented. "
            "Use 'archive' or 'delete' policy instead."
        )

    # ------------------------------------------------------------------
    # Dry run
    # ------------------------------------------------------------------

    async def _dry_run(
        self, policy: RetentionPolicy, cutoff: datetime
    ) -> RetentionResult:
        """Count affected rows without executing mutations."""
        conn = self._db._connection_manager
        row = await conn.fetchone(
            f"SELECT COUNT(*) as cnt FROM {policy.table_name} "
            f"WHERE {policy.cutoff_field} < ?",
            cutoff.isoformat(),
        )
        count = row["cnt"] if row else 0
        return RetentionResult(
            model_name=policy.model_name,
            policy=policy.policy,
            affected_rows=count,
            dry_run=True,
        )
