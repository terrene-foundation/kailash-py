"""
Tier 2 (Integration) Tests for Multi-Agent Coordination in Kaizen Framework

These tests verify multi-agent coordination integrates correctly with real
Core SDK components and A2A infrastructure. All external services are real (NO MOCKING).

Test Requirements:
- Use real Docker services from tests/utils
- NO MOCKING - test actual multi-agent interactions
- Test multi-agent workflows with real Core SDK execution
- Test agent communication with real A2A nodes
- Test team coordination with real workflow execution
- Timeout: <5 seconds per test
"""

import time

import pytest

from kailash.runtime.local import LocalRuntime

# Import Core SDK components (real, not mocked)
from kailash.workflow.builder import WorkflowBuilder

# Test markers
pytestmark = pytest.mark.integration


class TestMultiAgentWorkflowIntegration:
    """Test multi-agent workflow integration with real Core SDK components."""

    def test_debate_workflow_builds_to_real_core_sdk_workflow(self):
        """Test debate workflow templates build to executable Core SDK workflows."""
        import kaizen

        framework = kaizen.Framework()

        # Create real agents
        proponent = framework.create_agent(
            config={"name": "proponent", "role": "proponent"}
        )
        opponent = framework.create_agent(
            config={"name": "opponent", "role": "opponent"}
        )
        moderator = framework.create_agent(
            config={"name": "moderator", "role": "moderator"}
        )

        # Create debate workflow
        debate_workflow = framework.create_debate_workflow(
            agents=[proponent, opponent, moderator],
            topic="Should we invest in renewable energy?",
            rounds=2,
            decision_criteria="evidence-based consensus",
        )

        # Test workflow builds to real Core SDK format
        workflow_builder = debate_workflow.build()
        assert workflow_builder is not None
        assert isinstance(workflow_builder, WorkflowBuilder)

        # Build the actual workflow
        built_workflow = workflow_builder.build()
        assert built_workflow is not None

        # Verify it's a real Core SDK workflow
        assert hasattr(built_workflow, "nodes")
        assert hasattr(
            built_workflow, "connections"
        )  # Core SDK uses connections, not edges
        assert len(built_workflow.nodes) > 0

        # Should include A2A coordination nodes
        node_types = [node.node_type for node in built_workflow.nodes.values()]
        assert any(
            "A2A" in node_type or "LLMAgent" in node_type for node_type in node_types
        )

    def test_consensus_workflow_executes_with_real_runtime(self):
        """Test consensus workflow executes with real LocalRuntime."""
        import kaizen

        framework = kaizen.Framework()

        # Create agents for consensus
        agents = [
            framework.create_agent(config={"name": f"agent_{i}", "role": "participant"})
            for i in range(2)
        ]

        # Create consensus workflow
        consensus_workflow = framework.create_consensus_workflow(
            agents=agents,
            topic="Team meeting schedule",
            consensus_threshold=0.8,
            max_iterations=2,
        )

        # Build workflow
        workflow_builder = consensus_workflow.build()
        built_workflow = workflow_builder.build()

        # Execute with real runtime
        runtime = LocalRuntime()
        results, run_id = runtime.execute(built_workflow)

        # Verify execution results
        assert results is not None
        assert run_id is not None
        assert isinstance(results, dict)
        assert len(results) > 0

        # Should have results from multiple agents/nodes
        assert len(results) >= len(agents)

    def test_supervisor_worker_workflow_real_execution(self):
        """Test supervisor-worker workflow with real workflow execution."""
        import kaizen

        framework = kaizen.Framework()

        # Create supervisor and workers
        supervisor = framework.create_agent(
            config={"name": "supervisor", "role": "supervisor"}
        )
        workers = [
            framework.create_agent(config={"name": f"worker_{i}", "role": "worker"})
            for i in range(2)
        ]

        # Create supervisor-worker workflow
        supervisor_workflow = framework.create_supervisor_worker_workflow(
            supervisor=supervisor,
            workers=workers,
            task="Process customer data",
            coordination_pattern="hierarchical",
        )

        # Build and execute workflow
        workflow_builder = supervisor_workflow.build()
        built_workflow = workflow_builder.build()
        results, run_id = framework.execute(built_workflow)

        # Verify execution results
        assert results is not None
        assert run_id is not None

        # Should have coordination results
        assert len(results) > 0


