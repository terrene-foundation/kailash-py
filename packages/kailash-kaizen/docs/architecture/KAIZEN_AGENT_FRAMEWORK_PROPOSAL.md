# Kaizen Agent Framework - Comprehensive Proposal

**Status**: Proposal (Awaiting Approval)
**Created**: 2025-10-26
**Author**: Claude Code Analysis

---

## Executive Summary

This document proposes a unified, user-focused framework for Kaizen agents that addresses:

1. **Seamless custom agent registration** - How users create and register custom agents
2. **Clear structural organization** - Single agents vs. orchestration patterns
3. **Comprehensive pattern coverage** - All 17 research patterns from industry best practices
4. **Intuitive user journey** - Objective → Single Agent → Custom → Orchestration

---

## Part 1: Understanding Current State

### 1.1 Example Analysis: ReActAgent (react.py)

**Current Structure**:
```python
@register_node()  # Registration Type 1: For WorkflowBuilder/Studio
class ReActAgent(BaseAgent):
    metadata = NodeMetadata(
        name="ReActAgent",
        description="Reasoning + Acting agent...",
        version="1.0.0",
        tags={"ai", "kaizen", "react", "reasoning", "tool-use"},
    )

    def __init__(self, config: ReActConfig = None, ...):
        # Domain-specific config
        config = config or ReActConfig()

        # CRITICAL: Strategy = HOW the agent executes
        multi_cycle_strategy = MultiCycleStrategy(
            max_cycles=config.max_cycles,
            convergence_check=self._check_convergence
        )

        # Initialize BaseAgent
        super().__init__(
            config=config,
            signature=ReActSignature(),
            strategy=multi_cycle_strategy,  # HOW to execute
            tools="all"  # Enable tools via MCP
        )
```

**Key Insights**:
- ✅ Uses `@register_node()` for Core SDK/WorkflowBuilder discovery
- ✅ Has domain-specific config (`ReActConfig`)
- ✅ Uses `MultiCycleStrategy` for iterative execution
- ✅ Extends `BaseAgent` for execution
- ❌ **NOT registered for `Agent(agent_type="react")` parameter**
- ❌ **No seamless way for users to register custom agents**

### 1.2 What is "Strategy"?

**Strategy = HOW the agent executes (execution method)**

Available strategies:
- `AsyncSingleShotStrategy` - Execute once, async (default)
- `SingleShotStrategy` - Execute once, sync
- `MultiCycleStrategy` - Execute iteratively until convergence
- `StreamingStrategy` - Execute with streaming output
- `ParallelBatchStrategy` - Execute multiple inputs in parallel
- `HumanInLoopStrategy` - Execute with human approval

**Key Principle**: Strategy is **orthogonal** to agent type
- Any agent can use any strategy
- Strategy = HOW (execution method)
- Agent Type = WHAT (behavior pattern)

Example:
```python
# ReAct agent with multi-cycle strategy (iterative)
react = ReActAgent()  # Uses MultiCycleStrategy by default

# Simple QA agent with single-shot strategy (one-time)
simple = SimpleQAAgent()  # Uses AsyncSingleShotStrategy by default

# Custom agent with streaming strategy
custom = CustomAgent(strategy=StreamingStrategy())
```

### 1.3 Current Structural Confusion

**Problem**: Two coordination directories with unclear separation

```
kaizen/
├── agents/
│   ├── specialized/           # Single agents ✅
│   │   ├── react.py
│   │   ├── simple_qa.py
│   │   └── ...
│   └── coordination/          # ❌ CONFUSING: Multi-agent patterns in "agents"
│       ├── supervisor_worker.py
│       ├── consensus_pattern.py
│       ├── debate_pattern.py
│       ├── handoff_pattern.py
│       └── sequential_pipeline.py
└── coordination/              # ❌ CONFUSING: Only 2 files, unclear purpose
    ├── patterns.py
    └── teams.py
```

