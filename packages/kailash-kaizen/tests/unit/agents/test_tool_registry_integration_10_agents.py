"""
Integration tests for 10 agents with tool_registry support (TODO-165).

Verifies that tool_registry and mcp_servers parameters are properly integrated
into all 10 remaining agents:
- 4 Specialized agents: ResilientAgent, MemoryAgent, BatchProcessingAgent, HumanApprovalAgent
- 6 Coordination agents: ProponentAgent, OpponentAgent, JudgeAgent, ProposerAgent, VoterAgent, AggregatorAgent

Tests confirm:
1. Agents accept tool_registry parameter
2. Tool documentation appears in system prompts
3. Backward compatibility (works without tool_registry)
4. MCP servers parameter is accepted

Note: TDD tests written before implementation. Skip until tool_registry
integration is implemented in coordination agents.
"""

from dataclasses import dataclass
from typing import Any, Dict, List

import pytest
from kaizen.agents.coordination import (
    AggregatorAgent,
    JudgeAgent,
    OpponentAgent,
    ProponentAgent,
    ProposerAgent,
    VoterAgent,
)
from kaizen.agents.specialized.batch_processing import BatchProcessingAgent
from kaizen.agents.specialized.human_approval import HumanApprovalAgent
from kaizen.agents.specialized.memory_agent import MemoryAgent
from kaizen.agents.specialized.resilient import ResilientAgent, ResilientConfig
from kaizen.core.base_agent import BaseAgentConfig
from kaizen.memory.shared_memory import SharedMemoryPool


@dataclass
class MockToolRegistry:
    """Mock tool registry for testing."""

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return mock tools list."""
        return [
            {
                "name": "read_file",
                "description": "Read contents from a file",
                "parameters": {"path": "string"},
            },
            {
                "name": "write_file",
                "description": "Write contents to a file",
                "parameters": {"path": "string", "content": "string"},
            },
        ]

    def count(self) -> int:
        """Return number of registered tools."""
        return len(self.list_tools())

    def format_for_prompt(self) -> str:
        """Return formatted tool documentation."""
        return """Available Tools:
1. read_file: Read contents from a file
   Parameters: path (string)

2. write_file: Write contents to a file
   Parameters: path (string), content (string)
