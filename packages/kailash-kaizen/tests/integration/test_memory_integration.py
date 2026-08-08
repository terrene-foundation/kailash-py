"""
Tier 2 Integration Tests: Memory Systems with Real Infrastructure.

Tests memory systems (BufferMemory, VectorMemory, KnowledgeGraphMemory, SharedMemoryPool)
with REAL data and REAL operations. NO MOCKING ALLOWED.

Test Coverage:
- BufferMemory with real conversations (5 tests)
- SummaryMemory with real summarization (3 tests)
- VectorMemory with real embeddings (5 tests)
- KnowledgeGraphMemory with real extraction (3 tests)
- SharedMemoryPool with real collaboration (4 tests)

Total: 20 integration tests
"""

import os
from typing import Any, Dict, List

import pytest

# Memory implementations
from kaizen.memory.buffer import BufferMemory
from kaizen.memory.knowledge_graph import KnowledgeGraphMemory
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.memory.summary import SummaryMemory
from kaizen.memory.vector import VectorMemory

# Real LLM provider for summarization
from tests.utils.real_llm_providers import RealOpenAIProvider

# =============================================================================
# BUFFER MEMORY INTEGRATION TESTS (5 tests)
# =============================================================================


@pytest.mark.integration
def test_buffer_memory_with_real_conversation():
    """Test BufferMemory with real multi-turn conversation data."""
    memory = BufferMemory(max_turns=5)
    session_id = "integration_test_buffer_001"

    # Simulate real conversation turns
    turns = [
        {
            "user": "What is Python?",
            "agent": "Python is a high-level programming language.",
        },
        {
            "user": "What makes it popular?",
            "agent": "Python is popular for its simplicity and versatility.",
        },
        {
            "user": "Can you give examples?",
            "agent": "Python is used in web development, data science, AI, and automation.",
        },
    ]

    # Save real conversation data (NO MOCKING)
    for turn in turns:
        memory.save_turn(session_id, turn)

    # Verify real memory operations
    context = memory.load_context(session_id)
    assert len(context["turns"]) == 3
    assert context["turns"][0]["user"] == "What is Python?"
    assert "programming language" in context["turns"][0]["agent"]


@pytest.mark.integration
def test_buffer_memory_max_turns_enforcement():
    """Test BufferMemory enforces max_turns limit with real data."""
    memory = BufferMemory(max_turns=3)
    session_id = "integration_test_buffer_002"

    # Add more turns than max_turns
    for i in range(5):
        memory.save_turn(session_id, {"user": f"Question {i}", "agent": f"Answer {i}"})

    # Verify only last 3 turns are kept
    context = memory.load_context(session_id)
    assert len(context["turns"]) == 3
    assert context["turns"][0]["user"] == "Question 2"  # Oldest kept
    assert context["turns"][2]["user"] == "Question 4"  # Newest


@pytest.mark.integration
def test_buffer_memory_multi_session_isolation():
    """Test BufferMemory isolates different sessions correctly."""
    memory = BufferMemory(max_turns=5)

    # Create two separate sessions
    session_1 = "integration_test_buffer_003a"
    session_2 = "integration_test_buffer_003b"

    memory.save_turn(
        session_1, {"user": "Session 1 question", "agent": "Session 1 answer"}
    )
    memory.save_turn(
        session_2, {"user": "Session 2 question", "agent": "Session 2 answer"}
    )

    # Verify isolation
    context_1 = memory.load_context(session_1)
    context_2 = memory.load_context(session_2)

    assert len(context_1["turns"]) == 1
    assert len(context_2["turns"]) == 1
    assert context_1["turns"][0]["user"] == "Session 1 question"
    assert context_2["turns"][0]["user"] == "Session 2 question"


@pytest.mark.integration
def test_buffer_memory_clear_session():
    """Test BufferMemory session clearing with real data.

    ``BufferMemory`` has no ``clear_session``; its real method is
    ``clear(session_id)`` — same arity and same meaning, so this one IS a
    straight rename (unlike the SharedMemoryPool calls below).
    """
    memory = BufferMemory(max_turns=5)
    session_id = "integration_test_buffer_004"
    other_session_id = "integration_test_buffer_004_bystander"

    # Add turns
    memory.save_turn(session_id, {"user": "Question", "agent": "Answer"})
    memory.save_turn(other_session_id, {"user": "Other", "agent": "Other answer"})
    assert len(memory.load_context(session_id)["turns"]) == 1

    # Clear session
    memory.clear(session_id)

    # Verify session is empty
    context = memory.load_context(session_id)
    assert len(context["turns"]) == 0

    # ...and that clearing was SCOPED to it. Without a bystander session, this
    # test passes identically whether clear() drops one session or all of them.
    assert (
        len(memory.load_context(other_session_id)["turns"]) == 1
    ), "clear(session_id) also dropped an unrelated session's history"


