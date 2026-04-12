"""Tests that deprecated strategy extension points emit DeprecationWarning.

Each of the four extension points (pre_execute / post_execute on both
SingleShotStrategy and AsyncSingleShotStrategy) was decorated with
@deprecated in v2.5.0.  These tests confirm the warning is emitted on
every call and carries the expected message.
"""

import warnings

import pytest

from kaizen.strategies.single_shot import SingleShotStrategy
from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy


EXPECTED_MESSAGE = (
    "Deprecated since v2.5.0: Use composition wrappers "
    "(MonitoredAgent, GovernedAgent, StreamingAgent) instead."
)


class TestSingleShotStrategyDeprecation:
    """SingleShotStrategy.pre_execute and .post_execute emit DeprecationWarning."""

    def test_pre_execute_emits_deprecation_warning(self):
        strategy = SingleShotStrategy()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = strategy.pre_execute({"key": "value"})
        assert result == {"key": "value"}
        deprecation_warnings = [
            w for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) == 1
        assert EXPECTED_MESSAGE in str(deprecation_warnings[0].message)

    def test_post_execute_emits_deprecation_warning(self):
        strategy = SingleShotStrategy()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = strategy.post_execute({"answer": "42"})
        assert result == {"answer": "42"}
        deprecation_warnings = [
            w for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) == 1
        assert EXPECTED_MESSAGE in str(deprecation_warnings[0].message)

    def test_pre_execute_has_deprecated_marker(self):
        strategy = SingleShotStrategy()
        assert getattr(strategy.pre_execute, "_deprecated", False) is True

    def test_post_execute_has_deprecated_marker(self):
        strategy = SingleShotStrategy()
        assert getattr(strategy.post_execute, "_deprecated", False) is True


class TestAsyncSingleShotStrategyDeprecation:
    """AsyncSingleShotStrategy.pre_execute and .post_execute emit DeprecationWarning."""

    def test_pre_execute_emits_deprecation_warning(self):
        strategy = AsyncSingleShotStrategy()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = strategy.pre_execute({"key": "value"})
        assert result == {"key": "value"}
        deprecation_warnings = [
            w for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) == 1
        assert EXPECTED_MESSAGE in str(deprecation_warnings[0].message)

    def test_post_execute_emits_deprecation_warning(self):
        strategy = AsyncSingleShotStrategy()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = strategy.post_execute({"answer": "42"})
        assert result == {"answer": "42"}
        deprecation_warnings = [
            w for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) == 1
        assert EXPECTED_MESSAGE in str(deprecation_warnings[0].message)

    def test_pre_execute_has_deprecated_marker(self):
        strategy = AsyncSingleShotStrategy()
        assert getattr(strategy.pre_execute, "_deprecated", False) is True

    def test_post_execute_has_deprecated_marker(self):
        strategy = AsyncSingleShotStrategy()
        assert getattr(strategy.post_execute, "_deprecated", False) is True
