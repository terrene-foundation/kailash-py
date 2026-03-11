"""Resource management for Nexus MCP server.

This module implements Phase 3 of the MCP enhancement plan by providing
resource providers for workflow definitions, documentation, and data access.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from kailash.mcp_server import MCPServer
from kailash.workflow import Workflow

logger = logging.getLogger(__name__)


class NexusResourceManager:
    """Manage resources for Nexus MCP server.

    Provides access to:
    - Workflow definitions and schemas
    - Documentation and help content
    - Data resources (files, databases, etc.)
    - System information and configuration
    """

    def __init__(self, mcp_server: MCPServer, nexus_instance: Any):
        """Initialize resource manager.

        Args:
            mcp_server: The MCP server instance
            nexus_instance: The parent Nexus instance
        """
        self.server = mcp_server
        self.nexus = nexus_instance
        self._setup_default_resources()

    def _setup_default_resources(self):
        """Set up default resource providers."""

        # Workflow definitions as resources
        @self.server.resource("workflow://*")
        async def get_workflow_definition(uri: str) -> Dict[str, Any]:
            """Provide workflow definition and schema."""
            workflow_name = uri.replace("workflow://", "")

            if workflow_name not in self.nexus._workflows:
                return {
                    "uri": uri,
                    "mimeType": "application/json",
                    "error": f"Workflow '{workflow_name}' not found",
                }

            workflow = self.nexus._workflows[workflow_name]

            # Extract workflow information
            workflow_info = self._extract_workflow_info(workflow_name, workflow)

            return {
                "uri": uri,
                "mimeType": "application/json",
                "content": json.dumps(workflow_info, indent=2),
            }

        # Documentation resources
        @self.server.resource("docs://*")
        async def get_documentation(uri: str) -> Dict[str, Any]:
            """Provide documentation content."""
            doc_path = uri.replace("docs://", "")

            # Map documentation paths
            doc_content = self._get_documentation(doc_path)

            if doc_content:
                return {"uri": uri, "mimeType": "text/markdown", "content": doc_content}
            else:
                return {
                    "uri": uri,
                    "mimeType": "text/plain",
                    "error": f"Documentation '{doc_path}' not found",
                }

        # Data resources (files, configurations, etc.)
        @self.server.resource("data://*")
        async def get_data_resource(uri: str) -> Dict[str, Any]:
            """Provide data resources."""
            resource_path = uri.replace("data://", "")

            # Security check - only allow specific data access
            if not self._is_allowed_resource(resource_path):
                return {
                    "uri": uri,
                    "mimeType": "application/json",
                    "error": "Access denied to this resource",
                }

            content = self._get_data_content(resource_path)
            mime_type = self._get_mime_type(resource_path)

            if content is not None:
                return {"uri": uri, "mimeType": mime_type, "content": content}
            else:
                return {
                    "uri": uri,
                    "mimeType": "application/json",
                    "error": f"Resource '{resource_path}' not found",
                }

        # Configuration resources
        @self.server.resource("config://*")
        async def get_configuration(uri: str) -> Dict[str, Any]:
            """Provide configuration information."""
            config_key = uri.replace("config://", "")

            config_data = self._get_configuration(config_key)

            return {
                "uri": uri,
                "mimeType": "application/json",
                "content": json.dumps(config_data, indent=2),
            }

        # Help resources
        @self.server.resource("help://*")
        async def get_help(uri: str) -> Dict[str, Any]:
            """Provide context-sensitive help."""
            help_topic = uri.replace("help://", "")

            help_content = self._get_help_content(help_topic)

            return {"uri": uri, "mimeType": "text/markdown", "content": help_content}

        logger.info("Default resource providers configured")

    def _extract_workflow_info(self, name: str, workflow: Workflow) -> Dict[str, Any]:
        """Extract comprehensive workflow information.

        Args:
            name: Workflow name
            workflow: Workflow instance

        Returns:
            Dictionary with workflow information
        """
        info = {
            "name": name,
            "type": "workflow",
            "nodes": [],
            "connections": [],
            "metadata": {},
        }

        # Extract metadata if available
        if hasattr(workflow, "metadata"):
            info["metadata"] = workflow.metadata

        # Extract nodes
        if hasattr(workflow, "_nodes"):
            for node_id, node in workflow._nodes.items():
                node_info = {
                    "id": node_id,
                    "type": node.__class__.__name__,
                    "parameters": {},
                }

                # Get node parameters
                if hasattr(node, "_config"):
                    node_info["parameters"] = node._config

                info["nodes"].append(node_info)

        # Extract connections
        if hasattr(workflow, "_connections"):
            for conn in workflow._connections:
                conn_info = {
                    "source": conn.get("source"),
                    "output": conn.get("output"),
                    "target": conn.get("target"),
                    "input": conn.get("input"),
                }
                info["connections"].append(conn_info)

        # Add schema information
        info["schema"] = {
            "inputs": self._extract_workflow_inputs(workflow),
            "outputs": self._extract_workflow_outputs(workflow),
        }

        return info

    def _extract_workflow_inputs(self, workflow: Workflow) -> Dict[str, Any]:
        """Extract workflow input schema.

        Attempts to extract schema from workflow metadata. If not available,
        returns empty dict as automatic schema inference is deferred to v1.1.

        TODO v1.1: Implement automatic schema inference by analyzing:
        - Node configurations for parameter references
        - First node in workflow as entry point
        - Parameter usage patterns across workflow
        """
        inputs = {}

        # Extract from explicit metadata if available
        if hasattr(workflow, "metadata") and workflow.metadata:
            # Check for explicit parameters in metadata
            if "parameters" in workflow.metadata:
                return workflow.metadata["parameters"]

            # Check for input_schema in metadata
            if "input_schema" in workflow.metadata:
                return workflow.metadata["input_schema"]

        # Automatic inference not yet implemented - return empty dict
        # Workflows should document their inputs in metadata for now
        return inputs

    def _extract_workflow_outputs(self, workflow: Workflow) -> Dict[str, Any]:
        """Extract workflow output schema.

        Attempts to extract schema from workflow metadata. If not available,
        returns empty dict as automatic schema inference is deferred to v1.1.

        TODO v1.1: Implement automatic schema inference by analyzing:
        - Final nodes in workflow (nodes with no outgoing connections)
        - Node output configurations
        - Common output patterns
        """
        outputs = {}

        # Extract from explicit metadata if available
        if hasattr(workflow, "metadata") and workflow.metadata:
            if "output_schema" in workflow.metadata:
                return workflow.metadata["output_schema"]

        # Automatic inference not yet implemented - return empty dict
        # Workflows should document their outputs in metadata for now
        return outputs

    def _get_documentation(self, doc_path: str) -> Optional[str]:
        """Get documentation content for a given path."""
        # Predefined documentation
        docs = {
            "quickstart": """# Nexus Quick Start Guide

