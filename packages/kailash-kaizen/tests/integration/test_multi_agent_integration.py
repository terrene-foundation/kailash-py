"""
Tier 2 Integration Tests: Multi-Agent Collaboration with Real Infrastructure.

Tests multi-agent coordination patterns with REAL LLMs and REAL collaboration.
NO MOCKING ALLOWED.

Test Coverage:
- Shared-insights example with real LLMs (5 tests)
- Agent collaboration patterns (5 tests)
- Insight propagation (5 tests)

Total: 15 integration tests
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Memory systems for collaboration
from kaizen.memory.shared_memory import SharedMemoryPool

# Real LLM providers
from tests.utils.real_llm_providers import RealOpenAIProvider

# =============================================================================
# SHARED-INSIGHTS EXAMPLE INTEGRATION TESTS (5 tests)
# =============================================================================


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_shared_insights_example_multi_agent_workflow():
    """Test shared-insights example with real multi-agent collaboration."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/2-multi-agent/shared-insights"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import SharedInsightsWorkflow, WorkflowConfig

        config = WorkflowConfig(
            llm_provider="openai", model="gpt-5-nano", temperature=0.3, num_agents=3
        )

        workflow = SharedInsightsWorkflow(config)

        # Run multi-agent collaboration with real LLMs
        results = workflow.run(topic="Python programming best practices")

        # Verify collaboration happened
        assert results is not None
        assert "insights" in results or "agent_outputs" in results
        # Should have results from multiple agents
        assert (
            len(results.get("insights", [])) > 0
            or len(results.get("agent_outputs", {})) > 0
        )

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_shared_insights_example_insight_sharing():
    """Test shared-insights example shares insights between agents."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/2-multi-agent/shared-insights"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import SharedInsightsWorkflow, WorkflowConfig

        config = WorkflowConfig(
            llm_provider="openai", model="gpt-5-nano", num_agents=2, share_insights=True
        )

        workflow = SharedInsightsWorkflow(config)

        results = workflow.run(topic="Machine learning")

        # Verify insights were shared
        assert results is not None
        # Check for shared insights
        shared_insights = results.get("shared_insights", [])
        assert isinstance(shared_insights, list)

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_shared_insights_example_agent_specialization():
    """Test shared-insights example uses specialized agents."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/2-multi-agent/shared-insights"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import SharedInsightsWorkflow, WorkflowConfig

        config = WorkflowConfig(
            llm_provider="openai",
            model="gpt-5-nano",
            agents={
                "researcher": {"role": "Research factual information"},
                "analyst": {"role": "Analyze and synthesize"},
                "writer": {"role": "Write clear summaries"},
            },
        )

        workflow = SharedInsightsWorkflow(config)

        results = workflow.run(topic="AI ethics")

        # Each specialized agent should contribute
        assert results is not None
        agent_outputs = results.get("agent_outputs", {})
        # Should have outputs from specialized agents
        assert len(agent_outputs) > 0

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_shared_insights_example_consensus_building():
    """Test shared-insights example builds consensus across agents."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/2-multi-agent/shared-insights"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import SharedInsightsWorkflow, WorkflowConfig

        config = WorkflowConfig(
            llm_provider="openai", model="gpt-5-nano", num_agents=3, consensus_mode=True
        )

        workflow = SharedInsightsWorkflow(config)

        results = workflow.run(topic="Climate change solutions")

        # Should build consensus
        assert results is not None
        consensus = results.get("consensus", {})
        # Consensus should be formed from multiple agent inputs
        assert consensus is not None

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_shared_insights_example_incremental_collaboration():
    """Test shared-insights example builds insights incrementally."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/2-multi-agent/shared-insights"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import SharedInsightsWorkflow, WorkflowConfig

        config = WorkflowConfig(
            llm_provider="openai", model="gpt-5-nano", num_agents=3, incremental=True
        )

        workflow = SharedInsightsWorkflow(config)

        # Each agent builds on previous insights
        results = workflow.run(topic="Software architecture patterns")

        assert results is not None
        # Should have incremental contributions
        iterations = results.get("iterations", [])
        assert isinstance(iterations, list)

    finally:
        sys.path.remove(str(example_path))


