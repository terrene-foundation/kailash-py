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
workflow = WorkflowBuilder()
workflow.add_node("A2ACoordinatorNode", "coordinator", {
    "action": "register",
    "agent_info": {
        "id": "analyst_001",
        "skills": ["data_analysis", "reporting"],
        "role": "analyst"
    }
})

runtime = LocalRuntime()
result, run_id = runtime.execute(workflow.build())

# Delegate tasks with strategies
workflow = WorkflowBuilder()
workflow.add_node("A2ACoordinatorNode", "coordinator", {
    "action": "delegate",
    "task": {
        "name": "Analyze Q3 Data",
        "required_skills": ["data_analysis"],
        "priority": "high"
    },
    "coordination_strategy": "best_match"  # or "round_robin", "auction"
})

result, run_id = runtime.execute(workflow.build())

# Broadcast messages to teams
workflow = WorkflowBuilder()
workflow.add_node("A2ACoordinatorNode", "coordinator", {
    "action": "broadcast",
    "message": {
        "content": "Phase 1 complete, begin synthesis",
        "target_roles": ["analyst", "synthesizer"],
        "priority": "high"
    }
})

result, run_id = runtime.execute(workflow.build())

# Build consensus on decisions
workflow = WorkflowBuilder()
workflow.add_node("A2ACoordinatorNode", "coordinator", {
    "action": "consensus",
    "consensus_proposal": {
        "proposal": "Accept analysis results",
        "require_unanimous": False
    }
})

result, run_id = runtime.execute(workflow.build())

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
workflow = WorkflowBuilder()
workflow.add_node("AgentPoolManagerNode", "pool_manager", {
    "action": "register",
    "agent_id": "ml_expert_007",
    "capabilities": ["machine_learning", "deep_learning", "pytorch"],
    "metadata": {
        "experience_years": 5,
        "specialization": "computer_vision"
    }
})

runtime = LocalRuntime()
result, run_id = runtime.execute(workflow.build())

# Find agents by capability
workflow = WorkflowBuilder()
workflow.add_node("AgentPoolManagerNode", "pool_manager", {
    "action": "find_by_capability",
    "required_capabilities": ["machine_learning", "data_analysis"],
    "min_performance": 0.8  # Only high performers
})

result, run_id = runtime.execute(workflow.build())

# Update agent status
workflow = WorkflowBuilder()
workflow.add_node("AgentPoolManagerNode", "pool_manager", {
    "action": "update_status",
    "agent_id": "ml_expert_007",
    "status": "busy"
})

result, run_id = runtime.execute(workflow.build())

# Track performance metrics
workflow = WorkflowBuilder()
workflow.add_node("AgentPoolManagerNode", "pool_manager", {
    "action": "get_metrics",
    "agent_id": "ml_expert_007"
})

result, run_id = runtime.execute(workflow.build())

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
# Step 1: Maintain the talent pool
workflow = WorkflowBuilder()
workflow.add_node("AgentPoolManagerNode", "pool_manager", {
    "action": "register",
    "agent_id": "expert_001",
    "capabilities": ["nlp", "sentiment_analysis"]
})

runtime = LocalRuntime()
result, run_id = runtime.execute(workflow.build())

# Step 2: Analyze problem requirements
workflow = WorkflowBuilder()
workflow.add_node("ProblemAnalyzerNode", "problem_analyzer", {
    "problem_description": "Analyze customer sentiment across channels"
})

problem_analysis, run_id = runtime.execute(workflow.build())

# Step 3: Find suitable agents from pool
workflow = WorkflowBuilder()
workflow.add_node("AgentPoolManagerNode", "pool_manager", {
    "action": "find_by_capability",
    "required_capabilities": ["nlp", "sentiment_analysis"],  # Simulated from problem analysis
    "min_performance": 0.75
})

available_agents, run_id = runtime.execute(workflow.build())

# Step 4: Form optimal team
workflow = WorkflowBuilder()
workflow.add_node("TeamFormationNode", "team_formation", {
    "problem_analysis": {"required_capabilities": ["nlp", "sentiment_analysis"]},
    "available_agents": [{"id": "expert_001", "capabilities": ["nlp", "sentiment_analysis"]}],  # Simulated
    "formation_strategy": "capability_matching"
})

team, run_id = runtime.execute(workflow.build())

# Step 5: Register team with coordinator
workflow = WorkflowBuilder()
# In practice, you would loop through team members
workflow.add_node("A2ACoordinatorNode", "coordinator", {
    "action": "register",
    "agent_info": {"id": "expert_001", "capabilities": ["nlp", "sentiment_analysis"]}
})

