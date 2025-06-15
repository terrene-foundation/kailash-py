=======================
Kailash Workflow Studio
=======================

.. note::
   The Kailash Workflow Studio is currently in development (as of Session 48).
   This visual workflow builder will provide a drag-and-drop interface for
   creating and managing Kailash workflows.

Overview
========

The Kailash Workflow Studio is a web-based visual interface for building,
testing, and deploying workflows using the Kailash Python SDK. It provides
a user-friendly alternative to writing Python code while maintaining full
access to all SDK capabilities.

Key Features
============

Visual Workflow Builder
-----------------------

- **Drag-and-Drop Interface**: Create workflows by dragging nodes from the
  palette and connecting them on the canvas
- **Dynamic Node Palette**: Automatically populated with all 66+ available
  nodes from the SDK
- **Real-time Validation**: Instant feedback on connection compatibility and
  parameter validation
- **Property Panel**: Configure node parameters through intuitive forms

Multi-Tenant Architecture
-------------------------

- **Isolated Workspaces**: Each organization gets its own isolated environment
- **Persistent Storage**: Workflows and data are stored per-tenant
- **Scalable Deployment**: Docker-based architecture supports any number of tenants
- **Security**: Complete data isolation between tenants

Seamless SDK Integration
------------------------

- **100% SDK Coverage**: Every node and feature in the SDK is available in the Studio
- **Bidirectional Sync**: Import Python workflows and export visual workflows as code
- **API-First Design**: All functionality exposed through REST and WebSocket APIs
- **Real-time Execution**: Monitor workflow execution with live updates

Architecture
============

Frontend Stack
--------------

The Studio frontend is built with modern web technologies:

- **React 18** with TypeScript for type-safe component development
- **Vite** for fast development and optimized production builds
- **React Flow** for the visual workflow canvas
- **Tailwind CSS** for responsive, consistent styling
- **Tanstack React Query** for efficient data fetching and caching

Backend Integration
-------------------

The Studio extends the Kailash SDK with additional API endpoints::

    # Node Discovery
    GET /api/nodes                    # List all available nodes
    GET /api/nodes/{category}         # List nodes by category
    GET /api/nodes/{node_id}/schema   # Get node parameter schema

    # Workflow Management
    GET /api/workflows                # List tenant workflows
    POST /api/workflows               # Create new workflow
    GET /api/workflows/{id}           # Get workflow details
    PUT /api/workflows/{id}           # Update workflow
    DELETE /api/workflows/{id}        # Delete workflow

    # Workflow Execution
    POST /api/workflows/{id}/execute  # Execute workflow
    GET /api/executions/{id}          # Get execution status
    WS /ws/executions/{id}            # Real-time execution updates

Multi-Tenant Deployment
-----------------------

Each tenant gets isolated resources:

.. code-block:: yaml

   # docker-compose.yml structure
   services:
     postgres:         # Shared database with schema isolation
     redis:           # Shared cache with database isolation
     tenant_{id}:     # Per-tenant application container
       environment:
         TENANT_ID: ${TENANT_ID}
         DATABASE_URL: postgresql://.../${TENANT_ID}
       volumes:
         - ./tenants/${TENANT_ID}/workflows:/app/workflows
         - ./tenants/${TENANT_ID}/data:/app/data

Getting Started
===============

Development Mode
----------------

For local development and testing:

.. code-block:: bash

   # Clone the repository
   git clone https://github.com/terrene-foundation/kailash-py.git
   cd kailash-python-sdk

   # Start the Studio in development mode
   ./studio/start-studio.sh

   # Access the Studio at http://localhost:3000

This starts:

- Backend API on port 8000
- Frontend development server on port 3000
- PostgreSQL and Redis in Docker containers

Production Deployment
---------------------

Deploy a new tenant in production:

.. code-block:: bash

   # Deploy tenant with custom domain
   ./studio/deploy-tenant.sh \
     --tenant-id acme \
     --domain acme.studio.kailash.ai

   # This creates:
   # - Isolated Docker container
   # - PostgreSQL schema
   # - Redis database
   # - Nginx routing configuration

Creating Workflows
==================

Basic Workflow Creation
-----------------------

1. **Add Nodes**: Drag nodes from the palette to the canvas
2. **Connect Nodes**: Draw connections between node outputs and inputs
3. **Configure Parameters**: Click nodes to open the property panel
4. **Test Execution**: Use the Run button to execute the workflow
5. **Monitor Progress**: View real-time execution status and logs

