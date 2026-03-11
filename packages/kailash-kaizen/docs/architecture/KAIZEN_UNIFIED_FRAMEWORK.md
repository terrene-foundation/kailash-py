# Kaizen Unified Framework - User-Focused Architecture

**Status**: Proposed
**Date**: 2025-10-26
**Purpose**: Coherent user-focused framework for single agents and multi-agent orchestration

---

## Executive Summary

Kaizen provides a **2-layer architecture** for building AI systems:

1. **Layer 1: Single Agents** - Individual AI agents with various execution strategies
2. **Layer 2: Orchestration** - Multi-agent patterns for complex workflows

Each layer has clear responsibilities and a seamless user experience.

---

## Part 1: Understanding the Current Structure

### What is "Strategy"?

**Strategy = HOW the agent executes (execution method)**

Current strategies in `kaizen/strategies/`:
- `AsyncSingleShotStrategy` - Execute once and return (simple Q&A)
- `MultiCycleStrategy` - Execute iteratively until convergence (ReAct, Planning)
- `ChainOfThoughtStrategy` - Execute with reasoning steps (CoT)
- More strategies can be added for different execution patterns

**Key Insight**: Strategy is **orthogonal** to agent type. Any agent can use any strategy.

Example:
```python
# Same agent type (Q&A), different strategies:
simple_agent = Agent(agent_type="simple", strategy=AsyncSingleShotStrategy())  # One-shot
iterative_agent = Agent(agent_type="simple", strategy=MultiCycleStrategy())    # Multi-cycle
```

### What is "Agent Type"?

**Agent Type = WHAT the agent does (behavior pattern)**

Current agent types should map to **single-agent patterns** from the research:
- `simple` - Direct Q&A
- `reflection` - Self-critique and refinement
- `tool_use` - External tool integration
- `react` - Reasoning + Acting cycles
- `planning` - Plan → Execute → Verify
- `pev` - Planner-Executor-Verifier
- `tree_of_thoughts` - Explore multiple reasoning paths
- ... (custom types via registration)

### Current Registration: `@register_node()`

**Existing mechanism** (already works!):
```python
from kailash.nodes.base import register_node, NodeMetadata

@register_node()
class MyCustomAgent(BaseAgent):
    metadata = NodeMetadata(
        name="MyCustomAgent",
        description="My custom agent pattern",
        version="1.0.0",
        tags={"ai", "kaizen", "custom"},
    )

    def __init__(self, ...):
        super().__init__(
            config=config,
            signature=MySignature(),
            strategy=MultiCycleStrategy(),
        )
```

**Problem**: This only registers for WorkflowBuilder/Studio, not for `agent_type` parameter!

---

## Part 2: Proposed Unified Framework

### Layer 1: Single Agents

#### **User Journey**:
```
1. Choose from built-in agents → Agent(agent_type="react")
2. Customize own agent → Create class + register
3. Use immediately → agent.run("task")
```

#### **Architecture**:

```
kaizen/
├── agent.py                    # Unified Agent (user entry point)
├── agent_config.py             # Configuration system
├── agent_types.py              # Agent type registry + presets
├── smart_defaults.py           # Smart defaults manager
├── rich_output.py              # Console UX
│
├── agents/
│   ├── specialized/            # Pre-built single agents
│   │   ├── simple_qa.py        # ✅ Direct Q&A
│   │   ├── reflection.py       # ❌ TODO: Self-critique pattern
│   │   ├── react.py            # ✅ ReAct pattern
│   │   ├── planning.py         # ❌ TODO: Planning pattern
│   │   ├── pev.py              # ❌ TODO: PEV pattern
│   │   ├── tree_of_thoughts.py # ❌ TODO: ToT pattern
│   │   └── ...
│   └── registry.py             # NEW: Agent registration system
│
└── strategies/                 # Execution strategies (HOW)
    ├── single_shot.py          # ✅ One execution
    ├── multi_cycle.py          # ✅ Iterative execution
    ├── chain_of_thought.py     # ✅ Reasoning steps
    └── ...
```

#### **Dual Registration System**:

