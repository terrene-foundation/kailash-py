#!/usr/bin/env python3
"""
Comprehensive validation of kailash-dataflow CLAUDE.md guidance system.
Tests all patterns, user personas, and workflows to ensure zero failures.
"""

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Test results storage
test_results = {
    "basic_patterns": [],
    "user_personas": [],
    "navigation_paths": [],
    "errors": [],
    "summary": {},
}


def log_test(
    category: str, test_name: str, success: bool, details: str = "", error: str = ""
):
    """Log test result"""
    result = {
        "test_name": test_name,
        "success": success,
        "details": details,
        "error": error,
        "timestamp": datetime.now().isoformat(),
    }
    test_results[category].append(result)

    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status} {test_name}")
    if details:
        print(f"   Details: {details}")
    if error:
        print(f"   Error: {error}")


def test_basic_pattern():
    """Test the basic pattern (foundation) from CLAUDE.md"""
    try:
        # Test 1: Basic DataFlow initialization
        from kailash_dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Initialize DataFlow
        db = DataFlow()
        log_test(
            "basic_patterns",
            "DataFlow initialization",
            True,
            "Zero config SQLite created",
        )

        # Test 2: Model definition
        @db.model
        class User:
            name: str
            email: str
            active: bool = True

        log_test(
            "basic_patterns",
            "Model definition",
            True,
            "User model with type hints created",
        )

        # Test 3: Workflow creation
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserCreateNode",
            "create_user",
            {"name": "Alice", "email": "alice@example.com"},
        )

        log_test(
            "basic_patterns",
            "Workflow creation",
            True,
            "UserCreateNode added successfully",
        )

        # Test 4: Execution
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        log_test(
            "basic_patterns",
            "Workflow execution",
            True,
            f"Executed with run_id: {run_id}",
        )

        # Test 5: Verify results
        if "create_user" in results and "data" in results["create_user"]:
            user_data = results["create_user"]["data"]
            if (
                user_data["name"] == "Alice"
                and user_data["email"] == "alice@example.com"
            ):
                log_test(
                    "basic_patterns",
                    "Result validation",
                    True,
                    "User created with correct data",
                )
            else:
                log_test(
                    "basic_patterns",
                    "Result validation",
                    False,
                    "",
                    f"Unexpected data: {user_data}",
                )
        else:
            log_test(
                "basic_patterns",
                "Result validation",
                False,
                "",
                f"Results structure unexpected: {results}",
            )

    except Exception as e:
        log_test("basic_patterns", "Basic pattern execution", False, "", str(e))
        test_results["errors"].append(f"Basic pattern: {str(e)}")


def test_production_pattern():
    """Test production pattern (database connection)"""
    try:
        from kailash_dataflow import DataFlow

        # Test 1: Environment variable method (simulate)
        os.environ["DATABASE_URL"] = "sqlite:///test_prod.db"
        db1 = DataFlow()
        log_test(
            "basic_patterns",
            "Environment variable config",
            True,
            "DataFlow with DATABASE_URL",
        )

        # Test 2: Direct configuration
        db2 = DataFlow(database_url="sqlite:///test_direct.db", pool_size=20)
        log_test(
            "basic_patterns",
            "Direct configuration",
            True,
            "DataFlow with direct config",
        )

        # Clean up
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]

    except Exception as e:
        log_test("basic_patterns", "Production pattern", False, "", str(e))
        test_results["errors"].append(f"Production pattern: {str(e)}")


