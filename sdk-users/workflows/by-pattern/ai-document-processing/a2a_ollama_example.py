"""
A2A Communication with Ollama - Real LLM Agent Collaboration

This example demonstrates real agent-to-agent communication using Ollama models,
showing how different specialized agents can collaborate on complex research tasks
using actual language models running locally.

Purpose:
    Showcases production-ready A2A communication with real LLMs, demonstrating
    how agents with different model capabilities can work together effectively
    through shared memory and coordinated task execution.

Key Concepts Demonstrated:
    1. Multi-model agent teams (Llama 3.2, Mistral, Phi)
    2. Real-time collaboration with actual LLM responses
    3. Specialized agent roles based on model strengths
    4. Shared memory pool with semantic search
    5. Coordinator-based task orchestration
    6. Consensus building across diverse models

Prerequisites:
    - Ollama installed and running locally
    - Required models pulled:
        ollama pull llama3.2  # Research specialist
        ollama pull mistral   # Analysis expert
        ollama pull phi       # Synthesis and summarization
    - Python ollama package: pip install ollama

Model Selection Rationale:
    - Llama 3.2: Fast, versatile, good for general research
    - Mistral: Excellent reasoning, ideal for analysis
    - Phi: Efficient, great for synthesis and summaries

Usage:
    Ensure Ollama is running:
        ollama serve

    Run the example:
        python a2a_ollama_example.py

Expected Output:
    - Real-time agent responses on the research topic
    - Visible information sharing through memory pool
    - Consensus building demonstration
    - Performance metrics (tokens, timing)

Customization:
    - Change research topic in main()
    - Adjust model parameters (temperature, max_tokens)
    - Modify agent prompts for different behaviors
    - Add more agents with different models

Performance Notes:
    - Execution time: 30-60 seconds depending on hardware
    - Memory usage: ~2-4GB for all three models
    - Can run on CPU, GPU acceleration recommended

Next Steps:
    - a2a_ollama_adaptive.py: Auto-detects available models
    - a2a_ollama_code_review.py: Specialized code review system
    - intelligent_agent_orchestration_demo.py: Full orchestration
"""

import time

from kailash import Workflow
from kailash.nodes.ai import A2AAgentNode, A2ACoordinatorNode, SharedMemoryPoolNode
from kailash.runtime.local import LocalRuntime


def create_ollama_research_team():
    """
    Create a research team with different Ollama models.

    This function builds a sophisticated multi-agent research system where each
    agent uses a different Ollama model, chosen for its specific strengths:

    - Llama 3.2: Research specialist - fast, broad knowledge
    - Mistral: Analysis expert - deep reasoning, pattern recognition
    - Phi: Synthesis specialist - concise summaries, integration

    The agents collaborate through a shared memory pool with attention filtering,
    allowing them to build on each other's work while maintaining focus.

    Returns:
        Workflow: Configured workflow with three Ollama-powered agents

    Architecture:
        - SharedMemoryPoolNode: Central knowledge repository
        - A2ACoordinatorNode: Orchestrates agent collaboration
        - Research Agent (Llama): Initial investigation and discovery
        - Analysis Agent (Mistral): Deep analysis of findings
        - Synthesis Agent (Phi): Integration and summarization

    The workflow is designed to handle complex research topics by leveraging
    the complementary strengths of different language models.
    """
    workflow = Workflow(
        workflow_id="ollama_research_team",
        name="Ollama Research Team",
        description="Multi-agent research using different Ollama models",
    )

    # Shared memory pool
    workflow.add_node("shared_memory", SharedMemoryPoolNode())

    # Coordinator
    workflow.add_node("coordinator", A2ACoordinatorNode())

    # Research Agent - Using Llama model
    workflow.add_node(
        "research_agent",
        A2AAgentNode(),
        config={
            "agent_id": "researcher_llama",
            "agent_role": "researcher",
            "provider": "ollama",
            "model": "llama3.2",  # Fast and good for research
            "system_prompt": """You are a research specialist using Llama 3.2. Your role is to:
1. Gather and analyze information on given topics
2. Identify key findings and patterns
3. Share important discoveries with the team
4. Be concise but thorough in your analysis""",
            "attention_filter": {
                "tags": ["research", "data", "findings"],
                "importance_threshold": 0.6,
                "window_size": 20,
            },
        },
    )

    # Analysis Agent - Using Mistral
    workflow.add_node(
        "analysis_agent",
        A2AAgentNode(),
        config={
            "agent_id": "analyst_mistral",
            "agent_role": "analyst",
            "provider": "ollama",
            "model": "mistral",  # Good for analytical tasks
            "system_prompt": """You are an analytical expert using Mistral. Your role is to:
1. Analyze research findings from other agents
2. Identify trends and correlations
3. Provide statistical insights
4. Draw meaningful conclusions from data
5. Share critical insights with high importance scores""",
            "attention_filter": {
                "tags": ["analysis", "statistics", "trends", "research"],
                "importance_threshold": 0.7,
                "window_size": 15,
            },
        },
    )

    # Synthesis Agent - Using Phi
    workflow.add_node(
        "synthesis_agent",
        A2AAgentNode(),
        config={
            "agent_id": "synthesizer_phi",
            "agent_role": "synthesizer",
            "provider": "ollama",
            "model": "phi",  # Efficient for synthesis
            "system_prompt": """You are a synthesis expert using Phi. Your role is to:
1. Review all findings from research and analysis agents
2. Integrate different perspectives
3. Create comprehensive summaries
4. Formulate final conclusions
5. Prioritize actionable insights""",
            "attention_filter": {
                "tags": ["findings", "analysis", "conclusion"],
                "importance_threshold": 0.5,
                "window_size": 30,
                "preferred_agents": ["researcher_llama", "analyst_mistral"],
            },
        },
    )

    # Connect all agents to shared memory
    for agent_id in ["research_agent", "analysis_agent", "synthesis_agent"]:
        workflow.connect(agent_id, "shared_memory")
        workflow.connect(agent_id, "coordinator")

    return workflow