**Why Confusing**:
- "agents" directory should contain **single agents**, not orchestration patterns
- Having both `agents/coordination/` and `coordination/` is redundant
- Users don't understand the difference

---

## Part 2: Proposed User Journey

### 2.1 The Four-Step Journey

**As a user, I would go like this:**

```
Step 1: I have an objective
    ↓
Step 2: Let's try using one agent, select from the list and choose ReAct or autonomous
    ↓
Step 3: Let's try customizing our own, then register it and test
    ↓
Step 4: Seems like we need more agents in a workflow, let's do an orchestration
```

### 2.2 Step-by-Step Examples

**Step 1: I have an objective**
```python
# User has a task
objective = "Analyze quarterly sales data and generate insights"
```

**Step 2: Try a single agent**
```python
from kaizen import Agent

# Option A: Use preset agent type
agent = Agent(model="gpt-4", agent_type="react")
result = agent.run(objective)

# Option B: Use specialized agent directly
from kaizen.agents import ReActAgent
agent = ReActAgent(model="gpt-4")
result = agent.solve_task(objective)
```

**Step 3: Customize and register**
```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from kaizen.agents.registry import register_agent_type

# Create custom agent
class SalesAnalystAgent(BaseAgent):
    def __init__(self, model, **kwargs):
        super().__init__(
            config={"model": model, **kwargs},
            signature=SalesSignature(),
            strategy=MultiCycleStrategy(max_cycles=10),
        )

# Register it seamlessly
register_agent_type(
    name="sales_analyst",
    agent_class=SalesAnalystAgent,
    description="Specialized sales data analyst",
)

# Use immediately with Agent API
agent = Agent(model="gpt-4", agent_type="sales_analyst")
result = agent.run(objective)
```

**Step 4: Orchestration (multiple agents)**
```python
from kaizen.orchestration import Pipeline

# Create specialized agents
researcher = Agent(model="gpt-4", agent_type="research")
analyst = Agent(model="gpt-4", agent_type="sales_analyst")
writer = Agent(model="gpt-4", agent_type="report_writer")

# Sequential pipeline
pipeline = Pipeline.sequential([researcher, analyst, writer])
result = pipeline.run(objective)

# OR Supervisor-Worker
supervisor = Agent(model="gpt-4", agent_type="coordinator")
workers = [researcher, analyst, writer]
pipeline = Pipeline.supervisor_worker(supervisor, workers)
result = pipeline.run(objective)
```

---

## Part 3: Mapping 17 Research Patterns to Kaizen

### 3.1 Pattern Classification

**Single-Agent Patterns** (6 patterns):
1. Reflection - Self-critique and improvement
2. Tool Use - External tool integration
3. ReAct - Reasoning + Action cycles
4. Planning - Pre-plan then execute
5. PEV (Planner-Executor-Verifier) - Planning with error recovery
6. Tree-of-Thoughts (ToT) - Explore multiple possibilities

**Multi-Agent Patterns** (9 patterns):
7. Multi-Agent Teams - Specialized team collaboration
8. Meta-Controller - Smart routing between specialists
9. Blackboard - Dynamic collaboration with shared workspace
10. Ensemble - Multiple perspectives, synthesized decision
11. Sequential - Linear pipeline of specialists
12. Consensus - Group agreement through voting
13. Debate - Adversarial discussion to reach conclusion
14. Handoff - Sequential task passing between specialists
15. Parallel - Concurrent execution of independent tasks

**Advanced Features** (2+ patterns):
16. Memory Systems - Episodic + Semantic long-term memory
17. Self-Improvement Loops - Iterative refinement until quality threshold

### 3.2 Kaizen Implementation Status

