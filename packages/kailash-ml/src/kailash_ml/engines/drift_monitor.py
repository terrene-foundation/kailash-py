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
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import polars as pl
from kailash_ml.drift.alerts import (
    AlertConfig,
    DriftAlertDispatcher,
)
from kailash_ml.drift.policy import DriftMonitorReferencePolicy
from kailash_ml.drift.stats import (
    DriftThresholds,
    chi2_test,
    jensen_shannon_continuous,
    jensen_shannon_discrete,
    new_category_fraction as _new_category_fraction,
    select_statistics,
)
from kailash_ml.errors import (
    DriftMonitorError,
    DriftThresholdError,
    InsufficientSamplesError,
    ReferenceNotFoundError,
    TenantRequiredError,
    ZeroVarianceReferenceError,
)
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
    """Drift result for a single feature.

    W26 (spec ``ml-drift.md §§3.1–3.3``): ``chi2_*``, ``jsd``,
    ``new_category_fraction``, ``statistics_used``, and
    ``stability_note`` are added with optional/None defaults so existing
    callers that only read PSI / KS continue to work unchanged.
    """

    feature_name: str
    psi: float
    ks_statistic: float
    ks_pvalue: float
    drift_detected: bool
    drift_type: str  # "none", "moderate", "severe"
    # W26 extended stats — optional so pre-W26 callers / persisted rows
    # still deserialize cleanly.
    chi2_statistic: float | None = None
    chi2_pvalue: float | None = None
    jsd: float | None = None
    new_category_fraction: float | None = None
    # Set of statistic tokens computed for this column (per
    # ``kailash_ml.drift.stats.select_statistics``).  Serialized as a
    # sorted list for JSON portability.
    statistics_used: list[str] | None = None
    # Per spec §3.6 MUST 5 — smoothing fired OR stats skipped due to
    # ``MIN_BIN_COUNT``.  ``None`` when nothing noteworthy happened.
    stability_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_name": self.feature_name,
            "psi": self.psi,
            "ks_statistic": self.ks_statistic,
            "ks_pvalue": self.ks_pvalue,
            "drift_detected": self.drift_detected,
            "drift_type": self.drift_type,
            "chi2_statistic": self.chi2_statistic,
            "chi2_pvalue": self.chi2_pvalue,
            "jsd": self.jsd,
            "new_category_fraction": self.new_category_fraction,
            "statistics_used": (
                list(self.statistics_used) if self.statistics_used is not None else None
            ),
            "stability_note": self.stability_note,
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
            chi2_statistic=data.get("chi2_statistic"),
            chi2_pvalue=data.get("chi2_pvalue"),
            jsd=data.get("jsd"),
            new_category_fraction=data.get("new_category_fraction"),
            statistics_used=data.get("statistics_used"),
            stability_note=data.get("stability_note"),
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
    """In-memory representation of stored reference data.

    W26.b: ``policy`` / ``timestamp_column`` / ``raw_data`` support
    non-static reference-refresh modes per ``specs/ml-drift.md §4.5``.
    ``data`` (per-feature Series) is retained for static-mode fast path
    so existing code paths are unaffected. ``raw_data`` holds the full
    reference DataFrame only when ``policy.mode != "static"`` — static
    monitors keep the lightweight per-feature Series form.
    """

    model_name: str
    feature_columns: list[str]
    data: dict[str, pl.Series]  # feature_name -> series
    statistics: dict[str, Any]  # per-feature stats
    sample_size: int
    set_at: datetime
    policy: DriftMonitorReferencePolicy = field(
        default_factory=DriftMonitorReferencePolicy
    )
    timestamp_column: str | None = None
    raw_data: pl.DataFrame | None = None
    # Sliding-mode refresh cadence memoisation: (last_refresh_at, cached_slice).
    # Rolling-mode recomputes on every check so this stays None.
    _cached_slice_at: datetime | None = None
    _cached_slice: pl.DataFrame | None = None


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
# Datetime dtype helper
# ---------------------------------------------------------------------------


def _is_datetime_dtype(dtype: Any) -> bool:
    """Accept any parameterisation of ``pl.Datetime``.

    ``pl.Datetime`` is parameterised by ``(time_unit, time_zone)`` in
    modern polars, so ``dtype == pl.Datetime`` is False for e.g.
    ``Datetime('us', 'UTC')``. This helper walks the standard escape
    hatches so every supported shape is accepted.
    """
    try:
        # Polars ≥0.20: Datetime instances provide base_type().
        if hasattr(dtype, "base_type"):
            base = dtype.base_type()
            if base == pl.Datetime:
                return True
    except Exception:  # noqa: BLE001 — defensive for dtype API drift
        pass
    try:
        if isinstance(dtype, pl.Datetime):
            return True
    except TypeError:
        # Older polars raised if pl.Datetime was a class-like singleton.
        pass
    return dtype == pl.Datetime


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------


async def _migrate_references_legacy_shape(conn: ConnectionManager) -> None:
    """Migrate a legacy ``_kml_drift_references`` table (no ``tenant_id``
    column, single-column PK on ``model_name``) to the W26.e composite-PK
    shape. Safe no-op when the table is already at the new shape.

    Strategy: SQLite cannot alter a PK in place. We probe for the legacy
    shape via ``PRAGMA table_info``, and if the table exists AND lacks
    ``tenant_id``, we RENAME → CREATE new shape → INSERT SELECT with
    ``tenant_id=''`` → DROP legacy inside a single transaction so a crash
    mid-migration leaves the old table intact.

    Legacy rows land with ``tenant_id=''`` which is unreachable from the
    new tenant-required API (any DriftMonitor construction with empty
    tenant_id is rejected by :class:`TenantRequiredError`). We emit a
    ``drift.schema.legacy_rows_unreachable`` WARN so operators see the
    count that became orphaned and can plan a manual fix.
    """
    try:
        info = await conn.fetch("PRAGMA table_info(_kml_drift_references)")
    except Exception as exc:  # noqa: BLE001 — dialect probe best-effort
        logger.debug(
            "drift.migration.pragma_probe_skipped",
            extra={"drift_reason": str(exc)},
        )
        return

    if not info:
        # Table did not exist — the CREATE IF NOT EXISTS just landed
        # the new shape. Nothing to migrate.
        return

    columns = {row["name"] if hasattr(row, "__getitem__") else None for row in info}
    # ``__getitem__`` check above tolerates both dict-shaped rows and
    # asyncpg Record-shaped rows; filter out the None sentinel.
    columns = {c for c in columns if c is not None}
    if "tenant_id" in columns:
        # Already on the new shape.
        return

    logger.info(
        "drift.schema.legacy_references_detected",
        extra={"drift_columns": sorted(columns)},
    )

    # Perform the migration inside a single transaction so a crash
    # between rename and copy leaves the legacy table intact.
    async with conn.transaction() as tx:
        await tx.execute(
            "ALTER TABLE _kml_drift_references RENAME TO _kml_drift_references_legacy"
        )
        await tx.execute(
            "CREATE TABLE _kml_drift_references ("
            "  tenant_id TEXT NOT NULL,"
            "  model_name TEXT NOT NULL,"
            "  feature_columns TEXT NOT NULL,"
            "  statistics TEXT NOT NULL,"
            "  sample_size INTEGER NOT NULL,"
            "  set_at TEXT NOT NULL,"
            "  policy_json TEXT,"
            "  timestamp_column TEXT,"
            "  PRIMARY KEY (tenant_id, model_name)"
            ")"
        )
        # Copy rows. Legacy shape may or may not carry policy_json /
        # timestamp_column depending on whether W26.b ALTER TABLE ran.
        if "policy_json" in columns and "timestamp_column" in columns:
            copy_sql = (
                "INSERT INTO _kml_drift_references "
                "(tenant_id, model_name, feature_columns, statistics, "
                " sample_size, set_at, policy_json, timestamp_column) "
                "SELECT '', model_name, feature_columns, statistics, "
                "       sample_size, set_at, policy_json, timestamp_column "
                "FROM _kml_drift_references_legacy"
            )
        else:
            copy_sql = (
                "INSERT INTO _kml_drift_references "
                "(tenant_id, model_name, feature_columns, statistics, "
                " sample_size, set_at, policy_json, timestamp_column) "
                "SELECT '', model_name, feature_columns, statistics, "
                "       sample_size, set_at, NULL, NULL "
                "FROM _kml_drift_references_legacy"
            )
        await tx.execute(copy_sql)
        rows_moved_row = await tx.fetchone(
            "SELECT COUNT(*) AS n FROM _kml_drift_references"
        )
        await tx.execute("DROP TABLE _kml_drift_references_legacy")

    rows_moved = (
        rows_moved_row["n"]
        if rows_moved_row is not None and "n" in rows_moved_row
        else 0
    )
    logger.info(
        "drift.schema.migrated_references",
        extra={"drift_rows_moved": int(rows_moved)},
    )
    if rows_moved > 0:
        logger.warning(
            "drift.schema.legacy_rows_unreachable",
            extra={
                "drift_rows_moved": int(rows_moved),
                "drift_note": (
                    "Legacy tenant-less rows were migrated with "
                    "tenant_id=''. The W26.e API rejects empty tenant_id "
                    "at DriftMonitor construction, so these rows are "
                    "unreachable without a manual UPDATE to set tenant_id."
                ),
            },
        )


