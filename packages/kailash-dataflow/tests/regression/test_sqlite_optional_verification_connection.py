"""Physical verification distinguishes absent tables from unreachable memory state."""

import logging

import pytest

from dataflow import DataFlow


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        ":memory:",
        "sqlite:///:memory:",
        "sqlite://:memory:",
        "sqlite+aiosqlite:///:memory:",
    ],
)
async def test_unshared_memory_verification_is_structurally_inconclusive(
    tmp_path, caplog, url
):
    # This file owner has no shared memory handle for the separately supplied URL.
    db = DataFlow(f"sqlite:///{tmp_path / 'owner.db'}", test_mode=False)
    try:
        with caplog.at_level(logging.WARNING):
            result = await db._verify_table_physically_exists_detailed("SchemaRow", url)
        assert result == (None, "unverifiable-backend")
        assert db._open_sqlite_connection(url) is None
        assert [record.getMessage() for record in caplog.records] == [
            "engine.table_existence_check_inconclusive_memory"
        ]
    finally:
        await db.close_async()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["file", "native", "managed_memory", "shared_memory"])
async def test_owned_sqlite_verification_reads_real_committed_tables(
    tmp_path, caplog, kind
):
    url = {
        "file": f"sqlite:///{tmp_path / 'proof.db'}",
        "native": f"file:{tmp_path / 'proof.db'}?mode=rwc",
        "managed_memory": ":memory:",
        "shared_memory": f"file:{tmp_path / 'proof'}?mode=memory&cache=shared",
    }[kind]
    db = DataFlow(url, test_mode=False)
    expected_notices = (
        ["Using SQLite :memory: database for testing. Production requires PostgreSQL."]
        if kind == "managed_memory"
        else []
    )
    assert [r.getMessage() for r in caplog.records] == expected_notices
    caplog.clear()
    try:
        with caplog.at_level(logging.WARNING):
            connection = db._open_sqlite_connection(url)
            assert connection is not None
            try:
                connection.execute("CREATE TABLE schema_rows (id INTEGER PRIMARY KEY)")
                connection.execute("INSERT INTO schema_rows VALUES (73)")
                connection.commit()
            finally:
                connection.close()
            assert await db._verify_table_physically_exists_detailed(
                "SchemaRow", url
            ) == (True, "verified")
            assert await db._verify_table_physically_exists_detailed(
                "MissingRow", url
            ) == (False, "verified")
            other = db._open_sqlite_connection(url)
            assert other is not None
            try:
                assert other.execute("SELECT id FROM schema_rows").fetchall() == [(73,)]
            finally:
                other.close()
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    finally:
        await db.close_async()