| Pattern | Type | Status | Kaizen Location | Notes |
|---------|------|--------|-----------------|-------|
| **Reflection** | Single | ⚠️ Partial | `self_reflection.py` | Needs enhancement |
| **Tool Use** | Single | ✅ Complete | `tool_registry` | 12 builtin tools |
| **ReAct** | Single | ✅ Complete | `react.py` | Production-ready |
| **Planning** | Single | ❌ TODO | - | Need to implement |
| **PEV** | Single | ❌ TODO | - | Need to implement |
| **ToT** | Single | ❌ TODO | - | Need to implement |
| **Multi-Agent Teams** | Multi | ✅ Complete | Google A2A integration | Capability-based |
| **Meta-Controller** | Multi | ❌ TODO | - | Need intelligent routing |
| **Blackboard** | Multi | ❌ TODO | - | Need shared workspace |
| **Ensemble** | Multi | ❌ TODO | - | Need voting/synthesis |
| **Sequential** | Multi | ✅ Complete | `sequential_pipeline.py` | In coordination/ |
| **Consensus** | Multi | ✅ Complete | `consensus_pattern.py` | In coordination/ |
| **Debate** | Multi | ✅ Complete | `debate_pattern.py` | In coordination/ |
| **Handoff** | Multi | ✅ Complete | `handoff_pattern.py` | In coordination/ |
| **Parallel** | Multi | ⚠️ Partial | `parallel_batch.py` | Strategy-level only |
| **Memory** | Advanced | ✅ Complete | `memory/` | Buffer, Semantic, Persistent |
| **Self-Improvement** | Advanced | ⚠️ Partial | Self-reflection | Needs loops |

**Summary**:
- ✅ Complete: 7 patterns
- ⚠️ Partial: 3 patterns
- ❌ TODO: 7 patterns

---

## Part 4: Proposed Architecture

### 4.1 Clean 2-Layer Separation

```
kaizen/
├── agents/
│   ├── specialized/              # LAYER 1: Single Agents
│   │   ├── simple_qa.py         # ✅ Simple Q&A
│   │   ├── reflection.py        # ⚠️ Self-reflection (enhance)
│   │   ├── react.py             # ✅ ReAct (complete)
│   │   ├── planning.py          # ❌ Planning (TODO)
│   │   ├── pev.py               # ❌ PEV (TODO)
│   │   ├── tree_of_thoughts.py  # ❌ ToT (TODO)
│   │   ├── code_generation.py   # ✅ Code specialist
│   │   ├── rag_research.py      # ✅ RAG specialist
│   │   └── ...
│   └── registry.py              # NEW: Agent registration system
│
└── orchestration/               # LAYER 2: Multi-Agent Orchestration
    ├── pipeline.py              # NEW: High-level Pipeline API
    ├── patterns/                # All coordination patterns
    │   ├── supervisor_worker.py # ✅ From agents/coordination/
    │   ├── meta_controller.py   # ❌ TODO
    │   ├── blackboard.py        # ❌ TODO
    │   ├── ensemble.py          # ❌ TODO
    │   ├── sequential.py        # ✅ From agents/coordination/
    │   ├── consensus.py         # ✅ From agents/coordination/
    │   ├── debate.py            # ✅ From agents/coordination/
    │   ├── handoff.py           # ✅ From agents/coordination/
    │   └── parallel.py          # ⚠️ Enhance from strategy
    └── core/                    # Shared orchestration infrastructure
        ├── coordinator.py       # From coordination/
        └── shared_memory_pool.py # From coordination/
```

### 4.2 Reorganization Plan

**BEFORE** (Confusing):
```
kaizen/agents/coordination/  # Multi-agent patterns in "agents"
kaizen/coordination/         # Only 2 files
```

**AFTER** (Clear):
```
kaizen/agents/specialized/   # All single agents
kaizen/orchestration/        # All multi-agent patterns
  ├── patterns/              # Moved from agents/coordination/
  ├── core/                  # Moved from coordination/
  └── pipeline.py            # NEW: High-level API
```

---

## Part 5: Dual Registration System

### 5.1 The Problem

Currently, agents are only registered for Core SDK WorkflowBuilder:

```python
@register_node()  # Type 1: For WorkflowBuilder/Studio
class ReActAgent(BaseAgent):
    ...
```

But NOT for the unified Agent API:
```python
# This doesn't work yet!
agent = Agent(model="gpt-4", agent_type="react")  # ❌ No registration
```

### 5.2 The Solution: Dual Registration

**Registration Type 1**: Core SDK WorkflowBuilder (existing)
```python
from kailash.nodes.base import register_node

@register_node()
class ReActAgent(BaseAgent):
    ...
```

**Registration Type 2**: Agent API (NEW)
```python
from kaizen.agents.registry import register_agent_type

register_agent_type(
    name="react",
    agent_class=ReActAgent,
    description="Reasoning + Acting cycles",
    default_strategy=MultiCycleStrategy,
    preset_config={"max_cycles": 10},
    category="specialized",
    tags=["reasoning", "tool-use", "iterative"],
)
```

**Why Both?**:
- Type 1: Existing Core SDK integration, WorkflowBuilder/Studio discovery
- Type 2: New unified Agent API, seamless custom agent registration

### 5.3 Seamless Custom Agent Registration

**Example 1: Register with function**
```python
from kaizen.agents.registry import register_agent_type

class ResearchAgent(BaseAgent):
    def __init__(self, model, **kwargs):
        super().__init__(
            config={"model": model, **kwargs},
            signature=ResearchSignature(),
            strategy=MultiCycleStrategy(max_cycles=15),
        )

# Register
register_agent_type(
    name="research",
    agent_class=ResearchAgent,
    description="Research agent with citation tracking",
    category="specialized",
    tags=["research", "citations"],
)

# Use immediately
from kaizen import Agent
agent = Agent(model="gpt-4", agent_type="research")
```

**Example 2: Register with decorator**
```python
from kaizen.agents.registry import agent_type

@agent_type(
    name="research",
    description="Research agent with citation tracking",
    category="specialized",
    tags=["research", "citations"],
)
class ResearchAgent(BaseAgent):
    def __init__(self, model, **kwargs):
        super().__init__(
            config={"model": model, **kwargs},
            signature=ResearchSignature(),
            strategy=MultiCycleStrategy(max_cycles=15),
        )

# Already registered! Use directly:
from kaizen import Agent
agent = Agent(model="gpt-4", agent_type="research")
```

---

## Part 6: High-Level Orchestration API

### 6.1 The Problem

Currently, users need to use Core SDK WorkflowBuilder for multi-agent:

```python
# Too low-level for most users
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("ReActAgent", "researcher", {...})
workflow.add_node("ReActAgent", "analyst", {...})
workflow.add_connection("researcher", "analyst")
result = runtime.execute(workflow.build())
```

### 6.2 The Solution: Pipeline API

**High-level abstraction** that hides Core SDK complexity:

```python
from kaizen.orchestration import Pipeline
from kaizen import Agent

# Sequential Pipeline
researcher = Agent(model="gpt-4", agent_type="research")
analyst = Agent(model="gpt-4", agent_type="analyst")
writer = Agent(model="gpt-4", agent_type="writer")

pipeline = Pipeline.sequential([researcher, analyst, writer])
result = pipeline.run("Analyze Q4 sales trends")
```

### 6.3 All Orchestration Patterns

**1. Sequential Pipeline**
```python
pipeline = Pipeline.sequential([agent1, agent2, agent3])
result = pipeline.run(task)
```

**2. Supervisor-Worker**
```python
supervisor = Agent(model="gpt-4", agent_type="coordinator")
workers = [specialist1, specialist2, specialist3]

pipeline = Pipeline.supervisor_worker(
    supervisor=supervisor,
    workers=workers,
    selection_mode="semantic",  # Semantic capability matching
)
result = pipeline.run(task)
```

