# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: #1708 — workflow_id must not be an unbounded metric label.

The enterprise Prometheus/DataDog adapter recorded ``workflow_id`` (a per-build
``uuid4()``) as a metric label, which mints a new time-series per workflow build
— a cardinality bomb on any long-lived scrape target. Only the bounded
``success`` dimension may be a label.
"""

from __future__ import annotations

import pytest


@pytest.mark.regression
def test_workflow_execution_metric_has_no_unbounded_workflow_id_label() -> None:
    prometheus_client = pytest.importorskip("prometheus_client")
    from kailash.runtime.monitoring.runtime_monitor import EnterpriseMonitoringManager

    mgr = EnterpriseMonitoringManager("regr-1708-runtime")
    if not mgr.adapters["prometheus"].enabled:
        pytest.skip("prometheus_client adapter unavailable")

    mgr.record_workflow_execution("uuid-aaaa-1111", 12.5, True)
    mgr.record_workflow_execution("uuid-bbbb-2222", 8.0, False)

    out = prometheus_client.generate_latest().decode()
    lines = [
        line
        for line in out.splitlines()
        if "workflows_total" in line and not line.startswith("#")
    ]
    assert lines, "kailash_runtime_workflows_total not exported"
    for line in lines:
        assert "workflow_id" not in line, f"unbounded workflow_id label present: {line}"
    # the bounded success dimension survives
    assert any(
        'success="True"' in line for line in lines
    ), "bounded success label missing"
