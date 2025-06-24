"""Actor-based components for Kailash SDK.

This module provides actor-based patterns for improved fault tolerance
and isolation in distributed systems.
"""

from .connection_actor import ActorConnection, ConnectionActor, ConnectionState
from .supervisor import ActorSupervisor, SupervisionStrategy

__all__ = [
    "ActorConnection",
    "ConnectionState",
    "ConnectionActor",
    "ActorSupervisor",
    "SupervisionStrategy",
]
