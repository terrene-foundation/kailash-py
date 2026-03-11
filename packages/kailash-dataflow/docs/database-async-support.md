# DataFlow Multi-Database Async Support Documentation

## Overview

DataFlow supports multiple databases with proper async drivers. This document describes the implementation approach used for SQLite support, which serves as a template for adding MySQL and MongoDB support.

## SQLite Async Support Implementation

### Problem Statement
DataFlow generated CRUD nodes were failing with SQLite because they were hardcoded to use PostgreSQL-specific async connections:
```
Database query failed: invalid DSN: scheme is expected to be either "postgresql" or "postgres", got 'sqlite'
```

### Solution Architecture

#### 1. Database Type Detection
The core fix was to pass the database type to AsyncSQLDatabaseNode instances in generated nodes:

**File**: `src/dataflow/core/nodes.py`
```python
# Before (broken):
sql_node = AsyncSQLDatabaseNode(
    node_id=f"{model_name}_{operation}_sql",
    connection_string=connection_string,
    query=query,
    params=params,
    fetch_mode="one",
    validate_queries=False,
)

# After (fixed):
sql_node = AsyncSQLDatabaseNode(
    node_id=f"{model_name}_{operation}_sql",
    database_type=database_type,  # ✅ ADDED
    connection_string=connection_string,
    query=query,
    params=params,
    fetch_mode="one",
    validate_queries=False,
)
```

#### 2. SQLite Connection String Parsing
Fixed SQLiteAdapter to properly handle absolute paths with 4 slashes:

**File**: `src/kailash/nodes/data/async_sql.py`
```python
# Fixed parsing for sqlite:////absolute/path format
elif path_part.startswith("/"):
    # Absolute path with 4 slashes
    self._db_path = path_part
```

#### 3. Memory Database Consistency
SQLite `:memory:` databases are isolated per connection. To ensure DDL and CRUD operations use the same database:

**File**: `src/dataflow/core/engine.py`
```python
# Resolve :memory: to temporary file for consistency
if database_url == ":memory:":
    import tempfile
    import os
    pid = os.getpid()
    temp_db = f"/tmp/dataflow_memory_{pid}.db"
    self._resolved_database_url = f"sqlite:///{temp_db}"
else:
    self._resolved_database_url = database_url
```

#### 4. Interface Compatibility
Added missing parameters to SQLiteAdapter for interface consistency:

```python
async def execute(self, query: str, params: Optional[List[Any]] = None,
                  parameter_types: Optional[List[str]] = None) -> Any:
    # parameter_types added for interface compatibility
```

## Implementation Pattern for New Databases

### MySQL (aiomysql) Implementation Steps

1. **Update Database Type Detection**
   ```python
   # In DataFlow.__init__
   if "mysql" in database_url:
       self._database_type = "mysql"
   ```

2. **Create MySQL Adapter**
   ```python
   class MySQLAdapter(DatabaseAdapterBase):
       async def connect(self):
           import aiomysql
           self.pool = await aiomysql.create_pool(
               host=self.host,
               port=self.port,
               user=self.user,
               password=self.password,
               db=self.database,
               **self.options
           )
   ```

3. **Update AsyncSQLDatabaseNode**
   - Add MySQL to supported database types
   - Handle MySQL-specific parameter placeholders (%s)
   - Implement proper async execution

4. **Test with DataFlow**
   ```python
   db = DataFlow("mysql://user:pass@localhost/db")
   @db.model
   class User:
       name: str
       email: str
   ```

### MongoDB (motor) Implementation Steps

1. **Create MongoDB Adapter**
   ```python
   class MongoDBAdapter(DatabaseAdapterBase):
       async def connect(self):
           import motor.motor_asyncio
           self.client = motor.motor_asyncio.AsyncIOMotorClient(
               self.connection_string
           )
           self.db = self.client[self.database]
   ```

2. **Extend Node Generation**
   - MongoDB uses documents, not SQL
   - Generate MongoDB-specific nodes (MongoCreateNode, etc.)
   - Use motor's async methods

3. **Handle Schema Differences**
   - MongoDB is schemaless
   - Model definitions become validation schemas
   - No table creation needed