**Registration Type 1: For WorkflowBuilder/Studio** (existing)
```python
from kailash.nodes.base import register_node

@register_node()  # Makes agent discoverable to Core SDK
class ReActAgent(BaseAgent):
    ...
```

**Registration Type 2: For agent_type Parameter** (NEW)
```python
from kaizen.agents.registry import register_agent_type

# Auto-register when module is imported
register_agent_type(
    name="react",
    agent_class=ReActAgent,
    description="Reasoning + Acting cycles",
    default_strategy=MultiCycleStrategy,
    preset_config={
        "max_cycles": 10,
        "confidence_threshold": 0.7,
    }
)
```

#### **Proposed agents/registry.py**:

```python
"""
Agent Type Registration System

Allows users to register custom agents for use with agent_type parameter.
"""

from dataclasses import dataclass
from typing import Dict, Type, Any, Optional, Callable
from kaizen.core.base_agent import BaseAgent


@dataclass
class AgentTypeRegistration:
    """Registration for an agent type."""

    name: str
    """Unique agent type identifier (e.g., 'react', 'planning')"""

    agent_class: Type[BaseAgent]
    """Agent class (must extend BaseAgent)"""

    description: str
    """Human-readable description"""

    default_strategy: Optional[Type] = None
    """Default strategy class for this agent type"""

    preset_config: Dict[str, Any] = None
    """Default configuration preset"""

    factory: Optional[Callable] = None
    """Optional factory function to create agent instances"""


# Global registry (same pattern as tools)
_AGENT_TYPE_REGISTRY: Dict[str, AgentTypeRegistration] = {}


def register_agent_type(
    name: str,
    agent_class: Type[BaseAgent] = None,
    description: str = "",
    default_strategy: Type = None,
    preset_config: Dict[str, Any] = None,
    factory: Callable = None,
    override: bool = False,
) -> None:
    """
    Register an agent type for use with Agent(agent_type="...").

    Args:
        name: Unique agent type identifier
        agent_class: Agent class (must extend BaseAgent)
        description: Human-readable description
        default_strategy: Default strategy for this agent type
        preset_config: Default configuration
        factory: Optional factory function
        override: Allow overriding existing types

    Example (Class-based):
        >>> from kaizen.agents.specialized.react import ReActAgent
        >>> from kaizen.strategies.multi_cycle import MultiCycleStrategy
        >>>
        >>> register_agent_type(
        ...     name="react",
        ...     agent_class=ReActAgent,
        ...     description="Reasoning + Acting cycles",
        ...     default_strategy=MultiCycleStrategy,
        ...     preset_config={"max_cycles": 10},
        ... )

    Example (Factory-based):
        >>> def create_research_agent(model, **kwargs):
        ...     return ResearchAgent(
        ...         model=model,
        ...         enable_citations=True,
        ...         **kwargs
        ...     )
        >>>
        >>> register_agent_type(
        ...     name="research",
        ...     description="Research with citations",
        ...     factory=create_research_agent,
        ... )
    """
    if name in _AGENT_TYPE_REGISTRY and not override:
        raise ValueError(
            f"Agent type '{name}' already registered. "
            f"Use override=True to replace."
        )

    registration = AgentTypeRegistration(
        name=name,
        agent_class=agent_class,
        description=description,
        default_strategy=default_strategy,
        preset_config=preset_config or {},
        factory=factory,
    )

    _AGENT_TYPE_REGISTRY[name] = registration
    print(f"✅ Registered agent type: {name}")


def get_agent_registration(name: str) -> AgentTypeRegistration:
    """
    Get agent type registration.

    Args:
        name: Agent type identifier

    Returns:
        AgentTypeRegistration

    Raises:
        ValueError: If agent type not found
    """
    if name not in _AGENT_TYPE_REGISTRY:
        available = ", ".join(_AGENT_TYPE_REGISTRY.keys())
        raise ValueError(
            f"Unknown agent type: {name}. "
            f"Available: {available}"
        )

    return _AGENT_TYPE_REGISTRY[name]


def create_agent_from_type(
    agent_type: str,
    model: str,
    **kwargs
) -> BaseAgent:
    """
    Create agent instance from registered type.

    Args:
        agent_type: Registered agent type
        model: LLM model
        **kwargs: Additional agent parameters

    Returns:
        Agent instance

    Example:
        >>> agent = create_agent_from_type("react", model="gpt-4")
    """
    registration = get_agent_registration(agent_type)

    # Use factory if provided
    if registration.factory:
        return registration.factory(model=model, **kwargs)

    # Use agent class
    if registration.agent_class:
        # Merge preset config with kwargs
        config = {**registration.preset_config, **kwargs}
        return registration.agent_class(model=model, **config)

    raise ValueError(
        f"Agent type '{agent_type}' has no class or factory"
    )


def list_agent_types() -> Dict[str, str]:
    """
    List all registered agent types.

    Returns:
        Dict mapping agent_type to description
    """
    return {
        name: reg.description
        for name, reg in _AGENT_TYPE_REGISTRY.items()
    }


# Decorator for easy registration
def agent_type(
    name: str,
    description: str = "",
    default_strategy: Type = None,
    preset_config: Dict[str, Any] = None,
):
    """
    Decorator to register agent type.

    Example:
        >>> from kaizen.agents.registry import agent_type
        >>> from kaizen.strategies import MultiCycleStrategy
        >>>
        >>> @agent_type(
        ...     name="research",
        ...     description="Research agent with citations",
        ...     default_strategy=MultiCycleStrategy,
        ... )
        ... class ResearchAgent(BaseAgent):
        ...     ...
    """
    def decorator(cls: Type[BaseAgent]):
        register_agent_type(
            name=name,
            agent_class=cls,
            description=description or cls.__doc__,
            default_strategy=default_strategy,
            preset_config=preset_config,
        )
        return cls

    return decorator
```