def test_generated_nodes():
    """Test generated nodes (automatic)"""
    try:
        from kailash_dataflow import DataFlow

        db = DataFlow()

        @db.model
        class Product:
            name: str
            price: float

        # Test that model registration worked
        if hasattr(db, "models") and "Product" in [m.__name__ for m in db.models]:
            log_test(
                "basic_patterns", "Model registration", True, "Product model registered"
            )
        else:
            log_test(
                "basic_patterns",
                "Model registration",
                False,
                "",
                "Product model not found in db.models",
            )

        # Test node generation (check if they exist in workflow context)
        from kailash.workflow.builder import WorkflowBuilder

        workflow = WorkflowBuilder()

        # Test basic CRUD nodes
        crud_nodes = [
            "ProductCreateNode",
            "ProductReadNode",
            "ProductUpdateNode",
            "ProductDeleteNode",
            "ProductListNode",
        ]

        for node_name in crud_nodes:
            try:
                workflow.add_node(
                    node_name,
                    f"test_{node_name.lower()}",
                    {"name": "Test Product", "price": 99.99},
                )
                log_test(
                    "basic_patterns",
                    f"Generated {node_name}",
                    True,
                    f"{node_name} available",
                )
            except Exception as e:
                log_test("basic_patterns", f"Generated {node_name}", False, "", str(e))

        # Test bulk nodes
        bulk_nodes = [
            "ProductBulkCreateNode",
            "ProductBulkUpdateNode",
            "ProductBulkDeleteNode",
        ]

        for node_name in bulk_nodes:
            try:
                workflow.add_node(
                    node_name,
                    f"test_{node_name.lower()}",
                    {"data": [{"name": "Bulk Product", "price": 50.00}]},
                )
                log_test(
                    "basic_patterns",
                    f"Generated {node_name}",
                    True,
                    f"{node_name} available",
                )
            except Exception as e:
                log_test("basic_patterns", f"Generated {node_name}", False, "", str(e))

    except Exception as e:
        log_test("basic_patterns", "Generated nodes test", False, "", str(e))
        test_results["errors"].append(f"Generated nodes: {str(e)}")


def test_model_definition_patterns():
    """Test model definition critical patterns"""
    try:
        from datetime import datetime

        from kailash_dataflow import DataFlow

        db = DataFlow()

        # Test advanced model with DataFlow features
        @db.model
        class Order:
            customer_id: int
            total: float
            status: str = "pending"
            created_at: datetime

            __dataflow__ = {
                "soft_delete": True,
                "multi_tenant": True,
                "versioned": True,
            }

            __indexes__ = [{"name": "idx_status", "fields": ["status", "created_at"]}]

        log_test(
            "basic_patterns",
            "Advanced model definition",
            True,
            "Order model with DataFlow features",
        )

        # Test that model is registered
        if hasattr(db, "models") and "Order" in [m.__name__ for m in db.models]:
            log_test(
                "basic_patterns",
                "Advanced model registration",
                True,
                "Order model registered with features",
            )
        else:
            log_test(
                "basic_patterns",
                "Advanced model registration",
                False,
                "",
                "Order model not registered",
            )

    except Exception as e:
        log_test("basic_patterns", "Model definition patterns", False, "", str(e))
        test_results["errors"].append(f"Model definition: {str(e)}")


def test_workflow_integration():
    """Test workflow integration patterns"""
    try:
        from kailash_dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow()

        @db.model
        class Order:
            customer_id: int
            total: float

        @db.model
        class OrderItem:
            order_id: int
            product_id: int
            quantity: int
            price: float

        # Test workflow with connections
        workflow = WorkflowBuilder()

        workflow.add_node(
            "OrderCreateNode", "create_order", {"customer_id": 123, "total": 250.00}
        )

        workflow.add_node(
            "OrderItemBulkCreateNode",
            "add_items",
            {
                "data": [
                    {"product_id": 1, "quantity": 2, "price": 100.00},
                    {"product_id": 2, "quantity": 1, "price": 50.00},
                ]
            },
        )

        workflow.add_connection("create_order", "add_items", "id", "order_id")

        log_test(
            "basic_patterns",
            "Workflow integration setup",
            True,
            "Order workflow with connections",
        )

        # Test execution
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        log_test(
            "basic_patterns",
            "Workflow integration execution",
            True,
            f"Connected workflow executed: {run_id}",
        )

    except Exception as e:
        log_test("basic_patterns", "Workflow integration", False, "", str(e))
        test_results["errors"].append(f"Workflow integration: {str(e)}")


def test_bulk_operations():
    """Test bulk operations patterns"""
    try:
        from kailash_dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow()

        @db.model
        class Product:
            name: str
            price: float
            category: str

        workflow = WorkflowBuilder()

        # Test bulk create
        product_data = [
            {"name": f"Product {i}", "price": i * 10.0, "category": "electronics"}
            for i in range(1, 101)  # 100 products
        ]

        workflow.add_node(
            "ProductBulkCreateNode",
            "import_products",
            {"data": product_data, "batch_size": 1000, "conflict_resolution": "skip"},
        )

        log_test(
            "basic_patterns", "Bulk create setup", True, "100 products for bulk insert"
        )

        # Test bulk update
        workflow.add_node(
            "ProductBulkUpdateNode",
            "update_prices",
            {"filter": {"category": "electronics"}, "update": {"price": "price * 0.9"}},
        )

        workflow.add_connection("import_products", "update_prices")

        log_test(
            "basic_patterns",
            "Bulk update setup",
            True,
            "Bulk update with filter and expression",
        )

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        log_test(
            "basic_patterns",
            "Bulk operations execution",
            True,
            f"Bulk workflow executed: {run_id}",
        )

    except Exception as e:
        log_test("basic_patterns", "Bulk operations", False, "", str(e))
        test_results["errors"].append(f"Bulk operations: {str(e)}")


