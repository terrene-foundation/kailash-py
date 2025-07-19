"""
Unit tests for hybrid search functionality.
"""

import pytest
import numpy as np
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from kailash.nodes.ai.hybrid_search import (
    HybridSearchNode,
    AdaptiveSearchNode,
    TFIDFVectorizer,
    FuzzyMatcher,
    ContextualScorer,
    SearchContext,
    SearchResult,
)
from kailash.nodes.ai.a2a import (
    A2AAgentCard,
    CapabilityLevel,
    CollaborationStyle,
    Capability,
    PerformanceMetrics,
)


class TestTFIDFVectorizer:
    """Test TF-IDF vectorizer functionality."""

    def test_tokenize(self):
        """Test text tokenization."""
        vectorizer = TFIDFVectorizer()
        tokens = vectorizer._tokenize("The quick brown fox jumps over the lazy dog")

        # Should remove stop words and short tokens
        assert "the" not in tokens
        assert "quick" in tokens
        assert "brown" in tokens
        assert "fox" in tokens
        assert "jumps" in tokens
        assert "over" in tokens
        assert "lazy" in tokens
        assert "dog" in tokens

    def test_fit_and_transform(self):
        """Test fitting and transforming documents."""
        vectorizer = TFIDFVectorizer()
        documents = [
            "python programming code",
            "java programming software",
            "testing quality assurance",
        ]

        vectorizer.fit(documents)

        # Check vocabulary was built
        assert len(vectorizer.vocabulary) > 0
        assert "python" in vectorizer.vocabulary
        assert "programming" in vectorizer.vocabulary
        assert "testing" in vectorizer.vocabulary

        # Transform documents
        vectors = vectorizer.transform(documents)
        assert vectors.shape[0] == 3
        assert vectors.shape[1] == len(vectorizer.vocabulary)

    def test_cosine_similarity(self):
        """Test cosine similarity calculation."""
        vectorizer = TFIDFVectorizer()

        # Test identical vectors
        vec1 = np.array([1, 2, 3])
        vec2 = np.array([1, 2, 3])
        similarity = vectorizer.cosine_similarity(vec1, vec2)
        assert similarity == pytest.approx(1.0)

        # Test orthogonal vectors
        vec1 = np.array([1, 0, 0])
        vec2 = np.array([0, 1, 0])
        similarity = vectorizer.cosine_similarity(vec1, vec2)
        assert similarity == pytest.approx(0.0)

        # Test zero vectors
        vec1 = np.array([0, 0, 0])
        vec2 = np.array([1, 2, 3])
        similarity = vectorizer.cosine_similarity(vec1, vec2)
        assert similarity == 0.0


class TestFuzzyMatcher:
    """Test fuzzy matching functionality."""

    def test_expand_terms(self):
        """Test term expansion with synonyms."""
        matcher = FuzzyMatcher()

        terms = ["code", "test"]
        expanded = matcher.expand_terms(terms)

        assert "code" in expanded
        assert "coding" in expanded
        assert "programming" in expanded
        assert "test" in expanded
        assert "testing" in expanded
        assert "qa" in expanded

    def test_calculate_fuzzy_score(self):
        """Test fuzzy matching score calculation."""
        matcher = FuzzyMatcher()

        # Exact match
        score = matcher.calculate_fuzzy_score("python coding", "python coding")
        assert score == 1.0

        # Synonym match
        score = matcher.calculate_fuzzy_score("python coding", "python programming")
        assert score > 0.5

        # Partial match
        score = matcher.calculate_fuzzy_score("python testing", "java testing")
        assert 0.0 < score < 1.0

        # No match
        score = matcher.calculate_fuzzy_score("python", "java")
        assert score >= 0.0


