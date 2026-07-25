"""Regression test — _phase_execution error paths sanitize provider errors (#1953).

Defense-in-depth parity with the #1953 folds. #1953 folded
``sanitize_provider_error`` into the synthesis / iteration / MCP error paths of
``IterativeLLMAgentNode`` (``iterative_llm_agent.py`` L438/612/1057/1120/1852).
Two holistic reviewers (correctness + security) flagged FOUR sibling
``except Exception as e:`` sites in ``_phase_execution`` that stored a raw
``str(e)`` into the user-visible ``execution_results`` dict WITHOUT the local
sanitize the sibling folds use:

  * first except block (the no-execution-steps ``direct_llm`` path):
    ``error_result["error"] = str(e)`` and ``execution_results["errors"].append(str(e))``
  * second except block (the per-step execution path): the SAME shape.

These are SAFE TODAY because the base ``LLMAgentNode.run`` re-raises
``RuntimeError(sanitize_provider_error(e, provider))`` before the exception
reaches ``_phase_execution`` — so ``str(e)`` is already the sanitized message
and the raw exception survives only in ``__cause__`` (which ``str()`` omits).
The gap is defense-in-depth: a FUTURE refactor that adds a raw-raising provider
path (or changes the base node to ``raise e``) would leak a credential at these
four sites with no local guard.

This test SIMULATES that future refactor by monkeypatching the provider-dispatch
boundary (``LLMAgentNode.run`` — the ``super().run()`` ``_phase_execution``
dispatches through) to raise an exception carrying a RAW (fake) credential in
its message, then drives ``_phase_execution`` down BOTH except paths and asserts
the user-visible ``execution_results`` never carries the raw credential AND does
carry the sanitizer's ``[REDACTED]`` marker.

Tier 1 unit test: it monkeypatches the base ``run`` to raise a
credential-bearing exception (the future-refactor scenario) and observes the
REAL returned ``execution_results`` dict, never a mock that hides the leak.

The fake credential is a synthetic OpenAI-style key that matches the
``sanitize_provider_error`` credential regex (``sk-[A-Za-z0-9_-]{20,}``). It is
NOT a real secret.
"""

import pytest

from kaizen.nodes.ai.iterative_llm_agent import IterativeLLMAgentNode
from kaizen.nodes.ai.llm_agent import LLMAgentNode

pytestmark = pytest.mark.regression

_MESSAGES = [{"role": "user", "content": "Why did revenue drop last quarter?"}]

# Synthetic OpenAI-style key — matches the sanitizer's sk-[A-Za-z0-9_-]{20,}
# pattern. NOT a real credential.
_FAKE_CREDENTIAL = "sk-FAKE1234567890abcdefghijKLMNOP"
_RAW_ERROR = f"provider error: api_key={_FAKE_CREDENTIAL} leaked from upstream SDK"


def _raise_with_raw_credential(self, **kwargs):
    """Simulate a future refactor where the base node re-raises WITHOUT sanitizing:
    a raw provider exception whose message embeds a live credential reaches
    ``_phase_execution``."""
    raise RuntimeError(_RAW_ERROR)


def _assert_no_raw_credential_but_redacted(execution_results):
    """Every user-visible error surface MUST redact the credential, never carry it raw."""
    # (a) the per-step error_result stored in steps_completed
    error_results = [
        step for step in execution_results["steps_completed"] if not step.get("success")
    ]
    assert error_results, "expected at least one failed step recording the error"
    for step in error_results:
        error_field = str(step.get("error", ""))
        assert (
            _FAKE_CREDENTIAL not in error_field
        ), f"raw credential leaked into steps_completed[].error: {error_field!r}"
        assert (
            "[REDACTED]" in error_field
        ), f"expected sanitizer redaction marker in steps_completed[].error: {error_field!r}"

    # (b) the execution_results["errors"] list
    errors_joined = " ".join(str(e) for e in execution_results["errors"])
    assert execution_results[
        "errors"
    ], "expected the errors[] list to record the failure"
    assert (
        _FAKE_CREDENTIAL not in errors_joined
    ), f"raw credential leaked into execution_results['errors']: {errors_joined!r}"
    assert (
        "[REDACTED]" in errors_joined
    ), f"expected sanitizer redaction marker in execution_results['errors']: {errors_joined!r}"

    # The failure is still surfaced (defense-in-depth must not swallow the error).
    assert execution_results["success"] is False


class TestPhaseExecutionSanitizesProviderErrors:
    """A raw-credential-bearing provider exception reaching _phase_execution's
    except paths is sanitized before it lands in the user-visible dict."""

    def test_direct_llm_except_sanitizes_credential(self, monkeypatch):
        """First except block — the ``direct_llm`` no-execution-steps path."""
        monkeypatch.setattr(LLMAgentNode, "run", _raise_with_raw_credential)

        node = IterativeLLMAgentNode()
        plan = {"planning_mode": "direct_llm"}
        result = node._phase_execution(
            {"provider": "mock", "messages": _MESSAGES}, plan, discoveries={}
        )

        _assert_no_raw_credential_but_redacted(result)

    def test_per_step_except_sanitizes_credential(self, monkeypatch):
        """Second except block — the per-step (no-tools direct-LLM) execution path."""
        monkeypatch.setattr(LLMAgentNode, "run", _raise_with_raw_credential)

        node = IterativeLLMAgentNode()
        plan = {
            "execution_steps": [{"step": 1, "action": "analyze", "tools": []}],
            "user_query": "Why did revenue drop last quarter?",
        }
        result = node._phase_execution(
            {"provider": "mock", "messages": _MESSAGES}, plan, discoveries={}
        )

        _assert_no_raw_credential_but_redacted(result)
