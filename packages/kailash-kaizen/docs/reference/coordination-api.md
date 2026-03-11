# Coordination API Reference

**Version**: 1.0.0
**Module**: `kaizen.orchestration`
**Purpose**: Meta-controller routing and multi-agent coordination

## Overview

The Coordination API provides intelligent agent routing and multi-agent orchestration through the Pipeline meta-controller pattern. The system routes tasks to the best agent based on capability matching (A2A protocol) with graceful fallback strategies.

### Key Features

- **Semantic Routing**: A2A capability-based agent selection
- **Fallback Strategies**: Round-robin, random routing when A2A unavailable
- **Graceful Error Handling**: Continue execution on agent failures
- **Composable Pipelines**: Convert routing logic to agents via `.to_agent()`
- **Zero Configuration**: Automatic capability discovery from agent descriptions
- **Production Ready**: 100% test coverage with real multi-agent workflows

### Architecture

```
┌───────────────────────────────────────────────────────────┐
│                  Meta-Controller Router                    │
│                                                            │
│      User Request  → Router → Agent Selection → Result    │
│                                                            │
│  ┌────────────────────────────────────────────────────┐  │
│  │         Routing Strategy Selection                  │  │
│  │                                                      │  │
│  │  ┌──────────────┐  ┌────────────┐  ┌────────────┐ │  │
│  │  │   Semantic   │  │Round-Robin │  │  Random    │ │  │
│  │  │  (A2A Match) │  │  (Rotate)  │  │(Randomize) │ │  │
│  │  └──────┬───────┘  └──────┬─────┘  └──────┬─────┘ │  │
│  │         │                  │                │       │  │
│  └─────────┼──────────────────┼────────────────┼───────┘  │
│            │                  │                │           │
│     ┌──────▼──────────────────▼────────────────▼──────┐   │
│     │          Agent Pool (N agents)                   │   │
│     │                                                   │   │
│     │  ┌──────────┐  ┌──────────┐  ┌──────────┐      │   │
│     │  │  Code    │  │   Data   │  │  Writing │      │   │
│     │  │ Specialist│  │ Specialist│  │Specialist│      │   │
│     │  │           │  │           │  │           │      │   │
│     │  │ A2A Card  │  │ A2A Card  │  │ A2A Card  │      │   │
│     │  └────┬──────┘  └────┬──────┘  └────┬──────┘      │   │
│     └───────┼──────────────┼──────────────┼─────────┘   │
│             │              │              │              │
│       ┌─────▼──────────────▼──────────────▼─────┐       │
│       │      Capability Matching (A2A)          │       │
│       │  Scores: [0.9, 0.3, 0.1] → Select Best │       │
│       └──────────────────┬───────────────────────┘       │
│                          │                               │
│                  ┌───────▼────────┐                      │
│                  │  Execute Agent │                      │
│                  │  Return Result │                      │
│                  └────────────────┘                      │
└───────────────────────────────────────────────────────────┘
```

## Pipeline.router()

**Purpose**: Create meta-controller pipeline with intelligent routing

**Location**: `kaizen.orchestration.pipeline`

**Factory Method**:
```python
from kaizen.orchestration.pipeline import Pipeline

@staticmethod
def router(
    agents: List[BaseAgent],
    routing_strategy: str = "semantic",
    error_handling: str = "graceful",
) -> Pipeline:
    """
    Create meta-controller (router) pipeline.

    Args:
        agents: List of agents to route between (must not be empty)
        routing_strategy: "semantic" (A2A), "round-robin", or "random"
        error_handling: "graceful" (default) or "fail-fast"

    Returns:
        Pipeline: Meta-controller pipeline instance

    Raises:
        ValueError: If agents list is empty

    Example:
        # Semantic routing with A2A
        pipeline = Pipeline.router(
            agents=[code_agent, data_agent, writing_agent],
            routing_strategy="semantic"
        )

        result = pipeline.run(
            task="Analyze sales data",
            input="sales.csv"
        )
    """
```

