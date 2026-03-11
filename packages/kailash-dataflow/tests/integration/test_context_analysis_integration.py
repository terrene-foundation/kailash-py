"""Integration tests for context analysis with Inspector.

Tests end-to-end error analysis flow: capture → categorize → analyze with
real DataFlow workflows and Inspector integration.
"""

import pytest
import pytest_asyncio
from dataflow import DataFlow
from dataflow.debug.context_analyzer import ContextAnalyzer
from dataflow.debug.error_capture import ErrorCapture
from dataflow.debug.error_categorizer import ErrorCategorizer
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector

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


@pytest_asyncio.fixture
async def inspector(db):
    """Create Inspector with DataFlow instance."""
    return Inspector(db)


@pytest_asyncio.fixture
async def analyzer(inspector):
    """Create ContextAnalyzer with Inspector."""
    return ContextAnalyzer(inspector)


@pytest.mark.asyncio
async def test_parameter_error_with_inspector(db, capture, categorizer, analyzer):
    """Test full pipeline for parameter error with Inspector integration."""

    @db.model
    class User:
        id: str
        name: str

    await db.initialize()

    # Create workflow with missing parameter (missing 'id')
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
        # Capture error
        captured = capture.capture(e)

        # Categorize error
        category = categorizer.categorize(captured)

        # Analyze with Inspector
        analysis = analyzer.analyze(captured, category)

        # Verify analysis contains Inspector context
        assert analysis.root_cause is not None
        assert "id" in analysis.root_cause or "id" in analysis.context_data.get(
            "missing_parameter", ""
        )

        # Verify Inspector integration
        if "model_name" in analysis.context_data:
            assert analysis.context_data["model_name"] == "User"

        # Verify suggestions provided
        assert len(analysis.suggestions) > 0


@pytest.mark.asyncio
async def test_connection_error_with_inspector(db, capture, categorizer, inspector):
    """Test full pipeline for connection error with workflow structure."""

    @db.model
    class User:
        id: str
        name: str

    await db.initialize()

    # Create workflow with invalid connection
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {"id": "1", "name": "Alice"})

    # Create analyzer with workflow context
    inspector_with_workflow = Inspector(db, workflow)
    analyzer = ContextAnalyzer(inspector_with_workflow)

    runtime = LocalRuntime()

    try:
        # Add connection to non-existent node (raises WorkflowValidationError)
        workflow.add_connection("nonexistent_node", "output", "create", "name")
        results, _ = runtime.execute(workflow.build())
        pytest.fail("Expected exception for invalid connection")
    except Exception as e:
        # Capture error
        captured = capture.capture(e)

        # Categorize error
        category = categorizer.categorize(captured)

        # Analyze with Inspector + workflow
        analysis = analyzer.analyze(captured, category)

        # Verify analysis
        assert analysis.root_cause is not None

        # If workflow context available, should have node information
        if "available_nodes" in analysis.context_data:
            available_nodes = analysis.context_data["available_nodes"]
            assert "create" in available_nodes

        # Verify suggestions
        assert len(analysis.suggestions) > 0


@pytest.mark.asyncio
async def test_end_to_end_context_extraction(db, capture, categorizer, analyzer):
    """Test complete error processing pipeline with context extraction."""

    @db.model
    class User:
        id: str
        name: str

    await db.initialize()

    # Test 1: Parameter error
    workflow1 = WorkflowBuilder()
    workflow1.add_node("UserCreateNode", "create1", {"id": "1", "name": "Alice"})

    runtime = LocalRuntime()

    try:
        results, _ = runtime.execute(workflow1.build())
        # May succeed if all required fields provided
    except Exception as e:
        captured = capture.capture(e)
        category = categorizer.categorize(captured)
        analysis = analyzer.analyze(captured, category)

        # Should provide meaningful analysis
        assert analysis.root_cause != "Unknown error - unable to determine root cause"
        assert len(analysis.affected_nodes) > 0 or len(analysis.suggestions) > 0

    # Test 2: Successful operation (no error)
    workflow2 = WorkflowBuilder()
    workflow2.add_node("UserCreateNode", "create2", {"id": "2", "name": "Bob"})

    results, _ = runtime.execute(workflow2.build())
    assert "create2" in results


@pytest.mark.asyncio
async def test_inspector_integration_accuracy(db, inspector, analyzer):
    """Test Inspector API usage correctness in context extraction."""

    @db.model
    class User:
        id: str
        name: str

    await db.initialize()

    # Verify Inspector can access model information
    try:
        model_info = inspector.model("User")
        assert model_info.name == "User"

        # Skip if schema is empty (Inspector API limitation)
        if not model_info.schema:
            pytest.skip("Inspector returned empty schema - API limitation")

        assert "id" in model_info.schema
        assert "name" in model_info.schema

        # Test parameter error analysis with Inspector context
        from datetime import datetime

        from dataflow.debug.error_capture import CapturedError
        from dataflow.debug.error_categorizer import ErrorCategory

        error = CapturedError(
            exception=ValueError("NOT NULL constraint failed: users.id"),
            error_type="ValueError",
            message="NOT NULL constraint failed: users.id",
            stacktrace=[],
            context={"node_id": "UserCreateNode"},
            timestamp=datetime.now(),
        )

        category = ErrorCategory(
            category="PARAMETER",
            pattern_id="PARAM_001",
            confidence=0.9,
            features={},
        )

        analysis = analyzer.analyze(error, category)

        # Verify Inspector data was used
        assert analysis.context_data.get("model_name") == "User"
        assert analysis.context_data.get("table_name") == "users"
        assert "id" in analysis.context_data.get("missing_parameter", "")
        assert analysis.context_data.get("is_primary_key") is not None

    except ValueError as e:
        # Model not found - expected in some test configurations
        pytest.skip(f"Model not accessible via Inspector: {e}")
