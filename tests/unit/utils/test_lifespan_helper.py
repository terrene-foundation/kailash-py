"""Tier 1 unit tests for ``kailash.utils.lifespan``.

These tests cover the helper's contract in isolation using a tiny stub object
that exposes the same ``router.on_startup`` / ``router.on_shutdown`` shape
FastAPI exposes — sufficient for unit coverage of the iteration semantics.

The shared helper lives at ``src/kailash/utils/lifespan.py`` and is consumed
by every Kailash FastAPI surface that sets a custom ``lifespan=`` (per
``framework-first.md`` § "Drive The Data, Not The Dispatch"). This file
exercises:

- sync handler dispatch (``def`` returning ``None``)
- async handler dispatch (``async def`` returning a coroutine)
- mixed sync + async dispatch in registration order
- per-handler exception isolation (handler N raises, N+1 still runs)
- first-exception re-raise after the loop completes
- ``propagate_errors=False`` log-only behavior
- empty list = no-op (no spurious raises)

A real FastAPI app is exercised in the Tier 2 integration test sibling at
``tests/integration/utils/test_lifespan_helper_with_fastapi.py``.
"""

from __future__ import annotations

import logging

import pytest

from kailash.utils.lifespan import (
    drive_router_lifespan_shutdown,
    drive_router_lifespan_startup,
)


class _RouterStub:
    """Minimal stand-in for ``FastAPI.router`` exposing the two list surfaces."""

    def __init__(self) -> None:
        self.on_startup: list = []
        self.on_shutdown: list = []


class _AppStub:
    """Minimal stand-in for ``FastAPI`` exposing only ``.router``."""

    def __init__(self) -> None:
        self.router = _RouterStub()


# ---------------------------------------------------------------------------
# Startup helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_startup_dispatches_sync_handler() -> None:
    """Sync handlers (return None) MUST be invoked exactly once."""
    app = _AppStub()
    calls: list[str] = []

    def sync_handler() -> None:
        calls.append("sync")

    app.router.on_startup.append(sync_handler)

    await drive_router_lifespan_startup(app)

    assert calls == ["sync"]


@pytest.mark.asyncio
async def test_startup_dispatches_async_handler() -> None:
    """Async handlers (return a coroutine) MUST be awaited."""
    app = _AppStub()
    calls: list[str] = []

    async def async_handler() -> None:
        calls.append("async")

    app.router.on_startup.append(async_handler)

    await drive_router_lifespan_startup(app)

    assert calls == ["async"]


@pytest.mark.asyncio
async def test_startup_dispatches_mixed_sync_and_async_in_order() -> None:
    """Mixed registrations MUST execute in registration order."""
    app = _AppStub()
    calls: list[str] = []

    def sync_first() -> None:
        calls.append("sync_first")

    async def async_second() -> None:
        calls.append("async_second")

    def sync_third() -> None:
        calls.append("sync_third")

    app.router.on_startup.extend([sync_first, async_second, sync_third])

    await drive_router_lifespan_startup(app)

    assert calls == ["sync_first", "async_second", "sync_third"]


@pytest.mark.asyncio
async def test_startup_isolates_handler_exceptions() -> None:
    """A raise in handler N MUST NOT prevent handler N+1 from running.

    The helper's contract: every registered handler runs exactly once even
    when an earlier one raises. After the loop completes, the FIRST captured
    exception is re-raised so uvicorn aborts cleanly. This test asserts both
    invariants on a 3-handler list where the middle handler fails.
    """
    app = _AppStub()
    calls: list[str] = []

    def first_runs() -> None:
        calls.append("first")

    async def second_raises() -> None:
        calls.append("second")
        raise RuntimeError("boom from second")

    def third_still_runs() -> None:
        calls.append("third")

    app.router.on_startup.extend([first_runs, second_raises, third_still_runs])

    with pytest.raises(RuntimeError, match="boom from second"):
        await drive_router_lifespan_startup(app)

    # Critically: ALL THREE handlers ran despite the middle one raising.
    assert calls == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_startup_reraises_first_exception_when_multiple_fail() -> None:
    """When N>1 handlers raise, the FIRST one is the one re-raised.

    Preserves the "first failure wins" semantics callers reason about when
    debugging — the operator sees the actual root cause in the traceback,
    not the last failure to fire.
    """
    app = _AppStub()

    def raises_a() -> None:
        raise ValueError("first error")

    def raises_b() -> None:
        raise RuntimeError("second error")

    app.router.on_startup.extend([raises_a, raises_b])

    with pytest.raises(ValueError, match="first error"):
        await drive_router_lifespan_startup(app)


