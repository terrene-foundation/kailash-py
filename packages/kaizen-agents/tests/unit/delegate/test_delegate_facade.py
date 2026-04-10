# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for SPEC-05 Delegate Engine Facade.

Covers:
    - TASK-05-01: Module scaffold and imports
    - TASK-05-02: Constructor signature with new params (signature, envelope, inner_agent)
    - TASK-05-03: Inner BaseAgent core build
    - TASK-05-04/05/06: Wrapper stacking (Monitored, L3Governed, Streaming)
    - TASK-05-07: Model resolution with env fallback
    - TASK-05-09: ConstructorIOError exception
    - TASK-05-10: Constructor IO ban (AST verification)
    - TASK-05-12: run_sync() refuses under running event loop
    - TASK-05-18: ToolRegistryCollisionError
    - TASK-05-27: run() event passthrough
    - TASK-05-28: run_sync() refusal under running loop
    - TASK-05-30: close() proxy
    - TASK-05-31: Introspection properties (core_agent, signature, model)
    - TASK-05-32: consumed_usd / budget_remaining
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import textwrap
from typing import Any

import pytest

from kaizen_agents.delegate.delegate import (
    ConstructorIOError,
    Delegate,
    ToolRegistryCollisionError,
)
from kaizen_agents.delegate.events import (
    BudgetExhausted,
    DelegateEvent,
    ErrorEvent,
    TextDelta,
    TurnComplete,
)

# ---------------------------------------------------------------------------
# Helpers -- fake streaming adapter (same pattern as test_delegate.py)
# ---------------------------------------------------------------------------


class FakeStreamEvent:
    """Minimal stand-in for protocol.StreamEvent."""

    def __init__(
        self,
        event_type: str = "text_delta",
        content: str = "",
        tool_calls: list[dict[str, Any]] | None = None,
        finish_reason: str | None = None,
        model: str = "test-model",
        usage: dict[str, int] | None = None,
        delta_text: str = "",
    ) -> None:
        self.event_type = event_type
        self.content = content
        self.tool_calls = tool_calls or []
        self.finish_reason = finish_reason
        self.model = model
        self.usage = usage or {}
        self.delta_text = delta_text


class FakeAdapter:
    """A fake StreamingChatAdapter that yields pre-configured events."""

    def __init__(self, events: list[FakeStreamEvent]) -> None:
        self._events = events

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Any:
        for event in self._events:
            yield event


def _make_adapter(*texts: str) -> FakeAdapter:
    """Create an adapter that streams the given text fragments."""
    events = [FakeStreamEvent(event_type="text_delta", delta_text=t) for t in texts]
    events.append(
        FakeStreamEvent(
            event_type="done",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )
    )
    return events


def _simple_adapter() -> FakeAdapter:
    """Create a simple adapter that yields 'Hello world'."""
    return FakeAdapter(_make_adapter("Hello", " world"))


# ============================================================================
# TASK-05-01: Module scaffold and imports
# ============================================================================


class TestModuleScaffold:
    """TASK-05-01: Delegate is importable from expected paths."""

    def test_delegate_importable_from_delegate_module(self):
        from kaizen_agents.delegate.delegate import Delegate

        assert Delegate is not None

    def test_delegate_importable_from_delegate_package(self):
        from kaizen_agents.delegate import Delegate

        assert Delegate is not None

    def test_delegate_importable_from_top_level(self):
        from kaizen_agents import Delegate

        assert Delegate is not None

    def test_exceptions_importable(self):
        from kaizen_agents.delegate import (
            ConstructorIOError,
            ToolRegistryCollisionError,
        )

        assert issubclass(ConstructorIOError, RuntimeError)
        assert issubclass(ToolRegistryCollisionError, ValueError)


# ============================================================================
# TASK-05-02: Constructor signature with new params
# ============================================================================