class TestAgentCommunicationIntegration:
    """Test agent communication integration with real A2A infrastructure."""

    def test_agent_communication_uses_real_workflow_execution(self):
        """Test agent communication creates and executes real workflows."""
        import kaizen

        framework = kaizen.Framework()

        # Create agents
        agent_a = framework.create_agent(config={"name": "agent_a", "role": "analyst"})
        agent_b = framework.create_agent(
            config={"name": "agent_b", "role": "researcher"}
        )

        # Test communication with real execution
        response = agent_a.communicate_with(
            target_agent=agent_b,
            message="What are your insights on market trends?",
            context={"topic": "market_analysis", "urgency": "high"},
        )

        # Verify real communication response
        assert response is not None
        assert isinstance(response, dict)
        assert "message" in response
        assert "sender" in response
        assert "receiver" in response
        assert "timestamp" in response

        # Verify proper agent identification
        assert response["sender"] == "agent_b"
        assert response["receiver"] == "agent_a"

        # Verify response contains actual content
        assert len(response["message"]) > 0
        assert response["message"] != "No response"

    def test_multi_agent_conversation_maintains_context(self):
        """Test multi-round agent conversation maintains context."""
        import kaizen

        framework = kaizen.Framework()

        # Create conversational agents
        analyst = framework.create_agent(
            config={
                "name": "analyst",
                "role": "Data analyst with expertise in market research",
            }
        )
        researcher = framework.create_agent(
            config={
                "name": "researcher",
                "role": "Market researcher with industry knowledge",
            }
        )

        # First communication
        response1 = analyst.communicate_with(
            researcher,
            "What's the current state of the renewable energy market?",
            context={"conversation_id": "market_research_1"},
        )

        assert response1 is not None
        # In integration tests, we verify communication works, not content quality
        assert len(response1["message"]) > 0

        # Follow-up communication
        response2 = analyst.communicate_with(
            researcher,
            "What are the main growth opportunities you mentioned?",
            context={
                "conversation_id": "market_research_1",
                "reference": response1["message"],
            },
        )

        assert response2 is not None
        assert len(response2["message"]) > 0

        # Verify conversation history is maintained
        history = analyst.get_conversation_history("researcher")
        assert len(history) >= 2

        # Verify conversation context
        assert (
            history[0]["message"]
            == "What's the current state of the renewable energy market?"
        )
        assert (
            history[1]["message"]
            == "What are the main growth opportunities you mentioned?"
        )

    def test_agent_broadcast_to_multiple_agents(self):
        """Test agent broadcasting to multiple agents with real execution."""
        import kaizen

        framework = kaizen.Framework()

        # Create coordinator and team agents
        coordinator = framework.create_agent(
            config={"name": "coordinator", "role": "team_coordinator"}
        )
        team_agents = [
            framework.create_agent(
                config={"name": f"team_member_{i}", "role": f"specialist_{i}"}
            )
            for i in range(3)
        ]

        # Test broadcast communication
        responses = coordinator.broadcast_message(
            target_agents=team_agents,
            message="Please provide your status update on the current project.",
            context={"meeting_type": "standup", "date": "2024-01-15"},
        )

        # Verify broadcast responses
        assert responses is not None
        assert isinstance(responses, list)
        assert len(responses) == 3

        # Verify each response
        for i, response in enumerate(responses):
            assert isinstance(response, dict)
            assert "sender" in response
            assert "message" in response
            assert response["sender"] == f"team_member_{i}"
            assert len(response["message"]) > 0


