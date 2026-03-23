# Codebase Inventory — What Exists Today

## 1. Kaizen Agent Framework (`packages/kailash-kaizen/src/kaizen/`)

### 1.1 Agent System

| Component          | Location              | Current State                                    | L3 Relevance                               |
| ------------------ | --------------------- | ------------------------------------------------ | ------------------------------------------ |
| `AgentConfig`      | `agent_config.py`     | 30+ fields, no `envelope` field                  | **B1 blocker**: Must add optional envelope |
| `agent_types.py`   | `agent_types.py`      | Agent type definitions                           | Reference for AgentSpec design             |
| `agent.py`         | `agent.py`            | Main Agent class                                 | Foundation for AgentFactory wrapping       |
| Specialized agents | `agents/specialized/` | 12 agent types (react, cot, rag, planning, etc.) | Pattern reference for L3 spawning          |
| Autonomous agents  | `agents/autonomous/`  | Claude Code, Codex integrations                  | L3 autonomy builds on this subsystem       |
| Agent registry     | `agents/registry.py`  | Name-based agent registration                    | AgentInstanceRegistry is NEW, separate     |

### 1.2 Autonomy Subsystem (`core/autonomy/`)

| Component          | Location              | Current State                                   | L3 Relevance                           |
| ------------------ | --------------------- | ----------------------------------------------- | -------------------------------------- |
| Control protocol   | `control/protocol.py` | Pause/resume/terminate control                  | Foundation for L3 lifecycle management |
| Control transports | `control/transports/` | CLI, HTTP, memory, stdio                        | Extend for L3 agent control            |
| Hooks system       | `hooks/`              | Audit, cost tracking, logging, metrics, tracing | Direct reuse for L3 EATP audit hooks   |
| Permissions        | `permissions/`        | Permission management                           | Foundation for tool access control     |
| State management   | `state/`              | Agent state tracking                            | Foundation for AgentState enum         |
| Interrupts         | `interrupts/`         | Interrupt handling                              | Reference for L3 hold/escalation       |
| Observability      | `observability/`      | Metrics, tracing                                | Extend for L3 envelope monitoring      |

### 1.3 Composition & DAG (`composition/`)

| Component            | Location            | Current State                    | L3 Relevance                       |
| -------------------- | ------------------- | -------------------------------- | ---------------------------------- |
| DAG validator        | `dag_validator.py`  | Cycle detection, validation      | **Direct reuse** for PlanValidator |
| Cost estimator       | `cost_estimator.py` | Cost estimation for compositions | Foundation for budget summation    |
| Composition models   | `models.py`         | Composition data types           | Pattern reference for Plan types   |
| Schema compatibility | `schema_compat.py`  | Schema validation                | Input/output mapping validation    |
| Errors               | `errors.py`         | Composition errors               | Extend for PlanError               |

### 1.4 Coordination (`coordination/`)

| Component | Location      | Current State         | L3 Relevance                             |
| --------- | ------------- | --------------------- | ---------------------------------------- |
| Patterns  | `patterns.py` | Coordination patterns | Reference for L3 delegation patterns     |
| Teams     | `teams.py`    | Team coordination     | Foundation for multi-agent orchestration |

### 1.5 Memory System

| Component     | Location        | Current State                      | L3 Relevance                                          |
| ------------- | --------------- | ---------------------------------- | ----------------------------------------------------- |
| Memory module | `memory/`       | Session, shared, persistent memory | **Not replaced** by ScopedContext; different concerns |
| Buffer memory | In agent_config | Turn-based buffer                  | Agent's conversation memory (not task context)        |

### 1.6 Trust Integration (`core/autonomy/hooks/`)

| Component          | Location                        | Current State              | L3 Relevance                               |
| ------------------ | ------------------------------- | -------------------------- | ------------------------------------------ |
| Cost tracking hook | `builtin/cost_tracking_hook.py` | Per-action cost tracking   | Foundation for EnvelopeTracker integration |
| Audit hook         | `builtin/audit_hook.py`         | EATP audit record creation | Direct reuse for L3 EATP records           |

