=====
Nodes
=====

Nodes are the fundamental building blocks of Kailash workflows. Each node performs
a specific operation -- reading data, transforming it, calling an API, or running
custom code.

Node Basics
===========

Every node has:

- **Type**: A string identifying the node class (e.g., ``"PythonCodeNode"``)
- **ID**: A unique string identifier within the workflow
- **Config**: A dictionary of parameters controlling behavior

.. code-block:: python

   from kailash.workflow.builder import WorkflowBuilder

   workflow = WorkflowBuilder()
   workflow.add_node("PythonCodeNode", "my_node", {
       "code": "result = {'value': 42}"
   })

Node Categories
===============

Data Nodes
----------

For reading and writing data:

- **CSVReaderNode** / **CSVWriterNode**: CSV file operations
- **JSONReaderNode** / **JSONWriterNode**: JSON file operations
- **TextReaderNode** / **TextWriterNode**: Plain text operations
- **AsyncSQLDatabaseNode**: Async database queries with parameterized SQL

.. code-block:: python

   workflow.add_node("CSVReaderNode", "read_csv", {
       "file_path": "data.csv"
   })

   workflow.add_node("AsyncSQLDatabaseNode", "query_db", {
       "connection_string": os.environ.get("DATABASE_URL"),
       "query": "SELECT * FROM users WHERE active = $1",
       "parameter_types": ["BOOLEAN"]
   })

AI / LLM Nodes
---------------

For AI and language model operations:

- **LLMAgentNode**: Single LLM call with prompt
- **IterativeLLMAgentNode**: Multi-turn LLM interactions
- **EmbeddingGeneratorNode**: Generate vector embeddings

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")

   workflow.add_node("LLMAgentNode", "analyzer", {
       "model": model,
       "prompt": "Analyze: {input_text}"
   })

.. warning::

   Never hardcode model names. Always read from environment variables.

Logic Nodes
-----------

For workflow control flow:

- **SwitchNode**: Conditional routing based on data values
- **MergeNode**: Combine multiple data streams

.. code-block:: python

   workflow.add_node("SwitchNode", "router", {
       "condition_field": "priority",
       "routes": {
           "high": "value == 'high'",
           "low": "default"
       }
   })

Code Nodes
----------

For custom logic:

- **PythonCodeNode**: Execute Python code in a sandboxed environment
- **CodeExecutor**: Full async execution pipeline for custom nodes

.. code-block:: python

   workflow.add_node("PythonCodeNode", "custom_logic", {
       "code": """
   # Access input data
   processed = [item * 2 for item in input_data]
   result = {'processed': processed, 'count': len(processed)}
   """
   })

Custom Nodes
============

Create custom nodes by subclassing ``BaseNode``:

.. code-block:: python

   from kailash.nodes.base import BaseNode, NodeParameter
   from typing import Dict, Any

   class MyCustomNode(BaseNode):
       """A custom node that doubles input values."""

       @classmethod
       def get_node_type(cls) -> str:
           return "MyCustomNode"

       def get_parameters(self) -> Dict[str, NodeParameter]:
           return {
               "multiplier": NodeParameter(
                   name="multiplier",
                   type=float,
                   required=False,
                   default=2.0,
                   description="Multiplication factor"
               )
           }

       def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
           data = kwargs.get("input_data", [])
           multiplier = kwargs.get("multiplier", 2.0)
           return {
               "result": [x * multiplier for x in data]
           }

Use custom nodes in workflows:

.. code-block:: python

   from kailash.workflow.builder import WorkflowBuilder
   from kailash.runtime import LocalRuntime

   workflow = WorkflowBuilder()
   workflow.add_node("MyCustomNode", "doubler", {
       "multiplier": 3.0
   })

   with LocalRuntime() as runtime:
       results, run_id = runtime.execute(
           workflow.build(),
           parameters={"doubler": {"input_data": [1, 2, 3]}}
       )

Async Custom Nodes
------------------

For I/O-bound operations, use ``AsyncNode``:

.. code-block:: python

   from kailash.nodes.base import AsyncNode, NodeParameter
   from typing import Dict, Any

   class MyAsyncNode(AsyncNode):
       """An async node for I/O-bound operations."""

       @classmethod
       def get_node_type(cls) -> str:
           return "MyAsyncNode"

       def get_parameters(self) -> Dict[str, NodeParameter]:
           return {
               "url": NodeParameter(
                   name="url", type=str, required=True
               )
           }

       async def async_run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
           url = kwargs["url"]
           # Perform async I/O here
           return {"result": f"Fetched from {url}"}

Cycle-Aware Nodes
-----------------

For nodes that participate in iterative workflows:

.. code-block:: python

   from kailash.nodes.base_cycle_aware import CycleAwareNode
   from kailash.nodes.base import NodeParameter
   from typing import Dict, Any

   class ConvergenceNode(CycleAwareNode):
       """Node with built-in convergence detection."""

       def get_parameters(self) -> Dict[str, NodeParameter]:
           return {
               "target": NodeParameter(name="target", type=float, required=True),
           }

       def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
           target = kwargs["target"]
           iteration = self.get_iteration(context)
           prev = self.get_previous_state(context)

           value = prev.get("value", 0.0)
           value += (target - value) * 0.3

           self.accumulate_values(context, "value", value)
           converged = abs(value - target) < 0.01
           self.set_cycle_state({"value": value})

           return {"value": value, "converged": converged}

Node Parameters
===============

The ``NodeParameter`` class defines what inputs a node accepts:

.. code-block:: python

   NodeParameter(
       name="param_name",       # Parameter name
       type=str,                # Python type
       required=True,           # Whether required
       default=None,            # Default value
       description="Help text"  # Documentation
   )

Parameters can be provided in the config dictionary when adding a node, or at
execution time via the ``parameters`` argument to ``runtime.execute()``.

Best Practices
==============

1. **Keep nodes focused** -- each node should do one thing well
2. **Use PythonCodeNode** for quick custom logic
3. **Subclass BaseNode** for reusable components
4. **Use AsyncNode** for I/O-bound operations
5. **Read API keys and model names from** ``os.environ``
6. **Use parameterized SQL** -- never build queries with string concatenation
