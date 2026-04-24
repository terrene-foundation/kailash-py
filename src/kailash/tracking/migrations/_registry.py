# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Numbered-migration discovery + ordered-apply registry.

Discovers migrations by scanning this package for modules matching
``NNNN_<name>.py`` (where ``NNNN`` is a 4-digit zero-padded ordinal),
imports each, and uses its ``Migration`` class.

The registry is used by the ``km doctor migrate`` CLI (W33b) and by
the ExperimentTracker's first-open bootstrap in W10. Both call
:meth:`MigrationRegistry.apply_pending` which walks the ordered list
and applies every migration whose ``verify()`` returns ``False``.
"""
from __future__ import annotations

import importlib
import logging
import re
from pathlib import Path
from typing import Any, Optional

from kailash.tracking.migrations._base import MigrationBase, MigrationResult

__all__ = [
    "MigrationRegistry",
    "get_registry",
]

logger = logging.getLogger(__name__)

_FILENAME_PATTERN = re.compile(r"^(\d{4})_([a-z0-9_]+)\.py$")


class MigrationRegistry:
    """Ordered registry of numbered migrations in this package.

    The ordinal extracted from the filename (``NNNN_<name>.py``) is the
    canonical ordering key. The registry discovers migrations lazily on
    first :meth:`get_ordered` call and caches the result.
    """

    def __init__(self, package_dir: Optional[Path] = None) -> None:
        self._package_dir = package_dir or Path(__file__).parent
        self._ordered: Optional[list[MigrationBase]] = None

    def _discover(self) -> list[MigrationBase]:
        migrations: list[tuple[int, MigrationBase]] = []
        for entry in sorted(self._package_dir.iterdir()):
            match = _FILENAME_PATTERN.match(entry.name)
            if not match:
                continue
            ordinal = int(match.group(1))
            module_name = f"kailash.tracking.migrations.{entry.stem}"
            module = importlib.import_module(module_name)
            cls = getattr(module, "Migration", None)
            if cls is None:
                logger.warning(
                    "kailash.tracking.migrations.missing_migration_class",
                    extra={"module": module_name, "file": entry.name},
                )
                continue
            if not issubclass(cls, MigrationBase):
                raise TypeError(
                    f"{module_name}.Migration must subclass MigrationBase; "
                    f"got {cls!r}"
                )
            migrations.append((ordinal, cls()))
        migrations.sort(key=lambda pair: pair[0])
        return [m for _, m in migrations]

    def get_ordered(self) -> list[MigrationBase]:
        if self._ordered is None:
            self._ordered = self._discover()
        return self._ordered

    async def apply_pending(
        self,
        conn: Any,
        *,
        tenant_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> list[MigrationResult]:
        """Apply every migration whose :meth:`verify` returns ``False``.

        Walks migrations in ordinal order. Stops and re-raises on the
        first failure so the caller can recover from a mid-sequence
        abort without further half-applied state.
        """
        results: list[MigrationResult] = []
        for migration in self.get_ordered():
            already = await migration.verify(conn)
            if already:
                continue
            result = await migration.apply(conn, tenant_id=tenant_id, dry_run=dry_run)
            results.append(result)
        return results


_registry: Optional[MigrationRegistry] = None


def get_registry() -> MigrationRegistry:
    global _registry
    if _registry is None:
        _registry = MigrationRegistry()
    return _registry
