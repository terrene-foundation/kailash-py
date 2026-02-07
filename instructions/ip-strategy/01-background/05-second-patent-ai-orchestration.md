> **HISTORICAL DOCUMENT**
>
> This background analysis was prepared as part of the IP strategy development process
> (February 2026). On 6 February 2026, the decision was made to adopt pure Apache 2.0
> licensing and donate all platform assets to OCEAN Foundation. See `DECISION-MEMORANDUM.md`
> and `07-foundation/` for the final strategy.

# 05 - Second Patent: AI Workflow Orchestration (P251088SG)

## Document Purpose

Summary of the second patent application covering AI workflow orchestration, filed to close the Kaizen framework coverage gap identified in the IP strategy analysis.

## Application Details

| Field                 | Value                                                                  |
| --------------------- | ---------------------------------------------------------------------- |
| Application Reference | P251088SG                                                              |
| Applicant             | Terrene Foundation                                                     |
| Title                 | "Method and System for Orchestrating Artificial Intelligence Workflow" |
| Filing Type           | Singapore Provisional Application                                      |
| Filing Date           | 7 October 2025                                                         |
| Priority Date         | 7 October 2025                                                         |
| Attorney              | Auriga IP Pte. Ltd. (presumed)                                         |
| Claims                | 11 (1 independent method + 10 dependent)                               |

## Deadlines

| Event                   | Date               | Status                             |
| ----------------------- | ------------------ | ---------------------------------- |
| Provisional filing      | 7 October 2025     | Filed                              |
| Complete SG application | **7 October 2026** | Pending (8 months from 3 Feb 2026) |
| PCT filing (if desired) | **7 October 2026** | Decision pending                   |

## Patent Architecture (From Drawings)

### FIG. 1 - Computing System (100)

Core system comprising:

- **Processor** (102) and **Memory** (104)
- **LLM-Guided Workflow Creation Module** (106)
- **Multi-Agent Orchestration Module** (108)
- **Iterative Workflow Engine** (110)
- **Convergence Detection Unit** (112)
- **Shared Memory for Agent Communication** (122)
- **Python Ecosystem Integration Layer** (114)
- **Containerization Module** (116)
- **Container Orchestration Engine** (120)
- **Structured Documentation Interface** (118) for context engineering input

### FIG. 2 - LLM-Guided Workflow Creation Module (106)

Pipeline:

1. Structured documentation or context engineering input (200)
2. Prompt Parsing Unit (202)
3. LLM Module (204) — transformer-based (GPT, BERT, CodeT5)
4. Generated Workflow Components (206)
5. Version Control & Testing Interface (208)
6. Output to Development Environment (210)

### FIG. 3 - Method Flowchart (300)

Nine-step method:

1. (302) Receive workflow creation input via structured documentation interface
2. (304) Generate workflow components using LLM with predefined modular nodes
3. (306) Instantiate plurality of software agents (communicating via shared memory)
4. (308) Execute iterative workflow cycle
5. (310) Detect convergence using convergence detection algorithm
6. (312) Terminate execution upon convergence
7. (314) Integrate Python-based libraries via ecosystem integration layer
8. (316) Generate containerized deployment package
9. (318) Deploy to production via container orchestration engine

### FIG. 4 - Agent-Oriented Orchestration Subsystem

Multi-agent architecture:

- Task A Agent (400), Task B Agent (402), Task C Agent (404)
- **Inter-agent Communication Links** (410)
- **Memory Bus** (408)
- **Role Assignment Logic** (412) for self-organizing team formation
- **Shared Memory** (122)

### FIG. 5 - Containerization and Deployment Pipeline

Workflow source components & modular nodes (500) → Containerization Tool/Docker (502) → Container Image (504) → Container Registry (506) → Kubernetes Deployment Platform (508)

### FIG. 6 - Smart Server (600)

Self-contained server comprising:

- Direct User Input/API (200) — no AI client needed
- **Embedded LLM Reasoning via LLMAgentNode** (602)
- **Multi-Agent Orchestration** (604)
- **Iterative Workflow Engine** (606)
- **Containerization + Deployment** (608)

## Claim Structure (11 claims)

### Independent Claim 1 (Method)

Computer-implemented method for orchestrating an AI workflow comprising:

1. Receiving workflow creation input comprising a structured documentation interface
2. Generating workflow components using an LLM, where the input comprises predefined modular nodes specifying structured context for discrete tasks
3. Instantiating a plurality of software agents (each performing a task defined by the workflow components), communicating via shared memory
4. Executing an iterative workflow cycle
5. Detecting convergence using a convergence detection algorithm
6. Terminating execution upon convergence
7. Integrating Python-based libraries via a Python ecosystem integration layer
8. Generating a containerized deployment package
9. Deploying to production via a container orchestration engine

### Dependent Claims (2-11)

