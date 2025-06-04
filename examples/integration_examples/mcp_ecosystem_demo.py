#!/usr/bin/env python3
"""
MCP Ecosystem Demo - Simplified for Easy Running

This is a minimal version that demonstrates the core concepts
without requiring external dependencies.
"""

import json
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import HTMLResponse
import uvicorn
from typing import Dict, List, Any
import asyncio
import time

# Create the demo app
app = FastAPI(
    title="MCP Ecosystem Demo", description="Zero-code workflow builder for Kailash SDK"
)

# Mock data storage
workflows = {}
workflow_stats = {"total": 0, "running": 0, "completed": 0, "failed": 0}
mcp_servers = {
    "github-mcp": {
        "status": "connected",
        "tools": ["list_issues", "create_pr", "list_repos"],
    },
    "slack-mcp": {"status": "connected", "tools": ["send_message", "list_channels"]},
    "filesystem-mcp": {
        "status": "connected",
        "tools": ["read_file", "write_file", "list_files"],
    },
}


@app.get("/")
async def home():
    """Serve the demo UI with live interactive components"""
    return HTMLResponse(
        """
<!DOCTYPE html>
<html>
<head>
    <title>MCP Ecosystem - Kailash SDK Demo</title>
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #333; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px; }
        .card {
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .server {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px;
            margin: 5px 0;
            background: #f9f9f9;
            border-radius: 4px;
        }
        .status { 
            color: #28a745;
            font-size: 12px;
            font-weight: bold;
        }
        .workflow {
            border: 1px solid #e0e0e0;
            border-radius: 6px;
            padding: 15px;
            margin: 10px 0;
            cursor: pointer;
            transition: all 0.2s;
        }
        .workflow:hover {
            border-color: #007bff;
            box-shadow: 0 2px 8px rgba(0,123,255,0.1);
        }
        .workflow h3 { margin: 0 0 8px 0; color: #333; }
        .workflow p { margin: 0; color: #666; font-size: 14px; }
        button {
            background: #007bff;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin-top: 10px;
        }
        button:hover { background: #0056b3; }
        .success { 
            background: #d4edda;
            color: #155724;
            padding: 10px;
            border-radius: 4px;
            margin: 10px 0;
        }
        .builder-container {
            display: grid;
            grid-template-columns: 200px 1fr;
            gap: 20px;
            min-height: 300px;
        }
        .node-palette {
            background: #f9f9f9;
            padding: 15px;
            border-radius: 8px;
        }
        .node-palette h4 {
            margin: 0 0 10px 0;
            color: #666;
        }
        .node-item {
            background: white;
            padding: 10px;
            margin: 8px 0;
            border-radius: 6px;
            cursor: grab;
            border: 2px solid #e0e0e0;
            transition: all 0.2s;
        }
        .node-item:hover {
            border-color: #007bff;
            transform: translateX(5px);
        }
        .workflow-canvas {
            background: white;
            border: 2px dashed #ddd;
            border-radius: 8px;
            padding: 20px;
            position: relative;
            min-height: 300px;
        }
        .workflow-canvas.drag-over {
            border-color: #007bff;
            background: #f0f8ff;
        }
        .drop-hint {
            color: #999;
            text-align: center;
            margin-top: 100px;
        }
        .dropped-node {
            background: #e3f2fd;
            padding: 10px 15px;
            margin: 10px;
            border-radius: 6px;
            display: inline-block;
            position: relative;
            cursor: move;
        }
        .dropped-node .remove {
            position: absolute;
            right: -5px;
            top: -5px;
            background: #ff5252;
            color: white;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            text-align: center;
            line-height: 20px;
            cursor: pointer;
            font-size: 12px;
        }
        .builder-actions {
            margin-top: 15px;
            text-align: right;
        }
        .builder-actions button {
            margin-left: 10px;
        }
        button.primary {
            background: #28a745;
        }
        button.primary:hover {
            background: #218838;
        }
        #execution-log {
            font-family: monospace;
            font-size: 12px;
            background: #f5f5f5;
            padding: 15px;
            border-radius: 4px;
            max-height: 200px;
            overflow-y: auto;
        }
        .log-entry {
            margin: 2px 0;
            padding: 2px 5px;
        }
        .log-success { color: #28a745; }
        .log-info { color: #17a2b8; }
        .log-error { color: #dc3545; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 6px;
            text-align: center;
        }
        .stat-value {
            font-size: 24px;
            font-weight: bold;
            color: #007bff;
        }
        .stat-label {
            font-size: 12px;
            color: #666;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 MCP Ecosystem - Zero Code Workflow Builder</h1>
        <p>Build and deploy workflows without writing any code!</p>
        
        <div class="grid">
            <div class="card">
                <h2>📡 MCP Servers</h2>
                <div id="servers"></div>
            </div>
            
            <div class="card">
                <h2>🔧 Workflow Templates</h2>
                <div class="workflow" onclick="deployWorkflow('github-slack')">
                    <h3>GitHub → Slack Notifier</h3>
                    <p>Monitor GitHub issues and send notifications to Slack</p>
                    <button>Deploy Workflow</button>
                </div>
                
                <div class="workflow" onclick="deployWorkflow('data-pipeline')">
                    <h3>Data Processing Pipeline</h3>
                    <p>Read CSV → Transform with Python → Save as JSON</p>
                    <button>Deploy Workflow</button>
                </div>
                
                <div class="workflow" onclick="deployWorkflow('ai-assistant')">
                    <h3>AI Research Assistant</h3>
                    <p>Search web → Summarize → Save to file</p>
                    <button>Deploy Workflow</button>
                </div>
            </div>
        </div>
        
        <div class="card" style="margin-top: 20px;">
            <h2>🎨 Visual Workflow Builder</h2>
            <div class="builder-container">
                <div class="node-palette">
                    <h4>Available Nodes</h4>
                    <div class="node-item" draggable="true" data-node-type="CSVReaderNode">
                        📄 CSV Reader
                    </div>
                    <div class="node-item" draggable="true" data-node-type="PythonCodeNode">
                        🐍 Python Code
                    </div>
                    <div class="node-item" draggable="true" data-node-type="JSONWriterNode">
                        💾 JSON Writer
                    </div>
                    <div class="node-item" draggable="true" data-node-type="github-mcp.list_issues">
                        🐙 GitHub Issues
                    </div>
                    <div class="node-item" draggable="true" data-node-type="slack-mcp.send_message">
                        💬 Slack Message
                    </div>
                </div>
                <div class="workflow-canvas" id="canvas">
                    <div class="drop-hint">Drop nodes here to build workflow</div>
                </div>
            </div>
            <div class="builder-actions">
                <button onclick="clearCanvas()">Clear</button>
                <button onclick="deployCustomWorkflow()" class="primary">Deploy Custom Workflow</button>
            </div>
        </div>
        
        <div class="card" style="margin-top: 20px;">
            <h2>📊 Live Workflow Execution</h2>
            <div id="execution-log"></div>
        </div>
        
        <div id="status"></div>
    </div>
    
    <script>
        let workflowNodes = [];
        let stats = { total: 0, running: 0, completed: 0 };
        
        // Initialize drag and drop
        document.addEventListener('DOMContentLoaded', () => {
            const canvas = document.getElementById('canvas');
            const nodeItems = document.querySelectorAll('.node-item');
            
            nodeItems.forEach(item => {
                item.addEventListener('dragstart', (e) => {
                    e.dataTransfer.setData('nodeType', e.target.dataset.nodeType);
                    e.dataTransfer.setData('nodeText', e.target.textContent.trim());
                });
            });
            
            canvas.addEventListener('dragover', (e) => {
                e.preventDefault();
                canvas.classList.add('drag-over');
            });
            
            canvas.addEventListener('dragleave', () => {
                canvas.classList.remove('drag-over');
            });
            
            canvas.addEventListener('drop', (e) => {
                e.preventDefault();
                canvas.classList.remove('drag-over');
                
                const nodeType = e.dataTransfer.getData('nodeType');
                const nodeText = e.dataTransfer.getData('nodeText');
                
                addNodeToCanvas(nodeType, nodeText);
            });
            
            updateStats();
        });
        
        function addNodeToCanvas(nodeType, nodeText) {
            const canvas = document.getElementById('canvas');
            const nodeId = 'node_' + Date.now();
            
            workflowNodes.push({ id: nodeId, type: nodeType, text: nodeText });
            
            // Remove hint if first node
            if (workflowNodes.length === 1) {
                canvas.querySelector('.drop-hint').style.display = 'none';
            }
            
            const nodeEl = document.createElement('div');
            nodeEl.className = 'dropped-node';
            nodeEl.id = nodeId;
            nodeEl.innerHTML = `
                ${nodeText}
                <span class="remove" onclick="removeNode('${nodeId}')">×</span>
            `;
            
            canvas.appendChild(nodeEl);
            
            addLog('info', `Added node: ${nodeText}`);
        }
        
        function removeNode(nodeId) {
            workflowNodes = workflowNodes.filter(n => n.id !== nodeId);
            document.getElementById(nodeId).remove();
            
            if (workflowNodes.length === 0) {
                document.querySelector('.drop-hint').style.display = 'block';
            }
        }
        
        function clearCanvas() {
            workflowNodes = [];
            const canvas = document.getElementById('canvas');
            canvas.innerHTML = '<div class="drop-hint">Drop nodes here to build workflow</div>';
            addLog('info', 'Canvas cleared');
        }
        
        async function deployCustomWorkflow() {
            if (workflowNodes.length === 0) {
                addLog('error', 'No nodes to deploy!');
                return;
            }
            
            const workflowId = 'custom_' + Date.now();
            addLog('info', `Deploying custom workflow: ${workflowId}`);
            
            // Simulate deployment
            stats.running++;
            updateStats();
            
            setTimeout(() => {
                stats.running--;
                stats.completed++;
                stats.total++;
                updateStats();
                addLog('success', `✅ Custom workflow deployed with ${workflowNodes.length} nodes`);
            }, 1500);
        }
        
        // Load MCP servers with animation
        async function loadServers() {
            const response = await fetch('/api/servers');
            const servers = await response.json();
            
            const serversDiv = document.getElementById('servers');
            serversDiv.innerHTML = Object.entries(servers).map(([id, info]) => `
                <div class="server">
                    <div>
                        <strong>${id}</strong>
                        <br><small>${info.tools.length} tools available</small>
                    </div>
                    <span class="status">● ${info.status}</span>
                </div>
            `).join('');
        }
        
        // Enhanced deploy workflow with live updates
        async function deployWorkflow(workflowId, event) {
            if (event) event.stopPropagation();
            
            const statusDiv = document.getElementById('status');
            statusDiv.innerHTML = '<div class="success">🔄 Deploying ' + workflowId + '...</div>';
            
            addLog('info', `Starting deployment: ${workflowId}`);
            stats.running++;
            updateStats();
            
            try {
                const response = await fetch('/api/deploy/' + workflowId, {
                    method: 'POST'
                });
                const result = await response.json();
                
                statusDiv.innerHTML = `
                    <div class="success">
                        ✅ ${result.message}<br>
                        <small>Workflow ID: ${result.workflow_id}</small>
                    </div>
                `;
                
                addLog('success', `✅ ${result.message}`);
                stats.running--;
                stats.completed++;
                stats.total++;
                updateStats();
                
                // Auto-hide status after 5 seconds
                setTimeout(() => {
                    statusDiv.innerHTML = '';
                }, 5000);
                
            } catch (err) {
                statusDiv.innerHTML = '<div style="color: red;">Error: ' + err.message + '</div>';
                addLog('error', `❌ Deployment failed: ${err.message}`);
                stats.running--;
                updateStats();
            }
        }
        
        function addLog(type, message) {
            const logDiv = document.getElementById('execution-log');
            const timestamp = new Date().toLocaleTimeString();
            const entry = document.createElement('div');
            entry.className = `log-entry log-${type}`;
            entry.textContent = `[${timestamp}] ${message}`;
            logDiv.appendChild(entry);
            logDiv.scrollTop = logDiv.scrollHeight;
        }
        
        function updateStats() {
            // Update or create stats display
            let statsDiv = document.getElementById('stats');
            if (!statsDiv) {
                const container = document.querySelector('.container');
                statsDiv = document.createElement('div');
                statsDiv.id = 'stats';
                statsDiv.className = 'card';
                statsDiv.innerHTML = '<h2>📈 Live Statistics</h2><div class="stats-grid"></div>';
                container.insertBefore(statsDiv, container.children[1]);
            }
            
            const grid = statsDiv.querySelector('.stats-grid');
            grid.innerHTML = `
                <div class="stat-card">
                    <div class="stat-value">${stats.total}</div>
                    <div class="stat-label">Total Workflows</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${stats.running}</div>
                    <div class="stat-label">Running Now</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${stats.completed}</div>
                    <div class="stat-label">Completed</div>
                </div>
            `;
        }
        
        // Initialize with welcome message
        addLog('info', '🚀 MCP Ecosystem started');
        addLog('info', 'Drag nodes to canvas or deploy templates');
        
        // Initialize
        loadServers();
        setInterval(loadServers, 5000);
        
        // Simulate some activity
        setTimeout(() => {
            addLog('success', '✅ Connected to 3 MCP servers');
        }, 1000);
    </script>
</body>
</html>
    """
    )


