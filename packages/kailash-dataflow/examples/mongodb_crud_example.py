"""
Complete MongoDB CRUD Example with DataFlow.

This example demonstrates:
1. Setting up MongoDB connection
2. Document CRUD operations
3. Query patterns and filters
4. Aggregation pipelines
5. Index management
6. Workflow integration

Prerequisites:
- MongoDB running locally or accessible via connection string
- DataFlow with MongoDB support installed
"""

import asyncio
from datetime import datetime

from dataflow import DataFlow
from dataflow.adapters import MongoDBAdapter
from dataflow.nodes.mongodb_nodes import (
    AggregateNode,
    BulkDocumentInsertNode,
    CreateIndexNode,
    DocumentCountNode,
    DocumentDeleteNode,
    DocumentFindNode,
    DocumentInsertNode,
    DocumentUpdateNode,
)

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder


async def setup_connection():
    """Step 1: Set up MongoDB connection and verify connectivity."""
    print("=" * 60)
    print("Step 1: MongoDB Connection Setup")
    print("=" * 60)

    # Create MongoDB adapter
    adapter = MongoDBAdapter(
        "mongodb://localhost:27017/dataflow_demo", maxPoolSize=50, minPoolSize=10
    )

    # Connect
    await adapter.connect()
    print("✓ Connected to MongoDB")

    # Health check
    health = await adapter.health_check()
    print(f"✓ Database: {health['database']}")
    print(f"✓ Collections: {health['collections_count']}")
    print(f"✓ Server Version: {health.get('server_version', 'N/A')}")

    return adapter


async def basic_crud_operations(adapter):
    """Step 2: Basic CRUD operations using adapter directly."""
    print("\n" + "=" * 60)
    print("Step 2: Basic CRUD Operations")
    print("=" * 60)

    # CREATE - Insert documents
    print("\n📝 Creating documents...")

    user1_id = await adapter.insert_one(
        "users",
        {
            "name": "Alice Johnson",
            "email": "alice@example.com",
            "age": 30,
            "role": "developer",
            "skills": ["python", "javascript", "mongodb"],
            "status": "active",
            "created_at": datetime.now().isoformat(),
        },
    )
    print(f"✓ Created user: {user1_id}")

    user2_id = await adapter.insert_one(
        "users",
        {
            "name": "Bob Smith",
            "email": "bob@example.com",
            "age": 25,
            "role": "designer",
            "skills": ["figma", "photoshop", "illustrator"],
            "status": "active",
            "created_at": datetime.now().isoformat(),
        },
    )
    print(f"✓ Created user: {user2_id}")

    # READ - Find documents
    print("\n🔍 Finding documents...")

    user = await adapter.find_one("users", {"email": "alice@example.com"})
    print(f"✓ Found user: {user['name']} ({user['role']})")

    active_users = await adapter.find(
        "users", filter={"status": "active"}, sort=[("name", 1)], limit=10
    )
    print(f"✓ Found {len(active_users)} active users")

    # UPDATE - Modify documents
    print("\n✏️  Updating documents...")

    result = await adapter.update_one(
        "users",
        {"email": "alice@example.com"},
        {"$set": {"age": 31, "last_login": datetime.now().isoformat()}},
    )
    print(f"✓ Updated {result['modified_count']} document(s)")

    # DELETE - Remove documents
    print("\n🗑️  Deleting documents...")

    # We'll create and then delete a test user
    test_id = await adapter.insert_one(
        "users",
        {"name": "Test User", "email": "test@example.com", "status": "inactive"},
    )

    count = await adapter.delete_one("users", {"email": "test@example.com"})
    print(f"✓ Deleted {count} document(s)")


async def query_patterns(adapter):
    """Step 3: Demonstrate various query patterns."""
    print("\n" + "=" * 60)
    print("Step 3: Query Patterns")
    print("=" * 60)

    # Comparison operators
    print("\n🔍 Comparison Operators:")
    users_over_25 = await adapter.find("users", {"age": {"$gte": 25}})
    print(f"  • Users age >= 25: {len(users_over_25)}")

    # Array operators
    print("\n🔍 Array Operators:")
    python_devs = await adapter.find("users", {"skills": "python"})
    print(f"  • Python developers: {len(python_devs)}")

    # Logical operators
    print("\n🔍 Logical Operators:")
    senior_devs = await adapter.find(
        "users", {"$and": [{"age": {"$gte": 30}}, {"role": "developer"}]}
    )
    print(f"  • Senior developers (age >= 30): {len(senior_devs)}")

    # Projection (select specific fields)
    print("\n🔍 Projection (Field Selection):")
    users = await adapter.find(
        "users", {"status": "active"}, projection={"name": 1, "email": 1, "_id": 0}
    )
    print(f"  • Users with name and email only: {len(users)}")
    if users:
        print(f"    Example: {users[0]}")


