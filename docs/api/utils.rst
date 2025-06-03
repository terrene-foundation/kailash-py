=====
Utils
=====

This section covers utility functions and helpers in the Kailash SDK.

.. contents:: Table of Contents
   :local:
   :depth: 2

Export Utilities
================

The export module provides functionality for exporting workflows to various formats
compatible with Kailash orchestration.

WorkflowExporter
----------------

.. autoclass:: kailash.utils.export.WorkflowExporter
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash.utils.export import WorkflowExporter
   from kailash import Workflow

   # Create workflow
   workflow = Workflow("data_pipeline")
   # ... add nodes and edges ...

   # Export to YAML
   exporter = WorkflowExporter(workflow)
   yaml_content = exporter.to_yaml()

   # Export to JSON
   json_content = exporter.to_json()

   # Export with validation
   validated_export = exporter.export(
       format="yaml",
       validate=True,
       include_metadata=True
   )

Export Formats
--------------

**YAML Format:**

.. code-block:: yaml

   workflow:
     id: data_pipeline
     name: Data Processing Pipeline
     version: "1.0"
     metadata:
       created_at: "2024-01-01T10:00:00"
       author: "user@example.com"

     nodes:
       - id: read_data
         type: CSVReaderNode
         config:
           file_path: "input.csv"

       - id: process
         type: DataTransformer
         config:
           operations:
             - type: filter
               column: status
               value: active

       - id: save_data
         type: CSVWriterNode
         config:
           file_path: "output.csv"

     edges:
       - from: read_data
         to: process
       - from: process
         to: save_data

**JSON Format:**

.. code-block:: json

   {
     "workflow": {
       "id": "data_pipeline",
       "name": "Data Processing Pipeline",
       "nodes": [
         {
           "id": "read_data",
           "type": "CSVReaderNode",
           "config": {
             "file_path": "input.csv"
           }
         }
       ],
       "edges": [
         {
           "from": "read_data",
           "to": "process"
         }
       ]
     }
   }

Export Options
--------------

.. code-block:: python

   # Export with custom options
   export_config = {
       "format": "yaml",
       "pretty_print": True,
       "include_comments": True,
       "validate_schema": True,
       "compress": False
   }

   content = exporter.export(**export_config)

   # Save to file
   exporter.save("workflow.yaml", **export_config)

Hierarchical RAG Utilities
==========================

The SDK provides specialized nodes for building hierarchical Retrieval-Augmented
Generation (RAG) workflows.

RAG Components
--------------

**Data Source Nodes:**

.. code-block:: python

   from kailash.nodes.data.sources import DocumentSourceNode, QuerySourceNode

   # Autonomous document provider
   doc_source = DocumentSourceNode()

   # Query provider for RAG processing
   query_source = QuerySourceNode()

**Document Processing Nodes:**

.. code-block:: python

   from kailash.nodes.transform.chunkers import HierarchicalChunkerNode
   from kailash.nodes.transform.formatters import (
       ChunkTextExtractorNode, QueryTextWrapperNode, ContextFormatterNode
   )

   # Split documents into intelligent chunks
   chunker = HierarchicalChunkerNode(chunk_size=200, overlap=50)

   # Extract text for embedding generation
   text_extractor = ChunkTextExtractorNode()

   # Wrap queries for batch processing
   query_wrapper = QueryTextWrapperNode()

   # Format context for LLM consumption
   context_formatter = ContextFormatterNode()

**Retrieval and Scoring:**

.. code-block:: python

   from kailash.nodes.data.retrieval import RelevanceScorerNode

   # Multi-method similarity scoring
   relevance_scorer = RelevanceScorerNode(
       similarity_method="cosine",  # or "text_based"
       top_k=3
   )

