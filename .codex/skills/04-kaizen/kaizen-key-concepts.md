# Kaizen Key Concepts

Conceptual reference for Kaizen's core architecture. Load when you need a deeper understanding of signatures, BaseAgent internals, the 6 autonomy subsystems, or AgentRegistry coordination before implementing.

## Signature-Based Programming

Signatures define type-safe interfaces for agents:

- **Input**: Define expected inputs with descriptions
- **Output**: Specify output format and structure
- **Validation**: Automatic type checking and validation
- **Optimization**: Framework can optimize prompts automatically

See [kaizen-signatures](kaizen-signatures.md) for authoring patterns.

## BaseAgent Architecture

Foundation for all Kaizen agents:

- **Error Handling**: Built-in retry logic and error recovery
- **Audit Trails**: Automatic logging of agent actions
- **Cost Tracking**: Monitor API usage and costs
- **Streaming**: Support for streaming responses
- **Memory**: State management across invocations
- **Hooks System**: Zero-code-change observability and lifecycle management

See [kaizen-baseagent-quick](kaizen-baseagent-quick.md) for initialization patterns.

## Autonomy Infrastructure (6 Subsystems)

### 1. Hooks System

Event-driven observability framework:

- Zero-code-change monitoring via lifecycle events (PRE/POST hooks)
- 6 builtin hooks: Logging, Metrics, Cost, Performance, Audit, Tracing
- Production security: RBAC, Ed25519 signatures, process isolation, rate limiting
- Performance: <0.01ms overhead (625x better than 10ms target)

See [kaizen-observability-hooks](kaizen-observability-hooks.md).

### 2. Checkpoint System

Persistent state management:

- Save/load/fork agent state for failure recovery
- 4 storage backends: Filesystem, Redis, PostgreSQL, S3
- Automatic compression and incremental checkpoints
- State manager with deduplication and versioning

See [kaizen-checkpoint-resume](kaizen-checkpoint-resume.md).

### 3. Interrupt Mechanism

Graceful shutdown and execution control:

- 3 interrupt sources: USER (Ctrl+C), SYSTEM (timeout/budget), PROGRAMMATIC (API)
- 2 shutdown modes: GRACEFUL (finish cycle + checkpoint) vs IMMEDIATE (stop now)
- Signal propagation across multi-agent hierarchies

See [kaizen-interrupt-mechanism](kaizen-interrupt-mechanism.md).

### 4. Memory System

3-tier hierarchical storage:

- Hot tier: In-memory buffer (<1ms retrieval, last 100 messages)
- Warm tier: Database (10-50ms, agent-specific history with JSONL compression)
- Cold tier: Object storage (100ms+, long-term archival with S3/MinIO)
- DataFlow-backed with auto-persist and cross-session continuity

See [kaizen-memory-system](kaizen-memory-system.md) and [kaizen-persistent-memory](kaizen-persistent-memory.md).

### 5. Planning Agents

Structured workflow orchestration:

- PlanningAgent: Plan before you act (pre-execution validation)
- PEVAgent: Plan, Execute, Verify, Refine (iterative refinement)
- Tree-of-Thoughts: Explore multiple reasoning paths
- Multi-step decomposition, validation, and replanning

### 6. Meta-Controller Routing

Intelligent task delegation:

- A2A-based semantic capability matching (no hardcoded if/else)
- Automatic agent discovery, ranking, and selection
- Fallback strategies and load balancing
- Integrated with Router, Ensemble, and Supervisor-Worker patterns

## AgentRegistry — Distributed Coordination

For 100+ agent distributed systems:

- O(1) capability-based discovery with semantic matching
- Event broadcasting (6 event types for cross-runtime coordination)
- Health monitoring with automatic deregistration
- Status management (ACTIVE, UNHEALTHY, DEGRADED, OFFLINE)
- Multi-runtime coordination across processes/machines

See [kaizen-agent-registry](kaizen-agent-registry.md).

## Pipeline Patterns (9 Composable Patterns)

- **Ensemble**: Multi-perspective collaboration with A2A discovery + synthesis
- **Blackboard**: Controller-driven iterative problem-solving
- **Router** (Meta-Controller): Intelligent task routing via A2A matching
- **Parallel**: Concurrent execution with aggregation
- **Sequential**: Linear agent chain
- **Supervisor-Worker**: Hierarchical coordination
- **Handoff**: Agent handoff with context transfer
- **Consensus**: Voting-based decision making
- **Debate**: Adversarial deliberation

**Use when:**

- **Ensemble**: Need diverse perspectives synthesized (code review, research)
- **Blackboard**: Iterative problem-solving (optimization, debugging)
- **Router**: Intelligent task delegation to specialists
- **Parallel**: Bulk processing or voting-based consensus
- **Sequential**: Linear workflows with dependency chains

See [kaizen-orchestration](kaizen-orchestration.md).
