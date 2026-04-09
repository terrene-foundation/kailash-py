"""
Test WorkflowGenerator drops response_format for Gemini when MCP tools are present.

Regression test for gh#357: When tools are discovered via MCP and the provider is
Google/Gemini, response_format (which translates to response_mime_type on the
Gemini side) must be removed from node_config because Gemini rejects the
combination of response_mime_type + tools in a single request.

The prompt-based JSON suffix is used as fallback instead.
"""

from unittest.mock import MagicMock, patch

import pytest

from kaizen.core.config import BaseAgentConfig
from kaizen.core.workflow_generator import WorkflowGenerator
from kaizen.signatures import InputField, OutputField, Signature


class ToolTestSignature(Signature):
    """Test signature for tool + response_format conflict."""

    query: str = InputField(desc="User query")
    result: str = OutputField(desc="Result")


class TestWorkflowGeneratorGeminiToolsConflict:
    """Regression tests for gh#357: response_format dropped when Gemini + tools."""

    def _make_agent_with_tools(self, tools_list):
        """Create a mock agent that returns pre-cached MCP tools."""
        agent = MagicMock()
        agent._discovered_mcp_tools = {"test_server": tools_list}
        agent.discover_mcp_tools = MagicMock()
        return agent

    def _sample_tools(self):
        """Return a list of sample MCP tool dicts in OpenAI format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "mcp__test__search",
                    "description": "Search documents",
                    "parameters": {
                        "type": "object",
                        "properties": {"q": {"type": "string"}},
                    },
                },
            }
        ]

    @patch("kaizen.core.tool_formatters.get_tools_for_provider")
    def test_google_provider_drops_response_format_when_tools_present(
        self, mock_get_tools
    ):
        """When provider is 'google' and MCP tools are discovered,
        response_format must be removed from node_config."""
        mock_get_tools.return_value = self._sample_tools()

        config = BaseAgentConfig(
            llm_provider="google",
            model="gemini-2.0-flash",
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "ToolTestSignature",
                    "strict": True,
                    "schema": {"type": "object"},
                },
            },
            structured_output_mode="explicit",
        )

        agent = self._make_agent_with_tools(self._sample_tools())
        generator = WorkflowGenerator(
            config=config, signature=ToolTestSignature(), agent=agent
        )
        workflow = generator.generate_signature_workflow()

        node_id = list(workflow.nodes.keys())[0]
        node = workflow.nodes[node_id]

        # tools must be present
        assert "tools" in node["config"]
        assert len(node["config"]["tools"]) == 1

        # response_format must be REMOVED for Gemini + tools
        assert (
            "response_format" not in node["config"]
        ), "response_format should be dropped when Gemini provider has tools (gh#357)"

    @patch("kaizen.core.tool_formatters.get_tools_for_provider")
    def test_gemini_alias_drops_response_format_when_tools_present(
        self, mock_get_tools
    ):
        """The 'gemini' alias should behave identically to 'google'."""
        mock_get_tools.return_value = self._sample_tools()

        config = BaseAgentConfig(
            llm_provider="gemini",
            model="gemini-2.5-flash",
            response_format={"type": "json_object"},
            structured_output_mode="explicit",
        )

        agent = self._make_agent_with_tools(self._sample_tools())
        generator = WorkflowGenerator(
            config=config, signature=ToolTestSignature(), agent=agent
        )
        workflow = generator.generate_signature_workflow()

        node_id = list(workflow.nodes.keys())[0]
        node = workflow.nodes[node_id]

        assert "tools" in node["config"]
        assert (
            "response_format" not in node["config"]
        ), "response_format should be dropped for 'gemini' alias too (gh#357)"

    @patch("kaizen.core.tool_formatters.get_tools_for_provider")
    def test_openai_provider_keeps_response_format_with_tools(self, mock_get_tools):
        """OpenAI supports tools + response_format together -- must NOT drop it."""
        mock_get_tools.return_value = self._sample_tools()

        config = BaseAgentConfig(
            llm_provider="openai",
            model="gpt-4o",
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "ToolTestSignature",
                    "strict": True,
                    "schema": {"type": "object"},
                },
            },
            structured_output_mode="explicit",
        )

        agent = self._make_agent_with_tools(self._sample_tools())
        generator = WorkflowGenerator(
            config=config, signature=ToolTestSignature(), agent=agent
        )
        workflow = generator.generate_signature_workflow()

        node_id = list(workflow.nodes.keys())[0]
        node = workflow.nodes[node_id]

        assert "tools" in node["config"]
        # OpenAI should KEEP response_format
        assert (
            "response_format" in node["config"]
        ), "response_format must be preserved for OpenAI even with tools"

    @patch("kaizen.core.tool_formatters.get_tools_for_provider")
    def test_google_provider_keeps_response_format_without_tools(self, mock_get_tools):
        """When no tools are discovered, response_format should remain for Gemini."""
        # Return empty tools -- simulates no MCP tools discovered
        mock_get_tools.return_value = []

        config = BaseAgentConfig(
            llm_provider="google",
            model="gemini-2.0-flash",
            response_format={"type": "json_object"},
            structured_output_mode="explicit",
        )

        # Agent with no cached tools
        agent = MagicMock()
        agent._discovered_mcp_tools = {}
        agent.discover_mcp_tools = MagicMock()

        generator = WorkflowGenerator(
            config=config, signature=ToolTestSignature(), agent=agent
        )
        workflow = generator.generate_signature_workflow()

        node_id = list(workflow.nodes.keys())[0]
        node = workflow.nodes[node_id]

        # No tools discovered, so tools should not be in config
        assert "tools" not in node["config"]
        # response_format should be preserved since there are no tools
        assert "response_format" in node["config"]
        assert node["config"]["response_format"] == {"type": "json_object"}
