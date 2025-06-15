.. Kailash Python SDK documentation master file


Kailash Python SDK API Documentation
====================================

.. image:: https://img.shields.io/badge/python-3.8+-blue.svg
   :target: https://www.python.org/downloads/
   :alt: Python Version

.. image:: https://img.shields.io/badge/license-MIT-green.svg
   :target: https://opensource.org/licenses/MIT
   :alt: License

Welcome to the Kailash Python SDK v0.4.0 documentation! This release introduces the
**Enterprise Middleware Architecture** with real-time communication and production-ready features.

**Latest Updates (v0.4.0):**
- 🌉 **Enterprise Middleware Architecture** - Complete refactor from monolithic to composable middleware
- 🔄 **Real-time Communication** - WebSocket/SSE with comprehensive event streaming
- 🤖 **AI Chat Integration** - Built-in chat middleware with natural language workflow generation
- ✅ **Test Excellence** - 799 tests passing (100% pass rate), CI optimization
- 🚀 **Production Ready** - Health checks, metrics, graceful shutdown, connection pooling

**Previous Updates (v0.3.2):**
- 🛡️ **Admin Tool Framework** - Complete enterprise admin infrastructure with React UI, RBAC, audit logging
- 🔒 **Async Database & ABAC** - High-performance async database operations with Attribute-Based Access Control
- 🧪 **LLM-based QA Testing** - Comprehensive QA framework with AI agents for frontend and backend testing
- 📊 **100+ Production Nodes** - Expanded node library including middleware, admin, security, and async database nodes

**Previous Updates (v0.3.1):**
- 💼 **Complete Finance Workflow Library** - Production-ready credit risk, portfolio optimization, trading signals, fraud detection
- 🧠 **PythonCodeNode Best Practices** - Enhanced from_function() patterns with comprehensive training data
- 🚀 **Enhanced MCP Server** - Zero-configuration workflow exposure with default tools for discovery and execution

**Previous Major Release (v0.2.0):**
- 🔁 **Universal Hybrid Cyclic Graph Architecture** with 30,000+ iterations/second performance
- 🛠️ **Developer Tools** - CycleAnalyzer, CycleDebugger, CycleProfiler for production cyclic workflows

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
   workflow_studio

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/nodes
   api/workflow
   api/middleware
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

   examples/index
   examples/self_organizing_agents
   examples/mcp_ecosystem

.. toctree::
   :maxdepth: 1
   :caption: Development

   migration_guide
   changelog
   contributing
   security
   unimplemented_nodes_tracker

Overview
========

The Kailash Python SDK is designed to bridge the gap between AI Business
Coaches (ABCs) and the Product Delivery Team (PDT) at Terrene Foundation. It provides:

- **Node-Based Architecture**: Build complex workflows by connecting
  reusable nodes
- **Extensive Node Library**: Pre-built nodes for data I/O, transformation,
  AI/ML, APIs, and more
- **Coordinated AI Workflows**: Advanced multi-agent systems with A2A communication,
  self-organizing agent pools, and MCP integration
- **Flexible Runtime**: Execute workflows locally, in Docker, or distributed
  environments
- **Access Control**: Comprehensive RBAC and multi-tenant security
- **Task Tracking**: Monitor workflow execution with detailed metrics and logs
- **Easy Extension**: Create custom nodes with simple Python classes

Key Features
------------

🔧 **Comprehensive Node Library (85+ Nodes)**
   - Data I/O: CSV, JSON, Text, SQL, AsyncSQL, SharePoint
   - Admin: UserManagement, RoleManagement, PermissionCheck, AuditLog, SecurityEvent
   - Transform: Filter, Map, Sort, Custom processors
   - Logic: SwitchNode, MergeNode, Conditional routing
   - AI/ML: Classification, Embeddings, NLP, MCPAgent
   - API: REST, GraphQL, HTTP with auth
   - Security: Enhanced Access Control (ABAC with 16 operators)
   - Code: Secure Python code execution

🤖 **Advanced AI Coordination**
   - **A2A (Agent-to-Agent)**: Direct communication between AI agents
   - **Self-Organizing Agent Pools**: Autonomous team formation and problem solving
   - **MCP (Model Context Protocol)**: AI context management and tool discovery
   - **Enhanced MCP Server**: Zero-config workflow exposure with built-in discovery tools
   - **Intelligent Orchestration**: Adaptive workflows with convergence detection
   - **Multi-Agent Workflows**: Coordinated agent teams for complex tasks

📊 **Workflow Management**
   - Visual workflow builder
   - State management
   - Error handling and recovery
   - Parallel execution
   - Conditional routing
   - **Cyclic workflows** with convergence detection and developer tools

🚀 **Multiple Runtime Options**
   - Local execution for development
   - Docker runtime for isolation
   - Async execution for I/O operations
   - Parallel processing for performance

🔄 **Universal Hybrid Cyclic Graph Architecture** (New in v0.2.0)
   - **High-Performance Cycles**: 30,000+ iterations/second
   - **Automatic Convergence**: Built-in trend detection and early termination
   - **Developer Tools**: CycleAnalyzer, CycleDebugger, CycleProfiler
   - **Phase 5 API**: CycleBuilder for intuitive cyclic workflow creation
   - **Cycle-Aware Nodes**: Pre-built support for iterative processing

