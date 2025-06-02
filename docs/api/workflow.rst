========
Workflow
========

This section covers the workflow management components of the Kailash SDK.

.. contents:: Table of Contents
   :local:
   :depth: 2

Workflow Class
==============

The core class for building and managing workflows.

.. autoclass:: kailash.workflow.Workflow
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

**Basic Usage:**

.. code-block:: python

   from kailash import Workflow

   # Create a workflow
   workflow = Workflow("data_pipeline")

   # Add nodes
   workflow.add_node("CSVReader", "input", config={"file_path": "data.csv"})
   workflow.add_node("DataFilter", "filter", config={"column": "active", "value": True})
   workflow.add_node("CSVWriter", "output", config={"file_path": "filtered.csv"})

   # Connect nodes
   workflow.connect_sequential(["input", "filter", "output"])

   # Execute
   results = workflow.run()

WorkflowBuilder
===============

Builder pattern for constructing workflows programmatically.

.. autoclass:: kailash.workflow.builder.WorkflowBuilder
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash.workflow import WorkflowBuilder

   # Using builder pattern
   builder = WorkflowBuilder("etl_pipeline")

   workflow = (builder
       .add_node("CSVReader", "extract", config={"file_path": "input.csv"})
       .add_node("DataTransformer", "transform", config={
           "operations": [
               {"type": "rename", "old": "id", "new": "customer_id"},
               {"type": "cast", "column": "amount", "dtype": "float"}
           ]
       })
       .add_node("SQLWriter", "load", config={
           "connection_string": "postgresql://localhost/db",
           "table_name": "customers"
       })
       .connect_sequential(["extract", "transform", "load"])
       .build()
   )

   results = workflow.run()

Workflow Graph Management
=========================

Internal graph representation is handled by the Workflow class.

.. autoclass:: kailash.workflow.graph.Workflow
   :members:
   :undoc-members:
   :show-inheritance:

**Key Methods:**

- ``add_node(node_id, node_instance)``: Add a node to the graph
- ``add_edge(source, target, metadata)``: Connect two nodes
- ``get_execution_order()``: Get topological sort of nodes
- ``validate()``: Check for cycles and connectivity

WorkflowRunner
==============

Executes workflows with various runtime configurations.

.. autoclass:: kailash.workflow.runner.WorkflowRunner
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   from kailash.workflow import WorkflowRunner
   from kailash.tracking import TaskManager

   # Create runner with task tracking
   task_manager = TaskManager()
   runner = WorkflowRunner(
       workflow=workflow,
       task_manager=task_manager
   )

   # Run with configuration
   results = runner.run(
       initial_data={"customers": customer_df},
       config={
           "max_workers": 4,
           "timeout": 300
       }
   )

   # Access execution metrics
   run_id = results["run_id"]
   metrics = task_manager.get_run_metrics(run_id)

State Management
================

Manages workflow execution state and data flow.

.. autoclass:: kailash.workflow.state.StateManager
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: kailash.workflow.state.WorkflowStateWrapper
   :members:
   :undoc-members:
   :show-inheritance:

**State Management:**

.. code-block:: python

   from kailash.nodes import Node

   # Access during node execution
   class MyNode(Node):
       def execute(self, inputs):
           # Get workflow state
           state = self.workflow_state

           # Store intermediate results
           state.set_node_output("my_node", {"result": data})

           # Access previous outputs
           previous = state.get_node_output("previous_node")

           return {"processed": data}

Workflow Patterns
=================

Sequential Pipeline
-------------------

Simple linear data flow:

.. code-block:: python

   workflow = Workflow("sequential")

   # Add nodes
   nodes = ["read", "validate", "transform", "save"]
   for i, node_id in enumerate(nodes):
       workflow.add_node(f"Node{i}", node_id, config={})

   # Connect in sequence
   workflow.connect_sequential(nodes)

Parallel Processing
-------------------

Execute multiple branches concurrently:

.. code-block:: python

   workflow = Workflow("parallel")

   # Source node
   workflow.add_node("CSVReader", "source", config={"file_path": "data.csv"})

   # Parallel branches
   workflow.add_node("DataFilter", "filter1", config={"column": "type", "value": "A"})
   workflow.add_node("DataFilter", "filter2", config={"column": "type", "value": "B"})
   workflow.add_node("DataFilter", "filter3", config={"column": "type", "value": "C"})

   # Merge results
   workflow.add_node("Merge", "combine", config={"strategy": "concat"})

   # Connect
   for filter_id in ["filter1", "filter2", "filter3"]:
       workflow.add_edge("source", filter_id)
       workflow.add_edge(filter_id, "combine")

Conditional Routing
-------------------

Route data based on conditions:

.. code-block:: python

   workflow = Workflow("conditional")

   # Add switch node
   workflow.add_node("Switch", "router", config={
       "condition": "priority",
       "routes": {
           "high": "priority == 'high'",
           "medium": "priority == 'medium'",
           "low": "default"
       }
   })

   # Add handlers for each route
   workflow.add_node("PythonCodeNode", "high_handler", config={
       "code": "return {'processed': 'high priority'}"
   })
   workflow.add_node("PythonCodeNode", "medium_handler", config={
       "code": "return {'processed': 'medium priority'}"
   })
   workflow.add_node("PythonCodeNode", "low_handler", config={
       "code": "return {'processed': 'low priority'}"
   })

   # Connect routes
   workflow.add_edge("router", "high_handler", output_port="high")
   workflow.add_edge("router", "medium_handler", output_port="medium")
   workflow.add_edge("router", "low_handler", output_port="low")

