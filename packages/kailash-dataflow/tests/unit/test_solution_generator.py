"""Unit tests for solution generator component.

Tests the SolutionGenerator solution matching engine with mocked KnowledgeBase
to ensure accurate relevance scoring and solution customization.
"""

from unittest.mock import Mock

import pytest
from dataflow.debug.analysis_result import AnalysisResult
from dataflow.debug.error_categorizer import ErrorCategory
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.debug.solution_generator import SolutionGenerator
from dataflow.debug.suggested_solution import SuggestedSolution


@pytest.fixture
def mock_knowledge_base():
    """Create mock KnowledgeBase with standard test solutions."""
    kb = Mock(spec=KnowledgeBase)

    # Mock solution for parameter error
    mock_param_solution = {
        "id": "SOL_001",
        "title": "Add Missing 'id' Parameter to CreateNode",
        "category": "QUICK_FIX",
        "description": "Add required 'id' field to CREATE operation",
        "code_example": 'workflow.add_node("UserCreateNode", "create", {"id": "user-123", "name": "Alice"})',
        "explanation": "The 'id' field is required for all CREATE operations in DataFlow...",
        "references": ["https://docs.dataflow.dev/nodes/create"],
        "difficulty": "easy",
        "estimated_time": 1,
    }

    # Mock solution for connection error
    mock_conn_solution = {
        "id": "SOL_015",
        "title": "Fix Connection Source Node Typo",
        "category": "QUICK_FIX",
        "description": "Correct typo in source node name",
        "code_example": 'workflow.add_connection("user_create", "id", "user_read", "id")  # Fixed typo',
        "explanation": "The source node 'usr_create' has a typo. Use 'user_create' instead.",
        "references": ["https://docs.dataflow.dev/connections"],
        "difficulty": "easy",
        "estimated_time": 1,
    }

    # Mock pattern with related solutions
    mock_param_pattern = {
        "name": "Missing Required Parameter 'id'",
        "category": "PARAMETER",
        "related_solutions": ["SOL_001"],
    }

    mock_conn_pattern = {
        "name": "Connection Source Node Not Found",
        "category": "CONNECTION",
        "related_solutions": ["SOL_015"],
    }

    # Configure mocks
    kb.get_pattern = Mock(
        side_effect=lambda pid: (
            mock_param_pattern if pid == "PARAM_001" else mock_conn_pattern
        )
    )
    kb.get_solutions_for_pattern = Mock(
        side_effect=lambda pid: (
            [mock_param_solution] if pid == "PARAM_001" else [mock_conn_solution]
        )
    )

    return kb


@pytest.fixture
def generator(mock_knowledge_base):
    """Create SolutionGenerator with mock KnowledgeBase."""
    return SolutionGenerator(mock_knowledge_base)


def test_generate_solutions_parameter_error(generator):
    """Test solution generation for parameter error."""
    analysis = AnalysisResult(
        root_cause="Node 'create_user' is missing required parameter 'id'",
        affected_nodes=["create_user"],
        affected_connections=[],
        affected_models=["User"],
        context_data={
            "node_type": "UserCreateNode",
            "model_name": "User",
            "missing_parameter": "id",
            "is_primary_key": True,
        },
    )

    category = ErrorCategory(
        category="PARAMETER", pattern_id="PARAM_001", confidence=0.9, features={}
    )

    solutions = generator.generate_solutions(analysis, category)

    # Verify solutions returned
    assert len(solutions) > 0
    assert isinstance(solutions[0], SuggestedSolution)

    # Verify relevance score
    assert solutions[0].relevance_score >= 0.3

    # Verify solution content
    assert "id" in solutions[0].code_example
    assert (
        "UserCreateNode" in solutions[0].code_example
        or "user" in solutions[0].code_example.lower()
    )


def test_generate_solutions_connection_error(generator):
    """Test solution generation for connection error."""
    analysis = AnalysisResult(
        root_cause="Connection references non-existent node 'usr_create'",
        affected_nodes=["user_read"],
        affected_connections=["usr_create → user_read"],
        affected_models=[],
        context_data={
            "source_node": "usr_create",
            "target_node": "user_read",
            "missing_node": "usr_create",
            "available_nodes": ["user_create", "user_read"],
            "similar_nodes": [("user_create", 0.9)],
        },
    )

    category = ErrorCategory(
        category="CONNECTION", pattern_id="CONN_001", confidence=0.85, features={}
    )

    solutions = generator.generate_solutions(analysis, category)

    # Verify solutions returned
    assert len(solutions) > 0
    assert isinstance(solutions[0], SuggestedSolution)

    # Verify relevance score (should be high for typo fixes)
    assert solutions[0].relevance_score >= 0.3


