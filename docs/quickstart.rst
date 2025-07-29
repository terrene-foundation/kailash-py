==========
Quickstart
==========

Get up and running with Kailash SDK in 5 minutes! This guide shows you how to
build practical workflows quickly.

5-Minute Setup
==============

1. Install the SDK
------------------

.. code-block:: bash

   pip install kailash

2. Create Your First Workflow
-----------------------------

Save this as ``quickstart.py``:

.. code-block:: python

   from kailash import Workflow

   # Create a workflow
   w = Workflow("quickstart")

   # Add nodes
   w.add_node("CSVReaderNode", "read", config={"file_path": "data.csv"})
   w.add_node("DataFilter", "filter", config={"column": "age", "value": 18, "operation": ">="})
   w.add_node("CSVWriterNode", "write", config={"file_path": "adults.csv"})

   # Connect nodes
   w.connect_sequential(["read", "filter", "write"])

   # Run it!
   w.run()

3. Add Notifications (Optional)
-------------------------------

Get instant alerts when your workflow completes:

.. code-block:: python

   # Add Discord alerts to any workflow
   from kailash.nodes.alerts import DiscordAlertNode

   # Add success notification
   w.add_node("DiscordAlertNode", "notify", config={
       "webhook_url": "${DISCORD_WEBHOOK}",
       "title": "✅ Workflow Complete",
       "message": "Data processing finished successfully",
       "alert_type": "success"
   })

   # Connect after processing
   w.connect("write", "notify")

4. Run the Workflow
-------------------

.. code-block:: bash

   # Set your Discord webhook (optional)
   export DISCORD_WEBHOOK="https://discord.com/api/webhooks/..."

   python quickstart.py

That's it! You've just built a data processing pipeline with notifications.

Common Use Cases
================

Dynamic File Discovery (New in v0.2.1)
----------------------------------------

Process multiple files dynamically without hardcoding file paths:

.. code-block:: python

   from kailash import Workflow
   from kailash.nodes.data import DirectoryReaderNode

   w = Workflow("dynamic_files")

   # Discover files automatically
   w.add_node("DirectoryReaderNode", "discover", config={
       "directory_path": "./data/uploads",
       "pattern": "*.{csv,json,xml}",
       "recursive": True,
       "include_metadata": True
   })

   # Process CSV files specifically
   w.add_node("DataTransformer", "process_csv", config={
       "transformations": ['''
   # Get CSV files from discovery
   files_by_type = locals().get("files_by_type", {})
   csv_files = files_by_type.get("csv", [])

   processed = []
   for file_info in csv_files:
       # Process each CSV file
       import pandas as pd
       df = pd.read_csv(file_info["file_path"])
       summary = {
           "file": file_info["file_name"],
           "rows": len(df),
           "columns": list(df.columns),
           "size_mb": file_info["file_size"] / 1024 / 1024
       }
       processed.append(summary)

   result = {"csv_summaries": processed}
   ''']
   })

   # Save processing results
   w.add_node("JSONWriterNode", "save", config={
       "file_path": "file_processing_report.json"
   })

   # Connect with enhanced parameter mapping
   w.connect("discover", "process_csv", mapping={
       "files_by_type": "files_by_type"
   })
   w.connect("process_csv", "save")

   results = w.run()

Data Processing Pipeline
------------------------

Process customer data with filtering and transformation:

.. code-block:: python

   from kailash import Workflow

   w = Workflow("customer_pipeline")

   # Read customer data
   w.add_node("CSVReaderNode", "customers", config={
       "file_path": "customers.csv"
   })

   # Filter active customers
   w.add_node("DataFilter", "active_only", config={
       "column": "status",
       "value": "active"
   })

   # Calculate customer metrics
   w.add_node("PythonCodeNode", "add_metrics", config={
       "code": '''
   import pandas as pd
   df = inputs["data"]
   df["lifetime_value"] = df["purchases"] * df["avg_order_value"]
   df["segment"] = pd.cut(df["lifetime_value"],
                          bins=[0, 100, 500, float('inf')],
                          labels=["Low", "Medium", "High"])
   return {"data": df}
   '''
   })

   # Save results
   w.add_node("CSVWriterNode", "save", config={
       "file_path": "customer_segments.csv"
   })

   # Connect and run
   w.connect_sequential(["customers", "active_only", "add_metrics", "save"])
   results = w.run()

API Data Enrichment
-------------------

Enrich data using external APIs:

.. code-block:: python

   from kailash import Workflow

   w = Workflow("api_enrichment")

   # Read companies to enrich
   w.add_node("JSONReaderNode", "companies", config={
       "file_path": "companies.json"
   })

   # Enrich with API data
   w.add_node("RESTClient", "enrich", config={
       "base_url": "https://api.example.com",
       "endpoint": "/company/{company_id}",
       "method": "GET",
       "auth": {
           "type": "bearer",
           "token": "${API_TOKEN}"
       }
   })

   # Save enriched data
   w.add_node("JSONWriterNode", "save", config={
       "file_path": "enriched_companies.json"
   })

   w.connect_sequential(["companies", "enrich", "save"])
   w.run()

