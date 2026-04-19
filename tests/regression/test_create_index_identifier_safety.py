# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: ``ConnectionManager.create_index()`` rejects unsafe identifiers
via ``dialect.quote_identifier()`` before the DB driver sees anything.

Per ``rules/dataflow-identifier-safety.md`` MUST Rule 1, every DDL that
interpolates a dynamic identifier MUST route through
``dialect.quote_identifier()``. This test exercises the real DDL hot path:
``ConnectionManager.create_index()`` on a live SQLite database, asserting
that malicious table / index names raise :class:`IdentifierError` BEFORE
any SQL reaches aiosqlite.

This closes #550 — core SDK parity with DataFlow's canonical
``quote_identifier`` contract.
"""

from __future__ import annotations

import pytest

from kailash.db.connection import ConnectionManager
from kailash.db.dialect import IdentifierError


@pytest.fixture
async def conn():
    """Real aiosqlite-backed ConnectionManager against an in-memory db.

    Uses a real connection (Tier 2 discipline — no mocking of the
    adapter). The test asserts that ``create_index`` rejects unsafe
    identifiers at the quote_identifier boundary BEFORE issuing any
    DDL to the driver; the real connection is needed to prove the
    rejection is not driver-side.
    """
    mgr = ConnectionManager("sqlite:///:memory:")
    await mgr.initialize()
    # Pre-create a table so a malicious-index-on-valid-table scenario
    # doesn't fail for the wrong reason.
    await mgr.execute("CREATE TABLE test_users (id INTEGER, name TEXT)")
    try:
        yield mgr
    finally:
        await mgr.close()


class TestCreateIndexRejectsUnsafeTable:
    """``create_index(table=...)`` MUST reject malicious table names."""

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_table_name_with_injection_rejected(self, conn):
        with pytest.raises(IdentifierError):
            await conn.create_index(
                "idx_name",
                'users"; DROP TABLE customers; --',
                "col",
            )

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_table_name_with_semicolon_rejected(self, conn):
        with pytest.raises(IdentifierError):
            await conn.create_index("idx_name", "users;drop", "col")

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_table_name_with_space_rejected(self, conn):
        with pytest.raises(IdentifierError):
            await conn.create_index("idx_name", "users WHERE 1=1", "col")


class TestCreateIndexRejectsUnsafeIndexName:
    """``create_index(index_name=...)`` MUST reject malicious index names."""

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_index_name_injection_rejected(self, conn):
        with pytest.raises(IdentifierError):
            await conn.create_index(
                'idx"; DROP TABLE test_users; --',
                "test_users",
                "id",
            )

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_index_name_with_backtick_rejected(self, conn):
        with pytest.raises(IdentifierError):
            await conn.create_index("`injected`", "test_users", "id")


class TestCreateIndexRejectsUnsafeColumn:
    """``create_index(columns=...)`` MUST reject malicious column names."""

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_column_injection_rejected(self, conn):
        with pytest.raises(IdentifierError):
            await conn.create_index(
                "idx_name",
                "test_users",
                "id); DROP TABLE test_users; --",
            )

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_multi_column_injection_on_second_rejected(self, conn):
        with pytest.raises(IdentifierError):
            await conn.create_index(
                "idx_name",
                "test_users",
                "id, name; DROP TABLE test_users",
            )


class TestCreateIndexSucceedsForValidIdentifiers:
    """Sanity: valid identifiers still work end-to-end on a real DB."""

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_create_valid_index(self, conn):
        # If the index were NOT created, a second call without IF NOT EXISTS
        # would raise. SQLite uses IF NOT EXISTS, so we verify creation via
        # sqlite_master reflection.
        await conn.create_index("idx_test_users_name", "test_users", "name")
        rows = await conn.fetch(
            "SELECT name FROM sqlite_master WHERE type='index' AND name = ?",
            "idx_test_users_name",
        )
        assert len(rows) == 1, f"Expected idx_test_users_name to exist, got: {rows}"

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_create_composite_index(self, conn):
        await conn.create_index("idx_test_users_composite", "test_users", "id, name")
        rows = await conn.fetch(
            "SELECT name FROM sqlite_master WHERE type='index' AND name = ?",
            "idx_test_users_composite",
        )
        assert len(rows) == 1


class TestCreateIndexUsesDialectQuoting:
    """The DDL produced by ``create_index`` wraps identifiers in the
    SQLite quote char (``"``). Reflection via ``sqlite_master.sql``
    confirms ``quote_identifier`` was applied, not a naive f-string."""

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_generated_ddl_is_quoted(self, conn):
        await conn.create_index("idx_quoted_check", "test_users", "name")
        rows = await conn.fetch(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name = ?",
            "idx_quoted_check",
        )
        assert len(rows) == 1
        sql = rows[0]["sql"] or ""
        # The DDL MUST contain dialect quotes around the identifiers.
        assert '"idx_quoted_check"' in sql, f"DDL missing quoted index name. Got: {sql}"
        assert '"test_users"' in sql, f"DDL missing quoted table name. Got: {sql}"
        assert '"name"' in sql, f"DDL missing quoted column name. Got: {sql}"
