"""
Tier 1 (Unit) Tests for Multi-Agent Coordination in Kaizen Framework

These tests verify the multi-agent coordination capabilities including
workflow templates, agent communication, and team coordination patterns.

Test Requirements:
- Fast execution (<1 second per test)
- No external dependencies
- Can use mocks for external services only
- Test multi-agent workflow templates
- Test agent communication patterns
- Test team coordination creation
"""

from unittest.mock import patch

import pytest

# Import standardized test fixtures
from tests.fixtures.consolidated_test_fixtures import consolidated_fixtures


# Test multi-agent workflow templates
class TestMultiAgentWorkflowTemplates:
    """Test multi-agent workflow template creation and configuration."""

    def test_framework_creates_debate_workflow(self, performance_tracker):
        """Test framework can create debate workflow templates."""
        import kaizen

        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)

        # Create agents for debate
        proponent = framework.create_agent(
            config={"name": "proponent", "role": "proponent"}
        )
        opponent = framework.create_agent(
            config={"name": "opponent", "role": "opponent"}
        )
        moderator = framework.create_agent(
            config={"name": "moderator", "role": "moderator"}
        )

        # Test framework has debate workflow creation capability
        assert hasattr(framework, "create_debate_workflow")
        assert callable(framework.create_debate_workflow)

        # Create debate workflow
        debate_workflow = framework.create_debate_workflow(
            agents=[proponent, opponent, moderator],
            topic="Investment decision",
            rounds=3,
            decision_criteria="evidence-based consensus",
        )

        assert debate_workflow is not None
        assert hasattr(debate_workflow, "agents")
        assert hasattr(debate_workflow, "topic")
        assert hasattr(debate_workflow, "rounds")
        assert hasattr(debate_workflow, "decision_criteria")

        # Verify workflow configuration
        assert len(debate_workflow.agents) == 3
        assert debate_workflow.topic == "Investment decision"
        assert debate_workflow.rounds == 3
        assert debate_workflow.decision_criteria == "evidence-based consensus"

    def test_framework_creates_consensus_workflow(self, performance_tracker):
        """Test framework can create consensus workflow templates."""
        import kaizen

        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)

        # Create agents for consensus
        agents = [
            framework.create_agent(config={"name": f"agent_{i}", "role": "participant"})
            for i in range(3)
        ]

        # Test framework has consensus workflow creation capability
        assert hasattr(framework, "create_consensus_workflow")
        assert callable(framework.create_consensus_workflow)

        # Create consensus workflow
        consensus_workflow = framework.create_consensus_workflow(
            agents=agents,
            topic="Strategic planning",
            consensus_threshold=0.75,
            max_iterations=5,
        )

        assert consensus_workflow is not None
        assert hasattr(consensus_workflow, "agents")
        assert hasattr(consensus_workflow, "topic")
        assert hasattr(consensus_workflow, "consensus_threshold")
        assert hasattr(consensus_workflow, "max_iterations")

        # Verify workflow configuration
        assert len(consensus_workflow.agents) == 3
        assert consensus_workflow.topic == "Strategic planning"
        assert consensus_workflow.consensus_threshold == 0.75
        assert consensus_workflow.max_iterations == 5

    def test_framework_creates_supervisor_worker_workflow(self, performance_tracker):
        """Test framework can create supervisor-worker workflow templates."""
        import kaizen

        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)

        # Create supervisor and workers
        supervisor = framework.create_agent(
            config={"name": "supervisor", "role": "supervisor"}
        )
        workers = [
            framework.create_agent(config={"name": f"worker_{i}", "role": "worker"})
            for i in range(3)
        ]

        # Test framework has supervisor-worker workflow creation capability
        assert hasattr(framework, "create_supervisor_worker_workflow")
        assert callable(framework.create_supervisor_worker_workflow)

        # Create supervisor-worker workflow
        supervisor_workflow = framework.create_supervisor_worker_workflow(
            supervisor=supervisor,
            workers=workers,
            task="Data processing pipeline",
            coordination_pattern="hierarchical",
        )

        assert supervisor_workflow is not None
        assert hasattr(supervisor_workflow, "supervisor")
        assert hasattr(supervisor_workflow, "workers")
        assert hasattr(supervisor_workflow, "task")
        assert hasattr(supervisor_workflow, "coordination_pattern")

        # Verify workflow configuration
        assert supervisor_workflow.supervisor == supervisor
        assert len(supervisor_workflow.workers) == 3
        assert supervisor_workflow.task == "Data processing pipeline"
        assert supervisor_workflow.coordination_pattern == "hierarchical"

    def test_workflow_templates_can_build_to_core_sdk(self, performance_tracker):
        """Test multi-agent workflow templates can compile to Core SDK workflows."""
        import kaizen

        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)

        # Create agents
        agents = [
            framework.create_agent(config={"name": f"agent_{i}", "role": "participant"})
            for i in range(2)
        ]

        # Create workflow template
        consensus_workflow = framework.create_consensus_workflow(
            agents=agents,
            topic="Test consensus",
            consensus_threshold=0.8,
            max_iterations=3,
        )

        # Test workflow can be built to Core SDK format
        assert hasattr(consensus_workflow, "build")
        assert callable(consensus_workflow.build)

        # Build workflow
        built_workflow = consensus_workflow.build()
        assert built_workflow is not None

        # Should have nodes and edges like Core SDK workflows
        assert hasattr(built_workflow, "nodes")
        assert len(built_workflow.nodes) > 0


