"""
Unit tests for FallbackStrategy.

Tests cover:
- First strategy succeeds (returns immediately)
- First fails, second succeeds
- First two fail, third succeeds
- All strategies fail (raises RuntimeError)
- Tracks errors from failed strategies
- 2 strategies, 3 strategies, 5 strategies
- Empty strategies list raises ValueError
- Error message includes all failures
- Metadata added to successful result
- get_error_summary returns correct format
"""

import pytest
from kaizen.strategies.fallback import FallbackStrategy


class MockAgent:
    """Mock agent for testing."""

    async def execute(self, inputs):
        """Mock execution."""
        return {"response": "success"}


class SuccessStrategy:
    """Strategy that always succeeds."""

    async def execute(self, agent, inputs):
        """Always succeed."""
        return {"response": "success from SuccessStrategy"}


class FailStrategy:
    """Strategy that always fails."""

    def __init__(self, error_message="Strategy failed"):
        self.error_message = error_message

    async def execute(self, agent, inputs):
        """Always fail."""
        raise RuntimeError(self.error_message)


class CountingStrategy:
    """Strategy that counts executions."""

    execution_count = 0

    async def execute(self, agent, inputs):
        """Count executions."""
        CountingStrategy.execution_count += 1
        return {"response": f"execution {CountingStrategy.execution_count}"}


@pytest.mark.asyncio
async def test_first_strategy_succeeds():
    """Test that first strategy succeeds and returns immediately."""
    strategies = [SuccessStrategy(), FailStrategy()]
    fallback = FallbackStrategy(strategies)
    agent = MockAgent()

    result = await fallback.execute(agent, {"prompt": "test"})

    assert result["response"] == "success from SuccessStrategy"
    assert result["_fallback_strategy_used"] == 0
    assert result["_fallback_attempts"] == 1
    assert len(fallback.last_errors) == 0  # No errors


@pytest.mark.asyncio
async def test_first_fails_second_succeeds():
    """Test first fails, second succeeds."""
    strategies = [FailStrategy("first failed"), SuccessStrategy()]
    fallback = FallbackStrategy(strategies)
    agent = MockAgent()

    result = await fallback.execute(agent, {"prompt": "test"})

    assert result["response"] == "success from SuccessStrategy"
    assert result["_fallback_strategy_used"] == 1
    assert result["_fallback_attempts"] == 2
    assert len(fallback.last_errors) == 1  # One error from first strategy


@pytest.mark.asyncio
async def test_first_two_fail_third_succeeds():
    """Test first two fail, third succeeds."""
    strategies = [
        FailStrategy("first failed"),
        FailStrategy("second failed"),
        SuccessStrategy(),
    ]
    fallback = FallbackStrategy(strategies)
    agent = MockAgent()

    result = await fallback.execute(agent, {"prompt": "test"})

    assert result["response"] == "success from SuccessStrategy"
    assert result["_fallback_strategy_used"] == 2
    assert result["_fallback_attempts"] == 3
    assert len(fallback.last_errors) == 2  # Two errors from first two strategies


@pytest.mark.asyncio
async def test_all_strategies_fail():
    """Test all strategies fail (raises RuntimeError)."""
    strategies = [
        FailStrategy("first failed"),
        FailStrategy("second failed"),
        FailStrategy("third failed"),
    ]
    fallback = FallbackStrategy(strategies)
    agent = MockAgent()

    with pytest.raises(RuntimeError) as exc_info:
        await fallback.execute(agent, {"prompt": "test"})

    error_message = str(exc_info.value)
    assert "All 3 strategies failed" in error_message
    assert "first failed" in error_message
    assert "second failed" in error_message
    assert "third failed" in error_message
    assert len(fallback.last_errors) == 3


@pytest.mark.asyncio
async def test_tracks_errors_from_failed_strategies():
    """Test that errors from failed strategies are tracked."""
    strategies = [FailStrategy("error 1"), FailStrategy("error 2"), SuccessStrategy()]
    fallback = FallbackStrategy(strategies)
    agent = MockAgent()

    await fallback.execute(agent, {"prompt": "test"})

    assert len(fallback.last_errors) == 2
    assert str(fallback.last_errors[0][1]) == "error 1"
    assert str(fallback.last_errors[1][1]) == "error 2"


