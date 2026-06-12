# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 wiring — ``FeatureMaterialiser`` + ``FeatureStore.materialize`` (FM2 Shard B).

Per ``rules/facade-manager-detection.md`` MUST Rule 2 + ``rules/orphan-detection.md``
MUST Rule 2, this exercises the write-through materialise path end-to-end against a
REAL DataFlow instance (file-backed SQLite) and asserts the externally-observable
contract for the 7 Shard-B invariants:

1. **tenant isolation** — cross-tenant materialise raises
   :class:`CrossTenantReadError`; missing tenant raises
   :class:`TenantRequiredError`.
2. **classification propagation** — a column flagged REDACT on the group is
   ``[REDACTED]`` in the returned summary frame (mutation return-path redaction);
   the PERSISTED value is the real value (read-back proves it).
3. **compute correctness** — the ``@feature``-derived column in the persisted
   table equals the expected ``fn`` output.
4. **lineage-hash registration** — ``materialize`` returns a stable
   ``sha256:<64hex>`` lineage hash; identical re-materialise reproduces it.
5. **point-in-time consistency** — after materialise, a
   ``FeatureStore.get_features(timestamp=T)`` read returns the as-of-correct row.
6. **idempotent re-materialise** — re-running the same materialise does NOT
   duplicate rows (read-back row count is stable).
7. **cache invalidation** — the result carries the tenant-scoped ``v*`` wildcard
   matching the store's existing ``invalidation_pattern``.

NO MOCKING — real DataFlow persistence path + real ``dataflow.transform`` +
``dataflow.hash`` (``rules/testing.md`` Tier 2). Every write is verified with a
read-back (``rules/testing.md`` State Persistence). File-backed SQLite mirrors the
precedent in ``test_feature_group_authoring.py`` + ``test_feature_registry.py``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import pytest
from kailash_ml.errors import (
    CrossTenantReadError,
    FeatureStoreError,
    TenantRequiredError,
)
from kailash_ml.features import (
    FeatureField,
    FeatureGroup,
    FeatureMaterialiser,
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


def _group(
    *, name: str = "UserFeat", classification: dict | None = None
) -> FeatureGroup:
    return FeatureGroup(
        _schema(name=name),
        classification=classification,
        features=[amount_log],
    )


def _input_frame() -> pl.DataFrame:
    """Two entities, one row each, with an event_time for point-in-time reads."""
    return pl.DataFrame(
        {
            "entity_id": ["u1", "u2"],
            "event_time": [
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 2, tzinfo=timezone.utc),
            ],
            "amount": [9.0, 99.0],
        }
    )


@pytest.fixture
def store_db(tmp_path: Path):
    """Single-tenant DataFlow + a FeatureStore over it (file-backed SQLite)."""
    db_path = tmp_path / "feat_materialise.sqlite"
    df = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)
    store = FeatureStore(df)
    try:
        yield store, df, db_path
    finally:
        try:
            df.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Invariant 3 + 6: compute correctness + read-back, via the FeatureStore facade
# ---------------------------------------------------------------------------


async def test_materialize_persists_and_reads_back(store_db):
    """materialize via FeatureStore → read-back the persisted table; assert
    derived values + lineage hash recorded (invariants 3, 4)."""
    store, df, _ = store_db
    group = _group()

    result = await store.materialize(group, _input_frame(), tenant_id="_single")

    # Lineage hash is the shipped sha256:<64hex> shape (invariant 4).
    assert isinstance(result["lineage_hash"], str)
    assert result["lineage_hash"].startswith("sha256:")
    assert len(result["lineage_hash"].split(":", 1)[1]) == 64
    assert result["row_count"] == 2
    assert result["group"] == "UserFeat"
    assert result["version"] == 1

    # Read-back the PERSISTED table (NO mocking — real backing store).
    rows = await df.express.list("UserFeat", {}, limit=100)
    assert len(rows) == 2
    by_entity = {r["entity_id"]: r for r in rows}

    # Compute correctness (invariant 3): amount_log == log1p(amount).
    import math

    assert by_entity["u1"]["amount_log"] == pytest.approx(math.log1p(9.0))
    assert by_entity["u2"]["amount_log"] == pytest.approx(math.log1p(99.0))
    # Base column round-trips too.
    assert by_entity["u1"]["amount"] == pytest.approx(9.0)