🌐 **REST API Wrapper**
   - Expose any workflow as REST API
   - Automatic OpenAPI documentation
   - Multiple execution modes (sync/async/stream)
   - Production-ready with FastAPI

📈 **Monitoring & Analytics**
   - Real-time task tracking
   - Performance metrics and visualization
   - Live monitoring dashboards with WebSocket streaming
   - Comprehensive performance reports (HTML, Markdown, JSON)
   - Interactive charts with Chart.js integration
   - Resource utilization monitoring (CPU, memory, I/O)
   - Execution history and bottleneck analysis

🛡️ **Admin Tool Framework** (New in v0.3.2)
   - **Enterprise Admin Nodes**: UserManagement, RoleManagement, PermissionCheck, AuditLog, SecurityEvent
   - **React UI Components**: Complete admin interfaces with TypeScript integration
   - **RBAC & Multi-Tenancy**: Role-based access control with hierarchical permissions
   - **Async Database Support**: High-performance PostgreSQL with connection pooling
   - **ABAC Security**: Attribute-Based Access Control with 16 operators and data masking
   - **LLM-based QA Testing**: Comprehensive testing framework with AI QA agents

💼 **Finance Workflow Library** (v0.3.1)
   - **Credit Risk Assessment**: AI-powered risk scoring with customer and transaction analysis
   - **Portfolio Optimization**: Modern Portfolio Theory with Sharpe ratio optimization and rebalancing
   - **Trading Signals**: Technical indicators (RSI, MACD, Bollinger Bands) with AI sentiment analysis
   - **Fraud Detection**: Real-time transaction monitoring with velocity analysis and pattern detection
   - **Production-Ready**: All workflows use PythonCodeNode.from_function() best practices

Quick Example
-------------

.. code-block:: python

   from kailash import Workflow
   from kailash.nodes import NodeRegistry

   # Create a simple data processing workflow
   workflow = Workflow("data_processing")

   # Add nodes
   reader = workflow.add_node("CSVReaderNode", "read_data", config={
       "file_path": "customers.csv"
   })

   filter_node = workflow.add_node("DataFilter", "filter_active", config={
       "column": "status",
       "value": "active"
   })

   writer = workflow.add_node("CSVWriterNode", "save_results", config={
       "file_path": "active_customers.csv"
   })

   # Connect nodes
   workflow.add_edge("read_data", "filter_active")
   workflow.add_edge("filter_active", "save_results")

   # Execute workflow
   results = workflow.run()

Coordinated AI Workflow Example
-------------------------------

.. code-block:: python

   from kailash import Workflow
   from kailash.nodes.ai.self_organizing import (
       AgentPoolManagerNode, ProblemAnalyzerNode,
       TeamFormationNode, SelfOrganizingAgentNode
   )
   from kailash.nodes.ai.a2a import A2ACoordinatorNode
   from kailash.runtime import LocalRuntime

   # Create a self-organizing research system
   workflow = Workflow("ai_research_team")

   # Add agent pool manager and problem analyzer
   workflow.add_node("pool_manager", AgentPoolManagerNode())
   workflow.add_node("problem_analyzer", ProblemAnalyzerNode())
   workflow.add_node("team_formation", TeamFormationNode())
   workflow.add_node("coordinator", A2ACoordinatorNode())

   # Create specialized agents
   agents = [
       ("data_analyst", ["data_analysis", "statistics"]),
       ("ml_engineer", ["machine_learning", "modeling"]),
       ("researcher", ["research", "literature_review"])
   ]

   for agent_id, capabilities in agents:
       workflow.add_node(agent_id, SelfOrganizingAgentNode(), config={
           "agent_id": agent_id,
           "capabilities": capabilities,
           "provider": "openai",
           "model": "gpt-4"
       })

   # Execute with a complex research problem
   runtime = LocalRuntime()
   result, _ = runtime.execute(workflow, parameters={
       "problem_analyzer": {
           "problem_description": "Analyze customer churn patterns and predict future behavior"
       }
   })

Finance Workflow Example (New in v0.3.1)
----------------------------------------

**Credit Risk Assessment with AI Analysis:**

