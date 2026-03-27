# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for S5 OpenTelemetry tracing enhancement.

Covers:
- TracingLevel configuration and env-var resolution.
- WorkflowTracer span lifecycle at each level.
- NodeInstrumentor wrapping and attribute recording.
- DataFlowInstrumentor query tracing.
- DatabaseInstrumentor auto-instrumentation.
- MetricsBridge recording methods.

All tests work regardless of whether ``opentelemetry`` is installed:
when absent the tests verify graceful no-op behaviour.
"""

from __future__ import annotations

import os
import sys
import threading
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers — detect whether OTel is available
# ---------------------------------------------------------------------------
def _otel_available() -> bool:
    try:
        import opentelemetry  # noqa: F401

        return True
    except ImportError:
        return False


HAS_OTEL = _otel_available()


# ---------------------------------------------------------------------------
# TracingLevel
# ---------------------------------------------------------------------------


class TestTracingLevel:
    """TracingLevel enum and env-var resolution."""

    def test_enum_values(self) -> None:
        from kailash.runtime.tracing import TracingLevel

        assert TracingLevel.NONE.value == "none"
        assert TracingLevel.BASIC.value == "basic"
        assert TracingLevel.DETAILED.value == "detailed"
        assert TracingLevel.FULL.value == "full"

    def test_resolve_from_env_basic(self) -> None:
        from kailash.runtime.tracing import _resolve_tracing_level, TracingLevel

        with patch.dict(os.environ, {"KAILASH_TRACING_LEVEL": "basic"}):
            assert _resolve_tracing_level() is TracingLevel.BASIC

    def test_resolve_from_env_full(self) -> None:
        from kailash.runtime.tracing import _resolve_tracing_level, TracingLevel

        with patch.dict(os.environ, {"KAILASH_TRACING_LEVEL": "full"}):
            assert _resolve_tracing_level() is TracingLevel.FULL

    def test_resolve_from_env_unknown_defaults_to_none(self) -> None:
        from kailash.runtime.tracing import _resolve_tracing_level, TracingLevel

        with patch.dict(os.environ, {"KAILASH_TRACING_LEVEL": "turbo"}):
            assert _resolve_tracing_level() is TracingLevel.NONE

    def test_resolve_unset_defaults_based_on_otel(self) -> None:
        from kailash.runtime.tracing import (
            _OTEL_AVAILABLE,
            _resolve_tracing_level,
            TracingLevel,
        )

        env = os.environ.copy()
        env.pop("KAILASH_TRACING_LEVEL", None)
        with patch.dict(os.environ, env, clear=True):
            level = _resolve_tracing_level()
            # Defaults to BASIC when OTel is available (backward compat), NONE otherwise
            expected = TracingLevel.BASIC if _OTEL_AVAILABLE else TracingLevel.NONE
            assert level is expected


# ---------------------------------------------------------------------------
# WorkflowTracer — without OTel
# ---------------------------------------------------------------------------


class TestWorkflowTracerNoOtel:
    """WorkflowTracer behaviour when OTel is *not* available."""

    def test_disabled_when_otel_missing(self) -> None:
        from kailash.runtime import tracing as mod

        original = mod._OTEL_AVAILABLE
        try:
            mod._OTEL_AVAILABLE = False
            tracer = mod.WorkflowTracer(level=mod.TracingLevel.FULL)
            assert tracer.enabled is False
            assert tracer.start_workflow_span("wf", "name") is None
            assert tracer.start_node_span("n", "T") is None
            assert tracer.start_db_span("SELECT") is None
            tracer.end_span(None)
            tracer.set_attribute(None, "k", "v")
        finally:
            mod._OTEL_AVAILABLE = original

    def test_none_level_disables_even_with_otel(self) -> None:
        from kailash.runtime.tracing import TracingLevel, WorkflowTracer

        tracer = WorkflowTracer(level=TracingLevel.NONE)
        assert tracer.level is TracingLevel.NONE
        # Even if OTel is installed, NONE means no spans
        assert tracer.start_workflow_span("wf", "name") is None


# ---------------------------------------------------------------------------
# WorkflowTracer — with OTel (skip if not installed)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_OTEL, reason="opentelemetry not installed")
class TestWorkflowTracerWithOtel:
    """WorkflowTracer behaviour when OTel *is* available."""

    def test_basic_creates_workflow_spans(self) -> None:
        from kailash.runtime.tracing import TracingLevel, WorkflowTracer

        tracer = WorkflowTracer(level=TracingLevel.BASIC)
        assert tracer.enabled is True
        span = tracer.start_workflow_span("wf-1", "test_wf", run_id="run-1")
        assert span is not None
        tracer.end_span(span)

    def test_basic_skips_node_spans(self) -> None:
        from kailash.runtime.tracing import TracingLevel, WorkflowTracer

        tracer = WorkflowTracer(level=TracingLevel.BASIC)
        assert tracer.start_node_span("n1", "SomeNode") is None

    def test_detailed_creates_node_spans(self) -> None:
        from kailash.runtime.tracing import TracingLevel, WorkflowTracer

        tracer = WorkflowTracer(level=TracingLevel.DETAILED)
        span = tracer.start_node_span("n1", "PythonCodeNode")
        assert span is not None
        tracer.end_span(span)

    def test_detailed_skips_db_spans(self) -> None:
        from kailash.runtime.tracing import TracingLevel, WorkflowTracer

        tracer = WorkflowTracer(level=TracingLevel.DETAILED)
        assert tracer.start_db_span("SELECT") is None

    def test_full_creates_db_spans(self) -> None:
        from kailash.runtime.tracing import TracingLevel, WorkflowTracer

        tracer = WorkflowTracer(level=TracingLevel.FULL)
        span = tracer.start_db_span("SELECT", statement="SELECT 1", db_system="sqlite")
        assert span is not None
        tracer.end_span(span)

    def test_end_span_records_error(self) -> None:
        from kailash.runtime.tracing import TracingLevel, WorkflowTracer

        tracer = WorkflowTracer(level=TracingLevel.BASIC)
        span = tracer.start_workflow_span("wf", "err_test")
        assert span is not None
        tracer.end_span(span, error=ValueError("boom"))

    def test_set_attribute(self) -> None:
        from kailash.runtime.tracing import TracingLevel, WorkflowTracer

        tracer = WorkflowTracer(level=TracingLevel.BASIC)
        span = tracer.start_workflow_span("wf", "attr_test")
        tracer.set_attribute(span, "custom.key", "custom_value")
        tracer.end_span(span)

    def test_tenant_id_attribute(self) -> None:
        from kailash.runtime.tracing import TracingLevel, WorkflowTracer

        tracer = WorkflowTracer(level=TracingLevel.BASIC)
        span = tracer.start_workflow_span("wf", "tenant_test", tenant_id="tenant-42")
        assert span is not None
        tracer.end_span(span)

    def test_level_setter_thread_safe(self) -> None:
        from kailash.runtime.tracing import TracingLevel, WorkflowTracer

        tracer = WorkflowTracer(level=TracingLevel.NONE)
        assert tracer.enabled is False

        tracer.level = TracingLevel.FULL
        assert tracer.level is TracingLevel.FULL
        assert tracer.enabled is True

        tracer.level = TracingLevel.NONE
        assert tracer.enabled is False


# ---------------------------------------------------------------------------
# configure_tracing / get_workflow_tracer
# ---------------------------------------------------------------------------


class TestConfigureTracing:
    """Global configuration helpers."""

    def test_configure_creates_singleton(self) -> None:
        from kailash.runtime import tracing as mod

        # Reset global state for isolation
        old = mod._global_tracer
        mod._global_tracer = None
        try:
            result = mod.configure_tracing(mod.TracingLevel.BASIC)
            assert result is mod.get_workflow_tracer()
            assert result.level is mod.TracingLevel.BASIC
        finally:
            mod._global_tracer = old

    def test_configure_updates_existing(self) -> None:
        from kailash.runtime import tracing as mod

        old = mod._global_tracer
        mod._global_tracer = None
        try:
            first = mod.configure_tracing(mod.TracingLevel.BASIC)
            second = mod.configure_tracing(mod.TracingLevel.FULL)
            assert first is second
            assert first.level is mod.TracingLevel.FULL
        finally:
            mod._global_tracer = old


# ---------------------------------------------------------------------------
# NodeInstrumentor
# ---------------------------------------------------------------------------


class TestNodeInstrumentor:
    """Node-level instrumentation."""

    def test_passthrough_when_disabled(self) -> None:
        from kailash.runtime import tracing as mod
        from kailash.runtime.instrumentation.nodes import NodeInstrumentor

        old = mod._global_tracer
        mod._global_tracer = mod.WorkflowTracer(level=mod.TracingLevel.NONE)
        try:
            inst = NodeInstrumentor()
            result = inst.execute(
                node_id="n1",
                node_type="TestNode",
                func=lambda x: x * 2,
                args=(21,),
            )
            assert result == 42
        finally:
            mod._global_tracer = old

    def test_propagates_exception(self) -> None:
        from kailash.runtime import tracing as mod
        from kailash.runtime.instrumentation.nodes import NodeInstrumentor

        old = mod._global_tracer
        mod._global_tracer = mod.WorkflowTracer(level=mod.TracingLevel.NONE)
        try:
            inst = NodeInstrumentor()

            def boom() -> None:
                raise RuntimeError("test error")

            with pytest.raises(RuntimeError, match="test error"):
                inst.execute(node_id="n1", node_type="T", func=boom)
        finally:
            mod._global_tracer = old

    @pytest.mark.skipif(not HAS_OTEL, reason="opentelemetry not installed")
    def test_creates_span_at_detailed(self) -> None:
        from kailash.runtime import tracing as mod
        from kailash.runtime.instrumentation.nodes import NodeInstrumentor

        old = mod._global_tracer
        mod._global_tracer = mod.WorkflowTracer(level=mod.TracingLevel.DETAILED)
        try:
            inst = NodeInstrumentor()
            result = inst.execute(
                node_id="n1",
                node_type="PythonCodeNode",
                func=lambda: "hello",
            )
            assert result == "hello"
        finally:
            mod._global_tracer = old

    def test_decorator_instrument_node(self) -> None:
        from kailash.runtime import tracing as mod
        from kailash.runtime.instrumentation.nodes import instrument_node

        old = mod._global_tracer
        mod._global_tracer = mod.WorkflowTracer(level=mod.TracingLevel.NONE)
        try:

            @instrument_node("step1", "PythonCodeNode")
            def my_step(x: int) -> int:
                return x + 1

            assert my_step(10) == 11
        finally:
            mod._global_tracer = old


# ---------------------------------------------------------------------------
# DataFlowInstrumentor
# ---------------------------------------------------------------------------


class TestDataFlowInstrumentor:
    """DataFlow query tracing."""

    def test_passthrough_when_not_full(self) -> None:
        from kailash.runtime import tracing as mod
        from kailash.runtime.instrumentation.dataflow import DataFlowInstrumentor

        old = mod._global_tracer
        mod._global_tracer = mod.WorkflowTracer(level=mod.TracingLevel.DETAILED)
        try:
            inst = DataFlowInstrumentor(db_system="sqlite")
            result = inst.trace_query(
                statement="SELECT 1",
                execute_fn=lambda: [{"a": 1}],
            )
            assert result == [{"a": 1}]
        finally:
            mod._global_tracer = old

    @pytest.mark.skipif(not HAS_OTEL, reason="opentelemetry not installed")
    def test_traces_query_at_full(self) -> None:
        from kailash.runtime import tracing as mod
        from kailash.runtime.instrumentation.dataflow import DataFlowInstrumentor

        old = mod._global_tracer
        mod._global_tracer = mod.WorkflowTracer(level=mod.TracingLevel.FULL)
        try:
            inst = DataFlowInstrumentor(db_system="postgresql")
            result = inst.trace_query(
                statement="SELECT id FROM users WHERE active = ?",
                execute_fn=lambda: [{"id": 1}, {"id": 2}],
            )
            assert len(result) == 2
        finally:
            mod._global_tracer = old

    def test_propagates_query_error(self) -> None:
        from kailash.runtime import tracing as mod
        from kailash.runtime.instrumentation.dataflow import DataFlowInstrumentor

        old = mod._global_tracer
        mod._global_tracer = mod.WorkflowTracer(level=mod.TracingLevel.NONE)
        try:
            inst = DataFlowInstrumentor()

            def fail() -> None:
                raise ConnectionError("db down")

            with pytest.raises(ConnectionError, match="db down"):
                inst.trace_query(statement="SELECT 1", execute_fn=fail)
        finally:
            mod._global_tracer = old

    def test_count_rows_list(self) -> None:
        from kailash.runtime.instrumentation.dataflow import DataFlowInstrumentor

        assert DataFlowInstrumentor._count_rows([1, 2, 3]) == 3

    def test_count_rows_none(self) -> None:
        from kailash.runtime.instrumentation.dataflow import DataFlowInstrumentor

        assert DataFlowInstrumentor._count_rows(None) == 0

    def test_count_rows_unknown(self) -> None:
        from kailash.runtime.instrumentation.dataflow import DataFlowInstrumentor

        assert DataFlowInstrumentor._count_rows("not a result") is None


# ---------------------------------------------------------------------------
# DatabaseInstrumentor
# ---------------------------------------------------------------------------


class TestDatabaseInstrumentor:
    """Auto-instrumentation for ConnectionManager-like objects."""

    def _make_fake_conn(self) -> Any:
        """Create a fake connection manager with execute/fetchone/fetchall."""

        class FakeConn:
            def execute(self, sql: str, *args: Any) -> int:
                return 1

            def fetchone(self, sql: str, *args: Any) -> Optional[dict[str, Any]]:
                return {"id": 1}

            def fetchall(self, sql: str, *args: Any) -> list[dict[str, Any]]:
                return [{"id": 1}, {"id": 2}]

        return FakeConn()

    def test_instrument_and_uninstrument(self) -> None:
        from kailash.runtime import tracing as mod
        from kailash.runtime.instrumentation.database import DatabaseInstrumentor

        old = mod._global_tracer
        mod._global_tracer = mod.WorkflowTracer(level=mod.TracingLevel.NONE)
        try:
            conn = self._make_fake_conn()
            inst = DatabaseInstrumentor(db_system="sqlite")

            inst.instrument(conn)
            assert getattr(conn, "_kailash_otel_instrumented", False) is True
            # Methods still work
            assert conn.execute("INSERT INTO t VALUES (?)") == 1
            assert conn.fetchone("SELECT 1") == {"id": 1}
            assert len(conn.fetchall("SELECT *")) == 2

            inst.uninstrument(conn)
            assert getattr(conn, "_kailash_otel_instrumented", False) is False
            # Methods restored
            assert conn.execute("INSERT INTO t VALUES (?)") == 1
        finally:
            mod._global_tracer = old

    def test_double_instrument_is_noop(self) -> None:
        from kailash.runtime import tracing as mod
        from kailash.runtime.instrumentation.database import DatabaseInstrumentor

        old = mod._global_tracer
        mod._global_tracer = mod.WorkflowTracer(level=mod.TracingLevel.NONE)
        try:
            conn = self._make_fake_conn()
            inst = DatabaseInstrumentor()
            inst.instrument(conn)
            inst.instrument(conn)  # Should not raise or double-wrap
            assert conn.execute("SELECT 1") == 1
            inst.uninstrument(conn)
        finally:
            mod._global_tracer = old

    def test_uninstrument_without_instrument_is_safe(self) -> None:
        from kailash.runtime.instrumentation.database import DatabaseInstrumentor

        conn = self._make_fake_conn()
        inst = DatabaseInstrumentor()
        inst.uninstrument(conn)  # Should not raise

    @pytest.mark.skipif(not HAS_OTEL, reason="opentelemetry not installed")
    def test_spans_created_at_full(self) -> None:
        from kailash.runtime import tracing as mod
        from kailash.runtime.instrumentation.database import DatabaseInstrumentor

        old = mod._global_tracer
        mod._global_tracer = mod.WorkflowTracer(level=mod.TracingLevel.FULL)
        try:
            conn = self._make_fake_conn()
            inst = DatabaseInstrumentor(db_system="sqlite")
            inst.instrument(conn)
            result = conn.fetchall("SELECT * FROM users")
            assert len(result) == 2
            inst.uninstrument(conn)
        finally:
            mod._global_tracer = old


# ---------------------------------------------------------------------------
# MetricsBridge
# ---------------------------------------------------------------------------


class TestMetricsBridge:
    """Prometheus metrics bridge."""

    def test_noop_when_otel_missing(self) -> None:
        from kailash.runtime import metrics as mod

        original = mod._OTEL_METRICS_AVAILABLE
        try:
            mod._OTEL_METRICS_AVAILABLE = False
            bridge = mod.MetricsBridge()
            assert bridge.enabled is False
            # All methods are safe no-ops
            bridge.record_workflow_start("wf")
            bridge.record_workflow_duration("wf", 1.5)
            bridge.record_node_duration("n1", "T", 0.5)
        finally:
            mod._OTEL_METRICS_AVAILABLE = original

    @pytest.mark.skipif(not HAS_OTEL, reason="opentelemetry not installed")
    def test_enabled_with_otel(self) -> None:
        from kailash.runtime.metrics import MetricsBridge

        bridge = MetricsBridge()
        assert bridge.enabled is True

    @pytest.mark.skipif(not HAS_OTEL, reason="opentelemetry not installed")
    def test_record_workflow_start(self) -> None:
        from kailash.runtime.metrics import MetricsBridge

        bridge = MetricsBridge()
        bridge.record_workflow_start("test_wf", tenant_id="t-1")

    @pytest.mark.skipif(not HAS_OTEL, reason="opentelemetry not installed")
    def test_record_workflow_duration(self) -> None:
        from kailash.runtime.metrics import MetricsBridge

        bridge = MetricsBridge()
        bridge.record_workflow_duration("test_wf", 2.5, status="ok")

    @pytest.mark.skipif(not HAS_OTEL, reason="opentelemetry not installed")
    def test_record_node_duration(self) -> None:
        from kailash.runtime.metrics import MetricsBridge

        bridge = MetricsBridge()
        bridge.record_node_duration("n1", "PythonCodeNode", 0.42, status="ok")

    @pytest.mark.skipif(not HAS_OTEL, reason="opentelemetry not installed")
    def test_record_workflow_duration_error(self) -> None:
        from kailash.runtime.metrics import MetricsBridge

        bridge = MetricsBridge()
        bridge.record_workflow_duration("fail_wf", 0.1, status="error")

    def test_singleton_get_metrics_bridge(self) -> None:
        from kailash.runtime import metrics as mod

        old = mod._global_bridge
        mod._global_bridge = None
        try:
            b1 = mod.get_metrics_bridge()
            b2 = mod.get_metrics_bridge()
            assert b1 is b2
        finally:
            mod._global_bridge = old


# ---------------------------------------------------------------------------
# Thread-safety smoke tests
# ---------------------------------------------------------------------------


class TestThreadSafety:
    """Verify key components are safe under concurrent access."""

    def test_concurrent_tracer_level_changes(self) -> None:
        from kailash.runtime.tracing import TracingLevel, WorkflowTracer

        tracer = WorkflowTracer(level=TracingLevel.NONE)
        errors: list[Exception] = []

        def toggle(level: TracingLevel) -> None:
            try:
                for _ in range(50):
                    tracer.level = level
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=toggle, args=(TracingLevel.FULL,)),
            threading.Thread(target=toggle, args=(TracingLevel.NONE,)),
            threading.Thread(target=toggle, args=(TracingLevel.BASIC,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert errors == [], f"Thread errors: {errors}"

    def test_concurrent_node_instrumentation(self) -> None:
        from kailash.runtime import tracing as mod
        from kailash.runtime.instrumentation.nodes import NodeInstrumentor

        old = mod._global_tracer
        mod._global_tracer = mod.WorkflowTracer(level=mod.TracingLevel.NONE)
        try:
            inst = NodeInstrumentor()
            results: list[int] = []
            errors: list[Exception] = []

            def run_node(val: int) -> None:
                try:
                    r = inst.execute(
                        node_id=f"n-{val}",
                        node_type="TestNode",
                        func=lambda v: v * 2,
                        args=(val,),
                    )
                    results.append(r)
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=run_node, args=(i,)) for i in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)
            assert errors == []
            assert sorted(results) == [i * 2 for i in range(10)]
        finally:
            mod._global_tracer = old
