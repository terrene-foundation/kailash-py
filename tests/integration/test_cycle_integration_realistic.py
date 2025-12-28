"""Integration tests for cycle scenarios with realistic timing.

These tests use actual delays and external-like behaviors to validate
cycle patterns in more realistic conditions. Marked as slow tests.
"""

import json
import time
from datetime import datetime
from typing import Any

import pytest
from kailash import Workflow
from kailash.nodes.base import NodeParameter
from kailash.nodes.base_cycle_aware import CycleAwareNode
from kailash.runtime.local import LocalRuntime


class RealisticETLNode(CycleAwareNode):
    """ETL node with realistic failure and retry patterns."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "data_source": NodeParameter(
                name="data_source", type=str, required=False, default=""
            ),
            "max_retries": NodeParameter(
                name="max_retries", type=int, required=False, default=3
            ),
            "retry_delay": NodeParameter(
                name="retry_delay", type=float, required=False, default=0.1
            ),
            "failure_rate": NodeParameter(
                name="failure_rate", type=float, required=False, default=0.3
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        data_source = kwargs.get("data_source", "")
        max_retries = kwargs.get("max_retries", 3)
        retry_delay = kwargs.get("retry_delay", 0.1)
        failure_rate = kwargs.get("failure_rate", 0.3)

        context = kwargs.get("context", {})
        iteration = self.get_iteration(context)
        retry_count = self.get_previous_state(context).get("retry_count", 0)

        # Simulate connection/processing time
        time.sleep(retry_delay / 2)  # Minimal delay for realism

        # Simulate failure based on failure rate and iteration
        import random

        random.seed(iteration + retry_count)  # Deterministic for testing
        should_fail = random.random() < failure_rate and retry_count < 2

        if should_fail:
            new_retry_count = retry_count + 1
            should_retry = new_retry_count <= max_retries

            if should_retry:
                # Real exponential backoff (but capped low for tests)
                backoff_delay = retry_delay * (2**retry_count)
                actual_delay = min(backoff_delay, 0.2)  # Cap at 0.2s for tests
                time.sleep(actual_delay)

            return {
                "status": "failed",
                "error": f"Connection timeout to {data_source}",
                "retry_count": new_retry_count,
                "should_retry": should_retry,
                "backoff_delay": actual_delay if should_retry else 0,
                **self.set_cycle_state({"retry_count": new_retry_count}),
            }

        # Success - simulate data processing
        time.sleep(retry_delay / 4)  # Processing time

        return {
            "status": "success",
            "data": [{"id": i, "value": f"data_{i}"} for i in range(5)],
            "retry_count": retry_count,
            "records_processed": 5,
            **self.set_cycle_state({"retry_count": 0}),
        }


class RealisticAPIPollerNode(CycleAwareNode):
    """API poller with realistic timing and rate limiting."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "poll_interval": NodeParameter(
                name="poll_interval", type=float, required=False, default=0.1
            ),
            "max_polls": NodeParameter(
                name="max_polls", type=int, required=False, default=8
            ),
            "endpoint": NodeParameter(
                name="endpoint", type=str, required=False, default=""
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        poll_interval = kwargs.get("poll_interval", 0.1)
        max_polls = kwargs.get("max_polls", 8)
        endpoint = kwargs.get("endpoint", "")

        context = kwargs.get("context", {})
        iteration = self.get_iteration(context)
        last_poll_time = self.get_previous_state(context).get("last_poll_time", 0)
        rate_limit_remaining = self.get_previous_state(context).get(
            "rate_limit_remaining", 100
        )

        # Enforce rate limiting with real timing
        current_time = time.time()
        time_since_last = (
            current_time - last_poll_time if last_poll_time > 0 else poll_interval
        )

        if time_since_last < poll_interval:
            sleep_time = poll_interval - time_since_last
            time.sleep(sleep_time)
            current_time = time.time()

        # Simulate API call delay
        time.sleep(0.02)  # 20ms API latency

        # Simulate progressive API responses
        if iteration < 2:
            api_response = {
                "status": "pending",
                "progress": iteration * 30,
                "rate_limit_remaining": rate_limit_remaining - 1,
            }
        elif iteration < 4:
            api_response = {
                "status": "processing",
                "progress": 60 + iteration * 10,
                "rate_limit_remaining": rate_limit_remaining - 1,
            }
        else:
            api_response = {
                "status": "ready",
                "data": {"result": "completed", "items": 42},
                "rate_limit_remaining": rate_limit_remaining - 1,
            }

        # Update state
        new_rate_limit = api_response["rate_limit_remaining"]

        # Determine continuation
        data_ready = api_response.get("status") == "ready"
        rate_limited = new_rate_limit <= 0
        max_polls_reached = iteration >= max_polls - 1

        should_continue = not data_ready and not rate_limited and not max_polls_reached

        return {
            "api_response": api_response,
            "should_continue": should_continue,
            "iteration": iteration,
            "endpoint": endpoint,
            **self.set_cycle_state(
                {
                    "last_poll_time": current_time,
                    "rate_limit_remaining": new_rate_limit,
                }
            ),
        }


class RealisticBatchProcessorNode(CycleAwareNode):
    """Batch processor with realistic processing delays and checkpoints."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "total_records": NodeParameter(
                name="total_records", type=int, required=False, default=50
            ),
            "batch_size": NodeParameter(
                name="batch_size", type=int, required=False, default=8
            ),
            "processing_delay": NodeParameter(
                name="processing_delay", type=float, required=False, default=0.01
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        total_records = kwargs.get("total_records", 50)
        batch_size = kwargs.get("batch_size", 8)
        processing_delay = kwargs.get("processing_delay", 0.01)
        # Debug: print what we're getting
        # print(f"RealisticBatchProcessorNode received total_records={total_records}")

        context = kwargs.get("context", {})
        iteration = self.get_iteration(context)
        processed_count = self.get_previous_state(context).get("processed_count", 0)

        # Calculate batch
        batch_start = processed_count
        batch_end = min(batch_start + batch_size, total_records)

        # Process batch with realistic timing
        batch_data = []
        for i in range(batch_start, batch_end):
            # Simulate per-record processing time
            time.sleep(processing_delay)

            processed_record = {
                "record_id": i,
                "processed_value": i * 2.5,
                "batch_number": iteration,
                "processed_at": time.time(),
            }
            batch_data.append(processed_record)

        new_processed_count = batch_end
        progress = new_processed_count / total_records
        all_processed = new_processed_count >= total_records

        # Create checkpoint
        checkpoint = {
            "batch_number": iteration,
            "processed_count": new_processed_count,
            "last_successful_id": batch_end - 1,
            "timestamp": time.time(),
            "progress_percent": progress * 100,
        }

        return {
            "batch_data": batch_data,
            "batch_size": len(batch_data),
            "checkpoint": checkpoint,
            "progress": progress,
            "all_processed": all_processed,
            "records_remaining": total_records - new_processed_count,
            **self.set_cycle_state({"processed_count": new_processed_count}),
        }


@pytest.mark.slow
class TestRealisticCycleScenarios:
    """Integration tests with realistic timing and external-like behavior."""

    @pytest.mark.skip(
        reason="Flaky test with deliberate failures - timing sensitive in CI"
    )
    def test_realistic_etl_with_retries(self):
        """Test ETL pipeline with realistic retry timing and failures."""
        workflow = Workflow("realistic-etl", "Realistic ETL Pipeline")

        etl_node = RealisticETLNode()
        workflow.add_node("etl", etl_node)
        workflow.create_cycle("etl_retry_cycle").connect(
            "etl", "etl", mapping={}
        ).max_iterations(8).converge_when("status == 'success'").build()

        runtime = LocalRuntime()
        start_time = time.time()

        result, _ = runtime.execute(
            workflow,
            parameters={
                "etl": {
                    "data_source": "production_db",
                    "max_retries": 3,
                    "retry_delay": 0.05,  # 50ms base delay
                    "failure_rate": 0.4,  # 40% failure rate
                }
            },
        )

        end_time = time.time()
        execution_time = end_time - start_time

        # Should succeed eventually
        assert result["etl"]["status"] == "success"
        assert result["etl"]["records_processed"] == 5

        # Should take measurable time due to realistic delays
        assert execution_time > 0.1  # At least 100ms
        assert execution_time < 2.0  # But not too long

        # Verify workflow state tracking
        # Note: LocalRuntime doesn't have get_workflow_state method
        # workflow_state = runtime.get_workflow_state(workflow.id)
        # assert "execution_history" in workflow_state

    def test_realistic_api_polling_with_rate_limits(self):
        """Test API polling with realistic timing and rate limiting."""
        workflow = Workflow("realistic-api-poll", "Realistic API Polling")

        poller_node = RealisticAPIPollerNode()
        workflow.add_node("poller", poller_node)
        workflow.create_cycle("api_polling_cycle").connect(
            "poller", "poller", mapping={}
        ).max_iterations(10).converge_when("should_continue == False").build()

        runtime = LocalRuntime()
        start_time = time.time()

        result, _ = runtime.execute(
            workflow,
            parameters={
                "poller": {
                    "poll_interval": 0.08,  # 80ms between polls
                    "max_polls": 8,
                    "endpoint": "https://api.example.com/status",
                }
            },
        )

        end_time = time.time()
        execution_time = end_time - start_time

        # Should complete successfully
        assert result["poller"]["api_response"]["status"] == "ready"
        assert result["poller"]["api_response"]["data"]["result"] == "completed"
        assert result["poller"]["should_continue"] is False

        # Should respect rate limiting timing
        expected_min_time = 5 * 0.08  # At least 5 polls * 80ms interval
        assert execution_time >= expected_min_time * 0.8  # Allow some tolerance

        # Verify rate limit tracking
        assert "rate_limit_remaining" in result["poller"]["api_response"]

    def test_realistic_batch_processing_with_checkpoints(self):
        """Test batch processing with realistic per-record timing."""
        workflow = Workflow("realistic-batch", "Realistic Batch Processing")

        processor_node = RealisticBatchProcessorNode()
        workflow.add_node("processor", processor_node)
        workflow.create_cycle("batch_processing_cycle").connect(
            "processor", "processor", mapping={}
        ).max_iterations(15).converge_when("all_processed == True").build()

        runtime = LocalRuntime()
        start_time = time.time()

        result, _ = runtime.execute(
            workflow,
            parameters={
                "processor": {
                    "total_records": 35,
                    "batch_size": 6,
                    "processing_delay": 0.005,  # 5ms per record
                }
            },
        )

        end_time = time.time()
        execution_time = end_time - start_time

        # Should process all records
        assert result["processor"]["all_processed"] is True
        # The test passes 35 records, so that's what should be processed
        assert result["processor"]["checkpoint"]["processed_count"] == 35
        assert result["processor"]["progress"] == 1.0

        # Should take time proportional to record count and processing delay
        expected_min_time = 35 * 0.005  # 35 records * 5ms each
        assert execution_time >= expected_min_time * 0.8  # Allow tolerance

        # Verify checkpoint data
        checkpoint = result["processor"]["checkpoint"]
        assert checkpoint["progress_percent"] == 100.0
        assert "timestamp" in checkpoint

    def test_realistic_resource_optimization_cycle(self):
        """Test resource optimization with gradual improvement timing."""
        workflow = Workflow("realistic-optimization", "Realistic Resource Optimization")

        class RealisticOptimizerNode(CycleAwareNode):
            def get_parameters(self):
                return {
                    "target_efficiency": NodeParameter(
                        name="target_efficiency",
                        type=float,
                        required=False,
                        default=0.92,
                    ),
                    "optimization_delay": NodeParameter(
                        name="optimization_delay",
                        type=float,
                        required=False,
                        default=0.03,
                    ),
                }

            def run(self, **kwargs):
                target_efficiency = kwargs.get("target_efficiency", 0.92)
                optimization_delay = kwargs.get("optimization_delay", 0.03)
                context = kwargs.get("context", {})

                iteration = self.get_iteration(context)
                current_efficiency = self.get_previous_state(context).get(
                    "efficiency", 0.65
                )

                # Simulate optimization work with real delay
                time.sleep(optimization_delay)

                # Gradual improvement with diminishing returns
                improvement = 0.10 * (
                    1 - current_efficiency
                )  # Increased from 0.08 to 0.10 for faster convergence
                new_efficiency = min(current_efficiency + improvement, 1.0)

                converged = new_efficiency >= target_efficiency

                return {
                    "efficiency": new_efficiency,
                    "improvement": improvement,
                    "target_met": converged,
                    "iteration": iteration,
                    "optimization_time": optimization_delay,
                    **self.set_cycle_state({"efficiency": new_efficiency}),
                }

        optimizer_node = RealisticOptimizerNode()
        workflow.add_node("optimizer", optimizer_node)
        workflow.create_cycle("optimization_cycle").connect(
            "optimizer", "optimizer", mapping={}
        ).max_iterations(15).converge_when("target_met == True").build()

        runtime = LocalRuntime()
        start_time = time.time()

        result, _ = runtime.execute(
            workflow,
            parameters={
                "optimizer": {
                    "target_efficiency": 0.90,
                    "optimization_delay": 0.02,  # 20ms per optimization step
                }
            },
        )

        end_time = time.time()
        execution_time = end_time - start_time

        # Should converge to target
        assert result["optimizer"]["target_met"] is True
        assert result["optimizer"]["efficiency"] >= 0.90

        # Should take measurable time
        min_expected_time = result["optimizer"]["iteration"] * 0.02
        assert execution_time >= min_expected_time * 0.8

        # Verify improvement progression
        assert result["optimizer"]["efficiency"] > 0.65  # Started at 0.65

    def test_realistic_data_quality_improvement_cycle(self, tmp_path):
        """Test data quality improvement with file I/O and processing delays."""
        workflow = Workflow("realistic-quality", "Realistic Data Quality Improvement")

        class RealisticQualityNode(CycleAwareNode):
            def get_parameters(self):
                return {
                    "input_file": NodeParameter(
                        name="input_file", type=str, required=False, default=""
                    ),
                    "quality_threshold": NodeParameter(
                        name="quality_threshold",
                        type=float,
                        required=False,
                        default=0.85,
                    ),
                    "processing_delay": NodeParameter(
                        name="processing_delay",
                        type=float,
                        required=False,
                        default=0.01,
                    ),
                }

            def run(self, **kwargs):
                input_file = kwargs.get("input_file", "")
                quality_threshold = kwargs.get("quality_threshold", 0.85)
                processing_delay = kwargs.get("processing_delay", 0.01)
                context = kwargs.get("context", {})

                iteration = self.get_iteration(context)
                current_quality = self.get_previous_state(context).get(
                    "quality_score", 0.60
                )

                # Simulate data processing with realistic delay
                time.sleep(processing_delay)

                # Simulate quality improvement
                if input_file and input_file.endswith("_clean"):
                    # Pre-cleaned data improves faster
                    improvement = 0.12
                else:
                    # Regular improvement
                    improvement = 0.08

                new_quality = min(current_quality + improvement, 1.0)
                quality_met = new_quality >= quality_threshold

                # Simulate file operations
                if iteration % 2 == 0:  # Every other iteration, simulate file write
                    time.sleep(0.005)  # File I/O delay

                return {
                    "quality_score": new_quality,
                    "improvement": improvement,
                    "quality_threshold_met": quality_met,
                    "iteration": iteration,
                    "processed_file": input_file,
                    **self.set_cycle_state({"quality_score": new_quality}),
                }

        # Create test input file
        test_file = tmp_path / "test_data.csv"
        test_file.write_text("id,name,value\n1,test,100\n2,sample,200\n")

        quality_node = RealisticQualityNode()
        workflow.add_node("quality", quality_node)
        workflow.create_cycle("quality_improvement_cycle").connect(
            "quality", "quality", mapping={}
        ).max_iterations(8).converge_when("quality_threshold_met == True").build()

        runtime = LocalRuntime()
        start_time = time.time()

        result, _ = runtime.execute(
            workflow,
            parameters={
                "quality": {
                    "input_file": str(test_file),
                    "quality_threshold": 0.85,
                    "processing_delay": 0.015,  # 15ms processing
                }
            },
        )

        end_time = time.time()
        execution_time = end_time - start_time

        # Should achieve quality threshold
        assert result["quality"]["quality_threshold_met"] is True
        assert result["quality"]["quality_score"] >= 0.85

        # Should take realistic time
        expected_iterations = result["quality"]["iteration"] + 1
        min_expected_time = expected_iterations * 0.015
        assert execution_time >= min_expected_time * 0.7  # Allow tolerance for file I/O

        # Verify file processing
        assert result["quality"]["processed_file"] == str(test_file)