async def bulk_operations(adapter):
    """Step 4: Demonstrate bulk operations."""
    print("\n" + "=" * 60)
    print("Step 4: Bulk Operations")
    print("=" * 60)

    # Bulk insert products
    print("\n📦 Bulk Insert:")

    products = [
        {"name": "Laptop", "category": "electronics", "price": 1200, "stock": 15},
        {"name": "Mouse", "category": "electronics", "price": 25, "stock": 100},
        {"name": "Keyboard", "category": "electronics", "price": 75, "stock": 50},
        {"name": "Desk", "category": "furniture", "price": 300, "stock": 10},
        {"name": "Chair", "category": "furniture", "price": 200, "stock": 20},
    ]

    inserted_ids = await adapter.insert_many("products", products)
    print(f"✓ Inserted {len(inserted_ids)} products")

    # Bulk update
    print("\n✏️  Bulk Update:")

    result = await adapter.update_many(
        "products",
        {"category": "electronics"},
        {"$mul": {"price": 0.9}},  # 10% discount on electronics
    )
    print(f"✓ Applied discount to {result['modified_count']} products")

    # Count documents
    electronics_count = await adapter.count_documents(
        "products", {"category": "electronics"}
    )
    print(f"✓ Total electronics products: {electronics_count}")


async def aggregation_pipelines(adapter):
    """Step 5: Demonstrate aggregation pipelines."""
    print("\n" + "=" * 60)
    print("Step 5: Aggregation Pipelines")
    print("=" * 60)

    # Simple aggregation - group by category
    print("\n📊 Products by Category:")

    results = await adapter.aggregate(
        "products",
        [
            {
                "$group": {
                    "_id": "$category",
                    "total_products": {"$sum": 1},
                    "total_stock": {"$sum": "$stock"},
                    "avg_price": {"$avg": "$price"},
                }
            },
            {"$sort": {"total_products": -1}},
        ],
    )

    for result in results:
        print(
            f"  • {result['_id']}: {result['total_products']} products, "
            f"${result['avg_price']:.2f} avg price, "
            f"{result['total_stock']} total stock"
        )

    # Complex aggregation - statistics
    print("\n📊 Product Statistics:")

    stats = await adapter.aggregate(
        "products",
        [
            {
                "$group": {
                    "_id": None,
                    "total_products": {"$sum": 1},
                    "total_value": {"$sum": {"$multiply": ["$price", "$stock"]}},
                    "avg_price": {"$avg": "$price"},
                    "min_price": {"$min": "$price"},
                    "max_price": {"$max": "$price"},
                }
            }
        ],
    )

    if stats:
        stat = stats[0]
        print(f"  • Total Products: {stat['total_products']}")
        print(f"  • Total Inventory Value: ${stat['total_value']:.2f}")
        print(f"  • Average Price: ${stat['avg_price']:.2f}")
        print(f"  • Price Range: ${stat['min_price']:.2f} - ${stat['max_price']:.2f}")


async def index_management(adapter):
    """Step 6: Demonstrate index management."""
    print("\n" + "=" * 60)
    print("Step 6: Index Management")
    print("=" * 60)

    # Create single field index
    print("\n🔧 Creating Indexes:")

    index1 = await adapter.create_index(
        "users", [("email", 1)], unique=True, name="email_unique_idx"
    )
    print(f"✓ Created unique index: {index1}")

    # Create compound index
    index2 = await adapter.create_index(
        "users", [("role", 1), ("age", -1)], name="role_age_idx"
    )
    print(f"✓ Created compound index: {index2}")

    # Create text index for searching
    index3 = await adapter.create_index(
        "products", [("name", "text"), ("category", "text")], name="products_text_idx"
    )
    print(f"✓ Created text index: {index3}")

    # List all indexes
    print("\n📋 Current Indexes:")

    user_indexes = await adapter.list_indexes("users")
    print(f"  Users collection ({len(user_indexes)} indexes):")
    for idx in user_indexes:
        print(f"    - {idx['name']}: {idx['key']}")

    product_indexes = await adapter.list_indexes("products")
    print(f"  Products collection ({len(product_indexes)} indexes):")
    for idx in product_indexes:
        print(f"    - {idx['name']}: {idx['key']}")


