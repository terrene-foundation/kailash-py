"""Regression test — mock-upgrade substitution MUST be provider-gated.

``kaizen.core.agents.Agent`` ships a test-harness "mock-upgrade" mechanism:
``_extract_intelligent_response`` (direct-LLM / CoT / ReAct paths) and
``_apply_intelligent_mock_conversion_to_llm_result`` (signature-based path)
both classify LLM output as ``is_mock_response`` via an unconditional
``startswith()`` check against three generic openers —

    "I understand you want me to work with"
    "Regarding your question about"
    "Based on the provided data and context"

— plus the substring "Mock vision response for testing". On a match, the
REAL response content was silently discarded and replaced with
``_generate_intelligent_mock_response()``: a hardcoded keyword-lookup table
("2+2" -> "4", "capital of france" -> "Paris", plus a catch-all filler
paragraph). This classifier ran on the PRODUCTION response path with NO
provider guard — so a genuine real-provider answer to an analytical/RAG
query that happens to *open* with "Based on the provided data and
context..." (a phrasing real models commonly produce) was misclassified as
mock, its real content dropped, and a fabricated lookup answer substituted
in its place and returned to the user as if it were the model's answer.

This is a zero-tolerance Rule 2 (hardcoded mock responses on a production
path) + Rule 3 (silent fallback discarding real output) violation. The three
openers originate ONLY from the mock transport
(``kaizen/llm/testing/mock_transport.py``) and ``LLMAgentNode``'s built-in
mock fallback (``kaizen/nodes/ai/llm_agent.py::_mock_llm_response``), which
is itself only ever dispatched when ``provider == "mock"``
(``kaizen/nodes/ai/llm_agent.py::run``). So the fix is a PROVIDER GATE, not
LLM reasoning and not removal of the test-harness behavior: both
``is_mock_response`` classifier sites now additionally require
``Agent._is_mock_provider_active()`` (True only when
``_get_provider_for_config() == "mock"`` — the SAME provider-resolution
method used to build the ``provider`` param actually dispatched to
``LLMAgentNode``).

Scope of THIS file's coverage: within the two classifier functions covered
here (``_extract_intelligent_response`` and
``_apply_intelligent_mock_conversion_to_llm_result``), a REAL provider's
output is now returned verbatim regardless of what it happens to open
with. Genuine mock-provider output through those same two functions is
still upgraded to an intelligent mock answer (existing test-harness
behavior preserved). Every mock-upgrade firing now emits a WARN-level,
grep-able ``mode=fake`` log line per rules/observability.md Rule 3 (with
the payload itself fingerprinted, never logged raw, per rules/security.md
"No secrets in logs").

This file does NOT cover the whole-``Agent`` surface. Two adjacent gaps,
each covered by a SEPARATE regression test class in this same file:
(1) the ``_signature_workflow`` cache in ``_execute_with_signature`` bakes
``provider`` in ONCE and can dispatch under a STALE provider even after
``update_config()``/``set_signature()``/``reset()`` change it live — see
``TestSignatureWorkflowCacheInvalidation``; (2) ``_execute_with_pattern``
(``execute_cot``/``execute_react``) never set ``provider`` at all and
silently fell back to ``LLMAgentNode``'s own ``"mock"`` default — see
``TestPatternExecutionProviderPropagation``.

These are Tier 1 unit tests: `Agent` is constructed with an explicit
``provider`` config value (never relying on ambient ``OPENAI_API_KEY`` /
``ANTHROPIC_API_KEY`` env-var auto-detection), and the private classifier
methods are called directly with deterministic inputs — no network call, no
env-var mutation, so no env-var lock (rules/testing.md § Env-Var Lock
Discipline) is required. Per rules/env-models.md, the model identifier is
resolved from env via the module's own ``_resolve_default_model()`` helper
— never a hardcoded literal.
"""

from __future__ import annotations

import logging
import threading
from typing import Iterator

import pytest

from kaizen.core.agents import Agent, _fingerprint_payload, _resolve_default_model

pytestmark = pytest.mark.regression

_AGENT_LOGGER_NAME = "kaizen.core.agents"

# Module-scope env lock per rules/testing.md § "Serialize Env-Var-Mutating
# Tests Via Module Lock" — matches the established lock domain used by
# tests/regression/test_issue_fnew5_provider_intrinsic_defaults.py for the
# SAME env surface (OPENAI_API_KEY / ANTHROPIC_API_KEY).
_ENV_LOCK = threading.Lock()

# Every env var `_get_provider_for_config()` / `_create_llm_agent_params`
# consult. Cleared before the one test in this file that mutates env, so
# ambient .env (or this repo's root-conftest LLM cost-guard scrub) never
# leaks into the assertion either way.
_PROVIDER_ENV_VARS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")


