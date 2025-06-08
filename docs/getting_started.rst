===============
Getting Started
===============

Welcome to the Kailash Python SDK v0.2.0! This guide will help you get up and running quickly.

**New in v0.2.0**: Universal Hybrid Cyclic Graph Architecture with high-performance iterative workflows,
automatic convergence detection, and comprehensive developer tools.

Prerequisites
=============

Before you begin, ensure you have:

- Python 3.8 or higher installed
- pip (Python package installer)
- Basic understanding of Python programming
- (Optional) Docker for containerized execution

Installation
============

Install Using pip
-----------------

The easiest way to install the Kailash SDK is using pip:

.. code-block:: bash

   pip install kailash

Install from Source
-------------------

For development or to get the latest features:

.. code-block:: bash

   git clone https://github.com/terrene-foundation/kailash-py.git
   cd kailash-python-sdk
   pip install -e .

Install with Optional Dependencies
----------------------------------

For additional features, install with extras:

.. code-block:: bash

   # For API testing support
   pip install kailash[api-testing]

   # For development tools
   pip install kailash[dev]

   # For all optional dependencies
   pip install kailash[all]

Verify Installation
-------------------

Verify the installation by checking the version:

.. code-block:: bash

   python -c "import kailash; print(kailash.__version__)"

Or use the CLI:

.. code-block:: bash

   kailash --version

Your First Workflow
===================

Let's create a simple workflow that reads data, processes it, and saves the results.

Step 1: Import Required Components
----------------------------------

.. code-block:: python

   from kailash import Workflow
   from kailash.nodes import NodeRegistry

Step 2: Create a Workflow
-------------------------

.. code-block:: python

   # Create a new workflow
   workflow = Workflow("my_first_workflow")

Step 3: Add Nodes
-----------------

.. code-block:: python

   # Add a CSV reader node
   reader = workflow.add_node(
       node_type="CSVReaderNode",
       node_id="read_customers",
       config={
           "file_path": "customers.csv"
       }
   )

   # Add a data filter node
   filter_node = workflow.add_node(
       node_type="DataFilter",
       node_id="filter_active",
       config={
           "column": "status",
           "value": "active",
           "operation": "equals"
       }
   )

   # Add a CSV writer node
   writer = workflow.add_node(
       node_type="CSVWriterNode",
       node_id="save_results",
       config={
           "file_path": "active_customers.csv"
       }
   )

Step 4: Connect Nodes
---------------------

.. code-block:: python

   # Connect the nodes in sequence
   workflow.add_edge("read_customers", "filter_active")
   workflow.add_edge("filter_active", "save_results")

Step 5: Execute the Workflow
----------------------------

.. code-block:: python

   # Run the workflow
   results = workflow.run()

   # Check the results
   print(f"Workflow completed: {results.get('success')}")
   print(f"Output saved to: active_customers.csv")

Complete Example
----------------

Here's the complete script:

.. code-block:: python

   from kailash import Workflow

   # Create and configure workflow
   workflow = Workflow("customer_processing")

   # Add nodes
   workflow.add_node("CSVReaderNode", "read_data", config={
       "file_path": "customers.csv"
   })

   workflow.add_node("DataFilter", "filter_active", config={
       "column": "status",
       "value": "active"
   })

   workflow.add_node("CSVWriterNode", "save_data", config={
       "file_path": "active_customers.csv"
   })

   # Connect nodes
   workflow.add_edge("read_data", "filter_active")
   workflow.add_edge("filter_active", "save_data")

   # Execute
   results = workflow.run()

   if results["success"]:
       print("Workflow completed successfully!")
   else:
       print(f"Workflow failed: {results.get('error')}")

Understanding Node Types
========================

The SDK provides several categories of nodes:

Data Nodes
----------

For reading and writing data:

- **CSVReaderNode/CSVWriterNode**: Handle CSV files
- **JSONReaderNode/JSONWriterNode**: Handle JSON files
- **TextReaderNode/TextWriterNode**: Handle text files
- **SQLReader/Writer**: Database operations
- **SharePointReader/Writer**: SharePoint integration

Transform Nodes
---------------

For data manipulation:

- **DataFilter**: Filter rows based on conditions
- **DataMapper**: Transform data with custom logic
- **DataSorter**: Sort data by columns
- **DataTransformer**: Apply complex transformations

Logic Nodes
-----------

For workflow control:

