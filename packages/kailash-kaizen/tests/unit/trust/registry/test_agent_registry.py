"""
Unit tests for AgentRegistry.

Tests cover the intent of the registry:
- Trust-verified agent registration
- Capability-based discovery
- Complex discovery queries with ranking
- Status and heartbeat management
- Trust validation during operations

Note: These are unit tests (Tier 1), mocking is allowed.
"""

from datetime import datetime, timedelta, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen.trust.registry.agent_registry import AgentRegistry, DiscoveryQuery
from kaizen.trust.registry.exceptions import (
    AgentNotFoundError,
    TrustVerificationError,
    ValidationError,
)
from kaizen.trust.registry.models import AgentMetadata, AgentStatus, RegistrationRequest
from kaizen.trust.registry.store import InMemoryAgentRegistryStore


class TestAgentRegistryInitialization:
    """Tests for AgentRegistry initialization."""

    def test_requires_trust_ops_when_verify_enabled(self):
        """Registry requires trust_operations when verify_on_registration is True."""
        store = InMemoryAgentRegistryStore()

        with pytest.raises(ValueError) as exc_info:
            AgentRegistry(
                store=store,
                trust_operations=None,
                verify_on_registration=True,
            )

        assert "trust_operations is required" in str(exc_info.value)

    def test_allows_no_trust_ops_when_verify_disabled(self):
        """Registry accepts no trust_operations when verification is disabled."""
        store = InMemoryAgentRegistryStore()

        registry = AgentRegistry(
            store=store,
            trust_operations=None,
            verify_on_registration=False,
        )

        assert registry is not None

    def test_accepts_all_configuration_options(self):
        """Registry accepts all configuration parameters."""
        store = InMemoryAgentRegistryStore()
        trust_ops = MagicMock()

        registry = AgentRegistry(
            store=store,
            trust_operations=trust_ops,
            verify_on_registration=True,
            auto_update_last_seen=False,
            heartbeat_interval=120,
        )

        assert registry._auto_update_last_seen is False
        assert registry._heartbeat_interval == 120


class TestAgentRegistration:
    """Tests for agent registration."""

    @pytest.fixture
    def store(self):
        return InMemoryAgentRegistryStore()

    @pytest.fixture
    def registry(self, store):
        return AgentRegistry(
            store=store,
            trust_operations=None,
            verify_on_registration=False,
        )

    @pytest.mark.asyncio
    async def test_successful_registration(self, registry):
        """Valid registration request creates agent in registry."""
        request = RegistrationRequest(
            agent_id="agent-001",
            agent_type="worker",
            capabilities=["analyze_data"],
            trust_chain_hash="hash123",
            verify_trust=False,
        )

        metadata = await registry.register(request)

        assert metadata.agent_id == "agent-001"
        assert metadata.status == AgentStatus.ACTIVE
        assert metadata.capabilities == ["analyze_data"]

    @pytest.mark.asyncio
    async def test_registration_sets_timestamps(self, registry):
        """Registration sets both registered_at and last_seen."""
        request = RegistrationRequest(
            agent_id="agent-001",
            agent_type="worker",
            capabilities=["task"],
            trust_chain_hash="hash123",
            verify_trust=False,
        )

        before = datetime.now(timezone.utc)
        metadata = await registry.register(request)
        after = datetime.now(timezone.utc)

        assert before <= metadata.registered_at <= after
        assert before <= metadata.last_seen <= after

    @pytest.mark.asyncio
    async def test_invalid_request_raises_validation_error(self, registry):
        """Invalid registration request raises ValidationError."""
        request = RegistrationRequest(
            agent_id="",  # Invalid: empty
            agent_type="worker",
            capabilities=[],  # Invalid: empty
            trust_chain_hash="hash123",
            verify_trust=False,
        )

        with pytest.raises(ValidationError):
            await registry.register(request)

    @pytest.mark.asyncio
    async def test_registration_with_optional_fields(self, registry):
        """Registration preserves optional fields."""
        request = RegistrationRequest(
            agent_id="agent-001",
            agent_type="worker",
            capabilities=["task"],
            constraints=["read_only"],
            metadata={"version": "1.0"},
            trust_chain_hash="hash123",
            endpoint="localhost:8080",
            public_key="ssh-rsa AAAA...",
            verify_trust=False,
        )

        metadata = await registry.register(request)

        assert metadata.constraints == ["read_only"]
        assert metadata.metadata == {"version": "1.0"}
        assert metadata.endpoint == "localhost:8080"
        assert metadata.public_key == "ssh-rsa AAAA..."


