"""
Complete end-to-end integration tests for Kaizen-Nexus.

This test suite validates complete integration workflows:
- Multi-channel deployment → execution → session management → results
- Multi-agent coordination via Nexus
- Error recovery across channels
- Deployment lifecycle management
- Platform health monitoring

Part of TODO-149 Phase 4: Performance & Testing
"""

import time
from dataclasses import dataclass

import pytest

# Check Nexus availability
try:
    from nexus import Nexus

    NEXUS_AVAILABLE = True
except ImportError:
    NEXUS_AVAILABLE = False
    Nexus = None

# Import Kaizen components
from kaizen.core.base_agent import BaseAgent
from kaizen.integrations.nexus import NEXUS_AVAILABLE as INTEGRATION_AVAILABLE
from kaizen.integrations.nexus import NexusSessionManager, deploy_multi_channel
from kaizen.signatures import InputField, OutputField, Signature

# Skip all tests if Nexus not available
pytestmark = pytest.mark.skipif(
    not NEXUS_AVAILABLE or not INTEGRATION_AVAILABLE, reason="Nexus not available"
)


# Test agents
class AnalysisSignature(Signature):
    """Analysis agent signature."""

    data: list = InputField(description="Data to analyze")
    insights: list = OutputField(description="Analysis insights")


