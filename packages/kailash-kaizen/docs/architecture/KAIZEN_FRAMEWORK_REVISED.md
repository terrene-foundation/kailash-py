# Kaizen Agent Framework - REVISED Proposal

**Status**: Revised Proposal (Addressing Feedback)
**Created**: 2025-10-26
**Revised**: 2025-10-26 (Revision 2)

---

## Changes from Previous Proposal

This revision addresses 5 critical points of feedback:

1. ✅ **Missed autonomous agents directory** - Now included in analysis
2. ✅ **Method name inconsistency** - Standardized to `.run()` across all agents
3. ✅ **Registration inheritance** - `register_agent_type` now inherits `@register_node`
4. ✅ **Nested/composable pipelines** - Full composability design
5. ✅ **Pipeline pattern overlap analysis** - Clear "when to use which" decision matrix + A2A integration

---

## Part 1: Complete Directory Structure (CORRECTED)

### 1.1 All Agent Categories

```
kaizen/agents/
├── specialized/          # Domain-specific single agents
│   ├── simple_qa.py
│   ├── react.py
│   ├── chain_of_thought.py
│   ├── rag_research.py
│   ├── code_generation.py
│   ├── self_reflection.py
│   ├── memory_agent.py
│   ├── streaming_chat.py
│   ├── batch_processing.py
│   ├── human_approval.py
│   └── resilient.py
│
├── autonomous/           # ✅ ADDED: Autonomous agents (full autonomy)
│   ├── base.py          # Base autonomous agent
│   ├── claude_code.py   # Claude Code autonomous agent
│   └── codex.py         # Codex autonomous agent
│
├── multi_modal/          # Multi-modal processing
│   ├── vision_agent.py
│   ├── transcription_agent.py
│   └── multi_modal_agent.py
│
├── coordination/         # ❌ TO MOVE: Multi-agent patterns
│   ├── supervisor_worker.py
│   ├── consensus_pattern.py
│   ├── debate_pattern.py
│   ├── handoff_pattern.py
│   └── sequential_pipeline.py
│
└── registry.py          # NEW: Agent registration system
```

**Key Insight**: Autonomous agents are a distinct category - they have full autonomy with tool calling, planning, and self-directed execution.

---

## Part 2: Execution Method Standardization

### 2.1 Current Inconsistency (PROBLEM)

| Agent | Current Method | File |
|-------|----------------|------|
| ReActAgent | `.solve_task()` | react.py |
| SimpleQAAgent | `.ask()` | simple_qa.py |
| VisionAgent | `.analyze()` | vision_agent.py |
| MultiModalAgent | `.analyze()` | multi_modal_agent.py |
| BaseAgent | `.run()` | base_agent.py |

**Problem**: Inconsistent method names create confusion and poor UX.

### 2.2 Standardization Plan

**DECISION**: **`.run()` is the universal execution method**

**Rationale**:
- BaseAgent already uses `.run()`
- Generic and works for all agent types
- Matches industry conventions (LangChain, etc.)

**Implementation**:

1. **Keep `.run()` as primary method** (all agents)
2. **Add convenience aliases** (backward compatibility)

```python
class ReActAgent(BaseAgent):
    def run(self, task: str, **kwargs) -> Dict[str, Any]:
        """Universal execution method."""
        # Main implementation
        ...

    def solve_task(self, task: str, **kwargs) -> Dict[str, Any]:
        """Convenience alias for .run()"""
        return self.run(task=task, **kwargs)


class SimpleQAAgent(BaseAgent):
    def run(self, question: str, **kwargs) -> Dict[str, Any]:
        """Universal execution method."""
        # Main implementation
        ...

    def ask(self, question: str, **kwargs) -> Dict[str, Any]:
        """Convenience alias for .run()"""
        return self.run(question=question, **kwargs)


class VisionAgent(BaseAgent):
    def run(self, image: str, question: str, **kwargs) -> Dict[str, Any]:
        """Universal execution method."""
        # Main implementation
        ...

    def analyze(self, image: str, question: str, **kwargs) -> Dict[str, Any]:
        """Convenience alias for .run()"""
        return self.run(image=image, question=question, **kwargs)
```

