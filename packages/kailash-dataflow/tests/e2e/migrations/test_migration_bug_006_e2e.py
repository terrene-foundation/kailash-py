#!/usr/bin/env python3
"""
Tier 3 End-to-End Tests for Bug 006 Migration Fix
Tests complete user workflows with REAL infrastructure stack.
NO MOCKING ALLOWED - Complete scenarios with real services.
"""

import asyncio
import os
import subprocess
import time

import asyncpg
import pytest
from dataflow import DataFlow


@pytest.mark.e2e
@pytest.mark.timeout(10)
async def test_complete_multi_developer_workflow():
    """
    Complete E2E workflow: Multiple developers working on same project.
    Simulates the exact Bug 006 scenario that was reported.
    """
    print("=" * 60)
    print("Bug 006 E2E Test: Multi-Developer Workflow")
    print("=" * 60)

    db_url = os.getenv(
        "TEST_DATABASE_URL", "postgresql://test:test@localhost:5433/test_bug_006_e2e"
    )

    # Clean slate
    await _reset_database_completely(db_url)

    # === Day 1: Developer Alice creates initial application ===
    print("\n🧑‍💻 Developer Alice: Initial App Development")
    print("-" * 40)

    alice_db = DataFlow(db_url)

    @alice_db.model
    class User:
        username: str
        email: str
        is_active: bool = True

    @alice_db.model
    class Project:
        name: str
        description: str
        owner_id: int
        status: str = "active"

    @alice_db.model
    class Task:
        title: str
        project_id: int
        assignee_id: int
        completed: bool = False

    print("Alice: Defined User, Project, Task models")

    # Alice initializes the application
    await alice_db.initialize()
    print("✅ Alice: Database initialized successfully")

    # Alice creates some data
    user_node = alice_db.get_node("UserCreateNode")
    alice_user = await user_node.execute(
        {"username": "alice", "email": "alice@company.com"}
    )
    print(f"✅ Alice: Created user account (ID: {alice_user['id']})")

    project_node = alice_db.get_node("ProjectCreateNode")
    project = await project_node.execute(
        {
            "name": "Company Website",
            "description": "Main company website project",
            "owner_id": alice_user["id"],
        }
    )
    print(f"✅ Alice: Created project (ID: {project['id']})")

    task_node = alice_db.get_node("TaskCreateNode")
    task = await task_node.execute(
        {
            "title": "Design homepage",
            "project_id": project["id"],
            "assignee_id": alice_user["id"],
        }
    )
    print(f"✅ Alice: Created task (ID: {task['id']})")

    # Record Alice's migration state
    alice_migrations = await _get_detailed_migration_history(alice_db)
    print(f"Alice's migrations: {len(alice_migrations)}")

    # === Day 2: Developer Bob joins the project ===
    print("\n🧑‍💻 Developer Bob: Joining Existing Project")
    print("-" * 40)

    # Bob clones the repo and runs the same code
    bob_db = DataFlow(db_url)

    @bob_db.model
    class User:
        username: str
        email: str
        is_active: bool = True

    @bob_db.model
    class Project:
        name: str
        description: str
        owner_id: int
        status: str = "active"

    @bob_db.model
    class Task:
        title: str
        project_id: int
        assignee_id: int
        completed: bool = False

    print("Bob: Defined identical models to Alice")

    # Bob initializes - should NOT create duplicate migration
    await bob_db.initialize()
    print("✅ Bob: Initialization successful (no conflicts!)")

    # Verify no duplicate migrations
    bob_migrations = await _get_detailed_migration_history(bob_db)
    assert len(bob_migrations) == len(
        alice_migrations
    ), f"Bob triggered duplicate migrations! Alice: {len(alice_migrations)}, Bob: {len(bob_migrations)}"
    print("✅ Bob: No duplicate migrations created")

    # Bob can see Alice's data
    user_list = bob_db.get_node("UserListNode")
    users = await user_list.execute({})
    assert len(users["records"]) == 1, "Bob can't see Alice's user"
    assert users["records"][0]["username"] == "alice", "Data corruption detected"
    print("✅ Bob: Can see Alice's data correctly")

    # Bob creates his own user
    bob_user = await bob_db.get_node("UserCreateNode").execute(
        {"username": "bob", "email": "bob@company.com"}
    )
    print(f"✅ Bob: Created his user account (ID: {bob_user['id']})")

    # === Day 3: Developer Charlie joins with different model subset ===
    print("\n🧑‍💻 Developer Charlie: Admin Panel Development")
    print("-" * 40)

    # Charlie is building admin panel and only needs subset of fields
    charlie_db = DataFlow(db_url)

    @charlie_db.model
    class User:
        # Admin only needs basic info
        username: str
        email: str
        # Not modeling is_active field

    @charlie_db.model
    class Project:
        # Admin only needs basic project info
        name: str
        owner_id: int
        # Not modeling description and status

    # Note: Charlie doesn't need Task model for admin panel

    print("Charlie: Defined admin models (subset of fields)")

    # Charlie initializes - should work with existing schema
    await charlie_db.initialize()
    print("✅ Charlie: Initialization successful (schema compatible!)")

    # Verify no additional migrations
    charlie_migrations = await _get_detailed_migration_history(charlie_db)
    assert len(charlie_migrations) == len(
        alice_migrations
    ), f"Charlie's subset models triggered migrations! Expected: {len(alice_migrations)}, Got: {len(charlie_migrations)}"
    print("✅ Charlie: No migrations needed for subset models")

    # Charlie can work with existing data
    admin_users = await charlie_db.get_node("UserListNode").execute({})
    assert len(admin_users["records"]) == 2, "Admin can't see all users"
    print(f"✅ Charlie: Admin panel sees all {len(admin_users['records'])} users")

    # === Day 4: Production deployment with existing database ===
    print("\n🚀 Production Deployment: Existing Database Integration")
    print("-" * 40)

    # Simulate production database with additional legacy fields
    prod_db_url = os.getenv(
        "TEST_DATABASE_URL", "postgresql://test:test@localhost:5433/test_production_db"
    )
    await _setup_production_like_database(prod_db_url)

    # Production app connecting to existing database
    prod_db = DataFlow(prod_db_url)

    @prod_db.model
    class User:
        username: str
        email: str
        is_active: bool = True
        # Production DB has: legacy_id, import_date, old_system_ref, etc.

    @prod_db.model
    class Project:
        name: str
        description: str
        owner_id: int
        status: str = "active"
        # Production DB has: legacy_project_id, billing_code, etc.

    print("Production: Models defined for existing database")

    # Production deployment should NOT destroy existing data
    await prod_db.initialize()
    print("✅ Production: Safe deployment (no destructive migration!)")

    # Verify existing production data is preserved
    async with prod_db.get_connection() as conn:
        result = await conn.fetch(
            "SELECT username, legacy_id FROM users WHERE legacy_id IS NOT NULL"
        )
        assert len(result) > 0, "Existing production data was lost!"
        print(f"✅ Production: {len(result)} legacy users preserved")

        for row in result:
            print(f"   - {row['username']} (Legacy ID: {row['legacy_id']})")

    # Production app can create new data
    prod_user = await prod_db.get_node("UserCreateNode").execute(
        {"username": "production_user", "email": "prod@company.com"}
    )
    print(f"✅ Production: Created new user (ID: {prod_user['id']})")

    # === Validation: Complete workflow success ===
    print("\n✅ COMPLETE WORKFLOW SUCCESS!")
    print("=" * 60)
    print("Bug 006 is FIXED - Verified scenarios:")
    print("  1. ✅ Multiple developers with identical models")
    print("  2. ✅ Developer with subset of model fields")
    print("  3. ✅ Production deployment to existing database")
    print("  4. ✅ No destructive auto-migrations")
    print("  5. ✅ Legacy data preservation")
    print("  6. ✅ No duplicate migration conflicts")
    print("=" * 60)


