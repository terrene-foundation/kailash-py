"""Issue #2014 -- hook process isolation never ran under the ``spawn`` start method.

WHAT WAS BROKEN

``IsolatedHookExecutor.execute_isolated`` built its worker as a CLOSURE inside
the method. ``spawn`` transfers the process target by pickling it, and pickle
stores a function by its ``module.qualname`` rather than by its code, so a local
object has no representation at all -- ``Process.start()`` raised
``Can't get local object 'IsolatedHookExecutor.execute_isolated.<locals>._run_hook'``
on every single call. ``IsolatedHookManager._execute_hook`` then caught that,
logged it, and ran the hook through ``super()._execute_hook`` instead.

``spawn`` is the default start method on macOS and Windows. On those platforms
isolation therefore failed for EVERY hook, every time, and every hook ran in the
agent's own process with the agent's own privileges -- while the caller was
handed a successful-looking ``HookResult``. Only Linux, where ``fork`` is the
default, isolated anything at all.

WHY THESE TESTS ARE WRITTEN THIS WAY

A test that merely calls an isolating manager and asserts the call succeeded
passes identically whether isolation happened or not -- that is exactly how the
pre-existing suite stayed green across the entire bug. Every test below is
therefore pinned to an observable that DIFFERS between the isolated and the
non-isolated execution:

* the PID the hook body actually ran in,
* whether the child observed a mutation only the parent's address space holds,
* whether an in-process side effect fired at all.

The start method is pinned to ``spawn`` explicitly rather than left to the
platform. That matters for CI: on Linux ``fork`` is the default, a forked child
inherits the parent's memory, and the fork/spawn discrimination test below would
pass for the wrong reason if the pin were ever dropped.
"""

import multiprocessing
import os
import pickle
import subprocess
import sys

import pytest

from kaizen.core.autonomy.hooks.manager import HookManager
from kaizen.core.autonomy.hooks.security.isolation import (
    _ISOLATION_START_METHOD,
    HookIsolationError,
    IsolatedHookExecutor,
    IsolatedHookManager,
    ResourceLimits,
    _isolated_hook_worker,
)
from kaizen.core.autonomy.hooks.types import HookEvent, HookPriority, HookResult

from . import _issue_2014_isolation_hooks as hooks

pytestmark = pytest.mark.regression


#: Limits generous enough that nothing here is killed by a resource cap.
#: The limit-enforcement behaviour has its own tests further down; the isolation
#: tests must not be able to fail for a resource reason.
GENEROUS = ResourceLimits(max_memory_mb=4096, max_cpu_seconds=60, max_file_size_mb=64)

#: Written by a hook that runs IN THIS PROCESS. It stays empty for as long as
#: every hook really is isolated, which is what makes it a usable detector.
_IN_PROCESS_SIDE_EFFECTS: list[str] = []


@pytest.fixture(autouse=True)
def _clear_side_effects():
    _IN_PROCESS_SIDE_EFFECTS.clear()
    yield
    _IN_PROCESS_SIDE_EFFECTS.clear()


# --------------------------------------------------------------------------
# The mechanism that could not work: a closure cannot cross a spawn boundary
# --------------------------------------------------------------------------


class TestWorkerIsTransferable:
    def test_worker_lives_at_module_scope_and_survives_pickling(self):
        """The direct regression assertion for the original defect.

        Pickling the worker is precisely what ``Process.start()`` does under
        ``spawn``. The pre-fix closure raised ``AttributeError: Can't get local
        object ...`` here; that is the falsifying result this asserts against.
        """
        restored = pickle.loads(pickle.dumps(_isolated_hook_worker))

        assert restored is _isolated_hook_worker
        assert _isolated_hook_worker.__qualname__ == "_isolated_hook_worker", (
            "the worker must stay at module scope: a nested or closure worker "
            "has no pickle representation and cannot be spawned"
        )

    def test_a_closure_worker_would_not_have_survived(self):
        """Pins the mechanism itself, so the test above cannot pass vacuously.

        If pickling a local function ever started working, the assertion above
        would no longer discriminate between a module-scope worker and the
        closure that caused #2014.
        """

        def _local_worker():  # pragma: no cover - never called
            return None

        with pytest.raises((AttributeError, pickle.PicklingError)):
            pickle.dumps(_local_worker)

    def test_start_method_is_pinned_not_inherited(self):
        """A platform-dependent start method is the condition that hid the bug."""
        assert _ISOLATION_START_METHOD == "spawn"
        assert _ISOLATION_START_METHOD in multiprocessing.get_all_start_methods()


