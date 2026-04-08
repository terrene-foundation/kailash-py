# kailash-rs Agent Architecture Deep Audit — 2026-04-07

**Status**: This is the most important rs research file. It reveals the composition-over-extension-points pattern that resolves the Python red team's composition self-contradiction.

## BaseAgent Trait (The Primitive Contract)

**Location**: `crates/kailash-kaizen/src/agent/mod.rs`

```rust
#[async_trait]
pub trait BaseAgent: Send + Sync {
    fn name(&self) -> &str;
    fn description(&self) -> &str;
    async fn run(&self, input: &str) -> Result<AgentResult, AgentError>;
    async fn run_with_memory(
        &self,
        input: &str,
        _shared_memory: Arc<dyn AgentMemory>,
    ) -> Result<AgentResult, AgentError> {
        // default delegates to run()
        self.run(input).await
    }
}
```

**Only 2 methods** (4 if you count name/description). No extension points. No mixins. No strategies. No Node inheritance.

## AgentResult

```rust
pub struct AgentResult {
    pub response: String,
    pub session_id: Uuid,
    pub iterations: u32,
    pub tool_calls_made: u32,
    pub total_tokens: u64,
    pub prompt_tokens: u64,
    pub completion_tokens: u64,
    pub duration_ms: u64,
}
```

## AgentConfig

```rust
pub struct AgentConfig {
    pub model_env_var: String,           // read from .env (Rule: .env is source of truth)
    pub model: Option<String>,           // explicit override
    pub execution_mode: ExecutionMode,   // Autonomous | SingleShot
    pub memory: MemoryConfig,            // Session | None
    pub tool_access: ToolAccess,         // Full | Constrained | None
    pub max_iterations: u32,             // TAOD loop limit
    pub system_prompt: Option<String>,
    pub temperature: Option<f64>,
    pub max_tokens: Option<u32>,
    pub envelope: Option<String>,        // L3 envelope reference
}

pub enum ExecutionMode {
    Autonomous,   // full TAOD loop + conversation history
    SingleShot,   // one LLM call, no iteration
}
```

## Core Supporting Traits

### AgentMemory

```rust
#[async_trait]
pub trait AgentMemory: Send + Sync {
    async fn store(&self, key: &str, value: Value) -> Result<(), AgentError>;
    async fn retrieve(&self, key: &str) -> Result<Option<Value>, AgentError>;
    async fn remove(&self, key: &str) -> Result<(), AgentError>;
    async fn keys(&self) -> Result<Vec<String>, AgentError>;
    async fn clear(&self) -> Result<(), AgentError>;
}
```

**Implementations**: SessionMemory (HashMap), SharedMemory (Arc<RwLock>), NoMemory, PersistentMemory (file or SQLite).

### Tool System

```rust
pub struct ToolDef {
    pub name: Arc<str>,
    pub description: Arc<str>,
    pub parameters: Vec<ToolParam>,
    pub func: Arc<dyn ToolFn>,  // async callable
}

#[async_trait]
pub trait ToolFn: Send + Sync {
    async fn call(&self, inputs: ValueMap) -> Result<Value, AgentError>;
}

pub struct ToolRegistry {
    tools: HashMap<String, ToolDef>,
}
```

**Critical**: ToolRegistry stores **callable executors** (func is `Arc<dyn ToolFn>`), not just JSON schemas. This is why Rust's tools actually execute.

### Output Schema

```rust
pub struct OutputSchema { /* JSON schema */ }
pub struct StructuredOutput { /* parser + validator + retry */ }

// Orchestrator:
// 1. parse text → extract JSON
// 2. validate schema
// 3. if invalid, retry with correction prompt
```

### Checkpoint

