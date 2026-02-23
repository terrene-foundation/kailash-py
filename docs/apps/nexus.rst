Nexus - Multi-Channel Platform
==============================

.. image:: https://img.shields.io/badge/app-nexus-purple.svg
   :alt: Nexus Application

.. image:: https://img.shields.io/badge/multi--channel-platform-green.svg
   :alt: Multi-Channel Platform

Nexus is a revolutionary multi-channel platform that allows you to expose workflows through API, CLI, and MCP interfaces from a single codebase. Register once, deploy everywhere.

Overview
--------

Nexus eliminates the traditional need to build separate APIs, CLI tools, and AI agent integrations. With Nexus, you register your workflow once and it becomes automatically available through all channels with unified session management and cross-channel synchronization.

Key Features
------------

🔄 **Single Codebase → Multiple Channels**
   Register workflows once, automatically available as REST API, CLI commands, and MCP tools.

🎯 **Zero Configuration**
   Start with ``app = Nexus()`` and ``app.start()`` - no routing, no CLI setup, no MCP server configuration.

🔐 **Enterprise Orchestration**
   Multi-tenancy, RBAC, session management, and cross-channel synchronization built-in.

🤖 **Real MCP Integration**
   AI agents can discover and execute your workflows as tools with full parameter validation.

📊 **Unified Monitoring**
   Single dashboard for API requests, CLI usage, and MCP tool executions with comprehensive metrics.

🏢 **Production Ready**
   Health checks, rate limiting, audit logging, and enterprise security patterns included.

Installation
------------

.. code-block:: bash

   # Install Nexus directly
   pip install kailash-nexus

   # Or as part of Kailash
   pip install kailash[nexus]

Quick Start
-----------

**Basic Multi-Channel Deployment:**

.. code-block:: python

   from nexus import Nexus

   # Zero-configuration startup
   app = Nexus()

   # Register workflow once
   @app.workflow
   def process_data(input_data: list, operation: str = "sum") -> dict:
       """Process a list of numbers with the specified operation."""
       if operation == "sum":
           result = sum(input_data)
       elif operation == "avg":
           result = sum(input_data) / len(input_data)
       else:
           result = len(input_data)

       return {"result": result, "operation": operation, "count": len(input_data)}

   # Start all channels
   app.start()

   # Now available as:
   # - REST API: POST /workflows/process_data
   # - CLI: nexus run process_data --input-data "[1,2,3]" --operation sum
   # - MCP: AI agents can call process_data tool

**Advanced Workflow Registration:**

.. code-block:: python

   from nexus import Nexus
   from kailash.workflow.builder import WorkflowBuilder

   app = Nexus()

   import os

   # Register complex Kailash workflows
   def create_analysis_workflow():
       model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")
       workflow = WorkflowBuilder()
       workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
       workflow.add_node("LLMAgentNode", "analyzer", {
           "model": model,
           "use_real_mcp": True
       })
       workflow.add_connection("reader", "data", "analyzer", "input")
       return workflow.build()

   app.register("data_analysis", create_analysis_workflow())

   # Enterprise configuration
   app.enable_auth()
   app.enable_monitoring()
   app.start()

Multi-Channel Architecture
--------------------------

**Channel Overview:**

.. mermaid::

   graph LR
       User[👤 User] --> API[🌐 REST API]
       User --> CLI[💻 CLI Interface]
       AI[🤖 AI Agent] --> MCP[🔗 MCP Protocol]

       API --> Nexus[🎯 Nexus Core]
       CLI --> Nexus
       MCP --> Nexus

       Nexus --> Workflow1[📊 Analytics]
       Nexus --> Workflow2[🔄 ETL Pipeline]
       Nexus --> Workflow3[🤖 AI Processing]

**REST API Channel:**

.. code-block:: bash

   # Automatic REST endpoints
   GET  /workflows                    # List all workflows
   POST /workflows/{name}             # Execute workflow
   GET  /workflows/{name}/info        # Workflow metadata
   GET  /executions/{run_id}          # Execution status
   GET  /docs                         # OpenAPI documentation
   GET  /health                       # Health checks

**CLI Channel:**

.. code-block:: bash

   # Automatic CLI commands
   nexus list                              # List workflows
   nexus run process_data --help          # Show workflow help
   nexus run process_data --input-data "[1,2,3]"  # Execute workflow
   nexus status {run_id}                   # Check execution status
   nexus logs {run_id}                     # View execution logs

**MCP Channel:**

.. code-block:: python

   # AI agents automatically discover workflows as tools
   # Available MCP tools:
   # - process_data(input_data: list, operation: str) -> dict
   # - data_analysis(file_path: str) -> dict
   # Each with full parameter validation and documentation

Advanced Features
-----------------

**Cross-Channel Session Management:**