**3. Meta-Controller (Smart Routing)**
```python
routes = {
    "coding": coding_agent,
    "research": research_agent,
    "writing": writing_agent,
}

pipeline = Pipeline.router(routes)
result = pipeline.run(task)  # Auto-routes to best agent
```

**4. Ensemble (Multiple Perspectives)**
```python
bullish_agent = Agent(model="gpt-4", agent_type="bullish_analyst")
bearish_agent = Agent(model="gpt-4", agent_type="bearish_analyst")
quant_agent = Agent(model="gpt-4", agent_type="quant_analyst")
synthesizer = Agent(model="gpt-4", agent_type="cio")

pipeline = Pipeline.ensemble(
    agents=[bullish_agent, bearish_agent, quant_agent],
    synthesizer=synthesizer,
)
result = pipeline.run("Should we invest in ACME Corp?")
```

**5. Blackboard (Dynamic Collaboration)**
```python
specialists = [data_agent, code_agent, viz_agent]

pipeline = Pipeline.blackboard(
    specialists=specialists,
    shared_workspace=SharedWorkspace(),
    coordinator=controller_agent,
)
result = pipeline.run(task)
```

**6. Consensus**
```python
agents = [expert1, expert2, expert3]

pipeline = Pipeline.consensus(
    agents=agents,
    voting_strategy="majority",  # or "unanimous", "weighted"
)
result = pipeline.run(task)
```

**7. Debate**
```python
proposer = Agent(model="gpt-4", agent_type="proposer")
opposer = Agent(model="gpt-4", agent_type="critic")
judge = Agent(model="gpt-4", agent_type="judge")

pipeline = Pipeline.debate(
    proposer=proposer,
    opposer=opposer,
    judge=judge,
    max_rounds=3,
)
result = pipeline.run(task)
```

---

## Part 7: Implementation Roadmap

### Phase 1: Registry System (Week 1)
- [ ] Create `kaizen/agents/registry.py`
- [ ] Implement `register_agent_type()` function
- [ ] Implement `@agent_type` decorator
- [ ] Update `Agent.__init__()` to use registry
- [ ] Register all existing agents (react, simple_qa, etc.)
- [ ] Write tests for registry system

### Phase 2: Reorganization (Week 2)
- [ ] Move `kaizen/agents/coordination/` → `kaizen/orchestration/patterns/`
- [ ] Move `kaizen/coordination/` → `kaizen/orchestration/core/`
- [ ] Update all imports across codebase
- [ ] Test backward compatibility
- [ ] Update documentation

### Phase 3: High-Level Pipeline API (Week 3)
- [ ] Create `kaizen/orchestration/pipeline.py`
- [ ] Implement `Pipeline.sequential()`
- [ ] Implement `Pipeline.supervisor_worker()`
- [ ] Implement `Pipeline.ensemble()`
- [ ] Implement `Pipeline.router()` (Meta-Controller)
- [ ] Implement `Pipeline.blackboard()`
- [ ] Implement `Pipeline.consensus()`
- [ ] Implement `Pipeline.debate()`
- [ ] Write tests for all patterns

### Phase 4: Missing Patterns (Week 4)
- [ ] Implement `planning.py` (single-agent)
- [ ] Implement `pev.py` (Planner-Executor-Verifier)
- [ ] Implement `tree_of_thoughts.py` (ToT)
- [ ] Enhance `reflection.py` with self-improvement loops
- [ ] Implement `meta_controller.py` (intelligent routing)
- [ ] Implement `blackboard.py` (dynamic collaboration)
- [ ] Implement `ensemble.py` (voting/synthesis)
- [ ] Write comprehensive examples

---

## Part 8: Key Design Decisions

### Decision 1: Dual Registration
**Why**: Maintain backward compatibility with Core SDK while enabling unified Agent API

**Impact**: All agents work both ways:
- `from kaizen.agents import ReActAgent; agent = ReActAgent()`
- `from kaizen import Agent; agent = Agent(agent_type="react")`

