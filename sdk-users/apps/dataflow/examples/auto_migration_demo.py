#!/usr/bin/env python3
"""
DataFlow Auto-Migration System Demo

Demonstrates the advanced database migration system that automatically detects
schema changes, provides visual confirmation, and supports rollback capabilities.

Features:
- Automatic schema comparison and diff generation
- Visual confirmation before applying changes
- Rollback and versioning support
- Multi-database compatibility (PostgreSQL, MySQL, SQLite)
- Zero SQL knowledge required for users
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add the DataFlow app to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from dataflow.migrations import (
    AutoMigrationSystem,
    ColumnDefinition,
    Migration,
    MigrationGenerator,
    MigrationOperation,
    MigrationStatus,
    MigrationType,
    SchemaDiff,
    SchemaInspector,
    TableDefinition,
)


class MockDatabaseConnection:
    """Mock database connection for demonstration purposes."""

    def __init__(self, dialect: str = "postgresql"):
        self.dialect = dialect
        self.schema = {}
        self.migration_history = []

    async def cursor(self):
        """Return mock cursor."""
        return MockCursor(self)

    async def transaction(self):
        """Return mock transaction context."""
        return MockTransaction()


class MockCursor:
    """Mock database cursor."""

    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, query, params=None):
        """Mock execute method."""
        print(f"    Executing SQL: {query[:60]}{'...' if len(query) > 60 else ''}")
        return []

    async def fetchall(self):
        """Mock fetchall method."""
        # Return sample schema data for demo
        return [
            ("users", "id", "INTEGER", "NO", None, None, True),
            ("users", "name", "VARCHAR", "NO", None, 255, False),
            ("users", "email", "VARCHAR", "YES", None, 255, False),
            ("orders", "id", "INTEGER", "NO", None, None, True),
            ("orders", "user_id", "INTEGER", "NO", None, None, False),
            ("orders", "total", "DECIMAL", "NO", "0.00", None, False),
        ]


class MockTransaction:
    """Mock transaction context manager."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


def create_sample_schemas():
    """Create sample current and target schemas for demonstration."""

    # Current schema (what's in database)
    current_schema = {}

    # Users table (existing)
    users_table = TableDefinition(name="users")
    users_table.columns = [
        ColumnDefinition(name="id", type="INTEGER", primary_key=True, nullable=False),
        ColumnDefinition(name="name", type="VARCHAR", max_length=255, nullable=False),
        ColumnDefinition(name="email", type="VARCHAR", max_length=255, nullable=True),
    ]
    current_schema["users"] = users_table

    # Orders table (existing)
    orders_table = TableDefinition(name="orders")
    orders_table.columns = [
        ColumnDefinition(name="id", type="INTEGER", primary_key=True, nullable=False),
        ColumnDefinition(name="user_id", type="INTEGER", nullable=False),
        ColumnDefinition(name="total", type="DECIMAL", default="0.00", nullable=False),
    ]
    current_schema["orders"] = orders_table

    # Target schema (what we want)
    target_schema = {}

    # Updated users table (add created_at, modify email to be required)
    target_users = TableDefinition(name="users")
    target_users.columns = [
        ColumnDefinition(name="id", type="INTEGER", primary_key=True, nullable=False),
        ColumnDefinition(name="name", type="VARCHAR", max_length=255, nullable=False),
        ColumnDefinition(
            name="email", type="VARCHAR", max_length=255, nullable=False
        ),  # Changed to required
        ColumnDefinition(
            name="created_at",
            type="TIMESTAMP",
            default="CURRENT_TIMESTAMP",
            nullable=False,
        ),  # New column
    ]
    target_schema["users"] = target_users

    # Updated orders table (add status column)
    target_orders = TableDefinition(name="orders")
    target_orders.columns = [
        ColumnDefinition(name="id", type="INTEGER", primary_key=True, nullable=False),
        ColumnDefinition(name="user_id", type="INTEGER", nullable=False),
        ColumnDefinition(name="total", type="DECIMAL", default="0.00", nullable=False),
        ColumnDefinition(
            name="status",
            type="VARCHAR",
            max_length=50,
            default="pending",
            nullable=False,
        ),  # New column
    ]
    target_schema["orders"] = target_orders

    # New products table
    products_table = TableDefinition(name="products")
    products_table.columns = [
        ColumnDefinition(name="id", type="INTEGER", primary_key=True, nullable=False),
        ColumnDefinition(name="name", type="VARCHAR", max_length=255, nullable=False),
        ColumnDefinition(name="price", type="DECIMAL", nullable=False),
        ColumnDefinition(
            name="category", type="VARCHAR", max_length=100, nullable=True
        ),
        ColumnDefinition(name="in_stock", type="BOOLEAN", default=True, nullable=False),
    ]
    target_schema["products"] = products_table

    return current_schema, target_schema


