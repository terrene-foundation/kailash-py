========
Workflow
========

This section covers the workflow management components of the Kailash SDK,
including the new Universal Hybrid Cyclic Graph Architecture introduced in v0.2.0.

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
   workflow.add_node("CSVReaderNode", "input", config={"file_path": "data.csv"})
   workflow.add_node("DataFilter", "filter", config={"column": "active", "value": True})
   workflow.add_node("CSVWriterNode", "output", config={"file_path": "filtered.csv"})

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
       .add_node("CSVReaderNode", "extract", config={"file_path": "input.csv"})
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
- ``connect(source, target, mapping=None, condition=None, cycle=False, max_iterations=100, convergence_check=None)``:
  Connect nodes with optional cycle support
- ``get_execution_order()``: Get topological sort of nodes (DAG workflows only)
- ``validate()``: Check for proper graph structure and cycle configuration

Cyclic Workflows (Enhanced in v0.2.0)
=====================================

Kailash v0.2.0 introduces the Universal Hybrid Cyclic Graph Architecture with
high-performance iterative processing, automatic convergence detection, and
comprehensive developer tools.

**Performance:** 30,000+ iterations per second for typical workflows.

CycleBuilder API (New in v0.2.0)
---------------------------------

.. autoclass:: kailash.workflow.CycleBuilder
   :members:
   :undoc-members:
   :show-inheritance:

**Phase 5 API - Simple and Intuitive:**

.. code-block:: python

   from kailash.workflow import CycleBuilder
   from kailash.nodes import PythonCodeNode

   # Create builder
   builder = CycleBuilder("optimization")

   # Add cycle node with automatic state management
   optimizer_code = '''
   # Access previous state with automatic defaults
   try:
       x = cycle_state["x"]
       loss = cycle_state["loss"]
   except:
       x = 10.0  # Initial value
       loss = float('inf')

   # Gradient descent step
   gradient = 2 * x  # derivative of x^2
   learning_rate = 0.1
   new_x = x - learning_rate * gradient
   new_loss = new_x ** 2

   # Check convergence
   converged = abs(new_loss - loss) < 0.001

   result = {"x": new_x, "loss": new_loss, "converged": converged}
   '''

   builder.add_cycle_node(
       "optimizer",
       PythonCodeNode(name="optimizer", code=optimizer_code),
       convergence_check="converged == True",
       max_iterations=100
   )

   # Build and run
   workflow = builder.build()
   results = workflow.run()

**Advanced Features:**

.. code-block:: python

   # Multi-node cycles with CycleBuilder
   builder = CycleBuilder("multi_stage")

   # Add multiple nodes in cycle
   builder.add_cycle_node("stage1", Stage1Node())
   builder.add_node("stage2", Stage2Node())  # Regular node in cycle
   builder.add_node("stage3", Stage3Node())

   # Define cycle path
   builder.connect("stage1", "stage2")
   builder.connect("stage2", "stage3")
   builder.close_cycle("stage3", "stage1",
                      convergence_check="converged == True")

   workflow = builder.build()

**Traditional API (Still Supported):**

.. code-block:: python

   from kailash import Workflow

   workflow = Workflow("iterative_process")

   # Add a cycle-aware node
   workflow.add_node("processor", MyProcessorNode())

   # Connect node to itself to create a cycle
   workflow.create_cycle("processing_cycle") \
           .connect("processor", "processor", mapping={"output": "input"}) \
           .max_iterations(100) \
           .converge_when("done == True") \
           .build()

CycleAnalyzer (New in v0.2.0)
------------------------------

.. autoclass:: kailash.workflow.CycleAnalyzer
   :members:
   :undoc-members:
   :show-inheritance:

**Analyze Cycle Performance:**

.. code-block:: python

   from kailash.workflow import CycleAnalyzer

   analyzer = CycleAnalyzer(workflow)

   # Analyze execution
   report = analyzer.analyze_execution(results)

   print(f"Total iterations: {report['iterations']}")
   print(f"Performance: {report['iterations_per_second']:.0f} iter/sec")
   print(f"Convergence rate: {report['convergence_rate']:.2%}")

   # Generate detailed report
   analyzer.generate_report("cycle_analysis.json")

   # Visualize convergence
   analyzer.plot_convergence("convergence.png")

CycleDebugger (New in v0.2.0)
------------------------------

.. autoclass:: kailash.workflow.CycleDebugger
   :members:
   :undoc-members:
   :show-inheritance:

**Debug Cyclic Workflows:**

.. code-block:: python

   from kailash.workflow import CycleDebugger

   debugger = CycleDebugger(workflow)

   # Enable debugging
   debugger.enable_debugging()

   # Set breakpoints
   debugger.set_breakpoint("optimizer", iteration=10)
   debugger.set_conditional_breakpoint(
       "optimizer",
       condition=lambda state: state.get("loss", 0) < 0.1
   )

   # Run with debugging
   results = workflow.run()

   # Get debug information
   debug_info = debugger.get_debug_info()
   print(f"State at iteration 10: {debug_info['breakpoints'][10]}")

   # Trace execution
   trace = debugger.get_execution_trace()
   for step in trace:
       print(f"Iteration {step['iteration']}: {step['state']}")

