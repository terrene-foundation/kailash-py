.. Kailash Python SDK documentation master file

Kailash Python SDK Documentation
=================================

.. image:: https://img.shields.io/badge/python-3.11+-blue.svg
   :target: https://www.python.org/downloads/
   :alt: Python Version

.. image:: https://img.shields.io/badge/license-MIT-green.svg
   :target: https://opensource.org/licenses/MIT
   :alt: License

.. image:: https://img.shields.io/badge/version-0.8.1-green.svg
   :alt: SDK Version

.. image:: https://img.shields.io/badge/tests-2400%2B%20passing-brightgreen.svg
   :alt: Tests: 2400+ Passing

.. image:: https://img.shields.io/badge/performance-11x%20faster-yellow.svg
   :alt: Performance: 11x Faster

Welcome to the **Kailash Python SDK** - The enterprise-grade workflow orchestration platform that transforms how you build production applications. From zero-config database operations to multi-channel platforms, comprehensive AI integration, and enterprise-grade security.

🚀 **Latest Release: v0.8.1**
   Complete app framework with DataFlow, Nexus, AI Registry, and User Management platforms. 11x faster test execution with 100% pass rate across 2,400+ tests.

Quick Links
-----------

**🏗️ Complete Application Framework**
   Ready-to-deploy applications: :doc:`DataFlow <apps/dataflow>`, :doc:`Nexus <apps/nexus>`, :doc:`AI Registry <apps/ai-registry>`, and :doc:`User Management <apps/user-management>`.

**🚀 Getting Started**
   New to Kailash? Start with :doc:`installation <installation>` and your :doc:`first workflow <quickstart>`.

**📋 Node Ecosystem**
   Browse 115+ production-ready nodes with smart selection in the :doc:`Node Catalog <api/nodes>`.

**🏢 Enterprise Guide**
   Security, resilience, compliance, and production patterns. See :doc:`enterprise features <enterprise/index>`.

**📚 Framework Documentation**
   - **DataFlow**: Zero-config database operations with enterprise power
   - **Nexus**: Multi-channel orchestration (API, CLI, MCP) platform
   - **AI Registry**: Advanced RAG with 47+ specialized nodes
   - **User Management**: Enterprise RBAC with comprehensive security

What's New in v0.8.1
---------------------

**🎯 Complete Application Framework**

🏗️ **Production-Ready Applications**
   - **DataFlow**: Zero-config database operations with MongoDB-style queries
   - **Nexus**: Multi-channel platform (API + CLI + MCP) from single codebase
   - **AI Registry**: Advanced RAG with 47+ specialized nodes
   - **User Management**: Enterprise RBAC system with comprehensive security

⚡ **Performance Breakthrough**
   - **11x faster test execution**: 117s → 10.75s with smart isolation
   - **100% test pass rate**: 2,400+ tests across all categories
   - **31.8M operations/second**: Query performance baseline
   - **30,000+ iterations/second**: Cyclic workflow execution

🧪 **Testing Excellence**
   - **Docker Integration**: Real PostgreSQL, Redis, MongoDB for testing
   - **Smart Isolation**: Fixture-based isolation without process forking
   - **Comprehensive Coverage**: Unit, integration, and E2E testing
   - **Performance Monitoring**: Automated benchmarks and regression detection

🤖 **AI Integration**
   - **Real MCP execution** by default for all AI agents
   - **47+ specialized RAG nodes** for document processing
   - **Self-organizing agent pools** with intelligent coordination
   - **Complete LLM integration** with embeddings and vector search

📦 **PyPI Integration**
   - All packages available with proper extras support
   - ``pip install kailash[dataflow,nexus]`` for complete frameworks
   - Direct app installation: ``pip install kailash-dataflow``

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
   :caption: Application Framework
   :hidden:

   apps/dataflow
   apps/nexus
   apps/ai-registry
   apps/user-management
   apps/mcp-platform

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
   :caption: Enterprise Features
   :hidden:

   enterprise/index
   enterprise/security
   enterprise/compliance
   enterprise/monitoring
   enterprise/deployment

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
   testing
   unimplemented_nodes_tracker
   v0.2.0-release-summary
   adr/index

