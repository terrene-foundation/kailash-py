"""Tests for AsyncSQLDatabaseNode security features."""

import pytest
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode, QueryValidator
from kailash.sdk_exceptions import (
    NodeConfigurationError,
    NodeExecutionError,
    NodeValidationError,
)


class TestQueryValidator:
    """Test QueryValidator security validation."""

    def test_validate_query_allows_safe_queries(self):
        """Test that safe queries are allowed."""
        safe_queries = [
            "SELECT * FROM users WHERE id = :id",
            "INSERT INTO logs (message) VALUES (:message)",
            "UPDATE settings SET value = :value WHERE key = :key",
            "DELETE FROM sessions WHERE expires_at < :now",
        ]

        for query in safe_queries:
            # Should not raise
            QueryValidator.validate_query(query)

    def test_validate_query_blocks_dangerous_patterns(self):
        """Test that dangerous patterns are blocked."""
        dangerous_queries = [
            # Multiple statements
            "SELECT * FROM users; DROP TABLE users",
            "UPDATE users SET admin=1; DELETE FROM audit_log",
            # SQL comments that might hide code
            "SELECT * FROM users WHERE id = 1 -- OR 1=1",
            "SELECT * FROM users /* OR 1=1 */ WHERE id = 1",
            # Union-based injection
            "SELECT * FROM users WHERE id = 1 UNION SELECT * FROM passwords",
            # Time-based blind injection
            "SELECT * FROM users WHERE id = 1 AND SLEEP(5)",
            "SELECT * FROM users WHERE id = 1 AND PG_SLEEP(5)",
            # File operations
            "SELECT LOAD_FILE('/etc/passwd')",
            "SELECT * INTO OUTFILE '/tmp/data.txt' FROM users",
            # System commands
            "EXEC XP_CMDSHELL 'dir'",
        ]

        for query in dangerous_queries:
            with pytest.raises(NodeValidationError, match="dangerous pattern"):
                QueryValidator.validate_query(query)

    def test_validate_query_blocks_admin_commands_by_default(self):
        """Test that admin commands are blocked by default."""
        admin_queries = [
            "CREATE TABLE new_table (id INT)",
            "ALTER TABLE users ADD COLUMN admin BOOLEAN",
            "DROP TABLE users",
            "GRANT ALL ON users TO hacker",
            "REVOKE SELECT ON users FROM public",
            "TRUNCATE TABLE audit_log",
        ]

        for query in admin_queries:
            with pytest.raises(NodeValidationError, match="administrative command"):
                QueryValidator.validate_query(query, allow_admin=False)

    def test_validate_query_allows_admin_commands_when_enabled(self):
        """Test that admin commands are allowed when explicitly enabled."""
        admin_queries = [
            "CREATE TABLE new_table (id INT)",
            "ALTER TABLE users ADD COLUMN admin BOOLEAN",
            "DROP TABLE users",
        ]

        for query in admin_queries:
            # Should not raise when allow_admin=True
            QueryValidator.validate_query(query, allow_admin=True)

    def test_validate_identifier(self):
        """Test identifier validation."""
        # Valid identifiers
        valid_identifiers = [
            "users",
            "user_sessions",
            "schema1.table1",
            "_private_table",
            "Table123",
        ]

        for identifier in valid_identifiers:
            # Should not raise
            QueryValidator.validate_identifier(identifier)

        # Invalid identifiers
        invalid_identifiers = [
            "users; DROP TABLE users",
            "users/*comment*/",
            "123table",  # Starts with number
            "user-table",  # Contains hyphen
            "user table",  # Contains space
            "'users'",  # Contains quotes
            "schema.table.column",  # Too many dots
        ]

        for identifier in invalid_identifiers:
            with pytest.raises(NodeValidationError, match="Invalid identifier"):
                QueryValidator.validate_identifier(identifier)

    def test_sanitize_string_literal(self):
        """Test string literal sanitization."""
        assert QueryValidator.sanitize_string_literal("hello") == "hello"
        assert QueryValidator.sanitize_string_literal("O'Brien") == "O''Brien"
        assert (
            QueryValidator.sanitize_string_literal("path\\to\\file")
            == "path\\\\to\\\\file"
        )
        assert (
            QueryValidator.sanitize_string_literal("'; DROP TABLE users--")
            == "''; DROP TABLE users--"
        )

    def test_validate_connection_string(self):
        """Test connection string validation."""
        # Valid connection strings
        valid_strings = [
            "postgresql://user:pass@localhost/db",
            "mysql://user:pass@host:3306/database",
            "postgresql://user:pass@host/db?sslmode=require",
        ]

        for conn_string in valid_strings:
            # Should not raise
            QueryValidator.validate_connection_string(conn_string)

        # Suspicious connection strings
        suspicious_strings = [
            "postgresql://user:pass@localhost/db;host=|whoami",
            "postgresql://user:pass@localhost/db;host=`id`",
            "postgresql://user:pass@localhost/db?sslcert=/etc/passwd",
            "postgresql://user:pass@localhost/db?sslkey=/etc/shadow",
        ]

        for conn_string in suspicious_strings:
            with pytest.raises(NodeValidationError, match="suspicious pattern"):
                QueryValidator.validate_connection_string(conn_string)


