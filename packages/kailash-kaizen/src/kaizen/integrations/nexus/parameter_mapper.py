"""Parameter mapping between channels and agent inputs."""

from typing import Any, Dict


class ParameterMapper:
    """Maps channel-specific parameters to agent inputs."""

    @staticmethod
    def from_api_request(request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Map API request JSON to agent parameters."""
        # API uses JSON directly
        return request_data

    @staticmethod
    def from_cli_args(cli_args: Dict[str, str]) -> Dict[str, Any]:
        """Map CLI arguments to agent parameters."""
        # CLI args are strings, convert to appropriate types
        return cli_args  # Type conversion happens in agent

    @staticmethod
    def from_mcp_tool_call(tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """Map MCP tool call arguments to agent parameters."""
        # MCP uses JSON, similar to API
        return tool_args

    @staticmethod
    def to_api_response(agent_result: Dict[str, Any]) -> Dict[str, Any]:
        """Format agent result for API response."""
        return {"status": "success", "result": agent_result}

    @staticmethod
    def to_cli_output(agent_result: Dict[str, Any]) -> str:
        """Format agent result for CLI output."""
        # Format for terminal display
        import json

        return json.dumps(agent_result, indent=2)

    @staticmethod
    def to_mcp_result(agent_result: Dict[str, Any]) -> Dict[str, Any]:
        """Format agent result for MCP response."""
        return {"content": [{"type": "text", "text": str(agent_result)}]}