def test_user_persona_level_1():
    """Test Level 1 user persona (new to frameworks) E2E workflow"""
    try:
        print("\n=== Testing Level 1 User Persona (New to Frameworks) ===")

        # Step 1: Copy basic pattern
        from kailash_dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow()

        @db.model
        class Task:
            title: str
            description: str
            completed: bool = False

        log_test(
            "user_personas", "Level 1 - Basic pattern copy", True, "Task model created"
        )

        # Step 2: Create simple workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "TaskCreateNode",
            "create_task",
            {"title": "Learn DataFlow", "description": "Complete the quickstart guide"},
        )

        workflow.add_node(
            "TaskListNode", "list_tasks", {"filter": {"completed": False}}
        )

        workflow.add_connection("create_task", "list_tasks")

        log_test(
            "user_personas",
            "Level 1 - Simple workflow",
            True,
            "Task creation and listing",
        )

        # Step 3: Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Step 4: Verify results
        if "create_task" in results and "list_tasks" in results:
            task_data = results["create_task"]["data"]
            tasks_list = results["list_tasks"]["data"]

            if task_data["title"] == "Learn DataFlow" and len(tasks_list) >= 1:
                log_test(
                    "user_personas",
                    "Level 1 - E2E workflow",
                    True,
                    "Complete workflow successful",
                )
            else:
                log_test(
                    "user_personas",
                    "Level 1 - E2E workflow",
                    False,
                    "",
                    f"Unexpected results: {results}",
                )
        else:
            log_test(
                "user_personas",
                "Level 1 - E2E workflow",
                False,
                "",
                f"Missing results: {results}",
            )

    except Exception as e:
        log_test("user_personas", "Level 1 - E2E workflow", False, "", str(e))
        test_results["errors"].append(f"Level 1 persona: {str(e)}")


def test_user_persona_level_2():
    """Test Level 2 user persona (Django/Rails background) E2E workflow"""
    try:
        print("\n=== Testing Level 2 User Persona (Django/Rails Background) ===")

        from kailash_dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        db = DataFlow()

        # Django-like model definition
        @db.model
        class User:
            username: str
            email: str
            is_active: bool = True

        @db.model
        class Post:
            title: str
            content: str
            author_id: int
            published: bool = False

        log_test(
            "user_personas",
            "Level 2 - Django-like models",
            True,
            "User and Post models",
        )

        # Django-like workflow (create user, then posts)
        workflow = WorkflowBuilder()

        workflow.add_node(
            "UserCreateNode",
            "create_user",
            {"username": "john_doe", "email": "john@example.com"},
        )

        workflow.add_node(
            "PostCreateNode",
            "create_post",
            {
                "title": "My First Post",
                "content": "This is my first post using DataFlow",
                "author_id": ":user_id",
            },
        )

        workflow.add_node(
            "PostListNode",
            "list_posts",
            {"filter": {"author_id": ":user_id", "published": False}},
        )

        workflow.add_connection("create_user", "create_post", "id", "user_id")
        workflow.add_connection("create_user", "list_posts", "id", "user_id")

        log_test(
            "user_personas",
            "Level 2 - Django-like workflow",
            True,
            "User->Post relationship workflow",
        )

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify results
        if all(key in results for key in ["create_user", "create_post", "list_posts"]):
            log_test(
                "user_personas",
                "Level 2 - E2E workflow",
                True,
                "Django-style workflow completed",
            )
        else:
            log_test(
                "user_personas",
                "Level 2 - E2E workflow",
                False,
                "",
                f"Missing results: {results}",
            )

    except Exception as e:
        log_test("user_personas", "Level 2 - E2E workflow", False, "", str(e))
        test_results["errors"].append(f"Level 2 persona: {str(e)}")


