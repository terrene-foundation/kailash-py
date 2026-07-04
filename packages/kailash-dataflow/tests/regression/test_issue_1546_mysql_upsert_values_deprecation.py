# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1546 — MySQL ``ON DUPLICATE KEY UPDATE
col = VALUES(col)`` is DEPRECATED as of MySQL 8.0.20.

MySQL 8.0.19 introduced the replacement row-alias form
``INSERT ... VALUES (...) AS new_row ON DUPLICATE KEY UPDATE col = new_row.col``,
which removes the deprecation. The row-alias form is NOT supported by MariaDB nor
by MySQL < 8.0.19, so DataFlow VERSION-GATES: it detects the server flavor/version
once (a single cached ``SELECT VERSION()`` round-trip) and emits the row-alias
form ONLY for non-MariaDB MySQL >= 8.0.19; every other server keeps the legacy
``VALUES(col)`` form those servers still require.

The single-record upsert path funnels through
``sql/dialects.py::MySQLDialect.build_upsert_query`` (called from
``core/nodes.py``); the version flag is threaded in as ``use_row_alias``.

Permanent regression tests — NEVER delete (``rules/testing.md`` Regression).
"""

from __future__ import annotations

import gc
import json
import os
import time
import warnings

import pytest

from dataflow import DataFlow
from dataflow.sql.dialects import (
    MySQLDialect,
    mysql_supports_row_alias_upsert,
    parse_mysql_server_version,
)

MYSQL_URL = os.getenv(
    "TEST_MYSQL_URL", "mysql://kailash_test:test_password@localhost:3307/kailash_test"
)


def _uid(prefix: str = "u") -> str:
    return f"{prefix}-{int(time.time() * 1_000_000)}"


def _raw_conn():
    import pymysql

    return pymysql.connect(
        host="localhost",
        port=3307,
        user="kailash_test",
        password="test_password",
        database="kailash_test",
    )


# ---------------------------------------------------------------------------
# Tier-2: real MySQL 8.0.46 — warning-free upsert + round-trip
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_mysql_single_upsert_emits_zero_deprecation_warnings():
    """AC1: on real MySQL 8.0.46, a single-record ``db.express.upsert`` round-trips
    correctly (read-back) AND the emitted upsert SQL raises ZERO deprecation
    warnings — proven by executing the dialect's generated row-alias SQL on a raw
    connection and asserting ``SHOW WARNINGS`` is empty, while the legacy
    ``VALUES()`` form on the SAME server DOES raise the 1287 deprecation warning
    (so the fix is load-bearing, not a no-op)."""
    db = DataFlow(MYSQL_URL, auto_migrate=True)

    @db.model
    class Issue1546Upsert:
        id: str
        email: str
        name: str
        __dataflow__ = {"indexes": [{"fields": ["email"], "unique": True}]}

    table = db._models["Issue1546Upsert"]["table_name"]

    conn = _raw_conn()
    conn.cursor().execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()
    db._ensure_connected()

    email = f"{_uid('alice')}@example.com"
    try:
        # End-to-end: express.upsert auto-detects 8.0.46 → row-alias form.
        await db.express.upsert_advanced(
            "Issue1546Upsert",
            where={"email": email},
            create={"id": _uid("u"), "email": email, "name": "Alice"},
            update={"name": "Alice"},
            conflict_on=["email"],
        )
        await db.express.upsert_advanced(
            "Issue1546Upsert",
            where={"email": email},
            create={"id": _uid("u2"), "email": email, "name": "Alice Updated"},
            update={"name": "Alice Updated"},
            conflict_on=["email"],
        )
        # The server was detected as row-alias-capable and cached once.
        assert db._mysql_upsert_row_alias is True

        # Round-trip read-back: exactly the UPDATE payload landed.
        fresh = await db.express.read(
            "Issue1546Upsert",
            (await db.express.list("Issue1546Upsert", {"email": email}))[0]["id"],
        )
        assert fresh["name"] == "Alice Updated"

        # Warning proof: build the EXACT SQL the single-record path emits and run
        # both branches on a raw connection, comparing SHOW WARNINGS.
        dialect = MySQLDialect()
        new_form = dialect.build_upsert_query(
            table,
            {"id": _uid("w"), "email": f"{_uid('w')}@x.com", "name": "N"},
            {"name": "N2"},
            ["email"],
            use_row_alias=True,
        )
        old_form = dialect.build_upsert_query(
            table,
            {"id": _uid("w2"), "email": f"{_uid('w2')}@x.com", "name": "N"},
            {"name": "N2"},
            ["email"],
            use_row_alias=False,
        )
        cur = conn.cursor()
        cur.execute(new_form.query, list(new_form.params.values()))
        cur.execute("SHOW WARNINGS")
        new_warnings = cur.fetchall()
        cur.execute(old_form.query, list(old_form.params.values()))
        cur.execute("SHOW WARNINGS")
        old_warnings = cur.fetchall()
        conn.commit()

        assert (
            new_warnings == ()
        ), f"row-alias form must be warning-free: {new_warnings}"
        # The legacy form DOES warn (1287) on 8.0.46 — proves the fix matters.
        assert any(w[1] == 1287 for w in old_warnings), old_warnings
    finally:
        conn.cursor().execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
        conn.close()
        db.close()


def _fresh_dict_rows(table: str, where_col: str, where_val) -> list:
    """Read-back on a FRESH connection (committed state), avoiding the raw
    connection's REPEATABLE-READ snapshot from earlier statements."""
    import pymysql

    conn = _raw_conn()
    try:
        cur = conn.cursor(pymysql.cursors.DictCursor)
        cur.execute(f"SELECT * FROM {table} WHERE {where_col} = %s", [where_val])
        return list(cur.fetchall())
    finally:
        conn.close()


