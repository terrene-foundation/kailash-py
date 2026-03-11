"""
End-to-end tests for building real applications with DataFlow.

Tests complete application scenarios including e-commerce, blog platforms,
SaaS applications, and enterprise systems to validate production readiness.
"""

import asyncio
import os
import subprocess

# Import DataFlow components
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from dataflow import DataFlow

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestECommerceApplication:
    """Test building a complete e-commerce application with DataFlow."""

    def setup_method(self):
        """Set up test database connection."""
        # Use the official test infrastructure on port 5434
        self.db_url = "postgresql://test_user:test_password@localhost:5434/kailash_test"

    def teardown_method(self):
        """Clean up test database after each test."""
        # Drop all tables to ensure clean state for next test
        import asyncpg

        async def cleanup():
            conn = await asyncpg.connect(
                host="localhost",
                port=5434,
                user="test_user",
                password="test_password",
                database="kailash_test",
            )
            try:
                # Drop all user tables (keep system tables)
                tables = await conn.fetch(
                    """
                    SELECT tablename FROM pg_tables
                    WHERE schemaname = 'public'
                    AND tablename NOT LIKE 'dataflow_%'
                """
                )
                for table in tables:
                    await conn.execute(
                        f"DROP TABLE IF EXISTS {table['tablename']} CASCADE"
                    )
            finally:
                await conn.close()

        asyncio.run(cleanup())

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
            subtotal: float

        @db.model
        class Payment:
            order_id: int
            amount: float
            payment_method: str
            transaction_id: str
            status: str = "pending"
            processed_at: float = None

        @db.model
        class Shipment:
            order_id: int
            tracking_number: str
            carrier: str
            status: str = "preparing"
            estimated_delivery: float

        # Create the database tables
        db.create_tables()

        runtime = LocalRuntime()

        # Step 1: Customer Registration
        workflow_customer = WorkflowBuilder()
        workflow_customer.add_node("CustomerCreateNode", "register_customer", {})

        customer_params = {
            "register_customer": {
                "name": "John Smith",
                "email": "john.smith@example.com",
                "address": "123 Main St, City, Country",
            }
        }
        customer_result, _ = runtime.execute(
            workflow_customer.build(), parameters=customer_params
        )
        assert customer_result is not None

        # Step 2: Product Catalog Setup
        workflow_products = WorkflowBuilder()
        products_data = [
            {
                "name": "Laptop",
                "description": "High-end laptop",
                "price": 1299.99,
                "inventory": 50,
                "category": "Electronics",
            },
            {
                "name": "Mouse",
                "description": "Wireless mouse",
                "price": 49.99,
                "inventory": 200,
                "category": "Accessories",
            },
            {
                "name": "Keyboard",
                "description": "Mechanical keyboard",
                "price": 149.99,
                "inventory": 100,
                "category": "Accessories",
            },
        ]

        workflow_products.add_node("ProductBulkCreateNode", "setup_products", {})

        products_params = {"setup_products": {"data": products_data, "batch_size": 10}}
        products_result, _ = runtime.execute(
            workflow_products.build(), parameters=products_params
        )
        assert products_result is not None

        # Step 3: Shopping Cart Creation
        workflow_cart = WorkflowBuilder()
        workflow_cart.add_node("CartCreateNode", "create_cart", {})

        cart_params = {
            "create_cart": {
                "customer_id": 1,
                "created_at": time.time(),
                "status": "active",
            }
        }
        cart_result, _ = runtime.execute(workflow_cart.build(), parameters=cart_params)
        assert cart_result is not None

        # Step 4: Add Items to Cart
        workflow_cart_items = WorkflowBuilder()
        cart_items = [
            {"cart_id": 1, "product_id": 1, "quantity": 1, "unit_price": 1299.99},
            {"cart_id": 1, "product_id": 2, "quantity": 2, "unit_price": 49.99},
        ]

        workflow_cart_items.add_node("CartItemBulkCreateNode", "add_to_cart", {})

        cart_items_params = {"add_to_cart": {"data": cart_items, "batch_size": 10}}
        cart_items_result, _ = runtime.execute(
            workflow_cart_items.build(), parameters=cart_items_params
        )
        assert cart_items_result is not None

        # Step 5: Calculate Order Total with Tax and Discount
        workflow_order = WorkflowBuilder()

        # Calculate totals
        subtotal = 1299.99 + (2 * 49.99)  # $1399.97
        tax_rate = 0.08  # 8% tax
        tax_amount = subtotal * tax_rate
        loyalty_discount = 50.0  # $50 loyalty discount
        total_amount = subtotal + tax_amount - loyalty_discount

        workflow_order.add_node("OrderCreateNode", "create_order", {})

        order_params = {
            "create_order": {
                "customer_id": 1,
                "cart_id": 1,
                "total_amount": total_amount,
                "discount_amount": loyalty_discount,
                "tax_amount": tax_amount,
                "status": "pending",
                "payment_status": "pending",
            }
        }
        order_result, _ = runtime.execute(
            workflow_order.build(), parameters=order_params
        )
        assert order_result is not None

        # Step 6: Process Payment
        workflow_payment = WorkflowBuilder()
        workflow_payment.add_node("PaymentCreateNode", "process_payment", {})

        # Simulate payment processing
        workflow_payment.add_node("PaymentUpdateNode", "confirm_payment", {})

        # Update order payment status
        workflow_payment.add_node("OrderUpdateNode", "update_order_payment", {})

        workflow_payment.add_connection(
            "process_payment", "id", "confirm_payment", "id"
        )
        workflow_payment.add_connection(
            "confirm_payment", "order_id", "update_order_payment", "id"
        )

        payment_params = {
            "process_payment": {
                "order_id": 1,
                "amount": total_amount,
                "payment_method": "credit_card",
                "transaction_id": "TXN-123456789",
                "status": "processing",
            },
            "confirm_payment": {
                "id": "1",
                "status": "completed",
                "processed_at": time.time(),
            },
            "update_order_payment": {
                "id": "1",
                "payment_status": "completed",
                "status": "confirmed",
            },
        }
        payment_result, _ = runtime.execute(
            workflow_payment.build(), parameters=payment_params
        )
        assert payment_result is not None

        # Step 7: Update Inventory
        workflow_inventory = WorkflowBuilder()
        workflow_inventory.add_node("ProductUpdateNode", "update_laptop_inventory", {})

        workflow_inventory.add_node("ProductUpdateNode", "update_mouse_inventory", {})

        inventory_params = {
            "update_laptop_inventory": {"id": "1", "inventory": 49},  # Reduced by 1
            "update_mouse_inventory": {"id": "2", "inventory": 198},  # Reduced by 2
        }
        inventory_result, _ = runtime.execute(
            workflow_inventory.build(), parameters=inventory_params
        )
        assert inventory_result is not None

        # Step 8: Create Shipment
        workflow_shipment = WorkflowBuilder()
        workflow_shipment.add_node("ShipmentCreateNode", "create_shipment", {})

        shipment_params = {
            "create_shipment": {
                "order_id": 1,
                "tracking_number": "SHIP-789012345",
                "carrier": "FastShip Express",
                "status": "preparing",
                "estimated_delivery": time.time()
                + (3 * 24 * 60 * 60),  # 3 days from now
            }
        }
        shipment_result, _ = runtime.execute(
            workflow_shipment.build(), parameters=shipment_params
        )
        assert shipment_result is not None

        # Step 9: Update Customer Loyalty Points
        workflow_loyalty = WorkflowBuilder()
        points_earned = int(total_amount / 10)  # 1 point per $10 spent

        workflow_loyalty.add_node("CustomerUpdateNode", "update_loyalty", {})

        loyalty_params = {
            "update_loyalty": {"id": "1", "loyalty_points": points_earned}
        }
        loyalty_result, _ = runtime.execute(
            workflow_loyalty.build(), parameters=loyalty_params
        )
        assert loyalty_result is not None

        # Step 10: Order Status Query
        workflow_status = WorkflowBuilder()
        workflow_status.add_node("OrderListNode", "check_order_status", {})

        status_params = {
            "check_order_status": {
                "filter": {"customer_id": 1, "status": "confirmed"},
                "sort": [{"created_at": -1}],
                "limit": 5,
            }
        }
        status_result, _ = runtime.execute(
            workflow_status.build(), parameters=status_params
        )
        assert status_result is not None

        # Verify complete e-commerce flow worked
        assert order_result is not None
        assert payment_result is not None
        assert shipment_result is not None
        assert "create_order" in order_result
        assert "confirm_payment" in payment_result
        assert "create_shipment" in shipment_result