```rust
pub struct AgentCheckpoint {
    pub agent_name: String,
    pub model: String,
    pub state: Value,
    pub timestamp: DateTime<Utc>,
}

#[async_trait]
pub trait CheckpointStorage: Send + Sync {
    async fn save(&self, checkpoint: &AgentCheckpoint) -> Result<String, AgentError>;
    async fn load(&self, id: &str) -> Result<AgentCheckpoint, AgentError>;
    async fn delete(&self, id: &str) -> Result<(), AgentError>;
}
```

**Implementations**: InMemoryCheckpointStorage, FileCheckpointStorage.

## Agent (Concrete Primitive Implementation)

**Location**: `crates/kaizen-agents/src/agent_engine/concrete.rs`

```rust
pub struct Agent {
    config: AgentConfig,
    model: String,
    llm: Arc<LlmClient>,                      // shared LLM client
    tools: Arc<ToolRegistry>,                 // shared tools
    memory: Box<dyn AgentMemory>,             // persistent KV store
    conversation: Vec<ConversationTurn>,      // history
    output_schema: Option<StructuredOutput>,  // structured extraction
    hydrator: Option<Arc<dyn ToolHydrator>>,  // progressive tool disclosure
}

impl BaseAgent for Agent {
    fn name(&self) -> &str { &self.config.name }
    fn description(&self) -> &str { "Kaizen Agent" }
    async fn run(&self, input: &str) -> Result<AgentResult, AgentError>;
    async fn run_with_memory(&self, input: &str, shared_memory: Arc<dyn AgentMemory>)
        -> Result<AgentResult, AgentError>;
}

impl Agent {
    // Constructor
    pub fn new(config: AgentConfig, llm: LlmClient) -> Result<Self, AgentError>;

    // Builder methods (composition-style, not inheritance)
    pub fn with_output_schema(self, schema: OutputSchema) -> Self;
    pub fn with_tools(self, tools: ToolRegistry) -> Self;
    pub fn with_memory(self, memory: Box<dyn AgentMemory>) -> Self;
    pub fn with_shared_llm(self, llm: Arc<LlmClient>) -> Self;
    pub fn with_hydrator(self, hydrator: Arc<dyn ToolHydrator>) -> Self;

    // Public API
    pub async fn chat(&mut self, input: &str) -> Result<String, AgentError>;
    pub async fn chat_with_result(&mut self, input: &str) -> Result<AgentResult, AgentError>;
    pub async fn chat_stream(&mut self, input: &str) -> (CallerEventStream, ChatStreamHandle);
    pub fn conversation(&self) -> &[ConversationTurn];
    pub fn clear_conversation(&mut self);
    pub fn resolve_tools(&self) -> Option<Vec<ToolDef>>;
}
```

**Key observation**: `Agent` is itself a composition. It holds `Arc<LlmClient>`, `Arc<ToolRegistry>`, `Box<dyn AgentMemory>`, `Option<StructuredOutput>`. It's not "the base class you inherit from" — it's "the default composition of primitives."

## TaodRunner (The Autonomous Execution Loop)

**Location**: `crates/kaizen-agents/src/agent_engine/taod.rs`

```rust
pub struct TaodConfig {
    pub max_iterations: u32,
    pub timeout: Duration,
    pub system_prompt: Option<String>,
    pub model: String,                  // read from env
    pub temperature: Option<f64>,
    pub max_tokens: Option<u32>,
    pub api_key: Option<String>,
    pub base_url: Option<String>,
}

pub struct TaodResult {
    pub final_response: String,
    pub iterations: u32,
    pub tool_calls_made: Vec<String>,
    pub tool_call_records: Vec<ToolCallRecord>,
    pub elapsed: Duration,
}

pub struct TaodRunner {
    llm: Arc<LlmClient>,
    tools: Arc<ToolRegistry>,
    memory: Box<dyn AgentMemory>,
    config: TaodConfig,
    hydrator: Option<Arc<dyn ToolHydrator>>,
}

impl TaodRunner {
    pub fn new(llm: Arc<LlmClient>, tools: Arc<ToolRegistry>,
               memory: Box<dyn AgentMemory>, config: TaodConfig) -> Self;

    pub async fn run(&mut self, prompt: &str) -> Result<TaodResult, AgentError>;
    pub fn run_stream(&self, prompt: &str) -> CallerEventStream;
    pub fn with_hydrator(self, hydrator: Arc<dyn ToolHydrator>) -> Self;
}
```

