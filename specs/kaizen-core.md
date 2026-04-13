# Kailash Kaizen -- Domain Specification — Core

Version: 2.7.3
Package: `kailash-kaizen`
License: Apache-2.0
Owner: Terrene Foundation (Singapore CLG)

Parent domain: Kailash Kaizen AI agent framework. This file covers the architecture overview, BaseAgent, BaseAgentConfig, AgentLoop, CoreAgent, Kaizen framework class, global convenience functions, performance requirements, deprecated APIs, and invariants. See also `kaizen-signatures.md`, `kaizen-providers.md`, and `kaizen-advanced.md`.

This document is the authoritative domain-truth specification for the Kailash Kaizen AI agent framework. It covers every public class, method signature, configuration contract, edge case, and invariant that governs Kaizen behavior. Code that contradicts this spec is a bug; this spec that contradicts code is a documentation debt.

---

## 1. Architecture Overview

Kaizen is a signature-based AI agent framework built on the Kailash Core SDK. It provides three abstraction layers:

```
Layer 1 (Zero-Config)     Agent(model="gpt-4")
Layer 2 (Configuration)   Agent(model="gpt-4", agent_type="react", memory_turns=20)
Layer 3 (Expert Override)  Agent(model="gpt-4", custom_memory=RedisMemory())
```

Internal architecture:

```
kaizen (package root)
  __init__.py              Public API re-exports, global config functions
  agent.py                 Deprecated sync Agent wrapper (removed in 3.0.0)
  agent_config.py          AgentConfig dataclass (Layer 2 config for sync Agent)
  agent_types.py           Agent type presets (simple, react, cot, rag, autonomous, vision, audio)
  core/
    framework.py           Kaizen class (framework entry point)
    agents.py              Agent + AgentManager (CoreAgent, workflow compilation)
    base_agent.py          BaseAgent (universal agent with strategy execution, MCP, A2A)
    config.py              BaseAgentConfig, KaizenConfig
    agent_loop.py          AgentLoop (TAOD execution loop)
    mcp_mixin.py           MCPMixin (MCP tool discovery/execution)
    a2a_mixin.py           A2AMixin (Google A2A protocol)
    structured_output.py   JSON schema generation from signatures
    prompt_utils.py        System prompt generation from signatures
    workflow_generator.py  Workflow generation from agent config
  signatures/
    core.py                Signature, InputField, OutputField, SignatureMeta
    enterprise.py          Enterprise validators, composition, registry
    multi_modal.py         ImageField, AudioField
    patterns.py            ChainOfThought, ReAct, RAG, MultiAgent patterns
  providers/
    base.py                BaseAIProvider, LLMProvider, EmbeddingProvider, SPEC-02 protocols
    registry.py            PROVIDERS dict, get_provider(), get_provider_for_model()
    types.py               Message, ChatResponse, TokenUsage, ToolCall, StreamEvent
    errors.py              ProviderError hierarchy
    cost.py                CostTracker, ModelPricing, CostConfig
    llm/                   OpenAI, Anthropic, Google, Ollama, Azure, Docker, Perplexity, Mock
    embedding/             Cohere, HuggingFace
  strategies/
    base_strategy.py       ExecutionStrategy protocol
    single_shot.py         SingleShotStrategy
    async_single_shot.py   AsyncSingleShotStrategy
    multi_cycle.py         MultiCycleStrategy (ReAct, iterative)
    streaming.py           StreamingStrategy
    parallel_batch.py      ParallelBatchStrategy
    fallback.py            FallbackStrategy
    human_in_loop.py       HumanInLoopStrategy
    convergence.py         ConvergenceStrategy, TestDriven, Satisfaction, Hybrid
  memory/
    conversation_base.py   KaizenMemory abstract base
    buffer.py              BufferMemory
    persistent_buffer.py   PersistentBufferMemory
    summary.py             SummaryMemory
    vector.py              VectorMemory
    knowledge_graph.py     KnowledgeGraphMemory
    shared_memory.py       SharedMemoryPool
    enterprise.py          3-tier EnterpriseMemorySystem
  tools/
    types.py               ToolDefinition, ToolParameter, ToolResult, DangerLevel
  composition/
    dag_validator.py       validate_dag() -- cycle detection
    schema_compat.py       check_schema_compatibility()
    cost_estimator.py      estimate_cost()
    models.py              ValidationResult, CompatibilityResult, CostEstimate
    errors.py              CompositionError, CycleDetectedError, SchemaIncompatibleError
  cost/
    tracker.py             CostTracker (multi-modal, microdollar precision)
  optimization/
    engine.py              AutoOptimizationEngine, PerformanceTracker
    core.py                OptimizationEngine, strategies
    feedback.py            FeedbackSystem, AnomalyDetector, LearningEngine
    strategies.py          Bayesian, Genetic, RandomSearch
    dashboard.py           OptimizationDashboard
  audio/
    whisper_processor.py   WhisperProcessor (local Whisper STT)
  config/
    providers.py           ProviderConfig, auto-detection
```