Complete RAG Pipeline Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from kailash.workflow import Workflow
   from kailash.nodes.ai.embedding_generator import EmbeddingGeneratorNode
   from kailash.nodes.ai.llm_agent import LLMAgentNode
   from kailash.nodes.data.sources import DocumentSourceNode, QuerySourceNode
   from kailash.nodes.data.retrieval import RelevanceScorerNode
   from kailash.nodes.transform.chunkers import HierarchicalChunkerNode
   from kailash.nodes.transform.formatters import (
       ChunkTextExtractorNode, QueryTextWrapperNode, ContextFormatterNode
   )

   # Create hierarchical RAG workflow
   workflow = Workflow("hierarchical_rag", name="Hierarchical RAG Workflow")

   # Data sources (autonomous - no external files needed)
   doc_source = DocumentSourceNode()
   query_source = QuerySourceNode()

   # Document processing pipeline
   chunker = HierarchicalChunkerNode()
   chunk_text_extractor = ChunkTextExtractorNode()
   query_text_wrapper = QueryTextWrapperNode()

   # AI processing with Ollama
   chunk_embedder = EmbeddingGeneratorNode(
       provider="ollama", model="nomic-embed-text", operation="embed_batch"
   )
   query_embedder = EmbeddingGeneratorNode(
       provider="ollama", model="nomic-embed-text", operation="embed_batch"
   )

   # Retrieval and response generation
   relevance_scorer = RelevanceScorerNode()
   context_formatter = ContextFormatterNode()
   llm_agent = LLMAgentNode(provider="ollama", model="llama3.2", temperature=0.7)

   # Add all nodes to workflow
   for name, node in {
       "doc_source": doc_source, "query_source": query_source,
       "chunker": chunker, "chunk_text_extractor": chunk_text_extractor,
       "query_text_wrapper": query_text_wrapper, "chunk_embedder": chunk_embedder,
       "query_embedder": query_embedder, "relevance_scorer": relevance_scorer,
       "context_formatter": context_formatter, "llm_agent": llm_agent
   }.items():
       workflow.add_node(name, node)

   # Connect the RAG pipeline
   workflow.connect("doc_source", "chunker", {"documents": "documents"})
   workflow.connect("chunker", "chunk_text_extractor", {"chunks": "chunks"})
   workflow.connect("chunk_text_extractor", "chunk_embedder", {"input_texts": "input_texts"})
   workflow.connect("query_source", "query_text_wrapper", {"query": "query"})
   workflow.connect("query_text_wrapper", "query_embedder", {"input_texts": "input_texts"})
   workflow.connect("chunker", "relevance_scorer", {"chunks": "chunks"})
   workflow.connect("query_embedder", "relevance_scorer", {"embeddings": "query_embedding"})
   workflow.connect("chunk_embedder", "relevance_scorer", {"embeddings": "chunk_embeddings"})
   workflow.connect("relevance_scorer", "context_formatter", {"relevant_chunks": "relevant_chunks"})
   workflow.connect("query_source", "context_formatter", {"query": "query"})
   workflow.connect("context_formatter", "llm_agent", {"messages": "messages"})

   # Execute the RAG workflow
   from kailash.runtime.local import LocalRuntime
   runtime = LocalRuntime()
   results, run_id = runtime.execute(workflow)

   print("RAG Response:", results["llm_agent"]["response"])

Node Registry Utilities
=======================

Utilities for working with the node registry.

NodeRegistry
------------

.. note::
   🚧 **Coming Soon** - This utility is planned for a future release.

**Planned Features:**
- Dynamic node discovery and registration
- Node metadata and documentation
- Plugin system for third-party nodes
- Node versioning and compatibility checks

**Alternative:** Use direct imports for now.

**Example Usage:**

.. code-block:: python

   from kailash.nodes import NodeRegistry

   # List all available nodes
   available_nodes = NodeRegistry.list_nodes()
   print(f"Available nodes: {available_nodes}")

   # Get node class
   CSVReaderNode = NodeRegistry.get_node("CSVReaderNode")

   # Check if node exists
   if NodeRegistry.has_node("CustomNode"):
       node_class = NodeRegistry.get_node("CustomNode")

   # Get node metadata
   metadata = NodeRegistry.get_node_metadata("DataFilter")
   print(f"Node category: {metadata['category']}")
   print(f"Node version: {metadata['version']}")

