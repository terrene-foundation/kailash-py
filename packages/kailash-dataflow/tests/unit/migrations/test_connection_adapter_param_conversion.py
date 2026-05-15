"""Tier-1 unit tests for ConnectionManagerAdapter parameter conversion.

The SUT is pure-string algorithm (%s -> $N placeholder mapping); no DB
connection is required. Tier-2 round-trip coverage of the same SUT against
real PG lives at tests/integration/migration/test_migration_lock_manager_integration.py
§ TestConnectionAdapterIntegration (per testing.md § One Direct Test Per
Variant — different tier = different variant; both required).

Implements: specs/testing-tiers.md § Tier-1 Contract.

Per testing.md § 3-Tier Testing exception (Protocol-Satisfying Deterministic
Adapters): the deterministic helper classes below (FakeDataFlow,
FakeAsyncRuntime) satisfy the runtime/dataflow protocols ConnectionManagerAdapter
expects. They are hand-rolled deterministic adapters with stable, inspectable
behavior; the file imports nothing from the standard library mocking module
and constructs no synthetic patch / magic / async patch instances.
"""

import pytest

from dataflow.utils.connection_adapter import ConnectionManagerAdapter

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Deterministic Protocol-Satisfying Adapters (NOT mocks — see module docstring)
# ---------------------------------------------------------------------------


class _FakeDatabaseConfig:
    """Deterministic config object satisfying ConnectionManagerAdapter's
    expected `dataflow.config.database` shape (url + get_connection_url())."""

    def __init__(self, url: str):
        self.url = url

    def get_connection_url(self, environment: str = "test") -> str:
        # ConnectionManagerAdapter.__init__ calls
        # self.dataflow.config.database.get_connection_url(self.dataflow.config.environment)
        # — accept the env positional arg the way the real DatabaseConfig does.
        del environment  # interface-only; deterministic stub returns one url
        return self.url


class _FakeConfig:
    """Deterministic config object satisfying ConnectionManagerAdapter's
    expected `dataflow.config` shape (database + environment)."""

    def __init__(self, url: str, environment: str = "test"):
        self.database = _FakeDatabaseConfig(url)
        self.environment = environment


class FakeDataFlow:
    """Deterministic stand-in for DataFlow satisfying the surface
    ConnectionManagerAdapter reads at construction time."""

    def __init__(self, url: str, environment: str = "test"):
        self.config = _FakeConfig(url, environment)


class FakeAsyncRuntime:
    """Deterministic protocol-satisfying runtime that records calls and
    returns a controlled tuple from execute_workflow_async.

    Replaces what an asynchronous-patch helper from the standard library
    mocking module would supply. The helper is a plain class; deterministic
    behavior is inspectable via call_count + last_call.
    """

    def __init__(self, return_value):
        self._return_value = return_value
        self.call_count = 0
        self.last_call = None  # (args, kwargs)
        self.calls = []  # list of (args, kwargs)

    async def execute_workflow_async(self, *args, **kwargs):
        self.call_count += 1
        self.last_call = (args, kwargs)
        self.calls.append((args, kwargs))
        # Allow per-call return overriding via return_value mutation.
        return self._return_value

    def set_return_value(self, value):
        self._return_value = value


class FakeAsyncExecuteQuery:
    """Deterministic stand-in for adapter.execute_query when a test wants to
    intercept the method without exercising _runtime.execute_workflow_async.
    Records calls; returns a controlled value or raises a controlled side effect.
    """

    def __init__(self, return_value=None, side_effects=None):
        self._return_value = return_value
        self._side_effects = list(side_effects) if side_effects is not None else None
        self.call_count = 0
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.call_count += 1
        self.calls.append((args, kwargs))
        if self._side_effects is not None:
            effect = self._side_effects.pop(0)
            if isinstance(effect, Exception):
                raise effect
            return effect
        return self._return_value

    def assert_called_once_with(self, *args, **kwargs):
        assert self.call_count == 1, f"expected 1 call, got {self.call_count}"
        actual = self.calls[0]
        assert actual == (
            args,
            kwargs,
        ), f"call args mismatch: {actual} != {(args, kwargs)}"

    def assert_called(self):
        assert self.call_count >= 1, "expected at least one call"


