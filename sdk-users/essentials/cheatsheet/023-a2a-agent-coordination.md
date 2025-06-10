# A2A Agent Coordination

## A2ACoordinatorNode Patterns

```python
from kailash import Workflow
from kailash.nodes.ai.a2a import A2ACoordinatorNode, SharedMemoryPoolNode
from kailash.runtime.local import LocalRuntime

# Basic A2A coordination workflow
workflow = Workflow("a2a-coordination", "Agent-to-Agent Coordination")

# Shared memory for agent communication
workflow.add_node("memory", SharedMemoryPoolNode(
    memory_size_limit=1000,
    attention_window=50
))

# A2A coordinator for task delegation
workflow.add_node("coordinator", A2ACoordinatorNode())

# Connect components
workflow.connect("memory", "coordinator")

# Execute with coordination strategy
runtime = LocalRuntime()
results, _ = runtime.execute(workflow, parameters={
    "coordinator": {
        "action": "register",
        "agent_info": {
            "id": "analyst_001",
            "skills": ["analysis", "data"],
            "role": "analyst"
        }
    }
})
```

## Agent Registration Patterns

### Register Multiple Agents
```python
# Register different types of agents
agents = [
    {
        "id": "analyst_001",
        "skills": ["analysis", "data", "visualization"],
        "role": "data_analyst",
        "capabilities": ["statistical_analysis", "data_mining"],
        "max_concurrent_tasks": 3
    },
    {
        "id": "researcher_001",
        "skills": ["research", "investigation", "synthesis"],
        "role": "researcher",
        "capabilities": ["web_search", "document_analysis"],
        "max_concurrent_tasks": 2
    },
    {
        "id": "writer_001",
        "skills": ["writing", "communication", "editing"],
        "role": "content_creator",
        "capabilities": ["technical_writing", "copywriting"],
        "max_concurrent_tasks": 5
    }
]

# Register each agent
for agent_info in agents:
    results, _ = runtime.execute(workflow, parameters={
        "coordinator": {
            "action": "register",
            "agent_info": agent_info
        }
    })
    print(f"Registered agent: {agent_info['id']}")
```

## Task Delegation Strategies

### Skill-Based Matching
```python
# Delegate task based on required skills
task = {
    "id": "data_analysis_q4",
    "type": "analysis",
    "description": "Analyze Q4 sales data and identify trends",
    "required_skills": ["analysis", "data"],
    "priority": "high",
    "estimated_duration": 120,  # minutes
    "context": {
        "data_source": "sales_db",
        "output_format": "dashboard"
    }
}

results, _ = runtime.execute(workflow, parameters={
    "coordinator": {
        "action": "delegate",
        "task": task,
        "coordination_strategy": "best_match"
    }
})

delegation_result = results.get("coordinator", {})
if delegation_result.get("success"):
    print(f"Task delegated to: {delegation_result['assigned_agent']}")
    print(f"Match score: {delegation_result['match_score']}")
```

### Load Balancing Strategy
```python
# Distribute tasks evenly across available agents
results, _ = runtime.execute(workflow, parameters={
    "coordinator": {
        "action": "delegate",
        "task": {
            "type": "content_creation",
            "description": "Write product documentation",
            "required_skills": ["writing"],
            "priority": "medium"
        },
        "coordination_strategy": "load_balance"
    }
})
```

### Priority-Based Assignment
```python
# Assign high-priority tasks to best available agents
results, _ = runtime.execute(workflow, parameters={
    "coordinator": {
        "action": "delegate",
        "task": {
            "type": "urgent_analysis",
            "description": "Emergency system failure analysis",
            "required_skills": ["analysis", "troubleshooting"],
            "priority": "critical",
            "deadline": "1h"
        },
        "coordination_strategy": "priority_first"
    }
})
```

## Cycle-Aware A2A Coordination

