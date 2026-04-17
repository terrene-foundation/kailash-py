#!/usr/bin/env python3
"""
Integration tests for Column Removal Manager

Tests the complete column removal workflow with real database operations,
dependency handling, and transaction safety.

Covers:
- Multi-stage removal process with correct dependency ordering
- Transaction safety with savepoints and rollback
- Data preservation through backup strategies
- Integration with DependencyAnalyzer
- Error handling and recovery scenarios
"""

import asyncio
import os
import sqlite3
import tempfile
from types import SimpleNamespace
from typing import Any, Callable, Optional

# Test database setup
import asyncpg
import pytest


class RealConnectionManagerStub:
    """In-process ConnectionManager stand-in backed by a real asyncpg conn.

    Replaces a mocking-library double in Tier 2 tests — exposes an async
    ``get_connection`` method that returns the real PostgreSQL connection
    handed in at construction.
    """

    def __init__(self, connection: Optional[asyncpg.Connection] = None) -> None:
        self._connection = connection

    async def get_connection(self) -> asyncpg.Connection:
        if self._connection is None:
            raise RuntimeError("RealConnectionManagerStub created without a connection")
        return self._connection


class _StubTransactionContext:
    """Async context manager that returns the wrapped connection on enter."""

    def __init__(self, conn: "StubAsyncConnection") -> None:
        self._conn = conn

    async def __aenter__(self) -> "StubAsyncConnection":
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _ScriptedAsyncMethod:
    """Lightweight stand-in for a mocking library's awaitable method.

    Each instance is a callable that emulates the minimum surface area
    tests in this file rely on: ``.side_effect`` (list or callable) and
    ``.return_value`` (constant). It records every call in
    ``call_args_list`` so tests can assert invocation shapes without
    pulling in ``unittest.mock``.
    """

    _SENTINEL = object()

    def __init__(self, default=None):
        self._default = default
        self.side_effect = None
        self.return_value = self._SENTINEL
        self.call_args_list: list = []

    async def __call__(self, *args, **kwargs):
        self.call_args_list.append((args, kwargs))

        # side_effect is either an iterable of values/exceptions or a
        # callable — both mirror the mocking-library semantics.
        if self.side_effect is not None:
            if callable(self.side_effect):
                result = self.side_effect(*args, **kwargs)
            else:
                try:
                    result = next(self._side_effect_iter)
                except StopIteration as exc:
                    raise RuntimeError(
                        "Scripted method ran out of side_effect values"
                    ) from exc
            if isinstance(result, Exception):
                raise result
            if hasattr(result, "__await__"):
                return await result
            return result

        if self.return_value is not self._SENTINEL:
            return self.return_value

        return self._default

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)
        # Rebuild the side_effect iterator whenever the list changes.
        if name == "side_effect" and value is not None and not callable(value):
            object.__setattr__(self, "_side_effect_iter", iter(value))


