# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for DimReductionEngine -- PCA, NMF, t-SNE, UMAP."""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from kailash_ml.engines.dim_reduction import (
    DimReductionEngine,
    DimReductionResult,
    _detect_elbow,
    _sanitize_float,
)
from sklearn.datasets import make_classification

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine() -> DimReductionEngine:
    return DimReductionEngine()


@pytest.fixture()
def numeric_data() -> pl.DataFrame:
    """100-row dataset with 10 numeric features (some correlated for PCA)."""
    X, _ = make_classification(
        n_samples=100,
        n_features=10,
        n_informative=5,
        n_redundant=3,
        n_clusters_per_class=2,
        random_state=42,
    )
    data = {f"f{i}": X[:, i].tolist() for i in range(10)}
    return pl.DataFrame(data)


@pytest.fixture()
def nonneg_data() -> pl.DataFrame:
    """100-row dataset with 10 non-negative features (for NMF)."""
    rng = np.random.RandomState(42)
    # Use uniform [0.1, 1.1] to keep values small and well-conditioned
    X = rng.uniform(0.1, 1.1, size=(100, 10))
    data = {f"f{i}": X[:, i].tolist() for i in range(10)}
    return pl.DataFrame(data)


# ---------------------------------------------------------------------------
# DimReductionResult serialization
# ---------------------------------------------------------------------------


class TestDimReductionResult:
    def test_to_dict_from_dict_roundtrip(self) -> None:
        result = DimReductionResult(
            transformed=[[1.0, 2.0], [3.0, 4.0]],
            n_components=2,
            algorithm="pca",
            explained_variance_ratio=[0.6, 0.3],
            reconstruction_error=0.05,
            metrics={"cumulative_explained_variance": 0.9},
        )
        d = result.to_dict()
        restored = DimReductionResult.from_dict(d)
        assert restored.transformed == result.transformed
        assert restored.n_components == result.n_components
        assert restored.algorithm == result.algorithm
        assert restored.explained_variance_ratio == result.explained_variance_ratio
        assert restored.reconstruction_error == result.reconstruction_error
        assert restored.metrics == result.metrics

    def test_to_dict_none_fields(self) -> None:
        result = DimReductionResult(
            transformed=[[1.0]],
            n_components=1,
            algorithm="tsne",
            explained_variance_ratio=None,
            reconstruction_error=None,
            metrics={},
        )
        d = result.to_dict()
        assert d["explained_variance_ratio"] is None
        assert d["reconstruction_error"] is None
        restored = DimReductionResult.from_dict(d)
        assert restored.explained_variance_ratio is None
        assert restored.reconstruction_error is None

    def test_frozen_dataclass(self) -> None:
        result = DimReductionResult(
            transformed=[[1.0]],
            n_components=1,
            algorithm="pca",
            explained_variance_ratio=None,
            reconstruction_error=None,
            metrics={},
        )
        with pytest.raises(AttributeError):
            result.algorithm = "nmf"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


class TestSanitizeFloat:
    def test_finite(self) -> None:
        assert _sanitize_float(1.5) == 1.5

    def test_nan(self) -> None:
        assert _sanitize_float(float("nan")) is None

    def test_inf(self) -> None:
        assert _sanitize_float(float("inf")) is None

    def test_neg_inf(self) -> None:
        assert _sanitize_float(float("-inf")) is None

    def test_integer_coercion(self) -> None:
        assert _sanitize_float(3) == 3.0


class TestDetectElbow:
    def test_clear_elbow(self) -> None:
        # First component dominates, sharp dropoff -- elbow should be
        # in the first half where the curve bends.
        ratios = [0.7, 0.1, 0.05, 0.03, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01]
        elbow = _detect_elbow(ratios)
        assert 1 <= elbow <= 5

    def test_empty_ratios(self) -> None:
        assert _detect_elbow([]) == 1

    def test_single_component(self) -> None:
        assert _detect_elbow([1.0]) == 1

    def test_uniform_ratios(self) -> None:
        ratios = [0.1] * 10  # uniform -> cumulative crosses 0.95 at index 9
        elbow = _detect_elbow(ratios)
        assert 1 <= elbow <= 10


# ---------------------------------------------------------------------------
# PCA
# ---------------------------------------------------------------------------


