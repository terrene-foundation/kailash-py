# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W15 Tier-2 — audit emission through the ``km.track()`` facade.

Every mutation primitive on :class:`ExperimentRun` MUST append a single
row to ``experiment_audit`` with the correct ``(tenant_id, actor_id,
resource_kind, action)`` per spec §8.2. These tests drive the real
SQLite backend through the facade and assert the audit row lands.

The test matches the wiring-test convention per
``rules/facade-manager-detection.md`` §2: the facade is
``km.track(...)``, the externally observable effect is an audit row
visible via :meth:`SqliteTrackerStore.list_audit_rows`.
"""
from __future__ import annotations

import pytest
from kailash_ml.tracking import SINGLE_TENANT_SENTINEL, SqliteTrackerStore


@pytest.mark.asyncio
async def test_run_start_and_end_emit_audit_rows():
    import kailash_ml as km

    store = SqliteTrackerStore(":memory:")
    try:
        async with km.track(
            "exp-audit-runlife",
            backend=store,
            tenant_id="acme",
            actor_id="alice@acme.com",
        ) as run:
            run_id = run.run_id
        rows = await store.list_audit_rows(tenant_id="acme")
    finally:
        await store.close()

    actions = [r["action"] for r in rows]
    assert "run.start" in actions
    assert "run.end" in actions
    # Tenant + actor MUST be persisted on every row.
    for r in rows:
        assert r["tenant_id"] == "acme"
        assert r["actor_id"] == "alice@acme.com"
    # run.end's resource_id references the finished run.
    run_end = [r for r in rows if r["action"] == "run.end"][0]
    assert run_end["resource_id"] == run_id


@pytest.mark.asyncio
async def test_log_param_emits_one_audit_row():
    import kailash_ml as km

    store = SqliteTrackerStore(":memory:")
    try:
        async with km.track(
            "exp-audit-param",
            backend=store,
            tenant_id="acme",
            actor_id="alice@acme.com",
        ) as run:
            await run.log_param("lr", 0.01)
        rows = await store.list_audit_rows(tenant_id="acme", resource_kind="param")
    finally:
        await store.close()

    assert len(rows) == 1
    assert rows[0]["action"] == "log_param"
    assert rows[0]["actor_id"] == "alice@acme.com"


@pytest.mark.asyncio
async def test_log_metric_emits_one_audit_row():
    import kailash_ml as km

    store = SqliteTrackerStore(":memory:")
    try:
        async with km.track(
            "exp-audit-metric",
            backend=store,
            tenant_id="acme",
            actor_id="bob@acme.com",
        ) as run:
            await run.log_metric("loss", 0.42, step=1)
        rows = await store.list_audit_rows(tenant_id="acme", resource_kind="metric")
    finally:
        await store.close()

    assert len(rows) == 1
    assert rows[0]["action"] == "log_metric"
    assert rows[0]["actor_id"] == "bob@acme.com"


@pytest.mark.asyncio
async def test_log_artifact_emits_audit_and_registers_subjects():
    import kailash_ml as km

    store = SqliteTrackerStore(":memory:")
    try:
        async with km.track(
            "exp-audit-artifact",
            backend=store,
            tenant_id="acme",
            actor_id="alice@acme.com",
        ) as run:
            await run.log_artifact(
                b"payload-bytes",
                name="preds.csv",
                data_subject_ids=["subj-1", "subj-2"],
            )
            run_id = run.run_id
        artifact_rows = await store.list_audit_rows(
            tenant_id="acme", resource_kind="artifact"
        )
        subjs = await store.list_subject_runs(tenant_id="acme", subject_id="subj-1")
    finally:
        await store.close()

    assert len(artifact_rows) == 1
    assert artifact_rows[0]["action"] == "log_artifact"
    # Subject registration wired — GDPR erase_subject will find the run.
    assert run_id in subjs


@pytest.mark.asyncio
async def test_add_tag_emits_audit_row():
    import kailash_ml as km

    store = SqliteTrackerStore(":memory:")
    try:
        async with km.track(
            "exp-audit-tag",
            backend=store,
            tenant_id="acme",
            actor_id="alice@acme.com",
        ) as run:
            await run.add_tag("environment", "prod")
        rows = await store.list_audit_rows(tenant_id="acme", resource_kind="tag")
    finally:
        await store.close()

    assert len(rows) == 1
    assert rows[0]["action"] == "add_tag"


@pytest.mark.asyncio
async def test_single_tenant_sentinel_populates_audit_tenant_column():
    """When the caller never supplies a tenant, audit rows MUST carry
    the ``_single`` sentinel — NEVER ``None``, NEVER ``"default"``."""
    import kailash_ml as km

    store = SqliteTrackerStore(":memory:")
    try:
        async with km.track("exp-single", backend=store) as run:
            await run.log_param("lr", 0.01)
        rows = await store.list_audit_rows(tenant_id=SINGLE_TENANT_SENTINEL)
    finally:
        await store.close()

    assert len(rows) >= 1
    # Every audit row for this session carries the sentinel.
    for r in rows:
        assert r["tenant_id"] == SINGLE_TENANT_SENTINEL
