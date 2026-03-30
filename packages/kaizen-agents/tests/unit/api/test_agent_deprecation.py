"""Regression tests for Agent API deprecation and bug fixes."""

import warnings
import pytest
from unittest.mock import AsyncMock, MagicMock
from kaizen_agents.api.agent import Agent
from kaizen_agents.api.result import AgentResult


class TestAgentDeprecation:
    """Test that Agent is properly deprecated."""

    def test_agent_init_emits_deprecation_warning(self):
        """BUG-FIX: Agent.__init__ must emit DeprecationWarning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Agent(model="test-model")
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) >= 1
            assert "Delegate" in str(deprecation_warnings[0].message)


class TestAgentResultErrorMethod:
    """Test BUG-1 fix: AgentResult.from_error() called correctly."""

    def test_from_error_exists(self):
        """AgentResult.from_error() must exist as a classmethod."""
        assert hasattr(AgentResult, "from_error")
        assert callable(AgentResult.from_error)

    def test_from_error_returns_result(self):
        """AgentResult.from_error() must return an AgentResult."""
        result = AgentResult.from_error(
            error_message="test error",
            error_type="ValueError",
        )
        assert isinstance(result, AgentResult)
        assert result.error is not None


class TestNoSilentFabrication:
    """Test BUG-2 fix: No silent success on failure."""

    @pytest.mark.asyncio
    async def test_execute_single_propagates_errors(self):
        """_execute_single must NOT return fabricated success on exception."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            agent = Agent(model="test-model")

        context = {
            "task": "test task",
            "model": "test-model",
            "temperature": 0.7,
        }

        # Mock runtime to raise
        mock_runtime = MagicMock()
        mock_runtime.execute = AsyncMock(side_effect=RuntimeError("LLM failed"))

        result = await agent._execute_single(mock_runtime, context)

        # Must NOT contain the fabricated text (BUG-2 would return this)
        assert result.text != "Executed task: test task"
        # Must be an error result, not a fabricated success
        assert result.error is not None
        assert result.status.value == "error"


class TestRunSyncModern:
    """Test BUG-4 fix: run_sync uses modern asyncio API."""

    def test_run_sync_does_not_use_get_event_loop(self):
        """run_sync must not call asyncio.get_event_loop()."""
        import inspect

        source = inspect.getsource(Agent.run_sync)
        assert "get_event_loop" not in source
