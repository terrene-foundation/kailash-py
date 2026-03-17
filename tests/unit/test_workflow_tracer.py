# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for WorkflowTracer (TODO-014: OpenTelemetry integration).

These tests do NOT require opentelemetry to be installed.  They verify:

1. Graceful degradation when OTel is absent (all methods are safe no-ops).
2. Correct span lifecycle when OTel is present (mocked).
3. Singleton behaviour of ``get_workflow_tracer()``.
"""

from __future__ import annotations

import importlib
import sys
import types
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_import():
    """Re-import tracing module so module-level detection runs again."""
    mod_name = "kailash.runtime.tracing"
    # Clear cached module and singleton
    sys.modules.pop(mod_name, None)
    mod = importlib.import_module(mod_name)
    return mod


# ---------------------------------------------------------------------------
# Test group 1: Graceful degradation (OTel NOT installed)
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """All operations must be no-ops when opentelemetry is not installed."""

    def test_tracer_disabled_without_otel(self):
        """WorkflowTracer.enabled is False when OTel is absent."""
        # Temporarily hide opentelemetry from the import system
        with mock.patch.dict(
            sys.modules, {"opentelemetry": None, "opentelemetry.trace": None}
        ):
            mod = _fresh_import()
            tracer = mod.WorkflowTracer()
            assert tracer.enabled is False

    def test_start_workflow_span_returns_none(self):
        """start_workflow_span returns None when disabled."""
        with mock.patch.dict(
            sys.modules, {"opentelemetry": None, "opentelemetry.trace": None}
        ):
            mod = _fresh_import()
            tracer = mod.WorkflowTracer()
            span = tracer.start_workflow_span("wf-1", "test_workflow")
            assert span is None

    def test_start_node_span_returns_none(self):
        """start_node_span returns None when disabled."""
        with mock.patch.dict(
            sys.modules, {"opentelemetry": None, "opentelemetry.trace": None}
        ):
            mod = _fresh_import()
            tracer = mod.WorkflowTracer()
            span = tracer.start_node_span("node-1", "PythonCodeNode")
            assert span is None

    def test_end_span_noop_with_none(self):
        """end_span does nothing when span is None."""
        with mock.patch.dict(
            sys.modules, {"opentelemetry": None, "opentelemetry.trace": None}
        ):
            mod = _fresh_import()
            tracer = mod.WorkflowTracer()
            # Should not raise
            tracer.end_span(None)
            tracer.end_span(None, status="error", error=RuntimeError("boom"))

    def test_set_attribute_noop_with_none(self):
        """set_attribute does nothing when span is None."""
        with mock.patch.dict(
            sys.modules, {"opentelemetry": None, "opentelemetry.trace": None}
        ):
            mod = _fresh_import()
            tracer = mod.WorkflowTracer()
            # Should not raise
            tracer.set_attribute(None, "key", "value")


# ---------------------------------------------------------------------------
# Test group 2: OTel present (mocked)
# ---------------------------------------------------------------------------


def _build_mock_otel():
    """Build a fake opentelemetry module tree sufficient for WorkflowTracer."""
    # Create a mock tracer
    mock_tracer = mock.MagicMock()
    mock_span = mock.MagicMock()
    mock_tracer.start_span.return_value = mock_span

    # StatusCode enum
    status_code = types.SimpleNamespace(OK="OK", ERROR="ERROR")

    # trace module
    trace_mod = types.ModuleType("opentelemetry.trace")
    trace_mod.get_tracer = mock.MagicMock(return_value=mock_tracer)
    trace_mod.set_span_in_context = mock.MagicMock(return_value=mock.sentinel.ctx)
    trace_mod.StatusCode = status_code

    # opentelemetry top-level
    otel_mod = types.ModuleType("opentelemetry")
    otel_mod.trace = trace_mod

    return otel_mod, trace_mod, mock_tracer, mock_span, status_code


class TestWithOTel:
    """Verify correct OTel API usage when the library is present."""

    def _import_with_mock_otel(self):
        otel_mod, trace_mod, mock_tracer, mock_span, status_code = _build_mock_otel()
        with mock.patch.dict(
            sys.modules,
            {
                "opentelemetry": otel_mod,
                "opentelemetry.trace": trace_mod,
            },
        ):
            mod = _fresh_import()
            return mod, mock_tracer, mock_span, status_code

    def test_tracer_enabled(self):
        mod, _, _, _ = self._import_with_mock_otel()
        tracer = mod.WorkflowTracer(service_name="test-svc")
        assert tracer.enabled is True

    def test_start_workflow_span(self):
        mod, mock_tracer, mock_span, _ = self._import_with_mock_otel()
        tracer = mod.WorkflowTracer()
        span = tracer.start_workflow_span("wf-123", "my_workflow")

        assert span is mock_span
        mock_tracer.start_span.assert_called_once_with(
            "workflow.my_workflow",
            attributes={
                "workflow.id": "wf-123",
                "workflow.name": "my_workflow",
            },
        )

    def test_start_node_span_without_parent(self):
        mod, mock_tracer, mock_span, _ = self._import_with_mock_otel()
        tracer = mod.WorkflowTracer()
        # Reset from the workflow span call in __init__
        mock_tracer.start_span.reset_mock()

        span = tracer.start_node_span("node-1", "CSVReaderNode")
        assert span is mock_span
        mock_tracer.start_span.assert_called_once_with(
            "node.CSVReaderNode",
            context=None,
            attributes={
                "node.id": "node-1",
                "node.type": "CSVReaderNode",
            },
        )

    def test_start_node_span_with_parent(self):
        mod, mock_tracer, mock_span, _ = self._import_with_mock_otel()
        tracer = mod.WorkflowTracer()
        mock_tracer.start_span.reset_mock()

        parent = mock.MagicMock(name="parent_span")
        span = tracer.start_node_span("node-2", "PythonCodeNode", parent_span=parent)

        assert span is mock_span
        # set_span_in_context should have been called with the parent
        # The context kwarg should be the sentinel returned by set_span_in_context
        call_kwargs = mock_tracer.start_span.call_args
        assert call_kwargs[1]["context"] is not None

    def test_end_span_ok(self):
        mod, _, mock_span, status_code = self._import_with_mock_otel()
        tracer = mod.WorkflowTracer()
        tracer.end_span(mock_span, status="ok")

        mock_span.set_status.assert_called_with(status_code.OK)
        mock_span.end.assert_called_once()

    def test_end_span_error(self):
        mod, _, mock_span, status_code = self._import_with_mock_otel()
        tracer = mod.WorkflowTracer()
        err = ValueError("bad input")
        tracer.end_span(mock_span, error=err)

        mock_span.set_status.assert_called_with(status_code.ERROR, "bad input")
        mock_span.record_exception.assert_called_once_with(err)
        mock_span.end.assert_called_once()

    def test_set_attribute(self):
        mod, _, mock_span, _ = self._import_with_mock_otel()
        tracer = mod.WorkflowTracer()
        tracer.set_attribute(mock_span, "node.duration_s", 1.23)
        mock_span.set_attribute.assert_called_with("node.duration_s", 1.23)


# ---------------------------------------------------------------------------
# Test group 3: Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    """get_workflow_tracer() returns the same instance on repeated calls."""

    def test_returns_same_instance(self):
        with mock.patch.dict(
            sys.modules, {"opentelemetry": None, "opentelemetry.trace": None}
        ):
            mod = _fresh_import()
            # Reset the global singleton
            mod._global_tracer = None
            t1 = mod.get_workflow_tracer()
            t2 = mod.get_workflow_tracer()
            assert t1 is t2

    def test_singleton_is_workflow_tracer(self):
        with mock.patch.dict(
            sys.modules, {"opentelemetry": None, "opentelemetry.trace": None}
        ):
            mod = _fresh_import()
            mod._global_tracer = None
            t = mod.get_workflow_tracer()
            assert isinstance(t, mod.WorkflowTracer)
