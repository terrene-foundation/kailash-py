# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for FeatureStore construction + dependency guards.

These do NOT hit a real DataFlow / database — they cover:

1. Constructor-side validation (missing dataflow, bad default_tenant_id).
2. Tenant resolution: method-kwarg > default > TenantRequiredError.
3. Cache key / invalidation pattern helpers route through the canonical
   key builder.
4. Loud ImportError when ``dataflow.ml_feature_source`` is unavailable
   (simulated via monkeypatching the deferred loader).
"""
from __future__ import annotations

from types import SimpleNamespace

import polars as pl
import pytest
from kailash_ml.errors import TenantRequiredError
from kailash_ml.features import FeatureField, FeatureSchema, FeatureStore
from kailash_ml.features import store as _store_mod


def _mk_schema() -> FeatureSchema:
    return FeatureSchema(
        name="user_churn",
        version=1,
        fields=(
            FeatureField(name="age", dtype="float64"),
            FeatureField(name="tenure_months", dtype="int64"),
        ),
        entity_id_column="user_id",
    )


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


def test_constructor_requires_dataflow_instance() -> None:
    with pytest.raises(TypeError, match="dataflow=...\\) is required"):
        FeatureStore(None)  # type: ignore[arg-type]


def test_constructor_validates_default_tenant_id() -> None:
    fake_df = SimpleNamespace()  # store never touches the df in ctor
    with pytest.raises(TenantRequiredError, match="forbidden sentinel"):
        FeatureStore(fake_df, default_tenant_id="default")  # type: ignore[arg-type]


def test_default_tenant_id_returned_via_property() -> None:
    fake_df = SimpleNamespace()
    fs = FeatureStore(fake_df, default_tenant_id="acme")  # type: ignore[arg-type]
    assert fs.default_tenant_id == "acme"
    assert fs.dataflow is fake_df


# ---------------------------------------------------------------------------
# Cache key plumbing — the store routes to the canonical helper
# ---------------------------------------------------------------------------


def test_cache_key_for_row_routes_through_canonical_helper() -> None:
    fake_df = SimpleNamespace()
    fs = FeatureStore(fake_df, default_tenant_id="acme")  # type: ignore[arg-type]
    schema = _mk_schema()
    key = fs.cache_key_for_row(schema, "u42")
    assert key == "kailash_ml:v1:acme:feature:user_churn:1:u42"


def test_cache_key_for_row_accepts_override_tenant() -> None:
    fake_df = SimpleNamespace()
    fs = FeatureStore(fake_df, default_tenant_id="acme")  # type: ignore[arg-type]
    schema = _mk_schema()
    key = fs.cache_key_for_row(schema, "u1", tenant_id="bob")
    assert "bob" in key and "acme" not in key


def test_cache_key_for_row_missing_tenant_raises() -> None:
    fake_df = SimpleNamespace()
    fs = FeatureStore(fake_df)  # type: ignore[arg-type]
    schema = _mk_schema()
    with pytest.raises(TenantRequiredError):
        fs.cache_key_for_row(schema, "u1")


def test_invalidation_pattern_single_version() -> None:
    fake_df = SimpleNamespace()
    fs = FeatureStore(fake_df, default_tenant_id="acme")  # type: ignore[arg-type]
    pat = fs.invalidation_pattern(_mk_schema())
    assert pat == "kailash_ml:v*:acme:feature:user_churn:1:*"


def test_invalidation_pattern_all_versions() -> None:
    fake_df = SimpleNamespace()
    fs = FeatureStore(fake_df, default_tenant_id="acme")  # type: ignore[arg-type]
    pat = fs.invalidation_pattern(_mk_schema(), all_versions=True)
    assert pat == "kailash_ml:v*:acme:feature:user_churn:*"


# ---------------------------------------------------------------------------
# get_features — argument validation (no DataFlow required)
# ---------------------------------------------------------------------------


async def test_get_features_rejects_non_schema() -> None:
    fs = FeatureStore(SimpleNamespace(), default_tenant_id="acme")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="schema must be FeatureSchema"):
        await fs.get_features("user_churn")  # type: ignore[arg-type]


async def test_get_features_rejects_non_datetime_timestamp() -> None:
    fs = FeatureStore(SimpleNamespace(), default_tenant_id="acme")  # type: ignore[arg-type]
    schema = _mk_schema()
    with pytest.raises(TypeError, match="timestamp must be datetime"):
        await fs.get_features(schema, timestamp="2026-01-01")  # type: ignore[arg-type]


async def test_get_features_requires_tenant_id() -> None:
    fs = FeatureStore(SimpleNamespace())  # type: ignore[arg-type]
    schema = _mk_schema()
    with pytest.raises(TenantRequiredError):
        await fs.get_features(schema)


# ---------------------------------------------------------------------------
# ml_feature_source loud failure path
# ---------------------------------------------------------------------------


async def test_get_features_raises_import_error_when_binding_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``ml_feature_source`` is not resolvable, the store MUST
    fail loudly with an actionable ImportError citing the canonical
    sibling spec ``specs/dataflow-ml-integration.md §1.1``.
    """
    monkeypatch.setattr(
        _store_mod,
        "_import_ml_feature_source",
        _raise_missing_binding,
    )
    fs = FeatureStore(SimpleNamespace(), default_tenant_id="acme")  # type: ignore[arg-type]
    with pytest.raises(ImportError) as ei:
        await fs.get_features(_mk_schema())
    # Message MUST name the binding AND cite the sibling spec so
    # operators have a durable cross-reference (no workspace-history
    # references per `rules/specs-authority.md` § 1).
    msg = str(ei.value)
    assert "ml_feature_source" in msg
    assert "dataflow-ml-integration.md" in msg


