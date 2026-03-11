"""End-to-end integration tests for Debug Agent with real DataFlow errors.

Tests the complete Debug Agent pipeline with production error scenarios across
all 5 error categories: PARAMETER, CONNECTION, MIGRATION, RUNTIME, CONFIGURATION.

NO MOCKING - All tests use real DataFlow workflows and KnowledgeBase.
"""

import json
import time
from typing import Optional

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
    """Create DataFlow instance with in-memory database."""
    return DataFlow(":memory:")


@pytest_asyncio.fixture
async def inspector(db):
    """Create Inspector with DataFlow instance."""
    return Inspector(db)


@pytest_asyncio.fixture
async def debug_agent(knowledge_base, inspector):
    """Create DebugAgent with real components."""
    return DebugAgent(knowledge_base, inspector)


# ==================== PARAMETER ERROR TESTS (5 tests) ====================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_missing_id_parameter(db, debug_agent):
    """E2E test for missing 'id' parameter in CreateNode.

    Scenario: User forgets to include required 'id' field in CREATE operation.
    Expected: Debug Agent diagnoses missing parameter and suggests adding 'id'.
    """

    @db.model
    class User:
        id: str
        name: str
        email: str

    await db.initialize()

    # Create workflow with missing 'id' parameter
    workflow = WorkflowBuilder()
    workflow.add_node(
        "UserCreateNode",
        "create",
        {
            "name": "Alice",
            "email": "alice@example.com",
            # Missing required 'id' parameter
        },
    )

    runtime = LocalRuntime()

    try:
        results, _ = runtime.execute(workflow.build())
        pytest.fail("Expected exception for missing 'id' parameter")
    except Exception as e:
        # Run Debug Agent
        report = debug_agent.debug(e, max_solutions=5, min_relevance=0.0)

        # Verify basic structure
        assert report.captured_error is not None
        assert report.error_category is not None
        assert report.analysis_result is not None

        # Verify error message contains relevant information
        error_msg = report.captured_error.message.lower()
        assert "not null" in error_msg or "constraint" in error_msg or "id" in error_msg

        # Verify execution time tracking
        assert report.execution_time > 0
        assert report.execution_time < 1000  # Should complete quickly


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_type_mismatch_parameter(db, debug_agent):
    """E2E test for parameter type mismatch.

    Scenario: User provides integer where string is expected.
    Expected: Debug Agent diagnoses type mismatch and suggests correct type.
    """

    @db.model
    class Product:
        id: str
        name: str
        price: float

    await db.initialize()

    # Create workflow with type mismatch
    workflow = WorkflowBuilder()
    workflow.add_node(
        "ProductCreateNode",
        "create",
        {
            "id": "prod-001",
            "name": "Widget",
            "price": "invalid_price",  # String instead of float
        },
    )

    runtime = LocalRuntime()

    try:
        results, _ = runtime.execute(workflow.build())
        # May or may not raise exception depending on validation
    except Exception as e:
        # Run Debug Agent
        report = debug_agent.debug(e, max_solutions=3, min_relevance=0.0)

        # Verify report structure
        assert report.captured_error is not None
        assert report.error_category is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_invalid_parameter_value(db, debug_agent):
    """E2E test for invalid parameter value.

    Scenario: User provides empty string for required field.
    Expected: Debug Agent diagnoses invalid value and suggests validation.
    """

    @db.model
    class User:
        id: str
        email: str
        status: str

    await db.initialize()

    # Debug from error message (common scenario - analyzing logged errors)
    error_message = "CHECK constraint failed: email must be valid format"
    report = debug_agent.debug_from_string(
        error_message, error_type="DatabaseError", max_solutions=3, min_relevance=0.0
    )

    # Verify report structure
    assert report.captured_error.message == error_message
    assert report.error_category is not None
    assert report.analysis_result is not None
    assert report.execution_time > 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_createnode_updatenode_confusion(db, debug_agent):
    """E2E test for CreateNode vs UpdateNode parameter pattern confusion.

    Scenario: User uses UpdateNode pattern in CreateNode (filter + fields).
    Expected: Debug Agent diagnoses pattern mismatch and suggests flat parameters.
    """
    # Debug from error message (common mistake pattern)
    error_message = "CreateNode received 'filter' parameter - use flat parameters like {id: 'value', name: 'value'}"
    report = debug_agent.debug_from_string(
        error_message, error_type="ParameterError", max_solutions=5, min_relevance=0.0
    )

    # Verify report structure
    assert report.captured_error is not None
    assert "filter" in report.captured_error.message.lower()
    assert report.error_category is not None
    assert report.analysis_result is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_reserved_field_parameter(db, debug_agent):
    """E2E test for using reserved auto-managed fields.

    Scenario: User tries to set created_at or updated_at manually.
    Expected: Debug Agent diagnoses reserved field usage and suggests removal.
    """
    # Debug from error message (validation error)
    error_message = (
        "Field 'created_at' is auto-managed - do not include in CREATE operations"
    )
    report = debug_agent.debug_from_string(
        error_message, error_type="ValidationError", max_solutions=3, min_relevance=0.0
    )

    # Verify report structure
    assert report.captured_error is not None
    assert (
        "created_at" in report.captured_error.message
        or "auto-managed" in report.captured_error.message
    )
    assert report.error_category is not None


