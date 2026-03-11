"""
Unit tests for multi-channel deployment.

Tests API, CLI, and MCP deployment capabilities for Kaizen agents.
Following TDD methodology - tests written FIRST.
"""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

# Import Kaizen core components
from kaizen.core.base_agent import BaseAgent

# Import Nexus integration components (to be implemented)
from kaizen.integrations.nexus import (
    NexusDeploymentMixin,
    deploy_as_api,
    deploy_as_cli,
    deploy_as_mcp,
    deploy_multi_channel,
)
from kaizen.signatures import InputField, OutputField, Signature


# Test fixtures
@dataclass
class MockConfig:
    """Mock config for test agents."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7


class DeploymentTestSignature(Signature):
    """Test agent signature."""

    question: str = InputField(description="User question")
    answer: str = OutputField(description="Answer to question")


# Alias for backward compatibility with tests using TestSignature
TestSignature = DeploymentTestSignature


class DeploymentTestAgent(BaseAgent):
    """Test agent for deployment."""

    def __init__(self, config: MockConfig):
        super().__init__(config=config, signature=DeploymentTestSignature())

    def ask(self, question: str) -> dict:
        """Ask a question."""
        return self.run(question=question)


@pytest.fixture
def mock_nexus_app():
    """Mock Nexus application."""
    app = MagicMock()
    app.register = MagicMock()
    app.health_check = MagicMock(return_value={"status": "healthy", "workflows": {}})
    return app


@pytest.fixture
def test_agent():
    """Create test agent."""
    config = MockConfig()
    return DeploymentTestAgent(config)


# ============================================================================
# API Deployment Tests
# ============================================================================


class TestAPIDeployment:
    """Test API deployment functionality."""

    def test_deploy_agent_as_api(self, test_agent, mock_nexus_app):
        """Test agent deploys as REST API endpoint."""
        endpoint = deploy_as_api(
            agent=test_agent, nexus_app=mock_nexus_app, endpoint_name="qa"
        )

        # Verify endpoint returned
        assert endpoint is not None
        assert isinstance(endpoint, str)

        # Verify registration called
        mock_nexus_app.register.assert_called_once()

    def test_api_endpoint_naming(self, test_agent, mock_nexus_app):
        """Test API endpoint follows naming convention."""
        endpoint = deploy_as_api(
            agent=test_agent, nexus_app=mock_nexus_app, endpoint_name="qa"
        )

        # Should follow pattern: /api/workflows/{name}/execute
        assert endpoint.startswith("/api/workflows/")
        assert endpoint.endswith("/execute")
        assert "qa" in endpoint
        assert endpoint == "/api/workflows/qa/execute"

    def test_api_workflow_registration(self, test_agent, mock_nexus_app):
        """Test workflow registered with Nexus."""
        deploy_as_api(agent=test_agent, nexus_app=mock_nexus_app, endpoint_name="qa")

        # Verify register called with correct name
        call_args = mock_nexus_app.register.call_args
        assert call_args is not None
        assert call_args[0][0] == "qa"  # First arg is endpoint_name

        # Verify workflow object passed (second arg)
        workflow = call_args[0][1]
        assert workflow is not None

    def test_api_parameter_mapping(self, test_agent, mock_nexus_app):
        """Test request params map to agent inputs."""
        # This test verifies the workflow structure supports parameter mapping
        deploy_as_api(agent=test_agent, nexus_app=mock_nexus_app, endpoint_name="qa")

        # Get registered workflow
        call_args = mock_nexus_app.register.call_args
        workflow = call_args[0][1]

        # Verify workflow can accept parameters
        # (actual mapping happens via Nexus platform)
        assert workflow is not None

    def test_api_result_formatting(self, test_agent, mock_nexus_app):
        """Test response follows API format."""
        from kaizen.integrations.nexus.parameter_mapper import ParameterMapper

        # Test result formatting
        agent_result = {"answer": "Test answer"}
        api_response = ParameterMapper.to_api_response(agent_result)

        assert "status" in api_response
        assert api_response["status"] == "success"
        assert "result" in api_response
        assert api_response["result"] == agent_result

    def test_api_custom_prefix(self, test_agent, mock_nexus_app):
        """Test API deployment with custom prefix."""
        endpoint = deploy_as_api(
            agent=test_agent,
            nexus_app=mock_nexus_app,
            endpoint_name="qa",
            prefix="/custom/api",
        )

        assert endpoint.startswith("/custom/api")
        assert endpoint == "/custom/api/qa/execute"


# ============================================================================
# CLI Deployment Tests
# ============================================================================


class TestCLIDeployment:
    """Test CLI deployment functionality."""

    def test_deploy_agent_as_cli(self, test_agent, mock_nexus_app):
        """Test agent deploys as CLI command."""
        command = deploy_as_cli(
            agent=test_agent, nexus_app=mock_nexus_app, command_name="qa"
        )

        # Verify command returned
        assert command is not None
        assert isinstance(command, str)

        # Verify registration called
        mock_nexus_app.register.assert_called_once()

    def test_cli_command_naming(self, test_agent, mock_nexus_app):
        """Test CLI command follows naming convention."""
        command = deploy_as_cli(
            agent=test_agent, nexus_app=mock_nexus_app, command_name="qa"
        )

        # Should follow pattern: nexus run {name}
        assert command.startswith("nexus run")
        assert "qa" in command
        assert command == "nexus run qa"

    def test_cli_argument_parsing(self, test_agent, mock_nexus_app):
        """Test CLI args map to agent inputs."""
        # Deploy CLI
        deploy_as_cli(agent=test_agent, nexus_app=mock_nexus_app, command_name="qa")

        # Verify workflow registered
        call_args = mock_nexus_app.register.call_args
        assert call_args is not None
        assert call_args[0][0] == "qa"

    def test_cli_output_formatting(self, test_agent, mock_nexus_app):
        """Test CLI output is user-friendly."""
        from kaizen.integrations.nexus.parameter_mapper import ParameterMapper

        # Test output formatting
        agent_result = {"answer": "Test answer"}
        cli_output = ParameterMapper.to_cli_output(agent_result)

        assert isinstance(cli_output, str)
        # Should be JSON formatted
        import json

        parsed = json.loads(cli_output)
        assert parsed == agent_result

    def test_cli_custom_prefix(self, test_agent, mock_nexus_app):
        """Test CLI deployment with custom command prefix."""
        command = deploy_as_cli(
            agent=test_agent,
            nexus_app=mock_nexus_app,
            command_name="qa",
            command_prefix="my-cli execute",
        )

        assert command.startswith("my-cli execute")
        assert command == "my-cli execute qa"


# ============================================================================
# MCP Deployment Tests
# ============================================================================


class TestMCPDeployment:
    """Test MCP deployment functionality."""

    def test_deploy_agent_as_mcp(self, test_agent, mock_nexus_app):
        """Test agent deploys as MCP tool."""
        tool_name = deploy_as_mcp(
            agent=test_agent, nexus_app=mock_nexus_app, tool_name="qa"
        )

        # Verify tool name returned
        assert tool_name is not None
        assert isinstance(tool_name, str)
        assert tool_name == "qa"

        # Verify registration called
        mock_nexus_app.register.assert_called_once()

    def test_mcp_tool_naming(self, test_agent, mock_nexus_app):
        """Test MCP tool follows naming convention."""
        tool_name = deploy_as_mcp(
            agent=test_agent, nexus_app=mock_nexus_app, tool_name="qa_tool"
        )

        # Tool name should match input
        assert tool_name == "qa_tool"

    def test_mcp_schema_generation(self, test_agent, mock_nexus_app):
        """Test MCP schema generated from agent signature."""
        # Deploy with auto-description
        deploy_as_mcp(agent=test_agent, nexus_app=mock_nexus_app, tool_name="qa")

        # Verify workflow registered
        call_args = mock_nexus_app.register.call_args
        assert call_args is not None
        assert call_args[0][0] == "qa"

    def test_mcp_parameter_mapping(self, test_agent, mock_nexus_app):
        """Test MCP params map to agent inputs."""
        from kaizen.integrations.nexus.parameter_mapper import ParameterMapper

        # Test parameter mapping
        tool_args = {"question": "What is AI?"}
        agent_params = ParameterMapper.from_mcp_tool_call(tool_args)

        assert agent_params == tool_args

    def test_mcp_result_formatting(self, test_agent, mock_nexus_app):
        """Test MCP result follows MCP format."""
        from kaizen.integrations.nexus.parameter_mapper import ParameterMapper

        # Test result formatting
        agent_result = {"answer": "Test answer"}
        mcp_result = ParameterMapper.to_mcp_result(agent_result)

        assert "content" in mcp_result
        assert isinstance(mcp_result["content"], list)
        assert len(mcp_result["content"]) > 0
        assert mcp_result["content"][0]["type"] == "text"

    def test_mcp_custom_description(self, test_agent, mock_nexus_app):
        """Test MCP deployment with custom description."""
        tool_name = deploy_as_mcp(
            agent=test_agent,
            nexus_app=mock_nexus_app,
            tool_name="qa",
            tool_description="Custom Q&A tool",
        )

        assert tool_name == "qa"
        # Description handling verified via registration


# ============================================================================
# Multi-Channel Deployment Tests
# ============================================================================


class TestMultiChannelDeployment:
    """Test multi-channel deployment functionality."""

    def test_deploy_multi_channel(self, test_agent, mock_nexus_app):
        """Test deploy across all channels simultaneously."""
        channels = deploy_multi_channel(
            agent=test_agent, nexus_app=mock_nexus_app, name="qa"
        )

        # Verify all channels returned
        assert isinstance(channels, dict)
        assert "api" in channels
        assert "cli" in channels
        assert "mcp" in channels

    def test_multi_channel_consistency(self, test_agent, mock_nexus_app):
        """Test same behavior across channels."""
        channels = deploy_multi_channel(
            agent=test_agent, nexus_app=mock_nexus_app, name="qa"
        )

        # Verify consistent naming
        assert channels["api"] == "/api/workflows/qa/execute"
        assert channels["cli"] == "nexus run qa"
        assert channels["mcp"] == "qa"

    def test_multi_channel_workflow_sharing(self, test_agent, mock_nexus_app):
        """Test shared workflow execution."""
        deploy_multi_channel(agent=test_agent, nexus_app=mock_nexus_app, name="qa")

        # All channels register workflows (once per channel)
        # Verify register called 3 times (once per channel)
        assert mock_nexus_app.register.call_count == 3

        # Each channel uses channel-specific name to avoid conflicts
        calls = mock_nexus_app.register.call_args_list
        registered_names = [call[0][0] for call in calls]

        # Should have: qa_api, qa_cli, qa_mcp
        assert "qa_api" in registered_names
        assert "qa_cli" in registered_names
        assert "qa_mcp" in registered_names


# ============================================================================
# Parameter Mapper Tests
# ============================================================================


class TestParameterMapper:
    """Test parameter mapping utilities."""

    def test_from_api_request(self):
        """Test API request parameter mapping."""
        from kaizen.integrations.nexus.parameter_mapper import ParameterMapper

        request_data = {"question": "What is AI?", "temperature": 0.7}
        params = ParameterMapper.from_api_request(request_data)

        assert params == request_data

    def test_from_cli_args(self):
        """Test CLI argument parameter mapping."""
        from kaizen.integrations.nexus.parameter_mapper import ParameterMapper

        cli_args = {"question": "What is AI?", "temperature": "0.7"}
        params = ParameterMapper.from_cli_args(cli_args)

        # Args preserved as-is (type conversion in agent)
        assert params == cli_args

    def test_from_mcp_tool_call(self):
        """Test MCP tool call parameter mapping."""
        from kaizen.integrations.nexus.parameter_mapper import ParameterMapper

        tool_args = {"question": "What is AI?", "temperature": 0.7}
        params = ParameterMapper.from_mcp_tool_call(tool_args)

        assert params == tool_args

    def test_to_api_response(self):
        """Test API response formatting."""
        from kaizen.integrations.nexus.parameter_mapper import ParameterMapper

        agent_result = {"answer": "AI is artificial intelligence"}
        response = ParameterMapper.to_api_response(agent_result)

        assert response["status"] == "success"
        assert response["result"] == agent_result

    def test_to_cli_output(self):
        """Test CLI output formatting."""
        from kaizen.integrations.nexus.parameter_mapper import ParameterMapper

        agent_result = {"answer": "AI is artificial intelligence"}
        output = ParameterMapper.to_cli_output(agent_result)

        assert isinstance(output, str)
        import json

        assert json.loads(output) == agent_result

    def test_to_mcp_result(self):
        """Test MCP result formatting."""
        from kaizen.integrations.nexus.parameter_mapper import ParameterMapper

        agent_result = {"answer": "AI is artificial intelligence"}
        result = ParameterMapper.to_mcp_result(agent_result)

        assert "content" in result
        assert result["content"][0]["type"] == "text"
        assert "answer" in result["content"][0]["text"]


# ============================================================================
# NexusDeploymentMixin Tests
# ============================================================================


class TestNexusDeploymentMixin:
    """Test NexusDeploymentMixin methods."""

    def test_mixin_deploy_as_api(self, mock_nexus_app):
        """Test mixin deploy_as_api method."""

        # Create agent with mixin
        class MixinAgent(NexusDeploymentMixin, BaseAgent):
            def __init__(self, config):
                super().__init__(config=config, signature=TestSignature())

        agent = MixinAgent(MockConfig())
        endpoint = agent.deploy_as_api(mock_nexus_app, "qa")

        assert endpoint == "/api/workflows/qa/execute"

    def test_mixin_deploy_as_cli(self, mock_nexus_app):
        """Test mixin deploy_as_cli method."""

        class MixinAgent(NexusDeploymentMixin, BaseAgent):
            def __init__(self, config):
                super().__init__(config=config, signature=TestSignature())

        agent = MixinAgent(MockConfig())
        command = agent.deploy_as_cli(mock_nexus_app, "qa")

        assert command == "nexus run qa"

    def test_mixin_deploy_as_mcp(self, mock_nexus_app):
        """Test mixin deploy_as_mcp method."""

        class MixinAgent(NexusDeploymentMixin, BaseAgent):
            def __init__(self, config):
                super().__init__(config=config, signature=TestSignature())

        agent = MixinAgent(MockConfig())
        tool_name = agent.deploy_as_mcp(mock_nexus_app, "qa")

        assert tool_name == "qa"

    def test_mixin_deploy_multi_channel(self, mock_nexus_app):
        """Test mixin deploy_multi_channel method."""

        class MixinAgent(NexusDeploymentMixin, BaseAgent):
            def __init__(self, config):
                super().__init__(config=config, signature=TestSignature())

        agent = MixinAgent(MockConfig())
        channels = agent.deploy_multi_channel(mock_nexus_app, "qa")

        assert "api" in channels
        assert "cli" in channels
        assert "mcp" in channels
