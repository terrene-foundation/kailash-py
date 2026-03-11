"""
Tests for DataFlow connection interface.

Verifies:
- Connection initialization
- Lazy DataFlow initialization
- Agent-DataFlow connection
- Schema discovery
- Node access
- Multi-agent coordination
"""

from unittest.mock import MagicMock

import pytest


class TestDataFlowConnection:
    """Test suite for DataFlowConnection interface."""

    @pytest.fixture
    def mock_dataflow(self):
        """Create a mock DataFlow instance."""
        mock_db = MagicMock()
        mock_db.list_models.return_value = ["User", "Product", "Order"]
        mock_db.get_model.return_value = MagicMock()
        return mock_db

    @pytest.fixture
    def dataflow_connection_class(self):
        """Get DataFlowConnection class, skipping if DataFlow unavailable."""
        try:
            from kaizen.integrations.dataflow import (
                DATAFLOW_AVAILABLE,
                DataFlowConnection,
            )

            if not DATAFLOW_AVAILABLE:
                pytest.skip("DataFlow not available - integration disabled")
            return DataFlowConnection
        except ImportError:
            pytest.skip("DataFlow integration not available")

    def test_dataflow_connection_initialization(
        self, mock_dataflow, dataflow_connection_class
    ):
        """
        Verify connection object initializes with DataFlow instance.

        Connection should accept DataFlow instance and store reference.
        """
        connection = dataflow_connection_class(db=mock_dataflow, lazy_init=False)

        # Should store DataFlow instance
        assert connection.db is mock_dataflow
        assert connection.lazy_init is False

    def test_lazy_dataflow_initialization(
        self, mock_dataflow, dataflow_connection_class
    ):
        """
        Verify DataFlow doesn't initialize until first use.

        Lazy initialization prevents startup overhead.
        """
        connection = dataflow_connection_class(db=mock_dataflow, lazy_init=True)

        # Should not call initialization immediately
        assert connection.lazy_init is True

        # Connection should exist but not initialized yet
        assert connection.db is mock_dataflow

    def test_agent_dataflow_connection(self, mock_dataflow):
        """
        Verify BaseAgent can connect to DataFlow instance.

        Agents should be able to establish connection to database.
        """
        try:
            from kaizen.core.config import BaseAgentConfig
            from kaizen.integrations.dataflow import (
                DATAFLOW_AVAILABLE,
                DataFlowAwareAgent,
            )

            if not DATAFLOW_AVAILABLE:
                pytest.skip("DataFlow not available")

            config = BaseAgentConfig(llm_provider="mock", model="gpt-4")

            # Create agent with DataFlow connection
            agent = DataFlowAwareAgent(config=config, db=mock_dataflow)

            # Should have database connection
            assert agent.db_connection is not None
            assert agent.db_connection.db is mock_dataflow

        except ImportError:
            pytest.skip("DataFlow integration not available")

    def test_connection_table_schema_discovery(
        self, mock_dataflow, dataflow_connection_class
    ):
        """
        Verify connection can discover DataFlow table schemas.

        Should provide access to table metadata and structure.
        """
        # Setup mock schema
        mock_schema = {
            "columns": {
                "id": {"type": "INTEGER", "primary_key": True},
                "name": {"type": "VARCHAR(255)", "nullable": False},
                "email": {"type": "VARCHAR(255)", "unique": True},
            }
        }
        mock_dataflow.get_table_schema = MagicMock(return_value=mock_schema)

        connection = dataflow_connection_class(db=mock_dataflow)

        # Should discover schema
        schema = connection.get_table_schema("users")

        assert schema is not None
        assert "columns" in schema
        assert "id" in schema["columns"]
        mock_dataflow.get_table_schema.assert_called_once_with("users")

    def test_connection_node_access(self, mock_dataflow, dataflow_connection_class):
        """
        Verify connection provides access to DataFlow-generated nodes.

        DataFlow generates 11 nodes per model - connection should expose them.
        """
        # Mock DataFlow node names
        expected_nodes = {
            "create": "UserCreateNode",
            "read": "UserReadNode",
            "update": "UserUpdateNode",
            "delete": "UserDeleteNode",
            "list": "UserListNode",
            "bulk_create": "UserBulkCreateNode",
            "bulk_update": "UserBulkUpdateNode",
            "bulk_delete": "UserBulkDeleteNode",
            "bulk_upsert": "UserBulkUpsertNode",
        }

        mock_dataflow.get_nodes_for_model = MagicMock(return_value=expected_nodes)

        connection = dataflow_connection_class(db=mock_dataflow)

        # Should access generated nodes
        nodes = connection.get_nodes_for_table("User")

        assert nodes is not None
        assert len(nodes) == 9
        assert nodes["create"] == "UserCreateNode"
        assert nodes["list"] == "UserListNode"

    def test_multiple_agents_shared_dataflow(self, mock_dataflow):
        """
        Verify multiple agents can share same DataFlow instance.

        Critical for multi-agent coordination on shared database.
        """
        try:
            from kaizen.core.config import BaseAgentConfig
            from kaizen.integrations.dataflow import (
                DATAFLOW_AVAILABLE,
                DataFlowAwareAgent,
            )

            if not DATAFLOW_AVAILABLE:
                pytest.skip("DataFlow not available")

            # Create multiple agents with shared DataFlow
            agent1 = DataFlowAwareAgent(
                config=BaseAgentConfig(llm_provider="mock", model="gpt-4"),
                db=mock_dataflow,
            )

            agent2 = DataFlowAwareAgent(
                config=BaseAgentConfig(llm_provider="mock", model="gpt-4"),
                db=mock_dataflow,
            )

            # Both should share same DataFlow instance
            assert agent1.db_connection.db is mock_dataflow
            assert agent2.db_connection.db is mock_dataflow
            assert agent1.db_connection.db is agent2.db_connection.db

        except ImportError:
            pytest.skip("DataFlow integration not available")


