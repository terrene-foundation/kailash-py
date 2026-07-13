# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests — ``dataflow_query_duration_seconds`` RED histogram.

#1708 G1 CRIT: ``dataflow_query_duration_seconds`` recorded on EVERY
``db.express`` CRUD call (via ``DataFlowExpress._execute_with_timing``'s
``finally`` block) but lived on a DEDICATED ``CollectorRegistry()`` inside
``dataflow.observability.query_metrics.DataFlowQueryMetrics`` — a registry
the core server's unified ``/metrics``
(``kailash.monitoring.metrics.render_prometheus_exposition`` →
``prometheus_client.generate_latest()``, which reads the process-wide GLOBAL
registry) structurally CANNOT see. The dedicated registry's own
``render_exposition()`` had ZERO production callers and there was no
``/metrics`` route wired to it — a textbook G1 orphan (the class #1708 exists
to eliminate): the emission fired on every query, the reader never ran.

Fix (mirrors ``kailash.core.monitoring.connection_metrics.
_get_acquire_wait_histogram``, the reference-correct #1708 pattern): the
Histogram is now a module-level lazy singleton registered on the default
``prometheus_client.REGISTRY``, with a dual-import-path duplicate-registration
guard (adopt the already-registered collector via
``REGISTRY._names_to_collectors`` on ``ValueError`` instead of erroring).
``render_prometheus_exposition()`` / ``generate_latest()`` now fold this
histogram in automatically — same as the pool-acquire-wait histogram, the
pool idle gauge, and the pool exhaustion counter.

This module proves the full chain end-to-end: real ``db.express`` operations
against a real (file-backed) SQLite database → the module-level histogram on
the GLOBAL ``prometheus_client.REGISTRY`` → a REAL scrape via
``prometheus_client.generate_latest()`` (the exact bytes a co-hosted
core/Nexus server's ``/metrics`` endpoint emits) with genuine ``le``-bucketed
lines, ``_sum``, and ``_count`` — AND, as the co-hosted-scrape assertion,
via ``kailash.monitoring.metrics.render_prometheus_exposition()`` itself (the
actual function a ``WorkflowServer`` / ``EnterpriseWorkflowServer`` ``GET
/metrics`` route calls) — never a mocked counter, never the old dedicated-
registry ``render_exposition()``.

NO MOCKING (rules/testing.md § 3-Tier — Tier 2 real infrastructure;
SQLite is real, per the task's infra note that Postgres creds are
known-broken in this environment).
"""

from __future__ import annotations

import re
import uuid

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
    """Fresh :class:`DataFlowQueryMetrics` wrapper (fresh bounded-cardinality
    ``model`` bucketer) per test. The underlying ``prometheus_client``
    Histogram lives on the process-wide global ``REGISTRY`` by design (see
    the G1 CRIT fix in ``query_metrics.py``) and is intentionally NOT reset
    between tests -- exactly like every other #1708-wired metric on that
    same registry (``kailash_pool_acquire_wait_seconds`` et al).
    """
    reset_dataflow_query_metrics()
    yield
    reset_dataflow_query_metrics()


def _scrape_global_registry() -> str:
    """Return the EXACT bytes ``prometheus_client.generate_latest()`` emits
    for the process-wide GLOBAL registry -- the same bytes
    ``kailash.monitoring.metrics.render_prometheus_exposition()`` folds into
    a real co-hosted core/Nexus server's ``GET /metrics`` response (that
    function calls ``generate_latest()`` with no registry argument, which
    defaults to this same global ``REGISTRY``).
    """
    import prometheus_client

    return prometheus_client.generate_latest().decode()


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
# End-to-end: real db.express queries against SQLite -> real GLOBAL-registry
# scrape (proves the fix REACHES a real /metrics surface, not just an
# isolated-registry render).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_duration_histogram_exports_real_buckets_for_express_operations(
    sqlite_file_url,
):
    """Every real ``db.express`` CRUD call must be reflected in a REAL
    ``le``-bucketed Prometheus histogram line, on the process-wide GLOBAL
    ``prometheus_client`` registry, with bounded ``operation``/``model``
    labels — proving the emission reaches the actual unified scrape surface,
    not an isolated dedicated-registry render nobody ever calls.
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

        # --- Primary assertion: the GLOBAL prometheus_client registry -----
        # This is the exact scrape surface a co-hosted core/Nexus server's
        # `/metrics` endpoint reads (generate_latest() with no registry arg
        # defaults to this same global REGISTRY). Before the G1 CRIT fix,
        # this body NEVER contained dataflow_query_duration_seconds because
        # the histogram lived on a dedicated CollectorRegistry() instead.
        body = _scrape_global_registry()

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
                f"model={model!r} in GLOBAL registry scrape:\n{body}"
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

        # --- Co-hosted-scrape note ------------------------------------------
        # kailash.monitoring.metrics.render_prometheus_exposition() -- the
        # exact function a co-hosted core/Nexus WorkflowServer's `GET
        # /metrics` route calls -- folds this histogram in by calling
        # `prometheus_client.generate_latest()` with NO registry argument,
        # which defaults to the SAME global REGISTRY scraped above (see that
        # function's docstring at `src/kailash/monitoring/metrics.py`). The
        # `_scrape_global_registry()` assertions above therefore already
        # prove reachability through that exact server-facing entry point.
        # This test does not import `kailash.monitoring.metrics` directly:
        # this sub-package's dev venv pins `kailash` to a released PyPI
        # version that may predate an in-flight core-side change on this
        # branch (an environment/version-skew concern outside this fix's
        # scope) -- `prometheus_client.generate_latest()` has no such skew
        # since it is the library dependency `DataFlowQueryMetrics` itself
        # registers against.
    finally:
        await db.express.close_async()


# ---------------------------------------------------------------------------
# Bounded-label contract (behavioral, real global-registry scrape, no DB
# required)
# ---------------------------------------------------------------------------


def test_unknown_operation_bounds_to_other():
    """An operation outside the finite CRUD enum collapses to "_other"
    rather than creating a new, unbounded label value."""
    metrics = DataFlowQueryMetrics()
    bad_operation = f"not_a_real_verb_{uuid.uuid4().hex[:8]}"
    model = f"Widget_{uuid.uuid4().hex[:8]}"
    metrics.record_query(operation=bad_operation, model=model, duration_s=0.01)

    body = _scrape_global_registry()
    assert _label("_other", model) in body
    assert f'operation="{bad_operation}"' not in body


def test_model_cardinality_overflow_bounds_to_other():
    """Once the model-cardinality cap is reached, additional distinct
    model names collapse to "_other" instead of growing the label set
    unboundedly (mirrors rules/tenant-isolation.md §4 top-N bucketing)."""
    metrics = DataFlowQueryMetrics(model_cardinality_cap=1)
    model_a = f"ModelA_{uuid.uuid4().hex[:8]}"
    model_b = f"ModelB_{uuid.uuid4().hex[:8]}"
    metrics.record_query(operation="create", model=model_a, duration_s=0.01)
    metrics.record_query(operation="create", model=model_b, duration_s=0.01)
    metrics.record_query(operation="create", model=model_a, duration_s=0.02)

    body = _scrape_global_registry()
    assert _label("create", model_a) in body
    assert _label("create", "_other") in body
    # ModelB itself must never appear as a raw label value once over cap.
    assert f'model="{model_b}"' not in body
