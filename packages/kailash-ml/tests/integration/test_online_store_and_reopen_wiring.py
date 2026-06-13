# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 wiring — FM2 Wave-3 Shard C (online store + fresh-reopen re-registration).

Two deliverables under one suite (``rules/testing.md`` Tier 2 — real infra, NO
mocking):

**C-1 (online store, ``OnlineFeatureStore``).** Marker ``online_store``.

- *Unavailable path (deterministic).* Point the adapter at an unreachable host
  and assert the typed :class:`OnlineStoreUnavailableError` propagates from both
  ``populate`` and ``get`` — never a bare ``redis.ConnectionError``. NO redis
  mock: the failure is a REAL connection refusal against an unroutable
  ``127.0.0.1`` port, so the wrapping is exercised against the live driver.
- *Live path (skip-if-unset).* When ``REDIS_URL`` is set, materialize →
  serve-online → read-back asserts the served rows match; a second tenant's
  rows stay isolated (the key embeds ``tenant_id``).

**C-2 (fresh-reopen re-registration).** Materialize on one ``FeatureStore``,
construct a FRESH one over the SAME SQLite file, ``get_features`` → assert rows
returned. Mirrors ``journal/0004``'s repro (the limitation this shard closes):
before disposition (a) the fresh read raised ``FeatureSourceError(... ListNode
not found ...)``; now the read self-heals by re-registering the dynamic
``@db.model`` on demand. Tenant isolation across the reopen is asserted too.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import pytest
from kailash_ml.errors import OnlineStoreUnavailableError, TenantRequiredError
from kailash_ml.features import (
    FeatureField,
    FeatureGroup,
    FeatureSchema,
    FeatureStore,
    OnlineFeatureStore,
    feature,
)

from dataflow import DataFlow

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@feature(name="amount_log", dtype="float64")
def amount_log() -> pl.Expr:
    return pl.col("amount").log1p()


def _schema(*, name: str = "UserFeatC") -> FeatureSchema:
    return FeatureSchema(
        name=name,
        version=1,
        fields=(FeatureField(name="amount", dtype="float64"),),
        entity_id_column="entity_id",
        timestamp_column="event_time",
    )


def _group(*, name: str = "UserFeatC") -> FeatureGroup:
    return FeatureGroup(_schema(name=name), features=[amount_log])


def _input_frame() -> pl.DataFrame:
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


# An unroutable Redis target — 127.0.0.1:1 is the reserved TCP port 1, which
# refuses immediately, giving a deterministic backend-down without a mock.
_UNREACHABLE_REDIS_URL = "redis://127.0.0.1:1/0"


# ===========================================================================
# C-1: online-store UNAVAILABLE path — deterministic, no mock
# ===========================================================================


@pytest.mark.online_store
async def test_online_store_populate_unavailable_raises_typed():
    """populate against an unreachable backend raises OnlineStoreUnavailableError
    (typed), NOT a bare redis.ConnectionError."""
    online = OnlineFeatureStore(_UNREACHABLE_REDIS_URL)
    try:
        with pytest.raises(OnlineStoreUnavailableError) as excinfo:
            await online.populate(_schema(), _input_frame(), tenant_id="_single")
        # The masked URL appears (credential-safe); no raw host:port creds leak.
        assert "***@127.0.0.1:1" in str(excinfo.value)
        # Cause-chained from the real redis exception (fail-loud, not swallowed).
        assert excinfo.value.__cause__ is not None
    finally:
        await online.close()


@pytest.mark.online_store
async def test_online_store_get_unavailable_raises_typed():
    """get against an unreachable backend raises OnlineStoreUnavailableError."""
    online = OnlineFeatureStore(_UNREACHABLE_REDIS_URL)
    try:
        with pytest.raises(OnlineStoreUnavailableError):
            await online.get(_schema(), ["u1"], tenant_id="_single")
    finally:
        await online.close()


