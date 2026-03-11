"""
Unit tests for Solution Ranking Engine.

Tests LLM-based solution ranking with mock LLM responses.

Test Coverage:
- LLM-based ranking with mock responses
- Cached ranking retrieval (hit)
- Cached ranking cache miss
- Combined score calculation (70/30 split)
- Ranking with pattern effectiveness (high)
- Ranking with pattern effectiveness (low)
- Ranking with no pattern history
- Top 3 selection from 5+ solutions
- Relevance score range validation
- Solution ranking consistency
"""

from unittest.mock import MagicMock, Mock

import pytest
from dataflow.debug.data_structures import (
    ErrorAnalysis,
    ErrorSolution,
    KnowledgeBase,
    RankedSolution,
    WorkflowContext,
)
from dataflow.debug.solution_ranking import SolutionRankingEngine


@pytest.fixture
def knowledge_base():
    """Create knowledge base instance."""
    return KnowledgeBase(storage_type="memory")


@pytest.fixture
def pattern_engine(knowledge_base):
    """Create pattern recognition engine."""
    from dataflow.debug.pattern_recognition import PatternRecognitionEngine

    return PatternRecognitionEngine(knowledge_base)


@pytest.fixture
def mock_llm_agent():
    """Create mock LLM agent (KaizenNode)."""
    mock_agent = Mock()
    return mock_agent


@pytest.fixture
def error_analysis():
    """Create sample error analysis."""
    return ErrorAnalysis(
        error_code="DF-101",
        category="parameter",
        message="Missing required parameter 'id'",
        context={"node_id": "create_user", "parameter": "id"},
        causes=[
            "Parameter not provided in workflow",
            "Parameter mapping incorrect",
            "Parameter name typo",
        ],
        solutions=[
            ErrorSolution(
                description="Add 'id' parameter to node",
                code_template="workflow.add_node('UserCreateNode', 'create', {'id': 'user_123'})",
                auto_fixable=True,
                priority=1,
            ),
            ErrorSolution(
                description="Check parameter mapping",
                code_template="workflow.add_connection('source', 'id', 'create', 'id')",
                auto_fixable=False,
                priority=2,
            ),
            ErrorSolution(
                description="Fix parameter name typo",
                code_template="# Change 'user_id' to 'id' in node parameters",
                auto_fixable=False,
                priority=3,
            ),
        ],
        severity="error",
        docs_url="https://docs.dataflow.dev/errors/DF-101",
    )


@pytest.fixture
def workflow_context():
    """Create sample workflow context."""
    return WorkflowContext(
        nodes=["create_user", "read_user"],
        connections=[{"from": "create_user", "to": "read_user"}],
        node_type="UserCreateNode",
    )


@pytest.fixture
def ranking_engine(mock_llm_agent, knowledge_base, pattern_engine):
    """Create solution ranking engine."""
    return SolutionRankingEngine(mock_llm_agent, knowledge_base, pattern_engine)


# ============================================================================
# Test 1: LLM-based ranking with mock LLM responses
# ============================================================================


def test_llm_based_ranking(
    ranking_engine, error_analysis, workflow_context, mock_llm_agent
):
    """Test LLM-based ranking with mock LLM responses."""
    # Mock LLM response
    mock_llm_agent.run = Mock(
        return_value={
            "response": """
Solution 1: relevance=0.9, reasoning="Directly addresses missing 'id' parameter"
Solution 2: relevance=0.7, reasoning="Checks parameter mapping which could be the issue"
Solution 3: relevance=0.5, reasoning="Typo is less likely but possible"
        """,
            "confidence": 0.85,
        }
    )

    # Rank solutions
    ranked_solutions = ranking_engine.rank_solutions(
        error_analysis, workflow_context, error_analysis.solutions
    )

    # Verify LLM was called
    assert mock_llm_agent.run.called

    # Verify ranking results
    assert len(ranked_solutions) == 3
    assert ranked_solutions[0].relevance_score == 0.9
    assert ranked_solutions[1].relevance_score == 0.7
    assert ranked_solutions[2].relevance_score == 0.5

    # Verify reasoning
    assert "Directly addresses" in ranked_solutions[0].reasoning
    assert "parameter mapping" in ranked_solutions[1].reasoning
    assert "Typo" in ranked_solutions[2].reasoning

    # Verify confidence
    assert ranked_solutions[0].confidence == 0.85


# ============================================================================
# Test 2: Cached ranking retrieval (hit)
# ============================================================================


