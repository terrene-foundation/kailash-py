"""Regression pins for the four channel-shutdown defects #2018-#2021.

All four are the same shape: ``stop()`` wrote a status that did not describe
what teardown had established, and a status field is a return value an
orchestrator acts on.

THE SERVER HERE IS REAL. It binds a TCP port, serves on a dedicated thread and
is released only by a genuine shutdown -- no ``Mock``, deliberately. A ``Mock``
satisfies every ``hasattr`` and returns a truthy value for every call, so a
mock-driven shutdown test passes identically whether the server thread stopped
or not: it cannot tell the defect from the fix, which is the whole question.
The port is the independent witness -- ``_port_is_serving`` connects to it, so
"the channel says STOPPED" and "the server is still answering" are measured
separately and can disagree.

Each test below was confirmed to RED against the pre-fix sources
(``git show origin/main:src/kailash/channels/*.py``) before the fix landed; the
verbatim run is in the PR body. Nothing here imports a symbol the pre-fix tree
lacks, so the fail-first run is READABLE RED rather than a collection error --
an un-runnable check is zero evidence in either direction.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import pytest

from kailash.channels.base import ChannelConfig, ChannelStatus, ChannelType
from kailash.channels.cli_channel import CLIChannel
from kailash.channels.mcp_channel import MCPChannel

pytestmark = pytest.mark.regression


class _RealServer:
    """A genuinely blocking server: a bound port and an accept loop on a thread.

    ``run()`` does not return until ``_shutdown`` is set, which is exactly the
    property ``MCPChannel.start()`` puts it on a dedicated daemon thread for.
    ``honour_stop=False`` models the real failure this pins -- a server whose
    ``stop()`` does not (or cannot) unwind its serve loop.
    """

    def __init__(self, *, honour_stop: bool) -> None:
        self._honour_stop = honour_stop
        self._shutdown = threading.Event()
        self.run_entered = threading.Event()
        #: Set the instant ``stop()`` is entered. ``MCPChannel.stop()`` calls
        #: the server's ``stop()`` immediately before entering the thread join,
        #: so this is the join's starting gun for a test that must interrupt it.
        self.stop_entered = threading.Event()
        self.stop_calls = 0

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self._sock.settimeout(0.02)
        self.port: int = self._sock.getsockname()[1]

    def run(self) -> None:
        self.run_entered.set()
        try:
            while not self._shutdown.is_set():
                try:
                    conn, _ = self._sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                conn.close()
        finally:
            self._sock.close()

    def stop(self) -> None:
        self.stop_entered.set()
        self.stop_calls += 1
        if self._honour_stop:
            self._shutdown.set()

    def force_shutdown(self) -> None:
        """Teardown hatch. NOT named ``stop`` -- see :class:`_ServerWithoutStop`."""
        self._shutdown.set()


class _ServerWithoutStop(_RealServer):
    """A server exposing no ``stop()`` at all.

    ``MCPChannel.stop()`` branches on ``hasattr(self.mcp_server, "stop")``, so
    the attribute must genuinely be absent -- which is why the teardown hatch
    on the base class is called ``force_shutdown``.
    """

    def __init__(self) -> None:
        super().__init__(honour_stop=False)

    stop = None  # type: ignore[assignment]

    def __getattribute__(self, name: str):
        if name == "stop":
            raise AttributeError("stop")
        return object.__getattribute__(self, name)


def _port_is_serving(port: int) -> bool:
    """Independent witness: can a client still connect and be served?

    This is what "the channel stopped" is supposed to mean to the outside
    world, and it is measured through the socket rather than through any state
    the channel keeps about itself.
    """
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _mcp_channel(server: _RealServer, name: str) -> MCPChannel:
    return MCPChannel(
        ChannelConfig(name=name, channel_type=ChannelType.MCP, port=server.port),
        mcp_server=server,
    )


async def _teardown(channel: MCPChannel, server: _RealServer) -> None:
    server.force_shutdown()
    thread = channel._mcp_server_thread
    if thread is not None:
        await asyncio.to_thread(thread.join, 5.0)
    channel._mcp_server_thread = None
    channel.close()


class TestStopDoesNotReportStoppedOverALiveServerThread:
    """#2018 -- the headline. STOPPED over a thread that is still SERVING.

    ``cleaned`` gates STOPPED on ``_cleanup``, which covers ``_running_task``
    and the event queue and NOT the server thread. Both failing paths WARNed
    accurately and then recorded STOPPED anyway, so a caller that trusts the
    status proceeds to teardown while requests are still being answered.
    """

    @pytest.mark.asyncio
    async def test_join_timeout_is_not_reported_as_stopped(self) -> None:
        server = _RealServer(honour_stop=False)
        channel = _mcp_channel(server, "rt_mcp_join_timeout")
        # The status is what is under test, not the timeout's value. 5s of dead
        # waiting would measure the same property and cost 5s.
        channel._MCP_SERVER_JOIN_TIMEOUT = 0.4

        try:
            await channel.start()
            assert server.run_entered.wait(2.0), "premise: the serve loop never started"
            assert _port_is_serving(server.port), "premise: the server is not serving"

            await channel.stop()

            status = channel.status
            thread_alive = channel._mcp_server_thread is not None and (
                channel._mcp_server_thread.is_alive()
            )
            still_serving = _port_is_serving(server.port)
        finally:
            await _teardown(channel, server)

        # The premise of the whole test: the thread genuinely outlived stop().
        # Without this the assertions below could pass on a thread that died.
        assert thread_alive, "premise: the server thread did not outlive stop()"
        assert still_serving, "premise: the server stopped answering on its own"
        assert status is not ChannelStatus.STOPPED, (
            "stop() reported STOPPED while the MCP server thread was still "
            "ALIVE and still answering on its port"
        )
        assert status is ChannelStatus.STOPPING

    @pytest.mark.asyncio
    async def test_a_retry_does_not_clear_to_stopped_over_the_same_thread(
        self,
    ) -> None:
        """Dropping the handle would move the lie one call later, not fix it."""
        server = _RealServer(honour_stop=False)
        channel = _mcp_channel(server, "rt_mcp_retry")
        channel._MCP_SERVER_JOIN_TIMEOUT = 0.3

        try:
            await channel.start()
            assert server.run_entered.wait(2.0)

            await channel.stop()
            await channel.stop()

            status = channel.status
            still_serving = _port_is_serving(server.port)
        finally:
            await _teardown(channel, server)

        assert still_serving, "premise: the server stopped answering on its own"
        assert status is not ChannelStatus.STOPPED, (
            "the second stop() reported STOPPED over the same live thread; the "
            "handle was dropped instead of retained for re-observation"
        )

    @pytest.mark.asyncio
    async def test_server_without_a_stop_entrypoint_is_not_reported_as_stopped(
        self,
    ) -> None:
        server = _ServerWithoutStop()
        channel = _mcp_channel(server, "rt_mcp_no_stop")

        try:
            await channel.start()
            assert server.run_entered.wait(2.0)
            assert _port_is_serving(server.port), "premise: the server is not serving"

            await channel.stop()

            status = channel.status
            still_serving = _port_is_serving(server.port)
        finally:
            await _teardown(channel, server)

        assert still_serving, "premise: the server stopped answering on its own"
        assert status is not ChannelStatus.STOPPED, (
            "stop() reported STOPPED although the server exposes no stop(), so "
            "nothing could ever unwind its serve loop"
        )

    @pytest.mark.asyncio
    async def test_a_server_that_really_stops_still_reports_stopped(self) -> None:
        """The negative control, and it is load-bearing.

        Without it every assertion above is satisfied by a channel that NEVER
        reports STOPPED -- which would be a different way of lying, and would
        break every honest caller.
        """
        server = _RealServer(honour_stop=True)
        channel = _mcp_channel(server, "rt_mcp_honest")

        try:
            await channel.start()
            assert server.run_entered.wait(2.0)
            assert _port_is_serving(server.port), "premise: the server is not serving"
            thread = channel._mcp_server_thread

            await channel.stop()

            status = channel.status
            assert thread is not None
            thread_alive = thread.is_alive()
            # The handle is retained everywhere else, so this is the one place
            # it is released -- and the release has to still happen, or the
            # cancellation-safety fix would just be a leak.
            handle_released = channel._mcp_server_thread is None
            still_serving = _port_is_serving(server.port)
        finally:
            await _teardown(channel, server)

        assert not thread_alive, "the server thread should have exited"
        assert handle_released, (
            "an honest stop left the server-thread handle set; it must be "
            "cleared once the thread has been observed dead"
        )
        assert not still_serving, "the port should have been released"
        assert status is ChannelStatus.STOPPED, (
            f"an honest stop was downgraded to {status}; the fix must not "
            "refuse to report success"
        )

    @pytest.mark.asyncio
    async def test_cancelling_stop_during_the_join_retains_the_handle(self) -> None:
        """The retention must survive the case it was built for: cancellation.

        The two tests above cover the NON-cancelled paths, where the handle is
        put back after the join reports the thread still alive. But the restore
        sits AFTER the join's await, so a caller-aimed cancellation there skips
        it and the handle is already ``None`` -- and the next ``stop()`` then
        finds nothing to observe and clears straight to STOPPED over a port
        that is still answering. That is the identical #2018 lie one call
        later, which is exactly what
        ``test_a_retry_does_not_clear_to_stopped_over_the_same_thread`` pins
        for the non-cancelled path.

        Caller-aimed cancellation is this method's DESIGN CASE -- the entire
        ``cleanup_ran``/``close_ran``/``finally`` machinery exists for it -- so
        the retention has to hold on it too. The handle is therefore cleared
        only where the thread has been positively observed dead, never
        optimistically before an await.
        """
        server = _RealServer(honour_stop=False)
        channel = _mcp_channel(server, "rt_mcp_cancelled_join")
        # Long on purpose: the cancellation must land INSIDE the join. The join
        # cannot finish early because this server ignores stop(), so the test
        # spends only as long as the sleep below.
        channel._MCP_SERVER_JOIN_TIMEOUT = 5.0

        try:
            await channel.start()
            assert server.run_entered.wait(2.0), "premise: the serve loop never started"
            assert _port_is_serving(server.port), "premise: the server is not serving"
            thread = channel._mcp_server_thread
            assert thread is not None, "premise: no server thread was created"

            stopping = asyncio.create_task(channel.stop())
            # Wait for the join's starting gun rather than guessing at a sleep
            # long enough to cover every await before it.
            await asyncio.to_thread(server.stop_entered.wait, 2.0)
            await asyncio.sleep(0.1)
            stopping.cancel()
            with pytest.raises(asyncio.CancelledError):
                await stopping

            handle_after_cancel = channel._mcp_server_thread
            alive_after_cancel = thread.is_alive()
            serving_after_cancel = _port_is_serving(server.port)

            # The follow-up stop() is the one an orchestrator actually acts on.
            await channel.stop()
            status = channel.status
            serving_after_retry = _port_is_serving(server.port)
        finally:
            await _teardown(channel, server)

        assert alive_after_cancel, "premise: the server thread did not outlive the join"
        assert serving_after_cancel, "premise: the server stopped answering on its own"
        assert handle_after_cancel is thread, (
            "cancelling stop() inside the join dropped the server-thread "
            "handle; the restore is unreachable on the cancelled path"
        )
        assert serving_after_retry, "premise: the server stopped answering on its own"
        assert status is not ChannelStatus.STOPPED, (
            "the stop() following a cancelled stop() reported STOPPED while "
            "the server thread was still ALIVE and still answering on its port"
        )


class TestTheServerThreadJoinDoesNotFreezeTheEventLoop:
    """#2019 -- ``Thread.join(timeout=...)`` is synchronous.

    The shipped 5s timeout meant a five-second freeze of the ENTIRE loop at
    shutdown, stalling sibling channels' stops and the shutdown deadline
    itself. Counting heartbeat ticks DURING the stop is what discriminates: a
    frozen loop cannot run them, and no property of ``stop()``'s own return
    tells the two states apart.
    """

    @pytest.mark.asyncio
    async def test_other_tasks_keep_running_while_the_join_is_outstanding(
        self,
    ) -> None:
        server = _RealServer(honour_stop=False)
        channel = _mcp_channel(server, "rt_mcp_heartbeat")
        join_timeout = 0.6
        channel._MCP_SERVER_JOIN_TIMEOUT = join_timeout

        ticks = 0

        async def _heartbeat() -> None:
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        try:
            await channel.start()
            assert server.run_entered.wait(2.0)

            beat = asyncio.ensure_future(_heartbeat())
            await asyncio.sleep(0.05)  # let the heartbeat establish itself
            ticks = 0

            wall_start = time.monotonic()
            await channel.stop()
            elapsed = time.monotonic() - wall_start

            observed = ticks
            beat.cancel()
            await asyncio.gather(beat, return_exceptions=True)
        finally:
            await _teardown(channel, server)

        # Premise: the join really was outstanding for about the full timeout.
        # If stop() returned instantly the tick count proves nothing.
        assert elapsed >= join_timeout * 0.8, (
            f"premise: stop() returned in {elapsed:.3f}s, so the join never "
            f"blocked for its {join_timeout}s timeout and this measures nothing"
        )
        # A free loop runs ~60 ticks in 0.6s. A frozen one runs 0.
        assert observed >= 10, (
            f"only {observed} heartbeat ticks ran during a {elapsed:.2f}s "
            "stop(); the thread join blocked the event loop"
        )


class TestCloseIsRetriedWhenCloseItselfRaises:
    """#2020 -- the retry was unreachable in the one case it exists for.

    ``_cleanup() -> cleanup_ran = True -> close()``. When ``close()`` raised,
    the ``finally``'s guarded retry was skipped because the flag it keyed on
    was already ``True``, and the runtime reference stayed stranded.
    """

    @staticmethod
    def _fail_close_once(channel) -> list[int]:
        """Make the FIRST close() raise. Later calls do the real work.

        A persistent failure cannot discriminate -- the runtime is stranded
        under both the old and new code, so only a TRANSIENT failure shows
        whether the retry fires at all.
        """
        calls: list[int] = []
        real_close = channel.close

        def _close() -> None:
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("release() failed transiently")
            real_close()

        channel.close = _close  # type: ignore[method-assign]
        return calls

    @pytest.mark.asyncio
    async def test_cli_channel_retries_close_and_releases_the_runtime(self) -> None:
        channel = CLIChannel(
            ChannelConfig(name="rt_cli_close", channel_type=ChannelType.CLI)
        )
        channel.status = ChannelStatus.RUNNING
        calls = self._fail_close_once(channel)

        with pytest.raises(RuntimeError, match="release\\(\\) failed transiently"):
            await channel.stop()

        stranded = getattr(channel, "runtime", None) is not None

        assert len(calls) == 2, (
            f"close() was called {len(calls)} time(s); the guarded retry never "
            "fired because it keyed on cleanup_ran, which was already True"
        )
        assert not stranded, "close() was not retried, so the runtime is stranded"

    @pytest.mark.asyncio
    async def test_mcp_channel_retries_close_and_releases_the_runtime(self) -> None:
        server = _RealServer(honour_stop=True)
        channel = _mcp_channel(server, "rt_mcp_close")
        channel.status = ChannelStatus.RUNNING
        calls = self._fail_close_once(channel)

        try:
            with pytest.raises(RuntimeError, match="release\\(\\) failed transiently"):
                await channel.stop()

            stranded = getattr(channel, "runtime", None) is not None
        finally:
            server.force_shutdown()

        assert len(calls) == 2, (
            f"close() was called {len(calls)} time(s); the guarded retry never "
            "fired because it keyed on cleanup_ran, which was already True"
        )
        assert not stranded, "close() was not retried, so the runtime is stranded"

    @pytest.mark.asyncio
    async def test_a_close_that_succeeds_is_not_called_twice(self) -> None:
        """Negative control: a second flag must not mean a second close().

        ``close()`` is idempotent, so a redundant call would be silent -- which
        is exactly why it needs pinning rather than assuming.
        """
        channel = CLIChannel(
            ChannelConfig(name="rt_cli_close_ok", channel_type=ChannelType.CLI)
        )
        channel.status = ChannelStatus.RUNNING

        calls: list[int] = []
        real_close = channel.close

        def _close() -> None:
            calls.append(1)
            real_close()

        channel.close = _close  # type: ignore[method-assign]

        await channel.stop()

        assert channel.status is ChannelStatus.STOPPED
        assert len(calls) == 1, f"close() ran {len(calls)} times on the happy path"


class TestADiedEventTaskIsNotReportedAsStopping:
    """#2021 -- ``STOPPING`` means "still running, stop it again".

    That advice is true for a task that IGNORED its cancellation and false for
    one that DIED: the task is gone, so a retry finds nothing to cancel and
    clears to STOPPED, laundering a failed teardown into a clean stop. Both
    conditions returned ``complete=False`` and were indistinguishable.
    """

    @staticmethod
    async def _run_with_event_task(channel, task: asyncio.Task) -> ChannelStatus:
        channel._running_task = task
        channel._server_task = None
        channel.status = ChannelStatus.RUNNING
        await channel.stop()
        return channel.status

    @pytest.mark.asyncio
    async def test_a_died_event_task_reports_error_not_stopping(self) -> None:
        async def _dies_on_cancel() -> None:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                raise ValueError("backing store gone") from None

        task = asyncio.ensure_future(_dies_on_cancel())
        await asyncio.sleep(0.05)
        assert not task.done(), "premise: the task must be running to be cancelled"

        server = _RealServer(honour_stop=True)
        channel = _mcp_channel(server, "rt_mcp_died")
        try:
            status = await self._run_with_event_task(channel, task)
            retry_status = (await channel.stop(), channel.status)[1]
        finally:
            server.force_shutdown()
            await asyncio.gather(task, return_exceptions=True)

        assert status is ChannelStatus.ERROR, (
            f"a DIED event task reported {status}; STOPPING tells the caller to "
            "stop again, and there is nothing left to stop"
        )
        assert (
            retry_status is ChannelStatus.ERROR
        ), f"retrying stop() laundered the failure to {retry_status}"

    @pytest.mark.asyncio
    async def test_a_live_event_task_still_reports_stopping(self) -> None:
        """The other half. Distinguishing the two must not collapse them the
        other way -- a live task IS retryable and STOPPING is the right advice.
        """
        release = asyncio.Event()

        async def _ignores_cancel() -> None:
            while True:
                try:
                    await asyncio.sleep(0.01)
                except asyncio.CancelledError:
                    if release.is_set():
                        raise
                    continue

        task = asyncio.ensure_future(_ignores_cancel())
        await asyncio.sleep(0.05)
        assert not task.done()

        server = _RealServer(honour_stop=True)
        channel = _mcp_channel(server, "rt_mcp_live")
        try:
            status = await self._run_with_event_task(channel, task)
        finally:
            server.force_shutdown()
            release.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        assert status is ChannelStatus.STOPPING, (
            f"a LIVE event task reported {status}; it is still running and "
            "stopping again is exactly what the caller should do"
        )
