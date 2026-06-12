# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 wiring — ``FeatureStore.erase_tenant`` GDPR tenant erasure (FM2 Shard F).

Per ``rules/facade-manager-detection.md`` MUST Rule 1/2 + ``rules/orphan-detection.md``
MUST Rule 2, this exercises the GDPR tenant-erasure path end-to-end against a REAL
DataFlow instance (file-backed SQLite) and asserts the externally-observable
contract for the 5 Shard-F invariants:

1. **tenant-scoped delete** — ``erase_tenant("tenant_a")`` deletes ONLY tenant A's
   materialized feature-table rows; tenant B's rows survive untouched (read-back
   both: A's rows GONE, B's rows present + readable).
2. **registry consistency post-erase** — tenant A's
   :class:`~kailash_ml.features.registry.FeatureRegistry` rows are also gone
   (``registry.list(tenant_a)`` returns empty); tenant B's registry rows intact.
3. **audit trail** — the erase emits a ``feature_store.erase_tenant.ok``
   state-transition log line carrying ``action='erase'`` +
   ``resource_kind='feature_tenant'`` (observability Rule 4); the result's
   ``audit_emitted`` flag confirms it.
4. **reuse ``ErasureRefusedError``** — the alias-protection refusal path raises the
   REUSED canonical :class:`~kailash_ml.errors.ErasureRefusedError` (a
   ``TrackingError`` subclass, NOT redefined); the invalid/sentinel-tenant refusal
   raises :class:`~kailash_ml.errors.TenantRequiredError`.
5. **fail-closed on partial erase** — when a delete leg fails mid-erase the helper
   surfaces :class:`~kailash_ml.errors.FeatureStoreError` (PARTIAL ERASE flagged),
   never silently leaving half-erased state (``rules/zero-tolerance.md`` Rule 3).

Plus: **idempotent** re-erase (a second ``erase_tenant`` on an already-erased
tenant returns zero counts, not an error).

NO MOCKING of the persistence path — real DataFlow ``express.list`` /
``express.delete`` / ``materialize`` / ``register`` (``rules/testing.md`` Tier 2).
Every delete is verified with a read-back (``rules/testing.md`` State Persistence).
File-backed SQLite mirrors the precedent in ``test_feature_materialiser_wiring.py``
+ ``test_feature_registry.py``. The Invariant-5 fail-closed test monkeypatches the
DataFlow ``express.delete`` to RAISE — this is a deterministic fault-injection
adapter at the framework boundary (exercising the helper's real error path), NOT a
mock of the system-under-test.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import pytest
from kailash_ml.errors import (
    ErasureRefusedError,
    FeatureStoreError,
    TenantRequiredError,
)
from kailash_ml.features import (
    EraseTenantResult,
    FeatureField,
    FeatureGroup,
    FeatureRegistry,
    FeatureSchema,
    FeatureStore,
    feature,
)

from dataflow import DataFlow

pytestmark = pytest.mark.integration


# A @feature-authored derived column: log1p of the base amount.
@feature(name="amount_log", dtype="float64")
def amount_log() -> pl.Expr:
    return pl.col("amount").log1p()


def _schema(*, name: str = "UserFeat") -> FeatureSchema:
    return FeatureSchema(
        name=name,
        version=1,
        fields=(FeatureField(name="amount", dtype="float64"),),
        entity_id_column="entity_id",
        timestamp_column="event_time",
    )


def _group(*, name: str = "UserFeat") -> FeatureGroup:
    return FeatureGroup(_schema(name=name), features=[amount_log])


def _input_frame(amounts: list[float]) -> pl.DataFrame:
    """Two entities, one row each, with an event_time for the content-id hash."""
    return pl.DataFrame(
        {
            "entity_id": ["u1", "u2"],
            "event_time": [
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 2, tzinfo=timezone.utc),
            ],
            "amount": amounts,
        }
    )


@pytest.fixture
def store_db(tmp_path: Path):
    """A FeatureStore + FeatureRegistry over one file-backed-SQLite DataFlow."""
    db_path = tmp_path / "feat_erase.sqlite"
    df = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)
    store = FeatureStore(df)
    registry = FeatureRegistry(df)
    try:
        yield store, registry, df
    finally:
        try:
            df.close()
        except Exception:
            pass


