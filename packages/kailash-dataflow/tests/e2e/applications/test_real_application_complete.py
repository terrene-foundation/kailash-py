"""
E2E tests for real application building scenarios using ONLY DataFlow components.

Tests complete application workflows to ensure DataFlow can power
production applications WITHOUT using psql or ANY raw SQL commands.

This demonstrates the proper way to test DataFlow applications.
"""

import asyncio
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytest
from dataflow import DataFlow
from dataflow.testing.dataflow_test_utils import DataFlowTestUtils

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.e2e
@pytest.mark.requires_postgres
class TestECommerceApplicationComplete:
    """Test complete e-commerce application using ONLY DataFlow components."""

    @pytest.fixture
    def db_url(self):
        """Real PostgreSQL database URL."""
        return os.getenv(
            "DATABASE_URL",
            "postgresql://test_user:test_password@localhost:5434/kailash_test",
        )

    @pytest.fixture
    def test_utils(self, db_url):
        """DataFlow test utilities for proper database operations."""
        return DataFlowTestUtils(db_url)

    @pytest.fixture
    def ecommerce_db(self, db_url, test_utils):
        """Setup e-commerce DataFlow models with proper cleanup."""
        # Clean database using DataFlow utilities
        test_utils.cleanup_database()

        # Create DataFlow instance
        db = DataFlow(
            database_url=db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 5)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 10)),
        )

        # Define e-commerce models
        @db.model
        class Customer:
            name: str
            email: str
            phone: Optional[str] = None
            address: Optional[str] = None
            created_at: Optional[datetime] = None

        @db.model
        class Product:
            name: str
            description: str
            price: float
            stock_quantity: int = 0
            category: str = "general"
            sku: Optional[str] = None

        @db.model
        class Cart:
            customer_id: int
            status: str = "active"
            created_at: Optional[datetime] = None

        @db.model
        class CartItem:
            cart_id: int
            product_id: int
            quantity: int = 1
            added_at: Optional[datetime] = None

        @db.model
        class Order:
            customer_id: int
            total_amount: float
            status: str = "pending"
            payment_method: Optional[str] = None
            shipping_address: Optional[str] = None
            created_at: Optional[datetime] = None

        @db.model
        class OrderItem:
            order_id: int
            product_id: int
            quantity: int
            unit_price: float

        @db.model
        class Inventory:
            product_id: int
            warehouse_id: int = 1
            quantity_available: int = 0
            quantity_reserved: int = 0
            last_updated: Optional[datetime] = None

        # Create tables using DataFlow
        db.create_tables()

        yield db

        # Cleanup using DataFlow utilities
        test_utils.cleanup_database()

    def test_complete_ecommerce_order_flow_no_sql(self, ecommerce_db, test_utils):
        """Test complete e-commerce order flow using ONLY DataFlow components."""
        runtime = LocalRuntime()

        # Phase 1: Customer Registration using DataFlow
        customer_workflow = WorkflowBuilder()

        customer_workflow.add_node(
            "CustomerCreateNode",
            "create_customer",
            {
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "+1234567890",
                "address": "123 Main St, City, 12345",
            },
        )

        results, _ = runtime.execute(customer_workflow.build())
        customer_id = results["create_customer"]["id"]
        assert customer_id is not None

        # Phase 2: Product Catalog Setup using DataFlow bulk operations
        products = [
            {
                "name": "Laptop Pro",
                "description": "High-performance laptop with latest specs",
                "price": 1299.99,
                "stock_quantity": 50,
                "category": "electronics",
                "sku": "LAP-001",
            },
            {
                "name": "Wireless Mouse",
                "description": "Ergonomic wireless mouse with precision tracking",
                "price": 49.99,
                "stock_quantity": 200,
                "category": "accessories",
                "sku": "MOU-001",
            },
            {
                "name": "USB-C Hub",
                "description": "7-in-1 USB-C hub with 4K HDMI",
                "price": 79.99,
                "stock_quantity": 150,
                "category": "accessories",
                "sku": "HUB-001",
            },
            {
                "name": "Laptop Bag",
                "description": "Premium laptop bag with extra compartments",
                "price": 89.99,
                "stock_quantity": 100,
                "category": "accessories",
                "sku": "BAG-001",
            },
        ]

        # Bulk insert products using DataFlow
        bulk_result = test_utils.bulk_insert_test_data("Product", products)
        assert bulk_result["processed"] == 4

        # Query products to get IDs using DataFlow
        all_products = test_utils.query_data("Product", limit=10)
        assert len(all_products) == 4

        laptop_id = next(p["id"] for p in all_products if p["name"] == "Laptop Pro")
        mouse_id = next(p["id"] for p in all_products if p["name"] == "Wireless Mouse")
        hub_id = next(p["id"] for p in all_products if p["name"] == "USB-C Hub")

        # Phase 3: Initialize Inventory using DataFlow
        inventory_workflow = WorkflowBuilder()

        for product in all_products:
            inventory_workflow.add_node(
                "InventoryCreateNode",
                f"init_inv_{product['id']}",
                {
                    "product_id": product["id"],
                    "warehouse_id": 1,
                    "quantity_available": product["stock_quantity"],
                    "quantity_reserved": 0,
                },
            )

        # Connect inventory nodes
        for i in range(1, len(all_products)):
            inventory_workflow.add_connection(
                f"init_inv_{all_products[i-1]['id']}",
                f"init_inv_{all_products[i]['id']}",
            )

        runtime.execute(inventory_workflow.build())

        # Phase 4: Shopping Cart Management using DataFlow
        cart_workflow = WorkflowBuilder()

        # Create cart
        cart_workflow.add_node(
            "CartCreateNode",
            "create_cart",
            {"customer_id": customer_id, "status": "active"},
        )

        # Add items to cart
        cart_workflow.add_node(
            "CartItemCreateNode",
            "add_laptop",
            {"cart_id": "${create_cart.id}", "product_id": laptop_id, "quantity": 1},
        )

        cart_workflow.add_node(
            "CartItemCreateNode",
            "add_mouse",
            {"cart_id": "${create_cart.id}", "product_id": mouse_id, "quantity": 2},
        )

        cart_workflow.add_node(
            "CartItemCreateNode",
            "add_hub",
            {"cart_id": "${create_cart.id}", "product_id": hub_id, "quantity": 1},
        )

        # List cart items
        cart_workflow.add_node(
            "CartItemListNode",
            "list_cart_items",
            {"filter": {"cart_id": "${create_cart.id}"}, "limit": 10},
        )

        # Connect cart workflow
        cart_workflow.add_connection("create_cart", "add_laptop")
        cart_workflow.add_connection("add_laptop", "add_mouse")
        cart_workflow.add_connection("add_mouse", "add_hub")
        cart_workflow.add_connection("add_hub", "list_cart_items")

        cart_results, _ = runtime.execute(cart_workflow.build())
        cart_id = cart_results["create_cart"]["id"]
        cart_items = cart_results["list_cart_items"]["records"]
        assert len(cart_items) == 3

        # Phase 5: Checkout Process with Inventory Management
        checkout_operations = []

        # Calculate total
        total_amount = 0
        for item in cart_items:
            product = next(p for p in all_products if p["id"] == item["product_id"])
            total_amount += product["price"] * item["quantity"]

        # Create order operation
        checkout_operations.append(
            {
                "node_type": "OrderCreateNode",
                "parameters": {
                    "customer_id": customer_id,
                    "total_amount": total_amount,
                    "status": "pending",
                    "payment_method": "credit_card",
                    "shipping_address": "123 Main St, City, 12345",
                },
            }
        )

        # Execute checkout in transaction using DataFlow
        checkout_results = test_utils.execute_transaction(checkout_operations)
        order_id = checkout_results["op_0"]["id"]

        # Phase 6: Create order items and update inventory
        order_items_workflow = WorkflowBuilder()

        # Create order items
        for idx, item in enumerate(cart_items):
            product = next(p for p in all_products if p["id"] == item["product_id"])

            # Create order item
            order_items_workflow.add_node(
                "OrderItemCreateNode",
                f"order_item_{idx}",
                {
                    "order_id": order_id,
                    "product_id": item["product_id"],
                    "quantity": item["quantity"],
                    "unit_price": product["price"],
                },
            )

            # Reserve inventory
            order_items_workflow.add_node(
                "InventoryUpdateNode",
                f"reserve_inv_{idx}",
                {
                    "id": "${get_inv_" + str(idx) + ".records[0].id}",
                    "quantity_available": "${get_inv_"
                    + str(idx)
                    + ".records[0].quantity_available} - "
                    + str(item["quantity"]),
                    "quantity_reserved": "${get_inv_"
                    + str(idx)
                    + ".records[0].quantity_reserved} + "
                    + str(item["quantity"]),
                },
            )

            # Get inventory record first
            order_items_workflow.add_node(
                "InventoryListNode",
                f"get_inv_{idx}",
                {"filter": {"product_id": item["product_id"]}, "limit": 1},
            )

            if idx == 0:
                order_items_workflow.add_connection(
                    f"get_inv_{idx}", f"order_item_{idx}"
                )
            else:
                order_items_workflow.add_connection(
                    f"reserve_inv_{idx-1}", f"get_inv_{idx}"
                )
                order_items_workflow.add_connection(
                    f"get_inv_{idx}", f"order_item_{idx}"
                )

            order_items_workflow.add_connection(
                f"order_item_{idx}", f"reserve_inv_{idx}"
            )

        # Update cart status
        last_idx = len(cart_items) - 1
        order_items_workflow.add_node(
            "CartUpdateNode", "close_cart", {"id": cart_id, "status": "checked_out"}
        )
        order_items_workflow.add_connection(f"reserve_inv_{last_idx}", "close_cart")

        # Execute order items workflow
        runtime.execute(order_items_workflow.build())

        # Phase 7: Order Processing and Fulfillment
        processing_workflow = WorkflowBuilder()

        # Process payment
        processing_workflow.add_node(
            "OrderUpdateNode",
            "process_payment",
            {"id": order_id, "status": "payment_confirmed"},
        )

        # Prepare shipment
        processing_workflow.add_node(
            "OrderUpdateNode",
            "prepare_shipment",
            {"id": order_id, "status": "preparing_shipment"},
        )

        # Ship order
        processing_workflow.add_node(
            "OrderUpdateNode", "ship_order", {"id": order_id, "status": "shipped"}
        )

        # Update inventory (move from reserved to shipped)
        for idx, item in enumerate(cart_items):
            processing_workflow.add_node(
                "InventoryListNode",
                f"get_ship_inv_{idx}",
                {"filter": {"product_id": item["product_id"]}, "limit": 1},
            )

            processing_workflow.add_node(
                "InventoryUpdateNode",
                f"ship_inv_{idx}",
                {
                    "id": "${get_ship_inv_" + str(idx) + ".records[0].id}",
                    "quantity_reserved": "${get_ship_inv_"
                    + str(idx)
                    + ".records[0].quantity_reserved} - "
                    + str(item["quantity"]),
                },
            )

        # Connect processing workflow
        processing_workflow.add_connection("process_payment", "prepare_shipment")
        processing_workflow.add_connection("prepare_shipment", "ship_order")

        prev_node = "ship_order"
        for idx in range(len(cart_items)):
            processing_workflow.add_connection(prev_node, f"get_ship_inv_{idx}")
            processing_workflow.add_connection(f"get_ship_inv_{idx}", f"ship_inv_{idx}")
            prev_node = f"ship_inv_{idx}"

        # Execute processing
        runtime.execute(processing_workflow.build())

        # Phase 8: Verify Final State using DataFlow queries
        verification_workflow = WorkflowBuilder()

        # Verify order status
        verification_workflow.add_node(
            "OrderReadNode", "verify_order", {"id": order_id}
        )

        # Verify inventory levels
        verification_workflow.add_node(
            "InventoryListNode",
            "verify_inventory",
            {"filter": {"product_id": laptop_id}, "limit": 1},
        )

        # Verify order items
        verification_workflow.add_node(
            "OrderItemListNode",
            "verify_items",
            {"filter": {"order_id": order_id}, "limit": 10},
        )

        # Connect verification
        verification_workflow.add_connection("verify_order", "verify_inventory")
        verification_workflow.add_connection("verify_inventory", "verify_items")

        verify_results, _ = runtime.execute(verification_workflow.build())

        # Assertions
        final_order = verify_results["verify_order"]
        assert final_order["status"] == "shipped"
        assert final_order["total_amount"] == 1429.96  # 1299.99 + 2*49.99 + 79.99

        laptop_inventory = verify_results["verify_inventory"]["records"][0]
        assert laptop_inventory["quantity_available"] == 49  # 50 - 1
        assert laptop_inventory["quantity_reserved"] == 0  # shipped, not reserved

        order_items = verify_results["verify_items"]["records"]
        assert len(order_items) == 3

        # Phase 9: Analytics using DataFlow aggregation
        analytics_workflow = WorkflowBuilder()

        # Get sales summary
        analytics_workflow.add_node(
            "OrderListNode",
            "daily_orders",
            {"filter": {"status": "shipped"}, "limit": 100},
        )

        # Get inventory status
        analytics_workflow.add_node(
            "InventoryListNode", "inventory_status", {"filter": {}, "limit": 100}
        )

        analytics_workflow.add_connection("daily_orders", "inventory_status")

        analytics_results, _ = runtime.execute(analytics_workflow.build())

        shipped_orders = analytics_results["daily_orders"]["records"]
        assert len(shipped_orders) >= 1

        inventory_status = analytics_results["inventory_status"]["records"]
        assert len(inventory_status) == 4  # 4 products


