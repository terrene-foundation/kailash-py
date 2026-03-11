"""
Unit tests for PatternRecognitionEngine (Week 10 Task 4.3).

Tests pattern key generation, match score calculation, similarity finding,
and effectiveness retrieval from Knowledge Base.

Test Coverage:
- Pattern key generation (basic, with category, with full context)
- Match score calculation (exact, category, similar, different)
- Find similar patterns (exact match, partial matches, no match)
- Get pattern effectiveness (with feedback, no feedback)
"""

import pytest
from dataflow.debug.data_structures import (
    ErrorAnalysis,
    ErrorSolution,
    KnowledgeBase,
    NodeInfo,
    RankedSolution,
    WorkflowContext,
)
from dataflow.debug.pattern_recognition import PatternRecognitionEngine


@pytest.fixture
def knowledge_base():
    """Create KnowledgeBase instance for testing."""
    return KnowledgeBase(storage_type="memory")


@pytest.fixture
def pattern_engine(knowledge_base):
    """Create PatternRecognitionEngine instance for testing."""
    return PatternRecognitionEngine(knowledge_base)


@pytest.fixture
def sample_error_analysis():
    """Create sample ErrorAnalysis for testing."""
    return ErrorAnalysis(
        error_code="DF-101",
        category="parameter",
        message="Missing required parameter 'id'",
        context={
            "node_id": "create_user",
            "parameter": "id",
            "node_type": "UserCreateNode",
        },
        causes=[
            "Parameter not provided in node configuration",
            "Upstream connection missing",
            "Parameter name typo",
        ],
        solutions=[
            ErrorSolution(
                description="Add missing parameter to node",
                code_template="workflow.add_node('UserCreateNode', 'create', {'id': 'user_123'})",
                auto_fixable=False,
                priority=1,
            )
        ],
        severity="error",
        docs_url="https://docs.dataflow.dev/errors/DF-101",
    )


@pytest.fixture
def sample_workflow_context():
    """Create sample WorkflowContext for testing."""
    return WorkflowContext(
        nodes=["create_user", "read_user"],
        connections=[{"from": "create_user", "to": "read_user"}],
        node_type="UserCreateNode",
        node_metadata=NodeInfo(
            node_id="create_user",
            node_type="UserCreateNode",
            model_name="User",
            expected_params={"id": "str", "name": "str"},
            output_params={"id": "str", "name": "str"},
            connections_in=[],
            connections_out=[{"from": "create_user", "to": "read_user"}],
        ),
    )


# ============================================================================
# Test Pattern Key Generation
# ============================================================================


def test_generate_pattern_key_basic(pattern_engine, sample_error_analysis):
    """Test pattern key generation with error_code only."""
    # No workflow context - should generate key from error_code only
    key = pattern_engine.generate_pattern_key(sample_error_analysis, None)

    # Pattern key should be error_code
    assert key == "DF-101"
    assert isinstance(key, str)
    assert key.startswith("DF-")


def test_generate_pattern_key_with_category(pattern_engine, sample_error_analysis):
    """Test pattern key generation with category from context."""
    # Empty workflow context - should add category
    context = WorkflowContext()
    key = pattern_engine.generate_pattern_key(sample_error_analysis, context)

    # Pattern key should include category
    assert "DF-101" in key
    assert "parameter" in key
    assert isinstance(key, str)


def test_generate_pattern_key_with_node_type(
    pattern_engine, sample_error_analysis, sample_workflow_context
):
    """Test pattern key generation with node_type from context."""
    key = pattern_engine.generate_pattern_key(
        sample_error_analysis, sample_workflow_context
    )

    # Pattern key should include error_code, category, and node_type
    assert "DF-101" in key
    assert "parameter" in key
    assert "UserCreateNode" in key
    assert isinstance(key, str)


def test_generate_pattern_key_with_full_context(pattern_engine):
    """Test pattern key generation with full context details."""
    error = ErrorAnalysis(
        error_code="DF-201",
        category="connection",
        message="Connection type mismatch",
        context={
            "node_id": "process_data",
            "parameter": "data",
            "from_node": "read_user",
            "to_node": "process_data",
            "node_type": "PythonCodeNode",
        },
        causes=["Type mismatch between nodes"],
        solutions=[
            ErrorSolution(
                description="Add type conversion",
                code_template="...",
                auto_fixable=False,
                priority=1,
            )
        ],
        severity="error",
        docs_url="https://docs.dataflow.dev/errors/DF-201",
    )

    context = WorkflowContext(node_type="PythonCodeNode")
    key = pattern_engine.generate_pattern_key(error, context)

    # Should include error_code, category, and node_type
    assert "DF-201" in key
    assert "connection" in key
    assert "PythonCodeNode" in key


