"""Unit tests for Nexus handler() decorator and register_handler() method.

Tests cover:
- Decorator behavior (returns original function)
- register_handler() method validation
- Handler registry population
- Invalid input handling
- Integration with workflow registration
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))


async def sample_handler(name: str, count: int = 1) -> dict:
    """Sample handler for testing."""
    return {"name": name, "count": count}


async def another_handler(text: str) -> dict:
    return {"text": text}


class TestHandlerDecorator:
    """Tests for @app.handler() decorator."""

    def test_decorator_returns_original_function(self):
        """The decorator should return the original function unchanged."""
        with patch("nexus.core.create_gateway") as mock_gw:
            mock_gw.return_value = Mock()
            from nexus import Nexus

            app = Nexus()

            @app.handler("sample")
            async def my_handler(name: str) -> dict:
                return {"name": name}

            # The decorator should return the original function
            assert my_handler.__name__ == "my_handler"
            assert callable(my_handler)

    def test_decorator_registers_workflow(self):
        """Handler decorator should register workflow in _workflows."""
        with patch("nexus.core.create_gateway") as mock_gw:
            mock_gw.return_value = Mock()
            from nexus import Nexus

            app = Nexus()

            @app.handler("greet", description="Greeting handler")
            async def greet(name: str) -> dict:
                return {"message": f"Hello, {name}!"}

            assert "greet" in app._workflows
            assert "greet" in app._handler_registry

    def test_decorator_with_tags(self):
        """Handler decorator should store tags in registry."""
        with patch("nexus.core.create_gateway") as mock_gw:
            mock_gw.return_value = Mock()
            from nexus import Nexus

            app = Nexus()

            @app.handler("tagged", tags=["api", "test"])
            async def tagged_handler(x: str) -> dict:
                return {"x": x}

            assert app._handler_registry["tagged"]["tags"] == ["api", "test"]

    def test_decorator_stores_description(self):
        """Handler decorator should store description in registry."""
        with patch("nexus.core.create_gateway") as mock_gw:
            mock_gw.return_value = Mock()
            from nexus import Nexus

            app = Nexus()

            @app.handler("described", description="A test handler")
            async def described_handler(x: str) -> dict:
                return {"x": x}

            assert app._handler_registry["described"]["description"] == "A test handler"

    def test_decorator_uses_docstring_as_fallback_description(self):
        """Without explicit description, handler docstring is used."""
        with patch("nexus.core.create_gateway") as mock_gw:
            mock_gw.return_value = Mock()
            from nexus import Nexus

            app = Nexus()

            @app.handler("documented")
            async def documented_handler(x: str) -> dict:
                """Handler with docstring."""
                return {"x": x}

            assert (
                "Handler with docstring"
                in app._handler_registry["documented"]["description"]
            )


class TestRegisterHandler:
    """Tests for app.register_handler() method."""

    def test_register_handler_basic(self):
        """register_handler should create workflow and populate registry."""
        with patch("nexus.core.create_gateway") as mock_gw:
            mock_gw.return_value = Mock()
            from nexus import Nexus

            app = Nexus()
            app.register_handler("sample", sample_handler)

            assert "sample" in app._workflows
            assert "sample" in app._handler_registry
            assert app._handler_registry["sample"]["handler"] is sample_handler

    def test_register_handler_non_callable_raises(self):
        """register_handler should raise TypeError for non-callable."""
        with patch("nexus.core.create_gateway") as mock_gw:
            mock_gw.return_value = Mock()
            from nexus import Nexus

            app = Nexus()

            with pytest.raises(TypeError, match="handler_func must be callable"):
                app.register_handler("bad", "not a function")

    def test_register_handler_empty_name_raises(self):
        """register_handler should raise ValueError for empty name."""
        with patch("nexus.core.create_gateway") as mock_gw:
            mock_gw.return_value = Mock()
            from nexus import Nexus

            app = Nexus()

            with pytest.raises(ValueError, match="name cannot be empty"):
                app.register_handler("", sample_handler)

    def test_register_handler_whitespace_name_raises(self):
        """register_handler should raise ValueError for whitespace-only name."""
        with patch("nexus.core.create_gateway") as mock_gw:
            mock_gw.return_value = Mock()
            from nexus import Nexus

            app = Nexus()

            with pytest.raises(ValueError, match="name cannot be empty"):
                app.register_handler("   ", sample_handler)

    def test_register_multiple_handlers(self):
        """Multiple handlers can be registered with different names."""
        with patch("nexus.core.create_gateway") as mock_gw:
            mock_gw.return_value = Mock()
            from nexus import Nexus

            app = Nexus()
            app.register_handler("handler_a", sample_handler)
            app.register_handler("handler_b", another_handler)

            assert len(app._handler_registry) == 2
            assert "handler_a" in app._handler_registry
            assert "handler_b" in app._handler_registry

    def test_register_handler_stores_workflow(self):
        """Handler registry should include the built workflow."""
        with patch("nexus.core.create_gateway") as mock_gw:
            mock_gw.return_value = Mock()
            from nexus import Nexus

            app = Nexus()
            app.register_handler("sample", sample_handler)

            assert app._handler_registry["sample"]["workflow"] is not None

    def test_register_sync_handler(self):
        """Sync functions should be accepted as handlers."""
        with patch("nexus.core.create_gateway") as mock_gw:
            mock_gw.return_value = Mock()
            from nexus import Nexus

            app = Nexus()

            def sync_handler(x: int) -> dict:
                return {"result": x * 2}

            app.register_handler("sync", sync_handler)
            assert "sync" in app._handler_registry


class TestWorkflowSandboxValidation:
    """Tests for _validate_workflow_sandbox() registration-time validation."""

    def test_warns_on_blocked_imports(self, caplog):
        """Should warn when PythonCodeNode uses blocked imports."""
        with patch("nexus.core.create_gateway") as mock_gw:
            mock_gw.return_value = Mock()
            from nexus import Nexus

            app = Nexus()

            # Build a workflow with PythonCodeNode that has blocked imports
            from kailash.nodes.code.python import PythonCodeNode
            from kailash.workflow.builder import WorkflowBuilder

            node = PythonCodeNode(
                name="bad_node",
                code="import subprocess\nresult = subprocess.run(['ls'])",
                validate_security=False,
            )
            builder = WorkflowBuilder()
            builder.add_node_instance(node, "bad_node")
            workflow = builder.build()

            import logging

            with caplog.at_level(logging.WARNING, logger="nexus.core"):
                app.register("bad_workflow", workflow)

            assert any("subprocess" in msg for msg in caplog.messages)
            assert any("@app.handler()" in msg for msg in caplog.messages)

    def test_no_warning_for_allowed_imports(self, caplog):
        """Should not warn for PythonCodeNode with allowed imports."""
        with patch("nexus.core.create_gateway") as mock_gw:
            mock_gw.return_value = Mock()
            from nexus import Nexus

            app = Nexus()

            from kailash.nodes.code.python import PythonCodeNode
            from kailash.workflow.builder import WorkflowBuilder

            node = PythonCodeNode(
                name="good_node",
                code="import json\nresult = json.dumps({'ok': True})",
                validate_security=False,
            )
            builder = WorkflowBuilder()
            builder.add_node_instance(node, "good_node")
            workflow = builder.build()

            import logging

            with caplog.at_level(logging.WARNING, logger="nexus.core"):
                app.register("good_workflow", workflow)

            sandbox_warnings = [
                msg for msg in caplog.messages if "not in the sandbox" in msg
            ]
            assert len(sandbox_warnings) == 0

    def test_warns_on_syntax_errors(self, caplog):
        """Should warn when PythonCodeNode has syntax errors."""
        with patch("nexus.core.create_gateway") as mock_gw:
            mock_gw.return_value = Mock()
            from nexus import Nexus

            app = Nexus()

            from kailash.nodes.code.python import PythonCodeNode
            from kailash.workflow.builder import WorkflowBuilder

            node = PythonCodeNode(
                name="syntax_node",
                code="def foo(:\n  pass",  # Invalid syntax
                validate_security=False,
            )
            builder = WorkflowBuilder()
            builder.add_node_instance(node, "syntax_node")
            workflow = builder.build()

            import logging

            with caplog.at_level(logging.WARNING, logger="nexus.core"):
                app.register("syntax_workflow", workflow)

            assert any("syntax error" in msg for msg in caplog.messages)

    def test_no_warning_for_handler_workflows(self, caplog):
        """HandlerNode workflows should not trigger sandbox warnings."""
        with patch("nexus.core.create_gateway") as mock_gw:
            mock_gw.return_value = Mock()
            from nexus import Nexus

            app = Nexus()

            import logging

            with caplog.at_level(logging.WARNING, logger="nexus.core"):

                @app.handler("clean_handler")
                async def clean(name: str) -> dict:
                    import subprocess  # This is in the handler, not PythonCodeNode

                    return {"name": name}

            sandbox_warnings = [
                msg for msg in caplog.messages if "not in the sandbox" in msg
            ]
            assert len(sandbox_warnings) == 0


class TestDuplicateHandlerDetection:
    """Tests for duplicate handler name detection (WS03 red team fix)."""

    def test_duplicate_handler_name_raises_value_error(self):
        """Registering a handler with the same name should raise ValueError."""
        with patch("nexus.core.create_gateway") as mock_gw:
            mock_gw.return_value = Mock()
            from nexus import Nexus

            app = Nexus()
            app.register_handler("my_handler", sample_handler)

            with pytest.raises(ValueError, match="already registered"):
                app.register_handler("my_handler", another_handler)

    def test_different_handler_names_succeed(self):
        """Handlers with different names should register without error."""
        with patch("nexus.core.create_gateway") as mock_gw:
            mock_gw.return_value = Mock()
            from nexus import Nexus

            app = Nexus()
            app.register_handler("handler_1", sample_handler)
            app.register_handler("handler_2", another_handler)

            assert "handler_1" in app._handler_registry
            assert "handler_2" in app._handler_registry

    def test_duplicate_via_decorator_raises(self):
        """Duplicate handler name via @app.handler() decorator should raise."""
        with patch("nexus.core.create_gateway") as mock_gw:
            mock_gw.return_value = Mock()
            from nexus import Nexus

            app = Nexus()

            @app.handler("greet")
            async def greet_v1(name: str) -> dict:
                return {"v": 1}

            with pytest.raises(ValueError, match="already registered"):

                @app.handler("greet")
                async def greet_v2(name: str) -> dict:
                    return {"v": 2}