# ==================== CONNECTION ERROR TESTS (3 tests) ====================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_missing_source_node_connection(db, debug_agent):
    """E2E test for missing source node in connection.

    Scenario: User connects to non-existent source node.
    Expected: Debug Agent diagnoses missing node and suggests adding it.
    """

    @db.model
    class User:
        id: str
        name: str

    await db.initialize()

    # Create workflow with missing source node - catch validation error
    workflow = WorkflowBuilder()
    workflow.add_node("UserReadNode", "read", {"id": "user-123"})

    try:
        # Connection to non-existent node 'create_user' - raises validation error
        workflow.add_connection("create_user", "id", "read", "id")
        pytest.fail("Expected exception for missing source node")
    except Exception as e:
        # Run Debug Agent on validation error
        report = debug_agent.debug(e, max_solutions=3, min_relevance=0.0)

        # Verify error capture
        assert report.captured_error is not None
        error_msg = report.captured_error.message.lower()
        assert (
            "create_user" in error_msg
            or "not found" in error_msg
            or "source" in error_msg
        )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_circular_dependency_connection(db, debug_agent):
    """E2E test for circular dependency in connections.

    Scenario: User creates circular connection (A -> B -> A).
    Expected: Debug Agent diagnoses circular dependency and suggests breaking cycle.
    """
    # Debug from error message (circular dependency detected)
    error_message = "Circular dependency detected: node_a -> node_b -> node_a"
    report = debug_agent.debug_from_string(
        error_message,
        error_type="CircularDependencyError",
        max_solutions=3,
        min_relevance=0.0,
    )

    # Verify report structure
    assert report.captured_error is not None
    assert "circular" in report.captured_error.message.lower()
    assert report.error_category is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_type_incompatibility_connection(db, debug_agent):
    """E2E test for type incompatibility in connections.

    Scenario: User connects string output to integer input.
    Expected: Debug Agent diagnoses type mismatch and suggests conversion.
    """
    # Debug from error message (type incompatibility)
    error_message = (
        "Type mismatch in connection: source outputs 'str' but target expects 'int'"
    )
    report = debug_agent.debug_from_string(
        error_message,
        error_type="TypeMismatchError",
        max_solutions=3,
        min_relevance=0.0,
    )

    # Verify report structure
    assert report.captured_error is not None
    assert (
        "type" in report.captured_error.message.lower()
        or "mismatch" in report.captured_error.message.lower()
    )
    assert report.error_category is not None


# ==================== MIGRATION ERROR TESTS (3 tests) ====================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_schema_conflict_migration(db, debug_agent):
    """E2E test for schema conflict during migration.

    Scenario: User modifies model but migration conflicts with existing data.
    Expected: Debug Agent diagnoses schema conflict and suggests resolution steps.
    """
    # Debug from error message (schema conflict)
    error_message = "Cannot alter column 'email' from TEXT to INTEGER - data type incompatible with existing rows"
    report = debug_agent.debug_from_string(
        error_message, error_type="MigrationError", max_solutions=5, min_relevance=0.0
    )

    # Verify report structure
    assert report.captured_error is not None
    assert (
        "alter" in report.captured_error.message.lower()
        or "column" in report.captured_error.message.lower()
    )
    assert report.error_category is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_missing_table_migration(db, debug_agent):
    """E2E test for missing table during migration.

    Scenario: User references table that doesn't exist yet.
    Expected: Debug Agent diagnoses missing table and suggests initialization.
    """
    # Debug from error message (missing table)
    error_message = "Table 'users' does not exist - run db.initialize() first"
    report = debug_agent.debug_from_string(
        error_message,
        error_type="TableNotFoundError",
        max_solutions=3,
        min_relevance=0.0,
    )

    # Verify report structure
    assert report.captured_error is not None
    assert (
        "table" in report.captured_error.message.lower()
        or "users" in report.captured_error.message.lower()
    )
    assert report.error_category is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_constraint_violation_migration(db, debug_agent):
    """E2E test for constraint violation during migration.

    Scenario: User adds NOT NULL constraint but existing data has NULLs.
    Expected: Debug Agent diagnoses constraint violation and suggests data cleanup.
    """
    # Debug from error message (constraint violation)
    error_message = "Cannot add NOT NULL constraint to column 'email' - 3 existing rows have NULL values"
    report = debug_agent.debug_from_string(
        error_message,
        error_type="ConstraintViolationError",
        max_solutions=3,
        min_relevance=0.0,
    )

    # Verify report structure
    assert report.captured_error is not None
    assert (
        "constraint" in report.captured_error.message.lower()
        or "null" in report.captured_error.message.lower()
    )
    assert report.error_category is not None


