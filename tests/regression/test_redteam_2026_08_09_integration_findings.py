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
        orphaned = not (running_task.cancelled() or running_task.done())
        # Tear down BEFORE asserting. On the pre-fix code ``_running_task`` is
        # precisely what is left pending, and leaving it pending hangs loop
        # teardown -- which would make the fail-first run UN-RUNNABLE rather
        # than RED, and an un-runnable check is zero evidence either way.
        running_task.cancel()
        await asyncio.gather(running_task, return_exceptions=True)
        await self._kill(server_task, release)

        assert not orphaned, (
            "_running_task was left pending after a cancelled stop(); "
            "_cleanup did not run, so the task is orphaned"
        )
        assert channel.status is ChannelStatus.STOPPING

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
        orphaned = not (running_task.cancelled() or running_task.done())
        stranded = getattr(channel, "runtime", None) is not None
        # Tear down before asserting -- see the sibling test above.
        running_task.cancel()
        await asyncio.gather(running_task, return_exceptions=True)
        await self._kill(main_task, release)

        assert not orphaned, "_running_task was left pending after a cancelled stop()"
        assert not stranded, "close() did not run, so the runtime reference is stranded"


class TestCleanupFailureDoesNotReplaceTheCallerCancellation:
    """Round 2 found the F13 defect reintroduced INSIDE its own fix.

    ``_cleanup`` swallows only ``CancelledError``, so a ``_running_task`` that
    died of a REAL error re-raises out of the ``finally`` and REPLACES the
    propagating ``CancelledError`` -- demoting the caller's cancellation to
    ``__context__``. That is precisely the swallowed-cancellation defect the
    F13 work exists to close, one layer down. The CLI variant additionally
    skipped ``close()``, stranding the runtime the block was added to release.
    """

    @pytest.mark.asyncio
    async def test_api_channel_cleanup_error_does_not_mask_cancellation(self) -> None:
        channel = APIChannel(
            ChannelConfig(name="rt_api2", channel_type=ChannelType.API, port=18996)
        )

        release = asyncio.Event()

        async def _ignores_cancel() -> None:
            while True:
                try:
                    await asyncio.sleep(0.01)
                except asyncio.CancelledError:
                    if release.is_set():
                        raise
                    continue

        server_task = asyncio.ensure_future(_ignores_cancel())
        channel._server_task = server_task
        channel.status = ChannelStatus.RUNNING

        async def _exploding_cleanup() -> None:
            raise RuntimeError("backing store gone")

        channel._cleanup = _exploding_cleanup  # type: ignore[method-assign]

        stopper = asyncio.ensure_future(channel.stop())
        await asyncio.sleep(0.05)
        assert not stopper.done()
        stopper.cancel()

        # CAPTURE -> TEAR DOWN -> ASSERT. Asserting first means a FAILING run
        # never reaches the teardown below, and the uncancellable task then
        # hangs loop teardown -- so the test dies by SIGKILL with no report
        # instead of failing readably. An un-runnable check is zero evidence in
        # either direction. This is the same ordering defect the strand pins
        # already fixed; it survived here because this class was written first.
        outcome: BaseException | None = None
        try:
            await stopper
        except BaseException as exc:  # noqa: BLE001 - the outcome IS the assertion
            outcome = exc

        release.set()
        server_task.cancel()
        await asyncio.gather(server_task, return_exceptions=True)

        # The caller asked for cancellation; a failing cleanup must not convert
        # that into RuntimeError.
        assert isinstance(outcome, asyncio.CancelledError), (
            f"stop() raised {type(outcome).__name__ if outcome else 'nothing'}; "
            "a failing _cleanup replaced the caller's cancellation"
        )

    @pytest.mark.asyncio
    async def test_cli_channel_closes_runtime_even_when_cleanup_raises(self) -> None:
        channel = CLIChannel(
            ChannelConfig(name="rt_cli2", channel_type=ChannelType.CLI)
        )

        release = asyncio.Event()

        async def _ignores_cancel() -> None:
            while True:
                try:
                    await asyncio.sleep(0.01)
                except asyncio.CancelledError:
                    if release.is_set():
                        raise
                    continue

        main_task = asyncio.ensure_future(_ignores_cancel())
        channel._main_task = main_task
        channel.status = ChannelStatus.RUNNING

        async def _exploding_cleanup() -> None:
            raise RuntimeError("backing store gone")

        channel._cleanup = _exploding_cleanup  # type: ignore[method-assign]

        stopper = asyncio.ensure_future(channel.stop())
        await asyncio.sleep(0.05)
        assert not stopper.done()
        stopper.cancel()
        # CAPTURE -> TEAR DOWN -> ASSERT; see the sibling test above.
        outcome: BaseException | None = None
        try:
            await stopper
        except BaseException as exc:  # noqa: BLE001 - the outcome IS the assertion
            outcome = exc
        stranded = getattr(channel, "runtime", None) is not None

        release.set()
        main_task.cancel()
        await asyncio.gather(main_task, return_exceptions=True)

        assert isinstance(outcome, asyncio.CancelledError), (
            f"stop() raised {type(outcome).__name__ if outcome else 'nothing'}; "
            "a failing _cleanup replaced the caller's cancellation"
        )
        assert (
            not stranded
        ), "close() was skipped because _cleanup raised; the runtime is stranded"