class TestTrustVerifiedRegistration:
    """Tests for trust-verified registration."""

    @pytest.fixture
    def mock_trust_ops(self):
        trust_ops = MagicMock()
        trust_ops.verify = AsyncMock()
        trust_ops.get_chain = AsyncMock()
        return trust_ops

    @pytest.fixture
    def store(self):
        return InMemoryAgentRegistryStore()

    @pytest.fixture
    def registry(self, store, mock_trust_ops):
        return AgentRegistry(
            store=store,
            trust_operations=mock_trust_ops,
            verify_on_registration=True,
        )

    @pytest.mark.asyncio
    async def test_trust_verified_registration_success(self, registry, mock_trust_ops):
        """Registration succeeds when trust verification passes."""
        # Setup mock chain with matching capabilities
        mock_chain = MagicMock()
        mock_chain.compute_hash.return_value = "correct_hash"
        mock_attestation = MagicMock()
        mock_attestation.capability = "analyze_data"
        mock_chain.capability_attestations = [mock_attestation]

        mock_trust_ops.verify.return_value = MagicMock(valid=True, reason=None)
        mock_trust_ops.get_chain.return_value = mock_chain

        request = RegistrationRequest(
            agent_id="agent-001",
            agent_type="worker",
            capabilities=["analyze_data"],
            trust_chain_hash="correct_hash",
            verify_trust=True,
        )

        metadata = await registry.register(request)

        assert metadata.agent_id == "agent-001"
        mock_trust_ops.verify.assert_called_once()

    @pytest.mark.asyncio
    async def test_trust_verification_failure_rejects_registration(
        self, registry, mock_trust_ops
    ):
        """Registration fails when trust verification fails."""
        mock_trust_ops.verify.return_value = MagicMock(
            valid=False, reason="Chain revoked"
        )

        request = RegistrationRequest(
            agent_id="agent-001",
            agent_type="worker",
            capabilities=["analyze_data"],
            trust_chain_hash="hash123",
            verify_trust=True,
        )

        with pytest.raises(TrustVerificationError):
            await registry.register(request)

    @pytest.mark.asyncio
    async def test_hash_mismatch_rejects_registration(self, registry, mock_trust_ops):
        """Registration fails when trust chain hash doesn't match."""
        mock_chain = MagicMock()
        mock_chain.compute_hash.return_value = "actual_hash"

        mock_trust_ops.verify.return_value = MagicMock(valid=True, reason=None)
        mock_trust_ops.get_chain.return_value = mock_chain

        request = RegistrationRequest(
            agent_id="agent-001",
            agent_type="worker",
            capabilities=["analyze_data"],
            trust_chain_hash="wrong_hash",
            verify_trust=True,
        )

        with pytest.raises(TrustVerificationError) as exc_info:
            await registry.register(request)

        assert "hash mismatch" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_missing_capability_in_chain_rejects_registration(
        self, registry, mock_trust_ops
    ):
        """Registration fails when requested capability is not in trust chain."""
        mock_chain = MagicMock()
        mock_chain.compute_hash.return_value = "hash123"
        # Chain only has 'read_data' capability, not 'write_data'
        mock_attestation = MagicMock()
        mock_attestation.capability = "read_data"
        mock_chain.capability_attestations = [mock_attestation]

        mock_trust_ops.verify.return_value = MagicMock(valid=True, reason=None)
        mock_trust_ops.get_chain.return_value = mock_chain

        request = RegistrationRequest(
            agent_id="agent-001",
            agent_type="worker",
            capabilities=["write_data"],  # Not in chain
            trust_chain_hash="hash123",
            verify_trust=True,
        )

        with pytest.raises(TrustVerificationError) as exc_info:
            await registry.register(request)

        assert "not in trust chain" in str(exc_info.value).lower()


