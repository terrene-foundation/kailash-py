#!/usr/bin/env python3
"""
DataFlow QueryBuilder Example

Demonstrates MongoDB-style query building with cross-database support.
"""

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from kailash_dataflow import DataFlow

# Initialize DataFlow with query builder
db = DataFlow(enable_query_cache=True, cache_invalidation_strategy="pattern_based")


# Define a model
@db.model
class User:
    id: int
    name: str
    email: str
    age: int
    status: str
    created_at: str
    metadata: dict


def query_builder_examples():
    """Demonstrate QueryBuilder capabilities"""

    print("🔧 MongoDB-Style Query Building Examples")
    print("=" * 50)

    # Example 1: Basic query building
    print("\n1. Basic Query Building")
    builder = User.query_builder()
    builder.where("age", "$gt", 18)
    builder.where("status", "$eq", "active")
    sql, params = builder.build_select(["name", "email"])
    print(f"SQL: {sql}")
    print(f"Parameters: {params}")

    # Example 2: Complex conditions
    print("\n2. Complex Conditions")
    builder = db.build_query("users")
    builder.where("age", "$gte", 21)
    builder.where("age", "$lte", 65)
    builder.where("status", "$in", ["active", "premium"])
    builder.where("email", "$like", "%@company.com")
    sql, params = builder.build_select(["id", "name", "email", "status"])
    print(f"SQL: {sql}")
    print(f"Parameters: {params}")

    # Example 3: JSON/JSONB queries (PostgreSQL)
    print("\n3. JSON/JSONB Queries")
    builder = db.build_query("users")
    builder.where("metadata", "$has_key", "preferences")
    builder.where("metadata", "$has_key", "settings")
    sql, params = builder.build_select(["id", "name", "metadata"])
    print(f"SQL: {sql}")
    print(f"Parameters: {params}")

    # Example 4: Multi-tenant queries
    print("\n4. Multi-Tenant Queries")
    builder = db.build_query("users", tenant_id="tenant_123")
    builder.where("status", "$eq", "active")
    builder.where("created_at", "$gte", "2024-01-01")
    sql, params = builder.build_select(["id", "name", "email"])
    print(f"SQL: {sql}")
    print(f"Parameters: {params}")

    # Example 5: Update operations
    print("\n5. Update Operations")
    builder = db.build_query("users")
    builder.where("id", "$eq", 123)
    sql, params = builder.build_update(
        {"last_login": "2024-01-15T10:30:00Z", "login_count": 5}
    )
    print(f"SQL: {sql}")
    print(f"Parameters: {params}")

    # Example 6: Delete operations
    print("\n6. Delete Operations")
    builder = db.build_query("users")
    builder.where("status", "$eq", "inactive")
    builder.where("last_login", "$lt", "2023-01-01")
    sql, params = builder.build_delete()
    print(f"SQL: {sql}")
    print(f"Parameters: {params}")


def cross_database_examples():
    """Demonstrate cross-database compatibility"""

    print("\n\n🌐 Cross-Database Compatibility")
    print("=" * 40)

    # Test different database types
    databases = ["postgresql", "mysql", "sqlite"]

    for db_type in databases:
        print(f"\n{db_type.upper()} Example:")
        from kailash.nodes.data.query_builder import create_query_builder

        builder = create_query_builder(db_type)
        builder.table("users")
        builder.where("age", "$gt", 18)
        builder.where("status", "$in", ["active", "premium"])

        if db_type == "postgresql":
            builder.where("name", "$ilike", "%john%")  # Case-insensitive
        else:
            builder.where("name", "$like", "%john%")  # Case-sensitive

        sql, params = builder.build_select(["id", "name", "email"])
        print(f"  SQL: {sql}")
        print(f"  Parameters: {params}")


def workflow_integration_example():
    """Demonstrate integration with Kailash workflows"""

    print("\n\n🔄 Workflow Integration")
    print("=" * 30)

    # Create workflow with query builder
    workflow = WorkflowBuilder()

    # Build query using DataFlow
    builder = db.build_query("users")
    builder.where("status", "$eq", "active")
    builder.where("age", "$gte", 21)
    sql, params = builder.build_select(["id", "name", "email"])

    # Add nodes to workflow
    workflow.add_node(
        "AsyncSQLDatabaseNode",
        "query_users",
        {
            "connection_string": "sqlite:///example.db",
            "query_template": sql,
            "parameters": params,
        },
    )

    workflow.add_node(
        "LLMAgentNode",
        "analyze_users",
        {"model": "gpt-4", "system_prompt": "Analyze user data and provide insights"},
    )

    workflow.connect("query_users", "result", mapping={"analyze_users": "input_data"})

    print("Workflow created with QueryBuilder integration!")
    print(f"Query: {sql}")
    print(f"Parameters: {params}")

    # Execute workflow
    runtime = LocalRuntime()
    print("\nWorkflow ready for execution with LocalRuntime")


if __name__ == "__main__":
    # Run examples
    query_builder_examples()
    cross_database_examples()
    workflow_integration_example()

    print("\n✅ QueryBuilder examples completed!")
    print("\nNext steps:")
    print("1. Run with real database connection")
    print("2. Test with different database types")
    print("3. Integrate with Redis caching")
    print("4. Add to production workflows")
