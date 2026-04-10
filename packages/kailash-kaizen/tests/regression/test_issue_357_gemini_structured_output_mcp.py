"""
Regression: #357 -- BaseAgent MCP auto-discovery breaks structured output on Gemini.

Gemini does not allow function calling and JSON response mode
(response_mime_type: 'application/json') in the same request, causing
a 400 error.  When the agent config requests structured output
(response_format is set), MCP auto-discovery must be suppressed so that
no tools are injected into the LLM request.

Structured output mode takes priority over auto-tool discovery.
"""

import pytest
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import InputField, OutputField, Signature


class SimpleSignature(Signature):
    """Minimal signature for testing."""

    query: str = InputField(description="User query")
    answer: str = OutputField(description="Agent answer")


class TestIssue357GeminiStructuredOutputMCP:
    """Regression tests for #357: structured output suppresses MCP auto-inject."""

    @pytest.mark.regression
    def test_structured_output_json_object_suppresses_mcp_auto_discovery(self):
        """When response_format requests json_object, MCP auto-discovery is skipped."""
        config = BaseAgentConfig(
            llm_provider="google",
            model="gemini-2.0-flash",
            response_format={"type": "json_object"},
        )
        agent = BaseAgent(config=config, signature=SimpleSignature())

        # MCP should NOT be auto-injected
        assert agent._mcp_servers == []
        assert agent._mcp_client is None

    @pytest.mark.regression
    def test_structured_output_json_schema_suppresses_mcp_auto_discovery(self):
        """When response_format requests json_schema, MCP auto-discovery is skipped."""
        config = BaseAgentConfig(
            llm_provider="google",
            model="gemini-2.0-flash",
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "answer_schema",
                    "schema": {
                        "type": "object",
                        "properties": {"answer": {"type": "string"}},
                        "required": ["answer"],
                    },
                },
            },
        )
        agent = BaseAgent(config=config, signature=SimpleSignature())

        assert agent._mcp_servers == []
        assert agent._mcp_client is None

    @pytest.mark.regression
    def test_structured_output_mode_off_does_not_suppress_mcp(self):
        """When structured_output_mode is 'off', MCP auto-discovery proceeds normally."""
        config = BaseAgentConfig(
            llm_provider="google",
            model="gemini-2.0-flash",
            response_format={"type": "json_object"},
            structured_output_mode="off",
        )
        agent = BaseAgent(config=config, signature=SimpleSignature())

        # structured_output_mode='off' means the response_format won't be sent
        # to the provider, so MCP tools are safe to inject
        assert len(agent._mcp_servers) == 1
        assert agent._mcp_servers[0]["name"] == "kaizen_builtin"
        assert agent._mcp_client is not None

    @pytest.mark.regression
    def test_no_structured_output_still_auto_connects_mcp(self):
        """Without structured output, MCP auto-discovery works as before."""
        config = BaseAgentConfig(
            llm_provider="google",
            model="gemini-2.0-flash",
        )
        agent = BaseAgent(config=config, signature=SimpleSignature())

        # No structured output -- MCP should auto-connect
        assert len(agent._mcp_servers) == 1
        assert agent._mcp_servers[0]["name"] == "kaizen_builtin"
        assert agent._mcp_client is not None

    @pytest.mark.regression
    def test_explicit_mcp_servers_override_structured_output_suppression(self):
        """Explicitly provided mcp_servers are used even with structured output."""
        config = BaseAgentConfig(
            llm_provider="google",
            model="gemini-2.0-flash",
            response_format={"type": "json_object"},
        )
        custom_servers = [
            {"name": "my_server", "command": "my-mcp", "transport": "stdio"}
        ]
        agent = BaseAgent(
            config=config, signature=SimpleSignature(), mcp_servers=custom_servers
        )

        # Explicit servers always win -- user takes responsibility for compatibility
        assert len(agent._mcp_servers) == 1
        assert agent._mcp_servers[0]["name"] == "my_server"
        assert agent._mcp_client is not None

    @pytest.mark.regression
    def test_openai_structured_output_also_suppresses_mcp(self):
        """Structured output suppression is provider-agnostic, not Gemini-only."""
        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4",
            response_format={"type": "json_object"},
        )
        agent = BaseAgent(config=config, signature=SimpleSignature())

        # Provider-agnostic: any structured output suppresses auto-MCP
        assert agent._mcp_servers == []
        assert agent._mcp_client is None

    @pytest.mark.regression
    def test_has_structured_output_property(self):
        """BaseAgentConfig.has_structured_output returns correct values."""
        # No response_format
        config_none = BaseAgentConfig(llm_provider="openai", model="gpt-4")
        assert config_none.has_structured_output is False

        # With response_format
        config_json = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4",
            response_format={"type": "json_object"},
        )
        assert config_json.has_structured_output is True

        # With response_format but mode='off'
        config_off = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4",
            response_format={"type": "json_object"},
            structured_output_mode="off",
        )
        assert config_off.has_structured_output is False
