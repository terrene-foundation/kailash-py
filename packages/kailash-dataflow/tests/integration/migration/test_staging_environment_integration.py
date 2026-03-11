#!/usr/bin/env python3
"""
Integration Tests for Safe Staging Environment - TODO-141 TDD Implementation

Tests the staging environment system with real database scenarios integrating with:
- Real PostgreSQL database instances via Docker test environment
- TODO-137: DependencyAnalyzer for dependency analysis
- TODO-138: ForeignKeyAnalyzer for FK analysis
- TODO-140: RiskAssessmentEngine for risk assessment integration
- Complete staging environment lifecycle management

TIER 2 REQUIREMENTS:
- Use real Docker services from tests/utils
- Run ./tests/utils/test-env up && ./tests/utils/test-env status before tests
- NO MOCKING - test actual component interactions
- Test database connections, schema replication, data sampling
- Validate staging environment lifecycle management
- Test integration with existing migration components
- Location: tests/integration/migration/
- Timeout: <5 seconds per test
"""

import asyncio
import time
from datetime import datetime
from typing import Dict, List

import asyncpg
import pytest
from dataflow.migrations.dependency_analyzer import (
    DependencyAnalyzer,
    DependencyReport,
    DependencyType,
    ForeignKeyDependency,
    ImpactLevel,
)
from dataflow.migrations.foreign_key_analyzer import (
    FKImpactLevel,
    FKImpactReport,
    ForeignKeyAnalyzer,
)
from dataflow.migrations.risk_assessment_engine import (
    RiskAssessmentEngine,
    RiskCategory,
    RiskLevel,
    RiskScore,
)
from dataflow.migrations.staging_environment_manager import (
    DataSamplingResult,
    ProductionDatabase,
    SchemaReplicationResult,
    StagingDatabase,
    StagingEnvironment,
    StagingEnvironmentConfig,
    StagingEnvironmentInfo,
    StagingEnvironmentManager,
    StagingEnvironmentStatus,
)

from kailash.runtime.local import LocalRuntime
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    return LocalRuntime()


