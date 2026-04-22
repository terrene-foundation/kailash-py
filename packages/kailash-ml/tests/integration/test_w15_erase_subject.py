# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W15 Tier-2 — GDPR ``km.erase_subject`` round-trip.

The erasure path MUST:

1. Delete every ``metrics/artifacts/tags/model_versions/subjects`` row
   for the subject's runs.
2. Null-out ``experiment_runs.params`` for those runs (the shell stays
   so audit cross-refs resolve).
3. PRESERVE every prior audit row unchanged — triggers installed at
   ``initialize()`` enforce append-only.
4. APPEND a new audit row with ``action='erase'``,
   ``resource_id='sha256:<8hex>'``, and per-resource counters in
   ``new_state``.

These tests drive the real SQLite backend through
``km.track(...)`` + ``km.erase_subject(...)`` and assert each of the
four above via :meth:`SqliteTrackerStore.list_audit_rows` and direct
reads on the deleted tables.
"""
from __future__ import annotations

import json

import pytest
from kailash_ml.errors import (
    ErasureRefusedError,
    MultiTenantOpError,
    TenantRequiredError,
    fingerprint_classified_value,
)
from kailash_ml.tracking import SqliteTrackerStore


@pytest.mark.asyncio
async def test_erase_subject_clears_content_and_preserves_audit():
    import kailash_ml as km

    store = SqliteTrackerStore(":memory:")
    try:
        # Populate: one run, one artifact linked to subject-alice, one
        # metric, one param, one tag.
        async with km.track(
            "exp-erase",
            backend=store,
            tenant_id="acme",
            actor_id="operator@acme.com",
        ) as run:
            await run.log_param("lr", 0.01)
            await run.log_metric("loss", 0.42, step=1)
            await run.log_artifact(
                b"csv-bytes",
                name="preds.csv",
                data_subject_ids=["subj-alice"],
            )
            await run.add_tag("environment", "prod")
            run_id = run.run_id

        # Capture pre-erasure audit row count so we can assert
        # preservation after erasure.
        audit_before = await store.list_audit_rows(tenant_id="acme")
        assert len(audit_before) >= 5  # run.start/end + param + metric + artifact + tag

        # Fire the erasure.
        result = await km.erase_subject(
            "subj-alice",
            tenant_id="acme",
            actor_id="operator@acme.com",
            backend=store,
        )

        # Content is gone.
        metrics = await store.list_metrics(run_id)
        artifacts = await store.list_artifacts(run_id)
        tags = await store.list_tags(run_id)
        run_row = await store.get_run(run_id)
        subjects = await store.list_subject_runs(
            tenant_id="acme", subject_id="subj-alice"
        )

        assert metrics == []
        assert artifacts == []
        assert tags == {}
        # Run shell persists for audit cross-reference but params are nulled.
        assert run_row is not None
        assert run_row["params"] == {}
        assert subjects == []

        # Audit rows preserved AND the new erase row appended.
        audit_after = await store.list_audit_rows(tenant_id="acme")
        assert len(audit_after) == len(audit_before) + 1
        erase_rows = [r for r in audit_after if r["action"] == "erase"]
        assert len(erase_rows) == 1
        erase_row = erase_rows[0]
        assert erase_row["resource_kind"] == "data_subject"
        # Fingerprint is the 8-hex SHA-256 form per
        # rules/event-payload-classification.md §2.
        assert erase_row["resource_id"] == fingerprint_classified_value("subj-alice")
        assert erase_row["resource_id"].startswith("sha256:")
        assert len(erase_row["resource_id"]) == len("sha256:") + 8
        # Raw subject id MUST NOT appear anywhere in the audit row.
        assert "subj-alice" not in json.dumps(erase_row)
        # Counters serialised in new_state.
        counters = json.loads(erase_row["new_state"])
        assert counters["runs"] == 1
        assert counters["artifacts"] == 1
        assert counters["metrics"] == 1
        assert counters["tags"] == 1

        # Return shape mirrors counters + metadata.
        assert result["runs"] == 1
        assert result["subject_fingerprint"] == erase_row["resource_id"]
        assert result["audit_preserved"] is True
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_erase_subject_refuses_without_tenant_in_strict_mode(
    monkeypatch,
):
    import kailash_ml as km

    monkeypatch.delenv("KAILASH_TENANT_ID", raising=False)
    store = SqliteTrackerStore(":memory:")
    try:
        with pytest.raises(TenantRequiredError):
            await km.erase_subject(
                "subj-alice",
                backend=store,
                multi_tenant=True,
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_erase_subject_requires_non_empty_subject_id():
    import kailash_ml as km

    store = SqliteTrackerStore(":memory:")
    try:
        with pytest.raises(MultiTenantOpError):
            await km.erase_subject("", tenant_id="acme", backend=store)
        with pytest.raises(MultiTenantOpError):
            await km.erase_subject("   ", tenant_id="acme", backend=store)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_erase_subject_refuses_when_production_alias_exists():
    """The spec §8.4/§9.1 hook — ``ErasureRefusedError`` fires when a
    backend exposes ``has_production_alias_for_subject`` and returns
    True. The production hook ships in W18; this test uses a test-
    double to prove the refusal path activates once the hook lands.
    """
    import kailash_ml as km

    store = SqliteTrackerStore(":memory:")

    async def _always_refuses(*, tenant_id, subject_id):
        return True

    # Attach the hook dynamically — mirrors the production W18 surface
    # without requiring the registry to ship in this shard.
    store.has_production_alias_for_subject = _always_refuses  # type: ignore[attr-defined]
    try:
        with pytest.raises(ErasureRefusedError):
            await km.erase_subject(
                "subj-alice",
                tenant_id="acme",
                actor_id="operator@acme.com",
                backend=store,
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_erase_subject_with_unknown_subject_is_noop():
    import kailash_ml as km

    store = SqliteTrackerStore(":memory:")
    try:
        result = await km.erase_subject(
            "never-existed",
            tenant_id="acme",
            actor_id="operator@acme.com",
            backend=store,
        )
        assert result["runs"] == 0
        # Even a no-op appends an audit row so forensics can see the
        # attempted erasure.
        audit = await store.list_audit_rows(
            tenant_id="acme", resource_kind="data_subject"
        )
        assert len(audit) == 1
        assert audit[0]["action"] == "erase"
    finally:
        await store.close()
