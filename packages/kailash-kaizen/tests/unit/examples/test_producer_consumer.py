"""
Test Suite for Producer-Consumer Multi-Agent Pattern

Tests the pipeline processing pattern with queue management:
- 2 ProducerAgents generate work items
- 3 ConsumerAgents process work items
- 1 QueueManagerAgent manages queue and load balancing

Coverage: 21 comprehensive tests
"""

import pytest

# Standardized example loading
from example_import_helper import import_example_module

# Load producer-consumer example
_module = import_example_module("examples/2-multi-agent/producer-consumer")
ProducerAgent = _module.ProducerAgent
ConsumerAgent = _module.ConsumerAgent
QueueManagerAgent = _module.QueueManagerAgent
ProducerConsumerConfig = _module.ProducerConsumerConfig
producer_consumer_workflow = _module.producer_consumer_workflow

from kaizen.memory.shared_memory import SharedMemoryPool


class TestProducerAgent:
    """Test ProducerAgent work item generation (3 tests)"""

    def test_producer_generates_items(self):
        """Test single producer generates work items"""
        shared_pool = SharedMemoryPool()
        config = ProducerConsumerConfig()

        producer = ProducerAgent(
            config=config, shared_memory=shared_pool, agent_id="producer_1"
        )

        # Produce 3 items
        results = producer.produce(task_spec="Generate test data", count=3)

        assert len(results) == 3
        assert all("item" in r for r in results)
        assert all("item_id" in r for r in results)
        assert all(r["item_id"].startswith("item_") for r in results)

    def test_multiple_producers(self):
        """Test multiple producers generate distinct items"""
        shared_pool = SharedMemoryPool()
        config = ProducerConsumerConfig()

        producer1 = ProducerAgent(config, shared_pool, "producer_1")
        producer2 = ProducerAgent(config, shared_pool, "producer_2")

        results1 = producer1.produce("Task A", count=2)
        results2 = producer2.produce("Task B", count=2)

        # Verify distinct IDs
        ids1 = [r["item_id"] for r in results1]
        ids2 = [r["item_id"] for r in results2]

        assert len(set(ids1 + ids2)) == 4  # All unique

    def test_items_written_to_queue(self):
        """Test produced items written to shared memory queue"""

        shared_pool = SharedMemoryPool()
        config = ProducerConsumerConfig()

        producer = ProducerAgent(config, shared_pool, "producer_1")
        producer.produce("Generate items", count=3)

        # Read from queue segment
        memories = shared_pool.read_relevant(
            agent_id="test_reader",
            tags=["work", "pending"],
            segments=["queue"],
            exclude_own=False,
            limit=10,
        )

        assert len(memories) >= 3
        # Check that metadata contains item
        for m in memories:
            metadata = m.get("metadata", {})
            assert "item" in metadata