class TestAgentCommunication:
    """Test agent-to-agent communication capabilities."""

    def test_agent_can_communicate_with_other_agent(self, performance_tracker):
        """Test agents can communicate with each other."""
        import kaizen

        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)

        # Create agents
        agent_a = framework.create_agent(config={"name": "agent_a", "role": "analyst"})
        framework.create_agent(config={"name": "agent_b", "role": "researcher"})

        # Test agent has communication capability
        assert hasattr(agent_a, "communicate_with")
        assert callable(agent_a.communicate_with)

        # Test communication method signature
        import inspect

        sig = inspect.signature(agent_a.communicate_with)
        expected_params = {"target_agent", "message", "context"}
        assert set(sig.parameters.keys()) >= expected_params

    @patch("kailash.runtime.local.LocalRuntime.execute")
    def test_agent_communication_creates_workflow(
        self, mock_execute, performance_tracker
    ):
        """Test agent communication creates appropriate workflow for execution."""
        import kaizen

        # Mock runtime execution
        mock_execute.return_value = (
            {"comm_response_agent_b": {"response": "Hello from agent B"}},
            "test_run_id",
        )

        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)

        agent_a = framework.create_agent(config={"name": "agent_a", "role": "analyst"})
        agent_b = framework.create_agent(
            config={"name": "agent_b", "role": "researcher"}
        )

        # Test communication
        response = agent_a.communicate_with(
            target_agent=agent_b,
            message="What's your analysis?",
            context={"priority": "high"},
        )

        # Verify communication created workflow and executed it
        assert mock_execute.called

        # Verify response structure
        assert response is not None
        assert isinstance(response, dict)
        assert "message" in response
        assert "sender" in response
        assert "receiver" in response
        assert "context" in response
        assert "timestamp" in response

        # Verify response content
        assert response["sender"] == "agent_b"
        assert response["receiver"] == "agent_a"
        assert "Hello from agent B" in response["message"]

    def test_agent_communication_tracks_conversation_history(self, performance_tracker):
        """Test agent communication maintains conversation history."""
        import kaizen

        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)

        agent_a = framework.create_agent(config={"name": "agent_a", "role": "analyst"})
        framework.create_agent(config={"name": "agent_b", "role": "researcher"})

        # Test conversation history tracking capability
        assert hasattr(agent_a, "get_conversation_history")
        assert callable(agent_a.get_conversation_history)

        # Initial conversation history should be empty
        history = agent_a.get_conversation_history("agent_b")
        assert isinstance(history, list)
        assert len(history) == 0

    def test_agent_can_broadcast_to_multiple_agents(self, performance_tracker):
        """Test agents can broadcast messages to multiple agents."""
        import kaizen

        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)

        # Create multiple agents
        sender = framework.create_agent(
            config={"name": "sender", "role": "coordinator"}
        )
        [
            framework.create_agent(
                config={"name": f"receiver_{i}", "role": "participant"}
            )
            for i in range(3)
        ]

        # Test broadcast capability
        assert hasattr(sender, "broadcast_message")
        assert callable(sender.broadcast_message)

        # Test broadcast method signature
        import inspect

        sig = inspect.signature(sender.broadcast_message)
        expected_params = {"target_agents", "message", "context"}
        assert set(sig.parameters.keys()) >= expected_params


