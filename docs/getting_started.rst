===============
Getting Started
===============

Welcome to the Kailash SDK v0.12.5. This guide walks you through core concepts and
patterns you will use in every Kailash project.

Prerequisites
=============

- Python 3.11 or higher
- pip or uv package manager
- A ``.env`` file with your API keys (see :doc:`installation`)

Core Concepts
=============

The Kailash SDK is built around three pillars:

1. **Workflows** -- Directed graphs of nodes that define what to do
2. **Runtimes** -- Engines that execute workflows
3. **Trust** -- Cryptographic chains that verify who authorized what

Everything follows one pattern:

.. code-block:: python

   from kailash.workflow.builder import WorkflowBuilder
   from kailash.runtime import LocalRuntime

   workflow = WorkflowBuilder()
   # ... add nodes and connections ...
   with LocalRuntime() as runtime:
       results, run_id = runtime.execute(workflow.build())

Building Workflows
==================

WorkflowBuilder is the entry point for all workflow construction.

Adding Nodes
------------

Nodes are the building blocks. Each node has a type, a unique string ID, and a
configuration dictionary:

.. code-block:: python

   from kailash.workflow.builder import WorkflowBuilder

   workflow = WorkflowBuilder()

   # Pattern: workflow.add_node("NodeType", "node_id", {config})
   workflow.add_node("PythonCodeNode", "step_1", {
       "code": "result = {'value': input_data * 2}"
   })

   workflow.add_node("PythonCodeNode", "step_2", {
       "code": "result = {'final': input_data + 100}"
   })

.. important::

   Node IDs must be string literals. The 4-parameter pattern is:
   ``workflow.add_node("NodeType", "node_id", {config}, connections)``
   where connections is optional.

Connecting Nodes
----------------

Connections define data flow between nodes:

.. code-block:: python

   # Connect output of step_1 to input of step_2
   workflow.add_connection("step_1", "step_2", "result", "input_data")

   # Parameters:
   #   source_node_id, target_node_id, source_output, target_input

Executing Workflows
===================

LocalRuntime (Sync)
-------------------

For CLI scripts and synchronous contexts:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kailash.workflow.builder import WorkflowBuilder
   from kailash.runtime import LocalRuntime

   workflow = WorkflowBuilder()
   workflow.add_node("PythonCodeNode", "hello", {
       "code": "result = {'message': 'Hello from Kailash!'}"
   })

   with LocalRuntime() as runtime:
       results, run_id = runtime.execute(workflow.build())
       print(results["hello"]["result"]["message"])

AsyncLocalRuntime (Async)
-------------------------

For Docker, FastAPI, and async contexts:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kailash.workflow.builder import WorkflowBuilder
   from kailash.runtime import AsyncLocalRuntime

   workflow = WorkflowBuilder()
   workflow.add_node("PythonCodeNode", "hello", {
       "code": "result = {'message': 'Hello from async Kailash!'}"
   })

   runtime = AsyncLocalRuntime()
   try:
       results, run_id = await runtime.execute_workflow_async(
           workflow.build(), inputs={}
       )
   finally:
       runtime.close()

Auto-Detection
--------------

Let the SDK choose the right runtime:

.. code-block:: python

   from kailash.runtime import get_runtime

   runtime = get_runtime()  # AsyncLocalRuntime for Docker, LocalRuntime otherwise

Runtime Configuration
---------------------

Both runtimes inherit from ``BaseRuntime`` with 29 configuration parameters:

.. code-block:: python

   runtime = LocalRuntime(
       debug=True,
       enable_cycles=True,                    # CycleExecutionMixin
       conditional_execution="skip_branches",  # ConditionalExecutionMixin
       connection_validation="strict",         # ValidationMixin (strict/warn/off)
   )

CARE Trust Framework
====================

The CARE (Context, Action, Reasoning, Evidence) framework is what
makes Kailash unique among AI platforms. It provides verifiable trust chains from
human authorization through agent delegation.

**Three verification modes:**

