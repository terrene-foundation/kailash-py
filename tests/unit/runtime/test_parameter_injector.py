"""Unit tests for runtime parameter injection framework.

Follows the testing policy:
- Unit tests (Tier 1): Fast, isolated, mocking allowed for external dependencies
- Tests deferred configuration pattern and parameter injection logic
"""

import inspect
import logging
from typing import Any, Dict, List, Union
from unittest.mock import MagicMock, Mock, patch

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.parameter_injector import (
    DeferredConfigNode,
    WorkflowParameterInjector,
    create_deferred_node,
    create_deferred_oauth2,
    create_deferred_sql,
)
from kailash.sdk_exceptions import NodeValidationError
from kailash.workflow.graph import Workflow


class MockOAuth2Node(Node):
    """Mock OAuth2 node for testing."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.token_url = kwargs.get("token_url")
        self.client_id = kwargs.get("client_id")
        self.client_secret = kwargs.get("client_secret")

    def get_parameters(self):
        return {
            "token_url": NodeParameter(
                name="token_url", type=str, required=True, description="OAuth token URL"
            ),
            "client_id": NodeParameter(
                name="client_id", type=str, required=True, description="Client ID"
            ),
            "client_secret": NodeParameter(
                name="client_secret",
                type=str,
                required=False,
                description="Client secret",
            ),
        }

    def run(self, **kwargs):
        return {"access_token": "mock_token", "token_type": "Bearer"}


class MockSQLNode(Node):
    """Mock SQL node for testing."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.database = kwargs.get("database")
        self.query = kwargs.get("query")
        self.host = kwargs.get("host")
        self.user = kwargs.get("user")
        self.password = kwargs.get("password")

    def get_parameters(self):
        return {
            "database": NodeParameter(
                name="database", type=str, required=False, description="Database name"
            ),
            "query": NodeParameter(
                name="query", type=str, required=True, description="SQL query"
            ),
            "host": NodeParameter(
                name="host", type=str, required=False, description="Database host"
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
        }

    def run(self, **kwargs):
        return {"rows": [{"id": 1, "name": "test"}], "count": 1}


class MockHTTPNode(Node):
    """Mock HTTP node for testing."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.url = kwargs.get("url")

    def get_parameters(self):
        return {
            "url": NodeParameter(
                name="url", type=str, required=True, description="Request URL"
            ),
        }

    def run(self, **kwargs):
        return {"status_code": 200, "body": "OK"}


class MockPythonCodeNode(Node):
    """Mock PythonCodeNode that accepts **kwargs."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.function = kwargs.get("function")
        self.code = kwargs.get("code")

    def get_parameters(self):
        return {
            "input_data": NodeParameter(
                name="input_data", type=Any, required=False, description="Input data"
            ),
        }

    def run(self, **kwargs):
        if self.function and hasattr(self.function, "__call__"):
            sig = inspect.signature(self.function)
            # Check if function accepts **kwargs
            has_var_keyword = any(
                param.kind == inspect.Parameter.VAR_KEYWORD
                for param in sig.parameters.values()
            )
            if has_var_keyword:
                return self.function(**kwargs)
            else:
                # Filter kwargs to match function parameters
                func_params = list(sig.parameters.keys())
                filtered_kwargs = {k: v for k, v in kwargs.items() if k in func_params}
                return self.function(**filtered_kwargs)
        return {"result": "processed", "kwargs_received": list(kwargs.keys())}


class TestDeferredConfigNode:
    """Test DeferredConfigNode functionality."""

    def test_deferred_node_initialization(self):
        """Test DeferredConfigNode initialization with basic config."""
        initial_config = {
            "token_url": "https://oauth.example.com",
            "name": "test_oauth",
        }

        deferred_node = DeferredConfigNode(MockOAuth2Node, **initial_config)

        assert deferred_node._node_class == MockOAuth2Node
        # initial_config preserves all original parameters including name
        assert deferred_node._initial_config == initial_config
        assert deferred_node._runtime_config == {}
        assert deferred_node._actual_node is None
        assert deferred_node._is_initialized is False
        assert deferred_node.metadata.name == "test_oauth"

    def test_cache_node_validation_redis_host(self):
        """Test Redis/Cache node validation with redis_host parameter."""
        deferred_node = DeferredConfigNode(
            MockCacheNode, redis_host="localhost", redis_port=6379
        )

        assert deferred_node._has_required_config() is True

    def test_cache_node_validation_host_port(self):
        """Test Redis/Cache node validation with host/port parameters."""
        deferred_node = DeferredConfigNode(MockCacheNode, host="localhost", port=6379)

        assert deferred_node._has_required_config() is True

    def test_cache_node_validation_missing(self):
        """Test Redis/Cache node validation with missing parameters."""
        deferred_node = DeferredConfigNode(MockCacheNode)

        assert deferred_node._has_required_config() is False

    def test_llm_node_validation_model(self):
        """Test LLM/Agent node validation with model parameter."""
        deferred_node = DeferredConfigNode(MockLLMNode, model="gpt-4")

        assert deferred_node._has_required_config() is True

    def test_llm_node_validation_provider(self):
        """Test LLM/Agent node validation with provider parameter."""
        deferred_node = DeferredConfigNode(MockLLMNode, provider="openai")

        assert deferred_node._has_required_config() is True

    def test_llm_node_validation_missing(self):
        """Test LLM/Agent node validation with missing parameters."""
        deferred_node = DeferredConfigNode(MockLLMNode)

        assert deferred_node._has_required_config() is False

    def test_node_with_get_parameter_definitions(self):
        """Test validation for nodes that use get_parameter_definitions method."""

        class NodeWithParamDefs(Node):
            @classmethod
            def get_parameter_definitions(cls):
                return {
                    "required_param": Mock(required=True),
                    "optional_param": Mock(required=False),
                    "default_none_param": Mock(default=None, required=False),
                }

            def run(self, **kwargs):
                return {"ok": True}

        deferred_node = DeferredConfigNode(NodeWithParamDefs, optional_param="value")

        # Missing required_param and default_none_param
        assert deferred_node._has_required_config() is False

        # Add required parameters
        deferred_node.set_runtime_config(
            required_param="value", default_none_param="value"
        )
        assert deferred_node._has_required_config() is True

    def test_node_validation_exception_handling(self):
        """Test handling of exceptions during parameter definition access."""

        class BrokenParamDefNode(Node):
            @classmethod
            def get_parameter_definitions(cls):
                raise RuntimeError("Cannot get parameters")

            def run(self, **kwargs):
                return {"ok": True}

        # Should handle exception gracefully and continue validation
        deferred_node = DeferredConfigNode(BrokenParamDefNode)
        # Since it can't get param defs and it's not a known node type, should pass
        assert deferred_node._has_required_config() is True

    def test_get_default_parameters_unknown_node(self):
        """Test default parameters for unknown node types."""

        class UnknownNode(Node):
            def run(self, **kwargs):
                return {"ok": True}

        deferred_node = DeferredConfigNode(UnknownNode)
        params = deferred_node._get_default_parameters()

        assert params == {}

    def test_concurrent_runtime_config_updates(self):
        """Test concurrent updates to runtime configuration."""
        deferred_node = DeferredConfigNode(
            MockOAuth2Node, token_url="https://initial.com"
        )

        # Simulate concurrent config updates
        deferred_node.set_runtime_config(client_id="abc123")
        deferred_node.set_runtime_config(client_secret="secret1")
        deferred_node.set_runtime_config(client_id="xyz789")  # Override

        effective = deferred_node.get_effective_config()

        assert effective["token_url"] == "https://initial.com"
        assert effective["client_id"] == "xyz789"  # Last update wins
        assert effective["client_secret"] == "secret1"

    def test_deferred_node_default_name(self):
        """Test DeferredConfigNode with default name generation."""
        deferred_node = DeferredConfigNode(MockOAuth2Node)

        assert deferred_node.metadata.name == "deferred_MockOAuth2Node"

    def test_set_runtime_config(self):
        """Test setting runtime configuration."""
        deferred_node = DeferredConfigNode(
            MockOAuth2Node, token_url="https://oauth.example.com"
        )

        deferred_node.set_runtime_config(
            client_id="test_client", client_secret="test_secret"
        )

        assert deferred_node._runtime_config == {
            "client_id": "test_client",
            "client_secret": "test_secret",
        }

    def test_get_effective_config(self):
        """Test getting effective configuration combining initial and runtime."""
        initial_config = {
            "token_url": "https://oauth.example.com",
            "grant_type": "client_credentials",
        }
        deferred_node = DeferredConfigNode(MockOAuth2Node, **initial_config)

        deferred_node.set_runtime_config(
            client_id="test_client", token_url="https://oauth2.example.com"
        )

        effective = deferred_node.get_effective_config()

        # Runtime config should override initial config
        assert effective == {
            "token_url": "https://oauth2.example.com",  # Overridden
            "grant_type": "client_credentials",
            "client_id": "test_client",
        }

    def test_has_required_config_oauth2_success(self):
        """Test OAuth2 node configuration validation - success case."""
        deferred_node = DeferredConfigNode(
            MockOAuth2Node, token_url="https://oauth.example.com"
        )
        deferred_node.set_runtime_config(client_id="test_client")

        assert deferred_node._has_required_config() is True

    def test_has_required_config_oauth2_missing(self):
        """Test OAuth2 node configuration validation - missing parameters."""
        deferred_node = DeferredConfigNode(
            MockOAuth2Node, token_url="https://oauth.example.com"
        )
        # Missing client_id

        assert deferred_node._has_required_config() is False

    def test_has_required_config_sql_connection_string(self):
        """Test SQL node validation with connection string."""
        deferred_node = DeferredConfigNode(
            MockSQLNode, connection_string="sqlite:///:memory:"
        )
        deferred_node.set_runtime_config(query="SELECT * FROM users")

        assert deferred_node._has_required_config() is True

    def test_has_required_config_sql_individual_params(self):
        """Test SQL node validation with individual parameters."""
        deferred_node = DeferredConfigNode(
            MockSQLNode, host="localhost", database="test", user="user"
        )
        deferred_node.set_runtime_config(query="SELECT * FROM users")

        assert deferred_node._has_required_config() is True

    def test_has_required_config_sql_minimal(self):
        """Test SQL node validation with minimal configuration."""
        deferred_node = DeferredConfigNode(MockSQLNode, database="test")
        deferred_node.set_runtime_config(query="SELECT * FROM users")

        assert deferred_node._has_required_config() is True

    def test_has_required_config_sql_missing_query(self):
        """Test SQL node validation missing query."""
        deferred_node = DeferredConfigNode(MockSQLNode, database="test")
        # Missing query parameter

        assert deferred_node._has_required_config() is False

    def test_has_required_config_http_success(self):
        """Test HTTP node validation - success case."""
        deferred_node = DeferredConfigNode(MockHTTPNode, url="https://api.example.com")

        assert deferred_node._has_required_config() is True

    def test_has_required_config_http_missing(self):
        """Test HTTP node validation - missing URL."""
        deferred_node = DeferredConfigNode(MockHTTPNode)

        assert deferred_node._has_required_config() is False

    def test_initialize_if_needed_success(self):
        """Test successful node initialization."""
        deferred_node = DeferredConfigNode(
            MockOAuth2Node,
            token_url="https://oauth.example.com",
            client_id="test_client",
        )

        deferred_node._initialize_if_needed()

        assert deferred_node._is_initialized is True
        assert deferred_node._actual_node is not None
        assert isinstance(deferred_node._actual_node, MockOAuth2Node)
        assert deferred_node._actual_node.token_url == "https://oauth.example.com"
        assert deferred_node._actual_node.client_id == "test_client"

    def test_initialize_if_needed_missing_config(self):
        """Test initialization when required config is missing."""
        deferred_node = DeferredConfigNode(MockOAuth2Node)  # Missing required params

        deferred_node._initialize_if_needed()

        assert deferred_node._is_initialized is False
        assert deferred_node._actual_node is None

    def test_initialize_if_needed_initialization_error(self):
        """Test handling of initialization errors."""

        # Mock node class that raises an error during initialization
        class BadNode(Node):
            def __init__(self, **kwargs):
                raise ValueError("Initialization failed")

        deferred_node = DeferredConfigNode(BadNode)

        # Should not raise error, just log warning
        deferred_node._initialize_if_needed()

        assert deferred_node._is_initialized is False
        assert deferred_node._actual_node is None

    def test_get_parameters_default_oauth2(self):
        """Test getting default parameters for OAuth2 node."""
        deferred_node = DeferredConfigNode(MockOAuth2Node)

        params = deferred_node.get_parameters()

        assert "token_url" in params
        assert "client_id" in params
        assert "client_secret" in params
        assert "grant_type" in params
        assert params["token_url"].required is True
        assert params["grant_type"].default == "client_credentials"

    def test_get_parameters_default_sql(self):
        """Test getting default parameters for SQL node."""
        deferred_node = DeferredConfigNode(MockSQLNode)

        params = deferred_node.get_parameters()

        assert "database_type" in params
        assert "host" in params
        assert "database" in params
        assert "user" in params
        assert "password" in params
        assert "query" in params
        assert params["query"].required is True

    def test_get_parameters_actual_node(self):
        """Test getting parameters from actual initialized node."""
        deferred_node = DeferredConfigNode(
            MockOAuth2Node,
            token_url="https://oauth.example.com",
            client_id="test_client",
        )
        deferred_node._initialize_if_needed()

        params = deferred_node.get_parameters()

        # Should get parameters from actual node
        assert len(params) == 3  # token_url, client_id, client_secret
        assert "token_url" in params
        assert params["token_url"].required is True

    def test_extract_config_params(self):
        """Test extracting configuration parameters from runtime inputs."""
        deferred_node = DeferredConfigNode(MockOAuth2Node)

        inputs = {
            "token_url": "https://oauth.example.com",
            "client_id": "test_client",
            "regular_param": "not_config",
            "database": "test_db",  # SQL param
            "host": "localhost",  # SQL param
        }

        config_params = deferred_node._extract_config_params(inputs)

        assert config_params == {
            "token_url": "https://oauth.example.com",
            "client_id": "test_client",
            "database": "test_db",
            "host": "localhost",
        }
        assert "regular_param" not in config_params

    def test_validate_inputs_with_config_extraction(self):
        """Test input validation with configuration parameter extraction."""
        deferred_node = DeferredConfigNode(
            MockOAuth2Node, token_url="https://oauth.example.com"
        )

        inputs = {"client_id": "test_client", "data": "test_data"}

        # This will trigger initialization and validation
        try:
            validated = deferred_node.validate_inputs(**inputs)
            # Should extract client_id as config and set runtime config
            assert deferred_node._runtime_config["client_id"] == "test_client"
            assert validated == inputs
        except NodeValidationError:
            # If validation fails because of OAuth2Node requirements, that's expected
            # The important thing is that config was extracted
            assert deferred_node._runtime_config["client_id"] == "test_client"

    def test_validate_inputs_delegates_to_actual_node(self):
        """Test that validation delegates to actual node when available."""
        mock_node = Mock(spec=MockOAuth2Node)
        mock_node.validate_inputs.return_value = {"validated": "data"}

        deferred_node = DeferredConfigNode(
            MockOAuth2Node, token_url="https://oauth.example.com"
        )
        deferred_node._actual_node = mock_node
        deferred_node._is_initialized = True

        inputs = {"test": "data"}
        result = deferred_node.validate_inputs(**inputs)

        mock_node.validate_inputs.assert_called_once_with(**inputs)
        assert result == {"validated": "data"}

    def test_run_success(self):
        """Test successful node execution."""
        deferred_node = DeferredConfigNode(
            MockOAuth2Node,
            token_url="https://oauth.example.com",
            client_id="test_client",
        )

        result = deferred_node.run()

        assert result == {"access_token": "mock_token", "token_type": "Bearer"}
        assert deferred_node._is_initialized is True

    def test_run_with_runtime_config(self):
        """Test execution with runtime configuration."""
        deferred_node = DeferredConfigNode(
            MockOAuth2Node, token_url="https://oauth.example.com"
        )

        # Provide client_id at runtime
        result = deferred_node.run(client_id="runtime_client")

        assert result == {"access_token": "mock_token", "token_type": "Bearer"}
        assert deferred_node._runtime_config["client_id"] == "runtime_client"

    def test_run_missing_config(self):
        """Test execution when required configuration is missing."""
        deferred_node = DeferredConfigNode(MockOAuth2Node)  # Missing required params

        with pytest.raises(
            RuntimeError,
            match="Cannot execute MockOAuth2Node - missing required configuration",
        ):
            deferred_node.run()

    def test_run_delegates_to_actual_node(self):
        """Test that execution delegates to actual node."""
        deferred_node = DeferredConfigNode(
            MockOAuth2Node,
            token_url="https://oauth.example.com",
            client_id="test_client",
        )
        deferred_node._initialize_if_needed()

        # Mock the actual node's execute method
        deferred_node._actual_node.execute = Mock(return_value={"custom": "result"})

        result = deferred_node.run(test_param="value")

        deferred_node._actual_node.execute.assert_called_once_with(test_param="value")
        assert result == {"custom": "result"}

    @pytest.mark.asyncio
    async def test_async_run_success(self):
        """Test successful asynchronous node execution."""
        deferred_node = DeferredConfigNode(
            MockOAuth2Node,
            token_url="https://oauth.example.com",
            client_id="test_client",
        )

        result = await deferred_node.async_run()

        assert result == {"access_token": "mock_token", "token_type": "Bearer"}

    @pytest.mark.asyncio
    async def test_async_run_missing_config(self):
        """Test async execution when required configuration is missing."""
        deferred_node = DeferredConfigNode(MockOAuth2Node)

        with pytest.raises(
            RuntimeError,
            match="Cannot execute MockOAuth2Node - missing required configuration",
        ):
            await deferred_node.async_run()

    @pytest.mark.asyncio
    async def test_async_run_delegates_to_async_method(self):
        """Test async execution delegates to actual node's async method."""
        deferred_node = DeferredConfigNode(
            MockOAuth2Node,
            token_url="https://oauth.example.com",
            client_id="test_client",
        )
        deferred_node._initialize_if_needed()

        # Mock async_run method
        async def mock_async_run(**kwargs):
            return {"async": "result"}

        deferred_node._actual_node.async_run = mock_async_run

        result = await deferred_node.async_run(test_param="value")

        assert result == {"async": "result"}

    @pytest.mark.asyncio
    async def test_async_run_fallback_to_execute(self):
        """Test async execution falls back to execute when async_run not available."""
        deferred_node = DeferredConfigNode(
            MockOAuth2Node,
            token_url="https://oauth.example.com",
            client_id="test_client",
        )
        deferred_node._initialize_if_needed()

        # Mock execute method only
        deferred_node._actual_node.execute = Mock(return_value={"sync": "result"})

        result = await deferred_node.async_run(test_param="value")

        deferred_node._actual_node.execute.assert_called_once_with(test_param="value")
        assert result == {"sync": "result"}


class MockCacheNode(Node):
    """Mock cache/Redis node for testing."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.redis_host = kwargs.get("redis_host", kwargs.get("host"))
        self.redis_port = kwargs.get("redis_port", kwargs.get("port"))

    def get_parameters(self):
        return {
            "redis_host": NodeParameter(
                name="redis_host", type=str, required=True, description="Redis host"
            ),
            "redis_port": NodeParameter(
                name="redis_port", type=int, required=True, description="Redis port"
            ),
            "key": NodeParameter(
                name="key", type=str, required=True, description="Cache key"
            ),
        }

    def run(self, **kwargs):
        return {"cached": True, "key": kwargs.get("key")}


class MockLLMNode(Node):
    """Mock LLM/Agent node for testing."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.model = kwargs.get("model")
        self.provider = kwargs.get("provider")

    def get_parameters(self):
        return {
            "model": NodeParameter(
                name="model", type=str, required=False, description="Model name"
            ),
            "provider": NodeParameter(
                name="provider", type=str, required=False, description="Provider name"
            ),
            "prompt": NodeParameter(
                name="prompt", type=str, required=True, description="Prompt text"
            ),
        }

    def run(self, **kwargs):
        return {"response": f"Generated from {self.model or self.provider}"}


class TestWorkflowParameterInjector:
    """Test WorkflowParameterInjector functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create mock workflow
        self.mock_workflow = Mock(spec=Workflow)
        self.mock_workflow.nodes = {
            "oauth_node": MockOAuth2Node(name="oauth_node"),
            "sql_node": MockSQLNode(name="sql_node"),
            "http_node": MockHTTPNode(name="http_node"),
            "cache_node": MockCacheNode(name="cache_node"),
            "llm_node": MockLLMNode(name="llm_node"),
        }
        self.mock_workflow.connections = []
        self.mock_workflow.metadata = {}
        self.mock_workflow._node_instances = self.mock_workflow.nodes

        self.injector = WorkflowParameterInjector(self.mock_workflow, debug=True)

    def test_injector_initialization(self):
        """Test WorkflowParameterInjector initialization."""
        assert self.injector.workflow == self.mock_workflow
        assert self.injector.debug is True
        assert self.injector.logger is not None

    def test_inject_parameters_placeholder(self):
        """Test parameter injection placeholder implementation."""
        workflow_params = {
            "token_url": "https://oauth.example.com",
            "database": "test_db",
        }

        # Should not raise an error (placeholder implementation)
        self.injector.inject_parameters(workflow_params)

    def test_transform_workflow_parameters_empty(self):
        """Test transforming empty workflow parameters."""
        result = self.injector.transform_workflow_parameters({})

        assert result == {}

    def test_transform_workflow_parameters_explicit_mappings(self):
        """Test transforming parameters with explicit workflow input mappings."""
        # Mock workflow with metadata
        self.mock_workflow.metadata = {
            "_workflow_inputs": {
                "oauth_node": {"api_url": "token_url", "client": "client_id"},
                "sql_node": {"db_name": "database"},
            }
        }

        workflow_params = {
            "api_url": "https://oauth.example.com",
            "client": "test_client",
            "db_name": "test_database",
        }

        result = self.injector.transform_workflow_parameters(workflow_params)

        # Should only contain explicitly mapped nodes
        assert "oauth_node" in result
        assert "sql_node" in result
        assert result["oauth_node"]["token_url"] == "https://oauth.example.com"
        assert result["oauth_node"]["client_id"] == "test_client"
        assert result["sql_node"]["database"] == "test_database"

    def test_transform_workflow_parameters_auto_distribution(self):
        """Test automatic parameter distribution to all nodes."""
        workflow_params = {
            "token_url": "https://oauth.example.com",
            "url": "https://api.example.com",
            "database": "test_db",
        }

        result = self.injector.transform_workflow_parameters(workflow_params)

        # Parameters should be distributed to compatible nodes
        assert "oauth_node" in result
        assert "http_node" in result
        assert "sql_node" in result

        # Check that each parameter went to at least one compatible node
        # Note: fuzzy matching might distribute parameters to multiple nodes
        oauth_params = result["oauth_node"]
        http_params = result["http_node"]
        sql_params = result["sql_node"]

        # OAuth node should get token_url
        assert "token_url" in oauth_params
        # HTTP node should get url
        assert "url" in http_params
        # SQL node should get database
        assert "database" in sql_params

    def test_get_nested_parameter_simple(self):
        """Test getting simple parameter without dot notation."""
        parameters = {"token_url": "https://oauth.example.com", "database": "test_db"}

        value = self.injector._get_nested_parameter(parameters, "token_url")

        assert value == "https://oauth.example.com"

    def test_get_nested_parameter_nested(self):
        """Test getting nested parameter with dot notation."""
        parameters = {"auth": {"oauth": {"token_url": "https://oauth.example.com"}}}

        value = self.injector._get_nested_parameter(parameters, "auth.oauth.token_url")

        assert value == "https://oauth.example.com"

    def test_get_nested_parameter_missing(self):
        """Test getting nested parameter that doesn't exist."""
        parameters = {"auth": {"basic": {"username": "user"}}}

        value = self.injector._get_nested_parameter(parameters, "auth.oauth.token_url")

        assert value is None

    def test_validate_parameters_no_warnings(self):
        """Test parameter validation with all parameters used."""
        # Parameters that match node parameters
        workflow_params = {
            "token_url": "https://oauth.example.com",
            "url": "https://api.example.com",
            "database": "test_db",
        }

        warnings = self.injector.validate_parameters(workflow_params)

        assert warnings == []

    def test_validate_parameters_unused_params(self):
        """Test parameter validation with unused parameters."""
        workflow_params = {
            "token_url": "https://oauth.example.com",
            "unused_param": "unused_value",
            "another_unused": "another_unused_value",
        }

        warnings = self.injector.validate_parameters(workflow_params)

        assert len(warnings) == 1
        assert "Unused workflow parameters" in warnings[0]
        assert "unused_param" in warnings[0]
        assert "another_unused" in warnings[0]

    def test_get_entry_nodes(self):
        """Test getting entry nodes (nodes with no incoming connections)."""
        # Mock connections - sql_node has incoming from oauth_node
        mock_connection = Mock()
        mock_connection.target_node = "sql_node"
        self.mock_workflow.connections = [mock_connection]

        entry_nodes = self.injector._get_entry_nodes()

        # All nodes except sql_node should be entry nodes (sql_node has incoming connection)
        assert len(entry_nodes) == 4
        assert "oauth_node" in entry_nodes
        assert "http_node" in entry_nodes
        assert "cache_node" in entry_nodes
        assert "llm_node" in entry_nodes
        assert "sql_node" not in entry_nodes

    def test_get_all_nodes(self):
        """Test getting all nodes in workflow."""
        all_nodes = self.injector._get_all_nodes()

        assert len(all_nodes) == 5
        assert "oauth_node" in all_nodes
        assert "sql_node" in all_nodes
        assert "http_node" in all_nodes
        assert "cache_node" in all_nodes
        assert "llm_node" in all_nodes
        assert isinstance(all_nodes["oauth_node"], MockOAuth2Node)

    def test_should_inject_parameter_direct_match(self):
        """Test parameter injection check for direct parameter name match."""
        node_param_defs = {
            "token_url": NodeParameter(name="token_url", type=str, required=True)
        }

        should_inject = self.injector._should_inject_parameter(
            "token_url", "https://oauth.example.com", node_param_defs
        )

        assert should_inject is True

    def test_should_inject_parameter_workflow_alias(self):
        """Test parameter injection check for workflow alias match."""
        mock_param = Mock()
        mock_param.workflow_alias = "api_url"

        node_param_defs = {"token_url": mock_param}

        should_inject = self.injector._should_inject_parameter(
            "api_url", "https://oauth.example.com", node_param_defs
        )

        assert should_inject is True

    def test_should_inject_parameter_auto_map_from(self):
        """Test parameter injection check for auto_map_from match."""
        mock_param = Mock()
        mock_param.auto_map_from = ["api_url", "oauth_url"]

        node_param_defs = {"token_url": mock_param}

        should_inject = self.injector._should_inject_parameter(
            "api_url", "https://oauth.example.com", node_param_defs
        )

        assert should_inject is True

    def test_should_inject_parameter_no_match(self):
        """Test parameter injection check when no match found."""
        node_param_defs = {
            "token_url": NodeParameter(name="token_url", type=str, required=True)
        }

        should_inject = self.injector._should_inject_parameter(
            "database", "test_db", node_param_defs
        )

        assert should_inject is False

    def test_get_mapped_parameter_name_direct_match(self):
        """Test getting mapped parameter name for direct match."""
        node_param_defs = {
            "token_url": NodeParameter(name="token_url", type=str, required=True)
        }

        mapped_name = self.injector._get_mapped_parameter_name(
            "token_url", "https://oauth.example.com", node_param_defs
        )

        assert mapped_name == "token_url"

    def test_get_mapped_parameter_name_workflow_alias(self):
        """Test getting mapped parameter name for workflow alias."""
        mock_param = Mock()
        mock_param.workflow_alias = "api_url"

        node_param_defs = {"token_url": mock_param}

        mapped_name = self.injector._get_mapped_parameter_name(
            "api_url", "https://oauth.example.com", node_param_defs, None
        )

        assert mapped_name == "token_url"

    def test_get_mapped_parameter_name_fuzzy_match(self):
        """Test getting mapped parameter name for fuzzy match."""
        node_param_defs = {
            "input_data": NodeParameter(name="input_data", type=str, required=True)
        }

        # "data" should fuzzy match to "input_data"
        mapped_name = self.injector._get_mapped_parameter_name(
            "data", "test_value", node_param_defs, None
        )

        assert mapped_name == "input_data"

    def test_get_mapped_parameter_name_kwargs_node(self):
        """Test getting mapped parameter name for node that accepts **kwargs."""

        def test_function(**kwargs):
            return kwargs

        python_node = MockPythonCodeNode(name="python_node", function=test_function)
        node_param_defs = python_node.get_parameters()

        mapped_name = self.injector._get_mapped_parameter_name(
            "custom_param", "custom_value", node_param_defs, python_node
        )

        assert mapped_name == "custom_param"

    def test_get_mapped_parameter_name_invalid_inputs(self):
        """Test getting mapped parameter name with invalid inputs."""
        # Test with non-string parameter name
        result = self.injector._get_mapped_parameter_name(123, "value", {}, None)
        assert result is None

        # Test with non-dict node_param_defs
        result = self.injector._get_mapped_parameter_name(
            "param", "value", "not_a_dict", None
        )
        assert result is None

    def test_is_compatible_type_success(self):
        """Test type compatibility check - success cases."""
        mock_param = Mock()
        mock_param.type = str

        assert self.injector._is_compatible_type("test_string", mock_param) is True

        mock_param.type = int
        assert self.injector._is_compatible_type(42, mock_param) is True

    def test_is_compatible_type_failure(self):
        """Test type compatibility check - failure cases."""
        mock_param = Mock()
        mock_param.type = str

        assert self.injector._is_compatible_type(42, mock_param) is False

    def test_is_compatible_type_no_constraint(self):
        """Test type compatibility check with no type constraint."""
        mock_param = Mock()
        # No type attribute
        del mock_param.type

        assert self.injector._is_compatible_type("anything", mock_param) is True

    def test_is_compatible_type_union(self):
        """Test type compatibility check with Union types."""
        mock_param = Mock()
        mock_param.type = Union[str, int]

        assert self.injector._is_compatible_type("test", mock_param) is True
        assert self.injector._is_compatible_type(42, mock_param) is True
        assert self.injector._is_compatible_type(3.14, mock_param) is False

    def test_get_fuzzy_parameter_matches_aliases(self):
        """Test fuzzy parameter matching with known aliases."""
        node_param_defs = {
            "input_data": NodeParameter(name="input_data", type=str),
            "endpoint": NodeParameter(name="endpoint", type=str),
            "configuration": NodeParameter(name="configuration", type=dict),
        }

        # Test known aliases
        matches = self.injector._get_fuzzy_parameter_matches("data", node_param_defs)
        assert "input_data" in matches

        matches = self.injector._get_fuzzy_parameter_matches("url", node_param_defs)
        assert "endpoint" in matches

        matches = self.injector._get_fuzzy_parameter_matches("config", node_param_defs)
        assert "configuration" in matches

    def test_get_fuzzy_parameter_matches_substring(self):
        """Test fuzzy parameter matching with substring matching."""
        node_param_defs = {
            "database_url": NodeParameter(name="database_url", type=str),
            "user_credentials": NodeParameter(name="user_credentials", type=dict),
        }

        # Test substring matching
        matches = self.injector._get_fuzzy_parameter_matches(
            "database", node_param_defs
        )
        assert "database_url" in matches

        matches = self.injector._get_fuzzy_parameter_matches(
            "credentials", node_param_defs
        )
        assert "user_credentials" in matches

    def test_node_accepts_kwargs_pythoncode_with_kwargs(self):
        """Test checking if PythonCodeNode accepts **kwargs."""

        def test_function(param1, param2, **kwargs):
            return {"result": "test"}

        python_node = MockPythonCodeNode(name="python_test", function=test_function)

        accepts_kwargs = self.injector._node_accepts_kwargs(python_node)

        assert accepts_kwargs is True

    def test_node_accepts_kwargs_pythoncode_without_kwargs(self):
        """Test checking PythonCodeNode without **kwargs."""

        def test_function(param1, param2):
            return {"result": "test"}

        python_node = MockPythonCodeNode(name="python_test", function=test_function)

        accepts_kwargs = self.injector._node_accepts_kwargs(python_node)

        assert accepts_kwargs is False

    def test_node_accepts_kwargs_pythoncode_with_code(self):
        """Test checking PythonCodeNode with inline code."""
        python_node = MockPythonCodeNode(
            name="python_test", code="return {'result': 'test'}"
        )

        accepts_kwargs = self.injector._node_accepts_kwargs(python_node)

        assert accepts_kwargs is True

    def test_node_accepts_kwargs_regular_node(self):
        """Test checking regular node (not PythonCodeNode)."""
        oauth_node = MockOAuth2Node(name="oauth_test")

        accepts_kwargs = self.injector._node_accepts_kwargs(oauth_node)

        assert accepts_kwargs is False

    def test_configure_deferred_node_success(self):
        """Test configuring a deferred node with runtime parameters."""
        # Add deferred node to workflow
        deferred_node = DeferredConfigNode(
            MockOAuth2Node, token_url="https://oauth.example.com"
        )
        self.mock_workflow._node_instances["deferred_oauth"] = deferred_node

        self.injector.configure_deferred_node(
            "deferred_oauth", client_id="runtime_client"
        )

        assert deferred_node._runtime_config["client_id"] == "runtime_client"
        assert deferred_node._is_initialized is True

    def test_configure_deferred_node_not_found(self):
        """Test configuring a deferred node that doesn't exist."""
        with pytest.raises(
            ValueError, match="Node 'nonexistent' not found in workflow"
        ):
            self.injector.configure_deferred_node("nonexistent", param="value")

    def test_configure_deferred_node_not_deferred(self):
        """Test configuring a regular node (not deferred)."""
        with pytest.raises(
            ValueError, match="Node 'oauth_node' is not a deferred configuration node"
        ):
            self.injector.configure_deferred_node("oauth_node", param="value")

    def test_get_nested_parameter_non_dict_intermediate(self):
        """Test nested parameter access when intermediate value is not a dict."""
        parameters = {"config": "not_a_dict", "other": {"nested": "value"}}

        # Should return None when path cannot be traversed
        value = self.injector._get_nested_parameter(parameters, "config.redis.host")
        assert value is None

        # Should work for valid paths
        value = self.injector._get_nested_parameter(parameters, "other.nested")
        assert value == "value"

    def test_is_compatible_type_with_none_type(self):
        """Test type compatibility when parameter type is None."""
        mock_param = Mock()
        mock_param.type = None

        assert self.injector._is_compatible_type("any_value", mock_param) is True
        assert self.injector._is_compatible_type(123, mock_param) is True
        assert self.injector._is_compatible_type(None, mock_param) is True

    def test_is_compatible_type_exception_handling(self):
        """Test type compatibility when type checking raises exception."""
        mock_param = Mock()
        # Create a type that raises exception when used with isinstance
        mock_param.type = Mock(side_effect=TypeError("Cannot check type"))

        # Should return True when exception occurs
        assert self.injector._is_compatible_type("any_value", mock_param) is True

    def test_get_mapped_parameter_auto_map_from_string(self):
        """Test parameter mapping with auto_map_from as string (not list)."""
        mock_param = Mock()
        mock_param.auto_map_from = "single_alias"  # String instead of list

        node_param_defs = {"target_param": mock_param}

        mapped = self.injector._get_mapped_parameter_name(
            "single_alias", "value", node_param_defs, None
        )

        assert mapped == "target_param"

    def test_get_mapped_parameter_exception_in_param_def(self):
        """Test parameter mapping when accessing param def raises exception."""

        # Create a param def that raises exception when accessed
        class BrokenParamDef:
            @property
            def workflow_alias(self):
                raise RuntimeError("Cannot access alias")

        node_param_defs = {
            "broken_param": BrokenParamDef(),
            "good_param": NodeParameter(name="good_param", type=str),
        }

        # Should skip broken param and continue
        mapped = self.injector._get_mapped_parameter_name(
            "good_param", "value", node_param_defs, None
        )

        assert mapped == "good_param"

    def test_node_accepts_kwargs_with_wrapper(self):
        """Test kwargs detection for nodes with wrapper attribute."""
        # Create mock wrapper that has accepts_var_keyword method
        mock_wrapper = Mock()
        mock_wrapper.accepts_var_keyword.return_value = True

        node = Mock()
        node.__class__.__name__ = "PythonCodeNode"
        node.wrapper = mock_wrapper
        node.code = None
        node.function = None

        accepts = self.injector._node_accepts_kwargs(node)

        assert accepts is True
        mock_wrapper.accepts_var_keyword.assert_called_once()

    def test_node_accepts_kwargs_invalid_function_signature(self):
        """Test kwargs detection when function signature inspection fails."""

        def broken_function():
            pass

        # Mock inspect.signature to raise exception
        with patch("inspect.signature", side_effect=ValueError("Cannot inspect")):
            node = Mock()
            node.__class__.__name__ = "PythonCodeNode"
            node.function = broken_function
            node.wrapper = None
            node.code = None

            accepts = self.injector._node_accepts_kwargs(node)

            assert accepts is False

    def test_validate_parameters_with_primary_auto_map(self):
        """Test parameter validation with auto_map_primary."""

        # Create node with auto_map_primary parameter
        class NodeWithAutoMapPrimary(Node):
            def get_parameters(self):
                param1 = NodeParameter(name="internal_url", type=str, required=True)
                param1.workflow_alias = "endpoint"

                param2 = NodeParameter(name="auth_token", type=str, required=True)
                param2.auto_map_from = ["token", "api_key", "auth_key"]

                param3 = NodeParameter(name="primary_data", type=Any, required=True)
                param3.auto_map_primary = True

                return {
                    "internal_url": param1,
                    "auth_token": param2,
                    "primary_data": param3,
                }

            def run(self, **kwargs):
                return {"processed": True}

        self.mock_workflow._node_instances["alias_node"] = NodeWithAutoMapPrimary(
            name="alias_node"
        )

        workflow_params = {
            "endpoint": "https://api.example.com",  # Maps to internal_url via alias
            "token": "secret_token",  # Maps to auth_token via auto_map_from
            "some_data": {"key": "value"},  # Should map to primary_data
        }

        warnings = self.injector.validate_parameters(workflow_params)

        # All parameters should be used due to mapping
        assert warnings == []

    def test_configure_deferred_node_no_node_instances(self):
        """Test configuring deferred node when _node_instances doesn't exist."""
        # Remove _node_instances attribute
        delattr(self.mock_workflow, "_node_instances")

        with pytest.raises(ValueError, match="Node 'test_node' not found in workflow"):
            self.injector.configure_deferred_node("test_node", param="value")

    def test_get_all_nodes_no_node_instances(self):
        """Test getting all nodes when _node_instances doesn't exist."""
        # Create workflow without _node_instances
        workflow = Mock()
        workflow.nodes = {"node1": Mock(), "node2": Mock()}
        delattr(workflow, "_node_instances")

        injector = WorkflowParameterInjector(workflow)
        all_nodes = injector._get_all_nodes()

        assert all_nodes == {}

    def test_transform_parameters_with_complex_nested_paths(self):
        """Test transforming parameters with complex nested workflow input mappings."""
        self.mock_workflow.metadata = {
            "_workflow_inputs": {
                "cache_node": {
                    "config.redis.host": "redis_host",
                    "config.redis.port": "redis_port",
                },
                "llm_node": {
                    "ai.model_name": "model",
                    "ai.settings.temperature": "temperature",
                },
            }
        }

        workflow_params = {
            "config": {"redis": {"host": "redis-server", "port": 6380}},
            "ai": {"model_name": "gpt-4", "settings": {"temperature": 0.7}},
        }

        result = self.injector.transform_workflow_parameters(workflow_params)

        # Should map nested parameters correctly
        assert result["cache_node"]["redis_host"] == "redis-server"
        assert result["cache_node"]["redis_port"] == 6380
        assert result["llm_node"]["model"] == "gpt-4"
        assert result["llm_node"]["temperature"] == 0.7


class TestConvenienceFunctions:
    """Test convenience functions for creating deferred nodes."""

    @patch("kailash.nodes.api.auth.OAuth2Node")
    def test_create_deferred_oauth2(self, mock_oauth2_class):
        """Test creating deferred OAuth2 node."""
        mock_oauth2_class.__name__ = "OAuth2Node"

        deferred_node = create_deferred_oauth2(
            token_url="https://oauth.example.com", client_id="test_client"
        )

        assert isinstance(deferred_node, DeferredConfigNode)
        assert deferred_node._node_class == mock_oauth2_class
        assert deferred_node._initial_config["token_url"] == "https://oauth.example.com"
        assert deferred_node._initial_config["client_id"] == "test_client"

    @patch("kailash.nodes.data.async_sql.AsyncSQLDatabaseNode")
    def test_create_deferred_sql(self, mock_sql_class):
        """Test creating deferred SQL node."""
        mock_sql_class.__name__ = "AsyncSQLDatabaseNode"

        deferred_node = create_deferred_sql(
            database="test_db", query="SELECT * FROM users"
        )

        assert isinstance(deferred_node, DeferredConfigNode)
        assert deferred_node._node_class == mock_sql_class
        assert deferred_node._initial_config["database"] == "test_db"
        assert deferred_node._initial_config["query"] == "SELECT * FROM users"

    def test_create_deferred_node(self):
        """Test creating deferred node for any node class."""
        deferred_node = create_deferred_node(
            MockHTTPNode, url="https://api.example.com"
        )

        assert isinstance(deferred_node, DeferredConfigNode)
        assert deferred_node._node_class == MockHTTPNode
        assert deferred_node._initial_config["url"] == "https://api.example.com"
