"""
Simple A2A Communication Example - Two Agents Sharing Information

This example demonstrates the fundamental concepts of agent-to-agent (A2A) communication
in the Kailash SDK, showing how agents can share discoveries and build upon each other's
work through a shared memory pool with selective attention mechanisms.

Purpose:
    Provides a minimal working example of A2A communication suitable for learning
    the basic patterns before moving to more complex multi-agent scenarios.

Key Concepts Demonstrated:
    1. Creating and configuring a SharedMemoryPoolNode
    2. Setting up A2AAgentNode instances with different roles
    3. Attention filtering to focus on relevant information
    4. Automatic insight extraction and sharing
    5. Building knowledge incrementally across agents

Prerequisites:
    - Basic understanding of Kailash workflow concepts
    - Familiarity with node-based architectures
    - No external dependencies (uses mock provider)

Usage:
    Run this example directly:
        python a2a_simple_example.py

    Or integrate into your workflow:
        from a2a_simple_example import create_simple_a2a_workflow
        workflow = create_simple_a2a_workflow()

Expected Output:
    The example will show:
    - Research agent discovering patterns
    - Analysis agent building on those discoveries
    - Memory pool contents showing shared insights
    - Attention filtering in action

Next Steps:
    After understanding this example, explore:
    - a2a_complex_research.py for multi-stage research
    - a2a_coordinated_example.py for task delegation
    - a2a_ollama_example.py for real LLM integration
"""

from kailash import Workflow
from kailash.nodes.ai import A2AAgentNode, SharedMemoryPoolNode
from kailash.runtime.local import LocalRuntime


def create_simple_a2a_workflow():
    """
    Create a simple two-agent workflow with shared memory.

    This function sets up a basic A2A workflow with two agents (researcher and analyst)
    that communicate through a shared memory pool. The agents use attention filtering
    to focus on relevant information and automatically share insights.

    Returns:
        Workflow: Configured workflow ready for execution

    Workflow Structure:
        - SharedMemoryPoolNode: Central memory for agent communication
        - Research Agent: Discovers patterns and shares findings
        - Analysis Agent: Analyzes research findings and provides insights

    The agents are configured with complementary attention filters to ensure
    relevant information flows between them while avoiding information overload.

    Example:
        >>> workflow = create_simple_a2a_workflow()
        >>> runtime = LocalRuntime()
        >>> results, _ = runtime.execute(workflow, parameters={
        ...     "research_agent": {
        ...         "messages": [{"role": "user", "content": "Find patterns in sales data"}]
        ...     }
        ... })
    """
    workflow = Workflow(
        workflow_id="simple_a2a_example",
        name="Simple A2A Example",
        description="Two agents sharing information through a memory pool",
    )

    # Create shared memory pool
    workflow.add_node("shared_memory", SharedMemoryPoolNode())

    # Create research agent
    workflow.add_node(
        "research_agent",
        A2AAgentNode(),
        config={
            "agent_id": "researcher_001",
            "agent_role": "researcher",
            "provider": "mock",  # Using mock for example
            "model": "mock-model",
            "system_prompt": "You are a research agent. Find interesting patterns in data.",
            "attention_filter": {
                "tags": ["data", "findings"],
                "importance_threshold": 0.5,
                "window_size": 10,
            },
        },
    )

    # Create analysis agent
    workflow.add_node(
        "analysis_agent",
        A2AAgentNode(),
        config={
            "agent_id": "analyst_001",
            "agent_role": "analyst",
            "provider": "mock",
            "model": "mock-model",
            "system_prompt": "You are an analysis agent. Analyze findings from research.",
            "attention_filter": {
                "tags": ["research", "findings", "pattern"],
                "importance_threshold": 0.6,
                "window_size": 5,
            },
        },
    )

    # Connect agents to shared memory
    workflow.connect("research_agent", "shared_memory")
    workflow.connect("analysis_agent", "shared_memory")

    return workflow


def main():
    """
    Run the simple A2A example.

    This function demonstrates the complete A2A communication flow:
    1. Research agent discovers patterns and shares insights
    2. Analysis agent reads relevant memories and builds on them
    3. Memory pool contents are examined to show information flow

    The example uses mock LLM providers for reproducibility but the
    same patterns work with real LLM providers like OpenAI or Ollama.

    Output includes:
        - Agent responses showing discoveries and analysis
        - Metadata about shared context usage
        - Complete memory pool contents for inspection
    """
    print("=== Simple A2A Communication Example ===\n")

    # Create workflow
    workflow = create_simple_a2a_workflow()
    runtime = LocalRuntime()

    # Step 1: Research agent makes a discovery
    print("Step 1: Research agent analyzing data...")

    # First, let's write some initial data to the memory pool
    memory_pool = workflow._node_instances["shared_memory"]

    # Research agent discovers something
    research_params = {
        "agent_id": "researcher_001",
        "messages": [
            {
                "role": "user",
                "content": "I found that customer purchases increase by 40% during holiday seasons.",
            }
        ],
        "memory_pool": memory_pool,
        "provider": "mock",
        "model": "mock-model",
    }

    result1, run_id1 = runtime.execute(
        workflow, parameters={"research_agent": research_params}
    )

    if result1.get("research_agent", {}).get("success"):
        print(
            f"Research Agent Response: {result1['research_agent']['response']['content']}"
        )
        print(
            f"Shared context used: {result1['research_agent']['a2a_metadata']['shared_context_used']}"
        )
        print(
            f"Insights generated: {result1['research_agent']['a2a_metadata']['insights_generated']}"
        )

    print("\n" + "-" * 50 + "\n")

    # Step 2: Analysis agent reads from shared memory and analyzes
    print("Step 2: Analysis agent reading shared discoveries...")

    analysis_params = {
        "agent_id": "analyst_001",
        "messages": [
            {
                "role": "user",
                "content": "What patterns can you identify from the research findings?",
            }
        ],
        "memory_pool": memory_pool,
        "provider": "mock",
        "model": "mock-model",
    }

    result2, run_id2 = runtime.execute(
        workflow, parameters={"analysis_agent": analysis_params}
    )

    if result2.get("analysis_agent", {}).get("success"):
        print(
            f"Analysis Agent Response: {result2['analysis_agent']['response']['content']}"
        )
        print(
            f"Shared context used: {result2['analysis_agent']['a2a_metadata']['shared_context_used']}"
        )
        print(
            f"Insights generated: {result2['analysis_agent']['a2a_metadata']['insights_generated']}"
        )

    print("\n" + "-" * 50 + "\n")

    # Step 3: Check shared memory contents
    print("Step 3: Examining shared memory pool...")
    memory_state = memory_pool.execute(
        action="read", agent_id="observer", attention_filter={}  # Read all memories
    )

    if memory_state["success"]:
        print(f"Total memories in pool: {memory_state['total_available']}")
        print("\nMemory contents:")
        for i, memory in enumerate(memory_state["memories"], 1):
            print(f"\n{i}. From {memory['agent_id']} ({memory['agent_id']}):")
            print(f"   Content: {memory['content']}")
            print(f"   Tags: {memory['tags']}")
            print(f"   Importance: {memory['importance']}")


if __name__ == "__main__":
    main()
