"""
Unit Tests for Agent Discovery Extensions (Tier 1)

Tests the user-filtered agent discovery and skill metadata.
Part of TODO-204 Enterprise-App Streaming Integration.

Coverage:
- AccessConstraints
- AccessMetadata
- AgentWithAccess
- AgentSkillMetadata
- UserFilteredAgentDiscovery
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from kaizen_agents.patterns.discovery import (
    AccessConstraints,
    AccessMetadata,
    AgentSkillMetadata,
    AgentWithAccess,
    UserFilteredAgentDiscovery,
)
from kaizen_agents.patterns.runtime import AgentMetadata, AgentStatus


class MockAgent:
    """Mock agent for testing."""

    def __init__(
        self,
        name: str = "MockAgent",
        agent_id: str = "mock-001",
        description: str = "A mock agent for testing",
    ):
        self.name = name
        self.agent_id = agent_id
        self.description = description
        self._a2a_card = None
        self._signature = None


class TestAccessConstraints:
    """Test AccessConstraints dataclass."""

    def test_default_values(self):
        """Test default values."""
        constraints = AccessConstraints()

        assert constraints.max_daily_invocations is None
        assert constraints.max_tokens_per_session is None
        assert constraints.max_cost_per_session_usd is None
        assert constraints.allowed_tools is None
        assert constraints.blocked_tools is None
        assert constraints.time_window_start is None
        assert constraints.time_window_end is None

    def test_custom_values(self):
        """Test custom values."""
        constraints = AccessConstraints(
            max_daily_invocations=100,
            max_tokens_per_session=10000,
            max_cost_per_session_usd=1.0,
            allowed_tools=["search", "calculator"],
            blocked_tools=["delete_file"],
            time_window_start="09:00:00",
            time_window_end="17:00:00",
        )

        assert constraints.max_daily_invocations == 100
        assert constraints.max_tokens_per_session == 10000
        assert constraints.max_cost_per_session_usd == 1.0
        assert constraints.allowed_tools == ["search", "calculator"]
        assert constraints.blocked_tools == ["delete_file"]
        assert constraints.time_window_start == "09:00:00"
        assert constraints.time_window_end == "17:00:00"

    def test_to_dict(self):
        """Test serialization."""
        constraints = AccessConstraints(
            max_daily_invocations=50,
            allowed_tools=["read_file"],
        )

        data = constraints.to_dict()

        assert data["max_daily_invocations"] == 50
        assert data["allowed_tools"] == ["read_file"]
        assert data["max_tokens_per_session"] is None


class TestAccessMetadata:
    """Test AccessMetadata dataclass."""

    def test_default_values(self):
        """Test default values."""
        meta = AccessMetadata()

        assert meta.permission_level == "execute"
        assert isinstance(meta.constraints, AccessConstraints)
        assert meta.granted_by is None
        assert meta.granted_at is None
        assert meta.expires_at is None

    def test_custom_values(self):
        """Test custom values."""
        constraints = AccessConstraints(max_daily_invocations=10)
        meta = AccessMetadata(
            permission_level="admin",
            constraints=constraints,
            granted_by="system",
            granted_at="2024-01-01T00:00:00Z",
            expires_at="2024-12-31T23:59:59Z",
        )

        assert meta.permission_level == "admin"
        assert meta.constraints.max_daily_invocations == 10
        assert meta.granted_by == "system"

    def test_to_dict(self):
        """Test serialization."""
        meta = AccessMetadata(
            permission_level="view",
            granted_by="admin-user",
        )

        data = meta.to_dict()

        assert data["permission_level"] == "view"
        assert data["granted_by"] == "admin-user"
        assert "constraints" in data


class TestAgentWithAccess:
    """Test AgentWithAccess dataclass."""

    def test_creation(self):
        """Test creation with metadata and access."""
        agent = MockAgent(name="TestAgent", agent_id="test-001")
        agent_metadata = AgentMetadata(
            agent_id="test-001",
            agent=agent,
            status=AgentStatus.ACTIVE,
        )
        access = AccessMetadata(permission_level="execute")

        agent_with_access = AgentWithAccess(
            metadata=agent_metadata,
            access=access,
        )

        assert agent_with_access.agent_id == "test-001"
        assert agent_with_access.agent is agent
        assert agent_with_access.access.permission_level == "execute"

    def test_to_dict(self):
        """Test serialization."""
        agent = MockAgent(name="SerialAgent", agent_id="serial-001")
        agent_metadata = AgentMetadata(
            agent_id="serial-001",
            agent=agent,
            status=AgentStatus.ACTIVE,
        )
        access = AccessMetadata(permission_level="admin")

        agent_with_access = AgentWithAccess(
            metadata=agent_metadata,
            access=access,
        )

        data = agent_with_access.to_dict()

        assert data["id"] == "serial-001"
        assert data["name"] == "SerialAgent"
        assert data["status"] == "active"
        assert "_access" in data
        assert data["_access"]["permission_level"] == "admin"

    def test_extract_capabilities(self):
        """Test capability extraction from A2A card."""
        agent = MockAgent()
        agent._a2a_card = {
            "capability": "text_generation",
            "capabilities": ["summarization", "translation"],
        }
        agent_metadata = AgentMetadata(
            agent_id="cap-001",
            agent=agent,
            status=AgentStatus.ACTIVE,
            a2a_card=agent._a2a_card,
        )

        agent_with_access = AgentWithAccess(
            metadata=agent_metadata,
            access=AccessMetadata(),
        )

        data = agent_with_access.to_dict()
        capabilities = data["capabilities"]

        assert "text_generation" in capabilities
        assert "summarization" in capabilities
        assert "translation" in capabilities


class TestAgentSkillMetadata:
    """Test AgentSkillMetadata dataclass."""

    def test_default_values(self):
        """Test default values."""
        skill = AgentSkillMetadata(
            id="skill-001",
            name="TestSkill",
            description="A test skill",
        )

        assert skill.id == "skill-001"
        assert skill.name == "TestSkill"
        assert skill.description == "A test skill"
        assert skill.capabilities == []
        assert skill.suggested_prompts == []
        assert skill.input_schema is None
        assert skill.output_types == []
        assert skill.avg_execution_time_seconds == 0.0
        assert skill.avg_cost_cents == 0.0

    def test_full_initialization(self):
        """Test full initialization."""
        skill = AgentSkillMetadata(
            id="full-skill",
            name="FullSkill",
            description="A fully configured skill",
            capabilities=["analyze", "summarize"],
            suggested_prompts=["Analyze this data", "Summarize the document"],
            input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
            output_types=["text", "json"],
            avg_execution_time_seconds=2.5,
            avg_cost_cents=5,
            tags=["data", "analysis"],
            icon="chart",
            category="Analytics",
        )

        assert skill.capabilities == ["analyze", "summarize"]
        assert len(skill.suggested_prompts) == 2
        assert skill.input_schema is not None
        assert skill.avg_execution_time_seconds == 2.5
        assert skill.avg_cost_cents == 5
        assert skill.tags == ["data", "analysis"]
        assert skill.icon == "chart"
        assert skill.category == "Analytics"

    def test_to_dict(self):
        """Test serialization."""
        skill = AgentSkillMetadata(
            id="dict-skill",
            name="DictSkill",
            description="Serialization test",
            capabilities=["test"],
        )

        data = skill.to_dict()

        assert data["id"] == "dict-skill"
        assert data["name"] == "DictSkill"
        assert data["description"] == "Serialization test"
        assert data["capabilities"] == ["test"]
        assert "suggested_prompts" in data
        assert "input_schema" in data

    def test_from_agent(self):
        """Test creation from agent instance."""
        agent = MockAgent(
            name="AgentFromTest",
            agent_id="from-test-001",
            description="An agent for testing from_agent",
        )

        skill = AgentSkillMetadata.from_agent(agent)

        assert skill.id == "from-test-001"
        assert skill.name == "AgentFromTest"
        assert "An agent for testing" in skill.description

    def test_from_agent_with_custom_values(self):
        """Test creation from agent with custom values."""
        agent = MockAgent()

        skill = AgentSkillMetadata.from_agent(
            agent,
            agent_id="custom-id",
            suggested_prompts=["Try this", "Or this"],
            avg_execution_time=3.0,
            avg_cost_cents=10,
        )

        assert skill.id == "custom-id"
        assert skill.suggested_prompts == ["Try this", "Or this"]
        assert skill.avg_execution_time_seconds == 3.0
        assert skill.avg_cost_cents == 10

    def test_from_agent_with_a2a_card(self):
        """Test capability extraction from A2A card."""
        agent = MockAgent()
        agent._a2a_card = {"capabilities": ["cap1", "cap2"]}

        skill = AgentSkillMetadata.from_agent(agent)

        assert "cap1" in skill.capabilities
        assert "cap2" in skill.capabilities

    def test_from_agent_without_name(self):
        """Test fallback to class name when no name."""
        agent = MagicMock()
        agent.__class__.__name__ = "CustomAgentClass"
        del agent.name  # Remove name attribute

        skill = AgentSkillMetadata.from_agent(agent, agent_id="no-name-001")

        assert skill.name == "CustomAgentClass"


class MockAgentRegistry:
    """Mock AgentRegistry for testing discovery."""

    def __init__(self):
        self._agents: Dict[str, AgentMetadata] = {}

    async def register_agent(self, agent, agent_id: str):
        """Register a mock agent."""
        self._agents[agent_id] = AgentMetadata(
            agent_id=agent_id,
            agent=agent,
            status=AgentStatus.ACTIVE,
        )

    async def list_agents(self, status_filter=None):
        """List all agents."""
        if status_filter:
            return [a for a in self._agents.values() if a.status == status_filter]
        return list(self._agents.values())

    async def get_agent(self, agent_id: str):
        """Get agent by ID."""
        return self._agents.get(agent_id)

    async def find_agents_by_capability(self, capability: str, status_filter=None):
        """Find agents by capability (mock returns all)."""
        return await self.list_agents(status_filter)


class TestUserFilteredAgentDiscovery:
    """Test UserFilteredAgentDiscovery."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test initialization."""
        registry = MockAgentRegistry()
        discovery = UserFilteredAgentDiscovery(registry)

        assert discovery._registry is registry
        assert discovery._permission_checker is None

    @pytest.mark.asyncio
    async def test_find_agents_for_user_no_filter(self):
        """Test finding agents for user without filters."""
        registry = MockAgentRegistry()
        await registry.register_agent(MockAgent(name="Agent1"), "agent-1")
        await registry.register_agent(MockAgent(name="Agent2"), "agent-2")

        discovery = UserFilteredAgentDiscovery(registry)

        agents = await discovery.find_agents_for_user(
            user_id="user-123",
            organization_id="org-456",
        )

        assert len(agents) == 2
        assert all(isinstance(a, AgentWithAccess) for a in agents)

    @pytest.mark.asyncio
    async def test_find_agents_with_capability_filter(self):
        """Test finding agents with capability filter."""
        registry = MockAgentRegistry()
        await registry.register_agent(MockAgent(name="Agent1"), "agent-1")

        discovery = UserFilteredAgentDiscovery(registry)

        agents = await discovery.find_agents_for_user(
            user_id="user-123",
            organization_id="org-456",
            capability_filter="summarization",
        )

        # Mock returns all agents for any capability
        assert len(agents) == 1

    @pytest.mark.asyncio
    async def test_find_agents_with_permission_checker(self):
        """Test finding agents with permission checker."""
        registry = MockAgentRegistry()
        await registry.register_agent(MockAgent(name="AllowedAgent"), "allowed-1")
        await registry.register_agent(MockAgent(name="DeniedAgent"), "denied-1")

        # Mock permission checker that denies "denied-1"
        permission_checker = AsyncMock()

        async def check_permission(agent_id, action, user_id, organization_id):
            if agent_id == "denied-1":
                result = MagicMock()
                result.valid = False
                return result
            result = MagicMock()
            result.valid = True
            result.constraints = {}
            return result

        permission_checker.verify = check_permission

        discovery = UserFilteredAgentDiscovery(
            registry,
            permission_checker=permission_checker,
        )

        agents = await discovery.find_agents_for_user(
            user_id="user-123",
            organization_id="org-456",
        )

        assert len(agents) == 1
        assert agents[0].agent_id == "allowed-1"

    @pytest.mark.asyncio
    async def test_get_skill_metadata(self):
        """Test getting skill metadata for agent."""
        registry = MockAgentRegistry()
        agent = MockAgent(name="SkillAgent", agent_id="skill-agent-1")
        await registry.register_agent(agent, "skill-agent-1")

        discovery = UserFilteredAgentDiscovery(registry)

        skill = await discovery.get_skill_metadata("skill-agent-1")

        assert skill is not None
        assert skill.id == "skill-agent-1"
        assert skill.name == "SkillAgent"

    @pytest.mark.asyncio
    async def test_get_skill_metadata_nonexistent(self):
        """Test getting skill metadata for nonexistent agent."""
        registry = MockAgentRegistry()
        discovery = UserFilteredAgentDiscovery(registry)

        skill = await discovery.get_skill_metadata("nonexistent")

        assert skill is None

    @pytest.mark.asyncio
    async def test_list_skill_metadata(self):
        """Test listing all skill metadata."""
        registry = MockAgentRegistry()
        await registry.register_agent(MockAgent(name="Agent1"), "agent-1")
        await registry.register_agent(MockAgent(name="Agent2"), "agent-2")

        discovery = UserFilteredAgentDiscovery(registry)

        skills = await discovery.list_skill_metadata()

        assert len(skills) == 2
        assert all(isinstance(s, AgentSkillMetadata) for s in skills)

    @pytest.mark.asyncio
    async def test_list_skill_metadata_for_user(self):
        """Test listing skill metadata filtered by user."""
        registry = MockAgentRegistry()
        await registry.register_agent(MockAgent(name="Agent1"), "agent-1")

        discovery = UserFilteredAgentDiscovery(registry)

        skills = await discovery.list_skill_metadata(
            user_id="user-123",
            organization_id="org-456",
        )

        assert len(skills) == 1

    @pytest.mark.asyncio
    async def test_access_metadata_from_permission_constraints(self):
        """Test access metadata extracted from permission constraints."""
        registry = MockAgentRegistry()
        await registry.register_agent(MockAgent(name="Agent1"), "agent-1")

        # Mock permission checker with constraints
        permission_checker = AsyncMock()

        async def check_with_constraints(agent_id, action, user_id, organization_id):
            result = MagicMock()
            result.valid = True
            result.constraints = {
                "max_daily_invocations": 50,
                "max_tokens": 5000,
            }
            return result

        permission_checker.verify = check_with_constraints

        discovery = UserFilteredAgentDiscovery(
            registry,
            permission_checker=permission_checker,
        )

        agents = await discovery.find_agents_for_user(
            user_id="user-123",
            organization_id="org-456",
        )

        assert len(agents) == 1
        constraints = agents[0].access.constraints
        assert constraints.max_daily_invocations == 50
        assert constraints.max_tokens_per_session == 5000