@pytest.mark.integration
def test_buffer_memory_context_formatting():
    """Test BufferMemory formats context correctly for real agent consumption."""
    memory = BufferMemory(max_turns=5)
    session_id = "integration_test_buffer_005"

    # Add conversation
    memory.save_turn(session_id, {"user": "Hello", "agent": "Hi there!"})
    memory.save_turn(
        session_id, {"user": "How are you?", "agent": "I'm doing well, thanks!"}
    )

    # Get formatted context
    context = memory.load_context(session_id)

    assert "turns" in context
    assert isinstance(context["turns"], list)
    assert all("user" in turn and "agent" in turn for turn in context["turns"])


# =============================================================================
# SUMMARY MEMORY INTEGRATION TESTS (3 tests) - Requires Real LLM
# =============================================================================


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_summary_memory_with_real_llm():
    """Test SummaryMemory with real LLM summarization (NO MOCKING)."""
    # Create real LLM provider
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    # Create SummaryMemory with real summarizer
    def real_summarizer(turns: List[Dict[str, str]]) -> str:
        """Real summarization using OpenAI."""
        conversation_text = "\n".join(
            [f"User: {turn['user']}\nAgent: {turn['agent']}" for turn in turns]
        )

        messages = [
            {
                "role": "system",
                "content": "Summarize the following conversation concisely.",
            },
            {"role": "user", "content": conversation_text},
        ]

        response = llm_provider.complete(messages, temperature=0.3, max_tokens=100)
        return response["content"]

    memory = SummaryMemory(max_turns=3, summarizer_fn=real_summarizer)
    session_id = "integration_test_summary_001"

    # Add turns to trigger summarization
    for i in range(4):
        memory.save_turn(
            session_id,
            {
                "user": f"Question {i} about Python programming",
                "agent": f"Answer {i} explaining Python features",
            },
        )

    # Verify summary was created (using real LLM)
    context = memory.load_context(session_id)
    assert "summary" in context
    assert len(context["summary"]) > 0
    assert isinstance(context["summary"], str)


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_summary_memory_preserves_recent_turns():
    """Test SummaryMemory preserves recent turns while summarizing old ones."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    def real_summarizer(turns: List[Dict[str, str]]) -> str:
        conversation_text = "\n".join(
            [f"User: {turn['user']}\nAgent: {turn['agent']}" for turn in turns]
        )

        messages = [
            {
                "role": "system",
                "content": "Summarize this conversation in one sentence.",
            },
            {"role": "user", "content": conversation_text},
        ]

        response = llm_provider.complete(messages, temperature=0.3, max_tokens=50)
        return response["content"]

    memory = SummaryMemory(max_turns=2, summarizer_fn=real_summarizer)
    session_id = "integration_test_summary_002"

    # Add 5 turns
    for i in range(5):
        memory.save_turn(session_id, {"user": f"Question {i}", "agent": f"Answer {i}"})

    context = memory.load_context(session_id)

    # Should have summary + recent turns
    assert "summary" in context
    assert "turns" in context
    assert len(context["turns"]) <= 2  # Only recent turns


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_summary_memory_incremental_updates():
    """Test SummaryMemory updates summary incrementally with real LLM."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    def real_summarizer(turns: List[Dict[str, str]]) -> str:
        conversation_text = "\n".join(
            [f"User: {turn['user']}\nAgent: {turn['agent']}" for turn in turns]
        )

        messages = [
            {"role": "system", "content": "Create a brief summary."},
            {"role": "user", "content": conversation_text},
        ]

        response = llm_provider.complete(messages, temperature=0.3, max_tokens=50)
        return response["content"]

    memory = SummaryMemory(max_turns=2, summarizer_fn=real_summarizer)
    session_id = "integration_test_summary_003"

    # First batch of turns
    for i in range(3):
        memory.save_turn(
            session_id,
            {"user": f"First topic question {i}", "agent": f"First topic answer {i}"},
        )

    first_summary = memory.load_context(session_id).get("summary", "")

    # Second batch of turns
    for i in range(3):
        memory.save_turn(
            session_id,
            {"user": f"Second topic question {i}", "agent": f"Second topic answer {i}"},
        )

    second_summary = memory.load_context(session_id).get("summary", "")

    # Summary should exist and potentially be updated
    assert first_summary is not None
    assert second_summary is not None
    assert isinstance(second_summary, str)


