"""
Unit tests for HumanInLoopStrategy.

Tests cover:
- Approval callback called with result
- Approved result returns successfully
- Rejected result raises RuntimeError
- Tracks approval history
- Custom callback injection works
- Multiple approvals in sequence
- Feedback passed correctly
- Metadata added to approved results
- get_approval_history returns all decisions
- Default callback auto-approves
"""

import pytest
from kaizen.strategies.human_in_loop import HumanInLoopStrategy


class MockAgent:
    """Mock agent for testing."""

    async def execute(self, inputs):
        """Mock execution."""
        return {"response": f"Agent response to: {inputs.get('prompt', 'input')}"}


def auto_approve_callback(result):
    """Callback that auto-approves."""
    return True, "Auto-approved"


def auto_reject_callback(result):
    """Callback that auto-rejects."""
    return False, "Rejected for testing"


def conditional_callback(result):
    """Callback that approves based on confidence."""
    confidence = result.get("confidence", 0)
    if confidence >= 0.8:
        return True, f"Approved - high confidence ({confidence})"
    else:
        return False, f"Rejected - low confidence ({confidence})"


@pytest.mark.asyncio
async def test_approval_callback_called_with_result():
    """Test that approval callback is called with result."""
    called = False
    received_result = None

    def tracking_callback(result):
        nonlocal called, received_result
        called = True
        received_result = result
        return True, "approved"

    strategy = HumanInLoopStrategy(approval_callback=tracking_callback)
    agent = MockAgent()

    await strategy.execute(agent, {"prompt": "test"})

    assert called, "Callback should have been called"
    assert received_result is not None, "Callback should receive result"
    assert "response" in received_result


@pytest.mark.asyncio
async def test_approved_result_returns_successfully():
    """Test that approved result returns successfully."""
    strategy = HumanInLoopStrategy(approval_callback=auto_approve_callback)
    agent = MockAgent()

    result = await strategy.execute(agent, {"prompt": "test"})

    assert "response" in result
    assert result["_human_approved"] is True
    assert result["_approval_feedback"] == "Auto-approved"


@pytest.mark.asyncio
async def test_rejected_result_raises_runtime_error():
    """Test that rejected result raises RuntimeError."""
    strategy = HumanInLoopStrategy(approval_callback=auto_reject_callback)
    agent = MockAgent()

    with pytest.raises(RuntimeError) as exc_info:
        await strategy.execute(agent, {"prompt": "test"})

    assert "Human rejected result" in str(exc_info.value)
    assert "Rejected for testing" in str(exc_info.value)


@pytest.mark.asyncio
async def test_tracks_approval_history():
    """Test that approval history is tracked."""
    strategy = HumanInLoopStrategy(approval_callback=auto_approve_callback)
    agent = MockAgent()

    # Execute multiple times
    await strategy.execute(agent, {"prompt": "test1"})
    await strategy.execute(agent, {"prompt": "test2"})

    history = strategy.get_approval_history()

    assert len(history) == 2
    assert all("approved" in h for h in history)
    assert all("feedback" in h for h in history)
    assert all("result" in h for h in history)


@pytest.mark.asyncio
async def test_custom_callback_injection_works():
    """Test that custom callback injection works."""
    call_count = 0

    def custom_callback(result):
        nonlocal call_count
        call_count += 1
        return True, f"Call {call_count}"

    strategy = HumanInLoopStrategy(approval_callback=custom_callback)
    agent = MockAgent()

    result1 = await strategy.execute(agent, {"prompt": "test1"})
    result2 = await strategy.execute(agent, {"prompt": "test2"})

    assert call_count == 2
    assert result1["_approval_feedback"] == "Call 1"
    assert result2["_approval_feedback"] == "Call 2"


@pytest.mark.asyncio
async def test_multiple_approvals_in_sequence():
    """Test multiple approvals in sequence."""
    strategy = HumanInLoopStrategy(approval_callback=auto_approve_callback)
    agent = MockAgent()

    results = []
    for i in range(5):
        result = await strategy.execute(agent, {"prompt": f"test{i}"})
        results.append(result)

    assert len(results) == 5
    assert all(r["_human_approved"] is True for r in results)

    history = strategy.get_approval_history()
    assert len(history) == 5