## Key Principles

1. **Database Type Awareness**: Always pass database type to nodes
2. **Async Driver Usage**: Use appropriate async drivers (aiosqlite, aiomysql, motor)
3. **Connection String Parsing**: Handle database-specific URL formats
4. **Interface Compatibility**: Maintain consistent interfaces across adapters
5. **Error Handling**: Provide clear error messages for unsupported operations

## Testing Strategy

1. **Unit Tests**: Mock database connections
2. **Integration Tests**: Use real databases via Docker
3. **E2E Tests**: Complete workflows with each database type

## Current Status

- ✅ **PostgreSQL**: Full production support with asyncpg
- ⚠️ **SQLite**: Basic workflow support with aiosqlite (limited migration features)
- ❌ **MySQL**: Not yet implemented
- ❌ **MongoDB**: Not yet implemented

## PostgreSQL-Only Migration System Limitations

### Why PostgreSQL Only?

The DataFlow migration system is currently **PostgreSQL-exclusive** due to architectural decisions made in the core migration components:

#### 1. **Hard-coded PostgreSQL Dependencies**

**File**: `src/dataflow/migrations/auto_migration_system.py`
- Uses `asyncpg`-specific connection interface
- PostgreSQL-specific SQL generation
- INFORMATION_SCHEMA queries that assume PostgreSQL structure

**File**: `src/dataflow/migrations/schema_state_manager.py`
- PostgreSQL-specific schema inspection queries
- Uses PostgreSQL data type system
- Assumes PostgreSQL constraint and index structures

#### 2. **PostgreSQL-Specific SQL Generation**

**Migration DDL Generation**:
```python
# PostgreSQL-specific syntax in migration generators
CREATE TABLE users (
    id SERIAL PRIMARY KEY,           -- PostgreSQL SERIAL type
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    email VARCHAR(255) UNIQUE
);

# PostgreSQL-specific ALTER statements
ALTER TABLE users ADD COLUMN status VARCHAR(20) DEFAULT 'active';
```

**Schema Inspection**:
```sql
-- PostgreSQL-specific INFORMATION_SCHEMA queries
SELECT
    table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public';
```

#### 3. **Migration History Tracking**

**File**: `src/dataflow/core/model_registry.py`
- Migration history stored in PostgreSQL-specific format
- Uses PostgreSQL CURRENT_TIMESTAMP function
- Assumes PostgreSQL transaction semantics

### What Works with SQLite Currently

**✅ Basic DataFlow Operations** (with development Core SDK):
- `DataFlow(':memory:')` initialization
- Model registration with `@db.model`
- Basic CRUD node generation and execution
- Simple workflows with AsyncSQLDatabaseNode
- **Fixed**: SQLite async parameter compatibility

**❌ Advanced Migration Features**:
- Automatic schema migrations (PostgreSQL-only migration system)
- Migration rollback system
- Schema state caching
- Visual migration builder
- Migration performance tracking

### Critical Development Note

**⚠️ Important**: DataFlow development currently requires using the **development version** of the Core SDK, not the installed package version.

#### The Issue
When using the installed Core SDK package (`pip install kailash`), you may encounter:
```
SQLiteAdapter.execute() got an unexpected keyword argument 'parameter_types'
```

#### The Solution
Ensure the development Core SDK is in your Python path:
```bash
export PYTHONPATH="/path/to/kailash_python_sdk/src:$PYTHONPATH"
# or
PYTHONPATH="/path/to/kailash_python_sdk/src:$PYTHONPATH" python your_script.py
```

#### Root Cause
- **Installed Core SDK**: Older version without `parameter_types` parameter
- **Development Core SDK**: Current version with full async compatibility
- **DataFlow**: Requires latest Core SDK features for full functionality

This will be resolved when the next Core SDK version is published to PyPI.

## Multi-Database Implementation Guide

This section provides a comprehensive roadmap for implementing MongoDB, MySQL, and SQLite support across both the Core SDK and DataFlow, based on our current research and SQLite compatibility findings.

### Architecture Overview