### Unified Agent API (ADR-020)

The canonical import path is:

```python
from kaizen import Agent          # Resolves to kaizen_agents.Agent (async) if installed,
                                  # else kaizen.core.agents.Agent (CoreAgent fallback)
from kaizen import CoreAgent      # Always kaizen.core.agents.Agent
from kaizen import Kaizen         # Framework class
from kaizen import Signature, InputField, OutputField  # Signature system
```

The deprecated sync `Agent` in `kaizen.agent` emits `DeprecationWarning` on import and will be removed in 3.0.0. Do not import from `kaizen.agent` directly.

---

## 3. BaseAgent

`kaizen.core.base_agent.BaseAgent` is the universal agent class. All agent behavior flows through it.

### 3.1 Inheritance

```python
class BaseAgent(MCPMixin, A2AMixin, Node):
```

- `MCPMixin`: MCP tool discovery, execution, server exposure.
- `A2AMixin`: Google A2A protocol (agent cards, capabilities).
- `Node`: Kailash Core SDK Node base class (enables workflow composition).

### 3.2 Constructor

```python
def __init__(
    self,
    config: Any,                              # BaseAgentConfig or domain config (auto-converted)
    signature: Optional[Signature] = None,    # Uses _default_signature() if None
    strategy: Optional[Any] = None,           # Uses _default_strategy() if None
    memory: Optional[Any] = None,             # KaizenMemory instance
    shared_memory: Optional[Any] = None,      # SharedMemoryPool
    agent_id: Optional[str] = None,           # Auto-generated if None
    control_protocol: Optional[Any] = None,   # ControlProtocol for user interaction
    mcp_servers: Optional[List[Dict]] = None, # None = auto-connect builtin; [] = disable
    hook_manager: Optional[Any] = None,       # HookManager for lifecycle hooks
)
```

**Contracts:**

- `config` is auto-converted to `BaseAgentConfig` via `BaseAgentConfig.from_domain_config()` if not already an instance.
- `mcp_servers=None` auto-injects the builtin MCP server (12 tools) UNLESS `config.has_structured_output` is True (structured output is incompatible with function calling on some providers like Gemini).
- `mcp_servers=[]` explicitly disables all MCP tools.
- `agent_id` defaults to `f"agent_{id(self)}"` if not provided.
- The permission system is initialized from config: `PermissionPolicy`, `ExecutionContext`, `ToolApprovalManager`.
- Hooks are initialized from config if `hooks_enabled=True`.
- Mixins are applied dynamically based on config flags (logging, performance, error handling, batch processing, memory, transparency, validation).

### 3.3 Execution Methods

#### `run(**inputs) -> Dict[str, Any]`

Synchronous execution. Delegates to `AgentLoop.run_sync(self, **inputs)`.

**Parameters:**

- `**inputs`: Keyword arguments matching signature input field names.
- Special parameter: `session_id` (str) for memory persistence across calls.

**Returns:** Dict matching signature output field names.

#### `run_async(**inputs) -> Dict[str, Any]`

Asynchronous execution. Delegates to `AgentLoop.run_async(self, **inputs)`.

**Contracts:**

- Requires `use_async_llm=True` in configuration.
- Raises `ValueError` if `use_async_llm=False`.

### 3.4 Extension Points (7 total)

These are deprecated in v2.5.0 -- composition wrappers (StreamingAgent, MonitoredAgent, GovernedAgent) are preferred for new code.

| Method                               | Purpose                              | Default Behavior                                                  |
| ------------------------------------ | ------------------------------------ | ----------------------------------------------------------------- |
| `_default_signature()`               | Fallback signature                   | Returns generic input/output                                      |
| `_default_strategy()`                | Fallback strategy                    | `AsyncSingleShotStrategy` or `MultiCycleStrategy` based on config |
| `_generate_system_prompt()`          | System prompt from signature + tools | Builds prompt with field descriptions + discovered MCP tools      |
| `_validate_signature_output(output)` | Validate output shape                | Checks all output fields present                                  |
| `_pre_execution_hook(inputs)`        | Before execution                     | Logs execution start                                              |
| `_post_execution_hook(result)`       | After execution                      | Logs completion                                                   |
| `_handle_error(error, context)`      | Error handling                       | Logs error, returns error dict or re-raises                       |