def test_user_persona_level_3():
    """Test Level 3 user persona (performance/scale) E2E workflow"""
    try:
        print("\n=== Testing Level 3 User Persona (Performance/Scale) ===")

        from kailash_dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Performance-optimized configuration
        db = DataFlow(pool_size=10, echo=False)  # Smaller for testing  # No SQL logging

        @db.model
        class Product:
            name: str
            price: float
            category: str
            stock: int

        log_test(
            "user_personas",
            "Level 3 - Performance config",
            True,
            "Optimized DataFlow config",
        )

        # High-performance bulk operations
        workflow = WorkflowBuilder()

        # Bulk create 1000 products
        product_data = [
            {
                "name": f"Product {i}",
                "price": i * 10.0,
                "category": "electronics" if i % 2 == 0 else "clothing",
                "stock": 100,
            }
            for i in range(1, 1001)
        ]

        workflow.add_node(
            "ProductBulkCreateNode",
            "import_products",
            {"data": product_data, "batch_size": 100, "conflict_resolution": "skip"},
        )

        # Bulk update prices
        workflow.add_node(
            "ProductBulkUpdateNode",
            "update_electronics_prices",
            {"filter": {"category": "electronics"}, "update": {"price": "price * 0.8"}},
        )

        # Bulk update stock
        workflow.add_node(
            "ProductBulkUpdateNode",
            "update_low_stock",
            {"filter": {"stock": {"$lt": 50}}, "update": {"stock": 200}},
        )

        workflow.add_connection("import_products", "update_electronics_prices")
        workflow.add_connection("update_electronics_prices", "update_low_stock")

        log_test(
            "user_personas",
            "Level 3 - Bulk operations workflow",
            True,
            "1000 products bulk workflow",
        )

        # Execute with performance measurement
        import time

        start_time = time.time()

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        execution_time = time.time() - start_time

        if "import_products" in results and "update_electronics_prices" in results:
            log_test(
                "user_personas",
                "Level 3 - E2E workflow",
                True,
                f"Performance workflow completed in {execution_time:.2f}s",
            )
        else:
            log_test(
                "user_personas",
                "Level 3 - E2E workflow",
                False,
                "",
                f"Missing results: {results}",
            )

    except Exception as e:
        log_test("user_personas", "Level 3 - E2E workflow", False, "", str(e))
        test_results["errors"].append(f"Level 3 persona: {str(e)}")


def test_user_persona_level_4():
    """Test Level 4 user persona (production/enterprise) E2E workflow"""
    try:
        print("\n=== Testing Level 4 User Persona (Production/Enterprise) ===")

        from kailash_dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Production-ready configuration
        db = DataFlow(
            database_url="sqlite:///enterprise_test.db",
            pool_size=20,
            pool_recycle=3600,
            monitoring=True,
            multi_tenant=True,
            echo=False,
        )

        @db.model
        class Customer:
            name: str
            email: str
            tenant_id: int

            __dataflow__ = {
                "soft_delete": True,
                "multi_tenant": True,
                "versioned": True,
            }

            __indexes__ = [
                {
                    "name": "idx_tenant_email",
                    "fields": ["tenant_id", "email"],
                    "unique": True,
                }
            ]

        @db.model
        class Order:
            customer_id: int
            total: float
            status: str = "pending"
            tenant_id: int

            __dataflow__ = {
                "soft_delete": True,
                "multi_tenant": True,
                "versioned": True,
            }

        log_test(
            "user_personas",
            "Level 4 - Enterprise config",
            True,
            "Production DataFlow with multi-tenancy",
        )

        # Enterprise workflow with transaction safety
        workflow = WorkflowBuilder()

        # Create customer
        workflow.add_node(
            "CustomerCreateNode",
            "create_customer",
            {
                "name": "Enterprise Corp",
                "email": "orders@enterprise.com",
                "tenant_id": 1,
            },
        )

        # Create order
        workflow.add_node(
            "OrderCreateNode",
            "create_order",
            {"customer_id": ":customer_id", "total": 5000.00, "tenant_id": 1},
        )

        # Update order status
        workflow.add_node(
            "OrderUpdateNode",
            "confirm_order",
            {"id": ":order_id", "status": "confirmed"},
        )

        workflow.add_connection("create_customer", "create_order", "id", "customer_id")
        workflow.add_connection("create_order", "confirm_order", "id", "order_id")

        log_test(
            "user_personas",
            "Level 4 - Enterprise workflow",
            True,
            "Multi-tenant enterprise workflow",
        )

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        if all(
            key in results
            for key in ["create_customer", "create_order", "confirm_order"]
        ):
            order_data = results["confirm_order"]["data"]
            if order_data["status"] == "confirmed":
                log_test(
                    "user_personas",
                    "Level 4 - E2E workflow",
                    True,
                    "Enterprise workflow completed",
                )
            else:
                log_test(
                    "user_personas",
                    "Level 4 - E2E workflow",
                    False,
                    "",
                    f"Order status: {order_data['status']}",
                )
        else:
            log_test(
                "user_personas",
                "Level 4 - E2E workflow",
                False,
                "",
                f"Missing results: {results}",
            )

    except Exception as e:
        log_test("user_personas", "Level 4 - E2E workflow", False, "", str(e))
        test_results["errors"].append(f"Level 4 persona: {str(e)}")


