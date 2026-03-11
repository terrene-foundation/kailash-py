"""
Trust Orchestration Integration Module.

This module integrates EATP Phase 2 components for comprehensive
trust-aware multi-agent workflows:

- SecureOrchestrationChannel: Secure task delegation over encrypted channels
- RegistryAwareRuntime: Agent registry integration for capability-based selection
- DelegationMessage: Standardized message protocol for workflow delegation

Example:
    from kaizen.trust.orchestration.integration import (
        SecureOrchestrationChannel,
        DelegationMessageType,
        DelegationMessage,
        RegistryAwareRuntime,
    )

    # Create secure orchestration channel
    channel = SecureOrchestrationChannel(
        agent_id="supervisor-001",
        private_key=private_key,
        trust_operations=trust_ops,
        agent_registry=registry,
        replay_protection=replay_protection,
    )

    # Delegate task securely
    result = await channel.delegate_task(
        worker_agent_id="worker-001",
        task=task_definition,
        context=trust_context,
    )
"""

from kaizen.trust.orchestration.integration.registry_aware import (
    AgentSelector,
    CapabilityBasedSelector,
    HealthAwareSelector,
    RegistryAwareRuntime,
)
from kaizen.trust.orchestration.integration.secure_channel import (
    DelegationMessage,
    DelegationMessageType,
    DelegationResult,
    SecureOrchestrationChannel,
)

__all__ = [
    # Secure Channel Integration
    "SecureOrchestrationChannel",
    "DelegationMessageType",
    "DelegationMessage",
    "DelegationResult",
    # Registry Integration
    "RegistryAwareRuntime",
    "AgentSelector",
    "CapabilityBasedSelector",
    "HealthAwareSelector",
]
