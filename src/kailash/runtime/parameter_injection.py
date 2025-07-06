"""Parameter injection framework for enterprise nodes.

This module provides a framework for handling runtime parameter injection
in enterprise nodes that traditionally require initialization-time configuration.
It bridges the gap between static configuration and dynamic workflow parameters.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)


class ParameterInjectionMixin:
    """Mixin to add parameter injection capabilities to nodes.

    This mixin allows nodes to defer configuration until runtime,
    enabling workflow-level parameter injection for connection parameters.
    """

    def __init__(self, *args, **kwargs):
        """Initialize with deferred configuration support."""
        # Store original kwargs for deferred initialization
        self._deferred_config = kwargs.copy()
        self._is_initialized = False
        self._runtime_config = {}
        super().__init__(*args, **kwargs)

    def set_runtime_parameters(self, **runtime_params: Any) -> None:
        """Set runtime parameters for deferred initialization.

        Args:
            **runtime_params: Runtime parameters to use for configuration
        """
        self._runtime_config.update(runtime_params)
        logger.debug(
            f"Set runtime parameters for {self.__class__.__name__}: {list(runtime_params.keys())}"
        )

    def get_effective_config(self) -> Dict[str, Any]:
        """Get effective configuration combining init-time and runtime parameters.

        Returns:
            Combined configuration with runtime parameters taking precedence
        """
        effective_config = self._deferred_config.copy()
        effective_config.update(self._runtime_config)
        return effective_config

    def initialize_with_runtime_config(self) -> None:
        """Initialize the node with runtime configuration.

        Should be called by subclasses when they need to set up connections
        or other resources that depend on runtime parameters.
        """
        if not self._is_initialized:
            self._perform_initialization(self.get_effective_config())
            self._is_initialized = True

    @abstractmethod
    def _perform_initialization(self, config: Dict[str, Any]) -> None:
        """Perform actual initialization with effective configuration.

        Args:
            config: Combined configuration to use for initialization
        """
        pass

    def validate_inputs(self, **kwargs) -> Dict[str, Any]:
        """Override to inject runtime parameters before validation."""
        # Extract connection parameters from runtime inputs
        connection_params = self._extract_connection_params(kwargs)
        if connection_params:
            self.set_runtime_parameters(**connection_params)

        # Initialize if we have new runtime parameters
        if connection_params and not self._is_initialized:
            self.initialize_with_runtime_config()

        return super().validate_inputs(**kwargs)

    def _extract_connection_params(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Extract connection-related parameters from runtime inputs.

        Args:
            inputs: Runtime input parameters

        Returns:
            Dictionary of connection parameters
        """
        # Define connection parameter patterns
        connection_param_patterns = [
            "host",
            "port",
            "database",
            "user",
            "password",
            "connection_string",
            "token_url",
            "client_id",
            "client_secret",
            "auth_url",
            "api_key",
            "database_type",
            "grant_type",
            "scope",
            "username",
        ]

        connection_params = {}
        for key, value in inputs.items():
            if key in connection_param_patterns:
                connection_params[key] = value

        return connection_params


class ConfigurableOAuth2Node:
    """OAuth2Node with runtime parameter injection support.

    This class extends OAuth2Node to support runtime configuration of
    connection parameters through workflow parameter injection.
    """

    def __init__(self, **kwargs):
        """Initialize with deferred OAuth configuration."""
        from kailash.nodes.base import Node, NodeMetadata

        # Store configuration
        self._deferred_config = kwargs.copy()
        self._runtime_config = {}
        self._is_initialized = False
        self._oauth_node = None

        # Initialize metadata
        if "metadata" not in kwargs:
            kwargs["metadata"] = NodeMetadata(
                id=kwargs.get("name", "configurable_oauth2").replace(" ", "_").lower(),
                name=kwargs.get("name", "ConfigurableOAuth2Node"),
                description="OAuth2 node with runtime parameter injection",
                tags={"auth", "oauth2", "configurable"},
                version="1.0.0",
            )

        # Store metadata for later use
        self.metadata = kwargs["metadata"]

    def _perform_initialization(self, config: Dict[str, Any]) -> None:
        """Initialize OAuth2Node with runtime configuration."""
        from kailash.nodes.api.auth import OAuth2Node

        # Filter out non-OAuth parameters
        oauth_config = {}
        oauth_params = [
            "token_url",
            "client_id",
            "client_secret",
            "grant_type",
            "scope",
            "username",
            "password",
            "refresh_token",
        ]

        for param in oauth_params:
            if param in config:
                oauth_config[param] = config[param]

        # Create the actual OAuth2Node
        self._oauth_node = OAuth2Node(**oauth_config)
        logger.info(
            f"Initialized OAuth2Node with runtime config: {list(oauth_config.keys())}"
        )

    def get_parameters(self):
        """Get parameters from the underlying OAuth2Node or default set."""
        if self._oauth_node:
            return self._oauth_node.get_parameters()
        else:
            # Return default OAuth2 parameters for workflow building
            from kailash.nodes.base import NodeParameter

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

    def run(self, **kwargs):
        """Execute OAuth2 authentication with runtime configuration."""
        # Ensure initialization with current parameters
        if not self._is_initialized:
            self.set_runtime_parameters(**kwargs)
            self.initialize_with_runtime_config()

        if not self._oauth_node:
            raise RuntimeError(
                "OAuth2Node not initialized - missing connection parameters"
            )

        # Delegate to the initialized OAuth2Node
        return self._oauth_node.execute(**kwargs)