## Getting Started

1. **Install Nexus:**
   ```bash
   pip install kailash-nexus
   ```

2. **Create a simple workflow:**
   ```python
   from nexus import Nexus
   from kailash.workflow.builder import WorkflowBuilder

   app = Nexus()

   workflow = WorkflowBuilder()
   workflow.add_node("PythonCodeNode", "process", {
       "code": "result = {'message': 'Hello from Nexus!'}"
   })

   app.register("hello", workflow.build())
   app.start()
   ```

3. **Access your workflow:**
   - API: POST http://localhost:8000/workflows/hello
   - CLI: nexus run hello
   - MCP: Connect AI agent to ws://localhost:3001

## Key Features

- **Zero Configuration**: Works out of the box
- **Multi-Channel**: API, CLI, and MCP from one registration
- **Enterprise Ready**: Built-in auth, monitoring, and scaling
- **AI Native**: Full MCP protocol support for AI agents
""",
            "api": """# Nexus API Reference

## Endpoints

### Execute Workflow
- **POST** `/workflows/{name}`
- **Body**: JSON with workflow parameters
- **Response**: Workflow execution results

### List Workflows
- **GET** `/workflows`
- **Response**: List of registered workflows

### Health Check
- **GET** `/health`
- **Response**: Platform health status

## Authentication

When auth is enabled:
- Include `Authorization: Bearer <token>` header
- Or use API key: `X-API-Key: <key>`

## WebSocket

Real-time updates available at `ws://host:port/ws`
""",
            "mcp": """# MCP Integration Guide

## Connecting AI Agents

Nexus provides full Model Context Protocol support:

### Available Features
- **Tools**: All workflows exposed as executable tools
- **Resources**: Access workflow definitions and docs
- **Prompts**: Pre-configured templates (coming soon)

### Connection
```
ws://localhost:3001
```

### Authentication
Include API key in connection headers when auth is enabled.

### Tool Discovery
Send `tools/list` to discover available workflows.