def test_generate_pattern_key_consistency(
    pattern_engine, sample_error_analysis, sample_workflow_context
):
    """Test pattern key generation is consistent for same inputs."""
    key1 = pattern_engine.generate_pattern_key(
        sample_error_analysis, sample_workflow_context
    )
    key2 = pattern_engine.generate_pattern_key(
        sample_error_analysis, sample_workflow_context
    )

    # Same inputs should generate same key
    assert key1 == key2


def test_generate_pattern_key_different_contexts(pattern_engine, sample_error_analysis):
    """Test pattern key generation differs for different contexts."""
    context1 = WorkflowContext(node_type="UserCreateNode")
    context2 = WorkflowContext(node_type="UserUpdateNode")

    key1 = pattern_engine.generate_pattern_key(sample_error_analysis, context1)
    key2 = pattern_engine.generate_pattern_key(sample_error_analysis, context2)

    # Different contexts should generate different keys
    assert key1 != key2


# ============================================================================
# Test Match Score Calculation
# ============================================================================


def test_calculate_match_score_exact(pattern_engine, sample_error_analysis):
    """Test match score calculation for exact error code match."""
    error1 = sample_error_analysis
    error2 = ErrorAnalysis(
        error_code="DF-101",  # Same error code
        category="parameter",
        message="Missing required parameter 'name'",
        context={"node_id": "create_user", "parameter": "name"},
        causes=["Parameter not provided"],
        solutions=[
            ErrorSolution(
                description="Add parameter",
                code_template="...",
                auto_fixable=False,
                priority=1,
            )
        ],
        severity="error",
        docs_url="https://docs.dataflow.dev/errors/DF-101",
    )

    score = pattern_engine.calculate_match_score(error1, error2)

    # Exact error code match should return 1.0
    assert score == 1.0
    assert isinstance(score, float)


def test_calculate_match_score_category(pattern_engine, sample_error_analysis):
    """Test match score calculation for same category match."""
    error1 = sample_error_analysis  # DF-101, parameter
    error2 = ErrorAnalysis(
        error_code="DF-102",  # Different error code
        category="parameter",  # Same category
        message="Invalid parameter type",
        context={"node_id": "create_user", "parameter": "id"},
        causes=["Type mismatch"],
        solutions=[
            ErrorSolution(
                description="Fix type",
                code_template="...",
                auto_fixable=False,
                priority=1,
            )
        ],
        severity="error",
        docs_url="https://docs.dataflow.dev/errors/DF-102",
    )

    score = pattern_engine.calculate_match_score(error1, error2)

    # Same category should return 0.7
    assert score == 0.7
    assert isinstance(score, float)


def test_calculate_match_score_similar_context(pattern_engine, sample_error_analysis):
    """Test match score calculation for similar context match."""
    error1 = sample_error_analysis  # DF-101, parameter
    error2 = ErrorAnalysis(
        error_code="DF-201",  # Different error code
        category="connection",  # Different category
        message="Connection missing",
        context={
            "node_id": "create_user",  # Same node_id
            "parameter": "id",  # Same parameter
        },
        causes=["Connection not found"],
        solutions=[
            ErrorSolution(
                description="Add connection",
                code_template="...",
                auto_fixable=False,
                priority=1,
            )
        ],
        severity="error",
        docs_url="https://docs.dataflow.dev/errors/DF-201",
    )

    score = pattern_engine.calculate_match_score(error1, error2)

    # Similar context should return 0.5
    assert score == 0.5
    assert isinstance(score, float)


def test_calculate_match_score_different(pattern_engine, sample_error_analysis):
    """Test match score calculation for completely different errors."""
    error1 = sample_error_analysis  # DF-101, parameter
    error2 = ErrorAnalysis(
        error_code="DF-301",  # Different error code
        category="migration",  # Different category
        message="Migration failed",
        context={"table": "users"},  # Different context
        causes=["Schema conflict"],
        solutions=[
            ErrorSolution(
                description="Fix schema",
                code_template="...",
                auto_fixable=False,
                priority=1,
            )
        ],
        severity="error",
        docs_url="https://docs.dataflow.dev/errors/DF-301",
    )

    score = pattern_engine.calculate_match_score(error1, error2)

    # Different errors should return 0.0
    assert score == 0.0
    assert isinstance(score, float)


