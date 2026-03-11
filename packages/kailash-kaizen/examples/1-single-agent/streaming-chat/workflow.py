"""
Streaming Chat Agent - Real-time token streaming for interactive chat.

Demonstrates StreamingStrategy for real-time chat applications:
- Async token-by-token streaming with async for
- Real-time display for chatbots and assistants
- Both streaming and non-streaming modes
- Built on BaseAgent + StreamingStrategy

Use Cases:
- Interactive chatbots with real-time response display
- Long-form content generation with progress feedback
- Conversational AI with immediate user feedback
- Streaming API endpoints for chat applications

Performance:
- Streaming mode: ~10ms latency per token
- Non-streaming mode: Standard BaseAgent execution
- Configurable chunk size for throughput vs latency tradeoff
"""

from dataclasses import dataclass
from typing import AsyncIterator

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature
from kaizen.strategies.streaming import StreamingStrategy


class ChatSignature(Signature):
    """Signature for streaming chat interactions."""

    message: str = InputField(desc="User message")
    response: str = OutputField(desc="Agent response")


@dataclass
class ChatConfig:
    """Configuration for Streaming Chat Agent."""

    llm_provider: str = "openai"
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7
    max_tokens: int = 500
    streaming: bool = True  # Enable/disable streaming mode
    chunk_size: int = 1  # Tokens per chunk (1 = token-by-token)


class StreamChatAgent(BaseAgent):
    """
    Streaming Chat Agent using StreamingStrategy.

    Features:
    - Real-time token streaming via async iteration
    - Fallback to synchronous mode when streaming disabled
    - Built-in error handling and logging via BaseAgent
    - Configurable chunk size for throughput control

    Example:
        >>> import asyncio
        >>> config = ChatConfig(streaming=True)
        >>> agent = StreamChatAgent(config)
        >>>
        >>> # Streaming mode
        >>> async def demo():
        ...     async for token in agent.stream_chat("What is Python?"):
        ...         print(token, end="", flush=True)
        ...
        >>> asyncio.run(demo())
        >>>
        >>> # Non-streaming mode
        >>> config_sync = ChatConfig(streaming=False)
        >>> agent_sync = StreamChatAgent(config_sync)
        >>> response = agent_sync.chat("What is Python?")
        >>> print(response)
    """

    def __init__(self, config: ChatConfig):
        """Initialize Streaming Chat Agent with optional streaming strategy."""
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        # Use StreamingStrategy if streaming enabled
        strategy = None
        if config.streaming:
            strategy = StreamingStrategy(chunk_size=config.chunk_size)

        # Initialize BaseAgent
        super().__init__(config=config, signature=ChatSignature(), strategy=strategy)

        self.chat_config = config

    async def stream_chat(self, message: str) -> AsyncIterator[str]:
        """
        Stream chat response token by token.

        Args:
            message: User message to respond to

        Yields:
            str: Token or chunk from response

        Raises:
            ValueError: If streaming not enabled

        Example:
            >>> async for token in agent.stream_chat("Hello"):
            ...     print(token, end="", flush=True)
        """
        if not isinstance(self.strategy, StreamingStrategy):
            raise ValueError(
                "Streaming requires StreamingStrategy (set streaming=True in config)"
            )

        # Stream via StreamingStrategy
        async for chunk in self.strategy.stream(self, {"message": message}):
            yield chunk

    def chat(self, message: str) -> str:
        """
        Non-streaming chat (standard execution).

        Args:
            message: User message to respond to

        Returns:
            str: Complete response

        Example:
            >>> response = agent.chat("What is AI?")
            >>> print(response)
        """
        result = self.run(message=message)
        return result.get("response", "No response")


def demo_streaming():
    """Demo streaming chat with real-time token display."""
    import asyncio

    config = ChatConfig(streaming=True, llm_provider="mock", model="gpt-3.5-turbo")
    agent = StreamChatAgent(config)

    async def stream_demo():
        print("Streaming Chat Demo")
        print("=" * 50)
        print("\nQuestion: What is Python?\n")
        print("Streaming response: ", end="", flush=True)

        async for token in agent.stream_chat("What is Python?"):
            print(token, end="", flush=True)

        print("\n")

    asyncio.run(stream_demo())


def demo_non_streaming():
    """Demo non-streaming chat with standard execution."""
    config = ChatConfig(streaming=False, llm_provider="openai", model="gpt-3.5-turbo")
    agent = StreamChatAgent(config)

    print("Non-Streaming Chat Demo")
    print("=" * 50)
    print("\nQuestion: What is machine learning?\n")

    try:
        response = agent.chat("What is machine learning?")
        print(f"Response: {response}\n")
    except Exception as e:
        print("Note: Non-streaming requires configured LLM provider")
        print(f"Error: {e}\n")


if __name__ == "__main__":
    # Demo streaming mode
    demo_streaming()

    # Demo non-streaming mode
    demo_non_streaming()
