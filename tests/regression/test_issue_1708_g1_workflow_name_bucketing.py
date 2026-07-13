# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: #1708 G1 — bounded top-N admission for explicitly-named
workflows, plus explicit second-scale buckets on the node-duration histogram.

``sanitize_workflow_name`` (``src/kailash/runtime/metrics.py``) previously
collapsed ONLY the auto-generated ``Workflow-{8hex}`` default to a sentinel.
Any EXPLICITLY-named workflow (``name=f"etl-{customer_id}"``) passed through
verbatim into ``kailash_workflow_executions_total{workflow.name,success}`` and
``kailash_workflow_duration_seconds{workflow.name}`` -- an unbounded
cardinality bomb for any caller that mints a fresh name per
tenant/customer/request. This regression pins the top-N admission bucketer
fix: the first N distinct explicitly-named workflows are admitted verbatim,
every name beyond the cap collapses to the bounded ``"_other"`` sentinel.

Also pins the sibling MED-1 finding: ``kailash_node_execution_duration_seconds``
now supplies the same explicit second-scale bucket boundaries W1f gave the
workflow-duration histogram (previously OTel-default millisecond-scale
buckets, making per-node p95/p99 queries meaningless).
"""

from __future__ import annotations

import pytest

pytest.importorskip("opentelemetry.sdk.metrics", reason="requires kailash[telemetry]")

from opentelemetry.sdk.metrics import MeterProvider  # noqa: E402
from opentelemetry.sdk.metrics.export import InMemoryMetricReader  # noqa: E402

import kailash.runtime.metrics as metrics_mod  # noqa: E402


@pytest.fixture
def isolated_meter_reader(monkeypatch):
    """Real, isolated OTel MeterProvider + InMemoryMetricReader.

    Mirrors ``tests/regression/test_issue_1708_w1f_workflow_red_no_uuid_label.py``
    -- OTel's global ``set_meter_provider`` is a do-once guard, so this fixture
    redirects ``MetricsBridge``'s meter-resolution call directly rather than
    racing that global.
    """
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(metrics_mod._metrics_mod, "get_meter", provider.get_meter)
    monkeypatch.setattr(metrics_mod, "_global_bridge", None)
    yield reader
    monkeypatch.setattr(metrics_mod, "_global_bridge", None)


@pytest.fixture
def small_top_n_bucketer():
    """Replace the module-global workflow-name bucketer with a top_n=3 one
    for the duration of the test, then restore the env-derived default."""
    metrics_mod._reset_workflow_bucketer_for_tests(top_n=3)
    yield
    metrics_mod._reset_workflow_bucketer_for_tests()


def _all_attribute_strings(reader: InMemoryMetricReader, metric_name: str) -> list[str]:
    """Every attribute key AND value string recorded for ``metric_name``."""
    data = reader.get_metrics_data()
    values: list[str] = []
    if data is None:
        return values
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name != metric_name:
                    continue
                for dp in metric.data.data_points:
                    for key, val in dict(dp.attributes).items():
                        values.append(str(key))
                        values.append(str(val))
    return values


def _explicit_bounds_for(reader: InMemoryMetricReader, metric_name: str) -> list[tuple]:
    """``explicit_bounds`` recorded on every histogram data point for
    ``metric_name`` (empty list if the metric was never recorded)."""
    data = reader.get_metrics_data()
    bounds: list[tuple] = []
    if data is None:
        return bounds
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name != metric_name:
                    continue
                for dp in metric.data.data_points:
                    bounds.append(tuple(dp.explicit_bounds))
    return bounds


# ---------------------------------------------------------------------------
# Finding H1 -- unbounded explicitly-named workflow cardinality
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_sanitize_workflow_name_admits_top_n_then_buckets_overflow_to_other(
    small_top_n_bucketer,
) -> None:
    """Behavioral: with top_n=3, the first 3 distinct explicit names pass
    through verbatim; every subsequent distinct name collapses to `_other`."""
    admitted = [
        metrics_mod.sanitize_workflow_name(f"etl-customer-{i}") for i in range(3)
    ]
    assert admitted == ["etl-customer-0", "etl-customer-1", "etl-customer-2"]

    overflow = [
        metrics_mod.sanitize_workflow_name(f"etl-customer-{i}") for i in range(3, 10)
    ]
    assert overflow == ["_other"] * 7

    # Previously-admitted names keep resolving verbatim (monotonic admission).
    assert metrics_mod.sanitize_workflow_name("etl-customer-0") == "etl-customer-0"

    # The UUID-default sentinel collapse still applies independently and is
    # NOT itself subject to the top-N cap (it never enters the bucketer).
    assert metrics_mod.sanitize_workflow_name("Workflow-deadbeef") == "unnamed_workflow"


@pytest.mark.regression
def test_more_than_top_n_distinct_workflow_names_bound_exported_label_cardinality(
    isolated_meter_reader, small_top_n_bucketer
) -> None:
    """>N distinct explicitly-named workflow executions MUST NOT mint >N+1
    distinct ``workflow.name`` label values on the real OTel export path --
    proving the fix bounds the canonical hot-path metric, not just the
    ``sanitize_workflow_name`` helper in isolation (#1708 G1 HIGH)."""
    bridge = metrics_mod.MetricsBridge()
    distinct_names = [f"etl-customer-{i}" for i in range(10)]  # 10 > top_n=3
    for name in distinct_names:
        bridge.record_workflow_execution(name, 0.05, success=True)

    values = _all_attribute_strings(
        isolated_meter_reader, "kailash_workflow_executions_total"
    )
    assert values, "kailash_workflow_executions_total not recorded"

    # The overflow names (index 3..9) MUST NOT appear verbatim anywhere.
    leaked = [n for n in distinct_names[3:] if n in values]
    assert leaked == [], f"overflow workflow names leaked verbatim: {leaked}"

    # The bounded sentinel MUST be present -- overflow really collapsed.
    assert "_other" in values

    # Total distinct workflow.name label VALUES emitted is bounded at
    # top_n (3 admitted) + 1 (the "_other" bucket) = 4, never 10.
    emitted_name_values = {v for v in values if v in distinct_names or v == "_other"}
    assert len(emitted_name_values) <= 4, (
        f"expected <= 4 distinct workflow.name values (3 admitted + _other), "
        f"got {len(emitted_name_values)}: {emitted_name_values}"
    )


# ---------------------------------------------------------------------------
# Finding MED-1 -- node-duration histogram had no explicit buckets
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_node_execution_duration_seconds_exports_explicit_second_scale_buckets(
    isolated_meter_reader,
) -> None:
    """``kailash_node_execution_duration_seconds`` MUST export the same
    second-scale ``explicit_bounds`` W1f gave the workflow-duration
    histogram -- not OTel's millisecond-scale default -- so per-node p95/p99
    queries are meaningful (#1708 G1 MED-1)."""
    bridge = metrics_mod.MetricsBridge()
    bridge.record_node_duration("n1", "PythonCodeNode", 1.5, status="ok")

    bounds = _explicit_bounds_for(
        isolated_meter_reader, "kailash_node_execution_duration_seconds"
    )
    assert bounds, "kailash_node_execution_duration_seconds not recorded"
    for recorded_bounds in bounds:
        assert (
            recorded_bounds == metrics_mod.WORKFLOW_DURATION_BUCKETS_SECONDS
        ), f"expected second-scale explicit bounds, got {recorded_bounds!r}"
        # Sanity: NOT the OTel millisecond-scale default (0, 5, 10, 25 ...).
        assert 30.0 in recorded_bounds and 600.0 in recorded_bounds
