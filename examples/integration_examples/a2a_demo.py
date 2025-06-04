"""
A2A Communication Demo - Showcasing Core Features

This demo illustrates:
1. Shared memory pool for inter-agent communication
2. Selective attention mechanisms
3. Agent coordination and task delegation
4. Memory relevance scoring
"""

from kailash.nodes.ai import A2AAgentNode, A2ACoordinatorNode, SharedMemoryPoolNode


def demo_shared_memory():
    """Demonstrate shared memory pool functionality."""
    print("=== Shared Memory Pool Demo ===\n")

    # Create memory pool
    memory = SharedMemoryPoolNode()

    # Agent 1 writes a discovery
    print("1. Agent writes discovery to shared memory:")
    result = memory.run(
        action="write",
        agent_id="researcher_001",
        content="Found 30% increase in customer satisfaction after UI redesign",
        tags=["research", "ui", "customer_satisfaction"],
        importance=0.9,
        segment="findings",
    )
    print(f"   Memory ID: {result['memory_id']}")
    print(f"   Stored in segment: {result['segment']}")

    # Agent 2 writes another finding
    print("\n2. Another agent writes finding:")
    memory.run(
        action="write",
        agent_id="analyst_001",
        content="Minor bug in payment processing",
        tags=["bug", "payment"],
        importance=0.3,
        segment="issues",
    )

    # Agent 3 reads with attention filter
    print("\n3. Third agent reads with attention filter (high importance only):")
    filtered_result = memory.run(
        action="read",
        agent_id="manager_001",
        attention_filter={
            "importance_threshold": 0.7,
            "tags": ["research", "customer_satisfaction"],
            "window_size": 5,
        },
    )

    print(f"   Found {len(filtered_result['memories'])} relevant memories:")
    for mem in filtered_result["memories"]:
        print(f"   - {mem['content'][:50]}... (importance: {mem['importance']})")

    # Semantic query
    print("\n4. Semantic query across all memories:")
    query_result = memory.run(
        action="query", agent_id="searcher_001", query="customer satisfaction"
    )

    print(f"   Found {query_result['total_matches']} matches")
    if query_result["results"]:
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
            "role": "data_analyst",
        },
        {
            "id": "ml_engineer_001",
            "skills": ["machine_learning", "model_training", "optimization"],
            "role": "ml_engineer",
        },
        {
            "id": "researcher_001",
            "skills": ["research", "literature_review", "hypothesis_testing"],
            "role": "researcher",
        },
    ]

    for agent in agents:
        result = coordinator.run(action="register", agent_info=agent)
        print(f"   - {agent['id']}: {', '.join(agent['skills'])}")

    # Delegate tasks
    print("\n2. Delegating tasks based on required skills:")
    tasks = [
        {
            "name": "Analyze customer data patterns",
            "required_skills": ["data_analysis", "statistics"],
        },
        {
            "name": "Train predictive model",
            "required_skills": ["machine_learning", "model_training"],
        },
        {"name": "Research competitive solutions", "required_skills": ["research"]},
    ]

    for task in tasks:
        result = coordinator.run(
            action="delegate", task=task, coordination_strategy="best_match"
        )
        print(f"   - '{task['name']}' → {result['delegated_to']}")

    # Broadcast message
    print("\n3. Broadcasting message to relevant agents:")
    broadcast_result = coordinator.run(
        action="broadcast",
        message={
            "content": "New dataset available for analysis",
            "target_skills": ["data_analysis", "machine_learning"],
        },
    )
    print(f"   Message sent to: {', '.join(broadcast_result['recipients'])}")

    # Consensus building
    print("\n4. Building consensus on approach:")
    coordinator.run(
        action="consensus",
        consensus_proposal={
            "session_id": "approach_decision",
            "proposal": "Use ensemble methods for better prediction accuracy",
        },
    )

    # Simulate votes
    for agent_id in ["data_analyst_001", "ml_engineer_001"]:
        coordinator.run(
            action="consensus",
            consensus_proposal={"session_id": "approach_decision"},
            agent_id=agent_id,
            vote=True,
        )

    print("   Consensus reached: Yes (2/2 votes)")