def _assert_warning_free_and_legacy_warns(
    conn, new_sql: str, new_params, old_sql: str, old_params
) -> None:
    """Execute the row-alias SQL the bulk path emits on 8.0.46 and assert ZERO
    warnings; execute the legacy VALUES() form and assert it DOES raise the 1287
    deprecation warning (so the fix is load-bearing, not a no-op)."""
    cur = conn.cursor()
    cur.execute(new_sql, new_params)
    cur.execute("SHOW WARNINGS")
    new_warnings = cur.fetchall()
    cur.execute(old_sql, old_params)
    cur.execute("SHOW WARNINGS")
    old_warnings = cur.fetchall()
    conn.commit()
    assert new_warnings == (), f"row-alias form must be warning-free: {new_warnings}"
    assert any(w[1] == 1287 for w in old_warnings), old_warnings


# ---------------------------------------------------------------------------
# Tier-2: real MySQL 8.0.46 — the THREE bulk upsert paths are warning-free too
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_bulk_upsert_db_bulk_path_warning_free():
    """AC (bulk path 1): ``db.bulk.bulk_upsert`` round-trips AND the MySQL SQL it
    emits on 8.0.46 raises ZERO deprecation warnings (row-alias form), while the
    legacy VALUES() form on the same server DOES warn (1287)."""
    db = DataFlow(MYSQL_URL, auto_migrate=False)

    @db.model
    class Issue1546BulkDb:
        id: str
        tag: str
        name: str

    # DataFlow pluralizes the class name into the real table name and injects the
    # created_at/updated_at columns on the write path — the fixture DDL must match.
    table = db._models["Issue1546BulkDb"]["table_name"]
    conn = _raw_conn()
    conn.cursor().execute(f"DROP TABLE IF EXISTS {table}")
    conn.cursor().execute(
        f"CREATE TABLE {table} (id VARCHAR(64) PRIMARY KEY, "
        f"tag VARCHAR(64) UNIQUE, name VARCHAR(64), "
        f"created_at DATETIME NULL, updated_at DATETIME NULL)"
    )
    conn.commit()

    tag = _uid("t")
    try:
        # Real bulk op through db.bulk: INSERT then UPDATE in place on the tag key.
        await db.bulk.bulk_upsert(
            "Issue1546BulkDb",
            [{"id": _uid("a"), "tag": tag, "name": "N1"}],
            conflict_on=["tag"],
        )
        await db.bulk.bulk_upsert(
            "Issue1546BulkDb",
            [{"id": _uid("b"), "tag": tag, "name": "N2"}],
            conflict_on=["tag"],
        )
        assert db._mysql_upsert_row_alias is True
        rows = _fresh_dict_rows(table, "tag", tag)
        assert len(rows) == 1 and rows[0]["name"] == "N2", rows

        # Warning proof: the EXACT SQL db.bulk emits, both branches, on a raw conn.
        columns = ["id", "tag", "name"]
        record = {"id": _uid("w"), "tag": _uid("wtag"), "name": "W"}
        new_q, new_p = db.bulk._build_mysql_upsert(
            table,
            columns,
            [record],
            "update",
            "Issue1546BulkDb",
            ["tag"],
            use_row_alias=True,
        )
        record2 = {"id": _uid("w2"), "tag": _uid("wtag2"), "name": "W"}
        old_q, old_p = db.bulk._build_mysql_upsert(
            table,
            columns,
            [record2],
            "update",
            "Issue1546BulkDb",
            ["tag"],
            use_row_alias=False,
        )
        _assert_warning_free_and_legacy_warns(conn, new_q, new_p, old_q, old_p)
    finally:
        conn.cursor().execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
        conn.close()
        db.close()


