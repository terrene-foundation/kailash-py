# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""DriftMonitor engine -- PSI, KS-test, performance degradation detection.

Detects distribution shifts using PSI (Population Stability Index) and
KS-test (Kolmogorov-Smirnov). Stores reference distributions and drift
reports in the database via ConnectionManager. Alerts when thresholds
are breached.

API cleanup (issue #351):
- ``set_reference_data()`` stores per-feature reference distributions.
- ``DriftCallback`` type alias for the ``on_drift_detected`` handler.
- Internal helpers use ``_store_performance_baseline`` / ``_load_performance_baseline``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import polars as pl
from kailash_ml.types import AgentInfusionProtocol
from scipy.stats import ks_2samp

from kailash.db.connection import ConnectionManager

logger = logging.getLogger(__name__)

__all__ = [
    "DriftCallback",
    "DriftMonitor",
    "DriftReport",
    "DriftSpec",
    "FeatureDriftResult",
    "PerformanceDegradationReport",
]

# ---------------------------------------------------------------------------
# Severity ordering
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {"none": 0, "moderate": 1, "severe": 2}

# ---------------------------------------------------------------------------
# Callback type
# ---------------------------------------------------------------------------

DriftCallback = Callable[["DriftReport"], Awaitable[None]]
"""Async callback invoked when drift is detected.

Signature: ``async def handler(report: DriftReport) -> None``.
"""


# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------


@dataclass
class FeatureDriftResult:
    """Drift result for a single feature."""

    feature_name: str
    psi: float
    ks_statistic: float
    ks_pvalue: float
    drift_detected: bool
    drift_type: str  # "none", "moderate", "severe"

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_name": self.feature_name,
            "psi": self.psi,
            "ks_statistic": self.ks_statistic,
            "ks_pvalue": self.ks_pvalue,
            "drift_detected": self.drift_detected,
            "drift_type": self.drift_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeatureDriftResult:
        return cls(
            feature_name=data["feature_name"],
            psi=data["psi"],
            ks_statistic=data["ks_statistic"],
            ks_pvalue=data["ks_pvalue"],
            drift_detected=data["drift_detected"],
            drift_type=data["drift_type"],
        )


@dataclass
class DriftReport:
    """Complete drift report for a model."""

    model_name: str
    feature_results: list[FeatureDriftResult]
    overall_drift_detected: bool
    overall_severity: str  # "none", "moderate", "severe"
    checked_at: datetime
    reference_set_at: datetime
    sample_size_reference: int
    sample_size_current: int

    @property
    def drifted_features(self) -> list[str]:
        return [f.feature_name for f in self.feature_results if f.drift_detected]

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "feature_results": [f.to_dict() for f in self.feature_results],
            "overall_drift_detected": self.overall_drift_detected,
            "overall_severity": self.overall_severity,
            "checked_at": self.checked_at.isoformat(),
            "reference_set_at": self.reference_set_at.isoformat(),
            "sample_size_reference": self.sample_size_reference,
            "sample_size_current": self.sample_size_current,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DriftReport:
        return cls(
            model_name=data["model_name"],
            feature_results=[
                FeatureDriftResult.from_dict(f) for f in data["feature_results"]
            ],
            overall_drift_detected=data["overall_drift_detected"],
            overall_severity=data["overall_severity"],
            checked_at=datetime.fromisoformat(data["checked_at"]),
            reference_set_at=datetime.fromisoformat(data["reference_set_at"]),
            sample_size_reference=data["sample_size_reference"],
            sample_size_current=data["sample_size_current"],
        )


@dataclass
class PerformanceDegradationReport:
    """Performance comparison: current vs baseline."""

    model_name: str
    baseline_metrics: dict[str, float]
    current_metrics: dict[str, float]
    degradation: dict[str, float]  # metric_name -> absolute change
    degraded: bool  # True if any metric degraded beyond threshold
    checked_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "baseline_metrics": dict(self.baseline_metrics),
            "current_metrics": dict(self.current_metrics),
            "degradation": dict(self.degradation),
            "degraded": self.degraded,
            "checked_at": self.checked_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PerformanceDegradationReport:
        return cls(
            model_name=data["model_name"],
            baseline_metrics=data["baseline_metrics"],
            current_metrics=data["current_metrics"],
            degradation=data["degradation"],
            degraded=data["degraded"],
            checked_at=datetime.fromisoformat(data["checked_at"]),
        )


@dataclass
class DriftSpec:
    """Specification for scheduled drift monitoring.

    Parameters
    ----------
    feature_columns:
        Feature columns to monitor. If None, uses those from the stored reference.
    psi_threshold:
        Override PSI threshold for this schedule. If None, uses monitor default.
    ks_threshold:
        Override KS threshold for this schedule. If None, uses monitor default.
    on_drift_detected:
        Optional async callback invoked when drift is detected.
        Signature: ``async def handler(report: DriftReport) -> None``.
    """

    feature_columns: list[str] | None = None
    psi_threshold: float | None = None
    ks_threshold: float | None = None
    on_drift_detected: DriftCallback | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_columns": self.feature_columns,
            "psi_threshold": self.psi_threshold,
            "ks_threshold": self.ks_threshold,
            "on_drift_detected": None,  # callable is not serializable
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DriftSpec:
        return cls(
            feature_columns=data.get("feature_columns"),
            psi_threshold=data.get("psi_threshold"),
            ks_threshold=data.get("ks_threshold"),
            # on_drift_detected is not restored from serialized form
        )


# ---------------------------------------------------------------------------
# Reference data storage
# ---------------------------------------------------------------------------


@dataclass
class _StoredReference:
    """In-memory representation of stored reference data."""

    model_name: str
    feature_columns: list[str]
    data: dict[str, pl.Series]  # feature_name -> series
    statistics: dict[str, Any]  # per-feature stats
    sample_size: int
    set_at: datetime


# ---------------------------------------------------------------------------
# PSI calculation
# ---------------------------------------------------------------------------


def _compute_psi(
    reference: pl.Series,
    current: pl.Series,
    n_bins: int = 10,
) -> float:
    """Population Stability Index.

    PSI < 0.1: no significant shift
    PSI 0.1-0.2: moderate shift
    PSI > 0.2: significant shift
    """
    if reference.dtype in (pl.Categorical, pl.Utf8, pl.String):
        return _compute_psi_categorical(reference, current)

    ref_arr = reference.drop_nulls().to_numpy().astype(np.float64)
    cur_arr = current.drop_nulls().to_numpy().astype(np.float64)

    if len(ref_arr) == 0 or len(cur_arr) == 0:
        return 0.0

    # Equal-width bins from reference distribution
    ref_min, ref_max = float(ref_arr.min()), float(ref_arr.max())
    if ref_min == ref_max:
        return 0.0

    edges = np.linspace(ref_min, ref_max, n_bins + 1)
    # Extend edges slightly to capture all values
    edges[0] = min(edges[0], float(cur_arr.min())) - 1e-10
    edges[-1] = max(edges[-1], float(cur_arr.max())) + 1e-10

    ref_counts = np.histogram(ref_arr, bins=edges)[0]
    cur_counts = np.histogram(cur_arr, bins=edges)[0]

    # Normalize to proportions, clip to avoid log(0)
    ref_pct = np.clip(ref_counts / ref_counts.sum(), 1e-6, None)
    cur_pct = np.clip(cur_counts / cur_counts.sum(), 1e-6, None)

    psi = float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))
    return psi


