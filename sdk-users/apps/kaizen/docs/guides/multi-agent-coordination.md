# Multi-Agent Coordination Guide

## Overview

Kaizen provides production-ready multi-agent coordination using Google's Agent-to-Agent (A2A) protocol for semantic capability matching, eliminating hardcoded agent selection logic.

**Key Features:**
- **Semantic Matching**: Agents selected by capability, not hardcoded rules
- **A2A Protocol**: 100% compliant with Google A2A specification
- **Automatic Discovery**: BaseAgent auto-generates capability cards
- **5 Coordination Patterns**: Supervisor-Worker, Consensus, Debate, Sequential, Handoff
- **Shared Memory**: Multi-agent context sharing via SharedMemoryPool

**Version:** Kaizen v0.2.0+

---

## Google A2A Protocol

### What is A2A?

Agent-to-Agent (A2A) is Google's protocol for multi-agent systems, enabling:
1. **Capability Discovery**: Agents advertise what they can do
2. **Semantic Matching**: Tasks matched to agents by capability analysis
3. **Dynamic Routing**: No hardcoded if/else agent selection
4. **Composability**: Agents work together without tight coupling

### A2A Capability Cards

Every BaseAgent automatically generates an A2A card:

```python
from kaizen.agents import SimpleQAAgent

agent = SimpleQAAgent(config)
card = agent.to_a2a_card()

# Returns:
# {
#   "name": "SimpleQAAgent",
#   "description": "Question answering agent...",
#   "capabilities": ["can_answer_questions", "can_provide_explanations"],
#   "input_schema": {
#     "type": "object",
#     "properties": {"question": {"type": "string"}}
#   },
#   "output_schema": {
#     "type": "object",
#     "properties": {"answer": {"type": "string"}}
#   },
#   "specialties": ["general_knowledge", "reasoning"]
# }
```

**Key Benefit**: Coordinators use these cards for semantic matching, eliminating ~40-50% of manual selection logic.

---

## Coordination Patterns

### 1. Supervisor-Worker Pattern

**When to Use:**
- Task decomposition needed
- Multiple specialized workers
- Central coordination required
- Dynamic task assignment

**Example:**
```python
from kaizen.agents.coordination.supervisor_worker import SupervisorWorkerPattern
from kaizen.agents import SimpleQAAgent, CodeGenerationAgent, RAGResearchAgent
from kaizen.memory import SharedMemoryPool

# Create shared memory
shared_pool = SharedMemoryPool()

# Create workers
qa_agent = SimpleQAAgent(config, shared_memory=shared_pool, agent_id="qa")
code_agent = CodeGenerationAgent(config, shared_memory=shared_pool, agent_id="code")
research_agent = RAGResearchAgent(config, shared_memory=shared_pool, agent_id="research")

# Create pattern
pattern = SupervisorWorkerPattern(
    supervisor=supervisor_agent,
    workers=[qa_agent, code_agent, research_agent],
    coordinator=coordinator,
    shared_pool=shared_pool
)

# Semantic task routing (NO hardcoded if/else!)
result = pattern.execute_task("Analyze this codebase and suggest improvements")
# Automatically routes to code_agent based on A2A capabilities
```

**How It Works:**
1. Supervisor receives task
2. Analyzes task requirements
3. Uses A2A cards to match task with best worker
4. Assigns task and monitors execution
5. Aggregates results

---

### 2. Consensus Pattern

**When to Use:**
- Multiple perspectives needed
- Decision requires agreement
- Risk mitigation important
- Democratic decision-making

**Example:**
```python
from kaizen.agents.coordination.consensus_pattern import ConsensusPattern

# Create pattern with 3+ voters
pattern = ConsensusPattern(
    proposer=proposer_agent,
    voters=[voter1, voter2, voter3],
    aggregator=aggregator_agent,
    shared_pool=shared_pool,
    threshold=0.7  # 70% agreement required
)

# Reach consensus on decision
result = pattern.reach_consensus("Should we deploy the new feature?")
# Returns: {"decision": "approve", "agreement": 0.85, "dissenting_views": [...]}
```

**Flow:**
1. Proposer presents option
2. Each voter analyzes independently
3. Voters cast votes with reasoning
4. Aggregator determines consensus
5. Returns decision + confidence

---

### 3. Debate Pattern

**When to Use:**
- Exploring tradeoffs
- Critical decisions
- Adversarial analysis needed
- Risk assessment