**Args**:
- **agents** (`List[BaseAgent]`): Agents to route between (minimum: 1 agent)
- **routing_strategy** (`str`): Routing algorithm
  - `"semantic"`: A2A capability matching (recommended)
  - `"round-robin"`: Rotate through agents sequentially
  - `"random"`: Random agent selection
- **error_handling** (`str`): Error mode
  - `"graceful"`: Return error info, continue execution (default)
  - `"fail-fast"`: Raise exception on first error

**Returns**:
- `Pipeline`: MetaControllerPipeline instance ready for execution

**Raises**:
- `ValueError`: If `agents` list is empty

---

## Routing Strategies

### Semantic Routing (A2A)

**Purpose**: Select best agent based on A2A capability matching

**How It Works**:
1. Extract task description from inputs
2. Generate A2A capability cards for all agents
3. Calculate capability match scores using `capability.matches_requirement(task)`
4. Select agent with highest score (> 0)
5. Fallback to first agent if all scores = 0 or A2A unavailable

**Requirements**:
- Agents must have `to_a2a_card()` method (BaseAgent provides this automatically)
- Task description must be provided in `run(task="...")`
- A2A nodes must be available (`kailash.nodes.ai.a2a`)

**Example**:
```python
from kaizen.orchestration.pipeline import Pipeline

# Create specialist agents
coding_agent = BaseAgent(
    config=config,
    signature=CodingSignature(),
    agent_id="code_specialist",
    description="Expert in Python programming and algorithms"
)

data_agent = BaseAgent(
    config=config,
    signature=DataSignature(),
    agent_id="data_specialist",
    description="Expert in data analysis and visualization"
)

# Create semantic router
router = Pipeline.router(
    agents=[coding_agent, data_agent],
    routing_strategy="semantic"
)

# Route based on task semantics
result1 = router.run(
    task="Write a Python function to sort a list",
    input="implement_sorting"
)
# → Routes to coding_agent (capability match score: 0.9)

result2 = router.run(
    task="Analyze sales trends and create chart",
    input="sales.csv"
)
# → Routes to data_agent (capability match score: 0.85)
```

**Capability Matching Algorithm**:
```python
# Simplified capability matching logic
best_score = 0.0
best_agent = None

for agent in agents:
    card = agent.to_a2a_card()

    for capability in card.primary_capabilities:
        score = capability.matches_requirement(task)

        if score > best_score:
            best_score = score
            best_agent = agent

# Select best match or fallback
if best_agent and best_score > 0:
    return best_agent
else:
    return agents[0]  # Fallback
```

---

### Round-Robin Routing

**Purpose**: Distribute load evenly across all agents

**How It Works**:
1. Maintain current index (starts at 0)
2. Select agent at current index
3. Increment index (wrap around to 0 after last agent)
4. Repeat for each request

**Use Cases**:
- Load balancing when all agents have equal capability
- Testing multiple agents with same workload
- Fallback when A2A unavailable

**Example**:
```python
from kaizen.orchestration.pipeline import Pipeline

# Create router with round-robin
router = Pipeline.router(
    agents=[agent1, agent2, agent3],
    routing_strategy="round-robin"
)

# Requests distributed evenly
result1 = router.run(task="Task 1", input="data1")  # → agent1
result2 = router.run(task="Task 2", input="data2")  # → agent2
result3 = router.run(task="Task 3", input="data3")  # → agent3
result4 = router.run(task="Task 4", input="data4")  # → agent1 (wrapped)
```

---

### Random Routing

**Purpose**: Random agent selection for unpredictable distribution

**How It Works**:
1. Randomly select agent from pool
2. Execute selected agent
3. Return result

**Use Cases**:
- A/B testing with multiple agent configurations
- Simulating non-deterministic systems
- Quick prototyping without capability matching

**Example**:
```python
from kaizen.orchestration.pipeline import Pipeline

# Create router with random selection
router = Pipeline.router(
    agents=[agent_a, agent_b, agent_c],
    routing_strategy="random"
)

# Each request randomly routed
result1 = router.run(task="Any task", input="data1")  # → random agent
result2 = router.run(task="Any task", input="data2")  # → random agent
```

---

## Error Handling Modes

### Graceful Mode (Default)

**Purpose**: Continue execution even when agents fail

