# Multi-Channel Usage Guide

Master Nexus's revolutionary multi-channel architecture: single workflow registration automatically creates API endpoints, CLI commands, and MCP tools.

## Overview

This guide demonstrates Nexus's core innovation: **workflow-native orchestration** where registering one workflow instantly provides three access methods:

- **REST API** - HTTP endpoints with OpenAPI documentation
- **CLI Interface** - Interactive command-line tools
- **MCP Protocol** - AI agent tool discovery and execution

## Revolutionary Architecture

Traditional platforms require separate implementations for each interface. Nexus automatically generates all three:

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

# Build once
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "fetch_data", {
    "url": "https://api.github.com/users/octocat",
    "method": "GET"
})

# Register once → Available everywhere
app.register("github-user", workflow)
app.start()

# Now available as:
# 1. REST API: POST /workflows/github-user/execute
# 2. CLI: nexus run github-user
# 3. MCP: AI agents discover as "github-user" tool
```

## REST API Channel

### Basic API Usage

Every registered workflow automatically gets REST endpoints:

```bash
# Execute workflow
curl -X POST http://localhost:8000/workflows/github-user/execute \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"username": "octocat"}}'

# Get workflow schema
curl http://localhost:8000/workflows/github-user/schema

# Get OpenAPI documentation
curl http://localhost:8000/docs

# Health check
curl http://localhost:8000/health
```

### Advanced API Features

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus(api_port=8001)

# Advanced workflow with multiple inputs
workflow = WorkflowBuilder()

# User input validation
workflow.add_node("PythonCodeNode", "validate_input", {
    "code": """
def validate_user_input(data):
    username = data.get('username', '').strip()
    if not username:
        return {'error': 'Username is required', 'valid': False}
    if len(username) > 50:
        return {'error': 'Username too long', 'valid': False}
    return {'username': username, 'valid': True}
""",
    "function_name": "validate_user_input"
})

# GitHub API call
workflow.add_node("HTTPRequestNode", "fetch_user", {
    "url": "https://api.github.com/users/{username}",
    "method": "GET",
    "headers": {"Accept": "application/vnd.github.v3+json"}
})

# Data transformation
workflow.add_node("PythonCodeNode", "transform_response", {
    "code": """
def transform_user_data(data):
    if 'login' not in data:
        return {'error': 'User not found'}

    return {
        'user': {
            'username': data.get('login'),
            'name': data.get('name'),
            'bio': data.get('bio'),
            'public_repos': data.get('public_repos', 0),
            'followers': data.get('followers', 0),
            'created_at': data.get('created_at'),
            'avatar_url': data.get('avatar_url')
        },
        'success': True
    }
""",
    "function_name": "transform_user_data"
})

app.register("enhanced-github-user", workflow)
app.start()
```

### Testing API Endpoints

```python
import requests
import json

def test_api_workflow():
    """Test the enhanced GitHub user workflow via API"""

    # Test valid user
    response = requests.post(
        "http://localhost:8001/workflows/enhanced-github-user/execute",
        json={"inputs": {"username": "octocat"}}
    )

    if response.status_code == 200:
        result = response.json()
        print(f"✅ API Success: {result.get('user', {}).get('name', 'Unknown')}")
    else:
        print(f"❌ API Error: {response.status_code}")

    # Test invalid user
    response = requests.post(
        "http://localhost:8001/workflows/enhanced-github-user/execute",
        json={"inputs": {"username": ""}}
    )

    result = response.json()
    if 'error' in result:
        print(f"✅ Validation working: {result['error']}")

# Run API tests
test_api_workflow()
```

## CLI Interface Channel

### Basic CLI Usage

Workflows become interactive CLI commands:

```bash
# Execute workflow interactively
nexus run github-user

# Execute with parameters
nexus run github-user --username octocat

# List available workflows
nexus list

# Get workflow information
nexus info github-user

# Get help
nexus --help
```