class TestContextualScorer:
    """Test contextual scoring functionality."""

    def test_calculate_context_score(self):
        """Test context score calculation."""
        scorer = ContextualScorer()

        # Create test context
        context = SearchContext(
            task_history=[
                {"agent_id": "agent1", "success": True, "quality": 0.8},
                {"agent_id": "agent1", "success": True, "quality": 0.9},
            ],
            agent_performance={
                "agent1": {"success_rate": 0.9, "average_quality": 0.85}
            },
            recent_interactions={"agent1": datetime.now() - timedelta(days=1)},
            domain_expertise={"agent1": ["python", "testing", "automation"]},
            collaboration_patterns={
                "agent1": ["successful collaboration", "team player"]
            },
        )

        score, explanation = scorer.calculate_context_score(
            "agent1", ["python", "testing"], context
        )

        assert 0.0 <= score <= 1.0
        assert "task_success" in explanation
        assert "recency" in explanation
        assert "collaboration" in explanation
        assert "domain_expertise" in explanation

    def test_task_success_score(self):
        """Test task success score calculation."""
        scorer = ContextualScorer()
        context = SearchContext(
            agent_performance={"agent1": {"success_rate": 0.9, "average_quality": 0.8}}
        )

        score = scorer._calculate_task_success_score("agent1", context)
        expected = 0.9 * 0.7 + 0.8 * 0.3  # 0.63 + 0.24 = 0.87
        assert score == pytest.approx(expected)

    def test_recency_score(self):
        """Test recency score calculation."""
        scorer = ContextualScorer()

        # Recent interaction
        context = SearchContext(
            recent_interactions={"agent1": datetime.now() - timedelta(hours=1)}
        )
        score = scorer._calculate_recency_score("agent1", context)
        assert score == 1.0

        # Week old interaction
        context = SearchContext(
            recent_interactions={"agent1": datetime.now() - timedelta(days=7)}
        )
        score = scorer._calculate_recency_score("agent1", context)
        assert score == 0.8

        # No interaction history
        context = SearchContext()
        score = scorer._calculate_recency_score("agent1", context)
        assert score == 0.5


class TestSearchResult:
    """Test SearchResult functionality."""

    def test_search_result_creation(self):
        """Test creating a search result."""
        result = SearchResult(
            agent_id="agent1",
            agent_card=None,
            semantic_score=0.8,
            keyword_score=0.7,
            context_score=0.6,
            performance_score=0.9,
            combined_score=0.75,
            explanation={"test": "explanation"},
            confidence=0.85,
        )

        assert result.agent_id == "agent1"
        assert result.semantic_score == 0.8
        assert result.keyword_score == 0.7
        assert result.context_score == 0.6
        assert result.performance_score == 0.9
        assert result.combined_score == 0.75
        assert result.confidence == 0.85

    def test_search_result_to_dict(self):
        """Test converting search result to dictionary."""
        result = SearchResult(
            agent_id="agent1",
            agent_card=None,
            semantic_score=0.8,
            keyword_score=0.7,
            context_score=0.6,
            performance_score=0.9,
            combined_score=0.75,
            explanation={"test": "explanation"},
            confidence=0.85,
        )

        data = result.to_dict()

        assert data["agent_id"] == "agent1"
        assert data["semantic_score"] == 0.8
        assert data["keyword_score"] == 0.7
        assert data["context_score"] == 0.6
        assert data["performance_score"] == 0.9
        assert data["combined_score"] == 0.75
        assert data["confidence"] == 0.85
        assert data["explanation"] == {"test": "explanation"}


