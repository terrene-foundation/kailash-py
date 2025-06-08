#!/usr/bin/env python3
"""
Database Node Examples - SQLite Focus

This example demonstrates the SQLDatabaseNode functionality using SQLite including:
1. Project-level database configuration
2. Connection configured at node creation time
3. Query and parameters passed at runtime
4. Shared connection pools across all node instances
5. Security features and validation
6. ETL workflow patterns

SQLite is used throughout for simplicity - no external database server required.
The same patterns work with PostgreSQL and MySQL by updating the connection URL.
"""

import os
import sqlite3

from kailash import Workflow
from kailash.nodes.base import NodeMetadata
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.sql import SQLDatabaseNode
from kailash.nodes.logic.operations import MergeNode
from kailash.nodes.transform.processors import FilterNode
from kailash.runtime import LocalRuntime
from kailash.sdk_exceptions import NodeExecutionError


def get_sqlite_config(db_path: str) -> dict:
    """Get SQLite database configuration for examples."""
    return {
        "connection_string": f"sqlite:///{db_path}",
        "pool_size": 5,
        "max_overflow": 10,
        "pool_timeout": 30,
        "pool_recycle": 3600,
        "pool_pre_ping": True,
    }


def create_sample_database(db_path: str = "sample_customers.db") -> str:
    """Create a sample SQLite database with customer data for examples."""

    # Remove existing database
    if os.path.exists(db_path):
        os.remove(db_path)

    # Create new database with sample data
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create customers table
    cursor.execute(
        """
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            age INTEGER,
            city TEXT,
            registration_date TEXT,
            is_active BOOLEAN,
            total_orders INTEGER DEFAULT 0,
            total_spent REAL DEFAULT 0.0
        )
    """
    )

    # Create orders table
    cursor.execute(
        """
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            order_date TEXT,
            amount REAL,
            status TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers (id)
        )
    """
    )

    # Insert sample customers
    customers_data = [
        (
            1,
            "John Doe",
            "john@email.com",
            28,
            "New York",
            "2024-01-15",
            True,
            5,
            1250.75,
        ),
        (
            2,
            "Jane Smith",
            "jane@email.com",
            34,
            "Los Angeles",
            "2024-02-20",
            True,
            12,
            3400.50,
        ),
        (
            3,
            "Bob Johnson",
            "bob@email.com",
            45,
            "Chicago",
            "2024-01-10",
            False,
            2,
            180.25,
        ),
        (
            4,
            "Alice Brown",
            "alice@email.com",
            29,
            "New York",
            "2024-03-05",
            True,
            8,
            2100.00,
        ),
        (
            5,
            "Charlie Wilson",
            "charlie@email.com",
            52,
            "San Francisco",
            "2023-12-01",
            True,
            15,
            4500.75,
        ),
    ]

    cursor.executemany(
        """
        INSERT INTO customers (id, name, email, age, city, registration_date, is_active, 
                             total_orders, total_spent) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        customers_data,
    )

    # Insert sample orders
    orders_data = [
        (1, 1, "2024-01-20", 250.75, "completed"),
        (2, 1, "2024-02-15", 180.50, "completed"),
        (3, 2, "2024-03-01", 320.25, "completed"),
        (4, 2, "2024-03-15", 450.75, "completed"),
        (5, 4, "2024-03-10", 150.00, "completed"),
        (6, 4, "2024-04-20", 380.25, "completed"),
    ]

    cursor.executemany(
        """
        INSERT INTO orders (id, customer_id, order_date, amount, status) 
        VALUES (?, ?, ?, ?, ?)
    """,
        orders_data,
    )

    conn.commit()
    conn.close()

    print(f"✅ Sample database '{db_path}' created successfully!")
    return db_path


def example_1_basic_sql_operations():
    """Example 1: Basic SQLDatabaseNode operations."""
    print("\n" + "=" * 70)
    print("📊 EXAMPLE 1: Basic SQL Database Operations")
    print("=" * 70)

    # Create sample database
    db_path = create_sample_database("example1.db")

    # Get database configuration
    db_config = get_sqlite_config(db_path)

    # Create SQL database node with direct configuration - much cleaner!
    sql_node = SQLDatabaseNode(
        **db_config,  # Pass configuration directly
        metadata=NodeMetadata(
            id="sql_production_node",
            name="Production SQL Database Node",
            description="Demonstrates direct connection configuration",
            version="1.0",
            author="Kailash SDK",
            tags={"database", "sql", "sqlite", "production"},
        ),
    )

    print("\n🔍 1. Basic SELECT Query")
    result = sql_node.run(
        query="SELECT * FROM customers WHERE is_active = ?",
        parameters=[True],
        result_format="dict",
    )

    print(f"   Rows returned: {result['row_count']}")
    print(f"   Columns: {result['columns']}")
    print(f"   Execution time: {result['execution_time']:.4f}s")
    print(f"   Sample row: {result['data'][0] if result['data'] else 'No data'}")

    print("\n📝 2. INSERT Query - Add new customer")
    insert_result = sql_node.run(
        query="""INSERT INTO customers (name, email, age, city, registration_date, is_active, total_orders, total_spent) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        parameters=[
            "Eva Green",
            "eva@email.com",
            31,
            "Boston",
            "2024-06-06",
            True,
            0,
            0.0,
        ],
        result_format="dict",
    )

    print(f"   Rows affected: {insert_result['row_count']}")
    print(f"   Execution time: {insert_result['execution_time']:.4f}s")

    print("\n📊 3. Different Result Formats")

    # Dict format (default)
    dict_result = sql_node.run(
        query="SELECT name, age FROM customers LIMIT 2", result_format="dict"
    )
    print(f"   Dict format: {dict_result['data']}")

    # List format
    list_result = sql_node.run(
        query="SELECT name, age FROM customers LIMIT 2", result_format="list"
    )
    print(f"   List format: {list_result['data']}")

    print("\n⚙️ 4. Node Reusability")
    print("   🔄 Same node, multiple different queries:")

    # The same node can execute multiple queries since connection is configured once
    customers_count = sql_node.run(query="SELECT COUNT(*) as total FROM customers")
    print(f"   Total customers: {customers_count['data'][0]['total']}")

    active_customers = sql_node.run(
        query="SELECT COUNT(*) as active FROM customers WHERE is_active = ?",
        parameters=[True],
    )
    print(f"   Active customers: {active_customers['data'][0]['active']}")

    top_customers = sql_node.run(
        query="SELECT name, total_spent FROM customers ORDER BY total_spent DESC LIMIT 3",
        result_format="dict",
    )
    print("   Top customers by spending:")
    for customer in top_customers["data"]:
        print(f"     • {customer['name']}: ${customer['total_spent']:.2f}")

    print("\n🔧 5. Connection Pool Status")
    pool_status = SQLDatabaseNode.get_pool_status()
    for conn_str, status in pool_status.items():
        print(f"   Connection: {conn_str}")
        print(f"     Pool size: {status['pool_size']}")
        print(f"     Checked out: {status['checked_out']}")
        print(f"     Utilization: {status['utilization']:.1%}")
        print(f"     Total queries: {status['metrics'].get('total_queries', 0)}")

    print("\n   ✅ Key Features:")
    print("     • Direct configuration in constructor - no setup required")
    print("     • Only query and parameters passed at runtime")
    print("     • Shared connection pools prevent connection explosion")
    print("     • Configuration via simple dictionaries or parameters")
    print("     • Clean separation of configuration vs runtime data")

    # Cleanup
    SQLDatabaseNode.cleanup_pools()
    os.remove(db_path)
    print("\n   ✅ Example 1 completed successfully!")


