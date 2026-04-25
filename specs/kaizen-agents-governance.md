# Kailash Kaizen Agents Specification — Governance & Orchestration

Version: 0.9.3

Parent domain: Kailash `kaizen-agents` package (Layer 2 — ENGINES). This file covers GovernedSupervisor, PACT governance subsystems, audit integration, event system, journey orchestration, agent lifecycle management, message transport, session management, runtime adapters, orchestration layer, and DataFlow integration. See also `kaizen-agents-core.md` and `kaizen-agents-patterns.md`.

---

## 9. GovernedSupervisor

The progressive-disclosure entry point for L3 orchestration. Hides the 20-concept L3 surface area behind three layers.

### 9.1 Progressive Disclosure

**Layer 1 (simple)**:

```python
supervisor = GovernedSupervisor(model="claude-sonnet-4-6", budget_usd=10.0)
result = await supervisor.run("Analyze this codebase")
```

**Layer 2 (configured)**:

```python
supervisor = GovernedSupervisor(
    model="claude-sonnet-4-6",
    budget_usd=10.0,
    tools=["read_file", "grep", "write_report"],
    data_clearance="restricted",
    warning_threshold=0.70,
)
```

**Layer 3 (advanced)**:

```python
supervisor.accountability   # AccountabilityTracker (read-only view)
supervisor.budget           # BudgetTracker (read-only view)
supervisor.cascade          # CascadeManager (read-only view)
supervisor.clearance        # ClearanceEnforcer (read-only view)
supervisor.audit            # AuditTrail (read-only view)
supervisor.dereliction      # DerelictionDetector (read-only view)
supervisor.bypass_manager   # BypassManager (read-only view)
supervisor.vacancy          # VacancyManager (read-only view)
supervisor.classifier       # ClassificationAssigner (read-only view)
```

All Layer 3 properties return `_ReadOnlyView` proxies that expose only query methods. Mutation methods are blocked.

### 9.2 Constructor Parameters

| Parameter           | Default               | Description                                                            |
| ------------------- | --------------------- | ---------------------------------------------------------------------- |
| `model`             | `"claude-sonnet-4-6"` | Model identifier                                                       |
| `budget_usd`        | `1.0`                 | Maximum budget in USD (must be finite, non-negative)                   |
| `tools`             | `[]`                  | Allowed tool names (default-deny per PACT Rule 5)                      |
| `data_clearance`    | `"public"`            | One of: public, internal, restricted, confidential, secret, top_secret |
| `timeout_seconds`   | `300.0`               | Maximum execution time                                                 |
| `warning_threshold` | `0.70`                | Budget warning threshold (0.0-1.0)                                     |
| `max_children`      | `10`                  | Max child agents per parent                                            |
| `max_depth`         | `5`                   | Max delegation depth                                                   |
| `policy_source`     | `""`                  | Human identity defining constraints                                    |
| `cost_model`        | `None`                | Optional CostModel for computing LLM token costs                       |

### 9.3 run() Method

```python
async def run(
    self,
    objective: str,
    context: dict | None = None,
    execute_node: ExecuteNodeFn | None = None,
) -> SupervisorResult
```

Decomposes the objective into a plan, executes each node through the provided callback, tracks budget and audit, returns results.

**Plan execution**: Nodes are executed in topological order. Ready nodes are those whose dependencies are all completed. Budget is checked before each node execution. If budget is exhausted, the node is held.

**Hold mechanism**: `GovernanceHeldError` from an executor pauses the node. A `HoldRecord` is created with an `asyncio.Event` for signaling resolution. External code calls `supervisor.resolve_hold(node_id, approved=True/False)` to resume or reject.

**Non-optional node failure halts the plan** (R1-06).

### 9.4 SupervisorResult

```python
@dataclass(frozen=True)
class SupervisorResult:
    success: bool
    results: dict[str, Any]
    plan: Plan | None
    events: list[PlanEvent]
    audit_trail: list[dict[str, Any]]
    budget_consumed: float
    budget_allocated: float
    modifications: list[PlanModification]
```

Frozen to prevent post-construction mutation.

### 9.5 Cost Resolution

Resolution order:

1. If `cost` is present and valid in executor output, use directly.
2. If absent but `prompt_tokens` and `completion_tokens` are present and a `CostModel` is configured, compute from token counts.
3. Otherwise 0.0.

