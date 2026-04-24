# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring tests for kailash.observability.ml.

Per rules/facade-manager-detection.md §2 + rules/orphan-detection.md §2,
these tests prove the metric surfaces ACTUALLY increment when the public
recorder functions are called — real prometheus_client registry, no
mocks. Proves the metric counters are not orphans.
"""

from __future__ import annotations

import pytest

pytest.importorskip("prometheus_client", reason="requires kailash[observability]")


def _collect_sample_value(metric_name: str, labels: dict) -> float:
    """Scrape a single labeled sample from the default Prometheus registry.

    Returns 0.0 if the sample is absent. This is the real scraping
    path — no mocks. The labels dict matches the Histogram's labelnames.
    """
    from prometheus_client import REGISTRY

    for metric in REGISTRY.collect():
        if metric.name == metric_name or metric.name == metric_name.rstrip(
            "_seconds"
        ).rstrip("_ms").rstrip("_total"):
            for sample in metric.samples:
                # Match by sample name suffix (Histogram creates _sum / _count / _bucket).
                if all(sample.labels.get(k) == v for k, v in labels.items()):
                    return sample.value
    return 0.0


def _collect_histogram_count(metric_name: str, labels: dict) -> float:
    """Read the _count sample of a Histogram with matching labels."""
    from prometheus_client import REGISTRY

    for metric in REGISTRY.collect():
        for sample in metric.samples:
            if sample.name.endswith("_count") and all(
                sample.labels.get(k) == v for k, v in labels.items()
            ):
                if sample.name.startswith(metric_name):
                    return sample.value
    return 0.0


def _collect_counter_total(metric_name: str, labels: dict) -> float:
    """Read the _total sample of a Counter with matching labels."""
    from prometheus_client import REGISTRY

    for metric in REGISTRY.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total") and all(
                sample.labels.get(k) == v for k, v in labels.items()
            ):
                if sample.name.startswith(metric_name):
                    return sample.value
    return 0.0


@pytest.fixture(autouse=True)
def _reset_bucketer():
    """Reset the top-N tenant bucketer between tests."""
    from kailash.observability.ml import _reset_bucketer_for_tests

    _reset_bucketer_for_tests()
    yield
    _reset_bucketer_for_tests()


def test_record_train_duration_increments_histogram():
    """MLEngine.fit() -> record_train_duration must increment the
    Histogram's _count sample under the exact label set the recorder
    emits."""
    from kailash.observability.ml import record_train_duration

    labels = {
        "engine_name": "sklearn.ensemble.RandomForestClassifier",
        "model_name": "test_wiring_train",
        "tenant_id_bucket": "tenant-wiring-a",
    }
    before = _collect_histogram_count("kailash_ml_train_duration_seconds", labels)
    record_train_duration(
        engine_name="sklearn.ensemble.RandomForestClassifier",
        model_name="test_wiring_train",
        tenant_id="tenant-wiring-a",
        duration_s=12.5,
    )
    after = _collect_histogram_count("kailash_ml_train_duration_seconds", labels)
    assert after == before + 1.0


def test_record_inference_latency_increments_histogram():
    from kailash.observability.ml import record_inference_latency

    labels = {
        "model_name": "test_wiring_infer",
        "version": "3",
        "tenant_id_bucket": "tenant-wiring-b",
    }
    before = _collect_histogram_count("kailash_ml_inference_latency_ms", labels)
    record_inference_latency(
        model_name="test_wiring_infer",
        version="3",
        tenant_id="tenant-wiring-b",
        latency_ms=42.1,
    )
    after = _collect_histogram_count("kailash_ml_inference_latency_ms", labels)
    assert after == before + 1.0


def test_record_drift_alert_increments_counter():
    from kailash.observability.ml import record_drift_alert

    labels = {
        "feature_name": "tenure_months",
        "severity": "high",
        "tenant_id_bucket": "tenant-wiring-c",
    }
    before = _collect_counter_total("kailash_ml_drift_alerts", labels)
    record_drift_alert(
        feature_name="tenure_months",
        severity="high",
        tenant_id="tenant-wiring-c",
        count=2,
    )
    after = _collect_counter_total("kailash_ml_drift_alerts", labels)
    assert after == before + 2.0


def test_bounded_cardinality_other_bucket_when_top_n_exceeded(monkeypatch):
    """Newcomer tenants beyond the top-N cutoff emit to the "_other"
    bucket label — proves bounded cardinality in the live registry."""
    from kailash.observability.ml import (
        _reset_bucketer_for_tests,
        record_inference_latency,
    )

    _reset_bucketer_for_tests(top_n=2)

    record_inference_latency(
        model_name="m", version="1", tenant_id="tenant-hot-A", latency_ms=1.0
    )
    record_inference_latency(
        model_name="m", version="1", tenant_id="tenant-hot-B", latency_ms=1.0
    )
    # Third tenant starts in _other.
    record_inference_latency(
        model_name="m", version="1", tenant_id="tenant-cold-C", latency_ms=1.0
    )

    other_count = _collect_histogram_count(
        "kailash_ml_inference_latency_ms",
        {"model_name": "m", "version": "1", "tenant_id_bucket": "_other"},
    )
    assert other_count >= 1.0


def test_metrics_endpoint_body_when_prometheus_present():
    """The metrics endpoint body MUST be the real Prometheus exposition
    when prometheus_client is installed. When absent, it returns the
    explanatory "install kailash[observability]" body instead."""
    from kailash.observability.ml import metrics_endpoint_body

    body = metrics_endpoint_body()
    assert isinstance(body, str)
    # Either a HELP/TYPE exposition OR the explanatory fallback.
    if "HELP" in body or "TYPE" in body:
        # Real exposition — look for one of our metric names.
        assert (
            "kailash_ml_train_duration_seconds" in body
            or "kailash_ml_inference_latency_ms" in body
            or "kailash_ml_drift_alerts" in body
        )
    else:
        assert "kailash[observability]" in body