@pytest.fixture
def _env_serialized(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with _ENV_LOCK:
        for var in _PROVIDER_ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        yield


# Real-looking answers that happen to OPEN with one of the mock-transport's
# generic templates. A genuine model can plausibly produce prose starting
# this way (especially the RAG/analytical opener); none of these strings
# were ever really produced by a mock-only transport in this test — they are
# stand-ins for "real provider output that collides with a mock template".
_COLLIDING_REAL_CONTENTS = [
    # Collides with "Based on the provided data and context" opener.
    "Based on the provided data and context, the Q3 revenue decline of 12% "
    "correlates with three factors: increased customer acquisition cost, "
    "elevated churn in the enterprise segment, and delayed feature releases "
    "in the analytics product line.",
    # Collides with "Regarding your question about" opener.
    "Regarding your question about the merger timeline, the due-diligence "
    "phase typically spans eight to twelve weeks depending on regulatory "
    "review requirements.",
    # Collides with "I understand you want me to work with" opener.
    "I understand you want me to work with the uploaded spreadsheet to "
    "produce a quarterly variance report broken out by region.",
    # Collides with the "Mock vision response for testing" substring.
    "I can see the image(s) you've provided. Based on my analysis, "
    "[Mock vision response for testing]",
]

_REAL_PROVIDERS = ["openai", "anthropic"]

# Deterministic mock-upgrade fixture: `_generate_intelligent_mock_response`
# hardcodes "2+2" -> "4" (kaizen/core/agents.py `_generate_intelligent_mock_response`).
_DETERMINISTIC_MOCK_INPUTS = {"question": "What is 2+2?"}
_DETERMINISTIC_MOCK_ANSWER = "4"


def _make_agent(provider: str) -> Agent:
    """Build an ``Agent`` with an EXPLICIT provider (never env-detected).

    ``_get_provider_for_config()`` returns ``self.config["provider"]``
    verbatim whenever the key is present, before ever consulting
    ``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY`` — so this fully controls the
    provider gate without touching the environment.
    """
    return Agent(
        "mock_upgrade_provider_gate_test_agent",
        {"provider": provider, "model": _resolve_default_model()},
    )


class TestIsMockProviderActiveGate:
    """Direct coverage of the shared gate predicate."""

    @pytest.mark.parametrize("provider", _REAL_PROVIDERS + ["google", "ollama"])
    def test_real_and_other_non_mock_providers_are_not_mock(self, provider):
        agent = _make_agent(provider)
        assert agent._is_mock_provider_active() is False

    def test_mock_provider_is_mock(self):
        agent = _make_agent("mock")
        assert agent._is_mock_provider_active() is True


class TestExtractIntelligentResponseProviderGate:
    """``_extract_intelligent_response`` — direct-LLM / CoT / ReAct paths."""

    @pytest.mark.parametrize("provider", _REAL_PROVIDERS)
    @pytest.mark.parametrize("content", _COLLIDING_REAL_CONTENTS)
    def test_real_provider_content_returned_verbatim(self, provider, content):
        """A REAL provider's answer MUST survive unmodified, even when it
        happens to open with a mock-transport template string."""
        agent = _make_agent(provider)
        llm_result = {"content": content}

        result = agent._extract_intelligent_response(
            llm_result, _DETERMINISTIC_MOCK_INPUTS
        )

        assert result["answer"] == content.strip()
        assert result["response"] == content.strip()
        # MUST NOT have been silently swapped for the fabricated lookup answer.
        assert result["answer"] != _DETERMINISTIC_MOCK_ANSWER

    @pytest.mark.parametrize("provider", _REAL_PROVIDERS)
    def test_real_provider_emits_no_fake_mode_warning(self, provider, caplog):
        agent = _make_agent(provider)
        llm_result = {"content": _COLLIDING_REAL_CONTENTS[0]}

        with caplog.at_level(logging.WARNING, logger=_AGENT_LOGGER_NAME):
            agent._extract_intelligent_response(llm_result, _DETERMINISTIC_MOCK_INPUTS)

        assert not any("mode=fake" in rec.getMessage() for rec in caplog.records)

    @pytest.mark.parametrize("content", _COLLIDING_REAL_CONTENTS)
    def test_mock_provider_still_upgrades(self, content):
        """Existing test-harness behavior is PRESERVED: genuine mock-provider
        output is still substituted with an intelligent mock answer derived
        from the original inputs."""
        agent = _make_agent("mock")
        llm_result = {"content": content}

        result = agent._extract_intelligent_response(
            llm_result, _DETERMINISTIC_MOCK_INPUTS
        )

        assert result["answer"] == _DETERMINISTIC_MOCK_ANSWER
        assert result["answer"] != content.strip()

    def test_mock_provider_emits_fake_mode_warning(self, caplog):
        agent = _make_agent("mock")
        llm_result = {"content": _COLLIDING_REAL_CONTENTS[0]}

        with caplog.at_level(logging.WARNING, logger=_AGENT_LOGGER_NAME):
            agent._extract_intelligent_response(llm_result, _DETERMINISTIC_MOCK_INPUTS)

        fake_records = [
            rec
            for rec in caplog.records
            if "mode=fake" in rec.getMessage() and rec.levelno == logging.WARNING
        ]
        assert fake_records, "Expected a WARN-level mode=fake log line on mock-upgrade"

    def test_mock_provider_warning_fingerprints_inputs_not_raw(self, caplog):
        """rules/security.md "No secrets in logs" + rules/observability.md
        Rule 4/8: the WARN line MUST carry a fingerprint, never the raw
        caller-supplied ``original_inputs`` payload verbatim."""
        agent = _make_agent("mock")
        llm_result = {"content": _COLLIDING_REAL_CONTENTS[0]}

        with caplog.at_level(logging.WARNING, logger=_AGENT_LOGGER_NAME):
            agent._extract_intelligent_response(llm_result, _DETERMINISTIC_MOCK_INPUTS)

        warn_messages = [
            rec.getMessage() for rec in caplog.records if rec.levelno == logging.WARNING
        ]
        assert warn_messages, "Expected at least one WARN record"
        expected_fingerprint = _fingerprint_payload(_DETERMINISTIC_MOCK_INPUTS)
        assert any(expected_fingerprint in msg for msg in warn_messages)
        # The raw input dict MUST NOT appear verbatim in ANY WARN line.
        raw_dump = str(_DETERMINISTIC_MOCK_INPUTS)
        assert not any(raw_dump in msg for msg in warn_messages)


class TestApplyIntelligentMockConversionProviderGate:
    """``_apply_intelligent_mock_conversion_to_llm_result`` — signature path."""

    @pytest.mark.parametrize("provider", _REAL_PROVIDERS)
    @pytest.mark.parametrize("content", _COLLIDING_REAL_CONTENTS)
    def test_real_provider_content_returned_verbatim(self, provider, content):
        agent = _make_agent(provider)
        llm_result = {"content": content}

        result = agent._apply_intelligent_mock_conversion_to_llm_result(llm_result)

        assert result["content"] == content
        assert result["content"] != _DETERMINISTIC_MOCK_ANSWER

    @pytest.mark.parametrize("provider", _REAL_PROVIDERS)
    def test_real_provider_emits_no_fake_mode_warning(self, provider, caplog):
        agent = _make_agent(provider)
        llm_result = {"content": _COLLIDING_REAL_CONTENTS[0]}

        with caplog.at_level(logging.WARNING, logger=_AGENT_LOGGER_NAME):
            agent._apply_intelligent_mock_conversion_to_llm_result(llm_result)

        assert not any("mode=fake" in rec.getMessage() for rec in caplog.records)

    @pytest.mark.parametrize("content", _COLLIDING_REAL_CONTENTS)
    def test_mock_provider_still_upgrades(self, content):
        agent = _make_agent("mock")
        agent._current_execution_inputs = _DETERMINISTIC_MOCK_INPUTS
        llm_result = {"content": content}

        result = agent._apply_intelligent_mock_conversion_to_llm_result(llm_result)

        assert result["content"] == _DETERMINISTIC_MOCK_ANSWER
        assert result["content"] != content

    def test_mock_provider_emits_fake_mode_warning(self, caplog):
        agent = _make_agent("mock")
        agent._current_execution_inputs = _DETERMINISTIC_MOCK_INPUTS
        llm_result = {"content": _COLLIDING_REAL_CONTENTS[0]}

        with caplog.at_level(logging.WARNING, logger=_AGENT_LOGGER_NAME):
            agent._apply_intelligent_mock_conversion_to_llm_result(llm_result)

        fake_records = [
            rec
            for rec in caplog.records
            if "mode=fake" in rec.getMessage() and rec.levelno == logging.WARNING
        ]
        assert fake_records, "Expected a WARN-level mode=fake log line on mock-upgrade"

    def test_mock_provider_warning_fingerprints_content_not_raw(self, caplog):
        """rules/security.md "No secrets in logs" + rules/observability.md
        Rule 4/8: the WARN line MUST carry a fingerprint, never the raw
        LLM ``response_content`` payload verbatim."""
        agent = _make_agent("mock")
        agent._current_execution_inputs = _DETERMINISTIC_MOCK_INPUTS
        content = _COLLIDING_REAL_CONTENTS[0]
        llm_result = {"content": content}

        with caplog.at_level(logging.WARNING, logger=_AGENT_LOGGER_NAME):
            agent._apply_intelligent_mock_conversion_to_llm_result(llm_result)

        warn_messages = [
            rec.getMessage() for rec in caplog.records if rec.levelno == logging.WARNING
        ]
        assert warn_messages, "Expected at least one WARN record"
        expected_fingerprint = _fingerprint_payload(content)
        assert any(expected_fingerprint in msg for msg in warn_messages)
        # The raw response content MUST NOT appear verbatim in ANY WARN line.
        assert not any(content in msg for msg in warn_messages)


class _RecordingKaizenStub:
    """Stub ``kaizen_instance`` for ``_execute_with_signature`` that records
    the dispatched ``provider`` read off each built workflow's node config,
    and returns a FIXED canned response regardless of what provider was
    dispatched. Returning a fixed response (rather than branching on the
    dispatched provider) isolates the cache-invalidation correctness
    property (FIX 1) from the classifier gate (already covered by the
    classes above): the SAME colliding content is dispatched on every call,
    so any divergence in ``result["answer"]`` between calls is caused
    SOLELY by the live gate (``_is_mock_provider_active()``) agreeing or
    disagreeing with whatever provider was actually recorded as dispatched.
    """

    def __init__(self, agent_id: str, response_content: str) -> None:
        self._agent_id = agent_id
        self._response_content = response_content
        self.dispatched_providers: list = []

    def execute(self, built_workflow, parameters=None):
        # `built_workflow.nodes[id]` is a `kailash.workflow.graph.NodeInstance`
        # (pydantic model) exposing its params via a `.config` dict attribute
        # — NOT subscriptable itself.
        node_config = built_workflow.nodes[self._agent_id].config
        self.dispatched_providers.append(node_config.get("provider"))
        return ({self._agent_id: {"content": self._response_content}}, "run-id")


class TestSignatureWorkflowCacheInvalidation:
    """FIX 1 — the ``_signature_workflow`` cache built by
    ``_execute_with_signature`` bakes ``provider`` into the node config
    ONCE and reused it forever, even after ``update_config()`` /
    ``set_signature()`` / ``reset()`` changed the LIVE config. Because the
    provider-gate predicate (``_is_mock_provider_active()``) reads
    ``self.config["provider"]`` LIVE, a stale cache made dispatch and gate
    disagree — exactly the failure mode this PR's provider gate exists to
    prevent, reintroduced one layer up. ``update_config``/``set_signature``/
    ``reset`` now invalidate the cache so the NEXT execute() rebuilds the
    node config under the CURRENT provider.
    """

    def test_update_config_provider_change_reaches_second_dispatch(self):
        """Switching config provider "openai" -> "mock" MUST reach the
        SECOND dispatch (not the stale first-build value) — and because
        both dispatch AND gate now agree on "mock", the genuine mock-upgrade
        fires (existing test-harness behavior), not a gate/dispatch
        disagreement."""
        real_content = (
            "Based on the provided data and context, quarterly revenue grew "
            "8% driven by expansion in the enterprise segment."
        )
        stub = _RecordingKaizenStub("cache_invalidation_agent_1", real_content)
        agent = Agent(
            "cache_invalidation_agent_1",
            {"provider": "openai", "model": _resolve_default_model()},
            signature="question -> answer",
            kaizen_instance=stub,
        )

        # First dispatch: provider="openai" (real). Gate agrees (real);
        # content matches a trigger phrase but MUST still survive verbatim.
        result1 = agent.execute(question="What changed this quarter?")
        # `execute()` returns Dict in signature-mode, Tuple in workflow-mode
        # (agents.py:2571 idiom) — narrow for pyright before subscripting.
        assert isinstance(result1, dict), (
            "execute() with a signature MUST return Dict (signature-mode)"
        )
        assert stub.dispatched_providers == ["openai"]
        assert result1["answer"] == real_content

        # The documented mutator for changing provider on a live agent.
        agent.update_config({"provider": "mock"})

        # Second dispatch MUST reflect the NEW provider, not the stale
        # cached "openai" — this is FIX 1's core correctness property.
        result2 = agent.execute(question="What changed this quarter?")
        assert isinstance(result2, dict), (
            "execute() with a signature MUST return Dict (signature-mode)"
        )
        assert stub.dispatched_providers == ["openai", "mock"], (
            "second dispatch used a STALE cached provider instead of the "
            "live config — update_config() silently failed to propagate"
        )
        # Dispatch and gate now agree ("mock" both places) -> genuine
        # mock-upgrade fires; the real-looking content is intentionally
        # replaced because the agent is NOW actually mock-configured.
        assert result2["answer"] != real_content

    def test_update_config_real_to_real_provider_change_stays_verbatim(self):
        """Switching between two REAL providers MUST leave trigger-phrase
        content verbatim on BOTH dispatches — the gate must never misfire
        due to a stale cached provider disagreeing with the live config."""
        real_content = (
            "Based on the provided data and context, quarterly revenue grew "
            "8% driven by expansion in the enterprise segment."
        )
        stub = _RecordingKaizenStub("cache_invalidation_agent_2", real_content)
        agent = Agent(
            "cache_invalidation_agent_2",
            {"provider": "openai", "model": _resolve_default_model()},
            signature="question -> answer",
            kaizen_instance=stub,
        )

        result1 = agent.execute(question="What changed this quarter?")
        assert isinstance(result1, dict), (
            "execute() with a signature MUST return Dict (signature-mode)"
        )
        assert stub.dispatched_providers == ["openai"]
        assert result1["answer"] == real_content

        agent.update_config({"provider": "anthropic"})

        result2 = agent.execute(question="What changed this quarter?")
        assert isinstance(result2, dict), (
            "execute() with a signature MUST return Dict (signature-mode)"
        )
        assert stub.dispatched_providers == ["openai", "anthropic"]
        # Both dispatches real -> gate never fires -> verbatim both times.
        assert result2["answer"] == real_content

    def test_set_signature_invalidates_cache(self):
        from kaizen.signatures import Signature as _Signature

        stub = _RecordingKaizenStub("sig_invalidate_agent", "irrelevant content")
        agent = Agent(
            "sig_invalidate_agent",
            {"provider": "openai", "model": _resolve_default_model()},
            signature="question -> answer",
            kaizen_instance=stub,
        )
        agent.execute(question="warm the cache")
        assert hasattr(agent, "_signature_workflow")

        agent.set_signature(_Signature(inputs=["question"], outputs=["answer"]))
        assert not hasattr(agent, "_signature_workflow")

    def test_reset_invalidates_cache(self):
        stub = _RecordingKaizenStub("reset_invalidate_agent", "irrelevant content")
        agent = Agent(
            "reset_invalidate_agent",
            {"provider": "openai", "model": _resolve_default_model()},
            signature="question -> answer",
            kaizen_instance=stub,
        )
        agent.execute(question="warm the cache")
        assert hasattr(agent, "_signature_workflow")

        agent.reset()
        assert not hasattr(agent, "_signature_workflow")


class _PatternRecordingKaizenStub:
    """Stub ``kaizen_instance`` for ``execute_cot``/``execute_react`` that
    records the dispatched ``provider`` off the pattern-executor's built
    workflow node (``f"{agent_id}_{pattern}"``)."""

    def __init__(self, node_id: str, response_content: str) -> None:
        self._node_id = node_id
        self._response_content = response_content
        self.dispatched_providers: list = []

    def execute(self, built_workflow, parameters=None):
        # See `_RecordingKaizenStub.execute` above re: `NodeInstance.config`.
        node_config = built_workflow.nodes[self._node_id].config
        self.dispatched_providers.append(node_config.get("provider"))
        return ({self._node_id: {"content": self._response_content}}, "run-id")


class TestPatternExecutionProviderPropagation:
    """FIX 4 — ``_execute_with_pattern`` (``execute_cot``/``execute_react``)
    built its node params with NO ``provider`` key at all. Neither
    ``compile_to_workflow_params()`` nor the pattern executors'
    ``get_enhanced_parameters()`` ever injected one either, so
    ``LLMAgentNode`` fell through to its OWN parameter default
    (``"mock"`` — see ``kaizen/nodes/ai/llm_agent.py::get_parameters``),
    meaning every CoT/ReAct execution silently mock-dispatched regardless
    of the agent's actually configured provider. Fixed by setting
    ``base_params["provider"] = self._get_provider_for_config()`` — the
    SAME env-first resolution used by every other execute path.
    """

    def test_execute_cot_dispatches_configured_real_provider(self):
        agent_id = "cot_provider_propagation_agent"
        node_id = f"{agent_id}_chain_of_thought"
        stub = _PatternRecordingKaizenStub(
            node_id, "Step 1: multiply. Final Answer: 42"
        )
        agent = Agent(
            agent_id,
            {"provider": "openai", "model": _resolve_default_model()},
            signature="problem -> reasoning, answer",
            kaizen_instance=stub,
        )

        agent.execute_cot(problem="What is 6 * 7?")

        assert stub.dispatched_providers == ["openai"]
        assert "mock" not in stub.dispatched_providers

    def test_execute_react_dispatches_configured_real_provider(self):
        agent_id = "react_provider_propagation_agent"
        node_id = f"{agent_id}_react"
        stub = _PatternRecordingKaizenStub(
            node_id, "Thought: research. Final Answer: done"
        )
        agent = Agent(
            agent_id,
            {"provider": "anthropic", "model": _resolve_default_model()},
            signature="task -> thought, action, observation",
            kaizen_instance=stub,
        )

        agent.execute_react(task="Research topic X")

        assert stub.dispatched_providers == ["anthropic"]
        assert "mock" not in stub.dispatched_providers


class TestDirectConfigMutationDoesNotDesyncGateFromDispatch:
    """PART A — a direct ``agent.config["provider"] = "mock"`` mutation (the
    idiom used at ``tests/unit/test_agents_comprehensive.py:307``) bypasses
    the 3 cache-invalidating mutators (``update_config``/``set_signature``/
    ``reset``) entirely — it writes straight into the dict those mutators
    guard. Before PART A, the classifier gate re-derived provider LIVE from
    `self.config` at classification time, so this direct mutation alone
    would desync the gate from whatever was ACTUALLY dispatched, silently
    discarding real output. Threading `dispatched_provider` through the
    classifier closes this: the gate uses the value ACTUALLY placed in the
    dispatched node config, which a later direct-dict mutation cannot
    retroactively change.

    FIX 15 note (Round 5): the 3rd test in this class
    (``test_direct_mutation_now_reaches_second_dispatch_after_fix15``)
    exercises the REAL `_execute_with_signature` cache, not the classifier
    function directly. FIX 15 made that cache provider-aware, so a direct
    mutation now reaches the very next dispatch instead of leaving it
    stale — PART A's dispatched-provider-threading remains valid
    defense-in-depth (the first 2 tests below, which call the classifier
    directly with an explicit `dispatched_provider`, are unaffected), but
    the 3rd test's expected OUTCOME changed: the cache no longer goes
    stale in the first place, so there is nothing left to "correctly
    survive despite staleness" — the mutation takes effect immediately.
    """

    def test_direct_mutation_after_dispatch_leaves_gate_using_dispatched_value(self):
        """Simulates the exact race PART A closes: a REAL dispatch happens
        under "openai", then — AFTER dispatch-build but BEFORE
        classification — something mutates `agent.config["provider"]`
        directly to "mock" (bypassing every cache-invalidating mutator).
        The classifier MUST still treat this as a REAL-provider result
        because `dispatched_provider="openai"` was threaded from the
        ACTUAL dispatch, not re-derived from the (now-mutated) live config.
        """
        agent = _make_agent("openai")
        content = _COLLIDING_REAL_CONTENTS[0]
        llm_result = {"content": content}

        # Direct dict-write idiom — bypasses update_config()'s invalidation
        # entirely (there is nothing here for it to invalidate; the point is
        # the LIVE config now disagrees with what was already dispatched).
        agent.config["provider"] = "mock"

        # `dispatched_provider="openai"` represents the provider value that
        # was ACTUALLY placed in the node config at dispatch-build time,
        # BEFORE the mutation above.
        result = agent._extract_intelligent_response(
            llm_result, _DETERMINISTIC_MOCK_INPUTS, dispatched_provider="openai"
        )

        assert result["answer"] == content.strip(), (
            "gate must follow the DISPATCHED provider, not the live "
            "(direct-mutated) config — real content was wrongly discarded"
        )
        assert result["answer"] != _DETERMINISTIC_MOCK_ANSWER

    def test_direct_mutation_reaches_fallback_gate_when_no_dispatched_provider(self):
        """Contrast case: WITHOUT a `dispatched_provider`, the classifier
        falls back to `_is_mock_provider_active()` (live re-derivation), so
        the SAME direct mutation DOES flip the gate — this is the
        documented, intentional fallback behavior for callers that cannot
        supply the dispatched value, not a bug."""
        agent = _make_agent("openai")
        content = _COLLIDING_REAL_CONTENTS[0]
        llm_result = {"content": content}

        agent.config["provider"] = "mock"

        result = agent._extract_intelligent_response(
            llm_result, _DETERMINISTIC_MOCK_INPUTS
        )

        assert result["answer"] == _DETERMINISTIC_MOCK_ANSWER
        assert agent._is_mock_provider_active() is True

    def test_direct_mutation_now_reaches_second_dispatch_after_fix15(self):
        """End-to-end variant through the REAL `_execute_with_signature`
        path. Historically (pre-FIX-15), this test asserted the OPPOSITE
        of what it asserts now: a direct `agent.config["provider"] =
        "mock"` mutation (NOT `update_config()`) left the cached
        `_signature_workflow` — and therefore the ACTUAL dispatch — on the
        ORIGINAL "openai" provider forever, because the cache was guarded
        by a bare `hasattr` check with no provider-freshness tracking.

        FIX 15 (Round 5 final-sweep finding — the SAME class of gap as
        FIX 12/13) closed that: the cache now re-reads
        `_get_provider_for_config()` (which itself reads LIVE off
        `self.config`) on every call, so a direct dict mutation is picked
        up on the very NEXT dispatch, exactly like `update_config()`
        already was. The SECOND dispatch therefore genuinely occurs under
        "mock" — and because the dispatched content collides with a known
        mock-response pattern AND the dispatch is now GENUINELY "mock",
        the mock-upgrade classifier correctly substitutes it. That is the
        gate working AS DESIGNED (a genuine mock-provider dispatch with
        mock-pattern-colliding content SHOULD be substituted) — not the
        bug the classifier-threading (PART A) fix was closing."""
        real_content = _COLLIDING_REAL_CONTENTS[0]
        stub = _RecordingKaizenStub("direct_mutation_agent", real_content)
        agent = Agent(
            "direct_mutation_agent",
            {"provider": "openai", "model": _resolve_default_model()},
            signature="question -> answer",
            kaizen_instance=stub,
        )

        # Warm the cache — first dispatch under the real "openai" provider.
        result1 = agent.execute(question="What changed this quarter?")
        assert isinstance(result1, dict), (
            "execute() with a signature MUST return Dict (signature-mode)"
        )
        assert stub.dispatched_providers == ["openai"]
        assert result1["answer"] == real_content

        # Direct dict mutation — bypasses update_config()'s explicit
        # invalidation call, but FIX 15's provider-aware memo check picks
        # up the drift anyway (it re-derives the LIVE resolved provider on
        # every call, not just at the 3 named mutator call sites).
        agent.config["provider"] = "mock"

        result2 = agent.execute(question="What changed this quarter?")
        assert isinstance(result2, dict), (
            "execute() with a signature MUST return Dict (signature-mode)"
        )
        # FIX 15: the cache rebuilds, so the SECOND dispatch genuinely
        # occurs under "mock" — no longer stuck on the stale "openai".
        assert stub.dispatched_providers == ["openai", "mock"], (
            "FIX 15 MUST make a direct provider mutation reach the very "
            "next dispatch, not leave _signature_workflow stale"
        )
        # Content collides with a known mock pattern AND the dispatch is
        # genuinely "mock" now -> the mock-upgrade gate correctly fires.
        assert result2["answer"] != real_content


class TestCommunicateWithProviderPropagation:
    """PART B — `communicate_with()` never set `provider` in
    `communication_params` at all, so every inter-agent communication
    silently mock-dispatched regardless of the RECEIVING agent's actually
    configured provider — and (unlike every other LLMAgentNode-param site)
    this path has NO mock-upgrade gating, so the raw mock template would be
    returned verbatim as the inter-agent reply. Fixed by setting
    `communication_params["provider"] = target_agent._get_provider_for_config()`.
    """

    def test_communicate_with_dispatches_target_agents_real_provider(self):
        sender = Agent(
            "comm_sender_agent",
            {"provider": "mock", "model": _resolve_default_model()},
        )
        receiver = Agent(
            "comm_receiver_agent",
            {"provider": "openai", "model": _resolve_default_model()},
        )

        dispatched_providers: list = []

        class _CommRecordingKaizenStub:
            def execute(self, built_workflow, parameters=None):
                node_id = f"comm_response_{receiver.name}"
                node_config = built_workflow.nodes[node_id].config
                dispatched_providers.append(node_config.get("provider"))
                return (
                    {node_id: {"response": {"content": "Acknowledged."}}},
                    "run-id",
                )

        sender.kaizen = _CommRecordingKaizenStub()

        response = sender.communicate_with(receiver, "What's your analysis?")

        assert dispatched_providers == ["openai"], (
            "communicate_with() MUST dispatch under the RECEIVING agent's "
            "configured provider, not silently fall back to mock"
        )
        assert response["message"] == "Acknowledged."


class TestCompileWorkflowProviderPropagation:
    """PART B — `compile_workflow()`'s `node_params` never set `provider`
    unless `self.config` happened to already carry an explicit key, so an
    agent relying on env-detected provider resolution (the common case)
    would silently compile a mock-dispatching node regardless of real API
    keys present. Fixed by setting `node_params["provider"] =
    self._get_provider_for_config()` explicitly.
    """

    def test_compile_workflow_node_carries_real_provider(self):
        """No explicit `provider` in config — the common case, where
        `_get_provider_for_config()` auto-detects from ambient API keys.
        This is precisely the scenario the fix addresses: the pre-fix code
        only added `provider` to `node_params` via the loop over
        `self.config.items()` — which only fires when `self.config`
        ALREADY has an explicit "provider" key. An agent relying on
        auto-detection (no explicit key) got a `node_params` with NO
        "provider" key at all, silently falling through to LLMAgentNode's
        own "mock" parameter default regardless of real API keys present.
        Asserting `"provider" in node_config` (rather than pinning a
        specific provider string) keeps this test environment-independent:
        it fails pre-fix regardless of which/whether an API key happens to
        be configured in the ambient environment.
        """
        agent = Agent(
            "compile_workflow_provider_agent",
            {"model": _resolve_default_model()},  # NO explicit "provider"
        )
        expected_provider = agent._get_provider_for_config()

        workflow = agent.compile_workflow()

        # `workflow` is an UNBUILT `WorkflowBuilder` — `.nodes[id]` is a
        # dict-shaped spec (`{"type": ..., "config": ...}`), NOT the
        # pydantic `NodeInstance` a BUILT `Workflow.nodes[id]` would be
        # (see `_RecordingKaizenStub` above re: that distinction).
        node_config = workflow.nodes[agent.agent_id]["config"]
        assert "provider" in node_config, (
            "compile_workflow() node_params MUST carry an explicit "
            "'provider' key even when self.config has none — omitting it "
            'silently falls through to LLMAgentNode\'s own "mock" default'
        )
        assert node_config["provider"] == expected_provider


class TestMultiModalSignatureCompilerProviderPropagation:
    """ADDITIONAL sibling finding (same class, discovered during the Part B
    LLMAgentNode-param-building sweep, fixed in the SAME PR per
    rules/security.md "Multi-Site Kwarg Plumbing"):
    `SignatureCompiler._create_llm_agent_params` (used by
    `compile_to_workflow_config()` / `Agent.compile_to_workflow()` for
    multi-modal signatures) hardcoded `config.get("provider", "mock")` — a
    signature config with NO explicit "provider" key silently
    mock-dispatched regardless of real API keys present. Fixed to mirror
    `Agent._get_provider_for_config()`'s env-first detection.
    """

    def test_create_llm_agent_params_uses_env_detected_provider(
        self, monkeypatch, _env_serialized
    ):
        """Deterministic regardless of ambient environment: this repo's root
        ``conftest.py`` actively SCRUBS ``OPENAI_API_KEY``/``ANTHROPIC_API_KEY``
        from ``os.environ`` for every bare test run (LLM cost-guard) — so
        asserting against whatever the ambient env happens to hold would
        pass identically for BOTH the buggy hardcoded-"mock" code and the
        fixed env-detecting code (both resolve to "mock" when no key is
        visible). Injecting a fake key via ``monkeypatch.setenv`` AFTER
        collection — when the test body actually runs — makes the key
        genuinely visible to `os.environ.get(...)`, giving the assertion
        real discriminating power between fixed and buggy behavior.
        """
        from kaizen.signatures.core import Signature, SignatureCompiler

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key")

        compiler = SignatureCompiler()
        config = {"model": _resolve_default_model()}  # NO explicit "provider"

        node_params = compiler._create_llm_agent_params(
            signature_obj=Signature(inputs=["question"], outputs=["answer"]),
            config=config,
        )

        assert node_params["provider"] == "anthropic"

    def test_create_llm_agent_params_explicit_provider_wins(self):
        from kaizen.signatures.core import Signature, SignatureCompiler

        compiler = SignatureCompiler()
        config = {"model": _resolve_default_model(), "provider": "anthropic"}

        node_params = compiler._create_llm_agent_params(
            signature_obj=Signature(inputs=["question"], outputs=["answer"]),
            config=config,
        )

        assert node_params["provider"] == "anthropic"


class _FakeNexusAgentConfig:
    """Minimal stand-in for the config object `NexusDeploymentMixin.to_workflow()`
    reads (`llm_provider`, `model`, `temperature`) — avoids depending on the
    full `BaseAgentConfig` dataclass construction path for a mixin-only test.
    """

    def __init__(self, llm_provider=None, model=None, temperature=0.7):
        self.llm_provider = llm_provider
        self.model = model
        self.temperature = temperature


class TestNexusDeploymentMixinProviderKey:
    """FIX 5 — `NexusDeploymentMixin.to_workflow()` (kaizen/integrations/
    nexus/base.py) passed `"llm_provider"` to `add_node("LLMAgentNode",
    ...)`. LLMAgentNode's declared NodeParameter is named `"provider"` — it
    never reads `"llm_provider"` — so even an EXPLICITLY configured real
    provider was silently ignored and the node fell through to
    LLMAgentNode's own `"mock"` parameter default. A publicly-exported
    deployment mixin serving mock output to real requests. Fixed to emit
    `"provider"`, falling back to the same openai/anthropic/mock env-first
    order `Agent._get_provider_for_config()` uses when `llm_provider` is
    unset (never leaves an unset/None provider — that re-defaults to mock).
    """

    class _NexusOnlyAgent:
        """Uses ONLY the mixin's `to_workflow()` via explicit delegation —
        NOT via inheriting `NexusDeploymentMixin` alongside `BaseAgent`.
        A class combining `(BaseAgent, NexusDeploymentMixin)` resolves
        `to_workflow()` to `BaseAgent`'s own (separately-fixed, already
        correct) implementation via MRO, masking this exact bug — see
        `tests/unit/integrations/test_nexus_base_classes.py
        ::test_workflow_preserves_llm_config`, which unintentionally
        exercises `BaseAgent.to_workflow()`, never the mixin's.
        """

        def __init__(self, config):
            self.config = config
            self.signature = None

        def _build_system_prompt(self):
            from kaizen.integrations.nexus.base import NexusDeploymentMixin

            return NexusDeploymentMixin._build_system_prompt(self)

        def to_workflow(self):
            from kaizen.integrations.nexus.base import NexusDeploymentMixin

            return NexusDeploymentMixin.to_workflow(self)

    @staticmethod
    def _llm_agent_node_config(agent) -> dict:
        # Deliberately do NOT `.build()`: the BUILT `Workflow.nodes[id]` is a
        # pydantic `NodeInstance` that auto-fills every declared NodeParameter
        # default (including "provider": "mock") for keys the raw params dict
        # never set — which would make a MISSING "provider" key
        # indistinguishable from an explicit one and defeat this exact
        # regression check. The UNBUILT `WorkflowBuilder.nodes[id]["config"]`
        # is the raw dict passed to `add_node(...)`, with no auto-fill.
        workflow = agent.to_workflow()
        node_id = next(iter(workflow.nodes))
        assert workflow.nodes[node_id]["type"] == "LLMAgentNode"
        return workflow.nodes[node_id]["config"]

    def test_explicit_provider_uses_provider_key_not_llm_provider(self):
        agent = self._NexusOnlyAgent(_FakeNexusAgentConfig(llm_provider="anthropic"))

        node_config = self._llm_agent_node_config(agent)

        assert node_config.get("provider") == "anthropic", (
            "NexusDeploymentMixin.to_workflow() MUST pass the real provider "
            "under the 'provider' key — LLMAgentNode never reads 'llm_provider'"
        )
        assert "llm_provider" not in node_config

    def test_unset_provider_falls_back_to_env_detection(self):
        agent = self._NexusOnlyAgent(_FakeNexusAgentConfig(llm_provider=None))

        node_config = self._llm_agent_node_config(agent)

        assert "provider" in node_config, (
            "the RAW (unbuilt) node params MUST carry an explicit 'provider' "
            "key even when llm_provider is unset — omitting it silently "
            "falls through to LLMAgentNode's own 'mock' parameter default"
        )
        assert node_config["provider"] is not None, (
            "an unset llm_provider MUST resolve via env-detection, never "
            "leave provider=None (which re-defaults to LLMAgentNode's mock)"
        )
        assert "llm_provider" not in node_config


class TestBaseAgentToWorkflowProviderKey:
    """FIX 6 — `BaseAgent.to_workflow()` (kaizen/core/base_agent.py) set
    `node_config["provider"]` ONLY when `self.config.llm_provider is not
    None`. `BaseAgentConfig` (kaizen/core/config.py, NOT agent_config.py)
    has NO provider auto-detection of its own, so `BaseAgent(model="...")`
    constructed with no explicit provider omitted the "provider" key
    entirely, silently falling through to LLMAgentNode's own "mock"
    parameter default. Reachable in production via Nexus
    `deploy_as_api`/`deploy_as_cli`/`deploy_as_mcp`
    (`kaizen/integrations/nexus/deployment.py`). Fixed to always emit an
    explicit "provider" key, env-detecting when unset.
    """

    @staticmethod
    def _llm_agent_node_config(agent) -> dict:
        # Deliberately do NOT `.build()` — see the identical comment in
        # `TestNexusDeploymentMixinProviderKey._llm_agent_node_config`: the
        # BUILT `NodeInstance` auto-fills LLMAgentNode's declared "provider"
        # NodeParameter default ("mock") for any key the raw params dict
        # never set, which would make a MISSING "provider" key
        # indistinguishable from an explicit one.
        workflow = agent.to_workflow()
        node_id = next(iter(workflow.nodes))
        assert workflow.nodes[node_id]["type"] == "LLMAgentNode"
        return workflow.nodes[node_id]["config"]

    def test_no_explicit_provider_still_emits_provider_key(self):
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig

        config = BaseAgentConfig(llm_provider=None, model=_resolve_default_model())
        agent = BaseAgent(config=config)

        node_config = self._llm_agent_node_config(agent)

        assert "provider" in node_config, (
            "BaseAgent.to_workflow() MUST always emit an explicit 'provider' "
            "key, even with no configured llm_provider — omitting it "
            "silently falls through to LLMAgentNode's own 'mock' default"
        )
        assert node_config["provider"] is not None

    def test_explicit_provider_is_preserved(self):
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig

        config = BaseAgentConfig(
            llm_provider="anthropic", model=_resolve_default_model()
        )
        agent = BaseAgent(config=config)

        node_config = self._llm_agent_node_config(agent)

        assert node_config["provider"] == "anthropic"


class TestDeploymentCacheKeyProviderResolution:
    """FIX 8 — `DeploymentCache.create_cache_key` (kaizen/integrations/nexus/
    deployment_cache.py) hashed the RAW `llm_provider` attribute, not the
    RESOLVED provider `to_workflow()` would actually dispatch to.
    `deploy_as_api`/`deploy_as_cli`/`deploy_as_mcp` (deployment.py, default
    `use_cache=True`) check the cache key BEFORE ever calling
    `agent.to_workflow()` — on a cache hit, `to_workflow()` never runs at
    all. When `llm_provider` is None (the common auto-detect case FIX5/
    FIX6 target), the OLD key was IDENTICAL regardless of ambient key
    availability. Scenario this closes: process starts with no keys ->
    deploy caches a `provider="mock"` workflow under a `llm_provider=None`
    key -> real keys are injected into the SAME long-lived process later
    -> a re-deploy hits the SAME stale key -> serves mock to real requests
    forever. Fixed by hashing the RESOLVED provider (`llm_provider or
    detect_provider_from_env()` — the SAME resolution `to_workflow()`
    uses), so the key changes the moment ambient key availability changes.
    """

    class _FakeAgent:
        """Minimal stand-in exposing exactly what `create_cache_key` reads
        (`agent.config.llm_provider`, `agent.config.model`,
        `agent.signature`) — avoids depending on the full `BaseAgentConfig`
        construction path for a cache-key-only test."""

        def __init__(self, llm_provider=None, model=None):
            self.config = _FakeNexusAgentConfig(llm_provider=llm_provider, model=model)
            self.signature = None

    def test_cache_key_differs_when_ambient_provider_availability_changes(
        self, monkeypatch, _env_serialized
    ):
        from kaizen.integrations.nexus.deployment_cache import DeploymentCache

        agent = self._FakeAgent(llm_provider=None, model=_resolve_default_model())

        # No real API keys present (cleared by `_env_serialized`) -> the
        # resolved provider is "mock".
        key_no_keys = DeploymentCache.create_cache_key(agent, "my_workflow")

        # Inject a real key AFTER the first key was computed — the SAME
        # agent object, SAME `llm_provider=None` — now resolves to "openai".
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
        key_with_openai_key = DeploymentCache.create_cache_key(agent, "my_workflow")

        assert key_no_keys != key_with_openai_key, (
            "cache key MUST change when ambient provider availability "
            "changes for an agent with no explicit llm_provider — "
            "otherwise a cache hit serves a stale mock-dispatching "
            "workflow forever after real keys are injected into the "
            "same long-lived process"
        )

    def test_cache_key_stable_when_explicit_provider_set_regardless_of_env(
        self, monkeypatch, _env_serialized
    ):
        """Contrast case: an EXPLICIT `llm_provider` MUST NOT be
        second-guessed by ambient env — the cache key stays stable
        regardless of what keys happen to be present, matching
        `to_workflow()`'s own explicit-wins precedence."""
        from kaizen.integrations.nexus.deployment_cache import DeploymentCache

        agent = self._FakeAgent(
            llm_provider="anthropic", model=_resolve_default_model()
        )

        key_no_keys = DeploymentCache.create_cache_key(agent, "my_workflow")

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")
        key_with_openai_key = DeploymentCache.create_cache_key(agent, "my_workflow")

        assert key_no_keys == key_with_openai_key


class TestToNodeConfigProviderKey:
    """FIX 9 — `Agent.to_node_config()` (kaizen/core/agents.py) returned
    ``{"config": self.config.copy(), ...}`` with NO provider resolution —
    the SAME LLMAgentNode-param-building bug class as the 6+ sites already
    fixed elsewhere in the Agent surface. A consumer feeding this dict
    straight to `add_node(...)` would silently mock-dispatch a
    real-provider agent. Fixed via
    ``resolved.setdefault("provider", self._get_provider_for_config())``.
    """

    def test_to_node_config_carries_explicit_provider(self):
        agent = _make_agent("anthropic")

        node_config = agent.to_node_config()

        assert "provider" in node_config["config"]
        assert node_config["config"]["provider"] == "anthropic"

    def test_to_node_config_consumer_built_node_dispatches_real_provider(self):
        """Mirrors `TestCompileWorkflowProviderPropagation`: a consumer
        that feeds `to_node_config()`'s output straight into
        `add_node(...)` MUST see the real resolved provider, not silently
        fall through to LLMAgentNode's own "mock" default."""
        from kailash.workflow.builder import WorkflowBuilder

        agent = _make_agent("anthropic")
        node_config = agent.to_node_config()

        workflow = WorkflowBuilder()
        workflow.add_node(
            node_config["type"], node_config["agent_id"], node_config["config"]
        )

        built_node_config = workflow.nodes[node_config["agent_id"]]["config"]
        assert built_node_config["provider"] == "anthropic"

    def test_to_node_config_no_explicit_provider_env_detects(self):
        """No explicit "provider" in config — the auto-detect case FIX 9
        targets. Asserts against `agent._get_provider_for_config()`
        (computed the SAME way, at the SAME env state) rather than a
        pinned literal, so the test stays environment-independent (this
        repo's root conftest actively scrubs OPENAI_API_KEY/
        ANTHROPIC_API_KEY for a bare test run)."""
        agent = Agent(
            "to_node_config_no_provider_agent",
            {"model": _resolve_default_model()},  # NO explicit "provider"
        )
        expected_provider = agent._get_provider_for_config()

        node_config = agent.to_node_config()

        assert "provider" in node_config["config"]
        assert node_config["config"]["provider"] == expected_provider


class TestBaseAgentToWorkflowMemoRebuildsOnProviderDrift:
    """FIX 12 — `BaseAgent.to_workflow()` (kaizen/core/base_agent.py)
    memoized `self._workflow` on first build with the THEN-resolved
    provider baked in, and `self._workflow` was only reset by `cleanup()`
    — never by a config OR ambient-env change. Because provider resolution
    is env-dependent (FIX 6: `llm_provider or detect_provider_from_env()`),
    the memo could go stale: process starts with no keys -> to_workflow()
    builds+memoizes provider="mock" -> a real key is injected into the
    SAME long-lived process -> the SAME agent's NEXT to_workflow() call
    returned the STALE mock-dispatching memo — even through
    `deploy_as_api`, even after `clear_deployment_cache()` (FIX 8 alone
    cannot fix this; it only makes the CACHE KEY track the resolved
    provider, it does not make `to_workflow()` itself re-resolve). Fixed
    by tracking `self._workflow_provider` (the provider the memo was BUILT
    with) and trusting the memo ONLY when it still matches the CURRENT
    resolved provider.
    """

    @staticmethod
    def _llm_agent_node_config(workflow) -> dict:
        node_id = next(iter(workflow.nodes))
        assert workflow.nodes[node_id]["type"] == "LLMAgentNode"
        return workflow.nodes[node_id]["config"]

    def test_memo_rebuilds_when_ambient_provider_drifts(
        self, monkeypatch, _env_serialized
    ):
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig

        config = BaseAgentConfig(llm_provider=None, model=_resolve_default_model())
        agent = BaseAgent(config=config)

        # No real keys present (cleared by `_env_serialized`) -> resolves
        # to "mock" and memoizes it.
        wf1 = agent.to_workflow()
        node1 = self._llm_agent_node_config(wf1)
        assert node1["provider"] == "mock"

        # Inject a real key AFTER the first build — the SAME agent
        # instance, SAME llm_provider=None (no `update_config`/config
        # mutation of any kind — purely an ambient env change).
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")

        wf2 = agent.to_workflow()
        node2 = self._llm_agent_node_config(wf2)
        assert node2["provider"] == "openai", (
            "to_workflow() MUST rebuild (not return the stale memo) when "
            "the resolved provider drifts due to an ambient env change"
        )
        assert wf1 is not wf2, (
            "a provider-drifted call MUST NOT reuse the old memo object"
        )

    def test_memo_reused_when_provider_stable(self, monkeypatch, _env_serialized):
        """Perf-benefit check (no regression): the memo IS still reused
        (SAME object, no rebuild) across repeated calls when the resolved
        provider does NOT change."""
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.config import BaseAgentConfig

        config = BaseAgentConfig(
            llm_provider="anthropic", model=_resolve_default_model()
        )
        agent = BaseAgent(config=config)

        wf1 = agent.to_workflow()
        wf2 = agent.to_workflow()
        wf3 = agent.to_workflow()

        assert wf1 is wf2 is wf3, (
            "stable-provider case MUST still memoize (no perf regression) — "
            "the fix rebuilds ONLY on provider drift, not on every call"
        )


class TestCompileWorkflowMemoRebuildsOnProviderDrift:
    """FIX 13 — the SAME class of gap as FIX 12, one layer up:
    `Agent.compile_workflow()` (kaizen/core/agents.py) — and the `.workflow`
    property, which used to bypass `compile_workflow()`'s check entirely
    once `_is_compiled` was True — trusted the `_is_compiled`/`_workflow`
    memo regardless of whether the resolved provider had drifted since the
    memo was built. `update_config()`/`set_signature()`/`reset()` already
    invalidated the memo for EXPLICIT config changes; this closes the
    AMBIENT-env-drift path those mutators cannot see. Fixed via the same
    `self._workflow_provider` tracking pattern as FIX 12, and by making
    `.workflow` ALWAYS route through `compile_workflow()` instead of
    returning `self._workflow` directly.
    """

    @staticmethod
    def _llm_agent_node_config(agent, workflow) -> dict:
        return workflow.nodes[agent.agent_id]["config"]

    def test_compile_workflow_rebuilds_when_ambient_provider_drifts(
        self, monkeypatch, _env_serialized
    ):
        agent = Agent(
            "compile_workflow_drift_agent",
            {"model": _resolve_default_model()},  # NO explicit "provider"
        )

        wf1 = agent.compile_workflow()
        node1 = self._llm_agent_node_config(agent, wf1)
        assert node1["provider"] == "mock"

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")

        wf2 = agent.compile_workflow()
        node2 = self._llm_agent_node_config(agent, wf2)
        assert node2["provider"] == "openai", (
            "compile_workflow() MUST rebuild (not return the stale memo) "
            "when the resolved provider drifts due to an ambient env change"
        )
        assert wf1 is not wf2

    def test_workflow_property_rebuilds_when_ambient_provider_drifts(
        self, monkeypatch, _env_serialized
    ):
        """Same scenario through the `.workflow` property specifically —
        it used to short-circuit straight to `self._workflow` once
        `_is_compiled` was True, bypassing any memo check at all."""
        agent = Agent(
            "workflow_property_drift_agent",
            {"model": _resolve_default_model()},
        )

        wf1 = agent.workflow
        node1 = self._llm_agent_node_config(agent, wf1)
        assert node1["provider"] == "mock"

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")

        wf2 = agent.workflow
        node2 = self._llm_agent_node_config(agent, wf2)
        assert node2["provider"] == "openai", (
            "the .workflow property MUST rebuild on provider drift, not "
            "short-circuit to the stale self._workflow"
        )

    def test_compile_workflow_memo_reused_when_provider_stable(self):
        """Perf-benefit check (no regression): repeated calls with a
        STABLE resolved provider reuse the SAME memo object."""
        agent = _make_agent("anthropic")

        wf1 = agent.compile_workflow()
        wf2 = agent.compile_workflow()
        wf3 = agent.workflow

        assert wf1 is wf2 is wf3, (
            "stable-provider case MUST still memoize (no perf regression)"
        )


class TestExecuteWithSignatureCacheRebuildsOnProviderDrift:
    """FIX 15 — a THIRD memoization site with the SAME class of gap as
    FIX 12/13, surfaced by Round 5's mandated FINAL EXHAUSTIVE RE-SWEEP:
    `Agent._execute_with_signature()`'s `self._signature_workflow` cache
    (kaizen/core/agents.py) was guarded by a bare `hasattr(self,
    "_signature_workflow")` check — "was a signature-workflow already
    built", never "is it still valid". `update_config()`/`set_signature()`/
    `reset()` already invalidate it for EXPLICIT config mutations (Round 2
    FIX 1), but an AMBIENT env-provider change (a real key injected into a
    long-lived process, with NO explicit mutator call) left the cache
    trusted forever — not merely a mock-upgrade-gate misclassification
    (PART A's `dispatched_provider` threading already keeps that gate
    honest against whatever's dispatched), but every subsequent
    signature-execution DISPATCH itself never advancing past the provider
    resolved at first build. Fixed via the same `self.
    _signature_workflow_provider` tracking pattern as FIX 12/13.
    """

    def test_execute_with_signature_rebuilds_when_ambient_provider_drifts(
        self, monkeypatch, _env_serialized
    ):
        real_content = "Quarterly revenue increased 8 percent due to expanded partner integrations and reduced customer churn."
        stub = _RecordingKaizenStub("ambient_drift_signature_agent", real_content)
        agent = Agent(
            "ambient_drift_signature_agent",
            {"model": _resolve_default_model()},  # NO explicit "provider"
            signature="question -> answer",
            kaizen_instance=stub,
        )

        # No real keys present (cleared by `_env_serialized`) -> resolves
        # to "mock" and memoizes `_signature_workflow` under "mock".
        result1 = agent.execute(question="What changed?")
        assert stub.dispatched_providers == ["mock"]
        assert result1["answer"] == real_content

        # Inject a real key AFTER the first dispatch — the SAME agent
        # instance, NO explicit update_config()/set_signature()/reset()
        # call — purely an ambient env change.
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake-key")

        result2 = agent.execute(question="What changed?")
        assert stub.dispatched_providers == ["mock", "openai"], (
            "_execute_with_signature() MUST rebuild the stale "
            "_signature_workflow cache (not keep dispatching under the "
            "provider resolved at first build) when the resolved "
            "provider drifts due to an ambient env change"
        )
        assert result2["answer"] == real_content

    def test_execute_with_signature_cache_reused_when_provider_stable(self):
        """Perf-benefit check (no regression): repeated calls with a
        STABLE resolved provider reuse the SAME cached signature-workflow
        object (no rebuild on every call)."""
        real_content = "Quarterly revenue increased 8 percent due to expanded partner integrations and reduced customer churn."
        stub = _RecordingKaizenStub("stable_signature_agent", real_content)
        agent = Agent(
            "stable_signature_agent",
            {"provider": "anthropic", "model": _resolve_default_model()},
            signature="question -> answer",
            kaizen_instance=stub,
        )

        agent.execute(question="q1")
        cached_workflow_after_first = agent._signature_workflow
        agent.execute(question="q2")
        cached_workflow_after_second = agent._signature_workflow

        assert cached_workflow_after_first is cached_workflow_after_second, (
            "stable-provider case MUST still reuse the cached "
            "_signature_workflow (no perf regression)"
        )
        assert stub.dispatched_providers == ["anthropic", "anthropic"]
