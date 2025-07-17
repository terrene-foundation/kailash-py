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
            MockSQLNode, connection_string="postgresql://user:pass@host/db"
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

        # oauth_node and http_node should be entry nodes
        assert len(entry_nodes) == 2
        assert "oauth_node" in entry_nodes
        assert "http_node" in entry_nodes
        assert "sql_node" not in entry_nodes

    def test_get_all_nodes(self):
        """Test getting all nodes in workflow."""
        all_nodes = self.injector._get_all_nodes()

        assert len(all_nodes) == 3
        assert "oauth_node" in all_nodes
        assert "sql_node" in all_nodes
        assert "http_node" in all_nodes
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