## 2. Trust-Plane (`src/kailash/trust/`)

### 2.1 Constraint Infrastructure

| Component       | Location                        | Current State               | L3 Relevance                                           |
| --------------- | ------------------------------- | --------------------------- | ------------------------------------------------------ |
| Budget tracker  | `constraints/budget_tracker.py` | Financial budget tracking   | **Foundation** for EnvelopeTracker financial dimension |
| Budget store    | `constraints/budget_store.py`   | Persistent budget storage   | Extend for L3 durable state                            |
| Spend tracker   | `constraints/spend_tracker.py`  | Spend recording and queries | Foundation for cost_history                            |
| Evaluator       | `constraints/evaluator.py`      | Per-dimension evaluation    | Reuse inside EnvelopeEnforcer                          |
| Dimension model | `constraints/dimension.py`      | Dimension type definitions  | Reuse for dimension-specific tracking                  |
| Commerce        | `constraints/commerce.py`       | Commerce constraints        | Reference                                              |

### 2.2 Enforcement

| Component       | Location                | Current State                                | L3 Relevance                             |
| --------------- | ----------------------- | -------------------------------------------- | ---------------------------------------- |
| StrictEnforcer  | `enforce/strict.py`     | Per-action checking against all 5 dimensions | **Direct reuse** inside EnvelopeEnforcer |
| Shadow enforcer | `enforce/shadow.py`     | Shadow mode enforcement                      | Reference for non-bypassable pattern     |
| Decorators      | `enforce/decorators.py` | Enforcement decorators                       | Extend for L3 middleware                 |

### 2.3 Trust Records

| Component   | Location         | Current State                    | L3 Relevance                   |
| ----------- | ---------------- | -------------------------------- | ------------------------------ |
| Chain store | `chain.py`       | Delegation chain management      | Reuse for parent-child lineage |
| Key manager | `key_manager.py` | Cryptographic key management     | Support for signed records     |
| Signing     | `signing/`       | Crypto, multi-sig, CRL, rotation | EATP record signing            |

## 3. PACT Governance (`packages/kailash-pact/src/pact/governance/`)

### 3.1 Core Governance

| Component          | Location        | Current State                  | L3 Relevance                                          |
| ------------------ | --------------- | ------------------------------ | ----------------------------------------------------- |
| GovernanceEngine   | `engine.py`     | Full governance engine         | Pattern reference for EnvelopeEnforcer                |
| GovernanceContext  | `context.py`    | Frozen immutable context       | **Direct reuse** — agents receive context, not engine |
| Addressing (D/T/R) | `addressing.py` | Address parsing and validation | **Direct reuse** for L3 positional addressing         |
| Clearance          | `clearance.py`  | Knowledge clearance levels     | **Direct reuse** for ScopedContext classification     |
| Knowledge          | `knowledge.py`  | Knowledge store and access     | Foundation for ScopedContext                          |

### 3.2 Envelope Infrastructure

| Component        | Location              | Current State                                               | L3 Relevance                                    |
| ---------------- | --------------------- | ----------------------------------------------------------- | ----------------------------------------------- |
| Envelopes        | `envelopes.py`        | Role/Task/Effective envelope model, `intersect_envelopes()` | **Direct reuse** — this IS the envelope algebra |
| Envelope adapter | `envelope_adapter.py` | EATP↔PACT envelope bridge                                   | Reuse for L3 envelope construction              |
| Config           | `config.py`           | ConstraintEnvelopeConfig with all 5 dimensions              | **Direct reuse** — L3 envelopes ARE this type   |

### 3.3 Gradient & Verdict

