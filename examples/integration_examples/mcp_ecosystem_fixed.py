#!/usr/bin/env python3
"""
MCP Ecosystem Gateway - Fixed Implementation

This is a corrected version that works with the actual Kailash SDK API.
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn

from kailash.api.gateway import WorkflowAPIGateway
from kailash.api.mcp_integration import MCPIntegration, MCPToolNode
from kailash.nodes.mcp.client import MCPClient
from kailash.nodes.base import Node, NodeParameter
from kailash.workflow import Workflow
from kailash.runtime.local import LocalRuntime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MCPServerRegistry:
    """Registry for MCP servers with discovery capabilities"""
    
    def __init__(self):
        self.servers: Dict[str, Dict] = {}
        self.clients: Dict[str, MCPClient] = {}
        
    async def register_server(self, server_id: str, config: Dict[str, Any]):
        """Register an MCP server"""
        logger.info(f"Registering MCP server: {server_id}")
        
        # Create client
        client = MCPClient(
            server_config={
                "name": server_id,
                "transport": config.get("transport", "stdio"),
                "command": config.get("command"),
                "args": config.get("args", []),
                "env": config.get("env", {})
            }
        )
        
        # Since we're using mock implementation, simulate discovery
        mock_tools = [
            {
                "name": "list_issues",
                "description": "List GitHub issues",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string"},
                        "state": {"type": "string", "default": "open"}
                    },
                    "required": ["repo"]
                }
            },
            {
                "name": "send_message",
                "description": "Send Slack message",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "channel": {"type": "string"},
                        "text": {"type": "string"}
                    },
                    "required": ["channel", "text"]
                }
            }
        ]
        
        # Store server info
        self.servers[server_id] = {
            "config": config,
            "tools": mock_tools if server_id in ["github-mcp", "slack-mcp"] else [],
            "status": "connected"
        }
        self.clients[server_id] = client
        
        logger.info(f"Server {server_id} registered successfully")
        return True


class SimpleMCPGateway:
    """Simplified MCP Gateway using Kailash SDK"""
    
    def __init__(self):
        # Create the API gateway with proper initialization
        self.gateway = WorkflowAPIGateway(
            title="MCP Ecosystem Gateway",
            description="Zero-code MCP workflow builder"
        )
        
        self.mcp_registry = MCPServerRegistry()
        self.workflows = {}
        
        # Add custom routes
        self._setup_routes()
        
    def _setup_routes(self):
        """Setup custom API routes"""
        
        @self.gateway.app.get("/mcp/servers")
        async def list_servers():
            """List registered MCP servers"""
            return {
                "servers": [
                    {
                        "id": server_id,
                        "status": info["status"],
                        "tools": len(info.get("tools", []))
                    }
                    for server_id, info in self.mcp_registry.servers.items()
                ]
            }
            
        @self.gateway.app.post("/mcp/register")
        async def register_server(server_config: Dict[str, Any]):
            """Register a new MCP server"""
            server_id = server_config["id"]
            success = await self.mcp_registry.register_server(server_id, server_config)
            return {"success": success, "server_id": server_id}
            
        @self.gateway.app.get("/")
        async def home():
            """Home page with UI"""
            return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
    <title>MCP Ecosystem - Kailash SDK</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .server { border: 1px solid #ddd; padding: 10px; margin: 10px 0; }
        button { background: #007bff; color: white; border: none; padding: 8px 16px; cursor: pointer; }
        button:hover { background: #0056b3; }
        .workflow { background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; }
    </style>
</head>
<body>
    <h1>MCP Ecosystem Gateway</h1>
    <p>Build workflows visually using MCP tools!</p>
    
    <h2>Registered MCP Servers</h2>
    <div id="servers"></div>
    
    <h2>Sample Workflows</h2>
    <div class="workflow">
        <h3>GitHub to Slack Notifier</h3>
        <p>Monitor GitHub issues and send notifications to Slack</p>
        <button onclick="deployWorkflow('github-slack')">Deploy</button>
    </div>
    
    <div class="workflow">
        <h3>Data Processing Pipeline</h3>
        <p>Read CSV, process with Python, and save as JSON</p>
        <button onclick="deployWorkflow('data-pipeline')">Deploy</button>
    </div>
    
    <div id="status"></div>
    
    <script>
        async function loadServers() {
            const response = await fetch('/mcp/servers');
            const data = await response.json();
            
            const serversDiv = document.getElementById('servers');
            serversDiv.innerHTML = data.servers.map(s => 
                `<div class="server">
                    <strong>${s.id}</strong> - Status: ${s.status} - Tools: ${s.tools}
                </div>`
            ).join('');
        }
        
        async function deployWorkflow(workflowId) {
            const status = document.getElementById('status');
            status.textContent = 'Deploying ' + workflowId + '...';
            
            try {
                const response = await fetch('/deploy/' + workflowId, {
                    method: 'POST'
                });
                const result = await response.json();
                status.textContent = result.message || 'Deployed successfully!';
            } catch (err) {
                status.textContent = 'Error: ' + err.message;
            }
        }
        
        // Load servers on page load
        loadServers();
        setInterval(loadServers, 5000);
    </script>
</body>
</html>
            """)
            
        @self.gateway.app.post("/deploy/{workflow_id}")
        async def deploy_workflow(workflow_id: str):
            """Deploy a pre-built workflow"""
            if workflow_id == "github-slack":
                # Create a sample workflow
                workflow = Workflow(
                    workflow_id="github_slack_" + str(len(self.workflows)),
                    name="GitHub to Slack Notifier"
                )
                
                # Add mock nodes
                # In real implementation, would use actual MCPToolNode
                from kailash.nodes.code.python import PythonCodeNode
                
                github_node = PythonCodeNode(
                    name="github_mock",
                    code="""
# Mock GitHub issues fetch
result = {
    'issues': [
        {'id': 1, 'title': 'Bug in login', 'state': 'open'},
        {'id': 2, 'title': 'Feature request', 'state': 'open'}
    ]
}
"""
                )
                
                slack_node = PythonCodeNode(
                    name="slack_mock",
                    code="""
# Mock Slack notification
issues = data.get('issues', [])
result = {
    'message': f'Found {len(issues)} open issues',
    'sent': True
}
"""
                )
                
                workflow.add_node("github", github_node)
                workflow.add_node("slack", slack_node)
                workflow.connect("github", "slack")
                
                # Register with gateway
                self.gateway.register_workflow(workflow_id, workflow)
                self.workflows[workflow_id] = workflow
                
                return {"success": True, "message": f"Workflow {workflow_id} deployed"}
                
            elif workflow_id == "data-pipeline":
                # Create data pipeline workflow
                from kailash.nodes.data.readers import CSVReaderNode
                from kailash.nodes.code.python import PythonCodeNode
                from kailash.nodes.data.writers import JSONWriterNode
                
                workflow = Workflow(
                    workflow_id="data_pipeline_" + str(len(self.workflows)),
                    name="Data Processing Pipeline"
                )
                
                # Note: These would need actual file paths in real usage
                reader = CSVReaderNode(file_path="data/input.csv")
                processor = PythonCodeNode(
                    name="data_processor",
                    code="result = {'processed': len(data), 'data': data}"
                )
                writer = JSONWriterNode(file_path="outputs/result.json")
                
                workflow.add_node("reader", reader)
                workflow.add_node("processor", processor)
                workflow.add_node("writer", writer)
                
                workflow.connect("reader", "processor")
                workflow.connect("processor", "writer")
                
                self.gateway.register_workflow(workflow_id, workflow)
                self.workflows[workflow_id] = workflow
                
                return {"success": True, "message": f"Workflow {workflow_id} deployed"}
                
            else:
                raise HTTPException(status_code=404, detail="Workflow not found")
    
    async def start(self):
        """Start the gateway"""
        # Register some mock MCP servers
        await self.mcp_registry.register_server("github-mcp", {
            "command": "npx",
            "args": ["@modelcontextprotocol/server-github"],
            "transport": "stdio"
        })
        
        await self.mcp_registry.register_server("slack-mcp", {
            "command": "python",
            "args": ["-m", "mcp_server_slack"],
            "transport": "stdio"
        })
        
        logger.info("Starting MCP Ecosystem Gateway...")
        logger.info("Web UI available at: http://localhost:8000")
        
        # Use the gateway's run method
        self.gateway.run(port=8000)


async def main():
    """Run the MCP ecosystem"""
    gateway = SimpleMCPGateway()
    await gateway.start()


if __name__ == "__main__":
    asyncio.run(main())