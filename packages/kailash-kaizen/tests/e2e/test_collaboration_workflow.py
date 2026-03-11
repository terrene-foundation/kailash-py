"""
Tier 3 E2E Tests: Complete Multi-Agent Collaboration Workflow with Real Infrastructure.

Tests complete multi-agent collaboration workflows end-to-end with REAL LLMs,
REAL insight sharing, and REAL agent coordination. NO MOCKING ALLOWED.

Test Coverage:
- Complete multi-agent collaboration (3 tests)
- Insight flow workflow (2 tests)

Total: 5 E2E tests
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Shared memory for collaboration
from kaizen.memory.shared_memory import SharedMemoryPool

# Real LLM providers
from tests.utils.real_llm_providers import RealOpenAIProvider

# =============================================================================
# COMPLETE MULTI-AGENT COLLABORATION E2E TESTS (3 tests)
# =============================================================================


@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_complete_multi_agent_collaboration_workflow():
    """Test complete multi-agent collaboration workflow end-to-end (E2E)."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/2-multi-agent/shared-insights"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import SharedInsightsWorkflow, WorkflowConfig

        config = WorkflowConfig(
            llm_provider="openai",
            model="gpt-5-nano",
            temperature=0.3,
            max_tokens=300,
            num_agents=3,
            share_insights=True,
        )

        workflow = SharedInsightsWorkflow(config)

        # Complete collaboration workflow
        topic = "The future of artificial intelligence and its impact on society"

        results = workflow.run(topic=topic)

        # Verify complete workflow execution
        assert results is not None
        assert (
            "insights" in results
            or "agent_outputs" in results
            or "final_output" in results
        )

        # Should have contributions from multiple agents
        if "agent_outputs" in results:
            assert (
                len(results["agent_outputs"]) >= 2
            ), "Should have outputs from multiple agents"

        # Shared insights should exist
        if "shared_insights" in results:
            assert len(results["shared_insights"]) > 0, "Should have shared insights"

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_multi_agent_research_synthesis_workflow():
    """Test multi-agent research and synthesis workflow (E2E)."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")
    pool = SharedMemoryPool()

    # Complete research-synthesis workflow
    # Agent 1: Researcher (gathers information)
    def research_agent(topic: str) -> Dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": "You are a research agent. Provide factual information.",
            },
            {"role": "user", "content": f"Research: {topic}"},
        ]
        result = llm_provider.complete(messages, temperature=0.1, max_tokens=200)

        insight = {
            "topic": topic,
            "insight": result["content"],
            "confidence": 0.85,
            "type": "research",
            "agent": "researcher",
        }
        pool.add_insight("researcher", insight)
        return insight

    # Agent 2: Analyst (analyzes research)
    def analyst_agent(topic: str) -> Dict[str, Any]:
        # Get research insights
        research_insights = pool.get_insights(agent_id="analyst", topic=topic, top_k=3)

        context = "\n".join([ins.get("insight", "") for ins in research_insights])

        messages = [
            {
                "role": "system",
                "content": "You are an analyst. Analyze the research findings.",
            },
            {
                "role": "user",
                "content": f"Research findings:\n{context}\n\nProvide analysis.",
            },
        ]
        result = llm_provider.complete(messages, temperature=0.2, max_tokens=200)

        insight = {
            "topic": topic,
            "insight": result["content"],
            "confidence": 0.80,
            "type": "analysis",
            "agent": "analyst",
        }
        pool.add_insight("analyst", insight)
        return insight

    # Agent 3: Synthesizer (creates final synthesis)
    def synthesizer_agent(topic: str) -> Dict[str, Any]:
        # Get all insights
        all_insights = pool.get_insights(agent_id="synthesizer", topic=topic, top_k=5)

        context = "\n".join(
            [
                f"{ins.get('type', 'unknown')}: {ins.get('insight', '')}"
                for ins in all_insights
            ]
        )

        messages = [
            {
                "role": "system",
                "content": "You are a synthesizer. Create a comprehensive synthesis.",
            },
            {
                "role": "user",
                "content": f"All insights:\n{context}\n\nCreate synthesis.",
            },
        ]
        result = llm_provider.complete(messages, temperature=0.2, max_tokens=300)

        return {
            "topic": topic,
            "synthesis": result["content"],
            "sources": len(all_insights),
            "agent": "synthesizer",
        }

    # Execute complete workflow
    topic = "Climate change solutions"

    research_result = research_agent(topic)
    analysis_result = analyst_agent(topic)
    synthesis_result = synthesizer_agent(topic)

    # Verify complete workflow
    assert research_result is not None
    assert "insight" in research_result

    assert analysis_result is not None
    assert "insight" in analysis_result

    assert synthesis_result is not None
    assert "synthesis" in synthesis_result

    # Synthesis should incorporate multiple sources
    assert synthesis_result["sources"] >= 2


@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_multi_agent_consensus_building_workflow():
    """Test multi-agent consensus building workflow (E2E)."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    # Complete consensus workflow
    # Multiple agents provide perspectives
    def agent_perspective(agent_id: str, topic: str, stance: str) -> Dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": f"Provide a {stance} perspective on this topic.",
            },
            {"role": "user", "content": topic},
        ]
        result = llm_provider.complete(messages, temperature=0.3, max_tokens=150)

        return {"agent": agent_id, "stance": stance, "perspective": result["content"]}

    # Moderator builds consensus
    def moderator_consensus(perspectives: List[Dict[str, Any]]) -> Dict[str, Any]:
        all_perspectives = "\n\n".join(
            [f"{p['agent']} ({p['stance']}):\n{p['perspective']}" for p in perspectives]
        )

        messages = [
            {"role": "system", "content": "Find common ground and build consensus."},
            {
                "role": "user",
                "content": f"Perspectives:\n\n{all_perspectives}\n\nBuild consensus.",
            },
        ]
        result = llm_provider.complete(messages, temperature=0.2, max_tokens=300)

        return {"consensus": result["content"], "num_perspectives": len(perspectives)}

    # Execute workflow
    topic = "Should organizations adopt remote work policies?"

    # Gather perspectives
    perspectives = [
        agent_perspective("agent_1", topic, "supportive"),
        agent_perspective("agent_2", topic, "critical"),
        agent_perspective("agent_3", topic, "balanced"),
    ]

    # Build consensus
    consensus = moderator_consensus(perspectives)

    # Verify workflow
    assert len(perspectives) == 3
    assert all("perspective" in p for p in perspectives)

    assert "consensus" in consensus
    assert len(consensus["consensus"]) > 0
    assert consensus["num_perspectives"] == 3


