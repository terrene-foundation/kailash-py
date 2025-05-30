==========
Quickstart
==========

Get up and running with Kailash SDK in 5 minutes! This guide shows you how to build practical workflows quickly.

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
   w.add_node("CSVReader", "read", config={"file_path": "data.csv"})
   w.add_node("DataFilter", "filter", config={"column": "age", "value": 18, "operation": ">="})
   w.add_node("CSVWriter", "write", config={"file_path": "adults.csv"})
   
   # Connect nodes
   w.connect_sequential(["read", "filter", "write"])
   
   # Run it!
   w.run()

3. Run the Workflow
-------------------

.. code-block:: bash

   python quickstart.py

That's it! You've just built a data processing pipeline.

Common Use Cases
================

Data Processing Pipeline
------------------------

Process customer data with filtering and transformation:

.. code-block:: python

   from kailash import Workflow
   
   w = Workflow("customer_pipeline")
   
   # Read customer data
   w.add_node("CSVReader", "customers", config={
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
   w.add_node("CSVWriter", "save", config={
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
   w.add_node("JSONReader", "companies", config={
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
   w.add_node("JSONWriter", "save", config={
       "file_path": "enriched_companies.json"
   })
   
   w.connect_sequential(["companies", "enrich", "save"])
   w.run()

Text Analysis Pipeline
----------------------

Analyze customer feedback with AI:

.. code-block:: python

   from kailash import Workflow
   
   w = Workflow("feedback_analysis")
   
   # Read feedback data
   w.add_node("CSVReader", "feedback", config={
       "file_path": "customer_feedback.csv"
   })
   
   # Sentiment analysis
   w.add_node("TextClassifier", "sentiment", config={
       "model": "sentiment-analysis",
       "text_column": "feedback"
   })
   
   # Categorize by sentiment
   w.add_node("Switch", "route", config={
       "condition": "sentiment_score",
       "routes": {
           "positive": "score > 0.6",
           "negative": "score < 0.4",
           "neutral": "default"
       }
   })
   
   # Save positive feedback
   w.add_node("CSVWriter", "save_positive", config={
       "file_path": "positive_feedback.csv"
   })
   
   # Save negative feedback for review
   w.add_node("JSONWriter", "save_negative", config={
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

   from kailash import (
       Workflow,        # Main workflow class
       NodeRegistry,    # Access available nodes
       WorkflowRunner,  # Execute workflows
       TaskManager      # Track execution
   )

Common Nodes
------------

**Data I/O**

.. code-block:: python

   # Reading
   w.add_node("CSVReader", "csv_in", config={"file_path": "data.csv"})
   w.add_node("JSONReader", "json_in", config={"file_path": "data.json"})
   w.add_node("TextReader", "txt_in", config={"file_path": "data.txt"})
   
   # Writing
   w.add_node("CSVWriter", "csv_out", config={"file_path": "output.csv"})
   w.add_node("JSONWriter", "json_out", config={"file_path": "output.json"})

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
   w.add_node("Switch", "router", config={
       "condition": "category",
       "routes": {
           "high": "value > 1000",
           "medium": "value > 100",
           "low": "default"
       }
   })
   
   # Merge streams
   w.add_node("Merge", "combine", config={
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
   
   w.add_node("CSVReader", "read1", config={"file_path": "file1.csv", **csv_config})
   w.add_node("CSVReader", "read2", config={"file_path": "file2.csv", **csv_config})

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

Next Steps
==========

Ready for more? Here's where to go next:

1. **Learn Core Concepts**: :doc:`guides/concepts`
2. **Explore Node Types**: :doc:`api/nodes`
3. **Build Complex Workflows**: :doc:`guides/workflows`
4. **Create Custom Nodes**: :doc:`guides/custom_nodes`
5. **Production Best Practices**: :doc:`guides/best_practices`

Need Help?
----------

- 📖 **Full Documentation**: :doc:`index`
- 💡 **Examples**: :doc:`examples/index`
- 🐛 **Troubleshooting**: :doc:`guides/troubleshooting`
- 💬 **Community**: `GitHub Discussions <https://github.com/terrene-foundation/kailash-py/discussions>`_

Happy workflow building! 🚀