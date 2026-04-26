# Kailash Kaizen -- Domain Specification — Advanced Features

Version: 2.13.1
Package: `kailash-kaizen`

Parent domain: Kailash Kaizen AI agent framework. This file covers cost tracking, composition system, optimization system, audio support, configuration system, agent type presets, Google A2A protocol, permission system, hook system, and trust/posture. See also `kaizen-core.md`, `kaizen-signatures.md`, and `kaizen-providers.md`.

---

## 12. Cost Tracking

### 12.1 Provider-Level Cost Tracking (kaizen.providers.cost)

Thread-safe accumulator for LLM token costs:

```python
tracker = CostTracker(config=CostConfig(
    enabled=True,
    pricing={
        "gpt-4o": ModelPricing(prompt_cost_per_1k=0.005, completion_cost_per_1k=0.015),
        "gpt-4o-mini": ModelPricing(prompt_cost_per_1k=0.00015, completion_cost_per_1k=0.0006),
    }
))

cost = tracker.record("gpt-4o", prompt_tokens=500, completion_tokens=100)
print(tracker.total_cost_usd)
```

**Contracts:**

- Thread-safe via `threading.Lock`.
- Records bounded to 10,000 entries (deque maxlen).
- Returns incremental cost per `record()` call.

### 12.2 Multi-Modal Cost Tracking (kaizen.cost.tracker)

Tracks usage across providers and modalities with budget management:

```python
tracker = CostTracker(
    budget_limit=10.0,        # $10 max
    alert_threshold=0.8,      # Alert at 80%
    warn_on_openai_usage=False,
    enable_cost_tracking=True,
)

tracker.record_usage(
    provider="openai",
    modality="text",
    model="gpt-4o",
    cost=0.05,
    input_size=None,
    duration=None,
)
```

**Contracts:**

- Costs stored internally as integer microdollars (1 USD = 1,000,000 microdollars) to prevent floating-point precision loss. Cross-SDK alignment with kailash-rs#38.
- `budget_limit` must be finite and non-negative. NaN/Inf values raise `ValueError` (trust-plane rule 3).
- `cost` values must be finite and non-negative. NaN/Inf raise `ValueError`.
- Records bounded to 10,000 entries (deque maxlen).
- Budget alerts fire once when threshold is crossed.
- `on_alert` callback receives `CostAlert` objects.

### 12.3 UsageRecord

```python
@dataclass
class UsageRecord:
    provider: str       # 'ollama', 'openai', etc.
    modality: str       # 'vision', 'audio', 'text', 'mixed'
    model: str
    cost: float         # USD
    timestamp: datetime
    input_size: Optional[int] = None   # Bytes (vision)
    duration: Optional[int] = None     # Seconds (audio)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

---

## 13. Composition System

### 13.1 DAG Validation

```python
from kaizen.composition import validate_dag

result: ValidationResult = validate_dag(
    agents=[
        {"name": "researcher", "inputs_from": []},
        {"name": "writer", "inputs_from": ["researcher"]},
        {"name": "editor", "inputs_from": ["writer"]},
    ],
    max_agents=1000,  # DoS prevention
)

assert result.is_valid
print(result.topological_order)  # ['researcher', 'writer', 'editor']
```

**Contracts:**

- Uses iterative DFS with 3-color marking (WHITE/GRAY/BLACK) for cycle detection. Avoids Python stack overflow on deep chains.
- `max_agents` guard prevents DoS via unbounded composition size. Raises `CompositionError` if exceeded.
- Duplicate agent names raise `CompositionError`.
- Missing dependencies generate warnings (non-fatal) but do not invalidate the DAG.
- Returns `topological_order` (valid execution order) when no cycles exist.

### 13.2 Schema Compatibility

```python
from kaizen.composition import check_schema_compatibility

result: CompatibilityResult = check_schema_compatibility(
    output_schema=researcher_signature,
    input_schema=writer_signature,
)

assert result.compatible
print(result.mismatches)   # Field-level incompatibilities
print(result.warnings)     # Non-fatal issues
```

### 13.3 Cost Estimation

```python
from kaizen.composition import estimate_cost

estimate: CostEstimate = estimate_cost(agents=[...])
print(estimate.estimated_total_microdollars)  # Total in microdollars
print(estimate.per_agent)                      # Per-agent breakdown
print(estimate.confidence)                     # "high", "medium", "low"
```

### 13.4 Composition Errors

```python
class CompositionError(Exception):
    def __init__(self, message: str, details: dict = None): ...

class CycleDetectedError(CompositionError): ...
class SchemaIncompatibleError(CompositionError): ...
```

---

## 14. Optimization System

### 14.1 AutoOptimizationEngine

Main coordination engine for automatic optimization:

```python
from kaizen.optimization import AutoOptimizationEngine