class TestAgentDiscovery:
    """Tests for agent discovery."""

    @pytest.fixture
    def store(self):
        return InMemoryAgentRegistryStore()

    @pytest.fixture
    def registry(self, store):
        return AgentRegistry(
            store=store,
            trust_operations=None,
            verify_on_registration=False,
        )

    async def register_agent(
        self,
        registry,
        agent_id: str,
        capabilities: List[str],
        agent_type: str = "worker",
        status: AgentStatus = AgentStatus.ACTIVE,
        constraints: List[str] = None,
    ) -> AgentMetadata:
        """Helper to register an agent."""
        request = RegistrationRequest(
            agent_id=agent_id,
            agent_type=agent_type,
            capabilities=capabilities,
            constraints=constraints or [],
            trust_chain_hash="hash123",
            verify_trust=False,
        )
        metadata = await registry.register(request)
        if status != AgentStatus.ACTIVE:
            await registry.update_status(agent_id, status)
        return metadata

    @pytest.mark.asyncio
    async def test_find_by_single_capability(self, registry):
        """Find agents by a single capability."""
        await self.register_agent(registry, "agent-1", ["analyze_data", "export"])
        await self.register_agent(registry, "agent-2", ["analyze_data"])
        await self.register_agent(registry, "agent-3", ["export"])

        results = await registry.find_by_capability("analyze_data")

        assert len(results) == 2
        agent_ids = [a.agent_id for a in results]
        assert "agent-1" in agent_ids
        assert "agent-2" in agent_ids
        assert "agent-3" not in agent_ids

    @pytest.mark.asyncio
    async def test_find_by_capability_filters_inactive(self, registry):
        """Active-only filter excludes non-active agents."""
        await self.register_agent(
            registry, "agent-1", ["task"], status=AgentStatus.ACTIVE
        )
        await self.register_agent(
            registry, "agent-2", ["task"], status=AgentStatus.SUSPENDED
        )

        active_results = await registry.find_by_capability("task", active_only=True)
        all_results = await registry.find_by_capability("task", active_only=False)

        assert len(active_results) == 1
        assert active_results[0].agent_id == "agent-1"
        assert len(all_results) == 2

    @pytest.mark.asyncio
    async def test_find_by_multiple_capabilities_match_all(self, registry):
        """Match-all requires agent to have ALL capabilities."""
        await self.register_agent(registry, "agent-1", ["a", "b", "c"])
        await self.register_agent(registry, "agent-2", ["a", "b"])
        await self.register_agent(registry, "agent-3", ["a"])

        results = await registry.find_by_capabilities(["a", "b"], match_all=True)

        assert len(results) == 2
        agent_ids = [a.agent_id for a in results]
        assert "agent-1" in agent_ids
        assert "agent-2" in agent_ids
        assert "agent-3" not in agent_ids

    @pytest.mark.asyncio
    async def test_find_by_multiple_capabilities_match_any(self, registry):
        """Match-any requires agent to have ANY capability."""
        await self.register_agent(registry, "agent-1", ["a", "b"])
        await self.register_agent(registry, "agent-2", ["c"])
        await self.register_agent(registry, "agent-3", ["d"])

        results = await registry.find_by_capabilities(["a", "c"], match_all=False)

        assert len(results) == 2
        agent_ids = [a.agent_id for a in results]
        assert "agent-1" in agent_ids
        assert "agent-2" in agent_ids
        assert "agent-3" not in agent_ids


