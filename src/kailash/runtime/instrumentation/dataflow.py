# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""DataFlow query tracing with OpenTelemetry semantic conventions.

Instruments DataFlow database operations with OTel spans following the
`OpenTelemetry Database semantic conventions
<https://opentelemetry.io/docs/specs/semconv/database/>`_:

- ``db.system``    -- Database system identifier (``sqlite``, ``postgresql``, etc.).
- ``db.statement`` -- SQL statement text (truncated to 1024 chars).
- ``db.operation`` -- High-level operation (``SELECT``, ``INSERT``, ...).
- ``db.row_count`` -- Number of rows returned / affected.
- ``db.duration_s``-- Query wall-clock time in seconds.

Active only at :attr:`~kailash.runtime.tracing.TracingLevel.FULL`.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Callable, Optional

from kailash.runtime.tracing import TracingLevel, get_workflow_tracer

logger = logging.getLogger(__name__)

__all__ = ["DataFlowInstrumentor"]

_SQL_OP_RE = re.compile(r"^\s*(\w+)", re.IGNORECASE)
_MAX_STATEMENT_LEN = 1024


def _extract_operation(statement: str) -> str:
    """Extract the leading SQL verb from *statement*."""
    m = _SQL_OP_RE.match(statement)
    return m.group(1).upper() if m else "UNKNOWN"


class DataFlowInstrumentor:
    """Instruments DataFlow / database operations with OTel spans.

    Thread-safe.  When tracing is not at ``FULL``, all methods are no-ops.

    Example::

        inst = DataFlowInstrumentor(db_system="postgresql")
        result = inst.trace_query(
            statement="SELECT * FROM users WHERE id = ?",
            execute_fn=conn.fetchall,
            args=("SELECT * FROM users WHERE id = ?", user_id),
            parent_span=node_span,
        )
    """

    def __init__(self, db_system: str = "") -> None:
        self._db_system = db_system
        self._lock = threading.Lock()

    def trace_query(
        self,
        statement: str,
        execute_fn: Callable[..., Any],
        args: tuple[Any, ...] = (),
        kwargs: Optional[dict[str, Any]] = None,
        parent_span: Optional[Any] = None,
    ) -> Any:
        """Execute *execute_fn* inside an OTel database span.

        Args:
            statement:   SQL statement text (for span attributes).
            execute_fn:  The callable that actually runs the query.
            args:        Positional arguments forwarded to *execute_fn*.
            kwargs:      Keyword arguments forwarded to *execute_fn*.
            parent_span: Optional parent span for hierarchy.

        Returns:
            Whatever *execute_fn* returns.

        Raises:
            Any exception raised by *execute_fn* (recorded on the span first).
        """
        kwargs = kwargs or {}
        tracer = get_workflow_tracer()

        if not tracer.enabled or tracer.level is not TracingLevel.FULL:
            return execute_fn(*args, **kwargs)

        operation = _extract_operation(statement)
        span = tracer.start_db_span(
            operation=operation,
            statement=statement[:_MAX_STATEMENT_LEN],
            db_system=self._db_system,
            parent_span=parent_span,
        )
        start = time.monotonic()
        try:
            result = execute_fn(*args, **kwargs)
            duration = time.monotonic() - start
            tracer.set_attribute(span, "db.duration_s", round(duration, 6))
            row_count = self._count_rows(result)
            if row_count is not None:
                tracer.set_attribute(span, "db.row_count", row_count)
            tracer.end_span(span, status="ok")
            return result
        except Exception as exc:
            duration = time.monotonic() - start
            tracer.set_attribute(span, "db.duration_s", round(duration, 6))
            tracer.end_span(span, error=exc)
            raise

    @staticmethod
    def _count_rows(result: Any) -> Optional[int]:
        """Attempt to determine a row count from a query result.

        Returns ``None`` when the result type is not countable.
        """
        if result is None:
            return 0
        if isinstance(result, (list, tuple)):
            return len(result)
        if hasattr(result, "rowcount"):
            rc = result.rowcount
            if isinstance(rc, int) and rc >= 0:
                return rc
        return None