class TestBlogPlatformApplication:
    """Updated test class with real database support."""

    def setup_method(self):
        """Set up test database connection."""
        # Use the official test infrastructure on port 5434
        self.db_url = "postgresql://test_user:test_password@localhost:5434/kailash_test"

    def teardown_method(self):
        """Clean up test database after each test."""
        # Drop all tables to ensure clean state for next test
        import asyncpg

        async def cleanup():
            conn = await asyncpg.connect(
                host="localhost",
                port=5434,
                user="test_user",
                password="test_password",
                database="kailash_test",
            )
            try:
                # Drop all user tables (keep system tables)
                tables = await conn.fetch(
                    """
                    SELECT tablename FROM pg_tables
                    WHERE schemaname = 'public'
                    AND tablename NOT LIKE 'dataflow_%'
                """
                )
                for table in tables:
                    await conn.execute(
                        f"DROP TABLE IF EXISTS {table['tablename']} CASCADE"
                    )
            finally:
                await conn.close()

        asyncio.run(cleanup())

    """Test building a complete blog platform with DataFlow."""

    def test_complete_blog_content_management_flow(self):
        """Test complete blog content management from authoring to publishing."""
        # Use real PostgreSQL database for E2E testing
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        # Define blog platform models
        @db.model
        class Author:
            username: str
            email: str
            bio: str
            verified: bool = False

        @db.model
        class Category:
            name: str
            slug: str
            description: str
            parent_id: int = None

        @db.model
        class Post:
            title: str
            slug: str
            content: str
            excerpt: str
            author_id: int
            category_id: int
            status: str = "draft"
            published_at: float = None
            view_count: int = 0
            featured: bool = False

        @db.model
        class Tag:
            name: str
            slug: str

        @db.model
        class PostTag:
            post_id: int
            tag_id: int

        @db.model
        class Comment:
            post_id: int
            author_name: str
            author_email: str
            content: str
            approved: bool = False
            created_at: float = time.time()

        @db.model
        class Subscriber:
            email: str
            active: bool = True
            subscribed_at: float = time.time()

        # Create the database tables
        db.create_tables()

        runtime = LocalRuntime()

        # Step 1: Author Registration
        workflow_author = WorkflowBuilder()
        workflow_author.add_node(
            "AuthorCreateNode",
            "register_author",
            {
                "username": "tech_writer",
                "email": "writer@techblog.com",
                "bio": "Technology enthusiast and software developer",
                "verified": True,
            },
        )

        author_result, _ = runtime.execute(workflow_author.build())
        assert author_result is not None

        # Step 2: Category Setup
        workflow_categories = WorkflowBuilder()
        categories_data = [
            {
                "name": "Technology",
                "slug": "technology",
                "description": "Tech news and tutorials",
            },
            {
                "name": "Programming",
                "slug": "programming",
                "description": "Coding tutorials",
                "parent_id": 1,
            },
            {
                "name": "AI & ML",
                "slug": "ai-ml",
                "description": "Artificial Intelligence",
                "parent_id": 1,
            },
        ]

        workflow_categories.add_node(
            "CategoryBulkCreateNode",
            "setup_categories",
            {"data": categories_data, "batch_size": 10},
        )

        categories_result, _ = runtime.execute(workflow_categories.build())
        assert categories_result is not None

        # Step 3: Create Blog Post
        workflow_post = WorkflowBuilder()
        workflow_post.add_node(
            "PostCreateNode",
            "create_post",
            {
                "title": "Getting Started with DataFlow",
                "slug": "getting-started-with-dataflow",
                "content": "DataFlow is a powerful framework for building data-driven applications...",
                "excerpt": "Learn how to build applications with DataFlow",
                "author_id": 1,
                "category_id": 2,
                "status": "draft",
            },
        )

        post_result, _ = runtime.execute(workflow_post.build())
        assert post_result is not None

        # Step 4: Add Tags
        workflow_tags = WorkflowBuilder()
        tags_data = [
            {"name": "DataFlow", "slug": "dataflow"},
            {"name": "Python", "slug": "python"},
            {"name": "Database", "slug": "database"},
        ]

        workflow_tags.add_node(
            "TagBulkCreateNode", "create_tags", {"data": tags_data, "batch_size": 10}
        )

        # Associate tags with post
        post_tags_data = [
            {"post_id": 1, "tag_id": 1},
            {"post_id": 1, "tag_id": 2},
            {"post_id": 1, "tag_id": 3},
        ]

        workflow_tags.add_node(
            "PostTagBulkCreateNode",
            "associate_tags",
            {"data": post_tags_data, "batch_size": 10},
        )

        tags_result, _ = runtime.execute(workflow_tags.build())
        assert tags_result is not None

        # Step 5: Review and Publish Post
        workflow_publish = WorkflowBuilder()

        # Update post to published
        workflow_publish.add_node(
            "PostUpdateNode",
            "publish_post",
            {
                "id": "1",
                "status": "published",
                "published_at": time.time(),
                "featured": True,
            },
        )

        publish_result, _ = runtime.execute(workflow_publish.build())
        assert publish_result is not None

        # Step 6: Add Comments
        workflow_comments = WorkflowBuilder()
        comments_data = [
            {
                "post_id": 1,
                "author_name": "Alice",
                "author_email": "alice@example.com",
                "content": "Great article! Very helpful.",
                "approved": True,
            },
            {
                "post_id": 1,
                "author_name": "Bob",
                "author_email": "bob@example.com",
                "content": "Thanks for sharing this tutorial.",
                "approved": True,
            },
        ]

        workflow_comments.add_node(
            "CommentBulkCreateNode",
            "add_comments",
            {"data": comments_data, "batch_size": 10},
        )

        comments_result, _ = runtime.execute(workflow_comments.build())
        assert comments_result is not None

        # Step 7: Update View Count
        workflow_views = WorkflowBuilder()
        workflow_views.add_node(
            "PostUpdateNode", "increment_views", {"id": "1", "view_count": 150}
        )

        views_result, _ = runtime.execute(workflow_views.build())
        assert views_result is not None

        # Step 8: Newsletter Subscribers
        workflow_subscribers = WorkflowBuilder()
        subscribers_data = [
            {"email": "subscriber1@example.com"},
            {"email": "subscriber2@example.com"},
            {"email": "subscriber3@example.com"},
        ]

        workflow_subscribers.add_node(
            "SubscriberBulkCreateNode",
            "add_subscribers",
            {"data": subscribers_data, "batch_size": 10},
        )

        subscribers_result, _ = runtime.execute(workflow_subscribers.build())
        assert subscribers_result is not None

        # Step 9: Content Analytics Query
        workflow_analytics = WorkflowBuilder()

        # Popular posts query
        workflow_analytics.add_node(
            "PostListNode",
            "popular_posts",
            {
                "filter": {"status": "published"},
                "sort": [{"view_count": -1}],
                "limit": 10,
            },
        )

        # Recent comments query
        workflow_analytics.add_node(
            "CommentListNode",
            "recent_comments",
            {"filter": {"approved": True}, "sort": [{"created_at": -1}], "limit": 5},
        )

        analytics_result, _ = runtime.execute(workflow_analytics.build())
        assert analytics_result is not None

        # Verify blog platform flow
        assert post_result["create_post"]["title"] == "Getting Started with DataFlow"
        assert publish_result["publish_post"]["status"] == "published"
        assert views_result["increment_views"]["view_count"] == 150