# =============================================================================
# INSIGHT FLOW WORKFLOW E2E TESTS (2 tests)
# =============================================================================


@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_insight_flow_sequential_enhancement():
    """Test insights flow and enhance sequentially through agents (E2E)."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")
    pool = SharedMemoryPool()

    # Sequential enhancement workflow
    def enhance_insight(agent_id: str, topic: str, iteration: int) -> Dict[str, Any]:
        # Get previous insights
        previous_insights = pool.get_insights(agent_id=agent_id, topic=topic, top_k=5)

        if previous_insights:
            context = "\n".join([ins.get("insight", "") for ins in previous_insights])
            prompt = f"Previous insights:\n{context}\n\nEnhance and expand on these insights about {topic}."
        else:
            prompt = f"Provide initial insights about {topic}."

        messages = [
            {"role": "system", "content": "Enhance and expand insights progressively."},
            {"role": "user", "content": prompt},
        ]

        result = llm_provider.complete(messages, temperature=0.2, max_tokens=200)

        insight = {
            "topic": topic,
            "insight": result["content"],
            "iteration": iteration,
            "confidence": 0.7 + (iteration * 0.05),  # Increasing confidence
            "agent": agent_id,
        }

        pool.add_insight(agent_id, insight)
        return insight

    # Execute sequential enhancement
    topic = "Sustainable energy solutions"

    # 4 iterations of enhancement
    enhancements = []
    for i in range(4):
        enhanced = enhance_insight(f"enhancer_{i}", topic, i + 1)
        enhancements.append(enhanced)

    # Verify sequential enhancement
    assert len(enhancements) == 4

    # Confidence should increase with iterations
    confidences = [e["confidence"] for e in enhancements]
    assert (
        confidences[-1] > confidences[0]
    ), "Confidence should increase with enhancement"

    # Final insights should build on earlier ones
    final_insights = pool.get_insights(agent_id="final", topic=topic, top_k=10)
    assert len(final_insights) >= 3, "Should accumulate multiple insights"


@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_insight_flow_parallel_aggregation():
    """Test insights flow from parallel agents and aggregate (E2E)."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")
    pool = SharedMemoryPool()

    # Parallel insight generation
    def parallel_agent(agent_id: str, topic: str, aspect: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": f"Focus on the {aspect} aspect."},
            {"role": "user", "content": f"Analyze {topic} from {aspect} perspective."},
        ]

        result = llm_provider.complete(messages, temperature=0.2, max_tokens=150)

        insight = {
            "topic": topic,
            "aspect": aspect,
            "insight": result["content"],
            "confidence": 0.85,
            "agent": agent_id,
        }

        pool.add_insight(agent_id, insight)
        return insight

    # Aggregator combines parallel insights
    def aggregator_agent(topic: str) -> Dict[str, Any]:
        all_insights = pool.get_insights(agent_id="aggregator", topic=topic, top_k=10)

        insights_by_aspect = {}
        for ins in all_insights:
            aspect = ins.get("aspect", "general")
            insights_by_aspect[aspect] = ins.get("insight", "")

        combined = "\n\n".join(
            [
                f"{aspect.upper()}:\n{insight}"
                for aspect, insight in insights_by_aspect.items()
            ]
        )

        messages = [
            {"role": "system", "content": "Aggregate insights from different aspects."},
            {
                "role": "user",
                "content": f"Insights:\n\n{combined}\n\nCreate aggregated view.",
            },
        ]

        result = llm_provider.complete(messages, temperature=0.2, max_tokens=300)

        return {
            "topic": topic,
            "aggregated_insight": result["content"],
            "num_aspects": len(insights_by_aspect),
            "agent": "aggregator",
        }

    # Execute parallel-aggregate workflow
    topic = "Future of work"

    # Parallel agents analyze different aspects
    parallel_results = [
        parallel_agent("agent_tech", topic, "technology"),
        parallel_agent("agent_social", topic, "social"),
        parallel_agent("agent_economic", topic, "economic"),
    ]

    # Aggregate all insights
    aggregated = aggregator_agent(topic)

    # Verify workflow
    assert len(parallel_results) == 3
    assert all("insight" in r for r in parallel_results)

    assert "aggregated_insight" in aggregated
    assert aggregated["num_aspects"] >= 2, "Should aggregate multiple aspects"
    assert len(aggregated["aggregated_insight"]) > 0