.. code-block:: python

   from kailash.workflow import Workflow
   from kailash.nodes.data import CSVReaderNode, JSONWriterNode
   from kailash.nodes.code import PythonCodeNode
   from kailash.nodes.ai import LLMAgentNode
   from kailash.runtime import LocalRuntime

   def calculate_risk_metrics(customers, transactions):
       """Calculate comprehensive risk metrics for credit assessment."""
       import pandas as pd
       import numpy as np

       # Convert to DataFrames
       customers_df = pd.DataFrame(customers)
       transactions_df = pd.DataFrame(transactions)

       # Calculate transaction metrics per customer
       transaction_metrics = transactions_df.groupby("customer_id").agg({
           "amount": ["sum", "mean", "count", "std"],
           "transaction_date": ["min", "max"]
       }).reset_index()

       # Merge with customer data and calculate risk scores
       risk_df = pd.merge(customers_df, transaction_metrics, on="customer_id", how="left")

       # Calculate composite risk score (0-100, higher is better/lower risk)
       risk_df["risk_score"] = (
           risk_df["tier_score"] * 0.4 +
           risk_df["transaction_score"] * 0.3 +
           risk_df["amount_score"] * 0.3
       ).clip(0, 100)

       return {"result": risk_df.to_dict("records")}

   # Create workflow
   workflow = Workflow("credit-risk-assessment", "Credit Risk Assessment System")

   # Add nodes
   workflow.add_node("customer_reader", CSVReaderNode(file_path="customers.csv"))
   workflow.add_node("transaction_reader", CSVReaderNode(file_path="transactions.csv"))
   workflow.add_node("risk_calculator", PythonCodeNode.from_function(func=calculate_risk_metrics))

   # AI-powered risk analysis
   workflow.add_node("risk_analyzer", LLMAgentNode(
       model="gpt-4",
       system_prompt="You are a financial risk assessment expert. Analyze customer risk data.",
       prompt="Analyze the following customer risk metrics: {{risk_metrics}}"
   ))

   workflow.add_node("report_writer", JSONWriterNode(
       file_path="credit_risk_reports.json", pretty_print=True
   ))

   # Connect nodes
   workflow.connect("customer_reader", "risk_calculator", mapping={"data": "customers"})
   workflow.connect("transaction_reader", "risk_calculator", mapping={"data": "transactions"})
   workflow.connect("risk_calculator", "risk_analyzer", mapping={"result": "risk_metrics"})
   workflow.connect("risk_analyzer", "report_writer", mapping={"response": "data"})

   # Execute
   runtime = LocalRuntime()
   results, run_id = runtime.execute(workflow)

Cyclic Workflow Example (New in v0.2.0)
---------------------------------------

**Using the new CycleBuilder API:**

.. code-block:: python

   from kailash.workflow import CycleBuilder
   from kailash.nodes import PythonCodeNode

   # Phase 5 API - Simple and intuitive
   builder = CycleBuilder("gradient_descent")

   # Add optimizer with automatic convergence tracking
   optimizer_code = '''
   # Access previous state with automatic defaults
   try:
       value = cycle_state["value"]
   except:
       value = 0.1

   # Gradient descent step
   gradient = 2 * (value - 0.5)  # derivative of (x-0.5)^2
   learning_rate = 0.1
   new_value = value - learning_rate * gradient

   # Check convergence
   converged = abs(new_value - value) < 0.001

   result = {"value": new_value, "converged": converged}
   '''

   builder.add_cycle_node(
       "optimizer",
       PythonCodeNode(name="optimizer", code=optimizer_code),
       initial_state={"value": 0.1},
       convergence_check="converged == True",
       max_iterations=100
   )

   # Build and run
   workflow = builder.build()
   results = workflow.run()

   # Analyze with developer tools
   from kailash.workflow import CycleAnalyzer
   analyzer = CycleAnalyzer(workflow)
   report = analyzer.analyze_execution(results)
   print(f"Converged in {report['iterations']} iterations")
   print(f"Performance: {report['iterations_per_second']:.0f} iter/sec")

**Using Cycle-Aware Nodes:**

.. code-block:: python

   from kailash.nodes.base_cycle_aware import CycleAwareNode

   class OptimizerNode(CycleAwareNode):
       """Iterative optimization with built-in convergence tools."""

       def run(self, context, **kwargs):
           # Automatic iteration tracking
           iteration = self.get_iteration(context)
           prev_state = self.get_previous_state(context)

           # Your optimization logic
           value = prev_state.get("value", 0.1)
           improvement = 0.1 * (1 - value)
           new_value = value + improvement

           # Built-in convergence detection
           self.accumulate_values(context, "value", new_value)
           trend = self.detect_convergence_trend(context, "value")

           # Automatic state management
           self.set_cycle_state({"value": new_value})
           converged = new_value > 0.95 or trend["converging"]

           return {"value": new_value, "converged": converged}

Architecture Overview
---------------------

The Kailash SDK follows a modular architecture with three main layers:

.. mermaid::

   graph TB
       subgraph NodeTypes["Node Types"]
           A[Data Nodes]
           B[Transform Nodes]
           C[Logic Nodes]
           D[AI/ML Nodes]
           E[API Nodes]
           F[Code Nodes]
       end

       subgraph WorkflowEngine["Workflow Engine"]
           G[Builder]
           H[Graph]
           I[Runner]
           J[State Manager]
       end

       subgraph Runtime["Runtime Options"]
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

       style A fill:#e1f5fe
       style B fill:#e8f5e8
       style C fill:#fff3e0
       style D fill:#f3e5f5
       style E fill:#fce4ec
       style F fill:#e0f2f1

.. note::
   If the diagram above doesn't render properly, you can view the `interactive architecture diagram <_static/architecture_diagram.html>`_ in a separate window.

Indices and Tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
