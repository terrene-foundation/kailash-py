# Kailash App Framework Documentation

This directory contains documentation for Kailash application frameworks that are available via PyPI.

## Available Applications

### 🗄️ [DataFlow](dataflow/) - Zero-Config Database Platform
Transform database operations with MongoDB-style queries that work across any database.

**Installation:** `pip install kailash-dataflow`

**Features:**
- MongoDB-style queries across PostgreSQL, MySQL, SQLite
- Redis-powered caching with smart invalidation
- Automatic API generation with OpenAPI docs
- Enterprise features: multi-tenancy, audit logging, compliance

**Quick Start:**
```python
from dataflow import DataFlow

app = DataFlow()
users = app.query("users").where({"age": {"$gt": 18}}).limit(10)
app.start()  # API at http://localhost:8000
```

### 🔄 [Nexus](nexus/) - Multi-Channel Platform
Expose workflows through API, CLI, and MCP interfaces from a single codebase.

**Installation:** `pip install kailash-nexus`

**Features:**
- Single workflow registration → API + CLI + MCP
- Zero configuration required
- Cross-channel session management
- Enterprise orchestration with RBAC

**Quick Start:**
```python
from nexus import Nexus

app = Nexus()

@app.workflow
def process_data(data: list) -> dict:
    return {"result": sum(data)}

app.start()  # Available as API, CLI, and MCP
```

## Documentation Structure

Each application includes:
- **README.md** - Overview and quick start guide
- **docs/** - Detailed documentation and guides
- **examples/** - Runnable code examples

## Installation Options

```bash
# Install individual apps
pip install kailash-dataflow
pip install kailash-nexus

# Or install through Kailash SDK
pip install kailash[dataflow]     # DataFlow only
pip install kailash[nexus]        # Nexus only
pip install kailash[dataflow,nexus]  # Both
pip install kailash[all]          # Everything
```

## Getting Help

- **Documentation**: Browse the docs/ directory in each app
- **Examples**: Check the examples/ directory for runnable code
- **Community**: [GitHub Issues](https://github.com/terrene-foundation/kailash-py/issues)
- **PyPI**: [kailash](https://pypi.org/project/kailash/), [kailash-dataflow](https://pypi.org/project/kailash-dataflow/), [kailash-nexus](https://pypi.org/project/kailash-nexus/)
