MCP Server Development
======================

This guide covers building production-ready MCP servers with the Kailash SDK.

Server Basics
-------------

Creating a Server
~~~~~~~~~~~~~~~~~

.. code-block:: python

   from kailash.mcp_server import MCPServer

   # Basic server
   server = MCPServer("my-server")

   # Server with configuration
   server = MCPServer(
       "configured-server",
       config={
           "host": "0.0.0.0",
           "port": 8080,
           "enable_metrics": True,
           "enable_cache": True,
           "cache_ttl": 300
       }
   )

Tool Development
----------------

Basic Tools
~~~~~~~~~~~

.. code-block:: python

   @server.tool()
   def echo(message: str) -> dict:
       """Echo back a message."""
       return {"echo": message}

   @server.tool()
   def add_numbers(a: float, b: float) -> dict:
       """Add two numbers."""
       return {"result": a + b}

Tools with Validation
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from pydantic import BaseModel, Field, validator

   class SearchRequest(BaseModel):
       query: str = Field(..., min_length=1, max_length=100)
       limit: int = Field(10, ge=1, le=100)
       offset: int = Field(0, ge=0)

       @validator('query')
       def clean_query(cls, v):
           return v.strip()

   @server.tool()
   def search(request: SearchRequest) -> dict:
       """Search with validated parameters."""
       results = database.search(
           request.query,
           limit=request.limit,
           offset=request.offset
       )
       return {
           "results": results,
           "total": len(results),
           "query": request.query
       }

Async Tools
~~~~~~~~~~~

.. code-block:: python

   import httpx

   @server.tool()
   async def fetch_data(url: str, headers: dict = None) -> dict:
       """Fetch data from URL asynchronously."""
       async with httpx.AsyncClient() as client:
           response = await client.get(url, headers=headers)
           return {
               "status": response.status_code,
               "data": response.json() if response.status_code == 200 else None,
               "headers": dict(response.headers)
           }

Tools with Caching
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   @server.tool(cache_key="weather_{city}_{date}")
   async def get_weather(city: str, date: str = None) -> dict:
       """Get weather with caching by city and date."""
       if date is None:
           date = datetime.now().strftime("%Y-%m-%d")

       # Expensive API call - will be cached
       weather_data = await fetch_weather_api(city, date)

       return {
           "city": city,
           "date": date,
           "weather": weather_data
       }

Error Handling
~~~~~~~~~~~~~~

.. code-block:: python

   from kailash.mcp_server.errors import (
       ToolExecutionError,
       ValidationError,
       ResourceNotFoundError
   )

   @server.tool()
   def divide(a: float, b: float) -> dict:
       """Divide with proper error handling."""
       if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
           raise ValidationError("Inputs must be numbers")

       if b == 0:
           raise ToolExecutionError(
               "Division by zero",
               details={"numerator": a, "denominator": b},
               suggestions=["Check denominator is non-zero"]
           )

       return {"result": a / b}

Resource Management
-------------------

Static Resources
~~~~~~~~~~~~~~~~

.. code-block:: python

   @server.resource()
   async def api_documentation() -> dict:
       """Provide API documentation."""
       return {
           "version": "1.0",
           "endpoints": {
               "search": "Search the database",
               "calculate": "Perform calculations"
           },
           "authentication": "Bearer token required"
       }

Dynamic Resources
~~~~~~~~~~~~~~~~~

.. code-block:: python

   @server.resource()
   async def system_status() -> dict:
       """Provide current system status."""
       return {
           "status": "healthy",
           "uptime": get_uptime(),
           "cpu_usage": get_cpu_usage(),
           "memory": get_memory_info(),
           "timestamp": datetime.now().isoformat()
       }

Cached Resources
~~~~~~~~~~~~~~~~