### The TAOD Loop

```
run(prompt)
  ↓
conversation = [prompt]
start_time = now()
iteration = 0

loop {
    iteration++
    if iteration > max_iterations { break with MaxIterations }
    if elapsed > timeout { break with Timeout }

    // 1. THINK
    Thought = llm.complete(conversation, tools)

    // 2. ACT
    if Thought.tool_calls.is_none() {
        return Thought.content as final_response (finished)
    }
    Actions = execute(Thought.tool_calls)   // parallel via asyncio

    // 3. OBSERVE
    conversation.push(AssistantTurn(Thought))
    conversation.push(ToolResultTurn(Actions))
    Observation = synthesize(Actions)

    // 4. DECIDE
    Decision = should_continue(Observation, iteration, elapsed)
    if Decision.Done { return final_response }
}

return TaodResult { ... }
```

**Important**: TaodRunner is NOT a BaseAgent implementation. It's a separate primitive that Agent uses internally for autonomous execution. Agent's `run()` delegates to TaodRunner when `execution_mode == Autonomous`.

## Streaming (Wrapper Pattern)

**Location**: `crates/kaizen-agents/src/streaming/`

```rust
pub enum CallerEvent {
    Start,
    Token(String),
    ToolCall(ToolCallRequest),
    ToolResult(ToolResult),
    Done(TaodResult),
    Error(AgentError),
}

pub type CallerEventStream = Box<dyn Stream<Item = CallerEvent> + Send>;

pub struct StreamingAgent {
    agent: Agent,                          // <-- WRAPS Agent
    handler: Option<Arc<dyn StreamHandler>>,
}

impl StreamingAgent {
    pub async fn run_stream(&self, prompt: &str) -> CallerEventStream;
}

pub trait StreamHandler: Send + Sync {
    async fn on_start(&self);
    async fn on_token(&self, token: &str);
    async fn on_end(&self, full_text: &str);
    async fn on_error(&self, error: &AgentError);
}

pub struct TokenCollector {
    full_text: RwLock<String>,
}
impl StreamHandler for TokenCollector { ... }

pub struct ChannelStreamHandler {
    tx: tokio::sync::mpsc::Sender<StreamEvent>,
}
```

**The composition-wrapper pattern**: StreamingAgent **wraps** an Agent and adds streaming behavior. Agent doesn't need to know about streaming. Users who need events wrap their Agent in StreamingAgent.

## All BaseAgent Implementations in Rust

| Implementation    | File                                   | Pattern               | What It Adds                                         |
| ----------------- | -------------------------------------- | --------------------- | ---------------------------------------------------- |
| `Agent`           | `agent_engine/concrete.rs`             | Primary concrete impl | LLM + tools + memory + signatures + hydrator         |
| `SupervisorAgent` | `orchestration/supervisor.rs`          | Composes WorkerAgents | Routing strategy (RoundRobin, Capability, Custom)    |
| `WorkerAgent`     | `orchestration/worker.rs`              | Wraps any BaseAgent   | Worker status tracking, capabilities list            |
| `StreamingAgent`  | `streaming/agent.rs`                   | Wraps Agent           | Event stream (CallerEvent)                           |
| `L3GovernedAgent` | `l3_runtime/agent.rs`                  | Wraps any BaseAgent   | EATP + envelope + hold enforcement                   |
| `MonitoredAgent`  | `kailash-kaizen/src/cost/monitored.rs` | Wraps any BaseAgent   | Cost tracking via CostTracker                        |
| Specialized       | `agents/specialized/*`                 | Wraps Agent           | ConversationalAgent, ResearchAgent, ToolCallingAgent |

