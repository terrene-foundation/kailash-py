"""
Tier 3 E2E Tests: Meta-Controller Fallback Handling with Real OpenAI LLM.

Tests graceful fallback when primary agent fails with real infrastructure:
- Real OpenAI LLM inference (gpt-4o-mini for quality)
- Real agent failure scenarios
- Graceful fallback to alternative agents
- Error handling and recovery mechanisms

Requirements:
- OpenAI API key in .env (OPENAI_API_KEY)
- No mocking (real infrastructure only)
- Tests may take 30s-90s due to LLM inference

Test Coverage:
1. test_fallback_when_primary_agent_fails - Fallback when primary agent fails

Budget: $0.10 (1 test × $0.10)
Duration: ~30-60s total
"""

import os
from dataclasses import dataclass

import pytest
from dotenv import load_dotenv
from kaizen.core.base_agent import BaseAgent
from kaizen.orchestration.pipeline import Pipeline
from kaizen.signatures import InputField, OutputField, Signature

from tests.utils.cost_tracking import get_global_tracker
from tests.utils.reliability_helpers import (
    async_retry_with_backoff,
    require_openai_api_key,
)

# Load environment variables
load_dotenv()

# Check OpenAI API key availability
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set",
    ),
]


# ============================================================================
# Test Signatures
# ============================================================================


class TaskSignature(Signature):
    """Signature for general tasks."""

    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Task result")


# ============================================================================
# Agent Configurations
# ============================================================================


@dataclass
class TestAgentConfig:
    """Configuration for test agents."""

    llm_provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.3


# ============================================================================
# Agent Classes
# ============================================================================


class FailingAgent(BaseAgent):
    """Agent that fails after initialization."""

    def __init__(self):
        config = TestAgentConfig()
        super().__init__(
            config=config,
            signature=TaskSignature(),
            agent_id="failing_agent",
            description="Agent that fails during execution",
        )
        self._fail_on_next_run = True

    def run(self, **inputs):
        """Override run to fail intentionally."""
        if self._fail_on_next_run:
            raise RuntimeError("Primary agent intentionally failed for testing")
        return super().run(**inputs)


class BackupAgent(BaseAgent):
    """Backup agent that always succeeds."""

    def __init__(self):
        config = TestAgentConfig()
        super().__init__(
            config=config,
            signature=TaskSignature(),
            agent_id="backup_agent",
            description="Reliable backup agent for fallback scenarios",
        )


class PrimaryAgent(BaseAgent):
    """Primary agent for normal operation."""

    def __init__(self):
        config = TestAgentConfig()
        super().__init__(
            config=config,
            signature=TaskSignature(),
            agent_id="primary_agent",
            description="Primary agent for task execution",
        )


# ============================================================================
# Helper Functions
# ============================================================================


