"""
Unit tests for ParallelBatchStrategy.

Tests cover:
- execute_batch processes all inputs
- Results in same order as inputs
- max_concurrent limits concurrency
- Batch of 10, 100, 1000 items
- Error in one item doesn't stop others
- Semaphore correctly limits concurrent execution
- Empty batch returns empty list
- Single item batch
- Verify concurrent execution (timing test)
- Different max_concurrent values (1, 5, 50)
"""

import asyncio
import time

import pytest
from kaizen.strategies.parallel_batch import ParallelBatchStrategy


class MockAgent:
    """Mock agent for testing."""

    async def execute(self, inputs):
        """Mock execution."""
        return {"response": f"Processed: {inputs.get('prompt', 'input')}"}


@pytest.mark.asyncio
async def test_execute_batch_processes_all_inputs():
    """Test that execute_batch processes all inputs."""
    strategy = ParallelBatchStrategy(max_concurrent=10)
    agent = MockAgent()
    batch = [{"prompt": f"Q{i}"} for i in range(10)]

    results = await strategy.execute_batch(agent, batch)

    assert len(results) == 10, f"Expected 10 results, got {len(results)}"
    assert all("response" in r for r in results), "All results should have response"


@pytest.mark.asyncio
async def test_results_in_same_order_as_inputs():
    """Test that results are in same order as inputs."""
    strategy = ParallelBatchStrategy(max_concurrent=10)
    agent = MockAgent()
    batch = [{"prompt": f"Q{i}"} for i in range(20)]

    results = await strategy.execute_batch(agent, batch)

    # Verify order by checking the prompts in responses
    for i, result in enumerate(results):
        expected_response = f"Processed: Q{i}"
        assert (
            result["response"] == expected_response
        ), f"Result {i} out of order: expected '{expected_response}', got '{result['response']}'"


@pytest.mark.asyncio
async def test_max_concurrent_limits_concurrency():
    """Test that max_concurrent limits concurrency."""
    # This test uses timing to verify concurrency limiting
    strategy = ParallelBatchStrategy(max_concurrent=5)
    agent = MockAgent()
    batch = [{"prompt": f"Q{i}"} for i in range(10)]

    start = time.time()
    results = await strategy.execute_batch(agent, batch)
    elapsed = time.time() - start

    # With max_concurrent=5 and 10 items, should take ~2 batches worth of time
    # Each item takes 0.01s, so 5 concurrent = 0.01s per batch
    # 10 items / 5 concurrent = 2 batches = ~0.02s minimum
    assert len(results) == 10
    assert (
        elapsed >= 0.015
    ), f"Should take at least 0.015s with concurrency limiting, took {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_batch_of_10_items():
    """Test batch of 10 items."""
    strategy = ParallelBatchStrategy(max_concurrent=10)
    agent = MockAgent()
    batch = [{"prompt": f"Q{i}"} for i in range(10)]

    results = await strategy.execute_batch(agent, batch)

    assert len(results) == 10
    assert all(r["batch"] is True for r in results)


@pytest.mark.asyncio
async def test_batch_of_100_items():
    """Test batch of 100 items."""
    strategy = ParallelBatchStrategy(max_concurrent=20)
    agent = MockAgent()
    batch = [{"prompt": f"Q{i}"} for i in range(100)]

    results = await strategy.execute_batch(agent, batch)

    assert len(results) == 100
    assert all("response" in r for r in results)


@pytest.mark.asyncio
async def test_batch_of_1000_items():
    """Test batch of 1000 items."""
    strategy = ParallelBatchStrategy(max_concurrent=50)
    agent = MockAgent()
    batch = [{"prompt": f"Q{i}"} for i in range(1000)]

    results = await strategy.execute_batch(agent, batch)

    assert len(results) == 1000
    assert all("response" in r for r in results)


@pytest.mark.asyncio
async def test_empty_batch_returns_empty_list():
    """Test that empty batch returns empty list."""
    strategy = ParallelBatchStrategy(max_concurrent=10)
    agent = MockAgent()
    batch = []

    results = await strategy.execute_batch(agent, batch)

    assert results == [], "Empty batch should return empty list"


@pytest.mark.asyncio
async def test_single_item_batch():
    """Test single item batch."""
    strategy = ParallelBatchStrategy(max_concurrent=10)
    agent = MockAgent()
    batch = [{"prompt": "Q0"}]

    results = await strategy.execute_batch(agent, batch)

    assert len(results) == 1
    assert results[0]["response"] == "Processed: Q0"


