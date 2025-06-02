.. _examples-basic:

==============
Basic Examples
==============

This section contains basic examples to get you started with the Kailash Python SDK.

Simple Data Processing
----------------------

.. code-block:: python

   from kailash.workflow import Workflow
   from kailash.nodes.data import CSVReader, CSVWriter
   from kailash.runtime.local import LocalRuntime

   # Create workflow
   workflow = Workflow("simple_processing", name="Simple Processing")

   # Add nodes
   reader = CSVReader(file_path="input.csv")
   writer = CSVWriter(file_path="output.csv")

   workflow.add_node("read", reader)
   workflow.add_node("write", writer)

   # Connect nodes
   workflow.connect("read", "write")

   # Execute
   runtime = LocalRuntime()
   results, run_id = runtime.execute(workflow)

For more examples, see the `examples directory <https://github.com/terrene-foundation/kailash-py/tree/main/examples>`_.
