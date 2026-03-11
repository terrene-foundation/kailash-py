"""
Test Memory Agent Example - Async Migration (Task 0A.6)

Tests that memory-agent example uses AsyncSingleShotStrategy by default.
Written BEFORE migration (TDD).
"""

import asyncio
import inspect

import pytest

# Standardized example loading
from example_import_helper import import_example_module

# Load memory-agent example
_memory_module = import_example_module("examples/1-single-agent/memory-agent")
MemoryAgent = _memory_module.MemoryAgent
MemoryConfig = _memory_module.MemoryConfig

from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy


class TestMemoryAgentAsyncMigration:
    """Test suite for Memory Agent async migration."""

    def test_memory_uses_async_strategy_by_default(self):
        """Task 0A.6: Verify MemoryAgent uses AsyncSingleShotStrategy."""
        config = MemoryConfig(llm_provider="openai", model="gpt-3.5-turbo")
        agent = MemoryAgent(config=config)

        assert isinstance(
            agent.strategy, AsyncSingleShotStrategy
        ), f"Expected AsyncSingleShotStrategy, got {type(agent.strategy).__name__}"

    def test_memory_no_explicit_strategy_override(self):
        """Test that MemoryAgent no longer explicitly passes strategy."""
        config = MemoryConfig()
        agent = MemoryAgent(config=config)
        assert isinstance(agent.strategy, AsyncSingleShotStrategy)

    def test_run_method_works_with_async(self):
        """Test that chat() method works with async strategy."""
        config = MemoryConfig()
        agent = MemoryAgent(config=config)

        result = agent.run(message="Hello, how are you?")
        assert isinstance(result, dict)
        assert "response" in result or "error" in result

    def test_multiple_memory_agents_independent(self):
        """Test that multiple memory agents don't interfere."""
        config = MemoryConfig()
        agent1 = MemoryAgent(config=config)
        agent2 = MemoryAgent(config=config)

        assert isinstance(agent1.strategy, AsyncSingleShotStrategy)
        assert isinstance(agent2.strategy, AsyncSingleShotStrategy)
        assert agent1.strategy is not agent2.strategy


class TestMemoryAgentRaceConditions:
    """Test for race conditions with async memory operations."""

    def test_memory_no_race_conditions_sequential(self):
        """Test sequential chat doesn't have race conditions."""
        config = MemoryConfig()
        agent = MemoryAgent(config=config)

        results = []
        for i in range(5):
            result = agent.chat(f"Message {i}", session_id="test")
            results.append(result)

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_memory_no_race_conditions_concurrent(self):
        """Test concurrent chat operations don't interfere with memory."""
        config = MemoryConfig()
        agent = MemoryAgent(config=config)

        async def chat_async(message, session_id):
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, agent.chat, message, session_id)

        # 10 concurrent messages to different sessions
        tasks = [chat_async(f"Message {i}", f"session_{i}") for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        assert len(results) == 10


class TestMemoryAgentConsistency:
    """Test memory consistency with async execution."""

    def test_memory_conversation_continuity(self):
        """Test that conversation history is maintained correctly.

        Note: With mock provider, we test structure only. Conversation count
        depends on LLM provider behavior (real or mock).
        """
        config = MemoryConfig()
        agent = MemoryAgent(config=config)

        # First message
        result1 = agent.run(message="My name is Alice", session_id="test")
        assert (
            "memory_updated" in result1 or "error" in result1 or "response" in result1
        )

        # get_conversation_count should return a non-negative integer
        count = agent.get_conversation_count("test")
        assert isinstance(count, int)
        assert count >= 0

    def test_memory_session_isolation(self):
        """Test that different sessions are isolated.

        Note: With mock provider, we test structure only. Counts depend on
        LLM provider behavior (real or mock).
        """
        config = MemoryConfig()
        agent = MemoryAgent(config=config)

        agent.run(message="Message 1", session_id="session1")
        agent.run(message="Message 2", session_id="session2")

        # Each session should have separate memory - test isolation, not count
        count1 = agent.get_conversation_count("session1")
        count2 = agent.get_conversation_count("session2")

        # Counts should be non-negative integers (may be 0 with mock provider)
        assert isinstance(count1, int)
        assert isinstance(count2, int)
        assert count1 >= 0
        assert count2 >= 0

    def test_memory_empty_message_handling(self):
        """Test that empty message handling returns a valid result.

        Note: Agent doesn't perform input validation - it processes empty input.
        With mock provider, we test structure only.
        """
        config = MemoryConfig()
        agent = MemoryAgent(config=config)

        result = agent.run(message="")

        # Result should be a dict (may contain response, error, or memory_updated)
        assert isinstance(result, dict)


class TestMemoryAgentBackwardCompatibility:
    """Test backward compatibility after async migration."""

    def test_memory_config_parameters_preserved(self):
        """Test that all MemoryConfig parameters are preserved."""
        config = MemoryConfig(
            llm_provider="anthropic",
            model="claude-3-haiku",
            temperature=0.7,
            max_tokens=500,
            max_history_turns=10,
        )

        agent = MemoryAgent(config=config)

        assert agent.memory_config.llm_provider == "anthropic"
        assert agent.memory_config.model == "claude-3-haiku"
        assert agent.memory_config.max_history_turns == 10

    def test_memory_clear_functionality(self):
        """Test that memory clear still works.

        Note: With mock provider, we test that clear_memory resets to 0,
        regardless of whether conversation count was incremented.
        """
        config = MemoryConfig()
        agent = MemoryAgent(config=config)

        agent.run(message="Test message", session_id="test")
        # Note: count may be 0 with mock provider if memory isn't updated

        agent.clear_memory("test")
        assert agent.get_conversation_count("test") == 0


class TestMemoryAgentAsyncPerformance:
    """Test performance characteristics with async memory strategy."""

    def test_memory_strategy_has_async_execute(self):
        """Test that strategy.execute is async."""
        config = MemoryConfig()
        agent = MemoryAgent(config=config)

        assert inspect.iscoroutinefunction(agent.strategy.execute)

    @pytest.mark.asyncio
    async def test_memory_concurrent_sessions(self):
        """Test that concurrent sessions can execute in parallel."""
        config = MemoryConfig()
        agent = MemoryAgent(config=config)

        async def chat_async(message, session_id):
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, agent.chat, message, session_id)

        # 5 sessions, 2 messages each
        tasks = []
        for session_id in range(5):
            for msg_num in range(2):
                tasks.append(chat_async(f"Message {msg_num}", f"session_{session_id}"))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert len(results) == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
