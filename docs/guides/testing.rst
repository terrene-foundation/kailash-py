:orphan:

.. _guides-testing:

=================
Testing Workflows
=================

This guide covers testing strategies for Kailash workflows and nodes.

Unit Testing Nodes
------------------

.. code-block:: python

   import pytest
   from kailash.nodes.transform import DataTransformer

   def test_data_transformer():
       node = DataTransformer(
           transformations=["lambda x: x * 2"]
       )

       result = node.execute(data=[1, 2, 3])
       assert result["data"] == [2, 4, 6]

Integration Testing
-------------------

.. code-block:: python

   from kailash.workflow import Workflow
   from kailash.runtime.testing import TestingRuntime

   def test_workflow_integration():
       workflow = Workflow("test_workflow")
       # ... setup workflow

       runtime = TestingRuntime()
       results, run_id = runtime.execute(workflow)

       assert results["final_node"]["status"] == "success"
