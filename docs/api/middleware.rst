=====================
Middleware Components
=====================

.. currentmodule:: kailash.middleware

The Kailash middleware layer provides enterprise-grade components for building production
applications with real-time communication, session management, and AI integration capabilities.

Overview
========

The middleware architecture consists of composable components that work together to provide
a complete solution for frontend-backend communication in workflow-based applications.

Core Components
===============

Agent-UI Middleware
-------------------

.. autoclass:: kailash.middleware.AgentUIMiddleware
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

The AgentUIMiddleware serves as the central orchestration hub for frontend communication,
providing session management, dynamic workflow creation, and execution monitoring.

**Key Features:**

- Multi-tenant session isolation
- Dynamic workflow creation from JSON configurations
- Real-time execution monitoring
- Automatic session cleanup
- Database persistence support

**Usage Example:**

.. code-block:: python

   from kailash.middleware import AgentUIMiddleware

   agent_ui = AgentUIMiddleware(
       max_sessions=1000,
       session_timeout_minutes=60,
       enable_persistence=True
   )

   # Create session
   session_id = await agent_ui.create_session("user123")

   # Create dynamic workflow
   workflow_config = {
       "name": "data_pipeline",
       "nodes": [...],
       "connections": [...]
   }

   workflow_id = await agent_ui.create_dynamic_workflow(
       session_id, workflow_config
   )

API Gateway
-----------

.. autoclass:: kailash.middleware.APIGateway
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autofunction:: kailash.middleware.create_gateway

The APIGateway provides RESTful API endpoints with authentication, CORS, and automatic
OpenAPI documentation generation.

**Key Features:**

- RESTful API endpoints for workflow management
- JWT authentication integration
- CORS configuration
- Automatic OpenAPI/Swagger documentation
- Health monitoring endpoints

**Usage Example:**

.. code-block:: python

   from kailash.middleware import create_gateway

   gateway = create_gateway(
       title="My Production API",
       cors_origins=["https://myapp.com"],
       enable_docs=True,
       enable_auth=True
   )

   # Gateway provides automatic endpoints:
   # POST /api/sessions - Create session
   # POST /api/workflows - Create workflow
   # POST /api/executions - Execute workflow
   # GET /health - Health check
   # GET /docs - API documentation

Real-time Middleware
--------------------

.. autoclass:: kailash.middleware.RealtimeMiddleware
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Provides real-time communication capabilities including WebSocket and Server-Sent Events
for live workflow updates.

**Key Features:**

- WebSocket bi-directional communication
- Server-Sent Events (SSE) streaming
- Event filtering and subscription management
- Webhook delivery for external integrations
- Automatic reconnection handling

**Usage Example:**

.. code-block:: python

   from kailash.middleware import RealtimeMiddleware

   realtime = RealtimeMiddleware(agent_ui)

   # Subscribe to events
   async def handle_events(event):
       print(f"Event: {event.type} - {event.data}")

   await realtime.event_stream.subscribe(
       "my_listener", handle_events
   )

AI Chat Middleware
------------------

.. autoclass:: kailash.middleware.AIChatMiddleware
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

AI-powered conversation management with natural language workflow generation capabilities.

**Key Features:**

- Natural language to workflow conversion
- Context-aware conversation management
- Vector search integration for semantic similarity
- Intent recognition and response generation
- Chat history persistence

**Usage Example:**

.. code-block:: python

   from kailash.middleware import AIChatMiddleware

   ai_chat = AIChatMiddleware(
       agent_ui,
       enable_vector_search=True,
       vector_database_url="postgresql://...",
       llm_provider="ollama"
   )

   # Start chat session
   chat_session_id = await ai_chat.start_chat_session("user123")

   # Send message
   response = await ai_chat.send_message(
       chat_session_id,
       "Create a workflow to process CSV data",
       context={"data_source": "customers.csv"}
   )

Event System
============

Event Stream
------------

