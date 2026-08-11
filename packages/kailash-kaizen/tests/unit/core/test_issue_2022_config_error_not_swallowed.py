"""Regression: a configuration failure must not be reported as a model failure (#2022).

The user-visible defect in #2022 is NOT the missing ``llm_provider`` kwarg —
that is only what triggers it. The defect is the SWALLOW.

``AgentLoop`` wraps the whole run in ``except Exception as error: return
agent._handle_error(error, {"inputs": inputs})``, and ``_handle_error`` folded
EVERY exception into ``{"error": ..., "success": False}``. So when
``LLMAgentNode`` correctly and loudly raised ``ConfigurationError`` ("provider
is unresolved"), the caller received an EMPTY result instead. Downstream
validation then rejected that empty result as a malformed model response, and
the user was told *"the LLM emitted a plan that does not conform to MLPlan"*
when in truth their provider had never been wired — with the stack trace that
would have said so already discarded.

That is the ``rules/zero-tolerance.md`` Rule 3 silent-error-hiding shape, and
it mis-attributes EVERY provider and credential failure, not just this one.

Both halves are pinned here:
  * the swallow — configuration-class errors propagate; ordinary run-time
    errors still return the historical envelope (NEGATIVE control);
  * the resolution — ``resolve_agent_provider`` answers "which provider serves
    this model?" through the canonical public resolvers.

Model literals below are deliberate and are NOT a ``rules/env-models.md``
violation: these tests assert the model-PREFIX -> provider mapping itself, so
the prefix under test IS the fixture. Reading the model from ``.env`` would
make the assertion depend on whichever model the operator happens to have
configured — a non-discriminating instrument. No live call is made; nothing
here selects a deployment model.
"""

from __future__ import annotations

import pytest

from kaizen.config.providers import ConfigurationError
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

KEYLESS_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "DEEPSEEK_API_KEY",
    "KAIZEN_ALLOW_KEYLESS_MOCK",
)


@pytest.fixture
def keyless(monkeypatch):
    """A genuinely keyless environment — no provider resolvable from env."""
    for var in KEYLESS_VARS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


class TestHandleErrorDoesNotSwallowConfigurationErrors:
    """The unit-level contract on the disposition itself."""

    def test_configuration_error_propagates(self):
        agent = BaseAgent(config=BaseAgentConfig(llm_provider="mock"))
        with pytest.raises(ConfigurationError):
            agent._handle_error(
                ConfigurationError("LLMAgentNode: 'provider' is unresolved (None)"),
                {"inputs": {}},
            )

    def test_configuration_error_propagates_even_when_handling_enabled(self):
        """error_handling_enabled governs run-time resilience, not broken setup."""
        agent = BaseAgent(
            config=BaseAgentConfig(llm_provider="mock", error_handling_enabled=True)
        )
        with pytest.raises(ConfigurationError):
            agent._handle_error(ConfigurationError("unresolved"), {"inputs": {}})

    def test_ordinary_runtime_error_still_returns_envelope(self):
        """NEGATIVE CONTROL — this must NOT become a blanket re-raise."""
        agent = BaseAgent(config=BaseAgentConfig(llm_provider="mock"))
        out = agent._handle_error(
            RuntimeError("model returned garbage"), {"inputs": {}}
        )
        assert out["success"] is False
        assert out["type"] == "RuntimeError"

    def test_original_exception_object_is_preserved(self):
        """The cause must survive — that is the whole point of not swallowing."""
        agent = BaseAgent(config=BaseAgentConfig(llm_provider="mock"))
        original = ConfigurationError("provider unresolved")
        with pytest.raises(ConfigurationError) as caught:
            agent._handle_error(original, {"inputs": {}})
        assert caught.value is original


class TestUnresolvedProviderSurfacesThroughRun:
    """End-to-end through the REAL strategy + AgentLoop swallow sites.

    Parametrized over EVERY strategy type. The first fix landed the re-raise in
    AsyncSingleShotStrategy only; MultiCycleStrategy still converted the
    ConfigurationError into a returned dict, and because it RETURNS rather than
    raises, ``_handle_error`` never ran and could not backstop it. Enforcement
    -surface parity: one predicate, every surface that swallows.
    """

    @pytest.mark.parametrize("strategy_type", ["single_shot", "multi_cycle"])
    def test_run_raises_configuration_error_not_empty_result(
        self, keyless, strategy_type
    ):
        agent = BaseAgent(
            config=BaseAgentConfig(model="gpt-4o-mini", strategy_type=strategy_type)
        )
        with pytest.raises(ConfigurationError):
            agent.run(input="hello")

    def test_sync_single_shot_strategy_also_reraises(self, keyless):
        """SingleShotStrategy is public API — a caller may pass it directly."""
        from kaizen.strategies.single_shot import SingleShotStrategy

        agent = BaseAgent(
            config=BaseAgentConfig(model="gpt-4o-mini"),
            strategy=SingleShotStrategy(),
        )
        with pytest.raises(ConfigurationError):
            agent.run(input="hello")


