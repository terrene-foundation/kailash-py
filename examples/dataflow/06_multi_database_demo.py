#!/usr/bin/env python3
"""
DataFlow Multi-Database Support Demonstration

Shows how DataFlow seamlessly supports PostgreSQL, MySQL, and SQLite with
dialect-specific optimizations and consistent API.

Features demonstrated:
1. Automatic dialect detection from database URLs
2. Cross-database SQL generation
3. Dialect-specific type mapping
4. Advanced feature detection
5. Performance optimizations per database
"""

import os
import sys

# Add the DataFlow app to the path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../apps/kailash-dataflow/src")
)

from dataflow.database import (
    DatabaseDialect,
    DatabaseFeature,
    SQLGenerator,
    detect_dialect,
    get_database_adapter,
)


def demonstrate_dialect_detection():
    """Show automatic dialect detection from database URLs."""
    print("=== Dialect Detection ===\n")

    urls = [
        "postgresql://user:pass@localhost/db",
        "postgres://user:pass@localhost/db",
        "mysql://user:pass@localhost/db",
        "sqlite:///path/to/database.db",
        "postgresql+asyncpg://user:pass@localhost/db",
        "mysql+aiomysql://user:pass@localhost/db",
    ]

    for url in urls:
        dialect = detect_dialect(url)
        print(f"URL: {url}")
        print(f"Detected Dialect: {dialect.value}\n")


def demonstrate_feature_support():
    """Show feature support across different databases."""
    print("\n=== Feature Support Matrix ===\n")

    adapters = {
        "PostgreSQL": get_database_adapter(DatabaseDialect.POSTGRESQL),
        "MySQL": get_database_adapter(DatabaseDialect.MYSQL),
        "SQLite": get_database_adapter(DatabaseDialect.SQLITE),
    }

    features = [
        DatabaseFeature.TRANSACTIONS,
        DatabaseFeature.FOREIGN_KEYS,
        DatabaseFeature.JSON_TYPE,
        DatabaseFeature.UUID_TYPE,
        DatabaseFeature.ARRAY_TYPE,
        DatabaseFeature.UPSERT,
        DatabaseFeature.RETURNING,
        DatabaseFeature.WINDOW_FUNCTIONS,
        DatabaseFeature.MATERIALIZED_VIEWS,
        DatabaseFeature.STORED_PROCEDURES,
    ]

    # Print header
    print(f"{'Feature':<30} {'PostgreSQL':<12} {'MySQL':<12} {'SQLite':<12}")
    print("-" * 66)

    # Print feature support
    for feature in features:
        row = f"{feature.value:<30}"
        for db_name, adapter in adapters.items():
            supported = "✅" if adapter.supports_feature(feature) else "❌"
            row += f" {supported:<12}"
        print(row)


def demonstrate_type_mapping():
    """Show type mapping across databases."""
    print("\n\n=== Type Mapping ===\n")

    adapters = {
        "PostgreSQL": get_database_adapter(DatabaseDialect.POSTGRESQL),
        "MySQL": get_database_adapter(DatabaseDialect.MYSQL),
        "SQLite": get_database_adapter(DatabaseDialect.SQLITE),
    }

    types = ["INTEGER", "VARCHAR", "BOOLEAN", "JSON", "UUID", "DECIMAL", "TIMESTAMP"]

    # Print header
    print(f"{'SQL Type':<15} {'PostgreSQL':<15} {'MySQL':<15} {'SQLite':<15}")
    print("-" * 60)

    # Print type mappings
    for sql_type in types:
        row = f"{sql_type:<15}"
        for db_name, adapter in adapters.items():
            mapped_type = adapter.map_type(sql_type)
            row += f" {mapped_type:<15}"
        print(row)


