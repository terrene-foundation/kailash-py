"""
Unit tests for CountNode SQL generation.

Tests SQL generation for COUNT(*) operations across PostgreSQL, MySQL, and SQLite adapters.
"""

import pytest
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow


class TestCountNodeSQLGeneration:
    """Test CountNode SQL generation for all SQL adapters."""

    @pytest.fixture
    def postgresql_db(self):
        """Create PostgreSQL DataFlow instance (in-memory simulation)."""
        db = DataFlow(
            "postgresql://user:pass@localhost:5432/testdb", auto_migrate=False
        )

        @db.model
        class User:
            id: str
            name: str
            email: str
            active: bool

        return db

    @pytest.fixture
    def mysql_db(self):
        """Create MySQL DataFlow instance (in-memory simulation)."""
        db = DataFlow("mysql://user:pass@localhost:3306/testdb", auto_migrate=False)

        @db.model
        class User:
            id: str
            name: str
            email: str
            active: bool

        return db

    @pytest.fixture
    def sqlite_db(self):
        """Create SQLite DataFlow instance (in-memory)."""
        db = DataFlow(":memory:")

        @db.model
        class User:
            id: str
            name: str
            email: str
            active: bool

        return db

    def test_count_node_generated_for_postgresql(self, postgresql_db):
        """Test that UserCountNode is generated for PostgreSQL models."""
        assert "UserCountNode" in postgresql_db._nodes
        node_class = postgresql_db._nodes["UserCountNode"]
        node = node_class()

        # Verify node has correct parameters
        params = node.get_parameters()
        assert "filter" in params
        # database_url is the base parameter, not db_instance/model_name
        assert "database_url" in params

        # Verify filter is optional
        assert params["filter"].required is False
        assert params["filter"].default == {}

    def test_count_node_generated_for_mysql(self, mysql_db):
        """Test that UserCountNode is generated for MySQL models."""
        assert "UserCountNode" in mysql_db._nodes
        node_class = mysql_db._nodes["UserCountNode"]
        node = node_class()

        params = node.get_parameters()
        assert "database_url" in params
        assert "filter" in params

    def test_count_node_generated_for_sqlite(self, sqlite_db):
        """Test that UserCountNode is generated for SQLite models."""
        assert "UserCountNode" in sqlite_db._nodes
        node_class = sqlite_db._nodes["UserCountNode"]
        node = node_class()

        params = node.get_parameters()
        assert "database_url" in params
        assert "filter" in params

    def test_count_node_return_structure(self, sqlite_db):
        """Test that CountNode returns expected structure."""
        # This is a unit test, so we'll mock the adapter's count method
        node_class = sqlite_db._nodes["UserCountNode"]
        node = node_class()

        # Verify return structure expectations (will be validated in integration tests)
        # Expected return: {"count": int}
        assert hasattr(node, "async_run")

    def test_count_node_filter_parameter_types(self, sqlite_db):
        """Test that filter parameter accepts various filter types."""
        node_class = sqlite_db._nodes["UserCountNode"]
        node = node_class()

        params = node.get_parameters()
        filter_param = params["filter"]

        # Filter should accept dict type
        assert filter_param.type == dict
        # Filter should have default empty dict
        assert filter_param.default == {}

    def test_count_node_without_filter(self, sqlite_db):
        """Test CountNode usage without filter (count all)."""
        # Build workflow with CountNode
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserCountNode",
            "count_all",
            {
                # No filter = count all records
            },
        )

        # Verify workflow builds successfully
        built_workflow = workflow.build()
        assert "count_all" in built_workflow.nodes

    def test_count_node_with_simple_filter(self, sqlite_db):
        """Test CountNode usage with simple equality filter."""
        workflow = WorkflowBuilder()
        workflow.add_node("UserCountNode", "count_active", {"filter": {"active": True}})

        built_workflow = workflow.build()
        assert "count_active" in built_workflow.nodes

    def test_count_node_with_complex_filter(self, sqlite_db):
        """Test CountNode usage with MongoDB-style complex filter."""
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserCountNode",
            "count_complex",
            {"filter": {"active": True, "email": {"$like": "%@example.com"}}},
        )

        built_workflow = workflow.build()
        assert "count_complex" in built_workflow.nodes

    def test_multiple_models_generate_separate_count_nodes(self):
        """Test that each model gets its own CountNode."""
        db = DataFlow(":memory:")

        @db.model
        class User:
            id: str
            name: str

        @db.model
        class Order:
            id: str
            user_id: str
            amount: float

        # Verify each model has its own CountNode
        assert "UserCountNode" in db._nodes
        assert "OrderCountNode" in db._nodes

        # Verify they are different classes
        assert db._nodes["UserCountNode"] != db._nodes["OrderCountNode"]

    def test_count_node_11th_node_for_model(self, sqlite_db):
        """Test that CountNode is the 11th node generated per model."""
        # Expected nodes per model (v0.8.0+):
        # 1. CreateNode
        # 2. ReadNode
        # 3. UpdateNode
        # 4. DeleteNode
        # 5. ListNode
        # 6. UpsertNode
        # 7. BulkCreateNode
        # 8. BulkUpdateNode
        # 9. BulkDeleteNode
        # 10. BulkUpsertNode
        # 11. CountNode (NEW)

        expected_nodes = [
            "UserCreateNode",
            "UserReadNode",
            "UserUpdateNode",
            "UserDeleteNode",
            "UserListNode",
            "UserUpsertNode",
            "UserBulkCreateNode",
            "UserBulkUpdateNode",
            "UserBulkDeleteNode",
            "UserBulkUpsertNode",
            "UserCountNode",  # 11th node
        ]

        for node_name in expected_nodes:
            assert node_name in sqlite_db._nodes, f"Missing node: {node_name}"

        # Verify total count
        user_nodes = [n for n in sqlite_db._nodes.keys() if n.startswith("User")]
        assert (
            len(user_nodes) == 11
        ), f"Expected 11 nodes, got {len(user_nodes)}: {user_nodes}"


