.. _examples-advanced:

=================
Advanced Examples
=================

This section demonstrates advanced features and patterns in the Kailash Python SDK.

Complex Workflow with Conditional Logic
---------------------------------------

.. code-block:: python

   from kailash.workflow import Workflow
   from kailash.nodes.logic import Switch, Merge
   from kailash.nodes.transform import DataTransformer
   from kailash.runtime.local import LocalRuntime

   # Create workflow with branching
   workflow = Workflow("advanced_flow", name="Advanced Flow")

   # Add switch for conditional routing
   switch = Switch()
   workflow.add_node("router", switch)

   # Add processing branches
   high_value = DataTransformer(transformations=["lambda x: x"])
   low_value = DataTransformer(transformations=["lambda x: x"])
   
   workflow.add_node("process_high", high_value)
   workflow.add_node("process_low", low_value)

   # Add merge to combine results
   merge = Merge()
   workflow.add_node("combine", merge)

   # Connect with conditional routing
   workflow.connect("router", "process_high")
   workflow.connect("router", "process_low")
   workflow.connect("process_high", "combine")
   workflow.connect("process_low", "combine")

For more examples, see the `workflow examples <https://github.com/terrene-foundation/kailash-py/tree/main/examples/workflow_examples>`_.