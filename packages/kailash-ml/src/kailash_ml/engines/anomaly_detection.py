# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""AnomalyDetectionEngine -- unsupervised anomaly detection via sklearn.

Supports Isolation Forest, Local Outlier Factor, and One-Class SVM.
All data handling uses polars internally; conversion to numpy happens
at the sklearn boundary via ``interop.py``.

Anomaly scores are normalized to [0, 1] regardless of algorithm, where
higher scores indicate stronger anomaly signal.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl
from kailash_ml.interop import to_sklearn_input

logger = logging.getLogger(__name__)

__all__ = [
    "AnomalyDetectionEngine",
    "AnomalyResult",
    "EnsembleAnomalyResult",
]

# ---------------------------------------------------------------------------
# Supported algorithms
# ---------------------------------------------------------------------------

_SUPPORTED_ALGORITHMS = frozenset({"isolation_forest", "lof", "one_class_svm"})


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnomalyResult:
    """Result of a single anomaly detection algorithm."""

    labels: list[int]  # 1 = normal, -1 = anomaly
    scores: list[float]  # normalized to [0, 1], higher = more anomalous
    n_anomalies: int
    contamination: float
    algorithm: str
    metrics: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "labels": list(self.labels),
            "scores": list(self.scores),
            "n_anomalies": self.n_anomalies,
            "contamination": self.contamination,
            "algorithm": self.algorithm,
            "metrics": dict(self.metrics),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnomalyResult:
        return cls(
            labels=data["labels"],
            scores=data["scores"],
            n_anomalies=data["n_anomalies"],
            contamination=data["contamination"],
            algorithm=data["algorithm"],
            metrics=data["metrics"],
        )


