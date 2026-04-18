"""Tier 2 wiring tests: shutdown-hook idempotency across sync and async paths.

The FastAPI lifespan fires plugin `on_shutdown` hooks via
:meth:`Nexus._call_shutdown_hooks_async`, and :meth:`Nexus.stop` fires the
sync variant :meth:`Nexus._call_shutdown_hooks`. Both paths share the flag
``_shutdown_hooks_fired`` under ``_shutdown_hooks_fired_lock`` so that
whichever path runs first claims the flag and the second path short-circuits.

These tests exercise both orderings end-to-end against real uvicorn and
real plugin hooks:

1. Lifespan shutdown runs first (normal graceful path) → ``Nexus.stop()``
   afterwards is a no-op for the plugin counter.
2. ``Nexus.stop()`` runs first (signal-handler / abrupt path) → lifespan's
   async path is a no-op for the same counter.

In both cases the plugin counter MUST read exactly 1.

No mocking — real uvicorn, real plugin, real threading.Lock.
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


class _CountingShutdownPlugin:
    """Plugin whose ``on_shutdown`` hook increments a counter each call.

    Double-firing the hook flips the counter from 1 to 2 — the regression
    signal that round-1 sec H2 / rev H1 asked a test to detect.
    """

    name = "counting-shutdown-plugin"

    def __init__(self) -> None:
        self.shutdown_count: int = 0

    def install(self, app) -> None:
        return None

    async def on_shutdown(self) -> None:
        self.shutdown_count += 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_shutdown_hooks_fire_exactly_once_when_lifespan_completes_then_stop():
    """Normal path: lifespan shutdown fires hooks, then Nexus.stop() no-ops.

    Boots Nexus inside a real uvicorn server, triggers graceful shutdown
    via ``server.should_exit = True``, awaits the lifespan teardown (which
    runs ``_call_shutdown_hooks_async``), then calls ``app.stop()`` — which
    in turn calls ``_call_shutdown_hooks`` (sync).

    Without the idempotency flag + lock, the plugin counter reads 2.
    With the fix, it reads exactly 1.
    """
    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_durability=False,
        rate_limit=None,
    )
    plugin = _CountingShutdownPlugin()
    app.add_plugin(plugin)

    fastapi_app = app.fastapi_app
    assert fastapi_app is not None

    port = _free_port()
    config = uvicorn.Config(
        fastapi_app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    server.config.lifespan = "on"
    # Simulate Nexus.start() having marked the server running — stop() only
    # takes the full shutdown branch when _running is True.
    app._running = True
    server_task = asyncio.create_task(server.serve())

    try:
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        assert server.started, "uvicorn never reached started state"

        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            resp = await client.get("/", timeout=5.0)
            assert resp.status_code == 200

        # Graceful shutdown — lifespan's finally: runs _call_shutdown_hooks_async.
        server.should_exit = True
        try:
            await asyncio.wait_for(server_task, timeout=10.0)
        except asyncio.TimeoutError:
            server_task.cancel()
            try:
                await server_task
            except (asyncio.CancelledError, Exception):
                pass
            pytest.fail("uvicorn did not stop within 10s")

        # After lifespan teardown, counter must be 1.
        assert plugin.shutdown_count == 1, (
            f"After graceful lifespan shutdown, plugin counter is "
            f"{plugin.shutdown_count}; expected 1."
        )

        # Nexus.stop() on the sync path MUST be a no-op for shutdown hooks
        # because the async path already claimed the flag under the lock.
        app.stop()
        assert plugin.shutdown_count == 1, (
            f"After Nexus.stop() following lifespan shutdown, plugin "
            f"counter is {plugin.shutdown_count}; expected 1 (sync path "
            f"should have short-circuited on _shutdown_hooks_fired)."
        )
    finally:
        if not server_task.done():
            server.should_exit = True
            try:
                await asyncio.wait_for(server_task, timeout=5.0)
            except asyncio.TimeoutError:
                server_task.cancel()
                try:
                    await server_task
                except (asyncio.CancelledError, Exception):
                    pass
        app.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_shutdown_hooks_fire_exactly_once_when_stop_called_before_lifespan_shutdown():
    """Abrupt path: Nexus.stop() first, then lifespan runs — still exactly one fire.

    Simulates the signal-handler sequence where an out-of-band ``stop()`` fires
    the sync shutdown path while uvicorn is still running, then uvicorn's
    lifespan exits and tries to fire the async path. The lock makes the
    second attempt a no-op.

    Without the idempotency flag + lock this produces counter == 2.
    With the fix it produces counter == 1.
    """
    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_durability=False,
        rate_limit=None,
    )
    plugin = _CountingShutdownPlugin()
    app.add_plugin(plugin)

    fastapi_app = app.fastapi_app
    assert fastapi_app is not None

    port = _free_port()
    config = uvicorn.Config(
        fastapi_app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    server.config.lifespan = "on"
    app._running = True
    server_task = asyncio.create_task(server.serve())

    try:
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        assert server.started, "uvicorn never reached started state"

        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            resp = await client.get("/", timeout=5.0)
            assert resp.status_code == 200

        # Fire the sync path FIRST (mimics a signal handler / external
        # shutdown command that reaches Nexus.stop before uvicorn's
        # lifespan starts its teardown).
        #
        # The sync path's _run_async_hook schedules an async hook as a task
        # on the running loop rather than awaiting inline, so yield once so
        # the task can complete before we assert the counter.
        app.stop()
        for _ in range(20):
            if plugin.shutdown_count >= 1:
                break
            await asyncio.sleep(0.05)
        assert plugin.shutdown_count == 1, (
            f"After Nexus.stop() (abrupt path), plugin counter is "
            f"{plugin.shutdown_count}; expected 1."
        )

        # Now let uvicorn finish. Its lifespan will call
        # _call_shutdown_hooks_async, which must short-circuit on the
        # already-claimed flag.
        server.should_exit = True
        try:
            await asyncio.wait_for(server_task, timeout=10.0)
        except asyncio.TimeoutError:
            server_task.cancel()
            try:
                await server_task
            except (asyncio.CancelledError, Exception):
                pass
            pytest.fail("uvicorn did not stop within 10s")

        # Counter is still 1 — the lifespan's async path did NOT re-fire
        # the hook.
        assert plugin.shutdown_count == 1, (
            f"After lifespan shutdown following Nexus.stop(), plugin "
            f"counter is {plugin.shutdown_count}; expected 1 (async path "
            f"should have short-circuited on _shutdown_hooks_fired)."
        )
    finally:
        if not server_task.done():
            server.should_exit = True
            try:
                await asyncio.wait_for(server_task, timeout=5.0)
            except asyncio.TimeoutError:
                server_task.cancel()
                try:
                    await server_task
                except (asyncio.CancelledError, Exception):
                    pass
        app.close()
