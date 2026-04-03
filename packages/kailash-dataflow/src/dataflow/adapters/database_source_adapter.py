# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Database Source Adapter — external/read-only database sources.

Reuses existing DataFlow adapter infrastructure for database connections.
Supports three change detection strategies in order of preference:
1. Change counter table (`_fabric_changes`) if available
2. `MAX(updated_at)` if table has an `updated_at` column
3. `COUNT(*)` as fallback

Table names are validated per infrastructure-sql.md to prevent injection.
"""

from __future__ import annotations

import collections
import logging
import re
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from dataflow.adapters.source_adapter import BaseSourceAdapter
from dataflow.fabric.config import DatabaseSourceConfig

logger = logging.getLogger(__name__)

__all__ = ["DatabaseSourceAdapter"]

_TABLE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_table_name(name: str) -> str:
    """Validate SQL identifier to prevent injection (infrastructure-sql.md Rule 1)."""
    if not _TABLE_NAME_RE.match(name):
        raise ValueError(
            f"Invalid table name '{name}': must match [a-zA-Z_][a-zA-Z0-9_]*"
        )
    return name


class DatabaseSourceAdapter(BaseSourceAdapter):
    """Source adapter for external databases.

    Uses existing DataFlow connection infrastructure — NOT a reimplementation.
    Supports read-only mode for external databases that should not be modified.
    """

    def __init__(self, name: str, config: DatabaseSourceConfig) -> None:
        super().__init__(name, circuit_breaker=config.circuit_breaker)
        self.config = config
        self._conn: Any = None
        self._last_state: collections.OrderedDict[str, Any] = (
            collections.OrderedDict()
        )  # table -> last known state for change detection (bounded)
        self._change_detection_strategy: Dict[str, str] = {}  # table -> strategy
        self._MAX_TRACKED_TABLES = 1000

    @property
    def database_type(self) -> str:
        return "database"

    async def _connect(self) -> None:
        try:
            import aiosqlite
        except ImportError:
            aiosqlite = None  # type: ignore[assignment]

        url = self.config.url

        if url.startswith("sqlite"):
            if aiosqlite is None:
                raise ImportError(
                    "aiosqlite is required for SQLite database sources. "
                    "Install with: pip install kailash"
                )
            db_path = url.replace("sqlite:///", "").replace("sqlite://", "")
            if not db_path or db_path == ":memory:":
                db_path = ":memory:"
            self._conn = await aiosqlite.connect(db_path)
            self._conn.row_factory = aiosqlite.Row
        else:
            # PostgreSQL or MySQL — use asyncpg/aiomysql
            if "postgresql" in url or "postgres" in url:
                try:
                    import asyncpg
                except ImportError as exc:
                    raise ImportError(
                        "asyncpg is required for PostgreSQL database sources. "
                        "Install with: pip install kailash"
                    ) from exc
                self._conn = await asyncpg.connect(url)
            else:
                scheme = url.split("://")[0] if "://" in url else "unknown"
                raise ValueError(
                    f"Unsupported database URL scheme for source adapter: {scheme}"
                )

        logger.debug("Database source adapter '%s' connected", self.name)

    async def _disconnect(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def detect_change(self) -> bool:
        if self._conn is None:
            raise ConnectionError(f"Database adapter '{self.name}' not connected")

        tables = self.config.tables
        if not tables:
            return False

        changed = False
        for table in tables:
            table = _validate_table_name(table)
            strategy = await self._get_detection_strategy(table)
            current_state = await self._get_table_state(table, strategy)

            if self._last_state.get(table) != current_state:
                if table in self._last_state:
                    self._last_state.move_to_end(table)
                self._last_state[table] = current_state
                while len(self._last_state) > self._MAX_TRACKED_TABLES:
                    self._last_state.popitem(last=False)
                changed = True

        return changed

    async def _get_detection_strategy(self, table: str) -> str:
        """Determine the best change detection strategy for a table."""
        if table in self._change_detection_strategy:
            return self._change_detection_strategy[table]

        # Strategy 1: Check for _fabric_changes counter table
        strategy = await self._try_change_counter(table)
        if strategy:
            self._change_detection_strategy[table] = "change_counter"
            return "change_counter"

        # Strategy 2: Check for updated_at column
        strategy = await self._try_updated_at(table)
        if strategy:
            self._change_detection_strategy[table] = "updated_at"
            return "updated_at"

        # Strategy 3: Fallback to COUNT(*)
        self._change_detection_strategy[table] = "count"
        return "count"

    async def _try_change_counter(self, table: str) -> bool:
        """Check if _fabric_changes table exists and has an entry for this table."""
        try:
            if hasattr(self._conn, "fetchval"):
                # asyncpg
                result = await self._conn.fetchval(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = '_fabric_changes' LIMIT 1"
                )
                return result is not None
            else:
                # aiosqlite
                cursor = await self._conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='_fabric_changes'"
                )
                row = await cursor.fetchone()
                return row is not None
        except Exception:
            return False

    async def _try_updated_at(self, table: str) -> bool:
        """Check if table has an updated_at column."""
        _validate_table_name(table)  # Defense-in-depth
        try:
            if hasattr(self._conn, "fetchval"):
                result = await self._conn.fetchval(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = $1 AND column_name = 'updated_at' LIMIT 1",
                    table,
                )
                return result is not None
            else:
                cursor = await self._conn.execute(f"PRAGMA table_info({table})")
                columns = await cursor.fetchall()
                return any(col[1] == "updated_at" for col in columns)
        except Exception:
            return False

    async def _get_table_state(self, table: str, strategy: str) -> Any:
        """Get current table state using the chosen strategy."""
        if strategy == "change_counter":
            if hasattr(self._conn, "fetchval"):
                return await self._conn.fetchval(
                    "SELECT change_count FROM _fabric_changes WHERE table_name = $1",
                    table,
                )
            else:
                cursor = await self._conn.execute(
                    "SELECT change_count FROM _fabric_changes WHERE table_name = ?",
                    (table,),
                )
                row = await cursor.fetchone()
                return row[0] if row else None

        elif strategy == "updated_at":
            if hasattr(self._conn, "fetchval"):
                return await self._conn.fetchval(f"SELECT MAX(updated_at) FROM {table}")
            else:
                cursor = await self._conn.execute(
                    f"SELECT MAX(updated_at) FROM {table}"
                )
                row = await cursor.fetchone()
                return row[0] if row else None

        else:  # count
            if hasattr(self._conn, "fetchval"):
                return await self._conn.fetchval(f"SELECT COUNT(*) FROM {table}")
            else:
                cursor = await self._conn.execute(f"SELECT COUNT(*) FROM {table}")
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def fetch(
        self, path: str = "", params: Optional[Dict[str, Any]] = None
    ) -> Any:
        if self._conn is None:
            raise ConnectionError(f"Database adapter '{self.name}' not connected")

        table = _validate_table_name(path) if path else None
        if not table:
            if self.config.tables:
                table = _validate_table_name(self.config.tables[0])
            else:
                raise ValueError(
                    f"Database source '{self.name}': no table specified in path or config"
                )

        if hasattr(self._conn, "fetch"):
            # asyncpg
            rows = await self._conn.fetch(f"SELECT * FROM {table}")
            data = [dict(row) for row in rows]
        else:
            # aiosqlite
            cursor = await self._conn.execute(f"SELECT * FROM {table}")
            columns = (
                [desc[0] for desc in cursor.description] if cursor.description else []
            )
            raw_rows = await cursor.fetchall()
            data = [dict(zip(columns, row)) for row in raw_rows]

        self._record_successful_data(path, data)
        return data

    async def fetch_pages(
        self, path: str = "", page_size: int = 100
    ) -> AsyncIterator[List[Any]]:
        if self._conn is None:
            raise ConnectionError(f"Database adapter '{self.name}' not connected")

        table = _validate_table_name(path) if path else None
        if not table and self.config.tables:
            table = _validate_table_name(self.config.tables[0])
        if not table:
            raise ValueError(f"Database source '{self.name}': no table specified")

        offset = 0
        while True:
            if hasattr(self._conn, "fetch"):
                rows = await self._conn.fetch(
                    f"SELECT * FROM {table} LIMIT $1 OFFSET $2",
                    page_size,
                    offset,
                )
                page = [dict(row) for row in rows]
            else:
                cursor = await self._conn.execute(
                    f"SELECT * FROM {table} LIMIT ? OFFSET ?",
                    (page_size, offset),
                )
                columns = (
                    [desc[0] for desc in cursor.description]
                    if cursor.description
                    else []
                )
                raw_rows = await cursor.fetchall()
                page = [dict(zip(columns, row)) for row in raw_rows]

            if not page:
                break
            yield page
            if len(page) < page_size:
                break
            offset += page_size

    async def list(self, prefix: str = "", limit: int = 1000) -> List[Any]:
        """List available tables in the database."""
        if self._conn is None:
            raise ConnectionError(f"Database adapter '{self.name}' not connected")

        if hasattr(self._conn, "fetch"):
            # asyncpg (PostgreSQL)
            rows = await self._conn.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name LIKE $1 "
                "ORDER BY table_name LIMIT $2",
                f"{prefix}%",
                limit,
            )
            return [row["table_name"] for row in rows]
        else:
            # aiosqlite
            cursor = await self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ? "
                "ORDER BY name LIMIT ?",
                (f"{prefix}%", limit),
            )
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def write(self, path: str, data: Any) -> Any:
        if self.config.read_only:
            raise PermissionError(
                f"Database source '{self.name}' is read-only. "
                f"Set read_only=False in DatabaseSourceConfig to enable writes."
            )

        if self._conn is None:
            raise ConnectionError(f"Database adapter '{self.name}' not connected")

        table = _validate_table_name(path)

        if not isinstance(data, dict):
            raise ValueError("Database write expects a dict of column: value pairs")

        columns = list(data.keys())
        values = list(data.values())

        # Validate column names
        for col in columns:
            _validate_table_name(col)

        if hasattr(self._conn, "execute"):
            if hasattr(self._conn, "fetchval"):
                # asyncpg — uses $1, $2, ... placeholders
                placeholders = ", ".join(f"${i+1}" for i in range(len(values)))
                col_names = ", ".join(columns)
                await self._conn.execute(
                    f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
                    *values,
                )
            else:
                # aiosqlite — uses ? placeholders
                placeholders = ", ".join("?" for _ in values)
                col_names = ", ".join(columns)
                await self._conn.execute(
                    f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
                    tuple(values),
                )
                await self._conn.commit()

        return {"table": table, "columns": columns}

    def supports_feature(self, feature: str) -> bool:
        supported = {"detect_change", "fetch", "fetch_pages", "list"}
        if not self.config.read_only:
            supported.add("write")
        return feature in supported
