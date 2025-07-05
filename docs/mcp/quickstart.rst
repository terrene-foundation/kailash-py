MCP Quick Start
===============

This guide will help you get started with MCP in 5 minutes.

Installation
------------

First, ensure you have Kailash SDK installed:

.. code-block:: bash

   pip install kailash

Your First MCP Server
---------------------

Create a simple MCP server with basic tools:

.. code-block:: python

   # mcp_server.py
   import asyncio
   from kailash.mcp_server import MCPServer

   # Create server
   server = MCPServer("quickstart-server")

   # Add a simple tool
   @server.tool()
   def greet(name: str) -> dict:
       """Greet someone by name."""
       return {"greeting": f"Hello, {name}!"}

   # Add a calculation tool
   @server.tool()
   def calculate(a: float, b: float, operation: str) -> dict:
       """Perform basic calculations."""
       operations = {
           "add": a + b,
           "subtract": a - b,
           "multiply": a * b,
           "divide": a / b if b != 0 else "Error: Division by zero"
       }
       result = operations.get(operation, "Error: Unknown operation")
       return {"result": result, "operation": operation}

   # Add a resource
   @server.resource()
   async def server_info() -> dict:
       """Provide server information."""
       return {
           "name": "QuickStart Server",
           "version": "1.0.0",
           "tools": ["greet", "calculate"]
       }

   # Run the server
   async def main():
       print("Starting MCP server on port 8080...")
       await server.start(host="0.0.0.0", port=8080)
       print("Server running. Press Ctrl+C to stop.")

       try:
           await asyncio.Event().wait()
       except KeyboardInterrupt:
           print("Shutting down...")
       finally:
           await server.shutdown()

   if __name__ == "__main__":
       asyncio.run(main())

Run the server:

.. code-block:: bash

   python mcp_server.py

Your First MCP Client
---------------------

Create a client to connect to your server:

.. code-block:: python

   # mcp_client.py
   import asyncio
   from kailash.mcp_server import MCPClient

   async def main():
       # Create client
       client = MCPClient("quickstart-client")

       try:
           # Connect to server
           print("Connecting to MCP server...")
           await client.connect("mcp://localhost:8080")
           print("Connected!")

           # List available tools
           tools = await client.list_tools()
           print(f"\nAvailable tools: {list(tools.keys())}")

           # Use the greet tool
           result = await client.call_tool("greet", {"name": "World"})
           print(f"\nGreet result: {result}")

           # Use the calculate tool
           result = await client.call_tool("calculate", {
               "a": 10,
               "b": 5,
               "operation": "multiply"
           })
           print(f"Calculate result: {result}")

           # Get server info resource
           info = await client.get_resource("server_info")
           print(f"\nServer info: {info}")

       finally:
           await client.disconnect()
           print("\nDisconnected")

   if __name__ == "__main__":
       asyncio.run(main())

Run the client:

.. code-block:: bash

   python mcp_client.py

LLM Agent with MCP
------------------

Use MCP tools with an LLM agent:

.. code-block:: python

   # mcp_agent.py
   import asyncio
   from kailash.core import LocalRuntime
   from kailash.nodes.ai import LLMAgentNode

   async def main():
       # Create runtime and agent
       runtime = LocalRuntime()

       # Create agent with MCP integration
       agent = LLMAgentNode(
           name="assistant",
           llm_config={
               "model": "gpt-4",  # or "ollama/llama2"
               "temperature": 0.7
           },
           mcp_servers=["mcp://localhost:8080"],
           enable_mcp=True,
           system_prompt="You are a helpful assistant with access to calculation tools."
       )

       # Test the agent
       messages = [
           {"role": "user", "content": "Hi! Can you greet Alice for me?"},
           {"role": "user", "content": "What's 15 multiplied by 7?"},
           {"role": "user", "content": "What tools do you have available?"}
       ]

       for message in messages:
           print(f"\nUser: {message['content']}")

           result = await agent.process({
               "messages": [message]
           })

           print(f"Assistant: {result['response']['content']}")

           if result.get('tools_used'):
               print(f"Tools used: {result['tools_used']}")

   if __name__ == "__main__":
       asyncio.run(main())

Complete Example: Math Tutor
----------------------------

Here's a complete example of an MCP-powered math tutor:

.. code-block:: python

   # math_tutor_server.py
   import asyncio
   import math
   from kailash.mcp_server import MCPServer

   server = MCPServer("math-tutor")

   @server.tool()
   def solve_quadratic(a: float, b: float, c: float) -> dict:
       """Solve quadratic equation ax² + bx + c = 0"""
       discriminant = b**2 - 4*a*c

       if discriminant < 0:
           return {
               "solutions": "No real solutions",
               "discriminant": discriminant
           }
       elif discriminant == 0:
           x = -b / (2*a)
           return {
               "solutions": [x],
               "discriminant": discriminant
           }
       else:
           x1 = (-b + math.sqrt(discriminant)) / (2*a)
           x2 = (-b - math.sqrt(discriminant)) / (2*a)
           return {
               "solutions": [x1, x2],
               "discriminant": discriminant
           }

   @server.tool()
   def calculate_stats(numbers: list[float]) -> dict:
       """Calculate statistics for a list of numbers"""
       if not numbers:
           return {"error": "Empty list"}

       n = len(numbers)
       mean = sum(numbers) / n

       # Calculate variance
       variance = sum((x - mean) ** 2 for x in numbers) / n
       std_dev = math.sqrt(variance)

       return {
           "count": n,
           "mean": mean,
           "min": min(numbers),
           "max": max(numbers),
           "std_dev": std_dev,
           "sum": sum(numbers)
       }

   @server.tool()
   def explain_concept(topic: str) -> dict:
       """Explain a math concept"""
       explanations = {
           "quadratic": "A quadratic equation is a polynomial equation of degree 2. The general form is ax² + bx + c = 0, where a ≠ 0.",
           "mean": "The mean (average) is the sum of all values divided by the number of values.",
           "variance": "Variance measures how spread out numbers are from their average value."
       }

       explanation = explanations.get(
           topic.lower(),
           f"I don't have a specific explanation for '{topic}' yet."
       )

       return {"explanation": explanation, "topic": topic}

   async def main():
       print("Math Tutor MCP Server starting...")
       await server.start(host="0.0.0.0", port=8080)
       print("Server running on port 8080")

       try:
           await asyncio.Event().wait()
       except KeyboardInterrupt:
           await server.shutdown()

   if __name__ == "__main__":
       asyncio.run(main())

Next Steps
----------

Now that you have MCP running:

1. **Explore More Tools**: Add more complex tools to your server
2. **Add Authentication**: Secure your MCP server
3. **Try Service Discovery**: Use multiple MCP servers
4. **Build Production Apps**: See deployment guide

Useful Resources
----------------

- :doc:`server_development` - Build production MCP servers
- :doc:`client_development` - Advanced client features
- :doc:`agent_integration` - LLM integration patterns
- :doc:`examples` - More complete examples

Common Issues
-------------

**Connection Refused**
   Make sure the MCP server is running before starting the client.

**Tool Not Found**
   Check that the tool name matches exactly (case-sensitive).

**Import Errors**
   Ensure Kailash SDK is installed: ``pip install kailash``

**Async Errors**
   Remember to use ``await`` with async functions and ``asyncio.run()`` for main.
