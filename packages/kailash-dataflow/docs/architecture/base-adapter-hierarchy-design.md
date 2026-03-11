# BaseAdapter Hierarchy Design

## Overview

This document outlines the architectural design for the BaseAdapter hierarchy that will support multiple database types (SQL, Document, Vector, Graph, Key-Value) while maintaining 100% backward compatibility with existing DataFlow v0.5.6 code.

## Current Architecture (v0.5.6)

```
DatabaseAdapter (base.py:16-129)
├── PostgreSQLAdapter
├── MySQLAdapter
└── SQLiteAdapter
```

**Current Interface:**
- Connection management: `connect()`, `disconnect()`
- Query execution: `execute_query()`, `execute_transaction()`
- Schema operations: `get_table_schema()`, `create_table()`, `drop_table()`
- Feature detection: `supports_feature()`, `get_dialect()`
- SQL-specific: `get_tables_query()`, `get_columns_query()`

## Proposed Tiered Hierarchy

```
BaseAdapter (new - minimal interface)
│
├── DatabaseAdapter (existing - inherits from BaseAdapter)
│   ├── PostgreSQLAdapter
│   ├── PostgreSQLVectorAdapter (extends PostgreSQL + pgvector)
│   ├── TimescaleDBAdapter (extends PostgreSQL + time-series)
│   ├── MySQLAdapter
│   └── SQLiteAdapter
│
├── DocumentAdapter (new)
│   └── MongoDBAdapter (PyMongo Async API)
│
├── VectorAdapter (new)
│   ├── QdrantAdapter
│   ├── MilvusAdapter
│   └── WeaviateAdapter
│
├── GraphAdapter (new)
│   ├── Neo4jAdapter (Cypher)
│   └── ArangoDBAdapter (AQL)
│
└── KeyValueAdapter (new)
    ├── RedisAdapter
    └── DynamoDBAdapter
```

## Design Principles

1. **Minimal BaseAdapter**: Only essential methods all adapters must implement
2. **Specialized Subclasses**: DatabaseAdapter, DocumentAdapter, VectorAdapter, etc. add domain-specific methods
3. **100% Backward Compatibility**: Existing code continues to work unchanged
4. **Progressive Enhancement**: New adapters can add specialized nodes without breaking existing patterns
5. **Type Safety**: Clear interfaces for each adapter category

## BaseAdapter Interface (Minimal)

```python
class BaseAdapter(ABC):
    """Minimal base interface for all DataFlow adapters."""

    def __init__(self, connection_string: str, **kwargs):
        """Initialize adapter with connection string."""
        self.connection_string = connection_string
        self.is_connected = False
        self._config = kwargs

    @property
    @abstractmethod
    def adapter_type(self) -> str:
        """Get adapter type: 'sql', 'document', 'vector', 'graph', 'key-value'."""
        pass

    @property
    @abstractmethod
    def database_type(self) -> str:
        """Get specific database type: 'postgresql', 'mongodb', 'neo4j', etc."""
        pass

    @abstractmethod
    async def connect(self) -> None:
        """Establish database connection."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close database connection."""
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check database connection health."""
        pass

    @abstractmethod
    def supports_feature(self, feature: str) -> bool:
        """Check if database supports a specific feature."""
        pass
```

**Rationale:**
- **connection_string**: All databases need connection strings
- **adapter_type**: Categorize adapters for node generation
- **database_type**: Specific database identification
- **connect/disconnect**: Universal connection lifecycle
- **health_check**: Essential for monitoring
- **supports_feature**: Feature detection for progressive enhancement

## DatabaseAdapter (SQL-Specific)