async def demonstrate_schema_inspection():
    """Demonstrate schema inspection and comparison."""
    print("🔍 Step 1: Schema Inspection & Comparison")
    print("-" * 45)

    # Create mock connection
    connection = MockDatabaseConnection("postgresql")
    inspector = SchemaInspector(connection, "postgresql")

    print("📊 Current Database Schema:")
    current_schema, target_schema = create_sample_schemas()

    for table_name, table_def in current_schema.items():
        print(f"  📋 {table_name} ({len(table_def.columns)} columns):")
        for col in table_def.columns:
            nullable = "NULL" if col.nullable else "NOT NULL"
            pk = " [PK]" if col.primary_key else ""
            default = f" DEFAULT {col.default}" if col.default else ""
            print(f"    - {col.name}: {col.type} {nullable}{default}{pk}")

    print("\n🎯 Target Schema:")
    for table_name, table_def in target_schema.items():
        print(f"  📋 {table_name} ({len(table_def.columns)} columns):")
        for col in table_def.columns:
            nullable = "NULL" if col.nullable else "NOT NULL"
            pk = " [PK]" if col.primary_key else ""
            default = f" DEFAULT {col.default}" if col.default else ""
            print(f"    - {col.name}: {col.type} {nullable}{default}{pk}")

    # Compare schemas
    print("\n🔄 Schema Comparison:")
    diff = inspector.compare_schemas(current_schema, target_schema)

    print(f"  Changes detected: {diff.has_changes()}")
    print(f"  Total changes: {diff.change_count()}")

    if diff.tables_to_create:
        print(f"  📋 New tables: {len(diff.tables_to_create)}")
        for table in diff.tables_to_create:
            print(f"    ✅ {table.name}")

    if diff.tables_to_drop:
        print(f"  🗑️ Tables to drop: {len(diff.tables_to_drop)}")
        for table_name in diff.tables_to_drop:
            print(f"    ❌ {table_name}")

    if diff.tables_to_modify:
        print(f"  🔄 Tables to modify: {len(diff.tables_to_modify)}")
        for table_name, current, target in diff.tables_to_modify:
            print(f"    📝 {table_name}")

    return diff


async def demonstrate_migration_generation(diff: SchemaDiff):
    """Demonstrate migration generation from schema differences."""
    print("\n🛠️ Step 2: Migration Generation")
    print("-" * 32)

    # Generate migration for different databases
    dialects = ["postgresql", "mysql", "sqlite"]

    for dialect in dialects:
        print(f"\n💾 {dialect.upper()} Migration:")
        print("-" * (len(dialect) + 13))

        generator = MigrationGenerator(dialect)
        migration = generator.generate_migration(diff, f"{dialect}_migration")

        print(f"  Version: {migration.version}")
        print(f"  Operations: {len(migration.operations)}")
        print(f"  Checksum: {migration.checksum}")

        print("\n  📋 Operations:")
        for i, operation in enumerate(migration.operations, 1):
            print(
                f"    {i}. {operation.operation_type.value.upper()}: {operation.description}"
            )
            print(f"       Table: {operation.table_name}")

            # Show first line of SQL
            sql_preview = operation.sql_up.split("\n")[0]
            print(
                f"       SQL: {sql_preview[:70]}{'...' if len(sql_preview) > 70 else ''}"
            )

            if operation.metadata:
                print(f"       Metadata: {operation.metadata}")

        # Show full SQL for first operation as example
        if migration.operations:
            print("\n  📜 Sample SQL (Operation 1):")
            sample_sql = migration.operations[0].sql_up
            for line in sample_sql.split("\n"):
                if line.strip():
                    print(f"       {line}")


