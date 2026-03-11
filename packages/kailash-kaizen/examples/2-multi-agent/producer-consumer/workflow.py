"""
Producer-Consumer Multi-Agent Pattern.

This example demonstrates pipeline processing with queue management using
SharedMemoryPool from Phase 2 (Week 3). Producers generate work items, consumers
process them, and a queue manager handles coordination and load balancing.

Agents:
1. ProducerAgent (multiple instances) - Generate work items
2. ConsumerAgent (multiple instances) - Process work items
3. QueueManagerAgent - Manages work queue and load balancing

Key Features:
- Pipeline processing with work queues
- FIFO queue semantics
- Parallel consumer processing
- Load balancing across consumers
- Queue statistics and monitoring
- Error handling and recovery

Architecture:
    ProducerAgent(s) generate items
         |
         v (write to SharedMemoryPool)
    SharedMemoryPool ["work", "pending", "queue"]
         |
         v (consumers read FIFO)
    ConsumerAgent(s) (process in parallel)
         |
         v (write results to SharedMemoryPool)
    SharedMemoryPool ["work", "completed", "results"]
         |
         v (manager monitors)
    QueueManagerAgent (tracks stats, balancing)
         |
         v
    Final Results + Statistics

Use Cases:
- Data pipeline processing
- Batch job processing
- Work queue management
- Producer-consumer patterns
- Stream processing

Author: Kaizen Framework Team
Created: 2025-10-02 (Phase 5, Task 5E.1)
Reference: Classic producer-consumer pattern with shared memory
"""

import json
import time
import uuid
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField, Signature

# Signature definitions


class ProductionSignature(Signature):
    """Signature for producer work item generation."""

    task_spec: str = InputField(desc="What to produce")
    count: int = InputField(desc="Number of items to produce", default=1)

    item: str = OutputField(desc="Produced work item")
    item_id: str = OutputField(desc="Unique item ID")


class ConsumptionSignature(Signature):
    """Signature for consumer work processing."""

    item: str = InputField(desc="Work item to process")
    item_id: str = InputField(desc="Item identifier")

    result: str = OutputField(desc="Processing result")
    status: str = OutputField(desc="success/error", default="success")


class QueueManagementSignature(Signature):
    """Signature for queue manager coordination."""

    queue_stats: str = InputField(desc="Current queue statistics (JSON)")

    action: str = OutputField(desc="Management action", default="monitor")
    load_balance: str = OutputField(
        desc="Load balancing recommendations", default="balanced"
    )


# Configuration


