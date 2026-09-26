# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression test for issue #2081 — the sync->async bridge join must talk.

``LocalRuntime.execute()`` called from inside a running event loop bridges to
async on a worker thread and joins it. That join was ``thread.join()`` — no
timeout, no output, ever. Exceptions raised inside the thread are captured and
re-raised after the join, so a RAISE cannot hang the caller; only a BLOCK can,
and when it blocked the wait was permanent and completely silent.

That silence is what made #2081 undiagnosable: three CI runs produced 15 and
40 minutes of wall clock and zero actionable output, because the instrument
could not distinguish "hung on one test" from "uniformly slower on a small
runner".

Two properties are pinned here:

  1. The join is SLICED and emits a WARNING naming the workflow and dumping the
     stuck thread's stack. It still waits — a workflow may legitimately run for
     hours, and truncating one would trade a visible hang for silent data loss.
  2. ``sync_bridge_timeout`` converts that into a typed ``RuntimeExecutionError``
     for deployments that want a hard bound.

These tests drive ``_join_sync_bridge`` against a real ``threading.Thread``
that genuinely blocks — nothing is patched, and the blocking is the same shape
as the bridge thread wedged on pool teardown.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from decimal import Decimal

import pytest

from kailash.nodes.base import Node, NodeParameter
from kailash.runtime import local as local_runtime
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import RuntimeExecutionError
from kailash.workflow.graph import Workflow

# ``_join_sync_bridge`` is imported INSIDE the tests that need it. It is a
# symbol this fix introduces, so a module-level import would turn a pre-fix run
# of this file into a collection ImportError and hide
# ``test_a_slow_bridge_is_not_silent_at_the_real_call_site`` — the one test
# here that demonstrates the DEFECT rather than the new API.

pytestmark = [pytest.mark.regression]


class _NamedWorkflow:
    """Minimal stand-in carrying only what the join reads: a ``name``."""

    def __init__(self, name: str) -> None:
        self.name = name


class _SleepingNode(Node):
    """Block the actual workflow worker without process-wide sandbox limits."""

    def get_parameters(self):
        return {"delay": NodeParameter(name="delay", type=float, required=True)}

    def run(self, **kwargs):
        time.sleep(kwargs["delay"])
        return {"done": True}


def _sleeping_workflow(name: str, node_id: str, delay: float) -> Workflow:
    workflow = Workflow(name, name=name)
    workflow.add_node(node_id, _SleepingNode(delay=delay))
    return workflow


def _blocked_thread(release: threading.Event) -> threading.Thread:
    """Start a REAL thread that blocks until ``release`` is set."""
    thread = threading.Thread(
        target=release.wait, name="kailash-sync-bridge-test", daemon=True
    )
    thread.start()
    return thread


@pytest.mark.timeout(60)
def test_stuck_bridge_logs_a_warning_naming_the_workflow_and_its_stack(
    caplog, monkeypatch
):
    """A bridge that stops progressing MUST say so, with a stack.

    PRE-FIX: ``thread.join()`` emits nothing at all, forever. POST-FIX: every
    watchdog interval logs the workflow name and the stuck thread's stack.
    """
    from kailash.runtime.local import _join_sync_bridge

    monkeypatch.setattr(local_runtime, "SYNC_BRIDGE_WATCHDOG_INTERVAL", 0.3)
    release = threading.Event()
    thread = _blocked_thread(release)
    workflow = _NamedWorkflow("stuck_workflow")

    def _release_after(delay: float) -> None:
        time.sleep(delay)
        release.set()

    releaser = threading.Thread(target=_release_after, args=(1.0,), daemon=True)
    releaser.start()

    with caplog.at_level(logging.WARNING, logger="kailash.runtime.local"):
        _join_sync_bridge(thread, workflow, timeout=None)
    releaser.join(timeout=5)

    warnings = [r for r in caplog.records if "sync_bridge_slow" in r.getMessage()]
    assert warnings, (
        "a bridge thread stuck past the watchdog interval produced NO log "
        "output — this is the #2081 silence that made three CI runs unreadable"
    )
    message = warnings[0].getMessage()
    assert "stuck_workflow" in message, "the log MUST name the workflow"
    assert (
        "File " in message or "stack unavailable" in message
    ), "the log MUST carry the stuck thread's stack, or say why it could not"


@pytest.mark.timeout(60)
def test_join_still_waits_by_default_rather_than_truncating(monkeypatch):
    """The default MUST NOT be a deadline — a long workflow still completes."""
    from kailash.runtime.local import _join_sync_bridge

    monkeypatch.setattr(local_runtime, "SYNC_BRIDGE_WATCHDOG_INTERVAL", 0.2)
    release = threading.Event()
    thread = _blocked_thread(release)

    def _release_after(delay: float) -> None:
        time.sleep(delay)
        release.set()

    releaser = threading.Thread(target=_release_after, args=(0.9,), daemon=True)
    releaser.start()

    # Several watchdog intervals elapse; the join must still return normally
    # rather than raising, because no hard bound was configured.
    _join_sync_bridge(thread, _NamedWorkflow("slow_but_fine"), timeout=None)
    releaser.join(timeout=5)

    assert not thread.is_alive(), "the join must return only once the bridge is done"


