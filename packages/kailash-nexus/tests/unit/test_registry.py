# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for NTR-002: HandlerRegistry extraction.

Tests the HandlerRegistry, HandlerDef, and HandlerParam dataclasses
extracted from core.py into nexus/registry.py.
"""

import pytest

from nexus.registry import HandlerDef, HandlerParam, HandlerRegistry


# ---------------------------------------------------------------------------
# HandlerParam tests
# ---------------------------------------------------------------------------


class TestHandlerParam:
    """Tests for the HandlerParam dataclass."""

    def test_defaults(self):
        p = HandlerParam(name="x")
        assert p.name == "x"
        assert p.param_type == "string"
        assert p.required is True
        assert p.default is None
        assert p.description == ""

    def test_all_fields(self):
        p = HandlerParam(
            name="count",
            param_type="integer",
            required=False,
            default=10,
            description="Number of items",
        )
        assert p.name == "count"
        assert p.param_type == "integer"
        assert p.required is False
        assert p.default == 10
        assert p.description == "Number of items"

    def test_valid_param_types(self):
        """Verify all documented param_type values are accepted."""
        for pt in ("string", "integer", "float", "bool", "object", "array", "file"):
            p = HandlerParam(name="x", param_type=pt)
            assert p.param_type == pt


# ---------------------------------------------------------------------------
# HandlerDef tests
# ---------------------------------------------------------------------------


class TestHandlerDef:
    """Tests for the HandlerDef dataclass."""

    def test_defaults(self):
        hd = HandlerDef(name="greet")
        assert hd.name == "greet"
        assert hd.func is None
        assert hd.params == []
        assert hd.description == ""
        assert hd.tags == []
        assert hd.metadata == {}

    def test_with_func(self):
        def my_func():
            pass

        hd = HandlerDef(name="my_handler", func=my_func)
        assert hd.func is my_func

    def test_with_params(self):
        params = [
            HandlerParam(name="a", param_type="string"),
            HandlerParam(name="b", param_type="integer", required=False, default=0),
        ]
        hd = HandlerDef(name="test", params=params)
        assert len(hd.params) == 2
        assert hd.params[0].name == "a"
        assert hd.params[1].default == 0

    def test_with_tags_and_metadata(self):
        hd = HandlerDef(
            name="test",
            tags=["api", "public"],
            metadata={"version": 2},
        )
        assert hd.tags == ["api", "public"]
        assert hd.metadata == {"version": 2}


# ---------------------------------------------------------------------------
# HandlerRegistry tests
# ---------------------------------------------------------------------------


class TestHandlerRegistryWorkflows:
    """Tests for workflow registration in HandlerRegistry."""

    def test_register_workflow(self):
        reg = HandlerRegistry()
        wf = object()  # Workflow placeholder
        reg.register_workflow("my_wf", wf)
        assert reg.get_workflow("my_wf") is wf

    def test_get_workflow_missing(self):
        reg = HandlerRegistry()
        assert reg.get_workflow("nonexistent") is None

    def test_workflow_count(self):
        reg = HandlerRegistry()
        assert reg.workflow_count == 0
        reg.register_workflow("a", object())
        reg.register_workflow("b", object())
        assert reg.workflow_count == 2

    def test_list_workflows(self):
        reg = HandlerRegistry()
        wf1 = object()
        wf2 = object()
        reg.register_workflow("first", wf1)
        reg.register_workflow("second", wf2)
        listing = reg.list_workflows()
        assert listing == {"first": wf1, "second": wf2}

    def test_list_workflows_returns_copy(self):
        """Modifying the returned dict must not affect the registry."""
        reg = HandlerRegistry()
        reg.register_workflow("x", object())
        listing = reg.list_workflows()
        listing["injected"] = object()
        assert "injected" not in reg.list_workflows()

    def test_overwrite_workflow(self):
        reg = HandlerRegistry()
        wf1 = object()
        wf2 = object()
        reg.register_workflow("test", wf1)
        reg.register_workflow("test", wf2)
        assert reg.get_workflow("test") is wf2
        assert reg.workflow_count == 1


class TestHandlerRegistryHandlers:
    """Tests for handler registration in HandlerRegistry."""

    @staticmethod
    def _make_handler():
        async def greet(name: str, greeting: str = "Hello") -> dict:
            return {"message": f"{greeting}, {name}!"}

        return greet

    def test_register_handler_basic(self):
        reg = HandlerRegistry()
        func = self._make_handler()
        hd = reg.register_handler("greet", func, description="Greet a user")

        assert isinstance(hd, HandlerDef)
        assert hd.name == "greet"
        assert hd.func is func
        assert hd.description == "Greet a user"

    def test_register_handler_extracts_params(self):
        reg = HandlerRegistry()
        func = self._make_handler()
        hd = reg.register_handler("greet", func)

        assert len(hd.params) == 2
        assert hd.params[0].name == "name"
        assert hd.params[0].param_type == "string"
        assert hd.params[0].required is True
        assert hd.params[1].name == "greeting"
        assert hd.params[1].required is False
        assert hd.params[1].default == "Hello"

    def test_register_handler_duplicate_raises(self):
        reg = HandlerRegistry()
        func = self._make_handler()
        reg.register_handler("greet", func)
        with pytest.raises(ValueError, match="already registered"):
            reg.register_handler("greet", func)

    def test_get_handler(self):
        reg = HandlerRegistry()
        func = self._make_handler()
        reg.register_handler("greet", func)
        hd = reg.get_handler("greet")
        assert hd is not None
        assert hd.name == "greet"

    def test_get_handler_missing(self):
        reg = HandlerRegistry()
        assert reg.get_handler("missing") is None

    def test_handler_count(self):
        reg = HandlerRegistry()
        assert reg.handler_count == 0

        async def a():
            pass

        async def b():
            pass

        reg.register_handler("a", a)
        reg.register_handler("b", b)
        assert reg.handler_count == 2

    def test_list_handlers(self):
        reg = HandlerRegistry()

        async def handler1():
            pass

        async def handler2():
            pass

        reg.register_handler("first", handler1)
        reg.register_handler("second", handler2)
        listing = reg.list_handlers()
        assert len(listing) == 2
        names = {hd.name for hd in listing}
        assert names == {"first", "second"}

    def test_handler_with_tags_and_metadata(self):
        reg = HandlerRegistry()

        async def func():
            pass

        hd = reg.register_handler(
            "tagged",
            func,
            tags=["internal", "v2"],
            metadata={"version": 2, "owner": "team-a"},
        )
        assert hd.tags == ["internal", "v2"]
        assert hd.metadata == {"version": 2, "owner": "team-a"}

    def test_handler_with_workflow(self):
        """register_handler stores a workflow reference for backward compat."""
        reg = HandlerRegistry()

        async def func():
            pass

        wf = object()
        reg.register_handler("test", func, workflow=wf)
        compat_dict = reg._handler_funcs["test"]
        assert compat_dict["workflow"] is wf

    def test_handler_description_from_docstring(self):
        reg = HandlerRegistry()

        async def func():
            """This handler does something."""
            pass

        hd = reg.register_handler("doc", func)
        assert hd.description == "This handler does something."


class TestHandlerRegistryParamExtraction:
    """Tests for _extract_params static method."""

    def test_no_params(self):
        async def func():
            pass

        params = HandlerRegistry._extract_params(func)
        assert params == []

    def test_self_and_cls_excluded(self):
        class Dummy:
            def method(self, x: str):
                pass

            @classmethod
            def class_method(cls, y: int):
                pass

        params_inst = HandlerRegistry._extract_params(Dummy().method)
        assert len(params_inst) == 1
        assert params_inst[0].name == "x"

    def test_type_mapping(self):
        def func(a: str, b: int, c: float, d: bool, e: dict, f: list):
            pass

        params = HandlerRegistry._extract_params(func)
        types = {p.name: p.param_type for p in params}
        assert types == {
            "a": "string",
            "b": "integer",
            "c": "float",
            "d": "bool",
            "e": "object",
            "f": "array",
        }

    def test_unannotated_defaults_to_string(self):
        def func(x):
            pass

        params = HandlerRegistry._extract_params(func)
        assert params[0].param_type == "string"

    def test_required_and_default(self):
        def func(required_param: str, optional_param: str = "default"):
            pass

        params = HandlerRegistry._extract_params(func)
        assert params[0].required is True
        assert params[0].default is None
        assert params[1].required is False
        assert params[1].default == "default"

    def test_nexus_file_type(self):
        from nexus.files import NexusFile

        def func(upload: NexusFile):
            pass

        params = HandlerRegistry._extract_params(func)
        assert params[0].param_type == "file"


class TestHandlerRegistryEventBusIntegration:
    """Tests for EventBus integration in HandlerRegistry."""

    def test_no_event_bus(self):
        """Registry works without an EventBus."""
        reg = HandlerRegistry()

        async def func():
            pass

        hd = reg.register_handler("test", func)
        assert hd is not None

    def test_with_event_bus_publishes(self):
        """Registry publishes handler_registered events when EventBus is present."""
        published = []

        class FakeBus:
            def publish_handler_registered(self, name, handler_def):
                published.append((name, handler_def))

        reg = HandlerRegistry(event_bus=FakeBus())

        async def func():
            pass

        reg.register_handler("test", func)
        assert len(published) == 1
        assert published[0][0] == "test"
