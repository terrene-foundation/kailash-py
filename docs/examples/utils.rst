:orphan:

.. _examples-utils:


Utility Examples
================

This section shows examples of using utility functions and helpers.

Workflow Export
---------------

.. code-block:: python

   from kailash.utils.export import WorkflowExporter

   exporter = WorkflowExporter()

   # Export to YAML
   workflow.save("my_workflow.yaml", format="yaml")

   # Export to JSON
   workflow.save("my_workflow.json", format="json")

Hierarchical RAG Usage
----------------------

.. code-block:: python

   from kailash.workflow import Workflow
   from kailash.nodes.data.sources import DocumentSourceNode, QuerySourceNode
   from kailash.nodes.transform.chunkers import HierarchicalChunkerNode
   from kailash.nodes.data.retrieval import RelevanceScorerNode

   # Create RAG workflow
   workflow = Workflow("rag_pipeline", name="Hierarchical RAG Pipeline")

   # Add RAG components
   workflow.add_node("doc_source", DocumentSourceNode())
   workflow.add_node("query_source", QuerySourceNode())
   workflow.add_node("chunker", HierarchicalChunkerNode(chunk_size=200))
   workflow.add_node("relevance_scorer", RelevanceScorerNode(similarity_method="cosine"))

   # Connect the pipeline
   workflow.connect("doc_source", "chunker", {"documents": "documents"})

   # Execute
   from kailash.runtime.local import LocalRuntime
   results, run_id = LocalRuntime().execute(workflow)