async def _seed_two_tenants(store: FeatureStore, registry: FeatureRegistry):
    """Materialize + register the SAME feature group for tenant_a AND tenant_b.

    Both tenants persist into the SAME backing table ``UserFeat``; the rows stay
    distinct because the materialiser's content-addressed id bakes the tenant into
    the hash (``id = sha256(tenant|group|version|entity|ts)``).
    """
    group = _group()
    await store.materialize(group, _input_frame([9.0, 99.0]), tenant_id="tenant_a")
    await store.materialize(group, _input_frame([5.0, 55.0]), tenant_id="tenant_b")
    await registry.register(group, tenant_id="tenant_a")
    await registry.register(group, tenant_id="tenant_b")
    return group


# ---------------------------------------------------------------------------
# Invariants 1 + 2: tenant-scoped delete + registry consistency post-erase
# ---------------------------------------------------------------------------


async def test_erase_tenant_deletes_only_target_tenant(store_db):
    """erase_tenant(A) removes A's materialized + registry rows; B's are intact
    (invariants 1 + 2). Every delete is verified with a read-back."""
    store, registry, df = store_db
    await _seed_two_tenants(store, registry)

    # Read-back BEFORE: 4 materialized rows (2 per tenant), 1 registry row each.
    rows_before = await df.express.list("UserFeat", {}, limit=100)
    assert len(rows_before) == 4
    assert len(await registry.list(tenant_id="tenant_a")) == 1
    assert len(await registry.list(tenant_id="tenant_b")) == 1

    result = await store.erase_tenant(tenant_id="tenant_a")
    assert isinstance(result, EraseTenantResult)
    assert result["feature_rows"] == 2
    assert result["registry_rows"] == 1
    assert result["feature_groups"] == 1

    # Read-back AFTER: only tenant_b's 2 materialized rows survive.
    rows_after = await df.express.list("UserFeat", {}, limit=100)
    assert len(rows_after) == 2, "tenant_a rows not fully deleted (or B's collateral)"

    # Tenant B's rows are the SURVIVORS — their content matches B's materialise
    # (amounts 5.0 / 55.0), proving A's rows (9.0 / 99.0) were the ones deleted.
    surviving_amounts = sorted(r["amount"] for r in rows_after)
    assert surviving_amounts == pytest.approx([5.0, 55.0])

    # Invariant 2: tenant_a registry rows gone; tenant_b registry rows intact.
    assert await registry.list(tenant_id="tenant_a") == []
    b_regs = await registry.list(tenant_id="tenant_b")
    assert len(b_regs) == 1
    assert b_regs[0].schema.name == "UserFeat"


async def test_erase_tenant_leaves_sibling_readable(store_db):
    """After erasing tenant_a, tenant_b's features still read back via the store
    (invariant 1 — sibling untouched, not just row-count-intact)."""
    store, registry, df = store_db
    group = await _seed_two_tenants(store, registry)

    await store.erase_tenant(tenant_id="tenant_a")

    # Tenant B's data is still queryable through the read surface.
    df_b = await store.get_features(group.schema, tenant_id="tenant_b")
    assert set(df_b["entity_id"].to_list()) == {"u1", "u2"}


# ---------------------------------------------------------------------------
# Idempotency: a second erase on an already-erased tenant is a no-op, not error
# ---------------------------------------------------------------------------


async def test_erase_tenant_is_idempotent(store_db):
    """A second erase_tenant on an already-erased tenant returns zero counts and
    does NOT raise (idempotent)."""
    store, registry, df = store_db
    await _seed_two_tenants(store, registry)

    first = await store.erase_tenant(tenant_id="tenant_a")
    assert first["feature_rows"] == 2

    second = await store.erase_tenant(tenant_id="tenant_a")
    assert second["feature_rows"] == 0
    assert second["registry_rows"] == 0
    assert second["feature_groups"] == 0
    # tenant_b still intact after the double-erase of A.
    assert len(await df.express.list("UserFeat", {}, limit=100)) == 2


# ---------------------------------------------------------------------------
# Invariant 3: audit trail (state-transition log line emitted)
# ---------------------------------------------------------------------------


