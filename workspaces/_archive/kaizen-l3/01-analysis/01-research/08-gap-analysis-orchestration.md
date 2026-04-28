# Gap Analysis — Existing Orchestration vs L3 Requirements

## 1. Summary

The existing `kaizen/orchestration/` module provides L0-L2 multi-agent patterns. The L3 orchestration layer (kaizen-agents) requires LLM-dependent decision-making on top of L3 SDK primitives. This analysis maps what exists, what can be extended, and what must be built from scratch.

---

## 2. Existing Orchestration Inventory

### 2.1 OrchestrationRuntime (L0-L2)

- Agent lifecycle management (register/deregister, health monitoring)
- Task distribution with A2A semantic routing
- Resource management (concurrency limits, budget in USD)
- Error handling (retry policies, circuit breaker, failover)
- 4 strategies: Sequential, Parallel, Hierarchical, Pipeline

### 2.2 Multi-Agent Patterns (11)

| Pattern                   | L3 Mapping                                   | Reuse Potential                     |
| ------------------------- | -------------------------------------------- | ----------------------------------- |
| SupervisorWorkerPattern   | -> DelegationProtocol + AgentFactory         | High (refactor to use L3 types)     |
| ConsensusPattern          | -> Plan DAG with parallel vote nodes         | Medium (different execution model)  |
| DebatePattern             | -> Plan DAG with adversarial nodes           | Medium (different execution model)  |
| HandoffPattern            | -> Linear Plan DAG with CompletionDependency | High (direct mapping)               |
| SequentialPipelinePattern | -> Linear Plan DAG with DataDependency       | High (direct mapping)               |
| EnsemblePattern           | -> Fan-out Plan DAG                          | High (direct mapping)               |
| ParallelPattern           | -> Parallel Plan DAG nodes                   | High (direct mapping)               |
| BlackboardPattern         | -> ScopedContext shared writes               | Medium (different access model)     |
| MetaControllerPattern     | -> Capability routing                        | Low (replaced by CapabilityMatcher) |
| BaseMultiAgentPattern     | -> Not needed (Plan DAG is the base)         | None                                |
| HierarchicalPattern       | -> DelegationProtocol chain                  | High (direct mapping)               |

### 2.3 Specialized Agents (15)

These agents (ChainOfThought, ReAct, Planning, CodeGen, RAG, etc.) are **LLM execution strategies**, not orchestration components. They continue to work at L3 — an AgentSpec can reference any specialized agent type. No changes needed.

### 2.4 Execution Strategies

| Strategy              | L3 Relevance                                |
| --------------------- | ------------------------------------------- |
| SingleShotStrategy    | Used by simple plan nodes (one LLM call)    |
| MultiCycleStrategy    | Used by complex plan nodes (ReAct-style)    |
| StreamingStrategy     | Used for streaming plan node output         |
| ParallelBatchStrategy | Replaced by Plan DAG parallel execution     |
| FallbackStrategy      | Replaced by gradient-based failure handling |
| HumanInLoopStrategy   | Replaced by HELD gradient zone              |

### 2.5 Signature System

Kaizen's signature-based programming (`kaizen/signatures/`) provides:

- Declarative input/output contracts
- LLM call abstraction
- Type-safe structured output
- **This is the natural building block for orchestration components.**

---

## 3. Gap Matrix

### 3.1 Green — Direct Reuse (No Changes)

| Capability                | Existing Component    | Notes                                     |
| ------------------------- | --------------------- | ----------------------------------------- |
| LLM provider abstraction  | `kaizen/llm/`         | All providers (OpenAI, Anthropic, Ollama) |
| Signature-based LLM calls | `kaizen/signatures/`  | Declarative contracts                     |
| Tool execution framework  | `kaizen/tools/`       | Native + builtin tools                    |
| Agent base class          | `kaizen/core/base.py` | BaseAgent for specialized agents          |
| Memory system             | `kaizen/memory/`      | Session, shared, persistent               |
| Cost tracking             | `kaizen/cost/`        | BudgetTracker (financial)                 |
| MCP integration           | `kaizen/mcp/`         | Agent-as-client, agent-as-server          |

### 3.2 Yellow — Extend/Adapt

