"""Issue #2109 defect 1, second half -- the ISOLATED path ignored the budget.

``HookManager._execute_hook`` resolves a per-hook execution budget through
``_resolve_timeout``, so ``AuditTrailHook`` (which declares
``timeout_seconds = 2.0``) is not cut off at the shared 0.5s "SECURITY FIX #10"
guard that the best-effort observability hooks sit behind.

``IsolatedHookManager`` OVERRIDES ``_execute_hook``. Its non-isolated branch
delegates to ``super()``, which resolves correctly. Its ISOLATED branch handed
the caller's shared ``timeout`` straight to ``execute_isolated``, so with
isolation enabled the audit hook was still on 0.5s and its records still
dropped -- the defect fixed on one path and left live on the other.

WHAT THESE TESTS ASSERT, AND WHAT THAT PROVES
---------------------------------------------
They assert at the SEAM: the timeout value the manager hands to
``IsolatedHookExecutor.execute_isolated``. They do NOT drive real process
isolation.

  * PROVES: the manager resolves the per-hook budget and passes THAT value,
    not the shared default, across the isolated branch -- which is the whole
    of the defect under test.
  * DOES NOT PROVE: that ``execute_isolated`` then enforces the budget it is
    given. That is the executor's own contract, exercised by the real-spawn
    tests in ``tests/regression/test_issue_2014_spawn_isolation.py``.

The seam was chosen because an end-to-end assertion would need a real ``spawn``
interpreter per hook plus a handler sleeping BETWEEN 0.5s and 2.0s -- a
wall-clock race that would be flaky exactly when the machine is loaded. A
recorded argument is exact and has no timing component.
"""

import sys
from pathlib import Path

import pytest

from kaizen.core.autonomy.hooks.protocol import BaseHook
from kaizen.core.autonomy.hooks.security.isolation import (
    HookIsolationError,
    IsolatedHookManager,
)
from kaizen.core.autonomy.hooks.types import HookContext, HookEvent, HookResult

# Provenance guard -- pinned RELATIVE to this file, never to an absolute
# worktree path, so it travels with the checkout. `kaizen` resolving to an
# INSTALLED copy has produced false greens in this repo.
_PKG_ROOT = Path(__file__).resolve().parents[5]  # .../packages/kailash-kaizen

# The shared budget ``HookManager.trigger`` defaults to (SECURITY FIX #10).
SHARED_DEFAULT = 0.5


def test_kaizen_resolves_to_this_checkout():
    """Refuse to report on an installed copy of the package under test."""
    import kaizen

    resolved = Path(kaizen.__file__).resolve()
    expected_src = (_PKG_ROOT / "src").resolve()
    assert resolved.is_relative_to(expected_src), (
        f"kaizen resolved to {resolved}, not this checkout under {expected_src}. "
        f"sys.path[0]={sys.path[0]!r}"
    )


class RecordingExecutor:
    """Stands in for ``IsolatedHookExecutor`` and records the budget it is given.

    This is the SEAM. Substituting it replaces the process-isolation machinery
    (the ENVIRONMENT) and leaves the subject -- the manager's budget resolution
    on the isolated branch -- entirely real.
    """

    def __init__(self, raises: BaseException | None = None):
        self.calls: list[float] = []
        self._raises = raises

    async def execute_isolated(self, handler, context, timeout: float) -> HookResult:
        self.calls.append(timeout)
        if self._raises is not None:
            raise self._raises
        return HookResult(success=True, data={}, duration_ms=1.0)

    @property
    def only_timeout(self) -> float:
        assert len(self.calls) == 1, f"expected exactly one call, got {self.calls}"
        return self.calls[0]


class PlainHook(BaseHook):
    """An ordinary best-effort hook: declares no budget of its own."""

    def __init__(self):
        super().__init__(name="plain_hook")
        self.ran = False

    async def handle(self, context: HookContext) -> HookResult:
        self.ran = True
        return HookResult(success=True, data={})


