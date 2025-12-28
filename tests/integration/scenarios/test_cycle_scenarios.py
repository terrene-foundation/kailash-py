"""Consolidated cycle scenario tests with mocked timing.

Tests practical cycle patterns without actual sleep delays:
- ETL retry patterns with exponential backoff
- API polling with rate limiting
- Data processing with checkpoints
- Resource optimization cycles
"""

import time
from datetime import datetime
from typing import Any
from unittest.mock import Mock, patch

import pytest
from kailash import Workflow
from kailash.nodes.base import NodeParameter
from kailash.nodes.base_cycle_aware import CycleAwareNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.cyclic_runner import CyclicWorkflowExecutor


class MockETLNode(CycleAwareNode):
    """ETL node with configurable failure patterns for testing."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "data_source": NodeParameter(
                name="data_source", type=str, required=False, default=""
            ),
            "max_retries": NodeParameter(
                name="max_retries", type=int, required=False, default=3
            ),
            "retry_delay": NodeParameter(
                name="retry_delay", type=float, required=False, default=1.0
            ),
            "failure_pattern": NodeParameter(
                name="failure_pattern", type=list, required=False, default=[]
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        data_source = kwargs.get("data_source", "")
        max_retries = kwargs.get("max_retries", 3)
        retry_delay = kwargs.get("retry_delay", 1.0)
        failure_pattern = kwargs.get("failure_pattern", [])

        context = kwargs.get("context", {})
        iteration = self.get_iteration(context)
        retry_count = self.get_previous_state(context).get("retry_count", 0)

        # Check if this iteration should fail based on pattern
        should_fail = iteration < len(failure_pattern) and failure_pattern[iteration]

        if should_fail:
            new_retry_count = retry_count + 1
            should_retry = new_retry_count <= max_retries

            backoff_delay = 0
            if should_retry:
                # Mock exponential backoff (no actual sleep)
                backoff_delay = retry_delay * (2**retry_count)

            return {
                "status": "failed",
                "error": f"Simulated failure at iteration {iteration}",
                "retry_count": new_retry_count,
                "should_retry": should_retry,
                "backoff_delay": min(backoff_delay, 10) if should_retry else 0,
                **self.set_cycle_state({"retry_count": new_retry_count}),
            }

        # Success case
        return {
            "status": "success",
            "data": [f"record_{i}" for i in range(10)],
            "retry_count": retry_count,
            "records_processed": 10,
            **self.set_cycle_state({"retry_count": 0}),  # Reset on success
        }


class MockAPIPollerNode(CycleAwareNode):
    """API polling node with configurable response patterns."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "poll_interval": NodeParameter(
                name="poll_interval", type=float, required=False, default=1.0
            ),
            "max_polls": NodeParameter(
                name="max_polls", type=int, required=False, default=10
            ),
            "response_pattern": NodeParameter(
                name="response_pattern", type=list, required=False, default=[]
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        poll_interval = kwargs.get("poll_interval", 1.0)
        max_polls = kwargs.get("max_polls", 10)
        response_pattern = kwargs.get("response_pattern", [])

        context = kwargs.get("context", {})
        iteration = self.get_iteration(context)

        # Get response for this iteration
        if iteration < len(response_pattern):
            response = response_pattern[iteration]
        else:
            response = {"status": "ready", "data": "final_result"}

        # Determine continuation
        data_ready = response.get("status") == "ready"
        rate_limited = response.get("status") == "rate_limited"
        max_polls_reached = iteration >= max_polls - 1

        should_continue = not data_ready and not rate_limited and not max_polls_reached

        return {
            "api_response": response,
            "should_continue": should_continue,
            "iteration": iteration,
            "poll_interval": poll_interval,
            "rate_limit_remaining": response.get("rate_limit_remaining", 100),
        }


class MockBatchProcessorNode(CycleAwareNode):
    """Batch processing node with checkpoint simulation."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "total_records": NodeParameter(
                name="total_records", type=int, required=False, default=100
            ),
            "batch_size": NodeParameter(
                name="batch_size", type=int, required=False, default=10
            ),
            "processing_time": NodeParameter(
                name="processing_time", type=float, required=False, default=0.1
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        total_records = kwargs.get("total_records", 100)
        batch_size = kwargs.get("batch_size", 10)
        processing_time = kwargs.get("processing_time", 0.1)

        context = kwargs.get("context", {})
        iteration = self.get_iteration(context)
        processed_count = self.get_previous_state(context).get("processed_count", 0)

        # Calculate batch bounds
        batch_start = processed_count
        batch_end = min(batch_start + batch_size, total_records)

        # Mock processing (no actual sleep)
        batch_data = [
            {
                "record_id": i,
                "processed_value": i * 2,
                "batch_number": iteration,
                "processing_time": processing_time,
            }
            for i in range(batch_start, batch_end)
        ]

        new_processed_count = batch_end
        progress = new_processed_count / total_records
        all_processed = new_processed_count >= total_records

        checkpoint = {
            "batch_number": iteration,
            "processed_count": new_processed_count,
            "last_successful_id": batch_end - 1,
            "progress_percent": progress * 100,
        }

        return {
            "batch_data": batch_data,
            "checkpoint": checkpoint,
            "progress": progress,
            "all_processed": all_processed,
            "records_remaining": total_records - new_processed_count,
            **self.set_cycle_state({"processed_count": new_processed_count}),
        }


class TestCyclePatterns:
    """Consolidated tests for common cycle patterns."""

    def test_etl_retry_with_exponential_backoff(self):
        """Test ETL retry pattern with exponential backoff (mocked timing)."""
        workflow = Workflow("etl-retry", "ETL Retry Test")

        # Configure to fail 2 times then succeed
        failure_pattern = [True, True, False]  # Fail, Fail, Success

        etl_node = MockETLNode()
        workflow.add_node("etl", etl_node)
        workflow.create_cycle("etl_retry").connect("etl", "etl").max_iterations(
            5
        ).converge_when("status == 'success'").build()

        executor = CyclicWorkflowExecutor()
        result, _ = executor.execute(
            workflow,
            parameters={
                "etl": {
                    "data_source": "test_db",
                    "max_retries": 3,
                    "retry_delay": 1.0,
                    "failure_pattern": failure_pattern,
                }
            },
        )

        # Verify retry behavior
        assert result["etl"]["status"] == "success"
        assert result["etl"]["records_processed"] == 10

        # Verify execution completed with expected retry count
        # Note: Workflow executor tracks iterations internally

    def test_api_polling_with_rate_limits(self):
        """Test API polling with rate limiting and progressive responses."""
        workflow = Workflow("api-poll", "API Polling Test")

        # Progressive response pattern
        response_pattern = [
            {"status": "pending", "progress": 25, "rate_limit_remaining": 99},
            {"status": "processing", "progress": 50, "rate_limit_remaining": 98},
            {"status": "processing", "progress": 75, "rate_limit_remaining": 97},
            {"status": "ready", "data": "final_result", "rate_limit_remaining": 96},
        ]

        poller_node = MockAPIPollerNode()
        workflow.add_node("poller", poller_node)
        workflow.create_cycle("api_poll").connect("poller", "poller").max_iterations(
            10
        ).converge_when("should_continue == False").build()

        executor = CyclicWorkflowExecutor()
        result, _ = executor.execute(
            workflow,
            parameters={
                "poller": {
                    "poll_interval": 0.5,
                    "max_polls": 10,
                    "response_pattern": response_pattern,
                }
            },
        )

        # Verify polling completed successfully
        assert result["poller"]["api_response"]["status"] == "ready"
        assert result["poller"]["api_response"]["data"] == "final_result"
        assert result["poller"]["should_continue"] is False

    def test_batch_processing_with_checkpoints(self):
        """Test batch processing with checkpoint mechanism."""
        workflow = Workflow("batch-process", "Batch Processing Test")

        processor_node = MockBatchProcessorNode()
        workflow.add_node("processor", processor_node)
        workflow.create_cycle("batch_process").connect(
            "processor", "processor"
        ).max_iterations(20).converge_when("all_processed == True").build()

        executor = CyclicWorkflowExecutor()
        result, _ = executor.execute(
            workflow,
            parameters={
                "processor": {
                    "total_records": 45,
                    "batch_size": 10,
                    "processing_time": 0.05,
                }
            },
        )

        # Verify all records processed (using passed total_records=45)
        assert result["processor"]["all_processed"] is True
        assert result["processor"]["checkpoint"]["processed_count"] == 45
        assert result["processor"]["progress"] == 1.0
        assert result["processor"]["records_remaining"] == 0

    @patch("time.sleep")
    def test_cycle_timing_patterns_mocked(self, mock_sleep):
        """Test that timing calls are properly mocked in cycle scenarios."""
        workflow = Workflow("timing-test", "Timing Test")

        # Use a node that would normally call time.sleep
        class TimingAwareNode(CycleAwareNode):
            def get_parameters(self):
                return {
                    "delay": NodeParameter(
                        name="delay", type=float, required=False, default=1.0
                    ),
                }

            def run(self, **kwargs):
                delay = kwargs.get("delay", 1.0)
                context = kwargs.get("context", {})
                iteration = self.get_iteration(context)

                # This would normally block, but should be mocked
                time.sleep(delay)

                return {
                    "iteration": iteration,
                    "delay_used": delay,
                    "completed": iteration >= 2,
                }

        timing_node = TimingAwareNode()
        workflow.add_node("timer", timing_node)
        workflow.create_cycle("timing_test").connect("timer", "timer").max_iterations(
            3
        ).converge_when("completed == True").build()

        executor = CyclicWorkflowExecutor()
        start_time = time.time()
        result, _ = executor.execute(
            workflow,
            parameters={"timer": {"delay": 2.0}},
        )
        end_time = time.time()

        # Verify execution was fast (mocked) not slow (real sleep)
        execution_time = end_time - start_time
        assert execution_time < 1.0  # Should be much faster than 6 seconds (3 * 2.0)

        # Verify sleep was called with expected parameters
        assert mock_sleep.called
        assert mock_sleep.call_count >= 2  # At least 2 iterations before convergence

        # Verify results
        assert result["timer"]["completed"] is True

    def test_resource_optimization_cycle(self):
        """Test resource optimization with convergence detection."""
        workflow = Workflow("resource-opt", "Resource Optimization Test")

        class ResourceOptimizerNode(CycleAwareNode):
            def get_parameters(self):
                return {
                    "target_efficiency": NodeParameter(
                        name="target_efficiency",
                        type=float,
                        required=False,
                        default=0.95,
                    ),
                    "improvement_rate": NodeParameter(
                        name="improvement_rate", type=float, required=False, default=0.1
                    ),
                }

            def run(self, **kwargs):
                target_efficiency = kwargs.get("target_efficiency", 0.95)
                improvement_rate = kwargs.get("improvement_rate", 0.1)
                context = kwargs.get("context", {})

                iteration = self.get_iteration(context)
                current_efficiency = self.get_previous_state(context).get(
                    "efficiency", 0.6
                )

                # Simulate optimization improving efficiency
                new_efficiency = min(
                    current_efficiency + improvement_rate,
                    target_efficiency + 0.1,  # Can overshoot slightly
                )

                converged = new_efficiency >= target_efficiency

                return {
                    "efficiency": new_efficiency,
                    "improvement": new_efficiency - current_efficiency,
                    "target_met": converged,
                    "iteration": iteration,
                    **self.set_cycle_state({"efficiency": new_efficiency}),
                }

        optimizer_node = ResourceOptimizerNode()
        workflow.add_node("optimizer", optimizer_node)
        workflow.create_cycle("resource_opt").connect(
            "optimizer", "optimizer"
        ).max_iterations(10).converge_when("target_met == True").build()

        executor = CyclicWorkflowExecutor()
        result, _ = executor.execute(
            workflow,
            parameters={
                "optimizer": {
                    "target_efficiency": 0.95,
                    "improvement_rate": 0.15,
                }
            },
        )

        # Verify optimization converged
        assert result["optimizer"]["target_met"] is True
        assert result["optimizer"]["efficiency"] >= 0.95
        assert (
            result["optimizer"]["iteration"] < 10
        )  # Should converge before max iterations


class TestCycleErrorHandling:
    """Test error handling patterns in cycles."""

    def test_cycle_with_retry_exhaustion(self):
        """Test cycle behavior with retry exhaustion."""
        workflow = Workflow("retry-exhaustion", "Retry Exhaustion Test")

        # Configure to always fail
        failure_pattern = [True] * 10  # Always fail

        etl_node = MockETLNode()
        workflow.add_node("etl", etl_node)
        workflow.create_cycle("retry_exhaustion").connect("etl", "etl").max_iterations(
            3
        ).build()

        executor = CyclicWorkflowExecutor()
        result, _ = executor.execute(
            workflow,
            parameters={
                "etl": {
                    "max_retries": 2,
                    "failure_pattern": failure_pattern,
                }
            },
        )

        # With always-fail pattern and max_iterations=3, should fail after retries
        assert result["etl"]["status"] == "failed"
        assert (
            result["etl"]["retry_count"] >= 2
        )  # Should have retried max_retries times
        assert result["etl"]["should_retry"] is False  # No more retries allowed

    def test_cycle_with_timeout_simulation(self):
        """Test cycle behavior with timeout conditions."""
        workflow = Workflow("timeout-test", "Timeout Test")

        class TimeoutAwareNode(CycleAwareNode):
            def get_parameters(self):
                return {
                    "timeout_iterations": NodeParameter(
                        name="timeout_iterations", type=int, required=False, default=5
                    ),
                }

            def run(self, **kwargs):
                timeout_iterations = kwargs.get("timeout_iterations", 5)
                context = kwargs.get("context", {})
                iteration = self.get_iteration(context)

                timed_out = iteration >= timeout_iterations

                return {
                    "iteration": iteration,
                    "timed_out": timed_out,
                    "status": "timeout" if timed_out else "running",
                }

        timeout_node = TimeoutAwareNode()
        workflow.add_node("timeout", timeout_node)
        workflow.create_cycle("timeout_test").connect(
            "timeout", "timeout"
        ).max_iterations(10).converge_when("timed_out == True").build()

        executor = CyclicWorkflowExecutor()
        result, _ = executor.execute(
            workflow,
            parameters={"timeout": {"timeout_iterations": 3}},
        )

        # Verify timeout was detected (using timeout_iterations=3)
        assert result["timeout"]["timed_out"] is True
        assert result["timeout"]["status"] == "timeout"
        assert result["timeout"]["iteration"] == 3