```
Kailash Multi-Database Architecture

Core SDK (src/kailash/)
├── AsyncSQLDatabaseNode (SQL databases)
├── AsyncMongoDBNode (document databases) [NEW]
└── Database Adapters:
    ├── PostgreSQLAdapter ✅ (asyncpg)
    ├── SQLiteAdapter ⚠️ (aiosqlite - parameter_types fixed)
    ├── MySQLAdapter ❌ (aiomysql) [NEW]
    └── MongoDBAdapter ❌ (motor) [NEW]

DataFlow (packages/kailash-dataflow/)
├── SQL Migration System (PostgreSQL-only) ⚠️
├── Document Migration System [NEW]
└── Database Adapters:
    ├── PostgreSQLAdapter ✅
    ├── SQLiteAdapter ⚠️ (limited migration support)
    ├── MySQLAdapter ❌ [NEW]
    └── MongoDBAdapter ❌ [NEW]
```

### Phase 1: Core SDK Multi-Database Foundation

**Goal**: Extend Core SDK AsyncSQLDatabaseNode and create AsyncMongoDBNode

#### 1.1 MongoDB Support - Motor Integration

**Target**: Create `AsyncMongoDBNode` for document-based operations

**Implementation Path**:
```python
# File: src/kailash/nodes/data/async_mongodb.py
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection

class MongoDBAdapter(DatabaseAdapter):
    """MongoDB adapter using Motor for async operations."""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.client: Optional[AsyncIOMotorClient] = None
        self.database: Optional[AsyncIOMotorDatabase] = None

    async def connect(self) -> None:
        """Establish MongoDB connection using Motor."""
        try:
            import motor.motor_asyncio
        except ImportError:
            raise NodeExecutionError(
                "motor not installed. Install with: pip install motor"
            )

        # Build connection URI
        if self.config.connection_string:
            uri = self.config.connection_string
        else:
            uri = f"mongodb://{self.config.host}:{self.config.port or 27017}"

        self.client = motor.motor_asyncio.AsyncIOMotorClient(
            uri,
            maxPoolSize=self.config.max_pool_size or 20,
            serverSelectionTimeoutMS=self.config.command_timeout * 1000 or 30000
        )

        # Select database
        db_name = self.config.database or 'kailash'
        self.database = self.client[db_name]

        # Test connection
        await self.client.admin.command('ping')

    async def find_one(self, collection: str, filter_doc: dict) -> Optional[dict]:
        """Find single document."""
        collection_obj = self.database[collection]
        return await collection_obj.find_one(filter_doc)

    async def find_many(self, collection: str, filter_doc: dict, limit: Optional[int] = None) -> List[dict]:
        """Find multiple documents."""
        collection_obj = self.database[collection]
        cursor = collection_obj.find(filter_doc)
        if limit:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=None)

    async def insert_one(self, collection: str, document: dict) -> str:
        """Insert single document."""
        collection_obj = self.database[collection]
        result = await collection_obj.insert_one(document)
        return str(result.inserted_id)

    async def update_one(self, collection: str, filter_doc: dict, update_doc: dict) -> bool:
        """Update single document."""
        collection_obj = self.database[collection]
        result = await collection_obj.update_one(filter_doc, {'$set': update_doc})
        return result.modified_count > 0

    async def delete_one(self, collection: str, filter_doc: dict) -> bool:
        """Delete single document."""
        collection_obj = self.database[collection]
        result = await collection_obj.delete_one(filter_doc)
        return result.deleted_count > 0

class AsyncMongoDBNode(AsyncNode):
    """MongoDB operations node using Motor async driver."""

    def __init__(self, **config):
        self._adapter: Optional[MongoDBAdapter] = None
        super().__init__(**config)

    async def _get_adapter(self) -> MongoDBAdapter:
        """Get or create MongoDB adapter."""
        if not self._adapter:
            db_config = DatabaseConfig(
                type=DatabaseType.MONGODB,
                host=self.config.get("host", "localhost"),
                port=self.config.get("port", 27017),
                database=self.config.get("database", "kailash"),
                connection_string=self.config.get("connection_string")
            )
            self._adapter = MongoDBAdapter(db_config)
            await self._adapter.connect()
        return self._adapter

    async def run_async(self, **inputs) -> Dict[str, Any]:
        """Execute MongoDB operation."""
        operation = inputs.get("operation", "find_one")
        collection = inputs.get("collection")

        if not collection:
            raise NodeExecutionError("Collection name required")

        adapter = await self._get_adapter()

        if operation == "find_one":
            filter_doc = inputs.get("filter", {})
            result = await adapter.find_one(collection, filter_doc)
            return {"result": result, "success": result is not None}

        elif operation == "insert_one":
            document = inputs.get("document", {})
            document_id = await adapter.insert_one(collection, document)
            return {"result": {"inserted_id": document_id}, "success": True}

        # Add other operations...
        else:
            raise NodeExecutionError(f"Unsupported operation: {operation}")
```

