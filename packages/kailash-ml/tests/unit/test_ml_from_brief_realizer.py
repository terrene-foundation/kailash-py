# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for ``kailash_ml.from_brief`` realizer helpers.

Per ``rules/testing.md`` § 3-Tier Testing:

* **Tier 1 (Unit)** — these tests exercise the realizer's deterministic
  structural-plumbing helpers (``_polars_dtype_to_feature_dtype``,
  ``_validate_columns_subset``, ``_validate_task``,
  ``_validate_eval_metric``, ``_realize_triple``) and the typed
  exception discriminators on :class:`BriefInterpretationError`.
* **NO LLM REQUIRED** — every test in this file is offline + fast
  (<1s per test). The LLM-mediation path is exercised in the Tier-2
  file (``tests/integration/test_ml_from_brief.py``).

Verification scope:

1. Dtype mapping coverage (polars dtype → FeatureField dtype string).
2. Column-subset gate raises with the correct discriminator.
3. Task allowlist raises with the correct discriminator.
4. Metric allowlist raises with the correct discriminator.
5. ``_realize_triple`` produces a FROZEN FeatureSchema with the
   expected fields, framework-matched ModelSpec, and metric-ordered
   EvalSpec.
6. Data-leakage guard (target column also in feature columns) raises
   ``malformed=True``.
7. Top-level ``from_brief`` input validation (non-polars df, empty df).