class TestStagingEnvironmentManagerIntegration:
    """Integration tests for StagingEnvironmentManager with real PostgreSQL."""

    @pytest.fixture
    def manager_config(self, test_suite):
        """Create staging environment manager configuration."""
        # Production database (using test database as production)
        prod_db_config = ProductionDatabase(
            host=test_suite.config.host,
            port=test_suite.config.port,
            database=test_suite.config.database,
            user=test_suite.config.user,
            password=test_suite.config.password,
            schema_name="public",
        )

        # Staging database configuration (separate database)
        staging_db_config = StagingDatabase(
            host=test_suite.config.host,
            port=test_suite.config.port,
            database=f"{test_suite.config.database}_staging",
            user=test_suite.config.user,
            password=test_suite.config.password,
            schema_name="public",
        )

        # Initialize staging environment manager
        config = StagingEnvironmentConfig(
            default_data_sample_size=0.1,
            max_staging_environments=3,
            cleanup_timeout_seconds=60,
            schema_replication_timeout=120,
        )
        manager = StagingEnvironmentManager(config)

        return {
            "prod_db_config": prod_db_config,
            "staging_db_config": staging_db_config,
            "config": config,
            "manager": manager,
        }

    def setup_method(self):
        """Setup for each test method."""
        self.test_start_time = time.time()

    def teardown_method(self):
        """Cleanup after each test method."""
        test_duration = time.time() - self.test_start_time
        assert (
            test_duration < 5.0
        ), f"Test exceeded 5 second timeout: {test_duration:.2f}s"

    @pytest.mark.asyncio
    async def test_production_database_connection_validation(
        self, manager_config, test_suite
    ):
        """Test connection validation to production database."""
        manager = manager_config["manager"]
        prod_db_config = manager_config["prod_db_config"]

        # Test successful connection
        await manager._validate_production_connection(prod_db_config)

        # Test failed connection with invalid credentials
        invalid_db_config = ProductionDatabase(
            host="localhost",
            port=5433,
            database="nonexistent_db",
            user="invalid_user",
            password="invalid_password",
        )

        with pytest.raises(ConnectionError):
            await manager._validate_production_connection(invalid_db_config)

    @pytest.mark.asyncio
    async def test_staging_environment_creation_real_db(
        self, manager_config, test_suite
    ):
        """Test staging environment creation with real database operations."""
        manager = manager_config["manager"]
        prod_db_config = manager_config["prod_db_config"]

        try:
            # Create staging environment
            staging_env = await manager.create_staging_environment(
                production_db=prod_db_config,
                data_sample_size=0.05,  # 5% sample for faster testing
            )

            # Verify environment creation
            assert staging_env.staging_id.startswith("staging_")
            assert staging_env.status == StagingEnvironmentStatus.ACTIVE
            assert staging_env.data_sample_size == 0.05
            assert staging_env.production_db == prod_db_config

            # Verify environment is tracked
            assert staging_env.staging_id in manager.active_environments

            # Get environment info
            env_info = await manager.get_staging_environment_info(
                staging_env.staging_id
            )
            assert isinstance(env_info, StagingEnvironmentInfo)
            assert env_info.staging_environment.staging_id == staging_env.staging_id

        finally:
            # Cleanup staging environment
            if (
                staging_env
                and staging_env.staging_id in self.manager.active_environments
            ):
                await self.manager.cleanup_staging_environment(staging_env.staging_id)

    @pytest.mark.asyncio
    async def test_staging_database_setup_and_cleanup(self):
        """Test staging database setup and cleanup operations."""
        staging_env = None
        try:
            # Create staging environment
            staging_env = await self.manager.create_staging_environment(
                production_db=self.prod_db_config,
                data_sample_size=0.01,  # 1% sample for minimal data
            )

            # Verify staging database exists conceptually
            # (Note: In real implementation, this would create actual database)
            assert staging_env.status == StagingEnvironmentStatus.ACTIVE

            # Test cleanup
            cleanup_result = await self.manager.cleanup_staging_environment(
                staging_env.staging_id
            )

            # Verify cleanup results
            assert cleanup_result["cleanup_status"] == "SUCCESS"
            assert cleanup_result["resources_freed"] is True
            assert cleanup_result["database_dropped"] is True
            assert cleanup_result["cleanup_time_seconds"] >= 0

            # Verify environment is removed from tracking
            assert staging_env.staging_id not in self.manager.active_environments

        except Exception as e:
            # Ensure cleanup happens even on failure
            if (
                staging_env
                and staging_env.staging_id in self.manager.active_environments
            ):
                await self.manager.cleanup_staging_environment(staging_env.staging_id)
            raise

    @pytest.mark.asyncio
    async def test_multiple_staging_environments_management(self):
        """Test managing multiple staging environments simultaneously."""
        environments = []
        try:
            # Create multiple staging environments
            for i in range(3):
                env = await self.manager.create_staging_environment(
                    production_db=self.prod_db_config, data_sample_size=0.01
                )
                environments.append(env)
                assert env.status == StagingEnvironmentStatus.ACTIVE

            # Verify all environments are tracked
            assert len(self.manager.active_environments) >= 3

            # Test hitting the limit
            with pytest.raises(
                RuntimeError, match="Maximum staging environments exceeded"
            ):
                await self.manager.create_staging_environment(
                    production_db=self.prod_db_config
                )

            # Cleanup one environment
            first_env = environments[0]
            await self.manager.cleanup_staging_environment(first_env.staging_id)
            assert first_env.staging_id not in self.manager.active_environments

            # Verify we can create another one now
            new_env = await self.manager.create_staging_environment(
                production_db=self.prod_db_config, data_sample_size=0.01
            )
            environments[0] = new_env  # Replace cleaned up env

        finally:
            # Cleanup all environments
            for env in environments:
                if env and env.staging_id in self.manager.active_environments:
                    await self.manager.cleanup_staging_environment(env.staging_id)

    @pytest.mark.asyncio
    async def test_staging_environment_error_handling(self):
        """Test error handling and recovery in staging environment operations."""
        # Test invalid sample size
        with pytest.raises(
            ValueError, match="Data sample size must be between 0.0 and 1.0"
        ):
            await self.manager.create_staging_environment(
                production_db=self.prod_db_config,
                data_sample_size=1.5,  # Invalid size > 1.0
            )

        with pytest.raises(
            ValueError, match="Data sample size must be between 0.0 and 1.0"
        ):
            await self.manager.create_staging_environment(
                production_db=self.prod_db_config,
                data_sample_size=-0.1,  # Invalid size < 0.0
            )

        # Test cleanup of non-existent environment
        with pytest.raises(ValueError, match="Staging environment not found"):
            await self.manager.cleanup_staging_environment("nonexistent_staging_id")

        # Test getting info for non-existent environment
        with pytest.raises(ValueError, match="Staging environment not found"):
            await self.manager.get_staging_environment_info("nonexistent_staging_id")


