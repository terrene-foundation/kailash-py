"""
Tier 1 Unit Tests for BaseAgent MCP Auto-Connection

Tests the automatic connection to builtin MCP server.
"""

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import InputField, OutputField, Signature


class TestSignature(Signature):
    """Simple test signature."""

    input: str = InputField(description="Test input")
    output: str = OutputField(description="Test output")


class TestBaseAgentMCPAutoConnection:
    """Test BaseAgent automatically connects to builtin MCP server."""

    def test_auto_connect_when_mcp_servers_none(self):
        """Test BaseAgent auto-connects when mcp_servers=None (default)."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        agent = BaseAgent(config=config, signature=TestSignature())

        # Should auto-connect to kaizen_builtin
        assert agent._mcp_servers is not None
        assert len(agent._mcp_servers) == 1
        assert agent._mcp_servers[0]["name"] == "kaizen_builtin"
        assert agent._mcp_client is not None

    def test_auto_connect_server_configuration(self):
        """Test auto-connected server has correct configuration."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        agent = BaseAgent(config=config, signature=TestSignature())

        server_config = agent._mcp_servers[0]
        assert server_config["name"] == "kaizen_builtin"
        assert server_config["command"] == "python"
        assert server_config["args"] == ["-m", "kaizen.mcp.builtin_server"]
        assert server_config["transport"] == "stdio"
        assert "description" in server_config

    def test_explicit_empty_list_disables_mcp(self):
        """Test mcp_servers=[] disables MCP integration."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        agent = BaseAgent(config=config, signature=TestSignature(), mcp_servers=[])

        # Should NOT connect to any MCP server
        assert agent._mcp_servers == []
        assert agent._mcp_client is None

    def test_custom_mcp_servers_used(self):
        """Test custom mcp_servers override auto-connection."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        custom_servers = [
            {"name": "custom_server", "command": "custom-mcp", "transport": "stdio"}
        ]
        agent = BaseAgent(
            config=config, signature=TestSignature(), mcp_servers=custom_servers
        )

        # Should use custom servers, NOT auto-connect
        assert agent._mcp_servers == custom_servers
        assert agent._mcp_servers[0]["name"] == "custom_server"
        assert agent._mcp_client is not None

    def test_mcp_discovery_caches_initialized(self):
        """Test MCP discovery caches are initialized when MCP enabled."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        agent = BaseAgent(config=config, signature=TestSignature())

        # Auto-connection should initialize caches
        assert hasattr(agent, "_discovered_mcp_tools")
        assert hasattr(agent, "_discovered_mcp_resources")
        assert hasattr(agent, "_discovered_mcp_prompts")
        assert isinstance(agent._discovered_mcp_tools, dict)
        assert isinstance(agent._discovered_mcp_resources, dict)
        assert isinstance(agent._discovered_mcp_prompts, dict)

    def test_mcp_caches_empty_when_disabled(self):
        """Test MCP caches exist but client is None when MCP disabled."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        agent = BaseAgent(config=config, signature=TestSignature(), mcp_servers=[])

        # Caches should exist but client should be None
        assert agent._mcp_client is None
        assert isinstance(agent._discovered_mcp_tools, dict)
        assert isinstance(agent._discovered_mcp_resources, dict)
        assert isinstance(agent._discovered_mcp_prompts, dict)


class TestBaseAgentBackwardCompatibility:
    """Test BaseAgent changes don't break existing functionality."""

    def test_agent_creation_without_mcp_param(self):
        """Test creating agent without mcp_servers parameter works."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        agent = BaseAgent(config=config, signature=TestSignature())

        # Should create successfully
        assert agent is not None
        assert agent.config.llm_provider == "openai"
        assert agent.config.model == "gpt-4"

    def test_agent_with_other_params_unaffected(self):
        """Test other BaseAgent parameters still work correctly."""
        config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        agent = BaseAgent(
            config=config, signature=TestSignature(), agent_id="test_agent_123"
        )

        assert agent.agent_id == "test_agent_123"
        assert agent.signature is not None
        assert agent.config is not None

    def test_domain_config_auto_conversion_still_works(self):
        """Test domain config auto-conversion still works with MCP."""
        from dataclasses import dataclass

        @dataclass
        class CustomConfig:
            llm_provider: str = "openai"
            model: str = "gpt-4"
            custom_param: str = "value"

        agent = BaseAgent(config=CustomConfig(), signature=TestSignature())

        # Should auto-convert and auto-connect to MCP
        assert isinstance(agent.config, BaseAgentConfig)
        assert agent.config.llm_provider == "openai"
        assert agent._mcp_servers is not None  # Auto-connected
