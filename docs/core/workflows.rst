=========
Workflows
=========

Workflows are directed graphs of nodes that define what operations to perform and
how data flows between them. ``WorkflowBuilder`` is the primary interface for
constructing workflows.

WorkflowBuilder
===============

Creating a Workflow
-------------------

.. code-block:: python

   from kailash.workflow.builder import WorkflowBuilder

   workflow = WorkflowBuilder()

Adding Nodes
------------

The ``add_node`` method accepts a node type (string), a unique node ID (string),
a configuration dictionary, and optionally a connections specification:

.. code-block:: python

   # 3-parameter form (most common)
   workflow.add_node("PythonCodeNode", "process", {
       "code": "result = {'value': input_data * 2}"
   })

   # 4-parameter form (with inline connections)
   workflow.add_node("PythonCodeNode", "transform", {
       "code": "result = {'output': data + 1}"
   }, {"data": ("process", "result")})

.. important::

   Node IDs must be string literals. Never use variables or f-strings for node IDs.

   .. code-block:: python

      # CORRECT
      workflow.add_node("PythonCodeNode", "my_node", {})

      # WRONG -- do not use variables
      # workflow.add_node("PythonCodeNode", node_id_var, {})

Connecting Nodes
----------------

Use ``add_connection`` to wire output from one node to input of another:

.. code-block:: python

   workflow.add_connection(
       "source_node",    # source node ID
       "target_node",    # target node ID
       "output_param",   # output parameter name from source
       "input_param"     # input parameter name on target
   )

Example with multiple connections:

.. code-block:: python

   workflow = WorkflowBuilder()

   workflow.add_node("CSVReaderNode", "read", {
       "file_path": "data.csv"
   })

   workflow.add_node("PythonCodeNode", "filter", {
       "code": """
   filtered = [r for r in records if r.get('active')]
   result = {'data': filtered}
   """
   })

   workflow.add_node("PythonCodeNode", "summarize", {
       "code": "result = {'total': len(data)}"
   })

   # Wire the data flow
   workflow.add_connection("read", "filter", "data", "records")
   workflow.add_connection("filter", "summarize", "data", "data")

Building and Executing
----------------------

Always call ``.build()`` before execution:

.. code-block:: python

   from kailash.runtime import LocalRuntime

   runtime = LocalRuntime()
   results, run_id = runtime.execute(workflow.build())

.. warning::

   You must always call ``.build()``. Passing the workflow directly will fail:

   .. code-block:: python

      # CORRECT
      results, run_id = runtime.execute(workflow.build())

      # WRONG
      # results, run_id = runtime.execute(workflow)

Passing Parameters at Execution
-------------------------------

Provide runtime parameters to nodes:

.. code-block:: python

   results, run_id = runtime.execute(
       workflow.build(),
       parameters={
           "my_node": {"param1": "value1", "param2": 42}
       }
   )

Parallel Branches
=================

When nodes have no dependencies between them, the runtime can execute them
in parallel (especially with ``AsyncLocalRuntime``):

.. code-block:: python

   workflow = WorkflowBuilder()

   workflow.add_node("PythonCodeNode", "source", {
       "code": "result = {'data': [1, 2, 3, 4, 5]}"
   })

   # Two independent processing branches
   workflow.add_node("PythonCodeNode", "branch_a", {
       "code": "result = {'sum': sum(data)}"
   })
   workflow.add_node("PythonCodeNode", "branch_b", {
       "code": "result = {'avg': sum(data) / len(data)}"
   })

   # Merge results
   workflow.add_node("PythonCodeNode", "merge", {
       "code": "result = {'sum': sum_result, 'avg': avg_result}"
   })

   # Fan-out
   workflow.add_connection("source", "branch_a", "data", "data")
   workflow.add_connection("source", "branch_b", "data", "data")

   # Fan-in
   workflow.add_connection("branch_a", "merge", "sum", "sum_result")
   workflow.add_connection("branch_b", "merge", "avg", "avg_result")

Cyclic Workflows
================

Enable iterative processing with convergence detection:

.. code-block:: python

   from kailash.workflow.builder import WorkflowBuilder
   from kailash.runtime import LocalRuntime

   workflow = WorkflowBuilder()

   workflow.add_node("PythonCodeNode", "iterate", {
       "code": """
   x = cycle_state.get('x', 10.0)
   new_x = x * 0.9  # Decay toward 0
   converged = abs(new_x) < 0.01
   result = {'x': new_x, 'converged': converged}
   """
   })

   runtime = LocalRuntime(enable_cycles=True)
   results, run_id = runtime.execute(workflow.build())

.. note::

   Topological sort and cycle edge classification are cached per workflow.
   The cache is invalidated when you call ``add_node()`` or ``connect()``.

Conditional Execution
=====================

Use ``SwitchNode`` for conditional branching:

.. code-block:: python

   workflow = WorkflowBuilder()

   workflow.add_node("SwitchNode", "router", {
       "condition_field": "category"
   })

   workflow.add_node("PythonCodeNode", "handle_a", {
       "code": "result = {'handled': 'category A'}"
   })

   workflow.add_node("PythonCodeNode", "handle_b", {
       "code": "result = {'handled': 'category B'}"
   })

   runtime = LocalRuntime(conditional_execution="skip_branches")
   results, run_id = runtime.execute(workflow.build())

Connection Validation
=====================

The runtime validates connections between nodes to prevent parameter injection:

.. code-block:: python

   # Three validation modes
   runtime = LocalRuntime(connection_validation="strict")  # Block invalid
   runtime = LocalRuntime(connection_validation="warn")    # Log warnings
   runtime = LocalRuntime(connection_validation="off")     # No validation

In ``strict`` mode, the runtime will raise an error if a connection references
parameters that do not exist on the target node.

Workflow with Trust
===================

Attach a CARE trust context to any workflow execution:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kailash.workflow.builder import WorkflowBuilder
   from kailash.runtime import LocalRuntime
   from kailash.runtime.trust import (
       RuntimeTrustContext,
       TrustVerificationMode,
       TrustVerifier,
       TrustVerifierConfig,
   )

   workflow = WorkflowBuilder()
   workflow.add_node("PythonCodeNode", "secure_process", {
       "code": "result = {'status': 'processed with trust'}"
   })

   ctx = RuntimeTrustContext(
       trace_id="trace-workflow-001",
       delegation_chain=["human-operator", "agent-orchestrator"],
       verification_mode=TrustVerificationMode.ENFORCING,
   )

   verifier = TrustVerifier(
       config=TrustVerifierConfig(mode="enforcing"),
   )

   runtime = LocalRuntime(
       trust_context=ctx,
       trust_verifier=verifier,
       trust_verification_mode="enforcing",
   )

   results, run_id = runtime.execute(workflow.build())

See :doc:`trust` for the complete CARE trust documentation.

Best Practices
==============

1. **Always use** ``runtime.execute(workflow.build())`` -- never skip ``.build()``
2. **Use string literals** for node IDs
3. **Read model names from** ``.env`` -- never hardcode ``"gpt-4"`` or similar
4. **Use** ``AsyncLocalRuntime`` **in Docker/FastAPI** contexts
5. **Use** ``LocalRuntime`` **for CLI/scripts**
6. **Enable connection validation** in production: ``connection_validation="strict"``
7. **Attach trust context** for auditable workflows
