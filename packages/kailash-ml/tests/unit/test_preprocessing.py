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
