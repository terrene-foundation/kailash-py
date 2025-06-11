"""Integration tests for async database infrastructure."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from kailash.nodes.data import (
    AsyncSQLDatabaseNode,
    AsyncPostgreSQLVectorNode,
    AsyncConnectionManager,
    get_connection_manager
)
from kailash.access_control import UserContext, PermissionRule, NodePermission, PermissionEffect
from kailash.access_control_enhanced import EnhancedAccessControlManager
from kailash.access_control_abac import (
    AttributeCondition,
    AttributeOperator,
    AttributeMaskingRule
)
from kailash.utils.migrations import Migration, MigrationRunner, MigrationGenerator
from kailash.workflow import Workflow
from kailash.runtime.async_local import AsyncLocalRuntime


class TestAsyncDatabaseIntegration:
    """Test async database components integration."""
    
    @pytest.fixture
    def db_config(self):
        """Database configuration for tests."""
        return {
            "type": "postgresql",
            "host": "localhost",
            "port": 5432,
            "database": "test_db",
            "user": "test_user",
            "password": "test_pass"
        }
    
    @pytest.fixture
    def connection_manager(self):
        """Get connection manager instance."""
        # Reset singleton for tests
        AsyncConnectionManager._instance = None
        return get_connection_manager()
    
    @pytest.mark.asyncio
    async def test_async_sql_with_connection_pooling(self, db_config):
        """Test AsyncSQLDatabaseNode with connection pooling."""
        # Create node
        node = AsyncSQLDatabaseNode(
            name="test_query",
            connection_string="postgresql://test@localhost/db",
            query="SELECT * FROM users WHERE active = :active",
            params={"active": True},
            pool_size=5,
            max_pool_size=10
        )
        
        # Mock connection manager
        with patch('kailash.nodes.data.async_sql.get_connection_manager') as mock_get_cm:
            mock_cm = AsyncMock()
            mock_get_cm.return_value = mock_cm
            
            # Mock connection context
            mock_conn = AsyncMock()
            mock_conn.fetch = AsyncMock(return_value=[
                {"id": 1, "name": "User 1"},
                {"id": 2, "name": "User 2"}
            ])
            
            mock_cm.get_connection.return_value.__aenter__ = AsyncMock(
                return_value=mock_conn
            )
            mock_cm.get_connection.return_value.__aexit__ = AsyncMock()
            
            # Execute node
            result = await node.async_run()
            
            # Verify connection manager was used
            mock_cm.get_connection.assert_called_once()
            call_args = mock_cm.get_connection.call_args
            assert call_args[0][0] == "default"  # tenant_id
            assert call_args[0][1]["type"] == "postgresql"
    
    @pytest.mark.asyncio
    async def test_vector_node_operations(self):
        """Test AsyncPostgreSQLVectorNode operations."""
        # Create table operation
        create_node = AsyncPostgreSQLVectorNode(
            name="create_vector_table",
            connection_string="postgresql://localhost/vectordb",
            table_name="embeddings",
            dimension=384,
            operation="create_table"
        )
        
        # Mock connection
        with patch.object(create_node._connection_manager, 'get_connection') as mock_get_conn:
            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock()
            
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock()
            
            result = await create_node.async_run()
            
            assert result["result"]["status"] == "success"
            assert result["result"]["table"] == "embeddings"
            
            # Verify extension and table creation
            assert mock_conn.execute.call_count >= 1
            calls = [call[0][0] for call in mock_conn.execute.call_args_list]
            assert any("CREATE EXTENSION IF NOT EXISTS vector" in call for call in calls)
            assert any("CREATE TABLE IF NOT EXISTS embeddings" in call for call in calls)
    
    @pytest.mark.asyncio
    async def test_vector_similarity_search(self):
        """Test vector similarity search."""
        search_node = AsyncPostgreSQLVectorNode(
            name="search_similar",
            connection_string="postgresql://localhost/vectordb",
            table_name="embeddings",
            operation="search",
            vector=[0.1, 0.2, 0.3],
            distance_metric="cosine",
            limit=5
        )
        
        with patch.object(search_node._connection_manager, 'get_connection') as mock_get_conn:
            mock_conn = AsyncMock()
            
            # Mock search results
            mock_conn.fetch = AsyncMock(return_value=[
                {"id": 1, "vector": [0.1, 0.2, 0.3], "distance": 0.01, "metadata": {"doc": "A"}},
                {"id": 2, "vector": [0.15, 0.25, 0.35], "distance": 0.05, "metadata": {"doc": "B"}}
            ])
            
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock()
            
            result = await search_node.async_run()
            
            assert result["result"]["count"] == 2
            assert result["result"]["distance_metric"] == "cosine"
            assert len(result["result"]["matches"]) == 2
            assert result["result"]["matches"][0]["distance"] == 0.01
    
    @pytest.mark.asyncio
    async def test_connection_manager_pooling(self, connection_manager, db_config):
        """Test connection manager pool management."""
        tenant_id = "test_tenant"
        
        # Mock asyncpg
        with patch('kailash.nodes.data.async_connection.asyncpg') as mock_asyncpg:
            mock_pool = AsyncMock()
            mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
            
            # Get pool multiple times
            pool1 = await connection_manager.get_pool(tenant_id, db_config)
            pool2 = await connection_manager.get_pool(tenant_id, db_config)
            
            # Should reuse same pool
            assert pool1 is pool2
            assert mock_asyncpg.create_pool.call_count == 1
            
            # Check metrics
            metrics = connection_manager.get_metrics(tenant_id)
            assert len(metrics) == 1
    
    @pytest.mark.asyncio
    async def test_abac_with_async_nodes(self):
        """Test ABAC integration with async database nodes."""
        # Create access control manager
        acm = EnhancedAccessControlManager()
        
        # Add ABAC rule for database access
        acm.add_rule(PermissionRule(
            id="db_dept_access",
            resource_type="node",
            resource_id="user_data_query",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            conditions={
                "type": "attribute_expression",
                "value": {
                    "attribute_path": "user.attributes.department",
                    "operator": "equals",
                    "value": "finance"
                }
            }
        ))
        
        # Add masking rule
        acm.add_masking_rule(
            "user_data_query",
            AttributeMaskingRule(
                field_path="salary",
                mask_type="redact",
                condition=AttributeCondition(
                    attribute_path="user.attributes.level",
                    operator=AttributeOperator.LESS_THAN,
                    value="manager"
                )
            )
        )
        
        # Create users
        finance_manager = UserContext(
            user_id="fm001",
            tenant_id="corp",
            email="finance.mgr@corp.com",
            attributes={"department": "finance", "level": "manager"}
        )
        
        finance_analyst = UserContext(
            user_id="fa001",
            tenant_id="corp",
            email="finance.analyst@corp.com",
            attributes={"department": "finance", "level": "analyst"}
        )
        
        # Check access
        mgr_decision = acm.check_node_access(
            finance_manager, "user_data_query", NodePermission.EXECUTE
        )
        assert mgr_decision.allowed
        
        analyst_decision = acm.check_node_access(
            finance_analyst, "user_data_query", NodePermission.EXECUTE
        )
        assert analyst_decision.allowed
        
        # Test masking
        test_data = {
            "employee_id": "EMP123",
            "name": "John Doe",
            "salary": 95000,
            "department": "finance"
        }
        
        # Manager sees full data
        mgr_masked = acm.apply_data_masking(
            finance_manager, "user_data_query", test_data
        )
        assert mgr_masked["salary"] == 95000
        
        # Analyst sees redacted salary
        analyst_masked = acm.apply_data_masking(
            finance_analyst, "user_data_query", test_data
        )
        assert analyst_masked["salary"] == "[REDACTED]"
    
    @pytest.mark.asyncio
    async def test_migration_framework(self, db_config):
        """Test migration framework functionality."""
        # Create test migration
        class TestMigration(Migration):
            id = "test_001"
            description = "Test migration"
            dependencies = []
            
            async def forward(self, conn):
                await conn.execute("CREATE TABLE test_table (id INT)")
            
            async def backward(self, conn):
                await conn.execute("DROP TABLE test_table")
        
        # Create runner
        runner = MigrationRunner(db_config, migration_table="test_migrations")
        
        # Mock connection manager
        with patch.object(runner.connection_manager, 'get_connection') as mock_get_conn:
            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock()
            mock_conn.fetch = AsyncMock(return_value=[])
            
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock()
            
            # Initialize runner
            await runner.initialize()
            
            # Register migration
            runner.register_migration(TestMigration)
            
            # Create plan
            plan = await runner.create_plan()
            assert len(plan.migrations_to_apply) == 1
            assert plan.migrations_to_apply[0].id == "test_001"
            
            # Execute plan
            history = await runner.execute_plan(plan, dry_run=True)
            assert len(history) == 1
            assert history[0].migration_id == "test_001"
    
    @pytest.mark.asyncio
    async def test_workflow_with_async_nodes(self):
        """Test workflow execution with async database nodes."""
        # Create workflow
        workflow = Workflow(name="async_db_workflow")
        
        # Add async nodes
        workflow.add_node("fetch_users", AsyncSQLDatabaseNode(
            connection_string="postgresql://localhost/db",
            query="SELECT id, name FROM users WHERE active = true"
        ))
        
        workflow.add_node("fetch_embeddings", AsyncPostgreSQLVectorNode(
            connection_string="postgresql://localhost/vectordb",
            table_name="user_embeddings",
            operation="search",
            vector=[0.5] * 384,
            limit=10
        ))
        
        # Mock node execution
        with patch.object(AsyncSQLDatabaseNode, 'async_run') as mock_sql_run:
            with patch.object(AsyncPostgreSQLVectorNode, 'async_run') as mock_vector_run:
                mock_sql_run.return_value = {
                    "result": {
                        "data": [{"id": 1, "name": "User 1"}],
                        "row_count": 1
                    }
                }
                
                mock_vector_run.return_value = {
                    "result": {
                        "matches": [{"id": 1, "distance": 0.1}],
                        "count": 1
                    }
                }
                
                # Execute workflow
                runtime = AsyncLocalRuntime()
                results = await runtime.execute_workflow(workflow)
                
                assert "fetch_users" in results
                assert "fetch_embeddings" in results
                assert results["fetch_users"]["result"]["row_count"] == 1
                assert results["fetch_embeddings"]["result"]["count"] == 1