async def test_materialize_logs_fingerprint_not_raw_tenant(store_db, caplog):
    """HIGH-2 regression (Wave-2 redteam R2): NO materialiser log line — on the
    success (.start/.compute/.ok) OR failure (.error) path — may carry the RAW
    tenant id; only ``tenant_fingerprint`` (observability Rule 4/8). Guards both
    the .ok (line 292) and .error (line 322) sites the R1 fix missed."""
    import logging

    store, df, _ = store_db
    group = _group()

    # Success path — emits feature_materialise.{start,compute,ok}.
    with caplog.at_level(logging.DEBUG, logger="kailash_ml.features.materialiser"):
        await store.materialize(group, _input_frame(), tenant_id="acme_audit")
    mat_records = [
        r for r in caplog.records if r.getMessage().startswith("feature_materialise")
    ]
    assert mat_records, "no feature_materialise log lines emitted"
    for r in mat_records:
        assert (
            getattr(r, "tenant_id", None) is None
        ), f"raw tenant_id leaked on log line {r.getMessage()!r}"
        assert "acme_audit" not in r.getMessage()
        assert getattr(r, "tenant_fingerprint", "").startswith("sha256:")

    # Failure path — inject a persist failure so feature_materialise.error fires;
    # assert neither the log record nor the wrapping exception carries the raw tenant.
    caplog.clear()

    async def _boom(*a, **kw):
        raise RuntimeError("injected persist failure")

    monkeypatch_target = df.express
    orig_upsert = monkeypatch_target.upsert
    monkeypatch_target.upsert = _boom
    try:
        with caplog.at_level(logging.INFO, logger="kailash_ml.features.materialiser"):
            with pytest.raises(FeatureStoreError) as excinfo:
                await store.materialize(group, _input_frame(), tenant_id="acme_audit")
    finally:
        monkeypatch_target.upsert = orig_upsert
    assert "acme_audit" not in str(excinfo.value)
    assert "acme_audit" not in repr(excinfo.value)
    err_records = [
        r for r in caplog.records if r.getMessage() == "feature_materialise.error"
    ]
    assert err_records, "no feature_materialise.error log line emitted on failure"
    for r in err_records:
        assert getattr(r, "tenant_id", None) is None
        assert "acme_audit" not in r.getMessage()


# ---------------------------------------------------------------------------
# Invariant 6: idempotent re-materialise (no duplicate rows)
# ---------------------------------------------------------------------------


async def test_rematerialize_is_idempotent(store_db):
    """Re-running the same materialize does NOT duplicate rows (invariant 6)."""
    store, df, _ = store_db
    group = _group()

    await store.materialize(group, _input_frame(), tenant_id="_single")
    first = await df.express.list("UserFeat", {}, limit=100)
    assert len(first) == 2

    # Identical re-materialise — content-addressed ids conflict-resolve via upsert.
    await store.materialize(group, _input_frame(), tenant_id="_single")
    second = await df.express.list("UserFeat", {}, limit=100)
    assert len(second) == 2, "re-materialise duplicated rows"


# ---------------------------------------------------------------------------
# Invariant 4: lineage-hash stability across identical re-materialise
# ---------------------------------------------------------------------------


async def test_lineage_hash_is_stable(store_db):
    """Identical re-materialise reproduces the same lineage hash (invariant 4)."""
    store, _, _ = store_db
    group = _group()

    r1 = await store.materialize(group, _input_frame(), tenant_id="_single")
    r2 = await store.materialize(group, _input_frame(), tenant_id="_single")
    assert r1["lineage_hash"] == r2["lineage_hash"]


# ---------------------------------------------------------------------------
# Invariant 1: tenant isolation
# ---------------------------------------------------------------------------


async def test_missing_tenant_raises(store_db):
    """A store with no default tenant requires tenant_id (invariant 1)."""
    store, _, _ = store_db
    group = _group()
    with pytest.raises(TenantRequiredError):
        await store.materialize(group, _input_frame())  # no tenant


async def test_cross_tenant_materialise_raises(tmp_path: Path):
    """A group bound to tenant A materialised under tenant B raises
    CrossTenantReadError (invariant 1)."""
    db_path = tmp_path / "feat_materialise_mt.sqlite"
    df = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)
    materialiser = FeatureMaterialiser(df)
    try:
        # Group bound to tenant_a via its classification dict (the registry's
        # convention for a tenant-scoped rehydrated group).
        bound_group = FeatureGroup(
            _schema(),
            classification={"tenant_id": "tenant_a"},
            features=[amount_log],
        )

        # Materialising under tenant_b crosses the boundary → typed refusal.
        with pytest.raises(CrossTenantReadError):
            await materialiser.materialize(
                bound_group, _input_frame(), tenant_id="tenant_b"
            )
        # FeatureStoreError supertype also catches it (taxonomy).
        with pytest.raises(FeatureStoreError):
            await materialiser.materialize(
                bound_group, _input_frame(), tenant_id="tenant_b"
            )

        # Under the matching tenant it proceeds + persists.
        ok = await materialiser.materialize(
            bound_group, _input_frame(), tenant_id="tenant_a"
        )
        assert ok["row_count"] == 2
    finally:
        try:
            df.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Invariant 2: classification propagation on the mutation return-path