def example_2_security_features():
    """Example 2: Security features and validation."""
    print("\n" + "=" * 70)
    print("🔒 EXAMPLE 2: Security Features")
    print("=" * 70)

    # Create sample database
    db_path = create_sample_database("example2.db")

    # Get database configuration
    db_config = get_sqlite_config(db_path)

    # Create SQL node with direct configuration
    sql_node = SQLDatabaseNode(**db_config)

    print("\n🛡️ 1. Password Masking in Logs")
    test_connections = [
        "sqlite:///local.db",  # No password to mask
        "sqlite:///path/to/database.db",  # Also no password
    ]

    for conn_str in test_connections:
        masked = SQLDatabaseNode._mask_connection_password(conn_str)
        print(f"   Connection: {conn_str}")
        print(f"   Masked:     {masked}")

    # Show how it would work with password-containing connections
    print("\n   Example with password-containing connections:")
    password_examples = [
        "postgresql://user:secret123@host/db",
        "mysql://admin:password@localhost/mydb",
    ]

    for conn_str in password_examples:
        masked = SQLDatabaseNode._mask_connection_password(conn_str)
        print(f"   Original: {conn_str}")
        print(f"   Masked:   {masked}")

    print("\n🔍 2. Query Safety Validation")
    # These queries will trigger warnings but not fail
    safe_queries = [
        "SELECT * FROM customers",
        "SELECT name FROM customers WHERE active = ?",
    ]

    potentially_dangerous = [
        "SELECT * FROM users; DROP TABLE admin;",
        "UPDATE customers SET status = 'inactive'",
    ]

    print("   Safe queries (no warnings):")
    for query in safe_queries:
        sql_node._validate_query_safety(query)
        print(f"     ✅ {query}")

    print("   Potentially dangerous queries (will log warnings):")
    for query in potentially_dangerous:
        sql_node._validate_query_safety(query)
        print(f"     ⚠️  {query}")

    print("\n🔒 3. SQL Injection Prevention")
    # Demonstrate that parameterized queries prevent injection
    malicious_input = "1'; DROP TABLE customers; --"

    # This is safe because we use parameterized queries
    safe_result = sql_node.run(
        query="SELECT * FROM customers WHERE id = ?",
        parameters=[malicious_input],  # This will be safely escaped
        result_format="dict",
    )

    print(f"   Malicious input: {malicious_input}")
    print(f"   Rows returned: {safe_result['row_count']} (should be 0)")
    print("   ✅ SQL injection prevented by parameterized queries!")

    # Verify table still exists
    verify_result = sql_node.run(
        query="SELECT COUNT(*) as count FROM customers", result_format="dict"
    )
    print(f"   Table still has {verify_result['data'][0]['count']} customers")

    print("\n🆔 4. Identifier Sanitization")
    valid_identifiers = ["customers", "user_data", "db.table"]
    invalid_identifiers = ["table'; DROP", "123invalid", "user--comment"]

    print("   Valid identifiers:")
    for identifier in valid_identifiers:
        try:
            sanitized = sql_node._sanitize_identifier(identifier)
            print(f"     ✅ {identifier} -> {sanitized}")
        except NodeExecutionError as e:
            print(f"     ❌ {identifier} -> Error: {e}")

    print("   Invalid identifiers:")
    for identifier in invalid_identifiers:
        try:
            sanitized = sql_node._sanitize_identifier(identifier)
            print(f"     ❌ {identifier} -> {sanitized} (should have failed!)")
        except NodeExecutionError as e:
            print(f"     ✅ {identifier} -> Correctly rejected: {e}")

    # Cleanup
    SQLDatabaseNode.cleanup_pools()
    os.remove(db_path)
    print("   ✅ Example 2 completed successfully!")


