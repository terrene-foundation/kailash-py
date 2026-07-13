# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring tests for canonical workflow RED metrics (issue #1708 W1f).

Per rules/facade-manager-detection.md §1 + rules/orphan-detection.md §2, these
tests prove the ``MetricsBridge.record_workflow_execution`` RED triple is
ACTUALLY invoked by ``LocalRuntime.execute`` / ``AsyncLocalRuntime`` on a real
workflow run — not just callable in isolation. A REAL, in-memory OTel
``InMemoryMetricReader`` is attached, a real trivial ``WorkflowBuilder``
workflow is executed through the real ``LocalRuntime``, and the recorded
samples are read back from the reader (no source-grep, no mocking of the
meter/counter/histogram — every instrument is a genuine OTel SDK object).

Isolation note: OpenTelemetry's global ``set_meter_provider`` may only
succeed once per process (subsequent calls are silent no-ops with a logged
warning — see ``opentelemetry.metrics._internal._set_meter_provider``, a
``do_once`` guard). Rather than race that global against whichever test
module in this pytest session claims it first, the ``_isolated_meter_reader``
fixture redirects the SAME resolution point ``MetricsBridge.__init__`` calls
(``kailash.runtime.metrics._metrics_mod.get_meter``) to a dedicated, real
``MeterProvider``/``InMemoryMetricReader`` pair for the duration of one test.
Every ``Counter.add`` / ``Histogram.record`` call in the code under test is
still genuine OTel SDK behavior; only the provider-resolution wiring is
redirected — not a mock, not a stub, no faked return values.
"""

from __future__ import annotations

from typing import Any, Optional

import pytest

pytest.importorskip("opentelemetry.sdk.metrics", reason="requires kailash[telemetry]")

from opentelemetry.sdk.metrics import MeterProvider  # noqa: E402
from opentelemetry.sdk.metrics.export import InMemoryMetricReader  # noqa: E402

import kailash.runtime.metrics as metrics_mod  # noqa: E402
from kailash.runtime.async_local import AsyncLocalRuntime  # noqa: E402
from kailash.runtime.local import LocalRuntime  # noqa: E402
from kailash.workflow.builder import WorkflowBuilder  # noqa: E402


@pytest.fixture
def isolated_meter_reader(monkeypatch):
    """Attach a real, isolated OTel MeterProvider + InMemoryMetricReader.

    Yields the ``InMemoryMetricReader`` so tests can call
    ``get_metrics_data()`` and assert on real recorded samples.
    """
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])

    # Redirect the exact call MetricsBridge.__init__ makes
    # (`_metrics_mod.get_meter(meter_name)`) to OUR provider, bypassing the
    # process-global do-once guard entirely. `provider.get_meter` is the
    # real OTel SDK MeterProvider method — no mock object involved.
    monkeypatch.setattr(metrics_mod._metrics_mod, "get_meter", provider.get_meter)
    # Force a fresh MetricsBridge singleton bound to our provider on the
    # next get_metrics_bridge() call.
    monkeypatch.setattr(metrics_mod, "_global_bridge", None)

    yield reader

    # Reset the singleton again so subsequent tests build a fresh bridge
    # against whatever meter provider is live at that point.
    monkeypatch.setattr(metrics_mod, "_global_bridge", None)


def _find_metric(reader: InMemoryMetricReader, name: str) -> Optional[Any]:
    data = reader.get_metrics_data()
    if data is None:
        return None
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == name:
                    return metric
    return None


def _data_points(metric: Any) -> list:
    if metric is None:
        return []
    return list(metric.data.data_points)


def _build_trivial_workflow(name: str, *, code: str = 'result = {"ok": True}'):
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "n", {"code": code})
    return builder.build(name=name)


def _build_two_node_failing_workflow(name: str):
    """A -> B where A raises. `A` has a downstream dependent, so
    LocalRuntime's ``_should_stop_on_error`` stops execution and the
    failure propagates out of ``execute()`` as a raised exception —
    the real "a workflow that raises" scenario (not just a per-node
    ``failed: True`` entry captured silently in the results dict)."""
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "a", {"code": 'raise ValueError("boom")'})
    builder.add_node("PythonCodeNode", "b", {"code": 'result = {"ok": True}'})
    builder.add_connection("a", "result", "b", "unused_input")
    return builder.build(name=name)


class TestLocalRuntimeExecuteRedMetrics:
    """Sync LocalRuntime.execute() -> MetricsBridge wiring."""

    def test_success_path_records_counter_and_duration(self, isolated_meter_reader):
        workflow = _build_trivial_workflow("w1f-sync-success")

        with LocalRuntime() as runtime:
            results, run_id = runtime.execute(workflow)

        assert run_id is not None
        assert results["n"]["result"] == {"ok": True}

        counter = _find_metric(
            isolated_meter_reader, "kailash_workflow_executions_total"
        )
        assert counter is not None, "kailash_workflow_executions_total not recorded"
        points = _data_points(counter)
        assert any(
            dict(dp.attributes).get("workflow.name") == "w1f-sync-success"
            and dict(dp.attributes).get("success") == "true"
            and dp.value >= 1
            for dp in points
        ), f"expected bounded {{workflow.name, success=true}} sample, got {[dict(p.attributes) for p in points]}"

        histogram = _find_metric(
            isolated_meter_reader, "kailash_workflow_duration_seconds"
        )
        assert histogram is not None, "kailash_workflow_duration_seconds not recorded"
        hpoints = _data_points(histogram)
        assert any(
            dict(dp.attributes).get("workflow.name") == "w1f-sync-success"
            and dp.count >= 1
            for dp in hpoints
        ), f"expected a duration sample for w1f-sync-success, got {[dict(p.attributes) for p in hpoints]}"
        # Second-scale explicit bucket boundaries (not the ms-scale OTel
        # default) — a trivial in-process node execution must land inside
        # the pinned boundaries, not overflow into a single useless bucket.
        matching = next(
            dp
            for dp in hpoints
            if dict(dp.attributes).get("workflow.name") == "w1f-sync-success"
        )
        assert (
            tuple(matching.explicit_bounds)
            == metrics_mod.WORKFLOW_DURATION_BUCKETS_SECONDS
        )

    def test_error_path_records_success_false(self, isolated_meter_reader):
        workflow = _build_two_node_failing_workflow("w1f-sync-error")

        with pytest.raises(Exception):
            with LocalRuntime() as runtime:
                runtime.execute(workflow)

        counter = _find_metric(
            isolated_meter_reader, "kailash_workflow_executions_total"
        )
        assert counter is not None
        points = _data_points(counter)
        assert any(
            dict(dp.attributes).get("workflow.name") == "w1f-sync-error"
            and dict(dp.attributes).get("success") == "false"
            and dp.value >= 1
            for dp in points
        ), f"expected success=false sample, got {[dict(p.attributes) for p in points]}"

        histogram = _find_metric(
            isolated_meter_reader, "kailash_workflow_duration_seconds"
        )
        assert histogram is not None
        hpoints = _data_points(histogram)
        assert any(
            dict(dp.attributes).get("workflow.name") == "w1f-sync-error"
            and dp.count >= 1
            for dp in hpoints
        ), "expected a duration sample recorded on the error path too"


class TestAsyncLocalRuntimeExecuteRedMetrics:
    """Async AsyncLocalRuntime.execute_workflow_async() -> MetricsBridge wiring."""

    @pytest.mark.asyncio
    async def test_success_path_records_counter_and_duration(
        self, isolated_meter_reader
    ):
        workflow = _build_trivial_workflow("w1f-async-success")

        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(workflow, inputs={})

        assert run_id is not None
        assert results["n"]["result"] == {"ok": True}

        counter = _find_metric(
            isolated_meter_reader, "kailash_workflow_executions_total"
        )
        assert counter is not None
        points = _data_points(counter)
        assert any(
            dict(dp.attributes).get("workflow.name") == "w1f-async-success"
            and dict(dp.attributes).get("success") == "true"
            for dp in points
        ), f"expected success=true sample, got {[dict(p.attributes) for p in points]}"

    @pytest.mark.asyncio
    async def test_error_path_records_success_false(self, isolated_meter_reader):
        workflow = _build_two_node_failing_workflow("w1f-async-error")

        runtime = AsyncLocalRuntime()
        with pytest.raises(Exception):
            await runtime.execute_workflow_async(workflow, inputs={})

        counter = _find_metric(
            isolated_meter_reader, "kailash_workflow_executions_total"
        )
        assert counter is not None
        points = _data_points(counter)
        assert any(
            dict(dp.attributes).get("workflow.name") == "w1f-async-error"
            and dict(dp.attributes).get("success") == "false"
            for dp in points
        ), f"expected success=false sample, got {[dict(p.attributes) for p in points]}"
