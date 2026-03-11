# MongoDB Implementation Plan - MongoDBAdapter

Complete specification for MongoDB document database support in DataFlow.

## Overview

Implement MongoDB adapter with Motor (async MongoDB driver) for document-based operations, enabling flexible schema applications, aggregation pipelines, and NoSQL patterns in DataFlow.

## Objectives

1. Extend BaseAdapter (not DatabaseAdapter) with MongoDB operations
2. Create 8 MongoDB-specific workflow nodes
3. Integrate seamlessly with DataFlow ecosystem
4. Maintain 100% backward compatibility
5. Support both standalone and replica set configurations

## Architecture

### MongoDBAdapter (Extends BaseAdapter)

```python
from dataflow.adapters.base_adapter import BaseAdapter
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

class MongoDBAdapter(BaseAdapter):
    """MongoDB document database adapter using Motor async driver.

    Key Differences from SQL Adapters:
    - Document-based, not relational
    - Flexible schema (schemaless)
    - No SQL queries (MongoDB query language)
    - Aggregation pipelines instead of JOINs
    - Different indexing strategies
    """

    def __init__(self, connection_string: str, **kwargs):
        """
        Initialize MongoDB adapter.

        Args:
            connection_string: MongoDB connection string
                - mongodb://localhost:27017/mydb (standalone)
                - mongodb://user:pass@localhost:27017/mydb?authSource=admin
                - mongodb+srv://cluster.mongodb.net/mydb (Atlas)
            database_name: Database name (optional, can be in connection string)
            **kwargs: Additional Motor client options
        """
        self.connection_string = connection_string
        self.database_name = kwargs.pop("database_name", None)
        self.client_options = kwargs

        self._client: AsyncIOMotorClient = None
        self._db: AsyncIOMotorDatabase = None
        self._connected = False

    @property
    def adapter_type(self) -> str:
        """Get adapter type category."""
        return "document"  # Not "sql"

    @property
    def database_type(self) -> str:
        """Get specific database type identifier."""
        return "mongodb"
```

### Key Methods

#### Connection Management
```python
async def connect(self) -> None:
    """Establish MongoDB connection."""

async def disconnect(self) -> None:
    """Close MongoDB connection."""

async def health_check(self) -> Dict[str, Any]:
    """Check MongoDB connection and server status."""
```

#### Document Operations
```python
async def insert_one(self, collection: str, document: dict) -> str:
    """Insert single document, return inserted_id."""

async def insert_many(self, collection: str, documents: list[dict]) -> list[str]:
    """Bulk insert documents, return inserted_ids."""

async def find_one(self, collection: str, filter: dict) -> Optional[dict]:
    """Find single document by filter."""

async def find(self, collection: str, filter: dict = {}, **options) -> list[dict]:
    """Find multiple documents with pagination."""

async def update_one(self, collection: str, filter: dict, update: dict) -> dict:
    """Update single document."""

async def update_many(self, collection: str, filter: dict, update: dict) -> dict:
    """Update multiple documents."""

async def delete_one(self, collection: str, filter: dict) -> int:
    """Delete single document, return count."""

async def delete_many(self, collection: str, filter: dict) -> int:
    """Delete multiple documents, return count."""

async def count_documents(self, collection: str, filter: dict = {}) -> int:
    """Count documents matching filter."""

async def aggregate(self, collection: str, pipeline: list[dict]) -> list[dict]:
    """Execute aggregation pipeline."""
```

#### Index Management
```python
async def create_index(self, collection: str, keys: list[tuple], **options):
    """Create index on collection."""

async def create_indexes(self, collection: str, indexes: list[dict]):
    """Create multiple indexes."""

async def list_indexes(self, collection: str) -> list[dict]:
    """List all indexes on collection."""

async def drop_index(self, collection: str, index_name: str):
    """Drop specific index."""
```

#### Collection Management
```python
async def create_collection(self, collection: str, **options):
    """Create collection with validation schema (optional)."""

async def drop_collection(self, collection: str):
    """Drop collection."""

async def list_collections(self) -> list[str]:
    """List all collections in database."""

async def collection_exists(self, collection: str) -> bool:
    """Check if collection exists."""
```

### Feature Detection

```python
def supports_feature(self, feature: str) -> bool:
    """
    MongoDB feature detection.

    Supported features:
    - "documents": Document operations
    - "flexible_schema": Schemaless operations
    - "aggregation": Aggregation pipelines
    - "text_search": Full-text search
    - "geospatial": Geospatial queries
    - "transactions": Multi-document transactions (replica sets only)
    - "change_streams": Real-time data changes
    - "gridfs": Large file storage
    """
    mongodb_features = {
        "documents",
        "flexible_schema",
        "aggregation",
        "text_search",
        "geospatial",
        "transactions",
        "change_streams",
        "gridfs",
    }
    return feature in mongodb_features
```