class TestAgentTeamCreation:
    """Test agent team creation and coordination patterns."""

    def test_framework_can_create_agent_team(self, performance_tracker):
        """Test framework can create agent teams with coordination patterns."""
        import kaizen

        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)

        # Test framework has team creation capability
        assert hasattr(framework, "create_agent_team")
        assert callable(framework.create_agent_team)

        # Test method signature
        import inspect

        sig = inspect.signature(framework.create_agent_team)
        expected_params = {"team_name", "pattern", "roles", "coordination"}
        assert set(sig.parameters.keys()) >= expected_params

    def test_agent_team_creation_with_collaborative_pattern(self, performance_tracker):
        """Test agent team creation with collaborative coordination pattern."""
        import kaizen

        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)

        # Create agent team
        team = framework.create_agent_team(
            team_name="research_team",
            pattern="collaborative",
            roles=["researcher", "analyst", "validator"],
            coordination="consensus",
        )

        assert team is not None
        assert hasattr(team, "name")
        assert hasattr(team, "pattern")
        assert hasattr(team, "coordination")
        assert hasattr(team, "members")

        # Verify team configuration
        assert team.name == "research_team"
        assert team.pattern == "collaborative"
        assert team.coordination == "consensus"
        assert len(team.members) == 3

        # Verify team members have correct roles
        member_roles = [getattr(member, "role", None) for member in team.members]
        assert any("researcher" in str(role) for role in member_roles)
        assert any("analyst" in str(role) for role in member_roles)
        assert any("validator" in str(role) for role in member_roles)

    def test_agent_team_creation_with_hierarchical_pattern(self, performance_tracker):
        """Test agent team creation with hierarchical coordination pattern."""
        import kaizen

        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)

        # Create agent team with hierarchy
        team = framework.create_agent_team(
            team_name="project_team",
            pattern="hierarchical",
            roles=["leader", "worker", "worker"],
            coordination="supervisor",
        )

        assert team is not None
        assert team.name == "project_team"
        assert team.pattern == "hierarchical"
        assert team.coordination == "supervisor"
        assert len(team.members) == 3

        # Verify hierarchical structure
        authority_levels = [
            getattr(member, "authority_level", None) for member in team.members
        ]
        assert "leader" in authority_levels
        assert authority_levels.count("worker") == 2

    def test_agent_team_has_coordination_methods(self, performance_tracker):
        """Test agent teams have coordination and collaboration methods."""
        import kaizen

        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)

        team = framework.create_agent_team(
            team_name="test_team",
            pattern="collaborative",
            roles=["member1", "member2"],
            coordination="consensus",
        )

        # Test team has coordination capabilities
        assert hasattr(team, "coordinate")
        assert hasattr(team, "members")
        assert hasattr(team, "set_state")

        # Test team can manage state
        if hasattr(team, "set_state"):
            team.set_state({"workflow_stage": "planning"})
            assert hasattr(team, "state")


class TestSpecializedAgentCreation:
    """Test creation of specialized agents with role-based behavior."""

    def test_framework_creates_specialized_agents(self, performance_tracker):
        """Test framework can create specialized agents with roles."""
        import kaizen

        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)

        # Test framework has specialized agent creation capability
        assert hasattr(framework, "create_specialized_agent")
        assert callable(framework.create_specialized_agent)

        # Test method signature
        import inspect

        sig = inspect.signature(framework.create_specialized_agent)
        expected_params = {"name", "role", "config"}
        assert set(sig.parameters.keys()) >= expected_params

    def test_specialized_agent_creation_with_research_role(self, performance_tracker):
        """Test creation of specialized research agent."""
        import kaizen

        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)

        # Create specialized research agent
        agent = framework.create_specialized_agent(
            name="research_specialist",
            role="Research and analyze market trends",
            config={
                "model": "gpt-4",
                "expertise": "market_analysis",
                "capabilities": ["research", "analysis", "reporting"],
            },
        )

        assert agent is not None
        assert hasattr(agent, "role")
        assert hasattr(agent, "expertise")
        assert hasattr(agent, "capabilities")

        # Verify specialized configuration
        assert agent.role == "Research and analyze market trends"
        assert agent.expertise == "market_analysis"
        assert "research" in agent.capabilities
        assert "analysis" in agent.capabilities
        assert "reporting" in agent.capabilities

    def test_specialized_agent_role_based_behavior_traits(self, performance_tracker):
        """Test specialized agents get appropriate behavior traits for their role."""
        import kaizen

        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)

        # Create different specialized agents
        research_agent = framework.create_specialized_agent(
            name="researcher",
            role="Research and analyze data",
            config={"model": "gpt-4"},
        )

        creative_agent = framework.create_specialized_agent(
            name="designer",
            role="Creative design and innovation",
            config={"model": "gpt-4"},
        )

        leadership_agent = framework.create_specialized_agent(
            name="leader",
            role="Lead and coordinate team efforts",
            config={"model": "gpt-4"},
        )

        # Verify different behavior traits based on role
        # Research agents should have analytical traits
        research_config = research_agent.config
        if "behavior_traits" in research_config:
            traits = research_config["behavior_traits"]
            analytical_traits = [
                "thorough",
                "analytical",
                "evidence_based",
                "methodical",
            ]
            assert any(trait in traits for trait in analytical_traits)

        # Creative agents should have innovative traits
        creative_config = creative_agent.config
        if "behavior_traits" in creative_config:
            traits = creative_config["behavior_traits"]
            creative_traits = ["innovative", "divergent", "imaginative", "flexible"]
            assert any(trait in traits for trait in creative_traits)

        # Leadership agents should have collaborative traits
        leadership_config = leadership_agent.config
        if "behavior_traits" in leadership_config:
            traits = leadership_config["behavior_traits"]
            leadership_traits = [
                "decisive",
                "communicative",
                "collaborative",
                "strategic",
            ]
            assert any(trait in traits for trait in leadership_traits)

    def test_specialized_agent_parameter_validation(self, performance_tracker):
        """Test specialized agent creation validates parameters."""
        import kaizen

        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)

        # Test invalid name parameter
        with pytest.raises(ValueError, match="Agent name cannot be empty"):
            framework.create_specialized_agent(
                name="", role="Test role", config={"model": "gpt-4"}
            )

        with pytest.raises(ValueError, match="Agent name cannot be empty"):
            framework.create_specialized_agent(
                name="   ", role="Test role", config={"model": "gpt-4"}
            )

        # Test invalid role parameter
        with pytest.raises(ValueError, match="Role cannot be empty"):
            framework.create_specialized_agent(
                name="test_agent", role="", config={"model": "gpt-4"}
            )

        with pytest.raises(ValueError, match="Role cannot be empty"):
            framework.create_specialized_agent(
                name="test_agent", role="   ", config={"model": "gpt-4"}
            )

        # Test duplicate agent name
        framework.create_specialized_agent(
            name="duplicate_agent", role="Test role", config={"model": "gpt-4"}
        )

        with pytest.raises(ValueError, match="Agent 'duplicate_agent' already exists"):
            framework.create_specialized_agent(
                name="duplicate_agent", role="Another role", config={"model": "gpt-4"}
            )