class TestAgentTeamCoordinationIntegration:
    """Test agent team coordination with real workflow execution."""

    def test_agent_team_executes_collaborative_workflow(self):
        """Test agent team executes collaborative workflows with real coordination."""
        import kaizen

        framework = kaizen.Framework()

        # Create collaborative team
        team = framework.create_agent_team(
            team_name="product_development_team",
            pattern="collaborative",
            roles=["designer", "developer", "tester"],
            coordination="consensus",
        )

        # Verify team has real agents
        assert len(team.members) == 3
        assert all(hasattr(member, "agent_id") for member in team.members)
        assert all(hasattr(member, "kaizen") for member in team.members)

        # Test team coordination workflow
        if hasattr(team, "coordinate"):
            coordination_result = team.coordinate(
                task="Design new user interface",
                context={"priority": "high", "deadline": "2024-02-01"},
            )

            assert coordination_result is not None

    def test_hierarchical_team_coordination_with_authority_levels(self):
        """Test hierarchical team coordination respects authority levels."""
        import kaizen

        framework = kaizen.Framework()

        # Create hierarchical team
        team = framework.create_agent_team(
            team_name="project_management_team",
            pattern="hierarchical",
            roles=["leader", "worker", "worker"],
            coordination="supervisor",
        )

        # Verify hierarchical structure
        assert len(team.members) == 3

        # Find leader and workers
        leader = None
        workers = []
        for member in team.members:
            if hasattr(member, "authority_level"):
                if member.authority_level == "leader":
                    leader = member
                elif member.authority_level == "worker":
                    workers.append(member)

        assert leader is not None, "Team should have a leader"
        assert len(workers) == 2, "Team should have 2 workers"

        # Verify leader has different configuration
        assert hasattr(leader, "config")
        assert leader.config.get("team_role") != workers[0].config.get("team_role")

    def test_team_state_management_with_real_coordination(self):
        """Test agent team state management during coordination."""
        import kaizen

        framework = kaizen.Framework()

        # Create team with state management
        team = framework.create_agent_team(
            team_name="research_team",
            pattern="collaborative",
            roles=["researcher", "analyst"],
            coordination="consensus",
            state_management=True,
        )

        # Verify initial state
        if hasattr(team, "state"):
            initial_state = team.state
            assert "workflow_stage" in initial_state
            assert initial_state["workflow_stage"] == "initialized"

        # Update team state
        if hasattr(team, "set_state"):
            team.set_state(
                {"workflow_stage": "planning", "current_task": "market_analysis"}
            )

            updated_state = team.state
            assert updated_state["workflow_stage"] == "planning"
            assert updated_state["current_task"] == "market_analysis"


class TestMultiAgentPerformanceIntegration:
    """Test multi-agent coordination performance with real execution."""

    def test_multi_agent_workflow_execution_performance(self):
        """Test multi-agent workflows execute within performance requirements."""
        import kaizen

        framework = kaizen.Framework()

        # Create agents
        agents = [
            framework.create_agent(
                config={"name": f"perf_agent_{i}", "role": "performer"}
            )
            for i in range(3)
        ]

        # Create and execute consensus workflow
        start_time = time.time()

        consensus_workflow = framework.create_consensus_workflow(
            agents=agents,
            topic="Performance testing consensus",
            consensus_threshold=0.7,
            max_iterations=2,
        )

        workflow_builder = consensus_workflow.build()
        built_workflow = workflow_builder.build()
        results, run_id = framework.execute(built_workflow)

        end_time = time.time()

        # Verify performance requirements
        execution_time = end_time - start_time
        assert (
            execution_time < 5.0
        ), f"Multi-agent workflow took {execution_time:.3f}s, expected < 5.0s"

        # Verify successful execution
        assert results is not None
        assert run_id is not None
        assert len(results) > 0

    def test_agent_communication_performance_at_scale(self):
        """Test agent communication performance with multiple agents."""
        import kaizen

        framework = kaizen.Framework()

        # Create multiple agents
        coordinator = framework.create_agent(
            config={"name": "coordinator", "role": "coordinator"}
        )
        agents = [
            framework.create_agent(config={"name": f"agent_{i}", "role": "participant"})
            for i in range(5)
        ]

        # Test communication performance
        start_time = time.time()

        responses = coordinator.broadcast_message(
            target_agents=agents,
            message="Quick status check",
            context={"type": "performance_test"},
        )

        end_time = time.time()

        # Verify performance requirements
        communication_time = end_time - start_time
        assert (
            communication_time < 3.0
        ), f"Broadcast communication took {communication_time:.3f}s, expected < 3.0s"

        # Verify all communications succeeded
        assert len(responses) == 5
        successful_responses = [r for r in responses if "error" not in r]
        assert len(successful_responses) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
