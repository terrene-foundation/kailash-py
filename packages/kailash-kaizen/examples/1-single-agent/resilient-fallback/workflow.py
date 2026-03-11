"""
Resilient Fallback Agent - Sequential fallback for robust degraded service.

Demonstrates FallbackStrategy for multi-model redundancy:
- Try strategies in order until one succeeds
- Primary → Secondary → Tertiary fallback chain
- Track which strategy succeeded
- Built on BaseAgent + FallbackStrategy

Use Cases:
- Multi-model fallback (GPT-4 → GPT-3.5 → local model)
- Cost optimization (try expensive first, fall back to cheap)
- Redundancy for critical operations
- Progressive degradation for high availability

Performance:
- Immediate return on first success
- Error tracking for all failed attempts
- No unnecessary retries
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature
from kaizen.strategies.async_single_shot import AsyncSingleShotStrategy
from kaizen.strategies.fallback import FallbackStrategy


class QuerySignature(Signature):
    """Signature for resilient query processing."""

    query: str = InputField(desc="Query to process")
    response: str = OutputField(desc="Response to query")


@dataclass
class FallbackConfig:
    """Configuration for Resilient Fallback Agent."""

    models: List[str] = field(default_factory=list)  # Fallback chain of models
    llm_provider: str = "openai"
    temperature: float = 0.7
    max_tokens: int = 300

    def __post_init__(self):
        """Validate configuration."""
        if not self.models:
            raise ValueError(
                "FallbackConfig requires at least one model in fallback chain"
            )


class ResilientAgent(BaseAgent):
    """
    Resilient Fallback Agent using FallbackStrategy.

    Features:
    - Sequential fallback through model chain
    - Immediate return on first success
    - Track which strategy succeeded
    - Error summary for all failures
    - Built-in logging and error handling via BaseAgent

    Example:
        >>> import asyncio
        >>> # Configure fallback chain: GPT-4 → GPT-3.5 → local
        >>> config = FallbackConfig(
        ...     models=["gpt-4", "gpt-3.5-turbo", "local-model"]
        ... )
        >>> agent = ResilientAgent(config)
        >>>
        >>> # Query with automatic fallback
        >>> result = asyncio.run(agent.query_async("What is AI?"))
        >>> print(f"Used strategy: {result.get('_fallback_strategy_used')}")
    """

    def __init__(self, config: FallbackConfig):
        """Initialize Resilient Fallback Agent with model fallback chain."""
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        # Create strategies for each model in fallback chain
        strategies = []
        for model in config.models:
            # Each model gets its own strategy
            # In a real implementation, you'd configure each with different models
            # For demo purposes, we use AsyncSingleShotStrategy
            strategy = AsyncSingleShotStrategy()
            strategies.append(strategy)

        # Use FallbackStrategy with model strategies
        fallback_strategy = FallbackStrategy(strategies=strategies)

        # Initialize BaseAgent
        super().__init__(
            config=config, signature=QuerySignature(), strategy=fallback_strategy
        )

        self.fallback_config = config

    async def query_async(self, query: str) -> Dict[str, Any]:
        """
        Process query with automatic fallback.

        Args:
            query: Query to process

        Returns:
            Dict with response and fallback metadata

        Example:
            >>> result = await agent.query_async("What is Python?")
            >>> print(result.get("response"))
            >>> print(f"Used strategy #{result.get('_fallback_strategy_used')}")
        """
        # Execute via strategy (handles fallback automatically)
        result = await self.strategy.execute(self, {"query": query})
        return result

    def query(self, query: str) -> str:
        """
        Synchronous query (for compatibility).

        Args:
            query: Query to process

        Returns:
            str: Response text

        Example:
            >>> response = agent.query("What is machine learning?")
        """
        import asyncio

        result = asyncio.run(self.query_async(query))
        return result.get("response", "No response")

    def get_error_summary(self) -> List[Dict[str, Any]]:
        """
        Get error summary from failed strategies.

        Returns:
            List of error summaries with strategy name, error message, and type

        Example:
            >>> try:
            ...     result = await agent.query_async("test")
            ... except Exception:
            ...     errors = agent.get_error_summary()
            ...     for error in errors:
            ...         print(f"{error['strategy']}: {error['error']}")
        """
        return self.strategy.get_error_summary()


def demo_fallback_success():
    """Demo successful fallback (primary strategy works)."""
    import asyncio

    config = FallbackConfig(
        models=["gpt-4", "gpt-3.5-turbo", "local-model"], llm_provider="mock"
    )
    agent = ResilientAgent(config)

    async def demo():
        print("Resilient Fallback Demo - Primary Success")
        print("=" * 50)
        print(f"Fallback chain: {' → '.join(config.models)}\n")

        try:
            result = await agent.query_async("What is artificial intelligence?")

            print("Query: What is artificial intelligence?")
            print(f"Response: {result.get('response', 'N/A')}")
            print(
                f"Strategy used: #{result.get('_fallback_strategy_used', 0)} ({config.models[result.get('_fallback_strategy_used', 0)]})"
            )
            print(f"Attempts: {result.get('_fallback_attempts', 1)}\n")

        except Exception as e:
            print(f"All strategies failed: {e}\n")
            errors = agent.get_error_summary()
            for i, error in enumerate(errors):
                print(f"  {i+1}. {error['strategy']}: {error['error']}")

    asyncio.run(demo())


def demo_fallback_chain():
    """Demo multiple queries with fallback."""
    import asyncio

    config = FallbackConfig(models=["gpt-4", "gpt-3.5-turbo"], llm_provider="mock")
    agent = ResilientAgent(config)

    async def demo():
        print("Fallback Chain Demo")
        print("=" * 50)
        print(f"Chain: {' → '.join(config.models)}\n")

        queries = [
            "What is Python?",
            "Explain machine learning",
            "What are neural networks?",
        ]

        for i, query in enumerate(queries, 1):
            try:
                result = await agent.query_async(query)
                strategy_idx = result.get("_fallback_strategy_used", 0)
                print(f"{i}. Query: {query}")
                print(f"   Model: {config.models[strategy_idx]}")
                print(f"   Response: {result.get('response', 'N/A')[:50]}...\n")

            except Exception as e:
                print(f"{i}. Query: {query}")
                print(f"   Error: {e}\n")

    asyncio.run(demo())


def demo_cost_optimization():
    """Demo cost optimization with fallback."""
    print("Cost Optimization Demo")
    print("=" * 50)
    print("Strategy: Try expensive model first, fall back to cheap\n")

    # Expensive → Moderate → Cheap
    config = FallbackConfig(
        models=["gpt-4", "gpt-3.5-turbo", "local-llama"], llm_provider="mock"
    )

    print(f"Fallback chain: {' → '.join(config.models)}")
    print("  gpt-4: $0.03/1K tokens (best quality)")
    print("  gpt-3.5-turbo: $0.002/1K tokens (good quality)")
    print("  local-llama: Free (basic quality)")
    print("\nIf GPT-4 fails → fall back to GPT-3.5")
    print("If GPT-3.5 fails → fall back to local model")
    print("Optimize cost while maintaining service\n")


if __name__ == "__main__":
    # Demo successful fallback
    demo_fallback_success()

    print()

    # Demo fallback chain
    demo_fallback_chain()

    print()

    # Demo cost optimization
    demo_cost_optimization()
