"""
E2E tests for real application building scenarios using DataFlow components.

Tests complete application workflows to ensure DataFlow can power
production applications WITHOUT using psql or raw SQL commands.
"""

import asyncio
import os
from datetime import datetime
from typing import Optional

import pytest
from dataflow import DataFlow

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.e2e
@pytest.mark.requires_postgres
class TestECommerceApplication:
    """Test complete e-commerce application using DataFlow components."""

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
        # Clear existing data using DataFlow's cleanup capabilities
        db = DataFlow(
            database_url=db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        # Define e-commerce models
        @db.model
        class Customer:
            name: str
            email: str
            phone: Optional[str] = None
            address: Optional[str] = None

        @db.model
        class Product:
            name: str
            description: str
            price: float
            stock_quantity: int = 0
            category: str = "general"

        @db.model
        class Cart:
            customer_id: int
            status: str = "active"

        @db.model
        class CartItem:
            cart_id: int
            product_id: int
            quantity: int = 1

        @db.model
        class Order:
            customer_id: int
            total_amount: float
            status: str = "pending"
            payment_method: Optional[str] = None
            shipping_address: Optional[str] = None

        @db.model
        class OrderItem:
            order_id: int
            product_id: int
            quantity: int
            unit_price: float

        # Create tables
        db.create_tables()

        yield db

        # Cleanup using DataFlow's drop_tables if available
        if hasattr(db, "drop_tables"):
            db.drop_tables()

    def test_complete_ecommerce_order_flow(self, ecommerce_db):
        """Test complete e-commerce order flow from cart to delivery using DataFlow."""
        runtime = LocalRuntime()

        # Phase 1: Customer Registration
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

        # Phase 2: Product Catalog Setup
        product_workflow = WorkflowBuilder()

        products = [
            {
                "name": "Laptop",
                "description": "High-performance laptop",
                "price": 999.99,
                "stock_quantity": 10,
                "category": "electronics",
            },
            {
                "name": "Mouse",
                "description": "Wireless mouse",
                "price": 29.99,
                "stock_quantity": 50,
                "category": "accessories",
            },
            {
                "name": "Keyboard",
                "description": "Mechanical keyboard",
                "price": 79.99,
                "stock_quantity": 30,
                "category": "accessories",
            },
        ]

        # Use bulk create for products
        product_workflow.add_node(
            "ProductBulkCreateNode",
            "create_products",
            {"data": products, "batch_size": 10},
        )

        product_workflow.add_node("ProductListNode", "list_products", {"limit": 10})

        product_workflow.add_connection("create_products", "list_products")

        results, _ = runtime.execute(product_workflow.build())
        created_products = results["list_products"]["records"]

        # Phase 3: Shopping Cart Flow
        cart_workflow = WorkflowBuilder()

        # Create cart
        cart_workflow.add_node(
            "CartCreateNode",
            "create_cart",
            {"customer_id": customer_id, "status": "active"},
        )

        # Add items to cart
        laptop_id = next(p["id"] for p in created_products if p["name"] == "Laptop")
        mouse_id = next(p["id"] for p in created_products if p["name"] == "Mouse")

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

        # Calculate cart total using DataFlow aggregation
        cart_workflow.add_node(
            "CartItemListNode",
            "get_cart_items",
            {"filter": {"cart_id": "${create_cart.id}"}, "limit": 10},
        )

        # Connect cart workflow
        cart_workflow.add_connection("create_cart", "add_laptop")
        cart_workflow.add_connection("add_laptop", "add_mouse")
        cart_workflow.add_connection("add_mouse", "get_cart_items")

        cart_results, _ = runtime.execute(cart_workflow.build())
        cart_id = cart_results["create_cart"]["id"]
        cart_items = cart_results["get_cart_items"]["records"]

        # Phase 4: Checkout Process
        checkout_workflow = WorkflowBuilder()

        # Calculate total from cart items
        total_amount = 0
        for item in cart_items:
            product = next(p for p in created_products if p["id"] == item["product_id"])
            total_amount += product["price"] * item["quantity"]

        # Create order
        checkout_workflow.add_node(
            "OrderCreateNode",
            "create_order",
            {
                "customer_id": customer_id,
                "total_amount": total_amount,
                "status": "pending",
                "payment_method": "credit_card",
                "shipping_address": "123 Main St, City, 12345",
            },
        )

        # Create order items
        for idx, item in enumerate(cart_items):
            product = next(p for p in created_products if p["id"] == item["product_id"])
            checkout_workflow.add_node(
                "OrderItemCreateNode",
                f"order_item_{idx}",
                {
                    "order_id": "${create_order.id}",
                    "product_id": item["product_id"],
                    "quantity": item["quantity"],
                    "unit_price": product["price"],
                },
            )

            if idx == 0:
                checkout_workflow.add_connection("create_order", f"order_item_{idx}")
            else:
                checkout_workflow.add_connection(
                    f"order_item_{idx-1}", f"order_item_{idx}"
                )

        # Update cart status
        checkout_workflow.add_node(
            "CartUpdateNode", "close_cart", {"id": cart_id, "status": "checked_out"}
        )

        # Update product inventory
        for idx, item in enumerate(cart_items):
            product = next(p for p in created_products if p["id"] == item["product_id"])
            checkout_workflow.add_node(
                "ProductUpdateNode",
                f"update_stock_{idx}",
                {
                    "id": item["product_id"],
                    "stock_quantity": product["stock_quantity"] - item["quantity"],
                },
            )

        # Connect final nodes
        last_item_idx = len(cart_items) - 1
        checkout_workflow.add_connection(f"order_item_{last_item_idx}", "close_cart")
        checkout_workflow.add_connection("close_cart", "update_stock_0")

        for idx in range(len(cart_items) - 1):
            checkout_workflow.add_connection(
                f"update_stock_{idx}", f"update_stock_{idx+1}"
            )

        # Execute checkout
        checkout_results, _ = runtime.execute(checkout_workflow.build())
        order_id = checkout_results["create_order"]["id"]

        # Phase 5: Order Processing
        processing_workflow = WorkflowBuilder()

        # Simulate payment processing
        processing_workflow.add_node(
            "OrderUpdateNode",
            "process_payment",
            {"id": order_id, "status": "payment_confirmed"},
        )

        # Prepare for shipping
        processing_workflow.add_node(
            "OrderUpdateNode",
            "prepare_shipping",
            {"id": order_id, "status": "preparing_shipment"},
        )

        # Ship order
        processing_workflow.add_node(
            "OrderUpdateNode", "ship_order", {"id": order_id, "status": "shipped"}
        )

        # Verify final state
        processing_workflow.add_node("OrderReadNode", "verify_order", {"id": order_id})

        # Connect processing workflow
        processing_workflow.add_connection("process_payment", "prepare_shipping")
        processing_workflow.add_connection("prepare_shipping", "ship_order")
        processing_workflow.add_connection("ship_order", "verify_order")

        # Execute processing
        processing_results, _ = runtime.execute(processing_workflow.build())

        # Assertions
        final_order = processing_results["verify_order"]
        assert final_order["status"] == "shipped"
        assert final_order["total_amount"] == 1059.97  # 999.99 + 2*29.99
        assert final_order["customer_id"] == customer_id

        # Verify inventory was updated
        inventory_check = WorkflowBuilder()
        inventory_check.add_node("ProductReadNode", "check_laptop", {"id": laptop_id})
        inventory_check.add_node("ProductReadNode", "check_mouse", {"id": mouse_id})
        inventory_check.add_connection("check_laptop", "check_mouse")

        inventory_results, _ = runtime.execute(inventory_check.build())
        assert inventory_results["check_laptop"]["stock_quantity"] == 9  # 10 - 1
        assert inventory_results["check_mouse"]["stock_quantity"] == 48  # 50 - 2


@pytest.mark.e2e
@pytest.mark.requires_postgres
class TestBlogPlatformApplication:
    """Test complete blog platform using DataFlow components."""

    @pytest.fixture
    def blog_db(self):
        """Setup blog DataFlow models."""
        db_url = os.getenv(
            "DATABASE_URL",
            "postgresql://test_user:test_password@localhost:5434/kailash_test",
        )

        db = DataFlow(database_url=db_url)

        @db.model
        class BlogUser:
            username: str
            email: str
            password_hash: str
            role: str = "author"

        @db.model
        class BlogPost:
            author_id: int
            title: str
            content: str
            tags: list = []
            status: str = "draft"
            published_at: Optional[datetime] = None
            view_count: int = 0

        @db.model
        class Comment:
            post_id: int
            author_id: int
            content: str
            is_approved: bool = True

        db.create_tables()

        yield db

        if hasattr(db, "drop_tables"):
            db.drop_tables()

    def test_complete_blog_content_management_flow(self, blog_db):
        """Test blog content creation and management using DataFlow."""
        runtime = LocalRuntime()

        # Create users
        user_workflow = WorkflowBuilder()

        users = [
            {
                "username": "admin",
                "email": "admin@blog.com",
                "password_hash": "hashed_admin",
                "role": "admin",
            },
            {
                "username": "author1",
                "email": "author1@blog.com",
                "password_hash": "hashed_author1",
                "role": "author",
            },
            {
                "username": "reader1",
                "email": "reader1@blog.com",
                "password_hash": "hashed_reader1",
                "role": "reader",
            },
        ]

        user_workflow.add_node(
            "BlogUserBulkCreateNode", "create_users", {"data": users, "batch_size": 10}
        )

        user_results, _ = runtime.execute(user_workflow.build())

        # Create blog posts
        post_workflow = WorkflowBuilder()

        # Get author ID
        author_workflow = WorkflowBuilder()
        author_workflow.add_node(
            "BlogUserListNode",
            "get_author",
            {"filter": {"username": "author1"}, "limit": 1},
        )

        author_results, _ = runtime.execute(author_workflow.build())
        author_id = author_results["get_author"]["records"][0]["id"]

        # Create posts
        posts = [
            {
                "author_id": author_id,
                "title": "Getting Started with DataFlow",
                "content": "DataFlow is a powerful ORM that simplifies database operations...",
                "tags": ["dataflow", "python", "database"],
                "status": "published",
                "published_at": datetime.now().isoformat(),
            },
            {
                "author_id": author_id,
                "title": "Advanced DataFlow Patterns",
                "content": "Let's explore advanced patterns in DataFlow...",
                "tags": ["dataflow", "advanced", "patterns"],
                "status": "draft",
            },
        ]

        post_workflow.add_node(
            "BlogPostBulkCreateNode", "create_posts", {"data": posts, "batch_size": 10}
        )

        post_workflow.add_node(
            "BlogPostListNode",
            "list_published",
            {"filter": {"status": "published"}, "limit": 10},
        )

        post_workflow.add_connection("create_posts", "list_published")

        post_results, _ = runtime.execute(post_workflow.build())
        published_posts = post_results["list_published"]["records"]

        # Simulate reading posts and updating view count
        view_workflow = WorkflowBuilder()

        for idx, post in enumerate(published_posts):
            view_workflow.add_node(
                "BlogPostUpdateNode",
                f"increment_views_{idx}",
                {
                    "id": post["id"],
                    "view_count": post["view_count"] + 10,  # Simulate 10 views
                },
            )

            if idx > 0:
                view_workflow.add_connection(
                    f"increment_views_{idx-1}", f"increment_views_{idx}"
                )

        if published_posts:
            runtime.execute(view_workflow.build())

        # Add comments
        comment_workflow = WorkflowBuilder()

        if published_posts:
            post_id = published_posts[0]["id"]

            # Get reader ID
            reader_workflow = WorkflowBuilder()
            reader_workflow.add_node(
                "BlogUserListNode",
                "get_reader",
                {"filter": {"username": "reader1"}, "limit": 1},
            )

            reader_results, _ = runtime.execute(reader_workflow.build())
            reader_id = reader_results["get_reader"]["records"][0]["id"]

            # Create comments
            comment_workflow.add_node(
                "CommentCreateNode",
                "add_comment1",
                {
                    "post_id": post_id,
                    "author_id": reader_id,
                    "content": "Great article! Very helpful.",
                    "is_approved": True,
                },
            )

            comment_workflow.add_node(
                "CommentCreateNode",
                "add_comment2",
                {
                    "post_id": post_id,
                    "author_id": author_id,
                    "content": "Thanks for reading!",
                    "is_approved": True,
                },
            )

            comment_workflow.add_node(
                "CommentListNode",
                "list_comments",
                {"filter": {"post_id": post_id}, "limit": 10},
            )

            comment_workflow.add_connection("add_comment1", "add_comment2")
            comment_workflow.add_connection("add_comment2", "list_comments")

            comment_results, _ = runtime.execute(comment_workflow.build())
            comments = comment_results["list_comments"]["records"]

            assert len(comments) == 2
            assert comments[0]["content"] == "Great article! Very helpful."
            assert comments[1]["content"] == "Thanks for reading!"

        # Verify final state
        final_workflow = WorkflowBuilder()

        final_workflow.add_node("BlogPostListNode", "all_posts", {"limit": 10})

        final_workflow.add_node("BlogUserListNode", "all_users", {"limit": 10})

        final_workflow.add_connection("all_posts", "all_users")

        final_results, _ = runtime.execute(final_workflow.build())

        assert len(final_results["all_posts"]["records"]) == 2
        assert len(final_results["all_users"]["records"]) == 3

        # Check view counts were updated
        viewed_post = next(
            p
            for p in final_results["all_posts"]["records"]
            if p["status"] == "published"
        )
        assert viewed_post["view_count"] == 10
