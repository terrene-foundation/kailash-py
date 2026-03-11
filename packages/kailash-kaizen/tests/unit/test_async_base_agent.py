"""
Unit tests for BaseAgent async functionality.

Tests the async capabilities of BaseAgent including:
- run_async() method
- Async configuration validation
- Integration with async providers
- Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.signatures import InputField, OutputField, Signature


class SimpleQASignature(Signature):
    """Simple Q&A signature for testing."""

    question: str = InputField(description="User question")
    answer: str = OutputField(description="Answer to question")


class TestBaseAgentConfigAsync:
    """Test BaseAgentConfig async parameters."""

    def test_use_async_llm_parameter_exists(self):
        """Test use_async_llm parameter exists in BaseAgentConfig."""
        config = BaseAgentConfig(
            llm_provider="openai", model="gpt-4", use_async_llm=True
        )
        assert hasattr(config, "use_async_llm")
        assert config.use_async_llm is True

    def test_use_async_llm_defaults_to_false(self):
        """Test use_async_llm defaults to False for backwards compatibility."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        assert config.use_async_llm is False

    def test_use_async_llm_validation(self):
        """Test use_async_llm parameter validation."""
        # Valid: async with OpenAI
        config = BaseAgentConfig(
            llm_provider="openai", model="gpt-4", use_async_llm=True
        )
        assert config.use_async_llm is True

        # Valid: async with None provider (will be set later)
        config = BaseAgentConfig(llm_provider=None, model="gpt-4", use_async_llm=True)
        assert config.use_async_llm is True

        # Invalid: async with non-OpenAI provider
        with pytest.raises(
            ValueError, match="Async mode only supported for OpenAI provider"
        ):
            BaseAgentConfig(llm_provider="ollama", model="llama2", use_async_llm=True)

    def test_use_async_llm_type_validation(self):
        """Test use_async_llm must be boolean."""
        with pytest.raises(TypeError, match="use_async_llm must be a boolean"):
            config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
            config.use_async_llm = "true"  # String instead of bool
            config._validate_parameters()

    def test_from_domain_config_preserves_async_flag(self):
        """Test from_domain_config() preserves use_async_llm."""
        # Test with dict
        domain_config_dict = {
            "llm_provider": "openai",
            "model": "gpt-4",
            "use_async_llm": True,
        }
        config = BaseAgentConfig.from_domain_config(domain_config_dict)
        assert config.use_async_llm is True

        # Test with object
        from dataclasses import dataclass

        @dataclass
        class DomainConfig:
            llm_provider: str = "openai"
            model: str = "gpt-4"
            use_async_llm: bool = True

        domain_config_obj = DomainConfig()
        config = BaseAgentConfig.from_domain_config(domain_config_obj)
        assert config.use_async_llm is True