### Decision 2: Strategy Independence
**Why**: Strategy (HOW) is orthogonal to Agent Type (WHAT)

**Impact**: Users can mix and match:
- `Agent(agent_type="react", strategy=StreamingStrategy())`
- `Agent(agent_type="simple", strategy=MultiCycleStrategy())`

### Decision 3: Clear Separation (Single vs. Orchestration)
**Why**: Users need clear mental model

**Impact**:
- Single agents → `kaizen/agents/specialized/`
- Multi-agent patterns → `kaizen/orchestration/`

### Decision 4: High-Level Pipeline API
**Why**: Users shouldn't need Core SDK knowledge for orchestration

**Impact**: Simple orchestration without WorkflowBuilder:
- `Pipeline.sequential([a, b, c])`  instead of workflow building

---

## Part 9: Questions for Approval

**Before proceeding with implementation**, please confirm:

1. **Dual Registration System**: Approve `register_agent_type()` for Agent API registration?

2. **Reorganization**: Approve moving:
   - `agents/coordination/` → `orchestration/patterns/`
   - `coordination/` → `orchestration/core/`

3. **Pipeline API Design**: Approve high-level `Pipeline` class with:
   - `Pipeline.sequential()`
   - `Pipeline.supervisor_worker()`
   - `Pipeline.ensemble()`
   - `Pipeline.router()`
   - `Pipeline.blackboard()`
   - `Pipeline.consensus()`
   - `Pipeline.debate()`

4. **Implementation Priority**: Approve 4-phase roadmap:
   - Phase 1: Registry (Week 1)
   - Phase 2: Reorganization (Week 2)
   - Phase 3: Pipeline API (Week 3)
   - Phase 4: Missing patterns (Week 4)

---

## Appendix A: Complete Code Examples

### A.1 Custom Agent Registration (Full Example)

```python
"""
Creating and Registering a Custom Sales Analyst Agent
"""

from dataclasses import dataclass
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from kaizen.strategies.multi_cycle import MultiCycleStrategy
from kaizen.agents.registry import register_agent_type


# Step 1: Define domain-specific configuration
@dataclass
class SalesAnalystConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.3  # Lower for analytical tasks
    max_cycles: int = 8
    analysis_depth: str = "comprehensive"  # or "summary"


# Step 2: Define signature
class SalesAnalysisSignature(Signature):
    sales_data: str = InputField(description="Quarterly sales data")
    analysis_type: str = InputField(
        description="Type of analysis",
        default="trends"
    )

    insights: list = OutputField(description="Key insights discovered")
    recommendations: list = OutputField(description="Action recommendations")
    confidence: float = OutputField(description="Analysis confidence 0-1")


# Step 3: Create custom agent class
class SalesAnalystAgent(BaseAgent):
    def __init__(
        self,
        model: str = "gpt-4",
        analysis_depth: str = "comprehensive",
        **kwargs
    ):
        # Create config
        config = SalesAnalystConfig(
            model=model,
            analysis_depth=analysis_depth,
        )

        # Multi-cycle for iterative analysis
        strategy = MultiCycleStrategy(
            max_cycles=config.max_cycles,
            convergence_check=self._check_analysis_complete,
        )

        # Initialize BaseAgent
        super().__init__(
            config=config,
            signature=SalesAnalysisSignature(),
            strategy=strategy,
        )

        self.analysis_depth = analysis_depth

    def _check_analysis_complete(self, result: dict) -> bool:
        """Check if analysis is comprehensive enough."""
        insights = result.get("insights", [])
        confidence = result.get("confidence", 0.0)

        # Converge if we have enough insights with high confidence
        return len(insights) >= 3 and confidence >= 0.8

    def analyze(self, sales_data: str, analysis_type: str = "trends"):
        """Convenience method for sales analysis."""
        return self.run(
            sales_data=sales_data,
            analysis_type=analysis_type,
        )


# Step 4: Register the custom agent
register_agent_type(
    name="sales_analyst",
    agent_class=SalesAnalystAgent,
    description="Specialized sales data analyst with trend analysis",
    category="specialized",
    tags=["sales", "analysis", "business-intelligence"],
)


# Step 5: Use it immediately with Agent API
if __name__ == "__main__":
    from kaizen import Agent

    # Option 1: Via Agent API
    agent = Agent(model="gpt-4", agent_type="sales_analyst")

    # Option 2: Direct instantiation
    agent = SalesAnalystAgent(model="gpt-4", analysis_depth="summary")

    # Run analysis
    result = agent.analyze(
        sales_data="Q4 2024: Product A $2M, Product B $1.5M...",
        analysis_type="trends",
    )

    print("Insights:", result["insights"])
    print("Recommendations:", result["recommendations"])
    print("Confidence:", result["confidence"])
```

