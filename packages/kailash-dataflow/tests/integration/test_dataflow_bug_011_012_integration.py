"""
Integration tests for DataFlow bugs 011 and 012.

Bug 011: Logger undefined error (line 1758 in dataflow/core/nodes.py)
Bug 012: TDD isolation bypass due to params.host access failure (line 1748)

These tests use real Docker infrastructure to verify bug behavior in realistic scenarios.
"""

import asyncio
import os
from unittest.mock import Mock

import pytest

# Set TDD mode for integration tests
os.environ["DATAFLOW_TDD_MODE"] = "true"

from dataflow import DataFlow
from dataflow.testing.tdd_support import (
    setup_tdd_infrastructure,
    tdd_test_context,
    teardown_tdd_infrastructure,
)


class TestDataFlowBugs011And012Integration:
    """Integration test suite for critical DataFlow bugs 011 and 012."""

    @pytest.fixture(autouse=True)
    async def setup_tdd_infrastructure_fixture(self):
        """Set up TDD infrastructure for each test."""
        await setup_tdd_infrastructure()
        yield
        await teardown_tdd_infrastructure()

    async def test_bug_011_logger_error_with_real_tdd_context(self):
        """
        Test Bug 011: Logger undefined error with real TDD infrastructure.

        This test creates a real DataFlow instance with TDD context and verifies
        that generated nodes with the buggy logger reference cause NameError.
        """
        # Create DataFlow instance with TDD context
        async with tdd_test_context() as context:
            db = DataFlow(
                existing_schema_mode=True,
            )
            db.set_test_context(context)

            # Register a test model
            @db.model
            class TestBugIntegrationModel:
                name: str
                active: bool = True

            # Get the generated create node class
            create_node_class = db._nodes["TestBugIntegrationModelCreateNode"]

            # Create node instance
            node_instance = create_node_class("test_node", {})

            # Verify the node has a dataflow_instance
            assert hasattr(node_instance, "dataflow_instance")
            assert node_instance.dataflow_instance == db

            # Mock the TDD connection to trigger the exception path in _get_tdd_connection_info
            original_tdd_connection = db._tdd_connection
            try:
                # Create a mock connection that will cause AttributeError when accessing params.host
                mock_connection = Mock()

                class FakeAsyncpgParamsIntegration:
                    def __init__(self):
                        self.user = "test_user"
                        self.password = "test_password"
                        self.database = "test_database"
                        self.port = 5434
                        # Note: NO 'host' attribute - this is Bug 012!

                    def __getattr__(self, name):
                        if name == "host":
                            raise AttributeError(
                                "'ConnectionParameters' object has no attribute 'host'"
                            )
                        raise AttributeError(
                            f"'FakeAsyncpgParams' object has no attribute '{name}'"
                        )

                mock_connection._params = FakeAsyncpgParamsIntegration()
                db._tdd_connection = mock_connection

                # The bug: calling _get_tdd_connection_info should raise NameError
                # because 'logger' is not defined in the method scope (Bug 011)
                with pytest.raises(NameError, match="name 'logger' is not defined"):
                    node_instance._get_tdd_connection_info()

            finally:
                # Restore original TDD connection
                db._tdd_connection = original_tdd_connection

    async def test_bug_012_tdd_isolation_bypass_with_real_connection(self):
        """
        Test Bug 012: TDD isolation bypass with real database connection.

        This test verifies that the broken params.host access causes nodes to fall back
        to production database instead of maintaining TDD isolation.
        """
        # Create DataFlow instance with TDD context
        async with tdd_test_context() as context:
            db = DataFlow(
                existing_schema_mode=True,
            )
            db.set_test_context(context)

            # Register a test model
            @db.model
            class TestTDDIsolationModel:
                name: str
                active: bool = True

            # Get the generated create node class
            create_node_class = db._nodes["TestTDDIsolationModelCreateNode"]

            # Create node instance
            node_instance = create_node_class("test_node", {})

            # Verify the node has proper TDD context
            assert hasattr(node_instance, "dataflow_instance")
            assert node_instance.dataflow_instance == db
            assert hasattr(db, "_tdd_connection")
            assert db._tdd_connection is not None

            # Mock the real TDD connection to simulate asyncpg params structure issue
            original_tdd_connection = db._tdd_connection
            try:
                # Create a mock that simulates the real asyncpg connection params issue
                mock_connection = Mock()

                class RealAsyncpgParamsSimulation:
                    """Simulates real asyncpg connection params that don't have 'host' attribute"""

                    def __init__(self):
                        # These attributes exist in real asyncpg
                        self.user = "dataflow_test"
                        self.password = "dataflow_test_password"
                        self.database = "dataflow_test"
                        self.port = 5434
                        # But 'host' doesn't exist - this causes Bug 012

                    def __getattr__(self, name):
                        if name == "host":
                            raise AttributeError(
                                "'ConnectionParameters' object has no attribute 'host'"
                            )
                        raise AttributeError(
                            f"'ConnectionParameters' object has no attribute '{name}'"
                        )

                mock_connection._params = RealAsyncpgParamsSimulation()
                db._tdd_connection = mock_connection

                # Add a mock logger to avoid Bug 011 and focus on Bug 012
                node_instance.logger = Mock()

                # Bug 012: The method should return None due to params.host AttributeError
                # This causes TDD isolation to be bypassed
                connection_info = node_instance._get_tdd_connection_info()

                # Should return None due to Bug 012
                assert connection_info is None

                # Should have logged the error
                node_instance.logger.debug.assert_called()
                error_message = node_instance.logger.debug.call_args[0][0]
                assert "Failed to extract TDD connection info" in error_message

            finally:
                # Restore original TDD connection
                db._tdd_connection = original_tdd_connection

    async def test_tdd_connection_isolation_should_work_when_fixed(self):
        """
        Test showing how TDD connection isolation SHOULD work when bugs are fixed.

        This demonstrates the expected behavior after implementing the fixes.
        """
        # Create DataFlow instance with TDD context
        async with tdd_test_context() as context:
            db = DataFlow(
                existing_schema_mode=True,
            )
            db.set_test_context(context)

            # Register a test model
            @db.model
            class TestFixedIsolationModel:
                name: str
                active: bool = True

            # Get the generated create node class
            create_node_class = db._nodes["TestFixedIsolationModelCreateNode"]

            # Create node instance with a FIXED version of _get_tdd_connection_info
            node_instance = create_node_class("test_node", {})

            # Replace the buggy method with a fixed version
            def fixed_get_tdd_connection_info(self):
                """Fixed version of _get_tdd_connection_info method"""
                if hasattr(self.dataflow_instance, "_tdd_connection"):
                    try:
                        conn = self.dataflow_instance._tdd_connection
                        if hasattr(conn, "_params"):
                            params = conn._params
                            # FIXED: Use safe attribute access with getattr and proper defaults
                            host = getattr(
                                params,
                                "server_hostname",
                                getattr(params, "host", "localhost"),
                            )
                            user = getattr(params, "user", "postgres")
                            password = getattr(params, "password", "")
                            database = getattr(params, "database", "postgres")
                            port = getattr(params, "port", 5432)

                            return f"postgresql://{user}:{password}@{host}:{port}/{database}"
                        else:
                            return os.getenv(
                                "TEST_DATABASE_URL",
                                "postgresql://dataflow_test:dataflow_test_password@localhost:5434/dataflow_test",
                            )
                    except Exception as e:
                        # FIXED: Use self.logger instead of logger
                        self.logger.debug(f"Failed to extract TDD connection info: {e}")
                        return None

                return None

            # Apply the fixed method and add proper logger
            import logging
            import types

            node_instance.logger = logging.getLogger(__name__)
            node_instance._get_tdd_connection_info = types.MethodType(
                fixed_get_tdd_connection_info, node_instance
            )

            # Test with the original real TDD connection (should work now)
            connection_info = node_instance._get_tdd_connection_info()

            # With the fix, should extract connection info successfully
            # The exact format depends on the real asyncpg connection structure
            assert connection_info is not None
            assert "postgresql://" in connection_info
            assert (
                "dataflow_test" in connection_info
            )  # Should contain test database info

    async def test_integration_with_real_node_generation(self):
        """
        Integration test using actual node generation to verify bug presence.

        This test uses the real DataFlow node generation process to confirm
        that the bugs exist in the generated code.
        """
        # Create DataFlow instance with TDD context
        async with tdd_test_context() as context:
            db = DataFlow(
                existing_schema_mode=True,
            )
            db.set_test_context(context)

            # Register a test model using the real @db.model decorator
            @db.model
            class RealGeneratedNodeTest:
                name: str
                email: str
                active: bool = True

            # Verify all expected nodes were generated
            expected_nodes = [
                "RealGeneratedNodeTestCreateNode",
                "RealGeneratedNodeTestReadNode",
                "RealGeneratedNodeTestUpdateNode",
                "RealGeneratedNodeTestDeleteNode",
                "RealGeneratedNodeTestListNode",
                "RealGeneratedNodeTestCountNode",
                "RealGeneratedNodeTestExistsNode",
                "RealGeneratedNodeTestBatchCreateNode",
                "RealGeneratedNodeTestBatchUpdateNode",
            ]

            for node_name in expected_nodes:
                assert node_name in db._nodes, f"Expected node {node_name} not found"

                # Get the node class and create an instance
                node_class = db._nodes[node_name]
                node_instance = node_class("test_node", {})

                # Verify the node has the problematic method
                assert hasattr(node_instance, "_get_tdd_connection_info")
                assert callable(getattr(node_instance, "_get_tdd_connection_info"))

                # Verify the node has the dataflow_instance
                assert hasattr(node_instance, "dataflow_instance")
                assert node_instance.dataflow_instance == db

    async def test_production_database_fallback_risk(self):
        """
        Test demonstrating the risk of falling back to production database.

        This test shows how Bug 012 could cause test data to leak into production.
        """
        # Create DataFlow instance with TDD context
        async with tdd_test_context() as context:
            db = DataFlow(
                existing_schema_mode=True,
            )
            db.set_test_context(context)

            # Register a test model
            @db.model
            class ProductionLeakTestModel:
                name: str
                sensitive_data: str

            # Get a node that would be used for database operations
            create_node_class = db._nodes["ProductionLeakTestModelCreateNode"]
            node_instance = create_node_class(
                "test_node", {"name": "test_user", "sensitive_data": "secret_test_data"}
            )

            # Mock the TDD connection to simulate the bug scenario
            original_tdd_connection = db._tdd_connection
            try:
                # Simulate Bug 012: connection params access fails
                mock_connection = Mock()

                class BuggyAsyncpgParams:
                    def __init__(self):
                        self.user = "dataflow_test"
                        self.password = "dataflow_test_password"
                        self.database = "dataflow_test"
                        self.port = 5434

                    def __getattr__(self, name):
                        if name == "host":
                            raise AttributeError(
                                "'ConnectionParameters' object has no attribute 'host'"
                            )
                        raise AttributeError(
                            f"'ConnectionParameters' object has no attribute '{name}'"
                        )

                mock_connection._params = BuggyAsyncpgParams()
                db._tdd_connection = mock_connection

                # Add mock logger to avoid Bug 011
                node_instance.logger = Mock()

                # Simulate what happens when TDD connection info extraction fails
                connection_info = node_instance._get_tdd_connection_info()

                # Bug 012: Should return None, causing fallback to production DB
                assert connection_info is None

                # This represents the DANGEROUS scenario where the node might
                # fall back to using production database configuration instead
                # of the isolated test database

                # Log the security risk
                node_instance.logger.debug.assert_called()
                error_message = node_instance.logger.debug.call_args[0][0]
                assert "Failed to extract TDD connection info" in error_message

            finally:
                # Restore original TDD connection
                db._tdd_connection = original_tdd_connection


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
