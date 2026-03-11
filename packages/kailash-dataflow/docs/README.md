# DataFlow Documentation

Welcome to the DataFlow documentation! DataFlow is a multi-database framework that progressively scales from simple prototypes to enterprise applications.

> ✅ **v0.6.0 RELEASE**: Full support for PostgreSQL, MySQL, SQLite (SQL), MongoDB (Document), and pgvector (Vector Search)

## 📚 Documentation Structure

### Getting Started

- **[Installation Guide](getting-started/installation.md)** - Install DataFlow and dependencies
- **[Quick Start](getting-started/quickstart.md)** - Build your first DataFlow app in 5 minutes
- **[Core Concepts](getting-started/concepts.md)** - Understand DataFlow's architecture

### Development Guides

- **[Model Definition](development/models.md)** - Define database models with decorators
- **[Generated Nodes](development/nodes.md)** - Understand the 9 auto-generated nodes
- **[Bulk Operations](development/bulk-operations.md)** - High-performance data operations
- **[Relationships](development/relationships.md)** - Handle foreign keys and joins
- **[Query Patterns](development/queries.md)** - Advanced filtering and aggregation
- **[Custom Development](development/custom-nodes.md)** - Create custom nodes

### Features

- **[Auto-Migrations](features/auto-migrations.md)** - Automatic schema synchronization
- **[Visual Migration Builder](features/visual-migrations.md)** - Fluent API for migrations
- **[Multi-Database Support](features/multi-database.md)** - PostgreSQL, MySQL, SQLite
- **[Progressive Configuration](features/progressive-config.md)** - Zero-config to enterprise
- **[Query Optimization](features/optimization.md)** - 100-1000x performance gains
- **[Change Data Capture](features/cdc.md)** - Monitor database changes

### Enterprise Features

- **[Multi-Tenancy](enterprise/multi-tenant.md)** - Isolated tenant data
- **[Security & Encryption](enterprise/security.md)** - Field-level encryption, RBAC
- **[Audit & Compliance](enterprise/compliance.md)** - GDPR, HIPAA, SOC2 compliance
- **[Performance at Scale](enterprise/performance.md)** - Handle millions of records
- **[Distributed Transactions](enterprise/transactions.md)** - Saga and 2PC patterns
- **[High Availability](enterprise/high-availability.md)** - Read replicas, failover

### Production Guide

- **[Deployment](production/deployment.md)** - Deploy to production
- **[Monitoring](production/monitoring.md)** - Track performance and health
- **[Backup & Recovery](production/backup.md)** - Data protection strategies
- **[Troubleshooting](production/troubleshooting.md)** - Common issues and solutions
- **[Performance Tuning](production/tuning.md)** - Optimize for your workload

### Integration

- **[Nexus Integration](integration/nexus.md)** - Multi-channel platform integration
- **[Gateway APIs](integration/gateway.md)** - Auto-generate REST APIs
- **[Event-Driven Architecture](integration/events.md)** - Database events and webhooks
- **[Workflow Integration](integration/workflows.md)** - Use with Kailash workflows

### API Reference

- **[Python API](api/python.md)** - Complete Python API reference
- **[Node Reference](api/nodes.md)** - All node types and parameters
- **[Configuration](api/configuration.md)** - Configuration options
- **[Migrations API](api/migrations.md)** - Migration system reference

### Examples

- **[Basic Examples](examples/basic.md)** - Simple use cases
- **[Advanced Examples](examples/advanced.md)** - Complex scenarios
- **[Enterprise Examples](examples/enterprise.md)** - Production patterns
- **[Integration Examples](examples/integration.md)** - Nexus and Gateway

## 🚀 Quick Links

### For New Users

1. Start with **[Installation](getting-started/installation.md)**
2. Follow the **[Quick Start](getting-started/quickstart.md)**
3. Learn **[Core Concepts](getting-started/concepts.md)**

### For Developers

1. Master **[Model Definition](development/models.md)**
2. Understand **[Generated Nodes](development/nodes.md)**
3. Optimize with **[Bulk Operations](development/bulk-operations.md)**

### For Production

1. Plan **[Deployment](production/deployment.md)**
2. Setup **[Monitoring](production/monitoring.md)**
3. Configure **[Backup & Recovery](production/backup.md)**

## 🎯 Key Features

### Zero Configuration

```python
from dataflow import DataFlow

db = DataFlow("postgresql://localhost/myapp")  # PostgreSQL required in alpha

@db.model
class User:
    name: str
    email: str
```

### Auto-Generated Nodes

Every model automatically gets 11 nodes:

- `UserCreateNode` - Single record creation
- `UserReadNode` - Get by ID
- `UserUpdateNode` - Update single record
- `UserDeleteNode` - Delete single record
- `UserListNode` - Query with filters
- `UserUpsertNode` - Insert or update single record
- `UserCountNode` - Count with filters
- `UserBulkCreateNode` - Bulk insert
- `UserBulkUpdateNode` - Bulk update
- `UserBulkDeleteNode` - Bulk delete
- `UserBulkUpsertNode` - Bulk insert or update

### Progressive Scaling (v0.6.0)

- **Basic**: Zero-config SQLite or any database connection
- **Intermediate**: Add caching and monitoring
- **Advanced**: Production features
- **Enterprise**: Full platform capabilities

### Database Support (v0.6.0)

- **SQL Databases**: PostgreSQL, MySQL, SQLite (full execution + schema, 11 nodes per model)
- **Document Database**: MongoDB (flexible schema, 8 specialized nodes)
- **Vector Search**: PostgreSQL pgvector (semantic search, 3 vector nodes)

### Performance

- Single operations: <1ms
- Bulk operations: 10,000+ records/sec
- Query optimization: 100-1000x improvements
- Connection pooling: Automatic management

## 📋 Version History

- **v0.6.6** - Multi-database support, progressive configuration
- **v0.6.5** - Query optimization, visual migrations
- **v0.6.0** - Auto-migrations, bulk operations
- **v0.5.0** - Initial release with model decorators

## 🆘 Getting Help

- **Documentation**: You're here!
- **Examples**: See the [examples/](../../../examples/dataflow/) directory
- **Issues**: Report on GitHub
- **Community**: Join our Discord

---

**DataFlow: From prototype to production without changing a line of code.** 🚀
