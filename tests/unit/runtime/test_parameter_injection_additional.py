"""
Additional unit tests for kailash.runtime.parameter_injection module to achieve 100% coverage.

Tests the edge cases and uncovered lines:
- get_parameters() when node is initialized
- exception handling in wrapped node get_parameters
"""

from unittest.mock import MagicMock, patch

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.parameter_injection import (
    ConfigurableAsyncSQLNode,
    ConfigurableOAuth2Node,
    EnterpriseNodeFactory,
)


class BrokenNode(Node):
    """Node that fails to instantiate without parameters."""

    def __init__(self, required_param):
        super().__init__(name="broken")
        self.required_param = required_param

    def get_parameters(self):
        return {
            "required_param": NodeParameter(
                name="required_param",
                type=str,
                required=True,
                description="Required parameter",
            )
        }

    def run(self, **kwargs):
        return {"result": self.required_param}


class TestConfigurableOAuth2NodeCoverage:
    """Additional tests for ConfigurableOAuth2Node coverage."""

    @patch("kailash.nodes.api.auth.OAuth2Node")
    def test_get_parameters_after_initialization(self, mock_oauth_class):
        """Test get_parameters when OAuth2Node is initialized (line 179)."""
        # Create mock OAuth2Node instance
        mock_oauth_instance = MagicMock()
        mock_oauth_params = {
            "token_url": NodeParameter(
                name="token_url",
                type=str,
                required=True,
                description="Mocked OAuth token URL",
            ),
            "custom_param": NodeParameter(
                name="custom_param",
                type=str,
                required=False,
                description="Custom OAuth parameter",
            ),
        }
        mock_oauth_instance.get_parameters.return_value = mock_oauth_params
        mock_oauth_class.return_value = mock_oauth_instance

        # Create and initialize node
        node = ConfigurableOAuth2Node()
        node._perform_initialization(
            {"token_url": "https://auth.example.com/token", "client_id": "test_client"}
        )

        # Get parameters after initialization
        params = node.get_parameters()

        # Should return parameters from the initialized OAuth2Node
        assert params == mock_oauth_params
        assert "custom_param" in params
        mock_oauth_instance.get_parameters.assert_called_once()


class TestConfigurableAsyncSQLNodeCoverage:
    """Additional tests for ConfigurableAsyncSQLNode coverage."""

    @patch("kailash.nodes.data.async_sql.AsyncSQLDatabaseNode")
    def test_get_parameters_after_initialization(self, mock_sql_class):
        """Test get_parameters when AsyncSQLDatabaseNode is initialized (line 283)."""
        # Create mock AsyncSQLDatabaseNode instance
        mock_sql_instance = MagicMock()
        mock_sql_params = {
            "query": NodeParameter(
                name="query", type=str, required=True, description="Mocked SQL query"
            ),
            "custom_sql_param": NodeParameter(
                name="custom_sql_param",
                type=dict,
                required=False,
                description="Custom SQL parameter",
            ),
        }
        mock_sql_instance.get_parameters.return_value = mock_sql_params
        mock_sql_class.return_value = mock_sql_instance

        # Create and initialize node
        node = ConfigurableAsyncSQLNode()
        node._perform_initialization(
            {
                "database_type": "postgresql",
                "host": "localhost",
                "database": "test_db",
                "query": "SELECT 1",
            }
        )

        # Get parameters after initialization
        params = node.get_parameters()

        # Should return parameters from the initialized AsyncSQLDatabaseNode
        assert params == mock_sql_params
        assert "custom_sql_param" in params
        mock_sql_instance.get_parameters.assert_called_once()


class TestEnterpriseNodeFactoryCoverage:
    """Additional tests for EnterpriseNodeFactory coverage."""

    def test_wrapped_node_get_parameters_after_init(self):
        """Test wrapped node get_parameters when node is initialized (line 395)."""

        # Create a simple test node class
        class TestNode(Node):
            def get_parameters(self):
                return {
                    "test_param": NodeParameter(
                        name="test_param",
                        type=str,
                        required=True,
                        description="Test parameter",
                    )
                }

            def run(self, **kwargs):
                return {"result": kwargs.get("test_param")}

        # Create wrapped node
        wrapped = EnterpriseNodeFactory.wrap_enterprise_node(TestNode)

        # Initialize the wrapped node
        wrapped._perform_initialization({"name": "test"})

        # Get parameters after initialization
        params = wrapped.get_parameters()

        # Should return parameters from the wrapped node instance
        assert "test_param" in params
        assert params["test_param"].required is True

    def test_wrapped_node_get_parameters_with_broken_class(self):
        """Test wrapped node get_parameters with class that fails instantiation (lines 401-402)."""
        # Create wrapped node with BrokenNode that requires parameters
        wrapped = EnterpriseNodeFactory.wrap_enterprise_node(BrokenNode)

        # Get parameters before initialization (should catch exception)
        params = wrapped.get_parameters()

        # Should return empty dict due to exception
        assert params == {}

    def test_wrapped_node_get_parameters_with_working_class(self):
        """Test wrapped node get_parameters without initialization but working class."""

        # Create a node that can be instantiated without parameters
        class SimpleNode(Node):
            def __init__(self, **kwargs):
                super().__init__(name=kwargs.get("name", "simple"))

            def get_parameters(self):
                return {
                    "simple_param": NodeParameter(
                        name="simple_param",
                        type=str,
                        required=False,
                        description="Simple parameter",
                    )
                }

            def run(self, **kwargs):
                return {"result": "simple"}

        # Create wrapped node
        wrapped = EnterpriseNodeFactory.wrap_enterprise_node(SimpleNode)

        # Get parameters before initialization
        params = wrapped.get_parameters()

        # Should successfully get parameters from temporary instance
        assert "simple_param" in params
        assert params["simple_param"].required is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