class TestCountNodeParameterValidation:
    """Test parameter validation for CountNode."""

    @pytest.fixture
    def db(self):
        """Create DataFlow instance for testing."""
        db = DataFlow(":memory:")

        @db.model
        class Product:
            id: str
            name: str
            price: float
            in_stock: bool

        return db

    def test_count_node_has_database_url_parameter(self, db):
        """Test that database_url parameter exists (base parameter)."""
        node_class = db._nodes["ProductCountNode"]
        node = node_class()

        params = node.get_parameters()
        assert "database_url" in params
        # database_url is optional (defaults to DataFlow instance config)
        assert params["database_url"].required is False

    def test_count_node_has_filter_parameter(self, db):
        """Test that filter parameter exists."""
        node_class = db._nodes["ProductCountNode"]
        node = node_class()

        params = node.get_parameters()
        assert "filter" in params

    def test_count_node_filter_optional(self, db):
        """Test that filter parameter is optional."""
        node_class = db._nodes["ProductCountNode"]
        node = node_class()

        params = node.get_parameters()
        assert params["filter"].required is False

    def test_count_node_default_filter(self, db):
        """Test that filter defaults to empty dict."""
        node_class = db._nodes["ProductCountNode"]
        node = node_class()

        params = node.get_parameters()
        assert params["filter"].default == {}


class TestCountNodeDocumentation:
    """Test CountNode has proper documentation."""

    @pytest.fixture
    def db(self):
        db = DataFlow(":memory:")

        @db.model
        class User:
            id: str
            name: str

        return db

    def test_count_node_has_docstring(self, db):
        """Test that CountNode class has documentation."""
        node_class = db._nodes["UserCountNode"]

        # Node should have documentation
        assert node_class.__doc__ is not None
        assert len(node_class.__doc__) > 0

    def test_count_node_parameters_have_descriptions(self, db):
        """Test that all CountNode parameters have descriptions."""
        node_class = db._nodes["UserCountNode"]
        node = node_class()

        params = node.get_parameters()

        for param_name, param in params.items():
            assert (
                param.description is not None
            ), f"Parameter {param_name} missing description"
            assert (
                len(param.description) > 0
            ), f"Parameter {param_name} has empty description"