**Example:**
```python
from kaizen.agents.coordination.debate_pattern import DebatePattern

pattern = DebatePattern(
    proponent=proponent_agent,
    opponent=opponent_agent,
    judge=judge_agent,
    shared_pool=shared_pool,
    rounds=3  # Number of debate rounds
)

# Debate decision
result = pattern.debate("Should we migrate to microservices?")
# Returns: {
#   "decision": "proceed_with_caution",
#   "proponent_arguments": [...],
#   "opponent_arguments": [...],
#   "judge_reasoning": "...",
#   "confidence": 0.75
# }
```

**Flow:**
1. Proponent argues FOR
2. Opponent argues AGAINST
3. Multiple rounds of rebuttals
4. Judge evaluates arguments
5. Final decision with reasoning

---

### 4. Sequential Pattern

**When to Use:**
- Pipeline processing
- Each step depends on previous
- Linear workflow
- Data transformation chains

**Example:**
```python
from kaizen.agents.coordination.sequential_pattern import SequentialPattern

pattern = SequentialPattern(
    agents=[
        data_extraction_agent,
        data_validation_agent,
        data_enrichment_agent,
        data_storage_agent
    ],
    shared_pool=shared_pool
)

# Process through pipeline
result = pattern.execute("raw_data.csv")
# Each agent processes in sequence, building on previous results
```

---

### 5. Handoff Pattern

**When to Use:**
- Expertise transitions needed
- Escalation scenarios
- Progressive refinement
- Specialist routing

**Example:**
```python
from kaizen.agents.coordination.handoff_pattern import HandoffPattern

pattern = HandoffPattern(
    initial_agent=triage_agent,
    specialists={
        "technical": technical_specialist,
        "business": business_specialist,
        "legal": legal_specialist
    },
    shared_pool=shared_pool
)

# Smart handoff based on task analysis
result = pattern.process("Customer complaint about data privacy")
# triage_agent analyzes → hands off to legal_specialist
```

---

## Shared Memory Integration

### SharedMemoryPool

Enables context sharing across agents:

```python
from kaizen.memory import SharedMemoryPool

# Create shared pool
shared_pool = SharedMemoryPool()

# Agent 1 writes insight
agent1 = MyAgent(config, shared_memory=shared_pool, agent_id="agent1")
agent1.write_to_memory(
    content={"finding": "User prefers concise responses"},
    tags=["user_preference"],
    importance=0.9
)

# Agent 2 reads insight
agent2 = MyAgent(config, shared_memory=shared_pool, agent_id="agent2")
insights = agent2.read_from_memory(
    tags=["user_preference"],
    min_importance=0.8
)
# Can now adapt behavior based on agent1's finding
```

### Memory Scoping

**By Agent:**
```python
# Read only agent1's memories
memories = pool.get_memories(agent_id="agent1")
```

**By Tags:**
```python
# Read all research findings
findings = pool.get_memories(tags=["research"])
```

**By Importance:**
```python
# Read high-importance insights only
critical = pool.get_memories(min_importance=0.9)
```

---

## Semantic Agent Selection

### Automatic Matching (A2A)

```python
# NO hardcoded selection!
best_worker = pattern.supervisor.select_worker_for_task(
    task="Analyze sales data and create visualization",
    available_workers=[code_expert, data_expert, writing_expert],
    return_score=True
)

# Returns:
# {
#   "worker": <DataAnalystAgent>,
#   "score": 0.92,
#   "reasoning": "Task requires data analysis and visualization..."
# }
```

**How Matching Works:**
1. Task analyzed for requirements
2. Each worker's A2A card compared
3. Capability overlap calculated
4. Best match selected with confidence score
5. Automatic retry if agent fails

---

## Best Practices

### 1. Use Semantic Matching

```python
# ✅ GOOD - Semantic matching via A2A
pattern = SupervisorWorkerPattern(supervisor, workers, coordinator, pool)
result = pattern.execute_task(task)  # Automatic routing

# ❌ BAD - Hardcoded selection
if "code" in task:
    worker = code_agent
elif "data" in task:
    worker = data_agent
```

---

### 2. Provide Shared Memory

```python
# ✅ GOOD - Context sharing enabled
shared_pool = SharedMemoryPool()
agent1 = MyAgent(config, shared_memory=shared_pool)
agent2 = MyAgent(config, shared_memory=shared_pool)

# ❌ BAD - No context sharing
agent1 = MyAgent(config)  # Isolated
agent2 = MyAgent(config)  # Can't see agent1's work
```

---

### 3. Tag Insights Properly

