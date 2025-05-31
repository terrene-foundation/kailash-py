=====
Utils
=====

This section covers utility functions and helpers in the Kailash SDK.

.. contents:: Table of Contents
   :local:
   :depth: 2

Export Utilities
================

The export module provides functionality for exporting workflows to various formats compatible with Kailash orchestration.

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
         type: CSVReader
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
         type: CSVWriter
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
           "type": "CSVReader",
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

Template Utilities
==================

Templates for creating common workflow patterns.

WorkflowTemplates
-----------------

.. note::
   🚧 **Coming Soon** - This utility is planned for a future release.

**Planned Features:**
- Pre-built workflow templates for common patterns
- ETL pipeline templates
- API integration templates
- ML pipeline templates
- **Agentic workflow templates** (LangChain/Langgraph integration)

**Alternative:** Build workflows manually using the WorkflowBuilder for now.

**Available Templates:**

ETL Pipeline Template
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from kailash.utils.templates import WorkflowTemplates

   # Create ETL pipeline
   workflow = WorkflowTemplates.create_etl_pipeline(
       name="customer_etl",
       source_config={
           "type": "CSVReader",
           "file_path": "raw_customers.csv"
       },
       transform_config={
           "operations": [
               {"type": "clean", "columns": ["email", "phone"]},
               {"type": "validate", "schema": "customer_schema.json"},
               {"type": "enrich", "lookup": "geo_data.csv"}
           ]
       },
       target_config={
           "type": "SQLWriter",
           "connection_string": "postgresql://localhost/warehouse",
           "table": "dim_customers"
       }
   )

API Integration Template
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Create API integration workflow
   workflow = WorkflowTemplates.create_api_integration(
       name="api_sync",
       api_config={
           "base_url": "https://api.example.com",
           "auth": {
               "type": "oauth2",
               "client_id": "${CLIENT_ID}",
               "client_secret": "${CLIENT_SECRET}"
           }
       },
       endpoints=[
           {"path": "/users", "method": "GET"},
           {"path": "/orders", "method": "GET"},
           {"path": "/products", "method": "GET"}
       ],
       output_format="json"
   )

ML Pipeline Template
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Create ML pipeline
   workflow = WorkflowTemplates.create_ml_pipeline(
       name="customer_churn_prediction",
       data_source="customers.csv",
       feature_engineering=[
           {"type": "normalize", "columns": ["age", "income"]},
           {"type": "encode", "columns": ["category", "region"]},
           {"type": "generate", "features": ["recency", "frequency"]}
       ],
       model_config={
           "type": "RandomForestClassifier",
           "params": {
               "n_estimators": 100,
               "max_depth": 10
           }
       },
       output_path="predictions.csv"
   )

Custom Templates
----------------

Create custom workflow templates:

.. code-block:: python

   from kailash.utils.templates import BaseTemplate

   class DataQualityTemplate(BaseTemplate):
       """Template for data quality workflows."""

       def create(self, **kwargs):
           workflow = Workflow(kwargs['name'])

           # Add data reader
           workflow.add_node("CSVReader", "input", config={
               "file_path": kwargs['input_file']
           })

           # Add quality checks
           checks = kwargs.get('quality_checks', [])
           for i, check in enumerate(checks):
               node_id = f"check_{i}"
               workflow.add_node("DataValidator", node_id, config=check)

               if i == 0:
                   workflow.add_edge("input", node_id)
               else:
                   workflow.add_edge(f"check_{i-1}", node_id)

           # Add report generator
           workflow.add_node("QualityReporter", "report", config={
               "output_path": kwargs.get('report_path', 'quality_report.html')
           })

           workflow.add_edge(f"check_{len(checks)-1}", "report")

           return workflow

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
   CSVReader = NodeRegistry.get_node("CSVReader")

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

   is_valid = validator.validate_node_config("CSVReader", node_config)

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
