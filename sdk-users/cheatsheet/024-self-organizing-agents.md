# Self-Organizing Agents - Autonomous Team Formation

## Complete Self-Organizing System
```python
from kailash import Workflow
from kailash.nodes.ai.self_organizing import (
    AgentPoolManagerNode, ProblemAnalyzerNode,
    TeamFormationNode, SelfOrganizingAgentNode
)
from kailash.nodes.ai.intelligent_agent_orchestrator import (
    OrchestrationManagerNode, IntelligentCacheNode
)
from kailash.nodes.ai.a2a import SharedMemoryPoolNode
from kailash.runtime.local import LocalRuntime

# Build self-organizing workflow
workflow = Workflow("self-org", name="Self-Organizing System")

# Core components
workflow.add_node("memory", SharedMemoryPoolNode(
    memory_size_limit=1000,
    attention_window=50
))
workflow.add_node("cache", IntelligentCacheNode(
    ttl=3600,
    similarity_threshold=0.8
))

# Analysis and team formation
workflow.add_node("analyzer", ProblemAnalyzerNode())
workflow.add_node("team_former", TeamFormationNode(
    formation_strategy="capability_matching"
))

# Agent pool
workflow.add_node("pool", AgentPoolManagerNode(
    max_active_agents=20,
    agent_timeout=120
))

# Orchestration
workflow.add_node("orchestrator", OrchestrationManagerNode(
    max_iterations=10,
    quality_threshold=0.85
))

# Connect components
workflow.connect("orchestrator", "analyzer")
workflow.connect("analyzer", "team_former")
workflow.connect("team_former", "pool")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

```

## Problem Analysis
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.ai.intelligent_agent_orchestrator import OrchestrationManagerNode
from kailash.nodes.ai.self_organizing import ProblemAnalyzerNode

workflow = Workflow("problem-analysis")
workflow.add_node("orchestrator", OrchestrationManagerNode())
workflow.add_node("analyzer", ProblemAnalyzerNode())
runtime = LocalRuntime()

# Complex problem decomposition
results, run_id = runtime.execute(workflow, parameters={
    "orchestrator": {
        "query": "Analyze market trends for fintech growth",
        "problem_type": "strategic_analysis",
        "context": {
            "domain": "fintech",
            "depth": "comprehensive"
        }
    },
    "analyzer": {
        "decomposition_strategy": "hierarchical",
        "domain_knowledge": ["finance", "technology"]
    }
})

```

## Team Formation
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.ai.self_organizing import TeamFormationNode

workflow = Workflow("team-formation")
workflow.add_node("team_former", TeamFormationNode())
runtime = LocalRuntime()

# Form capability-based teams
results, run_id = runtime.execute(workflow, parameters={
    "team_former": {
        "required_capabilities": [
            "data_analysis",
            "machine_learning",
            "technical_writing"
        ],
        "team_size_range": [3, 7],
        "collaboration_style": "cross_functional"
    }
})

# Multi-phase team formation
results, run_id = runtime.execute(workflow, parameters={
    "team_former": {
        "problem_phases": [
            {
                "name": "research",
                "requirements": ["research_skills"],
                "duration": "2_weeks"
            },
            {
                "name": "analysis",
                "requirements": ["data_analysis"],
                "duration": "3_weeks"
            }
        ]
    }
})

```

## Agent Pool Management
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.ai.self_organizing import AgentPoolManagerNode

workflow = Workflow("agent-pool")
workflow.add_node("pool", AgentPoolManagerNode())
runtime = LocalRuntime()

# Intelligent agent allocation
results, run_id = runtime.execute(workflow, parameters={
    "pool": {
        "allocation_request": {
            "priority": "high",
            "required_skills": ["python", "ml"],
            "quality_requirements": {
                "accuracy": 0.95,
                "timeliness": 0.85
            }
        },
        "optimization_criteria": [
            "skill_match_score",
            "agent_availability"
        ]
    }
})

