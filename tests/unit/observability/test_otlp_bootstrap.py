# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 tests for kailash.observability.otlp — the OTLP/Prometheus bootstrap.

Covers (issue #1708):
  - configure_observability installs a Prometheus reader + Resource
    (service.name / service.version) on the global MeterProvider.
  - An OTel instrument recorded after configuration is exported through the
    prometheus_client registry as a real bucketed histogram (aggregatable
    p95/p99), NOT a client-side summary.
  - $OTEL_SERVICE_NAME resolution.
  - Idempotency (a second call returns the cached handle).
  - Graceful no-op when no signal is enabled (configured=False + a reason,
    never a raise) — the rules/zero-tolerance.md "no fake metrics" contract.

The global OTel MeterProvider can only be set once per process (OTel forbids
re-setting), so these tests reset only the module-level handle cache between
cases; the Prometheus reader stays registered once installed, which is exactly
the production lifecycle (configure once at startup).
"""

from __future__ import annotations

import pytest

from kailash.observability import (
    ObservabilityHandle,
    configure_observability,
    get_observability_handle,
)
from kailash.observability import otlp as _otlp


@pytest.fixture(autouse=True)
def _reset_handle_cache():
    _otlp._STATE = None
    yield
    _otlp._STATE = None


def test_symbols_present() -> None:
    from kailash import observability

    for name in (
        "configure_observability",
        "get_observability_handle",
        "shutdown_observability",
        "ObservabilityHandle",
    ):
        assert hasattr(observability, name)


def test_configures_prometheus_with_resource(monkeypatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)

    handle = configure_observability(prometheus=True, enable_traces=False, force=True)

    assert isinstance(handle, ObservabilityHandle)
    assert handle.configured is True
    assert handle.prometheus_enabled is True
    assert handle.service_name == "kailash"
    assert handle.service_version  # non-empty (kailash.__version__)
    assert get_observability_handle() is handle


def test_otel_metric_exports_as_bucketed_histogram(monkeypatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    configure_observability(prometheus=True, enable_traces=False, force=True)

    from opentelemetry import metrics

    meter = metrics.get_meter("kailash.test.otlp")
    counter = meter.create_counter("kailash_test_otlp_events_total", unit="1")
    counter.add(2, {"kind": "unit"})
    hist = meter.create_histogram("kailash_test_otlp_latency_seconds", unit="s")
    hist.record(0.01, {"op": "unit"})

    from prometheus_client import generate_latest

    out = generate_latest().decode()
    assert "kailash_test_otlp_events_total" in out
    # A real, aggregatable histogram exports le-keyed buckets — the enterprise
    # contract's hardest requirement (p95/p99 aggregatable across replicas).
    assert "kailash_test_otlp_latency_seconds_bucket" in out
    assert 'le="+Inf"' in out


def test_env_service_name_resolution(monkeypatch) -> None:
    monkeypatch.setenv("OTEL_SERVICE_NAME", "my-service")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    handle = configure_observability(prometheus=True, enable_traces=False, force=True)
    assert handle.service_name == "my-service"


def test_idempotent_returns_cached_handle() -> None:
    first = configure_observability(prometheus=True, enable_traces=False, force=True)
    second = configure_observability(prometheus=True, enable_traces=False)
    assert second is first


def test_no_signal_is_graceful_noop(monkeypatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    handle = configure_observability(
        prometheus=False,
        enable_metrics=True,
        enable_traces=False,
        enable_logs=False,
        force=True,
    )
    assert handle.configured is False
    assert handle.reason and "no signal" in handle.reason
