# Zero-Code MCP Ecosystem Design for Kailash SDK

## Overview

This document outlines how to implement a zero-code MCP (Model Context Protocol) ecosystem using the Kailash SDK, similar to the mcp-gateway project but leveraging Kailash's workflow and node architecture.

## Architecture

### 1. Core Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        MCP Ecosystem UI                          │
│  (Visual Workflow Builder with MCP Node Library)                │
└────────────────────┬────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────────┐
│                    Kailash MCP Gateway                          │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │ MCP Registry │  │ Workflow API │  │ Resource Manager   │   │
│  │              │  │              │  │                    │   │
│  │ - Tools      │  │ - Execute    │  │ - Storage          │   │
│  │ - Resources  │  │ - Monitor    │  │ - Versioning       │   │
│  │ - Prompts    │  │ - Deploy     │  │ - Access Control   │   │
│  └──────────────┘  └──────────────┘  └────────────────────┘   │
└────────────────────┬────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────────┐
│                    MCP Server Network                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │ GitHub MCP  │  │ Slack MCP   │  │ Custom MCP  │  ...      │
│  │ Server      │  │ Server      │  │ Servers     │           │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Implementation Strategy

#### Phase 1: Enhanced MCP Gateway

```python
# mcp_ecosystem_gateway.py
from kailash.api.gateway import WorkflowGateway
from kailash.api.mcp_integration import MCPIntegration
from kailash.nodes.mcp import MCPClient, MCPServer, MCPResource
from fastapi import FastAPI, WebSocket
from typing import Dict, List, Any
import asyncio

class MCPEcosystemGateway(WorkflowGateway):
    """Zero-code MCP ecosystem gateway"""

    def __init__(self, port: int = 8000):
        super().__init__(port)
        self.mcp_registry = MCPRegistry()
        self.workflow_builder = VisualWorkflowBuilder()
        self.resource_manager = ResourceManager()

    async def register_mcp_server(self, config: Dict[str, Any]):
        """Register an MCP server with auto-discovery"""
        server_id = config["id"]

        # Auto-discover capabilities
        client = MCPClient(
            server_command=config["command"],
            server_args=config.get("args", []),
            transport=config.get("transport", "stdio")
        )

        # List available tools, resources, and prompts
        tools = await client.list_tools()
        resources = await client.list_resources()
        prompts = await client.list_prompts()

        # Register in ecosystem
        self.mcp_registry.register_server(server_id, {
            "config": config,
            "tools": tools,
            "resources": resources,
            "prompts": prompts,
            "client": client
        })

        # Create workflow nodes for each capability
        for tool in tools:
            self._create_tool_node(server_id, tool)

    def _create_tool_node(self, server_id: str, tool: Dict):
        """Create a reusable node for an MCP tool"""
        from kailash.nodes.base import Node

        class DynamicMCPToolNode(Node):
            def __init__(self):
                super().__init__()
                self.server_id = server_id
                self.tool_name = tool["name"]

            def get_parameters(self):
                # Convert MCP tool schema to node parameters
                return self._schema_to_parameters(tool.get("inputSchema", {}))

            async def run(self, **kwargs):
                client = self.mcp_registry.get_client(server_id)
                result = await client.call_tool(self.tool_name, kwargs)
                return {"result": result}

        # Register node in catalog
        self.workflow_builder.register_node(
            f"{server_id}.{tool['name']}",
            DynamicMCPToolNode,
            metadata={
                "category": "MCP Tools",
                "server": server_id,
                "description": tool.get("description", "")
            }
        )
```

#### Phase 2: Visual Workflow Builder

```python
# visual_workflow_builder.py
from kailash.workflow import Workflow
from kailash.nodes.base import Node
from typing import Dict, List, Any
import json

class VisualWorkflowBuilder:
    """Visual workflow builder with MCP integration"""

    def __init__(self):
        self.node_catalog = {}
        self.workflow_templates = {}

    def create_workflow_from_json(self, workflow_def: Dict) -> Workflow:
        """Create workflow from visual builder JSON"""
        workflow = Workflow(workflow_def["id"])

        # Add nodes
        for node_def in workflow_def["nodes"]:
            node_class = self.node_catalog[node_def["type"]]
            node = node_class(**node_def.get("config", {}))
            workflow.add_node(node_def["id"], node)

        # Add connections
        for conn in workflow_def["connections"]:
            workflow.connect(
                conn["from"],
                conn["to"],
                mapping=conn.get("mapping", {})
            )

        return workflow

    def export_workflow_template(self, workflow: Workflow) -> Dict:
        """Export workflow as reusable template"""
        return {
            "id": workflow.id,
            "name": workflow.name,
            "nodes": [
                {
                    "id": node_id,
                    "type": node.__class__.__name__,
                    "config": node.config,
                    "position": {"x": 0, "y": 0}  # For UI
                }
                for node_id, node in workflow.nodes.items()
            ],
            "connections": [
                {
                    "from": edge.source,
                    "to": edge.target,
                    "mapping": edge.metadata.get("mapping", {})
                }
                for edge in workflow.edges
            ]
        }
```

