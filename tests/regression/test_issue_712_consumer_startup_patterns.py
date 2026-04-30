"""Regression: #712 — Nexus startup-handler discoverability + timing trap.

The brief framed #712 as "custom FastAPI lifespan silently disables
@app.on_event"; deep-dive verification (per workspace
``01-analysis/01-architecture.md``) found the canonical lifespan DOES
iterate ``router.on_startup`` (#500/#501 fix). The real failure mode is
two-pronged:

1.  **Discoverability gap** — there is no public API for
    ``run-this-at-startup``. Consumers either author a Plugin class for
    a one-line callback OR reach for ``nexus.fastapi_app.on_event(...)``.
2.  **Timing trap on ``fastapi_app``** — the property returns ``None``
    until ``_initialize_gateway()`` fires (lazy on first
    ``register()`` / ``start()``). Pre-init access raises
    ``AttributeError: 'NoneType' object has no attribute 'on_event'``,
    often wrapped in ``try/except`` that swallows the error and silently
    drops the startup logic.

Fix (this PR / MED-S3): added ``Nexus.add_startup_handler(func)`` and
``Nexus.add_shutdown_handler(func)`` public methods that route into the
existing ``_startup_hooks`` / ``_shutdown_hooks`` lists already wired
into the FastAPI lifespan (#501 contract). Methods refuse post-start
registration with a typed ``RuntimeError`` so a late call cannot
silently drop the hook.

This regression test reproduces the consumer-facing patterns and MUST
NOT be deleted per orphan-detection rules.

Acceptance per ``todos/active/MED-S3-nexus-add-startup-handler-public-api.md``:

- ``add_startup_handler`` accepts callable, appends to ``_startup_hooks``,
  refuses post-start with ``RuntimeError``, returns ``self``.
- ``add_shutdown_handler`` symmetric.
- Both async ``def`` and sync ``def`` are supported.
- Mediscribe-pattern E2E (DataFlow ``create_tables_async`` from a
  startup hook) is the canonical use case AND depends on #713 / MED-S4
  (lazy DataFlow runtime). This file ships with that test SKIPPED with
  an explicit reason — orchestrator MUST remove the skip after
  ``feat/issue-713-dataflow-lazy-runtime`` merges to main.
"""

from __future__ import annotations

import asyncio
import socket

import httpx
import pytest
import uvicorn

from nexus import Nexus


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ---------------------------------------------------------------------------
# Tier 1 — API contract (no server boot required)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_add_startup_handler_returns_self_for_chaining() -> None:
    """Regression: #712 — add_startup_handler returns self for chaining."""
    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_durability=False,
        rate_limit=None,
    )
    try:

        async def fn() -> None:
            return None

        result = app.add_startup_handler(fn)
        assert result is app, "add_startup_handler MUST return self for chaining"
    finally:
        app.close()


@pytest.mark.regression
def test_add_shutdown_handler_returns_self_for_chaining() -> None:
    """Regression: #712 — add_shutdown_handler returns self for chaining."""
    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_durability=False,
        rate_limit=None,
    )
    try:

        async def fn() -> None:
            return None

        result = app.add_shutdown_handler(fn)
        assert result is app, "add_shutdown_handler MUST return self for chaining"
    finally:
        app.close()


@pytest.mark.regression
def test_add_startup_handler_appends_to_internal_list() -> None:
    """Regression: #712 — add_startup_handler routes into _startup_hooks."""
    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_durability=False,
        rate_limit=None,
    )
    try:

        async def fn() -> None:
            return None

        before_count = len(app._startup_hooks)
        app.add_startup_handler(fn)
        assert len(app._startup_hooks) == before_count + 1
        assert app._startup_hooks[-1] is fn, (
            "add_startup_handler MUST append to _startup_hooks "
            "(the same list the FastAPI lifespan iterates via "
            "_call_startup_hooks_async)"
        )
    finally:
        app.close()


@pytest.mark.regression
def test_add_shutdown_handler_appends_to_internal_list() -> None:
    """Regression: #712 — add_shutdown_handler routes into _shutdown_hooks."""
    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_durability=False,
        rate_limit=None,
    )
    try:

        async def fn() -> None:
            return None

        before_count = len(app._shutdown_hooks)
        app.add_shutdown_handler(fn)
        assert len(app._shutdown_hooks) == before_count + 1
        assert app._shutdown_hooks[-1] is fn
    finally:
        app.close()


@pytest.mark.regression
def test_add_startup_handler_rejects_non_callable() -> None:
    """Regression: #712 — non-callable raises TypeError immediately."""
    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_durability=False,
        rate_limit=None,
    )
    try:
        with pytest.raises(TypeError, match="callable"):
            app.add_startup_handler("not a callable")  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="callable"):
            app.add_startup_handler(42)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="callable"):
            app.add_startup_handler(None)  # type: ignore[arg-type]
    finally:
        app.close()


@pytest.mark.regression
def test_add_shutdown_handler_rejects_non_callable() -> None:
    """Regression: #712 — non-callable raises TypeError immediately."""
    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_durability=False,
        rate_limit=None,
    )
    try:
        with pytest.raises(TypeError, match="callable"):
            app.add_shutdown_handler("not a callable")  # type: ignore[arg-type]
    finally:
        app.close()