**Behavior**:
- Agent execution failures are caught
- Error information returned in result dict
- Pipeline continues processing subsequent requests

**Return Format** (on error):
```python
{
    "error": "Exception message",
    "agent_id": "failed_agent_id",
    "status": "failed",
    "traceback": "Full traceback string"
}
```

**Example**:
```python
router = Pipeline.router(
    agents=[flaky_agent, stable_agent],
    routing_strategy="round-robin",
    error_handling="graceful"  # Default
)

# First request fails
result1 = router.run(task="Task 1", input="bad_data")
print(result1)
# Output: {"error": "Invalid input", "status": "failed", ...}

# Second request succeeds
result2 = router.run(task="Task 2", input="good_data")
print(result2)
# Output: {"result": "Success", "status": "completed"}
```

---

### Fail-Fast Mode

**Purpose**: Stop immediately on first error

**Behavior**:
- Agent execution failures raise exceptions
- Pipeline execution halts
- Useful for critical workflows where partial failure is unacceptable

**Example**:
```python
router = Pipeline.router(
    agents=[agent1, agent2],
    routing_strategy="semantic",
    error_handling="fail-fast"
)

try:
    result = router.run(task="Critical task", input="data")
except Exception as e:
    print(f"Pipeline failed: {e}")
    # Handle failure (rollback, retry, alert, etc.)
```

---

## Pipeline Execution

### run() Method

**Purpose**: Execute routing pipeline

**Signature**:
```python
def run(self, **inputs) -> Dict[str, Any]:
    """
    Execute router pipeline: select and execute best agent.

    Args:
        **inputs: Inputs for agent execution
            task (str, optional): Task description for A2A matching
            ... other inputs passed to selected agent

    Returns:
        Dict[str, Any]: Selected agent's execution result

    Error Handling:
        - graceful (default): Returns error info, continues
        - fail-fast: Raises exception on first error
    """
```

**Args**:
- **task** (`str`, optional): Task description for semantic routing (required for A2A matching)
- **...inputs**: Additional kwargs passed to selected agent

**Returns**:
- `Dict[str, Any]`: Agent execution result

**Example**:
```python
# Semantic routing requires 'task' parameter
result = router.run(
    task="Generate unit tests for Python function",
    function_code="def add(a, b): return a + b",
    test_framework="pytest"
)

# Round-robin/random can omit 'task'
result = router.run(
    input="Process this data",
    options={"verbose": True}
)
```

---

## Conversion to Agent

### to_agent() Method

**Purpose**: Convert pipeline to BaseAgent for composition

**Signature**:
```python
def to_agent(
    self,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> BaseAgent:
    """
    Convert pipeline to an Agent for composition.

    Creates a PipelineAgent that wraps this pipeline, allowing it to be
    used anywhere a BaseAgent is expected (multi-agent patterns, workflows, etc.)

    Args:
        name: Optional name for the pipeline agent
        description: Optional description for the pipeline agent

    Returns:
        BaseAgent: Agent wrapper around this pipeline

    Example:
        pipeline = Pipeline.router(agents=[...])
        pipeline_agent = pipeline.to_agent(
            name="routing_pipeline",
            description="Routes tasks to specialists"
        )

        # Use in multi-agent pattern
        supervisor = SupervisorAgent(workers=[pipeline_agent, other_agent])
    """
```

**Example**:
```python
from kaizen.orchestration.pipeline import Pipeline

# Create routing pipeline
router_pipeline = Pipeline.router(
    agents=[code_agent, data_agent, writing_agent],
    routing_strategy="semantic"
)

# Convert to agent
router_agent = router_pipeline.to_agent(
    name="specialist_router",
    description="Routes to appropriate specialist"
)

# Use in supervisor-worker pattern
from kaizen.agents.coordination.supervisor_worker import SupervisorWorkerPattern

pattern = SupervisorWorkerPattern(
    supervisor=supervisor_agent,
    workers=[router_agent, other_agent],  # Router as a worker!
    coordinator=coordinator_agent,
    shared_pool=SharedMemoryPool()
)

result = pattern.run(task="Complex multi-agent workflow")
```

---

## Integration Examples

