# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for DataExplorer (P1: Tested)."""
from __future__ import annotations

import polars as pl
import pytest
from kailash_ml.engines.data_explorer import (
    AlertConfig,
    ColumnProfile,
    DataExplorer,
    DataProfile,
    VisualizationReport,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


@pytest.fixture()
def explorer() -> DataExplorer:
    """Pre-built DataExplorer instance."""
    return DataExplorer()


# ---------------------------------------------------------------------------
# P1 promotion -- no longer experimental
# ---------------------------------------------------------------------------


class TestP1Promotion:
    """Verify DataExplorer is no longer experimental."""

    def test_no_experimental_decorator(self) -> None:
        assert not hasattr(DataExplorer, "_quality_tier")

    def test_instantiation_no_warning(self) -> None:
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            DataExplorer()
            experimental = [
                x
                for x in w
                if "experimental" in str(x.message).lower() or "P2" in str(x.message)
            ]
            assert len(experimental) == 0


# ---------------------------------------------------------------------------
# DataExplorer.profile -- numeric columns
# ---------------------------------------------------------------------------


class TestProfileNumeric:
    """Tests for profiling numeric columns."""

    async def test_numeric_stats_computed(
        self, sample_df: pl.DataFrame, explorer: DataExplorer
    ) -> None:
        profile = await explorer.profile(sample_df, columns=["score"])

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

    async def test_null_percentage_calculated(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [1.0, None, 3.0, None, 5.0]})
        profile = await explorer.profile(df)
        col = profile.columns[0]
        assert col.null_count == 2
        assert col.null_pct == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# DataExplorer.profile -- string columns
# ---------------------------------------------------------------------------


class TestProfileString:
    """Tests for profiling string columns."""

    async def test_top_values_for_string_column(
        self, sample_df: pl.DataFrame, explorer: DataExplorer
    ) -> None:
        profile = await explorer.profile(sample_df, columns=["grade"])
        col = profile.columns[0]
        assert col.top_values is not None
        names = [v[0] for v in col.top_values]
        assert "A" in names
        assert "B" in names


# ---------------------------------------------------------------------------
# DataExplorer.profile -- correlation matrix
# ---------------------------------------------------------------------------


class TestProfileCorrelation:
    """Tests for correlation matrix computation."""

    async def test_correlation_matrix_computed(
        self, numeric_df: pl.DataFrame, explorer: DataExplorer
    ) -> None:
        profile = await explorer.profile(numeric_df)

        assert profile.correlation_matrix is not None
        assert profile.correlation_matrix["x"]["y"] == pytest.approx(1.0, abs=0.01)
        assert profile.correlation_matrix["x"]["z"] == pytest.approx(-1.0, abs=0.01)

    async def test_no_correlation_for_single_numeric(
        self, explorer: DataExplorer
    ) -> None:
        df = pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        profile = await explorer.profile(df)
        assert profile.correlation_matrix is None


# ---------------------------------------------------------------------------
# DataExplorer.profile -- missing patterns
# ---------------------------------------------------------------------------