def test_user_persona_level_5():
    """Test Level 5 user persona (custom development) E2E workflow"""
    try:
        print("\n=== Testing Level 5 User Persona (Custom Development) ===")

        from kailash_dataflow import DataFlow

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Advanced configuration
        db = DataFlow(
            database_url="sqlite:///custom_test.db",
            pool_size=30,
            pool_max_overflow=50,
            pool_recycle=3600,
            monitoring=True,
            echo=False,
        )

        @db.model
        class Analytics:
            event_type: str
            user_id: int
            timestamp: str
            data: str  # JSON string

            __indexes__ = [
                {"name": "idx_event_timestamp", "fields": ["event_type", "timestamp"]},
                {"name": "idx_user_events", "fields": ["user_id", "timestamp"]},
            ]

        log_test(
            "user_personas",
            "Level 5 - Custom config",
            True,
            "Advanced DataFlow configuration",
        )

        # Custom high-performance analytics workflow
        workflow = WorkflowBuilder()

        # Generate large analytics dataset
        analytics_data = [
            {
                "event_type": "page_view" if i % 3 == 0 else "click",
                "user_id": i % 100,  # 100 users
                "timestamp": f"2024-01-{(i % 30) + 1:02d}T{(i % 24):02d}:00:00",
                "data": f'{{"page": "page_{i}", "duration": {i * 10}}}',
            }
            for i in range(1, 5001)  # 5000 events
        ]

        workflow.add_node(
            "AnalyticsBulkCreateNode",
            "import_analytics",
            {"data": analytics_data, "batch_size": 500, "conflict_resolution": "skip"},
        )

        # Custom aggregation queries
        workflow.add_node(
            "AnalyticsListNode",
            "get_page_views",
            {"filter": {"event_type": "page_view"}, "limit": 1000},
        )

        workflow.add_node(
            "AnalyticsListNode",
            "get_user_activity",
            {"filter": {"user_id": 42}, "order_by": ["timestamp"]},
        )

        workflow.add_connection("import_analytics", "get_page_views")
        workflow.add_connection("import_analytics", "get_user_activity")

        log_test(
            "user_personas",
            "Level 5 - Custom workflow",
            True,
            "5000 analytics events workflow",
        )

        # Execute with performance tracking
        import time

        start_time = time.time()

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        execution_time = time.time() - start_time

        if all(
            key in results
            for key in ["import_analytics", "get_page_views", "get_user_activity"]
        ):
            page_views = results["get_page_views"]["data"]
            user_activity = results["get_user_activity"]["data"]

            if len(page_views) > 0 and len(user_activity) > 0:
                log_test(
                    "user_personas",
                    "Level 5 - E2E workflow",
                    True,
                    f"Custom analytics workflow completed in {execution_time:.2f}s",
                )
            else:
                log_test(
                    "user_personas",
                    "Level 5 - E2E workflow",
                    False,
                    "",
                    f"Empty results: page_views={len(page_views)}, user_activity={len(user_activity)}",
                )
        else:
            log_test(
                "user_personas",
                "Level 5 - E2E workflow",
                False,
                "",
                f"Missing results: {results}",
            )

    except Exception as e:
        log_test("user_personas", "Level 5 - E2E workflow", False, "", str(e))
        test_results["errors"].append(f"Level 5 persona: {str(e)}")