class TestHybridSearchNode:
    """Test HybridSearchNode functionality."""

    @pytest.mark.asyncio
    async def test_basic_search(self):
        """Test basic hybrid search functionality."""
        node = HybridSearchNode(name="test_search")

        requirements = ["python programming", "testing automation"]
        agents = [
            {
                "agent_id": "agent1",
                "description": "Python developer with testing experience",
            },
            {
                "agent_id": "agent2",
                "description": "Java developer with database skills",
            },
            {"agent_id": "agent3", "description": "Python testing specialist"},
        ]

        result = await node.run(requirements=requirements, agents=agents, limit=5)

        assert result["success"] is True
        assert result["search_type"] == "hybrid_enhanced"
        assert result["count"] >= 0
        assert len(result["results"]) >= 0
        assert "weights" in result
        assert "threshold" in result

        # Check result structure if we have results
        if result["results"]:
            first_result = result["results"][0]
            assert "agent_id" in first_result
            assert "semantic_score" in first_result
            assert "keyword_score" in first_result
            assert "context_score" in first_result
            assert "performance_score" in first_result
            assert "combined_score" in first_result
            assert "confidence" in first_result
            assert "explanation" in first_result

    @pytest.mark.asyncio
    async def test_search_with_agent_cards(self):
        """Test search with A2A agent cards."""
        node = HybridSearchNode(name="test_search")

        # Create agent cards
        agent_card = A2AAgentCard(
            agent_id="agent1",
            agent_name="Test Agent",
            agent_type="coding",
            version="1.0.0",
            description="Python development specialist",
            primary_capabilities=[
                Capability(
                    name="python_development",
                    domain="programming",
                    level=CapabilityLevel.EXPERT,
                    description="Expert Python programmer",
                )
            ],
            tags=["python", "programming", "backend"],
        )

        requirements = ["python development"]
        agents = [agent_card.to_dict()]

        result = await node.run(requirements=requirements, agents=agents)

        assert result["success"] is True
        assert result["count"] >= 0

    @pytest.mark.asyncio
    async def test_search_with_context(self):
        """Test search with context information."""
        node = HybridSearchNode(name="test_search")

        requirements = ["python testing"]
        agents = [
            {"agent_id": "agent1", "description": "Python tester"},
            {"agent_id": "agent2", "description": "Java developer"},
        ]

        context = {
            "agent_performance": {
                "agent1": {"success_rate": 0.9, "average_quality": 0.8}
            },
            "recent_interactions": {"agent1": datetime.now().isoformat()},
            "domain_expertise": {"agent1": ["python", "testing"]},
        }

        result = await node.run(
            requirements=requirements, agents=agents, context=context
        )

        assert result["success"] is True
        assert result["count"] >= 0

    @pytest.mark.asyncio
    async def test_search_missing_requirements(self):
        """Test error when requirements are missing."""
        node = HybridSearchNode(name="test_search")

        with pytest.raises(ValueError, match="Requirements and agents are required"):
            await node.run(agents=["agent1"])

    @pytest.mark.asyncio
    async def test_search_missing_agents(self):
        """Test error when agents are missing."""
        node = HybridSearchNode(name="test_search")

        with pytest.raises(ValueError, match="Requirements and agents are required"):
            await node.run(requirements=["python"])

    def test_get_parameters(self):
        """Test getting node parameters."""
        node = HybridSearchNode(name="test_search")
        parameters = node.get_parameters()

        param_names = list(parameters.keys())
        assert "requirements" in param_names
        assert "agents" in param_names
        assert "context" in param_names
        assert "limit" in param_names
        assert "semantic_weight" in param_names
        assert "keyword_weight" in param_names
        assert "context_weight" in param_names
        assert "performance_weight" in param_names
        assert "min_threshold" in param_names

    def test_create_agent_text(self):
        """Test creating searchable text from agent card."""
        node = HybridSearchNode(name="test_search")

        agent_card = A2AAgentCard(
            agent_id="agent1",
            agent_name="Test Agent",
            agent_type="coding",
            version="1.0.0",
            description="Python specialist",
            primary_capabilities=[
                Capability(
                    name="python_coding",
                    domain="programming",
                    level=CapabilityLevel.EXPERT,
                    description="Expert Python programmer",
                )
            ],
            tags=["python", "backend"],
        )

        text = node._create_agent_text(agent_card)

        assert "Test Agent" in text
        assert "Python specialist" in text
        assert "python" in text
        assert "backend" in text
        assert "python_coding" in text
        assert "programming" in text

    def test_get_agent_id(self):
        """Test getting agent ID from different agent formats."""
        node = HybridSearchNode(name="test_search")

        # Dict with agent_id
        agent_id = node._get_agent_id({"agent_id": "test_agent"}, 0)
        assert agent_id == "test_agent"

        # Dict without agent_id
        agent_id = node._get_agent_id({"name": "test"}, 0)
        assert agent_id == "agent_0"

        # String
        agent_id = node._get_agent_id("test_agent", 0)
        assert agent_id == "agent_0"

    def test_calculate_confidence(self):
        """Test confidence calculation."""
        node = HybridSearchNode(name="test_search")

        # High agreement should give high confidence
        confidence = node._calculate_confidence(0.8, 0.8, 0.8, 0.8)
        assert confidence > 0.8

        # Low agreement should give low confidence
        confidence = node._calculate_confidence(0.1, 0.9, 0.2, 0.8)
        assert confidence < 0.7  # Adjusted expectation

        # High scores should boost confidence
        confidence = node._calculate_confidence(0.9, 0.9, 0.9, 0.9)
        assert confidence > 0.9