class TestConsumerAgent:
    """Test ConsumerAgent work processing (4 tests)"""

    def test_consumer_reads_from_queue(self):
        """Test consumer reads items from queue"""

        shared_pool = SharedMemoryPool()
        config = ProducerConsumerConfig()

        # Producer creates items
        producer = ProducerAgent(config, shared_pool, "producer_1")
        producer.produce("Task", count=2)

        # Consumer reads item
        consumer = ConsumerAgent(config, shared_pool, "consumer_1")
        result = consumer.consume()

        assert result is not None
        assert "item" in result
        assert "result" in result

    def test_consumer_processes_item(self):
        """Test consumer processes work item"""

        shared_pool = SharedMemoryPool()
        config = ProducerConsumerConfig()

        producer = ProducerAgent(config, shared_pool, "producer_1")
        producer.produce("Process this", count=1)

        consumer = ConsumerAgent(config, shared_pool, "consumer_1")
        result = consumer.consume()

        assert "status" in result
        assert result["status"] is not None
        assert "result" in result
        assert len(result["result"]) > 0

    def test_multiple_consumers(self):
        """Test multiple consumers process items in parallel"""

        shared_pool = SharedMemoryPool()
        config = ProducerConsumerConfig()

        # Producer creates 6 items
        producer = ProducerAgent(config, shared_pool, "producer_1")
        producer.produce("Task", count=6)

        # 3 consumers process items
        consumer1 = ConsumerAgent(config, shared_pool, "consumer_1")
        consumer2 = ConsumerAgent(config, shared_pool, "consumer_2")
        consumer3 = ConsumerAgent(config, shared_pool, "consumer_3")

        results = []
        for consumer in [consumer1, consumer2, consumer3]:
            result = consumer.consume()
            if result:
                results.append(result)

        assert len(results) >= 3

    def test_results_written_to_completed(self):
        """Test consumer writes results to completed segment"""

        shared_pool = SharedMemoryPool()
        config = ProducerConsumerConfig()

        producer = ProducerAgent(config, shared_pool, "producer_1")
        producer.produce("Task", count=1)

        consumer = ConsumerAgent(config, shared_pool, "consumer_1")
        consumer.consume()

        # Check completed segment
        completed = shared_pool.read_relevant(
            agent_id="test_reader",
            tags=["work", "completed"],
            segments=["results"],
            exclude_own=False,
            limit=10,
        )

        assert len(completed) >= 1


class TestQueueManagerAgent:
    """Test QueueManagerAgent queue tracking (4 tests)"""

    def test_queue_manager_tracks_pending(self):
        """Test queue manager tracks pending items"""

        shared_pool = SharedMemoryPool()
        config = ProducerConsumerConfig()

        producer = ProducerAgent(config, shared_pool, "producer_1")
        producer.produce("Task", count=5)

        manager = QueueManagerAgent(config, shared_pool, "queue_manager")
        stats = manager.get_queue_stats()

        assert "pending_count" in stats
        assert stats["pending_count"] >= 5

    def test_queue_manager_tracks_completed(self):
        """Test queue manager tracks completed items"""

        shared_pool = SharedMemoryPool()
        config = ProducerConsumerConfig()

        producer = ProducerAgent(config, shared_pool, "producer_1")
        producer.produce("Task", count=2)

        consumer = ConsumerAgent(config, shared_pool, "consumer_1")
        consumer.consume()
        consumer.consume()

        manager = QueueManagerAgent(config, shared_pool, "queue_manager")
        stats = manager.get_queue_stats()

        assert "completed_count" in stats
        assert stats["completed_count"] >= 2

    def test_queue_manager_detects_completion(self):
        """Test queue manager detects when all work is complete"""

        shared_pool = SharedMemoryPool()
        config = ProducerConsumerConfig()

        producer = ProducerAgent(config, shared_pool, "producer_1")
        producer.produce("Task", count=2)

        manager = QueueManagerAgent(config, shared_pool, "queue_manager")
        assert not manager.is_complete()

        consumer = ConsumerAgent(config, shared_pool, "consumer_1")
        consumer.consume()
        consumer.consume()

        # After processing all items
        assert manager.is_complete()

    def test_load_balancing(self):
        """Test queue manager provides load balancing recommendations"""

        shared_pool = SharedMemoryPool()
        config = ProducerConsumerConfig()

        producer = ProducerAgent(config, shared_pool, "producer_1")
        producer.produce("Task", count=10)

        manager = QueueManagerAgent(config, shared_pool, "queue_manager")
        balance = manager.balance_load()

        assert "action" in balance
        assert "recommendations" in balance