.. autoclass:: kailash.middleware.EventStream
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Comprehensive event management system for handling workflow and system events.

Event Types
-----------

.. autoclass:: kailash.middleware.EventType
   :members:
   :undoc-members:

Event Filtering
---------------

.. autoclass:: kailash.middleware.EventFilter
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Event Classes
-------------

.. autoclass:: kailash.middleware.WorkflowEvent
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: kailash.middleware.NodeEvent
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: kailash.middleware.UIEvent
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Authentication & Security
=========================

JWT Authentication Manager
---------------------------

.. autoclass:: kailash.middleware.auth.jwt_auth.JWTAuthManager
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

JWT-based authentication system with token management and validation.

**Usage Example:**

.. code-block:: python

   from kailash.middleware.auth.jwt_auth import JWTAuthManager

   auth_manager = JWTAuthManager(
       secret_key="your-secret-key",
       algorithm="HS256",
       access_token_expire_minutes=30
   )

   # Create token
   token = await auth_manager.create_access_token(
       user_id="user123",
       permissions=["read", "write"]
   )

   # Verify token
   payload = await auth_manager.verify_token(token)

Access Control Manager
----------------------

.. autoclass:: kailash.middleware.auth.MiddlewareAccessControlManager
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Unified access control system supporting RBAC, ABAC, and hybrid strategies.

MCP Integration
===============

MCP Server
----------

.. autoclass:: kailash.middleware.mcp.MiddlewareMCPServer
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Enhanced MCP server with caching, metrics, and configuration management.

MCP Client
----------

.. autoclass:: kailash.middleware.mcp.MiddlewareMCPClient
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Robust MCP client with connection management and error handling.

MCP Tool Node
-------------

.. autoclass:: kailash.middleware.mcp.MCPToolNode
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

MCP tool integration as SDK nodes for workflow usage.

MCP Resource Node
-----------------

.. autoclass:: kailash.middleware.mcp.MCPResourceNode
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

MCP resource access as SDK nodes for data integration.

Database Layer
==============

Database Manager
----------------

.. autoclass:: kailash.middleware.database.MiddlewareDatabaseManager
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Database connection and transaction management for middleware persistence.

Workflow Repository
-------------------

.. autoclass:: kailash.middleware.database.MiddlewareWorkflowRepository
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Repository for workflow persistence and retrieval.

Database Models
---------------

.. autoclass:: kailash.middleware.database.WorkflowModel
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: kailash.middleware.database.WorkflowExecutionModel
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. autoclass:: kailash.middleware.database.CustomNodeModel
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Schema Generation
=================

Node Schema Generator
---------------------

.. autoclass:: kailash.middleware.NodeSchemaGenerator
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Dynamic schema generation for all SDK nodes, enabling frontend node palette creation.

Dynamic Schema Registry
------------------------

.. autoclass:: kailash.middleware.DynamicSchemaRegistry
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Caching and optimization for schema queries.

Usage Patterns
==============

Basic Middleware Stack
----------------------

.. code-block:: python

   from kailash.middleware import (
       AgentUIMiddleware,
       APIGateway,
       create_gateway,
       RealtimeMiddleware
   )

   # Create basic stack
   agent_ui = AgentUIMiddleware(max_sessions=1000)
   gateway = create_gateway(title="My App")
   gateway.agent_ui = agent_ui

   # Add real-time communication
   realtime = RealtimeMiddleware(agent_ui)

   # Start server
   gateway.run(port=8000)

Production Configuration
------------------------

.. code-block:: python

   import os
   from kailash.middleware import create_gateway

   # Environment-based configuration
   gateway = create_gateway(
       title=os.getenv("APP_TITLE", "Production App"),
       cors_origins=os.getenv("CORS_ORIGINS", "").split(","),
       enable_docs=os.getenv("DEBUG", "false").lower() == "true",
       enable_auth=True,
       jwt_secret=os.getenv("JWT_SECRET"),
       max_sessions=int(os.getenv("MAX_SESSIONS", "1000")),
       session_timeout_minutes=int(os.getenv("SESSION_TIMEOUT", "60"))
   )