### A.2 Orchestration Example (Full Pipeline)

```python
"""
Complete Multi-Agent Pipeline for Market Analysis
"""

from kaizen import Agent
from kaizen.orchestration import Pipeline


# Create specialized agents
news_analyst = Agent(
    model="gpt-4",
    agent_type="research",
    instructions="Analyze news articles for market sentiment",
)

financial_analyst = Agent(
    model="gpt-4",
    agent_type="sales_analyst",
    instructions="Analyze financial metrics and trends",
)

technical_analyst = Agent(
    model="gpt-4",
    agent_type="code",  # Analyzes technical indicators
    instructions="Calculate technical indicators and patterns",
)

report_writer = Agent(
    model="gpt-4",
    agent_type="writer",
    instructions="Synthesize analysis into executive summary",
)


# Sequential Pipeline
def sequential_analysis(company: str):
    """Sequential pipeline: News → Financial → Technical → Report"""
    pipeline = Pipeline.sequential([
        news_analyst,
        financial_analyst,
        technical_analyst,
        report_writer,
    ])

    result = pipeline.run(f"Analyze {company} for investment decision")
    return result


# Supervisor-Worker Pipeline
def supervisor_analysis(company: str):
    """Supervisor coordinates specialists based on needs"""
    supervisor = Agent(
        model="gpt-4",
        agent_type="coordinator",
        instructions="Coordinate analysis specialists intelligently",
    )

    workers = [news_analyst, financial_analyst, technical_analyst]

    pipeline = Pipeline.supervisor_worker(
        supervisor=supervisor,
        workers=workers,
        selection_mode="semantic",  # A2A capability matching
    )

    result = pipeline.run(f"Should we invest in {company}?")
    return result


# Ensemble Pipeline
def ensemble_analysis(company: str):
    """Multiple analysts vote on decision"""
    bullish_analyst = Agent(
        model="gpt-4",
        agent_type="simple",
        instructions="Analyze from bullish perspective",
    )

    bearish_analyst = Agent(
        model="gpt-4",
        agent_type="simple",
        instructions="Analyze from bearish perspective",
    )

    quant_analyst = Agent(
        model="gpt-4",
        agent_type="code",
        instructions="Quantitative analysis only",
    )

    cio = Agent(
        model="gpt-4",
        agent_type="simple",
        instructions="Synthesize perspectives into final decision",
    )

    pipeline = Pipeline.ensemble(
        agents=[bullish_analyst, bearish_analyst, quant_analyst],
        synthesizer=cio,
    )

    result = pipeline.run(f"Investment decision for {company}")
    return result


# Run all approaches
if __name__ == "__main__":
    company = "ACME Corp"

    print("=== Sequential Analysis ===")
    result = sequential_analysis(company)
    print(result)

    print("\n=== Supervisor Analysis ===")
    result = supervisor_analysis(company)
    print(result)

    print("\n=== Ensemble Analysis ===")
    result = ensemble_analysis(company)
    print(result)
```

---

**END OF PROPOSAL**