@dataclass(frozen=True)
class EnsembleAnomalyResult:
    """Result of running multiple anomaly detection algorithms and combining."""

    labels: list[int]  # 1 = normal, -1 = anomaly (combined)
    combined_scores: list[float]  # averaged/combined scores in [0, 1]
    component_results: list[AnomalyResult]
    voting: str  # "majority" or "score_average"

    def to_dict(self) -> dict[str, Any]:
        return {
            "labels": list(self.labels),
            "combined_scores": list(self.combined_scores),
            "component_results": [r.to_dict() for r in self.component_results],
            "voting": self.voting,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnsembleAnomalyResult:
        return cls(
            labels=data["labels"],
            combined_scores=data["combined_scores"],
            component_results=[
                AnomalyResult.from_dict(r) for r in data["component_results"]
            ],
            voting=data["voting"],
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_scores(raw_scores: np.ndarray) -> np.ndarray:
    """Normalize anomaly scores to [0, 1] range.

    Uses min-max normalization. If all scores are identical, returns 0.5
    for all samples (no anomaly signal).

    Parameters
    ----------
    raw_scores:
        Raw decision function or score_samples output from sklearn.
        Convention: sklearn anomaly detectors typically output lower/more-negative
        values for anomalies. We invert so higher = more anomalous.

    Returns
    -------
    Normalized scores in [0, 1] where higher = more anomalous.
    """
    # Invert: sklearn convention is lower = more anomalous
    inverted = -raw_scores
    smin = inverted.min()
    smax = inverted.max()
    if smax - smin < 1e-12:
        return np.full_like(inverted, 0.5, dtype=np.float64)
    return (inverted - smin) / (smax - smin)


def _compute_anomaly_metrics(
    labels: np.ndarray, scores: np.ndarray
) -> dict[str, float]:
    """Compute unsupervised anomaly detection metrics.

    Since anomaly detection is unsupervised, metrics are descriptive
    rather than accuracy-based.
    """
    n_total = len(labels)
    n_anomalies = int(np.sum(labels == -1))
    n_normal = int(np.sum(labels == 1))

    metrics: dict[str, float] = {
        "n_samples": float(n_total),
        "n_anomalies": float(n_anomalies),
        "n_normal": float(n_normal),
        "anomaly_ratio": float(n_anomalies / n_total) if n_total > 0 else 0.0,
        "mean_anomaly_score": float(np.mean(scores)),
        "std_anomaly_score": float(np.std(scores)),
    }

    # Score separation: mean score of anomalies vs normals
    if n_anomalies > 0 and n_normal > 0:
        anomaly_mask = labels == -1
        normal_mask = labels == 1
        metrics["mean_score_anomalies"] = float(np.mean(scores[anomaly_mask]))
        metrics["mean_score_normals"] = float(np.mean(scores[normal_mask]))
        metrics["score_separation"] = (
            metrics["mean_score_anomalies"] - metrics["mean_score_normals"]
        )

    return metrics


def _validate_algorithm(algorithm: str) -> None:
    """Validate that the algorithm name is supported."""
    if algorithm not in _SUPPORTED_ALGORITHMS:
        raise ValueError(
            f"Unsupported algorithm '{algorithm}'. "
            f"Supported: {sorted(_SUPPORTED_ALGORITHMS)}"
        )


def _validate_contamination(contamination: float) -> None:
    """Validate contamination parameter is in valid range."""
    if not (0.0 < contamination < 0.5):
        raise ValueError(f"contamination must be in (0, 0.5), got {contamination}")


# ---------------------------------------------------------------------------
# AnomalyDetectionEngine
# ---------------------------------------------------------------------------


class AnomalyDetectionEngine:
    """[P1: Production with Caveats] Unsupervised anomaly detection engine.

    Supports Isolation Forest, Local Outlier Factor (LOF), and One-Class SVM.
    All methods accept polars DataFrames and convert at the sklearn boundary.
    Anomaly scores are normalized to [0, 1] regardless of algorithm.

    Usage::

        from kailash_ml.engines.anomaly_detection import AnomalyDetectionEngine

        engine = AnomalyDetectionEngine()

        # Single algorithm
        result = engine.detect(data, algorithm="isolation_forest", contamination=0.1)

        # Ensemble (multiple algorithms combined)
        result = engine.ensemble_detect(
            data,
            algorithms=["isolation_forest", "lof"],
            voting="majority",
        )
    """

    def detect(
        self,
        data: pl.DataFrame,
        *,
        algorithm: str = "isolation_forest",
        contamination: float = 0.1,
        feature_columns: list[str] | None = None,
        seed: int = 42,
        **kwargs: Any,
    ) -> AnomalyResult:
        """Run anomaly detection on the provided data.

        Parameters
        ----------
        data:
            Polars DataFrame containing features.
        algorithm:
            One of ``"isolation_forest"``, ``"lof"``, ``"one_class_svm"``.
        contamination:
            Expected proportion of anomalies in the data. Must be in (0, 0.5).
        feature_columns:
            Optional list of column names to use as features. If ``None``,
            all numeric columns are used.
        seed:
            Random seed for reproducibility.
        **kwargs:
            Additional keyword arguments passed to the underlying sklearn
            estimator constructor.

        Returns
        -------
        AnomalyResult with labels, normalized scores, and metrics.
        """
        _validate_algorithm(algorithm)
        _validate_contamination(contamination)

        if data.height == 0:
            raise ValueError("Input DataFrame is empty.")

        # Select feature columns
        if feature_columns is None:
            from kailash_ml.engines._shared import NUMERIC_DTYPES

            feature_columns = [
                c for c in data.columns if data[c].dtype in NUMERIC_DTYPES
            ]
            if not feature_columns:
                raise ValueError(
                    "No numeric columns found in data. "
                    "Specify feature_columns explicitly."
                )

        X, _, _ = to_sklearn_input(data, feature_columns=feature_columns)

        model = self._build_model(algorithm, contamination, seed, **kwargs)
        labels = model.fit_predict(X)

        # Extract raw scores
        raw_scores = self._get_raw_scores(model, X, algorithm)
        normalized_scores = _normalize_scores(raw_scores)

        metrics = _compute_anomaly_metrics(labels, normalized_scores)

        logger.info(
            "anomaly_detection.detect.complete",
            extra={
                "algorithm": algorithm,
                "n_samples": data.height,
                "n_anomalies": int(np.sum(labels == -1)),
                "contamination": contamination,
            },
        )

        return AnomalyResult(
            labels=labels.tolist(),
            scores=normalized_scores.tolist(),
            n_anomalies=int(np.sum(labels == -1)),
            contamination=contamination,
            algorithm=algorithm,
            metrics=metrics,
        )

    def ensemble_detect(
        self,
        data: pl.DataFrame,
        *,
        algorithms: list[str] | None = None,
        contamination: float = 0.1,
        voting: str = "majority",
        feature_columns: list[str] | None = None,
        seed: int = 42,
        **kwargs: Any,
    ) -> EnsembleAnomalyResult:
        """Run multiple anomaly detection algorithms and combine results.

        Parameters
        ----------
        data:
            Polars DataFrame containing features.
        algorithms:
            List of algorithm names. Defaults to
            ``["isolation_forest", "lof"]``.
        contamination:
            Expected proportion of anomalies. Must be in (0, 0.5).
        voting:
            Combination strategy. ``"majority"`` uses majority voting on
            labels. ``"score_average"`` averages normalized scores and
            applies a threshold at 0.5.
        feature_columns:
            Optional list of column names to use as features. If ``None``,
            all numeric columns are used.
        seed:
            Random seed for reproducibility.
        **kwargs:
            Additional keyword arguments passed to each estimator.

        Returns
        -------
        EnsembleAnomalyResult with combined labels, scores, and per-algorithm
        results.
        """
        if voting not in ("majority", "score_average"):
            raise ValueError(
                f"voting must be 'majority' or 'score_average', got '{voting}'"
            )

        if algorithms is None:
            algorithms = ["isolation_forest", "lof"]

        if len(algorithms) < 2:
            raise ValueError(
                "ensemble_detect requires at least 2 algorithms, "
                f"got {len(algorithms)}."
            )

        for alg in algorithms:
            _validate_algorithm(alg)

        # Run each algorithm
        component_results: list[AnomalyResult] = []
        for alg in algorithms:
            result = self.detect(
                data,
                algorithm=alg,
                contamination=contamination,
                feature_columns=feature_columns,
                seed=seed,
                **kwargs,
            )
            component_results.append(result)

        n_samples = data.height

        # Combine results
        if voting == "majority":
            combined_labels, combined_scores = self._majority_vote(
                component_results, n_samples
            )
        else:
            combined_labels, combined_scores = self._score_average(
                component_results, n_samples
            )

        logger.info(
            "anomaly_detection.ensemble_detect.complete",
            extra={
                "algorithms": algorithms,
                "voting": voting,
                "n_samples": n_samples,
                "n_anomalies": int(np.sum(np.array(combined_labels) == -1)),
            },
        )

        return EnsembleAnomalyResult(
            labels=combined_labels,
            combined_scores=combined_scores,
            component_results=component_results,
            voting=voting,
        )

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _build_model(
        self,
        algorithm: str,
        contamination: float,
        seed: int,
        **kwargs: Any,
    ) -> Any:
        """Instantiate the sklearn anomaly detection model."""
        if algorithm == "isolation_forest":
            from sklearn.ensemble import IsolationForest

            return IsolationForest(
                contamination=contamination,
                random_state=seed,
                **kwargs,
            )
        elif algorithm == "lof":
            from sklearn.neighbors import LocalOutlierFactor

            return LocalOutlierFactor(
                contamination=contamination,
                novelty=False,
                **kwargs,
            )
        elif algorithm == "one_class_svm":
            from sklearn.svm import OneClassSVM

            # OneClassSVM uses nu parameter instead of contamination
            # nu is an upper bound on the fraction of training errors
            # and a lower bound on the fraction of support vectors
            return OneClassSVM(
                nu=contamination,
                **kwargs,
            )
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

    def _get_raw_scores(
        self,
        model: Any,
        X: np.ndarray,
        algorithm: str,
    ) -> np.ndarray:
        """Extract raw anomaly scores from the fitted model.

        Different sklearn estimators expose scores via different methods.
        """
        if algorithm == "isolation_forest":
            # decision_function: higher = more normal in IsolationForest
            return model.decision_function(X)
        elif algorithm == "lof":
            # LOF with novelty=False stores scores after fit_predict
            # negative_outlier_factor_: more negative = more anomalous
            return model.negative_outlier_factor_
        elif algorithm == "one_class_svm":
            # decision_function: higher = more normal
            return model.decision_function(X)
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

    def _majority_vote(
        self,
        results: list[AnomalyResult],
        n_samples: int,
    ) -> tuple[list[int], list[float]]:
        """Combine results via majority voting on labels."""
        all_labels = np.array([r.labels for r in results])  # shape: (n_algs, n_samples)
        all_scores = np.array([r.scores for r in results])

        # Sum labels: each algorithm votes +1 (normal) or -1 (anomaly)
        vote_sums = all_labels.sum(axis=0)
        # Majority: if sum <= 0, majority says anomaly
        combined_labels = np.where(vote_sums > 0, 1, -1)

        # Average the normalized scores for the combined score
        combined_scores = all_scores.mean(axis=0)

        return combined_labels.tolist(), combined_scores.tolist()

    def _score_average(
        self,
        results: list[AnomalyResult],
        n_samples: int,
    ) -> tuple[list[int], list[float]]:
        """Combine results by averaging normalized scores."""
        all_scores = np.array([r.scores for r in results])
        combined_scores = all_scores.mean(axis=0)

        # Threshold at 0.5: scores above 0.5 are anomalies
        combined_labels = np.where(combined_scores > 0.5, -1, 1)

        return combined_labels.tolist(), combined_scores.tolist()