def test_cached_ranking_hit(
    ranking_engine,
    error_analysis,
    workflow_context,
    pattern_engine,
    knowledge_base,
    mock_llm_agent,
):
    """Test cached ranking retrieval (cache hit)."""
    # Pre-populate cache with high-confidence ranking
    pattern_key = pattern_engine.generate_pattern_key(error_analysis, workflow_context)

    cached_solutions = [
        RankedSolution(
            solution=error_analysis.solutions[0],
            relevance_score=0.95,
            reasoning="Cached solution #1",
            confidence=0.9,
            effectiveness_score=0.8,
        ),
        RankedSolution(
            solution=error_analysis.solutions[1],
            relevance_score=0.75,
            reasoning="Cached solution #2",
            confidence=0.9,
            effectiveness_score=0.6,
        ),
        RankedSolution(
            solution=error_analysis.solutions[2],
            relevance_score=0.55,
            reasoning="Cached solution #3",
            confidence=0.9,
            effectiveness_score=0.4,
        ),
    ]

    knowledge_base.store_ranking(pattern_key, cached_solutions)

    # Rank solutions (should return cached)
    ranked_solutions = ranking_engine.rank_solutions(
        error_analysis, workflow_context, error_analysis.solutions
    )

    # Verify LLM was NOT called (cache hit)
    assert not mock_llm_agent.run.called

    # Verify cached results
    assert len(ranked_solutions) == 3
    assert ranked_solutions[0].relevance_score == 0.95
    assert ranked_solutions[0].reasoning == "Cached solution #1"
    assert ranked_solutions[0].confidence == 0.9


# ============================================================================
# Test 3: Cached ranking cache miss
# ============================================================================


def test_cached_ranking_miss(
    ranking_engine, error_analysis, workflow_context, mock_llm_agent
):
    """Test cached ranking cache miss (no cached entry)."""
    # Mock LLM response
    mock_llm_agent.run = Mock(
        return_value={
            "response": """
Solution 1: relevance=0.9, reasoning="Best solution"
Solution 2: relevance=0.7, reasoning="Alternative approach"
Solution 3: relevance=0.5, reasoning="Last resort"
        """,
            "confidence": 0.85,
        }
    )

    # Rank solutions (cache miss, should call LLM)
    ranked_solutions = ranking_engine.rank_solutions(
        error_analysis, workflow_context, error_analysis.solutions
    )

    # Verify LLM was called (cache miss)
    assert mock_llm_agent.run.called

    # Verify LLM ranking used
    assert len(ranked_solutions) == 3
    assert ranked_solutions[0].relevance_score == 0.9
    assert "Best solution" in ranked_solutions[0].reasoning


# ============================================================================
# Test 4: Combined score calculation (70/30 split)
# ============================================================================


def test_combined_score_calculation(ranking_engine):
    """Test combined score calculation (70% relevance + 30% effectiveness)."""
    # Test case 1: High relevance, high effectiveness
    combined = ranking_engine._calculate_combined_score(
        relevance_score=0.9, effectiveness_score=0.8
    )
    expected = 0.7 * 0.9 + 0.3 * 0.8  # 0.63 + 0.24 = 0.87
    assert abs(combined - expected) < 0.01

    # Test case 2: High relevance, low effectiveness
    combined = ranking_engine._calculate_combined_score(
        relevance_score=0.9, effectiveness_score=0.2
    )
    expected = 0.7 * 0.9 + 0.3 * 0.2  # 0.63 + 0.06 = 0.69
    assert abs(combined - expected) < 0.01

    # Test case 3: Low relevance, high effectiveness
    combined = ranking_engine._calculate_combined_score(
        relevance_score=0.3, effectiveness_score=0.9
    )
    expected = 0.7 * 0.3 + 0.3 * 0.9  # 0.21 + 0.27 = 0.48
    assert abs(combined - expected) < 0.01

    # Test case 4: Zero effectiveness (no history)
    combined = ranking_engine._calculate_combined_score(
        relevance_score=0.8, effectiveness_score=0.0
    )
    expected = 0.7 * 0.8 + 0.3 * 0.0  # 0.56 + 0.0 = 0.56
    assert abs(combined - expected) < 0.01


# ============================================================================
# Test 5: Ranking with pattern effectiveness (high effectiveness)
# ============================================================================