**Key MongoDB Features to Support**:
- Document CRUD operations
- Aggregation pipelines
- Index management
- Transactions (MongoDB 4.0+)
- GridFS for file storage
- Change streams for real-time updates

#### 1.2 MySQL Support - aiomysql Integration

**Target**: Extend `SQLiteAdapter` pattern for MySQL using aiomysql

**Implementation Path**:
```python
# File: src/kailash/nodes/data/async_sql.py (extend existing)
class MySQLAdapter(DatabaseAdapter):
    """MySQL adapter using aiomysql."""

    async def connect(self) -> None:
        """Establish MySQL connection pool."""
        try:
            import aiomysql
        except ImportError:
            raise NodeExecutionError(
                "aiomysql not installed. Install with: pip install aiomysql"
            )

        self._pool = await aiomysql.create_pool(
            host=self.config.host or 'localhost',
            port=self.config.port or 3306,
            user=self.config.user,
            password=self.config.password,
            db=self.config.database,
            maxsize=self.config.max_pool_size or 20,
            charset='utf8mb4'
        )

    async def execute(
        self,
        query: str,
        params: Optional[Union[tuple, dict]] = None,
        fetch_mode: FetchMode = FetchMode.ALL,
        fetch_size: Optional[int] = None,
        transaction: Optional[Any] = None,
        parameter_types: Optional[dict[str, str]] = None,
    ) -> Any:
        """Execute MySQL query."""
        # Convert params to MySQL format (%s placeholders)
        if isinstance(params, dict):
            # Convert named parameters to positional
            mysql_query, mysql_params = self._convert_named_params(query, params)
        else:
            # Convert $1, $2 to %s format
            mysql_query = self._convert_postgres_placeholders(query)
            mysql_params = params or []

        # Use connection from transaction or pool
        if transaction:
            conn = transaction
        else:
            conn = await self._pool.acquire()

        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(mysql_query, mysql_params)

                if fetch_mode == FetchMode.ONE:
                    result = await cursor.fetchone()
                elif fetch_mode == FetchMode.ALL:
                    result = await cursor.fetchall()
                elif fetch_mode == FetchMode.MANY:
                    result = await cursor.fetchmany(fetch_size or 100)
                else:
                    result = None

                return result
        finally:
            if not transaction:
                self._pool.release(conn)

    def _convert_postgres_placeholders(self, query: str) -> str:
        """Convert PostgreSQL $1, $2 placeholders to MySQL %s."""
        import re
        # Replace $1, $2, etc. with %s
        return re.sub(r'\$\d+', '%s', query)

    def _convert_named_params(self, query: str, params: dict) -> Tuple[str, list]:
        """Convert named parameters to positional for MySQL."""
        import re
        param_order = []

        def replace_param(match):
            param_name = match.group(1)
            if param_name in params:
                param_order.append(params[param_name])
            return '%s'

        # Replace :param_name with %s
        mysql_query = re.sub(r':(\w+)', replace_param, query)
        return mysql_query, param_order
```

**MySQL-Specific Considerations**:
- Parameter placeholders: `%s` instead of `$1, $2`
- Data types: `AUTO_INCREMENT`, `TIMESTAMP`, `JSON` (MySQL 5.7+)
- Transaction isolation levels
- Character sets and collations
- Full-text search syntax differences