.. code-block:: python

   # Sessions persist across all channels
   app = Nexus()

   # Start workflow via API
   response = requests.post("/workflows/process_data", json={...})
   run_id = response.json()["run_id"]

   # Check status via CLI
   # nexus status {run_id}

   # AI agents can also access execution results
   # MCP tool: get_execution_result(run_id)

**Enterprise Authentication:**

.. code-block:: python

   # Multi-channel authentication
   app = Nexus(enable_auth=True)

   # JWT tokens work across all channels
   # API: Authorization: Bearer {token}
   # CLI: nexus login --token {token}
   # MCP: Authentication headers passed through

**Real-time Monitoring:**

.. code-block:: python

   # Unified monitoring across channels
   app = Nexus(enable_monitoring=True)

   # WebSocket endpoints for real-time updates
   # /ws/executions/{run_id}  - Real-time execution updates
   # /ws/metrics              - Live platform metrics
   # /ws/logs                 - Streaming logs

**Custom Channel Configuration:**

.. code-block:: python

   # Fine-tune each channel
   app = Nexus(
       api_port=8000,
       mcp_port=3001,
       enable_auth=True,
       enable_monitoring=True,
       rate_limit=1000  # requests per minute
   )

   # Configure specific channels
   app.api.cors_enabled = True
   app.api.docs_enabled = True
   app.mcp.discovery_enabled = True
   app.monitoring.metrics_interval = 30

Production Examples
-------------------

**1. Data Processing Platform:**

.. code-block:: python

   from nexus import Nexus
   import pandas as pd

   app = Nexus()

   @app.workflow
   def etl_pipeline(source_file: str, target_format: str = "csv") -> dict:
       """ETL pipeline for data transformation."""
       # Load data
       df = pd.read_csv(source_file)

       # Transform
       df["processed_at"] = pd.Timestamp.now()
       df = df.dropna()

       # Save
       output_file = f"processed_{source_file.split('/')[-1]}"
       if target_format == "csv":
           df.to_csv(output_file, index=False)
       elif target_format == "json":
           df.to_json(output_file, orient="records")

       return {
           "input_rows": len(df),
           "output_file": output_file,
           "format": target_format
       }

   app.start()

   # Usage:
   # API: POST /workflows/etl_pipeline {"source_file": "data.csv"}
   # CLI: nexus run etl_pipeline --source-file data.csv --target-format json
   # MCP: AI agents can call etl_pipeline tool with parameters

**2. AI Agent Orchestration:**

.. code-block:: python

   import os
   from nexus import Nexus
   from kailash.nodes.ai import LLMAgentNode

   app = Nexus()

   @app.workflow
   def ai_analysis(text: str, analysis_type: str = "sentiment") -> dict:
       """Multi-AI agent analysis pipeline."""
       model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")

       # Create specialized agents
       if analysis_type == "sentiment":
           agent = LLMAgentNode(
               model=model,
               system_prompt="Analyze sentiment of the provided text."
           )
       elif analysis_type == "summarize":
           agent = LLMAgentNode(
               model=model,
               system_prompt="Provide a concise summary of the text."
           )

       result = agent.execute(input_text=text)

       return {
           "analysis_type": analysis_type,
           "input_length": len(text),
           "result": result["response"],
           "confidence": result.get("confidence", 0.95)
       }

   app.start()

**3. Enterprise Workflow Hub:**

.. code-block:: python

   from nexus import Nexus
   from kailash.workflow.builder import WorkflowBuilder

   app = Nexus(
       enable_auth=True,
       enable_monitoring=True,
       rate_limit=500
   )

   # Register multiple enterprise workflows
   workflows = {
       "customer_onboarding": create_onboarding_workflow(),
       "fraud_detection": create_fraud_workflow(),
       "risk_assessment": create_risk_workflow(),
       "compliance_check": create_compliance_workflow()
   }

   for name, workflow in workflows.items():
       app.register(name, workflow)

   # Enterprise features
   app.enable_audit_logging()
   app.enable_rate_limiting()
   app.start()

Revolutionary Capabilities
--------------------------

**1. Durable-First Design:**

.. code-block:: python

   # Every request is resumable from checkpoints
   app = Nexus(enable_durability=True)

   # Long-running workflows automatically checkpoint
   @app.workflow
   def long_running_process(data: list) -> dict:
       results = []
       for i, item in enumerate(data):
           # Automatic checkpoint every 10 items
           if i % 10 == 0:
               app.checkpoint({"progress": i, "results": results})

           # Process item
           result = expensive_operation(item)
           results.append(result)

       return {"total_processed": len(results), "results": results}

**2. Cross-Channel State Sync:**

.. code-block:: python

   # Sessions persist across all interfaces
   session_id = app.create_session()

   # Start via API
   api_response = requests.post(f"/workflows/process_data?session={session_id}")

   # Monitor via CLI
   # nexus monitor --session {session_id}

   # AI agents can access same session
   # MCP tool: get_session_state(session_id)