def example_3_etl_workflow():
    """Example 3: Complete ETL workflow with database operations."""
    print("\n" + "=" * 70)
    print("🔄 EXAMPLE 3: ETL Workflow")
    print("=" * 70)

    # Create sample database
    db_path = create_sample_database("example3.db")

    # Get database configuration
    db_config = get_sqlite_config(db_path)

    # Create workflow
    workflow = Workflow("database_etl", "Database ETL Example")

    # Add nodes with direct configuration
    workflow.add_node("extract_customers", SQLDatabaseNode(**db_config))
    workflow.add_node("extract_orders", SQLDatabaseNode(**db_config))
    workflow.add_node("filter_high_value", FilterNode)
    workflow.add_node("merge_results", MergeNode)

    # Add analytics transformation
    analytics_code = """
def execute(customers_data, orders_data):
    analytics_results = []
    
    for customer in customers_data:
        # Find this customer's orders from orders_data
        customer_orders = [order for order in orders_data if order['customer_id'] == customer['id']]
        
        # Calculate metrics using BOTH datasets
        order_count_from_orders = len(customer_orders)  # From orders_data
        total_spent_from_orders = sum(order['amount'] for order in customer_orders)  # From orders_data
        customer_name = customer['name']  # From customers_data
        customer_city = customer['city']  # From customers_data
        
        # Compare stored vs calculated values
        stored_total = customer['total_spent']  # From customers_data
        calculated_total = total_spent_from_orders  # From orders_data
        
        analytics_results.append({
            'customer_name': customer_name,
            'city': customer_city,
            'stored_total': stored_total,
            'calculated_total': calculated_total,
            'order_count': order_count_from_orders,
            'avg_order_value': round(calculated_total / order_count_from_orders, 2) if order_count_from_orders > 0 else 0
        })
    
    return {
        'customers': analytics_results,
        'summary': {
            'total_customers': len(customers_data),
            'total_orders': len(orders_data),
            'customers_with_orders': len([c for c in analytics_results if c['order_count'] > 0])
        }
    }

# Assign result for PythonCodeNode execution
result = execute(customers_data, orders_data)
"""

    workflow.add_node(
        "transform_analytics",
        PythonCodeNode(name="customer_analytics", code=analytics_code),
    )

    # Connect workflow
    workflow.connect("extract_customers", "filter_high_value", mapping={"data": "data"})
    workflow.connect(
        "extract_customers", "transform_analytics", mapping={"data": "customers_data"}
    )
    workflow.connect(
        "extract_orders", "transform_analytics", mapping={"data": "orders_data"}
    )
    workflow.connect(
        "filter_high_value",
        "merge_results",
        mapping={"filtered_data": "filtered_customers"},
    )
    workflow.connect(
        "transform_analytics", "merge_results", mapping={"result": "analytics"}
    )

    # Execute workflow
    runtime = LocalRuntime()

    workflow_params = {
        "extract_customers": {
            "query": "SELECT * FROM customers WHERE is_active = ?",
            "parameters": [True],
            "result_format": "dict",
        },
        "extract_orders": {
            "query": "SELECT * FROM orders WHERE status = ?",
            "parameters": ["completed"],
            "result_format": "dict",
        },
        "filter_high_value": {"field": "total_spent", "operator": ">", "value": 1000.0},
        "merge_results": {"merge_type": "dict"},
    }

    print("\n⚙️ Executing ETL workflow...")
    results, _ = runtime.execute(workflow, parameters=workflow_params)

    # Display results
    customers_result = results.get("extract_customers", {})
    analytics_result = results.get("transform_analytics", {}).get("result", {})
    filtered_result = results.get("filter_high_value", {})

    print("\n📊 ETL Results:")
    print(f"   Customers extracted: {len(customers_result.get('data', []))}")
    print(f"   High-value customers: {len(filtered_result.get('filtered_data', []))}")

    if analytics_result:
        summary = analytics_result.get("summary", {})
        print(f"   Total revenue: ${summary.get('total_revenue', 0):,.2f}")
        print(f"   Customers analyzed: {summary.get('total_customers', 0)}")

        # Show sample analytics
        customers = analytics_result.get("customers", [])[:2]
        print("\n   Sample analytics:")
        for customer in customers:
            name = customer.get("customer_name", "Unknown")
            stored = customer.get("stored_total", 0)
            calculated = customer.get("calculated_total", 0)
            orders = customer.get("order_count", 0)
            avg_order = customer.get("avg_order_value", 0)
            print(
                f"     • {name}: {orders} orders, stored=${stored:.2f}, calculated=${calculated:.2f}, avg=${avg_order:.2f}"
            )

    # Cleanup
    SQLDatabaseNode.cleanup_pools()
    os.remove(db_path)
    print("   ✅ Example 3 completed successfully!")


