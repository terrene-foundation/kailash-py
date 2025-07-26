# Database Integration Guide

*Comprehensive database management with connection pooling, query routing, and enterprise features*

## Overview

The Kailash SDK provides robust database integration capabilities supporting SQL databases (PostgreSQL, MySQL, SQLite), vector databases (pgvector, Pinecone, Weaviate), and advanced features like connection pooling, query routing, transaction management, and data masking. This guide covers production-ready database patterns for enterprise applications.

## Prerequisites

- Completed [MCP Node Development Guide](32-mcp-node-development-guide.md)
- Understanding of database concepts and SQL
- Familiarity with async programming patterns

## Core Database Features

### SQLDatabaseNode

Production-ready SQL database integration with connection pooling.

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.data.sql import SQLDatabaseNode
from kailash.nodes.data.async_connection import AsyncConnectionManager

# Initialize SQL database node
sql_node = SQLDatabaseNode(
    name="main_database",

    # Database configuration
    connection_string="postgresql://user:password@localhost:5432/production_db",

    # Connection pool settings
    pool_size=20,
    max_overflow=30,
    pool_timeout=30,
    pool_recycle=3600,  # Recycle connections every hour

    # Query configuration
    query_timeout=30,
    enable_query_logging=True,

    # Security settings
    enable_access_control=True,
    enable_data_masking=True,

    # Performance settings
    enable_query_cache=True,
    cache_ttl=300,

    # Connection health
    health_check_query="SELECT 1",
    health_check_interval=60
)

# Basic database operations
async def basic_database_operations():
    """Demonstrate basic database operations."""

    # Simple query
    users = await sql_node.run(
        query="SELECT id, name, email FROM users WHERE active = %(active)s",
        parameters={"active": True},
        result_format="dict"
    )

    print(f"Found {len(users['data'])} active users")

    # Insert operation with transaction
    new_user_result = await sql_node.run(
        query="""
        INSERT INTO users (name, email, department, created_at)
        VALUES (%(name)s, %(email)s, %(department)s, NOW())
        RETURNING id, created_at
        """,
        parameters={
            "name": "John Doe",
            "email": "john.doe@company.com",
            "department": "Engineering"
        },
        result_format="dict",
        use_transaction=True
    )

    user_id = new_user_result['data'][0]['id']
    print(f"Created user with ID: {user_id}")

    # Complex analytical query
    analytics = await sql_node.run(
        query="""
        SELECT
            department,
            COUNT(*) as employee_count,
            AVG(salary) as avg_salary,
            MAX(created_at) as last_hire_date
        FROM users
        WHERE active = true
        GROUP BY department
        ORDER BY employee_count DESC
        """,
        result_format="dict",
        cache_key="department_analytics",
        cache_ttl=600  # Cache for 10 minutes
    )

    return {
        "users": users['data'],
        "new_user_id": user_id,
        "department_analytics": analytics['data']
    }

# Execute operations
result = await basic_database_operations()
```

### AsyncSQLDatabaseNode

High-performance async database operations for concurrent workloads.

```python
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

# Initialize async SQL node
async_sql_node = AsyncSQLDatabaseNode(
    name="async_database",

    # Database configuration
    database_type="postgresql",
    host="localhost",
    port=5432,
    database="production_db",
    username="app_user",
    password="secure_password",

    # Async connection pool
    pool_size=50,
    max_connections=100,
    pool_timeout=10.0,
    pool_recycle=7200,  # 2 hours

    # Retry configuration
    retry_attempts=3,
    retry_delay=1.0,
    retry_backoff_factor=2.0,

    # Performance settings
    fetch_size=1000,
    enable_prepared_statements=True,
    statement_cache_size=100,

    # Monitoring
    enable_query_metrics=True,
    slow_query_threshold=1.0  # Log queries > 1 second
)