@pytest.mark.timeout(60)
def test_sync_bridge_timeout_raises_a_typed_error_naming_the_workflow(monkeypatch):
    """The opt-in bound MUST fail with a named, actionable error — not a hang."""
    from kailash.runtime.local import _join_sync_bridge

    monkeypatch.setattr(local_runtime, "SYNC_BRIDGE_WATCHDOG_INTERVAL", 0.2)
    release = threading.Event()
    thread = _blocked_thread(release)

    try:
        started = time.monotonic()
        with pytest.raises(RuntimeExecutionError) as excinfo:
            _join_sync_bridge(thread, _NamedWorkflow("wedged"), timeout=0.6)
        elapsed = time.monotonic() - started
    finally:
        release.set()

    assert elapsed < 30, f"the bound did not apply; waited {elapsed:.1f}s"
    text = str(excinfo.value)
    assert "wedged" in text, "the error MUST name the workflow"
    assert "sync_bridge_timeout" in text, "the error MUST name the knob to change"
    assert (
        "execute_workflow_async" in text
    ), "the error MUST point at the async API that avoids the bridge entirely"


@pytest.mark.timeout(90)
@pytest.mark.asyncio
async def test_a_slow_bridge_is_not_silent_at_the_real_call_site(caplog, monkeypatch):
    """The DEFECT itself, at the real call site, using no new API.

    Every other test in this module exercises symbols the fix introduces, so
    against unfixed code they fail on an absent name rather than on the
    behaviour. This one does not: it drives ``LocalRuntime.execute()`` from
    inside a running loop with a node that outlasts the watchdog interval, and
    asserts only that the runtime SAID SOMETHING.

    PRE-FIX that assertion fails on an empty log — ``thread.join()`` is
    completely silent no matter how long the bridge takes, which is the whole
    reason #2081 needed three CI runs to localise. ``raising=False`` on the
    monkeypatch is what keeps this test runnable against unfixed code, where
    the module constant does not exist yet.
    """
    monkeypatch.setattr(
        local_runtime, "SYNC_BRIDGE_WATCHDOG_INTERVAL", 1.0, raising=False
    )

    workflow = _sleeping_workflow("issue_2081_slow_workflow", "slowpoke", delay=3.0)

    with (
        LocalRuntime() as runtime,
        caplog.at_level(logging.WARNING, logger="kailash.runtime.local"),
    ):
        results, _run_id = runtime.execute(workflow)

    assert results, "the workflow must still complete — this is not a deadline"
    slow = [r for r in caplog.records if "sync_bridge_slow" in r.getMessage()]
    assert slow, (
        "a bridge that ran well past the watchdog interval emitted NOTHING. "
        "That silence is the #2081 defect: a hung run and a merely-slow run "
        "are indistinguishable in the log, which is why the first two CI runs "
        "produced 15 and 40 minutes of wall clock and no actionable output"
    )
    assert "issue_2081_slow_workflow" in slow[0].getMessage()


@pytest.mark.timeout(90)
@pytest.mark.asyncio
async def test_execute_from_inside_a_running_loop_does_not_hang_forever():
    """The real call site: ``execute()`` from inside a running event loop.

    This is the shape #2081 describes. ``LocalRuntime.execute()`` invoked with
    a loop already running routes through ``_execute_sync``, which bridges to a
    worker thread and joins it. With a node that blocks, PRE-FIX this call
    NEVER RETURNS — the test hangs and is killed by the timeout marker above.
    POST-FIX the configured bound converts it into a typed error.

    The node's real ``time.sleep`` holds the workflow's bridge thread until
    the configured delay expires, independently of the caller's join timeout.
    """
    assert asyncio.get_running_loop() is not None  # precondition for the bridge

    # A finite sleep outlasts the one-second join bound and lets this test
    # drain its real worker before returning.
    workflow = _sleeping_workflow("issue_2081_blocking_workflow", "blocker", delay=5.0)

    with LocalRuntime(sync_bridge_timeout=1) as runtime:

        started = time.monotonic()
        with pytest.raises(RuntimeExecutionError, match="issue_2081_blocking_workflow"):
            runtime.execute(workflow)
        elapsed = time.monotonic() - started

        assert elapsed < 20, (
            f"execute() took {elapsed:.1f}s against a 1s sync_bridge_timeout — the "
            "bridge join is still unbounded (#2081)"
        )
        # The abandoned bridge thread is a daemon, so it cannot wedge interpreter
        # shutdown once we have given up on it. If it were not, the whole pytest
        # process would block at exit for the remainder of the node's sleep.
        bridges = [
            t
            for t in threading.enumerate()
            if t.name.startswith("kailash-sync-bridge-issue_2081")
        ]
        assert bridges, "precondition: the abandoned bridge thread is still running"
        assert all(t.daemon for t in bridges), (
            "an abandoned bridge thread MUST be a daemon; a non-daemon one is "
            "joined by threading._shutdown at interpreter exit, which re-creates "
            "the unbounded wait at process teardown"
        )
        # Drain before returning. The daemon assertion above is what pins the
        # product behaviour; drain the test's worker before the next test starts.
        for bridge in bridges:
            bridge.join(timeout=30)
            assert not bridge.is_alive(), "abandoned bridge thread failed to drain"


