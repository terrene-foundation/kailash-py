# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ClusteringEngine -- unsupervised clustering via KMeans, DBSCAN, GMM, Spectral.

All data handling uses polars internally; conversion to numpy happens at
the sklearn boundary via ``interop.py``.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl
from kailash_ml.engines._shared import NUMERIC_DTYPES
from kailash_ml.interop import to_sklearn_input

logger = logging.getLogger(__name__)

__all__ = [
    "ClusteringEngine",
    "ClusterResult",
    "KSweepResult",
]

# ---------------------------------------------------------------------------
# Supported algorithms
# ---------------------------------------------------------------------------

_SUPPORTED_ALGORITHMS = frozenset({"kmeans", "dbscan", "gmm", "spectral"})


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClusterResult:
    """Result of fitting a clustering algorithm."""

    labels: list[int]
    n_clusters: int
    algorithm: str
    silhouette_score: float | None
    calinski_harabasz_score: float | None
    inertia: float | None  # KMeans only
    metrics: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "labels": list(self.labels),
            "n_clusters": self.n_clusters,
            "algorithm": self.algorithm,
            "silhouette_score": self.silhouette_score,
            "calinski_harabasz_score": self.calinski_harabasz_score,
            "inertia": self.inertia,
            "metrics": dict(self.metrics),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClusterResult:
        return cls(
            labels=data["labels"],
            n_clusters=data["n_clusters"],
            algorithm=data["algorithm"],
            silhouette_score=data.get("silhouette_score"),
            calinski_harabasz_score=data.get("calinski_harabasz_score"),
            inertia=data.get("inertia"),
            metrics=data.get("metrics", {}),
        )


@dataclass(frozen=True)
class KSweepResult:
    """Result of sweeping across a range of k values."""

    results: list[ClusterResult]
    optimal_k: int
    criterion: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sanitize_float(value: float) -> float | None:
    """Return None for non-finite values, matching DataExplorer convention."""
    if value is None or not math.isfinite(value):
        return None
    return float(value)


def _compute_cluster_metrics(
    X: np.ndarray,
    labels: np.ndarray,
) -> dict[str, float | None]:
    """Compute silhouette and Calinski-Harabasz scores.

    Returns a dict with keys ``silhouette`` and ``calinski_harabasz``.
    Values are None when the metric cannot be computed (e.g. single cluster
    or all points in one cluster).
    """
    from sklearn.metrics import calinski_harabasz_score, silhouette_score

    n_labels = len(set(labels)) - (1 if -1 in labels else 0)

    # Metrics require at least 2 clusters and more samples than clusters
    if n_labels < 2 or n_labels >= len(X):
        return {"silhouette": None, "calinski_harabasz": None}

    sil = _sanitize_float(silhouette_score(X, labels))
    ch = _sanitize_float(calinski_harabasz_score(X, labels))

    return {"silhouette": sil, "calinski_harabasz": ch}


def _to_numpy(data: pl.DataFrame) -> np.ndarray:
    """Convert a polars DataFrame to a numpy array, selecting only numeric columns."""
    numeric_cols = [
        col
        for col, dtype in zip(data.columns, data.dtypes)
        if isinstance(dtype, type)
        and issubclass(dtype, NUMERIC_DTYPES)
        or isinstance(dtype, NUMERIC_DTYPES)
    ]
    if not numeric_cols:
        raise ValueError(
            "No numeric columns found in DataFrame. "
            "Clustering requires at least one numeric feature."
        )
    X, _, _ = to_sklearn_input(data.select(numeric_cols))
    return X


# ---------------------------------------------------------------------------
# ClusteringEngine
# ---------------------------------------------------------------------------