@pytest.mark.regression
@pytest.mark.integration
async def test_bulk_upsert_generated_node_path_warning_free():
    """AC (bulk path 2): the generated ``{Model}BulkUpsertNode``
    (``DataFlowBulkUpsertNode``) round-trips AND emits warning-free row-alias SQL on
    8.0.46; the legacy VALUES() form warns (1287)."""
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    from dataflow.nodes.bulk_upsert import DataFlowBulkUpsertNode
    from dataflow.sql.dialects import (
        mysql_row_alias_cache_key,
        resolve_mysql_row_alias_support,
    )

    table = "issue1546_bulk_node"
    conn = _raw_conn()
    conn.cursor().execute(f"DROP TABLE IF EXISTS {table}")
    # DataFlowBulkUpsertNode injects created_at/updated_at on the write path.
    conn.cursor().execute(
        f"CREATE TABLE {table} (id VARCHAR(64) PRIMARY KEY, "
        f"tag VARCHAR(64) UNIQUE, name VARCHAR(64), "
        f"created_at DATETIME NULL, updated_at DATETIME NULL)"
    )
    conn.commit()

    tag = _uid("t")
    try:
        node = DataFlowBulkUpsertNode(
            connection_string=MYSQL_URL, database_type="mysql", table_name=table
        )
        # Real node op: INSERT then UPDATE in place on the tag key.
        await node.async_run(
            data=[{"id": _uid("a"), "tag": tag, "name": "N1"}],
            conflict_on=["tag"],
            merge_strategy="update",
        )
        await node.async_run(
            data=[{"id": _uid("b"), "tag": tag, "name": "N2"}],
            conflict_on=["tag"],
            merge_strategy="update",
        )
        rows = _fresh_dict_rows(table, "tag", tag)
        assert len(rows) == 1 and rows[0]["name"] == "N2", rows

        # Warning proof via the node's own builder, both branches.
        cols = ["id", "tag", "name"]
        new_q, new_p = node._build_upsert_query(
            [{"id": _uid("w"), "tag": _uid("wt"), "name": "W"}],
            cols,
            "id, tag, name",
            False,
            "update",
            ["tag"],
            use_row_alias=True,
        )
        old_q, old_p = node._build_upsert_query(
            [{"id": _uid("w2"), "tag": _uid("wt2"), "name": "W"}],
            cols,
            "id, tag, name",
            False,
            "update",
            ["tag"],
            use_row_alias=False,
        )
        _assert_warning_free_and_legacy_warns(conn, new_q, new_p, old_q, old_p)

        # The server was probed as row-alias-capable (8.0.46).
        vnode = AsyncSQLDatabaseNode(
            connection_string=MYSQL_URL, database_type="mysql", validate_queries=False
        )
        try:
            assert (
                await resolve_mysql_row_alias_support(
                    vnode, mysql_row_alias_cache_key(MYSQL_URL)
                )
                is True
            )
        finally:
            await vnode.cleanup()
    finally:
        conn.cursor().execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
        conn.close()


