# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for kailash_ml.interop -- polars conversion module."""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from kailash_ml.interop import (
    from_pandas,
    from_sklearn_output,
    polars_to_arrow,
    polars_to_dict_records,
    to_pandas,
    to_sklearn_input,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_df() -> pl.DataFrame:
    """Small mixed-type DataFrame for round-trip tests."""
    return pl.DataFrame(
        {
            "entity_id": ["e0", "e1", "e2", "e3"],
            "feature_a": [1.0, 2.0, 3.0, 4.0],
            "feature_b": [10, 20, 30, 40],
            "category": ["cat", "dog", "cat", "bird"],
            "flag": [True, False, True, False],
            "target": [0.5, 1.5, 2.5, 3.5],
        }
    ).with_columns(pl.col("category").cast(pl.Categorical))


@pytest.fixture
def numeric_df() -> pl.DataFrame:
    """Pure numeric DataFrame."""
    return pl.DataFrame(
        {
            "x1": [1.0, 2.0, 3.0],
            "x2": [4.0, 5.0, 6.0],
            "y": [10.0, 20.0, 30.0],
        }
    )


@pytest.fixture
def df_with_nulls() -> pl.DataFrame:
    """DataFrame with null values."""
    return pl.DataFrame(
        {
            "a": [1.0, None, 3.0],
            "b": [None, 2.0, None],
            "target": [0.0, 1.0, 0.0],
        }
    )


# ---------------------------------------------------------------------------
# to_sklearn_input / from_sklearn_output
# ---------------------------------------------------------------------------


class TestToSklearnInput:
    def test_basic_numeric(self, numeric_df: pl.DataFrame) -> None:
        X, y, info = to_sklearn_input(numeric_df, ["x1", "x2"], "y")
        assert X.shape == (3, 2)
        assert y is not None
        assert y.shape == (3,)
        np.testing.assert_array_almost_equal(X[:, 0], [1.0, 2.0, 3.0])
        np.testing.assert_array_almost_equal(y, [10.0, 20.0, 30.0])

    def test_categorical_encoding(self, sample_df: pl.DataFrame) -> None:
        X, y, info = to_sklearn_input(sample_df, ["feature_a", "category"], "target")
        assert X.shape == (4, 2)
        assert "cat_mappings" in info
        assert "category" in info["cat_mappings"]
        # Categorical codes should be non-negative integers
        codes = X[:, 1]
        assert all(c >= 0 for c in codes)

    def test_boolean_encoding(self, sample_df: pl.DataFrame) -> None:
        X, _, info = to_sklearn_input(sample_df, ["flag"])
        assert X.shape == (4, 1)
        # True->1, False->0
        assert set(X[:, 0]) == {0.0, 1.0}

    def test_nulls_become_nan(self, df_with_nulls: pl.DataFrame) -> None:
        X, y, info = to_sklearn_input(df_with_nulls, ["a", "b"], "target")
        assert np.isnan(X[1, 0])  # a[1] was None
        assert np.isnan(X[0, 1])  # b[0] was None

    def test_no_target(self, numeric_df: pl.DataFrame) -> None:
        X, y, info = to_sklearn_input(numeric_df, ["x1", "x2"])
        assert y is None
        assert X.shape == (3, 2)

    def test_auto_feature_columns(self, numeric_df: pl.DataFrame) -> None:
        X, y, info = to_sklearn_input(numeric_df, target_column="y")
        assert X.shape == (3, 2)
        assert info["feature_columns"] == ["x1", "x2"]

    def test_utf8_raises(self) -> None:
        df = pl.DataFrame({"text": ["hello", "world"]})
        with pytest.raises(ValueError, match="Utf8/String"):
            to_sklearn_input(df)

    def test_null_column_raises(self) -> None:
        df = pl.DataFrame({"bad": pl.Series([None, None, None])})
        with pytest.raises(ValueError, match="entirely null"):
            to_sklearn_input(df)


class TestFromSklearnOutput:
    def test_restore_column_names(self, numeric_df: pl.DataFrame) -> None:
        X, y, info = to_sklearn_input(numeric_df, ["x1", "x2"], "y")
        restored = from_sklearn_output(X, info, ["x1", "x2"])
        assert restored.columns == ["x1", "x2"]
        assert restored.shape == (3, 2)

    def test_1d_predictions(self, numeric_df: pl.DataFrame) -> None:
        _, _, info = to_sklearn_input(numeric_df, ["x1", "x2"], "y")
        preds = np.array([1.0, 2.0, 3.0])
        result = from_sklearn_output(preds, info)
        assert result.shape == (3, 1)

    def test_sklearn_round_trip_column_names(self, numeric_df: pl.DataFrame) -> None:
        feature_cols = ["x1", "x2"]
        X, y, info = to_sklearn_input(numeric_df, feature_cols, "y")
        restored = from_sklearn_output(X, info, feature_cols)
        assert restored.columns == feature_cols