```python
from kailash.nodes.base import CycleAwareNode

# Enhanced A2A coordinator that learns across cycles
workflow = Workflow("cyclic-a2a", "Cyclic A2A Coordination")

# Pre-register agents
coordinator = A2ACoordinatorNode()
for agent_config in agent_configs:
    coordinator.run({}, action="register", agent_info=agent_config)

workflow.add_node("coordinator", coordinator)
workflow.add_node("evaluator", ConvergenceCheckerNode())

# Cycle: delegate → learn from performance → delegate better
workflow.connect("coordinator", "evaluator",
    mapping={"cycle_info.active_agents": "value"})
workflow.connect("evaluator", "coordinator",
    cycle=True,
    max_iterations=10,
    convergence_check="all_agents_active == True")

# Execute with learning-enabled coordination
results, _ = runtime.execute(workflow, parameters={
    "coordinator": {
        "action": "delegate",
        "task": {
            "type": "iterative_analysis",
            "description": "Multi-round market analysis",
            "required_skills": ["analysis", "research"],
            "iterations_needed": 5
        },
        "coordination_strategy": "adaptive_learning"
    },
    "evaluator": {
        "threshold": 3,  # Minimum active agents
        "mode": "threshold"
    }
})
```

## Agent Performance Tracking

### Performance Metrics Collection
```python
class PerformanceTrackingCoordinator(A2ACoordinatorNode):
    """Enhanced coordinator that tracks agent performance."""

    def run(self, context, **kwargs):
        action = kwargs.get("action", "delegate")

        if action == "report_completion":
            # Track task completion metrics
            task_result = kwargs.get("task_result", {})
            agent_id = task_result.get("agent_id")
            task_id = task_result.get("task_id")

            # Calculate performance metrics
            completion_time = task_result.get("completion_time", 0)
            quality_score = task_result.get("quality_score", 0.0)

            # Update agent performance history
            self.update_agent_performance(agent_id, {
                "task_id": task_id,
                "completion_time": completion_time,
                "quality_score": quality_score,
                "timestamp": time.time()
            })

            return {
                "performance_updated": True,
                "agent_id": agent_id,
                "new_rating": self.get_agent_rating(agent_id)
            }

        # Call parent for other actions
        return super().run(context, **kwargs)

# Usage
workflow.add_node("coordinator", PerformanceTrackingCoordinator())

# Report task completion
results, _ = runtime.execute(workflow, parameters={
    "coordinator": {
        "action": "report_completion",
        "task_result": {
            "agent_id": "analyst_001",
            "task_id": "analysis_q4",
            "completion_time": 95,  # minutes
            "quality_score": 8.5,   # out of 10
            "output_quality": "excellent"
        }
    }
})
```

## Advanced Coordination Patterns

### Dynamic Team Formation
```python
# Form teams dynamically based on task complexity
complex_task = {
    "id": "market_research_project",
    "type": "multi_phase_research",
    "description": "Comprehensive market analysis for new product launch",
    "phases": [
        {
            "name": "data_collection",
            "required_skills": ["research", "data"],
            "estimated_duration": 240
        },
        {
            "name": "analysis",
            "required_skills": ["analysis", "statistical_modeling"],
            "estimated_duration": 180
        },
        {
            "name": "report_generation",
            "required_skills": ["writing", "visualization"],
            "estimated_duration": 120
        }
    ],
    "coordination_type": "team_formation"
}

results, _ = runtime.execute(workflow, parameters={
    "coordinator": {
        "action": "form_team",
        "task": complex_task,
        "team_strategy": "skill_complementarity"
    }
})

team_info = results.get("coordinator", {})
if team_info.get("team_formed"):
    print(f"Team size: {len(team_info['team_members'])}")
    for member in team_info['team_members']:
        print(f"- {member['id']}: {member['assigned_phase']}")
```

### Hierarchical Coordination
```python
# Multi-level coordination with manager and worker agents
workflow = Workflow("hierarchical-a2a", "Hierarchical Agent Coordination")

# Manager coordinator
workflow.add_node("manager", A2ACoordinatorNode())

# Department coordinators
workflow.add_node("research_lead", A2ACoordinatorNode())
workflow.add_node("analysis_lead", A2ACoordinatorNode())
workflow.add_node("content_lead", A2ACoordinatorNode())

# Connect hierarchy
workflow.connect("manager", "research_lead")
workflow.connect("manager", "analysis_lead")
workflow.connect("manager", "content_lead")

# Execute hierarchical delegation
results, _ = runtime.execute(workflow, parameters={
    "manager": {
        "action": "delegate_hierarchical",
        "project": {
            "name": "Product Launch Analysis",
            "departments": ["research", "analysis", "content"],
            "coordination_style": "hierarchical"
        }
    }
})
```

## Shared Memory Integration

