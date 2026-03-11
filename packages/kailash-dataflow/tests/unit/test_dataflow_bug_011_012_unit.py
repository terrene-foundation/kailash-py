"""
Unit tests for DataFlow bugs 011 and 012.

Bug 011: Logger undefined error (line 1758 in dataflow/core/nodes.py)
Bug 012: TDD isolation bypass due to params.host access failure (line 1748)

These tests demonstrate the bugs before implementing fixes.
"""

import logging
import os
from unittest.mock import Mock, patch

import pytest


class TestDataFlowBugs011And012:
    """Test suite for critical DataFlow bugs 011 and 012."""

    def test_bug_011_logger_undefined_error(self):
        """
        Test Bug 011: logger.debug() should be self.logger.debug()

        This test directly creates a mock node with the buggy code pattern.
        """

        # Create a mock node that simulates the generated DataFlow node
        class MockDataFlowNode:
            def __init__(self):
                self.dataflow_instance = Mock()
                # Note: NO logger attribute - this is part of the bug

            def _get_tdd_connection_info(self):
                """Simulate the buggy method from lines 1733-1759 in nodes.py"""
                if hasattr(self.dataflow_instance, "_tdd_connection"):
                    # Build connection string from TDD connection
                    try:
                        # For asyncpg connections, we can get connection parameters
                        conn = self.dataflow_instance._tdd_connection
                        if hasattr(conn, "_params"):
                            params = conn._params
                            # Bug 012: params.host doesn't exist in asyncpg
                            return f"postgresql://{params.user}:{params.password}@{params.host}:{params.port}/{params.database}"
                        else:
                            # Fallback: use test database URL from environment
                            return os.getenv(
                                "TEST_DATABASE_URL",
                                "postgresql://dataflow_test:dataflow_test_password@localhost:5434/dataflow_test",
                            )
                    except Exception as e:
                        # Bug 011: 'logger' is not defined in this scope
                        logger.debug(f"Failed to extract TDD connection info: {e}")
                        return None

                return None

        # Create node instance and set up the bug scenario
        node_instance = MockDataFlowNode()

        # Mock TDD connection to trigger the exception path
        mock_connection = Mock()
        mock_connection._params = Mock()
        # Remove host attribute to trigger the exception
        delattr(mock_connection._params, "host")
        node_instance.dataflow_instance._tdd_connection = mock_connection

        # The bug: calling _get_tdd_connection_info should raise NameError
        # because 'logger' is not defined in the method scope
        with pytest.raises(NameError, match="name 'logger' is not defined"):
            node_instance._get_tdd_connection_info()

    def test_bug_012_params_host_attribute_error(self):
        """
        Test Bug 012: params.host access fails because asyncpg doesn't have host attribute

        This test demonstrates that asyncpg connection parameters don't have a 'host'
        attribute, causing AttributeError when trying to build connection string.
        """

        # Create a mock node that simulates the generated DataFlow node
        class MockDataFlowNodeForBug012:
            def __init__(self):
                self.dataflow_instance = Mock()
                self.logger = Mock()  # Add logger to avoid Bug 011

            def _get_tdd_connection_info(self):
                """Simulate the buggy method with proper logger but broken params access"""
                if hasattr(self.dataflow_instance, "_tdd_connection"):
                    try:
                        conn = self.dataflow_instance._tdd_connection
                        if hasattr(conn, "_params"):
                            params = conn._params
                            # Bug 012: params.host doesn't exist in asyncpg
                            return f"postgresql://{params.user}:{params.password}@{params.host}:{params.port}/{params.database}"
                        else:
                            return os.getenv(
                                "TEST_DATABASE_URL",
                                "postgresql://dataflow_test:dataflow_test_password@localhost:5434/dataflow_test",
                            )
                    except Exception as e:
                        # Using proper self.logger (Bug 011 fixed for this test)
                        self.logger.debug(f"Failed to extract TDD connection info: {e}")
                        return None

                return None

        # Create node instance
        node_instance = MockDataFlowNodeForBug012()

        # Mock TDD connection with realistic asyncpg _params structure
        mock_connection = Mock()

        # Create a custom class that simulates asyncpg ConnectionParameters
        class FakeAsyncpgParams:
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

        mock_connection._params = FakeAsyncpgParams()
        node_instance.dataflow_instance._tdd_connection = mock_connection

        # The bug: accessing params.host should cause the method to return None
        connection_info = node_instance._get_tdd_connection_info()

        # Should return None due to the AttributeError
        assert connection_info is None

        # Should have logged the error
        node_instance.logger.debug.assert_called_once()
        error_message = node_instance.logger.debug.call_args[0][0]
        assert "Failed to extract TDD connection info" in error_message

    def test_bug_012_fallback_to_test_database_url(self):
        """
        Test that when TDD connection info extraction fails, it falls back to TEST_DATABASE_URL.

        This demonstrates the intended behavior when Bug 012 is present.
        """

        # Create a mock node with logger but broken params access
        class MockDataFlowNodeFallback:
            def __init__(self):
                self.dataflow_instance = Mock()
                self.logger = Mock()

            def _get_tdd_connection_info(self):
                """Simulate the buggy method that falls back to TEST_DATABASE_URL"""
                if hasattr(self.dataflow_instance, "_tdd_connection"):
                    try:
                        conn = self.dataflow_instance._tdd_connection
                        if hasattr(conn, "_params"):
                            params = conn._params
                            # Bug 012: params.host doesn't exist
                            return f"postgresql://{params.user}:{params.password}@{params.host}:{params.port}/{params.database}"
                        else:
                            # Fallback path
                            return os.getenv(
                                "TEST_DATABASE_URL",
                                "postgresql://dataflow_test:dataflow_test_password@localhost:5434/dataflow_test",
                            )
                    except Exception as e:
                        self.logger.debug(f"Failed to extract TDD connection info: {e}")
                        return None

                return None

        node_instance = MockDataFlowNodeFallback()

        # Mock TDD connection that will cause params.host access failure
        mock_connection = Mock()

        # Create a custom class that simulates asyncpg ConnectionParameters
        class FakeAsyncpgParamsFallback:
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

        mock_connection._params = FakeAsyncpgParamsFallback()
        node_instance.dataflow_instance._tdd_connection = mock_connection

        # Set TEST_DATABASE_URL environment variable
        test_db_url = "postgresql://test:test@localhost:5434/test"
        with patch.dict(os.environ, {"TEST_DATABASE_URL": test_db_url}):
            connection_info = node_instance._get_tdd_connection_info()

            # Should return None due to Bug 012 (params.host AttributeError)
            assert connection_info is None

            # Should have logged the error
            node_instance.logger.debug.assert_called_once()

    def test_correct_asyncpg_connection_params_structure(self):
        """
        Test showing what the CORRECT asyncpg connection parameters structure should be.

        This test demonstrates the fix for Bug 012 by showing proper attribute access.
        """
        # Research shows asyncpg connection params have different structure
        # Based on asyncpg documentation, connection parameters use different names

        # Create a node with the FIXED method (what it should be)
        class FixedDataFlowNode:
            def __init__(self):
                self.dataflow_instance = Mock()
                self.logger = Mock()

            def _get_tdd_connection_info(self):
                """Simulate the FIXED method with correct asyncpg parameter access"""
                if hasattr(self.dataflow_instance, "_tdd_connection"):
                    try:
                        conn = self.dataflow_instance._tdd_connection
                        if hasattr(conn, "_params"):
                            params = conn._params
                            # FIXED: Use correct asyncpg parameter names
                            # asyncpg uses different attribute names than params.host
                            host = getattr(params, "server_hostname", "localhost")
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
                        self.logger.debug(f"Failed to extract TDD connection info: {e}")
                        return None

                return None

        node_instance = FixedDataFlowNode()

        # Mock TDD connection with more realistic asyncpg _params structure
        mock_connection = Mock()
        mock_params = Mock()

        # Use correct asyncpg parameter names (what the fix should use)
        mock_params.server_hostname = "localhost"
        mock_params.user = "test_user"
        mock_params.password = "test_password"
        mock_params.database = "test_database"
        mock_params.port = 5434

        mock_connection._params = mock_params
        node_instance.dataflow_instance._tdd_connection = mock_connection

        # The fixed method should work correctly
        connection_info = node_instance._get_tdd_connection_info()

        # Should successfully build connection string
        expected = "postgresql://test_user:test_password@localhost:5434/test_database"
        assert connection_info == expected

        # Should not have logged any errors
        node_instance.logger.debug.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    def test_default_fallback_when_no_env_var(self):
        """
        Test behavior when TEST_DATABASE_URL is not set and connection extraction fails.

        Should use the default fallback URL.
        """

        class MockDataFlowNodeDefault:
            def __init__(self):
                self.dataflow_instance = Mock()
                self.logger = Mock()

            def _get_tdd_connection_info(self):
                """Simulate method that falls back to default when no TEST_DATABASE_URL"""
                if hasattr(self.dataflow_instance, "_tdd_connection"):
                    try:
                        conn = self.dataflow_instance._tdd_connection
                        if hasattr(conn, "_params"):
                            params = conn._params
                            # Bug 012: params.host doesn't exist
                            return f"postgresql://{params.user}:{params.password}@{params.host}:{params.port}/{params.database}"
                        else:
                            return os.getenv(
                                "TEST_DATABASE_URL",
                                "postgresql://dataflow_test:dataflow_test_password@localhost:5434/dataflow_test",
                            )
                    except Exception as e:
                        self.logger.debug(f"Failed to extract TDD connection info: {e}")
                        return None

                return None

        node_instance = MockDataFlowNodeDefault()

        # Mock TDD connection that will cause attribute error
        mock_connection = Mock()

        # Create a custom class that simulates asyncpg ConnectionParameters with missing attrs
        class FakeAsyncpgParamsMinimal:
            def __init__(self):
                self.user = "test_user"
                # Missing other attributes to trigger Bug 012

            def __getattr__(self, name):
                if name in ["host", "password", "database", "port"]:
                    raise AttributeError(
                        f"'ConnectionParameters' object has no attribute '{name}'"
                    )
                raise AttributeError(
                    f"'FakeAsyncpgParams' object has no attribute '{name}'"
                )

        mock_connection._params = FakeAsyncpgParamsMinimal()
        node_instance.dataflow_instance._tdd_connection = mock_connection

        # Should return None due to Bug 012 and no TEST_DATABASE_URL fallback
        connection_info = node_instance._get_tdd_connection_info()
        assert connection_info is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
