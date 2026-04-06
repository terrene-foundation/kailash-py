# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""DataExplorer engine -- async statistical profiling, plotly visualizations.

Computes summary statistics, distributions, correlations, and missing value
analysis using polars.  Generates interactive plotly visualizations.
Async-first with parallel matrix computations via asyncio.gather().
Polars' internal Rayon engine provides multicore within each operation.
"""
from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
import polars as pl

logger = logging.getLogger(__name__)

__all__ = [
    "DataExplorer",
    "ColumnProfile",
    "DataProfile",
    "VisualizationReport",
    "AlertConfig",
]


# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------


@dataclass
class ColumnProfile:
    """Statistical profile for a single column."""

    name: str
    dtype: str
    count: int
    null_count: int
    null_pct: float
    unique_count: int
    # Numeric only
    mean: float | None = None
    std: float | None = None
    min_val: float | None = None
    max_val: float | None = None
    q25: float | None = None
    q50: float | None = None
    q75: float | None = None
    # Categorical only
    top_values: list[tuple[str, int]] | None = None
    # Extended numeric
    skewness: float | None = None
    kurtosis: float | None = None
    zero_count: int | None = None
    zero_pct: float | None = None
    iqr: float | None = None
    outlier_count: int | None = None
    outlier_pct: float | None = None
    # Universal
    cardinality_ratio: float | None = None
    inferred_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "count": self.count,
            "null_count": self.null_count,
            "null_pct": self.null_pct,
            "unique_count": self.unique_count,
            "mean": self.mean,
            "std": self.std,
            "min_val": self.min_val,
            "max_val": self.max_val,
            "q25": self.q25,
            "q50": self.q50,
            "q75": self.q75,
            "top_values": self.top_values,
            "skewness": self.skewness,
            "kurtosis": self.kurtosis,
            "zero_count": self.zero_count,
            "zero_pct": self.zero_pct,
            "iqr": self.iqr,
            "outlier_count": self.outlier_count,
            "outlier_pct": self.outlier_pct,
            "cardinality_ratio": self.cardinality_ratio,
            "inferred_type": self.inferred_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ColumnProfile:
        # Validate required fields
        for key in ("name", "dtype", "count", "null_count", "null_pct", "unique_count"):
            if key not in data:
                raise ValueError(
                    f"ColumnProfile.from_dict: missing required field '{key}'"
                )
        if not isinstance(data["count"], int) or data["count"] < 0:
            raise ValueError(
                f"ColumnProfile.from_dict: count must be non-negative int, got {data['count']!r}"
            )
        if not isinstance(data["null_count"], int) or data["null_count"] < 0:
            raise ValueError(
                f"ColumnProfile.from_dict: null_count must be non-negative int, got {data['null_count']!r}"
            )
        return cls(
            name=data["name"],
            dtype=data["dtype"],
            count=data["count"],
            null_count=data["null_count"],
            null_pct=data["null_pct"],
            unique_count=data["unique_count"],
            mean=data.get("mean"),
            std=data.get("std"),
            min_val=data.get("min_val"),
            max_val=data.get("max_val"),
            q25=data.get("q25"),
            q50=data.get("q50"),
            q75=data.get("q75"),
            top_values=data.get("top_values"),
            skewness=data.get("skewness"),
            kurtosis=data.get("kurtosis"),
            zero_count=data.get("zero_count"),
            zero_pct=data.get("zero_pct"),
            iqr=data.get("iqr"),
            outlier_count=data.get("outlier_count"),
            outlier_pct=data.get("outlier_pct"),
            cardinality_ratio=data.get("cardinality_ratio"),
            inferred_type=data.get("inferred_type"),
        )


@dataclass
class DataProfile:
    """Complete statistical profile of a dataset."""

    n_rows: int
    n_columns: int
    columns: list[ColumnProfile]
    correlation_matrix: dict[str, dict[str, float | None]] | None = None
    categorical_associations: dict[str, dict[str, float | None]] | None = None
    missing_patterns: list[dict[str, Any]] = field(default_factory=list)
    profiled_at: str = ""
    # Extended fields
    spearman_matrix: dict[str, dict[str, float | None]] | None = None
    duplicate_count: int = 0
    duplicate_pct: float = 0.0
    memory_bytes: int = 0
    sample_head: list[dict[str, Any]] = field(default_factory=list)
    sample_tail: list[dict[str, Any]] = field(default_factory=list)
    type_summary: dict[str, int] = field(default_factory=dict)
    alerts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_rows": self.n_rows,
            "n_columns": self.n_columns,
            "columns": [c.to_dict() for c in self.columns],
            "correlation_matrix": self.correlation_matrix,
            "categorical_associations": self.categorical_associations,
            "missing_patterns": list(self.missing_patterns),
            "profiled_at": self.profiled_at,
            "spearman_matrix": self.spearman_matrix,
            "duplicate_count": self.duplicate_count,
            "duplicate_pct": self.duplicate_pct,
            "memory_bytes": self.memory_bytes,
            "sample_head": list(self.sample_head),
            "sample_tail": list(self.sample_tail),
            "type_summary": dict(self.type_summary),
            "alerts": list(self.alerts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DataProfile:
        for key in ("n_rows", "n_columns", "columns"):
            if key not in data:
                raise ValueError(
                    f"DataProfile.from_dict: missing required field '{key}'"
                )
        if not isinstance(data["n_rows"], int) or data["n_rows"] < 0:
            raise ValueError(
                f"DataProfile.from_dict: n_rows must be non-negative int, got {data['n_rows']!r}"
            )
        return cls(
            n_rows=data["n_rows"],
            n_columns=data["n_columns"],
            columns=[ColumnProfile.from_dict(c) for c in data["columns"]],
            correlation_matrix=data.get("correlation_matrix"),
            categorical_associations=data.get("categorical_associations"),
            missing_patterns=data.get("missing_patterns", []),
            profiled_at=data.get("profiled_at", ""),
            spearman_matrix=data.get("spearman_matrix"),
            duplicate_count=data.get("duplicate_count", 0),
            duplicate_pct=data.get("duplicate_pct", 0.0),
            memory_bytes=data.get("memory_bytes", 0),
            sample_head=data.get("sample_head", []),
            sample_tail=data.get("sample_tail", []),
            type_summary=data.get("type_summary", {}),
            alerts=data.get("alerts", []),
        )


@dataclass
class VisualizationReport:
    """Collection of plotly visualizations."""

    figures: dict[str, Any] = field(default_factory=dict)
    summary_html: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "figures": None,  # plotly figures are not JSON-serializable
            "summary_html": self.summary_html,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VisualizationReport:
        return cls(
            figures=data.get("figures") or {},
            summary_html=data.get("summary_html"),
        )


@dataclass
class AlertConfig:
    """Thresholds for automatic data quality alerts."""

    high_correlation_threshold: float = 0.9
    high_null_pct_threshold: float = 0.05
    constant_threshold: int = 1
    high_cardinality_ratio: float = 0.9
    skewness_threshold: float = 2.0
    zero_pct_threshold: float = 0.5
    imbalance_ratio_threshold: float = 0.1
    duplicate_pct_threshold: float = 0.0


# ---------------------------------------------------------------------------
# Numeric dtype helpers
# ---------------------------------------------------------------------------

from kailash_ml.engines._shared import NUMERIC_DTYPES as _NUMERIC_DTYPES  # noqa: E402

_STRING_DTYPES = (pl.Utf8, pl.String, pl.Categorical)


# ---------------------------------------------------------------------------
# DataExplorer
# ---------------------------------------------------------------------------


class DataExplorer:
    """[P1: Tested] Statistical profiling and visualization engine.

    Computes summary statistics, distributions, correlations, and missing
    value analysis using polars. Generates interactive plotly visualizations.

    Parameters
    ----------
    output_format:
        Default output format ("dict" or "dataframe").
    alert_config:
        Thresholds for automatic data quality alerts. If ``None``, uses
        default thresholds from :class:`AlertConfig`.
    """

    def __init__(
        self,
        *,
        output_format: str = "dict",
        alert_config: AlertConfig | None = None,
    ) -> None:
        self._output_format = output_format
        self._alert_config = alert_config or AlertConfig()

    # ------------------------------------------------------------------
    # Type inference
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_column_type(
        series: pl.Series,
        *,
        unique_count: int,
        count: int,
    ) -> str:
        """Infer a semantic type label for *series*."""
        if series.dtype in _NUMERIC_DTYPES:
            non_null = series.drop_nulls()
            if unique_count == 1:
                return "constant"
            if unique_count == 2:
                vals = set(non_null.to_list())
                if vals <= {0, 1} or vals <= {True, False} or vals <= {0.0, 1.0}:
                    return "boolean"
            if unique_count == count and count > 1:
                return "id"
            if unique_count <= 10:
                return "categorical"
            return "numeric"
        if series.dtype in _STRING_DTYPES:
            if unique_count == 1:
                return "constant"
            if unique_count <= 50:
                return "categorical"
            return "text"
        # Boolean dtype
        if series.dtype == pl.Boolean:
            return "boolean"
        return "text"

    # ------------------------------------------------------------------
    # Profiling
    # ------------------------------------------------------------------

    async def profile(
        self,
        data: pl.DataFrame,
        *,
        columns: list[str] | None = None,
    ) -> DataProfile:
        """Compute statistical profile using polars with parallel execution.

        CPU-bound column profiling runs in a thread pool. Five independent
        matrix computations (Pearson, Spearman, Cramer's V, missing patterns,
        duplicates) execute concurrently via ``asyncio.gather()``. Each
        operation internally uses polars' Rayon multicore engine.
        """
        cols = columns or data.columns

        # CPU-bound column profiling offloaded to thread pool
        column_profiles = await asyncio.to_thread(self._profile_columns, data, cols)

        # Identify column types for parallel matrix computations
        numeric_cols = [c for c in cols if data[c].dtype in _NUMERIC_DTYPES]
        cat_cols = [
            c
            for c in cols
            if data[c].dtype in _STRING_DTYPES or data[c].dtype == pl.Categorical
        ]

        # 5 independent computations in parallel — each uses polars multicore
        (
            corr_matrix,
            spearman_matrix,
            cat_assoc,
            missing_patterns,
            dup_count,
        ) = await asyncio.gather(
            asyncio.to_thread(self._compute_pearson, data, numeric_cols),
            asyncio.to_thread(self._compute_spearman, data, numeric_cols),
            asyncio.to_thread(self._compute_cramers_v, data, cat_cols),
            asyncio.to_thread(self._find_missing_patterns, data, cols),
            asyncio.to_thread(lambda: int(data.is_duplicated().sum())),
        )

        dup_pct = dup_count / data.height if data.height > 0 else 0.0

        # Lightweight metadata (no thread needed)
        memory_bytes = data.estimated_size()
        sample_head = data.head(5).to_dicts()
        sample_tail = data.tail(5).to_dicts()

        type_summary: dict[str, int] = {}
        for cp in column_profiles:
            t = cp.inferred_type or "unknown"
            type_summary[t] = type_summary.get(t, 0) + 1

        # Pre-compute alerts so DataProfile is fully immutable at construction
        _proto = DataProfile(
            n_rows=data.height,
            n_columns=len(cols),
            columns=column_profiles,
            correlation_matrix=corr_matrix,
            categorical_associations=cat_assoc,
            missing_patterns=missing_patterns,
            profiled_at=datetime.now(timezone.utc).isoformat(),
            spearman_matrix=spearman_matrix,
            duplicate_count=dup_count,
            duplicate_pct=dup_pct,
            memory_bytes=memory_bytes,
            sample_head=sample_head,
            sample_tail=sample_tail,
            type_summary=type_summary,
            alerts=self._generate_alerts(
                DataProfile(
                    n_rows=data.height,
                    n_columns=len(cols),
                    columns=column_profiles,
                    correlation_matrix=corr_matrix,
                    duplicate_count=dup_count,
                    duplicate_pct=dup_pct,
                ),
                self._alert_config,
            ),
        )

        return _proto

    # ------------------------------------------------------------------
    # Sync column profiling (runs in thread pool)
    # ------------------------------------------------------------------

    def _profile_columns(
        self,
        data: pl.DataFrame,
        cols: list[str],
    ) -> list[ColumnProfile]:
        """Profile each column synchronously. Called via to_thread()."""
        column_profiles: list[ColumnProfile] = []

        for col in cols:
            series = data[col]
            count = series.len()
            null_c = series.null_count()
            uniq = series.n_unique()
            base = ColumnProfile(
                name=col,
                dtype=str(series.dtype),
                count=count,
                null_count=null_c,
                null_pct=null_c / count if count > 0 else 0.0,
                unique_count=uniq,
            )

            # Cardinality ratio (all columns)
            base.cardinality_ratio = uniq / count if count > 0 else 0.0

            if series.dtype in _NUMERIC_DTYPES:
                non_null = series.drop_nulls()
                if len(non_null) > 0:
                    _sf = DataExplorer._sanitize_float
                    base.mean = _sf(non_null.mean(), default=0.0)
                    base.std = _sf(non_null.std(), default=0.0)
                    base.min_val = _sf(non_null.min(), default=0.0)
                    base.max_val = _sf(non_null.max(), default=0.0)
                    base.q25 = _sf(non_null.quantile(0.25), default=0.0)
                    base.q50 = _sf(non_null.quantile(0.50), default=0.0)
                    base.q75 = _sf(non_null.quantile(0.75), default=0.0)

                    # IQR + outlier detection
                    iqr_val = (base.q75 or 0.0) - (base.q25 or 0.0)
                    base.iqr = iqr_val
                    lower = (base.q25 or 0.0) - 1.5 * iqr_val
                    upper = (base.q75 or 0.0) + 1.5 * iqr_val
                    outliers = int(((non_null < lower) | (non_null > upper)).sum())
                    base.outlier_count = outliers
                    base.outlier_pct = outliers / count if count > 0 else 0.0

                    # Skewness + kurtosis (via numpy)
                    if len(non_null) > 2:
                        arr = non_null.to_numpy().astype(float)
                        std_np = float(arr.std())
                        if std_np > 0 and math.isfinite(std_np):
                            centered = (arr - arr.mean()) / std_np
                            skew_val = float(np.mean(centered**3))
                            kurt_val = float(np.mean(centered**4) - 3.0)
                            base.skewness = skew_val if math.isfinite(skew_val) else 0.0
                            base.kurtosis = kurt_val if math.isfinite(kurt_val) else 0.0
                        else:
                            base.skewness = 0.0
                            base.kurtosis = 0.0
                    else:
                        base.skewness = 0.0
                        base.kurtosis = 0.0

                # Zero count / pct
                zeros = int((series == 0).sum())
                base.zero_count = zeros
                base.zero_pct = zeros / count if count > 0 else 0.0

            elif series.dtype in _STRING_DTYPES:
                vc = series.value_counts().sort("count", descending=True).head(10)
                col_name = col
                try:
                    vals = vc[col_name].to_list()
                    counts = vc["count"].to_list()
                    base.top_values = [(str(v), int(c)) for v, c in zip(vals, counts)]
                except Exception:
                    logger.debug(
                        "Failed to extract value counts for column %s",
                        col,
                        exc_info=True,
                    )
                    base.top_values = []

            # Type inference
            base.inferred_type = self._infer_column_type(
                series,
                unique_count=uniq,
                count=count,
            )

            column_profiles.append(base)

        return column_profiles

    # ------------------------------------------------------------------
    # Visualization
    # ------------------------------------------------------------------

    async def visualize(
        self,
        data: pl.DataFrame,
        *,
        columns: list[str] | None = None,
    ) -> VisualizationReport:
        """Generate plotly visualizations with parallel figure creation."""
        cols = columns or data.columns

        # Build figures in thread pool (plotly is CPU-bound)
        figures = await asyncio.to_thread(self._build_figures, data, cols)

        # Correlation heatmap needs the profile
        profile = await self.profile(data, columns=cols)
        if profile.correlation_matrix:
            import plotly.graph_objects as go

            labels = list(profile.correlation_matrix.keys())
            values = [
                [profile.correlation_matrix[r][c] for c in labels] for r in labels
            ]
            fig = go.Figure(
                data=go.Heatmap(
                    z=values,
                    x=labels,
                    y=labels,
                    text=[[f"{v:.2f}" for v in row] for row in values],
                    texttemplate="%{text}",
                )
            )
            fig.update_layout(title="Correlation Matrix")
            figures["correlation"] = fig

        return VisualizationReport(figures=figures)

    @staticmethod
    def _build_figures(
        data: pl.DataFrame,
        cols: list[str],
    ) -> dict[str, Any]:
        """Build plotly figures synchronously. Called via to_thread()."""
        import plotly.express as px

        figures: dict[str, Any] = {}
        for col in cols:
            series = data[col]
            if series.dtype in _NUMERIC_DTYPES:
                fig = px.histogram(
                    x=series.drop_nulls().to_list(),
                    title=f"Distribution: {col}",
                    labels={"x": col},
                )
                figures[col] = fig
            elif series.dtype in _STRING_DTYPES:
                vc = series.value_counts().sort("count", descending=True).head(20)
                try:
                    fig = px.bar(
                        x=vc[col].to_list(),
                        y=vc["count"].to_list(),
                        title=f"Value Counts: {col}",
                        labels={"x": col, "y": "Count"},
                    )
                    figures[col] = fig
                except Exception:
                    logger.debug(
                        "Failed to build figure for column %s", col, exc_info=True
                    )
        return figures

    # ------------------------------------------------------------------
    # HTML report
    # ------------------------------------------------------------------

    async def to_html(
        self,
        data: pl.DataFrame,
        *,
        title: str = "Data Profile Report",
    ) -> str:
        """Generate a self-contained HTML profiling report.

        Profiles and visualizes concurrently, then renders HTML.

        Parameters
        ----------
        data:
            The polars DataFrame to profile.
        title:
            Title displayed at the top of the report. HTML-escaped internally.

        Returns
        -------
        str
            Complete HTML document as a string.
        """
        from kailash_ml.engines._data_explorer_report import generate_html_report

        profile, viz = await asyncio.gather(
            self.profile(data),
            self.visualize(data),
        )
        return generate_html_report(profile, viz, title=title)

    # ------------------------------------------------------------------
    # Dataset comparison
    # ------------------------------------------------------------------

    async def compare(
        self,
        data_a: pl.DataFrame,
        data_b: pl.DataFrame,
        *,
        columns: list[str] | None = None,
    ) -> dict[str, Any]:
        """Compare two datasets statistically.

        Profiles both datasets concurrently and computes per-column deltas.

        Parameters
        ----------
        data_a:
            First dataset (typically the reference/training set).
        data_b:
            Second dataset (typically the current/production set).
        columns:
            Columns to compare. If None, compares all shared columns.

        Returns
        -------
        dict
            Keys: ``profile_a``, ``profile_b``, ``column_deltas``,
            ``shape_comparison``, ``shared_columns``, ``missing_in_a``,
            ``missing_in_b``.
        """
        shared = sorted(set(data_a.columns) & set(data_b.columns))
        cols = columns or shared

        # Profile both datasets in parallel
        profile_a, profile_b = await asyncio.gather(
            self.profile(data_a, columns=cols),
            self.profile(data_b, columns=cols),
        )

        # Build lookup for quick access
        stats_a = {cp.name: cp for cp in profile_a.columns}
        stats_b = {cp.name: cp for cp in profile_b.columns}

        column_deltas: list[dict[str, Any]] = []
        for col in cols:
            a = stats_a.get(col)
            b = stats_b.get(col)
            if a is None or b is None:
                continue
            delta: dict[str, Any] = {"column": col, "dtype": a.dtype}
            if a.mean is not None and b.mean is not None:
                delta["mean_delta"] = b.mean - a.mean
            if a.std is not None and b.std is not None:
                delta["std_delta"] = b.std - a.std
            delta["null_pct_delta"] = b.null_pct - a.null_pct
            delta["unique_count_delta"] = b.unique_count - a.unique_count
            column_deltas.append(delta)

        return {
            "profile_a": profile_a,
            "profile_b": profile_b,
            "column_deltas": column_deltas,
            "shape_comparison": {
                "rows_a": data_a.height,
                "rows_b": data_b.height,
                "cols_a": data_a.width,
                "cols_b": data_b.width,
            },
            "shared_columns": shared,
            "missing_in_a": sorted(set(data_b.columns) - set(data_a.columns)),
            "missing_in_b": sorted(set(data_a.columns) - set(data_b.columns)),
        }

    # ------------------------------------------------------------------
    # Numeric sanitisation
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_float(val: Any, *, default: float | None = None) -> float | None:
        """Convert *val* to a finite Python float or return *default*.

        Centralises NaN/Inf handling for every numeric output so new
        statistics added in the future inherit the guard automatically.
        """
        if val is None:
            return default
        fval = float(val)
        if not math.isfinite(fval):
            return default
        return fval

    # ------------------------------------------------------------------
    # Correlation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_pearson(
        data: pl.DataFrame,
        numeric_cols: list[str],
    ) -> dict[str, dict[str, float | None]] | None:
        """Pearson correlation matrix using pairwise-complete observation.

        Instead of ``fill_null(0.0)`` (which biases correlations toward
        zero), we drop nulls per column pair so that only shared non-null
        rows contribute.  When the DataFrame has *no* nulls we fast-path
        to ``df.corr()`` for performance.
        """
        if len(numeric_cols) < 2 or data.height < 2:
            return None

        numeric_df = data.select(numeric_cols)
        has_nulls = numeric_df.null_count().row(0) != tuple(0 for _ in numeric_cols)

        if not has_nulls:
            # Fast-path: no nulls → single vectorised correlation.
            corr_df = (
                numeric_df.corr()
                if hasattr(numeric_df, "corr")
                else numeric_df.pearson_corr()
            )
            matrix: dict[str, dict[str, float | None]] = {}
            for i, c in enumerate(numeric_cols):
                matrix[c] = {}
                for j, c2 in enumerate(numeric_cols):
                    val = corr_df[i, j]
                    matrix[c][c2] = DataExplorer._sanitize_float(val)
            return matrix

        # Pairwise-complete: drop nulls per column pair.
        matrix = {}
        for c in numeric_cols:
            matrix[c] = {}
        for i, c1 in enumerate(numeric_cols):
            matrix[c1][c1] = 1.0
            for j in range(i + 1, len(numeric_cols)):
                c2 = numeric_cols[j]
                pair = numeric_df.select([c1, c2]).drop_nulls()
                if pair.height < 2:
                    matrix[c1][c2] = None
                    matrix[c2][c1] = None
                    continue
                pair_corr = (
                    pair.corr() if hasattr(pair, "corr") else pair.pearson_corr()
                )
                val = DataExplorer._sanitize_float(pair_corr[0, 1])
                matrix[c1][c2] = val
                matrix[c2][c1] = val
        return matrix

    @staticmethod
    def _compute_spearman(
        data: pl.DataFrame,
        numeric_cols: list[str],
    ) -> dict[str, dict[str, float | None]] | None:
        """Spearman rank correlation via pairwise-complete observation.

        Ranks are computed per column, then Pearson correlation is applied
        on the ranked values with pairwise null-dropping.
        """
        if len(numeric_cols) < 2 or data.height < 2:
            return None

        numeric_df = data.select(numeric_cols)
        has_nulls = numeric_df.null_count().row(0) != tuple(0 for _ in numeric_cols)

        ranked = data.select([pl.col(c).rank().alias(c) for c in numeric_cols])

        if not has_nulls:
            ranked_filled = ranked.fill_null(0.0)
            corr_df = (
                ranked_filled.corr()
                if hasattr(ranked_filled, "corr")
                else ranked_filled.pearson_corr()
            )
            matrix: dict[str, dict[str, float | None]] = {}
            for i, c in enumerate(numeric_cols):
                matrix[c] = {}
                for j, c2 in enumerate(numeric_cols):
                    val = corr_df[i, j]
                    matrix[c][c2] = DataExplorer._sanitize_float(val)
            return matrix

        # Pairwise-complete on ranks.
        matrix = {}
        for c in numeric_cols:
            matrix[c] = {}
        for i, c1 in enumerate(numeric_cols):
            matrix[c1][c1] = 1.0
            for j in range(i + 1, len(numeric_cols)):
                c2 = numeric_cols[j]
                pair = ranked.select([c1, c2]).drop_nulls()
                if pair.height < 2:
                    matrix[c1][c2] = None
                    matrix[c2][c1] = None
                    continue
                pair_corr = (
                    pair.corr() if hasattr(pair, "corr") else pair.pearson_corr()
                )
                val = DataExplorer._sanitize_float(pair_corr[0, 1])
                matrix[c1][c2] = val
                matrix[c2][c1] = val
        return matrix

    @staticmethod
    def _compute_cramers_v(
        data: pl.DataFrame,
        cat_cols: list[str],
        *,
        max_cols: int = 20,
        max_cardinality: int = 100,
    ) -> dict[str, dict[str, float | None]] | None:
        """Cramer's V association matrix -- pure polars + numpy, no scipy.

        Bounded: skips columns with >*max_cardinality* unique values and
        processes at most *max_cols* categorical columns to avoid O(n^2)
        explosion on high-cardinality data.
        """
        # Filter out high-cardinality columns and bound total
        safe_cols = [c for c in cat_cols if data[c].n_unique() <= max_cardinality][
            :max_cols
        ]
        if len(safe_cols) < 2:
            return None
        matrix: dict[str, dict[str, float]] = {}
        for col_a in safe_cols:
            matrix[col_a] = {}
            for col_b in safe_cols:
                if col_a == col_b:
                    matrix[col_a][col_b] = 1.0
                    continue
                # Build contingency table via group_by + pivot
                ct = data.select([col_a, col_b]).group_by([col_a, col_b]).len()
                try:
                    pivot = ct.pivot(
                        on=col_b,
                        index=col_a,
                        values="len",
                    ).fill_null(0)
                except Exception:
                    logger.debug(
                        "Failed to pivot contingency table for %s × %s",
                        col_a,
                        col_b,
                        exc_info=True,
                    )
                    matrix[col_a][col_b] = 0.0
                    continue
                # Extract observed frequencies (skip the index column)
                value_cols = [c for c in pivot.columns if c != col_a]
                if not value_cols:
                    matrix[col_a][col_b] = 0.0
                    continue
                observed = pivot.select(value_cols).to_numpy().astype(float)
                n = observed.sum()
                if n == 0:
                    matrix[col_a][col_b] = 0.0
                    continue
                row_sums = observed.sum(axis=1, keepdims=True)
                col_sums = observed.sum(axis=0, keepdims=True)
                expected = row_sums * col_sums / n
                mask = expected > 0
                chi2 = float(
                    np.sum((observed[mask] - expected[mask]) ** 2 / expected[mask])
                )
                k = min(observed.shape)
                if k <= 1:
                    matrix[col_a][col_b] = 0.0
                else:
                    raw = float(np.sqrt(chi2 / (n * (k - 1))))
                    matrix[col_a][col_b] = raw if math.isfinite(raw) else 0.0
        return matrix

    # ------------------------------------------------------------------
    # Missing patterns
    # ------------------------------------------------------------------

    @staticmethod
    def _find_missing_patterns(
        data: pl.DataFrame,
        cols: list[str],
        *,
        max_null_cols: int = 20,
    ) -> list[dict[str, Any]]:
        """Find co-occurring null patterns.

        Bounded: analyses at most *max_null_cols* columns to prevent
        exponential group-by cardinality (2^n worst case).
        """
        null_cols = [c for c in cols if data[c].null_count() > 0][:max_null_cols]
        if len(null_cols) < 2:
            return (
                [{"columns": null_cols, "count": data[null_cols[0]].null_count()}]
                if null_cols
                else []
            )

        # Find rows where multiple columns are null together
        patterns: list[dict[str, Any]] = []
        null_mask = data.select([pl.col(c).is_null().alias(c) for c in null_cols])

        # Group by null patterns
        pattern_counts = null_mask.group_by(null_cols).len()
        for row in pattern_counts.iter_rows(named=True):
            null_in_row = [c for c in null_cols if row[c]]
            if len(null_in_row) >= 2:
                patterns.append(
                    {
                        "columns": null_in_row,
                        "count": row["len"],
                    }
                )

        return patterns

    # ------------------------------------------------------------------
    # Alert generation
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_alerts(
        profile: DataProfile,
        config: AlertConfig,
    ) -> list[dict[str, Any]]:
        """Scan a profile and emit data quality alerts."""
        alerts: list[dict[str, Any]] = []

        for cp in profile.columns:
            # High nulls
            if cp.null_pct is not None and cp.null_pct > config.high_null_pct_threshold:
                alerts.append(
                    {
                        "type": "high_nulls",
                        "column": cp.name,
                        "value": cp.null_pct,
                        "severity": "warning",
                    }
                )
            # Constant column
            if (
                cp.unique_count is not None
                and cp.unique_count <= config.constant_threshold
            ):
                alerts.append(
                    {
                        "type": "constant",
                        "column": cp.name,
                        "severity": "warning",
                    }
                )
            # High skewness
            if cp.skewness is not None and abs(cp.skewness) > config.skewness_threshold:
                alerts.append(
                    {
                        "type": "high_skewness",
                        "column": cp.name,
                        "value": cp.skewness,
                        "severity": "info",
                    }
                )
            # High zeros
            if cp.zero_pct is not None and cp.zero_pct > config.zero_pct_threshold:
                alerts.append(
                    {
                        "type": "high_zeros",
                        "column": cp.name,
                        "value": cp.zero_pct,
                        "severity": "info",
                    }
                )
            # High cardinality
            if (
                cp.cardinality_ratio is not None
                and cp.cardinality_ratio > config.high_cardinality_ratio
            ):
                alerts.append(
                    {
                        "type": "high_cardinality",
                        "column": cp.name,
                        "value": cp.cardinality_ratio,
                        "severity": "info",
                    }
                )

        # Cross-column: high correlation
        if profile.correlation_matrix:
            for c1, row in profile.correlation_matrix.items():
                for c2, val in row.items():
                    if (
                        c1 < c2
                        and val is not None
                        and abs(val) > config.high_correlation_threshold
                    ):
                        alerts.append(
                            {
                                "type": "high_correlation",
                                "columns": [c1, c2],
                                "value": val,
                                "severity": "warning",
                            }
                        )

        # Duplicates
        if profile.duplicate_pct > config.duplicate_pct_threshold:
            alerts.append(
                {
                    "type": "duplicates",
                    "value": profile.duplicate_pct,
                    "count": profile.duplicate_count,
                    "severity": "warning",
                }
            )

        # Imbalance for categorical / boolean columns
        for cp in profile.columns:
            if cp.inferred_type in ("categorical", "boolean") and cp.top_values:
                total = sum(c for _, c in cp.top_values)
                if total > 0:
                    min_count = min(c for _, c in cp.top_values)
                    ratio = min_count / total
                    if ratio < config.imbalance_ratio_threshold:
                        alerts.append(
                            {
                                "type": "imbalanced",
                                "column": cp.name,
                                "value": ratio,
                                "severity": "info",
                            }
                        )

        return alerts
