"""Shared FastAPI/Starlette router-iteration helpers for custom lifespans.

A custom ``lifespan`` passed to ``FastAPI(lifespan=...)`` REPLACES Starlette's
default ``_DefaultLifespan``, which is the only code that iterates
``router.on_startup`` / ``router.on_shutdown``. Custom lifespans that do NOT
re-iterate those lists silently drop every handler users register via
``@app.on_event("startup")`` or ``app.router.on_startup.append(...)``. This is
the #500 bug pattern.

Per ``framework-first.md`` § "Drive The Data, Not The Dispatch", these helpers
iterate the registered-handlers list — the data structure FastAPI's own
internal dispatcher walks — instead of calling ``app.router.startup()`` /
``app.router.shutdown()`` by name. Method names drift across FastAPI/Starlette
versions (underscore-prefix transitions, removals); the on_startup /
on_shutdown lists are strictly more stable because the framework's own hooks
depend on them.

Both helpers handle sync handlers (return ``None``) and async handlers (return
a coroutine) using ``inspect.iscoroutine(result)`` on the call's return value
— the same shape ``WorkflowServer`` previously inlined at lines 234-237. They
ISOLATE per-handler exceptions: one handler raising does NOT prevent the next
from running. After all handlers run, the FIRST exception is re-raised so the
ASGI server still sees a startup failure (preserving fail-fast semantics) UNLESS
``propagate_errors=False`` is passed (useful in shutdown, where best-effort
cleanup is the norm).

Example (custom lifespan honoring router hooks)::

    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    from kailash.utils import drive_router_lifespan_startup, drive_router_lifespan_shutdown

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await drive_router_lifespan_startup(app)
        try:
            yield
        finally:
            await drive_router_lifespan_shutdown(app, propagate_errors=False)

    app = FastAPI(lifespan=lifespan)
    @app.on_event("startup")
    async def warm_cache(): ...
"""

from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


async def _drive_handlers(
    handlers: list,
    *,
    phase: str,
    propagate_errors: bool,
) -> None:
    """Iterate ``handlers`` calling each, isolating per-handler failures.

    ``phase`` is a short label ("startup" / "shutdown") used in WARN log lines
    so an operator can tell which iteration produced the error.

    Per ``observability.md`` Rule 7 (bulk operations log partial failures at
    WARN), each failing handler emits a structured WARN line with the handler
    name and traceback. After the loop, the FIRST captured exception is
    re-raised when ``propagate_errors`` is True — preserving fail-fast for
    startup so uvicorn aborts boot cleanly. Shutdown callers typically pass
    ``propagate_errors=False`` because cleanup paths are best-effort and a
    later handler may still need to run even after an earlier one raises (same
    carve-out as ``zero-tolerance.md`` Rule 3 for cleanup paths).
    """
    first_error: BaseException | None = None

    for handler in list(handlers):
        handler_name = getattr(handler, "__qualname__", None) or getattr(
            handler, "__name__", repr(handler)
        )
        try:
            # Match the existing workflow_server.py pattern at lines 234-237:
            # call the handler, then await the result if it's a coroutine.
            # This handles both sync (`def`) and async (`async def`) handlers
            # uniformly without needing to introspect the function itself,
            # which is brittle when handlers are wrapped (functools.partial,
            # decorators, etc).
            result = handler()
            if inspect.iscoroutine(result):
                await result
        except BaseException as exc:  # noqa: BLE001 — isolate per-handler failures
            # exc_info=True attaches the full traceback to the log record so
            # operators can see WHERE in the handler the failure happened, not
            # just the exception class. Per observability.md Rule 7 the WARN
            # MUST be structured (kwargs / extra), not f-string interpolated.
            logger.warning(
                "lifespan.%s.handler_failed",
                phase,
                exc_info=True,
                extra={"handler": handler_name, "phase": phase},
            )
            if first_error is None:
                first_error = exc

    if first_error is not None and propagate_errors:
        raise first_error


async def drive_router_lifespan_startup(
    app: "FastAPI",
    *,
    propagate_errors: bool = True,
) -> None:
    """Drive every handler in ``app.router.on_startup`` to completion.

    Iterates ``app.router.on_startup`` — the SAME list Starlette's default
    lifespan walks internally — calling each handler in registration order.
    Sync handlers (return ``None``) are accepted; async handlers (return a
    coroutine) are awaited.

    Per-handler exceptions are isolated: if handler N raises, handlers N+1,
    N+2, ... still run. After all handlers complete, the FIRST captured
    exception is re-raised when ``propagate_errors`` is True (the default).
    This preserves fail-fast semantics at startup — uvicorn aborts the boot
    cleanly when any registered hook fails, matching what
    ``_DefaultLifespan.startup`` would have produced.

    Pass ``propagate_errors=False`` to log-only without re-raising. This is
    rarely correct at startup but available for symmetry with shutdown.

    Args:
        app: The FastAPI application whose ``router.on_startup`` to drive.
        propagate_errors: If True (default), re-raise the first captured
            handler exception after all handlers complete. If False, log
            failures and return normally.

    Why a helper module: three sibling FastAPI sites (``KailashAPIGateway``,
    ``WorkflowAPIGateway``, ``WorkflowAPI``) construct ``FastAPI`` with
    ``lifespan=`` set but do NOT iterate ``on_startup`` — they ship the same
    #500 silent-drop bug as the pre-fix ``WorkflowServer``. Routing every
    site through one helper localizes the cross-version invariant per
    ``framework-first.md`` § "Drive The Data".
    """
    await _drive_handlers(
        app.router.on_startup,
        phase="startup",
        propagate_errors=propagate_errors,
    )


async def drive_router_lifespan_shutdown(
    app: "FastAPI",
    *,
    propagate_errors: bool = True,
) -> None:
    """Drive every handler in ``app.router.on_shutdown`` to completion.

    Symmetric to :func:`drive_router_lifespan_startup`. Iterates
    ``app.router.on_shutdown`` calling each handler, awaiting coroutines, and
    isolating per-handler exceptions.

    By default the FIRST captured exception is re-raised after all handlers
    complete (``propagate_errors=True``). Shutdown callers commonly pass
    ``propagate_errors=False`` because cleanup paths are best-effort: one
    failing cleanup handler MUST NOT prevent later handlers from running, and
    the ASGI server is already tearing down — re-raising serves no purpose
    beyond the WARN log lines this helper already emits.

    Args:
        app: The FastAPI application whose ``router.on_shutdown`` to drive.
        propagate_errors: If True (default), re-raise the first captured
            handler exception after all handlers complete. If False, log
            failures and return normally — the typical shutdown choice.
    """
    await _drive_handlers(
        app.router.on_shutdown,
        phase="shutdown",
        propagate_errors=propagate_errors,
    )


__all__ = [
    "drive_router_lifespan_startup",
    "drive_router_lifespan_shutdown",
]