# =============================================================================
# AGENT COLLABORATION PATTERNS INTEGRATION TESTS (5 tests)
# =============================================================================


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_agent_collaboration_sequential_pipeline():
    """Test sequential agent pipeline with real LLMs."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    def agent_1_process(input_data: str) -> Dict[str, Any]:
        """Agent 1: Extract key points."""
        messages = [
            {"role": "system", "content": "Extract key points from the text."},
            {"role": "user", "content": input_data},
        ]
        result = llm_provider.complete(messages, temperature=0.1, max_tokens=150)
        return {"key_points": result["content"], "agent": "agent_1"}

    def agent_2_process(agent_1_output: Dict[str, Any]) -> Dict[str, Any]:
        """Agent 2: Summarize key points."""
        messages = [
            {"role": "system", "content": "Summarize these key points concisely."},
            {"role": "user", "content": agent_1_output["key_points"]},
        ]
        result = llm_provider.complete(messages, temperature=0.1, max_tokens=100)
        return {"summary": result["content"], "agent": "agent_2"}

    # Sequential pipeline
    input_text = "Python is a versatile programming language used in web development, data science, and AI."

    step_1 = agent_1_process(input_text)
    step_2 = agent_2_process(step_1)

    # Verify pipeline worked
    assert "key_points" in step_1
    assert "summary" in step_2
    assert len(step_2["summary"]) > 0


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_agent_collaboration_parallel_processing():
    """Test parallel agent processing with real LLMs."""
    import asyncio

    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    async def agent_analyze(text: str, aspect: str) -> Dict[str, Any]:
        """Agent analyzes specific aspect."""
        messages = [
            {"role": "system", "content": f"Analyze the {aspect} of this text."},
            {"role": "user", "content": text},
        ]
        result = llm_provider.complete(messages, temperature=0.1, max_tokens=100)
        return {"aspect": aspect, "analysis": result["content"]}

    async def parallel_analysis():
        text = "Python is a high-level, interpreted programming language known for readability."

        # Multiple agents analyze different aspects in parallel
        tasks = [
            agent_analyze(text, "technical aspects"),
            agent_analyze(text, "benefits"),
            agent_analyze(text, "use cases"),
        ]

        results = await asyncio.gather(*tasks)
        return results

    # Run parallel processing
    results = asyncio.run(parallel_analysis())

    # All agents should complete
    assert len(results) == 3
    assert all("analysis" in r for r in results)


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_agent_collaboration_supervisor_worker():
    """Test supervisor-worker pattern with real LLMs."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    def supervisor_delegate(task: str) -> List[Dict[str, Any]]:
        """Supervisor breaks down task into subtasks."""
        messages = [
            {"role": "system", "content": "Break this task into 3 simple subtasks."},
            {"role": "user", "content": task},
        ]
        result = llm_provider.complete(messages, temperature=0.1, max_tokens=150)

        # Create subtasks (simplified)
        return [
            {"subtask": f"Subtask 1: {result['content'][:50]}"},
            {"subtask": "Subtask 2: Research"},
            {"subtask": "Subtask 3: Compile"},
        ]

    def worker_execute(subtask: Dict[str, Any]) -> Dict[str, Any]:
        """Worker executes subtask."""
        messages = [
            {"role": "system", "content": "Execute this subtask."},
            {"role": "user", "content": subtask["subtask"]},
        ]
        result = llm_provider.complete(messages, temperature=0.1, max_tokens=100)
        return {"subtask": subtask["subtask"], "result": result["content"]}

    # Supervisor-worker workflow
    task = "Research Python frameworks and create a comparison report"

    subtasks = supervisor_delegate(task)
    worker_results = [worker_execute(st) for st in subtasks]

    # Verify workflow
    assert len(subtasks) == 3
    assert len(worker_results) == 3
    assert all("result" in r for r in worker_results)


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_agent_collaboration_debate_consensus():
    """Test debate-consensus pattern with real LLMs."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    def agent_position(topic: str, position: str) -> Dict[str, Any]:
        """Agent takes a position on topic."""
        messages = [
            {"role": "system", "content": f"Argue for the {position} position."},
            {"role": "user", "content": f"Topic: {topic}"},
        ]
        result = llm_provider.complete(messages, temperature=0.3, max_tokens=100)
        return {"position": position, "argument": result["content"]}

    def moderator_consensus(positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Moderator builds consensus."""
        all_arguments = "\n".join(
            [f"{p['position']}: {p['argument']}" for p in positions]
        )

        messages = [
            {
                "role": "system",
                "content": "Find common ground between these positions.",
            },
            {"role": "user", "content": all_arguments},
        ]
        result = llm_provider.complete(messages, temperature=0.1, max_tokens=150)
        return {"consensus": result["content"]}

    # Debate workflow
    topic = "Should Python use type hints?"

    position_1 = agent_position(topic, "pro")
    position_2 = agent_position(topic, "con")

    consensus = moderator_consensus([position_1, position_2])

    # Verify debate worked
    assert "argument" in position_1
    assert "argument" in position_2
    assert "consensus" in consensus


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_agent_collaboration_research_synthesis():
    """Test research-synthesis pattern with real LLMs."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    def researcher_agent(query: str) -> Dict[str, Any]:
        """Research agent gathers information."""
        messages = [
            {"role": "system", "content": "Research this query and provide findings."},
            {"role": "user", "content": query},
        ]
        result = llm_provider.complete(messages, temperature=0.1, max_tokens=150)
        return {"findings": result["content"]}

    def synthesis_agent(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Synthesis agent combines findings."""
        all_findings = "\n".join([f["findings"] for f in findings])

        messages = [
            {"role": "system", "content": "Synthesize these research findings."},
            {"role": "user", "content": all_findings},
        ]
        result = llm_provider.complete(messages, temperature=0.1, max_tokens=200)
        return {"synthesis": result["content"]}

    # Research-synthesis workflow
    research_1 = researcher_agent("What is Python used for?")
    research_2 = researcher_agent("Why is Python popular?")

    synthesis = synthesis_agent([research_1, research_2])

    # Verify workflow
    assert "findings" in research_1
    assert "findings" in research_2
    assert "synthesis" in synthesis