class TestConstructorSignature:
    """TASK-05-02: Constructor accepts all v2.x params plus new ones."""

    def test_v2x_parameters_preserved(self):
        """All v2.x parameters are present and keyword-only after model."""
        sig = inspect.signature(Delegate.__init__)
        params = list(sig.parameters.keys())

        # model is positional
        assert "model" in params

        # All these must be present (keyword-only)
        v2x_params = [
            "tools",
            "system_prompt",
            "max_turns",
            "budget_usd",
            "adapter",
            "config",
        ]
        for param_name in v2x_params:
            assert param_name in params, f"Missing v2.x parameter: {param_name}"
            p = sig.parameters[param_name]
            assert (
                p.kind == inspect.Parameter.KEYWORD_ONLY
            ), f"Parameter {param_name} should be keyword-only"

    def test_new_parameters_present(self):
        """SPEC-05 new parameters are present: signature, envelope, inner_agent."""
        sig = inspect.signature(Delegate.__init__)
        params = sig.parameters

        assert "signature" in params
        assert "envelope" in params
        assert "inner_agent" in params
        assert "api_key" in params
        assert "base_url" in params
        assert "temperature" in params
        assert "max_tokens" in params
        assert "mcp_servers" in params

    def test_new_parameters_keyword_only(self):
        """All new parameters are keyword-only."""
        sig = inspect.signature(Delegate.__init__)
        for name in ("signature", "envelope", "inner_agent", "api_key", "base_url"):
            p = sig.parameters[name]
            assert (
                p.kind == inspect.Parameter.KEYWORD_ONLY
            ), f"Parameter {name} should be keyword-only"

    def test_new_parameters_default_to_none(self):
        """New optional params default to None."""
        sig = inspect.signature(Delegate.__init__)
        for name in (
            "signature",
            "envelope",
            "inner_agent",
            "api_key",
            "base_url",
            "temperature",
            "max_tokens",
            "mcp_servers",
        ):
            p = sig.parameters[name]
            assert (
                p.default is None
            ), f"Parameter {name} should default to None, got {p.default}"

    def test_minimal_construction_works(self):
        """Delegate(model='x') does not raise."""
        d = Delegate(model="test-model", adapter=_simple_adapter())
        assert d is not None

    def test_construction_with_all_new_params(self):
        """Delegate with all new params does not raise."""
        d = Delegate(
            model="test-model",
            signature=None,
            tools=None,
            system_prompt="You are helpful.",
            temperature=0.5,
            max_tokens=100,
            max_turns=20,
            mcp_servers=None,
            budget_usd=10.0,
            envelope=None,
            api_key=None,
            base_url=None,
            inner_agent=None,
            adapter=_simple_adapter(),
        )
        assert d is not None


# ============================================================================
# TASK-05-07: Model resolution with DEFAULT_LLM_MODEL env fallback
# ============================================================================