async def test_erase_tenant_emits_audit_log(store_db, caplog):
    """erase_tenant emits a feature_store.erase_tenant.ok state-transition log line
    carrying action='erase' + resource_kind='feature_tenant' (invariant 3)."""
    store, registry, df = store_db
    await _seed_two_tenants(store, registry)

    with caplog.at_level(logging.INFO, logger="kailash_ml.features.erasure"):
        result = await store.erase_tenant(tenant_id="tenant_a")

    assert result["audit_emitted"] is True
    # The audit record is the structured 'ok' log line (observability Rule 4).
    ok_records = [
        r for r in caplog.records if r.getMessage() == "feature_store.erase_tenant.ok"
    ]
    assert ok_records, "no erase_tenant.ok audit log line emitted"
    rec = ok_records[0]
    assert getattr(rec, "action", None) == "erase"
    assert getattr(rec, "resource_kind", None) == "feature_tenant"
    # tenant fingerprint present; raw feature data / PII never logged (Rule 8).
    assert getattr(rec, "tenant_fingerprint", "").startswith("sha256:")
    # HIGH-1 regression (Wave-2 redteam R1): the RAW tenant id MUST NOT appear on
    # ANY audit log line — only the fingerprint (spec §11.4 fingerprint mandate;
    # observability Rule 4/8). Sweep every erasure log record, not just .ok.
    for r in caplog.records:
        assert (
            getattr(r, "tenant_id", None) is None
        ), f"raw tenant_id leaked on log line {r.getMessage()!r}"
        assert "tenant_a" not in r.getMessage()


# ---------------------------------------------------------------------------
# Invariant 4: reuse ErasureRefusedError (refusal path typed)
# ---------------------------------------------------------------------------


async def test_erase_tenant_refusal_raises_reused_error(store_db):
    """The alias-protection refusal path raises the REUSED canonical
    ErasureRefusedError (a TrackingError subclass, NOT a redefined class)
    (invariant 4)."""
    from kailash.ml.errors import ErasureRefusedError as CanonicalErasureRefused
    from kailash.ml.errors import TrackingError

    store, registry, df = store_db
    await _seed_two_tenants(store, registry)

    # Wire the forward-compat refusal hook to refuse (mirrors tracking/erasure.py).
    async def _refuse(*, tenant_id: str) -> bool:
        return True

    df.has_production_alias_for_tenant = _refuse

    with pytest.raises(ErasureRefusedError) as excinfo:
        await store.erase_tenant(tenant_id="tenant_a")
    # Identity: the class IS the canonical one + a TrackingError (not redefined).
    assert excinfo.type is CanonicalErasureRefused
    assert isinstance(excinfo.value, TrackingError)

    # The refusal did NOT delete anything (fail-closed before any delete).
    assert len(await df.express.list("UserFeat", {}, limit=100)) == 4

    # force=True bypasses the refusal hook (operator override).
    result = await store.erase_tenant(tenant_id="tenant_a", force=True)
    assert result["feature_rows"] == 2


async def test_erase_tenant_invalid_tenant_raises(store_db):
    """An invalid / forbidden-sentinel tenant raises TenantRequiredError before any
    delete — a destructive op MUST NOT run unscoped (invariant 4 / security)."""
    store, registry, df = store_db
    await _seed_two_tenants(store, registry)

    # Forbidden sentinel — would otherwise merge tenants into one cache slot.
    with pytest.raises(TenantRequiredError):
        await store.erase_tenant(tenant_id="global")
    # No data touched.
    assert len(await df.express.list("UserFeat", {}, limit=100)) == 4

    # Missing tenant on a store with no default also raises.
    with pytest.raises(TenantRequiredError):
        await store.erase_tenant()


# ---------------------------------------------------------------------------
# Invariant 5: fail-closed on partial erase
# ---------------------------------------------------------------------------


async def test_erase_tenant_fail_closed_on_partial_delete(store_db, monkeypatch):
    """If a delete leg fails mid-erase, erase_tenant surfaces FeatureStoreError
    (PARTIAL ERASE) rather than silently leaving half-erased state (invariant 5 /
    zero-tolerance Rule 3).

    Fault injection at the framework boundary: make express.delete RAISE on the
    materialized-feature-table delete. This exercises the helper's REAL fail-closed
    path (not a mock of the system-under-test)."""
    store, registry, df = store_db
    await _seed_two_tenants(store, registry)

    real_delete = df.express.delete

    async def _boom(model: str, id):  # noqa: A002 — match express.delete signature
        if model == "UserFeat":
            raise RuntimeError("injected backing-store delete failure")
        return await real_delete(model, id)

    monkeypatch.setattr(df.express, "delete", _boom)

    with pytest.raises(FeatureStoreError) as excinfo:
        await store.erase_tenant(tenant_id="tenant_a")
    # The error names the partial-erase condition (fail-closed, not swallowed).
    assert "PARTIAL ERASE" in excinfo.value.reason
    # MED-1 regression (Wave-2 redteam R1): the raw tenant id MUST NOT appear in
    # the exception's rendered message/repr — only a fingerprint (MLError
    # _format_message echoes any tenant_id= kwarg; we pass tenant_fingerprint= now).
    assert "tenant_a" not in str(excinfo.value)
    assert "tenant_a" not in repr(excinfo.value)