class TestDiscoveryQuery:
    """Tests for complex discovery queries."""

    @pytest.fixture
    def store(self):
        return InMemoryAgentRegistryStore()

    @pytest.fixture
    def registry(self, store):
        return AgentRegistry(
            store=store,
            trust_operations=None,
            verify_on_registration=False,
            auto_update_last_seen=False,
        )

    async def register_agent(
        self,
        registry,
        agent_id: str,
        capabilities: List[str],
        agent_type: str = "worker",
        constraints: List[str] = None,
    ) -> AgentMetadata:
        """Helper to register an agent."""
        request = RegistrationRequest(
            agent_id=agent_id,
            agent_type=agent_type,
            capabilities=capabilities,
            constraints=constraints or [],
            trust_chain_hash="hash123",
            verify_trust=False,
        )
        return await registry.register(request)

    @pytest.mark.asyncio
    async def test_discover_filters_by_agent_type(self, registry):
        """Discovery filters by agent type."""
        await self.register_agent(registry, "w1", ["task"], agent_type="worker")
        await self.register_agent(registry, "s1", ["task"], agent_type="supervisor")

        query = DiscoveryQuery(
            capabilities=["task"],
            agent_type="worker",
        )
        results = await registry.discover(query)

        assert len(results) == 1
        assert results[0].agent_id == "w1"

    @pytest.mark.asyncio
    async def test_discover_excludes_constraints(self, registry):
        """Discovery excludes agents with unwanted constraints."""
        await self.register_agent(registry, "a1", ["task"], constraints=[])
        await self.register_agent(
            registry, "a2", ["task"], constraints=["network_access"]
        )
        await self.register_agent(registry, "a3", ["task"], constraints=["read_only"])

        query = DiscoveryQuery(
            capabilities=["task"],
            exclude_constraints=["network_access"],
        )
        results = await registry.discover(query)

        assert len(results) == 2
        agent_ids = [a.agent_id for a in results]
        assert "a1" in agent_ids
        assert "a3" in agent_ids
        assert "a2" not in agent_ids

    @pytest.mark.asyncio
    async def test_discover_filters_by_min_last_seen(self, registry, store):
        """Discovery filters by minimum last_seen timestamp."""
        # Register agents
        await self.register_agent(registry, "recent", ["task"])
        await self.register_agent(registry, "old", ["task"])

        # Manually set old agent's last_seen to the past
        old_agent = await store.get_agent("old")
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        await store.update_last_seen("old", past_time)

        # Query for agents seen in last 30 minutes
        query = DiscoveryQuery(
            capabilities=["task"],
            min_last_seen=datetime.now(timezone.utc) - timedelta(minutes=30),
        )
        results = await registry.discover(query)

        assert len(results) == 1
        assert results[0].agent_id == "recent"

    @pytest.mark.asyncio
    async def test_discover_filters_by_status(self, registry):
        """Discovery filters by agent status."""
        await self.register_agent(registry, "active", ["task"])
        await self.register_agent(registry, "suspended", ["task"])
        await registry.update_status("suspended", AgentStatus.SUSPENDED)

        # Default query (ACTIVE only)
        active_query = DiscoveryQuery(capabilities=["task"])
        active_results = await registry.discover(active_query)

        # Query for suspended
        suspended_query = DiscoveryQuery(
            capabilities=["task"],
            status=AgentStatus.SUSPENDED,
        )
        suspended_results = await registry.discover(suspended_query)

        assert len(active_results) == 1
        assert active_results[0].agent_id == "active"
        assert len(suspended_results) == 1
        assert suspended_results[0].agent_id == "suspended"

    @pytest.mark.asyncio
    async def test_discovery_results_are_ranked(self, registry):
        """Discovery results are ranked by relevance."""
        # Agent with more capability matches should rank higher
        await self.register_agent(registry, "best", ["a", "b", "c"])
        await self.register_agent(registry, "good", ["a", "b"])
        await self.register_agent(registry, "ok", ["a"])

        query = DiscoveryQuery(
            capabilities=["a", "b", "c"],
            match_all=False,
        )
        results = await registry.discover(query)

        # Best match should be first
        assert results[0].agent_id == "best"


