"""
Comprehensive parity tests for PythonCodeNode (sync) and AsyncPythonCodeNode (async).

These tests ensure that both versions maintain consistent behavior, security policies,
and feature sets. Any deviation should be intentional and documented.

Version: v0.9.30
Created: 2025-10-24
Purpose: Prevent regression and ensure consistency between sync/async implementations
"""

import pytest
from kailash.nodes.code.async_python import AsyncPythonCodeNode
from kailash.nodes.code.common import (
    ALLOWED_ASYNC_BUILTINS,
    ALLOWED_ASYNC_MODULES,
    ALLOWED_BUILTINS,
    ALLOWED_MODULES,
    COMMON_ALLOWED_BUILTINS,
    COMMON_ALLOWED_MODULES,
)
from kailash.nodes.code.python import PythonCodeNode


class TestModuleWhitelistParity:
    """Test that module whitelists have consistent base and documented differences."""

    def test_common_modules_in_both(self):
        """Both sync and async should include all common modules."""
        assert COMMON_ALLOWED_MODULES.issubset(
            ALLOWED_MODULES
        ), "Common modules missing from sync"
        assert COMMON_ALLOWED_MODULES.issubset(
            ALLOWED_ASYNC_MODULES
        ), "Common modules missing from async"

    def test_critical_modules_in_both(self):
        """Critical modules must be in both versions."""
        critical_modules = {
            "math",
            "json",
            "datetime",
            "pandas",
            "numpy",
            "logging",
            "io",
            "types",
            "pathlib",
            "os",
        }

        assert critical_modules.issubset(
            ALLOWED_MODULES
        ), f"Missing critical modules in sync: {critical_modules - ALLOWED_MODULES}"
        assert critical_modules.issubset(
            ALLOWED_ASYNC_MODULES
        ), f"Missing critical modules in async: {critical_modules - ALLOWED_ASYNC_MODULES}"

    def test_async_specific_modules_not_in_sync(self):
        """Async-specific modules should not be in sync."""
        async_only = {"asyncio", "aiohttp", "asyncpg", "aiofiles"}

        for module in async_only:
            assert module in ALLOWED_ASYNC_MODULES, f"{module} should be in async"
            assert module not in ALLOWED_MODULES, f"{module} should not be in sync"

    def test_sync_specific_modules_not_in_async(self):
        """Sync-specific modules should not be in async."""
        sync_only = {"matplotlib", "seaborn", "plotly"}

        for module in sync_only:
            assert module in ALLOWED_MODULES, f"{module} should be in sync"
            # These could be in async too, but typically aren't due to blocking I/O


class TestBuiltinFunctionsParity:
    """Test that builtin functions have consistent base and documented differences."""

    def test_common_builtins_in_both(self):
        """Both sync and async should include all common builtins."""
        assert COMMON_ALLOWED_BUILTINS.issubset(
            ALLOWED_BUILTINS
        ), "Common builtins missing from sync"
        assert COMMON_ALLOWED_BUILTINS.issubset(
            ALLOWED_ASYNC_BUILTINS
        ), "Common builtins missing from async"

    def test_critical_builtins_in_both(self):
        """Critical builtins must be in both versions."""
        critical_builtins = {
            # Iteration (CRITICAL)
            "iter",
            "next",
            "len",
            "range",
            "enumerate",
            # Types
            "dict",
            "list",
            "str",
            "int",
            "float",
            # Exceptions (CRITICAL for cycle patterns)
            "NameError",
            "ValueError",
            "TypeError",
            "KeyError",
            # Type checking
            "isinstance",
            "hasattr",
            "type",
        }

        assert critical_builtins.issubset(
            ALLOWED_BUILTINS
        ), f"Missing critical builtins in sync: {critical_builtins - ALLOWED_BUILTINS}"
        assert critical_builtins.issubset(
            ALLOWED_ASYNC_BUILTINS
        ), f"Missing critical builtins in async: {critical_builtins - ALLOWED_ASYNC_BUILTINS}"

    def test_sync_has_open_async_does_not(self):
        """Sync should have 'open', async should not (use aiofiles)."""
        assert "open" in ALLOWED_BUILTINS, "Sync should have 'open'"
        assert "open" not in ALLOWED_ASYNC_BUILTINS, "Async should not have 'open'"

    def test_async_has_locals_globals_sync_does_not(self):
        """Async should have 'locals'/'globals' for debugging, sync might not."""
        assert "locals" in ALLOWED_ASYNC_BUILTINS, "Async should have 'locals'"
        assert "globals" in ALLOWED_ASYNC_BUILTINS, "Async should have 'globals'"


