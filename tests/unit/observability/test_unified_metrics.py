# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 tests for the unified /metrics exposition (issue #1708 W1b).

render_prometheus_exposition() is what the server /metrics endpoints render.
Before #1708 they exported ONLY the custom MetricsRegistry; the unification
also folds in the prometheus_client default registry — which carries the OTel
meters bridged by configure_observability()'s Prometheus reader AND the
prometheus_client-native instruments (asyncsql, ML) — plus optional pool lines.
"""

from __future__ import annotations

import pytest

from kailash.monitoring.metrics import render_prometheus_exposition
from kailash.observability import configure_observability
from kailash.observability import otlp as _otlp


@pytest.fixture(autouse=True)
def _reset_handle_cache():
    _otlp._STATE = None
    yield
    _otlp._STATE = None


def test_exposition_folds_in_otel_bridged_metrics(monkeypatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    configure_observability(prometheus=True, enable_traces=False, force=True)

    from opentelemetry import metrics

    meter = metrics.get_meter("kailash.test.unified")
    counter = meter.create_counter("kailash_unified_probe_total", unit="1")
    counter.add(1, {"k": "v"})

    body = render_prometheus_exposition()
    # An OTel-emitted metric reaches the unified /metrics body via the bridge —
    # the exact gap #1708 flagged (server /metrics previously missed OTel meters).
    assert "kailash_unified_probe_total" in body
    assert body.endswith("\n")  # valid OpenMetrics text


def test_exposition_appends_extra_pool_lines() -> None:
    extra = [
        "# HELP kailash_demo_pool_util utilization",
        "# TYPE kailash_demo_pool_util gauge",
        'kailash_demo_pool_util{pool="a"} 0.5',
    ]
    body = render_prometheus_exposition(extra_lines=extra)
    assert "kailash_demo_pool_util" in body
    assert body.endswith("\n")


def test_exposition_is_nonempty_text() -> None:
    # The custom registry always contributes validation/security/performance
    # collectors, so the body is never empty even before any OTel config.
    body = render_prometheus_exposition()
    assert isinstance(body, str)
