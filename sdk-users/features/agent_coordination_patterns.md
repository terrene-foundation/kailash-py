# Agent Coordination Patterns in Kailash SDK

This guide explains the different agent coordination patterns available in Kailash SDK, their key differences, and when to use each approach.

## Overview

Kailash SDK provides multiple approaches for coordinating multi-agent systems:

1. **A2ACoordinatorNode** - Direct orchestration for active workflows
2. **AgentPoolManagerNode** - Decentralized registry for agent management
3. **Hybrid Approach** - Combining both for sophisticated systems

Each pattern serves different needs and can be used independently or together.

## A2ACoordinatorNode: The Project Manager

### Purpose
The A2ACoordinatorNode acts as a centralized project manager, orchestrating specific workflows and managing direct agent interactions.

### Key Features
- **Task Delegation**: Assigns specific tasks to agents based on skills
- **Broadcast Messaging**: Sends updates to groups of agents
- **Consensus Building**: Manages voting and collective decisions
- **Workflow Coordination**: Plans and executes multi-step processes

### Core Actions
```python
# Register agents for a specific project
coordinator.run(
    action="register",
    agent_info={
        "id": "analyst_001",
        "skills": ["data_analysis", "reporting"],
        "role": "analyst"
    }
)

# Delegate tasks with strategies
coordinator.run(
    action="delegate",
    task={
        "name": "Analyze Q3 Data",
        "required_skills": ["data_analysis"],
        "priority": "high"
    },
    coordination_strategy="best_match"  # or "round_robin", "auction"
)

# Broadcast messages to teams
coordinator.run(
    action="broadcast",
    message={
        "content": "Phase 1 complete, begin synthesis",
        "target_roles": ["analyst", "synthesizer"],
        "priority": "high"
    }
)

# Build consensus on decisions
coordinator.run(
    action="consensus",
    consensus_proposal={
        "proposal": "Accept analysis results",
        "require_unanimous": False
    }
)

```

### When to Use A2ACoordinatorNode
- **Known Team**: You have a specific set of agents to coordinate
- **Structured Workflows**: Clear steps and task sequences
- **Active Coordination**: Need real-time task management
- **Decision Making**: Require consensus or voting mechanisms
- **Communication**: Need to broadcast updates to working teams

### Example Use Cases
- Coordinating a product review analysis with specific agents
- Managing a data pipeline with sequential processing steps
- Running a collaborative research project with defined phases
- Orchestrating a customer support workflow

## AgentPoolManagerNode: The Talent Pool Manager

### Purpose
The AgentPoolManagerNode maintains a dynamic registry of available agents, tracking their capabilities, performance, and availability for team formation.

### Key Features
- **Agent Registry**: Maintains comprehensive agent profiles
- **Capability Indexing**: Fast agent discovery by skills
- **Performance Tracking**: Long-term metrics and specializations
- **Dynamic Availability**: Real-time status management
- **Team Formation Support**: Enables self-organizing teams

### Core Actions
```python
# Register agents to the pool
pool_manager.run(
    action="register",
    agent_id="ml_expert_007",
    capabilities=["machine_learning", "deep_learning", "pytorch"],
    metadata={
        "experience_years": 5,
        "specialization": "computer_vision"
    }
)

# Find agents by capability
pool_manager.run(
    action="find_by_capability",
    required_capabilities=["machine_learning", "data_analysis"],
    min_performance=0.8  # Only high performers
)

# Update agent status
pool_manager.run(
    action="update_status",
    agent_id="ml_expert_007",
    status="busy"
)

# Track performance metrics
pool_manager.run(
    action="get_metrics",
    agent_id="ml_expert_007"
)

```

### When to Use AgentPoolManagerNode
- **Large Agent Ecosystem**: Managing many agents with diverse skills
- **Dynamic Team Formation**: Need to discover and assemble teams
- **Performance Tracking**: Long-term agent evaluation
- **Resource Management**: Tracking agent availability
- **Scalable Systems**: Growing or shrinking agent pools

### Example Use Cases
- Enterprise AI agent marketplace
- Dynamic consultant allocation system
- Self-organizing research teams
- Elastic compute agent pools
- Skill-based gig economy platforms

## Key Differences

| Aspect | A2ACoordinatorNode | AgentPoolManagerNode |
|--------|-------------------|---------------------|
| **Focus** | Task coordination | Agent management |
| **Scope** | Single workflow | Entire agent ecosystem |
| **Control** | Direct orchestration | Registry and discovery |
| **Team Size** | Small, known teams | Large, dynamic pools |
| **Persistence** | Workflow lifetime | Long-term tracking |
| **Formation** | Manual assignment | Self-organization support |
| **Metrics** | Basic task success | Comprehensive performance |
| **Use Pattern** | Project manager | HR department |