class TestCleanupJoinCannotStrandTheCaller:
    """The `finally` fix re-opened, one task over, what it set out to close.

    ``_cleanup`` used ``await self._running_task``. Running that from
    ``stop()``'s ``finally`` means a ``_running_task`` which IGNORES
    cancellation never completes the join, so the ``finally`` never completes
    and the caller who asked to be cancelled never regains control -- a strand,
    which the F13 shard's own commit body calls WORSE than the swallow it
    replaced. The existing pair varies the AWAITED task; this varies
    ``_running_task``, which is the one nothing else covers.
    """

    @pytest.mark.asyncio
    async def test_uncancellable_running_task_does_not_hold_the_caller(self) -> None:
        channel = APIChannel(
            ChannelConfig(name="rt_api3", channel_type=ChannelType.API, port=18995)
        )

        release = asyncio.Event()

        async def _ignores_cancel() -> None:
            while True:
                try:
                    await asyncio.sleep(0.01)
                except asyncio.CancelledError:
                    if release.is_set():
                        raise
                    continue

        server_task = asyncio.ensure_future(_ignores_cancel())
        running_task = asyncio.ensure_future(_ignores_cancel())
        channel._server_task = server_task
        channel._running_task = running_task
        channel.status = ChannelStatus.RUNNING

        stopper = asyncio.ensure_future(channel.stop())
        await asyncio.sleep(0.05)
        stopper.cancel()

        # Bounded observation, never wait_for: this file's own lesson is that a
        # hang must present as a readable result, not as a dead run.
        done, pending = await asyncio.wait({stopper}, timeout=3.0)
        stranded = bool(pending)

        release.set()
        for task in (server_task, running_task, stopper):
            task.cancel()
        await asyncio.gather(server_task, running_task, stopper, return_exceptions=True)

        assert not stranded, (
            "stop() never returned to a cancelled caller because _cleanup "
            "joined an uncancellable _running_task without a bound"
        )