# Advanced async operations
async def advanced_async_operations():
    """Demonstrate advanced async database operations."""

    # Batch insert with transaction
    user_data = [
        {"name": "Alice Smith", "email": "alice@company.com", "department": "Marketing"},
        {"name": "Bob Johnson", "email": "bob@company.com", "department": "Sales"},
        {"name": "Carol Davis", "email": "carol@company.com", "department": "Engineering"}
    ]

    batch_insert_result = await async_sql_node.run(
        query="""
        INSERT INTO users (name, email, department, created_at)
        VALUES (%(name)s, %(email)s, %(department)s, NOW())
        RETURNING id, name
        """,
        parameters=user_data,  # Batch parameters
        fetch_mode="all",
        use_transaction=True,
        isolation_level="READ_COMMITTED"
    )

    print(f"Batch inserted {len(batch_insert_result['data'])} users")

    # Streaming large result set
    large_dataset_results = []

    async for batch in async_sql_node.stream_query(
        query="""
        SELECT u.id, u.name, u.email, u.department, u.created_at,
               p.project_name, p.status, p.deadline
        FROM users u
        LEFT JOIN user_projects up ON u.id = up.user_id
        LEFT JOIN projects p ON up.project_id = p.id
        WHERE u.active = true
        ORDER BY u.created_at DESC
        """,
        batch_size=500,
        stream_timeout=30
    ):
        large_dataset_results.extend(batch)
        print(f"Processed batch of {len(batch)} records")

    print(f"Streamed total of {len(large_dataset_results)} records")

    # Complex transaction with multiple operations
    async with async_sql_node.transaction() as tx:
        # Update user status
        await tx.execute(
            "UPDATE users SET last_login = NOW() WHERE id = %(user_id)s",
            {"user_id": 123}
        )

        # Log activity
        await tx.execute(
            "INSERT INTO user_activity (user_id, activity_type, timestamp) VALUES (%(user_id)s, %(activity)s, NOW())",
            {"user_id": 123, "activity": "login"}
        )

        # Update session
        session_result = await tx.fetch_one(
            "INSERT INTO user_sessions (user_id, session_token, expires_at) VALUES (%(user_id)s, %(token)s, %(expires)s) RETURNING session_id",
            {"user_id": 123, "token": "abc123", "expires": "2024-12-31 23:59:59"}
        )

        session_id = session_result['session_id']

    return {
        "batch_inserted": len(batch_insert_result['data']),
        "streamed_records": len(large_dataset_results),
        "session_id": session_id
    }

# Execute async operations
async_result = await advanced_async_operations()
```

## Vector Database Integration

Advanced vector search capabilities for AI and ML applications.

### AsyncPostgreSQLVectorNode

```python
from kailash.nodes.data.async_vector import AsyncPostgreSQLVectorNode
import numpy as np

# Initialize vector database node
vector_node = AsyncPostgreSQLVectorNode(
    name="vector_database",

    # PostgreSQL connection
    connection_string="postgresql://user:password@localhost:5432/vector_db",

    # Vector configuration
    vector_dimension=1536,  # OpenAI embedding dimension
    distance_metric="cosine",  # "l2", "cosine", "inner_product"
    index_type="hnsw",  # "hnsw", "ivfflat"

    # Index parameters
    hnsw_m=16,           # Number of bi-directional links
    hnsw_ef_construction=64,  # Size of dynamic candidate list

    # Performance settings
    batch_size=1000,
    enable_parallel_indexing=True,

    # Schema configuration
    table_name="document_embeddings",
    vector_column="embedding",
    metadata_columns=["document_id", "title", "content", "tags", "created_at"]
)

