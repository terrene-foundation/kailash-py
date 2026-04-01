# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""DataExplorer engine -- statistical profiling, plotly visualizations.

Computes summary statistics, distributions, correlations, and missing value
analysis using polars.  Generates interactive plotly visualizations.
Optionally augments with agent narrative (double opt-in).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import polars as pl

from kailash_ml._decorators import experimental

logger = logging.getLogger(__name__)

__all__ = [
    "DataExplorer",
    "ColumnProfile",
    "DataProfile",
    "VisualizationReport",
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
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ColumnProfile:
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
        )


@dataclass
class DataProfile:
    """Complete statistical profile of a dataset."""

    n_rows: int
    n_columns: int
    columns: list[ColumnProfile]
    correlation_matrix: dict[str, dict[str, float]] | None = None
    categorical_associations: dict[str, dict[str, float]] | None = None
    missing_patterns: list[dict[str, Any]] = field(default_factory=list)
    profiled_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_rows": self.n_rows,
            "n_columns": self.n_columns,
            "columns": [c.to_dict() for c in self.columns],
            "correlation_matrix": self.correlation_matrix,
            "categorical_associations": self.categorical_associations,
            "missing_patterns": list(self.missing_patterns),
            "profiled_at": self.profiled_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DataProfile:
        return cls(
            n_rows=data["n_rows"],
            n_columns=data["n_columns"],
            columns=[ColumnProfile.from_dict(c) for c in data["columns"]],
            correlation_matrix=data.get("correlation_matrix"),
            categorical_associations=data.get("categorical_associations"),
            missing_patterns=data.get("missing_patterns", []),
            profiled_at=data.get("profiled_at", ""),
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


# ---------------------------------------------------------------------------
# Numeric dtype helpers
# ---------------------------------------------------------------------------

from kailash_ml.engines._shared import NUMERIC_DTYPES as _NUMERIC_DTYPES

_STRING_DTYPES = (pl.Utf8, pl.String, pl.Categorical)


# ---------------------------------------------------------------------------
# DataExplorer
# ---------------------------------------------------------------------------


@experimental
class DataExplorer:
    """[P2: Experimental] Statistical profiling and visualization engine.

    Computes summary statistics, distributions, correlations, and missing
    value analysis using polars. Generates interactive plotly visualizations.
    API may change in future versions.

    Parameters
    ----------
    output_format:
        Default output format ("dict" or "dataframe").
    """

    def __init__(self, *, output_format: str = "dict") -> None:
        self._output_format = output_format

    def profile(
        self,
        data: pl.DataFrame,
        *,
        columns: list[str] | None = None,
    ) -> DataProfile:
        """Compute statistical profile using polars.

        All computation is polars-native. No pandas conversion.
        """
        cols = columns or data.columns
        column_profiles: list[ColumnProfile] = []

        for col in cols:
            series = data[col]
            count = series.len()
            null_c = series.null_count()
            base = ColumnProfile(
                name=col,
                dtype=str(series.dtype),
                count=count,
                null_count=null_c,
                null_pct=null_c / count if count > 0 else 0.0,
                unique_count=series.n_unique(),
            )

            if series.dtype in _NUMERIC_DTYPES:
                non_null = series.drop_nulls()
                if len(non_null) > 0:
                    base.mean = float(non_null.mean())  # type: ignore[arg-type]
                    std_val = non_null.std()
                    base.std = float(std_val) if std_val is not None else 0.0
                    base.min_val = float(non_null.min())  # type: ignore[arg-type]
                    base.max_val = float(non_null.max())  # type: ignore[arg-type]
                    base.q25 = float(non_null.quantile(0.25))  # type: ignore[arg-type]
                    base.q50 = float(non_null.quantile(0.50))  # type: ignore[arg-type]
                    base.q75 = float(non_null.quantile(0.75))  # type: ignore[arg-type]
            elif series.dtype in _STRING_DTYPES:
                vc = series.value_counts().sort("count", descending=True).head(10)
                col_name = col
                try:
                    vals = vc[col_name].to_list()
                    counts = vc["count"].to_list()
                    base.top_values = [(str(v), int(c)) for v, c in zip(vals, counts)]
                except Exception:
                    base.top_values = []

            column_profiles.append(base)

        # Correlation matrix for numeric columns
        numeric_cols = [c for c in cols if data[c].dtype in _NUMERIC_DTYPES]
        corr_matrix: dict[str, dict[str, float]] | None = None
        if len(numeric_cols) >= 2:
            numeric_df = data.select(numeric_cols).fill_null(0.0)
            corr_df = (
                numeric_df.corr()
                if hasattr(numeric_df, "corr")
                else numeric_df.pearson_corr()
            )
            corr_matrix = {}
            for i, c in enumerate(numeric_cols):
                corr_matrix[c] = {}
                for j, c2 in enumerate(numeric_cols):
                    val = corr_df[i, j]
                    corr_matrix[c][c2] = float(val) if val is not None else 0.0

        return DataProfile(
            n_rows=data.height,
            n_columns=len(cols),
            columns=column_profiles,
            correlation_matrix=corr_matrix,
            categorical_associations=None,
            missing_patterns=self._find_missing_patterns(data, cols),
            profiled_at=datetime.now(timezone.utc).isoformat(),
        )

    def visualize(
        self,
        data: pl.DataFrame,
        *,
        columns: list[str] | None = None,
    ) -> VisualizationReport:
        """Generate plotly visualizations for each column."""
        import plotly.express as px
        import plotly.graph_objects as go

        cols = columns or data.columns
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
                    pass

        # Correlation heatmap
        profile = self.profile(data, columns=cols)
        if profile.correlation_matrix:
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

    def compare(
        self,
        data_a: pl.DataFrame,
        data_b: pl.DataFrame,
        *,
        columns: list[str] | None = None,
    ) -> dict[str, Any]:
        """Compare two datasets statistically.

        Profiles both datasets and computes per-column deltas for
        numeric statistics (mean, std, null_pct).

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

        profile_a = self.profile(data_a, columns=cols)
        profile_b = self.profile(data_b, columns=cols)

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

    def _find_missing_patterns(
        self, data: pl.DataFrame, cols: list[str]
    ) -> list[dict[str, Any]]:
        """Find co-occurring null patterns."""
        null_cols = [c for c in cols if data[c].null_count() > 0]
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
