# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Optional OpenTelemetry tracing for workflow execution.

Graceful degradation: if opentelemetry is not installed, all operations are no-ops.
Install with: pip install kailash[otel]

This module provides lightweight OpenTelemetry integration for the core SDK runtime.
It is independent of Kaizen's TracingManager (which targets Jaeger + HookContext).
Both can coexist: Kaizen traces agent-level hooks, this traces workflow/node execution.

Example:
    >>> from kailash.runtime.tracing import get_workflow_tracer
    >>> tracer = get_workflow_tracer()
    >>> if tracer.enabled:
    ...     span = tracer.start_workflow_span("wf-123", "my_workflow")
    ...     # ... execute workflow ...
    ...     tracer.end_span(span)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = ["WorkflowTracer", "get_workflow_tracer"]

# Graceful degradation: if opentelemetry-api is not installed, all tracing is no-op.
_OTEL_AVAILABLE = False
_trace = None
_StatusCode = None

try:
    from opentelemetry import trace as _trace_module
    from opentelemetry.trace import StatusCode as _StatusCodeClass

    _trace = _trace_module
    _StatusCode = _StatusCodeClass
    _OTEL_AVAILABLE = True
except ImportError:
    pass


class WorkflowTracer:
    """Traces workflow execution with OpenTelemetry spans.

    When opentelemetry-api is not installed, every method is a safe no-op that
    returns ``None`` for spans and performs no work.  This guarantees zero overhead
    in environments that do not opt into tracing.

    Attributes:
        enabled: Whether OpenTelemetry is available and the tracer is active.
    """

    def __init__(self, service_name: str = "kailash") -> None:
        self._enabled: bool = _OTEL_AVAILABLE
        self._tracer: Any = None
        if self._enabled and _trace is not None:
            self._tracer = _trace.get_tracer(service_name)

    @property
    def enabled(self) -> bool:
        """Return True when OpenTelemetry is installed and the tracer is active."""
        return self._enabled

    # ------------------------------------------------------------------
    # Span lifecycle
    # ------------------------------------------------------------------

    def start_workflow_span(
        self,
        workflow_id: str,
        workflow_name: str,
        run_id: str = "",
    ) -> Optional[Any]:
        """Start a span for the entire workflow execution.

        Args:
            workflow_id: Unique identifier for this workflow run.
            workflow_name: Human-readable workflow name.
            run_id: Runtime-assigned execution run ID.

        Returns:
            An OpenTelemetry ``Span`` if tracing is enabled, else ``None``.
        """
        if not self._enabled or self._tracer is None:
            return None
        attrs = {
            "workflow.id": workflow_id,
            "workflow.name": workflow_name,
        }
        if run_id:
            attrs["workflow.run_id"] = run_id
        span = self._tracer.start_span(
            f"workflow.{workflow_name}",
            attributes=attrs,
        )
        return span

    def start_node_span(
        self,
        node_id: str,
        node_type: str,
        parent_span: Optional[Any] = None,
    ) -> Optional[Any]:
        """Start a span for a single node execution within a workflow.

        If *parent_span* is provided the new span is created as a child, forming
        the expected workflow -> node hierarchy in trace viewers.

        Args:
            node_id: The node's unique identifier within the workflow.
            node_type: Class name of the node (e.g. ``"PythonCodeNode"``).
            parent_span: Optional parent span for hierarchy.

        Returns:
            An OpenTelemetry ``Span`` if tracing is enabled, else ``None``.
        """
        if not self._enabled or self._tracer is None or _trace is None:
            return None
        ctx = _trace.set_span_in_context(parent_span) if parent_span else None
        span = self._tracer.start_span(
            f"node.{node_type}",
            context=ctx,
            attributes={
                "node.id": node_id,
                "node.type": node_type,
            },
        )
        return span

    def end_span(
        self,
        span: Optional[Any],
        status: str = "ok",
        error: Optional[Exception] = None,
    ) -> None:
        """End a span, optionally recording an error.

        Args:
            span: The span to end.  ``None`` is silently ignored.
            status: ``"ok"`` (default) or ``"error"``.
            error: If provided, the exception is recorded on the span and the
                status is set to ``ERROR`` regardless of *status*.
        """
        if not self._enabled or span is None or _StatusCode is None:
            return
        if error is not None:
            span.set_status(_StatusCode.ERROR, str(error))
            span.record_exception(error)
        elif status == "ok":
            span.set_status(_StatusCode.OK)
        span.end()

    def set_attribute(
        self,
        span: Optional[Any],
        key: str,
        value: Any,
    ) -> None:
        """Set an attribute on a span.

        Args:
            span: Target span.  ``None`` is silently ignored.
            key: Attribute key (should follow OpenTelemetry semantic conventions).
            value: Attribute value (must be a primitive: str, int, float, bool).
        """
        if not self._enabled or span is None:
            return
        span.set_attribute(key, value)


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_global_tracer: Optional[WorkflowTracer] = None


def get_workflow_tracer() -> WorkflowTracer:
    """Return the module-level ``WorkflowTracer`` singleton.

    The instance is created lazily on first call and reused thereafter.
    """
    global _global_tracer
    if _global_tracer is None:
        _global_tracer = WorkflowTracer()
    return _global_tracer
