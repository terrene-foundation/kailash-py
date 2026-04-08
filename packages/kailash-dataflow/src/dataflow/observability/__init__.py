# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
DataFlow observability primitives.

Phase 7.2: correlation ID propagation via ContextVar so every log
line emitted inside a request/handler/agent execution scope carries
the same ``correlation_id`` field. Without this, multi-step requests
interleave in the log aggregator and become impossible to trace.

Contract (per ``rules/observability.md`` § "Correlation ID on Every
Log Line"):

- The ``correlation_id`` ContextVar is bound at the request / task
  / pipeline entry point by calling :func:`set_correlation_id`.
- Every log call inside that scope SHOULD include
  ``extra={"correlation_id": get_correlation_id(), ...}``.
- Nested scopes MAY push a child correlation_id via
  :func:`with_correlation_id` context manager, which stacks the
  child onto the parent and restores the parent on exit.
- If no correlation_id is bound, :func:`get_correlation_id` returns
  ``None`` (not empty string) so callers can emit a literal ``null``
  in JSON logs instead of a misleading empty string.

Example::

    from dataflow.observability import (
        set_correlation_id,
        get_correlation_id,
        with_correlation_id,
    )

    @app.post("/orders")
    async def create_order(req: Request):
        set_correlation_id(req.headers.get("x-request-id"))
        logger.info(
            "order.create.start",
            extra={"correlation_id": get_correlation_id()},
        )
        # ... any log call inside this request scope inherits the ID

    # nested scope — e.g. a sub-task spawned from the request
    async with with_correlation_id(f"{parent_id}.subtask"):
        logger.info("subtask.start", extra={...})
"""

from dataflow.observability.correlation import (
    clear_correlation_id,
    get_correlation_id,
    set_correlation_id,
    with_correlation_id,
)

__all__ = [
    "clear_correlation_id",
    "get_correlation_id",
    "set_correlation_id",
    "with_correlation_id",
]
