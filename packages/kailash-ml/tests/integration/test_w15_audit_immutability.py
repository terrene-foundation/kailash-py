# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W15 Tier-2 — audit immutability (spec §8.4).

The ``experiment_audit`` table MUST reject UPDATE and DELETE via
dialect-level triggers. The constraint is a structural defense: an
application-level guard is bypassable by anyone with direct
backend access; the trigger is not.

SQLite path covered here; the PostgreSQL equivalent is covered by the
parity test in ``tests/integration/test_tracker_store_parity.py`` when
``POSTGRES_TEST_URL`` is set.
"""
from __future__ import annotations

import aiosqlite
import pytest
from kailash_ml.tracking import SqliteTrackerStore


@pytest.mark.asyncio
async def test_audit_update_is_rejected(tmp_path):
    db_path = tmp_path / "audit-immutable.db"
    store = SqliteTrackerStore(str(db_path))
    try:
        await store.insert_audit_row(
            tenant_id="acme",
            actor_id="alice@acme.com",
            timestamp="2026-04-22T00:00:00+00:00",
            resource_kind="run",
            resource_id="run-1",
            action="run.start",
            prev_state=None,
            new_state=None,
        )
    finally:
        await store.close()

    # Open a bare aiosqlite connection — bypasses the pool but still
    # hits the on-disk schema where the trigger lives.
    conn = await aiosqlite.connect(str(db_path))
    try:
        with pytest.raises(aiosqlite.IntegrityError) as ei:
            await conn.execute(
                "UPDATE experiment_audit SET action = 'tamper' WHERE resource_id = ?",
                ("run-1",),
            )
            await conn.commit()
    finally:
        await conn.close()
    assert "append-only" in str(ei.value).lower()


@pytest.mark.asyncio
async def test_audit_delete_is_rejected(tmp_path):
    db_path = tmp_path / "audit-immutable2.db"
    store = SqliteTrackerStore(str(db_path))
    try:
        await store.insert_audit_row(
            tenant_id="acme",
            actor_id="alice@acme.com",
            timestamp="2026-04-22T00:00:00+00:00",
            resource_kind="run",
            resource_id="run-2",
            action="run.start",
        )
    finally:
        await store.close()

    conn = await aiosqlite.connect(str(db_path))
    try:
        with pytest.raises(aiosqlite.IntegrityError) as ei:
            await conn.execute(
                "DELETE FROM experiment_audit WHERE resource_id = ?", ("run-2",)
            )
            await conn.commit()
    finally:
        await conn.close()
    assert "append-only" in str(ei.value).lower()