# ---------------------------------------------------------------------------


async def test_classified_column_redacted_in_return_frame_only(store_db):
    """A REDACT-flagged column is [REDACTED] in the returned summary frame, but
    the PERSISTED value is the real value (invariant 2 — mutation return-path
    redaction; the backing store holds real data)."""
    store, df, _ = store_db
    group = _group(classification={"amount": ("SECRET", "REDACT")})

    result = await store.materialize(group, _input_frame(), tenant_id="_single")

    # Returned summary frame: classified column redacted.
    frame = result["frame"]
    assert frame["amount"].to_list() == ["[REDACTED]", "[REDACTED]"]

    # Persisted backing rows: REAL value (redaction is return-path only).
    rows = await df.express.list("UserFeat", {}, limit=100)
    by_entity = {r["entity_id"]: r for r in rows}
    assert by_entity["u1"]["amount"] == pytest.approx(9.0)


# ---------------------------------------------------------------------------
# Invariant 7: cache invalidation pattern parity with the read surface
# ---------------------------------------------------------------------------


async def test_invalidation_pattern_matches_store(store_db):
    """The result's invalidation_pattern matches the store's existing
    invalidation_pattern helper (invariant 7)."""
    store, _, _ = store_db
    group = _group()

    result = await store.materialize(group, _input_frame(), tenant_id="_single")
    expected = store.invalidation_pattern(group.schema, tenant_id="_single")
    assert result["invalidation_pattern"] == expected
    # Tenant-scoped v* wildcard (tenant-isolation Rule 3a shape).
    assert ":_single:" in result["invalidation_pattern"]
    assert result["invalidation_pattern"].startswith("kailash_ml:v*:")


# ---------------------------------------------------------------------------
# Invariant 5: point-in-time consistency after materialise
# ---------------------------------------------------------------------------


async def test_point_in_time_read_after_materialize(store_db):
    """After materialise, get_features(timestamp=T) returns the as-of-correct row
    (invariant 5). Per-row event_time was persisted, not synthesised at read."""
    store, _, _ = store_db
    group = _group()

    await store.materialize(group, _input_frame(), tenant_id="_single")

    # Read AS OF 2026-01-01: only u1's row has event_time <= T.
    as_of = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    df_out = await store.get_features(
        group.schema, timestamp=as_of, tenant_id="_single"
    )
    entities = set(df_out["entity_id"].to_list())
    assert "u1" in entities
    assert "u2" not in entities, "future-dated row leaked into the as-of read"

    # Read AS OF 2026-01-03: both rows visible.
    as_of2 = datetime(2026, 1, 3, tzinfo=timezone.utc)
    df_out2 = await store.get_features(
        group.schema, timestamp=as_of2, tenant_id="_single"
    )
    assert set(df_out2["entity_id"].to_list()) == {"u1", "u2"}


# ---------------------------------------------------------------------------
# schema-migration Rule 1: the backing table is a real @db.model (auto_migrate),
# NOT inline DDL — verify the table exists in the SQLite schema.
# ---------------------------------------------------------------------------


async def test_backing_table_created_via_db_model(store_db):
    """The materialised feature table is a DataFlow @db.model auto-migrated table
    (schema-migration Rule 1 — no inline DDL). Verify it via the DataFlow read
    surface (the pool-aware, WAL-consistent path) that the persisted rows carry
    the content-addressed id PK + the entity/declared/derived columns — proving
    the @db.model auto-migration created the full schema."""
    store, df, _ = store_db
    group = _group()
    await store.materialize(group, _input_frame(), tenant_id="_single")

    # Read-back through DataFlow Express (NOT a raw sqlite3 connection — that
    # bypasses the pool + WAL and can observe pre-checkpoint state). The row
    # keys ARE the auto-migrated columns.
    rows = await df.express.list("UserFeat", {}, limit=100)
    assert rows, "backing table UserFeat not created/populated by auto_migrate"
    col_names = set(rows[0].keys())
    # The deterministic content-addressed id PK + entity/declared/derived columns.
    assert "id" in col_names
    assert "entity_id" in col_names
    assert "amount" in col_names
    assert "amount_log" in col_names
    # The content-addressed id is a 32-hex deterministic key, not an autoincrement.
    assert all(
        isinstance(r["id"], str) and len(r["id"]) == 32 for r in rows
    ), "materialized rows lack the deterministic content-addressed id PK"
