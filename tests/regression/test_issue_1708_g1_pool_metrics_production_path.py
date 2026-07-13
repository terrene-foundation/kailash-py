# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: #1708 G1 HIGH-1 — pool idle gauge + exhaustion counter reach a
PRODUCTION ``/metrics`` scrape with NO ``ConnectionMetricsProvider.
register_source(...)`` wiring step.

Before this fix, ``kailash_pool_connections_idle`` and
``kailash_pool_exhaustion_events_total`` were only observable through
``ConnectionMetricsProvider.register_source(...)`` (see
``tests/tier2_integration/test_pool_metrics_use_completeness.py``), which has
ZERO production callers — ``grep -rn register_source src/ | grep -vi test``
returns only the method definition and its docstring cross-references. A
real ``WorkflowServer`` / ``EnterpriseWorkflowServer`` therefore had an empty
``ConnectionMetricsProvider._sources`` and emitted NO idle/exhaustion lines
at all, no matter how much pool activity the real
:class:`~kailash.core.monitoring.connection_metrics.ConnectionMetricsCollector`
instances recorded.

The fix registers both as real ``prometheus_client`` instruments on the
process-wide default ``REGISTRY`` (mirroring the acquire-wait histogram's
existing pattern, ``_get_acquire_wait_histogram``), set/incremented directly
inside ``update_pool_stats`` / ``track_pool_exhaustion`` — the REAL emission
sites — so they flow into ``generate_latest()`` (and therefore
``render_prometheus_exposition()``) unconditionally.