class TestMissingPatterns:
    """Tests for missing pattern detection."""

    async def test_no_nulls_returns_empty(
        self, sample_df: pl.DataFrame, explorer: DataExplorer
    ) -> None:
        profile = await explorer.profile(sample_df)
        assert profile.missing_patterns == []

    async def test_single_null_column_reported(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"a": [1, None, 3], "b": [10, 20, 30]})
        profile = await explorer.profile(df)
        assert len(profile.missing_patterns) >= 1

    async def test_co_occurring_nulls_detected(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame(
            {
                "a": [1, None, 3, None, 5],
                "b": [10, None, 30, None, 50],
                "c": [100, 200, 300, 400, 500],
            }
        )
        profile = await explorer.profile(df)
        co_occurring = [p for p in profile.missing_patterns if len(p["columns"]) >= 2]
        assert len(co_occurring) >= 1


# ---------------------------------------------------------------------------
# DataProfile metadata
# ---------------------------------------------------------------------------


class TestDataProfileMeta:
    """Tests for DataProfile metadata fields."""

    async def test_profiled_at_is_set(
        self, sample_df: pl.DataFrame, explorer: DataExplorer
    ) -> None:
        profile = await explorer.profile(sample_df)
        assert profile.profiled_at != ""
        assert "T" in profile.profiled_at  # ISO format has T separator


# ---------------------------------------------------------------------------
# Extended ColumnProfile fields
# ---------------------------------------------------------------------------


class TestSkewnessKurtosis:
    """Tests for skewness and kurtosis computation."""

    async def test_symmetric_distribution_zero_skewness(
        self, explorer: DataExplorer
    ) -> None:
        df = pl.DataFrame({"v": [1.0, 2.0, 3.0, 4.0, 5.0]})
        profile = await explorer.profile(df)
        col = profile.columns[0]
        assert col.skewness is not None
        assert col.skewness == pytest.approx(0.0, abs=0.1)

    async def test_skewed_distribution_nonzero(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [1.0, 1.0, 1.0, 1.0, 100.0]})
        profile = await explorer.profile(df)
        col = profile.columns[0]
        assert col.skewness is not None
        assert col.skewness > 1.0  # Positively skewed

    async def test_kurtosis_computed(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]})
        profile = await explorer.profile(df)
        col = profile.columns[0]
        assert col.kurtosis is not None
        # Uniform-ish distribution has negative excess kurtosis
        assert isinstance(col.kurtosis, float)

    async def test_constant_column_zero_skew_kurtosis(
        self, explorer: DataExplorer
    ) -> None:
        df = pl.DataFrame({"v": [5.0, 5.0, 5.0, 5.0]})
        profile = await explorer.profile(df)
        col = profile.columns[0]
        assert col.skewness == 0.0
        assert col.kurtosis == 0.0

    async def test_two_element_series_zero(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [1.0, 2.0]})
        profile = await explorer.profile(df)
        col = profile.columns[0]
        assert col.skewness == 0.0
        assert col.kurtosis == 0.0


class TestZeroCount:
    """Tests for zero_count and zero_pct."""

    async def test_zero_count_computed(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [0, 1, 0, 2, 0]})
        profile = await explorer.profile(df)
        col = profile.columns[0]
        assert col.zero_count == 3
        assert col.zero_pct == pytest.approx(0.6)

    async def test_no_zeros(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [1, 2, 3]})
        profile = await explorer.profile(df)
        col = profile.columns[0]
        assert col.zero_count == 0
        assert col.zero_pct == 0.0

    async def test_string_column_no_zero_fields(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": ["a", "b", "c"]})
        profile = await explorer.profile(df)
        col = profile.columns[0]
        assert col.zero_count is None
        assert col.zero_pct is None


class TestIQROutliers:
    """Tests for IQR and outlier detection."""

    async def test_iqr_computed(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [1.0, 2.0, 3.0, 4.0, 5.0]})
        profile = await explorer.profile(df)
        col = profile.columns[0]
        assert col.iqr is not None
        assert col.iqr >= 0

    async def test_outlier_detected(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [1.0, 2.0, 3.0, 4.0, 5.0, 100.0]})
        profile = await explorer.profile(df)
        col = profile.columns[0]
        assert col.outlier_count is not None
        assert col.outlier_count >= 1
        assert col.outlier_pct is not None
        assert col.outlier_pct > 0

    async def test_no_outliers_in_tight_data(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [10.0, 10.1, 10.2, 10.3, 10.4]})
        profile = await explorer.profile(df)
        col = profile.columns[0]
        assert col.outlier_count == 0


