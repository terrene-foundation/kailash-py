# Async Database & ABAC Infrastructure

This guide covers the enterprise-grade async database capabilities and attribute-based access control (ABAC) features.

## Overview

The async database and ABAC infrastructure provides:
- **WorkflowConnectionPool**: ⭐ Production-grade connection pooling with actor-based fault tolerance (RECOMMENDED)
- **AsyncSQLDatabaseNode**: Non-blocking database operations with single connection reuse
- **AsyncConnectionManager**: Centralized connection pool management
- **AsyncPostgreSQLVectorNode**: pgvector operations for AI/ML workflows
- **Enhanced ABAC**: Attribute-based access control with complex conditions
- **Migration Framework**: Django-inspired async-first database migrations

> **Important**: For production applications, use `WorkflowConnectionPool` instead of `AsyncSQLDatabaseNode` for better connection management, fault tolerance, and performance.

## WorkflowConnectionPool (Production Recommended)

Enterprise-grade connection pooling with actor-based fault tolerance, health monitoring, and automatic recovery.

### Key Features
- **Actor-based architecture**: Each connection is an independent actor with supervisor monitoring
- **Connection pooling**: Min/max pool sizes with automatic scaling
- **Health monitoring**: Automatic health checks and connection recycling
- **Fault tolerance**: Supervisor-based failure recovery
- **Pre-warming**: Pattern-based connection preparation
- **Comprehensive metrics**: Detailed statistics and monitoring

### Basic Usage

```python
from kailash.nodes.data import WorkflowConnectionPool

# Create production connection pool
pool = WorkflowConnectionPool(
    name="main_pool",
    database_type="postgresql",
    host="localhost",
    port=5432,
    database="production_db",
    user="app_user",
    password="secure_password",
    min_connections=10,      # Minimum pool size
    max_connections=50,      # Maximum pool size
    health_threshold=70,     # Recycle connections below 70% health
    pre_warm=True           # Pre-warm based on usage patterns
)

# Initialize pool (do this once at startup)
await pool.execute({"operation": "initialize"})

# Use in workflows
async def execute_query(query, params):
    # Acquire connection
    conn = await pool.execute({"operation": "acquire"})
    conn_id = conn["connection_id"]

    try:
        # Execute query
        result = await pool.execute({
            "operation": "execute",
            "connection_id": conn_id,
            "query": query,
            "params": params,
            "fetch_mode": "all"
        })
        return result["data"]
    finally:
        # Always release connection
        await pool.execute({
            "operation": "release",
            "connection_id": conn_id
        })

# Monitor pool health
stats = await pool.execute({"operation": "stats"})
print(f"Pool efficiency: {stats['queries']['executed'] / stats['connections']['created']:.1f} queries/connection")
```

### Transaction Support

```python
async def transfer_funds(from_account, to_account, amount):
    conn = await pool.execute({"operation": "acquire"})
    conn_id = conn["connection_id"]

    try:
        # Start transaction
        await pool.execute({
            "operation": "execute",
            "connection_id": conn_id,
            "query": "BEGIN",
            "fetch_mode": "one"
        })

        # Perform operations
        await pool.execute({
            "operation": "execute",
            "connection_id": conn_id,
            "query": "UPDATE accounts SET balance = balance - $1 WHERE id = $2",
            "params": [amount, from_account],
            "fetch_mode": "one"
        })

        await pool.execute({
            "operation": "execute",
            "connection_id": conn_id,
            "query": "UPDATE accounts SET balance = balance + $1 WHERE id = $2",
            "params": [amount, to_account],
            "fetch_mode": "one"
        })

        # Commit
        await pool.execute({
            "operation": "execute",
            "connection_id": conn_id,
            "query": "COMMIT",
            "fetch_mode": "one"
        })

    except Exception as e:
        # Rollback on error
        await pool.execute({
            "operation": "execute",
            "connection_id": conn_id,
            "query": "ROLLBACK",
            "fetch_mode": "one"
        })
        raise
    finally:
        await pool.execute({
            "operation": "release",
            "connection_id": conn_id
        })
```

