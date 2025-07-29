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
from kailash.runtime.local import LocalRuntime

# Create workflow with SQL database node
workflow = WorkflowBuilder()
workflow.add_node("SQLDatabaseNode", "main_database", {
    # Database configuration
    "connection_string": "postgresql://user:password@localhost:5432/production_db",

    # Connection pool settings
    "pool_size": 20,
    "max_overflow": 30,
    "pool_timeout": 30,
    "pool_recycle": 3600,  # Recycle connections every hour

    # Query configuration
    "query_timeout": 30,
    "enable_query_logging": True,

    # Security settings
    "enable_access_control": True,
    "enable_data_masking": True,

    # Performance settings
    "enable_query_cache": True,
    "cache_ttl": 300,

    # Connection health
    "health_check_query": "SELECT 1",
    "health_check_interval": 60
})

# Basic database operations
async def basic_database_operations():
    """Demonstrate basic database operations."""

    runtime = LocalRuntime()

    # Simple query
    query_workflow = WorkflowBuilder()
    query_workflow.add_node("SQLDatabaseNode", "query_users", {
        "connection_string": "postgresql://user:password@localhost:5432/production_db",
        "query": "SELECT id, name, email FROM users WHERE active = :active",
        "parameters": {"active": True},
        "result_format": "dict"
    })

    results, _ = await runtime.execute_async(query_workflow.build())
    users = results["query_users"]["result"]
    print(f"Found {len(users['data'])} active users")

    # Insert operation with transaction
    insert_workflow = WorkflowBuilder()
    insert_workflow.add_node("SQLDatabaseNode", "insert_user", {
        "connection_string": "postgresql://user:password@localhost:5432/production_db",
        "query": """
        INSERT INTO users (name, email, department, created_at)
        VALUES (:name, :email, :department, NOW())
        RETURNING id, created_at
        """,
        "parameters": {
            "name": "John Doe",
            "email": "john.doe@company.com",
            "department": "Engineering"
        },
        "result_format": "dict",
        "use_transaction": True
    })

    results, _ = await runtime.execute_async(insert_workflow.build())
    new_user_result = results["insert_user"]["result"]
    user_id = new_user_result['data'][0]['id']
    print(f"Created user with ID: {user_id}")

    # Complex analytical query
    analytics_workflow = WorkflowBuilder()
    analytics_workflow.add_node("SQLDatabaseNode", "analytics_query", {
        "connection_string": "postgresql://user:password@localhost:5432/production_db",
        "query": """
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

# Create workflow with async SQL node
async_workflow = WorkflowBuilder()
async_workflow.add_node("AsyncSQLDatabaseNode", "async_database", {

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

    batch_workflow = WorkflowBuilder()
    batch_workflow.add_node("AsyncSQLDatabaseNode", "batch_insert", {
        "connection_string": "postgresql://user:password@localhost:5432/production_db",
        "query": """
        INSERT INTO users (name, email, department, created_at)
        VALUES (:name, :email, :department, NOW())
        RETURNING id, name
        """,
        "parameters": user_data,  # Batch parameters
        "fetch_mode": "all",
        "use_transaction": True,
        "isolation_level": "READ_COMMITTED"
    })

    runtime = LocalRuntime()
    batch_results, _ = await runtime.execute_async(batch_workflow.build())
    batch_insert_result = batch_results["batch_insert"]["result"]

    print(f"Batch inserted {len(batch_insert_result['data'])} users")

    # Streaming large result set
    stream_workflow = WorkflowBuilder()
    stream_workflow.add_node("AsyncSQLDatabaseNode", "stream_query", {
        "connection_string": "postgresql://user:password@localhost:5432/production_db",
        "query": """
        SELECT u.id, u.name, u.email, u.department, u.created_at,
               p.project_name, p.status, p.deadline
        FROM users u
        LEFT JOIN user_projects up ON u.id = up.user_id
        LEFT JOIN projects p ON up.project_id = p.id
        WHERE u.active = true
        ORDER BY u.created_at DESC
        """,
        "operation": "stream",
        "batch_size": 500,
        "stream_timeout": 30
    })

    runtime = LocalRuntime()
    stream_results, _ = await runtime.execute_async(stream_workflow.build())
    large_dataset_results = stream_results["stream_query"]["result"]["data"]
    print(f"Streamed total of {len(large_dataset_results)} records")

    print(f"Streamed total of {len(large_dataset_results)} records")

    # Complex transaction with multiple operations
    transaction_workflow = WorkflowBuilder()

    # Update user status
    transaction_workflow.add_node("AsyncSQLDatabaseNode", "update_status", {
        "connection_string": "postgresql://user:password@localhost:5432/production_db",
        "query": "UPDATE users SET last_login = NOW() WHERE id = :user_id",
        "parameters": {"user_id": 123},
        "use_transaction": True
    })

    # Log activity
    transaction_workflow.add_node("AsyncSQLDatabaseNode", "log_activity", {
        "connection_string": "postgresql://user:password@localhost:5432/production_db",
        "query": "INSERT INTO user_activity (user_id, activity_type, timestamp) VALUES (:user_id, :activity, NOW())",
        "parameters": {"user_id": 123, "activity": "login"},
        "use_transaction": True
    })

    # Update session
    transaction_workflow.add_node("AsyncSQLDatabaseNode", "update_session", {
        "connection_string": "postgresql://user:password@localhost:5432/production_db",
        "query": "INSERT INTO user_sessions (user_id, session_token, expires_at) VALUES (:user_id, :token, :expires) RETURNING session_id",
        "parameters": {"user_id": 123, "token": "abc123", "expires": "2024-12-31 23:59:59"},
        "use_transaction": True,
        "fetch_mode": "one"
    })

    # Connect in sequence for transaction ordering
    transaction_workflow.add_connection("update_status", "result", "log_activity", "previous_result")
    transaction_workflow.add_connection("log_activity", "result", "update_session", "previous_result")

    runtime = LocalRuntime()
    tx_results, _ = await runtime.execute_async(transaction_workflow.build())
    session_id = tx_results["update_session"]["result"]["data"]["session_id"]

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

# Initialize vector database workflow
vector_workflow = WorkflowBuilder()
vector_workflow.add_node("AsyncPostgreSQLVectorNode", "vector_database", {
    # PostgreSQL connection
    "connection_string": "postgresql://user:password@localhost:5432/vector_db",

    # Vector configuration
    "vector_dimension": 1536,  # OpenAI embedding dimension
    "distance_metric": "cosine",  # "l2", "cosine", "inner_product"
    "index_type": "hnsw",  # "hnsw", "ivfflat"

    # Index parameters
    "hnsw_m": 16,           # Number of bi-directional links
    "hnsw_ef_construction": 64,  # Size of dynamic candidate list

    # Performance settings
    "batch_size": 1000,
    "enable_parallel_indexing": True,

    # Schema configuration
    "table_name": "document_embeddings",
    "vector_column": "embedding",
    "metadata_columns": ["document_id", "title", "content", "tags", "created_at"]
})

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
    insert_workflow = WorkflowBuilder()
    insert_workflow.add_node("AsyncPostgreSQLVectorNode", "insert_vectors", {
        "connection_string": "postgresql://user:password@localhost:5432/vector_db",
        "operation": "insert_batch",
        "data": documents,
        "on_conflict": "update"  # Update if document_id already exists
    })

    runtime = LocalRuntime()
    insert_results, _ = await runtime.execute_async(insert_workflow.build())
    insert_result = insert_results["insert_vectors"]["result"]

    print(f"Inserted {insert_result['inserted_count']} embeddings")

    # Vector similarity search
    query_embedding = generate_embedding("machine learning algorithms")

    search_workflow = WorkflowBuilder()
    search_workflow.add_node("AsyncPostgreSQLVectorNode", "similarity_search", {
        "connection_string": "postgresql://user:password@localhost:5432/vector_db",
        "operation": "similarity_search",
        "query_vector": query_embedding,
        "limit": 5,
        "distance_threshold": 0.8,

        # Metadata filtering
        "filters": {
            "tags": {"contains": "ml"},
            "created_at": {"gte": "2024-01-01"}
        },

        # Return metadata
        "include_metadata": True,
        "include_distances": True
    })

    runtime = LocalRuntime()
    search_results_data, _ = await runtime.execute_async(search_workflow.build())
    search_results = search_results_data["similarity_search"]["result"]

    print(f"Found {len(search_results['results'])} similar documents")

    # Hybrid search (vector + text)
    hybrid_workflow = WorkflowBuilder()
    hybrid_workflow.add_node("AsyncPostgreSQLVectorNode", "hybrid_search", {
        "connection_string": "postgresql://user:password@localhost:5432/vector_db",
        "operation": "hybrid_search",
        "query_vector": query_embedding,
        "text_query": "neural networks",
        "vector_weight": 0.7,  # 70% vector similarity, 30% text match
        "text_weight": 0.3,
        "limit": 10,

        # Advanced filtering
        "filters": {
            "tags": {"intersects": ["ml", "dl", "algorithms"]},
            "title": {"ilike": "%learning%"}
        }
    })

    runtime = LocalRuntime()
    hybrid_results_data, _ = await runtime.execute_async(hybrid_workflow.build())
    hybrid_results = hybrid_results_data["hybrid_search"]["result"]

    print(f"Hybrid search found {len(hybrid_results['results'])} documents")

    # Vector clustering analysis
    cluster_workflow = WorkflowBuilder()
    cluster_workflow.add_node("AsyncPostgreSQLVectorNode", "cluster_analysis", {
        "connection_string": "postgresql://user:password@localhost:5432/vector_db",
        "operation": "cluster_analysis",
        "num_clusters": 3,
        "clustering_method": "kmeans",
        "include_cluster_stats": True
    })

    runtime = LocalRuntime()
    cluster_results, _ = await runtime.execute_async(cluster_workflow.build())
    cluster_analysis = cluster_results["cluster_analysis"]["result"]

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
vector_workflow = WorkflowBuilder()
vector_workflow.add_node("VectorDatabaseNode", "pinecone_vectors", {
    "provider": "pinecone",

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
weaviate_workflow = WorkflowBuilder()
weaviate_workflow.add_node("VectorDatabaseNode", "weaviate_vectors", {
    "provider": "weaviate",

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
    pinecone_insert_workflow = WorkflowBuilder()
    pinecone_insert_workflow.add_node("VectorDatabaseNode", "pinecone_insert", {
        "provider": "pinecone",
        "operation": "upsert",
        "vectors": [
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
        "namespace": "documents"
    })

    runtime = LocalRuntime()
    pinecone_results, _ = await runtime.execute_async(pinecone_insert_workflow.build())
    pinecone_result = pinecone_results["pinecone_insert"]["result"]

    # Insert to Weaviate
    weaviate_insert_workflow = WorkflowBuilder()
    weaviate_insert_workflow.add_node("VectorDatabaseNode", "weaviate_insert", {
        "provider": "weaviate",
        "operation": "create",
        "data": {
            "title": "AI and Machine Learning",
            "content": "Comprehensive guide to AI and ML concepts",
            "category": "technology",
            "timestamp": "2024-01-15T10:00:00Z"
        },
        "vector": generate_embedding("AI and Machine Learning"),
        "class_name": "Document"
    })

    runtime = LocalRuntime()
    weaviate_results, _ = await runtime.execute_async(weaviate_insert_workflow.build())
    weaviate_result = weaviate_results["weaviate_insert"]["result"]

    # Cross-provider search comparison
    query_vector = generate_embedding("machine learning algorithms")

    # Search Pinecone
    pinecone_search_workflow = WorkflowBuilder()
    pinecone_search_workflow.add_node("VectorDatabaseNode", "pinecone_search", {
        "provider": "pinecone",
        "operation": "query",
        "vector": query_vector,
        "top_k": 5,
        "namespace": "documents",
        "filter": {"category": {"$eq": "technology"}},
        "include_metadata": True
    })

    runtime = LocalRuntime()
    pinecone_search_results, _ = await runtime.execute_async(pinecone_search_workflow.build())
    pinecone_search = pinecone_search_results["pinecone_search"]["result"]

    # Search Weaviate
    weaviate_search_workflow = WorkflowBuilder()
    weaviate_search_workflow.add_node("VectorDatabaseNode", "weaviate_search", {
        "provider": "weaviate",
        "operation": "near_vector",
        "vector": query_vector,
        "limit": 5,
        "where": {
            "path": ["category"],
            "operator": "Equal",
            "valueText": "technology"
        },
        "class_name": "Document"
    })

    runtime = LocalRuntime()
    weaviate_search_results, _ = await runtime.execute_async(weaviate_search_workflow.build())
    weaviate_search = weaviate_search_results["weaviate_search"]["result"]

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

# Initialize connection manager workflow
connection_workflow = WorkflowBuilder()
connection_workflow.add_node("AsyncConnectionManagerNode", "connection_manager", {
    # Multi-tenant configuration
    "enable_multi_tenant": True,
    "tenant_isolation": True,

    # Health monitoring
    "health_check_interval": 30,
    "health_check_timeout": 5,
    "max_health_failures": 3,

    # Connection encryption
    "enable_encryption": True,
    "ssl_context": "require",

    # Monitoring
    "enable_metrics": True,
    "metrics_collection_interval": 10
})

# Register multiple database connections
register_workflow = WorkflowBuilder()
register_workflow.add_node("AsyncConnectionManagerNode", "register_primary", {
    "operation": "register_connection",
    "name": "primary_postgres",
    "connection_string": "postgresql://user:password@db1:5432/app_db",
    "pool_config": {
        "min_size": 10,
        "max_size": 50,
        "command_timeout": 30
    }
})

register_workflow.add_node("AsyncConnectionManagerNode", "register_replica", {
    "operation": "register_connection",
    "name": "read_replica",
    "connection_string": "postgresql://user:password@db2:5432/app_db",
    "pool_config": {
        "min_size": 5,
        "max_size": 25,
        "command_timeout": 30
    },
    "connection_type": "read_only"
})

runtime = LocalRuntime()
await runtime.execute_async(register_workflow.build())

# Use connection manager in workflows
async def managed_database_workflow():
    """Demonstrate connection management in workflows."""

    # Get connection for tenant
    conn_workflow = WorkflowBuilder()
    conn_workflow.add_node("AsyncSQLDatabaseNode", "tenant_query", {
        "connection_string": "postgresql://user:password@db1:5432/app_db",
        "query": "SELECT * FROM tenant_data WHERE tenant_id = :tenant_id",
        "parameters": {"tenant_id": "tenant_123"},
        "enable_multi_tenant": True,
        "tenant_id": "tenant_123"
    })

    runtime = LocalRuntime()
    results, _ = await runtime.execute_async(conn_workflow.build())
    result = results["tenant_query"]["result"]["data"]

    return {"records": len(result)}

# Monitor connection health
health_workflow = WorkflowBuilder()
health_workflow.add_node("AsyncConnectionManagerNode", "health_check", {
    "operation": "get_health_status"
})

runtime = LocalRuntime()
health_results, _ = await runtime.execute_async(health_workflow.build())
health_status = health_results["health_check"]["result"]
print(f"Connection health: {health_status}")
```

### WorkflowConnectionPool

```python
# Advanced connection pool for workflow-scoped connections
pool_workflow = WorkflowBuilder()
pool_workflow.add_node("WorkflowConnectionPoolNode", "workflow_connection_pool", {
    # Database configuration
    "database_type": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "workflow_db",
    "user": "workflow_user",
    "password": "secure_password",

    # Pool configuration
    "min_connections": 5,
    "max_connections": 25,
    "health_threshold": 75,  # Health score threshold

    # Pattern-based pre-warming
    "pre_warm_enabled": True,
    "pre_warm_patterns": [
        {"hour_range": (8, 18), "target_connections": 15},  # Business hours
        {"hour_range": (18, 8), "target_connections": 8}    # Off hours
    ],

    # Adaptive sizing
    "adaptive_sizing_enabled": True,

    # Query routing
    "enable_query_routing": True,

    # Circuit breaker
    "circuit_breaker_failure_threshold": 5,
    "circuit_breaker_recovery_timeout": 60,

    # Monitoring
    "enable_monitoring": True,
    "metrics_retention_minutes": 60
})

# Use in workflow
pool_query_workflow = WorkflowBuilder()
pool_query_workflow.add_node("WorkflowConnectionPoolNode", "pool_query", {
    "operation": "execute",
    "query": "SELECT COUNT(*) as total_orders, AVG(amount) as avg_amount FROM orders WHERE created_at >= NOW() - INTERVAL '24 hours'",
    "fetch_mode": "one"
})

runtime = LocalRuntime()
pool_results, _ = await runtime.execute_async(pool_query_workflow.build())
workflow_pool_result = pool_results["pool_query"]["result"]

print(f"Pool query result: {workflow_pool_result}")

# Get pool metrics
metrics_workflow = WorkflowBuilder()
metrics_workflow.add_node("WorkflowConnectionPoolNode", "get_metrics", {
    "operation": "get_metrics"
})

runtime = LocalRuntime()
metrics_results, _ = await runtime.execute_async(metrics_workflow.build())
pool_metrics = metrics_results["get_metrics"]["result"]
print(f"Pool health: {pool_metrics['health']['success_rate']:.2%}")
```

## Query Routing and Optimization

### QueryRouter

```python
from kailash.nodes.data.query_router import QueryRouter

# Initialize intelligent query router workflow
router_workflow = WorkflowBuilder()
router_workflow.add_node("QueryRouterNode", "intelligent_query_router", {
    # Connection definitions
    "connections": {
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
    "enable_load_balancing": True,
    "enable_query_caching": True,
    "cache_ttl": 300,

    # Performance monitoring
    "enable_performance_tracking": True,
    "health_check_interval": 30
})

# Intelligent query routing
async def intelligent_query_routing():
    """Demonstrate intelligent query routing."""

    # Simple read query -> routed to read replica
    user_query_workflow = WorkflowBuilder()
    user_query_workflow.add_node("QueryRouterNode", "user_query", {
        "query": "SELECT id, name, email FROM users WHERE id = :user_id",
        "parameters": {"user_id": 12345},
        "query_type": "READ_SIMPLE"  # Auto-detected if not specified
    })

    runtime = LocalRuntime()
    user_query_results, _ = await runtime.execute_async(user_query_workflow.build())
    user_query = user_query_results["user_query"]["result"]

    # Complex analytical query -> routed to analytics DB
    analytics_query_workflow = WorkflowBuilder()
    analytics_query_workflow.add_node("QueryRouterNode", "analytics_query", {
        "query": """
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
        "query_type": "READ_COMPLEX"
    })

    runtime = LocalRuntime()
    analytics_results, _ = await runtime.execute_async(analytics_query_workflow.build())
    analytics_query = analytics_results["analytics_query"]["result"]

    # Write operation -> routed to primary
    write_query_workflow = WorkflowBuilder()
    write_query_workflow.add_node("QueryRouterNode", "write_query", {
        "query": "INSERT INTO user_activities (user_id, activity_type, timestamp) VALUES (:user_id, :activity, NOW())",
        "parameters": {"user_id": 12345, "activity": "login"},
        "query_type": "WRITE_SIMPLE"
    })

    runtime = LocalRuntime()
    write_results, _ = await runtime.execute_async(write_query_workflow.build())
    write_query = write_results["write_query"]["result"]

    # Bulk write -> routed to primary with optimization
    bulk_data = [
        {"product_id": i, "category": f"category_{i%10}", "price": 10.0 + i}
        for i in range(1000)
    ]

    bulk_write_workflow = WorkflowBuilder()
    bulk_write_workflow.add_node("QueryRouterNode", "bulk_write", {
        "query": "INSERT INTO products (product_id, category, price) VALUES (:product_id, :category, :price)",
        "parameters": bulk_data,
        "query_type": "WRITE_BULK",
        "batch_size": 100
    })

    runtime = LocalRuntime()
    bulk_results, _ = await runtime.execute_async(bulk_write_workflow.build())
    bulk_write = bulk_results["bulk_write"]["result"]

    # Get routing statistics
    stats_workflow = WorkflowBuilder()
    stats_workflow.add_node("QueryRouterNode", "get_stats", {
        "operation": "get_routing_stats"
    })

    runtime = LocalRuntime()
    stats_results, _ = await runtime.execute_async(stats_workflow.build())
    routing_stats = stats_results["get_stats"]["result"]

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

