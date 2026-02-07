> **HISTORICAL DOCUMENT**
>
> This background analysis was prepared as part of the IP strategy development process
> (February 2026). On 6 February 2026, the decision was made to adopt pure Apache 2.0
> licensing and donate all platform assets to OCEAN Foundation. See `DECISION-MEMORANDUM.md`
> and `07-foundation/` for the final strategy.

# 03 - Codebase Architecture Mapping

## Document Purpose

Detailed mapping between the patented architecture (PCT/SG2024/050503) and the Kailash SDK implementation.

## Overview

The Kailash Python SDK is the **reference implementation** of the architecture described in the patent application. Every major architectural element in the patent has a direct counterpart in the codebase.

## Detailed Mapping

### Data Fabric Layer (Patent Ref: 310) = DataFlow Framework

| Patent Element          | Patent Ref | Kailash Implementation                       | Key Files/Modules                                   |
| ----------------------- | ---------- | -------------------------------------------- | --------------------------------------------------- |
| Data Fabric Layer       | 310        | `kailash-dataflow` package                   | `apps/kailash-dataflow/`                            |
| Source Data Layer       | 314        | Multi-database connectors                    | PostgreSQL, MySQL, SQLite, MongoDB drivers          |
| Unified Data Layer      | 312        | `@db.model` decorator + auto-generated nodes | 11 nodes per SQL model, 8 per MongoDB, 3 for vector |
| Metadata Transformation | FIG. 6     | Model-to-node generation pipeline            | Schema introspection + node factory                 |

**How the patent claim maps to code:**

The patent's core claim - _"transform source metadata to solution metadata into a unified data format"_ - is implemented by DataFlow's automatic node generation:

1. **Source metadata** = Raw database schemas across PostgreSQL, MySQL, SQLite, MongoDB (heterogeneous formats)
2. **Transformation** = The `@db.model` decorator introspects the model and generates standardized operation nodes
3. **Solution metadata** = The 11 unified nodes (CREATE, READ, UPDATE, DELETE, LIST, UPSERT, COUNT, BULK_CREATE, BULK_UPDATE, BULK_DELETE, BULK_UPSERT) that present a consistent interface regardless of underlying database
4. **Unified data format** = All nodes follow the same parameter contract (flat params for Create, filter+fields for Update, etc.)

### Composable Layer (Patent Ref: 320) = Core SDK + Nexus

| Patent Element               | Patent Ref | Kailash Implementation     | Key Files/Modules                                    |
| ---------------------------- | ---------- | -------------------------- | ---------------------------------------------------- |
| Composable Layer             | 320        | Core SDK `WorkflowBuilder` | `kailash/workflow/builder.py`                        |
| Configurable Component Layer | 322        | 110+ nodes                 | `kailash/nodes/`                                     |
| Output Interface             | 324        | Nexus multi-channel        | `apps/kailash-nexus/` (API/CLI/MCP)                  |
| Process Orchestrator         | 326        | Runtime engines            | `kailash/runtime/` (LocalRuntime, AsyncLocalRuntime) |

**How the composable layer maps to code:**

```python
# Patent Step 403: "Invoking a composable layer comprising a plurality of
# configurable components configured to develop the service application"

from kailash.workflow.builder import WorkflowBuilder  # Composable Layer (320)

workflow = WorkflowBuilder()

# Configurable Component Layer (322) - 110+ node types
workflow.add_node("CreateUser", "create", {"name": "test"})
workflow.add_node("ReadUser", "read", {"filter": {"id": 1}})
workflow.add_node("SwitchNode", "route", {"condition": "..."})

# Connections = "mapping solution metadata to configurable components"
workflow.add_connection("create", "read", {"id": "user_id"})
```

### Process Orchestrator (Patent Ref: 326) = Runtime Engine

| Patent Element       | Patent Ref | Kailash Implementation              | Key Capabilities                                            |
| -------------------- | ---------- | ----------------------------------- | ----------------------------------------------------------- |
| Process Orchestrator | 326        | `LocalRuntime`                      | Sync execution, cycle support, conditional branching        |
| Process Orchestrator | 326        | `AsyncLocalRuntime`                 | Async execution, level-based parallelism, semaphore control |
| Workflow Execution   | FIG. 9     | `runtime.execute(workflow.build())` | Node-by-node execution with parameter passing               |

**Runtime architecture supporting the patent claims:**

```python
# Patent Step 404: "Developing the service application on an output interface
# by the one or more of the plurality of configurable components interacting
# through a process orchestrator for executing the operation request"

from kailash.runtime import LocalRuntime  # Process Orchestrator (326)

runtime = LocalRuntime(
    enable_cycles=True,                    # Supports FIG. 9 cyclic flows
    conditional_execution="skip_branches", # Supports Switch nodes
    connection_validation="strict"         # Validates component interactions
)

# "interacting through a process orchestrator for executing the operation request"
results, run_id = runtime.execute(workflow.build())
```

### Output Interface (Patent Ref: 324) = Nexus Multi-Channel

| Patent Element       | Patent Ref       | Kailash Implementation | Channels                         |
| -------------------- | ---------------- | ---------------------- | -------------------------------- |
| Output Interface     | 324              | Nexus platform         | API (REST), CLI, MCP (AI agents) |
| Multi-company access | FIG. 1 (101-103) | Multi-tenant sessions  | Unified session management       |

```python
# Patent: "Developing the service application on an output interface"

from nexus import Nexus  # Output Interface (324)

app = Nexus()
app.register(my_workflow)  # Deploy workflow across all channels
app.start()                # API + CLI + MCP simultaneously
```

