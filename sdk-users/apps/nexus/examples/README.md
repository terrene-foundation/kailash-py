# Nexus Examples

This directory contains practical examples demonstrating Nexus multi-channel capabilities.

## Available Examples

### 1. [Basic Usage](basic_usage.py)
Simple workflow registration and multi-channel deployment:
- Zero-configuration setup
- Workflow registration patterns
- Automatic API, CLI, and MCP exposure
- Cross-channel session management

### 2. [FastAPI Style Patterns](fastapi_style_patterns.py)
Migration patterns from traditional frameworks:
- FastAPI to Nexus migration
- Decorator-based workflow registration
- Advanced parameter validation
- Authentication and middleware

## Running the Examples

```bash
# Install Nexus
pip install kailash-nexus

# Run basic example
python basic_usage.py

# The workflow is now available through:
# - API: http://localhost:8000/workflows/
# - CLI: nexus list
# - MCP: Available to AI agents
```

## Multi-Channel Access

After running an example, you can access your workflows through:

### API Channel
```bash
# List workflows
curl http://localhost:8000/workflows

# Execute workflow
curl -X POST http://localhost:8000/workflows/process_data \
  -H "Content-Type: application/json" \
  -d '{"input_data": [1, 2, 3]}'
```

### CLI Channel
```bash
# List available workflows
nexus list

# Get help for a workflow
nexus run process_data --help

# Execute workflow
nexus run process_data --input-data "[1, 2, 3]"
```

### MCP Channel
AI agents can automatically discover and use your workflows as tools.

## Learning Path

1. Start with `basic_usage.py` to understand core concepts
2. Study `fastapi_style_patterns.py` for migration patterns

Each example includes detailed comments explaining the concepts and patterns.