class TestResolveAgentProvider:
    """The public provider-resolution surface (#2022 acceptance criterion 3)."""

    def test_model_keyed_wins_over_environment(self, keyless):
        """A Claude model dispatches to anthropic even with an OpenAI key set.

        This closes an env/model MISMATCH class: the env-keyed fallback alone
        sent a Claude model to openai whenever OPENAI_API_KEY happened to be
        set.
        """
        from kaizen.core import resolve_agent_provider

        keyless.setenv("OPENAI_API_KEY", "sk-test-not-used")
        assert resolve_agent_provider("claude-sonnet-4") == "anthropic"

    @pytest.mark.parametrize(
        "model,expected",
        [
            ("gpt-4o-mini", "openai"),
            ("claude-3-5-haiku", "anthropic"),
            ("gemini-2.0-flash", "google"),
            ("deepseek-chat", "deepseek"),
        ],
    )
    def test_registered_prefixes_resolve_without_any_credential(
        self, keyless, model, expected
    ):
        from kaizen.core import resolve_agent_provider

        assert resolve_agent_provider(model) == expected

    def test_unregistered_model_falls_back_to_environment(self, keyless):
        """Preserves today's behaviour for models outside the prefix registry."""
        from kaizen.core import resolve_agent_provider

        keyless.setenv("OPENAI_API_KEY", "sk-test-not-used")
        assert resolve_agent_provider("chatgpt-4o-latest") == "openai"

    def test_unresolvable_raises_actionable_configuration_error(self, keyless):
        """Fail LOUD and name the fix — never return None into the node gate."""
        from kaizen.core import resolve_agent_provider

        with pytest.raises(ConfigurationError) as caught:
            resolve_agent_provider("some-unknown-local-model", component="unit-test")

        message = str(caught.value)
        assert "some-unknown-local-model" in message
        assert "llm_provider" in message, "error must name the kwarg that fixes it"
        assert "unit-test" in message, "error must name the calling component"

    def test_missing_model_raises_rather_than_guessing(self, keyless):
        from kaizen.core import resolve_agent_provider

        with pytest.raises(ConfigurationError):
            resolve_agent_provider(None)


class TestFrameworkExecutePath:
    """`Kaizen.execute` is a SIXTH swallow site, on the `Agent` path.

    The strategies were guarded first, but `core/framework.py::Kaizen.execute`
    wraps `LocalRuntime` too, and eight `self.kaizen.execute(...)` call sites in
    `core/agents.py` route through it — including `:383`, an agent execution
    path. Without the guard a ConfigurationError arriving there is returned as a
    result dict, which is the #2022 symptom on a path the strategy fixes do not
    cover.
    """

    def test_execute_raises_rather_than_returning_failed_node(self, keyless):
        from kailash.workflow.builder import WorkflowBuilder
        from kaizen.core.framework import Kaizen

        workflow = WorkflowBuilder()
        workflow.add_node(
            "LLMAgentNode",
            "agent_exec",
            {"provider": None, "model": "gpt-4o-mini", "system_prompt": "hi"},
        )

        with pytest.raises(ConfigurationError):
            Kaizen().execute(
                workflow.build(),
                {"agent_exec": {"messages": [{"role": "user", "content": "hi"}]}},
            )

    def test_successful_execute_still_returns_results_and_run_id(self):
        """NEGATIVE CONTROL — the guard must not disturb the return contract."""
        from kailash.workflow.builder import WorkflowBuilder
        from kaizen.core.framework import Kaizen

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "ok", {"code": "result = {'value': 1}"})

        results, run_id = Kaizen().execute(workflow.build(), {})
        assert isinstance(results, dict)
        assert run_id is not None


class TestCrossPackageCallSite:
    """A REAL consumer of the resolver, exercised where CI installs both packages.

    The kaizen CI job installs ``kailash-dataflow`` (it does NOT install
    kailash-ml), so ``DataFlow.from_brief`` is the call site that can actually
    be driven here. It reaches provider resolution before any database work, so
    this needs no infrastructure and no live LLM.

    This is what makes #2022's acceptance criterion 4 real: the regression is
    caught by a job that RUNS, rather than by a test that skips without a model
    env var — which is precisely why the defect shipped.
    """

    def test_dataflow_from_brief_raises_actionable_configuration_error(self, keyless):
        dataflow = pytest.importorskip(
            "dataflow",
            reason="kailash-dataflow not installed in this environment",
        )

        with pytest.raises(ConfigurationError) as caught:
            dataflow.DataFlow.from_brief(
                "users have email and name",
                llm_model="some-unregistered-local-model",
            )

        message = str(caught.value)
        assert "dataflow.from_brief" in message, "must name the calling component"
        assert "llm_provider" in message, "must name the kwarg that fixes it"
