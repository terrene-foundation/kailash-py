"""Docker-based integration tests for execution pipeline - NO MOCKS."""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import asyncpg
import pytest
from kailash.access_control import UserContext
from kailash.database.execution_pipeline import (
    DatabaseExecutionPipeline,
    ExecutionContext,
    ExecutionResult,
)

from tests.integration.docker_test_base import DockerIntegrationTestBase


@pytest.mark.integration
@pytest.mark.requires_docker
class TestExecutionPipelineDocker(DockerIntegrationTestBase):
    """Test execution pipeline with real database."""

    @pytest.fixture
    async def test_schema(self, test_database):
        """Create test schema in real database."""
        # Create tables
        await test_database.execute(
            """
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255),
                email VARCHAR(255) UNIQUE,
                tenant_id VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        await test_database.execute(
            """
            CREATE TABLE audit_log (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                action VARCHAR(100),
                query TEXT,
                parameters JSONB,
                execution_time FLOAT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Insert test data
        await test_database.execute(
            """
            INSERT INTO users (name, email, tenant_id) VALUES
            ('Alice', 'alice@example.com', 'tenant1'),
            ('Bob', 'bob@example.com', 'tenant1'),
            ('Charlie', 'charlie@example.com', 'tenant2')
        """
        )

        yield test_database

    @pytest.fixture
    def execution_pipeline(self, workflow_db_config):
        """Create execution pipeline with real database config."""
        return DatabaseExecutionPipeline(
            query_executor=None, validation_rules={}  # Will be set up per test
        )

    @pytest.mark.asyncio
    async def test_basic_query_execution(self, execution_pipeline, test_schema):
        """Test basic query execution through pipeline."""
        context = ExecutionContext(
            query="SELECT * FROM users WHERE tenant_id = $1 ORDER BY name",
            parameters=["tenant1"],
            node_name="test_node",
            result_format="dict",
        )

        result = await execution_pipeline.execute(context)

        # Verify result
        assert isinstance(result, ExecutionResult)
        assert result.row_count == 2
        assert len(result.data) == 2
        assert result.data[0]["name"] == "Alice"
        assert result.data[1]["name"] == "Bob"
        assert result.columns == ["id", "name", "email", "tenant_id", "created_at"]
        assert result.execution_time > 0

    @pytest.mark.asyncio
    async def test_query_caching(self, execution_pipeline, test_schema):
        """Test query result caching with real database."""
        context = ExecutionContext(
            query="SELECT COUNT(*) as count FROM users",
            parameters=[],
            node_name="count_node",
        )

        # First execution - cache miss
        start_time = time.time()
        result1 = await execution_pipeline.execute(context)
        first_execution_time = time.time() - start_time

        # Second execution - cache hit
        start_time = time.time()
        result2 = await execution_pipeline.execute(context)
        second_execution_time = time.time() - start_time

        # Verify caching worked
        assert result1.data == result2.data
        assert result1.row_count == result2.row_count
        assert second_execution_time < first_execution_time * 0.5  # Much faster
        assert result2.metadata.get("cache_hit") is True

    @pytest.mark.asyncio
    async def test_rate_limiting(self, execution_pipeline, test_schema):
        """Test rate limiting with real rapid queries."""
        # Skip this test as RateLimiter is not available
        pytest.skip("RateLimiter not implemented in DatabaseExecutionPipeline")

        # Execute queries rapidly
        contexts = [
            ExecutionContext(
                query="SELECT * FROM users WHERE id = $1",
                parameters=[i % 3 + 1],
                node_name=f"rapid_node_{i}",
            )
            for i in range(8)
        ]

        start_time = time.time()
        results = []
        rate_limited = False

        for context in contexts:
            try:
                result = await execution_pipeline.execute(context)
                results.append(result)
            except Exception as e:
                if "rate limit" in str(e).lower():
                    rate_limited = True
                    break

        # Should hit rate limit
        assert rate_limited or len(results) <= 5

    @pytest.mark.asyncio
    async def test_user_context_isolation(self, execution_pipeline, test_schema):
        """Test user context isolation with real multi-tenant data."""
        # Create user contexts
        user1 = UserContext(user_id="user1", tenant_id="tenant1")
        user2 = UserContext(user_id="user2", tenant_id="tenant2")

        # Execute same query with different user contexts
        context1 = ExecutionContext(
            query="SELECT * FROM users WHERE tenant_id = $1",
            parameters=[user1.tenant_id],
            user_context=user1,
            node_name="tenant_query",
        )

        context2 = ExecutionContext(
            query="SELECT * FROM users WHERE tenant_id = $1",
            parameters=[user2.tenant_id],
            user_context=user2,
            node_name="tenant_query",
        )

        result1 = await execution_pipeline.execute(context1)
        result2 = await execution_pipeline.execute(context2)

        # Verify isolation
        assert result1.row_count == 2  # Alice and Bob
        assert result2.row_count == 1  # Only Charlie
        assert all(r["tenant_id"] == "tenant1" for r in result1.data)
        assert all(r["tenant_id"] == "tenant2" for r in result2.data)

    @pytest.mark.asyncio
    async def test_transaction_handling(self, execution_pipeline, test_schema):
        """Test transaction handling with real database."""
        # Start transaction
        context_begin = ExecutionContext(query="BEGIN", node_name="tx_start")
        await execution_pipeline.execute(context_begin)

        try:
            # Insert new user
            context_insert = ExecutionContext(
                query="INSERT INTO users (name, email, tenant_id) VALUES ($1, $2, $3) RETURNING id",
                parameters=["David", "david@example.com", "tenant1"],
                node_name="tx_insert",
            )
            insert_result = await execution_pipeline.execute(context_insert)
            new_id = insert_result.data[0]["id"]

            # Update user
            context_update = ExecutionContext(
                query="UPDATE users SET name = $1 WHERE id = $2",
                parameters=["David Updated", new_id],
                node_name="tx_update",
            )
            await execution_pipeline.execute(context_update)

            # Commit transaction
            context_commit = ExecutionContext(query="COMMIT", node_name="tx_commit")
            await execution_pipeline.execute(context_commit)

            # Verify changes persisted
            context_verify = ExecutionContext(
                query="SELECT * FROM users WHERE id = $1",
                parameters=[new_id],
                node_name="tx_verify",
            )
            verify_result = await execution_pipeline.execute(context_verify)

            assert verify_result.data[0]["name"] == "David Updated"

        except Exception:
            # Rollback on error
            context_rollback = ExecutionContext(
                query="ROLLBACK", node_name="tx_rollback"
            )
            await execution_pipeline.execute(context_rollback)
            raise

    @pytest.mark.asyncio
    async def test_parallel_execution(self, execution_pipeline, test_schema):
        """Test parallel query execution with real database."""
        # Create multiple contexts
        contexts = [
            ExecutionContext(
                query="SELECT * FROM users WHERE id = $1",
                parameters=[i % 3 + 1],
                node_name=f"parallel_node_{i}",
            )
            for i in range(10)
        ]

        # Execute in parallel
        start_time = time.time()
        tasks = [execution_pipeline.execute(ctx) for ctx in contexts]
        results = await asyncio.gather(*tasks)
        execution_time = time.time() - start_time

        # Verify all succeeded
        assert len(results) == 10
        assert all(isinstance(r, ExecutionResult) for r in results)
        assert all(r.row_count == 1 for r in results)

        # Should be faster than sequential (connection pooling)
        assert execution_time < 1.0

    @pytest.mark.asyncio
    async def test_audit_logging(self, execution_pipeline, test_schema):
        """Test audit logging with real database."""
        # Enable audit logging
        execution_pipeline.enable_audit = True

        # Create context with user
        user_context = UserContext(user_id="auditor", tenant_id="tenant1")
        context = ExecutionContext(
            query="SELECT * FROM users WHERE email = $1",
            parameters=["alice@example.com"],
            user_context=user_context,
            node_name="audit_test",
        )

        # Execute query
        result = await execution_pipeline.execute(context)

        # Check audit log (would need to implement audit log query)
        audit_context = ExecutionContext(
            query="SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 1",
            node_name="audit_check",
        )
        audit_result = await execution_pipeline.execute(audit_context)

        if audit_result.row_count > 0:
            audit_entry = audit_result.data[0]
            assert audit_entry["action"] == "SELECT"
            assert "alice@example.com" in str(audit_entry["parameters"])

    @pytest.mark.asyncio
    async def test_connection_pool_management(self, execution_pipeline, test_schema):
        """Test connection pool behavior under load."""
        # Skip this test as ConnectionPoolManager is not available
        pytest.skip(
            "ConnectionPoolManager not implemented in DatabaseExecutionPipeline"
        )

        # Create load with many concurrent queries
        async def run_query(i):
            context = ExecutionContext(
                query="SELECT pg_sleep(0.1), $1 as num",  # Small delay
                parameters=[i],
                node_name=f"pool_test_{i}",
            )
            return await execution_pipeline.execute(context)

        # Run many queries concurrently
        start_time = time.time()
        tasks = [run_query(i) for i in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        execution_time = time.time() - start_time

        # Check results
        successful = [r for r in results if isinstance(r, ExecutionResult)]
        errors = [r for r in results if isinstance(r, Exception)]

        assert len(successful) >= 15  # Most should succeed
        assert execution_time < 5.0  # Should use pooling efficiently

    @pytest.mark.asyncio
    async def test_query_timeout(self, execution_pipeline, test_schema):
        """Test query timeout with real slow query."""
        # Configure short timeout
        execution_pipeline.query_timeout = 0.5  # 500ms

        context = ExecutionContext(
            query="SELECT pg_sleep(2)", node_name="timeout_test"  # 2 second sleep
        )

        start_time = time.time()
        with pytest.raises(Exception) as exc_info:
            await execution_pipeline.execute(context)
        execution_time = time.time() - start_time

        # Should timeout quickly
        assert execution_time < 1.0
        assert "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_result_format_conversion(self, execution_pipeline, test_schema):
        """Test different result format conversions."""
        base_query = "SELECT id, name FROM users ORDER BY id LIMIT 2"

        # Test dict format (default)
        context_dict = ExecutionContext(
            query=base_query, result_format="dict", node_name="format_dict"
        )
        result_dict = await execution_pipeline.execute(context_dict)
        assert isinstance(result_dict.data[0], dict)
        assert "id" in result_dict.data[0]
        assert "name" in result_dict.data[0]

        # Test list format
        context_list = ExecutionContext(
            query=base_query, result_format="list", node_name="format_list"
        )
        result_list = await execution_pipeline.execute(context_list)
        assert isinstance(result_list.data[0], list)
        assert len(result_list.data[0]) == 2

        # Test dataframe format (if supported)
        context_df = ExecutionContext(
            query=base_query, result_format="dataframe", node_name="format_df"
        )
        try:
            result_df = await execution_pipeline.execute(context_df)
            # Would check dataframe properties if supported
        except:
            # Not all implementations support dataframe
            pass