@pytest.mark.regression
@pytest.mark.integration
async def test_bulk_create_pool_update_path_warning_free():
    """AC (bulk path 3): ``BulkCreatePoolNode`` with ``conflict_resolution='update'``
    round-trips (UPDATE in place on the id PK) AND emits warning-free row-alias SQL
    on 8.0.46; the legacy VALUES() form warns (1287)."""
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    from dataflow.nodes.bulk_create_pool import BulkCreatePoolNode
    from dataflow.sql.dialects import (
        mysql_row_alias_cache_key,
        resolve_mysql_row_alias_support,
    )

    table = "issue1546_bulk_pool"
    conn = _raw_conn()
    conn.cursor().execute(f"DROP TABLE IF EXISTS {table}")
    conn.cursor().execute(
        f"CREATE TABLE {table} (id VARCHAR(64) PRIMARY KEY, name VARCHAR(64))"
    )
    conn.commit()

    rid = _uid("p")
    try:
        node = BulkCreatePoolNode(
            connection_string=MYSQL_URL,
            database_type="mysql",
            table_name=table,
            conflict_resolution="update",
        )
        # Real node op twice on the same id → UPDATE in place, one row.
        await node.async_run(data=[{"id": rid, "name": "A"}])
        await node.async_run(data=[{"id": rid, "name": "B"}])
        rows = _fresh_dict_rows(table, "id", rid)
        assert len(rows) == 1 and rows[0]["name"] == "B", rows

        # Warning proof: reconstruct the EXACT update-branch SQL the node emits in
        # _process_direct (id PK conflict target, all non-id columns updated).
        vnode = AsyncSQLDatabaseNode(
            connection_string=MYSQL_URL, database_type="mysql", validate_queries=False
        )
        try:
            ura = await resolve_mysql_row_alias_support(
                vnode, mysql_row_alias_cache_key(MYSQL_URL)
            )
        finally:
            await vnode.cleanup()
        assert ura is True

        new_sql = (
            f"INSERT INTO {table} (id, name) VALUES (%s, %s) AS new_row "
            f"ON DUPLICATE KEY UPDATE name = new_row.name"
        )
        old_sql = (
            f"INSERT INTO {table} (id, name) VALUES (%s, %s) "
            f"ON DUPLICATE KEY UPDATE name = VALUES(name)"
        )
        _assert_warning_free_and_legacy_warns(
            conn, new_sql, [_uid("x"), "W"], old_sql, [_uid("y"), "W"]
        )
    finally:
        conn.cursor().execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
        conn.close()


