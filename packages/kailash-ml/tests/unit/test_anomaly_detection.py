# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for AnomalyDetectionEngine -- isolation forest, LOF, one-class SVM."""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from kailash_ml.engines.anomaly_detection import (
    AnomalyDetectionEngine,
    AnomalyResult,
    EnsembleAnomalyResult,
    _compute_anomaly_metrics,
    _normalize_scores,
    _validate_algorithm,
    _validate_contamination,
)
from sklearn.datasets import make_blobs

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine() -> AnomalyDetectionEngine:
    return AnomalyDetectionEngine()


@pytest.fixture()
def normal_data() -> pl.DataFrame:
    """200-row dataset from a single Gaussian cluster (mostly normal)."""
    X, _ = make_blobs(
        n_samples=200,
        centers=1,
        cluster_std=1.0,
        random_state=42,
        n_features=5,
    )
    data = {f"f{i}": X[:, i].tolist() for i in range(5)}
    return pl.DataFrame(data)


@pytest.fixture()
def data_with_anomalies() -> pl.DataFrame:
    """200 normal samples + 20 outliers injected far from the cluster."""
    X_normal, _ = make_blobs(
        n_samples=200,
        centers=[[0.0, 0.0, 0.0, 0.0, 0.0]],
        cluster_std=1.0,
        random_state=42,
        n_features=5,
    )
    rng = np.random.RandomState(99)
    X_outliers = rng.uniform(low=10.0, high=15.0, size=(20, 5))
    X = np.vstack([X_normal, X_outliers])
    data = {f"f{i}": X[:, i].tolist() for i in range(5)}
    return pl.DataFrame(data)


@pytest.fixture()
def mixed_type_data() -> pl.DataFrame:
    """DataFrame with both numeric and string columns."""
    return pl.DataFrame(
        {
            "f0": [1.0, 2.0, 3.0, 100.0] * 25,
            "f1": [0.5, 0.6, 0.7, 50.0] * 25,
            "category": ["a", "b", "c", "d"] * 25,
        }
    )


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