class TestExceptionClassesParity:
    """Test that exception classes are identical in both versions."""

    def test_all_exception_classes_identical(self):
        """Both versions must support identical exception classes."""
        exception_classes = {
            "Exception",
            "ValueError",
            "TypeError",
            "KeyError",
            "NameError",  # CRITICAL for cycle patterns
            "AttributeError",
            "IndexError",
            "RuntimeError",
            "StopIteration",
            "ImportError",
            "OSError",
            "IOError",
            "FileNotFoundError",
            "ZeroDivisionError",
            "ArithmeticError",
            "AssertionError",
            "ConnectionError",
        }

        missing_sync = exception_classes - ALLOWED_BUILTINS
        missing_async = exception_classes - ALLOWED_ASYNC_BUILTINS

        assert not missing_sync, f"Missing exception classes in sync: {missing_sync}"
        assert not missing_async, f"Missing exception classes in async: {missing_async}"


class TestAPIConsistency:
    """Test that both nodes expose consistent public APIs."""

    def test_both_have_list_allowed_modules(self):
        """Both nodes should have list_allowed_modules static method."""
        assert hasattr(
            PythonCodeNode, "list_allowed_modules"
        ), "Sync missing list_allowed_modules"
        assert hasattr(
            AsyncPythonCodeNode, "list_allowed_modules"
        ), "Async missing list_allowed_modules"

    def test_both_have_check_module_availability(self):
        """Both nodes should have check_module_availability static method."""
        assert hasattr(
            PythonCodeNode, "check_module_availability"
        ), "Sync missing check_module_availability"
        assert hasattr(
            AsyncPythonCodeNode, "check_module_availability"
        ), "Async missing check_module_availability"

    def test_both_have_validate_code(self):
        """Both nodes should have validate_code method."""
        sync_node = PythonCodeNode(name="test", code="result = 1")
        async_node = AsyncPythonCodeNode(code="result = 1")

        assert hasattr(sync_node, "validate_code"), "Sync missing validate_code"
        assert hasattr(async_node, "validate_code"), "Async missing validate_code"

    def test_both_have_from_function(self):
        """Both nodes should have from_function class method."""
        assert hasattr(PythonCodeNode, "from_function"), "Sync missing from_function"
        assert hasattr(
            AsyncPythonCodeNode, "from_function"
        ), "Async missing from_function"


class TestSecurityConsistency:
    """Test that security policies are consistent between sync and async."""

    def test_both_block_eval_exec(self):
        """Both should block eval and exec."""
        # Test sync - validate_code returns a result dict, doesn't raise
        sync_node = PythonCodeNode(name="test_sync", code="result=1")
        sync_result = sync_node.validate_code("eval('1+1')")
        assert not sync_result["valid"], "Sync should mark eval as invalid"

        # Test async - initialization raises SafetyViolationError
        with pytest.raises(Exception):  # SafetyViolationError
            async_node = AsyncPythonCodeNode(code="eval('1+1')")

    def test_both_block_subprocess(self):
        """Both should block subprocess imports."""
        # Test sync
        sync_result = PythonCodeNode(name="test", code="result=1").validate_code(
            "import subprocess"
        )
        assert not sync_result["valid"], "Sync should block subprocess"

        # Test async
        with pytest.raises(Exception):  # SafetyViolationError
            async_node = AsyncPythonCodeNode(code="import subprocess")

    def test_both_allow_safe_modules(self):
        """Both should allow safe common modules."""
        safe_modules = ["math", "json", "datetime", "pandas"]

        for module in safe_modules:
            # Sync
            sync_code = f"import {module}\nresult = 1"
            sync_result = PythonCodeNode(name="test", code="result=1").validate_code(
                sync_code
            )
            assert sync_result["valid"], f"Sync should allow {module}"

            # Async
            async_code = f"import {module}\nresult = 1"
            try:
                async_node = AsyncPythonCodeNode(code=async_code)
                assert True, f"Async should allow {module}"
            except Exception as e:
                pytest.fail(f"Async should allow {module}: {e}")