def _compute_psi_categorical(
    reference: pl.Series,
    current: pl.Series,
) -> float:
    """PSI for categorical features."""
    # Get unique categories from both
    ref_cast = reference.cast(pl.Utf8)
    cur_cast = current.cast(pl.Utf8)

    ref_counts = ref_cast.value_counts()
    cur_counts = cur_cast.value_counts()

    # Build frequency dicts
    ref_dict: dict[str, int] = {}
    for row in ref_counts.iter_rows():
        ref_dict[str(row[0])] = row[1]

    cur_dict: dict[str, int] = {}
    for row in cur_counts.iter_rows():
        cur_dict[str(row[0])] = row[1]

    all_cats = set(ref_dict.keys()) | set(cur_dict.keys())
    ref_total = sum(ref_dict.values())
    cur_total = sum(cur_dict.values())

    if ref_total == 0 or cur_total == 0:
        return 0.0

    psi = 0.0
    for cat in all_cats:
        ref_pct = max(ref_dict.get(cat, 0) / ref_total, 1e-6)
        cur_pct = max(cur_dict.get(cat, 0) / cur_total, 1e-6)
        psi += (cur_pct - ref_pct) * np.log(cur_pct / ref_pct)

    return float(psi)


# ---------------------------------------------------------------------------
# KS test
# ---------------------------------------------------------------------------


