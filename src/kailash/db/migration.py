# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Schema migration utilities for Kailash infrastructure tables.

Provides helpers for schema version management and future migration
support.  In v1.0.0, schema creation is handled inline by each store's
``initialize()`` method and version tracking is managed by
:class:`~kailash.infrastructure.factory.StoreFactory`.

This module centralises the schema version constant and provides
a ``check_schema_version()`` helper that can be used independently
of the StoreFactory (e.g. by CLI tooling or health-check endpoints).

Future versions will add incremental migration runners here.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "SCHEMA_VERSION",
    "check_schema_version",
    "stamp_schema_version",
]

# Current schema version for all infrastructure tables.
# Bump when adding new tables or altering existing schemas.
SCHEMA_VERSION = 1


async def check_schema_version(conn: Any) -> Optional[int]:
    """Read the current schema version from ``kailash_meta``.

    Parameters
    ----------
    conn:
        An initialized :class:`~kailash.db.connection.ConnectionManager`.

    Returns
    -------
    int or None
        The stored schema version, or ``None`` if the meta table does
        not exist or has no ``schema_version`` entry.
    """
    try:
        row = await conn.fetchone(
            "SELECT value FROM kailash_meta WHERE key = ?",
            "schema_version",
        )
        if row:
            return int(row["value"])
        return None
    except Exception:
        # Table may not exist yet
        return None


async def stamp_schema_version(conn: Any, version: int = SCHEMA_VERSION) -> None:
    """Create or update the schema version in ``kailash_meta``.

    Parameters
    ----------
    conn:
        An initialized :class:`~kailash.db.connection.ConnectionManager`.
    version:
        The version number to stamp (default: current ``SCHEMA_VERSION``).

    Raises
    ------
    RuntimeError
        If the existing schema version is newer than *version*
        (downgrade protection).
    """
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS kailash_meta (key TEXT PRIMARY KEY, value TEXT)"
    )

    existing = await check_schema_version(conn)
    if existing is not None and existing > version:
        raise RuntimeError(
            f"Database schema version {existing} is newer than code "
            f"version {version}. Upgrade kailash to a newer version."
        )

    if existing is None:
        await conn.execute(
            "INSERT INTO kailash_meta (key, value) VALUES (?, ?)",
            "schema_version",
            str(version),
        )
    elif existing < version:
        await conn.execute(
            "UPDATE kailash_meta SET value = ? WHERE key = ?",
            str(version),
            "schema_version",
        )
        logger.info("Schema version updated: %d -> %d", existing, version)
