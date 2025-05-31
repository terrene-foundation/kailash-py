.. Kailash Python SDK documentation master file

====================================
Kailash Python SDK API Documentation
====================================

.. image:: https://img.shields.io/badge/python-3.8+-blue.svg
   :target: https://www.python.org/downloads/
   :alt: Python Version

.. image:: https://img.shields.io/badge/license-MIT-green.svg
   :target: https://opensource.org/licenses/MIT
   :alt: License

Welcome to the Kailash Python SDK documentation! This SDK provides a comprehensive framework for building workflow-based applications with a container-node architecture.

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   getting_started
   installation
   quickstart
   tutorials/index

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   best_practices
   troubleshooting
   performance

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/nodes
   api/workflow
   api/runtime
   api/tracking
   api/visualization
   api/utils
   api/cli

.. toctree::
   :maxdepth: 2
   :caption: Examples

   examples/basic
   examples/advanced
   examples/integrations
   examples/patterns

.. toctree::
   :maxdepth: 1
   :caption: Development

   migration_guide
   changelog
   contributing
   security

Overview
========

The Kailash Python SDK is designed to bridge the gap between AI Business Coaches (ABCs) and the Product Delivery Team (PDT) at Terrene Foundation. It provides:

- **Node-Based Architecture**: Build complex workflows by connecting reusable nodes
- **Extensive Node Library**: Pre-built nodes for data I/O, transformation, AI/ML, APIs, and more
- **Flexible Runtime**: Execute workflows locally, in Docker, or distributed environments
- **Task Tracking**: Monitor workflow execution with detailed metrics and logs
- **Easy Extension**: Create custom nodes with simple Python classes

Key Features
------------

🔧 **Comprehensive Node Library**
   - Data I/O: CSV, JSON, Text, SQL, SharePoint
   - Transform: Filter, Map, Sort, Custom processors
   - Logic: Switch, Merge, Conditional routing
   - AI/ML: Classification, Embeddings, NLP
   - API: REST, GraphQL, HTTP with auth
   - Code: Secure Python code execution

📊 **Workflow Management**
   - Visual workflow builder
   - State management
   - Error handling and recovery
   - Parallel execution
   - Conditional routing

🚀 **Multiple Runtime Options**
   - Local execution for development
   - Docker runtime for isolation
   - Async execution for I/O operations
   - Parallel processing for performance

📈 **Monitoring & Analytics**
   - Real-time task tracking
   - Performance metrics and visualization
   - Live monitoring dashboards with WebSocket streaming
   - Comprehensive performance reports (HTML, Markdown, JSON)
   - Interactive charts with Chart.js integration
   - Resource utilization monitoring (CPU, memory, I/O)
   - Execution history and bottleneck analysis

Quick Example
-------------

.. code-block:: python

   from kailash import Workflow, NodeRegistry

   # Create a simple data processing workflow
   workflow = Workflow("data_processing")

   # Add nodes
   reader = workflow.add_node("CSVReader", "read_data", config={
       "file_path": "customers.csv"
   })

   filter_node = workflow.add_node("DataFilter", "filter_active", config={
       "column": "status",
       "value": "active"
   })

   writer = workflow.add_node("CSVWriter", "save_results", config={
       "file_path": "active_customers.csv"
   })

   # Connect nodes
   workflow.add_edge("read_data", "filter_active")
   workflow.add_edge("filter_active", "save_results")

   # Execute workflow
   results = workflow.run()

Architecture Overview
--------------------

.. mermaid::

   graph TB
       subgraph "Node Types"
           A[Data Nodes]
           B[Transform Nodes]
           C[Logic Nodes]
           D[AI/ML Nodes]
           E[API Nodes]
           F[Code Nodes]
       end

       subgraph "Workflow Engine"
           G[Builder]
           H[Graph]
           I[Runner]
           J[State Manager]
       end

       subgraph "Runtime"
           K[Local]
           L[Docker]
           M[Async]
           N[Parallel]
       end

       A --> G
       B --> G
       C --> G
       D --> G
       E --> G
       F --> G

       G --> H
       H --> I
       I --> J

       I --> K
       I --> L
       I --> M
       I --> N

Indices and Tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