class TestCardinalityRatio:
    """Tests for cardinality_ratio."""

    async def test_unique_column_ratio_one(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [1, 2, 3, 4, 5]})
        profile = await explorer.profile(df)
        col = profile.columns[0]
        assert col.cardinality_ratio == pytest.approx(1.0)

    async def test_constant_column_ratio(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [1, 1, 1, 1]})
        profile = await explorer.profile(df)
        col = profile.columns[0]
        assert col.cardinality_ratio == pytest.approx(0.25)

    async def test_string_column_has_ratio(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": ["a", "b", "a", "b"]})
        profile = await explorer.profile(df)
        col = profile.columns[0]
        assert col.cardinality_ratio == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Type inference
# ---------------------------------------------------------------------------


class TestTypeInference:
    """Tests for inferred_type."""

    async def test_numeric_inferred(self, explorer: DataExplorer) -> None:
        # 100 rows, 99 unique (one repeat) -- not id, not categorical
        df = pl.DataFrame({"v": list(range(99)) + [0]})
        profile = await explorer.profile(df)
        assert profile.columns[0].inferred_type == "numeric"

    async def test_boolean_inferred_01(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [0, 1, 0, 1, 0]})
        profile = await explorer.profile(df)
        assert profile.columns[0].inferred_type == "boolean"

    async def test_id_inferred(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [1, 2, 3, 4, 5]})
        profile = await explorer.profile(df)
        assert profile.columns[0].inferred_type == "id"

    async def test_constant_inferred(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [7, 7, 7, 7]})
        profile = await explorer.profile(df)
        assert profile.columns[0].inferred_type == "constant"

    async def test_categorical_numeric(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [1, 2, 3, 1, 2, 3, 1, 2, 3, 1, 2, 3]})
        profile = await explorer.profile(df)
        assert profile.columns[0].inferred_type == "categorical"

    async def test_categorical_string(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": ["cat", "dog", "cat", "dog"]})
        profile = await explorer.profile(df)
        assert profile.columns[0].inferred_type == "categorical"

    async def test_text_string(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [f"text_{i}" for i in range(100)]})
        profile = await explorer.profile(df)
        assert profile.columns[0].inferred_type == "text"


# ---------------------------------------------------------------------------
# Spearman correlation
# ---------------------------------------------------------------------------