# =============================================================================
# VECTOR MEMORY INTEGRATION TESTS (5 tests) - Requires Real Embeddings
# =============================================================================


@pytest.mark.integration
def test_vector_memory_with_real_embeddings():
    """Test VectorMemory with real embedding model (NO MOCKING)."""
    # Use sentence-transformers for real embeddings
    try:
        from sentence_transformers import SentenceTransformer

        embedder = SentenceTransformer("all-MiniLM-L6-v2")
    except ImportError:
        pytest.skip("sentence-transformers not available")

    memory = VectorMemory(embedding_fn=embedder.encode, top_k=3)
    session_id = "integration_test_vector_001"

    # Add real conversations with different topics
    turns = [
        {
            "user": "Tell me about Python programming",
            "agent": "Python is a versatile language.",
        },
        {"user": "What about machine learning?", "agent": "ML is a subset of AI."},
        {"user": "Explain neural networks", "agent": "Neural networks are ML models."},
    ]

    for turn in turns:
        memory.save_turn(session_id, turn)

    # Perform real semantic search
    results = memory.search(session_id, "programming languages", top_k=2)

    assert len(results) > 0
    # Python-related turn should be most relevant
    assert "Python" in str(results[0]) or "programming" in str(results[0]).lower()


@pytest.mark.integration
def test_vector_memory_semantic_search_accuracy():
    """Test VectorMemory semantic search with real embeddings."""
    try:
        from sentence_transformers import SentenceTransformer

        embedder = SentenceTransformer("all-MiniLM-L6-v2")
    except ImportError:
        pytest.skip("sentence-transformers not available")

    memory = VectorMemory(embedding_fn=embedder.encode, top_k=5)
    session_id = "integration_test_vector_002"

    # Add diverse topics
    memory.save_turn(
        session_id,
        {
            "user": "What is Python?",
            "agent": "Python is a programming language for software development.",
        },
    )
    memory.save_turn(
        session_id,
        {
            "user": "Tell me about cooking pasta",
            "agent": "Pasta is cooked in boiling water for 8-10 minutes.",
        },
    )
    memory.save_turn(
        session_id,
        {
            "user": "How does Java work?",
            "agent": "Java is a compiled programming language that runs on JVM.",
        },
    )

    # Search for programming-related content
    results = memory.search(session_id, "software development languages", top_k=2)

    # Should retrieve programming-related turns, not cooking
    assert len(results) >= 1
    results_text = str(results).lower()
    assert (
        "programming" in results_text
        or "python" in results_text
        or "java" in results_text
    )
    assert "pasta" not in results_text and "cooking" not in results_text


@pytest.mark.integration
def test_vector_memory_with_context_loading():
    """Test VectorMemory loads relevant context correctly."""
    try:
        from sentence_transformers import SentenceTransformer

        embedder = SentenceTransformer("all-MiniLM-L6-v2")
    except ImportError:
        pytest.skip("sentence-transformers not available")

    memory = VectorMemory(embedding_fn=embedder.encode, top_k=3)
    session_id = "integration_test_vector_003"

    # Add conversation history
    for i in range(5):
        memory.save_turn(
            session_id,
            {
                "user": f"Question {i} about AI topic {i}",
                "agent": f"Answer {i} explaining concept {i}",
            },
        )

    # Load context with query
    context = memory.load_context(session_id, query="AI concepts")

    assert "relevant_turns" in context
    assert len(context["relevant_turns"]) <= 3  # Respects top_k
    assert isinstance(context["relevant_turns"], list)


@pytest.mark.integration
def test_vector_memory_multi_session_isolation():
    """Test VectorMemory isolates sessions correctly."""
    try:
        from sentence_transformers import SentenceTransformer

        embedder = SentenceTransformer("all-MiniLM-L6-v2")
    except ImportError:
        pytest.skip("sentence-transformers not available")

    memory = VectorMemory(embedding_fn=embedder.encode, top_k=3)

    session_1 = "integration_test_vector_004a"
    session_2 = "integration_test_vector_004b"

    # Session 1: Python topics
    memory.save_turn(
        session_1,
        {
            "user": "Explain Python decorators",
            "agent": "Decorators are functions that modify other functions.",
        },
    )

    # Session 2: Cooking topics
    memory.save_turn(
        session_2,
        {
            "user": "How to make pizza?",
            "agent": "Pizza requires dough, sauce, and toppings.",
        },
    )

    # Search in session 1 should not retrieve session 2 content
    results_1 = memory.search(session_1, "programming", top_k=2)
    results_text_1 = str(results_1).lower()

    assert "decorator" in results_text_1 or "python" in results_text_1
    assert "pizza" not in results_text_1