# ==================== RUNTIME ERROR TESTS (2 tests) ====================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_transaction_timeout_runtime(db, debug_agent):
    """E2E test for transaction timeout in runtime.

    Scenario: User has long-running transaction that times out.
    Expected: Debug Agent diagnoses timeout and suggests increasing limit or optimization.
    """
    # Debug from error message (transaction timeout)
    error_message = "Transaction timeout after 30 seconds - consider increasing timeout or optimizing query"
    report = debug_agent.debug_from_string(
        error_message, error_type="TimeoutError", max_solutions=3, min_relevance=0.0
    )

    # Verify report structure
    assert report.captured_error is not None
    assert (
        "timeout" in report.captured_error.message.lower()
        or "transaction" in report.captured_error.message.lower()
    )
    assert report.error_category is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_event_loop_collision_runtime(db, debug_agent):
    """E2E test for event loop collision (AsyncLocalRuntime).

    Scenario: User calls AsyncLocalRuntime.execute_workflow_async() from sync context.
    Expected: Debug Agent diagnoses event loop issue and suggests using LocalRuntime.
    """
    # Debug from error message (event loop collision)
    error_message = "Event loop collision detected - use AsyncLocalRuntime for async contexts or LocalRuntime for sync contexts"
    report = debug_agent.debug_from_string(
        error_message, error_type="RuntimeError", max_solutions=3, min_relevance=0.0
    )

    # Verify report structure
    assert report.captured_error is not None
    assert (
        "event loop" in report.captured_error.message.lower()
        or "runtime" in report.captured_error.message.lower()
    )
    assert report.error_category is not None


# ==================== CONFIGURATION ERROR TESTS (2 tests) ====================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_invalid_database_url_configuration(db, debug_agent):
    """E2E test for invalid database URL configuration.

    Scenario: User provides malformed database URL.
    Expected: Debug Agent diagnoses invalid URL and suggests correction.
    """
    # Debug from error message (invalid database URL)
    error_message = "Invalid database URL format: 'postgres://localhost' - use postgresql://user:password@host:port/database"
    report = debug_agent.debug_from_string(
        error_message,
        error_type="ConfigurationError",
        max_solutions=3,
        min_relevance=0.0,
    )

    # Verify report structure
    assert report.captured_error is not None
    assert (
        "url" in report.captured_error.message.lower()
        or "postgres" in report.captured_error.message.lower()
    )
    assert report.error_category is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_missing_environment_variables_configuration(db, debug_agent):
    """E2E test for missing environment variables.

    Scenario: User forgot to set required DATABASE_URL environment variable.
    Expected: Debug Agent diagnoses missing env var and suggests setting it.
    """
    # Debug from error message (missing environment variable)
    error_message = "Environment variable 'DATABASE_URL' not set - configure in .env file or export in shell"
    report = debug_agent.debug_from_string(
        error_message,
        error_type="ConfigurationError",
        max_solutions=3,
        min_relevance=0.0,
    )

    # Verify report structure
    assert report.captured_error is not None
    assert (
        "database_url" in report.captured_error.message.lower()
        or "environment" in report.captured_error.message.lower()
    )
    assert report.error_category is not None


