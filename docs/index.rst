.. Kailash Python SDK documentation master file

Kailash Python SDK Documentation
=================================

.. image:: https://img.shields.io/badge/python-3.8+-blue.svg
   :target: https://www.python.org/downloads/
   :alt: Python Version

.. image:: https://img.shields.io/badge/license-MIT-green.svg
   :target: https://opensource.org/licenses/MIT
   :alt: License

.. image:: https://img.shields.io/badge/version-0.6.6+-green.svg
   :alt: SDK Version

Welcome to the **Kailash Python SDK** - The enterprise-grade workflow orchestration platform that bridges AI and traditional software development with production-ready patterns and frameworks.

.. warning::
   **Documentation Enhancement in Progress**: We're integrating 200+ documentation files to provide comprehensive coverage. Some links may be temporarily unavailable.

Quick Links
-----------

**🚀 Getting Started**
   New to Kailash? Start here with :doc:`installation <installation>` and your :doc:`first workflow <quickstart>`.

**📋 Quick Reference**
   54+ cheatsheets with copy-paste patterns for common tasks. *Coming soon!*

**🔍 Node Catalog**
   Browse 110+ production-ready nodes with smart selection guide in the :doc:`API Reference <api/nodes>`.

**🏢 Enterprise Guide**
   Security, resilience, compliance, and production patterns. See :doc:`best practices <best_practices>`.

**🔧 Framework Guides**
   - **DataFlow**: Zero-config database operations with enterprise power
   - **Nexus**: Multi-channel orchestration (API, CLI, MCP) platform

What's New
----------

**v0.6.6+ Latest Features:**

🔌 **MCP Production Hardening**
   - Real MCP execution by default (``use_real_mcp=True``)
   - LLMAgentNode now supports explicit MCP control
   - Comprehensive MCP testing infrastructure

📊 **Enterprise Monitoring**
   - Transaction monitoring with deadlock detection
   - Race condition analysis and performance anomaly detection
   - Distributed transaction management (Saga & 2PC patterns)

🏗️ **Framework Enhancements**
   - DataFlow: Modular architecture with 100% backward compatibility
   - Nexus: Production-hardened with Terraform automation
   - Query Builder: MongoDB-style queries across databases
   - Query Cache: Redis-powered with pattern invalidation

🧪 **Testing Excellence**
   - 3,000+ tests with 100% pass rate
   - Comprehensive validation framework
   - Test-driven development patterns

.. toctree::
   :maxdepth: 2
   :caption: Getting Started
   :hidden:

   getting_started
   installation
   quickstart
   tutorials/index

.. toctree::
   :maxdepth: 2
   :caption: User Guide
   :hidden:

   best_practices
   troubleshooting
   performance
   workflow_studio
   data-consolidation-guide
   enhancements/sql-oauth-credential-enhancements
   features/http_nodes_comparison

.. toctree::
   :maxdepth: 2
   :caption: Model Context Protocol (MCP)
   :hidden:

   mcp/index

.. toctree::
   :maxdepth: 2
   :caption: API Reference
   :hidden:

   api/nodes
   api/workflow
   api/middleware
   api/gateway
   api/workflow_api
   api/runtime
   api/access_control
   api/tracking
   api/visualization
   api/utils
   api/cli

.. toctree::
   :maxdepth: 2
   :caption: Examples
   :hidden:

   examples/index
   examples/self_organizing_agents
   examples/mcp_ecosystem

.. toctree::
   :maxdepth: 1
   :caption: Development
   :hidden:

   changelog
   contributing
   security
   unimplemented_nodes_tracker
   v0.2.0-release-summary
   adr/index

Key Features
------------

🎯 **Workflow Orchestration**
   Build complex workflows by connecting reusable nodes with visual or code-based approaches.

🤖 **AI-First Design**
   Native support for LLMs, embeddings, RAG, and multi-agent coordination with MCP integration.

🏗️ **Enterprise Ready**
   Production-grade security, monitoring, resilience patterns, and compliance features.

⚡ **High Performance**
   Async execution, connection pooling, distributed transactions, and optimized data operations.

🔧 **Extensible Architecture**
   Create custom nodes, middleware, and frameworks with simple Python classes.

📊 **Comprehensive Monitoring**
   Real-time metrics, distributed tracing, health checks, and performance analytics.

Quick Example
-------------

.. code-block:: python

   from kailash.workflow.builder import WorkflowBuilder
   from kailash.runtime.local import LocalRuntime

   # Build a workflow
   workflow = WorkflowBuilder()
   workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
   workflow.add_node("LLMAgentNode", "analyzer", {
       "model": "gpt-4",
       "use_real_mcp": True  # Real MCP execution (v0.6.6+)
   })
   workflow.add_connection("reader", "data", "analyzer", "input")

   # Execute
   runtime = LocalRuntime()
   results, run_id = runtime.execute(workflow.build())

Architecture Overview
---------------------

The Kailash SDK provides a layered architecture for maximum flexibility:

.. mermaid::

   graph TB
       subgraph Applications["🏗️ Applications & Frameworks"]
           DataFlow[DataFlow<br/>Database Operations]
           Nexus[Nexus<br/>Multi-Channel Platform]
           Custom[Custom Apps]
       end

       subgraph SDK["🎯 Core SDK"]
           Nodes[110+ Nodes]
           Workflow[Workflow Engine]
           Runtime[Runtime Options]
           Middleware[Middleware]
       end

       subgraph Infrastructure["⚙️ Infrastructure"]
           Docker[Docker]
           K8s[Kubernetes]
           Cloud[Cloud Services]
           MCP[MCP Servers]
       end

       Applications --> SDK
       SDK --> Infrastructure

       style DataFlow fill:#e3f2fd
       style Nexus fill:#f3e5f5
       style Nodes fill:#e8f5e9
       style Workflow fill:#fff9c4

Community & Support
-------------------

- **GitHub**: `github.com/terrene-foundation/kailash-py <https://github.com/terrene-foundation/kailash-py>`_
- **Issues**: Report bugs and request features
- **Discussions**: Ask questions and share patterns
- **Contributing**: See our :doc:`contributing` guide

License
-------

The Kailash Python SDK is released under the MIT License. See the :doc:`license` file for details.

Indices and Tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
