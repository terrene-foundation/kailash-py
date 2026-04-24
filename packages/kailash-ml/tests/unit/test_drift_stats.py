# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for W26.a drift statistics.

Covers:

  - Pinned smoothing constants (spec §3.6) — module-level, not
    re-derived per call.
  - :func:`chi2_test` detects categorical drift and returns
    ``(statistic, pvalue)``.
  - :func:`jensen_shannon_continuous` detects continuous drift,
    returns ``0`` for identical distributions, raises
    :class:`ZeroVarianceReferenceError` on zero-variance reference.
  - :func:`jensen_shannon_discrete` detects categorical drift with
    disjoint category sets.
  - :func:`select_statistics` auto-selects per column dtype per
    spec §3.3.
  - :class:`DriftThresholds` validates inputs and applies per-column
    overrides.
"""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from kailash_ml.drift import (
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
from kailash_ml.drift.stats import new_category_fraction
from kailash_ml.errors import DriftThresholdError, ZeroVarianceReferenceError


# ---------------------------------------------------------------------------
# Pinned smoothing constants — spec §3.6 cross-SDK parity
# ---------------------------------------------------------------------------


def test_smoothing_constants_match_spec() -> None:
    """PSI / JSD / KL / MIN_BIN_COUNT constants match ``specs/ml-drift.md §3.6``."""
    assert PSI_SMOOTH_EPS == 1e-4
    assert JSD_SMOOTH_EPS == 1e-10
    assert KL_SMOOTH_EPS == 1e-10
    assert MIN_BIN_COUNT == 10


# ---------------------------------------------------------------------------
# chi² contingency test
# ---------------------------------------------------------------------------


def test_chi2_detects_categorical_drift() -> None:
    ref = pl.Series("c", ["a"] * 100 + ["b"] * 100)
    cur = pl.Series("c", ["a"] * 10 + ["b"] * 190)
    stat, pval = chi2_test(ref, cur)
    assert stat > 0
    assert pval < 0.05


def test_chi2_no_drift_identical_distributions() -> None:
    """Identical ref + cur → pvalue ≈ 1 (no drift)."""
    ref = pl.Series("c", ["a"] * 100 + ["b"] * 100)
    cur = pl.Series("c", ["a"] * 100 + ["b"] * 100)
    _, pval = chi2_test(ref, cur)
    assert pval > 0.9


def test_chi2_returns_sentinel_on_empty() -> None:
    ref = pl.Series("c", [], dtype=pl.Utf8)
    cur = pl.Series("c", ["a", "b"])
    assert chi2_test(ref, cur) == (0.0, 1.0)


def test_chi2_returns_sentinel_on_single_shared_category() -> None:
    ref = pl.Series("c", ["a", "a", "a"])
    cur = pl.Series("c", ["a", "a", "a"])
    assert chi2_test(ref, cur) == (0.0, 1.0)


# ---------------------------------------------------------------------------
# Jensen-Shannon divergence
# ---------------------------------------------------------------------------


def test_jsd_continuous_detects_shift() -> None:
    rng = np.random.default_rng(0)
    ref = pl.Series("x", rng.normal(0, 1, 500))
    cur = pl.Series("x", rng.normal(5, 1, 500))  # big shift
    jsd = jensen_shannon_continuous(ref, cur)
    assert jsd > 0.3


def test_jsd_continuous_no_drift() -> None:
    """Two samples from the same distribution → low JSD."""
    rng = np.random.default_rng(0)
    ref = pl.Series("x", rng.normal(0, 1, 1000))
    cur = pl.Series("x", rng.normal(0, 1, 1000))
    jsd = jensen_shannon_continuous(ref, cur)
    assert jsd < 0.05


def test_jsd_continuous_raises_on_zero_variance_reference() -> None:
    """Spec §3.6 MUST 2: zero-variance reference → typed error."""
    ref = pl.Series("x", [3.14] * 100)
    cur = pl.Series("x", [1.0, 2.0, 3.0])
    with pytest.raises(ZeroVarianceReferenceError, match="zero variance"):
        jensen_shannon_continuous(ref, cur)


def test_jsd_continuous_empty_returns_zero() -> None:
    ref = pl.Series("x", [], dtype=pl.Float64)
    cur = pl.Series("x", [1.0, 2.0])
    assert jensen_shannon_continuous(ref, cur) == 0.0


def test_jsd_discrete_detects_disjoint_categories() -> None:
    """Disjoint category sets → JSD approaches ln(2) ≈ 0.693."""
    ref = pl.Series("c", ["a"] * 50 + ["b"] * 50)
    cur = pl.Series("c", ["x"] * 100)
    jsd = jensen_shannon_discrete(ref, cur)
    assert jsd > 0.5


def test_jsd_discrete_no_drift_identical() -> None:
    ref = pl.Series("c", ["a"] * 100 + ["b"] * 100)
    cur = pl.Series("c", ["a"] * 100 + ["b"] * 100)
    assert jensen_shannon_discrete(ref, cur) < 0.01


# ---------------------------------------------------------------------------
# Column-type auto-selection — spec §3.3
# ---------------------------------------------------------------------------


def test_select_statistics_float_is_continuous() -> None:
    assert select_statistics(pl.Series("x", [1.0, 2.0, 3.0])) == frozenset(
        {"ks", "psi", "jsd"}
    )


def test_select_statistics_string_is_categorical() -> None:
    assert select_statistics(pl.Series("x", ["a", "b"])) == frozenset(
        {"chi2", "jsd", "new_category"}
    )


def test_select_statistics_boolean_is_chi2_only() -> None:
    assert select_statistics(pl.Series("x", [True, False, True])) == frozenset({"chi2"})


def test_select_statistics_int_low_cardinality_is_categorical() -> None:
    # 100 rows, 3 unique values → ratio 0.03 < 0.05 threshold.
    values = [0, 1, 2] * 33 + [0]
    assert select_statistics(pl.Series("x", values)) == frozenset(
        {"chi2", "jsd", "new_category"}
    )


def test_select_statistics_int_high_cardinality_is_continuous() -> None:
    # 100 unique values → continuous.
    values = list(range(100))
    assert select_statistics(pl.Series("x", values)) == frozenset({"ks", "psi", "jsd"})


def test_select_statistics_unknown_dtype_returns_empty() -> None:
    """List / Struct / Object dtypes → empty set (caller skips with WARN)."""
    assert select_statistics(pl.Series("x", [[1], [2]])) == frozenset()


# ---------------------------------------------------------------------------
# new_category_fraction
# ---------------------------------------------------------------------------


def test_new_category_fraction_all_new() -> None:
    ref = pl.Series("c", ["a", "b"])
    cur = pl.Series("c", ["x", "y", "z"])
    assert new_category_fraction(ref, cur) == 1.0


def test_new_category_fraction_none_new() -> None:
    ref = pl.Series("c", ["a", "b"])
    cur = pl.Series("c", ["a", "a", "b"])
    assert new_category_fraction(ref, cur) == 0.0


def test_new_category_fraction_mixed() -> None:
    ref = pl.Series("c", ["a"])
    cur = pl.Series("c", ["a", "a", "x", "y"])  # 2/4 new
    assert new_category_fraction(ref, cur) == 0.5


def test_new_category_fraction_empty_current() -> None:
    assert (
        new_category_fraction(pl.Series("c", ["a"]), pl.Series("c", [], dtype=pl.Utf8))
        is None
    )


# ---------------------------------------------------------------------------
# DriftThresholds
# ---------------------------------------------------------------------------


def test_drift_thresholds_defaults_match_spec() -> None:
    t = DriftThresholds()
    assert t.psi == 0.2
    assert t.ks_pvalue == 0.05
    assert t.chi2_pvalue == 0.05
    assert t.jsd == 0.1
    assert t.new_category_fraction == 0.05


def test_drift_thresholds_rejects_nan() -> None:
    with pytest.raises(DriftThresholdError, match="finite"):
        DriftThresholds(psi=float("nan"))


def test_drift_thresholds_rejects_negative() -> None:
    with pytest.raises(DriftThresholdError, match="non-negative"):
        DriftThresholds(jsd=-0.1)


def test_drift_thresholds_rejects_out_of_range_pvalue() -> None:
    with pytest.raises(DriftThresholdError, match=r"\[0, 1\]"):
        DriftThresholds(ks_pvalue=1.5)


def test_drift_thresholds_rejects_unknown_override_key() -> None:
    with pytest.raises(DriftThresholdError, match="unknown key"):
        DriftThresholds(column_overrides={"age": {"psi_bad": 0.1}})


def test_drift_thresholds_resolve_merges_overrides() -> None:
    t = DriftThresholds(
        psi=0.2,
        column_overrides={"age": {"ks_pvalue": 0.01, "psi": 0.3}},
    )
    age = t.resolve("age")
    assert age["ks_pvalue"] == 0.01
    assert age["psi"] == 0.3
    # Other columns fall back to defaults.
    assert t.resolve("country")["ks_pvalue"] == 0.05
    assert t.resolve("country")["psi"] == 0.2