class TestStagingEnvironmentProductionSchemaIntegration:
    """Integration tests for production schema operations with real database setup."""

    @classmethod
    def setup_class(cls):
        """Setup test class with production-like schema."""
        cls.prod_db_config = ProductionDatabase(
            host="localhost",
            port=5435,  # Correct port for dataflow_test_postgres container
            database="dataflow_test",
            user="dataflow_test",
            password="dataflow_test_password",
        )

        cls.config = StagingEnvironmentConfig(cleanup_timeout_seconds=60)
        cls.manager = StagingEnvironmentManager(cls.config)

    @pytest.mark.asyncio
    async def test_production_schema_inspection(self):
        """Test production schema inspection capabilities."""
        # This would be a real test with actual production schema inspection
        staging_env = None
        try:
            # Create a basic staging environment for testing
            staging_env = await self.manager.create_staging_environment(
                production_db=self.prod_db_config, data_sample_size=0.01
            )

            # Test schema inspection methods (these are currently mocked in implementation)
            conn_pool = await self.manager._get_connection_pool(self.prod_db_config)

            async with conn_pool.acquire() as conn:
                # Test getting production tables
                tables = await self.manager._get_production_tables(conn, None)
                assert isinstance(tables, list)

                # Test getting production constraints
                constraints = await self.manager._get_production_constraints(conn, None)
                assert isinstance(constraints, list)

                # Test getting production indexes
                indexes = await self.manager._get_production_indexes(conn, None)
                assert isinstance(indexes, list)

        finally:
            if staging_env:
                await self.manager.cleanup_staging_environment(staging_env.staging_id)

    @pytest.mark.asyncio
    async def test_schema_replication_simulation(self):
        """Test schema replication workflow simulation."""
        staging_env = None
        try:
            # Create staging environment
            staging_env = await self.manager.create_staging_environment(
                production_db=self.prod_db_config, data_sample_size=0.01
            )

            # Test schema replication (currently simulated)
            replication_result = await self.manager.replicate_production_schema(
                staging_id=staging_env.staging_id, include_data=True
            )

            # Verify replication result structure
            assert isinstance(replication_result, SchemaReplicationResult)
            assert replication_result.tables_replicated >= 0
            assert replication_result.replication_time_seconds >= 0
            assert replication_result.data_sampling_completed is True

        finally:
            if staging_env:
                await self.manager.cleanup_staging_environment(staging_env.staging_id)

    @pytest.mark.asyncio
    async def test_data_sampling_simulation(self):
        """Test data sampling workflow simulation."""
        staging_env = None
        try:
            # Create staging environment
            staging_env = await self.manager.create_staging_environment(
                production_db=self.prod_db_config, data_sample_size=0.05
            )

            # Test data sampling for specific table
            sampling_result = await self.manager.sample_production_data(
                staging_id=staging_env.staging_id,
                table_name="test_table",
                sample_size=0.1,
            )

            # Verify sampling result structure
            assert isinstance(sampling_result, DataSamplingResult)
            assert sampling_result.table_name == "test_table"
            assert sampling_result.sample_percentage == 10.0
            assert sampling_result.sampling_time_seconds >= 0
            assert sampling_result.constraints_preserved is True

        finally:
            if staging_env:
                await self.manager.cleanup_staging_environment(staging_env.staging_id)


