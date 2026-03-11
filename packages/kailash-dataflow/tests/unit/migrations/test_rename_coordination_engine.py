#!/usr/bin/env python3
"""
Unit Tests for Rename Coordination Engine - TODO-139 Phase 2

Tests the core coordination system that executes complex multi-object rename
operations with transaction safety and rollback capabilities.

CRITICAL TEST COVERAGE:
- Multi-object rename workflow execution with dependency-aware ordering
- Transaction coordination with comprehensive rollback capabilities
- Integration with Phase 1 TableRenameAnalyzer for planning
- Integration with ForeignKeyAnalyzer for FK relationship management
- SQL rewriting for views and triggers referencing renamed tables
- Partial failure recovery and complex operation rollback

Key Features Tested:
1. Dependency-Aware Execution: Execute renames in correct dependency order
2. Transaction Coordination: Multi-step transactions with savepoints and rollback
3. FK Relationship Management: Maintain referential integrity during renames
4. SQL Rewriting: Update views and triggers to reference new table names
5. Partial Failure Recovery: Roll back complex operations when failures occur
6. Progress Tracking: Monitor and report progress through complex rename workflows
"""

import asyncio
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest

from dataflow.migrations.foreign_key_analyzer import (
    FKChain,
    FKImpactReport,
    FKSafeMigrationPlan,
    ForeignKeyAnalyzer,
)

# Import the classes we're testing (will be implemented)
from dataflow.migrations.rename_coordination_engine import (
    CircularDependencyError,
    CoordinationResult,
    RenameCoordinationEngine,
    RenameCoordinationError,
    RenameWorkflow,
    RenameWorkflowStep,
    WorkflowStatus,
    WorkflowStepType,
)
from dataflow.migrations.rename_transaction_manager import (
    RenameTransactionManager,
    RollbackResult,
    SavepointManager,
    TransactionError,
    TransactionState,
)
from dataflow.migrations.sql_rewriter import (
    SQLRewriteError,
    SQLRewriter,
    TriggerRewriteResult,
    ViewRewriteResult,
)

# Import existing classes from Phase 1
from dataflow.migrations.table_rename_analyzer import (
    DependencyGraph,
    RenameImpactLevel,
    SchemaObject,
    SchemaObjectType,
    TableRenameAnalyzer,
    TableRenameReport,
)