@pytest.mark.online_store
async def test_online_store_serve_via_facade_unavailable_raises_typed(tmp_path: Path):
    """FeatureStore.serve_online surfaces the typed error from the online tier."""
    db_path = tmp_path / "c_serve_unavail.sqlite"
    df = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)
    store = FeatureStore(df)
    online = OnlineFeatureStore(_UNREACHABLE_REDIS_URL)
    try:
        with pytest.raises(OnlineStoreUnavailableError):
            await store.serve_online(online, _schema(), ["u1"], tenant_id="_single")
    finally:
        await online.close()
        try:
            df.close()
        except Exception:
            pass


@pytest.mark.online_store
async def test_online_store_missing_tenant_raises_before_backend():
    """Missing tenant raises TenantRequiredError BEFORE any backend call (a
    destructive/unscoped serve must not run — the validate gate fires first,
    so this passes even with no Redis reachable)."""
    online = OnlineFeatureStore(_UNREACHABLE_REDIS_URL)
    try:
        with pytest.raises(TenantRequiredError):
            await online.get(_schema(), ["u1"])  # no tenant
        with pytest.raises(TenantRequiredError):
            await online.populate(_schema(), _input_frame())  # no tenant
    finally:
        await online.close()


@pytest.mark.online_store
def test_online_store_url_is_masked_at_construction():
    """The instance exposes only a credential-masked URL (log-safe)."""
    online = OnlineFeatureStore("redis://user:topsecret@cache.internal:6380/3")
    assert online.masked_url == "redis://***@cache.internal:6380/3"
    assert "topsecret" not in online.masked_url


# ===========================================================================
# C-1: online-store LIVE path — skip-if-unset (real Redis via REDIS_URL)
# ===========================================================================

_LIVE_REDIS_URL = os.environ.get("REDIS_URL") or os.environ.get(
    "ONLINE_FEATURE_STORE_REDIS_URL"
)
_skip_no_redis = pytest.mark.skipif(
    _LIVE_REDIS_URL is None,
    reason="online_store live path needs REDIS_URL (or ONLINE_FEATURE_STORE_REDIS_URL)",
)


@pytest.mark.online_store
@_skip_no_redis
async def test_materialize_write_through_then_serve_online_reads_back(tmp_path: Path):
    """materialize(online_store=...) → serve_online reads the SAME rows back
    (online/offline key parity; live Redis)."""
    db_path = tmp_path / "c_live.sqlite"
    df = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)
    store = FeatureStore(df)
    online = OnlineFeatureStore(_LIVE_REDIS_URL, default_ttl_seconds=300)
    group = _group(name="UserFeatLive")
    try:
        result = await store.materialize(
            group, _input_frame(), tenant_id="acme", online_store=online
        )
        assert result["row_count"] == 2

        served = await store.serve_online(
            online, group.schema, ["u1", "u2"], tenant_id="acme"
        )
        by_entity = {r["entity_id"]: r for r in served.iter_rows(named=True)}
        assert set(by_entity) == {"u1", "u2"}
        assert by_entity["u1"]["amount"] == pytest.approx(9.0)
        assert by_entity["u2"]["amount"] == pytest.approx(99.0)
    finally:
        await online.close()
        try:
            df.close()
        except Exception:
            pass


@pytest.mark.online_store
@_skip_no_redis
async def test_online_serve_is_tenant_isolated(tmp_path: Path):
    """Materialize tenant A + tenant B online; serving A returns ONLY A's rows
    (the cache key embeds tenant_id — tenant-isolation Rule 1)."""
    db_path = tmp_path / "c_live_mt.sqlite"
    df = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)
    store = FeatureStore(df)
    online = OnlineFeatureStore(_LIVE_REDIS_URL, default_ttl_seconds=300)
    schema = FeatureSchema(
        name="UserFeatTenantIso",
        version=1,
        fields=(FeatureField(name="amount", dtype="float64"),),
        entity_id_column="entity_id",
        timestamp_column="event_time",
    )
    try:
        a_frame = pl.DataFrame(
            {
                "entity_id": ["e1"],
                "event_time": [datetime(2026, 1, 1, tzinfo=timezone.utc)],
                "amount": [11.0],
            }
        )
        b_frame = pl.DataFrame(
            {
                "entity_id": ["e1"],  # SAME entity id, different tenant
                "event_time": [datetime(2026, 1, 1, tzinfo=timezone.utc)],
                "amount": [777.0],
            }
        )
        await online.populate(schema, a_frame, tenant_id="tenant_a")
        await online.populate(schema, b_frame, tenant_id="tenant_b")

        a_served = await store.serve_online(
            online, schema, ["e1"], tenant_id="tenant_a"
        )
        a_rows = list(a_served.iter_rows(named=True))
        assert len(a_rows) == 1
        # Tenant A sees its OWN value (11.0), never tenant B's (777.0).
        assert a_rows[0]["amount"] == pytest.approx(11.0)
        assert a_rows[0]["amount"] != pytest.approx(777.0)
    finally:
        await online.close()
        try:
            df.close()
        except Exception:
            pass


