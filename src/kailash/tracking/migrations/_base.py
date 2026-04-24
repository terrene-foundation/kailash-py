# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Abstract base class + result dataclass for numbered tracking migrations.

See ``specs/kailash-core-ml-integration.md §4``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, ClassVar, Optional

__all__ = [
    "MigrationBase",
    "MigrationResult",
    "STATUS_ENUM_1_0",
    "STATUS_ALIASES_LEGACY",
]


# Cross-SDK-locked status vocabulary (Decision 3).
STATUS_ENUM_1_0 = frozenset({"RUNNING", "FINISHED", "FAILED", "KILLED"})

# Legacy 0.x aliases that migration 0001 consolidates into FINISHED.
STATUS_ALIASES_LEGACY = frozenset({"COMPLETED", "SUCCESS"})


@dataclass(frozen=True)
class MigrationResult:
    """Frozen record returned by every :meth:`MigrationBase.apply`.

    Contains enough context for an operator to confirm the migration
    executed as intended (row counts, timing) without revealing any
    classified data content.
    """

    version: str
    name: str
    applied_at: datetime
    rows_migrated: int
    tenant_id: Optional[str]
    was_dry_run: bool
    direction: str  # "upgrade" or "downgrade"
    notes: str = ""

    @classmethod
    def now(cls, **kwargs: Any) -> "MigrationResult":
        kwargs.setdefault("applied_at", datetime.now(timezone.utc))
        return cls(**kwargs)


class MigrationBase(ABC):
    """Abstract base for every numbered tracking migration.

    Subclasses MUST set class variables ``version`` and ``name``; the
    registry uses these for discovery + idempotent re-application
    detection.

    Both :meth:`apply` and :meth:`rollback` are async so they can run
    inside an ``async with conn.transaction(): ...`` block without
    blocking the event loop on long-running UPDATE statements.
    """

    version: ClassVar[str]  # e.g. "1.0.0"
    name: ClassVar[str]  # e.g. "status_vocabulary_finished"

    @abstractmethod
    async def apply(
        self,
        conn: Any,
        *,
        tenant_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> MigrationResult:
        """Apply the migration. MUST be idempotent — re-running yields
        the same result once applied."""

    @abstractmethod
    async def rollback(
        self,
        conn: Any,
        *,
        tenant_id: Optional[str] = None,
        force_downgrade: bool = False,
    ) -> MigrationResult:
        """Roll the migration back. MUST require ``force_downgrade=True``
        when the down path is destructive or non-trivially irreversible
        per ``rules/schema-migration.md`` Rule 7."""

    @abstractmethod
    async def verify(self, conn: Any) -> bool:
        """Return ``True`` when the migration has been applied against
        ``conn``'s bound store."""
