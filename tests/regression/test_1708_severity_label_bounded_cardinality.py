# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test: ``severity`` on ``kailash_ml_drift_alerts_total`` MUST be
a bounded metric-label dimension (#1708 M1).

Before this fix, ``record_drift_alert`` landed the caller-supplied
``severity`` string raw onto the Prometheus/OTel label — every other
non-tenant label (``engine_name`` / ``model_name`` / ``version`` /
``feature_name``) went through a top-N bucketer, but ``severity`` did not.
The module's own header comment asserted "severity stays raw (bounded enum
vocabulary)" while ``record_drift_alert``'s docstring simultaneously said
"the observability layer does not enforce the vocabulary" — a
self-contradiction that hid the real bug: a misbehaving or adversarial
drift monitor emitting free-form severity strings could grow the
``severity`` label dimension without bound (a Prometheus cardinality bomb).

The fix (``_normalize_severity`` in
``src/kailash/observability/ml/__init__.py``) whitelist-validates
``severity`` against the fixed enum ``{"low", "medium", "high", "critical"}``
(case-insensitive), and collapses any out-of-vocabulary value — including
non-str input — to the ``"unknown"`` sentinel BEFORE it reaches the metric
label. This test proves, against the REAL ``prometheus_client`` registry
(no mocking, Tier 2 per ``rules/testing.md`` § 3-Tier Testing):

  (a) a valid (and case-varied) severity passes through, normalized, as its
      own label value;
  (b) N distinct junk/free-form severities collapse onto exactly ONE bounded
      series (the ``"unknown"`` sentinel), not N distinct series.

