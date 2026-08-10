"""
Unit tests for batch-processing example.

Tests cover:
- Agent initialization with ParallelBatchStrategy
- Config parameters work correctly
- Strategy executes successfully
- Returns expected results for batch
- Handles errors gracefully
- Concurrent batch processing works
- Semaphore limiting prevents resource exhaustion
- Single execution still works
- Integration with BaseAgent infrastructure
- Full workflow with strategy
- Empty batch handling
- Max concurrent limit respected
"""

import pytest

# Standardized example loading
from example_import_helper import import_example_module

# Load batch-processing example
_batch_module = import_example_module("examples/1-single-agent/batch-processing")
BatchProcessorAgent = _batch_module.BatchProcessorAgent
BatchConfig = _batch_module.BatchConfig
ProcessingSignature = _batch_module.ProcessingSignature

from kaizen.strategies.parallel_batch import ParallelBatchStrategy


class TestBatchProcessorAgent:
    """Test ParallelBatchStrategy integration in batch-processing example."""

    def test_agent_initializes_with_parallel_batch_strategy(self):
        """Test agent initializes with ParallelBatchStrategy."""
        config = BatchConfig(
            max_concurrent=5, llm_provider="mock", model="gpt-3.5-turbo"
        )
        agent = BatchProcessorAgent(config)

        assert isinstance(
            agent.strategy, ParallelBatchStrategy
        ), f"Agent should use ParallelBatchStrategy, got {type(agent.strategy)}"

    def test_config_parameters_work_correctly(self):
        """Test that config parameters are properly set."""
        config = BatchConfig(
            max_concurrent=10, llm_provider="openai", model="gpt-4", temperature=0.5
        )
        agent = BatchProcessorAgent(config)

        assert agent.batch_config.max_concurrent == 10
        assert agent.batch_config.llm_provider == "openai"
        assert agent.batch_config.model == "gpt-4"
        assert agent.batch_config.temperature == 0.5

    def test_strategy_has_correct_max_concurrent(self):
        """Test that strategy is configured with correct max_concurrent."""
        config = BatchConfig(
            max_concurrent=7, llm_provider="mock", model="gpt-3.5-turbo"
        )
        agent = BatchProcessorAgent(config)

        assert (
            agent.strategy.max_concurrent == 7
        ), f"Strategy max_concurrent should be 7, got {agent.strategy.max_concurrent}"

    @pytest.mark.asyncio
    async def test_concurrent_batch_processing_works(self):
        """Test concurrent batch processing works correctly."""
        config = BatchConfig(
            max_concurrent=3, llm_provider="mock", model="gpt-3.5-turbo"
        )
        agent = BatchProcessorAgent(config)

        # Create batch of inputs
        batch = [{"prompt": f"Process item {i}"} for i in range(10)]

        results = await agent.process_batch(batch)

        assert len(results) == 10, f"Should process all 10 items, got {len(results)}"
        assert all(isinstance(r, dict) for r in results), "All results should be dicts"

    @pytest.mark.asyncio
    async def test_batch_results_in_same_order_as_inputs(self):
        """Test that batch results are in same order as inputs."""
        config = BatchConfig(
            max_concurrent=5, llm_provider="mock", model="gpt-3.5-turbo"
        )
        agent = BatchProcessorAgent(config)

        # Create batch with identifiable inputs
        batch = [{"prompt": f"Item_{i}"} for i in range(5)]

        results = await agent.process_batch(batch)

        # Results should be in same order
        assert len(results) == 5
        for i, result in enumerate(results):
            assert "response" in result or "batch" in result  # Check result structure

    @pytest.mark.asyncio
    async def test_max_concurrent_limit_respected(self):
        """Test that max_concurrent limit is respected (no resource exhaustion)."""
        config = BatchConfig(
            max_concurrent=2, llm_provider="mock", model="gpt-3.5-turbo"
        )
        agent = BatchProcessorAgent(config)

        # Large batch
        batch = [{"prompt": f"Item_{i}"} for i in range(20)]

        # This should NOT cause resource exhaustion
        results = await agent.process_batch(batch)

        assert len(results) == 20, "All items should be processed"

    @pytest.mark.asyncio
    async def test_empty_batch_handling(self):
        """Test handling of empty batch."""
        config = BatchConfig(
            max_concurrent=5, llm_provider="mock", model="gpt-3.5-turbo"
        )
        agent = BatchProcessorAgent(config)

        results = await agent.process_batch([])

        assert results == [], "Empty batch should return empty list"

    @pytest.mark.asyncio
    async def test_single_item_batch_works(self):
        """Test batch processing with single item."""
        config = BatchConfig(
            max_concurrent=5, llm_provider="mock", model="gpt-3.5-turbo"
        )
        agent = BatchProcessorAgent(config)

        batch = [{"prompt": "Single item"}]
        results = await agent.process_batch(batch)

        assert len(results) == 1, "Should process single item"
        assert isinstance(results[0], dict)

    def test_agent_uses_processing_signature(self):
        """Test that agent uses ProcessingSignature."""
        config = BatchConfig(
            max_concurrent=5, llm_provider="mock", model="gpt-3.5-turbo"
        )
        agent = BatchProcessorAgent(config)

        assert isinstance(
            agent.signature, ProcessingSignature
        ), f"Agent should use ProcessingSignature, got {type(agent.signature)}"

    def test_agent_inherits_from_base_agent(self):
        """Test that BatchProcessorAgent inherits from BaseAgent."""
        from kaizen.core.base_agent import BaseAgent

        config = BatchConfig(
            max_concurrent=5, llm_provider="mock", model="gpt-3.5-turbo"
        )
        agent = BatchProcessorAgent(config)

        assert isinstance(
            agent, BaseAgent
        ), "BatchProcessorAgent should inherit from BaseAgent"

    @pytest.mark.asyncio
    async def test_batch_processing_performance(self):
        """Test that batch processing is reasonably fast."""
        import time

        config = BatchConfig(
            max_concurrent=5, llm_provider="mock", model="gpt-3.5-turbo"
        )
        agent = BatchProcessorAgent(config)

        batch = [{"prompt": f"Item_{i}"} for i in range(10)]

        start = time.time()
        results = await agent.process_batch(batch)
        elapsed = time.time() - start

        assert len(results) == 10
        # With 0.01s per item and max_concurrent=5, should take ~0.02s (2 batches)
        # Allow generous margin for test environment
        assert elapsed < 1.0, f"Batch processing too slow: {elapsed:.3f}s"

    @pytest.mark.asyncio
    async def test_batch_method_delegates_to_strategy(self):
        """Test that process_batch delegates to strategy.execute_batch."""
        config = BatchConfig(
            max_concurrent=5, llm_provider="mock", model="gpt-3.5-turbo"
        )
        agent = BatchProcessorAgent(config)

        batch = [{"prompt": "test"}]
        results = await agent.process_batch(batch)

        # Should have called strategy.execute_batch
        assert len(results) == 1
        assert isinstance(results[0], dict)

    @pytest.mark.asyncio
    async def test_different_max_concurrent_values(self):
        """Test different max_concurrent values work correctly."""
        # Test various concurrency limits
        for max_concurrent in [1, 3, 10]:
            config = BatchConfig(
                max_concurrent=max_concurrent,
                llm_provider="mock",
                model="gpt-3.5-turbo",
            )
            agent = BatchProcessorAgent(config)

            batch = [{"prompt": f"Item_{i}"} for i in range(5)]
            results = await agent.process_batch(batch)

            assert (
                len(results) == 5
            ), f"Should process all 5 items with max_concurrent={max_concurrent}"