**Benefits**:
- ✅ Consistent `.run()` across ALL agents
- ✅ Backward compatibility with existing code
- ✅ Domain-specific convenience methods preserved
- ✅ Better documentation and examples

**Migration**:
```python
# OLD (still works)
react_agent.solve_task("Book a flight")
qa_agent.ask("What is AI?")
vision_agent.analyze("image.png", "What's in this?")

# NEW (recommended)
react_agent.run(task="Book a flight")
qa_agent.run(question="What is AI?")
vision_agent.run(image="image.png", question="What's in this?")
```

---

## Part 3: Dual Registration with Inheritance

### 3.1 Design: `register_agent_type` Auto-Inherits `@register_node`

**DECISION**: `register_agent_type` automatically calls `@register_node`

**Why**: Single decorator approach for users, dual registration happens automatically.

### 3.2 Implementation

```python
# kaizen/agents/registry.py

def register_agent_type(
    name: str,
    agent_class: Type[BaseAgent],
    description: str = "",
    default_strategy: Type = None,
    preset_config: Dict[str, Any] = None,
    category: str = "general",
    tags: list = None,
    override: bool = False,
):
    """
    Register agent type with DUAL registration:
    1. Agent API registry (for Agent(agent_type="..."))
    2. Core SDK registry (for WorkflowBuilder)

    This automatically calls @register_node for Core SDK integration.
    """
    # Step 1: Register for Agent API
    registration = AgentTypeRegistration(...)
    _AGENT_TYPE_REGISTRY[name] = registration

    # Step 2: Auto-register for Core SDK (@register_node)
    from kailash.nodes.base import register_node_class

    # Create metadata for Core SDK registration
    metadata = NodeMetadata(
        name=agent_class.__name__,
        description=description,
        version="1.0.0",
        tags=set(tags) if tags else set(),
    )

    # Auto-register with Core SDK
    register_node_class(agent_class, metadata)

    logger.info(
        f"Dual registration complete for '{name}': "
        f"Agent API + Core SDK"
    )
```

### 3.3 Usage for Pre-Defined Agents

**Current (react.py)**:
```python
@register_node()  # Only Core SDK
class ReActAgent(BaseAgent):
    ...
```

**NEW (react.py)**:
```python
# NO DECORATOR on class! Registration happens in registry module

class ReActAgent(BaseAgent):
    ...

# In agents/register_builtin.py:
register_agent_type(
    name="react",
    agent_class=ReActAgent,
    description="Reasoning + Acting cycles",
    default_strategy=MultiCycleStrategy,
    preset_config={"max_cycles": 10},
    category="specialized",
    tags=["reasoning", "tool-use", "iterative"],
)  # Auto-registers for BOTH Agent API + Core SDK
```

**Benefits**:
- ✅ Single registration call for dual registration
- ✅ All pre-defined agents use same pattern
- ✅ Core SDK integration automatic
- ✅ Agent API integration automatic

### 3.4 Migration Plan for All Pre-Defined Agents

**Step 1**: Remove `@register_node()` decorators from all agent classes

**Step 2**: Add dual registration in `register_builtin.py`:

```python
# agents/register_builtin.py

def register_builtin_agents():
    """Register all builtin agents with dual registration."""

    # Specialized agents
    register_agent_type(name="simple", agent_class=SimpleQAAgent, ...)
    register_agent_type(name="react", agent_class=ReActAgent, ...)
    register_agent_type(name="cot", agent_class=ChainOfThoughtAgent, ...)
    register_agent_type(name="rag", agent_class=RAGResearchAgent, ...)
    register_agent_type(name="code", agent_class=CodeGenerationAgent, ...)
    register_agent_type(name="reflection", agent_class=SelfReflectionAgent, ...)
    register_agent_type(name="memory", agent_class=MemoryAgent, ...)
    register_agent_type(name="streaming", agent_class=StreamingChatAgent, ...)

    # Autonomous agents
    register_agent_type(name="autonomous", agent_class=AutonomousAgent, ...)
    register_agent_type(name="claude_code", agent_class=ClaudeCodeAgent, ...)
    register_agent_type(name="codex", agent_class=CodexAgent, ...)

    # Multi-modal agents
    register_agent_type(name="vision", agent_class=VisionAgent, ...)
    register_agent_type(name="audio", agent_class=TranscriptionAgent, ...)
    register_agent_type(name="multimodal", agent_class=MultiModalAgent, ...)

    # Enterprise agents
    register_agent_type(name="batch", agent_class=BatchProcessingAgent, ...)
    register_agent_type(name="approval", agent_class=HumanApprovalAgent, ...)
    register_agent_type(name="resilient", agent_class=ResilientAgent, ...)
```

