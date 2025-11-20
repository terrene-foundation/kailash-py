# Meta-Controller Routing Guide

**Version**: 1.0.0
**Status**: Production Ready
**Last Updated**: 2025-11-03

---

## Executive Summary

The Meta-Controller (Router) pattern provides intelligent request routing to the best-fit agent using Google's A2A (Agent-to-Agent) protocol for semantic capability matching. This eliminates hardcoded agent selection logic and enables dynamic, capability-based routing.

**Key Benefits:**
- No hardcoded if/else routing logic
- Semantic matching via A2A capability cards
- Multiple routing strategies (semantic, round-robin, random)
- Graceful error handling with fallback support
- Composable with Pipeline pattern

---

## Table of Contents

1. [What is Meta-Controller Routing?](#what-is-meta-controller-routing)
2. [Routing Strategies](#routing-strategies)
3. [A2A Capability Matching](#a2a-capability-matching)
4. [Quick Start](#quick-start)
5. [Configuration](#configuration)
6. [Advanced Usage](#advanced-usage)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

---

## What is Meta-Controller Routing?

**Meta-Controller routing** routes requests to the most appropriate agent from a pool of available agents based on task requirements and agent capabilities.

### Traditional Approach (Hardcoded)

```python
def route_request(task: str):
    # ❌ HARDCODED LOGIC - Brittle and unmaintainable
    if "code" in task.lower() or "python" in task.lower():
        return code_agent.run(task=task)
    elif "data" in task.lower() or "analysis" in task.lower():
        return data_agent.run(task=task)
    elif "write" in task.lower() or "article" in task.lower():
        return writing_agent.run(task=task)
    else:
        return default_agent.run(task=task)

# Problems:
# 1. Keyword matching is unreliable
# 2. Adding agents requires code changes
# 3. No semantic understanding
# 4. Difficult to maintain
```

### Meta-Controller Approach (Capability-Based)

```python
from kaizen.orchestration.pipeline import Pipeline

# ✅ SEMANTIC ROUTING - No hardcoded logic
pipeline = Pipeline.router(
    agents=[code_agent, data_agent, writing_agent],
    routing_strategy="semantic"  # A2A capability matching
)

# Automatically routes to best agent
result = pipeline.run(task="Analyze sales data and create visualization")
# Routes to data_agent based on capabilities (score: 0.9)

result = pipeline.run(task="Generate Python function with tests")
# Routes to code_agent based on capabilities (score: 0.95)

result = pipeline.run(task="Write blog post about AI ethics")
# Routes to writing_agent based on capabilities (score: 0.88)

# Benefits:
# 1. Semantic understanding of task and capabilities
# 2. No code changes when adding agents
# 3. Automatic best-fit selection
# 4. Maintainable and scalable
```

---

## Routing Strategies

### 1. Semantic Routing (A2A Capability Matching)

**Pattern**: Match task requirements with agent capabilities using semantic analysis

**How It Works:**
```
User Request → Task Analysis → A2A Capability Matching → Best Agent
                                        ↓
                        Score each agent's capabilities
                                (0.0 - 1.0)
                                        ↓
                            Select highest scoring agent
```

**Example:**
```python
pipeline = Pipeline.router(
    agents=[code_expert, data_expert, writing_expert],
    routing_strategy="semantic"
)

# Task: "Analyze sales data and create visualization"
#
# A2A Matching Scores:
# - code_expert:    0.4  (capability: "Code generation")
# - data_expert:    0.9  (capability: "Data analysis and visualization")  ← SELECTED
# - writing_expert: 0.3  (capability: "Content writing")
#
# Result: Routes to data_expert

result = pipeline.run(task="Analyze sales data and create visualization")
```

**When to Use:**
- Task requirements vary significantly
- Multiple specialized agents available
- Semantic understanding needed
- Dynamic agent selection required

### 2. Round-Robin Routing

**Pattern**: Rotate through agents in sequence for load balancing

**How It Works:**
```
Request 1 → Agent 1
Request 2 → Agent 2
Request 3 → Agent 3
Request 4 → Agent 1  (wraps around)
Request 5 → Agent 2
...
```

**Example:**
```python
pipeline = Pipeline.router(
    agents=[agent1, agent2, agent3],
    routing_strategy="round-robin"
)

# Requests distributed evenly
result1 = pipeline.run(task="Task 1")  # → agent1
result2 = pipeline.run(task="Task 2")  # → agent2
result3 = pipeline.run(task="Task 3")  # → agent3
result4 = pipeline.run(task="Task 4")  # → agent1
```

**When to Use:**
- Agents have similar capabilities
- Load balancing needed
- Fair distribution required
- Task type doesn't matter

### 3. Random Routing

**Pattern**: Randomly select agent for each request

**How It Works:**
```
Request → Random Selection → Random Agent
```

**Example:**
```python
pipeline = Pipeline.router(
    agents=[agent1, agent2, agent3],
    routing_strategy="random"
)

# Random selection for each request
result1 = pipeline.run(task="Task 1")  # → random agent
result2 = pipeline.run(task="Task 2")  # → random agent
result3 = pipeline.run(task="Task 3")  # → random agent
```

**When to Use:**
- Load distribution across identical agents
- A/B testing different agents
- No preference for specific agent
- Simple load balancing

### Strategy Comparison

| Strategy | Selection Method | Use Case | Agent Similarity Required |
|----------|------------------|----------|--------------------------|
| **Semantic** | A2A capability matching | Specialized agents | No - diverse capabilities |
| **Round-Robin** | Sequential rotation | Load balancing | Yes - similar capabilities |
| **Random** | Random selection | Simple load distribution | Yes - identical capabilities |

---

## A2A Capability Matching

### What is A2A?

**Agent-to-Agent (A2A)** is Google's protocol for multi-agent systems enabling semantic capability discovery and matching.

### How A2A Cards Work

Every BaseAgent automatically generates an A2A capability card:

```python
from kaizen.agents import CodeGenerationAgent

agent = CodeGenerationAgent(config)
card = agent.to_a2a_card()

# Generated A2A Card:
# {
#   "name": "CodeGenerationAgent",
#   "description": "Generates production-ready code with tests",
#   "primary_capabilities": [
#     {
#       "name": "code_generation",
#       "description": "Generate Python code with unit tests",
#       "keywords": ["code", "python", "generation", "programming"]
#     },
#     {
#       "name": "test_writing",
#       "description": "Write comprehensive unit tests",
#       "keywords": ["test", "unittest", "pytest", "testing"]
#     }
#   ],
#   "input_schema": {...},
#   "output_schema": {...}
# }
```

### Semantic Matching Algorithm

```python
# Simplified A2A matching logic

def match_task_to_agent(task: str, agents: List[BaseAgent]) -> BaseAgent:
    """
    Match task to best agent using A2A capability matching.

    Returns agent with highest capability match score.
    """
    best_agent = None
    best_score = 0.0

    for agent in agents:
        # Get A2A capability card
        card = agent.to_a2a_card()

        # Calculate match score for each capability
        for capability in card.primary_capabilities:
            score = capability.matches_requirement(task)
            # Score based on keyword overlap, semantic similarity

            if score > best_score:
                best_score = score
                best_agent = agent

    return best_agent
```

### Capability Match Example

```python
# Task: "Analyze sales data and create visualization"

# Agent 1: CodeGenerationAgent
# - Primary capability: "Code generation and programming"
# - Keywords: ["code", "python", "programming", "function"]
# - Match score: 0.3 (weak match - "programming" tangentially related)

# Agent 2: DataAnalysisAgent
# - Primary capability: "Data analysis and visualization"
# - Keywords: ["data", "analysis", "visualization", "statistics"]
# - Match score: 0.9 (strong match - "analysis", "data", "visualization")

# Agent 3: WritingAgent
# - Primary capability: "Content writing and editing"
# - Keywords: ["writing", "article", "content", "blog"]
# - Match score: 0.1 (no match)

# Result: DataAnalysisAgent selected (score: 0.9)
```

---

## Quick Start

### Basic Semantic Routing

```python
from kaizen.orchestration.pipeline import Pipeline
from kaizen.agents import CodeGenerationAgent, DataAnalysisAgent, WritingAgent

# Create agents
code_agent = CodeGenerationAgent(config)
data_agent = DataAnalysisAgent(config)
writing_agent = WritingAgent(config)

# Create router with semantic routing
pipeline = Pipeline.router(
    agents=[code_agent, data_agent, writing_agent],
    routing_strategy="semantic"
)

# Route requests automatically
result = pipeline.run(task="Generate Python function to calculate fibonacci")
# → Routed to code_agent

result = pipeline.run(task="Analyze customer churn data")
# → Routed to data_agent

result = pipeline.run(task="Write blog post about machine learning")
# → Routed to writing_agent
```

### Load Balancing with Round-Robin

```python
from kaizen.orchestration.pipeline import Pipeline

# Create identical worker agents
worker1 = SimpleQAAgent(config, agent_id="worker1")
worker2 = SimpleQAAgent(config, agent_id="worker2")
worker3 = SimpleQAAgent(config, agent_id="worker3")

# Round-robin load balancing
pipeline = Pipeline.router(
    agents=[worker1, worker2, worker3],
    routing_strategy="round-robin"
)

# Distribute load evenly
for i in range(9):
    result = pipeline.run(question=f"Question {i}")
    # worker1 handles 3 requests
    # worker2 handles 3 requests
    # worker3 handles 3 requests
```

### Error Handling

```python
from kaizen.orchestration.pipeline import Pipeline

# Graceful error handling (default)
pipeline = Pipeline.router(
    agents=[agent1, agent2],
    routing_strategy="semantic",
    error_handling="graceful"
)

result = pipeline.run(task="Task that may fail")

if "error" in result:
    print(f"Agent failed: {result['error']}")
    print(f"Status: {result['status']}")
else:
    print(f"Success: {result}")

# Fail-fast mode
pipeline = Pipeline.router(
    agents=[agent1, agent2],
    routing_strategy="semantic",
    error_handling="fail-fast"  # Raises exception on error
)

try:
    result = pipeline.run(task="Task")
except Exception as e:
    print(f"Pipeline failed: {e}")
```

---

## Configuration

### Pipeline.router() Parameters

```python
pipeline = Pipeline.router(
    agents=[agent1, agent2, agent3],      # List of agents (required)
    routing_strategy="semantic",          # Routing strategy (default: "semantic")
    error_handling="graceful"             # Error handling mode (default: "graceful")
)
```

**Parameters:**

| Parameter | Type | Default | Options | Description |
|-----------|------|---------|---------|-------------|
| `agents` | List[BaseAgent] | Required | N/A | List of agents to route between (must not be empty) |
| `routing_strategy` | str | "semantic" | semantic, round-robin, random | Routing strategy to use |
| `error_handling` | str | "graceful" | graceful, fail-fast | Error handling mode |

### Error Handling Modes

**Graceful (Default):**
- Returns error dict on failure
- Continues execution
- Allows error recovery

```python
result = pipeline.run(task="Task")
if "error" in result:
    # Handle error gracefully
    fallback_result = handle_error(result)
```

**Fail-Fast:**
- Raises exception on failure
- Stops execution immediately
- Use for critical operations

```python
try:
    result = pipeline.run(task="Critical task")
except Exception as e:
    # Handle exception
    log_critical_failure(e)
```

---

## Advanced Usage

### Multi-Strategy Routing

Combine multiple routing strategies for complex scenarios:

```python
from kaizen.orchestration.pipeline import Pipeline

# Strategy 1: Semantic routing for mixed tasks
semantic_router = Pipeline.router(
    agents=[code_agent, data_agent, writing_agent],
    routing_strategy="semantic"
)

# Strategy 2: Round-robin for load balancing
load_balancer = Pipeline.router(
    agents=[worker1, worker2, worker3],
    routing_strategy="round-robin"
)

# Route based on task type
def route_request(task: str, task_type: str):
    if task_type == "specialized":
        return semantic_router.run(task=task)
    elif task_type == "general":
        return load_balancer.run(task=task)
```

### Custom Agent Selection

Extend MetaControllerPipeline for custom logic:

```python
from kaizen.orchestration.patterns.meta_controller import MetaControllerPipeline

class CustomRouter(MetaControllerPipeline):
    def _select_agent(self, task: str = None):
        """Custom agent selection logic."""
        # Priority 1: Use A2A if available
        if self.routing_strategy == "semantic" and task:
            agent = self._select_agent_via_a2a(task)
            if agent:
                return agent

        # Priority 2: Custom business logic
        if "urgent" in task.lower():
            return self.agents[0]  # Priority agent

        # Priority 3: Fallback to round-robin
        return self._select_agent_round_robin()
```

### Monitoring and Metrics

Track routing decisions for analysis:

```python
from kaizen.orchestration.pipeline import Pipeline

class MonitoredRouter:
    def __init__(self, agents):
        self.router = Pipeline.router(agents=agents, routing_strategy="semantic")
        self.routing_stats = {"total": 0, "by_agent": {}}

    def run(self, **inputs):
        result = self.router.run(**inputs)

        # Track routing decision
        self.routing_stats["total"] += 1
        agent_id = result.get("agent_id", "unknown")
        self.routing_stats["by_agent"][agent_id] = \
            self.routing_stats["by_agent"].get(agent_id, 0) + 1

        return result

    def get_stats(self):
        return self.routing_stats

# Usage
router = MonitoredRouter(agents=[code_agent, data_agent])

for task in tasks:
    result = router.run(task=task)

# View routing statistics
stats = router.get_stats()
print(f"Total requests: {stats['total']}")
print(f"Distribution: {stats['by_agent']}")
```

---

## Best Practices

### 1. Use Semantic Routing for Specialized Agents

✅ **DO**: Use semantic routing when agents have distinct capabilities
```python
pipeline = Pipeline.router(
    agents=[code_expert, data_scientist, technical_writer],
    routing_strategy="semantic"
)
```

❌ **DON'T**: Use semantic routing for identical agents (use round-robin)
```python
# WRONG: All agents identical, semantic routing unnecessary
pipeline = Pipeline.router(
    agents=[qa_agent1, qa_agent2, qa_agent3],
    routing_strategy="semantic"  # Wasteful A2A matching
)
```

### 2. Provide Task Context for Better Matching

✅ **DO**: Provide descriptive task descriptions
```python
result = pipeline.run(
    task="Analyze customer churn data and create visualization dashboard"
)
# Clear task description enables accurate A2A matching
```

❌ **DON'T**: Use vague task descriptions
```python
# WRONG: Vague task, poor A2A matching
result = pipeline.run(task="Do analysis")
```

### 3. Set Appropriate Error Handling

✅ **DO**: Use graceful for production, fail-fast for critical operations
```python
# Production: Graceful error handling
pipeline = Pipeline.router(agents, error_handling="graceful")

# Critical: Fail-fast for data integrity
pipeline = Pipeline.router(agents, error_handling="fail-fast")
```

### 4. Monitor Routing Decisions

✅ **DO**: Track which agents are selected
```python
result = pipeline.run(task="Task")
if hasattr(result, "agent_id"):
    metrics.record("agent_selected", result.agent_id)
```

### 5. Test Routing Logic

✅ **DO**: Write tests for routing behavior
```python
def test_semantic_routing():
    pipeline = Pipeline.router(
        agents=[code_agent, data_agent],
        routing_strategy="semantic"
    )

    # Test code task routes to code_agent
    result = pipeline.run(task="Generate Python function")
    assert result["agent_id"] == "code_agent"

    # Test data task routes to data_agent
    result = pipeline.run(task="Analyze dataset")
    assert result["agent_id"] == "data_agent"
```

---

## Troubleshooting

### Issue 1: Wrong Agent Selected

**Symptom**: Semantic routing selects incorrect agent

**Causes**:
1. Agent capability keywords don't match task
2. Multiple agents have similar capabilities
3. A2A capability cards not descriptive enough

**Solutions**:

```python
# Solution 1: Verify A2A capability cards
for agent in agents:
    card = agent.to_a2a_card()
    print(f"Agent: {card.name}")
    print(f"Capabilities: {card.primary_capabilities}")
    # Check if capabilities match expected tasks

# Solution 2: Provide more specific task descriptions
result = pipeline.run(
    task="Analyze sales data using statistical methods and create interactive visualization"
    # More specific than: "Analyze data"
)

# Solution 3: Use custom agent selection
class PriorityRouter(MetaControllerPipeline):
    def _select_agent(self, task: str = None):
        # Add priority logic before A2A matching
        if "urgent" in task.lower():
            return self.priority_agent
        return super()._select_agent(task)
```

### Issue 2: Round-Robin Not Distributing Evenly

**Symptom**: Some agents receive more requests than others

**Causes**:
1. Concurrent requests
2. Pipeline instance not shared
3. Round-robin state not persisted

**Solutions**:

```python
# Solution 1: Use single pipeline instance
pipeline = Pipeline.router(agents, routing_strategy="round-robin")

# Use same instance for all requests
for task in tasks:
    result = pipeline.run(task=task)

# Solution 2: Track distribution
class DistributionTracker:
    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.counts = {agent.agent_id: 0 for agent in pipeline.agents}

    def run(self, **inputs):
        result = self.pipeline.run(**inputs)
        agent_id = result.get("agent_id")
        self.counts[agent_id] = self.counts.get(agent_id, 0) + 1
        return result

tracker = DistributionTracker(pipeline)
```

### Issue 3: A2A Capability Matching Fails

**Symptom**: All requests routed to first agent (fallback behavior)

**Causes**:
1. A2A import failed
2. Agents don't have to_a2a_card() method
3. Capability scores all 0.0

**Solutions**:

```python
# Solution 1: Check A2A availability
from kaizen.orchestration.patterns.meta_controller import A2A_AVAILABLE

if not A2A_AVAILABLE:
    print("WARNING: A2A not available, using fallback routing")

# Solution 2: Verify BaseAgent inheritance
from kaizen.core.base_agent import BaseAgent

assert isinstance(agent, BaseAgent), "Agent must extend BaseAgent"

# Solution 3: Debug capability matching
pipeline = Pipeline.router(agents, routing_strategy="semantic")

# Add debug logging
for agent in pipeline.agents:
    card = agent.to_a2a_card()
    for cap in card.primary_capabilities:
        score = cap.matches_requirement("Your task here")
        print(f"{agent.agent_id}: {cap.name} = {score}")
```

### Issue 4: Graceful Error Handling Not Working

**Symptom**: Exceptions raised despite graceful mode

**Causes**:
1. Error occurs before agent selection
2. Error occurs during pipeline initialization
3. Agent raises unhandled exception type

**Solutions**:

```python
# Solution 1: Wrap in try/except
try:
    result = pipeline.run(task="Task")
    if "error" in result:
        handle_agent_error(result)
except Exception as e:
    handle_pipeline_error(e)

# Solution 2: Check pipeline configuration
pipeline = Pipeline.router(
    agents=agents,
    routing_strategy="semantic",
    error_handling="graceful"  # Ensure graceful mode set
)

# Solution 3: Use fail-fast to identify error source
pipeline_debug = Pipeline.router(
    agents=agents,
    error_handling="fail-fast"  # Get full traceback
)
```

### Issue 5: Performance Issues with Semantic Routing

**Symptom**: Routing takes too long

**Causes**:
1. Too many agents
2. A2A matching overhead
3. Complex capability matching

**Solutions**:

```python
# Solution 1: Use round-robin for high throughput
pipeline = Pipeline.router(
    agents=agents,
    routing_strategy="round-robin"  # Faster than semantic
)

# Solution 2: Reduce agent pool
# Create specialized routers for different task types
code_router = Pipeline.router(
    agents=[code_agent1, code_agent2],  # Only 2 agents
    routing_strategy="semantic"
)

data_router = Pipeline.router(
    agents=[data_agent1, data_agent2],  # Only 2 agents
    routing_strategy="semantic"
)

# Solution 3: Cache routing decisions
routing_cache = {}

def route_with_cache(task: str):
    if task in routing_cache:
        return routing_cache[task]

    result = pipeline.run(task=task)
    routing_cache[task] = result
    return result
```

---

## Summary

**Meta-Controller routing** provides intelligent agent selection through:

**Three Routing Strategies:**
1. **Semantic**: A2A capability-based matching (no hardcoded logic)
2. **Round-Robin**: Sequential rotation for load balancing
3. **Random**: Random selection for simple distribution

**Key Features:**
- ✅ No hardcoded if/else routing logic
- ✅ Semantic understanding via A2A protocol
- ✅ Automatic best-fit agent selection
- ✅ Graceful error handling with fallback
- ✅ Composable with Pipeline pattern

**When to Use:**
- Multiple specialized agents available
- Dynamic task routing needed
- Semantic matching required
- Load balancing across agents

**Best Practices:**
- Use semantic routing for specialized agents
- Use round-robin for identical agents
- Provide descriptive task descriptions
- Monitor routing decisions
- Test routing logic comprehensively

---

**Framework**: Kaizen AI Framework built on Kailash Core SDK
**License**: MIT
**Location**: `kaizen.orchestration.patterns.meta_controller`
**Related**: [Multi-Agent Coordination Guide](multi-agent-coordination.md)
**Tests**: `tests/unit/orchestration/test_meta_controller_pipeline.py`, `tests/e2e/autonomy/test_meta_controller_e2e.py`
