"""
Coordinated A2A Example - Multiple Agents with Task Delegation

This example demonstrates coordinated multi-agent collaboration where:
1. A coordinator delegates tasks to specialized agents
2. Agents share findings through a memory pool
3. Consensus is reached on conclusions
"""

from kailash import Workflow
from kailash.nodes.ai import A2AAgentNode, A2ACoordinatorNode, SharedMemoryPoolNode
from kailash.runtime.local import LocalRuntime


def create_coordinated_workflow():
    """Create a coordinated multi-agent research workflow."""
    workflow = Workflow(
        workflow_id="coordinated_a2a_example",
        name="Coordinated A2A Example",
        description="Multiple agents with task delegation and consensus",
    )

    # Shared infrastructure
    workflow.add_node("memory_pool", SharedMemoryPoolNode())

    workflow.add_node("coordinator", A2ACoordinatorNode())

    # Data source - use a simple node to provide data
    from kailash.nodes.base import Node, NodeParameter, register_node

    @register_node()
    class DataProviderNode(Node):
        """Simple node to provide static data."""

        def get_parameters(self):
            return {
                "data": NodeParameter(
                    name="data",
                    type=str,
                    required=False,
                    default="""Q3 2024 Financial Report Summary:
- Revenue increased by 25% YoY to $450M
- Operating costs reduced by 10% through automation
- Customer acquisition cost decreased by 15%
- Market share grew from 12% to 15%
- Employee satisfaction score: 8.5/10
- Product defect rate reduced by 40%""",
                )
            }

        def run(self, **kwargs):
            return {"content": kwargs.get("data")}

    workflow.add_node("data_source", DataProviderNode())

    # Specialized agents
    workflow.add_node(
        "financial_analyst",
        A2AAgentNode(),
        config={
            "agent_id": "fin_analyst_001",
            "agent_role": "financial_analyst",
            "provider": "mock",
            "model": "mock-model",
            "system_prompt": "You are a financial analyst. Focus on revenue, costs, and financial metrics.",
            "attention_filter": {
                "tags": ["finance", "revenue", "costs", "metrics"],
                "importance_threshold": 0.6,
                "window_size": 10,
            },
        },
    )

    workflow.add_node(
        "market_analyst",
        A2AAgentNode(),
        config={
            "agent_id": "mkt_analyst_001",
            "agent_role": "market_analyst",
            "provider": "mock",
            "model": "mock-model",
            "system_prompt": "You are a market analyst. Focus on market share, competition, and growth.",
            "attention_filter": {
                "tags": ["market", "competition", "growth", "strategy"],
                "importance_threshold": 0.6,
                "window_size": 10,
            },
        },
    )

    workflow.add_node(
        "operations_analyst",
        A2AAgentNode(),
        config={
            "agent_id": "ops_analyst_001",
            "agent_role": "operations_analyst",
            "provider": "mock",
            "model": "mock-model",
            "system_prompt": "You are an operations analyst. Focus on efficiency, quality, and employee metrics.",
            "attention_filter": {
                "tags": ["operations", "efficiency", "quality", "employees"],
                "importance_threshold": 0.5,
                "window_size": 10,
            },
        },
    )

    # Connect components
    # Data flows to all analysts
    workflow.connect("data_source", "financial_analyst")
    workflow.connect("data_source", "market_analyst")
    workflow.connect("data_source", "operations_analyst")

    # All agents connect to shared memory
    for agent_id in ["financial_analyst", "market_analyst", "operations_analyst"]:
        workflow.connect(agent_id, "memory_pool")

    # All agents register with coordinator
    for agent_id in ["financial_analyst", "market_analyst", "operations_analyst"]:
        workflow.connect(agent_id, "coordinator")

    return workflow