# Initialize schema manager workflow
schema_workflow = WorkflowBuilder()
schema_workflow.add_node("AdminSchemaManagerNode", "production_schema_manager", {
    # Database connection
    "connection_string": "postgresql://admin:password@localhost:5432/production_db",

    # Schema configuration
    "schema_version_table": "schema_versions",
    "migration_path": "/app/migrations",

    # Validation settings
    "enable_schema_validation": True,
    "validate_foreign_keys": True,
    "validate_indexes": True,

    # Backup settings
    "enable_schema_backup": True,
    "backup_path": "/backups/schema",

    # Safety settings
    "require_confirmation": True,
    "dry_run_mode": False
})

# Schema operations
async def schema_management_operations():
    """Demonstrate schema management operations."""

    # Create complete schema
    schema_creation_workflow = WorkflowBuilder()
    schema_creation_workflow.add_node("AdminSchemaManagerNode", "create_schema", {
        "connection_string": "postgresql://admin:password@localhost:5432/production_db",
        "operation": "create_schema",
        "schema_definition": {
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
        "version": "1.0.0",
        "backup_existing": True
    })

    runtime = LocalRuntime()
    schema_results, _ = await runtime.execute_async(schema_creation_workflow.build())
    schema_creation = schema_results["create_schema"]["result"]

    # Validate schema health
    validation_workflow = WorkflowBuilder()
    validation_workflow.add_node("AdminSchemaManagerNode", "validate_schema", {
        "connection_string": "postgresql://admin:password@localhost:5432/production_db",
        "operation": "validate_schema",
        "validation_checks": [
            "table_structure",
            "foreign_key_constraints",
            "index_integrity",
            "data_consistency"
        ],
        "include_performance_analysis": True
    })

    runtime = LocalRuntime()
    validation_results, _ = await runtime.execute_async(validation_workflow.build())
    validation_result = validation_results["validate_schema"]["result"]

    # Migration planning
    migration_plan_workflow = WorkflowBuilder()
    migration_plan_workflow.add_node("AdminSchemaManagerNode", "plan_migration", {
        "connection_string": "postgresql://admin:password@localhost:5432/production_db",
        "operation": "plan_migration",
        "target_schema_version": "2.0.0",
        "migration_files": [
            "001_add_user_preferences_table.sql",
            "002_add_project_tags_column.sql",
            "003_create_activity_log_table.sql"
        ],
        "analyze_dependencies": True,
        "estimate_downtime": True
    })

    runtime = LocalRuntime()
    migration_plan_results, _ = await runtime.execute_async(migration_plan_workflow.build())
    migration_plan = migration_plan_results["plan_migration"]["result"]

    # Execute migration (with safety checks)
    if validation_result['health_score'] > 0.95:
        migration_exec_workflow = WorkflowBuilder()
        migration_exec_workflow.add_node("AdminSchemaManagerNode", "execute_migration", {
            "connection_string": "postgresql://admin:password@localhost:5432/production_db",
            "operation": "execute_migration",
            "migration_plan": migration_plan,
            "backup_before_migration": True,
            "rollback_on_failure": True,
            "max_downtime_minutes": 5
        })

        runtime = LocalRuntime()
        migration_exec_results, _ = await runtime.execute_async(migration_exec_workflow.build())
        migration_result = migration_exec_results["execute_migration"]["result"]

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
    conn_mgr_workflow = WorkflowBuilder()
    conn_mgr_workflow.add_node("AsyncConnectionManagerNode", "connection_manager", {
        "enable_multi_tenant": True,
        "health_check_interval": 30,
        "enable_encryption": True
    })

    # Register connections
    register_primary_workflow = WorkflowBuilder()
    register_primary_workflow.add_node("AsyncConnectionManagerNode", "register_primary", {
        "operation": "register_connection",
        "name": "primary_db",
        "connection_string": "postgresql://user:pass@primary:5432/prod_db",
        "pool_config": {"min_size": 20, "max_size": 100}
    })

    register_replica_workflow = WorkflowBuilder()
    register_replica_workflow.add_node("AsyncConnectionManagerNode", "register_replica", {
        "operation": "register_connection",
        "name": "read_replica",
        "connection_string": "postgresql://user:pass@replica:5432/prod_db",
        "pool_config": {"min_size": 10, "max_size": 50},
        "connection_type": "read_only"
    })

    runtime = LocalRuntime()
    await runtime.execute_async(register_primary_workflow.build())
    await runtime.execute_async(register_replica_workflow.build())

    # 2. Query routing
    query_router_workflow = WorkflowBuilder()
    query_router_workflow.add_node("QueryRouterNode", "production_router", {
        "connections": {
            "primary": {"capabilities": ["READ_SIMPLE", "READ_COMPLEX", "WRITE_SIMPLE", "WRITE_BULK", "DDL"]},
            "replica": {"capabilities": ["READ_SIMPLE", "READ_COMPLEX"]}
        },
        "enable_load_balancing": True,
        "enable_query_caching": True
    })

    # 3. Vector database for AI features
    vector_db_workflow = WorkflowBuilder()
    vector_db_workflow.add_node("AsyncPostgreSQLVectorNode", "ai_vectors", {
        "connection_string": "postgresql://user:pass@vector:5432/vector_db",
        "vector_dimension": 1536,
        "distance_metric": "cosine"
    })

    # 4. Schema management
    schema_mgr_workflow = WorkflowBuilder()
    schema_mgr_workflow.add_node("AdminSchemaManagerNode", "schema_manager", {
        "connection_string": "postgresql://admin:pass@primary:5432/prod_db"
    })

    # 5. Workflow connection pool
    pool_workflow = WorkflowBuilder()
    pool_workflow.add_node("WorkflowConnectionPoolNode", "workflow_pool", {
        "database_type": "postgresql",
        "host": "primary",
        "database": "prod_db",
        "min_connections": 10,
        "max_connections": 50,
        "enable_monitoring": True
    })

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
    prepared_workflow = WorkflowBuilder()
    prepared_workflow.add_node("SQLDatabaseNode", "prepared_query", {
        "connection_string": "postgresql://user:password@localhost:5432/production_db",
        "query": "SELECT * FROM users WHERE department = :department AND active = :active",
        "prepare_statement": True
    })

    # Batch operations for better performance
    batch_workflow = WorkflowBuilder()
    for idx, (dept, active) in enumerate([("Engineering", True), ("Marketing", True), ("Sales", True)]):
        batch_workflow.add_node("SQLDatabaseNode", f"batch_{idx}", {
            "connection_string": "postgresql://user:password@localhost:5432/production_db",
            "query": "SELECT * FROM users WHERE department = :department AND active = :active",
            "parameters": {"department": dept, "active": active}
        })

    runtime = LocalRuntime()
    batch_results, _ = await runtime.execute_async(batch_workflow.build())

    # Use appropriate fetch modes
    iterator_workflow = WorkflowBuilder()
    iterator_workflow.add_node("AsyncSQLDatabaseNode", "large_result", {
        "connection_string": "postgresql://user:password@localhost:5432/production_db",
        "query": "SELECT * FROM large_table ORDER BY created_at",
        "fetch_mode": "iterator",
        "chunk_size": 1000
    })

    iterator_results, _ = await runtime.execute_async(iterator_workflow.build())
    large_result = iterator_results["large_result"]["result"]

    # Connection-specific optimizations
    optimization_workflow = WorkflowBuilder()
    optimization_workflow.add_node("AsyncSQLDatabaseNode", "set_work_mem", {
        "connection_string": "postgresql://user:password@localhost:5432/production_db",
        "query": "SET work_mem = '256MB'"
    })
    optimization_workflow.add_node("AsyncSQLDatabaseNode", "set_page_cost", {
        "connection_string": "postgresql://user:password@localhost:5432/production_db",
        "query": "SET random_page_cost = 1.1"
    })
    optimization_workflow.add_node("AsyncSQLDatabaseNode", "complex_query", {
        "connection_string": "postgresql://user:password@localhost:5432/production_db",
        "query": "SELECT * FROM complex_analytical_view"
    })

    # Execute in sequence to maintain session settings
    optimization_workflow.add_connection("set_work_mem", "result", "set_page_cost", "previous")
    optimization_workflow.add_connection("set_page_cost", "result", "complex_query", "previous")

    opt_results, _ = await runtime.execute_async(optimization_workflow.build())
    result = opt_results["complex_query"]["result"]

    return {"optimization": "complete"}
```

### 3. Security and Access Control

```python
# Database security patterns
async def database_security_patterns():
    """Implement database security best practices."""

    # Row-level security
    secured_workflow = WorkflowBuilder()
    secured_workflow.add_node("SQLDatabaseNode", "secured_database", {
        "connection_string": "postgresql://app_user:password@localhost:5432/secure_db",

        # Enable access control
        "enable_access_control": True,
        "access_control_config": {
            "row_level_security": True,
            "column_masking": True,
            "audit_logging": True
        },

        # Data masking rules
        "data_masking_rules": {
            "users.email": {"mask_type": "email", "visible_chars": 3},
            "users.phone": {"mask_type": "phone", "visible_chars": 4},
            "financial.account_number": {"mask_type": "full", "replacement": "***"}
        }
    })

    # Query with user context
    user_context = {
        "user_id": "user_123",
        "role": "analyst",
        "department": "finance",
        "clearance_level": 3
    }

    secured_query_workflow = WorkflowBuilder()
    secured_query_workflow.add_node("SQLDatabaseNode", "secured_query", {
        "connection_string": "postgresql://app_user:password@localhost:5432/secure_db",
        "query": "SELECT id, name, email, salary FROM users WHERE department = :dept",
        "parameters": {"dept": "finance"},
        "user_context": user_context,
        "enable_access_control": True
    })

    runtime = LocalRuntime()
    secured_results, _ = await runtime.execute_async(secured_query_workflow.build())
    secured_result = secured_results["secured_query"]["result"]

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