### Migration from AsyncSQLDatabaseNode

See the [migration guide](../migration-guides/async-sql-to-workflowconnectionpool.md) for step-by-step instructions on migrating from AsyncSQLDatabaseNode to WorkflowConnectionPool.

## AsyncSQLDatabaseNode

High-performance async database operations supporting PostgreSQL, MySQL, and SQLite.

### Basic Usage

```python
from kailash.nodes.data import AsyncSQLDatabaseNode

# Create async database node
node = AsyncSQLDatabaseNode(
    name="fetch_active_users",
    database_type="postgresql",
    host="localhost",
    database="myapp",
    user="dbuser",
    password="dbpass",
    query="SELECT * FROM users WHERE active = :active AND department = :dept",
    params={"active": True, "dept": "engineering"},
    pool_size=10,
    max_pool_size=20
)

# Execute in workflow
workflow = WorkflowBuilder()
workflow.add_node("AsyncSQLDatabaseNode", "users", {
    "query": "SELECT * FROM users WHERE active = true",
    "pool_size": 10,
    "max_pool_size": 20
})
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

```

### Connection String Support

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

# Using connection string
node = AsyncSQLDatabaseNode(
    name="query_db",
    database_type="postgresql",
    connection_string="postgresql://user:pass@host:5432/db",
    query="SELECT COUNT(*) as total FROM orders",
    fetch_mode="one"
)

```

### Fetch Modes

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

# Fetch single row
single_node = AsyncSQLDatabaseNode(
    name="get_user",
    connection_string=conn_str,
    query="SELECT * FROM users WHERE id = :id",
    params={"id": 123},
    fetch_mode="one"  # Returns single dict or None
)

# Fetch all rows (default)
all_node = AsyncSQLDatabaseNode(
    name="list_users",
    connection_string=conn_str,
    query="SELECT * FROM users",
    fetch_mode="all"  # Returns list of dicts
)

# Fetch specific number
batch_node = AsyncSQLDatabaseNode(
    name="recent_orders",
    connection_string=conn_str,
    query="SELECT * FROM orders ORDER BY created_at DESC",
    fetch_mode="many",
    fetch_size=100  # Returns first 100 rows
)

```

## AsyncConnectionManager

Centralized connection pool management with multi-tenant support.

### Features

- Connection pooling per tenant
- Automatic health checks
- Pool metrics and monitoring
- Graceful degradation
- Connection retry logic

### Direct Usage

```python
from kailash.nodes.data import get_connection_manager

# Get connection manager instance
manager = get_connection_manager()

# Get connection from pool
async with manager.get_connection(
    tenant_id="tenant1",
    db_config={
        "type": "postgresql",
        "host": "localhost",
        "database": "myapp",
        "user": "dbuser",
        "password": "dbpass"
    }
) as conn:
    # Use connection
    rows = await conn.fetch("SELECT * FROM users")

```

### Pool Configuration

```python
from kailash.nodes.data.async_connection import PoolConfig

# Custom pool configuration
pool_config = PoolConfig(
    min_size=5,
    max_size=50,
    connection_timeout=30.0,
    command_timeout=120.0,
    health_check_interval=60.0
)

# Use with node
node = AsyncSQLDatabaseNode(
    name="heavy_query",
    connection_string=conn_str,
    query="SELECT * FROM large_table",
    pool_size=pool_config.min_size,
    max_pool_size=pool_config.max_size,
    timeout=pool_config.command_timeout
)

```

### Monitoring

```python
# Get pool metrics
metrics = manager.get_metrics(tenant_id="tenant1")
for pool_key, pool_metrics in metrics.items():
    print(f"Pool: {pool_key}")
    print(f"  Active connections: {pool_metrics['active_connections']}")
    print(f"  Total requests: {pool_metrics['total_requests']}")
    print(f"  Average wait time: {pool_metrics['avg_wait_time']:.2f}s")
    print(f"  Health: {'Healthy' if pool_metrics['is_healthy'] else 'Unhealthy'}")

```