- **disabled** (default): No trust checks. Existing code works unchanged.
- **permissive**: Logs trust events but does not block execution.
- **enforcing**: Blocks workflows that fail trust verification.

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kailash.runtime import LocalRuntime
   from kailash.runtime.trust import (
       RuntimeTrustContext,
       TrustVerificationMode,
   )

   ctx = RuntimeTrustContext(
       trace_id="trace-001",
       delegation_chain=["human-alice", "agent-coordinator", "agent-worker"],
       verification_mode=TrustVerificationMode.PERMISSIVE,
   )

   with LocalRuntime(
       trust_context=ctx,
       trust_verification_mode="permissive",
   ) as runtime:
       results, run_id = runtime.execute(workflow.build())

See :doc:`core/trust` for the full trust framework documentation.

Choosing a Framework
====================

The Core SDK is always available. Frameworks build on top of it for specific use cases:

.. list-table::
   :widths: 20 40 40
   :header-rows: 1

   * - Framework
     - Use Case
     - Install
   * - **Core SDK**
     - Custom workflows, fine-grained control
     - ``pip install kailash``
   * - **Kaizen** (v1.2.5)
     - AI agents, signatures, multi-agent teams
     - ``pip install kailash-kaizen``
   * - **Nexus** (v1.4.2)
     - Multi-channel (API + CLI + MCP)
     - ``pip install kailash-nexus``
   * - **DataFlow** (v0.12.4)
     - Database operations, auto-generated nodes
     - ``pip install kailash-dataflow``

All frameworks use the same underlying workflow execution:
``runtime.execute(workflow.build())``.

Common Patterns
===============

Data Processing Pipeline
------------------------

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kailash.workflow.builder import WorkflowBuilder
   from kailash.runtime import LocalRuntime

   workflow = WorkflowBuilder()

   workflow.add_node("CSVReaderNode", "read_data", {
       "file_path": "customers.csv"
   })

   workflow.add_node("PythonCodeNode", "transform", {
       "code": """
   # Filter and transform
   active = [r for r in input_data if r.get('status') == 'active']
   result = {'data': active, 'count': len(active)}
   """
   })

   workflow.add_connection("read_data", "transform", "data", "input_data")

   with LocalRuntime() as runtime:
       results, run_id = runtime.execute(workflow.build())

AI-Powered Workflow
-------------------

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kailash.workflow.builder import WorkflowBuilder
   from kailash.runtime import LocalRuntime

   model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")

   workflow = WorkflowBuilder()

   workflow.add_node("LLMAgentNode", "analyzer", {
       "model": model,
       "prompt": "Analyze the following data and provide insights: {input_data}"
   })

   with LocalRuntime() as runtime:
       results, run_id = runtime.execute(
           workflow.build(),
           parameters={"analyzer": {"input_data": "Q1 revenue up 15%, costs down 8%"}}
       )

Cyclic Workflow
---------------

For iterative processing with convergence detection:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kailash.workflow.builder import WorkflowBuilder
   from kailash.runtime import LocalRuntime

   workflow = WorkflowBuilder()

   workflow.add_node("PythonCodeNode", "optimizer", {
       "code": """
   # Iterative optimization
   x = cycle_state.get('x', 5.0)
   gradient = 2 * (x - 2)
   new_x = x - 0.1 * gradient
   converged = abs(gradient) < 0.001
   result = {'x': new_x, 'converged': converged}
   """
   })

   with LocalRuntime(enable_cycles=True) as runtime:
       results, run_id = runtime.execute(workflow.build())

Next Steps
==========

- :doc:`core/workflows` -- Advanced workflow patterns, connections, and cycles
- :doc:`core/nodes` -- Node types and custom node development
- :doc:`core/runtime` -- Runtime architecture and configuration
- :doc:`core/trust` -- CARE trust framework deep dive
- :doc:`frameworks/kaizen` -- Build AI agents
- :doc:`frameworks/nexus` -- Deploy multi-channel platforms
- :doc:`frameworks/dataflow` -- Zero-config database operations