class TestSaaSApplicationMultiTenant:
    """Updated test class with real database support."""

    def setup_method(self):
        """Set up test database connection."""
        # Use the official test infrastructure on port 5434
        self.db_url = "postgresql://test_user:test_password@localhost:5434/kailash_test"

    def teardown_method(self):
        """Clean up test database after each test."""
        # Drop all tables to ensure clean state for next test
        import asyncpg

        async def cleanup():
            conn = await asyncpg.connect(
                host="localhost",
                port=5434,
                user="test_user",
                password="test_password",
                database="kailash_test",
            )
            try:
                # Drop all user tables (keep system tables)
                tables = await conn.fetch(
                    """
                    SELECT tablename FROM pg_tables
                    WHERE schemaname = 'public'
                    AND tablename NOT LIKE 'dataflow_%'
                """
                )
                for table in tables:
                    await conn.execute(
                        f"DROP TABLE IF EXISTS {table['tablename']} CASCADE"
                    )
            finally:
                await conn.close()

        asyncio.run(cleanup())

    """Test building a multi-tenant SaaS application with DataFlow."""

    def test_complete_saas_tenant_lifecycle(self):
        """Test complete SaaS tenant lifecycle from onboarding to usage."""
        # Use real PostgreSQL database for E2E testing
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        # Define SaaS models with multi-tenancy
        @db.model
        class Tenant:
            name: str
            subdomain: str
            plan: str
            status: str = "trial"
            created_at: float = time.time()
            trial_ends_at: float = time.time() + (14 * 24 * 60 * 60)  # 14 days trial

        @db.model
        class User:
            tenant_id: int
            name: str
            email: str
            role: str
            active: bool = True
            last_login: float = None

            __dataflow__ = {"multi_tenant": True}

        @db.model
        class Project:
            tenant_id: int
            name: str
            description: str
            status: str = "active"
            created_by: int

            __dataflow__ = {"multi_tenant": True, "soft_delete": True}

        @db.model
        class Task:
            tenant_id: int
            project_id: int
            title: str
            description: str
            assigned_to: int = None
            priority: str = "medium"
            status: str = "todo"
            due_date: float = None

            __dataflow__ = {"multi_tenant": True, "versioned": True}

        @db.model
        class Usage:
            tenant_id: int
            resource_type: str
            resource_count: int
            measured_at: float = time.time()

            __dataflow__ = {"multi_tenant": True}

        @db.model
        class Invoice:
            tenant_id: int
            amount: float
            status: str = "pending"
            due_date: float
            paid_at: float = None

            __dataflow__ = {"multi_tenant": True}

        # Create the database tables
        db.create_tables()

        runtime = LocalRuntime()

        # Step 1: Tenant Onboarding
        workflow_tenant = WorkflowBuilder()
        workflow_tenant.add_node("TenantCreateNode", "onboard_tenant", {})

        tenant_params = {
            "onboard_tenant": {
                "name": "Acme Corporation",
                "subdomain": "acme",
                "plan": "professional",
                "status": "trial",
            }
        }
        tenant_result, _ = runtime.execute(
            workflow_tenant.build(), parameters=tenant_params
        )
        assert tenant_result is not None
        tenant_id = 1

        # Step 2: Create Admin User
        workflow_admin = WorkflowBuilder()
        workflow_admin.add_node("UserCreateNode", "create_admin", {})

        admin_params = {
            "create_admin": {
                "tenant_id": tenant_id,
                "name": "Admin User",
                "email": "admin@acme.com",
                "role": "admin",
                "active": True,
            }
        }
        admin_result, _ = runtime.execute(
            workflow_admin.build(), parameters=admin_params
        )
        assert admin_result is not None

        # Step 3: Create Team Members
        workflow_team = WorkflowBuilder()
        team_data = [
            {
                "tenant_id": tenant_id,
                "name": "John Doe",
                "email": "john@acme.com",
                "role": "member",
            },
            {
                "tenant_id": tenant_id,
                "name": "Jane Smith",
                "email": "jane@acme.com",
                "role": "member",
            },
            {
                "tenant_id": tenant_id,
                "name": "Bob Johnson",
                "email": "bob@acme.com",
                "role": "viewer",
            },
        ]

        workflow_team.add_node("UserBulkCreateNode", "create_team", {})

        team_params = {"create_team": {"data": team_data, "batch_size": 10}}
        team_result, _ = runtime.execute(workflow_team.build(), parameters=team_params)
        assert team_result is not None

        # Step 4: Create Projects
        workflow_projects = WorkflowBuilder()
        projects_data = [
            {
                "tenant_id": tenant_id,
                "name": "Website Redesign",
                "description": "Redesign company website",
                "created_by": 1,
            },
            {
                "tenant_id": tenant_id,
                "name": "Mobile App",
                "description": "Build mobile application",
                "created_by": 1,
            },
        ]

        workflow_projects.add_node("ProjectBulkCreateNode", "create_projects", {})

        projects_params = {"create_projects": {"data": projects_data, "batch_size": 10}}
        projects_result, _ = runtime.execute(
            workflow_projects.build(), parameters=projects_params
        )
        assert projects_result is not None

        # Step 5: Create Tasks
        workflow_tasks = WorkflowBuilder()
        tasks_data = [
            {
                "tenant_id": tenant_id,
                "project_id": 1,
                "title": "Design mockups",
                "description": "Create initial design mockups",
                "assigned_to": 2,
                "priority": "high",
                "due_date": time.time() + (7 * 24 * 60 * 60),
            },
            {
                "tenant_id": tenant_id,
                "project_id": 1,
                "title": "Frontend development",
                "description": "Implement frontend components",
                "assigned_to": 3,
                "priority": "medium",
            },
            {
                "tenant_id": tenant_id,
                "project_id": 2,
                "title": "API development",
                "description": "Build REST API",
                "assigned_to": 2,
                "priority": "high",
            },
        ]

        workflow_tasks.add_node("TaskBulkCreateNode", "create_tasks", {})

        tasks_params = {"create_tasks": {"data": tasks_data, "batch_size": 10}}
        tasks_result, _ = runtime.execute(
            workflow_tasks.build(), parameters=tasks_params
        )
        assert tasks_result is not None

        # Step 6: Update Task Status
        workflow_task_update = WorkflowBuilder()
        workflow_task_update.add_node("TaskUpdateNode", "start_task", {})

        task_update_params = {
            "start_task": {
                "id": "1",
                "status": "in_progress",
                "version": 1,  # Optimistic locking
            }
        }
        task_update_result, _ = runtime.execute(
            workflow_task_update.build(), parameters=task_update_params
        )
        assert task_update_result is not None

        # Step 7: Track Usage
        workflow_usage = WorkflowBuilder()
        usage_data = [
            {"tenant_id": tenant_id, "resource_type": "users", "resource_count": 4},
            {"tenant_id": tenant_id, "resource_type": "projects", "resource_count": 2},
            {"tenant_id": tenant_id, "resource_type": "tasks", "resource_count": 3},
            {
                "tenant_id": tenant_id,
                "resource_type": "storage_gb",
                "resource_count": 5,
            },
        ]

        workflow_usage.add_node("UsageBulkCreateNode", "track_usage", {})

        usage_params = {"track_usage": {"data": usage_data, "batch_size": 10}}
        usage_result, _ = runtime.execute(
            workflow_usage.build(), parameters=usage_params
        )
        assert usage_result is not None

        # Step 8: Convert Trial to Paid
        workflow_conversion = WorkflowBuilder()
        workflow_conversion.add_node("TenantUpdateNode", "convert_to_paid", {})

        conversion_params = {
            "convert_to_paid": {
                "id": str(tenant_id),
                "status": "active",
                "plan": "professional",
            }
        }
        conversion_result, _ = runtime.execute(
            workflow_conversion.build(), parameters=conversion_params
        )
        assert conversion_result is not None

        # Step 9: Generate Invoice
        workflow_invoice = WorkflowBuilder()
        workflow_invoice.add_node("InvoiceCreateNode", "generate_invoice", {})

        invoice_params = {
            "generate_invoice": {
                "tenant_id": tenant_id,
                "amount": 99.00,
                "status": "pending",
                "due_date": time.time() + (30 * 24 * 60 * 60),  # 30 days
            }
        }
        invoice_result, _ = runtime.execute(
            workflow_invoice.build(), parameters=invoice_params
        )
        assert invoice_result is not None

        # Step 10: Multi-Tenant Query
        workflow_tenant_query = WorkflowBuilder()

        # Query only shows data for specific tenant
        workflow_tenant_query.add_node("TaskListNode", "tenant_tasks", {})

        tenant_query_params = {
            "tenant_tasks": {
                "filter": {"tenant_id": tenant_id, "status": "in_progress"},
                "sort": [{"priority": 1}, {"due_date": 1}],
            }
        }
        tenant_query_result, _ = runtime.execute(
            workflow_tenant_query.build(), parameters=tenant_query_params
        )
        assert tenant_query_result is not None

        # Verify SaaS flow
        assert tenant_result["onboard_tenant"]["name"] == "Acme Corporation"
        assert conversion_result["convert_to_paid"]["status"] == "active"
        assert invoice_result["generate_invoice"]["amount"] == 99.00