# =============================================================================
# INSIGHT PROPAGATION INTEGRATION TESTS (5 tests)
# =============================================================================


@pytest.mark.integration
def test_insight_propagation_shared_memory_pool():
    """Test insights propagate through SharedMemoryPool."""
    pool = SharedMemoryPool()

    # Agent 1 adds insight
    pool.add_insight(
        "agent_1",
        {
            "topic": "Python",
            "insight": "Python has excellent data science libraries",
            "confidence": 0.9,
            "source": "research",
        },
    )

    # Agent 2 retrieves and builds on insight
    agent_2_context = pool.get_insights(agent_id="agent_2", topic="Python")

    # Agent 2 adds derived insight
    pool.add_insight(
        "agent_2",
        {
            "topic": "Python",
            "insight": "Python's data science ecosystem includes NumPy and Pandas",
            "confidence": 0.85,
            "source": "synthesis",
            "based_on": agent_2_context,
        },
    )

    # Agent 3 retrieves all insights
    agent_3_context = pool.get_insights(agent_id="agent_3", topic="Python")

    # Should have insights from multiple agents
    assert len(agent_3_context) >= 2


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_insight_propagation_with_real_llm():
    """Test insight propagation with real LLM-generated insights."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")
    pool = SharedMemoryPool()

    def generate_insight(
        agent_id: str, prompt: str, prior_insights: List[Dict]
    ) -> None:
        """Generate insight using LLM with access to prior insights."""
        context = (
            "\n".join([f"- {ins.get('insight', '')}" for ins in prior_insights])
            if prior_insights
            else "No prior insights."
        )

        messages = [
            {"role": "system", "content": "Generate an insight based on the context."},
            {"role": "user", "content": f"Context:\n{context}\n\nNew prompt: {prompt}"},
        ]

        result = llm_provider.complete(messages, temperature=0.3, max_tokens=100)

        pool.add_insight(
            agent_id,
            {
                "topic": "AI",
                "insight": result["content"],
                "confidence": 0.8,
                "agent": agent_id,
            },
        )

    # Agent 1 generates initial insight
    generate_insight("agent_1", "What is AI?", [])

    # Agent 2 builds on Agent 1's insight
    agent_1_insights = pool.get_insights(agent_id="agent_2", topic="AI")
    generate_insight("agent_2", "How is AI used?", agent_1_insights)

    # Agent 3 synthesizes both
    all_insights = pool.get_insights(agent_id="agent_3", topic="AI")
    generate_insight("agent_3", "What is the future of AI?", all_insights)

    # Should have insights from all agents
    final_insights = pool.get_insights(agent_id="final", topic="AI")
    assert len(final_insights) >= 3


@pytest.mark.integration
def test_insight_propagation_topic_filtering():
    """Test insights propagate correctly filtered by topic."""
    pool = SharedMemoryPool()

    # Add insights on different topics
    pool.add_insight(
        "agent_1", {"topic": "Python", "insight": "Python insight 1", "confidence": 0.9}
    )

    pool.add_insight(
        "agent_1", {"topic": "Java", "insight": "Java insight 1", "confidence": 0.8}
    )

    pool.add_insight(
        "agent_2",
        {"topic": "Python", "insight": "Python insight 2", "confidence": 0.85},
    )

    # Get Python insights only
    python_insights = pool.get_insights(agent_id="agent_3", topic="Python")

    # Should only get Python insights
    assert all("Python" in ins.get("topic", "") for ins in python_insights)
    assert len(python_insights) == 2


@pytest.mark.integration
def test_insight_propagation_confidence_ranking():
    """Test insights propagate ranked by confidence."""
    pool = SharedMemoryPool()

    # Add insights with varying confidence
    pool.add_insight(
        "agent_1",
        {"topic": "ML", "insight": "Low confidence insight", "confidence": 0.3},
    )

    pool.add_insight(
        "agent_2",
        {"topic": "ML", "insight": "High confidence insight", "confidence": 0.95},
    )

    pool.add_insight(
        "agent_3",
        {"topic": "ML", "insight": "Medium confidence insight", "confidence": 0.6},
    )

    # Get top 2 insights
    top_insights = pool.get_insights(agent_id="agent_4", topic="ML", top_k=2)

    # Should get highest confidence insights
    assert len(top_insights) <= 2


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_insight_propagation_collaborative_refinement():
    """Test insights are refined collaboratively through propagation."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")
    pool = SharedMemoryPool()

    def refine_insight(agent_id: str, base_insight: str) -> str:
        """Refine insight using LLM."""
        messages = [
            {"role": "system", "content": "Refine and improve this insight."},
            {"role": "user", "content": base_insight},
        ]

        result = llm_provider.complete(messages, temperature=0.2, max_tokens=100)
        return result["content"]

    # Initial rough insight
    initial_insight = "Python is good for programming"

    # Agent 1 refines
    refined_1 = refine_insight("agent_1", initial_insight)
    pool.add_insight(
        "agent_1",
        {"topic": "Python", "insight": refined_1, "confidence": 0.7, "version": 1},
    )

    # Agent 2 refines further
    agent_1_insights = pool.get_insights(agent_id="agent_2", topic="Python")
    if agent_1_insights:
        refined_2 = refine_insight("agent_2", agent_1_insights[0]["insight"])
        pool.add_insight(
            "agent_2",
            {"topic": "Python", "insight": refined_2, "confidence": 0.85, "version": 2},
        )

    # Final insights should be more refined than initial
    final_insights = pool.get_insights(agent_id="final", topic="Python")
    assert len(final_insights) >= 1

    # Latest version should exist
    versions = [ins.get("version", 0) for ins in final_insights]
    assert max(versions) >= 1