async def _create_drift_tables(conn: ConnectionManager) -> None:
    """Create drift monitor tables if they do not exist.

    W26.b extended ``_kml_drift_references`` with ``policy_json`` and
    ``timestamp_column`` to persist ``DriftMonitorReferencePolicy``
    configuration.

    W26.e introduces tenant-scoping end-to-end per ``specs/ml-drift.md``
    §4.1 and ``rules/tenant-isolation.md`` MUST 1-5. The reference PK
    becomes ``(tenant_id, model_name)`` — legacy tenant-less tables (no
    ``tenant_id`` column) are migrated in place via a RENAME + copy +
    DROP inside a single transaction. Reports and performance baselines
    gain a ``tenant_id`` column and tenant-indexed lookups.
    """
    # W26.e (§4.1 + rules/tenant-isolation.md MUST 1) — references are
    # tenant-scoped by composite PK. The CREATE IF NOT EXISTS path lands
    # the new shape on fresh DBs; legacy DBs created before W26.e get
    # migrated below.
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS _kml_drift_references ("
        "  tenant_id TEXT NOT NULL,"
        "  model_name TEXT NOT NULL,"
        "  feature_columns TEXT NOT NULL,"
        "  statistics TEXT NOT NULL,"
        "  sample_size INTEGER NOT NULL,"
        "  set_at TEXT NOT NULL,"
        "  policy_json TEXT,"
        "  timestamp_column TEXT,"
        "  PRIMARY KEY (tenant_id, model_name)"
        ")"
    )
    try:
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_drift_refs_tenant "
            "ON _kml_drift_references (tenant_id)"
        )
    except Exception as exc:  # noqa: BLE001 — dialect-agnostic idempotency
        logger.debug(
            "drift.migration.index_ddl_ignored",
            extra={
                "drift_ddl": "idx_drift_refs_tenant",
                "drift_reason": str(exc),
            },
        )

    # W26.e legacy-shape migration. SQLite cannot add/drop a PK via
    # ALTER TABLE, so the portable fix is RENAME + new CREATE + INSERT
    # SELECT + DROP inside a single transaction. We probe for the
    # legacy shape via PRAGMA table_info; if ``tenant_id`` is absent on
    # the table the CREATE IF NOT EXISTS above did NOT re-run (table
    # already existed). In that case the table here is the legacy
    # tenant-less one and we migrate it.
    await _migrate_references_legacy_shape(conn)

    # Legacy policy_json / timestamp_column idempotent ALTERs for W26.b
    # backward-compat. Only fire on tables that already carry tenant_id
    # (fresh tables from the CREATE above already have both columns).
    for col_ddl in (
        "ALTER TABLE _kml_drift_references ADD COLUMN policy_json TEXT",
        "ALTER TABLE _kml_drift_references ADD COLUMN timestamp_column TEXT",
    ):
        try:
            await conn.execute(col_ddl)
        except Exception as exc:  # noqa: BLE001 — dialect-agnostic idempotency
            logger.debug(
                "drift.migration.alter_table_ignored",
                extra={
                    "drift_ddl": col_ddl,
                    "drift_reason": str(exc),
                },
            )

    # W26.e — _kml_drift_reports gains tenant_id + tenant-checked_at index.
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS _kml_drift_reports ("
        "  id TEXT PRIMARY KEY,"
        "  tenant_id TEXT NOT NULL DEFAULT '',"
        "  model_name TEXT NOT NULL,"
        "  feature_results TEXT NOT NULL,"
        "  overall_drift INTEGER NOT NULL,"
        "  overall_severity TEXT NOT NULL,"
        "  checked_at TEXT NOT NULL"
        ")"
    )
    # Idempotent ALTER for legacy reports tables.
    try:
        await conn.execute(
            "ALTER TABLE _kml_drift_reports ADD COLUMN tenant_id "
            "TEXT NOT NULL DEFAULT ''"
        )
    except Exception as exc:  # noqa: BLE001 — dialect-agnostic idempotency
        logger.debug(
            "drift.migration.alter_table_ignored",
            extra={
                "drift_ddl": "reports.tenant_id",
                "drift_reason": str(exc),
            },
        )
    try:
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_drift_reports_tenant_checked "
            "ON _kml_drift_reports (tenant_id, checked_at DESC)"
        )
    except Exception as exc:  # noqa: BLE001 — dialect-agnostic idempotency
        logger.debug(
            "drift.migration.index_ddl_ignored",
            extra={
                "drift_ddl": "idx_drift_reports_tenant_checked",
                "drift_reason": str(exc),
            },
        )

    # W26.e — performance baselines tenant-scoped via added column.
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS _kml_performance_baselines ("
        "  tenant_id TEXT NOT NULL DEFAULT '',"
        "  model_name TEXT NOT NULL,"
        "  metrics TEXT NOT NULL,"
        "  set_at TEXT NOT NULL,"
        "  PRIMARY KEY (tenant_id, model_name)"
        ")"
    )
    # Legacy baseline tables may exist without tenant_id. SQLite cannot
    # re-PK, but we CAN add the column and let the application layer
    # filter by (tenant_id, model_name) — legacy rows see ``tenant_id=''``
    # and are only reachable by a monitor configured with an empty tenant
    # (which is now blocked by TenantRequiredError).
    try:
        await conn.execute(
            "ALTER TABLE _kml_performance_baselines ADD COLUMN tenant_id "
            "TEXT NOT NULL DEFAULT ''"
        )
    except Exception as exc:  # noqa: BLE001 — dialect-agnostic idempotency
        logger.debug(
            "drift.migration.alter_table_ignored",
            extra={
                "drift_ddl": "perf_baselines.tenant_id",
                "drift_reason": str(exc),
            },
        )
    # W26.c (spec §5.1) — restart-surviving drift schedules.
    # Landed with tenant_id + actor_id columns even though tenant-scoping
    # isn't fully wired across the monitor surface yet; a later
    # tenant-scoping shard will tighten API defaults, not migrate the
    # table. ``enabled`` is stored as INTEGER for SQLite portability
    # (SQLite has no native BOOLEAN type).
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS _kml_drift_schedules ("
        "  schedule_id TEXT PRIMARY KEY,"
        "  tenant_id TEXT NOT NULL DEFAULT '',"
        "  model_name TEXT NOT NULL,"
        "  model_version INTEGER NOT NULL DEFAULT 0,"
        "  interval_seconds INTEGER NOT NULL,"
        "  enabled INTEGER NOT NULL DEFAULT 1,"
        "  starts_at TEXT,"
        "  ends_at TEXT,"
        "  last_run_at TEXT,"
        "  last_run_outcome TEXT,"
        "  last_run_drift_detected INTEGER,"
        "  next_run_at TEXT NOT NULL,"
        "  created_at TEXT NOT NULL,"
        "  created_by_actor_id TEXT NOT NULL DEFAULT 'system',"
        "  updated_at TEXT NOT NULL"
        ")"
    )
    # Partial index on next_run_at (SQLite 3.8+; PostgreSQL + MySQL both
    # accept the same syntax). Fallback on older engines is handled via
    # try/except below — non-partial index is functionally equivalent for
    # the scheduler polling query.
    for idx_ddl in (
        "CREATE INDEX IF NOT EXISTS idx_drift_sched_next "
        "ON _kml_drift_schedules (next_run_at) WHERE enabled = 1",
        "CREATE INDEX IF NOT EXISTS idx_drift_sched_tenant "
        "ON _kml_drift_schedules (tenant_id)",
    ):
        try:
            await conn.execute(idx_ddl)
        except Exception as exc:  # noqa: BLE001 — partial-index fallback
            # SQLite < 3.8 rejects "WHERE" in CREATE INDEX. Fall back to
            # non-partial for the next_run_at index; non-partial is the
            # same structure, slightly larger. The tenant_id index has
            # no partial clause so this branch only fires if the DDL
            # hits a true engine issue — log at DEBUG regardless.
            logger.debug(
                "drift.migration.index_ddl_ignored",
                extra={
                    "drift_ddl": idx_ddl,
                    "drift_reason": str(exc),
                },
            )
            if "WHERE" in idx_ddl:
                try:
                    await conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_drift_sched_next "
                        "ON _kml_drift_schedules (next_run_at)"
                    )
                except Exception as fallback_exc:  # noqa: BLE001
                    logger.debug(
                        "drift.migration.index_fallback_ignored",
                        extra={"drift_reason": str(fallback_exc)},
                    )


