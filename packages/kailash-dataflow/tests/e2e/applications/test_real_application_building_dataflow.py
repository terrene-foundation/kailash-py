"""
End-to-end tests for building real applications with DataFlow.

Tests complete application scenarios including e-commerce, blog platforms,
SaaS applications, and enterprise systems to validate production readiness.
Uses DataFlow components instead of raw SQL/psql for all operations.
"""

import asyncio
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from dataflow import DataFlow
from dataflow.testing.dataflow_test_utils import DataFlowTestUtils

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestECommerceApplication:
    """Test building a complete e-commerce application with DataFlow."""

    def setup_method(self):
        """Set up test database connection."""
        # Use the official test infrastructure on port 5434
        self.db_url = "postgresql://test_user:test_password@localhost:5434/kailash_test"
        self.test_utils = DataFlowTestUtils(self.db_url)

    def teardown_method(self):
        """Clean up test database after each test."""
        # Use DataFlow's migration system to clean up
        self.test_utils.cleanup_database()

    def test_complete_ecommerce_order_flow(self):
        """Test complete e-commerce order flow from cart to delivery."""
        # Use real PostgreSQL database for E2E testing
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        # Define e-commerce models
        @db.model
        class Customer:
            name: str
            email: str
            address: str
            loyalty_points: int = 0

        @db.model
        class Product:
            name: str
            description: str
            price: float
            inventory: int
            category: str

        @db.model
        class Cart:
            customer_id: int
            created_at: float = time.time()
            status: str = "active"

        @db.model
        class CartItem:
            cart_id: int
            product_id: int
            quantity: int
            unit_price: float

        @db.model
        class Order:
            customer_id: int
            cart_id: int
            total_amount: float
            discount_amount: float = 0.0
            tax_amount: float = 0.0
            status: str = "pending"
            payment_status: str = "pending"

        @db.model
        class OrderItem:
            order_id: int
            product_id: int
            quantity: int
            unit_price: float
            total_price: float

        @db.model
        class Inventory:
            product_id: int
            available_quantity: int
            reserved_quantity: int = 0
            warehouse_location: str = "main"

        # Create tables
        db.create_tables()

        # Phase 1: Customer Registration and Product Catalog Setup
        # Create customer using generated node directly
        create_customer_node = db._nodes["CustomerCreateNode"]()
        customer = create_customer_node.execute(
            name="John Doe",
            email="john@example.com",
            address="123 Main St, City, Country",
        )
        assert customer["id"] is not None

        # Bulk create products
        bulk_product_node = db._nodes["ProductBulkCreateNode"]()
        products = bulk_product_node.execute(
            data=[
                {
                    "name": "Laptop Pro 15",
                    "description": "High-performance laptop",
                    "price": 1299.99,
                    "inventory": 50,
                    "category": "Electronics",
                },
                {
                    "name": "Wireless Mouse",
                    "description": "Ergonomic wireless mouse",
                    "price": 49.99,
                    "inventory": 200,
                    "category": "Accessories",
                },
                {
                    "name": "USB-C Hub",
                    "description": "7-in-1 USB-C hub",
                    "price": 79.99,
                    "inventory": 100,
                    "category": "Accessories",
                },
            ],
            batch_size=1000,
        )
        assert products["processed"] == 3

        # List products to get their IDs
        list_products_node = db._nodes["ProductListNode"]()
        product_list = list_products_node.execute(limit=10)
        products = product_list["records"]

        # Create inventory records
        bulk_inventory_node = db._nodes["InventoryBulkCreateNode"]()
        inventory_result = bulk_inventory_node.execute(
            data=[
                {"product_id": p["id"], "available_quantity": p["inventory"]}
                for p in products
            ],
            batch_size=1000,
        )
        assert inventory_result["processed"] == 3

        # Phase 2: Shopping Cart Management
        # Create shopping cart
        create_cart_node = db._nodes["CartCreateNode"]()
        cart = create_cart_node.execute(
            customer_id=customer["id"], created_at=time.time()
        )

        # Add items to cart
        laptop = next(p for p in products if "Laptop" in p["name"])
        mouse = next(p for p in products if "Mouse" in p["name"])

        bulk_cart_items_node = db._nodes["CartItemBulkCreateNode"]()
        cart_items_result = bulk_cart_items_node.execute(
            data=[
                {
                    "cart_id": cart["id"],
                    "product_id": laptop["id"],
                    "quantity": 1,
                    "unit_price": laptop["price"],
                },
                {
                    "cart_id": cart["id"],
                    "product_id": mouse["id"],
                    "quantity": 2,
                    "unit_price": mouse["price"],
                },
            ],
            batch_size=1000,
        )

        # Phase 3: Order Processing
        # Calculate order totals
        total_amount = laptop["price"] + (mouse["price"] * 2)
        discount_amount = total_amount * 0.1  # 10% discount
        tax_amount = (total_amount - discount_amount) * 0.08  # 8% tax

        # Create order
        create_order_node = db._nodes["OrderCreateNode"]()
        order = create_order_node.execute(
            customer_id=customer["id"],
            cart_id=cart["id"],
            total_amount=total_amount - discount_amount + tax_amount,
            discount_amount=discount_amount,
            tax_amount=tax_amount,
            status="confirmed",
            payment_status="paid",
        )

        # Create order items
        list_cart_items_node = db._nodes["CartItemListNode"]()
        cart_items = list_cart_items_node.execute(
            filter={"cart_id": cart["id"]}, limit=100
        )["records"]

        bulk_order_items_node = db._nodes["OrderItemBulkCreateNode"]()
        order_items_data = [
            {
                "order_id": order["id"],
                "product_id": item["product_id"],
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
                "total_price": item["unit_price"] * item["quantity"],
            }
            for item in cart_items
        ]
        order_items_result = bulk_order_items_node.execute(
            data=order_items_data, batch_size=1000
        )

        # Phase 4: Inventory Management
        # Update inventory for each product
        for item in cart_items:
            read_inventory_node = db._nodes["InventoryListNode"]()
            inv_result = read_inventory_node.execute(
                filter={"product_id": item["product_id"]}, limit=1
            )
            inventory = inv_result["records"][0]

            update_inventory_node = db._nodes["InventoryUpdateNode"]()
            update_inventory_node.execute(
                id=inventory["id"],
                available_quantity=inventory["available_quantity"] - item["quantity"],
                reserved_quantity=inventory["reserved_quantity"] + item["quantity"],
            )

        # Update cart status
        update_cart_node = db._nodes["CartUpdateNode"]()
        update_cart_node.execute(id=cart["id"], status="completed")

        # Phase 5: Verification
        # Verify order was created successfully
        read_order_node = db._nodes["OrderReadNode"]()
        final_order = read_order_node.execute(id=order["id"])
        assert final_order["status"] == "confirmed"
        assert final_order["payment_status"] == "paid"

        # Verify inventory was updated
        for item in cart_items:
            read_inventory_node = db._nodes["InventoryListNode"]()
            inv_result = read_inventory_node.execute(
                filter={"product_id": item["product_id"]}, limit=1
            )
            inventory = inv_result["records"][0]
            original_inv = next(p for p in products if p["id"] == item["product_id"])[
                "inventory"
            ]
            assert inventory["available_quantity"] == original_inv - item["quantity"]
            assert inventory["reserved_quantity"] == item["quantity"]

        # Verify customer loyalty points (would be updated by a trigger or workflow)
        # For now, just verify customer still exists
        read_customer_node = db._nodes["CustomerReadNode"]()
        final_customer = read_customer_node.execute(id=customer["id"])
        assert final_customer["email"] == "john@example.com"

        print("✓ E-commerce order flow completed successfully")