### Context Sharing Between Agents
```python
# Configure shared memory with attention mechanism
workflow.add_node("memory", SharedMemoryPoolNode(
    memory_size_limit=5000,     # Total memory capacity
    attention_window=100,       # Recent items to focus on
    retention_policy="importance"  # Keep important items longer
))

# Agents share context through memory
results, _ = runtime.execute(workflow, parameters={
    "memory": {
        "action": "store_context",
        "context": {
            "agent_id": "researcher_001",
            "findings": "Market shows 15% growth in AI tools",
            "confidence": 0.85,
            "sources": ["industry_report_2024", "survey_data"],
            "tags": ["market_research", "ai_tools", "growth"]
        }
    }
})

# Other agents can retrieve relevant context
results, _ = runtime.execute(workflow, parameters={
    "memory": {
        "action": "retrieve_context",
        "query": {
            "tags": ["market_research"],
            "agent_requesting": "analyst_001",
            "max_items": 10
        }
    }
})
```

### Cross-Agent Communication
```python
# Enable agents to send messages to each other
class CommunicatingCoordinator(A2ACoordinatorNode):
    def run(self, context, **kwargs):
        action = kwargs.get("action")

        if action == "send_message":
            message = kwargs.get("message", {})
            recipient = message.get("to")
            sender = message.get("from")
            content = message.get("content")

            # Route message through shared memory
            self.store_agent_message(sender, recipient, content)

            return {
                "message_sent": True,
                "from": sender,
                "to": recipient,
                "timestamp": time.time()
            }

        elif action == "get_messages":
            agent_id = kwargs.get("agent_id")
            messages = self.get_agent_messages(agent_id)

            return {
                "messages": messages,
                "unread_count": len([m for m in messages if not m.get("read")])
            }

        return super().run(context, **kwargs)
```

## Monitoring and Analytics

### Real-time Coordination Metrics
```python
class MonitoredCoordinator(A2ACoordinatorNode):
    """Coordinator with built-in monitoring."""

    def run(self, context, **kwargs):
        # Execute coordination
        result = super().run(context, **kwargs)

        # Collect metrics
        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        metrics = {
            "iteration": iteration,
            "active_agents": self.get_active_agent_count(),
            "pending_tasks": self.get_pending_task_count(),
            "average_response_time": self.calculate_avg_response_time(),
            "success_rate": self.calculate_success_rate(),
            "resource_utilization": self.calculate_resource_usage()
        }

        # Add metrics to result
        result["coordination_metrics"] = metrics

        # Log performance every 5 iterations
        if iteration % 5 == 0:
            print(f"Coordination Metrics (Iteration {iteration}):")
            for key, value in metrics.items():
                print(f"  {key}: {value}")

        return result
```

## Best Practices

### 1. Agent Lifecycle Management
```python
# Proper agent registration and cleanup
def register_agent_pool(coordinator, agent_configs):
    """Register multiple agents with error handling."""
    registered = []
    failed = []

    for config in agent_configs:
        try:
            result = coordinator.run({}, action="register", agent_info=config)
            if result.get("success"):
                registered.append(config["id"])
            else:
                failed.append((config["id"], result.get("error")))
        except Exception as e:
            failed.append((config["id"], str(e)))

    return {"registered": registered, "failed": failed}

# Cleanup inactive agents
def cleanup_inactive_agents(coordinator, max_idle_time=3600):
    """Remove agents that have been idle too long."""
    result = coordinator.run({}, action="cleanup_inactive",
                           max_idle_time=max_idle_time)
    return result.get("removed_agents", [])
```

### 2. Error Handling and Recovery
```python
class RobustCoordinator(A2ACoordinatorNode):
    """Coordinator with comprehensive error handling."""

    def run(self, context, **kwargs):
        try:
            return super().run(context, **kwargs)
        except AgentUnavailableError as e:
            # Try alternative agents
            return self.find_alternative_agent(kwargs.get("task"))
        except TaskTimeoutError as e:
            # Reassign task to different agent
            return self.reassign_task(kwargs.get("task"))
        except CoordinationError as e:
            # Fallback to manual coordination
            return self.manual_coordination_fallback(kwargs)
```

### 3. Scalability Considerations
```python
# Configure for high-throughput scenarios
coordinator = A2ACoordinatorNode(
    max_concurrent_tasks=50,
    agent_pool_size=20,
    task_queue_limit=200,
    load_balancing_strategy="weighted_round_robin",
    health_check_interval=30  # seconds
)
```
