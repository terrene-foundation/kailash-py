# Kailash Nexus - Zero Configuration Workflow Orchestration

[![PyPI version](https://badge.fury.io/py/kailash-nexus.svg)](https://badge.fury.io/py/kailash-nexus)
[![Python Support](https://img.shields.io/pypi/pyversions/kailash-nexus.svg)](https://pypi.org/project/kailash-nexus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A truly zero-configuration platform that allows enterprise users to focus on creating workflows without learning infrastructure complexity.

## Installation

```bash
pip install kailash-nexus
```

## What is Nexus?

Nexus embodies the zero-config philosophy: **just create `Nexus()` and start!**

- **Zero Parameters**: No configuration files, environment variables, or setup required
- **Progressive Enhancement**: Start simple, add features as needed
- **Multi-Channel**: API, CLI, and MCP access unified
- **Simple Registration**: Use `app.register(name, workflow)` to add workflows
- **Enterprise Ready**: Built-in auth, monitoring, and rate limiting

## Quick Start

```python
from nexus import Nexus

# That's it! Zero configuration needed.
app = Nexus()
app.start()
```

## Core Features

### 1. Zero Configuration Initialization
```python
from nexus import Nexus

# Create and start with zero parameters
app = Nexus()

# Optional: Configure enterprise features
app = Nexus(
    api_port=8000,      # Default: 8000
    mcp_port=3001,      # Default: 3001
    enable_auth=False,  # Default: False
    enable_monitoring=False,  # Default: False
    rate_limit=None,    # Default: None
    auto_discovery=True # Default: True
)

app.start()

# Check health
print(app.health_check())
```

### 2. Automatic Workflow Discovery
Place workflows in your directory using these patterns:
- `workflows/*.py`
- `*.workflow.py`
- `workflow_*.py`
- `*_workflow.py`

Example workflow file (`my_workflow.py`):
```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "agent", {"model": "gpt-4"})
```

Nexus automatically discovers and registers it!

### 3. Workflow Registration
Register workflows with the simple `register()` method:

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

# Create a workflow
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("PythonCodeNode", "process", {"code": "result = len(data)"})
workflow.add_connection("reader", "data", "process", "data")

# Register the workflow
app.register("data_processor", workflow.build())

app.start()
```

### 4. Multi-Channel Access
Your workflows are automatically available via:

- **REST API**: `http://localhost:8000/workflows/{name}`
- **CLI**: `nexus run {name}`
- **MCP**: Model Context Protocol integration

### 5. Smart Defaults
- API server on port 8000 (auto-finds available port)
- MCP server on port 3001 (auto-finds available port)
- Health endpoint at `/health`
- Auto CORS and documentation enabled
- Graceful error handling and isolation

## Architecture

Nexus is built as a separate application using Kailash SDK components:

```
┌─ kailash_nexus_app/
├── core.py          # Zero-config wrapper around SDK
├── discovery.py     # Auto-discovery of workflows
├── plugins.py       # Progressive enhancement system
├── channels.py      # Multi-channel configuration
└── __init__.py      # Simple Nexus class
```

### Key Principles

1. **SDK as Building Blocks**: Uses existing Kailash SDK without modification
2. **Zero Config by Default**: No parameters required for basic usage
3. **Progressive Enhancement**: Add complexity only when needed
4. **Smart Defaults**: Everything just works out of the box

## Plugin System

Built-in plugins include:

- **Auth Plugin**: Authentication and authorization
- **Monitoring Plugin**: Performance metrics and health checks
- **Rate Limit Plugin**: Request rate limiting

Create custom plugins:
```python
from kailash_nexus_app.plugins import NexusPlugin

class MyPlugin(NexusPlugin):
    @property
    def name(self):
        return "my_plugin"

    @property
    def description(self):
        return "My custom plugin"

    def apply(self, nexus_instance):
        # Enhance nexus functionality
        nexus_instance.my_feature = True
```

## Testing

Comprehensive test suite with 52 tests:

```bash
# Run all tests
python -m pytest tests/ -v

# Unit tests only (45 tests)
python -m pytest tests/unit/ -v

# Integration tests only (7 tests)
python -m pytest tests/integration/ -v
```

## Use Cases

### Data Scientists
```python
# Just start and focus on workflows
from nexus import Nexus
app = Nexus()
app.start()
```

### DevOps Engineers
```python
# Add production features progressively
from nexus import Nexus

app = Nexus(enable_auth=True, enable_monitoring=True)
app.start()
```

### AI Developers
```python
# Register AI workflows automatically
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

# Manual registration
workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "ai", {"model": "gpt-4"})
app.register("ai-assistant", workflow.build())

app.start()
```

## Comparison with v1

| Feature | Nexus v1 | Nexus v2 (This Implementation) |
|---------|----------|--------------------------------|
| Configuration | 200+ lines | 0 lines |
| Startup | Complex setup | `Nexus().start()` |
| Channels | Manual config | Auto-configured |
| Discovery | None | Automatic |
| Enhancement | Built-in complexity | Progressive plugins |

## Implementation Status

✅ **Core Features Implemented (v1.0)**:
- Zero-config initialization
- Workflow discovery and auto-registration
- Plugin system for progressive enhancement
- Channel configuration with smart defaults
- Comprehensive test suite (248 tests passing)
- Event logging system (retrieve with `get_events()`)
- Metadata-based workflow schema extraction
- Multi-channel workflow registration (API + CLI + MCP)

🔧 **Recent Fixes (v1.1.1)**:
- Fixed 10 stub implementations (3 CRITICAL, 4 HIGH, 3 MEDIUM)
- Removed redundant channel initialization methods
- Updated event broadcasting with honest v1.0 capabilities
- Fixed resource configuration AttributeError
- Improved error handling across plugin and discovery systems

⏳ **Planned for v1.1** (see ROADMAP.md):
- Real-time event broadcasting via WebSocket/SSE
- Automatic workflow schema inference from nodes
- Enhanced MCP resource capabilities
- Advanced enterprise monitoring features

This implementation demonstrates the true zero-config vision: a platform where enterprise users can focus on creating workflows without infrastructure complexity, with clear distinction between current (v1.0) and planned (v1.1) capabilities.
