# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 — dataflow.ml import + symbol presence tests.

Per ``rules/orphan-detection.md`` MUST Rule 6, every public symbol in
``dataflow.ml.__all__`` MUST be eagerly importable. This file is the
mechanical guard — a future refactor that accidentally drops a symbol
from the ``dataflow.ml`` surface fails here in milliseconds.

These tests do NOT exercise end-to-end behavior (see the integration
tier for that); they assert only that the public API surface exists in
the shape spec'd by ``specs/dataflow-ml-integration.md`` § 1.1.
"""

from __future__ import annotations

import inspect

import polars as pl
import pytest


@pytest.mark.unit
def test_import_dataflow_ml_module_succeeds():
    """``import dataflow.ml`` must succeed without kailash-ml installed."""
    import dataflow.ml as ml  # noqa: F401


@pytest.mark.unit
def test_public_api_symbols_present():
    """Every symbol in ``specs/dataflow-ml-integration.md`` § 1.1 is exported."""
    import dataflow.ml as ml

    required = {
        "ml_feature_source",
        "transform",
        "hash",
        "TrainingContext",
        "ML_TRAIN_START_EVENT",
        "ML_TRAIN_END_EVENT",
        "emit_train_start",
        "emit_train_end",
        "on_train_start",
        "on_train_end",
        "_kml_classify_actions",
        "build_cache_key",
        "DataFlowMLIntegrationError",
        "FeatureSourceError",
        "DataFlowTransformError",
        "LineageHashError",
        "MLTenantRequiredError",
    }
    missing = required - set(ml.__all__)
    assert not missing, f"dataflow.ml.__all__ missing symbols: {sorted(missing)}"
    for symbol in required:
        assert hasattr(ml, symbol), f"dataflow.ml.{symbol} not importable"


@pytest.mark.unit
def test_training_context_requires_non_empty_fields():
    from dataflow.ml import TrainingContext

    good = TrainingContext(
        run_id="r1",
        tenant_id="t1",
        dataset_hash="sha256:" + "a" * 64,
        actor_id="alice",
    )
    assert good.run_id == "r1"
    assert good.tenant_id == "t1"

    # Empty run_id rejected
    with pytest.raises(ValueError, match="run_id"):
        TrainingContext(
            run_id="",
            tenant_id="t1",
            dataset_hash="sha256:" + "a" * 64,
            actor_id="alice",
        )

    # Missing sha256 prefix rejected
    with pytest.raises(ValueError, match="dataset_hash"):
        TrainingContext(
            run_id="r1",
            tenant_id="t1",
            dataset_hash="notahash",
            actor_id="alice",
        )

    # Empty actor_id rejected
    with pytest.raises(ValueError, match="actor_id"):
        TrainingContext(
            run_id="r1",
            tenant_id="t1",
            dataset_hash="sha256:" + "a" * 64,
            actor_id="",
        )


@pytest.mark.unit
def test_training_context_is_frozen():
    from dataflow.ml import TrainingContext

    ctx = TrainingContext(
        run_id="r1",
        tenant_id="t1",
        dataset_hash="sha256:" + "a" * 64,
        actor_id="alice",
    )
    with pytest.raises(Exception):
        ctx.run_id = "r2"  # type: ignore[misc]


@pytest.mark.unit
def test_hash_stable_same_data_reordered_columns_returns_same_hash():
    """spec § 4.3 — stable=True produces same hash for reordered columns."""
    from dataflow.ml import hash as df_hash

    df_a = pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    df_b = pl.DataFrame({"b": ["x", "y", "z"], "a": [1, 2, 3]})

    assert df_hash(df_a) == df_hash(df_b)


@pytest.mark.unit
def test_hash_stable_same_data_reordered_rows_returns_same_hash():
    """spec § 4.3 — stable=True produces same hash for reordered rows."""
    from dataflow.ml import hash as df_hash

    df_a = pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    df_b = pl.DataFrame({"a": [3, 1, 2], "b": ["z", "x", "y"]})

    assert df_hash(df_a) == df_hash(df_b)


@pytest.mark.unit
def test_hash_stable_false_different_hash_for_reordered_rows():
    """spec § 4.3 — stable=False is order-sensitive."""
    from dataflow.ml import hash as df_hash

    df_a = pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    df_b = pl.DataFrame({"a": [3, 1, 2], "b": ["z", "x", "y"]})

    # Without canonicalization, order matters
    assert df_hash(df_a, stable=False) != df_hash(df_b, stable=False)


@pytest.mark.unit
def test_hash_format_is_sha256_prefixed_64hex():
    """spec § 4.1 — return value matches r'^sha256:[a-f0-9]{64}$'."""
    import re

    from dataflow.ml import hash as df_hash

    df = pl.DataFrame({"a": [1]})
    h = df_hash(df)
    assert re.match(r"^sha256:[a-f0-9]{64}$", h), f"bad hash shape: {h!r}"


@pytest.mark.unit
def test_hash_rejects_non_polars_input():
    from dataflow.ml import LineageHashError, hash as df_hash

    with pytest.raises(LineageHashError):
        df_hash({"not": "a frame"})  # type: ignore[arg-type]

    with pytest.raises(LineageHashError):
        df_hash([1, 2, 3])  # type: ignore[arg-type]


@pytest.mark.unit
def test_hash_rejects_unsupported_algorithm():
    from dataflow.ml import LineageHashError, hash as df_hash

    df = pl.DataFrame({"a": [1]})
    with pytest.raises(LineageHashError, match="algorithm"):
        df_hash(df, algorithm="md5")


@pytest.mark.unit
def test_hash_accepts_lazyframe():
    from dataflow.ml import hash as df_hash

    lf = pl.LazyFrame({"a": [1, 2, 3]})
    h = df_hash(lf)
    assert h.startswith("sha256:")


@pytest.mark.unit
def test_transform_rejects_pandas():
    """spec § 1.3 — pandas inputs rejected at the boundary."""
    import polars as pl

    from dataflow.ml import DataFlowTransformError, transform

    expr = pl.col("a") + 1
    try:
        import pandas as pd
    except ImportError:
        pytest.skip("pandas not installed; rejection test not applicable")

    source = pd.DataFrame({"a": [1, 2, 3]})
    with pytest.raises(DataFlowTransformError, match="polars"):
        transform(expr, source, name="t1")


@pytest.mark.unit
def test_transform_rejects_non_expr():
    from dataflow.ml import DataFlowTransformError, transform

    source = pl.LazyFrame({"a": [1]})
    with pytest.raises(DataFlowTransformError, match="polars.Expr"):
        transform("col_a + 1", source, name="t1")  # type: ignore[arg-type]


@pytest.mark.unit
def test_transform_requires_non_empty_name():
    from dataflow.ml import DataFlowTransformError, transform

    source = pl.LazyFrame({"a": [1]})
    expr = pl.col("a") + 1
    with pytest.raises(DataFlowTransformError, match="name"):
        transform(expr, source, name="")


@pytest.mark.unit
def test_transform_applies_expression_to_lazyframe():
    from dataflow.ml import transform

    source = pl.LazyFrame({"a": [1, 2, 3]})
    expr = pl.col("a") + 10
    result = transform(expr, source, name="plus_ten")
    collected = result.collect()
    assert "plus_ten" in collected.columns
    assert collected["plus_ten"].to_list() == [11, 12, 13]


@pytest.mark.unit
def test_transform_preserves_classification_metadata():
    """spec § 3.3 — classification metadata survives transform chain."""
    from dataflow.ml import transform

    source = pl.LazyFrame({"a": [1, 2, 3]})
    source._kailash_ml_metadata = {  # type: ignore[attr-defined]
        "kailash_ml.classification": {"a": "PII"}
    }
    expr = pl.col("a") + 1
    result = transform(expr, source, name="t1", tenant_id="tenant-42")

    meta = getattr(result, "_kailash_ml_metadata", {})
    assert meta.get("kailash_ml.classification") == {"a": "PII"}
    assert meta.get("kailash_ml.transform") == "t1"
    assert meta.get("kailash_ml.tenant_id") == "tenant-42"


@pytest.mark.unit
def test_kml_classify_actions_none_policy_allows_all():
    from dataflow.ml import _kml_classify_actions

    result = _kml_classify_actions(None, "User", ["id", "email", "age"])
    assert result == {"id": "allow", "email": "allow", "age": "allow"}


@pytest.mark.unit
def test_kml_classify_actions_translates_masking_strategies():
    from dataflow.classification.policy import FieldClassification
    from dataflow.classification.types import (
        DataClassification,
        MaskingStrategy,
        RetentionPolicy,
    )
    from dataflow.ml import _kml_classify_actions

    class StubPolicy:
        def __init__(self, mapping):
            self._mapping = mapping

        def get_field(self, model, field):
            return self._mapping.get((model, field))

    policy = StubPolicy(
        {
            ("User", "email"): FieldClassification(
                DataClassification.PII,
                RetentionPolicy.YEARS_7,
                MaskingStrategy.REDACT,
            ),
            ("User", "ssn"): FieldClassification(
                DataClassification.PII,
                RetentionPolicy.YEARS_7,
                MaskingStrategy.HASH,
            ),
            ("User", "card"): FieldClassification(
                DataClassification.PII,
                RetentionPolicy.YEARS_7,
                MaskingStrategy.LAST_FOUR,
            ),
            ("User", "password"): FieldClassification(
                DataClassification.SENSITIVE,
                RetentionPolicy.YEARS_7,
                MaskingStrategy.ENCRYPT,
            ),
            ("User", "display_name"): FieldClassification(
                DataClassification.PUBLIC,
                RetentionPolicy.INDEFINITE,
                MaskingStrategy.NONE,
            ),
        }
    )

    actions = _kml_classify_actions(
        policy,
        "User",
        ["id", "email", "ssn", "card", "password", "display_name"],
    )
    assert actions == {
        "id": "allow",  # not in policy -> allow
        "email": "redact",
        "ssn": "hash",
        "card": "hash",
        "password": "encrypt",
        "display_name": "allow",  # NONE masking -> allow
    }


@pytest.mark.unit
def test_build_cache_key_multi_tenant_includes_tenant_id():
    """rules/tenant-isolation.md § 1 — multi-tenant key carries tenant."""
    from dataflow.ml import build_cache_key

    key = build_cache_key(
        group_name="user_features",
        tenant_id="tenant-a",
        point_in_time=None,
        since=None,
        until=None,
        limit=None,
    )
    assert "tenant-a" in key
    assert key.startswith("kailash_ml:v1:tenant-a:feature_source:user_features:")


@pytest.mark.unit
def test_build_cache_key_single_tenant_omits_tenant_slot():
    from dataflow.ml import build_cache_key

    key = build_cache_key(
        group_name="user_features",
        tenant_id=None,
        point_in_time=None,
        since=None,
        until=None,
        limit=None,
    )
    assert key.startswith("kailash_ml:v1:feature_source:user_features:")


@pytest.mark.unit
def test_ml_feature_source_conflicting_window_raises():
    """spec § 2.2 — point_in_time + since/until raises ValueError."""
    from datetime import datetime

    from dataflow.ml import ml_feature_source

    class DummyGroup:
        name = "g"
        multi_tenant = False

    with pytest.raises(ValueError, match="point_in_time"):
        ml_feature_source(
            DummyGroup(),
            point_in_time=datetime(2026, 1, 1),
            since=datetime(2025, 1, 1),
        )


@pytest.mark.unit
def test_error_hierarchy_all_inherit_dataflow_error():
    """spec § 5 — every ML error inherits from DataFlowError."""
    from dataflow.exceptions import DataFlowError
    from dataflow.ml import (
        DataFlowMLIntegrationError,
        DataFlowTransformError,
        FeatureSourceError,
        LineageHashError,
        MLTenantRequiredError,
    )

    for cls in (
        DataFlowMLIntegrationError,
        FeatureSourceError,
        DataFlowTransformError,
        LineageHashError,
        MLTenantRequiredError,
    ):
        assert issubclass(cls, DataFlowError), (
            f"{cls.__name__} must inherit from DataFlowError "
            "(spec § 5) so existing except handlers catch it"
        )


@pytest.mark.unit
def test_hash_same_frame_deterministic_across_calls():
    """Hash MUST be deterministic — same frame produces same hash every call."""
    from dataflow.ml import hash as df_hash

    df = pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    h1 = df_hash(df)
    h2 = df_hash(df)
    h3 = df_hash(df)
    assert h1 == h2 == h3


@pytest.mark.unit
def test_hash_different_dtype_produces_different_hash():
    """spec § 4.3 — column dtype changes affect the hash."""
    from dataflow.ml import hash as df_hash

    df_int = pl.DataFrame({"a": pl.Series([1, 2, 3], dtype=pl.Int64)})
    df_float = pl.DataFrame({"a": pl.Series([1.0, 2.0, 3.0], dtype=pl.Float64)})
    assert df_hash(df_int) != df_hash(df_float)


@pytest.mark.unit
def test_emit_train_start_signature_present():
    """Signature guard: emit_train_start takes (db, context, ...)."""
    from dataflow.ml import emit_train_start

    sig = inspect.signature(emit_train_start)
    params = list(sig.parameters)
    assert params[:2] == ["db", "context"], f"unexpected signature: {sig}"