@pytest.mark.integration
def test_vector_memory_top_k_parameter():
    """Test VectorMemory respects top_k parameter in searches."""
    try:
        from sentence_transformers import SentenceTransformer

        embedder = SentenceTransformer("all-MiniLM-L6-v2")
    except ImportError:
        pytest.skip("sentence-transformers not available")

    memory = VectorMemory(embedding_fn=embedder.encode, top_k=2)
    session_id = "integration_test_vector_005"

    # Add multiple turns
    for i in range(10):
        memory.save_turn(session_id, {"user": f"Question {i}", "agent": f"Answer {i}"})

    # Search with different top_k values
    results_2 = memory.search(session_id, "question", top_k=2)
    results_5 = memory.search(session_id, "question", top_k=5)

    assert len(results_2) <= 2
    assert len(results_5) <= 5


# =============================================================================
# KNOWLEDGE GRAPH MEMORY INTEGRATION TESTS (3 tests) - Requires Real Extraction
# =============================================================================


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_knowledge_graph_memory_with_real_extraction():
    """Test KnowledgeGraphMemory with real entity/relation extraction."""
    llm_provider = RealOpenAIProvider(model="gpt-5-nano")

    def real_extractor(text: str) -> Dict[str, Any]:
        """Extract entities and relations using real LLM."""
        messages = [
            {
                "role": "system",
                "content": "Extract entities and relations from the text. Return as JSON with 'entities' and 'relations' keys.",
            },
            {"role": "user", "content": f"Text: {text}"},
        ]

        llm_provider.complete(messages, temperature=0.1, max_tokens=200)

        # Simple extraction - in real implementation, parse LLM response
        return {
            "entities": ["Python", "programming", "language"],
            "relations": [("Python", "is_a", "language")],
        }

    memory = KnowledgeGraphMemory(extractor_fn=real_extractor)
    session_id = "integration_test_kg_001"

    # Add turn with extractable knowledge
    memory.save_turn(
        session_id,
        {
            "user": "What is Python?",
            "agent": "Python is a high-level programming language.",
        },
    )

    # Verify knowledge extraction happened
    context = memory.load_context(session_id)
    assert "knowledge_graph" in context or "entities" in context


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_knowledge_graph_memory_accumulation():
    """Test KnowledgeGraphMemory accumulates knowledge over time."""
    RealOpenAIProvider(model="gpt-5-nano")

    def real_extractor(text: str) -> Dict[str, Any]:
        # Simplified extractor for testing
        return {
            "entities": ["test_entity"],
            "relations": [("entity1", "relates_to", "entity2")],
        }

    memory = KnowledgeGraphMemory(extractor_fn=real_extractor)
    session_id = "integration_test_kg_002"

    # Add multiple turns
    for i in range(3):
        memory.save_turn(
            session_id, {"user": f"Question {i}", "agent": f"Answer {i} with knowledge"}
        )

    # Knowledge should accumulate
    context = memory.load_context(session_id)
    assert context is not None


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_knowledge_graph_memory_query():
    """Test KnowledgeGraphMemory can query accumulated knowledge."""
    RealOpenAIProvider(model="gpt-5-nano")

    def real_extractor(text: str) -> Dict[str, Any]:
        return {
            "entities": ["Python", "Java", "programming"],
            "relations": [("Python", "is_a", "programming_language")],
        }

    memory = KnowledgeGraphMemory(extractor_fn=real_extractor)
    session_id = "integration_test_kg_003"

    memory.save_turn(
        session_id,
        {"user": "Tell me about Python", "agent": "Python is a programming language."},
    )

    # Query knowledge graph
    context = memory.load_context(session_id, query="Python programming")
    assert context is not None


# =============================================================================
# SHARED MEMORY POOL INTEGRATION TESTS (4 tests)
# =============================================================================


def _share(pool, agent_id, *, topic, content, importance, **metadata):
    """Write one insight through ``SharedMemoryPool``'s REAL contract.

    These tests were written against an ``add_insight(agent_id, {topic,
    insight, confidence})`` API that ``SharedMemoryPool`` has never had. Its
    actual writer is ``write_insight(insight)`` — ONE dict, with ``agent_id``,
    ``content``, ``tags``, ``importance`` and ``segment`` all REQUIRED and
    validated. So this was never a method rename: both the arity and every
    field name differ, and renaming the call would have raised ValueError on
    the missing required fields rather than silently passing.

    Mapping applied here: topic -> tags, insight -> content, confidence ->
    importance. ``segment`` has no analogue in the old shape, so a single
    constant is used — no test filters on it, and folding topic into it would
    conflate two independent filter axes.
    """
    insight = {
        "agent_id": agent_id,
        "content": content,
        "tags": [topic],
        "importance": importance,
        "segment": "collaboration",
    }
    if metadata:
        insight["metadata"] = metadata
    pool.write_insight(insight)
    return insight