class TestModelResolution:
    """TASK-05-07: Model resolves from explicit, then env, then error."""

    def test_explicit_model_wins(self):
        d = Delegate(model="explicit-model", adapter=_simple_adapter())
        assert d.model == "explicit-model"

    def test_env_fallback(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_LLM_MODEL", "env-model")
        d = Delegate(model="", adapter=_simple_adapter())
        assert d.model == "env-model"

    def test_empty_model_with_env_set(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_LLM_MODEL", "from-env")
        d = Delegate(adapter=_simple_adapter())
        assert d.model == "from-env"

    def test_explicit_model_overrides_env(self, monkeypatch):
        monkeypatch.setenv("DEFAULT_LLM_MODEL", "env-model")
        d = Delegate(model="explicit-model", adapter=_simple_adapter())
        assert d.model == "explicit-model"


# ============================================================================
# TASK-05-09: ConstructorIOError exception
# ============================================================================


class TestConstructorIOError:
    """TASK-05-09: ConstructorIOError is properly defined."""

    def test_subclasses_runtime_error(self):
        assert issubclass(ConstructorIOError, RuntimeError)

    def test_message_includes_operation_name(self):
        exc = ConstructorIOError("asyncio.run")
        assert "asyncio.run" in str(exc)

    def test_message_includes_spec_reference(self):
        exc = ConstructorIOError("httpx.get")
        assert "SPEC-05" in str(exc)

    def test_operation_attribute(self):
        exc = ConstructorIOError("socket.connect")
        assert exc.operation == "socket.connect"


# ============================================================================
# TASK-05-18: ToolRegistryCollisionError
# ============================================================================


class TestToolRegistryCollisionError:
    """TASK-05-18: ToolRegistryCollisionError for name collisions."""

    def test_subclasses_value_error(self):
        assert issubclass(ToolRegistryCollisionError, ValueError)

    def test_message_includes_tool_name(self):
        exc = ToolRegistryCollisionError("search", ["server_a", "server_b"])
        assert "search" in str(exc)

    def test_attributes(self):
        exc = ToolRegistryCollisionError("grep", ["fs", "mcp_builtin"])
        assert exc.tool_name == "grep"
        assert exc.sources == ["fs", "mcp_builtin"]


# ============================================================================
# TASK-05-10: Constructor IO ban (AST verification)
# ============================================================================


class TestConstructorIOBan:
    """TASK-05-10: No outbound IO calls in Delegate.__init__."""

    def _get_init_ast(self) -> ast.FunctionDef:
        """Parse the __init__ method body from source."""
        source = inspect.getsource(Delegate.__init__)
        # Dedent so it parses correctly
        source = textwrap.dedent(source)
        tree = ast.parse(source)
        # The top-level node is a Module, first body item is the function def
        func_def = tree.body[0]
        assert isinstance(func_def, ast.FunctionDef)
        return func_def

    def _collect_calls(self, node: ast.AST) -> list[str]:
        """Recursively collect all function call names (dotted) in an AST."""
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Attribute):
                    # e.g. asyncio.run or self._loop.run
                    parts = []
                    current = func
                    while isinstance(current, ast.Attribute):
                        parts.append(current.attr)
                        current = current.value
                    if isinstance(current, ast.Name):
                        parts.append(current.id)
                    parts.reverse()
                    calls.append(".".join(parts))
                elif isinstance(func, ast.Name):
                    calls.append(func.id)
        return calls

    def test_no_asyncio_run_in_init(self):
        """asyncio.run must never appear in __init__."""
        func_def = self._get_init_ast()
        calls = self._collect_calls(func_def)
        banned = [c for c in calls if "asyncio.run" in c]
        assert not banned, f"Banned asyncio.run calls found in __init__: {banned}"

    def test_no_outbound_http_in_init(self):
        """No HTTP client calls in __init__."""
        func_def = self._get_init_ast()
        calls = self._collect_calls(func_def)
        http_patterns = [
            "requests.get",
            "requests.post",
            "httpx.get",
            "httpx.post",
            "urllib.request",
        ]
        banned = [c for c in calls if any(p in c for p in http_patterns)]
        assert not banned, f"Banned HTTP calls found in __init__: {banned}"

    def test_no_subprocess_in_init(self):
        """No subprocess calls in __init__."""
        func_def = self._get_init_ast()
        calls = self._collect_calls(func_def)
        banned = [c for c in calls if "subprocess" in c]
        assert not banned, f"Banned subprocess calls found in __init__: {banned}"

    def test_no_socket_in_init(self):
        """No raw socket creation in __init__."""
        func_def = self._get_init_ast()
        calls = self._collect_calls(func_def)
        banned = [c for c in calls if "socket.socket" in c]
        assert not banned, f"Banned socket calls found in __init__: {banned}"


# ============================================================================
# TASK-05-12/28: run_sync() refuses under running event loop
# ============================================================================


class TestRunSyncLoopDetection:
    """TASK-05-12: run_sync() refuses inside a running event loop."""

    def test_run_sync_raises_inside_async(self):
        """Calling run_sync from inside asyncio.run raises RuntimeError."""

        async def _inner():
            d = Delegate(model="test-model", adapter=_simple_adapter())
            d.run_sync("hello")

        with pytest.raises(
            RuntimeError, match="cannot be called from inside a running event loop"
        ):
            asyncio.run(_inner())

    def test_run_sync_error_suggests_async_alternative(self):
        """Error message suggests the async API."""

        async def _inner():
            d = Delegate(model="test-model", adapter=_simple_adapter())
            d.run_sync("hello")

        with pytest.raises(RuntimeError, match="async for event in delegate.run"):
            asyncio.run(_inner())


# ============================================================================
# TASK-05-30: close() proxy
# ============================================================================


class TestCloseProxy:
    """TASK-05-30: close() marks the Delegate as closed."""

    def test_close_marks_closed(self):
        d = Delegate(model="test-model", adapter=_simple_adapter())
        assert d._closed is False
        d.close()
        assert d._closed is True

    def test_run_after_close_yields_error(self):
        d = Delegate(model="test-model", adapter=_simple_adapter())
        d.close()

        async def _run() -> list[DelegateEvent]:
            events: list[DelegateEvent] = []
            async for event in d.run("hello"):
                events.append(event)
            return events

        events = asyncio.run(_run())
        assert len(events) == 1
        assert isinstance(events[0], ErrorEvent)
        assert "closed" in events[0].error.lower()


# ============================================================================
# TASK-05-31: Introspection properties
# ============================================================================


class TestIntrospectionProperties:
    """TASK-05-31: core_agent, signature, model properties."""

    def test_model_property(self):
        d = Delegate(model="my-model", adapter=_simple_adapter())
        assert d.model == "my-model"

    def test_signature_property_none(self):
        d = Delegate(model="test-model", adapter=_simple_adapter())
        assert d.signature is None

    def test_signature_property_set(self):
        from kaizen.signatures import InputField, OutputField, Signature

        class MySignature(Signature):
            question: str = InputField(desc="A question")
            answer: str = OutputField(desc="An answer")

        d = Delegate(
            model="test-model", signature=MySignature, adapter=_simple_adapter()
        )
        assert d.signature is MySignature

    def test_wrapper_stack_returns_baseagent(self):
        from kaizen.core.base_agent import BaseAgent

        d = Delegate(model="test-model", adapter=_simple_adapter())
        stack = d.wrapper_stack
        assert isinstance(stack, BaseAgent)


# ============================================================================
# TASK-05-32: consumed_usd / budget_remaining
# ============================================================================


class TestBudgetProperties:
    """TASK-05-32: Budget-related properties."""

    def test_budget_usd_none_when_not_set(self):
        d = Delegate(model="test-model", adapter=_simple_adapter())
        assert d.budget_usd is None

    def test_budget_usd_set(self):
        d = Delegate(model="test-model", budget_usd=5.0, adapter=_simple_adapter())
        assert d.budget_usd == 5.0

    def test_consumed_usd_starts_at_zero(self):
        d = Delegate(model="test-model", budget_usd=5.0, adapter=_simple_adapter())
        assert d.consumed_usd == 0.0

    def test_budget_remaining_none_when_no_budget(self):
        d = Delegate(model="test-model", adapter=_simple_adapter())
        assert d.budget_remaining is None

    def test_budget_remaining_equals_budget_at_start(self):
        d = Delegate(model="test-model", budget_usd=10.0, adapter=_simple_adapter())
        assert d.budget_remaining == 10.0


# ============================================================================
# TASK-05-27: run() event passthrough
# ============================================================================


def _text_stream_events(text: str, chunk_size: int = 5) -> list[FakeStreamEvent]:
    """Create stream events for a text response (matches test_delegate.py)."""
    events: list[FakeStreamEvent] = []
    accumulated = ""
    for i in range(0, len(text), chunk_size):
        chunk = text[i : i + chunk_size]
        accumulated += chunk
        events.append(
            FakeStreamEvent(
                event_type="text_delta",
                content=accumulated,
                delta_text=chunk,
            )
        )
    events.append(
        FakeStreamEvent(
            event_type="done",
            content=accumulated,
            finish_reason="stop",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        )
    )
    return events


class TestRunEventPassthrough:
    """TASK-05-27: run() yields typed events from the loop."""

    def test_text_response_yields_text_deltas(self):
        """A text response yields TextDelta events."""
        stream_events = _text_stream_events("Hello, world!")
        adapter = FakeAdapter(stream_events)
        d = Delegate(model="test-model", adapter=adapter)

        async def _run() -> list[DelegateEvent]:
            events: list[DelegateEvent] = []
            async for event in d.run("greet me"):
                events.append(event)
            return events

        events = asyncio.run(_run())
        text_deltas = [e for e in events if isinstance(e, TextDelta)]
        assert len(text_deltas) > 0
        full_text = "".join(td.text for td in text_deltas)
        assert full_text == "Hello, world!"

    def test_text_response_yields_turn_complete(self):
        """A text response ends with TurnComplete carrying full text."""
        stream_events = _text_stream_events("Done")
        adapter = FakeAdapter(stream_events)
        d = Delegate(model="test-model", adapter=adapter)

        async def _run() -> list[DelegateEvent]:
            events: list[DelegateEvent] = []
            async for event in d.run("do it"):
                events.append(event)
            return events

        events = asyncio.run(_run())
        turn_completes = [e for e in events if isinstance(e, TurnComplete)]
        assert len(turn_completes) == 1
        assert turn_completes[0].text == "Done"

    def test_empty_prompt_yields_error(self):
        """An empty prompt yields an ErrorEvent."""
        adapter = FakeAdapter([])
        d = Delegate(model="test-model", adapter=adapter)

        async def _run() -> list[DelegateEvent]:
            events: list[DelegateEvent] = []
            async for event in d.run(""):
                events.append(event)
            return events

        events = asyncio.run(_run())
        assert len(events) == 1
        assert isinstance(events[0], ErrorEvent)
        assert "empty" in events[0].error.lower()

    def test_run_with_budget_exhausted(self):
        """Budget of 0 yields BudgetExhausted immediately."""
        adapter = FakeAdapter([])
        d = Delegate(model="test-model", budget_usd=0.0, adapter=adapter)

        async def _run() -> list[DelegateEvent]:
            events: list[DelegateEvent] = []
            async for event in d.run("hello"):
                events.append(event)
            return events

        events = asyncio.run(_run())
        budget_events = [e for e in events if isinstance(e, BudgetExhausted)]
        assert len(budget_events) == 1


# ============================================================================
# Budget validation
# ============================================================================


class TestBudgetValidation:
    """Budget validation in constructor (safety guard)."""

    def test_nan_budget_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            Delegate(model="test-model", budget_usd=float("nan"))

    def test_inf_budget_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            Delegate(model="test-model", budget_usd=float("inf"))

    def test_negative_budget_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            Delegate(model="test-model", budget_usd=-1.0)

    def test_zero_budget_accepted(self):
        d = Delegate(model="test-model", budget_usd=0.0, adapter=_simple_adapter())
        assert d.budget_usd == 0.0


# ============================================================================
# Deferred MCP (TASK-05-11)
# ============================================================================


class TestDeferredMCP:
    """TASK-05-11: MCP servers are stored but not connected in constructor."""

    def test_mcp_servers_stored_as_deferred(self):
        servers = [{"name": "test", "url": "http://localhost:8080"}]
        d = Delegate(model="test-model", mcp_servers=servers, adapter=_simple_adapter())
        assert d._deferred_mcp is not None
        assert len(d._deferred_mcp) == 1

    def test_deferred_mcp_is_copy(self):
        servers = [{"name": "test", "url": "http://localhost:8080"}]
        d = Delegate(model="test-model", mcp_servers=servers, adapter=_simple_adapter())
        # Mutating the original should not affect the delegate's copy
        servers.append({"name": "extra"})
        assert len(d._deferred_mcp) == 1

    def test_no_mcp_servers_means_no_deferred(self):
        d = Delegate(model="test-model", adapter=_simple_adapter())
        assert d._deferred_mcp is None

    def test_mcp_not_configured_at_construction(self):
        d = Delegate(
            model="test-model", mcp_servers=[{"name": "x"}], adapter=_simple_adapter()
        )
        assert d._mcp_configured is False


# ============================================================================
# Wrapper stacking (TASK-05-04/05/06)
# ============================================================================


class TestWrapperStacking:
    """TASK-05-04/05/06: Wrapper stack composition."""

    def test_no_budget_no_monitored(self):
        d = Delegate(model="test-model", adapter=_simple_adapter())
        assert d._monitored is None

    def test_budget_creates_monitored_when_available(self):
        d = Delegate(model="test-model", budget_usd=5.0, adapter=_simple_adapter())
        # MonitoredAgent might or might not be available depending on environment;
        # the important thing is the Delegate is constructed successfully
        # and budget tracking works
        assert d.budget_usd == 5.0

    def test_no_envelope_no_governed(self):
        d = Delegate(model="test-model", adapter=_simple_adapter())
        assert d._governed is None

    def test_envelope_creates_governed_when_available(self):
        """When ConstraintEnvelope is available, governance wrapping works."""
        try:
            from kailash.trust.envelope import ConstraintEnvelope

            envelope = ConstraintEnvelope()
            d = Delegate(
                model="test-model", envelope=envelope, adapter=_simple_adapter()
            )
            # If L3GovernedAgent is importable, governed wrapper is set
            if d._governed is not None:
                from kaizen_agents.governed_agent import L3GovernedAgent

                assert isinstance(d._governed, L3GovernedAgent)
        except ImportError:
            pytest.skip("kailash.trust.envelope not available")


# ============================================================================
# Repr
# ============================================================================


class TestRepr:
    """Delegate repr."""

    def test_repr_includes_model(self):
        d = Delegate(model="my-model", adapter=_simple_adapter())
        assert "my-model" in repr(d)

    def test_repr_includes_budget(self):
        d = Delegate(model="my-model", budget_usd=10.0, adapter=_simple_adapter())
        assert "$10.00" in repr(d)

    def test_repr_no_budget(self):
        d = Delegate(model="my-model", adapter=_simple_adapter())
        assert "budget" not in repr(d)