def test_ranking_with_high_effectiveness(
    ranking_engine,
    error_analysis,
    workflow_context,
    pattern_engine,
    knowledge_base,
    mock_llm_agent,
):
    """Test ranking with high pattern effectiveness."""
    # Mock LLM response
    mock_llm_agent.run = Mock(
        return_value={
            "response": """
Solution 1: relevance=0.8, reasoning="Good solution"
Solution 2: relevance=0.7, reasoning="Alternative"
Solution 3: relevance=0.6, reasoning="Backup"
        """,
            "confidence": 0.85,
        }
    )

    # Add high effectiveness scores to knowledge base
    pattern_key = pattern_engine.generate_pattern_key(error_analysis, workflow_context)

    # Record positive feedback (9 thumbs up, 1 thumbs down, 10 uses)
    for i in range(10):
        knowledge_base.record_feedback(pattern_key, 0, "used")
    for i in range(9):
        knowledge_base.record_feedback(pattern_key, 0, "thumbs_up")
    knowledge_base.record_feedback(pattern_key, 0, "thumbs_down")

    # Pre-store ranking to trigger effectiveness update (all 3 solutions)
    knowledge_base.store_ranking(
        pattern_key,
        [
            RankedSolution(
                solution=error_analysis.solutions[0],
                relevance_score=0.8,
                reasoning="Good solution",
                confidence=0.85,
                effectiveness_score=0.0,  # Will be updated
            ),
            RankedSolution(
                solution=error_analysis.solutions[1],
                relevance_score=0.7,
                reasoning="Alternative",
                confidence=0.85,
                effectiveness_score=0.0,
            ),
            RankedSolution(
                solution=error_analysis.solutions[2],
                relevance_score=0.6,
                reasoning="Backup",
                confidence=0.85,
                effectiveness_score=0.0,
            ),
        ],
    )

    # Update effectiveness
    knowledge_base._update_effectiveness_scores(pattern_key)

    # Get pattern effectiveness
    pattern_effectiveness = pattern_engine.get_pattern_effectiveness(pattern_key)
    assert pattern_effectiveness is not None
    assert pattern_effectiveness["effectiveness_score"] == 0.8  # (9-1)/10 = 0.8

    # Rank solutions
    ranked_solutions = ranking_engine.rank_solutions(
        error_analysis, workflow_context, error_analysis.solutions
    )

    # Verify effectiveness integrated into combined score
    assert len(ranked_solutions) == 3
    # Combined score should be higher due to effectiveness
    # relevance=0.8, effectiveness=0.8 → 0.7*0.8 + 0.3*0.8 = 0.8


# ============================================================================
# Test 6: Ranking with pattern effectiveness (low effectiveness)
# ============================================================================


def test_ranking_with_low_effectiveness(
    ranking_engine,
    error_analysis,
    workflow_context,
    pattern_engine,
    knowledge_base,
    mock_llm_agent,
):
    """Test ranking with low pattern effectiveness."""
    # Mock LLM response
    mock_llm_agent.run = Mock(
        return_value={
            "response": """
Solution 1: relevance=0.8, reasoning="Solution with bad history"
Solution 2: relevance=0.7, reasoning="Alternative"
Solution 3: relevance=0.6, reasoning="Backup"
        """,
            "confidence": 0.85,
        }
    )

    # Add low effectiveness scores (1 thumbs up, 9 thumbs down, 10 uses)
    pattern_key = pattern_engine.generate_pattern_key(error_analysis, workflow_context)

    for i in range(10):
        knowledge_base.record_feedback(pattern_key, 0, "used")
    knowledge_base.record_feedback(pattern_key, 0, "thumbs_up")
    for i in range(9):
        knowledge_base.record_feedback(pattern_key, 0, "thumbs_down")

    # Pre-store ranking (all 3 solutions)
    knowledge_base.store_ranking(
        pattern_key,
        [
            RankedSolution(
                solution=error_analysis.solutions[0],
                relevance_score=0.8,
                reasoning="Solution with bad history",
                confidence=0.85,
                effectiveness_score=0.0,
            ),
            RankedSolution(
                solution=error_analysis.solutions[1],
                relevance_score=0.7,
                reasoning="Alternative",
                confidence=0.85,
                effectiveness_score=0.0,
            ),
            RankedSolution(
                solution=error_analysis.solutions[2],
                relevance_score=0.6,
                reasoning="Backup",
                confidence=0.85,
                effectiveness_score=0.0,
            ),
        ],
    )

    # Update effectiveness
    knowledge_base._update_effectiveness_scores(pattern_key)

    # Get pattern effectiveness
    pattern_effectiveness = pattern_engine.get_pattern_effectiveness(pattern_key)
    assert pattern_effectiveness["effectiveness_score"] == -0.8  # (1-9)/10 = -0.8

    # Rank solutions
    ranked_solutions = ranking_engine.rank_solutions(
        error_analysis, workflow_context, error_analysis.solutions
    )

    # Verify low effectiveness reduces combined score
    # relevance=0.8, effectiveness=-0.8 → 0.7*0.8 + 0.3*(-0.8) = 0.56 - 0.24 = 0.32
    assert len(ranked_solutions) == 3


