"""The multi-agent patterns' graceful-mode error RETURNS must not leak credentials.

Sibling of ``test_local_error_sinks_are_scrubbed.py`` (the LOG surface) and of
``test_log_sinks_do_not_releak_via_traceback.py`` (the ``exc_info`` surface).
This file pins the third surface, which neither of those can see: the graceful
error dict a pattern RETURNS TO ITS CALLER.

WHY A SEPARATE FILE, AND WHY THE OTHER TWO ARE BLIND TO THIS
------------------------------------------------------------
The swept-surface scanner in ``test_local_error_sinks_are_scrubbed.py`` walks
``ast.ExceptHandler`` nodes and flags a caught exception's *name* reaching a
string context. Every sink pinned here defeats that scanner structurally:

* ``"traceback": traceback.format_exc()`` names no exception at all. The call
  is a bare attribute access on a module, so no scanner keyed on the handler's
  bound name can see it -- yet it renders the SAME exception the sibling
  ``"error"`` key on the line above was scrubbed to protect.
* ``parallel._execute_parallel_async`` converts exceptions that
  ``asyncio.gather(return_exceptions=True)`` RETURNS AS VALUES. There is no
  ``except`` clause in that function, so it is outside the scanner's domain by
  construction.
* ``meta_controller._handle_agent_error`` receives the exception as a
  PARAMETER. Its function body contains no ``ExceptHandler`` node either.

That is the whole reason these nine sites survived the #1970 sweep and the
689f9ebd8 traceback sweep: five of them sit in files the scanner already counts
as SWEPT, because the scrubbed ``"error"`` key one line up is exactly what
marks the file covered.

WHAT A LEAKED TRACEBACK ACTUALLY CARRIES
----------------------------------------
More than the message, which is why "the message is scrubbed" was never
sufficient. A rendered traceback carries the exception's final line verbatim
(re-introducing what the scrub removed), every chained cause under "the above
exception was the direct cause", and the SOURCE LINE of each frame -- so a
literal credential in a call expression is rendered too.

TIER 1: pure functions, no infrastructure, no network. The agents are local
stubs that raise; the SCRUBBER IS THE REAL ONE and every assertion is made
against its real output (rules/testing.md -- the component under test is never
mocked).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from kaizen.core.base_agent import BaseAgent
from kaizen.utils.credential_scrub import DEFAULT_PLACEHOLDER
from kaizen_agents.patterns.patterns.blackboard import BlackboardPipeline
from kaizen_agents.patterns.patterns.ensemble import EnsemblePipeline
from kaizen_agents.patterns.patterns.meta_controller import MetaControllerPipeline
from kaizen_agents.patterns.patterns.parallel import ParallelPipeline

# A vendor-prefixed key (claimed by a literal-anchored rule) and a URL-userinfo
# credential (claimed by the DSN rule). Two shapes so a partial scrub cannot
# pass: the remote preset must claim both.
CREDENTIAL = "sk-abcdefghijklmnopqrstuvwxyz0123456789"
DSN = "postgresql://svc_user:hunter2@db.internal:5432/app"


def _boom() -> RuntimeError:
    """The exception every stub raises: one that names its own credentials.

    This is the realistic shape. A provider auth failure names the endpoint it
    could not authenticate against, and a driver's connect error embeds the DSN
    it dialled -- both verbatim in ``str(exc)`` and therefore in the traceback's
    final line.
    """
    return RuntimeError(f"provider auth failed: key={CREDENTIAL} dsn={DSN}")


@dataclass
class _MockConfig:
    """Minimal domain config; ``BaseAgent`` auto-converts it.

    ``llm_provider="mock"`` per rules/testing.md — a unit test names the mock
    provider explicitly rather than inheriting whatever the environment has.
    """

    llm_provider: str = "mock"
    model: str = "mock-model"


class RaisingAgent(BaseAgent):
    """A REAL ``BaseAgent`` whose ``run`` raises a credential-bearing error.

    Subclassing ``BaseAgent`` rather than duck-typing is deliberate, and it is
    not about silencing a type checker. The pipelines declare
    ``agents: list[BaseAgent]``, and a double that does not satisfy the
    interface it stands in for can pass while the real call path would not --
    the same vacuity class this whole file is about. Constructing the real
    base class also means ``run`` goes through ``LoggingMixin``'s wrapper, as
    it does in production, so the pipelines see the object they actually get.

    ``mcp_servers=[]`` disables MCP auto-connect, which is what keeps this
    Tier 1: no network, no subprocess, no provider.
    """

    def __init__(self, agent_id: str = "raiser") -> None:
        super().__init__(config=_MockConfig(), agent_id=agent_id, mcp_servers=[])

    def run(self, **inputs: Any) -> dict[str, Any]:
        raise _boom()


class QuietAgent(BaseAgent):
    """A REAL ``BaseAgent`` that succeeds, for the slots that must not fail."""

    def __init__(self, agent_id: str = "quiet", **result: Any) -> None:
        super().__init__(config=_MockConfig(), agent_id=agent_id, mcp_servers=[])
        self._result = result or {"result": "ok"}

    def run(self, **inputs: Any) -> dict[str, Any]:
        return dict(self._result)


# ---------------------------------------------------------------------------
# The shared contract every graceful error return must satisfy.
# ---------------------------------------------------------------------------
def assert_no_credential(payload: dict[str, Any], *, where: str) -> None:
    """Neither secret appears anywhere in the returned dict, at any depth.

    Asserting on the WHOLE payload rather than on a named key is deliberate:
    an assertion pinned to ``payload["error"]`` passes against every defect
    this file exists to catch, since ``"error"`` was already scrubbed at five
    of the nine sites while ``"traceback"`` beside it shipped the exception in
    full.
    """
    blob = repr(payload)
    assert CREDENTIAL not in blob, (
        f"{where}: the API key reached the caller in {payload.keys()!r}. "
        "A graceful error return is a caller-visible surface; route it "
        "through scrub_remote_error (rules/security.md, no secrets in logs)."
    )
    assert DSN not in blob, (
        f"{where}: the DSN (with password) reached the caller in "
        f"{payload.keys()!r}. Same contract as the API key."
    )


def assert_diagnostic_survives(payload: dict[str, Any], *, where: str) -> None:
    """The scrub redacts the credential WITHOUT emptying the field.

    Without this, ``"traceback": ""`` would pass ``assert_no_credential`` --
    the vacuous way to satisfy a leak test. The point of scrubbing rather than
    dropping is that the frame trail survives, so it is asserted.
    """
    tb = payload.get("traceback")
    if tb is None:
        return  # a site that legitimately drops the field
    assert "Traceback (most recent call last)" in tb, (
        f"{where}: traceback field is present but carries no frame trail "
        f"({tb!r}). Scrubbing must preserve the diagnostic; if the field "
        "cannot be made meaningful it should be dropped, not blanked."
    )
    assert DEFAULT_PLACEHOLDER in tb, (
        f"{where}: traceback shows no redaction marker, so the credential-"
        "bearing final line was probably never rendered into it."
    )
    assert "RuntimeError" in tb, (
        f"{where}: traceback names no exception type -- it is not this "
        "failure's traceback."
    )


# ---------------------------------------------------------------------------
# parallel.py
# ---------------------------------------------------------------------------
class TestParallelPipeline:
    def test_sync_agent_error_return_is_scrubbed(self) -> None:
        """``_execute_agent_sync`` -- the shape that made the file read as swept.

        Its ``"error"`` key already called ``scrub_remote_error``; the
        ``"traceback"`` key in the SAME returned dict did not.
        """
        pipeline = ParallelPipeline(agents=[RaisingAgent()])
        payload = pipeline._execute_agent_sync(RaisingAgent(), {"task": "t"})

        assert payload["status"] == "failed"
        assert_no_credential(payload, where="parallel._execute_agent_sync")
        assert_diagnostic_survives(payload, where="parallel._execute_agent_sync")

    def test_public_run_does_not_leak(self) -> None:
        """The same defect through the PUBLIC surface a user actually calls."""
        pipeline = ParallelPipeline(agents=[RaisingAgent(), RaisingAgent("b")])
        aggregated = pipeline.run(task="t")

        assert_no_credential(aggregated, where="parallel.run")
        for entry in aggregated["results"]:
            assert_diagnostic_survives(entry, where="parallel.run[]")

    def test_gathered_exception_conversion_is_scrubbed(self) -> None:
        """``_execute_parallel_async`` -- exceptions returned as VALUES.

        ``_execute_agent_sync`` swallows agent errors in graceful mode, so the
        conversion branch is reached only when the per-agent call itself raises.
        Overriding that one method is what drives it: the code under test --
        the gather + conversion branch -- is entirely real.
        """

        class ExplodingParallel(ParallelPipeline):
            def _execute_agent_sync(self, agent: Any, inputs: Any) -> dict[str, Any]:
                raise _boom()

        pipeline = ExplodingParallel(agents=[RaisingAgent()])
        results = asyncio.run(pipeline._execute_parallel_async({"task": "t"}))

        assert len(results) == 1
        assert results[0]["status"] == "failed"
        assert_no_credential(results[0], where="parallel._execute_parallel_async")

    def test_gathered_exception_traceback_is_this_failures_traceback(self) -> None:
        """The wrong-traceback defect, independent of the leak.

        ``traceback.format_exc()`` reads ``sys.exc_info()``. In this function
        there is no active exception -- ``asyncio.gather`` RETURNED the
        exception rather than raising it -- so the call yields the string
        ``"NoneType: None"`` (or, if this code is ever reached beneath an outer
        handler, some UNRELATED exception's traceback). Scrubbing alone would
        have left a field that is worse than useless: confidently wrong.
        """

        class ExplodingParallel(ParallelPipeline):
            def _execute_agent_sync(self, agent: Any, inputs: Any) -> dict[str, Any]:
                raise _boom()

        pipeline = ExplodingParallel(agents=[RaisingAgent()])
        results = asyncio.run(pipeline._execute_parallel_async({"task": "t"}))
        tb = results[0].get("traceback")

        assert tb != "NoneType: None\n", (
            "parallel._execute_parallel_async returned the traceback of NO "
            "exception. format_exc() reads ambient interpreter state; this "
            "site must derive the traceback from the exception OBJECT."
        )
        assert_diagnostic_survives(results[0], where="parallel._execute_parallel_async")


# ---------------------------------------------------------------------------
# blackboard.py
# ---------------------------------------------------------------------------
class TestBlackboardPipeline:
    def test_specialist_error_return_is_scrubbed(self) -> None:
        pipeline = BlackboardPipeline(
            specialists=[RaisingAgent()], controller=QuietAgent()
        )
        payload = pipeline._execute_specialist(RaisingAgent(), {"insights": []})

        assert payload["status"] == "failed"
        assert_no_credential(payload, where="blackboard._execute_specialist")
        assert_diagnostic_survives(payload, where="blackboard._execute_specialist")

    def test_controller_error_return_is_scrubbed(self) -> None:
        pipeline = BlackboardPipeline(
            specialists=[QuietAgent()], controller=RaisingAgent()
        )
        payload = pipeline._execute_controller({"insights": []})

        assert payload["status"] == "controller_failed"
        assert_no_credential(payload, where="blackboard._execute_controller")
        assert_diagnostic_survives(payload, where="blackboard._execute_controller")

    def test_public_run_does_not_leak(self) -> None:
        """A failing controller short-circuits ``run`` -- the caller-visible path."""
        pipeline = BlackboardPipeline(
            specialists=[QuietAgent()], controller=RaisingAgent()
        )
        blackboard = pipeline.run(task="t")

        assert_no_credential(blackboard, where="blackboard.run")


# ---------------------------------------------------------------------------
# ensemble.py
# ---------------------------------------------------------------------------
class TestEnsemblePipeline:
    def test_perspective_error_return_is_scrubbed(self) -> None:
        pipeline = EnsemblePipeline(
            agents=[RaisingAgent()], synthesizer=QuietAgent(), discovery_mode="all"
        )
        perspectives = pipeline._execute_agents([RaisingAgent()], task="t")

        assert len(perspectives) == 1
        assert perspectives[0]["status"] == "failed"
        assert_no_credential(perspectives[0], where="ensemble._execute_agents")
        assert_diagnostic_survives(perspectives[0], where="ensemble._execute_agents")

    def test_synthesis_error_return_is_scrubbed(self) -> None:
        pipeline = EnsemblePipeline(
            agents=[QuietAgent()], synthesizer=RaisingAgent(), discovery_mode="all"
        )
        payload = pipeline._synthesize_perspectives([{"result": "ok"}], task="t")

        assert payload["status"] == "synthesis_failed"
        assert_no_credential(payload, where="ensemble._synthesize_perspectives")
        assert_diagnostic_survives(payload, where="ensemble._synthesize_perspectives")

    def test_public_run_does_not_leak(self) -> None:
        pipeline = EnsemblePipeline(
            agents=[RaisingAgent()], synthesizer=RaisingAgent(), discovery_mode="all"
        )
        result = pipeline.run(task="t")

        assert_no_credential(result, where="ensemble.run")


# ---------------------------------------------------------------------------
# meta_controller.py
# ---------------------------------------------------------------------------
class TestMetaControllerPipeline:
    def test_agent_error_return_is_scrubbed(self) -> None:
        """Both keys leaked here: ``str(error)`` AND the traceback.

        This is the one site with no scrub at all, because the exception
        arrives as a function PARAMETER -- there is no ``except`` clause in
        ``_handle_agent_error`` for a handler-scoped scanner to key on.

        The exception is RAISED and caught rather than merely constructed,
        because that is the only shape the sole caller can produce and it is
        the shape that carries a ``__traceback__``. A bare ``_boom()`` would
        test a state this function is never called in -- and would quietly
        weaken the assertion, since an unraised exception has no frames to
        leak in the first place.
        """
        pipeline = MetaControllerPipeline(
            agents=[RaisingAgent()], routing_strategy="round-robin"
        )
        try:
            raise _boom()
        except RuntimeError as exc:
            caught = exc
        payload = pipeline._handle_agent_error(RaisingAgent(), caught)

        assert payload["status"] == "failed"
        assert_no_credential(payload, where="meta_controller._handle_agent_error")
        assert_diagnostic_survives(payload, where="meta_controller._handle_agent_error")

    def test_public_run_does_not_leak(self) -> None:
        pipeline = MetaControllerPipeline(
            agents=[RaisingAgent()], routing_strategy="round-robin"
        )
        payload = pipeline.run(task="t")

        assert_no_credential(payload, where="meta_controller.run")
        assert_diagnostic_survives(payload, where="meta_controller.run")


# ---------------------------------------------------------------------------
# Negative control -- the assertions above are not vacuously true.
# ---------------------------------------------------------------------------
class TestTheInstrumentDiscriminates:
    """Prove the contract helpers RED on the defect they claim to detect.

    Without this, every assertion above would pass just as well against a
    pipeline that returned an empty dict, and the suite would be reporting on
    nothing (rules/instrument-discipline.md MUST-2).
    """

    def test_assert_no_credential_reds_on_a_raw_traceback(self) -> None:
        import traceback

        try:
            raise _boom()
        except RuntimeError as exc:
            leaked = {
                "error": "scrubbed message, no secret here",
                "traceback": "".join(traceback.format_exception(exc)),
            }

        with pytest.raises(AssertionError, match="API key reached the caller"):
            assert_no_credential(leaked, where="control")

    def test_assert_diagnostic_survives_reds_on_a_blanked_field(self) -> None:
        with pytest.raises(AssertionError, match="no frame trail"):
            assert_diagnostic_survives({"traceback": ""}, where="control")

    def test_assert_diagnostic_survives_reds_on_the_null_traceback(self) -> None:
        with pytest.raises(AssertionError, match="no frame trail"):
            assert_diagnostic_survives(
                {"traceback": "NoneType: None\n"}, where="control"
            )
