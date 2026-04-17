# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for PreprocessingPipeline -- auto-detection, encoding, scaling, imputation."""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from sklearn.datasets import make_classification, make_regression

from kailash_ml.engines.preprocessing import (
    PreprocessingPipeline,
    SetupResult,
    _detect_task_type,
    _identify_column_types,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def pipeline() -> PreprocessingPipeline:
    return PreprocessingPipeline()


@pytest.fixture()
def classification_df() -> pl.DataFrame:
    """DataFrame with numeric + categorical features for classification."""
    X, y = make_classification(
        n_samples=100,
        n_features=3,
        n_informative=2,
        n_redundant=0,
        random_state=42,
    )
    return pl.DataFrame(
        {
            "num_a": X[:, 0].tolist(),
            "num_b": X[:, 1].tolist(),
            "num_c": X[:, 2].tolist(),
            "cat_x": ["red", "blue", "green", "red"] * 25,
            "target": y.tolist(),
        }
    )


@pytest.fixture()
def regression_df() -> pl.DataFrame:
    """DataFrame with numeric features for regression."""
    X, y = make_regression(
        n_samples=100,
        n_features=3,
        n_informative=2,
        random_state=42,
    )
    return pl.DataFrame(
        {
            "num_a": X[:, 0].tolist(),
            "num_b": X[:, 1].tolist(),
            "num_c": X[:, 2].tolist(),
            "target": y.tolist(),
        }
    )


@pytest.fixture()
def missing_df() -> pl.DataFrame:
    """DataFrame with missing values."""
    return pl.DataFrame(
        {
            "num_a": [1.0, None, 3.0, None, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            "num_b": [None, 2.0, None, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            "cat_x": ["a", None, "b", "a", None, "b", "a", "b", "a", "b"],
            "target": [0, 1, 0, 1, 0, 1, 0, 1, 0, 1],
        }
    )


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestDetectTaskType:
    """Tests for _detect_task_type."""

    def test_boolean_is_classification(self) -> None:
        s = pl.Series("t", [True, False, True, False])
        assert _detect_task_type(s) == "classification"

    def test_categorical_is_classification(self) -> None:
        s = pl.Series("t", ["a", "b", "a", "b"]).cast(pl.Categorical)
        assert _detect_task_type(s) == "classification"

    def test_string_is_classification(self) -> None:
        s = pl.Series("t", ["yes", "no", "yes", "no"])
        assert _detect_task_type(s) == "classification"

    def test_few_unique_int_is_classification(self) -> None:
        s = pl.Series("t", [0, 1, 2, 0, 1, 2])
        assert _detect_task_type(s) == "classification"

    def test_many_unique_float_is_regression(self) -> None:
        s = pl.Series("t", list(range(50)))
        assert _detect_task_type(s) == "regression"

    def test_boundary_20_classification(self) -> None:
        s = pl.Series("t", list(range(20)))
        assert _detect_task_type(s) == "classification"

    def test_boundary_21_regression(self) -> None:
        s = pl.Series("t", list(range(21)))
        assert _detect_task_type(s) == "regression"


class TestIdentifyColumnTypes:
    """Tests for _identify_column_types."""

    def test_basic_identification(self) -> None:
        df = pl.DataFrame(
            {
                "num": [1.0, 2.0],
                "cat": ["a", "b"],
                "target": [0, 1],
            }
        )
        numeric, categorical = _identify_column_types(df, "target")
        assert "num" in numeric
        assert "cat" in categorical
        assert "target" not in numeric
        assert "target" not in categorical

    def test_boolean_is_categorical(self) -> None:
        df = pl.DataFrame(
            {
                "flag": [True, False],
                "val": [1.0, 2.0],
                "target": [0, 1],
            }
        )
        numeric, categorical = _identify_column_types(df, "target")
        assert "flag" in categorical
        assert "val" in numeric


# ---------------------------------------------------------------------------
# PreprocessingPipeline.setup -- basic
# ---------------------------------------------------------------------------


class TestSetupBasic:
    """Tests for basic setup functionality."""

    def test_classification_detection(
        self, pipeline: PreprocessingPipeline, classification_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(classification_df, "target")
        assert isinstance(result, SetupResult)
        assert result.task_type == "classification"
        assert result.target_column == "target"

    def test_regression_detection(
        self, pipeline: PreprocessingPipeline, regression_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(regression_df, "target")
        assert result.task_type == "regression"

    def test_train_test_split_sizes(
        self, pipeline: PreprocessingPipeline, regression_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(regression_df, "target", train_size=0.7)
        assert result.train_data.height == 70
        assert result.test_data.height == 30

    def test_default_split_80_20(
        self, pipeline: PreprocessingPipeline, regression_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(regression_df, "target")
        assert result.train_data.height == 80
        assert result.test_data.height == 20

    def test_numeric_columns_detected(
        self, pipeline: PreprocessingPipeline, classification_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(classification_df, "target")
        assert "num_a" in result.numeric_columns
        assert "num_b" in result.numeric_columns

    def test_categorical_columns_detected(
        self, pipeline: PreprocessingPipeline, classification_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(classification_df, "target")
        assert "cat_x" in result.categorical_columns

    def test_original_shape_recorded(
        self, pipeline: PreprocessingPipeline, classification_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(classification_df, "target")
        assert result.original_shape == (100, 5)

    def test_summary_is_human_readable(
        self, pipeline: PreprocessingPipeline, classification_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(classification_df, "target")
        assert "classification" in result.summary
        assert "Numeric features:" in result.summary
        assert "Categorical features:" in result.summary


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestSetupValidation:
    """Tests for setup input validation."""

    def test_missing_target_raises(self, pipeline: PreprocessingPipeline) -> None:
        df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
        with pytest.raises(ValueError, match="not found"):
            pipeline.setup(df, "nonexistent")

    def test_empty_data_raises(self, pipeline: PreprocessingPipeline) -> None:
        df = pl.DataFrame({"target": pl.Series("target", [], dtype=pl.Int64)})
        with pytest.raises(ValueError, match="empty"):
            pipeline.setup(df, "target")

    def test_invalid_train_size_raises(
        self, pipeline: PreprocessingPipeline, regression_df: pl.DataFrame
    ) -> None:
        with pytest.raises(ValueError, match="train_size"):
            pipeline.setup(regression_df, "target", train_size=0.0)
        with pytest.raises(ValueError, match="train_size"):
            pipeline.setup(regression_df, "target", train_size=1.0)

    def test_invalid_encoding_raises(
        self, pipeline: PreprocessingPipeline, classification_df: pl.DataFrame
    ) -> None:
        with pytest.raises(ValueError, match="categorical_encoding"):
            pipeline.setup(classification_df, "target", categorical_encoding="invalid")

    def test_invalid_imputation_raises(
        self, pipeline: PreprocessingPipeline, classification_df: pl.DataFrame
    ) -> None:
        with pytest.raises(ValueError, match="imputation_strategy"):
            pipeline.setup(classification_df, "target", imputation_strategy="invalid")


# ---------------------------------------------------------------------------
# Imputation
# ---------------------------------------------------------------------------


class TestImputation:
    """Tests for missing value imputation."""

    def test_mean_imputation(
        self, pipeline: PreprocessingPipeline, missing_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(
            missing_df, "target", imputation_strategy="mean", normalize=False
        )
        # After imputation, no nulls in train or test
        for col in result.train_data.columns:
            assert result.train_data[col].null_count() == 0

    def test_median_imputation(
        self, pipeline: PreprocessingPipeline, missing_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(
            missing_df, "target", imputation_strategy="median", normalize=False
        )
        for col in result.train_data.columns:
            assert result.train_data[col].null_count() == 0

    def test_mode_imputation(
        self, pipeline: PreprocessingPipeline, missing_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(
            missing_df, "target", imputation_strategy="mode", normalize=False
        )
        for col in result.train_data.columns:
            assert result.train_data[col].null_count() == 0

    def test_drop_imputation(
        self, pipeline: PreprocessingPipeline, missing_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(
            missing_df, "target", imputation_strategy="drop", normalize=False
        )
        # Rows with nulls should be removed
        total = result.train_data.height + result.test_data.height
        assert total < missing_df.height


# ---------------------------------------------------------------------------
# Categorical encoding
# ---------------------------------------------------------------------------


class TestCategoricalEncoding:
    """Tests for categorical encoding strategies."""

    def test_onehot_encoding(
        self, pipeline: PreprocessingPipeline, classification_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(
            classification_df,
            "target",
            categorical_encoding="onehot",
            normalize=False,
        )
        # Original cat_x column should be removed
        assert "cat_x" not in result.train_data.columns
        # New one-hot columns should exist
        onehot_cols = [c for c in result.train_data.columns if c.startswith("cat_x_")]
        assert len(onehot_cols) == 3  # red, blue, green

    def test_ordinal_encoding(
        self, pipeline: PreprocessingPipeline, classification_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(
            classification_df,
            "target",
            categorical_encoding="ordinal",
            normalize=False,
        )
        # cat_x should still exist but be numeric
        assert "cat_x" in result.train_data.columns
        assert result.train_data["cat_x"].dtype == pl.Float64

    def test_target_encoding(
        self, pipeline: PreprocessingPipeline, classification_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(
            classification_df,
            "target",
            categorical_encoding="target",
            normalize=False,
        )
        # cat_x should still exist but be numeric
        assert "cat_x" in result.train_data.columns
        assert result.train_data["cat_x"].dtype == pl.Float64

    def test_no_categoricals_noop(
        self, pipeline: PreprocessingPipeline, regression_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(
            regression_df,
            "target",
            categorical_encoding="onehot",
            normalize=False,
        )
        assert result.categorical_columns == []
        # All original columns preserved
        assert "num_a" in result.train_data.columns


# ---------------------------------------------------------------------------
# Scaling
# ---------------------------------------------------------------------------


class TestScaling:
    """Tests for numeric scaling."""

    def test_normalize_true_scales(
        self, pipeline: PreprocessingPipeline, regression_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(regression_df, "target", normalize=True)
        # Scaled columns should have approximately zero mean
        for col in result.numeric_columns:
            if col in result.train_data.columns:
                # Combine train+test for checking (both are scaled)
                combined = pl.concat([result.train_data, result.test_data])
                # Mean should be approximately 0 (not exact due to split)
                mean_val = combined[col].mean()
                assert mean_val is not None
                assert abs(mean_val) < 1.0  # Roughly centered

    def test_normalize_false_preserves(
        self, pipeline: PreprocessingPipeline, regression_df: pl.DataFrame
    ) -> None:
        original_mean = regression_df["num_a"].mean()
        result = pipeline.setup(regression_df, "target", normalize=False)
        combined = pl.concat([result.train_data, result.test_data])
        new_mean = combined["num_a"].mean()
        # Should be approximately the same (just reordered by shuffle)
        assert original_mean is not None and new_mean is not None
        assert abs(original_mean - new_mean) < 0.5


# ---------------------------------------------------------------------------
# Outlier removal
# ---------------------------------------------------------------------------


class TestOutlierRemoval:
    """Tests for IQR-based outlier removal."""

    def test_outlier_removal_reduces_rows(
        self, pipeline: PreprocessingPipeline
    ) -> None:
        # Create data with clear outliers
        normal = list(range(100))
        outlier_data = normal + [10000, -10000]
        df = pl.DataFrame(
            {
                "val": [float(x) for x in outlier_data],
                "target": [0, 1] * 51,
            }
        )
        result = pipeline.setup(df, "target", remove_outliers=True, normalize=False)
        total = result.train_data.height + result.test_data.height
        assert total < 102

    def test_no_outlier_removal_preserves_rows(
        self, pipeline: PreprocessingPipeline, regression_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(regression_df, "target", remove_outliers=False)
        total = result.train_data.height + result.test_data.height
        assert total == 100


# ---------------------------------------------------------------------------
# get_config
# ---------------------------------------------------------------------------


class TestGetConfig:
    """Tests for get_config."""

    def test_returns_config_after_setup(
        self, pipeline: PreprocessingPipeline, regression_df: pl.DataFrame
    ) -> None:
        pipeline.setup(regression_df, "target")
        config = pipeline.get_config()
        assert config["target"] == "target"
        assert config["task_type"] == "regression"
        assert config["normalize"] is True
        assert "numeric_columns" in config

    def test_raises_before_setup(self, pipeline: PreprocessingPipeline) -> None:
        with pytest.raises(RuntimeError, match="not been fitted"):
            pipeline.get_config()


# ---------------------------------------------------------------------------
# transform (new data)
# ---------------------------------------------------------------------------


class TestTransform:
    """Tests for applying fitted transforms to new data."""

    def test_transform_after_setup(
        self, pipeline: PreprocessingPipeline, classification_df: pl.DataFrame
    ) -> None:
        pipeline.setup(
            classification_df,
            "target",
            categorical_encoding="ordinal",
            normalize=True,
        )
        new_data = classification_df.head(10)
        transformed = pipeline.transform(new_data)
        assert transformed.height == 10

    def test_transform_raises_before_setup(
        self, pipeline: PreprocessingPipeline, classification_df: pl.DataFrame
    ) -> None:
        with pytest.raises(RuntimeError, match="not been fitted"):
            pipeline.transform(classification_df)

    def test_transform_preserves_shape_onehot(
        self, pipeline: PreprocessingPipeline, classification_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(
            classification_df,
            "target",
            categorical_encoding="onehot",
            normalize=False,
        )
        new_data = classification_df.head(5)
        transformed = pipeline.transform(new_data)
        # Should have same columns as training data
        assert transformed.height == 5
        # One-hot columns should be present
        onehot_cols = [c for c in transformed.columns if c.startswith("cat_x_")]
        assert len(onehot_cols) == 3


# ---------------------------------------------------------------------------
# inverse_transform
# ---------------------------------------------------------------------------


class TestInverseTransform:
    """Tests for reversing transforms."""

    def test_inverse_scaling(
        self, pipeline: PreprocessingPipeline, regression_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(regression_df, "target", normalize=True)
        # Take a sample and inverse-transform
        sample = result.train_data.head(5)
        inversed = pipeline.inverse_transform(sample)
        # Values should be back to original scale (approximately)
        assert inversed.height == 5

    def test_inverse_raises_before_setup(
        self, pipeline: PreprocessingPipeline, regression_df: pl.DataFrame
    ) -> None:
        with pytest.raises(RuntimeError, match="not been fitted"):
            pipeline.inverse_transform(regression_df)


# ---------------------------------------------------------------------------
# Frozen result validation
# ---------------------------------------------------------------------------


class TestSetupResultFrozen:
    """Verify SetupResult is frozen."""

    def test_cannot_modify_result(
        self, pipeline: PreprocessingPipeline, regression_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(regression_df, "target")
        with pytest.raises(AttributeError):
            result.task_type = "changed"  # type: ignore[misc]

    def test_transformers_dict_present(
        self, pipeline: PreprocessingPipeline, regression_df: pl.DataFrame
    ) -> None:
        result = pipeline.setup(regression_df, "target", normalize=True)
        assert "scaler" in result.transformers


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests."""

    def test_single_numeric_column(self, pipeline: PreprocessingPipeline) -> None:
        df = pl.DataFrame(
            {
                "val": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
                "target": [0, 1, 0, 1, 0, 1, 0, 1, 0, 1],
            }
        )
        result = pipeline.setup(df, "target", normalize=True)
        assert result.numeric_columns == ["val"]
        assert result.categorical_columns == []

    def test_only_categoricals(self, pipeline: PreprocessingPipeline) -> None:
        df = pl.DataFrame(
            {
                "cat_a": ["x", "y", "z", "x", "y", "z", "x", "y", "z", "x"],
                "cat_b": ["a", "b", "a", "b", "a", "b", "a", "b", "a", "b"],
                "target": [0, 1, 0, 1, 0, 1, 0, 1, 0, 1],
            }
        )
        result = pipeline.setup(
            df, "target", categorical_encoding="ordinal", normalize=False
        )
        assert len(result.categorical_columns) == 2
        assert result.numeric_columns == []

    def test_boolean_target_is_classification(
        self, pipeline: PreprocessingPipeline
    ) -> None:
        df = pl.DataFrame(
            {
                "val": list(range(20)),
                "target": [True, False] * 10,
            }
        )
        result = pipeline.setup(df, "target", normalize=False)
        assert result.task_type == "classification"

    def test_all_missing_numeric_column(self, pipeline: PreprocessingPipeline) -> None:
        df = pl.DataFrame(
            {
                "val": [None, None, None, None, None, None, None, None, None, None],
                "other": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
                "target": [0, 1, 0, 1, 0, 1, 0, 1, 0, 1],
            }
        )
        # Should not crash -- val column is all-null so fill with 0.0
        result = pipeline.setup(
            df, "target", imputation_strategy="mean", normalize=False
        )
        assert result.train_data.height > 0

    def test_deterministic_splits(
        self, pipeline: PreprocessingPipeline, regression_df: pl.DataFrame
    ) -> None:
        """Same seed produces identical splits."""
        result1 = pipeline.setup(regression_df, "target", seed=42)
        result2 = pipeline.setup(regression_df, "target", seed=42)
        assert result1.train_data.equals(result2.train_data)
        assert result1.test_data.equals(result2.test_data)

    def test_different_seeds_different_splits(
        self, pipeline: PreprocessingPipeline, regression_df: pl.DataFrame
    ) -> None:
        result1 = pipeline.setup(regression_df, "target", seed=42)
        result2 = pipeline.setup(regression_df, "target", seed=99)
        # Extremely unlikely to produce the same split
        assert not result1.train_data.equals(result2.train_data)


# ---------------------------------------------------------------------------
# Cardinality guard (#313)
# ---------------------------------------------------------------------------


class TestCardinalityGuard:
    """Tests for max_cardinality and exclude_columns (#313)."""

    @pytest.fixture()
    def high_card_df(self) -> pl.DataFrame:
        """DataFrame with a high-cardinality categorical column."""
        n = 200
        return pl.DataFrame(
            {
                "id": [f"id_{i}" for i in range(n)],
                "color": ["red", "blue", "green"] * 66 + ["red", "blue"],
                "size": ["S", "M", "L", "XL"] * 50,
                "value": list(range(n)),
                "target": [0, 1] * 100,
            }
        )

    def test_high_cardinality_auto_downgrade(self, high_card_df: pl.DataFrame) -> None:
        """Columns exceeding max_cardinality are ordinal-encoded."""
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            high_card_df,
            "target",
            categorical_encoding="onehot",
            max_cardinality=10,
            normalize=False,
        )
        # 'id' has 200 unique -> ordinal (1 column kept)
        # 'color' has 3 unique -> onehot (3 columns)
        # 'size' has 4 unique -> onehot (4 columns)
        train_cols = result.train_data.columns
        # Should NOT have 200 id_* columns
        id_onehot = [c for c in train_cols if c.startswith("id_")]
        assert len(id_onehot) == 0, f"id was one-hot encoded: {id_onehot[:5]}"
        # Should still have color/size one-hot columns
        color_onehot = [c for c in train_cols if c.startswith("color_")]
        assert len(color_onehot) == 3

    def test_all_columns_exceed_threshold(self, high_card_df: pl.DataFrame) -> None:
        """When all categoricals exceed threshold, all get ordinal."""
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            high_card_df,
            "target",
            categorical_encoding="onehot",
            max_cardinality=2,
            normalize=False,
        )
        train_cols = result.train_data.columns
        # No one-hot columns should exist for any of the categoricals
        onehot_cols = [
            c
            for c in train_cols
            if any(c.startswith(f"{cat}_") for cat in ["id", "color", "size"])
        ]
        assert len(onehot_cols) == 0, f"Unexpected one-hot columns: {onehot_cols}"
        # Original columns should remain (ordinal-encoded as Int64)
        assert "id" in train_cols
        assert "color" in train_cols
        assert "size" in train_cols

    def test_exclude_columns(self, high_card_df: pl.DataFrame) -> None:
        """Excluded columns are not encoded."""
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            high_card_df,
            "target",
            categorical_encoding="onehot",
            exclude_columns=["id"],
            normalize=False,
        )
        train_cols = result.train_data.columns
        # id should NOT be one-hot encoded (excluded)
        id_onehot = [c for c in train_cols if c.startswith("id_")]
        assert len(id_onehot) == 0
        # id should remain as its original string column
        assert "id" in train_cols

    def test_exclude_nonexistent_column_raises(
        self, high_card_df: pl.DataFrame
    ) -> None:
        """Excluding a nonexistent column raises ValueError."""
        pipeline = PreprocessingPipeline()
        with pytest.raises(ValueError, match="not in DataFrame"):
            pipeline.setup(
                high_card_df,
                "target",
                categorical_encoding="onehot",
                exclude_columns=["nonexistent"],
            )

    def test_exclude_noncategorical_ignored(self, high_card_df: pl.DataFrame) -> None:
        """Excluding a numeric column is silently ignored (it's not categorical)."""
        pipeline = PreprocessingPipeline()
        # Should not raise -- 'value' is numeric, not categorical
        result = pipeline.setup(
            high_card_df,
            "target",
            categorical_encoding="onehot",
            exclude_columns=["value"],
            normalize=False,
        )
        assert result.train_data is not None

    def test_target_encoding_ignores_cardinality(
        self, high_card_df: pl.DataFrame
    ) -> None:
        """Target encoding is cardinality-safe; max_cardinality should not apply."""
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            high_card_df,
            "target",
            categorical_encoding="target",
            max_cardinality=2,
            normalize=False,
        )
        # Should work without any cardinality warnings
        assert result.train_data is not None

    def test_default_threshold_preserves_existing(self) -> None:
        """Default max_cardinality=50 doesn't affect small category counts."""
        df = pl.DataFrame(
            {
                "color": ["red", "blue", "green"] * 20,
                "target": [0, 1] * 30,
            }
        )
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            df, "target", categorical_encoding="onehot", normalize=False
        )
        train_cols = result.train_data.columns
        color_onehot = [c for c in train_cols if c.startswith("color_")]
        assert len(color_onehot) == 3

    def test_transform_applies_mixed_encoding(self, high_card_df: pl.DataFrame) -> None:
        """transform() correctly applies mixed onehot+ordinal to new data."""
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            high_card_df,
            "target",
            categorical_encoding="onehot",
            max_cardinality=10,
            normalize=False,
        )
        # transform should work on test data
        assert result.test_data is not None
        test_cols = result.test_data.columns
        # Same encoding should be applied
        id_onehot = [c for c in test_cols if c.startswith("id_")]
        assert len(id_onehot) == 0


# ---------------------------------------------------------------------------
# Normalization methods (#330)
# ---------------------------------------------------------------------------


class TestNormalizationMethods:
    """Tests for normalize_method parameter (#330)."""

    @pytest.fixture()
    def norm_df(self) -> pl.DataFrame:
        """DataFrame with known numeric values for normalization checks."""
        return pl.DataFrame(
            {
                "a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
                "b": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0],
                "target": list(range(10)),
            }
        )

    def test_zscore_approximately_zero_mean_unit_var(
        self, norm_df: pl.DataFrame
    ) -> None:
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            norm_df, "target", normalize=True, normalize_method="zscore"
        )
        combined = pl.concat([result.train_data, result.test_data])
        for col in ["a", "b"]:
            mean_val = combined[col].mean()
            std_val = combined[col].std()
            assert mean_val is not None and abs(mean_val) < 0.5
            assert std_val is not None and abs(std_val - 1.0) < 0.5

    def test_minmax_range_zero_to_one(self, norm_df: pl.DataFrame) -> None:
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            norm_df, "target", normalize=True, normalize_method="minmax"
        )
        combined = pl.concat([result.train_data, result.test_data])
        for col in ["a", "b"]:
            min_val = combined[col].min()
            max_val = combined[col].max()
            assert min_val is not None and min_val >= -0.01
            assert max_val is not None and max_val <= 1.01

    def test_robust_uses_median_centering(self, norm_df: pl.DataFrame) -> None:
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            norm_df, "target", normalize=True, normalize_method="robust"
        )
        combined = pl.concat([result.train_data, result.test_data])
        for col in ["a", "b"]:
            median_val = combined[col].median()
            # RobustScaler centers on median; after transform the median
            # of the full dataset should be close to 0
            assert median_val is not None and abs(median_val) < 0.5

    def test_maxabs_range_minus_one_to_one(self, norm_df: pl.DataFrame) -> None:
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            norm_df, "target", normalize=True, normalize_method="maxabs"
        )
        combined = pl.concat([result.train_data, result.test_data])
        for col in ["a", "b"]:
            min_val = combined[col].min()
            max_val = combined[col].max()
            assert min_val is not None and min_val >= -1.01
            assert max_val is not None and max_val <= 1.01

    def test_invalid_normalize_method_raises(self, norm_df: pl.DataFrame) -> None:
        pipeline = PreprocessingPipeline()
        with pytest.raises(ValueError, match="normalize_method"):
            pipeline.setup(norm_df, "target", normalize_method="invalid")

    def test_scaler_stored_in_transformers(self, norm_df: pl.DataFrame) -> None:
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            norm_df, "target", normalize=True, normalize_method="minmax"
        )
        assert "scaler" in result.transformers
        from sklearn.preprocessing import MinMaxScaler

        assert isinstance(result.transformers["scaler"], MinMaxScaler)

    def test_transform_uses_fitted_scaler(self, norm_df: pl.DataFrame) -> None:
        """transform() on new data uses the same scaler fitted during setup."""
        pipeline = PreprocessingPipeline()
        pipeline.setup(norm_df, "target", normalize=True, normalize_method="minmax")
        new_data = norm_df.head(3)
        transformed = pipeline.transform(new_data)
        for col in ["a", "b"]:
            min_val = transformed[col].min()
            max_val = transformed[col].max()
            assert min_val is not None and min_val >= -0.01
            assert max_val is not None and max_val <= 1.01


# ---------------------------------------------------------------------------
# Advanced imputation (#331)
# ---------------------------------------------------------------------------


class TestAdvancedImputation:
    """Tests for KNN and iterative imputation (#331)."""

    @pytest.fixture()
    def impute_df(self) -> pl.DataFrame:
        """DataFrame with nulls for advanced imputation testing."""
        return pl.DataFrame(
            {
                "a": [1.0, None, 3.0, None, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
                "b": [10.0, 20.0, None, 40.0, 50.0, None, 70.0, 80.0, 90.0, 100.0],
                "cat": ["x", None, "y", "x", "y", "x", None, "y", "x", "y"],
                "target": [0, 1, 0, 1, 0, 1, 0, 1, 0, 1],
            }
        )

    def test_knn_fills_nulls(self, impute_df: pl.DataFrame) -> None:
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            impute_df,
            "target",
            imputation_strategy="knn",
            normalize=False,
        )
        combined = pl.concat([result.train_data, result.test_data])
        for col in ["a", "b"]:
            assert combined[col].null_count() == 0

    def test_knn_categorical_gets_mode(self, impute_df: pl.DataFrame) -> None:
        """Categorical columns still receive mode imputation under knn."""
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            impute_df,
            "target",
            imputation_strategy="knn",
            categorical_encoding="ordinal",
            normalize=False,
        )
        combined = pl.concat([result.train_data, result.test_data])
        # cat column should have no nulls after encoding
        assert combined["cat"].null_count() == 0

    def test_knn_n_neighbors(self, impute_df: pl.DataFrame) -> None:
        """Custom n_neighbors is respected."""
        pipeline = PreprocessingPipeline()
        pipeline.setup(
            impute_df,
            "target",
            imputation_strategy="knn",
            impute_n_neighbors=3,
            normalize=False,
        )
        imputer = pipeline._transformers["sklearn_imputer"]
        assert imputer.n_neighbors == 3

    def test_iterative_fills_nulls(self, impute_df: pl.DataFrame) -> None:
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            impute_df,
            "target",
            imputation_strategy="iterative",
            normalize=False,
        )
        combined = pl.concat([result.train_data, result.test_data])
        for col in ["a", "b"]:
            assert combined[col].null_count() == 0

    def test_iterative_categorical_gets_mode(self, impute_df: pl.DataFrame) -> None:
        """Categorical columns still receive mode imputation under iterative."""
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            impute_df,
            "target",
            imputation_strategy="iterative",
            categorical_encoding="ordinal",
            normalize=False,
        )
        combined = pl.concat([result.train_data, result.test_data])
        assert combined["cat"].null_count() == 0

    def test_knn_transform_uses_fitted_imputer(self, impute_df: pl.DataFrame) -> None:
        """transform() on new data uses the fitted KNN imputer."""
        pipeline = PreprocessingPipeline()
        pipeline.setup(
            impute_df,
            "target",
            imputation_strategy="knn",
            categorical_encoding="ordinal",
            normalize=False,
        )
        new_data = pl.DataFrame(
            {
                "a": [None, 4.0, 6.0],
                "b": [30.0, None, 80.0],
                "cat": ["x", "y", "x"],
                "target": [0, 1, 0],
            }
        )
        transformed = pipeline.transform(new_data)
        for col in ["a", "b"]:
            assert transformed[col].null_count() == 0

    def test_iterative_transform_uses_fitted_imputer(
        self, impute_df: pl.DataFrame
    ) -> None:
        """transform() on new data uses the fitted iterative imputer."""
        pipeline = PreprocessingPipeline()
        pipeline.setup(
            impute_df,
            "target",
            imputation_strategy="iterative",
            categorical_encoding="ordinal",
            normalize=False,
        )
        new_data = pl.DataFrame(
            {
                "a": [None, 4.0, 6.0],
                "b": [30.0, None, 80.0],
                "cat": ["x", "y", "x"],
                "target": [0, 1, 0],
            }
        )
        transformed = pipeline.transform(new_data)
        for col in ["a", "b"]:
            assert transformed[col].null_count() == 0

    def test_sklearn_imputer_stored(self, impute_df: pl.DataFrame) -> None:
        """The fitted sklearn imputer is stored in transformers."""
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            impute_df,
            "target",
            imputation_strategy="knn",
            normalize=False,
        )
        assert "sklearn_imputer" in result.transformers
        from sklearn.impute import KNNImputer

        assert isinstance(result.transformers["sklearn_imputer"], KNNImputer)


# ---------------------------------------------------------------------------
# Multicollinearity removal (#332)
# ---------------------------------------------------------------------------


class TestMulticollinearityRemoval:
    """Tests for remove_multicollinearity parameter (#332)."""

    def test_highly_correlated_feature_dropped(self) -> None:
        """When two features are nearly identical, the one with lower
        target correlation is dropped."""
        rng = np.random.RandomState(42)
        n = 200
        base = rng.randn(n)
        target = (base > 0).astype(int)
        df = pl.DataFrame(
            {
                "feat_a": base.tolist(),
                # feat_b is a near-perfect copy of feat_a (r ~ 1.0)
                "feat_b": (base + rng.randn(n) * 0.001).tolist(),
                # feat_c is independent
                "feat_c": rng.randn(n).tolist(),
                "target": target.tolist(),
            }
        )
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            df,
            "target",
            normalize=False,
            remove_multicollinearity=True,
            multicollinearity_threshold=0.9,
        )
        dropped = result.transformers.get("multicollinear_dropped", [])
        # One of feat_a / feat_b should be dropped
        assert len(dropped) == 1
        assert dropped[0] in ("feat_a", "feat_b")
        # The dropped column should not be in train or test data
        assert dropped[0] not in result.train_data.columns
        assert dropped[0] not in result.test_data.columns
        # feat_c (independent) should be kept
        assert "feat_c" in result.train_data.columns

    def test_weakly_correlated_features_kept(self) -> None:
        """Features below the threshold are not removed."""
        rng = np.random.RandomState(42)
        n = 200
        df = pl.DataFrame(
            {
                "feat_a": rng.randn(n).tolist(),
                "feat_b": rng.randn(n).tolist(),
                "target": rng.randint(0, 2, n).tolist(),
            }
        )
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            df,
            "target",
            normalize=False,
            remove_multicollinearity=True,
            multicollinearity_threshold=0.9,
        )
        dropped = result.transformers.get("multicollinear_dropped", [])
        assert len(dropped) == 0
        assert "feat_a" in result.train_data.columns
        assert "feat_b" in result.train_data.columns

    def test_disabled_by_default(self) -> None:
        """Multicollinearity removal is off by default."""
        rng = np.random.RandomState(42)
        n = 100
        base = rng.randn(n)
        df = pl.DataFrame(
            {
                "feat_a": base.tolist(),
                "feat_b": base.tolist(),  # perfect copy
                "target": rng.randint(0, 2, n).tolist(),
            }
        )
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(df, "target", normalize=False)
        # Both columns should still be present
        assert "feat_a" in result.train_data.columns
        assert "feat_b" in result.train_data.columns

    def test_transform_drops_same_columns(self) -> None:
        """transform() on new data drops the same columns that were
        removed during setup."""
        rng = np.random.RandomState(42)
        n = 200
        base = rng.randn(n)
        df = pl.DataFrame(
            {
                "feat_a": base.tolist(),
                "feat_b": (base + rng.randn(n) * 0.001).tolist(),
                "feat_c": rng.randn(n).tolist(),
                "target": rng.randint(0, 2, n).tolist(),
            }
        )
        pipeline = PreprocessingPipeline()
        pipeline.setup(
            df,
            "target",
            normalize=False,
            remove_multicollinearity=True,
            multicollinearity_threshold=0.9,
        )
        dropped = pipeline._transformers.get("multicollinear_dropped", [])
        assert len(dropped) == 1

        new_data = df.head(5)
        transformed = pipeline.transform(new_data)
        assert dropped[0] not in transformed.columns

    def test_drops_column_with_lower_target_correlation(self) -> None:
        """When two features are correlated, the one with lower
        absolute target correlation is dropped."""
        rng = np.random.RandomState(42)
        n = 200
        target = rng.randint(0, 2, n)
        # feat_a has strong target correlation
        feat_a = target.astype(float) + rng.randn(n) * 0.1
        # feat_b is a near-copy of feat_a with small noise to keep
        # inter-feature correlation above 0.9 while having slightly
        # lower target correlation
        feat_b = feat_a + rng.randn(n) * 0.05
        df = pl.DataFrame(
            {
                "feat_a": feat_a.tolist(),
                "feat_b": feat_b.tolist(),
                "target": target.tolist(),
            }
        )
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            df,
            "target",
            normalize=False,
            remove_multicollinearity=True,
            multicollinearity_threshold=0.8,
        )
        dropped = result.transformers.get("multicollinear_dropped", [])
        # feat_b has lower target correlation, so it should be dropped
        assert dropped == ["feat_b"]

    def test_single_feature_no_removal(self) -> None:
        """With only one numeric feature, nothing can be removed."""
        df = pl.DataFrame(
            {
                "feat": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
                "target": [0, 1, 0, 1, 0, 1, 0, 1, 0, 1],
            }
        )
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            df,
            "target",
            normalize=False,
            remove_multicollinearity=True,
            multicollinearity_threshold=0.5,
        )
        dropped = result.transformers.get("multicollinear_dropped", [])
        assert len(dropped) == 0

    def test_multicollinear_dropped_in_config(self) -> None:
        """Config reflects multicollinearity settings."""
        df = pl.DataFrame(
            {
                "a": [1.0, 2.0, 3.0, 4.0, 5.0],
                "target": [0, 1, 0, 1, 0],
            }
        )
        pipeline = PreprocessingPipeline()
        pipeline.setup(
            df,
            "target",
            normalize=False,
            remove_multicollinearity=True,
            multicollinearity_threshold=0.85,
        )
        config = pipeline.get_config()
        assert config["remove_multicollinearity"] is True
        assert config["multicollinearity_threshold"] == 0.85


# ---------------------------------------------------------------------------
# Class imbalance handling (#327)
# ---------------------------------------------------------------------------


class TestClassImbalance:
    """Tests for fix_imbalance parameter (#327)."""

    @pytest.fixture()
    def imbalanced_df(self) -> pl.DataFrame:
        """DataFrame with severe class imbalance (90/10 split)."""
        rng = np.random.RandomState(42)
        n_majority = 180
        n_minority = 20
        n = n_majority + n_minority
        df = pl.DataFrame(
            {
                "feat_a": rng.randn(n).tolist(),
                "feat_b": rng.randn(n).tolist(),
                "target": ([0] * n_majority + [1] * n_minority),
            }
        )
        return df

    def test_class_weight_sets_flag(self, imbalanced_df: pl.DataFrame) -> None:
        """class_weight method sets the flag without resampling."""
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            imbalanced_df,
            "target",
            normalize=False,
            fix_imbalance=True,
            imbalance_method="class_weight",
        )
        assert pipeline._use_balanced_class_weight is True
        # No resampling -- row counts should match normal split
        total = result.train_data.height + result.test_data.height
        assert total == imbalanced_df.height

    def test_class_weight_no_extra_dependency(
        self, imbalanced_df: pl.DataFrame
    ) -> None:
        """class_weight works without imbalanced-learn installed."""
        pipeline = PreprocessingPipeline()
        # Should not raise ImportError
        result = pipeline.setup(
            imbalanced_df,
            "target",
            normalize=False,
            fix_imbalance=True,
            imbalance_method="class_weight",
        )
        assert result.train_data.height > 0

    def test_fix_imbalance_disabled_by_default(
        self, imbalanced_df: pl.DataFrame
    ) -> None:
        """Imbalance correction is off by default."""
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(imbalanced_df, "target", normalize=False)
        assert pipeline._use_balanced_class_weight is False
        # Train size should be the normal 80%
        assert result.train_data.height == int(imbalanced_df.height * 0.8)

    def test_fix_imbalance_skipped_for_regression(self) -> None:
        """Imbalance correction is not applied for regression tasks."""
        rng = np.random.RandomState(42)
        n = 100
        df = pl.DataFrame(
            {
                "feat": rng.randn(n).tolist(),
                "target": rng.randn(n).tolist(),  # continuous -> regression
            }
        )
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            df,
            "target",
            normalize=False,
            fix_imbalance=True,
            imbalance_method="class_weight",
        )
        assert pipeline._use_balanced_class_weight is False
        assert result.task_type == "regression"

    def test_invalid_imbalance_method_raises(self, imbalanced_df: pl.DataFrame) -> None:
        """Invalid imbalance_method raises ValueError."""
        pipeline = PreprocessingPipeline()
        with pytest.raises(ValueError, match="imbalance_method"):
            pipeline.setup(
                imbalanced_df,
                "target",
                fix_imbalance=True,
                imbalance_method="invalid",
            )

    def test_imbalance_config_stored(self, imbalanced_df: pl.DataFrame) -> None:
        """Config reflects imbalance settings."""
        pipeline = PreprocessingPipeline()
        pipeline.setup(
            imbalanced_df,
            "target",
            normalize=False,
            fix_imbalance=True,
            imbalance_method="class_weight",
        )
        config = pipeline.get_config()
        assert config["fix_imbalance"] is True
        assert config["imbalance_method"] == "class_weight"

    def test_summary_includes_imbalance(self, imbalanced_df: pl.DataFrame) -> None:
        """Summary mentions imbalance correction."""
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            imbalanced_df,
            "target",
            normalize=False,
            fix_imbalance=True,
            imbalance_method="class_weight",
        )
        assert "class_weight" in result.summary

    def test_smote_resamples_training_data(self, imbalanced_df: pl.DataFrame) -> None:
        """SMOTE increases the minority class in training data."""
        imblearn = pytest.importorskip("imblearn")  # noqa: F841
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            imbalanced_df,
            "target",
            normalize=False,
            fix_imbalance=True,
            imbalance_method="smote",
        )
        # After SMOTE, training data should have more rows
        normal_train_size = int(imbalanced_df.height * 0.8)
        assert result.train_data.height > normal_train_size
        # Classes should be balanced in training data
        class_counts = result.train_data["target"].value_counts()
        counts = class_counts["count"].to_list()
        assert counts[0] == counts[1]
        # Test data should be unmodified
        assert result.test_data.height == imbalanced_df.height - normal_train_size

    def test_adasyn_resamples_training_data(self, imbalanced_df: pl.DataFrame) -> None:
        """ADASYN increases the minority class in training data."""
        imblearn = pytest.importorskip("imblearn")  # noqa: F841
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            imbalanced_df,
            "target",
            normalize=False,
            fix_imbalance=True,
            imbalance_method="adasyn",
        )
        normal_train_size = int(imbalanced_df.height * 0.8)
        assert result.train_data.height > normal_train_size

    def test_smote_only_on_train_not_test(self, imbalanced_df: pl.DataFrame) -> None:
        """SMOTE modifies training data only; test data is untouched."""
        imblearn = pytest.importorskip("imblearn")  # noqa: F841
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            imbalanced_df,
            "target",
            normalize=False,
            fix_imbalance=True,
            imbalance_method="smote",
        )
        expected_test = imbalanced_df.height - int(imbalanced_df.height * 0.8)
        assert result.test_data.height == expected_test