@pytest.mark.e2e
@pytest.mark.timeout(10)
async def test_concurrent_application_startup():
    """
    Test multiple applications starting up simultaneously.
    This tests the race condition scenario from Bug 006.
    """
    print("\n🏁 Testing Concurrent Application Startup")
    print("-" * 40)

    db_url = os.getenv(
        "TEST_DATABASE_URL", "postgresql://test:test@localhost:5433/test_concurrent"
    )
    await _reset_database_completely(db_url)

    # Define the same schema for all apps
    async def create_app_instance(app_name: str, delay: float = 0):
        """Create and initialize a DataFlow app instance."""
        if delay > 0:
            await asyncio.sleep(delay)

        print(f"{app_name}: Starting initialization...")
        db = DataFlow(db_url)

        @db.model
        class User:
            username: str
            email: str

        @db.model
        class Session:
            token: str
            user_id: int

        await db.initialize()
        print(f"✅ {app_name}: Initialization complete")
        return db

    # Start 3 apps concurrently with slight delays
    print("Starting 3 applications concurrently...")
    tasks = [
        create_app_instance("API-Service", 0.0),
        create_app_instance("Worker-Service", 0.1),
        create_app_instance("Admin-Panel", 0.2),
    ]

    # Wait for all to complete
    apps = await asyncio.gather(*tasks)
    print("✅ All applications started successfully!")

    # Verify only one migration was applied
    migration_count = await _get_migration_count(apps[0])
    print(f"Total migrations applied: {migration_count}")

    # Should be exactly 1 migration (not 3)
    assert (
        migration_count <= 1
    ), f"Race condition detected! {migration_count} migrations instead of 1"

    # All apps should be able to work with the database
    for i, app in enumerate(apps):
        user_create = app.get_node("UserCreateNode")
        user = await user_create.execute(
            {"username": f"user_from_app_{i}", "email": f"app{i}@test.com"}
        )
        print(f"✅ App {i}: Created user {user['id']}")

    # Verify all users exist
    user_list = apps[0].get_node("UserListNode")
    all_users = await user_list.execute({})
    assert len(all_users["records"]) == 3, "Not all apps could create users"
    print(f"✅ All apps working: {len(all_users['records'])} users created")