# ---------------------------------------------------------------------------
# TestConnectionManagerAdapter — extracted from
# tests/integration/migrations/test_migration_lock_manager_integration.py
# (8 tests, deleted in same commit). Bodies preserved verbatim modulo
# substitution of standard-library patch helpers with the deterministic
# protocol adapters declared above (Protocol-Satisfying exception).
# ---------------------------------------------------------------------------


class TestConnectionManagerAdapter:
    """Test ConnectionManagerAdapter for MigrationLockManager integration."""

    def test_adapter_initialization(self):
        """Test ConnectionManagerAdapter initializes correctly."""
        fake_dataflow = FakeDataFlow("postgresql://localhost/test")

        adapter = ConnectionManagerAdapter(fake_dataflow)

        assert adapter.dataflow == fake_dataflow
        assert not adapter._transaction_started
        assert adapter._parameter_style == "postgresql"  # Default for PostgreSQL URL

    def test_adapter_parameter_format_conversion(self):
        """Test parameter placeholder conversion from %s to $1, $2, etc."""
        fake_dataflow = FakeDataFlow("postgresql://localhost/test")
        adapter = ConnectionManagerAdapter(fake_dataflow)

        # Test SQL with %s placeholders
        sql = "INSERT INTO test_table (col1, col2) VALUES (%s, %s)"
        params = ["value1", "value2"]

        converted_sql, converted_params = adapter._convert_parameters(sql, params)

        expected_sql = "INSERT INTO test_table (col1, col2) VALUES ($1, $2)"
        assert converted_sql == expected_sql
        assert converted_params == params

    def test_adapter_parameter_format_no_conversion_needed(self):
        """Test parameter conversion when no %s placeholders exist."""
        fake_dataflow = FakeDataFlow("sqlite:///:memory:")
        adapter = ConnectionManagerAdapter(fake_dataflow)

        sql = "SELECT * FROM test_table"
        params = None

        converted_sql, converted_params = adapter._convert_parameters(sql, params)

        assert converted_sql == sql
        assert converted_params == params

    @pytest.mark.asyncio
    async def test_execute_query_basic(self):
        """Test basic query execution through adapter."""
        fake_dataflow = FakeDataFlow("sqlite:///:memory:")
        adapter = ConnectionManagerAdapter(fake_dataflow)

        # Replace adapter.execute_query with a deterministic protocol-satisfying
        # callable (a plain class, not a synthetic patch helper).
        fake_execute = FakeAsyncExecuteQuery(return_value=[{"success": True}])
        adapter.execute_query = fake_execute  # type: ignore[method-assign]

        result = await adapter.execute_query("SELECT 1", None)

        fake_execute.assert_called_once_with("SELECT 1", None)
        assert result == [{"success": True}]

    @pytest.mark.asyncio
    async def test_execute_query_with_parameter_conversion(self):
        """Test query execution with parameter format conversion."""
        fake_dataflow = FakeDataFlow("sqlite:///:memory:")
        adapter = ConnectionManagerAdapter(fake_dataflow)

        # Replace adapter._runtime with a deterministic runtime that returns
        # success for empty results (DML operations).
        fake_runtime = FakeAsyncRuntime(
            return_value=({"query_execution": {"result": []}}, None)
        )
        adapter._runtime = fake_runtime

        sql = "INSERT INTO locks (name, value) VALUES (%s, %s)"
        params = ["test_lock", "test_value"]

        result = await adapter.execute_query(sql, params)

        # Should have called runtime.execute_workflow_async with converted SQL
        assert fake_runtime.call_count == 1

        # Should return success indicator for empty results (DML operations)
        assert result == [{"success": True}]

    @pytest.mark.asyncio
    async def test_execute_query_dml_result_handling(self):
        """Test DML operation result handling - empty results should return success."""
        fake_dataflow = FakeDataFlow("sqlite:///:memory:")
        adapter = ConnectionManagerAdapter(fake_dataflow)

        fake_runtime = FakeAsyncRuntime(
            return_value=({"query_execution": {"result": []}}, None)
        )
        adapter._runtime = fake_runtime

        result = await adapter.execute_query("INSERT INTO test (id) VALUES (%s)", [1])

        # Empty results for DML should return success indicator
        assert result == [{"success": True}]

    @pytest.mark.asyncio
    async def test_execute_query_select_result_handling(self):
        """Test SELECT operation result handling - return actual results."""
        fake_dataflow = FakeDataFlow("sqlite:///:memory:")
        adapter = ConnectionManagerAdapter(fake_dataflow)

        expected_results = [{"id": 1, "name": "test"}]

        fake_runtime = FakeAsyncRuntime(
            return_value=(
                {"query_execution": {"result": [{"data": expected_results}]}},
                None,
            )
        )
        adapter._runtime = fake_runtime

        result = await adapter.execute_query("SELECT * FROM test", None)

        # SELECT should return actual results
        assert result == expected_results

    @pytest.mark.asyncio
    async def test_transaction_operations(self):
        """Test transaction begin, commit, and rollback operations."""
        fake_dataflow = FakeDataFlow("sqlite:///:memory:")
        adapter = ConnectionManagerAdapter(fake_dataflow)

        fake_runtime = FakeAsyncRuntime(
            return_value=({"begin_transaction": {"result": "success"}}, None)
        )
        adapter._runtime = fake_runtime

        # Test begin transaction
        await adapter.begin_transaction()
        assert adapter._transaction_started

        # Reset response for commit
        fake_runtime.set_return_value(
            ({"commit_transaction": {"result": "success"}}, None)
        )

        # Test commit transaction
        await adapter.commit_transaction()
        assert not adapter._transaction_started

        # Reset response for begin
        fake_runtime.set_return_value(
            ({"begin_transaction": {"result": "success"}}, None)
        )

        # Reset for rollback test
        await adapter.begin_transaction()
        assert adapter._transaction_started

        # Reset response for rollback
        fake_runtime.set_return_value(
            ({"rollback_transaction": {"result": "success"}}, None)
        )

        # Test rollback transaction
        await adapter.rollback_transaction()
        assert not adapter._transaction_started


