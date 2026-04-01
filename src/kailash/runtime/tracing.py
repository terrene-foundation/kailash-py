# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Optional OpenTelemetry tracing for workflow execution.

Graceful degradation: if opentelemetry is not installed, all operations are no-ops.
Included in the base install (pip install kailash).

This module provides lightweight OpenTelemetry integration for the core SDK runtime.
It is independent of Kaizen's TracingManager (which targets Jaeger + HookContext).
Both can coexist: Kaizen traces agent-level hooks, this traces workflow/node execution.

Progressive configuration via ``TracingLevel``:

- ``NONE``:     No instrumentation (zero overhead).
- ``BASIC``:    Workflow-level spans only.
- ``DETAILED``: Workflow + node-level spans.
- ``FULL``:     Workflow + node + database + custom spans.

Configure via the ``KAILASH_TRACING_LEVEL`` environment variable or programmatically.

Example:
    >>> from kailash.runtime.tracing import get_workflow_tracer, TracingLevel
    >>> tracer = get_workflow_tracer()
    >>> if tracer.enabled:
    ...     span = tracer.start_workflow_span("wf-123", "my_workflow")
    ...     # ... execute workflow ...
    ...     tracer.end_span(span)
"""

from __future__ import annotations

import logging
import os
import threading
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "TracingLevel",
    "WorkflowTracer",
    "get_workflow_tracer",
    "configure_tracing",
]

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


class TracingLevel(Enum):
    """Progressive tracing configuration levels.

    Controls the granularity of OpenTelemetry instrumentation.

    Attributes:
        NONE:     No instrumentation.  All tracing methods are no-ops.
        BASIC:    Workflow-level spans only (start/end per workflow execution).
        DETAILED: Workflow + node-level spans (each node gets a child span).
        FULL:     Workflow + node + database + custom spans (maximum visibility).
    """

    NONE = "none"
    BASIC = "basic"
    DETAILED = "detailed"
    FULL = "full"


def _resolve_tracing_level() -> TracingLevel:
    """Resolve tracing level from the ``KAILASH_TRACING_LEVEL`` env var.

    Falls back to ``NONE`` if the variable is unset or has an unrecognised value.
    """
    default = "basic" if _OTEL_AVAILABLE else "none"
    raw = os.environ.get("KAILASH_TRACING_LEVEL", default).strip().lower()
    for level in TracingLevel:
        if level.value == raw:
            return level
    logger.warning("Unrecognised KAILASH_TRACING_LEVEL=%r; defaulting to NONE", raw)
    return TracingLevel.NONE


class WorkflowTracer:
    """Traces workflow execution with OpenTelemetry spans.

    When opentelemetry-api is not installed **or** the tracing level is ``NONE``,
    every method is a safe no-op that returns ``None`` for spans and performs no
    work.  This guarantees zero overhead in environments that do not opt into
    tracing.

    Attributes:
        enabled: Whether OpenTelemetry is available and tracing level is not NONE.
        level:   The active :class:`TracingLevel`.
    """

    def __init__(
        self,
        service_name: str = "kailash",
        level: Optional[TracingLevel] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._level: TracingLevel = (
            level if level is not None else _resolve_tracing_level()
        )
        self._service_name = service_name
        self._tracer: Any = None

        otel_active = _OTEL_AVAILABLE and self._level is not TracingLevel.NONE
        if otel_active and _trace is not None:
            self._tracer = _trace.get_tracer(service_name)
        self._enabled: bool = otel_active and self._tracer is not None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """Return True when OpenTelemetry is installed and tracing is active."""
        return self._enabled

    @property
    def level(self) -> TracingLevel:
        """Return the current tracing level."""
        return self._level

    @level.setter
    def level(self, new_level: TracingLevel) -> None:
        """Reconfigure the tracing level at runtime (thread-safe)."""
        with self._lock:
            self._level = new_level
            otel_active = _OTEL_AVAILABLE and new_level is not TracingLevel.NONE
            if otel_active and _trace is not None and self._tracer is None:
                self._tracer = _trace.get_tracer(self._service_name)
            self._enabled = otel_active and self._tracer is not None

    # ------------------------------------------------------------------
    # Span lifecycle
    # ------------------------------------------------------------------

    def start_workflow_span(
        self,
        workflow_id: str,
        workflow_name: str,
        run_id: str = "",
        tenant_id: str = "",
    ) -> Optional[Any]:
        """Start a span for the entire workflow execution.

        Args:
            workflow_id: Unique identifier for this workflow definition.
            workflow_name: Human-readable workflow name.
            run_id: Runtime-assigned execution run ID.
            tenant_id: Optional tenant identifier for multi-tenant deployments.

        Returns:
            An OpenTelemetry ``Span`` if tracing is enabled at BASIC or above,
            else ``None``.
        """
        if not self._enabled or self._tracer is None:
            return None
        if self._level is TracingLevel.NONE:
            return None

        attrs: dict[str, Any] = {
            "workflow.id": workflow_id,
            "workflow.name": workflow_name,
        }
        if run_id:
            attrs["workflow.run_id"] = run_id
        if tenant_id:
            attrs["tenant.id"] = tenant_id
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
            An OpenTelemetry ``Span`` if tracing is enabled at DETAILED or above,
            else ``None``.
        """
        if not self._enabled or self._tracer is None or _trace is None:
            return None
        if self._level not in (TracingLevel.DETAILED, TracingLevel.FULL):
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

    def start_db_span(
        self,
        operation: str,
        statement: str = "",
        db_system: str = "",
        parent_span: Optional[Any] = None,
    ) -> Optional[Any]:
        """Start a span for a database operation.

        Only active at ``TracingLevel.FULL``.

        Args:
            operation: The database operation (e.g. ``"SELECT"``, ``"INSERT"``).
            statement: The SQL statement (will be truncated to 1024 chars).
            db_system: Database system identifier (e.g. ``"sqlite"``, ``"postgresql"``).
            parent_span: Optional parent span for hierarchy.

        Returns:
            An OpenTelemetry ``Span`` if tracing level is FULL, else ``None``.
        """
        if not self._enabled or self._tracer is None or _trace is None:
            return None
        if self._level is not TracingLevel.FULL:
            return None

        ctx = _trace.set_span_in_context(parent_span) if parent_span else None
        attrs: dict[str, Any] = {
            "db.operation": operation,
        }
        if statement:
            attrs["db.statement"] = statement[:1024]
        if db_system:
            attrs["db.system"] = db_system
        span = self._tracer.start_span(
            f"db.{operation}",
            context=ctx,
            attributes=attrs,
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
_global_lock = threading.Lock()


def get_workflow_tracer() -> WorkflowTracer:
    """Return the module-level ``WorkflowTracer`` singleton.

    The instance is created lazily on first call and reused thereafter.
    Thread-safe via a module-level lock.
    """
    global _global_tracer
    if _global_tracer is None:
        with _global_lock:
            if _global_tracer is None:
                _global_tracer = WorkflowTracer()
    return _global_tracer


def configure_tracing(
    level: TracingLevel,
    service_name: str = "kailash",
) -> WorkflowTracer:
    """Configure the global tracer with the given level and service name.

    If the global tracer already exists its level is updated in-place.
    Otherwise a new tracer is created.

    Args:
        level: Desired tracing granularity.
        service_name: OpenTelemetry service name.

    Returns:
        The (re)configured global :class:`WorkflowTracer` singleton.
    """
    global _global_tracer
    with _global_lock:
        if _global_tracer is None:
            _global_tracer = WorkflowTracer(service_name=service_name, level=level)
        else:
            _global_tracer.level = level
    return _global_tracer
