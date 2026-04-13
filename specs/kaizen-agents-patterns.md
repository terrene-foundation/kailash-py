# Kailash Kaizen Agents Specification — Patterns

Version: 0.9.2

Parent domain: Kailash `kaizen-agents` package (Layer 2 — ENGINES). This file covers specialized agents (ReAct/CoT/ToT/Vision/Audio/etc.), multi-agent coordination patterns (Debate, Supervisor-Worker, Consensus, Ensemble, etc.), pipeline infrastructure, autonomous agent implementations, research patterns, agent registry, and workflow templates. See also `kaizen-agents-core.md` and `kaizen-agents-governance.md`.

---

## 6. Specialized Agent Patterns

All specialized agents extend `BaseAgent` from Layer 1 and use Signature-based I/O. All follow zero-config progressive disclosure (constructor defaults, env var overrides, explicit params).

### 6.1 ReActAgent

**Pattern**: Reason + Act + Observe (iterative)

**When to use**: Tasks requiring multi-step reasoning with tool use. The agent reasons about what to do, takes an action (tool call or finish), observes the result, and decides next steps.

**Strategy**: `MultiCycleStrategy` (not single-shot). Iterates Reason -> Act -> Observe cycles until convergence.

**Signature fields**:

- Input: `task`, `context`, `available_tools`, `previous_actions`
- Output: `thought`, `action` (tool_use/finish/clarify), `action_input`, `confidence`, `need_tool`, `tool_calls`

**Convergence detection** (priority order):

1. **Objective** (preferred): `tool_calls` field present and empty -> converged. Non-empty -> continue.
2. **Subjective** (fallback): `action == "finish"` -> converged. `confidence >= threshold` -> converged.
3. **Default**: converged (safe fallback to prevent infinite loops).

