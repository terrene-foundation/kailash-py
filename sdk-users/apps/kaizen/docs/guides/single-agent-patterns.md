# Single-Agent Patterns - Complete Guide

## Overview

Kaizen provides **6 single-agent patterns** for different reasoning and execution workflows. This guide helps you choose the right pattern for your task.

**Available Patterns**:
1. **Planning** - Plan Before You Act (Plan → Validate → Execute)
2. **PEV** - Plan, Execute, Verify, Refine (Iterative refinement loop)
3. **Tree-of-Thoughts** - Multi-Path Exploration (Generate N → Evaluate → Select)
4. **ReAct** - Reasoning + Action Cycles (Think → Act → Observe, repeat)
5. **Chain-of-Thought** - Step-by-Step Reasoning (Linear reasoning chain)
6. **SimpleQA** - Direct Question Answering (Single-shot response)

## Pattern Selection Flowchart

```
START: What type of task do you have?

┌─ Single Q&A, no workflow needed?
│  └─ YES → SimpleQA
│  └─ NO  → Continue

┌─ Need upfront structured plan?
│  ├─ YES: Pre-execution validation critical?
│  │  ├─ YES → Planning Agent
│  │  └─ NO: Post-execution verification critical?
│  │     ├─ YES → PEV Agent
│  │     └─ NO → Planning Agent
│  └─ NO → Continue

┌─ Need to explore multiple alternatives?
│  └─ YES → Tree-of-Thoughts
│  └─ NO  → Continue

┌─ Need real-time adaptation based on observations?
│  └─ YES → ReAct
│  └─ NO  → Chain-of-Thought
```

## Comprehensive Comparison Matrix

### High-Level Comparison

| Pattern | Planning Phase | Verification | Iteration | Multi-Path | Real-Time | Best For |
|---------|---------------|--------------|-----------|------------|-----------|----------|
| **Planning** | ✅ Complete upfront | Pre-execution | Single (or replan) | ❌ | ❌ | Structured workflows, critical validation |
| **PEV** | ✅ Initial plan | Post-execution | Multiple refine cycles | ❌ | ❌ | Quality-critical, iterative refinement |
| **Tree-of-Thoughts** | ❌ | Score evaluation | Single generation | ✅ N paths | ❌ | Strategic decisions, alternatives |
| **ReAct** | ❌ | Observation-based | Variable action cycles | ❌ | ✅ | Dynamic, real-time adaptation |
| **Chain-of-Thought** | ❌ | ❌ | Single reasoning | ❌ | ❌ | Step-by-step reasoning |
| **SimpleQA** | ❌ | ❌ | Single-shot | ❌ | ❌ | Simple Q&A, no workflow |

### Detailed Feature Comparison

#### Pattern Characteristics

| Feature | Planning | PEV | ToT | ReAct | CoT | SimpleQA |
|---------|----------|-----|-----|-------|-----|----------|
| **Upfront Planning** | ✅ Complete | ✅ Initial | ❌ | ❌ | ❌ | ❌ |
| **Pre-Execution Validation** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Post-Execution Verification** | ❌ | ✅ | ✅ Scores | ✅ Observations | ❌ | ❌ |
| **Iterative Refinement** | Replan only | ✅ Multiple | ❌ | ✅ Variable | ❌ | ❌ |
| **Multi-Path Exploration** | ❌ | ❌ | ✅ N paths | ❌ | ❌ | ❌ |
| **Real-Time Adaptation** | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| **Tool Calling** | Optional | Optional | Optional | ✅ Integral | Optional | Optional |
| **Structured Output** | ✅ | ✅ | ✅ | ✅ | Reasoning only | ❌ |

#### Performance Characteristics