@app.get("/api/servers")
async def get_servers():
    """Get MCP server status"""
    return mcp_servers


@app.post("/api/deploy/{workflow_id}")
async def deploy_workflow(workflow_id: str):
    """Deploy a workflow template"""
    templates = {
        "github-slack": {
            "name": "GitHub to Slack Notifier",
            "description": "Monitor GitHub and notify Slack",
            "nodes": ["github-mcp.list_issues", "slack-mcp.send_message"],
        },
        "data-pipeline": {
            "name": "Data Processing Pipeline",
            "description": "ETL workflow for data processing",
            "nodes": ["CSVReaderNode", "PythonCodeNode", "JSONWriterNode"],
        },
        "ai-assistant": {
            "name": "AI Research Assistant",
            "description": "Research and summarize topics",
            "nodes": ["web-search", "llm-summarize", "file-save"],
        },
    }

    if workflow_id not in templates:
        raise HTTPException(status_code=404, detail="Template not found")

    # Mock deployment
    import time

    workflow_instance_id = f"{workflow_id}_{int(time.time())}"
    workflows[workflow_instance_id] = {
        "template": workflow_id,
        "status": "deployed",
        "created": time.time(),
        "runs": 0,
    }

    # Update stats
    workflow_stats["total"] += 1

    return {
        "success": True,
        "workflow_id": workflow_instance_id,
        "message": f"Successfully deployed {templates[workflow_id]['name']}",
    }