class TestIncompleteCleanupIsNotReportedAsStopped:
    """Round 3: bounding the join traded a hang for a LIE.

    ``asyncio.wait`` returns ``(done, pending)``. Discarding it left nothing to
    distinguish "the task stopped" from "the timeout elapsed and it is still
    running" -- so cleanup logged success and ``stop()`` recorded ``STOPPED``
    over a live task. A hang is loud; a false status is silent, and a status
    field is a return value an orchestrator acts on. The sibling bounded join in
    ``visualization/api.py`` already refuses to claim success on timeout; this
    pins the same property for the channel path.
    """

    @pytest.mark.asyncio
    async def test_uncancellable_event_task_yields_stopping_not_stopped(self) -> None:
        channel = APIChannel(
            ChannelConfig(name="rt_api4", channel_type=ChannelType.API, port=18994)
        )

        release = asyncio.Event()

        async def _ignores_cancel() -> None:
            while True:
                try:
                    await asyncio.sleep(0.01)
                except asyncio.CancelledError:
                    if release.is_set():
                        raise
                    continue

        running_task = asyncio.ensure_future(_ignores_cancel())
        # LET IT ACTUALLY START. `ensure_future` only schedules; cancelling a
        # task that has never been entered cancels it outright, so the
        # ignore-cancellation handler never runs and the task dies on the first
        # cancel.
        #
        # MEASURED, because the intuitive reading of this is WRONG: without the
        # yield the test does not vacuously PASS, it fails BOTH ways. The task
        # dies immediately, cleanup legitimately completes, STOPPED is the
        # CORRECT status -- and the assertion calls that a defect. So the yield
        # guards against a FALSE POSITIVE, not a vacuous pass, and
        # `assert not running_task.done()` is what makes its removal detectable
        # rather than merely wrong.
        await asyncio.sleep(0.05)
        assert not running_task.done()

        channel._running_task = running_task
        channel._server_task = None
        channel.status = ChannelStatus.RUNNING

        # Success path: nothing cancels stop(); it runs to completion and the
        # only thing that can go wrong is the event task refusing to die.
        await channel.stop()

        status = channel.status
        release.set()
        running_task.cancel()
        await asyncio.gather(running_task, return_exceptions=True)

        assert status is not ChannelStatus.STOPPED, (
            "stop() reported STOPPED while the event task was still live; the "
            "bounded join's timeout was discarded instead of surfaced"
        )
        assert status is ChannelStatus.STOPPING

    @pytest.mark.asyncio
    async def test_mcp_channel_also_declines_to_report_stopped(self) -> None:
        """The THIRD channel. Two of three is how this defect got here.

        `MCPChannel` inherits the same bounded join, and was left on the
        unqualified `status = STOPPED` when the other two were fixed. Pinning
        only the channels that were in the lens is what let the sibling gap
        survive the sweep in the first place.
        """
        from kailash.channels.mcp_channel import MCPChannel

        channel = MCPChannel(
            ChannelConfig(name="rt_mcp", channel_type=ChannelType.MCP, port=18992)
        )

        release = asyncio.Event()

        async def _ignores_cancel() -> None:
            while True:
                try:
                    await asyncio.sleep(0.01)
                except asyncio.CancelledError:
                    if release.is_set():
                        raise
                    continue

        running_task = asyncio.ensure_future(_ignores_cancel())
        await asyncio.sleep(0.05)
        assert not running_task.done()

        channel._running_task = running_task
        channel._server_task = None
        channel.status = ChannelStatus.RUNNING

        await channel.stop()

        status = channel.status
        release.set()
        running_task.cancel()
        await asyncio.gather(running_task, return_exceptions=True)

        assert status is not ChannelStatus.STOPPED, (
            "MCPChannel reported STOPPED while its event task was still live; "
            "the parity sweep reached two of three channels"
        )

    @pytest.mark.asyncio
    async def test_event_task_dying_of_a_real_error_is_surfaced_not_swallowed(
        self, caplog
    ) -> None:
        """The OTHER way cleanup is incomplete, and the one nothing covered.

        ``asyncio.wait`` does not re-raise -- that is why it replaced the
        ``await`` that displaced the caller's cancellation -- so a task that
        died of a real error was silently swallowed once ``done`` was
        discarded. This pins the retrieval: the error surfaces as TYPE + FRAMES
        (never the message, per the F10 discipline), and the status follows.
        """
        channel = APIChannel(
            ChannelConfig(name="rt_api6", channel_type=ChannelType.API, port=18991)
        )

        secret = "postgres://svc:hunter2@db.internal:5432/x"

        async def _dies_on_cancel() -> None:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                raise ValueError(f"backing store gone: {secret}") from None

        running_task = asyncio.ensure_future(_dies_on_cancel())
        await asyncio.sleep(0.05)
        assert not running_task.done()

        channel._running_task = running_task
        channel._server_task = None
        channel.status = ChannelStatus.RUNNING

        with caplog.at_level(logging.WARNING):
            await channel.stop()

        status = channel.status
        rendered = caplog.text
        await asyncio.gather(running_task, return_exceptions=True)

        assert status is ChannelStatus.STOPPING, (
            "the event task died of a real error, so cleanup did NOT complete; "
            "STOPPED would report a clean stop over a failed teardown"
        )
        assert "ValueError" in rendered, "the task's error was swallowed"
        # F10 discipline: the type and the frames, never the message.
        assert secret not in rendered
        assert "hunter2" not in rendered

    @pytest.mark.asyncio
    async def test_complete_cleanup_still_reports_stopped(self) -> None:
        """Negative control: the honest path must NOT be downgraded."""
        channel = APIChannel(
            ChannelConfig(name="rt_api5", channel_type=ChannelType.API, port=18993)
        )

        async def _cooperative() -> None:
            await asyncio.Event().wait()

        running_task = asyncio.ensure_future(_cooperative())
        channel._running_task = running_task
        channel._server_task = None
        channel.status = ChannelStatus.RUNNING

        await channel.stop()

        assert channel.status is ChannelStatus.STOPPED
        assert running_task.cancelled() or running_task.done()