| Component         | Location        | Current State                                  | L3 Relevance                                            |
| ----------------- | --------------- | ---------------------------------------------- | ------------------------------------------------------- |
| GradientEngine    | `gradient.py`   | Gradient zone evaluation with EvaluationResult | **Direct reuse** for EnvelopeTracker zone determination |
| GovernanceVerdict | `verdict.py`    | Verdict with level, reason, audit details      | **Extend** for L3 Verdict type                          |
| Middleware        | `middleware.py` | PACT middleware patterns                       | Pattern for EnvelopeEnforcer middleware                 |

### 3.4 Agent Integration

| Component         | Location           | Current State                     | L3 Relevance                        |
| ----------------- | ------------------ | --------------------------------- | ----------------------------------- |
| PactGovernedAgent | `agent.py`         | Agent with governance enforcement | Foundation for L3 governed agents   |
| Agent mapping     | `agent_mapping.py` | Kaizen↔PACT agent bridge          | Extend for AgentInstance mapping    |
| Decorators        | `decorators.py`    | Governance decorators             | Reuse for L3 enforcement decorators |

### 3.5 Storage & Audit

| Component        | Location           | Current State                               | L3 Relevance                                 |
| ---------------- | ------------------ | ------------------------------------------- | -------------------------------------------- |
| Store interfaces | `store.py`         | Abstract governance stores                  | Extend for AgentInstanceRegistry persistence |
| SQLite stores    | `stores/sqlite.py` | SQLite-backed governance stores             | Reuse pattern for L3 stores                  |
| Audit            | `audit.py`         | Audit trail management                      | **Direct reuse** for L3 EATP records         |
| Compilation      | `compilation.py`   | Org tree compilation with depth/node limits | Reference for L3 depth enforcement           |

## 4. Key Observations

### What's Strong (Direct Reuse)

- **5-dimensional constraint envelope model** — fully implemented with intersection algebra
- **GradientEngine** — already evaluates AUTO_APPROVED / FLAGGED / HELD / BLOCKED
- **StrictEnforcer** — per-action checking against all dimensions
- **D/T/R addressing** — positional addressing with validation
- **Knowledge clearance** — 5 classification levels
- **Governance context** — frozen immutable context pattern
- **Audit trail** — EATP audit anchor creation
- **DAG validation** — cycle detection in composition module

### What's Partially There (Extend/Adapt)

- **BudgetTracker** — financial only, needs multi-dimension extension
- **AgentConfig** — needs optional envelope field (B1)
- **Agent state** — basic states exist, needs formal state machine with 6 states
- **Composition DAG** — validation exists, needs PlanNode/PlanEdge types
- **Cost tracking** — exists in hooks, needs continuous tracking (not just per-action)

### What's Missing (Build New)

- **EnvelopeTracker** — continuous multi-dimension budget tracking with reclamation
- **EnvelopeSplitter** — budget division with ratio-based allocation
- **EnvelopeEnforcer** — non-bypassable middleware combining tracker + enforcer + hold queue
- **ScopedContext** — hierarchical context with projection-based access control
- **MessageRouter** — envelope-aware routing with typed L3 payloads
- **MessageChannel** — bounded point-to-point channels with backpressure
- **DeadLetterStore** — bounded ring buffer for undeliverable messages
- **AgentFactory** — runtime agent instantiation with envelope validation
- **AgentInstanceRegistry** — lifecycle tracking separate from AgentRegistry
- **AgentSpec** — runtime instantiation blueprint
- **AgentInstance** — running agent entity with lifecycle state machine
- **Plan/PlanNode/PlanEdge** — DAG types
- **PlanValidator** — structural + envelope + resource validation
- **PlanExecutor** — gradient-driven DAG execution
- **PlanModification** — typed plan mutations

### Cross-SDK Notes (Python-specific)

- Python has a richer autonomy subsystem than Rust (state management, hooks, control protocol)
- Python uses `@dataclass` (not Pydantic) per EATP SDK conventions
- Python's `GovernanceVerdict.level` is string-based ("auto_approved") vs. the spec's enum-based `GradientZone`
- Python already has `intersect_envelopes()` and `MonotonicTighteningError`
- The existing composition module (`dag_validator.py`) provides a head start on PlanValidator