result, run_id = runtime.execute(workflow.build())

# Step 6: Coordinate the actual work
workflow = WorkflowBuilder()
workflow.add_node("A2ACoordinatorNode", "coordinator", {
    "action": "delegate",
    "task": {
        "name": "Sentiment Analysis Phase 1",
        "required_skills": ["sentiment_analysis"]
    }
})

result, run_id = runtime.execute(workflow.build())

# Step 7: Update pool metrics after completion
workflow = WorkflowBuilder()
workflow.add_node("AgentPoolManagerNode", "pool_manager", {
    "action": "update_status",
    "agent_id": "expert_001",
    "status": "available",
    "performance_update": {
        "task_completed": True,
        "success_score": 0.95
    }
})

result, run_id = runtime.execute(workflow.build())

```

## Complete Demo: Agent Coordination in Action

Here's a comprehensive example demonstrating both coordination patterns:

```python
"""
A2A Communication Demo - Agent Coordination Patterns

This example demonstrates both A2ACoordinatorNode and SharedMemoryPoolNode
for effective multi-agent coordination.
"""

from kailash.nodes.ai import A2ACoordinatorNode, SharedMemoryPoolNode


def demo_shared_memory():
    """Demonstrate shared memory pool functionality."""
    print("=== Shared Memory Pool Demo ===\n")

    # Create memory pool
    memory = SharedMemoryPoolNode()

    # Agent 1 writes a discovery
    print("1. Agent writes discovery to shared memory:")
    result = memory.execute(
        action="write",
        agent_id="researcher_001",
        content="Found 30% increase in customer satisfaction after UI redesign",
        tags=["research", "ui", "customer_satisfaction"],
        importance=0.9,
        segment="findings"
    )
    print(f"   Memory ID: {result['memory_id']}")
    print(f"   Stored in segment: {result['segment']}")

    # Agent 2 writes another finding
    print("\n2. Another agent writes finding:")
    memory.execute(
        action="write",
        agent_id="analyst_001",
        content="Minor bug in payment processing",
        tags=["bug", "payment"],
        importance=0.3,
        segment="issues"
    )

    # Agent 3 reads with attention filter
    print("\n3. Third agent reads with attention filter (high importance only):")
    filtered_result = memory.execute(
        action="read",
        agent_id="manager_001",
        attention_filter={
            "importance_threshold": 0.7,
            "tags": ["research", "customer_satisfaction"],
            "window_size": 5
        }
    )

    print(f"   Found {len(filtered_result['memories'])} relevant memories:")
    for mem in filtered_result['memories']:
        print(f"   - {mem['content'][:50]}... (importance: {mem['importance']})")

    # Semantic query
    print("\n4. Semantic query across all memories:")
    query_result = memory.execute(
        action="query",
        agent_id="searcher_001",
        query="customer satisfaction"
    )

    print(f"   Found {query_result['total_matches']} matches")
    if query_result['results']:
        print(f"   Best match: {query_result['results'][0]['content']}")


def demo_agent_coordination():
    """Demonstrate agent coordination and task delegation."""
    print("\n\n=== Agent Coordination Demo ===\n")

    # Create coordinator
    coordinator = A2ACoordinatorNode()

    # Register agents
    print("1. Registering specialized agents:")
    agents = [
        {
            "id": "data_analyst_001",
            "skills": ["data_analysis", "statistics", "visualization"],
            "role": "data_analyst"
        },
        {
            "id": "ml_engineer_001",
            "skills": ["machine_learning", "model_training", "optimization"],
            "role": "ml_engineer"
        },
        {
            "id": "researcher_001",
            "skills": ["research", "literature_review", "hypothesis_testing"],
            "role": "researcher"
        }
    ]

    for agent in agents:
        result = coordinator.execute(
            action="register",
            agent_info=agent
        )
        print(f"   Registered: {agent['id']} as {agent['role']}")

    # Delegate task
    print("\n2. Delegating analysis task:")
    task_result = coordinator.execute(
        action="delegate",
        task={
            "name": "Analyze customer behavior patterns",
            "required_skills": ["data_analysis", "statistics"],
            "priority": "high",
            "deadline": "2024-12-10"
        },
        coordination_strategy="best_match"
    )

    print(f"   Task delegated to: {task_result['assigned_agent']['id']}")
    print(f"   Match score: {task_result['delegation']['score']:.2f}")

    # Broadcast message
    print("\n3. Broadcasting update to all agents:")
    broadcast_result = coordinator.execute(
        action="broadcast",
        message={
            "content": "New dataset available for analysis",
            "priority": "medium",
            "target_roles": ["data_analyst", "ml_engineer"]
        }
    )

    print(f"   Message delivered to {broadcast_result['delivered_count']} agents")

    # Build consensus
    print("\n4. Building consensus on approach:")
    consensus_result = coordinator.execute(
        action="consensus",
        consensus_proposal={
            "proposal": "Use ensemble methods for prediction",
            "proposer": "ml_engineer_001",
            "require_unanimous": False
        }
    )

    print(f"   Consensus reached: {consensus_result['consensus']['approved']}")
    print(f"   Approval rate: {consensus_result['consensus']['approval_rate']:.1%}")