#### 1.3 Enhanced SQLite Support - aiosqlite Improvements

**Target**: Complete aiosqlite integration and fix remaining issues

**Current Status**: ✅ Basic functionality working, ⚠️ needs full feature parity

**Implementation Path**:
```python
# File: src/kailash/nodes/data/async_sql.py (enhance existing)
class SQLiteAdapter(DatabaseAdapter):
    """Enhanced SQLite adapter with full aiosqlite support."""

    async def execute(
        self,
        query: str,
        params: Optional[Union[tuple, dict]] = None,
        fetch_mode: FetchMode = FetchMode.ALL,
        fetch_size: Optional[int] = None,
        transaction: Optional[Any] = None,
        parameter_types: Optional[dict[str, str]] = None,  # ✅ Already fixed
    ) -> Any:
        """Execute query with enhanced SQLite support."""
        # Convert PostgreSQL-style queries to SQLite
        sqlite_query = self._adapt_query_for_sqlite(query)
        sqlite_params = self._adapt_params_for_sqlite(params)

        # Handle parameter_types for SQLite (mostly ignore, but log warnings)
        if parameter_types:
            self._log_parameter_type_warnings(parameter_types)

        # Rest of existing implementation...

    def _adapt_query_for_sqlite(self, query: str) -> str:
        """Adapt PostgreSQL/MySQL queries for SQLite."""
        import re

        # Convert PostgreSQL $1, $2 to SQLite ? placeholders
        adapted = re.sub(r'\$\d+', '?', query)

        # Convert data types
        adapted = re.sub(r'\bSERIAL\b', 'INTEGER', adapted, flags=re.IGNORECASE)
        adapted = re.sub(r'\bBIGSERIAL\b', 'INTEGER', adapted, flags=re.IGNORECASE)
        adapted = re.sub(r'\bTIMESTAMP\b', 'TEXT', adapted, flags=re.IGNORECASE)

        # Convert AUTO_INCREMENT to SQLite syntax
        adapted = re.sub(r'\bAUTO_INCREMENT\b', '', adapted, flags=re.IGNORECASE)

        return adapted

    def _log_parameter_type_warnings(self, parameter_types: dict):
        """Log warnings about unsupported parameter types in SQLite."""
        logger = logging.getLogger(__name__)
        for param, param_type in parameter_types.items():
            if param_type.lower() not in ['text', 'integer', 'real', 'blob']:
                logger.warning(
                    f"SQLite doesn't support parameter type '{param_type}' for '{param}'. "
                    f"Using dynamic typing instead."
                )
```

### Phase 2: DataFlow Multi-Database Support

**Goal**: Extend DataFlow for multi-database model generation and operations

#### 2.1 Database-Agnostic Model Registration

**Target**: Support `@db.model` for all database types