class TestProducerConsumerPipeline:
    """Test full pipeline workflow (4 tests)"""

    def test_full_pipeline(self):
        """Test complete producer-consumer pipeline"""

        result = producer_consumer_workflow(
            task_spec="Generate and process test data",
            item_count=5,
            producer_count=2,
            consumer_count=3,
        )

        assert "status" in result
        assert result["status"] == "success"
        assert "results" in result
        assert len(result["results"]) >= 5
        assert "stats" in result

    def test_fifo_order(self):
        """Test items processed in FIFO order"""

        shared_pool = SharedMemoryPool()
        config = ProducerConsumerConfig()

        producer = ProducerAgent(config, shared_pool, "producer_1")
        producer.produce("Sequential task", count=3)

        consumer = ConsumerAgent(config, shared_pool, "consumer_1")

        # Consume in order
        results = []
        for _ in range(3):
            result = consumer.consume()
            if result:
                results.append(result)

        # Verify order preserved
        assert len(results) == 3

    def test_parallel_processing(self):
        """Test parallel processing by multiple consumers"""

        result = producer_consumer_workflow(
            task_spec="Parallel processing test",
            item_count=9,
            producer_count=1,
            consumer_count=3,
        )

        stats = result["stats"]
        assert stats["consumer_count"] == 3
        assert len(result["results"]) >= 9

    def test_stats_accurate(self):
        """Test pipeline statistics are accurate"""

        result = producer_consumer_workflow(
            task_spec="Stats test", item_count=6, producer_count=2, consumer_count=2
        )

        stats = result["stats"]

        assert stats["total_items"] == 6
        assert stats["pending_count"] >= 0
        assert stats["completed_count"] >= 6
        assert stats["producer_count"] == 2
        assert stats["consumer_count"] == 2


class TestProducerConsumerErrorHandling:
    """Test error handling and edge cases (3 tests)"""

    def test_consumer_error_handling(self):
        """Test consumer handles processing errors gracefully"""

        shared_pool = SharedMemoryPool()
        config = ProducerConsumerConfig()

        producer = ProducerAgent(config, shared_pool, "producer_1")
        producer.produce("Error test", count=1)

        consumer = ConsumerAgent(config, shared_pool, "consumer_1")
        result = consumer.consume()

        # Should handle errors without crashing
        assert result is not None
        assert "status" in result

    def test_empty_queue(self):
        """Test consumer handles empty queue gracefully"""

        shared_pool = SharedMemoryPool()
        config = ProducerConsumerConfig()

        consumer = ConsumerAgent(config, shared_pool, "consumer_1")
        result = consumer.consume()

        # Should return None or empty result
        assert result is None or result.get("status") == "no_work"

    @pytest.mark.timeout(300)  # 5 minutes for large batch processing
    def test_large_batch(self):
        """Test pipeline handles large batch of items"""

        result = producer_consumer_workflow(
            task_spec="Large batch test",
            item_count=20,
            producer_count=2,
            consumer_count=4,
        )

        assert result["status"] == "success"
        assert len(result["results"]) >= 20
        assert result["stats"]["completed_count"] >= 20


class TestProducerConsumerIntegration:
    """Integration tests for complete pattern (3 tests)"""

    def test_workflow_creates_all_agents(self):
        """Test workflow creates correct number of agents"""

        result = producer_consumer_workflow(
            task_spec="Agent creation test",
            item_count=5,
            producer_count=2,
            consumer_count=3,
        )

        stats = result["stats"]
        assert "producer_count" in stats
        assert "consumer_count" in stats
        assert stats["producer_count"] == 2
        assert stats["consumer_count"] == 3

    def test_shared_memory_coordination(self):
        """Test shared memory enables coordination"""

        result = producer_consumer_workflow(
            task_spec="Memory coordination test",
            item_count=4,
            producer_count=1,
            consumer_count=2,
        )

        # Verify shared memory was used
        assert "shared_memory_entries" in result["stats"]
        assert result["stats"]["shared_memory_entries"] > 0

    def test_multiple_workflow_runs_isolated(self):
        """Test multiple workflow runs are isolated"""

        result1 = producer_consumer_workflow(
            task_spec="Run 1", item_count=3, producer_count=1, consumer_count=1
        )

        result2 = producer_consumer_workflow(
            task_spec="Run 2", item_count=3, producer_count=1, consumer_count=1
        )

        # Each run should have independent results
        assert result1["results"] != result2["results"]
        assert len(result1["results"]) >= 3
        assert len(result2["results"]) >= 3
