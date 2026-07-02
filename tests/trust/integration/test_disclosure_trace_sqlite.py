# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 integration: disclosure tracing bound to a persistent SQLite audit store.

Exercises DisclosureTracer against a real ``SqliteAuditStore`` (real
infrastructure, no mocking) to prove:

- The ``disclosure`` audit event persists and its Merkle chain stays intact.
- The trace token is bound to the persisted audit record (survives read-back).
- Reverse lookup (token -> recipient) resolves through the keyed store.
- Deterministic re-recording is idempotent in the reverse store.
"""

from __future__ import annotations

import pytest

pytest.importorskip(
    "aiosqlite",
    reason="aiosqlite required for AsyncSQLitePool-backed disclosure tests; "
    "install via kailash[db-sqlite] extra",
)

from kailash.core.pool.sqlite_pool import (  # noqa: E402
    AsyncSQLitePool,
    SQLitePoolConfig,
)
from kailash.trust.audit_store import (  # noqa: E402
    AuditEventType,
    AuditFilter,
    SqliteAuditStore,
)
from kailash.trust.disclosure import DisclosureTracer  # noqa: E402
from kailash.trust.signing import derive_trace_token  # noqa: E402

_KEY = b"server-held-32-byte-secret-key!!"
_COUNTER = 0


def _unique_memory_uri() -> str:
    global _COUNTER
    _COUNTER += 1
    return f"file:disclosure_test_{_COUNTER}?mode=memory&cache=shared"


@pytest.fixture
async def audit_store():
    uri = _unique_memory_uri()
    config = SQLitePoolConfig(db_path=uri, uri=True, max_read_connections=2)
    pool = AsyncSQLitePool(config)
    await pool.initialize()
    store = SqliteAuditStore(pool)
    await store.initialize()
    yield store
    await pool.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_disclosure_persists_and_binds_token(audit_store):
    tracer = DisclosureTracer(_KEY, audit_store)
    event, token = await tracer.record_disclosure(
        recipient="user-42",
        resource="report-2026-q2",
        session="sess-abc",
        actor="delivery-agent",
    )
    assert event.metadata["trace_token"] == token
    assert event.action == AuditEventType.DISCLOSURE.value

    # Read back from SQLite: the persisted event carries the bound token and
    # its hash verifies (token is part of the Merkle-chained metadata).
    rows = await audit_store.query(
        AuditFilter(action=AuditEventType.DISCLOSURE.value, limit=10)
    )
    assert len(rows) == 1
    persisted = rows[0]
    assert persisted.metadata["trace_token"] == token
    assert persisted.verify_integrity() is True
    assert persisted.resource == "report-2026-q2"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reverse_lookup_after_persist(audit_store):
    tracer = DisclosureTracer(_KEY, audit_store)
    _, token = await tracer.record_disclosure(
        recipient="user-42", resource="r", session="s"
    )
    assert (await tracer.lookup_recipient(token)) == "user-42"
    # Token is exactly the keyed HMAC derivation (deterministic).
    assert token == derive_trace_token(_KEY, "user-42", "r", "s")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_disclosures_chain_intact(audit_store):
    tracer = DisclosureTracer(_KEY, audit_store)
    tokens = []
    for i in range(4):
        _, tok = await tracer.record_disclosure(
            recipient=f"user-{i}", resource="r", session="s"
        )
        tokens.append(tok)
    assert await audit_store.verify_chain() is True
    assert len(set(tokens)) == 4
    for i, tok in enumerate(tokens):
        assert (await tracer.lookup_recipient(tok)) == f"user-{i}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_deterministic_rerecord_idempotent_reverse_store(audit_store):
    tracer = DisclosureTracer(_KEY, audit_store)
    _, tok1 = await tracer.record_disclosure(
        recipient="user-42", resource="r", session="s"
    )
    _, tok2 = await tracer.record_disclosure(
        recipient="user-42", resource="r", session="s"
    )
    assert tok1 == tok2
    assert (await tracer.lookup_recipient(tok1)) == "user-42"
