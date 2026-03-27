# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Auto-instrumentation for ``ConnectionManager`` database operations.

Wraps the key ``ConnectionManager`` methods (``execute``, ``fetchone``,
``fetchall``) with OTel spans so that every query is visible in traces
without manual instrumentation at each call site.

Active only at :attr:`~kailash.runtime.tracing.TracingLevel.FULL`.

Usage::

    from kailash.runtime.instrumentation.database import DatabaseInstrumentor

    instrumentor = DatabaseInstrumentor()
    instrumentor.instrument(connection_manager)
    # All subsequent queries on connection_manager emit OTel spans.

    instrumentor.uninstrument(connection_manager)
    # Restores original methods.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional

from kailash.runtime.tracing import TracingLevel, get_workflow_tracer

logger = logging.getLogger(__name__)

__all__ = ["DatabaseInstrumentor"]

_MAX_STATEMENT_LEN = 1024
_INSTRUMENTED_ATTR = "_kailash_otel_instrumented"


class DatabaseInstrumentor:
    """Monkey-patches a ``ConnectionManager`` to emit OTel spans per query.

    Thread-safe.  Calling :meth:`instrument` twice on the same object is safe
    (the second call is a no-op).

    Attributes:
        db_system: The ``db.system`` semantic-convention value attached to spans.
    """

    def __init__(self, db_system: str = "") -> None:
        self._db_system = db_system
        self._lock = threading.Lock()
        self._originals: dict[int, dict[str, Callable[..., Any]]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def instrument(self, conn_manager: Any) -> None:
        """Wrap ``execute``, ``fetchone``, ``fetchall`` on *conn_manager*.

        Args:
            conn_manager: A ``ConnectionManager`` instance (or any object with
                the three named methods).
        """
        obj_id = id(conn_manager)
        with self._lock:
            if getattr(conn_manager, _INSTRUMENTED_ATTR, False):
                return  # Already instrumented

            originals: dict[str, Callable[..., Any]] = {}
            for method_name in ("execute", "fetchone", "fetchall"):
                original = getattr(conn_manager, method_name, None)
                if original is None:
                    continue
                originals[method_name] = original
                wrapped = self._make_wrapper(original, method_name)
                setattr(conn_manager, method_name, wrapped)

            self._originals[obj_id] = originals
            setattr(conn_manager, _INSTRUMENTED_ATTR, True)
            logger.debug(
                "Instrumented ConnectionManager %s (db_system=%s)",
                obj_id,
                self._db_system,
            )

    def uninstrument(self, conn_manager: Any) -> None:
        """Restore original methods on *conn_manager*.

        Safe to call even if the object was never instrumented.
        """
        obj_id = id(conn_manager)
        with self._lock:
            originals = self._originals.pop(obj_id, None)
            if originals is None:
                return
            for method_name, original in originals.items():
                setattr(conn_manager, method_name, original)
            setattr(conn_manager, _INSTRUMENTED_ATTR, False)
            logger.debug("Uninstrumented ConnectionManager %s", obj_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_wrapper(
        self,
        original: Callable[..., Any],
        method_name: str,
    ) -> Callable[..., Any]:
        """Create a tracing wrapper around *original*."""
        db_system = self._db_system

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_workflow_tracer()
            if not tracer.enabled or tracer.level is not TracingLevel.FULL:
                return original(*args, **kwargs)

            statement = args[0] if args and isinstance(args[0], str) else method_name
            truncated = statement[:_MAX_STATEMENT_LEN]

            operation = method_name.upper()
            span = tracer.start_db_span(
                operation=operation,
                statement=truncated,
                db_system=db_system,
            )
            start = time.monotonic()
            try:
                result = original(*args, **kwargs)
                duration = time.monotonic() - start
                tracer.set_attribute(span, "db.duration_s", round(duration, 6))
                _set_row_count(tracer, span, result)
                tracer.end_span(span, status="ok")
                return result
            except Exception as exc:
                duration = time.monotonic() - start
                tracer.set_attribute(span, "db.duration_s", round(duration, 6))
                tracer.end_span(span, error=exc)
                raise

        wrapper.__name__ = original.__name__ if hasattr(original, "__name__") else method_name
        wrapper.__qualname__ = getattr(original, "__qualname__", method_name)
        return wrapper


def _set_row_count(tracer: Any, span: Optional[Any], result: Any) -> None:
    """Best-effort row count extraction and attribute setting."""
    if result is None:
        tracer.set_attribute(span, "db.row_count", 0)
    elif isinstance(result, (list, tuple)):
        tracer.set_attribute(span, "db.row_count", len(result))
    elif hasattr(result, "rowcount"):
        rc = result.rowcount
        if isinstance(rc, int) and rc >= 0:
            tracer.set_attribute(span, "db.row_count", rc)
