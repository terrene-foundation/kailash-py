"""Regression: MCPChannel must not wedge a shared-executor worker.

``MCPServer.run()`` is a blocking serve loop. It used to be dispatched with
``loop.run_in_executor(None, self.mcp_server.run)`` -- asyncio's DEFAULT
executor. Workers of that pool are registered in
``concurrent.futures.thread._threads_queues``, and CPython's
``concurrent.futures.thread._python_exit`` hook (invoked from
``threading._shutdown()``) ``join()``s every registered worker
UNCONDITIONALLY, daemon flag included.

A worker parked inside ``run()`` never returns to its work queue, so that join
never completes and the whole process hangs at interpreter exit. Observed
signature: the ``packages/kailash-nexus`` pytest suite printed its complete
summary (``2592 passed``) and then never exited; the main thread sat in::

    File ".../threading.py", line 1094 in join
    File ".../concurrent/futures/thread.py", line 31 in _python_exit
    File ".../threading.py", line 1536 in _shutdown

This is a PRODUCTION defect, not a test artifact: any long-running host process
that starts an ``MCPChannel`` permanently consumes a default-executor worker and
cannot exit cleanly.

The assertions below are behavioural -- they observe the interpreter-level
registry that ``_python_exit`` actually walks, not an implementation detail of
``MCPChannel``.
"""

import asyncio
import sys
import threading
import traceback
from concurrent.futures import thread as _cf_thread
from typing import Any, List, Optional, Tuple

import pytest

from kailash.channels.base import ChannelConfig, ChannelType
from kailash.channels.mcp_channel import MCPChannel

pytestmark = [pytest.mark.regression, pytest.mark.asyncio]


class _UnstoppableMCPServer:
    """Faithful stand-in for the real ``MCPServer``: blocking ``run()``, NO ``stop()``.

    This models production exactly. ``MCPServer.run()`` with
    ``transport == "websocket"`` enters ``asyncio.run(self._run_websocket())``
    -> ``run_forever()`` and blocks indefinitely, and the class exposes NO
    ``stop()`` method -- so ``MCPChannel.stop()``'s
    ``hasattr(self.mcp_server, "stop")`` guard is False and nothing ever
    unwinds the serve loop. That is precisely why the pool worker stays wedged
    and ``_python_exit`` hangs the interpreter.

    ``release_for_test`` is deliberately NOT named ``stop``: ``MCPChannel``
    must not be able to find it, or the double would be more cooperative than
    the real server and the tests would stop discriminating.
    """

    def __init__(self) -> None:
        self._shutdown = threading.Event()
        self.entered = threading.Event()
        self.run_thread: Optional[threading.Thread] = None

    def run(self) -> None:
        self.run_thread = threading.current_thread()
        self.entered.set()
        # Blocks exactly like the real serve loop.
        self._shutdown.wait()

    def release_for_test(self) -> None:
        """Test-only escape hatch so a wedged thread never leaks into siblings."""
        self._shutdown.set()


class _StoppableMCPServer(_UnstoppableMCPServer):
    """Variant that DOES expose ``stop()``, for asserting stop() is honored."""

    def stop(self) -> None:
        self._shutdown.set()


def _pooled_workers_running_target(
    target_thread: Optional[threading.Thread],
) -> List[Tuple[threading.Thread, str]]:
    """Pool workers registered with ``_python_exit`` that are NOT parked.

    A worker parked on ``work_queue.get(block=True)`` will consume the ``None``
    sentinel ``_python_exit`` puts on its queue and terminate. A worker executing
    a work item that never returns will not -- and ``_python_exit`` blocks on it
    forever. Only the second kind is a leak.
    """
    frames = sys._current_frames()
    leaked: List[Tuple[threading.Thread, str]] = []
    for worker in list(_cf_thread._threads_queues.keys()):
        if not worker.is_alive():
            continue
        if target_thread is not None and worker is not target_thread:
            continue
        frame = frames.get(worker.ident)
        if frame is None:
            continue
        stack = "".join(traceback.format_stack(frame))
        if "work_queue.get(block=True)" in stack:
            continue  # parked; _python_exit's sentinel will free it
        leaked.append((worker, stack))
    return leaked