# Vector operations
async def vector_database_operations():
    """Demonstrate vector database operations."""

    # Generate sample embeddings (replace with actual embeddings)
    def generate_embedding(text: str) -> list:
        # In production, use actual embedding model
        np.random.seed(hash(text) % 2**32)
        return np.random.random(1536).tolist()

    # Insert embeddings with metadata
    documents = [
        {
            "document_id": "doc_001",
            "title": "Machine Learning Fundamentals",
            "content": "An introduction to machine learning concepts and algorithms.",
            "tags": ["ml", "fundamentals", "algorithms"],
            "embedding": generate_embedding("Machine Learning Fundamentals")
        },
        {
            "document_id": "doc_002",
            "title": "Deep Learning with Neural Networks",
            "content": "Advanced deep learning techniques using neural networks.",
            "tags": ["dl", "neural-networks", "advanced"],
            "embedding": generate_embedding("Deep Learning with Neural Networks")
        },
        {
            "document_id": "doc_003",
            "title": "Natural Language Processing",
            "content": "Processing and understanding human language with computers.",
            "tags": ["nlp", "language", "processing"],
            "embedding": generate_embedding("Natural Language Processing")
        }
    ]

    # Batch insert embeddings
    insert_result = await vector_node.run(
        operation="insert_batch",
        data=documents,
        on_conflict="update"  # Update if document_id already exists
    )

    print(f"Inserted {insert_result['inserted_count']} embeddings")

    # Vector similarity search
    query_embedding = generate_embedding("machine learning algorithms")

    search_results = await vector_node.run(
        operation="similarity_search",
        query_vector=query_embedding,
        limit=5,
        distance_threshold=0.8,

        # Metadata filtering
        filters={
            "tags": {"contains": "ml"},
            "created_at": {"gte": "2024-01-01"}
        },

        # Return metadata
        include_metadata=True,
        include_distances=True
    )

    print(f"Found {len(search_results['results'])} similar documents")

    # Hybrid search (vector + text)
    hybrid_results = await vector_node.run(
        operation="hybrid_search",
        query_vector=query_embedding,
        text_query="neural networks",
        vector_weight=0.7,  # 70% vector similarity, 30% text match
        text_weight=0.3,
        limit=10,

        # Advanced filtering
        filters={
            "tags": {"intersects": ["ml", "dl", "algorithms"]},
            "title": {"ilike": "%learning%"}
        }
    )

    print(f"Hybrid search found {len(hybrid_results['results'])} documents")

    # Vector clustering analysis
    cluster_analysis = await vector_node.run(
        operation="cluster_analysis",
        num_clusters=3,
        clustering_method="kmeans",
        include_cluster_stats=True
    )

    return {
        "inserted_documents": insert_result['inserted_count'],
        "similarity_results": search_results['results'][:3],  # Top 3
        "hybrid_results": hybrid_results['results'][:3],
        "cluster_stats": cluster_analysis['cluster_stats']
    }

# Execute vector operations
vector_result = await vector_database_operations()
```

### VectorDatabaseNode (Multi-Provider)

```python
from kailash.nodes.data.vector_db import VectorDatabaseNode

# Pinecone configuration
pinecone_node = VectorDatabaseNode(
    name="pinecone_vectors",
    provider="pinecone",

    # Pinecone configuration
    api_key="your-pinecone-api-key",
    environment="us-west1-gcp",
    index_name="document-embeddings",

    # Vector configuration
    dimension=1536,
    metric="cosine",
    pod_type="p1.x1",

    # Metadata configuration
    metadata_config={
        "indexed_fields": ["category", "timestamp", "author"],
        "non_indexed_fields": ["content", "raw_text"]
    }
)

# Weaviate configuration
weaviate_node = VectorDatabaseNode(
    name="weaviate_vectors",
    provider="weaviate",

    # Weaviate configuration
    url="http://localhost:8080",
    api_key="your-weaviate-api-key",

    # Schema configuration
    class_name="Document",
    properties=[
        {"name": "title", "dataType": ["text"]},
        {"name": "content", "dataType": ["text"]},
        {"name": "category", "dataType": ["string"]},
        {"name": "timestamp", "dataType": ["date"]}
    ],

    # Vector configuration
    vectorizer="text2vec-openai",
    vector_index_type="hnsw"
)

