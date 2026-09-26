"""Memory databases use their actual instance identity in both cache keyspaces."""

import logging
import shutil
import socket
import subprocess
import time

import pytest

from dataflow import DataFlow
from dataflow.cache.key_generator import (
    express_db_instance_fingerprint,
    resolve_db_identity,
)
from dataflow.core.pool_utils import is_sqlite
from dataflow.core.pool_validator import validate_pool_config


@pytest.mark.parametrize("url", [":memory:", "sqlite:///:memory:", "sqlite://:memory:"])
@pytest.mark.asyncio
async def test_memory_aliases_get_distinct_query_and_express_identities(url, caplog):
    databases = [DataFlow(url, test_mode=False) for _ in range(2)]
    try:
        for db in databases:
            assert await db.initialize()
            assert db.config.database.url == url
        a, b = databases
        assert a._memory_db_uri != b._memory_db_uri
        query = [db._cache_integration.key_generator for db in databases]
        express = [db.express._key_gen for db in databases]
        assert query[0].db_identity and query[1].db_identity
        assert query[0].generate_key("Row", "SELECT 1", []) != query[1].generate_key(
            "Row", "SELECT 1", []
        )
        assert express[0].express_db_instance and express[1].express_db_instance
        assert express[0].generate_express_key("Row", "list", {}) != express[
            1
        ].generate_express_key("Row", "list", {})
        assert not [
            r.getMessage()
            for r in caplog.records
            if r.levelno >= logging.WARNING
            and (
                "db_identity" in r.getMessage()
                or "db_instance_disabled" in r.getMessage()
                or "probe failed" in r.getMessage()
            )
        ]
    finally:
        for db in databases:
            await db.close_async()


@pytest.mark.parametrize(
    "url",
    [":memory:", "file:unit_memory?mode=memory&cache=shared", "sqlite:///:memory:"],
)
def test_sqlite_alias_pool_validation_needs_no_server_probe(url, caplog):
    assert is_sqlite(url)
    result = validate_pool_config(url, pool_size=5, max_overflow=2)
    assert result["status"] == "skipped"
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.asyncio
async def test_file_database_keeps_existing_fingerprint_bytes(tmp_path):
    url = f"sqlite:///{tmp_path / 'same.db'}"
    db = DataFlow(url, test_mode=False)
    try:
        assert await db.initialize()
        assert db._memory_db_uri is None
        assert (
            db._cache_integration.key_generator.db_identity
            == resolve_db_identity(url).identity
        )
        assert (
            db.express._key_gen.express_db_instance
            == express_db_instance_fingerprint(url)
        )
    finally:
        await db.close_async()


@pytest.fixture
def private_redis(tmp_path):
    """Own a private real Redis process; never touch an existing service."""
    executable = shutil.which("redis-server")
    if executable is None:
        pytest.skip("real Redis integration requires redis-server executable")
    import redis

    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    log = (tmp_path / "redis.log").open("w+")
    process = subprocess.Popen(
        [
            executable,
            "--bind",
            "127.0.0.1",
            "--port",
            str(port),
            "--save",
            "",
            "--appendonly",
            "no",
        ],
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    client = redis.Redis(host="127.0.0.1", port=port, socket_timeout=1)
    try:
        deadline = time.monotonic() + 5
        while True:
            assert process.poll() is None, "private Redis exited before readiness"
            try:
                if client.ping():
                    break
            except redis.exceptions.ConnectionError:
                assert time.monotonic() < deadline, "private Redis did not become ready"
                time.sleep(0.02)
        yield f"redis://127.0.0.1:{port}/0"
    finally:
        client.close()
        process.terminate()
        try:
            process.wait(timeout=5)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            log.close()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["query", "express"])
async def test_shared_real_redis_separates_memory_rows_and_keeps_hits(
    private_redis, surface
):
    from dataflow.cache.async_redis_adapter import AsyncRedisCacheAdapter

    databases = [
        DataFlow("sqlite:///:memory:", redis_url=private_redis, test_mode=False)
        for _ in range(2)
    ]
    try:
        for db, value in zip(databases, ["alpha", "beta"]):
            # Query-cache configuration and the public Express option point at
            # the SAME owned Redis service, with unmodified production backends.
            db.config.cache_redis_url = private_redis

            @db.model
            class SharedMemoryRow:
                id: str
                value: str

            assert await db.initialize()
            assert isinstance(
                db._cache_integration.cache_manager, AsyncRedisCacheAdapter
            )
            assert isinstance(db.express._cache_manager, AsyncRedisCacheAdapter)
            await db.express.create("SharedMemoryRow", {"id": "same", "value": value})

        async def read(db):
            if surface == "express":
                return await db.express.list("SharedMemoryRow")
            return await db._nodes["SharedMemoryRowListNode"]().execute_async()

        def values(result):
            rows = result if surface == "express" else result["records"]
            return [row["value"] for row in rows]

        for db, expected in zip(databases, ["alpha", "beta"]):
            first = await read(db)
            assert values(first) == [expected]
            hits = db.express.get_cache_stats()["hits"]
            warm = await read(db)
            assert values(warm) == [expected]
            if surface == "express":
                assert db.express.get_cache_stats()["hits"] == hits + 1
            else:
                assert first["_cache"]["hit"] is False
                assert warm["_cache"]["hit"] is True

        if surface == "express":
            await databases[0].express.update(
                "SharedMemoryRow", "same", {"value": "changed"}
            )
        else:
            await databases[0]._nodes["SharedMemoryRowUpdateNode"]().execute_async(
                filter={"id": "same"}, fields={"value": "changed"}
            )
        assert values(await read(databases[0])) == ["changed"]
        assert values(await read(databases[1])) == ["beta"]
    finally:
        for db in databases:
            await db.close_async()