@pytest.mark.regression
def test_add_startup_handler_refuses_post_start() -> None:
    """Regression: #712 — registration after start() raises RuntimeError.

    The lifespan dispatches startup hooks once at uvicorn boot. After
    ``start()`` (or after ``_running = True``) the lifespan has already
    fired or is firing, and a late append cannot be guaranteed to run.
    The typed RuntimeError converts a silent drop into an actionable
    failure (zero-tolerance Rule 3a — typed delegate guards).
    """
    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_durability=False,
        rate_limit=None,
    )
    try:
        # Simulate post-start state directly. start() blocks on uvicorn,
        # so we set the flag the public API guards on.
        app._running = True

        async def too_late() -> None:
            return None

        with pytest.raises(RuntimeError, match="after Nexus.start"):
            app.add_startup_handler(too_late)
    finally:
        app._running = False
        app.close()


@pytest.mark.regression
def test_add_shutdown_handler_refuses_post_start() -> None:
    """Regression: #712 — symmetric post-start refusal for shutdown handler."""
    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_durability=False,
        rate_limit=None,
    )
    try:
        app._running = True

        async def too_late() -> None:
            return None

        with pytest.raises(RuntimeError, match="after Nexus.start"):
            app.add_shutdown_handler(too_late)
    finally:
        app._running = False
        app.close()


@pytest.mark.regression
def test_add_startup_handler_accepts_sync_callable() -> None:
    """Regression: #712 — sync def is accepted and queued.

    Matches the existing plugin-protocol behaviour: sync hooks run as
    plain calls; async hooks are awaited. The dispatch lives in
    ``_call_startup_hooks_async``.
    """
    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_durability=False,
        rate_limit=None,
    )
    try:

        def sync_fn() -> None:
            return None

        app.add_startup_handler(sync_fn)
        assert app._startup_hooks[-1] is sync_fn
    finally:
        app.close()


# ---------------------------------------------------------------------------
# Tier 2/3 — server boot, hook fires inside FastAPI lifespan
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_add_startup_handler_fires_during_uvicorn_boot() -> None:
    """Regression: #712 — handler registered via public API fires at boot."""
    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_durability=False,
        rate_limit=None,
    )

    flag: list[int] = []

    async def my_startup() -> None:
        flag.append(1)

    # Register BEFORE register() / start() — exercises the canonical
    # consumer pattern that fastapi_app.on_event cannot support
    # (timing trap returns None).
    app.add_startup_handler(my_startup)

    port = _free_port()
    config = uvicorn.Config(
        app.fastapi_app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    server.config.lifespan = "on"
    task = asyncio.create_task(server.serve())

    try:
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        assert server.started

        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            resp = await client.get("/", timeout=5.0)
            assert resp.status_code == 200

        assert flag == [1], (
            f"Startup handler registered via add_startup_handler did not "
            f"fire (flag={flag}). The hook was queued in _startup_hooks "
            f"but the FastAPI lifespan did not dispatch it via "
            f"_call_startup_hooks_async. This is the #712 bug — public "
            f"API is non-functional."
        )
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except asyncio.TimeoutError:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        app.close()


@pytest.mark.regression
@pytest.mark.asyncio
async def test_add_shutdown_handler_fires_during_uvicorn_teardown() -> None:
    """Regression: #712 — shutdown handler fires when lifespan exits."""
    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_durability=False,
        rate_limit=None,
    )

    shutdown_flag: list[int] = []

    async def my_shutdown() -> None:
        shutdown_flag.append(1)

    app.add_shutdown_handler(my_shutdown)

    port = _free_port()
    config = uvicorn.Config(
        app.fastapi_app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    server.config.lifespan = "on"
    task = asyncio.create_task(server.serve())

    try:
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        assert server.started

        # Trigger shutdown by signalling uvicorn.
        server.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except asyncio.TimeoutError:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        assert shutdown_flag == [1], (
            f"Shutdown handler registered via add_shutdown_handler did not "
            f"fire (shutdown_flag={shutdown_flag}). Hook was queued in "
            f"_shutdown_hooks but the FastAPI lifespan did not dispatch "
            f"it via _call_shutdown_hooks_async at teardown."
        )
    finally:
        app.close()


# ---------------------------------------------------------------------------
# Mediscribe pattern — DataFlow async DDL from a startup hook
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.skip(
    reason=(
        "Depends on #713 / MED-S4 (lazy DataFlow runtime). The Mediscribe "
        "pattern is `db = DataFlow(url)` at module scope, then "
        "`await db.create_tables_async()` inside a startup hook. Today this "
        "fails with `AttributeError: 'LocalRuntime' object has no attribute "
        "'execute_workflow_async'` because DataFlow.__init__ binds "
        "LocalRuntime when no event loop is running. Enable this test "
        "after `feat/issue-713-dataflow-lazy-runtime` merges to main — "
        "orchestrator: remove this skip decorator."
    )
)
async def test_add_startup_handler_runs_dataflow_create_tables_async() -> None:
    """Regression: #712 + #713 — Mediscribe E2E pattern.

    The canonical consumer pattern this PR enables:

        nexus = Nexus(...)
        db = DataFlow("postgresql://...")

        @db.model
        class User:
            id: int

        async def init_schema():
            await db.create_tables_async()

        nexus.add_startup_handler(init_schema)
        nexus.start()

    On a fresh PostgreSQL container, the schema MUST exist after boot.
    """
    # Implementation deferred until #713 lands. Test body intentionally
    # omitted to avoid shipping a partial repro that masks the real
    # failure mode.
    pytest.fail("Should be skipped until #713 lands")