def test_calculate_match_score_symmetry(pattern_engine, sample_error_analysis):
    """Test match score is symmetric (score(A,B) == score(B,A))."""
    error1 = sample_error_analysis
    error2 = ErrorAnalysis(
        error_code="DF-102",
        category="parameter",
        message="Different error",
        context={},
        causes=["Cause"],
        solutions=[
            ErrorSolution(
                description="Solution",
                code_template="...",
                auto_fixable=False,
                priority=1,
            )
        ],
        severity="error",
        docs_url="https://docs.dataflow.dev/errors/DF-102",
    )

    score1 = pattern_engine.calculate_match_score(error1, error2)
    score2 = pattern_engine.calculate_match_score(error2, error1)

    # Match score should be symmetric
    assert score1 == score2


def test_calculate_match_score_range(pattern_engine, sample_error_analysis):
    """Test match score is always between 0.0 and 1.0."""
    error2 = ErrorAnalysis(
        error_code="DF-999",
        category="unknown",
        message="Unknown error",
        context={},
        causes=["Unknown"],
        solutions=[
            ErrorSolution(
                description="Fix", code_template="...", auto_fixable=False, priority=1
            )
        ],
        severity="error",
        docs_url="https://docs.dataflow.dev/errors/DF-999",
    )

    score = pattern_engine.calculate_match_score(sample_error_analysis, error2)

    # Score should be in range [0.0, 1.0]
    assert 0.0 <= score <= 1.0


# ============================================================================
# Test Find Similar Patterns
# ============================================================================


def test_find_similar_patterns_exact_match(
    pattern_engine, knowledge_base, sample_error_analysis
):
    """Test finding exact matching pattern from Knowledge Base."""
    # Store pattern in knowledge base
    pattern_key = "DF-101:parameter:UserCreateNode"
    ranked_solutions = [
        RankedSolution(
            solution=ErrorSolution(
                description="Add missing parameter",
                code_template="workflow.add_node('UserCreateNode', 'create', {'id': 'user_123'})",
                auto_fixable=False,
                priority=1,
            ),
            relevance_score=0.9,
            reasoning="Exact match for missing parameter error",
            confidence=0.95,
            effectiveness_score=0.8,
        )
    ]
    knowledge_base.store_ranking(pattern_key, ranked_solutions)

    # Find similar patterns
    results = pattern_engine.find_similar_patterns(sample_error_analysis)

    # Should find exact match
    assert len(results) > 0
    assert results[0]["pattern_key"] == pattern_key
    assert results[0]["match_score"] == 1.0
    assert results[0]["solutions"] == ranked_solutions


def test_find_similar_patterns_partial_matches(pattern_engine, knowledge_base):
    """Test finding partial matching patterns sorted by score."""
    # Store multiple patterns with different scores
    patterns = [
        ("DF-101:parameter:UserCreateNode", 1.0),  # Exact match
        ("DF-101:parameter:UserUpdateNode", 0.9),  # Same error+category, different node
        ("DF-102:parameter:UserCreateNode", 0.7),  # Same category, different error
        (
            "DF-201:connection:UserCreateNode",
            0.5,
        ),  # Different category, similar context
    ]

    for pattern_key, _ in patterns:
        ranked_solutions = [
            RankedSolution(
                solution=ErrorSolution(
                    description=f"Solution for {pattern_key}",
                    code_template="...",
                    auto_fixable=False,
                    priority=1,
                ),
                relevance_score=0.8,
                reasoning="Test solution",
                confidence=0.9,
                effectiveness_score=0.0,
            )
        ]
        knowledge_base.store_ranking(pattern_key, ranked_solutions)

    # Create error analysis
    error = ErrorAnalysis(
        error_code="DF-101",
        category="parameter",
        message="Missing parameter",
        context={"node_type": "UserCreateNode"},
        causes=["Missing parameter"],
        solutions=[
            ErrorSolution(
                description="Add parameter",
                code_template="...",
                auto_fixable=False,
                priority=1,
            )
        ],
        severity="error",
        docs_url="https://docs.dataflow.dev/errors/DF-101",
    )

    # Find similar patterns
    results = pattern_engine.find_similar_patterns(error)

    # Should find all patterns sorted by match score (descending)
    assert len(results) > 0

    # Check sorting: scores should be descending
    scores = [r["match_score"] for r in results]
    assert scores == sorted(scores, reverse=True)

    # Check top match has highest score
    assert results[0]["match_score"] >= results[-1]["match_score"]


