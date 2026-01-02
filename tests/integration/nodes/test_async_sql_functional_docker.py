"""Docker-based functional tests for AsyncSQLDatabaseNode - NO MOCKS."""

import asyncio
import base64
import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import asyncpg
import pytest
from kailash.nodes.data.async_sql import (
    AsyncSQLDatabaseNode,
    DatabaseConfig,
    DatabaseType,
    MySQLAdapter,
    PostgreSQLAdapter,
    QueryValidator,
    SQLiteAdapter,
)

from tests.integration.docker_test_base import DockerIntegrationTestBase


@pytest.mark.integration
@pytest.mark.requires_docker
class TestQueryValidatorFunctionalityDocker(DockerIntegrationTestBase):
    """Test SQL query validation with real database."""

    @pytest.fixture
    async def test_db(self, test_database):
        """Create test tables for validation testing."""
        await test_database.execute(
            """
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255),
                email VARCHAR(255)
            )
        """
        )
        await test_database.execute(
            """
            CREATE TABLE accounts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                balance DECIMAL(10, 2)
            )
        """
        )
        yield test_database

    def test_dangerous_pattern_detection(self):
        """Test detection of SQL injection patterns."""
        # Test multiple statement injection
        dangerous_queries = [
            "SELECT * FROM users; DROP TABLE users",
            "SELECT * FROM users; DELETE FROM accounts",
            "UPDATE users SET name='test'; CREATE TABLE malicious",
            "SELECT * FROM users WHERE id=1; INSERT INTO admin VALUES('hacker')",
        ]

        for query in dangerous_queries:
            with pytest.raises(Exception) as exc_info:
                QueryValidator.validate_query(query)
            assert "dangerous pattern" in str(exc_info.value).lower()

    def test_admin_pattern_enforcement(self):
        """Test enforcement of admin-only patterns."""
        admin_queries = [
            "CREATE TABLE new_table (id INT)",
            "ALTER TABLE users ADD COLUMN email VARCHAR(255)",
            "DROP TABLE old_data",
            "CREATE INDEX idx_users_email ON users(email)",
            "GRANT SELECT ON users TO public_user",
            "REVOKE ALL ON accounts FROM user1",
            "TRUNCATE TABLE logs",
        ]

        # Test without admin permission (should fail)
        for query in admin_queries:
            with pytest.raises(Exception) as exc_info:
                QueryValidator.validate_query(query, allow_admin=False)
            assert "administrative command" in str(exc_info.value).lower()

        # Test with admin permission (should pass)
        for query in admin_queries:
            # Should not raise exception
            QueryValidator.validate_query(query, allow_admin=True)

    @pytest.mark.asyncio
    async def test_query_validation_with_real_execution(self, async_sql_node, test_db):
        """Test that validated queries execute successfully."""
        # Test safe query
        safe_query = "SELECT * FROM users WHERE name = $1"
        QueryValidator.validate_query(safe_query)  # Should pass

        # Execute the safe query
        result = await async_sql_node.execute(
            query=safe_query, parameters=["test_user"]
        )
        assert result["success"] is True

        # Test dangerous query is blocked before execution
        dangerous_query = "SELECT * FROM users; DROP TABLE users"
        with pytest.raises(Exception):
            QueryValidator.validate_query(dangerous_query)