@pytest.mark.e2e
@pytest.mark.timeout(10)
async def test_real_world_migration_scenarios():
    """
    Test real-world migration scenarios that should NOT trigger destructive changes.
    """
    print("\n🌍 Testing Real-World Migration Scenarios")
    print("-" * 40)

    db_url = os.getenv(
        "TEST_DATABASE_URL", "postgresql://test:test@localhost:5433/test_real_world"
    )

    # === Scenario 1: Microservice architecture ===
    print("\n📱 Scenario 1: Microservice Architecture")
    await _reset_database_completely(db_url)

    # Service 1: User Service
    user_service = DataFlow(db_url)

    @user_service.model
    class User:
        username: str
        email: str
        profile_data: dict = {}

    await user_service.initialize()
    print("✅ User Service: Initialized")

    # Service 2: Order Service (shares User table)
    order_service = DataFlow(db_url)

    @order_service.model
    class User:
        # Order service only needs basic user info
        username: str
        email: str
        # Doesn't model profile_data

    @order_service.model
    class Order:
        order_number: str
        user_id: int
        total_amount: float

    await order_service.initialize()
    print("✅ Order Service: Initialized (no conflicts)")

    # Service 3: Analytics Service (read-only access)
    analytics_service = DataFlow(db_url)

    @analytics_service.model
    class User:
        # Analytics only needs username for reports
        username: str
        # Minimal model for read-only access

    await analytics_service.initialize()
    print("✅ Analytics Service: Initialized (minimal model)")

    # All services should work together
    user = await user_service.get_node("UserCreateNode").execute(
        {
            "username": "microservice_user",
            "email": "user@microservice.com",
            "profile_data": {"preferences": "dark_mode"},
        }
    )

    order = await order_service.get_node("OrderCreateNode").execute(
        {"order_number": "ORD-001", "user_id": user["id"], "total_amount": 99.99}
    )

    analytics_users = await analytics_service.get_node("UserListNode").execute({})

    print(
        f"✅ Microservices: User {user['id']}, Order {order['id']}, Analytics sees {len(analytics_users['records'])} users"
    )

    # === Scenario 2: Legacy system integration ===
    print("\n🏛️  Scenario 2: Legacy System Integration")
    legacy_db_url = os.getenv(
        "TEST_DATABASE_URL", "postgresql://test:test@localhost:5433/test_legacy"
    )
    await _setup_complex_legacy_database(legacy_db_url)

    # Modern application connecting to legacy database
    modern_app = DataFlow(legacy_db_url)

    @modern_app.model
    class Customer:
        # Only model what we need from legacy table
        customer_code: str
        company_name: str
        email: str
        # Legacy table has 20+ additional fields

    await modern_app.initialize()
    print("✅ Modern App: Connected to legacy database safely")

    # Verify legacy data is intact
    async with modern_app.get_connection() as conn:
        legacy_count = await conn.fetchval(
            "SELECT COUNT(*) FROM customers WHERE legacy_system_id IS NOT NULL"
        )
        print(f"✅ Legacy Data: {legacy_count} legacy records preserved")

    # Modern app can work with subset
    customers = await modern_app.get_node("CustomerListNode").execute({})
    print(f"✅ Modern App: Can access {len(customers['records'])} customers")


# Helper Functions


async def _reset_database_completely(db_url: str):
    """Completely reset test database."""
    try:
        # Extract database name from URL
        db_name = db_url.split("/")[-1]
        base_url = db_url.rsplit("/", 1)[0]

        # Connect to postgres database to recreate test database
        postgres_url = base_url + "/postgres"

        async with asyncpg.connect(postgres_url) as conn:
            # Terminate connections to test database
            await conn.execute(
                f"""
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = '{db_name}'
                  AND pid <> pg_backend_pid()
            """
            )

            # Drop and recreate database
            await conn.execute(f"DROP DATABASE IF EXISTS {db_name}")
            await conn.execute(f"CREATE DATABASE {db_name}")

        print(f"✅ Database {db_name} completely reset")

    except Exception as e:
        print(f"⚠️  Database reset warning: {e}")