def demonstrate_sql_generation():
    """Show SQL generation across databases."""
    print("\n\n=== SQL Generation Examples ===\n")

    # Create generators for each database
    pg_gen = SQLGenerator(get_database_adapter(DatabaseDialect.POSTGRESQL))
    mysql_gen = SQLGenerator(get_database_adapter(DatabaseDialect.MYSQL))
    sqlite_gen = SQLGenerator(get_database_adapter(DatabaseDialect.SQLITE))

    # 1. CREATE TABLE
    print("1. CREATE TABLE Statement:\n")

    columns = [
        {"name": "id", "type": "INTEGER", "primary_key": True, "auto_increment": True},
        {"name": "name", "type": "VARCHAR", "length": 100, "nullable": False},
        {"name": "email", "type": "VARCHAR", "length": 255, "unique": True},
        {"name": "metadata", "type": "JSON"},
        {"name": "created_at", "type": "TIMESTAMP", "default": "CURRENT_TIMESTAMP"},
    ]

    print("PostgreSQL:")
    print(pg_gen.create_table("users", columns))
    print("\nMySQL:")
    print(mysql_gen.create_table("users", columns))
    print("\nSQLite:")
    print(sqlite_gen.create_table("users", columns))

    # 2. INSERT with RETURNING
    print("\n\n2. INSERT Statement with RETURNING:\n")

    print("PostgreSQL:")
    pg_sql, pg_values = pg_gen.insert(
        "users",
        ["name", "email"],
        ["John Doe", "john@example.com"],
        returning=["id", "created_at"],
    )
    print(f"SQL: {pg_sql}")
    print(f"Values: {pg_values}")

    print("\nMySQL (no RETURNING support):")
    mysql_sql, mysql_values = mysql_gen.insert(
        "users", ["name", "email"], ["John Doe", "john@example.com"]
    )
    print(f"SQL: {mysql_sql}")
    print(f"Values: {mysql_values}")

    # 3. UPSERT Operations
    print("\n\n3. UPSERT (INSERT ... ON CONFLICT) Operations:\n")

    print("PostgreSQL (ON CONFLICT):")
    pg_sql, _ = get_database_adapter(DatabaseDialect.POSTGRESQL).get_upsert_sql(
        "users",
        ["email", "name"],
        ["john@example.com", "John Doe"],
        ["email"],
        ["name"],
    )
    print(pg_sql)

    print("\nMySQL (ON DUPLICATE KEY):")
    mysql_sql, _ = get_database_adapter(DatabaseDialect.MYSQL).get_upsert_sql(
        "users",
        ["email", "name"],
        ["john@example.com", "John Doe"],
        ["email"],
        ["name"],
    )
    print(mysql_sql)

    print("\nSQLite (ON CONFLICT):")
    sqlite_sql, _ = get_database_adapter(DatabaseDialect.SQLITE).get_upsert_sql(
        "users",
        ["email", "name"],
        ["john@example.com", "John Doe"],
        ["email"],
        ["name"],
    )
    print(sqlite_sql)

    # 4. Complex SELECT
    print("\n\n4. Complex SELECT Query:\n")

    select_sql = pg_gen.select(
        "orders",
        columns=["id", "total", "status"],
        joins=[{"type": "INNER", "table": "users", "on": "orders.user_id = users.id"}],
        where_clause="orders.status = 'completed'",
        group_by=["status"],
        having_clause="SUM(total) > 1000",
        order_by=[("total", "DESC")],
        limit=10,
        offset=20,
    )

    print("PostgreSQL SELECT:")
    print(select_sql)

    # 5. JSON Operations
    print("\n\n5. JSON Extraction Operations:\n")

    pg_adapter = get_database_adapter(DatabaseDialect.POSTGRESQL)
    mysql_adapter = get_database_adapter(DatabaseDialect.MYSQL)
    sqlite_adapter = get_database_adapter(DatabaseDialect.SQLITE)

    json_path = "$.user.preferences.theme"

    print(f"Extracting JSON path: {json_path}\n")
    print(f"PostgreSQL: {pg_adapter.get_json_extract_sql('settings', json_path)}")
    print(f"MySQL: {mysql_adapter.get_json_extract_sql('settings', json_path)}")
    print(f"SQLite: {sqlite_adapter.get_json_extract_sql('settings', json_path)}")