@pytest.mark.e2e
@pytest.mark.requires_postgres
class TestProductionReadinessComplete:
    """Test production readiness scenarios using ONLY DataFlow components."""

    @pytest.fixture
    def db_url(self):
        """Real PostgreSQL database URL."""
        return os.getenv(
            "DATABASE_URL",
            "postgresql://test_user:test_password@localhost:5434/kailash_test",
        )

    @pytest.fixture
    def test_utils(self, db_url):
        """DataFlow test utilities."""
        return DataFlowTestUtils(db_url)

    def test_database_migration_using_dataflow(self, test_utils):
        """Test database migrations using DataFlow's migration system."""
        # Initial schema
        initial_migration = [
            {
                "type": "create_table",
                "name": "users",
                "columns": [
                    {"name": "id", "type": "serial", "primary_key": True},
                    {"name": "username", "type": "varchar(100)", "nullable": False},
                    {"name": "email", "type": "varchar(255)", "nullable": False},
                    {
                        "name": "created_at",
                        "type": "timestamp",
                        "default": "CURRENT_TIMESTAMP",
                    },
                ],
            },
            {
                "type": "create_table",
                "name": "posts",
                "columns": [
                    {"name": "id", "type": "serial", "primary_key": True},
                    {"name": "user_id", "type": "integer", "nullable": False},
                    {"name": "title", "type": "varchar(255)", "nullable": False},
                    {"name": "content", "type": "text"},
                    {
                        "name": "created_at",
                        "type": "timestamp",
                        "default": "CURRENT_TIMESTAMP",
                    },
                ],
            },
        ]

        # Apply initial migration
        test_utils.run_migration(initial_migration)

        # Verify schema
        assert test_utils.verify_schema(["users", "posts"])

        # Schema evolution - add new columns
        evolution_migration = [
            {
                "type": "add_column",
                "table": "users",
                "column": {
                    "name": "profile_picture",
                    "type": "varchar(500)",
                    "nullable": True,
                },
            },
            {
                "type": "add_column",
                "table": "posts",
                "column": {
                    "name": "published",
                    "type": "boolean",
                    "nullable": False,
                    "default": "false",
                },
            },
        ]

        # Apply evolution migration
        test_utils.run_migration(evolution_migration)

        # Create DataFlow models for the migrated schema
        db = DataFlow(database_url=test_utils.database_url)

        @db.model
        class User:
            username: str
            email: str
            profile_picture: Optional[str] = None

        @db.model
        class Post:
            user_id: int
            title: str
            content: Optional[str] = None
            published: bool = False

        # Use the models with DataFlow
        runtime = LocalRuntime()

        # Create test data
        test_workflow = WorkflowBuilder()

        test_workflow.add_node(
            "UserCreateNode",
            "create_user",
            {
                "username": "testuser",
                "email": "test@example.com",
                "profile_picture": "https://example.com/avatar.jpg",
            },
        )

        test_workflow.add_node(
            "PostCreateNode",
            "create_post",
            {
                "user_id": "${create_user.id}",
                "title": "Test Post",
                "content": "This is a test post after migration",
                "published": True,
            },
        )

        test_workflow.add_connection("create_user", "create_post")

        results, _ = runtime.execute(test_workflow.build())

        assert results["create_user"]["username"] == "testuser"
        assert results["create_post"]["published"] is True

        # Cleanup
        cleanup_migration = [
            {"type": "drop_table", "name": "posts"},
            {"type": "drop_table", "name": "users"},
        ]

        test_utils.run_migration(cleanup_migration)