**Configuration**:
| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_cycles` | 10 | Maximum reasoning cycles |
| `confidence_threshold` | 0.7 | Minimum confidence to finish |
| `mcp_discovery_enabled` | True | Enable MCP tool discovery |
| `enable_parallel_tools` | False | Parallel tool execution |
| `timeout` | 30 | Request timeout seconds |
| `max_retries` | 3 | Retry count on failure |

**Edge cases**: Empty task returns `INVALID_INPUT` error immediately without LLM call.

### 6.2 ChainOfThoughtAgent

**Pattern**: Linear step-by-step reasoning

**When to use**: Problems requiring transparent decomposition with explicit reasoning chains. Math, logic, analysis tasks where showing work matters.

**Strategy**: `AsyncSingleShotStrategy` (default). Single LLM call with structured output.

**Signature fields**:

- Input: `problem`, `context`
- Output: `step1` through `step5`, `final_answer`, `confidence`

**Post-processing**:

- If LLM returns plain text instead of structured JSON, `_extract_from_text_response()` parses step markers and final answer.
- If `confidence < confidence_threshold`, a `warning` field is added.
- If `enable_verification` is True (default), a `verified` boolean is added.

**Configuration**:
| Parameter | Default | Description |
|-----------|---------|-------------|
| `reasoning_steps` | 5 | Number of reasoning steps |
| `confidence_threshold` | 0.7 | Minimum acceptable confidence |
| `enable_verification` | True | Add verification flag |
| `temperature` | 0.1 | Low temperature for precision |

### 6.3 ToTAgent (Tree-of-Thoughts)

**Pattern**: Parallel multi-path exploration

**When to use**: Strategic decisions, creative problems, situations where multiple reasoning approaches should be compared. Differs from CoT (single path) and ReAct (single iterative path).

**Execution phases**:

1. **Generate**: Create N reasoning paths (parallel or sequential)
2. **Evaluate**: Score each path independently (completeness, errors, structure, quality)
3. **Select**: Choose best path by highest score
4. **Execute**: Return result from best path

**Configuration**:
| Parameter | Default | Description |
|-----------|---------|-------------|
| `num_paths` | 5 | Number of reasoning paths to generate |
| `max_paths` | 20 | Safety limit (raises ValueError if num_paths > max_paths) |
| `evaluation_criteria` | "quality" | Options: quality, speed, creativity |
| `parallel_execution` | True | Parallel path generation with semaphore (max 5 concurrent) |
| `temperature` | 0.9 | High temperature for diversity |

**Fallback**: If parallel execution fails, falls back to sequential generation.

### 6.4 Vision Agent

Located at `agents/multi_modal/vision_agent.py`. Handles image understanding tasks using multimodal LLM capabilities.

### 6.5 Audio / Transcription Agent

Located at `agents/multi_modal/transcription_agent.py`. Handles audio transcription and understanding.

### 6.6 Other Specialized Agents

| Agent                  | Module                                   | Purpose                                           |
| ---------------------- | ---------------------------------------- | ------------------------------------------------- |
| `RAGResearchAgent`     | `agents/specialized/rag_research.py`     | Retrieval-augmented generation for research tasks |
| `PlanningAgent`        | `agents/specialized/planning.py`         | Task decomposition and planning                   |
| `MemoryAgent`          | `agents/specialized/memory_agent.py`     | Long-term memory management                       |
| `SelfReflectionAgent`  | `agents/specialized/self_reflection.py`  | Self-evaluation and improvement                   |
| `ResilientAgent`       | `agents/specialized/resilient.py`        | Error recovery and retry logic                    |
| `HumanApprovalAgent`   | `agents/specialized/human_approval.py`   | Human-in-the-loop approval gates                  |
| `CodeGenerationAgent`  | `agents/specialized/code_generation.py`  | Code generation with validation                   |
| `SimpleQAAgent`        | `agents/specialized/simple_qa.py`        | Direct question-answering                         |
| `StreamingChatAgent`   | `agents/specialized/streaming_chat.py`   | Streaming conversational interface                |
| `BatchProcessingAgent` | `agents/specialized/batch_processing.py` | Batch task processing                             |
| `PEVAgent`             | `agents/specialized/pev.py`              | Plan-Execute-Verify pattern                       |

---

## 7. Multi-Agent Coordination Patterns

All multi-agent patterns extend `BaseMultiAgentPattern`, which provides:

- `shared_memory: SharedMemoryPool` for agent coordination
- `get_agents()`, `get_agent_ids()`, `get_agent_names()` for introspection
- `clear_shared_memory()`, `get_shared_insights()`, `count_insights_by_tags()` for state management
- `validate_pattern()` for initialization validation (shared memory exists, agents initialized, unique IDs)

**Deprecation notice (v0.9.0)**: All specialized agent subclasses within patterns (ProponentAgent, OpponentAgent, JudgeAgent, SupervisorAgent, WorkerAgent, CoordinatorAgent, ProposerAgent, VoterAgent, AggregatorAgent) are deprecated. In v1.0, patterns will accept plain `BaseAgent` instances with role defined via `config.system_prompt`, not specialized subclasses.

### 7.1 DebatePattern

**Pattern**: Adversarial reasoning through structured debate

**Architecture**:

```
User Topic -> ProponentAgent (argues FOR)
           -> OpponentAgent (argues AGAINST)
           -> SharedMemoryPool (stores arguments)
           -> ProponentAgent (rebuts opponent)
           -> OpponentAgent (rebuts proponent)
           -> (Repeat for N rounds)
           -> JudgeAgent (evaluates & decides)
           -> Final Judgment
