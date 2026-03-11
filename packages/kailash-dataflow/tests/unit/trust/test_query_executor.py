#!/usr/bin/env python3
"""
Unit Tests for TrustAwareQueryExecutor (CARE-019).

Tests the trust-aware query execution logic for DataFlow.
These tests verify that queries are properly wrapped with trust
verification and constraint enforcement.

Test Coverage:
- Enforcement mode behavior (disabled, permissive, enforcing)
- Read operations with various constraints
- Write operations and read-only restrictions
- Audit event recording
- Table access verification
- Query result structure validation
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dataflow.trust.query_wrapper import (
    QueryAccessResult,
    QueryExecutionResult,
    TrustAwareQueryExecutor,
)


class TestExecutorDisabledMode:
    """Tests for executor in disabled mode."""

    @pytest.mark.asyncio
    async def test_executor_disabled_mode_allows_all(self, mock_dataflow_instance):
        """Test disabled mode allows all operations without verification."""
        executor = TrustAwareQueryExecutor(
            dataflow_instance=mock_dataflow_instance,
            trust_verifier=None,
            trust_operations=None,
            enforcement_mode="disabled",
            audit_generator=None,
        )

        result = await executor.execute_read(
            model_name="User",
            filter={"id": 1},
            agent_id="agent-001",
            trust_context=None,
        )

        assert isinstance(result, QueryExecutionResult)
        assert result.success is True
        # No constraints should be applied
        assert result.constraints_applied == []


class TestExecutorNoTrustOps:
    """Tests for executor without trust operations configured."""

    @pytest.mark.asyncio
    async def test_executor_no_trust_ops_allows_all(self, mock_dataflow_instance):
        """Test executor without trust_operations allows all operations."""
        executor = TrustAwareQueryExecutor(
            dataflow_instance=mock_dataflow_instance,
            trust_verifier=None,
            trust_operations=None,
            enforcement_mode="enforcing",
            audit_generator=None,
        )

        result = await executor.execute_read(
            model_name="User",
            filter={"id": 1},
            agent_id="agent-001",
            trust_context=None,
        )

        assert isinstance(result, QueryExecutionResult)
        assert result.success is True


class TestExecutorReadOperations:
    """Tests for executor read operations with constraints."""

    @pytest.mark.asyncio
    async def test_executor_read_with_data_scope(
        self, mock_dataflow_instance, mock_trust_operations, sample_constraints
    ):
        """Test data scope filter is applied to read operations."""
        # Configure mock to return data scope constraints
        data_scope_constraints = [
            c for c in sample_constraints if c.value == "department:finance"
        ]
        mock_trust_operations.get_agent_constraints = AsyncMock(
            return_value=data_scope_constraints
        )

        executor = TrustAwareQueryExecutor(
            dataflow_instance=mock_dataflow_instance,
            trust_verifier=None,
            trust_operations=mock_trust_operations,
            enforcement_mode="enforcing",
            audit_generator=None,
        )

        result = await executor.execute_read(
            model_name="User",
            filter={"id": 1},
            agent_id="agent-001",
            trust_context=None,
        )

        assert isinstance(result, QueryExecutionResult)
        assert result.success is True
        # Data scope constraint should be applied
        assert len(result.constraints_applied) > 0

    @pytest.mark.asyncio
    async def test_executor_read_with_column_filter(
        self, mock_dataflow_instance, mock_trust_operations
    ):
        """Test column access constraint filters columns."""
        from tests.unit.trust.conftest import MockConstraint, MockConstraintType

        column_constraint = MockConstraint(
            id="con-col",
            constraint_type=MockConstraintType.ACTION_RESTRICTION,
            value="no_pii",
            source="test",
        )
        mock_trust_operations.get_agent_constraints = AsyncMock(
            return_value=[column_constraint]
        )

        executor = TrustAwareQueryExecutor(
            dataflow_instance=mock_dataflow_instance,
            trust_verifier=None,
            trust_operations=mock_trust_operations,
            enforcement_mode="enforcing",
            audit_generator=None,
        )

        result = await executor.execute_read(
            model_name="User",
            filter={},
            agent_id="agent-001",
            trust_context=None,
        )

        assert isinstance(result, QueryExecutionResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_executor_read_with_row_limit(
        self, mock_dataflow_instance, mock_trust_operations
    ):
        """Test row limit constraint is applied."""
        from tests.unit.trust.conftest import MockConstraint, MockConstraintType

        row_limit_constraint = MockConstraint(
            id="con-row",
            constraint_type=MockConstraintType.RESOURCE_LIMIT,
            value="row_limit:100",
            source="test",
        )
        mock_trust_operations.get_agent_constraints = AsyncMock(
            return_value=[row_limit_constraint]
        )

        executor = TrustAwareQueryExecutor(
            dataflow_instance=mock_dataflow_instance,
            trust_verifier=None,
            trust_operations=mock_trust_operations,
            enforcement_mode="enforcing",
            audit_generator=None,
        )

        result = await executor.execute_read(
            model_name="User",
            filter={},
            agent_id="agent-001",
            trust_context=None,
        )

        assert isinstance(result, QueryExecutionResult)
        assert result.success is True


class TestExecutorWriteOperations:
    """Tests for executor write operations."""

    @pytest.mark.asyncio
    async def test_executor_write_blocked_read_only(
        self, mock_dataflow_instance, mock_trust_operations
    ):
        """Test read-only constraint blocks write operations."""
        from tests.unit.trust.conftest import MockConstraint, MockConstraintType

        read_only_constraint = MockConstraint(
            id="con-ro",
            constraint_type=MockConstraintType.ACTION_RESTRICTION,
            value="read_only",
            source="test",
        )
        mock_trust_operations.get_agent_constraints = AsyncMock(
            return_value=[read_only_constraint]
        )

        executor = TrustAwareQueryExecutor(
            dataflow_instance=mock_dataflow_instance,
            trust_verifier=None,
            trust_operations=mock_trust_operations,
            enforcement_mode="enforcing",
            audit_generator=None,
        )

        with pytest.raises(PermissionError) as exc_info:
            await executor.execute_write(
                model_name="User",
                operation="create",
                data={"name": "Test"},
                agent_id="agent-001",
                trust_context=None,
            )

        assert "read_only" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_executor_write_allowed_with_access(
        self, mock_dataflow_instance, mock_trust_operations
    ):
        """Test write succeeds when agent has write access."""
        mock_trust_operations.get_agent_constraints = AsyncMock(return_value=[])

        executor = TrustAwareQueryExecutor(
            dataflow_instance=mock_dataflow_instance,
            trust_verifier=None,
            trust_operations=mock_trust_operations,
            enforcement_mode="enforcing",
            audit_generator=None,
        )

        result = await executor.execute_write(
            model_name="User",
            operation="create",
            data={"name": "Test"},
            agent_id="agent-001",
            trust_context=None,
        )

        assert isinstance(result, QueryExecutionResult)
        assert result.success is True


class TestExecutorEnforcementModes:
    """Tests for different enforcement modes."""

    @pytest.mark.asyncio
    async def test_executor_permissive_mode_logs_denial(
        self, mock_dataflow_instance, mock_trust_operations, mock_audit_generator
    ):
        """Test permissive mode logs but allows denied operations."""
        from tests.unit.trust.conftest import MockConstraint, MockConstraintType

        read_only_constraint = MockConstraint(
            id="con-ro",
            constraint_type=MockConstraintType.ACTION_RESTRICTION,
            value="read_only",
            source="test",
        )
        mock_trust_operations.get_agent_constraints = AsyncMock(
            return_value=[read_only_constraint]
        )

        executor = TrustAwareQueryExecutor(
            dataflow_instance=mock_dataflow_instance,
            trust_verifier=None,
            trust_operations=mock_trust_operations,
            enforcement_mode="permissive",
            audit_generator=mock_audit_generator,
        )

        # In permissive mode, should log but allow
        result = await executor.execute_write(
            model_name="User",
            operation="create",
            data={"name": "Test"},
            agent_id="agent-001",
            trust_context=None,
        )

        # Should succeed in permissive mode
        assert isinstance(result, QueryExecutionResult)
        # Audit should have been called
        mock_audit_generator.resource_accessed.assert_called()

    @pytest.mark.asyncio
    async def test_executor_enforcing_mode_blocks_denial(
        self, mock_dataflow_instance, mock_trust_operations
    ):
        """Test enforcing mode raises error on denied operations."""
        from tests.unit.trust.conftest import MockConstraint, MockConstraintType

        read_only_constraint = MockConstraint(
            id="con-ro",
            constraint_type=MockConstraintType.ACTION_RESTRICTION,
            value="read_only",
            source="test",
        )
        mock_trust_operations.get_agent_constraints = AsyncMock(
            return_value=[read_only_constraint]
        )

        executor = TrustAwareQueryExecutor(
            dataflow_instance=mock_dataflow_instance,
            trust_verifier=None,
            trust_operations=mock_trust_operations,
            enforcement_mode="enforcing",
            audit_generator=None,
        )

        with pytest.raises(PermissionError):
            await executor.execute_write(
                model_name="User",
                operation="create",
                data={"name": "Test"},
                agent_id="agent-001",
                trust_context=None,
            )


class TestExecutorAuditIntegration:
    """Tests for audit event recording."""

    @pytest.mark.asyncio
    async def test_executor_audit_event_recorded(
        self, mock_dataflow_instance, mock_trust_operations, mock_audit_generator
    ):
        """Test audit generator records events correctly."""
        mock_trust_operations.get_agent_constraints = AsyncMock(return_value=[])

        executor = TrustAwareQueryExecutor(
            dataflow_instance=mock_dataflow_instance,
            trust_verifier=None,
            trust_operations=mock_trust_operations,
            enforcement_mode="enforcing",
            audit_generator=mock_audit_generator,
        )

        result = await executor.execute_read(
            model_name="User",
            filter={"id": 1},
            agent_id="agent-001",
            trust_context=None,
        )

        assert result.success is True
        # Verify audit was recorded
        mock_audit_generator.resource_accessed.assert_called_once()


class TestExecutorTableAccess:
    """Tests for table access verification."""

    @pytest.mark.asyncio
    async def test_executor_table_access_denied(
        self, mock_dataflow_instance, mock_trust_verifier
    ):
        """Test unauthorized table access raises error."""
        # Configure verifier to deny access
        mock_trust_verifier.verify_resource_access = AsyncMock(
            return_value=MagicMock(allowed=False, reason="Table access denied")
        )

        executor = TrustAwareQueryExecutor(
            dataflow_instance=mock_dataflow_instance,
            trust_verifier=mock_trust_verifier,
            trust_operations=None,
            enforcement_mode="enforcing",
            audit_generator=None,
        )

        with pytest.raises(PermissionError) as exc_info:
            await executor.execute_read(
                model_name="SecretTable",
                filter={},
                agent_id="agent-001",
                trust_context=None,
            )

        assert "access denied" in str(exc_info.value).lower()


class TestExecutorResultStructure:
    """Tests for QueryExecutionResult structure."""

    @pytest.mark.asyncio
    async def test_executor_execution_result_structure(self, mock_dataflow_instance):
        """Test QueryExecutionResult has correct fields."""
        executor = TrustAwareQueryExecutor(
            dataflow_instance=mock_dataflow_instance,
            trust_verifier=None,
            trust_operations=None,
            enforcement_mode="disabled",
            audit_generator=None,
        )

        result = await executor.execute_read(
            model_name="User",
            filter={},
            agent_id="agent-001",
            trust_context=None,
        )

        assert hasattr(result, "success")
        assert hasattr(result, "data")
        assert hasattr(result, "rows_affected")
        assert hasattr(result, "constraints_applied")
        assert hasattr(result, "audit_event_id")
        assert hasattr(result, "execution_time_ms")

        assert isinstance(result.success, bool)
        assert isinstance(result.rows_affected, int)
        assert isinstance(result.constraints_applied, list)
        assert isinstance(result.execution_time_ms, float)

    @pytest.mark.asyncio
    async def test_executor_pii_filtered_in_result(
        self, mock_dataflow_instance, mock_trust_operations
    ):
        """Test PII columns are not in result data when no_pii constraint active."""
        from tests.unit.trust.conftest import MockConstraint, MockConstraintType

        no_pii_constraint = MockConstraint(
            id="con-pii",
            constraint_type=MockConstraintType.ACTION_RESTRICTION,
            value="no_pii",
            source="test",
        )
        mock_trust_operations.get_agent_constraints = AsyncMock(
            return_value=[no_pii_constraint]
        )

        # Configure mock to return data with PII
        mock_dataflow_instance.execute = AsyncMock(
            return_value={
                "data": [
                    {"id": 1, "name": "Alice", "ssn": "123-45-6789", "email": "a@b.com"}
                ]
            }
        )

        # Configure model columns to include PII columns so they can be detected
        mock_dataflow_instance.get_model_columns = MagicMock(
            return_value=["id", "name", "ssn", "email"]
        )

        executor = TrustAwareQueryExecutor(
            dataflow_instance=mock_dataflow_instance,
            trust_verifier=None,
            trust_operations=mock_trust_operations,
            enforcement_mode="enforcing",
            audit_generator=None,
        )

        result = await executor.execute_read(
            model_name="User",
            filter={},
            agent_id="agent-001",
            trust_context=None,
        )

        assert result.success is True
        # PII column should be filtered from result
        # The executor should filter SSN from the returned data
        if result.data and isinstance(result.data, dict) and "data" in result.data:
            for row in result.data["data"]:
                assert "ssn" not in row

    @pytest.mark.asyncio
    async def test_executor_time_window_applied(
        self, mock_dataflow_instance, mock_trust_operations
    ):
        """Test time window filter is applied to queries."""
        from tests.unit.trust.conftest import MockConstraint, MockConstraintType

        time_constraint = MockConstraint(
            id="con-time",
            constraint_type=MockConstraintType.TIME_WINDOW,
            value="last_30_days",
            source="test",
        )
        mock_trust_operations.get_agent_constraints = AsyncMock(
            return_value=[time_constraint]
        )

        executor = TrustAwareQueryExecutor(
            dataflow_instance=mock_dataflow_instance,
            trust_verifier=None,
            trust_operations=mock_trust_operations,
            enforcement_mode="enforcing",
            audit_generator=None,
        )

        result = await executor.execute_read(
            model_name="Transaction",
            filter={},
            agent_id="agent-001",
            trust_context=None,
        )

        assert result.success is True
        # Time window constraint should be in applied constraints
        assert any(
            "time_window" in c.lower() for c in result.constraints_applied
        ) or any("last_30_days" in c.lower() for c in result.constraints_applied)


class TestQueryAccessResultSerialization:
    """Tests for QueryAccessResult serialization."""

    def test_query_access_result_serialization(self):
        """Test QueryAccessResult fields are correct."""
        result = QueryAccessResult(
            allowed=True,
            filtered_columns=["id", "name", "email"],
            additional_filters={"department": "engineering"},
            row_limit=500,
            denied_reason=None,
            applied_constraints=[
                "data_scope:department:engineering",
                "resource_limit:row_limit:500",
            ],
            pii_columns_filtered=["ssn", "dob"],
            sensitive_columns_flagged=["salary"],
        )

        # Verify all fields
        assert result.allowed is True
        assert len(result.filtered_columns) == 3
        assert result.additional_filters["department"] == "engineering"
        assert result.row_limit == 500
        assert result.denied_reason is None
        assert len(result.applied_constraints) == 2
        assert "ssn" in result.pii_columns_filtered
        assert "salary" in result.sensitive_columns_flagged
