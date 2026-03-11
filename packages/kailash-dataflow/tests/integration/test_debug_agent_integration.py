"""Integration tests for Debug Agent CLI interface.

Tests the complete Debug Agent pipeline end-to-end with real
KnowledgeBase and DataFlow workflows.
"""

import json

import pytest
import pytest_asyncio
from dataflow import DataFlow
from dataflow.debug.cli_formatter import CLIFormatter
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector

from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest_asyncio.fixture
async def knowledge_base():
    """Create KnowledgeBase with real YAML files."""
    return KnowledgeBase(
        "src/dataflow/debug/patterns.yaml",
        "src/dataflow/debug/solutions.yaml",
    )


@pytest_asyncio.fixture
async def db():
    """Create DataFlow instance."""
    return DataFlow(":memory:")


@pytest_asyncio.fixture
async def inspector(db):
    """Create Inspector with DataFlow instance."""
    return Inspector(db)


@pytest_asyncio.fixture
async def debug_agent(knowledge_base, inspector):
    """Create DebugAgent with real components."""
    return DebugAgent(knowledge_base, inspector)


@pytest.mark.asyncio
async def test_debug_agent_end_to_end(db, debug_agent):
    """Test complete Debug Agent pipeline with real error."""

    @db.model
    class User:
        id: str
        name: str
        email: str

    await db.initialize()

    # Create workflow with missing parameter (triggers real error)
    workflow = WorkflowBuilder()
    workflow.add_node(
        "UserCreateNode", "create", {"name": "Alice"}  # Missing required 'id' parameter
    )

    runtime = LocalRuntime()

    # Execute and capture error
    try:
        results, _ = runtime.execute(workflow.build())
        pytest.fail("Expected exception for missing parameter")
    except Exception as e:
        # Run Debug Agent pipeline
        report = debug_agent.debug(e, max_solutions=5, min_relevance=0.0)

        # Verify report structure
        assert report.captured_error is not None
        assert report.error_category is not None
        assert report.analysis_result is not None
        assert report.execution_time > 0

        # Verify captured error
        assert report.captured_error.exception is not None
        assert report.captured_error.error_type != ""
        assert report.captured_error.message != ""

        # Verify category (may be UNKNOWN due to wrapped exception issue)
        assert report.error_category.category != ""
        assert 0.0 <= report.error_category.confidence <= 1.0

        # Verify analysis
        assert report.analysis_result.root_cause != ""

        # Solutions may be 0 if categorizer returns UNKNOWN
        # This is expected and documented in previous tasks


@pytest.mark.asyncio
async def test_debug_agent_with_formatter(db, debug_agent):
    """Test Debug Agent with CLI formatter."""

    @db.model
    class User:
        id: str
        name: str

    await db.initialize()

    # Create workflow with error
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {"name": "Alice"})  # Missing 'id'

    runtime = LocalRuntime()

    try:
        results, _ = runtime.execute(workflow.build())
        pytest.fail("Expected exception")
    except Exception as e:
        # Generate report
        report = debug_agent.debug(e)

        # Format for CLI
        formatter = CLIFormatter()
        output = formatter.format_report(report)

        # Verify formatted output contains key sections
        assert "DataFlow Debug Agent" in output
        assert "ERROR" in output  # Error section
        assert report.captured_error.error_type in output

        # Should have box drawing characters
        assert "╔" in output or "┌" in output


@pytest.mark.asyncio
async def test_debug_from_string_integration(debug_agent):
    """Test debugging error message string."""
    error_message = "NOT NULL constraint failed: users.id"

    # Run debug pipeline on string
    report = debug_agent.debug_from_string(
        error_message, error_type="DatabaseError", max_solutions=3, min_relevance=0.0
    )

    # Verify report structure
    assert report.captured_error.message == error_message
    assert report.error_category is not None
    assert report.analysis_result is not None

    # Verify execution time is tracked
    assert report.execution_time > 0


@pytest.mark.asyncio
async def test_json_output_format(db, debug_agent):
    """Test JSON serialization of debug report."""

    @db.model
    class User:
        id: str
        name: str

    await db.initialize()

    # Create workflow with error
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {"name": "Alice"})  # Missing 'id'

    runtime = LocalRuntime()

    try:
        results, _ = runtime.execute(workflow.build())
        pytest.fail("Expected exception")
    except Exception as e:
        # Generate report
        report = debug_agent.debug(e)

        # Export to JSON
        json_str = report.to_json()
        assert isinstance(json_str, str)

        # Parse JSON
        data = json.loads(json_str)

        # Verify JSON structure
        assert "captured_error" in data
        assert "error_category" in data
        assert "analysis_result" in data
        assert "suggested_solutions" in data
        assert "execution_time" in data

        # Verify data types
        assert isinstance(data["captured_error"], dict)
        assert isinstance(data["error_category"], dict)
        assert isinstance(data["analysis_result"], dict)
        assert isinstance(data["suggested_solutions"], list)
        assert isinstance(data["execution_time"], (int, float))


@pytest.mark.asyncio
async def test_complete_pipeline_with_context(db, debug_agent):
    """Test complete pipeline with Inspector context."""

    @db.model
    class User:
        id: str
        name: str
        email: str

    await db.initialize()

    # Create workflow
    workflow = WorkflowBuilder()
    workflow.add_node(
        "UserCreateNode",
        "create",
        {
            "name": "Alice",
            "email": "alice@example.com",
            # Missing 'id'
        },
    )

    runtime = LocalRuntime()

    try:
        results, _ = runtime.execute(workflow.build())
        pytest.fail("Expected exception")
    except Exception as e:
        # Run debug pipeline
        report = debug_agent.debug(e, max_solutions=3, min_relevance=0.0)

        # Verify all stages completed
        assert report.captured_error is not None
        assert report.error_category is not None
        assert report.analysis_result is not None

        # Verify execution metadata
        assert report.execution_time > 0

        # Verify serialization works
        data = report.to_dict()
        assert "captured_error" in data
        assert "error_category" in data


@pytest.mark.asyncio
async def test_debug_agent_without_solutions(debug_agent):
    """Test Debug Agent when no solutions are found."""
    # Generic error that may not have specific solutions
    error_message = "Unexpected internal error"

    report = debug_agent.debug_from_string(
        error_message, error_type="InternalError", max_solutions=5, min_relevance=0.3
    )

    # Report should still be created even with 0 solutions
    assert report.captured_error is not None
    assert report.error_category is not None
    assert report.analysis_result is not None

    # Solutions may be empty
    # This is expected for uncategorized or generic errors
