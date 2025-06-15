Workflow API Wrapper
====================

The Workflow API Wrapper module provides a simple way to expose any Kailash workflow
as a REST API. This enables external applications to execute workflows without
requiring the Kailash SDK.

Overview
--------

The API wrapper transforms workflows into production-ready REST APIs with minimal
configuration::

    # This import is deprecated - use middleware instead
    # from kailash.middleware import create_gateway

    # Any workflow becomes an API in 3 lines
    api = WorkflowAPI(workflow)
    api.run(port=8000)

Core Components
---------------

WorkflowAPI Class
~~~~~~~~~~~~~~~~~

.. note::
   This functionality has been replaced by the middleware architecture.
   See :doc:`middleware` for current API implementation.

   The main API wrapper class that provides REST endpoints for workflow execution.

   **Key Features:**

   - Automatic endpoint generation
   - Multiple execution modes (sync, async, streaming)
   - Built-in OpenAPI documentation
   - Request validation
   - Error handling

HierarchicalRAGAPI Class
~~~~~~~~~~~~~~~~~~~~~~~~

.. note::
   This functionality has been replaced by the middleware architecture.

   Specialized API wrapper for Hierarchical RAG workflows with domain-specific endpoints.

Factory Functions
~~~~~~~~~~~~~~~~~

.. note::
   This functionality has been replaced by the middleware architecture.

   Factory function to create appropriate API wrappers based on workflow type.

Request/Response Models
-----------------------

WorkflowRequest
~~~~~~~~~~~~~~~

.. note::
   This functionality has been replaced by the middleware architecture.

WorkflowResponse
~~~~~~~~~~~~~~~~

.. note::
   This functionality has been replaced by the middleware architecture.

ExecutionMode
~~~~~~~~~~~~~

.. note::
   This functionality has been replaced by the middleware architecture.

Usage Examples
--------------

Basic Usage
~~~~~~~~~~~

Expose a simple workflow as an API::

    from kailash.workflow.graph import Workflow
    # This import is deprecated - use middleware instead
    # from kailash.middleware import create_gateway

    # Create your workflow
    workflow = Workflow("my_workflow", name="My Workflow")
    workflow.add_node("filter", "Filter")

    # Expose as API
    api = WorkflowAPI(workflow)
    api.run(port=8000)

The API will be available at:

- ``POST /execute`` - Execute the workflow
- ``GET /workflow/info`` - Get workflow metadata
- ``GET /health`` - Health check
- ``GET /docs`` - Interactive API documentation

Synchronous Execution
~~~~~~~~~~~~~~~~~~~~~

Execute a workflow and wait for results::

    curl -X POST http://localhost:8000/execute \
      -H "Content-Type: application/json" \
      -d '{
        "inputs": {
          "filter": {
            "data": [1, 2, 3, 4, 5],
            "operator": ">",
            "value": 3
          }
        },
        "mode": "sync"
      }'

Response::

    {
      "outputs": {
        "filter": {
          "filtered_data": [4, 5]
        }
      },
      "execution_time": 0.025,
      "workflow_id": "my_workflow",
      "version": "1.0.0"
    }

Asynchronous Execution
~~~~~~~~~~~~~~~~~~~~~~

Start workflow execution and check status later::

    # Start execution
    curl -X POST http://localhost:8000/execute \
      -H "Content-Type: application/json" \
      -d '{
        "inputs": {...},
        "mode": "async"
      }'

    # Response
    {
      "execution_id": "123e4567-e89b-12d3-a456-426614174000",
      "status": "pending",
      "message": "Execution started. Check status at /status/123e4567..."
    }

    # Check status
    curl http://localhost:8000/status/123e4567-e89b-12d3-a456-426614174000

Custom Endpoints
~~~~~~~~~~~~~~~~

Add custom endpoints to the API::

    api = WorkflowAPI(workflow)

    @api.app.get("/custom/info")
    async def custom_info():
        return {
            "workflow_name": workflow.name,
            "custom_data": "Additional information"
        }

    api.run(port=8000)

Production Deployment
---------------------

Development Mode
~~~~~~~~~~~~~~~~

For development with auto-reload::

    api.run(
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="debug"
    )

Production Configuration
~~~~~~~~~~~~~~~~~~~~~~~~

For production deployment::

    api.run(
        host="0.0.0.0",
        port=80,
        workers=4,
        log_level="info",
        access_log=False
    )

HTTPS Support
~~~~~~~~~~~~~

Enable SSL/TLS for secure communication::

    api.run(
        host="0.0.0.0",
        port=443,
        ssl_keyfile="/path/to/key.pem",
        ssl_certfile="/path/to/cert.pem"
    )

Docker Deployment
~~~~~~~~~~~~~~~~~

Example Dockerfile::

    FROM python:3.11-slim

    WORKDIR /app
    COPY . .

    RUN pip install kailash

    EXPOSE 8000

    CMD ["python", "-m", "kailash.api.workflow_api", "my_workflow.yaml"]

Advanced Features
-----------------

Middleware Integration
~~~~~~~~~~~~~~~~~~~~~~

Add CORS support::

    from fastapi.middleware.cors import CORSMiddleware

    api.app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"]
    )

Authentication
~~~~~~~~~~~~~~

Add authentication to endpoints::

    from fastapi import Depends
    from fastapi.security import HTTPBearer

    security = HTTPBearer()

    @api.app.post("/secure/execute")
    async def secure_execute(
        request: WorkflowRequest,
        credentials = Depends(security)
    ):
        # Verify credentials
        # Execute workflow
        pass

Rate Limiting
~~~~~~~~~~~~~

Implement rate limiting::

    from slowapi import Limiter
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address)
    api.app.state.limiter = limiter

    @api.app.post("/execute")
    @limiter.limit("10/minute")
    async def rate_limited_execute(request: WorkflowRequest):
        return await api._execute_sync(request)

Specialized APIs
----------------

RAG API Example
~~~~~~~~~~~~~~~

Create a specialized API for RAG workflows::

    # This import is deprecated - use middleware instead
    # from kailash.middleware import create_gateway

    # Create RAG-specific API
    api = create_workflow_api(
        rag_workflow,
        api_type="rag",
        app_name="RAG Service",
        description="Hierarchical RAG API"
    )

    # Additional endpoints:
    # POST /documents - Add documents
    # POST /query - Query with RAG

    api.run(port=8001)

Best Practices
--------------

1. **Error Handling**: The API wrapper includes automatic error handling and returns
appropriate HTTP status codes.

2. **Validation**: Input validation is performed automatically using Pydantic models.

3. **Documentation**: OpenAPI documentation is generated automatically at ``/docs``.

4. **Monitoring**: Use the ``/health`` endpoint for monitoring and load balancer health
checks.

5. **Scaling**: Use multiple workers for production deployments to handle concurrent
requests.

6. **Security**: Always use HTTPS in production and implement proper authentication.

See Also
--------

- :doc:`/api/workflow` - Workflow creation and management
- :doc:`/api/runtime` - Workflow execution runtimes
- :doc:`/examples/integration` - Integration examples
- `FastAPI Documentation <https://fastapi.tiangolo.com/>`_