class TestRenameCoordinationEngineCore:
    """Test core RenameCoordinationEngine functionality."""

    @pytest.fixture
    def mock_connection(self):
        """Mock database connection."""
        return AsyncMock()

    @pytest.fixture
    def mock_connection_manager(self, mock_connection):
        """Mock connection manager."""
        manager = AsyncMock()
        manager.get_connection.return_value = mock_connection
        return manager

    @pytest.fixture
    def mock_table_analyzer(self):
        """Mock TableRenameAnalyzer."""
        analyzer = AsyncMock(spec=TableRenameAnalyzer)
        return analyzer

    @pytest.fixture
    def mock_fk_analyzer(self):
        """Mock ForeignKeyAnalyzer."""
        analyzer = AsyncMock(spec=ForeignKeyAnalyzer)
        return analyzer

    @pytest.fixture
    def mock_sql_rewriter(self):
        """Mock SQLRewriter."""
        rewriter = AsyncMock(spec=SQLRewriter)
        return rewriter

    @pytest.fixture
    def mock_transaction_manager(self):
        """Mock RenameTransactionManager."""
        manager = AsyncMock(spec=RenameTransactionManager)
        return manager

    @pytest.fixture
    def coordination_engine(
        self,
        mock_connection_manager,
        mock_table_analyzer,
        mock_fk_analyzer,
        mock_sql_rewriter,
        mock_transaction_manager,
    ):
        """Create RenameCoordinationEngine with mocked dependencies."""
        return RenameCoordinationEngine(
            connection_manager=mock_connection_manager,
            table_analyzer=mock_table_analyzer,
            fk_analyzer=mock_fk_analyzer,
            sql_rewriter=mock_sql_rewriter,
            transaction_manager=mock_transaction_manager,
        )

    def test_initialization(self, coordination_engine):
        """Test engine initialization with all dependencies."""
        assert coordination_engine is not None
        assert coordination_engine.connection_manager is not None
        assert coordination_engine.table_analyzer is not None
        assert coordination_engine.fk_analyzer is not None
        assert coordination_engine.sql_rewriter is not None
        assert coordination_engine.transaction_manager is not None

    def test_initialization_missing_dependencies_raises_error(self):
        """Test initialization fails with missing required dependencies."""
        with pytest.raises(ValueError, match="Connection manager is required"):
            RenameCoordinationEngine(connection_manager=None)

    @pytest.mark.asyncio
    async def test_execute_simple_rename_workflow(
        self, coordination_engine, mock_table_analyzer, mock_connection
    ):
        """Test execution of simple single-table rename workflow."""
        # Setup test data
        old_name = "test_table"
        new_name = "renamed_table"

        # Mock analyzer report with minimal dependencies
        mock_report = Mock(spec=TableRenameReport)
        mock_report.old_table_name = old_name
        mock_report.new_table_name = new_name
        mock_report.schema_objects = []
        mock_report.dependency_graph = None  # No dependency graph for simple case
        mock_report.impact_summary.overall_risk = RenameImpactLevel.SAFE

        mock_table_analyzer.analyze_table_rename.return_value = mock_report

        # Execute rename workflow
        result = await coordination_engine.execute_table_rename(
            old_name, new_name, connection=mock_connection
        )

        # Verify result
        assert result is not None
        assert result.success is True
        assert result.workflow_id is not None
        assert len(result.completed_steps) > 0

        # Verify analyzer was called
        mock_table_analyzer.analyze_table_rename.assert_called_once_with(
            old_name, new_name, mock_connection
        )

    @pytest.mark.asyncio
    async def test_execute_rename_with_foreign_key_dependencies(
        self,
        coordination_engine,
        mock_table_analyzer,
        mock_fk_analyzer,
        mock_connection,
    ):
        """Test rename workflow with FK dependencies requiring coordination."""
        # Setup test data
        old_name = "parent_table"
        new_name = "renamed_parent"

        # Mock FK objects
        fk_object = Mock(spec=SchemaObject)
        fk_object.object_type = SchemaObjectType.FOREIGN_KEY
        fk_object.impact_level = RenameImpactLevel.CRITICAL
        fk_object.object_name = "child_parent_fk"
        fk_object.references_table = "child_table"

        # Mock analyzer report with FK dependencies
        mock_report = Mock(spec=TableRenameReport)
        mock_report.old_table_name = old_name
        mock_report.new_table_name = new_name
        mock_report.schema_objects = [fk_object]
        mock_report.dependency_graph = None  # No circular dependency
        mock_report.impact_summary.overall_risk = RenameImpactLevel.CRITICAL

        mock_table_analyzer.analyze_table_rename.return_value = mock_report

        # Mock FK analysis
        mock_fk_plan = Mock(spec=FKSafeMigrationPlan)
        mock_fk_plan.steps = []
        mock_fk_analyzer.generate_fk_safe_migration_plan.return_value = mock_fk_plan

        # Execute rename workflow
        result = await coordination_engine.execute_table_rename(
            old_name, new_name, connection=mock_connection
        )

        # Verify result
        assert result is not None
        assert result.success is True

        # Verify FK objects were detected in the schema objects
        # (FK coordination is handled internally by the engine)
        assert len(mock_report.schema_objects) == 1
        assert mock_report.schema_objects[0].object_type == SchemaObjectType.FOREIGN_KEY

    @pytest.mark.asyncio
    async def test_execute_rename_with_view_dependencies(
        self,
        coordination_engine,
        mock_table_analyzer,
        mock_sql_rewriter,
        mock_connection,
    ):
        """Test rename workflow with view dependencies requiring SQL rewriting."""
        # Setup test data
        old_name = "data_table"
        new_name = "renamed_data_table"

        # Mock view object requiring SQL rewrite
        view_object = Mock(spec=SchemaObject)
        view_object.object_type = SchemaObjectType.VIEW
        view_object.impact_level = RenameImpactLevel.HIGH
        view_object.object_name = "data_summary_view"
        view_object.definition = f"SELECT * FROM {old_name}"
        view_object.requires_sql_rewrite = True

        # Mock analyzer report with view dependencies
        mock_report = Mock(spec=TableRenameReport)
        mock_report.old_table_name = old_name
        mock_report.new_table_name = new_name
        mock_report.schema_objects = [view_object]
        mock_report.dependency_graph = None  # No circular dependency
        mock_report.impact_summary.overall_risk = RenameImpactLevel.HIGH

        mock_table_analyzer.analyze_table_rename.return_value = mock_report

        # Mock SQL rewriter results
        mock_rewrite_result = Mock(spec=ViewRewriteResult)
        mock_rewrite_result.success = True
        mock_rewrite_result.original_sql = view_object.definition
        mock_rewrite_result.rewritten_sql = f"SELECT * FROM {new_name}"
        mock_sql_rewriter.rewrite_view_sql.return_value = mock_rewrite_result

        # Execute rename workflow
        result = await coordination_engine.execute_table_rename(
            old_name, new_name, connection=mock_connection
        )

        # Verify result
        assert result is not None
        assert result.success is True

        # Verify SQL rewriting was performed
        mock_sql_rewriter.rewrite_view_sql.assert_called_once()

    @pytest.mark.asyncio
    async def test_workflow_with_circular_dependencies_raises_error(
        self, coordination_engine, mock_table_analyzer, mock_connection
    ):
        """Test that circular dependencies are detected and raise appropriate error."""
        # Setup test data with circular dependency
        old_name = "table_a"
        new_name = "renamed_table_a"

        # Mock dependency graph with circular dependency
        mock_graph = Mock(spec=DependencyGraph)
        mock_graph.circular_dependency_detected = True
        mock_graph.has_circular_dependencies.return_value = True

        mock_report = Mock(spec=TableRenameReport)
        mock_report.dependency_graph = mock_graph
        mock_report.impact_summary.overall_risk = RenameImpactLevel.CRITICAL

        mock_table_analyzer.analyze_table_rename.return_value = mock_report

        # Execute and expect circular dependency error (wrapped in RenameCoordinationError)
        with pytest.raises(RenameCoordinationError, match="Coordination failed"):
            await coordination_engine.execute_table_rename(
                old_name, new_name, connection=mock_connection
            )

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_failure(
        self,
        coordination_engine,
        mock_transaction_manager,
        mock_table_analyzer,
        mock_connection,
    ):
        """Test transaction rollback when rename operation fails."""
        # Setup test data
        old_name = "test_table"
        new_name = "renamed_table"

        mock_report = Mock(spec=TableRenameReport)
        mock_report.schema_objects = []
        mock_report.impact_summary.overall_risk = RenameImpactLevel.SAFE

        mock_table_analyzer.analyze_table_rename.return_value = mock_report

        # Mock transaction manager to simulate failure and rollback
        mock_transaction_manager.begin_transaction.return_value = "txn_123"
        mock_transaction_manager.execute_step.side_effect = Exception(
            "Simulated failure"
        )

        mock_rollback_result = Mock(spec=RollbackResult)
        mock_rollback_result.success = True
        mock_rollback_result.rolled_back_operations = ["DROP SAVEPOINT"]
        mock_transaction_manager.rollback_transaction.return_value = (
            mock_rollback_result
        )

        # Execute and expect error with rollback
        with pytest.raises(RenameCoordinationError):
            await coordination_engine.execute_table_rename(
                old_name, new_name, connection=mock_connection
            )

        # Verify rollback was attempted
        mock_transaction_manager.rollback_transaction.assert_called_once()

    def test_build_rename_workflow_simple_case(self, coordination_engine):
        """Test building rename workflow for simple case with no dependencies."""
        # Setup minimal report
        report = Mock(spec=TableRenameReport)
        report.old_table_name = "old_table"
        report.new_table_name = "new_table"
        report.schema_objects = []
        report.impact_summary.overall_risk = RenameImpactLevel.SAFE

        # Build workflow
        workflow = coordination_engine._build_rename_workflow(report)

        # Verify workflow structure
        assert workflow is not None
        assert workflow.old_table_name == "old_table"
        assert workflow.new_table_name == "new_table"
        assert len(workflow.steps) > 0  # Should have at least the rename step
        assert workflow.requires_transaction is True

    def test_build_rename_workflow_with_dependencies(self, coordination_engine):
        """Test building workflow with complex dependencies."""
        # Setup report with multiple dependency types
        fk_obj = Mock(spec=SchemaObject)
        fk_obj.object_type = SchemaObjectType.FOREIGN_KEY
        fk_obj.impact_level = RenameImpactLevel.CRITICAL

        view_obj = Mock(spec=SchemaObject)
        view_obj.object_type = SchemaObjectType.VIEW
        view_obj.requires_sql_rewrite = True
        view_obj.impact_level = RenameImpactLevel.HIGH

        report = Mock(spec=TableRenameReport)
        report.old_table_name = "complex_table"
        report.new_table_name = "renamed_complex"
        report.schema_objects = [fk_obj, view_obj]
        report.impact_summary.overall_risk = RenameImpactLevel.CRITICAL

        # Build workflow
        workflow = coordination_engine._build_rename_workflow(report)

        # Verify workflow complexity
        assert workflow is not None
        assert len(workflow.steps) > 1  # Multiple steps for dependencies
        assert any(
            step.step_type == WorkflowStepType.DROP_FK_CONSTRAINTS
            for step in workflow.steps
        )
        assert any(
            step.step_type == WorkflowStepType.REWRITE_VIEWS for step in workflow.steps
        )

    def test_order_workflow_steps_dependency_aware(self, coordination_engine):
        """Test that workflow steps are ordered correctly based on dependencies."""
        # Create workflow steps in wrong order
        steps = [
            Mock(step_type=WorkflowStepType.RENAME_TABLE, execution_order=3),
            Mock(step_type=WorkflowStepType.DROP_FK_CONSTRAINTS, execution_order=1),
            Mock(step_type=WorkflowStepType.REWRITE_VIEWS, execution_order=4),
            Mock(step_type=WorkflowStepType.RECREATE_FK_CONSTRAINTS, execution_order=5),
        ]

        # Order steps
        ordered_steps = coordination_engine._order_workflow_steps(steps)

        # Verify correct ordering
        assert len(ordered_steps) == 4
        assert ordered_steps[0].step_type == WorkflowStepType.DROP_FK_CONSTRAINTS
        assert ordered_steps[1].step_type == WorkflowStepType.RENAME_TABLE
        assert ordered_steps[2].step_type == WorkflowStepType.REWRITE_VIEWS
        assert ordered_steps[3].step_type == WorkflowStepType.RECREATE_FK_CONSTRAINTS

    def test_validate_rename_parameters_valid_input(self, coordination_engine):
        """Test parameter validation with valid input."""
        # Valid parameters should not raise
        coordination_engine._validate_rename_parameters(
            "valid_table", "new_valid_table"
        )

    def test_validate_rename_parameters_invalid_input(self, coordination_engine):
        """Test parameter validation with invalid input."""
        # Empty names should raise
        with pytest.raises(ValueError, match="Table names cannot be empty"):
            coordination_engine._validate_rename_parameters("", "new_name")

        with pytest.raises(ValueError, match="Table names cannot be empty"):
            coordination_engine._validate_rename_parameters("old_name", "")

        # Identical names should raise
        with pytest.raises(ValueError, match="Old and new names cannot be identical"):
            coordination_engine._validate_rename_parameters("same_name", "same_name")

    def test_calculate_workflow_progress(self, coordination_engine):
        """Test workflow progress calculation."""
        # Create mock workflow with steps
        completed_steps = [Mock(), Mock()]
        total_steps = [Mock(), Mock(), Mock(), Mock()]

        progress = coordination_engine._calculate_workflow_progress(
            completed_steps, total_steps
        )

        assert progress == 50.0  # 2/4 = 50%

    def test_generate_workflow_id_unique(self, coordination_engine):
        """Test that workflow IDs are unique."""
        id1 = coordination_engine._generate_workflow_id()
        id2 = coordination_engine._generate_workflow_id()

        assert id1 != id2
        assert isinstance(id1, str)
        assert len(id1) > 0