### Basic Semantic Routing

**Pattern**: Route to best specialist based on task

```python
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.orchestration.pipeline import Pipeline
from kaizen.signatures import Signature, InputField, OutputField

# Define signatures
class CodingSignature(Signature):
    task: str = InputField(description="Coding task")
    code: str = OutputField(description="Generated code")

class DataSignature(Signature):
    task: str = InputField(description="Data analysis task")
    analysis: str = OutputField(description="Analysis results")

# Create specialist agents
config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

code_specialist = BaseAgent(
    config=config,
    signature=CodingSignature(),
    agent_id="code_specialist",
    description="Expert in Python programming, algorithms, and code generation"
)

data_specialist = BaseAgent(
    config=config,
    signature=DataSignature(),
    agent_id="data_specialist",
    description="Expert in data analysis, visualization, and statistical insights"
)

# Create meta-controller
router = Pipeline.router(
    agents=[code_specialist, data_specialist],
    routing_strategy="semantic"
)

# Route coding task
coding_result = router.run(
    task="Write a function to calculate Fibonacci numbers",
    input="generate_fibonacci"
)
print(f"Routed to: {coding_result.get('agent_id', 'unknown')}")
# Output: code_specialist

# Route data task
data_result = router.run(
    task="Analyze sales trends and identify patterns",
    input="sales_data.csv"
)
print(f"Routed to: {data_result.get('agent_id', 'unknown')}")
# Output: data_specialist
```

---

### Multi-Specialist System

**Pattern**: Route among many specialists

```python
from kaizen.orchestration.pipeline import Pipeline

# Create 5 specialist agents
specialists = [
    BaseAgent(config, CodingSignature(), "coder", "Python programming expert"),
    BaseAgent(config, DataSignature(), "data_analyst", "Data analysis expert"),
    BaseAgent(config, WritingSignature(), "writer", "Technical writing expert"),
    BaseAgent(config, DevOpsSignature(), "devops", "DevOps and infrastructure expert"),
    BaseAgent(config, SecuritySignature(), "security", "Security and compliance expert"),
]

# Create router
router = Pipeline.router(
    agents=specialists,
    routing_strategy="semantic"
)

# Test routing accuracy
tasks = [
    ("Implement OAuth authentication", "coder"),
    ("Analyze user engagement metrics", "data_analyst"),
    ("Write API documentation", "writer"),
    ("Configure Kubernetes cluster", "devops"),
    ("Audit code for SQL injection", "security"),
]

for task, expected_agent in tasks:
    result = router.run(task=task, input="test")
    actual_agent = result.get("agent_id", "unknown")
    print(f"Task: {task[:30]}... → {actual_agent} ({'✓' if actual_agent == expected_agent else '✗'})")
```

**Output**:
```
Task: Implement OAuth authentica... → coder ✓
Task: Analyze user engagement me... → data_analyst ✓
Task: Write API documentation... → writer ✓
Task: Configure Kubernetes clust... → devops ✓
Task: Audit code for SQL injecti... → security ✓
```

---

### Graceful Error Handling

**Pattern**: Continue execution despite agent failures

```python
from kaizen.orchestration.pipeline import Pipeline

# Create agents (some may fail)
agents = [
    reliable_agent,
    flaky_agent_1,
    flaky_agent_2,
]

# Graceful error handling
router = Pipeline.router(
    agents=agents,
    routing_strategy="round-robin",
    error_handling="graceful"  # Default
)

# Process batch of requests
requests = [
    {"task": "Task 1", "input": "good_data"},
    {"task": "Task 2", "input": "bad_data"},   # Will fail
    {"task": "Task 3", "input": "good_data"},
]

results = []
for req in requests:
    result = router.run(**req)

    if result.get("status") == "failed":
        print(f"❌ {req['task']} failed: {result['error']}")
        results.append(None)
    else:
        print(f"✓ {req['task']} succeeded")
        results.append(result)

# Continue processing successful results
successful_results = [r for r in results if r is not None]
print(f"\nProcessed {len(successful_results)}/{len(requests)} successfully")
```

