# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for governance decorators -- @governed_tool.

Covers:
- TODO 7032: @governed_tool decorator marks functions as governance-aware
- TODO 7033: Decorated functions carry governance metadata
- Decorated functions remain callable
- Metadata attributes are preserved through wrapping
- Integration with PactGovernedAgent auto-registration
"""

from __future__ import annotations

import pytest

from pact.governance.decorators import governed_tool


# ---------------------------------------------------------------------------
# Basic Decorator Tests
# ---------------------------------------------------------------------------


class TestGovernedToolDecorator:
    """@governed_tool marks functions as governance-aware."""

    def test_decorated_function_is_callable(self) -> None:
        """A decorated function should still be callable."""

        @governed_tool("read_data")
        def read_data(query: str) -> str:
            return f"result for {query}"

        result = read_data("test")
        assert result == "result for test"

    def test_decorated_function_has_governed_flag(self) -> None:
        """Decorated function should have _governed = True."""

        @governed_tool("write_report")
        def write_report(content: str) -> str:
            return f"wrote: {content}"

        assert hasattr(write_report, "_governed")
        assert write_report._governed is True

    def test_decorated_function_has_action_name(self) -> None:
        """Decorated function should carry the governance action name."""

        @governed_tool("send_email", cost=2.0)
        def send_email(to: str, body: str) -> str:
            return f"sent to {to}"

        assert hasattr(send_email, "_governance_action")
        assert send_email._governance_action == "send_email"

    def test_decorated_function_has_cost(self) -> None:
        """Decorated function should carry the governance cost."""

        @governed_tool("expensive_op", cost=50.0)
        def expensive_op() -> str:
            return "done"

        assert hasattr(send := expensive_op, "_governance_cost")
        assert expensive_op._governance_cost == 50.0

    def test_default_cost_is_zero(self) -> None:
        """Default cost should be 0.0 when not specified."""

        @governed_tool("cheap_op")
        def cheap_op() -> str:
            return "done"

        assert cheap_op._governance_cost == 0.0

    def test_decorated_function_has_resource(self) -> None:
        """Decorated function should carry the governance resource."""

        @governed_tool("access_data", resource="budget-reports")
        def access_data() -> str:
            return "data"

        assert hasattr(access_data, "_governance_resource")
        assert access_data._governance_resource == "budget-reports"

    def test_default_resource_is_none(self) -> None:
        """Default resource should be None when not specified."""

        @governed_tool("basic_op")
        def basic_op() -> str:
            return "done"

        assert basic_op._governance_resource is None

    def test_preserves_function_name(self) -> None:
        """Decorated function should preserve __name__ via functools.wraps."""

        @governed_tool("my_action")
        def my_function(x: int) -> int:
            return x * 2

        assert my_function.__name__ == "my_function"

    def test_preserves_function_docstring(self) -> None:
        """Decorated function should preserve __doc__ via functools.wraps."""

        @governed_tool("my_action")
        def my_function() -> str:
            """This function does something."""
            return "done"

        assert my_function.__doc__ == "This function does something."

    def test_preserves_return_value(self) -> None:
        """Decorated function should pass through return values unchanged."""

        @governed_tool("compute", cost=1.0)
        def compute(a: int, b: int) -> int:
            return a + b

        assert compute(3, 4) == 7

    def test_preserves_kwargs(self) -> None:
        """Decorated function should accept and pass through kwargs."""

        @governed_tool("format_text")
        def format_text(text: str, *, uppercase: bool = False) -> str:
            return text.upper() if uppercase else text

        assert format_text("hello", uppercase=True) == "HELLO"
        assert format_text("hello") == "hello"


# ---------------------------------------------------------------------------
# Multiple Decorators
# ---------------------------------------------------------------------------


class TestMultipleDecorators:
    """Multiple functions can be decorated with different action names."""

    def test_multiple_decorated_functions_independent(self) -> None:
        """Each decorated function should have its own independent metadata."""

        @governed_tool("action_a", cost=10.0, resource="res-a")
        def func_a() -> str:
            return "a"

        @governed_tool("action_b", cost=20.0, resource="res-b")
        def func_b() -> str:
            return "b"

        assert func_a._governance_action == "action_a"
        assert func_a._governance_cost == 10.0
        assert func_a._governance_resource == "res-a"

        assert func_b._governance_action == "action_b"
        assert func_b._governance_cost == 20.0
        assert func_b._governance_resource == "res-b"


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases for the decorator."""

    def test_decorator_on_lambda_like(self) -> None:
        """Decorator should work on simple functions."""

        @governed_tool("noop")
        def noop() -> None:
            pass

        assert noop._governed is True
        assert noop() is None

    def test_decorator_with_exception_in_function(self) -> None:
        """If the underlying function raises, the exception should propagate."""

        @governed_tool("risky_op")
        def risky_op() -> None:
            raise ValueError("something went wrong")

        with pytest.raises(ValueError, match="something went wrong"):
            risky_op()

        # But metadata should still be present
        assert risky_op._governed is True
        assert risky_op._governance_action == "risky_op"
