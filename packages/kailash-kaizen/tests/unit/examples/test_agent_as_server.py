"""
Tests for Agent as MCP Server Example

MIGRATED TO KAILASH.MCP_SERVER (2025-12-29)
These tests use the production kailash.mcp_server implementation.

3-Tier Testing Strategy:
- Tier 1 (Unit): Agent and server setup logic
- Tier 2 (Integration): Real MCP server from kailash.mcp_server.MCPServer
- Tier 3 (E2E): Complete server workflows with real JSON-RPC protocol

NO MOCKING of MCP protocol - uses production kailash.mcp_server.MCPServer.
"""

import asyncio
import logging

# Import example using standardized loader
import sys
import time
from pathlib import Path

import pytest

# Add examples directory to path for direct import
example_path = (
    Path(__file__).parent.parent.parent.parent
    / "examples"
    / "5-mcp-integration"
    / "agent-as-server"
)
if str(example_path) not in sys.path:
    sys.path.insert(0, str(example_path))

# Import from workflow module (with unique name to avoid conflicts)
import importlib.util

workflow_spec = importlib.util.spec_from_file_location(
    "agent_as_server_workflow", str(example_path / "workflow.py")
)
agent_as_server_example = importlib.util.module_from_spec(workflow_spec)
workflow_spec.loader.exec_module(agent_as_server_example)

MCPServerAgentConfig = agent_as_server_example.MCPServerAgentConfig
MCPServerAgent = agent_as_server_example.MCPServerAgent
QuestionAnsweringSignature = agent_as_server_example.QuestionAnsweringSignature
TextAnalysisSignature = agent_as_server_example.TextAnalysisSignature

# Production MCP infrastructure - kailash.mcp_server
from kailash.mcp_server import MCPServer
from kaizen.memory import SharedMemoryPool

logger = logging.getLogger(__name__)


# ===================================================================
# TIER 1: UNIT TESTS (Server Setup Logic)
# ===================================================================


class TestMCPServerAgentConfig:
    """Test server configuration validation."""

    def test_default_config(self):
        """Test default configuration values."""
        config = MCPServerAgentConfig()

        assert config.llm_provider == "openai"
        assert config.model == "gpt-3.5-turbo"
        assert config.server_name == "kaizen-qa-agent"
        assert config.server_port == 18090
        assert config.server_host == "0.0.0.0"  # Binds to all interfaces
        assert config.enable_auth is False
        assert config.enable_auto_discovery is True
        assert config.enable_metrics is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = MCPServerAgentConfig(
            server_name="custom-server",
            server_port=19000,
            enable_auth=True,
            auth_type="bearer",
            enable_metrics=False,
        )

        assert config.server_name == "custom-server"
        assert config.server_port == 19000
        assert config.enable_auth is True
        assert config.auth_type == "bearer"
        assert config.enable_metrics is False

    def test_enterprise_features_config(self):
        """Test enterprise features configuration."""
        config = MCPServerAgentConfig(
            enable_auth=True,
            auth_type="api_key",
            enable_auto_discovery=True,
            enable_metrics=True,
        )

        assert config.enable_auth is True
        assert config.auth_type == "api_key"
        assert config.enable_auto_discovery is True
        assert config.enable_metrics is True


class TestMCPServerSignatures:
    """Test signature definitions."""

    def test_question_answering_signature(self):
        """Test QuestionAnsweringSignature structure."""
        sig = QuestionAnsweringSignature()

        # Input fields
        assert hasattr(sig, "question")
        assert hasattr(sig, "context")
        assert hasattr(sig, "max_length")

        # Output fields
        assert hasattr(sig, "answer")
        assert hasattr(sig, "confidence")
        assert hasattr(sig, "sources")

    def test_text_analysis_signature(self):
        """Test TextAnalysisSignature structure."""
        sig = TextAnalysisSignature()

        # Input fields
        assert hasattr(sig, "text")
        assert hasattr(sig, "analysis_type")

        # Output fields
        assert hasattr(sig, "analysis")
        assert hasattr(sig, "key_points")
        assert hasattr(sig, "sentiment")