def test_calculate_relevance_score(generator):
    """Test relevance score calculation."""
    solution = {
        "title": "Add Missing 'id' Parameter to CreateNode",
        "category": "QUICK_FIX",
        "description": "Add required 'id' field to UserCreateNode",
        "code_example": 'workflow.add_node("UserCreateNode", "create", {"id": "value"})',
    }

    analysis = AnalysisResult(
        root_cause="Missing parameter 'id'",
        affected_nodes=["UserCreateNode"],
        affected_models=["User"],
        context_data={"missing_parameter": "id", "model_name": "User"},
    )

    category = ErrorCategory(
        category="PARAMETER", pattern_id="PARAM_001", confidence=0.9, features={}
    )

    score = generator._calculate_relevance_score(solution, analysis, category)

    # Verify score is in valid range
    assert 0.0 <= score <= 1.0

    # Verify score is high (good match)
    assert score >= 0.5  # Should be high relevance


def test_calculate_relevance_score_low_match(generator):
    """Test relevance score with poor context match."""
    solution = {
        "title": "Configure Database Connection Pool",
        "category": "CONFIGURATION",
        "description": "Adjust pool size settings",
        "code_example": "db = DataFlow(url, pool_size=20)",
    }

    analysis = AnalysisResult(
        root_cause="Missing parameter 'id'",
        affected_nodes=["UserCreateNode"],
        affected_models=["User"],
        context_data={"missing_parameter": "id"},
    )

    category = ErrorCategory(
        category="PARAMETER", pattern_id="PARAM_001", confidence=0.9, features={}
    )

    score = generator._calculate_relevance_score(solution, analysis, category)

    # Verify score is in valid range
    assert 0.0 <= score <= 1.0

    # Verify score is lower (poor match)
    assert score < 0.7


def test_customize_solution(generator):
    """Test solution customization with error context."""
    solution = {
        "code_example": 'workflow.add_node("${node_type}", "create", {"${parameter_name}": "value", "name": "Alice"})',
        "explanation": "Add missing parameter ${parameter_name} to ${node_type}",
        "description": "Fix ${node_type} by adding ${parameter_name}",
    }

    analysis = AnalysisResult(
        root_cause="Missing parameter",
        affected_nodes=[],
        affected_connections=[],
        affected_models=[],
        context_data={
            "missing_parameter": "id",
            "node_type": "UserCreateNode",
            "model_name": "User",
        },
    )

    customized = generator._customize_solution(solution, analysis, "SOL_001")

    # Verify placeholders replaced in code_example
    assert "${parameter_name}" not in customized["code_example"]
    assert "${node_type}" not in customized["code_example"]
    assert "id" in customized["code_example"]
    assert "UserCreateNode" in customized["code_example"]

    # Verify placeholders replaced in explanation
    assert "${parameter_name}" not in customized["explanation"]
    assert "${node_type}" not in customized["explanation"]
    assert "id" in customized["explanation"]

    # Verify placeholders replaced in description
    assert "${parameter_name}" not in customized["description"]


def test_filter_parameter_solutions(generator):
    """Test PARAMETER solution filtering."""
    solutions = [
        (
            "SOL_001",
            {
                "title": "Add Missing 'id' Parameter",
                "description": "Add id field to CreateNode",
            },
            0.7,
        ),
        (
            "SOL_002",
            {
                "title": "Fix Database Connection",
                "description": "Configure pool settings",
            },
            0.6,
        ),
    ]

    analysis = AnalysisResult(
        root_cause="Missing parameter 'id'",
        affected_nodes=[],
        affected_connections=[],
        affected_models=[],
        context_data={"missing_parameter": "id", "is_primary_key": True},
    )

    filtered = generator._filter_parameter_solutions(solutions, analysis)

    # Verify filtering occurred
    assert len(filtered) == 2

    # Verify score boosting for relevant solution
    sol1_score = next(s for s in filtered if s[0] == "SOL_001")[2]
    sol2_score = next(s for s in filtered if s[0] == "SOL_002")[2]

    # SOL_001 should have higher score (mentions "id")
    assert sol1_score > 0.7  # Boosted


def test_filter_connection_solutions(generator):
    """Test CONNECTION solution filtering."""
    solutions = [
        (
            "SOL_015",
            {"title": "Fix Node Typo", "description": "Correct typo in node name"},
            0.7,
        ),
        (
            "SOL_016",
            {"title": "Add Missing Connection", "description": "Create new connection"},
            0.6,
        ),
    ]

    analysis = AnalysisResult(
        root_cause="Missing node",
        affected_nodes=[],
        affected_connections=[],
        affected_models=[],
        context_data={
            "missing_node": "usr_create",
            "similar_nodes": [("user_create", 0.9)],
        },
    )

    filtered = generator._filter_connection_solutions(solutions, analysis)

    # Verify filtering occurred
    assert len(filtered) == 2

    # Verify score boosting for typo solution
    sol15_score = next(s for s in filtered if s[0] == "SOL_015")[2]

    # SOL_015 should have boosted score (typo fix)
    assert sol15_score > 0.7