# Multi-provider vector operations
async def multi_provider_vector_operations():
    """Demonstrate operations across multiple vector database providers."""

    # Insert to Pinecone
    pinecone_result = await pinecone_node.run(
        operation="upsert",
        vectors=[
            {
                "id": "doc_001",
                "values": generate_embedding("AI and Machine Learning"),
                "metadata": {
                    "title": "AI and Machine Learning",
                    "category": "technology",
                    "author": "Dr. Smith"
                }
            }
        ],
        namespace="documents"
    )

    # Insert to Weaviate
    weaviate_result = await weaviate_node.run(
        operation="create",
        data={
            "title": "AI and Machine Learning",
            "content": "Comprehensive guide to AI and ML concepts",
            "category": "technology",
            "timestamp": "2024-01-15T10:00:00Z"
        },
        vector=generate_embedding("AI and Machine Learning"),
        class_name="Document"
    )

    # Cross-provider search comparison
    query_vector = generate_embedding("machine learning algorithms")

    # Search Pinecone
    pinecone_search = await pinecone_node.run(
        operation="query",
        vector=query_vector,
        top_k=5,
        namespace="documents",
        filter={"category": {"$eq": "technology"}},
        include_metadata=True
    )

    # Search Weaviate
    weaviate_search = await weaviate_node.run(
        operation="near_vector",
        vector=query_vector,
        limit=5,
        where={
            "path": ["category"],
            "operator": "Equal",
            "valueText": "technology"
        },
        class_name="Document"
    )

    return {
        "pinecone_inserted": pinecone_result['upserted_count'],
        "weaviate_inserted": weaviate_result['id'],
        "pinecone_results": len(pinecone_search['matches']),
        "weaviate_results": len(weaviate_search['data'])
    }
```

## Connection Management and Pooling

### AsyncConnectionManager

```python
from kailash.nodes.data.async_connection import AsyncConnectionManager
from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool

# Initialize connection manager
connection_manager = AsyncConnectionManager(
    # Multi-tenant configuration
    enable_multi_tenant=True,
    tenant_isolation=True,

    # Health monitoring
    health_check_interval=30,
    health_check_timeout=5,
    max_health_failures=3,

    # Connection encryption
    enable_encryption=True,
    ssl_context="require",

    # Monitoring
    enable_metrics=True,
    metrics_collection_interval=10
)

# Register multiple database connections
await connection_manager.register_connection(
    name="primary_postgres",
    connection_string="postgresql://user:password@db1:5432/app_db",
    pool_config={
        "min_size": 10,
        "max_size": 50,
        "command_timeout": 30
    }
)

await connection_manager.register_connection(
    name="read_replica",
    connection_string="postgresql://user:password@db2:5432/app_db",
    pool_config={
        "min_size": 5,
        "max_size": 25,
        "command_timeout": 30
    },
    connection_type="read_only"
)

# Use connection manager in workflows
async def managed_database_workflow():
    """Demonstrate connection management in workflows."""

    # Get connection for tenant
    async with connection_manager.get_connection(
        name="primary_postgres",
        tenant_id="tenant_123"
    ) as conn:

        # Execute query with managed connection
        result = await conn.fetch(
            "SELECT * FROM tenant_data WHERE tenant_id = $1",
            "tenant_123"
        )

        return {"records": len(result)}

# Monitor connection health
health_status = await connection_manager.get_health_status()
print(f"Connection health: {health_status}")
```

### WorkflowConnectionPool

```python
# Advanced connection pool for workflow-scoped connections
workflow_pool = WorkflowConnectionPool(
    name="workflow_connection_pool",

    # Database configuration
    database_type="postgresql",
    host="localhost",
    port=5432,
    database="workflow_db",
    user="workflow_user",
    password="secure_password",

    # Pool configuration
    min_connections=5,
    max_connections=25,
    health_threshold=75,  # Health score threshold

    # Pattern-based pre-warming
    pre_warm_enabled=True,
    pre_warm_patterns=[
        {"hour_range": (8, 18), "target_connections": 15},  # Business hours
        {"hour_range": (18, 8), "target_connections": 8}    # Off hours
    ],

    # Adaptive sizing
    adaptive_sizing_enabled=True,

    # Query routing
    enable_query_routing=True,

    # Circuit breaker
    circuit_breaker_failure_threshold=5,
    circuit_breaker_recovery_timeout=60,

    # Monitoring
    enable_monitoring=True,
    metrics_retention_minutes=60
)