@pytest.mark.integration
@pytest.mark.requires_docker
class TestDatabaseAdapterFunctionalityDocker(DockerIntegrationTestBase):
    """Test database adapter functionality with real databases."""

    @pytest.fixture
    async def complex_table(self, test_database):
        """Create table with complex data types."""
        await test_database.execute(
            """
            CREATE TABLE complex_data (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255),
                balance DECIMAL(10, 2),
                created_at TIMESTAMP,
                birth_date DATE,
                profile_image BYTEA,
                unique_id UUID,
                tags TEXT[],
                settings JSONB,
                is_active BOOLEAN,
                last_login TIMESTAMP NULL
            )
        """
        )
        yield test_database

    @pytest.mark.asyncio
    async def test_complex_type_serialization(self, async_sql_node, complex_table):
        """Test serialization of complex types with real database."""
        test_uuid = uuid.uuid4()
        test_data = {
            "name": "Test User",
            "balance": Decimal("1234.56"),
            "created_at": datetime(2023, 12, 1, 10, 0, 0),
            "birth_date": date(1990, 5, 15),
            "profile_image": b"\x89PNG\r\n\x1a\n",
            "unique_id": test_uuid,
            "tags": ["python", "sql", "async"],
            "settings": {"theme": "dark", "notifications": True},
            "is_active": True,
            "last_login": None,
        }

        # Insert complex data
        result = await async_sql_node.execute(
            query="""
                INSERT INTO complex_data
                (name, balance, created_at, birth_date, profile_image,
                 unique_id, tags, settings, is_active, last_login)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING *
            """,
            parameters=[
                test_data["name"],
                test_data["balance"],
                test_data["created_at"],
                test_data["birth_date"],
                test_data["profile_image"],
                test_data["unique_id"],
                test_data["tags"],
                json.dumps(test_data["settings"]),
                test_data["is_active"],
                test_data["last_login"],
            ],
        )

        assert result["success"] is True
        row = result["rows"][0]

        # Verify serialization
        assert row["name"] == "Test User"
        assert float(row["balance"]) == 1234.56
        assert "2023-12-01" in row["created_at"]
        assert row["birth_date"] == "1990-05-15"
        assert base64.b64decode(row["profile_image"]) == b"\x89PNG\r\n\x1a\n"
        assert row["unique_id"] == str(test_uuid)
        assert row["tags"] == ["python", "sql", "async"]
        assert row["settings"]["theme"] == "dark"
        assert row["is_active"] is True
        assert row["last_login"] is None


@pytest.mark.integration
@pytest.mark.requires_docker
class TestAsyncSQLSecurityFeaturesDocker(DockerIntegrationTestBase):
    """Test security features with real database."""

    @pytest.fixture
    async def security_test_db(self, test_database):
        """Create tables for security testing."""
        await test_database.execute(
            """
            CREATE TABLE sensitive_data (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                ssn VARCHAR(20),
                credit_card VARCHAR(20),
                api_key VARCHAR(100)
            )
        """
        )

        # Insert test data
        await test_database.execute(
            """
            INSERT INTO sensitive_data (user_id, ssn, credit_card, api_key)
            VALUES
                (1, '123-45-6789', '4111-1111-1111-1111', 'sk_test_123456'),
                (2, '987-65-4321', '5500-0000-0000-0004', 'sk_live_abcdef')
        """
        )

        yield test_database

    @pytest.mark.asyncio
    async def test_parameterized_queries_prevent_injection(
        self, async_sql_node, security_test_db
    ):
        """Test that parameterized queries prevent SQL injection."""
        # Attempt injection via parameter (should be safe)
        malicious_input = "1' OR '1'='1"

        result = await async_sql_node.execute(
            query="SELECT * FROM sensitive_data WHERE user_id = $1",
            parameters=[malicious_input],
        )

        # Should return no results (injection attempt failed)
        assert result["success"] is True
        assert len(result["rows"]) == 0

        # Verify with legitimate query
        result = await async_sql_node.execute(
            query="SELECT * FROM sensitive_data WHERE user_id = $1", parameters=[1]
        )

        assert result["success"] is True
        assert len(result["rows"]) == 1
        assert result["rows"][0]["user_id"] == 1

    @pytest.mark.asyncio
    async def test_transaction_isolation(self, async_sql_node, security_test_db):
        """Test transaction isolation prevents data leaks."""
        # Start transaction 1
        await async_sql_node.execute(query="BEGIN")

        # Update sensitive data in transaction
        await async_sql_node.execute(
            query="UPDATE sensitive_data SET api_key = $1 WHERE user_id = $2",
            parameters=["new_key_123", 1],
        )

        # Create a second connection to test isolation
        second_node = AsyncSQLDatabaseNode(
            database_config=async_sql_node.database_config,
            pool_settings=async_sql_node.pool_settings,
        )

        # Query from second connection (should see old data)
        result = await second_node.execute(
            query="SELECT api_key FROM sensitive_data WHERE user_id = $1",
            parameters=[1],
        )

        assert result["rows"][0]["api_key"] == "sk_test_123456"  # Old value

        # Commit first transaction
        await async_sql_node.execute(query="COMMIT")

        # Now second connection should see new data
        result = await second_node.execute(
            query="SELECT api_key FROM sensitive_data WHERE user_id = $1",
            parameters=[1],
        )

        assert result["rows"][0]["api_key"] == "new_key_123"  # New value


