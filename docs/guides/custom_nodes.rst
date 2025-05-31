:orphan:

.. _guides-custom-nodes:

===================
Creating Custom Nodes
===================

This guide explains how to create custom nodes for the Kailash Python SDK.

.. note::
   For a complete example, see the :doc:`../best_practices` guide and the
   `node examples <https://github.com/terrene-foundation/kailash-py/tree/main/examples/node_examples>`_.

Basic Custom Node
-----------------

.. code-block:: python

   from typing import Dict, Any
   from kailash.nodes.base import Node, NodeParameter

   class MyCustomNode(Node):
       """A custom node that processes data."""
       
       def get_parameters(self) -> Dict[str, NodeParameter]:
           return {
               "input_data": NodeParameter(
                   name="input_data",
                   type=list,
                   required=True,
                   description="Input data to process"
               ),
               "multiplier": NodeParameter(
                   name="multiplier",
                   type=float,
                   required=False,
                   default=1.0,
                   description="Multiplication factor"
               )
           }
       
       def run(self, **kwargs) -> Dict[str, Any]:
           data = kwargs["input_data"]
           multiplier = kwargs.get("multiplier", 1.0)
           
           result = [item * multiplier for item in data]
           return {"output": result}