engine = AutoOptimizationEngine()
session = engine.create_session(signature=my_signature)
```

### 14.2 Optimization Strategies

| Strategy                       | Description                                |
| ------------------------------ | ------------------------------------------ |
| `BayesianOptimizationStrategy` | Bayesian optimization for parameter tuning |
| `GeneticOptimizationStrategy`  | Genetic algorithms for exploration         |
| `RandomSearchStrategy`         | Random search baseline                     |

### 14.3 Feedback System

```python
from kaizen.optimization import FeedbackSystem, FeedbackEntry, FeedbackType

system = FeedbackSystem()
system.add_feedback(FeedbackEntry(
    type=FeedbackType.QUALITY,
    score=0.85,
    metadata={"latency_ms": 250},
))
```

Components:

- `FeedbackSystem`: Collects and aggregates feedback.
- `AnomalyDetector`: Detects quality/performance anomalies.
- `LearningEngine`: Continuous learning from feedback.
- `QualityMetrics`: Quality measurement and tracking.

### 14.4 Performance Tracker

```python
from kaizen.optimization import PerformanceTracker

tracker = PerformanceTracker()
# Tracks latency, token usage, quality scores across executions
```

### 14.5 Optimization Dashboard

```python
from kaizen.optimization import OptimizationDashboard

dashboard = OptimizationDashboard()
metrics = dashboard.get_metrics()
```

---

## 15. Audio Support

### 15.1 WhisperProcessor

Local speech-to-text using `faster-whisper`:

```python
from kaizen.audio import WhisperProcessor, WhisperConfig

config = WhisperConfig(
    model_size="base",       # tiny, base, small, medium, large, large-v2, large-v3
    device="cpu",            # cpu or cuda
    compute_type="int8",     # int8, float16, float32
    language=None,           # None for auto-detect
    task="transcribe",       # transcribe or translate
    beam_size=5,
    best_of=5,
    temperature=0.0,
)

processor = WhisperProcessor(config)
result = processor.transcribe("audio.mp3")
print(result["text"])
```

**Contracts:**

- Requires `faster-whisper` optional dependency. Emits `warnings.warn()` if not installed.
- Raises `RuntimeError` on transcribe() if `faster-whisper` is not available.
- Model is lazy-loaded on first `transcribe()` call.
- Invalid `model_size` raises `ValueError` with valid options.

---

## 16. Configuration System

### 16.1 KaizenConfig

Framework-level configuration (used by `Kaizen` class):

```python
@dataclass
class KaizenConfig:
    signature_programming_enabled: bool = True
    mcp_integration_enabled: bool = True
    multi_agent_coordination: bool = True
    transparency_enabled: bool = False
    # ... additional framework config fields
```

### 16.2 Global Configuration Functions

```python
import kaizen

# Set global config
kaizen.configure(signature_programming_enabled=True, debug=True)

# Load from environment
config = kaizen.load_config_from_env(prefix="KAIZEN_")

# Load from file (YAML, JSON, TOML)
config = kaizen.load_config_from_file("kaizen.yaml")

# Auto-discover config files
# Searches: ./kaizen.{toml,yaml,yml,json}, ~/.config/kaizen/, ~/.kaizen/, /etc/kaizen/
config_file = kaizen.auto_discover_config()

# Get resolved config (file < env < global < explicit)
config = kaizen.get_resolved_config(explicit_config={"debug": True})

# Clear all global config
kaizen.clear_global_config()
```

**Precedence (lowest to highest):**

1. File configuration
2. Environment variables
3. Global configuration (`kaizen.configure()`)
4. Explicit parameters

### 16.3 ProviderConfig

```python
@dataclass
class ProviderConfig:
    provider: ProviderType
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: int = 30
    max_retries: int = 3