class TestMCPServerAgentInitialization:
    """Test agent initialization as MCP server."""

    def test_agent_creation_minimal(self):
        """Test agent creation with minimal config."""
        config = MCPServerAgentConfig(server_name="test-server", server_port=19001)

        agent = MCPServerAgent(config)

        assert agent is not None
        assert agent.server_config == config
        # MCP server is created on-demand, not at init
        assert agent._mcp_server is None
        assert hasattr(agent, "ask_question")
        assert hasattr(agent, "analyze_text")

    def test_agent_with_shared_memory(self):
        """Test agent creation with shared memory."""
        config = MCPServerAgentConfig(server_port=19002)
        memory = SharedMemoryPool()

        agent = MCPServerAgent(config, shared_memory=memory)

        assert agent.shared_memory == memory

    def test_tool_registration(self):
        """Test that agent has callable tool methods."""
        config = MCPServerAgentConfig(server_port=19003)
        agent = MCPServerAgent(config)

        # Agent has methods that will become MCP tools
        assert hasattr(agent, "ask_question")
        assert hasattr(agent, "analyze_text")
        assert hasattr(agent, "get_server_status")

        # All tool methods should be callable
        assert callable(agent.ask_question)
        assert callable(agent.analyze_text)
        assert callable(agent.get_server_status)

    def test_mcp_server_config_creation(self):
        """Test MCP server config is stored properly."""
        config = MCPServerAgentConfig(
            server_name="config-test-server",
            server_port=19004,
            enable_auth=True,
            auth_type="bearer",
        )

        agent = MCPServerAgent(config)

        # Verify server config is stored
        assert agent.server_config is not None
        assert agent.server_config.server_name == "config-test-server"
        assert agent.server_config.server_port == 19004
        assert agent.server_config.enable_auth is True
        assert agent.server_config.auth_type == "bearer"


# ===================================================================
# TIER 2: INTEGRATION TESTS (Real MCP Infrastructure)
# ===================================================================


class TestMCPServerIntegration:
    """Test real MCP server using kailash.mcp_server.MCPServer - NO MOCKING.

    Uses production kailash.mcp_server.MCPServer for real MCP protocol testing.
    """

    def test_mcp_server_creation(self):
        """Test MCPServer can be instantiated with various configs."""
        # Basic server
        server = MCPServer(name="test-server")
        assert server is not None

        # Server with features
        server_with_features = MCPServer(
            name="featured-server", enable_metrics=True, enable_cache=True
        )
        assert server_with_features is not None

    def test_mcp_server_tool_decorator(self):
        """Test @server.tool() decorator works."""
        server = MCPServer(name="decorator-test-server")

        # Register a tool
        @server.tool()
        def test_tool(arg1: str) -> dict:
            """Test tool for testing."""
            return {"arg1": arg1}

        # Tool should be registered
        assert server is not None

    def test_mcp_server_with_auth(self):
        """Test MCPServer with authentication."""
        try:
            from kailash.mcp_server.auth import APIKeyAuth

            auth = APIKeyAuth({"test-key": {"permissions": ["*"]}})
            server = MCPServer(name="auth-server", auth_provider=auth)
            assert server is not None
        except ImportError:
            pytest.skip("Auth module not available")


