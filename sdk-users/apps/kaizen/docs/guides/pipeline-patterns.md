# Pipeline Patterns Guide

## Overview

**Kaizen Pipeline Patterns** (v0.5.0+) provide composable multi-step workflows with A2A integration for semantic agent selection. All 9 patterns are production-ready and can be converted to BaseAgent via `.to_agent()`.

**Key Features:**
- **9 Pattern Types**: Sequential, Supervisor-Worker, Router, Ensemble, Blackboard, Consensus, Debate, Handoff, Parallel
- **A2A Integration**: 4 patterns use semantic capability matching (Router, Supervisor-Worker, Ensemble, Blackboard)
- **Composability**: All patterns can be nested and converted to BaseAgent
- **Factory Methods**: Clean API via `Pipeline.pattern_name()` static methods
- **Production Ready**: Tested, validated, backward compatible

---

## Pattern Catalog

### 1. Sequential Pipeline

**When to use:** Linear step-by-step processing where each step depends on the previous output.

**Factory method:** `Pipeline.sequential()`

**Example:**
```python
from kaizen.orchestration.pipeline import Pipeline
from kaizen.agents import SimpleQAAgent, CodeGenerationAgent

# ETL pipeline: Extract → Transform → Load
pipeline = Pipeline.sequential(
    agents=[extractor, transformer, loader]
)

result = pipeline.run(input="raw_data.csv")
print(result['final_output'])  # Last agent's output
print(result['intermediate_results'])  # All outputs
```

**Use Cases:**
- ETL workflows (extract, transform, load)
- Document processing pipelines
- Data transformation chains
- Any linear workflow with dependencies

**A2A Integration:** None (deterministic order)

**Gotchas:**
- Each agent's output must be compatible with next agent's input
- Failures cascade (use error handling)
- No parallelism (use Parallel pattern if independent)

---

### 2. Supervisor-Worker Pattern

**When to use:** Task decomposition with central coordination and semantic worker selection based on capability matching.

**Factory method:** `Pipeline.supervisor_worker()`

**Example:**
```python
pipeline = Pipeline.supervisor_worker(
    supervisor=supervisor_agent,
    workers=[code_expert, data_expert, writing_expert],
    selection_mode="semantic"  # A2A capability matching
)

# Supervisor decomposes and delegates
tasks = pipeline.delegate("Process 100 documents")

# Aggregate results
results = pipeline.aggregate_results(tasks[0]["request_id"])
```

**Use Cases:**
- Document processing at scale (100+ documents)
- Multi-domain task decomposition
- Load balancing across specialists
- Enterprise batch processing

**A2A Integration:** ✅ **Semantic worker selection** - Automatically routes tasks to best worker based on A2A capability matching

**Gotchas:**
- Supervisor must have task decomposition capability
- Workers should have distinct specialties for best routing
- Use `selection_mode="semantic"` for A2A (default)

---

### 3. Router (Meta-Controller) Pattern

**When to use:** Intelligent request routing to the best agent based on task requirements via A2A capability matching.

**Factory method:** `Pipeline.router()`

**Example:**
```python
pipeline = Pipeline.router(
    agents=[code_agent, data_agent, writing_agent],
    routing_strategy="semantic",  # A2A-based routing
    error_handling="graceful"
)

result = pipeline.run(
    task="Write a Python function to analyze data",
    input="sales.csv"
)

# Router automatically selects best agent (code_agent in this case)
```

**Use Cases:**
- API gateway for multi-agent systems
- Single request routing (not task decomposition)
- Dynamic agent selection based on request content
- Load balancing with semantic awareness

**A2A Integration:** ✅ **Semantic routing** - Routes each request to the best agent via A2A capability matching. Falls back to round-robin when A2A unavailable.

**Gotchas:**
- Always provide `task` parameter for best routing accuracy
- Don't hardcode routing logic - use semantic routing
- Fallback to round-robin when A2A unavailable (graceful)
- Set `error_handling="graceful"` for production

---

### 4. Ensemble Pattern

**When to use:** Multi-perspective analysis where diverse viewpoints improve result quality.

**Factory method:** `Pipeline.ensemble()`

**Example:**
```python
pipeline = Pipeline.ensemble(
    agents=[code_agent, data_agent, writing_agent, research_agent],
    synthesizer=synthesis_agent,
    discovery_mode="a2a",  # A2A agent discovery
    top_k=3  # Select top 3 agents
)

result = pipeline.run(
    task="Analyze codebase and suggest improvements",
    input="repository_path"
)

# Returns synthesized perspective from top-3 agents
```

**Use Cases:**
- Code review requiring multiple perspectives
- Critical decision analysis
- Document review with expert panel
- Any task benefiting from diverse viewpoints

