# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for ClusteringEngine -- KMeans, DBSCAN, GMM, Spectral."""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from kailash_ml.engines.clustering import (
    ClusteringEngine,
    ClusterResult,
    KSweepResult,
    _compute_cluster_metrics,
    _sanitize_float,
    _to_numpy,
)
from sklearn.datasets import make_blobs

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine() -> ClusteringEngine:
    return ClusteringEngine()


@pytest.fixture()
def blob_data_3() -> pl.DataFrame:
    """150-row dataset with 3 well-separated blobs and 4 features."""
    X, _ = make_blobs(
        n_samples=150,
        n_features=4,
        centers=3,
        cluster_std=0.5,
        random_state=42,
    )
    data = {f"f{i}": X[:, i].tolist() for i in range(4)}
    return pl.DataFrame(data)


@pytest.fixture()
def blob_data_5() -> pl.DataFrame:
    """200-row dataset with 5 well-separated blobs and 3 features."""
    X, _ = make_blobs(
        n_samples=200,
        n_features=3,
        centers=5,
        cluster_std=0.4,
        random_state=99,
    )
    data = {f"f{i}": X[:, i].tolist() for i in range(3)}
    return pl.DataFrame(data)


@pytest.fixture()
def mixed_dtype_data() -> pl.DataFrame:
    """DataFrame with numeric and non-numeric columns."""
    X, _ = make_blobs(n_samples=50, n_features=2, centers=2, random_state=7)
    return pl.DataFrame(
        {
            "f0": X[:, 0].tolist(),
            "f1": X[:, 1].tolist(),
            "label": ["a", "b"] * 25,
        }
    )


# ---------------------------------------------------------------------------
# KMeans
# ---------------------------------------------------------------------------


