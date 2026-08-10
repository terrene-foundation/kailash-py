"""The hook-name fallback must not render a caller-supplied object's ``repr``.

``PathwayManager._execute_hook`` logs ``handler_name`` on both its failure
branches, and that name is deliberately NOT scrubbed -- it is the diagnostic
that says WHICH hook failed.

The fallback used to be ``repr(handler)``. ``handler`` is CALLER-SUPPLIED and
typed as a callable, not as a function, so anything without ``__name__`` fell
through to that repr:

  * ``functools.partial(post, url="https://user:pw@host")`` renders its bound
    kwargs verbatim.
  * a callable object whose ``__repr__`` is dataclass-generated renders EVERY
    field, including a credential one.

Both reached the log line AND the returned ``JourneyHookResult.error`` -- the
exact leak class the surrounding commit exists to close, on the one field it
deliberately retains.

The fallback is now ``type(handler).__name__``, which cannot carry a payload by
construction. That is preferred over scrubbing the repr because the scrubber's
coverage is porous by its own measurement (a prefix-less 32-39 char key,
``token=``, a %40-encoded ``@`` all survive it) -- so a scrub here would be a
second porous surface rather than a closed one.

Every credential below is a synthetic sentinel: structurally credential-shaped,
self-describing, and unusable.
"""

import functools
import logging
from dataclasses import dataclass

import pytest

_SENTINEL = "SYNTHETIC-NOT-A-REAL-CREDENTIAL-f1"
_LEAKY_URL = f"https://svc:{_SENTINEL}@hooks.example.invalid/notify"


@pytest.fixture
def capture(caplog):
    """Capture the manager's own logger at WARNING+ (both sinks log there)."""
    caplog.set_level(logging.WARNING, logger="kaizen_agents.journey.manager")
    return caplog


def _manager(timeout: float = 5.0):
    """Build only what ``_execute_hook`` reads.

    ``__new__`` + ``_hook_timeout`` mirrors the sibling regression in this
    directory: the journey/session/config wiring is irrelevant to these sinks,
    and constructing it would couple the regression to unrelated churn.
    """
    from kaizen_agents.journey.manager import PathwayManager

    manager = PathwayManager.__new__(PathwayManager)
    manager._hook_timeout = timeout
    return manager


async def _hook_that_raises(context, *, url: str) -> None:
    """A hook whose BOUND ARGUMENT carries the credential, not its exception."""
    raise RuntimeError("hook backend unreachable")


@dataclass
class _CallableHook:
    """A callable object with a dataclass-generated ``__repr__``.

    This is the sharper case: the credential is a FIELD, so ``repr`` renders it
    even though nothing about the call or the exception mentions it.
    """

    endpoint: str
    api_key: str

    async def __call__(self, context) -> None:
        raise RuntimeError("hook backend unreachable")


class TestExceptionBranch:
    """The ``except Exception`` sink at ``_execute_hook``."""

    @pytest.mark.asyncio
    async def test_partial_bound_kwargs_do_not_reach_the_log_or_the_result(
        self, capture
    ):
        handler = functools.partial(_hook_that_raises, url=_LEAKY_URL)
        assert not hasattr(handler, "__name__"), (
            "precondition: a functools.partial has no __name__, which is what "
            "sends it down the fallback path under test"
        )

        result = await _manager()._execute_hook(handler, {})

        assert result.success is False
        # Anti-vacuity: without this, a sink that never fired would pass every
        # assertion below by emitting nothing at all.
        assert "Hook error" in capture.text, (
            "the hook-error sink never fired; the leak assertions below would "
            "hold vacuously"
        )
        assert _SENTINEL not in capture.text, capture.text
        assert _SENTINEL not in (result.error or ""), result.error
        # The diagnostic survives: the reader still learns WHICH hook failed.
        assert "partial" in capture.text.lower()

    @pytest.mark.asyncio
    async def test_callable_object_fields_do_not_reach_the_log_or_the_result(
        self, capture
    ):
        handler = _CallableHook(
            endpoint="https://hooks.example.invalid", api_key=_SENTINEL
        )
        assert not hasattr(handler, "__name__")
        assert _SENTINEL in repr(handler), (
            "precondition: the dataclass __repr__ DOES render the credential -- "
            "this is what the old fallback emitted"
        )

        result = await _manager()._execute_hook(handler, {})

        assert result.success is False
        assert "Hook error" in capture.text, "sink never fired; test would be vacuous"
        assert _SENTINEL not in capture.text, capture.text
        assert _SENTINEL not in (result.error or ""), result.error
        assert "_CallableHook" in capture.text


class TestTimeoutBranch:
    """The ``except TimeoutError`` sink -- the sibling site, same fallback."""

    @pytest.mark.asyncio
    async def test_timeout_path_does_not_render_the_repr(self, capture):
        import asyncio

        async def _slow(context, *, url: str) -> None:
            await asyncio.sleep(10)

        handler = functools.partial(_slow, url=_LEAKY_URL)

        result = await _manager(timeout=0.01)._execute_hook(handler, {})

        assert result.success is False
        assert "Hook timeout" in capture.text, "timeout sink never fired; vacuous"
        assert _SENTINEL not in capture.text, capture.text
        assert _SENTINEL not in (result.error or ""), result.error
