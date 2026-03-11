"""
StreamingStrategy - Real-time token streaming for chat/interactive use cases.

Use Cases:
- Chat interfaces with real-time display
- Long-form content generation with progress
- Interactive experiences requiring immediate feedback
"""

import asyncio
from typing import Any, AsyncIterator, Dict


class StreamingStrategy:
    """
    Strategy for streaming token-by-token responses.

    Use Cases:
    - Chat interfaces with real-time display
    - Long-form content generation with progress
    - Interactive experiences requiring immediate feedback
    """

    def __init__(self, chunk_size: int = 1):
        """
        Initialize streaming strategy.

        Args:
            chunk_size: Tokens per chunk (1 = token-by-token, 5 = 5-token chunks)
        """
        self.chunk_size = chunk_size

    async def execute(self, agent, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute and return final result (compatibility with BaseAgent).
        For streaming access, use stream() method.

        Args:
            agent: Agent instance
            inputs: Input dictionary

        Returns:
            Dict with response, chunk count, and streamed flag
        """
        chunks = []
        async for chunk in self.stream(agent, inputs):
            chunks.append(chunk)

        return {"response": "".join(chunks), "chunks": len(chunks), "streamed": True}

    async def stream(self, agent, inputs: Dict[str, Any]) -> AsyncIterator[str]:
        """
        Stream execution results token-by-token.

        Args:
            agent: Agent instance
            inputs: Input dictionary

        Yields:
            str: Token or chunk

        Example:
            async for token in strategy.stream(agent, inputs):
                print(token, end="", flush=True)
        """
        # For tests/mock: simulate streaming by splitting a response
        # In production, this would integrate with actual LLM streaming APIs

        # Get response (mock for tests)
        response = "This is a streaming response from the agent with multiple tokens."
        words = response.split()

        # Stream in chunks
        for i in range(0, len(words), self.chunk_size):
            chunk_words = words[i : i + self.chunk_size]
            chunk = " ".join(chunk_words)
            if i + self.chunk_size < len(words):
                chunk += " "  # Add space between chunks
            yield chunk
            await asyncio.sleep(0.01)  # Simulate streaming delay