def track_openai_usage(test_name: str, estimated_tokens: int = 1000):
    """Track estimated OpenAI usage for cost monitoring.

    Args:
        test_name: Name of the test
        estimated_tokens: Estimated total tokens (input + output)
    """
    tracker = get_global_tracker(budget_usd=20.0)
    # Conservative estimate: 60% input, 40% output
    input_tokens = int(estimated_tokens * 0.6)
    output_tokens = int(estimated_tokens * 0.4)

    tracker.track_usage(
        test_name=test_name,
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


# ============================================================================
# Test 20: Fallback When Primary Agent Fails
# ============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
@require_openai_api_key()
async def test_fallback_when_primary_agent_fails():
    """
    Test 20: Meta-controller gracefully handles primary agent failure with fallback.

    Validates:
    - Graceful error handling when primary agent fails
    - Meta-controller returns error info in graceful mode
    - System continues operating with fallback mechanisms
    - Error details are properly captured and reported

    Expected Cost: $0.10 (2 attempts × ~1000 tokens each)
    Expected Duration: 30-60s
    """
    print("\n" + "=" * 80)
    print("TEST 20: Fallback When Primary Agent Fails")
    print("=" * 80)

    # Test 1: Graceful error handling mode
    print("\n--- Test 1: Graceful Error Handling ---")

    # Create failing agent and backup agent
    failing_agent = FailingAgent()
    backup_agent = BackupAgent()

    # Create meta-controller with graceful error handling
    meta_controller = Pipeline.router(
        agents=[failing_agent],
        routing_strategy="semantic",
        error_handling="graceful",
    )

    task = "Process this test task"

    async def run_with_failing_agent():
        result = meta_controller.run(task=task, input="test_data")
        return result

    # Should return error info, not raise exception
    result = await async_retry_with_backoff(
        run_with_failing_agent,
        max_attempts=1,
        initial_delay=2.0,
        exceptions=(
            AssertionError,
        ),  # Only retry on assertion errors, not runtime errors
    )

    print(f"Task: {task}")
    print(f"Result keys: {list(result.keys())}")

    # Verify graceful error handling
    assert result is not None, "Result should not be None"
    assert isinstance(result, dict), "Result should be a dictionary"
    assert "error" in result, "Result should contain error info in graceful mode"
    assert "Primary agent intentionally failed" in str(result["error"])
    assert result["status"] == "failed", "Status should be 'failed'"

    print(f"Error captured: {result['error']}")
    print(f"Status: {result['status']}")

    # Test 2: Fallback to backup agent with round-robin
    print("\n--- Test 2: Fallback with Round-Robin Strategy ---")

    # Create meta-controller with multiple agents (round-robin fallback)
    meta_controller_with_backup = Pipeline.router(
        agents=[failing_agent, backup_agent],
        routing_strategy="round-robin",  # Will try failing first, then backup
        error_handling="graceful",
    )

    # First call - will hit failing agent
    async def run_first_call():
        result = meta_controller_with_backup.run(task=task, input="test_data_1")
        return result

    result_1 = await async_retry_with_backoff(
        run_first_call, max_attempts=1, initial_delay=2.0, exceptions=(AssertionError,)
    )

    print(f"First call result (failing agent): {list(result_1.keys())}")
    assert "error" in result_1, "First call should fail gracefully"

    # Second call - will hit backup agent
    async def run_second_call():
        result = meta_controller_with_backup.run(task=task, input="test_data_2")
        return result

    result_2 = await async_retry_with_backoff(
        run_second_call, max_attempts=3, initial_delay=2.0
    )

    print(f"Second call result (backup agent): {list(result_2.keys())}")

    # Verify backup agent succeeded
    assert result_2 is not None, "Backup agent result should not be None"
    assert isinstance(result_2, dict), "Result should be a dictionary"
    # Backup agent should succeed (no error or status is not failed)
    backup_succeeded = "error" not in result_2 or result_2.get("status") != "failed"
    assert backup_succeeded, "Backup agent should succeed"

    # Test 3: Fail-fast mode comparison
    print("\n--- Test 3: Fail-Fast Mode (Exception Raised) ---")

    # Create meta-controller with fail-fast mode
    meta_controller_failfast = Pipeline.router(
        agents=[failing_agent],
        routing_strategy="semantic",
        error_handling="fail-fast",
    )

    # Should raise exception in fail-fast mode
    async def run_failfast():
        result = meta_controller_failfast.run(task=task, input="test_data")
        return result

    exception_raised = False
    try:
        await async_retry_with_backoff(
            run_failfast,
            max_attempts=1,
            initial_delay=2.0,
            exceptions=(),  # Don't retry any exceptions
        )
    except RuntimeError as e:
        exception_raised = True
        print(f"Exception raised as expected: {e}")
        assert "Primary agent intentionally failed" in str(e)

    assert exception_raised, "Fail-fast mode should raise exception"

    # Track cost (2 attempts × ~1000 tokens each)
    track_openai_usage("test_fallback_when_primary_agent_fails", estimated_tokens=2000)

    print("\n✓ Test 20 completed successfully")
    print("=" * 80)


# ============================================================================
# Pytest Configuration
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