### 9.6 Tool Use Auditing

```python
supervisor.record_tool_use(
    tool_name="read_file",
    arguments={"path": "/etc/config"},
    blocked=False,
)
```

Records only argument keys (not values) in the audit trail for security.

---

## 10. Governance Subsystems

### 10.1 Overview

| Subsystem            | Class                                                                                  | Purpose                                         |
| -------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------------- |
| P2-02 Accountability | `AccountabilityTracker`, `AccountabilityRecord`                                        | D/T/R addressing, agent registration, lineage   |
| P2-03 Clearance      | `ClearanceEnforcer`, `ClassificationAssigner`, `ClassifiedValue`, `DataClassification` | Data classification and access control          |
| P2-04 Cascade        | `CascadeManager`, `CascadeEvent`, `CascadeEventType`                                   | Cascade revocation of envelopes                 |
| P2-05 Vacancy        | `VacancyManager`, `VacancyEvent`, `OrphanRecord`                                       | Orphan detection when agents terminate          |
| P2-06 Dereliction    | `DerelictionDetector`, `DerelictionWarning`, `DerelictionStats`                        | Detecting underperforming agents                |
| P2-07 Bypass         | `BypassManager`, `BypassRecord`                                                        | Emergency constraint bypass with audit          |
| P2-08 Budget         | `BudgetTracker`, `BudgetEvent`, `BudgetSnapshot`                                       | Financial tracking with warning/hold thresholds |
| Cost model           | `CostModel`                                                                            | LLM token cost computation                      |

### 10.2 Budget Tracking

`BudgetTracker` (located in `kaizen_agents.governance.budget`, distinct from the trust-plane `kailash.trust.constraints.budget_tracker.BudgetTracker` which handles microdollar reserve/record accounting) allocates budget per agent ID and records consumption. Emits `BudgetEvent` instances for warnings and holds:

- `warning` event when utilization exceeds `warning_threshold` (default 0.70).
- `hold` event when utilization exceeds `hold_threshold` (default 1.0).

### 10.3 Clearance

`ClearanceEnforcer` filters data based on `ConfidentialityLevel` (PUBLIC, RESTRICTED, CONFIDENTIAL, SECRET, TOP_SECRET). `ClassificationAssigner` assigns classifications to values. `ClassifiedValue` wraps a value with its classification for access control.

### 10.4 Envelope Allocator

`policy/envelope_allocator.py` manages envelope allocation for agent hierarchies. Implements monotonic tightening (child envelopes can only be equal to or more restrictive than parent).

---

## 11. Audit Integration

### 11.1 AuditTrail

Append-only audit trail with SHA-256 hash chain integrity.

**Record types**:

- `genesis` — root agent creation with envelope
- `delegation` — parent delegating to child with envelope
- `termination` — agent termination with reason and budget consumed
- `action` — governance-relevant action (tool call, budget check)
- `held` — held event (node paused for human approval)
- `modification` — plan modification applied during recovery

**AuditRecord fields**: `record_id`, `record_type`, `timestamp` (UTC), `agent_id`, `parent_id`, `action`, `details`, `prev_hash`, `record_hash`.

**Hash computation**: `sha256(prev_hash + record_type + agent_id + action + timestamp_iso)`.

**Storage**: In-memory bounded deque with `maxlen=10000` (per trust-plane rules). Thread-safe via `threading.Lock`.

**Chain verification**: `verify_chain()` recomputes each record's hash and verifies prev_hash linkage. Handles bounded eviction gracefully (first surviving record's prev_hash references evicted record). Uses `hmac.compare_digest()` for timing-safe comparison.

**Query**: `query_by_agent(agent_id)` returns all records for a specific agent. `to_list()` exports all records as dicts.

---

## 12. Event System

### 12.1 StreamEvent Hierarchy (Wrapper-Level Events)

All events are `@dataclass(frozen=True)` for immutability. Inherit from `StreamEvent` with `event_type` discriminator and monotonic `timestamp`.

