# MCP Ecosystem - Zero-Code Workflow Builder

A comprehensive example demonstrating how to build a zero-code MCP (Model Context Protocol) ecosystem using the Kailash SDK.

## 🎯 Production-Ready MCP Implementation
**Comprehensive Testing Complete**: 407 tests validate all MCP functionality
- **Unit Tests**: 391 tests covering client, server, tool execution
- **Integration Tests**: 14 tests with real MCP servers
- **E2E Tests**: 2 complete workflow scenarios
- **100% Pass Rate**: All components thoroughly tested

## Overview

The MCP ecosystem enables users to:
- Deploy workflows through a web interface without writing code
- Integrate with MCP servers for extended functionality
- Use pre-built workflow templates
- Build custom workflows with drag-and-drop
- Monitor workflow execution in real-time

## Quick Start

### 1. Navigate to the directory
```bash
cd examples/integration_examples
```

### 2. Set Python path
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)/../../src"
```

### 3. Run the ecosystem
```bash
python mcp_ecosystem_demo.py
# or use the shell script
./run_ecosystem.sh
```

### 4. Open your browser
```
http://localhost:8000
```

## Files in This Example

### Core Implementation Files
- **`mcp_ecosystem_demo.py`** - Main demo with web UI
- **`mcp_ecosystem_fixed.py`** - Full Kailash SDK integration
- **`test_mcp_fixed.py`** - Test suite for the implementation
- **`run_ecosystem.sh`** - Convenience script to run the ecosystem

### Documentation
- **`MCP_ECOSYSTEM_README.md`** - This file (consolidated documentation)
- **`TERMINAL_COMMANDS.txt`** - Copy-paste terminal commands

## Features

### 🌐 Web Interface
The dashboard provides:
- **MCP Server Status** - Real-time connection status for GitHub, Slack, and filesystem MCP servers
- **Workflow Templates** - Pre-built workflows ready to deploy
- **Visual Builder** - Drag-and-drop interface for custom workflows
- **Live Statistics** - Real-time workflow execution metrics
- **Execution Logs** - Live updates of workflow activities

### 🚀 Pre-built Workflows
1. **GitHub → Slack Notifier**
   - Monitors GitHub issues
   - Sends notifications to Slack

2. **Data Processing Pipeline**
   - Reads CSV files
   - Transforms data with Python
   - Saves as JSON

3. **AI Research Assistant**
   - Searches the web
   - Summarizes findings
   - Saves results to file

### 🎨 Visual Workflow Builder
- Drag nodes from palette to canvas
- Available nodes:
  - CSV Reader
  - Python Code
  - JSON Writer
  - GitHub Issues (MCP)
  - Slack Message (MCP)
- Build custom workflows visually
- Deploy with one click

## Frontend Technology Stack

The dashboard is built with a **lightweight, vanilla approach**:

### Technologies Used
- **HTML5** - Semantic structure embedded in Python
- **Vanilla JavaScript** - No frameworks, pure ES6+
- **CSS3** - Modern Grid/Flexbox, no CSS frameworks
- **FastAPI** - Python backend framework

### Key Features
- Native drag-and-drop API
- Fetch API for REST calls
- Real-time updates via polling
- Zero build process required
- Single file deployment

## API Endpoints

### Core Endpoints
- `GET /` - Web UI interface
- `GET /api/servers` - List MCP servers
- `POST /api/deploy/{workflow_id}` - Deploy a workflow
- `GET /api/workflows` - List deployed workflows
- `GET /api/stats` - Get execution statistics
- `POST /api/workflows/{id}/execute` - Execute a workflow

### Testing the API
```bash
# List MCP servers
curl http://localhost:8000/api/servers

# Deploy a workflow
curl -X POST http://localhost:8000/api/deploy/github-slack

# Get statistics
curl http://localhost:8000/api/stats
```

## Architecture

```
┌─────────────────────────────────────┐
│         Web UI (Browser)            │
│   - Visual workflow builder         │
│   - Real-time statistics            │
│   - Execution monitoring            │
└────────────┬────────────────────────┘
             │
┌────────────▼────────────────────────┐
│      MCP Ecosystem Gateway          │
│   - WorkflowAPIGateway base         │
│   - MCP server registry             │
│   - Workflow templates              │
│   - Execution engine                │
└────────────┬────────────────────────┘
             │
┌────────────▼────────────────────────┐
│       Kailash SDK Core              │
│   - Workflow engine                 │
│   - Node execution                  │
│   - State management                │
└─────────────────────────────────────┘
```

## Extending the Ecosystem

### Adding New MCP Servers
```python
await registry.register_server("my-mcp", {
    "command": "my-mcp-server",
    "args": ["--config", "config.json"],
    "transport": "stdio"
})

```

### Creating Workflow Templates
```python
template = {
    "name": "My Template",
    "nodes": [
        {"id": "reader", "type": "CSVReaderNode", "config": {...}},
        {"id": "processor", "type": "PythonCodeNode", "config": {...}}
    ],
    "connections": [
        {"source": "reader", "target": "processor"}
    ]
}

```

## Troubleshooting

### Import Errors
```bash
# Make sure Python path is set correctly
export PYTHONPATH="$(pwd)/../../src:${PYTHONPATH}"
```

### Port Already in Use
```bash
# Kill existing process on port 8000
lsof -ti:8000 | xargs kill -9
```

### MCP Server Connection Issues
- Ensure MCP servers are installed
- Check server commands in configuration
- Verify authentication tokens are set

## Testing the MCP Ecosystem

### Running MCP Tests
```bash
# Run all MCP tests (407 tests)
pytest tests/ -k "mcp" -v

# Unit tests only (391 tests, fast)
pytest tests/unit/ -k "mcp" -v

# Integration tests (14 tests, requires Docker)
pytest tests/integration/ -k "mcp" -v

# E2E tests (2 scenarios)
pytest tests/e2e/ -k "mcp" -v
```

### Test Coverage Areas
- **Tool Discovery**: Validates MCP server tool listing
- **Tool Execution**: Tests automatic tool calling
- **Error Handling**: Timeout and connection recovery
- **Async Contexts**: Jupyter/notebook compatibility
- **Multi-Round**: Complex tool interaction chains

## What This Demonstrates

This example showcases:
1. **Zero-Code Philosophy** - Deploy complex workflows without programming
2. **MCP Integration** - Seamless integration with Model Context Protocol
3. **Visual Programming** - Drag-and-drop workflow creation
4. **Real-Time Monitoring** - Live execution tracking and statistics
5. **Extensible Architecture** - Easy to add new nodes and servers
6. **Production Quality** - Backed by 407 comprehensive tests

## Future Enhancements

Potential improvements:
- WebSocket support for real-time updates
- Persistent workflow storage
- User authentication
- Workflow versioning
- Export/import workflows
- Integration with more MCP servers

---

Press Ctrl+C to stop the server when done.
