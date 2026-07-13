# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests — ``dataflow_query_duration_seconds`` RED histogram.

#1708 Wave 3 (observability program): the general DataFlow query path had
only an OTel span attribute (``kailash.runtime.instrumentation.dataflow.
DataFlowInstrumentor`` -- ``db.duration_s``, one number per query on one
trace, never bucketed, never aggregated, and — per this same audit —
never actually wired into any production call site). This module adds a
REAL bucketed Prometheus histogram
(``dataflow.observability.query_metrics.DataFlowQueryMetrics``, mirroring
the reference-correct ``dataflow.fabric.metrics.FabricMetrics`` pattern)
and wires it into ``dataflow.features.express.DataFlowExpress.
_execute_with_timing`` — the single choke point every ``db.express`` CRUD
call already routes through.

Per rules/orphan-detection.md + the #1708 G1 learning ("worst finding was
orphaned emission code no production path invoked"), this test proves the
full chain end-to-end: real ``db.express`` operations against a real
(file-backed) SQLite database → the singleton's REAL
``prometheus_client`` registry → a REAL scrape (``render_exposition()``)
with genuine ``le``-bucketed lines, ``_sum``, and ``_count`` — never a
mocked counter.

NO MOCKING (rules/testing.md § 3-Tier — Tier 2 real infrastructure;
SQLite is real, per the task's infra note that Postgres creds are
known-broken in this environment).
"""

from __future__ import annotations

import re

import pytest

from dataflow import DataFlow
from dataflow.observability.query_metrics import (
    DataFlowQueryMetrics,
    get_dataflow_query_metrics,
    reset_dataflow_query_metrics,
)

pytestmark = pytest.mark.regression


@pytest.fixture(autouse=True)
def _reset_query_metrics_singleton():
    """Fresh ``CollectorRegistry`` per test — mirrors the FabricMetrics
    test-reset discipline (``tests/integration/fabric/test_metrics_phase_5_12.py``)
    so this test's assertions are never polluted by histogram state a
    prior test in the same pytest process may have recorded.
    """
    reset_dataflow_query_metrics()
    yield
    reset_dataflow_query_metrics()


def _label(operation: str, model: str) -> str:
    # prometheus_client's text exposition renders labels in ALPHABETICAL
    # order of label NAME, not declaration order -- "model" sorts before
    # "operation".
    return f'model="{model}",operation="{operation}"'


def _bucket_line_pattern(operation: str, model: str) -> str:
    label = _label(operation, model)
    return rf'dataflow_query_duration_seconds_bucket\{{le="[^"]+",{label}\}} '


def _sum_count(body: str, operation: str, model: str) -> tuple[float, float]:
    label = _label(operation, model)
    sum_match = re.search(
        rf"dataflow_query_duration_seconds_sum\{{{label}\}} ([0-9.eE+-]+)", body
    )
    count_match = re.search(
        rf"dataflow_query_duration_seconds_count\{{{label}\}} ([0-9.eE+-]+)", body
    )
    assert sum_match is not None, f"missing _sum line for {label} in:\n{body}"
    assert count_match is not None, f"missing _count line for {label} in:\n{body}"
    return float(sum_match.group(1)), float(count_match.group(1))


# ---------------------------------------------------------------------------
# End-to-end: real db.express queries against SQLite -> real scrape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_duration_histogram_exports_real_buckets_for_express_operations(
    sqlite_file_url,
):
    """Every real ``db.express`` CRUD call must be reflected in a REAL
    ``le``-bucketed Prometheus histogram line with bounded ``operation``/
    ``model`` labels — proving the emission reaches the actual query
    execution path, not just an isolated unit test of the metrics class.
    """
    db = DataFlow(sqlite_file_url, auto_migrate=True)

    @db.model
    class Widget:
        id: str
        name: str

    @db.model
    class Gadget:
        id: str
        label: str

    try:
        await db.initialize()

        # Real queries through the real, framework-mandated CRUD path.
        await db.express.create("Widget", {"id": "w1", "name": "alpha"})
        await db.express.read("Widget", "w1")
        await db.express.update("Widget", "w1", {"name": "beta"})
        await db.express.list("Widget", {})
        await db.express.count("Widget", {})
        await db.express.create("Gadget", {"id": "g1", "label": "x"})
        await db.express.delete("Widget", "w1")

        metrics = get_dataflow_query_metrics()
        assert metrics.enabled, (
            "prometheus_client must be installed in this test venv "
            "(kailash-dataflow[fabric] extra) for dataflow_query_duration_"
            "seconds to be a real (non-noop) histogram"
        )

        body = metrics.render_exposition().decode()

        # Real HELP/TYPE declaration proves this is a genuine
        # prometheus_client Histogram family, not a hand-rolled dict.
        assert "# HELP dataflow_query_duration_seconds" in body
        assert "# TYPE dataflow_query_duration_seconds histogram" in body

        # Every operation actually invoked above must produce a real
        # le-bucketed line + a real (non-fake) _sum/_count pair, with the
        # bounded model label carrying the real model name (both Widget
        # and Gadget stay well under the top-100 cardinality cap).
        exercised = [
            ("create", "Widget"),
            ("read", "Widget"),
            ("update", "Widget"),
            ("list", "Widget"),
            ("count", "Widget"),
            ("delete", "Widget"),
            ("create", "Gadget"),
        ]
        for operation, model in exercised:
            assert re.search(_bucket_line_pattern(operation, model), body), (
                f"missing le-bucketed line for operation={operation!r} "
                f"model={model!r} in:\n{body}"
            )
            total_sum, total_count = _sum_count(body, operation, model)
            assert total_count >= 1, f"{operation}/{model} _count must be >= 1"
            assert total_sum > 0.0, (
                f"{operation}/{model} _sum must be a real positive duration, "
                "never a fake 0"
            )

        # Explicit second-scale buckets (#1708 G1 learning: default
        # prometheus_client buckets bottom out at 5ms and would put every
        # sub-millisecond Express observation in one bucket).
        for expected_bucket in ('le="0.0005"', 'le="0.005"', 'le="0.25"', 'le="10.0"'):
            assert expected_bucket in body, f"missing explicit bucket {expected_bucket}"
    finally:
        await db.express.close_async()


# ---------------------------------------------------------------------------
# Bounded-label contract (behavioral, no DB required)
# ---------------------------------------------------------------------------


def test_unknown_operation_bounds_to_other():
    """An operation outside the finite CRUD enum collapses to "_other"
    rather than creating a new, unbounded label value."""
    metrics = DataFlowQueryMetrics()
    metrics.record_query(operation="not_a_real_verb", model="Widget", duration_s=0.01)

    body = metrics.render_exposition().decode()
    assert _label("_other", "Widget") in body
    assert 'operation="not_a_real_verb"' not in body


def test_model_cardinality_overflow_bounds_to_other():
    """Once the model-cardinality cap is reached, additional distinct
    model names collapse to "_other" instead of growing the label set
    unboundedly (mirrors rules/tenant-isolation.md §4 top-N bucketing)."""
    metrics = DataFlowQueryMetrics(model_cardinality_cap=1)
    metrics.record_query(operation="create", model="ModelA", duration_s=0.01)
    metrics.record_query(operation="create", model="ModelB", duration_s=0.01)
    metrics.record_query(operation="create", model="ModelA", duration_s=0.02)

    body = metrics.render_exposition().decode()
    assert _label("create", "ModelA") in body
    assert _label("create", "_other") in body
    # ModelB itself must never appear as a raw label value once over cap.
    assert 'model="ModelB"' not in body