```

**Components**:

- `ProponentAgent`: Argues FOR a position using `ArgumentConstructionSignature`
- `OpponentAgent`: Argues AGAINST using `ArgumentConstructionSignature`
- `JudgeAgent`: Evaluates using `JudgmentSignature`. Reads all arguments from shared memory by debate_id, evaluates, and writes judgment.

**Coordination mechanism**: `SharedMemoryPool` with tagged insights. Arguments written with tags `["argument", "for"|"against", debate_id]`. Rebuttals add `"rebuttal"` tag. Judgments written with tags `["judgment", debate_id]`.

**Communication protocol**: Agents do not communicate directly. All communication flows through shared memory with structured JSON payloads.

**API**:

```python
pattern = create_debate_pattern(model="gpt-4", temperature=0.7)
result = pattern.debate("Should AI be regulated?", rounds=2)
judgment = pattern.get_judgment(result["debate_id"])
```

**Termination conditions**: Debate runs for exactly `rounds` iterations, then the judge evaluates. The judge's decision is one of `"for"`, `"against"`, or `"tie"`.

**Edge cases**: `rounds <= 0` returns immediately with no judgment. Confidence and strength values are clamped to `[0.0, 1.0]`. Invalid decision values default to `"tie"`.

### 7.2 SupervisorWorkerPattern

**Pattern**: Centralized task delegation with hierarchical coordination

**Architecture**:

```
User Request -> SupervisorAgent (decomposes into tasks)
             -> SharedMemoryPool (writes tasks with worker assignment)
             -> WorkerAgents (read tasks, execute, write results)
             -> SupervisorAgent (aggregates results)
             -> Final Result
```

**Components**:

- `SupervisorAgent`: Decomposes requests into tasks, delegates to workers (round-robin or A2A capability matching), aggregates results, handles failures and reassignments.
- `WorkerAgent`: Reads assigned tasks from shared memory, executes via `BaseAgent.run()`, writes results back.
- `CoordinatorAgent`: Monitor-only role. Reads all insights, does not write. Reports active workers, pending/completed task counts.

**Worker selection**:

1. **A2A capability matching** (preferred): When A2A is available, generates capability cards for all workers, uses LLM-first ranking via `rank_agents_by_capability_sync()`, selects best match.
2. **Round-robin** (fallback): Simple index-based assignment.

**Security: Delegation depth limiting**: `max_total_delegations` (default: 20) prevents runaway recursive delegation. Raises `DelegationCapExceeded` when exceeded.

**Shared memory tags**: Tasks: `["task", "pending", request_id, worker_id]`. Results: `["result", "completed", request_id]`. Errors: `["error", "failed", request_id]`.

**API**:

```python
pattern = create_supervisor_worker_pattern(num_workers=5, model="gpt-4")
tasks = pattern.delegate("Process 100 documents")
results = pattern.aggregate_results(tasks[0]["request_id"])
progress = pattern.monitor_progress()
```

**Edge cases**: `num_tasks=0` returns empty list. If LLM returns non-parseable tasks JSON, default tasks are created. Tasks are normalized (strings converted to dicts, list padded or truncated to `num_tasks`).

### 7.3 ConsensusPattern

**Pattern**: Democratic voting with multiple perspectives

**Architecture**:

```
User Request -> ProposerAgent (creates proposal)
             -> SharedMemoryPool (writes proposal)
             -> VoterAgents (read proposal, cast votes)
             -> SharedMemoryPool (write votes)
             -> AggregatorAgent (tallies votes, determines consensus)
             -> Final Decision
```

**Components**:

- `ProposerAgent`: Creates proposals with rationale using `ProposalCreationSignature`.
- `VoterAgent`: Evaluates proposals from a configurable perspective (e.g., "technical", "business", "security"). Votes: `approve`, `reject`, `abstain`.
- `AggregatorAgent`: Tallies votes using `ConsensusAggregationSignature`. Consensus = simple majority (>50% approvals).

**Voter perspectives**: Configured via `voter_perspectives` parameter (e.g., `["technical", "business", "security", "legal", "ops"]`). Each voter evaluates from their assigned perspective.

**API**:

```python
pattern = create_consensus_pattern(
    num_voters=5,
    voter_perspectives=["technical", "business", "security", "legal", "ops"],
)
proposal = pattern.create_proposal("Should we adopt AI?", "Important decision")
for voter in pattern.voters:
    voter.vote(proposal)