- **SwitchNode**: Conditional routing based on data
- **MergeNode**: Combine multiple data streams
- **Validator**: Validate data against schemas

AI/ML Nodes
-----------

For AI and machine learning:

- **TextClassifier**: Classify text data
- **EmbeddingGeneratorNode**: Generate embeddings
- **LLMAgentNode**: Interact with language models

API Nodes
---------

For external integrations:

- **HTTPClient**: Make HTTP requests
- **RESTClient**: RESTful API interactions
- **GraphQLClient**: GraphQL queries

Code Nodes
----------

For custom logic:

- **PythonCodeNode**: Execute Python code safely

Cycle-Aware Nodes (New in v0.2.0)
---------------------------------

For iterative processing:

- **CycleAwareNode**: Base class with convergence detection
- **Built-in cycle support**: All nodes can participate in cycles
- **Automatic state management**: Track iterations and convergence

Next Steps
==========

Now that you've created your first workflow:

1. **Master Cyclic Workflows**: Learn about the new :doc:`guides/cyclic_workflows` (v0.2.0)
2. **Explore Examples**: Check out the :doc:`examples/index` section
3. **Build Complex Workflows**: See :doc:`guides/workflows`
4. **Create Custom Nodes**: Learn in :doc:`guides/custom_nodes`
5. **Best Practices**: Review :doc:`guides/best_practices`
6. **Developer Tools**: Explore CycleAnalyzer, CycleDebugger, and CycleProfiler

Common Patterns
===============

Data Processing Pipeline
------------------------

.. code-block:: python

   workflow = Workflow("etl_pipeline")

   # Extract
   workflow.add_node("CSVReaderNode", "extract", config={
       "file_path": "raw_data.csv"
   })

   # Transform
   workflow.add_node("DataTransformer", "transform", config={
       "operations": [
           {"type": "rename", "old": "cust_id", "new": "customer_id"},
           {"type": "cast", "column": "amount", "dtype": "float"},
           {"type": "filter", "condition": "amount > 0"}
       ]
   })

   # Load
   workflow.add_node("SQLWriter", "load", config={
       "connection_string": "postgresql://...",
       "table_name": "processed_data"
   })

   workflow.connect_sequential(["extract", "transform", "load"])
   workflow.run()

API Integration
---------------

.. code-block:: python

   workflow = Workflow("api_integration")

   # Read input data
   workflow.add_node("JSONReaderNode", "read_requests", config={
       "file_path": "api_requests.json"
   })

   # Make API calls
   workflow.add_node("RESTClient", "call_api", config={
       "base_url": "https://api.example.com",
       "method": "POST",
       "endpoint": "/process"
   })

   # Save responses
   workflow.add_node("JSONWriterNode", "save_responses", config={
       "file_path": "api_responses.json"
   })

   workflow.connect_sequential(["read_requests", "call_api", "save_responses"])
   workflow.run()

Iterative Processing (New in v0.2.0)
------------------------------------

Create workflows that iterate until convergence:

.. code-block:: python

   from kailash.workflow import CycleBuilder
   from kailash.nodes import PythonCodeNode

   # Use the new CycleBuilder API
   builder = CycleBuilder("iterative_refinement")

   # Add a node that refines results iteratively
   refiner_code = '''
   # Access previous iteration's state
   try:
       quality = cycle_state["quality"]
       data = cycle_state["data"]
   except:
       quality = 0.0
       data = input_data

   # Refine the data
   refined_data = [x * 1.1 for x in data]  # Simple refinement
   new_quality = min(quality + 0.2, 1.0)  # Improve quality

   # Check if we've reached target quality
   converged = new_quality >= 0.95

   result = {
       "data": refined_data,
       "quality": new_quality,
       "converged": converged
   }
   '''

   builder.add_cycle_node(
       "refiner",
       PythonCodeNode(name="refiner", code=refiner_code),
       input_mapping={"input_data": "data"},
       convergence_check="converged == True",
       max_iterations=10
   )

   # Build and run
   workflow = builder.build()
   results = workflow.run(parameters={
       "refiner": {"data": [1, 2, 3, 4, 5]}
   })

   print(f"Final quality: {results['refiner']['quality']}")
   print(f"Refined data: {results['refiner']['data']}")

Getting Help
============

If you need help:

- Check the :doc:`troubleshooting` guide
- Review the API documentation sections
- Visit our `GitHub Issues <https://github.com/terrene-foundation/kailash-py/issues>`_
- Join our community discussions

Happy workflow building! 🚀