class TestSpearmanCorrelation:
    """Tests for Spearman rank correlation."""

    async def test_spearman_computed(
        self, numeric_df: pl.DataFrame, explorer: DataExplorer
    ) -> None:
        profile = await explorer.profile(numeric_df)
        assert profile.spearman_matrix is not None
        assert profile.spearman_matrix["x"]["y"] == pytest.approx(1.0, abs=0.01)
        assert profile.spearman_matrix["x"]["z"] == pytest.approx(-1.0, abs=0.01)

    async def test_spearman_none_for_single_col(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        profile = await explorer.profile(df)
        assert profile.spearman_matrix is None


# ---------------------------------------------------------------------------
# Cramer's V
# ---------------------------------------------------------------------------


class TestCramersV:
    """Tests for Cramer's V categorical association."""

    async def test_cramers_v_computed(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame(
            {
                "color": ["red", "blue", "red", "blue", "red", "blue"],
                "size": ["S", "L", "S", "L", "S", "L"],
            }
        )
        profile = await explorer.profile(df)
        assert profile.categorical_associations is not None
        assert profile.categorical_associations["color"]["size"] > 0.0
        assert profile.categorical_associations["color"]["color"] == 1.0

    async def test_cramers_v_none_for_single_cat(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"a": ["x", "y", "z"], "b": [1, 2, 3]})
        profile = await explorer.profile(df)
        assert profile.categorical_associations is None


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


class TestDuplicates:
    """Tests for duplicate row detection."""

    async def test_no_duplicates(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        profile = await explorer.profile(df)
        assert profile.duplicate_count == 0
        assert profile.duplicate_pct == 0.0

    async def test_duplicates_detected(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
        profile = await explorer.profile(df)
        assert profile.duplicate_count == 2  # 2 rows are duplicated
        assert profile.duplicate_pct > 0


# ---------------------------------------------------------------------------
# Memory + samples
# ---------------------------------------------------------------------------


class TestMemoryAndSamples:
    """Tests for memory_bytes, sample_head, sample_tail."""

    async def test_memory_bytes_positive(
        self, sample_df: pl.DataFrame, explorer: DataExplorer
    ) -> None:
        profile = await explorer.profile(sample_df)
        assert profile.memory_bytes > 0

    async def test_sample_head_length(
        self, sample_df: pl.DataFrame, explorer: DataExplorer
    ) -> None:
        profile = await explorer.profile(sample_df)
        assert len(profile.sample_head) == 5

    async def test_sample_tail_length(
        self, sample_df: pl.DataFrame, explorer: DataExplorer
    ) -> None:
        profile = await explorer.profile(sample_df)
        assert len(profile.sample_tail) == 5

    async def test_small_df_samples(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"a": [1, 2]})
        profile = await explorer.profile(df)
        assert len(profile.sample_head) == 2
        assert len(profile.sample_tail) == 2


# ---------------------------------------------------------------------------
# Type summary
# ---------------------------------------------------------------------------


class TestTypeSummary:
    """Tests for type_summary aggregation."""

    async def test_type_summary_matches_columns(
        self, sample_df: pl.DataFrame, explorer: DataExplorer
    ) -> None:
        profile = await explorer.profile(sample_df)
        total = sum(profile.type_summary.values())
        assert total == profile.n_columns

    async def test_type_summary_keys(self, explorer: DataExplorer) -> None:
        # 100 rows, 99 unique numerics (one repeat) -> "numeric"; 2 cats -> "categorical"
        df = pl.DataFrame({"num": list(range(99)) + [0], "cat": ["a", "b"] * 50})
        profile = await explorer.profile(df)
        assert "numeric" in profile.type_summary
        assert "categorical" in profile.type_summary


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


class TestAlerts:
    """Tests for the alert generation system."""

    async def test_high_null_alert(self) -> None:
        config = AlertConfig(high_null_pct_threshold=0.1)
        explorer = DataExplorer(alert_config=config)
        df = pl.DataFrame({"v": [1.0, None, None, None, 5.0]})
        profile = await explorer.profile(df)
        null_alerts = [a for a in profile.alerts if a["type"] == "high_nulls"]
        assert len(null_alerts) == 1
        assert null_alerts[0]["column"] == "v"

    async def test_constant_alert(self) -> None:
        explorer = DataExplorer()
        df = pl.DataFrame({"v": [5, 5, 5, 5]})
        profile = await explorer.profile(df)
        constant_alerts = [a for a in profile.alerts if a["type"] == "constant"]
        assert len(constant_alerts) == 1

    async def test_high_correlation_alert(self) -> None:
        config = AlertConfig(high_correlation_threshold=0.9)
        explorer = DataExplorer(alert_config=config)
        df = pl.DataFrame(
            {
                "a": [1.0, 2.0, 3.0, 4.0, 5.0],
                "b": [2.0, 4.0, 6.0, 8.0, 10.0],
            }
        )
        profile = await explorer.profile(df)
        corr_alerts = [a for a in profile.alerts if a["type"] == "high_correlation"]
        assert len(corr_alerts) >= 1

    async def test_duplicate_alert(self) -> None:
        config = AlertConfig(duplicate_pct_threshold=0.0)
        explorer = DataExplorer(alert_config=config)
        df = pl.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
        profile = await explorer.profile(df)
        dup_alerts = [a for a in profile.alerts if a["type"] == "duplicates"]
        assert len(dup_alerts) == 1

    async def test_high_skewness_alert(self) -> None:
        config = AlertConfig(skewness_threshold=1.0)
        explorer = DataExplorer(alert_config=config)
        df = pl.DataFrame({"v": [1.0, 1.0, 1.0, 1.0, 100.0]})
        profile = await explorer.profile(df)
        skew_alerts = [a for a in profile.alerts if a["type"] == "high_skewness"]
        assert len(skew_alerts) >= 1

    async def test_high_zeros_alert(self) -> None:
        config = AlertConfig(zero_pct_threshold=0.3)
        explorer = DataExplorer(alert_config=config)
        df = pl.DataFrame({"v": [0, 0, 0, 1, 2]})
        profile = await explorer.profile(df)
        zero_alerts = [a for a in profile.alerts if a["type"] == "high_zeros"]
        assert len(zero_alerts) == 1

    async def test_high_cardinality_alert(self) -> None:
        config = AlertConfig(high_cardinality_ratio=0.8)
        explorer = DataExplorer(alert_config=config)
        df = pl.DataFrame({"v": list(range(100))})
        profile = await explorer.profile(df)
        card_alerts = [a for a in profile.alerts if a["type"] == "high_cardinality"]
        assert len(card_alerts) >= 1

    async def test_imbalance_alert(self) -> None:
        config = AlertConfig(imbalance_ratio_threshold=0.15)
        explorer = DataExplorer(alert_config=config)
        df = pl.DataFrame({"v": ["A"] * 90 + ["B"] * 10})
        profile = await explorer.profile(df)
        imbal_alerts = [a for a in profile.alerts if a["type"] == "imbalanced"]
        assert len(imbal_alerts) >= 1

    async def test_no_alerts_clean_data(self) -> None:
        config = AlertConfig(
            high_null_pct_threshold=0.5,
            high_correlation_threshold=0.99,
            duplicate_pct_threshold=1.0,
        )
        explorer = DataExplorer(alert_config=config)
        # Use uncorrelated data to avoid high_correlation alert
        df = pl.DataFrame(
            {
                "a": [1.0, 5.0, 2.0, 8.0, 3.0, 7.0, 4.0, 9.0, 6.0, 10.0] * 2,
                "b": [10.0, 3.0, 7.0, 1.0, 8.0, 2.0, 9.0, 4.0, 6.0, 5.0] * 2,
            }
        )
        profile = await explorer.profile(df)
        # Confirm no spurious high_nulls / high_correlation / duplicates
        for alert in profile.alerts:
            assert alert["type"] not in ("high_nulls", "high_correlation")


# ---------------------------------------------------------------------------
# AlertConfig defaults
# ---------------------------------------------------------------------------


class TestAlertConfig:
    """Tests for AlertConfig dataclass."""

    def test_defaults(self) -> None:
        config = AlertConfig()
        assert config.high_correlation_threshold == 0.9
        assert config.high_null_pct_threshold == 0.05
        assert config.constant_threshold == 1
        assert config.duplicate_pct_threshold == 0.0

    def test_custom_thresholds(self) -> None:
        config = AlertConfig(high_correlation_threshold=0.5, skewness_threshold=1.0)
        assert config.high_correlation_threshold == 0.5
        assert config.skewness_threshold == 1.0


# ---------------------------------------------------------------------------
# Serialization round-trips
# ---------------------------------------------------------------------------


class TestSerialization:
    """Tests for to_dict / from_dict round-trips."""

    def test_column_profile_round_trip(self) -> None:
        cp = ColumnProfile(
            name="x",
            dtype="Float64",
            count=100,
            null_count=5,
            null_pct=0.05,
            unique_count=95,
            mean=50.0,
            skewness=0.3,
            kurtosis=-0.2,
            zero_count=10,
            zero_pct=0.1,
            iqr=25.0,
            outlier_count=3,
            outlier_pct=0.03,
            cardinality_ratio=0.95,
            inferred_type="numeric",
        )
        d = cp.to_dict()
        restored = ColumnProfile.from_dict(d)
        assert restored.skewness == 0.3
        assert restored.kurtosis == -0.2
        assert restored.zero_count == 10
        assert restored.iqr == 25.0
        assert restored.outlier_count == 3
        assert restored.cardinality_ratio == 0.95
        assert restored.inferred_type == "numeric"

    async def test_data_profile_round_trip(
        self, sample_df: pl.DataFrame, explorer: DataExplorer
    ) -> None:
        profile = await explorer.profile(sample_df)
        d = profile.to_dict()
        restored = DataProfile.from_dict(d)
        assert restored.n_rows == profile.n_rows
        assert restored.duplicate_count == profile.duplicate_count
        assert restored.duplicate_pct == profile.duplicate_pct
        assert restored.memory_bytes == profile.memory_bytes
        assert len(restored.sample_head) == len(profile.sample_head)
        assert len(restored.sample_tail) == len(profile.sample_tail)
        assert restored.type_summary == profile.type_summary
        assert len(restored.alerts) == len(profile.alerts)

    def test_data_profile_from_dict_defaults(self) -> None:
        """Backward-compat: missing new fields fall back to defaults."""
        minimal = {
            "n_rows": 10,
            "n_columns": 2,
            "columns": [],
        }
        restored = DataProfile.from_dict(minimal)
        assert restored.spearman_matrix is None
        assert restored.duplicate_count == 0
        assert restored.memory_bytes == 0
        assert restored.sample_head == []
        assert restored.type_summary == {}
        assert restored.alerts == []


# ---------------------------------------------------------------------------
# DataExplorer.compare
# ---------------------------------------------------------------------------


class TestCompare:
    """Tests for dataset comparison."""

    async def test_compare_basic(self, explorer: DataExplorer) -> None:
        df_a = pl.DataFrame({"v": [1.0, 2.0, 3.0]})
        df_b = pl.DataFrame({"v": [4.0, 5.0, 6.0]})
        result = await explorer.compare(df_a, df_b)
        assert "profile_a" in result
        assert "profile_b" in result
        assert len(result["column_deltas"]) == 1
        assert result["column_deltas"][0]["mean_delta"] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# DataExplorer.visualize
# ---------------------------------------------------------------------------


class TestVisualize:
    """Tests for visualization generation."""

    async def test_visualize_returns_report(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"num": [1.0, 2.0, 3.0], "cat": ["a", "b", "a"]})
        report = await explorer.visualize(df)
        assert isinstance(report, VisualizationReport)
        assert isinstance(report.figures, dict)

    async def test_numeric_histogram_created(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0]})
        report = await explorer.visualize(df)
        assert "x" in report.figures

    async def test_string_bar_chart_created(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"cat": ["a", "b", "a", "c"]})
        report = await explorer.visualize(df)
        assert "cat" in report.figures

    async def test_correlation_heatmap_created(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"x": [1.0, 2.0, 3.0], "y": [4.0, 5.0, 6.0]})
        report = await explorer.visualize(df)
        assert "correlation" in report.figures