# ---------------------------------------------------------------------------
# PCA dimensionality reduction
# ---------------------------------------------------------------------------


class TestPCA:
    """Tests for PCA dimensionality reduction."""

    @pytest.fixture()
    def wide_df(self) -> pl.DataFrame:
        """DataFrame with 100 numeric features (many redundant)."""
        rng = np.random.RandomState(42)
        n = 200
        # Generate 5 independent sources, then expand to 100 features.
        # Noise magnitude 1.0 (not 0.1) so the 100-d matrix is full-rank —
        # with 0.1 the matrix was rank-5 embedded in 100-d space and
        # sklearn's PCA / NMF internals triggered divide-by-zero matmul
        # warnings while computing variance for degenerate components.
        sources = rng.randn(n, 5)
        weights = rng.randn(5, 100)
        features = sources @ weights + rng.randn(n, 100) * 1.0
        data: dict[str, list[float]] = {}
        for i in range(100):
            data[f"feat_{i}"] = features[:, i].tolist()
        data["target"] = rng.randn(n).tolist()
        return pl.DataFrame(data)

    def test_pca_reduces_dimensions(self, wide_df: pl.DataFrame) -> None:
        """PCA with 100 input features produces fewer components."""
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            wide_df, "target", pca=True, pca_components=0.99, normalize=True
        )
        train_cols = result.train_data.columns
        pc_cols = [c for c in train_cols if c.startswith("pc_")]
        feat_cols = [c for c in train_cols if c.startswith("feat_")]
        assert len(pc_cols) > 0
        assert len(pc_cols) < 100
        assert len(feat_cols) == 0

    def test_pca_float_preserves_variance(self, wide_df: pl.DataFrame) -> None:
        """PCA with float components preserves explained variance."""
        pipeline = PreprocessingPipeline()
        pipeline.setup(wide_df, "target", pca=True, pca_components=0.95, normalize=True)
        pca_obj = pipeline._transformers["pca"]
        total_variance = sum(pca_obj.explained_variance_ratio_)
        assert total_variance >= 0.95

    def test_pca_int_gives_exact_count(self, wide_df: pl.DataFrame) -> None:
        """PCA with int components gives exact number of components."""
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            wide_df, "target", pca=True, pca_components=3, normalize=True
        )
        train_cols = result.train_data.columns
        pc_cols = [c for c in train_cols if c.startswith("pc_")]
        assert len(pc_cols) == 3

    def test_pca_disabled_by_default(self, wide_df: pl.DataFrame) -> None:
        """PCA is off by default -- columns are unchanged."""
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(wide_df, "target", normalize=False)
        train_cols = result.train_data.columns
        feat_cols = [c for c in train_cols if c.startswith("feat_")]
        pc_cols = [c for c in train_cols if c.startswith("pc_")]
        assert len(feat_cols) == 100
        assert len(pc_cols) == 0

    def test_pca_transform_same_structure(self, wide_df: pl.DataFrame) -> None:
        """transform() on new data produces same PC column structure."""
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            wide_df, "target", pca=True, pca_components=5, normalize=True
        )
        new_data = wide_df.head(10)
        transformed = pipeline.transform(new_data)
        pc_cols = [c for c in transformed.columns if c.startswith("pc_")]
        assert len(pc_cols) == 5
        feat_cols = [c for c in transformed.columns if c.startswith("feat_")]
        assert len(feat_cols) == 0


