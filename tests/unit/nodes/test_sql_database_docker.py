"""Unit tests for SQL Database nodes with mocked external dependencies.

NOTE: Tests requiring real Docker/PostgreSQL/MySQL/Ollama services have been
moved to tests/integration/nodes/test_sql_database_docker.py
"""

from unittest.mock import Mock, patch

import pytest

from kailash.nodes.data import AsyncSQLDatabaseNode, SQLDatabaseNode


@pytest.mark.unit
class TestSQLDatabaseNodeUnit:
    """Unit tests for SQL database nodes with mocked dependencies."""

    def test_node_initialization(self):
        """Test node initialization with connection string."""
        connection_string = "postgresql://user:pass@localhost:5432/testdb"
        node = SQLDatabaseNode(connection_string=connection_string)

        assert node.connection_string == connection_string
        assert hasattr(node, "execute")

    def test_async_node_initialization(self):
        """Test async node initialization."""
        node = AsyncSQLDatabaseNode(
            database_type="postgresql",
            host="localhost",
            port=5432,
            database="testdb",
            user="user",
            password="pass",
            query="SELECT 1",  # Required parameter
        )

        assert node.config.get("database_type") == "postgresql"
        assert node.config.get("host") == "localhost"
        assert hasattr(node, "async_run")

    def test_parameter_validation(self):
        """Test parameter validation for SQL nodes."""
        # Test missing connection string
        from kailash.sdk_exceptions import NodeExecutionError

        with pytest.raises(NodeExecutionError):
            SQLDatabaseNode()

    @patch("kailash.nodes.data.sql.create_engine")
    def test_mocked_database_operation(self, mock_create_engine):
        """Test database operations with mocked engine."""
        # Mock the database engine and connection
        mock_engine = Mock()
        mock_connection = Mock()
        mock_result = Mock()
        mock_context = Mock()

        mock_create_engine.return_value = mock_engine
        mock_engine.connect.return_value = mock_context
        mock_context.__enter__ = Mock(return_value=mock_connection)
        mock_context.__exit__ = Mock(return_value=None)
        mock_connection.execute.return_value = mock_result
        mock_result.fetchall.return_value = [{"count": 5}]

        node = SQLDatabaseNode(connection_string="postgresql://test")

        # This would be a real test with proper mocking implementation
        # The actual implementation depends on how the SQLDatabaseNode is structured
        assert node.connection_string == "postgresql://test"