#### Phase 3: MCP Tool Marketplace

```python
# mcp_marketplace.py
class MCPMarketplace:
    """Marketplace for MCP tools and workflows"""

    def __init__(self, gateway: MCPEcosystemGateway):
        self.gateway = gateway
        self.marketplace_db = MarketplaceDB()

    async def publish_workflow(self, workflow: Workflow, metadata: Dict):
        """Publish workflow to marketplace"""
        template = self.gateway.workflow_builder.export_workflow_template(workflow)

        # Add marketplace metadata
        marketplace_entry = {
            "template": template,
            "metadata": {
                **metadata,
                "author": metadata.get("author"),
                "version": metadata.get("version", "1.0.0"),
                "description": metadata.get("description"),
                "tags": metadata.get("tags", []),
                "mcp_servers": self._extract_mcp_servers(workflow),
                "preview": self._generate_preview(workflow)
            }
        }

        await self.marketplace_db.publish(marketplace_entry)

    async def install_workflow(self, workflow_id: str) -> Workflow:
        """Install workflow from marketplace"""
        entry = await self.marketplace_db.get(workflow_id)

        # Check MCP server requirements
        for server in entry["metadata"]["mcp_servers"]:
            if not self.gateway.mcp_registry.has_server(server):
                await self._auto_install_mcp_server(server)

        # Create workflow
        return self.gateway.workflow_builder.create_workflow_from_json(
            entry["template"]
        )
```

### 3. Zero-Code Features

#### A. Drag-and-Drop Interface

```javascript
// Frontend component example
const MCPWorkflowBuilder = () => {
    const [nodes, setNodes] = useState([]);
    const [connections, setConnections] = useState([]);

    const onDrop = (event) => {
        const nodeType = event.dataTransfer.getData('nodeType');
        const position = { x: event.clientX, y: event.clientY };

        // Add node to canvas
        const newNode = {
            id: generateId(),
            type: nodeType,
            position: position,
            data: getNodeDefaults(nodeType)
        };

        setNodes([...nodes, newNode]);
    };

    const exportWorkflow = () => {
        return {
            nodes: nodes,
            connections: connections
        };
    };

    return (
        <div className="workflow-builder">
            <NodePalette />
            <Canvas
                nodes={nodes}
                connections={connections}
                onDrop={onDrop}
            />
            <PropertiesPanel selectedNode={selectedNode} />
        </div>
    );
};
```

#### B. Auto-Discovery UI

```python
# auto_discovery_ui.py
class MCPAutoDiscovery:
    """Auto-discover and register MCP servers"""

    async def scan_for_servers(self) -> List[Dict]:
        """Scan for available MCP servers"""
        servers = []

        # Check known locations
        # 1. NPM global packages
        npm_servers = await self._scan_npm_globals()

        # 2. Python packages
        python_servers = await self._scan_python_packages()

        # 3. Docker containers
        docker_servers = await self._scan_docker_containers()

        # 4. Running processes
        process_servers = await self._scan_running_processes()

        return servers + npm_servers + python_servers + docker_servers + process_servers

    async def _scan_npm_globals(self):
        """Scan NPM global packages for MCP servers"""
        import subprocess
        result = subprocess.run(["npm", "list", "-g", "--json"], capture_output=True)
        packages = json.loads(result.stdout)

        mcp_servers = []
        for package_name, info in packages.get("dependencies", {}).items():
            if "mcp" in package_name or self._has_mcp_manifest(info["path"]):
                mcp_servers.append({
                    "type": "npm",
                    "name": package_name,
                    "command": f"npx {package_name}",
                    "transport": "stdio"
                })

        return mcp_servers
```

### 4. Example Implementations

#### Example 1: GitHub + Slack Workflow