def test_find_similar_patterns_no_match(
    pattern_engine, knowledge_base, sample_error_analysis
):
    """Test finding patterns when no matches exist."""
    # Knowledge base is empty - no patterns stored

    # Find similar patterns
    results = pattern_engine.find_similar_patterns(sample_error_analysis)

    # Should return empty list
    assert len(results) == 0
    assert isinstance(results, list)


def test_find_similar_patterns_filters_zero_score(pattern_engine, knowledge_base):
    """Test finding patterns filters out zero match scores."""
    # Store patterns with different categories (score 0.0)
    patterns = [
        ("DF-301:migration:UserCreateNode", 0.0),  # Different category
        ("DF-401:configuration:UserCreateNode", 0.0),  # Different category
    ]

    for pattern_key, _ in patterns:
        ranked_solutions = [
            RankedSolution(
                solution=ErrorSolution(
                    description=f"Solution for {pattern_key}",
                    code_template="...",
                    auto_fixable=False,
                    priority=1,
                ),
                relevance_score=0.8,
                reasoning="Test solution",
                confidence=0.9,
                effectiveness_score=0.0,
            )
        ]
        knowledge_base.store_ranking(pattern_key, ranked_solutions)

    # Create parameter error
    error = ErrorAnalysis(
        error_code="DF-101",
        category="parameter",
        message="Missing parameter",
        context={},
        causes=["Missing parameter"],
        solutions=[
            ErrorSolution(
                description="Add parameter",
                code_template="...",
                auto_fixable=False,
                priority=1,
            )
        ],
        severity="error",
        docs_url="https://docs.dataflow.dev/errors/DF-101",
    )

    # Find similar patterns
    results = pattern_engine.find_similar_patterns(error)

    # Should filter out zero-score matches
    assert len(results) == 0


def test_find_similar_patterns_limit(pattern_engine, knowledge_base):
    """Test finding patterns respects result limit."""
    # Store 10 patterns
    for i in range(10):
        pattern_key = f"DF-10{i}:parameter:UserCreateNode"
        ranked_solutions = [
            RankedSolution(
                solution=ErrorSolution(
                    description=f"Solution {i}",
                    code_template="...",
                    auto_fixable=False,
                    priority=1,
                ),
                relevance_score=0.8,
                reasoning="Test solution",
                confidence=0.9,
                effectiveness_score=0.0,
            )
        ]
        knowledge_base.store_ranking(pattern_key, ranked_solutions)

    # Create error
    error = ErrorAnalysis(
        error_code="DF-101",
        category="parameter",
        message="Missing parameter",
        context={},
        causes=["Missing parameter"],
        solutions=[
            ErrorSolution(
                description="Add parameter",
                code_template="...",
                auto_fixable=False,
                priority=1,
            )
        ],
        severity="error",
        docs_url="https://docs.dataflow.dev/errors/DF-101",
    )

    # Find similar patterns with limit
    results = pattern_engine.find_similar_patterns(error, limit=5)

    # Should return top 5 matches
    assert len(results) <= 5


# ============================================================================
# Test Get Pattern Effectiveness
# ============================================================================


def test_get_pattern_effectiveness_with_feedback(pattern_engine, knowledge_base):
    """Test retrieving pattern effectiveness with feedback data."""
    pattern_key = "DF-101:parameter:UserCreateNode"

    # Store pattern
    ranked_solutions = [
        RankedSolution(
            solution=ErrorSolution(
                description="Solution 1",
                code_template="...",
                auto_fixable=False,
                priority=1,
            ),
            relevance_score=0.9,
            reasoning="Test",
            confidence=0.9,
            effectiveness_score=0.0,
        )
    ]
    knowledge_base.store_ranking(pattern_key, ranked_solutions)

    # Record feedback
    knowledge_base.record_feedback(pattern_key, 0, "used")
    knowledge_base.record_feedback(pattern_key, 0, "thumbs_up")
    knowledge_base.record_feedback(pattern_key, 0, "thumbs_up")

    # Get effectiveness
    effectiveness = pattern_engine.get_pattern_effectiveness(pattern_key)

    # Should return effectiveness score
    assert effectiveness is not None
    assert isinstance(effectiveness, dict)
    assert "effectiveness_score" in effectiveness
    assert "feedback" in effectiveness
    assert effectiveness["effectiveness_score"] > 0.0  # 2 thumbs_up, 1 used = positive
    assert effectiveness["feedback"]["used"] == 1
    assert effectiveness["feedback"]["thumbs_up"] == 2


