"""Regression test — synthesis-phase LLM failure is NOT masked as success (#1953).

Distinct from #1947 (a forgotten/omitted provider — closed by the run() guard)
and #1952 (keyless-mock): #1953 is reachable ONLY AFTER the #1947 provider guard
has passed. With a RESOLVED, non-mock provider, a genuine runtime synthesis LLM
failure (bad key, network, rate-limit) at ``IterativeLLMAgentNode._phase_synthesis``
was swallowed by an ``except Exception`` that logged a warning and fell through to
a hand-built ``## Analysis Results`` template. ``run()`` then returned that template
inside ``{"success": True, "final_response": <template>, ...}`` — presenting a real
LLM failure to the caller as SUCCESS with a non-LLM answer.

The fix (#1953): a synthesis-phase LLM failure (a thrown exception OR an
unsuccessful response) with a resolved provider raises ``SynthesisError``, which
``run()`` surfaces as ``success=False`` with a ``synthesis_failed`` marker and the
underlying error. The degraded process-report (a summary of the REAL iteration
results — it carries value) is preserved under the clearly-named
``degraded_synthesis`` key, NEVER as ``final_response`` — so no caller mistakes the
template for a real model answer. Consistent with the #1947 fabricated-content-as-
real guard in the same file.

These are Tier 1 unit tests. They monkeypatch the base ``LLMAgentNode.run``
(the ``super().run()`` synthesis dispatches through) to RAISE — a resolved,
non-mock provider whose synthesis call genuinely fails at runtime — and observe
the REAL returned success flag / raised error, never a mock that hides the mask.
"""

import pytest

from kaizen.nodes.ai.iterative_llm_agent import (
    IterationState,
    IterativeLLMAgentNode,
    SynthesisError,
)
from kaizen.nodes.ai.llm_agent import LLMAgentNode

pytestmark = pytest.mark.regression

_MESSAGES = [{"role": "user", "content": "Why did revenue drop last quarter?"}]
_REAL_FINDING = "Finding: revenue dropped 12% driven by enterprise churn"


def _iteration_with_real_results() -> IterationState:
    """A successful iteration carrying real execution results the template summarizes."""
    return IterationState(
        iteration=1,
        phase="synthesis",
        start_time=0.0,
        end_time=1.0,
        execution_results={"intermediate_results": [_REAL_FINDING]},
        success=True,
    )


class TestPhaseSynthesisRaisesOnResolvedProviderFailure:
    """A resolved-provider synthesis LLM failure raises SynthesisError, not a template return."""

    def test_synthesis_llm_exception_raises_synthesis_error(self, monkeypatch):
        # Resolved provider whose synthesis call throws at runtime (bad key etc.).
        def _raise(self, **kwargs):
            raise RuntimeError("simulated runtime LLM failure: invalid api key")

        monkeypatch.setattr(LLMAgentNode, "run", _raise)

        node = IterativeLLMAgentNode()
        iterations = [_iteration_with_real_results()]
        kwargs = {"provider": "mock", "messages": _MESSAGES}

        with pytest.raises(SynthesisError) as exc_info:
            node._phase_synthesis(kwargs, iterations, global_discoveries={})

        # The degraded process-report is preserved on the error (it summarizes the
        # REAL iteration results) — but it is an ERROR, never a success return.
        report = exc_info.value.degraded_report
        assert (
            "## Analysis Results" in report
        ), "the degraded process-report should still be built and attached"
        assert (
            _REAL_FINDING in report
        ), "the degraded report should summarize the real iteration results"
        # The failure is surfaced (non-empty error message), never silently swallowed.
        assert str(exc_info.value)

    def test_synthesis_unsuccessful_response_raises_synthesis_error(self, monkeypatch):
        # A resolved provider that returns success=False (no exception) is ALSO a
        # genuine failure — it MUST NOT fall through to the template-as-answer.
        def _unsuccessful(self, **kwargs):
            return {"success": False, "error": "rate limited"}

        monkeypatch.setattr(LLMAgentNode, "run", _unsuccessful)

        node = IterativeLLMAgentNode()
        iterations = [_iteration_with_real_results()]
        kwargs = {"provider": "mock", "messages": _MESSAGES}

        with pytest.raises(SynthesisError) as exc_info:
            node._phase_synthesis(kwargs, iterations, global_discoveries={})
        assert "rate limited" in str(exc_info.value)


class TestRunReturnPathNotMaskedAsSuccess:
    """run() surfaces a synthesis failure as success=False, not a fabricated answer."""

    def test_run_synthesis_failure_is_not_success_with_template(self, monkeypatch):
        # Fail ONLY the synthesis dispatch (distinguished by its system prompt),
        # so the iterations run with a resolved provider and only the final
        # synthesis LLM call fails at runtime — the exact masking scenario.
        def _synthesis_only_failure(self, **kwargs):
            messages = kwargs.get("messages", [])
            system_text = " ".join(
                m.get("content", "")
                for m in messages
                if isinstance(m, dict) and m.get("role") == "system"
            )
            if "synthesizing results" in system_text.lower():
                raise RuntimeError("simulated runtime LLM failure: network error")
            return {"success": True, "response": {"content": _REAL_FINDING}}

        monkeypatch.setattr(LLMAgentNode, "run", _synthesis_only_failure)

        node = IterativeLLMAgentNode()
        result = node.run(provider="mock", messages=_MESSAGES, max_iterations=1)

        assert isinstance(result, dict)
        # THE regression guarantee: never success=True with a fabricated
        # `## Analysis Results` body presented as the answer.
        assert not (
            result.get("success") is True
            and "## Analysis Results" in str(result.get("final_response", ""))
        ), "a resolved-provider synthesis failure was masked as success=True"
        # The failure is observable to the caller.
        assert result.get("success") is False
        assert result.get("synthesis_failed") is True
        assert result.get("error"), "the underlying synthesis error must be surfaced"
        # The template, if kept, is under a clearly-named NON-final_response key.
        assert (
            "final_response" not in result
        ), "the template must not be presented as final_response on failure"
        assert "## Analysis Results" in str(
            result.get("degraded_synthesis", "")
        ), "the degraded process-report should be preserved under degraded_synthesis"

    def test_run_all_llm_calls_failing_still_not_masked(self, monkeypatch):
        # Even when every LLM call fails (no iteration results), the synthesis
        # failure MUST NOT be returned as success=True with a template.
        def _raise(self, **kwargs):
            raise RuntimeError("simulated runtime LLM failure: 401 unauthorized")

        monkeypatch.setattr(LLMAgentNode, "run", _raise)

        node = IterativeLLMAgentNode()
        result = node.run(provider="mock", messages=_MESSAGES, max_iterations=1)

        assert result.get("success") is False
        assert result.get("synthesis_failed") is True
        assert not (
            result.get("success") is True
            and "## Analysis Results" in str(result.get("final_response", ""))
        )


class TestSuccessfulSynthesisStillWorks:
    """Happy path unchanged: an explicit mock provider that succeeds returns success."""

    def test_explicit_mock_returns_success_with_final_response(self):
        node = IterativeLLMAgentNode()
        result = node.execute(provider="mock", messages=_MESSAGES, max_iterations=1)
        assert isinstance(result, dict)
        assert result.get("success") is True
        assert result.get("synthesis_failed") is not True
        assert "final_response" in result
