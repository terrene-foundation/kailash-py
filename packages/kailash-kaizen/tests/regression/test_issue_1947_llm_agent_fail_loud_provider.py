"""Regression test — LLMAgentNode fails loud on an unresolved provider (#1947).

The root cause behind #1943 and its follow-ups was structural:
``LLMAgentNode.get_parameters()`` declared ``provider`` as
``required=False, default="mock"``. Any construction site that omitted
``provider`` therefore silently dispatched to the mock provider and returned
fabricated content as if it were a real model answer. #1943 fixed every
Agent-surface site individually and #1946 fixed the RAG sites, but the
default itself was the hazard: every new or forgotten construction site
re-opened the silent-mock class.

The fix (#1947) closes the class at the node:

1. ``get_parameters()["provider"].default`` is now ``None`` (was ``"mock"``).
2. ``run()`` raises a typed ``ConfigurationError`` when ``provider`` resolves
   to ``None`` — a forgotten provider becomes a LOUD, typed failure instead of
   silent fabricated content.
3. The mock provider stays reachable when requested EXPLICITLY
   (``provider="mock"``) — the test-harness contract is preserved.

These are Tier 1 unit tests and are deliberately ENV-INDEPENDENT: the node
itself performs no environment provider-detection (that lives on the Agent
surface, ``Agent._get_provider_for_config()``), so a raw
``LLMAgentNode`` with no ``provider`` resolves to ``None`` at ``run()`` time
regardless of whether ``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY`` are set in
the ambient environment. This is what makes the fix a STRUCTURAL closure of
the class rather than an env-dependent heuristic.

Per the workspace trap: assertions that inspect a workflow's node config MUST
read the UNBUILT ``workflow.nodes[id]["config"]`` — the built ``NodeInstance``
applies parameter defaults and would mask a missing key. The behavioural
assertions here execute the node/workflow and observe the raised error, which
is the real user-facing behaviour and needs no such caveat.
"""

import pytest

from kaizen.config.providers import ConfigurationError
from kaizen.nodes.ai.llm_agent import LLMAgentNode

pytestmark = pytest.mark.regression

_MESSAGES = [{"role": "user", "content": "What is 2 + 2?"}]


class TestProviderDefaultIsNone:
    """The structural pin: the node's provider default MUST be None, not 'mock'."""

    def test_get_parameters_provider_default_is_none(self):
        # The load-bearing structural invariant. If a future edit reverts this
        # to default="mock", the silent-mock class re-opens and this fails loud.
        default = LLMAgentNode().get_parameters()["provider"].default
        assert default is None, (
            f"provider default is {default!r}, expected None. A non-None "
            f'(especially "mock") default re-opens the silent-mock class (#1947).'
        )


class TestUnresolvedProviderFailsLoud:
    """A missing/unresolved provider raises, never silently dispatches mock."""

    def test_direct_run_no_provider_raises_configuration_error(self):
        node = LLMAgentNode()
        # run() is the fail-loud site; it raises the typed ConfigurationError
        # directly (no framework wrapping at this layer).
        with pytest.raises(ConfigurationError) as exc_info:
            # No model kwarg: the fail-loud provider check precedes the model
            # read in run(), so the model value is irrelevant to this path.
            node.run(messages=_MESSAGES)
        assert "provider" in str(exc_info.value).lower()
        assert "#1947" in str(exc_info.value)

    def test_execute_no_provider_fails_loud_not_silent_mock(self):
        node = LLMAgentNode()
        # execute() runs validate_inputs (applies the None default) then run().
        # The framework wraps run()'s ConfigurationError in a NodeExecutionError,
        # but the failure is LOUD — the key regression guarantee is that no
        # result dict with fabricated mock content is returned.
        with pytest.raises(Exception) as exc_info:  # noqa: PT011 - assert on chain below
            # execute() applies the env-derived model default via validate_inputs;
            # the provider fail-loud fires regardless of model.
            node.execute(messages=_MESSAGES)
        # The typed ConfigurationError is in the cause chain OR named in the message.
        chain = []
        err = exc_info.value
        while err is not None:
            chain.append(err)
            err = getattr(err, "__cause__", None)
        assert any(isinstance(e, ConfigurationError) for e in chain) or (
            "ConfigurationError" in str(exc_info.value)
        ), f"expected ConfigurationError in the failure chain, got {chain!r}"

    def test_explicit_none_provider_fails_loud(self):
        # An EXPLICIT provider=None is treated identically to an omitted one —
        # None is "unresolved" regardless of how it arrived.
        node = LLMAgentNode()
        with pytest.raises(ConfigurationError):
            node.run(provider=None, messages=_MESSAGES)


class TestExplicitMockStillWorks:
    """The mock provider stays reachable when requested EXPLICITLY."""

    def test_explicit_mock_dispatches_mock_response(self):
        node = LLMAgentNode()
        result = node.execute(provider="mock", messages=_MESSAGES)
        assert isinstance(result, dict)
        assert result.get("success") is True
        # A mock response object is returned — fabricated-but-EXPLICITLY-requested,
        # which is the legitimate test-harness contract (never a silent default).
        assert result.get("response"), "explicit mock provider returned no response"