#### **Updated Agent.__init__() Integration**:

```python
# In agent.py
from kaizen.agents.registry import create_agent_from_type, get_agent_registration

class Agent:
    def __init__(self, model: str, agent_type: str = "simple", **kwargs):
        # Check if agent_type is registered
        try:
            registration = get_agent_registration(agent_type)

            # Create specialized agent instance
            specialized_agent = create_agent_from_type(
                agent_type=agent_type,
                model=model,
                **kwargs
            )

            # Use specialized agent's components
            self.base_agent = specialized_agent

        except ValueError:
            # Fall back to preset-based approach (backward compat)
            preset = get_agent_type_preset(agent_type)
            # ... existing code
```

### Layer 2: Multi-Agent Orchestration

#### **User Journey**:
```
1. Single agent not enough? → Need orchestration
2. Choose pattern → Pipeline, Routing, Supervisor-Worker, etc.
3. High-level API → Don't touch Core SDK
4. Use immediately → pipeline.run()
```

#### **Architecture**:

```
kaizen/
└── orchestration/              # Multi-agent coordination
    ├── __init__.py
    ├── pipeline.py             # NEW: High-level pipeline builder
    ├── router.py               # NEW: Meta-controller/routing
    │
    ├── patterns/               # Research-backed patterns
    │   ├── supervisor_worker.py    # ✅ Supervisor-Worker (existing)
    │   ├── meta_controller.py      # ❌ TODO: Smart routing
    │   ├── blackboard.py           # ❌ TODO: Shared workspace
    │   ├── ensemble.py             # ❌ TODO: Wisdom of crowds
    │   ├── consensus.py            # ✅ Consensus pattern
    │   ├── debate.py               # ✅ Debate pattern
    │   ├── sequential.py           # ✅ Sequential pipeline
    │   ├── handoff.py              # ✅ Agent-to-agent handoff
    │   └── parallel.py             # ❌ TODO: Parallel execution
    │
    └── builders/               # High-level builders
        ├── pipeline_builder.py # NEW: Fluent pipeline API
        └── workflow_builder.py # NEW: Visual workflow builder
```

#### **High-Level Orchestration API** (NEW):