.. code-block:: python

   @server.resource(cache_ttl=300)  # Cache for 5 minutes
   async def database_schema() -> dict:
       """Provide database schema with caching."""
       # Expensive operation - will be cached
       tables = await get_all_tables()
       schema = {}

       for table in tables:
           schema[table] = await get_table_schema(table)

       return {
           "schema": schema,
           "table_count": len(tables),
           "generated_at": datetime.now().isoformat()
       }

Authentication
--------------

Bearer Token
~~~~~~~~~~~~

.. code-block:: python

   from kailash.mcp_server.auth import BearerTokenAuth

   auth = BearerTokenAuth(token="secret-token")
   server = MCPServer("secure-server", auth=auth)

API Key
~~~~~~~

.. code-block:: python

   from kailash.mcp_server.auth import APIKeyAuth

   auth = APIKeyAuth(
       api_keys=["key1", "key2", "key3"],
       header_name="X-API-Key"
   )
   server = MCPServer("api-server", auth=auth)

JWT Authentication
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from kailash.mcp_server.auth import JWTAuth

   auth = JWTAuth(
       secret_key="your-secret-key",
       algorithm="HS256",
       verify_exp=True,
       verify_aud=True,
       audience="mcp-server"
   )
   server = MCPServer("jwt-server", auth=auth)

Custom Authentication
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from kailash.mcp_server.auth import AuthHandler

   class DatabaseAuth(AuthHandler):
       def __init__(self, db_connection):
           self.db = db_connection

       async def authenticate(self, request):
           # Get token from header
           auth_header = request.headers.get("Authorization")
           if not auth_header or not auth_header.startswith("Bearer "):
               raise AuthenticationError("Missing bearer token")

           token = auth_header[7:]  # Remove "Bearer "

           # Validate token against database
           user = await self.db.get_user_by_token(token)
           if not user:
               raise AuthenticationError("Invalid token")

           # Return user context
           return {
               "user_id": user.id,
               "username": user.username,
               "roles": user.roles,
               "permissions": user.permissions
           }

   auth = DatabaseAuth(db_connection)
   server = MCPServer("db-auth-server", auth=auth)

Tool Authorization
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   @server.tool(requires_auth=True)
   def admin_operation(action: str, user_context: dict) -> dict:
       """Operation requiring admin role."""
       if "admin" not in user_context.get("roles", []):
           raise PermissionError("Admin role required")

       # Perform admin operation
       result = perform_admin_action(action, user_context["user_id"])

       return {"result": result, "performed_by": user_context["username"]}

Advanced Features
-----------------

Middleware
~~~~~~~~~~

.. code-block:: python

   from kailash.mcp_server import Middleware

   class LoggingMiddleware(Middleware):
       async def process_request(self, request, context):
           print(f"Request: {request.tool} from {context.get('user_id', 'anonymous')}")
           return request

       async def process_response(self, response, context):
           print(f"Response: {response.success} in {response.duration}ms")
           return response

   server.add_middleware(LoggingMiddleware())

Rate Limiting
~~~~~~~~~~~~~

.. code-block:: python

   from kailash.mcp_server.middleware import RateLimiter

   # Global rate limit
   rate_limiter = RateLimiter(
       max_requests=100,
       window_seconds=60
   )
   server.add_middleware(rate_limiter)

   # Per-tool rate limit
   @server.tool(rate_limit={"max_requests": 10, "window": 60})
   def expensive_operation(data: dict) -> dict:
       """Rate-limited expensive operation."""
       return process_expensive(data)

Metrics and Monitoring
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Enable metrics
   server = MCPServer(
       "monitored-server",
       enable_metrics=True,
       metrics_config={
           "export_interval": 60,
           "include_latencies": True,
           "include_errors": True
       }
   )

   # Custom metrics
   @server.tool()
   def process_order(order: dict) -> dict:
       start = time.time()

       try:
           result = process(order)
           server.metrics.increment("orders.processed")
           server.metrics.histogram("order.value", order["total"])
           return result
       except Exception as e:
           server.metrics.increment("orders.failed")
           raise
       finally:
           duration = time.time() - start
           server.metrics.histogram("orders.duration", duration)