### 3.5 Workflow Generation

```python
def to_workflow(self) -> WorkflowBuilder:
```

Generates a Core SDK workflow from the agent's signature and config. Adds a single `LLMAgentNode` with system prompt, model, provider, temperature, max_tokens, and response_format from config.

### 3.6 Convenience Methods

| Method                                                          | Signature  | Purpose                                   |
| --------------------------------------------------------------- | ---------- | ----------------------------------------- |
| `write_to_memory(content, tags, importance, segment, metadata)` | `-> None`  | Write insights to shared memory           |
| `extract_list(result, field_name, default)`                     | `-> List`  | Type-safe list extraction from LLM output |
| `extract_dict(result, field_name, default)`                     | `-> Dict`  | Type-safe dict extraction                 |
| `extract_float(result, field_name, default)`                    | `-> float` | Type-safe float extraction                |
| `extract_str(result, field_name, default)`                      | `-> str`   | Type-safe string extraction               |

### 3.7 Control Protocol

```python
async def ask_user_question(
    self,
    question: str,
    options: Optional[List[str]] = None,
    timeout: float = 60.0,
) -> str
```

Asks the user a question during execution via the configured ControlProtocol. Raises `RuntimeError` if no control protocol is configured.

---

## 4. BaseAgentConfig

`kaizen.core.config.BaseAgentConfig` is the dataclass for individual agent configuration.

### 4.1 Fields

**LLM Configuration:**

| Field                    | Type              | Default      | Description                                  |
| ------------------------ | ----------------- | ------------ | -------------------------------------------- |
| `llm_provider`           | `Optional[str]`   | `None`       | Provider name (auto-detected from model)     |
| `model`                  | `Optional[str]`   | `None`       | Model identifier                             |
| `temperature`            | `Optional[float]` | `0.1`        | Sampling temperature                         |
| `max_tokens`             | `Optional[int]`   | `None`       | Token limit                                  |
| `provider_config`        | `Optional[Dict]`  | `None`       | Provider-specific settings                   |
| `response_format`        | `Optional[Dict]`  | `None`       | Structured output config                     |
| `structured_output_mode` | `str`             | `"explicit"` | `"explicit"`, `"off"`, `"auto"` (deprecated) |
| `api_key`                | `Optional[str]`   | `None`       | Per-request API key override (BYOK)          |
| `base_url`               | `Optional[str]`   | `None`       | Per-request base URL override                |
| `use_async_llm`          | `bool`            | `False`      | Enable async LLM client                      |

**Strategy Configuration:**

| Field           | Type  | Default         | Description                         |
| --------------- | ----- | --------------- | ----------------------------------- |
| `strategy_type` | `str` | `"single_shot"` | `"single_shot"` or `"multi_cycle"`  |
| `max_cycles`    | `int` | `5`             | Max cycles for multi_cycle strategy |

**Feature Flags (Mixins):**

| Flag                       | Default | Mixin Applied     |
| -------------------------- | ------- | ----------------- |
| `logging_enabled`          | `True`  | `LoggingMixin`    |
| `performance_enabled`      | `True`  | `MetricsMixin`    |
| `error_handling_enabled`   | `True`  | `RetryMixin`      |
| `batch_processing_enabled` | `False` | `CachingMixin`    |
| `memory_enabled`           | `False` | `TimeoutMixin`    |
| `transparency_enabled`     | `False` | `TracingMixin`    |
| `mcp_enabled`              | `False` | `ValidationMixin` |

**Permission System:**

| Field              | Type              | Default                  | Description                   |
| ------------------ | ----------------- | ------------------------ | ----------------------------- |
| `permission_mode`  | `PermissionMode`  | `PermissionMode.DEFAULT` | Permission enforcement mode   |
| `budget_limit_usd` | `Optional[float]` | `None`                   | Max budget (None = unlimited) |
| `allowed_tools`    | `set`             | `set()`                  | Explicitly allowed tools      |
| `denied_tools`     | `set`             | `set()`                  | Explicitly denied tools       |
| `permission_rules` | `List`            | `[]`                     | Custom permission rules       |