Key Features
------------

🎯 **Enterprise Application Framework**
   Complete production-ready applications, not just building blocks. DataFlow for database operations, Nexus for multi-channel deployment, AI Registry for RAG, and User Management for security.

🤖 **AI-First Design**
   Native support for LLMs, embeddings, RAG, and multi-agent coordination with real MCP execution by default.

🏗️ **Production-Grade Infrastructure**
   Enterprise security, monitoring, resilience patterns, compliance frameworks, and multi-tenant architecture.

⚡ **Exceptional Performance**
   11x faster test execution, 31.8M operations/second queries, connection pooling, and optimized async operations.

🧪 **Testing Excellence**
   2,400+ tests with 100% pass rate, Docker integration, smart isolation, and comprehensive validation.

🔧 **115+ Production Nodes**
   Comprehensive node ecosystem covering data, AI, security, monitoring, transactions, and enterprise operations.

Quick Start Examples
--------------------

**DataFlow - Zero-Config Database Operations**

.. code-block:: python

   from dataflow import DataFlow

   # Zero-configuration database operations
   app = DataFlow()

   # MongoDB-style queries across any database
   users = app.query("users").where({"age": {"$gt": 18}}).limit(10)

   # Redis-powered caching with smart invalidation
   cached_result = app.cache().get("user_stats",
       lambda: app.query("users").aggregate([
           {"$group": {"_id": "$department", "count": {"$sum": 1}}}
       ])
   )

   # Start enterprise API server
   app.start()  # Automatic API generation, monitoring, health checks

**Nexus - Multi-Channel Platform**

.. code-block:: python

   from nexus import Nexus

   # Single codebase → API + CLI + MCP
   app = Nexus()

   # Register workflow once, available on all channels
   @app.workflow
   def process_data(input_data):
       return {"processed": len(input_data)}

   app.start()
   # Now available as REST API, CLI command, and MCP tool

**Core SDK - Advanced Workflows**

.. code-block:: python

   from kailash.workflow.builder import WorkflowBuilder
   from kailash.runtime.local import LocalRuntime

   # Build enterprise workflow
   workflow = WorkflowBuilder()
   workflow.add_node("LLMAgentNode", "ai_agent", {
       "model": "gpt-4",
       "use_real_mcp": True  # Real MCP execution by default
   })
   workflow.add_node("AsyncSQLDatabaseNode", "database", {
       "connection_string": "postgresql://...",
       "query": "SELECT * FROM customers WHERE risk_score > $1",
       "parameter_types": ["DECIMAL"]  # PostgreSQL type inference
   })

   # Add cyclic optimization
   cycle = workflow.create_cycle("optimization")
   cycle.connect("processor", "evaluator") \
        .connect("evaluator", "processor") \
        .max_iterations(50) \
        .converge_when("quality > 0.95") \
        .build()

   # Execute with enterprise monitoring
   runtime = LocalRuntime()
   results, run_id = runtime.execute(workflow.build())

Architecture Overview
---------------------

The Kailash SDK provides a three-layer architecture for maximum flexibility:

.. mermaid::

   graph TB
       subgraph Studio["🎨 Studio UI Layer"]
           Visual[Visual Workflow Builder]
           Admin[Admin Dashboards]
           Monitor[Real-time Monitoring]
       end

       subgraph Applications["🏗️ Application Framework"]
           DataFlow[DataFlow<br/>Zero-Config Database]
           Nexus[Nexus<br/>Multi-Channel Platform]
           AIRegistry[AI Registry<br/>Advanced RAG]
           UserMgmt[User Management<br/>Enterprise RBAC]
       end

       subgraph SDK["🎯 Core SDK Foundation"]
           Nodes[115+ Production Nodes]
           Workflow[Workflow Engine]
           Runtime[Runtime Options]
           Security[Security Framework]
           Testing[Testing Infrastructure]
       end

       subgraph Infrastructure["⚙️ Infrastructure"]
           Docker[Docker Integration]
           K8s[Kubernetes Deployment]
           Cloud[Cloud Services]
           MCP[MCP Servers]
           Monitoring[Monitoring Stack]
       end

       Studio --> Applications
       Applications --> SDK
       SDK --> Infrastructure

       style DataFlow fill:#e3f2fd
       style Nexus fill:#f3e5f5
       style AIRegistry fill:#e8f5e9
       style UserMgmt fill:#fff3e0
       style Nodes fill:#e8f5e9
       style Workflow fill:#fff9c4
       style Testing fill:#f1f8e9