## AsyncPostgreSQLVectorNode

Vector operations for AI/ML workflows using pgvector.

### Table Management

```python
from kailash.nodes.data import AsyncPostgreSQLVectorNode

# Create vector table
create_node = AsyncPostgreSQLVectorNode(
    name="create_embeddings_table",
    connection_string="postgresql://localhost/vectordb",
    table_name="document_embeddings",
    dimension=768,  # For BERT embeddings
    operation="create_table"
)

# Create index for performance
index_node = AsyncPostgreSQLVectorNode(
    name="create_hnsw_index",
    connection_string="postgresql://localhost/vectordb",
    table_name="document_embeddings",
    operation="create_index",
    index_type="hnsw",
    distance_metric="cosine",
    m=16,  # HNSW parameter
    ef_construction=64
)

```

### Inserting Vectors

```python
# Single vector insert
insert_node = AsyncPostgreSQLVectorNode(
    name="insert_embedding",
    connection_string="postgresql://localhost/vectordb",
    table_name="document_embeddings",
    operation="insert",
    vector=embedding,  # List of floats
    metadata={"doc_id": "DOC123", "title": "Important Document"}
)

# Batch insert
batch_insert = AsyncPostgreSQLVectorNode(
    name="insert_batch",
    connection_string="postgresql://localhost/vectordb",
    table_name="document_embeddings",
    operation="insert",
    vectors=embeddings_list,  # List of vectors
    metadata=[
        {"doc_id": "DOC1", "type": "article"},
        {"doc_id": "DOC2", "type": "report"},
        # ... metadata for each vector
    ]
)

```

### Similarity Search

```python
# Basic similarity search
search_node = AsyncPostgreSQLVectorNode(
    name="find_similar",
    connection_string="postgresql://localhost/vectordb",
    table_name="document_embeddings",
    operation="search",
    vector=query_embedding,
    distance_metric="cosine",  # or "l2", "ip"
    limit=10
)

# Search with metadata filtering
filtered_search = AsyncPostgreSQLVectorNode(
    name="search_articles",
    connection_string="postgresql://localhost/vectordb",
    table_name="document_embeddings",
    operation="search",
    vector=query_embedding,
    distance_metric="cosine",
    metadata_filter="metadata->>'type' = 'article'",
    limit=5
)

# Optimized search with HNSW parameters
optimized_search = AsyncPostgreSQLVectorNode(
    name="fast_search",
    connection_string="postgresql://localhost/vectordb",
    table_name="document_embeddings",
    operation="search",
    vector=query_embedding,
    distance_metric="l2",
    ef_search=40,  # Higher = more accurate but slower
    limit=20
)

```

## ABAC (Attribute-Based Access Control)

Enhanced access control based on user and resource attributes.

### Basic ABAC Setup

```python
from kailash.access_control import AccessControlManager
from kailash.access_control import PermissionRule, NodePermission, PermissionEffect

# Create enhanced ACM
acm = AccessControlManager(strategy="abac")

# Add ABAC rule based on department
acm.add_rule(PermissionRule(
    id="dept_data_access",
    resource_type="node",
    resource_id="department_data",
    permission=NodePermission.READ_OUTPUT,
    effect=PermissionEffect.ALLOW,
    conditions={
        "type": "attribute_expression",
        "value": {
            "attribute_path": "user.attributes.department",
            "operator": "hierarchical_match",
            "value": "engineering"
        }
    }
))

```

### Complex Attribute Conditions

```python
from kailash.access_control_enhanced import (
    create_attribute_condition,
    create_complex_condition
)

# Multiple conditions with AND
complex_rule = PermissionRule(
    id="sensitive_access",
    resource_type="node",
    resource_id="sensitive_data",
    permission=NodePermission.EXECUTE,
    effect=PermissionEffect.ALLOW,
    conditions=create_complex_condition("and", [
        create_attribute_condition(
            "user.attributes.security_clearance",
            "in",
            ["secret", "top_secret"]
        ),
        create_attribute_condition(
            "user.attributes.department",
            "hierarchical_match",
            "finance"
        ),
        {
            "type": "time_of_day",
            "value": {"start": "08:00", "end": "18:00"}
        }
    ])
)

```