## MongoDB Workflow Nodes

### 1. DocumentInsertNode
```python
@register_node()
class DocumentInsertNode(AsyncNode):
    """Insert single document into MongoDB collection."""

    parameters = {
        "collection": NodeParameter(str, required=True),
        "document": NodeParameter(dict, required=True),
        "bypass_document_validation": NodeParameter(bool, default=False),
    }

    async def async_run(self, **kwargs):
        adapter = self.dataflow_instance.adapter

        if not isinstance(adapter, MongoDBAdapter):
            raise ValueError("DocumentInsertNode requires MongoDBAdapter")

        result_id = await adapter.insert_one(
            collection=self.collection,
            document=validated_inputs["document"]
        )

        return {
            "success": True,
            "inserted_id": str(result_id),
            "collection": self.collection
        }
```

### 2. DocumentFindNode
```python
@register_node()
class DocumentFindNode(AsyncNode):
    """Find documents in MongoDB collection."""

    parameters = {
        "collection": NodeParameter(str, required=True),
        "filter": NodeParameter(dict, default={}),
        "projection": NodeParameter(dict, default=None),
        "sort": NodeParameter(list, default=None),
        "limit": NodeParameter(int, default=0),
        "skip": NodeParameter(int, default=0),
    }

    async def async_run(self, **kwargs):
        results = await adapter.find(
            collection=self.collection,
            filter=validated_inputs["filter"],
            projection=validated_inputs["projection"],
            sort=validated_inputs["sort"],
            limit=validated_inputs["limit"],
            skip=validated_inputs["skip"]
        )

        return {
            "documents": results,
            "count": len(results),
            "collection": self.collection
        }
```

### 3. DocumentUpdateNode
```python
@register_node()
class DocumentUpdateNode(AsyncNode):
    """Update documents in MongoDB collection."""

    parameters = {
        "collection": NodeParameter(str, required=True),
        "filter": NodeParameter(dict, required=True),
        "update": NodeParameter(dict, required=True),
        "upsert": NodeParameter(bool, default=False),
        "multi": NodeParameter(bool, default=False),
    }
```

### 4. DocumentDeleteNode
```python
@register_node()
class DocumentDeleteNode(AsyncNode):
    """Delete documents from MongoDB collection."""

    parameters = {
        "collection": NodeParameter(str, required=True),
        "filter": NodeParameter(dict, required=True),
        "multi": NodeParameter(bool, default=False),
    }
```

### 5. AggregateNode
```python
@register_node()
class AggregateNode(AsyncNode):
    """Execute MongoDB aggregation pipeline."""

    parameters = {
        "collection": NodeParameter(str, required=True),
        "pipeline": NodeParameter(list, required=True),
        "allow_disk_use": NodeParameter(bool, default=False),
    }

    # Example pipeline:
    # [
    #     {"$match": {"status": "active"}},
    #     {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
    #     {"$sort": {"total": -1}},
    #     {"$limit": 10}
    # ]
```

### 6. BulkDocumentInsertNode
```python
@register_node()
class BulkDocumentInsertNode(AsyncNode):
    """Bulk insert documents into MongoDB."""

    parameters = {
        "collection": NodeParameter(str, required=True),
        "documents": NodeParameter(list, required=True),
        "ordered": NodeParameter(bool, default=True),
        "bypass_document_validation": NodeParameter(bool, default=False),
    }
```

### 7. CreateIndexNode
```python
@register_node()
class CreateIndexNode(AsyncNode):
    """Create index on MongoDB collection."""

    parameters = {
        "collection": NodeParameter(str, required=True),
        "keys": NodeParameter(list, required=True),  # [("field", 1), ("field2", -1)]
        "unique": NodeParameter(bool, default=False),
        "sparse": NodeParameter(bool, default=False),
        "name": NodeParameter(str, default=None),
    }
```

### 8. DocumentCountNode
```python
@register_node()
class DocumentCountNode(AsyncNode):
    """Count documents in MongoDB collection."""

    parameters = {
        "collection": NodeParameter(str, required=True),
        "filter": NodeParameter(dict, default={}),
    }
```

## Integration with DataFlow

### Model Definition (Flexible Schema)
```python
from dataflow import DataFlow
from dataflow.adapters import MongoDBAdapter

adapter = MongoDBAdapter("mongodb://localhost:27017/mydb")
db = DataFlow(adapter=adapter)

# MongoDB models are more flexible
@db.model
class User:
    # Fields are optional in MongoDB (schemaless)
    # Type hints serve as documentation, not enforcement
    name: str
    email: str
    profile: dict  # Nested documents
    tags: list[str]  # Arrays
    # MongoDB will accept any fields, not just these
```

