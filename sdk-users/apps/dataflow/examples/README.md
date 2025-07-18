# DataFlow Examples

This directory contains practical examples demonstrating DataFlow capabilities.

## Available Examples

### 1. [Basic CRUD Operations](01_basic_crud.py)
Simple database operations including:
- Creating and connecting to databases
- Basic queries with MongoDB-style syntax
- Insert, update, and delete operations
- Simple aggregations

### 2. [Advanced Features](02_advanced_features.py)
Complex queries and caching patterns:
- Advanced aggregation pipelines
- Redis caching with smart invalidation
- Query optimization techniques
- Real-time data streaming
- Custom query pipelines

### 3. [Enterprise Integration](03_enterprise_integration.py)
Production-ready patterns including:
- Multi-tenant architecture
- Security and access control
- Audit logging and compliance
- Performance monitoring
- Health checks and observability

## Running the Examples

```bash
# Install DataFlow
pip install kailash-dataflow

# Run basic example
python 01_basic_crud.py

# Run with environment configuration
export DATAFLOW_DATABASE_URL="postgresql://user:pass@localhost/db"
export DATAFLOW_REDIS_URL="redis://localhost:6379"
python 02_advanced_features.py
```

## Learning Path

1. Start with `01_basic_crud.py` to understand core concepts
2. Move to `02_advanced_features.py` for production patterns
3. Study `03_enterprise_integration.py` for enterprise deployment

Each example is self-contained and includes comments explaining the concepts.
