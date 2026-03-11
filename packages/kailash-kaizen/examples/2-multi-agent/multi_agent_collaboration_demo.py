"""
Multi-Agent Collaboration Demo using SharedMemoryPool.

This example demonstrates how multiple agents can collaborate by sharing
insights through a SharedMemoryPool. The demo shows:

1. Sequential collaboration: Agents build on each other's insights
2. Insight filtering: Agents read only relevant insights
3. Multi-agent workflow: Analyzer -> Responder -> Reviewer pattern

Example output shows how insights flow between agents for collaborative
problem solving.

Author: Kaizen Framework Team
Created: 2025-10-02 (Week 3, Phase 2: Shared Memory)
"""

from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.memory.shared_memory import SharedMemoryPool

# Create shared memory pool (global for all agents)
shared_pool = SharedMemoryPool()


# Agent 1: Analyzer
class AnalyzerStrategy:
    """Strategy that analyzes input and writes insights."""

    async def execute(self, agent, inputs):
        prompt = inputs.get("prompt", "")
        print(f"\n[{agent.agent_id}] Analyzing: {prompt}")

        # Check for previous insights
        shared_insights = inputs.get("_shared_insights", [])
        print(f"[{agent.agent_id}] Found {len(shared_insights)} shared insights")

        # Simulate analysis
        analysis = f"Analysis of '{prompt}': This appears to be a customer complaint about delayed shipping."

        return {
            "response": analysis,
            "_write_insight": "High-priority customer complaint detected: delayed shipping",
            "_insight_tags": ["customer", "complaint", "shipping", "urgent"],
            "_insight_importance": 0.95,
            "_insight_segment": "analysis",
            "_insight_metadata": {"source": "analyzer", "category": "complaint"},
        }


# Agent 2: Responder
class ResponderStrategy:
    """Strategy that generates responses based on analysis insights."""

    async def execute(self, agent, inputs):
        prompt = inputs.get("prompt", "")
        print(f"\n[{agent.agent_id}] Generating response for: {prompt}")

        # Read insights from analyzer
        shared_insights = inputs.get("_shared_insights", [])
        print(
            f"[{agent.agent_id}] Found {len(shared_insights)} shared insights from other agents"
        )

        if shared_insights:
            print(
                f"[{agent.agent_id}] Most relevant insight: {shared_insights[0]['content']}"
            )

        # Simulate response generation
        response = "We apologize for the shipping delay. We'll expedite your order immediately."

        return {
            "response": response,
            "_write_insight": "Response strategy: Apologize and expedite shipping",
            "_insight_tags": ["customer", "response", "solution"],
            "_insight_importance": 0.85,
            "_insight_segment": "planning",
            "_insight_metadata": {"action": "expedite", "tone": "apologetic"},
        }


# Agent 3: Reviewer
class ReviewerStrategy:
    """Strategy that reviews the response quality."""

    async def execute(self, agent, inputs):
        prompt = inputs.get("prompt", "")
        print(f"\n[{agent.agent_id}] Reviewing response: {prompt}")

        # Read all insights from analyzer and responder
        shared_insights = inputs.get("_shared_insights", [])
        print(
            f"[{agent.agent_id}] Found {len(shared_insights)} shared insights from other agents"
        )

        for insight in shared_insights:
            print(
                f"  - [{insight['agent_id']}] {insight['content']} (importance: {insight['importance']})"
            )

        # Simulate review
        review = "Response is appropriate: acknowledges issue, shows empathy, provides solution."

        return {
            "response": review,
            "_write_insight": "Response quality approved: meets customer service standards",
            "_insight_tags": ["review", "approved", "customer_service"],
            "_insight_importance": 0.80,
            "_insight_segment": "review",
            "_insight_metadata": {
                "status": "approved",
                "reviewer": "quality_assurance",
            },
        }


def main():
    """
    Run multi-agent collaboration demo.
    """
    print("=" * 80)
    print("Multi-Agent Collaboration Demo")
    print("=" * 80)

    # Create configuration
    config = BaseAgentConfig()

    # Create agents with shared memory
    analyzer = BaseAgent(config=config, shared_memory=shared_pool, agent_id="analyzer")
    analyzer.strategy = AnalyzerStrategy()

    responder = BaseAgent(
        config=config, shared_memory=shared_pool, agent_id="responder"
    )
    responder.strategy = ResponderStrategy()

    reviewer = BaseAgent(config=config, shared_memory=shared_pool, agent_id="reviewer")
    reviewer.strategy = ReviewerStrategy()

    # Execute sequential workflow
    print("\nPhase 1: Analysis")
    print("-" * 80)
    result1 = analyzer.run(prompt="My order is 5 days late and I need it urgently!")

    print("\nPhase 2: Response Generation")
    print("-" * 80)
    result2 = responder.run(prompt="Generate customer response based on analysis")

    print("\nPhase 3: Quality Review")
    print("-" * 80)
    result3 = reviewer.run(prompt="Review the response quality")

    # Show final shared memory state
    print("\n" + "=" * 80)
    print("Final Shared Memory State")
    print("=" * 80)

    all_insights = shared_pool.read_all()
    print(f"\nTotal insights in pool: {len(all_insights)}")

    for i, insight in enumerate(all_insights, 1):
        print(f"\nInsight {i}:")
        print(f"  Agent: {insight['agent_id']}")
        print(f"  Content: {insight['content']}")
        print(f"  Tags: {', '.join(insight['tags'])}")
        print(f"  Importance: {insight['importance']:.2f}")
        print(f"  Segment: {insight['segment']}")

    # Show statistics
    stats = shared_pool.get_stats()
    print("\n" + "=" * 80)
    print("Shared Memory Statistics")
    print("=" * 80)
    print(f"Total insights: {stats['insight_count']}")
    print(f"Unique agents: {stats['agent_count']}")
    print(f"Tag distribution: {stats['tag_distribution']}")
    print(f"Segment distribution: {stats['segment_distribution']}")

    # Demonstrate filtering
    print("\n" + "=" * 80)
    print("Attention Filtering Examples")
    print("=" * 80)

    # Filter 1: High importance customer insights
    high_importance = shared_pool.read_relevant(
        tags=["customer"], min_importance=0.85, exclude_own=False
    )
    print(f"\nHigh-importance customer insights (>= 0.85): {len(high_importance)}")
    for insight in high_importance:
        print(
            f"  - [{insight['agent_id']}] {insight['content']} ({insight['importance']:.2f})"
        )

    # Filter 2: Analysis segment only
    analysis_insights = shared_pool.read_relevant(
        segments=["analysis"], exclude_own=False
    )
    print(f"\nAnalysis segment insights: {len(analysis_insights)}")
    for insight in analysis_insights:
        print(f"  - [{insight['agent_id']}] {insight['content']}")

    # Filter 3: Top 2 insights
    top_insights = shared_pool.read_relevant(limit=2, exclude_own=False)
    print("\nTop 2 most important insights:")
    for insight in top_insights:
        print(
            f"  - [{insight['agent_id']}] {insight['content']} ({insight['importance']:.2f})"
        )

    print("\n" + "=" * 80)
    print("Demo Complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