Error Handling
--------------

Handle errors gracefully:

.. code-block:: python

   workflow = Workflow("error_handling")

   # Main processing node
   workflow.add_node("DataProcessor", "process", config={})

   # Error handler
   workflow.add_node("PythonCodeNode", "error_handler", config={
       "code": '''
   import logging
   logging.error(f"Processing failed: {inputs.get('error')}")
   # Send notification, save to error log, etc.
   return {"handled": True}
   '''
   })

   # Connect error output
   workflow.add_edge("process", "error_handler", output_port="error")

Dynamic Workflows
-----------------

Build workflows dynamically based on configuration:

.. code-block:: python

   def build_dynamic_workflow(config):
       workflow = Workflow("dynamic")

       # Add nodes based on config
       for step in config["steps"]:
           workflow.add_node(
               step["type"],
               step["id"],
               config=step.get("config", {})
           )

       # Connect based on config
       for connection in config["connections"]:
           workflow.add_edge(
               connection["from"],
               connection["to"],
               output_port=connection.get("port", "default")
           )

       return workflow

   # Use configuration
   config = {
       "steps": [
           {"type": "CSVReader", "id": "input", "config": {"file_path": "data.csv"}},
           {"type": "DataFilter", "id": "filter", "config": {"column": "active", "value": True}},
           {"type": "CSVWriter", "id": "output", "config": {"file_path": "output.csv"}}
       ],
       "connections": [
           {"from": "input", "to": "filter"},
           {"from": "filter", "to": "output"}
       ]
   }

   workflow = build_dynamic_workflow(config)

Workflow Visualization
======================

MermaidVisualizer
-----------------

.. autoclass:: kailash.workflow.mermaid_visualizer.MermaidVisualizer
   :members:
   :undoc-members:
   :show-inheritance:

**Example Usage:**

.. code-block:: python

   # Generate Mermaid diagram
   mermaid_diagram = workflow.to_mermaid()
   print(mermaid_diagram)

   # Save as markdown file
   workflow.save_mermaid_markdown("workflow_diagram.md")

   # Custom styling
   from kailash.workflow import MermaidVisualizer

   visualizer = MermaidVisualizer(workflow)
   diagram = visualizer.generate_mermaid(
       direction="LR",  # Left to right
       include_data_nodes=True,
       custom_styles={
           "data": "fill:#e1f5fe",
           "transform": "fill:#fff3e0",
           "logic": "fill:#f3e5f5"
       }
   )

Workflow Serialization
======================

Export Workflows
----------------

.. code-block:: python

   # Export to YAML
   workflow.export("workflow.yaml", format="yaml")

   # Export to JSON
   workflow.export("workflow.json", format="json")

   # Get export data
   export_data = workflow.to_dict()

Import Workflows
----------------

.. code-block:: python

   from kailash import Workflow

   # Load from YAML
   workflow = Workflow.from_file("workflow.yaml")

   # Load from JSON
   workflow = Workflow.from_file("workflow.json")

   # Load from dict
   workflow = Workflow.from_dict(export_data)

Best Practices
==============

1. **Use Descriptive Node IDs**

.. code-block:: python

   # Good
   workflow.add_node("CSVReader", "read_customer_data", ...)
   workflow.add_node("DataFilter", "filter_active_customers", ...)

   # Avoid
   workflow.add_node("CSVReader", "node1", ...)
   workflow.add_node("DataFilter", "node2", ...)

2. **Validate Early**

.. code-block:: python

   # Validate workflow before execution
   try:
       workflow.validate()
   except Exception as e:
       print(f"Workflow validation failed: {e}")
       # Fix issues before running

3. **Use Task Tracking**

.. code-block:: python

   # Always use task manager for production
   task_manager = TaskManager()
   runner = WorkflowRunner(workflow, task_manager)

   # Monitor execution
   results = runner.run()
   print(f"Execution took: {results['duration']}s")

4. **Handle Partial Results**

.. code-block:: python

   try:
       results = workflow.run()
   except WorkflowExecutionError as e:
       # Access partial results
       completed = e.partial_results
       print(f"Completed nodes: {list(completed.keys())}")

       # Handle cleanup
       cleanup_partial_results(completed)

5. **Modular Workflows**

.. code-block:: python

   # Create reusable sub-workflows
   def create_data_validation_workflow():
       w = Workflow("validation")
       w.add_node("SchemaValidator", "validate_schema", ...)
       w.add_node("DataQualityChecker", "check_quality", ...)
       return w

   # Compose larger workflows
   main_workflow = Workflow("main")
   validation_sub = create_data_validation_workflow()
   main_workflow.add_subworkflow("validation", validation_sub)

See Also
========

- :doc:`nodes` - Available node types
- :doc:`runtime` - Execution runtime options
- :doc:`tracking` - Task tracking and monitoring
- :doc:`/guides/workflows` - Workflow design guide
- :doc:`/examples/index` - Example workflows
