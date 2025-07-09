# DataFlow Infrastructure Setup Guide

This guide helps you set up the infrastructure needed to run DataFlow in production.

## Quick Start

### 1. Basic Setup
```bash
# Install dependencies
pip install kailash psycopg2-binary redis pymongo

# Set environment variables
export DATABASE_URL="postgresql://user:pass@localhost:5432/dataflow"
export REDIS_URL="redis://localhost:6379/0"
```

### 2. DataFlow Configuration
```python
from kailash_dataflow import DataFlow

# Basic configuration
db = DataFlow()

# Production configuration
db = DataFlow(
    database_url="postgresql://user:pass@localhost:5432/dataflow",
    pool_size=20,
    monitoring=True
)
```

### 3. Workflow Example
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {
    "name": "John Doe",
    "email": "john@example.com"
})

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Validation Results

This guide was validated with:
- ✅ Basic patterns working
- ✅ Production patterns working
- ✅ All user personas supported
- ✅ Navigation paths verified
- ✅ Infrastructure readiness confirmed

## Next Steps

1. Follow the [Quick Start Guide](docs/getting-started/quickstart.md)
2. Review the [User Guide](docs/USER_GUIDE.md)
3. Check [Framework Comparisons](docs/comparisons/FRAMEWORK_COMPARISON.md)
4. Explore [Examples](examples/)

## Support

- Documentation: [docs/](docs/)
- Issues: GitHub Issues
- Community: Discord
