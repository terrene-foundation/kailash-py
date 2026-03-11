"""
Tier 3 E2E Tests: Complete RAG Research Workflow with Real Infrastructure.

Tests complete RAG (Retrieval-Augmented Generation) workflows end-to-end with
REAL LLMs, REAL embeddings, and REAL semantic search. NO MOCKING ALLOWED.

Test Coverage:
- Complete research workflow (3 tests)
- Semantic search workflow (2 tests)

Total: 5 E2E tests
"""

import os
import sys
from pathlib import Path

import pytest

# Real LLM providers

# =============================================================================
# COMPLETE RESEARCH WORKFLOW E2E TESTS (3 tests)
# =============================================================================


@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_complete_rag_research_workflow():
    """Test complete RAG research workflow end-to-end with real embeddings."""
    try:
        from sentence_transformers import SentenceTransformer

        embedder = SentenceTransformer("all-MiniLM-L6-v2")
    except ImportError:
        pytest.skip("sentence-transformers not available")

    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/rag-research"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import RAGConfig, RAGResearchAgent

        config = RAGConfig(
            llm_provider="openai",
            model="gpt-5-nano",
            temperature=0.1,
            max_tokens=400,
            memory_config={"enabled": True, "embedder": embedder.encode, "top_k": 5},
        )

        agent = RAGResearchAgent(config)
        session_id = "e2e_rag_001"

        # Complete research workflow
        # Phase 1: Build knowledge base
        knowledge_base = [
            "Python is a high-level programming language created by Guido van Rossum.",
            "Python is widely used in data science, web development, and automation.",
            "Python has a simple syntax that emphasizes readability and reduces code complexity.",
            "Popular Python frameworks include Django for web and TensorFlow for machine learning.",
            "Python's extensive standard library provides built-in modules for many tasks.",
        ]

        for fact in knowledge_base:
            agent.research(fact, session_id=session_id)

        # Phase 2: Research queries leveraging RAG
        research_queries = [
            {
                "query": "Who created Python?",
                "expected_keywords": ["guido", "van rossum", "creator"],
            },
            {
                "query": "What is Python used for?",
                "expected_keywords": [
                    "data science",
                    "web",
                    "automation",
                    "development",
                ],
            },
            {
                "query": "What makes Python easy to learn?",
                "expected_keywords": ["syntax", "readable", "simple"],
            },
        ]

        for query_case in research_queries:
            result = agent.research(query_case["query"], session_id=session_id)

            # Verify RAG retrieval worked
            assert result is not None
            assert "findings" in result or "answer" in result

            # Check if response leverages retrieved knowledge
            response_text = result.get("findings", result.get("answer", "")).lower()

            # Should mention at least one expected keyword
            keywords_found = any(
                kw in response_text for kw in query_case["expected_keywords"]
            )
            assert (
                keywords_found
            ), f"Expected one of {query_case['expected_keywords']} in response to '{query_case['query']}'"

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_rag_workflow_incremental_knowledge_building():
    """Test RAG workflow builds knowledge incrementally (E2E)."""
    try:
        from sentence_transformers import SentenceTransformer

        embedder = SentenceTransformer("all-MiniLM-L6-v2")
    except ImportError:
        pytest.skip("sentence-transformers not available")

    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/rag-research"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import RAGConfig, RAGResearchAgent

        config = RAGConfig(
            llm_provider="openai",
            model="gpt-5-nano",
            temperature=0.1,
            max_tokens=400,
            memory_config={"enabled": True, "embedder": embedder.encode, "top_k": 3},
        )

        agent = RAGResearchAgent(config)
        session_id = "e2e_rag_incremental_001"

        # Incremental knowledge building workflow
        # Step 1: Basic concept
        result_1 = agent.research(
            "Machine learning is a subset of AI.", session_id=session_id
        )
        assert result_1 is not None

        # Step 2: Add related concept
        result_2 = agent.research("What is machine learning?", session_id=session_id)
        assert (
            "ai" in result_2.get("findings", result_2.get("answer", "")).lower()
            or "artificial"
            in result_2.get("findings", result_2.get("answer", "")).lower()
        )

        # Step 3: Add specific detail
        agent.research(
            "Deep learning uses neural networks for machine learning.",
            session_id=session_id,
        )

        # Step 4: Query should synthesize all knowledge
        result_4 = agent.research(
            "Explain the relationship between AI, ML, and deep learning.",
            session_id=session_id,
        )

        response = result_4.get("findings", result_4.get("answer", "")).lower()

        # Should synthesize concepts from knowledge base
        concepts_mentioned = sum(
            [
                "machine learning" in response or "ml" in response,
                "ai" in response or "artificial" in response,
                "deep learning" in response or "neural" in response,
            ]
        )

        assert (
            concepts_mentioned >= 2
        ), "Should synthesize multiple concepts from knowledge base"

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_rag_workflow_multi_domain_research():
    """Test RAG workflow handles multi-domain research (E2E)."""
    try:
        from sentence_transformers import SentenceTransformer

        embedder = SentenceTransformer("all-MiniLM-L6-v2")
    except ImportError:
        pytest.skip("sentence-transformers not available")

    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/rag-research"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import RAGConfig, RAGResearchAgent

        config = RAGConfig(
            llm_provider="openai",
            model="gpt-5-nano",
            temperature=0.1,
            max_tokens=400,
            memory_config={"enabled": True, "embedder": embedder.encode, "top_k": 5},
        )

        agent = RAGResearchAgent(config)
        session_id = "e2e_rag_multi_domain_001"

        # Multi-domain knowledge base
        domains = {
            "programming": [
                "Python is excellent for rapid prototyping and scripting.",
                "JavaScript is the language of the web and runs in browsers.",
            ],
            "science": [
                "Quantum computing uses qubits instead of classical bits.",
                "DNA sequencing has revolutionized genomics research.",
            ],
            "business": [
                "Agile methodology emphasizes iterative development.",
                "KPIs help measure business performance.",
            ],
        }

        # Build multi-domain knowledge
        for domain, facts in domains.items():
            for fact in facts:
                agent.research(fact, session_id=session_id)

        # Query each domain - RAG should retrieve relevant context
        domain_queries = [
            {
                "query": "Tell me about programming languages",
                "expected_domain": "programming",
                "keywords": ["python", "javascript", "programming"],
            },
            {
                "query": "What do you know about scientific computing?",
                "expected_domain": "science",
                "keywords": ["quantum", "dna", "research", "science"],
            },
            {
                "query": "Explain business methodologies",
                "expected_domain": "business",
                "keywords": ["agile", "kpi", "business", "performance"],
            },
        ]

        for query_case in domain_queries:
            result = agent.research(query_case["query"], session_id=session_id)
            response = result.get("findings", result.get("answer", "")).lower()

            # Should retrieve relevant domain knowledge
            domain_match = any(kw in response for kw in query_case["keywords"])
            assert (
                domain_match
            ), f"Expected domain-specific keywords {query_case['keywords']} for query '{query_case['query']}'"

    finally:
        sys.path.remove(str(example_path))


