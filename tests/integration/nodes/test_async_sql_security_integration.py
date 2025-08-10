"""Integration tests for AsyncSQLDatabaseNode security features with REAL PostgreSQL."""

import pytest
import pytest_asyncio
from tests.utils.docker_config import get_postgres_connection_string

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError

# Mark all tests as requiring postgres and as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]


class TestAsyncSQLSecurityIntegration:
    """Test security features with REAL PostgreSQL database."""

    @pytest_asyncio.fixture
    async def setup_database(self):
        """Set up test database."""
        conn_string = get_postgres_connection_string()

        # Create test table - this needs admin privileges
        setup_node = AsyncSQLDatabaseNode(
            name="setup",
            database_type="postgresql",
            connection_string=conn_string,
            allow_admin=True,  # Allow admin for setup
        )

        await setup_node.execute_async(query="DROP TABLE IF EXISTS security_test")
        await setup_node.execute_async(
            query="""
            CREATE TABLE security_test (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100),
                email VARCHAR(100),
                is_admin BOOLEAN DEFAULT false
            )
        """
        )

        # Insert test data
        await setup_node.execute_async(
            query="INSERT INTO security_test (username, email, is_admin) VALUES (:username, :email, :is_admin)",
            params={
                "username": "testuser",
                "email": "test@example.com",
                "is_admin": False,
            },
        )
        await setup_node.execute_async(
            query="INSERT INTO security_test (username, email, is_admin) VALUES (:username, :email, :is_admin)",
            params={
                "username": "admin",
                "email": "admin@example.com",
                "is_admin": True,
            },
        )

        yield conn_string

        # Cleanup
        await setup_node.execute_async(query="DROP TABLE IF EXISTS security_test")
        await setup_node.cleanup()

    @pytest.mark.asyncio
    async def test_sql_injection_prevention(self, setup_database):
        """Test that SQL injection attempts are blocked."""
        conn_string = setup_database

        # Create node with security enabled (default)
        node = AsyncSQLDatabaseNode(
            name="secure_node",
            database_type="postgresql",
            connection_string=conn_string,
        )

        # Attempt SQL injection via concatenation
        with pytest.raises(NodeExecutionError, match="dangerous pattern"):
            await node.execute_async(
                query="SELECT * FROM security_test WHERE username = 'admin'; DROP TABLE security_test; --'"
            )

        # Verify table still exists
        result = await node.execute_async(
            query="SELECT COUNT(*) as count FROM security_test"
        )
        assert result["result"]["data"][0]["count"] == 2

        # Safe parameterized query should work
        result = await node.execute_async(
            query="SELECT * FROM security_test WHERE username = :username",
            params={"username": "admin'; DROP TABLE security_test; --"},
        )
        # Should return no results (no user with that exact name)
        assert len(result["result"]["data"]) == 0

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_admin_command_blocking(self, setup_database):
        """Test that admin commands are blocked by default."""
        conn_string = setup_database

        # Create node without admin privileges (default)
        node = AsyncSQLDatabaseNode(
            name="user_node",
            database_type="postgresql",
            connection_string=conn_string,
        )

        # Try to create a table
        with pytest.raises(NodeExecutionError, match="administrative command"):
            await node.execute_async(query="CREATE TABLE hacker_table (id INT)")

        # Try to drop a table
        with pytest.raises(NodeExecutionError, match="administrative command"):
            await node.execute_async(query="DROP TABLE security_test")

        # Try to grant privileges
        with pytest.raises(NodeExecutionError, match="administrative command"):
            await node.execute_async(query="GRANT ALL ON security_test TO PUBLIC")

        # Regular queries should work
        result = await node.execute_async(
            query="SELECT * FROM security_test WHERE is_admin = :is_admin",
            params={"is_admin": False},
        )
        assert len(result["result"]["data"]) == 1
        assert result["result"]["data"][0]["username"] == "testuser"

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_admin_mode_allows_ddl(self, setup_database):
        """Test that admin mode allows DDL commands."""
        conn_string = setup_database

        # Create node with admin privileges
        admin_node = AsyncSQLDatabaseNode(
            name="admin_node",
            database_type="postgresql",
            connection_string=conn_string,
            allow_admin=True,
        )

        # Create a new table
        await admin_node.execute_async(
            query="CREATE TABLE admin_test_table (id SERIAL PRIMARY KEY, name VARCHAR(50))"
        )

        # Verify table was created
        result = await admin_node.execute_async(
            query="""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'admin_test_table'
            """
        )
        assert len(result["result"]["data"]) == 1

        # Drop the table
        await admin_node.execute_async(query="DROP TABLE admin_test_table")

        # Verify table was dropped
        result = await admin_node.execute_async(
            query="""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'admin_test_table'
            """
        )
        assert len(result["result"]["data"]) == 0

        await admin_node.cleanup()

    @pytest.mark.asyncio
    async def test_comment_injection_prevention(self, setup_database):
        """Test that SQL comment injection is prevented."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="secure_node",
            database_type="postgresql",
            connection_string=conn_string,
        )

        # Try comment-based injection
        with pytest.raises(NodeExecutionError, match="dangerous pattern"):
            await node.execute_async(
                query="SELECT * FROM security_test WHERE username = 'admin' -- ' OR 1=1"
            )

        # Try multi-line comment injection
        with pytest.raises(NodeExecutionError, match="dangerous pattern"):
            await node.execute_async(
                query="SELECT * FROM security_test WHERE username = 'admin' /* ' OR 1=1 */"
            )

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_union_injection_prevention(self, setup_database):
        """Test that UNION-based injection is prevented."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="secure_node",
            database_type="postgresql",
            connection_string=conn_string,
        )

        # Try UNION injection
        with pytest.raises(NodeExecutionError, match="dangerous pattern"):
            await node.execute_async(
                query="SELECT username, email FROM security_test WHERE id = 1 UNION SELECT table_name, column_name FROM information_schema.columns"
            )

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_security_bypass_option(self, setup_database):
        """Test that security can be bypassed when explicitly disabled."""
        conn_string = setup_database

        # Create node with security disabled (NOT RECOMMENDED)
        insecure_node = AsyncSQLDatabaseNode(
            name="insecure_node",
            database_type="postgresql",
            connection_string=conn_string,
            validate_queries=False,
        )

        # Dangerous queries should now work (but still fail at DB level if invalid)
        # This query would normally be blocked
        query_with_comment = (
            "SELECT * FROM security_test WHERE username = 'admin' -- this is a comment"
        )

        # Should not raise validation error
        result = await insecure_node.execute_async(query=query_with_comment)
        assert len(result["result"]["data"]) == 1
        assert result["result"]["data"][0]["username"] == "admin"

        await insecure_node.cleanup()

    @pytest.mark.asyncio
    async def test_time_based_injection_prevention(self, setup_database):
        """Test that time-based blind SQL injection is prevented."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="secure_node",
            database_type="postgresql",
            connection_string=conn_string,
        )

        # Try time-based injection with PG_SLEEP
        with pytest.raises(NodeExecutionError, match="dangerous pattern"):
            await node.execute_async(
                query="SELECT * FROM security_test WHERE username = 'admin' AND PG_SLEEP(5) IS NOT NULL"
            )

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_parameterized_queries_safe(self, setup_database):
        """Test that parameterized queries handle malicious input safely."""
        conn_string = setup_database

        node = AsyncSQLDatabaseNode(
            name="secure_node",
            database_type="postgresql",
            connection_string=conn_string,
        )

        # Various injection attempts via parameters (all should be safe)
        malicious_inputs = [
            "admin' OR '1'='1",
            "admin'; DROP TABLE security_test; --",
            "admin' UNION SELECT null, null, null --",
            "admin' AND PG_SLEEP(5)--",
        ]

        for malicious_input in malicious_inputs:
            # These should all safely return no results
            result = await node.execute_async(
                query="SELECT * FROM security_test WHERE username = :username",
                params={"username": malicious_input},
            )
            assert len(result["result"]["data"]) == 0

        # Verify table still exists and has correct data
        result = await node.execute_async(
            query="SELECT COUNT(*) as count FROM security_test"
        )
        assert result["result"]["data"][0]["count"] == 2

        await node.cleanup()