## Integration Pattern: Using Both Together

The most powerful multi-agent systems combine both approaches:

```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Step 1: Maintain the talent pool
pool_manager.run(
    action="register",
    agent_id="expert_001",
    capabilities=["nlp", "sentiment_analysis"]
)

# Step 2: Analyze problem requirements
problem_analysis = problem_analyzer.run(
    problem_description="Analyze customer sentiment across channels"
)

# Step 3: Find suitable agents from pool
available_agents = pool_manager.run(
    action="find_by_capability",
    required_capabilities=problem_analysis["required_capabilities"],
    min_performance=0.75
)

# Step 4: Form optimal team
team = team_formation.run(
    problem_analysis=problem_analysis,
    available_agents=available_agents["agents"],
    formation_strategy="capability_matching"
)

# Step 5: Register team with coordinator
coordinator = A2ACoordinatorNode()
for agent in team["selected_agents"]:
    coordinator.run(action="register", agent_info=agent)

# Step 6: Coordinate the actual work
coordinator.run(
    action="delegate",
    task={
        "name": "Sentiment Analysis Phase 1",
        "required_skills": ["sentiment_analysis"]
    }
)

# Step 7: Update pool metrics after completion
for agent in team["selected_agents"]:
    pool_manager.run(
        action="update_status",
        agent_id=agent["id"],
        status="available",
        performance_update={
            "task_completed": True,
            "success_score": 0.95
        }
    )

```

## Decision Tree: Which Pattern to Use?

```
Do you have a specific workflow to execute?
├─ YES → Do you know which agents to use?
│   ├─ YES → Use A2ACoordinatorNode only
│   └─ NO → Do you have a large agent pool?
│       ├─ YES → Use AgentPoolManagerNode + A2ACoordinatorNode
│       └─ NO → Build pool first with AgentPoolManagerNode
│
└─ NO → Are you building an agent management system?
    ├─ YES → Use AgentPoolManagerNode
    └─ NO → Do agents need to self-organize?
        ├─ YES → Use AgentPoolManagerNode + TeamFormationNode
        └─ NO → Start with A2ACoordinatorNode for simple coordination
```

## Best Practices

### For A2ACoordinatorNode:
1. **Register all agents** before starting coordination
2. **Use appropriate delegation strategies** (best_match for skills, round_robin for load balancing)
3. **Broadcast important updates** to keep agents synchronized
4. **Build consensus** for critical decisions
5. **Track task completion** to update agent status

### For AgentPoolManagerNode:
1. **Maintain accurate capabilities** for each agent
2. **Update performance metrics** after each task
3. **Monitor agent availability** to prevent overload
4. **Use capability indexing** for efficient searches
5. **Prune inactive agents** periodically

### For Hybrid Systems:
1. **Separate concerns**: Pool for management, Coordinator for execution
2. **Maintain consistency**: Sync status between systems
3. **Track metrics**: Update pool performance from coordinator results
4. **Plan for scale**: Design for growing agent populations
5. **Enable emergence**: Let teams self-organize when appropriate

## Example Scenarios

### Scenario 1: Fixed Team Project
**Use A2ACoordinatorNode only**
```python
# You have 3 analysts working on monthly reports
# Register them once, coordinate their work
coordinator.run(action="register", agent_info=analyst_1)
coordinator.run(action="register", agent_info=analyst_2)
coordinator.run(action="register", agent_info=analyst_3)
# Delegate report sections, broadcast deadlines, build consensus on findings

```

### Scenario 2: Dynamic Research Platform
**Use AgentPoolManagerNode + TeamFormationNode**
```python
# Researchers join/leave dynamically
# Form teams based on research topics
pool.run(action="register", agent_id="quantum_researcher_42", capabilities=["quantum", "physics"])
# When new research project arrives, find and form optimal team
team = formation.run(problem_analysis={"required": ["quantum", "ml"]})

```

### Scenario 3: Enterprise AI Operations
**Use Full Stack: Pool + Coordinator + TeamFormation**
```python
# Large organization with 100+ AI agents
# Different projects need different teams
# Track long-term performance and specializations
# Coordinate specific projects while maintaining the talent pool

```

## Conclusion

The choice between A2ACoordinatorNode and AgentPoolManagerNode depends on your specific needs:

- **Use A2ACoordinatorNode** when you need to coordinate known agents on specific tasks
- **Use AgentPoolManagerNode** when you need to manage a dynamic pool of agents
- **Use both** when you need sophisticated multi-agent systems with both management and coordination

Remember: these patterns are complementary, not competing. The most powerful multi-agent systems leverage both approaches to create adaptive, scalable, and efficient agent ecosystems.
