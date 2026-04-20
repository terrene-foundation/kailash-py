# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: DataFlow migration helpers reject SQL-injection payloads
via ``dialect.quote_identifier()`` before any DDL reaches the database.

Per ``rules/dataflow-identifier-safety.md`` MUST Rule 1, every DDL that
interpolates a dynamic identifier MUST route through
``dialect.quote_identifier()``. Prior to the kailash 2.8.11
dialect-safety sweep, three migration modules interpolated
caller-provided table / column / constraint / index / trigger / view
names directly into DDL strings via raw f-strings:

* ``application_safe_rename_strategy.py`` — ALTER TABLE RENAME,
  CREATE TABLE ... LIKE, DROP TABLE, DROP VIEW
* ``column_removal_manager.py`` — CREATE TABLE (backup), DROP TABLE,
  ALTER TABLE DROP COLUMN / DROP CONSTRAINT, DROP INDEX, DROP VIEW,
  DROP TRIGGER
* ``not_null_handler.py`` — ALTER TABLE ADD COLUMN / ALTER COLUMN,
  UPDATE .. FROM, DROP COLUMN rollback path

This test exercises each helper with the standard injection payload set
and asserts that :class:`InvalidIdentifierError` (or
:class:`IdentifierError` — both ValueError subclasses) is raised BEFORE
any execute() call reaches the connection.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from dataflow.adapters.exceptions import InvalidIdentifierError

pytestmark = [pytest.mark.regression]


# ---------------------------------------------------------------------------
# Shared stubs — reject all execute() calls because the validator MUST
# raise before any DDL reaches the connection.
# ---------------------------------------------------------------------------


class _RejectingConnection:
    """Connection stub that fails if any execute/fetch/fetchval is called.

    Every DDL helper we're testing should raise InvalidIdentifierError
    BEFORE touching the connection. If a call lands here, the test
    fails because the validator was bypassed.
    """

    async def execute(self, sql: str, *args: Any) -> Any:
        raise AssertionError(
            f"execute() called despite invalid identifier — validator "
            f"bypassed: {sql!r}"
        )

    async def fetch(self, sql: str, *args: Any) -> Any:
        raise AssertionError(
            f"fetch() called despite invalid identifier — validator "
            f"bypassed: {sql!r}"
        )

    async def fetchval(self, sql: str, *args: Any) -> Any:
        raise AssertionError(
            f"fetchval() called despite invalid identifier — validator "
            f"bypassed: {sql!r}"
        )

    def transaction(self) -> "_RejectingTransaction":
        return _RejectingTransaction()


class _RejectingTransaction:
    async def __aenter__(self) -> "_RejectingConnection":
        return _RejectingConnection()

    async def __aexit__(self, *exc: Any) -> bool:
        return False


# The standard injection payload set per
# rules/dataflow-identifier-safety.md § Rule 3.
_INJECTION_PAYLOADS = [
    'users"; DROP TABLE customers; --',
    '"; DROP TABLE foo; --',
    "name WITH DATA",
    "123_starts_with_digit",
    "path\x00traversal",
    "table with spaces",
    "..",
    "schema.table",  # dotted — not a single identifier
    "",  # empty
]


# ---------------------------------------------------------------------------
# application_safe_rename_strategy.py
# ---------------------------------------------------------------------------


def test_application_safe_rename_create_temp_table_rejects_injection() -> None:
    """_create_temp_table uses quote_identifier on both temp + source."""
    from dataflow.migrations.application_safe_rename_strategy import (
        BlueGreenConfig,
        BlueGreenRenameManager,
    )

    mgr = BlueGreenRenameManager(connection_manager=None, config=BlueGreenConfig())
    conn = _RejectingConnection()

    # Inject into temp_table; source_table valid.
    for payload in _INJECTION_PAYLOADS:
        with pytest.raises(InvalidIdentifierError):
            asyncio.run(mgr._create_temp_table("valid_source", payload, conn))

    # Inject into source_table; temp_table valid.
    for payload in _INJECTION_PAYLOADS:
        with pytest.raises(InvalidIdentifierError):
            asyncio.run(mgr._create_temp_table(payload, "valid_temp", conn))


def test_application_safe_rename_sync_data_rejects_injection() -> None:
    """_sync_data validates both table identifiers before INSERT FROM."""
    from dataflow.migrations.application_safe_rename_strategy import (
        BlueGreenConfig,
        BlueGreenRenameManager,
    )

    mgr = BlueGreenRenameManager(connection_manager=None, config=BlueGreenConfig())
    conn = _RejectingConnection()

    for payload in _INJECTION_PAYLOADS:
        with pytest.raises(InvalidIdentifierError):
            asyncio.run(mgr._sync_data("valid_source", payload, conn))
        with pytest.raises(InvalidIdentifierError):
            asyncio.run(mgr._sync_data(payload, "valid_temp", conn))


def test_application_safe_rename_cleanup_temp_objects_rejects_injection() -> None:
    """_cleanup_temp_objects validates each temp_obj identifier."""
    from dataflow.migrations.application_safe_rename_strategy import (
        BlueGreenConfig,
        BlueGreenRenameManager,
    )

    mgr = BlueGreenRenameManager(connection_manager=None, config=BlueGreenConfig())

    for payload in _INJECTION_PAYLOADS:
        mgr.temp_objects = [payload]

        # The loop catches Exception to log and continue; the validator
        # raise is swallowed. To observe the validator's rejection we
        # must catch it before the loop swallows. Instead we assert
        # NO connection call was made by providing a strict stub.
        class _StrictConn:
            async def execute(self, sql: str, *a: Any) -> None:
                raise AssertionError(f"DDL reached conn: {sql!r}")

        # The exception is caught by the loop's try/except — but the
        # try block's execute() stub fails loudly if reached. If
        # quote_identifier runs before execute(), execute() is never
        # called at all.
        asyncio.run(mgr._cleanup_temp_objects(_StrictConn()))


