=====
Nodes
=====

This section provides comprehensive documentation for all node types available in the Kailash SDK.

.. contents:: Table of Contents
   :local:
   :depth: 2

Base Node Classes
=================

Node
----

.. autoclass:: kailash.nodes.base.Node
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

AsyncNode
---------

.. autoclass:: kailash.nodes.base_async.AsyncNode
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

Data Nodes
==========

.. note::

   Additional data nodes are planned for future releases:

   - **XMLReader/XMLWriter**: For XML file processing
   - **ParquetReader/ParquetWriter**: For Apache Parquet columnar storage
   - **ExcelReader/ExcelWriter**: For Microsoft Excel files

   Track implementation progress in the `GitHub issues <https://github.com/your-org/kailash-sdk/issues>`_.


Data nodes handle input/output operations for various file formats and data sources.

Readers
-------

CSVReader
~~~~~~~~~

.. autoclass:: kailash.nodes.data.readers.CSVReader
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash import Workflow
   from kailash.nodes.data import CSVReader

   workflow = Workflow("csv_example")

   # Create the CSV reader node
   csv_reader = CSVReader(
       file_path="customers.csv",
       encoding="utf-8"
   )

   # Add the node to the workflow
   workflow.add_node("read_customers", csv_reader)

JSONReader
~~~~~~~~~~

.. autoclass:: kailash.nodes.data.readers.JSONReader
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("JSONReader", "read_config", config={
       "file_path": "config.json",
       "encoding": "utf-8"
   })

TextReader
~~~~~~~~~~

.. autoclass:: kailash.nodes.data.readers.TextReader
   :members:
   :undoc-members:
   :show-inheritance:



Writers
-------

CSVWriter
~~~~~~~~~

.. autoclass:: kailash.nodes.data.writers.CSVWriter
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("CSVWriter", "save_results", config={
       "file_path": "output/results.csv",
       "index": False,
       "encoding": "utf-8"
   })

JSONWriter
~~~~~~~~~~

.. autoclass:: kailash.nodes.data.writers.JSONWriter
   :members:
   :undoc-members:
   :show-inheritance:

TextWriter
~~~~~~~~~~

.. autoclass:: kailash.nodes.data.writers.TextWriter
   :members:
   :undoc-members:
   :show-inheritance:



SQLDatabaseNode
~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.data.sql.SQLDatabaseNode
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("SQLDatabaseNode", "query_orders", config={
       "connection_string": "postgresql://user:pass@host/db",
       "query": "SELECT * FROM orders WHERE status = 'active'",
       "params": {"limit": 1000}
   })

SQLQueryBuilderNode
~~~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.data.sql.SQLQueryBuilderNode
   :members:
   :undoc-members:
   :show-inheritance:

SharePoint Nodes
----------------

SharePointGraphReader
~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.data.sharepoint_graph.SharePointGraphReader
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("SharePointGraphReader", "read_docs", config={
       "tenant_id": "${TENANT_ID}",
       "client_id": "${CLIENT_ID}",
       "client_secret": "${CLIENT_SECRET}",
       "site_url": "https://company.sharepoint.com/sites/docs",
       "operation": "list_files",
       "library": "Shared Documents"
   })

SharePointGraphWriter
~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.data.sharepoint_graph.SharePointGraphWriter
   :members:
   :undoc-members:
   :show-inheritance:

Transform Nodes
===============

Transform nodes manipulate and process data.

DataFilter
----------

.. note::
   🚧 **Coming Soon** - This node is planned for a future release.

**Planned Features:**
- Column-based filtering with multiple operators
- Complex condition support (AND/OR logic)
- Null value handling
- Performance optimized for large datasets

**Alternative:** Use the :doc:`PythonCodeNode <../api/nodes>` for custom filtering logic in the meantime.

**Example Usage:**

.. code-block:: python

   # Simple equality filter
   workflow.add_node("Filter", "filter_active", config={
       "column": "status",
       "value": "active"
   })

   # Complex filter with operator
   workflow.add_node("Filter", "filter_high_value", config={
       "column": "revenue",
       "value": 10000,
       "operation": ">="
   })