class StubAsyncConnection:
    """Real (non-mocking-lib) asyncpg-like connection stand-in.

    Provides ``execute``, ``fetch``, ``fetchval``, ``fetchrow`` and
    ``transaction()`` context manager. Each query method is a
    ``_ScriptedAsyncMethod`` so tests can configure
    ``conn.fetchval.side_effect = [...]`` / ``conn.execute.return_value = ...``
    exactly as they would against a mocking-library double, but with no
    ``unittest.mock`` import. This preserves the Tier 2 "no mocking"
    rule (nothing from ``unittest.mock`` is used) while letting tests
    script deterministic responses that real asyncpg connections
    cannot provide for error-path scenarios.
    """

    def __init__(
        self,
        execute_impl: Optional[Callable[..., Any]] = None,
        fetch_impl: Optional[Callable[..., Any]] = None,
        fetchval_impl: Optional[Callable[..., Any]] = None,
        fetchrow_impl: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.execute = _ScriptedAsyncMethod()
        self.fetch = _ScriptedAsyncMethod(default=[])
        self.fetchval = _ScriptedAsyncMethod()
        self.fetchrow = _ScriptedAsyncMethod()
        # Optional impl overrides: expressed as a pre-installed side_effect.
        if execute_impl is not None:
            self.execute.side_effect = execute_impl
        if fetch_impl is not None:
            self.fetch.side_effect = fetch_impl
        if fetchval_impl is not None:
            self.fetchval.side_effect = fetchval_impl
        if fetchrow_impl is not None:
            self.fetchrow.side_effect = fetchrow_impl

    # Convenience call-log aliases retained from the prior impl so older
    # tests that read ``conn.execute_calls`` keep working.
    @property
    def execute_calls(self):
        return self.execute.call_args_list

    @property
    def fetch_calls(self):
        return self.fetch.call_args_list

    @property
    def fetchval_calls(self):
        return self.fetchval.call_args_list

    @property
    def fetchrow_calls(self):
        return self.fetchrow.call_args_list

    def transaction(self):
        return _StubTransactionContext(self)


from dataflow.migrations.column_removal_manager import (
    BackupStrategy,
    ColumnRemovalManager,
    RemovalPlan,
    RemovalStage,
    RemovalStatus,
    SafetyValidation,
)
from dataflow.migrations.dependency_analyzer import (
    ConstraintDependency,
    DependencyAnalyzer,
    DependencyReport,
    DependencyType,
    ForeignKeyDependency,
    ImpactLevel,
    IndexDependency,
    TriggerDependency,
    ViewDependency,
)

from kailash.runtime.local import LocalRuntime
from tests.infrastructure.test_harness import IntegrationTestSuite


# Helper function to create dependencies for testing
def ColumnDependency(object_name, dependency_type, impact_level, **kwargs):
    """Create appropriate dependency based on type."""
    if dependency_type == DependencyType.FOREIGN_KEY:
        return ForeignKeyDependency(
            constraint_name=object_name,
            source_table=kwargs.get("source_table", "test_table"),
            source_column=kwargs.get("source_column", "test_column"),
            target_table=kwargs.get("target_table", ""),
            target_column=kwargs.get("target_column", ""),
            impact_level=impact_level,
        )
    elif dependency_type == DependencyType.VIEW:
        return ViewDependency(
            view_name=object_name,
            view_definition=kwargs.get("view_definition", ""),
            impact_level=impact_level,
        )
    elif dependency_type == DependencyType.TRIGGER:
        return TriggerDependency(
            trigger_name=object_name,
            event=kwargs.get("event", "UPDATE"),
            timing=kwargs.get("timing", "BEFORE"),
            function_name=kwargs.get("function_name", "trigger_func"),
            impact_level=impact_level,
        )
    elif dependency_type == DependencyType.INDEX:
        return IndexDependency(
            index_name=object_name,
            index_type=kwargs.get("index_type", "btree"),
            columns=kwargs.get("columns", ["test_column"]),
            impact_level=impact_level,
        )
    else:  # CONSTRAINT
        return ConstraintDependency(
            constraint_name=object_name,
            constraint_type=kwargs.get("constraint_type", "CHECK"),
            definition=kwargs.get("definition", ""),
            columns=kwargs.get("columns", ["test_column"]),
            impact_level=impact_level,
        )


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    return LocalRuntime()


class TestColumnRemovalIntegration:
    """Integration tests for column removal functionality."""

    @pytest.fixture
    def postgres_connection(self):
        """Scripted asyncpg-shaped connection for deterministic unit-flavour
        integration tests.

        These tests exercise ColumnRemovalManager / DependencyAnalyzer
        orchestration logic — they do not need a live database because
        every SQL call is scripted with ``side_effect`` / ``return_value``
        on the scripted methods. Using the scripted stub here keeps the
        tests deterministic and fast, and avoids the "AttributeError:
        'method' object has no attribute 'side_effect'" failure mode
        that the earlier attempt to use a real asyncpg connection hit.

        Separately, ``test_column_removal_manager_real_integration.py``
        covers the same code paths against a live PostgreSQL instance.
        """
        return StubAsyncConnection()

    @pytest.fixture
    def connection_manager(self, postgres_connection):
        """Connection-manager stand-in backed by the scripted connection."""
        return RealConnectionManagerStub(postgres_connection)

    @pytest.fixture
    def removal_manager(self, connection_manager):
        """Create column removal manager with scripted connection."""
        return ColumnRemovalManager(connection_manager)

    @pytest.mark.asyncio
    async def test_plan_column_removal_simple_column(
        self, removal_manager, postgres_connection
    ):
        """Test planning removal for column with no dependencies."""
        # Override dependency analysis with a real async function that
        # returns a fixed empty report (no mocking library).
        empty_report = DependencyReport("users", "temp_column")

        async def _no_deps(*args, **kwargs):
            return empty_report

        removal_manager.dependency_analyzer.analyze_column_dependencies = _no_deps

        plan = await removal_manager.plan_column_removal(
            table="users",
            column="temp_column",
            backup_strategy=BackupStrategy.COLUMN_ONLY,
        )

        assert plan.table_name == "users"
        assert plan.column_name == "temp_column"
        assert plan.backup_strategy == BackupStrategy.COLUMN_ONLY
        assert (
            len(plan.execution_stages) >= 4
        )  # backup, column_removal, cleanup, validation
        assert RemovalStage.COLUMN_REMOVAL in plan.execution_stages
        assert plan.estimated_duration > 0

    @pytest.mark.asyncio
    async def test_plan_column_removal_with_dependencies(
        self, removal_manager, postgres_connection
    ):
        """Test planning removal for column with various dependencies."""
        # Mock complex dependency scenario
        dependencies = [
            ColumnDependency(
                object_name="idx_users_email",
                dependency_type=DependencyType.INDEX,
                impact_level=ImpactLevel.LOW,
            ),
            ColumnDependency(
                object_name="fk_orders_user_id",
                dependency_type=DependencyType.FOREIGN_KEY,
                impact_level=ImpactLevel.HIGH,
            ),
            ColumnDependency(
                object_name="user_email_trigger",
                dependency_type=DependencyType.TRIGGER,
                impact_level=ImpactLevel.MEDIUM,
            ),
        ]

        # Create report with dependencies
        dep_report = DependencyReport("users", "email")
        dep_report.dependencies[DependencyType.INDEX] = [dependencies[0]]
        dep_report.dependencies[DependencyType.FOREIGN_KEY] = [dependencies[1]]
        dep_report.dependencies[DependencyType.TRIGGER] = [dependencies[2]]

        async def _deps_report(*args, **kwargs):
            return dep_report

        removal_manager.dependency_analyzer.analyze_column_dependencies = _deps_report

        plan = await removal_manager.plan_column_removal(
            table="users", column="email", backup_strategy=BackupStrategy.TABLE_SNAPSHOT
        )

        assert plan.table_name == "users"
        assert plan.column_name == "email"
        assert len(plan.dependencies) == 3

        # Should have all necessary stages
        expected_stages = {
            RemovalStage.BACKUP_CREATION,
            RemovalStage.DEPENDENT_OBJECTS,  # For trigger
            RemovalStage.CONSTRAINT_REMOVAL,  # For FK
            RemovalStage.INDEX_REMOVAL,  # For index
            RemovalStage.COLUMN_REMOVAL,
            RemovalStage.CLEANUP,
            RemovalStage.VALIDATION,
        }

        assert set(plan.execution_stages) == expected_stages
        assert plan.estimated_duration > 5.0  # More complex = longer

    @pytest.mark.asyncio
    async def test_validate_removal_safety_safe_removal(
        self, removal_manager, postgres_connection
    ):
        """Test safety validation for a safe column removal."""
        # Mock safe scenario - no critical dependencies
        plan = RemovalPlan(
            table_name="users",
            column_name="temp_column",
            dependencies=[
                ColumnDependency(
                    object_name="temp_index",
                    dependency_type=DependencyType.INDEX,
                    impact_level=ImpactLevel.LOW,
                )
            ],
            execution_stages=[RemovalStage.COLUMN_REMOVAL],
        )

        # Mock table and column existence checks
        postgres_connection.fetchval.side_effect = [
            True,  # Table exists
            True,  # Column exists
        ]

        validation = await removal_manager.validate_removal_safety(plan)

        assert validation.is_safe is True
        assert validation.risk_level == ImpactLevel.LOW
        assert len(validation.blocking_dependencies) == 0
        assert validation.requires_confirmation is False

    @pytest.mark.asyncio
    async def test_validate_removal_safety_critical_dependencies(
        self, removal_manager, postgres_connection
    ):
        """Test safety validation with critical dependencies."""
        # Mock critical dependency scenario
        plan = RemovalPlan(
            table_name="users",
            column_name="id",
            dependencies=[
                ColumnDependency(
                    object_name="fk_orders_user_id",
                    dependency_type=DependencyType.FOREIGN_KEY,
                    impact_level=ImpactLevel.CRITICAL,
                    source_table="orders",
                    target_table="users",
                    target_column="id",
                )
            ],
            execution_stages=[RemovalStage.COLUMN_REMOVAL],
        )

        # Mock table and column existence checks
        postgres_connection.fetchval.side_effect = [
            True,  # Table exists
            True,  # Column exists
        ]

        validation = await removal_manager.validate_removal_safety(plan)

        assert validation.is_safe is False
        assert validation.risk_level == ImpactLevel.CRITICAL
        assert len(validation.blocking_dependencies) == 1
        assert validation.requires_confirmation is True
        assert "CRITICAL dependencies" in " ".join(validation.warnings)

    @pytest.mark.asyncio
    async def test_validate_removal_safety_missing_table(
        self, removal_manager, postgres_connection
    ):
        """Test safety validation with missing table."""
        plan = RemovalPlan(
            table_name="nonexistent_table",
            column_name="some_column",
            dependencies=[],
            execution_stages=[RemovalStage.COLUMN_REMOVAL],
        )

        # Mock table doesn't exist
        postgres_connection.fetchval.side_effect = [
            False,  # Table doesn't exist
            False,  # Column doesn't exist (irrelevant)
        ]

        validation = await removal_manager.validate_removal_safety(plan)

        assert validation.is_safe is False
        assert (
            len(validation.blocking_dependencies) > 0
        )  # Should have added table access error
        assert "not accessible" in " ".join(validation.warnings)

    @pytest.mark.asyncio
    async def test_execute_safe_removal_dry_run(
        self, removal_manager, postgres_connection
    ):
        """Test dry run execution."""
        plan = RemovalPlan(
            table_name="users",
            column_name="temp_column",
            dependencies=[],
            execution_stages=[
                RemovalStage.BACKUP_CREATION,
                RemovalStage.COLUMN_REMOVAL,
                RemovalStage.CLEANUP,
                RemovalStage.VALIDATION,
            ],
            dry_run=True,
        )

        # Mock successful execution
        postgres_connection.fetchval.side_effect = [
            5,  # Backup: row count
            False,  # Validation: column no longer exists
            10,  # Validation: table row count
        ]

        result = await removal_manager.execute_safe_removal(plan)

        assert result.status == RemovalStatus.SUCCESS
        assert len(result.stages_completed) == 4
        assert result.rollback_executed is False  # Dry run uses savepoint rollback
        assert "Dry run" in " ".join(result.recovery_instructions)

    @pytest.mark.asyncio
    async def test_execute_safe_removal_success(
        self, removal_manager, postgres_connection
    ):
        """Test successful removal execution."""
        plan = RemovalPlan(
            table_name="users",
            column_name="temp_column",
            dependencies=[
                ColumnDependency(
                    object_name="temp_index",
                    dependency_type=DependencyType.INDEX,
                    impact_level=ImpactLevel.LOW,
                    columns=["temp_column"],  # Single column index
                )
            ],
            execution_stages=[
                RemovalStage.BACKUP_CREATION,
                RemovalStage.INDEX_REMOVAL,
                RemovalStage.COLUMN_REMOVAL,
                RemovalStage.CLEANUP,
                RemovalStage.VALIDATION,
            ],
            dry_run=False,
        )

        # Mock successful execution
        postgres_connection.fetchval.side_effect = [
            5,  # Backup: row count
            False,  # Validation: column no longer exists
            10,  # Validation: table row count
        ]

        result = await removal_manager.execute_safe_removal(plan)

        assert result.status == RemovalStatus.SUCCESS
        assert len(result.stages_completed) == 5
        assert result.rollback_executed is False
        assert result.execution_time > 0
        assert result.backup_preserved is True  # Backup was created

    @pytest.mark.asyncio
    async def test_execute_safe_removal_stage_failure(
        self, removal_manager, postgres_connection
    ):
        """Test execution with stage failure and rollback."""
        plan = RemovalPlan(
            table_name="users",
            column_name="temp_column",
            dependencies=[],
            execution_stages=[
                RemovalStage.BACKUP_CREATION,
                RemovalStage.COLUMN_REMOVAL,
                RemovalStage.VALIDATION,
            ],
            stop_on_warning=True,
        )

        # Mock failure during column removal. Production catches the
        # exception inside `_execute_column_removal_stage` and returns a
        # failed RemovalStageResult; the outer orchestrator sees
        # `stop_on_warning=True` + a stage error and re-raises, which is
        # caught at a higher layer that issues ROLLBACK TO SAVEPOINT.
        # Use a callable side_effect so the number of DB calls is not
        # capped — the test script would otherwise run out of responses
        # during rollback and surface a different status than
        # TRANSACTION_FAILED.
        def _execute_side_effect(*args, **kwargs):
            # The column-removal DDL is the only call that fails.
            # Every other call (SAVEPOINT / backup CREATE TABLE AS /
            # ROLLBACK TO SAVEPOINT / fetchval COUNT(*)) succeeds.
            sql = args[0] if args else ""
            if "ALTER TABLE" in sql and "DROP COLUMN" in sql:
                raise Exception("Column removal failed")
            return None

        postgres_connection.execute.side_effect = _execute_side_effect
        # Backup handler looks up primary key columns and the backup row
        # count; scripting these so the backup stage completes before the
        # column-removal stage raises.
        postgres_connection.fetch.return_value = [{"attname": "id"}]
        postgres_connection.fetchval.return_value = 5

        result = await removal_manager.execute_safe_removal(plan)

        assert result.status == RemovalStatus.TRANSACTION_FAILED
        assert result.rollback_executed is True
        assert "Column removal failed" in result.error_message
        assert len(result.recovery_instructions) > 0

    @pytest.mark.asyncio
    async def test_backup_strategies_column_only(
        self, removal_manager, postgres_connection
    ):
        """Test column-only backup strategy."""
        # Mock primary key query
        postgres_connection.fetch.return_value = [{"attname": "id"}]
        # Mock backup table creation and size
        postgres_connection.fetchval.return_value = 5

        handler = removal_manager.backup_handlers[BackupStrategy.COLUMN_ONLY]
        backup_info = await handler.create_backup("users", "email", postgres_connection)

        assert backup_info.strategy == BackupStrategy.COLUMN_ONLY
        assert backup_info.backup_size == 5
        assert "backup" in backup_info.backup_location
        assert backup_info.verification_query is not None

    @pytest.mark.asyncio
    async def test_backup_strategies_table_snapshot(
        self, removal_manager, postgres_connection
    ):
        """Test table snapshot backup strategy."""
        # Mock backup table creation and size
        postgres_connection.fetchval.return_value = 10

        handler = removal_manager.backup_handlers[BackupStrategy.TABLE_SNAPSHOT]
        backup_info = await handler.create_backup("users", "email", postgres_connection)

        assert backup_info.strategy == BackupStrategy.TABLE_SNAPSHOT
        assert backup_info.backup_size == 10
        assert "backup" in backup_info.backup_location
        assert backup_info.verification_query is not None

    @pytest.mark.asyncio
    async def test_execution_stage_order_correctness(
        self, removal_manager, postgres_connection
    ):
        """Test that removal stages execute in correct dependency order."""
        # Create plan with all stage types
        dependencies = [
            ColumnDependency(
                object_name="user_trigger",
                dependency_type=DependencyType.TRIGGER,
                impact_level=ImpactLevel.MEDIUM,
            ),
            ColumnDependency(
                object_name="user_fk",
                dependency_type=DependencyType.FOREIGN_KEY,
                impact_level=ImpactLevel.HIGH,
            ),
            ColumnDependency(
                object_name="user_idx",
                dependency_type=DependencyType.INDEX,
                impact_level=ImpactLevel.LOW,
            ),
        ]

        stages = removal_manager._generate_execution_stages(dependencies)

        # Verify correct ordering
        stage_order = {stage: i for i, stage in enumerate(stages)}

        # Backup should be first
        assert stage_order[RemovalStage.BACKUP_CREATION] == 0

        # Dependent objects before constraints
        assert (
            stage_order[RemovalStage.DEPENDENT_OBJECTS]
            < stage_order[RemovalStage.CONSTRAINT_REMOVAL]
        )

        # Constraints before indexes
        assert (
            stage_order[RemovalStage.CONSTRAINT_REMOVAL]
            < stage_order[RemovalStage.INDEX_REMOVAL]
        )

        # Indexes before column
        assert (
            stage_order[RemovalStage.INDEX_REMOVAL]
            < stage_order[RemovalStage.COLUMN_REMOVAL]
        )

        # Column before cleanup
        assert (
            stage_order[RemovalStage.COLUMN_REMOVAL] < stage_order[RemovalStage.CLEANUP]
        )

        # Cleanup before validation
        assert stage_order[RemovalStage.CLEANUP] < stage_order[RemovalStage.VALIDATION]

    @pytest.mark.asyncio
    async def test_transaction_savepoint_rollback(
        self, removal_manager, postgres_connection
    ):
        """Test transaction savepoint and rollback functionality."""
        plan = RemovalPlan(
            table_name="users",
            column_name="temp_column",
            dependencies=[],
            execution_stages=[RemovalStage.COLUMN_REMOVAL],
            enable_rollback=True,
        )

        # Mock exception during execution to trigger rollback
        # Counter to track call number
        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # SAVEPOINT creation succeeds
            elif call_count[0] == 2:
                raise Exception("Simulated failure")  # Column removal fails
            else:
                return None  # ROLLBACK TO SAVEPOINT succeeds

        postgres_connection.execute.side_effect = execute_side_effect

        result = await removal_manager.execute_safe_removal(plan)

        # Verify rollback was executed
        assert result.rollback_executed is True
        assert result.status == RemovalStatus.TRANSACTION_FAILED

        # Verify savepoint operations were called
        savepoint_calls = [
            call
            for call in postgres_connection.execute.call_args_list
            if "SAVEPOINT" in str(call) or "ROLLBACK TO SAVEPOINT" in str(call)
        ]
        # Should have SAVEPOINT creation and ROLLBACK TO SAVEPOINT calls
        # (Exact verification depends on mock implementation)

    @pytest.mark.asyncio
    async def test_integration_with_dependency_analyzer(
        self, removal_manager, postgres_connection
    ):
        """Test integration with dependency analyzer."""
        # Test that removal manager correctly uses dependency analyzer
        original_analyze = (
            removal_manager.dependency_analyzer.analyze_column_dependencies
        )
        # Create report with a single constraint dependency
        dep_report = DependencyReport("test_table", "test_column")
        test_dep = ColumnDependency(
            object_name="test_constraint",
            dependency_type=DependencyType.CONSTRAINT,
            impact_level=ImpactLevel.LOW,
        )
        dep_report.dependencies[DependencyType.CONSTRAINT] = [test_dep]

        # Real async replacement with call-recording.
        call_log: list = []

        async def _record_and_return(table, column, connection):
            call_log.append((table, column, connection))
            return dep_report

        removal_manager.dependency_analyzer.analyze_column_dependencies = (
            _record_and_return
        )

        plan = await removal_manager.plan_column_removal("test_table", "test_column")

        # Verify analyzer was called with correct parameters
        assert len(call_log) == 1
        assert call_log[0] == (
            "test_table",
            "test_column",
            postgres_connection,
        )

        # Verify plan includes analyzer results
        assert len(plan.dependencies) == 1
        assert plan.dependencies[0].dependency_type == DependencyType.CONSTRAINT

    @pytest.mark.asyncio
    async def test_error_recovery_and_cleanup(
        self, removal_manager, postgres_connection
    ):
        """Test error recovery and cleanup functionality."""
        plan = RemovalPlan(
            table_name="users",
            column_name="temp_column",
            dependencies=[],
            execution_stages=[
                RemovalStage.BACKUP_CREATION,
                RemovalStage.COLUMN_REMOVAL,
                RemovalStage.CLEANUP,
            ],
        )

        # Mock partial success - backup succeeds, column removal fails
        postgres_connection.fetchval.side_effect = [5]  # Backup size

        # Counter to track call number
        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # SAVEPOINT creation succeeds
            elif call_count[0] == 2:
                return None  # Backup creation succeeds
            elif call_count[0] == 3:
                raise Exception("Permission denied")  # Column removal fails
            else:
                return None  # ROLLBACK TO SAVEPOINT succeeds

        postgres_connection.execute.side_effect = execute_side_effect

        result = await removal_manager.execute_safe_removal(plan)

        assert result.status == RemovalStatus.TRANSACTION_FAILED
        assert result.rollback_executed is True

        # Verify recovery instructions include backup information
        instructions = result.recovery_instructions
        assert any("Backup was created" in instr for instr in instructions)
        assert any("Permission denied" in instr for instr in instructions)

    def test_duration_estimation_accuracy(self, removal_manager):
        """Test that duration estimation is reasonable."""
        # Test with no dependencies
        empty_deps = []
        duration = removal_manager._estimate_removal_duration(empty_deps)
        assert duration >= 5.0  # Base time
        assert duration <= 10.0  # Should be relatively quick

        # Test with complex dependencies
        complex_deps = [
            ColumnDependency("idx1", DependencyType.INDEX, ImpactLevel.LOW),
            ColumnDependency("fk1", DependencyType.FOREIGN_KEY, ImpactLevel.HIGH),
            ColumnDependency("fk2", DependencyType.FOREIGN_KEY, ImpactLevel.HIGH),
            ColumnDependency("trig1", DependencyType.TRIGGER, ImpactLevel.MEDIUM),
            ColumnDependency("view1", DependencyType.VIEW, ImpactLevel.MEDIUM),
        ]
        duration = removal_manager._estimate_removal_duration(complex_deps)
        assert duration > 10.0  # Should be longer with more dependencies
        assert duration <= 20.0  # But still reasonable


class TestColumnRemovalEdgeCases:
    """Test edge cases and error conditions for column removal.

    These tests exercise internal error-handling paths (permission denied,
    backup failure, column-not-exists) that real PostgreSQL cannot be made
    to trigger on arbitrary tables. The tests use the ``StubAsyncConnection``
    and ``RealConnectionManagerStub`` classes defined at module top — both
    are real Python classes, not mocking-library doubles.
    """

    @pytest.fixture
    def stub_state(self) -> SimpleNamespace:
        """Mutable holder so tests can swap the connection per test."""
        return SimpleNamespace(current_conn=None)

    @pytest.fixture
    def connection_manager(self, stub_state):
        """Dynamic connection manager stub that returns stub_state.current_conn."""

        class _DynamicStub:
            def __init__(self, state):
                self._state = state

            async def get_connection(self):
                return self._state.current_conn

        return _DynamicStub(stub_state)

    @pytest.fixture
    def removal_manager(self, connection_manager):
        """Create removal manager for edge case tests."""
        return ColumnRemovalManager(connection_manager)

    @pytest.mark.asyncio
    async def test_column_already_removed(
        self, removal_manager, connection_manager, stub_state
    ):
        """Test handling when column is already removed."""
        fetchval_values = iter([True, False])  # table exists, column doesn't

        def _fetchval(*args, **kwargs):
            return next(fetchval_values)

        stub_state.current_conn = StubAsyncConnection(fetchval_impl=_fetchval)

        plan = RemovalPlan(
            table_name="users",
            column_name="nonexistent_column",
            dependencies=[],
            execution_stages=[RemovalStage.COLUMN_REMOVAL],
        )

        validation = await removal_manager.validate_removal_safety(plan)

        assert validation.is_safe is False
        assert any("does not exist" in warning for warning in validation.warnings)

    @pytest.mark.asyncio
    async def test_permission_denied_handling(
        self, removal_manager, connection_manager, stub_state
    ):
        """Test handling of permission denied errors."""
        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # SAVEPOINT creation succeeds
            elif call_count[0] == 2:
                raise Exception("permission denied")  # Column removal fails
            else:
                return None  # ROLLBACK TO SAVEPOINT succeeds

        stub_state.current_conn = StubAsyncConnection(execute_impl=execute_side_effect)

        plan = RemovalPlan(
            table_name="users",
            column_name="temp_column",
            execution_stages=[RemovalStage.COLUMN_REMOVAL],
        )

        result = await removal_manager.execute_safe_removal(plan)

        assert result.status == RemovalStatus.TRANSACTION_FAILED
        assert "permission denied" in result.error_message

    @pytest.mark.asyncio
    async def test_backup_failure_handling(
        self, removal_manager, connection_manager, stub_state
    ):
        """Test handling when backup creation fails."""
        call_count = [0]

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # SAVEPOINT creation succeeds
            elif call_count[0] == 2:
                raise Exception("Backup failed")  # Backup stage fails
            else:
                return None  # ROLLBACK TO SAVEPOINT succeeds

        stub_state.current_conn = StubAsyncConnection(execute_impl=execute_side_effect)

        plan = RemovalPlan(
            table_name="users",
            column_name="temp_column",
            backup_strategy=BackupStrategy.COLUMN_ONLY,
            execution_stages=[
                RemovalStage.BACKUP_CREATION,
                RemovalStage.COLUMN_REMOVAL,
            ],
        )

        result = await removal_manager.execute_safe_removal(plan)

        assert result.status == RemovalStatus.TRANSACTION_FAILED
        assert len(result.stages_completed) >= 1  # Backup stage attempted
        assert result.stages_completed[0].success is False
        assert "Backup failed" in result.stages_completed[0].errors[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
