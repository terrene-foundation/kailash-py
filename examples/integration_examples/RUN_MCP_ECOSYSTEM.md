# Running the MCP Ecosystem Example

## Quick Start

1. **Navigate to the examples directory:**
```bash
cd examples/integration_examples
```

2. **Set up Python path (required):**
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)/../../src"
```

3. **Run the ecosystem demo:**
```bash
python mcp_ecosystem_demo.py
```

4. **Open your browser to:**
```
http://localhost:8000
```

## What You'll See

### Web Interface
- **MCP Servers Panel**: Shows 3 connected MCP servers (github-mcp, slack-mcp, filesystem-mcp)
- **Workflow Templates**: 3 pre-built workflows you can deploy with one click
- **Visual Builder**: Placeholder for future drag-and-drop interface

### Available Workflows
1. **GitHub → Slack Notifier**: Monitor GitHub issues and send Slack notifications
2. **Data Processing Pipeline**: ETL workflow (CSV → Transform → JSON)
3. **AI Research Assistant**: Web search → Summarize → Save

## API Endpoints

- `GET /` - Web UI
- `GET /api/servers` - List MCP servers
- `POST /api/deploy/{workflow_id}` - Deploy a workflow
- `GET /api/workflows` - List deployed workflows
- `GET /docs` - FastAPI documentation

## Testing the API

Once the server is running, you can test it with curl:

```bash
# List MCP servers
curl http://localhost:8000/api/servers

# Deploy a workflow
curl -X POST http://localhost:8000/api/deploy/github-slack

# List deployed workflows
curl http://localhost:8000/api/workflows
```

## Complete Terminal Session Example

```bash
# From the kailash_python_sdk root directory
cd examples/integration_examples

# Set Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/../../src"

# Run the server
python mcp_ecosystem_demo.py

# In another terminal, test the API
curl http://localhost:8000/api/servers
```

## Troubleshooting

If you get import errors:
```bash
# Make sure you're in the right directory
pwd  # Should show .../examples/integration_examples

# Set the Python path correctly
export PYTHONPATH="$(pwd)/../../src:${PYTHONPATH}"

# Try again
python mcp_ecosystem_demo.py
```

## What This Demonstrates

This example shows how to build a zero-code MCP ecosystem using Kailash SDK:
- Visual workflow deployment interface
- Integration with MCP servers
- One-click workflow deployment
- REST API for programmatic access
- Template-based workflow creation

Press Ctrl+C to stop the server when done.