### Attribute-Based Data Masking

```python
from kailash.access_control_abac import (
    AttributeMaskingRule,
    AttributeCondition,
    AttributeOperator,
    AttributeExpression,
    LogicalOperator
)

# Mask SSN for non-HR users
acm.add_masking_rule(
    "employee_data",
    AttributeMaskingRule(
        field_path="ssn",
        mask_type="redact",
        condition=AttributeExpression(
            operator=LogicalOperator.NOT,
            conditions=[
                AttributeCondition(
                    attribute_path="user.attributes.department",
                    operator=AttributeOperator.EQUALS,
                    value="hr"
                )
            ]
        )
    )
)

# Partial mask salary for non-managers
acm.add_masking_rule(
    "employee_data",
    AttributeMaskingRule(
        field_path="salary",
        mask_type="partial",  # Shows first/last 2 chars
        condition=AttributeCondition(
            attribute_path="user.attributes.is_manager",
            operator=AttributeOperator.NOT_EQUALS,
            value=True
        )
    )
)

```

### User Context with Attributes

```python
from kailash.access_control import UserContext

# Create user with attributes
user = UserContext(
    user_id="emp123",
    tenant_id="acme",
    email="john.doe@acme.com",
    roles=["engineer", "team_lead"],
    attributes={
        "department": "engineering.backend.api",
        "security_clearance": "secret",
        "region": "us-west",
        "is_manager": True,
        "team_size": 8,
        "years_experience": 5
    }
)

```

## Migration Framework

Django-inspired async database migrations.

### Creating Migrations

```python
from kailash.utils.migrations import Migration

class CreateUserProfileTable(Migration):
    id = "001_create_user_profile"
    description = "Create user profile table"
    dependencies = []

    async def forward(self, connection):
        await connection.execute("""
            CREATE TABLE user_profiles (
                id SERIAL PRIMARY KEY,
                user_id INTEGER UNIQUE NOT NULL,
                bio TEXT,
                avatar_url VARCHAR(500),
                preferences JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await connection.execute("""
            CREATE INDEX idx_profile_user ON user_profiles(user_id)
        """)

    async def backward(self, connection):
        await connection.execute("DROP TABLE IF EXISTS user_profiles CASCADE")

```

### Running Migrations

```python
from kailash.utils.migrations import MigrationRunner

# Create runner
runner = MigrationRunner(
    db_config={
        "type": "postgresql",
        "host": "localhost",
        "database": "myapp",
        "user": "dbuser",
        "password": "dbpass"
    }
)

# Initialize migration tracking
await runner.initialize()

# Register migrations
runner.register_migration(CreateUserProfileTable)

# Create and execute plan
plan = await runner.create_plan()
history = await runner.execute_plan(plan, user="admin")

```

### Migration Generator

```python
from kailash.utils.migrations import MigrationGenerator

# Create generator
generator = MigrationGenerator("./migrations")

# Generate new migration
migration_file = generator.create_migration(
    name="add_user_settings",
    description="Add settings table for user preferences",
    migration_type="schema",
    dependencies=["001_create_user_profile"]
)

```

## Complete Example: Secure Data Pipeline