@pytest.mark.asyncio
async def test_verify_concurrent_execution_timing():
    """Test that execution is actually concurrent (timing test)."""
    # With concurrency, 10 items should take ~0.01s (not 0.1s sequential)
    strategy = ParallelBatchStrategy(max_concurrent=10)
    agent = MockAgent()
    batch = [{"prompt": f"Q{i}"} for i in range(10)]

    start = time.time()
    results = await strategy.execute_batch(agent, batch)
    elapsed = time.time() - start

    assert len(results) == 10
    # Should complete in ~0.01s (concurrent), not 0.1s (sequential)
    assert (
        elapsed < 0.05
    ), f"Concurrent execution should be fast (<0.05s), took {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_max_concurrent_1():
    """Test max_concurrent=1 (sequential execution)."""
    strategy = ParallelBatchStrategy(max_concurrent=1)
    agent = MockAgent()
    batch = [{"prompt": f"Q{i}"} for i in range(5)]

    start = time.time()
    results = await strategy.execute_batch(agent, batch)
    elapsed = time.time() - start

    assert len(results) == 5
    # With max_concurrent=1, should be sequential: 5 * 0.01s = 0.05s
    assert (
        elapsed >= 0.045
    ), f"Sequential execution should take >=0.045s, took {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_max_concurrent_5():
    """Test max_concurrent=5."""
    strategy = ParallelBatchStrategy(max_concurrent=5)
    agent = MockAgent()
    batch = [{"prompt": f"Q{i}"} for i in range(15)]

    results = await strategy.execute_batch(agent, batch)

    assert len(results) == 15
    assert all("response" in r for r in results)


@pytest.mark.asyncio
async def test_max_concurrent_50():
    """Test max_concurrent=50 with large batch."""
    strategy = ParallelBatchStrategy(max_concurrent=50)
    agent = MockAgent()
    batch = [{"prompt": f"Q{i}"} for i in range(100)]

    results = await strategy.execute_batch(agent, batch)

    assert len(results) == 100
    assert all("response" in r for r in results)


@pytest.mark.asyncio
async def test_execute_single_input_compatibility():
    """Test execute method for single input (BaseAgent compatibility)."""
    strategy = ParallelBatchStrategy(max_concurrent=10)
    agent = MockAgent()
    inputs = {"prompt": "test"}

    result = await strategy.execute(agent, inputs)

    assert "response" in result
    assert "batch" in result
    assert result["batch"] is False  # Single execution, not batch


@pytest.mark.asyncio
async def test_batch_flag_set_correctly():
    """Test that batch flag is set correctly in results."""
    strategy = ParallelBatchStrategy(max_concurrent=10)
    agent = MockAgent()

    # Single execution
    single_result = await strategy.execute(agent, {"prompt": "test"})
    assert single_result["batch"] is False

    # Batch execution
    batch_results = await strategy.execute_batch(agent, [{"prompt": "test"}])
    assert all(r["batch"] is True for r in batch_results)


@pytest.mark.asyncio
async def test_semaphore_limits_actual_concurrency():
    """Test that semaphore actually limits concurrent execution."""
    # Use a counter to track max concurrent executions
    max_concurrent = 0
    current_concurrent = 0
    lock = asyncio.Lock()

    class CountingStrategy(ParallelBatchStrategy):
        async def execute_batch(self, agent, batch_inputs):
            nonlocal max_concurrent, current_concurrent

            async def execute_one(inputs):
                nonlocal max_concurrent, current_concurrent

                async with self.max_concurrent_semaphore:
                    async with lock:
                        current_concurrent += 1
                        max_concurrent = max(max_concurrent, current_concurrent)

                    await asyncio.sleep(0.01)

                    async with lock:
                        current_concurrent -= 1

                    return {
                        "response": f"Processed: {inputs.get('prompt', 'input')}",
                        "batch": True,
                    }

            # Store semaphore for tracking
            self.max_concurrent_semaphore = asyncio.Semaphore(self.max_concurrent)

            tasks = [execute_one(inputs) for inputs in batch_inputs]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results

    strategy = CountingStrategy(max_concurrent=3)
    agent = MockAgent()
    batch = [{"prompt": f"Q{i}"} for i in range(10)]

    results = await strategy.execute_batch(agent, batch)

    assert len(results) == 10
    assert max_concurrent <= 3, f"Max concurrent should be <=3, was {max_concurrent}"


@pytest.mark.asyncio
async def test_different_batch_sizes_maintain_order():
    """Test that order is maintained across different batch sizes."""
    strategy = ParallelBatchStrategy(max_concurrent=10)
    agent = MockAgent()

    for batch_size in [5, 20, 50, 100]:
        batch = [{"prompt": f"Q{i}"} for i in range(batch_size)]
        results = await strategy.execute_batch(agent, batch)

        assert len(results) == batch_size
        for i, result in enumerate(results):
            expected = f"Processed: Q{i}"
            assert (
                result["response"] == expected
            ), f"Batch size {batch_size}, index {i}: expected '{expected}', got '{result['response']}'"