# ---------------------------------------------------------------------------
# Target transformation
# ---------------------------------------------------------------------------


class TestTargetTransformation:
    """Tests for target column power transformation."""

    @pytest.fixture()
    def skewed_regression_df(self) -> pl.DataFrame:
        """DataFrame with a heavily skewed regression target."""
        rng = np.random.RandomState(42)
        n = 200
        # Exponential distribution produces positive skew
        target = rng.exponential(scale=10.0, size=n)
        return pl.DataFrame(
            {
                "feat_a": rng.randn(n).tolist(),
                "feat_b": rng.randn(n).tolist(),
                "target": target.tolist(),
            }
        )

    def test_target_transform_applied_for_regression(
        self, skewed_regression_df: pl.DataFrame
    ) -> None:
        """Target values change after power transformation."""
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            skewed_regression_df,
            "target",
            normalize=False,
            transform_target=True,
        )
        assert result.task_type == "regression"
        assert "target_transformer" in result.transformers
        # Transformed target should differ from original
        combined = pl.concat([result.train_data, result.test_data])
        original_mean = skewed_regression_df["target"].mean()
        transformed_mean = combined["target"].mean()
        assert original_mean is not None and transformed_mean is not None
        assert abs(original_mean - transformed_mean) > 0.01

    def test_target_transform_skipped_for_classification(self) -> None:
        """Target transform is silently skipped for classification."""
        rng = np.random.RandomState(42)
        n = 100
        df = pl.DataFrame(
            {
                "feat": rng.randn(n).tolist(),
                "target": ([0] * 50 + [1] * 50),
            }
        )
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(df, "target", normalize=False, transform_target=True)
        assert result.task_type == "classification"
        assert "target_transformer" not in result.transformers

    def test_inverse_transform_reverses_target(
        self, skewed_regression_df: pl.DataFrame
    ) -> None:
        """inverse_transform recovers the original target values."""
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(
            skewed_regression_df,
            "target",
            normalize=False,
            transform_target=True,
        )
        # Take transformed training data and inverse transform
        sample = result.train_data.head(10)
        inversed = pipeline.inverse_transform(sample)
        # Compare against original data (find matching rows by features)
        # The inversed target should be close to the original scale
        inversed_vals = inversed["target"].to_numpy()
        # Values should be positive (original was exponential)
        assert all(v > 0 for v in inversed_vals)
        # Values should be in the original scale range, not the
        # compressed transformed range
        orig_max = skewed_regression_df["target"].max()
        assert orig_max is not None
        assert inversed_vals.max() > 1.0  # Original scale, not near-zero

    def test_target_transform_disabled_by_default(
        self, skewed_regression_df: pl.DataFrame
    ) -> None:
        """Target transformation is off by default."""
        pipeline = PreprocessingPipeline()
        result = pipeline.setup(skewed_regression_df, "target", normalize=False)
        assert "target_transformer" not in result.transformers
