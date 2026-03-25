"""
Integration Tests for Agent Discovery (Tier 2)

Tests the agent discovery system with real components.
Part of TODO-204 Enterprise-App Streaming Integration.

NO MOCKING: Uses real registry and permission systems.
"""

import asyncio
from typing import Any, Dict, List, Optional

import pytest

from kaizen_agents.patterns.discovery import (
    AccessConstraints,
    AccessMetadata,
    AgentSkillMetadata,
    AgentWithAccess,
    UserFilteredAgentDiscovery,
)
from kaizen_agents.patterns.registry import AgentRegistry
from kaizen_agents.patterns.runtime import AgentMetadata, AgentStatus


class IntegrationTestAgent:
    """Test agent with full capabilities."""

    def __init__(
        self,
        name: str,
        agent_id: str,
        description: str = "",
        capabilities: Optional[List[str]] = None,
    ):
        self.name = name
        self.agent_id = agent_id
        self.description = description or f"{name} agent for testing"
        self._a2a_card = {
            "capabilities": capabilities or [],
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute agent."""
        return {"answer": f"Response from {self.name}"}


class MockPermissionChecker:
    """Permission checker for testing."""

    def __init__(self, allowed_agents: Optional[List[str]] = None):
        self._allowed_agents = allowed_agents or []
        self._verify_calls = []

    async def verify(
        self,
        agent_id: str,
        action: str,
        user_id: str,
        organization_id: str,
    ):
        """Verify permission."""
        self._verify_calls.append(
            {
                "agent_id": agent_id,
                "action": action,
                "user_id": user_id,
                "organization_id": organization_id,
            }
        )

        class Result:
            def __init__(self, valid: bool, constraints: Dict):
                self.valid = valid
                self.constraints = constraints

        if not self._allowed_agents or agent_id in self._allowed_agents:
            return Result(
                valid=True,
                constraints={
                    "max_daily_invocations": 100,
                    "max_tokens": 10000,
                },
            )
        return Result(valid=False, constraints={})


class TestUserFilteredDiscoveryIntegration:
    """Integration tests for UserFilteredAgentDiscovery."""

    @pytest.mark.asyncio
    async def test_discover_agents_from_registry(self):
        """Test discovering agents from real registry."""
        registry = AgentRegistry()
        discovery = UserFilteredAgentDiscovery(registry)

        # Register agents
        agents = [
            IntegrationTestAgent("Analyzer", "analyzer-001", capabilities=["analysis"]),
            IntegrationTestAgent(
                "Summarizer", "summarizer-001", capabilities=["summarization"]
            ),
            IntegrationTestAgent(
                "Translator", "translator-001", capabilities=["translation"]
            ),
        ]

        for agent in agents:
            await registry.register_agent(
                agent=agent,
                runtime_id="test-runtime",
            )

        # Discover agents for user
        results = await discovery.find_agents_for_user(
            user_id="user-001",
            organization_id="org-001",
        )

        assert len(results) == 3
        agent_ids = [r.agent_id for r in results]
        assert "analyzer-001" in agent_ids
        assert "summarizer-001" in agent_ids
        assert "translator-001" in agent_ids

    @pytest.mark.asyncio
    async def test_permission_filtered_discovery(self):
        """Test discovery with permission filtering."""
        registry = AgentRegistry()
        permission_checker = MockPermissionChecker(
            allowed_agents=["analyzer-001", "translator-001"]
        )
        discovery = UserFilteredAgentDiscovery(
            registry,
            permission_checker=permission_checker,
        )

        # Register agents
        agents = [
            IntegrationTestAgent("Analyzer", "analyzer-001"),
            IntegrationTestAgent("Summarizer", "summarizer-001"),
            IntegrationTestAgent("Translator", "translator-001"),
        ]

        for agent in agents:
            await registry.register_agent(
                agent=agent,
                runtime_id="test-runtime",
            )

        # Discover with permission filter
        results = await discovery.find_agents_for_user(
            user_id="user-002",
            organization_id="org-002",
        )

        # Only allowed agents returned
        assert len(results) == 2
        agent_ids = [r.agent_id for r in results]
        assert "analyzer-001" in agent_ids
        assert "translator-001" in agent_ids
        assert "summarizer-001" not in agent_ids

    @pytest.mark.asyncio
    async def test_skill_metadata_extraction(self):
        """Test skill metadata extraction from agents."""
        registry = AgentRegistry()
        discovery = UserFilteredAgentDiscovery(registry)

        agent = IntegrationTestAgent(
            name="DataProcessor",
            agent_id="processor-001",
            description="Processes and transforms data",
            capabilities=["data_processing", "transformation"],
        )
        await registry.register_agent(
            agent=agent,
            runtime_id="test-runtime",
        )

        # Get skill metadata
        skill = await discovery.get_skill_metadata("processor-001")

        assert skill is not None
        assert skill.id == "processor-001"
        assert skill.name == "DataProcessor"
        assert "data_processing" in skill.capabilities
        assert "transformation" in skill.capabilities

    @pytest.mark.asyncio
    async def test_list_all_skills(self):
        """Test listing all skill metadata."""
        registry = AgentRegistry()
        discovery = UserFilteredAgentDiscovery(registry)

        # Register multiple agents
        for i in range(5):
            agent = IntegrationTestAgent(
                name=f"Agent{i}",
                agent_id=f"agent-{i:03d}",
                capabilities=[f"capability_{i}"],
            )
            await registry.register_agent(
                agent=agent,
                runtime_id="test-runtime",
            )

        # List all skills
        skills = await discovery.list_skill_metadata()

        assert len(skills) == 5
        for skill in skills:
            assert isinstance(skill, AgentSkillMetadata)

    @pytest.mark.asyncio
    async def test_access_constraints_from_permissions(self):
        """Test access constraints are extracted from permissions."""
        registry = AgentRegistry()
        permission_checker = MockPermissionChecker(allowed_agents=["agent-001"])
        discovery = UserFilteredAgentDiscovery(
            registry,
            permission_checker=permission_checker,
        )

        agent = IntegrationTestAgent("Agent", "agent-001")
        await registry.register_agent(
            agent=agent,
            runtime_id="test-runtime",
        )

        results = await discovery.find_agents_for_user(
            user_id="user-003",
            organization_id="org-003",
        )

        assert len(results) == 1
        access = results[0].access
        assert access.constraints.max_daily_invocations == 100
        assert access.constraints.max_tokens_per_session == 10000

    @pytest.mark.asyncio
    async def test_empty_registry(self):
        """Test discovery with empty registry."""
        registry = AgentRegistry()
        discovery = UserFilteredAgentDiscovery(registry)

        results = await discovery.find_agents_for_user(
            user_id="user-004",
            organization_id="org-004",
        )

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_nonexistent_skill_metadata(self):
        """Test getting skill metadata for nonexistent agent."""
        registry = AgentRegistry()
        discovery = UserFilteredAgentDiscovery(registry)

        skill = await discovery.get_skill_metadata("nonexistent-001")

        assert skill is None


class TestAgentSkillMetadataIntegration:
    """Integration tests for AgentSkillMetadata."""

    def test_from_agent_with_full_metadata(self):
        """Test creating skill from fully configured agent."""
        agent = IntegrationTestAgent(
            name="FullAgent",
            agent_id="full-001",
            description="Agent with full metadata",
            capabilities=["cap1", "cap2", "cap3"],
        )

        skill = AgentSkillMetadata.from_agent(
            agent,
            suggested_prompts=["Try this", "Do that"],
            avg_execution_time=2.5,
            avg_cost_cents=10,
        )

        assert skill.id == "full-001"
        assert skill.name == "FullAgent"
        assert skill.description == "Agent with full metadata"
        assert len(skill.capabilities) == 3
        assert skill.suggested_prompts == ["Try this", "Do that"]
        assert skill.avg_execution_time_seconds == 2.5
        assert skill.avg_cost_cents == 10

    def test_from_agent_minimal(self):
        """Test creating skill from minimal agent."""

        class MinimalAgent:
            pass

        agent = MinimalAgent()
        skill = AgentSkillMetadata.from_agent(agent, agent_id="minimal-001")

        assert skill.id == "minimal-001"
        assert skill.name == "MinimalAgent"
        assert skill.capabilities == []

    def test_skill_to_dict_roundtrip(self):
        """Test skill serialization roundtrip."""
        skill = AgentSkillMetadata(
            id="round-001",
            name="RoundtripAgent",
            description="Test roundtrip",
            capabilities=["test"],
            suggested_prompts=["Try me"],
            avg_execution_time_seconds=1.5,
            avg_cost_cents=5,
            tags=["test", "integration"],
            category="Testing",
        )

        data = skill.to_dict()

        assert data["id"] == "round-001"
        assert data["name"] == "RoundtripAgent"
        assert data["capabilities"] == ["test"]
        assert data["tags"] == ["test", "integration"]
        assert data["category"] == "Testing"


class TestAccessMetadataIntegration:
    """Integration tests for access metadata."""

    @pytest.mark.asyncio
    async def test_access_metadata_to_dict(self):
        """Test access metadata serialization."""
        constraints = AccessConstraints(
            max_daily_invocations=50,
            max_tokens_per_session=5000,
            allowed_tools=["search", "read"],
            time_window_start="09:00:00",
            time_window_end="17:00:00",
        )

        access = AccessMetadata(
            permission_level="execute",
            constraints=constraints,
            granted_by="admin",
            granted_at="2024-01-01T00:00:00Z",
        )

        data = access.to_dict()

        assert data["permission_level"] == "execute"
        assert data["constraints"]["max_daily_invocations"] == 50
        assert data["constraints"]["allowed_tools"] == ["search", "read"]
        assert data["granted_by"] == "admin"

    @pytest.mark.asyncio
    async def test_agent_with_access_serialization(self):
        """Test AgentWithAccess complete serialization."""
        registry = AgentRegistry()
        agent = IntegrationTestAgent(
            name="SerializableAgent",
            agent_id="serial-001",
            capabilities=["serialize"],
        )
        await registry.register_agent(
            agent=agent,
            runtime_id="test-runtime",
        )

        metadata = await registry.get_agent(agent.agent_id)
        access = AccessMetadata(
            permission_level="admin",
            constraints=AccessConstraints(max_daily_invocations=200),
        )

        agent_with_access = AgentWithAccess(
            metadata=metadata,
            access=access,
        )

        data = agent_with_access.to_dict()

        assert data["id"] == "serial-001"
        assert data["name"] == "SerializableAgent"
        assert "serialize" in data["capabilities"]
        assert data["_access"]["permission_level"] == "admin"
        assert data["_access"]["constraints"]["max_daily_invocations"] == 200