| Claim | Depends On | Covers                                                                                                                                                 |
| ----- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 2     | 1          | LLM is a transformer-based neural network trained on software development corpora                                                                      |
| 3     | 1          | Convergence based on predefined iterations or threshold metric                                                                                         |
| 4     | 1          | Shared memory as in-memory data store or shared memory bus                                                                                             |
| 5     | 1          | Agents include data ingestion, analysis, or result synthesis agents                                                                                    |
| 6     | 1          | Python libraries include pandas, NumPy, or scikit-learn                                                                                                |
| 7     | 1          | Containerization using Docker-based runtime                                                                                                            |
| 8     | 1          | Container orchestration using Kubernetes                                                                                                               |
| 9     | 1          | Version control/testing integration with source repo and pytest                                                                                        |
| 10    | 1          | Structured documentation interface via script, CLI, or API (no GUI required)                                                                           |
| 11    | 1          | Modular nodes include AI nodes (structured context to reduce hallucinations) and non-AI nodes (enterprise requirements: security, logging, compliance) |

## Patent-to-Codebase Mapping

| Patent Element                      | Ref   | SDK Component                                     | Framework           |
| ----------------------------------- | ----- | ------------------------------------------------- | ------------------- |
| LLM-Guided Workflow Creation Module | 106   | `Agent` API + `BaseAgent` with LLM integration    | Kaizen              |
| Prompt Parsing Unit                 | 202   | Signature-based programming, prompt parsing       | Kaizen              |
| LLM Module                          | 204   | LLM integration (GPT-4, Claude, etc.)             | Kaizen              |
| Generated Workflow Components       | 206   | `WorkflowBuilder` + automatic node generation     | Core SDK + DataFlow |
| Multi-Agent Orchestration Module    | 108   | `AgentRegistry` + `OrchestrationRuntime`          | Kaizen              |
| Software Agents (400-404)           | FIG.4 | `BaseAgent` instances with role specialization    | Kaizen              |
| Shared Memory                       | 122   | Agent memory / session state / blackboard pattern | Kaizen              |
| Role Assignment Logic               | 412   | Supervisor-worker, router, ensemble patterns      | Kaizen              |
| Inter-agent Communication Links     | 410   | A2A protocol, agent-to-agent messaging            | Kaizen              |
| Iterative Workflow Engine           | 110   | `CycleExecutionMixin` + `CyclicWorkflowExecutor`  | Core SDK            |
| Convergence Detection Unit          | 112   | Convergence detection in cyclic workflows         | Core SDK            |
| Python Ecosystem Integration Layer  | 114   | `PythonCode` node (110+ nodes)                    | Core SDK            |
| Structured Documentation Interface  | 118   | Multi-channel deployment (CLI/API/MCP)            | Nexus               |
| Containerization Module             | 116   | Docker deployment integration                     | Nexus               |
| Container Orchestration Engine      | 120   | Kubernetes deployment                             | Nexus               |
| Smart Server                        | 600   | Self-contained Nexus deployment                   | Nexus               |
| Version Control & Testing Interface | 208   | pytest integration, CI pipeline                   | Core SDK            |
| Memory Bus                          | 408   | Connection/parameter passing between nodes        | Core SDK            |

## Relationship to First Patent (PCT/SG2024/050503)

The two patents are **complementary**:

| Aspect                   | Patent 1 (PCT/SG2024/050503)                      | Patent 2 (P251088SG)                               |
| ------------------------ | ------------------------------------------------- | -------------------------------------------------- |
| Focus                    | Platform architecture                             | AI orchestration layer                             |
| Core innovation          | Data fabric + composable layer                    | LLM-guided multi-agent workflows                   |
| Primary framework        | DataFlow + Core SDK                               | Kaizen + Core SDK                                  |
| Key figures              | FIG. 3 (two-layer architecture)                   | FIG. 4 (agent orchestration)                       |
| Distinguishing feature   | Source data extraction from heterogeneous formats | Deterministic contextual scaffolding for AI agents |
| Prior art differentiated | D1 (SCM platform), D2 (metadata orchestrator)     | n8n (visual-first, no AI-native support)           |

**Together**, they create complete IP coverage:

- Patent 1 covers the "what" — the platform that transforms data and orchestrates components
- Patent 2 covers the "how" — the AI-native agent system that runs on the platform

## Key Technical Differentiators Claimed

1. **Deterministic contextual scaffolding** — Structured context payloads constraining LLM output within technical boundaries (reduces hallucinations)
2. **Self-organizing multi-agent architecture** — Dynamic role assignment and team formation
3. **Convergence-aware iterative execution** — 30,000+ iterations/sec with automatic termination
4. **Python-native integration** — Direct library integration (pandas, NumPy, scikit-learn) without code translation
5. **Container-aligned development** — Seamless research-to-production via automated containerization
6. **Smart server architecture** — Self-contained execution without external AI clients
7. **Structured documentation/context engineering** — Methodology for guiding AI agents with machine-readable context

## Observations for Complete Application

When converting from provisional to complete application (by 7 October 2026):

1. **Add system claims**: Currently only method claims (1 independent). The complete application should mirror Patent 1's structure with both method and system independent claims.
2. **Strengthen Alice positioning**: The description already emphasizes technical specificity, but the claims could be tightened for US prosecution.
3. **Consider PCT filing**: Given the AI agent orchestration space is rapidly evolving, filing a PCT from this priority would extend international protection.
4. **Cross-reference Patent 1**: The complete application should reference PCT/SG2024/050503 to establish the relationship between the platform architecture and the AI orchestration layer.

## Source Documents

- P251088SG description and claims.pdf (7 October 2025)
- P251088SG drawings.pdf (6 figures)
