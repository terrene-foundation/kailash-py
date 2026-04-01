# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for DataExplorer (P2 experimental)."""
from __future__ import annotations

import warnings

import polars as pl
import pytest
from kailash_ml._decorators import ExperimentalWarning, _warned_classes
from kailash_ml.engines.data_explorer import (
    ColumnProfile,
    DataExplorer,
    DataProfile,
    VisualizationReport,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_experimental_warnings():
    """Reset the experimental warning tracker so each test is independent."""
    _warned_classes.discard("DataExplorer")
    yield
    _warned_classes.discard("DataExplorer")


@pytest.fixture()
def sample_df() -> pl.DataFrame:
    """Small 8-row DataFrame with numeric and string columns."""
    return pl.DataFrame(
        {
            "id": list(range(1, 9)),
            "score": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0],
            "grade": ["A", "B", "A", "C", "B", "A", "C", "B"],
        }
    )


@pytest.fixture()
def numeric_df() -> pl.DataFrame:
    """DataFrame with only numeric columns for correlation testing."""
    return pl.DataFrame(
        {
            "x": [1.0, 2.0, 3.0, 4.0, 5.0],
            "y": [2.0, 4.0, 6.0, 8.0, 10.0],
            "z": [5.0, 4.0, 3.0, 2.0, 1.0],
        }
    )


# ---------------------------------------------------------------------------
# @experimental decorator
# ---------------------------------------------------------------------------


class TestExperimentalDecorator:
    """Tests for the @experimental decorator on DataExplorer."""

    def test_first_instantiation_warns(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            DataExplorer()
            assert len(w) == 1
            assert issubclass(w[0].category, ExperimentalWarning)
            assert "DataExplorer" in str(w[0].message)
            assert "P2" in str(w[0].message)

    def test_second_instantiation_silent(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            DataExplorer()  # first -- warns
            DataExplorer()  # second -- silent
            experimental_warnings = [
                x for x in w if issubclass(x.category, ExperimentalWarning)
            ]
            assert len(experimental_warnings) == 1

    def test_quality_tier_attribute(self) -> None:
        assert DataExplorer._quality_tier == "P2"


# ---------------------------------------------------------------------------
# DataExplorer.profile -- numeric columns
# ---------------------------------------------------------------------------


class TestProfileNumeric:
    """Tests for profiling numeric columns."""

    def test_numeric_stats_computed(self, sample_df: pl.DataFrame) -> None:
        explorer = DataExplorer()
        profile = explorer.profile(sample_df, columns=["score"])

        assert profile.n_rows == 8
        assert profile.n_columns == 1
        col = profile.columns[0]
        assert col.name == "score"
        assert col.count == 8
        assert col.null_count == 0
        assert col.null_pct == 0.0
        assert col.mean == pytest.approx(45.0)
        assert col.min_val == pytest.approx(10.0)
        assert col.max_val == pytest.approx(80.0)
        assert col.q50 is not None

    def test_null_percentage_calculated(self) -> None:
        df = pl.DataFrame({"v": [1.0, None, 3.0, None, 5.0]})
        explorer = DataExplorer()
        profile = explorer.profile(df)
        col = profile.columns[0]
        assert col.null_count == 2
        assert col.null_pct == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# DataExplorer.profile -- string columns
# ---------------------------------------------------------------------------


class TestProfileString:
    """Tests for profiling string columns."""

    def test_top_values_for_string_column(self, sample_df: pl.DataFrame) -> None:
        explorer = DataExplorer()
        profile = explorer.profile(sample_df, columns=["grade"])
        col = profile.columns[0]
        assert col.top_values is not None
        # "A" appears 3 times, "B" 3 times, "C" 2 times
        names = [v[0] for v in col.top_values]
        assert "A" in names
        assert "B" in names


# ---------------------------------------------------------------------------
# DataExplorer.profile -- correlation matrix
# ---------------------------------------------------------------------------


class TestProfileCorrelation:
    """Tests for correlation matrix computation."""

    def test_correlation_matrix_computed(self, numeric_df: pl.DataFrame) -> None:
        explorer = DataExplorer()
        profile = explorer.profile(numeric_df)

        assert profile.correlation_matrix is not None
        # x and y are perfectly correlated
        assert profile.correlation_matrix["x"]["y"] == pytest.approx(1.0, abs=0.01)
        # x and z are inversely correlated
        assert profile.correlation_matrix["x"]["z"] == pytest.approx(-1.0, abs=0.01)

    def test_no_correlation_for_single_numeric(self) -> None:
        df = pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        explorer = DataExplorer()
        profile = explorer.profile(df)
        assert profile.correlation_matrix is None


# ---------------------------------------------------------------------------
# DataExplorer.profile -- missing patterns
# ---------------------------------------------------------------------------


class TestMissingPatterns:
    """Tests for missing pattern detection."""

    def test_no_nulls_returns_empty(self, sample_df: pl.DataFrame) -> None:
        explorer = DataExplorer()
        profile = explorer.profile(sample_df)
        assert profile.missing_patterns == []

    def test_single_null_column_reported(self) -> None:
        df = pl.DataFrame({"a": [1, None, 3], "b": [10, 20, 30]})
        explorer = DataExplorer()
        profile = explorer.profile(df)
        # At least one pattern referencing column "a"
        assert len(profile.missing_patterns) >= 1

    def test_co_occurring_nulls_detected(self) -> None:
        df = pl.DataFrame(
            {
                "a": [1, None, 3, None, 5],
                "b": [10, None, 30, None, 50],
                "c": [100, 200, 300, 400, 500],
            }
        )
        explorer = DataExplorer()
        profile = explorer.profile(df)
        # Rows 1 and 3 have both a and b null
        co_occurring = [p for p in profile.missing_patterns if len(p["columns"]) >= 2]
        assert len(co_occurring) >= 1


# ---------------------------------------------------------------------------
# DataProfile metadata
# ---------------------------------------------------------------------------


class TestDataProfileMeta:
    """Tests for DataProfile metadata fields."""

    def test_profiled_at_is_set(self, sample_df: pl.DataFrame) -> None:
        explorer = DataExplorer()
        profile = explorer.profile(sample_df)
        assert profile.profiled_at != ""
        assert "T" in profile.profiled_at  # ISO format has T separator