```python
from kaizen.orchestration import Pipeline

# Example 1: Sequential pipeline
pipeline = Pipeline.sequential([
    Agent(model="gpt-4", agent_type="research"),
    Agent(model="gpt-4", agent_type="analysis"),
    Agent(model="gpt-4", agent_type="writing"),
])

result = pipeline.run("Research quantum computing and write report")

# Example 2: Parallel + Ensemble
pipeline = Pipeline.ensemble([
    Agent(model="gpt-4", agent_type="bullish_analyst"),
    Agent(model="gpt-4", agent_type="bearish_analyst"),
    Agent(model="gpt-4", agent_type="quant_analyst"),
], synthesizer=Agent(model="gpt-4", agent_type="cio"))

result = pipeline.run("Analyze Tesla stock")

# Example 3: Router (Meta-Controller)
pipeline = Pipeline.router({
    "coding": Agent(model="gpt-4", agent_type="code_expert"),
    "research": Agent(model="gpt-4", agent_type="researcher"),
    "writing": Agent(model="gpt-4", agent_type="writer"),
})

result = pipeline.run("Write a Python function to sort a list")
# Auto-routes to code_expert

# Example 4: Supervisor-Worker
pipeline = Pipeline.supervisor_worker(
    supervisor=Agent(model="gpt-4", agent_type="coordinator"),
    workers=[
        Agent(model="gpt-4", agent_type="data_analyst"),
        Agent(model="gpt-4", agent_type="code_expert"),
        Agent(model="gpt-4", agent_type="writer"),
    ]
)

result = pipeline.run("Analyze sales data and create visualization")
```

---

## Part 3: Mapping Research Patterns to Kaizen

### Single-Agent Patterns → kaizen/agents/specialized/

| Pattern | Status | Implementation | Strategy |
|---------|--------|----------------|----------|
| **1. Reflection** | ❌ TODO | `reflection.py` | MultiCycleStrategy |
| **2. Tool Use** | ✅ EXISTS | Via `tool_registry` | AsyncSingleShotStrategy |
| **3. ReAct** | ✅ EXISTS | `react.py` | MultiCycleStrategy |
| **4. Planning** | ❌ TODO | `planning.py` | MultiCycleStrategy |
| **5. PEV** | ❌ TODO | `pev.py` | MultiCycleStrategy |
| **6. ToT** | ❌ TODO | `tree_of_thoughts.py` | TreeExplorationStrategy |

### Multi-Agent Patterns → kaizen/orchestration/patterns/

| Pattern | Status | Implementation | Use Case |
|---------|--------|----------------|----------|
| **7. Multi-Agent** | ✅ EXISTS | `supervisor_worker.py` | Specialist teams |
| **8. Meta-Controller** | ❌ TODO | `meta_controller.py` | Smart routing |
| **9. Blackboard** | ❌ TODO | `blackboard.py` | Dynamic collaboration |
| **10. Ensemble** | ❌ TODO | `ensemble.py` | Decision-making |
| **11. Sequential** | ✅ EXISTS | `sequential.py` | Pipeline |
| **12. Consensus** | ✅ EXISTS | `consensus.py` | Agreement |
| **13. Debate** | ✅ EXISTS | `debate.py` | Dialectic |
| **14. Handoff** | ✅ EXISTS | `handoff.py` | Agent-to-agent |
| **15. Parallel** | ❌ TODO | `parallel.py` | Concurrent |

### Advanced Features → kaizen/

| Feature | Status | Location | Purpose |
|---------|--------|----------|---------|
| **Memory** | ✅ EXISTS | `kaizen/memory/` | Long-term context |
| **Learning** | ✅ EXISTS | `kaizen/memory/learning/` | Self-improvement |
| **Checkpointing** | ❌ TODO | `kaizen/memory/checkpoint/` | Failure recovery |
| **Control Protocol** | ✅ EXISTS | `kaizen/core/autonomy/control/` | Safety/approval |

---

## Part 4: Reorganization Plan

### Current Structure Issues

**Problem 1**: `kaizen/agents/coordination/` contains multi-agent patterns
- **Confusing**: "coordination" sounds like orchestration
- **Should be**: `kaizen/orchestration/patterns/`

