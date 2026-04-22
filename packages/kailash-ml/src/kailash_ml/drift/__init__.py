# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Drift detection primitives for kailash-ml.

This sub-package hosts the column-type-aware drift statistics and the
``DriftThresholds`` configuration dataclass consumed by
:class:`kailash_ml.engines.drift_monitor.DriftMonitor`.

The pure-stats helpers here have no dependency on the storage layer or
on ``ConnectionManager`` — they operate on ``polars.Series`` pairs and
return floats or ``(statistic, pvalue)`` tuples — so they can be used
standalone in a notebook or bench before plumbing through the engine.

See ``specs/ml-drift.md §3`` for the column-type-aware selection rule
and ``§3.6`` for the pinned smoothing-constant contract.
"""
from __future__ import annotations

from kailash_ml.drift.policy import (
    DriftMonitorReferencePolicy,
    DriftPolicyMode,
)
from kailash_ml.drift.stats import (
    JSD_SMOOTH_EPS,
    KL_SMOOTH_EPS,
    MIN_BIN_COUNT,
    PSI_SMOOTH_EPS,
    DriftThresholds,
    chi2_test,
    jensen_shannon_continuous,
    jensen_shannon_discrete,
    select_statistics,
)

__all__ = [
    "DriftMonitorReferencePolicy",
    "DriftPolicyMode",
    "DriftThresholds",
    "JSD_SMOOTH_EPS",
    "KL_SMOOTH_EPS",
    "MIN_BIN_COUNT",
    "PSI_SMOOTH_EPS",
    "chi2_test",
    "jensen_shannon_continuous",
    "jensen_shannon_discrete",
    "select_statistics",
]