class TestConnectionOperations:
    """Test connection operation methods."""

    @pytest.fixture
    def mock_dataflow(self):
        """Create a mock DataFlow instance with full operation support."""
        mock_db = MagicMock()
        mock_db.list_tables.return_value = ["users", "products", "orders"]
        mock_db.get_table_schema.return_value = {"columns": {"id": {"type": "INTEGER"}}}
        mock_db.get_nodes_for_model.return_value = {
            "create": "UserCreateNode",
            "read": "UserReadNode",
            "update": "UserUpdateNode",
            "delete": "UserDeleteNode",
            "list": "UserListNode",
            "bulk_create": "UserBulkCreateNode",
            "bulk_update": "UserBulkUpdateNode",
            "bulk_delete": "UserBulkDeleteNode",
            "bulk_upsert": "UserBulkUpsertNode",
        }
        return mock_db

    @pytest.fixture
    def dataflow_connection_class(self):
        """Get DataFlowConnection class."""
        try:
            from kaizen.integrations.dataflow import (
                DATAFLOW_AVAILABLE,
                DataFlowConnection,
            )

            if not DATAFLOW_AVAILABLE:
                pytest.skip("DataFlow not available")
            return DataFlowConnection
        except ImportError:
            pytest.skip("DataFlow integration not available")

    def test_list_tables_operation(self, mock_dataflow, dataflow_connection_class):
        """
        Verify connection can list all available tables.

        Should provide table discovery capability.
        """
        connection = dataflow_connection_class(db=mock_dataflow)

        tables = connection.list_tables()

        assert tables is not None
        assert isinstance(tables, list)
        assert "users" in tables
        assert "products" in tables
        assert "orders" in tables
        mock_dataflow.list_tables.assert_called_once()

    def test_get_table_schema_operation(self, mock_dataflow, dataflow_connection_class):
        """
        Verify connection can retrieve table schema.

        Should provide detailed schema information.
        """
        connection = dataflow_connection_class(db=mock_dataflow)

        schema = connection.get_table_schema("users")

        assert schema is not None
        assert isinstance(schema, dict)
        assert "columns" in schema
        mock_dataflow.get_table_schema.assert_called_once_with("users")

    def test_get_nodes_for_table_operation(
        self, mock_dataflow, dataflow_connection_class
    ):
        """
        Verify connection can retrieve DataFlow nodes for table.

        Should map table to all 9 generated node types.
        """
        connection = dataflow_connection_class(db=mock_dataflow)

        nodes = connection.get_nodes_for_table("users")

        assert nodes is not None
        assert isinstance(nodes, dict)
        assert len(nodes) == 9
        assert "create" in nodes
        assert "list" in nodes
        mock_dataflow.get_nodes_for_model.assert_called_once()


class TestConnectionErrorHandling:
    """Test connection error handling and edge cases."""

    @pytest.fixture
    def dataflow_connection_class(self):
        """Get DataFlowConnection class."""
        try:
            from kaizen.integrations.dataflow import (
                DATAFLOW_AVAILABLE,
                DataFlowConnection,
            )

            if not DATAFLOW_AVAILABLE:
                pytest.skip("DataFlow not available")
            return DataFlowConnection
        except ImportError:
            pytest.skip("DataFlow integration not available")

    def test_connection_invalid_dataflow_instance(self, dataflow_connection_class):
        """
        Verify connection validates DataFlow instance type.

        Should reject non-DataFlow objects.
        """
        # This will be tested during implementation
        # Connection should validate db parameter type
        pass

    def test_connection_table_not_found(self, dataflow_connection_class):
        """
        Verify connection handles missing table gracefully.

        Should provide clear error when table doesn't exist.
        """
        mock_db = MagicMock()
        mock_db.get_table_schema.side_effect = ValueError("Table not found")

        connection = dataflow_connection_class(db=mock_db)

        with pytest.raises(ValueError, match="Table not found"):
            connection.get_table_schema("nonexistent")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