async def demonstrate_auto_migration_system():
    """Demonstrate the complete auto-migration system."""
    print("\n🚀 Step 3: Auto-Migration System")
    print("-" * 33)

    # Create mock connection and migration system
    connection = MockDatabaseConnection("postgresql")
    migration_system = AutoMigrationSystem(connection, "postgresql", "demo_migrations")

    print("🔧 Initializing auto-migration system...")
    print(f"  Database dialect: {migration_system.dialect}")
    print(f"  Migrations directory: {migration_system.migrations_dir}")

    # Create sample target schema
    current_schema, target_schema = create_sample_schemas()

    print("\n📊 Running auto-migration in dry-run mode...")

    try:
        # Run auto-migration in dry-run mode
        success, migrations = await migration_system.auto_migrate(
            target_schema,
            dry_run=True,
            interactive=False,  # Disable interactive mode for demo
            auto_confirm=False,
        )

        print(f"  Auto-migration completed: {success}")
        print(f"  Migrations generated: {len(migrations)}")

        if migrations:
            migration = migrations[0]
            print("\n  📋 Generated Migration Details:")
            print(f"    Version: {migration.version}")
            print(f"    Name: {migration.name}")
            print(f"    Operations: {len(migration.operations)}")
            print(f"    Status: {migration.status.value}")
            print(f"    Can rollback: {migration_system._can_rollback(migration)}")

    except Exception as e:
        print(f"  ❌ Error during auto-migration: {e}")

    # Demonstrate migration status
    print("\n📈 Migration Status:")
    try:
        status = await migration_system.get_migration_status()
        print(f"  Total migrations: {status['total_migrations']}")
        print(f"  Applied migrations: {status['applied_migrations']}")
        print(f"  Failed migrations: {status['failed_migrations']}")
        print(f"  Pending migrations: {status['pending_migrations']}")
    except Exception as e:
        print(f"  ❌ Error getting migration status: {e}")


async def demonstrate_rollback_capabilities():
    """Demonstrate migration rollback capabilities."""
    print("\n🔄 Step 4: Rollback Capabilities")
    print("-" * 31)

    print("📋 Rollback Scenario Analysis:")

    # Create different types of operations to show rollback capabilities
    operations = [
        MigrationOperation(
            operation_type=MigrationType.CREATE_TABLE,
            table_name="products",
            description="Create products table",
            sql_up="CREATE TABLE products (id INTEGER PRIMARY KEY, name VARCHAR(255));",
            sql_down="DROP TABLE products;",
        ),
        MigrationOperation(
            operation_type=MigrationType.ADD_COLUMN,
            table_name="users",
            description="Add created_at column",
            sql_up="ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;",
            sql_down="ALTER TABLE users DROP COLUMN created_at;",
        ),
        MigrationOperation(
            operation_type=MigrationType.DROP_COLUMN,
            table_name="orders",
            description="Drop old_field column",
            sql_up="ALTER TABLE orders DROP COLUMN old_field;",
            sql_down="-- Cannot automatically recreate dropped column: old_field",
        ),
        MigrationOperation(
            operation_type=MigrationType.MODIFY_COLUMN,
            table_name="users",
            description="Make email required",
            sql_up="ALTER TABLE users ALTER COLUMN email SET NOT NULL;",
            sql_down="ALTER TABLE users ALTER COLUMN email DROP NOT NULL;",
        ),
    ]

    for i, operation in enumerate(operations, 1):
        can_rollback = not operation.sql_down.startswith("-- Cannot")
        rollback_status = "✅ Can rollback" if can_rollback else "❌ Cannot rollback"

        print(
            f"\n  {i}. {operation.operation_type.value.upper()}: {operation.description}"
        )
        print(f"     {rollback_status}")
        print(f"     Forward SQL: {operation.sql_up[:50]}...")
        print(f"     Rollback SQL: {operation.sql_down[:50]}...")

        if not can_rollback:
            print("     ⚠️ Warning: This operation cannot be automatically rolled back")


