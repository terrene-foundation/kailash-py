"""Regression test: no Prometheus series declared ``# TYPE ... histogram``
may carry a bare ``quantile=`` label with no ``le=`` buckets (#1708 W1c).

Before this fix, ``ConnectionMetricsCollector.export_prometheus()`` declared
its percentile-summary block (metric_sum + metric_count +
metric{quantile="q"}, computed post-hoc from a sliding-window sample deque
with no pre-declared bucket boundaries) as ``# TYPE <name> histogram`` — that
shape is a Prometheus SUMMARY, not a histogram (a real histogram requires
``<name>_bucket{le="..."}`` series). A scraper parsing this as a histogram
would look for ``_bucket`` series and find ``quantile=`` labels instead:
invalid exposition for that metric type.

The fix declared the same block ``# TYPE <name> summary`` (the emitted shape
already matched a summary — metric_sum + metric_count + quantile lines — the
bug was purely the TYPE keyword).

@pytest.mark.regression per rules/testing.md § "Regression Testing".
"""

from __future__ import annotations

import re
from typing import Dict

import pytest
from fastapi.testclient import TestClient

from src.kailash.core.monitoring.connection_metrics import ConnectionMetricsCollector
from src.kailash.servers import WorkflowServer

_TYPE_RE = re.compile(r"^#\s*TYPE\s+(\S+)\s+(\S+)\s*$")
_METRIC_NAME_RE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)\{")


def _find_histogram_types_with_quantile_series(body: str) -> Dict[str, str]:
    """Return {metric_name: offending_line} for every metric declared
    ``# TYPE <name> histogram`` that also has a ``quantile=`` labeled series
    anywhere in the exposition text.

    This is a general structural parser (not a regex over the WHOLE body for
    the literal bug string) — it builds the TYPE map first, then checks every
    data line's metric name against it, so it also guards against the same
    mislabel being reintroduced anywhere else in the unified /metrics output.
    """
    declared_histogram: set[str] = set()
    for line in body.splitlines():
        match = _TYPE_RE.match(line.strip())
        if match and match.group(2) == "histogram":
            declared_histogram.add(match.group(1))

    offenders: Dict[str, str] = {}
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        if "quantile=" not in stripped:
            continue
        name_match = _METRIC_NAME_RE.match(stripped)
        if not name_match:
            continue
        metric_name = name_match.group(1)
        if metric_name in declared_histogram:
            offenders[metric_name] = line
    return offenders


@pytest.mark.regression
class TestNoHistogramTypeWithQuantileSeries:
    """No # TYPE ... histogram line may be followed by a quantile= series
    anywhere in this collector's own Prometheus export."""

    def test_export_prometheus_no_histogram_with_quantile(self):
        collector = ConnectionMetricsCollector("regression_test_pool")

        # Populate real histogram samples via the actual timer/tracking API
        # (no mocking) so export_prometheus() emits at least one percentile
        # summary block — the exact block the mislabel affected.
        with collector.track_acquisition():
            pass
        with collector.track_acquisition():
            pass

        body = collector.export_prometheus()

        offenders = _find_histogram_types_with_quantile_series(body)
        assert not offenders, (
            "Found metric(s) declared '# TYPE ... histogram' with a bare "
            f"quantile= series (should be 'summary'): {offenders}\n\nFull "
            f"export:\n{body}"
        )

        # Positive control: the fixed block IS present and now typed summary.
        assert "# TYPE connection_pool_connection_acquisition_ms summary" in body
        assert 'quantile="0.5"' in body

    def test_unified_metrics_endpoint_no_histogram_with_quantile(self):
        """Same structural invariant, walked through the real server
        /metrics endpoint — the unified path a Prometheus scraper actually
        hits in production (#1708 W1b)."""
        server = WorkflowServer(title="Type Mislabel Regression Test Server")
        client = TestClient(server.app)
        body = client.get("/metrics").text

        offenders = _find_histogram_types_with_quantile_series(body)
        assert not offenders, (
            "Found metric(s) declared '# TYPE ... histogram' with a bare "
            f"quantile= series in the unified /metrics scrape: {offenders}"
        )