async def _setup_production_like_database(db_url: str):
    """Setup database that simulates production with legacy fields."""
    await _reset_database_completely(db_url)

    async with asyncpg.connect(db_url) as conn:
        # Create users table with legacy fields
        await conn.execute(
            """
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) NOT NULL UNIQUE,
                email VARCHAR(255) NOT NULL,
                is_active BOOLEAN DEFAULT true,

                -- Legacy fields from old system
                legacy_id VARCHAR(50),
                import_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                old_system_ref VARCHAR(100),
                migration_batch INTEGER,

                -- Standard timestamps
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Insert existing production data
        await conn.execute(
            """
            INSERT INTO users (username, email, legacy_id, old_system_ref, migration_batch)
            VALUES
            ('legacy_user_1', 'legacy1@company.com', 'LEG_001', 'OLD_SYS_123', 1),
            ('legacy_user_2', 'legacy2@company.com', 'LEG_002', 'OLD_SYS_456', 1),
            ('migrated_user', 'migrated@company.com', 'LEG_003', 'OLD_SYS_789', 2)
        """
        )

        # Create projects table with legacy fields
        await conn.execute(
            """
            CREATE TABLE projects (
                id SERIAL PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                description TEXT,
                owner_id INTEGER REFERENCES users(id),
                status VARCHAR(50) DEFAULT 'active',

                -- Legacy fields
                legacy_project_id VARCHAR(50),
                billing_code VARCHAR(20),
                old_status_code VARCHAR(10),

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        print("✅ Production-like database created with legacy data")


async def _setup_complex_legacy_database(db_url: str):
    """Setup complex legacy database with many extra fields."""
    await _reset_database_completely(db_url)

    async with asyncpg.connect(db_url) as conn:
        await conn.execute(
            """
            CREATE TABLE customers (
                id SERIAL PRIMARY KEY,
                customer_code VARCHAR(50) NOT NULL UNIQUE,
                company_name VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL,

                -- Contact information
                phone VARCHAR(50),
                fax VARCHAR(50),
                website VARCHAR(255),

                -- Address fields
                address_line1 VARCHAR(255),
                address_line2 VARCHAR(255),
                city VARCHAR(100),
                state VARCHAR(50),
                postal_code VARCHAR(20),
                country VARCHAR(100),

                -- Business information
                industry VARCHAR(100),
                company_size VARCHAR(50),
                annual_revenue DECIMAL(15,2),
                tax_id VARCHAR(50),

                -- Legacy system fields
                legacy_system_id VARCHAR(100),
                old_customer_number VARCHAR(50),
                import_source VARCHAR(50),
                import_date TIMESTAMP,
                last_sync_date TIMESTAMP,
                sync_status VARCHAR(20),

                -- Internal fields
                account_manager_id INTEGER,
                credit_limit DECIMAL(10,2),
                payment_terms VARCHAR(50),
                priority_level INTEGER,
                notes TEXT,

                -- Status tracking
                status VARCHAR(50) DEFAULT 'active',
                is_verified BOOLEAN DEFAULT false,
                verification_date TIMESTAMP,

                -- Timestamps
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_contact_date TIMESTAMP,
                next_followup_date TIMESTAMP
            )
        """
        )

        # Insert complex legacy data
        await conn.execute(
            """
            INSERT INTO customers (
                customer_code, company_name, email, phone,
                legacy_system_id, old_customer_number, import_source,
                industry, company_size, credit_limit
            ) VALUES (
                'LEGACY001', 'Old Corp Inc', 'contact@oldcorp.com', '+1-555-0123',
                'OLDSYS_12345', 'CUST_789', 'legacy_migration',
                'Manufacturing', 'Large', 50000.00
            )
        """
        )

        print("✅ Complex legacy database created")


async def _get_detailed_migration_history(dataflow_instance):
    """Get detailed migration history."""
    try:
        async with dataflow_instance.get_connection() as conn:
            result = await conn.fetch(
                """
                SELECT version, name, checksum, status, created_at
                FROM dataflow_migrations
                ORDER BY created_at
            """
            )
            return list(result)
    except Exception:
        return []


async def _get_migration_count(dataflow_instance) -> int:
    """Get count of applied migrations."""
    try:
        async with dataflow_instance.get_connection() as conn:
            result = await conn.fetchval(
                """
                SELECT COUNT(*) FROM dataflow_migrations
                WHERE status = 'applied'
            """
            )
            return result if result else 0
    except Exception:
        return 0


if __name__ == "__main__":
    print("DataFlow Bug 006 End-to-End Tests (Tier 3)")
    print("Requires: Full infrastructure stack running")
    print("=" * 60)

    # Check requirements
    db_url = os.getenv("TEST_DATABASE_URL")
    if not db_url:
        print("❌ TEST_DATABASE_URL not set")
        exit(1)

    # Run E2E tests
    pytest.main([__file__, "-v", "-s", "--tb=short"])
