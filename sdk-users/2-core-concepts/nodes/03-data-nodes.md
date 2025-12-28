# Data I/O Nodes

**Module**: `kailash.nodes.data`
**Last Updated**: 2025-01-06

This document covers all data input/output nodes including file operations, databases, streaming, SharePoint integration, and RAG components.

## Table of Contents
- [File I/O Nodes](#file-io-nodes)
- [Database Nodes](#database-nodes)
- [Streaming Nodes](#streaming-nodes)
- [Vector Database Nodes](#vector-database-nodes)
- [Source Management Nodes](#source-management-nodes)
- [Retrieval Nodes](#retrieval-nodes)
- [SharePoint Integration Nodes](#sharepoint-integration-nodes)

## File I/O Nodes

### CSVReaderNode
- **Module**: `kailash.nodes.data.readers`
- **Purpose**: Read CSV files
- **Parameters**:
  - `file_path`: Path to CSV file
  - `delimiter`: Column delimiter
  - `encoding`: File encoding

### CSVWriterNode
- **Module**: `kailash.nodes.data.writers`
- **Purpose**: Write CSV files
- **Parameters**:
  - `file_path`: Output file path
  - `data`: Data to write
  - `headers`: Column headers

### JSONReaderNode
- **Module**: `kailash.nodes.data.readers`
- **Purpose**: Read JSON files
- **Parameters**:
  - `file_path`: Path to JSON file
  - `encoding`: File encoding

### JSONWriterNode
- **Module**: `kailash.nodes.data.writers`
- **Purpose**: Write JSON files
- **Parameters**:
  - `file_path`: Output file path
  - `data`: Data to write
  - `indent`: JSON indentation

### TextReaderNode
- **Module**: `kailash.nodes.data.readers`
- **Purpose**: Read text files
- **Parameters**:
  - `file_path`: Path to text file
  - `encoding`: File encoding

### DocumentProcessorNode ⭐ **NEW**
- **Module**: `kailash.nodes.data.readers`
- **Purpose**: Advanced document processor for multiple formats with automatic format detection and metadata extraction
- **Key Features**:
  - Automatic format detection (PDF, DOCX, MD, HTML, RTF, TXT)
  - Rich metadata extraction (title, author, dates, structure)
  - Structure preservation (sections, headings, pages)
  - Unified output format across all document types
  - Encoding detection and handling
  - Comprehensive error handling with fallbacks
- **Supported Formats**:
  - **PDF**: Text extraction with page information
  - **DOCX**: Content and document properties
  - **Markdown**: Structure parsing with heading detection
  - **HTML**: Clean text extraction with structure
  - **RTF**: Rich text format processing
  - **TXT**: Plain text with encoding detection
- **Parameters**:
  - `file_path`: Path to document file (required)
  - `extract_metadata`: Extract document metadata (default: True)
  - `preserve_structure`: Maintain document structure (default: True)
  - `encoding`: Text encoding for plain text files (default: "utf-8")
  - `page_numbers`: Include page/section numbers (default: True)
  - `extract_images`: Extract image references (default: False)
- **Best For**:
  - Document management systems
  - RAG pipelines requiring document analysis
  - Content migration and processing
  - Multi-format document workflows
  - Metadata-driven applications
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  processor = DocumentProcessorNode(
      extract_metadata=True,
      preserve_structure=True
  )
  result = processor.run(file_path="report.pdf")

  content = result["content"]           # Extracted text
  metadata = result["metadata"]         # Document properties
  sections = result["sections"]         # Structural elements
  doc_format = result["document_format"] # Detected format

  ```
- **Output Structure**:
  ```python
  {
      "content": "Full document text",
      "metadata": {
          "title": "Document Title",
          "author": "Author Name",
          "creation_date": "2024-01-01",
          "word_count": 1500,
          "character_count": 8500,
          "document_format": "pdf"
      },
      "sections": [
          {
              "type": "heading",
              "level": 1,
              "title": "Chapter 1",
              "content": "Chapter content...",
              "start_position": 0,
              "end_position": 100
          }
      ],
      "document_format": "pdf"
  }

  ```

### TextWriterNode
- **Module**: `kailash.nodes.data.writers`
- **Purpose**: Write text files
- **Parameters**:
  - `file_path`: Output file path
  - `content`: Text content

## Database Nodes

### WorkflowConnectionPool ⭐ **PRODUCTION RECOMMENDED**
- **Module**: `kailash.nodes.data.workflow_connection_pool`
- **Purpose**: Production-grade connection pooling with actor-based fault tolerance
- **Key Features**:
  - Actor-based architecture for fault tolerance
  - Connection pooling with min/max limits
  - Health monitoring and automatic recycling
  - Pre-warming based on workflow patterns
  - Comprehensive metrics and statistics
  - Supervisor integration for failure recovery
  - Support for PostgreSQL, MySQL, SQLite
  - **NEW**: Adaptive pool sizing (Phase 2)
  - **NEW**: Pattern tracking for query routing (Phase 2)
- **Parameters**:
  - `name`: Pool name for identification
  - `database_type`: "postgresql", "mysql", or "sqlite"
  - `host`: Database host
  - `port`: Database port
  - `database`: Database name
  - `user`: Database user
  - `password`: Database password
  - `min_connections`: Minimum pool size (default: 2)
  - `max_connections`: Maximum pool size (default: 10)
  - `health_threshold`: Health score threshold for recycling (default: 75)
  - `pre_warm`: Enable pattern-based pre-warming (default: True)
  - `adaptive_sizing`: **NEW** Enable dynamic pool sizing (default: False)
  - `enable_query_routing`: **NEW** Enable pattern tracking (default: False)
- **Operations**:
  - `initialize`: Start the pool
  - `acquire`: Get a connection from pool
  - `release`: Return connection to pool
  - `execute`: Execute query on connection
  - `stats`: Get pool statistics
  - `recycle`: Force recycle a connection
- **Best For**:
  - Production applications with high concurrency
  - Long-running services requiring fault tolerance
  - Applications with database connection limits
  - Systems requiring connection health monitoring
- **Example**:
  ```python
  from kailash.nodes.data import WorkflowConnectionPool

  # Create connection pool
  pool = WorkflowConnectionPool(
      name="main_pool",
      database_type="postgresql",
      host="localhost",
      port=5432,
      database="myapp",
      user="postgres",
      password="password",
      min_connections=5,
      max_connections=20,
      health_threshold=70,
      pre_warm=True
  )

  # Initialize pool
  await pool.execute({"operation": "initialize"})

  # Use in workflow
  async def process_order(order_id):
      # Acquire connection
      conn = await pool.execute({"operation": "acquire"})
      conn_id = conn["connection_id"]

      try:
          # Execute query
          result = await pool.execute({
              "operation": "execute",
              "connection_id": conn_id,
              "query": "SELECT * FROM orders WHERE id = $1",
              "params": [order_id],
              "fetch_mode": "one"
          })
          return result["data"]
      finally:
          # Always release connection
          await pool.execute({
              "operation": "release",
              "connection_id": conn_id
          })

  # Get pool statistics
  stats = await pool.execute({"operation": "stats"})
  print(f"Active connections: {stats['current_state']['active_connections']}")
  print(f"Pool efficiency: {stats['queries']['executed'] / stats['connections']['created']:.1f} queries/connection")
  ```

### QueryRouterNode ⭐ **NEW - PHASE 2**
- **Module**: `kailash.nodes.data.query_router`
- **Purpose**: Intelligent query routing with caching and optimization
- **Key Features**:
  - Automatic connection management (no manual acquire/release)
  - Query classification (READ_SIMPLE, READ_COMPLEX, WRITE, etc.)
  - Prepared statement caching for performance
  - Read/write splitting for scalability
  - Transaction support with session affinity
  - Pattern learning for workload optimization
  - Health-aware routing decisions
- **Parameters**:
  - `name`: Router name for identification
  - `connection_pool`: Name of WorkflowConnectionPool to use (required)
  - `enable_read_write_split`: Route reads to any healthy connection (default: True)
  - `cache_size`: Max prepared statements to cache (default: 1000)
  - `pattern_learning`: Learn from query patterns (default: True)
  - `health_threshold`: Min health score for routing (default: 50.0)
- **Best For**:
  - High-performance applications with query patterns
  - Read-heavy workloads requiring load distribution
  - Applications needing prepared statement caching
  - Systems requiring transaction session management
- **Example**:
  ```python
  from kailash.nodes.data import WorkflowConnectionPool
  from kailash.nodes.data.query_router import QueryRouterNode

  # First create pool with Phase 2 features
  pool = WorkflowConnectionPool(
      name="smart_pool",
      database_type="postgresql",
      host="localhost",
      database="myapp",
      min_connections=5,
      max_connections=50,
      adaptive_sizing=True,
      enable_query_routing=True
  )
  await pool.execute({"operation": "initialize"})

  # Create query router
  router = QueryRouterNode(
      name="query_router",
      connection_pool="smart_pool",
      enable_read_write_split=True,
      cache_size=2000,
      pattern_learning=True
  )

  # Simple query - no connection management needed!
  result = await router.execute({
      "query": "SELECT * FROM users WHERE active = ?",
      "parameters": [True]
  })

  # Transaction with session affinity
  await router.execute({
      "query": "BEGIN",
      "session_id": "user_123"
  })

  await router.execute({
      "query": "UPDATE accounts SET balance = balance - ? WHERE id = ?",
      "parameters": [100, 1],
      "session_id": "user_123"
  })

  await router.execute({
      "query": "COMMIT",
      "session_id": "user_123"
  })

  # Check router performance
  metrics = await router.get_metrics()
  print(f"Cache hit rate: {metrics['cache_stats']['hit_rate']:.2%}")
  print(f"Avg routing time: {metrics['router_metrics']['avg_routing_time_ms']}ms")
  ```

### AsyncSQLDatabaseNode ⭐ **ENHANCED**
- **Module**: `kailash.nodes.data.async_sql`
- **Purpose**: Production-grade asynchronous SQL execution with enterprise features
- **Key Features**:
  - **✅ Transaction Management**: Auto, manual, and none modes for precise control
  - **✅ Optimistic Locking**: Version-based concurrency control with conflict resolution
  - **✅ Connection Pool Sharing**: Efficient resource utilization across workflows
  - **✅ Advanced Parameter Handling**: Database-specific parameter conversion (PostgreSQL ANY(), etc.)
  - **✅ Intelligent Retry Logic**: Exponential backoff with DNS/network error handling
  - **✅ Security Validation**: Query validation with configurable admin operation control
  - **✅ Performance Monitoring**: Comprehensive metrics and connection health tracking
  - **✅ Multiple Result Formats**: DataFrame serialization for complex data structures

- **Constructor Parameters**:
  - `database_type`: Database type (`postgresql`, `mysql`, `sqlite`)
  - `host`: Database host (required unless using connection_string)
  - `port`: Database port (optional, uses defaults)
  - `database`: Database name (required)
  - `user`: Database user (required)
  - `password`: Database password (required)
  - `connection_string`: Full connection string (alternative to individual params)
  - `transaction_mode`: Transaction handling mode (`"auto"`, `"manual"`, `"none"`)
  - `share_pool`: Enable connection pool sharing across instances (default: `True`)
  - `validate_queries`: Enable security query validation (default: `True`)
  - `allow_admin`: Allow admin operations (CREATE, DROP, etc.) (default: `False`)
  - `retry_config`: Retry configuration object (optional)
  - `command_timeout`: Pool-level timeout applied to all queries (default: 60.0 seconds)

- **Timeout Configuration**:

  Timeouts are applied at the connection pool level via `command_timeout`, protecting all queries automatically:

  ```python
  # Configure pool-level timeout (recommended)
  node = AsyncSQLDatabaseNode(
      database_type="postgresql",
      host="localhost",
      database="myapp",
      user="dbuser",
      password="dbpass",
      command_timeout=30.0  # All queries timeout after 30 seconds
  )
  ```

  **How it works**:
  - Applied automatically to all queries through the connection pool
  - Protects against slow queries without per-query timeout parameters
  - Used by health checks and all database operations
  - Default 60 seconds is suitable for most applications

  **Best practices**:
  - Use default 60 seconds for typical OLTP queries
  - Increase to 300+ seconds for analytical/batch queries
  - Set to 5-10 seconds for health checks in load balancers
  - Monitor slow query logs to optimize timeout values

- **Transaction Management Modes**:
  ```python
  # AUTO MODE (default) - Each query in its own transaction
  node = AsyncSQLDatabaseNode(
      database_type="postgresql",
      host="localhost",
      database="myapp",
      user="dbuser",
      password="dbpass",
      transaction_mode="auto"  # Default
  )

  # MANUAL MODE - Explicit transaction control
  node = AsyncSQLDatabaseNode(
      database_type="postgresql",
      host="localhost",
      database="myapp",
      user="dbuser",
      password="dbpass",
      transaction_mode="manual"
  )

  # Begin transaction
  await node.begin_transaction()
  try:
      await node.async_run(query="UPDATE accounts SET balance = balance - 100 WHERE id = 1")
      await node.async_run(query="UPDATE accounts SET balance = balance + 100 WHERE id = 2")
      await node.commit()
  except Exception:
      await node.rollback()
      raise

  # NONE MODE - No transaction wrapping (for read-only operations)
  node = AsyncSQLDatabaseNode(
      database_type="postgresql",
      host="localhost",
      database="myapp",
      user="dbuser",
      password="dbpass",
      transaction_mode="none"
  )
  ```

- **Optimistic Locking Integration** ⭐ **NEW**:
  ```python
  # Read with version tracking
  node = AsyncSQLDatabaseNode(
      database_type="postgresql",
      host="localhost",
      database="myapp",
      user="dbuser",
      password="dbpass"
  )

  # Enable optimistic locking mode
  result = await node.async_run(
      query="SELECT *, version FROM users WHERE id = :user_id",
      params={"user_id": 123},
      fetch_mode="one",
      enable_optimistic_locking=True
  )

  # Update with version check
  update_result = await node.async_run(
      query="UPDATE users SET name = :name, version = version + 1 WHERE id = :id AND version = :expected_version",
      params={
          "name": "John Updated",
          "id": 123,
          "expected_version": result["result"]["data"]["version"]
      },
      enable_optimistic_locking=True,
      conflict_resolution="retry"
  )
  ```

- **Advanced Parameter Handling** ⭐ **ENHANCED**:
  ```python
  # PostgreSQL ANY() array operations
  await node.async_run(
      query="SELECT * FROM users WHERE id = ANY(:user_ids)",
      params={"user_ids": [1, 2, 3, 4, 5]},  # Automatically converted
      fetch_mode="all"
  )

  # Named parameters with type conversion
  result = await node.async_run(
      query="SELECT * FROM orders WHERE created_date >= :start_date AND status = :status",
      params={
          "start_date": "2024-01-01",  # Converted to appropriate date type
          "status": "active"
      },
      fetch_mode="all"
  )

  # Complex data types (JSON, arrays)
  await node.async_run(
      query="INSERT INTO events (data, tags) VALUES (:event_data, :tags)",
      params={
          "event_data": {"user_id": 123, "action": "login"},  # JSON serialized
          "tags": ["auth", "security", "user"]  # Array handling
      }
  )
  ```

- **Connection Pool Sharing** ⭐ **ENHANCED**:
  ```python
  # Multiple nodes sharing the same connection pool
  node1 = AsyncSQLDatabaseNode(
      name="reader",
      database_type="postgresql",
      host="localhost",
      database="myapp",
      share_pool=True  # Default
  )

  node2 = AsyncSQLDatabaseNode(
      name="writer",
      database_type="postgresql",
      host="localhost",
      database="myapp",
      share_pool=True  # Shares pool with node1
  )
  ```

- **Retry Logic with Error Handling** ⭐ **ENHANCED**:
  ```python
  from kailash.nodes.data.async_sql import RetryConfig

  # Custom retry configuration
  retry_config = RetryConfig(
      max_retries=5,
      base_delay=0.5,
      max_delay=10.0,
      backoff_multiplier=2.0,
      jitter=True
  )

  node = AsyncSQLDatabaseNode(
      database_type="postgresql",
      host="localhost",
      database="myapp",
      retry_config=retry_config
  )

  # Automatically retries on:
  # - Connection failures
  # - DNS resolution errors
  # - Network timeouts
  # - Temporary database locks
  # - Connection pool exhaustion
  ```

- **Security and Query Validation** ⭐ **ENHANCED**:
  ```python
  # Secure configuration for production
  node = AsyncSQLDatabaseNode(
      database_type="postgresql",
      host="localhost",
      database="myapp",
      validate_queries=True,   # Enable security validation
      allow_admin=False       # Disable admin operations
  )

  # Admin operations require explicit permission
  admin_node = AsyncSQLDatabaseNode(
      database_type="postgresql",
      host="localhost",
      database="myapp",
      validate_queries=True,
      allow_admin=True  # Required for CREATE, DROP, ALTER, etc.
  )

  await admin_node.async_run(
      query="CREATE TEMPORARY TABLE temp_analysis AS SELECT * FROM users WHERE active = :active",
      params={"active": True}
  )
  ```

- **Result Format and Data Access**:
  ```python
  # Standard result format
  result = await node.async_run(
      query="SELECT id, name, email FROM users WHERE active = :active",
      params={"active": True},
      fetch_mode="all"
  )

  # Access data: result["result"]["data"]
  users = result["result"]["data"]  # List of dictionaries

  # Single record fetch
  user = await node.async_run(
      query="SELECT * FROM users WHERE id = :user_id",
      params={"user_id": 123},
      fetch_mode="one"
  )
  user_data = user["result"]["data"]  # Single dictionary or None

  # Iterator for large datasets
  async for batch in await node.async_run(
      query="SELECT * FROM large_table",
      fetch_mode="iterator",
      fetch_size=1000
  ):
      process_batch(batch["result"]["data"])
  ```

- **Best For**:
  - Production applications requiring transaction control
  - Concurrent workflows needing optimistic locking
  - Applications with complex parameter handling needs
  - Systems requiring comprehensive error handling and retries
  - Enterprise applications needing security validation

- **Performance Considerations**:
  - Connection pool sharing reduces resource usage
  - Retry logic handles transient failures gracefully
  - Transaction modes optimize for different use cases
  - Parameter conversion minimizes database-specific code

### SQLDatabaseNode
- **Module**: `kailash.nodes.data.sql`
- **Purpose**: Synchronous SQL query execution with shared connection pooling
- **Key Features**:
  - Unified parameter handling: supports both list and dict parameters
  - Named parameter binding using `:param_name` syntax (recommended)
  - Automatic conversion of positional parameters (`?`, `$1`, `%s`) to named parameters
  - Shared connection pools for efficient resource utilization
  - Transaction support with automatic commit/rollback
  - Access control integration
- **Constructor Parameters**:
  - `connection_string`: Database connection URL (required)
  - `pool_size`: Connection pool size (default: 5)
  - `max_overflow`: Maximum overflow connections (default: 10)
  - `pool_timeout`: Connection timeout seconds (default: 30)
  - `pool_recycle`: Connection recycle time seconds (default: 3600)
  - `pool_pre_ping`: Test connections before use (default: True)
- **Runtime Parameters** (passed to `execute()`):
  - `query`: SQL query to execute
  - `parameters`: Query parameters (dict for named, list for positional)
  - `operation`: Operation type ("execute", "fetch_all", "fetch_one")
  - `result_format`: Output format ("dict", "list", "raw")
- **Parameter Format Examples**:
  ```python
  # Named parameters (recommended)
  node.execute(
      query="SELECT * FROM users WHERE active = :active AND age > :min_age",
      parameters={"active": True, "min_age": 18},
      operation="fetch_all"
  )

  # Positional parameters (auto-converted to named)
  node.execute(
      query="SELECT * FROM users WHERE id = ?",
      parameters=[123],
      operation="fetch_one"
  )
  ```
- **Best For**: Production applications requiring connection pooling and parameter flexibility

### OptimisticLockingNode ⭐ **NEW - ENTERPRISE CONCURRENCY**
- **Module**: `kailash.nodes.data.optimistic_locking`
- **Purpose**: Enterprise-grade concurrency control with version-based conflict detection
- **Key Features**:
  - **✅ Version-Based Concurrency**: Prevents lost updates in concurrent environments
  - **✅ Conflict Resolution Strategies**: Fail-fast, retry, merge, last-writer-wins
  - **✅ Automatic Retry Logic**: Configurable retry with exponential backoff
  - **✅ Performance Metrics**: Lock contention monitoring and conflict analysis
  - **✅ Database Integration**: Seamless integration with AsyncSQLDatabaseNode
  - **✅ Batch Operations**: Support for multiple record updates with conflict handling

- **Constructor Parameters**:
  - `version_field`: Version column name (default: `"version"`)
  - `max_retries`: Maximum retry attempts (default: 3)
  - `retry_delay`: Initial retry delay in seconds (default: 0.1)
  - `retry_backoff_multiplier`: Backoff multiplier for retries (default: 2.0)
  - `default_conflict_resolution`: Default conflict strategy (default: `ConflictResolution.RETRY`)

- **Conflict Resolution Strategies**:
  ```python
  from kailash.nodes.data.optimistic_locking import ConflictResolution, OptimisticLockingNode

  # FAIL_FAST - Immediately fail on version conflict
  lock_manager = OptimisticLockingNode(
      default_conflict_resolution=ConflictResolution.FAIL_FAST
  )

  # RETRY - Automatically retry operation with updated version
  lock_manager = OptimisticLockingNode(
      default_conflict_resolution=ConflictResolution.RETRY,
      max_retries=5,
      retry_delay=0.2
  )

  # MERGE - Attempt to merge non-conflicting changes
  lock_manager = OptimisticLockingNode(
      default_conflict_resolution=ConflictResolution.MERGE
  )

  # LAST_WRITER_WINS - Override with new data (use with caution)
  lock_manager = OptimisticLockingNode(
      default_conflict_resolution=ConflictResolution.LAST_WRITER_WINS
  )
  ```

- **Basic Usage Examples**:
  ```python
  # Initialize lock manager
  lock_manager = OptimisticLockingNode(
      version_field="version",
      max_retries=3
  )

  # Read with version tracking
  result = await lock_manager.execute(
      action="read_with_version",
      table_name="users",
      record_id=123,
      connection=db_connection
  )

  current_data = result["data"]
  current_version = result["version"]

  # Update with version check
  update_result = await lock_manager.execute(
      action="update_with_version",
      table_name="users",
      record_id=123,
      update_data={"name": "John Updated", "email": "john@example.com"},
      expected_version=current_version,
      conflict_resolution="retry",
      connection=db_connection
  )

  if update_result["lock_status"] == "success":
      print(f"Update successful. New version: {update_result['new_version']}")
  else:
      print(f"Update failed: {update_result['lock_status']}")
  ```

- **Batch Operations** ⭐ **ADVANCED**:
  ```python
  # Batch update with conflict handling
  batch_updates = [
      {"record_id": 1, "update_data": {"status": "active"}, "expected_version": 5},
      {"record_id": 2, "update_data": {"status": "inactive"}, "expected_version": 3},
      {"record_id": 3, "update_data": {"status": "pending"}, "expected_version": 7}
  ]

  batch_result = await lock_manager.execute(
      action="batch_update",
      table_name="users",
      batch_updates=batch_updates,
      conflict_resolution="retry",
      connection=db_connection
  )

  # Results per record
  for record_result in batch_result["results"]:
      if record_result["lock_status"] == "success":
          print(f"Record {record_result['record_id']} updated successfully")
      else:
          print(f"Record {record_result['record_id']} failed: {record_result['lock_status']}")
  ```

- **Integration with AsyncSQLDatabaseNode**:
  ```python
  # Combined optimistic locking with async SQL operations
  async_sql_node = AsyncSQLDatabaseNode(
      database_type="postgresql",
      host="localhost",
      database="myapp",
      transaction_mode="manual"  # Manual mode for precise control
  )

  lock_manager = OptimisticLockingNode()

  # Get connection from SQL node
  await async_sql_node.connect()
  connection = async_sql_node._adapter

  # Begin transaction
  transaction = await connection.begin_transaction()

  try:
      # Read current state
      user = await lock_manager.execute(
          action="read_with_version",
          table_name="users",
          record_id=user_id,
          connection=connection,
          transaction=transaction
      )

      # Business logic
      updated_data = process_user_data(user["data"])

      # Update with version check
      result = await lock_manager.execute(
          action="update_with_version",
          table_name="users",
          record_id=user_id,
          update_data=updated_data,
          expected_version=user["version"],
          connection=connection,
          transaction=transaction
      )

      await connection.commit_transaction(transaction)

  except Exception as e:
      await connection.rollback_transaction(transaction)
      raise
  ```

- **Performance Monitoring**:
  ```python
  # Get lock contention metrics
  metrics = lock_manager.get_metrics()

  print(f"Total operations: {metrics['total_operations']}")
  print(f"Success rate: {metrics['successful_operations'] / metrics['total_operations']:.2%}")
  print(f"Version conflicts: {metrics['version_conflicts']}")
  print(f"Average retries: {metrics['avg_retry_count']:.1f}")

  # Conflict history analysis
  recent_conflicts = lock_manager.get_conflict_history(limit=10)
  for conflict in recent_conflicts:
      print(f"Conflict in {conflict['table_name']} record {conflict['record_id']} at {conflict['timestamp']}")
  ```

- **Best For**:
  - High-concurrency applications with frequent updates
  - E-commerce systems (inventory, orders, payments)
  - Financial applications requiring data consistency
  - Multi-tenant applications with shared data
  - Enterprise systems with audit requirements

- **Performance Considerations**:
  - Version fields should be indexed for performance
  - Retry logic reduces conflict impact in high-concurrency scenarios
  - Conflict monitoring helps identify hotspot records
  - Batch operations reduce network round-trips

### QueryBuilder ⭐ **NEW** - MongoDB-Style Query Building
- **Module**: `kailash.nodes.data.query_builder`
- **Purpose**: Production-ready query builder with MongoDB-style operators that generates optimized SQL
- **Key Features**:
  - **MongoDB-Style Operators**: $eq, $ne, $lt, $lte, $gt, $gte, $in, $nin, $like, $ilike, $regex, $and, $or, $has_key
  - **Multi-Database Support**: PostgreSQL, MySQL, SQLite with dialect-specific optimizations
  - **Automatic Tenant Isolation**: Built-in tenant_id injection for multi-tenant applications
  - **Parameter Binding**: Automatic parameter binding with SQL injection prevention
  - **Comprehensive Validation**: Type checking and operator validation
  - **Fluent API**: Method chaining for readable query construction
  - **JSON Support**: PostgreSQL JSON operators (?, ?|, ?&, @>) and MySQL JSON functions
- **Supported Operations**:
  - **SELECT**: Build select queries with fields, conditions, and tenant isolation
  - **UPDATE**: Build update queries with WHERE conditions
  - **DELETE**: Build delete queries with WHERE conditions
  - **INSERT**: Build insert queries (planned for v0.6.7)
- **Parameters**:
  - `dialect`: Database dialect ("postgresql", "mysql", "sqlite")
  - `table_name`: Target table name
  - `tenant_id`: Optional tenant ID for multi-tenant isolation
- **Factory Function**: `create_query_builder(dialect="postgresql")`
- **Best For**:
  - Multi-tenant applications requiring query isolation
  - Applications with complex query logic
  - Teams familiar with MongoDB query syntax
  - Cross-database applications
  - Applications requiring SQL injection prevention
- **Example**:
  ```python
  from kailash.nodes.data.query_builder import create_query_builder

  # Create PostgreSQL query builder
  builder = create_query_builder("postgresql")

  # Build complex query with MongoDB-style operators
  builder.table("users").tenant("tenant_123")
  builder.where("age", "$gt", 18)
  builder.where("status", "$in", ["active", "premium"])
  builder.where("metadata", "$has_key", "preferences")

  # Generate SQL and parameters
  sql, params = builder.build_select(["name", "email", "created_at"])
  # Result: SELECT name, email, created_at FROM users WHERE tenant_id = $1 AND age > $2 AND status = ANY($3) AND metadata ? $4
  # Params: ["tenant_123", 18, ["active", "premium"], "preferences"]

  # Build update query
  builder.reset().table("users").where("id", "$eq", 123)
  sql, params = builder.build_update({"last_login": "2024-01-01"})

  # Build delete query
  builder.reset().table("users").where("status", "$eq", "inactive")
  sql, params = builder.build_delete()
  ```
- **MongoDB Operators**:
  - **$eq**: Equal to
  - **$ne**: Not equal to
  - **$lt**: Less than
  - **$lte**: Less than or equal to
  - **$gt**: Greater than
  - **$gte**: Greater than or equal to
  - **$in**: In array
  - **$nin**: Not in array
  - **$like**: SQL LIKE pattern
  - **$ilike**: Case-insensitive LIKE (PostgreSQL only)
  - **$regex**: Regular expression match
  - **$and**: Logical AND (implicit)
  - **$or**: Logical OR (planned for v0.6.7)
  - **$has_key**: JSON key exists (PostgreSQL/MySQL)
- **Testing**: 33 unit tests, 8 integration tests with real databases

### QueryCache ⭐ **NEW** - Redis Query Result Caching
- **Module**: `kailash.nodes.data.query_cache`
- **Purpose**: Enterprise-grade query result caching with Redis backend
- **Key Features**:
  - **Multiple Cache Patterns**: Cache-aside, write-through, write-behind, refresh-ahead
  - **Intelligent Invalidation**: TTL-based, manual, pattern-based, event-based strategies
  - **Tenant Isolation**: Automatic tenant-based cache key separation
  - **Automatic Key Generation**: SHA-256 based cache keys with query normalization
  - **Pattern-Based Invalidation**: Table-based cache invalidation using Redis SETs
  - **Health Monitoring**: Redis connection health checks and statistics
  - **Configurable TTL**: Per-query and global TTL settings
  - **Error Resilience**: Graceful degradation when Redis is unavailable
  - **Comprehensive Metrics**: Cache hit rates, key counts, Redis statistics
- **Cache Patterns**:
  - **CACHE_ASIDE**: Manual cache management (default)
  - **WRITE_THROUGH**: Synchronous cache updates
  - **WRITE_BEHIND**: Asynchronous cache updates
  - **REFRESH_AHEAD**: Proactive cache refresh
- **Invalidation Strategies**:
  - **TTL**: Time-based expiration (default)
  - **MANUAL**: Manual cache invalidation
  - **PATTERN_BASED**: Table-based pattern invalidation
  - **EVENT_BASED**: Event-driven invalidation
- **Parameters**:
  - `redis_host`: Redis server host (default: "localhost")
  - `redis_port`: Redis server port (default: 6379)
  - `redis_db`: Redis database number (default: 0)
  - `redis_password`: Redis password (optional)
  - `default_ttl`: Default TTL in seconds (default: 3600)
  - `cache_pattern`: Cache pattern (default: CACHE_ASIDE)
  - `invalidation_strategy`: Invalidation strategy (default: TTL)
  - `key_prefix`: Cache key prefix (default: "kailash:query")
- **Operations**:
  - `get(query, parameters, tenant_id)`: Get cached result
  - `set(query, parameters, result, tenant_id, ttl)`: Cache result
  - `invalidate(query, parameters, tenant_id)`: Invalidate specific cache entry
  - `invalidate_table(table_name, tenant_id)`: Invalidate all cache entries for table
  - `clear_all(tenant_id)`: Clear all cache entries (globally or per tenant)
  - `get_stats()`: Get cache statistics
  - `health_check()`: Check cache and Redis health
- **Best For**:
  - High-traffic applications with repeated queries
  - Applications with expensive query operations
  - Multi-tenant applications requiring cache isolation
  - Applications requiring fine-grained cache control
  - Systems with complex cache invalidation requirements
- **Example**:
  ```python
  from kailash.nodes.data.query_cache import QueryCache, CacheInvalidationStrategy

  # Create cache with pattern-based invalidation
  cache = QueryCache(
      redis_host="localhost",
      redis_port=6379,
      invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED,
      default_ttl=3600
  )

  # Cache query result
  query = "SELECT * FROM users WHERE age > $1"
  parameters = [18]
  result = {"users": [{"id": 1, "name": "John", "age": 25}]}

  success = cache.set(query, parameters, result, tenant_id="tenant_123")

  # Retrieve cached result
  cached_result = cache.get(query, parameters, tenant_id="tenant_123")
  if cached_result:
      print(f"Cache hit: {cached_result['result']}")

  # Invalidate all cache entries for users table
  deleted_count = cache.invalidate_table("users", tenant_id="tenant_123")

  # Get cache statistics
  stats = cache.get_stats()
  print(f"Hit rate: {stats['hit_rate']:.2%}")
  print(f"Total keys: {stats['total_keys']}")

  # Health check
  health = cache.health_check()
  print(f"Cache status: {health['status']}")
  ```
- **Factory Function**: `create_query_cache(config)` for configuration-based creation
- **Testing**: 40 unit tests, 8 integration tests with real Redis

### SQLQueryBuilderNode (Deprecated)
- **Module**: `kailash.nodes.data.sql`
- **Purpose**: Build SQL queries programmatically
- **Status**: ⚠️ **DEPRECATED** - Use QueryBuilder instead
- **Parameters**:
  - `table`: Table name
  - `operation`: SELECT, INSERT, UPDATE, DELETE
  - `conditions`: WHERE conditions

## Streaming Nodes

### EventStreamNode
- **Module**: `kailash.nodes.data.streaming`
- **Purpose**: Handle event streams
- **Parameters**:
  - `stream_url`: Stream endpoint
  - `event_types`: Events to handle

### KafkaConsumerNode
- **Module**: `kailash.nodes.data.streaming`
- **Purpose**: Consume Kafka messages
- **Parameters**:
  - `bootstrap_servers`: Kafka servers
  - `topic`: Topic to consume
  - `group_id`: Consumer group ID

### StreamPublisherNode
- **Module**: `kailash.nodes.data.streaming`
- **Purpose**: Publish to streams
- **Parameters**:
  - `stream_url`: Stream endpoint
  - `data`: Data to publish

### WebSocketNode
- **Module**: `kailash.nodes.data.streaming`
- **Purpose**: WebSocket connections
- **Parameters**:
  - `ws_url`: WebSocket URL
  - `on_message`: Message handler

## Vector Database Nodes

### EmbeddingNode
- **Module**: `kailash.nodes.data.vector_db`
- **Purpose**: Manage embeddings for vector databases
- **Parameters**:
  - `embedding_model`: Model to use
  - `vector_store`: Storage backend

### TextSplitterNode
- **Module**: `kailash.nodes.data.vector_db`
- **Purpose**: Split text into chunks
- **Parameters**:
  - `chunk_size`: Size of chunks
  - `chunk_overlap`: Overlap between chunks
  - `separator`: Split separator

### VectorDatabaseNode
- **Module**: `kailash.nodes.data.vector_db`
- **Purpose**: Vector database operations
- **Parameters**:
  - `db_type`: Database type (pinecone, weaviate, etc.)
  - `connection_params`: Connection parameters

## Source Management Nodes

### DocumentSourceNode
- **Module**: `kailash.nodes.data.sources`
- **Purpose**: Manage document sources
- **Parameters**:
  - `source_path`: Document location
  - `metadata`: Document metadata

### QuerySourceNode
- **Module**: `kailash.nodes.data.sources`
- **Purpose**: Manage query sources
- **Parameters**:
  - `query_template`: Query template
  - `parameters`: Query parameters

## Retrieval Nodes

### HybridRetrieverNode ⭐ **NEW**
- **Module**: `kailash.nodes.data.retrieval`
- **Purpose**: State-of-the-art hybrid retrieval combining dense and sparse methods
- **Key Features**: Combines semantic (dense) and keyword (sparse) retrieval for 20-30% better performance
- **Parameters**:
  - `fusion_strategy`: Fusion method - "rrf", "linear", or "weighted" (default: "rrf")
  - `dense_weight`: Weight for dense retrieval (0.0-1.0, default: 0.6)
  - `sparse_weight`: Weight for sparse retrieval (0.0-1.0, default: 0.4)
  - `top_k`: Number of results to return (default: 5)
  - `rrf_k`: RRF parameter for rank fusion (default: 60)
- **Best For**: Production RAG systems, enterprise search, multi-modal retrieval
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  retriever = HybridRetrieverNode(fusion_strategy="rrf", top_k=5)
  result = retriever.run(
      query="machine learning algorithms",
      dense_results=vector_search_results,  # From semantic search
      sparse_results=keyword_search_results  # From BM25/keyword search
  )
  hybrid_results = result["hybrid_results"]  # Best of both methods

  ```

### RelevanceScorerNode
- **Module**: `kailash.nodes.data.retrieval`
- **Purpose**: Score document relevance with advanced ranking
- **Parameters**:
  - `similarity_method`: Scoring method - "cosine", "dot", "euclidean" (default: "cosine")
  - `top_k`: Number of top results to return (default: 5)
- **Enhanced Features**: Works with embeddings for precise relevance scoring
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  scorer = RelevanceScorerNode(similarity_method="cosine", top_k=3)
  result = scorer.run(
      chunks=retrieved_chunks,
      query_embedding=query_embeddings,
      chunk_embeddings=chunk_embeddings
  )
  relevant_chunks = result["relevant_chunks"]  # Top ranked results

  ```

## SharePoint Integration Nodes

### SharePointGraphReader
- **Module**: `kailash.nodes.data.sharepoint_graph`
- **Purpose**: Read files from SharePoint using Microsoft Graph API
- **Parameters**:
  - `tenant_id`: Azure AD tenant ID
  - `client_id`: Azure AD app client ID
  - `client_secret`: Azure AD app client secret
  - `site_url`: SharePoint site URL
  - `operation`: Operation type (list_files, download_file)
  - `library_name`: Document library name
- **Example**:
  ```python
  sharepoint = SharePointGraphReader()
  result = sharepoint.run(
      tenant_id=os.getenv("SHAREPOINT_TENANT_ID"),
      client_id=os.getenv("SHAREPOINT_CLIENT_ID"),
      client_secret=os.getenv("SHAREPOINT_CLIENT_SECRET"),
      site_url="https://company.sharepoint.com/sites/YourSite",
      operation="list_files",
      library_name="Documents"
  )

  ```

### SharePointGraphWriter
- **Module**: `kailash.nodes.data.sharepoint_graph`
- **Purpose**: Upload files to SharePoint using Microsoft Graph API
- **Parameters**: Same authentication parameters plus:
  - `file_path`: Destination file path
  - `content`: File content to upload

## See Also
- [Transform Nodes](06-transform-nodes.md) - Data transformation and processing
- [AI Nodes](02-ai-nodes.md) - AI and ML capabilities
- [API Reference](../api/05-nodes-data.yaml) - Detailed API documentation