```

**Contracts:**

- `api_key` is redacted in `__repr__` to prevent leakage in logs/tracebacks.
- Empty/whitespace-only `api_key` raises `ConfigurationError`.

### 16.4 Provider Auto-Detection

Provider is auto-detected from model name in `AgentConfig._detect_provider_from_model()`:

| Model pattern                           | Detected provider  |
| --------------------------------------- | ------------------ |
| Contains `gpt` or `davinci`             | `openai`           |
| Contains `claude`                       | `anthropic`        |
| Contains `llama`, `mistral`, `bakllava` | `ollama`           |
| Contains `gemini`                       | `google`           |
| Unknown                                 | `openai` (default) |

Valid providers: `openai`, `azure`, `anthropic`, `ollama`, `docker`, `cohere`, `huggingface`, `google`, `gemini`, `perplexity`, `pplx`, `mock`.

Invalid provider names raise `ValueError` with the list of valid providers. Empty string provider raises `ValueError`.

---

## 17. Agent Type Presets

Pre-defined configurations for common agent patterns:

| Type         | Strategy                  | Tools | Memory | Special                            |
| ------------ | ------------------------- | ----- | ------ | ---------------------------------- |
| `simple`     | `AsyncSingleShotStrategy` | No    | Yes    | Basic Q&A                          |
| `react`      | `ReActStrategy`           | Yes   | Yes    | max_iterations=10, show_reasoning  |
| `cot`        | `ChainOfThoughtStrategy`  | No    | Yes    | show_reasoning                     |
| `rag`        | `RAGStrategy`             | Yes   | Yes    | retrieval_backend="semantic"       |
| `autonomous` | `AutonomousStrategy`      | Yes   | Yes    | enable_planning, max_iterations=20 |
| `vision`     | `VisionStrategy`          | No    | Yes    | enable_multimodal                  |
| `audio`      | `AudioStrategy`           | No    | Yes    | enable_multimodal                  |

Each preset includes a default `Signature` subclass:

- `SimpleQASignature`: prompt -> answer
- `ChainOfThoughtSignature`: prompt -> reasoning, answer
- `ReActSignature`: prompt -> thought, action, observation, answer
- `RAGSignature`: query -> retrieved_context, answer
- `AutonomousSignature`: task -> plan, execution, result
- `VisionSignature`: image, question -> answer
- `AudioSignature`: audio, language -> transcription

---

## 19. Google A2A Protocol

BaseAgent supports Google's Agent-to-Agent protocol via `A2AMixin`.

### 19.1 Agent Card Generation

```python
card = agent.to_a2a_card()
# Returns A2AAgentCard with:
#   agent_id, agent_name, agent_type, version,
#   primary_capabilities, secondary_capabilities,
#   collaboration_style, performance, resources,
#   description, tags, specializations
```

### 19.2 Supporting Types

```python
A2AAgentCard           # Full agent capability card
Capability             # Individual capability
CapabilityLevel        # Capability proficiency level
CollaborationStyle     # How the agent prefers to collaborate
PerformanceMetrics     # Agent performance data
ResourceRequirements   # Compute/memory requirements
A2ATask                # Task for inter-agent delegation
TaskState              # pending, running, completed, failed
TaskPriority           # low, normal, high, urgent
TaskValidator          # Task validation
Insight                # Agent insight/observation
InsightType            # Type of insight
TaskIteration          # Iteration within a task
```

### 19.3 Factory Functions

```python
card = create_research_agent_card(...)
card = create_coding_agent_card(...)
card = create_qa_agent_card(...)

task = create_research_task(...)
task = create_implementation_task(...)
task = create_validation_task(...)
```

---

## 22. Permission System

### 22.1 Execution Context

```python
@dataclass
class ExecutionContext:
    mode: PermissionMode
    budget_limit: Optional[float]
    allowed_tools: set
    denied_tools: set
    rules: List[PermissionRule]
```

### 22.2 Permission Policy

`PermissionPolicy` evaluates whether a tool call is allowed based on the execution context, allowed/denied sets, and custom rules.

### 22.3 Tool Approval Manager

`ToolApprovalManager` requests human approval for tools that require it, using the configured ControlProtocol.

---

## 23. Hook System

### 23.1 HookEvent

Events that trigger hooks during the execution lifecycle:

- `PRE_EXECUTION` / `POST_EXECUTION`
- `PRE_MEMORY_LOAD` / `POST_MEMORY_LOAD`
- `PRE_MEMORY_SAVE` / `POST_MEMORY_SAVE`

### 23.2 HookManager

```python
manager = HookManager()
manager.register(HookEvent.PRE_EXECUTION, my_hook)
await manager.trigger(HookEvent.PRE_EXECUTION, agent_id="agent_1", data={...})
```

**Contracts:**

- Hook failures are logged but do not halt execution (swallowed in `_trigger_hook_sync` / `_trigger_hook_async`).
- Hook timeout is configurable via `hook_timeout` in BaseAgentConfig (default: 5.0s).
- `hooks_directory` enables filesystem-based hook discovery (`.kaizen/hooks/`).

---

## 24. Trust and Posture (SPEC-04)

### 24.1 AgentPosture

```python
from kailash.trust.posture import AgentPosture

# Valid postures
AgentPosture.SUPERVISED
AgentPosture.AUTONOMOUS
# etc.
```

### 24.2 Posture Immutability

`BaseAgentConfig.posture` is immutable after `__post_init__` completes. Attempting to reassign raises:

```
AttributeError: BaseAgentConfig.posture is immutable after construction
(SPEC-04 S10.3). Use dataclasses.replace() to create a new config with
a different posture.
```

### 24.3 Governance Envelope

`AgentConfig.envelope` accepts a PACT `ConstraintEnvelopeConfig` that governs agent authority. When set, downstream systems (TAOD runner, tool executor, delegation) enforce constraints. When absent, no envelope enforcement is applied (L0-L2 backward-compatible).