---

## Part 4: Composable/Nested Pipeline Patterns

### 4.1 Design Principle: Full Composability

**DECISION**: Pipelines can be nested arbitrarily deep.

**Why**: Real-world workflows require complex compositions like:
- Supervisor-Worker where each worker is a Sequential pipeline
- Sequential pipeline where one step is an Ensemble
- Ensemble where each agent is a Supervisor-Worker

### 4.2 Pipeline Interface

All pipelines implement the same interface:

```python
class PipelineProtocol:
    """Protocol that all pipelines must implement."""

    def run(self, **inputs) -> Dict[str, Any]:
        """Execute the pipeline."""
        ...

    def to_agent(self) -> Agent:
        """Convert pipeline to an Agent for composition."""
        ...
```

### 4.3 Nested Example 1: Supervisor-Worker with Sequential Workers

```python
from kaizen import Agent
from kaizen.orchestration import Pipeline

# Create sequential pipelines for each worker
data_worker = Pipeline.sequential([
    Agent(model="gpt-4", agent_type="data_extractor"),
    Agent(model="gpt-4", agent_type="data_validator"),
    Agent(model="gpt-4", agent_type="data_transformer"),
])

code_worker = Pipeline.sequential([
    Agent(model="gpt-4", agent_type="code_analyzer"),
    Agent(model="gpt-4", agent_type="code_optimizer"),
])

viz_worker = Pipeline.sequential([
    Agent(model="gpt-4", agent_type="viz_designer"),
    Agent(model="gpt-4", agent_type="viz_renderer"),
])

# Create supervisor-worker where workers are pipelines
supervisor = Agent(model="gpt-4", agent_type="coordinator")

analysis_pipeline = Pipeline.supervisor_worker(
    supervisor=supervisor,
    workers=[
        data_worker.to_agent(),   # Convert pipeline to agent
        code_worker.to_agent(),
        viz_worker.to_agent(),
    ],
)

# Use in a larger sequential pipeline
final_pipeline = Pipeline.sequential([
    Agent(model="gpt-4", agent_type="requirements_analyzer"),
    analysis_pipeline.to_agent(),  # Nested supervisor-worker
    Agent(model="gpt-4", agent_type="report_writer"),
])

result = final_pipeline.run(task="Analyze sales data and create dashboard")
```

### 4.4 Nested Example 2: Ensemble with Supervisor-Worker Agents

```python
# Each analyst is a supervisor-worker team
bullish_team = Pipeline.supervisor_worker(
    supervisor=Agent(model="gpt-4", agent_type="coordinator"),
    workers=[
        Agent(model="gpt-4", agent_type="news_analyst"),
        Agent(model="gpt-4", agent_type="sentiment_analyst"),
    ],
)

bearish_team = Pipeline.supervisor_worker(
    supervisor=Agent(model="gpt-4", agent_type="coordinator"),
    workers=[
        Agent(model="gpt-4", agent_type="risk_analyst"),
        Agent(model="gpt-4", agent_type="technical_analyst"),
    ],
)

# Ensemble of teams
investment_decision = Pipeline.ensemble(
    agents=[
        bullish_team.to_agent(),
        bearish_team.to_agent(),
    ],
    synthesizer=Agent(model="gpt-4", agent_type="cio"),
)

result = investment_decision.run(task="Should we invest in ACME Corp?")
```

### 4.5 Implementation: `.to_agent()` Method

```python
class Pipeline:
    def to_agent(self) -> Agent:
        """
        Convert pipeline to an Agent for composition.

        This allows pipelines to be used anywhere an Agent is expected.
        """
        class PipelineAgent(BaseAgent):
            def __init__(self, pipeline):
                self.pipeline = pipeline

                # Initialize BaseAgent with minimal config
                super().__init__(
                    config={"model": "pipeline", "llm_provider": "pipeline"},
                    signature=Signature(),  # Pass-through signature
                )

            def run(self, **inputs) -> Dict[str, Any]:
                """Delegate to underlying pipeline."""
                return self.pipeline.run(**inputs)

        return PipelineAgent(pipeline=self)
```