# Use in workflow
workflow_pool_result = await workflow_pool.run(
    operation="execute",
    query="SELECT COUNT(*) as total_orders, AVG(amount) as avg_amount FROM orders WHERE created_at >= NOW() - INTERVAL '24 hours'",
    fetch_mode="one"
)

print(f"Pool query result: {workflow_pool_result}")

# Get pool metrics
pool_metrics = await workflow_pool.get_metrics()
print(f"Pool health: {pool_metrics['health']['success_rate']:.2%}")
```

## Query Routing and Optimization

### QueryRouter

```python
from kailash.nodes.data.query_router import QueryRouter

# Initialize intelligent query router
query_router = QueryRouter(
    name="intelligent_query_router",

    # Connection definitions
    connections={
        "primary_write": {
            "connection_string": "postgresql://user:pass@primary:5432/db",
            "capabilities": ["READ_SIMPLE", "READ_COMPLEX", "WRITE_SIMPLE", "WRITE_BULK", "DDL"],
            "max_concurrent": 50,
            "priority": 100
        },
        "read_replica_1": {
            "connection_string": "postgresql://user:pass@replica1:5432/db",
            "capabilities": ["READ_SIMPLE", "READ_COMPLEX"],
            "max_concurrent": 30,
            "priority": 80
        },
        "read_replica_2": {
            "connection_string": "postgresql://user:pass@replica2:5432/db",
            "capabilities": ["READ_SIMPLE", "READ_COMPLEX"],
            "max_concurrent": 30,
            "priority": 80
        },
        "analytics_db": {
            "connection_string": "postgresql://user:pass@analytics:5432/db",
            "capabilities": ["READ_COMPLEX"],
            "max_concurrent": 20,
            "priority": 60
        }
    },

    # Routing configuration
    enable_load_balancing=True,
    enable_query_caching=True,
    cache_ttl=300,

    # Performance monitoring
    enable_performance_tracking=True,
    health_check_interval=30
)

# Intelligent query routing
async def intelligent_query_routing():
    """Demonstrate intelligent query routing."""

    # Simple read query -> routed to read replica
    user_query = await query_router.run(
        query="SELECT id, name, email FROM users WHERE id = %(user_id)s",
        parameters={"user_id": 12345},
        query_type="READ_SIMPLE"  # Auto-detected if not specified
    )

    # Complex analytical query -> routed to analytics DB
    analytics_query = await query_router.run(
        query="""
        SELECT
            DATE_TRUNC('month', created_at) as month,
            COUNT(*) as order_count,
            SUM(amount) as total_revenue,
            AVG(amount) as avg_order_value,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY amount) as median_amount
        FROM orders
        WHERE created_at >= NOW() - INTERVAL '12 months'
        GROUP BY month
        ORDER BY month
        """,
        query_type="READ_COMPLEX"
    )

    # Write operation -> routed to primary
    write_query = await query_router.run(
        query="INSERT INTO user_activities (user_id, activity_type, timestamp) VALUES (%(user_id)s, %(activity)s, NOW())",
        parameters={"user_id": 12345, "activity": "login"},
        query_type="WRITE_SIMPLE"
    )

    # Bulk write -> routed to primary with optimization
    bulk_data = [
        {"product_id": i, "category": f"category_{i%10}", "price": 10.0 + i}
        for i in range(1000)
    ]

    bulk_write = await query_router.run(
        query="INSERT INTO products (product_id, category, price) VALUES (%(product_id)s, %(category)s, %(price)s)",
        parameters=bulk_data,
        query_type="WRITE_BULK",
        batch_size=100
    )

    # Get routing statistics
    routing_stats = await query_router.get_routing_stats()

    return {
        "user_data": user_query['data'],
        "analytics_data": len(analytics_query['data']),
        "write_success": write_query['success'],
        "bulk_inserted": bulk_write['rows_affected'],
        "routing_stats": routing_stats
    }