# ---------------------------------------------------------------------------
# Tier-2: registry path (FINDING 1 — regression this PR introduces) + leak (FINDING 2)
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_registry_model_registration_warning_free():
    """FINDING 1 (regression this PR introduces): the model-registry upsert became
    reachable on MySQL via the #1547 pymysql-driver fix. Its ON DUPLICATE KEY UPDATE
    emitted the deprecated ``VALUES(col)`` on every model registration → ≥2× 1287 on
    8.0.20+. Version-gated now: a DEFAULT ``DataFlow(mysql_url)`` registration
    round-trips (``dataflow_model_registry`` row) AND the registry row-alias SQL
    (INSERT then ODKU UPDATE) is warning-free; the legacy form warns (1287). The
    version self-reference is table-qualified so the alias does not make it
    ambiguous (``version = dataflow_model_registry.version + 1``)."""
    conn = _raw_conn()
    cur = conn.cursor()
    db = DataFlow(MYSQL_URL, auto_migrate=True)

    @db.model
    class Issue1546Registry:
        id: str
        name: str

    db._ensure_connected()
    try:
        # Round-trip: the registry row landed for this model.
        cur.execute(
            "SELECT model_name FROM dataflow_model_registry "
            "WHERE model_name = 'Issue1546Registry'"
        )
        reg = cur.fetchone()
        assert reg is not None and reg[0] == "Issue1546Registry", reg

        # The sync version probe resolved row-alias support for this 8.0.46 server
        # and populated the SHARED process cache (keyed on the raw configured URL).
        from dataflow.sql.dialects import (
            mysql_row_alias_cache_key,
            mysql_row_alias_support_cached,
        )

        assert (
            mysql_row_alias_support_cached(mysql_row_alias_cache_key(MYSQL_URL)) is True
        )

        # Warning proof: the EXACT registry row-alias SQL, INSERT then ODKU UPDATE.
        cur.execute(
            "DELETE FROM dataflow_model_registry "
            "WHERE model_name IN ('WP1546', 'WPL1546')"
        )
        conn.commit()
        row_alias_sql = (
            "INSERT INTO dataflow_model_registry (model_name, model_checksum, "
            "model_definitions, application_id, status, version, metadata) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) AS new_row ON DUPLICATE KEY UPDATE "
            "model_checksum=new_row.model_checksum, "
            "model_definitions=new_row.model_definitions, "
            "updated_at=CURRENT_TIMESTAMP, "
            "version=dataflow_model_registry.version+1"
        )
        legacy_sql = (
            "INSERT INTO dataflow_model_registry (model_name, model_checksum, "
            "model_definitions, application_id, status, version, metadata) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
            "model_checksum=VALUES(model_checksum), "
            "model_definitions=VALUES(model_definitions), "
            "updated_at=CURRENT_TIMESTAMP, version=version+1"
        )
        empty = json.dumps({})
        cur.execute(row_alias_sql, ["WP1546", "ck1", empty, "app", "active", 1, empty])
        cur.execute("SHOW WARNINGS")
        w_insert = cur.fetchall()
        cur.execute(row_alias_sql, ["WP1546", "ck2", empty, "app", "active", 1, empty])
        cur.execute("SHOW WARNINGS")
        w_update = cur.fetchall()
        cur.execute(
            "SELECT version FROM dataflow_model_registry WHERE model_name='WP1546'"
        )
        # ODKU incremented the version — the table-qualified self-reference works
        # under the row alias (no "Column 'version' is ambiguous").
        assert cur.fetchone()[0] == 2
        cur.execute(legacy_sql, ["WPL1546", "ck1", empty, "app", "active", 1, empty])
        cur.execute(legacy_sql, ["WPL1546", "ck2", empty, "app", "active", 1, empty])
        cur.execute("SHOW WARNINGS")
        w_legacy = cur.fetchall()
        conn.commit()

        assert w_insert == (), f"registry INSERT must be warning-free: {w_insert}"
        assert w_update == (), f"registry ODKU UPDATE must be warning-free: {w_update}"
        assert any(w[1] == 1287 for w in w_legacy), w_legacy
    finally:
        cur.execute(
            "DELETE FROM dataflow_model_registry "
            "WHERE model_name IN ('WP1546', 'WPL1546')"
        )
        conn.commit()
        conn.close()
        db.close()


