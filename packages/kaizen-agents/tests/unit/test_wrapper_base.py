# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for WrapperBase — composition wrapper fundamentals.

Covers:
- Type validation (only BaseAgent instances accepted)
- Duplicate wrapper detection
- Canonical stack ordering enforcement
- Parameter/workflow proxy
- Inner/innermost access
"""

from __future__ import annotations

from typing import Any

import pytest

from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen_agents.wrapper_base import (
    DuplicateWrapperError,
    WrapperBase,
    WrapperOrderError,
)

# ---------------------------------------------------------------------------
# Helpers — minimal concrete agents for testing
# ---------------------------------------------------------------------------


class _StubAgent(BaseAgent):
    """Minimal concrete agent for wrapper tests."""

    def run(self, **inputs: Any) -> dict[str, Any]:
        return {"text": "stub-result"}

    async def run_async(self, **inputs: Any) -> dict[str, Any]:
        return {"text": "stub-result-async"}


class _ConcreteWrapper(WrapperBase):
    """A concrete wrapper subclass (not in the priority map)."""

    pass


def _make_agent(**overrides: Any) -> _StubAgent:
    config = BaseAgentConfig(**overrides)
    return _StubAgent(config=config, mcp_servers=[])


# ---------------------------------------------------------------------------
# Type validation
# ---------------------------------------------------------------------------


class TestTypeValidation:
    def test_rejects_non_base_agent(self) -> None:
        with pytest.raises(TypeError, match="WrapperBase requires a BaseAgent"):
            _ConcreteWrapper("not-an-agent")  # type: ignore[arg-type]

    def test_accepts_base_agent(self) -> None:
        agent = _make_agent()
        wrapper = _ConcreteWrapper(agent)
        assert wrapper._inner is agent


# ---------------------------------------------------------------------------
# Duplicate wrapper detection
# ---------------------------------------------------------------------------


class TestDuplicateDetection:
    def test_same_wrapper_type_twice_raises(self) -> None:
        agent = _make_agent()
        wrapped = _ConcreteWrapper(agent)
        with pytest.raises(DuplicateWrapperError, match="already present"):
            _ConcreteWrapper(wrapped)

    def test_different_wrapper_types_allowed(self) -> None:
        class _AnotherWrapper(WrapperBase):
            pass

        agent = _make_agent()
        first = _ConcreteWrapper(agent)
        second = _AnotherWrapper(first)
        assert second._inner is first


# ---------------------------------------------------------------------------
# Stack ordering
# ---------------------------------------------------------------------------


class TestStackOrdering:
    def test_governed_before_monitored_ok(self) -> None:
        from kailash.trust.envelope import ConstraintEnvelope
        from kaizen_agents.governed_agent import L3GovernedAgent
        from kaizen_agents.monitored_agent import MonitoredAgent

        agent = _make_agent()
        governed = L3GovernedAgent(agent, envelope=ConstraintEnvelope(), mcp_servers=[])
        monitored = MonitoredAgent(governed, mcp_servers=[])
        assert monitored._inner is governed

    def test_monitored_before_governed_raises(self) -> None:
        from kailash.trust.envelope import ConstraintEnvelope
        from kaizen_agents.governed_agent import L3GovernedAgent
        from kaizen_agents.monitored_agent import MonitoredAgent

        agent = _make_agent()
        monitored = MonitoredAgent(agent, mcp_servers=[])
        with pytest.raises(WrapperOrderError, match="Cannot apply"):
            L3GovernedAgent(monitored, envelope=ConstraintEnvelope(), mcp_servers=[])

    def test_streaming_on_top_ok(self) -> None:
        from kaizen_agents.monitored_agent import MonitoredAgent
        from kaizen_agents.streaming_agent import StreamingAgent

        agent = _make_agent()
        monitored = MonitoredAgent(agent, mcp_servers=[])
        streaming = StreamingAgent(monitored, mcp_servers=[])
        assert streaming._inner is monitored


# ---------------------------------------------------------------------------
# Proxy methods
# ---------------------------------------------------------------------------


class TestProxyMethods:
    def test_get_parameters_proxies(self) -> None:
        agent = _make_agent()
        wrapper = _ConcreteWrapper(agent)
        assert wrapper.get_parameters() == agent.get_parameters()

    def test_run_delegates(self) -> None:
        agent = _make_agent()
        wrapper = _ConcreteWrapper(agent)
        result = wrapper.run(prompt="test")
        assert result == {"text": "stub-result"}
        assert wrapper._inner_called is True

    async def test_run_async_delegates(self) -> None:
        agent = _make_agent()
        wrapper = _ConcreteWrapper(agent)
        result = await wrapper.run_async(prompt="test")
        assert result == {"text": "stub-result-async"}
        assert wrapper._inner_called is True


# ---------------------------------------------------------------------------
# Inner / innermost access
# ---------------------------------------------------------------------------


class TestInnerAccess:
    def test_inner_returns_direct_child(self) -> None:
        agent = _make_agent()
        wrapper = _ConcreteWrapper(agent)
        assert wrapper.inner is agent

    def test_innermost_walks_stack(self) -> None:
        class _Wrapper2(WrapperBase):
            pass

        agent = _make_agent()
        w1 = _ConcreteWrapper(agent)
        w2 = _Wrapper2(w1)
        assert w2.innermost is agent
        assert w2.inner is w1