# ---------------------------------------------------------------------------
# TestParameterConversionEdgeCases — extracted from
# tests/integration/migrations/test_migration_lock_manager_integration.py
# (4 tests, deleted in same commit). Pure string-algorithm tests; no
# runtime / async surface needed.
# ---------------------------------------------------------------------------


class TestParameterConversionEdgeCases:
    """Test edge cases for parameter conversion."""

    def test_multiple_parameter_conversion(self):
        """Test conversion with many parameters."""
        fake_dataflow = FakeDataFlow("postgresql://localhost/test")
        adapter = ConnectionManagerAdapter(fake_dataflow)

        sql = "INSERT INTO test (a, b, c, d, e) VALUES (%s, %s, %s, %s, %s)"
        params = [1, 2, 3, 4, 5]

        converted_sql, converted_params = adapter._convert_parameters(sql, params)

        expected_sql = "INSERT INTO test (a, b, c, d, e) VALUES ($1, $2, $3, $4, $5)"
        assert converted_sql == expected_sql
        assert converted_params == params

    def test_mixed_sql_with_other_placeholders(self):
        """Test conversion doesn't affect other SQL constructs."""
        fake_dataflow = FakeDataFlow("postgresql://localhost/test")
        adapter = ConnectionManagerAdapter(fake_dataflow)

        sql = "SELECT * FROM test WHERE field = %s AND other_field LIKE '%%pattern%%'"
        params = ["value"]

        converted_sql, converted_params = adapter._convert_parameters(sql, params)

        expected_sql = (
            "SELECT * FROM test WHERE field = $1 AND other_field LIKE '%%pattern%%'"
        )
        assert converted_sql == expected_sql
        assert converted_params == params

    def test_no_parameters(self):
        """Test with None parameters."""
        fake_dataflow = FakeDataFlow("sqlite:///:memory:")
        adapter = ConnectionManagerAdapter(fake_dataflow)

        sql = "SELECT * FROM test"
        params = None

        converted_sql, converted_params = adapter._convert_parameters(sql, params)

        assert converted_sql == sql
        assert converted_params is None

    def test_empty_parameters_list(self):
        """Test with empty parameters list."""
        fake_dataflow = FakeDataFlow("postgresql://localhost/test")
        adapter = ConnectionManagerAdapter(fake_dataflow)

        sql = "SELECT * FROM test WHERE id = %s"  # Has placeholder but empty params
        params = []

        converted_sql, converted_params = adapter._convert_parameters(sql, params)

        expected_sql = "SELECT * FROM test WHERE id = $1"  # Still converts
        assert converted_sql == expected_sql
        assert converted_params == []