@pytest.mark.integration
@pytest.mark.requires_docker
class TestAsyncSQLPerformanceFeaturesDocker(DockerIntegrationTestBase):
    """Test performance features with real database."""

    @pytest.fixture
    async def performance_test_db(self, test_database):
        """Create tables with large datasets for performance testing."""
        await test_database.execute(
            """
            CREATE TABLE performance_test (
                id SERIAL PRIMARY KEY,
                category VARCHAR(50),
                value INTEGER,
                data JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create index for performance
        await test_database.execute(
            """
            CREATE INDEX idx_performance_category ON performance_test(category)
        """
        )

        yield test_database

    @pytest.mark.asyncio
    async def test_batch_operations_performance(
        self, async_sql_node, performance_test_db
    ):
        """Test batch insert performance with real database."""
        # Prepare batch data
        batch_size = 1000
        categories = ["A", "B", "C", "D", "E"]

        start_time = datetime.now()

        # Insert batch data
        for i in range(0, batch_size, 100):
            batch_values = []
            for j in range(100):
                idx = i + j
                batch_values.extend(
                    [
                        categories[idx % 5],
                        idx * 10,
                        json.dumps({"index": idx, "squared": idx * idx}),
                    ]
                )

            placeholders = ", ".join(
                f"(${k+1}, ${k+2}, ${k+3})" for k in range(0, len(batch_values), 3)
            )

            await async_sql_node.execute(
                query=f"""
                    INSERT INTO performance_test (category, value, data)
                    VALUES {placeholders}
                """,
                parameters=batch_values,
            )

        insert_duration = (datetime.now() - start_time).total_seconds()

        # Verify data
        count_result = await async_sql_node.execute(
            query="SELECT COUNT(*) as count FROM performance_test"
        )
        assert count_result["rows"][0]["count"] == batch_size

        # Test indexed query performance
        start_time = datetime.now()

        result = await async_sql_node.execute(
            query="""
                SELECT category, COUNT(*) as count, AVG(value) as avg_value
                FROM performance_test
                GROUP BY category
                ORDER BY category
            """
        )

        query_duration = (datetime.now() - start_time).total_seconds()

        assert result["success"] is True
        assert len(result["rows"]) == 5
        assert all(row["count"] == 200 for row in result["rows"])

        # Performance assertions
        assert insert_duration < 5.0  # Should insert 1000 rows in under 5 seconds
        assert query_duration < 0.5  # Indexed query should be fast

    @pytest.mark.asyncio
    async def test_connection_pool_efficiency(
        self, async_sql_node, performance_test_db
    ):
        """Test connection pool reuse with concurrent queries."""
        # Insert test data
        await async_sql_node.execute(
            query="""
                INSERT INTO performance_test (category, value, data)
                SELECT
                    chr(65 + (i % 5)) as category,
                    i * 10 as value,
                    jsonb_build_object('id', i) as data
                FROM generate_series(1, 100) as i
            """
        )

        # Run concurrent queries to test pool efficiency
        async def run_query(query_id):
            result = await async_sql_node.execute(
                query="""
                    SELECT category, COUNT(*) as count
                    FROM performance_test
                    WHERE value > $1
                    GROUP BY category
                """,
                parameters=[query_id * 100],
            )
            return result["success"]

        # Execute 20 concurrent queries
        start_time = datetime.now()
        tasks = [run_query(i) for i in range(20)]
        results = await asyncio.gather(*tasks)
        duration = (datetime.now() - start_time).total_seconds()

        # All queries should succeed
        assert all(results)

        # Should complete quickly due to connection pooling
        assert duration < 2.0  # 20 queries in under 2 seconds
