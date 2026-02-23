.. _examples-index:

Examples
========

This section contains examples demonstrating how to use the Kailash SDK with
current API patterns.

.. toctree::
   :maxdepth: 2

   basic
   advanced
   integrations
   patterns

.. note::

   All code examples use ``os.environ`` for model names and API keys.
   Never hardcode model names like ``"gpt-4"`` -- always read from ``.env``.

Example Categories
------------------

**Basic Examples**
   Simple workflows demonstrating WorkflowBuilder, node creation, and runtime execution.

**Advanced Examples**
   Complex patterns including cyclic workflows, conditional execution, and parallel branches.

**Integration Examples**
   External system integrations including APIs, databases, and AI providers.

**Patterns**
   Production-ready workflow patterns for common use cases.

Quick Example
-------------

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

   runtime = LocalRuntime()
   results, run_id = runtime.execute(workflow.build())
   print(results["hello"]["result"]["message"])

For the complete collection of runnable examples, visit the
`examples directory
<https://github.com/terrene-foundation/kailash-py/tree/main/examples>`_
in the GitHub repository.