def _make_channel(server: Any) -> MCPChannel:
    return MCPChannel(
        config=ChannelConfig(
            name="regression-mcp-channel",
            channel_type=ChannelType.MCP,
            host="127.0.0.1",
            port=0,
        ),
        mcp_server=server,
    )


async def test_mcp_channel_start_does_not_wedge_a_pooled_executor_worker() -> None:
    """The blocking serve loop must not run on an atexit-joined pool worker.

    Pre-fix this FAILS: ``run()`` was submitted to asyncio's default executor,
    so the thread that entered it is in ``_threads_queues`` and is executing a
    work item that never returns -- precisely the state that makes
    ``_python_exit`` hang the interpreter.
    """
    server = _UnstoppableMCPServer()
    channel = _make_channel(server)

    try:
        await channel.start()

        # Wait for the serve loop to actually be entered, otherwise we would be
        # asserting against a thread that has not started blocking yet and the
        # test would pass vacuously.
        assert server.entered.wait(timeout=10.0), "MCP serve loop never started"

        wedged = _pooled_workers_running_target(server.run_thread)
        assert not wedged, (
            "MCPServer.run() is executing on a thread registered in "
            "concurrent.futures.thread._threads_queues. _python_exit() joins "
            "that thread unconditionally at interpreter shutdown and the serve "
            "loop never returns, so the process will hang after every test "
            "summary. Offending stack:\n\n" + wedged[0][1]
        )

        # And positively: it must be running on a daemon thread, which the
        # interpreter abandons at shutdown instead of joining.
        assert server.run_thread is not None
        assert server.run_thread.daemon, (
            "MCP serve loop must run on a daemon thread so interpreter "
            f"shutdown can abandon it; got daemon={server.run_thread.daemon}"
        )
    finally:
        server.release_for_test()
        await channel.stop()


async def test_mcp_channel_stop_shuts_the_server_down_when_it_can() -> None:
    """``stop()`` must actually invoke the server's shutdown, not silently no-op.

    The old implementation called ``future.cancel()`` on an executor future
    whose work item had already started -- which returns ``False`` and does
    nothing -- and then ``await``ed ``mcp_server.stop()``, which raises
    ``TypeError`` for the SYNC ``stop()`` the SDK's servers actually define.
    """
    server = _StoppableMCPServer()
    channel = _make_channel(server)

    try:
        await channel.start()
        assert server.entered.wait(timeout=10.0), "MCP serve loop never started"
        run_thread = server.run_thread
        assert run_thread is not None

        await channel.stop()

        run_thread.join(timeout=10.0)
        assert not run_thread.is_alive(), (
            "MCP serve thread survived channel.stop(); stop() did not actually "
            "shut the server down."
        )
    finally:
        server.release_for_test()


async def test_no_busy_pooled_workers_survive_a_start_stop_cycle() -> None:
    """Whole-cycle invariant: no new atexit-joined worker is left running.

    This is the assertion that maps directly onto the observed defect -- it
    counts exactly the threads ``_python_exit`` will block on.

    Uses the UNSTOPPABLE double on purpose: the real ``MCPServer`` exposes no
    ``stop()``, so nothing unwinds its serve loop. A cooperative double would
    let the pool worker return to its queue unaided and the assertion would
    pass even against the broken dispatch -- it would not discriminate.
    """
    before = {t.ident for t, _ in _pooled_workers_running_target(None)}

    server = _UnstoppableMCPServer()
    channel = _make_channel(server)
    try:
        await channel.start()
        assert server.entered.wait(timeout=10.0), "MCP serve loop never started"
        await channel.stop()

        # Give any unwinding thread a moment to leave the registry.
        await asyncio.sleep(0.1)

        after = _pooled_workers_running_target(None)
        new = [(t, s) for t, s in after if t.ident not in before]
        assert not new, (
            "start()/stop() left "
            f"{len(new)} busy worker(s) registered with concurrent.futures' "
            "atexit joiner; the interpreter will hang at exit. First stack:\n\n"
            + new[0][1]
        )
    finally:
        # Never leak a wedged thread into sibling tests, whatever happened.
        server.release_for_test()