| Metric | Planning | PEV | ToT | ReAct | CoT | SimpleQA |
|--------|----------|-----|-----|-------|-----|----------|
| **Latency** | 5-10s | 15-30s (5 iter) | 5-10s (parallel) | Variable | 2-5s | 1-2s |
| **Cost** | 1× | 5× (iterations) | 5× (N paths) | Variable | 1× | 1× |
| **Memory** | ~50MB | ~100MB | ~50MB × N | Variable | ~30MB | ~20MB |
| **Concurrency** | Sequential | Sequential | ✅ Parallel | Sequential | Single | Single |

#### Use Case Suitability

| Use Case | Planning | PEV | ToT | ReAct | CoT | SimpleQA |
|----------|----------|-----|-----|-------|-----|----------|
| **Research Reports** | ✅✅✅ | ✅✅ | ✅ | ✅ | ✅ | ❌ |
| **Code Generation** | ✅✅ | ✅✅✅ | ✅ | ✅✅ | ✅ | ❌ |
| **Strategic Decisions** | ✅✅ | ✅ | ✅✅✅ | ✅ | ✅✅ | ❌ |
| **Dynamic Troubleshooting** | ❌ | ❌ | ❌ | ✅✅✅ | ✅ | ❌ |
| **Math Problems** | ✅ | ✅ | ✅ | ✅ | ✅✅✅ | ❌ |
| **Simple Q&A** | ❌ | ❌ | ❌ | ❌ | ✅ | ✅✅✅ |
| **Compliance Workflows** | ✅✅✅ | ✅✅ | ❌ | ✅ | ❌ | ❌ |
| **Creative Content** | ✅✅ | ✅✅ | ✅✅✅ | ✅ | ✅✅ | ❌ |
| **Data Pipelines** | ✅✅✅ | ✅✅ | ✅ | ✅ | ❌ | ❌ |

**Legend**: ✅✅✅ Best fit, ✅✅ Good fit, ✅ Acceptable, ❌ Not suitable

## Pattern Deep Dives

### 1. Planning Agent - Plan Before You Act

**Pattern**: Generate complete plan → Validate feasibility → Execute validated plan

**Three-Phase Workflow**:
1. **Plan**: Generate detailed execution plan with steps and dependencies
2. **Validate**: Check plan feasibility, structure, and completeness
3. **Execute**: Execute validated plan step-by-step

**When to Use**:
- Complex multi-step tasks requiring upfront planning
- Critical operations needing validation before execution
- Structured deliverables with clear steps and dependencies
- Resource planning where feasibility must be checked first
- Audit requirements needing validated plans

**Configuration**:
```python
from kaizen.agents.specialized.planning import PlanningAgent, PlanningConfig

config = PlanningConfig(
    max_plan_steps=10,         # Limit plan complexity
    validation_mode="strict",  # strict, warn, off
    enable_replanning=True     # Replan on validation failure
)
```

**Key Parameters**:
- `max_plan_steps`: Maximum plan steps (prevents over-planning)
- `validation_mode`: Pre-execution validation strictness
- `enable_replanning`: Auto-replan on validation failure

**See**: [Planning Agent Guide](./planning-agent.md)

### 2. PEV Agent - Plan, Execute, Verify, Refine

**Pattern**: Create plan → Execute → Verify quality → Refine based on feedback (iterative loop)

**Iterative Workflow**:
1. **Plan**: Create initial execution plan
2. **Execute**: Execute the plan
3. **Verify**: Check result quality against criteria
4. **Refine**: Improve plan based on verification feedback
5. Repeat steps 2-4 until verified or max iterations

**When to Use**:
- Quality-critical outputs (code generation, document writing)
- Verification-driven workflows with measurable quality criteria
- Iterative improvement needed to reach target quality
- Feedback-based optimization

**Configuration**:
```python
from kaizen.agents.specialized.pev import PEVAgent, PEVAgentConfig

config = PEVAgentConfig(
    max_iterations=5,                      # Maximum refinement cycles
    verification_strictness="medium",      # strict, medium, lenient
    enable_error_recovery=True             # Recover from errors
)
```

**Key Parameters**:
- `max_iterations`: Maximum refinement cycles (prevents infinite loops)
- `verification_strictness`: Post-execution verification level
- `enable_error_recovery`: Attempt recovery from execution errors