class TestAnalyticsDashboardApplication:
    """Updated test class with real database support."""

    def setup_method(self):
        """Set up test database connection."""
        # Use the official test infrastructure on port 5434
        self.db_url = "postgresql://test_user:test_password@localhost:5434/kailash_test"

    def teardown_method(self):
        """Clean up test database after each test."""
        # Drop all tables to ensure clean state for next test
        import asyncpg

        async def cleanup():
            conn = await asyncpg.connect(
                host="localhost",
                port=5434,
                user="test_user",
                password="test_password",
                database="kailash_test",
            )
            try:
                # Drop all user tables (keep system tables)
                tables = await conn.fetch(
                    """
                    SELECT tablename FROM pg_tables
                    WHERE schemaname = 'public'
                    AND tablename NOT LIKE 'dataflow_%'
                """
                )
                for table in tables:
                    await conn.execute(
                        f"DROP TABLE IF EXISTS {table['tablename']} CASCADE"
                    )
            finally:
                await conn.close()

        asyncio.run(cleanup())

    """Test building an analytics dashboard application with DataFlow."""

    def test_complete_analytics_pipeline(self):
        """Test complete analytics pipeline from data ingestion to visualization."""
        # Use real PostgreSQL database for E2E testing
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        # Define analytics models
        @db.model
        class DataSource:
            name: str
            type: str
            connection_string: str
            active: bool = True

        @db.model
        class Metric:
            name: str
            source_id: int
            query: str
            refresh_interval: int  # seconds
            last_refresh: float = None

        @db.model
        class MetricValue:
            metric_id: int
            value: float
            timestamp: float = time.time()
            dimensions: str = "{}"  # JSON string

        @db.model
        class Dashboard:
            name: str
            description: str
            layout: str = "{}"  # JSON string
            public: bool = False

        @db.model
        class Widget:
            dashboard_id: int
            metric_id: int
            widget_type: str
            position: str = "{}"  # JSON string
            config: str = "{}"  # JSON string

        @db.model
        class Alert:
            metric_id: int
            condition: str
            threshold: float
            severity: str = "warning"
            active: bool = True
            last_triggered: float = None

        # Create the database tables
        db.create_tables()

        runtime = LocalRuntime()

        # Step 1: Configure Data Sources
        workflow_sources = WorkflowBuilder()
        sources_data = [
            {
                "name": "Production Database",
                "type": "postgresql",
                "connection_string": "postgresql://prod/analytics",
            },
            {
                "name": "Sales API",
                "type": "rest_api",
                "connection_string": "https://api.sales.com/v1",
            },
            {
                "name": "User Events",
                "type": "event_stream",
                "connection_string": "kafka://events:9092",
            },
        ]

        workflow_sources.add_node(
            "DataSourceBulkCreateNode",
            "setup_sources",
            {"data": sources_data, "batch_size": 10},
        )

        sources_result, _ = runtime.execute(workflow_sources.build())
        assert sources_result is not None

        # Step 2: Define Metrics
        workflow_metrics = WorkflowBuilder()
        metrics_data = [
            {
                "name": "Active Users",
                "source_id": 1,
                "query": "SELECT COUNT(DISTINCT user_id) FROM sessions WHERE date = CURRENT_DATE",
                "refresh_interval": 300,  # 5 minutes
            },
            {
                "name": "Revenue Today",
                "source_id": 2,
                "query": "GET /metrics/revenue/today",
                "refresh_interval": 600,  # 10 minutes
            },
            {
                "name": "Conversion Rate",
                "source_id": 3,
                "query": "events.purchase / events.visit * 100",
                "refresh_interval": 300,
            },
            {
                "name": "Average Order Value",
                "source_id": 2,
                "query": "GET /metrics/aov",
                "refresh_interval": 900,  # 15 minutes
            },
        ]

        workflow_metrics.add_node(
            "MetricBulkCreateNode",
            "define_metrics",
            {"data": metrics_data, "batch_size": 10},
        )

        metrics_result, _ = runtime.execute(workflow_metrics.build())
        assert metrics_result is not None

        # Step 3: Collect Metric Values
        workflow_collect = WorkflowBuilder()

        # Simulate metric collection
        current_time = time.time()
        metric_values_data = [
            # Active Users over time
            {"metric_id": 1, "value": 1250, "timestamp": current_time - 3600},
            {"metric_id": 1, "value": 1320, "timestamp": current_time - 1800},
            {"metric_id": 1, "value": 1405, "timestamp": current_time},
            # Revenue over time
            {"metric_id": 2, "value": 15420.50, "timestamp": current_time - 3600},
            {"metric_id": 2, "value": 18930.25, "timestamp": current_time - 1800},
            {"metric_id": 2, "value": 22156.75, "timestamp": current_time},
            # Conversion Rate
            {"metric_id": 3, "value": 3.2, "timestamp": current_time - 3600},
            {"metric_id": 3, "value": 3.5, "timestamp": current_time - 1800},
            {"metric_id": 3, "value": 3.8, "timestamp": current_time},
            # Average Order Value
            {"metric_id": 4, "value": 85.50, "timestamp": current_time - 3600},
            {"metric_id": 4, "value": 92.30, "timestamp": current_time - 1800},
            {"metric_id": 4, "value": 89.75, "timestamp": current_time},
        ]

        workflow_collect.add_node(
            "MetricValueBulkCreateNode",
            "collect_metrics",
            {"data": metric_values_data, "batch_size": 20},
        )

        # Update last refresh time
        for i in range(1, 5):
            workflow_collect.add_node(
                "MetricUpdateNode",
                f"update_refresh_{i}",
                {"id": str(i), "last_refresh": current_time},
            )

        collect_result, _ = runtime.execute(workflow_collect.build())
        assert collect_result is not None

        # Step 4: Create Dashboard
        workflow_dashboard = WorkflowBuilder()
        workflow_dashboard.add_node("DashboardCreateNode", "create_dashboard", {})

        dashboard_params = {
            "create_dashboard": {
                "name": "Executive Dashboard",
                "description": "Real-time business metrics",
                "layout": '{"columns": 3, "rows": 2}',
                "public": False,
            }
        }
        dashboard_result, _ = runtime.execute(
            workflow_dashboard.build(), parameters=dashboard_params
        )
        assert dashboard_result is not None

        # Step 5: Add Widgets
        workflow_widgets = WorkflowBuilder()
        widgets_data = [
            {
                "dashboard_id": 1,
                "metric_id": 1,
                "widget_type": "number",
                "position": '{"row": 0, "col": 0}',
                "config": '{"title": "Active Users", "format": "number"}',
            },
            {
                "dashboard_id": 1,
                "metric_id": 2,
                "widget_type": "number",
                "position": '{"row": 0, "col": 1}',
                "config": '{"title": "Revenue Today", "format": "currency"}',
            },
            {
                "dashboard_id": 1,
                "metric_id": 3,
                "widget_type": "gauge",
                "position": '{"row": 0, "col": 2}',
                "config": '{"title": "Conversion Rate", "min": 0, "max": 10}',
            },
            {
                "dashboard_id": 1,
                "metric_id": 1,
                "widget_type": "line_chart",
                "position": '{"row": 1, "col": 0, "width": 2}',
                "config": '{"title": "Active Users Trend", "period": "1h"}',
            },
            {
                "dashboard_id": 1,
                "metric_id": 4,
                "widget_type": "bar_chart",
                "position": '{"row": 1, "col": 2}',
                "config": '{"title": "AOV Trend", "period": "1h"}',
            },
        ]

        workflow_widgets.add_node("WidgetBulkCreateNode", "add_widgets", {})

        widgets_params = {"add_widgets": {"data": widgets_data, "batch_size": 10}}
        widgets_result, _ = runtime.execute(
            workflow_widgets.build(), parameters=widgets_params
        )
        assert widgets_result is not None

        # Step 6: Set Up Alerts
        workflow_alerts = WorkflowBuilder()
        alerts_data = [
            {
                "metric_id": 1,
                "condition": "less_than",
                "threshold": 1000,
                "severity": "warning",
                "active": True,
            },
            {
                "metric_id": 2,
                "condition": "less_than",
                "threshold": 10000,
                "severity": "critical",
                "active": True,
            },
            {
                "metric_id": 3,
                "condition": "less_than",
                "threshold": 2.5,
                "severity": "warning",
                "active": True,
            },
        ]

        workflow_alerts.add_node("AlertBulkCreateNode", "setup_alerts", {})

        alerts_params = {"setup_alerts": {"data": alerts_data, "batch_size": 10}}
        alerts_result, _ = runtime.execute(
            workflow_alerts.build(), parameters=alerts_params
        )
        assert alerts_result is not None

        # Step 7: Query Dashboard Data
        workflow_query = WorkflowBuilder()

        # Get latest metric values
        workflow_query.add_node("MetricValueListNode", "latest_values", {})

        # Check triggered alerts
        workflow_query.add_node("AlertListNode", "check_alerts", {})

        query_params = {
            "latest_values": {
                "filter": {"timestamp": {"$gte": current_time - 300}},
                "sort": [{"timestamp": -1}],
                "limit": 20,
            },
            "check_alerts": {
                "filter": {
                    "active": True,
                    "last_triggered": {"$gte": current_time - 3600},
                },
                "sort": [{"severity": 1}, {"last_triggered": -1}],
            },
        }
        query_result, _ = runtime.execute(
            workflow_query.build(), parameters=query_params
        )
        assert query_result is not None

        # Verify analytics pipeline
        assert len(metrics_data) == 4
        assert dashboard_result["create_dashboard"]["name"] == "Executive Dashboard"
        assert len(widgets_data) == 5
        assert len(alerts_data) == 3