| Event                  | event_type               | Fields                                                           |
| ---------------------- | ------------------------ | ---------------------------------------------------------------- |
| `TextDelta`            | `text_delta`             | `text: str`                                                      |
| `ToolCallStart`        | `tool_call_start`        | `call_id: str`, `name: str`                                      |
| `ToolCallEnd`          | `tool_call_end`          | `call_id: str`, `name: str`, `result: str`, `error: str`         |
| `TurnComplete`         | `turn_complete`          | `text: str`, `usage: dict`, `structured: Any`, `iterations: int` |
| `BudgetExhausted`      | `budget_exhausted`       | `budget_usd: float`, `consumed_usd: float`                       |
| `ErrorEvent`           | `error`                  | `error: str`, `details: dict`                                    |
| `StreamBufferOverflow` | `stream_buffer_overflow` | `dropped_count: int`, `oldest_timestamp: float`                  |

`StreamTimeoutError` is a `RuntimeError` subclass raised when a streaming operation exceeds its timeout.

### 12.2 DelegateEvent Hierarchy (Delegate-Level Events)

Mutable `@dataclass` events yielded by `Delegate.run()`. Same event types as StreamEvent but not frozen (for backward compatibility with the Delegate's accumulation pattern).

---

## 13. Journey Orchestration

### 13.1 Architecture

Journey orchestration (Layer 5) enables multi-phase user journey definitions with nested pathway classes.

```
Journey (JourneyMeta metaclass)
  - Extracts nested Pathway classes automatically
  - Validates entry pathway exists
  - Manages global transitions

Pathway (PathwayMeta metaclass)
  - Extracts signature, agents, pipeline config
  - Supports various pipeline types
  - Accumulates context across pathways
```

### 13.2 Journey Definition

```python
class BookingJourney(Journey):
    __entry_pathway__ = "intake"
    __transitions__ = [
        Transition(trigger=IntentTrigger(["help"]), to_pathway="faq")
    ]

    class IntakePath(Pathway):
        __signature__ = IntakeSignature
        __agents__ = ["intake_agent"]
        __next__ = "booking"
        __accumulate__ = ["customer_name", "customer_email"]

    class BookingPath(Pathway):
        __signature__ = BookingSignature
        __agents__ = ["booking_agent"]

    class FAQPath(Pathway):
        __signature__ = FAQSignature
        __agents__ = ["faq_agent"]
        __return_behavior__ = ReturnToPrevious()
```

### 13.3 JourneyMeta Metaclass

Automatically extracts nested `Pathway` classes from the journey definition. Converts PascalCase class names to snake_case pathway IDs (e.g., `IntakePath` -> `"intake"`, `UserRegistrationPath` -> `"user_registration"`). Validates that `__entry_pathway__` exists in extracted pathways. Defaults to first pathway if not specified.

### 13.4 PathwayMeta Metaclass

Extracts pathway configuration from class attributes:

- `__signature__` — Signature class for I/O contract
- `__agents__` — List of agent IDs
- `__pipeline__` — Pipeline type: `sequential`, `parallel`, `router`, `ensemble`, `supervisor_worker`
- `__pipeline_config__` — Pattern-specific settings (e.g., `routing_strategy`, `top_k`)
- `__accumulate__` — Fields to preserve across pathways
- `__next__` — Default next pathway
- `__guidelines__` — Pathway-specific behavioral guidelines (merged with signature guidelines)
- `__return_behavior__` — Navigation behavior after completion (`ReturnToPrevious`, `ReturnToSpecific`)

### 13.5 Pathway Execution

```python
async def execute(self, context: PathwayContext) -> PathwayResult
```

1. Resolves agent IDs to agent instances from the manager's registry.
2. Builds pipeline from agents based on pipeline type.
3. Prepares inputs from context (including accumulated context from previous pathways).
4. Executes pipeline.
5. Extracts accumulated fields from result.

### 13.6 JourneyConfig

| Parameter                     | Default         | Description                                       |
| ----------------------------- | --------------- | ------------------------------------------------- |
| `intent_detection_model`      | `"gpt-4o-mini"` | Model for intent classification                   |
| `intent_confidence_threshold` | `0.7`           | Minimum confidence for intent match               |
| `intent_cache_ttl_seconds`    | `300`           | Cache TTL for intent results                      |
| `max_pathway_depth`           | `10`            | Maximum pathway navigation depth (prevents loops) |
| `pathway_timeout_seconds`     | `60.0`          | Timeout for pathway execution                     |
| `max_context_size_bytes`      | `1048576`       | Maximum accumulated context size (1MB)            |
| `context_persistence`         | `"memory"`      | Storage backend: "memory", "dataflow", "redis"    |
| `error_recovery`              | `"graceful"`    | Error handling: "fail_fast", "graceful", "retry"  |
| `max_retries`                 | `3`             | Maximum retry attempts                            |

### 13.7 Intent Detection

`IntentDetector` provides LLM-powered intent classification with a three-tier detection flow:

1. **Pattern matching (fast path, <1ms)**: Checks patterns in `IntentTrigger` objects. If any trigger's patterns match, returns immediately with confidence 1.0.
2. **Cache lookup (<5ms)**: Checks if the message+triggers combination is cached (MD5 hash key, TTL-based expiry, max 1000 entries with LRU eviction).
3. **LLM classification (slow path, <200ms)**: Uses `BaseAgent` with `IntentClassificationSignature`. Only fires for triggers with `use_llm_fallback=True`.

**IntentClassificationSignature**:

- Input: `message`, `available_intents` (JSON list), `conversation_context`
- Output: `intent` (name or "unknown"), `confidence` (0.0-1.0), `reasoning`

**IntentMatch result**: `intent`, `confidence`, `reasoning`, `trigger` (matched trigger), `from_cache`, `detection_method` ("pattern"/"llm"/"cache").

### 13.8 PathwayContext and PathwayResult

```python
@dataclass
class PathwayContext:
    session_id: str
    pathway_id: str
    user_message: str
    accumulated_context: Dict[str, Any]
    conversation_history: List[Dict[str, Any]]

@dataclass
class PathwayResult:
    outputs: Dict[str, Any]
    accumulated: Dict[str, Any]
    next_pathway: Optional[str]
    is_complete: bool
    error: Optional[str]
```

---

## 14. Agent Lifecycle Management

`AgentLifecycleManager` bridges local kaizen-agents types and SDK `AgentFactory`.

### 14.1 Operations

- `spawn_agent(local_spec, parent_id)` — converts local `AgentSpec` to SDK `AgentSpec`, spawns via factory. Validates parent state, max_children, max_depth, tool subset.
- `terminate_agent(instance_id, reason)` — terminates agent and cascades to all descendants. Resolves reason string to `TerminationReason` enum (fallback: `EXPLICIT_TERMINATION`).
- `mark_running(instance_id)` — transitions to Running state.
- `mark_completed(instance_id, result)` — transitions to Completed state.
- `get_children(parent_id)` — returns direct children.
- `get_lineage(instance_id)` — returns root-to-instance ancestry path.

### 14.2 Spec Conversion

Local `AgentSpec` fields are mapped to SDK `AgentSpec`:

- `ConstraintEnvelope` -> dict via `envelope_to_dict()`
- `MemoryConfig` -> dict with session/shared/persistent keys
- `timedelta max_lifetime` -> float seconds (or None)
- All other fields map directly

---

## 15. Message Transport

`MessageTransport` wraps the SDK `MessageRouter` for protocol-level message exchange.

### 15.1 Message Types

| Type            | Payload                                                                                                           | Direction       |
| --------------- | ----------------------------------------------------------------------------------------------------------------- | --------------- |
| `DELEGATION`    | `DelegationPayload` (task_description, context_snapshot, deadline, priority)                                      | Parent -> Child |
| `COMPLETION`    | `CompletionPayload` (result, success, context_updates, resource_consumed, error_detail)                           | Child -> Parent |
| `CLARIFICATION` | `ClarificationPayload` (question, blocking, is_response, options)                                                 | Bidirectional   |
| `ESCALATION`    | `EscalationPayload` (severity, problem_description, attempted_mitigations, suggested_action, violating_dimension) | Child -> Parent |
| `STATUS`        | `StatusPayload` (phase, resource_usage, progress_pct)                                                             | Child -> Parent |
| `SYSTEM`        | `SystemPayload` (subtype, reason, dimension, detail, instance_id)                                                 | System          |

### 15.2 Channel Management

```python
transport.setup_channel(parent_id, child_id, capacity=100)  # Bidirectional
transport.teardown_channel(instance_id)  # Close all, pending -> dead letters
```

### 15.3 Send/Receive

```python
msg_id = await transport.send_delegation(from_id, to_id, payload, correlation_id, ttl_seconds=300)
msg_id = await transport.send_completion(from_id, to_id, payload, correlation_id)
msg_id = await transport.send_clarification(from_id, to_id, payload, correlation_id)
msg_id = await transport.send_escalation(from_id, to_id, payload, correlation_id)
messages = await transport.receive_pending(instance_id)  # Returns list[L3Message]
```

### 15.4 Type Conversion

Local payload types (`kaizen_agents.types`) are converted to SDK types (`kaizen.l3.messaging.types`) at the boundary and vice versa. Enums are mapped by name (both sides share the same member names).

---

## 16. Session Management

`SessionManager` persists sessions as JSON files under `<root>/.kz/sessions/`.

### 16.1 Operations

- `save_session(name, conversation, usage, config)` — persists state to disk with 0o600 permissions (POSIX), path traversal protection via allowlist sanitization.
- `load_session(name)` — loads and returns parsed dict, or None.
- `list_sessions()` — lists all sessions with metadata, sorted by timestamp descending.
- `fork_session(source, new_name)` — copies session with updated metadata.
- `delete_session(name)` — deletes session file.
- `auto_save(conversation, usage, config)` — auto-saves as `_auto` for crash recovery.

### 16.2 Security

- File permissions: 0o600 on POSIX, standard write on Windows.
- Directory permissions: 0o700.
- Path sanitization: `re.sub(r"[^a-zA-Z0-9_-]", "_", name)` prevents path traversal.
- No TOCTOU window: uses `os.open()` with `O_CREAT | O_TRUNC` and permission flags on POSIX.

---

## 17. Runtime Adapters

Runtime adapters connect kaizen-agents to external agent runtimes.

| Adapter              | Module                             | Runtime              |
| -------------------- | ---------------------------------- | -------------------- |
| `ClaudeCodeAdapter`  | `runtime_adapters/claude_code.py`  | Claude Code CLI      |
| `GeminiCliAdapter`   | `runtime_adapters/gemini_cli.py`   | Gemini CLI           |
| `KaizenLocalAdapter` | `runtime_adapters/kaizen_local.py` | Local Kaizen runtime |
| `OpenAICodexAdapter` | `runtime_adapters/openai_codex.py` | OpenAI Codex         |

Tool mapping submodules (`runtime_adapters/tool_mapping/`) handle provider-specific tool format conversion (base, gemini, mcp, openai).

---

## 19. Orchestration Layer

### 19.1 Planner

- `planner/decomposer.py` — Decomposes objectives into sub-tasks
- `planner/composer.py` — Composes sub-tasks into execution plans
- `planner/designer.py` — Designs agent configurations for plan nodes

### 19.2 Protocols

- `protocols/delegation.py` — Parent-to-child task delegation protocol
- `protocols/clarification.py` — Inter-agent clarification request/response protocol
- `protocols/escalation.py` — Child-to-parent escalation protocol

### 19.3 Recovery

- `recovery/diagnoser.py` — Diagnoses failures in plan execution
- `recovery/recomposer.py` — Recomposes plans after failure

### 19.4 Context Management

- `context/injector.py` — Injects context into agent prompts
- `context/summarizer.py` — Summarizes context for compression
- `context/_scope_bridge.py` — Bridges context scopes between agents

### 19.5 Monitor

`orchestration/monitor.py` — Monitors orchestration progress and health.

### 19.6 Strategy-Driven Runtime — Cross-SDK Parity

The `kaizen.orchestration.OrchestrationRuntime` class (added 2026-04-25, issue #602) ships the Python equivalent of the Rust `kaizen-agents::orchestration::runtime::OrchestrationRuntime` shape (kailash-rs ISS-27). This is the canonical strategy-driven multi-agent coordinator and is distinct from `kaizen_agents.patterns.OrchestrationRuntime` (registry/lifecycle/health-monitoring runtime for 10-100 agent fleets) and `kaizen.trust.orchestration.TrustAwareOrchestrationRuntime` (trust-policy enforcement).

**Public surface (`kaizen.orchestration`):**

- `OrchestrationRuntime(strategy, coordinator=None, config=None)` — strategy-driven runtime; builder-style `.add_agent(name, agent)`, `.strategy(s)`, `.coordinator(c)`, `.config(c)` setters all return `self`.
- `OrchestrationStrategy` — frozen dataclass + classmethod factories: `sequential()`, `parallel()`, `hierarchical(coordinator_name)`, `pipeline(steps)`. Mirrors the Rust enum without exposing an opaque string surface.
- `OrchestrationStrategyKind` — `StrEnum`; lowercase string values (`"sequential"`, `"parallel"`, `"hierarchical"`, `"pipeline"`) match the Rust serde discriminator.
- `PipelineStep(agent_name, input_from)` + `PipelineInputSource` — pipeline strategy step descriptors; `PipelineInputSource.from_initial()`, `from_agent_output(name)`, `from_template(template)`.
- `OrchestrationConfig(max_total_iterations=50, max_agent_calls=100, timeout_secs=None, fail_fast=True, share_conversation_history=False)` — field shape parity with Rust struct.
- `OrchestrationResult(agent_results, final_output, total_iterations, total_tokens, duration_ms)` — field shape parity with Rust struct; `to_dict()` returns the cross-SDK-stable mapping.
- `Coordinator` Protocol — `async store(key, value)` / `async retrieve(key) -> Optional`. Mirrors Rust's `Arc<dyn AgentMemory>`.
- `AgentLike` Protocol — `name` property + `async run_async(**inputs) -> Mapping`. Real `kaizen.core.base_agent.BaseAgent` instances satisfy this Protocol; test/port shims may implement the minimum.
- `SharedMemoryCoordinator` — default in-memory coordinator backed by `kaizen.memory.shared_memory.SharedMemoryPool`.
- `OrchestrationError` — typed error subclassing `RuntimeError` for empty-runtime / unknown-coordinator / pipeline-step-references-unknown-agent / max-agent-calls.

**Execution contract:**

- `await runtime.run(input)` returns `OrchestrationResult`. Async-first to match the Rust `async fn run`.
- `runtime.run_sync(input)` — synchronous convenience that calls `asyncio.run` internally. Per `rules/patterns.md` § "Paired Public Surface — Consistent Async-ness", this MUST NOT be called from inside an active event loop (raises `RuntimeError: This event loop is already running`); CLI/script use only.
- `OrchestrationConfig.timeout_secs` enforced via `asyncio.wait_for`; on expiry `asyncio.TimeoutError` is raised (preserves the standard library type so existing `except asyncio.TimeoutError` handlers compose).
- `fail_fast=True` (default) — Sequential / Hierarchical / Pipeline raise `OrchestrationError` on the first agent failure; Parallel cancels in-flight tasks and raises. `fail_fast=False` — Parallel collects all successes and surfaces the first error only when every agent failed.

**Strategy semantics (mirrors Rust `_run_*` helpers):**

| Strategy       | Input handling                                     | Final output                                                          |
| -------------- | -------------------------------------------------- | --------------------------------------------------------------------- |
| Sequential     | Each agent receives prior agent's `response`.      | Last agent's response.                                                |
| Parallel       | Every agent receives the same input.               | Single agent: lone response. Multi-agent: `--- name ---\n` headers.   |
| Hierarchical   | Coordinator first; sub-agents receive its response | Coordinator's response (the synthesis).                               |
| Pipeline       | Per-step input from `PipelineInputSource`          | Last step's response (preserves insertion order).                     |

**Coordinator forwarding:** The default agent invoker forwards the registered `Coordinator` as a `coordinator=` kwarg ONLY when the target callable's signature accepts it (`inspect.signature` opt-in). This is structural plumbing (signature inspection), NOT runtime classification — agents that do not declare the kwarg run in isolation.

**Cross-SDK parity tests:** `tests/integration/orchestration/test_runtime_e2e.py::TestCrossSdkShapeParity` locks the `OrchestrationResult` field set + `OrchestrationStrategyKind` lowercase values against the Rust struct shape. Field divergence between SDKs is caught at test-collection time, not at the wire.

---

## 20. DataFlow Integration

`integrations/dataflow/` provides integration between Kaizen agents and the DataFlow framework:

| Module               | Purpose                         |
| -------------------- | ------------------------------- |
| `base.py`            | Base DataFlow integration       |
| `connection.py`      | Connection management           |
| `ai_enhanced_ops.py` | AI-enhanced database operations |
| `batch_optimizer.py` | Batch operation optimization    |
| `db_driven_ai.py`    | Database-driven AI workflows    |
| `query_cache.py`     | Query result caching            |
| `query_optimizer.py` | Query optimization              |