**See**: [PEV Agent Guide](./pev-agent.md)

### 3. Tree-of-Thoughts Agent - Multi-Path Exploration

**Pattern**: Generate N parallel paths → Evaluate each → Select best → Execute winner

**Multi-Path Workflow**:
1. **Generate**: Create N independent reasoning paths (in parallel if enabled)
2. **Evaluate**: Score each path using evaluation criteria
3. **Select**: Choose path with highest score
4. **Execute**: Execute only the best path

**When to Use**:
- Multiple valid approaches exist, need to explore alternatives
- Strategic decision-making where diverse perspectives improve outcomes
- Creative problem-solving benefiting from alternative solutions
- Uncertainty about optimal path

**Configuration**:
```python
from kaizen.agents.specialized.tree_of_thoughts import ToTAgent, ToTAgentConfig

config = ToTAgentConfig(
    num_paths=5,                # Number of alternative paths
    temperature=0.9,            # HIGH for diversity (0.8-1.0)
    evaluation_criteria="quality",  # quality, speed, creativity
    parallel_execution=True     # Generate paths in parallel
)
```

**Key Parameters**:
- `num_paths`: Number of paths to explore (3-7 typical, max 20)
- `temperature`: MUST be high (0.9) for path diversity
- `evaluation_criteria`: How to score paths
- `parallel_execution`: Enable parallel generation (much faster)

**See**: [Tree-of-Thoughts Guide](./tree-of-thoughts-agent.md)

### 4. ReAct Agent - Reasoning + Action Cycles

**Pattern**: Think → Act → Observe → Repeat

**Iterative Workflow**:
1. **Reasoning**: Analyze current situation and plan next action
2. **Action**: Execute action using tools
3. **Observation**: Observe action results
4. Repeat until task complete

**When to Use**:
- Dynamic environments requiring real-time adaptation
- Tool-heavy workflows (file operations, API calls, web search)
- Exploratory tasks where path forward is unclear
- Observation-driven decision making

**Configuration**:
```python
from kaizen.agents import ReActAgent
from kaizen.agents.autonomous.react import ReActConfig

config = ReActConfig(
    max_cycles=10,  # Maximum reasoning-action cycles
    # Tool calling automatically enabled
)
```

**Key Feature**: Autonomous tool calling with 12 builtin tools (file, HTTP, bash, web)

**See**: Kaizen documentation for ReAct patterns

### 5. Chain-of-Thought Agent - Step-by-Step Reasoning

**Pattern**: Single linear reasoning chain

**Reasoning Workflow**:
1. Break down problem into intermediate steps
2. Solve each step sequentially
3. Combine steps into final answer

**When to Use**:
- Complex reasoning tasks benefiting from step-by-step approach
- Math problems, logic puzzles
- Transparent reasoning required
- No workflow orchestration needed

**Configuration**:
```python
from kaizen.agents import ChainOfThoughtAgent
from kaizen.agents.specialized.chain_of_thought import CoTConfig

config = CoTConfig(
    # Standard LLM configuration
    llm_provider="openai",
    model="gpt-4"
)
```

**See**: Kaizen documentation for CoT patterns

### 6. SimpleQA Agent - Direct Question Answering

**Pattern**: Single-shot question-answer

**Simple Workflow**:
1. Receive question
2. Generate answer
3. Return response

**When to Use**:
- Simple question answering
- No workflow needed
- Fast single-shot responses
- Lookup tasks

**Configuration**:
```python
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

config = QAConfig(
    llm_provider="openai",
    model="gpt-3.5-turbo"
)
```

**See**: Kaizen documentation for SimpleQA patterns

## Real-World Use Cases by Pattern

### Research & Reports
| Task | Best Pattern | Why |
|------|--------------|-----|
| Academic paper analysis | **Planning** | Multi-step workflow, structured deliverable |
| Literature review | **PEV** | Iterative improvement, quality verification |
| Market research report | **Planning** | Upfront structure, validation before writing |
| Competitive analysis | **Tree-of-Thoughts** | Multiple perspectives, select best insights |