@pytest.mark.asyncio
async def test_startup_propagate_errors_false_swallows_after_logging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """propagate_errors=False MUST log + suppress; all handlers still run."""
    app = _AppStub()
    calls: list[str] = []

    def first_raises() -> None:
        calls.append("first")
        raise RuntimeError("ignored failure")

    async def second_runs() -> None:
        calls.append("second")

    app.router.on_startup.extend([first_raises, second_runs])

    caplog.set_level(logging.WARNING, logger="kailash.utils.lifespan")
    # No raise expected.
    await drive_router_lifespan_startup(app, propagate_errors=False)

    assert calls == ["first", "second"]
    # Verify the failure was logged at WARN with the structured event name.
    warns = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("lifespan.startup.handler_failed" in r.message for r in warns), warns


@pytest.mark.asyncio
async def test_startup_empty_list_is_noop() -> None:
    """An empty on_startup MUST NOT raise — common case for apps with no hooks."""
    app = _AppStub()
    # No handlers registered at all.
    await drive_router_lifespan_startup(app)


# ---------------------------------------------------------------------------
# Shutdown helper — symmetric coverage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_dispatches_sync_handler() -> None:
    app = _AppStub()
    calls: list[str] = []

    def sync_handler() -> None:
        calls.append("sync")

    app.router.on_shutdown.append(sync_handler)

    await drive_router_lifespan_shutdown(app)

    assert calls == ["sync"]


@pytest.mark.asyncio
async def test_shutdown_dispatches_async_handler() -> None:
    app = _AppStub()
    calls: list[str] = []

    async def async_handler() -> None:
        calls.append("async")

    app.router.on_shutdown.append(async_handler)

    await drive_router_lifespan_shutdown(app)

    assert calls == ["async"]


@pytest.mark.asyncio
async def test_shutdown_isolates_handler_exceptions() -> None:
    """Symmetric with startup — middle handler raise does not block siblings."""
    app = _AppStub()
    calls: list[str] = []

    def first_runs() -> None:
        calls.append("first")

    async def second_raises() -> None:
        calls.append("second")
        raise RuntimeError("shutdown boom")

    def third_still_runs() -> None:
        calls.append("third")

    app.router.on_shutdown.extend([first_runs, second_raises, third_still_runs])

    with pytest.raises(RuntimeError, match="shutdown boom"):
        await drive_router_lifespan_shutdown(app)

    assert calls == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_shutdown_propagate_errors_false_swallows_after_logging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """propagate_errors=False is the typical shutdown choice — log, don't raise.

    Mirrors the WorkflowServer call site which passes propagate_errors=False
    so a failing on_shutdown handler does NOT block ShutdownCoordinator.
    """
    app = _AppStub()
    calls: list[str] = []

    def first_raises() -> None:
        calls.append("first")
        raise RuntimeError("cleanup failure")

    async def second_runs() -> None:
        calls.append("second")

    app.router.on_shutdown.extend([first_raises, second_runs])

    caplog.set_level(logging.WARNING, logger="kailash.utils.lifespan")
    await drive_router_lifespan_shutdown(app, propagate_errors=False)

    assert calls == ["first", "second"]
    warns = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("lifespan.shutdown.handler_failed" in r.message for r in warns), warns


@pytest.mark.asyncio
async def test_shutdown_empty_list_is_noop() -> None:
    """Empty on_shutdown MUST NOT raise — symmetric with startup."""
    app = _AppStub()
    await drive_router_lifespan_shutdown(app)