class TestHeartbeatAndStatus:
    """Tests for heartbeat and status management."""

    @pytest.fixture
    def store(self):
        return InMemoryAgentRegistryStore()

    @pytest.fixture
    def registry(self, store):
        return AgentRegistry(
            store=store,
            trust_operations=None,
            verify_on_registration=False,
            heartbeat_interval=60,
        )

    @pytest.mark.asyncio
    async def test_heartbeat_updates_last_seen(self, registry, store):
        """Heartbeat updates agent's last_seen timestamp."""
        request = RegistrationRequest(
            agent_id="agent-001",
            agent_type="worker",
            capabilities=["task"],
            trust_chain_hash="hash123",
            verify_trust=False,
        )
        await registry.register(request)

        original = await store.get_agent("agent-001")
        original_last_seen = original.last_seen

        # Small delay to ensure timestamp difference
        import asyncio

        await asyncio.sleep(0.01)

        await registry.heartbeat("agent-001")

        updated = await store.get_agent("agent-001")
        assert updated.last_seen > original_last_seen

    @pytest.mark.asyncio
    async def test_update_status_changes_agent_status(self, registry, store):
        """Update status changes the agent's status."""
        request = RegistrationRequest(
            agent_id="agent-001",
            agent_type="worker",
            capabilities=["task"],
            trust_chain_hash="hash123",
            verify_trust=False,
        )
        await registry.register(request)

        await registry.update_status(
            "agent-001", AgentStatus.SUSPENDED, reason="Manual suspension"
        )

        agent = await store.get_agent("agent-001")
        assert agent.status == AgentStatus.SUSPENDED

    @pytest.mark.asyncio
    async def test_get_stale_agents_finds_inactive_agents(self, registry, store):
        """Stale detection finds agents without recent heartbeats."""
        # Register two agents
        for agent_id in ["fresh", "stale"]:
            request = RegistrationRequest(
                agent_id=agent_id,
                agent_type="worker",
                capabilities=["task"],
                trust_chain_hash="hash123",
                verify_trust=False,
            )
            await registry.register(request)

        # Set stale agent's last_seen to 10 minutes ago
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        await store.update_last_seen("stale", stale_time)

        # Find agents stale after 5 minutes
        stale_agents = await registry.get_stale_agents(timeout=300)

        assert len(stale_agents) == 1
        assert stale_agents[0].agent_id == "stale"


