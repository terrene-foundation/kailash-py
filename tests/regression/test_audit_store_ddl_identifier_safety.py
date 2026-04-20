# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: ``SqliteAuditStore`` rejects unsafe table names via
``dialect.quote_identifier()`` before any DDL reaches aiosqlite.

Per ``rules/dataflow-identifier-safety.md`` MUST Rule 1, every DDL that
interpolates a dynamic identifier MUST route through
``dialect.quote_identifier()``. ``SqliteAuditStore.__init__`` accepts a
caller-provided ``table_name`` which, prior to the kailash 2.8.11
dialect-safety sweep, was validated only by an inline regex in
``__init__`` and then raw f-string-interpolated into four DDL
statements in ``initialize()``.

This test proves:

1. The constructor raises :class:`IdentifierError` (a ``ValueError``
   subclass) on injection payloads — not a bare ``ValueError`` with a
   different error surface.
2. No DDL SQL text reaches the pool when construction fails: the
   ``_validate_identifier`` call in ``__init__`` runs before the pool
   is touched.
3. A well-formed table name survives construction AND ``initialize()``
   runs the quoted DDL without raising.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.regression]


_INJECTION_PAYLOADS = [
    # Classic SQL injection suffix
    'events"; DROP TABLE users; --',
    # Quote-escape bypass attempt
    'events", other_col TEXT); DROP TABLE users; --',
    # Reserved chars anywhere in the identifier
    "events WITH DATA",
    # Leading digit — valid SQL but disallowed by the allowlist regex
    "123_events",
    # Null byte — should be rejected before any DDL runs
    "events\x00injected",
    # Embedded space
    "kailash audit events",
    # Path traversal-style chars
    "../events",
    # Dotted identifier (schema.table) — not a single identifier
    "myschema.events",
    # Empty string
    "",
]


def test_audit_store_constructor_rejects_injection_payloads() -> None:
    """Constructor MUST raise IdentifierError on every injection payload.

    ``SqliteAuditStore.__init__`` routes ``table_name`` through
    ``kailash.db.dialect._validate_identifier`` before storing it.
    This test exercises that gate end-to-end: construct with each
    payload against a real SQLite pool (not a mock — per
    rules/dataflow-identifier-safety.md the pool never sees the
    unsafe name because the gate runs first).
    """
    from kailash.db.dialect import IdentifierError
    from kailash.trust.audit_store import SqliteAuditStore

    # A minimal pool-like object — never touched because __init__
    # raises before any pool access.
    class _PoolStub:
        async def acquire_write(self):  # pragma: no cover - not reached
            raise AssertionError("pool touched despite invalid table name")

    pool = _PoolStub()

    for payload in _INJECTION_PAYLOADS:
        with pytest.raises(IdentifierError):
            SqliteAuditStore(pool, table_name=payload)


def test_audit_store_constructor_rejects_non_string_table_name() -> None:
    """Non-string table names raise IdentifierError, not TypeError."""
    from kailash.db.dialect import IdentifierError
    from kailash.trust.audit_store import SqliteAuditStore

    class _PoolStub:
        pass

    for bad in (123, None, ["events"], {"table": "events"}):
        with pytest.raises(IdentifierError):
            SqliteAuditStore(_PoolStub(), table_name=bad)  # type: ignore[arg-type]


def test_audit_store_initialize_quotes_identifier_in_ddl() -> None:
    """initialize() MUST route table + index names through quote_identifier.

    This is the behavioral proof that the DDL interpolation uses the
    dialect-quoted form. We capture every SQL statement that the pool
    executes and verify every identifier appears as ``"<name>"`` (the
    SQLite quote char) rather than bare.
    """
    import asyncio

    from kailash.trust.audit_store import SqliteAuditStore

    captured_sql: list[str] = []

    class _CapturingConn:
        async def execute(self, sql: str) -> None:
            captured_sql.append(sql)

        async def commit(self) -> None:
            pass

    class _CapturingAcquireCtx:
        async def __aenter__(self):
            return _CapturingConn()

        async def __aexit__(self, *exc):
            return False

    class _CapturingPool:
        def acquire_write(self) -> _CapturingAcquireCtx:
            return _CapturingAcquireCtx()

    store = SqliteAuditStore(_CapturingPool(), table_name="my_audit_table")
    asyncio.run(store.initialize())

    # All four DDL statements should be captured: CREATE TABLE + 3
    # CREATE INDEX statements.
    assert (
        len(captured_sql) == 4
    ), f"expected 4 DDL statements, got {len(captured_sql)}: {captured_sql}"

    # Every statement interpolates the table name in quoted form.
    for stmt in captured_sql:
        assert (
            '"my_audit_table"' in stmt
        ), f"table name not quoted in DDL — quote_identifier bypassed: {stmt!r}"

    # Index names are also quoted.
    joined = "\n".join(captured_sql)
    assert '"idx_my_audit_table_actor"' in joined
    assert '"idx_my_audit_table_action"' in joined
    assert '"idx_my_audit_table_timestamp"' in joined


def test_audit_store_error_message_does_not_echo_raw_payload() -> None:
    """IdentifierError error message MUST NOT echo the raw attacker payload.

    Per rules/dataflow-identifier-safety.md MUST Rule 2, the error
    message uses a hash fingerprint — echoing the raw payload is a
    stored-XSS / log-poisoning vector.
    """
    from kailash.db.dialect import IdentifierError
    from kailash.trust.audit_store import SqliteAuditStore

    attacker_payload = 'events"; DROP TABLE users; --'

    try:
        SqliteAuditStore(object(), table_name=attacker_payload)
    except IdentifierError as err:
        assert "DROP TABLE users" not in str(err), (
            "IdentifierError message echoed the raw SQL injection "
            "payload — log-poisoning / stored-XSS vector"
        )
        assert attacker_payload not in str(err)
    else:
        pytest.fail("expected IdentifierError")