**Critical: ZERO subclass inheritance**. Every implementation is either the primary `Agent` or a **composition wrapper**.

## SupervisorAgent + WorkerAgent (Multi-Agent Pattern)

```rust
pub struct SupervisorAgent {
    supervisor_name: String,
    workers: Vec<Arc<WorkerAgent>>,
    routing_strategy: RoutingStrategy,  // RoundRobin | Capability | CapabilityWithHint | Custom
    round_robin_index: AtomicUsize,
    max_delegation_depth: u32,
}

pub struct WorkerAgent {
    name: String,
    inner: Arc<dyn BaseAgent>,          // WRAPS any BaseAgent
    capabilities: Vec<String>,          // keywords for routing
    status: AtomicU32,                  // WorkerStatus flags
}

#[async_trait]
impl BaseAgent for SupervisorAgent {
    async fn run(&self, input: &str) -> Result<AgentResult, AgentError> {
        // 1. Select worker via routing_strategy
        let worker = self.select_worker(input)?;
        // 2. Delegate task to worker
        worker.inner.run(input).await
    }
}
```

**Note**: Both SupervisorAgent and WorkerAgent themselves implement BaseAgent. They can be nested inside other wrappers (e.g., `MonitoredAgent(SupervisorAgent(...))`).

## DelegateEngine (The Engine Facade)

**Location**: `crates/kaizen-agents/src/delegate_engine.rs`

```rust
pub struct DelegateEngine {
    agent: Option<Agent>,
    taod: Option<TaodRunner>,
    supervisor: Option<GovernedSupervisor>,
    pact: Option<PactEngine>,
    llm_client: Option<Arc<LlmClient>>,
    hydrator: Option<Arc<dyn ToolHydrator>>,
}

impl DelegateEngine {
    pub fn builder() -> DelegateEngineBuilder;

    pub async fn run(&self, prompt: &str) -> Result<TaodResult, AgentError> {
        // Requires: agent + llm_client
        // Constructs TaodRunner on-the-fly from agent config
    }

    pub fn run_stream(&self, prompt: &str) -> CallerEventStream {
        // Streams TAOD execution as CallerEvent items
    }

    pub fn is_governed(&self) -> bool {
        self.pact.is_some() || self.supervisor.is_some()
    }
}

pub struct DelegateEngineBuilder {
    agent: Option<Agent>,
    taod: Option<TaodRunner>,
    supervisor: Option<GovernedSupervisor>,
    pact: Option<PactEngine>,
    llm_client: Option<Arc<LlmClient>>,
    hydrator: Option<Arc<dyn ToolHydrator>>,
}

impl DelegateEngineBuilder {
    pub fn agent(mut self, agent: Agent) -> Self;
    pub fn taod(mut self, taod: TaodRunner) -> Self;
    pub fn supervisor(mut self, supervisor: GovernedSupervisor) -> Self;
    pub fn pact(mut self, pact: PactEngine) -> Self;
    pub fn llm_client(mut self, client: Arc<LlmClient>) -> Self;
    pub fn hydrator(mut self, hydrator: Arc<dyn ToolHydrator>) -> Self;
    pub fn build(self) -> DelegateEngine;
}
```

**This is pure composition via optional fields.** Unlike Python's `Delegate` (which has progressive disclosure layers), Rust's `DelegateEngine` is a plain composition struct that users build up.

## L3 Runtime

**Files**: `kaizen-agents/src/l3_runtime/`

| File          | Purpose                                                  |
| ------------- | -------------------------------------------------------- |
| `agent.rs`    | `L3GovernedAgent` (BaseAgent wrapper enforcing L3 rules) |
| `factory/`    | `AgentFactory` (8-precondition spawn, registry)          |
| `messaging/`  | `MessageRouter` (priority channels, validation)          |
| `pipeline.rs` | `L3EnforcementPipeline` (EATP + envelope + hold)         |
| `plan/`       | `PlanExecutor` (DAG scheduling via topological sort)     |