class TestAgentLifecycle:
    """Tests for agent lifecycle operations."""

    @pytest.fixture
    def store(self):
        return InMemoryAgentRegistryStore()

    @pytest.fixture
    def registry(self, store):
        return AgentRegistry(
            store=store,
            trust_operations=None,
            verify_on_registration=False,
        )

    @pytest.mark.asyncio
    async def test_unregister_removes_agent(self, registry, store):
        """Unregister removes agent from registry."""
        request = RegistrationRequest(
            agent_id="agent-001",
            agent_type="worker",
            capabilities=["task"],
            trust_chain_hash="hash123",
            verify_trust=False,
        )
        await registry.register(request)

        await registry.unregister("agent-001")

        result = await registry.get("agent-001")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_retrieves_registered_agent(self, registry):
        """Get retrieves a registered agent's metadata."""
        request = RegistrationRequest(
            agent_id="agent-001",
            agent_type="worker",
            capabilities=["task"],
            trust_chain_hash="hash123",
            verify_trust=False,
        )
        await registry.register(request)

        metadata = await registry.get("agent-001")

        assert metadata is not None
        assert metadata.agent_id == "agent-001"

    @pytest.mark.asyncio
    async def test_get_returns_none_for_unknown_agent(self, registry):
        """Get returns None for non-existent agent."""
        result = await registry.get("unknown-agent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_all_returns_all_agents(self, registry):
        """List all returns all registered agents."""
        for i in range(3):
            request = RegistrationRequest(
                agent_id=f"agent-{i}",
                agent_type="worker",
                capabilities=["task"],
                trust_chain_hash="hash123",
                verify_trust=False,
            )
            await registry.register(request)

        all_agents = await registry.list_all()

        assert len(all_agents) == 3

    @pytest.mark.asyncio
    async def test_list_all_active_only(self, registry):
        """List all with active_only filters by status."""
        request1 = RegistrationRequest(
            agent_id="active",
            agent_type="worker",
            capabilities=["task"],
            trust_chain_hash="hash123",
            verify_trust=False,
        )
        request2 = RegistrationRequest(
            agent_id="suspended",
            agent_type="worker",
            capabilities=["task"],
            trust_chain_hash="hash123",
            verify_trust=False,
        )
        await registry.register(request1)
        await registry.register(request2)
        await registry.update_status("suspended", AgentStatus.SUSPENDED)

        active_agents = await registry.list_all(active_only=True)

        assert len(active_agents) == 1
        assert active_agents[0].agent_id == "active"


class TestTrustValidation:
    """Tests for trust validation operations."""

    @pytest.fixture
    def mock_trust_ops(self):
        trust_ops = MagicMock()
        trust_ops.verify = AsyncMock()
        return trust_ops

    @pytest.fixture
    def store(self):
        return InMemoryAgentRegistryStore()

    @pytest.fixture
    def registry(self, store, mock_trust_ops):
        return AgentRegistry(
            store=store,
            trust_operations=mock_trust_ops,
            verify_on_registration=False,  # Allow registration without verification
        )

    @pytest.mark.asyncio
    async def test_validate_agent_trust_returns_true_when_valid(
        self, registry, mock_trust_ops
    ):
        """Trust validation returns True for valid trust."""
        # Register agent
        request = RegistrationRequest(
            agent_id="agent-001",
            agent_type="worker",
            capabilities=["task"],
            trust_chain_hash="hash123",
            verify_trust=False,
        )
        await registry.register(request)

        mock_trust_ops.verify.return_value = MagicMock(valid=True, reason=None)

        result = await registry.validate_agent_trust("agent-001")

        assert result is True

    @pytest.mark.asyncio
    async def test_validate_agent_trust_revokes_on_invalid(
        self, registry, mock_trust_ops, store
    ):
        """Trust validation revokes agent when trust is invalid."""
        # Register agent
        request = RegistrationRequest(
            agent_id="agent-001",
            agent_type="worker",
            capabilities=["task"],
            trust_chain_hash="hash123",
            verify_trust=False,
        )
        await registry.register(request)

        mock_trust_ops.verify.return_value = MagicMock(
            valid=False, reason="Trust revoked"
        )

        result = await registry.validate_agent_trust("agent-001")

        assert result is False
        agent = await store.get_agent("agent-001")
        assert agent.status == AgentStatus.REVOKED

    @pytest.mark.asyncio
    async def test_validate_returns_true_without_trust_ops(self, store):
        """Trust validation returns True when trust_operations not configured."""
        registry = AgentRegistry(
            store=store,
            trust_operations=None,
            verify_on_registration=False,
        )

        # Register agent
        request = RegistrationRequest(
            agent_id="agent-001",
            agent_type="worker",
            capabilities=["task"],
            trust_chain_hash="hash123",
            verify_trust=False,
        )
        await registry.register(request)

        result = await registry.validate_agent_trust("agent-001")

        # Should return True (assume valid) when trust checking disabled
        assert result is True
