# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1538 — PostgreSQL ``db.express.list`` returns a
STALE row after an upsert that took the UPDATE branch, even with ``cache_ttl=0``.

Root cause (confirmed by live PG:5434 reproduction, not hypothesis):

DataFlow has TWO independent cache layers on the Express read path:

1. the **Express cache** (``DataFlowExpress._cache_manager``), which
   ``cache_ttl=0`` correctly bypasses (``_cache_get`` returns ``None`` when
   ``effective_ttl <= 0``); and
2. the **node query cache** (``DataFlow._cache_integration``), consulted by the
   generated ``{Model}ListNode`` with ``enable_cache=True`` by default — a
   DIFFERENT backend that ``cache_ttl=0`` on the Express layer does NOT touch.

A prior ``db.express.list(...)`` primes layer (2). The single-record
``UpsertNode`` (``dataflow/core/nodes.py`` ``operation == "upsert"``) then failed
to invalidate layer (2) after a successful upsert — every sibling write branch
(create / update / delete / bulk_*) called
``cache_integration.invalidate_model_cache(...)`` but the single upsert branch
did not. Compounding it, ``ListNodeCacheIntegration._setup_invalidation_patterns``
registered no ``upsert`` / ``bulk_upsert`` pattern, so even the calls that DID
exist (bulk_upsert) matched zero patterns in ``CacheInvalidator.invalidate`` and
silently no-op'd. Net effect: the upsert-UPDATE left the primed list/count entry
in the node cache and the next ``list(cache_ttl=0)`` served the pre-update row.

A plain ``db.express.update`` did NOT exhibit the bug because ``UpdateNode``
already calls ``invalidate_model_cache(model, "update", row)`` and the ``update``
pattern was registered — hence the control case below MUST stay fresh.

The fix (two surgical, additive parts):
  * ``dataflow/core/nodes.py`` — the single upsert success path now calls
    ``cache_integration.invalidate_model_cache(self.model_name, "upsert", row)``.
  * ``dataflow/cache/list_node_integration.py`` — register ``upsert`` and
    ``bulk_upsert`` invalidation patterns (version-wildcard sweep).

Not MVCC / connection-snapshot: the raw read-back below and an
``enable_cache=False`` node read both return the fresh row from the same pool
while the cached Express read returned stale — proving the staleness lived in
the node cache, not an open transaction.

Permanent regression tests — NEVER delete (``rules/testing.md`` Regression).
"""

from __future__ import annotations

import time

import pytest

from dataflow import DataFlow


def _email(prefix: str = "alice") -> str:
    return f"{prefix}-{int(time.time() * 1_000_000)}@example.com"


@pytest.fixture
async def pg_suite():
    from tests.infrastructure.test_harness import IntegrationTestSuite

    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


async def _drop_table(url, table):
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    node = AsyncSQLDatabaseNode(
        connection_string=url,
        database_type="postgresql",
        query=f"DROP TABLE IF EXISTS {table} CASCADE",
        validate_queries=False,
    )
    await node.async_run()
    await node.cleanup()


# ---------------------------------------------------------------------------
# AC1 — the exact #1538 sequence: upsert(INSERT) → list(prime) →
#        upsert(UPDATE) → list(cache_ttl=0) MUST see the UPDATED value.
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_pg_express_list_fresh_after_upsert_update(pg_suite):
    url = pg_suite.config.url
    await _drop_table(url, "person1538_as")

    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Person1538A:
        email: str
        name: str
        __dataflow__ = {"indexes": [{"fields": ["email"], "unique": True}]}

    await db.initialize()
    email = _email()

    # 1. upsert → INSERT
    await db.express.upsert(
        "Person1538A", {"email": email, "name": "Alice New"}, conflict_on=["email"]
    )
    # 2. prime the node-level list cache
    primed = await db.express.list("Person1538A", {"email": email})
    assert [r["name"] for r in primed] == ["Alice New"]

    # 3. upsert → UPDATE branch
    await db.express.upsert(
        "Person1538A",
        {"email": email, "name": "Alice Updated"},
        conflict_on=["email"],
    )

    # 4. list with cache_ttl=0 MUST reflect the UPDATE, not the primed value.
    after = await db.express.list("Person1538A", {"email": email}, cache_ttl=0)
    assert [r["name"] for r in after] == ["Alice Updated"], (
        "Express list served a STALE row after upsert-UPDATE (issue #1538). "
        "The node-level _cache_integration was not invalidated by the upsert."
    )

    # Read-back through the harness connection (bypasses BOTH DataFlow cache
    # layers) proves the DB row itself is correct — i.e. this was a cache bug,
    # not a write/MVCC bug.
    async with pg_suite.get_connection() as conn:
        raw = await conn.fetchval(
            "SELECT name FROM person1538_as WHERE email = $1", email
        )
    assert raw == "Alice Updated"


# ---------------------------------------------------------------------------
# AC2 — control: plain express.update MUST stay fresh (it already invalidated
#        the node cache; the differentiator that made #1538 upsert-specific).
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_pg_express_list_fresh_after_plain_update_control(pg_suite):
    url = pg_suite.config.url
    await _drop_table(url, "person1538_bs")

    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Person1538B:
        email: str
        name: str
        __dataflow__ = {"indexes": [{"fields": ["email"], "unique": True}]}

    await db.initialize()
    email = _email("bob")

    await db.express.upsert(
        "Person1538B", {"email": email, "name": "Bob New"}, conflict_on=["email"]
    )
    primed = await db.express.list("Person1538B", {"email": email})
    assert [r["name"] for r in primed] == ["Bob New"]

    rec = await db.express.find_one("Person1538B", {"email": email})
    await db.express.update("Person1538B", rec["id"], {"name": "Bob Updated"})

    after = await db.express.list("Person1538B", {"email": email}, cache_ttl=0)
    assert [r["name"] for r in after] == ["Bob Updated"]

    async with pg_suite.get_connection() as conn:
        raw = await conn.fetchval(
            "SELECT name FROM person1538_bs WHERE email = $1", email
        )
    assert raw == "Bob Updated"


# ---------------------------------------------------------------------------
# AC3 — same-class fix: bulk_upsert UPDATE branch MUST also invalidate the node
#        cache (its invalidate_model_cache call previously no-op'd for lack of a
#        registered "bulk_upsert" pattern).
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_pg_express_list_fresh_after_bulk_upsert_update(pg_suite):
    url = pg_suite.config.url
    await _drop_table(url, "person1538_cs")

    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Person1538C:
        email: str
        name: str
        __dataflow__ = {"indexes": [{"fields": ["email"], "unique": True}]}

    await db.initialize()
    email = _email("carol")

    await db.express.bulk_upsert(
        "Person1538C",
        [{"email": email, "name": "Carol New"}],
        conflict_on=["email"],
    )
    primed = await db.express.list("Person1538C", {"email": email})
    assert [r["name"] for r in primed] == ["Carol New"]

    await db.express.bulk_upsert(
        "Person1538C",
        [{"email": email, "name": "Carol Updated"}],
        conflict_on=["email"],
    )

    after = await db.express.list("Person1538C", {"email": email}, cache_ttl=0)
    assert [r["name"] for r in after] == ["Carol Updated"], (
        "Express list served a STALE row after bulk_upsert-UPDATE (issue #1538 "
        "same-class): the 'bulk_upsert' invalidation pattern was not registered."
    )

    async with pg_suite.get_connection() as conn:
        raw = await conn.fetchval(
            "SELECT name FROM person1538_cs WHERE email = $1", email
        )
    assert raw == "Carol Updated"