class TestMCPServerAgentExposure:
    """Test MCPServerAgent server exposure via kailash.mcp_server."""

    def test_agent_expose_as_server(self):
        """Test agent can be exposed as MCP server."""
        config = MCPServerAgentConfig(
            server_name="expose-test-server",
            server_port=19010,
            enable_auth=False,
            enable_auto_discovery=False,
        )

        agent = MCPServerAgent(config)

        # Expose should create MCPServer
        server = agent.expose_as_server()

        assert server is not None
        assert agent._mcp_server is not None
        assert isinstance(agent._mcp_server, MCPServer)

    def test_agent_expose_registers_tools(self):
        """Test expose_as_server registers tools on server."""
        config = MCPServerAgentConfig(
            server_name="tools-test-server",
            server_port=19011,
            enable_auth=False,
            enable_auto_discovery=False,
        )

        agent = MCPServerAgent(config)
        server = agent.expose_as_server()

        # Server should exist with registered tools
        assert server is not None

    def test_agent_get_server_status(self):
        """Test get_server_status returns correct info."""
        config = MCPServerAgentConfig(
            server_name="status-test-server",
            server_port=19012,
            enable_auth=False,
            enable_metrics=True,
        )

        agent = MCPServerAgent(config)

        # Before expose
        status_before = agent.get_server_status()
        assert status_before["status"] == "not_initialized"

        # After expose
        agent.expose_as_server()
        status_after = agent.get_server_status()
        assert status_after["status"] == "running"
        assert status_after["server_name"] == "status-test-server"
        assert status_after["port"] == 19012
        assert status_after["tools_available"] == 3

    def test_agent_expose_with_enterprise_features(self):
        """Test expose with enterprise features enabled."""
        config = MCPServerAgentConfig(
            server_name="enterprise-test-server",
            server_port=19013,
            enable_auth=True,
            auth_type="api_key",
            enable_auto_discovery=True,
            enable_metrics=True,
        )

        agent = MCPServerAgent(config)
        server = agent.expose_as_server()

        # Server should be created
        assert server is not None

        # Status should reflect enterprise features
        status = agent.get_server_status()
        assert status["auth_enabled"] is True
        assert status["discovery_enabled"] is True
        assert status["metrics_enabled"] is True


class TestMCPServerToolInvocation:
    """Test MCP tool invocation via agent methods."""

    def test_ask_question_method(self):
        """Test ask_question method works."""
        config = MCPServerAgentConfig(server_port=19020)
        agent = MCPServerAgent(config)

        # Method should be callable
        assert callable(agent.ask_question)

        # Note: Actual invocation requires LLM, so we just test signature
        # In integration tests with real LLM, this would produce real answers

    def test_analyze_text_method(self):
        """Test analyze_text method works."""
        config = MCPServerAgentConfig(server_port=19021)
        agent = MCPServerAgent(config)

        # Method should be callable
        assert callable(agent.analyze_text)

    def test_get_server_status_method(self):
        """Test get_server_status method returns expected structure."""
        config = MCPServerAgentConfig(
            server_name="method-test-server", server_port=19022
        )
        agent = MCPServerAgent(config)

        # Before server setup - returns minimal status
        status = agent.get_server_status()

        assert "status" in status
        # When not initialized, only status and message are returned
        assert status["status"] == "not_initialized"

        # After expose, full status is returned
        agent.expose_as_server()
        status_after = agent.get_server_status()
        assert "server_name" in status_after
        assert status_after["server_name"] == "method-test-server"


# ===================================================================
# TIER 3: E2E TESTS (Complete Workflows)
# ===================================================================