# --------------------------------------------------------------------------
# The control actually engages
# --------------------------------------------------------------------------


class TestHookReallyRunsElsewhere:
    @pytest.mark.asyncio
    async def test_hook_body_executes_in_a_different_process(self):
        """The PID the hook OBSERVED, not the fact that the call returned.

        Falsifying result: ``data["pid"] == os.getpid()``, which is what the
        pre-fix fallback produced on every call under spawn.
        """
        executor = IsolatedHookExecutor(GENEROUS)

        result = await executor.execute_isolated(
            hooks.PidReportingHook(), hooks.build_context(), timeout=30.0
        )

        assert result.success is True, result.error
        assert (
            result.data["pid"] != os.getpid()
        ), "the hook ran in the parent process: isolation did not engage"

    @pytest.mark.asyncio
    async def test_child_is_a_fresh_interpreter_not_a_fork(self, monkeypatch):
        """Discriminates ``spawn`` from ``fork``, and so is meaningful on Linux.

        The parent mutates a module global in its own address space only. A
        ``fork``ed child inherits that mutation; a ``spawn``ed child re-imports
        the module from source and cannot see it.

        Falsifying result: ``observed == "mutated-in-parent"``, meaning the
        start method was inherited from the platform rather than pinned -- the
        condition under which #2014 stayed invisible on Linux.
        """
        monkeypatch.setattr(hooks, "PARENT_ONLY_MUTATION", "mutated-in-parent")
        assert hooks.PARENT_ONLY_MUTATION == "mutated-in-parent"

        executor = IsolatedHookExecutor(GENEROUS)
        result = await executor.execute_isolated(
            hooks.StartMethodProbeHook(), hooks.build_context(), timeout=30.0
        )

        assert result.success is True, result.error
        assert result.data["observed"] == "not-mutated", (
            "the child inherited the parent's address space: this is fork, not "
            "spawn, and the picklability contract is not being enforced"
        )
        assert result.data["pid"] != os.getpid()

    @pytest.mark.asyncio
    async def test_context_crosses_the_boundary_intact(self):
        executor = IsolatedHookExecutor(GENEROUS)

        result = await executor.execute_isolated(
            hooks.EchoHook(), hooks.build_context({"payload": [1, 2, 3]}), timeout=30.0
        )

        assert result.success is True, result.error
        assert result.data["echoed"] == {"payload": [1, 2, 3]}

    @pytest.mark.asyncio
    async def test_hook_crash_is_contained_and_reported(self):
        """A crash in the child is a hook failure, never an isolation failure."""
        executor = IsolatedHookExecutor(GENEROUS)

        result = await executor.execute_isolated(
            hooks.CrashingHook(), hooks.build_context(), timeout=30.0
        )

        assert result.success is False
        assert "simulated hook crash" in result.error
        assert os.getpid() == os.getpid(), "parent survived"

    @pytest.mark.asyncio
    async def test_result_that_cannot_cross_the_boundary_is_named_precisely(self):
        """The worker's explicit ``pickle.dumps(result)`` probe.

        Without it the queue's feeder thread fails asynchronously and drops the
        item, and the parent misreports the cause as "exited without a result".
        """
        executor = IsolatedHookExecutor(GENEROUS)

        result = await executor.execute_isolated(
            hooks.UnpicklableResultHook(), hooks.build_context(), timeout=30.0
        )

        assert result.success is False
        assert "cannot cross the process boundary" in result.error

    @pytest.mark.asyncio
    async def test_hook_that_overruns_its_timeout_is_stopped(self):
        executor = IsolatedHookExecutor(GENEROUS)

        result = await executor.execute_isolated(
            hooks.SlowHook(), hooks.build_context(), timeout=1.0
        )

        assert result.success is False
        assert "timeout" in result.error.lower()


# --------------------------------------------------------------------------
# The fallback is gone: isolation failure never becomes in-process execution
# --------------------------------------------------------------------------