### L3GovernedAgent

```rust
pub struct L3GovernedAgent {
    inner: Arc<dyn BaseAgent>,         // WRAPS any BaseAgent
    pipeline: Arc<L3EnforcementPipeline>,
}

#[async_trait]
impl BaseAgent for L3GovernedAgent {
    async fn run(&self, input: &str) -> Result<AgentResult, AgentError> {
        // 1. Check EATP trust chain
        // 2. Validate envelope (budget, clearance)
        // 3. Enforce cascade constraints
        // 4. Handle hold/bypass
        // 5. Delegate to inner agent
        self.pipeline.pre_execute(input).await?;
        let result = self.inner.run(input).await?;
        self.pipeline.post_execute(&result).await?;
        Ok(result)
    }
}
```

**This is the canonical composition-wrapper pattern**: takes a BaseAgent, adds a capability (governance), implements BaseAgent so it can be further wrapped.

## Governance Subsystems (8 modules)

**Files**: `kaizen-agents/src/governance/`

1. **accountability.rs** — D/T/R tracking (Decider, Trustee, Responder)
2. **budget.rs** — `GovernanceBudgetTracker` (multidimensional: financial, compute, time)
3. **bypass.rs** — `BypassManager` (emergency hold/resume on governance+budget)
4. **cascade.rs** — `CascadeManager` (parent → child constraint inheritance)
5. **clearance.rs** — `ClearanceEnforcer` (knowledge classification access control)
6. **dereliction.rs** — `DerelictionDetector` (failure to perform duty)
7. **envelope_adapter.rs** — `RoleEnvelope` ↔ budget/clearance conversion
8. **vacancy.rs** — `VacancyManager` (orphaned role detection)

**None make LLM calls directly.** They are deterministic governance engines. Higher-level orchestration (Decomposer, Designer, Diagnoser, Recomposer, Monitor) makes LLM calls to **apply** governance policies.

**This matches Python's kaizen-agents governance modules exactly.**

## PactEngine

**Location**: `kaizen-agents/src/pact_engine/mod.rs`

```rust
pub struct PactEngine {
    engine: Arc<GovernanceEngine>,              // policy verdict (from kailash-pact)
    budget: Arc<GovernanceBudgetTracker>,       // spend tracking
    bypass: Arc<BypassManager>,                 // hold/resume
    config: PactEngineConfig,
}

impl PactEngine {
    pub async fn execute(
        &self,
        task_id: &str,
        role_address: &str,
        inputs: DelegateInputs,
        delegate: &dyn GovernedDelegate,
    ) -> Result<DelegateResult, OrchestrationError> {
        // Step 1: Check governance verdict (Blocked/Held/Flagged/AutoApproved)
        // Step 2: Check budget (financial/compute/time)
        // Step 3: Execute delegate (callback)
        // Step 4: Record cost in budget tracker
    }
}
```

**This is the "Dual Plane bridge"** — connects the policy plane (GovernanceEngine from kailash-pact) to the execution plane (budget + bypass + delegate callback).

## Cost Tracking (Standalone Module)

**Location**: `crates/kailash-kaizen/src/cost/`

```rust
pub struct CostTracker {
    config: CostConfig,
    cumulative_cost: Arc<Mutex<f64>>,    // in microdollars (integer precision)
    per_model: Arc<Mutex<HashMap<String, CostRecord>>>,
}

pub struct CostConfig {
    pub model_pricing: HashMap<String, ModelPricing>,
    pub budget_limit: Option<f64>,
}

pub struct ModelPricing {
    pub prompt_price_per_token: f64,
    pub completion_price_per_token: f64,
}

pub struct MonitoredAgent {
    inner: Arc<dyn BaseAgent>,           // WRAPS any BaseAgent
    tracker: Arc<CostTracker>,
}

#[async_trait]
impl BaseAgent for MonitoredAgent {
    async fn run(&self, input: &str) -> Result<AgentResult, AgentError> {
        let result = self.inner.run(input).await?;
        self.tracker.record_usage(&result.model, &result.usage)?;
        Ok(result)
    }
}
```