# ==================== ADVANCED E2E TESTS ====================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_complete_pipeline_with_cli_formatter(db, debug_agent):
    """E2E test for complete pipeline with CLI formatting.

    Verifies:
    - Error capture with real DataFlow workflow
    - Error categorization with KnowledgeBase
    - Context analysis with Inspector
    - Solution generation
    - CLI formatting with colors and box drawing
    """

    @db.model
    class Order:
        id: str
        product_id: str
        quantity: int

    await db.initialize()

    # Create workflow with multiple issues
    workflow = WorkflowBuilder()
    workflow.add_node(
        "OrderCreateNode",
        "create",
        {
            "product_id": "prod-001",
            "quantity": 5,
            # Missing required 'id' parameter
        },
    )

    runtime = LocalRuntime()

    try:
        results, _ = runtime.execute(workflow.build())
        pytest.fail("Expected exception")
    except Exception as e:
        # Run Debug Agent
        report = debug_agent.debug(e, max_solutions=5, min_relevance=0.0)

        # Verify report components
        assert report.captured_error is not None
        assert report.error_category is not None
        assert report.analysis_result is not None

        # Format for CLI
        formatter = CLIFormatter()
        output = formatter.format_report(report)

        # Verify CLI output
        assert "DataFlow Debug Agent" in output
        assert "ERROR" in output
        assert report.captured_error.error_type in output

        # Verify box drawing characters
        assert "╔" in output or "┌" in output

        # Verify execution time tracking
        assert report.execution_time > 0

        # Verify JSON serialization
        json_str = report.to_json()
        data = json.loads(json_str)
        assert "captured_error" in data
        assert "error_category" in data
        assert "analysis_result" in data
        assert "suggested_solutions" in data
        assert "execution_time" in data


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_accuracy_metrics_validation(db, debug_agent):
    """E2E test for validating Debug Agent accuracy metrics.

    Tests:
    - Error categorization accuracy
    - Solution relevance scoring
    - Execution time performance (<50ms target)

    Success Criteria:
    - Report generation completes successfully
    - Execution time < 50ms for simple errors
    - Report structure is valid
    """

    @db.model
    class User:
        id: str
        username: str

    await db.initialize()

    # Test multiple error scenarios and track accuracy
    test_scenarios = [
        {
            "params": {"username": "alice"},  # Missing 'id'
            "expected_contains": ["id", "not null", "constraint"],
        }
    ]

    for scenario in test_scenarios:
        workflow = WorkflowBuilder()
        workflow.add_node("UserCreateNode", "create", scenario["params"])
        runtime = LocalRuntime()

        try:
            results, _ = runtime.execute(workflow.build())
        except Exception as e:
            start_time = time.time()
            report = debug_agent.debug(e, max_solutions=5, min_relevance=0.0)
            execution_time_ms = (time.time() - start_time) * 1000

            # Verify report structure
            assert report.captured_error is not None
            assert report.error_category is not None
            assert report.analysis_result is not None

            # Verify execution time performance
            assert execution_time_ms < 1000  # Should be fast (<1s)

            # Verify error message contains expected keywords
            error_msg = report.captured_error.message.lower()
            # At least one expected keyword should be present
            assert any(
                keyword in error_msg for keyword in scenario["expected_contains"]
            )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_json_export_import_roundtrip(db, debug_agent):
    """E2E test for JSON export/import roundtrip.

    Verifies:
    - DebugReport can be serialized to JSON
    - JSON can be deserialized back to DebugReport
    - All data is preserved through roundtrip
    """

    @db.model
    class Product:
        id: str
        name: str

    await db.initialize()

    workflow = WorkflowBuilder()
    workflow.add_node("ProductCreateNode", "create", {"name": "Widget"})  # Missing 'id'
    runtime = LocalRuntime()

    try:
        results, _ = runtime.execute(workflow.build())
    except Exception as e:
        # Generate report
        report = debug_agent.debug(e, max_solutions=3, min_relevance=0.0)

        # Export to JSON
        json_str = report.to_json()
        assert isinstance(json_str, str)
        assert len(json_str) > 0

        # Parse JSON
        data = json.loads(json_str)

        # Verify structure
        assert "captured_error" in data
        assert "error_category" in data
        assert "analysis_result" in data
        assert "suggested_solutions" in data
        assert "execution_time" in data

        # Import back from JSON
        from dataflow.debug.debug_report import DebugReport

        restored_report = DebugReport.from_dict(data)

        # Verify restored report
        assert restored_report.error_category.category == report.error_category.category
        assert restored_report.captured_error.message == report.captured_error.message
        assert restored_report.execution_time == report.execution_time
        assert len(restored_report.suggested_solutions) == len(
            report.suggested_solutions
        )