# Health check and scaling
results, run_id = runtime.execute(workflow, parameters={
    "pool": {
        "action": "health_check"
    }
})

```

## Orchestration Patterns
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.ai.intelligent_agent_orchestrator import OrchestrationManagerNode

workflow = Workflow("orchestration")
workflow.add_node("orchestrator", OrchestrationManagerNode())
runtime = LocalRuntime()

# Multi-phase orchestration
results, run_id = runtime.execute(workflow, parameters={
    "orchestrator": {
        "project": {
            "name": "AI Strategy",
            "phases": [
                {
                    "name": "assessment",
                    "objectives": ["current_state"],
                    "success_criteria": ["completeness > 0.9"]
                },
                {
                    "name": "planning",
                    "objectives": ["roadmap"],
                    "success_criteria": ["feasibility > 0.8"]
                }
            ]
        },
        "orchestration_mode": "phase_gated"
    }
})

```

## Intelligent Caching
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.ai.intelligent_agent_orchestrator import IntelligentCacheNode

workflow = Workflow("intelligent-cache")
workflow.add_node("cache", IntelligentCacheNode())
runtime = LocalRuntime()

# Store solutions for reuse
results, run_id = runtime.execute(workflow, parameters={
    "cache": {
        "action": "store",
        "content": {
            "problem_type": "market_analysis",
            "domain": "fintech",
            "insights": ["15% growth", "AI adoption"],
            "confidence": 0.92
        }
    }
})

# Retrieve similar solutions
results, run_id = runtime.execute(workflow, parameters={
    "cache": {
        "action": "retrieve",
        "query": {
            "problem_type": "market_analysis",
            "domain": "healthcare_tech"
        },
        "similarity_threshold": 0.7
    }
})

```

## Best Practices

### Gradual Autonomy
```python
# Increase autonomy over iterations
autonomy_levels = [
    {"iterations": [0, 2], "level": "guided"},
    {"iterations": [3, 6], "level": "supervised"},
    {"iterations": [7, 10], "level": "autonomous"}
]

```

### Quality Gates
```python
quality_gates = {
    "agent_level": {
        "output_validation": True,
        "self_assessment": True
    },
    "team_level": {
        "cross_validation": True,
        "consensus_check": True
    },
    "system_level": {
        "quality_threshold": 0.85
    }
}

```

### Error Handling
```python
try:
    results, _ = runtime.execute(workflow, parameters={
        "orchestrator": {"query": "Complex problem"}
    })
except Exception as e:
    # Fallback to simpler approach
    print(f"Self-organizing failed: {e}")

```

## Common Patterns

### Research Team Formation
```python
from kailash import Workflow
from kailash.nodes.ai.self_organizing import SelfOrganizingAgentNode

# Form research team for complex investigation
workflow = Workflow("research-team")
workflow.add_node("research_team", SelfOrganizingAgentNode(
    specialization="research",
    autonomy_level="high",
    collaboration_preference="peer_to_peer"
))

```

### Analysis Swarm
```python
from kailash import Workflow
from kailash.nodes.ai.self_organizing import SelfOrganizingAgentNode

workflow = Workflow("analysis-swarm")

# Multiple analysts working in parallel
for i in range(5):
    workflow.add_node(f"analyst_{i}", SelfOrganizingAgentNode(
        specialization="analysis",
        autonomy_level="medium"
    ))

```

### Synthesis Collective
```python
from kailash import Workflow
from kailash.nodes.ai.self_organizing import SelfOrganizingAgentNode

# Collective intelligence for synthesis
workflow = Workflow("synthesis-collective")
workflow.add_node("synthesis", SelfOrganizingAgentNode(
    specialization="synthesis",
    collaboration_preference="consensus_driven"
))

```

## Next Steps
- [A2A Coordination](023-a2a-agent-coordination.md) - Agent communication
- [Advanced Features](../developer/03-advanced-features.md) - Enterprise patterns
- [Production Workflows](../workflows/) - Real-world examples