def test_sync_bridge_timeout_rejects_a_non_positive_bound():
    """A zero/negative bound is a configuration error, not a silent no-op."""
    with pytest.raises(ValueError, match="sync_bridge_timeout"):
        LocalRuntime(sync_bridge_timeout=0)
    with pytest.raises(ValueError, match="sync_bridge_timeout"):
        LocalRuntime(sync_bridge_timeout=-5)
    # None is the documented default and must remain accepted.
    with LocalRuntime(sync_bridge_timeout=None) as runtime:
        assert runtime._sync_bridge_timeout is None


@pytest.mark.parametrize(
    "kwargs, error, message",
    [
        ({"sync_bridge_timeout": 0}, ValueError, "sync_bridge_timeout"),
        ({"sync_bridge_timeout": -5}, ValueError, "sync_bridge_timeout"),
        ({"sync_bridge_timeout": float("nan")}, ValueError, "sync_bridge_timeout"),
        ({"sync_bridge_timeout": float("inf")}, ValueError, "sync_bridge_timeout"),
        ({"sync_bridge_timeout": -float("inf")}, ValueError, "sync_bridge_timeout"),
        ({"sync_bridge_timeout": 10**400}, ValueError, "sync_bridge_timeout"),
        ({"sync_bridge_timeout": Decimal("1")}, TypeError, "must be an int or float"),
        ({"sync_bridge_timeout": "1"}, TypeError, "must be an int or float"),
        ({"history_store": object()}, TypeError, "must expose a callable"),
    ],
)
def test_invalid_configuration_precedes_resource_initialization(
    monkeypatch, kwargs, error, message
):
    def reject_resource_initialization(self, *args, **kwargs):
        pytest.fail("invalid configuration reached resource initialization")

    monkeypatch.setattr(
        local_runtime.BaseRuntime, "__init__", reject_resource_initialization
    )
    with pytest.raises(error, match=message):
        LocalRuntime(**kwargs)


def test_valid_history_store_still_records_completed_nodes():
    from types import SimpleNamespace

    from kailash.nodes.transform.formatters import ChunkTextExtractorNode
    from kailash.workflow.builder import WorkflowBuilder

    recorded = []

    async def record_event(event):
        recorded.append(event)

    builder = WorkflowBuilder()
    builder.add_node(
        ChunkTextExtractorNode.__name__, "completed", {"chunks": [{"content": "42"}]}
    )
    with LocalRuntime(
        history_store=SimpleNamespace(record_event=record_event)
    ) as runtime:
        runtime.execute(builder.build())

    assert [event.node_id for event in recorded] == ["completed"]


@pytest.mark.parametrize("bound", [float("nan"), float("inf"), -float("inf"), 10**400])
def test_sync_bridge_timeout_rejects_unusable_bounds(bound):
    """Reject bounds that disable the deadline or overflow its join arithmetic."""
    with pytest.raises(ValueError, match="finite positive"):
        # Close an erroneously admitted runtime if the validation regresses.
        with LocalRuntime(sync_bridge_timeout=bound):
            pass


@pytest.mark.parametrize("bound", [1, 0.25])
def test_sync_bridge_timeout_preserves_finite_numeric_bounds(bound):
    """Admitted integer and float bounds work in the actual join arithmetic."""
    joins = []

    class FinishedThread:
        def join(self, timeout):
            joins.append(timeout)

        def is_alive(self):
            return False

    with LocalRuntime(sync_bridge_timeout=bound) as runtime:
        local_runtime._join_sync_bridge(
            FinishedThread(),
            _NamedWorkflow("finished"),
            timeout=runtime._sync_bridge_timeout,
        )
    assert joins == [bound]


def test_configured_finite_bound_still_limits_real_bridge():
    """The admitted public bound reaches the actual blocking-thread join."""
    release = threading.Event()
    thread = _blocked_thread(release)
    try:
        with LocalRuntime(sync_bridge_timeout=0.05) as runtime:
            with pytest.raises(RuntimeExecutionError, match="finite_bound"):
                local_runtime._join_sync_bridge(
                    thread,
                    _NamedWorkflow("finite_bound"),
                    timeout=runtime._sync_bridge_timeout,
                )
            assert thread.is_alive()
    finally:
        release.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