# ---------------------------------------------------------------------------
# DriftMonitor
# ---------------------------------------------------------------------------


class DriftMonitor:
    """[P0: Production] Drift monitor for model performance monitoring.

    W26.e (``specs/ml-drift.md §4.1`` + ``rules/tenant-isolation.md``):
    every :class:`DriftMonitor` instance is bound to exactly ONE tenant.
    Multi-tenant deployments construct N monitors (one per tenant).
    Passing an empty ``tenant_id`` raises :class:`TenantRequiredError` at
    construction time — silent fallback to a shared tenant is blocked
    per ``rules/zero-tolerance.md`` Rule 3.

    Parameters
    ----------
    conn:
        An initialized ConnectionManager.
    tenant_id:
        **Required.** Non-empty tenant scope for every reference, report,
        schedule, alert, and performance baseline this monitor writes.
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
        tenant_id: str,
        psi_threshold: float = 0.2,
        ks_threshold: float = 0.05,
        performance_threshold: float = 0.1,
        thresholds: DriftThresholds | None = None,
        tracker: Any = None,
        alerts: AlertConfig | None = None,
    ) -> None:
        import math

        # W26.e: tenant_id is REQUIRED. Empty string + non-string raise
        # to close the "silent fallback to shared tenant" failure mode.
        if not isinstance(tenant_id, str):
            raise TypeError(
                f"tenant_id must be a string, got {type(tenant_id).__name__}"
            )
        if not tenant_id:
            raise TenantRequiredError(
                reason=(
                    "DriftMonitor requires a non-empty tenant_id. "
                    "Construct DriftMonitor(conn, tenant_id='<your_tenant>'). "
                    "Multi-tenant deployments construct one DriftMonitor "
                    "instance per tenant."
                ),
            )

        for name, val in [
            ("psi_threshold", psi_threshold),
            ("ks_threshold", ks_threshold),
            ("performance_threshold", performance_threshold),
        ]:
            if not math.isfinite(val):
                raise ValueError(f"{name} must be finite, got {val}")

        self._conn = conn
        self._tenant_id = tenant_id
        self._psi_threshold = psi_threshold
        self._ks_threshold = ks_threshold
        self._performance_threshold = performance_threshold
        # W26: per-column threshold config.  Falls back to legacy
        # psi_threshold / ks_threshold values when None so pre-W26
        # constructors are unaffected.
        self._thresholds = thresholds or DriftThresholds(
            psi=psi_threshold, ks_pvalue=ks_threshold
        )
        # W26: optional duck-typed tracker.  When set, check_drift emits
        # ``log_metric("drift/{feature}/{statistic}", value)`` per
        # spec §6.4.  The duck-typed contract is the same shape
        # RLDiagnostics / DLDiagnostics consume — any object exposing
        # ``log_metric(key, value, *, step=None)`` satisfies it.
        self._tracker = tracker
        self._initialized = False
        # In-memory reference cache (bounded to prevent OOM with many
        # models). W26.e composite (tenant_id, model_name) key —
        # defense-in-depth per rules/tenant-isolation.md MUST 1 even
        # though a single monitor instance is already tenant-scoped.
        self._references: dict[tuple[str, str], _StoredReference] = {}
        self._max_references = 100
        # W26.c (spec §5) — persistent restart-surviving schedules.
        # ``_data_sources`` maps schedule_id → async data_fn. Python
        # callables are not persistable, so after process restart the
        # caller MUST re-register via ``register_data_source`` before
        # ``start_scheduler`` dispatches the schedule. ``_scheduled_specs``
        # holds the optional DriftSpec (callback + threshold overrides)
        # per schedule_id for the worker dispatch path.
        self._data_sources: dict[str, Any] = {}
        self._scheduled_specs: dict[str, DriftSpec] = {}
        # Legacy in-process task map retained for the deprecated
        # ``active_schedules`` property + ``cancel_monitoring`` shim so
        # downstream consumers (dashboard/server.py) keep working.
        self._scheduled_tasks: dict[str, asyncio.Task[None]] = {}
        # Worker loop state
        self._scheduler_worker_task: asyncio.Task[None] | None = None
        self._scheduler_running: bool = False
        # W26.b: minimum rows in a policy-sliced reference before
        # check_drift will run the statistics. Below this raise
        # InsufficientSamplesError rather than emit a report computed
        # against a sparse slice — slice sparsity itself is a data
        # finding, not a drift one.
        self._min_slice_samples: int = 10
        # W26.d: optional alerting surface.  Per spec §6.1 the
        # dispatcher is in-memory per DriftMonitor instance; cross-
        # process coordination is an explicit non-goal for this shard.
        self._alert_dispatcher: DriftAlertDispatcher | None = (
            DriftAlertDispatcher(alerts) if alerts is not None else None
        )

    async def _ensure_tables(self) -> None:
        if not self._initialized:
            await _create_drift_tables(self._conn)
            self._initialized = True

    # ------------------------------------------------------------------
    # Per-feature summary statistics (extracted so both set_reference_data
    # and policy-driven slicing in check_drift can re-derive them).
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_reference_summary(
        reference_data: pl.DataFrame,
        feature_columns: list[str],
    ) -> tuple[dict[str, pl.Series], dict[str, Any]]:
        """Return (per-feature Series dict, per-feature stats dict)."""
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
        return data_series, statistics

    # ------------------------------------------------------------------
    # Policy-driven reference slicing (W26.b) — returns the effective
    # reference DataFrame for a given ``checked_at``. Static mode
    # short-circuits to the original frame; rolling/sliding/seasonal
    # filter on the stored timestamp column.
    # ------------------------------------------------------------------

    @staticmethod
    def _slice_reference(
        reference: _StoredReference,
        checked_at: datetime,
    ) -> pl.DataFrame:
        """Return the policy-appropriate reference slice.

        Contract:
        - ``static``: returns the full raw frame unchanged.
        - ``rolling``: returns rows in ``[checked_at - window, checked_at)``.
        - ``sliding``: same as rolling but memoised per ``refresh_cadence``.
        - ``seasonal``: returns rows in ``[checked_at - period - tol,
          checked_at - period + tol]`` where ``tol`` is ``policy.window``
          or a sensible default.

        Raises
        ------
        DriftMonitorError
            When policy != static but no raw reference / timestamp
            column was stored.
        """
        policy = reference.policy
        if policy.mode == "static":
            if reference.raw_data is None:
                # Pure static-mode path — raw_data isn't stored.
                # _slice_reference is only called for non-static modes
                # from check_drift, so this branch is defensive.
                return pl.DataFrame({name: s for name, s in reference.data.items()})
            return reference.raw_data

        if reference.raw_data is None or reference.timestamp_column is None:
            raise DriftMonitorError(
                reason=(
                    "Non-static DriftMonitorReferencePolicy requires raw "
                    "reference_data and a timestamp_column; set_reference_data "
                    "may not have been called with these arguments"
                ),
                resource_id=reference.model_name,
            )

        ts_col = reference.timestamp_column
        raw = reference.raw_data

        if policy.mode in ("rolling", "sliding"):
            if policy.mode == "sliding":
                cadence = policy.refresh_cadence
                if (
                    cadence is not None
                    and reference._cached_slice is not None
                    and reference._cached_slice_at is not None
                    and (checked_at - reference._cached_slice_at) < cadence
                ):
                    return reference._cached_slice
            assert policy.window is not None
            lower = checked_at - policy.window
            sliced = raw.filter(
                (pl.col(ts_col) >= lower) & (pl.col(ts_col) < checked_at)
            )
            if policy.mode == "sliding":
                reference._cached_slice_at = checked_at
                reference._cached_slice = sliced
            return sliced

        # mode == "seasonal"
        assert policy.seasonal_period is not None
        anchor = checked_at - policy.seasonal_period
        # Tolerance defaults to the explicit policy.window if set,
        # else 1/24 of the seasonal period (approx. one hour for a
        # weekly period) with a minimum of one hour so intra-hour
        # rounding never produces empty slices.
        if policy.window is not None:
            tol = policy.window
        else:
            tol = max(policy.seasonal_period / 24, timedelta(hours=1))
        lower = anchor - tol
        upper = anchor + tol
        return raw.filter((pl.col(ts_col) >= lower) & (pl.col(ts_col) <= upper))

    # ------------------------------------------------------------------
    # set_reference_data
    # ------------------------------------------------------------------

    async def set_reference_data(
        self,
        model_name: str,
        reference_data: pl.DataFrame,
        feature_columns: list[str],
        *,
        policy: DriftMonitorReferencePolicy | None = None,
        timestamp_column: str | None = None,
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
        policy:
            Optional :class:`DriftMonitorReferencePolicy`. When ``None``
            or ``policy.mode == "static"`` the monitor retains the
            pre-W26.b lightweight per-feature Series form. Non-static
            policies require ``timestamp_column`` and persist the full
            reference DataFrame so slicing is deterministic.
        timestamp_column:
            Required when ``policy.mode != "static"``. MUST name a
            ``pl.Datetime`` column in ``reference_data``.

        Raises
        ------
        DriftThresholdError
            When non-static policy is supplied without a valid
            timestamp column.
        """
        await self._ensure_tables()

        resolved_policy = policy or DriftMonitorReferencePolicy()

        if resolved_policy.mode != "static":
            if timestamp_column is None:
                raise DriftThresholdError(
                    reason=(
                        f"DriftMonitorReferencePolicy.mode={resolved_policy.mode!r} "
                        "requires timestamp_column"
                    ),
                    resource_id=model_name,
                )
            if timestamp_column not in reference_data.columns:
                raise DriftThresholdError(
                    reason=(
                        f"timestamp_column={timestamp_column!r} not present in "
                        f"reference_data columns={list(reference_data.columns)!r}"
                    ),
                    resource_id=model_name,
                )
            ts_dtype = reference_data[timestamp_column].dtype
            if not _is_datetime_dtype(ts_dtype):
                raise DriftThresholdError(
                    reason=(
                        f"timestamp_column={timestamp_column!r} MUST be "
                        f"pl.Datetime, got {ts_dtype!r}"
                    ),
                    resource_id=model_name,
                )
        elif timestamp_column is not None:
            # Accept timestamp_column for static mode as a forward-compat
            # storage hint but raise if it's missing from the frame.
            if timestamp_column not in reference_data.columns:
                raise DriftThresholdError(
                    reason=(
                        f"timestamp_column={timestamp_column!r} not present in "
                        f"reference_data columns={list(reference_data.columns)!r}"
                    ),
                    resource_id=model_name,
                )

        now = datetime.now(timezone.utc)

        data_series, statistics = self._compute_reference_summary(
            reference_data, feature_columns
        )

        # Keep the full raw frame for non-static policies so
        # check_drift can slice deterministically. Static mode retains
        # its lightweight per-feature Series form for backward compat.
        raw_data: pl.DataFrame | None = (
            reference_data if resolved_policy.mode != "static" else None
        )

        ref = _StoredReference(
            model_name=model_name,
            feature_columns=feature_columns,
            data=data_series,
            statistics=statistics,
            sample_size=reference_data.height,
            set_at=now,
            policy=resolved_policy,
            timestamp_column=timestamp_column,
            raw_data=raw_data,
        )
        cache_key = (self._tenant_id, model_name)
        self._references[cache_key] = ref
        # Evict oldest references if over limit
        while len(self._references) > self._max_references:
            oldest_key = next(iter(self._references))
            if oldest_key != cache_key:
                del self._references[oldest_key]
            else:
                break

        policy_json = json.dumps(resolved_policy.to_dict())

        # Persist to database (transaction eliminates TOCTOU race).
        # W26.e composite PK (tenant_id, model_name) per §4.2.
        async with self._conn.transaction() as tx:
            existing = await tx.fetchone(
                "SELECT model_name FROM _kml_drift_references "
                "WHERE tenant_id = ? AND model_name = ?",
                self._tenant_id,
                model_name,
            )
            if existing:
                await tx.execute(
                    "UPDATE _kml_drift_references "
                    "SET feature_columns = ?, statistics = ?, sample_size = ?, "
                    "    set_at = ?, policy_json = ?, timestamp_column = ? "
                    "WHERE tenant_id = ? AND model_name = ?",
                    json.dumps(feature_columns),
                    json.dumps(statistics, default=str),
                    reference_data.height,
                    now.isoformat(),
                    policy_json,
                    timestamp_column,
                    self._tenant_id,
                    model_name,
                )
            else:
                await tx.execute(
                    "INSERT INTO _kml_drift_references "
                    "(tenant_id, model_name, feature_columns, statistics, "
                    " sample_size, set_at, policy_json, timestamp_column) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    self._tenant_id,
                    model_name,
                    json.dumps(feature_columns),
                    json.dumps(statistics, default=str),
                    reference_data.height,
                    now.isoformat(),
                    policy_json,
                    timestamp_column,
                )

        logger.info(
            "drift.reference.set",
            extra={
                "drift_tenant_id": self._tenant_id,
                "drift_model_name": model_name,
                "drift_sample_count": reference_data.height,
                "drift_feature_count": len(feature_columns),
            },
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
        checked_at: datetime | None = None,
    ) -> DriftReport:
        """Check feature drift against stored reference.

        W26.e — this monitor is bound to ``self._tenant_id`` at
        construction; every reference lookup + report write is scoped to
        that tenant. No per-call ``tenant_id`` kwarg is accepted.

        Parameters
        ----------
        model_name:
            Model identifier (must have a reference set).
        current_data:
            Current dataset to compare.
        agent:
            Optional agent for drift interpretation.
        checked_at:
            Wall-clock anchor used to slice the reference when the
            model's policy is non-static. Defaults to
            ``datetime.now(timezone.utc)``. Tests MUST pin this so the
            time axis is deterministic.

        Returns
        -------
        DriftReport

        Raises
        ------
        ReferenceNotFoundError
            If no reference is set for the model under this monitor's
            tenant scope.
        InsufficientSamplesError
            If a non-static policy's slice contains fewer than
            ``_min_slice_samples`` rows.
        """
        await self._ensure_tables()

        cache_key = (self._tenant_id, model_name)
        reference = self._references.get(cache_key)
        if reference is None:
            raise ReferenceNotFoundError(
                reason=(
                    f"No reference set for model {model_name!r} under "
                    f"tenant_id={self._tenant_id!r}. Call "
                    "set_reference_data() first."
                ),
                resource_id=model_name,
                tenant_id=self._tenant_id,
            )

        resolved_checked_at = checked_at or datetime.now(timezone.utc)

        logger.info(
            "drift.check.start",
            extra={
                "drift_tenant_id": self._tenant_id,
                "drift_model_name": model_name,
                "drift_mode": reference.policy.mode,
                "drift_checked_at": resolved_checked_at.isoformat(),
            },
        )

        # Policy-driven reference re-materialisation. Static mode keeps
        # the stored per-feature Series form; non-static modes re-slice
        # and recompute the summary against the sliced window.
        if reference.policy.mode == "static":
            effective_ref_series: dict[str, pl.Series] = reference.data
            effective_sample_size = reference.sample_size
        else:
            sliced = self._slice_reference(reference, resolved_checked_at)
            min_samples = self._min_slice_samples
            if sliced.height < min_samples:
                raise InsufficientSamplesError(
                    reason=(
                        f"Policy-sliced reference for model {model_name!r} "
                        f"(tenant_id={self._tenant_id!r}) has {sliced.height} "
                        f"rows; require >= {min_samples}"
                    ),
                    resource_id=model_name,
                    tenant_id=self._tenant_id,
                    mode=reference.policy.mode,
                    checked_at=resolved_checked_at.isoformat(),
                )
            effective_ref_series, _ = self._compute_reference_summary(
                sliced, reference.feature_columns
            )
            effective_sample_size = sliced.height

        feature_results: list[FeatureDriftResult] = []

        for feature_name in reference.feature_columns:
            ref_series = effective_ref_series[feature_name]
            if feature_name not in current_data.columns:
                logger.warning(
                    "drift.check.feature_missing",
                    extra={
                        "drift_tenant_id": self._tenant_id,
                        "drift_model_name": model_name,
                        "drift_feature": feature_name,
                    },
                )
                continue
            cur_series = current_data[feature_name]
            per_col_thresholds = self._thresholds.resolve(feature_name)
            stats_to_compute = select_statistics(ref_series)

            psi = _compute_psi(ref_series, cur_series)

            # KS test only for numeric features
            is_numeric = ref_series.dtype not in (pl.Categorical, pl.Utf8, pl.String)
            if is_numeric and "ks" in stats_to_compute:
                ks_stat, ks_pval = _compute_ks(ref_series, cur_series)
            else:
                ks_stat, ks_pval = 0.0, 1.0

            # W26: chi² for categorical / boolean columns.
            chi2_stat: float | None = None
            chi2_pval: float | None = None
            if "chi2" in stats_to_compute:
                chi2_stat, chi2_pval = chi2_test(ref_series, cur_series)

            # W26: JSD for continuous + categorical.  Zero-variance
            # reference raises at the stats layer; surface as a
            # per-feature stability note rather than abort the whole
            # check_drift call (the caller may want to see the other
            # features' drift state even if one column is degenerate).
            jsd: float | None = None
            stability_note: str | None = None
            if "jsd" in stats_to_compute:
                try:
                    if is_numeric:
                        jsd = jensen_shannon_continuous(ref_series, cur_series)
                    else:
                        jsd = jensen_shannon_discrete(ref_series, cur_series)
                except ZeroVarianceReferenceError as exc:
                    stability_note = f"zero_variance_reference:{feature_name}"
                    logger.warning(
                        "drift.jsd.zero_variance_reference",
                        extra={
                            "drift_tenant_id": self._tenant_id,
                            "drift_model_name": model_name,
                            "drift_feature": feature_name,
                            "drift_reason": str(exc),
                        },
                    )

            new_cat_frac: float | None = None
            if "new_category" in stats_to_compute:
                new_cat_frac = _new_category_fraction(ref_series, cur_series)

            # Aggregate drift detection across every computed statistic.
            drift_detected = (
                psi > per_col_thresholds["psi"]
                or (is_numeric and ks_pval < per_col_thresholds["ks_pvalue"])
                or (
                    chi2_pval is not None
                    and chi2_pval < per_col_thresholds["chi2_pvalue"]
                )
                or (jsd is not None and jsd >= per_col_thresholds["jsd"])
                or (
                    new_cat_frac is not None
                    and new_cat_frac > per_col_thresholds["new_category_fraction"]
                )
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
                    chi2_statistic=chi2_stat,
                    chi2_pvalue=chi2_pval,
                    jsd=jsd,
                    new_category_fraction=new_cat_frac,
                    statistics_used=sorted(stats_to_compute),
                    stability_note=stability_note,
                )
            )

            # W26: tracker emission per spec §6.4 + todo invariant 4.
            # Emits one ``log_metric`` per computed statistic, keyed as
            # ``drift/{feature}/{statistic}``.  Best-effort — a tracker
            # backend error MUST NOT abort drift detection.
            if self._tracker is not None:
                self._emit_feature_metrics(
                    feature_name=feature_name,
                    psi=psi,
                    ks_pval=(
                        ks_pval if is_numeric and "ks" in stats_to_compute else None
                    ),
                    chi2_pval=chi2_pval,
                    jsd=jsd,
                    new_cat_frac=new_cat_frac,
                    drift_detected=drift_detected,
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
            checked_at=resolved_checked_at,
            reference_set_at=reference.set_at,
            sample_size_reference=effective_sample_size,
            sample_size_current=current_data.height,
        )

        # Store report (returns report_id for alert dispatch linkback)
        report_id = await self._store_report(report)

        logger.info(
            "drift.check.ok",
            extra={
                "drift_tenant_id": self._tenant_id,
                "drift_model_name": model_name,
                "drift_mode": reference.policy.mode,
                "drift_overall_drift": overall_drift,
                "drift_overall_severity": overall_severity,
            },
        )

        # W26.d: evaluate + dispatch alerts per spec §6.2.  Dispatcher
        # errors from individual channels are already swallowed+logged
        # inside the dispatcher; a catastrophic dispatcher failure
        # (state mutation, bug) is caught here so drift detection
        # returns the report regardless.
        if self._alert_dispatcher is not None:
            try:
                await self._alert_dispatcher.evaluate_and_dispatch(
                    report=report,
                    tenant_id=self._tenant_id,
                    model_name=model_name,
                    # W26.d passthrough — registry/version wiring is a
                    # follow-up shard. Use 0 as the sentinel and keep
                    # the DriftAlert payload field stable.
                    model_version=0,
                    report_id=report_id,
                )
            except Exception:  # pragma: no cover - defense-in-depth
                logger.exception(
                    "drift.alert.dispatcher_error",
                    extra={
                        "drift_tenant_id": self._tenant_id,
                        "drift_model_name": model_name,
                        "drift_report_id": report_id,
                    },
                )

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
        """Retrieve stored drift reports for a model.

        W26.e — filters by ``self._tenant_id`` so cross-tenant reports
        are never returned.
        """
        await self._ensure_tables()
        return await self._conn.fetch(
            "SELECT * FROM _kml_drift_reports "
            "WHERE tenant_id = ? AND model_name = ? "
            "ORDER BY checked_at DESC LIMIT ?",
            self._tenant_id,
            model_name,
            limit,
        )

    # ------------------------------------------------------------------
    # Scheduled monitoring — W26.c restart-surviving (spec §5)
    # ------------------------------------------------------------------

    async def schedule_monitoring(
        self,
        model_name: str,
        interval: timedelta,
        data_fn: Any,  # async callable returning pl.DataFrame
        *,
        spec: DriftSpec | None = None,
        actor_id: str = "system",
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
        enabled: bool = True,
        schedule_id: str | None = None,
    ) -> str:
        """Persist a restart-surviving drift-check schedule.

        W26.e — the schedule is written with ``tenant_id = self._tenant_id``.
        No per-call ``tenant_id`` kwarg is accepted; multi-tenant
        deployments construct one :class:`DriftMonitor` per tenant.

        Per ``specs/ml-drift.md §5``, the schedule is written to
        ``_kml_drift_schedules`` BEFORE the scheduler worker dispatches
        it. The Python callable ``data_fn`` is registered in-process on
        ``self._data_sources[schedule_id]`` — after a process restart,
        the caller MUST re-register via :meth:`register_data_source`
        with the original ``schedule_id`` before calling
        :meth:`start_scheduler`.

        Parameters
        ----------
        model_name:
            Model identifier (must have a reference set on this monitor
            instance when the schedule is first registered).
        interval:
            How often to run drift checks. Must be >= 1 second.
        data_fn:
            Async callable that returns the current data as ``pl.DataFrame``.
        spec:
            Optional :class:`DriftSpec` overrides (thresholds + on-drift
            callback).
        actor_id:
            Audit attribution for the schedule row.
        starts_at:
            First dispatch time (UTC). Defaults to immediately.
        ends_at:
            Optional expiry — schedules past this are skipped by the
            worker (enabled remains 1).
        enabled:
            Initial enabled state. ``False`` writes the row but the
            scheduler worker will skip it until re-enabled.
        schedule_id:
            Caller-supplied id (defaults to ``uuid4()``). Use when
            re-registering a schedule that previously existed
            (e.g. after restart if the caller tracks ids externally).

        Returns
        -------
        str
            The ``schedule_id`` of the persisted schedule row.
        """
        if (self._tenant_id, model_name) not in self._references:
            raise ValueError(
                f"No reference set for model '{model_name}' under "
                f"tenant_id={self._tenant_id!r}. "
                "Call set_reference_data() first."
            )
        if interval.total_seconds() < 1:
            raise ValueError("Monitoring interval must be at least 1 second.")

        await self._ensure_tables()

        resolved_id = schedule_id or str(uuid.uuid4())
        interval_seconds = int(interval.total_seconds())
        now = datetime.now(timezone.utc)
        resolved_start = starts_at or now
        next_run_at = resolved_start

        await self._conn.execute(
            "INSERT INTO _kml_drift_schedules "
            "(schedule_id, tenant_id, model_name, model_version, "
            " interval_seconds, enabled, starts_at, ends_at, "
            " next_run_at, created_at, created_by_actor_id, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            resolved_id,
            self._tenant_id,
            model_name,
            0,
            interval_seconds,
            1 if enabled else 0,
            resolved_start.isoformat() if starts_at is not None else None,
            ends_at.isoformat() if ends_at is not None else None,
            next_run_at.isoformat(),
            now.isoformat(),
            actor_id,
            now.isoformat(),
        )

        self._data_sources[resolved_id] = data_fn
        self._scheduled_specs[resolved_id] = spec or DriftSpec()

        logger.info(
            "drift.scheduler.schedule_created",
            extra={
                "drift_schedule_id": resolved_id,
                "drift_tenant_id": self._tenant_id,
                "drift_model_name": model_name,
                "drift_interval_seconds": interval_seconds,
                "drift_actor_id": actor_id,
            },
        )
        return resolved_id

    def register_data_source(self, schedule_id: str, data_fn: Any) -> None:
        """Re-register the async data callable for a persisted schedule.

        REQUIRED after a process restart for every schedule the caller
        wants the scheduler worker to dispatch. Schedules without a
        registered data source are skipped with a WARN log line per
        :meth:`_poll_and_dispatch` — the worker does not crash.
        """
        self._data_sources[schedule_id] = data_fn
        # Keep a default spec available — callers can upgrade via
        # ``register_spec`` if they need to restore thresholds / callback.
        self._scheduled_specs.setdefault(schedule_id, DriftSpec())

    def register_spec(self, schedule_id: str, spec: DriftSpec) -> None:
        """Re-register the :class:`DriftSpec` for a persisted schedule.

        Optional counterpart to :meth:`register_data_source` for callers
        that need to restore threshold overrides / drift callbacks after
        a process restart. The ``DriftSpec.on_drift_detected`` callable
        is not serialisable, so the caller owns its recovery.
        """
        self._scheduled_specs[schedule_id] = spec

    async def cancel_schedule(
        self,
        schedule_id: str,
        *,
        actor_id: str = "system",
        reason: str = "",
    ) -> bool:
        """Disable a persisted schedule (spec §5.5 soft-cancel).

        W26.e — scoped to ``self._tenant_id``. Returns ``False`` when
        ``schedule_id`` does not exist OR exists under a different
        tenant, so cross-tenant cancels are impossible.

        Sets ``enabled = 0`` + updates ``updated_at``. Returns ``True``
        if a row existed under this monitor's tenant and was previously
        enabled, ``False`` otherwise. Also drops any in-process dispatch
        task the legacy shim may have spawned.
        """
        await self._ensure_tables()

        now_iso = datetime.now(timezone.utc).isoformat()
        row = await self._conn.fetchone(
            "SELECT enabled, model_name FROM _kml_drift_schedules "
            "WHERE schedule_id = ? AND tenant_id = ?",
            schedule_id,
            self._tenant_id,
        )
        if row is None:
            return False

        was_enabled = bool(row["enabled"])
        if was_enabled:
            await self._conn.execute(
                "UPDATE _kml_drift_schedules "
                "SET enabled = 0, updated_at = ? "
                "WHERE schedule_id = ? AND tenant_id = ?",
                now_iso,
                schedule_id,
                self._tenant_id,
            )

        # Also clean up the legacy in-process task keyed by model_name
        # if this schedule was dispatched through the shim path.
        model_name = row["model_name"] if hasattr(row, "__getitem__") else None
        if model_name is not None:
            task = self._scheduled_tasks.pop(model_name, None)
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        logger.info(
            "drift.scheduler.cancel",
            extra={
                "drift_tenant_id": self._tenant_id,
                "drift_schedule_id": schedule_id,
                "drift_actor_id": actor_id,
                "drift_reason": reason,
                "drift_was_enabled": was_enabled,
            },
        )
        return was_enabled

    async def list_schedules(
        self,
        *,
        model_name: str | None = None,
        enabled_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Return persisted schedule rows scoped to this monitor's tenant.

        W26.e — results are always filtered by ``self._tenant_id``; no
        per-call ``tenant_id`` kwarg is accepted.

        Filters:
          - ``model_name`` — restrict to a single model.
          - ``enabled_only`` — exclude disabled schedules (default).

        Each returned dict contains the columns from
        ``_kml_drift_schedules`` plus an ``enabled: bool`` projection
        (SQLite stores ``enabled`` as INTEGER 0/1; the boolean projection
        is the cross-dialect stable form).
        """
        await self._ensure_tables()

        clauses: list[str] = ["tenant_id = ?"]
        params: list[Any] = [self._tenant_id]
        if enabled_only:
            clauses.append("enabled = 1")
        if model_name is not None:
            clauses.append("model_name = ?")
            params.append(model_name)

        where = f"WHERE {' AND '.join(clauses)}"
        sql = (
            "SELECT schedule_id, tenant_id, model_name, model_version, "
            "       interval_seconds, enabled, starts_at, ends_at, "
            "       last_run_at, last_run_outcome, last_run_drift_detected, "
            "       next_run_at, created_at, created_by_actor_id, updated_at "
            f"FROM _kml_drift_schedules {where} "
            "ORDER BY next_run_at ASC"
        )
        rows = await self._conn.fetch(sql, *params)
        result: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["enabled"] = bool(d.get("enabled"))
            if d.get("last_run_drift_detected") is not None:
                d["last_run_drift_detected"] = bool(d["last_run_drift_detected"])
            result.append(d)
        return result

    async def start_scheduler(self, *, poll_interval: float = 10.0) -> None:
        """Start the background worker that polls _kml_drift_schedules.

        Spawns exactly one coroutine per monitor instance. The worker
        polls the persisted schedule table every ``poll_interval``
        seconds, atomically claims due schedules, and dispatches the
        drift check through :meth:`check_drift`.

        Re-calling ``start_scheduler`` when already running is a no-op.
        """
        if self._scheduler_running:
            return
        await self._ensure_tables()
        self._scheduler_running = True
        self._scheduler_worker_task = asyncio.create_task(
            self._scheduler_worker(poll_interval),
            name="drift-scheduler-worker",
        )
        logger.info(
            "drift.scheduler.started",
            extra={
                "drift_tenant_id": self._tenant_id,
                "drift_poll_interval_seconds": poll_interval,
            },
        )

    async def stop_scheduler(self) -> None:
        """Cancel the background worker and any in-flight legacy tasks."""
        self._scheduler_running = False
        if self._scheduler_worker_task is not None:
            self._scheduler_worker_task.cancel()
            try:
                await self._scheduler_worker_task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001 — defensive on shutdown
                logger.debug(
                    "drift.scheduler.stop_error",
                    extra={"drift_tenant_id": self._tenant_id},
                    exc_info=True,
                )
            self._scheduler_worker_task = None
        # Drop any legacy in-process tasks left by the deprecated
        # ``cancel_monitoring`` shim path.
        for model_name in list(self._scheduled_tasks):
            task = self._scheduled_tasks.pop(model_name, None)
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.info(
            "drift.scheduler.stopped",
            extra={"drift_tenant_id": self._tenant_id},
        )

    async def _scheduler_worker(self, poll_interval: float) -> None:
        """Worker loop polling the schedule table (spec §5.2)."""
        while self._scheduler_running:
            try:
                await self._poll_and_dispatch()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — worker resilience
                logger.exception(
                    "drift.scheduler.poll_error",
                    extra={"drift_tenant_id": self._tenant_id},
                )
            try:
                await asyncio.sleep(poll_interval)
            except asyncio.CancelledError:
                raise

    async def _poll_and_dispatch(self) -> None:
        """Claim due schedules and dispatch drift checks (spec §5.2-5.3).

        Atomic claim protocol (cross-dialect, no ``RETURNING``):

        1. ``SELECT`` enabled rows with ``next_run_at <= now`` and
           ``next_run_at`` matching a snapshot we took (optimistic read).
        2. ``UPDATE`` with a ``WHERE next_run_at = ?`` guard — if another
           process / worker already bumped ``next_run_at`` the guard
           fails silently and we skip.
        3. Re-``SELECT`` the row and verify ``next_run_at`` matches the
           new value we tried to write — this is the optimistic-concurrency
           confirmation (rowcount is surfaced inconsistently across
           aiosqlite / asyncpg / aiomysql; round-trip read is the portable
           form).
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        # W26.e — tenant-scoped poll; each monitor worker only claims
        # schedules for its own tenant. Replicas for different tenants
        # poll the same table without cross-tenant dispatch.
        due_rows = await self._conn.fetch(
            "SELECT schedule_id, interval_seconds, next_run_at, "
            "       model_name, ends_at "
            "FROM _kml_drift_schedules "
            "WHERE tenant_id = ? AND enabled = 1 AND next_run_at <= ? "
            "ORDER BY next_run_at ASC",
            self._tenant_id,
            now_iso,
        )
        for row in due_rows:
            schedule_id = row["schedule_id"]
            old_next_run = row["next_run_at"]
            interval_seconds = int(row["interval_seconds"])
            model_name = row["model_name"]
            ends_at = row.get("ends_at") if hasattr(row, "get") else row["ends_at"]

            # Honour ends_at — treat as past-expiry, don't claim but
            # leave the row alone (operators inspect + disable).
            if ends_at is not None:
                try:
                    ends_at_dt = datetime.fromisoformat(ends_at)
                    if ends_at_dt.tzinfo is None:
                        ends_at_dt = ends_at_dt.replace(tzinfo=timezone.utc)
                    if now >= ends_at_dt:
                        continue
                except ValueError:
                    logger.debug(
                        "drift.scheduler.ends_at_unparseable",
                        extra={
                            "drift_tenant_id": self._tenant_id,
                            "drift_schedule_id": schedule_id,
                            "drift_ends_at": ends_at,
                        },
                    )

            new_next_run = now + timedelta(seconds=interval_seconds)
            new_next_run_iso = new_next_run.isoformat()

            # Atomic claim — update only if another process hasn't
            # already moved ``next_run_at``. W26.e: also guard by
            # tenant_id so a fiddled tenant_id column cannot let
            # another tenant's worker silently move the row.
            await self._conn.execute(
                "UPDATE _kml_drift_schedules "
                "SET next_run_at = ?, updated_at = ? "
                "WHERE schedule_id = ? AND tenant_id = ? "
                "  AND next_run_at = ? AND enabled = 1",
                new_next_run_iso,
                now_iso,
                schedule_id,
                self._tenant_id,
                old_next_run,
            )
            confirm = await self._conn.fetchone(
                "SELECT next_run_at FROM _kml_drift_schedules "
                "WHERE schedule_id = ? AND tenant_id = ?",
                schedule_id,
                self._tenant_id,
            )
            if confirm is None or confirm["next_run_at"] != new_next_run_iso:
                logger.debug(
                    "drift.scheduler.claim_contended",
                    extra={
                        "drift_tenant_id": self._tenant_id,
                        "drift_schedule_id": schedule_id,
                    },
                )
                continue

            logger.debug(
                "drift.scheduler.claim_won",
                extra={
                    "drift_tenant_id": self._tenant_id,
                    "drift_schedule_id": schedule_id,
                },
            )

            data_fn = self._data_sources.get(schedule_id)
            if data_fn is None:
                logger.warning(
                    "drift.scheduler.missing_data_source",
                    extra={
                        "drift_tenant_id": self._tenant_id,
                        "drift_schedule_id": schedule_id,
                        "drift_model_name": model_name,
                    },
                )
                continue

            spec = self._scheduled_specs.get(schedule_id, DriftSpec())

            # Dispatch drift check. Any exception here is logged as a
            # run outcome but does not abort subsequent schedules in
            # this poll batch.
            outcome = "success"
            drift_detected: bool | None = None
            try:
                current_data = await data_fn()
                report = await self.check_drift(model_name, current_data)
                drift_detected = report.overall_drift_detected
                if report.overall_drift_detected and spec.on_drift_detected is not None:
                    await spec.on_drift_detected(report)
            except Exception:  # noqa: BLE001 — record + continue
                outcome = "failed"
                logger.exception(
                    "drift.scheduler.dispatch_failed",
                    extra={
                        "drift_tenant_id": self._tenant_id,
                        "drift_schedule_id": schedule_id,
                        "drift_model_name": model_name,
                    },
                )

            await self._conn.execute(
                "UPDATE _kml_drift_schedules "
                "SET last_run_at = ?, last_run_outcome = ?, "
                "    last_run_drift_detected = ?, updated_at = ? "
                "WHERE schedule_id = ? AND tenant_id = ?",
                now_iso,
                outcome,
                None if drift_detected is None else (1 if drift_detected else 0),
                datetime.now(timezone.utc).isoformat(),
                schedule_id,
                self._tenant_id,
            )

    # ------------------------------------------------------------------
    # Deprecated shims — retained for one milestone so the dashboard +
    # Tier-1 test suite keep working. See spec §5 (retained API surface).
    # ------------------------------------------------------------------

    async def cancel_monitoring(self, model_name: str) -> bool:
        """Deprecated — prefer :meth:`cancel_schedule` keyed by schedule_id.

        Cancels every persisted schedule for ``model_name`` (soft-disable
        via ``cancel_schedule``) AND drops any in-process task the legacy
        dispatch path may have spawned. Returns ``True`` if at least one
        schedule was previously enabled OR an in-process task was
        cancelled; ``False`` otherwise.
        """
        cancelled_any = False
        try:
            schedules = await self.list_schedules(
                model_name=model_name, enabled_only=True
            )
        except Exception:  # noqa: BLE001 — tolerate mock-fetch quirks in unit tests
            schedules = []
        for sched in schedules:
            if await self.cancel_schedule(
                sched["schedule_id"], actor_id="system", reason="cancel_monitoring shim"
            ):
                cancelled_any = True

        task = self._scheduled_tasks.pop(model_name, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            cancelled_any = True
        return cancelled_any

    async def shutdown(self) -> None:
        """Deprecated — prefer :meth:`stop_scheduler`.

        Stops the scheduler worker AND cancels every in-process task
        left by the legacy dispatch path.
        """
        await self.stop_scheduler()

    @property
    def active_schedules(self) -> list[str]:
        """Deprecated — returns legacy in-process task model-names only.

        For persistent schedules prefer :meth:`list_schedules`. Retained
        so existing consumers (dashboard/server.py `overview` endpoint)
        keep compiling; the overview will show 0 in-process tasks now
        that the dispatch path is DB-backed.
        """
        return [name for name, task in self._scheduled_tasks.items() if not task.done()]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _emit_feature_metrics(
        self,
        *,
        feature_name: str,
        psi: float,
        ks_pval: float | None,
        chi2_pval: float | None,
        jsd: float | None,
        new_cat_frac: float | None,
        drift_detected: bool,
    ) -> None:
        """Emit per-feature drift statistics to the configured tracker.

        W26 invariant 4 + spec ``ml-drift.md §6.4``.  Keys use the
        ``drift/{feature}/{statistic}`` shape the todo fixes; when
        drift is detected, a sentinel ``drift/{feature}/alert`` value
        of ``1.0`` lands so dashboards can filter alerts without a
        separate tag system.
        """
        if self._tracker is None:
            return

        def _emit(key: str, value: float | None) -> None:
            if value is None:
                return
            try:
                self._tracker.log_metric(key, float(value))
            except Exception as exc:  # noqa: BLE001 — tracker backends vary
                # Best-effort emission; the in-memory report is the
                # source of truth.  DEBUG because tracker outages are
                # not drift findings.
                logger.debug(
                    "drift.tracker_emit_failed",
                    extra={
                        "drift_tenant_id": self._tenant_id,
                        "drift_feature": feature_name,
                        "drift_metric": key,
                        "error": str(exc),
                    },
                )

        base = f"drift/{feature_name}"
        _emit(f"{base}/psi", psi)
        _emit(f"{base}/ks_pvalue", ks_pval)
        _emit(f"{base}/chi2_pvalue", chi2_pval)
        _emit(f"{base}/jsd", jsd)
        _emit(f"{base}/new_category_fraction", new_cat_frac)
        # Sentinel binary alert flag — matches the todo's "+ tag
        # 'drift_alert'" invariant.  Log aggregators and dashboards
        # query ``drift/*/alert == 1`` to surface drifted features.
        _emit(f"{base}/alert", 1.0 if drift_detected else 0.0)

    async def _store_report(self, report: DriftReport) -> str:
        """Persist a drift report to the database.

        W26.e — rows are tenant-scoped (``self._tenant_id``) so
        ``get_drift_history`` only returns reports for this monitor's
        tenant.

        Returns the generated ``report_id`` so the alert dispatcher
        (W26.d) can link :class:`DriftAlert` payloads back into
        ``_kml_drift_reports`` per spec §6.3.
        """
        report_id = str(uuid.uuid4())
        await self._conn.execute(
            "INSERT INTO _kml_drift_reports "
            "(id, tenant_id, model_name, feature_results, overall_drift, "
            " overall_severity, checked_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            report_id,
            self._tenant_id,
            report.model_name,
            json.dumps([f.to_dict() for f in report.feature_results]),
            1 if report.overall_drift_detected else 0,
            report.overall_severity,
            report.checked_at.isoformat(),
        )
        return report_id

    async def _load_performance_baseline(
        self, model_name: str
    ) -> dict[str, float] | None:
        """Load stored performance baseline (tenant-scoped per W26.e)."""
        row = await self._conn.fetchone(
            "SELECT metrics FROM _kml_performance_baselines "
            "WHERE tenant_id = ? AND model_name = ?",
            self._tenant_id,
            model_name,
        )
        if row is None:
            return None
        return json.loads(row["metrics"])

    async def _store_performance_baseline(
        self, model_name: str, metrics: dict[str, float]
    ) -> None:
        """Store performance baseline (transaction eliminates TOCTOU race).

        W26.e — rows are tenant-scoped via composite (tenant_id, model_name)
        shape so two tenants' baselines for the same model never collide.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self._conn.transaction() as tx:
            existing = await tx.fetchone(
                "SELECT model_name FROM _kml_performance_baselines "
                "WHERE tenant_id = ? AND model_name = ?",
                self._tenant_id,
                model_name,
            )
            if existing:
                await tx.execute(
                    "UPDATE _kml_performance_baselines SET metrics = ?, set_at = ? "
                    "WHERE tenant_id = ? AND model_name = ?",
                    json.dumps(metrics),
                    now_iso,
                    self._tenant_id,
                    model_name,
                )
            else:
                await tx.execute(
                    "INSERT INTO _kml_performance_baselines "
                    "(tenant_id, model_name, metrics, set_at) "
                    "VALUES (?, ?, ?, ?)",
                    self._tenant_id,
                    model_name,
                    json.dumps(metrics),
                    now_iso,
                )