**A2A Integration:** ✅ **Agent discovery** - Automatically selects top-k agents with best capability matches via A2A. Synthesizer combines their perspectives.

**Gotchas:**
- Set `top_k` appropriately (3-5 agents typical, avoid 10+)
- Ensure synthesizer can handle multiple perspectives
- Use `discovery_mode="all"` only for small agent pools (<10 agents)
- Synthesizer quality critical to final result

---

### 5. Blackboard Pattern

**When to use:** Complex problems requiring iterative collaboration and dynamic specialist selection based on evolving state.

**Factory method:** `Pipeline.blackboard()`

**Example:**
```python
pipeline = Pipeline.blackboard(
    specialists=[problem_solver, data_analyst, optimizer, validator],
    controller=controller_agent,
    selection_mode="semantic",  # A2A specialist selection
    max_iterations=5
)

result = pipeline.run(
    task="Solve complex optimization problem",
    input="problem_definition"
)

# Iteratively selects specialists until controller determines convergence
```

**Use Cases:**
- Complex optimization problems
- Iterative refinement workflows
- Problems requiring dynamic expertise
- Multi-stage problem solving

**A2A Integration:** ✅ **Dynamic specialist selection** - Iteratively selects specialists based on evolving blackboard state using A2A. Controller determines convergence.

**Gotchas:**
- Set `max_iterations` to prevent infinite loops (5-10 typical)
- Controller must have clear convergence criteria
- Blackboard state should be self-contained
- Monitor iteration count for performance

---

### 6. Consensus Pattern

**When to use:** Democratic decision-making requiring agreement across multiple voters.

**Factory method:** `Pipeline.consensus()`

**Example:**
```python
pipeline = Pipeline.consensus(
    agents=[technical_expert, business_expert, legal_expert],
    threshold=0.67,  # 2 out of 3 must agree (67% threshold)
    voting_strategy="majority"
)

# Create proposal
proposal = pipeline.create_proposal("Should we adopt AI technology?")

# Voters vote
for voter in pipeline.voters:
    voter.vote(proposal)

# Determine consensus
result = pipeline.determine_consensus(proposal["proposal_id"])
print(f"Decision: {result['decision']}, Agreement: {result['agreement']}")
```

**Use Cases:**
- Multi-stakeholder decisions
- Risk mitigation through agreement
- Policy decisions requiring consensus
- Democratic voting systems

**A2A Integration:** None (voting-based decision, not capability matching)

**Gotchas:**
- Set threshold appropriately (0.5 for majority, 1.0 for unanimous, 0.67 for super-majority)
- Ensure voters have sufficient context for informed voting
- Use `voting_strategy="weighted"` for expert panels
- Handle tie-breaking scenarios

---

### 7. Debate Pattern

**When to use:** Adversarial analysis to explore tradeoffs, strengthen arguments, and expose weaknesses.

**Factory method:** `Pipeline.debate()`

**Example:**
```python
pipeline = Pipeline.debate(
    agents=[proponent_agent, opponent_agent],
    rounds=3,
    judge=judge_agent
)

result = pipeline.debate(
    topic="Should AI be regulated?",
    context="Considering safety and innovation"
)

print(f"Winner: {result['judgment']['winner']}")
print(f"Reasoning: {result['judgment']['reasoning']}")
```

**Use Cases:**
- Critical decision analysis
- Exploring tradeoffs and alternatives
- Strengthening arguments through rebuttals
- Risk assessment with opposing views

**A2A Integration:** None (adversarial fixed roles: proponent, opponent, judge)

**Gotchas:**
- Set rounds appropriately (3-5 typical, avoid 10+)
- Judge must be neutral and capable
- Provide sufficient context for informed debate
- Ensure proponent and opponent have opposing incentives

---

### 8. Handoff Pattern

**When to use:** Tier escalation where task complexity determines which tier handles the request.

**Factory method:** `Pipeline.handoff()`

**Example:**
```python
pipeline = Pipeline.handoff(
    agents=[tier1_agent, tier2_agent, tier3_agent]
)

result = pipeline.execute_with_handoff(
    task="Debug complex distributed system issue",
    max_tier=3
)

print(f"Handled by tier: {result['final_tier']}")
print(f"Escalations: {result['escalation_count']}")
```

**Use Cases:**
- Customer support escalation
- Technical support tiers
- Healthcare triage systems
- Any tiered service model

**A2A Integration:** None (tier-based escalation, not capability matching)

**Gotchas:**
- Each tier must evaluate its capability before escalating
- Avoid unnecessary escalations (inefficient, costly)
- Tier 1 should handle 70-80% of requests
- Set `max_tier` to prevent infinite escalation

---

### 9. Parallel Pattern