# ---------------------------------------------------------------------------
# DataExplorer.to_html
# ---------------------------------------------------------------------------


class TestToHtml:
    """Tests for HTML report generation."""

    async def test_returns_html_string(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [1.0, 2.0, 3.0]})
        html_str = await explorer.to_html(df)
        assert isinstance(html_str, str)
        assert html_str.startswith("<!DOCTYPE html>") or "<html" in html_str

    async def test_contains_title(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [1.0, 2.0, 3.0]})
        html_str = await explorer.to_html(df, title="My Test Report")
        assert "My Test Report" in html_str

    async def test_contains_overview_section(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [1.0, 2.0, 3.0]})
        html_str = await explorer.to_html(df)
        assert "overview" in html_str.lower() or "Overview" in html_str

    async def test_xss_safe_title(self, explorer: DataExplorer) -> None:
        df = pl.DataFrame({"v": [1.0, 2.0, 3.0]})
        html_str = await explorer.to_html(df, title='<script>alert("xss")</script>')
        assert "<script>alert" not in html_str
        assert "&lt;script&gt;" in html_str

    async def test_contains_variable_cards(self) -> None:
        df = pl.DataFrame({"score": [1.0, 2.0, 3.0], "grade": ["A", "B", "C"]})
        explorer = DataExplorer()
        html_str = await explorer.to_html(df)
        assert "score" in html_str
        assert "grade" in html_str


# ---------------------------------------------------------------------------
# from_dict validation
# ---------------------------------------------------------------------------


class TestFromDictValidation:
    """Tests for from_dict input validation."""

    def test_column_profile_missing_field_raises(self) -> None:
        with pytest.raises(ValueError, match="missing required field"):
            ColumnProfile.from_dict({"name": "x"})

    def test_column_profile_negative_count_raises(self) -> None:
        with pytest.raises(ValueError, match="count must be non-negative"):
            ColumnProfile.from_dict(
                {
                    "name": "x",
                    "dtype": "Int64",
                    "count": -1,
                    "null_count": 0,
                    "null_pct": 0.0,
                    "unique_count": 1,
                }
            )

    def test_data_profile_missing_field_raises(self) -> None:
        with pytest.raises(ValueError, match="missing required field"):
            DataProfile.from_dict({"n_rows": 10})

    def test_data_profile_negative_rows_raises(self) -> None:
        with pytest.raises(ValueError, match="n_rows must be non-negative"):
            DataProfile.from_dict({"n_rows": -1, "n_columns": 2, "columns": []})
