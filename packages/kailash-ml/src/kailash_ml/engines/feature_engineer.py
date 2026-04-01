# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""FeatureEngineer engine -- automated feature generation + selection.

Generates candidate features (interactions, polynomial, binning, temporal)
from source data, evaluates them, and selects the best subset.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl
from kailash_ml_protocols import FeatureSchema

from kailash_ml._decorators import experimental

logger = logging.getLogger(__name__)

__all__ = [
    "FeatureEngineer",
    "GeneratedColumn",
    "GeneratedFeatures",
    "FeatureRank",
    "SelectedFeatures",
]


# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------


@dataclass
class GeneratedColumn:
    """A single generated feature column."""

    name: str
    source_columns: list[str]
    strategy: str  # "interaction", "polynomial", "binning", "temporal"
    dtype: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source_columns": list(self.source_columns),
            "strategy": self.strategy,
            "dtype": self.dtype,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GeneratedColumn:
        return cls(
            name=data["name"],
            source_columns=data["source_columns"],
            strategy=data["strategy"],
            dtype=data["dtype"],
        )


@dataclass
class GeneratedFeatures:
    """Result of feature generation."""

    original_columns: list[str]
    generated_columns: list[GeneratedColumn]
    total_candidates: int
    data: pl.DataFrame

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_columns": list(self.original_columns),
            "generated_columns": [g.to_dict() for g in self.generated_columns],
            "total_candidates": self.total_candidates,
            "data": None,  # polars DataFrame is not JSON-serializable
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GeneratedFeatures:
        return cls(
            original_columns=data["original_columns"],
            generated_columns=[
                GeneratedColumn.from_dict(g) for g in data["generated_columns"]
            ],
            total_candidates=data["total_candidates"],
            data=pl.DataFrame(),  # DataFrame cannot be restored from serialized form
        )