class TestPCA:
    def test_basic_pca(
        self, engine: DimReductionEngine, numeric_data: pl.DataFrame
    ) -> None:
        result = engine.reduce(numeric_data, algorithm="pca", n_components=3)
        assert result.algorithm == "pca"
        assert result.n_components == 3
        assert len(result.transformed) == 100
        assert all(len(row) == 3 for row in result.transformed)
        assert result.explained_variance_ratio is not None
        assert len(result.explained_variance_ratio) == 3
        # Variance ratios should be positive and sum to <= 1
        assert all(r > 0 for r in result.explained_variance_ratio)
        assert sum(result.explained_variance_ratio) <= 1.0 + 1e-9
        assert result.reconstruction_error is not None
        assert result.reconstruction_error >= 0

    def test_pca_2d(
        self, engine: DimReductionEngine, numeric_data: pl.DataFrame
    ) -> None:
        result = engine.reduce(numeric_data, algorithm="pca", n_components=2)
        assert result.n_components == 2
        assert "cumulative_explained_variance" in result.metrics

    def test_pca_explained_variance_ordering(
        self, engine: DimReductionEngine, numeric_data: pl.DataFrame
    ) -> None:
        """Variance ratios must be in descending order (PCA contract)."""
        result = engine.reduce(numeric_data, algorithm="pca", n_components=5)
        assert result.explained_variance_ratio is not None
        for i in range(len(result.explained_variance_ratio) - 1):
            assert (
                result.explained_variance_ratio[i]
                >= result.explained_variance_ratio[i + 1]
            )

    def test_pca_full_components(
        self, engine: DimReductionEngine, numeric_data: pl.DataFrame
    ) -> None:
        """Using all components should explain ~100% variance."""
        result = engine.reduce(numeric_data, algorithm="pca", n_components=10)
        assert result.explained_variance_ratio is not None
        total = sum(result.explained_variance_ratio)
        assert total > 0.999

    def test_pca_select_columns(
        self, engine: DimReductionEngine, numeric_data: pl.DataFrame
    ) -> None:
        cols = ["f0", "f1", "f2"]
        result = engine.reduce(
            numeric_data, algorithm="pca", n_components=2, columns=cols
        )
        assert result.n_components == 2
        assert result.metrics["n_features_original"] == 3


# ---------------------------------------------------------------------------
# NMF
# ---------------------------------------------------------------------------


class TestNMF:
    def test_basic_nmf(
        self, engine: DimReductionEngine, nonneg_data: pl.DataFrame
    ) -> None:
        result = engine.reduce(nonneg_data, algorithm="nmf", n_components=3)
        assert result.algorithm == "nmf"
        assert result.n_components == 3
        assert len(result.transformed) == 100
        assert all(len(row) == 3 for row in result.transformed)
        # NMF output should be non-negative
        assert all(val >= 0 for row in result.transformed for val in row)
        assert result.explained_variance_ratio is None
        assert result.reconstruction_error is not None

    def test_nmf_negative_data_raises(
        self, engine: DimReductionEngine, numeric_data: pl.DataFrame
    ) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            engine.reduce(numeric_data, algorithm="nmf", n_components=2)

    def test_nmf_reconstruction_error(
        self, engine: DimReductionEngine, nonneg_data: pl.DataFrame
    ) -> None:
        """More components should yield lower reconstruction error."""
        result_2 = engine.reduce(nonneg_data, algorithm="nmf", n_components=2)
        result_5 = engine.reduce(nonneg_data, algorithm="nmf", n_components=5)
        assert result_2.reconstruction_error is not None
        assert result_5.reconstruction_error is not None
        assert result_5.reconstruction_error <= result_2.reconstruction_error


# ---------------------------------------------------------------------------
# t-SNE
# ---------------------------------------------------------------------------


class TestTSNE:
    def test_basic_tsne(
        self, engine: DimReductionEngine, numeric_data: pl.DataFrame
    ) -> None:
        result = engine.reduce(numeric_data, algorithm="tsne", n_components=2)
        assert result.algorithm == "tsne"
        assert result.n_components == 2
        assert len(result.transformed) == 100
        assert all(len(row) == 2 for row in result.transformed)
        assert result.explained_variance_ratio is None
        assert result.reconstruction_error is None
        assert "kl_divergence" in result.metrics

    def test_tsne_custom_perplexity(
        self, engine: DimReductionEngine, numeric_data: pl.DataFrame
    ) -> None:
        result = engine.reduce(
            numeric_data, algorithm="tsne", n_components=2, perplexity=10.0
        )
        assert result.metrics["perplexity"] == 10.0

    def test_tsne_perplexity_auto_clamp(self, engine: DimReductionEngine) -> None:
        """Small dataset: perplexity is auto-clamped to a safe value."""
        small = pl.DataFrame(
            {"a": [1.0, 2.0, 3.0, 4.0, 5.0], "b": [5.0, 4.0, 3.0, 2.0, 1.0]}
        )
        # Default perplexity=30 would fail with 5 samples; auto-clamp handles it
        result = engine.reduce(small, algorithm="tsne", n_components=2)
        assert result.n_components == 2
        assert result.metrics["perplexity"] <= 5.0


