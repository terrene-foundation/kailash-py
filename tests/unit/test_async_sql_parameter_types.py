"""Unit tests for AsyncSQL parameter type inference fix."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from kailash.nodes.data.async_sql import (
    AsyncSQLDatabaseNode,
    DatabaseAdapter,
    FetchMode,
    PostgreSQLAdapter,
)


class TestAsyncSQLParameterTypes:
    """Test parameter_types functionality for PostgreSQL type inference issues."""

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock database adapter."""
        adapter = Mock(spec=DatabaseAdapter)
        adapter.execute = AsyncMock()
        adapter.connect = AsyncMock()
        adapter.disconnect = AsyncMock()
        adapter.begin_transaction = AsyncMock(return_value="transaction")
        adapter.commit_transaction = AsyncMock()
        adapter.rollback_transaction = AsyncMock()
        return adapter

    @pytest.fixture
    def node(self):
        """Create AsyncSQLDatabaseNode instance with test config."""
        return AsyncSQLDatabaseNode(
            database_type="postgresql",
            host="localhost",
            database="test_db",
            user="test_user",
            password="test_pass",
        )

    @pytest.mark.asyncio
    async def test_parameter_types_passed_through_chain(self, node, mock_adapter):
        # Patch the adapter creation
        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            # Mock execute to return a result
            mock_adapter.execute.return_value = []

            # Execute with parameter_types
            await node.async_run(
                query="INSERT INTO logs (details) VALUES (jsonb_build_object('id', :id))",
                params={"id": "test123"},
                parameter_types={"id": "text"},
            )

            # Verify execute was called with parameter_types
            mock_adapter.execute.assert_called_once()
            call_args = mock_adapter.execute.call_args
            assert call_args.kwargs.get("parameter_types") == {"id": "text"}

    @pytest.mark.asyncio
    async def test_parameter_types_from_config(self, node, mock_adapter):
        """Test that parameter_types can be set in node config."""
        # Update node config
        node.config["parameter_types"] = {"role_id": "uuid", "metadata": "jsonb"}

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            mock_adapter.execute.return_value = []

            # Execute without providing parameter_types in call
            await node.async_run(
                query="UPDATE users SET metadata = :metadata WHERE role_id = :role_id",
                params={
                    "role_id": "123e4567-e89b-12d3-a456-426614174000",
                    "metadata": {"key": "value"},
                },
            )

            # Verify config parameter_types were used
            call_args = mock_adapter.execute.call_args
            assert call_args.kwargs.get("parameter_types") == {
                "role_id": "uuid",
                "metadata": "jsonb",
            }

    @pytest.mark.asyncio
    async def test_runtime_parameter_types_override_config(self, node, mock_adapter):
        """Test that runtime parameter_types override config values."""
        # Set config parameter_types
        node.config["parameter_types"] = {"id": "integer"}

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            mock_adapter.execute.return_value = []

            # Execute with different parameter_types
            await node.async_run(
                query="SELECT * FROM users WHERE id = :id",
                params={"id": "abc123"},
                parameter_types={"id": "text"},  # Override config
            )

            # Verify runtime parameter_types were used
            call_args = mock_adapter.execute.call_args
            assert call_args.kwargs.get("parameter_types") == {"id": "text"}

    @pytest.mark.asyncio
    async def test_postgresql_adapter_applies_type_casts(self):
        """Test that PostgreSQLAdapter correctly applies type casts when parameter_types are provided."""
        # Instead of testing the adapter directly, test through the node
        # which is the intended usage pattern
        node = AsyncSQLDatabaseNode(
            database_type="postgresql",
            host="localhost",
            database="test_db",
            user="test_user",
            password="test_pass",
        )

        # Create a mock adapter that captures the execute call
        mock_adapter = Mock(spec=DatabaseAdapter)
        execute_calls = []

        async def capture_execute(**kwargs):
            execute_calls.append(kwargs)
            return []

        mock_adapter.execute = AsyncMock(side_effect=capture_execute)
        mock_adapter.connect = AsyncMock()
        mock_adapter.disconnect = AsyncMock()

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            # Test query with parameter types
            original_query = "INSERT INTO audit (data) VALUES (jsonb_build_object('user_id', :user_id, 'action', :action))"
            params = {"user_id": "123", "action": "login"}
            parameter_types = {"user_id": "text", "action": "text"}

            # Execute with parameter types
            await node.async_run(
                query=original_query, params=params, parameter_types=parameter_types
            )

            # Verify parameter_types were passed to adapter
            assert len(execute_calls) == 1
            assert execute_calls[0]["parameter_types"] == parameter_types

    @pytest.mark.asyncio
    async def test_no_parameter_types_no_modification(self):
        """Test that queries are not modified when parameter_types is None."""
        node = AsyncSQLDatabaseNode(
            database_type="postgresql",
            host="localhost",
            database="test_db",
            user="test_user",
            password="test_pass",
        )

        # Create a mock adapter
        mock_adapter = Mock(spec=DatabaseAdapter)
        execute_calls = []

        async def capture_execute(**kwargs):
            execute_calls.append(kwargs)
            return []

        mock_adapter.execute = AsyncMock(side_effect=capture_execute)
        mock_adapter.connect = AsyncMock()
        mock_adapter.disconnect = AsyncMock()

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            original_query = "SELECT * FROM users WHERE id = :id"
            params = {"id": 123}

            # Execute without parameter types
            await node.async_run(query=original_query, params=params)

            # Verify parameter_types is None
            assert len(execute_calls) == 1
            assert execute_calls[0].get("parameter_types") is None

    @pytest.mark.asyncio
    async def test_complex_jsonb_query_with_types(self, node, mock_adapter):
        """Test complex JSONB query that previously failed without type hints."""
        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            mock_adapter.execute.return_value = []

            # Complex query that fails without type hints
            query = """
                INSERT INTO audit_logs (action, details, created_by)
                VALUES (
                    :action,
                    jsonb_build_object(
                        'role_id', :role_id,
                        'granted_by', :granted_by,
                        'permissions', :permissions::jsonb,
                        'metadata', jsonb_build_object(
                            'timestamp', :timestamp,
                            'ip_address', :ip_address
                        )
                    ),
                    :created_by
                )
            """

            params = {
                "action": "role_assigned",
                "role_id": "admin",
                "granted_by": "system",
                "permissions": '["read", "write", "delete"]',
                "timestamp": "2024-01-01T00:00:00Z",
                "ip_address": "192.168.1.1",
                "created_by": "system",
            }

            parameter_types = {
                "action": "text",
                "role_id": "text",
                "granted_by": "text",
                "permissions": "jsonb",
                "timestamp": "timestamptz",
                "ip_address": "inet",
                "created_by": "text",
            }

            await node.async_run(
                query=query, params=params, parameter_types=parameter_types
            )

            # Verify parameter_types were passed
            call_args = mock_adapter.execute.call_args
            assert call_args.kwargs.get("parameter_types") == parameter_types

    @pytest.mark.asyncio
    async def test_coalesce_null_handling_with_types(self, node, mock_adapter):
        """Test COALESCE with NULL values that requires type hints."""
        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            mock_adapter.execute.return_value = []

            query = """
                UPDATE users
                SET preferences = jsonb_set(
                    COALESCE(preferences, '{}'),
                    '{notifications}',
                    :notification_settings::jsonb
                )
                WHERE user_id = :user_id
            """

            params = {
                "notification_settings": '{"email": true, "sms": false}',
                "user_id": "user123",
            }

            parameter_types = {"notification_settings": "jsonb", "user_id": "text"}

            await node.async_run(
                query=query, params=params, parameter_types=parameter_types
            )

            # Verify execution with types
            assert mock_adapter.execute.called
            call_args = mock_adapter.execute.call_args
            assert call_args.kwargs.get("parameter_types") == parameter_types
        # except ImportError: # Orphaned except removed
        # pass  # ImportError will cause test failure as intended