**Problem 2**: `kaizen/coordination/` has only 2 files
- **Unclear purpose**
- **Should merge into**: `kaizen/orchestration/`

**Problem 3**: No high-level orchestration API
- **Current**: Users must use Core SDK WorkflowBuilder
- **Should be**: High-level Pipeline/Router API

### Proposed Reorganization

```
BEFORE:
kaizen/
├── agents/
│   └── coordination/          # ❌ CONFUSING NAME
│       ├── supervisor_worker.py
│       ├── consensus.py
│       ├── debate.py
│       ├── sequential.py
│       └── handoff.py
└── coordination/               # ❌ UNCLEAR PURPOSE
    ├── coordinator.py
    └── shared_memory_pool.py

AFTER:
kaizen/
├── agents/
│   ├── specialized/           # ✅ SINGLE AGENTS
│   │   ├── simple_qa.py
│   │   ├── react.py
│   │   ├── reflection.py       # NEW
│   │   ├── planning.py         # NEW
│   │   └── ...
│   └── registry.py            # NEW: Registration system
│
└── orchestration/             # ✅ MULTI-AGENT PATTERNS
    ├── __init__.py
    ├── pipeline.py            # NEW: High-level API
    ├── router.py              # NEW: Meta-controller
    │
    ├── patterns/              # ✅ CLEAR NAMING
    │   ├── supervisor_worker.py  # MOVED
    │   ├── meta_controller.py    # NEW
    │   ├── blackboard.py         # NEW
    │   ├── ensemble.py           # NEW
    │   ├── consensus.py          # MOVED
    │   ├── debate.py             # MOVED
    │   ├── sequential.py         # MOVED
    │   ├── handoff.py            # MOVED
    │   └── parallel.py           # NEW
    │
    ├── core/                  # ✅ INTERNAL COMPONENTS
    │   ├── coordinator.py        # MOVED from coordination/
    │   └── shared_memory_pool.py # MOVED from coordination/
    │
    └── builders/              # NEW: High-level builders
        ├── pipeline_builder.py
        └── workflow_builder.py
```

---

## Part 5: User Experience Examples

### Example 1: Start with Single Agent

```python
from kaizen import Agent

# Step 1: Try built-in agent
agent = Agent(model="gpt-4", agent_type="react")
result = agent.run("Book a flight to Paris")

print(result["thought"])  # See reasoning
print(result["action"])   # See action taken
```

### Example 2: Customize Own Agent

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from kaizen.agents.registry import register_agent_type
from kaizen.strategies import MultiCycleStrategy

# Step 1: Define signature
class ResearchSignature(Signature):
    query: str = InputField(description="Research query")
    sources: list = OutputField(description="Source citations")
    summary: str = OutputField(description="Research summary")

# Step 2: Create agent class
class ResearchAgent(BaseAgent):
    def __init__(self, model, **kwargs):
        super().__init__(
            config={"model": model, **kwargs},
            signature=ResearchSignature(),
            strategy=MultiCycleStrategy(max_cycles=10),
        )

# Step 3: Register it
register_agent_type(
    name="research",
    agent_class=ResearchAgent,
    description="Research with source citations",
)

# Step 4: Use immediately!
agent = Agent(model="gpt-4", agent_type="research")
result = agent.run("Research quantum computing breakthroughs")
```

### Example 3: Need Orchestration

```python
from kaizen import Agent
from kaizen.orchestration import Pipeline

# Step 1: Realize single agent isn't enough
# Step 2: Choose orchestration pattern

# Option A: Sequential pipeline
pipeline = Pipeline.sequential([
    Agent(model="gpt-4", agent_type="researcher"),
    Agent(model="gpt-4", agent_type="analyst"),
    Agent(model="gpt-4", agent_type="writer"),
])

result = pipeline.run("Research AI trends, analyze, and write report")