### CLI Implementation Example

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

# CLI-friendly workflow
workflow = WorkflowBuilder()

# Interactive parameter collection
workflow.add_node("PythonCodeNode", "collect_params", {
    "code": """
def collect_cli_params(data):
    import os

    # Get from CLI args or environment
    username = data.get('username') or os.getenv('GITHUB_USERNAME')

    if not username:
        # In real CLI, this would prompt user
        username = input('Enter GitHub username: ')

    return {
        'username': username,
        'source': 'cli_input'
    }
""",
    "function_name": "collect_cli_params"
})

# Process and display results
workflow.add_node("PythonCodeNode", "display_results", {
    "code": """
def display_cli_results(data):
    user = data.get('user', {})

    # CLI-friendly output formatting
    output = f'''
GitHub User Information:
-----------------------
Username: {user.get('username', 'N/A')}
Name: {user.get('name', 'N/A')}
Bio: {user.get('bio', 'No bio available')}
Public Repos: {user.get('public_repos', 0)}
Followers: {user.get('followers', 0)}
Created: {user.get('created_at', 'N/A')}
'''

    print(output)
    return {'cli_output': output, 'displayed': True}
""",
    "function_name": "display_cli_results"
})

app.register("cli-github-user", workflow)
app.start()
```

### CLI Configuration

```python
# Configure CLI behavior
app.cli.interactive = True          # Enable interactive prompts
app.cli.auto_complete = True        # Enable tab completion
app.cli.progress_bars = True        # Show progress indicators
app.cli.colored_output = True       # Colorized terminal output
```

## MCP Protocol Channel

### AI Agent Integration

Workflows automatically become discoverable tools for AI agents:

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus(mcp_port=3001)

# AI-agent friendly workflow
workflow = WorkflowBuilder()

# Add metadata for AI discovery
workflow.add_metadata({
    "name": "github_user_lookup",
    "description": "Look up GitHub user information by username",
    "parameters": {
        "username": {
            "type": "string",
            "description": "GitHub username to look up",
            "required": True
        }
    },
    "returns": {
        "type": "object",
        "description": "GitHub user profile information"
    }
})

# Agent-optimized data processing
workflow.add_node("PythonCodeNode", "agent_format", {
    "code": """
def format_for_agents(data):
    user = data.get('user', {})

    # Structured data that AI agents can easily process
    agent_response = {
        'tool_name': 'github_user_lookup',
        'success': True,
        'data': {
            'username': user.get('username'),
            'display_name': user.get('name'),
            'description': user.get('bio'),
            'metrics': {
                'repositories': user.get('public_repos', 0),
                'followers': user.get('followers', 0)
            },
            'profile_url': f"https://github.com/{user.get('username', '')}",
            'avatar_url': user.get('avatar_url')
        },
        'metadata': {
            'retrieved_at': __import__('datetime').datetime.now().isoformat(),
            'source': 'github_api'
        }
    }

    return agent_response
""",
    "function_name": "format_for_agents"
})

app.register("ai-github-lookup", workflow)
app.start()
```

### MCP Tool Discovery

```python
# MCP server automatically exposes tools
def get_available_mcp_tools():
    """AI agents can discover available tools"""
    return {
        "tools": [
            {
                "name": "ai-github-lookup",
                "description": "Look up GitHub user information",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "GitHub username"
                        }
                    },
                    "required": ["username"]
                }
            }
        ]
    }

# AI agents can execute tools
def execute_mcp_tool(tool_name, parameters):
    """Execute MCP tool programmatically"""
    import requests

    response = requests.post(
        f"http://localhost:3001/tools/{tool_name}/execute",
        json={"parameters": parameters}
    )

    return response.json()
```

## Cross-Channel Session Management

### Unified Sessions

Sessions work across all channels seamlessly:

