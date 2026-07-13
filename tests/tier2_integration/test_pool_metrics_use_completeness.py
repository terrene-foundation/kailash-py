"""Tier 2 integration tests: pool acquire-wait histogram + USE completeness
(idle connections + pool-exhaustion events) reaching the REAL unified server
``/metrics`` scrape (#1708 W1c).

These tests walk the actual user-facing surface — ``WorkflowServer``'s real
``GET /metrics`` HTTP endpoint via ``TestClient`` — rather than calling an
exporter function directly. That is the same unified path #1708 W1b built
(``render_prometheus_exposition()``: custom ``MetricsRegistry`` +
``prometheus_client`` default registry + optional pool lines), so a green
assertion here proves the new histogram / gauge / counter reach production
scrapes, not merely that a helper function returns the right string.

No mocking (`rules/testing.md` Tier 2): real ``ConnectionMetricsCollector``
instances, real ``prometheus_client`` registry, real FastAPI app via
``TestClient``.
"""

from __future__ import annotations

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from src.kailash.core.monitoring.connection_metrics import ConnectionMetricsCollector
from src.kailash.servers import WorkflowServer

EXPECTED_ACQUIRE_WAIT_BUCKETS = (
    "0.001",
    "0.005",
    "0.01",
    "0.025",
    "0.05",
    "0.1",
    "0.25",
    "0.5",
    "1.0",
    "2.5",
    "5.0",
    "10.0",
    "+Inf",
)


@pytest.mark.integration
class TestPoolAcquireWaitHistogramReachesUnifiedMetrics:
    """kailash_pool_acquire_wait_seconds MUST be a real bucketed histogram
    (le= series + _sum + _count) reachable from the server's real /metrics
    endpoint — the same unified path #1708 W1b built for OTel + native
    prometheus_client instruments."""

    def test_histogram_bucket_sum_count_reach_metrics_endpoint(self):
        # Unique pool name per test: an ephemeral test-only label to isolate
        # this test's assertions from any other test's observations on the
        # same process-global prometheus_client REGISTRY (not a precedent for
        # production cardinality — production pool names are a small, fixed,
        # operator-assigned set per rules/security.md § bounded labels).
        pool_name = f"acquire_wait_test_{uuid.uuid4().hex[:8]}"
        collector = ConnectionMetricsCollector(pool_name)

        # Real TimerContext + real sleep — no mocking of the timing path.
        for _ in range(3):
            with collector.track_acquisition():
                time.sleep(0.01)

        server = WorkflowServer(title="Acquire Wait Histogram Test Server")
        client = TestClient(server.app)
        resp = client.get("/metrics")
        assert resp.status_code == 200
        body = resp.text

        assert "# HELP kailash_pool_acquire_wait_seconds" in body
        # The mislabel this shard fixes was a SUMMARY (quantile= lines, no
        # le= buckets) declared "# TYPE ... histogram". This metric is the
        # real thing: bucketed, declared histogram, and it must say so.
        assert "# TYPE kailash_pool_acquire_wait_seconds histogram" in body

        pool_label = f'pool="{pool_name}"'
        bucket_lines = [
            line
            for line in body.splitlines()
            if line.startswith("kailash_pool_acquire_wait_seconds_bucket")
            and pool_label in line
        ]
        assert bucket_lines, "no le=-bucketed lines for this pool in /metrics"

        for bucket in EXPECTED_ACQUIRE_WAIT_BUCKETS:
            assert any(f'le="{bucket}"' in line for line in bucket_lines), (
                f"missing explicit second-scale bucket le={bucket!r}; "
                f"got:\n" + "\n".join(bucket_lines)
            )

        count_lines = [
            line
            for line in body.splitlines()
            if line.startswith("kailash_pool_acquire_wait_seconds_count")
            and pool_label in line
        ]
        sum_lines = [
            line
            for line in body.splitlines()
            if line.startswith("kailash_pool_acquire_wait_seconds_sum")
            and pool_label in line
        ]
        assert len(count_lines) == 1, count_lines
        assert len(sum_lines) == 1, sum_lines

        observed_count = float(count_lines[0].rsplit(" ", 1)[1])
        observed_sum = float(sum_lines[0].rsplit(" ", 1)[1])
        assert observed_count == 3.0
        # 3 observations of >= 0.01s each; real wall-clock sleep, so the
        # floor is loose to avoid flakiness on a loaded CI runner.
        assert observed_sum >= 0.02

    def test_le_infinity_bucket_is_cumulative_ceiling(self):
        """The +Inf bucket MUST equal the total observation count — proves
        this is a real cumulative histogram, not a mislabeled summary."""
        pool_name = f"acquire_wait_ceiling_{uuid.uuid4().hex[:8]}"
        collector = ConnectionMetricsCollector(pool_name)

        for _ in range(5):
            with collector.track_acquisition():
                pass  # near-zero duration; still lands in the smallest bucket

        server = WorkflowServer(title="Acquire Wait Ceiling Test Server")
        client = TestClient(server.app)
        body = client.get("/metrics").text

        pool_label = f'pool="{pool_name}"'
        inf_lines = [
            line
            for line in body.splitlines()
            if line.startswith("kailash_pool_acquire_wait_seconds_bucket")
            and pool_label in line
            and 'le="+Inf"' in line
        ]
        assert len(inf_lines) == 1
        assert float(inf_lines[0].rsplit(" ", 1)[1]) == 5.0


@pytest.mark.integration
class TestUSECompletenessReachesUnifiedMetrics:
    """Idle-connection gauge + pool-exhaustion counter MUST appear in the
    real server /metrics scrape once a pool source reporting them is
    registered — the wiring gap #1708 W1c closes."""

    def test_idle_and_exhaustion_appear_in_metrics_endpoint(self):
        pool_name = f"use_pool_{uuid.uuid4().hex[:8]}"
        collector = ConnectionMetricsCollector(pool_name)
        collector.update_pool_stats(active=6, idle=4, total=10)
        collector.track_pool_exhaustion()
        collector.track_pool_exhaustion()
        collector.track_pool_exhaustion()

        server = WorkflowServer(title="USE Completeness Test Server")
        # Register the real collector as a pool source through the exact
        # mechanism production code uses (ConnectionMetricsProvider.
        # register_source), proving the collector -> router -> scrape path
        # end to end rather than a synthetic dict shortcut.
        server._connection_metrics_provider.register_source(pool_name, collector)

        client = TestClient(server.app)
        body = client.get("/metrics").text

        pool_label = f'pool="{pool_name}"'
        assert "# TYPE kailash_pool_connections_idle gauge" in body
        assert f"kailash_pool_connections_idle{{{pool_label}}} 4" in body
        assert "# TYPE kailash_pool_exhaustion_events_total counter" in body
        assert f"kailash_pool_exhaustion_events_total{{{pool_label}}} 3" in body