This test proves the production path end to end: it records pool activity
through the real collector API, hits the REAL ``GET /metrics`` HTTP endpoint
of BOTH server surfaces via ``TestClient``, and asserts the metrics appear —
while explicitly asserting ``register_source`` was never called (the
provider's ``_sources`` mapping stays empty throughout).

Also pins #1708 G1 LOW-1: ``EnterpriseWorkflowServer.__metrics`` previously
omitted ``extra_lines=conn_lines`` entirely (it overrides
``_register_root_endpoints`` wholesale rather than delegating to
``WorkflowServer``'s), so the enterprise surface diverged from the base
surface. Both surfaces MUST now emit identical pool-metric families for the
same pool.

No mocking (`rules/testing.md` Tier 2): real ``ConnectionMetricsCollector``
instances, real ``prometheus_client`` registry, real FastAPI apps via
``TestClient``.
"""

from __future__ import annotations

import re
import uuid

import pytest
from fastapi.testclient import TestClient

from src.kailash.core.monitoring.connection_metrics import ConnectionMetricsCollector
from src.kailash.servers import EnterpriseWorkflowServer, WorkflowServer


def _extract_value(body: str, metric_name: str, pool_label: str) -> float | None:
    """Return the numeric value of ``metric_name{pool="..."}`` in ``body``.

    Structural line-parse (not a semantic/regex "did a string appear" check
    per ``rules/probe-driven-verification.md`` Rule 3 — this asserts the
    file-format-defined shape of a Prometheus exposition line, which is a
    structural property, not a semantic claim about assistant output).
    """
    pattern = re.compile(
        r"^"
        + re.escape(metric_name)
        + r"\{[^}]*"
        + re.escape(pool_label)
        + r"[^}]*\}\s+([0-9.eE+-]+)\s*$"
    )
    for line in body.splitlines():
        m = pattern.match(line)
        if m:
            return float(m.group(1))
    return None


@pytest.mark.regression
class TestPoolMetricsReachProductionScrapeWithoutRegisterSource:
    """kailash_pool_connections_idle / kailash_pool_exhaustion_events_total
    MUST appear on a REAL server's /metrics without any test (or production
    code) calling register_source()."""

    def test_workflow_server_emits_idle_and_exhaustion_without_register_source(self):
        pool_name = f"g1_prod_path_{uuid.uuid4().hex[:8]}"
        collector = ConnectionMetricsCollector(pool_name)

        # Real production API calls -- the same calls WorkflowConnectionPool
        # makes on its maintenance / acquire-failure paths.
        collector.update_pool_stats(active=3, idle=7, total=10)
        collector.track_pool_exhaustion()
        collector.track_pool_exhaustion()

        server = WorkflowServer(title="G1 Pool Metrics Production Path Server")
        try:
            # Structural proof that NOTHING wired this collector into the
            # router-level provider -- the historical (and only) path that
            # used to be required for these two metrics to appear.
            assert server._connection_metrics_provider._sources == {}

            client = TestClient(server.app)
            body = client.get("/metrics").text

            pool_label = f'pool="{pool_name}"'
            assert "# TYPE kailash_pool_connections_idle gauge" in body
            idle_value = _extract_value(
                body, "kailash_pool_connections_idle", pool_label
            )
            assert idle_value == 7.0, body

            assert "# TYPE kailash_pool_exhaustion_events_total counter" in body
            exhaustion_value = _extract_value(
                body, "kailash_pool_exhaustion_events_total", pool_label
            )
            assert exhaustion_value == 2.0, body

            # The provider's _sources mapping is STILL empty after the
            # scrape -- proving the /metrics response did not depend on it.
            assert server._connection_metrics_provider._sources == {}
        finally:
            server.close()

    def test_enterprise_server_emits_idle_and_exhaustion_without_register_source(self):
        """#1708 G1 LOW-1: EnterpriseWorkflowServer's /metrics MUST emit the
        same pool-metric families the base WorkflowServer emits."""
        pool_name = f"g1_prod_path_ent_{uuid.uuid4().hex[:8]}"
        collector = ConnectionMetricsCollector(pool_name)

        collector.update_pool_stats(active=1, idle=4, total=5)
        collector.track_pool_exhaustion()

        server = EnterpriseWorkflowServer(
            title="G1 Pool Metrics Production Path Enterprise Server"
        )
        try:
            assert server._connection_metrics_provider._sources == {}

            client = TestClient(server.app)
            body = client.get("/metrics").text

            pool_label = f'pool="{pool_name}"'
            assert "# TYPE kailash_pool_connections_idle gauge" in body
            idle_value = _extract_value(
                body, "kailash_pool_connections_idle", pool_label
            )
            assert idle_value == 4.0, body

            assert "# TYPE kailash_pool_exhaustion_events_total counter" in body
            exhaustion_value = _extract_value(
                body, "kailash_pool_exhaustion_events_total", pool_label
            )
            assert exhaustion_value == 1.0, body

            assert server._connection_metrics_provider._sources == {}
        finally:
            server.close()

    def test_both_server_surfaces_expose_identical_pool_metric_families(self):
        """#1708 G1 LOW-1 parity: the SET of pool-metric family names on the
        base surface and the enterprise surface MUST match -- the
        enterprise /metrics handler previously omitted extra_lines=conn_lines
        entirely, dropping every ConnectionMetricsProvider-sourced line
        (utilization/near-exhaustion alert gauges) that the base surface has
        always had."""
        pool_name = f"g1_parity_{uuid.uuid4().hex[:8]}"
        collector = ConnectionMetricsCollector(pool_name)
        collector.update_pool_stats(active=9, idle=1, total=10)
        collector.track_pool_exhaustion()
        # Also exercise the acquire-wait histogram so all THREE already-fixed
        # metric families (W1c histogram + G1 idle gauge + G1 exhaustion
        # counter) are present in this process for the parity check below.
        with collector.track_acquisition():
            pass

        base_server = WorkflowServer(title="G1 Parity Base Server")
        enterprise_server = EnterpriseWorkflowServer(
            title="G1 Parity Enterprise Server"
        )
        try:
            base_body = TestClient(base_server.app).get("/metrics").text
            enterprise_body = TestClient(enterprise_server.app).get("/metrics").text

            for metric_name in (
                "kailash_pool_connections_idle",
                "kailash_pool_exhaustion_events_total",
                "kailash_pool_acquire_wait_seconds",
            ):
                assert (
                    f"# TYPE {metric_name}" in base_body
                ), f"{metric_name} missing from base WorkflowServer /metrics"
                assert f"# TYPE {metric_name}" in enterprise_body, (
                    f"{metric_name} missing from EnterpriseWorkflowServer /metrics "
                    "-- base and enterprise /metrics have diverged (G1 LOW-1)"
                )
        finally:
            base_server.close()
            enterprise_server.close()
