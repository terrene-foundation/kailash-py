# MongoDB Quickstart Guide

Complete guide to using MongoDB with DataFlow for document database operations.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Basic Setup](#basic-setup)
5. [Document Operations](#document-operations)
6. [Querying Documents](#querying-documents)
7. [Aggregation Pipelines](#aggregation-pipelines)
8. [Indexing](#indexing)
9. [Workflow Integration](#workflow-integration)
10. [Complete Example](#complete-example)
11. [Best Practices](#best-practices)
12. [Troubleshooting](#troubleshooting)

---

## Overview

DataFlow's MongoDB support provides:
- **Document Database Operations**: CRUD operations for flexible schema documents
- **Aggregation Pipelines**: Complex data processing and transformations
- **Motor Async Driver**: Production-ready async MongoDB operations
- **Workflow Nodes**: 8 specialized nodes for MongoDB operations
- **MongoDB Query Language**: Full support for MongoDB's powerful query syntax

### Key Differences from SQL

| Feature | SQL (PostgreSQL/MySQL) | MongoDB |
|---------|----------------------|---------|
| Data Model | Relational (tables, rows) | Document (collections, documents) |
| Schema | Fixed schema | Flexible schema |
| Query Language | SQL | MongoDB Query Language |
| JOINs | SQL JOINs | Aggregation pipelines |
| Transactions | Always available | Replica sets only |
| Best For | Structured data, complex relationships | Semi-structured data, rapid iteration |

---

## Prerequisites

### MongoDB Installation

**macOS** (via Homebrew):
```bash
brew tap mongodb/brew
brew install mongodb-community@7.0
brew services start mongodb-community@7.0
```

**Ubuntu/Debian**:
```bash
wget -qO - https://www.mongodb.org/static/pgp/server-7.0.asc | sudo apt-key add -
echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
sudo apt-get update
sudo apt-get install -y mongodb-org
sudo systemctl start mongod
```

**Docker** (recommended for development):
```bash
docker run -d \
  --name mongodb \
  -p 27017:27017 \
  -e MONGO_INITDB_ROOT_USERNAME=admin \
  -e MONGO_INITDB_ROOT_PASSWORD=password \
  mongo:7.0
```

### Verify Installation

```bash
# Check MongoDB is running
mongosh --eval "db.version()"
# Should output: 7.0.x
```

---

## Installation

Install DataFlow with MongoDB support:

```bash
pip install kailash-dataflow>=0.7.0
```

Dependencies installed automatically:
- `motor>=3.3.0` - Async MongoDB driver
- `pymongo>=4.5.0` - Motor dependency
- `dnspython>=2.4.0` - For mongodb+srv:// URLs

---

## Basic Setup

### 1. Create MongoDB Adapter

```python
from dataflow.adapters import MongoDBAdapter

# Local MongoDB
adapter = MongoDBAdapter("mongodb://localhost:27017/mydb")

# With authentication
adapter = MongoDBAdapter(
    "mongodb://admin:password@localhost:27017/mydb?authSource=admin"
)

# MongoDB Atlas (cloud)
adapter = MongoDBAdapter(
    "mongodb+srv://username:password@cluster.mongodb.net/mydb"
)

# Custom configuration
adapter = MongoDBAdapter(
    "mongodb://localhost:27017/mydb",
    maxPoolSize=50,
    minPoolSize=10,
    serverSelectionTimeoutMS=5000
)
```

### 2. Connect to MongoDB

```python
import asyncio

async def main():
    # Connect
    await adapter.connect()

    # Health check
    health = await adapter.health_check()
    print(f"Connected: {health['connected']}")
    print(f"Database: {health['database']}")
    print(f"Collections: {health['collections_count']}")

    # Your operations here...

    # Disconnect when done
    await adapter.disconnect()

asyncio.run(main())
```

### 3. Basic Document Operations

```python
async def basic_operations():
    await adapter.connect()

    # Insert document
    user_id = await adapter.insert_one(
        "users",
        {
            "name": "Alice",
            "email": "alice@example.com",
            "age": 30,
            "tags": ["developer", "python"]
        }
    )
    print(f"Inserted user: {user_id}")

    # Find document
    user = await adapter.find_one("users", {"email": "alice@example.com"})
    print(f"Found user: {user['name']}")

    # Update document
    result = await adapter.update_one(
        "users",
        {"email": "alice@example.com"},
        {"$set": {"age": 31, "status": "active"}}
    )
    print(f"Updated {result['modified_count']} document(s)")

    # Delete document
    count = await adapter.delete_one("users", {"email": "alice@example.com"})
    print(f"Deleted {count} document(s)")

    await adapter.disconnect()

asyncio.run(basic_operations())
```

---

## Document Operations

### Insert Operations

**Single Insert**:
```python
# Insert one document
user_id = await adapter.insert_one(
    "users",
    {
        "name": "Bob",
        "email": "bob@example.com",
        "profile": {
            "age": 25,
            "city": "NYC",
            "interests": ["music", "sports"]
        }
    }
)
```

**Bulk Insert**:
```python
# Insert multiple documents
users = [
    {"name": "Alice", "email": "alice@example.com", "age": 30},
    {"name": "Bob", "email": "bob@example.com", "age": 25},
    {"name": "Charlie", "email": "charlie@example.com", "age": 35}
]

inserted_ids = await adapter.insert_many("users", users)
print(f"Inserted {len(inserted_ids)} users")
```

### Find Operations

**Find One**:
```python
# Find single document
user = await adapter.find_one("users", {"email": "alice@example.com"})

# With projection (select specific fields)
user = await adapter.find_one(
    "users",
    {"email": "alice@example.com"},
    projection={"name": 1, "email": 1, "_id": 0}
)
```

**Find Many**:
```python
# Find all active users
users = await adapter.find(
    "users",
    filter={"status": "active"},
    sort=[("name", 1)],  # 1 = ascending, -1 = descending
    limit=10,
    skip=0
)

# Find with complex filter
senior_devs = await adapter.find(
    "users",
    filter={
        "age": {"$gte": 30},
        "tags": {"$in": ["developer", "engineer"]},
        "status": {"$ne": "inactive"}
    }
)
```

### Update Operations

**Update One**:
```python
# Update single document
result = await adapter.update_one(
    "users",
    {"email": "alice@example.com"},
    {"$set": {"status": "active", "last_login": "2024-01-15"}}
)
print(f"Matched: {result['matched_count']}, Modified: {result['modified_count']}")
```

**Update Many**:
```python
# Update multiple documents
result = await adapter.update_many(
    "users",
    {"status": "inactive"},
    {"$set": {"archived": True, "archived_date": "2024-01-15"}}
)
print(f"Updated {result['modified_count']} users")
```

**Upsert** (Update or Insert):
```python
# Create if doesn't exist
result = await adapter.update_one(
    "users",
    {"email": "new@example.com"},
    {"$set": {"name": "New User", "status": "active"}},
    upsert=True
)
if result['upserted_id']:
    print(f"Created new user: {result['upserted_id']}")
```

**Update Operators**:
```python
# Increment age
await adapter.update_one(
    "users",
    {"email": "alice@example.com"},
    {"$inc": {"age": 1, "login_count": 1}}
)

# Add to array
await adapter.update_one(
    "users",
    {"email": "alice@example.com"},
    {"$push": {"tags": "python-expert"}}
)

# Remove from array
await adapter.update_one(
    "users",
    {"email": "alice@example.com"},
    {"$pull": {"tags": "beginner"}}
)
```

### Delete Operations

**Delete One**:
```python
count = await adapter.delete_one("users", {"email": "alice@example.com"})
```

**Delete Many**:
```python
# Delete all inactive users
count = await adapter.delete_many(
    "users",
    {"status": "inactive", "last_login": {"$lt": "2023-01-01"}}
)
print(f"Deleted {count} inactive users")
```

---

## Querying Documents

### MongoDB Query Operators

**Comparison Operators**:
```python
# Equal
{"age": {"$eq": 30}}  # or simply {"age": 30}

# Greater than / Less than
{"age": {"$gt": 25}}   # >25
{"age": {"$gte": 25}}  # >=25
{"age": {"$lt": 50}}   # <50
{"age": {"$lte": 50}}  # <=50

# Not equal
{"status": {"$ne": "inactive"}}

# In array
{"role": {"$in": ["admin", "moderator"]}}

# Not in array
{"status": {"$nin": ["banned", "suspended"]}}
```

**Logical Operators**:
```python
# AND (implicit)
{"status": "active", "age": {"$gte": 18}}

# OR
{"$or": [
    {"status": "active"},
    {"status": "premium"}
]}

# AND + OR
{"$and": [
    {"age": {"$gte": 18}},
    {"$or": [{"role": "admin"}, {"role": "moderator"}]}
]}

# NOT
{"age": {"$not": {"$lt": 18}}}
```

**Element Operators**:
```python
# Field exists
{"email": {"$exists": True}}

# Field type
{"age": {"$type": "int"}}
```

**Array Operators**:
```python
# Array contains value
{"tags": "python"}

# Array contains any of values
{"tags": {"$in": ["python", "javascript"]}}

# Array contains all values
{"tags": {"$all": ["python", "developer"]}}

# Array size
{"tags": {"$size": 3}}
```

**Text Search**:
```python
# First create text index
await adapter.create_index(
    "articles",
    [("content", "text")],
    name="content_text"
)

# Then search
articles = await adapter.find(
    "articles",
    {"$text": {"$search": "python tutorial"}}
)
```

---

## Aggregation Pipelines

Aggregation pipelines process documents through multiple stages for complex data transformations.

### Basic Aggregation

```python
# Sales by category
results = await adapter.aggregate(
    "orders",
    [
        # Stage 1: Filter completed orders
        {"$match": {"status": "completed"}},

        # Stage 2: Group by category
        {"$group": {
            "_id": "$category",
            "total_sales": {"$sum": "$amount"},
            "order_count": {"$sum": 1},
            "avg_order": {"$avg": "$amount"}
        }},

        # Stage 3: Sort by total sales
        {"$sort": {"total_sales": -1}},

        # Stage 4: Limit to top 10
        {"$limit": 10}
    ]
)

for result in results:
    print(f"{result['_id']}: ${result['total_sales']:.2f}")
```

### Advanced Aggregation

**Lookup (JOIN)**:
```python
# Join users with their orders
results = await adapter.aggregate(
    "users",
    [
        {"$match": {"status": "active"}},

        # Join with orders collection
        {"$lookup": {
            "from": "orders",
            "localField": "_id",
            "foreignField": "user_id",
            "as": "orders"
        }},

        # Add computed fields
        {"$addFields": {
            "order_count": {"$size": "$orders"},
            "total_spent": {"$sum": "$orders.amount"}
        }},

        # Project specific fields
        {"$project": {
            "name": 1,
            "email": 1,
            "order_count": 1,
            "total_spent": 1
        }}
    ]
)
```

**Unwind Arrays**:
```python
# Flatten array of tags
results = await adapter.aggregate(
    "articles",
    [
        # Unwind tags array
        {"$unwind": "$tags"},

        # Group by tag
        {"$group": {
            "_id": "$tags",
            "article_count": {"$sum": 1}
        }},

        # Sort by count
        {"$sort": {"article_count": -1}}
    ]
)
```

**Bucket (Histogram)**:
```python
# Age distribution
results = await adapter.aggregate(
    "users",
    [
        {"$bucket": {
            "groupBy": "$age",
            "boundaries": [0, 18, 30, 50, 100],
            "default": "Other",
            "output": {
                "count": {"$sum": 1},
                "users": {"$push": "$name"}
            }
        }}
    ]
)
```

---

## Indexing

### Create Indexes

**Single Field Index**:
```python
# Create index on email field
index_name = await adapter.create_index(
    "users",
    [("email", 1)],  # 1 = ascending, -1 = descending
    unique=True
)
```

**Compound Index**:
```python
# Create compound index
index_name = await adapter.create_index(
    "users",
    [("last_name", 1), ("first_name", 1)],
    name="full_name_idx"
)
```

**Text Index**:
```python
# Create text index for full-text search
index_name = await adapter.create_index(
    "articles",
    [("title", "text"), ("content", "text")],
    name="articles_text_idx"
)
```

**Geospatial Index**:
```python
# Create 2dsphere index for location queries
index_name = await adapter.create_index(
    "places",
    [("location", "2dsphere")],
    name="location_idx"
)
```

### Manage Indexes

**List Indexes**:
```python
indexes = await adapter.list_indexes("users")
for index in indexes:
    print(f"{index['name']}: {index['key']}")
```

**Drop Index**:
```python
await adapter.drop_index("users", "email_1")
```

---

## Workflow Integration

### Using MongoDB Nodes in Workflows

```python
from dataflow import DataFlow
from dataflow.adapters import MongoDBAdapter
from dataflow.nodes.mongodb_nodes import (
    DocumentInsertNode,
    DocumentFindNode,
    DocumentUpdateNode,
    AggregateNode
)
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime

# Setup
adapter = MongoDBAdapter("mongodb://localhost:27017/mydb")
db = DataFlow(adapter=adapter)
await db.initialize()

workflow = WorkflowBuilder()

# Insert user
workflow.add_node("DocumentInsertNode", "create_user", {
    "collection": "users",
    "document": {
        "name": "Alice",
        "email": "alice@example.com",
        "status": "active"
    }
})

# Find active users
workflow.add_node("DocumentFindNode", "find_active", {
    "collection": "users",
    "filter": {"status": "active"},
    "sort": [("name", 1)],
    "limit": 10
})

# Aggregate sales by category
workflow.add_node("AggregateNode", "sales_by_category", {
    "collection": "orders",
    "pipeline": [
        {"$match": {"status": "completed"}},
        {"$group": {
            "_id": "$category",
            "total": {"$sum": "$amount"}
        }},
        {"$sort": {"total": -1}}
    ]
})

# Execute workflow
runtime = AsyncLocalRuntime()
results = await runtime.execute_workflow_async(workflow.build())

print(f"Created user: {results['create_user']['inserted_id']}")
print(f"Found {results['find_active']['count']} active users")
print(f"Sales results: {results['sales_by_category']['count']} categories")
```

### All MongoDB Nodes

1. **DocumentInsertNode** - Insert single document
2. **DocumentFindNode** - Find documents with filters
3. **DocumentUpdateNode** - Update documents
4. **DocumentDeleteNode** - Delete documents
5. **AggregateNode** - Aggregation pipelines
6. **BulkDocumentInsertNode** - Bulk insert
7. **CreateIndexNode** - Create indexes
8. **DocumentCountNode** - Count documents

---

## Complete Example

See `examples/mongodb_crud_example.py` for a complete end-to-end example demonstrating:
- Connection setup
- CRUD operations
- Query patterns
- Aggregation pipelines
- Index management
- Error handling

---

## Best Practices

### 1. Connection Management

```python
# Use context managers for automatic cleanup
class MongoDBContext:
    def __init__(self, adapter):
        self.adapter = adapter

    async def __aenter__(self):
        await self.adapter.connect()
        return self.adapter

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.adapter.disconnect()

# Usage
async with MongoDBContext(adapter) as db:
    users = await db.find("users", {"status": "active"})
```

### 2. Indexing Strategy

- **Create indexes for frequently queried fields**
- **Use compound indexes for multi-field queries**
- **Monitor index usage**: `db.collection.stats()`
- **Avoid too many indexes** (slows down writes)

### 3. Query Optimization

```python
# ✅ GOOD - Use projection to limit fields
users = await adapter.find(
    "users",
    {"status": "active"},
    projection={"name": 1, "email": 1}
)

# ❌ BAD - Fetching all fields unnecessarily
users = await adapter.find("users", {"status": "active"})
```

### 4. Aggregation Performance

```python
# Use $match early in pipeline to reduce documents
pipeline = [
    {"$match": {"status": "active"}},  # Filter first
    {"$group": {...}},                 # Then group
    {"$sort": {...}},                  # Then sort
]

# Enable disk use for large aggregations
results = await adapter.aggregate(
    "orders",
    pipeline,
    allowDiskUse=True
)
```

### 5. Error Handling

```python
from pymongo.errors import DuplicateKeyError, ConnectionFailure

try:
    await adapter.insert_one("users", {
        "email": "duplicate@example.com"
    })
except DuplicateKeyError:
    print("User with this email already exists")
except ConnectionFailure:
    print("Failed to connect to MongoDB")
except Exception as e:
    print(f"Unexpected error: {e}")
```

---

## Troubleshooting

### Connection Issues

**Problem**: `ConnectionFailure: [Errno 61] Connection refused`

**Solution**:
```bash
# Check if MongoDB is running
mongosh --eval "db.version()"

# Start MongoDB (macOS)
brew services start mongodb-community

# Start MongoDB (Linux)
sudo systemctl start mongod

# Check MongoDB logs
tail -f /usr/local/var/log/mongodb/mongo.log
```

### Authentication Errors

**Problem**: `OperationFailure: Authentication failed`

**Solution**:
```python
# Ensure correct auth credentials and authSource
adapter = MongoDBAdapter(
    "mongodb://user:password@localhost:27017/mydb?authSource=admin"
)
```

### Performance Issues

**Problem**: Slow queries

**Solutions**:
1. **Create indexes** on frequently queried fields
2. **Use explain()** to analyze query performance
3. **Add pagination** with limit/skip
4. **Use aggregation** instead of find + processing

### Schema Validation Errors

**Problem**: Document doesn't match expected structure

**Solution**:
```python
# MongoDB is schemaless, but you can add validation
await adapter.create_collection(
    "users",
    validator={
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["name", "email"],
            "properties": {
                "name": {"bsonType": "string"},
                "email": {"bsonType": "string"}
            }
        }
    }
)
```

---

## Next Steps

- **Read**: [MongoDB Aggregation Guide](mongodb-aggregation.md)
- **Read**: [MongoDB vs SQL Guide](mongodb-vs-sql.md)
- **Example**: `examples/mongodb_crud_example.py`
- **Example**: `examples/mongodb_aggregation_example.py`

---

**Version**: DataFlow v0.7.0+
**Last Updated**: 2025-10-21