class ProducerConsumerConfig(BaseAgentConfig):
    """Configuration for producer-consumer pattern."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"
    queue_segment: str = "queue"
    results_segment: str = "results"


# Agent implementations


class ProducerAgent(BaseAgent):
    """
    ProducerAgent: Generates work items for the pipeline.

    Responsibilities:
    - Generate work items based on task specification
    - Assign unique IDs to items
    - Write items to shared memory queue
    - Support multiple concurrent producers

    Shared Memory Behavior:
    - Writes items with tags: ["work", "pending"]
    - Segment: "queue"
    - Importance: 0.7 (moderate - work items)
    - Metadata: item_id, producer_id, timestamp
    """

    def __init__(
        self,
        config: ProducerConsumerConfig,
        shared_memory: SharedMemoryPool,
        agent_id: str,
    ):
        """
        Initialize ProducerAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for coordination
            agent_id: Unique identifier for this producer
        """
        super().__init__(
            config=config,
            signature=ProductionSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )
        self.config = config

    def produce(self, task_spec: str, count: int = 1) -> List[Dict[str, Any]]:
        """
        Produce work items.

        Args:
            task_spec: Specification of what to produce
            count: Number of items to produce

        Returns:
            List of produced items with IDs
        """
        items = []

        for i in range(count):
            # Generate unique item ID
            item_id = f"item_{uuid.uuid4().hex[:8]}"

            # Execute production via base agent
            result = self.run(
                task_spec=task_spec, count=1, session_id=f"produce_{item_id}"
            )

            # Extract item
            item = result.get("item", f"Work item {i+1} for: {task_spec}")

            # Write to shared memory queue
            if self.shared_memory:
                self.shared_memory.write_insight(
                    {
                        "agent_id": self.agent_id,
                        "content": item,
                        "tags": ["work", "pending"],
                        "importance": 0.7,
                        "segment": self.config.queue_segment,
                        "metadata": {
                            "item_id": item_id,
                            "item": item,
                            "producer_id": self.agent_id,
                            "timestamp": time.time(),
                            "status": "pending",
                        },
                    }
                )

            items.append({"item_id": item_id, "item": item, "producer": self.agent_id})

        return items


class ConsumerAgent(BaseAgent):
    """
    ConsumerAgent: Processes work items from the queue.

    Responsibilities:
    - Read work items from queue (FIFO)
    - Process items independently
    - Write results to shared memory
    - Handle errors gracefully
    - Support parallel processing

    Shared Memory Behavior:
    - Reads items with tags: ["work", "pending"]
    - Writes results with tags: ["work", "completed"]
    - Segment: "results"
    - Importance: 0.8 (high - completed work)
    - Metadata: item_id, consumer_id, status, timestamp
    """

    def __init__(
        self,
        config: ProducerConsumerConfig,
        shared_memory: SharedMemoryPool,
        agent_id: str,
    ):
        """
        Initialize ConsumerAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for coordination
            agent_id: Unique identifier for this consumer
        """
        super().__init__(
            config=config,
            signature=ConsumptionSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )
        self.config = config
        self.processed_items = set()  # Track processed items to avoid duplicates

    def consume(self) -> Optional[Dict[str, Any]]:
        """
        Consume and process next work item from queue.

        Returns:
            Processing result or None if queue is empty
        """
        if not self.shared_memory:
            return None

        # Read pending work items (FIFO - oldest first)
        pending_items = self.shared_memory.read_relevant(
            agent_id=self.agent_id,
            tags=["work", "pending"],
            segments=[self.config.queue_segment],
            exclude_own=False,  # Read items from all agents
            limit=100,
        )

        if not pending_items:
            return {"status": "no_work", "item": None, "result": None}

        # Find first unprocessed item
        work_item = None
        for item_memory in pending_items:
            metadata = item_memory.get("metadata", {})
            item_id = metadata.get("item_id")
            if item_id and item_id not in self.processed_items:
                work_item = item_memory
                break

        if not work_item:
            return {"status": "no_work", "item": None, "result": None}

        # Extract item details
        metadata = work_item.get("metadata", {})
        item_id = metadata.get("item_id")
        item_content = metadata.get("item", work_item.get("content", ""))

        # Mark as processed
        self.processed_items.add(item_id)

        # Process item via base agent
        try:
            result = self.run(
                item=item_content, item_id=item_id, session_id=f"consume_{item_id}"
            )

            status = result.get("status", "success")
            processing_result = result.get("result", f"Processed: {item_content}")

        except Exception as e:
            status = "error"
            processing_result = f"Error processing item: {str(e)}"

        # Write result to shared memory
        if self.shared_memory:
            self.shared_memory.write_insight(
                {
                    "agent_id": self.agent_id,
                    "content": processing_result,
                    "tags": ["work", "completed"],
                    "importance": 0.8,
                    "segment": self.config.results_segment,
                    "metadata": {
                        "item_id": item_id,
                        "original_item": item_content,
                        "result": processing_result,
                        "consumer_id": self.agent_id,
                        "status": status,
                        "timestamp": time.time(),
                    },
                }
            )

        return {
            "item_id": item_id,
            "item": item_content,
            "result": processing_result,
            "status": status,
            "consumer": self.agent_id,
        }


class QueueManagerAgent(BaseAgent):
    """
    QueueManagerAgent: Manages queue and coordinates load balancing.

    Responsibilities:
    - Track queue statistics
    - Monitor pending and completed work
    - Provide load balancing recommendations
    - Detect completion status
    - Report system health

    Shared Memory Behavior:
    - Reads ALL insights (monitoring)
    - Does NOT write to shared memory
    - Monitors segments: "queue", "results"
    """

    def __init__(
        self,
        config: ProducerConsumerConfig,
        shared_memory: SharedMemoryPool,
        agent_id: str,
    ):
        """
        Initialize QueueManagerAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for coordination
            agent_id: Unique identifier for this manager
        """
        super().__init__(
            config=config,
            signature=QueueManagementSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )
        self.config = config

    def get_queue_stats(self) -> Dict[str, Any]:
        """
        Get current queue statistics.

        Returns:
            Dictionary with queue statistics
        """
        if not self.shared_memory:
            return {"pending_count": 0, "completed_count": 0, "total_items": 0}

        # Count pending items
        pending = self.shared_memory.read_relevant(
            agent_id=self.agent_id,
            tags=["work", "pending"],
            segments=[self.config.queue_segment],
            exclude_own=False,
            limit=1000,
        )

        # Count completed items
        completed = self.shared_memory.read_relevant(
            agent_id=self.agent_id,
            tags=["work", "completed"],
            segments=[self.config.results_segment],
            exclude_own=False,
            limit=1000,
        )

        # Extract unique item IDs to avoid double counting
        pending_ids = set()
        for item in pending:
            metadata = item.get("metadata", {})
            item_id = metadata.get("item_id")
            if item_id:
                pending_ids.add(item_id)

        completed_ids = set()
        for item in completed:
            metadata = item.get("metadata", {})
            item_id = metadata.get("item_id")
            if item_id:
                completed_ids.add(item_id)

        # Remove completed items from pending (they're no longer pending)
        truly_pending = pending_ids - completed_ids

        return {
            "pending_count": len(truly_pending),
            "completed_count": len(completed_ids),
            "total_items": len(pending_ids),  # Total unique items ever in queue
            "pending_ids": list(truly_pending),
            "completed_ids": list(completed_ids),
        }

    def is_complete(self) -> bool:
        """
        Check if all work is complete.

        Returns:
            True if no pending items and has completed items, False otherwise
        """
        stats = self.get_queue_stats()
        return stats["pending_count"] == 0 and stats["completed_count"] > 0

    def balance_load(self) -> Dict[str, Any]:
        """
        Provide load balancing recommendations.

        Returns:
            Load balancing recommendations
        """
        stats = self.get_queue_stats()

        # Execute management via base agent
        result = self.run(
            queue_stats=json.dumps(stats), session_id=f"balance_{uuid.uuid4().hex[:8]}"
        )

        recommendations = []

        # Generate recommendations based on queue state
        if stats["pending_count"] > 10:
            recommendations.append("High queue depth - consider adding consumers")
        elif stats["pending_count"] > 0:
            recommendations.append("Normal queue depth - current consumers sufficient")
        else:
            recommendations.append("Queue empty - all work processed")

        return {
            "action": result.get("action", "monitor"),
            "recommendations": recommendations,
            "stats": stats,
        }


# Workflow function


def producer_consumer_workflow(
    task_spec: str,
    item_count: int = 5,
    producer_count: int = 2,
    consumer_count: int = 3,
) -> Dict[str, Any]:
    """
    Run producer-consumer multi-agent workflow.

    This workflow demonstrates pipeline processing with queue management:
    1. ProducerAgents generate work items
    2. Items are written to SharedMemoryPool queue
    3. ConsumerAgents read and process items in parallel (FIFO)
    4. Consumers write results to SharedMemoryPool
    5. QueueManagerAgent monitors queue and provides statistics
    6. Return all results with statistics

    Args:
        task_spec: Specification of work to produce
        item_count: Total number of items to produce
        producer_count: Number of producer agents
        consumer_count: Number of consumer agents

    Returns:
        Dictionary containing:
        - task_spec: Original task specification
        - items_produced: Items generated
        - results: Processing results
        - stats: Queue and shared memory statistics
        - status: Workflow completion status
    """
    # Setup shared memory pool
    shared_pool = SharedMemoryPool()
    config = ProducerConsumerConfig()

    # Create agents
    producers = []
    for i in range(producer_count):
        producer = ProducerAgent(
            config=config, shared_memory=shared_pool, agent_id=f"producer_{i+1}"
        )
        producers.append(producer)

    consumers = []
    for i in range(consumer_count):
        consumer = ConsumerAgent(
            config=config, shared_memory=shared_pool, agent_id=f"consumer_{i+1}"
        )
        consumers.append(consumer)

    manager = QueueManagerAgent(
        config=config, shared_memory=shared_pool, agent_id="queue_manager"
    )

    print(f"\n{'='*60}")
    print(f"Producer-Consumer Pattern: {task_spec}")
    print(f"{'='*60}\n")

    # Step 1: Producers generate items
    print(f"Step 1: Producers generating {item_count} items...")
    all_items = []
    items_per_producer = item_count // producer_count
    remainder = item_count % producer_count

    for i, producer in enumerate(producers):
        count = items_per_producer + (1 if i < remainder else 0)
        if count > 0:
            items = producer.produce(task_spec, count=count)
            all_items.extend(items)
            print(f"  - {producer.agent_id}: produced {len(items)} items")

    # Step 2: Queue manager checks queue
    print("\nStep 2: Queue manager checking queue status...")
    stats = manager.get_queue_stats()
    print(f"  - Pending items: {stats['pending_count']}")
    print(f"  - Completed items: {stats['completed_count']}")

    # Step 3: Consumers process items
    print("\nStep 3: Consumers processing items...")
    all_results = []

    # Each consumer processes items until queue is empty
    max_iterations = item_count + 5  # Safety limit
    iteration = 0

    while not manager.is_complete() and iteration < max_iterations:
        for consumer in consumers:
            result = consumer.consume()
            if result and result["status"] not in ["no_work"]:
                all_results.append(result)
                print(f"  - {consumer.agent_id}: processed item {result['item_id']}")

        iteration += 1

    # Step 4: Queue manager final stats
    print("\nStep 4: Queue manager final statistics...")
    final_stats = manager.get_queue_stats()
    print(f"  - Total items processed: {final_stats['completed_count']}")
    print(f"  - Items remaining: {final_stats['pending_count']}")

    balance = manager.balance_load()
    print(f"  - Load balancing: {balance['recommendations']}")

    # Show shared memory stats
    memory_stats = shared_pool.get_stats()
    print(f"\n{'='*60}")
    print("Shared Memory Statistics:")
    print(f"{'='*60}")
    print(f"  - Total insights: {memory_stats['insight_count']}")
    print(f"  - Agents involved: {memory_stats['agent_count']}")
    print(f"  - Tag distribution: {memory_stats['tag_distribution']}")
    print(f"  - Segment distribution: {memory_stats['segment_distribution']}")
    print(f"{'='*60}\n")

    return {
        "task_spec": task_spec,
        "items_produced": all_items,
        "results": all_results,
        "stats": {
            **memory_stats,
            "total_items": item_count,
            "pending_count": final_stats["pending_count"],
            "completed_count": final_stats["completed_count"],
            "producer_count": producer_count,
            "consumer_count": consumer_count,
            "shared_memory_entries": memory_stats["insight_count"],
        },
        "status": "success" if manager.is_complete() else "incomplete",
    }


# Main execution
if __name__ == "__main__":
    # Run example workflow
    result = producer_consumer_workflow(
        task_spec="Generate and process customer data records",
        item_count=10,
        producer_count=2,
        consumer_count=3,
    )

    print("\nWorkflow Complete!")
    print(f"Task: {result['task_spec']}")
    print(f"Items produced: {len(result['items_produced'])}")
    print(f"Items processed: {len(result['results'])}")
    print(f"Status: {result['status']}")
