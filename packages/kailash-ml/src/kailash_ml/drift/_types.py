# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared types for ``kailash_ml.drift`` and ``kailash_ml.engines.drift_monitor``.

This module breaks the static import cycle between
:mod:`kailash_ml.engines.drift_monitor` and :mod:`kailash_ml.drift.alerts`.
``alerts.py`` previously imported ``DriftReport`` / ``FeatureDriftResult``
from ``drift_monitor`` under a ``TYPE_CHECKING`` guard, while
``drift_monitor`` imports ``AlertConfig`` / ``DriftAlertDispatcher`` from
``alerts`` at module scope. Both sides now import the dataclasses from
this leaf module.

Per ``rules/orphan-detection.md §6b`` the dataclasses are eagerly defined
here with no behavioral changes — ``drift_monitor`` re-exports them so
``from kailash_ml.engines.drift_monitor import DriftReport`` continues
to resolve for every existing caller.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

__all__ = ["FeatureDriftResult", "DriftReport"]


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
