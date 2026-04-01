# Kaizen Integration Points

## Purpose

Research how kailash-ml agents will use Kaizen's agent infrastructure (BaseAgent, Signature, Delegate pattern), and analyze the circular dependency resolution strategy.

## Kaizen Architecture Summary

Kaizen (`packages/kailash-kaizen/` + `packages/kaizen-agents/`) provides:

1. **Signature system** (`kaizen.signatures.core`): Declarative I/O field specifications (`InputField`, `OutputField`) that describe what the LLM should reason about
2. **BaseAgent** (`kaizen.core`): Base class for agents that use Signatures for LLM calls
3. **Delegate** (`kaizen_agents.delegate`): High-level autonomous agent facade with progressive governance layers (minimal -> configured -> governed)
4. **Pipeline/Router** (`kaizen.orchestration.pipeline`): Multi-agent routing via LLM reasoning
5. **AgentRegistry** (`kaizen.core.registry`): Agent registration for discovery and scaling
6. **Tool system**: Function-based tools that agents can invoke (dumb data endpoints per `rules/agent-reasoning.md`)

## Integration Point 1: ML Agent Signatures

All 6 kailash-ml agents (DataScientist, FeatureEngineer, ModelSelector, ExperimentInterpreter, DriftAnalyst, RetrainingDecision) follow the same pattern:

```python
# In kailash_ml/agents/data_scientist.py
from kaizen.signatures.core import Signature, InputField, OutputField

class DataScientistSignature(Signature):
    """Analyze a dataset and formulate an ML strategy."""
    data_profile: str = InputField(description="Statistical profile from DataExplorer")
    ...
    confidence: float = OutputField(description="Confidence (0-1)")
```

**Key finding**: Kaizen's Signature system supports `str`, `float`, `list[str]`, `list[dict]`, and other types as OutputFields. The `confidence: float` output is a standard pattern -- no special handling needed.

**Import dependency**: This requires `from kaizen.signatures.core import Signature, InputField, OutputField`. This import is gated behind `try/except ImportError` with a clear message: "Install kailash-ml[agents] to use ML agents."

## Integration Point 2: Delegate Pattern for Agent Execution

The architecture specifies that all ML agents use the `Delegate` pattern rather than raw BaseAgent subclassing or direct LLM calls.

**Delegate** (`kaizen_agents.delegate.delegate.Delegate`) provides:

- Progressive disclosure: minimal (just a model name) -> configured (tools, system prompt) -> governed (budget cap)
- `budget_usd` parameter for cost control (aligns with Guardrail 2: `max_llm_cost_usd`)
- Tool registry integration
- Streaming event-based execution

**How ML agents would use Delegate**:

```python
# Agent-augmented AutoML
delegate = Delegate(
    model=os.environ["LLM_MODEL"],
    tools=ml_tool_registry,
    budget_usd=spec.max_llm_cost_usd,
)

async for event in delegate.run(
    f"Analyze this data profile and suggest models: {data_profile}"
):
    if isinstance(event, DelegateEvent):
        # Process suggestion
```

**Concern**: The Delegate pattern is stateless per-run. ML agents may need multi-turn reasoning (e.g., DataScientistAgent profiles data, then uses the profile to suggest features). This can be handled by:

1. Passing accumulated context as input fields (preferred -- maintains LLM-first principle)
2. Using Delegate's tool system to persist and retrieve intermediate state

## Integration Point 3: Agent Tools (Dumb Data Endpoints)

Per `rules/agent-reasoning.md`, tools must be dumb data endpoints. kailash-ml agent tools:

```python
# kailash_ml/agents/tools.py

async def profile_data(dataset_ref: str) -> dict:
    """Fetch statistical profile for a dataset. No decisions."""
    # Calls DataExplorer.profile() and returns raw stats
    ...

async def get_column_stats(dataset_ref: str, column: str) -> dict:
    """Fetch per-column statistics. No decisions."""
    ...

async def compute_feature(dataset_ref: str, expression: str) -> dict:
    """Compute a polars expression on the dataset. No decisions."""
    ...
```

**Pattern**: Each tool is a thin wrapper around an existing kailash-ml engine method. The tool fetches data; the LLM (via Signature) reasons about what to do with it.