Iterative Processing with Cycles (New in v0.2.0)
-------------------------------------------------

The new CycleBuilder API makes it easy to create powerful iterative workflows:

**Example 1: Optimization with Automatic Convergence**

.. code-block:: python

   from kailash.workflow import CycleBuilder
   from kailash.nodes import PythonCodeNode

   # Create optimization workflow
   builder = CycleBuilder("optimization")

   # Gradient descent optimizer
   optimizer_code = '''
   # Access cycle state with automatic defaults
   try:
       x = cycle_state["x"]
       learning_rate = cycle_state["learning_rate"]
   except:
       x = 5.0  # Start far from minimum
       learning_rate = 0.1

   # Gradient of f(x) = (x-2)^2
   gradient = 2 * (x - 2)

   # Update x
   new_x = x - learning_rate * gradient

   # Adaptive learning rate
   if abs(gradient) < 0.1:
       learning_rate *= 0.9

   # Check convergence
   converged = abs(gradient) < 0.001

   result = {
       "x": new_x,
       "gradient": gradient,
       "learning_rate": learning_rate,
       "converged": converged
   }
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

   # Analyze performance
   from kailash.workflow import CycleAnalyzer
   analyzer = CycleAnalyzer(workflow)
   report = analyzer.analyze_execution(results)
   print(f"Found minimum at x={results['optimizer']['x']:.4f}")
   print(f"Converged in {report['iterations']} iterations")
   print(f"Performance: {report['iterations_per_second']:.0f} iter/sec")

**Example 2: Data Processing with Retry Logic**

.. code-block:: python

   from kailash.workflow import CycleBuilder
   from kailash.nodes import PythonCodeNode

   builder = CycleBuilder("retry_pipeline")

   # Processor with automatic retry
   processor_code = '''
   import random

   # Get data and attempt count
   try:
       data = cycle_state["data"]
       attempts = cycle_state["attempts"]
   except:
       data = input_data  # First iteration
       attempts = 0

   attempts += 1

   # Simulate processing that might fail
   if attempts < 3 and random.random() < 0.7:
       # Simulate failure
       result = {
           "data": data,
           "attempts": attempts,
           "success": False,
           "error": f"Failed on attempt {attempts}"
       }
   else:
       # Process data
       processed = [x * 2 for x in data]
       result = {
           "data": processed,
           "attempts": attempts,
           "success": True
       }
   '''

   builder.add_cycle_node(
       "processor",
       PythonCodeNode(name="processor", code=processor_code),
       input_mapping={"input_data": "data"},
       convergence_check="success == True",
       max_iterations=5
   )

   # Run with input data
   workflow = builder.build()
   results = workflow.run(parameters={
       "processor": {"data": [1, 2, 3, 4, 5]}
   })

   print(f"Succeeded after {results['processor']['attempts']} attempts")
   print(f"Result: {results['processor']['data']}")

**Example 3: Using Cycle-Aware Nodes**

.. code-block:: python

   from kailash import Workflow
   from kailash.nodes.base_cycle_aware import CycleAwareNode
   from kailash.nodes.base import NodeParameter
   from typing import Dict, Any

   class ConvergenceNode(CycleAwareNode):
       """Node with built-in convergence detection tools."""

       def get_parameters(self) -> Dict[str, NodeParameter]:
           return {
               "target": NodeParameter(name="target", type=float, required=True),
               "tolerance": NodeParameter(name="tolerance", type=float, required=False, default=0.01)
           }

       def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
           target = kwargs["target"]
           tolerance = kwargs.get("tolerance", 0.01)

           # Get iteration and previous state
           iteration = self.get_iteration(context)
           prev_state = self.get_previous_state(context)

           # Initialize or update value
           value = prev_state.get("value", 0.0)
           value += (target - value) * 0.3  # Move 30% closer each iteration

           # Track values for trend analysis
           self.accumulate_values(context, "value", value)
           trend = self.detect_convergence_trend(context, "value")

           # Log progress
           self.log_cycle_info(context, f"Iteration {iteration}: value={value:.4f}")

           # Check convergence
           converged = abs(value - target) < tolerance or trend["converging"]

           # Save state
           self.set_cycle_state({"value": value})

           return {
               "value": value,
               "converged": converged,
               "iterations": iteration + 1,
               "trend": trend
           }

   # Use in workflow
   workflow = Workflow("convergence_demo")
   workflow.add_node("converge", ConvergenceNode())
   workflow.create_cycle("convergence_cycle") \
           .connect("converge", "converge") \
           .max_iterations(50) \
           .converge_when("converged == True") \
           .build()

   results = workflow.run(parameters={"converge": {"target": 10.0}})
   print(f"Converged to {results['converge']['value']:.4f} in {results['converge']['iterations']} iterations")

Text Analysis Pipeline
----------------------

Analyze customer feedback with AI:

.. code-block:: python

   from kailash import Workflow

   w = Workflow("feedback_analysis")

   # Read feedback data
   w.add_node("CSVReaderNode", "feedback", config={
       "file_path": "customer_feedback.csv"
   })

   # Sentiment analysis
   w.add_node("TextClassifier", "sentiment", config={
       "model": "sentiment-analysis",
       "text_column": "feedback"
   })

   # Categorize by sentiment
   w.add_node("SwitchNode", "route", config={
       "condition": "sentiment_score",
       "routes": {
           "positive": "score > 0.6",
           "negative": "score < 0.4",
           "neutral": "default"
       }
   })

   # Save positive feedback
   w.add_node("CSVWriterNode", "save_positive", config={
       "file_path": "positive_feedback.csv"
   })

   # Save negative feedback for review
   w.add_node("JSONWriterNode", "save_negative", config={
       "file_path": "needs_review.json"
   })

   # Connect nodes
   w.add_edge("feedback", "sentiment")
   w.add_edge("sentiment", "route")
   w.add_edge("route", "save_positive", output_port="positive")
   w.add_edge("route", "save_negative", output_port="negative")

   w.run()

Quick Reference
===============

Essential Classes
-----------------

.. code-block:: python

   from kailash import Workflow
   from kailash.nodes import NodeRegistry
   from kailash.workflow.runner import WorkflowRunner
   from kailash.tracking import TaskManager

Common Nodes
------------

**Data I/O**

.. code-block:: python

   # Reading
   w.add_node("CSVReaderNode", "csv_in", config={"file_path": "data.csv"})
   w.add_node("JSONReaderNode", "json_in", config={"file_path": "data.json"})
   w.add_node("TextReaderNode", "txt_in", config={"file_path": "data.txt"})

   # Writing
   w.add_node("CSVWriterNode", "csv_out", config={"file_path": "output.csv"})
   w.add_node("JSONWriterNode", "json_out", config={"file_path": "output.json"})

**Data Processing**

.. code-block:: python

   # Filter
   w.add_node("DataFilter", "filter", config={
       "column": "age",
       "value": 21,
       "operation": ">="
   })

   # Transform
   w.add_node("DataMapper", "map", config={
       "mapping": {
           "full_name": "lambda row: f'{row.first_name} {row.last_name}'",
           "is_adult": "lambda row: row.age >= 18"
       }
   })

   # Sort
   w.add_node("DataSorter", "sort", config={
       "by": ["score", "name"],
       "ascending": [False, True]
   })

**Logic & Control**

.. code-block:: python

   # Conditional routing
   w.add_node("SwitchNode", "router", config={
       "condition": "category",
       "routes": {
           "high": "value > 1000",
           "medium": "value > 100",
           "low": "default"
       }
   })

   # Merge streams
   w.add_node("MergeNode", "combine", config={
       "strategy": "concat"  # or "join", "union"
   })

**Custom Code**

.. code-block:: python

   # Inline Python code
   w.add_node("PythonCodeNode", "custom", config={
       "code": '''
   # Your Python code here
   result = inputs["data"].groupby("category").sum()
   return {"summary": result}
   '''
   })

Connection Patterns
-------------------

.. code-block:: python

   # Sequential connection
   w.connect_sequential(["node1", "node2", "node3"])

   # Individual connections
   w.add_edge("source", "target")
   w.add_edge("source", "target", output_port="error")

   # Parallel branches
   w.add_edge("source", "branch1")
   w.add_edge("source", "branch2")
   w.add_edge("branch1", "merge")
   w.add_edge("branch2", "merge")

Workflow Execution
------------------

.. code-block:: python

   # Simple run
   results = w.run()

   # With initial data
   results = w.run(initial_data={"customers": customer_df})

   # With configuration
   results = w.run(config={"max_workers": 4})

   # Track execution
   from kailash import TaskManager

   tm = TaskManager()
   runner = WorkflowRunner(workflow=w, task_manager=tm)
   results = runner.run()

   # Get execution metrics
   metrics = tm.get_run_metrics(results["run_id"])

Tips & Tricks
=============

1. **Use Environment Variables**

.. code-block:: python

   import os

   w.add_node("RESTClient", "api", config={
       "base_url": os.getenv("API_BASE_URL"),
       "auth": {
           "token": os.getenv("API_TOKEN")
       }
   })

2. **Debug with Print Nodes**

.. code-block:: python

   # Add debug nodes to inspect data
   w.add_node("PythonCodeNode", "debug", config={
       "code": '''
   print(f"Data shape: {inputs['data'].shape}")
   print(f"Columns: {inputs['data'].columns.tolist()}")
   print(f"First row: {inputs['data'].iloc[0].to_dict()}")
   return inputs
   '''
   })

3. **Reusable Node Configs**

.. code-block:: python

   # Define common configurations
   csv_config = {
       "encoding": "utf-8",
       "parse_dates": True,
       "na_values": ["N/A", "null"]
   }

   w.add_node("CSVReaderNode", "read1", config={"file_path": "file1.csv", **csv_config})
   w.add_node("CSVReaderNode", "read2", config={"file_path": "file2.csv", **csv_config})

4. **Error Handling**

.. code-block:: python

   try:
       results = w.run()
   except Exception as e:
       print(f"Workflow failed: {e}")
       # Access partial results
       if hasattr(e, "partial_results"):
           print(f"Completed nodes: {e.partial_results.keys()}")

5. **Workflow Visualization**

.. code-block:: python

   # Generate Mermaid diagram
   diagram = w.to_mermaid()
   print(diagram)

   # Save as markdown
   w.save_mermaid_markdown("workflow_diagram.md")

6. **Performance Monitoring**

Track and visualize workflow performance:

.. code-block:: python

   from kailash.tracking import TaskManager
   from kailash.visualization.performance import PerformanceVisualizer

   # Run with tracking
   task_manager = TaskManager()
   results, run_id = runtime.execute(workflow, task_manager=task_manager)

   # Visualize performance
   perf_viz = PerformanceVisualizer(task_manager)
   perf_viz.create_run_performance_summary(run_id, output_dir="performance")

   # The SDK automatically collects:
   # - Execution time per node
   # - CPU and memory usage
   # - I/O operations
   # - Resource bottlenecks

7. **Debug Cyclic Workflows** (New in v0.2.0)

Use the new developer tools for cyclic workflows:

.. code-block:: python

   from kailash.workflow import CycleDebugger, CycleProfiler

   # Enable debugging
   debugger = CycleDebugger(workflow)
   debugger.enable_debugging()

   # Run workflow
   results = workflow.run()

   # Get detailed debug info
   debug_info = debugger.get_debug_info()
   print(f"Total iterations: {debug_info['total_iterations']}")
   print(f"Convergence history: {debug_info['convergence_history']}")

   # Profile performance
   profiler = CycleProfiler(workflow)
   profile = profiler.profile_execution(results)
   print(f"Average iteration time: {profile['avg_iteration_time']:.4f}s")
   print(f"Bottleneck: {profile['bottleneck_node']}")

Next Steps
==========

Ready for more? Here's where to go next:

1. **Master Cyclic Workflows**: :doc:`guides/cyclic_workflows` (New in v0.2.0)
2. **Explore Node Types**: :doc:`api/nodes`
3. **Build Complex Workflows**: :doc:`guides/workflows`
4. **Create Custom Nodes**: :doc:`guides/custom_nodes`
5. **Production Best Practices**: :doc:`guides/best_practices`
6. **Learn Phase 5 API**: :doc:`api/workflow` - CycleBuilder and developer tools

Production-Ready Workflow Library
---------------------------------

For complete, production-ready workflows, explore our comprehensive library:

- **Quick Start Patterns** (``sdk-users/2-core-concepts/workflows/quick-start/``)

  - 30-second copy-paste workflows for common tasks
  - Essential SDK patterns covering 80% of use cases
  - Fast error-to-solution lookup guide

- **Industry Solutions** (``sdk-users/2-core-concepts/workflows/by-industry/``)

  - Healthcare: Clinical diagnostics, patient data processing
  - Financial Services: Risk analysis, transaction processing
  - Manufacturing: IoT data processing, quality control

- **Technical Patterns** (``sdk-users/2-core-concepts/workflows/by-pattern/``)

  - ETL pipelines with error handling
  - REST API integrations with retry logic
  - Event-driven architectures
  - File processing and monitoring
  - Security and authentication flows

- **Enterprise Solutions** (``sdk-users/2-core-concepts/workflows/by-enterprise/``)

  - Customer 360° integration workflows
  - Multi-system data synchronization
  - Business process automation

All workflows include:

- Complete working Python scripts
- Real-world data examples (no mocks)
- Error handling and recovery patterns
- Performance optimization techniques
- Deployment-ready configurations

Need Help?
----------

- 📖 **Full Documentation**: :doc:`index`
- 💡 **Examples**: :doc:`examples/index`
- 🐛 **Troubleshooting**: :doc:`troubleshooting`
- 💬 **Community**: `GitHub Discussions <https://github.com/terrene-foundation/kailash-py/discussions>`_

Happy workflow building! 🚀