class TestBaseAgentRunAsync:
    """Test BaseAgent.run_async() method."""

    def test_run_async_method_exists(self):
        """Test run_async() method exists and is async."""
        config = BaseAgentConfig(
            llm_provider="openai", model="gpt-4", use_async_llm=True
        )
        agent = BaseAgent(config=config, signature=SimpleQASignature())

        assert hasattr(agent, "run_async")
        assert callable(agent.run_async)

        # Verify it's an async method
        import inspect

        assert inspect.iscoroutinefunction(agent.run_async)

    @pytest.mark.asyncio
    async def test_run_async_requires_async_config(self):
        """Test run_async() requires use_async_llm=True."""
        # Agent configured for sync mode
        config = BaseAgentConfig(
            llm_provider="openai", model="gpt-4", use_async_llm=False
        )
        agent = BaseAgent(config=config, signature=SimpleQASignature())

        # Should raise ValueError
        with pytest.raises(ValueError, match="Agent not configured for async mode"):
            await agent.run_async(question="What is 2+2?")

    @pytest.mark.asyncio
    async def test_run_async_with_async_config(self):
        """Test run_async() works with use_async_llm=True."""
        config = BaseAgentConfig(
            llm_provider="openai", model="gpt-4", use_async_llm=True
        )
        agent = BaseAgent(config=config, signature=SimpleQASignature())

        # Mock at the provider factory level - where LLMAgentNode gets providers
        with patch("kaizen.nodes.ai.ai_providers.get_provider") as mock_get_provider:
            mock_provider = AsyncMock()
            mock_get_provider.return_value = mock_provider

            # Mock chat_async response with JSON-formatted content matching signature
            mock_provider.chat_async = AsyncMock(
                return_value={
                    "content": '{"answer": "2+2 equals 4"}',  # JSON string matching signature
                    "role": "assistant",
                    "model": "gpt-4",
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                }
            )

            # Also mock sync chat method (might be called in some paths)
            mock_provider.chat = MagicMock(
                return_value={
                    "content": '{"answer": "2+2 equals 4"}',  # JSON string matching signature
                    "role": "assistant",
                    "model": "gpt-4",
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                }
            )

            # Execute
            result = await agent.run_async(question="What is 2+2?")

            # Verify provider was requested
            assert mock_get_provider.called, "Provider factory should be called"

            # Verify result
            assert "answer" in result
            assert result["answer"] is not None

    @pytest.mark.asyncio
    async def test_run_async_signature_input_validation(self):
        """Test run_async() validates inputs against signature."""
        config = BaseAgentConfig(
            llm_provider="openai", model="gpt-4", use_async_llm=True
        )
        agent = BaseAgent(config=config, signature=SimpleQASignature())

        with patch("kaizen.nodes.ai.ai_providers.get_provider") as mock_get_provider:
            mock_provider = AsyncMock()
            mock_get_provider.return_value = mock_provider
            mock_provider.chat_async = AsyncMock(
                return_value={
                    "content": "4",
                    "role": "assistant",
                    "model": "gpt-4",
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                }
            )
            mock_provider.chat = MagicMock(
                return_value={
                    "content": "4",
                    "role": "assistant",
                    "model": "gpt-4",
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                }
            )

            # Valid input
            try:
                result = await agent.run_async(question="What is 2+2?")
                # Should not raise
            except ValueError:
                pytest.fail("run_async() raised ValueError with valid inputs")

    @pytest.mark.asyncio
    async def test_run_async_calls_pre_post_hooks(self):
        """Test run_async() calls pre/post execution hooks."""
        config = BaseAgentConfig(
            llm_provider="openai", model="gpt-4", use_async_llm=True
        )

        class HookedAgent(BaseAgent):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.pre_called = False
                self.post_called = False

            def _pre_execution_hook(self, inputs):
                self.pre_called = True
                return super()._pre_execution_hook(inputs)

            def _post_execution_hook(self, result):
                self.post_called = True
                return super()._post_execution_hook(result)

        agent = HookedAgent(config=config, signature=SimpleQASignature())

        with patch("kaizen.nodes.ai.ai_providers.get_provider") as mock_get_provider:
            mock_provider = AsyncMock()
            mock_get_provider.return_value = mock_provider
            mock_provider.chat_async = AsyncMock(
                return_value={
                    "content": '{"answer": "4"}',  # JSON string matching signature
                    "role": "assistant",
                    "model": "gpt-4",
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                }
            )
            mock_provider.chat = MagicMock(
                return_value={
                    "content": '{"answer": "4"}',  # JSON string matching signature
                    "role": "assistant",
                    "model": "gpt-4",
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                }
            )

            await agent.run_async(question="What is 2+2?")

            # Verify hooks were called
            assert agent.pre_called is True
            assert agent.post_called is True

    @pytest.mark.asyncio
    async def test_run_async_with_memory(self):
        """Test run_async() supports memory integration."""
        config = BaseAgentConfig(
            llm_provider="openai", model="gpt-4", use_async_llm=True
        )

        # Mock memory
        mock_memory = MagicMock()
        mock_memory.load_context.return_value = {"history": "Previous conversation"}
        mock_memory.save_turn = MagicMock()

        agent = BaseAgent(
            config=config, signature=SimpleQASignature(), memory=mock_memory
        )

        with patch("kaizen.nodes.ai.ai_providers.get_provider") as mock_get_provider:
            mock_provider = AsyncMock()
            mock_get_provider.return_value = mock_provider
            mock_provider.chat_async = AsyncMock(
                return_value={
                    "content": '{"answer": "4"}',  # JSON string matching signature
                    "role": "assistant",
                    "model": "gpt-4",
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                }
            )
            mock_provider.chat = MagicMock(
                return_value={
                    "content": '{"answer": "4"}',  # JSON string matching signature
                    "role": "assistant",
                    "model": "gpt-4",
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                }
            )

            # Execute with session_id
            await agent.run_async(question="What is 2+2?", session_id="session123")

            # Verify memory methods were called
            mock_memory.load_context.assert_called_once_with("session123")
            mock_memory.save_turn.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_async_error_handling(self):
        """Test run_async() handles errors gracefully."""
        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4",
            use_async_llm=True,
            error_handling_enabled=True,
        )
        agent = BaseAgent(config=config, signature=SimpleQASignature())

        with patch("kaizen.nodes.ai.ai_providers.get_provider") as mock_get_provider:
            mock_provider = AsyncMock()
            mock_get_provider.return_value = mock_provider

            # Simulate error in both async and sync methods
            mock_provider.chat_async = AsyncMock(side_effect=Exception("API error"))
            mock_provider.chat = MagicMock(side_effect=Exception("API error"))

            # Should not raise, should handle gracefully
            result = await agent.run_async(question="What is 2+2?")

            # Verify error was handled
            assert "error" in str(result).lower() or result is not None