**Benefits**:
- ✅ Pipelines are first-class agents
- ✅ Can be nested arbitrarily
- ✅ Uniform interface (`.run()`)
- ✅ Composable building blocks

---

## Part 5: Pipeline Pattern Decision Matrix

### 5.1 The Problem: When to Use Which?

Users need clear guidance on **WHEN** to use each pattern, not just **HOW**.

### 5.2 Decision Matrix

| Pattern | When to Use | When NOT to Use | A2A Integration |
|---------|-------------|-----------------|-----------------|
| **Sequential** | Tasks with clear linear flow (A → B → C), where each step depends on previous | Tasks requiring parallelism, dynamic routing, or iteration | N/A (linear flow) |
| **Supervisor-Worker** | Complex tasks needing intelligent delegation, where supervisor knows which specialist to call | Simple linear tasks, tasks requiring consensus/debate | ✅ **Uses A2A semantic matching** for worker selection |
| **Meta-Controller (Router)** | Known categories of requests, where routing logic is deterministic | Tasks requiring multiple specialists, tasks needing collaboration | ⚠️ Can use A2A for capability matching, but routing is deterministic |
| **Ensemble** | High-stakes decisions requiring multiple perspectives, where diversity of viewpoints matters | Simple tasks, time-sensitive tasks (ensemble is slow) | ⚠️ Can use A2A for agent discovery, but voting/synthesis is manual |
| **Blackboard** | Emergent solutions from opportunistic collaboration, where next step depends on current state | Tasks with known workflow, tasks requiring deterministic execution | ✅ **Uses A2A for dynamic specialist selection** based on blackboard state |
| **Consensus** | Group decision-making requiring agreement, compliance/governance scenarios | Individual decisions, time-sensitive tasks | ⚠️ Can use A2A for agent discovery, but consensus mechanism is separate |
| **Debate** | Adversarial analysis (pros/cons), where challenging assumptions is valuable | Routine tasks, consensus-building scenarios | N/A (fixed proposer/opposer roles) |
| **Handoff** | Sequential specialists with natural handoff points (analyst → developer → tester) | Tasks requiring iteration back to previous steps | N/A (linear handoff) |
| **Parallel** | Independent tasks that can run concurrently, where order doesn't matter | Tasks with dependencies, tasks requiring sequential results | N/A (independent execution) |

### 5.3 A2A Protocol Integration

**What is A2A?**
Google A2A (Agent-to-Agent) protocol provides **capability-based agent discovery** using semantic matching.

**Where Kaizen Uses A2A**:

1. **Supervisor-Worker** (PRIMARY USE)
   - Supervisor analyzes task requirements
   - A2A semantically matches task to worker capabilities
   - NO hardcoded if/else routing logic

   ```python
   # Supervisor uses A2A to select best worker
   supervisor = Agent(model="gpt-4", agent_type="coordinator")

   # Workers declare capabilities via A2A cards
   data_worker = Agent(model="gpt-4", agent_type="data_analyst")
   code_worker = Agent(model="gpt-4", agent_type="code_expert")

   # A2A matches task to capabilities automatically
   pipeline = Pipeline.supervisor_worker(
       supervisor=supervisor,
       workers=[data_worker, code_worker],
       selection_mode="semantic",  # Uses A2A
   )
   ```

2. **Blackboard** (SECONDARY USE)
   - Controller analyzes blackboard state
   - A2A selects next specialist based on current needs
   - Dynamic, opportunistic collaboration

   ```python
   # Blackboard uses A2A for dynamic selection
   pipeline = Pipeline.blackboard(
       specialists=[data, code, viz],
       controller=Agent(model="gpt-4", agent_type="coordinator"),
       selection_mode="semantic",  # Uses A2A
   )
   ```

3. **Ensemble/Consensus** (OPTIONAL USE)
   - A2A can discover compatible agents
   - But voting/synthesis is manual
   - Less critical than Supervisor-Worker

**A2A Implementation**:

```python
# agents/coordination/supervisor_worker.py (CURRENT IMPLEMENTATION)

class SupervisorAgent(BaseAgent):
    def select_worker_for_task(
        self,
        task: Dict[str, Any],
        available_workers: List[BaseAgent],
        return_score: bool = False,
    ) -> Union[BaseAgent, Dict[str, Any]]:
        """
        Select best worker for task using A2A semantic matching.

        Uses Google A2A protocol for capability-based selection.
        NO hardcoded if/else logic!
        """
        if not A2A_AVAILABLE:
            # Fallback to simple selection
            return available_workers[0]

        # Get A2A capability cards from workers
        worker_cards = []
        for worker in available_workers:
            if hasattr(worker, "to_a2a_card"):
                worker_cards.append(worker.to_a2a_card())

        # Semantic matching using A2A
        best_match = self._semantic_match_task_to_capabilities(
            task, worker_cards
        )

        return best_match
```

**Key Insight**: A2A eliminates manual routing logic. The supervisor/controller just describes the task, and A2A finds the best specialist based on declared capabilities.

### 5.4 Detailed Pattern Descriptions

**Sequential Pipeline**
```
Use When:
- Research → Analysis → Report (each depends on previous)
- Data Extract → Transform → Load (ETL workflow)
- Requirements → Design → Implementation

Benefits:
- Simple mental model
- Clear dependencies
- Predictable execution

Trade-offs:
- No parallelism
- No dynamic routing
- Fixed execution order
```

**Supervisor-Worker (WITH A2A)**
```
Use When:
- Complex multi-domain tasks (code + data + viz)
- Unknown specialist requirements upfront
- Need intelligent delegation

Benefits:
- ✅ A2A semantic matching (NO hardcoded routing)
- Parallel worker execution
- Centralized coordination

Trade-offs:
- Supervisor overhead
- More complex debugging
- Requires well-defined capabilities

A2A Advantage:
Supervisor: "I need someone to analyze sales trends"
A2A: Matches to DataAnalystAgent based on capabilities
NO: if task.contains("sales"): route_to(sales_agent)  # ❌ BAD
```

**Meta-Controller (Router)**
```
Use When:
- Known request categories (coding, research, writing)
- Deterministic routing rules
- Single specialist per request

Benefits:
- Fast routing
- Predictable behavior
- No collaboration overhead

Trade-offs:
- Fixed categories
- No multi-specialist tasks
- Manual routing logic

vs Supervisor-Worker:
- Router: Deterministic routing, one specialist
- Supervisor: Semantic matching (A2A), multiple specialists
```

**Ensemble**
```
Use When:
- Investment decisions (bullish + bearish + quant)
- High-stakes predictions
- Need diverse viewpoints

Benefits:
- Reduced bias
- Robust decisions
- Multiple perspectives

Trade-offs:
- Slow (sequential evaluation)
- Expensive (multiple LLM calls)
- Requires synthesis

vs Supervisor-Worker:
- Ensemble: All agents evaluate, then synthesize
- Supervisor: One worker selected, executes alone
```

**Blackboard (WITH A2A)**
```
Use When:
- Emergent solutions (don't know workflow upfront)
- Opportunistic collaboration
- Next step depends on current state

Benefits:
- ✅ A2A dynamic specialist selection
- Flexible workflows
- Adaptive to discoveries

Trade-offs:
- Complex coordination
- Unpredictable execution
- Difficult testing

A2A Advantage:
Blackboard State: "Partial analysis complete, need visualization"
A2A: Dynamically selects VizAgent based on current need
```

**Consensus**
```
Use When:
- Governance/compliance decisions
- Need group agreement
- Conflict resolution

Benefits:
- Democratic decisions
- Builds trust
- Auditable process

Trade-offs:
- Slow (iterative rounds)
- May not reach consensus
- Expensive

vs Debate:
- Consensus: Seeks agreement
- Debate: Seeks best argument
```

**Debate**
```
Use When:
- Pros/cons analysis
- Challenge assumptions
- Adversarial testing

Benefits:
- Robust conclusions
- Identifies weak arguments
- Forced critical thinking

Trade-offs:
- Polarized viewpoints
- No middle ground
- Fixed proposer/opposer

vs Ensemble:
- Debate: Two sides, one wins
- Ensemble: Multiple sides, synthesize
```

---