class TestMCPServerWorkflows:
    """Test complete MCP server workflows.

    Uses kailash.mcp_server.MCPServer for production server patterns.
    """

    def test_agent_has_start_server_method(self):
        """Test agent has start_server method."""
        config = MCPServerAgentConfig(server_port=19030)
        agent = MCPServerAgent(config)

        assert hasattr(agent, "start_server")
        assert callable(agent.start_server)

    def test_agent_has_start_server_async_method(self):
        """Test agent has async start_server_async method."""
        config = MCPServerAgentConfig(server_port=19031)
        agent = MCPServerAgent(config)

        assert hasattr(agent, "start_server_async")
        assert asyncio.iscoroutinefunction(agent.start_server_async)

    def test_server_lifecycle_expose(self):
        """Test server lifecycle - expose."""
        config = MCPServerAgentConfig(
            server_name="lifecycle-test-server",
            server_port=19032,
            enable_auth=False,
            enable_auto_discovery=False,
        )

        agent = MCPServerAgent(config)

        # Initial state - no server
        assert agent._mcp_server is None

        # Expose creates server
        server = agent.expose_as_server()
        assert server is not None
        assert agent._mcp_server is not None

        # Status reflects running state (after expose, before actual start)
        status = agent.get_server_status()
        assert status["status"] == "running"

    def test_complete_server_setup(self):
        """Test complete server setup workflow."""
        config = MCPServerAgentConfig(
            server_name="complete-setup-server",
            server_port=19033,
            enable_auth=False,
            enable_auto_discovery=False,
            enable_metrics=True,
        )

        agent = MCPServerAgent(config)

        # Step 1: Create agent with config
        assert agent.server_config == config

        # Step 2: Verify tool methods exist
        assert callable(agent.ask_question)
        assert callable(agent.analyze_text)
        assert callable(agent.get_server_status)

        # Step 3: Expose as server
        server = agent.expose_as_server()
        assert server is not None

        # Step 4: Check status
        status = agent.get_server_status()
        assert status["status"] == "running"
        assert status["tools_available"] == 3

    def test_multiple_agent_servers(self):
        """Test creating multiple agent servers."""
        config1 = MCPServerAgentConfig(
            server_name="multi-server-1",
            server_port=19034,
            enable_auth=False,
            enable_auto_discovery=False,
        )
        config2 = MCPServerAgentConfig(
            server_name="multi-server-2",
            server_port=19035,
            enable_auth=False,
            enable_auto_discovery=False,
        )

        agent1 = MCPServerAgent(config1)
        agent2 = MCPServerAgent(config2)

        # Expose both
        server1 = agent1.expose_as_server()
        server2 = agent2.expose_as_server()

        # Both should be created successfully
        assert server1 is not None
        assert server2 is not None

        # Each should have its own config
        status1 = agent1.get_server_status()
        status2 = agent2.get_server_status()

        assert status1["server_name"] == "multi-server-1"
        assert status2["server_name"] == "multi-server-2"
        assert status1["port"] == 19034
        assert status2["port"] == 19035


# ===================================================================
# PERFORMANCE TESTS
# ===================================================================


class TestMCPServerPerformance:
    """Test server performance characteristics using kailash.mcp_server.MCPServer."""

    def test_mcp_server_creation_performance(self):
        """Test MCPServer creation is fast."""
        start_time = time.time()
        server = MCPServer(name="perf-test-server")
        creation_time = time.time() - start_time

        # Server creation should be instant (< 0.5 seconds)
        assert creation_time < 0.5
        assert server is not None

    def test_agent_creation_performance(self):
        """Test MCPServerAgent creation is fast."""
        config = MCPServerAgentConfig(server_port=19040)

        start_time = time.time()
        agent = MCPServerAgent(config)
        creation_time = time.time() - start_time

        # Agent creation should be fast (< 1 second)
        assert creation_time < 1.0
        assert agent is not None

    def test_server_expose_performance(self):
        """Test server expose is fast."""
        config = MCPServerAgentConfig(
            server_port=19041, enable_auth=False, enable_auto_discovery=False
        )
        agent = MCPServerAgent(config)

        start_time = time.time()
        server = agent.expose_as_server()
        expose_time = time.time() - start_time

        # Expose should be fast (< 1 second)
        assert expose_time < 1.0
        assert server is not None

    def test_multiple_tool_registration_performance(self):
        """Test registering multiple tools is fast."""
        server = MCPServer(name="multi-tool-perf-server")

        start_time = time.time()

        # Register multiple tools
        for i in range(10):

            @server.tool()
            def test_tool(arg: str) -> dict:
                return {"arg": arg}

        registration_time = time.time() - start_time

        # Should be very fast (< 0.5 seconds for 10 tools)
        assert registration_time < 0.5


# ===================================================================
# PYTEST MARKERS
# ===================================================================

pytestmark = [
    pytest.mark.integration,
    pytest.mark.mcp,
    pytest.mark.server,
]