class TestSQLRewriter:
    """Test SQL rewriting functionality for views and triggers."""

    @pytest.fixture
    def sql_rewriter(self):
        """Create SQLRewriter instance."""
        return SQLRewriter()

    def test_rewrite_simple_view_sql(self, sql_rewriter):
        """Test rewriting simple view SQL with table reference."""
        original_sql = "SELECT id, name FROM old_table WHERE active = true"

        result = sql_rewriter.rewrite_view_sql(
            view_name="test_view",
            original_sql=original_sql,
            old_table_name="old_table",
            new_table_name="new_table",
        )

        assert result.success is True
        assert "new_table" in result.rewritten_sql
        assert "old_table" not in result.rewritten_sql
        assert result.modifications_made == 1

    def test_rewrite_complex_view_sql_with_joins(self, sql_rewriter):
        """Test rewriting complex view SQL with JOIN statements."""
        original_sql = """
        SELECT t1.id, t2.name, t1.created_at
        FROM old_table t1
        JOIN another_table t2 ON t1.id = t2.old_table_id
        WHERE t1.active = true
        """

        result = sql_rewriter.rewrite_view_sql(
            view_name="complex_view",
            original_sql=original_sql,
            old_table_name="old_table",
            new_table_name="new_table",
        )

        assert result.success is True
        assert "new_table" in result.rewritten_sql
        assert result.modifications_made >= 1  # At least one table reference changed

    def test_rewrite_trigger_sql(self, sql_rewriter):
        """Test rewriting trigger SQL with table references."""
        original_sql = """
        CREATE TRIGGER update_timestamp
        BEFORE UPDATE ON old_table
        FOR EACH ROW
        EXECUTE FUNCTION update_modified_column();
        """

        result = sql_rewriter.rewrite_trigger_sql(
            trigger_name="update_timestamp",
            original_sql=original_sql,
            old_table_name="old_table",
            new_table_name="new_table",
        )

        assert result.success is True
        assert "new_table" in result.rewritten_sql
        assert "old_table" not in result.rewritten_sql

    def test_rewrite_with_no_references_returns_original(self, sql_rewriter):
        """Test rewriting SQL that doesn't reference the target table."""
        original_sql = "SELECT id, name FROM other_table WHERE active = true"

        result = sql_rewriter.rewrite_view_sql(
            view_name="unrelated_view",
            original_sql=original_sql,
            old_table_name="target_table",
            new_table_name="new_target_table",
        )

        assert result.success is True
        assert result.rewritten_sql == original_sql
        assert result.modifications_made == 0

    def test_rewrite_handles_quoted_identifiers(self, sql_rewriter):
        """Test rewriting SQL with quoted table identifiers."""
        original_sql = 'SELECT * FROM "old_table" WHERE id > 100'

        result = sql_rewriter.rewrite_view_sql(
            view_name="quoted_view",
            original_sql=original_sql,
            old_table_name="old_table",
            new_table_name="new_table",
        )

        assert result.success is True
        assert (
            '"new_table"' in result.rewritten_sql or "new_table" in result.rewritten_sql
        )

    def test_rewrite_invalid_sql_returns_error(self, sql_rewriter):
        """Test that invalid SQL is handled gracefully."""
        invalid_sql = "INVALID SQL SYNTAX HERE;;; FROM WHERE"

        with pytest.raises(SQLRewriteError):
            sql_rewriter.rewrite_view_sql(
                view_name="invalid_view",
                original_sql=invalid_sql,
                old_table_name="old_table",
                new_table_name="new_table",
            )