**Python doesn't have this cost module.** Python's `BudgetTracker` lives in `kailash.trust.*` but isn't wired into agents as a wrapper. Python should port this pattern.

## Rust vs Python Architectural Comparison

| Aspect                  | Python (current)                                | Rust                                                                     | Target (Python after refactor)                                   |
| ----------------------- | ----------------------------------------------- | ------------------------------------------------------------------------ | ---------------------------------------------------------------- |
| **BaseAgent interface** | Monolith with 7 extension points, 3,698 LOC     | 2-method trait                                                           | **2-method trait** (slim BaseAgent)                              |
| **Concrete agent**      | BaseAgent (it IS the concrete)                  | `Agent` struct                                                           | **`Agent` = slimmed BaseAgent**                                  |
| **Streaming**           | None (AgentLoop in parallel stack)              | `StreamingAgent(Agent)` wrapper                                          | **`StreamingAgent(BaseAgent)` wrapper**                          |
| **Cost tracking**       | BudgetTracker in kailash.trust (not wired)      | `MonitoredAgent(BaseAgent)` wrapper                                      | **`MonitoredAgent(BaseAgent)` wrapper**                          |
| **Governance**          | GovernedSupervisor (wraps Delegate)             | `L3GovernedAgent(BaseAgent)` wrapper                                     | **`L3GovernedAgent(BaseAgent)` wrapper**                         |
| **Supervisor/Worker**   | SupervisorWorkerPattern (coordination pattern)  | `SupervisorAgent` + `WorkerAgent` (BaseAgent impls)                      | **Same as Rust — BaseAgent-based**                               |
| **Specialized agents**  | BaseAgent subclasses (188 files)                | Wrap Agent (composition)                                                 | **Deprecate subclass pattern, use composition**                  |
| **Delegate facade**     | Parallel stack, own loop + adapters + MCP       | `DelegateEngine` (composes Agent + TaodRunner + governance + PactEngine) | **`Delegate` composes BaseAgent + wrappers + governance**        |
| **TAOD loop**           | `delegate/loop.py` (AgentLoop)                  | `agent_engine/taod.rs` (TaodRunner)                                      | **`kaizen/core/agent_loop.py` (used by StreamingAgent wrapper)** |
| **Adapters**            | `delegate/adapters/` (separate)                 | `kailash-kaizen/src/llm/` (canonical)                                    | **`kaizen/providers/` (extracted from ai_providers.py)**         |
| **MCP client**          | 2 parallel clients                              | 1 client                                                                 | **1 client from packages/kailash-mcp/**                          |
| **Tool registry**       | JSON schemas (BaseAgent) + callables (Delegate) | Callables + JSON schemas unified                                         | **Unified ToolRegistry**                                         |

## Extension Points Comparison

### Python BaseAgent (7 extension points)

1. `_default_signature()` — Provide signature
2. `_default_strategy()` — Select strategy
3. `_generate_system_prompt()` — Customize prompt
4. `_validate_signature_output()` — Validate output
5. `_pre_execution_hook()` — Pre-execution
6. `_post_execution_hook()` — Post-execution
7. `_handle_error()` — Error handling

**Problem**: Capability fragmentation. Hard to reason about which agents have which capabilities. Subclasses override different points in inconsistent ways.

### Rust BaseAgent (0 extension points)

All via **composition wrappers**:

- `MonitoredAgent` wraps for cost
- `StreamingAgent` wraps for streaming
- `L3GovernedAgent` wraps for enforcement
- `StructuredOutput` is a separate component (field on `Agent`)
- Retry is in `StructuredOutput`, not `BaseAgent`
- Hooks are in wrappers, not the base trait

**Advantage**: Explicit, composable, no hidden behavior. You can stack wrappers indefinitely.

## The Convergence Target for Python

After Option B (slim BaseAgent, deprecate extension points), Python's kaizen should look like:

```python
# packages/kailash-kaizen/src/kaizen/core/base_agent.py
class BaseAgent(Node):
    """Minimal primitive contract. Matches Rust's BaseAgent trait semantically.

    Composes: LlmClient + ToolRegistry + AgentMemory + StructuredOutput + Signature.
    Extension points (deprecated in v2.x, removed in v3.0):
    - _default_signature() -> use signature= parameter instead
    - _default_strategy() -> use execution_mode= parameter instead
    - _generate_system_prompt() -> use system_prompt= parameter instead
    - _validate_signature_output() -> use signature validation automatically
    - _pre_execution_hook() -> use composition wrappers instead
    - _post_execution_hook() -> use composition wrappers instead
    - _handle_error() -> use composition wrappers instead
    """

    def __init__(self, config, signature=None, llm=None, tools=None, memory=None, ...):
        self._config = config
        self._signature = signature
        self._llm = llm or get_provider(config.model)           # from kaizen.providers
        self._tools = tools or ToolRegistry()                    # unified registry
        self._memory = memory or SessionMemory()
        self._structured_output = StructuredOutput.from_signature(signature) if signature else None
        # ... minimal init, delegates to primitive components

    def run(self, **inputs) -> Dict[str, Any]:
        """Workflow-composable execution. Returns Dict for compatibility with multi-agent patterns."""
        ...

    async def run_async(self, **inputs) -> Dict[str, Any]:
        """Async variant for FastAPI/Nexus."""
        ...

    # Node interface (workflow integration)
    def get_parameters(self) -> Dict[str, NodeParameter]: ...
    def to_workflow(self) -> Workflow: ...

# packages/kaizen-agents/src/kaizen_agents/streaming_agent.py
class StreamingAgent(BaseAgent):
    """Wraps any BaseAgent and emits events via AgentLoop (TAOD)."""

    def __init__(self, inner: BaseAgent, loop_config: Optional[AgentLoopConfig] = None):
        self._inner = inner
        self._loop = AgentLoop(inner, config=loop_config or AgentLoopConfig())

    async def run_stream(self, prompt: str) -> AsyncGenerator[DelegateEvent, None]:
        async for event in self._loop.run_turn(prompt):
            yield event

    # Also implements BaseAgent for patterns that want Dict
    def run(self, **inputs) -> Dict[str, Any]:
        events = asyncio.run(self._collect(**inputs))
        return events[-1].to_dict()

# packages/kaizen-agents/src/kaizen_agents/monitored_agent.py
class MonitoredAgent(BaseAgent):
    """Wraps any BaseAgent with cost tracking via kailash.trust.BudgetTracker."""

    def __init__(self, inner: BaseAgent, budget_usd: float, cost_config: Optional[CostConfig] = None):
        self._inner = inner
        self._tracker = CostTracker(cost_config or CostConfig.default())
        self._budget = BudgetTracker(limit=budget_usd)

    def run(self, **inputs) -> Dict[str, Any]:
        result = self._inner.run(**inputs)
        self._tracker.record_usage(result.get("model"), result.get("usage"))
        self._budget.check_and_deduct(self._tracker.last_cost())
        return result

# packages/kaizen-agents/src/kaizen_agents/l3_governed_agent.py
class L3GovernedAgent(BaseAgent):
    """Wraps any BaseAgent with PACT envelope enforcement."""

    def __init__(self, inner: BaseAgent, envelope: ConstraintEnvelope,
                 pact_engine: Optional[PactEngine] = None):
        self._inner = inner
        self._envelope = envelope
        self._pact = pact_engine

    def run(self, **inputs) -> Dict[str, Any]:
        # 1. Check governance verdict
        verdict = self._pact.evaluate(inputs, self._envelope)
        if verdict.blocked:
            raise GovernanceBlockedError(verdict.reason)
        if verdict.held:
            return self._pact.hold(inputs, verdict.reason)
        # 2. Execute inner agent
        return self._inner.run(**inputs)

# packages/kaizen-agents/src/kaizen_agents/delegate.py
class Delegate:
    """Engine facade: composes BaseAgent + wrappers + governance."""

    def __init__(self, model: str, *, signature=None, tools=None,
                 budget_usd=None, envelope=None, mcp_servers=None, ...):
        # Build the stack
        inner = BaseAgent(
            config=BaseAgentConfig(model=model),
            signature=signature,
            tools=tools or ToolRegistry(),
        )

        if mcp_servers:
            inner = inner.with_mcp_servers(mcp_servers)  # uses kailash_mcp.MCPClient

        if budget_usd:
            inner = MonitoredAgent(inner, budget_usd=budget_usd)

        if envelope:
            inner = L3GovernedAgent(inner, envelope=envelope)

        self._stack = StreamingAgent(inner)  # outermost wrapper for event streaming

    async def run(self, prompt: str) -> AsyncGenerator[DelegateEvent, None]:
        async for event in self._stack.run_stream(prompt):
            yield event

    def run_sync(self, prompt: str) -> str:
        return asyncio.run(self._run_blocking(prompt))
```

## Test Coverage Verification

**kailash-kaizen tests**: 8 test files in `/tests/`, includes phase7d_test.rs for EATP trust chain
**kaizen-agents tests**: 2 test files in `/tests/`, plus extensive inline tests in delegate_engine.rs, pact_engine.rs, governance modules, StreamingAgent, TaodRunner, Agent

**Observation**: Rust emphasizes inline `#[cfg(test)]` modules; Python is more integration-test-heavy.

## Key Insights for Python Convergence

1. **BaseAgent should be a minimal 2-method contract** (matches Rust)
2. **The concrete Agent is BaseAgent slimmed** (Option B confirmed)
3. **All capabilities are wrappers** (StreamingAgent, MonitoredAgent, L3GovernedAgent, SupervisorAgent, WorkerAgent)
4. **Wrappers themselves implement BaseAgent** — they can be stacked
5. **Delegate is the engine facade** that composes the stack internally
6. **Multi-agent patterns (Supervisor/Worker) are BaseAgent wrappers**, not a separate coordination layer
7. **The 7 Python extension points are the architectural smell** that needs to be removed
8. **Signatures, cost tracking, checkpointing, structured output, memory, tools** are all **composable primitives** that Agent holds as fields (or wrappers stack on top)

## Cargo Dependency Verification

**kaizen-agents → kailash-kaizen**: Confirmed in Cargo.toml:

```toml
[dependencies]
kailash-kaizen = { path = "../kailash-kaizen" }
kailash-pact = { path = "../kailash-pact" }
```

**No circular dependencies.** Clean layering:

```
kaizen-agents (orchestration)
    ↓
kailash-kaizen (SDK primitives: BaseAgent trait, LlmClient, tools, memory, cost, checkpoint, structured output, L3 core)
    ↓
kailash-pact (governance policy types)
kailash-core, kailash-value (foundation)
```

## Summary

**Rust's agent architecture is the convergence target.** Python should:

1. Slim `BaseAgent` from 3,698 lines to ~500 lines (a minimal primitive)
2. Deprecate the 7 extension points (v2.x shims, v3.0 removal)
3. Add composition wrappers: `StreamingAgent`, `MonitoredAgent`, `L3GovernedAgent`
4. Refactor `SupervisorAgent`/`WorkerAgent` to implement BaseAgent (not separate pattern classes)
5. Make `Delegate` a composition facade (not a parallel implementation)
6. Share primitives: `kailash-mcp`, `kaizen/providers/`, `kaizen/tools/registry.py`
7. Migrate ~600 tests to composition-based test setup (no subclassing of BaseAgent)

**Rust stays the same** — it's already correct.