```python
class DatabaseAdapter(BaseAdapter):
    """Adapter for SQL databases (PostgreSQL, MySQL, SQLite)."""

    @property
    def adapter_type(self) -> str:
        return "sql"

    @property
    @abstractmethod
    def default_port(self) -> int:
        """Get default port for database type."""
        pass

    @abstractmethod
    async def execute_query(self, query: str, params: List[Any] = None) -> List[Dict]:
        """Execute SQL query and return results."""
        pass

    @abstractmethod
    async def execute_transaction(self, queries: List[Tuple[str, List[Any]]]) -> List[Any]:
        """Execute multiple queries in a transaction."""
        pass

    @abstractmethod
    async def get_table_schema(self, table_name: str) -> Dict[str, Dict]:
        """Get table schema information."""
        pass

    @abstractmethod
    async def create_table(self, table_name: str, schema: Dict[str, Dict]) -> None:
        """Create a table with given schema."""
        pass

    @abstractmethod
    async def drop_table(self, table_name: str) -> None:
        """Drop a table."""
        pass

    @abstractmethod
    def get_dialect(self) -> str:
        """Get SQL dialect identifier."""
        pass
```

**Changes from Current:**
- Inherits from BaseAdapter (minimal changes)
- Adds `adapter_type` property (returns "sql")
- All existing methods preserved
- 100% backward compatible

## DocumentAdapter (MongoDB, CouchDB)

```python
class DocumentAdapter(BaseAdapter):
    """Adapter for document databases."""

    @property
    def adapter_type(self) -> str:
        return "document"

    @abstractmethod
    async def execute_operation(self, collection: str, operation: str,
                                 params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute document operation (insert, find, update, delete)."""
        pass

    @abstractmethod
    async def get_collection_schema(self, collection_name: str) -> Dict[str, Any]:
        """Get collection schema (if applicable)."""
        pass

    @abstractmethod
    async def create_collection(self, collection_name: str,
                                 schema: Optional[Dict] = None) -> None:
        """Create collection with optional schema validation."""
        pass

    @abstractmethod
    async def drop_collection(self, collection_name: str) -> None:
        """Drop collection."""
        pass

    @abstractmethod
    async def create_index(self, collection_name: str,
                           index_spec: Dict[str, Any]) -> None:
        """Create index on collection."""
        pass
```

**CRUD Mapping:**
- CREATE → execute_operation("collection", "insert_one", {doc})
- READ → execute_operation("collection", "find_one", {filter})
- UPDATE → execute_operation("collection", "update_one", {filter, update})
- DELETE → execute_operation("collection", "delete_one", {filter})
- LIST → execute_operation("collection", "find", {filter})

## VectorAdapter (Qdrant, Milvus, Weaviate)

```python
class VectorAdapter(BaseAdapter):
    """Adapter for vector databases."""

    @property
    def adapter_type(self) -> str:
        return "vector"

    @abstractmethod
    async def create_collection(self, collection_name: str,
                                 vector_size: int, distance: str) -> None:
        """Create vector collection with specified dimensions."""
        pass

    @abstractmethod
    async def upsert_vectors(self, collection_name: str,
                            vectors: List[Tuple[str, List[float], Dict]]) -> None:
        """Insert/update vectors with IDs and metadata."""
        pass

    @abstractmethod
    async def search_vectors(self, collection_name: str,
                            query_vector: List[float], k: int = 10,
                            filter: Optional[Dict] = None) -> List[Dict]:
        """Semantic similarity search."""
        pass

    @abstractmethod
    async def get_vector(self, collection_name: str, vector_id: str) -> Dict:
        """Retrieve vector by ID."""
        pass

    @abstractmethod
    async def delete_vectors(self, collection_name: str,
                            vector_ids: List[str]) -> None:
        """Delete vectors by IDs."""
        pass
```

## GraphAdapter (Neo4j, ArangoDB)

```python
class GraphAdapter(BaseAdapter):
    """Adapter for graph databases."""

    @property
    def adapter_type(self) -> str:
        return "graph"

    @abstractmethod
    async def create_node(self, label: str, properties: Dict) -> str:
        """Create graph node, return node ID."""
        pass

    @abstractmethod
    async def create_edge(self, from_node: str, to_node: str,
                         edge_type: str, properties: Dict) -> str:
        """Create relationship between nodes."""
        pass

    @abstractmethod
    async def traverse(self, start_node: str, pattern: str,
                      max_depth: int = 5) -> List[Dict]:
        """Graph traversal query."""
        pass

    @abstractmethod
    async def execute_query(self, query: str, params: Dict = None) -> List[Dict]:
        """Execute native graph query (Cypher, AQL, Gremlin)."""
        pass
```