# ---------------------------------------------------------------------------
# UMAP
# ---------------------------------------------------------------------------


def _umap_available() -> bool:
    try:
        import umap  # noqa: F401

        return True
    except ImportError:
        return False


class TestUMAP:
    @pytest.mark.skipif(not _umap_available(), reason="umap-learn not installed")
    def test_basic_umap(
        self, engine: DimReductionEngine, numeric_data: pl.DataFrame
    ) -> None:
        result = engine.reduce(numeric_data, algorithm="umap", n_components=2)
        assert result.algorithm == "umap"
        assert result.n_components == 2
        assert len(result.transformed) == 100
        assert all(len(row) == 2 for row in result.transformed)
        assert result.explained_variance_ratio is None
        assert result.reconstruction_error is None
        assert "n_neighbors" in result.metrics

    @pytest.mark.skipif(not _umap_available(), reason="umap-learn not installed")
    def test_umap_custom_params(
        self, engine: DimReductionEngine, numeric_data: pl.DataFrame
    ) -> None:
        result = engine.reduce(
            numeric_data, algorithm="umap", n_components=3, n_neighbors=10, min_dist=0.2
        )
        assert result.n_components == 3
        assert result.metrics["n_neighbors"] == 10.0
        assert result.metrics["min_dist"] == 0.2

    def test_umap_import_error_message(self, engine: DimReductionEngine) -> None:
        """When umap-learn is not installed, error message points to the extra."""
        if _umap_available():
            pytest.skip("umap-learn is installed; cannot test ImportError path")
        data = pl.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]})
        with pytest.raises(ImportError, match="umap-learn"):
            engine.reduce(data, algorithm="umap", n_components=2)


# ---------------------------------------------------------------------------
# Variance analysis
# ---------------------------------------------------------------------------


class TestVarianceAnalysis:
    def test_variance_analysis(
        self, engine: DimReductionEngine, numeric_data: pl.DataFrame
    ) -> None:
        result = engine.variance_analysis(numeric_data)
        assert "explained_variance_ratio" in result
        assert "cumulative_variance" in result
        assert "elbow_component" in result
        assert "n_components_95" in result
        ratios = result["explained_variance_ratio"]
        cumulative = result["cumulative_variance"]
        assert len(ratios) == 10
        assert len(cumulative) == 10
        # Cumulative must be monotonically increasing
        for i in range(len(cumulative) - 1):
            assert cumulative[i + 1] >= cumulative[i]
        # Last cumulative should be ~1.0
        assert cumulative[-1] > 0.999
        assert 1 <= result["elbow_component"] <= 10
        assert 1 <= result["n_components_95"] <= 10

    def test_variance_analysis_select_columns(
        self, engine: DimReductionEngine, numeric_data: pl.DataFrame
    ) -> None:
        result = engine.variance_analysis(numeric_data, columns=["f0", "f1", "f2"])
        assert len(result["explained_variance_ratio"]) == 3


# ---------------------------------------------------------------------------
# Validation / edge cases
# ---------------------------------------------------------------------------


class TestValidation:
    def test_unsupported_algorithm(
        self, engine: DimReductionEngine, numeric_data: pl.DataFrame
    ) -> None:
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            engine.reduce(numeric_data, algorithm="lda", n_components=2)

    def test_n_components_too_large(
        self, engine: DimReductionEngine, numeric_data: pl.DataFrame
    ) -> None:
        with pytest.raises(ValueError, match="exceeds the number of features"):
            engine.reduce(numeric_data, algorithm="pca", n_components=20)

    def test_n_components_zero(
        self, engine: DimReductionEngine, numeric_data: pl.DataFrame
    ) -> None:
        with pytest.raises(ValueError, match="n_components must be >= 1"):
            engine.reduce(numeric_data, algorithm="pca", n_components=0)

    def test_empty_dataframe(self, engine: DimReductionEngine) -> None:
        empty = pl.DataFrame({"a": [], "b": []}).cast(
            {"a": pl.Float64, "b": pl.Float64}
        )
        with pytest.raises(ValueError, match="must not be empty"):
            engine.reduce(empty, algorithm="pca", n_components=1)

    def test_deterministic_with_seed(
        self, engine: DimReductionEngine, numeric_data: pl.DataFrame
    ) -> None:
        r1 = engine.reduce(numeric_data, algorithm="pca", n_components=2, seed=123)
        r2 = engine.reduce(numeric_data, algorithm="pca", n_components=2, seed=123)
        assert r1.transformed == r2.transformed