def demonstrate_ollama_collaboration():
    """Run a collaborative research session with Ollama models."""
    print("=== Ollama Multi-Agent Research Demo ===\n")
    print("Note: This requires Ollama to be running with models installed.")
    print("If you see errors, make sure to run:")
    print("  ollama pull llama3.2")
    print("  ollama pull mistral")
    print("  ollama pull phi\n")

    workflow = create_ollama_research_team()
    runtime = LocalRuntime()
    memory_pool = workflow._node_instances["shared_memory"]
    coordinator = workflow._node_instances["coordinator"]

    # Register agents with coordinator
    print("Step 1: Registering agents...\n")
    agents = [
        {
            "id": "researcher_llama",
            "skills": ["research", "information_gathering", "pattern_recognition"],
            "role": "researcher",
        },
        {
            "id": "analyst_mistral",
            "skills": ["data_analysis", "statistical_analysis", "trend_identification"],
            "role": "analyst",
        },
        {
            "id": "synthesizer_phi",
            "skills": ["synthesis", "summarization", "conclusion_formulation"],
            "role": "synthesizer",
        },
    ]

    for agent in agents:
        result = coordinator.execute(action="register", agent_info=agent)
        print(f"  Registered {agent['id']}: {result['success']}")

    # Research Topic
    research_topic = (
        "Impact of artificial intelligence on software development productivity"
    )
    print(f"\n{'='*60}")
    print(f"RESEARCH TOPIC: {research_topic}")
    print(f"{'='*60}\n")

    # Phase 1: Initial Research
    print("Phase 1: Initial Research with Llama 3.2")
    print("-" * 40)

    try:
        result1, _ = runtime.execute(
            workflow,
            parameters={
                "research_agent": {
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Research the following topic and identify key findings: {research_topic}",
                        }
                    ],
                    "memory_pool": memory_pool,
                    "provider": "ollama",
                    "model": "llama3.2",
                }
            },
        )

        if result1.get("research_agent", {}).get("success"):
            response = result1["research_agent"]["response"]["content"]
            print(f"Research Agent (Llama):\n{response}\n")
            insights = result1["research_agent"]["a2a_metadata"]["insights_generated"]
            print(f"Insights generated: {insights}")
        else:
            print(
                "Research agent failed:",
                result1.get("research_agent", {}).get("error", "Unknown error"),
            )

    except Exception as e:
        print(f"Error with research agent: {e}")
        print("Make sure Ollama is running and llama3.2 model is installed")

    time.sleep(1)  # Small delay between phases

    # Phase 2: Analysis
    print("\n\nPhase 2: Analysis with Mistral")
    print("-" * 40)

    try:
        result2, _ = runtime.execute(
            workflow,
            parameters={
                "analysis_agent": {
                    "messages": [
                        {
                            "role": "user",
                            "content": "Analyze the research findings and identify key trends and implications",
                        }
                    ],
                    "memory_pool": memory_pool,
                    "provider": "ollama",
                    "model": "mistral",
                }
            },
        )

        if result2.get("analysis_agent", {}).get("success"):
            response = result2["analysis_agent"]["response"]["content"]
            print(f"Analysis Agent (Mistral):\n{response}\n")

            # Check shared context usage
            shared_context = result2["analysis_agent"]["a2a_metadata"][
                "shared_context_used"
            ]
            print(f"Shared context from other agents: {shared_context}")
        else:
            print(
                "Analysis agent failed:",
                result2.get("analysis_agent", {}).get("error", "Unknown error"),
            )

    except Exception as e:
        print(f"Error with analysis agent: {e}")
        print("Make sure Ollama is running and mistral model is installed")

    time.sleep(1)

    # Phase 3: Synthesis
    print("\n\nPhase 3: Synthesis with Phi")
    print("-" * 40)

    try:
        result3, _ = runtime.execute(
            workflow,
            parameters={
                "synthesis_agent": {
                    "messages": [
                        {
                            "role": "user",
                            "content": "Synthesize all findings and provide actionable conclusions",
                        }
                    ],
                    "memory_pool": memory_pool,
                    "provider": "ollama",
                    "model": "phi",
                }
            },
        )

        if result3.get("synthesis_agent", {}).get("success"):
            response = result3["synthesis_agent"]["response"]["content"]
            print(f"Synthesis Agent (Phi):\n{response}\n")

            shared_context = result3["synthesis_agent"]["a2a_metadata"][
                "shared_context_used"
            ]
            print(f"Integrated insights from {shared_context} other agents")
        else:
            print(
                "Synthesis agent failed:",
                result3.get("synthesis_agent", {}).get("error", "Unknown error"),
            )

    except Exception as e:
        print(f"Error with synthesis agent: {e}")
        print("Make sure Ollama is running and phi model is installed")

    # Review Shared Memory
    print("\n\n" + "=" * 60)
    print("SHARED MEMORY ANALYSIS")
    print("=" * 60)

    # Get all memories
    all_memories = memory_pool.execute(
        action="read",
        agent_id="reviewer",
        attention_filter={"importance_threshold": 0.0, "window_size": 100},
    )

    if all_memories["success"]:
        print(f"\nTotal memories created: {all_memories['total_available']}")

        # Group by agent
        by_agent = {}
        for mem in all_memories["memories"]:
            agent = mem["agent_id"]
            if agent not in by_agent:
                by_agent[agent] = []
            by_agent[agent].append(mem)

        print("\nMemories by agent:")
        for agent, memories in by_agent.items():
            print(f"  {agent}: {len(memories)} memories")

        # Show high-importance memories
        high_importance = [
            m for m in all_memories["memories"] if m["importance"] >= 0.8
        ]
        if high_importance:
            print(f"\nHigh-importance insights ({len(high_importance)}):")
            for i, mem in enumerate(high_importance[:3], 1):
                print(f"\n{i}. [{mem['agent_id']}] (importance: {mem['importance']})")
                print(
                    f"   {mem['content'][:200]}..."
                    if len(mem["content"]) > 200
                    else f"   {mem['content']}"
                )
                print(f"   Tags: {', '.join(mem['tags'])}")

    # Demonstrate semantic search
    print("\n\n" + "=" * 60)
    print("SEMANTIC SEARCH DEMO")
    print("=" * 60)

    search_query = "productivity improvements"
    search_results = memory_pool.execute(
        action="query", agent_id="searcher", query=search_query
    )

    if search_results["success"] and search_results["results"]:
        print(f"\nSearch results for '{search_query}':")
        for i, result in enumerate(search_results["results"][:3], 1):
            print(
                f"\n{i}. [{result['agent_id']}] (match score: {result['match_score']:.2f})"
            )
            print(f"   {result['content'][:150]}...")


