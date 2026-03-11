#!/usr/bin/env python3
"""
DataFlow Visual Migration Builder Demo

Demonstrates the visual migration builder that allows creating migrations through
method calls instead of SQL, providing a declarative and intuitive API.

Features:
- Declarative schema modification API
- Visual operation builder with method chaining
- Automatic SQL generation from method calls
- Support for all major database operations
- Multi-database compatibility
- Type-safe migration building
"""

import sys

from dataflow.migrations import (
    ColumnType,
    ConstraintType,
    IndexType,
    MigrationScript,
    VisualMigrationBuilder,
)


def demonstrate_basic_table_creation():
    """Demonstrate basic table creation with visual migration builder."""
    print("🏗️ Step 1: Basic Table Creation")
    print("-" * 35)

    # Create a migration builder
    builder = VisualMigrationBuilder("create_users_table", "postgresql")

    # Create users table with fluent API
    print("📋 Creating users table with fluent API:")
    table = builder.create_table("users")

    # Add columns using fluent API
    table.id()  # Auto-incrementing primary key
    table.string("first_name", 100).not_null()
    table.string("last_name", 100).not_null()
    table.string("email", 255).unique().not_null()
    table.string("phone", 20).null()
    table.boolean("active").default_value(True).not_null()
    table.timestamps()  # created_at and updated_at

    # Add indexes
    table.index("email")
    table.index("active", "created_at")
    table.unique_index("email")

    # Add constraints
    table.check_constraint("valid_email", "email LIKE '%@%'")

    # Finalize the table
    table._finalize()

    # Show generated migration
    print("\n📜 Generated Migration Preview:")
    print(builder.preview())

    return builder


def demonstrate_column_operations():
    """Demonstrate various column operations."""
    print("\n🔧 Step 2: Column Operations")
    print("-" * 28)

    builder = VisualMigrationBuilder("modify_users_table", "postgresql")

    print("📋 Column Operations:")

    # Add new column
    print("  ✅ Adding 'avatar_url' column")
    builder.add_column("users", "avatar_url", ColumnType.VARCHAR).length(
        500
    ).null()._finalize()

    # Add another column with default
    print("  ✅ Adding 'status' column with default")
    builder.add_column("users", "status", ColumnType.VARCHAR).length(20).default_value(
        "pending"
    ).not_null()._finalize()

    # Modify existing column
    print("  🔄 Modifying 'email' column to be longer")
    builder.modify_column("users", "email", ColumnType.VARCHAR).length(
        320
    ).not_null()._finalize()

    # Drop column
    print("  ❌ Dropping 'phone' column")
    builder.drop_column("users", "phone")

    # Rename column
    print("  📝 Renaming 'active' to 'is_active'")
    builder.rename_column("users", "active", "is_active")

    print("\n📜 Column Operations Migration:")
    preview = builder.preview()
    # Show just the operation descriptions
    for line in preview.split("\n"):
        if line.strip().startswith(("1.", "2.", "3.", "4.", "5.")):
            print(f"    {line.strip()}")

    return builder


def demonstrate_index_operations():
    """Demonstrate index operations."""
    print("\n📊 Step 3: Index Operations")
    print("-" * 26)

    builder = VisualMigrationBuilder("manage_indexes", "postgresql")

    print("📋 Index Operations:")

    # Simple index
    print("  📌 Creating simple index on 'email'")
    builder.add_index("users", "idx_users_email").on_columns("email")._finalize()

    # Composite index
    print("  📌 Creating composite index on 'last_name', 'first_name'")
    builder.add_index("users", "idx_users_name").on_columns(
        "last_name", "first_name"
    )._finalize()

    # Unique index
    print("  🔒 Creating unique index on 'email'")
    builder.add_index("users", "uniq_users_email").on_columns(
        "email"
    ).unique()._finalize()

    # Partial index (PostgreSQL)
    print("  🎯 Creating partial index on active users")
    builder.add_index("users", "idx_active_users").on_columns("created_at").where(
        "is_active = true"
    )._finalize()

    # Hash index (PostgreSQL)
    print("  #️⃣ Creating hash index on 'status'")
    builder.add_index("users", "idx_users_status_hash").on_columns("status").using(
        IndexType.HASH
    )._finalize()

    # Covering index (PostgreSQL)
    print("  📦 Creating covering index")
    builder.add_index("users", "idx_users_covering").on_columns("id").include(
        "email", "first_name"
    )._finalize()

    # Drop index
    print("  🗑️ Dropping old index")
    builder.drop_index("old_idx_users", "users")

    print("\n📜 Index Operations Summary:")
    print(f"    Total operations: {len(builder.operations)}")
    for i, op in enumerate(builder.operations, 1):
        print(f"    {i}. {op.description}")

    return builder


