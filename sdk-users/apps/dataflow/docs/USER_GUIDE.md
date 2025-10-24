# Kailash DataFlow User Guide

## Table of Contents
1. [Introduction](#introduction)
2. [Why DataFlow?](#why-dataflow)
3. [Framework Comparisons](#framework-comparisons)
4. [Getting Started](#getting-started)
5. [Core Concepts](#core-concepts)
6. [Built-in Safety Features](#built-in-safety-features)
7. [Advanced Features](#advanced-features)
8. [Production Deployment](#production-deployment)
9. [Migration Guides](#migration-guides)

## Introduction

DataFlow is a revolutionary database framework that combines the ease of use of Django ORM with the power of Kailash SDK's enterprise-grade infrastructure. Built 100% on Kailash SDK components, it provides:

- **Zero-configuration development** - Just works out of the box
- **Production-grade quality** - Enterprise features built-in
- **Workflow-native design** - Database operations as first-class nodes
- **10-100x performance** - Compared to traditional ORMs
- **Automatic data safety** - Built-in protection for complex operations
- **Smart error recovery** - Automatically handles failures and cleanup

## Why DataFlow?

### The Problem with Traditional ORMs

Traditional web framework ORMs (Django, Rails, SQLAlchemy) were designed for the request-response cycle:

1. **Request-scoped connections** - Connection per HTTP request
2. **Synchronous operations** - Blocking I/O limits throughput
3. **Limited transaction scope** - Single request boundaries
4. **Poor resource utilization** - Connections idle between requests

### The DataFlow Solution

DataFlow leverages Kailash's workflow-centric architecture:

1. **Workflow-scoped connections** - Persist across entire workflow
2. **Async-first operations** - Non-blocking for high throughput
3. **Distributed transactions** - Span multiple services/databases
4. **Optimal resource usage** - Actor-based connection pooling

## Framework Comparisons

### DataFlow vs Django ORM

| Feature | Django ORM | DataFlow | Improvement |
|---------|------------|----------|-------------|
| **Connection Pooling** | Thread-local, limited | Actor-based, workflow-scoped | 50x capacity |
| **Async Support** | Minimal (Django 4.1+) | Native async throughout | 10x throughput |
| **Transaction Scope** | Request-bound | Workflow-bound | Matches business logic |
| **Bulk Operations** | Manual optimization | Automatic database-specific optimization | 100x faster bulk operations |
| **Error Recovery** | Manual try/catch | Automatic retry and cleanup | Zero-config resilience |
| **Monitoring** | Django Debug Toolbar | Real-time, production-grade | Enterprise-ready |
| **Multi-tenancy** | Manual implementation | Built-in with isolation | Secure by default |
| **Data Safety** | Manual transaction management | Automatic protection | No data corruption |

#### Django Example - Complex Order Processing
```python
# Django - Manual error handling required
from django.db import models, transaction
from django.core.exceptions import ValidationError

class Order(models.Model):
    customer_id = models.IntegerField()
    total = models.DecimalField(max_digits=10, decimal_places=2)

def process_order(customer_id, items):
    try:
        with transaction.atomic():
            # Step 1: Create order
            order = Order.objects.create(customer_id=customer_id, total=0)

            # Step 2: Process each item (manual loop)
            total = 0
            for item in items:
                product = Product.objects.select_for_update().get(id=item['id'])
                if product.stock < item['quantity']:
                    raise ValidationError("Insufficient stock")
                product.stock -= item['quantity']
                product.save()
                total += product.price * item['quantity']

            # Step 3: Update order total
            order.total = total
            order.save()

            # Step 4: Send email (if this fails, order is rolled back!)
            send_confirmation_email(order.customer_id)

    except Exception as e:
        # Manual error handling
        logger.error(f"Order processing failed: {e}")
        return {"status": "error", "message": str(e)}

    return {"status": "success", "order_id": order.id}
```

#### DataFlow Example - Automatic Safety
```python
# DataFlow - Automatic error handling and optimization
from kailash_dataflow import DataFlow

db = DataFlow()

@db.model
class Order:
    customer_id: int
    total: float

@db.model
class Product:
    name: str
    price: float
    stock: int

# Simple workflow - DataFlow handles all the complexity
workflow = WorkflowBuilder()

# Step 1: Create order
workflow.add_node("OrderCreateNode", "create_order", {
    "customer_id": 123,
    "total": 0
})

# Step 2: Bulk update inventory (automatically optimized)
workflow.add_node("ProductBulkUpdateNode", "update_inventory", {
    "updates": [
        {"id": 1, "stock": "stock - 2"},
        {"id": 2, "stock": "stock - 1"}
    ]
})

# Step 3: Send confirmation
workflow.add_node("EmailNotificationNode", "send_email", {
    "template": "order_confirmation"
})

# DataFlow automatically:
# - Ensures all steps succeed or all are rolled back
# - Optimizes bulk operations for your database
# - Retries on temporary failures
# - If email fails, completes order but logs the issue
# - Provides real-time monitoring and metrics
```

### DataFlow vs Prisma

| Feature | Prisma | DataFlow | Advantage |
|---------|--------|----------|-----------|
| **Schema Definition** | schema.prisma file | Python classes | No separate schema file |
| **Type Safety** | Generated TypeScript | Native Python types | Built-in type hints |
| **Migrations** | Prisma Migrate | Kailash migrations | Async, versioned |
| **Query Builder** | Prisma Client | Workflow nodes | Composable operations |
| **Performance** | Good | Excellent | Workflow optimization |

#### Prisma Example
```prisma
// schema.prisma
model Product {
  id    Int     @id @default(autoincrement())
  name  String
  price Float
}
```

```typescript
// TypeScript code
const product = await prisma.product.create({
  data: { name: 'iPhone 15', price: 999.99 }
});
```

#### DataFlow Example
```python
# Single Python file - no schema separation
@db.model
class Product:
    name: str
    price: float

# Type-safe operations
workflow.add_node("ProductCreateNode", "create", {
    "name": "iPhone 15",  # IDE autocomplete
    "price": 999.99       # Type validated
})
```

### DataFlow vs SQLAlchemy

| Feature | SQLAlchemy | DataFlow | Benefit |
|---------|------------|----------|---------|
| **Setup Complexity** | High (engine, session, base) | Zero config | Instant productivity |
| **Async Support** | SQLAlchemy 2.0+ | Native | Better performance |
| **Session Management** | Manual | Automatic | No session leaks |
| **Query Execution** | Imperative | Declarative workflows | Better composition |

#### SQLAlchemy Example
```python
# SQLAlchemy - Complex setup
from sqlalchemy import create_engine, Column, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()
engine = create_engine('postgresql://...')
Session = sessionmaker(bind=engine)

class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    price = Column(Float)

# Manual session management
session = Session()
try:
    product = Product(name='iPhone 15', price=999.99)
    session.add(product)
    session.commit()
finally:
    session.close()
```

#### DataFlow Example
```python
# DataFlow - Zero setup
db = DataFlow()  # Auto-configures everything

@db.model
class Product:
    name: str
    price: float

# Automatic session management
workflow.add_node("ProductCreateNode", "create", {
    "name": "iPhone 15",
    "price": 999.99
})
# No manual session handling needed
```

## Getting Started

### Installation

DataFlow is included with Kailash SDK:

```bash
pip install kailash
```

### Quick Start

```python
from kailash_dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# 1. Zero configuration
db = DataFlow()

# 2. Define your model
@db.model
class User:
    name: str
    email: str
    active: bool = True

# 3. Use in workflows
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice",
    "email": "alice@example.com"
})

# 4. Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

That's it! DataFlow automatically:
- Creates an in-memory database
- Generates CRUD and bulk operation nodes
- Handles connections and connection pooling
- Protects your data with automatic safety mechanisms
- Monitors performance and provides real-time insights
- Handles failures with smart retry and cleanup logic

## Core Concepts

### Models

Models define your data structure using Python type hints:

```python
from datetime import datetime
from typing import Optional
from kailash_dataflow import DataFlow

db = DataFlow()

@db.model
class BlogPost:
    title: str
    content: str
    published: bool = False
    views: int = 0
    published_at: Optional[datetime] = None

    # DataFlow options
    __dataflow__ = {
        'soft_delete': True,      # Adds deleted_at field
        'versioned': True,        # Adds version field
        'multi_tenant': True,     # Adds tenant_id field
    }

    # Indexes
    __indexes__ = [
        {'name': 'idx_published', 'fields': ['published', 'published_at']},
        {'name': 'idx_views', 'fields': ['views'], 'type': 'btree'},
    ]
```

### Generated Nodes

For each model, DataFlow automatically generates these nodes:

#### Basic Operations
1. **CreateNode** - Insert new records
2. **ReadNode** - Fetch single record
3. **UpdateNode** - Modify existing records
4. **DeleteNode** - Remove records (soft/hard)
5. **ListNode** - Query multiple records

#### High-Performance Bulk Operations
6. **BulkCreateNode** - Insert thousands of records efficiently
7. **BulkUpdateNode** - Update multiple records with smart filtering
8. **BulkDeleteNode** - Remove multiple records safely
9. **BulkUpsertNode** - Insert or update records intelligently

#### Example: What You Get Automatically
```python
@db.model
class Product:
    name: str
    price: float
    category: str

# DataFlow automatically creates these nodes for you:
# - ProductCreateNode
# - ProductReadNode
# - ProductUpdateNode
# - ProductDeleteNode
# - ProductListNode
# - ProductBulkCreateNode     ← New! High-performance bulk insert
# - ProductBulkUpdateNode     ← New! Smart bulk updates
# - ProductBulkDeleteNode     ← New! Safe bulk deletion
# - ProductBulkUpsertNode     ← New! Insert-or-update operations
```

#### Bulk Operations Benefits
- **Database-Optimized**: Uses PostgreSQL COPY, MySQL batch INSERT, etc.
- **Chunking**: Automatically splits large datasets for optimal memory usage
- **Progress Tracking**: Real-time progress reporting for long operations
- **Error Recovery**: Continues processing even if some records fail
- **Automatic Cleanup**: Rolls back changes if critical errors occur

### Workflow Integration

Database operations integrate naturally with Kailash workflows:

#### Simple Operations
```python
workflow = WorkflowBuilder()

# Create a blog post
workflow.add_node("BlogPostCreateNode", "create_post", {
    "title": "Introduction to DataFlow",
    "content": "DataFlow makes database operations simple..."
})

# Update view count
workflow.add_node("BlogPostUpdateNode", "increment_views", {
    "id": 1,  # Use actual post ID or parameter mapping
    "views": 100  # New view count
})

# Connect nodes - output flows to input
workflow.add_connection("create_post", "increment_views", "id", "post_id")
```

#### Bulk Operations for High Performance
```python
# Import thousands of products efficiently
workflow = WorkflowBuilder()

# Step 1: Bulk import products (handles chunking, optimization, progress tracking)
workflow.add_node("ProductBulkCreateNode", "import_products", {
    "records": product_data,  # List of thousands of products
    "chunk_size": 1000,       # Optional: DataFlow chooses optimal size
    "error_strategy": "continue"  # Continue if some records fail
})

# Step 2: Bulk update categories (database-optimized SQL) - v0.6.0+ API
workflow.add_node("ProductBulkUpdateNode", "categorize_products", {
    "filter": {"category": "uncategorized"},
    "fields": {"category": "general"}  # v0.6.0+ API
})

# Step 3: Generate reports on the imported data
workflow.add_node("ReportGeneratorNode", "create_import_report", {
    "report_type": "import_summary"
})

# DataFlow automatically coordinates all steps with safety guarantees
```

#### Real-World Example: E-commerce Data Migration
```python
# Migrate product catalog from old system
workflow = WorkflowBuilder()

# Step 1: Extract data from legacy system
workflow.add_node("LegacyDataExtractorNode", "extract_legacy", {
    "source": "legacy_db",
    "table": "products"
})

# Step 2: Transform and validate data
workflow.add_node("DataTransformNode", "transform_data", {
    "transformations": ["normalize_prices", "validate_categories"]
})

# Step 3: Bulk insert into new system (automatically optimized)
workflow.add_node("ProductBulkCreateNode", "import_products", {
    "records": ":transformed_data",
    "conflict_resolution": "skip",  # Skip duplicates
    "validation": "strict"          # Validate all fields
})

# Step 4: Update search indexes
workflow.add_node("SearchIndexUpdateNode", "update_search", {
    "index_type": "product_catalog"
})

# Connect the workflow
workflow.add_connection("source", "result", "target", "input")  # Fixed complex pattern
workflow.add_connection("transform_data", "import_products", "transformed_data")
workflow.add_connection("import_products", "update_search", "imported_ids")

# DataFlow automatically:
# - Handles the entire migration as one protected operation
# - Rolls back everything if any step fails critically
# - Provides real-time progress tracking
# - Optimizes bulk operations for your database type
# - Retries on temporary failures
# - Generates detailed operation reports
```

## Built-in Safety Features

DataFlow automatically protects your data with enterprise-grade safety features that "just work" - no configuration required.

### Automatic Data Protection

DataFlow automatically wraps your operations in safety mechanisms:

```python
# This simple workflow is automatically protected
workflow = WorkflowBuilder()
workflow.add_node("OrderCreateNode", "create_order", {
    "customer_id": 123,
    "items": [{"product_id": 1, "quantity": 2}]
})
workflow.add_node("InventoryUpdateNode", "update_stock", {
    "product_id": 1,
    "quantity": -2
})

# DataFlow automatically:
# - Ensures both operations succeed or both fail
# - Handles cleanup if something goes wrong
# - Retries on temporary failures
# - Monitors performance and health
```

### Smart Bulk Operations

When you process large amounts of data, DataFlow automatically handles the complexity:

```python
# Processing thousands of records safely
@db.model
class Product:
    name: str
    price: float
    category: str

# This automatically handles:
# - Chunking large datasets for optimal performance
# - Database-specific optimizations (PostgreSQL COPY, MySQL batch INSERT)
# - Automatic retry on temporary failures
# - Progress tracking and monitoring
# - Cleanup if the operation fails partway through
workflow.add_node("ProductBulkCreateNode", "import_products", {
    "records": [
        {"name": "Product 1", "price": 10.99, "category": "electronics"},
        # ... thousands more records
    ]
})
```

### Multi-Step Operation Safety

For complex workflows involving multiple steps, DataFlow automatically coordinates everything:

```python
# Order processing workflow
workflow = WorkflowBuilder()

# Step 1: Create the order
workflow.add_node("OrderCreateNode", "create_order", {...})

# Step 2: Process payment
workflow.add_node("PaymentProcessNode", "charge_card", {...})

# Step 3: Update inventory
workflow.add_node("InventoryUpdateNode", "reserve_items", {...})

# Step 4: Send confirmation
workflow.add_node("EmailNotificationNode", "send_confirmation", {...})

# DataFlow automatically:
# - Ensures all steps complete successfully
# - If payment fails, automatically cancels the order
# - If inventory is insufficient, refunds the payment
# - If email fails, still completes the order but logs the issue
# - Provides real-time monitoring of the entire process
```

### What This Means for You

1. **No Manual Error Handling** - DataFlow automatically handles failures
2. **No Data Corruption** - Operations are protected from partial failures
3. **No Performance Tuning** - Automatic optimization for your database
4. **No Monitoring Setup** - Built-in tracking and alerting
5. **No Complex Coordination** - Multi-step operations "just work"

### Configuration Options (Optional)

While DataFlow works great with zero configuration, you can customize the safety behavior:

```python
# For high-consistency requirements (banking, medical)
db = DataFlow(
    data_safety_level="maximum",  # Strictest protection
    auto_retry_attempts=5,        # More retries for critical operations
)

# For high-performance requirements (analytics, logging)
db = DataFlow(
    data_safety_level="balanced",  # Good protection, faster performance
    bulk_optimization_mode="speed", # Optimize for throughput
)

# For simple applications (development, prototyping)
db = DataFlow()  # Default: good protection with great performance
```

## Advanced Features

### Multi-Tenancy

```python
# Enable multi-tenancy
db = DataFlow(multi_tenant=True)

@db.model
class Customer:
    name: str
    email: str
    # tenant_id added automatically

# Tenant isolation is automatic
workflow.add_node("CustomerListNode", "list_customers", {
    # Only returns current tenant's customers
})
```

### Optimistic Locking

```python
@db.model
class Product:
    name: str
    stock: int

    __dataflow__ = {'versioned': True}

# Update with version check (v0.6.0+ API)
workflow.add_node("ProductUpdateNode", "update_stock", {
    "filter": {"id": 1, "version": 5},  # v0.6.0+ API
    "fields": {"stock": 100},
    # Fails if version changed (concurrent update)
})
```

### Real-Time Monitoring

DataFlow includes enterprise-grade monitoring that tracks everything automatically:

```python
# Enable comprehensive monitoring (enabled by default in production)
db = DataFlow(
    monitoring=True,
    slow_query_threshold=1.0,      # Alert on queries > 1s
    query_insights=True,           # Detailed metrics
    performance_monitoring=True,   # Track bulk operation performance
    safety_monitoring=True,        # Monitor automatic recovery actions
)

# Access monitoring data
monitor = db.get_monitor_nodes()
transaction_monitor = monitor['transaction']    # Tracks multi-step operations
metrics_collector = monitor['metrics']          # Performance metrics
bulk_monitor = monitor['bulk_operations']       # Bulk operation insights
safety_monitor = monitor['safety']              # Automatic recovery tracking
```

#### What Gets Monitored Automatically

1. **Operation Performance**
   - Query execution times
   - Bulk operation throughput
   - Connection pool utilization
   - Memory usage during large operations

2. **Data Safety Events**
   - Automatic retry attempts
   - Recovery actions taken
   - Multi-step operation coordination
   - Error patterns and resolution

3. **System Health**
   - Database connection health
   - Resource utilization
   - Performance anomalies
   - Capacity planning metrics

#### Production Dashboard Integration

```python
# Export metrics to your monitoring system
db = DataFlow(
    monitoring_export_format="prometheus",  # or "datadog", "cloudwatch"
    monitoring_endpoint="/metrics",
    real_time_alerts=True,
)

# Metrics are automatically available at:
# - /metrics (Prometheus format)
# - Real-time WebSocket: ws://your-app/monitoring
# - REST API: GET /api/monitoring/stats
```

### Query Optimization

```python
# DataFlow automatically optimizes queries
workflow.add_node("ProductListNode", "search", {
    "filter": {"price": {"$lt": 1000}},
    "order_by": ["-created_at"],
    "limit": 20,
    # Automatically uses indexes
    # Generates optimal SQL
    # Caches results if enabled
})
```

## Production Deployment

### Environment Configuration

```bash
# Production environment variables
export KAILASH_ENV=production
export DATABASE_URL=postgresql://user:pass@host:5432/db
export DB_POOL_SIZE=100
export DATAFLOW_MONITORING=true
export DATAFLOW_MULTI_TENANT=true
```

### Performance Tuning

```python
# Production configuration
from kailash_dataflow import DataFlow

db = DataFlow(
    database_url="postgresql://user:pass@host:5432/db",
    pool_size=100,
    pool_max_overflow=200,
    pool_recycle=3600,
    echo=False,
    monitoring=True,
    multi_tenant=True,
    audit_logging=True,
    encryption_key="your-encryption-key",
    cache_enabled=True,
    cache_ttl=3600
)
```

### Scaling Strategies

1. **Connection Pool Optimization**
   ```python
# Calculate optimal pool size
pool_size = cpu_count * 4  # General rule
max_overflow = pool_size * 2
   ```

2. **Read Replicas**
   ```python
# Automatic read/write splitting
workflow.add_node("ProductListNode", "read_products", {
    # Automatically routes to read replica
})
   ```

3. **Caching Layer**
   ```python
   db = DataFlow(
       enable_query_cache=True,
       cache_ttl=300,  # 5 minutes
   )
   ```

## Migration Guides

### From Django

See [Django Migration Guide](migration-guides/from-django.md) for detailed steps.

Key differences:
- Models use Python type hints instead of Django fields
- Operations are workflow nodes instead of view functions
- Connections persist across workflow instead of per-request

### From SQLAlchemy

See [SQLAlchemy Migration Guide](migration-guides/from-sqlalchemy.md).

Key improvements:
- No session management needed
- Automatic connection pooling
- Built-in async support

### From Prisma

See [Prisma Migration Guide](migration-guides/from-prisma.md).

Key advantages:
- No separate schema file
- Python-native type safety
- Workflow integration

## Best Practices

1. **Start Simple** - Use zero configuration for development
2. **Model Design** - Use type hints for clarity and auto-generated validation
3. **Workflow Patterns** - Compose small, reusable nodes
4. **Bulk Operations** - Use bulk nodes for processing large datasets (>100 records)
5. **Safety First** - Let DataFlow handle error recovery automatically
6. **Monitoring** - Enable comprehensive monitoring in staging and production
7. **Testing** - Use in-memory mode for fast tests, real databases for integration tests
8. **Data Safety Levels** - Choose appropriate safety level for your use case:
   - `development`: Fast iteration, basic protection
   - `balanced`: Good for most production applications (default)
   - `maximum`: For critical systems (financial, medical, legal)

### When to Use What

#### Use Basic Operations For:
- Simple CRUD operations
- Individual record processing
- Development and prototyping
- Operations on <100 records

#### Use Bulk Operations For:
- Data imports/exports
- Batch processing
- Analytics data loading
- Operations on >100 records
- Performance-critical workflows

#### Use Maximum Safety Level For:
- Financial transactions
- Medical records
- Legal document processing
- Any system where data loss is unacceptable

#### Use Balanced Safety Level For:
- E-commerce applications
- Content management systems
- User-generated content
- Most business applications

#### Use Development Safety Level For:
- Local development
- Testing environments
- Prototyping
- Non-critical data processing

## Troubleshooting

### Common Issues

1. **"No primary key" error**
   - DataFlow adds `id` field automatically
   - Define custom primary key if needed

2. **Connection pool exhausted**
   - Increase pool_size
   - Check for connection leaks
   - Monitor with TransactionMonitorNode

3. **Slow queries**
   - Enable query insights
   - Add appropriate indexes
   - Use read replicas for heavy reads

4. **Bulk operation performance issues**
   - Check if you're using the right chunk_size (default is usually optimal)
   - Ensure your database has sufficient memory for bulk operations
   - Consider using `bulk_optimization_mode="speed"` for non-critical data
   - Monitor bulk operation metrics in the dashboard

5. **"Safety operation failed" errors**
   - Check the automatic recovery logs in monitoring
   - Verify all participants in multi-step operations are accessible
   - Consider increasing `auto_retry_attempts` for unreliable networks
   - Check if your safety level is too strict for your use case

6. **Multi-step operation timeouts**
   - Increase timeout values in production configuration
   - Break large operations into smaller chunks
   - Use bulk operations for large datasets instead of loops
   - Monitor operation progress in real-time dashboard

7. **Memory usage during large imports**
   - DataFlow automatically chunks large operations
   - If still seeing issues, reduce chunk_size manually
   - Consider using streaming imports for very large datasets
   - Monitor memory usage in the operations dashboard

### Getting Help

- **Operation Logs**: Check DataFlow's automatic operation logging
- **Monitoring Dashboard**: Use built-in metrics to diagnose issues
- **Safety Reports**: Review automatic recovery action reports
- **Performance Metrics**: Analyze bulk operation performance data
- **Community Support**: Join the Kailash community for help

## Next Steps

- Explore [examples/](../examples/) for working code
- Read [Architecture Decision Records](adr/) for design rationale
- Try the [Getting Started Tutorial](getting-started.md)
- Join the Kailash community for support

## Summary

DataFlow represents a new generation of database frameworks that combines:

✅ **Zero-Configuration Development** - Just works out of the box
✅ **Enterprise-Grade Safety** - Automatic data protection and recovery
✅ **High-Performance Bulk Operations** - Database-optimized processing
✅ **Intelligent Monitoring** - Real-time insights and alerting
✅ **Workflow-Native Design** - Perfect integration with business logic
✅ **Production-Ready Scaling** - From prototype to enterprise

### What Makes DataFlow Different

Unlike traditional ORMs that require manual error handling, complex transaction management, and performance optimization, DataFlow **automatically handles the hard parts** while maintaining the simplicity you love.

**For Django developers**: Get the ease of Django ORM with 100x performance and enterprise reliability.

**For new projects**: Start with zero configuration and automatically inherit enterprise-grade capabilities.

**For existing systems**: Migrate incrementally while gaining automatic safety and performance benefits.

**DataFlow: Where simplicity meets enterprise power. Start simple, scale infinitely, sleep soundly.** 🚀