# =============================================================================
# SEMANTIC SEARCH WORKFLOW E2E TESTS (2 tests)
# =============================================================================


@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_rag_semantic_search_accuracy():
    """Test RAG semantic search retrieves semantically similar content (E2E)."""
    try:
        from sentence_transformers import SentenceTransformer

        embedder = SentenceTransformer("all-MiniLM-L6-v2")
    except ImportError:
        pytest.skip("sentence-transformers not available")

    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/rag-research"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import RAGConfig, RAGResearchAgent

        config = RAGConfig(
            llm_provider="openai",
            model="gpt-5-nano",
            temperature=0.1,
            max_tokens=400,
            memory_config={"enabled": True, "embedder": embedder.encode, "top_k": 3},
        )

        agent = RAGResearchAgent(config)
        session_id = "e2e_rag_semantic_001"

        # Diverse knowledge base
        knowledge = [
            "The Eiffel Tower is located in Paris, France.",
            "Python is a popular programming language for data science.",
            "The Pacific Ocean is the largest ocean on Earth.",
            "Machine learning algorithms can identify patterns in data.",
            "The Great Wall of China is visible from space.",
            "Neural networks are inspired by the human brain.",
        ]

        for fact in knowledge:
            agent.research(fact, session_id=session_id)

        # Semantic search tests
        semantic_tests = [
            {
                "query": "Tell me about coding and software",
                "should_retrieve": [
                    "python",
                    "programming",
                    "machine learning",
                    "algorithms",
                    "neural networks",
                ],
                "should_not_retrieve": ["eiffel tower", "ocean", "great wall"],
            },
            {
                "query": "What famous landmarks do you know?",
                "should_retrieve": ["eiffel tower", "great wall", "paris", "china"],
                "should_not_retrieve": [
                    "python",
                    "machine learning",
                    "neural networks",
                ],
            },
        ]

        for test_case in semantic_tests:
            result = agent.research(test_case["query"], session_id=session_id)
            response = result.get("findings", result.get("answer", "")).lower()

            # Should retrieve semantically similar content
            retrieved_count = sum(
                1 for item in test_case["should_retrieve"] if item in response
            )

            # Should NOT retrieve semantically dissimilar content
            not_retrieved_count = sum(
                1 for item in test_case["should_not_retrieve"] if item in response
            )

            # More relevant content should be retrieved than irrelevant
            assert (
                retrieved_count > not_retrieved_count
            ), f"Semantic search should prioritize relevant content for query '{test_case['query']}'"

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_rag_semantic_search_top_k_ranking():
    """Test RAG semantic search ranks results by relevance (E2E)."""
    try:
        from sentence_transformers import SentenceTransformer

        embedder = SentenceTransformer("all-MiniLM-L6-v2")
    except ImportError:
        pytest.skip("sentence-transformers not available")

    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/rag-research"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import RAGConfig, RAGResearchAgent

        config = RAGConfig(
            llm_provider="openai",
            model="gpt-5-nano",
            temperature=0.1,
            max_tokens=400,
            memory_config={
                "enabled": True,
                "embedder": embedder.encode,
                "top_k": 2,  # Only top 2 results
            },
        )

        agent = RAGResearchAgent(config)
        session_id = "e2e_rag_ranking_001"

        # Knowledge with varying relevance to target query
        knowledge = [
            "Python is widely used in data analysis and scientific computing.",  # Most relevant
            "Python supports object-oriented and functional programming paradigms.",  # Highly relevant
            "Python was created by Guido van Rossum in 1991.",  # Moderately relevant
            "Many companies use Python for web development with Django.",  # Less relevant to data science
            "The Python community is very active and helpful.",  # Least relevant to data science
        ]

        for fact in knowledge:
            agent.research(fact, session_id=session_id)

        # Query targeting data science specifically
        result = agent.research(
            "How is Python used in data science and analysis?", session_id=session_id
        )

        response = result.get("findings", result.get("answer", "")).lower()

        # With top_k=2, should retrieve most relevant facts
        # Most relevant: data analysis, scientific computing
        highly_relevant_count = sum(
            [
                "data analysis" in response or "data" in response,
                "scientific" in response or "analysis" in response,
            ]
        )

        # Less relevant facts should appear less frequently
        less_relevant_count = sum(
            ["1991" in response, "django" in response, "community" in response]
        )

        # Should prioritize highly relevant content
        assert (
            highly_relevant_count >= less_relevant_count
        ), "Top-k ranking should prioritize most relevant results"

    finally:
        sys.path.remove(str(example_path))