DataMapper
----------

.. note::
   🚧 **Coming Soon** - This node is planned for a future release.

**Planned Features:**
- Column mapping and transformation
- Lambda function support
- Data type conversion
- Nested data structure handling

**Alternative:** Use the :doc:`PythonCodeNode <../api/nodes>` for custom mapping logic in the meantime.

**Example Usage:**

.. code-block:: python

   workflow.add_node("Map", "add_columns", config={
       "mapping": {
           "full_name": "lambda row: f'{row.first_name} {row.last_name}'",
           "is_vip": "lambda row: row.total_purchases > 10000",
           "category": "lambda row: 'Gold' if row.score > 80 else 'Silver'"
       }
   })

DataSorter
----------

.. note::
   🚧 **Coming Soon** - This node is planned for a future release.

**Planned Features:**
- Multi-column sorting
- Custom sort key functions
- Memory-efficient sorting for large datasets
- Stable sorting algorithms

**Alternative:** Use the :doc:`PythonCodeNode <../api/nodes>` for custom sorting logic in the meantime.

DataTransformer
---------------

.. autoclass:: kailash.nodes.transform.processors.DataTransformer
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("DataTransformer", "transform", config={
       "operations": [
           {"type": "rename", "old": "cust_id", "new": "customer_id"},
           {"type": "cast", "column": "age", "dtype": "int"},
           {"type": "fillna", "column": "email", "value": "unknown@example.com"},
           {"type": "drop", "columns": ["temp_field", "debug_info"]}
       ]
   })

Logic Nodes
===========

.. note::

   The **Validator** node for complex data validation rules is planned for a future release.


Logic nodes control workflow execution flow.

Switch
------

.. autoclass:: kailash.nodes.logic.operations.Switch
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("Switch", "route_by_value", config={
       "condition": "customer_segment",
       "routes": {
           "premium": "lifetime_value > 10000",
           "standard": "lifetime_value > 1000",
           "basic": "default"
       }
   })

Merge
-----

.. autoclass:: kailash.nodes.logic.operations.Merge
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("Merge", "combine_streams", config={
       "strategy": "concat",  # or "join", "union"
       "join_on": "customer_id",  # for join strategy
       "how": "left"  # for join strategy
   })

Validator
---------

.. note::
   🚧 **Coming Soon** - This node is planned for a future release.

**Planned Features:**
- Schema validation using JSON Schema
- Data quality checks
- Custom validation rules
- Error reporting and data cleansing

**Alternative:** Use the :doc:`PythonCodeNode <../api/nodes>` for custom validation logic in the meantime.

AI/ML Nodes
===========

AI and machine learning nodes for intelligent processing.

Provider Architecture
---------------------

The AI nodes use a unified provider architecture that supports multiple LLM and embedding providers:

.. automodule:: kailash.nodes.ai.ai_providers
   :members: get_provider, get_available_providers
   :undoc-members:

**Supported Providers:**

- **OpenAI**: GPT models and text embeddings
- **Anthropic**: Claude models (LLM only)
- **Ollama**: Local models for both LLM and embeddings
- **Cohere**: Embedding models
- **HuggingFace**: Embedding models (API and local)
- **Mock**: For testing without API keys

**Example: Check Available Providers**

.. code-block:: python

   from kailash.nodes.ai import get_available_providers
   
   # Check all providers
   providers = get_available_providers()
   for name, info in providers.items():
       if info['available']:
           print(f"{name}: ✓ Chat={info['chat']}, Embeddings={info['embeddings']}")
   
   # Check only LLM providers
   llm_providers = get_available_providers("chat")
   
   # Check only embedding providers
   embed_providers = get_available_providers("embeddings")

TextClassifier
--------------

.. autoclass:: kailash.nodes.ai.models.TextClassifier
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("TextClassifier", "sentiment", config={
       "model": "sentiment-analysis",
       "text_column": "review_text",
       "batch_size": 32
   })

EmbeddingGenerator
------------------