@dataclass
class FeatureRank:
    """Ranking of a single feature."""

    column_name: str
    score: float
    rank: int
    source: str  # "original" or "generated"

    def to_dict(self) -> dict[str, Any]:
        return {
            "column_name": self.column_name,
            "score": self.score,
            "rank": self.rank,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeatureRank:
        return cls(
            column_name=data["column_name"],
            score=data["score"],
            rank=data["rank"],
            source=data["source"],
        )


@dataclass
class SelectedFeatures:
    """Result of feature selection."""

    selected_columns: list[str]
    rankings: list[FeatureRank]
    dropped_columns: list[str]
    method: str
    n_original: int
    n_generated: int
    n_selected: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_columns": list(self.selected_columns),
            "rankings": [r.to_dict() for r in self.rankings],
            "dropped_columns": list(self.dropped_columns),
            "method": self.method,
            "n_original": self.n_original,
            "n_generated": self.n_generated,
            "n_selected": self.n_selected,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SelectedFeatures:
        return cls(
            selected_columns=data["selected_columns"],
            rankings=[FeatureRank.from_dict(r) for r in data["rankings"]],
            dropped_columns=data["dropped_columns"],
            method=data["method"],
            n_original=data["n_original"],
            n_generated=data["n_generated"],
            n_selected=data["n_selected"],
        )


# ---------------------------------------------------------------------------
# Numeric dtype helpers
# ---------------------------------------------------------------------------

from kailash_ml.engines._shared import NUMERIC_DTYPES as _NUMERIC_DTYPES


# ---------------------------------------------------------------------------
# FeatureEngineer
# ---------------------------------------------------------------------------


@experimental
class FeatureEngineer:
    """[P2: Experimental] Automated feature generation and selection engine.

    Generates candidate features (interactions, polynomial, binning) from
    source data, evaluates them using statistical tests and model-based
    importance, and selects the best subset. API may change in future versions.

    Parameters
    ----------
    feature_store:
        Optional FeatureStore for persisting selected features.
    max_features:
        Maximum number of features to keep during selection.
    """

    def __init__(
        self,
        feature_store: Any | None = None,
        *,
        max_features: int = 50,
    ) -> None:
        self._feature_store = feature_store
        self._max_features = max_features

    def generate(
        self,
        data: pl.DataFrame,
        schema: FeatureSchema,
        *,
        strategies: list[str] | None = None,
    ) -> GeneratedFeatures:
        """Generate candidate features using specified strategies.

        All generation uses polars expressions. No pandas.
        """
        strategies = strategies or ["interactions", "polynomial", "binning"]
        generated: list[GeneratedColumn] = []
        result_df = data.clone()

        numeric_cols = [
            f.name
            for f in schema.features
            if f.dtype in ("float64", "int64", "float32", "int32")
            and f.name in data.columns
            and data[f.name].dtype in _NUMERIC_DTYPES
        ]
        datetime_cols = [
            f.name
            for f in schema.features
            if f.dtype == "datetime" and f.name in data.columns
        ]

        if "interactions" in strategies and len(numeric_cols) >= 2:
            for i, col_a in enumerate(numeric_cols):
                for col_b in numeric_cols[i + 1 :]:
                    name = f"{col_a}_x_{col_b}"
                    result_df = result_df.with_columns(
                        (
                            pl.col(col_a).fill_null(0.0) * pl.col(col_b).fill_null(0.0)
                        ).alias(name)
                    )
                    generated.append(
                        GeneratedColumn(name, [col_a, col_b], "interaction", "float64")
                    )

        if "polynomial" in strategies:
            for col in numeric_cols:
                name = f"{col}_squared"
                result_df = result_df.with_columns(
                    (pl.col(col).fill_null(0.0) ** 2).alias(name)
                )
                generated.append(GeneratedColumn(name, [col], "polynomial", "float64"))

        if "binning" in strategies:
            for col in numeric_cols:
                name = f"{col}_binned"
                try:
                    labels = [f"q{i}" for i in range(5)]
                    result_df = result_df.with_columns(
                        pl.col(col).qcut(5, labels=labels).alias(name)
                    )
                    generated.append(
                        GeneratedColumn(name, [col], "binning", "categorical")
                    )
                except Exception:
                    # qcut can fail on constant columns
                    logger.debug("Binning failed for column %s", col)

        if "temporal" in strategies:
            for col in datetime_cols:
                for component, expr in [
                    ("dow", pl.col(col).dt.weekday()),
                    ("hour", pl.col(col).dt.hour()),
                    ("month", pl.col(col).dt.month()),
                ]:
                    name = f"{col}_{component}"
                    result_df = result_df.with_columns(expr.alias(name))
                    generated.append(GeneratedColumn(name, [col], "temporal", "int64"))

        return GeneratedFeatures(
            original_columns=[f.name for f in schema.features],
            generated_columns=generated,
            total_candidates=len(schema.features) + len(generated),
            data=result_df,
        )

    def select(
        self,
        data: pl.DataFrame,
        candidates: GeneratedFeatures,
        target: str,
        *,
        method: str = "importance",
        top_k: int | None = None,
    ) -> SelectedFeatures:
        """Select best features from candidates.

        Uses tree-based importance (sklearn) by default.
        """
        top_k = top_k or self._max_features
        generated_names = {g.name for g in candidates.generated_columns}
        feature_cols = [
            c
            for c in candidates.original_columns
            + [g.name for g in candidates.generated_columns]
            if c in data.columns and c != target
        ]

        if method == "importance":
            rankings = self._importance_ranking(
                data, feature_cols, target, generated_names
            )
        elif method == "correlation":
            rankings = self._correlation_ranking(
                data, feature_cols, target, generated_names
            )
        elif method == "mutual_info":
            rankings = self._mutual_info_ranking(
                data, feature_cols, target, generated_names
            )
        else:
            raise ValueError(f"Unknown selection method: {method}")

        selected = [r.column_name for r in rankings[:top_k]]
        dropped = [r.column_name for r in rankings[top_k:]]

        return SelectedFeatures(
            selected_columns=selected,
            rankings=rankings,
            dropped_columns=dropped,
            method=method,
            n_original=len(candidates.original_columns),
            n_generated=len(candidates.generated_columns),
            n_selected=len(selected),
        )

    def _importance_ranking(
        self,
        data: pl.DataFrame,
        feature_cols: list[str],
        target: str,
        generated_names: set[str],
    ) -> list[FeatureRank]:
        """Rank features by tree-based importance (sklearn RandomForest)."""
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

        from kailash_ml.interop import to_sklearn_input

        # Filter to numeric columns only for sklearn
        numeric_feature_cols = [
            c for c in feature_cols if data[c].dtype in _NUMERIC_DTYPES
        ]
        if not numeric_feature_cols:
            return []

        X, y, _ = to_sklearn_input(
            data.select(numeric_feature_cols + [target]),
            feature_columns=numeric_feature_cols,
            target_column=target,
        )
        if y is None:
            return []

        # Detect task type from target
        n_unique = len(np.unique(y[~np.isnan(y)]))
        if n_unique <= 20:
            model = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=1)
        else:
            model = RandomForestRegressor(n_estimators=50, random_state=42, n_jobs=1)

        model.fit(X, y)
        importances = model.feature_importances_

        rankings = []
        for i, col in enumerate(numeric_feature_cols):
            rankings.append(
                FeatureRank(
                    column_name=col,
                    score=float(importances[i]),
                    rank=0,
                    source="generated" if col in generated_names else "original",
                )
            )
        rankings.sort(key=lambda r: r.score, reverse=True)
        for i, r in enumerate(rankings):
            r.rank = i + 1

        return rankings

    def _correlation_ranking(
        self,
        data: pl.DataFrame,
        feature_cols: list[str],
        target: str,
        generated_names: set[str],
    ) -> list[FeatureRank]:
        """Rank features by absolute Pearson correlation with target."""
        numeric_cols = [c for c in feature_cols if data[c].dtype in _NUMERIC_DTYPES]
        if not numeric_cols or target not in data.columns:
            return []

        rankings = []
        target_series = data[target].fill_null(0.0).cast(pl.Float64)
        for col in numeric_cols:
            try:
                corr = (
                    data[col]
                    .fill_null(0.0)
                    .cast(pl.Float64)
                    .pearson_corr(target_series)
                )
                score = abs(float(corr)) if corr is not None else 0.0
            except Exception:
                score = 0.0
            rankings.append(
                FeatureRank(
                    column_name=col,
                    score=score,
                    rank=0,
                    source="generated" if col in generated_names else "original",
                )
            )
        rankings.sort(key=lambda r: r.score, reverse=True)
        for i, r in enumerate(rankings):
            r.rank = i + 1
        return rankings

    def _mutual_info_ranking(
        self,
        data: pl.DataFrame,
        feature_cols: list[str],
        target: str,
        generated_names: set[str],
    ) -> list[FeatureRank]:
        """Rank features by mutual information with target."""
        from sklearn.feature_selection import (
            mutual_info_classif,
            mutual_info_regression,
        )

        from kailash_ml.interop import to_sklearn_input

        numeric_cols = [c for c in feature_cols if data[c].dtype in _NUMERIC_DTYPES]
        if not numeric_cols:
            return []

        X, y, _ = to_sklearn_input(
            data.select(numeric_cols + [target]),
            feature_columns=numeric_cols,
            target_column=target,
        )
        if y is None:
            return []

        n_unique = len(np.unique(y[~np.isnan(y)]))
        if n_unique <= 20:
            mi = mutual_info_classif(X, y, random_state=42)
        else:
            mi = mutual_info_regression(X, y, random_state=42)

        rankings = []
        for i, col in enumerate(numeric_cols):
            rankings.append(
                FeatureRank(
                    column_name=col,
                    score=float(mi[i]),
                    rank=0,
                    source="generated" if col in generated_names else "original",
                )
            )
        rankings.sort(key=lambda r: r.score, reverse=True)
        for i, r in enumerate(rankings):
            r.rank = i + 1
        return rankings
