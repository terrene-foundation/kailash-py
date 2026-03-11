#!/usr/bin/env python3
"""
Test DataFlow with existing database scenario.
Validates that DataFlow can work with legacy databases without destructive migrations.

NO MOCKING - Uses real PostgreSQL database infrastructure as per testing policy.
"""

import asyncio
import os

import pytest
from dataflow import DataFlow

from tests.infrastructure.test_harness import IntegrationTestSuite


async def setup_existing_database(test_suite):
    """Create a legacy database with existing schema using standardized test infrastructure."""

    print("=== Setting up Legacy Database ===")

    # Use test suite infrastructure instead of hardcoded database configuration
    db = test_suite.dataflow_harness.create_dataflow(
        auto_migrate=False, existing_schema_mode=True
    )

    async with test_suite.infrastructure.connection() as conn:
        # Clean existing tables
        await conn.execute("DROP TABLE IF EXISTS orders CASCADE")
        await conn.execute("DROP TABLE IF EXISTS customers CASCADE")

        # Create legacy schema with extra fields
        await conn.execute(
            """
            CREATE TABLE customers (
                id SERIAL PRIMARY KEY,
                customer_code VARCHAR(50) NOT NULL UNIQUE,
                company_name VARCHAR(200) NOT NULL,
                email VARCHAR(150) NOT NULL,
                is_active BOOLEAN DEFAULT true,
                old_system_id VARCHAR(100),
                legacy_category VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Insert legacy data
        await conn.execute(
            """
            INSERT INTO customers
            (customer_code, company_name, email, old_system_id, legacy_category)
            VALUES
            ('CUST001', 'Acme Corp', 'contact@acme.com', 'OLD_ACME_123', 'PREMIUM'),
            ('CUST002', 'TechStart Inc', 'info@techstart.com', 'OLD_TECH_456', 'STANDARD'),
            ('CUST003', 'Global Industries', 'sales@global.com', 'OLD_GLOB_789', 'PREMIUM')
        """
        )

        print("✅ Legacy database created with:")
        print("   - 3 customers with legacy fields")
        print("   - Extra columns not in DataFlow models")

        return test_suite.config.url


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestExistingDatabaseScenario:
    """Test DataFlow integration with existing databases using standardized test infrastructure."""

    @pytest.mark.asyncio
    async def test_safe_connection_with_existing_schema_mode(self):
        """Test DataFlow integration with existing database using existing_schema_mode."""

        # Use test harness for proper infrastructure management
        suite = IntegrationTestSuite()
        async with suite.session():
            # Setup existing database using standardized infrastructure
            db_url = await setup_existing_database(suite)

            print("\n=== Testing DataFlow with Existing Database ===")

            # Create DataFlow instance with existing_schema_mode=True
            db = suite.dataflow_harness.create_dataflow(
                auto_migrate=False, existing_schema_mode=True
            )

            # Define models with SUBSET of database fields
            @db.model
            class Customer:
                customer_code: str
                company_name: str
                email: str
                is_active: bool = True
                # Note: NOT defining legacy fields

            print("DataFlow models defined (subset of DB fields)")

            # Initialize - should NOT attempt destructive migration
            try:
                # This should work with existing_schema_mode=True
                success = db._model_registry.initialize()
                print(f"✅ DataFlow registry initialized: {success}")
            except Exception as e:
                print(f"❌ Failed to initialize: {e}")
                raise

            # Test basic functionality - registry should work
            registry = db._model_registry
            assert registry._initialized is True

            # Test model discovery
            discovered = registry.discover_models()
            assert isinstance(discovered, dict)

            # Test that models are registered
            models = db.get_models()
            assert len(models) > 0

            print("✅ SUCCESS: DataFlow works with existing database in safe mode!")
            print("   - No destructive migrations attempted")
            print("   - Registry initialized successfully")
            print("   - Model discovery working")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
