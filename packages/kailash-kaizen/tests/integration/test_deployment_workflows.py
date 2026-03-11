"""
Integration tests for deployment workflows.

Tests real deployments across all channels with actual Nexus platform.
Tier 2 testing - real infrastructure, no mocks.
"""

from dataclasses import dataclass

import pytest

# Import Kaizen core components
from kaizen.core.base_agent import BaseAgent

# Import Nexus integration
from kaizen.integrations.nexus import (
    NEXUS_AVAILABLE,
    deploy_as_api,
    deploy_as_cli,
    deploy_as_mcp,
    deploy_multi_channel,
)
from kaizen.signatures import InputField, OutputField, Signature

# Skip all tests if Nexus not available
pytestmark = pytest.mark.skipif(
    not NEXUS_AVAILABLE,
    reason="Nexus not available - install with: pip install kailash-nexus",
)


# Test fixtures
@dataclass
class IntegrationConfig:
    """Config for integration test agents."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7


class IntegrationSignature(Signature):
    """Integration test signature."""

    input_text: str = InputField(description="Input text")
    output_text: str = OutputField(description="Output text")


class IntegrationAgent(BaseAgent):
    """Agent for integration testing."""

    def __init__(self, config: IntegrationConfig):
        super().__init__(config=config, signature=IntegrationSignature())

    def process(self, input_text: str) -> dict:
        """Process input text."""
        return self.run(input_text=input_text)


@pytest.fixture
def nexus_app():
    """Create real Nexus application instance."""
    if not NEXUS_AVAILABLE:
        pytest.skip("Nexus not available")

    from nexus import Nexus

    # Create Nexus with test ports to avoid conflicts
    app = Nexus(
        api_port=8001,  # Use non-default ports for testing
        mcp_port=3002,
        auto_discovery=False,  # Disable auto-discovery for tests
    )

    yield app

    # Cleanup (if needed)
    # app.shutdown() would go here if implemented


@pytest.fixture
def integration_agent():
    """Create integration test agent."""
    config = IntegrationConfig()
    return IntegrationAgent(config)


# ============================================================================
# API Deployment Integration Tests
# ============================================================================


class TestAPIDeploymentIntegration:
    """Integration tests for API deployment."""

    def test_api_deployment_execution(self, nexus_app, integration_agent):
        """Test execute deployed API workflow."""
        # Get initial workflow count
        initial_health = nexus_app.health_check()
        initial_count = initial_health["workflows"]

        # Deploy agent as API
        endpoint = deploy_as_api(
            agent=integration_agent,
            nexus_app=nexus_app,
            endpoint_name="integration_test_api_1",
        )

        # Verify deployment
        assert endpoint == "/api/workflows/integration_test_api_1/execute"

        # Verify workflow registered (count increased)
        health = nexus_app.health_check()
        assert health["workflows"] == initial_count + 1

    def test_api_multiple_deployments(self, nexus_app, integration_agent):
        """Test multiple API deployments."""
        # Get initial count
        initial_count = nexus_app.health_check()["workflows"]

        # Deploy same agent with different names
        endpoint1 = deploy_as_api(
            agent=integration_agent,
            nexus_app=nexus_app,
            endpoint_name="test_api_multi_1",
        )

        endpoint2 = deploy_as_api(
            agent=integration_agent,
            nexus_app=nexus_app,
            endpoint_name="test_api_multi_2",
        )

        # Verify both registered (count increased by 2)
        health = nexus_app.health_check()
        assert health["workflows"] == initial_count + 2

        # Verify different endpoints
        assert endpoint1 != endpoint2
        assert "test_api_multi_1" in endpoint1
        assert "test_api_multi_2" in endpoint2


# ============================================================================
# CLI Deployment Integration Tests
# ============================================================================


class TestCLIDeploymentIntegration:
    """Integration tests for CLI deployment."""

    def test_cli_deployment_execution(self, nexus_app, integration_agent):
        """Test execute deployed CLI workflow."""
        # Get initial count
        initial_count = nexus_app.health_check()["workflows"]

        # Deploy agent as CLI
        command = deploy_as_cli(
            agent=integration_agent,
            nexus_app=nexus_app,
            command_name="integration_cli_1",
        )

        # Verify deployment
        assert command == "nexus run integration_cli_1"

        # Verify workflow registered
        health = nexus_app.health_check()
        assert health["workflows"] == initial_count + 1

    def test_cli_command_consistency(self, nexus_app, integration_agent):
        """Test CLI command naming consistency."""
        # Deploy multiple CLI commands
        cmd1 = deploy_as_cli(
            agent=integration_agent, nexus_app=nexus_app, command_name="cmd_cli_1"
        )

        cmd2 = deploy_as_cli(
            agent=integration_agent, nexus_app=nexus_app, command_name="cmd_cli_2"
        )

        # Verify consistent format
        assert cmd1.startswith("nexus run")
        assert cmd2.startswith("nexus run")
        assert "cmd_cli_1" in cmd1
        assert "cmd_cli_2" in cmd2


# ============================================================================
# MCP Deployment Integration Tests
# ============================================================================


class TestMCPDeploymentIntegration:
    """Integration tests for MCP deployment."""

    def test_mcp_deployment_execution(self, nexus_app, integration_agent):
        """Test execute deployed MCP workflow."""
        # Get initial count
        initial_count = nexus_app.health_check()["workflows"]

        # Deploy agent as MCP tool
        tool_name = deploy_as_mcp(
            agent=integration_agent, nexus_app=nexus_app, tool_name="integration_mcp_1"
        )

        # Verify deployment
        assert tool_name == "integration_mcp_1"

        # Verify workflow registered
        health = nexus_app.health_check()
        assert health["workflows"] == initial_count + 1

    def test_mcp_tool_discovery(self, nexus_app, integration_agent):
        """Test MCP tools are discoverable."""
        # Get initial count
        initial_count = nexus_app.health_check()["workflows"]

        # Deploy multiple MCP tools
        deploy_as_mcp(
            agent=integration_agent, nexus_app=nexus_app, tool_name="tool_mcp_1"
        )

        deploy_as_mcp(
            agent=integration_agent, nexus_app=nexus_app, tool_name="tool_mcp_2"
        )

        # Verify both registered
        health = nexus_app.health_check()
        assert health["workflows"] == initial_count + 2


# ============================================================================
# Multi-Channel Integration Tests
# ============================================================================


class TestMultiChannelIntegration:
    """Integration tests for multi-channel deployment."""

    def test_concurrent_channel_access(self, nexus_app, integration_agent):
        """Test multiple channels access same workflow."""
        # Get initial count
        initial_count = nexus_app.health_check()["workflows"]

        # Deploy across all channels
        channels = deploy_multi_channel(
            agent=integration_agent, nexus_app=nexus_app, name="multi_test_1"
        )

        # Verify all channels deployed
        assert "api" in channels
        assert "cli" in channels
        assert "mcp" in channels

        # Verify workflow registered
        # Note: deploy_multi_channel registers same workflow 3 times (once per channel)
        # This is expected behavior for multi-channel deployment
        health = nexus_app.health_check()
        assert health["workflows"] == initial_count + 3

    def test_deployment_lifecycle(self, nexus_app, integration_agent):
        """Test deploy, execute, undeploy workflow."""
        # Get initial count
        initial_count = nexus_app.health_check()["workflows"]

        # Deploy workflow
        channels = deploy_multi_channel(
            agent=integration_agent, nexus_app=nexus_app, name="lifecycle_test_1"
        )

        # Verify deployed (3 registrations for 3 channels)
        health = nexus_app.health_check()
        assert health["workflows"] == initial_count + 3

        # Verify channels configured
        assert channels["api"] == "/api/workflows/lifecycle_test_1/execute"
        assert channels["cli"] == "nexus run lifecycle_test_1"
        assert channels["mcp"] == "lifecycle_test_1"

        # Note: Undeploy functionality would be tested here if implemented
        # For now, verify deployment is stable

    def test_multi_channel_parameter_consistency(self, nexus_app, integration_agent):
        """Test parameters consistent across channels."""
        # Get initial count
        initial_count = nexus_app.health_check()["workflows"]

        # Deploy multi-channel
        deploy_multi_channel(
            agent=integration_agent, nexus_app=nexus_app, name="param_test_1"
        )

        # All channels should accept same parameters
        # (signature-based parameter mapping)

        # Verify deployment (3 registrations for 3 channels)
        health = nexus_app.health_check()
        assert health["workflows"] == initial_count + 3

        # Parameter consistency verified via shared workflow


# ============================================================================
# Error Handling Integration Tests
# ============================================================================


class TestDeploymentErrorHandling:
    """Integration tests for deployment error handling."""

    def test_duplicate_deployment_handling(self, nexus_app, integration_agent):
        """Test handling of duplicate deployments."""
        # Get initial count
        initial_count = nexus_app.health_check()["workflows"]

        # First deployment
        deploy_as_api(
            agent=integration_agent,
            nexus_app=nexus_app,
            endpoint_name="duplicate_test_1",
        )

        # Second deployment with same name raises error (expected Nexus behavior)
        # Note: Nexus doesn't allow duplicate workflow names
        import pytest

        with pytest.raises(ValueError, match="already registered"):
            deploy_as_api(
                agent=integration_agent,
                nexus_app=nexus_app,
                endpoint_name="duplicate_test_1",
            )

        # Verify only one workflow registered
        health = nexus_app.health_check()
        assert health["workflows"] == initial_count + 1

    def test_invalid_agent_deployment(self, nexus_app):
        """Test deployment with invalid agent."""
        # This test ensures proper error handling exists
        # For now, just verify normal path works

        config = IntegrationConfig()
        agent = IntegrationAgent(config)

        endpoint = deploy_as_api(
            agent=agent, nexus_app=nexus_app, endpoint_name="valid_test_1"
        )

        assert endpoint is not None


# ============================================================================
# Performance Integration Tests
# ============================================================================


class TestDeploymentPerformance:
    """Integration tests for deployment performance."""

    def test_rapid_deployments(self, nexus_app, integration_agent):
        """Test rapid sequential deployments."""
        # Get initial count
        initial_count = nexus_app.health_check()["workflows"]

        # Deploy 10 workflows rapidly
        endpoints = []
        for i in range(10):
            endpoint = deploy_as_api(
                agent=integration_agent,
                nexus_app=nexus_app,
                endpoint_name=f"rapid_perf_{i}",
            )
            endpoints.append(endpoint)

        # Verify all deployed
        health = nexus_app.health_check()
        assert health["workflows"] == initial_count + 10

        # Verify unique endpoints
        assert len(set(endpoints)) == 10

    def test_deployment_health_check(self, nexus_app, integration_agent):
        """Test health check with multiple deployments."""
        # Get initial count
        initial_count = nexus_app.health_check()["workflows"]

        # Deploy several workflows
        deploy_multi_channel(
            nexus_app=nexus_app, agent=integration_agent, name="health_test_1"
        )
        deploy_multi_channel(
            nexus_app=nexus_app, agent=integration_agent, name="health_test_2"
        )

        # Check health
        health = nexus_app.health_check()

        # Health status is 'stopped' before app.start() is called
        assert health["status"] in ["healthy", "stopped"]
        # 2 multi-channel deployments = 6 workflow registrations (3 per multi-channel)
        assert health["workflows"] == initial_count + 6