# Execute routing demo
routing_result = await intelligent_query_routing()
```

## Database Schema Management

### AdminSchemaManager

```python
from kailash.nodes.admin.schema_manager import AdminSchemaManager

# Initialize schema manager
schema_manager = AdminSchemaManager(
    name="production_schema_manager",

    # Database connection
    connection_string="postgresql://admin:password@localhost:5432/production_db",

    # Schema configuration
    schema_version_table="schema_versions",
    migration_path="/app/migrations",

    # Validation settings
    enable_schema_validation=True,
    validate_foreign_keys=True,
    validate_indexes=True,

    # Backup settings
    enable_schema_backup=True,
    backup_path="/backups/schema",

    # Safety settings
    require_confirmation=True,
    dry_run_mode=False
)

# Schema operations
async def schema_management_operations():
    """Demonstrate schema management operations."""

    # Create complete schema
    schema_creation = await schema_manager.run(
        operation="create_schema",
        schema_definition={
            "tables": {
                "users": {
                    "columns": {
                        "id": {"type": "SERIAL", "primary_key": True},
                        "email": {"type": "VARCHAR(255)", "unique": True, "not_null": True},
                        "name": {"type": "VARCHAR(100)", "not_null": True},
                        "department": {"type": "VARCHAR(50)"},
                        "created_at": {"type": "TIMESTAMP", "default": "NOW()"},
                        "updated_at": {"type": "TIMESTAMP", "default": "NOW()"}
                    },
                    "indexes": [
                        {"name": "idx_users_email", "columns": ["email"], "unique": True},
                        {"name": "idx_users_department", "columns": ["department"]},
                        {"name": "idx_users_created_at", "columns": ["created_at"]}
                    ]
                },
                "projects": {
                    "columns": {
                        "id": {"type": "SERIAL", "primary_key": True},
                        "name": {"type": "VARCHAR(200)", "not_null": True},
                        "description": {"type": "TEXT"},
                        "owner_id": {"type": "INTEGER", "not_null": True},
                        "status": {"type": "VARCHAR(20)", "default": "'active'"},
                        "created_at": {"type": "TIMESTAMP", "default": "NOW()"}
                    },
                    "foreign_keys": [
                        {
                            "columns": ["owner_id"],
                            "references": {"table": "users", "columns": ["id"]},
                            "on_delete": "CASCADE"
                        }
                    ],
                    "indexes": [
                        {"name": "idx_projects_owner", "columns": ["owner_id"]},
                        {"name": "idx_projects_status", "columns": ["status"]}
                    ]
                }
            },
            "views": {
                "user_project_summary": {
                    "definition": """
                    SELECT
                        u.id as user_id,
                        u.name as user_name,
                        u.department,
                        COUNT(p.id) as project_count,
                        ARRAY_AGG(p.name) as project_names
                    FROM users u
                    LEFT JOIN projects p ON u.id = p.owner_id
                    GROUP BY u.id, u.name, u.department
                    """
                }
            }
        },
        version="1.0.0",
        backup_existing=True
    )

    # Validate schema health
    validation_result = await schema_manager.run(
        operation="validate_schema",
        validation_checks=[
            "table_structure",
            "foreign_key_constraints",
            "index_integrity",
            "data_consistency"
        ],
        include_performance_analysis=True
    )

    # Migration planning
    migration_plan = await schema_manager.run(
        operation="plan_migration",
        target_schema_version="2.0.0",
        migration_files=[
            "001_add_user_preferences_table.sql",
            "002_add_project_tags_column.sql",
            "003_create_activity_log_table.sql"
        ],
        analyze_dependencies=True,
        estimate_downtime=True
    )

    # Execute migration (with safety checks)
    if validation_result['health_score'] > 0.95:
        migration_result = await schema_manager.run(
            operation="execute_migration",
            migration_plan=migration_plan,
            backup_before_migration=True,
            rollback_on_failure=True,
            max_downtime_minutes=5
        )

        return {
            "schema_created": schema_creation['success'],
            "validation_score": validation_result['health_score'],
            "migration_executed": migration_result['success'],
            "migration_time": migration_result['execution_time_seconds']
        }
    else:
        return {
            "schema_created": schema_creation['success'],
            "validation_score": validation_result['health_score'],
            "migration_skipped": "Health score too low",
            "validation_issues": validation_result['issues']
        }

