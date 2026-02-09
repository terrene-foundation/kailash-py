"""Unit tests for PythonCodeNode and AsyncPythonCodeNode sandbox_mode parameter.

Tests cover:
- Default restricted mode blocks disallowed imports
- Trusted mode allows any import
- Invalid sandbox_mode raises error
- Security warning emitted in trusted mode
- Syntax errors still caught in trusted mode (async variant)
"""

import logging

import pytest
from kailash.nodes.code.async_python import AsyncPythonCodeNode
from kailash.nodes.code.python import PythonCodeNode
from kailash.sdk_exceptions import NodeConfigurationError, NodeExecutionError


class TestPythonCodeNodeSandboxMode:
    """Tests for PythonCodeNode sandbox_mode parameter."""

    def test_default_restricted_mode(self):
        """Default mode should be 'restricted'."""
        node = PythonCodeNode(
            name="test_node",
            code="result = 42",
            validate_security=False,
        )
        assert node.sandbox_mode == "restricted"

    def test_restricted_mode_blocks_imports(self):
        """Restricted mode should block disallowed imports."""
        node = PythonCodeNode(
            name="test_node",
            code="import subprocess\nresult = 1",
            validate_security=False,
        )
        # The safety check happens in execute_code, not at init
        with pytest.raises((NodeExecutionError, Exception)):
            node.run()

    def test_trusted_mode_allows_any_import(self):
        """Trusted mode should allow imports that would normally be blocked."""
        node = PythonCodeNode(
            name="test_node",
            code="import sys\nresult = sys.version",
            sandbox_mode="trusted",
            validate_security=False,
        )
        assert node.sandbox_mode == "trusted"
        # Should not raise on execution - sys is always available
        result = node.run()
        assert "result" in result
        assert isinstance(result["result"], str)

    def test_invalid_sandbox_mode_raises(self):
        """Invalid sandbox_mode should raise NodeConfigurationError."""
        with pytest.raises(NodeConfigurationError, match="sandbox_mode must be"):
            PythonCodeNode(
                name="test_node",
                code="result = 1",
                sandbox_mode="invalid_mode",
            )

    def test_trusted_mode_emits_warning(self, caplog):
        """Trusted mode should emit a security warning."""
        with caplog.at_level(logging.WARNING):
            PythonCodeNode(
                name="test_node",
                code="result = 1",
                sandbox_mode="trusted",
                validate_security=False,
            )

        assert any("sandbox_mode='trusted'" in msg for msg in caplog.messages)
        assert any(
            "Only use this for code you fully control" in msg for msg in caplog.messages
        )


class TestAsyncPythonCodeNodeSandboxMode:
    """Tests for AsyncPythonCodeNode sandbox_mode parameter."""

    def test_default_restricted_mode(self):
        """Default mode should be 'restricted'."""
        node = AsyncPythonCodeNode(
            code="import asyncio\nawait asyncio.sleep(0)\nresult = {'ok': True}",
        )
        assert node.sandbox_mode == "restricted"

    def test_trusted_mode_creation(self):
        """Trusted mode should allow creation with disallowed imports."""
        # This import would normally fail validation in restricted mode
        node = AsyncPythonCodeNode(
            code="import subprocess\nresult = {'ok': True}",
            sandbox_mode="trusted",
        )
        assert node.sandbox_mode == "trusted"

    def test_invalid_sandbox_mode_raises(self):
        """Invalid sandbox_mode should raise NodeConfigurationError."""
        with pytest.raises(NodeConfigurationError, match="sandbox_mode must be"):
            AsyncPythonCodeNode(
                code="result = 1",
                sandbox_mode="invalid_mode",
            )

    def test_trusted_mode_still_checks_syntax(self):
        """Trusted mode should still reject syntax errors."""
        with pytest.raises(NodeConfigurationError, match="syntax error"):
            AsyncPythonCodeNode(
                code="def foo(:\n  pass",
                sandbox_mode="trusted",
            )

    def test_trusted_mode_emits_warning(self, caplog):
        """Trusted mode should emit a security warning."""
        with caplog.at_level(logging.WARNING):
            AsyncPythonCodeNode(
                code="import asyncio\nresult = {'ok': True}",
                sandbox_mode="trusted",
            )

        assert any("sandbox_mode='trusted'" in msg for msg in caplog.messages)