def demonstrate_table_operations():
    """Demonstrate table-level operations."""
    print("\n🏢 Step 4: Table Operations")
    print("-" * 26)

    builder = VisualMigrationBuilder("table_operations", "postgresql")

    print("📋 Table Operations:")

    # Create complex table
    print("  ✅ Creating 'orders' table")
    orders = builder.create_table("orders")
    orders.id()
    orders.integer("user_id").references("users.id").not_null()
    orders.string("order_number", 50).unique().not_null()
    orders.decimal("total", 10, 2).default_value("0.00").not_null()
    orders.string("status", 20).default_value("pending").not_null()
    orders.text("notes").null()
    orders.json("metadata").null()
    orders.timestamps()

    # Add indexes to orders table
    orders.index("user_id")
    orders.index("status", "created_at")
    orders.unique_index("order_number")

    # Add constraints
    orders.foreign_key("user_id", "users.id", "CASCADE")
    orders.check_constraint("positive_total", "total >= 0")
    orders.check_constraint(
        "valid_status", "status IN ('pending', 'processing', 'completed', 'cancelled')"
    )

    orders._finalize()

    # Rename table
    print("  📝 Renaming 'old_logs' to 'audit_logs'")
    builder.rename_table("old_logs", "audit_logs")

    # Drop table
    print("  ❌ Dropping 'temporary_data' table")
    builder.drop_table("temporary_data")

    # Custom SQL operation
    print("  🛠️ Adding custom SQL for database extension")
    builder.execute_sql(
        "CREATE EXTENSION IF NOT EXISTS 'uuid-ossp';",
        "Enable UUID extension for PostgreSQL",
    )

    print("\n📜 Generated SQL for orders table:")
    migration = builder.build()
    if migration.operations:
        create_table_op = migration.operations[0]
        sql_lines = create_table_op.sql_up.split("\n")
        for line in sql_lines[:10]:  # Show first 10 lines
            if line.strip():
                print(f"    {line}")
        if len(sql_lines) > 10:
            print(f"    ... and {len(sql_lines) - 10} more lines")

    return builder


def demonstrate_multi_database_support():
    """Demonstrate multi-database support."""
    print("\n🗄️ Step 5: Multi-Database Support")
    print("-" * 34)

    print("📋 Database-Specific Features:")

    databases = [("PostgreSQL", "postgresql"), ("MySQL", "mysql"), ("SQLite", "sqlite")]

    for db_name, dialect in databases:
        print(f"\n💾 {db_name} Features:")
        print("-" * (len(db_name) + 11))

        builder = VisualMigrationBuilder(f"{dialect}_migration", dialect)

        # Create table with auto-increment
        table = builder.create_table("sample")
        table.id()  # This will use dialect-specific auto-increment
        table.string("name", 255).not_null()
        table.timestamp("created_at").default_value("CURRENT_TIMESTAMP")
        table._finalize()

        # Add index
        builder.add_index("sample", "idx_sample_name").on_columns("name")._finalize()

        # Show generated SQL
        migration = builder.build()
        if migration.operations:
            create_op = migration.operations[0]
            sql = create_op.sql_up

            print("    CREATE TABLE SQL:")
            for line in sql.split("\n"):
                if line.strip():
                    print(f"      {line}")

            if len(migration.operations) > 1:
                index_op = migration.operations[1]
                print("\n    CREATE INDEX SQL:")
                print(f"      {index_op.sql_up}")

            # Highlight dialect-specific features
            if dialect == "postgresql":
                if "SERIAL" in sql:
                    print("    🎯 Uses SERIAL for auto-increment")
                if "CONCURRENTLY" in (
                    migration.operations[1].sql_up
                    if len(migration.operations) > 1
                    else ""
                ):
                    print("    🎯 Uses CONCURRENTLY for non-blocking index creation")
            elif dialect == "mysql":
                if "AUTO_INCREMENT" in sql:
                    print("    🎯 Uses AUTO_INCREMENT for auto-increment")
            elif dialect == "sqlite":
                print("    🎯 Simple, portable SQL syntax")


def demonstrate_migration_script():
    """Demonstrate complete migration script with up/down operations."""
    print("\n📃 Step 6: Complete Migration Script")
    print("-" * 36)

    print("📋 Creating complete migration script with up/down operations:")

    # Create migration script
    script = MigrationScript("add_user_profiles", "postgresql")

    # Up migration - create user profiles
    up = script.up()

    print("  ⬆️ Up Migration:")
    profiles = up.create_table("user_profiles")
    profiles.id()
    profiles.integer("user_id").references("users.id").not_null().unique()
    profiles.string("bio", 1000).null()
    profiles.string("avatar_url", 500).null()
    profiles.string("website", 255).null()
    profiles.json("social_links").null()
    profiles.json("preferences").default_value("{}").not_null()
    profiles.timestamps()

    # Add indexes
    profiles.index("user_id")
    profiles.foreign_key("user_id", "users.id", "CASCADE")
    profiles._finalize()

    # Add column to existing users table
    up.add_column("users", "profile_completed", ColumnType.BOOLEAN).default_value(
        False
    ).not_null()._finalize()

    print("    - Create user_profiles table")
    print("    - Add profile_completed column to users")

    # Down migration - rollback changes
    down = script.down()

    print("  ⬇️ Down Migration:")
    down.drop_column("users", "profile_completed")
    down.drop_table("user_profiles")

    print("    - Drop profile_completed column from users")
    print("    - Drop user_profiles table")

    # Show preview
    print("\n📜 Complete Migration Script Preview:")
    preview = script.preview_all()

    # Extract key information
    lines = preview.split("\n")
    for line in lines:
        if (
            "Migration Preview:" in line
            or line.startswith("Version:")
            or line.startswith("Operations:")
        ):
            print(f"    {line}")
        elif line.strip().startswith(("1.", "2.", "3.", "4.")):
            print(f"      {line.strip()}")