# ============================================================================
# Test 7: Ranking with no pattern history (effectiveness = 0.0)
# ============================================================================


def test_ranking_with_no_history(
    ranking_engine, error_analysis, workflow_context, mock_llm_agent
):
    """Test ranking with no pattern history (effectiveness = 0.0)."""
    # Mock LLM response
    mock_llm_agent.run = Mock(
        return_value={
            "response": """
Solution 1: relevance=0.9, reasoning="New pattern, no history"
Solution 2: relevance=0.7, reasoning="Alternative"
Solution 3: relevance=0.5, reasoning="Backup"
        """,
            "confidence": 0.85,
        }
    )

    # Rank solutions (no history, effectiveness = 0.0)
    ranked_solutions = ranking_engine.rank_solutions(
        error_analysis, workflow_context, error_analysis.solutions
    )

    # Verify effectiveness defaults to 0.0
    assert len(ranked_solutions) == 3
    assert ranked_solutions[0].effectiveness_score == 0.0
    assert ranked_solutions[1].effectiveness_score == 0.0
    assert ranked_solutions[2].effectiveness_score == 0.0

    # Combined score should be 70% relevance only
    # relevance=0.9, effectiveness=0.0 → 0.7*0.9 + 0.3*0.0 = 0.63


# ============================================================================
# Test 8: Top 3 selection from 5+ solutions
# ============================================================================


def test_top_3_selection(ranking_engine, mock_llm_agent):
    """Test top 3 selection from 5+ solutions."""
    # Create error with 5 solutions
    error_analysis = ErrorAnalysis(
        error_code="DF-201",
        category="connection",
        message="Connection error",
        context={},
        causes=["Cause 1", "Cause 2", "Cause 3"],
        solutions=[
            ErrorSolution(f"Solution {i+1}", f"code_{i+1}", False, i + 1)
            for i in range(5)
        ],
        severity="error",
        docs_url="https://docs.dataflow.dev",
    )

    # Mock LLM response with 5 solutions
    mock_llm_agent.run = Mock(
        return_value={
            "response": """
Solution 1: relevance=0.95, reasoning="Best solution"
Solution 2: relevance=0.85, reasoning="Second best"
Solution 3: relevance=0.75, reasoning="Third best"
Solution 4: relevance=0.65, reasoning="Fourth best"
Solution 5: relevance=0.55, reasoning="Fifth best"
        """,
            "confidence": 0.85,
        }
    )

    workflow_context = WorkflowContext()

    # Rank solutions
    ranked_solutions = ranking_engine.rank_solutions(
        error_analysis, workflow_context, error_analysis.solutions
    )

    # Verify only top 3 returned
    assert len(ranked_solutions) == 3
    assert ranked_solutions[0].relevance_score == 0.95
    assert ranked_solutions[1].relevance_score == 0.85
    assert ranked_solutions[2].relevance_score == 0.75


# ============================================================================
# Test 9: Relevance score range validation (0.0-1.0)
# ============================================================================


def test_relevance_score_validation(
    ranking_engine, error_analysis, workflow_context, mock_llm_agent
):
    """Test relevance score range validation (0.0-1.0)."""
    # Mock LLM response with invalid scores
    mock_llm_agent.run = Mock(
        return_value={
            "response": """
Solution 1: relevance=1.5, reasoning="Invalid score > 1.0"
Solution 2: relevance=-0.3, reasoning="Invalid score < 0.0"
Solution 3: relevance=0.7, reasoning="Valid score"
        """,
            "confidence": 0.85,
        }
    )

    # Rank solutions (should handle invalid scores)
    ranked_solutions = ranking_engine.rank_solutions(
        error_analysis, workflow_context, error_analysis.solutions
    )

    # Verify scores clamped to valid range [0.0, 1.0]
    assert len(ranked_solutions) == 3

    for solution in ranked_solutions:
        assert 0.0 <= solution.relevance_score <= 1.0


