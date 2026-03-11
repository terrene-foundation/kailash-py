"""
StreamingChatAgent - Production-Ready Real-Time Token Streaming

Zero-config usage:
    from kaizen.agents import StreamingChatAgent

    agent = StreamingChatAgent()

    # Streaming mode
    async for token in agent.stream("What is Python?"):
        print(token, end="", flush=True)

    # Non-streaming mode (uses .run())
    result = agent.run(message="What is AI?")
    print(result["response"])

Progressive configuration:
    agent = StreamingChatAgent(
        llm_provider="openai",
        model="gpt-4",
        temperature=0.7,
        streaming=True,
        chunk_size=1  # Token-by-token streaming
    )

Environment variable support:
    KAIZEN_LLM_PROVIDER=openai
    KAIZEN_MODEL=gpt-3.5-turbo
    KAIZEN_TEMPERATURE=0.7
    KAIZEN_MAX_TOKENS=500
    KAIZEN_STREAMING=true
    KAIZEN_CHUNK_SIZE=1
"""

import os
from dataclasses import dataclass, field, replace
from typing import Any, AsyncIterator, Dict, Optional

from kailash.nodes.base import NodeMetadata
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature
from kaizen.strategies.streaming import StreamingStrategy


class ChatSignature(Signature):
    """Signature for streaming chat interactions."""

    message: str = InputField(desc="User message")
    response: str = OutputField(desc="Agent response")


@dataclass
class StreamingChatConfig:
    """
    Configuration for Streaming Chat Agent.

    All parameters have sensible defaults and can be overridden via:
    1. Constructor arguments (highest priority)
    2. Environment variables (KAIZEN_*)
    3. Default values (lowest priority)
    """

    # LLM configuration
    llm_provider: str = field(
        default_factory=lambda: os.getenv("KAIZEN_LLM_PROVIDER", "openai")
    )
    model: str = field(
        default_factory=lambda: os.getenv("KAIZEN_MODEL", "gpt-3.5-turbo")
    )
    temperature: float = field(
        default_factory=lambda: float(os.getenv("KAIZEN_TEMPERATURE", "0.7"))
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("KAIZEN_MAX_TOKENS", "500"))
    )

    # Streaming configuration
    streaming: bool = field(
        default_factory=lambda: os.getenv("KAIZEN_STREAMING", "true").lower() == "true"
    )
    chunk_size: int = field(
        default_factory=lambda: int(os.getenv("KAIZEN_CHUNK_SIZE", "1"))
    )

    # Technical configuration
    timeout: int = 30
    retry_attempts: int = 3
    provider_config: Dict[str, Any] = field(default_factory=dict)