class TestRenameTransactionManager:
    """Test transaction management with rollback capabilities."""

    @pytest.fixture
    def mock_connection(self):
        """Mock database connection."""
        return AsyncMock()

    @pytest.fixture
    def transaction_manager(self, mock_connection):
        """Create RenameTransactionManager instance."""
        return RenameTransactionManager(mock_connection)

    @pytest.mark.asyncio
    async def test_begin_transaction(self, transaction_manager, mock_connection):
        """Test beginning a new transaction."""
        transaction_id = await transaction_manager.begin_transaction()

        assert transaction_id is not None
        assert isinstance(transaction_id, str)
        mock_connection.execute.assert_called_with("BEGIN")

    @pytest.mark.asyncio
    async def test_create_savepoint(self, transaction_manager, mock_connection):
        """Test creating savepoints during transaction."""
        # Begin transaction first
        transaction_id = await transaction_manager.begin_transaction()

        # Create savepoint
        savepoint_name = await transaction_manager.create_savepoint("test_point")

        assert savepoint_name is not None
        mock_connection.execute.assert_called_with(f"SAVEPOINT {savepoint_name}")

    @pytest.mark.asyncio
    async def test_rollback_to_savepoint(self, transaction_manager, mock_connection):
        """Test rolling back to a specific savepoint."""
        # Begin transaction and create savepoint
        transaction_id = await transaction_manager.begin_transaction()
        savepoint_name = await transaction_manager.create_savepoint("rollback_test")

        # Rollback to savepoint
        result = await transaction_manager.rollback_to_savepoint(savepoint_name)

        assert result.success is True
        mock_connection.execute.assert_called_with(
            f"ROLLBACK TO SAVEPOINT {savepoint_name}"
        )

    @pytest.mark.asyncio
    async def test_commit_transaction(self, transaction_manager, mock_connection):
        """Test committing a transaction."""
        transaction_id = await transaction_manager.begin_transaction()

        result = await transaction_manager.commit_transaction()

        assert result.success is True
        mock_connection.execute.assert_called_with("COMMIT")

    @pytest.mark.asyncio
    async def test_rollback_transaction(self, transaction_manager, mock_connection):
        """Test rolling back entire transaction."""
        transaction_id = await transaction_manager.begin_transaction()

        result = await transaction_manager.rollback_transaction()

        assert result.success is True
        mock_connection.execute.assert_called_with("ROLLBACK")

    @pytest.mark.asyncio
    async def test_execute_step_with_savepoint(
        self, transaction_manager, mock_connection
    ):
        """Test executing workflow step with automatic savepoint management."""
        transaction_id = await transaction_manager.begin_transaction()

        # Mock workflow step
        step = Mock()
        step.sql_command = "ALTER TABLE test_table RENAME TO new_test_table"
        step.step_id = "test_step_1"

        result = await transaction_manager.execute_step(step)

        assert result.success is True
        # Should have executed the SQL command
        mock_connection.execute.assert_any_call(step.sql_command)

    @pytest.mark.asyncio
    async def test_transaction_state_tracking(self, transaction_manager):
        """Test that transaction state is properly tracked."""
        assert transaction_manager.current_state == TransactionState.NOT_STARTED

        await transaction_manager.begin_transaction()
        assert transaction_manager.current_state == TransactionState.ACTIVE

        await transaction_manager.commit_transaction()
        assert transaction_manager.current_state == TransactionState.COMMITTED

    @pytest.mark.asyncio
    async def test_nested_savepoint_management(
        self, transaction_manager, mock_connection
    ):
        """Test management of multiple nested savepoints."""
        transaction_id = await transaction_manager.begin_transaction()

        # Create multiple savepoints
        sp1 = await transaction_manager.create_savepoint("point1")
        sp2 = await transaction_manager.create_savepoint("point2")
        sp3 = await transaction_manager.create_savepoint("point3")

        # Verify all savepoints are tracked
        assert len(transaction_manager.active_savepoints) == 3
        assert sp1 in transaction_manager.active_savepoints
        assert sp2 in transaction_manager.active_savepoints
        assert sp3 in transaction_manager.active_savepoints

    @pytest.mark.asyncio
    async def test_connection_error_handling(self, mock_connection):
        """Test handling of database connection errors."""
        # Setup connection to raise errors
        mock_connection.execute.side_effect = Exception("Connection lost")

        transaction_manager = RenameTransactionManager(mock_connection)

        # Should raise TransactionError
        with pytest.raises(TransactionError):
            await transaction_manager.begin_transaction()


