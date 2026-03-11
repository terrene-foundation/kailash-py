"""Unit tests for knowledge base component.

Tests the KnowledgeBase to ensure proper loading and querying of error
patterns and solutions from YAML files.
"""

import pytest
from dataflow.debug.knowledge_base import KnowledgeBase


@pytest.fixture
def knowledge_base():
    """Create KnowledgeBase fixture."""
    patterns_path = "src/dataflow/debug/patterns.yaml"
    solutions_path = "src/dataflow/debug/solutions.yaml"
    return KnowledgeBase(patterns_path, solutions_path)


def test_load_patterns(knowledge_base):
    """Test pattern loading from YAML."""
    # Should have 50+ patterns
    assert len(knowledge_base.patterns) >= 50

    # Verify pattern structure
    for pattern_id, pattern in knowledge_base.patterns.items():
        assert "name" in pattern
        assert "category" in pattern
        assert pattern["category"] in [
            "PARAMETER",
            "CONNECTION",
            "MIGRATION",
            "CONFIGURATION",
            "RUNTIME",
        ]


def test_get_pattern(knowledge_base):
    """Test getting pattern by ID."""
    pattern = knowledge_base.get_pattern("PARAM_001")

    assert pattern is not None
    assert "name" in pattern
    assert "category" in pattern
    assert "regex" in pattern
    assert "related_solutions" in pattern

    # Verify pattern has required fields
    assert isinstance(pattern["name"], str)
    assert isinstance(pattern["category"], str)
    assert isinstance(pattern["related_solutions"], list)


def test_get_patterns_by_category(knowledge_base):
    """Test getting patterns by category."""
    param_patterns = knowledge_base.get_patterns_by_category("PARAMETER")

    # Should have 15+ parameter patterns
    assert len(param_patterns) >= 15

    # All patterns should have PARAMETER category
    for pattern in param_patterns:
        assert pattern["category"] == "PARAMETER"
        assert "id" in pattern  # Added by method

    # Test other categories
    conn_patterns = knowledge_base.get_patterns_by_category("CONNECTION")
    assert len(conn_patterns) >= 10

    migration_patterns = knowledge_base.get_patterns_by_category("MIGRATION")
    assert len(migration_patterns) >= 8

    config_patterns = knowledge_base.get_patterns_by_category("CONFIGURATION")
    assert len(config_patterns) >= 7

    runtime_patterns = knowledge_base.get_patterns_by_category("RUNTIME")
    assert len(runtime_patterns) >= 10


def test_get_solution(knowledge_base):
    """Test getting solution by ID."""
    solution = knowledge_base.get_solution("SOL_001")

    assert solution is not None
    assert "title" in solution
    assert "category" in solution
    assert "description" in solution
    assert "code_example" in solution

    # Verify solution has required fields
    assert isinstance(solution["title"], str)
    assert isinstance(solution["category"], str)
    assert solution["category"] in [
        "QUICK_FIX",
        "CODE_REFACTORING",
        "CONFIGURATION",
        "ARCHITECTURE",
    ]


def test_reload_patterns(knowledge_base):
    """Test pattern reload functionality."""
    initial_count = len(knowledge_base.patterns)

    # Reload patterns
    knowledge_base.reload_patterns()

    # Should have same count
    assert len(knowledge_base.patterns) == initial_count

    # Test solution reload
    initial_solution_count = len(knowledge_base.solutions)
    knowledge_base.reload_solutions()
    assert len(knowledge_base.solutions) == initial_solution_count