### Workflow Integration
```python
from dataflow.nodes.mongodb_nodes import DocumentInsertNode, DocumentFindNode
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime

workflow = WorkflowBuilder()

# Insert document
workflow.add_node("DocumentInsertNode", "insert", {
    "collection": "users",
    "document": {
        "name": "Alice",
        "email": "alice@example.com",
        "profile": {
            "age": 30,
            "city": "NYC"
        },
        "tags": ["developer", "python"]
    }
})

# Find documents
workflow.add_node("DocumentFindNode", "find", {
    "collection": "users",
    "filter": {"tags": {"$in": ["python"]}},
    "sort": [("name", 1)],
    "limit": 10
})

runtime = AsyncLocalRuntime()
results = await runtime.execute_workflow_async(workflow.build())
```

## Testing Strategy

### Unit Tests (Tier 1)
**File**: `tests/unit/adapters/test_mongodb_adapter.py`
- Adapter initialization
- Feature detection
- Method signatures
- Parameter validation
- Error handling (with mocks)

**File**: `tests/unit/nodes/test_mongodb_nodes.py`
- Node initialization
- Parameter definition
- Validation logic
- Error messages (with mocks)

### Integration Tests (Tier 2) - Real MongoDB
**File**: `tests/integration/adapters/test_mongodb_adapter_integration.py`
- Connection management
- Document CRUD operations
- Aggregation pipelines
- Index creation
- Bulk operations
- Transaction support (with replica set)

**File**: `tests/integration/nodes/test_mongodb_nodes_integration.py`
- Complete workflows with real MongoDB
- DataFlow integration
- Multi-step operations

### End-to-End Tests (Tier 3)
**File**: `tests/e2e/test_mongodb_workflows.py`
- Complete application scenarios
- User management workflow
- E-commerce catalog workflow
- Analytics aggregation workflow

## Dependencies

### Required Packages
```python
install_requires=[
    "kailash>=0.9.25",
    "motor>=3.3.0",  # Async MongoDB driver
    "pymongo>=4.5.0",  # Motor dependency
    "dnspython>=2.4.0",  # For mongodb+srv:// URLs
]
```

### Motor (Async MongoDB Driver)
- **Version**: 3.3.0+
- **Why**: Production-ready async driver
- **Features**: Full MongoDB protocol support, connection pooling

## Performance Targets

- **Connection Time**: <100ms to MongoDB
- **Insert Latency**: <10ms for single document
- **Bulk Insert**: >1000 docs/second
- **Query Latency**: <50ms for indexed queries
- **Aggregation**: <200ms for typical pipelines

## Documentation

### User Guides
- `docs/guides/mongodb-quickstart.md` - Getting started
- `docs/guides/mongodb-aggregation.md` - Aggregation pipelines
- `docs/guides/mongodb-vs-sql.md` - Migration from SQL

### Examples
- `examples/mongodb_crud_example.py` - Basic operations
- `examples/mongodb_aggregation_example.py` - Analytics
- `examples/mongodb_migration_example.py` - From SQL to MongoDB

## Timeline

- **Week 1, Day 1-2**: MongoDBAdapter implementation
- **Week 1, Day 3-4**: MongoDB workflow nodes
- **Week 1, Day 5**: Unit tests
- **Week 2, Day 1-2**: Integration tests with real MongoDB
- **Week 2, Day 3**: E2E tests
- **Week 2, Day 4-5**: Documentation and examples

**Total**: 2 weeks

## Success Criteria

✅ MongoDBAdapter extends BaseAdapter (not DatabaseAdapter)
✅ 8 MongoDB-specific workflow nodes
✅ 100% test coverage (unit + integration + E2E)
✅ Connection time <100ms
✅ Seamless DataFlow integration
✅ Comprehensive documentation
✅ Zero breaking changes

## Key Differences from SQL Adapters

| Aspect | SQL Adapters | MongoDB Adapter |
|--------|-------------|----------------|
| Base Class | DatabaseAdapter | BaseAdapter |
| Data Model | Relational (tables, rows) | Document (collections, documents) |
| Schema | Fixed schema | Flexible schema |
| Query Language | SQL | MongoDB query language |
| JOINs | SQL JOINs | Aggregation pipelines |
| Transactions | Always available | Replica sets only |
| Indexes | SQL indexes | MongoDB indexes |
| Operations | CRUD + SQL | CRUD + Aggregation |

---

**Status:** Ready to implement
**Risk:** LOW (Motor is production-ready)
**Value:** HIGH (enables NoSQL applications)
