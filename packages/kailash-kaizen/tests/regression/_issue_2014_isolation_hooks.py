"""Module-scope hook handlers for the issue #2014 regression tests.

These live in a HELPER module, not in the test module, on purpose.

Under the ``spawn`` start method the child is a fresh interpreter that re-imports
the defining module of every pickled object by name. Keeping the handlers here
means the child imports this small, side-effect-free module rather than
re-importing a ``test_*`` module under pytest's assertion-rewriting import hook.

Everything here MUST stay importable at module scope: that is precisely the
property issue #2014 was about.
"""

import os
from typing import Any

from kaizen.core.autonomy.hooks.types import HookContext, HookResult

#: Rewritten by the PARENT process at test time, never by an importer.
#:
#: This is the fork-vs-spawn discriminator. Under ``fork`` the child is a copy of
#: the parent's address space and observes the parent's mutation. Under ``spawn``
#: the child re-imports this module from source and observes the literal below.
#: A test that asserts on this value therefore fails on Linux (where ``fork`` is
#: the default) if the start method is ever left to the platform.
PARENT_ONLY_MUTATION = "not-mutated"


class PidReportingHook:
    """Reports the PID it actually executed in."""

    name = "pid-reporting-hook"

    async def handle(self, context: HookContext) -> HookResult:
        return HookResult(success=True, data={"pid": os.getpid()})


class StartMethodProbeHook:
    """Reports whether it observed the parent's in-memory mutation.

    ``"not-mutated"`` means a fresh interpreter (``spawn``).
    ``"mutated-in-parent"`` means an inherited address space (``fork``).
    """

    name = "start-method-probe-hook"

    async def handle(self, context: HookContext) -> HookResult:
        return HookResult(
            success=True,
            data={"observed": PARENT_ONLY_MUTATION, "pid": os.getpid()},
        )


class CrashingHook:
    """Raises inside the child, to prove a hook crash cannot take the parent down."""

    name = "crashing-hook"

    async def handle(self, context: HookContext) -> HookResult:
        raise RuntimeError("simulated hook crash")


class UnpicklableResultHook:
    """Returns a result that cannot cross the process boundary.

    A module object has no pickle representation, so this exercises the worker's
    explicit ``pickle.dumps(result)`` probe. Without that probe the failure would
    surface only as a queue feeder-thread traceback on the child's stderr plus a
    silently dropped item, which the parent would misreport as "exited without a
    result".
    """

    name = "unpicklable-result-hook"

    async def handle(self, context: HookContext) -> HookResult:
        import types

        return HookResult(success=True, data={"mod": types})


class EchoHook:
    """Returns the context data it was handed, to prove the context crossed intact."""

    name = "echo-hook"

    async def handle(self, context: HookContext) -> HookResult:
        return HookResult(success=True, data={"echoed": context.data})


class SlowHook:
    """Sleeps well past any test timeout, to exercise the timeout path."""

    name = "slow-hook"

    async def handle(self, context: HookContext) -> HookResult:
        import asyncio

        await asyncio.sleep(30)
        return HookResult(success=True, data={"slept": True})


def build_context(data: dict[str, Any] | None = None) -> HookContext:
    """A picklable context for the executor-level tests."""
    from kaizen.core.autonomy.hooks.types import HookEvent

    return HookContext(
        event_type=HookEvent.PRE_AGENT_LOOP,
        agent_id="agent-2014",
        timestamp=0.0,
        data=data if data is not None else {},
    )
