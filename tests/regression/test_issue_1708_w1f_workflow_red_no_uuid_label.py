# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: #1708 W1f — canonical workflow RED metrics never carry an
unbounded workflow_id / UUID-shaped label.

Wave 1d fixed this exact cardinality bomb on the ORPHANED
``EnterpriseMonitoringManager.record_workflow_execution`` (``workflow_id``
recorded as a Prometheus label / DataDog tag). Wave 1f wires the REAL,
hot-path RED metrics through the OTel ``MetricsBridge``
(``LocalRuntime.execute`` / ``AsyncLocalRuntime.execute_workflow_async``) —
this regression pins the SAME bounded-label invariant at the new call site,
including the subtler footgun this wave discovered: ``WorkflowBuilder.build()``
defaults an UNNAMED workflow's ``name`` to ``f"Workflow-{workflow_id[:8]}"``
— an 8-hex-char fragment of a fresh ``uuid4()`` minted on *every* ``.build()``
call. Recording that fragment verbatim would mint a brand-new time series on
every anonymous workflow execution, the same unbounded-cardinality shape as
the raw ``workflow_id`` even though it is a different field.
"""

from __future__ import annotations

import re
import uuid

import pytest

pytest.importorskip("opentelemetry.sdk.metrics", reason="requires kailash[telemetry]")

from opentelemetry.sdk.metrics import MeterProvider  # noqa: E402
from opentelemetry.sdk.metrics.export import InMemoryMetricReader  # noqa: E402

import kailash.runtime.metrics as metrics_mod  # noqa: E402
from kailash.runtime.local import LocalRuntime  # noqa: E402
from kailash.workflow.builder import WorkflowBuilder  # noqa: E402

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_AUTO_GENERATED_NAME_RE = re.compile(r"^Workflow-[0-9a-fA-F]{8}$")


@pytest.fixture
def isolated_meter_reader(monkeypatch):
    """Real, isolated OTel MeterProvider + InMemoryMetricReader.

    See ``tests/integration/test_workflow_red_metrics_wiring.py`` for the
    full rationale (OTel's global ``set_meter_provider`` is a do-once
    guard; this fixture redirects MetricsBridge's meter-resolution call
    directly rather than racing that global).
    """
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(metrics_mod._metrics_mod, "get_meter", provider.get_meter)
    monkeypatch.setattr(metrics_mod, "_global_bridge", None)
    yield reader
    monkeypatch.setattr(metrics_mod, "_global_bridge", None)


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


@pytest.mark.regression
def test_sanitize_workflow_name_collapses_auto_generated_fragment() -> None:
    """Behavioral: the exact WorkflowBuilder default-name shape collapses to
    the bounded sentinel; explicitly-named workflows pass through unchanged."""
    workflow_id = str(uuid.uuid4())
    auto_name = f"Workflow-{workflow_id[:8]}"

    assert metrics_mod.sanitize_workflow_name(auto_name) == "unnamed_workflow"
    assert metrics_mod.sanitize_workflow_name("orders-pipeline") == "orders-pipeline"
    assert metrics_mod.sanitize_workflow_name("") == "unnamed_workflow"
    assert metrics_mod.sanitize_workflow_name(None) == "unnamed_workflow"


@pytest.mark.regression
def test_unnamed_workflow_execution_emits_bounded_label_not_uuid_fragment(
    isolated_meter_reader,
) -> None:
    """An unnamed workflow's auto-generated ``Workflow-{uuid[:8]}`` name MUST
    NOT reach the metric attributes verbatim -- every real execution would
    otherwise mint a brand-new time series (#1708's exact cardinality bomb,
    landing at the canonical hot-path wiring instead of the orphaned
    enterprise adapter Wave 1d fixed)."""
    builder = WorkflowBuilder()
    builder.add_node("PythonCodeNode", "n", {"code": 'result = {"ok": True}'})
    workflow = builder.build()  # no name kwarg -> auto-generated per-build name

    assert _AUTO_GENERATED_NAME_RE.match(workflow.name), (
        "test premise broken: WorkflowBuilder no longer auto-generates "
        f"Workflow-<uuid8> names (got {workflow.name!r})"
    )

    with LocalRuntime() as runtime:
        runtime.execute(workflow)

    values = _all_attribute_strings(
        isolated_meter_reader, "kailash_workflow_executions_total"
    )
    assert values, "kailash_workflow_executions_total not recorded"
    assert "unnamed_workflow" in values

    for value in values:
        assert not _AUTO_GENERATED_NAME_RE.match(
            value
        ), f"unsanitized auto-generated workflow name leaked: {value}"
        assert not _UUID_RE.search(value), f"full UUID-shaped label leaked: {value}"
        assert value != workflow.workflow_id, "raw workflow_id leaked as a label value"


@pytest.mark.regression
def test_no_workflow_id_or_uuid_shaped_label_across_red_metrics(
    isolated_meter_reader,
) -> None:
    """Cardinality guard across BOTH RED metrics (counter + histogram) for
    both a NAMED workflow (sanity check) and an UNNAMED one (the real
    unbounded-cardinality risk this wave discovered)."""
    for explicit_name in (None, "orders-pipeline"):
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "n", {"code": 'result = {"ok": True}'})
        kwargs = {"name": explicit_name} if explicit_name else {}
        workflow = builder.build(**kwargs)

        with LocalRuntime() as runtime:
            runtime.execute(workflow)

    for metric_name in (
        "kailash_workflow_executions_total",
        "kailash_workflow_duration_seconds",
    ):
        values = _all_attribute_strings(isolated_meter_reader, metric_name)
        assert values, f"{metric_name} not recorded"
        for value in values:
            assert (
                "workflow_id" not in value
            ), f"workflow_id key/value leaked in {metric_name}: {value}"
            assert not _UUID_RE.search(
                value
            ), f"UUID-shaped value leaked in {metric_name}: {value}"
            assert not _AUTO_GENERATED_NAME_RE.match(
                value
            ), f"unsanitized auto-generated name leaked in {metric_name}: {value}"