| Capability                     | Existing                           | Gap                                               | Effort |
| ------------------------------ | ---------------------------------- | ------------------------------------------------- | ------ |
| Supervisor-worker coordination | SupervisorWorkerPattern            | Refactor to use DelegationProtocol + AgentFactory | Medium |
| Pipeline execution             | SequentialPipelinePattern          | Map to linear Plan DAG                            | Small  |
| Agent discovery                | AgentRegistry (name-based)         | Add semantic capability matching                  | Medium |
| State checkpointing            | StateManager with SharedMemoryPool | Extend to checkpoint Plan DAG state               | Medium |
| OrchestrationRuntime           | Runtime with 4 strategies          | Add Plan DAG strategy / PlanExecutor integration  | Medium |

### 3.3 Red — Build New

| Component                  | Complexity | Priority | Description                                     |
| -------------------------- | ---------- | -------- | ----------------------------------------------- |
| **TaskDecomposer**         | Medium     | P0       | LLM objective decomposition into subtasks       |
| **PlanComposer**           | High       | P0       | Wire subtasks into Plan DAG with proper edges   |
| **AgentDesigner**          | Medium     | P0       | Map subtask to AgentSpec (tools, envelope)      |
| **EnvelopeAllocator**      | Medium     | P0       | Distribute budget across children               |
| **PlanEvaluator**          | Medium     | P1       | Semantic plan quality assessment                |
| **FailureDiagnoser**       | Medium     | P1       | Error analysis and root cause                   |
| **Recomposer**             | High       | P1       | Generate recovery PlanModification              |
| **DelegationProtocol**     | Medium     | P0       | Compose and track delegation lifecycle          |
| **ClarificationProtocol**  | Medium     | P1       | Handle bidirectional clarification              |
| **EscalationProtocol**     | Medium     | P1       | Receive escalations, direct recovery            |
| **CompletionProtocol**     | Medium     | P0       | Validate results, merge context                 |
| **ClassificationAssigner** | Low        | P2       | LLM data classification                         |
| **CapabilityMatcher**      | Medium     | P1       | Semantic agent-task matching                    |
| **ResultAggregator**       | Low        | P1       | Synthesize multi-node outputs                   |
| **L3RuntimeBridge**        | High       | P0       | Wire PlanExecutor events to orchestration layer |

---

## 4. Integration Architecture

### 4.1 The Bridge Problem

The highest-risk component is the **L3RuntimeBridge** — the glue between PlanExecutor (SDK, deterministic) and the orchestration layer (LLM-dependent). Specifically:

1. PlanExecutor calls a `node_callback` for each Ready node
2. The callback must: spawn agent (Factory), create context scope (ScopedContext), send delegation message (MessageRouter), run the agent (LLM), receive completion, update plan state
3. PlanExecutor emits events (NodeHeld, EnvelopeWarning) that the orchestration layer must handle within timeout

This bridge is where all 5 SDK primitives converge with the orchestration layer. It must be rock-solid.

### 4.2 Coexistence Strategy

L0-L2 patterns should NOT be deprecated. They serve simpler use cases:

- **L0-L2**: Direct agent orchestration without PACT governance (quick prototypes, simple coordination)
- **L3**: PACT-governed autonomous agent systems with budgets, classification, and audit trail

The migration path: patterns that use SupervisorWorkerPattern can opt-in to L3 by providing an envelope. No breaking changes.

---

## 5. Effort Estimate

Using the autonomous execution model (rules/autonomous-execution.md):

| Phase             | Components                                                                                                                  | Autonomous Sessions         |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------- | --------------------------- |
| P0 Core           | TaskDecomposer, PlanComposer, AgentDesigner, EnvelopeAllocator, DelegationProtocol, CompletionProtocol, L3RuntimeBridge     | 2-3 sessions                |
| P1 Recovery       | FailureDiagnoser, Recomposer, PlanEvaluator, ClarificationProtocol, EscalationProtocol, CapabilityMatcher, ResultAggregator | 2 sessions                  |
| P2 Classification | ClassificationAssigner, existing pattern L3 adapters                                                                        | 1 session                   |
| Testing           | Signature-level tests, integration with SDK conformance suite                                                               | 1 session                   |
| **Total**         |                                                                                                                             | **6-7 autonomous sessions** |
