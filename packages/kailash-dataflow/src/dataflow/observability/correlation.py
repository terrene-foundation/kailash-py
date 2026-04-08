# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Correlation ID propagation via ContextVar.

The ContextVar is scoped per-asyncio-task, so concurrent requests
never cross-contaminate each other's correlation IDs. Set at the
entry point (HTTP handler, task queue worker, scheduled job, fabric
pipeline run) and every downstream log call reads it back via
:func:`get_correlation_id`.

Phase 7.2 — infrastructure. Phase 7.3 (entry/exit logs on every
public method) consumes this infrastructure to attach the ID
automatically. Until Phase 7.3 lands, callers attach the ID
manually via ``extra={"correlation_id": get_correlation_id()}``.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator, Optional

__all__ = [
    "clear_correlation_id",
    "get_correlation_id",
    "set_correlation_id",
    "with_correlation_id",
]


# The default is None so a log line emitted outside any scope can
# encode "no correlation id was bound" as a literal JSON null rather
# than an empty string (which is indistinguishable from "bound to
# the empty string" in log aggregators).
_correlation_id: ContextVar[Optional[str]] = ContextVar("_correlation_id", default=None)


def get_correlation_id() -> Optional[str]:
    """Return the correlation ID bound to the current asyncio task.

    Returns ``None`` when no ID has been set via
    :func:`set_correlation_id` or :func:`with_correlation_id` in
    the current scope.
    """
    return _correlation_id.get()


def set_correlation_id(correlation_id: Optional[str]) -> Token:
    """Bind a correlation ID to the current asyncio task.

    Returns the :class:`Token` that can be passed to
    :func:`ContextVar.reset` to restore the previous value. Most
    callers should prefer :func:`with_correlation_id` which handles
    reset automatically via the context manager protocol.

    ``None`` is an explicit "clear the binding" sentinel; pass the
    empty string if you actually mean the literal empty ID (which
    is typically a bug in upstream middleware).
    """
    return _correlation_id.set(correlation_id)


def clear_correlation_id() -> None:
    """Remove the correlation ID from the current asyncio task.

    Equivalent to ``set_correlation_id(None)`` but does not return
    a token. Intended for cleanup paths (task teardown, worker
    shutdown) where the caller does not need to restore a prior
    value.
    """
    _correlation_id.set(None)


@contextmanager
def with_correlation_id(correlation_id: Optional[str]) -> Iterator[Optional[str]]:
    """Context manager that binds a correlation ID for the scoped block.

    On entry, sets the ID to the supplied value. On exit (clean or
    exception), restores the previous value via the ContextVar
    token. This is the preferred entry point because it guarantees
    the binding doesn't leak out of the scope.

    Yields the same value that was passed in so callers can write::

        with with_correlation_id(req_id) as cid:
            logger.info("request.start", extra={"correlation_id": cid})
    """
    token = _correlation_id.set(correlation_id)
    try:
        yield correlation_id
    finally:
        _correlation_id.reset(token)
