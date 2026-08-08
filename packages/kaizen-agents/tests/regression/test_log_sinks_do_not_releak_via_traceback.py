# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Scrubbing the MESSAGE while keeping the TRACEBACK protects nothing.

The #1970 sweep established the reasoning at eight sites in ``kailash-kaizen``
(``llm/reasoning.py``, ``judges/_judge.py``, ``observability/trace_exporter.py``)
in those files' own words: dropping ``exc_info`` is what stops the raw message
re-entering via the traceback's final line. Eleven sinks in ``kaizen-agents``
were missed by that sweep. They came in two shapes::

    logger.exception(f"... {scrub_remote_error(e)}")          # always exc_info
    logger.error(f"... {scrub_remote_error(e)}", exc_info=True)

``logging`` renders ``exc_info`` by walking the exception chain, so a
``raise Wrapper(...) from provider_error`` prints the RAW ``provider_error``
under "The above exception was the direct cause of..." -- verbatim, after the
scrub removed it from the message.

These tests assert on the FULLY RENDERED record (``Formatter.format``, which is
what resolves ``exc_info`` into text), NOT on ``record.getMessage()``. A
message-only assertion passes against every one of the leaks below, which is
precisely how they survived the original sweep.

The sentinels are synthetic: RFC 2606 ``.invalid`` / ``.example`` hostnames and
self-describing values. They are not credentials; they carry the SHAPE the
scrubber keys on so they exercise the same branch a real one would.
"""

from __future__ import annotations

import logging

import pytest

pytestmark = pytest.mark.regression

_SENTINEL = "SYNTHETIC-NOT-A-REAL-CREDENTIAL-kzagents"
_LEAKY_DSN = f"postgresql://svc:{_SENTINEL}@db.example.invalid:5432/prod"


def _chained_exception() -> Exception:
    """A wrapper whose ``__cause__`` carries the credential.

    This is the shape that defeats a message-only scrub: ``str(wrapper)`` is
    clean, so the scrubbed message looks safe, while the rendered traceback
    prints the cause in full.
    """
    try:
        try:
            raise ConnectionError(f"could not connect: {_LEAKY_DSN}")
        except ConnectionError as inner:
            raise RuntimeError("operation failed") from inner
    except RuntimeError as wrapper:
        return wrapper


class _RenderingCapture(logging.Handler):
    """Captures the rendered record -- the only view that resolves exc_info."""

    def __init__(self) -> None:
        super().__init__()
        self.rendered: list[str] = []
        self._fmt = logging.Formatter("%(levelname)s %(message)s")

    def emit(self, record: logging.LogRecord) -> None:
        self.rendered.append(self._fmt.format(record))

    @property
    def text(self) -> str:
        return "\n".join(self.rendered)


@pytest.fixture
def capture():
    """Attach to the ROOT logger so every module under test is covered."""
    handler = _RenderingCapture()
    root = logging.getLogger()
    prior = root.level
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(prior)


class TestTheLeakVectorItself:
    """Pins WHY exc_info is the vector, independent of any call site.

    If this class ever goes green with ``exc_info=True``, ``logging`` changed
    its chain-rendering and every drop below can be revisited. Until then it is
    the falsifying control for the whole file: it demonstrates the instrument
    can distinguish leaked from scrubbed.
    """

    def test_exc_info_renders_the_chained_cause_verbatim(self, capture):
        from kaizen.utils.credential_scrub import scrub_remote_error

        exc = _chained_exception()
        scrubbed = scrub_remote_error(exc)
        # The scrub itself is not the problem -- the message IS clean.
        assert _SENTINEL not in scrubbed

        logging.getLogger("probe.leak").error(
            "failed: %s", scrubbed, exc_info=(type(exc), exc, exc.__traceback__)
        )
        assert _SENTINEL in capture.text, (
            "exc_info no longer renders the chained cause; the premise of this "
            "regression has changed and the drops must be re-justified."
        )

    def test_without_exc_info_the_same_call_is_clean(self, capture):
        from kaizen.utils.credential_scrub import scrub_remote_error

        exc = _chained_exception()
        logging.getLogger("probe.clean").error("failed: %s", scrub_remote_error(exc))
        assert _SENTINEL not in capture.text


class TestConditionTriggerFailSafeSink:
    """journey/transitions.py -- driven through the REAL public method."""

    def test_condition_failure_does_not_render_the_raw_cause(self, capture):
        from kaizen_agents.journey.transitions import ConditionTrigger

        def _explode(context):
            raise _chained_exception()

        trigger = ConditionTrigger(condition=_explode, description="probe")

        # Real call, real fail-safe path.
        assert trigger.evaluate("any message", {}) is False

        assert (
            "ConditionTrigger evaluation failed" in capture.text
        ), "the fail-safe sink never fired; this test would pass vacuously"
        assert _SENTINEL not in capture.text, capture.text


class TestPathwayManagerHookSink:
    """journey/manager.py::_execute_hook -- driven through the REAL method."""

    @pytest.mark.asyncio
    async def test_hook_failure_does_not_render_the_raw_cause(self, capture):
        from kaizen_agents.journey.manager import PathwayManager

        async def failing_hook(context):
            raise _chained_exception()

        # ``__new__`` + the one attribute ``_execute_hook`` reads: the manager's
        # journey/session/config wiring is irrelevant to this sink, and building
        # it would couple the regression to unrelated constructor churn.
        manager = PathwayManager.__new__(PathwayManager)
        manager._hook_timeout = 5.0

        result = await manager._execute_hook(failing_hook, {})

        # The degraded result is still returned -- the sink is not a crash path.
        assert result.success is False
        assert (
            "Hook error" in capture.text
        ), "the hook-error sink never fired; this test would pass vacuously"
        # The handler NAME is deliberately retained: it is the diagnostic.
        assert "failing_hook" in capture.text
        assert _SENTINEL not in capture.text, capture.text


class TestPrintRunnerSink:
    """delegate/print_mode.py -- driven through the REAL ``run`` coroutine.

    The runner is built with ``__new__`` and given a stub ``_loop``: the loop is
    a COLLABORATOR, not the code under test, and constructing the real one wants
    a provider client. ``PrintRunner.run`` itself -- including the sink -- is the
    genuine article here.
    """

    @pytest.mark.asyncio
    async def test_turn_failure_does_not_render_the_raw_cause(self, capture):
        from kaizen_agents.delegate.print_mode import PrintRunner

        class _ExplodingLoop:
            usage = None

            async def run_turn(self, prompt):  # noqa: ARG002
                raise _chained_exception()
                yield ""  # pragma: no cover - makes this an async generator

        runner = PrintRunner.__new__(PrintRunner)
        runner._config = None
        runner._loop = _ExplodingLoop()

        result = await runner.run("hello")

        assert result.is_error is True
        assert (
            "PrintRunner failed" in capture.text
        ), "the sink never fired; this test would pass vacuously"
        assert _SENTINEL not in capture.text, capture.text
        # The RETURN was already scrubbed before this fix; the log line was not.
        # Asserting both keeps the pair from drifting apart again.
        assert _SENTINEL not in (result.error_message or "")


class TestEmergencyCheckpointSink:
    """agents/autonomous/base.py -- the second PROVEN leak, driven for real.

    ``_handle_interrupt`` is the real method under test; only its collaborators
    (interrupt manager, config, state manager) are stubs. The immediate-shutdown
    branch is the one that reaches the checkpoint sink.
    """

    @pytest.mark.asyncio
    async def test_checkpoint_failure_does_not_render_the_raw_cause(self, capture):
        from kaizen_agents.agents.autonomous.base import BaseAutonomousAgent
        from kaizen_agents.agents.autonomous.base import (  # noqa: F401
            InterruptMode,
        )

        reason = type(
            "_Reason",
            (),
            {
                "message": "probe interrupt",
                "mode": InterruptMode.IMMEDIATE,
                "to_dict": lambda self: {"reason": "probe"},
            },
        )()

        class _Interrupts:
            def is_interrupted(self):
                return True

            def get_interrupt_reason(self):
                return reason

        class _StateManager:
            async def save_checkpoint(self, state, force=False):  # noqa: ARG002
                raise _chained_exception()

        agent = BaseAutonomousAgent.__new__(BaseAutonomousAgent)
        agent.interrupt_manager = _Interrupts()
        agent.autonomous_config = type("_Cfg", (), {"checkpoint_on_interrupt": True})()
        agent.state_manager = _StateManager()
        agent._capture_state = lambda: type("_S", (), {"status": "", "metadata": {}})()

        status = await agent._handle_interrupt()

        assert status.interrupted is True
        assert (
            "Failed to save emergency checkpoint" in capture.text
        ), "the checkpoint sink never fired; this test would pass vacuously"
        assert _SENTINEL not in capture.text, capture.text