```python
# Zero-code workflow definition (from UI)
workflow_json = {
    "id": "github-slack-notifier",
    "name": "GitHub PR to Slack",
    "nodes": [
        {
            "id": "github_monitor",
            "type": "github-mcp.watch_prs",
            "config": {
                "repo": "myorg/myrepo",
                "events": ["opened", "merged"]
            }
        },
        {
            "id": "format_message",
            "type": "PythonCodeNode",
            "config": {
                "code": """
result = {
    'text': f'PR #{data["number"]}: {data["title"]}',
    'channel': '#engineering'
}
"""
            }
        },
        {
            "id": "slack_notify",
            "type": "slack-mcp.send_message",
            "config": {
                "channel": "#engineering"
            }
        }
    ],
    "connections": [
        {"from": "github_monitor", "to": "format_message"},
        {"from": "format_message", "to": "slack_notify"}
    ]
}

# Deploy with one line
workflow = gateway.deploy_workflow(workflow_json)
```

#### Example 2: Multi-Agent Research Assistant

```python
# Complex MCP ecosystem workflow
research_workflow = {
    "id": "research-assistant",
    "nodes": [
        {
            "id": "query_parser",
            "type": "LLMAgentNode",
            "config": {"prompt": "Parse research query"}
        },
        {
            "id": "web_search",
            "type": "brave-search-mcp.search",
            "config": {"max_results": 10}
        },
        {
            "id": "arxiv_search",
            "type": "arxiv-mcp.search_papers",
            "config": {"max_results": 5}
        },
        {
            "id": "github_search",
            "type": "github-mcp.search_code",
            "config": {"language": "python"}
        },
        {
            "id": "synthesizer",
            "type": "LLMAgentNode",
            "config": {"prompt": "Synthesize research findings"}
        },
        {
            "id": "save_results",
            "type": "filesystem-mcp.write_file",
            "config": {"path": "research_results.md"}
        }
    ],
    "connections": [
        {"from": "query_parser", "to": "web_search"},
        {"from": "query_parser", "to": "arxiv_search"},
        {"from": "query_parser", "to": "github_search"},
        {"from": "web_search", "to": "synthesizer"},
        {"from": "arxiv_search", "to": "synthesizer"},
        {"from": "github_search", "to": "synthesizer"},
        {"from": "synthesizer", "to": "save_results"}
    ]
}
```

### 5. Implementation Roadmap

#### Phase 1: Core Infrastructure (Week 1-2)
- [ ] Enhance MCPClient with real MCP SDK integration
- [ ] Implement MCPEcosystemGateway
- [ ] Create MCP server registry and auto-discovery
- [ ] Build dynamic node generation from MCP tools

#### Phase 2: Visual Builder (Week 3-4)
- [ ] Create web-based workflow builder UI
- [ ] Implement drag-and-drop node palette
- [ ] Add connection drawing and validation
- [ ] Build properties panel for node configuration

#### Phase 3: Marketplace & Templates (Week 5-6)
- [ ] Implement workflow marketplace backend
- [ ] Create template sharing system
- [ ] Add workflow versioning and updates
- [ ] Build community features (ratings, comments)

#### Phase 4: Advanced Features (Week 7-8)
- [ ] Add workflow debugging and monitoring
- [ ] Implement workflow scheduling and triggers
- [ ] Create mobile app for workflow management
- [ ] Add workflow analytics and optimization

### 6. Key Differentiators

1. **Visual Programming**: Full drag-and-drop workflow creation
2. **MCP Native**: Built specifically for MCP ecosystem
3. **Marketplace**: Share and discover workflows
4. **Auto-Discovery**: Automatically find and register MCP servers
5. **Type Safety**: Schema validation for all connections
6. **Scalable**: Built on Kailash's proven architecture

### 7. API Examples

```python
# Initialize ecosystem
ecosystem = MCPEcosystemGateway(port=8000)

# Auto-discover and register all MCP servers
await ecosystem.auto_discover_servers()

# Create workflow from template
workflow = await ecosystem.marketplace.install_workflow("github-slack-notifier")

# Deploy and run
await ecosystem.deploy_workflow(workflow)

# Monitor execution
async for event in ecosystem.monitor_workflow(workflow.id):
    print(f"Event: {event.type} - {event.data}")
```

### 8. Configuration Format

```yaml
# mcp-ecosystem.yaml
servers:
  - id: github-mcp
    command: npx @modelcontextprotocol/server-github
    args: ["--token", "${GITHUB_TOKEN}"]
    transport: stdio

  - id: slack-mcp
    command: python -m mcp_server_slack
    env:
      SLACK_TOKEN: ${SLACK_TOKEN}
    transport: sse

  - id: custom-tools
    command: ./my-mcp-server
    transport: http
    endpoint: http://localhost:3000

marketplace:
  endpoint: https://mcp-marketplace.com
  auto_update: true

ui:
  port: 3000
  theme: dark
  enable_templates: true
```

This design provides a complete zero-code MCP ecosystem that leverages Kailash SDK's powerful workflow engine while making it accessible to non-programmers through visual tools and auto-discovery.
