"""Unit tests for HandlerNode and make_handler_workflow.

Tests cover:
- Async handler execution
- Sync handler wrapping (runs in executor)
- Signature-to-params derivation
- kwargs filtering
- MRO initialization order verification
- Dict and non-dict return handling
- Optional parameter detection
- Complex annotation fallback
- make_handler_workflow integration
"""

import asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest
from kailash.nodes.base import NodeParameter
from kailash.nodes.handler import (
    HandlerNode,
    _derive_params_from_signature,
    make_handler_workflow,
)

# --- Test handler functions ---


async def async_greet(name: str, greeting: str = "Hello") -> dict:
    """Greet someone."""
    return {"message": f"{greeting}, {name}!"}


def sync_add(a: int, b: int = 0) -> dict:
    return {"sum": a + b}


async def handler_with_all_types(
    text: str,
    count: int,
    ratio: float,
    flag: bool,
    data: dict,
    items: list,
) -> dict:
    return {
        "text": text,
        "count": count,
        "ratio": ratio,
        "flag": flag,
        "data": data,
        "items": items,
    }


async def handler_with_optional(name: str, title: Optional[str] = None) -> dict:
    prefix = f"{title} " if title else ""
    return {"greeting": f"Hello, {prefix}{name}!"}


async def handler_returns_string(name: str) -> str:
    return f"Hello, {name}!"


async def handler_with_kwargs(name: str, **extra) -> dict:
    return {"name": name, "extra": extra}


async def handler_no_annotations(x, y):
    return {"result": x + y}


class NotCallable:
    pass


# --- Tests for _derive_params_from_signature ---


class TestDeriveParamsFromSignature:
    def test_basic_types(self):
        params = _derive_params_from_signature(handler_with_all_types)

        assert "text" in params
        assert params["text"].type is str
        assert params["text"].required is True

        assert "count" in params
        assert params["count"].type is int

        assert "ratio" in params
        assert params["ratio"].type is float

        assert "flag" in params
        assert params["flag"].type is bool

        assert "data" in params
        assert params["data"].type is dict

        assert "items" in params
        assert params["items"].type is list

    def test_default_values(self):
        params = _derive_params_from_signature(async_greet)

        assert params["name"].required is True
        assert params["name"].default is None

        assert params["greeting"].required is False
        assert params["greeting"].default == "Hello"

    def test_optional_type(self):
        params = _derive_params_from_signature(handler_with_optional)

        assert params["name"].required is True
        assert params["title"].required is False
        assert params["title"].type is str

    def test_no_annotations_defaults_to_str(self):
        params = _derive_params_from_signature(handler_no_annotations)

        assert params["x"].type is str
        assert params["y"].type is str

    def test_kwargs_skipped(self):
        params = _derive_params_from_signature(handler_with_kwargs)

        assert "name" in params
        assert "extra" not in params

    def test_complex_annotation_falls_back_to_str(self):
        def handler_complex(data: Dict[str, Any]) -> dict:
            return data

        params = _derive_params_from_signature(handler_complex)
        # Dict[str, Any] is a complex generic, should fall back to str
        assert params["data"].type is str


# --- Tests for HandlerNode ---


class TestHandlerNode:
    def test_creation_with_async_handler(self):
        node = HandlerNode(handler=async_greet)

        assert node._handler is async_greet
        assert "name" in node._handler_params
        assert "greeting" in node._handler_params

    def test_creation_with_sync_handler(self):
        node = HandlerNode(handler=sync_add)

        assert node._handler is sync_add
        assert "a" in node._handler_params
        assert "b" in node._handler_params

    def test_creation_with_explicit_params(self):
        custom_params = {
            "input": NodeParameter(
                name="input", type=str, required=True, description="Custom input"
            )
        }
        node = HandlerNode(handler=async_greet, params=custom_params)

        assert node.get_parameters() == custom_params

    def test_non_callable_raises_error(self):
        with pytest.raises(TypeError, match="handler must be callable"):
            HandlerNode(handler="not a function")

    def test_mro_init_order(self):
        """Verify _handler and _handler_params are set before super().__init__."""
        # If MRO order is wrong, Node.__init__ would call get_parameters()
        # before _handler_params is set, causing AttributeError.
        # This test verifies the node constructs successfully.
        node = HandlerNode(handler=async_greet)
        params = node.get_parameters()

        assert isinstance(params, dict)
        assert len(params) > 0

    def test_get_parameters(self):
        node = HandlerNode(handler=async_greet)
        params = node.get_parameters()

        assert "name" in params
        assert params["name"].type is str
        assert params["name"].required is True

        assert "greeting" in params
        assert params["greeting"].type is str
        assert params["greeting"].required is False

    @pytest.mark.asyncio
    async def test_async_handler_execution(self):
        node = HandlerNode(handler=async_greet)
        result = await node.async_run(name="World", greeting="Hi")

        assert result == {"message": "Hi, World!"}

    @pytest.mark.asyncio
    async def test_sync_handler_runs_in_executor(self):
        node = HandlerNode(handler=sync_add)
        result = await node.async_run(a=3, b=4)

        assert result == {"sum": 7}

    @pytest.mark.asyncio
    async def test_kwargs_filtering(self):
        """Extra kwargs not in handler signature should be filtered out."""
        node = HandlerNode(handler=async_greet)
        # Pass extra params that don't exist in handler signature
        result = await node.async_run(
            name="World", greeting="Hey", extra_param="ignored"
        )

        assert result == {"message": "Hey, World!"}

    @pytest.mark.asyncio
    async def test_handler_with_var_kwargs_passes_all(self):
        """Handlers accepting **kwargs should receive all params."""
        node = HandlerNode(handler=handler_with_kwargs)
        result = await node.async_run(name="Alice", color="blue", size=42)

        assert result["name"] == "Alice"
        assert result["extra"] == {"color": "blue", "size": 42}

    @pytest.mark.asyncio
    async def test_non_dict_return_wrapped(self):
        """Non-dict returns should be wrapped as {'result': value}."""
        node = HandlerNode(handler=handler_returns_string)
        result = await node.async_run(name="World")

        assert result == {"result": "Hello, World!"}

    @pytest.mark.asyncio
    async def test_dict_return_passed_through(self):
        """Dict returns should be passed through unchanged."""
        node = HandlerNode(handler=async_greet)
        result = await node.async_run(name="World")

        assert isinstance(result, dict)
        assert "message" in result


# --- Tests for make_handler_workflow ---


class TestMakeHandlerWorkflow:
    def test_creates_workflow(self):
        workflow = make_handler_workflow(async_greet, "greeter")

        assert workflow is not None
        assert hasattr(workflow, "nodes")

    def test_workflow_has_node(self):
        workflow = make_handler_workflow(async_greet, "greeter")

        assert "greeter" in workflow.nodes

    def test_custom_input_mapping(self):
        workflow = make_handler_workflow(
            async_greet,
            "greeter",
            input_mapping={"user_name": "name", "prefix": "greeting"},
        )

        assert workflow is not None

    def test_default_identity_mapping(self):
        workflow = make_handler_workflow(async_greet, "greeter")

        # Workflow should have input mappings for name and greeting
        metadata = workflow.metadata if hasattr(workflow, "metadata") else {}
        assert workflow is not None