def demonstrate_advanced_features():
    """Demonstrate advanced migration builder features."""
    print("\n🚀 Step 7: Advanced Features")
    print("-" * 28)

    builder = VisualMigrationBuilder("advanced_migration", "postgresql")

    print("📋 Advanced Features:")

    # Create table with all column types
    print("  🎯 All column types demonstration")
    table = builder.create_table("showcase")

    # All basic types
    table.id("id")
    table.string("text_field", 255)
    table.text("long_text")
    table.integer("int_field")
    table.bigint("big_int_field")
    table.decimal("decimal_field", 10, 2)
    table.boolean("bool_field")
    table.timestamp("timestamp_field")
    table.json("json_field")
    table.uuid("uuid_field")

    # With various constraints
    table.string("constrained_field", 50).not_null().unique().check(
        "LENGTH(constrained_field) > 3"
    ).comment("Field with multiple constraints")

    # Foreign key
    table.integer("foreign_key_field").references("users.id").not_null()

    table._finalize()

    print("  📊 Complex indexes")
    # Complex index with all features (PostgreSQL)
    builder.add_index("showcase", "idx_complex").on_columns(
        "text_field", "int_field"
    ).using(IndexType.BTREE).where("bool_field = true").include(
        "timestamp_field"
    )._finalize()

    # Show comprehensive preview
    print("\n📜 Advanced Migration Statistics:")
    migration = builder.build()
    print(f"    Migration name: {migration.name}")
    print(f"    Version: {migration.version}")
    print(f"    Total operations: {len(migration.operations)}")
    print(f"    Checksum: {migration.checksum}")

    if migration.operations:
        create_op = migration.operations[0]
        sql_length = len(create_op.sql_up)
        print(f"    Generated SQL length: {sql_length} characters")

        # Count different elements
        sql = create_op.sql_up
        column_count = sql.count(",") + 1  # Rough estimate
        constraint_count = (
            sql.upper().count("NOT NULL")
            + sql.upper().count("UNIQUE")
            + sql.upper().count("PRIMARY KEY")
        )

        print(f"    Estimated columns: {column_count}")
        print(f"    Estimated constraints: {constraint_count}")


def main():
    """Run the complete visual migration builder demonstration."""
    try:
        print("🎨 DataFlow Visual Migration Builder Demo")
        print("=" * 55)
        print()
        print("This demo showcases the visual migration builder that allows")
        print("creating database migrations through method calls instead of SQL.")
        print()

        # Run demonstration steps
        demonstrate_basic_table_creation()
        demonstrate_column_operations()
        demonstrate_index_operations()
        demonstrate_table_operations()
        demonstrate_multi_database_support()
        demonstrate_migration_script()
        demonstrate_advanced_features()

        print("\n" + "=" * 55)
        print("✅ Visual Migration Builder Demo Complete!")
        print("=" * 55)

        print("\n🎯 Key Benefits Demonstrated:")
        print("  🎨 Fluent API for schema changes")
        print("  🔧 Method chaining for intuitive building")
        print("  🗄️ Multi-database SQL generation")
        print("  🛡️ Type-safe migration construction")
        print("  📋 Automatic SQL generation from declarations")
        print("  🔄 Complete up/down migration support")

        print("\n💡 Usage Examples:")
        print("  # Create table")
        print("  table = builder.create_table('users')")
        print("  table.id().string('name', 255).timestamps()")
        print()
        print("  # Add column")
        print("  builder.add_column('users', 'email', ColumnType.VARCHAR)")
        print("         .length(255).unique().not_null()")
        print()
        print("  # Create index")
        print("  builder.add_index('users', 'idx_email')")
        print("         .on_columns('email').using(IndexType.BTREE)")

        print("\n🚀 Next Steps:")
        print("  1. Use VisualMigrationBuilder in your migrations")
        print("  2. Combine with AutoMigrationSystem for complete workflow")
        print("  3. Leverage multi-database support for portability")
        print("  4. Build complex schemas with zero SQL knowledge")

        return 0

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