```python
from nexus import Nexus

app = Nexus()

# Create cross-channel session
session_id = app.create_session(channel="api")

# Use session in API
api_result = requests.post(
    "http://localhost:8000/workflows/github-user/execute",
    json={"inputs": {"username": "octocat"}},
    headers={"X-Session-ID": session_id}
)

# Same session available in CLI
# nexus run github-user --session session_id

# Same session available in MCP
mcp_result = execute_mcp_tool("ai-github-lookup", {
    "username": "octocat",
    "session_id": session_id
})

# Sync session data across channels
session_data = app.sync_session(session_id, "mcp")
print(f"Session data: {session_data}")
```

### Session State Persistence

```python
# Sessions persist workflow state across channels
def demonstrate_session_persistence():
    """Show how sessions maintain state across channels"""

    # Start workflow via API
    api_response = requests.post(
        "http://localhost:8000/workflows/multi-step-process/execute",
        json={
            "inputs": {"step": 1, "data": "initial"},
            "session_id": "demo-session"
        }
    )

    # Continue via CLI (session state preserved)
    # nexus continue multi-step-process --session demo-session --step 2

    # Complete via MCP (full state available)
    final_result = execute_mcp_tool("multi-step-process", {
        "step": 3,
        "session_id": "demo-session"
    })

    return final_result
```

## Real-Time Event Broadcasting

### Cross-Channel Events

Events broadcast to all active channels:

```python
from nexus import Nexus

app = Nexus()

# Register event listeners
@app.on_workflow_started
def on_workflow_start(event):
    """Broadcast workflow start to all channels"""
    app.broadcast_event("WORKFLOW_STARTED", {
        "workflow_id": event.workflow_id,
        "started_at": event.timestamp,
        "channel": event.channel
    })

@app.on_workflow_completed
def on_workflow_complete(event):
    """Broadcast completion to all channels"""
    app.broadcast_event("WORKFLOW_COMPLETED", {
        "workflow_id": event.workflow_id,
        "result": event.result,
        "duration": event.duration,
        "channel": event.channel
    })

# Real-time updates across channels
def setup_real_time_monitoring():
    """Set up real-time monitoring across all channels"""

    # API clients get WebSocket updates
    # CLI shows progress bars
    # MCP agents receive status notifications

    monitoring_workflow = WorkflowBuilder()

    monitoring_workflow.add_node("PythonCodeNode", "monitor_progress", {
        "code": """
def track_progress(data):
    import time

    # Simulate long-running process
    for i in range(5):
        progress = (i + 1) * 20

        # Broadcast progress to all channels
        app.broadcast_event('PROGRESS_UPDATE', {
            'percentage': progress,
            'step': f'Processing step {i+1}/5',
            'timestamp': time.time()
        })

        time.sleep(1)

    return {'completed': True, 'steps': 5}
""",
        "function_name": "track_progress"
    })

    app.register("monitored-process", monitoring_workflow)
```

## Performance Optimization

### Channel-Specific Optimizations

```python
from nexus import Nexus

app = Nexus()

# Optimize for different channel characteristics
app.api.response_compression = True      # Compress API responses
app.api.request_timeout = 30            # API timeout
app.api.max_concurrent_requests = 100   # API concurrency

app.cli.streaming_output = True         # Stream CLI output
app.cli.progress_indicators = True      # Show progress
app.cli.command_history = True          # Command history

app.mcp.tool_caching = True            # Cache MCP tool results
app.mcp.batch_operations = True        # Batch MCP calls
app.mcp.async_execution = True         # Async MCP execution
```

### Multi-Channel Load Balancing

```python
# Configure load balancing across channels
app.configure_load_balancing({
    "api": {
        "instances": 3,
        "health_check": "/health"
    },
    "cli": {
        "instances": 2,
        "session_affinity": True
    },
    "mcp": {
        "instances": 2,
        "tool_discovery_cache": 300  # 5 minutes
    }
})
```

## Testing Multi-Channel Workflows