CycleProfiler (New in v0.2.0)
------------------------------

.. autoclass:: kailash.workflow.CycleProfiler
   :members:
   :undoc-members:
   :show-inheritance:

**Profile Performance:**

.. code-block:: python

   from kailash.workflow import CycleProfiler

   profiler = CycleProfiler(workflow)

   # Profile execution
   profile = profiler.profile_execution(results)

   print(f"Average iteration time: {profile['avg_iteration_time']:.4f}s")
   print(f"Peak memory usage: {profile['peak_memory_mb']:.1f} MB")
   print(f"Bottleneck node: {profile['bottleneck_node']}")

   # Generate performance report
   profiler.generate_performance_report("performance_report.html")

   # Identify optimization opportunities
   suggestions = profiler.get_optimization_suggestions()
   for suggestion in suggestions:
       print(f"- {suggestion}")

**CycleBuilder API (v0.2.0+):**

- ``create_cycle(name)``: Creates a new cycle with a unique name
- ``connect(source, target, mapping=None)``: Connects nodes within the cycle
- ``max_iterations(n)``: Maximum iterations before forced stop (default: 100)
- ``converge_when(condition)``: Python expression evaluated against node outputs
- ``timeout(seconds)``: Maximum time limit for cycle execution
- ``build()``: Finalizes the cycle configuration

**Important Notes:**

- Use ``workflow.create_cycle("name").connect(...).build()`` for modern cycles
- The deprecated ``cycle=True`` parameter is superseded by CycleBuilder API
- Workflows with cycles use the ``CyclicRunner`` automatically
- Use ``CycleAwareNode`` base class for built-in cycle features
- State is managed automatically between iterations
- Performance optimized for 30,000+ iterations/second

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
   workflow.add_node("CSVReaderNode", "source", config={"file_path": "data.csv"})

   # Parallel branches
   workflow.add_node("DataFilter", "filter1", config={"column": "type", "value": "A"})
   workflow.add_node("DataFilter", "filter2", config={"column": "type", "value": "B"})
   workflow.add_node("DataFilter", "filter3", config={"column": "type", "value": "C"})

   # Merge results
   workflow.add_node("MergeNode", "combine", config={"strategy": "concat"})

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
   workflow.add_node("SwitchNode", "router", config={
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
           {"type": "CSVReaderNode", "id": "input", "config": {"file_path": "data.csv"}},
           {"type": "DataFilter", "id": "filter", "config": {"column": "active", "value": True}},
           {"type": "CSVWriterNode", "id": "output", "config": {"file_path": "output.csv"}}
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
   workflow.add_node("CSVReaderNode", "read_customer_data", ...)
   workflow.add_node("DataFilter", "filter_active_customers", ...)

   # Avoid
   workflow.add_node("CSVReaderNode", "node1", ...)
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

Cycle Configuration (New in v0.2.0)
===================================

.. autoclass:: kailash.workflow.CycleConfig
   :members:
   :undoc-members:
   :show-inheritance:

**Type-Safe Configuration:**

.. code-block:: python

   from kailash.workflow import CycleConfig

   # Create configuration
   config = CycleConfig(
       max_iterations=1000,
       convergence_check="loss < 0.001",
       early_termination="gradient < 1e-6",
       save_checkpoints=True,
       checkpoint_interval=100
   )

   # Use in workflow with CycleBuilder API
   workflow.create_cycle("optimization_cycle") \
           .connect("node1", "node2") \
           .max_iterations(config.max_iterations) \
           .converge_when(config.convergence_check) \
           .timeout(config.timeout) \
           .build()

Migration Tools (New in v0.2.0)
================================

.. automodule:: kailash.workflow.migration
   :members:
   :undoc-members:
   :show-inheritance:

**Migrate Existing Workflows:**

.. code-block:: python

   from kailash.workflow.migration import WorkflowMigrator

   # Migrate to use CycleBuilder
   migrator = WorkflowMigrator()

   # Analyze workflow
   analysis = migrator.analyze_workflow(old_workflow)
   print(f"Found {len(analysis['cycles'])} cycles")

   # Generate migration code
   new_code = migrator.generate_migration_code(old_workflow)
   print(new_code)

   # Auto-migrate
   new_workflow = migrator.migrate_workflow(old_workflow)

See Also
========

- :doc:`nodes` - Available node types
- :doc:`runtime` - Execution runtime options
- :doc:`tracking` - Task tracking and monitoring
- :doc:`/guides/workflows` - Workflow design guide
- :doc:`/guides/cyclic_workflows` - Cyclic workflow guide (New)
- :doc:`/examples/index` - Example workflows
