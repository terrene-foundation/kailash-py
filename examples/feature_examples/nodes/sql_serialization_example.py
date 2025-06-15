"""Example demonstrating SQLDatabaseNode serialization enhancements.

This example shows how the SQLDatabaseNode now automatically serializes
database-specific types (Decimal, datetime, etc.) to JSON-compatible formats.
"""

import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

# Add the src directory to Python path
sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
    ),
)

from kailash.nodes.data import SQLDatabaseNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow


def demonstrate_sql_serialization():
    """Demonstrate automatic serialization of database types."""
    print("🔄 SQLDatabaseNode Serialization Demo")
    print("=" * 50)

    # Create an in-memory SQLite database for testing
    connection_string = "sqlite:///:memory:"

    # Create SQLDatabaseNode
    sql_node = SQLDatabaseNode(connection_string=connection_string)

    # Create a test table with various data types
    create_table_query = """
    CREATE TABLE test_data (
        id INTEGER PRIMARY KEY,
        name TEXT,
        price DECIMAL(10, 2),
        quantity INTEGER,
        created_at TIMESTAMP,
        expiry_date DATE,
        metadata TEXT,
        is_active BOOLEAN
    )
    """

    # Execute table creation
    sql_node.execute(query=create_table_query)
    print("✅ Created test table with various data types")

    # Insert test data with different types
    insert_query = """
    INSERT INTO test_data (name, price, quantity, created_at, expiry_date, metadata, is_active)
    VALUES
        (?, ?, ?, ?, ?, ?, ?),
        (?, ?, ?, ?, ?, ?, ?)
    """

    # Use current time for timestamps
    now = datetime.now()
    today = date.today()
    future_date = today + timedelta(days=30)

    parameters = [
        # First record
        "Product A",
        99.99,  # Will be stored as DECIMAL
        10,
        now,
        future_date,
        '{"category": "electronics", "tags": ["new", "featured"]}',
        True,
        # Second record
        "Product B",
        149.50,  # Will be stored as DECIMAL
        5,
        now - timedelta(days=7),
        today,
        '{"category": "accessories", "tags": ["sale"]}',
        False,
    ]

    sql_node.execute(query=insert_query, parameters=parameters)
    print("✅ Inserted test data with various types")

    # Query the data back
    select_query = "SELECT * FROM test_data ORDER BY id"
    result = sql_node.execute(query=select_query, result_format="dict")

    print("\n📊 Query Results (with automatic serialization):")
    print("-" * 50)

    for row in result["data"]:
        print(f"\nProduct: {row['name']}")
        print(f"  ID: {row['id']} (type: {type(row['id']).__name__})")
        print(f"  Price: ${row['price']} (type: {type(row['price']).__name__})")
        print(f"  Quantity: {row['quantity']}")
        print(
            f"  Created: {row['created_at']} (type: {type(row['created_at']).__name__})"
        )
        print(
            f"  Expiry: {row['expiry_date']} (type: {type(row['expiry_date']).__name__})"
        )
        print(f"  Active: {row['is_active']}")
        print(f"  Metadata: {row['metadata']}")

    # Demonstrate JSON serialization
    print("\n🔧 JSON Serialization Test:")
    print("-" * 50)

    try:
        import json

        json_output = json.dumps(result["data"], indent=2)
        print("✅ Successfully serialized to JSON:")
        print(json_output[:200] + "..." if len(json_output) > 200 else json_output)
    except Exception as e:
        print(f"❌ JSON serialization failed: {e}")

    # Test with complex queries including aggregations
    print("\n📊 Testing Aggregation with Decimal Types:")
    print("-" * 50)

    agg_query = """
    SELECT
        COUNT(*) as total_products,
        SUM(price) as total_value,
        AVG(price) as average_price,
        MIN(created_at) as earliest_created,
        MAX(expiry_date) as latest_expiry
    FROM test_data
    """

    agg_result = sql_node.execute(query=agg_query, result_format="dict")

    for row in agg_result["data"]:
        print(f"Total Products: {row['total_products']}")
        print(
            f"Total Value: ${row['total_value']} (type: {type(row['total_value']).__name__})"
        )
        print(
            f"Average Price: ${row['average_price']:.2f} (type: {type(row['average_price']).__name__})"
        )
        print(f"Earliest Created: {row['earliest_created']}")
        print(f"Latest Expiry: {row['latest_expiry']}")

    return result


def demonstrate_workflow_with_serialization():
    """Demonstrate serialization in a workflow context."""
    print("\n\n🔄 Workflow with SQL Serialization Demo")
    print("=" * 50)

    # Create workflow
    workflow = Workflow(
        workflow_id="sql_serialization_workflow", name="SQL Serialization Workflow"
    )

    # Add nodes
    workflow.add_node(
        "create_db",
        SQLDatabaseNode(connection_string="sqlite:///:memory:"),
    )

    workflow.add_node(
        "setup_table",
        SQLDatabaseNode(connection_string="sqlite:///:memory:"),
    )

    workflow.add_node(
        "insert_data",
        SQLDatabaseNode(connection_string="sqlite:///:memory:"),
    )

    workflow.add_node(
        "query_data",
        SQLDatabaseNode(connection_string="sqlite:///:memory:"),
    )

    # Note: In a real workflow, you'd typically use a persistent database
    # or pass the connection between nodes. This is simplified for demo.

    print("✅ Created workflow with SQL nodes")
    print(f"   Nodes: {list(workflow.nodes.keys())}")

    # In practice, you would execute the workflow with proper connections
    # runtime = LocalRuntime()
    # runtime.execute_workflow(workflow)


def main():
    """Run all demonstrations."""
    try:
        # Demonstrate basic serialization
        result = demonstrate_sql_serialization()

        # Demonstrate workflow usage
        demonstrate_workflow_with_serialization()

        print("\n\n✅ All demonstrations completed successfully!")

        # Summary of serialization features
        print("\n📋 Serialization Features Summary:")
        print("-" * 50)
        print("✅ Decimal → float: Preserves numeric precision in JSON")
        print("✅ datetime → ISO string: Standard format for timestamps")
        print("✅ date → ISO string: Standard format for dates")
        print("✅ timedelta → seconds: Numeric representation of duration")
        print("✅ UUID → string: Text representation of unique identifiers")
        print("✅ bytes → base64: Encoded binary data")
        print("✅ Nested structures: Lists and dicts are recursively serialized")

    except Exception as e:
        print(f"\n❌ Error during demonstration: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