## Part 6: Revised Implementation Roadmap

### Phase 1: Standardization (Week 1)
- [ ] **Standardize `.run()` method across ALL agents**
  - [ ] Update react.py (add `.run()`, keep `.solve_task()` as alias)
  - [ ] Update simple_qa.py (add `.run()`, keep `.ask()` as alias)
  - [ ] Update vision_agent.py (add `.run()`, keep `.analyze()` as alias)
  - [ ] Update all other specialized agents
  - [ ] Update autonomous agents (base.py, claude_code.py, codex.py)
  - [ ] Update multi_modal agents
  - [ ] Write migration guide

- [ ] **Implement dual registration with inheritance**
  - [ ] Update `register_agent_type()` to auto-call `register_node`
  - [ ] Remove `@register_node()` from all agent classes
  - [ ] Update `register_builtin.py` with all agents
  - [ ] Test both Agent API and Core SDK access

### Phase 2: Reorganization (Week 2)
- [ ] Move `agents/coordination/` → `orchestration/patterns/`
- [ ] Move `coordination/` → `orchestration/core/`
- [ ] Update all imports
- [ ] Update autonomous agents to `agents/autonomous/` structure
- [ ] Test backward compatibility

### Phase 3: Composable Pipelines (Week 3)
- [ ] Implement `Pipeline` base class with `.to_agent()`
- [ ] Implement `Pipeline.sequential()` with composability
- [ ] Implement `Pipeline.supervisor_worker()` with A2A + composability
- [ ] Implement `Pipeline.ensemble()` with composability
- [ ] Implement `Pipeline.router()` (Meta-Controller)
- [ ] Implement `Pipeline.blackboard()` with A2A + composability
- [ ] Write nested pipeline tests
- [ ] Write decision matrix documentation

### Phase 4: Missing Patterns (Week 4)
- [ ] Implement missing single-agent patterns (Planning, PEV, ToT)
- [ ] Enhance Blackboard with full A2A integration
- [ ] Create comprehensive decision matrix documentation
- [ ] Write nested pipeline examples
- [ ] Performance testing for deep nesting

---

## Part 7: Key Decisions for Approval

Please confirm:

1. **✅ Method Standardization**: Approve `.run()` as universal method with backward-compatible aliases?

2. **✅ Dual Registration Inheritance**: Approve `register_agent_type()` auto-calling `@register_node`?

3. **✅ Pre-Defined Agent Migration**: Approve removing `@register_node()` and using `register_agent_type()` for all?

4. **✅ Composable Pipelines**: Approve `.to_agent()` method for arbitrary nesting?

5. **✅ A2A Integration**: Approve Supervisor-Worker and Blackboard using A2A semantic matching?

6. **✅ Decision Matrix**: Approve "when to use which" guidance over just "how to use"?

---

## Appendix: Complete Code Examples

### A.1 Standardized Agent Execution

```python
# react.py (UPDATED)

class ReActAgent(BaseAgent):
    # PRIMARY METHOD
    def run(self, task: str, context: str = "", **kwargs) -> Dict[str, Any]:
        """
        Universal execution method (recommended).

        Args:
            task: Task to solve
            context: Optional context
            **kwargs: Additional parameters

        Returns:
            Dict with thought, action, confidence, etc.
        """
        return super().run(task=task, context=context, **kwargs)

    # BACKWARD COMPATIBILITY ALIAS
    def solve_task(self, task: str, context: str = "", **kwargs) -> Dict[str, Any]:
        """
        Convenience alias for .run() (backward compatibility).

        DEPRECATED: Use .run() instead.
        """
        return self.run(task=task, context=context, **kwargs)
```

### A.2 Dual Registration (ALL Agents)