Server Lifecycle
----------------

Starting the Server
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   async def main():
       # Initialize resources
       await initialize_database()
       await load_configuration()

       try:
           # Start server
           print(f"Starting server on port {config.port}")
           await server.start(
               host=config.host,
               port=config.port
           )

           # Keep running
           await asyncio.Event().wait()

       except KeyboardInterrupt:
           print("Shutting down...")
       finally:
           # Cleanup
           await server.shutdown()
           await cleanup_resources()

Health Checks
~~~~~~~~~~~~~

.. code-block:: python

   @server.tool()
   def health() -> dict:
       """Health check endpoint."""
       checks = {
           "server": "ok",
           "database": check_database_health(),
           "cache": check_cache_health(),
           "external_api": check_external_api_health()
       }

       all_healthy = all(v == "ok" for v in checks.values())

       return {
           "status": "healthy" if all_healthy else "degraded",
           "checks": checks,
           "timestamp": datetime.now().isoformat(),
           "version": SERVER_VERSION
       }

Graceful Shutdown
~~~~~~~~~~~~~~~~~

.. code-block:: python

   import signal

   class GracefulServer:
       def __init__(self):
           self.server = MCPServer("graceful-server")
           self.shutdown_event = asyncio.Event()

       async def start(self):
           # Register signal handlers
           for sig in (signal.SIGTERM, signal.SIGINT):
               signal.signal(sig, self.handle_shutdown)

           await self.server.start()

           # Wait for shutdown
           await self.shutdown_event.wait()

           # Graceful shutdown
           print("Graceful shutdown initiated...")
           await self.server.shutdown(timeout=30)
           print("Server stopped")

       def handle_shutdown(self, signum, frame):
           print(f"Received signal {signum}")
           self.shutdown_event.set()

Testing
-------

Unit Testing Tools
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   import pytest
   from kailash.mcp_server import MCPServer

   @pytest.fixture
   def test_server():
       server = MCPServer("test-server")

       @server.tool()
       def add(a: int, b: int) -> dict:
           return {"result": a + b}

       return server

   async def test_add_tool(test_server):
       # Direct tool testing
       result = await test_server.call_tool("add", {"a": 5, "b": 3})
       assert result["result"] == 8

   async def test_tool_validation(test_server):
       # Test validation
       with pytest.raises(ValidationError):
           await test_server.call_tool("add", {"a": "not a number", "b": 3})

Integration Testing
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   @pytest.mark.integration
   async def test_server_client_integration():
       # Start server
       server = MCPServer("integration-test")

       @server.tool()
       def echo(msg: str) -> dict:
           return {"echo": msg}

       await server.start(host="localhost", port=0)  # Random port
       port = server.get_port()

       # Test with client
       client = MCPClient("test-client")
       await client.connect(f"mcp://localhost:{port}")

       result = await client.call_tool("echo", {"msg": "test"})
       assert result["echo"] == "test"

       # Cleanup
       await client.disconnect()
       await server.shutdown()

Best Practices
--------------

1. **Tool Design**
   - Keep tools focused and single-purpose
   - Use clear, descriptive names
   - Provide comprehensive docstrings
   - Validate inputs thoroughly

2. **Error Handling**
   - Use specific error types
   - Include helpful error messages
   - Provide error details and suggestions
   - Log errors for debugging

3. **Performance**
   - Cache expensive operations
   - Use async for I/O operations
   - Implement rate limiting
   - Monitor resource usage

4. **Security**
   - Always use authentication in production
   - Validate and sanitize all inputs
   - Use HTTPS/TLS for network transport
   - Implement proper authorization

5. **Monitoring**
   - Enable metrics collection
   - Set up health checks
   - Log important events
   - Monitor error rates

Next Steps
----------

- :doc:`deployment` - Deploy to production
- :doc:`authentication` - Advanced authentication
- :doc:`service_discovery` - Multi-server setups
- :doc:`examples` - Complete examples