@app.get("/api/workflows")
async def list_workflows():
    """List deployed workflows"""
    return {"workflows": workflows, "count": len(workflows)}


@app.get("/api/stats")
async def get_stats():
    """Get workflow execution statistics"""
    return workflow_stats


@app.post("/api/workflows/{workflow_id}/execute")
async def execute_workflow(workflow_id: str):
    """Simulate workflow execution"""
    if workflow_id not in workflows:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Update stats
    workflow_stats["running"] += 1

    # Simulate async execution
    import asyncio

    async def complete_execution():
        await asyncio.sleep(2)  # Simulate work
        workflow_stats["running"] -= 1
        workflow_stats["completed"] += 1
        workflows[workflow_id]["last_run"] = time.time()
        workflows[workflow_id]["runs"] = workflows[workflow_id].get("runs", 0) + 1

    # Start execution in background
    asyncio.create_task(complete_execution())

    return {"success": True, "message": f"Workflow {workflow_id} started execution"}


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🚀 MCP Ecosystem Demo Server")
    print("=" * 60)
    print("\n📍 Open your browser to: http://localhost:8000")
    print("📚 API Documentation: http://localhost:8000/docs")
    print("\nPress Ctrl+C to stop the server\n")

    uvicorn.run(app, host="0.0.0.0", port=8000)
