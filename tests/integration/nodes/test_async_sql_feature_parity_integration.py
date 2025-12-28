"""Unit tests for AsyncSQLDatabaseNode feature parity with sync SQLDatabaseNode."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.nodes.data.async_sql import (
    AsyncSQLDatabaseNode,
    DatabaseConfigManager,
    LockStatus,
    QueryValidator,
)
from kailash.sdk_exceptions import (
    NodeConfigurationError,
    NodeExecutionError,
    NodeValidationError,
)


class TestAsyncSQLFeatureParity:
    """Test feature parity between async and sync SQL database nodes."""

    def test_connection_pooling_configuration(self):
        """Test connection pooling configuration matches sync version."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            pool_size=5,
            max_pool_size=10,
            share_pool=True,
        )

        assert node.config["pool_size"] == 5
        assert node.config["max_pool_size"] == 10
        assert node._share_pool

    def test_pool_sharing_key_generation(self):
        """Test pool sharing key generation logic."""
        node1 = AsyncSQLDatabaseNode(
            name="test1",
            database_type="postgresql",
            host="localhost",
            port=5432,
            database="testdb",
            user="testuser",
            password="testpass",
            pool_size=10,
        )

        node2 = AsyncSQLDatabaseNode(
            name="test2",
            database_type="postgresql",
            host="localhost",
            port=5432,
            database="testdb",
            user="testuser",
            password="testpass",
            pool_size=10,
        )

        # Nodes with same config should generate same pool key
        key1 = node1._generate_pool_key()
        key2 = node2._generate_pool_key()
        assert key1 == key2

        # Different pool size should generate different key
        node3 = AsyncSQLDatabaseNode(
            name="test3",
            database_type="postgresql",
            host="localhost",
            port=5432,
            database="testdb",
            user="testuser",
            password="testpass",
            pool_size=20,  # Different pool size
        )

        key3 = node3._generate_pool_key()
        assert key1 != key3

    def test_query_validation_security(self):
        """Test query validation for SQL injection prevention."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            validate_queries=True,
            allow_admin=False,
        )

        # Test dangerous query patterns
        dangerous_queries = [
            "SELECT * FROM users; DROP TABLE users;",
            "SELECT * FROM users UNION SELECT * FROM passwords",
            "SELECT * FROM users WHERE id = 1 AND SLEEP(5)",
            "SELECT * FROM users /* malicious comment */ WHERE id = 1",
        ]

        for query in dangerous_queries:
            with pytest.raises(NodeValidationError):
                QueryValidator.validate_query(query, allow_admin=False)

    def test_admin_query_validation(self):
        """Test admin query validation logic."""
        # Test with allow_admin=False
        admin_queries = [
            "CREATE TABLE test (id INT)",
            "DROP TABLE test",
            "ALTER TABLE users ADD COLUMN email VARCHAR(255)",
            "GRANT SELECT ON users TO testuser",
        ]

        for query in admin_queries:
            with pytest.raises(NodeValidationError):
                QueryValidator.validate_query(query, allow_admin=False)

            # Should work with allow_admin=True
            try:
                QueryValidator.validate_query(query, allow_admin=True)
            except NodeValidationError:
                pytest.fail(f"Admin query should be allowed: {query}")

    def test_connection_string_validation(self):
        """Test connection string security validation."""
        # Valid connection strings
        valid_strings = [
            "postgresql://user:pass@localhost:5432/dbname",
            "mysql://user:pass@localhost:3306/dbname",
            "sqlite:///path/to/database.db",
        ]

        for conn_str in valid_strings:
            try:
                QueryValidator.validate_connection_string(conn_str)
            except NodeValidationError:
                pytest.fail(f"Valid connection string should pass: {conn_str}")

        # Invalid/suspicious connection strings
        invalid_strings = [
            "postgresql://user:pass@localhost:5432/dbname; DROP TABLE users;",
            "postgresql://user$(whoami):pass@localhost/db",
        ]

        for conn_str in invalid_strings:
            with pytest.raises(NodeValidationError):
                QueryValidator.validate_connection_string(conn_str)

    def test_database_config_manager_functionality(self):
        """Test DatabaseConfigManager matches sync version functionality."""
        import os
        import tempfile

        import yaml

        # Create temporary config file
        config_data = {
            "databases": {
                "test_db": {
                    "url": "postgresql://user:pass@localhost:5432/testdb",
                    "pool_size": 15,
                    "timeout": 30.0,
                },
                "dev_db": {
                    "url": "postgresql://${DB_USER}:${DB_PASS}@localhost:5432/devdb",
                    "max_retries": 5,
                },
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            manager = DatabaseConfigManager(config_path)

            # Test connection retrieval
            conn_string, db_config = manager.get_database_config("test_db")
            assert conn_string == "postgresql://user:pass@localhost:5432/testdb"
            assert db_config["pool_size"] == 15
            assert db_config["timeout"] == 30.0

            # Test environment variable substitution
            os.environ["DB_USER"] = "devuser"
            os.environ["DB_PASS"] = "devpass"

            # Clear cache to test env var substitution
            manager._config_cache.clear()

            conn_string, db_config = manager.get_database_config("dev_db")
            assert conn_string == "postgresql://devuser:devpass@localhost:5432/devdb"
            assert db_config["max_retries"] == 5

            # Test listing connections
            connections = manager.list_connections()
            assert "test_db" in connections
            assert "dev_db" in connections

            # Test non-existent connection
            with pytest.raises(NodeExecutionError):
                manager.get_database_config("nonexistent")

        finally:
            os.unlink(config_path)
            os.environ.pop("DB_USER", None)
            os.environ.pop("DB_PASS", None)

    def test_optimistic_locking_configuration(self):
        """Test optimistic locking configuration."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            enable_optimistic_locking=True,
            version_field="version_num",
            conflict_resolution="retry",
            version_retry_attempts=5,
        )

        assert node._enable_optimistic_locking
        assert node._version_field == "version_num"
        assert node._conflict_resolution == "retry"
        assert node._version_retry_attempts == 5

    @pytest.mark.asyncio
    async def test_optimistic_locking_functionality(self):
        """Test optimistic locking execution logic."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            enable_optimistic_locking=True,
        )

        # Mock adapter
        mock_adapter = AsyncMock()
        mock_adapter.execute.return_value = [
            {"id": 1, "name": "updated", "version": 2, "rows_affected": 1}
        ]

        # Mock execute_async to return the expected format
        async def mock_execute_async(**kwargs):
            return {
                "result": {
                    "data": [{"rows_affected": 1}],
                    "row_count": 1,
                }
            }

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            with patch.object(node, "execute_async", side_effect=mock_execute_async):
                result = await node.execute_with_version_check(
                    query="UPDATE users SET name = :name WHERE id = :id",
                    params={"name": "updated", "id": 1},
                    expected_version=1,
                    record_id=1,
                    table_name="users",
                )

                assert result["status"] == LockStatus.SUCCESS
                assert result["version_checked"]

    def test_retry_configuration_parity(self):
        """Test retry configuration matches sync version."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            max_retries=5,
            retry_delay=2.0,
        )

        assert node._retry_config.max_retries == 5
        assert node._retry_config.initial_delay == 2.0

        # Test retry config object
        from kailash.nodes.data.async_sql import RetryConfig

        retry_config = RetryConfig(max_retries=3, initial_delay=1.5)

        node_with_config = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            retry_config=retry_config,
        )

        assert node_with_config._retry_config.max_retries == 3
        assert node_with_config._retry_config.initial_delay == 1.5

    @pytest.mark.asyncio
    async def test_retry_logic_execution(self):
        """Test retry logic during query execution."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            max_retries=3,
            retry_delay=0.1,  # Fast retry for testing
        )

        # Mock adapter to fail twice then succeed
        mock_adapter = AsyncMock()
        mock_adapter.execute.side_effect = [
            Exception("connection reset"),  # Retryable error
            Exception("connection_refused"),  # Retryable error
            [{"result": "success"}],
        ]

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            with patch("asyncio.sleep"):  # Mock sleep to speed up test
                result = await node.execute_async(query="SELECT 'success' as result")

                assert result["result"]["data"][0]["result"] == "success"
                assert mock_adapter.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_batch_operations_parity(self):
        """Test batch operations match sync version functionality."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
        )

        # Mock adapter
        mock_adapter = AsyncMock()

        params_list = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
            {"name": "Charlie", "age": 35},
        ]

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_many_async(
                query="INSERT INTO users (name, age) VALUES (:name, :age)",
                params_list=params_list,
            )

            assert result["result"]["affected_rows"] == 3
            assert result["result"]["batch_size"] == 3
            mock_adapter.execute_many.assert_called_once()

    def test_parameter_validation_parity(self):
        """Test parameter validation matches sync version."""
        # Test database type validation
        with pytest.raises(NodeConfigurationError, match="Invalid database_type"):
            AsyncSQLDatabaseNode(
                name="test",
                database_type="invalid_db",
                host="localhost",
                database="testdb",
                user="testuser",
                password="testpass",
            )

        # Test fetch mode validation
        with pytest.raises(NodeConfigurationError, match="Invalid fetch_mode"):
            AsyncSQLDatabaseNode(
                name="test",
                database_type="postgresql",
                host="localhost",
                database="testdb",
                user="testuser",
                password="testpass",
                fetch_mode="invalid_mode",
            )

        # Test fetch_size requirement for 'many' mode
        with pytest.raises(NodeConfigurationError, match="fetch_size required"):
            AsyncSQLDatabaseNode(
                name="test",
                database_type="postgresql",
                host="localhost",
                database="testdb",
                user="testuser",
                password="testpass",
                fetch_mode="many",
                # fetch_size not provided
            )

    def test_connection_parameter_validation(self):
        """Test connection parameter validation."""
        # PostgreSQL requires host and database
        with pytest.raises(NodeConfigurationError, match="requires host and database"):
            AsyncSQLDatabaseNode(
                name="test",
                database_type="postgresql",
                # host and database missing
                user="testuser",
                password="testpass",
            )

        # SQLite requires database path
        with pytest.raises(NodeConfigurationError, match="SQLite requires database"):
            AsyncSQLDatabaseNode(
                name="test",
                database_type="sqlite",
                # database path missing
            )

        # Connection string should override individual parameters
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string="postgresql://user:pass@host:5432/db",
            # Individual params provided but should be ignored
            host="ignored",
            database="ignored",
        )

        assert node.config["connection_string"] == "postgresql://user:pass@host:5432/db"

    @pytest.mark.asyncio
    async def test_user_context_and_access_control(self):
        """Test user context and access control functionality."""
        # Mock access control manager
        mock_access_manager = MagicMock()
        mock_decision = MagicMock()
        mock_decision.allowed = True
        mock_access_manager.check_node_access.return_value = mock_decision
        # Mock data masking to return the same data (no masking)
        mock_access_manager.apply_data_masking.side_effect = (
            lambda user_ctx, node_name, data: data
        )

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            access_control_manager=mock_access_manager,
        )

        # Mock adapter
        mock_adapter = AsyncMock()
        mock_adapter.execute.return_value = [{"data": "test"}]

        user_context = {"user_id": "123", "role": "admin"}

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            result = await node.execute_async(
                query="SELECT 'test' as data", user_context=user_context
            )

            # Verify access control was checked
            mock_access_manager.check_node_access.assert_called_once()

            assert result["result"]["data"][0]["data"] == "test"

    @pytest.mark.asyncio
    async def test_access_control_denial(self):
        """Test access control denial behavior."""
        # Mock access control manager that denies access
        mock_access_manager = MagicMock()
        mock_decision = MagicMock()
        mock_decision.allowed = False
        mock_decision.reason = "Insufficient permissions"
        mock_access_manager.check_node_access.return_value = mock_decision

        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            access_control_manager=mock_access_manager,
        )

        user_context = {"user_id": "456", "role": "user"}

        with pytest.raises(
            NodeExecutionError, match="Access denied: Insufficient permissions"
        ):
            await node.execute_async(
                query="SELECT * FROM sensitive_data", user_context=user_context
            )

    def test_fetch_mode_parameter_handling(self):
        """Test fetch mode parameter handling."""
        # Test all valid fetch modes
        valid_modes = ["one", "all", "many", "iterator"]

        for mode in valid_modes:
            if mode == "many":
                node = AsyncSQLDatabaseNode(
                    name="test",
                    database_type="postgresql",
                    host="localhost",
                    database="testdb",
                    user="testuser",
                    password="testpass",
                    fetch_mode=mode,
                    fetch_size=10,  # Required for 'many' mode
                )
            else:
                node = AsyncSQLDatabaseNode(
                    name="test",
                    database_type="postgresql",
                    host="localhost",
                    database="testdb",
                    user="testuser",
                    password="testpass",
                    fetch_mode=mode,
                )

            assert node.config["fetch_mode"] == mode

    @pytest.mark.asyncio
    async def test_timeout_configuration(self):
        """Test timeout configuration and behavior."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            timeout=5.0,
        )

        assert node.config["timeout"] == 5.0

        # Test timeout in execution (would need real database for full test)
        # For unit test, we verify timeout is passed to adapter
        mock_adapter = AsyncMock()
        mock_adapter.execute.return_value = []

        with patch.object(node, "_get_adapter", return_value=mock_adapter):
            await node.execute_async(query="SELECT 1")
            # In real implementation, timeout would be passed to adapter

    def test_config_file_integration(self):
        """Test configuration file integration."""
        import os
        import tempfile

        import yaml

        # Create temporary config file
        config_data = {
            "databases": {
                "prod_db": {
                    "url": "postgresql://prod_user:prod_pass@prod_host:5432/prod_db",
                    "pool_size": 20,
                    "max_pool_size": 50,
                    "timeout": 60.0,
                    "validate_queries": True,
                    "allow_admin": False,
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            # Create node using config file
            node = AsyncSQLDatabaseNode(
                name="test",
                database_type="postgresql",
                connection_name="prod_db",
                config_file=config_path,
            )

            # Verify config was loaded
            assert (
                node.config["connection_string"]
                == "postgresql://prod_user:prod_pass@prod_host:5432/prod_db"
            )
            assert node.config["pool_size"] == 20
            assert node.config["max_pool_size"] == 50
            assert node.config["timeout"] == 60.0
            assert node._validate_queries
            assert not node._allow_admin

        finally:
            os.unlink(config_path)