**Output**:
```
✓ Task 1 succeeded
❌ Task 2 failed: Invalid input format
✓ Task 3 succeeded

Processed 2/3 successfully
```

---

### Nested Pipelines

**Pattern**: Compose routers within larger workflows

```python
from kaizen.orchestration.pipeline import Pipeline

# Create specialist routers
code_router = Pipeline.router(
    agents=[python_expert, java_expert, rust_expert],
    routing_strategy="semantic"
).to_agent(name="code_router")

data_router = Pipeline.router(
    agents=[sql_expert, viz_expert, ml_expert],
    routing_strategy="semantic"
).to_agent(name="data_router")

# Create top-level router
top_router = Pipeline.router(
    agents=[code_router, data_router],
    routing_strategy="semantic"
)

# Route hierarchically
result = top_router.run(
    task="Build ML model and generate Python deployment code",
    input="model_requirements.txt"
)
# → top_router routes to data_router
# → data_router routes to ml_expert
# → Result bubbles back up
```

---

## Testing

### Unit Tests

**Test routing logic**:

```python
import pytest
from kaizen.orchestration.pipeline import Pipeline
from kaizen.core.base_agent import BaseAgent

@pytest.mark.unit
def test_semantic_routing_selects_best_agent():
    """Test A2A semantic routing selects correct agent."""
    # Create mock agents
    code_agent = BaseAgent(
        config=config,
        signature=CodingSignature(),
        agent_id="coder",
        description="Python programming expert"
    )

    data_agent = BaseAgent(
        config=config,
        signature=DataSignature(),
        agent_id="data",
        description="Data analysis expert"
    )

    # Create router
    router = Pipeline.router(
        agents=[code_agent, data_agent],
        routing_strategy="semantic"
    )

    # Test coding task routing
    result = router.run(task="Write Python function", input="test")
    assert result.get("agent_id") == "coder"

    # Test data task routing
    result = router.run(task="Analyze sales data", input="test")
    assert result.get("agent_id") == "data"

@pytest.mark.unit
def test_round_robin_distributes_evenly():
    """Test round-robin rotates through agents."""
    agents = [agent1, agent2, agent3]

    router = Pipeline.router(
        agents=agents,
        routing_strategy="round-robin"
    )

    # Execute 6 requests
    for i in range(6):
        result = router.run(task=f"Task {i}", input="data")
        expected_agent = agents[i % 3].agent_id
        assert result.get("agent_id") == expected_agent
```

---

### Integration Tests

**Test real agent coordination**:

```python
import pytest
from kaizen.orchestration.pipeline import Pipeline

@pytest.mark.integration
@pytest.mark.asyncio
async def test_router_with_real_agents():
    """Test router with real LLM agents."""
    from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

    # Create real agents (Ollama - free)
    config = BaseAgentConfig(
        llm_provider="ollama",
        model="llama3.2:1b"
    )

    code_agent = BaseAgent(
        config=config,
        signature=CodingSignature(),
        description="Python expert"
    )

    data_agent = BaseAgent(
        config=config,
        signature=DataSignature(),
        description="Data expert"
    )

    # Create router
    router = Pipeline.router(
        agents=[code_agent, data_agent],
        routing_strategy="semantic"
    )

    # Test real routing
    result = router.run(
        task="Write a function to sort a list",
        input="sorting_task"
    )

    # Verify result structure
    assert isinstance(result, dict)
    assert "error" not in result or result.get("status") != "failed"
```

---

### E2E Tests

**Test full multi-agent workflow**:

```python
import pytest
from kaizen.orchestration.pipeline import Pipeline

@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
async def test_meta_controller_routes_correctly_e2e():
    """
    Test meta-controller routes tasks to correct specialists.

    Validates:
    - Coding tasks route to coding specialist
    - Data tasks route to data specialist
    - Writing tasks route to writing specialist
    """
    # Create real OpenAI agents
    config = BaseAgentConfig(
        llm_provider="openai",
        model="gpt-4o-2024-08-06"
    )

    coding_agent = BaseAgent(
        config=config,
        signature=CodingSignature(),
        agent_id="coding_specialist",
        description="Expert in Python programming and algorithms"
    )

    data_agent = BaseAgent(
        config=config,
        signature=DataSignature(),
        agent_id="data_specialist",
        description="Expert in data analysis and visualization"
    )

    # Create meta-controller
    router = Pipeline.router(
        agents=[coding_agent, data_agent],
        routing_strategy="semantic"
    )

    # Test coding task
    coding_result = router.run(
        task="Write a Python function to calculate fibonacci",
        input="fib"
    )

    assert "error" not in coding_result
    assert coding_result.get("agent_id") == "coding_specialist"

    # Test data task
    data_result = router.run(
        task="Analyze sales trends and identify patterns",
        input="sales.csv"
    )

    assert "error" not in data_result
    assert data_result.get("agent_id") == "data_specialist"
```

