"""Simple parameter injection framework for enterprise nodes.

This module provides a simpler approach to handling runtime parameter injection
for enterprise nodes that require connection configuration.
"""

import logging
from typing import Any, Dict, List, Optional, Union

from kailash.nodes.base import Node

logger = logging.getLogger(__name__)


class DeferredConfigNode(Node):
    """Base class for nodes that support deferred configuration.

    This provides a simple wrapper pattern that delays node creation
    until runtime parameters are available.
    """

    def __init__(self, node_class, **initial_config):
        """Initialize with deferred configuration.

        Args:
            node_class: The actual node class to instantiate later
            **initial_config: Initial configuration parameters
        """
        # Set our attributes first (needed by get_parameters)
        self._node_class = node_class
        self._initial_config = initial_config
        self._runtime_config = {}
        self._actual_node = None
        self._is_initialized = False

        # Initialize parent with basic config for Node functionality
        name = initial_config.get("name", f"deferred_{node_class.__name__}")
        node_config = initial_config.copy()
        node_config.pop("name", None)  # Remove name to avoid conflict
        super().__init__(name=name, **node_config)

    def set_runtime_config(self, **config):
        """Set runtime configuration parameters."""
        self._runtime_config.update(config)
        logger.debug(
            f"Set runtime config for {self._node_class.__name__}: {list(config.keys())}"
        )

    def get_effective_config(self):
        """Get effective configuration combining initial and runtime config."""
        effective = self._initial_config.copy()
        effective.update(self._runtime_config)
        return effective

    def _initialize_if_needed(self):
        """Initialize the actual node if not already done."""
        if not self._is_initialized and self._has_required_config():
            effective_config = self.get_effective_config()
            try:
                self._actual_node = self._node_class(**effective_config)
                self._is_initialized = True
                logger.info(
                    f"Initialized {self._node_class.__name__} with runtime config"
                )
            except Exception as e:
                logger.warning(f"Failed to initialize {self._node_class.__name__}: {e}")

    def _has_required_config(self):
        """Check if we have enough configuration to initialize the node."""
        effective_config = self.get_effective_config()
        node_name = self._node_class.__name__

        # Get required parameters from the node class if available
        try:
            if hasattr(self._node_class, "get_parameter_definitions"):
                required_params = []
                param_defs = self._node_class.get_parameter_definitions()
                for param_name, param_def in param_defs.items():
                    if hasattr(param_def, "required") and param_def.required:
                        required_params.append(param_name)
                    elif hasattr(param_def, "default") and param_def.default is None:
                        required_params.append(param_name)

                # Check if all required parameters are present
                missing_params = [
                    p for p in required_params if p not in effective_config
                ]
                if missing_params:
                    logger.warning(
                        f"Missing required parameters for {node_name}: {missing_params}"
                    )
                    return False

        except Exception as e:
            logger.debug(f"Could not get parameter definitions for {node_name}: {e}")

        # Node-specific validation rules
        if "OAuth2" in node_name:
            required_oauth = ["token_url", "client_id"]
            missing_oauth = [p for p in required_oauth if p not in effective_config]
            if missing_oauth:
                logger.warning(
                    f"Missing OAuth2 parameters for {node_name}: {missing_oauth}"
                )
                return False

        elif "SQL" in node_name:
            # Need either connection_string or individual db parameters or minimal database config
            has_connection_string = "connection_string" in effective_config
            has_individual_params = all(
                key in effective_config for key in ["host", "database", "user"]
            )
            has_minimal_config = "database" in effective_config  # For testing scenarios
            has_query = "query" in effective_config

            if not (
                has_connection_string or has_individual_params or has_minimal_config
            ):
                logger.warning(
                    f"Missing database connection parameters for {node_name}"
                )
                return False
            if not has_query:
                logger.warning(f"Missing query parameter for {node_name}")
                return False

        elif "HTTP" in node_name or "Request" in node_name:
            if "url" not in effective_config:
                logger.warning(f"Missing url parameter for {node_name}")
                return False

        elif "LLM" in node_name or "Agent" in node_name:
            if "model" not in effective_config and "provider" not in effective_config:
                logger.warning(f"Missing model/provider parameters for {node_name}")
                return False

        elif "Cache" in node_name or "Redis" in node_name:
            redis_params = ["redis_host", "redis_port", "host", "port"]
            has_redis_config = any(param in effective_config for param in redis_params)
            if not has_redis_config:
                logger.warning(f"Missing Redis connection parameters for {node_name}")
                return False

        # Validation passed
        logger.debug(f"Configuration validation passed for {node_name}")
        return True

    def get_parameters(self):
        """Get parameter definitions for this node."""
        if self._actual_node:
            return self._actual_node.get_parameters()
        else:
            # Return default parameters based on node type
            return self._get_default_parameters()

    def _get_default_parameters(self):
        """Get default parameter definitions before actual node creation."""
        from kailash.nodes.base import NodeParameter

        if "OAuth2" in self._node_class.__name__:
            return {
                "token_url": NodeParameter(
                    name="token_url",
                    type=str,
                    required=True,
                    description="OAuth token endpoint URL",
                ),
                "client_id": NodeParameter(
                    name="client_id",
                    type=str,
                    required=True,
                    description="OAuth client ID",
                ),
                "client_secret": NodeParameter(
                    name="client_secret",
                    type=str,
                    required=False,
                    description="OAuth client secret",
                ),
                "grant_type": NodeParameter(
                    name="grant_type",
                    type=str,
                    required=False,
                    default="client_credentials",
                    description="OAuth grant type",
                ),
            }

        elif "SQL" in self._node_class.__name__:
            return {
                "database_type": NodeParameter(
                    name="database_type",
                    type=str,
                    required=False,
                    default="postgresql",
                    description="Database type",
                ),
                "host": NodeParameter(
                    name="host", type=str, required=False, description="Database host"
                ),
                "database": NodeParameter(
                    name="database",
                    type=str,
                    required=False,
                    description="Database name",
                ),
                "user": NodeParameter(
                    name="user", type=str, required=False, description="Database user"
                ),
                "password": NodeParameter(
                    name="password",
                    type=str,
                    required=False,
                    description="Database password",
                ),
                "query": NodeParameter(
                    name="query",
                    type=str,
                    required=True,
                    description="SQL query to execute",
                ),
            }

        return {}

    def validate_inputs(self, **kwargs):
        """Validate inputs and extract runtime configuration."""
        # Extract potential configuration parameters
        config_params = self._extract_config_params(kwargs)
        if config_params:
            self.set_runtime_config(**config_params)

        # Try to initialize with current config
        self._initialize_if_needed()

        # If we have an actual node, delegate to it
        if self._actual_node and hasattr(self._actual_node, "validate_inputs"):
            return self._actual_node.validate_inputs(**kwargs)

        # Otherwise, just return the kwargs
        return kwargs

    def _extract_config_params(self, inputs):
        """Extract configuration parameters from runtime inputs."""
        config_keys = {
            # OAuth2 parameters
            "token_url",
            "client_id",
            "client_secret",
            "grant_type",
            "scope",
            "username",
            "password",
            "refresh_token",
            # SQL parameters
            "database_type",
            "connection_string",
            "host",
            "port",
            "database",
            "user",
            "password",
            "pool_size",
            "max_pool_size",
            "timeout",
        }

        return {k: v for k, v in inputs.items() if k in config_keys}

    def run(self, **kwargs):
        """Execute the node with runtime configuration."""
        # Extract and set any new configuration
        config_params = self._extract_config_params(kwargs)
        if config_params:
            self.set_runtime_config(**config_params)

        # Ensure we're initialized
        self._initialize_if_needed()

        if not self._actual_node:
            raise RuntimeError(
                f"Cannot execute {self._node_class.__name__} - missing required configuration. "
                f"Provided config: {list(self.get_effective_config().keys())}"
            )

        # Delegate to the actual node - prefer execute() for compatibility
        return self._actual_node.execute(**kwargs)

    async def async_run(self, **kwargs):
        """Execute the node asynchronously with runtime configuration."""
        # Extract and set any new configuration
        config_params = self._extract_config_params(kwargs)
        if config_params:
            self.set_runtime_config(**config_params)

        # Ensure we're initialized
        self._initialize_if_needed()

        if not self._actual_node:
            raise RuntimeError(
                f"Cannot execute {self._node_class.__name__} - missing required configuration. "
                f"Provided config: {list(self.get_effective_config().keys())}"
            )

        # Delegate to the actual node
        if hasattr(self._actual_node, "async_run"):
            return await self._actual_node.async_run(**kwargs)
        else:
            return self._actual_node.execute(**kwargs)


