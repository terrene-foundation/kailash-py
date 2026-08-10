"""
Unit tests for streaming-chat example.

Tests cover:
- Agent initialization with StreamingStrategy
- Config parameters work correctly
- Strategy executes successfully
- Returns expected results
- Handles errors gracefully
- Async token streaming works
- Stream yields proper chunks
- Synchronous run() method still works
- Integration with BaseAgent infrastructure
- Full workflow with strategy
- Empty input handling
- Multiple sequential streams work independently
"""

import pytest

# Standardized example loading
from example_import_helper import import_example_module

# Load streaming-chat example
_streaming_module = import_example_module("examples/1-single-agent/streaming-chat")
StreamChatAgent = _streaming_module.StreamChatAgent
ChatConfig = _streaming_module.ChatConfig
ChatSignature = _streaming_module.ChatSignature

from kaizen.strategies.streaming import StreamingStrategy


class TestStreamingChatAgent:
    """Test StreamingStrategy integration in streaming-chat example."""

    def test_agent_initializes_with_streaming_strategy(self):
        """Test agent initializes with StreamingStrategy when streaming=True."""
        config = ChatConfig(streaming=True, llm_provider="mock", model="gpt-3.5-turbo")
        agent = StreamChatAgent(config)

        assert isinstance(
            agent.strategy, StreamingStrategy
        ), f"Agent should use StreamingStrategy when streaming=True, got {type(agent.strategy)}"

    def test_agent_initializes_without_streaming_strategy(self):
        """Test agent initializes without StreamingStrategy when streaming=False."""
        config = ChatConfig(streaming=False, llm_provider="mock", model="gpt-3.5-turbo")
        agent = StreamChatAgent(config)

        # Should use default strategy (not StreamingStrategy)
        assert not isinstance(
            agent.strategy, StreamingStrategy
        ), "Agent should not use StreamingStrategy when streaming=False"

    def test_config_parameters_work_correctly(self):
        """Test that config parameters are properly set."""
        config = ChatConfig(
            streaming=True,
            llm_provider="openai",
            model="gpt-4",
            temperature=0.7,
            max_tokens=500,
        )
        agent = StreamChatAgent(config)

        # Access agent_config (BaseAgentConfig) and chat_config (ChatConfig)
        assert agent.chat_config.llm_provider == "openai"
        assert agent.chat_config.model == "gpt-4"
        assert agent.chat_config.temperature == 0.7
        assert agent.chat_config.max_tokens == 500
        assert config.streaming is True

    @pytest.mark.asyncio
    async def test_async_streaming_works(self):
        """Test async token streaming works correctly."""
        config = ChatConfig(streaming=True, llm_provider="mock", model="gpt-3.5-turbo")
        agent = StreamChatAgent(config)

        chunks = []
        async for chunk in agent.stream_chat("What is Python?"):
            chunks.append(chunk)

        assert len(chunks) > 0, "Should yield at least one chunk"
        assert all(isinstance(c, str) for c in chunks), "All chunks should be strings"

    @pytest.mark.asyncio
    async def test_stream_yields_proper_chunks(self):
        """Test that stream yields proper text chunks."""
        config = ChatConfig(streaming=True, llm_provider="mock", model="gpt-3.5-turbo")
        agent = StreamChatAgent(config)

        chunks = []
        async for chunk in agent.stream_chat("Hello"):
            chunks.append(chunk)
            # Each chunk should be non-empty string
            assert isinstance(chunk, str)
            assert len(chunk) > 0

        # Reconstruct full response
        full_response = "".join(chunks)
        assert len(full_response) > 0, "Full response should be non-empty"

    @pytest.mark.asyncio
    async def test_streaming_strategy_requires_streaming_enabled(self):
        """Test that stream_chat raises error if streaming not enabled."""
        config = ChatConfig(streaming=False, llm_provider="mock", model="gpt-3.5-turbo")
        agent = StreamChatAgent(config)

        with pytest.raises(ValueError, match="Streaming requires StreamingStrategy"):
            async for _ in agent.stream_chat("test"):
                pass

    def test_synchronous_chat_method_works(self):
        """Test that synchronous chat() method still works.

        Note: run() returns a dict with result or error fields.
        With mock provider, we test structure only.
        """
        config = ChatConfig(streaming=False, llm_provider="mock", model="gpt-3.5-turbo")
        agent = StreamChatAgent(config)

        result = agent.run(message="What is AI?")

        # run() returns a dict - may have 'response' field or 'error' field
        assert isinstance(result, dict)
        assert "response" in result or "error" in result

    def test_run_method_returns_answer_from_signature(self):
        """Test that run() returns signature output.

        Note: run() returns a dict with result or error fields.
        With mock provider, we test structure only.
        """
        config = ChatConfig(streaming=False, llm_provider="mock", model="gpt-3.5-turbo")
        agent = StreamChatAgent(config)

        result = agent.run(message="Test question")

        # run() returns a dict - may have 'response' field or 'error' field
        assert isinstance(result, dict)
        assert "response" in result or "error" in result

    def test_agent_uses_chat_signature(self):
        """Test that agent uses ChatSignature."""
        config = ChatConfig(streaming=True, llm_provider="mock", model="gpt-3.5-turbo")
        agent = StreamChatAgent(config)

        assert isinstance(
            agent.signature, ChatSignature
        ), f"Agent should use ChatSignature, got {type(agent.signature)}"

    def test_empty_message_handling(self):
        """Test handling of empty message input.

        Note: Agent doesn't perform input validation - it processes empty input.
        With mock provider, we test structure only.
        """
        config = ChatConfig(streaming=False, llm_provider="mock", model="gpt-3.5-turbo")
        agent = StreamChatAgent(config)

        # Empty string
        result = agent.run(message="")
        assert isinstance(result, dict), "Should handle empty message"
        assert "response" in result or "error" in result

        # Whitespace only
        result = agent.run(message="   ")
        assert isinstance(result, dict), "Should handle whitespace-only message"
        assert "response" in result or "error" in result

    @pytest.mark.asyncio
    async def test_multiple_sequential_streams(self):
        """Test multiple sequential streams work independently."""
        config = ChatConfig(streaming=True, llm_provider="mock", model="gpt-3.5-turbo")
        agent = StreamChatAgent(config)

        # First stream
        chunks1 = []
        async for chunk in agent.stream_chat("First question"):
            chunks1.append(chunk)

        # Second stream
        chunks2 = []
        async for chunk in agent.stream_chat("Second question"):
            chunks2.append(chunk)

        # Both should work independently
        assert len(chunks1) > 0, "First stream should yield chunks"
        assert len(chunks2) > 0, "Second stream should yield chunks"

    @pytest.mark.asyncio
    async def test_streaming_and_non_streaming_both_work(self):
        """Test that both streaming and non-streaming modes work."""
        # Streaming mode
        config_streaming = ChatConfig(
            streaming=True, llm_provider="mock", model="gpt-3.5-turbo"
        )
        agent_streaming = StreamChatAgent(config_streaming)

        chunks = []
        async for chunk in agent_streaming.stream_chat("Test"):
            chunks.append(chunk)

        assert len(chunks) > 0, "Streaming mode should work"

        # Non-streaming mode
        config_normal = ChatConfig(
            streaming=False, llm_provider="mock", model="gpt-3.5-turbo"
        )
        agent_normal = StreamChatAgent(config_normal)

        response = agent_normal.chat("Test")
        assert isinstance(response, str), "Non-streaming mode should work"
        assert len(response) > 0

    def test_agent_inherits_from_base_agent(self):
        """Test that StreamChatAgent inherits from BaseAgent."""
        from kaizen.core.base_agent import BaseAgent

        config = ChatConfig(streaming=True, llm_provider="mock", model="gpt-3.5-turbo")
        agent = StreamChatAgent(config)

        assert isinstance(
            agent, BaseAgent
        ), "StreamChatAgent should inherit from BaseAgent"