class ConfigurableAsyncSQLNode(ParameterInjectionMixin):
    """AsyncSQLDatabaseNode with runtime parameter injection support.

    This class extends AsyncSQLDatabaseNode to support runtime configuration
    of database connection parameters through workflow parameter injection.
    """

    def __init__(self, **kwargs):
        """Initialize with deferred database configuration."""
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        # Don't initialize AsyncSQLDatabaseNode yet - defer until runtime
        self._sql_node = None
        super().__init__(**kwargs)

    def _perform_initialization(self, config: Dict[str, Any]) -> None:
        """Initialize AsyncSQLDatabaseNode with runtime configuration."""
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        # Filter out non-SQL parameters
        sql_config = {}
        sql_params = [
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
        ]

        for param in sql_params:
            if param in config:
                sql_config[param] = config[param]

        # Add any query parameters
        if "query" in config:
            sql_config["query"] = config["query"]
        if "params" in config:
            sql_config["params"] = config["params"]
        if "fetch_mode" in config:
            sql_config["fetch_mode"] = config["fetch_mode"]

        # Create the actual AsyncSQLDatabaseNode
        self._sql_node = AsyncSQLDatabaseNode(**sql_config)
        logger.info(
            f"Initialized AsyncSQLDatabaseNode with runtime config: {list(sql_config.keys())}"
        )

    def get_parameters(self):
        """Get parameters from the underlying AsyncSQLDatabaseNode or default set."""
        if self._sql_node:
            return self._sql_node.get_parameters()
        else:
            # Return default SQL parameters for workflow building
            from kailash.nodes.base import NodeParameter

            return {
                "database_type": NodeParameter(
                    name="database_type",
                    type=str,
                    required=True,
                    default="postgresql",
                    description="Type of database",
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

    async def async_run(self, **kwargs):
        """Execute SQL query with runtime configuration."""
        # Ensure initialization with current parameters
        if not self._is_initialized:
            self.set_runtime_parameters(**kwargs)
            self.initialize_with_runtime_config()

        if not self._sql_node:
            raise RuntimeError(
                "AsyncSQLDatabaseNode not initialized - missing connection parameters"
            )

        # Delegate to the initialized AsyncSQLDatabaseNode
        return await self._sql_node.async_run(**kwargs)

    def run(self, **kwargs):
        """Synchronous wrapper for async_run."""
        import asyncio

        return asyncio.run(self.async_run(**kwargs))


class EnterpriseNodeFactory:
    """Factory for creating enterprise nodes with parameter injection support."""

    @staticmethod
    def create_oauth2_node(**kwargs) -> ConfigurableOAuth2Node:
        """Create an OAuth2Node with runtime parameter injection support.

        Args:
            **kwargs: Initial configuration parameters

        Returns:
            ConfigurableOAuth2Node instance
        """
        return ConfigurableOAuth2Node(**kwargs)

    @staticmethod
    def create_async_sql_node(**kwargs) -> ConfigurableAsyncSQLNode:
        """Create an AsyncSQLDatabaseNode with runtime parameter injection support.

        Args:
            **kwargs: Initial configuration parameters

        Returns:
            ConfigurableAsyncSQLNode instance
        """
        return ConfigurableAsyncSQLNode(**kwargs)

    @staticmethod
    def wrap_enterprise_node(node_class, **kwargs):
        """Wrap any enterprise node class with parameter injection support.

        Args:
            node_class: The enterprise node class to wrap
            **kwargs: Initial configuration parameters

        Returns:
            Wrapped node instance with parameter injection support
        """

        # Create a dynamic wrapper class
        class WrappedEnterpriseNode(ParameterInjectionMixin):
            def __init__(self, **init_kwargs):
                self._wrapped_node = None
                self._node_class = node_class
                super().__init__(**init_kwargs)

            def _perform_initialization(self, config):
                self._wrapped_node = self._node_class(**config)

            def get_parameters(self):
                if self._wrapped_node:
                    return self._wrapped_node.get_parameters()
                else:
                    # Try to get parameters from class if possible
                    try:
                        temp_node = self._node_class()
                        return temp_node.get_parameters()
                    except:
                        return {}

            def run(self, **run_kwargs):
                if not self._is_initialized:
                    self.set_runtime_parameters(**run_kwargs)
                    self.initialize_with_runtime_config()

                if not self._wrapped_node:
                    raise RuntimeError(f"{self._node_class.__name__} not initialized")

                return self._wrapped_node.execute(**run_kwargs)

        return WrappedEnterpriseNode(**kwargs)


# Convenience functions for workflow builders
def create_configurable_oauth2(**kwargs) -> ConfigurableOAuth2Node:
    """Convenience function to create a configurable OAuth2 node."""
    return EnterpriseNodeFactory.create_oauth2_node(**kwargs)


def create_configurable_sql(**kwargs) -> ConfigurableAsyncSQLNode:
    """Convenience function to create a configurable SQL node."""
    return EnterpriseNodeFactory.create_async_sql_node(**kwargs)
