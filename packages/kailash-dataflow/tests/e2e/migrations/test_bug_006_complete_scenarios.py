#!/usr/bin/env python3
"""
End-to-end tests for Bug 006: Destructive Auto-Migration.
Tests complete user scenarios with real infrastructure.
"""

import asyncio
import os

import psycopg2
import pytest
from dataflow import DataFlow
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


@pytest.mark.e2e
@pytest.mark.timeout(10)
class TestBug006CompleteScenarios:
    """Test complete Bug 006 scenarios with real infrastructure."""

    @pytest.fixture
    async def test_database(self):
        """Create a test database for E2E tests."""
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = os.getenv("DB_PORT", "5432")
        db_user = os.getenv("DB_USER", "postgres")
        db_password = os.getenv("DB_PASSWORD", "postgres")
        test_db = "test_bug006_e2e"

        # Create test database
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database="postgres",
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        cursor.execute(f"DROP DATABASE IF EXISTS {test_db}")
        cursor.execute(f"CREATE DATABASE {test_db}")

        cursor.close()
        conn.close()

        db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{test_db}"

        yield db_url

        # Cleanup
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database="postgres",
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        cursor.execute(f"DROP DATABASE IF EXISTS {test_db}")
        cursor.close()
        conn.close()

    @pytest.mark.asyncio
    async def test_scenario_1_development_to_production(self, test_database):
        """
        Scenario 1: Developer creates app in development, deploys to production.
        Production database must be protected from auto-migration.
        """
        # Phase 1: Development - migrations enabled
        dev_db = DataFlow(test_database, auto_migrate=True)  # Development mode

        @dev_db.model
        class User:
            username: str
            email: str
            is_active: bool = True

        @dev_db.model
        class Product:
            name: str
            price: float
            stock: int = 0

        # Create some test data
        user_create = dev_db.get_node("UserCreateNode")
        await user_create.execute({"username": "testuser", "email": "test@example.com"})

        product_create = dev_db.get_node("ProductCreateNode")
        await product_create.execute(
            {"name": "Test Product", "price": 99.99, "stock": 100}
        )

        # Phase 2: Production deployment - migrations disabled
        prod_db = DataFlow(
            test_database,
            auto_migrate=False,  # Production safety
            existing_schema_mode=True,  # Validate compatibility
        )

        # Same models in production
        @prod_db.model
        class User:
            username: str
            email: str
            is_active: bool = True

        @prod_db.model
        class Product:
            name: str
            price: float
            stock: int = 0

        # Verify data is preserved
        user_list = prod_db.get_node("UserListNode")
        users = await user_list.execute({})
        assert len(users["records"]) == 1
        assert users["records"][0]["username"] == "testuser"

        product_list = prod_db.get_node("ProductListNode")
        products = await product_list.execute({})
        assert len(products["records"]) == 1
        assert products["records"][0]["name"] == "Test Product"

    @pytest.mark.asyncio
    async def test_scenario_2_multiple_microservices(self, test_database):
        """
        Scenario 2: Multiple microservices sharing same database.
        Only first service creates schema, others use existing.
        """
        # Service 1: User Service (creates schema)
        user_service = DataFlow(
            test_database, auto_migrate=True
        )  # First service can migrate

        @user_service.model
        class User:
            username: str
            email: str
            role: str = "user"

        # Create admin user
        await user_service.get_node("UserCreateNode").execute(
            {"username": "admin", "email": "admin@example.com", "role": "admin"}
        )

        # Service 2: Auth Service (uses existing schema)
        auth_service = DataFlow(
            test_database,
            auto_migrate=False,  # Don't migrate
            existing_schema_mode=True,  # Validate only
        )

        @auth_service.model
        class User:
            username: str
            email: str
            role: str = "user"

        # Auth service can read users created by user service
        users = await auth_service.get_node("UserListNode").execute(
            {"filters": {"role": "admin"}}
        )
        assert len(users["records"]) == 1
        assert users["records"][0]["username"] == "admin"

        # Service 3: Reporting Service (read-only subset)
        reporting_service = DataFlow(
            test_database, auto_migrate=False, existing_schema_mode=True
        )

        @reporting_service.model
        class User:
            # Only needs subset of fields
            username: str
            role: str

        # Can still query with limited model
        all_users = await reporting_service.get_node("UserListNode").execute({})
        assert len(all_users["records"]) == 1

    @pytest.mark.asyncio
    async def test_scenario_3_legacy_database_integration(self, test_database):
        """
        Scenario 3: Integrating with existing legacy database.
        DataFlow must work with existing schema without modifications.
        """
        # First, create a "legacy" database schema manually
        conn = psycopg2.connect(test_database)
        cursor = conn.cursor()

        # Create legacy schema with extra fields
        cursor.execute(
            """
            CREATE TABLE customers (
                id SERIAL PRIMARY KEY,
                customer_code VARCHAR(50) UNIQUE NOT NULL,
                company_name VARCHAR(200) NOT NULL,
                contact_email VARCHAR(150) NOT NULL,
                contact_phone VARCHAR(50),
                address_line1 VARCHAR(200),
                address_line2 VARCHAR(200),
                city VARCHAR(100),
                state VARCHAR(50),
                postal_code VARCHAR(20),
                country VARCHAR(50),
                legacy_system_id VARCHAR(100),
                import_date TIMESTAMP,
                last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                internal_notes TEXT,
                credit_limit DECIMAL(10,2),
                payment_terms INTEGER,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Insert legacy data
        cursor.execute(
            """
            INSERT INTO customers
            (customer_code, company_name, contact_email, legacy_system_id, credit_limit)
            VALUES
            ('CUST001', 'Acme Corp', 'contact@acme.com', 'LEG_123', 50000.00),
            ('CUST002', 'Tech Industries', 'info@tech.com', 'LEG_456', 75000.00)
        """
        )

        conn.commit()
        cursor.close()
        conn.close()

        # Now connect with DataFlow - should NOT destroy existing data
        db = DataFlow(
            test_database,
            auto_migrate=False,  # Critical: no auto-migration
            existing_schema_mode=True,  # Validate compatibility
        )

        # Model only the fields we need
        @db.model
        class Customer:
            customer_code: str
            company_name: str
            contact_email: str
            is_active: bool = True

        # Verify we can read existing data
        customer_list = db.get_node("CustomerListNode")
        customers = await customer_list.execute({})

        assert len(customers["records"]) == 2
        assert customers["records"][0]["customer_code"] == "CUST001"
        assert customers["records"][0]["company_name"] == "Acme Corp"

        # Verify we can create new records (legacy fields get defaults)
        customer_create = db.get_node("CustomerCreateNode")
        new_customer = await customer_create.execute(
            {
                "customer_code": "CUST003",
                "company_name": "New Customer Inc",
                "contact_email": "new@customer.com",
            }
        )

        assert new_customer["customer_code"] == "CUST003"

        # Verify legacy fields are preserved
        conn = psycopg2.connect(test_database)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT legacy_system_id, credit_limit FROM customers WHERE customer_code = %s",
            ("CUST001",),
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        assert row[0] == "LEG_123"  # Legacy ID preserved
        assert float(row[1]) == 50000.00  # Credit limit preserved

    @pytest.mark.asyncio
    async def test_scenario_4_gradual_migration(self, test_database):
        """
        Scenario 4: Gradual migration from legacy to new system.
        Both systems must coexist during transition period.
        """
        # Phase 1: Legacy system creates initial schema
        conn = psycopg2.connect(test_database)
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE orders (
                order_id SERIAL PRIMARY KEY,
                order_number VARCHAR(50) UNIQUE NOT NULL,
                customer_name VARCHAR(200) NOT NULL,
                order_date DATE NOT NULL,
                total_amount DECIMAL(10,2) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                legacy_data JSONB
            )
        """
        )

        # Legacy system inserts data
        cursor.execute(
            """
            INSERT INTO orders
            (order_number, customer_name, order_date, total_amount, status, legacy_data)
            VALUES
            ('ORD-001', 'Customer A', '2024-01-01', 1000.00, 'completed', '{"source": "legacy"}'),
            ('ORD-002', 'Customer B', '2024-01-02', 2000.00, 'pending', '{"source": "legacy"}')
        """
        )

        conn.commit()
        cursor.close()
        conn.close()

        # Phase 2: New DataFlow system connects
        new_system = DataFlow(
            test_database, auto_migrate=False, existing_schema_mode=True
        )

        @new_system.model
        class Order:
            order_number: str
            customer_name: str
            order_date: str  # Will handle date conversion
            total_amount: float
            status: str = "pending"

        # New system can read legacy orders
        orders = await new_system.get_node("OrderListNode").execute({})
        assert len(orders["records"]) == 2

        # New system creates new orders (legacy_data will be null)
        await new_system.get_node("OrderCreateNode").execute(
            {
                "order_number": "ORD-003",
                "customer_name": "Customer C",
                "order_date": "2024-01-03",
                "total_amount": 3000.00,
                "status": "pending",
            }
        )

        # Both systems can coexist
        conn = psycopg2.connect(test_database)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orders")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()

        assert count == 3  # 2 legacy + 1 new


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