class TestKMeans:
    def test_fit_returns_cluster_result(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="kmeans", n_clusters=3)
        assert isinstance(result, ClusterResult)
        assert result.algorithm == "kmeans"
        assert result.n_clusters == 3
        assert len(result.labels) == len(blob_data_3)

    def test_silhouette_score_high_for_clean_blobs(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="kmeans", n_clusters=3)
        assert result.silhouette_score is not None
        assert result.silhouette_score > 0.5

    def test_calinski_harabasz_present(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="kmeans", n_clusters=3)
        assert result.calinski_harabasz_score is not None
        assert result.calinski_harabasz_score > 0

    def test_inertia_present(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="kmeans", n_clusters=3)
        assert result.inertia is not None
        assert result.inertia >= 0

    def test_metrics_dict_populated(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="kmeans", n_clusters=3)
        assert "silhouette" in result.metrics
        assert "calinski_harabasz" in result.metrics
        assert "inertia" in result.metrics

    def test_labels_are_valid(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="kmeans", n_clusters=3)
        unique_labels = set(result.labels)
        assert unique_labels == {0, 1, 2}

    def test_random_state_reproducibility(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        r1 = engine.fit(blob_data_3, algorithm="kmeans", n_clusters=3, random_state=0)
        r2 = engine.fit(blob_data_3, algorithm="kmeans", n_clusters=3, random_state=0)
        assert r1.labels == r2.labels


# ---------------------------------------------------------------------------
# DBSCAN
# ---------------------------------------------------------------------------


class TestDBSCAN:
    def test_fit_returns_cluster_result(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="dbscan", eps=1.0, min_samples=5)
        assert isinstance(result, ClusterResult)
        assert result.algorithm == "dbscan"

    def test_discovers_clusters(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="dbscan", eps=1.0, min_samples=5)
        # Well-separated blobs should produce at least 2 clusters
        assert result.n_clusters >= 2

    def test_inertia_is_none(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="dbscan", eps=1.0)
        assert result.inertia is None

    def test_noise_points_in_metrics(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="dbscan", eps=1.0)
        assert "n_noise_points" in result.metrics
        assert result.metrics["n_noise_points"] >= 0

    def test_noise_labels_are_minus_one(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="dbscan", eps=0.1, min_samples=100)
        # With very strict params, most points are noise
        assert -1 in result.labels


# ---------------------------------------------------------------------------
# GMM
# ---------------------------------------------------------------------------


class TestGMM:
    def test_fit_returns_cluster_result(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="gmm", n_clusters=3)
        assert isinstance(result, ClusterResult)
        assert result.algorithm == "gmm"
        assert result.n_clusters == 3

    def test_bic_and_aic_in_metrics(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="gmm", n_clusters=3)
        assert "bic" in result.metrics
        assert "aic" in result.metrics

    def test_inertia_is_none(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="gmm", n_clusters=3)
        assert result.inertia is None

    def test_silhouette_present(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="gmm", n_clusters=3)
        assert result.silhouette_score is not None

    def test_kwargs_forwarded(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        # covariance_type is forwarded to GaussianMixture
        result = engine.fit(
            blob_data_3, algorithm="gmm", n_clusters=3, covariance_type="diag"
        )
        assert result.n_clusters == 3


# ---------------------------------------------------------------------------
# Spectral
# ---------------------------------------------------------------------------


class TestSpectral:
    def test_fit_returns_cluster_result(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="spectral", n_clusters=3)
        assert isinstance(result, ClusterResult)
        assert result.algorithm == "spectral"
        assert result.n_clusters == 3

    def test_inertia_is_none(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="spectral", n_clusters=3)
        assert result.inertia is None

    def test_labels_valid(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="spectral", n_clusters=3)
        assert len(result.labels) == len(blob_data_3)
        unique = set(result.labels)
        assert len(unique) == 3


# ---------------------------------------------------------------------------
# K-Sweep
# ---------------------------------------------------------------------------


class TestKSweep:
    def test_sweep_returns_ksweep_result(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        sweep = engine.sweep_k(blob_data_3, k_range=range(2, 6))
        assert isinstance(sweep, KSweepResult)
        assert len(sweep.results) == 4
        assert sweep.criterion == "silhouette"

    def test_optimal_k_matches_ground_truth(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        sweep = engine.sweep_k(blob_data_3, k_range=range(2, 7))
        # With well-separated 3-blob data, optimal k should be 3
        assert sweep.optimal_k == 3

    def test_sweep_with_calinski_criterion(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        sweep = engine.sweep_k(
            blob_data_3, k_range=range(2, 6), criterion="calinski_harabasz"
        )
        assert sweep.criterion == "calinski_harabasz"
        assert sweep.optimal_k in range(2, 6)

    def test_sweep_with_gmm(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        sweep = engine.sweep_k(blob_data_3, k_range=range(2, 5), algorithm="gmm")
        assert len(sweep.results) == 3
        assert all(r.algorithm == "gmm" for r in sweep.results)

    def test_sweep_rejects_dbscan(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        with pytest.raises(ValueError, match="DBSCAN"):
            engine.sweep_k(blob_data_3, algorithm="dbscan")

    def test_sweep_rejects_invalid_criterion(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        with pytest.raises(ValueError, match="criterion"):
            engine.sweep_k(blob_data_3, criterion="inertia")


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_cluster_result_roundtrip(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="kmeans", n_clusters=3)
        d = result.to_dict()
        restored = ClusterResult.from_dict(d)

        assert restored.labels == result.labels
        assert restored.n_clusters == result.n_clusters
        assert restored.algorithm == result.algorithm
        assert restored.silhouette_score == result.silhouette_score
        assert restored.calinski_harabasz_score == result.calinski_harabasz_score
        assert restored.inertia == result.inertia
        assert restored.metrics == result.metrics

    def test_to_dict_contains_all_fields(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="kmeans", n_clusters=3)
        d = result.to_dict()
        assert set(d.keys()) == {
            "labels",
            "n_clusters",
            "algorithm",
            "silhouette_score",
            "calinski_harabasz_score",
            "inertia",
            "metrics",
        }

    def test_from_dict_with_missing_optional_fields(self) -> None:
        d = {
            "labels": [0, 1, 0],
            "n_clusters": 2,
            "algorithm": "kmeans",
        }
        result = ClusterResult.from_dict(d)
        assert result.silhouette_score is None
        assert result.calinski_harabasz_score is None
        assert result.inertia is None
        assert result.metrics == {}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_unsupported_algorithm_raises(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            engine.fit(blob_data_3, algorithm="birch")

    def test_empty_dataframe_raises(self, engine: ClusteringEngine) -> None:
        empty = pl.DataFrame({"f0": [], "f1": []}).cast(
            {"f0": pl.Float64, "f1": pl.Float64}
        )
        with pytest.raises(ValueError, match="empty"):
            engine.fit(empty, algorithm="kmeans", n_clusters=2)

    def test_no_numeric_columns_raises(self, engine: ClusteringEngine) -> None:
        df = pl.DataFrame({"a": ["x", "y", "z"], "b": ["p", "q", "r"]})
        with pytest.raises(ValueError, match="No numeric columns"):
            engine.fit(df, algorithm="kmeans", n_clusters=2)

    def test_mixed_dtype_excludes_non_numeric(
        self, engine: ClusteringEngine, mixed_dtype_data: pl.DataFrame
    ) -> None:
        result = engine.fit(mixed_dtype_data, algorithm="kmeans", n_clusters=2)
        assert len(result.labels) == len(mixed_dtype_data)

    def test_single_cluster_metrics_are_none(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="kmeans", n_clusters=1)
        assert result.silhouette_score is None
        assert result.calinski_harabasz_score is None

    def test_case_insensitive_algorithm(
        self, engine: ClusteringEngine, blob_data_3: pl.DataFrame
    ) -> None:
        result = engine.fit(blob_data_3, algorithm="KMeans", n_clusters=3)
        assert result.algorithm == "kmeans"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_sanitize_float_finite(self) -> None:
        assert _sanitize_float(1.5) == 1.5
        assert _sanitize_float(0.0) == 0.0
        assert _sanitize_float(-3.14) == -3.14

    def test_sanitize_float_nonfinite(self) -> None:
        assert _sanitize_float(float("inf")) is None
        assert _sanitize_float(float("-inf")) is None
        assert _sanitize_float(float("nan")) is None

    def test_compute_cluster_metrics_single_cluster(self) -> None:
        X = np.array([[1, 2], [3, 4], [5, 6]])
        labels = np.array([0, 0, 0])
        metrics = _compute_cluster_metrics(X, labels)
        assert metrics["silhouette"] is None
        assert metrics["calinski_harabasz"] is None

    def test_compute_cluster_metrics_two_clusters(self) -> None:
        X = np.array([[0, 0], [0, 1], [10, 10], [10, 11]])
        labels = np.array([0, 0, 1, 1])
        metrics = _compute_cluster_metrics(X, labels)
        assert metrics["silhouette"] is not None
        assert metrics["silhouette"] > 0.5

    def test_to_numpy_selects_numeric(self) -> None:
        df = pl.DataFrame(
            {
                "num1": [1.0, 2.0],
                "num2": [3.0, 4.0],
                "text": ["a", "b"],
            }
        )
        X = _to_numpy(df)
        assert X.shape == (2, 2)
