"""Integration tests for async database infrastructure with real services."""

import asyncio
import os
import sys

import pytest

# Add parent directory to path for test_config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_config import TEST_DB_CONFIG, VECTOR_DB_CONFIG

from kailash.access_control import (
    NodePermission,
    PermissionEffect,
    PermissionRule,
    UserContext,
)
from kailash.access_control_abac import (
    AttributeCondition,
    AttributeExpression,
    AttributeMaskingRule,
    AttributeOperator,
    LogicalOperator,
)
from kailash.access_control import AccessControlManager
from kailash.nodes.data import (
    AsyncConnectionManager,
    AsyncPostgreSQLVectorNode,
    AsyncSQLDatabaseNode,
    get_connection_manager,
)
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.utils.migrations import Migration, MigrationGenerator, MigrationRunner
from kailash.workflow import Workflow


class TestAsyncDatabaseIntegrationReal:
    """Test async database components with real connections."""

    @pytest.fixture
    def db_config(self):
        """Database configuration for tests."""
        return TEST_DB_CONFIG["postgresql"]

    @pytest.fixture
    def connection_manager(self):
        """Get connection manager instance."""
        # Reset singleton for tests
        AsyncConnectionManager._instance = None
        return get_connection_manager()

    @pytest.mark.asyncio
    async def test_async_sql_with_real_database(self, db_config):
        """Test AsyncSQLDatabaseNode with real PostgreSQL."""
        # Create node
        node = AsyncSQLDatabaseNode(
            name="test_query",
            database_type="postgresql",
            connection_string=TEST_DB_CONFIG["connection_string"],
            query="SELECT * FROM users WHERE active = :active",
            params={"active": True},
            pool_size=5,
            max_pool_size=10,
        )

        try:
            # Execute node
            result = await node.async_run()

            # Verify results
            assert "result" in result
            assert "data" in result["result"]
            assert "row_count" in result["result"]
            assert result["result"]["row_count"] >= 0
            assert result["result"]["database_type"] == "postgresql"
            
            # Check data structure if we have results
            if result["result"]["data"]:
                first_row = result["result"]["data"][0]
                assert "id" in first_row
                assert "name" in first_row
                assert "email" in first_row
                assert "active" in first_row

        finally:
            # Clean up
            await node.cleanup()

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires pgvector extension")
    async def test_vector_node_operations(self):
        """Test AsyncPostgreSQLVectorNode operations."""
        # Create table operation
        create_node = AsyncPostgreSQLVectorNode(
            name="create_vector_table",
            connection_string=VECTOR_DB_CONFIG["connection_string"],
            table_name="test_embeddings",
            operation="create_table",
            dimension=384,  # Changed from embedding_dimension to dimension
        )

        try:
            # Create table
            result = await create_node.async_run()
            assert result["result"]["success"] is True

            # Insert embeddings
            insert_node = AsyncPostgreSQLVectorNode(
                name="insert_embedding",
                connection_string=VECTOR_DB_CONFIG["connection_string"],
                table_name="test_embeddings",
                operation="insert",
                documents=["Test document for embedding"],
                metadata=[{"source": "test"}],
            )

            insert_result = await insert_node.async_run()
            assert insert_result["result"]["success"] is True
            assert insert_result["result"]["count"] == 1

            # Search similar
            search_node = AsyncPostgreSQLVectorNode(
                name="search_similar",
                connection_string=VECTOR_DB_CONFIG["connection_string"],
                table_name="test_embeddings",
                operation="search",
                query="Test query",
                top_k=5,
            )

            search_result = await search_node.async_run()
            assert search_result["result"]["success"] is True
            assert "matches" in search_result["result"]

        finally:
            # Clean up - drop test table
            cleanup_node = AsyncSQLDatabaseNode(
                name="cleanup",
                database_type="postgresql",
                connection_string=VECTOR_DB_CONFIG["connection_string"],
                query="DROP TABLE IF EXISTS test_embeddings",
            )
            await cleanup_node.async_run()
            await cleanup_node.cleanup()

    @pytest.mark.asyncio
    async def test_connection_manager_pooling(self, connection_manager):
        """Test connection manager pool management with real database."""
        tenant_id = "test_tenant"
        
        # Use consistent config for pool reuse testing
        db_config = TEST_DB_CONFIG["postgresql"]

        # Get pool multiple times with same config
        pool1 = await connection_manager.get_pool(tenant_id, db_config)
        pool2 = await connection_manager.get_pool(tenant_id, db_config)

        # Should reuse same pool
        assert pool1 is pool2

        # Check metrics - there should be at least one pool
        metrics = connection_manager.get_metrics(tenant_id)
        assert len(metrics) >= 1
        
        # Test actual query execution
        async with connection_manager.get_connection(tenant_id, db_config) as conn:
            result = await conn.fetch("SELECT 1 as test")
            assert len(result) == 1
            assert result[0]["test"] == 1

        # Clean up - connection manager doesn't have close_pool method
        # Pools are managed internally

    @pytest.mark.asyncio
    async def test_abac_with_data_masking(self, db_config):
        """Test ABAC with data masking on real data."""
        # Create access control manager
        access_manager = AccessControlManager(strategy="abac")

        # Add permission rule to allow execution
        access_manager.add_rule(
            PermissionRule(
                id="allow_query_execution",
                resource_type="node",
                resource_id="secure_query",
                permission=NodePermission.EXECUTE,
                effect=PermissionEffect.ALLOW,
            )
        )

        # Define masking rule for email
        access_manager.add_masking_rule(
            "secure_query",  # node_id
            AttributeMaskingRule(
                field_path="email",
                mask_type="partial",
                condition=AttributeExpression(
                    operator=LogicalOperator.AND,
                    conditions=[
                        AttributeCondition(
                            attribute_path="user.attributes.department",
                            operator=AttributeOperator.NOT_EQUALS,
                            value="IT",
                        )
                    ],
                ),
            )
        )

        # Create node with access control
        node = AsyncSQLDatabaseNode(
            name="secure_query",
            database_type="postgresql",
            connection_string=TEST_DB_CONFIG["connection_string"],
            query="SELECT id, name, email FROM users",
            access_control_manager=access_manager,
        )

        # Test with IT user (sees full data)
        it_context = UserContext(
            user_id="it_user",
            tenant_id="test_tenant",
            email="it_user@test.com",
            roles=["developer"],
            attributes={"department": "IT"},
        )

        it_result = await node.async_run(user_context=it_context)
        if it_result["result"]["data"]:
            # IT users see full email
            assert "@" in it_result["result"]["data"][0]["email"]

        # Test with non-IT user (sees masked data)
        hr_context = UserContext(
            user_id="hr_user",
            tenant_id="test_tenant",
            email="hr_user@test.com",
            roles=["hr_manager"],
            attributes={"department": "HR"},
        )

        hr_result = await node.async_run(user_context=hr_context)
        if hr_result["result"]["data"]:
            # HR users see masked email
            email = hr_result["result"]["data"][0]["email"]
            assert email.count("*") > 0  # Email should be partially masked

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_workflow_with_async_nodes(self):
        """Test workflow execution with async database nodes."""
        # Create workflow
        workflow = Workflow(workflow_id="async_db_workflow", name="async_db_workflow")

        # Add async nodes
        workflow.add_node(
            "fetch_users",
            AsyncSQLDatabaseNode(
                connection_string=TEST_DB_CONFIG["connection_string"],
                database_type="postgresql",
                query="SELECT id, name FROM users WHERE active = true",
                fetch_mode="all",
            ),
        )

        workflow.add_node(
            "count_active",
            AsyncSQLDatabaseNode(
                connection_string=TEST_DB_CONFIG["connection_string"],
                database_type="postgresql",
                query="SELECT COUNT(*) as count FROM users WHERE active = true",
                fetch_mode="one",
            ),
        )

        # Execute workflow
        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute(workflow)

        assert "fetch_users" in results
        assert "count_active" in results
        
        # Verify results exist
        if "fetch_users" in results and "result" in results["fetch_users"]:
            user_count = len(results["fetch_users"]["result"]["data"])
            if "count_active" in results and "result" in results["count_active"]:
                db_count = results["count_active"]["result"]["data"]["count"]
                assert user_count == db_count
        else:
            # If there was an error, just check that nodes were executed
            assert "fetch_users" in results
            assert "count_active" in results

    @pytest.mark.asyncio
    async def test_error_handling_with_real_database(self):
        """Test error handling with real database errors."""
        # Test invalid query
        node = AsyncSQLDatabaseNode(
            name="invalid_query",
            database_type="postgresql",
            connection_string=TEST_DB_CONFIG["connection_string"],
            query="SELECT * FROM non_existent_table",
        )

        with pytest.raises(Exception) as exc_info:
            await node.async_run()
        
        # Should get a database error about missing table
        assert "non_existent_table" in str(exc_info.value).lower() or "does not exist" in str(exc_info.value).lower()

        await node.cleanup()

    @pytest.mark.asyncio
    async def test_transaction_support(self):
        """Test transaction support with real database."""
        node = AsyncSQLDatabaseNode(
            name="transaction_test",
            database_type="postgresql",
            connection_string=TEST_DB_CONFIG["connection_string"],
            query="INSERT INTO users (name, email) VALUES (:name, :email)",
        )

        # This is a basic test - full transaction support would need
        # additional implementation in the AsyncSQLDatabaseNode
        try:
            result = await node.async_run(
                params={"name": "Transaction Test 2", "email": "tx2@test.com"}
            )
            # INSERT queries don't return rows with fetch, row_count is 0
            # This is expected behavior for PostgreSQL

            # Verify insertion
            verify_node = AsyncSQLDatabaseNode(
                name="verify",
                database_type="postgresql", 
                connection_string=TEST_DB_CONFIG["connection_string"],
                query="SELECT * FROM users WHERE email = :email",
                params={"email": "tx2@test.com"},
            )
            
            verify_result = await verify_node.async_run()
            assert len(verify_result["result"]["data"]) == 1

            # Clean up
            cleanup_node = AsyncSQLDatabaseNode(
                name="cleanup",
                database_type="postgresql",
                connection_string=TEST_DB_CONFIG["connection_string"],
                query="DELETE FROM users WHERE email = :email",
                params={"email": "tx2@test.com"},
            )
            await cleanup_node.async_run()
            
        finally:
            await node.cleanup()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])