result = pattern.determine_consensus(proposal["proposal_id"])
```

**Termination conditions**: Consensus is reached when `approvals > total_votes / 2`. The `consensus_reached` field is `"yes"` or `"no"`.

### 7.4 EnsemblePipeline

**Pattern**: Multi-perspective agent collaboration with A2A discovery

**Architecture**:

```
User Request -> Ensemble -> A2A Discovery (top-k) -> Multiple Agents -> Synthesizer -> Result
```

**Discovery modes**:

- `"a2a"` (default): Uses A2A capability matching to select top-k agents with best capability matches for the given task. Falls back to first top-k agents if A2A unavailable.
- `"all"`: Uses all agents.

**Error handling modes**:

- `"graceful"` (default): Collects partial results, records errors, continues.
- `"fail-fast"`: Raises exception on first error.

**Configuration**:
| Parameter | Default | Description |
|-----------|---------|-------------|
| `top_k` | 3 | Number of agents to select |
| `discovery_mode` | "a2a" | Agent selection strategy |
| `error_handling` | "graceful" | Error handling mode |

**API**:

```python
pipeline = Pipeline.ensemble(
    agents=[code_agent, data_agent, writing_agent, research_agent],
    synthesizer=synthesis_agent,
    discovery_mode="a2a",
    top_k=3,
)
result = pipeline.run(task="Multi-perspective analysis", input="data")
```

### 7.5 Other Multi-Agent Patterns

| Pattern                     | Module                                 | Description                                   |
| --------------------------- | -------------------------------------- | --------------------------------------------- |
| `HandoffPattern`            | `patterns/patterns/handoff.py`         | Agent-to-agent handoff with context transfer  |
| `SequentialPipelinePattern` | `patterns/patterns/sequential.py`      | Ordered agent execution chain                 |
| `ParallelPattern`           | `patterns/patterns/parallel.py`        | Concurrent agent execution with aggregation   |
| `BlackboardPattern`         | `patterns/patterns/blackboard.py`      | Shared knowledge space with specialist agents |
| `MetaControllerPattern`     | `patterns/patterns/meta_controller.py` | Meta-level coordination controller            |

---

## 8. Pipeline Infrastructure

### 8.1 Pipeline Base Class

```python
class Pipeline(ABC):
    @abstractmethod
    def run(self, **inputs) -> Dict[str, Any]: ...

    def to_agent(self, name=None, description=None) -> BaseAgent: ...
```

Pipelines are composable: any pipeline can be converted to a `BaseAgent` via `.to_agent()` for nesting within larger orchestrations.

### 8.2 Factory Methods

```python
Pipeline.sequential(agents)          # Linear execution
Pipeline.parallel(agents, ...)       # Concurrent execution
Pipeline.router(agents, ...)         # A2A semantic routing
Pipeline.ensemble(agents, ...)       # Multi-perspective with synthesis
Pipeline.supervisor_worker(...)      # Hierarchical delegation
```

---

## 18. Autonomous Agent Implementations

### 18.1 Base Autonomous Agent

`agents/autonomous/base.py` provides the base class for autonomous agents that operate without human intervention.

### 18.2 Claude Code Agent

`agents/autonomous/claude_code.py` wraps Claude Code as an autonomous agent.

### 18.3 Codex Agent

`agents/autonomous/codex.py` wraps OpenAI Codex as an autonomous agent.

---

## 21. Research Patterns

`research_patterns/` contains experimental and advanced patterns not yet promoted to production:

- `advanced_patterns.py` — Advanced multi-agent patterns
- `experimental.py` — Experimental agent architectures
- `intelligent_optimizer.py` — AI-driven optimization agent

---

## 25. Agent Registry

`agents/registry.py` — Global registry for discovering and managing agent types.

`agents/register_builtin.py` — Registers all built-in specialized agents.

`agents/nodes.py` — Agent node wrappers for workflow integration.

---

## 26. Workflow Templates

`workflows/` provides pre-built enterprise workflow templates:

| Template                   | Module                              | Description                           |
| -------------------------- | ----------------------------------- | ------------------------------------- |
| Debate workflow            | `workflows/debate.py`               | Debate-based decision making workflow |
| Consensus workflow         | `workflows/consensus.py`            | Consensus voting workflow             |
| Supervisor-worker workflow | `workflows/supervisor_worker.py`    | Hierarchical task delegation workflow |
| Enterprise templates       | `workflows/enterprise_templates.py` | Industry-standard workflow patterns   |
