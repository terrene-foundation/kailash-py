# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""DimReductionEngine -- dimensionality reduction via PCA, NMF, t-SNE, UMAP.

All data handling uses polars internally; conversion to numpy happens
at the sklearn boundary via ``interop.py``.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl
from kailash_ml.interop import to_sklearn_input

logger = logging.getLogger(__name__)

__all__ = [
    "DimReductionEngine",
    "DimReductionResult",
]

_SUPPORTED_ALGORITHMS = frozenset({"pca", "nmf", "tsne", "umap"})


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DimReductionResult:
    """Result of a dimensionality reduction operation."""

    transformed: list[list[float]]  # N x n_components
    n_components: int
    algorithm: str
    explained_variance_ratio: list[float] | None  # PCA only
    reconstruction_error: float | None  # PCA/NMF
    metrics: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "transformed": [list(row) for row in self.transformed],
            "n_components": self.n_components,
            "algorithm": self.algorithm,
            "explained_variance_ratio": (
                list(self.explained_variance_ratio)
                if self.explained_variance_ratio is not None
                else None
            ),
            "reconstruction_error": self.reconstruction_error,
            "metrics": dict(self.metrics),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DimReductionResult:
        return cls(
            transformed=data["transformed"],
            n_components=data["n_components"],
            algorithm=data["algorithm"],
            explained_variance_ratio=data.get("explained_variance_ratio"),
            reconstruction_error=data.get("reconstruction_error"),
            metrics=data.get("metrics", {}),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize_float(value: float) -> float | None:
    """Return *value* if finite, else ``None``.

    Guards all numeric outputs against NaN/Inf propagation -- same
    pattern used by ``DataExplorer._sanitize_float()``.
    """
    if isinstance(value, float) and math.isfinite(value):
        return value
    try:
        fval = float(value)
        return fval if math.isfinite(fval) else None
    except (TypeError, ValueError):
        return None


def _detect_elbow(ratios: list[float]) -> int:
    """Detect the elbow point in a cumulative explained-variance curve.

    Uses the maximum-distance-to-line heuristic (perpendicular distance
    from each point to the line connecting the first and last point on the
    cumulative curve).  Returns the 1-based component index of the elbow.

    Falls back to the component where cumulative variance first exceeds 0.95.
    """
    if not ratios:
        return 1

    cumulative = np.cumsum(ratios)
    n = len(cumulative)
    if n < 2:
        return 1

    # Line from first to last point on cumulative curve
    p1 = np.array([0.0, cumulative[0]])
    p2 = np.array([float(n - 1), cumulative[-1]])
    line_vec = p2 - p1
    line_len = np.linalg.norm(line_vec)

    if line_len < 1e-12:
        return 1

    # Perpendicular distance from each point to the line
    # Use the 2D cross-product formula directly to avoid the NumPy 2.0
    # deprecation warning for np.cross on 2D vectors.
    distances = np.zeros(n)
    lx, ly = line_vec[0], line_vec[1]
    for i in range(n):
        dx = p1[0] - float(i)
        dy = p1[1] - cumulative[i]
        distances[i] = abs(lx * dy - ly * dx) / line_len

    elbow_idx = int(np.argmax(distances))

    # Fallback: first component crossing 0.95 cumulative variance
    candidates = np.where(cumulative >= 0.95)[0]
    if len(candidates) > 0:
        threshold_idx = int(candidates[0])
        # Use whichever comes first
        elbow_idx = min(elbow_idx, threshold_idx)

    return elbow_idx + 1  # 1-based


# ---------------------------------------------------------------------------
# DimReductionEngine
# ---------------------------------------------------------------------------


class DimReductionEngine:
    """[P1: Production with Caveats] Dimensionality reduction -- PCA, NMF,
    t-SNE, UMAP.

    All methods accept polars DataFrames and convert at the sklearn boundary.
    UMAP requires the ``umap-learn`` optional dependency.
    """

    def reduce(
        self,
        data: pl.DataFrame,
        *,
        algorithm: str = "pca",
        n_components: int = 2,
        columns: list[str] | None = None,
        seed: int = 42,
        **kwargs: Any,
    ) -> DimReductionResult:
        """Reduce dimensionality of the input data.

        Parameters
        ----------
        data:
            Polars DataFrame containing numeric features.
        algorithm:
            One of ``"pca"``, ``"nmf"``, ``"tsne"``, ``"umap"``.
        n_components:
            Number of output dimensions.
        columns:
            Feature columns to use.  Defaults to all columns.
        seed:
            Random seed for reproducibility.
        **kwargs:
            Extra keyword arguments forwarded to the underlying algorithm
            (e.g. ``perplexity`` for t-SNE, ``n_neighbors`` for UMAP).
        """
        if algorithm not in _SUPPORTED_ALGORITHMS:
            raise ValueError(
                f"Unsupported algorithm '{algorithm}'. "
                f"Choose from: {', '.join(sorted(_SUPPORTED_ALGORITHMS))}"
            )
        if n_components < 1:
            raise ValueError(f"n_components must be >= 1, got {n_components}.")
        if data.height == 0:
            raise ValueError("Input data must not be empty.")

        # Convert polars -> numpy at the sklearn boundary
        X, _, _ = to_sklearn_input(data, feature_columns=columns)

        if n_components > X.shape[1]:
            raise ValueError(
                f"n_components ({n_components}) exceeds the number of "
                f"features ({X.shape[1]})."
            )

        dispatch = {
            "pca": self._reduce_pca,
            "nmf": self._reduce_nmf,
            "tsne": self._reduce_tsne,
            "umap": self._reduce_umap,
        }

        return dispatch[algorithm](X, n_components=n_components, seed=seed, **kwargs)

    def variance_analysis(
        self,
        data: pl.DataFrame,
        *,
        columns: list[str] | None = None,
    ) -> dict[str, Any]:
        """Analyse PCA variance structure without reducing.

        Returns a dict containing:
        - ``explained_variance_ratio``: per-component ratios
        - ``cumulative_variance``: cumulative sum
        - ``elbow_component``: suggested cutoff (1-based index)
        - ``n_components_95``: components needed for 95% variance
        """
        from sklearn.decomposition import PCA

        X, _, _ = to_sklearn_input(data, feature_columns=columns)
        pca = PCA(n_components=min(X.shape[0], X.shape[1]))
        pca.fit(X)

        ratios = pca.explained_variance_ratio_.tolist()
        cumulative = np.cumsum(ratios).tolist()

        # Components needed for 95% variance
        candidates_95 = [i + 1 for i, c in enumerate(cumulative) if c >= 0.95]
        n_95 = candidates_95[0] if candidates_95 else len(ratios)

        return {
            "explained_variance_ratio": ratios,
            "cumulative_variance": cumulative,
            "elbow_component": _detect_elbow(ratios),
            "n_components_95": n_95,
        }

    # ------------------------------------------------------------------
    # Algorithm implementations
    # ------------------------------------------------------------------

    def _reduce_pca(
        self,
        X: np.ndarray,
        *,
        n_components: int,
        seed: int,
        **kwargs: Any,
    ) -> DimReductionResult:
        from sklearn.decomposition import PCA

        pca = PCA(n_components=n_components, random_state=seed, **kwargs)
        X_transformed = pca.fit_transform(X)

        # Reconstruction error: mean squared error of inverse_transform
        X_reconstructed = pca.inverse_transform(X_transformed)
        reconstruction_error = float(np.mean((X - X_reconstructed) ** 2))

        ratios = pca.explained_variance_ratio_.tolist()
        cumulative_variance = float(np.sum(ratios))

        metrics: dict[str, float] = {
            "cumulative_explained_variance": cumulative_variance,
            "n_features_original": X.shape[1],
        }
        re_sanitized = _sanitize_float(reconstruction_error)
        if re_sanitized is not None:
            metrics["reconstruction_error"] = re_sanitized

        return DimReductionResult(
            transformed=X_transformed.tolist(),
            n_components=n_components,
            algorithm="pca",
            explained_variance_ratio=ratios,
            reconstruction_error=_sanitize_float(reconstruction_error),
            metrics=metrics,
        )

    def _reduce_nmf(
        self,
        X: np.ndarray,
        *,
        n_components: int,
        seed: int,
        **kwargs: Any,
    ) -> DimReductionResult:
        from sklearn.decomposition import NMF

        if np.any(X < 0):
            raise ValueError(
                "NMF requires non-negative input data. "
                "Consider using PCA for data with negative values."
            )

        nmf = NMF(n_components=n_components, random_state=seed, **kwargs)
        W = nmf.fit_transform(X)

        # Reconstruction error from NMF
        reconstruction_error = float(nmf.reconstruction_err_)

        metrics: dict[str, float] = {
            "n_features_original": X.shape[1],
            "n_iterations": float(nmf.n_iter_),
        }
        re_sanitized = _sanitize_float(reconstruction_error)
        if re_sanitized is not None:
            metrics["reconstruction_error"] = re_sanitized

        return DimReductionResult(
            transformed=W.tolist(),
            n_components=n_components,
            algorithm="nmf",
            explained_variance_ratio=None,
            reconstruction_error=_sanitize_float(reconstruction_error),
            metrics=metrics,
        )

    def _reduce_tsne(
        self,
        X: np.ndarray,
        *,
        n_components: int,
        seed: int,
        **kwargs: Any,
    ) -> DimReductionResult:
        from sklearn.manifold import TSNE

        # t-SNE defaults -- perplexity must be strictly less than n_samples
        max_perplexity = float(X.shape[0] - 1)
        default_perplexity = min(30.0, max(5.0, X.shape[0] / 4.0))
        perplexity = kwargs.pop("perplexity", min(default_perplexity, max_perplexity))
        max_iter = kwargs.pop("max_iter", kwargs.pop("n_iter", 1000))

        tsne = TSNE(
            n_components=n_components,
            perplexity=perplexity,
            max_iter=max_iter,
            random_state=seed,
            **kwargs,
        )
        X_transformed = tsne.fit_transform(X)

        kl_divergence = float(tsne.kl_divergence_)

        metrics: dict[str, float] = {
            "kl_divergence": kl_divergence,
            "n_features_original": X.shape[1],
            "perplexity": float(perplexity),
            "max_iter": float(max_iter),
        }

        return DimReductionResult(
            transformed=X_transformed.tolist(),
            n_components=n_components,
            algorithm="tsne",
            explained_variance_ratio=None,
            reconstruction_error=None,
            metrics=metrics,
        )

    def _reduce_umap(
        self,
        X: np.ndarray,
        *,
        n_components: int,
        seed: int,
        **kwargs: Any,
    ) -> DimReductionResult:
        try:
            import umap
        except ImportError:
            raise ImportError(
                "UMAP requires the 'umap-learn' package. "
                "Install it with: pip install kailash-ml[umap]"
            ) from None

        n_neighbors = kwargs.pop("n_neighbors", min(15, X.shape[0] - 1))
        min_dist = kwargs.pop("min_dist", 0.1)

        # umap-learn warns that `random_state` forces `n_jobs=1`; pre-set
        # the value so umap's "overridden to 1" UserWarning does not
        # fire. See umap_.py:1952 (umap-learn 0.5+). Same pattern as
        # UMAPTrainable in `trainable.py`.
        reducer = umap.UMAP(
            n_components=n_components,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            random_state=seed,
            n_jobs=kwargs.pop("n_jobs", 1),
            **kwargs,
        )
        X_transformed = reducer.fit_transform(X)

        metrics: dict[str, float] = {
            "n_features_original": X.shape[1],
            "n_neighbors": float(n_neighbors),
            "min_dist": float(min_dist),
        }

        return DimReductionResult(
            transformed=X_transformed.tolist(),
            n_components=n_components,
            algorithm="umap",
            explained_variance_ratio=None,
            reconstruction_error=None,
            metrics=metrics,
        )