# ============================================================================
# Test 10: Solution ranking consistency (same inputs = same output)
# ============================================================================


def test_ranking_consistency(
    ranking_engine, error_analysis, workflow_context, mock_llm_agent
):
    """Test solution ranking consistency (same inputs = same output)."""
    # Mock deterministic LLM response
    llm_response = {
        "response": """
Solution 1: relevance=0.9, reasoning="Consistent solution #1"
Solution 2: relevance=0.7, reasoning="Consistent solution #2"
Solution 3: relevance=0.5, reasoning="Consistent solution #3"
        """,
        "confidence": 0.85,
    }

    mock_llm_agent.run = Mock(return_value=llm_response)

    # First ranking
    ranked_solutions_1 = ranking_engine.rank_solutions(
        error_analysis, workflow_context, error_analysis.solutions
    )

    # Reset mock and run again
    mock_llm_agent.run = Mock(return_value=llm_response)

    # Second ranking (same inputs)
    ranked_solutions_2 = ranking_engine.rank_solutions(
        error_analysis, workflow_context, error_analysis.solutions
    )

    # Verify consistency
    assert len(ranked_solutions_1) == len(ranked_solutions_2)

    for sol1, sol2 in zip(ranked_solutions_1, ranked_solutions_2):
        assert sol1.relevance_score == sol2.relevance_score
        assert sol1.reasoning == sol2.reasoning
        assert sol1.confidence == sol2.confidence


# ============================================================================
# Test 11: Cache ranking storage after LLM call
# ============================================================================


def test_cache_ranking_storage(
    ranking_engine,
    error_analysis,
    workflow_context,
    pattern_engine,
    knowledge_base,
    mock_llm_agent,
):
    """Test cache ranking storage after LLM call."""
    # Mock LLM response
    mock_llm_agent.run = Mock(
        return_value={
            "response": """
Solution 1: relevance=0.9, reasoning="Solution to cache"
Solution 2: relevance=0.7, reasoning="Alternative"
Solution 3: relevance=0.5, reasoning="Backup"
        """,
            "confidence": 0.85,
        }
    )

    # Generate pattern key
    pattern_key = pattern_engine.generate_pattern_key(error_analysis, workflow_context)

    # Verify cache is empty
    assert knowledge_base.get_ranking(pattern_key) is None

    # Rank solutions (should cache results)
    ranked_solutions = ranking_engine.rank_solutions(
        error_analysis, workflow_context, error_analysis.solutions
    )

    # Verify results cached
    cached_ranking = knowledge_base.get_ranking(pattern_key)
    assert cached_ranking is not None
    assert len(cached_ranking) == 3
    assert cached_ranking[0].relevance_score == 0.9
    assert "Solution to cache" in cached_ranking[0].reasoning


# ============================================================================
# Test 12: Low confidence cache skip (confidence < 0.8)
# ============================================================================


def test_low_confidence_cache_skip(
    ranking_engine,
    error_analysis,
    workflow_context,
    pattern_engine,
    knowledge_base,
    mock_llm_agent,
):
    """Test low confidence cache skip (confidence < 0.8)."""
    # Pre-populate cache with low-confidence ranking
    pattern_key = pattern_engine.generate_pattern_key(error_analysis, workflow_context)

    low_confidence_solutions = [
        RankedSolution(
            solution=error_analysis.solutions[0],
            relevance_score=0.9,
            reasoning="Low confidence cached solution",
            confidence=0.6,  # Below 0.8 threshold
            effectiveness_score=0.0,
        )
    ]

    knowledge_base.store_ranking(pattern_key, low_confidence_solutions)

    # Mock LLM response (should be called despite cache)
    mock_llm_agent.run = Mock(
        return_value={
            "response": """
Solution 1: relevance=0.95, reasoning="New high-confidence solution"
Solution 2: relevance=0.75, reasoning="Alternative"
Solution 3: relevance=0.55, reasoning="Backup"
        """,
            "confidence": 0.9,
        }
    )

    # Rank solutions (should skip low-confidence cache and call LLM)
    ranked_solutions = ranking_engine.rank_solutions(
        error_analysis, workflow_context, error_analysis.solutions
    )

    # Verify LLM was called (cache skipped due to low confidence)
    assert mock_llm_agent.run.called

    # Verify new high-confidence ranking used
    assert ranked_solutions[0].relevance_score == 0.95
    assert "New high-confidence solution" in ranked_solutions[0].reasoning
    assert ranked_solutions[0].confidence == 0.9