class ClusteringEngine:
    """[P1: Production with Caveats] Unsupervised clustering engine.

    Supports KMeans, DBSCAN, Gaussian Mixture Models (GMM), and
    Spectral Clustering. All methods accept polars DataFrames and
    convert at the sklearn boundary.

    Example::

        engine = ClusteringEngine()
        result = engine.fit(df, algorithm="kmeans", n_clusters=5)
        sweep = engine.sweep_k(df, k_range=range(2, 11))
    """

    def fit(
        self,
        data: pl.DataFrame,
        algorithm: str = "kmeans",
        n_clusters: int = 3,
        **kwargs: Any,
    ) -> ClusterResult:
        """Fit a clustering algorithm to the data.

        Parameters
        ----------
        data:
            Polars DataFrame with numeric features. Non-numeric columns
            are silently excluded.
        algorithm:
            One of ``"kmeans"``, ``"dbscan"``, ``"gmm"``, ``"spectral"``.
        n_clusters:
            Number of clusters (ignored by DBSCAN which determines this
            automatically).
        **kwargs:
            Additional keyword arguments passed to the sklearn estimator.
            For example, ``eps`` and ``min_samples`` for DBSCAN, or
            ``covariance_type`` for GMM.

        Returns
        -------
        ClusterResult
            Frozen dataclass with labels, metrics, and algorithm metadata.

        Raises
        ------
        ValueError
            If ``algorithm`` is not supported or data has no numeric columns.
        """
        algorithm = algorithm.lower()
        if algorithm not in _SUPPORTED_ALGORITHMS:
            raise ValueError(
                f"Unsupported algorithm '{algorithm}'. "
                f"Choose from: {sorted(_SUPPORTED_ALGORITHMS)}"
            )

        if data.is_empty():
            raise ValueError("Cannot cluster an empty DataFrame.")

        X = _to_numpy(data)

        if algorithm == "kmeans":
            return self._fit_kmeans(X, n_clusters, **kwargs)
        elif algorithm == "dbscan":
            return self._fit_dbscan(X, **kwargs)
        elif algorithm == "gmm":
            return self._fit_gmm(X, n_clusters, **kwargs)
        elif algorithm == "spectral":
            return self._fit_spectral(X, n_clusters, **kwargs)
        # Unreachable due to validation above, but satisfies exhaustiveness
        raise ValueError(f"Unsupported algorithm '{algorithm}'.")  # pragma: no cover

    def sweep_k(
        self,
        data: pl.DataFrame,
        k_range: range = range(2, 11),
        algorithm: str = "kmeans",
        criterion: str = "silhouette",
        **kwargs: Any,
    ) -> KSweepResult:
        """Sweep across a range of k values to find the optimal cluster count.

        Parameters
        ----------
        data:
            Polars DataFrame with numeric features.
        k_range:
            Range of k values to try.
        algorithm:
            Clustering algorithm to use. Must support ``n_clusters``
            (i.e. not DBSCAN).
        criterion:
            Metric used to select optimal k. ``"silhouette"`` (higher is
            better) or ``"calinski_harabasz"`` (higher is better).
        **kwargs:
            Additional keyword arguments passed to the clustering algorithm.

        Returns
        -------
        KSweepResult
            Contains all per-k results plus the optimal k.
        """
        if algorithm.lower() == "dbscan":
            raise ValueError(
                "sweep_k does not support DBSCAN because it does not accept "
                "n_clusters. Use fit() with DBSCAN directly."
            )

        if criterion not in ("silhouette", "calinski_harabasz"):
            raise ValueError(
                f"criterion must be 'silhouette' or 'calinski_harabasz', "
                f"got '{criterion}'."
            )

        results: list[ClusterResult] = []
        for k in k_range:
            result = self.fit(data, algorithm=algorithm, n_clusters=k, **kwargs)
            results.append(result)

        # Find optimal k based on criterion
        best_k = k_range.start
        best_score = -float("inf")

        for result in results:
            score = result.metrics.get(criterion)
            if score is not None and score > best_score:
                best_score = score
                best_k = result.n_clusters

        return KSweepResult(
            results=results,
            optimal_k=best_k,
            criterion=criterion,
        )

    # -----------------------------------------------------------------------
    # Algorithm implementations
    # -----------------------------------------------------------------------

    def _fit_kmeans(
        self,
        X: np.ndarray,
        n_clusters: int,
        **kwargs: Any,
    ) -> ClusterResult:
        from sklearn.cluster import KMeans

        seed = kwargs.pop("random_state", 42)
        model = KMeans(
            n_clusters=n_clusters, random_state=seed, n_init="auto", **kwargs
        )
        labels = model.fit_predict(X)
        inertia = _sanitize_float(model.inertia_)

        cluster_metrics = _compute_cluster_metrics(X, labels)

        metrics: dict[str, float] = {}
        if cluster_metrics["silhouette"] is not None:
            metrics["silhouette"] = cluster_metrics["silhouette"]
        if cluster_metrics["calinski_harabasz"] is not None:
            metrics["calinski_harabasz"] = cluster_metrics["calinski_harabasz"]
        if inertia is not None:
            metrics["inertia"] = inertia

        return ClusterResult(
            labels=labels.tolist(),
            n_clusters=n_clusters,
            algorithm="kmeans",
            silhouette_score=cluster_metrics["silhouette"],
            calinski_harabasz_score=cluster_metrics["calinski_harabasz"],
            inertia=inertia,
            metrics=metrics,
        )

    def _fit_dbscan(
        self,
        X: np.ndarray,
        **kwargs: Any,
    ) -> ClusterResult:
        from sklearn.cluster import DBSCAN

        model = DBSCAN(**kwargs)
        labels = model.fit_predict(X)

        # DBSCAN labels: -1 = noise
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)

        cluster_metrics = _compute_cluster_metrics(X, labels)

        metrics: dict[str, float] = {}
        if cluster_metrics["silhouette"] is not None:
            metrics["silhouette"] = cluster_metrics["silhouette"]
        if cluster_metrics["calinski_harabasz"] is not None:
            metrics["calinski_harabasz"] = cluster_metrics["calinski_harabasz"]
        metrics["n_noise_points"] = float(int(np.sum(labels == -1)))

        return ClusterResult(
            labels=labels.tolist(),
            n_clusters=n_clusters,
            algorithm="dbscan",
            silhouette_score=cluster_metrics["silhouette"],
            calinski_harabasz_score=cluster_metrics["calinski_harabasz"],
            inertia=None,
            metrics=metrics,
        )

    def _fit_gmm(
        self,
        X: np.ndarray,
        n_clusters: int,
        **kwargs: Any,
    ) -> ClusterResult:
        from sklearn.mixture import GaussianMixture

        seed = kwargs.pop("random_state", 42)
        model = GaussianMixture(n_components=n_clusters, random_state=seed, **kwargs)
        labels = model.fit_predict(X)

        cluster_metrics = _compute_cluster_metrics(X, labels)

        bic = _sanitize_float(model.bic(X))
        aic = _sanitize_float(model.aic(X))

        metrics: dict[str, float] = {}
        if cluster_metrics["silhouette"] is not None:
            metrics["silhouette"] = cluster_metrics["silhouette"]
        if cluster_metrics["calinski_harabasz"] is not None:
            metrics["calinski_harabasz"] = cluster_metrics["calinski_harabasz"]
        if bic is not None:
            metrics["bic"] = bic
        if aic is not None:
            metrics["aic"] = aic

        return ClusterResult(
            labels=labels.tolist(),
            n_clusters=n_clusters,
            algorithm="gmm",
            silhouette_score=cluster_metrics["silhouette"],
            calinski_harabasz_score=cluster_metrics["calinski_harabasz"],
            inertia=None,
            metrics=metrics,
        )

    def _fit_spectral(
        self,
        X: np.ndarray,
        n_clusters: int,
        **kwargs: Any,
    ) -> ClusterResult:
        from sklearn.cluster import SpectralClustering

        seed = kwargs.pop("random_state", 42)
        model = SpectralClustering(
            n_clusters=n_clusters,
            random_state=seed,
            affinity="nearest_neighbors",
            **kwargs,
        )
        labels = model.fit_predict(X)

        cluster_metrics = _compute_cluster_metrics(X, labels)

        metrics: dict[str, float] = {}
        if cluster_metrics["silhouette"] is not None:
            metrics["silhouette"] = cluster_metrics["silhouette"]
        if cluster_metrics["calinski_harabasz"] is not None:
            metrics["calinski_harabasz"] = cluster_metrics["calinski_harabasz"]

        return ClusterResult(
            labels=labels.tolist(),
            n_clusters=n_clusters,
            algorithm="spectral",
            silhouette_score=cluster_metrics["silhouette"],
            calinski_harabasz_score=cluster_metrics["calinski_harabasz"],
            inertia=None,
            metrics=metrics,
        )