.. autoclass:: kailash.nodes.ai.embedding_generator.EmbeddingGenerator
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash.nodes.ai import EmbeddingGenerator
   
   # Single text embedding
   embedder = EmbeddingGenerator()
   result = embedder.run(
       provider="openai",
       model="text-embedding-3-large",
       input_text="This is a sample document to embed",
       operation="embed_text"
   )
   
   # Batch embedding with caching
   result = embedder.run(
       provider="huggingface",
       model="sentence-transformers/all-MiniLM-L6-v2",
       input_texts=["Document 1", "Document 2", "Document 3"],
       operation="embed_batch",
       batch_size=32,
       cache_enabled=True
   )
   
   # Calculate similarity between embeddings
   result = embedder.run(
       operation="calculate_similarity",
       embedding_1=[0.1, 0.2, 0.3, ...],
       embedding_2=[0.15, 0.25, 0.35, ...],
       similarity_metric="cosine"
   )

LLMAgent
--------

.. autoclass:: kailash.nodes.ai.llm_agent.LLMAgent
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash.nodes.ai import LLMAgent
   
   # Basic question-answering
   agent = LLMAgent()
   result = agent.run(
       provider="openai",
       model="gpt-4",
       prompt="What is the capital of France?",
       operation="qa"
   )
   
   # Conversation with memory
   result = agent.run(
       provider="anthropic",
       model="claude-3-sonnet-20240229",
       prompt="Explain quantum computing",
       operation="conversation",
       memory_config={
           "type": "window",
           "window_size": 10
       }
   )
   
   # Tool calling with functions
   result = agent.run(
       provider="openai",
       model="gpt-4",
       prompt="What's the weather in Paris?",
       operation="tool_calling",
       tools=[{
           "type": "function",
           "function": {
               "name": "get_weather",
               "description": "Get current weather",
               "parameters": {
                   "type": "object",
                   "properties": {
                       "location": {"type": "string"}
                   }
               }
           }
       }]
   )

API Nodes
=========

Nodes for external API integrations.

HTTPRequestNode
---------------

.. autoclass:: kailash.nodes.api.http.HTTPRequestNode
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash.nodes.api import HTTPRequestNode
   
   # Simple GET request
   workflow.add_node("HTTPRequestNode", "fetch_data", config={
       "url": "https://api.example.com/data",
       "method": "GET",
       "headers": {
           "Authorization": "Bearer ${API_TOKEN}"
       },
       "timeout": 30
   })
   
   # POST with authentication
   workflow.add_node("HTTPRequestNode", "create_resource", config={
       "url": "https://api.example.com/resources",
       "method": "POST",
       "auth_type": "bearer",
       "auth_token": "${API_TOKEN}",
       "json_data": {
           "name": "New Resource",
           "type": "example"
       }
   })

RESTClientNode
--------------

.. autoclass:: kailash.nodes.api.rest.RESTClientNode
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash.nodes.api import RESTClientNode
   
   # GET a resource
   workflow.add_node("RESTClientNode", "get_user", config={
       "base_url": "https://api.example.com",
       "resource": "users/{id}",
       "path_params": {"id": "123"},
       "method": "GET",
       "auth_type": "bearer",
       "auth_token": "${API_TOKEN}"
   })
   
   # Create a new resource
   workflow.add_node("RESTClientNode", "create_user", config={
       "base_url": "https://api.example.com",
       "resource": "users",
       "method": "POST",
       "data": {
           "name": "John Doe",
           "email": "john@example.com"
       },
       "version": "v2"
   })

GraphQLClient
-------------

.. note::
   🚧 **Coming Soon** - This node is planned for a future release.

**Planned Features:**
- GraphQL query and mutation support
- Variable binding and validation
- Schema introspection
- Subscription support

**Alternative:** Use the :doc:`PythonCodeNode <../api/nodes>` with GraphQL libraries in the meantime.

MCP Nodes
=========

Model Context Protocol (MCP) nodes for AI context management.

MCPClient
---------