```python
import asyncio
from kailash.workflow import Workflow
from kailash.nodes.data import AsyncSQLDatabaseNode, AsyncPostgreSQLVectorNode
from kailash.access_control import UserContext
from kailash.access_control import AccessControlManager
from kailash.runtime.access_controlled import AccessControlledRuntime

async def secure_data_pipeline():
    # Setup access control
    acm = AccessControlManager(strategy="abac")

    # Add department-based access
    acm.add_rule(PermissionRule(
        id="finance_data",
        resource_type="node",
        resource_id="financial_query",
        permission=NodePermission.EXECUTE,
        effect=PermissionEffect.ALLOW,
        conditions={
            "type": "department_hierarchy",
            "value": {
                "department": "finance",
                "include_children": True
            }
        }
    ))

    # Create workflow
    workflow = WorkflowBuilder()

    # Add async database query
    workflow.add_node("AsyncSQLDatabaseNode", "financial_query", {
        "query": """
            SELECT department,
                SUM(amount) as total_expenses,
                AVG(amount) as avg_expense,
                COUNT(*) as transaction_count
            FROM expenses
            WHERE date >= :start_date
            GROUP BY department
        """,
        "params": {"start_date": "2024-01-01"},
        "pool_size": 20
    })

    # Add vector search for similar transactions
    workflow.add_node("AsyncPostgreSQLVectorNode", "similar_transactions", {
        "query": "SELECT * FROM transactions WHERE vector_similarity > 0.8"
    })

    # Create user
    user = UserContext(
        user_id="fin001",
        tenant_id="acme",
        email="finance.analyst@acme.com",
        attributes={
            "department": "finance.analysis",
            "clearance": "confidential"
        }
    )

    # Execute with access control
    runtime = AccessControlledRuntime(
        access_control_manager=acm,
        user_context=user
    )

    results = await runtime.execute_workflow(workflow)
    return results

# Run the pipeline
results = asyncio.run(secure_data_pipeline())

```

## Performance Considerations

### Connection Pooling Best Practices

1. **Pool Sizing**: Start with `min_size=5, max_size=20` and adjust based on load
2. **Timeout Configuration**: Set appropriate timeouts for your queries
3. **Health Checks**: Enable automatic health checks for production
4. **Monitoring**: Regularly check pool metrics to optimize configuration

### Vector Search Optimization

1. **Index Selection**:
   - HNSW: Best for high recall requirements
   - IVFFlat: Better for memory-constrained environments

2. **Distance Metrics**:
   - Cosine: Normalized embeddings (most common)
   - L2: Euclidean distance for absolute positioning
   - IP: Inner product for maximum similarity

3. **Query Optimization**:
   - Use metadata filters to reduce search space
   - Adjust `ef_search` for accuracy vs speed tradeoff
   - Consider partitioning large tables

### ABAC Performance

1. **Rule Ordering**: Place most specific rules first with higher priority
2. **Condition Complexity**: Avoid deeply nested conditions when possible
3. **Caching**: The ACM caches decisions automatically
4. **Attribute Indexing**: Index frequently queried attributes in the database

## Error Handling

```python
from kailash.sdk_exceptions import NodeExecutionError

try:
    result = await node.execute_async()
except NodeExecutionError as e:
    # Handle database errors
    if "connection" in str(e):
        # Retry or use fallback
        pass
    elif "timeout" in str(e):
        # Query took too long
        pass

```

## Security Considerations

1. **Connection Strings**: Use environment variables, never hardcode
2. **SQL Injection**: Always use parameterized queries
3. **Access Control**: Implement ABAC rules for sensitive data
4. **Data Masking**: Apply masking rules for PII/sensitive fields
5. **Audit Logging**: The ACM logs all access decisions

## Migration to Async

If you have existing synchronous database nodes:

```python
# Before (synchronous)
from kailash.nodes.data import SQLDatabaseNode
sync_node = SQLDatabaseNode(
    name="old_query",
    connection_string="postgresql://localhost/db",
    query="SELECT * FROM users"
)

# After (asynchronous)
from kailash.nodes.data import AsyncSQLDatabaseNode
async_node = AsyncSQLDatabaseNode(
    name="new_query",
    database_type="postgresql",
    connection_string="postgresql://localhost/db",
    query="SELECT * FROM users",
    pool_size=10
)

```

The async version provides:
- Non-blocking execution
- Connection pooling
- Better resource utilization
- Higher concurrency support

## Next Steps

- Explore the [Admin Tool Framework](../admin_tools.md) built on this infrastructure
- See [Performance Tuning Guide](../performance.md) for optimization tips
- Check [Security Best Practices](../security.md) for production deployments
