"""
DataFlow QueryBuilder Usage Examples

Demonstrates MongoDB-style query building with DataFlow models.
"""

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow


def basic_query_example():
    """Basic QueryBuilder usage with a model."""
    db = DataFlow()

    @db.model
    class User:
        name: str
        email: str
        age: int
        status: str = "active"
        premium: bool = False

    # Get QueryBuilder instance from model
    builder = User.query_builder()

    # Simple equality query
    builder.where("status", "$eq", "active")
    sql, params = builder.build_select()
    print(f"Simple query: {sql}")
    print(f"Parameters: {params}")

    # Reset for new query
    builder.reset()

    # Complex query with multiple conditions
    builder.where("age", "$gte", 18)
    builder.where("status", "$in", ["active", "premium"])
    builder.where("email", "$like", "%@company.com")
    builder.order_by("created_at", "DESC")
    builder.limit(10)

    sql, params = builder.build_select()
    print(f"\nComplex query: {sql}")
    print(f"Parameters: {params}")


def advanced_operators_example():
    """Demonstrate all MongoDB-style operators."""
    db = DataFlow()

    @db.model
    class Product:
        name: str
        price: float
        category: str
        in_stock: bool = True
        tags: str = None

    builder = Product.query_builder()

    # Comparison operators
    print("\n=== Comparison Operators ===")

    # $gt, $gte, $lt, $lte
    builder.where("price", "$gt", 100)
    builder.where("price", "$lte", 1000)
    sql, params = builder.build_select()
    print(f"Price range: {sql}")

    builder.reset()

    # $ne (not equal)
    builder.where("category", "$ne", "deprecated")
    sql, params = builder.build_select()
    print(f"Not equal: {sql}")

    # List operators
    print("\n=== List Operators ===")
    builder.reset()

    # $in
    builder.where("category", "$in", ["electronics", "computers", "phones"])
    sql, params = builder.build_select()
    print(f"IN operator: {sql}")

    # $nin (not in)
    builder.reset()
    builder.where("category", "$nin", ["clearance", "discontinued"])
    sql, params = builder.build_select()
    print(f"NOT IN operator: {sql}")

    # Existence operators
    print("\n=== Existence Operators ===")
    builder.reset()

    # $exists
    builder.where("tags", "$exists", None)
    sql, params = builder.build_select()
    print(f"EXISTS: {sql}")

    # $null
    builder.reset()
    builder.where("tags", "$null", None)
    sql, params = builder.build_select()
    print(f"IS NULL: {sql}")

    # Pattern matching
    print("\n=== Pattern Matching ===")
    builder.reset()

    # $like
    builder.where("name", "$like", "iPhone%")
    sql, params = builder.build_select()
    print(f"LIKE: {sql}")

    # $regex (PostgreSQL)
    builder.reset()
    builder.where("name", "$regex", "^(iPhone|iPad)")
    sql, params = builder.build_select()
    print(f"REGEX: {sql}")


def workflow_integration_example():
    """Using QueryBuilder with DataFlow workflows."""
    db = DataFlow()

    @db.model
    class Order:
        customer_id: int
        total: float
        status: str = "pending"
        created_at: str
        shipped_at: str = None

    # Create workflow with advanced filtering
    workflow = WorkflowBuilder()

    # Find high-value pending orders
    workflow.add_node(
        "OrderListNode",
        "high_value_pending",
        {
            "filter": {
                "status": "pending",
                "total": {"$gte": 500.0},
                "created_at": {"$gte": "2025-01-01"},
            },
            "order_by": [{"total": -1}],  # Descending by total
            "limit": 20,
        },
    )

    # Find orders ready to ship
    workflow.add_node(
        "OrderListNode",
        "ready_to_ship",
        {
            "filter": {
                "status": {"$in": ["paid", "processing"]},
                "shipped_at": {"$null": None},
            },
            "order_by": [{"created_at": 1}],  # Oldest first
            "limit": 50,
        },
    )

    # Connect the nodes
    workflow.add_connection("high_value_pending", "ready_to_ship")

    # Build workflow
    built_workflow = workflow.build()
    print("\n=== Workflow with QueryBuilder ===")
    print(f"Workflow nodes: {list(built_workflow['nodes'].keys())}")

    # In a real application with database:
    # runtime = LocalRuntime()
    # results, run_id = runtime.execute(built_workflow)


