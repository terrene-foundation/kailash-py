"""
Simple E2E test for e-commerce using ONLY DataFlow components.
Demonstrates the correct way to use DataFlow without raw SQL or psql.
"""

import os
from datetime import datetime
from typing import Optional

import pytest
from dataflow import DataFlow
from dataflow.testing.simple_test_utils import clean_test_database


@pytest.mark.e2e
@pytest.mark.requires_postgres
class TestSimpleECommerce:
    """Test e-commerce flow using DataFlow components correctly."""

    @pytest.fixture
    def db_url(self):
        """Real PostgreSQL database URL."""
        return os.getenv(
            "DATABASE_URL",
            "postgresql://test_user:test_password@localhost:5434/kailash_test",
        )

    @pytest.fixture
    def ecommerce_db(self, db_url):
        """Setup e-commerce DataFlow models."""
        # Clean database first
        clean_test_database(db_url)

        # Create DataFlow instance
        db = DataFlow(database_url=db_url)

        # Define simple models
        @db.model
        class Customer:
            name: str
            email: str

        @db.model
        class Product:
            name: str
            price: float
            stock: int = 0

        @db.model
        class Order:
            customer_id: int
            total: float
            status: str = "pending"

        # Create tables
        db.create_tables()

        yield db

        # Cleanup
        clean_test_database(db_url)

    def test_simple_order_flow(self, ecommerce_db):
        """Test simple order flow using DataFlow correctly."""

        # Step 1: Create a customer using generated node directly
        create_customer_node = ecommerce_db._nodes["CustomerCreateNode"]()
        customer = create_customer_node.execute(
            name="John Doe", email="john@example.com"
        )
        assert customer["id"] is not None
        assert customer["name"] == "John Doe"

        # Step 2: Create products using bulk operation
        products_data = [
            {"name": "Laptop", "price": 999.99, "stock": 10},
            {"name": "Mouse", "price": 29.99, "stock": 50},
        ]

        bulk_create_node = ecommerce_db._nodes["ProductBulkCreateNode"]()
        products_result = bulk_create_node.execute(data=products_data, batch_size=1000)
        assert products_result["processed"] == 2

        # Step 3: List products to get their IDs
        list_products_node = ecommerce_db._nodes["ProductListNode"]()
        list_result = list_products_node.execute(limit=10)
        products = list_result["records"]
        assert len(products) == 2

        # Step 4: Create an order
        # Calculate total
        laptop = next(p for p in products if p["name"] == "Laptop")
        mouse = next(p for p in products if p["name"] == "Mouse")
        total = laptop["price"] + mouse["price"]

        create_order_node = ecommerce_db._nodes["OrderCreateNode"]()
        order = create_order_node.execute(
            customer_id=customer["id"], total=total, status="pending"
        )
        assert order["id"] is not None
        assert abs(order["total"] - 1029.98) < 0.01  # Float comparison tolerance
        assert order["customer_id"] == customer["id"]

        # Step 5: Update order status
        update_order_node = ecommerce_db._nodes["OrderUpdateNode"]()
        updated = update_order_node.execute(id=order["id"], status="completed")
        assert updated["updated"] is True

        # Step 6: Verify final state
        # Read the order
        read_order_node = ecommerce_db._nodes["OrderReadNode"]()
        final_order = read_order_node.execute(id=order["id"])
        assert final_order["status"] == "completed"
        assert abs(final_order["total"] - 1029.98) < 0.01  # Float comparison tolerance

        # List all orders for customer
        list_orders_node = ecommerce_db._nodes["OrderListNode"]()
        list_result = list_orders_node.execute(
            filter={"customer_id": customer["id"]}, limit=10
        )
        customer_orders = list_result["records"]
        assert len(customer_orders) == 1
        assert customer_orders[0]["id"] == order["id"]
