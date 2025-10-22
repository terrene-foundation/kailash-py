# DataFlow Documentation

Welcome to the DataFlow documentation! DataFlow is a zero-configuration database framework that progressively scales from simple prototypes to enterprise applications.

## 📚 Documentation Structure

### **Getting Started**
- **[Quick Start](getting-started/quickstart.md)** - Build your first DataFlow app in 5 minutes
- **[Core Concepts](getting-started/concepts.md)** - Understand DataFlow's architecture

### **Development Guides**
- **[Model Definition](development/models.md)** - Define database models with decorators
- **[CRUD Operations](development/crud.md)** - Create, Read, Update, Delete operations
- **[Bulk Operations](development/bulk-operations.md)** - High-performance data operations
- **[Query Patterns](development/query-patterns.md)** - Advanced filtering and aggregation
- **[Custom Development](development/custom-nodes.md)** - Create custom nodes

### **Features**
- **[Multi-Database Support](features/multi-database.md)** - PostgreSQL + SQLite (full parity), MySQL (coming soon)
- **[Query Builder](features/query-builder.md)** - MongoDB-style query building

### **Enterprise Features**
- **[Multi-Tenancy](enterprise/multi-tenant.md)** - Isolated tenant data
- **[Security & Encryption](enterprise/security.md)** - Field-level encryption, RBAC
- **[Audit & Compliance](enterprise/compliance.md)** - GDPR, HIPAA, SOC2 compliance

### **Advanced Topics**
- **[Database Optimization](advanced/database-optimization.md)** - Query optimization and indexing
- **[Connection Pooling](advanced/pooling.md)** - Connection pool configuration
- **[Read/Write Splitting](advanced/read-write-split.md)** - Database read/write splitting
- **[Monitoring](advanced/monitoring.md)** - Performance monitoring and observability
- **[Multi-Tenant](advanced/multi-tenant.md)** - Advanced multi-tenancy patterns
- **[Security](advanced/security.md)** - Advanced security patterns

### **Production Guide**
- **[Deployment](production/deployment.md)** - Deploy to production
- **[Performance](production/performance.md)** - Performance tuning and optimization
- **[Troubleshooting](production/troubleshooting.md)** - Common issues and solutions

### **Integration**
- **[Nexus Integration](integration/nexus.md)** - Multi-channel platform integration
- **[Gateway APIs](integration/gateway.md)** - Auto-generate REST APIs

### **API Reference**
- **[Node Reference](api/nodes.md)** - Complete node documentation

### **Reference Documentation**
- **[Database Dialects](reference/dialects.md)** - Database-specific features

### **Workflow Patterns**
- **[Error Handling](workflows/error-handling.md)** - Error handling patterns
- **[Node Usage](workflows/nodes.md)** - Node usage patterns
- **[Transactions](workflows/transactions.md)** - Transaction patterns

### **Framework Comparisons**
- **[DataFlow vs ORMs](comparisons/FRAMEWORK_COMPARISON.md)** - Comparison with traditional ORMs

## 🚀 Quick Links

### For New Users
1. Start with **[Quick Start](getting-started/quickstart.md)**
2. Learn **[Core Concepts](getting-started/concepts.md)**
3. Try **[Model Definition](development/models.md)**

### For Developers
1. Master **[CRUD Operations](development/crud.md)**
2. Use **[Bulk Operations](development/bulk-operations.md)**
3. Optimize with **[Query Patterns](development/query-patterns.md)**

### For Production
1. Plan **[Deployment](production/deployment.md)**
2. Setup **[Monitoring](advanced/monitoring.md)**
3. Configure **[Security](enterprise/security.md)**

## 🎯 Key Features

### Zero Configuration
```python
from dataflow import DataFlow

db = DataFlow()  # SQLite auto-created

@db.model
class User:
    name: str
    email: str
```

### Auto-Generated Nodes
Every model automatically gets 9 nodes:
- `UserCreateNode` - Single record creation
- `UserReadNode` - Get by ID
- `UserUpdateNode` - Update single record
- `UserDeleteNode` - Delete single record
- `UserListNode` - Query with filters
- `UserBulkCreateNode` - Bulk insert
- `UserBulkUpdateNode` - Bulk update
- `UserBulkDeleteNode` - Bulk delete
- `UserBulkUpsertNode` - Insert or update

### Progressive Scaling
- **Zero-config**: Just works with SQLite
- **Basic**: Add caching and monitoring
- **Intermediate**: Production features
- **Advanced**: Enterprise capabilities
- **Enterprise**: Full platform features

### Multi-Database Support
- **PostgreSQL**: Full feature support
- **MySQL**: Production ready
- **SQLite**: Perfect for development

### Performance
- Single operations: <1ms
- Bulk operations: 10,000+ records/sec
- Query optimization: 100-1000x improvements
- Connection pooling: Automatic management

## 📋 Version History

### Recent Critical Fixes

#### v0.6.3 (2025-10-22)
- **Fixed**: BulkDeleteNode safe mode validation bug
- **Fix**: Changed `not filter_conditions` to `"filter" not in validated_inputs`
- **Impact**: Safe mode now correctly validates empty filter operations
- **Verification**: Comprehensive search of 50+ files, 100+ locations checked

#### v0.6.2 (2025-10-22)
- **Fixed**: ListNode filter operators ($ne, $nin, $in, $not)
- **Fix**: Changed `if filter_dict:` to `if "filter" in kwargs:`
- **Impact**: All MongoDB-style operators now work correctly
- **Root Cause**: Python truthiness check on empty dict {} caused wrong behavior

**Upgrade Command:**
```bash
pip install --upgrade kailash-dataflow>=0.6.3
```

### Previous Releases

- **v0.6.6** - Multi-database support, progressive configuration
- **v0.6.5** - Query optimization, visual migrations
- **v0.6.0** - Auto-migrations, bulk operations
- **v0.5.0** - Initial release with model decorators

## 🆘 Getting Help

- **Documentation**: You're here!
- **Examples**: See the [examples/](../examples/) directory
- **Issues**: Report on GitHub
- **Community**: Join our Discord

---

**DataFlow: From prototype to production without changing a line of code.** 🚀
