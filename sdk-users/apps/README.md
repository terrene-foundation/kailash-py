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

### [Kaizen](kaizen/) - AI Agent Framework
Build production-ready AI agents with multi-modal processing, multi-agent coordination, and enterprise features.
**Installation:** `pip install kailash-kaizen`

**Features:**
- **Unified Architecture**: BaseAgent provides common infrastructure (87% code reduction)
- **Type-Safe Signatures**: Define inputs/outputs, framework handles validation
- **Auto-Optimization**: Automatic async execution, lazy initialization, performance tracking
- **Enterprise Ready**: Built-in error handling, logging, audit trails, memory management
- **Multi-Modal**: Vision (Ollama + OpenAI GPT-4V), Audio (Whisper)
- **Multi-Agent**: Google A2A protocol for semantic capability matching
- **Core SDK Compatible**: Seamless integration with Kailash workflows


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
pip install kailash-kaizen
```

## Getting Help

- **Documentation**: Browse the docs/ directory in each app
- **Examples**: Check the examples/ directory for runnable code
- **Community**: [GitHub Issues](https://github.com/terrene-foundation/kailash-py/issues)
- **PyPI**: [kailash](https://pypi.org/project/kailash/), [kailash-dataflow](https://pypi.org/project/kailash-dataflow/), [kailash-nexus](https://pypi.org/project/kailash-nexus/), [kailash-kaizen](https://pypi.org/project/kailash-kaizen/)