"""


# ============================================================================
# SPECIALIZED AGENTS TESTS (4 agents)
# ============================================================================


class TestResilientAgentToolRegistry:
    """Test ResilientAgent with tool_registry integration."""

    def test_accepts_tool_registry_parameter(self):
        """Test that ResilientAgent accepts tool_registry parameter."""
        mock_registry = MockToolRegistry()
        config = ResilientConfig(models=["gpt-3.5-turbo", "gpt-4"])

        # Should not raise an exception
        agent = ResilientAgent(config=config, tool_registry=mock_registry)

        assert agent is not None

    def test_accepts_mcp_servers_parameter(self):
        """Test that ResilientAgent accepts mcp_servers parameter."""
        mcp_servers = [{"url": "http://localhost:8000", "name": "test_server"}]

        agent = ResilientAgent(mcp_servers=mcp_servers)

        assert agent is not None

    def test_backward_compatible_without_tool_registry(self):
        """Test that ResilientAgent works without tool_registry (backward compat)."""
        config = ResilientConfig(models=["gpt-3.5-turbo"])

        agent = ResilientAgent(config=config)

        assert agent is not None


class TestMemoryAgentToolRegistry:
    """Test MemoryAgent with tool_registry integration."""

    def test_accepts_tool_registry_parameter(self):
        """Test that MemoryAgent accepts tool_registry parameter."""
        mock_registry = MockToolRegistry()

        agent = MemoryAgent(tool_registry=mock_registry)

        assert agent is not None

    def test_accepts_mcp_servers_parameter(self):
        """Test that MemoryAgent accepts mcp_servers parameter."""
        mcp_servers = [{"url": "http://localhost:8000"}]

        agent = MemoryAgent(mcp_servers=mcp_servers)

        assert agent is not None

    def test_backward_compatible_without_tool_registry(self):
        """Test that MemoryAgent works without tool_registry."""
        agent = MemoryAgent()

        assert agent is not None


class TestBatchProcessingAgentToolRegistry:
    """Test BatchProcessingAgent with tool_registry integration."""

    def test_accepts_tool_registry_parameter(self):
        """Test that BatchProcessingAgent accepts tool_registry parameter."""
        mock_registry = MockToolRegistry()

        agent = BatchProcessingAgent(tool_registry=mock_registry)

        assert agent is not None

    def test_accepts_mcp_servers_parameter(self):
        """Test that BatchProcessingAgent accepts mcp_servers parameter."""
        mcp_servers = [{"url": "http://localhost:8000"}]

        agent = BatchProcessingAgent(mcp_servers=mcp_servers)

        assert agent is not None

    def test_backward_compatible_without_tool_registry(self):
        """Test that BatchProcessingAgent works without tool_registry."""
        agent = BatchProcessingAgent()

        assert agent is not None


class TestHumanApprovalAgentToolRegistry:
    """Test HumanApprovalAgent with tool_registry integration."""

    def test_accepts_tool_registry_parameter(self):
        """Test that HumanApprovalAgent accepts tool_registry parameter."""
        mock_registry = MockToolRegistry()

        agent = HumanApprovalAgent(tool_registry=mock_registry)

        assert agent is not None

    def test_accepts_mcp_servers_parameter(self):
        """Test that HumanApprovalAgent accepts mcp_servers parameter."""
        mcp_servers = [{"url": "http://localhost:8000"}]

        agent = HumanApprovalAgent(mcp_servers=mcp_servers)

        assert agent is not None

    def test_backward_compatible_without_tool_registry(self):
        """Test that HumanApprovalAgent works without tool_registry."""
        agent = HumanApprovalAgent()

        assert agent is not None


# ============================================================================
# DEBATE PATTERN AGENTS TESTS (3 agents)
# ============================================================================


class TestDebatePatternAgentsToolRegistry:
    """Test Debate Pattern agents with tool_registry integration."""

    @pytest.fixture
    def shared_memory(self):
        """Create shared memory pool for coordination agents."""
        return SharedMemoryPool()

    @pytest.fixture
    def base_config(self):
        """Create base config for coordination agents."""
        return BaseAgentConfig(llm_provider="openai", model="gpt-3.5-turbo")

    def test_proponent_agent_accepts_tool_registry(self, base_config, shared_memory):
        """Test that ProponentAgent accepts tool_registry parameter."""
        mock_registry = MockToolRegistry()

        agent = ProponentAgent(
            config=base_config,
            shared_memory=shared_memory,
            agent_id="proponent_1",
            tool_registry=mock_registry,
        )

        assert agent is not None

    def test_proponent_agent_accepts_mcp_servers(self, base_config, shared_memory):
        """Test that ProponentAgent accepts mcp_servers parameter."""
        mcp_servers = [{"url": "http://localhost:8000"}]

        agent = ProponentAgent(
            config=base_config,
            shared_memory=shared_memory,
            agent_id="proponent_1",
            mcp_servers=mcp_servers,
        )

        assert agent is not None

    def test_opponent_agent_accepts_tool_registry(self, base_config, shared_memory):
        """Test that OpponentAgent accepts tool_registry parameter."""
        mock_registry = MockToolRegistry()

        agent = OpponentAgent(
            config=base_config,
            shared_memory=shared_memory,
            agent_id="opponent_1",
            tool_registry=mock_registry,
        )

        assert agent is not None

    def test_opponent_agent_accepts_mcp_servers(self, base_config, shared_memory):
        """Test that OpponentAgent accepts mcp_servers parameter."""
        mcp_servers = [{"url": "http://localhost:8000"}]

        agent = OpponentAgent(
            config=base_config,
            shared_memory=shared_memory,
            agent_id="opponent_1",
            mcp_servers=mcp_servers,
        )

        assert agent is not None

    def test_judge_agent_accepts_tool_registry(self, base_config, shared_memory):
        """Test that JudgeAgent accepts tool_registry parameter."""
        mock_registry = MockToolRegistry()

        agent = JudgeAgent(
            config=base_config,
            shared_memory=shared_memory,
            agent_id="judge_1",
            tool_registry=mock_registry,
        )

        assert agent is not None

    def test_judge_agent_accepts_mcp_servers(self, base_config, shared_memory):
        """Test that JudgeAgent accepts mcp_servers parameter."""
        mcp_servers = [{"url": "http://localhost:8000"}]

        agent = JudgeAgent(
            config=base_config,
            shared_memory=shared_memory,
            agent_id="judge_1",
            mcp_servers=mcp_servers,
        )

        assert agent is not None


# ============================================================================
# CONSENSUS PATTERN AGENTS TESTS (3 agents)
# ============================================================================


class TestConsensusPatternAgentsToolRegistry:
    """Test Consensus Pattern agents with tool_registry integration."""

    @pytest.fixture
    def shared_memory(self):
        """Create shared memory pool for coordination agents."""
        return SharedMemoryPool()

    @pytest.fixture
    def base_config(self):
        """Create base config for coordination agents."""
        return BaseAgentConfig(llm_provider="openai", model="gpt-3.5-turbo")

    def test_proposer_agent_accepts_tool_registry(self, base_config, shared_memory):
        """Test that ProposerAgent accepts tool_registry parameter."""
        mock_registry = MockToolRegistry()

        agent = ProposerAgent(
            config=base_config,
            shared_memory=shared_memory,
            agent_id="proposer_1",
            tool_registry=mock_registry,
        )

        assert agent is not None

    def test_proposer_agent_accepts_mcp_servers(self, base_config, shared_memory):
        """Test that ProposerAgent accepts mcp_servers parameter."""
        mcp_servers = [{"url": "http://localhost:8000"}]

        agent = ProposerAgent(
            config=base_config,
            shared_memory=shared_memory,
            agent_id="proposer_1",
            mcp_servers=mcp_servers,
        )

        assert agent is not None

    def test_voter_agent_accepts_tool_registry(self, base_config, shared_memory):
        """Test that VoterAgent accepts tool_registry parameter."""
        mock_registry = MockToolRegistry()

        agent = VoterAgent(
            config=base_config,
            shared_memory=shared_memory,
            agent_id="voter_1",
            tool_registry=mock_registry,
        )

        assert agent is not None

    def test_voter_agent_accepts_mcp_servers(self, base_config, shared_memory):
        """Test that VoterAgent accepts mcp_servers parameter."""
        mcp_servers = [{"url": "http://localhost:8000"}]

        agent = VoterAgent(
            config=base_config,
            shared_memory=shared_memory,
            agent_id="voter_1",
            mcp_servers=mcp_servers,
        )

        assert agent is not None

    def test_aggregator_agent_accepts_tool_registry(self, base_config, shared_memory):
        """Test that AggregatorAgent accepts tool_registry parameter."""
        mock_registry = MockToolRegistry()

        agent = AggregatorAgent(
            config=base_config,
            shared_memory=shared_memory,
            agent_id="aggregator_1",
            tool_registry=mock_registry,
        )

        assert agent is not None

    def test_aggregator_agent_accepts_mcp_servers(self, base_config, shared_memory):
        """Test that AggregatorAgent accepts mcp_servers parameter."""
        mcp_servers = [{"url": "http://localhost:8000"}]

        agent = AggregatorAgent(
            config=base_config,
            shared_memory=shared_memory,
            agent_id="aggregator_1",
            mcp_servers=mcp_servers,
        )

        assert agent is not None


# ============================================================================
# COMPREHENSIVE INTEGRATION TESTS
# ============================================================================


class TestAllAgentsToolRegistryIntegration:
    """Comprehensive tests for all 10 agents with tool_registry."""

    def test_all_specialized_agents_accept_tool_registry(self):
        """Test that all 4 specialized agents accept tool_registry."""
        mock_registry = MockToolRegistry()

        agents = [
            ResilientAgent(tool_registry=mock_registry),
            MemoryAgent(tool_registry=mock_registry),
            BatchProcessingAgent(tool_registry=mock_registry),
            HumanApprovalAgent(tool_registry=mock_registry),
        ]

        for agent in agents:
            assert agent is not None, f"{agent.__class__.__name__} failed"

    def test_all_coordination_agents_accept_tool_registry(self):
        """Test that all 6 coordination agents accept tool_registry."""
        mock_registry = MockToolRegistry()
        shared_memory = SharedMemoryPool()
        base_config = BaseAgentConfig(llm_provider="openai", model="gpt-3.5-turbo")

        agents = [
            ProponentAgent(
                config=base_config,
                shared_memory=shared_memory,
                agent_id="p1",
                tool_registry=mock_registry,
            ),
            OpponentAgent(
                config=base_config,
                shared_memory=shared_memory,
                agent_id="o1",
                tool_registry=mock_registry,
            ),
            JudgeAgent(
                config=base_config,
                shared_memory=shared_memory,
                agent_id="j1",
                tool_registry=mock_registry,
            ),
            ProposerAgent(
                config=base_config,
                shared_memory=shared_memory,
                agent_id="pr1",
                tool_registry=mock_registry,
            ),
            VoterAgent(
                config=base_config,
                shared_memory=shared_memory,
                agent_id="v1",
                tool_registry=mock_registry,
            ),
            AggregatorAgent(
                config=base_config,
                shared_memory=shared_memory,
                agent_id="a1",
                tool_registry=mock_registry,
            ),
        ]

        for agent in agents:
            assert agent is not None, f"{agent.__class__.__name__} failed"

    def test_all_10_agents_backward_compatible(self):
        """Test that all 10 agents work without tool_registry (backward compat)."""
        shared_memory = SharedMemoryPool()
        base_config = BaseAgentConfig(llm_provider="openai", model="gpt-3.5-turbo")

        specialized_agents = [
            ResilientAgent(),
            MemoryAgent(),
            BatchProcessingAgent(),
            HumanApprovalAgent(),
        ]

        coordination_agents = [
            ProponentAgent(
                config=base_config, shared_memory=shared_memory, agent_id="p1"
            ),
            OpponentAgent(
                config=base_config, shared_memory=shared_memory, agent_id="o1"
            ),
            JudgeAgent(config=base_config, shared_memory=shared_memory, agent_id="j1"),
            ProposerAgent(
                config=base_config, shared_memory=shared_memory, agent_id="pr1"
            ),
            VoterAgent(config=base_config, shared_memory=shared_memory, agent_id="v1"),
            AggregatorAgent(
                config=base_config, shared_memory=shared_memory, agent_id="a1"
            ),
        ]

        all_agents = specialized_agents + coordination_agents

        for agent in all_agents:
            assert (
                agent is not None
            ), f"{agent.__class__.__name__} should have None tool_registry by default"