### Resource Access
- `workflow://<name>` - Workflow definitions
- `docs://<topic>` - Documentation
- `config://<key>` - Configuration
""",
        }

        return docs.get(doc_path)

    def _get_data_content(self, resource_path: str) -> Optional[str]:
        """Get data content for a resource path."""
        # Example: Handle specific data resources
        if resource_path == "examples/sample.json":
            return json.dumps(
                {"example": "data", "timestamp": "2024-01-01T00:00:00Z"}, indent=2
            )

        # Try to read from file system (with security checks)
        safe_base = os.path.abspath("./data")
        requested_path = os.path.abspath(os.path.join(safe_base, resource_path))

        # Security: Ensure path is within safe directory
        if requested_path.startswith(safe_base) and os.path.exists(requested_path):
            try:
                with open(requested_path, "r") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Error reading resource {resource_path}: {e}")

        return None

    def _get_mime_type(self, resource_path: str) -> str:
        """Determine MIME type for a resource."""
        ext = os.path.splitext(resource_path)[1].lower()

        mime_types = {
            ".json": "application/json",
            ".xml": "application/xml",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".py": "text/x-python",
            ".yaml": "application/x-yaml",
            ".yml": "application/x-yaml",
        }

        return mime_types.get(ext, "application/octet-stream")

    def _is_allowed_resource(self, resource_path: str) -> bool:
        """Check if a resource path is allowed for access."""
        # Disallow access to sensitive paths
        forbidden_patterns = [
            "..",  # Directory traversal
            "/etc/",  # System configs
            "/proc/",  # Process info
            ".env",  # Environment files
            "secret",  # Anything with 'secret'
            "password",  # Anything with 'password'
            "key",  # Anything with 'key'
        ]

        path_lower = resource_path.lower()
        for pattern in forbidden_patterns:
            if pattern in path_lower:
                return False

        return True

    def _get_configuration(self, config_key: str) -> Dict[str, Any]:
        """Get configuration for a given key."""
        configs = {
            "platform": {
                "name": "Kailash Nexus",
                "version": "1.0.0",
                "api_port": self.nexus._api_port,
                "mcp_port": self.nexus._mcp_port,
                "features": {
                    "auth": self.nexus._enable_auth,
                    "monitoring": self.nexus._enable_monitoring,
                    "discovery": self.nexus._enable_discovery,
                    "transports": self.nexus._get_enabled_transports(),
                },
            },
            "workflows": {
                "registered": list(self.nexus._workflows.keys()),
                "count": len(self.nexus._workflows),
            },
            "limits": {
                "rate_limit": self.nexus.rate_limit_config,
                "max_workflows": 1000,
                "max_connections": 10000,
            },
        }

        return configs.get(
            config_key, {"error": f"Unknown configuration key: {config_key}"}
        )

    def _get_help_content(self, help_topic: str) -> str:
        """Get help content for a topic."""
        help_topics = {
            "getting-started": """# Getting Started with Nexus

1. Create a Nexus instance
2. Register your workflows
3. Start the platform
4. Access via API, CLI, or MCP

Need more help? Check:
- docs://quickstart - Quick start guide
- docs://api - API reference
- docs://mcp - MCP integration
""",
            "workflows": """# Working with Workflows

Workflows are the core of Nexus. Each workflow:
- Can contain multiple nodes
- Processes data through connections
- Is accessible via all channels

To see available workflows:
- API: GET /workflows
- MCP: Send tools/list
- Resources: workflow://<name>
""",
            "troubleshooting": """# Troubleshooting

Common issues:

**Port already in use:**
- Change ports: `Nexus(api_port=8080, mcp_port=3002)`

**Workflow not found:**
- Check registration: `app.register("name", workflow)`
- Ensure workflow is built: `workflow.build()`

**Connection refused:**
- Check if Nexus is running: `app.start()`
- Verify firewall settings
""",
        }

        content = help_topics.get(help_topic)
        if content:
            return content

        # Default help
        return f"""# Help: {help_topic}

No specific help available for '{help_topic}'.

Available help topics:
- help://getting-started
- help://workflows
- help://troubleshooting

Or check documentation:
- docs://quickstart
- docs://api
- docs://mcp
"""

    def register_custom_resource(self, pattern: str, handler: Any):
        """Register a custom resource handler.

        Args:
            pattern: URI pattern (e.g., "custom://*")
            handler: Async function to handle resource requests
        """
        self.server.resource(pattern)(handler)
        logger.info(f"Registered custom resource handler for {pattern}")