def example_4_error_handling():
    """Example 4: Error handling and edge cases."""
    print("\n" + "=" * 70)
    print("⚠️ EXAMPLE 4: Error Handling")
    print("=" * 70)

    print("\n❌ 1. Missing Connection String")
    try:
        # Try to create node without connection_string
        sql_node = SQLDatabaseNode()
    except Exception as e:
        print(f"   ✅ Correctly caught error: {str(e)[:100]}...")

    print("\n❌ 2. Invalid Connection String")
    try:
        # Try invalid connection URL
        sql_node = SQLDatabaseNode(connection_string="invalid://connection")
        sql_node.run(query="SELECT 1")
    except Exception as e:
        print(f"   ✅ Correctly caught error: {str(e)[:100]}...")

    print("\n❌ 3. Missing Required Parameters")
    # Create temporary database and valid config
    db_path = create_sample_database("error_test.db")
    db_config = get_sqlite_config(db_path)

    try:
        sql_node = SQLDatabaseNode(**db_config)
        sql_node.run()  # Missing query parameter
    except NodeExecutionError as e:
        print(f"   ✅ Correctly caught error: {e}")

    print("\n❌ 4. Invalid SQL Query")
    try:
        sql_node = SQLDatabaseNode(**db_config)
        sql_node.run(query="SELECT * FROM nonexistent_table")
    except NodeExecutionError as e:
        print(f"   ✅ Correctly caught SQL error: {str(e)[:100]}...")

    print("\n❌ 5. Invalid Parameter Types")
    try:
        sql_node = SQLDatabaseNode(**db_config)
        sql_node.run(
            query="SELECT * FROM customers WHERE id = ?",
            parameters="not_a_list",  # Should be list or dict
        )
    except Exception as e:
        print(f"   ✅ Correctly caught parameter error: {str(e)[:100]}...")

    # Cleanup
    SQLDatabaseNode.cleanup_pools()
    os.remove(db_path)
    print("   ✅ Example 4 completed successfully!")