def multi_database_example():
    """Demonstrate QueryBuilder with different databases."""
    print("\n=== Multi-Database Support ===")

    # PostgreSQL
    pg_db = DataFlow(database_url="postgresql://localhost/mydb")

    @pg_db.model
    class PgUser:
        username: str
        email: str

    pg_builder = PgUser.query_builder()
    pg_builder.where("username", "$regex", "^admin")
    sql, params = pg_builder.build_select()
    print(f"PostgreSQL regex: {sql}")

    # MySQL
    mysql_db = DataFlow(database_url="mysql://localhost/mydb")

    @mysql_db.model
    class MysqlUser:
        username: str
        email: str

    mysql_builder = MysqlUser.query_builder()
    mysql_builder.where("username", "$regex", "^admin")
    sql, params = mysql_builder.build_select()
    print(f"MySQL regex: {sql}")

    # SQLite
    sqlite_db = DataFlow(database_url="sqlite:///mydb.sqlite")

    @sqlite_db.model
    class SqliteUser:
        username: str
        email: str

    sqlite_builder = SqliteUser.query_builder()
    sqlite_builder.where("username", "$regex", ".*admin.*")
    sql, params = sqlite_builder.build_select()
    print(f"SQLite regex (converted to LIKE): {sql}")


def crud_operations_example():
    """Using QueryBuilder for all CRUD operations."""
    db = DataFlow()

    @db.model
    class Article:
        title: str
        content: str
        author_id: int
        published: bool = False
        views: int = 0

    builder = Article.query_builder()

    print("\n=== CRUD Operations ===")

    # INSERT
    article_data = {
        "title": "Getting Started with DataFlow",
        "content": "DataFlow is a powerful database framework...",
        "author_id": 42,
        "published": True,
    }
    sql, params = builder.build_insert(article_data)
    print(f"INSERT: {sql}")
    print(f"Values: {params}")

    # UPDATE
    builder.reset()
    builder.where("id", "$eq", 123)
    update_data = {"views": 1000, "published": True}
    sql, params = builder.build_update(update_data)
    print(f"\nUPDATE: {sql}")
    print(f"Values: {params}")

    # DELETE
    builder.reset()
    builder.where("published", "$eq", False)
    builder.where("created_at", "$lt", "2024-01-01")
    sql, params = builder.build_delete()
    print(f"\nDELETE: {sql}")
    print(f"Conditions: {params}")


def join_and_aggregation_example():
    """Advanced queries with joins and aggregation."""
    db = DataFlow()

    @db.model
    class OrderItem:
        order_id: int
        product_id: int
        quantity: int
        unit_price: float

    builder = OrderItem.query_builder()

    print("\n=== Joins and Aggregation ===")

    # Query with joins
    builder.select(
        [
            "order_items.quantity",
            "order_items.unit_price",
            "orders.status",
            "products.name AS product_name",
        ]
    )
    builder.join("orders", "orders.id = order_items.order_id")
    builder.join("products", "products.id = order_items.product_id")
    builder.where("orders.status", "$eq", "completed")
    builder.where("order_items.quantity", "$gte", 5)
    builder.order_by("order_items.quantity", "DESC")
    builder.limit(100)

    sql, params = builder.build_select()
    print(f"Join query: {sql}")
    print(f"Parameters: {params}")

    # Aggregation query
    builder.reset()
    builder.select(
        [
            "product_id",
            "SUM(quantity) AS total_quantity",
            "AVG(unit_price) AS avg_price",
        ]
    )
    builder.group_by("product_id")
    builder.having("SUM(quantity) > 100")

    sql, params = builder.build_select()
    print(f"\nAggregation query: {sql}")


if __name__ == "__main__":
    print("=== DataFlow QueryBuilder Examples ===\n")

    # Run all examples
    basic_query_example()
    advanced_operators_example()
    workflow_integration_example()
    multi_database_example()
    crud_operations_example()
    join_and_aggregation_example()

    print("\n=== Examples Complete ===")
    print("Note: These examples show SQL generation.")
    print(
        "With a real database connection, these queries would execute and return data."
    )