# ===========================================================================
# C-2: fresh-reopen re-registration (closes journal/0004 limitation)
# ===========================================================================


async def test_fresh_store_reopen_reads_materialised_table(tmp_path: Path):
    """C-2 repro: materialize on one FeatureStore, construct a FRESH FeatureStore
    over the SAME SQLite file, get_features → rows returned.

    Before disposition (a) the fresh read raised FeatureSourceError(... ListNode
    not found ...) because the dynamic @db.model was only registered in the
    materialising instance. The read now self-heals by re-registering on demand.
    """
    db_path = tmp_path / "c_reopen.sqlite"
    group = _group(name="UserFeatReopen")

    # Instance 1: materialize, then close (release the DataFlow registry).
    df1 = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)
    store1 = FeatureStore(df1)
    res = await store1.materialize(group, _input_frame(), tenant_id="_single")
    assert res["row_count"] == 2
    try:
        df1.close()
    except Exception:
        pass

    # Instance 2: a FRESH DataFlow over the SAME file — has NEVER registered the
    # model. The read must self-heal, not raise FeatureSourceError.
    df2 = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)
    store2 = FeatureStore(df2)
    try:
        out = await store2.get_features(group.schema, tenant_id="_single")
        entities = set(out["entity_id"].to_list())
        assert entities == {"u1", "u2"}, (
            "fresh-reopen read returned no rows — model re-registration self-heal "
            "did not fire (journal/0004 disposition (a) regression)"
        )
    finally:
        try:
            df2.close()
        except Exception:
            pass


async def test_fresh_store_reopen_serves_online_after_reregister(tmp_path: Path):
    """C-2 ⨯ C-1 cross-check (offline path only, no Redis dep): a FRESH store over
    the same file can re-derive + re-materialise the SAME logical rows
    idempotently. Proves the read/registration self-heal composes with a
    subsequent write on the fresh instance (the materialiser's own _ensure_model
    and the read self-heal share ONE registration helper, so the fresh instance
    binds the model exactly once whichever path touches it first).
    """
    db_path = tmp_path / "c_reopen_rematerialise.sqlite"
    group = _group(name="UserFeatReopenRe")

    df1 = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)
    store1 = FeatureStore(df1)
    await store1.materialize(group, _input_frame(), tenant_id="_single")
    try:
        df1.close()
    except Exception:
        pass

    # Fresh instance: read self-heal registers the model, THEN a re-materialise
    # on the same fresh instance is idempotent (content-addressed ids).
    df2 = DataFlow(f"sqlite:///{db_path}", auto_migrate=True)
    store2 = FeatureStore(df2)
    try:
        # Read first — exercises the read-path re-registration self-heal.
        out = await store2.get_features(group.schema, tenant_id="_single")
        assert set(out["entity_id"].to_list()) == {"u1", "u2"}

        # Re-materialise on the fresh instance — must NOT duplicate rows (the
        # shared helper already registered the model; the second registration is
        # a no-op).
        res2 = await store2.materialize(group, _input_frame(), tenant_id="_single")
        assert res2["row_count"] == 2
        rows = await df2.express.list("UserFeatReopenRe", {}, limit=100)
        assert len(rows) == 2, "re-materialise on fresh instance duplicated rows"
    finally:
        try:
            df2.close()
        except Exception:
            pass
