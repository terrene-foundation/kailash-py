"""
Base class for durable gateway E2E tests with proper test infrastructure.

This module provides:
1. Consistent database setup and teardown
2. Test data fixtures that ensure tests are self-contained
3. Helper methods for common test operations
4. Proper connection management without serialization issues
"""

import asyncio
import json
import random
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import asyncpg
import httpx
import pytest
import pytest_asyncio
from kailash.middleware.gateway.checkpoint_manager import CheckpointManager, DiskStorage
from kailash.middleware.gateway.durable_gateway import DurableAPIGateway
from kailash.workflow.builder import WorkflowBuilder


class DurableGatewayTestBase:
    """Base class for durable gateway E2E tests with proper infrastructure."""

    # Database configuration
    DB_CONFIG = {
        "host": "localhost",
        "port": 5434,
        "database": "kailash_test",
        "user": "test_user",
        "password": "test_password",
    }

    # Test data storage
    _test_customers: List[Dict[str, Any]] = []
    _test_products: List[Dict[str, Any]] = []
    _test_orders: List[Dict[str, Any]] = []

    @pytest.fixture(scope="class", autouse=True)
    def setup_test_data(self):
        """Set up test class with database schema and initial data."""

        async def async_setup():
            conn = await asyncpg.connect(**self.DB_CONFIG)
            try:
                # Create schema
                await self._create_test_schema(conn)
                # Seed test data
                await self._seed_test_data(conn)
            finally:
                await conn.close()

        # Run async setup
        asyncio.run(async_setup())
        yield

        # Cleanup
        async def async_cleanup():
            conn = await asyncpg.connect(**self.DB_CONFIG)
            try:
                await self._cleanup_test_data(conn)
            finally:
                await conn.close()

        asyncio.run(async_cleanup())

    @pytest.fixture(autouse=True)
    def setup_gateway(self):
        """Set up each test method with fresh gateway."""

        async def async_setup():
            self.temp_dir = tempfile.mkdtemp(prefix="kailash_e2e_")
            self.gateway = await self._create_gateway()
            self.port = await self._start_gateway(self.gateway)

        # Run async setup
        asyncio.run(async_setup())
        yield

        # Cleanup
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @classmethod
    async def _create_test_schema(cls, conn: asyncpg.Connection):
        """Create database schema for tests."""
        schemas = [
            # Customers table
            """CREATE TABLE IF NOT EXISTS customers (
                customer_id VARCHAR(50) PRIMARY KEY,
                tenant_id VARCHAR(50) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                first_name VARCHAR(100),
                last_name VARCHAR(100),
                tier VARCHAR(20) DEFAULT 'standard',
                lifetime_value DECIMAL(12,2) DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                status VARCHAR(20) DEFAULT 'active'
            )""",
            # Products table
            """CREATE TABLE IF NOT EXISTS products (
                product_id VARCHAR(50) PRIMARY KEY,
                tenant_id VARCHAR(50) NOT NULL,
                name VARCHAR(200) NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                category VARCHAR(100),
                inventory_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                status VARCHAR(20) DEFAULT 'active'
            )""",
            # Orders table
            """CREATE TABLE IF NOT EXISTS orders (
                order_id VARCHAR(50) PRIMARY KEY,
                customer_id VARCHAR(50) REFERENCES customers(customer_id),
                tenant_id VARCHAR(50) NOT NULL,
                total_amount DECIMAL(12,2) NOT NULL,
                tax_amount DECIMAL(12,2) DEFAULT 0,
                shipping_amount DECIMAL(12,2) DEFAULT 0,
                status VARCHAR(50) NOT NULL,
                payment_status VARCHAR(50),
                items JSONB NOT NULL,
                shipping_address JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            # Content items table
            """CREATE TABLE IF NOT EXISTS content_items (
                content_id VARCHAR(50) PRIMARY KEY,
                content_type VARCHAR(50) NOT NULL,
                title VARCHAR(200),
                body TEXT,
                author_id VARCHAR(50),
                tenant_id VARCHAR(50) NOT NULL,
                moderation_status VARCHAR(50) DEFAULT 'pending',
                moderation_result JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            # Support tickets table
            """CREATE TABLE IF NOT EXISTS support_tickets (
                ticket_id VARCHAR(50) PRIMARY KEY,
                customer_id VARCHAR(50),
                tenant_id VARCHAR(50) NOT NULL,
                subject VARCHAR(200),
                description TEXT,
                priority VARCHAR(20) DEFAULT 'medium',
                status VARCHAR(50) DEFAULT 'open',
                ai_analysis JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            # Additional tables as needed...
        ]

        for schema in schemas:
            await conn.execute(schema)

    @classmethod
    async def _seed_test_data(cls, conn: asyncpg.Connection):
        """Seed database with consistent test data."""
        # Clear existing test data first
        await cls._cleanup_test_data(conn)

        # Create test customers
        for i in range(10):
            customer = {
                "customer_id": f"test_cust_{i:04d}",
                "tenant_id": "test_tenant_1",
                "email": f"customer{i}@test.example.com",
                "first_name": f"Test{i}",
                "last_name": f"Customer{i}",
                "tier": random.choice(["standard", "premium", "enterprise"]),
                "lifetime_value": round(random.uniform(100, 10000), 2),
            }
            cls._test_customers.append(customer)

            await conn.execute(
                """
                INSERT INTO customers
                (customer_id, tenant_id, email, first_name, last_name, tier, lifetime_value)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (customer_id) DO NOTHING
            """,
                *customer.values(),
            )

        # Create test products with sufficient inventory
        categories = ["Electronics", "Clothing", "Books", "Home", "Sports"]
        for i in range(20):
            product = {
                "product_id": f"test_prod_{i:04d}",
                "tenant_id": "test_tenant_1",
                "name": f"Test Product {i}",
                "price": round(random.uniform(10, 500), 2),
                "category": random.choice(categories),
                "inventory_count": random.randint(
                    50, 200
                ),  # Ensure sufficient inventory
            }
            cls._test_products.append(product)

            await conn.execute(
                """
                INSERT INTO products
                (product_id, tenant_id, name, price, category, inventory_count)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (product_id) DO NOTHING
            """,
                *product.values(),
            )

        # Create test content items
        for i in range(15):
            await conn.execute(
                """
                INSERT INTO content_items
                (content_id, content_type, title, body, author_id, tenant_id, moderation_status)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (content_id) DO NOTHING
            """,
                f"test_content_{i:04d}",
                random.choice(["post", "comment", "review"]),
                f"Test Content {i}",
                f"This is test content body {i}. " * 10,
                f"test_author_{i % 5}",
                "test_tenant_1",
                "pending" if i < 10 else "approved",
            )

    @classmethod
    async def _cleanup_test_data(cls, conn: asyncpg.Connection):
        """Clean up test data."""
        # Delete in reverse order of foreign key dependencies
        await conn.execute("DELETE FROM orders WHERE order_id LIKE 'test_%'")
        await conn.execute("DELETE FROM support_tickets WHERE ticket_id LIKE 'test_%'")
        await conn.execute("DELETE FROM content_items WHERE content_id LIKE 'test_%'")
        await conn.execute("DELETE FROM products WHERE product_id LIKE 'test_%'")
        await conn.execute("DELETE FROM customers WHERE customer_id LIKE 'test_%'")

    async def _create_gateway(self) -> DurableAPIGateway:
        """Create a properly configured gateway instance."""
        checkpoint_manager = CheckpointManager(
            disk_storage=DiskStorage(self.temp_dir),
            retention_hours=48,
            compression_enabled=True,
        )

        gateway = DurableAPIGateway(
            title="Test E2E Gateway",
            enable_durability=True,
            checkpoint_manager=checkpoint_manager,
            durability_opt_in=False,
        )

        # Register workflows
        await self._register_test_workflows(gateway)

        return gateway

    async def _start_gateway(self, gateway: DurableAPIGateway) -> int:
        """Start the gateway and return the port."""
        port = random.randint(10000, 10999)

        server_thread = threading.Thread(
            target=lambda: gateway.run(host="localhost", port=port), daemon=True
        )
        server_thread.start()

        # Wait for gateway to start
        await self._wait_for_gateway(port)

        return port

    async def _wait_for_gateway(self, port: int, timeout: float = 10.0):
        """Wait for gateway to be ready."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"http://localhost:{port}/health", timeout=1.0
                    )
                    if response.status_code == 200:
                        return
            except:
                await asyncio.sleep(0.5)

        raise TimeoutError(f"Gateway did not start within {timeout} seconds")

    async def _register_test_workflows(self, gateway: DurableAPIGateway):
        """Register test workflows. Override in subclasses."""
        pass

    # Helper methods for tests

    def get_test_customer(self, index: int = 0) -> Dict[str, Any]:
        """Get a test customer by index."""
        return self._test_customers[index % len(self._test_customers)]

    def get_test_product(self, index: int = 0) -> Dict[str, Any]:
        """Get a test product by index."""
        return self._test_products[index % len(self._test_products)]

    def get_random_test_customer(self) -> Dict[str, Any]:
        """Get a random test customer."""
        return random.choice(self._test_customers)

    def get_random_test_products(self, count: int = 3) -> List[Dict[str, Any]]:
        """Get random test products."""
        return random.sample(self._test_products, min(count, len(self._test_products)))

    async def create_test_order(
        self, customer_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a test order with valid customer and products."""
        if not customer_id:
            customer = self.get_random_test_customer()
            customer_id = customer["customer_id"]

        products = self.get_random_test_products(random.randint(1, 3))

        items = []
        subtotal = 0
        for product in products:
            quantity = random.randint(1, 3)
            item = {
                "product_id": product["product_id"],
                "name": product["name"],
                "price": float(product["price"]),
                "quantity": quantity,
            }
            items.append(item)
            subtotal += item["price"] * quantity

        order_data = {
            "customer_id": customer_id,
            "tenant_id": "test_tenant_1",
            "items": items,
            "shipping_address": {
                "street": "123 Test St",
                "city": "Test City",
                "state": "TC",
                "zip": "12345",
                "country": "US",
            },
            "currency": "USD",
        }

        return order_data

    @staticmethod
    def create_db_connection_code() -> str:
        """Generate AsyncPythonCodeNode code for database connection."""
        return """
import asyncpg

# Create database connection
conn = await asyncpg.connect(
    host="localhost",
    port=5434,
    database="kailash_test",
    user="test_user",
    password="test_password"
)

try:
    # Your database operations here
    pass
finally:
    await conn.close()
"""