@pytest.mark.regression
@pytest.mark.integration
async def test_bulk_create_pool_no_connection_leak_resourcewarning():
    """FINDING 2 (leak symmetry): ``BulkCreatePoolNode._process_direct`` created a
    fresh per-batch ``AsyncSQLDatabaseNode`` and never cleaned it up — one leaked
    connection per batch (``ResourceWarning: AsyncSQLDatabaseNode GC'd while still
    connected``). Round-1 fixed the sibling ``bulk_upsert.py::_execute_query`` but
    not this parallel path. Assert real ops (batch_size=1 → multiple per-batch
    nodes) leak ZERO such ResourceWarnings, and all rows round-trip."""
    from dataflow.nodes.bulk_create_pool import BulkCreatePoolNode

    table = "issue1546_pool_leak"
    conn = _raw_conn()
    conn.cursor().execute(f"DROP TABLE IF EXISTS {table}")
    conn.cursor().execute(
        f"CREATE TABLE {table} (id VARCHAR(64) PRIMARY KEY, name VARCHAR(64))"
    )
    conn.commit()

    try:
        node = BulkCreatePoolNode(
            connection_string=MYSQL_URL,
            database_type="mysql",
            table_name=table,
            conflict_resolution="update",
            batch_size=1,  # force one per-batch sql_node per row
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            await node.async_run(
                data=[
                    {"id": _uid("a"), "name": "A"},
                    {"id": _uid("b"), "name": "B"},
                    {"id": _uid("c"), "name": "C"},
                ]
            )
            gc.collect()  # force finalizers; a leaked node would warn here
        leaks = [
            str(w.message)
            for w in caught
            if "AsyncSQLDatabaseNode GC'd while still connected" in str(w.message)
        ]
        assert leaks == [], f"per-batch nodes leaked connections: {leaks}"

        # Round-trip: all three rows landed.
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        assert cur.fetchone()[0] == 3
    finally:
        conn.cursor().execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()
        conn.close()


# ---------------------------------------------------------------------------
# Tier-1: generated-SQL pins for both version branches (no DB)
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_row_alias_branch_generates_alias_form():
    """MySQL >= 8.0.19 (non-MariaDB): the emitter declares a row alias on the
    INSERT and references it in ON DUPLICATE KEY UPDATE — no ``VALUES(col)``."""
    q = (
        MySQLDialect()
        .build_upsert_query(
            "t",
            {"id": 1, "email": "a@x.com", "name": "n"},
            {"name": "n2"},
            ["email"],
            use_row_alias=True,
        )
        .query
    )
    assert "VALUES (%s, %s, %s) AS new_row" in q
    assert "name = new_row.name" in q
    assert "VALUES(name)" not in q  # the deprecated reference is gone


def test_legacy_values_branch_generates_values_form_for_old_mysql_and_mariadb():
    """Sub-8.0.19 MySQL AND MariaDB (use_row_alias=False): the emitter MUST keep
    the legacy ``VALUES(col)`` form those servers require — no row alias."""
    q = (
        MySQLDialect()
        .build_upsert_query(
            "t",
            {"id": 1, "email": "a@x.com", "name": "n"},
            {"name": "n2"},
            ["email"],
            use_row_alias=False,
        )
        .query
    )
    assert "name = VALUES(name)" in q
    assert "AS new_row" not in q
    assert "new_row." not in q


def test_row_alias_no_updatable_cols_defaults_to_alias_id():
    """When conflict_on covers every column, the no-op self-assignment uses the
    alias (``id = new_row.id``) in the row-alias branch and ``VALUES(id)`` in the
    legacy branch."""
    new_q = (
        MySQLDialect()
        .build_upsert_query("t", {"id": 1}, {}, ["id"], use_row_alias=True)
        .query
    )
    old_q = (
        MySQLDialect()
        .build_upsert_query("t", {"id": 1}, {}, ["id"], use_row_alias=False)
        .query
    )
    assert "id = new_row.id" in new_q
    assert "id = VALUES(id)" in old_q


def test_version_gate_boundaries():
    """The 8.0.19 floor and the MariaDB exclusion are pinned."""
    assert mysql_supports_row_alias_upsert("8.0.46") is True
    assert mysql_supports_row_alias_upsert("8.0.19") is True
    assert mysql_supports_row_alias_upsert("8.0.18") is False
    assert mysql_supports_row_alias_upsert("5.7.44") is False
    # MariaDB never supports the row-alias form, at any version.
    assert mysql_supports_row_alias_upsert("10.11.2-MariaDB") is False
    assert mysql_supports_row_alias_upsert("5.5.5-10.11.2-MariaDB") is False
    # Unparseable → fail closed (legacy VALUES() form).
    assert mysql_supports_row_alias_upsert("") is False
    assert parse_mysql_server_version("5.5.5-10.11.2-MariaDB") == ((5, 5, 5), True)
    assert parse_mysql_server_version("8.0.46") == ((8, 0, 46), False)