class BudgetedHook(PlainHook):
    """A hook that opts onto a LONGER finite budget, as ``AuditTrailHook`` does."""

    timeout_seconds = 2.0

    def __init__(self):
        super().__init__()
        # Distinct from PlainHook's name: the stats assertions below key on it,
        # and inheriting "plain_hook" would silently assert against the wrong row.
        self.name = "budgeted_hook"


def _wire(hook: BaseHook, raises: BaseException | None = None):
    """Isolating manager whose executor is the recording seam."""
    manager = IsolatedHookManager(enable_isolation=True)
    recorder = RecordingExecutor(raises=raises)
    manager.executor = recorder
    manager.register(HookEvent.PRE_TOOL_USE, hook)
    return manager, recorder


async def _trigger(manager):
    return await manager.trigger(HookEvent.PRE_TOOL_USE, agent_id="a1", data={})


@pytest.mark.asyncio
async def test_isolated_branch_honours_a_declared_longer_budget():
    """THE DEFECT: the declared budget must survive the isolated branch.

    Pre-fix this records 0.5 -- the shared default -- because the isolated
    branch never consulted ``_resolve_timeout``.
    """
    manager, recorder = _wire(BudgetedHook())

    await _trigger(manager)

    assert recorder.only_timeout == 2.0, (
        f"isolated branch handed {recorder.only_timeout}s to execute_isolated; "
        f"the hook declared timeout_seconds=2.0"
    )


@pytest.mark.asyncio
async def test_ordinary_hooks_keep_the_shared_guard_under_isolation():
    """SECURITY FIX #10 must not be widened for hooks that declare nothing."""
    manager, recorder = _wire(PlainHook())

    await _trigger(manager)

    assert recorder.only_timeout == SHARED_DEFAULT


@pytest.mark.parametrize(
    "bad",
    [0, -1.0, float("inf"), float("nan"), True, "2.0", None],
    ids=["zero", "negative", "inf", "nan", "bool", "string", "none"],
)
@pytest.mark.asyncio
async def test_the_guard_cannot_be_disabled_by_a_bogus_override(bad):
    """Fail-CLOSED: a junk override falls back to the shared budget, not to no budget."""
    hook = PlainHook()
    hook.timeout_seconds = bad
    manager, recorder = _wire(hook)

    await _trigger(manager)

    assert recorder.only_timeout == SHARED_DEFAULT


@pytest.mark.asyncio
async def test_a_shorter_declared_budget_is_honoured_too():
    """The override selects a DIFFERENT finite bound -- it may tighten as well."""
    hook = PlainHook()
    hook.timeout_seconds = 0.1
    manager, recorder = _wire(hook)

    await _trigger(manager)

    assert recorder.only_timeout == 0.1


@pytest.mark.asyncio
async def test_isolation_failure_still_fails_closed_after_the_budget_change():
    """Issue #2014 must survive this edit: no in-process fallback, typed error."""
    hook = BudgetedHook()
    manager, recorder = _wire(
        hook, raises=HookIsolationError("budgeted_hook", "isolation unavailable")
    )

    with pytest.raises(HookIsolationError):
        await _trigger(manager)

    # The budget still reached the seam...
    assert recorder.only_timeout == 2.0
    # ...and the hook was NOT run in-process as a fallback.
    assert hook.ran is False
    # ...and the failure was counted.
    stats = manager.get_stats()["budgeted_hook"]
    assert stats["failure_count"] == 1


@pytest.mark.asyncio
async def test_non_isolated_branch_still_resolves_the_budget():
    """The opt-out branch delegates to the parent and must be unchanged."""
    manager = IsolatedHookManager(enable_isolation=False)
    hook = BudgetedHook()
    manager.register(HookEvent.PRE_TOOL_USE, hook)

    results = await _trigger(manager)

    assert results[0].success is True
    assert hook.ran is True