@pytest.mark.asyncio
async def test_feedback_passed_correctly():
    """Test that feedback is passed correctly."""
    feedbacks = []

    def feedback_callback(result):
        feedback = f"Feedback for: {result.get('response', 'unknown')}"
        feedbacks.append(feedback)
        return True, feedback

    strategy = HumanInLoopStrategy(approval_callback=feedback_callback)
    agent = MockAgent()

    result = await strategy.execute(agent, {"prompt": "test"})

    assert len(feedbacks) == 1
    assert result["_approval_feedback"] == feedbacks[0]
    assert "Feedback for:" in result["_approval_feedback"]


@pytest.mark.asyncio
async def test_metadata_added_to_approved_results():
    """Test that metadata is added to approved results."""
    strategy = HumanInLoopStrategy(approval_callback=auto_approve_callback)
    agent = MockAgent()

    result = await strategy.execute(agent, {"prompt": "test"})

    assert "_human_approved" in result
    assert "_approval_feedback" in result
    assert result["_human_approved"] is True
    assert isinstance(result["_approval_feedback"], str)


@pytest.mark.asyncio
async def test_get_approval_history_returns_all_decisions():
    """Test that get_approval_history returns all decisions."""
    # Mix of approvals and rejections
    call_count = 0

    def alternating_callback(result):
        nonlocal call_count
        call_count += 1
        if call_count % 2 == 0:
            return False, f"Reject {call_count}"
        return True, f"Approve {call_count}"

    strategy = HumanInLoopStrategy(approval_callback=alternating_callback)
    agent = MockAgent()

    # Approve (call 1)
    await strategy.execute(agent, {"prompt": "test1"})

    # Reject (call 2)
    try:
        await strategy.execute(agent, {"prompt": "test2"})
    except RuntimeError:
        pass

    # Approve (call 3)
    await strategy.execute(agent, {"prompt": "test3"})

    history = strategy.get_approval_history()

    assert len(history) == 3
    assert history[0]["approved"] is True
    assert history[1]["approved"] is False
    assert history[2]["approved"] is True


@pytest.mark.asyncio
async def test_default_callback_auto_approves():
    """Test that default callback auto-approves."""
    strategy = HumanInLoopStrategy()  # No callback provided
    agent = MockAgent()

    result = await strategy.execute(agent, {"prompt": "test"})

    assert result["_human_approved"] is True
    assert "Auto-approved (test mode)" in result["_approval_feedback"]


@pytest.mark.asyncio
async def test_approval_history_includes_rejection_details():
    """Test that approval history includes rejection details."""
    strategy = HumanInLoopStrategy(approval_callback=auto_reject_callback)
    agent = MockAgent()

    try:
        await strategy.execute(agent, {"prompt": "test"})
    except RuntimeError:
        pass

    history = strategy.get_approval_history()

    assert len(history) == 1
    assert history[0]["approved"] is False
    assert history[0]["feedback"] == "Rejected for testing"


@pytest.mark.asyncio
async def test_conditional_approval_based_on_result():
    """Test conditional approval based on result content."""
    strategy = HumanInLoopStrategy(approval_callback=conditional_callback)
    MockAgent()

    # Mock agent returns result with confidence
    class ConfidentAgent:
        async def execute(self, inputs):
            return {
                "response": f"Response to: {inputs.get('prompt')}",
                "confidence": inputs.get("confidence", 0.5),
            }

    confident_agent = ConfidentAgent()

    # High confidence - should approve
    result_high = await strategy.execute(
        confident_agent, {"prompt": "test", "confidence": 0.9}
    )
    assert result_high["_human_approved"] is True
    assert "high confidence" in result_high["_approval_feedback"]

    # Low confidence - should reject
    with pytest.raises(RuntimeError) as exc_info:
        await strategy.execute(confident_agent, {"prompt": "test", "confidence": 0.5})
    assert "low confidence" in str(exc_info.value)


@pytest.mark.asyncio
async def test_approval_history_maintains_order():
    """Test that approval history maintains chronological order."""
    strategy = HumanInLoopStrategy(approval_callback=auto_approve_callback)
    agent = MockAgent()

    prompts = ["test1", "test2", "test3", "test4", "test5"]
    for prompt in prompts:
        await strategy.execute(agent, {"prompt": prompt})

    history = strategy.get_approval_history()

    assert len(history) == len(prompts)
    for i, record in enumerate(history):
        expected_prompt = prompts[i]
        assert expected_prompt in record["result"]["response"]
