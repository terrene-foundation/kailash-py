"""
Test BaseAgent Default Strategy - Task 0A.1

Tests that BaseAgent uses AsyncSingleShotStrategy by default.
Written BEFORE implementation (TDD).
"""

import pytest
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy
from kaizen.strategies.multi_cycle import MultiCycleStrategy
from kaizen.strategies.single_shot import SingleShotStrategy


class TestBaseAgentDefaultStrategy:
    """Test suite for BaseAgent default strategy configuration."""

    def test_default_strategy_is_async_single_shot(self):
        """
        Task 0A.1: Verify BaseAgent uses AsyncSingleShotStrategy by default.

        Expected: When no strategy is provided, BaseAgent should use AsyncSingleShotStrategy.
        """
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        agent = BaseAgent(config=config)

        # CRITICAL: Default strategy must be AsyncSingleShotStrategy
        assert isinstance(
            agent.strategy, AsyncSingleShotStrategy
        ), f"Expected AsyncSingleShotStrategy, got {type(agent.strategy).__name__}"

    def test_default_strategy_without_strategy_type(self):
        """
        Test that default strategy is async when strategy_type not specified.
        """
        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4",
            # strategy_type not specified
        )

        agent = BaseAgent(config=config)

        assert isinstance(agent.strategy, AsyncSingleShotStrategy)

    def test_explicit_async_strategy_override(self):
        """
        Test that explicitly providing AsyncSingleShotStrategy works.
        """
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        explicit_strategy = AsyncSingleShotStrategy()
        agent = BaseAgent(config=config, strategy=explicit_strategy)

        assert agent.strategy is explicit_strategy
        assert isinstance(agent.strategy, AsyncSingleShotStrategy)

    def test_can_override_with_sync_strategy(self):
        """
        Test that users can still explicitly use sync strategy if needed.
        """
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        sync_strategy = SingleShotStrategy()
        agent = BaseAgent(config=config, strategy=sync_strategy)

        assert agent.strategy is sync_strategy
        assert isinstance(agent.strategy, SingleShotStrategy)
        assert not isinstance(agent.strategy, AsyncSingleShotStrategy)

    def test_can_override_with_multi_cycle_strategy(self):
        """
        Test that users can still use MultiCycleStrategy.
        """
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        multi_cycle_strategy = MultiCycleStrategy(max_cycles=10)
        agent = BaseAgent(config=config, strategy=multi_cycle_strategy)

        assert agent.strategy is multi_cycle_strategy
        assert isinstance(agent.strategy, MultiCycleStrategy)

    def test_strategy_type_single_shot_uses_async(self):
        """
        Test that strategy_type='single_shot' uses AsyncSingleShotStrategy.

        BREAKING CHANGE: Previously used sync, now uses async by default.
        """
        config = BaseAgentConfig(
            llm_provider="openai", model="gpt-4", strategy_type="single_shot"
        )

        agent = BaseAgent(config=config)

        # Should use async version even with strategy_type="single_shot"
        assert isinstance(agent.strategy, AsyncSingleShotStrategy)

    def test_strategy_type_multi_cycle_still_works(self):
        """
        Test that strategy_type='multi_cycle' still creates MultiCycleStrategy.
        """
        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4",
            strategy_type="multi_cycle",
            max_cycles=5,
        )

        agent = BaseAgent(config=config)

        assert isinstance(agent.strategy, MultiCycleStrategy)

    def test_multiple_agents_have_independent_strategies(self):
        """
        Test that multiple agents each get their own strategy instance.
        """
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        agent1 = BaseAgent(config=config)
        agent2 = BaseAgent(config=config)

        # Each agent should have its own strategy instance
        assert isinstance(agent1.strategy, AsyncSingleShotStrategy)
        assert isinstance(agent2.strategy, AsyncSingleShotStrategy)
        assert agent1.strategy is not agent2.strategy

    def test_strategy_has_execute_method(self):
        """
        Test that default strategy has the required execute method.
        """
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        agent = BaseAgent(config=config)

        assert hasattr(agent.strategy, "execute")
        assert callable(agent.strategy.execute)


class TestAsyncStrategyBackwardCompatibility:
    """Test backward compatibility after async migration."""

    def test_existing_code_without_strategy_param_uses_async(self):
        """
        Test that existing code (no strategy param) automatically uses async.

        This is a BREAKING CHANGE but improves performance.
        """
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        # Old code: BaseAgent(config=config)
        agent = BaseAgent(config=config)

        # Now uses async by default
        assert isinstance(agent.strategy, AsyncSingleShotStrategy)

    def test_old_sync_code_can_be_updated(self):
        """
        Test migration path: old sync code → async code.
        """
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        # OLD: agent = BaseAgent(config=config, strategy=SingleShotStrategy())
        # NEW: agent = BaseAgent(config=config)  # Uses async by default
        agent = BaseAgent(config=config)

        assert isinstance(agent.strategy, AsyncSingleShotStrategy)


class TestAsyncStrategyProperties:
    """Test properties specific to AsyncSingleShotStrategy."""

    def test_async_strategy_has_async_execute(self):
        """
        Test that AsyncSingleShotStrategy.execute is async.
        """
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        agent = BaseAgent(config=config)

        # AsyncSingleShotStrategy.execute should be an async method
        import inspect

        assert inspect.iscoroutinefunction(
            agent.strategy.execute
        ), "AsyncSingleShotStrategy.execute must be async"

    def test_async_strategy_builds_workflow(self):
        """
        Test that async strategy can build workflows.
        """
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

        agent = BaseAgent(config=config)

        assert hasattr(agent.strategy, "build_workflow")
        assert callable(agent.strategy.build_workflow)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
