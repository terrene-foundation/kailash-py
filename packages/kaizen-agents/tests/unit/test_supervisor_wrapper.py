# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for SupervisorWrapper.

Mocks are permitted at Tier 1 per rules/testing.md.  LLM routing is
mocked so the tests run without API keys.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen_agents.patterns.llm_routing import LLMBased
from kaizen_agents.supervisor_wrapper import SupervisorWrapper
from kaizen_agents.wrapper_base import WrapperBase


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _make_agent(agent_id: str = "test-agent") -> BaseAgent:
    """Create a minimal BaseAgent with mock provider for testing."""
    config = BaseAgentConfig(llm_provider="mock", model="mock-model")
    return BaseAgent(config=config, agent_id=agent_id, mcp_servers=[])


def _make_worker(agent_id: str, run_result: dict | None = None) -> BaseAgent:
    """Create a worker agent with a mocked run() return value."""
    agent = _make_agent(agent_id=agent_id)
    result = run_result or {"output": f"result from {agent_id}"}
    agent.run = MagicMock(return_value=result)
    agent.run_async = AsyncMock(return_value=result)
    return agent


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


class TestSupervisorWrapperIsWrapperBase:
    """SupervisorWrapper must be a WrapperBase subclass."""

    def test_is_wrapper_base_subclass(self):
        assert issubclass(SupervisorWrapper, WrapperBase)

    def test_isinstance_check(self):
        inner = _make_agent("inner")
        wrapper = SupervisorWrapper(inner, workers=[])
        assert isinstance(wrapper, WrapperBase)
        assert isinstance(wrapper, BaseAgent)


class TestSupervisorWrapperDelegation:
    """SupervisorWrapper delegates to workers via LLM routing."""

    def test_delegates_to_worker(self):
        inner = _make_agent("inner")
        inner.run = MagicMock(return_value={"output": "inner result"})

        worker = _make_worker("worker-1", {"output": "worker result"})

        # Mock LLM routing to select the worker
        with patch.object(
            LLMBased,
            "select_best",
            new_callable=AsyncMock,
            return_value=worker,
        ):
            wrapper = SupervisorWrapper(inner, workers=[worker])
            result = wrapper.run(task="translate this")

        assert result == {"output": "worker result"}
        worker.run.assert_called_once_with(task="translate this")
        # Inner agent should NOT have been called
        inner.run.assert_not_called()

    def test_falls_back_to_inner_when_no_workers(self):
        inner = _make_agent("inner")
        inner.run = MagicMock(return_value={"output": "inner result"})

        wrapper = SupervisorWrapper(inner, workers=[])
        result = wrapper.run(task="do something")

        assert result == {"output": "inner result"}
        inner.run.assert_called_once_with(task="do something")

    def test_falls_back_to_inner_when_routing_returns_none(self):
        inner = _make_agent("inner")
        inner.run = MagicMock(return_value={"output": "inner result"})
        worker = _make_worker("worker-1")

        with patch.object(
            LLMBased,
            "select_best",
            new_callable=AsyncMock,
            return_value=None,
        ):
            wrapper = SupervisorWrapper(inner, workers=[worker])
            result = wrapper.run(task="do something")

        assert result == {"output": "inner result"}
        inner.run.assert_called_once()


class TestSupervisorWrapperAsync:
    """Async delegation works correctly."""

    @pytest.mark.asyncio
    async def test_async_delegates_to_worker(self):
        inner = _make_agent("inner")
        inner.run_async = AsyncMock(return_value={"output": "inner result"})

        worker = _make_worker("worker-1", {"output": "async worker result"})

        with patch.object(
            LLMBased,
            "select_best",
            new_callable=AsyncMock,
            return_value=worker,
        ):
            wrapper = SupervisorWrapper(inner, workers=[worker])
            result = await wrapper.run_async(task="translate this")

        assert result == {"output": "async worker result"}
        worker.run_async.assert_called_once_with(task="translate this")


class TestSupervisorWrapperRouting:
    """SupervisorWrapper uses LLM routing when configured."""

    def test_accepts_custom_routing(self):
        inner = _make_agent("inner")
        routing = LLMBased()
        wrapper = SupervisorWrapper(inner, workers=[], routing=routing)
        assert wrapper._routing is routing

    def test_creates_default_routing_when_none(self):
        inner = _make_agent("inner")
        wrapper = SupervisorWrapper(inner, workers=[])
        assert isinstance(wrapper._routing, LLMBased)

    def test_workers_property_returns_copy(self):
        inner = _make_agent("inner")
        w1 = _make_worker("w1")
        w2 = _make_worker("w2")
        wrapper = SupervisorWrapper(inner, workers=[w1, w2])
        workers = wrapper.workers
        assert len(workers) == 2
        assert workers[0] is w1
        assert workers[1] is w2
        # Returned list is a copy, not the internal list
        workers.append(_make_worker("w3"))
        assert len(wrapper.workers) == 2


class TestSupervisorWrapperTaskExtraction:
    """_extract_task_text finds the right field from inputs."""

    def test_extracts_task_field(self):
        assert SupervisorWrapper._extract_task_text({"task": "hello"}) == "hello"

    def test_extracts_query_field(self):
        assert SupervisorWrapper._extract_task_text({"query": "search"}) == "search"

    def test_extracts_request_field(self):
        assert SupervisorWrapper._extract_task_text({"request": "do it"}) == "do it"

    def test_falls_back_to_joined_values(self):
        result = SupervisorWrapper._extract_task_text({"a": "hello", "b": "world"})
        assert "hello" in result
        assert "world" in result

    def test_empty_inputs(self):
        assert SupervisorWrapper._extract_task_text({}) == ""