.. autoclass:: kailash.nodes.mcp.client.MCPClient
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash.nodes.mcp import MCPClient
   
   # List available resources
   client = MCPClient()
   result = client.run(
       server_config={
           "name": "filesystem-server",
           "command": "python",
           "args": ["-m", "mcp_filesystem"]
       },
       operation="list_resources"
   )
   
   # Read a specific resource
   result = client.run(
       server_config=server_config,
       operation="read_resource",
       resource_uri="file:///path/to/document.txt"
   )
   
   # Call a tool on the server
   result = client.run(
       server_config=server_config,
       operation="call_tool",
       tool_name="create_file",
       tool_arguments={
           "path": "/path/to/new_file.txt",
           "content": "Hello, World!"
       }
   )

Code Nodes
==========

Nodes for executing custom code.

PythonCodeNode
--------------

.. autoclass:: kailash.nodes.code.python.PythonCodeNode
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   # Inline code execution
   workflow.add_node("PythonCodeNode", "process", config={
       "code": '''
   import pandas as pd

   # Access input data
   df = inputs["data"]

   # Process data
   result = df.groupby("category").agg({
       "revenue": "sum",
       "quantity": "count"
   })

   # Return results
   return {"summary": result}
   '''
   })

   # Execute from file
   workflow.add_node("PythonCodeNode", "analyze", config={
       "mode": "file",
       "file_path": "scripts/analysis.py"
   })

   # Call specific function
   workflow.add_node("PythonCodeNode", "transform", config={
       "mode": "function",
       "code": '''
   def process_data(df):
       df["processed"] = True
       return df.sort_values("timestamp")
   ''',
       "function_name": "process_data"
   })

Custom Node Development
=======================

Creating custom nodes is straightforward:

.. code-block:: python

   from kailash.nodes import Node, register_node

   @register_node("MyCustomNode")
   class MyCustomNode(Node):
       """Custom node for specific processing."""

       def validate_config(self) -> None:
           """Validate node configuration."""
           required = ["param1", "param2"]
           for param in required:
               if param not in self.config:
                   raise ValueError(f"Missing required parameter: {param}")

       def execute(self, inputs: dict) -> dict:
           """Execute the node logic."""
           # Access configuration
           param1 = self.config["param1"]
           param2 = self.config["param2"]

           # Process inputs
           data = inputs.get("data")
           if data is None:
               raise ValueError("No input data provided")

           # Your custom logic here
           result = self.process_data(data, param1, param2)

           # Return outputs
           return {"processed_data": result}

       def process_data(self, data, param1, param2):
           """Custom processing logic."""
           # Implementation here
           return data

For async operations:

.. code-block:: python

   from kailash.nodes import AsyncNode
   import aiohttp

   @register_node("AsyncAPINode")
   class AsyncAPINode(AsyncNode):
       """Async node for API calls."""

       async def execute(self, inputs: dict) -> dict:
           """Execute async API call."""
           url = self.config["url"]

           async with aiohttp.ClientSession() as session:
               async with session.get(url) as response:
                   data = await response.json()

           return {"api_response": data}

Node Configuration Best Practices
=================================

1. **Use Environment Variables for Secrets**

.. code-block:: python

   workflow.add_node("RESTClientNode", "api", config={
       "auth": {
           "token": "${API_TOKEN}"  # Resolved from environment
       }
   })

2. **Provide Sensible Defaults**

.. code-block:: python

   class MyNode(Node):
       def validate_config(self):
           # Set defaults
           self.config.setdefault("timeout", 30)
           self.config.setdefault("retry_count", 3)

3. **Validate Early and Clearly**

.. code-block:: python

   def validate_config(self):
       if not os.path.exists(self.config["file_path"]):
           raise ValueError(f"File not found: {self.config['file_path']}")

4. **Document Configuration Options**

.. code-block:: python

   class MyNode(Node):
       """
       My custom node.

       Config:
           file_path (str): Path to input file
           encoding (str, optional): File encoding. Defaults to 'utf-8'
           skip_errors (bool, optional): Skip errors. Defaults to False
       """

See Also
========

- :doc:`/guides/custom_nodes` - Guide to creating custom nodes
- :doc:`/best_practices` - Best practices for node usage
- :doc:`/examples/index` - Example workflows using various nodes
