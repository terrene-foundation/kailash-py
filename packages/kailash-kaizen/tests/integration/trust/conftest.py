"""
Integration test configuration for EATP trust module.

Provides fixtures for real EATP component testing without mocking.
These tests exercise actual cryptographic operations, trust chains,
and multi-agent coordination.

Test Intent:
- Verify EATP components work together correctly
- Test real cryptographic operations (Ed25519 signing/verification)
- Validate trust chain propagation across agents
- Ensure secure messaging integrity end-to-end
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest
from kaizen.trust import (  # Crypto; Chain; Authority; Operations; Registry; Messaging; Orchestration
    AgentHealthMonitor,
    AgentMetadata,
    AgentRegistry,
    AgentStatus,
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    ConstraintLooseningError,
    ContextMergeStrategy,
    DelegationEntry,
    DiscoveryQuery,
    GenesisRecord,
    HealthStatus,
    InMemoryReplayProtection,
    MessageMetadata,
    OrganizationalAuthority,
    OrganizationalAuthorityRegistry,
    RegistrationRequest,
    ReplayProtection,
    SecureChannel,
    SecureMessageEnvelope,
    TrustAwareOrchestrationRuntime,
    TrustAwareRuntimeConfig,
    TrustExecutionContext,
    TrustKeyManager,
    TrustLineageChain,
    TrustOperations,
    TrustPolicy,
    TrustPolicyEngine,
    VerificationLevel,
    VerificationResult,
    generate_keypair,
    sign,
    verify_signature,
)
from kaizen.trust.orchestration.integration.registry_aware import (
    CapabilityBasedSelector,
    HealthAwareSelector,
    RegistryAwareRuntime,
    RegistryAwareRuntimeConfig,
    RoundRobinSelector,
)

# Note: NO MOCKING in integration tests - use real implementations
from kaizen.trust.orchestration.integration.secure_channel import (
    DelegationMessage,
    DelegationMessageType,
    DelegationResult,
    SecureOrchestrationChannel,
)
from kaizen.trust.registry.store import InMemoryAgentRegistryStore


class TestAgent:
    """
    Test agent for integration testing.

    Simulates an agent with keys, trust chain, and capabilities
    for exercising EATP components.
    """

    def __init__(
        self,
        agent_id: str,
        capabilities: List[str],
        parent_agent_id: Optional[str] = None,
    ):
        self.agent_id = agent_id
        self.capabilities = capabilities
        self.parent_agent_id = parent_agent_id

        # Generate real keypair (returns base64-encoded strings)
        self.private_key, self.public_key = generate_keypair()

        # Track executed tasks
        self.executed_tasks: List[Dict[str, Any]] = []

    async def execute_task(
        self,
        task: Any,
        context: TrustExecutionContext,
    ) -> Dict[str, Any]:
        """Execute a task and return results."""
        self.executed_tasks.append(
            {
                "task": task,
                "context_id": context.context_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return {
            "status": "completed",
            "agent_id": self.agent_id,
            "task": task,
            "result": f"Processed by {self.agent_id}",
        }


@pytest.fixture
def test_keypair():
    """Generate a test keypair."""
    return generate_keypair()


class InMemoryTrustStore:
    """
    In-memory trust store for integration testing.

    Provides a real implementation that stores trust chains in memory
    instead of requiring PostgreSQL. NO MOCKING - real operations.
    """

    def __init__(self):
        self._chains: Dict[str, TrustLineageChain] = {}
        self._initialized = False

    async def initialize(self) -> None:
        self._initialized = True

    async def store_chain(
        self, chain: TrustLineageChain, expires_at: Optional[datetime] = None
    ) -> str:
        agent_id = chain.genesis.agent_id
        self._chains[agent_id] = chain
        return agent_id

    async def get_chain(
        self, agent_id: str, include_inactive: bool = False
    ) -> Optional[TrustLineageChain]:
        return self._chains.get(agent_id)

    async def update_chain(self, chain: TrustLineageChain) -> None:
        agent_id = chain.genesis.agent_id
        self._chains[agent_id] = chain

    async def delete_chain(self, agent_id: str) -> bool:
        if agent_id in self._chains:
            del self._chains[agent_id]
            return True
        return False

    async def list_chains_by_authority(
        self, authority_id: str
    ) -> List[TrustLineageChain]:
        return [
            c for c in self._chains.values() if c.genesis.authority_id == authority_id
        ]

    async def list_chains(
        self, authority_id: str = None, **kwargs
    ) -> List[TrustLineageChain]:
        """List all chains, optionally filtered by authority."""
        if authority_id:
            return [
                c
                for c in self._chains.values()
                if c.genesis.authority_id == authority_id
            ]
        return list(self._chains.values())

    async def close(self) -> None:
        self._chains.clear()


@pytest.fixture
def trust_store():
    """Create in-memory trust store for testing - NO MOCKING."""
    return InMemoryTrustStore()


@pytest.fixture
def key_manager():
    """Create trust key manager."""
    return TrustKeyManager()


@pytest.fixture
def authority_registry():
    """Create organizational authority registry."""
    return OrganizationalAuthorityRegistry()


@pytest.fixture
def trust_operations(authority_registry, key_manager, trust_store):
    """Create configured trust operations."""
    return TrustOperations(
        authority_registry=authority_registry,
        key_manager=key_manager,
        trust_store=trust_store,
    )


@pytest.fixture
def agent_registry():
    """Create agent registry with in-memory store (no trust verification for testing)."""
    store = InMemoryAgentRegistryStore()
    return AgentRegistry(store=store, verify_on_registration=False)


@pytest.fixture
def health_monitor(agent_registry):
    """Create health monitor with the agent registry."""
    return AgentHealthMonitor(
        registry=agent_registry,
        check_interval=60,
        stale_timeout=300,
    )


@pytest.fixture
def replay_protection():
    """Create replay protection."""
    return InMemoryReplayProtection()


@pytest.fixture
def supervisor_agent():
    """Create supervisor test agent."""
    return TestAgent(
        agent_id="supervisor-001",
        capabilities=["delegate", "analyze", "report", "manage"],
    )


@pytest.fixture
def worker_agents():
    """Create worker test agents."""
    return [
        TestAgent(
            agent_id="analyzer-001",
            capabilities=["analyze", "read_data"],
            parent_agent_id="supervisor-001",
        ),
        TestAgent(
            agent_id="reporter-001",
            capabilities=["report", "write_data"],
            parent_agent_id="supervisor-001",
        ),
        TestAgent(
            agent_id="processor-001",
            capabilities=["process", "transform_data"],
            parent_agent_id="supervisor-001",
        ),
    ]


@pytest.fixture
async def populated_registry(agent_registry, supervisor_agent, worker_agents):
    """Registry populated with test agents."""
    # Register supervisor
    await agent_registry.register(
        RegistrationRequest(
            agent_id=supervisor_agent.agent_id,
            agent_type="supervisor",
            capabilities=supervisor_agent.capabilities,
            constraints=[],
            trust_chain_hash="test-hash",
            public_key=supervisor_agent.public_key,
            metadata={"role": "supervisor"},
            verify_trust=False,
        )
    )

    # Register workers
    for worker in worker_agents:
        await agent_registry.register(
            RegistrationRequest(
                agent_id=worker.agent_id,
                agent_type="worker",
                capabilities=worker.capabilities,
                constraints=[],
                trust_chain_hash="test-hash",
                public_key=worker.public_key,
                metadata={"role": "worker"},
                verify_trust=False,
            )
        )

    return agent_registry


@pytest.fixture
async def healthy_agents(
    populated_registry, health_monitor, supervisor_agent, worker_agents
):
    """Health monitor with all agents healthy.

    Agents are healthy when they have recent heartbeats in the registry.
    The populated_registry fixture ensures agents are registered first.
    """
    # Send heartbeats for all agents to make them healthy
    await populated_registry.heartbeat(supervisor_agent.agent_id)
    for worker in worker_agents:
        await populated_registry.heartbeat(worker.agent_id)

    return health_monitor


@pytest.fixture
def supervisor_context(supervisor_agent):
    """Execution context for supervisor."""
    return TrustExecutionContext.create(
        parent_agent_id=supervisor_agent.agent_id,
        task_id="integration-test",
        delegated_capabilities=[
            "analyze",
            "report",
            "process",
            "read_data",
            "write_data",
        ],
        inherited_constraints={"max_records": 10000},
    )


@pytest.fixture
def trust_runtime(trust_operations, agent_registry):
    """Create trust-aware orchestration runtime.

    Note: verify_before_execution=False for these tests because the full
    trust verification depends on TrustOperations.get_chain which requires
    a complete trust store with established chains. These tests focus on
    workflow orchestration functionality.
    """
    return TrustAwareOrchestrationRuntime(
        trust_operations=trust_operations,
        agent_registry=agent_registry,  # Use sync fixture
        config=TrustAwareRuntimeConfig(
            verify_before_execution=False,  # Disable full trust verification
            audit_after_execution=False,
            enable_policy_engine=False,
        ),
    )


@pytest.fixture
def registry_aware_runtime(
    trust_operations,
    agent_registry,
    health_monitor,
):
    """Create registry-aware runtime with health monitoring.

    Note: verify_before_execution=False for these tests because the full
    trust verification depends on TrustOperations.get_chain which requires
    a complete trust store with established chains. These tests focus on
    registry-aware workflow orchestration functionality.
    """
    return RegistryAwareRuntime(
        trust_operations=trust_operations,
        agent_registry=agent_registry,  # Use sync fixture
        health_monitor=health_monitor,  # Use sync fixture
        config=RegistryAwareRuntimeConfig(
            auto_discover_agents=True,
            health_aware_selection=True,
            min_health_status=HealthStatus.HEALTHY,
            verify_before_execution=False,  # Disable full trust verification
            audit_after_execution=False,
            enable_policy_engine=False,
        ),
    )


@pytest.fixture
def supervisor_channel(
    supervisor_agent,
    trust_operations,
    populated_registry,
    replay_protection,
):
    """Create secure orchestration channel for supervisor."""
    return SecureOrchestrationChannel(
        agent_id=supervisor_agent.agent_id,
        private_key=supervisor_agent.private_key,
        trust_operations=trust_operations,
        agent_registry=populated_registry,
        replay_protection=replay_protection,
        auto_audit=True,
    )


@pytest.fixture
def worker_channels(
    worker_agents,
    trust_operations,
    populated_registry,
    replay_protection,
):
    """Create secure orchestration channels for workers."""
    return [
        SecureOrchestrationChannel(
            agent_id=worker.agent_id,
            private_key=worker.private_key,
            trust_operations=trust_operations,
            agent_registry=populated_registry,
            replay_protection=replay_protection,
            auto_audit=True,
        )
        for worker in worker_agents
    ]
