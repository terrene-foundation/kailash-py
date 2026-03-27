# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Node-level OpenTelemetry instrumentation.

Wraps individual node executions with child spans that capture:

- ``node.id``         -- The node's unique identifier.
- ``node.type``       -- The node class name.
- ``node.duration_s`` -- Execution wall-clock time in seconds.
- ``node.input_size`` -- Byte-length estimate of serialised inputs.
- ``node.output_size``-- Byte-length estimate of serialised outputs.

Active at :attr:`~kailash.runtime.tracing.TracingLevel.DETAILED` and above.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from kailash.runtime.tracing import TracingLevel, get_workflow_tracer

logger = logging.getLogger(__name__)

__all__ = ["NodeInstrumentor", "instrument_node"]

F = TypeVar("F", bound=Callable[..., Any])


def _estimate_size(obj: Any) -> int:
    """Return a rough byte-size estimate for *obj*.

    Uses ``sys.getsizeof`` as a fast, zero-dependency heuristic.  This is
    intentionally approximate -- the goal is order-of-magnitude awareness, not
    precision.
    """
    try:
        return sys.getsizeof(obj)
    except (TypeError, ValueError):
        return 0


class NodeInstrumentor:
    """Wraps node execution functions with OTel spans.

    Thread-safe.  When tracing is disabled or OTel is unavailable, the
    instrumented function runs with near-zero overhead (one ``if`` check).

    Example::

        instrumentor = NodeInstrumentor()
        result = instrumentor.execute(
            node_id="transform_1",
            node_type="PythonCodeNode",
            func=node.execute,
            args=(inputs,),
            parent_span=workflow_span,
        )
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def execute(
        self,
        node_id: str,
        node_type: str,
        func: Callable[..., Any],
        args: tuple[Any, ...] = (),
        kwargs: Optional[dict[str, Any]] = None,
        parent_span: Optional[Any] = None,
    ) -> Any:
        """Execute *func* inside an OTel span and return its result.

        If the tracer is not enabled at ``DETAILED`` or higher, *func* is
        called directly with no instrumentation overhead.

        Args:
            node_id:     Unique identifier for the node.
            node_type:   Class name / type label.
            func:        The callable to execute.
            args:        Positional arguments forwarded to *func*.
            kwargs:      Keyword arguments forwarded to *func*.
            parent_span: Optional parent span for hierarchy.

        Returns:
            Whatever *func* returns.

        Raises:
            Any exception raised by *func* (after recording it on the span).
        """
        kwargs = kwargs or {}
        tracer = get_workflow_tracer()

        if not tracer.enabled or tracer.level not in (
            TracingLevel.DETAILED,
            TracingLevel.FULL,
        ):
            return func(*args, **kwargs)

        span = tracer.start_node_span(node_id, node_type, parent_span=parent_span)
        start = time.monotonic()
        try:
            tracer.set_attribute(span, "node.input_size", _estimate_size(args))
            result = func(*args, **kwargs)
            duration = time.monotonic() - start
            tracer.set_attribute(span, "node.duration_s", round(duration, 6))
            tracer.set_attribute(span, "node.output_size", _estimate_size(result))
            tracer.end_span(span, status="ok")
            return result
        except Exception as exc:
            duration = time.monotonic() - start
            tracer.set_attribute(span, "node.duration_s", round(duration, 6))
            tracer.end_span(span, error=exc)
            raise


def instrument_node(
    node_id: str,
    node_type: str,
    parent_span: Optional[Any] = None,
) -> Callable[[F], F]:
    """Decorator that instruments a function as a node execution.

    Example::

        @instrument_node("etl_step", "PythonCodeNode")
        def etl_step(data):
            ...
    """
    _instrumentor = NodeInstrumentor()

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return _instrumentor.execute(
                node_id=node_id,
                node_type=node_type,
                func=func,
                args=args,
                kwargs=kwargs,
                parent_span=parent_span,
            )

        return wrapper  # type: ignore[return-value]

    return decorator