def demo_attention_mechanism():
    """Demonstrate selective attention in memory retrieval."""
    print("\n\n=== Selective Attention Demo ===\n")

    memory = SharedMemoryPoolNode()

    # Populate memory with various items
    print("1. Populating memory with diverse content:")
    memories = [
        ("High priority security issue", ["security", "critical"], 0.95, "alerts"),
        (
            "Routine maintenance completed",
            ["maintenance", "routine"],
            0.3,
            "operations",
        ),
        (
            "Customer data breach detected",
            ["security", "data", "critical"],
            0.99,
            "alerts",
        ),
        ("Weekly report generated", ["report", "routine"], 0.2, "reports"),
        (
            "Performance optimization achieved 50% speedup",
            ["performance", "optimization"],
            0.8,
            "improvements",
        ),
        ("Minor UI bug fixed", ["bug", "ui"], 0.4, "fixes"),
    ]

    for content, tags, importance, segment in memories:
        memory.run(
            action="write",
            agent_id="system",
            content=content,
            tags=tags,
            importance=importance,
            segment=segment,
        )

    print(f"   Added {len(memories)} memories across different segments")

    # Different agents with different attention filters
    print("\n2. Different agents reading with their attention filters:")

    # Security-focused agent
    print("\n   Security Agent (high importance security issues only):")
    security_memories = memory.run(
        action="read",
        agent_id="security_agent",
        attention_filter={
            "tags": ["security", "critical"],
            "importance_threshold": 0.9,
            "segments": ["alerts"],
            "window_size": 10,
        },
    )

    for mem in security_memories["memories"]:
        print(f"     - {mem['content']} (relevance: {mem['relevance_score']:.2f})")

    # Operations agent
    print("\n   Operations Agent (all operational items):")
    ops_memories = memory.run(
        action="read",
        agent_id="ops_agent",
        attention_filter={
            "tags": ["maintenance", "performance", "optimization"],
            "importance_threshold": 0.0,
            "segments": ["operations", "improvements"],
            "window_size": 10,
        },
    )

    for mem in ops_memories["memories"]:
        print(f"     - {mem['content']} (importance: {mem['importance']})")

    # Executive agent
    print("\n   Executive Agent (only high-importance items):")
    exec_memories = memory.run(
        action="read",
        agent_id="exec_agent",
        attention_filter={
            "importance_threshold": 0.8,
            "window_size": 5,
            "recency_window": 3600,  # Last hour
        },
    )

    for mem in exec_memories["memories"]:
        print(f"     - {mem['content']} (importance: {mem['importance']})")


def demo_memory_insights():
    """Show how memories accumulate insights over time."""
    print("\n\n=== Memory Insights Accumulation Demo ===\n")

    memory = SharedMemoryPoolNode()

    # Simulate a research workflow
    print("1. Research workflow generating insights:")

    # Phase 1: Initial observation
    memory.run(
        action="write",
        agent_id="observer_001",
        content="User engagement drops 40% after 3pm",
        tags=["observation", "engagement", "time_pattern"],
        importance=0.7,
        segment="research",
    )
    print("   Observer: Noted engagement pattern")

    # Phase 2: Analysis
    memory.run(
        action="write",
        agent_id="analyst_001",
        content="3pm drop correlates with school pickup times - parents leaving work early",
        tags=["analysis", "engagement", "causation", "demographics"],
        importance=0.85,
        segment="analysis",
    )
    print("   Analyst: Identified probable cause")

    # Phase 3: Strategy
    memory.run(
        action="write",
        agent_id="strategist_001",
        content="Recommend scheduling important content before 3pm or after 6pm",
        tags=["strategy", "recommendation", "engagement", "scheduling"],
        importance=0.9,
        segment="recommendations",
    )
    print("   Strategist: Proposed optimization strategy")

    # Show how different agents can build on this
    print("\n2. Agents querying related insights:")

    # Marketing agent looks for engagement insights
    engagement_insights = memory.run(
        action="read",
        agent_id="marketing_001",
        attention_filter={
            "tags": ["engagement", "strategy"],
            "importance_threshold": 0.7,
            "window_size": 10,
        },
    )

    print(
        f"\n   Marketing Agent found {len(engagement_insights['memories'])} relevant insights:"
    )
    for i, mem in enumerate(engagement_insights["memories"], 1):
        print(f"   {i}. [{mem['agent_id']}] {mem['content']}")


def main():
    """Run all demos."""
    print("=" * 60)
    print("A2A COMMUNICATION SYSTEM DEMONSTRATION")
    print("=" * 60)

    # Run demos
    demo_shared_memory()
    demo_agent_coordination()
    demo_attention_mechanism()
    demo_memory_insights()

    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)
    print("\nKey Features Demonstrated:")
    print("✓ Shared memory pools with segmentation")
    print("✓ Selective attention mechanisms")
    print("✓ Agent coordination and task delegation")
    print("✓ Consensus building")
    print("✓ Memory relevance scoring")
    print("✓ Semantic querying")
    print("✓ Multi-agent insight accumulation")


if __name__ == "__main__":
    main()