def test_rank_solutions(generator):
    """Test solution ranking by relevance score."""
    sol1 = SuggestedSolution(
        solution_id="SOL_001",
        title="Fix 1",
        category="QUICK_FIX",
        description="Solution 1",
        code_example="",
        explanation="",
        relevance_score=0.95,
        confidence=0.9,
    )

    sol2 = SuggestedSolution(
        solution_id="SOL_002",
        title="Fix 2",
        category="QUICK_FIX",
        description="Solution 2",
        code_example="",
        explanation="",
        relevance_score=0.75,
        confidence=0.8,
    )

    sol3 = SuggestedSolution(
        solution_id="SOL_003",
        title="Fix 3",
        category="CODE_REFACTORING",
        description="Solution 3",
        code_example="",
        explanation="",
        relevance_score=0.85,
        confidence=0.85,
    )

    ranked = generator._rank_solutions([sol2, sol3, sol1])

    # Verify ranking order (highest to lowest)
    assert ranked[0].relevance_score == 0.95
    assert ranked[1].relevance_score == 0.85
    assert ranked[2].relevance_score == 0.75
    assert ranked[0].solution_id == "SOL_001"


def test_min_relevance_threshold(generator):
    """Test minimum relevance threshold filtering."""
    analysis = AnalysisResult(
        root_cause="Missing parameter",
        affected_nodes=[],
        affected_connections=[],
        affected_models=[],
        context_data={"missing_parameter": "email"},  # Different parameter
    )

    category = ErrorCategory(
        category="PARAMETER",
        pattern_id="PARAM_001",
        confidence=0.2,  # Low confidence
        features={},
    )

    # Use high minimum relevance threshold
    solutions = generator.generate_solutions(
        analysis, category, max_solutions=5, min_relevance=0.8
    )

    # Verify only high-relevance solutions returned (or none)
    for solution in solutions:
        assert solution.relevance_score >= 0.8


def test_max_solutions_limit(generator):
    """Test maximum solutions limit."""
    analysis = AnalysisResult(
        root_cause="Missing parameter 'id'",
        affected_nodes=["UserCreateNode"],
        affected_models=["User"],
        context_data={"missing_parameter": "id"},
    )

    category = ErrorCategory(
        category="PARAMETER", pattern_id="PARAM_001", confidence=0.9, features={}
    )

    # Limit to 1 solution
    solutions = generator.generate_solutions(
        analysis, category, max_solutions=1, min_relevance=0.0
    )

    # Verify limit enforced
    assert len(solutions) <= 1


def test_suggested_solution_serialization():
    """Test SuggestedSolution to_dict() serialization."""
    solution = SuggestedSolution(
        solution_id="SOL_001",
        title="Add Missing 'id' Parameter",
        category="QUICK_FIX",
        description="Add required 'id' field",
        code_example='workflow.add_node("UserCreateNode", "create", {"id": "value"})',
        explanation="The 'id' field is required...",
        references=["https://docs.dataflow.dev/nodes/create"],
        difficulty="easy",
        estimated_time=1,
        relevance_score=0.95,
        confidence=0.9,
    )

    data = solution.to_dict()

    # Verify all fields present
    assert data["solution_id"] == "SOL_001"
    assert data["title"] == "Add Missing 'id' Parameter"
    assert data["category"] == "QUICK_FIX"
    assert data["relevance_score"] == 0.95
    assert data["confidence"] == 0.9
    assert data["difficulty"] == "easy"
    assert data["estimated_time"] == 1


def test_suggested_solution_cli_format():
    """Test SuggestedSolution CLI formatting."""
    solution = SuggestedSolution(
        solution_id="SOL_001",
        title="Add Missing 'id' Parameter",
        category="QUICK_FIX",
        description="Add required 'id' field to CreateNode",
        code_example='workflow.add_node("UserCreateNode", "create", {"id": "user-123"})',
        explanation="The 'id' field is required for all CREATE operations in DataFlow.",
        references=["https://docs.dataflow.dev/nodes/create"],
        difficulty="easy",
        estimated_time=1,
        relevance_score=0.95,
        confidence=0.9,
    )

    formatted = solution.format_for_cli()

    # Verify formatted output contains key elements
    assert "SOL_001" in formatted
    assert "Add Missing 'id' Parameter" in formatted
    assert "QUICK_FIX" in formatted
    assert "Difficulty: easy" in formatted
    assert "Time: 1 min" in formatted
    assert "Relevance: 95%" in formatted
    assert "Code Example:" in formatted
    assert "UserCreateNode" in formatted


def test_no_candidate_solutions(generator, mock_knowledge_base):
    """Test behavior when no candidate solutions found."""
    # Mock no solutions for pattern
    mock_knowledge_base.get_pattern.return_value = None

    analysis = AnalysisResult(
        root_cause="Unknown error",
        affected_nodes=[],
        affected_connections=[],
        affected_models=[],
        context_data={},
    )

    category = ErrorCategory(
        category="UNKNOWN", pattern_id="UNKNOWN", confidence=0.0, features={}
    )

    solutions = generator.generate_solutions(analysis, category)

    # Verify empty list returned
    assert len(solutions) == 0
