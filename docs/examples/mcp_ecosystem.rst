MCP Ecosystem Example
=====================

The MCP (Model Context Protocol) ecosystem example demonstrates how to build a
zero-code workflow deployment platform using the Kailash SDK.

Overview
--------

The MCP ecosystem provides:

- **Visual Workflow Builder**: Drag-and-drop interface for creating workflows
- **Zero-Code Deployment**: Deploy workflows without writing any code
- **MCP Server Integration**: Connect to GitHub, Slack, and filesystem MCP servers
- **Live Monitoring**: Real-time statistics and execution logs
- **REST API**: Programmatic access to all features

Quick Start
-----------

.. code-block:: bash

    # Navigate to examples
    cd examples/integration_examples

    # Run the ecosystem
    ./run_ecosystem.sh

    # Open browser to http://localhost:8000

Architecture
------------

The ecosystem uses a three-tier architecture:

1. **Web UI Layer** - Interactive dashboard built with vanilla HTML/CSS/JavaScript
2. **MCP Ecosystem Gateway** - Bridges the UI with Kailash SDK using WorkflowAPIGateway
3. **Kailash SDK Core** - Handles workflow execution and node management

Key Features
------------

Visual Workflow Builder
~~~~~~~~~~~~~~~~~~~~~~~

The drag-and-drop interface allows users to:

- Select nodes from the palette (CSV Reader, Python Code, JSON Writer, etc.)
- Drop nodes onto the canvas to build workflows
- Deploy custom workflows with one click

Pre-built Templates
~~~~~~~~~~~~~~~~~~~

Three workflow templates are included:

1. **GitHub → Slack Notifier**: Monitor GitHub issues and send Slack notifications
2. **Data Processing Pipeline**: Read CSV → Transform with Python → Save as JSON
3. **AI Research Assistant**: Search web → Summarize → Save results

Live Dashboard
~~~~~~~~~~~~~~

Real-time monitoring includes:

- Connected MCP server status
- Workflow execution statistics
- Live execution logs with timestamps

API Endpoints
-------------

The ecosystem exposes these REST endpoints:

.. code-block:: text

    GET  /                             # Web UI
    GET  /api/servers                  # List MCP servers
    POST /api/deploy/{workflow_id}     # Deploy a workflow
    GET  /api/workflows                # List deployed workflows
    GET  /api/stats                    # Execution statistics
    POST /api/workflows/{id}/execute   # Execute a workflow

Example Usage
-------------

Deploy a workflow via API:

.. code-block:: python

    import requests

    # Deploy the GitHub to Slack workflow
    response = requests.post("http://localhost:8000/api/deploy/github-slack")
    print(response.json())
    # Output: {"success": true, "workflow_id": "github_slack_1234567890"}

Create a custom workflow visually:

1. Drag "CSV Reader" node to canvas
2. Drag "Python Code" node to canvas
3. Drag "JSON Writer" node to canvas
4. Click "Deploy Custom Workflow"

Implementation Details
----------------------

The ecosystem is implemented in two versions:

1. **mcp_ecosystem_demo.py** - Simplified demo with mock MCP servers
2. **mcp_ecosystem_fixed.py** - Full integration with Kailash SDK

Both demonstrate the same concepts but the fixed version creates actual Kailash
workflows.

Technology Stack
----------------

- **Backend**: FastAPI for web framework and API
- **Frontend**: Vanilla HTML/CSS/JavaScript (no frameworks)
- **Workflow Engine**: Kailash SDK
- **MCP Integration**: Model Context Protocol for tool discovery

Future Enhancements
-------------------

Planned improvements include:

- WebSocket support for real-time updates
- Persistent workflow storage
- User authentication and multi-tenancy
- Visual workflow connections
- Export/import workflow definitions

See Also
--------

- :doc:`../api/gateway` - WorkflowAPIGateway documentation
- :doc:`../api/workflow_api` - Workflow API wrapper
- `MCP Protocol <https://modelcontextprotocol.io>`_ - Model Context Protocol

Enhanced MCP Server (New in v0.3.1)
-----------------------------------

The Kailash SDK now includes an **Enhanced MCP Server** that provides powerful default
capabilities for any workflow:

Default Tools Available
~~~~~~~~~~~~~~~~~~~~~~~

Every workflow automatically gets access to these tools via MCP:

- **workflow_execute**: Execute any Kailash workflow by ID
- **workflow_list**: List available workflows with descriptions
- **workflow_info**: Get detailed information about a specific workflow
- **node_info**: Get information about available nodes and their parameters
- **task_status**: Check the status of running workflow executions
- **result_retrieve**: Get the results of completed workflow executions

Example Usage
~~~~~~~~~~~~~

Start the enhanced MCP server:

.. code-block:: python

    from kailash.mcp.server_enhanced import EnhancedMCPServer

    # Create server with your workflows
    server = EnhancedMCPServer(
        name="finance-workflows",
        workflow_registry={
            "credit-risk": credit_risk_workflow,
            "portfolio-opt": portfolio_optimization_workflow,
            "fraud-detect": fraud_detection_workflow
        }
    )

    # Start serving
    server.serve()

Now any MCP client can discover and execute your workflows:

.. code-block:: python

    # From any MCP client
    tools = await client.list_tools()
    # Returns: workflow_execute, workflow_list, etc.

    # Execute a workflow
    result = await client.call_tool(
        "workflow_execute",
        workflow_id="credit-risk",
        parameters={"customer_file": "customers.csv"}
    )

Benefits
~~~~~~~~

1. **Zero Configuration**: Default tools work out of the box
2. **Workflow Discovery**: Clients can discover available workflows dynamically
3. **Async Execution**: Non-blocking workflow execution with status tracking
4. **Result Management**: Automatic result storage and retrieval
5. **Integration Ready**: Works with any MCP-compatible client (Claude, VS Code, etc.)

Use Cases
~~~~~~~~~

- **AI Assistants**: Give Claude or other LLMs access to your workflows
- **IDE Integration**: Execute workflows directly from VS Code
- **ChatOps**: Run workflows from Slack or Discord
- **API Gateway**: Expose workflows through a unified MCP interface

See :doc:`../api/mcp_integration` for detailed API documentation.