def test_navigation_paths():
    """Test that all navigation paths and file references exist"""
    try:
        dataflow_dir = Path(__file__).parent / "apps" / "kailash-dataflow"

        # Test START HERE paths
        start_paths = [
            "docs/getting-started/quickstart.md",
            "docs/getting-started/concepts.md",
        ]

        for path in start_paths:
            full_path = dataflow_dir / path
            if full_path.exists():
                log_test("navigation_paths", f"START HERE: {path}", True, "File exists")
            else:
                log_test(
                    "navigation_paths",
                    f"START HERE: {path}",
                    False,
                    "",
                    f"File not found: {full_path}",
                )

        # Test IMPLEMENTATION PATH
        impl_paths = [
            "docs/development/models.md",
            "docs/development/crud.md",
            "docs/workflows/nodes.md",
            "docs/development/bulk-operations.md",
            "docs/production/deployment.md",
        ]

        for path in impl_paths:
            full_path = dataflow_dir / path
            if full_path.exists():
                log_test(
                    "navigation_paths", f"IMPLEMENTATION: {path}", True, "File exists"
                )
            else:
                log_test(
                    "navigation_paths",
                    f"IMPLEMENTATION: {path}",
                    False,
                    "",
                    f"File not found: {full_path}",
                )

        # Test BY EXPERIENCE LEVEL paths
        exp_paths = [
            "docs/USER_GUIDE.md",
            "docs/comparisons/FRAMEWORK_COMPARISON.md",
            "docs/advanced/",
        ]

        for path in exp_paths:
            full_path = dataflow_dir / path
            if full_path.exists():
                log_test(
                    "navigation_paths", f"EXPERIENCE: {path}", True, "File/dir exists"
                )
            else:
                log_test(
                    "navigation_paths",
                    f"EXPERIENCE: {path}",
                    False,
                    "",
                    f"File/dir not found: {full_path}",
                )

        # Test examples directory
        examples_dir = dataflow_dir / "examples"
        if examples_dir.exists():
            log_test(
                "navigation_paths",
                "examples directory",
                True,
                "Examples directory exists",
            )
        else:
            log_test(
                "navigation_paths",
                "examples directory",
                False,
                "",
                "Examples directory not found",
            )

    except Exception as e:
        log_test("navigation_paths", "Navigation paths test", False, "", str(e))
        test_results["errors"].append(f"Navigation paths: {str(e)}")


def generate_report():
    """Generate comprehensive validation report"""
    print("\n" + "=" * 80)
    print("KAILASH DATAFLOW CLAUDE.MD VALIDATION REPORT")
    print("=" * 80)

    # Summary statistics
    total_tests = sum(
        len(results) for results in test_results.values() if isinstance(results, list)
    )
    passed_tests = sum(
        1
        for results in test_results.values()
        if isinstance(results, list)
        for result in results
        if result["success"]
    )
    failed_tests = total_tests - passed_tests

    print("\nSUMMARY:")
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests} (✅)")
    print(f"Failed: {failed_tests} (❌)")
    print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")

    # Detailed results by category
    categories = ["basic_patterns", "user_personas", "navigation_paths"]

    for category in categories:
        results = test_results[category]
        if results:
            passed = sum(1 for r in results if r["success"])
            total = len(results)
            print(f"\n{category.upper().replace('_', ' ')}: {passed}/{total} passed")

            for result in results:
                status = "✅" if result["success"] else "❌"
                print(f"  {status} {result['test_name']}")
                if result["error"]:
                    print(f"    Error: {result['error']}")

    # Error summary
    if test_results["errors"]:
        print("\nERRORS ENCOUNTERED:")
        for error in test_results["errors"]:
            print(f"  - {error}")

    # Recommendations
    print("\nRECOMMENDATIONS:")
    if failed_tests == 0:
        print("  ✅ All tests passed! CLAUDE.md is fully validated.")
    else:
        print(f"  ❌ {failed_tests} tests failed. Review errors above.")
        print("  - Check import paths and dependencies")
        print("  - Verify file structure matches documentation")
        print("  - Test in clean environment")

    print("\n" + "=" * 80)


def main():
    """Run all validation tests"""
    print("Starting comprehensive validation of kailash-dataflow CLAUDE.md...")
    print("Testing all patterns, user personas, and navigation paths...")

    # Test basic patterns
    print("\n=== Testing Basic Patterns ===")
    test_basic_pattern()
    test_production_pattern()
    test_generated_nodes()
    test_model_definition_patterns()
    test_workflow_integration()
    test_bulk_operations()

    # Test user personas
    print("\n=== Testing User Personas ===")
    test_user_persona_level_1()
    test_user_persona_level_2()
    test_user_persona_level_3()
    test_user_persona_level_4()
    test_user_persona_level_5()

    # Test navigation paths
    print("\n=== Testing Navigation Paths ===")
    test_navigation_paths()

    # Generate report
    generate_report()

    return test_results


if __name__ == "__main__":
    results = main()
