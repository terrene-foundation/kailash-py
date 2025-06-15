#!/usr/bin/env python3
"""Example of using the database migration framework.

This example demonstrates:
- Creating migrations
- Running migrations
- Rolling back migrations
- Checking migration status
"""

import asyncio
import os
from pathlib import Path

from kailash.utils.migrations import Migration, MigrationGenerator, MigrationRunner


# Example migrations
class CreateUsersTable(Migration):
    """Create users table for authentication."""

    id = "001_create_users_table"
    description = "Create users table with basic fields"
    dependencies = []

    async def forward(self, connection):
        """Create users table."""
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                username VARCHAR(100) UNIQUE NOT NULL,
                full_name VARCHAR(255),
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create indexes
        await connection.execute(
            """
            CREATE INDEX idx_users_email ON users(email);
            CREATE INDEX idx_users_username ON users(username);
            CREATE INDEX idx_users_active ON users(is_active) WHERE is_active = true;
        """
        )

    async def backward(self, connection):
        """Drop users table."""
        await connection.execute("DROP TABLE IF EXISTS users CASCADE")


class CreateWorkflowTables(Migration):
    """Create workflow execution tracking tables."""

    id = "002_create_workflow_tables"
    description = "Create tables for workflow execution tracking"
    dependencies = ["001_create_users_table"]

    async def forward(self, connection):
        """Create workflow tables."""
        # Workflows table
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS workflows (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                version VARCHAR(50),
                description TEXT,
                created_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Workflow executions table
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_executions (
                id SERIAL PRIMARY KEY,
                workflow_id INTEGER REFERENCES workflows(id),
                user_id INTEGER REFERENCES users(id),
                status VARCHAR(50) NOT NULL,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                metadata JSONB
            )
        """
        )

        # Create indexes
        await connection.execute(
            """
            CREATE INDEX idx_workflow_name ON workflows(name);
            CREATE INDEX idx_execution_workflow ON workflow_executions(workflow_id);
            CREATE INDEX idx_execution_user ON workflow_executions(user_id);
            CREATE INDEX idx_execution_status ON workflow_executions(status);
        """
        )

    async def backward(self, connection):
        """Drop workflow tables."""
        await connection.execute("DROP TABLE IF EXISTS workflow_executions CASCADE")
        await connection.execute("DROP TABLE IF EXISTS workflows CASCADE")


class AddUserAttributes(Migration):
    """Add attributes column to users table for ABAC."""

    id = "003_add_user_attributes"
    description = "Add JSONB attributes column for ABAC support"
    dependencies = ["001_create_users_table"]

    async def forward(self, connection):
        """Add attributes column."""
        await connection.execute(
            """
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS attributes JSONB DEFAULT '{}'::jsonb
        """
        )

        # Add index for common attribute queries
        await connection.execute(
            """
            CREATE INDEX idx_users_dept ON users((attributes->>'department'));
            CREATE INDEX idx_users_region ON users((attributes->>'region'));
        """
        )

    async def backward(self, connection):
        """Remove attributes column."""
        await connection.execute(
            """
            ALTER TABLE users DROP COLUMN IF EXISTS attributes
        """
        )


class PopulateTestData(Migration):
    """Populate test data for development."""

    id = "004_populate_test_data"
    description = "Add test users and workflows"
    dependencies = ["002_create_workflow_tables", "003_add_user_attributes"]

    async def forward(self, connection):
        """Insert test data."""
        # Insert test users
        await connection.execute(
            """
            INSERT INTO users (email, username, full_name, attributes)
            VALUES
                ('admin@example.com', 'admin', 'System Admin',
                 '{"department": "it", "role": "admin", "clearance": "top_secret"}'::jsonb),
                ('john@example.com', 'john_doe', 'John Doe',
                 '{"department": "engineering", "role": "developer", "clearance": "secret"}'::jsonb),
                ('jane@example.com', 'jane_smith', 'Jane Smith',
                 '{"department": "sales", "role": "manager", "clearance": "confidential"}'::jsonb)
            ON CONFLICT (email) DO NOTHING
        """
        )

        # Get admin user ID
        admin_row = await connection.fetchrow(
            "SELECT id FROM users WHERE username = 'admin'"
        )
        if admin_row:
            admin_id = admin_row["id"]

            # Insert test workflows
            await connection.execute(
                """
                INSERT INTO workflows (name, version, description, created_by)
                VALUES
                    ('data_processing', '1.0', 'ETL data processing workflow', $1),
                    ('ml_training', '1.0', 'Machine learning training pipeline', $1),
                    ('report_generation', '1.0', 'Generate monthly reports', $1)
                ON CONFLICT DO NOTHING
            """,
                admin_id,
            )

    async def backward(self, connection):
        """Remove test data."""
        # Delete in reverse order due to foreign keys
        await connection.execute(
            """
            DELETE FROM workflow_executions WHERE workflow_id IN (
                SELECT id FROM workflows WHERE name IN (
                    'data_processing', 'ml_training', 'report_generation'
                )
            )
        """
        )
        await connection.execute(
            """
            DELETE FROM workflows WHERE name IN (
                'data_processing', 'ml_training', 'report_generation'
            )
        """
        )
        await connection.execute(
            """
            DELETE FROM users WHERE username IN ('admin', 'john_doe', 'jane_smith')
        """
        )


async def demonstrate_migrations():
    """Run migration demonstration."""
    print("=== Database Migration Framework Demo ===\n")

    # Database configuration
    db_config = {
        "type": "postgresql",
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "database": os.getenv("DB_NAME", "kailash_test"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "postgres"),
    }

    # Create migration runner
    print("1. Initializing migration runner...")
    runner = MigrationRunner(db_config)
    await runner.initialize()

    # Register migrations
    print("\n2. Registering migrations...")
    migrations = [
        CreateUsersTable,
        CreateWorkflowTables,
        AddUserAttributes,
        PopulateTestData,
    ]

    for migration_class in migrations:
        runner.register_migration(migration_class)
        print(f"   Registered: {migration_class().id}")

    # Check current status
    print("\n3. Checking migration status...")
    applied = await runner.get_applied_migrations()
    print(f"   Applied migrations: {len(applied)}")
    for migration_id in sorted(applied):
        print(f"   - {migration_id}")

    # Create execution plan
    print("\n4. Creating migration plan...")
    plan = await runner.create_plan()
    print(f"   Migrations to apply: {len(plan.migrations_to_apply)}")
    for migration in plan.migrations_to_apply:
        print(f"   - {migration.id}: {migration.description}")

    if plan.warnings:
        print("   Warnings:")
        for warning in plan.warnings:
            print(f"   ! {warning}")

    # Execute migrations
    if plan.migrations_to_apply:
        print("\n5. Executing migrations...")

        # Dry run first
        print("   Running dry run...")
        dry_run_history = await runner.execute_plan(plan, dry_run=True)

        # Check dry run results
        if all(h.success for h in dry_run_history):
            print("   Dry run successful!")

            # Execute for real
            user_input = input("\n   Apply migrations? (y/n): ")
            if user_input.lower() == "y":
                history = await runner.execute_plan(plan, user="demo_user")

                print("\n   Migration results:")
                for record in history:
                    status = "✓" if record.success else "✗"
                    print(
                        f"   {status} {record.migration_id} ({record.execution_time:.2f}s)"
                    )
                    if record.error_message:
                        print(f"     Error: {record.error_message}")
        else:
            print("   Dry run failed!")
            for record in dry_run_history:
                if not record.success:
                    print(f"   ✗ {record.migration_id}: {record.error_message}")
    else:
        print("\n5. All migrations already applied!")

    # Show migration history
    print("\n6. Migration History:")
    history = await runner.get_migration_history()
    for record in history[:5]:  # Show last 5
        print(f"   {record.migration_id}")
        print(f"     Applied: {record.applied_at}")
        print(f"     By: {record.applied_by}")
        print(f"     Time: {record.execution_time:.2f}s")
        if record.rollback_at:
            print(f"     Rolled back: {record.rollback_at}")

    # Demonstrate migration generator
    print("\n7. Migration Generator Demo:")
    generator = MigrationGenerator("./example_migrations")

    # Generate a new migration
    migration_file = generator.create_migration(
        name="add_api_keys_table",
        description="Create table for API key management",
        migration_type="schema",
        dependencies=["001_create_users_table"],
    )
    print(f"   Generated: {migration_file}")

    # Show generated content
    with open(migration_file, "r") as f:
        content = f.read()
        print("\n   Preview (first 20 lines):")
        for line in content.split("\n")[:20]:
            print(f"   {line}")

    # Cleanup
    Path(migration_file).unlink()
    Path("./example_migrations").rmdir()

    print("\n=== Migration Demo Complete ===")


if __name__ == "__main__":
    # Note: This requires a PostgreSQL database to be running
    # You can start one with: docker run -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15

    try:
        asyncio.run(demonstrate_migrations())
    except Exception as e:
        print(f"\nError: {e}")
        print("\nMake sure PostgreSQL is running and accessible.")
        print("You can start a test database with:")
        print("  docker run -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15")