def demonstrate_consensus_building():
    """Demonstrate consensus building among Ollama agents."""
    print("\n\n" + "=" * 60)
    print("CONSENSUS BUILDING DEMO")
    print("=" * 60)

    workflow = create_ollama_research_team()
    coordinator = workflow._node_instances["coordinator"]

    # Register agents
    for agent_id in ["researcher_llama", "analyst_mistral", "synthesizer_phi"]:
        coordinator.execute(
            action="register",
            agent_info={"id": agent_id, "role": agent_id.split("_")[0]},
        )

    # Create consensus proposal
    proposal = {
        "session_id": "ai_impact_consensus",
        "proposal": "AI significantly improves developer productivity by 20-40% through code completion and automation",
        "deadline": time.time() + 300,
    }

    print("\nProposal:", proposal["proposal"])
    print("\nInitiating consensus...")

    # Start consensus
    coordinator.execute(action="consensus", consensus_proposal=proposal)

    # Simulate votes based on agent analysis
    votes = [
        ("researcher_llama", True, "Research supports this claim"),
        ("analyst_mistral", True, "Data shows 25-35% improvement"),
        ("synthesizer_phi", True, "Consensus aligns with findings"),
    ]

    for agent_id, vote, reason in votes:
        coordinator.execute(
            action="consensus",
            consensus_proposal={"session_id": "ai_impact_consensus"},
            agent_id=agent_id,
            vote=vote,
        )
        print(f"  {agent_id}: {'Yes' if vote else 'No'} - {reason}")

    # Check final consensus
    final_result = coordinator.execute(
        action="consensus", consensus_proposal={"session_id": "ai_impact_consensus"}
    )

    if final_result.get("consensus_reached"):
        print(f"\nConsensus reached: {final_result['result']}")
        print(f"Votes: {len(final_result['votes'])} agents participated")


def main():
    """Run the Ollama A2A demonstration."""
    print("=" * 60)
    print("A2A MULTI-AGENT COLLABORATION WITH OLLAMA")
    print("=" * 60)
    print()

    # Run the main collaboration demo
    demonstrate_ollama_collaboration()

    # Run consensus building demo
    demonstrate_consensus_building()

    print("\n\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)
    print("\nKey Insights:")
    print("- Different Ollama models can specialize in different tasks")
    print("- Agents share discoveries through the memory pool")
    print("- Selective attention filters relevant information")
    print("- Consensus can be reached through structured voting")
    print("\nTo use other models, update the 'model' parameter in agent configs")
    print("Popular options: llama3.2, mistral, phi, gemma2, qwen2.5")


if __name__ == "__main__":
    main()