def demonstrate_index_creation():
    """Show index creation across databases."""
    print("\n\n=== Index Creation ===\n")

    pg_gen = SQLGenerator(get_database_adapter(DatabaseDialect.POSTGRESQL))
    mysql_gen = SQLGenerator(get_database_adapter(DatabaseDialect.MYSQL))
    sqlite_gen = SQLGenerator(get_database_adapter(DatabaseDialect.SQLITE))

    # Basic index
    print("1. Basic Index:")
    print(f"PostgreSQL: {pg_gen.create_index('idx_email', 'users', ['email'])}")
    print(f"MySQL: {mysql_gen.create_index('idx_email', 'users', ['email'])}")
    print(f"SQLite: {sqlite_gen.create_index('idx_email', 'users', ['email'])}")

    # Partial index (PostgreSQL and SQLite only)
    print("\n2. Partial Index (PostgreSQL/SQLite):")
    pg_idx = pg_gen.create_index(
        "idx_active_users", "users", ["created_at"], where_clause="active = true"
    )
    print(f"PostgreSQL: {pg_idx}")

    sqlite_idx = sqlite_gen.create_index(
        "idx_active_users", "users", ["created_at"], where_clause="active = 1"
    )
    print(f"SQLite: {sqlite_idx}")

    # PostgreSQL-specific index types
    print("\n3. PostgreSQL GIN Index (for JSON/Array):")
    pg_gin = pg_gen.create_index(
        "idx_metadata", "users", ["metadata"], index_type="gin"
    )
    print(f"PostgreSQL: {pg_gin}")


def demonstrate_performance_features():
    """Show performance-related features."""
    print("\n\n=== Performance Features ===\n")

    pg_adapter = get_database_adapter(DatabaseDialect.POSTGRESQL)
    mysql_adapter = get_database_adapter(DatabaseDialect.MYSQL)
    sqlite_adapter = get_database_adapter(DatabaseDialect.SQLITE)

    print("1. Connection String Examples:")
    print("   PostgreSQL: postgresql://user:pass@localhost/db?pool_size=20")
    print("   MySQL: mysql://user:pass@localhost/db?charset=utf8mb4")
    print("   SQLite: sqlite:///path/to/db.sqlite?cache=shared")

    print("\n2. Bulk Operation Support:")
    print("   PostgreSQL: COPY FROM for ultra-fast bulk inserts")
    print("   MySQL: LOAD DATA INFILE for bulk operations")
    print("   SQLite: Batched INSERT with transaction wrapping")

    print("\n3. Query Optimization Features:")
    print(
        f"   PostgreSQL EXPLAIN: {pg_adapter.supports_feature(DatabaseFeature.EXPLAIN_ANALYZE)}"
    )
    print(
        f"   MySQL Query Hints: {mysql_adapter.supports_feature(DatabaseFeature.QUERY_HINTS)}"
    )
    print("   SQLite Query Plan: Always available via EXPLAIN QUERY PLAN")


def main():
    """Run all demonstrations."""
    print("DataFlow Multi-Database Support Demonstration")
    print("=" * 50)

    demonstrate_dialect_detection()
    demonstrate_feature_support()
    demonstrate_type_mapping()
    demonstrate_sql_generation()
    demonstrate_index_creation()
    demonstrate_performance_features()

    print("\n\n=== Summary ===")
    print(
        """
DataFlow provides seamless multi-database support with:

✅ Automatic dialect detection from connection URLs
✅ Consistent API across PostgreSQL, MySQL, and SQLite
✅ Dialect-specific SQL generation and optimizations
✅ Feature detection for conditional functionality
✅ Type mapping for cross-database compatibility
✅ Performance optimizations per database engine

This allows you to:
- Write database-agnostic code
- Switch databases without changing application logic
- Leverage database-specific features when available
- Optimize performance based on the database engine
"""
    )


if __name__ == "__main__":
    main()