### Comprehensive Testing Strategy

```python
import requests
import subprocess
import asyncio

class MultiChannelTester:
    """Test workflows across all channels"""

    def __init__(self, nexus_app):
        self.app = nexus_app

    def test_api_channel(self, workflow_name, inputs):
        """Test via REST API"""
        response = requests.post(
            f"http://localhost:8000/workflows/{workflow_name}/execute",
            json={"inputs": inputs}
        )
        return response.json()

    def test_cli_channel(self, workflow_name, params):
        """Test via CLI"""
        cmd = ["nexus", "run", workflow_name] + params
        result = subprocess.run(cmd, capture_output=True, text=True)
        return {"stdout": result.stdout, "stderr": result.stderr}

    def test_mcp_channel(self, tool_name, parameters):
        """Test via MCP protocol"""
        return execute_mcp_tool(tool_name, parameters)

    def test_all_channels(self, workflow_name, test_data):
        """Test same workflow across all channels"""
        results = {}

        # API test
        results["api"] = self.test_api_channel(
            workflow_name,
            test_data["inputs"]
        )

        # CLI test
        results["cli"] = self.test_cli_channel(
            workflow_name,
            test_data["cli_params"]
        )

        # MCP test
        results["mcp"] = self.test_mcp_channel(
            workflow_name,
            test_data["inputs"]
        )

        return results

# Usage
tester = MultiChannelTester(app)
test_results = tester.test_all_channels("github-user", {
    "inputs": {"username": "octocat"},
    "cli_params": ["--username", "octocat"]
})

print(f"API Result: {test_results['api']}")
print(f"CLI Result: {test_results['cli']}")
print(f"MCP Result: {test_results['mcp']}")
```

## Best Practices

### 1. Channel-Agnostic Design

```python
# Design workflows that work well across all channels
workflow.add_node("PythonCodeNode", "universal_output", {
    "code": """
def format_universal_output(data):
    # Structure data for all channels
    return {
        'api_response': data,           # For REST API
        'cli_display': format_cli(data),  # For CLI
        'mcp_tool_result': format_mcp(data)  # For MCP
    }
"""
})
```

### 2. Progressive Enhancement

```python
# Start simple, add channel-specific features
app = Nexus()

# Basic registration works everywhere
app.register("basic-workflow", workflow)

# Add API-specific features
app.api.enable_docs = True
app.api.enable_metrics = True

# Add CLI-specific features
app.cli.enable_autocomplete = True
app.cli.enable_history = True

# Add MCP-specific features
app.mcp.enable_tool_discovery = True
app.mcp.enable_streaming = True
```

### 3. Error Handling Across Channels

```python
# Consistent error handling for all channels
workflow.add_node("PythonCodeNode", "handle_errors", {
    "code": """
def universal_error_handler(data):
    if 'error' in data:
        return {
            'api_error': {'status': 'error', 'message': data['error']},
            'cli_error': f"Error: {data['error']}",
            'mcp_error': {'error': True, 'details': data['error']}
        }
    return data
"""
})
```

## Next Steps

Master advanced multi-channel concepts:

1. **[Session Management](session-management.md)** - Deep dive into cross-channel sessions
2. **[Enterprise Features](enterprise-features.md)** - Production multi-channel deployment
3. **[Performance Guide](../technical/performance-guide.md)** - Optimize channel performance
4. **[Integration Guide](../technical/integration-guide.md)** - Integrate with external systems

## Key Takeaways

✅ **Single Registration** → Three interfaces automatically
✅ **Cross-Channel Sessions** → Unified state management
✅ **Real-Time Events** → Live updates across all channels
✅ **Channel Optimization** → Tailored performance per interface
✅ **Universal Testing** → Validate all channels consistently

Nexus's multi-channel architecture revolutionizes workflow deployment by automatically generating REST APIs, CLI tools, and AI agent interfaces from a single workflow definition.
