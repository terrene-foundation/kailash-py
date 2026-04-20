# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for _feature_sql -- identifier validation and SQL generation.

These tests validate the security-critical surface: identifier validation
is enforced before any SQL interpolation. Integration-level SQL execution
is covered by test_feature_store.py.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from kailash_ml.engines._feature_sql import (
    create_feature_table,
    create_metadata_table,
    get_features_as_of,
    get_features_latest,
    get_features_range,
    list_all_schemas,
    read_metadata,
    upsert_batch,
    upsert_metadata,
)


@pytest.fixture
def conn():
    """Mock ConnectionManager with transaction support.

    Per L1 migration (kailash-ml 0.15.2), `_feature_sql` now calls
    `conn.dialect.quote_identifier(name)` directly — so the fixture's
    `dialect` MUST be a REAL `SQLiteDialect` instance (not an
    AsyncMock auto-attribute), otherwise the identifier validation
    path returns coroutines and the tests pass or fail for the
    wrong reason.
    """
    from kailash.db.dialect import SQLiteDialect

    mock = AsyncMock()
    mock.execute = AsyncMock()
    mock.fetchone = AsyncMock(return_value=None)
    mock.fetch = AsyncMock(return_value=[])
    mock.create_index = AsyncMock()
    # Real dialect: validates identifiers + quotes them; raises
    # IdentifierError (subclass of ValueError) on bad input, which is
    # what the TestIdentifierValidation class asserts via
    # pytest.raises(ValueError).
    mock.dialect = SQLiteDialect()

    # Transaction context manager mock
    tx_mock = AsyncMock()
    tx_mock.execute = AsyncMock()
    tx_mock.fetchone = AsyncMock(return_value=None)

    class _FakeTransaction:
        async def __aenter__(self):
            return tx_mock

        async def __aexit__(self, *args):
            pass

    mock.transaction = _FakeTransaction
    return mock


class TestIdentifierValidation:
    """Verify _validate_identifier is called for all SQL-interpolated names."""

    @pytest.mark.asyncio
    async def test_create_feature_table_validates_table_name(self, conn):
        with pytest.raises(ValueError):
            await create_feature_table(
                conn,
                "DROP TABLE evil; --",
                [("col1", "TEXT")],
                "entity_id",
                None,
            )

    @pytest.mark.asyncio
    async def test_create_feature_table_validates_entity_id(self, conn):
        with pytest.raises(ValueError):
            await create_feature_table(
                conn,
                "valid_table",
                [("col1", "TEXT")],
                "entity; DROP TABLE x",
                None,
            )

    @pytest.mark.asyncio
    async def test_create_feature_table_validates_timestamp(self, conn):
        with pytest.raises(ValueError):
            await create_feature_table(
                conn,
                "valid_table",
                [("col1", "TEXT")],
                "entity_id",
                "bad name with spaces",
            )

    @pytest.mark.asyncio
    async def test_create_feature_table_validates_columns(self, conn):
        with pytest.raises(ValueError):
            await create_feature_table(
                conn,
                "valid_table",
                [("col1", "TEXT"), ("evil;col", "TEXT")],
                "entity_id",
                None,
            )

    @pytest.mark.asyncio
    async def test_create_feature_table_valid(self, conn):
        await create_feature_table(
            conn,
            "features_v1",
            [("temperature", "REAL"), ("humidity", "REAL")],
            "entity_id",
            "timestamp",
        )
        assert conn.execute.call_count >= 1
        assert conn.create_index.call_count == 1


class TestCreateMetadataTable:
    @pytest.mark.asyncio
    async def test_creates_table(self, conn):
        await create_metadata_table(conn)
        call_sql = conn.execute.call_args[0][0]
        assert "_kml_feature_metadata" in call_sql
        assert "schema_name TEXT PRIMARY KEY" in call_sql


class TestGetFeaturesLatest:
    @pytest.mark.asyncio
    async def test_returns_rows(self, conn):
        conn.fetch = AsyncMock(return_value=[{"entity_id": "e1", "temp": 20.5}])
        result = await get_features_latest(
            conn, "features_v1", ["temp"], ["e1"], "entity_id"
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_validates_table_name(self, conn):
        with pytest.raises(ValueError):
            await get_features_latest(conn, "bad table!", ["temp"], ["e1"], "entity_id")


class TestGetFeaturesAsOf:
    @pytest.mark.asyncio
    async def test_validates_table_name(self, conn):
        from datetime import datetime, timezone

        with pytest.raises(ValueError):
            await get_features_as_of(
                conn,
                "bad; table",
                ["temp"],
                ["e1"],
                "entity_id",
                datetime.now(timezone.utc),
            )


class TestGetFeaturesRange:
    @pytest.mark.asyncio
    async def test_validates_table_name(self, conn):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        with pytest.raises(ValueError):
            await get_features_range(
                conn, "bad table!", ["temp"], "entity_id", now, now
            )


class TestUpsertBatch:
    @pytest.mark.asyncio
    async def test_validates_table_name(self, conn):
        with pytest.raises(ValueError):
            await upsert_batch(
                conn,
                "DROP TABLE evil",
                [{"entity_id": "e1", "temp": 20.0, "created_at": "now"}],
                ["entity_id", "temp", "created_at"],
            )

    @pytest.mark.asyncio
    async def test_valid_upsert(self, conn):
        await upsert_batch(
            conn,
            "features_v1",
            [{"entity_id": "e1", "temp": 20.0, "created_at": "2026-01-01"}],
            ["entity_id", "temp", "created_at"],
        )
        # Executes inside the transaction context — the tx_mock is internal
        # We verify no exception was raised and the function completed


class TestReadMetadata:
    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self, conn):
        result = await read_metadata(conn, "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_row(self, conn):
        conn.fetchone = AsyncMock(
            return_value={"schema_name": "test", "schema_hash": "abc"}
        )
        result = await read_metadata(conn, "test")
        assert result is not None
        assert result["schema_name"] == "test"


class TestUpsertMetadata:
    @pytest.mark.asyncio
    async def test_inserts_new(self, conn):
        # tx_mock.fetchone returns None by default → INSERT path
        await upsert_metadata(
            conn, "my_schema", "hash123", 1, 100, "2026-04-01T00:00:00"
        )
        # Completes without error — INSERT executed inside transaction

    @pytest.mark.asyncio
    async def test_updates_existing(self, conn):
        # Need the tx mock's fetchone to return existing row
        tx_mock = AsyncMock()
        tx_mock.fetchone = AsyncMock(return_value={"schema_name": "my_schema"})
        tx_mock.execute = AsyncMock()

        class _TxWithExisting:
            async def __aenter__(self):
                return tx_mock

            async def __aexit__(self, *args):
                pass

        conn.transaction = _TxWithExisting
        await upsert_metadata(
            conn, "my_schema", "hash456", 2, 200, "2026-04-01T00:00:00"
        )
        # Verify UPDATE was called (not INSERT)
        call_args = tx_mock.execute.call_args[0][0]
        assert "UPDATE" in call_args


class TestListAllSchemas:
    @pytest.mark.asyncio
    async def test_returns_list(self, conn):
        conn.fetch = AsyncMock(
            return_value=[
                {"schema_name": "a", "version": 1},
                {"schema_name": "b", "version": 2},
            ]
        )
        result = await list_all_schemas(conn)
        assert len(result) == 2