def test_get_pattern_effectiveness_no_feedback(pattern_engine, knowledge_base):
    """Test retrieving pattern effectiveness with no feedback data."""
    pattern_key = "DF-101:parameter:UserCreateNode"

    # Store pattern without feedback
    ranked_solutions = [
        RankedSolution(
            solution=ErrorSolution(
                description="Solution 1",
                code_template="...",
                auto_fixable=False,
                priority=1,
            ),
            relevance_score=0.9,
            reasoning="Test",
            confidence=0.9,
            effectiveness_score=0.0,
        )
    ]
    knowledge_base.store_ranking(pattern_key, ranked_solutions)

    # Get effectiveness
    effectiveness = pattern_engine.get_pattern_effectiveness(pattern_key)

    # Should return zero effectiveness
    assert effectiveness is not None
    assert effectiveness["effectiveness_score"] == 0.0
    assert effectiveness["feedback"]["used"] == 0
    assert effectiveness["feedback"]["thumbs_up"] == 0
    assert effectiveness["feedback"]["thumbs_down"] == 0


def test_get_pattern_effectiveness_pattern_not_found(pattern_engine, knowledge_base):
    """Test retrieving effectiveness for non-existent pattern."""
    pattern_key = "DF-999:unknown:UnknownNode"

    # Get effectiveness for non-existent pattern
    effectiveness = pattern_engine.get_pattern_effectiveness(pattern_key)

    # Should return None or default values
    assert effectiveness is None or effectiveness["effectiveness_score"] == 0.0


def test_get_pattern_effectiveness_negative_score(pattern_engine, knowledge_base):
    """Test retrieving pattern effectiveness with negative feedback."""
    pattern_key = "DF-101:parameter:UserCreateNode"

    # Store pattern
    ranked_solutions = [
        RankedSolution(
            solution=ErrorSolution(
                description="Solution 1",
                code_template="...",
                auto_fixable=False,
                priority=1,
            ),
            relevance_score=0.9,
            reasoning="Test",
            confidence=0.9,
            effectiveness_score=0.0,
        )
    ]
    knowledge_base.store_ranking(pattern_key, ranked_solutions)

    # Record negative feedback
    knowledge_base.record_feedback(pattern_key, 0, "used")
    knowledge_base.record_feedback(pattern_key, 0, "thumbs_down")
    knowledge_base.record_feedback(pattern_key, 0, "thumbs_down")

    # Get effectiveness
    effectiveness = pattern_engine.get_pattern_effectiveness(pattern_key)

    # Should return negative effectiveness score
    assert effectiveness is not None
    assert (
        effectiveness["effectiveness_score"] < 0.0
    )  # 2 thumbs_down, 1 used = negative
    assert effectiveness["feedback"]["thumbs_down"] == 2


def test_get_pattern_effectiveness_mixed_feedback(pattern_engine, knowledge_base):
    """Test retrieving pattern effectiveness with mixed feedback."""
    pattern_key = "DF-101:parameter:UserCreateNode"

    # Store pattern
    ranked_solutions = [
        RankedSolution(
            solution=ErrorSolution(
                description="Solution 1",
                code_template="...",
                auto_fixable=False,
                priority=1,
            ),
            relevance_score=0.9,
            reasoning="Test",
            confidence=0.9,
            effectiveness_score=0.0,
        )
    ]
    knowledge_base.store_ranking(pattern_key, ranked_solutions)

    # Record mixed feedback
    knowledge_base.record_feedback(pattern_key, 0, "used")
    knowledge_base.record_feedback(pattern_key, 0, "thumbs_up")
    knowledge_base.record_feedback(pattern_key, 0, "thumbs_down")

    # Get effectiveness
    effectiveness = pattern_engine.get_pattern_effectiveness(pattern_key)

    # Should return balanced effectiveness score (close to 0.0)
    assert effectiveness is not None
    assert -0.1 <= effectiveness["effectiveness_score"] <= 0.1  # 1 up, 1 down = ~0
    assert effectiveness["feedback"]["thumbs_up"] == 1
    assert effectiveness["feedback"]["thumbs_down"] == 1