### Software Development
| Task | Best Pattern | Why |
|------|--------------|-----|
| Code generation with tests | **PEV** | Iterative refinement, quality verification |
| Debugging | **ReAct** | Real-time adaptation, tool calling |
| Architecture design | **Tree-of-Thoughts** | Explore alternatives, evaluate trade-offs |
| Code review | **Chain-of-Thought** | Step-by-step reasoning |

### Business & Strategy
| Task | Best Pattern | Why |
|------|--------------|-----|
| Go-to-market strategy | **Tree-of-Thoughts** | Multiple alternatives, select best |
| Project planning | **Planning** | Structured workflow, resource validation |
| Process optimization | **PEV** | Iterative improvement based on metrics |
| Market entry decision | **Tree-of-Thoughts** | Explore options, evaluate risks |

### Data & Analytics
| Task | Best Pattern | Why |
|------|--------------|-----|
| Data pipeline design | **Planning** | Multi-step workflow, dependency validation |
| ETL workflow | **Planning** | Structured execution, validation |
| Data quality improvement | **PEV** | Iterative refinement, quality verification |
| Schema design | **Tree-of-Thoughts** | Explore alternatives, select best |

### Compliance & Legal
| Task | Best Pattern | Why |
|------|--------------|-----|
| Compliance workflow | **Planning** | Strict validation, audit trail |
| Contract analysis | **Chain-of-Thought** | Step-by-step reasoning |
| Risk assessment | **Tree-of-Thoughts** | Multiple scenarios, evaluate risks |
| Policy generation | **PEV** | Iterative refinement, compliance verification |

## Pattern Combination Strategies

### Sequential Combination
Use multiple patterns in sequence for complex workflows:

```python
# Step 1: Explore alternatives with ToT
tot_agent = ToTAgent(ToTAgentConfig(num_paths=5))
alternatives = tot_agent.run(task="Explore design alternatives")

# Step 2: Create detailed plan from best alternative
planning_agent = PlanningAgent(PlanningConfig())
plan = planning_agent.run(
    task=f"Create execution plan for: {alternatives['final_result']}"
)

# Step 3: Execute with refinement using PEV
pev_agent = PEVAgent(PEVAgentConfig(max_iterations=5))
final_result = pev_agent.run(task=plan['final_result'])
```

### Multi-Agent Ensemble
Combine patterns in ensemble for consensus:

```python
from kaizen.orchestration.patterns import EnsemblePattern

# Create agents with different patterns
planning_agent = PlanningAgent(PlanningConfig())
pev_agent = PEVAgent(PEVAgentConfig())
tot_agent = ToTAgent(ToTAgentConfig(num_paths=3))

# Use ensemble to synthesize perspectives
pattern = EnsemblePattern(
    agents=[planning_agent, pev_agent, tot_agent],
    synthesizer=synthesis_agent
)

result = pattern.run(task="Complex decision requiring multiple perspectives")
```

### Supervisor-Worker with Pattern Specialization
Route tasks to pattern-specific agents:

```python
from kaizen.orchestration.patterns import SupervisorWorkerPattern

# Create specialized workers
structured_worker = PlanningAgent(PlanningConfig())
quality_worker = PEVAgent(PEVAgentConfig())
creative_worker = ToTAgent(ToTAgentConfig())

# Supervisor routes based on task characteristics
pattern = SupervisorWorkerPattern(
    supervisor=supervisor_agent,
    workers=[structured_worker, quality_worker, creative_worker],
    coordinator=coordinator,
    shared_pool=shared_pool
)

# Supervisor uses A2A to route:
# - Structured tasks → Planning
# - Quality-critical → PEV
# - Creative/strategic → ToT
```

## Migration Guide

### Upgrading from SimpleQA
If your SimpleQA tasks have grown complex:

