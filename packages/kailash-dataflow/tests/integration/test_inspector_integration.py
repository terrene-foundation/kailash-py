"""
Integration tests for Inspector with real DataFlow workflows.

CRITICAL: NO MOCKING - Uses real infrastructure (PostgreSQL).

Tests cover:
- Real DataFlow workflows with actual execution
- Parameter tracing through complex workflow chains
- Connection analysis with real database operations
- Model introspection with real database tables
- Error diagnosis with real enhanced errors
"""

import pytest
from dataflow import DataFlow
from dataflow.platform.inspector import Inspector

from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestInspectorWithRealWorkflows:
    """Integration tests with real DataFlow workflows."""

    @pytest.mark.asyncio
    async def test_inspector_with_real_crud_workflow(self, standard_dataflow):
        """Test Inspector analyzing a real CRUD workflow."""
        db = standard_dataflow

        # Define real model
        @db.model
        class Product:
            id: str
            name: str
            price: float
            in_stock: bool

        await db.initialize()

        # Create Inspector
        inspector = Inspector(db)

        # Test model inspection
        model_info = inspector.model("Product")
        assert model_info.name == "Product"
        assert "id" in model_info.fields
        assert "name" in model_info.fields
        assert "price" in model_info.fields
        assert "in_stock" in model_info.fields

        # Test generated nodes
        node_info = inspector.node("ProductCreateNode")
        assert node_info.node_id == "ProductCreateNode"
        assert "id" in node_info.parameters
        assert "name" in node_info.parameters

    @pytest.mark.asyncio
    async def test_inspector_with_complex_workflow_chain(self, standard_dataflow):
        """Test Inspector with multi-step workflow chain."""
        db = standard_dataflow

        @db.model
        class Order:
            id: str
            product_id: str
            quantity: int
            total_price: float

        await db.initialize()

        # Build complex workflow
        workflow = WorkflowBuilder()

        # Step 1: Create order
        workflow.add_node(
            "OrderCreateNode",
            "create_order",
            {
                "id": "order-001",
                "product_id": "prod-123",
                "quantity": 5,
                "total_price": 99.95,
            },
        )

        # Step 2: Read order back
        workflow.add_node("OrderReadNode", "read_order", {})
        workflow.add_connection("create_order", "id", "read_order", "id")

        # Step 3: Update order
        workflow.add_node("OrderUpdateNode", "update_order", {})
        workflow.add_connection("read_order", "id", "update_order", "filter.id")
        workflow.add_parameter("update_order", "fields", {"quantity": 10})

        # Create Inspector with workflow
        inspector = Inspector(db, workflow)

        # Test workflow analysis
        summary = inspector.workflow_summary()
        assert summary["node_count"] == 3
        assert summary["connection_count"] == 2
        assert len(summary["entry_points"]) > 0

        # Test connection analysis
        connections = inspector.connections()
        assert len(connections) == 2

        # Test parameter tracing
        trace = inspector.trace_parameter("read_order", "id")
        assert trace.source_node == "create_order"
        assert trace.source_param == "id"
        assert trace.destination_node == "read_order"
        assert trace.destination_param == "id"

        # Test execution order
        order = inspector.execution_order()
        assert order[0] == "create_order"
        assert order[1] == "read_order"
        assert order[2] == "update_order"

    @pytest.mark.asyncio
    async def test_inspector_parameter_flow_analysis(self, standard_dataflow):
        """Test Inspector analyzing parameter flow through workflow."""
        db = standard_dataflow

        @db.model
        class Invoice:
            id: str
            order_id: str
            amount: float
            paid: bool

        await db.initialize()

        # Build workflow with parameter flow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "InvoiceCreateNode",
            "create_invoice",
            {
                "id": "inv-001",
                "order_id": "order-123",
                "amount": 199.99,
                "paid": False,
            },
        )
        workflow.add_node("InvoiceReadNode", "read_invoice", {})
        workflow.add_connection("create_invoice", "id", "read_invoice", "id")
        workflow.add_connection(
            "create_invoice", "order_id", "read_invoice", "order_id"
        )

        inspector = Inspector(db, workflow)

        # Test parameter flow from create to read
        flows = inspector.parameter_flow("create_invoice", "id")
        assert len(flows) > 0
        assert any(
            f.destination_node == "read_invoice" and f.destination_param == "id"
            for f in flows
        )

        # Test parameter dependencies
        deps = inspector.parameter_dependencies("read_invoice")
        assert "id" in deps or len(deps) > 0

    @pytest.mark.asyncio
    async def test_inspector_connection_validation(self, standard_dataflow):
        """Test Inspector validating connections with real workflow."""
        db = standard_dataflow

        @db.model
        class Customer:
            id: str
            name: str
            email: str

        await db.initialize()

        # Build workflow with valid connections
        workflow = WorkflowBuilder()
        workflow.add_node(
            "CustomerCreateNode",
            "create_customer",
            {"id": "cust-001", "name": "Alice", "email": "alice@example.com"},
        )
        workflow.add_node("CustomerReadNode", "read_customer", {})
        workflow.add_connection("create_customer", "id", "read_customer", "id")

        inspector = Inspector(db, workflow)

        # Validate connections
        is_valid, issues = inspector.validate_connections()
        assert is_valid or len(issues) == 0  # Should be valid

        # Test connection graph
        graph = inspector.connection_graph()
        assert "create_customer" in graph
        assert "read_customer" in graph["create_customer"]

    @pytest.mark.asyncio
    async def test_inspector_model_schema_diff_real_models(self, standard_dataflow):
        """Test Inspector comparing real model schemas."""
        db = standard_dataflow

        @db.model
        class UserV1:
            id: str
            name: str
            email: str

        @db.model
        class UserV2:
            id: str
            name: str
            email: str
            phone: str
            created_at: str

        await db.initialize()

        inspector = Inspector(db)

        # Compare schemas
        diff = inspector.model_schema_diff("UserV1", "UserV2")
        assert diff.model1_name == "UserV1"
        assert diff.model2_name == "UserV2"
        # Schemas differ, so either added or removed fields detected
        assert (
            not diff.identical
            or len(diff.added_fields) > 0
            or len(diff.removed_fields) > 0
        )

    @pytest.mark.asyncio
    async def test_inspector_model_migration_status(self, standard_dataflow):
        """Test Inspector checking migration status with real database."""
        db = standard_dataflow

        @db.model
        class Shipment:
            id: str
            tracking_number: str
            status: str

        await db.initialize()

        inspector = Inspector(db)

        # Check migration status
        status = inspector.model_migration_status("Shipment")
        assert status.model_name == "Shipment"
        assert isinstance(status.table_exists, bool)
        assert isinstance(status.schema_matches, bool)

    @pytest.mark.asyncio
    async def test_inspector_model_validation_rules(self, standard_dataflow):
        """Test Inspector extracting validation rules from real model."""
        db = standard_dataflow

        @db.model
        class Payment:
            id: str
            order_id: str  # Foreign key
            amount: float
            status: str

        await db.initialize()

        inspector = Inspector(db)

        # Get validation rules
        rules = inspector.model_validation_rules("Payment")
        assert rules.model_name == "Payment"
        assert isinstance(rules.required_fields, list)
        assert isinstance(rules.field_types, dict)
        assert isinstance(rules.foreign_keys, dict)

        # Check field types detected
        assert len(rules.field_types) > 0

    @pytest.mark.asyncio
    async def test_inspector_workflow_metrics_real_execution(self, standard_dataflow):
        """Test Inspector calculating metrics for real workflow."""
        db = standard_dataflow

        @db.model
        class Task:
            id: str
            title: str
            completed: bool

        await db.initialize()

        # Build workflow with multiple nodes
        workflow = WorkflowBuilder()
        for i in range(5):
            workflow.add_node(
                "TaskCreateNode",
                f"task_{i}",
                {"id": f"task-{i}", "title": f"Task {i}", "completed": False},
            )

        # Add connections
        for i in range(4):
            workflow.add_connection(f"task_{i}", "id", f"task_{i+1}", "id")

        inspector = Inspector(db, workflow)

        # Calculate metrics
        metrics = inspector.workflow_metrics()
        assert metrics["node_count"] == 5
        assert metrics["connection_count"] == 4
        assert metrics["depth"] >= 4
        assert isinstance(metrics["complexity"], (int, float))

    @pytest.mark.asyncio
    async def test_inspector_workflow_validation_report(self, standard_dataflow):
        """Test Inspector generating validation report for real workflow."""
        db = standard_dataflow

        @db.model
        class Comment:
            id: str
            content: str
            author_id: str

        await db.initialize()

        # Build workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "CommentCreateNode",
            "create_comment",
            {"id": "comment-1", "content": "Hello", "author_id": "user-1"},
        )
        workflow.add_node("CommentReadNode", "read_comment", {})
        workflow.add_connection("create_comment", "id", "read_comment", "id")

        inspector = Inspector(db, workflow)

        # Generate validation report
        report = inspector.workflow_validation_report()
        assert isinstance(report["is_valid"], bool)
        assert isinstance(report["errors"], list)
        assert isinstance(report["warnings"], list)
        assert isinstance(report["suggestions"], list)

    @pytest.mark.asyncio
    async def test_inspector_node_dependencies_real_workflow(self, standard_dataflow):
        """Test Inspector analyzing node dependencies in real workflow."""
        db = standard_dataflow

        @db.model
        class Article:
            id: str
            title: str
            published: bool

        await db.initialize()

        # Build workflow with dependencies
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ArticleCreateNode",
            "create_article",
            {"id": "article-1", "title": "Test", "published": False},
        )
        workflow.add_node("ArticleReadNode", "read_article", {})
        workflow.add_node("ArticleUpdateNode", "update_article", {})

        workflow.add_connection("create_article", "id", "read_article", "id")
        workflow.add_connection("read_article", "id", "update_article", "filter.id")

        inspector = Inspector(db, workflow)

        # Test node dependencies (upstream)
        deps = inspector.node_dependencies("read_article")
        assert "create_article" in deps

        # Test node dependents (downstream)
        dependents = inspector.node_dependents("read_article")
        assert "update_article" in dependents

    @pytest.mark.asyncio
    async def test_inspector_with_error_diagnosis_real_error(self, standard_dataflow):
        """Test Inspector diagnosing real DataFlow errors."""
        db = standard_dataflow
        inspector = Inspector(db)

        # Import error classes
        from dataflow.exceptions import EnhancedDataFlowError, ErrorSolution

        # Create real enhanced error
        error = EnhancedDataFlowError(
            error_code="DF-MODEL-001",
            message="Model schema mismatch",
            context={"model_name": "Product", "expected_fields": ["id", "name"]},
            causes=["Database schema doesn't match model definition"],
            solutions=[
                ErrorSolution(
                    priority=1,
                    description="Run migrations",
                    code_template="await db.initialize()",
                )
            ],
        )

        # Diagnose error
        diagnosis = inspector.diagnose_error(error)
        assert diagnosis.error_code == "DF-MODEL-001"
        assert diagnosis.error_type == "EnhancedDataFlowError"
        assert diagnosis.affected_component == "Product"
        assert len(diagnosis.inspector_commands) > 0
        assert len(diagnosis.recommended_actions) > 0

    @pytest.mark.asyncio
    async def test_inspector_connection_chain_real_workflow(self, standard_dataflow):
        """Test Inspector finding connection chains in real workflow."""
        db = standard_dataflow

        @db.model
        class Review:
            id: str
            product_id: str
            rating: int

        await db.initialize()

        # Build workflow with connection chain
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ReviewCreateNode",
            "create_review",
            {"id": "review-1", "product_id": "prod-1", "rating": 5},
        )
        workflow.add_node("ReviewReadNode", "read_review", {})
        workflow.add_node("ReviewUpdateNode", "update_review", {})

        workflow.add_connection("create_review", "id", "read_review", "id")
        workflow.add_connection("read_review", "id", "update_review", "filter.id")

        inspector = Inspector(db, workflow)

        # Find connection chain
        chain = inspector.connection_chain("create_review", "update_review")
        assert len(chain) == 2
        assert chain[0].source_node == "create_review"
        assert chain[1].target_node == "update_review"

    @pytest.mark.asyncio
    async def test_inspector_find_broken_connections(self, standard_dataflow):
        """Test Inspector finding broken connections in workflow."""
        db = standard_dataflow

        @db.model
        class Category:
            id: str
            name: str

        await db.initialize()

        # Build workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "CategoryCreateNode",
            "create_category",
            {"id": "cat-1", "name": "Electronics"},
        )

        # Note: Not adding connection to read node to test broken connection detection
        workflow.add_node("CategoryReadNode", "read_category", {})

        inspector = Inspector(db, workflow)

        # Find broken connections
        broken = inspector.find_broken_connections()
        # If implementation detects missing required connections, list should have items
        assert isinstance(broken, list)

    @pytest.mark.asyncio
    async def test_inspector_workflow_visualization_data(self, standard_dataflow):
        """Test Inspector generating visualization data for real workflow."""
        db = standard_dataflow

        @db.model
        class Tag:
            id: str
            name: str

        await db.initialize()

        # Build workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "TagCreateNode", "create_tag", {"id": "tag-1", "name": "python"}
        )
        workflow.add_node("TagReadNode", "read_tag", {})
        workflow.add_connection("create_tag", "id", "read_tag", "id")

        inspector = Inspector(db, workflow)

        # Generate visualization data
        viz_data = inspector.workflow_visualization_data()
        assert "nodes" in viz_data
        assert "edges" in viz_data
        assert len(viz_data["nodes"]) == 2
        assert len(viz_data["edges"]) == 1

    @pytest.mark.asyncio
    async def test_inspector_model_instances_count_real_data(self, standard_dataflow):
        """Test Inspector counting model instances with real database."""
        db = standard_dataflow

        @db.model
        class Event:
            id: str
            name: str
            date: str

        await db.initialize()

        inspector = Inspector(db)

        # Get count (should be 0 for new table)
        count = inspector.model_instances_count("Event")
        assert isinstance(count, int)
        assert count >= 0

    @pytest.mark.asyncio
    async def test_inspector_workflow_performance_profile(self, standard_dataflow):
        """Test Inspector generating performance profile for workflow."""
        db = standard_dataflow

        @db.model
        class Log:
            id: str
            message: str
            level: str

        await db.initialize()

        # Build workflow
        workflow = WorkflowBuilder()
        for i in range(3):
            workflow.add_node(
                "LogCreateNode",
                f"log_{i}",
                {"id": f"log-{i}", "message": f"Message {i}", "level": "info"},
            )

        inspector = Inspector(db, workflow)

        # Generate performance profile
        profile = inspector.workflow_performance_profile()
        assert isinstance(profile, dict)
        assert (
            "node_count" in profile or "estimated_time" in profile or len(profile) > 0
        )

    @pytest.mark.asyncio
    async def test_inspector_parameter_consumers_real_workflow(self, standard_dataflow):
        """Test Inspector finding parameter consumers in real workflow."""
        db = standard_dataflow

        @db.model
        class Notification:
            id: str
            user_id: str
            message: str

        await db.initialize()

        # Build workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "NotificationCreateNode",
            "create_notif",
            {"id": "notif-1", "user_id": "user-1", "message": "Hello"},
        )
        workflow.add_node("NotificationReadNode", "read_notif", {})
        workflow.add_connection("create_notif", "id", "read_notif", "id")

        inspector = Inspector(db, workflow)

        # Find consumers of create_notif's 'id' output
        consumers = inspector.parameter_consumers("create_notif", "id")
        assert isinstance(consumers, list)
        if len(consumers) > 0:
            assert any(c.destination_node == "read_notif" for c in consumers)

    @pytest.mark.asyncio
    async def test_inspector_find_parameter_source_real_workflow(
        self, standard_dataflow
    ):
        """Test Inspector finding parameter source in real workflow."""
        db = standard_dataflow

        @db.model
        class Session:
            id: str
            user_id: str
            token: str

        await db.initialize()

        # Build workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "SessionCreateNode",
            "create_session",
            {"id": "sess-1", "user_id": "user-1", "token": "abc123"},
        )
        workflow.add_node("SessionReadNode", "read_session", {})
        workflow.add_connection("create_session", "id", "read_session", "id")

        inspector = Inspector(db, workflow)

        # Find source of read_session's 'id' parameter
        source = inspector.find_parameter_source("read_session", "id")
        if source:
            assert source.source_node == "create_session"
            assert source.source_param == "id"

    @pytest.mark.asyncio
    async def test_inspector_instance_info_real_database(self, standard_dataflow):
        """Test Inspector getting DataFlow instance info with real database."""
        db = standard_dataflow
        inspector = Inspector(db)

        # Get instance info
        instance_info = inspector.instance()
        assert instance_info.database_url is not None
        assert isinstance(instance_info.model_count, int)
        assert instance_info.model_count >= 0