# Execute schema management
schema_result = await schema_management_operations()
```

## Production Database Patterns

### Complete Database Integration

```python
async def create_production_database_system():
    """Create a complete production database system."""

    # Initialize all database components

    # 1. Connection management
    connection_manager = AsyncConnectionManager(
        enable_multi_tenant=True,
        health_check_interval=30,
        enable_encryption=True
    )

    # Register connections
    await connection_manager.register_connection(
        name="primary_db",
        connection_string="postgresql://user:pass@primary:5432/prod_db",
        pool_config={"min_size": 20, "max_size": 100}
    )

    await connection_manager.register_connection(
        name="read_replica",
        connection_string="postgresql://user:pass@replica:5432/prod_db",
        pool_config={"min_size": 10, "max_size": 50},
        connection_type="read_only"
    )

    # 2. Query routing
    query_router = QueryRouter(
        name="production_router",
        connections={
            "primary": {"capabilities": ["READ_SIMPLE", "READ_COMPLEX", "WRITE_SIMPLE", "WRITE_BULK", "DDL"]},
            "replica": {"capabilities": ["READ_SIMPLE", "READ_COMPLEX"]}
        },
        enable_load_balancing=True,
        enable_query_caching=True
    )

    # 3. Vector database for AI features
    vector_db = AsyncPostgreSQLVectorNode(
        name="ai_vectors",
        connection_string="postgresql://user:pass@vector:5432/vector_db",
        vector_dimension=1536,
        distance_metric="cosine"
    )

    # 4. Schema management
    schema_manager = AdminSchemaManager(
        name="schema_manager",
        connection_string="postgresql://admin:pass@primary:5432/prod_db"
    )

    # 5. Workflow connection pool
    workflow_pool = WorkflowConnectionPool(
        name="workflow_pool",
        database_type="postgresql",
        host="primary",
        database="prod_db",
        min_connections=10,
        max_connections=50,
        enable_monitoring=True
    )

    return {
        "connection_manager": connection_manager,
        "query_router": query_router,
        "vector_db": vector_db,
        "schema_manager": schema_manager,
        "workflow_pool": workflow_pool
    }

# Production workflow integration
async def production_database_workflow():
    """Demonstrate production database workflow."""

    db_system = await create_production_database_system()

    # Multi-step database workflow
    workflow = WorkflowBuilder()

    # Data ingestion
    workflow.add_node("AsyncSQLDatabaseNode", "data_ingester", {
        "connection_name": "primary_db",
        "query": "INSERT INTO raw_data (source, data, created_at) VALUES (%(source)s, %(data)s, NOW()) RETURNING id",
        "use_transaction": True
    })

    # Data processing
    workflow.add_node("PythonCodeNode", "data_processor", {
        "code": """
        import json

        # Process the raw data
        processed_data = []
        for record in raw_data_result['data']:
            data = json.loads(record['data'])
            processed_record = {
                'id': record['id'],
                'processed_data': transform_data(data),
                'quality_score': calculate_quality(data)
            }
            processed_data.append(processed_record)

        result = {'processed_records': processed_data}
        """
    })

    # Vector embedding generation
    workflow.add_node("AsyncPostgreSQLVectorNode", "embedding_generator", {
        "operation": "insert_batch",
        "table_name": "document_embeddings"
    })

    # Analytics update
    workflow.add_node("QueryRouter", "analytics_updater", {
        "query": """
        INSERT INTO analytics_summary (date, total_records, avg_quality_score, created_at)
        SELECT CURRENT_DATE, COUNT(*), AVG(quality_score), NOW()
        FROM processed_data
        WHERE created_at >= CURRENT_DATE
        ON CONFLICT (date) DO UPDATE SET
            total_records = EXCLUDED.total_records,
            avg_quality_score = EXCLUDED.avg_quality_score
        """,
        "query_type": "WRITE_SIMPLE"
    })

    # Connect workflow
    workflow.add_connection("data_ingester", "data_processor", "result", "raw_data_result")
    workflow.add_connection("data_processor", "embedding_generator", "result.processed_records", "data")
    workflow.add_connection("data_processor", "analytics_updater", "result", "processed_data")

    # Execute workflow
    workflow_result = await runtime.execute(workflow.build(), {
        "data_ingester": {
            "source": "api_endpoint",
            "data": json.dumps({"user_actions": ["login", "view_page", "logout"]})
        }
    })

    return workflow_result