Frontend Integration
--------------------

.. code-block:: javascript

   // WebSocket connection for real-time updates
   const ws = new WebSocket('ws://localhost:8000/ws?session_id=my-session');

   ws.onmessage = (event) => {
       const update = JSON.parse(event.data);
       console.log('Workflow update:', update);
   };

   // Create and execute workflow via REST API
   const response = await fetch('/api/workflows', {
       method: 'POST',
       headers: { 'Content-Type': 'application/json' },
       body: JSON.stringify({
           session_id: 'my-session',
           workflow_config: {
               nodes: [...],
               connections: [...]
           }
       })
   });

Migration Guide
===============

From Legacy API to Middleware
------------------------------

**Old Pattern (Deprecated):**

.. code-block:: python

   # ❌ OLD - Don't use
   from kailash.api.gateway import WorkflowAPIGateway

   gateway = WorkflowAPIGateway(title="App")
   gateway.register_workflow("process", workflow)

**New Pattern (Current):**

.. code-block:: python

   # ✅ NEW - Use this
   from kailash.middleware import create_gateway

   gateway = create_gateway(title="App")
   # Workflows created dynamically via API

Breaking Changes in v0.4.0
---------------------------

1. **Import Paths**: Change imports from ``kailash.api`` to ``kailash.middleware``
2. **Gateway Creation**: Use ``create_gateway()`` instead of direct class instantiation
3. **Workflow Registration**: Workflows now created dynamically instead of pre-registered
4. **Authentication**: JWT authentication now integrated, not separate

Performance Considerations
==========================

Session Management
------------------

- **Memory Usage**: Each session consumes ~1-5MB depending on workflow complexity
- **Cleanup**: Automatic session cleanup after timeout (default 60 minutes)
- **Limits**: Default maximum 1000 concurrent sessions (configurable)

Real-time Communication
-----------------------

- **WebSocket Connections**: ~100KB memory per connection
- **Event Batching**: Events batched for efficiency (default 100 events/batch)
- **Message Size**: Maximum 10MB per WebSocket message

Database Performance
--------------------

- **Connection Pooling**: Default pool size 20 connections
- **Query Optimization**: Indexed queries for workflow and execution lookups
- **Persistence**: Optional - can run in-memory for development

Testing
=======

Unit Testing
------------

.. code-block:: python

   import pytest
   from kailash.middleware import AgentUIMiddleware

   @pytest.mark.asyncio
   async def test_session_creation():
       agent_ui = AgentUIMiddleware()
       session_id = await agent_ui.create_session("test_user")
       assert session_id is not None

       session = await agent_ui.get_session(session_id)
       assert session.user_id == "test_user"

Integration Testing
-------------------

.. code-block:: python

   @pytest.mark.asyncio
   async def test_workflow_execution():
       agent_ui = AgentUIMiddleware()
       session_id = await agent_ui.create_session("test_user")

       workflow_config = {
           "name": "test_workflow",
           "nodes": [
               {
                   "id": "test_node",
                   "type": "PythonCodeNode",
                   "config": {
                       "name": "test",
                       "code": "result = {'test': True}"
                   }
               }
           ],
           "connections": []
       }

       workflow_id = await agent_ui.create_dynamic_workflow(
           session_id, workflow_config
       )

       execution_id = await agent_ui.execute_workflow(
           session_id, workflow_id, inputs={}
       )

       # Wait for completion and verify results
       results = await agent_ui.get_execution_results(
           session_id, execution_id
       )

       assert results["test_node"]["result"]["test"] is True

Related Documentation
=====================

- :doc:`gateway` - Complete API gateway documentation
- :doc:`../getting_started` - Getting started with the SDK
- :doc:`../examples/index` - Usage examples and tutorials
- :doc:`../security` - Security and authentication details
