# A2A Agent Coordination - Multi-Agent Orchestration

## Basic Setup
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.ai.a2a import A2ACoordinatorNode, SharedMemoryPoolNode
from kailash.runtime.local import LocalRuntime

# Create coordination workflow
workflow = WorkflowBuilder()

# Shared memory for agent communication
workflow.add_node("SharedMemoryPoolNode", "memory", {}))

# A2A coordinator
workflow.add_node("coordinator", A2ACoordinatorNode())
workflow.add_connection("memory", "result", "coordinator", "input")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

```

## Agent Registration
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.ai.a2a import A2ACoordinatorNode

# Register multiple agents with skills
agents = [
    {
        "id": "analyst_001",
        "skills": ["analysis", "data"],
        "role": "data_analyst",
        "max_concurrent_tasks": 3
    },
    {
        "id": "researcher_001",
        "skills": ["research", "synthesis"],
        "role": "researcher",
        "max_concurrent_tasks": 2
    }
]

workflow = WorkflowBuilder()
workflow.add_node("coordinator", A2ACoordinatorNode())
runtime = LocalRuntime()

# Register each agent
for agent in agents:
    results, run_id = runtime.execute(workflow, parameters={
        "coordinator": {
            "action": "register",
            "agent_info": agent
        }
    })

```

## Task Delegation Strategies

### Skill-Based Matching
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.ai.a2a import A2ACoordinatorNode

workflow = WorkflowBuilder()
workflow.add_node("coordinator", A2ACoordinatorNode())
runtime = LocalRuntime()

# Delegate by required skills
results, run_id = runtime.execute(workflow, parameters={
    "coordinator": {
        "action": "delegate",
        "task": {
            "id": "analysis_q4",
            "type": "analysis",
            "required_skills": ["analysis", "data"],
            "priority": "high"
        },
        "coordination_strategy": "best_match"
    }
})

```

### Load Balancing
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.ai.a2a import A2ACoordinatorNode

workflow = WorkflowBuilder()
workflow.add_node("coordinator", A2ACoordinatorNode())
runtime = LocalRuntime()

# Distribute tasks evenly
results, run_id = runtime.execute(workflow, parameters={
    "coordinator": {
        "action": "delegate",
        "task": {
            "type": "documentation",
            "required_skills": ["writing"],
            "priority": "medium"
        },
        "coordination_strategy": "load_balance"
    }
})

```

## Dynamic Team Formation
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.ai.a2a import A2ACoordinatorNode

workflow = WorkflowBuilder()
workflow.add_node("coordinator", A2ACoordinatorNode())
runtime = LocalRuntime()

# Form teams for complex projects
complex_task = {
    "id": "market_research",
    "type": "multi_phase",
    "phases": [
        {
            "name": "data_collection",
            "required_skills": ["research"],
            "duration": 240
        },
        {
            "name": "analysis",
            "required_skills": ["analysis"],
            "duration": 180
        }
    ]
}

results, run_id = runtime.execute(workflow, parameters={
    "coordinator": {
        "action": "form_team",
        "task": complex_task,
        "team_strategy": "skill_complementarity"
    }
})

```

## Shared Memory Integration
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.ai.a2a import SharedMemoryPoolNode

workflow = WorkflowBuilder()
workflow.add_node("SharedMemoryPoolNode", "memory", {}))
runtime = LocalRuntime()

# Store agent findings
results, run_id = runtime.execute(workflow, parameters={
    "memory": {
        "action": "store_context",
        "context": {
            "agent_id": "researcher_001",
            "findings": "Market growth 15%",
            "confidence": 0.85,
            "tags": ["market", "growth"]
        }
    }
})

# Retrieve relevant context
results, run_id = runtime.execute(workflow, parameters={
    "memory": {
        "action": "retrieve_context",
        "query": {
            "tags": ["market"],
            "max_items": 10
        }
    }
})

```

## Performance Tracking
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.ai.a2a import A2ACoordinatorNode

workflow = WorkflowBuilder()
workflow.add_node("coordinator", A2ACoordinatorNode())
runtime = LocalRuntime()

# Report task completion
results, run_id = runtime.execute(workflow, parameters={
    "coordinator": {
        "action": "report_completion",
        "task_result": {
            "agent_id": "analyst_001",
            "task_id": "analysis_q4",
            "completion_time": 95,
            "quality_score": 8.5
        }
    }
})

```

## Best Practices

### Agent Management
- Register agents with clear skill definitions
- Set appropriate concurrent task limits
- Implement health checks for agent availability
- Clean up inactive agents regularly

### Task Delegation
- Use skill-based matching for quality
- Use load balancing for throughput
- Set task priorities appropriately
- Include timeout and fallback strategies

### Memory Usage
- Limit memory size to prevent overflow
- Use attention windows for recent context
- Tag contexts for efficient retrieval
- Implement retention policies

### Error Handling
```python
try:
    results, _ = runtime.execute(workflow, parameters={
        "coordinator": {"action": "delegate", "task": task}
    })
except Exception as e:
    # Fallback to manual assignment
    print(f"Coordination failed: {e}")

```

## Next Steps
- [Self-Organizing Agents](024-self-organizing-agents.md) - Autonomous teams
- [Cyclic Workflows](019-cyclic-workflows-basics.md) - Iterative coordination
- [Advanced Features](../developer/03-advanced-features.md) - Enterprise patterns