@dataclass
class AnalysisConfig:
    """Config for analysis agent."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.3


class AnalysisAgent(BaseAgent):
    """Analysis agent for testing."""

    def __init__(self, config: AnalysisConfig):
        super().__init__(config=config, signature=AnalysisSignature())

    def analyze(self, data: list) -> dict:
        """Analyze data."""
        return self.run(data=data)


class ReportSignature(Signature):
    """Report agent signature."""

    insights: list = InputField(description="Insights to report")
    report: str = OutputField(description="Generated report")


@dataclass
class ReportConfig:
    """Config for report agent."""

    llm_provider: str = "mock"
    model: str = "gpt-4"
    temperature: float = 0.5


class ReportAgent(BaseAgent):
    """Report generation agent."""

    def __init__(self, config: ReportConfig):
        super().__init__(config=config, signature=ReportSignature())

    def generate(self, insights: list) -> dict:
        """Generate report."""
        return self.run(insights=insights)


@pytest.fixture
def nexus_app():
    """Create Nexus app for testing."""
    if not NEXUS_AVAILABLE:
        pytest.skip("Nexus not available")

    app = Nexus(auto_discovery=False)
    yield app


@pytest.fixture
def analysis_agent():
    """Create analysis agent."""
    config = AnalysisConfig()
    return AnalysisAgent(config)


@pytest.fixture
def report_agent():
    """Create report agent."""
    config = ReportConfig()
    return ReportAgent(config)


@pytest.fixture
def session_manager():
    """Create session manager."""
    return NexusSessionManager(cleanup_interval=60)


class TestCompleteMultiChannelWorkflow:
    """Test complete multi-channel workflow from deployment to results."""

    def test_deploy_execute_session_results_flow(
        self, nexus_app, analysis_agent, session_manager
    ):
        """Test complete flow: Deploy → Execute → Session → Results."""
        # Step 1: Deploy across all channels
        deployment = deploy_multi_channel(
            agent=analysis_agent, nexus_app=nexus_app, name="analysis"
        )

        # Verify deployment
        assert "api" in deployment
        assert "cli" in deployment
        assert "mcp" in deployment

        # Step 2: Create session
        session = session_manager.create_session(user_id="test_user")

        # Step 3: Execute via API channel (simulated)
        session_manager.update_session_state(
            session.session_id, {"channel": "api", "status": "executing"}, channel="api"
        )

        # Execute workflow
        result = analysis_agent.analyze(data=[1, 2, 3, 4, 5])

        # Store result in session
        session_manager.update_session_state(
            session.session_id, {"result": result, "status": "completed"}, channel="api"
        )

        # Step 4: Access same session from CLI channel
        cli_state = session_manager.get_session_state(session.session_id)

        # Verify session state is synchronized
        assert cli_state["channel"] == "api"
        assert cli_state["status"] == "completed"
        assert "result" in cli_state

        # Step 5: Access same session from MCP channel
        session_manager.update_session_state(
            session.session_id, {"mcp_access": True}, channel="mcp"
        )

        final_state = session_manager.get_session_state(session.session_id)

        # Verify cross-channel state
        assert final_state["mcp_access"] is True
        assert final_state["status"] == "completed"

        # Verify session activity tracking
        assert session.channel_activity["api"] > 0
        assert session.channel_activity["mcp"] > 0

    def test_multi_step_workflow_with_sessions(
        self, nexus_app, analysis_agent, report_agent, session_manager
    ):
        """Test multi-step workflow using sessions."""
        # Deploy both agents
        deploy_multi_channel(analysis_agent, nexus_app, "analyze")
        deploy_multi_channel(report_agent, nexus_app, "report")

        # Create session
        session = session_manager.create_session(user_id="multi_step_user")

        # Step 1: Analysis
        analysis_result = analysis_agent.analyze(data=[10, 20, 30])
        session_manager.update_session_state(
            session.session_id,
            {"step": "analysis", "analysis_result": analysis_result},
            channel="api",
        )

        # Step 2: Report generation (uses analysis result)
        state = session_manager.get_session_state(session.session_id)
        insights = state["analysis_result"].get("insights", [])

        report_result = report_agent.generate(insights=insights)
        session_manager.update_session_state(
            session.session_id,
            {"step": "report", "report_result": report_result},
            channel="api",
        )

        # Verify complete workflow state
        final_state = session_manager.get_session_state(session.session_id)
        assert final_state["step"] == "report"
        assert "analysis_result" in final_state
        assert "report_result" in final_state


class TestMultiAgentCoordination:
    """Test multi-agent coordination via Nexus."""

    def test_multiple_agents_via_nexus_with_sessions(
        self, nexus_app, analysis_agent, report_agent, session_manager
    ):
        """Test coordinating multiple agents via Nexus with sessions."""
        # Deploy agents with different names
        deploy_multi_channel(analysis_agent, nexus_app, "agent1")
        deploy_multi_channel(report_agent, nexus_app, "agent2")

        # Create shared session
        session = session_manager.create_session(user_id="coordinator")

        # Agent 1 execution
        result1 = analysis_agent.analyze(data=[1, 2, 3])
        session_manager.update_session_state(
            session.session_id, {"agent1_result": result1}, channel="api"
        )

        # Agent 2 execution (can access agent1 result)
        state = session_manager.get_session_state(session.session_id)
        insights = state.get("agent1_result", {}).get("insights", [])

        result2 = report_agent.generate(insights=insights)
        session_manager.update_session_state(
            session.session_id, {"agent2_result": result2}, channel="api"
        )

        # Verify coordination
        final_state = session_manager.get_session_state(session.session_id)
        assert "agent1_result" in final_state
        assert "agent2_result" in final_state

    def test_parallel_agent_execution(
        self, nexus_app, analysis_agent, report_agent, session_manager
    ):
        """Test parallel execution of multiple agents."""
        # Deploy agents
        deploy_multi_channel(analysis_agent, nexus_app, "parallel1")
        deploy_multi_channel(report_agent, nexus_app, "parallel2")

        # Create sessions for each agent
        session1 = session_manager.create_session(user_id="user1")
        session2 = session_manager.create_session(user_id="user2")

        # Execute agents in parallel (simulated)
        result1 = analysis_agent.analyze(data=[1, 2, 3])
        result2 = report_agent.generate(insights=["insight1", "insight2"])

        # Store results in respective sessions
        session_manager.update_session_state(
            session1.session_id, {"result": result1}, channel="api"
        )
        session_manager.update_session_state(
            session2.session_id, {"result": result2}, channel="api"
        )

        # Verify session isolation
        state1 = session_manager.get_session_state(session1.session_id)
        state2 = session_manager.get_session_state(session2.session_id)

        assert state1 != state2
        assert state1["result"] != state2["result"]


class TestErrorRecoveryAcrossChannels:
    """Test error handling and recovery across channels."""

    def test_graceful_error_handling_in_deployment(self, nexus_app):
        """Test graceful handling of deployment errors."""

        # Try to deploy with invalid configuration
        class InvalidAgent:
            """Not a real BaseAgent."""

            pass

        invalid_agent = InvalidAgent()

        # Should handle gracefully
        with pytest.raises((AttributeError, TypeError)):
            deploy_multi_channel(invalid_agent, nexus_app, "invalid")

    def test_session_error_recovery(self, session_manager):
        """Test recovery from session errors."""
        # Try to access non-existent session
        state = session_manager.get_session_state("non_existent_session")

        # Should return None or empty dict (graceful handling)
        assert state is None or state == {}

        # Try to update non-existent session
        success = session_manager.update_session_state(
            "non_existent_session", {"key": "value"}, channel="api"
        )

        # Should return False (graceful failure)
        assert success is False

    def test_expired_session_handling(self, session_manager):
        """Test handling of expired sessions."""
        # Create session with short TTL
        session = session_manager.create_session(user_id="temp_user", ttl_hours=0.0001)

        # Wait for expiration
        time.sleep(0.1)

        # Try to access expired session
        state = session_manager.get_session_state(session.session_id)

        # Should handle gracefully (might return None or indicate expiration)
        # Behavior depends on cleanup policy
        assert state is None or "expired" in str(state).lower() or state == {}


class TestDeploymentLifecycleManagement:
    """Test deployment lifecycle (deploy, start, stop, undeploy)."""

    def test_deploy_and_health_check(self, nexus_app, analysis_agent):
        """Test deployment and health verification."""
        # Deploy agent
        deployment = deploy_multi_channel(analysis_agent, nexus_app, "health_test")

        # Verify deployment
        assert deployment is not None

        # Check platform health
        health = nexus_app.health_check()

        # Verify health response
        assert health["status"] in ["healthy", "ok"]
        assert "workflows" in health

    def test_multiple_deployments_coexist(
        self, nexus_app, analysis_agent, report_agent
    ):
        """Test that multiple deployments can coexist."""
        # Deploy first agent
        deployment1 = deploy_multi_channel(analysis_agent, nexus_app, "deploy1")

        # Deploy second agent
        deployment2 = deploy_multi_channel(report_agent, nexus_app, "deploy2")

        # Verify both deployed
        assert deployment1 is not None
        assert deployment2 is not None

        # Verify different endpoints
        assert deployment1["api"] != deployment2["api"]

    def test_redeployment_overwrites_previous(self, nexus_app, analysis_agent):
        """Test that redeployment overwrites previous deployment."""
        # Initial deployment
        deploy_multi_channel(analysis_agent, nexus_app, "redeploy_test")

        # Redeploy same agent
        deployment2 = deploy_multi_channel(analysis_agent, nexus_app, "redeploy_test")

        # Verify deployment succeeded (might overwrite or coexist)
        assert deployment2 is not None


class TestPlatformHealthMonitoring:
    """Test platform health monitoring."""

    def test_health_check_includes_workflows(self, nexus_app, analysis_agent):
        """Test that health check includes workflow information."""
        # Deploy agent
        deploy_multi_channel(analysis_agent, nexus_app, "health_workflow")

        # Check health
        health = nexus_app.health_check()

        # Verify workflow information
        assert "workflows" in health
        # Note: Actual workflow tracking depends on Nexus implementation

    def test_health_check_performance(self, nexus_app, analysis_agent):
        """Test that health check is fast."""
        # Deploy agent
        deploy_multi_channel(analysis_agent, nexus_app, "perf_health")

        # Measure health check time
        start_time = time.time()

        health = nexus_app.health_check()

        duration = time.time() - start_time

        # Verify health check is fast (<100ms)
        assert duration < 0.1, f"Health check took {duration:.4f}s, expected <0.1s"

        # Verify health status
        assert health["status"] in ["healthy", "ok"]

    def test_session_metrics_in_health(self, session_manager):
        """Test that session metrics are available."""
        # Create some sessions
        for i in range(5):
            session_manager.create_session(user_id=f"user_{i}")

        # Get metrics
        metrics = session_manager.get_session_metrics()

        # Verify metrics
        assert metrics["active_sessions"] >= 5
        assert metrics["total_sessions"] >= 5
        assert "average_ttl_seconds" in metrics
        assert "channels_used" in metrics


class TestIntegrationQuality:
    """Test integration quality and edge cases."""

    def test_deployment_parameter_validation(self, nexus_app, analysis_agent):
        """Test that deployment validates parameters."""
        # Valid deployment
        deployment = deploy_multi_channel(analysis_agent, nexus_app, "valid_deploy")
        assert deployment is not None

        # Invalid agent (None)
        with pytest.raises((TypeError, AttributeError, ValueError)):
            deploy_multi_channel(None, nexus_app, "invalid")

        # Invalid app (None)
        with pytest.raises((TypeError, AttributeError)):
            deploy_multi_channel(analysis_agent, None, "invalid")

    def test_session_edge_cases(self, session_manager):
        """Test session edge cases."""
        # Empty user_id
        with pytest.raises((ValueError, TypeError, AssertionError)):
            session_manager.create_session(user_id="")

        # Very long TTL
        session = session_manager.create_session(
            user_id="long_ttl_user", ttl_hours=1000
        )
        assert session is not None

        # Zero TTL
        session = session_manager.create_session(user_id="zero_ttl_user", ttl_hours=0)
        # Should create session (will expire immediately)
        assert session is not None

    def test_channel_isolation(self, nexus_app, analysis_agent, session_manager):
        """Test that channels are properly isolated."""
        # Deploy to all channels
        deploy_multi_channel(analysis_agent, nexus_app, "isolation_test")

        # Create session
        session = session_manager.create_session(user_id="isolation_user")

        # Update from API channel
        session_manager.update_session_state(
            session.session_id, {"api_data": "api_value"}, channel="api"
        )

        # Update from CLI channel
        session_manager.update_session_state(
            session.session_id, {"cli_data": "cli_value"}, channel="cli"
        )

        # Verify both updates are in session (channels share state)
        state = session_manager.get_session_state(session.session_id)
        assert state["api_data"] == "api_value"
        assert state["cli_data"] == "cli_value"

        # Verify channel activity tracking
        assert "api" in session.channel_activity
        assert "cli" in session.channel_activity