async def workflow_integration(adapter):
    """Step 7: Demonstrate workflow integration with MongoDB nodes."""
    print("\n" + "=" * 60)
    print("Step 7: Workflow Integration")
    print("=" * 60)

    # Create workflow
    workflow = WorkflowBuilder()

    # Add nodes to workflow
    print("\n🔨 Building Workflow:")

    # 1. Create a new order
    workflow.add_node(
        "DocumentInsertNode",
        "create_order",
        {
            "collection": "orders",
            "document": {
                "customer_email": "alice@example.com",
                "items": [
                    {"product": "Laptop", "quantity": 1, "price": 1200},
                    {"product": "Mouse", "quantity": 2, "price": 25},
                ],
                "total": 1250,
                "status": "pending",
                "created_at": datetime.now().isoformat(),
            },
        },
    )
    print("  ✓ Added DocumentInsertNode")

    # 2. Find all pending orders
    workflow.add_node(
        "DocumentFindNode",
        "find_pending_orders",
        {
            "collection": "orders",
            "filter": {"status": "pending"},
            "sort": [("created_at", -1)],
            "limit": 10,
        },
    )
    print("  ✓ Added DocumentFindNode")

    # 3. Count active users
    workflow.add_node(
        "DocumentCountNode",
        "count_active_users",
        {"collection": "users", "filter": {"status": "active"}},
    )
    print("  ✓ Added DocumentCountNode")

    # 4. Aggregate orders by status
    workflow.add_node(
        "AggregateNode",
        "orders_by_status",
        {
            "collection": "orders",
            "pipeline": [
                {
                    "$group": {
                        "_id": "$status",
                        "count": {"$sum": 1},
                        "total_amount": {"$sum": "$total"},
                    }
                },
                {"$sort": {"count": -1}},
            ],
        },
    )
    print("  ✓ Added AggregateNode")

    # Execute workflow
    print("\n⚡ Executing Workflow:")

    runtime = AsyncLocalRuntime()
    results = await runtime.execute_workflow_async(workflow.build())

    # Display results
    print("\n📊 Workflow Results:")

    print("\n  Order Created:")
    print(f"    • ID: {results['create_order']['inserted_id']}")
    print(f"    • Collection: {results['create_order']['collection']}")

    print("\n  Pending Orders:")
    print(f"    • Found: {results['find_pending_orders']['count']} orders")

    print("\n  Active Users:")
    print(f"    • Count: {results['count_active_users']['count']}")

    print("\n  Orders by Status:")
    for order_stat in results["orders_by_status"]["results"]:
        print(
            f"    • {order_stat['_id']}: {order_stat['count']} orders, "
            f"${order_stat['total_amount']:.2f} total"
        )


async def cleanup(adapter):
    """Step 8: Cleanup demo data."""
    print("\n" + "=" * 60)
    print("Step 8: Cleanup")
    print("=" * 60)

    print("\n🧹 Cleaning up demo collections...")

    # Drop demo collections
    collections = ["users", "products", "orders"]
    for collection in collections:
        try:
            await adapter.drop_collection(collection)
            print(f"✓ Dropped collection: {collection}")
        except Exception as e:
            print(f"⚠️  Collection {collection}: {e}")

    # Disconnect
    await adapter.disconnect()
    print("\n✓ Disconnected from MongoDB")


async def main():
    """Run complete MongoDB CRUD example."""
    print("\n" + "=" * 60)
    print("MongoDB CRUD Example - Complete Demonstration")
    print("=" * 60)

    try:
        # Step 1: Setup connection
        adapter = await setup_connection()

        # Step 2: Basic CRUD
        await basic_crud_operations(adapter)

        # Step 3: Query patterns
        await query_patterns(adapter)

        # Step 4: Bulk operations
        await bulk_operations(adapter)

        # Step 5: Aggregation pipelines
        await aggregation_pipelines(adapter)

        # Step 6: Index management
        await index_management(adapter)

        # Step 7: Workflow integration
        await workflow_integration(adapter)

        # Step 8: Cleanup
        await cleanup(adapter)

        print("\n" + "=" * 60)
        print("✅ Example Complete!")
        print("=" * 60)
        print("\nNext Steps:")
        print("1. Explore MongoDB query language in docs/guides/mongodb-quickstart.md")
        print("2. Learn aggregation pipelines in docs/guides/mongodb-aggregation.md")
        print("3. Compare with SQL in docs/guides/mongodb-vs-sql.md")
        print("4. Build your own MongoDB workflows with DataFlow!")

    except ConnectionError as e:
        print(f"\n❌ Connection Error: {e}")
        print("\nMake sure:")
        print('1. MongoDB is running (mongosh --eval "db.version()")')
        print("2. Connection string is correct")
        print("3. MongoDB is accessible on the specified port")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("1. Check MongoDB logs")
        print("2. Verify DataFlow installation (pip install kailash-dataflow>=0.7.0)")
        print("3. Review docs/guides/mongodb-quickstart.md")
        raise


if __name__ == "__main__":
    # Run the example
    asyncio.run(main())
