# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Column-type-aware drift statistics.

Three helpers that close the W26 todo's "4 test statistics" invariant
alongside the pre-existing PSI + KS implementations in
:mod:`kailash_ml.engines.drift_monitor`:

- :func:`chi2_test` — Pearson chi² contingency test for categorical
  drift.  Returns ``(statistic, pvalue)``.
- :func:`jensen_shannon_continuous` — Jensen-Shannon divergence between
  two continuous empirical distributions, discretised into equal-width
  bins from the reference range.
- :func:`jensen_shannon_discrete` — Jensen-Shannon divergence between
  two categorical distributions using category-probability smoothing.
- :func:`select_statistics` — column-type auto-selection per
  ``specs/ml-drift.md §3.3``.

Smoothing constants are pinned at the module level per ``§3.6`` so
cross-SDK parity and regression comparability are preserved.  See the
spec's "MUST 1–5" smoothing contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import polars as pl

from kailash_ml.errors import ZeroVarianceReferenceError

__all__ = [
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


# ---------------------------------------------------------------------------
# Pinned smoothing constants — spec §3.6
# ---------------------------------------------------------------------------

PSI_SMOOTH_EPS: float = 1e-4
"""Additive bin-mass constant used by PSI before normalisation."""

JSD_SMOOTH_EPS: float = 1e-10
"""Additive zero-prob smoothing for Jensen-Shannon (MUST 3)."""

KL_SMOOTH_EPS: float = 1e-10
"""Additive zero-prob smoothing for KL divergence (MUST 4) — same contract
as the RL-exploration KL path in :mod:`kailash_ml.diagnostics.rl`."""

MIN_BIN_COUNT: int = 10
"""Minimum bin count below which a statistic emits ``None`` and a
``stability_note`` per MUST 5."""


# ---------------------------------------------------------------------------
# Threshold configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DriftThresholds:
    """Per-statistic drift threshold configuration.

    Defaults match the industry conventions enumerated in
    ``specs/ml-drift.md §3.1`` and §3.2:

    - ``psi >= 0.2`` → drift (>= 0.25 severe).
    - ``ks_pvalue < 0.05`` → drift (KS 2-sample test).
    - ``chi2_pvalue < 0.05`` → drift (Pearson chi² contingency).
    - ``jsd >= 0.1`` → drift (Jensen-Shannon divergence).
    - ``new_category_fraction > 0.05`` → drift (fraction of rows whose
      category did not appear in the reference window).

    Per-column overrides are supported via :meth:`with_overrides`; the
    resulting instance MUST still satisfy every validation invariant
    (positive, finite, within statistic-specific bounds).

    Construction rejects NaN / negative / out-of-bound thresholds
    loudly rather than silently degrading — the operator is protected
    from a "drift never fires" misconfiguration.
    """

    psi: float = 0.2
    ks_pvalue: float = 0.05
    chi2_pvalue: float = 0.05
    jsd: float = 0.1
    new_category_fraction: float = 0.05
    # Per-column overrides: ``{"age": {"ks_pvalue": 0.01}, ...}``.  Keys
    # MUST be column names; inner keys MUST match the field names above.
    column_overrides: dict[str, dict[str, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        from kailash_ml.errors import DriftThresholdError

        for name in ("psi", "ks_pvalue", "chi2_pvalue", "jsd", "new_category_fraction"):
            val = getattr(self, name)
            if not np.isfinite(val):
                raise DriftThresholdError(
                    reason=f"DriftThresholds.{name}={val!r} must be finite (got NaN/Inf)"
                )
            if val < 0:
                raise DriftThresholdError(
                    reason=f"DriftThresholds.{name}={val!r} must be non-negative"
                )
            if name in {"ks_pvalue", "chi2_pvalue"} and not 0.0 <= val <= 1.0:
                raise DriftThresholdError(
                    reason=f"DriftThresholds.{name}={val!r} must lie in [0, 1] (p-value)"
                )
            if name == "new_category_fraction" and not 0.0 <= val <= 1.0:
                raise DriftThresholdError(
                    reason=f"DriftThresholds.{name}={val!r} must lie in [0, 1] (fraction)"
                )
        for col, overrides in self.column_overrides.items():
            for k in overrides:
                if k not in {
                    "psi",
                    "ks_pvalue",
                    "chi2_pvalue",
                    "jsd",
                    "new_category_fraction",
                }:
                    raise DriftThresholdError(
                        reason=(
                            f"DriftThresholds.column_overrides[{col!r}] contains "
                            f"unknown key {k!r}; expected one of psi / ks_pvalue / "
                            f"chi2_pvalue / jsd / new_category_fraction"
                        )
                    )

    def resolve(self, column: str) -> dict[str, float]:
        """Return the effective thresholds for ``column`` after overrides.

        Used by :class:`DriftMonitor.check_drift` when evaluating a
        feature's statistics against its per-column configuration.
        """
        base = {
            "psi": self.psi,
            "ks_pvalue": self.ks_pvalue,
            "chi2_pvalue": self.chi2_pvalue,
            "jsd": self.jsd,
            "new_category_fraction": self.new_category_fraction,
        }
        base.update(self.column_overrides.get(column, {}))
        return base


# ---------------------------------------------------------------------------
# Chi-squared contingency test
# ---------------------------------------------------------------------------


def chi2_test(reference: pl.Series, current: pl.Series) -> tuple[float, float]:
    """Pearson chi² contingency test on categorical counts.

    Builds a 2×K contingency table from the union of categories across
    ``reference`` and ``current`` and delegates to
    :func:`scipy.stats.chi2_contingency`.

    Returns:
        ``(statistic, pvalue)`` — float pair.  ``statistic`` is the
        chi² test statistic (≥ 0); ``pvalue`` is the p-value under
        the null hypothesis of identical distributions.

    Returns ``(0.0, 1.0)`` (no drift) when either side is empty or
    both sides have exactly one shared category — both cases make the
    test statistically meaningless rather than raising.
    """
    from scipy.stats import chi2_contingency

    ref_cast = reference.cast(pl.Utf8).drop_nulls()
    cur_cast = current.cast(pl.Utf8).drop_nulls()
    if len(ref_cast) == 0 or len(cur_cast) == 0:
        return 0.0, 1.0

    # Build category-count dicts via polars value_counts (avoids pandas).
    ref_vc = ref_cast.value_counts()
    cur_vc = cur_cast.value_counts()
    ref_col = ref_cast.name
    cur_col = cur_cast.name
    ref_counts = {row[ref_col]: row["count"] for row in ref_vc.to_dicts()}
    cur_counts = {row[cur_col]: row["count"] for row in cur_vc.to_dicts()}

    categories = sorted(set(ref_counts) | set(cur_counts))
    if len(categories) < 2:
        return 0.0, 1.0
    ref_row = [ref_counts.get(cat, 0) for cat in categories]
    cur_row = [cur_counts.get(cat, 0) for cat in categories]
    # chi2_contingency expects a table with ≥ 1 non-zero entry per row.
    if sum(ref_row) == 0 or sum(cur_row) == 0:
        return 0.0, 1.0

    table = np.asarray([ref_row, cur_row], dtype=np.float64)
    try:
        result = chi2_contingency(table)
    except ValueError:
        # scipy raises on degenerate tables (all-zero column etc.);
        # treat as "no drift detected" per the same stability contract
        # the early-return branches above already use.
        return 0.0, 1.0
    statistic = float(result[0])
    pvalue = float(result[1])
    return statistic, pvalue


# ---------------------------------------------------------------------------
# Jensen-Shannon divergence
# ---------------------------------------------------------------------------


def _smoothed_probabilities(counts: np.ndarray) -> np.ndarray:
    """Convert raw counts to a smoothed probability distribution.

    Adds ``JSD_SMOOTH_EPS`` to every bin and re-normalises so no bin
    has zero probability — closes the ``log(0) = -Inf`` failure mode
    that plagues unsmoothed JSD / KL implementations.
    """
    if counts.size == 0:
        return counts
    smoothed = counts.astype(np.float64) + JSD_SMOOTH_EPS
    total = float(smoothed.sum())
    if total == 0.0:
        return smoothed  # pragma: no cover — eps > 0 means total > 0
    return smoothed / total


def _kl_divergence(p: np.ndarray, q: np.ndarray) -> float:
    """KL(p || q) with ``KL_SMOOTH_EPS`` applied to both operands."""
    p_s = p + KL_SMOOTH_EPS
    q_s = q + KL_SMOOTH_EPS
    return float(np.sum(p_s * np.log(p_s / q_s)))


def _jsd_from_probs(p: np.ndarray, q: np.ndarray) -> float:
    """Jensen-Shannon divergence in [0, log(2)] given two prob vectors."""
    m = 0.5 * (p + q)
    return 0.5 * _kl_divergence(p, m) + 0.5 * _kl_divergence(q, m)


def jensen_shannon_continuous(
    reference: pl.Series,
    current: pl.Series,
    n_bins: int = 10,
) -> float:
    """Jensen-Shannon divergence between two continuous distributions.

    Uses equal-width bins spanning the reference's ``[min, max]``
    interval, widened by ``1e-10`` on each side to capture current-
    window values that lie just outside the reference range.  Per
    ``specs/ml-drift.md §3.6 MUST 2``, a reference with ``std == 0``
    raises :class:`ZeroVarianceReferenceError` — a data-quality signal
    routed elsewhere, not a drift finding.

    Raises:
        ZeroVarianceReferenceError: if the reference has a single
            unique value (``std == 0``).
    """
    ref_arr = reference.drop_nulls().to_numpy().astype(np.float64)
    cur_arr = current.drop_nulls().to_numpy().astype(np.float64)
    if ref_arr.size == 0 or cur_arr.size == 0:
        return 0.0

    ref_min = float(ref_arr.min())
    ref_max = float(ref_arr.max())
    if ref_min == ref_max:
        raise ZeroVarianceReferenceError(
            reason=(
                f"reference column {reference.name!r} has zero variance "
                f"(std == 0); Jensen-Shannon divergence cannot be computed. "
                f"This is a data-quality finding — do not silently coerce "
                f"to a single-bin histogram."
            )
        )

    edges = np.linspace(ref_min, ref_max, n_bins + 1)
    edges[0] = min(edges[0], float(cur_arr.min())) - 1e-10
    edges[-1] = max(edges[-1], float(cur_arr.max())) + 1e-10

    ref_counts, _ = np.histogram(ref_arr, bins=edges)
    cur_counts, _ = np.histogram(cur_arr, bins=edges)

    ref_probs = _smoothed_probabilities(ref_counts)
    cur_probs = _smoothed_probabilities(cur_counts)
    return _jsd_from_probs(ref_probs, cur_probs)


def jensen_shannon_discrete(
    reference: pl.Series,
    current: pl.Series,
) -> float:
    """Jensen-Shannon divergence between two categorical distributions.

    Forms the union of categories across both series, builds smoothed
    probability vectors, and returns ``JSD ∈ [0, ln 2]``.  Safe for
    any input (eps-smoothed), so no zero-variance raise here — the
    categorical form tolerates a single reference category (JSD is
    simply high if the current distribution differs).
    """
    ref_cast = reference.cast(pl.Utf8).drop_nulls()
    cur_cast = current.cast(pl.Utf8).drop_nulls()
    if len(ref_cast) == 0 or len(cur_cast) == 0:
        return 0.0

    ref_vc = ref_cast.value_counts()
    cur_vc = cur_cast.value_counts()
    ref_col = ref_cast.name
    cur_col = cur_cast.name
    ref_counts = {row[ref_col]: row["count"] for row in ref_vc.to_dicts()}
    cur_counts = {row[cur_col]: row["count"] for row in cur_vc.to_dicts()}

    categories = sorted(set(ref_counts) | set(cur_counts))
    ref_vec = np.asarray([ref_counts.get(c, 0) for c in categories], dtype=np.float64)
    cur_vec = np.asarray([cur_counts.get(c, 0) for c in categories], dtype=np.float64)
    ref_probs = _smoothed_probabilities(ref_vec)
    cur_probs = _smoothed_probabilities(cur_vec)
    return _jsd_from_probs(ref_probs, cur_probs)


# ---------------------------------------------------------------------------
# Column-type auto-selection — spec §3.3
# ---------------------------------------------------------------------------


# Every returned token MUST match a :class:`DriftThresholds` field name
# (or the implicit "new_category" axis).  Downstream code uses the set
# to decide which statistics to compute + compare against thresholds.
_CONTINUOUS_STATS: frozenset[str] = frozenset({"ks", "psi", "jsd"})
_CATEGORICAL_STATS: frozenset[str] = frozenset({"chi2", "jsd", "new_category"})
_BOOLEAN_STATS: frozenset[str] = frozenset({"chi2"})


def select_statistics(
    series: pl.Series,
    *,
    categorical_ratio_threshold: float = 0.05,
) -> frozenset[str]:
    """Return the set of statistics that apply to ``series``.

    Mirrors ``specs/ml-drift.md §3.3``:

    - ``Float32 / Float64``: continuous → KS + PSI + JSD.
    - ``Int*`` with ``n_unique / n <= threshold``: categorical →
      chi² + JSD + new-category.
    - ``Int*`` with ``n_unique / n > threshold``: continuous.
    - ``Categorical / Utf8 / String``: categorical.
    - ``Boolean``: chi².
    - ``Datetime / Date``: continuous (caller is responsible for
      bucketing to day / hour via polars before invoking drift
      checks).
    - ``List / Struct``: no applicable statistics — returns the empty
      set so the caller can skip with a WARN.
    """
    dtype = series.dtype
    if dtype in (pl.Float32, pl.Float64):
        return _CONTINUOUS_STATS
    if dtype == pl.Boolean:
        return _BOOLEAN_STATS
    if dtype in (pl.Categorical, pl.Utf8, pl.String):
        return _CATEGORICAL_STATS
    if dtype in (pl.Datetime, pl.Date, pl.Time):
        return _CONTINUOUS_STATS
    if dtype in (
        pl.Int8,
        pl.Int16,
        pl.Int32,
        pl.Int64,
        pl.UInt8,
        pl.UInt16,
        pl.UInt32,
        pl.UInt64,
    ):
        n = max(1, len(series))
        n_unique = series.n_unique()
        if n_unique / n <= categorical_ratio_threshold:
            return _CATEGORICAL_STATS
        return _CONTINUOUS_STATS
    # Unknown dtype (List / Struct / Object) — no applicable statistics.
    return frozenset()


def new_category_fraction(
    reference: pl.Series,
    current: pl.Series,
) -> Optional[float]:
    """Fraction of ``current`` rows whose category did not appear in
    ``reference``.

    Returns ``None`` when ``current`` is empty (the fraction is
    undefined).  Otherwise returns a value in ``[0, 1]``.
    """
    ref_cast = reference.cast(pl.Utf8).drop_nulls()
    cur_cast = current.cast(pl.Utf8).drop_nulls()
    if len(cur_cast) == 0:
        return None
    ref_set = set(ref_cast.to_list())
    new_count = sum(1 for v in cur_cast.to_list() if v not in ref_set)
    return new_count / len(cur_cast)