Registering Custom Nodes
------------------------

.. code-block:: python

   from kailash.nodes import Node, register_node

   # Decorator registration
   @register_node("MyCustomNode", category="transform", version="1.0")
   class MyCustomNode(Node):
       """Custom node implementation."""
       pass

   # Manual registration
   NodeRegistry.register("AnotherNode", AnotherNodeClass, {
       "category": "custom",
       "version": "1.0",
       "author": "developer@example.com"
   })

Node Discovery
--------------

.. code-block:: python

   # Discover nodes by category
   data_nodes = NodeRegistry.get_nodes_by_category("data")
   ai_nodes = NodeRegistry.get_nodes_by_category("ai")

   # Search nodes
   csv_nodes = NodeRegistry.search_nodes("csv")
   api_nodes = NodeRegistry.search_nodes("api")

   # Get node documentation
   for node_name in NodeRegistry.list_nodes():
       doc = NodeRegistry.get_node_doc(node_name)
       print(f"{node_name}: {doc}")

Configuration Utilities
=======================

ConfigValidator
---------------

Validate node and workflow configurations:

.. code-block:: python

   from kailash.utils.config import ConfigValidator

   validator = ConfigValidator()

   # Validate node config
   node_config = {
       "file_path": "data.csv",
       "encoding": "utf-8"
   }

   is_valid = validator.validate_node_config("CSVReaderNode", node_config)

   # Validate with schema
   schema = {
       "type": "object",
       "properties": {
           "file_path": {"type": "string"},
           "encoding": {"type": "string", "default": "utf-8"}
       },
       "required": ["file_path"]
   }

   validator.validate_against_schema(node_config, schema)

ConfigMerger
------------

Merge configurations with defaults:

.. code-block:: python

   from kailash.utils.config import ConfigMerger

   merger = ConfigMerger()

   # Define defaults
   defaults = {
       "timeout": 30,
       "retry_count": 3,
       "encoding": "utf-8"
   }

   # User config
   user_config = {
       "file_path": "data.csv",
       "timeout": 60
   }

   # Merge configs
   final_config = merger.merge(defaults, user_config)
   # Result: {"file_path": "data.csv", "timeout": 60, "retry_count": 3, "encoding": "utf-8"}

Environment Resolution
----------------------

Resolve environment variables in configurations:

.. code-block:: python

   from kailash.utils.config import resolve_env_vars

   config = {
       "api_key": "${API_KEY}",
       "base_url": "${API_BASE_URL:-https://api.example.com}",
       "timeout": 30
   }

   resolved = resolve_env_vars(config)
   # Resolves ${API_KEY} from environment
   # Uses default for API_BASE_URL if not set

Visualization Utilities
=======================

WorkflowVisualizer
------------------

Create visual representations of workflows:

.. code-block:: python

   from kailash.utils.visualization import WorkflowVisualizer

   # Generate Mermaid diagram directly from workflow
   mermaid_code = workflow.to_mermaid()

   # Generate Mermaid with markdown wrapper
   mermaid_markdown = workflow.to_mermaid_markdown(title="My Workflow")

   # Save to file
   with open("workflow.md", "w") as f:
       f.write(mermaid_markdown)

   # Or use WorkflowVisualizer for matplotlib visualization
   from kailash import WorkflowVisualizer
   visualizer = WorkflowVisualizer(workflow)
   visualizer.visualize()  # Display with matplotlib
   visualizer.save("workflow.png", dpi=300)  # Save as PNG

Execution Timeline
------------------

Visualize workflow execution timeline:

