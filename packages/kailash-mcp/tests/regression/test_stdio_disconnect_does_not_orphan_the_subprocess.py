"""A failed subprocess termination must not report "disconnected".

The defect: ``EnhancedStdioTransport.disconnect`` wrapped termination in a broad
``except Exception`` that logged and swallowed, then a ``finally`` nulled
``self.process`` regardless, then an unconditional
``logger.info("STDIO transport disconnected")`` fired.

Three consequences, and the third is what makes it HIGH rather than cosmetic:

1. The last line a status scraper sees says the transport disconnected.
2. The child process may still be running — a real OS resource, leaked.
3. Dropping the handle makes it **unrecoverable in-process**: nothing can ever
   retry the kill, because nothing still refers to the process.

An orchestrator treating "disconnected" as a completion signal proceeds while an
MCP subprocess is still alive.

The process double is a deterministic in-process stand-in, not a ``MagicMock``:
a Mock auto-satisfies every attribute and returns truthy sentinels, so
``terminate`` "succeeding" would be indistinguishable from it never being
called. This one records what it was asked to do and can be told to fail.
"""

import asyncio
import logging

import pytest
from kailash_mcp.transports.transports import EnhancedStdioTransport

pytestmark = pytest.mark.regression


class _FakeProcess:
    """Deterministic asyncio-subprocess stand-in.

    ``terminate_raises`` models the case the defect swallowed: the OS refuses
    the signal (EPERM, a zombie parent, a container PID-namespace edge) and the
    child keeps running.
    """

    def __init__(self, pid=4242, terminate_raises=None, exits_on_terminate=True):
        self.pid = pid
        self.returncode = None
        self.terminate_called = False
        self.kill_called = False
        self._terminate_raises = terminate_raises
        self._exits_on_terminate = exits_on_terminate
        self.stdin = None

    def terminate(self):
        self.terminate_called = True
        if self._terminate_raises is not None:
            raise self._terminate_raises
        if self._exits_on_terminate:
            self.returncode = 0

    def kill(self):
        self.kill_called = True
        self.returncode = -9

    async def wait(self):
        if self.returncode is None:
            # Models a child that ignores the signal: never exits on its own.
            await asyncio.sleep(3600)
        return self.returncode

    @property
    def alive(self) -> bool:
        return self.returncode is None


def _transport() -> EnhancedStdioTransport:
    t = EnhancedStdioTransport(command="echo", allow_arbitrary_commands=True)
    t._connected = True
    return t


def _disconnect_success_lines(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if "STDIO transport disconnected" in r.getMessage()
    ]


class TestFailedTerminationIsNotReportedAsDisconnected:
    @pytest.mark.asyncio
    async def test_no_success_line_when_termination_raises(self, caplog):
        """The success line must not fire for a termination that failed."""
        transport = _transport()
        transport.process = _FakeProcess(terminate_raises=PermissionError("EPERM"))

        with caplog.at_level(logging.INFO):
            await transport.disconnect()

        assert _disconnect_success_lines(caplog) == [], (
            "the transport reported 'STDIO transport disconnected' after "
            "termination failed; a status scraper reads this as a clean stop "
            f"while the child is still alive: {_disconnect_success_lines(caplog)!r}"
        )

    @pytest.mark.asyncio
    async def test_the_handle_is_retained_so_a_retry_is_possible(self):
        """Nulling the handle is what makes the orphan unrecoverable."""
        transport = _transport()
        proc = _FakeProcess(terminate_raises=PermissionError("EPERM"))
        transport.process = proc

        await transport.disconnect()

        assert transport.process is proc, (
            "the process handle was dropped after a FAILED termination — "
            "nothing can retry the kill, so the child is orphaned for the "
            "lifetime of the interpreter"
        )

    @pytest.mark.asyncio
    async def test_a_second_disconnect_retries_the_termination(self):
        """Retaining the handle is useless if the retry short-circuits.

        ``disconnect`` early-returns on ``not self._connected``, and the flag is
        cleared BEFORE termination is attempted — so after a failure the second
        call returned immediately without retrying. Both the handle and the
        entry condition have to allow the retry.
        """
        transport = _transport()
        failing = _FakeProcess(terminate_raises=PermissionError("EPERM"))
        transport.process = failing
        await transport.disconnect()
        assert failing.terminate_called, "precondition: the first attempt ran"

        # The condition clears; a retry must now actually attempt termination.
        recovered = _FakeProcess()
        transport.process = recovered

        await transport.disconnect()

        assert recovered.terminate_called, (
            "the second disconnect() short-circuited and never retried "
            "termination, so a recoverable orphan stays orphaned"
        )
        assert transport.process is None, "a SUCCESSFUL retry should clear the handle"

    @pytest.mark.asyncio
    async def test_the_failure_names_the_surviving_process(self, caplog):
        """An operator needs the pid to kill it by hand."""
        transport = _transport()
        transport.process = _FakeProcess(pid=31337, terminate_raises=OSError("boom"))

        with caplog.at_level(logging.ERROR):
            await transport.disconnect()

        errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("31337" in m for m in errors), (
            "the failure log does not name the surviving pid, so an operator "
            f"cannot clean it up: {errors!r}"
        )


class TestSuccessfulTerminationStillReportsSuccess:
    """CONTROL. Without these, deleting the success line entirely would satisfy
    every assertion above — 'never claims success' and 'never reports success'
    are different properties."""

    @pytest.mark.asyncio
    async def test_graceful_termination_reports_disconnected_and_clears(self, caplog):
        transport = _transport()
        proc = _FakeProcess()
        transport.process = proc

        with caplog.at_level(logging.INFO):
            await transport.disconnect()

        assert proc.terminate_called, "graceful termination was never attempted"
        assert _disconnect_success_lines(caplog), (
            "a SUCCESSFUL disconnect stopped reporting success — the fix must "
            "suppress the false line, not the true one"
        )
        assert transport.process is None, "a successful stop should clear the handle"

    @pytest.mark.asyncio
    async def test_escalates_to_kill_when_graceful_stop_is_ignored(self, caplog):
        """A child that ignores SIGTERM must still be killed, then reported."""
        transport = _transport()
        proc = _FakeProcess(exits_on_terminate=False)
        transport.process = proc

        with caplog.at_level(logging.INFO):
            await transport.disconnect()

        assert proc.terminate_called, "graceful termination was never attempted"
        assert proc.kill_called, (
            "the child ignored terminate() and was never killed — a graceful "
            "stop with no follow-up is exactly how the orphan survives"
        )
        assert not proc.alive, "the process was left running after disconnect()"
        assert _disconnect_success_lines(caplog), "a successful kill should report"

    @pytest.mark.asyncio
    async def test_disconnect_is_a_noop_when_never_connected(self, caplog):
        transport = EnhancedStdioTransport(
            command="echo", allow_arbitrary_commands=True
        )

        with caplog.at_level(logging.INFO):
            await transport.disconnect()

        assert (
            _disconnect_success_lines(caplog) == []
        ), "a transport that was never connected reported a disconnect"