def demo_collaborative_workflow():
    """Demonstrate a complete collaborative workflow."""
    print("\n\n=== Collaborative Workflow Demo ===\n")

    # Create both nodes
    coordinator = A2ACoordinatorNode()
    memory = SharedMemoryPoolNode()

    print("Setting up collaborative analysis workflow...")

    # Register agents with coordinator
    agents = ["analyst_001", "researcher_001", "synthesizer_001"]
    for agent_id in agents:
        coordinator.execute(
            action="register",
            agent_info={
                "id": agent_id,
                "role": agent_id.split("_")[0]
            }
        )

    # Simulate collaborative work
    print("\n1. Analyst discovers pattern:")
    memory.execute(
        action="write",
        agent_id="analyst_001",
        content="User engagement peaks at 2pm-4pm on weekdays",
        tags=["pattern", "engagement", "timing"],
        importance=0.8
    )

    print("2. Researcher adds context:")
    memory.execute(
        action="write",
        agent_id="researcher_001",
        content="Studies show post-lunch cognitive refresh affects online behavior",
        tags=["research", "behavior", "timing"],
        importance=0.7
    )

    print("3. Coordinator broadcasts synthesis request:")
    coordinator.execute(
        action="broadcast",
        message={
            "content": "Please synthesize findings on engagement timing",
            "target_roles": ["synthesizer"]
        }
    )

    print("4. Synthesizer queries relevant memories:")
    synthesis_data = memory.execute(
        action="query",
        agent_id="synthesizer_001",
        query="engagement timing patterns"
    )

    print(f"\nCollaborative workflow complete!")
    print(f"Total memories created: {synthesis_data['total_matches']}")
    print(f"Agents coordinated: {len(agents)}")


if __name__ == "__main__":
    # Run all demos
    demo_shared_memory()
    demo_agent_coordination()
    demo_collaborative_workflow()

    print("\n" + "="*60)
    print("Demo completed successfully!")
    print("Key takeaways:")
    print("- SharedMemoryPoolNode enables persistent knowledge sharing")
    print("- A2ACoordinatorNode manages active task coordination")
    print("- Combined usage creates powerful collaborative systems")
```

This demo showcases:
- **Shared Memory Operations**: Write, read with filters, and semantic queries
- **Agent Coordination**: Registration, task delegation, broadcasting, and consensus
- **Collaborative Workflows**: How both nodes work together for complex tasks
- **Real-world Patterns**: Practical examples of multi-agent collaboration

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
workflow = WorkflowBuilder()
workflow.add_node("A2ACoordinatorNode", "register_1", {
    "action": "register",
    "agent_info": {"id": "analyst_1", "role": "analyst"}
})
workflow.add_node("A2ACoordinatorNode", "register_2", {
    "action": "register",
    "agent_info": {"id": "analyst_2", "role": "analyst"}
})
workflow.add_node("A2ACoordinatorNode", "register_3", {
    "action": "register",
    "agent_info": {"id": "analyst_3", "role": "analyst"}
})

runtime = LocalRuntime()
result, run_id = runtime.execute(workflow.build())
# Delegate report sections, broadcast deadlines, build consensus on findings

```

### Scenario 2: Dynamic Research Platform
**Use AgentPoolManagerNode + TeamFormationNode**
```python
# Researchers join/leave dynamically
# Form teams based on research topics
workflow = WorkflowBuilder()
workflow.add_node("AgentPoolManagerNode", "pool", {
    "action": "register",
    "agent_id": "quantum_researcher_42",
    "capabilities": ["quantum", "physics"]
})

runtime = LocalRuntime()
result, run_id = runtime.execute(workflow.build())

# When new research project arrives, find and form optimal team
workflow = WorkflowBuilder()
workflow.add_node("TeamFormationNode", "formation", {
    "problem_analysis": {"required": ["quantum", "ml"]}
})

team, run_id = runtime.execute(workflow.build())

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