def main():
    """Run the coordinated A2A example."""
    print("=== Coordinated Multi-Agent Analysis Example ===\n")

    workflow = create_coordinated_workflow()
    runtime = LocalRuntime()

    # Step 1: Register agents with coordinator
    print("Step 1: Registering agents with coordinator...")

    coordinator = workflow._node_instances["coordinator"]
    agents_info = [
        {
            "id": "fin_analyst_001",
            "skills": ["financial_analysis", "revenue_analysis", "cost_analysis"],
            "role": "financial_analyst",
        },
        {
            "id": "mkt_analyst_001",
            "skills": ["market_analysis", "competitive_analysis", "growth_strategy"],
            "role": "market_analyst",
        },
        {
            "id": "ops_analyst_001",
            "skills": ["operations_analysis", "efficiency_metrics", "quality_control"],
            "role": "operations_analyst",
        },
    ]

    for agent_info in agents_info:
        result = coordinator.execute(action="register", agent_info=agent_info)
        print(f"Registered {agent_info['id']}: {result['success']}")

    print("\n" + "-" * 50 + "\n")

    # Step 2: Coordinator delegates analysis tasks
    print("Step 2: Delegating analysis tasks...")

    tasks = [
        {
            "name": "Financial Health Analysis",
            "required_skills": ["financial_analysis"],
            "description": "Analyze revenue growth and cost reduction",
        },
        {
            "name": "Market Position Analysis",
            "required_skills": ["market_analysis"],
            "description": "Evaluate market share growth and competitive position",
        },
        {
            "name": "Operational Excellence Review",
            "required_skills": ["operations_analysis"],
            "description": "Assess operational efficiency and quality improvements",
        },
    ]

    delegations = []
    for task in tasks:
        result = coordinator.execute(
            action="delegate", task=task, coordination_strategy="best_match"
        )
        if result["success"]:
            delegations.append(result)
            print(f"Task '{task['name']}' delegated to {result['delegated_to']}")

    print("\n" + "-" * 50 + "\n")

    # Step 3: Execute analysis with all agents
    print("Step 3: Agents analyzing data...")

    memory_pool = workflow._node_instances["memory_pool"]

    # Financial analyst
    result, _ = runtime.execute(
        workflow,
        parameters={
            "financial_analyst": {
                "messages": [
                    {
                        "role": "user",
                        "content": "Analyze the financial metrics in the Q3 report",
                    }
                ],
                "memory_pool": memory_pool,
                "provider": "mock",
                "model": "mock-model",
            }
        },
    )
    print("Financial Analyst completed analysis")

    # Market analyst
    result, _ = runtime.execute(
        workflow,
        parameters={
            "market_analyst": {
                "messages": [
                    {
                        "role": "user",
                        "content": "Analyze the market position from the Q3 report",
                    }
                ],
                "memory_pool": memory_pool,
                "provider": "mock",
                "model": "mock-model",
            }
        },
    )
    print("Market Analyst completed analysis")

    # Operations analyst
    result, _ = runtime.execute(
        workflow,
        parameters={
            "operations_analyst": {
                "messages": [
                    {
                        "role": "user",
                        "content": "Analyze operational metrics from the Q3 report",
                    }
                ],
                "memory_pool": memory_pool,
                "provider": "mock",
                "model": "mock-model",
            }
        },
    )
    print("Operations Analyst completed analysis")

    print("\n" + "-" * 50 + "\n")

    # Step 4: Broadcast request for consensus
    print("Step 4: Broadcasting consensus request...")

    broadcast_result = coordinator.execute(
        action="broadcast",
        message={
            "content": "All analysts please review shared findings and prepare for consensus on Q3 performance",
            "target_roles": [
                "financial_analyst",
                "market_analyst",
                "operations_analyst",
            ],
            "priority": "high",
        },
    )

    print(f"Broadcast sent to: {broadcast_result['recipients']}")

    print("\n" + "-" * 50 + "\n")

    # Step 5: Build consensus
    print("Step 5: Building consensus on Q3 performance...")

    coordinator.execute(
        action="consensus",
        consensus_proposal={
            "session_id": "q3_performance_review",
            "proposal": "Q3 shows strong overall performance with revenue growth, cost reduction, and market share gains",
            "require_unanimous": False,
        },
    )

    # Simulate votes from agents
    for agent_id in ["fin_analyst_001", "mkt_analyst_001", "ops_analyst_001"]:
        coordinator.execute(
            action="consensus",
            consensus_proposal={"session_id": "q3_performance_review"},
            agent_id=agent_id,
            vote=True,  # All agree based on positive metrics
        )

    print("\n" + "-" * 50 + "\n")

    # Step 6: Review shared memory
    print("Step 6: Reviewing collective insights...")

    collective_insights = memory_pool.execute(
        action="read",
        agent_id="summary_agent",
        attention_filter={"importance_threshold": 0.7, "window_size": 20},
    )

    print(
        f"\nHigh-importance insights from all agents ({collective_insights['total_available']} total):"
    )
    for i, memory in enumerate(collective_insights["memories"][:5], 1):
        print(f"\n{i}. {memory['agent_id']} ({memory.get('segment', 'general')}):")
        print(f"   {memory['content']}")
        print(f"   Importance: {memory['importance']:.1f}")

    # Final summary
    print("\n" + "=" * 50)
    print("ANALYSIS COMPLETE")
    print("=" * 50)
    print(f"Agents registered: {len(coordinator.registered_agents)}")
    print(f"Tasks delegated: {len(delegations)}")
    print("Consensus reached: Yes")
    print(f"Total insights generated: {collective_insights['total_available']}")


if __name__ == "__main__":
    main()
