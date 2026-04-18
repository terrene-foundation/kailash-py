# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 SQLi regression — BulkUpsertNode parameter binding (issue #492).

Before this fix, ``BulkUpsertNode._build_upsert_query`` interpolated
VALUES via ``value.replace("'", "''")`` and emitted a finished SQL
string. Hand-rolled escapes are the classic SQLi vector: backslash-
quote (``\\'``), null bytes (``\\x00``), Unicode quote homoglyphs
(``ʼ ‘ ’ ＇``), and multi-byte sequences can break out of the quoted
literal and inject DDL/DML.

The fix routes every VALUES position through driver parameter binding:
``$N`` for PostgreSQL, ``%s`` for MySQL, ``?`` for SQLite. The query
returned by ``_build_upsert_query`` carries placeholders only; values
land in a separate flat list bound by the driver.

These tests use the real PostgreSQL test infrastructure
(``IntegrationTestSuite`` per ``tests/CLAUDE.md``) and exercise the
classic SQLi payload set against the ``BulkUpsertNode`` public
``async_run`` surface. The contract: malicious payloads MUST land in
the row as literal data; the side table that the payload tries to drop
MUST remain intact.

Cross-SDK reference: kailash-rs has a parallel ``bulk_upsert.rs`` at
``crates/kailash-dataflow/src/nodes/bulk_upsert.rs``; cross-SDK issue
filed per ``rules/cross-sdk-inspection.md`` MUST 1.

References:
  - rules/security.md § Parameterized Queries
  - rules/infrastructure-sql.md § VALUES path
  - GH issue #492
"""

from __future__ import annotations

import time

import pytest
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

from dataflow.nodes.bulk_upsert import BulkUpsertNode
from tests.infrastructure.test_harness import IntegrationTestSuite

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# Canonical SQLi payload set. Each one historically broke through
# ``value.replace("'", "''")`` on at least one driver.
SQL_INJECTION_PAYLOADS = [
    "'; DROP TABLE test_canary_492; --",
    "\\'; DROP TABLE test_canary_492; --",
    "admin' OR '1'='1",
    "1; DELETE FROM test_canary_492 WHERE 1=1; --",
    # Unicode homoglyphs — visually identical to ' but distinct codepoints
    "alice\u2018name",  # LEFT SINGLE QUOTATION MARK
    "alice\u2019name",  # RIGHT SINGLE QUOTATION MARK
    "alice\uff07name",  # FULLWIDTH APOSTROPHE
    # Backslash sequences — break standard_conforming_strings off paths
    "alice\\nname",
    "alice\\\\name",
]


@pytest.fixture
async def test_suite():
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
async def upsert_table(test_suite):
    """Real PostgreSQL upsert target + a 'canary' side table the payload
    will try to drop. The fix is verified by asserting the canary still
    exists after every malicious upsert.
    """
    connection_string = test_suite.config.url
    suffix = int(time.time() * 1000)
    upsert_name = f"test_bulk_upsert_sqli_{suffix}"
    canary_name = "test_canary_492"  # name MUST match the payload literal

    setup = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        validate_queries=False,
    )
    # Drop both tables fresh
    for sql in [
        f"DROP TABLE IF EXISTS {upsert_name} CASCADE",
        f"DROP TABLE IF EXISTS {canary_name} CASCADE",
        (
            f"CREATE TABLE {upsert_name} ("
            "  id SERIAL PRIMARY KEY,"
            "  email VARCHAR(255) UNIQUE NOT NULL,"
            "  name VARCHAR(500) NOT NULL,"
            "  notes TEXT,"
            "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")"
        ),
        (
            f"CREATE TABLE {canary_name} ("
            "  id SERIAL PRIMARY KEY,"
            "  marker TEXT NOT NULL DEFAULT 'CANARY_PRESENT'"
            ")"
        ),
        f"INSERT INTO {canary_name} (marker) VALUES ('CANARY_PRESENT')",
    ]:
        await AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query=sql,
            validate_queries=False,
        ).async_run()

    await setup.cleanup()

    yield connection_string, upsert_name, canary_name

    # Teardown
    for sql in [
        f"DROP TABLE IF EXISTS {upsert_name} CASCADE",
        f"DROP TABLE IF EXISTS {canary_name} CASCADE",
    ]:
        cleanup = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query=sql,
            validate_queries=False,
        )
        await cleanup.async_run()
        await cleanup.cleanup()


async def _assert_canary_intact(connection_string: str, canary_name: str) -> None:
    """The canary table MUST still exist with the row that was seeded."""
    probe = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query=f"SELECT marker FROM {canary_name}",
        validate_queries=False,
    )
    result = await probe.async_run()
    await probe.cleanup()
    rows = result["result"]["data"]
    assert rows, f"canary table {canary_name} was dropped — SQLi succeeded"
    assert rows[0]["marker"] == "CANARY_PRESENT"


# ---------------------------------------------------------------------------
# SQLi regression coverage
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
async def test_bulk_upsert_rejects_sql_injection_in_string_field(upsert_table, payload):
    """Issue #492: every classic SQLi payload MUST be bound as data, not SQL."""
    connection_string, upsert_name, canary_name = upsert_table

    node = BulkUpsertNode(
        node_id="bulk_upsert_sqli",
        table_name=upsert_name,
        database_type="postgresql",
        connection_string=connection_string,
        conflict_columns=["email"],
    )
    result = await node.async_run(
        data=[
            {
                "email": f"victim+{abs(hash(payload))}@example.com",
                "name": payload,
                "notes": "first row",
            }
        ],
        conflict_on=["email"],
    )

    # The upsert MUST have succeeded — payload was bound as data.
    assert result["success"], result

    # The canary MUST still be intact — the payload did not become SQL.
    await _assert_canary_intact(connection_string, canary_name)

    # The malicious string MUST be retrievable verbatim from the row.
    probe = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query=f"SELECT name FROM {upsert_name} WHERE notes = 'first row'",
        validate_queries=False,
    )
    rows = (await probe.async_run())["result"]["data"]
    await probe.cleanup()
    assert len(rows) == 1
    assert (
        rows[0]["name"] == payload
    ), "Payload was mutated by the writer — escape logic is corrupting data."


