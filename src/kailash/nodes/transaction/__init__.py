"""Transaction management nodes for distributed systems.

This module provides enterprise-grade transaction patterns including:
- Saga pattern for long-running distributed transactions
- Two-phase commit (2PC) for ACID compliance across services
- Distributed transaction manager with automatic pattern selection
- Compensation logic for automatic rollback
- Distributed transaction coordination
- State persistence with multiple storage backends
"""

from .distributed_transaction_manager import (
    AvailabilityLevel,
    ConsistencyLevel,
    DistributedTransactionManagerNode,
    ParticipantCapability,
    TransactionPattern,
    TransactionRequirements,
    TransactionStatus,
)
from .saga_coordinator import SagaCoordinatorNode
from .saga_state_storage import (
    DatabaseStateStorage,
    InMemoryStateStorage,
    RedisStateStorage,
    SagaStateStorage,
    StorageFactory,
)
from .saga_step import SagaStepNode
from .two_phase_commit import TwoPhaseCommitCoordinatorNode

__all__ = [
    "SagaCoordinatorNode",
    "SagaStepNode",
    "TwoPhaseCommitCoordinatorNode",
    "DistributedTransactionManagerNode",
    "ParticipantCapability",
    "TransactionRequirements",
    "TransactionPattern",
    "TransactionStatus",
    "ConsistencyLevel",
    "AvailabilityLevel",
    "SagaStateStorage",
    "InMemoryStateStorage",
    "RedisStateStorage",
    "DatabaseStateStorage",
    "StorageFactory",
]