.. code-block:: python

   from kailash.utils.visualization import TimelineVisualizer
   from kailash.tracking import TaskManager

   # Get execution data
   task_manager = TaskManager()
   run_data = task_manager.get_run(run_id)

   # Create timeline
   timeline = TimelineVisualizer()
   timeline.add_run(run_data)

   # Generate visualization
   timeline.save("execution_timeline.html")

Performance Utilities
=====================

Profiling
---------

Profile workflow execution:

.. code-block:: python

   from kailash.utils.performance import WorkflowProfiler

   profiler = WorkflowProfiler()

   # Profile execution
   with profiler.profile(workflow):
       results = workflow.run()

   # Get profiling results
   profile_data = profiler.get_results()

   print(f"Total time: {profile_data['total_time']}s")
   print(f"Node times: {profile_data['node_times']}")
   print(f"Memory peak: {profile_data['memory_peak_mb']}MB")

   # Save detailed report
   profiler.save_report("profile_report.html")

Benchmarking
------------

Benchmark workflow performance:

.. code-block:: python

   from kailash.utils.performance import Benchmark

   benchmark = Benchmark()

   # Run benchmark
   results = benchmark.run(
       workflow,
       iterations=10,
       warmup=2,
       parallel_runs=3
   )

   print(f"Average time: {results['avg_time']}s")
   print(f"Min time: {results['min_time']}s")
   print(f"Max time: {results['max_time']}s")
   print(f"Std deviation: {results['std_dev']}s")

Optimization Suggestions
------------------------

Get optimization recommendations:

.. code-block:: python

   from kailash.utils.performance import Optimizer

   optimizer = Optimizer()
   suggestions = optimizer.analyze(workflow, profile_data)

   for suggestion in suggestions:
       print(f"Issue: {suggestion['issue']}")
       print(f"Impact: {suggestion['impact']}")
       print(f"Recommendation: {suggestion['recommendation']}")

Testing Utilities
=================

WorkflowTester
--------------

Test workflow execution:

.. code-block:: python

   from kailash.utils.testing import WorkflowTester

   tester = WorkflowTester()

   # Test with sample data
   test_result = tester.test_workflow(
       workflow,
       test_data={
           "input": pd.DataFrame({"id": [1, 2, 3], "value": [10, 20, 30]})
       },
       expected_output={
           "output": pd.DataFrame({"id": [1, 2, 3], "value": [20, 40, 60]})
       }
   )

   assert test_result.passed
   print(f"Execution time: {test_result.execution_time}s")

MockNode
--------

Create mock nodes for testing:

.. code-block:: python

   from kailash.utils.testing import MockNode, mock_node

   # Create mock node
   @mock_node("MockReader")
   class MockReader(MockNode):
       def execute(self, inputs):
           return {"data": self.config.get("mock_data", [])}

   # Use in tests
   workflow = Workflow("test")
   workflow.add_node("MockReader", "reader", config={
       "mock_data": [{"id": 1, "value": 100}]
   })

TestDataGenerator
-----------------

Generate test data:

.. code-block:: python

   from kailash.utils.testing import TestDataGenerator

   generator = TestDataGenerator()

   # Generate CSV data
   csv_data = generator.generate_csv(
       rows=1000,
       columns={
           "id": "sequence",
           "name": "name",
           "email": "email",
           "age": {"type": "integer", "min": 18, "max": 80},
           "score": {"type": "float", "min": 0, "max": 100}
       }
   )

   # Generate JSON data
   json_data = generator.generate_json(
       count=100,
       schema={
           "type": "object",
           "properties": {
               "id": {"type": "string", "format": "uuid"},
               "timestamp": {"type": "string", "format": "date-time"},
               "value": {"type": "number"}
           }
       }
   )

See Also
========

- :doc:`nodes` - Node types reference
- :doc:`workflow` - Workflow construction
- :doc:`/guides/testing` - Testing guide
- :doc:`/performance` - Performance guide
- :doc:`/examples/utils` - Utility examples