Performance Benchmarks
----------------------

**Recent Achievements:**
   - **11x faster test execution**: 117s → 10.75s with smart isolation
   - **100% test pass rate**: 2,400+ tests across all categories
   - **31.8M operations/second**: Query performance baseline
   - **30,000+ iterations/second**: Cyclic workflow execution

**Enterprise Benchmarks:**
   - **Query Cache**: 99.9% hit rate with intelligent invalidation
   - **Connection Pooling**: 10,000+ concurrent connections
   - **MCP Integration**: 407 tests with 100% pass rate
   - **Security**: Zero vulnerabilities in production deployment

Node Ecosystem (115+ Nodes)
----------------------------

**Core Categories:**
   - **Data Nodes**: CSVReaderNode, AsyncSQLDatabaseNode, QueryBuilderNode, QueryCacheNode
   - **AI Nodes**: LLMAgentNode, IterativeLLMAgentNode, EmbeddingGeneratorNode, SelfOrganizingAgentNode
   - **RAG Nodes**: 47+ specialized nodes for document processing and retrieval
   - **Security Nodes**: ThreatDetectionNode, AuditLogNode, AccessControlManager
   - **Monitoring Nodes**: TransactionMetricsNode, DeadlockDetectorNode, PerformanceAnomalyNode
   - **Transaction Nodes**: DistributedTransactionManagerNode, SagaCoordinatorNode

**Advanced Features:**
   - **Cyclic Workflows**: CycleBuilder API with convergence detection
   - **Distributed Transactions**: Automatic Saga/2PC pattern selection
   - **Real-time Monitoring**: WebSocket streaming with performance metrics
   - **Enterprise Security**: Multi-factor auth, threat detection, compliance

Installation & Setup
--------------------

**Quick Installation:**

.. code-block:: bash

   # Core SDK only
   pip install kailash

   # With complete app frameworks
   pip install kailash[dataflow,nexus]  # Database + multi-channel
   pip install kailash[all]             # Everything

   # Or install apps directly
   pip install kailash-dataflow  # Zero-config database framework
   pip install kailash-nexus     # Multi-channel platform

**Development Setup:**

.. code-block:: bash

   # Clone and setup
   git clone https://github.com/terrene-foundation/kailash-py.git
   cd kailash-python-sdk
   uv sync

   # Run tests (2,400+ tests)
   pytest tests/unit/ --timeout=1      # Fast unit tests
   pytest tests/integration/ --timeout=5  # Integration tests
   pytest tests/e2e/ --timeout=10     # End-to-end tests

Community & Support
-------------------

- **GitHub**: `github.com/terrene-foundation/kailash-py <https://github.com/terrene-foundation/kailash-py>`_
- **Issues**: Report bugs and request features
- **PyPI**: `pypi.org/project/kailash <https://pypi.org/project/kailash>`_
- **Documentation**: Complete guides and API reference
- **Contributing**: Claude Code-driven development workflow

License
-------

The Kailash Python SDK is released under the MIT License. See the :doc:`license` file for details.

Built with ❤️ by the Terrene Foundation team for the Kailash ecosystem.

Special recognition for the **11x performance breakthrough** and **100% test pass rate** achieved through innovative engineering and comprehensive testing strategies.

Indices and Tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
