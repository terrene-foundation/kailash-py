"""Tier 2 integration tests — drive_router_lifespan_* against real FastAPI.

The Tier 1 unit suite at ``tests/unit/utils/test_lifespan_helper.py`` proves
the helper's contract in isolation via a router stub. This Tier 2 suite
proves the WIRING: that the helper, when called from a custom ``lifespan=``
context manager, actually drives the handlers registered on a real
``FastAPI.router.on_startup`` / ``on_shutdown`` list.

Per ``testing.md`` § 3-Tier Testing, Tier 2 uses NO mocking — these tests
construct a real ``FastAPI`` app and drive its lifespan via Starlette's own
public ``app.router.lifespan_context(app)`` async context manager. This is
the same API uvicorn calls in production at lifespan boot/teardown, and the
same API Starlette's internal test infrastructure uses to run lifespan in
tests. It also avoids the ``@app.on_event`` deprecation warning surface (per
``zero-tolerance.md`` Rule 1) by registering hooks via
``app.router.add_event_handler`` and the public ``router.on_startup`` /
``router.on_shutdown`` lists — the SAME lists ``@app.on_event`` writes to
internally and the SAME lists the helper iterates.

End-to-end coverage of the helper through the FULL uvicorn HTTP transport
already exists at ``tests/regression/test_issue_500_router_on_startup.py``,
which boots an actual uvicorn server on a real socket. This file covers the
helper layer DIRECTLY with the lifespan API, independent of any HTTP server
or ASGI transport.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import pytest
from fastapi import FastAPI

from kailash.utils.lifespan import (
    drive_router_lifespan_shutdown,
    drive_router_lifespan_startup,
)


def _make_app_with_helper_lifespan() -> FastAPI:
    """Build a FastAPI app whose lifespan is driven by the shared helper.

    The custom ``lifespan=`` here is the EXACT pattern WorkflowServer (and
    the three sibling FastAPI sites patched in S2) use: a custom
    asynccontextmanager that calls the helper to drive ``router.on_startup``
    / ``router.on_shutdown``. Without those helper calls, the custom
    lifespan replaces Starlette's default and silently drops every
    user-registered hook (the #500 bug).
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await drive_router_lifespan_startup(app)
        try:
            yield
        finally:
            # Best-effort shutdown — matches WorkflowServer's call site at
            # workflow_server.py:283-292: one failing on_shutdown handler
            # MUST NOT block siblings or the ShutdownCoordinator.
            await drive_router_lifespan_shutdown(app, propagate_errors=False)

    return FastAPI(lifespan=lifespan)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_helper_drives_router_on_startup_via_lifespan_context() -> None:
    """Hooks registered on ``router.on_startup`` MUST fire under the helper.

    This is the #500 reproducer pattern: register a hook on the router's
    on_startup list (the public API ``@app.on_event("startup")`` writes to),
    then drive lifespan via the SAME context manager Starlette/uvicorn
    drive in production. Pre-helper, the hook was silently dropped because
    the custom lifespan replaced Starlette's default. Post-helper, both
    sync and async hooks fire in registration order.
    """
    app = _make_app_with_helper_lifespan()
    events: list[str] = []

    async def warm_cache() -> None:
        events.append("startup_async")

    def init_metrics() -> None:  # sync handler
        events.append("startup_sync")

    # Register via the public router.add_event_handler API. This is what
    # @app.on_event("startup") does internally; using it directly avoids
    # the FastAPI on_event DeprecationWarning while exercising the SAME
    # router.on_startup list the helper iterates.
    app.router.add_event_handler("startup", warm_cache)
    app.router.add_event_handler("startup", init_metrics)

    # Drive lifespan via Starlette's own public context manager — the SAME
    # API uvicorn invokes at boot. No HTTP transport needed; the helper
    # runs to completion when the context manager enters.
    async with app.router.lifespan_context(app):
        # Inside the lifespan: app is "running". Both handlers fired during
        # the __aenter__ phase before yielding control here.
        assert events == ["startup_async", "startup_sync"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_helper_drives_router_on_shutdown_via_lifespan_context() -> None:
    """Hooks on ``router.on_shutdown`` MUST fire when the lifespan exits."""
    app = _make_app_with_helper_lifespan()
    events: list[str] = []

    async def flush_metrics() -> None:
        events.append("shutdown_async")

    def close_pool() -> None:  # sync handler
        events.append("shutdown_sync")

    app.router.add_event_handler("shutdown", flush_metrics)
    app.router.add_event_handler("shutdown", close_pool)

    async with app.router.lifespan_context(app):
        # Inside the lifespan — shutdown handlers haven't fired yet.
        assert events == []

    # After __aexit__: the helper's drive_router_lifespan_shutdown ran in
    # the lifespan's `finally:` and walked router.on_shutdown.
    assert events == ["shutdown_async", "shutdown_sync"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_helper_handles_router_on_startup_append_pattern() -> None:
    """``app.router.on_startup.append(fn)`` MUST fire — the #500 minimal repro.

    This is the EXACT pattern from the #500 issue body: bypass the
    add_event_handler API, append directly to the list. Pre-fix, this hook
    was silently dropped because the custom lifespan didn't iterate the
    list. Post-fix (helper), it fires.
    """
    app = _make_app_with_helper_lifespan()
    events: list[str] = []

    async def my_startup() -> None:
        events.append("router_append")

    app.router.on_startup.append(my_startup)

    async with app.router.lifespan_context(app):
        assert events == ["router_append"], (
            "router.on_startup.append handler did not fire — this is the "
            "#500 regression class. Helper must iterate router.on_startup."
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_helper_runs_all_startup_handlers_even_when_one_raises() -> None:
    """Handler isolation MUST hold under a real FastAPI lifespan.

    Per the helper's contract: handler N raising MUST NOT prevent N+1. The
    Tier 1 suite tests this through a router stub; this Tier 2 test
    confirms the behavior survives the real Starlette lifespan_context API.

    The first handler's exception propagates out of the `async with`
    because drive_router_lifespan_startup uses propagate_errors=True by
    default — preserving fail-fast for startup so uvicorn aborts cleanly.
    """
    app = _make_app_with_helper_lifespan()
    events: list[str] = []

    def first() -> None:
        events.append("first")

    async def second_raises() -> None:
        events.append("second")
        raise RuntimeError("intentional failure for isolation test")

    def third() -> None:
        events.append("third")

    app.router.add_event_handler("startup", first)
    app.router.add_event_handler("startup", second_raises)
    app.router.add_event_handler("startup", third)

    with pytest.raises(RuntimeError, match="intentional failure"):
        async with app.router.lifespan_context(app):
            # Should never reach here — startup raised.
            pytest.fail("lifespan body executed despite startup failure")

    # Critical assertion: ALL THREE handlers ran despite the middle raising.
    # This is the helper's per-handler-isolation contract under real FastAPI.
    assert events == ["first", "second", "third"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_helper_with_no_handlers_is_noop_under_real_fastapi() -> None:
    """A FastAPI app with zero on_event hooks MUST drive lifespan cleanly.

    Empty-list path is the most common case for a freshly built app; the
    helper MUST not raise when the lists are empty AND lifespan must
    complete its full enter/exit cycle.
    """
    app = _make_app_with_helper_lifespan()
    body_ran = False

    async with app.router.lifespan_context(app):
        body_ran = True

    assert body_ran, "lifespan body did not execute"
