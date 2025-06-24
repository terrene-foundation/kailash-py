"""
Integration tests for error recovery patterns.

Tests demonstrate:
- Retry strategies with exponential backoff
- Circuit breaker patterns
- Fallback mechanisms
- Checkpoint-based recovery
- Graceful degradation
"""

import asyncio
import random
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

import pytest

pytest.skip("Error recovery patterns not implemented yet", allow_module_level=True)

from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic import SwitchNode
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.sdk_exceptions import NodeExecutionError, WorkflowError
from kailash.workflow import (
    AsyncPatterns,
    AsyncWorkflowBuilder,
    CircuitBreaker,
    ErrorHandler,
    RetryPolicy,
    Workflow,
)


class TestErrorRecoveryPatterns:
    """Test error recovery patterns in workflows."""

    def setup_method(self):
        """Set up test environment."""
        self.runtime = AsyncLocalRuntime(
            max_workers=10,
            enable_monitoring=True,
            enable_checkpointing=True,
        )

        # Track execution attempts for testing
        self.execution_attempts = {}
        self.circuit_breaker_states = {}

    def teardown_method(self):
        """Clean up after tests."""
        if hasattr(self, "runtime"):
            asyncio.run(self.runtime.close())

    @pytest.mark.asyncio
    async def test_retry_with_exponential_backoff(self):
        """Test retry pattern with exponential backoff."""
        attempt_times = []

        workflow = (
            AsyncWorkflowBuilder("retry_test")
            .add_async_code(
                "flaky_operation",
                """
# Simulate flaky operation that fails first 2 attempts
import time
attempt_times = globals().get('attempt_times', [])
attempt_times.append(time.time())

attempt_count = len(attempt_times)
if attempt_count < 3:
    raise ConnectionError(f"Connection failed (attempt {attempt_count})")

result = {
    'success': True,
    'attempts': attempt_count,
    'data': 'Operation succeeded after retries'
}
""",
                # Pass attempt_times to track timing
                globals_dict={"attempt_times": attempt_times},
            )
            .add_pattern(
                AsyncPatterns.retry(
                    max_attempts=4,
                    backoff_factor=2.0,
                    initial_delay=0.1,
                    exceptions=[ConnectionError],
                )
            )
            .build()
        )

        # Execute workflow
        result = await self.runtime.execute_workflow(workflow)

        # Verify success after retries
        assert result["flaky_operation"]["success"] is True
        assert result["flaky_operation"]["attempts"] == 3

        # Verify exponential backoff timing
        assert len(attempt_times) == 3
        # First retry after ~0.1s
        assert 0.05 < (attempt_times[1] - attempt_times[0]) < 0.2
        # Second retry after ~0.2s (2x backoff)
        assert 0.15 < (attempt_times[2] - attempt_times[1]) < 0.3

    @pytest.mark.asyncio
    async def test_circuit_breaker_pattern(self):
        """Test circuit breaker preventing cascading failures."""
        call_results = []

        # Create workflow with circuit breaker
        workflow = (
            AsyncWorkflowBuilder("circuit_breaker_test")
            .add_async_code(
                "external_service",
                """
# Simulate external service that always fails
call_results.append(datetime.now(UTC).isoformat())
raise TimeoutError("External service timeout")
""",
                globals_dict={
                    "call_results": call_results,
                    "datetime": datetime,
                    "UTC": UTC,
                },
            )
            .add_pattern(
                AsyncPatterns.circuit_breaker(
                    failure_threshold=2,
                    recovery_timeout=1,
                    half_open_requests=1,
                )
            )
            .build()
        )

        # First executions should fail and open circuit
        for i in range(3):
            try:
                await self.runtime.execute_workflow(workflow)
            except Exception as e:
                if i < 2:
                    assert "timeout" in str(e).lower()
                else:
                    # Circuit should be open
                    assert "circuit breaker is open" in str(e).lower()

        # Verify circuit breaker prevented third call
        assert len(call_results) == 2  # Only first 2 calls made

        # Wait for recovery timeout
        await asyncio.sleep(1.1)

        # Next call should attempt (half-open state)
        try:
            await self.runtime.execute_workflow(workflow)
        except Exception:
            pass

        assert len(call_results) == 3  # One more attempt made

    @pytest.mark.asyncio
    async def test_fallback_chain(self):
        """Test multiple fallback strategies."""
        workflow = (
            AsyncWorkflowBuilder("fallback_chain_test")
            # Primary service
            .add_async_code(
                "primary_service",
                """
# Always fails
raise Exception("Primary service unavailable")
""",
            )
            # First fallback
            .add_async_code(
                "fallback_service_1",
                """
# Also fails
raise Exception("Fallback 1 unavailable")
""",
                error_handler=ErrorHandler.skip(),
            )
            # Second fallback
            .add_async_code(
                "fallback_service_2",
                """
# This one works
result = {
    'source': 'fallback_2',
    'data': 'Emergency response data',
    'degraded': True
}
""",
                error_handler=ErrorHandler.skip(),
            )
            # Default response if all fail
            .add_async_code(
                "default_response",
                """
result = {
    'source': 'default',
    'data': 'System unavailable',
    'error': True
}
""",
                error_handler=ErrorHandler.skip(),
            )
            # Result selector
            .add_async_code(
                "select_result",
                """
# Select first available result
sources = [
    primary_service.get('result'),
    fallback_service_1.get('result'),
    fallback_service_2.get('result'),
    default_response.get('result')
]

result = next((s for s in sources if s is not None), {'error': 'No service available'})
""",
            )
            # Set up fallback chain
            .set_error_handler(
                "primary_service", ErrorHandler.fallback("fallback_service_1")
            )
            .set_error_handler(
                "fallback_service_1", ErrorHandler.fallback("fallback_service_2")
            )
            .set_error_handler(
                "fallback_service_2", ErrorHandler.fallback("default_response")
            )
            .add_connections(
                [
                    ("primary_service", "result", "select_result", "primary_service"),
                    (
                        "fallback_service_1",
                        "result",
                        "select_result",
                        "fallback_service_1",
                    ),
                    (
                        "fallback_service_2",
                        "result",
                        "select_result",
                        "fallback_service_2",
                    ),
                    ("default_response", "result", "select_result", "default_response"),
                ]
            )
            .build()
        )

        result = await self.runtime.execute_workflow(workflow)

        # Should get response from fallback_2
        assert result["select_result"]["source"] == "fallback_2"
        assert result["select_result"]["degraded"] is True

    @pytest.mark.asyncio
    async def test_checkpoint_recovery(self):
        """Test recovery from checkpoints after failure."""
        execution_state = {"completed_steps": []}

        workflow = (
            AsyncWorkflowBuilder("checkpoint_recovery_test")
            .with_checkpointing(
                {
                    "enabled": True,
                    "interval": 1,  # Checkpoint after each node
                }
            )
            # Step 1 - Always succeeds
            .add_async_code(
                "step1",
                """
execution_state['completed_steps'].append('step1')
result = {'step': 1, 'data': 'Step 1 complete'}
""",
                globals_dict={"execution_state": execution_state},
            )
            # Step 2 - Always succeeds
            .add_async_code(
                "step2",
                """
execution_state['completed_steps'].append('step2')
result = {'step': 2, 'data': 'Step 2 complete'}
""",
                globals_dict={"execution_state": execution_state},
            )
            # Step 3 - Fails on first attempt
            .add_async_code(
                "step3",
                """
if 'step3_retry' not in execution_state:
    execution_state['step3_retry'] = True
    raise Exception("Simulated failure at step 3")

execution_state['completed_steps'].append('step3')
result = {'step': 3, 'data': 'Step 3 complete after retry'}
""",
                globals_dict={"execution_state": execution_state},
            )
            .add_connections(
                [
                    ("step1", "result", "step2", "previous"),
                    ("step2", "result", "step3", "previous"),
                ]
            )
            .build()
        )

        # First execution should fail at step 3
        try:
            await self.runtime.execute_workflow(
                workflow, workflow_id="checkpoint_test_1"
            )
        except Exception as e:
            assert "step 3" in str(e)

        # Verify partial completion
        assert execution_state["completed_steps"] == ["step1", "step2"]

        # Resume from checkpoint
        result = await self.runtime.execute_workflow(
            workflow, workflow_id="checkpoint_test_1", resume=True
        )

        # Should complete successfully
        assert result["step3"]["step"] == 3
        assert "retry" in result["step3"]["data"]

        # Verify steps 1&2 weren't re-executed
        assert execution_state["completed_steps"] == ["step1", "step2", "step3"]

    @pytest.mark.asyncio
    async def test_timeout_with_graceful_degradation(self):
        """Test timeout handling with graceful degradation."""
        workflow = (
            AsyncWorkflowBuilder("timeout_degradation_test")
            # Slow operation with timeout
            .add_async_code(
                "slow_operation",
                """
import asyncio
# Simulate slow operation
await asyncio.sleep(2)
result = {'status': 'complete', 'quality': 'high'}
""",
            )
            # Fast alternative
            .add_async_code(
                "fast_alternative",
                """
# Quick but lower quality result
result = {'status': 'degraded', 'quality': 'low', 'reason': 'timeout'}
""",
                error_handler=ErrorHandler.skip(),
            )
            # Merge results
            .add_async_code(
                "merge_results",
                """
if 'slow_operation' in locals() and slow_operation.get('result'):
    result = slow_operation['result']
else:
    result = fast_alternative['result']
""",
            )
            # Add tight timeout
            .add_pattern(
                AsyncPatterns.timeout(
                    timeout_seconds=0.5,
                    error_handler=ErrorHandler.fallback("fast_alternative"),
                )
            )
            .set_error_handler(
                "slow_operation", ErrorHandler.fallback("fast_alternative")
            )
            .add_connections(
                [
                    ("slow_operation", "result", "merge_results", "slow_operation"),
                    ("fast_alternative", "result", "merge_results", "fast_alternative"),
                ]
            )
            .build()
        )

        result = await self.runtime.execute_workflow(workflow)

        # Should get degraded result due to timeout
        assert result["merge_results"]["status"] == "degraded"
        assert result["merge_results"]["quality"] == "low"
        assert result["merge_results"]["reason"] == "timeout"

    @pytest.mark.asyncio
    async def test_error_aggregation_and_reporting(self):
        """Test collecting and reporting errors from multiple sources."""
        workflow = (
            AsyncWorkflowBuilder("error_aggregation_test")
            # Multiple operations that might fail
            .add_async_code(
                "operation1",
                """
# Succeeds
result = {'status': 'success', 'data': 100}
""",
                error_handler=ErrorHandler.collect(),
            )
            .add_async_code(
                "operation2",
                """
# Fails with specific error
raise ValueError("Invalid input data: missing required field 'user_id'")
""",
                error_handler=ErrorHandler.collect(),
            )
            .add_async_code(
                "operation3",
                """
# Another failure
raise ConnectionError("Database connection timeout after 30s")
""",
                error_handler=ErrorHandler.collect(),
            )
            .add_async_code(
                "operation4",
                """
# Succeeds
result = {'status': 'success', 'data': 200}
""",
                error_handler=ErrorHandler.collect(),
            )
            # Error reporter
            .add_async_code(
                "error_report",
                """
errors = []
successes = []

# Collect results and errors
for op_name in ['operation1', 'operation2', 'operation3', 'operation4']:
    if op_name in locals():
        op_result = locals()[op_name]
        if 'error' in op_result:
            errors.append({
                'operation': op_name,
                'error_type': op_result['error']['type'],
                'message': op_result['error']['message'],
                'timestamp': datetime.now(UTC).isoformat()
            })
        elif 'result' in op_result:
            successes.append({
                'operation': op_name,
                'data': op_result['result']['data']
            })

result = {
    'total_operations': 4,
    'successful': len(successes),
    'failed': len(errors),
    'success_rate': len(successes) / 4,
    'errors': errors,
    'successes': successes
}
""",
                globals_dict={"datetime": datetime, "UTC": UTC},
            )
            # Connect all operations to error reporter
            .add_connections(
                [
                    ("operation1", "result", "error_report", "operation1"),
                    ("operation2", "error", "error_report", "operation2"),
                    ("operation3", "error", "error_report", "operation3"),
                    ("operation4", "result", "error_report", "operation4"),
                ]
            )
            .build()
        )

        result = await self.runtime.execute_workflow(workflow)

        # Verify error aggregation
        report = result["error_report"]
        assert report["total_operations"] == 4
        assert report["successful"] == 2
        assert report["failed"] == 2
        assert report["success_rate"] == 0.5

        # Check error details
        errors = {e["operation"]: e for e in report["errors"]}
        assert "operation2" in errors
        assert "ValueError" in errors["operation2"]["error_type"]
        assert "user_id" in errors["operation2"]["message"]

        assert "operation3" in errors
        assert "ConnectionError" in errors["operation3"]["error_type"]
        assert "timeout" in errors["operation3"]["message"]

    @pytest.mark.asyncio
    async def test_adaptive_retry_strategy(self):
        """Test adaptive retry that adjusts based on error type."""
        attempt_log = []

        workflow = (
            AsyncWorkflowBuilder("adaptive_retry_test")
            .add_async_code(
                "adaptive_operation",
                """
import random

attempt_log.append({
    'time': datetime.now(UTC).isoformat(),
    'attempt': len(attempt_log) + 1
})

attempt = len(attempt_log)

# Different error types on different attempts
if attempt == 1:
    # Transient network error - should retry quickly
    raise ConnectionError("Network timeout")
elif attempt == 2:
    # Rate limit - should back off more
    raise Exception("429: Rate limit exceeded")
elif attempt == 3:
    # Server error - should retry with moderate delay
    raise Exception("500: Internal server error")
else:
    # Success on 4th attempt
    result = {
        'success': True,
        'attempts': attempt,
        'final_strategy': 'succeeded after adaptive retries'
    }
""",
                globals_dict={
                    "attempt_log": attempt_log,
                    "datetime": datetime,
                    "UTC": UTC,
                    "random": random,
                },
            )
            # Adaptive retry pattern
            .add_pattern(
                AsyncPatterns.retry(
                    max_attempts=5,
                    backoff_factor=lambda attempt, error: (
                        0.1
                        if "timeout" in str(error).lower()
                        else 2.0 if "429" in str(error) else 0.5
                    ),
                    initial_delay=0.1,
                )
            )
            .build()
        )

        result = await self.runtime.execute_workflow(workflow)

        # Verify successful completion
        assert result["adaptive_operation"]["success"] is True
        assert result["adaptive_operation"]["attempts"] == 4

        # Verify adaptive timing
        assert len(attempt_log) == 4

        # Calculate delays between attempts
        for i in range(1, len(attempt_log)):
            current = datetime.fromisoformat(
                attempt_log[i]["time"].replace("Z", "+00:00")
            )
            previous = datetime.fromisoformat(
                attempt_log[i - 1]["time"].replace("Z", "+00:00")
            )
            delay = (current - previous).total_seconds()

            # Verify delay matches expected backoff for error type
            if i == 1:  # After network timeout
                assert delay < 0.3  # Quick retry
            elif i == 2:  # After rate limit
                assert delay > 1.5  # Longer backoff
            elif i == 3:  # After server error
                assert 0.3 < delay < 1.0  # Moderate delay