class TestAsyncSQLSecurityFeatures:
    """Test AsyncSQLDatabaseNode security features."""

    def test_security_enabled_by_default(self):
        """Test that query validation is enabled by default."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
        )

        assert node._validate_queries is True
        assert node._allow_admin is False

    def test_security_can_be_disabled(self):
        """Test that security features can be disabled."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            validate_queries=False,
            allow_admin=True,
        )

        assert node._validate_queries is False
        assert node._allow_admin is True

    def test_dangerous_query_in_config_blocked(self):
        """Test that dangerous queries in initial config are blocked."""
        with pytest.raises(
            NodeConfigurationError, match="Initial query validation failed"
        ):
            AsyncSQLDatabaseNode(
                name="test",
                database_type="postgresql",
                host="localhost",
                database="testdb",
                user="testuser",
                password="testpass",
                query="SELECT * FROM users; DROP TABLE users",
            )

    def test_admin_query_in_config_blocked_by_default(self):
        """Test that admin queries in config are blocked by default."""
        with pytest.raises(NodeConfigurationError, match="administrative command"):
            AsyncSQLDatabaseNode(
                name="test",
                database_type="postgresql",
                host="localhost",
                database="testdb",
                user="testuser",
                password="testpass",
                query="CREATE TABLE new_table (id INT)",
            )

    def test_admin_query_allowed_when_enabled(self):
        """Test that admin queries are allowed when admin mode is enabled."""
        # Should not raise
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            query="CREATE TABLE new_table (id INT)",
            allow_admin=True,
        )

        assert node.config["query"] == "CREATE TABLE new_table (id INT)"

    def test_dangerous_connection_string_blocked(self):
        """Test that dangerous connection strings are blocked."""
        with pytest.raises(
            NodeConfigurationError, match="Connection string failed security validation"
        ):
            AsyncSQLDatabaseNode(
                name="test",
                database_type="postgresql",
                connection_string="postgresql://user:pass@localhost/db;host=|whoami",
            )

    def test_dangerous_connection_string_allowed_when_validation_disabled(self):
        """Test that dangerous connection strings are allowed when validation is disabled."""
        # Should not raise
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            connection_string="postgresql://user:pass@localhost/db;host=|whoami",
            validate_queries=False,
        )

        assert node._validate_queries is False

    @pytest.mark.asyncio
    async def test_runtime_query_validation(self):
        """Test that queries are validated at runtime."""
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
        )

        # Mock the adapter to avoid actual database connection
        from unittest.mock import AsyncMock, patch

        with patch.object(node, "_get_adapter") as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_get_adapter.return_value = mock_adapter
            mock_adapter.execute = AsyncMock(return_value=[])

            # Dangerous query should be blocked
            with pytest.raises(NodeExecutionError, match="Query validation failed"):
                await node.execute_async(query="SELECT * FROM users; DROP TABLE users")

            # Safe query should work
            result = await node.execute_async(
                query="SELECT * FROM users WHERE id = :id", params={"id": 1}
            )

            assert result["result"]["data"] == []

    @pytest.mark.asyncio
    async def test_runtime_admin_query_validation(self):
        """Test that admin queries are validated at runtime."""
        # Node without admin privileges
        node = AsyncSQLDatabaseNode(
            name="test",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            allow_admin=False,
        )

        # Mock the adapter
        from unittest.mock import AsyncMock, patch

        with patch.object(node, "_get_adapter") as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_get_adapter.return_value = mock_adapter

            # Admin query should be blocked
            with pytest.raises(NodeExecutionError, match="administrative command"):
                await node.execute_async(query="CREATE TABLE new_table (id INT)")

        # Node with admin privileges
        admin_node = AsyncSQLDatabaseNode(
            name="test_admin",
            database_type="postgresql",
            host="localhost",
            database="testdb",
            user="testuser",
            password="testpass",
            allow_admin=True,
        )

        with patch.object(admin_node, "_get_adapter") as mock_get_adapter:
            mock_adapter = AsyncMock()
            mock_get_adapter.return_value = mock_adapter
            mock_adapter.execute = AsyncMock(return_value=[])

            # Admin query should be allowed
            result = await admin_node.execute_async(
                query="CREATE TABLE new_table (id INT)"
            )

            assert result is not None