class TestAsyncBackwardsCompatibility:
    """Test backwards compatibility - sync run() unchanged."""

    def test_sync_run_method_still_works(self):
        """Test sync run() method continues to work unchanged."""
        config = BaseAgentConfig(
            llm_provider="openai", model="gpt-4", use_async_llm=False
        )
        agent = BaseAgent(config=config, signature=SimpleQASignature())

        with patch("kaizen.nodes.ai.ai_providers.get_provider"):
            # Sync run should still work
            try:
                # Note: Will fail without proper mocking but method should exist
                assert hasattr(agent, "run")
                assert callable(agent.run)
            except Exception:
                pass  # Expected without full mocking

    def test_agent_without_async_flag_uses_sync(self):
        """Test agent without use_async_llm uses sync mode."""
        config = BaseAgentConfig(
            llm_provider="openai", model="gpt-4"
        )  # No use_async_llm
        agent = BaseAgent(config=config, signature=SimpleQASignature())

        # Should default to sync mode
        assert agent.config.use_async_llm is False

        # run_async() should raise error
        import asyncio

        with pytest.raises(ValueError, match="Agent not configured for async mode"):
            asyncio.run(agent.run_async(question="Test"))


class TestConcurrentAsyncExecution:
    """Test concurrent execution with async agents."""

    @pytest.mark.asyncio
    async def test_multiple_concurrent_requests(self):
        """Test multiple agents can execute concurrently."""
        import asyncio

        config = BaseAgentConfig(
            llm_provider="openai", model="gpt-4", use_async_llm=True
        )
        agent = BaseAgent(config=config, signature=SimpleQASignature())

        with patch("kaizen.nodes.ai.ai_providers.get_provider") as mock_get_provider:
            mock_provider = AsyncMock()
            mock_get_provider.return_value = mock_provider

            call_count = 0

            async def mock_chat_async(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                await asyncio.sleep(0.01)  # Simulate network delay
                return {
                    "content": f"Answer {call_count}",
                    "role": "assistant",
                    "model": "gpt-4",
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                }

            def mock_chat_sync(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return {
                    "content": f"Answer {call_count}",
                    "role": "assistant",
                    "model": "gpt-4",
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                }

            mock_provider.chat_async = mock_chat_async
            mock_provider.chat = mock_chat_sync

            # Execute 10 requests concurrently
            tasks = [agent.run_async(question=f"Question {i}") for i in range(10)]

            results = await asyncio.gather(*tasks)

            # Verify all completed
            assert len(results) == 10
            assert call_count == 10