def _raise_missing_binding():
    raise ImportError(
        "ml_feature_source is not available. kailash-ml 1.0+ "
        "FeatureStore.get_features requires DataFlow 2.1.0's polars "
        "binding — see specs/dataflow-ml-integration.md §1.1 for the "
        "canonical contract."
    )


# ---------------------------------------------------------------------------
# ml_feature_source happy path (protocol-satisfying deterministic adapter)
# ---------------------------------------------------------------------------


async def test_get_features_returns_polars_dataframe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a deterministic ml_feature_source binding the store returns a
    polars.DataFrame and emits the ok log line (invariant #1: polars in,
    polars out; no pandas)."""
    schema = _mk_schema()
    expected = pl.DataFrame(
        {"user_id": ["u1", "u2"], "age": [30.0, 40.0], "tenure_months": [5, 12]}
    )

    calls: list[dict] = []

    def fake_source(sch, *, tenant_id, point_in_time):
        calls.append(
            {"schema": sch, "tenant_id": tenant_id, "point_in_time": point_in_time}
        )
        return expected  # real polars.DataFrame (not a mock)

    monkeypatch.setattr(
        _store_mod,
        "_import_ml_feature_source",
        lambda: fake_source,
    )
    fs = FeatureStore(SimpleNamespace(), default_tenant_id="acme")  # type: ignore[arg-type]
    out = await fs.get_features(schema)
    assert isinstance(out, pl.DataFrame)
    assert out.columns == ["user_id", "age", "tenure_months"]
    assert calls[0]["tenant_id"] == "acme"
    assert calls[0]["point_in_time"] is None


async def test_get_features_collects_lazyframe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Binding may return a LazyFrame; the store MUST collect before return."""
    schema = _mk_schema()
    frame = pl.DataFrame({"user_id": ["u1"], "age": [30.0], "tenure_months": [5]})

    monkeypatch.setattr(
        _store_mod,
        "_import_ml_feature_source",
        lambda: lambda s, *, tenant_id, point_in_time: frame.lazy(),
    )
    fs = FeatureStore(SimpleNamespace(), default_tenant_id="acme")  # type: ignore[arg-type]
    out = await fs.get_features(schema)
    assert isinstance(out, pl.DataFrame)
    assert out.height == 1


async def test_get_features_entity_id_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = _mk_schema()
    full = pl.DataFrame(
        {
            "user_id": ["u1", "u2", "u3"],
            "age": [1.0, 2.0, 3.0],
            "tenure_months": [1, 2, 3],
        }
    )
    monkeypatch.setattr(
        _store_mod,
        "_import_ml_feature_source",
        lambda: lambda s, *, tenant_id, point_in_time: full,
    )
    fs = FeatureStore(SimpleNamespace(), default_tenant_id="acme")  # type: ignore[arg-type]
    out = await fs.get_features(schema, entity_ids=["u1", "u3"])
    assert sorted(out["user_id"].to_list()) == ["u1", "u3"]