```python
# Before: SimpleQA
from kaizen.agents import SimpleQAAgent
agent = SimpleQAAgent(QAConfig())
result = agent.ask("Complex multi-step task")

# After: Planning (if structured workflow needed)
from kaizen.agents.specialized.planning import PlanningAgent
agent = PlanningAgent(PlanningConfig(max_plan_steps=5))
result = agent.run(task="Complex multi-step task")

# After: PEV (if quality refinement needed)
from kaizen.agents.specialized.pev import PEVAgent
agent = PEVAgent(PEVAgentConfig(max_iterations=5))
result = agent.run(task="Complex multi-step task")
```

### Upgrading from CoT
If your CoT tasks need structure or verification:

```python
# Before: Chain-of-Thought
from kaizen.agents import ChainOfThoughtAgent
agent = ChainOfThoughtAgent(CoTConfig())
result = agent.run(question="Complex task")

# After: Planning (if workflow structure needed)
agent = PlanningAgent(PlanningConfig())
result = agent.run(task="Complex task")

# After: ToT (if alternatives needed)
agent = ToTAgent(ToTAgentConfig(num_paths=5))
result = agent.run(task="Complex task")
```

### Upgrading from ReAct
If your ReAct tasks are more structured than dynamic:

```python
# Before: ReAct
from kaizen.agents import ReActAgent
agent = ReActAgent(ReActConfig(max_cycles=10))
result = agent.run(task="Structured task")

# After: Planning (if structure is main need)
agent = PlanningAgent(PlanningConfig())
result = agent.run(task="Structured task")

# After: PEV (if verification is main need)
agent = PEVAgent(PEVAgentConfig())
result = agent.run(task="Structured task")
```

## Best Practices

### 1. Choose Pattern Based on Task Characteristics
- **Structured workflow** → Planning
- **Quality refinement** → PEV
- **Alternative exploration** → ToT
- **Real-time adaptation** → ReAct
- **Step-by-step reasoning** → CoT
- **Simple Q&A** → SimpleQA

### 2. Start Simple, Upgrade as Needed
```python
# Start with SimpleQA
result = SimpleQAAgent().ask("Task")

# If insufficient, upgrade to Planning
result = PlanningAgent().run(task="Task")

# If quality issues, upgrade to PEV
result = PEVAgent().run(task="Task")

# If need alternatives, upgrade to ToT
result = ToTAgent().run(task="Task")
```

### 3. Use Appropriate Configuration
- **Planning**: Set `max_plan_steps` to task complexity
- **PEV**: Set `max_iterations` based on quality requirements
- **ToT**: Use `temperature=0.9` for diversity, `num_paths` for breadth

### 4. Monitor Performance Metrics
- **Latency**: Planning < PEV < ToT (for same N)
- **Cost**: Single-shot < Planning < PEV < ToT
- **Quality**: ToT exploration or PEV refinement for highest quality

### 5. Combine Patterns for Complex Workflows
Use sequential combination, ensemble, or supervisor-worker patterns for complex tasks requiring multiple reasoning approaches.

## Troubleshooting

### Common Issues

**Problem**: Planning generates too many steps
- **Solution**: Reduce `max_plan_steps`

**Problem**: PEV never reaches verification
- **Solution**: Lower `verification_strictness` or increase `max_iterations`

**Problem**: ToT paths are too similar
- **Solution**: Increase `temperature` to 0.9 or higher

**Problem**: Pattern choice unclear
- **Solution**: Use decision flowchart above or try SimpleQA first, upgrade as needed

## See Also

- **[Planning Agent Guide](./planning-agent.md)** - Complete Planning documentation
- **[PEV Agent Guide](./pev-agent.md)** - Complete PEV documentation
- **[Tree-of-Thoughts Guide](./tree-of-thoughts-agent.md)** - Complete ToT documentation
- **[Multi-Agent Coordination](./multi-agent-coordination.md)** - Combining patterns
- **[API Reference](../reference/api-reference.md)** - Complete API documentation
