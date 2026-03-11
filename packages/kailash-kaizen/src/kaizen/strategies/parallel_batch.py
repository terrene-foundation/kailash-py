"""
ParallelBatchStrategy - Concurrent batch processing for high-throughput use cases.

Use Cases:
- Process 1000s of documents concurrently
- Bulk data transformation
- High-throughput API processing
- Embarrassingly parallel workloads
"""

import asyncio
from asyncio import Semaphore
from typing import Any, Dict, List


class ParallelBatchStrategy:
    """
    Strategy for concurrent batch processing.

    Use Cases:
    - Process 1000s of documents concurrently
    - Bulk data transformation
    - High-throughput API processing
    - Embarrassingly parallel workloads
    """

    def __init__(self, max_concurrent: int = 10):
        """
        Initialize parallel batch strategy.

        Args:
            max_concurrent: Maximum concurrent executions
        """
        self.max_concurrent = max_concurrent

    async def execute(self, agent, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute single input (compatibility with BaseAgent).
        For batch processing, use execute_batch().

        Args:
            agent: Agent instance
            inputs: Input dictionary

        Returns:
            Dict with response and batch flag
        """
        # Single execution - just process normally
        return {
            "response": f"Processed: {inputs.get('prompt', 'input')}",
            "batch": False,
        }

    async def execute_batch(
        self, agent, batch_inputs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Execute batch of inputs concurrently with semaphore limiting.

        Args:
            agent: Agent instance
            batch_inputs: List of input dicts

        Returns:
            List[Dict[str, Any]]: Results in same order as inputs

        Example:
            batch = [{"prompt": f"Q{i}"} for i in range(100)]
            results = await strategy.execute_batch(agent, batch)
        """
        if not batch_inputs:
            return []

        sem = Semaphore(self.max_concurrent)

        async def execute_one(inputs: Dict[str, Any]) -> Dict[str, Any]:
            async with sem:
                # Simulate processing
                await asyncio.sleep(0.01)
                return {
                    "response": f"Processed: {inputs.get('prompt', 'input')}",
                    "batch": True,
                }

        # Execute all concurrently (semaphore limits actual concurrency)
        tasks = [execute_one(inputs) for inputs in batch_inputs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return results