def _compute_ks(reference: pl.Series, current: pl.Series) -> tuple[float, float]:
    """Two-sample Kolmogorov-Smirnov test.

    Returns (ks_statistic, p_value).
    p_value < 0.05 indicates significant distribution difference.
    """
    ref_arr = reference.drop_nulls().to_numpy().astype(np.float64)
    cur_arr = current.drop_nulls().to_numpy().astype(np.float64)

    if len(ref_arr) < 2 or len(cur_arr) < 2:
        return (0.0, 1.0)

    stat, pvalue = ks_2samp(ref_arr, cur_arr)
    return (float(stat), float(pvalue))


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------


async def _create_drift_tables(conn: ConnectionManager) -> None:
    """Create drift monitor tables if they do not exist."""
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS _kml_drift_references ("
        "  model_name TEXT PRIMARY KEY,"
        "  feature_columns TEXT NOT NULL,"
        "  statistics TEXT NOT NULL,"
        "  sample_size INTEGER NOT NULL,"
        "  set_at TEXT NOT NULL"
        ")"
    )
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS _kml_drift_reports ("
        "  id TEXT PRIMARY KEY,"
        "  model_name TEXT NOT NULL,"
        "  feature_results TEXT NOT NULL,"
        "  overall_drift INTEGER NOT NULL,"
        "  overall_severity TEXT NOT NULL,"
        "  checked_at TEXT NOT NULL"
        ")"
    )
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS _kml_performance_baselines ("
        "  model_name TEXT PRIMARY KEY,"
        "  metrics TEXT NOT NULL,"
        "  set_at TEXT NOT NULL"
        ")"
    )


# ---------------------------------------------------------------------------
# DriftMonitor
# ---------------------------------------------------------------------------