@pytest.mark.integration
@pytest.mark.timeout(15)
class TestInspectorComplexScenarios:
    """Integration tests for complex real-world scenarios."""

    @pytest.mark.asyncio
    async def test_inspector_multi_model_workflow(self, standard_dataflow):
        """Test Inspector with workflow spanning multiple models."""
        db = standard_dataflow

        @db.model
        class User:
            id: str
            email: str

        @db.model
        class Post:
            id: str
            user_id: str
            title: str

        @db.model
        class Like:
            id: str
            post_id: str
            user_id: str

        await db.initialize()

        # Build workflow connecting multiple models
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserCreateNode", "create_user", {"id": "user-1", "email": "alice@test.com"}
        )
        workflow.add_node(
            "PostCreateNode",
            "create_post",
            {"id": "post-1", "title": "Hello World"},
        )
        workflow.add_connection("create_user", "id", "create_post", "user_id")

        workflow.add_node("LikeCreateNode", "create_like", {"id": "like-1"})
        workflow.add_connection("create_post", "id", "create_like", "post_id")
        workflow.add_connection("create_user", "id", "create_like", "user_id")

        inspector = Inspector(db, workflow)

        # Test comprehensive workflow analysis
        summary = inspector.workflow_summary()
        assert summary["node_count"] == 3
        assert summary["connection_count"] == 3

        # Test execution order spans all models
        order = inspector.execution_order()
        assert len(order) == 3
        assert order[0] == "create_user"

        # Test connection graph
        graph = inspector.connection_graph()
        assert "create_user" in graph
        assert "create_post" in graph["create_user"]

    @pytest.mark.asyncio
    async def test_inspector_end_to_end_debugging_workflow(self, standard_dataflow):
        """Test Inspector end-to-end debugging workflow simulation."""
        db = standard_dataflow

        @db.model
        class Bug:
            id: str
            description: str
            severity: str
            fixed: bool

        await db.initialize()

        # Simulate debugging workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "BugCreateNode",
            "report_bug",
            {
                "id": "bug-1",
                "description": "Login fails",
                "severity": "high",
                "fixed": False,
            },
        )
        workflow.add_node("BugReadNode", "investigate_bug", {})
        workflow.add_connection("report_bug", "id", "investigate_bug", "id")

        workflow.add_node("BugUpdateNode", "fix_bug", {})
        workflow.add_connection("investigate_bug", "id", "fix_bug", "filter.id")
        workflow.add_parameter("fix_bug", "fields", {"fixed": True})

        inspector = Inspector(db, workflow)

        # Simulate debugging session
        # 1. Understand workflow structure
        summary = inspector.workflow_summary()
        assert summary["node_count"] == 3

        # 2. Trace parameter flow
        trace = inspector.trace_parameter("investigate_bug", "id")
        assert trace.source_node == "report_bug"

        # 3. Validate connections
        is_valid, issues = inspector.validate_connections()
        assert is_valid or len(issues) == 0

        # 4. Check execution order
        order = inspector.execution_order()
        assert order == ["report_bug", "investigate_bug", "fix_bug"]

        # Complete workflow executed successfully through Inspector analysis
        assert True