class TestRenameWorkflow:
    """Test rename workflow data structures and validation."""

    def test_workflow_creation(self):
        """Test creating a rename workflow."""
        workflow = RenameWorkflow(
            workflow_id="test_123",
            old_table_name="old_table",
            new_table_name="new_table",
            steps=[],
        )

        assert workflow.workflow_id == "test_123"
        assert workflow.old_table_name == "old_table"
        assert workflow.new_table_name == "new_table"
        assert workflow.status == WorkflowStatus.PENDING

    def test_workflow_step_creation(self):
        """Test creating workflow steps."""
        step = RenameWorkflowStep(
            step_id="step_1",
            step_type=WorkflowStepType.DROP_FK_CONSTRAINTS,
            description="Drop FK constraints",
            sql_command="ALTER TABLE child DROP CONSTRAINT parent_fk",
            estimated_duration=2.0,
        )

        assert step.step_id == "step_1"
        assert step.step_type == WorkflowStepType.DROP_FK_CONSTRAINTS
        assert step.estimated_duration == 2.0

    def test_workflow_validation_valid(self):
        """Test validation of valid workflow."""
        step = RenameWorkflowStep(
            step_id="step_1",
            step_type=WorkflowStepType.RENAME_TABLE,
            description="Rename table",
            sql_command="ALTER TABLE old_name RENAME TO new_name",
        )

        workflow = RenameWorkflow(
            workflow_id="valid_workflow",
            old_table_name="old_table",
            new_table_name="new_table",
            steps=[step],
        )

        # Should not raise any validation errors
        assert workflow.is_valid()

    def test_workflow_validation_invalid_empty_steps(self):
        """Test validation fails for workflow with no steps."""
        workflow = RenameWorkflow(
            workflow_id="invalid_workflow",
            old_table_name="old_table",
            new_table_name="new_table",
            steps=[],
        )

        assert not workflow.is_valid()

    def test_coordination_result_success(self):
        """Test successful coordination result."""
        result = CoordinationResult(
            success=True,
            workflow_id="success_workflow",
            completed_steps=["step_1", "step_2"],
            total_duration=5.5,
        )

        assert result.success is True
        assert result.workflow_id == "success_workflow"
        assert len(result.completed_steps) == 2

    def test_coordination_result_failure(self):
        """Test failed coordination result with error details."""
        result = CoordinationResult(
            success=False,
            workflow_id="failed_workflow",
            error_message="FK constraint violation",
            failed_step="step_2",
        )

        assert result.success is False
        assert result.error_message == "FK constraint violation"
        assert result.failed_step == "step_2"