**Implementation Path**:
```python
# File: src/dataflow/core/engine.py (enhance existing)
class DataFlow:
    def __init__(self, database_url: str, **kwargs):
        # Detect database type from URL
        self._database_type = self._detect_database_type(database_url)

        # Initialize appropriate adapter
        if self._database_type == "mongodb":
            self._adapter = MongoDBDataFlowAdapter(database_url, **kwargs)
        elif self._database_type == "mysql":
            self._adapter = MySQLDataFlowAdapter(database_url, **kwargs)
        elif self._database_type == "sqlite":
            self._adapter = SQLiteDataFlowAdapter(database_url, **kwargs)
        elif self._database_type == "postgresql":
            self._adapter = PostgreSQLDataFlowAdapter(database_url, **kwargs)
        else:
            raise ValueError(f"Unsupported database type: {self._database_type}")

    def _detect_database_type(self, database_url: str) -> str:
        """Detect database type from connection string."""
        if database_url.startswith(('mongodb://', 'mongodb+srv://')):
            return "mongodb"
        elif database_url.startswith('mysql://'):
            return "mysql"
        elif database_url.startswith(('sqlite:///', ':memory:')):
            return "sqlite"
        elif database_url.startswith(('postgresql://', 'postgres://')):
            return "postgresql"
        else:
            # Default fallback or raise error
            raise ValueError(f"Cannot detect database type from URL: {database_url}")

# File: src/dataflow/adapters/mongodb.py
class MongoDBDataFlowAdapter:
    """DataFlow adapter for MongoDB operations."""

    def __init__(self, connection_string: str, **kwargs):
        self.connection_string = connection_string
        self.client = None
        self.database = None

    async def initialize(self):
        """Initialize MongoDB connection."""
        from motor.motor_asyncio import AsyncIOMotorClient
        self.client = AsyncIOMotorClient(self.connection_string)

        # Extract database name from connection string or use default
        db_name = self._extract_database_name() or 'kailash'
        self.database = self.client[db_name]

    def generate_nodes_for_model(self, model_class: type, model_name: str) -> Dict[str, Any]:
        """Generate MongoDB-specific CRUD nodes."""
        collection_name = self._get_collection_name(model_name)

        nodes = {}

        # Create Node - Insert Document
        nodes[f"{model_name}CreateNode"] = self._create_insert_node(model_class, collection_name)

        # Read Node - Find Document
        nodes[f"{model_name}ReadNode"] = self._create_find_node(model_class, collection_name)

        # Update Node - Update Document
        nodes[f"{model_name}UpdateNode"] = self._create_update_node(model_class, collection_name)

        # Delete Node - Delete Document
        nodes[f"{model_name}DeleteNode"] = self._create_delete_node(model_class, collection_name)

        # List Node - Find Multiple Documents
        nodes[f"{model_name}ListNode"] = self._create_list_node(model_class, collection_name)

        # Search Node - Text Search
        nodes[f"{model_name}SearchNode"] = self._create_search_node(model_class, collection_name)

        # Aggregate Node - Aggregation Pipeline
        nodes[f"{model_name}AggregateNode"] = self._create_aggregate_node(model_class, collection_name)

        # Count Node - Count Documents
        nodes[f"{model_name}CountNode"] = self._create_count_node(model_class, collection_name)

        # Index Node - Manage Indexes
        nodes[f"{model_name}IndexNode"] = self._create_index_node(model_class, collection_name)

        return nodes

    def _get_collection_name(self, model_name: str) -> str:
        """Convert model name to MongoDB collection name."""
        # Convert CamelCase to snake_case and pluralize
        import re
        snake_case = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', model_name)
        snake_case = re.sub('([a-z0-9])([A-Z])', r'\1_\2', snake_case).lower()

        # Simple pluralization
        if snake_case.endswith('y'):
            return snake_case[:-1] + 'ies'
        elif snake_case.endswith(('s', 'sh', 'ch', 'x', 'z')):
            return snake_case + 'es'
        else:
            return snake_case + 's'
```

#### 2.2 Database-Specific Node Generation

**MongoDB Document Operations**:
```python
def _create_insert_node(self, model_class: type, collection_name: str):
    """Create MongoDB insert node."""
    class MongoInsertNode(AsyncNode):
        async def run_async(self, **kwargs):
            # Validate against model schema
            validated_doc = self._validate_document(kwargs, model_class)

            # Add timestamps
            validated_doc['created_at'] = datetime.utcnow()
            validated_doc['updated_at'] = datetime.utcnow()

            # Insert document
            result = await self.database[collection_name].insert_one(validated_doc)

            return {
                "success": True,
                "inserted_id": str(result.inserted_id),
                "document": validated_doc
            }

    return MongoInsertNode
```

**MySQL SQL Operations**:
```python
def _create_insert_node(self, model_class: type, table_name: str):
    """Create MySQL insert node using aiomysql."""
    class MySQLInsertNode(AsyncNode):
        async def run_async(self, **kwargs):
            # Generate MySQL INSERT SQL
            fields = self._get_model_fields(model_class)
            columns = ', '.join(fields.keys())
            placeholders = ', '.join(['%s'] * len(fields))  # MySQL uses %s

            query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
            values = [kwargs.get(field) for field in fields.keys()]

            # Execute using MySQL adapter
            async with self.connection_pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, values)
                    await conn.commit()
                    return {"success": True, "last_insert_id": cursor.lastrowid}

    return MySQLInsertNode
```

### Phase 3: Migration System Extension