**3. Event-Driven Communication:**

.. code-block:: python

   # Real-time events across all channels
   @app.event("workflow_completed")
   def on_completion(event):
       # Notify all connected clients
       app.broadcast({
           "type": "completion",
           "workflow": event["workflow_name"],
           "result": event["result"]
       })

   # WebSocket: Real-time updates in web UI
   # CLI: Live progress updates
   # MCP: AI agents receive completion events

Performance & Benchmarks
-------------------------

**Multi-Channel Performance:**
   - **API Requests**: 10,000+ concurrent requests
   - **CLI Commands**: Sub-second execution for simple workflows
   - **MCP Tools**: 100+ simultaneous AI agent connections
   - **Cross-Channel Sync**: <50ms session synchronization

**Resource Efficiency:**
   - **Memory**: Single process serves all channels
   - **CPU**: Shared execution engine across interfaces
   - **Network**: Optimized serialization for each protocol
   - **Storage**: Unified logging and state management

**Benchmarks:**

.. code-block:: python

   # Built-in performance monitoring
   print(app.get_performance_metrics())
   # {
   #   "workflow_registration_time": {"average": 0.045, "target_met": True},
   #   "cross_channel_sync_time": {"average": 0.032, "target_met": True},
   #   "session_sync_latency": {"average": 0.028, "target_met": True}
   # }

Enterprise Features
-------------------

**Multi-Tenant Architecture:**

.. code-block:: python

   # Complete tenant isolation
   app = Nexus(multi_tenant=True)

   # All channels respect tenant boundaries
   # API: X-Tenant-ID header
   # CLI: --tenant flag
   # MCP: Tenant context in tool calls

**Security & Compliance:**

.. code-block:: python

   # Enterprise security patterns
   app = Nexus()
   app.enable_auth()              # JWT authentication
   app.enable_rate_limiting()     # DDoS protection
   app.enable_audit_logging()     # Compliance trails
   app.enable_threat_detection()  # Behavior analysis

**Health Monitoring:**

.. code-block:: python

   # Comprehensive health checks
   health = app.health_check()
   # {
   #   "status": "healthy",
   #   "platform_type": "zero-config-workflow",
   #   "channels": {"api": "active", "cli": "active", "mcp": "active"},
   #   "workflows": 5,
   #   "enterprise_features": {...}
   # }

Deployment Patterns
-------------------

**Docker Deployment:**

.. code-block:: dockerfile

   FROM python:3.11-slim
   COPY requirements.txt .
   RUN pip install kailash-nexus
   COPY app.py .
   EXPOSE 8000 3001
   CMD ["python", "app.py"]

**Kubernetes:**

.. code-block:: yaml

   apiVersion: v1
   kind: Service
   metadata:
     name: nexus-service
   spec:
     selector:
       app: nexus
     ports:
     - name: api
       port: 8000
       targetPort: 8000
     - name: mcp
       port: 3001
       targetPort: 3001

**Environment Variables:**

.. code-block:: bash

   export NEXUS_API_PORT=8000
   export NEXUS_MCP_PORT=3001
   export NEXUS_ENABLE_AUTH=true
   export NEXUS_ENABLE_MONITORING=true
   export NEXUS_RATE_LIMIT=1000

Migration Guide
---------------

**From FastAPI:**

.. code-block:: python

   # Before: FastAPI
   from fastapi import FastAPI
   app = FastAPI()

   @app.post("/process")
   def process_data(data: list):
       return {"result": sum(data)}

   # After: Nexus (adds CLI + MCP automatically)
   from nexus import Nexus
   app = Nexus()

   @app.workflow
   def process_data(data: list) -> dict:
       return {"result": sum(data)}

**From Click CLI:**

.. code-block:: python

   # Before: Click CLI
   import click

   @click.command()
   @click.option('--data', multiple=True)
   def process(data):
       result = sum(int(x) for x in data)
       print(f"Result: {result}")

   # After: Nexus (adds API + MCP automatically)
   from nexus import Nexus
   app = Nexus()

   @app.workflow
   def process_data(data: list) -> dict:
       return {"result": sum(data)}

API Reference
-------------

See the complete :doc:`Nexus API Reference <../api/nexus>` for detailed documentation of all classes and methods.

Examples Repository
-------------------

Complete production examples in ``apps/kailash-nexus/examples/``:

- **Enterprise Workflow Hub**: Multi-tenant workflow platform
- **AI Agent Orchestrator**: Coordinate multiple AI agents
- **Data Processing Pipeline**: ETL workflows with monitoring
- **API Gateway**: High-performance request routing

Support & Community
-------------------

- **GitHub**: `github.com/terrene-foundation/kailash-py <https://github.com/terrene-foundation/kailash-py>`_
- **Issues**: Report Nexus-specific issues
- **Documentation**: Complete deployment guides
- **Examples**: Production-ready implementations