def main():
    """Run all database node examples."""
    print("🗄️ DATABASE NODE EXAMPLES - SQLite Focus")
    print("=" * 70)
    print("This file demonstrates comprehensive database functionality using SQLite:")
    print("1. Basic SQL operations (SELECT, INSERT, UPDATE)")
    print("2. Security features and validation")
    print("3. Complete ETL workflow patterns")
    print("4. Error handling and edge cases")
    print()
    print("Note: SQLite is used for simplicity (no external database required).")
    print(
        "The same patterns work with PostgreSQL/MySQL by changing the connection URL."
    )

    try:
        example_1_basic_sql_operations()
        example_2_security_features()
        example_3_etl_workflow()
        example_4_error_handling()

        print("\n" + "=" * 70)
        print("🎉 ALL SQLite DATABASE EXAMPLES COMPLETED SUCCESSFULLY!")
        print("=" * 70)
        print("\nKey takeaways:")
        print("✅ SQLDatabaseNode provides production-ready database connectivity")
        print("✅ SQLite works out-of-the-box with no external dependencies")
        print("✅ Raw SQL interface with parameterized queries prevents SQL injection")
        print("✅ Security features protect sensitive data and credentials")
        print("✅ Database nodes integrate seamlessly with Kailash workflows")
        print("✅ Comprehensive error handling ensures robust production deployments")
        print("\n💡 To use PostgreSQL or MySQL:")
        print("   1. Change connection_string to postgresql:// or mysql:// URL")
        print("   2. Install database drivers (psycopg2, pymysql, etc.)")
        print("   3. Set up external database server")
        print("   4. All code patterns remain the same!")
        print("\n📝 Example configurations:")
        print(
            "   PostgreSQL: SQLDatabaseNode(connection_string='postgresql://user:pass@host/db')"
        )
        print(
            "   MySQL:      SQLDatabaseNode(connection_string='mysql://user:pass@host/db')"
        )
        print(
            "   SQLite:     SQLDatabaseNode(connection_string='sqlite:///path/to/db.db')"
        )

    except Exception as e:
        print(f"\n❌ Example failed: {e}")
        raise


if __name__ == "__main__":
    main()