**When to use:** Independent tasks that can execute concurrently for 10-100x speedup.

**Factory method:** `Pipeline.parallel()`

**Example:**
```python
def custom_aggregator(results):
    """Combine results from parallel agents."""
    return {"combined": " | ".join(r["output"] for r in results)}

pipeline = Pipeline.parallel(
    agents=[agent1, agent2, agent3],
    aggregator=custom_aggregator,
    max_workers=5,
    timeout=30.0,  # 30 second timeout per agent
    error_handling="graceful"
)

result = pipeline.run(input="test_data")
```

**Use Cases:**
- Batch processing (100+ documents)
- Independent data transformations
- Fan-out/fan-in patterns
- Any parallelizable workload

**A2A Integration:** None (parallel execution, not selective)

**Gotchas:**
- Set `max_workers` to prevent resource exhaustion
- Set `timeout` for long-running agents
- Use `error_handling="graceful"` for production (partial results)
- Ensure agents are truly independent (no shared state)

---

## Pattern Selection Decision Matrix

| Pattern | Task Decomposition | Semantic Selection (A2A) | Parallel Execution | Iterative | Democratic | Adversarial | Tiered |
|---------|-------------------|--------------------------|-------------------|-----------|------------|-------------|--------|
| **Sequential** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Supervisor-Worker** | ✅ | ✅ | Optional | ❌ | ❌ | ❌ | ❌ |
| **Router** | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Ensemble** | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Blackboard** | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| **Consensus** | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ |
| **Debate** | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ |
| **Handoff** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Parallel** | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |

---

## Quick Selection Guide

**Need A2A semantic matching?**
→ Router, Supervisor-Worker, Ensemble, Blackboard

**Need parallel execution?**
→ Parallel, Ensemble, Consensus

**Need iterative refinement?**
→ Blackboard, Debate

**Need democratic decision?**
→ Consensus

**Need adversarial analysis?**
→ Debate

**Need tier escalation?**
→ Handoff

**Need linear processing?**
→ Sequential

---

## Composability & Integration

### Converting Pipelines to Agents

All pipelines can be converted to BaseAgent via `.to_agent()`:

```python
from kaizen.orchestration.pipeline import Pipeline

# Create custom pipeline
class DataPipeline(Pipeline):
    def run(self, **inputs):
        # Multi-step processing
        return {"processed": True}

# Convert to BaseAgent
agent = DataPipeline().to_agent(
    name="data_processor",
    description="Processes and validates data"
)

# Now usable anywhere BaseAgent is expected
```

### Using Pipelines in Multi-Agent Patterns

Pipelines can be workers in Supervisor-Worker or other coordination patterns:

```python
from kaizen.orchestration.pipeline import Pipeline
from kaizen.orchestration.patterns import SupervisorWorkerPattern

# Create pipelines
doc_pipeline = Pipeline.sequential([extract, transform, load]).to_agent("doc_processor")
data_pipeline = Pipeline.parallel([analyze1, analyze2, analyze3]).to_agent("data_analyzer")

# Use in multi-agent pattern
pattern = SupervisorWorkerPattern(
    supervisor=supervisor,
    workers=[
        doc_pipeline,    # Pipeline as worker
        data_pipeline,   # Pipeline as worker
        qa_agent         # Regular agent
    ],
    coordinator=coordinator,
    shared_pool=shared_pool
)

# Supervisor routes tasks to pipelines like any agent
result = pattern.execute_task("Process 100 documents")
```

### Nesting Pipelines

Pipelines can be nested for modular design:

```python
# Sub-pipelines
cleaning_pipeline = Pipeline.sequential([clean1, clean2, clean3])
transform_pipeline = Pipeline.parallel([transform1, transform2])

# Master pipeline using sub-pipelines
master = Pipeline.sequential([
    cleaning_pipeline.to_agent("cleaner"),
    transform_pipeline.to_agent("transformer"),
    loader_agent
])

result = master.run(data="raw_data")
```

---

## A2A Integration Details

### Patterns with A2A (4 total)

| Pattern | A2A Feature | Benefit |
|---------|-------------|---------|
| **Router** | Semantic routing | Automatically routes to best agent |
| **Supervisor-Worker** | Semantic worker selection | Optimal task-worker matching |
| **Ensemble** | Agent discovery (top-k) | Selects best perspectives |
| **Blackboard** | Dynamic specialist selection | Adapts to evolving needs |

### How A2A Works

1. **Capability Cards**: Each agent has A2A card with primary capabilities
2. **Semantic Matching**: Task requirements matched against capabilities
3. **Scoring**: Similarity scores calculated (0.0-1.0)
4. **Selection**: Best agent(s) selected based on scores
5. **Fallback**: Graceful degradation when A2A unavailable