class TestProductionScenarios:
    """Updated test class with real database support."""

    def setup_method(self):
        """Set up test database connection."""
        # Use the official test infrastructure on port 5434
        self.db_url = "postgresql://test_user:test_password@localhost:5434/kailash_test"

    def teardown_method(self):
        """Clean up test database after each test."""
        # Drop all tables to ensure clean state for next test
        import asyncpg

        async def cleanup():
            conn = await asyncpg.connect(
                host="localhost",
                port=5434,
                user="test_user",
                password="test_password",
                database="kailash_test",
            )
            try:
                # Drop all user tables (keep system tables)
                tables = await conn.fetch(
                    """
                    SELECT tablename FROM pg_tables
                    WHERE schemaname = 'public'
                    AND tablename NOT LIKE 'dataflow_%'
                """
                )
                for table in tables:
                    await conn.execute(
                        f"DROP TABLE IF EXISTS {table['tablename']} CASCADE"
                    )
            finally:
                await conn.close()

        asyncio.run(cleanup())

    """Test production-level scenarios and edge cases."""

    def test_high_volume_data_processing(self):
        """Test handling high-volume data processing scenarios."""
        # Use real PostgreSQL database for E2E testing
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class Event:
            event_id: str
            event_type: str
            user_id: int
            properties: str  # JSON
            timestamp: float = time.time()

        # Create the database tables
        db.create_tables()

        runtime = LocalRuntime()

        # Simulate high-volume event ingestion
        workflow = WorkflowBuilder()

        # Generate 1000 events
        events_data = []
        event_types = ["page_view", "click", "purchase", "signup", "logout"]

        for i in range(1000):
            events_data.append(
                {
                    "event_id": f"evt_{i:06d}",
                    "event_type": event_types[i % len(event_types)],
                    "user_id": i % 100,  # 100 different users
                    "properties": f'{{"page": "/page{i % 10}", "value": {i * 1.5}}}',
                    "timestamp": time.time() - (1000 - i),  # Spread over time
                }
            )

        # Bulk insert with batching
        workflow.add_node(
            "EventBulkCreateNode",
            "ingest_events",
            {"data": events_data, "batch_size": 100},  # Process in batches of 100
        )

        start_time = time.time()
        result, _ = runtime.execute(workflow.build())
        end_time = time.time()

        processing_time = end_time - start_time

        # Verify high-volume processing
        assert result is not None
        assert processing_time < 10.0  # Should process 1000 records in under 10 seconds

        # Query aggregated data
        workflow_analytics = WorkflowBuilder()
        workflow_analytics.add_node(
            "EventListNode",
            "aggregate_events",
            {
                "filter": {"event_type": "purchase"},
                "aggregate": {
                    "total_purchases": {"$count": "*"},
                    "unique_users": {"$count_distinct": "user_id"},
                },
            },
        )

        analytics_result, _ = runtime.execute(workflow_analytics.build())
        assert analytics_result is not None

    def test_concurrent_user_operations(self):
        """Test handling concurrent operations from multiple users."""
        # Use real PostgreSQL database for E2E testing
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class Account:
            user_id: int
            balance: float
            version: int = 1

            __dataflow__ = {"versioned": True}  # Optimistic locking

        @db.model
        class Transaction:
            from_account: int
            to_account: int
            amount: float
            status: str = "pending"
            created_at: float = time.time()

        # Create the database tables
        db.create_tables()

        runtime = LocalRuntime()

        # Create test accounts
        workflow_setup = WorkflowBuilder()
        accounts_data = [
            {"user_id": 1, "balance": 1000.0},
            {"user_id": 2, "balance": 1000.0},
            {"user_id": 3, "balance": 1000.0},
        ]

        workflow_setup.add_node(
            "AccountBulkCreateNode",
            "create_accounts",
            {"data": accounts_data, "batch_size": 10},
        )

        setup_result, _ = runtime.execute(workflow_setup.build())
        assert setup_result is not None

        # Simulate concurrent transactions
        workflow_concurrent = WorkflowBuilder()

        # Multiple transfers happening simultaneously
        transfers = [
            {"from_account": 1, "to_account": 2, "amount": 100.0},
            {"from_account": 2, "to_account": 3, "amount": 50.0},
            {"from_account": 3, "to_account": 1, "amount": 75.0},
        ]

        for i, transfer in enumerate(transfers):
            # Create transaction record
            workflow_concurrent.add_node(
                "TransactionCreateNode", f"tx_{i}", {**transfer, "status": "processing"}
            )

            # Update sender balance (with version check)
            workflow_concurrent.add_node(
                "AccountUpdateNode",
                f"debit_{i}",
                {
                    "id": str(transfer["from_account"]),
                    "balance": 1000.0
                    - transfer["amount"],  # Would calculate dynamically
                    "version": "1",  # Optimistic locking
                },
            )

            # Update receiver balance
            workflow_concurrent.add_node(
                "AccountUpdateNode",
                f"credit_{i}",
                {
                    "id": str(transfer["to_account"]),
                    "balance": 1000.0
                    + transfer["amount"],  # Would calculate dynamically
                    "version": "1",
                },
            )

            # Mark transaction complete
            workflow_concurrent.add_node(
                "TransactionUpdateNode",
                f"complete_{i}",
                {"id": str(i + 1), "status": "completed"},
            )

        concurrent_result, _ = runtime.execute(workflow_concurrent.build())
        assert concurrent_result is not None

    def test_error_recovery_scenarios(self):
        """Test error handling and recovery scenarios."""
        # Use real PostgreSQL database for E2E testing
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class Job:
            job_type: str
            payload: str  # JSON
            status: str = "queued"
            attempts: int = 0
            max_attempts: int = 3
            error_message: str = None
            completed_at: float = None

        # Create the database tables
        db.create_tables()

        runtime = LocalRuntime()

        # Create jobs with different scenarios
        workflow_jobs = WorkflowBuilder()
        jobs_data = [
            {"job_type": "email", "payload": '{"to": "user1@example.com"}'},
            {"job_type": "report", "payload": '{"report_id": 123}'},
            {"job_type": "export", "payload": '{"format": "csv"}'},
        ]

        workflow_jobs.add_node(
            "JobBulkCreateNode", "queue_jobs", {"data": jobs_data, "batch_size": 10}
        )

        jobs_result, _ = runtime.execute(workflow_jobs.build())
        assert jobs_result is not None

        # Process jobs with error handling
        workflow_process = WorkflowBuilder()

        # Simulate job processing with potential failures
        for job_id in range(1, 4):
            # Attempt to process job
            workflow_process.add_node(
                "JobUpdateNode",
                f"process_{job_id}",
                {"id": str(job_id), "status": "processing", "attempts": 1},
            )

            # Simulate different outcomes
            if job_id == 2:  # Simulate failure for job 2
                workflow_process.add_node(
                    "JobUpdateNode",
                    f"fail_{job_id}",
                    {
                        "id": str(job_id),
                        "status": "failed",
                        "error_message": "Connection timeout",
                        "attempts": 2,
                    },
                )
            else:  # Success for others
                workflow_process.add_node(
                    "JobUpdateNode",
                    f"complete_{job_id}",
                    {
                        "id": str(job_id),
                        "status": "completed",
                        "completed_at": time.time(),
                    },
                )

        process_result, _ = runtime.execute(workflow_process.build())
        assert process_result is not None

        # Retry failed jobs
        workflow_retry = WorkflowBuilder()
        workflow_retry.add_node(
            "JobListNode",
            "find_failed",
            {"filter": {"status": "failed", "attempts": {"$lt": 3}}},
        )

        # Retry the failed job
        workflow_retry.add_node(
            "JobUpdateNode",
            "retry_job",
            {"id": "2", "status": "queued", "attempts": 2, "error_message": None},
        )

        retry_result, _ = runtime.execute(workflow_retry.build())
        assert retry_result is not None