@pytest.mark.regression per rules/testing.md § "Regression Testing".
"""

from __future__ import annotations

import uuid
from typing import Dict, List

import pytest

pytest.importorskip("prometheus_client", reason="requires kailash[observability]")


def _drift_alert_series(feature_name: str, tenant_bucket: str) -> Dict[str, float]:
    """Scrape the real Prometheus REGISTRY for every ``severity`` label
    value currently recorded for ``kailash_ml_drift_alerts_total`` under
    the given ``feature_name`` + ``tenant_id_bucket``.

    Returns {severity_label_value: counter_value}. This is a live registry
    read — no mocking — so it proves what actually landed as a label, not
    what the code merely intended to record.
    """
    from prometheus_client import REGISTRY

    result: Dict[str, float] = {}
    for metric in REGISTRY.collect():
        if metric.name != "kailash_ml_drift_alerts":
            continue
        for sample in metric.samples:
            if not sample.name.endswith("_total"):
                continue
            if sample.labels.get("feature_name") != feature_name:
                continue
            if sample.labels.get("tenant_id_bucket") != tenant_bucket:
                continue
            result[sample.labels["severity"]] = sample.value
    return result


@pytest.fixture(autouse=True)
def _reset_bucketer():
    """Reset the top-N bucketers between tests (sibling non-tenant label
    dimensions share module-global state with the severity fix under
    test)."""
    from kailash.observability.ml import _reset_bucketer_for_tests

    _reset_bucketer_for_tests()
    yield
    _reset_bucketer_for_tests()


@pytest.mark.regression
class TestSeverityLabelBoundedCardinality:
    """severity MUST be whitelist-validated + case-normalized before it
    lands as a kailash_ml_drift_alerts_total label — never raw."""

    def test_valid_severity_passes_through_normalized(self):
        """A valid, enum-vocabulary severity is recorded under its own
        (lowercased) label value — the enforcement does not corrupt the
        happy path."""
        from kailash.observability.ml import record_drift_alert

        feature = f"feature-valid-{uuid.uuid4().hex[:8]}"
        tenant_bucket = f"tenant-valid-{uuid.uuid4().hex[:8]}"

        # Case-varied input ("HIGH") MUST normalize to "high", not pass
        # through verbatim and not collapse to the "unknown" sentinel.
        record_drift_alert(
            feature_name=feature,
            severity="HIGH",
            tenant_id=tenant_bucket,
            count=3,
        )

        series = _drift_alert_series(feature, tenant_bucket)
        assert series == {"high": 3.0}, (
            f"Expected exactly one series labeled severity='high' with "
            f"value 3.0, got: {series}"
        )

    def test_all_four_vocabulary_members_pass_through_distinctly(self):
        """Each of the 4 enum members records as its own distinct series —
        the whitelist does not over-collapse legitimate values."""
        from kailash.observability.ml import record_drift_alert

        feature = f"feature-vocab-{uuid.uuid4().hex[:8]}"
        tenant_bucket = f"tenant-vocab-{uuid.uuid4().hex[:8]}"

        for sev in ("low", "medium", "high", "critical"):
            record_drift_alert(
                feature_name=feature,
                severity=sev,
                tenant_id=tenant_bucket,
                count=1,
            )

        series = _drift_alert_series(feature, tenant_bucket)
        assert series == {"low": 1.0, "medium": 1.0, "high": 1.0, "critical": 1.0}

    def test_free_form_junk_severities_collapse_to_one_bounded_series(self):
        """N distinct free-form/adversarial severity strings MUST collapse
        onto exactly ONE series (the 'unknown' sentinel) — proving the
        label dimension is bounded, not N-unbounded."""
        from kailash.observability.ml import record_drift_alert

        feature = f"feature-junk-{uuid.uuid4().hex[:8]}"
        tenant_bucket = f"tenant-junk-{uuid.uuid4().hex[:8]}"

        junk_severities: List[str] = [
            f"free-form-severity-{i}-{uuid.uuid4().hex[:12]}" for i in range(25)
        ]
        for junk in junk_severities:
            record_drift_alert(
                feature_name=feature,
                severity=junk,
                tenant_id=tenant_bucket,
                count=1,
            )

        series = _drift_alert_series(feature, tenant_bucket)

        # Exactly ONE bounded series, not len(junk_severities) distinct ones.
        assert series == {"unknown": 25.0}, (
            f"Expected 25 junk severities to collapse onto a single "
            f"'unknown' series (value 25.0); got {len(series)} distinct "
            f"series: {series}"
        )

    def test_non_str_severity_fails_closed_to_sentinel(self):
        """Non-str severity input (e.g. an int/None from a misbehaving
        caller) MUST also fail closed to the sentinel, not raise and not
        land as some coerced raw value."""
        from kailash.observability.ml import record_drift_alert

        feature = f"feature-nonstr-{uuid.uuid4().hex[:8]}"
        tenant_bucket = f"tenant-nonstr-{uuid.uuid4().hex[:8]}"

        record_drift_alert(
            feature_name=feature,
            severity=None,  # type: ignore[arg-type]
            tenant_id=tenant_bucket,
            count=1,
        )
        record_drift_alert(
            feature_name=feature,
            severity=12345,  # type: ignore[arg-type]
            tenant_id=tenant_bucket,
            count=1,
        )

        series = _drift_alert_series(feature, tenant_bucket)
        assert series == {"unknown": 2.0}

    def test_normalize_severity_helper_whitelist_and_sentinel(self):
        """Direct unit-level pin of the whitelist + case-normalization +
        fail-closed contract on the helper itself."""
        from kailash.observability.ml import (
            _SEVERITY_SENTINEL,
            _SEVERITY_VOCAB,
            _normalize_severity,
        )

        assert _SEVERITY_VOCAB == frozenset({"low", "medium", "high", "critical"})
        assert _SEVERITY_SENTINEL == "unknown"

        # Case-insensitive matching against the vocabulary.
        assert _normalize_severity("low") == "low"
        assert _normalize_severity("MEDIUM") == "medium"
        assert _normalize_severity("High") == "high"
        assert _normalize_severity("  critical  ") == "critical"

        # Out-of-vocabulary / non-str input fails closed to the sentinel.
        assert _normalize_severity("catastrophic") == _SEVERITY_SENTINEL
        assert _normalize_severity("") == _SEVERITY_SENTINEL
        assert _normalize_severity("info") == _SEVERITY_SENTINEL
        assert _normalize_severity(None) == _SEVERITY_SENTINEL
        assert _normalize_severity(42) == _SEVERITY_SENTINEL
        assert _normalize_severity(["high"]) == _SEVERITY_SENTINEL