### Disabling A2A

For patterns with A2A, use non-semantic modes:

```python
# Router without A2A
pipeline = Pipeline.router(agents=[...], routing_strategy="round-robin")

# Supervisor-Worker without A2A
pipeline = Pipeline.supervisor_worker(supervisor, workers, selection_mode="round-robin")

# Ensemble without A2A
pipeline = Pipeline.ensemble(agents=[...], synthesizer, discovery_mode="all")

# Blackboard without A2A
pipeline = Pipeline.blackboard(specialists=[...], controller, selection_mode="sequential")
```

---

## Best Practices

### 1. Error Handling

**Production**: Use graceful error handling (default)
```python
pipeline = Pipeline.router(agents=[...], error_handling="graceful")
# Returns partial results, doesn't crash on agent failure
```

**Development**: Use fail-fast for debugging
```python
pipeline.error_handling = "fail-fast"
# Raises exception immediately on agent failure
```

### 2. Performance Optimization

**Set Appropriate Limits**:
```python
# Parallel pattern
Pipeline.parallel(agents=[...], max_workers=5, timeout=30)

# Blackboard pattern
Pipeline.blackboard(specialists=[...], controller, max_iterations=5)
```

**Cache A2A Cards**:
- A2A cards are generated once per agent
- Reuse agents across pipeline invocations
- Avoid recreating agents unnecessarily

### 3. Agent Selection

**Distinct Capabilities**: Ensure agents have distinct specialties for best A2A matching
```python
# Good: Distinct capabilities
agents = [code_expert, data_expert, writing_expert]

# Bad: Overlapping capabilities
agents = [generic_agent1, generic_agent2, generic_agent3]
```

### 4. Testing

**Unit Test**: Test pipelines in isolation
```python
def test_pipeline():
    pipeline = Pipeline.sequential([agent1, agent2])
    result = pipeline.run(input="test")
    assert result['status'] == 'success'
```

**Integration Test**: Test with real agents (Tier 2)
```python
@pytest.mark.integration
def test_pipeline_integration():
    pipeline = Pipeline.router(agents=[real_agent1, real_agent2])
    result = pipeline.run(task="test task")
    assert 'output' in result
```

---

## Examples

### Example 1: ETL Pipeline (Sequential)

```python
from kaizen.orchestration.pipeline import Pipeline
from kaizen.agents import SimpleQAAgent  # Replace with actual extractor/transformer/loader

# Create ETL agents
extractor = SimpleQAAgent(config)  # Replace with DocumentExtractionAgent
transformer = SimpleQAAgent(config)  # Replace with DataTransformAgent
loader = SimpleQAAgent(config)      # Replace with DataLoaderAgent

# Build pipeline
etl_pipeline = Pipeline.sequential(agents=[extractor, transformer, loader])

# Execute
result = etl_pipeline.run(input="data.csv")
print(f"Status: {result['final_output']['status']}")
```

### Example 2: API Gateway (Router)

```python
# Create specialized agents
code_agent = CodeGenerationAgent(config)
data_agent = DataAnalysisAgent(config)
writing_agent = WritingAgent(config)

# Build router
router = Pipeline.router(
    agents=[code_agent, data_agent, writing_agent],
    routing_strategy="semantic"
)

# Route requests
request1 = router.run(task="Write Python function", input="...")
# → Routes to code_agent

request2 = router.run(task="Analyze sales data", input="...")
# → Routes to data_agent
```

### Example 3: Multi-Perspective Analysis (Ensemble)

```python
# Create expert agents
code_expert = CodeExpertAgent(config)
security_expert = SecurityExpertAgent(config)
performance_expert = PerformanceExpertAgent(config)
synthesis_agent = SynthesisAgent(config)

# Build ensemble
ensemble = Pipeline.ensemble(
    agents=[code_expert, security_expert, performance_expert],
    synthesizer=synthesis_agent,
    discovery_mode="a2a",
    top_k=3
)

# Get multi-perspective analysis
result = ensemble.run(
    task="Review this codebase",
    input="repository_path"
)
print(result['synthesized_perspective'])
```

---

## Related Documentation

- **[Multi-Agent Coordination Guide](multi-agent-coordination.md)** - Coordination patterns
- **[BaseAgent Architecture](baseagent-architecture.md)** - Agent fundamentals
- **[Pipeline Examples](../../../../examples/orchestration/pipeline-patterns/)** - Working code
- **[ADR-018](../../../docs/architecture/adr/ADR-018-pipeline-pattern-architecture-phase3.md)** - Architecture decisions

---

**Last Updated:** 2025-10-27
**Version:** Kaizen v0.5.0
**Status:** Production-ready ✅