```python
# agents/register_builtin.py

from kaizen.agents.registry import register_agent_type
from kaizen.strategies.multi_cycle import MultiCycleStrategy

# Specialized agents
from kaizen.agents.specialized.react import ReActAgent
from kaizen.agents.specialized.simple_qa import SimpleQAAgent
# ... more imports

# Autonomous agents
from kaizen.agents.autonomous.base import AutonomousAgent
from kaizen.agents.autonomous.claude_code import ClaudeCodeAgent
from kaizen.agents.autonomous.codex import CodexAgent

def register_builtin_agents():
    """
    Register all builtin agents with DUAL registration:
    - Agent API (for Agent(agent_type="..."))
    - Core SDK (for WorkflowBuilder)
    """

    # Specialized agents
    register_agent_type(
        name="react",
        agent_class=ReActAgent,
        description="Reasoning + Acting cycles",
        default_strategy=MultiCycleStrategy,
        preset_config={"max_cycles": 10},
        category="specialized",
        tags=["reasoning", "tool-use", "iterative"],
    )  # ← Auto-registers for BOTH Agent API + Core SDK!

    register_agent_type(
        name="simple",
        agent_class=SimpleQAAgent,
        description="Simple Q&A",
        category="specialized",
        tags=["qa", "simple"],
    )

    # Autonomous agents
    register_agent_type(
        name="autonomous",
        agent_class=AutonomousAgent,
        description="Fully autonomous agent with planning",
        category="autonomous",
        tags=["autonomous", "planning", "self-directed"],
    )

    register_agent_type(
        name="claude_code",
        agent_class=ClaudeCodeAgent,
        description="Claude Code autonomous agent",
        category="autonomous",
        tags=["autonomous", "code", "claude"],
    )

    # ... more registrations
```

### A.3 Nested Pipeline (Complex Example)

```python
"""
Real-World Example: Investment Analysis Pipeline

Architecture:
- Sequential outer pipeline (data → analysis → decision → report)
- Supervisor-Worker for analysis (each worker is a sequential pipeline)
- Ensemble for final decision (multiple perspectives)
"""

from kaizen import Agent
from kaizen.orchestration import Pipeline

# Step 1: Data Collection (simple agent)
data_collector = Agent(model="gpt-4", agent_type="simple")

# Step 2: Analysis (Supervisor-Worker with Sequential Workers)

# Data Analysis Worker = Sequential pipeline
data_analysis_pipeline = Pipeline.sequential([
    Agent(model="gpt-4", agent_type="data_extractor"),
    Agent(model="gpt-4", agent_type="data_validator"),
    Agent(model="gpt-4", agent_type="data_analyzer"),
])

# Technical Analysis Worker = Sequential pipeline
technical_analysis_pipeline = Pipeline.sequential([
    Agent(model="gpt-4", agent_type="chart_analyzer"),
    Agent(model="gpt-4", agent_type="indicator_calculator"),
])

# News Analysis Worker = Sequential pipeline
news_analysis_pipeline = Pipeline.sequential([
    Agent(model="gpt-4", agent_type="news_scraper"),
    Agent(model="gpt-4", agent_type="sentiment_analyzer"),
])

# Supervisor delegates to workers (each worker is a pipeline!)
analysis_supervisor = Agent(model="gpt-4", agent_type="coordinator")
analysis_stage = Pipeline.supervisor_worker(
    supervisor=analysis_supervisor,
    workers=[
        data_analysis_pipeline.to_agent(),      # ← Pipeline as agent!
        technical_analysis_pipeline.to_agent(),
        news_analysis_pipeline.to_agent(),
    ],
    selection_mode="semantic",  # A2A matching
)

# Step 3: Decision (Ensemble of Specialists)
decision_stage = Pipeline.ensemble(
    agents=[
        Agent(model="gpt-4", agent_type="bullish_analyst"),
        Agent(model="gpt-4", agent_type="bearish_analyst"),
        Agent(model="gpt-4", agent_type="quant_analyst"),
    ],
    synthesizer=Agent(model="gpt-4", agent_type="cio"),
)

# Step 4: Report Writer (simple agent)
report_writer = Agent(model="gpt-4", agent_type="report_writer")

# FINAL: Sequential outer pipeline combining all stages
investment_pipeline = Pipeline.sequential([
    data_collector,                  # Simple agent
    analysis_stage.to_agent(),       # Supervisor-Worker (nested pipelines)
    decision_stage.to_agent(),       # Ensemble
    report_writer,                   # Simple agent
])

# Execute entire nested pipeline
result = investment_pipeline.run(
    task="Analyze ACME Corp for investment decision"
)

print("Investment Decision:", result["decision"])
print("Confidence:", result["confidence"])
print("Report:", result["report"][:200])
```

---

**END OF REVISED PROPOSAL**