class TestMultiAgentCoordinationPerformance:
    """Test performance characteristics of multi-agent coordination."""

    def test_specialized_agent_creation_performance(self, performance_tracker):
        """Test specialized agent creation meets performance requirements."""

        import kaizen

        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)

        # Test single agent creation performance
        performance_tracker.start_timer("agent_creation")
        agent = framework.create_specialized_agent(
            name="perf_test_agent",
            role="Performance testing agent",
            config={"model": "gpt-3.5-turbo"},
        )
        creation_time_ms = performance_tracker.end_timer("agent_creation")

        # Should create agent in under 100ms
        performance_tracker.assert_performance("agent_creation", 100)
        assert (
            creation_time_ms < 100
        ), f"Agent creation took {creation_time_ms:.2f}ms, expected < 100ms"

        # Verify agent was created correctly
        assert agent is not None
        assert agent.role == "Performance testing agent"

    def test_multi_agent_workflow_creation_performance(self, performance_tracker):
        """Test multi-agent workflow creation meets performance requirements."""

        import kaizen

        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)

        # Create agents
        agents = [
            framework.create_agent(config={"name": f"agent_{i}", "role": "participant"})
            for i in range(3)
        ]

        # Test consensus workflow creation performance
        performance_tracker.start_timer("workflow_creation")
        consensus_workflow = framework.create_consensus_workflow(
            agents=agents,
            topic="Performance test consensus",
            consensus_threshold=0.75,
            max_iterations=3,
        )
        creation_time_ms = performance_tracker.end_timer("workflow_creation")

        # Should create workflow in under 500ms
        assert (
            creation_time_ms < 500
        ), f"Workflow creation took {creation_time_ms:.2f}ms, expected < 500ms"

        # Verify workflow was created correctly
        assert consensus_workflow is not None
        assert len(consensus_workflow.agents) == 3

    def test_agent_team_creation_performance(self, performance_tracker):
        """Test agent team creation meets performance requirements."""

        import kaizen

        config = consolidated_fixtures.get_configuration("minimal")
        framework = kaizen.Framework(config=config)

        # Test team creation performance
        performance_tracker.start_timer("team_creation")
        team = framework.create_agent_team(
            team_name="performance_team",
            pattern="collaborative",
            roles=["leader", "worker", "worker"],
            coordination="consensus",
        )
        creation_time_ms = performance_tracker.end_timer("team_creation")

        # Should create team in under 1000ms
        assert (
            creation_time_ms < 1000
        ), f"Team creation took {creation_time_ms:.2f}ms, expected < 1000ms"

        # Verify team was created correctly
        assert team is not None
        assert len(team.members) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