**Hooks System:**

| Field             | Type            | Default | Description                          |
| ----------------- | --------------- | ------- | ------------------------------------ |
| `hooks_enabled`   | `bool`          | `False` | Enable hooks system                  |
| `hook_timeout`    | `float`         | `5.0`   | Timeout per hook execution (seconds) |
| `builtin_hooks`   | `List[str]`     | `[]`    | Built-in hooks to enable             |
| `hooks_directory` | `Optional[str]` | `None`  | Directory for filesystem hooks       |

**Trust / Posture (SPEC-04):**

| Field     | Type                     | Default | Description                                  |
| --------- | ------------------------ | ------- | -------------------------------------------- |
| `posture` | `Optional[AgentPosture]` | `None`  | Trust posture (immutable after construction) |

**Contracts:**

- `posture` is immutable after `__post_init__` completes. Attempting to reassign raises `AttributeError` with a message directing to `dataclasses.replace()`.
- String posture values (e.g., `"supervised"`) are auto-coerced to `AgentPosture` enum members.
- `provider_config` with a `"type"` key is auto-migrated to `response_format` with a deprecation warning.
- `has_structured_output` property returns True if `response_format` is not None and `structured_output_mode` is not `"off"`.

---

## 5. AgentLoop (TAOD Execution)

`kaizen.core.agent_loop.AgentLoop` encapsulates the Think/Act/Observe/Decide execution flow.

### 5.1 Execution Flow

```
1. Extract session_id from inputs
2. Load memory context (individual + shared)
3. Trigger PRE_EXECUTION hook
4. Call _pre_execution_hook(inputs)
5. Execute strategy (sync or async)
6. Call _post_execution_hook(result)
7. Trigger POST_EXECUTION hook
8. Save memory turn (individual + shared insights)
9. Return result
```

### 5.2 Static Methods

```python
AgentLoop.run_sync(agent, **inputs) -> Dict[str, Any]
AgentLoop.run_async(agent, **inputs) -> Dict[str, Any]  # async
```

Both methods use duck typing for the `agent` parameter. The agent must provide: `hook_manager`, `agent_id`, `memory`, `shared_memory`, `signature`, `strategy`, `config`, and the 7 extension point methods.

### 5.3 Async/Sync Bridge

```python
def run_async_hook(coro) -> None:
```

Handles async/sync boundary for hook triggers:

- Inside an existing event loop: runs in a `ThreadPoolExecutor` with 1 worker, 5s timeout.
- No event loop: uses `asyncio.run()`.

### 5.4 Memory Integration

- `_load_memory_context(agent, inputs, session_id)`: Loads individual memory via `agent.memory.load_context(session_id)` and shared memory via `agent.shared_memory.read_relevant()`. Injects as `_memory_context` and `_shared_insights` keys in inputs.
- `_save_memory_turn(agent, inputs, processed_inputs, final_result, session_id)`: Saves conversation turn to individual memory, writes shared insights if `_write_insight` key is present in result.

---

## 6. CoreAgent (kaizen.core.agents.Agent)

`kaizen.core.agents.Agent` is a lightweight agent that compiles to a Core SDK workflow. It is the fallback when `kaizen-agents` is not installed.

### 6.1 Constructor

```python
def __init__(
    self,
    agent_id: str,
    config: Dict[str, Any],
    signature: Optional[Any] = None,
    kaizen_instance: Optional[Kaizen] = None,
)
```

**Contracts:**

- `config` is a plain dict with keys: `model`, `temperature`, `max_tokens`, `timeout`, `generation_config`, and any valid `LLMAgentNode` parameter.
- Default config: `model="gpt-3.5-turbo"`, `temperature=0.7`, `max_tokens=1000`, `timeout=30`.

### 6.2 Workflow Compilation

```python
def compile_workflow(self) -> WorkflowBuilder:
```

Creates a `WorkflowBuilder` with a single `LLMAgentNode`. Compiles once and caches. Parameters are split between top-level node params and `generation_config` sub-dict.

Valid top-level params forwarded to LLMAgentNode: `provider`, `messages`, `system_prompt`, `tools`, `conversation_id`, `memory_config`, `mcp_servers`, `mcp_context`, `rag_config`, `streaming`, `max_retries`, `auto_discover_tools`, `auto_execute_tools`, `tool_execution_config`.

### 6.3 Execution

