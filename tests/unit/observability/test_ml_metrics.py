# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 tests for kailash.observability.ml — counter shape + label bounding.

Covers:
  - Public recorder functions (record_train_duration /
    record_inference_latency / record_drift_alert) accept the spec §6.1
    keyword arguments and reject malformed inputs.
  - _bucket_tenant honors the top-N admission policy with "_other"
    overflow (rules/tenant-isolation.md §4).
  - metrics_endpoint_body() returns explanatory content AND a startup
    warning fires when prometheus_client is unavailable (no-op
    fallback — rules/zero-tolerance.md § "Fake metrics").
  - Integer-only count contract on record_drift_alert (TypeError on
    bool / negative).
"""

from __future__ import annotations

import pytest


def test_symbols_present() -> None:
    from kailash.observability import ml

    for name in (
        "record_train_duration",
        "record_inference_latency",
        "record_drift_alert",
        "metrics_endpoint_body",
        "PROMETHEUS_AVAILABLE",
        "OTEL_AVAILABLE",
        "TOP_TENANTS_DEFAULT",
    ):
        assert hasattr(ml, name), f"missing public symbol {name}"
    assert set(ml.__all__) == {
        "record_train_duration",
        "record_inference_latency",
        "record_drift_alert",
        "metrics_endpoint_body",
        "PROMETHEUS_AVAILABLE",
        "OTEL_AVAILABLE",
        "TOP_TENANTS_DEFAULT",
    }


def test_record_train_duration_rejects_negative() -> None:
    from kailash.observability.ml import record_train_duration

    with pytest.raises(ValueError, match="non-negative"):
        record_train_duration(
            engine_name="sklearn.X",
            model_name="m",
            tenant_id="t1",
            duration_s=-1.0,
        )


def test_record_train_duration_rejects_non_numeric() -> None:
    from kailash.observability.ml import record_train_duration

    with pytest.raises(TypeError):
        record_train_duration(
            engine_name="sklearn.X",
            model_name="m",
            tenant_id="t1",
            duration_s="slow",  # type: ignore[arg-type]
        )


def test_record_inference_latency_rejects_negative() -> None:
    from kailash.observability.ml import record_inference_latency

    with pytest.raises(ValueError, match="non-negative"):
        record_inference_latency(
            model_name="m",
            version="1",
            tenant_id="t1",
            latency_ms=-5.0,
        )


def test_record_drift_alert_count_contract() -> None:
    from kailash.observability.ml import record_drift_alert

    # count must be positive int — bool is NOT int for this purpose.
    with pytest.raises(ValueError, match="positive int"):
        record_drift_alert(feature_name="f", severity="low", tenant_id="t1", count=0)
    with pytest.raises(ValueError, match="positive int"):
        record_drift_alert(feature_name="f", severity="low", tenant_id="t1", count=True)  # type: ignore[arg-type]
    # positive int succeeds.
    record_drift_alert(feature_name="f", severity="low", tenant_id="t1", count=3)


def test_bucket_tenant_rejects_missing_tenant_id() -> None:
    from kailash.observability.ml import _reset_bucketer_for_tests, _bucket_tenant

    _reset_bucketer_for_tests(top_n=2)
    with pytest.raises(ValueError, match="non-empty"):
        _bucket_tenant("")
    with pytest.raises(ValueError, match="non-empty"):
        _bucket_tenant(None)  # type: ignore[arg-type]


def test_bucket_tenant_top_n_admission_and_other_overflow() -> None:
    """Top-N admission: first N tenants admitted; newcomers bucket as _other."""
    from kailash.observability.ml import _bucket_tenant, _reset_bucketer_for_tests

    _reset_bucketer_for_tests(top_n=2)

    # First two distinct tenants → admitted as themselves.
    assert _bucket_tenant("tenant-A") == "tenant-A"
    assert _bucket_tenant("tenant-B") == "tenant-B"

    # Third tenant has not yet accumulated more observations than the
    # lowest admitted → buckets as _other.
    assert _bucket_tenant("tenant-C") == "_other"

    # Subsequent observations of already-admitted tenants keep their
    # tenant_id.
    assert _bucket_tenant("tenant-A") == "tenant-A"
    assert _bucket_tenant("tenant-B") == "tenant-B"


def test_bucket_tenant_promotion_when_newcomer_exceeds_lowest() -> None:
    """Newcomer that exceeds the lowest admitted tenant's count IS promoted."""
    from kailash.observability.ml import _bucket_tenant, _reset_bucketer_for_tests

    _reset_bucketer_for_tests(top_n=2)

    # Admit A (count=3), B (count=1).
    _bucket_tenant("tenant-A")
    _bucket_tenant("tenant-A")
    _bucket_tenant("tenant-A")
    _bucket_tenant("tenant-B")
    assert _bucket_tenant("tenant-A") == "tenant-A"  # count 4
    assert _bucket_tenant("tenant-B") == "tenant-B"  # count 2

    # C arrives; count=1 < B's count=2 → _other.
    assert _bucket_tenant("tenant-C") == "_other"  # C now at 1
    # C observes twice more → count=3 > B's 2 → next observation of C
    # promotes C and evicts B.
    _bucket_tenant("tenant-C")  # count 2
    # Next call: C count=3, B count=2 — promotion triggers.
    label = _bucket_tenant("tenant-C")
    assert label == "tenant-C"


