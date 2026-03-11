"""
Batch Processor Agent - Concurrent batch processing for high-throughput use cases.

Demonstrates ParallelBatchStrategy for high-throughput data processing:
- Concurrent processing with semaphore limiting
- Process 1000s of items efficiently
- No resource exhaustion with configurable max_concurrent
- Built on BaseAgent + ParallelBatchStrategy

Use Cases:
- Bulk document analysis and classification
- Large-scale data transformation
- High-throughput API processing
- Embarrassingly parallel workloads

Performance:
- Concurrent execution with semaphore control
- Configurable max_concurrent limit (default: 10)
- Efficient resource utilization without exhaustion
"""

from dataclasses import dataclass
from typing import Any, Dict, List

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature
from kaizen.strategies.parallel_batch import ParallelBatchStrategy


class ProcessingSignature(Signature):
    """Signature for batch data processing."""

    prompt: str = InputField(desc="Data item to process")
    result: str = OutputField(desc="Processed result")


@dataclass
class BatchConfig:
    """Configuration for Batch Processor Agent."""

    llm_provider: str = "openai"
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.1
    max_tokens: int = 200
    max_concurrent: int = 10  # Maximum concurrent executions


class BatchProcessorAgent(BaseAgent):
    """
    Batch Processor Agent using ParallelBatchStrategy.

    Features:
    - Concurrent batch processing with semaphore limiting
    - Configurable max_concurrent to prevent resource exhaustion
    - Built-in error handling and logging via BaseAgent
    - Efficient processing of large datasets

    Example:
        >>> import asyncio
        >>> config = BatchConfig(max_concurrent=5)
        >>> agent = BatchProcessorAgent(config)
        >>>
        >>> # Process batch of 100 items
        >>> batch = [{"prompt": f"Process item {i}"} for i in range(100)]
        >>> results = asyncio.run(agent.process_batch(batch))
        >>> print(f"Processed {len(results)} items")
    """

    def __init__(self, config: BatchConfig):
        """Initialize Batch Processor Agent with parallel batch strategy."""
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        # Use ParallelBatchStrategy with configured max_concurrent
        strategy = ParallelBatchStrategy(max_concurrent=config.max_concurrent)

        # Initialize BaseAgent
        super().__init__(
            config=config, signature=ProcessingSignature(), strategy=strategy
        )

        self.batch_config = config

    async def process_batch(self, batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process batch of inputs concurrently.

        Args:
            batch: List of input dictionaries

        Returns:
            List[Dict[str, Any]]: Results in same order as inputs

        Example:
            >>> batch = [{"prompt": f"Item {i}"} for i in range(10)]
            >>> results = await agent.process_batch(batch)
        """
        if not batch:
            return []

        # Delegate to ParallelBatchStrategy
        results = await self.strategy.execute_batch(self, batch)

        return results

    def process_single(self, prompt: str) -> Dict[str, Any]:
        """
        Process single item (non-batch).

        Args:
            prompt: Single prompt to process

        Returns:
            Dict[str, Any]: Processing result

        Example:
            >>> result = agent.process_single("Analyze this text")
        """
        result = self.run(prompt=prompt)
        return result


def demo_batch_processing():
    """Demo concurrent batch processing."""
    import asyncio
    import time

    config = BatchConfig(max_concurrent=5, llm_provider="mock", model="gpt-3.5-turbo")
    agent = BatchProcessorAgent(config)

    async def batch_demo():
        print("Batch Processing Demo")
        print("=" * 50)

        # Create batch
        batch = [{"prompt": f"Process document {i}"} for i in range(20)]
        print(
            f"\nProcessing {len(batch)} items with max_concurrent={config.max_concurrent}..."
        )

        start = time.time()
        results = await agent.process_batch(batch)
        elapsed = time.time() - start

        print(f"Completed {len(results)} items in {elapsed:.3f}s")
        print(f"Throughput: {len(results)/elapsed:.1f} items/sec\n")

        # Show first few results
        print("Sample results:")
        for i, result in enumerate(results[:3]):
            print(f"  {i+1}. {result}")

    asyncio.run(batch_demo())


def demo_different_concurrency():
    """Demo different concurrency levels."""
    import asyncio
    import time

    async def test_concurrency(max_concurrent: int):
        config = BatchConfig(
            max_concurrent=max_concurrent, llm_provider="mock", model="gpt-3.5-turbo"
        )
        agent = BatchProcessorAgent(config)

        batch = [{"prompt": f"Item {i}"} for i in range(10)]

        start = time.time()
        results = await agent.process_batch(batch)
        elapsed = time.time() - start

        return len(results), elapsed

    async def compare():
        print("Concurrency Comparison")
        print("=" * 50)

        for max_concurrent in [1, 3, 5, 10]:
            count, elapsed = await test_concurrency(max_concurrent)
            print(
                f"max_concurrent={max_concurrent:2d}: {count} items in {elapsed:.3f}s ({count/elapsed:.1f} items/sec)"
            )

    asyncio.run(compare())


if __name__ == "__main__":
    # Demo batch processing
    demo_batch_processing()

    print()

    # Demo concurrency comparison
    demo_different_concurrency()