**Registration**: Tools are registered in a `ToolRegistry` and injected into the Delegate at construction.

## Integration Point 4: Circular Dependency Resolution

### The problem

```
kailash-ml ---needs---> kailash-kaizen  (for agent Signatures, Delegate)
kailash-kaizen ---needs---> kailash-ml  (for ML-aware tools: predict, get_metrics)
```

### The solution: kailash-ml-protocols

```
kailash-ml-protocols (~50KB, no ML deps)
  - MLToolProtocol: predict(), get_metrics(), trigger_retrain()
  - AgentInfusionProtocol: suggest_model(), suggest_features(), interpret_results()
  - Shared data contracts: FeatureSchema, ModelSignature, MetricSpec
```

**kailash-ml** implements `MLToolProtocol` and optionally consumes `AgentInfusionProtocol`.
**kailash-kaizen** optionally implements `AgentInfusionProtocol` and optionally consumes `MLToolProtocol`.

Neither depends on the other at install time. Runtime discovery via `try/except ImportError`.

### Critical analysis of this approach

**Strengths**:

- Clean dependency DAG -- no circular pip installs
- Protocol-based (structural typing via `@runtime_checkable`) -- duck typing, no inheritance coupling
- Thin package (~50KB) with zero ML dependencies

**Weaknesses**:

- A third package to maintain, version, release, and test
- Protocol evolution requires coordinating across 3 packages
- Users must install `kailash-ml-protocols` even if they never use agents (it is a base dependency of kailash-ml)

**Assessment**: The protocol package approach is the standard Python solution for circular dependencies. The alternative (conditional imports everywhere, no type safety) is worse. The ~50KB size means the cost is negligible.

### kailash-align dependency on kailash-ml-protocols

kailash-align (8th framework) depends on kailash-ml for `ModelRegistry` and `AdapterRegistry`. It also uses `kailash-ml-protocols` for type contracts. The protocol package serves double duty: breaking the kailash-ml <-> kailash-kaizen cycle AND providing shared types for kailash-align.

## Integration Point 5: Agent Guardrail Implementation

The 5 guardrails map to specific Kaizen/platform features:

| Guardrail              | Implementation                                               |
| ---------------------- | ------------------------------------------------------------ |
| 1. Confidence scores   | `confidence: float` OutputField on every Signature           |
| 2. Cost budget         | `Delegate(budget_usd=...)` + `LLMCostTracker`                |
| 3. Human approval gate | Custom `PendingApproval` class; `auto_approve=False` default |
| 4. Baseline comparison | Algorithmic path always runs alongside agent path            |
| 5. Audit trail         | DataFlow `MLAgentAuditLog` model via Express API             |

**Guardrail 2 detail**: The Delegate already supports `budget_usd`. kailash-ml adds an `LLMCostTracker` that tallies token-based costs across multiple Delegate runs within one AutoML/DataExplorer/FeatureEngineer invocation. If total exceeds `max_llm_cost_usd`, the engine falls back to pure algorithmic mode.

**Guardrail 3 detail**: This is NOT a Kaizen feature -- it is a kailash-ml application-layer pattern. When `auto_approve=False`, the engine returns a `PendingApproval` object instead of executing the agent's recommendation. The caller must call `approval.approve()` or `approval.reject()`.

## Risks

1. **Delegate API stability**: kailash-ml depends on Delegate's constructor signature (`model`, `tools`, `budget_usd`). If Delegate changes, kailash-ml's agent wiring breaks. Mitigation: pin kailash-kaizen version.
2. **Signature field type support**: The `list[dict]` output type (used by ModelSelectorAgent) needs verification that Kaizen's Signature system handles it correctly for LLM output parsing.
3. **Cost tracking accuracy**: Token-based cost estimation (for Guardrail 2) depends on model pricing. This must be configurable, not hardcoded. The `rules/env-models.md` already requires model names from `.env`.
4. **Multi-agent coordination**: If an AutoML session uses DataScientistAgent -> ModelSelectorAgent -> ExperimentInterpreterAgent in sequence, context must be passed between runs. The Delegate is stateless per-run, so accumulated context must be explicitly threaded through input fields.