### Method Claims Mapping (FIG. 10 = 400)

| Patent Step                                  | Ref | Kailash Code Pattern                                                    |
| -------------------------------------------- | --- | ----------------------------------------------------------------------- |
| Receive operation request                    | 401 | `runtime.execute(workflow.build(), inputs={...})` or Nexus API endpoint |
| Invoke data fabric layer                     | 402 | DataFlow `@db.model` generating nodes + schema transformation           |
| Invoke composable layer                      | 403 | `WorkflowBuilder.add_node()` with parameter mapping via connections     |
| Develop on output interface via orchestrator | 404 | `runtime.execute()` producing results, served via Nexus channels        |

## Industry-Specific Implementations (FIG. 5 Evidence)

The patent drawings (FIG. 5) show specific application deployments that correspond to Kailash's industry workflow capabilities:

| FIG. 5 Application | Tags                        | Kailash Implementation          |
| ------------------ | --------------------------- | ------------------------------- |
| MiltBank-HMO       | Healthcare                  | Healthcare workflow patterns    |
| ADAS               | Solo, Geotab, Teltonika, G7 | Telematics API integrations     |
| eCommerce          | Lazada, Shopee, Amazon      | E-commerce API nodes            |
| Platforms          | Axway, Boomi                | Integration platform connectors |
| TMS                | Versafleet, HopOn           | Transport management workflows  |
| WMS                | SAP, Oracle, Infor          | Warehouse management workflows  |
| EV                 | HGV, LGV, VHGV              | Fleet management workflows      |

## Kaizen Framework — Covered by Second Patent (P251088SG)

The Kaizen AI agent framework is now covered by a separate patent application filed on 7 October 2025. The second patent (P251088SG), titled _"Method and System for Orchestrating Artificial Intelligence Workflow"_, maps to the Kaizen framework as follows:

| Patent Element                      | Ref   | Kailash Implementation                            | Key Files/Modules                         |
| ----------------------------------- | ----- | ------------------------------------------------- | ----------------------------------------- |
| LLM-Guided Workflow Creation Module | 106   | `Agent` API + `BaseAgent` with LLM integration    | `apps/kailash-kaizen/kaizen/api/`         |
| Prompt Parsing Unit                 | 202   | Signature-based programming, prompt parsing       | `kaizen/core/signatures/`                 |
| LLM Module                          | 204   | LLM integration (GPT-4, Claude, etc.)             | `kaizen/core/llm/`                        |
| Multi-Agent Orchestration Module    | 108   | `AgentRegistry` + `OrchestrationRuntime`          | `kaizen/core/registry/`                   |
| Software Agents (400-404)           | FIG.4 | `BaseAgent` instances with role specialization    | `kaizen/core/base_agent.py`               |
| Shared Memory                       | 122   | Agent memory / session state / blackboard pattern | `kaizen/core/memory/`                     |
| Role Assignment Logic               | 412   | Supervisor-worker, router, ensemble patterns      | `kaizen/patterns/`                        |
| Inter-agent Communication Links     | 410   | A2A protocol, agent-to-agent messaging            | `kaizen/core/communication/`              |
| Iterative Workflow Engine           | 110   | `CycleExecutionMixin` + `CyclicWorkflowExecutor`  | `kailash/runtime/` (shared with Patent 1) |
| Convergence Detection Unit          | 112   | Convergence detection in cyclic workflows         | `kailash/runtime/` (shared with Patent 1) |
| Python Ecosystem Integration Layer  | 114   | `PythonCode` node (110+ nodes)                    | `kailash/nodes/` (shared with Patent 1)   |
| Structured Documentation Interface  | 118   | Multi-channel deployment (CLI/API/MCP)            | Nexus (shared with Patent 1)              |
| Containerization Module             | 116   | Docker deployment integration                     | Nexus deployment                          |
| Container Orchestration Engine      | 120   | Kubernetes deployment                             | Nexus deployment                          |
| Smart Server                        | 600   | Self-contained Nexus deployment                   | Nexus platform                            |

### Patent Portfolio Coverage Summary

| Framework | Patent 1 (PCT/SG2024/050503)   | Patent 2 (P251088SG)                    |
| --------- | ------------------------------ | --------------------------------------- |
| DataFlow  | **Primary** (Data Fabric)      | —                                       |
| Core SDK  | **Primary** (Composable)       | Shared (Iterative Engine, Convergence)  |
| Nexus     | **Primary** (Output Interface) | Shared (Containerization, Smart Server) |
| Kaizen    | —                              | **Primary** (AI Orchestration)          |

Together, the two patents provide comprehensive IP coverage across all four Kailash frameworks.

## Conclusion

The mapping between patents and codebase is comprehensive and direct. The Kailash SDK is not merely "inspired by" the patents — it IS the implementation of the patented architectures. With two patent applications now filed:

1. **Patent 1** (PCT/SG2024/050503) directly protects the platform architecture (DataFlow + Core SDK + Nexus)
2. **Patent 2** (P251088SG) directly protects the AI orchestration layer (Kaizen + Core SDK + Nexus)
3. Any competitor replicating the SDK's approach would likely infringe one or both patents
4. The SDK serves as evidence of reduction to practice for both patent families
5. The SDK's adoption metrics can demonstrate commercial value of the patent portfolio
6. The interlocking coverage eliminates the Kaizen gap identified in the original IP strategy analysis