@pytest.mark.regression
async def test_bulk_upsert_mixed_safe_and_malicious_batch(upsert_table):
    """Multi-row batch: safe rows MUST land normally, malicious rows MUST be data."""
    connection_string, upsert_name, canary_name = upsert_table

    node = BulkUpsertNode(
        node_id="bulk_upsert_sqli_batch",
        table_name=upsert_name,
        database_type="postgresql",
        connection_string=connection_string,
        conflict_columns=["email"],
    )
    rows = [
        {"email": "safe1@example.com", "name": "Alice", "notes": "safe"},
        {
            "email": "evil@example.com",
            "name": "'; DROP TABLE test_canary_492; --",
            "notes": "malicious",
        },
        {"email": "safe2@example.com", "name": "Bob", "notes": "safe"},
    ]
    result = await node.async_run(data=rows, conflict_on=["email"])
    assert result["success"], result

    await _assert_canary_intact(connection_string, canary_name)

    probe = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query=f"SELECT email, name FROM {upsert_name} ORDER BY email",
        validate_queries=False,
    )
    landed = (await probe.async_run())["result"]["data"]
    await probe.cleanup()
    assert len(landed) == 3
    by_email = {r["email"]: r["name"] for r in landed}
    assert by_email["safe1@example.com"] == "Alice"
    assert by_email["safe2@example.com"] == "Bob"
    assert by_email["evil@example.com"] == "'; DROP TABLE test_canary_492; --"


@pytest.mark.regression
async def test_bulk_upsert_emits_no_inlined_payload_in_query(upsert_table):
    """The query string MUST contain placeholders only — no inlined values.

    Direct exercise of the contract from ``rules/security.md`` § Parameterized
    Queries: VALUES are parameters, never substrings.
    """
    connection_string, upsert_name, _canary_name = upsert_table

    node = BulkUpsertNode(
        node_id="bulk_upsert_placeholder",
        table_name=upsert_name,
        database_type="postgresql",
        connection_string=connection_string,
        conflict_columns=["email"],
    )

    payload = "'; DROP TABLE test_canary_492; --"
    sql, params = node._build_upsert_query(
        batch=[{"email": "victim@example.com", "name": payload, "notes": "x"}],
        columns=["email", "name", "notes"],
        column_names="email, name, notes",
        return_records=False,
        merge_strategy="update",
        conflict_on=["email"],
    )
    # Placeholders only
    assert "$1" in sql and "$2" in sql and "$3" in sql
    # Payload MUST NOT appear in the SQL — only in params
    assert payload not in sql
    assert "DROP TABLE" not in sql
    assert payload in params


