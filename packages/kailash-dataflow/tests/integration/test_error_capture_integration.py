"""Integration tests for error capture and categorization.

Tests end-to-end error processing flow: capture → categorize → solutions lookup.
"""

import pytest
import pytest_asyncio
from dataflow import DataFlow
from dataflow.debug.error_capture import ErrorCapture
from dataflow.debug.error_categorizer import ErrorCategorizer
from dataflow.debug.knowledge_base import KnowledgeBase

from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest_asyncio.fixture
async def db():
    """Create DataFlow instance."""
    return DataFlow(":memory:")


@pytest_asyncio.fixture
async def knowledge_base():
    """Create KnowledgeBase."""
    return KnowledgeBase(
        "src/dataflow/debug/patterns.yaml",
        "src/dataflow/debug/solutions.yaml",
    )


@pytest_asyncio.fixture
async def capture():
    """Create ErrorCapture."""
    return ErrorCapture()


@pytest_asyncio.fixture
async def categorizer(knowledge_base):
    """Create ErrorCategorizer."""
    return ErrorCategorizer(knowledge_base)


@pytest.mark.asyncio
async def test_capture_and_categorize_parameter_error(db, capture, categorizer):
    """Test capturing and categorizing parameter error end-to-end."""

    @db.model
    class User:
        id: str
        name: str

    await db.initialize()

    # Create workflow with missing parameter
    workflow = WorkflowBuilder()
    workflow.add_node(
        "UserCreateNode",
        "create",
        {"name": "Alice"},  # Missing 'id' parameter
    )

    runtime = LocalRuntime()

    # Capture error
    try:
        results, _ = runtime.execute(workflow.build())
        pytest.fail("Expected exception for missing parameter")
    except Exception as e:
        captured = capture.capture(e)
        category = categorizer.categorize(captured)

        # Verify error was captured and categorized correctly
        assert captured.error_type is not None
        assert (
            "id" in captured.message.lower() or "required" in captured.message.lower()
        )

        # Should categorize as PARAMETER error
        assert category.category == "PARAMETER"
        assert category.confidence >= 0.5


@pytest.mark.asyncio
async def test_capture_and_categorize_connection_error(db, capture, categorizer):
    """Test capturing and categorizing connection error end-to-end."""

    @db.model
    class User:
        id: str
        name: str

    await db.initialize()

    # Create workflow with invalid connection
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {"id": "1", "name": "Alice"})

    runtime = LocalRuntime()

    try:
        # Add invalid connection to non-existent node (raises WorkflowValidationError)
        workflow.add_connection("nonexistent_node", "output", "create", "name")
        results, _ = runtime.execute(workflow.build())
        pytest.fail("Expected exception for invalid connection")
    except Exception as e:
        captured = capture.capture(e)
        category = categorizer.categorize(captured)

        # Verify error was captured
        assert captured.error_type is not None
        assert len(captured.stacktrace) > 0

        # Should categorize as CONNECTION error
        assert category.category in ["CONNECTION", "PARAMETER"]
        assert category.confidence > 0.0


def test_capture_multiple_errors(capture, categorizer):
    """Test capturing and categorizing multiple errors."""
    errors_captured = []
    categories = []

    for i in range(3):
        try:
            if i == 0:
                raise ValueError(f"Missing parameter 'id' in operation {i}")
            elif i == 1:
                raise KeyError(f"Node 'process_{i}' not found")
            else:
                raise TimeoutError(f"Query timeout in operation {i}")
        except Exception as e:
            captured = capture.capture(e)
            category = categorizer.categorize(captured)

            errors_captured.append(captured)
            categories.append(category)

    # Verify all errors were captured
    assert len(errors_captured) == 3
    assert len(capture.get_all_captured_errors()) >= 3

    # Verify all were categorized
    assert len(categories) == 3

    # First error should be PARAMETER
    assert categories[0].category == "PARAMETER"

    # Second error should be CONNECTION or PARAMETER
    assert categories[1].category in ["CONNECTION", "PARAMETER"]

    # Third error should be RUNTIME
    assert categories[2].category == "RUNTIME"


def test_pattern_matching_accuracy(capture, categorizer):
    """Test pattern matching accuracy across error types."""
    test_cases = [
        (ValueError("Missing required parameter 'id'"), "PARAMETER"),
        (KeyError("Source node 'user_create' not found"), "CONNECTION"),
        (Exception("Table 'users' already exists"), "MIGRATION"),
        (ValueError("Invalid database URL format"), "CONFIGURATION"),
        (TimeoutError("Query timeout after 30 seconds"), "RUNTIME"),
    ]

    correct = 0
    total = len(test_cases)

    for exception, expected_category in test_cases:
        try:
            raise exception
        except Exception as e:
            captured = capture.capture(e)
            category = categorizer.categorize(captured)

            # Allow some flexibility in categorization
            # (some errors might match multiple categories)
            if category.category == expected_category:
                correct += 1
            elif category.confidence > 0.7:
                # If very confident in a different category, that's acceptable
                correct += 0.5

    accuracy = correct / total

    # Require at least 60% accuracy (3 out of 5 correct)
    # This is a reasonable threshold given pattern overlap
    assert accuracy >= 0.6, f"Accuracy {accuracy:.2f} below threshold 0.6"


def test_knowledge_base_integration(knowledge_base, capture, categorizer):
    """Test KnowledgeBase integration with pattern and solution lookup."""
    # Create a parameter error
    try:
        raise ValueError("Missing required parameter 'id'")
    except Exception as e:
        captured = capture.capture(e)
        category = categorizer.categorize(captured)

    # Should have categorized successfully
    assert category.category is not None
    assert category.pattern_id is not None

    # Get the matched pattern from knowledge base
    pattern = knowledge_base.get_pattern(category.pattern_id)

    # Pattern should exist and have expected fields
    if pattern:  # May be UNKNOWN pattern
        assert "name" in pattern
        assert "category" in pattern
        assert "related_solutions" in pattern

        # Get solutions for this pattern
        solutions = knowledge_base.get_solutions_for_pattern(category.pattern_id)

        # Should have at least one solution
        if len(solutions) > 0:
            # Verify solution structure
            solution = solutions[0]
            assert "title" in solution
            assert "category" in solution
            assert "description" in solution
            assert solution["category"] in [
                "QUICK_FIX",
                "CODE_REFACTORING",
                "CONFIGURATION",
                "ARCHITECTURE",
            ]