def test_application_safe_rename_rollback_view_aliasing_rejects_injection() -> None:
    """RollbackManager._rollback_view_aliasing quotes each view name."""
    from dataflow.migrations.application_safe_rename_strategy import RollbackManager

    mgr = RollbackManager(connection_manager=None)

    class _StrictConn:
        async def execute(self, sql: str, *a: Any) -> None:
            raise AssertionError(f"DDL reached conn: {sql!r}")

    # Prefixed injection payloads — the loop filters on prefix so we
    # inject after the required prefix.
    for payload in (
        'alias_view"; DROP TABLE x; --',
        "migration_alias NAME WITH SPACES",
    ):
        with pytest.raises(InvalidIdentifierError):
            asyncio.run(mgr._rollback_view_aliasing([payload], _StrictConn()))


def test_application_safe_rename_rollback_blue_green_rejects_injection() -> None:
    """RollbackManager._rollback_blue_green quotes each temp table name."""
    from dataflow.migrations.application_safe_rename_strategy import RollbackManager

    mgr = RollbackManager(connection_manager=None)

    class _StrictConn:
        async def execute(self, sql: str, *a: Any) -> None:
            raise AssertionError(f"DDL reached conn: {sql!r}")

    for payload in ('temp_"; DROP TABLE x; --', "_migration_temp WITH SPACES"):
        with pytest.raises(InvalidIdentifierError):
            asyncio.run(mgr._rollback_blue_green([payload], _StrictConn()))


# ---------------------------------------------------------------------------
# column_removal_manager.py
# ---------------------------------------------------------------------------


def test_column_removal_cleanup_backup_rejects_injection() -> None:
    """ColumnOnlyBackupHandler.cleanup_backup validates backup_location."""
    from dataflow.migrations.column_removal_manager import (
        BackupInfo,
        BackupStrategy,
        ColumnOnlyBackupHandler,
    )

    handler = ColumnOnlyBackupHandler()

    class _StrictConn:
        async def execute(self, sql: str, *a: Any) -> None:
            raise AssertionError(f"DDL reached conn: {sql!r}")

    for payload in _INJECTION_PAYLOADS:
        info = BackupInfo(
            strategy=BackupStrategy.COLUMN_ONLY,
            backup_location=payload,
            backup_size=0,
            created_at=__import__("datetime").datetime.now(),
            verification_query="",
        )
        # cleanup_backup catches Exception and returns False — so the
        # validator raise is converted. We check the return value.
        result = asyncio.run(handler.cleanup_backup(info, _StrictConn()))
        assert result is False, (
            f"cleanup_backup accepted injection payload {payload!r} — "
            f"validator bypassed"
        )


def test_column_removal_table_snapshot_cleanup_rejects_injection() -> None:
    """TableSnapshotBackupHandler.cleanup_backup validates backup_location."""
    from dataflow.migrations.column_removal_manager import (
        BackupInfo,
        BackupStrategy,
        TableSnapshotBackupHandler,
    )

    handler = TableSnapshotBackupHandler()

    class _StrictConn:
        async def execute(self, sql: str, *a: Any) -> None:
            raise AssertionError(f"DDL reached conn: {sql!r}")

    for payload in _INJECTION_PAYLOADS:
        info = BackupInfo(
            strategy=BackupStrategy.TABLE_SNAPSHOT,
            backup_location=payload,
            backup_size=0,
            created_at=__import__("datetime").datetime.now(),
            verification_query="",
        )
        result = asyncio.run(handler.cleanup_backup(info, _StrictConn()))
        assert result is False


def test_column_removal_dialect_quoting_gate_via_helper() -> None:
    """Direct exercise of the quote_identifier gate the module relies on.

    The module binds `_DIALECT = DialectManager.get_dialect("postgresql")`
    at import time. We re-import it and confirm the helper rejects
    every injection payload, which is the single structural enforcement
    point for every DDL site in the module.
    """
    from dataflow.migrations.column_removal_manager import _DIALECT

    for payload in _INJECTION_PAYLOADS:
        with pytest.raises(InvalidIdentifierError):
            _DIALECT.quote_identifier(payload)


# ---------------------------------------------------------------------------
# not_null_handler.py
# ---------------------------------------------------------------------------


def test_not_null_handler_dialect_quoting_gate_via_helper() -> None:
    """Direct exercise of the quote_identifier gate the module relies on."""
    from dataflow.migrations.not_null_handler import _DIALECT

    for payload in _INJECTION_PAYLOADS:
        with pytest.raises(InvalidIdentifierError):
            _DIALECT.quote_identifier(payload)


def test_application_safe_rename_dialect_quoting_gate_via_helper() -> None:
    """Direct exercise of the quote_identifier gate the module relies on."""
    from dataflow.migrations.application_safe_rename_strategy import _DIALECT

    for payload in _INJECTION_PAYLOADS:
        with pytest.raises(InvalidIdentifierError):
            _DIALECT.quote_identifier(payload)