class TestValidation:
    def test_unsupported_algorithm_raises(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            engine.detect(normal_data, algorithm="dbscan")

    def test_contamination_too_low_raises(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        with pytest.raises(ValueError, match="contamination must be in"):
            engine.detect(normal_data, contamination=0.0)

    def test_contamination_too_high_raises(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        with pytest.raises(ValueError, match="contamination must be in"):
            engine.detect(normal_data, contamination=0.5)

    def test_contamination_negative_raises(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        with pytest.raises(ValueError, match="contamination must be in"):
            engine.detect(normal_data, contamination=-0.1)

    def test_empty_dataframe_raises(self, engine: AnomalyDetectionEngine):
        empty_df = pl.DataFrame({"f0": [], "f1": []}).cast(
            {"f0": pl.Float64, "f1": pl.Float64}
        )
        with pytest.raises(ValueError, match="empty"):
            engine.detect(empty_df)

    def test_no_numeric_columns_raises(self, engine: AnomalyDetectionEngine):
        df = pl.DataFrame({"a": ["x", "y", "z"] * 34})
        with pytest.raises(ValueError, match="No numeric columns"):
            engine.detect(df)

    def test_validate_algorithm_helper(self):
        _validate_algorithm("isolation_forest")
        _validate_algorithm("lof")
        _validate_algorithm("one_class_svm")
        with pytest.raises(ValueError):
            _validate_algorithm("invalid")

    def test_validate_contamination_helper(self):
        _validate_contamination(0.1)
        _validate_contamination(0.01)
        _validate_contamination(0.49)
        with pytest.raises(ValueError):
            _validate_contamination(0.0)
        with pytest.raises(ValueError):
            _validate_contamination(0.5)


# ---------------------------------------------------------------------------
# Isolation Forest tests
# ---------------------------------------------------------------------------


class TestIsolationForest:
    def test_detect_returns_anomaly_result(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        result = engine.detect(
            normal_data, algorithm="isolation_forest", contamination=0.1
        )
        assert isinstance(result, AnomalyResult)
        assert result.algorithm == "isolation_forest"
        assert result.contamination == 0.1

    def test_labels_are_1_or_neg1(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        result = engine.detect(normal_data, algorithm="isolation_forest")
        unique_labels = set(result.labels)
        assert unique_labels.issubset({1, -1})

    def test_scores_normalized_0_to_1(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        result = engine.detect(normal_data, algorithm="isolation_forest")
        assert all(0.0 <= s <= 1.0 for s in result.scores)

    def test_n_anomalies_matches_labels(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        result = engine.detect(normal_data, algorithm="isolation_forest")
        assert result.n_anomalies == sum(1 for lbl in result.labels if lbl == -1)

    def test_length_matches_input(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        result = engine.detect(normal_data, algorithm="isolation_forest")
        assert len(result.labels) == normal_data.height
        assert len(result.scores) == normal_data.height

    def test_detects_injected_anomalies(
        self, engine: AnomalyDetectionEngine, data_with_anomalies: pl.DataFrame
    ):
        result = engine.detect(
            data_with_anomalies, algorithm="isolation_forest", contamination=0.1
        )
        # The last 20 samples are outliers -- at least some should be detected
        outlier_labels = result.labels[200:]
        n_detected = sum(1 for lbl in outlier_labels if lbl == -1)
        assert n_detected >= 10, f"Only detected {n_detected}/20 injected outliers"

    def test_feature_columns_selection(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        result = engine.detect(
            normal_data,
            algorithm="isolation_forest",
            feature_columns=["f0", "f1"],
        )
        assert len(result.labels) == normal_data.height

    def test_reproducible_with_seed(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        r1 = engine.detect(normal_data, algorithm="isolation_forest", seed=42)
        r2 = engine.detect(normal_data, algorithm="isolation_forest", seed=42)
        assert r1.labels == r2.labels
        assert r1.scores == r2.scores


# ---------------------------------------------------------------------------
# LOF tests
# ---------------------------------------------------------------------------


class TestLOF:
    def test_detect_returns_anomaly_result(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        result = engine.detect(normal_data, algorithm="lof", contamination=0.1)
        assert isinstance(result, AnomalyResult)
        assert result.algorithm == "lof"

    def test_labels_are_1_or_neg1(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        result = engine.detect(normal_data, algorithm="lof")
        unique_labels = set(result.labels)
        assert unique_labels.issubset({1, -1})

    def test_scores_normalized_0_to_1(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        result = engine.detect(normal_data, algorithm="lof")
        assert all(0.0 <= s <= 1.0 for s in result.scores)

    def test_detects_injected_anomalies(
        self, engine: AnomalyDetectionEngine, data_with_anomalies: pl.DataFrame
    ):
        result = engine.detect(data_with_anomalies, algorithm="lof", contamination=0.1)
        outlier_labels = result.labels[200:]
        n_detected = sum(1 for lbl in outlier_labels if lbl == -1)
        assert n_detected >= 10, f"Only detected {n_detected}/20 injected outliers"

    def test_reproducible_with_seed(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        """LOF is deterministic for the same data, no seed needed."""
        r1 = engine.detect(normal_data, algorithm="lof")
        r2 = engine.detect(normal_data, algorithm="lof")
        assert r1.labels == r2.labels


# ---------------------------------------------------------------------------
# One-Class SVM tests
# ---------------------------------------------------------------------------


class TestOneClassSVM:
    def test_detect_returns_anomaly_result(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        result = engine.detect(
            normal_data, algorithm="one_class_svm", contamination=0.1
        )
        assert isinstance(result, AnomalyResult)
        assert result.algorithm == "one_class_svm"

    def test_labels_are_1_or_neg1(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        result = engine.detect(normal_data, algorithm="one_class_svm")
        unique_labels = set(result.labels)
        assert unique_labels.issubset({1, -1})

    def test_scores_normalized_0_to_1(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        result = engine.detect(normal_data, algorithm="one_class_svm")
        assert all(0.0 <= s <= 1.0 for s in result.scores)

    def test_detects_injected_anomalies(
        self, engine: AnomalyDetectionEngine, data_with_anomalies: pl.DataFrame
    ):
        result = engine.detect(
            data_with_anomalies, algorithm="one_class_svm", contamination=0.1
        )
        outlier_labels = result.labels[200:]
        n_detected = sum(1 for lbl in outlier_labels if lbl == -1)
        assert n_detected >= 5, f"Only detected {n_detected}/20 injected outliers"


# ---------------------------------------------------------------------------
# Score normalization tests
# ---------------------------------------------------------------------------


class TestScoreNormalization:
    def test_normalize_scores_range(self):
        raw = np.array([-3.0, -1.0, 0.0, 1.0, 3.0])
        normalized = _normalize_scores(raw)
        assert np.isclose(normalized.min(), 0.0)
        assert np.isclose(normalized.max(), 1.0)

    def test_normalize_scores_inverts(self):
        """Lower raw scores (more anomalous in sklearn) should become higher normalized scores."""
        raw = np.array([-5.0, 0.0, 5.0])
        normalized = _normalize_scores(raw)
        # -5.0 is most anomalous (lowest raw) -> should have highest normalized
        assert normalized[0] > normalized[2]

    def test_normalize_scores_constant_returns_0_5(self):
        raw = np.array([2.0, 2.0, 2.0, 2.0])
        normalized = _normalize_scores(raw)
        assert np.allclose(normalized, 0.5)

    def test_normalize_scores_single_element(self):
        raw = np.array([1.0])
        normalized = _normalize_scores(raw)
        assert np.isclose(normalized[0], 0.5)


# ---------------------------------------------------------------------------
# Metrics tests
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_compute_anomaly_metrics_basic(self):
        labels = np.array([1, 1, 1, -1, -1])
        scores = np.array([0.1, 0.2, 0.15, 0.8, 0.9])
        metrics = _compute_anomaly_metrics(labels, scores)

        assert metrics["n_samples"] == 5.0
        assert metrics["n_anomalies"] == 2.0
        assert metrics["n_normal"] == 3.0
        assert np.isclose(metrics["anomaly_ratio"], 0.4)
        assert "mean_anomaly_score" in metrics
        assert "std_anomaly_score" in metrics

    def test_compute_metrics_score_separation(self):
        labels = np.array([1, 1, -1, -1])
        scores = np.array([0.1, 0.2, 0.8, 0.9])
        metrics = _compute_anomaly_metrics(labels, scores)

        assert "score_separation" in metrics
        assert metrics["score_separation"] > 0  # anomalies have higher scores

    def test_metrics_in_result(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        result = engine.detect(normal_data, algorithm="isolation_forest")
        assert "n_samples" in result.metrics
        assert "anomaly_ratio" in result.metrics
        assert result.metrics["n_samples"] == float(normal_data.height)


# ---------------------------------------------------------------------------
# Ensemble detection tests
# ---------------------------------------------------------------------------


class TestEnsembleDetect:
    def test_majority_voting(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        result = engine.ensemble_detect(
            normal_data,
            algorithms=["isolation_forest", "lof"],
            voting="majority",
        )
        assert isinstance(result, EnsembleAnomalyResult)
        assert result.voting == "majority"
        assert len(result.labels) == normal_data.height
        assert len(result.combined_scores) == normal_data.height
        assert len(result.component_results) == 2

    def test_score_average_voting(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        result = engine.ensemble_detect(
            normal_data,
            algorithms=["isolation_forest", "lof"],
            voting="score_average",
        )
        assert isinstance(result, EnsembleAnomalyResult)
        assert result.voting == "score_average"
        assert all(0.0 <= s <= 1.0 for s in result.combined_scores)

    def test_ensemble_labels_are_1_or_neg1(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        result = engine.ensemble_detect(
            normal_data, algorithms=["isolation_forest", "lof"]
        )
        unique_labels = set(result.labels)
        assert unique_labels.issubset({1, -1})

    def test_ensemble_three_algorithms(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        result = engine.ensemble_detect(
            normal_data,
            algorithms=["isolation_forest", "lof", "one_class_svm"],
            voting="majority",
        )
        assert len(result.component_results) == 3
        algorithms_used = [r.algorithm for r in result.component_results]
        assert "isolation_forest" in algorithms_used
        assert "lof" in algorithms_used
        assert "one_class_svm" in algorithms_used

    def test_ensemble_detects_injected_anomalies(
        self, engine: AnomalyDetectionEngine, data_with_anomalies: pl.DataFrame
    ):
        result = engine.ensemble_detect(
            data_with_anomalies,
            algorithms=["isolation_forest", "lof"],
            contamination=0.1,
            voting="majority",
        )
        outlier_labels = result.labels[200:]
        n_detected = sum(1 for lbl in outlier_labels if lbl == -1)
        assert (
            n_detected >= 8
        ), f"Ensemble only detected {n_detected}/20 injected outliers"

    def test_invalid_voting_raises(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        with pytest.raises(ValueError, match="voting must be"):
            engine.ensemble_detect(normal_data, voting="invalid")

    def test_single_algorithm_raises(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        with pytest.raises(ValueError, match="at least 2 algorithms"):
            engine.ensemble_detect(normal_data, algorithms=["isolation_forest"])

    def test_default_algorithms(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        """Default should use isolation_forest + lof."""
        result = engine.ensemble_detect(normal_data)
        algorithms_used = [r.algorithm for r in result.component_results]
        assert algorithms_used == ["isolation_forest", "lof"]


# ---------------------------------------------------------------------------
# Serialization tests
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_anomaly_result_to_dict_roundtrip(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        result = engine.detect(normal_data, algorithm="isolation_forest")
        d = result.to_dict()

        assert isinstance(d, dict)
        assert d["algorithm"] == "isolation_forest"
        assert isinstance(d["labels"], list)
        assert isinstance(d["scores"], list)

        restored = AnomalyResult.from_dict(d)
        assert restored.labels == result.labels
        assert restored.scores == result.scores
        assert restored.algorithm == result.algorithm
        assert restored.contamination == result.contamination
        assert restored.n_anomalies == result.n_anomalies

    def test_ensemble_result_to_dict_roundtrip(
        self, engine: AnomalyDetectionEngine, normal_data: pl.DataFrame
    ):
        result = engine.ensemble_detect(
            normal_data, algorithms=["isolation_forest", "lof"]
        )
        d = result.to_dict()

        assert isinstance(d, dict)
        assert d["voting"] == "majority"
        assert len(d["component_results"]) == 2

        restored = EnsembleAnomalyResult.from_dict(d)
        assert restored.labels == result.labels
        assert restored.combined_scores == result.combined_scores
        assert restored.voting == result.voting
        assert len(restored.component_results) == len(result.component_results)


# ---------------------------------------------------------------------------
# Auto-detection of numeric columns
# ---------------------------------------------------------------------------


class TestAutoFeatureSelection:
    def test_auto_selects_numeric_columns(
        self, engine: AnomalyDetectionEngine, mixed_type_data: pl.DataFrame
    ):
        """Should automatically exclude the string 'category' column."""
        result = engine.detect(mixed_type_data, algorithm="isolation_forest")
        assert len(result.labels) == mixed_type_data.height

    def test_explicit_feature_columns_override(
        self, engine: AnomalyDetectionEngine, mixed_type_data: pl.DataFrame
    ):
        result = engine.detect(
            mixed_type_data,
            algorithm="isolation_forest",
            feature_columns=["f0"],
        )
        assert len(result.labels) == mixed_type_data.height