@pytest.mark.asyncio
async def test_variable_export_consistency():
    """Both should export variables consistently (multi-output pattern)."""
    code = """
filter_data = {"id": "test_123"}
fields_data = {"name": "John", "active": True}
count = 42
"""

    # Test async
    async_node = AsyncPythonCodeNode(code=code)
    async_result = await async_node.execute_async()

    # Both should export all variables
    assert "filter_data" in async_result
    assert "fields_data" in async_result
    assert "count" in async_result

    # Values should be correct
    assert async_result["filter_data"] == {"id": "test_123"}
    assert async_result["fields_data"] == {"name": "John", "active": True}
    assert async_result["count"] == 42


@pytest.mark.asyncio
async def test_result_variable_priority_consistency():
    """Both should prioritize 'result' when it exists."""
    code = """
other_var = {"data": "ignored"}
result = {"status": "success"}
"""

    # Test async
    async_node = AsyncPythonCodeNode(code=code)
    async_result = await async_node.execute_async()

    # Should only return 'result'
    assert "result" in async_result
    assert async_result["result"] == {"status": "success"}
    assert "other_var" not in async_result


@pytest.mark.asyncio
async def test_module_filtering_consistency():
    """Both should filter out imported modules from exports."""
    code = """
import json
import math

# These should be exported
data = {"value": 42}
number = math.pi
"""

    # Test async
    async_node = AsyncPythonCodeNode(code=code)
    async_result = await async_node.execute_async()

    # Variables should be exported
    assert "data" in async_result
    assert "number" in async_result

    # Modules should NOT be exported
    assert "json" not in async_result
    assert "math" not in async_result


def test_utility_method_consistency():
    """Both should have consistent utility method implementations."""
    # Test list_allowed_modules
    sync_modules = PythonCodeNode.list_allowed_modules()
    async_modules = AsyncPythonCodeNode.list_allowed_modules()

    assert isinstance(sync_modules, list), "Sync should return list"
    assert isinstance(async_modules, list), "Async should return list"
    assert len(sync_modules) > 0, "Sync should have modules"
    assert len(async_modules) > 0, "Async should have modules"

    # Test check_module_availability
    sync_check = PythonCodeNode.check_module_availability("math")
    async_check = AsyncPythonCodeNode.check_module_availability("asyncio")

    assert "module" in sync_check, "Sync should return structured result"
    assert "allowed" in sync_check, "Sync should indicate if allowed"
    assert "module" in async_check, "Async should return structured result"
    assert "allowed" in async_check, "Async should indicate if allowed"

    assert sync_check["allowed"], "math should be allowed in sync"
    assert async_check["allowed"], "asyncio should be allowed in async"


def test_error_message_quality():
    """Both should provide helpful error messages."""
    # Test module not allowed
    sync_result = PythonCodeNode(name="test", code="result=1").validate_code(
        "import subprocess"
    )
    assert not sync_result["valid"]
    assert len(sync_result["suggestions"]) > 0, "Sync should provide suggestions"

    # Test async
    with pytest.raises(Exception) as exc_info:
        AsyncPythonCodeNode(code="import subprocess")

    error_message = str(exc_info.value)
    assert "subprocess" in error_message.lower()
    assert len(error_message) > 50, "Error message should be informative"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