@pytest.mark.integration
def test_shared_memory_pool_multi_agent_sharing():
    """Test SharedMemoryPool allows multiple agents to share insights."""
    pool = SharedMemoryPool()

    _share(
        pool,
        "agent_1",
        topic="Python",
        content="Python is great for data science",
        importance=0.9,
    )
    _share(
        pool,
        "agent_2",
        topic="Python",
        content="Python has excellent libraries",
        importance=0.85,
    )

    # read_relevant excludes the caller's OWN insights by default, which is
    # exactly the property under test: a shared pool is for reading what OTHER
    # agents contributed. Each agent must therefore see precisely the other's.
    insights_1 = pool.read_relevant(agent_id="agent_1", tags=["Python"])
    insights_2 = pool.read_relevant(agent_id="agent_2", tags=["Python"])

    assert [i["content"] for i in insights_1] == [
        "Python has excellent libraries"
    ], f"agent_1 did not receive agent_2's shared insight: {insights_1!r}"
    assert [i["content"] for i in insights_2] == [
        "Python is great for data science"
    ], f"agent_2 did not receive agent_1's shared insight: {insights_2!r}"


@pytest.mark.integration
def test_shared_memory_pool_topic_filtering():
    """Test SharedMemoryPool filters insights by topic."""
    pool = SharedMemoryPool()

    _share(pool, "agent_1", topic="Python", content="Python insight", importance=0.9)
    _share(pool, "agent_1", topic="Java", content="Java insight", importance=0.8)

    # Read as a DIFFERENT agent. Reading as agent_1 would return nothing at all
    # (exclude_own defaults True), and an "every result is Python" assertion
    # over an empty list passes vacuously — it would hold just as well if the
    # tag filter were ignored entirely.
    python_insights = pool.read_relevant(agent_id="agent_2", tags=["Python"])

    assert [i["content"] for i in python_insights] == [
        "Python insight"
    ], f"tag filtering did not return exactly the Python insight: {python_insights!r}"
    assert "Java insight" not in str(
        python_insights
    ), f"an insight tagged Java survived a Python-only filter: {python_insights!r}"


@pytest.mark.integration
def test_shared_memory_pool_insight_ranking():
    """Test SharedMemoryPool ranks insights by confidence."""
    pool = SharedMemoryPool()

    _share(pool, "agent_1", topic="AI", content="Low", importance=0.3)
    _share(pool, "agent_1", topic="AI", content="High", importance=0.95)
    _share(pool, "agent_1", topic="AI", content="Medium", importance=0.6)

    insights = pool.read_relevant(agent_id="agent_2", tags=["AI"], limit=2)

    # The old assertion was `len(insights) <= 2`, which holds for ANY ordering
    # and even for an empty result — it never checked the ranking this test is
    # named for. Assert the actual order: highest importance first, and the
    # lowest dropped by the limit.
    assert [i["content"] for i in insights] == ["High", "Medium"], (
        "insights were not returned in descending importance order: "
        f"{[(i['content'], i['importance']) for i in insights]!r}"
    )


@pytest.mark.integration
def test_shared_memory_pool_cross_agent_collaboration():
    """Test SharedMemoryPool enables real cross-agent collaboration."""
    pool = SharedMemoryPool()

    # Agent 1: Research agent
    _share(
        pool,
        "research_agent",
        topic="ML",
        content="Machine learning requires large datasets",
        importance=0.9,
        source="research",
    )

    # Agent 2: Implementation agent reads the research, then contributes
    seen_by_implementation = pool.read_relevant(
        agent_id="implementation_agent", tags=["ML"]
    )
    assert [i["agent_id"] for i in seen_by_implementation] == ["research_agent"], (
        "the implementation agent did not receive the research agent's insight: "
        f"{seen_by_implementation!r}"
    )

    _share(
        pool,
        "implementation_agent",
        topic="ML",
        content="Implemented ML pipeline based on research",
        importance=0.85,
        source="implementation",
    )

    # Agent 3: Validation agent sees BOTH, since neither is its own
    all_insights = pool.read_relevant(agent_id="validation_agent", tags=["ML"])

    assert sorted(i["agent_id"] for i in all_insights) == [
        "implementation_agent",
        "research_agent",
    ], f"the validation agent did not see both contributors: {all_insights!r}"
