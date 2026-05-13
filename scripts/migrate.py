#!/usr/bin/env python3
"""Template for a DataFlow numbered migration.

Copy to migrations/NNNN_your_change.py and adapt.
See .claude/skills/02-dataflow/migration-scaffold.md for the full walkthrough.

Contract enforced by this template:
  1. Every dynamic identifier routes through `dialect.quote_identifier()`
     (rules/dataflow-identifier-safety.md MUST Rule 1).
  2. Every `upgrade()` has a matching `downgrade()`
     (rules/schema-migration.md MUST Rule 3).
  3. Destructive downgrades require explicit `force_downgrade=True`
     (sibling of rules/dataflow-identifier-safety.md MUST Rule 4's force_drop).
  4. No raw f-string DDL interpolation anywhere
     (rules/framework-first.md: raw SQL in application code is BLOCKED).

Downstream consumers: copy this file, rename, and replace the three sections
marked `# REPLACE:`. Do not import this module directly — it is a template,
not a runnable migration.

This template imports from `kailash-dataflow` (kailash-py), which is not a
dependency of the kailash-rs repo where this template lives. The pyright
directive below suppresses the template-only import warning; downstream
Python projects that copy this file will resolve the import normally.
"""

# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportUnusedImport=false

from __future__ import annotations

import logging
from typing import Any

from dataflow.adapters.dialect import DialectManager

logger = logging.getLogger(__name__)

# REPLACE: migration metadata ------------------------------------------------
MIGRATION_ID = "NNNN_your_change_description"
DESCRIPTION = "One-sentence summary of what this migration changes and why."
# Set DESTRUCTIVE = True if upgrade() drops data or downgrade() cannot restore
# the prior row contents. Destructive migrations require force_downgrade=True
# on the relevant direction.
DESTRUCTIVE = False
# ----------------------------------------------------------------------------


class DowngradeRefusedError(RuntimeError):
    """Raised when a destructive downgrade is invoked without force_downgrade=True."""


async def upgrade(conn: Any, database_type: str) -> None:
    """Apply the forward migration against `conn`.

    `conn` is the active DataFlow connection (asyncpg / aiomysql / aiosqlite
    wrapper). `database_type` is one of `"postgresql"` / `"mysql"` / `"sqlite"`
    and is passed into `DialectManager.get_dialect()` to pick the correct quoting / length rules.
    """
    dialect = DialectManager.get_dialect(database_type)

    # REPLACE: forward DDL ---------------------------------------------------
    # Example: add a nullable column named `signup_source` to `users`.
    # Use SQL-standard type literals; dialect adapters tolerate the
    # portable names (TEXT / VARCHAR / INTEGER / TIMESTAMP / BOOLEAN).
    # For dialect-specific types (BYTEA vs BLOB, SERIAL vs AUTOINCREMENT),
    # branch on `database_type` explicitly and keep each branch quoted.
    table = dialect.quote_identifier("users")
    column = dialect.quote_identifier("signup_source")
    column_type = "TEXT"
    await conn.execute(
        f"ALTER TABLE {table} ADD COLUMN {column} {column_type} DEFAULT 'organic'"
    )
    # Per rules/observability.md Rule 8, schema-revealing field names
    # (column, index, constraint names) MUST be emitted at DEBUG or
    # hashed. INFO-level operator signal carries migration_id + op only;
    # the column identity lives at DEBUG for ad-hoc investigation.
    logger.info(
        "migration.upgrade.ok",
        extra={"migration_id": MIGRATION_ID, "op": "add_column"},
    )
    logger.debug(
        "migration.upgrade.detail",
        extra={
            "migration_id": MIGRATION_ID,
            "op": "add_column",
            "column": "signup_source",
        },
    )
    # ------------------------------------------------------------------------


async def downgrade(
    conn: Any,
    database_type: str,
    *,
    force_downgrade: bool = False,
) -> None:
    """Reverse the forward migration against `conn`.

    Destructive downgrades MUST refuse by default and require `force_downgrade=True`.
    Non-destructive downgrades may ignore the flag.
    """
    dialect = DialectManager.get_dialect(database_type)

    # REPLACE: reverse DDL ---------------------------------------------------
    # Example (destructive — drops the column and loses per-row backfill data):
    if DESTRUCTIVE and not force_downgrade:
        raise DowngradeRefusedError(
            f"{MIGRATION_ID} downgrade drops data and is irreversible — "
            f"pass force_downgrade=True to acknowledge data loss"
        )
    table = dialect.quote_identifier("users")
    column = dialect.quote_identifier("signup_source")
    await conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
    logger.info(
        "migration.downgrade.ok",
        extra={
            "migration_id": MIGRATION_ID,
            "op": "drop_column",
            "force_downgrade": force_downgrade,
        },
    )
    logger.debug(
        "migration.downgrade.detail",
        extra={
            "migration_id": MIGRATION_ID,
            "op": "drop_column",
            "column": "signup_source",
        },
    )
    # ------------------------------------------------------------------------


# Mandatory Tier 2 test scaffold — copy into
# tests/integration/migrations/test_NNNN_your_change.py and adapt.
#
# import pytest
# from dataflow.adapters.dialect import DialectManager
# from dataflow.adapters.exceptions import InvalidIdentifierError
# from migrations import _NNNN_your_change as migration
#
# @pytest.mark.integration
# async def test_upgrade_applies(pg_conn):
#     await migration.upgrade(pg_conn, "postgresql")
#     rows = await pg_conn.fetch(
#         "SELECT column_name FROM information_schema.columns "
#         "WHERE table_name = 'users' AND column_name = 'signup_source'"
#     )
#     assert len(rows) == 1
#
# @pytest.mark.integration
# async def test_downgrade_reverses(pg_conn):
#     await migration.upgrade(pg_conn, "postgresql")
#     await migration.downgrade(pg_conn, "postgresql", force_downgrade=True)
#     rows = await pg_conn.fetch(
#         "SELECT column_name FROM information_schema.columns "
#         "WHERE table_name = 'users' AND column_name = 'signup_source'"
#     )
#     assert rows == []
#
# @pytest.mark.regression
# def test_dialect_rejects_injection_payloads():
#     dialect = DialectManager.get_dialect("postgresql")
#     with pytest.raises(InvalidIdentifierError):
#         dialect.quote_identifier('users"; DROP TABLE customers; --')
#     with pytest.raises(InvalidIdentifierError):
#         dialect.quote_identifier("column with spaces")
#     with pytest.raises(InvalidIdentifierError):
#         dialect.quote_identifier("123_leading_digit")
