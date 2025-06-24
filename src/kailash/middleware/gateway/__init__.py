"""Durable gateway implementation for production-grade request handling.

This module provides:
- Request durability with checkpointing
- Automatic deduplication
- Event sourcing for full auditability
- Long-running request support
"""

from .checkpoint_manager import CheckpointManager
from .deduplicator import RequestDeduplicator
from .durable_request import DurableRequest, RequestState
from .event_store import EventStore, RequestEvent

__all__ = [
    "DurableRequest",
    "RequestState",
    "CheckpointManager",
    "RequestDeduplicator",
    "EventStore",
    "RequestEvent",
]