class TestFailsClosed:
    @pytest.mark.asyncio
    async def test_unpicklable_handler_raises_the_typed_error(self):
        """An unpicklable handler is the exact shape #2014's own worker had."""

        async def _local_hook(context):  # pragma: no cover - must never run
            _IN_PROCESS_SIDE_EFFECTS.append("ran")
            return HookResult(success=True)

        executor = IsolatedHookExecutor(GENEROUS)

        with pytest.raises(HookIsolationError) as excinfo:
            await executor.execute_isolated(
                _local_hook, hooks.build_context(), timeout=30.0
            )

        assert "picklable" in str(excinfo.value)
        assert (
            _IN_PROCESS_SIDE_EFFECTS == []
        ), "the hook body ran in the parent process despite isolation failing"

    @pytest.mark.asyncio
    async def test_manager_raises_rather_than_running_the_hook_in_process(self):
        """The regression assertion for the deleted fallback.

        Pre-fix this returned a successful ``HookResult`` and appended to
        ``_IN_PROCESS_SIDE_EFFECTS``; both are asserted against here.
        """
        manager = IsolatedHookManager(limits=GENEROUS, enable_isolation=True)

        async def _local_hook(context):  # pragma: no cover - must never run
            _IN_PROCESS_SIDE_EFFECTS.append("ran")
            return HookResult(success=True)

        manager.register(HookEvent.PRE_AGENT_LOOP, _local_hook, HookPriority.NORMAL)

        with pytest.raises(HookIsolationError):
            await manager.trigger(
                HookEvent.PRE_AGENT_LOOP, agent_id="agent-2014", data={}, timeout=30.0
            )

        assert _IN_PROCESS_SIDE_EFFECTS == [], (
            "isolation failed and the hook was executed anyway -- this is the "
            "silent downgrade issue #2014 reported"
        )

    @pytest.mark.asyncio
    async def test_non_isolated_path_is_never_reached_on_isolation_failure(
        self, monkeypatch
    ):
        """Asserts on the CALL, not just on the side effect.

        The fallback invoked ``HookManager._execute_hook``. Recording calls to
        it proves the deleted branch is not reachable by any other route.
        """
        calls: list[str] = []

        original = HookManager._execute_hook

        async def _recording(self, handler, context, timeout):
            calls.append(getattr(handler, "name", type(handler).__name__))
            return await original(self, handler, context, timeout)

        monkeypatch.setattr(HookManager, "_execute_hook", _recording)

        manager = IsolatedHookManager(limits=GENEROUS, enable_isolation=True)

        async def _local_hook(context):  # pragma: no cover - must never run
            return HookResult(success=True)

        with pytest.raises(HookIsolationError):
            await manager._execute_hook(
                _LocalAdapter(_local_hook), hooks.build_context(), timeout=30.0
            )

        assert calls == [], (
            "HookManager._execute_hook was reached, so a non-isolated execution "
            "path is still live behind the isolating manager"
        )

    @pytest.mark.asyncio
    async def test_machinery_failure_is_converted_to_the_typed_error(self):
        """Callers get ONE exception type, whatever the executor raised."""
        manager = IsolatedHookManager(limits=GENEROUS, enable_isolation=True)
        manager.executor = _ExplodingExecutor()

        with pytest.raises(HookIsolationError) as excinfo:
            await manager._execute_hook(
                hooks.PidReportingHook(), hooks.build_context(), timeout=5.0
            )

        assert "isolation machinery failed" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_explicit_opt_out_still_runs_in_process(self):
        """The opt-out remains, because it is visible at the call site."""
        manager = IsolatedHookManager(limits=GENEROUS, enable_isolation=False)

        async def _local_hook(context):
            _IN_PROCESS_SIDE_EFFECTS.append("ran")
            return HookResult(success=True)

        manager.register(HookEvent.PRE_AGENT_LOOP, _local_hook, HookPriority.NORMAL)

        results = await manager.trigger(
            HookEvent.PRE_AGENT_LOOP, agent_id="agent-2014", data={}, timeout=5.0
        )

        assert len(results) == 1 and results[0].success is True
        assert _IN_PROCESS_SIDE_EFFECTS == ["ran"]

    @pytest.mark.asyncio
    async def test_isolated_and_opt_out_managers_disagree_about_the_same_hook(self):
        """Guards the pair: the two modes must be distinguishable.

        If this ever passes with both managers succeeding, the opt-out and the
        isolated path have converged again -- which is the #2014 state.
        """
        isolated = IsolatedHookManager(limits=GENEROUS, enable_isolation=True)
        opted_out = IsolatedHookManager(limits=GENEROUS, enable_isolation=False)

        async def _local_hook(context):
            return HookResult(success=True)

        for manager in (isolated, opted_out):
            manager.register(HookEvent.PRE_AGENT_LOOP, _local_hook, HookPriority.NORMAL)

        with pytest.raises(HookIsolationError):
            await isolated.trigger(
                HookEvent.PRE_AGENT_LOOP, agent_id="a", data={}, timeout=30.0
            )

        results = await opted_out.trigger(
            HookEvent.PRE_AGENT_LOOP, agent_id="a", data={}, timeout=5.0
        )
        assert results[0].success is True