class TestStagingEnvironmentIntegrationWithMigrationComponents:
    """Integration tests with existing migration system components."""

    @classmethod
    def setup_class(cls):
        """Setup integration test environment."""
        cls.prod_db_config = ProductionDatabase(
            host="localhost",
            port=5435,  # Correct port for dataflow_test_postgres container
            database="dataflow_test",
            user="dataflow_test",
            password="dataflow_test_password",
        )

        cls.config = StagingEnvironmentConfig()
        cls.manager = StagingEnvironmentManager(cls.config)

        # Initialize migration components for integration testing
        cls.dependency_analyzer = DependencyAnalyzer()
        cls.foreign_key_analyzer = ForeignKeyAnalyzer()
        cls.risk_engine = RiskAssessmentEngine()

    @pytest.mark.asyncio
    async def test_integration_with_dependency_analyzer(self):
        """Test integration between staging environment and dependency analyzer."""
        staging_env = None
        try:
            # Create staging environment
            staging_env = await self.manager.create_staging_environment(
                production_db=self.prod_db_config, data_sample_size=0.01
            )

            # Verify dependency analyzer can be used with staging environment
            assert self.manager.dependency_analyzer is not None
            assert isinstance(self.manager.dependency_analyzer, DependencyAnalyzer)

            # Test that staging environment info includes dependency context
            env_info = await self.manager.get_staging_environment_info(
                staging_env.staging_id
            )
            assert (
                env_info.staging_environment.status == StagingEnvironmentStatus.ACTIVE
            )

        finally:
            if staging_env:
                await self.manager.cleanup_staging_environment(staging_env.staging_id)

    @pytest.mark.asyncio
    async def test_integration_with_foreign_key_analyzer(self):
        """Test integration between staging environment and foreign key analyzer."""
        staging_env = None
        try:
            # Create staging environment
            staging_env = await self.manager.create_staging_environment(
                production_db=self.prod_db_config, data_sample_size=0.01
            )

            # Verify foreign key analyzer integration
            assert self.manager.foreign_key_analyzer is not None
            assert isinstance(self.manager.foreign_key_analyzer, ForeignKeyAnalyzer)

            # Test staging environment can provide FK analysis context
            assert staging_env.status == StagingEnvironmentStatus.ACTIVE

        finally:
            if staging_env:
                await self.manager.cleanup_staging_environment(staging_env.staging_id)

    @pytest.mark.asyncio
    async def test_integration_with_risk_assessment_engine(self):
        """Test integration between staging environment and risk assessment engine."""
        staging_env = None
        try:
            # Create staging environment
            staging_env = await self.manager.create_staging_environment(
                production_db=self.prod_db_config, data_sample_size=0.01
            )

            # Verify risk assessment engine integration
            assert self.manager.risk_engine is not None
            assert isinstance(self.manager.risk_engine, RiskAssessmentEngine)

            # Test that staging validation can reduce risk scores
            # (This integration will be completed in Phase 2 with MigrationValidationPipeline)
            env_info = await self.manager.get_staging_environment_info(
                staging_env.staging_id
            )
            assert env_info.staging_environment.data_sample_size == 0.01

        finally:
            if staging_env:
                await self.manager.cleanup_staging_environment(staging_env.staging_id)


class TestStagingEnvironmentPerformanceValidation:
    """Performance validation tests for staging environment operations."""

    @classmethod
    def setup_class(cls):
        """Setup performance test environment."""
        cls.prod_db_config = ProductionDatabase(
            host="localhost",
            port=5435,  # Correct port for dataflow_test_postgres container
            database="dataflow_test",
            user="dataflow_test",
            password="dataflow_test_password",
        )

        cls.config = StagingEnvironmentConfig()
        cls.manager = StagingEnvironmentManager(cls.config)

    @pytest.mark.asyncio
    async def test_staging_environment_creation_performance(self):
        """Test staging environment creation performance under 5 seconds."""
        start_time = time.time()
        staging_env = None

        try:
            # Create staging environment
            staging_env = await self.manager.create_staging_environment(
                production_db=self.prod_db_config, data_sample_size=0.01
            )

            creation_time = time.time() - start_time

            # Verify creation completed within performance bounds
            assert (
                creation_time < 5.0
            ), f"Staging environment creation took {creation_time:.2f}s (exceeds 5s limit)"
            assert staging_env.status == StagingEnvironmentStatus.ACTIVE

        finally:
            if staging_env:
                cleanup_start = time.time()
                await self.manager.cleanup_staging_environment(staging_env.staging_id)
                cleanup_time = time.time() - cleanup_start
                assert (
                    cleanup_time < 2.0
                ), f"Cleanup took {cleanup_time:.2f}s (exceeds 2s limit)"

    @pytest.mark.asyncio
    async def test_concurrent_staging_environment_operations(self):
        """Test concurrent staging environment operations."""
        environments = []
        start_time = time.time()

        try:
            # Create multiple environments concurrently
            tasks = []
            for i in range(2):  # Limited to 2 for performance
                task = asyncio.create_task(
                    self.manager.create_staging_environment(
                        production_db=self.prod_db_config,
                        data_sample_size=0.005,  # Very small sample for performance
                    )
                )
                tasks.append(task)

            # Wait for all environments to be created
            environments = await asyncio.gather(*tasks)
            creation_time = time.time() - start_time

            # Verify concurrent creation performance
            assert (
                creation_time < 8.0
            ), f"Concurrent creation took {creation_time:.2f}s (exceeds 8s limit)"
            assert len(environments) == 2

            # Verify all environments are active
            for env in environments:
                assert env.status == StagingEnvironmentStatus.ACTIVE
                assert env.staging_id in self.manager.active_environments

        finally:
            # Cleanup all environments
            for env in environments:
                if env and env.staging_id in self.manager.active_environments:
                    await self.manager.cleanup_staging_environment(env.staging_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