@pytest.mark.asyncio
async def test_2_strategies():
    """Test with 2 strategies."""
    strategies = [FailStrategy(), SuccessStrategy()]
    fallback = FallbackStrategy(strategies)
    agent = MockAgent()

    result = await fallback.execute(agent, {"prompt": "test"})

    assert result["_fallback_strategy_used"] == 1
    assert result["_fallback_attempts"] == 2


@pytest.mark.asyncio
async def test_3_strategies():
    """Test with 3 strategies."""
    strategies = [FailStrategy(), FailStrategy(), SuccessStrategy()]
    fallback = FallbackStrategy(strategies)
    agent = MockAgent()

    result = await fallback.execute(agent, {"prompt": "test"})

    assert result["_fallback_strategy_used"] == 2
    assert result["_fallback_attempts"] == 3


@pytest.mark.asyncio
async def test_5_strategies():
    """Test with 5 strategies."""
    strategies = [
        FailStrategy(),
        FailStrategy(),
        FailStrategy(),
        FailStrategy(),
        SuccessStrategy(),
    ]
    fallback = FallbackStrategy(strategies)
    agent = MockAgent()

    result = await fallback.execute(agent, {"prompt": "test"})

    assert result["_fallback_strategy_used"] == 4
    assert result["_fallback_attempts"] == 5


def test_empty_strategies_list_raises_value_error():
    """Test that empty strategies list raises ValueError."""
    with pytest.raises(ValueError) as exc_info:
        FallbackStrategy([])

    assert "requires at least one strategy" in str(exc_info.value)


@pytest.mark.asyncio
async def test_error_message_includes_all_failures():
    """Test that error message includes all failures."""
    strategies = [
        FailStrategy("Connection timeout"),
        FailStrategy("Authentication failed"),
        FailStrategy("Rate limit exceeded"),
    ]
    fallback = FallbackStrategy(strategies)
    agent = MockAgent()

    with pytest.raises(RuntimeError) as exc_info:
        await fallback.execute(agent, {"prompt": "test"})

    error_message = str(exc_info.value)
    assert "Connection timeout" in error_message
    assert "Authentication failed" in error_message
    assert "Rate limit exceeded" in error_message
    assert "FailStrategy" in error_message  # Strategy names


@pytest.mark.asyncio
async def test_metadata_added_to_successful_result():
    """Test that metadata is added to successful result."""
    strategies = [FailStrategy(), SuccessStrategy()]
    fallback = FallbackStrategy(strategies)
    agent = MockAgent()

    result = await fallback.execute(agent, {"prompt": "test"})

    assert "_fallback_strategy_used" in result
    assert "_fallback_attempts" in result
    assert isinstance(result["_fallback_strategy_used"], int)
    assert isinstance(result["_fallback_attempts"], int)


@pytest.mark.asyncio
async def test_get_error_summary_returns_correct_format():
    """Test that get_error_summary returns correct format."""
    strategies = [FailStrategy("error 1"), FailStrategy("error 2"), SuccessStrategy()]
    fallback = FallbackStrategy(strategies)
    agent = MockAgent()

    await fallback.execute(agent, {"prompt": "test"})

    summary = fallback.get_error_summary()

    assert len(summary) == 2
    assert summary[0]["strategy"] == "FailStrategy"
    assert summary[0]["error"] == "error 1"
    assert summary[0]["error_type"] == "RuntimeError"
    assert summary[1]["strategy"] == "FailStrategy"
    assert summary[1]["error"] == "error 2"
    assert summary[1]["error_type"] == "RuntimeError"


@pytest.mark.asyncio
async def test_error_summary_empty_on_first_success():
    """Test that error summary is empty when first strategy succeeds."""
    strategies = [SuccessStrategy(), FailStrategy()]
    fallback = FallbackStrategy(strategies)
    agent = MockAgent()

    await fallback.execute(agent, {"prompt": "test"})

    summary = fallback.get_error_summary()
    assert len(summary) == 0


@pytest.mark.asyncio
async def test_stops_after_first_success():
    """Test that fallback stops trying strategies after first success."""
    # Reset counter
    CountingStrategy.execution_count = 0

    strategies = [
        FailStrategy(),
        CountingStrategy(),
        CountingStrategy(),
        CountingStrategy(),
    ]
    fallback = FallbackStrategy(strategies)
    agent = MockAgent()

    result = await fallback.execute(agent, {"prompt": "test"})

    # Should only execute second strategy (first CountingStrategy)
    assert CountingStrategy.execution_count == 1
    assert result["response"] == "execution 1"
