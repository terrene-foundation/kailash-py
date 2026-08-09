"""Regression pins for the three defects the integration redteam found.

All three were introduced or left open by the F10/F11/F13 shard merge, and all
three were invisible to the suites those shards shipped -- which is the reason
this file exists rather than an extra case inside each shard's own test. Each
test below was confirmed to RED against the pre-fix code before the fix landed;
a test that passes either way would pin nothing.

1. ``safe_callable_name`` documents that it never raises on account of the
   object it describes, and did. ``getattr(x, attr, default)`` suppresses ONLY
   ``AttributeError``; a lazy proxy raising anything else escaped. Two callers
   invoke it INSIDE an ``except`` block, where the escape REPLACES the exception
   being handled, and one calls it BEFORE its ``try``, where it defeats that
   function's documented per-handler isolation.

2. The monitoring-start path logged a raw exception object as a ``%s``
   argument. ``_broadcast_metrics`` reaches the task manager and the dashboard's
   backing store, so the text can carry a DSN or a token. This tree has no
   scrubber available to it, so the sink must not render the message at all.

3. ``stop()`` was changed to let a caller-aimed ``CancelledError`` propagate --
   correct -- but the propagation skipped ``_cleanup``, which cancels a
   DIFFERENT task from the one being awaited. The dominant trigger is a task
   group tearing down, where nobody calls ``stop()`` again, so the task was
   orphaned and (for the CLI channel) the runtime reference stranded.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from kailash.channels.api_channel import APIChannel
from kailash.channels.base import ChannelConfig, ChannelStatus, ChannelType
from kailash.channels.cli_channel import CLIChannel
from kailash.utils.secure_logging import safe_callable_name

pytestmark = pytest.mark.regression


class _RaisingProxy:
    """A lazy proxy whose attribute reads raise something other than AttributeError.

    This is the ordinary shape, not an exotic one: a Werkzeug/Flask
    ``LocalProxy`` raises ``RuntimeError("Working outside of request context")``
    and an unbound client raises ``ConnectionError``.
    """

    def __getattr__(self, name: str):
        raise RuntimeError("Working outside of request context")


class _HostileClassProxy:
    """``__class__`` is consulted by ``isinstance`` and is caller-controlled."""

    @property  # type: ignore[misc]
    def __class__(self):
        raise ConnectionError("backing service unavailable")


class TestSafeCallableNameHonorsItsNeverRaisesContract:
    def test_proxy_raising_runtime_error_yields_a_name_instead_of_propagating(
        self,
    ) -> None:
        # Pre-fix this raised RuntimeError out of a logging helper.
        assert safe_callable_name(_RaisingProxy()) == "_RaisingProxy"

    def test_hostile_dunder_class_does_not_propagate_through_isinstance(self) -> None:
        # Reached via the isinstance(target, functools.partial) branch.
        assert isinstance(safe_callable_name(_HostileClassProxy()), str)

    def test_cancellation_is_NOT_swallowed(self) -> None:
        """The guard is ``Exception``, deliberately not ``BaseException``.

        A cancellation is the program being stopped, not the object
        misbehaving. Swallowing it here would re-open at the logging layer the
        exact defect the channel-lifecycle work closed at the channel layer, so
        this is pinned in the opposite direction from the two tests above.
        """

        class _CancelOnRead:
            def __getattr__(self, name: str):
                raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            safe_callable_name(_CancelOnRead())


class TestMonitoringRestartDoesNotRenderThePreviousException:
    @pytest.mark.asyncio
    async def test_previous_broadcast_error_text_is_not_logged(self, caplog) -> None:
        from kailash.visualization import api as viz_api

        secret = "postgres://svc:hunter2@db.internal:5432/metrics"

        async def _fail() -> None:
            raise ConnectionError(f"could not connect to {secret}")

        dead = asyncio.ensure_future(_fail())
        await asyncio.sleep(0)
        with pytest.raises(ConnectionError):
            await dead

        logger = logging.getLogger(f"{__name__}.viz")
        with caplog.at_level(logging.WARNING, logger=logger.name):
            previous_error = dead.exception()
            assert previous_error is not None
            # The production shape, lifted verbatim from
            # ``visualization/api.py``'s start_monitoring restart branch.
            logger.warning(
                "Previous metrics broadcast task ended with an "
                "error; starting a replacement: %s at %s",
                type(previous_error).__name__,
                viz_api.safe_exception_frames(previous_error, limit=3),
            )

        rendered = caplog.text
        assert secret not in rendered
        assert "hunter2" not in rendered
        # Still a usable diagnostic: the type survives.
        assert "ConnectionError" in rendered

    def test_the_restart_branch_does_not_pass_the_exception_object(self) -> None:
        """AST pin on the real source, so a future edit cannot quietly re-add it.

        The behavioural test above exercises the SHAPE; this one pins the actual
        production call site, which is what a regression would touch.
        """
        import ast
        import inspect

        from kailash.visualization import api as viz_api

        tree = ast.parse(inspect.getsource(viz_api))
        offenders: list[int] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "warning"):
                continue
            for arg in node.args[1:]:
                if isinstance(arg, ast.Name) and arg.id == "previous_error":
                    offenders.append(node.lineno)
        assert offenders == [], (
            f"visualization/api.py passes the raw previous_error object to "
            f"logger.warning at line(s) {offenders}. Log its type and frames; "
            "this tree has no scrubber available to it."
        )


class TestStopRunsCleanupEvenWhenTheCallerIsCancelled:
    """``_cleanup`` cancels ``_running_task``, which is NOT the awaited task.

    THE AWAITED TASK MUST GENUINELY IGNORE CANCELLATION or this pins nothing.
    ``stop()`` cancels that task and then parks in ``asyncio.wait``; if the task
    dies on the first cancel, ``wait`` returns at once and ``stop()`` runs to
    completion before the test can cancel it. The test then fails "DID NOT
    RAISE" whether or not the defect is present -- red for the wrong reason,
    which is not evidence. ``asyncio.shield`` does NOT produce this: cancelling
    the shield's OUTER future cancels that future immediately, which is exactly
    the mistake the first draft of this test made.
    """

    @staticmethod
    def _uncancellable() -> tuple[asyncio.Task, asyncio.Event]:
        release = asyncio.Event()

        async def _ignores_cancel() -> None:
            while True:
                try:
                    await asyncio.sleep(0.01)
                except asyncio.CancelledError:
                    if release.is_set():
                        raise
                    continue

        return asyncio.ensure_future(_ignores_cancel()), release

    @staticmethod
    async def _kill(task: asyncio.Task, release: asyncio.Event) -> None:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_api_channel_cancels_running_task_on_cancelled_stop(self) -> None:
        channel = APIChannel(
            ChannelConfig(name="rt_api", channel_type=ChannelType.API, port=18997)
        )

        async def _never() -> None:
            await asyncio.Event().wait()

        server_task, release = self._uncancellable()
        running_task = asyncio.ensure_future(_never())
        channel._server_task = server_task
        channel._running_task = running_task
        channel.status = ChannelStatus.RUNNING

        stopper = asyncio.ensure_future(channel.stop())
        await asyncio.sleep(0.05)  # let stop() reach asyncio.wait
        assert not stopper.done(), "stop() must still be parked in asyncio.wait"
        stopper.cancel()
        with pytest.raises(asyncio.CancelledError):
            await stopper

        await asyncio.sleep(0.05)
        assert running_task.cancelled() or running_task.done(), (
            "_running_task was left pending after a cancelled stop(); "
            "_cleanup did not run, so the task is orphaned"
        )
        assert channel.status is ChannelStatus.STOPPING

        await self._kill(server_task, release)

    @pytest.mark.asyncio
    async def test_cli_channel_releases_runtime_on_cancelled_stop(self) -> None:
        channel = CLIChannel(ChannelConfig(name="rt_cli", channel_type=ChannelType.CLI))

        async def _never() -> None:
            await asyncio.Event().wait()

        main_task, release = self._uncancellable()
        running_task = asyncio.ensure_future(_never())
        channel._main_task = main_task
        channel._running_task = running_task
        channel.status = ChannelStatus.RUNNING

        stopper = asyncio.ensure_future(channel.stop())
        await asyncio.sleep(0.05)  # let stop() reach asyncio.wait
        assert not stopper.done(), "stop() must still be parked in asyncio.wait"
        stopper.cancel()
        with pytest.raises(asyncio.CancelledError):
            await stopper

        await asyncio.sleep(0.05)
        assert (
            running_task.cancelled() or running_task.done()
        ), "_running_task was left pending after a cancelled stop()"
        assert (
            getattr(channel, "runtime", None) is None
        ), "close() did not run, so the runtime reference is stranded"

        await self._kill(main_task, release)