## Migration Strategy

### Phase 1: Create BaseAdapter (Week 1, Days 1-2)

1. Create `src/dataflow/adapters/base_adapter.py`:
```python
class BaseAdapter(ABC):
    """Minimal base interface for all adapters."""
    # Implement minimal interface
```

2. Keep existing `base.py` as `database_adapter.py`:
```python
from .base_adapter import BaseAdapter

class DatabaseAdapter(BaseAdapter):
    """SQL database adapter."""
    # Existing implementation with minimal changes
```

3. Update imports in `__init__.py`:
```python
from .base_adapter import BaseAdapter
from .database_adapter import DatabaseAdapter
from .postgresql import PostgreSQLAdapter
# ... etc
```

### Phase 2: Update Existing Adapters (Week 1, Days 3-4)

1. Update PostgreSQL, MySQL, SQLite to use new hierarchy
2. Add `adapter_type` property to each
3. Run full test suite to ensure backward compatibility

### Phase 3: Document and Validate (Week 1, Day 5)

1. Update architecture documentation
2. Add migration guide for future adapter developers
3. Validate all tests pass (no regressions)

## Backward Compatibility Guarantee

**All existing code continues to work:**

```python
# v0.5.6 code (still works)
from dataflow import DataFlow

db = DataFlow("postgresql://localhost/mydb")

@db.model
class User:
    id: str
    name: str

# Existing code unchanged
```

**Internal changes only:**
- DatabaseAdapter now inherits from BaseAdapter
- New adapters follow same pattern
- Node generation logic unchanged for SQL databases

## Testing Strategy

1. **Existing Test Suite**: Must pass 100% (no regressions)
2. **New BaseAdapter Tests**: Validate minimal interface
3. **Adapter Type Tests**: Verify adapter_type property for all adapters
4. **Import Tests**: Ensure backward-compatible imports

## Future Extensions

Once BaseAdapter is in place:

**Week 2-3: PostgreSQLVectorAdapter**
```python
class PostgreSQLVectorAdapter(PostgreSQLAdapter):
    """PostgreSQL with pgvector extension."""

    def supports_feature(self, feature: str) -> bool:
        if feature == "vector_search":
            return True
        return super().supports_feature(feature)
```

**Week 4-8: MongoDBAdapter**
```python
class MongoDBAdapter(DocumentAdapter):
    """MongoDB document database."""

    @property
    def database_type(self) -> str:
        return "mongodb"
```

## Benefits

1. **Clean Architecture**: Clear separation between adapter types
2. **Type Safety**: Each adapter category has specific interface
3. **Extensibility**: Easy to add new database types
4. **Maintainability**: Minimal shared interface reduces coupling
5. **Backward Compatibility**: Existing code works unchanged
6. **Progressive Enhancement**: New features don't break old code

## Implementation Checklist

- [ ] Create `base_adapter.py` with BaseAdapter class
- [ ] Rename `base.py` to `database_adapter.py`, inherit from BaseAdapter
- [ ] Update PostgreSQLAdapter to add `adapter_type` property
- [ ] Update MySQLAdapter to add `adapter_type` property
- [ ] Update SQLiteAdapter to add `adapter_type` property
- [ ] Update `__init__.py` imports
- [ ] Run full test suite (must pass 100%)
- [ ] Document changes in CHANGELOG.md
- [ ] Create adapter development guide

## Timeline

- **Day 1-2**: Create BaseAdapter, refactor DatabaseAdapter
- **Day 3-4**: Update existing adapters, run tests
- **Day 5**: Documentation, validation, commit

**Total:** 1 week (Week 1 of Phase C)

## Success Criteria

✅ All existing tests pass (100% backward compatibility)
✅ BaseAdapter provides minimal, clean interface
✅ DatabaseAdapter inherits cleanly from BaseAdapter
✅ No breaking changes to public API
✅ Foundation ready for DocumentAdapter, VectorAdapter, GraphAdapter

---

**Status**: Ready for implementation
**Risk**: LOW (internal refactoring only)
**Value**: HIGH (enables entire database expansion roadmap)