async def demonstrate_multi_database_support():
    """Demonstrate multi-database support."""
    print("\n🗄️ Step 5: Multi-Database Support")
    print("-" * 34)

    # Create a simple table definition
    table = TableDefinition(name="example")
    table.columns = [
        ColumnDefinition(
            name="id", type="INTEGER", primary_key=True, auto_increment=True
        ),
        ColumnDefinition(name="name", type="VARCHAR", max_length=255, nullable=False),
        ColumnDefinition(
            name="created_at", type="TIMESTAMP", default="CURRENT_TIMESTAMP"
        ),
    ]

    dialects = [("PostgreSQL", "postgresql"), ("MySQL", "mysql"), ("SQLite", "sqlite")]

    for db_name, dialect in dialects:
        print(f"\n💾 {db_name} Implementation:")
        print("-" * (len(db_name) + 17))

        generator = MigrationGenerator(dialect)

        # Generate CREATE TABLE SQL
        create_sql = generator._create_table_sql(table)
        print("  CREATE TABLE SQL:")
        for line in create_sql.split("\n"):
            if line.strip():
                print(f"    {line}")

        # Show dialect-specific features
        print("\n  Dialect-specific features:")
        if dialect == "postgresql":
            print("    ✅ SERIAL type for auto-increment")
            print("    ✅ CONCURRENTLY for non-blocking index creation")
            print("    ✅ Advanced column modification syntax")
        elif dialect == "mysql":
            print("    ✅ AUTO_INCREMENT for auto-increment")
            print("    ✅ MODIFY COLUMN syntax")
            print("    ✅ Standard MySQL data types")
        elif dialect == "sqlite":
            print("    ✅ Simple and portable SQL")
            print("    ✅ Minimal syntax requirements")
            print("    ⚠️ Limited ALTER TABLE support")


async def demonstrate_enterprise_features():
    """Demonstrate enterprise-grade features."""
    print("\n🏢 Step 6: Enterprise Features")
    print("-" * 29)

    print("🔐 Security Features:")
    print("  ✅ Migration checksums for integrity verification")
    print("  ✅ Atomic transactions for safe migration application")
    print("  ✅ Rollback capability tracking")
    print("  ✅ Migration history audit trail")

    print("\n📊 Monitoring & Observability:")
    print("  ✅ Visual migration preview with change summary")
    print("  ✅ Detailed operation breakdown")
    print("  ✅ Migration status tracking")
    print("  ✅ Rollback safety analysis")

    print("\n🎯 User Experience:")
    print("  ✅ Zero SQL knowledge required")
    print("  ✅ Interactive confirmation prompts")
    print("  ✅ Dry-run mode for testing")
    print("  ✅ Automatic schema discovery")

    print("\n⚡ Performance Features:")
    print("  ✅ Efficient schema comparison algorithms")
    print("  ✅ Batch operation generation")
    print("  ✅ Database-specific optimizations")
    print("  ✅ Minimal database round trips")

    print("\n🔄 Production Ready:")
    print("  ✅ Multi-database compatibility")
    print("  ✅ Version control integration")
    print("  ✅ CI/CD pipeline support")
    print("  ✅ Rollback strategies")


async def main():
    """Run the complete auto-migration demonstration."""
    try:
        print("🚀 DataFlow Auto-Migration System Demo")
        print("=" * 50)
        print()
        print("This demo showcases the advanced database migration system")
        print("that automatically detects schema changes, provides visual")
        print("confirmation, and supports rollback capabilities.")
        print()

        # Run demonstration steps
        diff = await demonstrate_schema_inspection()
        await demonstrate_migration_generation(diff)
        await demonstrate_auto_migration_system()
        await demonstrate_rollback_capabilities()
        await demonstrate_multi_database_support()
        await demonstrate_enterprise_features()

        print("\n" + "=" * 50)
        print("✅ Auto-Migration System Demo Complete!")
        print("=" * 50)

        print("\n🎯 Key Benefits Demonstrated:")
        print("  🔍 Automatic schema change detection")
        print("  🛠️ Multi-database SQL generation")
        print("  🚀 Zero-SQL knowledge required")
        print("  🔄 Safe rollback capabilities")
        print("  📊 Visual confirmation and preview")
        print("  🏢 Enterprise-grade features")

        print("\n💡 Next Steps:")
        print("  1. Integrate with your DataFlow models")
        print("  2. Configure for your database dialect")
        print("  3. Set up migration directory")
        print("  4. Use db.auto_migrate() in your application")
        print("  5. Enable CI/CD integration for automated deployments")

        return 0

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