---

## Production Patterns

### Retry on Failure

**Pattern**: Retry failed agents with exponential backoff

```python
import asyncio
from kaizen.orchestration.pipeline import Pipeline

async def execute_with_retry(router, task, input_data, max_retries=3):
    """Execute with exponential backoff retry."""
    for attempt in range(max_retries):
        result = router.run(task=task, input=input_data)

        if result.get("status") != "failed":
            return result

        # Exponential backoff
        wait_time = 2 ** attempt
        print(f"Attempt {attempt + 1} failed, retrying in {wait_time}s...")
        await asyncio.sleep(wait_time)

    raise Exception(f"Failed after {max_retries} attempts")

# Usage
result = await execute_with_retry(
    router=my_router,
    task="Critical task",
    input_data="important_data",
    max_retries=3
)
```

---

### Fallback Routing

**Pattern**: Fallback to different strategy on A2A failure

```python
from kaizen.orchestration.pipeline import Pipeline

def create_robust_router(agents):
    """Create router with fallback to round-robin."""
    try:
        # Try semantic routing
        return Pipeline.router(
            agents=agents,
            routing_strategy="semantic"
        )
    except Exception as e:
        print(f"Semantic routing unavailable: {e}")
        print("Falling back to round-robin")

        # Fallback to round-robin
        return Pipeline.router(
            agents=agents,
            routing_strategy="round-robin"
        )

# Usage
router = create_robust_router(my_agents)
```

---

### Monitoring and Metrics

**Pattern**: Track routing decisions for observability

```python
from collections import defaultdict
from kaizen.orchestration.pipeline import Pipeline

class MonitoredRouter:
    """Router with built-in metrics tracking."""

    def __init__(self, agents, routing_strategy="semantic"):
        self.router = Pipeline.router(
            agents=agents,
            routing_strategy=routing_strategy
        )
        self.metrics = defaultdict(int)

    def run(self, **inputs):
        """Execute with metrics tracking."""
        result = self.router.run(**inputs)

        # Track agent selection
        agent_id = result.get("agent_id", "unknown")
        self.metrics[f"routed_to_{agent_id}"] += 1

        # Track errors
        if result.get("status") == "failed":
            self.metrics["total_errors"] += 1

        self.metrics["total_requests"] += 1

        return result

    def get_metrics(self):
        """Get routing metrics."""
        return dict(self.metrics)

# Usage
router = MonitoredRouter(agents=[code_agent, data_agent])

for i in range(100):
    router.run(task=f"Task {i}", input="data")

print(router.get_metrics())
# Output: {
#   "routed_to_code_specialist": 45,
#   "routed_to_data_specialist": 55,
#   "total_errors": 0,
#   "total_requests": 100
# }
```

---

## Related Documentation

- **[Planning Agents API](./planning-agents-api.md)**: PlanningAgent and PEVAgent for complex task orchestration
- **[Tools API Reference](./tools-api.md)**: Tool calling and approval workflows
- **[BaseAgent Architecture](../guides/baseagent-architecture.md)**: Core agent system

---

## Version History

**v1.0.0** (2025-10-27):
- Initial release with Pipeline.router() factory method
- Semantic routing via A2A capability matching
- Round-robin and random fallback strategies
- Graceful and fail-fast error handling modes
- Pipeline composition via .to_agent()
- 100% test coverage with E2E validation

---

**Complete Coordination API documentation** | Production-ready meta-controller routing with A2A capability matching
