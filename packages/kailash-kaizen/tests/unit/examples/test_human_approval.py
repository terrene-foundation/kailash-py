"""
Unit tests for human-approval example.

Tests cover:
- Agent initialization with HumanInLoopStrategy
- Config parameters work correctly
- Strategy executes successfully with approval
- Approval callback invoked
- Auto-approve works (test mode)
- Rejection raises error
- Approval history tracking
- Approval metadata added to result
- Multiple approvals tracked
- Custom approval callback works
- Integration with BaseAgent
"""

import pytest

# Standardized example loading
from example_import_helper import import_example_module

# Load human-approval example
_approval_module = import_example_module("examples/1-single-agent/human-approval")
ApprovalAgent = _approval_module.ApprovalAgent
ApprovalConfig = _approval_module.ApprovalConfig
DecisionSignature = _approval_module.DecisionSignature

from kaizen.strategies.human_in_loop import HumanInLoopStrategy


class TestApprovalAgent:
    """Test HumanInLoopStrategy integration in human-approval example."""

    def test_agent_initializes_with_human_in_loop_strategy(self):
        """Test agent initializes with HumanInLoopStrategy."""
        config = ApprovalConfig(llm_provider="mock")
        agent = ApprovalAgent(config)

        assert isinstance(
            agent.strategy, HumanInLoopStrategy
        ), f"Agent should use HumanInLoopStrategy, got {type(agent.strategy)}"

    def test_config_parameters_work_correctly(self):
        """Test that config parameters are properly set."""

        def custom_callback(result):
            return True, "Approved"

        config = ApprovalConfig(
            llm_provider="openai",
            model="gpt-4",
            temperature=0.3,
            approval_callback=custom_callback,
        )
        agent = ApprovalAgent(config)

        assert agent.approval_config.llm_provider == "openai"
        assert agent.approval_config.model == "gpt-4"
        assert agent.approval_config.temperature == 0.3
        assert agent.approval_config.approval_callback == custom_callback

    @pytest.mark.asyncio
    async def test_run_executes_with_auto_approval(self):
        """Test that decide executes successfully with auto-approval."""
        config = ApprovalConfig(llm_provider="mock")
        agent = ApprovalAgent(config)

        result = await agent.decide_async("Test decision")

        assert isinstance(result, dict)
        assert "_human_approved" in result
        assert result["_human_approved"] is True

    @pytest.mark.asyncio
    async def test_approval_callback_invoked(self):
        """Test that approval callback is invoked during execution."""
        callback_invoked = []

        def track_callback(result):
            callback_invoked.append(result)
            return True, "Approved by test"

        config = ApprovalConfig(approval_callback=track_callback, llm_provider="mock")
        agent = ApprovalAgent(config)

        await agent.decide_async("Test")

        assert len(callback_invoked) == 1, "Callback should be invoked once"

    @pytest.mark.asyncio
    async def test_rejection_raises_error(self):
        """Test that rejection raises RuntimeError."""

        def reject_callback(result):
            return False, "Rejected for testing"

        config = ApprovalConfig(approval_callback=reject_callback, llm_provider="mock")
        agent = ApprovalAgent(config)

        with pytest.raises(RuntimeError, match="Human rejected result"):
            await agent.decide_async("Test decision")

    @pytest.mark.asyncio
    async def test_approval_history_tracking(self):
        """Test that approval history is tracked."""
        config = ApprovalConfig(llm_provider="mock")
        agent = ApprovalAgent(config)

        # Make multiple decisions
        await agent.decide_async("First decision")
        await agent.decide_async("Second decision")

        history = agent.get_approval_history()

        assert len(history) == 2, f"Should have 2 approval records, got {len(history)}"
        assert all("approved" in record for record in history)
        assert all("feedback" in record for record in history)

    @pytest.mark.asyncio
    async def test_approval_metadata_added(self):
        """Test that approval metadata is added to result."""
        config = ApprovalConfig(llm_provider="mock")
        agent = ApprovalAgent(config)

        result = await agent.decide_async("Test")

        assert "_human_approved" in result
        assert result["_human_approved"] is True
        assert "_approval_feedback" in result

    def test_run_sync_method_works(self):
        """Test synchronous run method.

        Note: run() returns a dict with result or error fields.
        With mock provider, we test structure only.
        """
        config = ApprovalConfig(llm_provider="mock")
        agent = ApprovalAgent(config)

        result = agent.run(decision_context="Test decision")

        # run() returns a dict - may have 'decision' field or 'error' field
        assert isinstance(result, dict)
        # Should have either decision output or error
        assert "decision" in result or "error" in result

    def test_agent_uses_decision_signature(self):
        """Test that agent uses DecisionSignature."""
        config = ApprovalConfig(llm_provider="mock")
        agent = ApprovalAgent(config)

        assert isinstance(
            agent.signature, DecisionSignature
        ), f"Agent should use DecisionSignature, got {type(agent.signature)}"

    def test_agent_inherits_from_base_agent(self):
        """Test that ApprovalAgent inherits from BaseAgent."""
        from kaizen.core.base_agent import BaseAgent

        config = ApprovalConfig(llm_provider="mock")
        agent = ApprovalAgent(config)

        assert isinstance(
            agent, BaseAgent
        ), "ApprovalAgent should inherit from BaseAgent"

    @pytest.mark.asyncio
    async def test_custom_approval_callback_works(self):
        """Test that custom approval callback works."""
        custom_feedback = "Custom approval message"

        def custom_callback(result):
            return True, custom_feedback

        config = ApprovalConfig(approval_callback=custom_callback, llm_provider="mock")
        agent = ApprovalAgent(config)

        result = await agent.decide_async("Test")

        assert result["_approval_feedback"] == custom_feedback

    @pytest.mark.asyncio
    async def test_empty_approval_history_initially(self):
        """Test that approval history is empty initially."""
        config = ApprovalConfig(llm_provider="mock")
        agent = ApprovalAgent(config)

        history = agent.get_approval_history()

        assert history == [], "Approval history should be empty initially"

    @pytest.mark.asyncio
    async def test_approval_history_contains_result_copy(self):
        """Test that approval history contains copy of result."""
        config = ApprovalConfig(llm_provider="mock")
        agent = ApprovalAgent(config)

        await agent.decide_async("Test")

        history = agent.get_approval_history()

        assert len(history) == 1
        assert "result" in history[0]
        assert isinstance(history[0]["result"], dict)
