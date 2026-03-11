"""Producer-Consumer Multi-Agent Pattern Example."""

from .workflow import (
    ConsumerAgent,
    ProducerAgent,
    ProducerConsumerConfig,
    QueueManagerAgent,
    producer_consumer_workflow,
)

__all__ = [
    "ProducerAgent",
    "ConsumerAgent",
    "QueueManagerAgent",
    "ProducerConsumerConfig",
    "producer_consumer_workflow",
]