@pytest.mark.asyncio
async def test_managed_memory_crosses_threads_while_raw_memory_still_warns(
    monkeypatch, caplog
):
    import asyncio
    import sqlite3
    from contextlib import closing

    from dataflow.core import async_utils

    monkeypatch.setattr(async_utils, "_sqlite_async_warning_shown", False)
    db = DataFlow(":memory:", test_mode=False)
    try:

        @db.model
        class ManagedMemoryProof:
            id: str
            value: str

        await db.initialize()
        await db.express.create("ManagedMemoryProof", {"id": "one", "value": "shared"})

        def read_on_another_thread():
            with closing(sqlite3.connect(db._memory_db_uri, uri=True)) as connection:
                return connection.execute(
                    "SELECT value FROM managed_memory_proofs"
                ).fetchall()

        assert await asyncio.to_thread(read_on_another_thread) == [("shared",)]
        assert not async_utils._sqlite_async_warning_shown
        assert not [r for r in caplog.records if r.name == "dataflow.core.async_utils"]

        with (
            closing(sqlite3.connect(":memory:")) as first,
            closing(sqlite3.connect(":memory:")) as second,
        ):
            first.execute("CREATE TABLE private_memory(value TEXT)")
            assert (
                second.execute(
                    "SELECT name FROM sqlite_master WHERE name='private_memory'"
                ).fetchall()
                == []
            )
        async_utils.warn_sqlite_async_limitation(":memory:")
        messages = [
            r.getMessage()
            for r in caplog.records
            if r.name == "dataflow.core.async_utils"
        ]
        assert len(messages) == 1
        assert "SEPARATE in-memory database" in messages[0]
    finally:
        await db.close_async()


def test_explicit_replica_url_keeps_its_own_target():
    from dataflow.utils.connection import ConnectionManager

    with DataFlow("sqlite:///:memory:", test_mode=False) as db:
        assert db._connection_manager._get_db_url() == db._memory_db_uri
        replica = ConnectionManager(db, url_override="sqlite:///replica.db")
        assert replica._get_db_url() == "sqlite:///replica.db"


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [":memory:", "sqlite:///:memory:", "sqlite://:memory:"])
async def test_public_getter_reads_express_memory_database(url):
    db = DataFlow(url, test_mode=False)
    connection = None
    try:

        @db.model
        class GetterMemoryRow:
            id: str
            value: str

        assert await db.initialize()
        await db.express.create("GetterMemoryRow", {"id": "one", "value": "shared"})
        connection = await db._get_async_database_connection()
        async with connection.execute("SELECT value FROM getter_memory_rows") as cursor:
            assert await cursor.fetchall() == [("shared",)]
    finally:
        if connection is not None:
            await connection.close()
        await db.close_async()


@pytest.mark.asyncio
@pytest.mark.parametrize("form", ["absolute", "file", "file_uri"])
async def test_public_getter_uses_canonical_sqlite_file_target(
    form, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "canonical.db"
    url = {
        "relative": "sqlite://canonical.db",
        "absolute": f"sqlite:///{path}",
        "file": f"file:{path}",
        "file_uri": f"file:{path}?mode=rwc",
    }[form]
    db = DataFlow(url, test_mode=False)
    connection = None
    try:

        @db.model
        class GetterFileRow:
            id: str
            value: str

        assert await db.initialize()
        await db.express.create("GetterFileRow", {"id": "one", "value": "on-disk"})
        assert path.is_file()
        connection = await db._get_async_database_connection()
        async with connection.execute("SELECT value FROM getter_file_rows") as cursor:
            assert await cursor.fetchall() == [("on-disk",)]
        async with connection.execute("PRAGMA database_list") as cursor:
            assert (await cursor.fetchone())[2] == str(path)
    finally:
        if connection is not None:
            await connection.close()
        await db.close_async()


@pytest.mark.asyncio
@pytest.mark.parametrize("form", ["relative", "adapter_absolute"])
async def test_public_getter_matches_adapter_path_contract(form, tmp_path, monkeypatch):
    from dataflow.adapters.sqlite import SQLiteAdapter

    monkeypatch.chdir(tmp_path)
    path = tmp_path / "adapter.db"
    url = "sqlite://adapter.db" if form == "relative" else f"sqlite://{path}"
    # This is the native adapter/getter address contract. SQLAlchemy registry
    # and synchronous migration URL handling are separate consumers.
    db = DataFlow(
        url, test_mode=False, auto_migrate=False, enable_model_persistence=False
    )
    adapter = SQLiteAdapter(url)
    connection = None
    try:
        await adapter.connect()
        await adapter.execute_query("CREATE TABLE address_proof(value TEXT)")
        await adapter.execute_query(
            "INSERT INTO address_proof(value) VALUES (?)", ["same-file"]
        )
        connection = await db._get_async_database_connection()
        async with connection.execute("SELECT value FROM address_proof") as cursor:
            assert await cursor.fetchall() == [("same-file",)]
        async with connection.execute("PRAGMA database_list") as cursor:
            assert (await cursor.fetchone())[2] == str(path)
    finally:
        if connection is not None:
            await connection.close()
        await adapter.disconnect()
        await db.close_async()
