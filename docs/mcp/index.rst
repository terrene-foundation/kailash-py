Model Context Protocol (MCP)
============================

The Model Context Protocol (MCP) provides a standardized way for AI applications to interact with external tools and resources. Kailash SDK offers comprehensive MCP support through servers, clients, and LLM agent integration.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   overview
   quickstart
   server_development
   architecture
   deployment
   monitoring
   security
   examples
   troubleshooting
   api-reference

Overview
--------

MCP enables:

- **Standardized Tool Access**: Consistent interface for AI agents to use tools
- **Resource Management**: Access to data, configurations, and knowledge bases
- **Service Discovery**: Automatic discovery of available services
- **Authentication**: Secure access control for tools and resources
- **High Availability**: Load balancing and failover support

Key Components
--------------

1. **MCP Servers**: Expose tools and resources
2. **MCP Clients**: Connect to and use MCP servers
3. **LLM Integration**: AI agents that can discover and use MCP tools
4. **Service Discovery**: Find and connect to available services
5. **Authentication**: Secure access control

Quick Example
-------------

.. code-block:: python

   from kailash.mcp_server import MCPServer

   # Create server
   server = MCPServer("my-server")

   @server.tool()
   def calculate(a: int, b: int, operation: str) -> dict:
       """Perform calculations."""
       ops = {
           "add": a + b,
           "subtract": a - b,
           "multiply": a * b,
           "divide": a / b if b != 0 else None
       }
       return {"result": ops.get(operation)}

   # Start server
   await server.start(host="0.0.0.0", port=8080)

Use Cases
---------

- **AI Tool Integration**: Give LLMs access to external tools
- **Microservices**: Build tool-based microservice architectures
- **API Gateways**: Expose existing APIs as MCP tools
- **Data Processing**: Create reusable data processing tools
- **Enterprise Integration**: Connect AI to enterprise systems

Getting Started
---------------

1. Install Kailash SDK with MCP support
2. Choose between building a server or client
3. Follow the quickstart guide for your use case
4. Explore advanced features as needed

Next Steps
----------

- :doc:`quickstart` - Get started in 5 minutes
- :doc:`server_development` - Build your first MCP server
- :doc:`examples` - See complete examples
- :doc:`api-reference` - Detailed API documentation