def create_deferred_oauth2(**kwargs):
    """Create a deferred OAuth2 node that accepts runtime configuration.

    Args:
        **kwargs: Initial configuration parameters

    Returns:
        DeferredConfigNode wrapping OAuth2Node
    """
    from kailash.nodes.api.auth import OAuth2Node

    return DeferredConfigNode(OAuth2Node, **kwargs)


def create_deferred_sql(**kwargs):
    """Create a deferred SQL node that accepts runtime configuration.

    Args:
        **kwargs: Initial configuration parameters

    Returns:
        DeferredConfigNode wrapping AsyncSQLDatabaseNode
    """
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    return DeferredConfigNode(AsyncSQLDatabaseNode, **kwargs)


def create_deferred_node(node_class, **kwargs):
    """Create a deferred node for any enterprise node class.

    Args:
        node_class: The node class to wrap
        **kwargs: Initial configuration parameters

    Returns:
        DeferredConfigNode wrapping the specified node class
    """
    return DeferredConfigNode(node_class, **kwargs)


class WorkflowParameterInjector:
    """Workflow-level parameter injection for enterprise nodes."""

    def __init__(self, workflow, debug=False):
        """Initialize the workflow parameter injector.

        Args:
            workflow: The workflow to inject parameters into
            debug: Enable debug logging
        """
        self.workflow = workflow
        self.debug = debug
        self.logger = logging.getLogger(__name__)

    def inject_parameters(self, workflow_params: Dict[str, Any]) -> None:
        """Inject workflow-level parameters into deferred configuration nodes.

        Args:
            workflow_params: Dictionary of workflow-level parameters
        """
        if self.debug:
            self.logger.debug(
                f"Injecting workflow parameters: {list(workflow_params.keys())}"
            )

        # For now, this is a placeholder implementation
        # In a full implementation, this would traverse the workflow
        # and inject parameters into any DeferredConfigNode instances
        pass

    def transform_workflow_parameters(
        self, parameters: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """Transform workflow parameters for injection.

        Args:
            parameters: Dictionary of workflow parameters

        Returns:
            Transformed parameters dictionary in node-specific format
        """
        if not parameters:
            return {}

        transformed = {}

        # Handle explicit workflow input mappings first
        if hasattr(self.workflow, "metadata") and self.workflow.metadata:
            workflow_inputs = self.workflow.metadata.get("_workflow_inputs", {})
            for node_id, input_mappings in workflow_inputs.items():
                node_params = {}
                for workflow_param, node_param in input_mappings.items():
                    # Handle dot notation for nested parameter access
                    value = self._get_nested_parameter(parameters, workflow_param)
                    if value is not None:
                        node_params[node_param] = value
                        if self.debug:
                            self.logger.debug(
                                f"Mapping workflow input {workflow_param} -> {node_param} for node {node_id} (value: {value})"
                            )

                if node_params:
                    transformed[node_id] = node_params

        # ENTERPRISE ENHANCEMENT: Get ALL nodes for parameter injection, not just entry nodes
        # Real enterprise workflows need parameters available throughout the execution graph
        all_nodes = self._get_all_nodes()

        if self.debug:
            self.logger.debug(
                f"Found nodes for parameter injection: {list(all_nodes.keys())}, "
                f"injecting parameters: {list(parameters.keys())}"
            )

        # Distribute workflow parameters to ALL nodes that can accept them
        for node_id, node_instance in all_nodes.items():
            # Skip nodes that already have explicit mappings
            if node_id in transformed:
                continue

            node_params = {}
            node_param_defs = node_instance.get_parameters()

            for param_name, value in parameters.items():
                # Check if this parameter is needed by this node and get the mapped parameter name
                mapped_param_name = self._get_mapped_parameter_name(
                    param_name, value, node_param_defs, node_instance
                )
                if mapped_param_name:
                    node_params[mapped_param_name] = value
                    if self.debug:
                        self.logger.debug(
                            f"Injecting {param_name} -> {mapped_param_name} into node {node_id}"
                        )

            if node_params:
                transformed[node_id] = node_params

        return transformed

    def _get_nested_parameter(self, parameters: Dict[str, Any], path: str) -> Any:
        """Get a nested parameter value using dot notation.

        Args:
            parameters: Parameters dictionary
            path: Dot-separated path (e.g., "data.user_id")

        Returns:
            Value at the specified path or None if not found
        """
        if "." not in path:
            # Simple parameter lookup
            return parameters.get(path)

        # Handle nested parameter access
        parts = path.split(".")
        current = parameters

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        return current

    def validate_parameters(self, parameters: Dict[str, Any]) -> list[str]:
        """Validate workflow parameters.

        Args:
            parameters: Dictionary of workflow parameters

        Returns:
            List of warning messages if validation issues found
        """
        warnings = []

        if not parameters:
            return warnings

        # ENTERPRISE ENHANCEMENT: Check ALL nodes for parameter usage, not just entry nodes
        all_nodes = self._get_all_nodes()

        # Check if any workflow parameters don't match any node parameters
        used_params = set()
        for node_id, node_instance in all_nodes.items():
            node_param_defs = node_instance.get_parameters()
            for param_name in parameters.keys():
                if self._get_mapped_parameter_name(
                    param_name, parameters[param_name], node_param_defs, node_instance
                ):
                    used_params.add(param_name)

        unused_params = set(parameters.keys()) - used_params
        if unused_params:
            warnings.append(f"Unused workflow parameters: {list(unused_params)}")

        return warnings

    def _get_entry_nodes(self) -> Dict[str, Any]:
        """Get entry nodes (nodes with no incoming connections).

        Returns:
            Dictionary of entry node IDs to node instances
        """
        entry_nodes = {}

        for node_id in self.workflow.nodes.keys():
            # Check if this node has any incoming connections
            has_incoming = False
            for connection in self.workflow.connections:
                if connection.target_node == node_id:
                    has_incoming = True
                    break

            if not has_incoming:
                # Get the actual node instance, not the metadata
                entry_nodes[node_id] = self.workflow._node_instances[node_id]

        return entry_nodes

    def _get_all_nodes(self) -> Dict[str, Any]:
        """Get all nodes in the workflow for enterprise parameter injection.

        ENTERPRISE CAPABILITY: Unlike _get_entry_nodes(), this method returns ALL nodes
        in the workflow that can potentially accept enterprise parameters. This enables
        true enterprise-grade parameter flow throughout complex workflows.

        Returns:
            Dictionary of all node IDs to node instances
        """
        all_nodes = {}

        for node_id in self.workflow.nodes.keys():
            # Get the actual node instance, not the metadata
            if (
                hasattr(self.workflow, "_node_instances")
                and node_id in self.workflow._node_instances
            ):
                all_nodes[node_id] = self.workflow._node_instances[node_id]

        return all_nodes

    def _should_inject_parameter(
        self, param_name: str, param_value: Any, node_param_defs: Dict[str, Any]
    ) -> bool:
        """Check if a parameter should be injected into a node.

        Args:
            param_name: Name of the parameter
            param_value: Value of the parameter
            node_param_defs: Node parameter definitions

        Returns:
            True if parameter should be injected
        """
        # Direct parameter name match
        if param_name in node_param_defs:
            return True

        # Check for workflow alias matches
        for param_def in node_param_defs.values():
            if (
                hasattr(param_def, "workflow_alias")
                and param_def.workflow_alias == param_name
            ):
                return True

            # Check for auto_map_from matches
            if hasattr(param_def, "auto_map_from") and param_def.auto_map_from:
                if param_name in param_def.auto_map_from:
                    return True

            # Check for auto_map_primary matches
            if hasattr(param_def, "auto_map_primary") and param_def.auto_map_primary:
                # Primary parameters get first available workflow parameter
                # This is a simplified implementation - could be more sophisticated
                return True

        return False

    def _get_mapped_parameter_name(
        self,
        param_name: str,
        param_value: Any,
        node_param_defs: Dict[str, Any],
        node_instance=None,
    ) -> str | None:
        """Get the mapped parameter name for injection.

        ENTERPRISE ENHANCEMENT: Enhanced to detect and inject parameters into
        PythonCodeNode functions that accept **kwargs for enterprise parameter injection.

        Args:
            param_name: Name of the workflow parameter
            param_value: Value of the parameter
            node_param_defs: Node parameter definitions
            node_instance: The node instance for advanced mapping

        Returns:
            The node parameter name to inject to, or the original param_name
            if the node accepts **kwargs parameters
        """
        # Validate inputs
        if not isinstance(param_name, str):
            logger.warning(f"Parameter name must be string, got {type(param_name)}")
            return None

        if not isinstance(node_param_defs, dict):
            logger.warning(
                f"Node parameter definitions must be dict, got {type(node_param_defs)}"
            )
            return None

        # Direct parameter name match (highest priority)
        if param_name in node_param_defs:
            return param_name

        # Check for workflow alias matches
        for node_param_name, param_def in node_param_defs.items():
            try:
                if (
                    hasattr(param_def, "workflow_alias")
                    and param_def.workflow_alias == param_name
                ):
                    return node_param_name

                # Check for auto_map_from matches
                if hasattr(param_def, "auto_map_from") and param_def.auto_map_from:
                    if isinstance(param_def.auto_map_from, list):
                        if param_name in param_def.auto_map_from:
                            return node_param_name
                    elif isinstance(param_def.auto_map_from, str):
                        if param_name == param_def.auto_map_from:
                            return node_param_name

                # Check for auto_map_primary matches
                if (
                    hasattr(param_def, "auto_map_primary")
                    and param_def.auto_map_primary
                ):
                    # Enhanced primary parameter matching with type checking
                    if self._is_compatible_type(param_value, param_def):
                        return node_param_name

            except Exception as e:
                logger.warning(
                    f"Error processing parameter definition for {node_param_name}: {e}"
                )
                continue

        # Enhanced fuzzy matching for common parameter patterns
        fuzzy_matches = self._get_fuzzy_parameter_matches(param_name, node_param_defs)
        if fuzzy_matches:
            # Return the best match (first in list)
            return fuzzy_matches[0]

        # ENTERPRISE FEATURE: Check if this specific node accepts **kwargs
        # This enables enterprise parameter injection into arbitrary functions
        if node_instance and self._node_accepts_kwargs(node_instance):
            # PythonCodeNode with **kwargs can accept any workflow parameter
            logger.debug(
                f"Injecting workflow parameter '{param_name}' into **kwargs function"
            )
            return param_name

        return None

    def _is_compatible_type(self, param_value: Any, param_def: Any) -> bool:
        """Check if parameter value is compatible with parameter definition type."""
        try:
            if not hasattr(param_def, "type"):
                return True  # No type constraint

            expected_type = param_def.type
            if expected_type is None:
                return True

            # Handle union types and generics
            if hasattr(expected_type, "__origin__"):
                # Handle Union, Optional, etc.
                if expected_type.__origin__ is Union:
                    return any(
                        isinstance(param_value, t) for t in expected_type.__args__
                    )

            # Direct type check
            return isinstance(param_value, expected_type)
        except Exception:
            return True  # If type checking fails, assume compatible

    def _get_fuzzy_parameter_matches(
        self, param_name: str, node_param_defs: Dict[str, Any]
    ) -> List[str]:
        """Get fuzzy matches for parameter names."""
        matches = []

        # Common parameter aliases
        aliases = {
            "input": ["data", "content", "text", "input_data"],
            "data": ["input", "content", "text", "input_data"],
            "content": ["data", "input", "text", "body"],
            "text": ["data", "input", "content", "body"],
            "url": ["endpoint", "address", "link", "uri"],
            "endpoint": ["url", "address", "link", "uri"],
            "config": ["configuration", "settings", "options"],
            "params": ["parameters", "args", "arguments"],
            "result": ["output", "response", "return"],
            "output": ["result", "response", "return"],
        }

        # Check if param_name has known aliases
        if param_name in aliases:
            for alias in aliases[param_name]:
                if alias in node_param_defs:
                    matches.append(alias)

        # Check reverse mapping
        for node_param_name in node_param_defs:
            if node_param_name in aliases and param_name in aliases[node_param_name]:
                matches.append(node_param_name)

        # Substring matching for partial matches
        for node_param_name in node_param_defs:
            if (
                param_name.lower() in node_param_name.lower()
                or node_param_name.lower() in param_name.lower()
            ):
                if node_param_name not in matches:
                    matches.append(node_param_name)

        return matches

    def _node_accepts_kwargs(self, node_instance) -> bool:
        """Check if a node can accept arbitrary keyword arguments.

        ENTERPRISE CAPABILITY: Detects PythonCodeNode instances that have
        functions with **kwargs parameters, enabling enterprise parameter injection.

        Args:
            node_instance: The node instance to check

        Returns:
            True if the node can accept arbitrary parameters via **kwargs
        """
        # Check if this is a PythonCodeNode with a function that accepts **kwargs
        if (
            hasattr(node_instance, "__class__")
            and "PythonCode" in node_instance.__class__.__name__
        ):
            # For PythonCodeNode created from functions
            if hasattr(node_instance, "wrapper") and node_instance.wrapper:
                if hasattr(node_instance.wrapper, "accepts_var_keyword"):
                    return node_instance.wrapper.accepts_var_keyword()

            # For PythonCodeNode with inline code - always accepts parameters
            if hasattr(node_instance, "code") and node_instance.code:
                return True

            # For function-based nodes, check the function signature
            if hasattr(node_instance, "function") and node_instance.function:
                import inspect

                try:
                    sig = inspect.signature(node_instance.function)
                    return any(
                        param.kind == inspect.Parameter.VAR_KEYWORD
                        for param in sig.parameters.values()
                    )
                except (ValueError, TypeError):
                    pass

        return False

    def configure_deferred_node(self, node_id: str, **config) -> None:
        """Configure a deferred node with runtime parameters.

        Args:
            node_id: ID of the deferred node to configure
            **config: Configuration parameters to apply
        """
        if (
            not hasattr(self.workflow, "_node_instances")
            or node_id not in self.workflow._node_instances
        ):
            raise ValueError(f"Node '{node_id}' not found in workflow")

        node_instance = self.workflow._node_instances[node_id]

        # Check if this is a deferred configuration node
        if hasattr(node_instance, "set_runtime_config"):
            node_instance.set_runtime_config(**config)
            # Force initialization now that we have runtime config
            if hasattr(node_instance, "_initialize_if_needed"):
                node_instance._initialize_if_needed()
            if self.debug:
                self.logger.debug(
                    f"Configured deferred node '{node_id}' with parameters: {list(config.keys())}"
                )
        else:
            raise ValueError(f"Node '{node_id}' is not a deferred configuration node")
