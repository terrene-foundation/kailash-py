"""
Validation tests to verify DataFlow bugs 011 and 012 are actually fixed in generated code.

These tests specifically test the actual generated code to ensure the fixes work in practice.
"""

import inspect
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


class TestDataFlowBugFixesValidation:
    """Validation test suite to verify bugs 011 and 012 are actually fixed."""

    def test_generated_code_has_fixed_logger_reference(self, memory_dataflow):
        """
        Validate that generated node code contains 'self.logger' instead of 'logger'.

        This directly inspects the generated code to verify Bug 011 fix.
        """
        db = memory_dataflow

        @db.model
        class ValidateLoggerFixModel:
            name: str
            active: bool = True

        # Get the generated create node class
        create_node_class = db._nodes["ValidateLoggerFixModelCreateNode"]

        # Get the source code of the _get_tdd_connection_info method
        method = getattr(create_node_class, "_get_tdd_connection_info", None)
        assert (
            method is not None
        ), "Generated node should have _get_tdd_connection_info method"
        assert callable(method), "_get_tdd_connection_info should be callable"

        # Get the method source code
        try:
            source_code = inspect.getsource(method)
        except OSError:
            # Method might be dynamically generated, let's check the class
            source_code = inspect.getsource(create_node_class)

        # Verify the fix: should contain 'self.logger' not bare 'logger'
        assert (
            "self.logger.debug" in source_code
        ), "Fixed code should use 'self.logger.debug'"

        # Verify the bug is not present: should NOT contain bare 'logger.debug'
        # Note: We need to be careful not to match 'self.logger.debug'
        import re

        bare_logger_pattern = r"(?<!self\.)logger\.debug"
        bare_logger_matches = re.findall(bare_logger_pattern, source_code)
        assert (
            len(bare_logger_matches) == 0
        ), f"Fixed code should not contain bare 'logger.debug', found: {bare_logger_matches}"

    def test_generated_code_has_fixed_parameter_access(self, memory_dataflow):
        """
        Validate that generated node code uses safe parameter access with getattr().

        This directly inspects the generated code to verify Bug 012 fix.
        """
        db = memory_dataflow

        @db.model
        class ValidateParamFixModel:
            name: str
            active: bool = True

        # Get the generated create node class
        create_node_class = db._nodes["ValidateParamFixModelCreateNode"]

        # Get the _get_tdd_connection_info method
        method = getattr(create_node_class, "_get_tdd_connection_info", None)
        assert (
            method is not None
        ), "Generated node should have _get_tdd_connection_info method"

        # Since the method is defined in a closure, we can't easily get source code
        # Instead, test that it handles missing parameters correctly
        node_instance = create_node_class()
        node_instance._tdd_mode = True
        node_instance._test_context = {"unit_test": True}
        node_instance.dataflow_instance = db

        # Set up scenario with missing parameters (simulating real asyncpg)
        mock_connection = Mock()

        class MinimalAsyncpgParams:
            def __init__(self):
                # Only basic parameters exist
                self.user = "test_user"
                self.database = "test_database"
                # Missing: password, port, host, server_hostname

        mock_connection._params = MinimalAsyncpgParams()
        node_instance.dataflow_instance._tdd_connection = mock_connection

        # Missing optional attributes must reach extraction and use defaults.
        connection_info = node_instance._get_tdd_connection_info()
        assert connection_info == "postgresql://test_user:@localhost:5432/test_database"

    def test_bug_011_fix_works_in_practice(self, memory_dataflow):
        """
        Test that Bug 011 fix actually works when exceptions are raised.

        This tests the real generated code with actual exception scenarios.
        """
        db = memory_dataflow

        @db.model
        class PracticalLoggerTestModel:
            name: str
            active: bool = True

        # Get the generated create node class
        create_node_class = db._nodes["PracticalLoggerTestModelCreateNode"]

        # Create node instance
        node_instance = create_node_class()
        node_instance._tdd_mode = True
        node_instance._test_context = {"unit_test": True}

        # Verify the node has the required attributes
        assert hasattr(node_instance, "logger"), "Node should have logger attribute"
        assert hasattr(
            node_instance, "dataflow_instance"
        ), "Node should have dataflow_instance attribute"

        # Set up a scenario that will trigger the exception path
        node_instance.dataflow_instance = SimpleNamespace()

        # Mock TDD connection that will cause exception in parameter extraction
        mock_connection = Mock()

        class ExceptionTriggeringParams:
            def __init__(self):
                self.user = "test_user"
                self.password = "test_password"
                self.database = "test_database"
                self.port = 5434

            def __getattr__(self, name):
                # This will trigger an exception that should be caught and logged
                raise RuntimeError(f"Simulated error accessing {name}")

        mock_connection._params = ExceptionTriggeringParams()
        node_instance.dataflow_instance._tdd_connection = mock_connection

        # The fixed method should handle the exception gracefully using self.logger
        # This should NOT raise NameError about 'logger' not being defined
        node_instance.logger = Mock()
        connection_info = node_instance._get_tdd_connection_info()

        # Should return None due to the exception, but not crash with NameError
        assert connection_info is None

        node_instance.logger.debug.assert_called_once_with(
            "nodes.failed_to_extract_tdd_connection_info",
            extra={"error_type": "RuntimeError"},
        )
        assert "Simulated error accessing host" not in repr(
            node_instance.logger.debug.call_args
        )

    def test_bug_012_fix_works_in_practice(self, memory_dataflow):
        """
        Test that Bug 012 fix actually works with missing connection parameters.

        This tests the real generated code with missing parameter scenarios.
        """
        db = memory_dataflow

        @db.model
        class PracticalParamTestModel:
            name: str
            active: bool = True

        # Get the generated create node class
        create_node_class = db._nodes["PracticalParamTestModelCreateNode"]

        # Create node instance
        node_instance = create_node_class()
        node_instance._tdd_mode = True
        node_instance._test_context = {"unit_test": True}

        # Set up scenario with missing parameters
        node_instance.dataflow_instance = SimpleNamespace()

        # Mock TDD connection with minimal parameters (simulating real asyncpg)
        mock_connection = Mock()

        class MinimalAsyncpgParams:
            def __init__(self):
                # Only basic parameters exist
                self.user = "test_user"
                self.database = "test_database"
                # Missing: password, port, host, server_hostname

            def __getattr__(self, name):
                # Simulate real asyncpg behavior - missing attributes raise AttributeError
                if name in ["host", "server_hostname", "password", "port"]:
                    raise AttributeError(
                        f"'ConnectionParameters' object has no attribute '{name}'"
                    )
                raise AttributeError(
                    f"'ConnectionParameters' object has no attribute '{name}'"
                )

        mock_connection._params = MinimalAsyncpgParams()
        node_instance.dataflow_instance._tdd_connection = mock_connection

        # AttributeError is an absent optional attribute, so defaults apply.
        connection_info = node_instance._get_tdd_connection_info()
        assert connection_info == "postgresql://test_user:@localhost:5432/test_database"

    def test_both_bugs_fixed_together_in_practice(self, memory_dataflow):
        """
        Test that both fixes work together in the real generated code.

        This tests a scenario that would trigger both bugs in the original code.
        """
        db = memory_dataflow

        @db.model
        class CombinedFixTestModel:
            name: str
            active: bool = True

        # Get the generated create node class
        create_node_class = db._nodes["CombinedFixTestModelCreateNode"]

        # Create node instance
        node_instance = create_node_class()
        node_instance._tdd_mode = True
        node_instance._test_context = {"unit_test": True}

        # Set up scenario that would trigger both bugs
        node_instance.dataflow_instance = SimpleNamespace()

        # Mock TDD connection that causes both parameter access issues AND logging issues
        mock_connection = Mock()

        class ProblematicAsyncpgParams:
            def __init__(self):
                self.user = "test_user"
                # Other attributes will cause various exceptions

            def __getattr__(self, name):
                if name == "password":
                    raise AttributeError(
                        "'ConnectionParameters' object has no attribute 'password'"
                    )
                elif name == "host":
                    raise AttributeError(
                        "'ConnectionParameters' object has no attribute 'host'"
                    )
                elif name == "server_hostname":
                    raise ConnectionError("Network error accessing server_hostname")
                elif name == "database":
                    raise RuntimeError("Database parameter corrupted")
                elif name == "port":
                    raise ValueError("Invalid port configuration")
                else:
                    raise AttributeError(
                        f"'ConnectionParameters' object has no attribute '{name}'"
                    )

        mock_connection._params = ProblematicAsyncpgParams()
        node_instance.dataflow_instance._tdd_connection = mock_connection

        # Both fixes should work together:
        # 1. Bug 011 fix: Exception should be logged using self.logger (not bare logger)
        # 2. Bug 012 fix: Missing parameters should be handled gracefully
        node_instance.logger = Mock()
        connection_info = node_instance._get_tdd_connection_info()

        # Should handle the complex exception scenario gracefully
        # With multiple exceptions occurring, the method correctly returns None
        # The key is that it doesn't crash with NameError for logger (Bug 011 fixed)
        assert connection_info is None  # Correctly handles multiple exceptions

        node_instance.logger.debug.assert_called_once_with(
            "nodes.failed_to_extract_tdd_connection_info",
            extra={"error_type": "ConnectionError"},
        )
        assert "Network error accessing server_hostname" not in repr(
            node_instance.logger.debug.call_args
        )

    def test_fixes_preserve_existing_functionality(self, memory_dataflow):
        """
        Test that the fixes don't break existing functionality.

        This ensures that normal operation still works correctly.
        """
        db = memory_dataflow

        @db.model
        class FunctionalityTestModel:
            name: str
            active: bool = True

        # Test all generated node types
        node_types = [
            "FunctionalityTestModelCreateNode",
            "FunctionalityTestModelReadNode",
            "FunctionalityTestModelUpdateNode",
            "FunctionalityTestModelDeleteNode",
            "FunctionalityTestModelListNode",
        ]

        for node_type in node_types:
            assert node_type in db._nodes
            if node_type in db._nodes:
                node_class = db._nodes[node_type]
                node_instance = node_class()

                # Verify basic functionality is preserved
                assert hasattr(node_instance, "_get_tdd_connection_info")
                assert callable(getattr(node_instance, "_get_tdd_connection_info"))
                assert hasattr(node_instance, "logger")
                assert hasattr(node_instance, "dataflow_instance")

                # Test normal case without TDD connection (should return None)
                node_instance.dataflow_instance = SimpleNamespace()
                connection_info = node_instance._get_tdd_connection_info()
                assert connection_info is None  # No TDD connection should return None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
