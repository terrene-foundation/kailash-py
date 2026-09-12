"""Regression tests for issue #2212.

``AsyncSingleShotStrategy`` decorated ``pre_execute`` / ``post_execute`` as
deprecated in 2.5.0 and then called both itself from ``execute()`` — the default
path for every single-shot agent. Each ``agent.run()`` therefore emitted two
DeprecationWarnings that no downstream change could avoid.

The fix keeps the deprecation (it is a landed, intentional public-API decision)
and moves the framework's own calls onto an internal hop that dispatches to the
public method ONLY when a caller has actually overridden it. So:

* default path  -> no warning, and the no-op default is skipped;
* overridden    -> the override STILL RUNS (silently dropping it would be a
  behaviour regression), and the deprecation warning fires, because at that
  point the deprecated extension point genuinely is in use;
* direct call   -> unchanged, still warns.
"""

import warnings
from typing import Any, Dict

import pytest

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import InputField, OutputField, Signature
from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy
from kaizen.strategies.single_shot import SingleShotStrategy


class _QASignature(Signature):
    """Minimal signature for the mock-provider round trip."""

    question: str = InputField(description="A question")
    answer: str = OutputField(description="The answer")


def _mock_agent(strategy=None) -> BaseAgent:
    """BaseAgent on the mock provider — no network call is made."""
    return BaseAgent(
        config=BaseAgentConfig(llm_provider="mock", model="mock-model"),
        signature=_QASignature(),
        strategy=strategy,
    )


def _deprecations(caught) -> list:
    return [w for w in caught if issubclass(w.category, DeprecationWarning)]


@pytest.mark.unit
class TestDefaultPathIsWarningFree:
    """#2212: the default single-shot path must not warn about its own internals."""

    def test_agent_run_emits_no_deprecation_warning(self):
        agent = _mock_agent()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            agent.run(question="What is 2+2?")

        offending = [
            f"{w.filename.rsplit('/', 1)[-1]}:{w.lineno}: {w.message}"
            for w in _deprecations(caught)
        ]
        assert offending == [], (
            "agent.run() on the default AsyncSingleShotStrategy emitted "
            f"DeprecationWarning(s) the caller cannot avoid: {offending}"
        )

    def test_default_strategy_is_async_single_shot(self):
        # Pins the premise of the test above: this IS the default path.
        assert isinstance(_mock_agent().strategy, AsyncSingleShotStrategy)


@pytest.mark.unit
class TestOverridesStillTakeEffect:
    """Routing around the public method MUST NOT drop a caller's override."""

    def test_subclass_overrides_are_invoked_during_run(self):
        calls = []

        class CustomStrategy(AsyncSingleShotStrategy):
            def pre_execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
                calls.append("pre")
                inputs = dict(inputs)
                inputs["preprocessed"] = True
                return inputs

            def post_execute(self, result: Dict[str, Any]) -> Dict[str, Any]:
                calls.append("post")
                result = dict(result)
                result["post_processed"] = True
                return result

        agent = _mock_agent(strategy=CustomStrategy())
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            agent.run(question="What is 2+2?")

        assert calls == ["pre", "post"], (
            "subclass overrides of the deprecated extension points must still "
            f"be called by execute(); observed: {calls}"
        )
        # Using a deprecated extension point SHOULD warn — that is the opt-in half.
        assert len(_deprecations(caught)) == 2

    def test_instance_level_override_is_invoked(self):
        calls = []
        strategy = AsyncSingleShotStrategy()
        strategy.pre_execute = lambda inputs: (calls.append("pre") or inputs)

        agent = _mock_agent(strategy=strategy)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            agent.run(question="What is 2+2?")

        assert calls == ["pre"]

    def test_sync_strategy_overrides_are_invoked(self):
        """Same contract on the sync sibling, which carries the same defect."""
        calls = []

        class CustomSyncStrategy(SingleShotStrategy):
            def pre_execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
                calls.append("pre")
                return inputs

            def post_execute(self, result: Dict[str, Any]) -> Dict[str, Any]:
                calls.append("post")
                return result

        agent = _mock_agent(strategy=CustomSyncStrategy())
        agent.run(question="What is 2+2?")

        assert calls == ["pre", "post"]

    def test_sync_default_path_emits_no_deprecation_warning(self):
        agent = _mock_agent(strategy=SingleShotStrategy())
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            agent.run(question="What is 2+2?")

        assert _deprecations(caught) == []


@pytest.mark.unit
class TestDeprecationSurfaceUnchanged:
    """The deprecation itself stands; only the framework's own calls moved."""

    @pytest.mark.parametrize(
        "strategy_cls", [AsyncSingleShotStrategy, SingleShotStrategy]
    )
    def test_direct_call_still_warns(self, strategy_cls):
        strategy = strategy_cls()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert strategy.pre_execute({"k": "v"}) == {"k": "v"}
            assert strategy.post_execute({"k": "v"}) == {"k": "v"}
        assert len(_deprecations(caught)) == 2

    @pytest.mark.parametrize(
        "strategy_cls", [AsyncSingleShotStrategy, SingleShotStrategy]
    )
    def test_message_names_the_class_that_actually_exists(self, strategy_cls):
        """The advised replacement is L3GovernedAgent; no GovernedAgent exists."""
        message = strategy_cls.pre_execute._deprecated_message
        assert "L3GovernedAgent" in message
        assert "MonitoredAgent, GovernedAgent" not in message