class TestSafeExceptionFramesIsBounded:
    """Round 7, rotated onto the helper THIS BRANCH introduced.

    It is live in 8 production sinks and its whole job is disclosure control,
    and no round had adversarially probed it until the seventh.
    """

    def test_chain_length_is_capped_and_says_so(self) -> None:
        """`seen` stops a CYCLE; nothing stopped a long ACYCLIC chain.

        A retry loop doing ``raise X from prev`` drove 5000 links into a single
        175,000-character log record — the log-spam mode `observability.md`
        forbids, on an error path an attacker can drive.
        """
        from kailash.utils.secure_logging import (
            _MAX_CHAIN_LINKS,
            safe_exception_frames,
        )

        exc: BaseException = ValueError("root")
        for i in range(200):
            try:
                raise RuntimeError(f"wrap-{i}") from exc
            except RuntimeError as wrapped:
                exc = wrapped

        rendered = safe_exception_frames(exc, limit=3)

        assert rendered.count(" <- ") <= _MAX_CHAIN_LINKS, (
            f"chain rendered {rendered.count(' <- ') + 1} links from a 200-deep "
            "chain; the cap did not apply"
        )
        assert len(rendered) < 10_000, f"single log record is {len(rendered)} chars"
        # Truncation must be VISIBLE — a silently-trimmed chain reads as a short
        # one, and the reader cannot tell a 2-link failure from a retry storm.
        assert "cap reached" in rendered

    def test_limit_zero_and_negative_retain_no_frames(self) -> None:
        """`limit=0` rendered EVERY frame — the opposite of a bound named limit."""
        from kailash.utils.secure_logging import safe_exception_frames

        def deep(n: int):
            if n:
                return deep(n - 1)
            raise ValueError("boom")

        try:
            deep(40)
        except ValueError as exc:
            zero = safe_exception_frames(exc, limit=0, follow_chain=False)
            negative = safe_exception_frames(exc, limit=-1, follow_chain=False)
            bounded = safe_exception_frames(exc, limit=5, follow_chain=False)

        # NOT `count(">")` — the `<no-frames>` placeholder contains one, so the
        # frame SEPARATOR and the empty MARKER are the same character. Assert on
        # the marker instead, which is what "no frames" actually renders as.
        assert zero == "ValueError@<no-frames>", f"limit=0 rendered: {zero[:120]}"
        assert (
            negative == "ValueError@<no-frames>"
        ), f"limit=-1 rendered: {negative[:120]}"
        # The negative control: a real bound still renders exactly that many
        # frames (5 frames -> 4 separators), so this cannot pass by rendering
        # nothing at all.
        assert "<no-frames>" not in bounded
        assert bounded.count(">") == 4

    def test_a_full_path_credential_still_does_not_survive(self) -> None:
        """The directory half of the disclosure surface stays closed.

        Round 7 established the BASENAME is attacker-influenceable (Jinja2
        compiles a template with the template name as the filename). The
        DIRECTORY portion must remain safe, because that is where a filesystem
        path carrying a credential would sit.
        """
        import os

        from kailash.utils.secure_logging import _relative_frame_path

        leaky = os.path.join(os.sep, "srv", "postgres:hunter2@db", "app.py")
        rendered = _relative_frame_path(leaky)
        assert "hunter2" not in rendered
        assert rendered == "app.py"