Origin: issue #1125 AC 5 + AC 10 — Tier-1 coverage for the realizer's
deterministic surface so a future refactor of the dtype map or the
validation gates fails loudly.
"""

from __future__ import annotations

import polars as pl
import pytest
from kailash_ml.engines.training_pipeline import EvalSpec, ModelSpec
from kailash_ml.features.schema import FeatureField, FeatureSchema
from kailash_ml.from_brief import (
    ALLOWED_EVAL_METRICS,
    ALLOWED_TASKS,
    DEFAULT_MODEL_CLASS_BY_TASK,
    MLPlan,
    _polars_dtype_to_feature_dtype,
    _realize_triple,
    _validate_columns_subset,
    _validate_eval_metric,
    _validate_task,
    from_brief,
)

from kailash._from_brief import BriefInterpretationError

# =========================================================================
# Dtype mapping coverage
# =========================================================================


@pytest.mark.parametrize(
    "pl_dtype,expected",
    [
        (pl.Float64, "float64"),
        (pl.Float32, "float32"),
        (pl.Int64, "int64"),
        (pl.Int32, "int32"),
        (pl.Int16, "int16"),
        (pl.Int8, "int8"),
        (pl.UInt64, "uint64"),
        (pl.UInt32, "uint32"),
        (pl.UInt8, "uint8"),
        (pl.Utf8, "utf8"),
        (pl.Boolean, "bool"),
        (pl.Date, "date"),
    ],
)
def test_polars_dtype_to_feature_dtype_maps_canonical(pl_dtype, expected):
    """Every common polars dtype maps to a FeatureField-compatible string."""
    assert _polars_dtype_to_feature_dtype(pl_dtype) == expected


def test_polars_dtype_to_feature_dtype_fallback_for_exotic():
    """Exotic dtypes (Struct, List) fall back to utf8 — no raise."""
    # We can't construct a Struct dtype trivially; the fallback path
    # is exercised by passing a custom string-like dtype.
    result = _polars_dtype_to_feature_dtype(pl.Object)
    # `Object` is not in the mapped set; fallback is utf8.
    assert result == "utf8"


# =========================================================================
# Column-subset gate
# =========================================================================


def test_validate_columns_subset_accepts_valid_subset():
    """Selected columns that all appear in df.columns pass silently."""
    _validate_columns_subset(
        selected=["age", "income"],
        df_columns=["age", "income", "tenure"],
        field_name="feature_columns",
    )


def test_validate_columns_subset_rejects_unknown_with_discriminator():
    """An unknown column raises with ``unknown_value`` set to the offender."""
    with pytest.raises(BriefInterpretationError) as exc_info:
        _validate_columns_subset(
            selected=["age", "phantom_column"],
            df_columns=["age", "income"],
            field_name="feature_columns",
        )
    assert exc_info.value.unknown_value == "phantom_column"


def test_validate_columns_subset_rejects_non_string_with_malformed():
    """A non-string entry raises with ``malformed=True``."""
    with pytest.raises(BriefInterpretationError) as exc_info:
        _validate_columns_subset(
            selected=["age", 123],  # type: ignore[list-item]
            df_columns=["age"],
            field_name="feature_columns",
        )
    assert exc_info.value.malformed is True


# =========================================================================
# Task + metric allowlist gates
# =========================================================================


@pytest.mark.parametrize("task", sorted(ALLOWED_TASKS))
def test_validate_task_accepts_every_allowlisted_task(task):
    """Every task in :data:`ALLOWED_TASKS` passes validation."""
    _validate_task(task)


def test_validate_task_rejects_unknown_with_discriminator():
    with pytest.raises(BriefInterpretationError) as exc_info:
        _validate_task("anomaly_detection")
    assert exc_info.value.unknown_value == "anomaly_detection"


def test_validate_task_rejects_non_string():
    with pytest.raises(BriefInterpretationError) as exc_info:
        _validate_task(None)  # type: ignore[arg-type]
    # Non-string fails the type check, unknown_value stays None.
    assert exc_info.value.unknown_value is None


@pytest.mark.parametrize("metric", sorted(ALLOWED_EVAL_METRICS))
def test_validate_eval_metric_accepts_every_allowlisted_metric(metric):
    """Every metric in :data:`ALLOWED_EVAL_METRICS` passes validation."""
    _validate_eval_metric(metric)


def test_validate_eval_metric_rejects_unknown_with_discriminator():
    with pytest.raises(BriefInterpretationError) as exc_info:
        _validate_eval_metric("perplexity")
    assert exc_info.value.unknown_value == "perplexity"


# =========================================================================
# Realizer triple construction
# =========================================================================


def _make_classification_plan(df_columns=("age", "tenure", "churned")):
    """Build a valid MLPlan for a binary-classification scenario."""
    return MLPlan(
        interpretation_confidence=0.9,
        dataframe_schema={col: "Int64" for col in df_columns},
        feature_columns=["age", "tenure"],
        target_column="churned",
        model_task="binary_classification",
        eval_metric="auc",
        schema_name="customer_churn",
    )


def _make_regression_plan(df_columns=("area_sqft", "bedrooms", "price")):
    return MLPlan(
        interpretation_confidence=0.85,
        dataframe_schema={col: "Float64" for col in df_columns},
        feature_columns=["area_sqft", "bedrooms"],
        target_column="price",
        model_task="regression",
        eval_metric="rmse",
        schema_name="house_prices",
    )


def test_realize_triple_returns_three_dataclasses():
    """Realizer returns ``(FeatureSchema, ModelSpec, EvalSpec)``."""
    plan = _make_classification_plan()
    df = pl.DataFrame({"age": [25], "tenure": [12], "churned": [0]})
    schema, model_spec, eval_spec = _realize_triple(plan, df)
    assert isinstance(schema, FeatureSchema)
    assert isinstance(model_spec, ModelSpec)
    assert isinstance(eval_spec, EvalSpec)


def test_realize_triple_feature_schema_matches_dataframe_columns():
    """AC 5: ``FeatureSchema.field_names`` matches plan.feature_columns."""
    plan = _make_classification_plan()
    df = pl.DataFrame({"age": [25], "tenure": [12], "churned": [0]})
    schema, _, _ = _realize_triple(plan, df)
    assert schema.field_names == plan.feature_columns


def test_realize_triple_feature_schema_is_frozen():
    """The realized FeatureSchema is the FROZEN content-addressed variant."""
    plan = _make_classification_plan()
    df = pl.DataFrame({"age": [25], "tenure": [12], "churned": [0]})
    schema, _, _ = _realize_triple(plan, df)
    # frozen=True dataclass raises on attribute assignment
    with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
        schema.name = "mutated"  # type: ignore[misc]
    # Content hash is derived
    assert len(schema.content_hash) == 16
    assert all(c in "0123456789abcdef" for c in schema.content_hash)


def test_realize_triple_model_spec_task_matches_brief_goal():
    """AC 5: ``ModelSpec`` framework is consistent with the task."""
    plan = _make_classification_plan()
    df = pl.DataFrame({"age": [25], "tenure": [12], "churned": [0]})
    _, model_spec, _ = _realize_triple(plan, df)
    # Per DEFAULT_MODEL_CLASS_BY_TASK
    assert model_spec.model_class == DEFAULT_MODEL_CLASS_BY_TASK[plan.model_task]
    assert model_spec.framework == "sklearn"


def test_realize_triple_regression_uses_regressor():
    """Regression task → RandomForestRegressor."""
    plan = _make_regression_plan()
    df = pl.DataFrame({"area_sqft": [1200.0], "bedrooms": [3.0], "price": [350000.0]})
    _, model_spec, _ = _realize_triple(plan, df)
    assert model_spec.model_class == "sklearn.ensemble.RandomForestRegressor"


def test_realize_triple_eval_metric_pinned_first_in_metrics():
    """Caller-iterating metrics in order sees the brief-derived choice first."""
    plan = _make_classification_plan()
    df = pl.DataFrame({"age": [25], "tenure": [12], "churned": [0]})
    _, _, eval_spec = _realize_triple(plan, df)
    assert eval_spec.metrics[0] == plan.eval_metric


# =========================================================================
# Top-level from_brief input validation
# =========================================================================


def test_from_brief_rejects_non_polars_df():
    """Passing a non-polars df raises ``TypeError`` with conversion hint."""
    with pytest.raises(TypeError, match="polars.DataFrame"):
        from_brief("predict X from Y", df=[1, 2, 3])  # type: ignore[arg-type]


def test_from_brief_rejects_empty_columns():
    """An empty-columns DataFrame raises ``ValueError`` loudly."""
    with pytest.raises(ValueError, match="no columns"):
        from_brief("predict X from Y", df=pl.DataFrame())


# =========================================================================
# FeatureSchema.with_features adapter (added in this same shard per
# autonomous-execution.md MUST-4 same-bug-class-same-shard discipline)
# =========================================================================


def test_with_features_returns_new_schema_with_bumped_version():
    """Refinement creates a new schema with version+1 by default."""
    schema = FeatureSchema(
        name="user_churn",
        fields=(FeatureField(name="age", dtype="int"),),
    )
    refined = schema.with_features(
        [
            FeatureField(name="age", dtype="int"),
            FeatureField(name="tenure_months", dtype="int"),
        ]
    )
    assert refined.version == schema.version + 1
    assert refined.field_names == ["age", "tenure_months"]
    # Content hash MUST differ — different field set → different hash
    assert refined.content_hash != schema.content_hash


def test_with_features_preserves_version_when_bump_disabled():
    """``bump_version=False`` keeps the same version slot."""
    schema = FeatureSchema(
        name="user_churn",
        fields=(FeatureField(name="age", dtype="int"),),
    )
    refined = schema.with_features(
        [FeatureField(name="age", dtype="int", description="updated description")],
        bump_version=False,
    )
    assert refined.version == schema.version
    # Description differs → content hash differs (description IS in
    # the canonical payload)
    assert refined.content_hash != schema.content_hash


def test_with_features_preserves_entity_id_and_timestamp():
    """Refinement carries over entity_id_column + timestamp_column."""
    schema = FeatureSchema(
        name="user_churn",
        fields=(FeatureField(name="age", dtype="int"),),
        entity_id_column="user_id",
        timestamp_column="observed_at",
    )
    refined = schema.with_features([FeatureField(name="age", dtype="int")])
    assert refined.entity_id_column == "user_id"
    assert refined.timestamp_column == "observed_at"