**Goal**: Create database-agnostic migration framework

#### 3.1 Abstract Migration Interface

```python
# File: src/dataflow/migrations/base_migration.py
from abc import ABC, abstractmethod

class DatabaseMigrationAdapter(ABC):
    """Abstract base for database-specific migration operations."""

    @abstractmethod
    async def create_table(self, table_def: TableDefinition) -> str:
        """Generate CREATE TABLE statement/operation."""
        pass

    @abstractmethod
    async def alter_table(self, table_name: str, operation: AlterOperation) -> str:
        """Generate ALTER TABLE statement/operation."""
        pass

    @abstractmethod
    async def drop_table(self, table_name: str) -> str:
        """Generate DROP TABLE statement/operation."""
        pass

    @abstractmethod
    async def create_index(self, index_def: IndexDefinition) -> str:
        """Generate CREATE INDEX statement/operation."""
        pass

class MongoDBMigrationAdapter(DatabaseMigrationAdapter):
    """MongoDB migration operations."""

    async def create_table(self, table_def: TableDefinition) -> str:
        # In MongoDB, "creating a table" means creating a collection with validation
        return f"db.createCollection('{table_def.name}', {self._build_validation_schema(table_def)})"

    async def create_index(self, index_def: IndexDefinition) -> str:
        return f"db.{index_def.table}.createIndex({self._build_index_spec(index_def)})"

class MySQLMigrationAdapter(DatabaseMigrationAdapter):
    """MySQL migration operations."""

    async def create_table(self, table_def: TableDefinition) -> str:
        columns = []
        for column in table_def.columns:
            col_sql = f"{column.name} {self._map_to_mysql_type(column.type)}"
            if column.primary_key:
                col_sql += " AUTO_INCREMENT PRIMARY KEY"
            if not column.nullable:
                col_sql += " NOT NULL"
            columns.append(col_sql)

        return f"CREATE TABLE {table_def.name} ({', '.join(columns)}) ENGINE=InnoDB"
```

### Phase 4: Implementation Priority & Dependencies

#### 4.1 Development Dependencies

**MongoDB (Motor)**:
```bash
pip install motor  # Async MongoDB driver
pip install pymongo[srv]  # For MongoDB Atlas connection strings
```

**MySQL (aiomysql)**:
```bash
pip install aiomysql  # Async MySQL driver
pip install PyMySQL  # Pure Python MySQL client
```

**SQLite (aiosqlite)**:
```bash
pip install aiosqlite  # Already included in current implementation
```

#### 4.2 Implementation Timeline

**Phase 1** (4-6 weeks): Core SDK Foundation
- Week 1-2: MongoDB AsyncMongoDBNode + Motor integration
- Week 3-4: MySQL MySQLAdapter + aiomysql integration
- Week 5-6: Enhanced SQLite features + testing

**Phase 2** (3-4 weeks): DataFlow Multi-Database
- Week 1-2: Database detection + adapter abstraction
- Week 3-4: Database-specific node generation

**Phase 3** (3-4 weeks): Migration System
- Week 1-2: Abstract migration interfaces
- Week 3-4: Database-specific migration adapters

**Phase 4** (2 weeks): Testing & Documentation
- Week 1: Comprehensive integration tests
- Week 2: Documentation + examples

#### 4.3 Testing Strategy

**Unit Tests** (Tier 1):
- Mock database connections
- Test adapter interfaces
- Validate query generation

**Integration Tests** (Tier 2):
- Real database connections via Docker
- Test CRUD operations
- Migration system validation

**E2E Tests** (Tier 3):
- Complete workflows
- Multi-database scenarios
- Performance benchmarks

### Critical Success Factors

1. **Consistent Interfaces**: Ensure all database adapters implement the same interface patterns
2. **Error Handling**: Database-specific error mapping to common error types
3. **Performance**: Connection pooling and query optimization for each database
4. **Documentation**: Clear examples for each database type
5. **Backward Compatibility**: Existing PostgreSQL functionality must not break

This roadmap provides a comprehensive path to full multi-database support while building on our current SQLite compatibility insights and successful migration framework implementation.
