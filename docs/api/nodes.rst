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

XMLReader
~~~~~~~~~

.. autoclass:: kailash.nodes.data.readers.XMLReader
   :members:
   :undoc-members:
   :show-inheritance:

ParquetReader
~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.data.readers.ParquetReader
   :members:
   :undoc-members:
   :show-inheritance:

ExcelReader
~~~~~~~~~~~

.. autoclass:: kailash.nodes.data.readers.ExcelReader
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

ParquetWriter
~~~~~~~~~~~~~

.. autoclass:: kailash.nodes.data.writers.ParquetWriter
   :members:
   :undoc-members:
   :show-inheritance:

ExcelWriter
~~~~~~~~~~~

.. autoclass:: kailash.nodes.data.writers.ExcelWriter
   :members:
   :undoc-members:
   :show-inheritance:

Database Nodes
--------------

SQLReader
~~~~~~~~~

.. autoclass:: kailash.nodes.data.sql.SQLReader
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("SQLReader", "query_orders", config={
       "connection_string": "postgresql://user:pass@host/db",
       "query": "SELECT * FROM orders WHERE status = 'active'",
       "params": {"limit": 1000}
   })

SQLWriter
~~~~~~~~~

.. autoclass:: kailash.nodes.data.sql.SQLWriter
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

.. autoclass:: kailash.nodes.transform.processors.DataFilter
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   # Simple equality filter
   workflow.add_node("DataFilter", "filter_active", config={
       "column": "status",
       "value": "active"
   })

   # Complex filter with operator
   workflow.add_node("DataFilter", "filter_high_value", config={
       "column": "revenue",
       "value": 10000,
       "operation": ">="
   })

DataMapper
----------

.. autoclass:: kailash.nodes.transform.processors.DataMapper
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("DataMapper", "add_columns", config={
       "mapping": {
           "full_name": "lambda row: f'{row.first_name} {row.last_name}'",
           "is_vip": "lambda row: row.total_purchases > 10000",
           "category": "lambda row: 'Gold' if row.score > 80 else 'Silver'"
       }
   })

DataSorter
----------

.. autoclass:: kailash.nodes.transform.processors.DataSorter
   :members:
   :undoc-members:
   :show-inheritance:

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

.. autoclass:: kailash.nodes.logic.operations.Validator
   :members:
   :undoc-members:
   :show-inheritance:

AI/ML Nodes
===========

AI and machine learning nodes for intelligent processing.

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

.. autoclass:: kailash.nodes.ai.models.EmbeddingGenerator
   :members:
   :undoc-members:
   :show-inheritance:

LLMAgent
--------

.. autoclass:: kailash.nodes.ai.agents.LLMAgent
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("LLMAgent", "analyze", config={
       "model": "gpt-4",
       "prompt_template": "Analyze the following customer feedback: {feedback}",
       "temperature": 0.7,
       "max_tokens": 500
   })

API Nodes
=========

Nodes for external API integrations.

HTTPClient
----------

.. autoclass:: kailash.nodes.api.http.HTTPClient
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("HTTPClient", "fetch_data", config={
       "url": "https://api.example.com/data",
       "method": "GET",
       "headers": {
           "Authorization": "Bearer ${API_TOKEN}"
       },
       "timeout": 30
   })

RESTClient
----------

.. autoclass:: kailash.nodes.api.rest.RESTClient
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   workflow.add_node("RESTClient", "api_call", config={
       "base_url": "https://api.example.com",
       "endpoint": "/users/{user_id}",
       "method": "PUT",
       "auth": {
           "type": "bearer",
           "token": "${API_TOKEN}"
       },
       "retry": {
           "max_attempts": 3,
           "backoff_factor": 2
       }
   })

GraphQLClient
-------------

.. autoclass:: kailash.nodes.api.graphql.GraphQLClient
   :members:
   :undoc-members:
   :show-inheritance:

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

   workflow.add_node("RESTClient", "api", config={
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

- :doc:`../guides/custom_nodes` - Guide to creating custom nodes
- :doc:`../guides/best_practices` - Best practices for node usage
- :doc:`../examples/index` - Example workflows using various nodes