CoreAgent provides structured execution via `execute(**kwargs)` and `execute_async(**kwargs)`, plus pattern-specific methods (`execute_react()`, `execute_cot()`).

---

## 7. Kaizen Framework Class

`kaizen.core.framework.Kaizen` is the main framework entry point.

### 7.1 Constructor

```python
def __init__(
    self,
    config: Optional[KaizenConfig] = None,
    memory_enabled: bool = False,
    optimization_enabled: bool = False,
    security_config: Optional[Dict[str, Any]] = None,
    monitoring_enabled: bool = False,
    debug: bool = False,
    lazy_runtime: bool = False,
    **kwargs,
)
```

**Contracts:**

- Unknown kwargs raise `TypeError` with the invalid parameter names.
- Passing `runtime=...` raises `TypeError` with a specific message: "Framework does not accept 'runtime' parameter."
- If `config` is None, a `KaizenConfig` is constructed from valid kwargs.

### 7.2 Key Methods

```python
def create_agent(self, agent_id: str, config: Dict = None, **kwargs) -> Agent
def execute(self, workflow) -> Tuple[Dict, str]          # (results, run_id)
def create_signature(self, signature_str: str) -> Signature
```

---

## 25. Global Convenience Functions

```python
import kaizen

# Create agent with resolved global config
agent = kaizen.create_agent("processor", config={"model": "gpt-4"})

# Module-level configuration
kaizen.configure(signature_programming_enabled=True)
kaizen.load_config_from_env("KAIZEN_")
kaizen.load_config_from_file("kaizen.yaml")
kaizen.auto_discover_config()
kaizen.get_resolved_config()
kaizen.clear_global_config()
```

---

## 26. Performance Requirements

| Operation                | Target                                         |
| ------------------------ | ---------------------------------------------- |
| Package import           | <100ms                                         |
| Signature compilation    | <50ms for complex signatures                   |
| Signature validation     | <10ms for type checking                        |
| Agent execution overhead | <200ms for signature-based workflows           |
| Memory usage             | <10MB additional overhead for signature system |
| Concurrent signatures    | 100+ simultaneous executions                   |

Performance is achieved via lazy loading:

- `WorkflowBuilder` imported only when `compile_workflow()` is called.
- `Pydantic` lazy-imported to avoid 1.8s import delay.
- `agents.py` (2599 lines, 95ms import) lazy-loaded in `framework.py`.
- Signatures module lazy-loaded until first use.

---

## 27. Deprecated APIs

| API                                    | Deprecated Since | Replacement                                                          | Removed In |
| -------------------------------------- | ---------------- | -------------------------------------------------------------------- | ---------- |
| `kaizen.agent.Agent` (sync wrapper)    | 2.3.0            | `from kaizen import Agent` or `from kaizen_agents import Agent`      | 3.0.0      |
| BaseAgent extension points (7 methods) | 2.5.0            | Composition wrappers (StreamingAgent, MonitoredAgent, GovernedAgent) | --         |
| `provider_config` with `"type"` key    | current          | `response_format` field                                              | --         |
| `structured_output_mode="auto"`        | current          | `"explicit"` or `"off"`                                              | --         |

---

## 28. Invariants

1. **Signature field immutability**: `_signature_inputs`, `_signature_outputs`, `_signature_intent`, `_signature_guidelines` are set at class creation time by `SignatureMeta` and must not be modified at runtime.
2. **Guidelines copy**: `Signature.guidelines` property returns a copy to prevent mutation of the class-level list.
3. **Posture immutability**: `BaseAgentConfig.posture` cannot be reassigned after `__post_init__`.
4. **Budget precision**: Cost tracking uses integer microdollars internally (1 USD = 1,000,000) to prevent floating-point accumulation errors.
5. **NaN/Inf rejection**: `CostTracker` rejects NaN and Inf values for both `budget_limit` and `cost` parameters.
6. **Record bounding**: All deque-based record stores use `maxlen=10_000` to prevent unbounded memory growth.
7. **MCP/structured output mutual exclusion**: When `has_structured_output` is True, MCP auto-discovery is suppressed.
8. **Provider error wrapping**: Provider-specific exceptions are always wrapped into the `ProviderError` hierarchy before surfacing to consumers.
9. **DAG validation stack safety**: Uses iterative DFS (not recursive) to handle compositions up to `max_agents=1000` without Python stack overflow.
10. **API key redaction**: `ProviderConfig.__repr__` redacts `api_key` to prevent leakage in logs and tracebacks.