# Option B: Supervisor-Worker
pipeline = Pipeline.supervisor_worker(
    supervisor=Agent(model="gpt-4", agent_type="coordinator"),
    workers=[
        Agent(model="gpt-4", agent_type="data_expert"),
        Agent(model="gpt-4", agent_type="code_expert"),
        Agent(model="gpt-4", agent_type="writer"),
    ]
)

result = pipeline.run("Analyze sales data and create dashboard")

# Option C: Ensemble (wisdom of crowds)
pipeline = Pipeline.ensemble([
    Agent(model="gpt-4", agent_type="bullish"),
    Agent(model="gpt-4", agent_type="bearish"),
    Agent(model="gpt-4", agent_type="quantitative"),
], synthesizer=Agent(model="gpt-4", agent_type="cio"))

result = pipeline.run("Should we invest in Tesla?")
```

---

## Part 6: Implementation Priority

### Phase 1: Foundation (Week 1)
1. ✅ Create `kaizen/agents/registry.py`
2. ✅ Update `Agent.__init__()` to use registry
3. ✅ Register existing agents (react, simple_qa, etc.)
4. ✅ Test agent_type parameter with registered types

### Phase 2: Reorganization (Week 2)
1. ❌ Move `kaizen/agents/coordination/` → `kaizen/orchestration/patterns/`
2. ❌ Move `kaizen/coordination/` → `kaizen/orchestration/core/`
3. ❌ Update all imports
4. ❌ Test backward compatibility

### Phase 3: High-Level API (Week 3)
1. ❌ Create `kaizen/orchestration/pipeline.py`
2. ❌ Implement `Pipeline.sequential()`
3. ❌ Implement `Pipeline.supervisor_worker()`
4. ❌ Implement `Pipeline.ensemble()`
5. ❌ Implement `Pipeline.router()` (Meta-Controller)

### Phase 4: Missing Patterns (Week 4)
1. ❌ Implement `reflection.py` (single-agent)
2. ❌ Implement `planning.py` (single-agent)
3. ❌ Implement `meta_controller.py` (multi-agent)
4. ❌ Implement `blackboard.py` (multi-agent)

---

## Part 7: Key Decisions

### Decision 1: Dual Registration
- **Why**: Need both WorkflowBuilder discovery AND agent_type parameter
- **How**: `@register_node()` for Core SDK, `register_agent_type()` for Agent
- **Benefit**: Seamless integration with existing Core SDK

### Decision 2: Strategy Independence
- **Why**: Execution method (Strategy) is orthogonal to behavior (Agent Type)
- **How**: Any agent can use any strategy
- **Benefit**: Maximum flexibility without class explosion

### Decision 3: High-Level Orchestration API
- **Why**: Users shouldn't touch Core SDK WorkflowBuilder for common patterns
- **How**: `Pipeline` class with fluent API
- **Benefit**: 80% use cases covered with simple API

### Decision 4: Clear Separation
- **Why**: Single agents vs. multi-agent orchestration are fundamentally different
- **How**: `kaizen/agents/specialized/` vs. `kaizen/orchestration/patterns/`
- **Benefit**: No confusion about where to look

---

## Summary

**For Users**:
1. **Single Agent**: `Agent(model="gpt-4", agent_type="react")`
2. **Custom Agent**: Create class + `register_agent_type()`
3. **Orchestration**: `Pipeline.sequential()`, `Pipeline.ensemble()`, etc.

**For Framework**:
- **agents/specialized/** - Single agent patterns (Reflection, ReAct, Planning, etc.)
- **orchestration/patterns/** - Multi-agent patterns (Supervisor-Worker, Ensemble, etc.)
- **strategies/** - Execution methods (SingleShot, MultiCycle, ToT, etc.)
- **registry** - Seamless registration for both Core SDK and Agent API

**Next Steps**:
1. Implement `agents/registry.py`
2. Reorganize `coordination/` → `orchestration/`
3. Create high-level `Pipeline` API
4. Fill in missing patterns

---

**Questions for Approval**:
1. Approve dual registration system (WorkflowBuilder + agent_type)?
2. Approve reorganization (coordination → orchestration)?
3. Approve Pipeline API design?
4. Priority order correct?
