"""Adapter for bridging mcp_platform and core SDK parameter formats."""

import logging
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class MCPPlatformAdapter:
    """Adapter to translate between mcp_platform and SDK MCP parameter formats."""

    @staticmethod
    def translate_server_config(platform_config: Dict[str, Any]) -> Dict[str, Any]:
        """Translate mcp_platform server config to SDK format.

        Args:
            platform_config: Server config from mcp_platform

        Returns:
            SDK-compatible server config
        """
        if not isinstance(platform_config, dict):
            logger.error(f"Platform config must be dict, got {type(platform_config)}")
            return {}

        # Extract mcp_platform format: {"transport": "stdio", "command": "...", "args": [...]}
        sdk_config = {}

        # Map required fields
        if "name" not in platform_config:
            # Generate name from command if not provided
            command = platform_config.get("command", "unknown")
            sdk_config["name"] = command.split("/")[-1].split("\\")[-1]
        else:
            sdk_config["name"] = platform_config["name"]

        # Transport mapping
        transport = platform_config.get("transport", "stdio")
        sdk_config["transport"] = transport

        # Command mapping
        if "command" in platform_config:
            sdk_config["command"] = platform_config["command"]

        # Arguments mapping
        if "args" in platform_config:
            sdk_config["args"] = platform_config["args"]
        elif "arguments" in platform_config:
            sdk_config["args"] = platform_config["arguments"]

        # Environment mapping
        if "env" in platform_config:
            sdk_config["env"] = platform_config["env"]
        elif "environment" in platform_config:
            sdk_config["env"] = platform_config["environment"]

        # Server-specific settings
        if "auto_start" in platform_config:
            sdk_config["auto_start"] = platform_config["auto_start"]

        if "timeout" in platform_config:
            sdk_config["timeout"] = platform_config["timeout"]

        # Tool list mapping
        if "tools" in platform_config:
            sdk_config["tools"] = platform_config["tools"]

        logger.debug(f"Translated platform config to SDK format: {sdk_config}")
        return sdk_config

    @staticmethod
    def translate_mcp_servers_list(
        platform_servers: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Translate list of mcp_platform server configs to SDK format.

        Args:
            platform_servers: List of server configs from mcp_platform

        Returns:
            List of SDK-compatible server configs
        """
        if not isinstance(platform_servers, list):
            logger.error(f"Platform servers must be list, got {type(platform_servers)}")
            return []

        sdk_servers = []
        for i, platform_config in enumerate(platform_servers):
            try:
                sdk_config = MCPPlatformAdapter.translate_server_config(platform_config)
                if sdk_config:
                    sdk_servers.append(sdk_config)
                else:
                    logger.warning(
                        f"Failed to translate server config {i}: {platform_config}"
                    )
            except Exception as e:
                logger.error(f"Error translating server config {i}: {e}")

        return sdk_servers

    @staticmethod
    def translate_tool_parameters(
        platform_params: Dict[str, Any], tool_schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Translate mcp_platform tool parameters to SDK format.

        Args:
            platform_params: Parameters from mcp_platform
            tool_schema: Optional tool schema for validation

        Returns:
            SDK-compatible tool parameters
        """
        if not isinstance(platform_params, dict):
            logger.error(f"Platform params must be dict, got {type(platform_params)}")
            return {}

        sdk_params = {}

        # Handle nested server configuration
        if "server_config" in platform_params:
            server_config = platform_params["server_config"]
            sdk_params["mcp_server_config"] = (
                MCPPlatformAdapter.translate_server_config(server_config)
            )

        # Handle tool-specific parameters
        for key, value in platform_params.items():
            if key == "server_config":
                continue  # Already handled above

            # Parameter name mapping
            if key == "tool_name":
                sdk_params["name"] = value
            elif key == "tool_args":
                sdk_params["arguments"] = value
            elif key == "tool_params":
                sdk_params["parameters"] = value
            else:
                sdk_params[key] = value

        # Validate against tool schema if provided
        if tool_schema and "parameters" in tool_schema:
            required_params = tool_schema["parameters"].get("required", [])
            missing_params = [p for p in required_params if p not in sdk_params]
            if missing_params:
                logger.warning(f"Missing required tool parameters: {missing_params}")

        logger.debug(f"Translated tool parameters: {sdk_params}")
        return sdk_params

    @staticmethod
    def translate_llm_agent_config(platform_config: Dict[str, Any]) -> Dict[str, Any]:
        """Translate mcp_platform LLM agent config to SDK format.

        Args:
            platform_config: LLM agent config from mcp_platform

        Returns:
            SDK-compatible LLM agent config
        """
        if not isinstance(platform_config, dict):
            logger.error(f"Platform config must be dict, got {type(platform_config)}")
            return {}

        sdk_config = platform_config.copy()

        # Handle mcp_platform server configuration
        if "server_config" in platform_config:
            server_config = platform_config["server_config"]
            if isinstance(server_config, dict):
                # Single server config
                sdk_config["mcp_servers"] = [
                    MCPPlatformAdapter.translate_server_config(server_config)
                ]
            elif isinstance(server_config, list):
                # Multiple server configs
                sdk_config["mcp_servers"] = (
                    MCPPlatformAdapter.translate_mcp_servers_list(server_config)
                )

            # Remove the old key
            sdk_config.pop("server_config")

        # Handle server_configs (plural) as well
        if "server_configs" in platform_config:
            server_configs = platform_config["server_configs"]
            sdk_config["mcp_servers"] = MCPPlatformAdapter.translate_mcp_servers_list(
                server_configs
            )
            sdk_config.pop("server_configs")

        # Ensure use_real_mcp is set correctly
        if "use_real_mcp" not in sdk_config:
            sdk_config["use_real_mcp"] = True  # Default to real MCP execution

        logger.debug(f"Translated LLM agent config: {sdk_config}")
        return sdk_config

    @staticmethod
    def validate_integration(
        platform_data: Dict[str, Any], expected_sdk_format: str
    ) -> bool:
        """Validate that platform data can be properly translated to SDK format.

        Args:
            platform_data: Data from mcp_platform
            expected_sdk_format: Expected SDK format type ("server_config", "tool_params", "llm_config")

        Returns:
            True if valid for translation, False otherwise
        """
        if not isinstance(platform_data, dict):
            logger.error(f"Platform data must be dict for {expected_sdk_format}")
            return False

        if expected_sdk_format == "server_config":
            required_fields = ["transport"]
            optional_fields = ["command", "name", "args"]

        elif expected_sdk_format == "tool_params":
            required_fields = []
            optional_fields = ["tool_name", "tool_args", "server_config"]

        elif expected_sdk_format == "llm_config":
            required_fields = []
            optional_fields = ["server_config", "server_configs", "mcp_servers"]

        else:
            logger.error(f"Unknown SDK format: {expected_sdk_format}")
            return False

        # Check for required fields
        missing_required = [f for f in required_fields if f not in platform_data]
        if missing_required:
            logger.error(
                f"Missing required fields for {expected_sdk_format}: {missing_required}"
            )
            return False

        # Check if we have at least some relevant fields
        has_relevant_fields = any(
            f in platform_data for f in required_fields + optional_fields
        )
        if not has_relevant_fields:
            logger.warning(f"No relevant fields found for {expected_sdk_format}")
            return False

        return True

    @staticmethod
    def create_error_recovery_config(
        original_config: Any, error_msg: str
    ) -> Dict[str, Any]:
        """Create a recovery configuration when translation fails.

        Args:
            original_config: The original configuration that failed
            error_msg: Error message describing the failure

        Returns:
            Recovery configuration
        """
        return {
            "name": "error_recovery",
            "transport": "stdio",
            "command": "echo",
            "args": ["Error in MCP configuration"],
            "original_config": original_config,
            "error_message": error_msg,
            "recovery_mode": True,
        }