# Execute production workflow
production_result = await production_database_workflow()
```

## Best Practices

### 1. Connection Management

```python
# Optimal connection configuration
def get_production_connection_config():
    """Get production-optimized connection configuration."""
    return {
        "pool_size": 20,           # Base pool size
        "max_overflow": 30,        # Additional connections under load
        "pool_timeout": 30,        # Wait time for connection
        "pool_recycle": 3600,      # Recycle connections hourly
        "pool_pre_ping": True,     # Validate connections before use
        "echo": False,             # Disable query logging in production
        "connect_args": {
            "sslmode": "require",
            "application_name": "kailash_app",
            "connect_timeout": 10
        }
    }
```

### 2. Query Optimization

```python
# Query optimization patterns
async def optimized_query_patterns():
    """Demonstrate query optimization patterns."""

    # Use prepared statements for repeated queries
    prepared_query = await sql_node.prepare_statement(
        "SELECT * FROM users WHERE department = $1 AND active = $2"
    )

    # Batch operations for better performance
    batch_results = await sql_node.execute_batch(
        prepared_query,
        [("Engineering", True), ("Marketing", True), ("Sales", True)]
    )

    # Use appropriate fetch modes
    large_result = await sql_node.fetch_iterator(
        "SELECT * FROM large_table ORDER BY created_at",
        chunk_size=1000
    )

    # Connection-specific optimizations
    async with sql_node.connection() as conn:
        # Set session-specific optimizations
        await conn.execute("SET work_mem = '256MB'")
        await conn.execute("SET random_page_cost = 1.1")

        # Execute optimization-sensitive query
        result = await conn.fetch("SELECT * FROM complex_analytical_view")

    return {"optimization": "complete"}
```

### 3. Security and Access Control

```python
# Database security patterns
async def database_security_patterns():
    """Implement database security best practices."""

    # Row-level security
    secured_sql_node = SQLDatabaseNode(
        name="secured_database",
        connection_string="postgresql://app_user:password@localhost:5432/secure_db",

        # Enable access control
        enable_access_control=True,
        access_control_config={
            "row_level_security": True,
            "column_masking": True,
            "audit_logging": True
        },

        # Data masking rules
        data_masking_rules={
            "users.email": {"mask_type": "email", "visible_chars": 3},
            "users.phone": {"mask_type": "phone", "visible_chars": 4},
            "financial.account_number": {"mask_type": "full", "replacement": "***"}
        }
    )

    # Query with user context
    user_context = {
        "user_id": "user_123",
        "role": "analyst",
        "department": "finance",
        "clearance_level": 3
    }

    secured_result = await secured_sql_node.run(
        query="SELECT id, name, email, salary FROM users WHERE department = %(dept)s",
        parameters={"dept": "finance"},
        user_context=user_context
    )

    return {"security_applied": True, "masked_fields": ["email", "salary"]}
```

## Related Guides

**Prerequisites:**
- [MCP Node Development Guide](32-mcp-node-development-guide.md) - Custom MCP nodes
- [Cyclic Workflows Guide](31-cyclic-workflows-guide.md) - Workflow cycles

**Next Steps:**
- [Monitoring and Observability Guide](34-monitoring-observability-guide.md) - Production monitoring
- [Compliance and Governance Guide](35-compliance-governance-guide.md) - Compliance patterns

---

**Master enterprise database integration with advanced connection management and intelligent query routing!**