# --------------------------------------------------------------------------
# Resource limits: per-limit, and never silently absent
# --------------------------------------------------------------------------


class TestResourceLimitReporting:
    def test_apply_returns_the_limits_it_could_not_enforce(self):
        """``apply()`` reports rather than swallows.

        On macOS ``RLIMIT_AS`` is refused outright, so ``max_memory_mb`` is
        expected in the returned list there. The assertion is written against
        the CONTRACT (a list naming real limit fields) so it holds on Linux,
        where the list is empty.
        """
        unenforced = ResourceLimits(
            max_memory_mb=4096, max_cpu_seconds=60, max_file_size_mb=64
        ).apply()

        assert isinstance(unenforced, list)
        assert set(unenforced) <= {
            "max_memory_mb",
            "max_cpu_seconds",
            "max_file_size_mb",
        }
        if sys.platform == "darwin":
            assert "max_memory_mb" in unenforced, (
                "macOS refuses setrlimit(RLIMIT_AS); that refusal must be "
                "reported, not swallowed"
            )
            assert "max_cpu_seconds" not in unenforced, (
                "a refusal of one limit must not discard the limits this "
                "platform does enforce"
            )

    @pytest.mark.asyncio
    async def test_unenforced_limits_reach_the_parent_log(self, caplog):
        """The child's own logging is unconfigured under spawn, so the parent logs it.

        Falsifying result on macOS: no such record, meaning the operator is
        never told that the memory cap is off.
        """
        if sys.platform != "darwin":
            pytest.skip("needs a platform with a known-unenforceable rlimit")

        caplog.set_level(
            "WARNING", logger="kaizen.core.autonomy.hooks.security.isolation"
        )

        executor = IsolatedHookExecutor(GENEROUS)
        result = await executor.execute_isolated(
            hooks.PidReportingHook(), hooks.build_context(), timeout=30.0
        )

        assert result.success is True, result.error
        assert "NOT enforced on this platform" in caplog.text
        assert "max_memory_mb" in caplog.text

    def test_a_limit_above_the_hard_ceiling_still_raises(self):
        """A capability gap is tolerated; a real misconfiguration is not.

        Run in a subprocess because lowering a hard limit is irreversible for
        the process that does it, and would poison the rest of the session.
        """
        script = """
import resource, sys
sys.path.insert(0, %r)
from kaizen.core.autonomy.hooks.security.isolation import ResourceLimits

# Lower the HARD ceiling, then ask for more than it allows.
resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
try:
    ResourceLimits(max_memory_mb=4096, max_cpu_seconds=60,
                   max_file_size_mb=64).apply()
except (OSError, ValueError):
    print("RAISED")
else:
    print("SWALLOWED")
""" % (
            os.path.join(os.path.dirname(__file__), "..", "..", "src"),
        )

        completed = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert "RAISED" in completed.stdout, (
            f"a value above the hard limit must re-raise, not be reported as a "
            f"platform gap. stdout={completed.stdout!r} stderr={completed.stderr[-2000:]!r}"
        )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


class _LocalAdapter:
    """Wraps a local function so it reaches the executor as a handler.

    Deliberately holds a reference to an unpicklable local function, which is
    what makes isolation fail.
    """

    name = "local-adapter"

    def __init__(self, func):
        self._func = func

    async def handle(self, context):  # pragma: no cover - must never run
        return await self._func(context)


class _ExplodingExecutor:
    """Raises something that is NOT a HookIsolationError."""

    async def execute_isolated(self, handler, context, timeout):
        raise RuntimeError("multiprocessing is unavailable in this sandbox")