```python
# ✅ GOOD - Descriptive tags
agent.write_to_memory(
    content={...},
    tags=["user_preference", "language_style"],
    importance=0.9
)

# ❌ BAD - Vague tags
agent.write_to_memory(
    content={...},
    tags=["stuff"],
    importance=0.5
)
```

---

### 4. Set Importance Correctly

```python
# ✅ GOOD - Meaningful importance levels
agent.write_to_memory(
    content={"critical_finding": "Security vulnerability"},
    importance=0.95  # Critical
)

agent.write_to_memory(
    content={"minor_note": "Typo in docs"},
    importance=0.3  # Low priority
)

# ❌ BAD - Everything is important
agent.write_to_memory(content={"anything": "..."}, importance=1.0)
```

---

## Advanced Patterns

### Pattern Composition

Combine multiple patterns:

```python
# Stage 1: Consensus on approach
consensus_result = consensus_pattern.reach_consensus("Which approach?")

# Stage 2: Debate details
debate_result = debate_pattern.debate(consensus_result["decision"])

# Stage 3: Supervisor-worker execution
final_result = supervisor_pattern.execute_task(debate_result["plan"])
```

### Dynamic Pattern Selection

```python
def select_pattern(task_type: str):
    if task_type == "decision":
        return consensus_pattern
    elif task_type == "analysis":
        return debate_pattern
    elif task_type == "execution":
        return supervisor_pattern
    else:
        return sequential_pattern

pattern = select_pattern(task["type"])
result = pattern.execute(task)
```

---

## Testing Multi-Agent Systems

### Unit Testing

```python
@pytest.mark.unit
def test_supervisor_worker_pattern():
    # Use mock agents
    supervisor = MockSupervisorAgent()
    workers = [MockWorkerAgent(id=i) for i in range(3)]

    pattern = SupervisorWorkerPattern(
        supervisor, workers, coordinator=None, shared_pool=None
    )

    result = pattern.execute_task("test task")
    assert result["status"] == "completed"
```

### Integration Testing

```python
@pytest.mark.integration
async def test_real_multi_agent():
    # Use real agents with mock LLM provider
    shared_pool = SharedMemoryPool()

    agent1 = SimpleQAAgent(TestConfig(llm_provider="mock"), shared_memory=shared_pool)
    agent2 = CodeGenerationAgent(TestConfig(llm_provider="mock"), shared_memory=shared_pool)

    pattern = SupervisorWorkerPattern(supervisor, [agent1, agent2], coordinator, shared_pool)

    result = pattern.execute_task("Generate Python code")
    assert "code" in result
```

---

## Performance Considerations

### Agent Pool Sizing

```python
# ✅ GOOD - Right-sized pool
workers = [
    specialized_agent_1,
    specialized_agent_2,
    specialized_agent_3
]  # 3-5 specialists is optimal

# ❌ BAD - Too many workers
workers = [agent for _ in range(20)]  # Coordination overhead
```

### Memory Management

```python
# ✅ GOOD - Prune old memories
shared_pool.prune_memories(max_age_minutes=60)

# ✅ GOOD - Limit memory size
shared_pool.set_max_memories(1000)
```

---

## Common Patterns by Use Case

| Use Case | Pattern | Why |
|----------|---------|-----|
| Task decomposition | Supervisor-Worker | Dynamic assignment |
| Critical decisions | Debate | Explore tradeoffs |
| Risk mitigation | Consensus | Multiple perspectives |
| Pipeline processing | Sequential | Linear dependencies |
| Expertise routing | Handoff | Specialist transitions |

---

## Troubleshooting

### Issue: Worker not selected

**Symptoms**: Task always routes to same worker

**Fix**: Check A2A capability cards:
```python
for worker in workers:
    print(worker.to_a2a_card())
# Ensure capabilities are distinct
```

---

### Issue: Memory not shared

**Symptoms**: Agents can't see each other's insights

**Fix**: Verify shared pool:
```python
# All agents must use SAME pool instance
shared_pool = SharedMemoryPool()
agent1 = MyAgent(config, shared_memory=shared_pool)  # ✅
agent2 = MyAgent(config, shared_memory=shared_pool)  # ✅
```

---

## Related Documentation

- **[BaseAgent Architecture](baseagent-architecture.md)** - Unified agent system
- **[Memory Patterns Guide](../reference/memory-patterns-guide.md)** - Memory usage patterns
- **[Strategy Selection](../reference/strategy-selection-guide.md)** - When to use which strategy
- **[API Reference](../reference/api-reference.md)** - Complete API documentation

---

**Last Updated:** 2025-10-22
**Version:** Kaizen v0.2.0
**Status:** Production-ready ✅