class TestAdaptiveSearchNode:
    """Test AdaptiveSearchNode functionality."""

    @pytest.mark.asyncio
    async def test_adaptive_search_basic(self):
        """Test basic adaptive search functionality."""
        node = AdaptiveSearchNode(name="adaptive_search")

        requirements = ["python programming"]
        agents = [
            {"agent_id": "agent1", "description": "Python developer"},
            {"agent_id": "agent2", "description": "Java developer"},
        ]

        result = await node.run(requirements=requirements, agents=agents)

        assert result["success"] is True
        assert result["learning_enabled"] is True
        assert "adaptive_weights" in result
        assert "search_history_size" in result

        # Check adaptive weights
        weights = result["adaptive_weights"]
        assert "semantic" in weights
        assert "keyword" in weights
        assert "context" in weights
        assert "performance" in weights

    @pytest.mark.asyncio
    async def test_adaptive_search_with_feedback(self):
        """Test adaptive search with feedback learning."""
        node = AdaptiveSearchNode(name="adaptive_search")

        # Create feedback history
        feedback_history = [
            {
                "success": 0.8,
                "component_scores": {
                    "semantic": 0.9,
                    "keyword": 0.7,
                    "context": 0.6,
                    "performance": 0.8,
                },
            },
            {
                "success": 0.9,
                "component_scores": {
                    "semantic": 0.8,
                    "keyword": 0.9,
                    "context": 0.7,
                    "performance": 0.9,
                },
            },
        ]

        # Store initial weights
        initial_weights = {
            "semantic": node.semantic_weight,
            "keyword": node.keyword_weight,
            "context": node.context_weight,
            "performance": node.performance_weight,
        }

        requirements = ["python programming"]
        agents = [{"agent_id": "agent1", "description": "Python developer"}]

        result = await node.run(
            requirements=requirements, agents=agents, feedback_history=feedback_history
        )

        assert result["success"] is True

        # Check that weights have been adapted
        final_weights = result["adaptive_weights"]

        # Weights should have changed (at least some of them)
        weight_changes = [
            abs(final_weights["semantic"] - initial_weights["semantic"]),
            abs(final_weights["keyword"] - initial_weights["keyword"]),
            abs(final_weights["context"] - initial_weights["context"]),
            abs(final_weights["performance"] - initial_weights["performance"]),
        ]

        assert max(weight_changes) > 0.0  # At least one weight should have changed

    def test_learn_from_feedback(self):
        """Test learning from feedback."""
        node = AdaptiveSearchNode(name="adaptive_search")

        # Store initial weights
        initial_semantic = node.semantic_weight
        initial_keyword = node.keyword_weight

        feedback_history = [
            {
                "success": 1.0,
                "component_scores": {
                    "semantic": 0.9,
                    "keyword": 0.5,
                    "context": 0.6,
                    "performance": 0.7,
                },
            }
        ]

        node._learn_from_feedback(feedback_history)

        # Semantic should be boosted, keyword should be reduced
        assert node.semantic_weight >= initial_semantic
        assert node.keyword_weight <= initial_keyword

        # Weights should sum to approximately 1
        total_weight = (
            node.semantic_weight
            + node.keyword_weight
            + node.context_weight
            + node.performance_weight
        )
        assert total_weight == pytest.approx(1.0, abs=0.01)

    def test_store_search_history(self):
        """Test storing search history."""
        node = AdaptiveSearchNode(name="adaptive_search")

        requirements = ["python programming"]
        agents = [{"agent_id": "agent1"}]
        result = {"count": 1, "success": True}

        initial_history_size = len(node.search_history)

        node._store_search_history(requirements, agents, result)

        assert len(node.search_history) == initial_history_size + 1
        assert len(node.weight_history) == initial_history_size + 1

        # Check stored record
        last_record = node.search_history[-1]
        assert last_record["requirements"] == requirements
        assert last_record["agent_count"] == 1
        assert last_record["result_count"] == 1
        assert "weights" in last_record
        assert "timestamp" in last_record

    def test_get_parameters(self):
        """Test getting adaptive search node parameters."""
        node = AdaptiveSearchNode(name="adaptive_search")
        parameters = node.get_parameters()

        param_names = list(parameters.keys())
        assert "requirements" in param_names
        assert "agents" in param_names
        assert "feedback_history" in param_names
        assert "adaptation_rate" in param_names
        assert "memory_window" in param_names