class TestSafeExceptionFramesDisclosesNeitherLayoutNorSource:
    def test_cwd_above_home_does_not_render_the_home_layout(self) -> None:
        """A cwd of "/" produces no leading "..", so the old guard never fired.

        Not an exotic configuration: a systemd unit with no ``WorkingDirectory``
        runs at "/". Under the old code every frame beneath the home directory
        rendered as ``home/<user>/svc/db.py`` -- the exact layout the function
        exists to hide.
        """
        import os

        from kailash.utils import secure_logging

        home = os.path.expanduser("~")
        victim = os.path.join(home, "svc", "db.py")
        user_component = os.path.basename(home)

        previous = os.getcwd()
        try:
            os.chdir("/")
            rendered = secure_logging._relative_frame_path(victim)
        finally:
            os.chdir(previous)

        assert user_component not in rendered
        assert rendered == "db.py"

    def test_a_real_workspace_cwd_still_renders_relative(self) -> None:
        """The negative half: the guard must not swallow the normal case.

        Without this, a fix that returned the basename unconditionally would
        pass the test above and destroy the diagnostic.
        """
        import os

        from kailash.utils import secure_logging

        target = os.path.join(os.getcwd(), "svc", "db.py")
        assert secure_logging._relative_frame_path(target) == os.path.join(
            "svc", "db.py"
        )

    def test_frames_carry_no_source_text_and_honour_the_limit(self) -> None:
        from kailash.utils.secure_logging import safe_exception_frames

        def deep(n: int):
            if n:
                return deep(n - 1)
            raise ValueError("boom-with-a-secret-in-it")

        try:
            deep(60)
        except ValueError as exc:
            rendered = safe_exception_frames(exc, limit=3)

        # The limit applies, and the message never appears -- only the type.
        assert rendered.count(">") == 2, rendered
        assert "boom-with-a-secret-in-it" not in rendered
        assert rendered.startswith("ValueError@")

    def test_source_is_never_read_for_frames_that_get_discarded(
        self, monkeypatch
    ) -> None:
        """Pin the lookup, not just the output.

        The sibling test above asserts no source text appears -- which was true
        BEFORE this fix too, because the rendering never used ``.line``. It
        therefore does not discriminate on the defect, which was that
        ``extract_tb`` READ the source for every frame before the limit slice
        threw them away. Thousands of frames from a deep recursion meant
        thousands of linecache reads on a path an attacker can drive. Only
        counting the reads tells the two states apart.
        """
        import linecache

        from kailash.utils.secure_logging import safe_exception_frames

        reads: list = []
        real_getline = linecache.getline
        monkeypatch.setattr(
            linecache,
            "getline",
            lambda *a, **kw: (reads.append(a), real_getline(*a, **kw))[1],
        )

        def deep(n: int):
            if n:
                return deep(n - 1)
            raise ValueError("boom")

        try:
            deep(200)
        except ValueError as exc:
            safe_exception_frames(exc, limit=3)

        assert reads == [], (
            f"{len(reads)} source lookups for a 200-frame traceback rendered "
            "at limit=3; the frames are read before the slice discards them"
        )