@pytest.mark.regression
@pytest.mark.parametrize(
    "bad_identifier",
    [
        'users"; DROP TABLE customers; --',
        "name with spaces",
        "123_starts_with_digit",
        "name'; DROP",
    ],
)
async def test_bulk_upsert_rejects_invalid_table_identifier(bad_identifier):
    """Issue #492 + dataflow-identifier-safety.md MUST 1: dynamic identifiers
    used by ``_build_upsert_query`` MUST be validated. A table_name that
    contains shell/SQL meta-characters MUST raise at query-build time, not
    silently land in DDL.
    """
    node = BulkUpsertNode(
        node_id="bulk_upsert_id",
        table_name=bad_identifier,
        database_type="postgresql",
        connection_string="postgresql://localhost/x",
        conflict_columns=["email"],
    )
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        node._build_upsert_query(
            batch=[{"email": "x@example.com"}],
            columns=["email"],
            column_names="email",
            return_records=False,
            merge_strategy="update",
            conflict_on=["email"],
        )


@pytest.mark.regression
async def test_bulk_upsert_rejects_invalid_column_identifier():
    """Identifier safety MUST extend to column names supplied via the
    runtime ``conflict_on`` parameter and the ``columns`` list.
    """
    node = BulkUpsertNode(
        node_id="bulk_upsert_col",
        table_name="users",
        database_type="postgresql",
        connection_string="postgresql://localhost/x",
        conflict_columns=["email"],
    )
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        node._build_upsert_query(
            batch=[{"email": "x@example.com"}],
            columns=["email"],
            column_names="email",
            return_records=False,
            merge_strategy="update",
            conflict_on=['email"; DROP TABLE customers; --'],
        )


@pytest.mark.regression
async def test_bulk_upsert_rejects_unsupported_dialect():
    """Typos / unknown dialect strings MUST raise loudly rather than fall
    through to SQLite REPLACE semantics. See `rules/dataflow-identifier-safety.md`.
    """
    from kailash.sdk_exceptions import NodeValidationError

    node = BulkUpsertNode(
        node_id="bulk_upsert_dialect",
        table_name="users",
        database_type="postgres",  # typo — should be 'postgresql'
        connection_string="postgresql://localhost/x",
        conflict_columns=["email"],
    )
    with pytest.raises(NodeValidationError, match="Unsupported database_type"):
        node._build_upsert_query(
            batch=[{"email": "x@example.com"}],
            columns=["email"],
            column_names="email",
            return_records=False,
            merge_strategy="update",
            conflict_on=["email"],
        )


@pytest.mark.regression
async def test_bulk_upsert_no_quote_escape_in_source():
    """Belt-and-suspenders source check: hand-rolled string-escape MUST be gone.

    Mechanical guard against a future refactor reintroducing the
    ``value.replace("'", "''")`` pattern that issue #492 closed. This is a
    pinning test, not a behavioural one — see ``rules/testing.md`` § Behavioral
    Regression Tests Over Source-Grep for why we keep BOTH styles for SQLi
    boundaries: behavioural tests above prove the runtime contract, this pin
    catches the dangerous string at the AST level before tests even run.
    """
    from pathlib import Path

    src = Path(
        "packages/kailash-dataflow/src/dataflow/nodes/bulk_upsert.py"
    ).read_text()
    assert (
        'value.replace("\'", "\'\'")' not in src
    ), "Hand-rolled SQL escape returned to bulk_upsert.py — see issue #492."
    assert (
        '.replace("\'", "\'\'")' not in src
    ), "Hand-rolled SQL escape returned to bulk_upsert.py — see issue #492."