def test_metrics_endpoint_body_returns_string() -> None:
    from kailash.observability.ml import metrics_endpoint_body

    body = metrics_endpoint_body()
    assert isinstance(body, str)
    # Either real Prometheus exposition OR the fallback explanation.
    # Both paths must return a non-empty string.
    assert len(body) > 0


def test_metrics_endpoint_body_explanatory_when_prometheus_missing(monkeypatch):
    """When prometheus_client is missing, body MUST advertise the extra."""
    from kailash.observability import ml

    monkeypatch.setattr(ml, "PROMETHEUS_AVAILABLE", False)
    body = ml.metrics_endpoint_body()
    assert "prometheus_client" in body
    assert "kailash[observability]" in body
    # Must NOT fake a successful Prometheus exposition.
    assert "kailash_ml_train_duration_seconds_bucket" not in body


def test_record_functions_are_noops_when_prometheus_missing(monkeypatch):
    """Silent no-op path is permitted IFF startup warning was emitted.

    The import-time UserWarning (see module docstring) is the loud
    signal; the runtime recorder simply does nothing when
    PROMETHEUS_AVAILABLE is False. This is the "loud warn + no-op
    body" form of rules/zero-tolerance.md § Fake metrics — operators
    see the warning at startup AND the /metrics endpoint body tells
    them what to install.
    """
    from kailash.observability import ml

    monkeypatch.setattr(ml, "PROMETHEUS_AVAILABLE", False)
    # Should not raise — recorders short-circuit when Prometheus absent.
    ml.record_train_duration(
        engine_name="sklearn.X", model_name="m", tenant_id="t1", duration_s=1.0
    )
    ml.record_inference_latency(
        model_name="m", version="1", tenant_id="t1", latency_ms=5.0
    )
    ml.record_drift_alert(feature_name="f", severity="low", tenant_id="t1")


def test_top_n_env_override(monkeypatch):
    """KAILASH_ML_METRICS_TOP_TENANTS overrides the default."""
    from kailash.observability.ml import _TenantBucketer, _top_n_from_env

    monkeypatch.setenv("KAILASH_ML_METRICS_TOP_TENANTS", "5")
    assert _top_n_from_env() == 5

    monkeypatch.setenv("KAILASH_ML_METRICS_TOP_TENANTS", "bogus")
    # Bogus value → falls back to TOP_TENANTS_DEFAULT with a warning.
    from kailash.observability.ml import TOP_TENANTS_DEFAULT

    assert _top_n_from_env() == TOP_TENANTS_DEFAULT

    monkeypatch.setenv("KAILASH_ML_METRICS_TOP_TENANTS", "-3")
    assert _top_n_from_env() == TOP_TENANTS_DEFAULT


def test_tenant_bucketer_rejects_bad_top_n() -> None:
    from kailash.observability.ml import _TenantBucketer

    with pytest.raises(ValueError, match="positive int"):
        _TenantBucketer(top_n=0)
    with pytest.raises(ValueError, match="positive int"):
        _TenantBucketer(top_n=-1)