Example: Data Processing Pipeline
---------------------------------

.. code-block:: text

   [CSV Reader] → [Filter] → [Transform] → [CSV Writer]
        ↓
   [Data Quality Check] → [Error Handler]

This workflow:

1. Reads data from a CSV file
2. Filters records based on criteria
3. Transforms the data
4. Writes results to a new CSV
5. Includes error handling for data quality issues

Importing and Exporting
-----------------------

**Import Python Workflows**:

.. code-block:: python

   # Python workflow can be imported directly
   from kailash import Workflow
   workflow = Workflow.load("my_workflow.py")

   # Upload to Studio via API
   api.post("/api/workflows/import", files={"workflow": workflow})

**Export Visual Workflows**:

- Export as Python code for local development
- Export as YAML for production deployment
- Export as JSON for version control

Advanced Features
=================

Real-time Collaboration
-----------------------

- Multiple users can view the same workflow
- Changes are synchronized in real-time
- Built-in commenting and annotation tools

Version Control Integration
---------------------------

- Git integration for workflow versioning
- Diff viewer for workflow changes
- Branch and merge workflow versions

Performance Monitoring
----------------------

- Execution timeline visualization
- Resource usage metrics
- Bottleneck identification
- Historical performance tracking

Development Guidelines
======================

For developers extending the Studio, comprehensive guidelines are available:

- **Architecture Patterns**: See ``shared/frontend/architecture.md``
- **Component Development**: See ``shared/frontend/components.md``
- **API Integration**: See ``shared/frontend/api-integration.md``
- **Testing Strategies**: See ``shared/frontend/testing.md``

Component Structure
-------------------

The Studio follows a hierarchical component architecture::

    App
    ├── Layout
    │   ├── Header
    │   ├── Sidebar
    │   └── MainContent
    ├── WorkflowEditor
    │   ├── NodePalette
    │   ├── WorkflowCanvas
    │   ├── PropertyPanel
    │   └── MiniMap
    └── ExecutionMonitor
        ├── StatusPanel
        ├── LogViewer
        └── MetricsDisplay

API Integration
===============

The Studio provides multiple ways to integrate with external systems:

REST API
--------

.. code-block:: python

   import requests

   # Get workflow details
   response = requests.get(
       "https://studio.kailash.ai/api/workflows/wf-123",
       headers={"Authorization": f"Bearer {token}"}
   )
   workflow = response.json()

   # Execute workflow
   response = requests.post(
       "https://studio.kailash.ai/api/workflows/wf-123/execute",
       json={"inputs": {"data": "value"}},
       headers={"Authorization": f"Bearer {token}"}
   )
   execution_id = response.json()["execution_id"]

WebSocket Updates
-----------------

.. code-block:: javascript

   const ws = new WebSocket('wss://studio.kailash.ai/ws/executions/exec-123');

   ws.onmessage = (event) => {
     const update = JSON.parse(event.data);
     console.log(`Task ${update.task_id}: ${update.status}`);
   };

SDK Integration
---------------

.. code-block:: python

   # This import is deprecated - use middleware instead
   # from kailash.middleware import create_gateway

   # Initialize client
   client = StudioClient(
       base_url="https://studio.kailash.ai",
       api_key="your-api-key"
   )

   # List workflows
   workflows = client.list_workflows()

   # Download and run locally
   workflow = client.get_workflow("wf-123")
   results = workflow.run(inputs={"data": "value"})

Current Status
==============

As of Session 48, the following has been completed:

✅ **Foundation**:
   - Frontend development guidelines created
   - React + TypeScript + Vite project structure
   - Docker infrastructure for deployment
   - Deployment scripts and tools

🚧 **In Progress**:
   - WorkflowStudioAPI backend implementation
   - Core UI components (NodePalette, Canvas, PropertyPanel)
   - Node discovery API integration

⏳ **Planned**:
   - WebSocket real-time updates
   - PostgreSQL schema isolation
   - Tenant authentication system
   - Production deployment patterns

References
==========

- **Architecture Decision**: See ADR-0033 for multi-tenant architecture details
- **Frontend Guidelines**: ``shared/frontend/``
- **API Documentation**: :doc:`/api/workflow_api`
- **Node Catalog**: ``sdk-users/nodes/comprehensive-node-catalog.md``

.. note::
   For the latest updates on Workflow Studio development, check the
   project's GitHub issues and the ``# contrib (removed)/project/todos/000-master.md`` file.