# ---------------------------------------------------------------------------
# polars_to_arrow
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("pyarrow"),
    reason="pyarrow not installed",
)
class TestPolarsToArrow:
    def test_basic_conversion(self, sample_df: pl.DataFrame) -> None:
        table = polars_to_arrow(sample_df)
        import pyarrow as pa

        assert isinstance(table, pa.Table)
        assert table.num_rows == 4

    def test_schema_validation_passes(self, numeric_df: pl.DataFrame) -> None:
        table = polars_to_arrow(numeric_df)
        # Validate against itself -- should pass
        polars_to_arrow(numeric_df, validate_schema=True, expected_schema=table.schema)

    def test_schema_validation_fails(self, numeric_df: pl.DataFrame) -> None:
        import pyarrow as pa

        wrong_schema = pa.schema([pa.field("wrong", pa.int64())])
        with pytest.raises(ValueError, match="Schema mismatch"):
            polars_to_arrow(
                numeric_df, validate_schema=True, expected_schema=wrong_schema
            )


# ---------------------------------------------------------------------------
# to_pandas / from_pandas round-trip
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("pyarrow"),
    reason="pyarrow not installed (required for polars↔pandas)",
)
class TestPandasRoundTrip:
    def test_numeric_round_trip(self, numeric_df: pl.DataFrame) -> None:
        pdf = to_pandas(numeric_df)
        restored = from_pandas(pdf)
        assert restored.shape == numeric_df.shape
        for col in numeric_df.columns:
            np.testing.assert_array_almost_equal(
                restored[col].to_numpy(), numeric_df[col].to_numpy()
            )

    def test_categorical_preserved(self) -> None:
        df = pl.DataFrame({"cat": ["a", "b", "a", "c"]}).with_columns(
            pl.col("cat").cast(pl.Categorical)
        )
        pdf = to_pandas(df)
        import pandas as pd

        assert isinstance(pdf["cat"].dtype, pd.CategoricalDtype)
        restored = from_pandas(pdf)
        assert restored["cat"].dtype == pl.Categorical

    def test_datetime_preserved(self) -> None:
        from datetime import datetime as dt

        df = pl.DataFrame({"ts": [dt(2026, 1, 1), dt(2026, 6, 15)]})
        pdf = to_pandas(df)
        restored = from_pandas(pdf)
        assert restored["ts"].dtype in (
            pl.Datetime,
            pl.Datetime("us"),
            pl.Datetime("ns"),
        )
        assert restored.shape == df.shape

    def test_nulls_preserved(self, df_with_nulls: pl.DataFrame) -> None:
        pdf = to_pandas(df_with_nulls)
        restored = from_pandas(pdf)
        assert restored["a"].null_count() == 1
        assert restored["b"].null_count() == 2

    def test_full_round_trip_schema(self, sample_df: pl.DataFrame) -> None:
        pdf = to_pandas(sample_df)
        restored = from_pandas(pdf)
        assert restored.shape == sample_df.shape
        # Numeric columns should match
        for col in ["feature_a", "feature_b", "target"]:
            np.testing.assert_array_almost_equal(
                restored[col].to_numpy(), sample_df[col].to_numpy()
            )


# ---------------------------------------------------------------------------
# polars_to_dict_records
# ---------------------------------------------------------------------------


class TestPolarsToDictRecords:
    def test_basic(self, numeric_df: pl.DataFrame) -> None:
        records = polars_to_dict_records(numeric_df)
        assert len(records) == 3
        assert records[0] == {"x1": 1.0, "x2": 4.0, "y": 10.0}

    def test_max_rows_exceeded(self) -> None:
        df = pl.DataFrame({"x": list(range(100))})
        with pytest.raises(ValueError, match="exceeding the max_rows limit"):
            polars_to_dict_records(df, max_rows=50)

    def test_empty_df(self) -> None:
        df = pl.DataFrame({"x": pl.Series([], dtype=pl.Float64)})
        records = polars_to_dict_records(df)
        assert records == []