class StreamingChatAgent(BaseAgent):
    """
    Production-ready Streaming Chat Agent using StreamingStrategy.

    Features:
    - Zero-config with sensible defaults (streaming enabled)
    - Real-time token streaming via async iteration
    - Fallback to synchronous mode when streaming disabled
    - Built-in error handling and logging via BaseAgent
    - Configurable chunk size for throughput control

    Inherits from BaseAgent:
    - Signature-based chat pattern
    - Streaming execution via StreamingStrategy
    - Error handling (ErrorHandlingMixin)
    - Performance tracking (PerformanceMixin)
    - Structured logging (LoggingMixin)

    Use Cases:
    - Interactive chatbots with real-time response display
    - Long-form content generation with progress feedback
    - Conversational AI with immediate user feedback
    - Streaming API endpoints for chat applications
    - Live customer support

    Performance:
    - Streaming mode: ~10ms latency per token
    - Non-streaming mode: Standard BaseAgent execution
    - Configurable chunk size for throughput vs latency tradeoff
    - Typical UX: Real-time typing effect

    Usage:
        # Zero-config streaming
        import asyncio
        agent = StreamingChatAgent()

        async def demo():
            async for token in agent.stream("What is Python?"):
                print(token, end="", flush=True)

        asyncio.run(demo())

        # Non-streaming mode
        agent_sync = StreamingChatAgent(streaming=False)
        result = agent_sync.run(message="What is AI?")
        print(result["response"])

        # Custom configuration
        agent = StreamingChatAgent(
            llm_provider="openai",
            model="gpt-4",
            streaming=True,
            chunk_size=5  # Stream 5 tokens at a time
        )
    """

    # Node metadata for Studio discovery
    metadata = NodeMetadata(
        name="StreamingChatAgent",
        description="Real-time token-by-token streaming for interactive chat applications",
        version="1.0.0",
        tags={"ai", "kaizen", "streaming", "chat", "real-time", "interactive"},
    )

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        streaming: Optional[bool] = None,
        chunk_size: Optional[int] = None,
        timeout: Optional[int] = None,
        retry_attempts: Optional[int] = None,
        provider_config: Optional[Dict[str, Any]] = None,
        config: Optional[StreamingChatConfig] = None,
        **kwargs,
    ):
        """
        Initialize Streaming Chat Agent with zero-config defaults.

        Args:
            llm_provider: Override default LLM provider
            model: Override default model
            temperature: Override default temperature
            max_tokens: Override default max tokens
            streaming: Enable/disable streaming mode
            chunk_size: Tokens per chunk (1 = token-by-token)
            timeout: Override default timeout
            retry_attempts: Override default retry attempts
            provider_config: Additional provider-specific configuration
            config: Full config object (overrides individual params)
        """
        # If config object provided, use it; otherwise build from parameters
        if config is None:
            config = StreamingChatConfig()

            # Override defaults with provided parameters
            if llm_provider is not None:
                config = replace(config, llm_provider=llm_provider)
            if model is not None:
                config = replace(config, model=model)
            if temperature is not None:
                config = replace(config, temperature=temperature)
            if max_tokens is not None:
                config = replace(config, max_tokens=max_tokens)
            if streaming is not None:
                config = replace(config, streaming=streaming)
            if chunk_size is not None:
                config = replace(config, chunk_size=chunk_size)
            if timeout is not None:
                config = replace(config, timeout=timeout)
            if retry_attempts is not None:
                config = replace(config, retry_attempts=retry_attempts)
            if provider_config is not None:
                config = replace(config, provider_config=provider_config)

        # Merge timeout into provider_config
        if config.timeout and (
            not config.provider_config or "timeout" not in config.provider_config
        ):
            provider_cfg = (
                config.provider_config.copy() if config.provider_config else {}
            )
            provider_cfg["timeout"] = config.timeout
            config = replace(config, provider_config=provider_cfg)

        # Use StreamingStrategy if streaming enabled
        strategy = None
        if config.streaming:
            strategy = StreamingStrategy(chunk_size=config.chunk_size)

        # Initialize BaseAgent
        super().__init__(
            config=config,  # Auto-converted to BaseAgentConfig
            signature=ChatSignature(),
            strategy=strategy,
            **kwargs,
        )

        self.chat_config = config

    async def stream(self, message: str) -> AsyncIterator[str]:
        """
        Stream chat response token by token.

        Args:
            message: User message to respond to

        Yields:
            str: Token or chunk from response

        Raises:
            ValueError: If streaming not enabled

        Example:
            >>> import asyncio
            >>> agent = StreamingChatAgent()
            >>>
            >>> async def demo():
            ...     async for token in agent.stream("Hello"):
            ...         print(token, end="", flush=True)
            ...
            >>> asyncio.run(demo())
        """
        if not isinstance(self.strategy, StreamingStrategy):
            raise ValueError(
                "Streaming requires StreamingStrategy (set streaming=True in config)"
            )

        # Stream via StreamingStrategy
        async for chunk in self.strategy.stream(self, {"message": message}):
            yield chunk


# Convenience function for quick streaming chat
async def stream_chat(
    message: str,
    llm_provider: str = "openai",
    model: str = "gpt-3.5-turbo",
    chunk_size: int = 1,
) -> AsyncIterator[str]:
    """
    Quick streaming chat with default configuration.

    Args:
        message: User message
        llm_provider: LLM provider to use
        model: Model to use
        chunk_size: Tokens per chunk

    Yields:
        str: Token or chunk from response

    Example:
        >>> import asyncio
        >>> from kaizen.agents.specialized.streaming_chat import stream_chat
        >>>
        >>> async def demo():
        ...     async for token in stream_chat("What is Python?"):
        ...         print(token, end="", flush=True)
        ...
        >>> asyncio.run(demo())
    """
    agent = StreamingChatAgent(
        llm_provider=llm_provider, model=model, streaming=True, chunk_size=chunk_size
    )

    async for chunk in agent.stream(message):
        yield chunk