class DriftMonitor:
    """[P0: Production] Drift monitor for model performance monitoring.

    Parameters
    ----------
    conn:
        An initialized ConnectionManager.
    psi_threshold:
        PSI above this triggers drift alert (default 0.2).
    ks_threshold:
        KS p-value below this triggers drift alert (default 0.05).
    performance_threshold:
        Absolute metric degradation threshold (default 0.1).
    """

    def __init__(
        self,
        conn: ConnectionManager,
        *,
        psi_threshold: float = 0.2,
        ks_threshold: float = 0.05,
        performance_threshold: float = 0.1,
    ) -> None:
        import math

        for name, val in [
            ("psi_threshold", psi_threshold),
            ("ks_threshold", ks_threshold),
            ("performance_threshold", performance_threshold),
        ]:
            if not math.isfinite(val):
                raise ValueError(f"{name} must be finite, got {val}")

        self._conn = conn
        self._psi_threshold = psi_threshold
        self._ks_threshold = ks_threshold
        self._performance_threshold = performance_threshold
        self._initialized = False
        # In-memory reference cache (bounded to prevent OOM with many models)
        self._references: dict[str, _StoredReference] = {}
        self._max_references = 100
        # Scheduled monitoring tasks
        self._scheduled_tasks: dict[str, asyncio.Task[None]] = {}

    async def _ensure_tables(self) -> None:
        if not self._initialized:
            await _create_drift_tables(self._conn)
            self._initialized = True

    # ------------------------------------------------------------------
    # set_reference_data
    # ------------------------------------------------------------------

    async def set_reference_data(
        self,
        model_name: str,
        reference_data: pl.DataFrame,
        feature_columns: list[str],
    ) -> None:
        """Store per-feature reference distribution.

        Parameters
        ----------
        model_name:
            Model identifier.
        reference_data:
            Reference dataset.
        feature_columns:
            Columns to monitor for drift.
        """
        await self._ensure_tables()

        now = datetime.now(timezone.utc)

        # Compute per-feature statistics
        statistics: dict[str, Any] = {}
        data_series: dict[str, pl.Series] = {}
        for col in feature_columns:
            series = reference_data[col]
            data_series[col] = series

            if series.dtype in (pl.Categorical, pl.Utf8, pl.String):
                cast_series = series.cast(pl.Utf8)
                vc = cast_series.value_counts()
                stats = {
                    "type": "categorical",
                    "categories": vc.to_dicts(),
                    "n": len(series),
                }
            else:
                num = series.drop_nulls().to_numpy().astype(np.float64)
                stats = {
                    "type": "numeric",
                    "mean": float(np.mean(num)) if len(num) > 0 else 0.0,
                    "std": float(np.std(num)) if len(num) > 0 else 0.0,
                    "min": float(np.min(num)) if len(num) > 0 else 0.0,
                    "max": float(np.max(num)) if len(num) > 0 else 0.0,
                    "n": len(num),
                }
            statistics[col] = stats

        ref = _StoredReference(
            model_name=model_name,
            feature_columns=feature_columns,
            data=data_series,
            statistics=statistics,
            sample_size=reference_data.height,
            set_at=now,
        )
        self._references[model_name] = ref
        # Evict oldest references if over limit
        while len(self._references) > self._max_references:
            oldest_key = next(iter(self._references))
            if oldest_key != model_name:
                del self._references[oldest_key]
            else:
                break

        # Persist to database (transaction eliminates TOCTOU race)
        async with self._conn.transaction() as tx:
            existing = await tx.fetchone(
                "SELECT model_name FROM _kml_drift_references WHERE model_name = ?",
                model_name,
            )
            if existing:
                await tx.execute(
                    "UPDATE _kml_drift_references "
                    "SET feature_columns = ?, statistics = ?, sample_size = ?, set_at = ? "
                    "WHERE model_name = ?",
                    json.dumps(feature_columns),
                    json.dumps(statistics, default=str),
                    reference_data.height,
                    now.isoformat(),
                    model_name,
                )
            else:
                await tx.execute(
                    "INSERT INTO _kml_drift_references "
                    "(model_name, feature_columns, statistics, sample_size, set_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    model_name,
                    json.dumps(feature_columns),
                    json.dumps(statistics, default=str),
                    reference_data.height,
                    now.isoformat(),
                )

        logger.info(
            "Set reference for '%s' (%d samples, %d features).",
            model_name,
            reference_data.height,
            len(feature_columns),
        )

    # ------------------------------------------------------------------
    # check_drift
    # ------------------------------------------------------------------

    async def check_drift(
        self,
        model_name: str,
        current_data: pl.DataFrame,
        *,
        agent: AgentInfusionProtocol | None = None,
    ) -> DriftReport:
        """Check feature drift against stored reference.

        Parameters
        ----------
        model_name:
            Model identifier (must have a reference set).
        current_data:
            Current dataset to compare.
        agent:
            Optional agent for drift interpretation.

        Returns
        -------
        DriftReport

        Raises
        ------
        ValueError
            If no reference is set for the model.
        """
        await self._ensure_tables()

        reference = self._references.get(model_name)
        if reference is None:
            raise ValueError(
                f"No reference set for model '{model_name}'. Call set_reference_data() first."
            )

        feature_results: list[FeatureDriftResult] = []

        for feature_name in reference.feature_columns:
            ref_series = reference.data[feature_name]
            if feature_name not in current_data.columns:
                logger.warning(
                    "Feature '%s' not in current data, skipping.", feature_name
                )
                continue
            cur_series = current_data[feature_name]

            psi = _compute_psi(ref_series, cur_series)

            # KS test only for numeric features
            is_numeric = ref_series.dtype not in (pl.Categorical, pl.Utf8, pl.String)
            if is_numeric:
                ks_stat, ks_pval = _compute_ks(ref_series, cur_series)
            else:
                ks_stat, ks_pval = 0.0, 1.0

            drift_detected = psi > self._psi_threshold or (
                is_numeric and ks_pval < self._ks_threshold
            )
            drift_type = "severe" if psi > 0.25 else "moderate" if psi > 0.1 else "none"

            feature_results.append(
                FeatureDriftResult(
                    feature_name=feature_name,
                    psi=psi,
                    ks_statistic=ks_stat,
                    ks_pvalue=ks_pval,
                    drift_detected=drift_detected,
                    drift_type=drift_type,
                )
            )

        overall_drift = any(f.drift_detected for f in feature_results)
        overall_severity = "none"
        if feature_results:
            overall_severity = max(
                (f.drift_type for f in feature_results),
                key=lambda s: _SEVERITY_ORDER.get(s, 0),
            )

        report = DriftReport(
            model_name=model_name,
            feature_results=feature_results,
            overall_drift_detected=overall_drift,
            overall_severity=overall_severity,
            checked_at=datetime.now(timezone.utc),
            reference_set_at=reference.set_at,
            sample_size_reference=reference.sample_size,
            sample_size_current=current_data.height,
        )

        # Store report
        await self._store_report(report)

        # Optional agent interpretation
        if agent is not None and report.overall_drift_detected:
            try:
                await agent.interpret_drift(
                    {
                        "model_name": report.model_name,
                        "drifted_features": report.drifted_features,
                        "severity": report.overall_severity,
                        "feature_results": [
                            f.to_dict() for f in report.feature_results
                        ],
                    }
                )
            except Exception:
                logger.debug("Agent drift interpretation failed.")

        return report

    # ------------------------------------------------------------------
    # check_performance
    # ------------------------------------------------------------------

    async def check_performance(
        self,
        model_name: str,
        predictions: pl.DataFrame,
        actuals: pl.DataFrame,
        *,
        baseline_metrics: dict[str, float] | None = None,
    ) -> PerformanceDegradationReport:
        """Check model performance degradation.

        Parameters
        ----------
        model_name:
            Model identifier.
        predictions:
            DataFrame with prediction column(s).
        actuals:
            DataFrame with actual/label column(s).
        baseline_metrics:
            Baseline metrics to compare against. If None, loads stored baseline.

        Returns
        -------
        PerformanceDegradationReport
        """
        await self._ensure_tables()

        # Compute current metrics
        pred_col = predictions.columns[0]
        actual_col = actuals.columns[0]

        y_pred = predictions[pred_col].to_numpy()
        y_true = actuals[actual_col].to_numpy()

        from sklearn import metrics as skmetrics

        current_metrics: dict[str, float] = {}
        # Try classification metrics
        try:
            current_metrics["accuracy"] = float(
                skmetrics.accuracy_score(y_true, y_pred)
            )
        except Exception:
            logger.debug("Could not compute accuracy metric.", exc_info=True)
        try:
            current_metrics["f1"] = float(
                skmetrics.f1_score(y_true, y_pred, average="weighted", zero_division=0)
            )
        except Exception:
            logger.debug("Could not compute f1 metric.", exc_info=True)

        # Load or use provided baseline
        if baseline_metrics is None:
            baseline_metrics = await self._load_performance_baseline(model_name)
            if baseline_metrics is None:
                # No baseline -- store current as baseline
                await self._store_performance_baseline(model_name, current_metrics)
                baseline_metrics = current_metrics

        # Compute degradation
        degradation: dict[str, float] = {}
        degraded = False
        for metric_name, current_value in current_metrics.items():
            if metric_name in baseline_metrics:
                delta = baseline_metrics[metric_name] - current_value
                degradation[metric_name] = delta
                if delta > self._performance_threshold:
                    degraded = True

        return PerformanceDegradationReport(
            model_name=model_name,
            baseline_metrics=baseline_metrics,
            current_metrics=current_metrics,
            degradation=degradation,
            degraded=degraded,
            checked_at=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # get_drift_history
    # ------------------------------------------------------------------

    async def get_drift_history(
        self,
        model_name: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Retrieve stored drift reports for a model."""
        await self._ensure_tables()
        return await self._conn.fetch(
            "SELECT * FROM _kml_drift_reports WHERE model_name = ? "
            "ORDER BY checked_at DESC LIMIT ?",
            model_name,
            limit,
        )

    # ------------------------------------------------------------------
    # Scheduled monitoring
    # ------------------------------------------------------------------

    async def schedule_monitoring(
        self,
        model_name: str,
        interval: timedelta,
        data_fn: Any,  # async callable returning pl.DataFrame
        spec: DriftSpec | None = None,
    ) -> None:
        """Schedule periodic drift monitoring as an asyncio background task.

        Parameters
        ----------
        model_name:
            Model identifier (must have a reference set).
        interval:
            How often to run drift checks.
        data_fn:
            Async callable that returns the current data as ``pl.DataFrame``.
            Signature: ``async def get_data() -> pl.DataFrame``.
        spec:
            Optional drift check specification overrides.
        """
        if model_name not in self._references:
            raise ValueError(
                f"No reference set for model '{model_name}'. Call set_reference_data() first."
            )
        if interval.total_seconds() < 1:
            raise ValueError("Monitoring interval must be at least 1 second.")

        # Cancel existing schedule for this model
        await self.cancel_monitoring(model_name)

        spec = spec or DriftSpec()

        async def _monitoring_loop() -> None:
            while True:
                await asyncio.sleep(interval.total_seconds())
                try:
                    current_data = await data_fn()
                    report = await self.check_drift(model_name, current_data)
                    if (
                        report.overall_drift_detected
                        and spec.on_drift_detected is not None
                    ):
                        await spec.on_drift_detected(report)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "Scheduled drift check failed for '%s'.", model_name
                    )

        task = asyncio.create_task(
            _monitoring_loop(), name=f"drift-monitor-{model_name}"
        )
        self._scheduled_tasks[model_name] = task
        logger.info(
            "Scheduled drift monitoring for '%s' every %s.",
            model_name,
            interval,
        )

    async def cancel_monitoring(self, model_name: str) -> bool:
        """Cancel scheduled monitoring for a model.

        Returns ``True`` if a task was cancelled, ``False`` if none was active.
        """
        task = self._scheduled_tasks.pop(model_name, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("Cancelled drift monitoring for '%s'.", model_name)
            return True
        return False

    async def shutdown(self) -> None:
        """Cancel all scheduled monitoring tasks."""
        for model_name in list(self._scheduled_tasks):
            await self.cancel_monitoring(model_name)

    @property
    def active_schedules(self) -> list[str]:
        """Return model names with active monitoring schedules."""
        return [name for name, task in self._scheduled_tasks.items() if not task.done()]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _store_report(self, report: DriftReport) -> None:
        """Persist a drift report to the database."""
        report_id = str(uuid.uuid4())
        await self._conn.execute(
            "INSERT INTO _kml_drift_reports "
            "(id, model_name, feature_results, overall_drift, overall_severity, checked_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            report_id,
            report.model_name,
            json.dumps([f.to_dict() for f in report.feature_results]),
            1 if report.overall_drift_detected else 0,
            report.overall_severity,
            report.checked_at.isoformat(),
        )

    async def _load_performance_baseline(
        self, model_name: str
    ) -> dict[str, float] | None:
        """Load stored performance baseline."""
        row = await self._conn.fetchone(
            "SELECT metrics FROM _kml_performance_baselines WHERE model_name = ?",
            model_name,
        )
        if row is None:
            return None
        return json.loads(row["metrics"])

    async def _store_performance_baseline(
        self, model_name: str, metrics: dict[str, float]
    ) -> None:
        """Store performance baseline (transaction eliminates TOCTOU race)."""
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._conn.transaction() as tx:
            existing = await tx.fetchone(
                "SELECT model_name FROM _kml_performance_baselines WHERE model_name = ?",
                model_name,
            )
            if existing:
                await tx.execute(
                    "UPDATE _kml_performance_baselines SET metrics = ?, set_at = ? "
                    "WHERE model_name = ?",
                    json.dumps(metrics),
                    now_iso,
                    model_name,
                )
            else:
                await tx.execute(
                    "INSERT INTO _kml_performance_baselines (model_name, metrics, set_at) "
                    "VALUES (?, ?, ?)",
                    model_name,
                    json.dumps(metrics),
                    now_iso,
                )
