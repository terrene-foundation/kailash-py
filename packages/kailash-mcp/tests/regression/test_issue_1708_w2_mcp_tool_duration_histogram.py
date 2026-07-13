# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for #1708 Wave 2 (kailash-mcp observability program).

``kailash_mcp/utils/metrics.py`` previously computed p95/p99 "latency"
figures client-side, in-process, over a rolling ~100-sample window per tool
(``MetricsCollector._tool_latencies`` capped via
``if len(...) > 100: keep last 100``), then emitted them as bare
``mcp_tool_latency_p95{tool="..."} <value>`` / ``mcp_tool_latency_p99{...}``
lines with no ``le=``/``_bucket``/``_sum``/``_count`` shape — a fake
summary-as-histogram (no real Prometheus histogram backing it), and that
custom exporter (``export_metrics(format="prometheus")``) had ZERO
production call sites reaching it (grep confirms ``get_server_stats()`` only
calls ``export_metrics()`` with the default ``format="dict"``) — an orphan
on top of being fake.

This test file proves the replacement: a REAL ``prometheus_client.Histogram``
named ``mcp_tool_duration_seconds``, with explicit second-scale buckets,
labeled by the bounded/finite ``tool`` name, observed at the REAL
production record site (``MetricsCollector.track_tool_call``, invoked from
``MCPServer._create_enhanced_tool``'s sync/async wrappers) — and reachable
end-to-end via ``prometheus_client.generate_latest()``, the same call any
process-level ``/metrics`` HTTP handler uses (no registry argument = the
global default ``prometheus_client.REGISTRY``).

Per ``rules/testing.md`` § 3-Tier Testing: Tier 2, NO mocking. Tests
exercise the REAL ``MCPServer`` + ``@server.tool()`` decorator (the actual
user-facing registration API), not ``MetricsCollector`` in isolation, per
``rules/orphan-detection.md`` § 2 ("Tier 2 test exercises the wired path").
"""

from __future__ import annotations

import re

import pytest

from kailash_mcp.server import MCPServer
from kailash_mcp.utils import metrics as metrics_module
from kailash_mcp.utils.metrics import MetricsCollector

prometheus_client = pytest.importorskip("prometheus_client")

# The explicit second-scale bucket boundaries mandated for a `_seconds`
# tool-duration metric (rules/observability.md explicit-buckets
# requirement). prometheus_client auto-appends "+Inf" if the caller's last
# bucket isn't already INF (verified against the installed
# prometheus_client's Histogram._prepare_buckets).
EXPECTED_LE_VALUES = {
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
}


def _bucket_lines_for_tool(body: str, tool_label: str) -> list[str]:
    return [
        line
        for line in body.splitlines()
        if line.startswith("mcp_tool_duration_seconds_bucket")
        and f'tool="{tool_label}"' in line
    ]


@pytest.mark.regression
async def test_async_tool_call_emits_real_bucketed_histogram():
    """A real MCPServer async tool call reaches the real /metrics scrape.

    Exercises the production path: @server.tool() -> _create_enhanced_tool
    -> async_wrapper -> MetricsCollector.track_tool_call ->
    _get_tool_duration_histogram().observe(). Reads back via
    prometheus_client.generate_latest() — the same call a real process's
    /metrics HTTP handler makes (no registry arg = the global default
    REGISTRY this histogram is registered against).
    """
    tool_label = "w2_probe_async_tool"
    server = MCPServer(
        f"metrics-w2-async-{tool_label}",
        enable_cache=False,
        enable_discovery=False,
    )

    @server.tool()
    async def w2_probe_async_tool(x: int) -> int:
        return x * 2

    result = await w2_probe_async_tool(x=21)
    assert result == 42

    body = prometheus_client.generate_latest().decode("utf-8")

    bucket_lines = _bucket_lines_for_tool(body, tool_label)
    assert bucket_lines, (
        "expected mcp_tool_duration_seconds_bucket{le=...} lines for "
        f"tool={tool_label!r} in the real /metrics scrape; got none — the "
        "histogram never observed (orphaned emission, #1708 G1 Learning 3)"
    )

    seen_les = {
        m.group(1) for line in bucket_lines if (m := re.search(r'le="([^"]+)"', line))
    }
    assert EXPECTED_LE_VALUES <= seen_les, (
        f"missing explicit second-scale buckets: {EXPECTED_LE_VALUES - seen_les} "
        "— histogram is using generic-scale default buckets, not the "
        "explicit ones mandated for a _seconds tool-duration metric"
    )

    assert f'mcp_tool_duration_seconds_sum{{tool="{tool_label}"}}' in body
    count_lines = [
        line
        for line in body.splitlines()
        if line.startswith("mcp_tool_duration_seconds_count")
        and f'tool="{tool_label}"' in line
    ]
    assert count_lines, "expected a _count line for the observed tool call"
    assert float(count_lines[0].split()[-1]) >= 1.0


@pytest.mark.regression
def test_sync_tool_call_emits_real_bucketed_histogram():
    """The sync_wrapper production path (non-async tool) also observes."""
    tool_label = "w2_probe_sync_tool"
    server = MCPServer(
        f"metrics-w2-sync-{tool_label}",
        enable_cache=False,
        enable_discovery=False,
    )

    @server.tool()
    def w2_probe_sync_tool(x: int) -> int:
        return x + 1

    result = w2_probe_sync_tool(x=41)
    assert result == 42

    body = prometheus_client.generate_latest().decode("utf-8")
    bucket_lines = _bucket_lines_for_tool(body, tool_label)
    assert bucket_lines, "sync_wrapper tool call did not reach the real histogram"

    count_lines = [
        line
        for line in body.splitlines()
        if line.startswith("mcp_tool_duration_seconds_count")
        and f'tool="{tool_label}"' in line
    ]
    assert count_lines and float(count_lines[0].split()[-1]) >= 1.0


@pytest.mark.regression
async def test_no_fake_quantile_labeled_lines_remain():
    """The removed client-side p95/p99 summary must not resurface anywhere.

    Covers all three surfaces the fake summary used to reach: the
    get_tool_stats() dict, the legacy export_metrics(format="prometheus")
    string exporter, and the real /metrics scrape.
    """
    tool_label = "w2_probe_no_quantile_tool"
    server = MCPServer(
        f"metrics-w2-noquantile-{tool_label}",
        enable_cache=False,
        enable_discovery=False,
    )

    @server.tool()
    async def w2_probe_no_quantile_tool(x: int) -> int:
        return x

    await w2_probe_no_quantile_tool(x=1)

    tool_stats = server.metrics.get_tool_stats()[tool_label]
    assert "p95_latency" not in tool_stats
    assert "p99_latency" not in tool_stats
    # Legitimate non-percentile aggregates stay.
    assert "avg_latency" in tool_stats
    assert "min_latency" in tool_stats
    assert "max_latency" in tool_stats

    legacy_export = server.metrics.export_metrics(format="prometheus")
    assert "mcp_tool_latency_p95" not in legacy_export
    assert "mcp_tool_latency_p99" not in legacy_export
    assert f'mcp_tool_calls{{tool="{tool_label}"}}' in legacy_export

    real_body = prometheus_client.generate_latest().decode("utf-8")
    assert "mcp_tool_latency_p95" not in real_body
    assert "mcp_tool_latency_p99" not in real_body
    # mcp_tool_duration_seconds is a REAL histogram (le=), never a summary
    # (quantile=) — assert no quantile= label appears on any of its lines.
    assert not any(
        "mcp_tool_duration_seconds" in line and "quantile=" in line
        for line in real_body.splitlines()
    )


@pytest.mark.regression
async def test_markdown_metrics_formatter_survives_removed_percentile_fields():
    """MetricsFormatter must not KeyError on the removed p95_latency field.

    Regression for a sibling break the p95/p99 removal introduced:
    ``MetricsFormatter.format()`` (utils/formatters.py) did an unguarded
    ``stats['p95_latency']`` dict access. Exercises the REAL end-to-end
    chain: MCPServer -> a real tool call -> get_server_stats() (the
    production dict shape) -> MetricsFormatter().format().
    """
    from kailash_mcp.utils.formatters import MetricsFormatter

    tool_label = "w2_probe_formatter_tool"
    server = MCPServer(
        f"metrics-w2-formatter-{tool_label}",
        enable_cache=False,
        enable_discovery=False,
    )

    @server.tool()
    async def w2_probe_formatter_tool(x: int) -> int:
        return x

    await w2_probe_formatter_tool(x=1)

    server_stats = server.get_server_stats()
    formatted = MetricsFormatter().format(server_stats["metrics"])

    assert tool_label in formatted
    assert "Avg Latency" in formatted
    assert "P95" not in formatted
    assert "p95_latency" not in formatted


@pytest.mark.regression
def test_prometheus_unavailable_degrades_gracefully(monkeypatch):
    """track_tool_call() must not raise when prometheus_client is absent.

    Simulates the ImportError-guard branch (rules/dependencies.md §
    "Declared = Imported" optional-extra pattern) directly, mirroring
    kailash.core.monitoring.connection_metrics's degrade contract.
    """
    monkeypatch.setattr(metrics_module, "_PROMETHEUS_AVAILABLE", False)
    monkeypatch.setattr(metrics_module, "_TOOL_DURATION_HISTOGRAM", None)

    assert metrics_module._get_tool_duration_histogram() is None

    collector = MetricsCollector(enabled=True)
    # Must not raise even though the histogram getter returns None.
    collector.track_tool_call("degraded_tool", 0.01, success=True)

    stats = collector.get_tool_stats()["degraded_tool"]
    assert stats["calls"] == 1
    assert "avg_latency" in stats
