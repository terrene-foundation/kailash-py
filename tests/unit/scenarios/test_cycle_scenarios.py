"""Real-world scenario tests for cyclic workflows.

Tests practical use cases including:
- ETL pipeline with retry cycles
- API polling with backoff cycles
- Data quality improvement cycles
- Resource optimization cycles
- Batch processing with checkpoints
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


class ETLRetryNode(CycleAwareNode):
    """ETL processor with retry capabilities."""

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
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Process data with retry logic."""
        context = kwargs.get("context", {})
        data_source = kwargs.get("data_source", "")
        max_retries = kwargs.get("max_retries", 3)
        retry_delay = kwargs.get("retry_delay", 1.0)

        iteration = self.get_iteration(context)
        prev_state = self.get_previous_state(context)
        retry_count = prev_state.get("retry_count", 0)

        # Simulate ETL operations with potential failures
        try:
            # Simulate connection issues on first attempts
            if iteration < 2 and retry_count == 0:
                raise Exception("Connection timeout")

            # Simulate data processing
            extracted_data = [
                {"id": i, "value": i * 10, "timestamp": time.time()} for i in range(10)
            ]

            # Transform data
            transformed_data = []
            for record in extracted_data:
                transformed = {
                    "id": record["id"],
                    "processed_value": record["value"] * 1.1,
                    "category": "A" if record["value"] < 50 else "B",
                    "processed_at": datetime.now().isoformat(),
                }
                transformed_data.append(transformed)

            # Success
            return {
                "data": transformed_data,
                "status": "success",
                "retry_count": 0,
                "should_retry": False,
                "records_processed": len(transformed_data),
                "iteration": iteration,
                **self.set_cycle_state({"retry_count": 0}),
            }

        except Exception as e:
            # Handle failure with exponential backoff
            new_retry_count = retry_count + 1
            should_retry = new_retry_count <= max_retries

            if should_retry:
                # Exponential backoff
                backoff_delay = retry_delay * (2**retry_count)
                time.sleep(min(backoff_delay, 10))  # Cap at 10 seconds

                self.log_cycle_info(
                    context,
                    f"ETL failed: {str(e)}. Retry {new_retry_count}/{max_retries} after {backoff_delay:.1f}s",
                )

            return {
                "data": [],
                "status": "failed",
                "error": str(e),
                "retry_count": new_retry_count,
                "should_retry": should_retry,
                "records_processed": 0,
                "iteration": iteration,
                **self.set_cycle_state({"retry_count": new_retry_count}),
            }


class APIPollerNode(CycleAwareNode):
    """Polls external API with smart retry and rate limiting."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "endpoint": NodeParameter(
                name="endpoint", type=str, required=False, default=""
            ),
            "poll_interval": NodeParameter(
                name="poll_interval", type=float, required=False, default=5.0
            ),
            "max_polls": NodeParameter(
                name="max_polls", type=int, required=False, default=10
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Poll API with rate limiting and backoff."""
        context = kwargs.get("context", {})
        endpoint = kwargs.get("endpoint", "mock_api")
        poll_interval = kwargs.get("poll_interval", 5.0)
        max_polls = kwargs.get("max_polls", 10)

        iteration = self.get_iteration(context)
        prev_state = self.get_previous_state(context)

        # Track rate limit state
        rate_limit_remaining = prev_state.get("rate_limit_remaining", 100)
        last_poll_time = prev_state.get("last_poll_time", 0)

        # Check rate limiting
        time_since_last = time.time() - last_poll_time
        if time_since_last < poll_interval:
            sleep_time = poll_interval - time_since_last
            time.sleep(sleep_time)

        # Simulate API call
        api_response = self._simulate_api_call(iteration, rate_limit_remaining)

        # Update rate limit tracking
        new_rate_limit = api_response.get(
            "rate_limit_remaining", rate_limit_remaining - 1
        )

        # Determine if we should continue polling
        data_ready = api_response.get("status") == "ready"
        rate_limited = new_rate_limit <= 0
        max_polls_reached = iteration >= max_polls - 1

        should_continue = not data_ready and not rate_limited and not max_polls_reached

        # Adjust poll interval based on response
        if api_response.get("retry_after"):
            new_poll_interval = api_response["retry_after"]
        elif new_rate_limit < 10:
            new_poll_interval = poll_interval * 2  # Slow down when approaching limit
        else:
            new_poll_interval = poll_interval

        self.log_cycle_info(
            context,
            f"Poll {iteration + 1}: Status={api_response.get('status')}, "
            f"Rate limit={new_rate_limit}, Next poll in {new_poll_interval}s",
        )

        return {
            "api_response": api_response,
            "poll_count": iteration + 1,
            "should_continue": should_continue,
            "data_ready": data_ready,
            "rate_limited": rate_limited,
            "poll_interval": new_poll_interval,
            **self.set_cycle_state(
                {"rate_limit_remaining": new_rate_limit, "last_poll_time": time.time()}
            ),
        }

    def _simulate_api_call(self, iteration: int, rate_limit: int) -> dict[str, Any]:
        """Simulate API response with various scenarios."""
        # Simulate different API responses
        if rate_limit <= 0:
            return {
                "status": "rate_limited",
                "rate_limit_remaining": 0,
                "retry_after": 60,
            }

        if iteration < 3:
            return {
                "status": "pending",
                "progress": iteration * 25,
                "rate_limit_remaining": rate_limit - 1,
            }
        elif iteration < 5:
            return {
                "status": "processing",
                "progress": 75 + iteration * 5,
                "rate_limit_remaining": rate_limit - 1,
            }
        else:
            return {
                "status": "ready",
                "data": {"results": [{"id": i, "value": i * 100} for i in range(5)]},
                "rate_limit_remaining": rate_limit - 1,
            }


class DataQualityOptimizerNode(CycleAwareNode):
    """Iteratively improves data quality."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "raw_data": NodeParameter(
                name="raw_data", type=list, required=False, default=[]
            ),
            "quality_rules": NodeParameter(
                name="quality_rules", type=dict, required=False, default={}
            ),
            "target_quality": NodeParameter(
                name="target_quality", type=float, required=False, default=0.95
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Apply quality improvements iteratively."""
        context = kwargs.get("context", {})
        raw_data = kwargs.get("raw_data", [])
        quality_rules = kwargs.get("quality_rules", {})
        target_quality = kwargs.get("target_quality", 0.95)

        iteration = self.get_iteration(context)
        prev_state = self.get_previous_state(context)

        # Get data from previous iteration or use raw data
        data = prev_state.get("improved_data", raw_data)

        # Apply quality improvements based on iteration
        quality_issues = []
        improved_data = []

        for record in data:
            improved_record = record.copy() if isinstance(record, dict) else record
            record_issues = []

            # Check and fix missing values
            if quality_rules.get("required_fields"):
                for field in quality_rules["required_fields"]:
                    if (
                        isinstance(improved_record, dict)
                        and field not in improved_record
                    ):
                        # Impute missing values
                        if field == "category":
                            improved_record[field] = "Unknown"
                        elif field == "value":
                            # Use median from other records
                            values = [
                                r.get(field, 0)
                                for r in data
                                if isinstance(r, dict) and field in r
                            ]
                            improved_record[field] = (
                                sum(values) / len(values) if values else 0
                            )
                        record_issues.append(f"Missing {field}")

            # Check data types
            if quality_rules.get("field_types") and isinstance(improved_record, dict):
                for field, expected_type in quality_rules["field_types"].items():
                    if field in improved_record:
                        try:
                            if expected_type == "int":
                                improved_record[field] = int(improved_record[field])
                            elif expected_type == "float":
                                improved_record[field] = float(improved_record[field])
                            elif expected_type == "str":
                                improved_record[field] = str(improved_record[field])
                        except (ValueError, TypeError):
                            record_issues.append(f"Invalid type for {field}")

            # Check value constraints
            if quality_rules.get("constraints") and isinstance(improved_record, dict):
                for field, constraint in quality_rules["constraints"].items():
                    if field in improved_record:
                        value = improved_record[field]
                        if "min" in constraint and value < constraint["min"]:
                            improved_record[field] = constraint["min"]
                            record_issues.append(f"{field} below minimum")
                        if "max" in constraint and value > constraint["max"]:
                            improved_record[field] = constraint["max"]
                            record_issues.append(f"{field} above maximum")

            improved_data.append(improved_record)
            if record_issues:
                quality_issues.extend(record_issues)

        # Calculate quality score
        total_possible_issues = len(data) * (
            len(quality_rules.get("required_fields", []))
            + len(quality_rules.get("field_types", []))
            + len(quality_rules.get("constraints", []))
        )

        quality_score = (
            1.0 - (len(quality_issues) / total_possible_issues)
            if total_possible_issues > 0
            else 1.0
        )

        # Apply additional improvements in later iterations
        if iteration > 0 and quality_score < target_quality:
            # Detect and fix outliers
            if quality_rules.get("outlier_detection"):
                numeric_fields = [
                    f
                    for f, t in quality_rules.get("field_types", {}).items()
                    if t in ["int", "float"]
                ]
                for field in numeric_fields:
                    values = [
                        r.get(field, 0)
                        for r in improved_data
                        if isinstance(r, dict) and field in r
                    ]
                    if values:
                        mean = sum(values) / len(values)
                        std_dev = (
                            sum((v - mean) ** 2 for v in values) / len(values)
                        ) ** 0.5

                        for record in improved_data:
                            if isinstance(record, dict) and field in record:
                                if abs(record[field] - mean) > 3 * std_dev:
                                    record[field] = mean  # Replace outlier with mean
                                    quality_issues.append(f"Outlier fixed in {field}")

        # Recalculate quality after improvements
        quality_score = min(
            1.0, quality_score + 0.05 * iteration
        )  # Gradual improvement

        converged = quality_score >= target_quality

        if iteration % 2 == 0:
            self.log_cycle_info(
                context,
                f"Quality: {quality_score:.2%}, Issues: {len(quality_issues)}, "
                f"Target: {target_quality:.2%}",
            )

        return {
            "data": improved_data,
            "quality_score": quality_score,
            "quality_issues": quality_issues[:10],  # First 10 issues
            "issue_count": len(quality_issues),
            "converged": converged,
            "iteration": iteration,
            **self.set_cycle_state(
                {
                    "improved_data": improved_data,
                    "quality_history": self.accumulate_values(
                        context, "quality_scores", quality_score, max_history=20
                    ),
                }
            ),
        }


class ResourceOptimizerNode(CycleAwareNode):
    """Optimizes resource allocation iteratively."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "resources": NodeParameter(
                name="resources", type=dict, required=False, default={}
            ),
            "constraints": NodeParameter(
                name="constraints", type=dict, required=False, default={}
            ),
            "optimization_goal": NodeParameter(
                name="optimization_goal", type=str, required=False, default="balanced"
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Optimize resource allocation."""
        context = kwargs.get("context", {})
        resources = kwargs.get("resources", {})
        constraints = kwargs.get("constraints", {})
        optimization_goal = kwargs.get("optimization_goal", "balanced")

        iteration = self.get_iteration(context)
        prev_state = self.get_previous_state(context)

        # Get current allocation or initialize
        current_allocation = prev_state.get(
            "allocation", self._initialize_allocation(resources)
        )

        # Calculate current metrics
        metrics = self._calculate_metrics(current_allocation, resources)

        # Optimize based on goal
        if optimization_goal == "cost":
            new_allocation = self._optimize_for_cost(
                current_allocation, resources, constraints
            )
        elif optimization_goal == "performance":
            new_allocation = self._optimize_for_performance(
                current_allocation, resources, constraints
            )
        else:  # balanced
            new_allocation = self._optimize_balanced(
                current_allocation, resources, constraints
            )

        # Calculate new metrics
        new_metrics = self._calculate_metrics(new_allocation, resources)

        # Check convergence (improvement < 1%)
        improvement = abs(new_metrics["efficiency"] - metrics["efficiency"])
        converged = improvement < 0.01 and iteration >= 5  # Need at least 5 iterations

        # Track optimization history
        efficiency_history = self.accumulate_values(
            context, "efficiency_history", new_metrics["efficiency"], max_history=30
        )

        if iteration % 3 == 0:
            self.log_cycle_info(
                context,
                f"Optimization: Cost=${new_metrics['total_cost']:.2f}, "
                f"Performance={new_metrics['total_performance']:.1f}, "
                f"Efficiency={new_metrics['efficiency']:.2%}",
            )

        return {
            "allocation": new_allocation,
            "metrics": new_metrics,
            "improvement": improvement,
            "converged": converged,
            "iteration": iteration,
            "efficiency_trend": efficiency_history[-5:],
            **self.set_cycle_state(
                {"allocation": new_allocation, "efficiency_history": efficiency_history}
            ),
        }

    def _initialize_allocation(self, resources: dict) -> dict:
        """Initialize resource allocation."""
        resources.get("budget", 1000)
        resource_types = resources.get("types", ["compute", "storage", "network"])

        # Equal initial allocation
        allocation = {}
        for resource_type in resource_types:
            allocation[resource_type] = {
                "units": 10,
                "cost_per_unit": resources.get(f"{resource_type}_cost", 10),
                "performance_per_unit": resources.get(
                    f"{resource_type}_performance", 1
                ),
            }

        return allocation

    def _calculate_metrics(self, allocation: dict, resources: dict) -> dict:
        """Calculate allocation metrics."""
        total_cost = 0
        total_performance = 0

        for resource_type, config in allocation.items():
            cost = config["units"] * config["cost_per_unit"]
            performance = config["units"] * config["performance_per_unit"]
            total_cost += cost
            total_performance += performance

        efficiency = total_performance / total_cost if total_cost > 0 else 0

        return {
            "total_cost": total_cost,
            "total_performance": total_performance,
            "efficiency": efficiency,
            "cost_breakdown": {
                k: v["units"] * v["cost_per_unit"] for k, v in allocation.items()
            },
        }

    def _optimize_for_cost(
        self, allocation: dict, resources: dict, constraints: dict
    ) -> dict:
        """Optimize for minimum cost."""
        new_allocation = {}
        constraints.get("max_budget", 1000)
        constraints.get("min_performance", 50)

        # Reduce expensive resources
        for resource_type, config in allocation.items():
            new_config = config.copy()
            if new_config["cost_per_unit"] > 15:
                new_config["units"] = max(1, int(config["units"] * 0.9))
            else:
                new_config["units"] = min(20, int(config["units"] * 1.1))
            new_allocation[resource_type] = new_config

        return new_allocation

    def _optimize_for_performance(
        self, allocation: dict, resources: dict, constraints: dict
    ) -> dict:
        """Optimize for maximum performance."""
        new_allocation = {}
        constraints.get("max_budget", 1000)

        # Increase high-performance resources
        for resource_type, config in allocation.items():
            new_config = config.copy()
            if new_config["performance_per_unit"] > 1.5:
                new_config["units"] = min(30, int(config["units"] * 1.2))
            else:
                new_config["units"] = max(1, int(config["units"] * 0.95))
            new_allocation[resource_type] = new_config

        return new_allocation

    def _optimize_balanced(
        self, allocation: dict, resources: dict, constraints: dict
    ) -> dict:
        """Optimize for balanced cost/performance."""
        new_allocation = {}

        for resource_type, config in allocation.items():
            new_config = config.copy()
            efficiency = config["performance_per_unit"] / config["cost_per_unit"]

            if efficiency > 0.2:
                new_config["units"] = min(25, int(config["units"] * 1.05))
            else:
                new_config["units"] = max(1, int(config["units"] * 0.98))

            new_allocation[resource_type] = new_config

        return new_allocation


class BatchProcessorNode(CycleAwareNode):
    """Processes data in batches with checkpointing."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "total_records": NodeParameter(
                name="total_records", type=int, required=False, default=1000
            ),
            "batch_size": NodeParameter(
                name="batch_size", type=int, required=False, default=100
            ),
            "processing_time": NodeParameter(
                name="processing_time", type=float, required=False, default=0.1
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Process batch with checkpointing."""
        context = kwargs.get("context", {})
        total_records = kwargs.get("total_records", 1000)
        batch_size = kwargs.get("batch_size", 100)
        processing_time = kwargs.get("processing_time", 0.1)

        iteration = self.get_iteration(context)
        prev_state = self.get_previous_state(context)

        # Get checkpoint
        processed_count = prev_state.get("processed_count", 0)
        prev_state.get("checkpoint_data", {})

        # Calculate batch range
        batch_start = processed_count
        batch_end = min(batch_start + batch_size, total_records)

        # Simulate batch processing
        batch_data = []
        for i in range(batch_start, batch_end):
            # Simulate processing with potential failure
            if i == 250 and iteration < 3:  # Simulate failure at record 250
                raise Exception(f"Processing failed at record {i}")

            processed_record = {
                "id": i,
                "original_value": i * 10,
                "processed_value": i * 10 * 1.1,
                "batch_number": iteration,
                "processed_at": time.time(),
            }
            batch_data.append(processed_record)

            # Simulate processing time
            time.sleep(processing_time / 100)  # Scaled down for testing

        # Update checkpoint
        new_processed_count = batch_end
        progress = new_processed_count / total_records

        # Create checkpoint data
        new_checkpoint = {
            "batch_number": iteration,
            "processed_count": new_processed_count,
            "last_successful_id": batch_end - 1,
            "timestamp": time.time(),
            "progress_percent": progress * 100,
        }

        # Check if processing is complete
        all_processed = new_processed_count >= total_records

        if iteration % 5 == 0 or all_processed:
            self.log_cycle_info(
                context,
                f"Batch {iteration}: Processed {new_processed_count}/{total_records} "
                f"({progress:.1%} complete)",
            )

        return {
            "batch_data": batch_data,
            "batch_size": len(batch_data),
            "checkpoint": new_checkpoint,
            "progress": progress,
            "all_processed": all_processed,
            "records_remaining": total_records - new_processed_count,
            **self.set_cycle_state(
                {
                    "processed_count": new_processed_count,
                    "checkpoint_data": new_checkpoint,
                    "batch_history": self.accumulate_values(
                        context, "batches", iteration, max_history=10
                    ),
                }
            ),
        }


class TestETLRetryPipeline:
    """Test ETL pipeline with retry capabilities."""

    def test_etl_with_exponential_backoff(self, tmp_path):
        """Test ETL pipeline with connection failures and exponential backoff."""
        workflow = Workflow("etl-retry", "ETL Pipeline with Retry")

        # Single ETL node that handles everything including retry logic
        class ETLWithConditionalRetryNode(CycleAwareNode):
            """ETL processor with built-in retry decision logic."""

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
                    "output_file": NodeParameter(
                        name="output_file", type=str, required=False, default=""
                    ),
                }

            def run(self, **kwargs) -> dict[str, Any]:
                """Process data with retry logic and save on success."""
                context = kwargs.get("context", {})
                data_source = kwargs.get("data_source", "")
                max_retries = kwargs.get("max_retries", 3)
                retry_delay = kwargs.get("retry_delay", 1.0)
                output_file = kwargs.get("output_file", "")

                iteration = self.get_iteration(context)
                prev_state = self.get_previous_state(context)
                retry_count = prev_state.get("retry_count", 0)

                # Simulate ETL operations with potential failures
                try:
                    # Simulate connection issues on first attempts
                    if iteration < 2 and retry_count == 0:
                        raise Exception("Connection timeout")

                    # Simulate data processing
                    extracted_data = [
                        {"id": i, "value": i * 10, "timestamp": time.time()}
                        for i in range(10)
                    ]

                    # Transform data
                    transformed_data = []
                    for record in extracted_data:
                        transformed = {
                            "id": record["id"],
                            "processed_value": record["value"] * 1.1,
                            "category": "A" if record["value"] < 50 else "B",
                            "processed_at": datetime.now().isoformat(),
                        }
                        transformed_data.append(transformed)

                    # Save to file on success
                    if output_file:
                        with open(output_file, "w") as f:
                            json.dump(
                                {"data": transformed_data, "status": "success"}, f
                            )

                    # Success
                    self.set_cycle_state({"retry_count": 0})

                    return {
                        "data": transformed_data,
                        "status": "success",
                        "retry_count": 0,
                        "should_retry": False,
                        "records_processed": len(transformed_data),
                        "iteration": iteration,
                        "data_source": data_source,
                        "max_retries": max_retries,
                        "retry_delay": retry_delay,
                        "output_file": output_file,
                        "converged": True,  # Success means we're done
                    }

                except Exception as e:
                    # Handle failure with exponential backoff
                    new_retry_count = retry_count + 1
                    should_retry = new_retry_count <= max_retries

                    if should_retry:
                        # Exponential backoff
                        backoff_delay = retry_delay * (2**retry_count)
                        time.sleep(min(backoff_delay, 0.1))  # Cap at 0.1s for tests

                        self.log_cycle_info(
                            context,
                            f"ETL failed: {str(e)}. Retry {new_retry_count}/{max_retries} "
                            f"after {backoff_delay:.1f}s",
                        )

                    self.set_cycle_state({"retry_count": new_retry_count})

                    return {
                        "data": None,
                        "status": "failed",
                        "error": str(e),
                        "retry_count": new_retry_count,
                        "should_retry": should_retry,
                        "records_processed": 0,
                        "iteration": iteration,
                        "data_source": data_source,
                        "max_retries": max_retries,
                        "retry_delay": retry_delay,
                        "output_file": output_file,
                        "converged": not should_retry,  # Stop if no more retries
                    }

        # Single node workflow
        workflow.add_node("etl_processor", ETLWithConditionalRetryNode())

        # Create retry cycle
        workflow.connect(
            "etl_processor",
            "etl_processor",
            mapping={
                "data_source": "data_source",
                "max_retries": "max_retries",
                "retry_delay": "retry_delay",
                "output_file": "output_file",
            },
            cycle=True,
            max_iterations=10,
            convergence_check="converged == True",
        )

        # Execute pipeline
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "etl_processor": {
                    "data_source": "test_database",
                    "max_retries": 3,
                    "retry_delay": 0.1,  # Short delay for testing
                    "output_file": str(tmp_path / "etl_output.json"),
                }
            },
        )

        # Verify ETL succeeded after retries
        assert run_id is not None
        etl_result = results.get("etl_processor", {})
        assert etl_result.get("status") == "success"
        assert etl_result.get("records_processed", 0) > 0
        assert etl_result.get("iteration", 0) >= 2  # Should have retried

        # Verify data was saved
        assert (tmp_path / "etl_output.json").exists()


class TestAPIPollingScenario:
    """Test API polling with rate limiting and backoff."""

    def test_api_polling_with_rate_limits(self):
        """Test API polling that respects rate limits."""
        workflow = Workflow("api-polling", "API Polling with Rate Limits")

        # Single API poller node that handles all polling logic
        class APIPollerWithConditionalContinueNode(CycleAwareNode):
            """API poller with built-in continuation logic."""

            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "endpoint": NodeParameter(
                        name="endpoint", type=str, required=False, default=""
                    ),
                    "poll_interval": NodeParameter(
                        name="poll_interval", type=float, required=False, default=5.0
                    ),
                    "max_polls": NodeParameter(
                        name="max_polls", type=int, required=False, default=10
                    ),
                }

            def run(self, **kwargs) -> dict[str, Any]:
                """Poll API with rate limiting and process when ready."""
                endpoint = kwargs.get("endpoint", "mock_api")
                poll_interval = kwargs.get("poll_interval", 5.0)
                max_polls = kwargs.get("max_polls", 10)
                context = kwargs.get("context", {})

                iteration = self.get_iteration(context)
                prev_state = self.get_previous_state(context)

                # Track rate limit state
                rate_limit_remaining = prev_state.get("rate_limit_remaining", 100)
                last_poll_time = prev_state.get("last_poll_time", 0)

                # Check rate limiting
                time_since_last = time.time() - last_poll_time
                if time_since_last < poll_interval:
                    sleep_time = poll_interval - time_since_last
                    time.sleep(sleep_time)

                # Simulate API response
                if rate_limit_remaining <= 0:
                    api_response = {
                        "status": "rate_limited",
                        "rate_limit_remaining": 0,
                        "retry_after": 60,
                    }
                elif iteration < 3:
                    api_response = {
                        "status": "pending",
                        "progress": iteration * 25,
                        "rate_limit_remaining": rate_limit_remaining - 1,
                    }
                elif iteration < 5:
                    api_response = {
                        "status": "processing",
                        "progress": 75 + iteration * 5,
                        "rate_limit_remaining": rate_limit_remaining - 1,
                    }
                else:
                    api_response = {
                        "status": "ready",
                        "data": {
                            "results": [{"id": i, "value": i * 100} for i in range(5)]
                        },
                        "rate_limit_remaining": rate_limit_remaining - 1,
                    }

                # Update rate limit tracking
                new_rate_limit = api_response.get(
                    "rate_limit_remaining", rate_limit_remaining - 1
                )

                # Determine if we should continue polling
                data_ready = api_response.get("status") == "ready"
                rate_limited = new_rate_limit <= 0
                max_polls_reached = iteration >= max_polls - 1

                # Process data if ready
                if data_ready:
                    processed_data = api_response.get("data", {}).get("results", [])
                    success = True
                    error = None
                elif rate_limited:
                    processed_data = []
                    success = False
                    error = "Rate limited"
                else:
                    processed_data = []
                    success = False
                    error = (
                        "Max polls reached" if max_polls_reached else "Still processing"
                    )

                self.log_cycle_info(
                    context,
                    f"Poll {iteration + 1}: Status={api_response.get('status')}, "
                    f"Rate limit={new_rate_limit}",
                )

                self.set_cycle_state(
                    {
                        "rate_limit_remaining": new_rate_limit,
                        "last_poll_time": time.time(),
                    }
                )

                return {
                    "api_response": api_response,
                    "poll_count": iteration + 1,
                    "data_ready": data_ready,
                    "rate_limited": rate_limited,
                    "processed_data": processed_data,
                    "success": success,
                    "error": error,
                    "endpoint": endpoint,
                    "poll_interval": poll_interval,
                    "max_polls": max_polls,
                    "converged": data_ready or rate_limited or max_polls_reached,
                }

        # Single node workflow
        workflow.add_node("api_poller", APIPollerWithConditionalContinueNode())

        # Create polling cycle
        workflow.connect(
            "api_poller",
            "api_poller",
            mapping={
                "endpoint": "endpoint",
                "poll_interval": "poll_interval",
                "max_polls": "max_polls",
            },
            cycle=True,
            max_iterations=20,
            convergence_check="converged == True",
        )

        # Execute polling
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "api_poller": {
                    "endpoint": "https://api.example.com/job/status",
                    "poll_interval": 0.5,  # Fast polling for test
                    "max_polls": 10,
                }
            },
        )

        # Verify polling behavior
        assert run_id is not None
        poller_result = results.get("api_poller", {})
        assert poller_result.get("data_ready") is True
        assert poller_result.get("poll_count", 0) > 3  # Should take several polls

        # Verify rate limiting worked
        assert not poller_result.get("rate_limited", False)

        # Check data was processed
        assert poller_result.get("success") is True
        assert len(poller_result.get("processed_data", [])) > 0


class TestDataQualityImprovement:
    """Test iterative data quality improvement scenarios."""

    def test_data_quality_optimization_cycle(self, tmp_path):
        """Test data quality improvement with multiple rules."""
        # Build quality improvement workflow
        workflow = Workflow("quality-improvement", "Data Quality Optimization")

        # Single node that handles data quality improvement
        class DataQualityWithConvergenceNode(CycleAwareNode):
            """Improve data quality with built-in convergence."""

            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "raw_data": NodeParameter(
                        name="raw_data", type=list, required=False, default=[]
                    ),
                    "quality_rules": NodeParameter(
                        name="quality_rules", type=dict, required=False, default={}
                    ),
                    "target_quality": NodeParameter(
                        name="target_quality", type=float, required=False, default=0.95
                    ),
                    "output_file": NodeParameter(
                        name="output_file", type=str, required=False, default=""
                    ),
                }

            def run(self, **kwargs) -> dict[str, Any]:
                """Apply quality improvements and save when converged."""
                raw_data = kwargs.get("raw_data", [])
                quality_rules = kwargs.get("quality_rules", {})
                target_quality = kwargs.get("target_quality", 0.95)
                output_file = kwargs.get("output_file", "")
                context = kwargs.get("context", {})

                iteration = self.get_iteration(context)
                prev_state = self.get_previous_state(context)

                # Use test data on first iteration
                if iteration == 0 and not raw_data:
                    # Default test data with quality issues
                    raw_data = [
                        {
                            "id": 1,
                            "name": "Product A",
                            "value": 100,
                            "category": "Electronics",
                        },
                        {
                            "id": 2,
                            "name": "Product B",
                            "value": -50,
                        },  # Missing category, negative value
                        {"id": 3, "value": 200, "category": "Books"},  # Missing name
                        {
                            "id": 4,
                            "name": "Product D",
                            "value": 5000,
                            "category": "Furniture",
                        },  # Outlier
                        {
                            "id": 5,
                            "name": "",
                            "value": "invalid",
                            "category": "Electronics",
                        },  # Invalid
                        {"name": "Product F", "value": 300},  # Missing id and category
                        {
                            "id": 7,
                            "name": "Product G",
                            "value": 250,
                            "category": "",
                        },  # Empty category
                    ]

                # Get data from previous iteration or use raw data
                data = prev_state.get("improved_data", raw_data)

                # Apply quality improvements
                quality_issues = []
                improved_data = []

                for record in data:
                    improved_record = (
                        record.copy() if isinstance(record, dict) else record
                    )
                    record_issues = []

                    # Fix missing fields
                    if quality_rules.get("required_fields"):
                        for field in quality_rules["required_fields"]:
                            if (
                                isinstance(improved_record, dict)
                                and field not in improved_record
                            ):
                                if field == "category":
                                    improved_record[field] = "Unknown"
                                elif field == "value":
                                    improved_record[field] = 0
                                elif field == "name":
                                    improved_record[field] = "Unknown Product"
                                elif field == "id":
                                    improved_record[field] = (
                                        hash(str(improved_record)) % 1000
                                    )
                                record_issues.append(f"Missing {field}")

                    # Fix data types
                    if quality_rules.get("field_types") and isinstance(
                        improved_record, dict
                    ):
                        for field, expected_type in quality_rules[
                            "field_types"
                        ].items():
                            if field in improved_record:
                                try:
                                    if expected_type == "int":
                                        improved_record[field] = int(
                                            improved_record[field]
                                        )
                                    elif expected_type == "float":
                                        improved_record[field] = float(
                                            improved_record[field]
                                        )
                                    elif expected_type == "str":
                                        improved_record[field] = str(
                                            improved_record[field]
                                        )
                                except (ValueError, TypeError):
                                    record_issues.append(f"Invalid type for {field}")
                                    # Set default values
                                    if expected_type == "int":
                                        improved_record[field] = 0
                                    elif expected_type == "float":
                                        improved_record[field] = 0.0
                                    elif expected_type == "str":
                                        improved_record[field] = ""

                    # Apply constraints
                    if quality_rules.get("constraints") and isinstance(
                        improved_record, dict
                    ):
                        for field, constraint in quality_rules["constraints"].items():
                            if field in improved_record:
                                try:
                                    value = float(improved_record[field])
                                    if (
                                        "min" in constraint
                                        and value < constraint["min"]
                                    ):
                                        improved_record[field] = constraint["min"]
                                        record_issues.append(f"{field} below minimum")
                                    if (
                                        "max" in constraint
                                        and value > constraint["max"]
                                    ):
                                        improved_record[field] = constraint["max"]
                                        record_issues.append(f"{field} above maximum")
                                except (ValueError, TypeError):
                                    improved_record[field] = constraint.get("min", 0)

                    improved_data.append(improved_record)
                    if record_issues:
                        quality_issues.extend(record_issues)

                # Calculate quality score
                total_possible_issues = len(data) * (
                    len(quality_rules.get("required_fields", []))
                    + len(quality_rules.get("field_types", []))
                    + len(quality_rules.get("constraints", []))
                )

                quality_score = (
                    1.0 - (len(quality_issues) / total_possible_issues)
                    if total_possible_issues > 0
                    else 1.0
                )

                # Gradual improvement
                quality_score = min(1.0, quality_score + 0.05 * iteration)

                converged = quality_score >= target_quality

                # Save if converged and output file specified
                if converged and output_file:
                    with open(output_file, "w") as f:
                        json.dump(improved_data, f)

                self.log_cycle_info(
                    context,
                    f"Quality: {quality_score:.2%}, Issues: {len(quality_issues)}, "
                    f"Target: {target_quality:.2%}",
                )

                self.set_cycle_state({"improved_data": improved_data})

                return {
                    "data": improved_data,
                    "quality_score": quality_score,
                    "quality_issues": quality_issues[:10],
                    "issue_count": len(quality_issues),
                    "converged": converged,
                    "iteration": iteration,
                    "raw_data": raw_data,
                    "quality_rules": quality_rules,
                    "target_quality": target_quality,
                    "output_file": output_file,
                }

        # Single node workflow
        workflow.add_node("quality_improver", DataQualityWithConvergenceNode())

        # Create quality improvement cycle
        workflow.connect(
            "quality_improver",
            "quality_improver",
            mapping={
                "raw_data": "raw_data",
                "quality_rules": "quality_rules",
                "target_quality": "target_quality",
                "output_file": "output_file",
            },
            cycle=True,
            max_iterations=15,
            convergence_check="converged == True",
        )

        # Execute quality improvement
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "quality_improver": {
                    "quality_rules": {
                        "required_fields": ["id", "name", "value", "category"],
                        "field_types": {
                            "id": "int",
                            "name": "str",
                            "value": "float",
                            "category": "str",
                        },
                        "constraints": {"value": {"min": 0, "max": 1000}},
                        "outlier_detection": True,
                    },
                    "target_quality": 0.90,
                    "output_file": str(tmp_path / "quality_improved.json"),
                }
            },
        )

        # Verify quality improvement
        assert run_id is not None
        optimizer_result = results.get("quality_improver", {})
        assert optimizer_result.get("quality_score", 0) >= 0.90
        assert (
            optimizer_result.get("iteration", 0) > 0
        )  # Should take multiple iterations

        # Check improved data
        assert (tmp_path / "quality_improved.json").exists()
        with open(tmp_path / "quality_improved.json") as f:
            improved_data = json.load(f)

            # All records should have required fields
            for record in improved_data:
                assert all(
                    field in record for field in ["id", "name", "value", "category"]
                )
                assert isinstance(record["value"], (int, float))
                assert 0 <= record["value"] <= 1000  # Constraints applied


class TestResourceOptimization:
    """Test resource optimization scenarios."""

    def test_cloud_resource_optimization(self):
        """Test iterative cloud resource optimization."""
        workflow = Workflow("resource-optimization", "Cloud Resource Optimizer")

        # Single resource optimizer node
        workflow.add_node("optimizer", ResourceOptimizerNode())

        # Create optimization cycle
        workflow.connect(
            "optimizer",
            "optimizer",
            mapping={
                "resources": "resources",
                "constraints": "constraints",
                "optimization_goal": "optimization_goal",
            },
            cycle=True,
            max_iterations=30,
            convergence_check="converged == True",
        )

        # Execute optimization
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "optimizer": {
                    "resources": {
                        "budget": 5000,
                        "types": ["compute", "storage", "network"],
                        "compute_cost": 20,
                        "compute_performance": 2.5,
                        "storage_cost": 5,
                        "storage_performance": 1.0,
                        "network_cost": 15,
                        "network_performance": 2.0,
                    },
                    "constraints": {"max_budget": 5000, "min_performance": 100},
                    "optimization_goal": "balanced",
                }
            },
        )

        # Verify optimization results
        assert run_id is not None
        optimizer_result = results.get("optimizer", {})

        # Check convergence
        assert optimizer_result.get("converged") is True
        assert (
            optimizer_result.get("iteration", 0) >= 5
        )  # Should optimize for at least 5 iterations

        # Verify metrics improved
        metrics = optimizer_result.get("metrics", {})
        assert metrics.get("total_cost", 0) <= 5000  # Within budget
        assert metrics.get("total_performance", 0) > 0  # Has performance
        assert metrics.get("efficiency", 0) > 0  # Has efficiency metric


class TestBatchProcessingCheckpoints:
    """Test batch processing with checkpoint recovery."""

    def test_batch_processing_with_checkpoints(self, tmp_path):
        """Test batch processing that can recover from failures."""
        workflow = Workflow("batch-processing", "Batch Processing with Checkpoints")

        # Single batch processor node that handles everything
        class BatchProcessorWithCheckpointsNode(CycleAwareNode):
            """Process batches with checkpointing and aggregation."""

            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "total_records": NodeParameter(
                        name="total_records", type=int, required=False, default=1000
                    ),
                    "batch_size": NodeParameter(
                        name="batch_size", type=int, required=False, default=100
                    ),
                    "processing_time": NodeParameter(
                        name="processing_time", type=float, required=False, default=0.1
                    ),
                    "processed_count": NodeParameter(
                        name="processed_count", type=int, required=False, default=0
                    ),
                }

            def run(self, **kwargs) -> dict[str, Any]:
                """Process batch with checkpointing and aggregation."""
                total_records = kwargs.get("total_records", 1000)
                batch_size = kwargs.get("batch_size", 100)
                processing_time = kwargs.get("processing_time", 0.1)
                context = kwargs.get("context", {})

                iteration = self.get_iteration(context)
                prev_state = self.get_previous_state(context)

                # Get checkpoint - use parameter if available (from cycle), else state
                if iteration > 0:
                    processed_count = kwargs.get(
                        "processed_count", prev_state.get("processed_count", 0)
                    )
                else:
                    processed_count = 0
                checkpoint_data = prev_state.get("checkpoint_data", {})
                aggregated_results = prev_state.get("aggregated_results", [])

                # Calculate batch range
                batch_start = processed_count
                batch_end = min(batch_start + batch_size, total_records)

                # Simulate batch processing
                batch_data = []
                try:
                    for i in range(batch_start, batch_end):
                        # Simulate processing with potential failure
                        if i == 250 and iteration < 3:  # Simulate failure at record 250
                            raise Exception(f"Processing failed at record {i}")

                        processed_record = {
                            "id": i,
                            "original_value": i * 10,
                            "processed_value": i * 10 * 1.1,
                            "batch_number": iteration,
                            "processed_at": time.time(),
                        }
                        batch_data.append(processed_record)

                        # Simulate processing time
                        time.sleep(processing_time / 100)  # Scaled down for testing

                    # Success - update checkpoint
                    new_processed_count = batch_end
                    progress = new_processed_count / total_records

                    # Create checkpoint data
                    new_checkpoint = {
                        "batch_number": iteration,
                        "processed_count": new_processed_count,
                        "last_successful_id": batch_end - 1,
                        "timestamp": time.time(),
                        "progress_percent": progress * 100,
                    }

                    # Aggregate results
                    aggregated_results.extend(batch_data)

                except Exception as e:
                    # Failure - restore from checkpoint
                    self.log_cycle_info(context, f"Batch processing failed: {str(e)}")
                    new_processed_count = processed_count  # Don't update count
                    progress = processed_count / total_records
                    new_checkpoint = checkpoint_data  # Keep old checkpoint
                    # Don't add failed batch to aggregated results

                # Check if processing is complete
                all_processed = new_processed_count >= total_records

                # Calculate aggregated metrics
                total_records_processed = (
                    new_processed_count  # Use the total count, not just aggregated
                )
                final_batch_number = iteration
                last_record_id = (
                    new_processed_count - 1 if new_processed_count > 0 else -1
                )

                if iteration % 5 == 0 or all_processed:
                    self.log_cycle_info(
                        context,
                        f"Batch {iteration}: Processed {new_processed_count}/{total_records} "
                        f"({progress:.1%} complete)",
                    )

                self.set_cycle_state(
                    {
                        "processed_count": new_processed_count,
                        "checkpoint_data": new_checkpoint,
                        "aggregated_results": aggregated_results[
                            -1000:
                        ],  # Keep last 1000 for memory
                    }
                )

                return {
                    "batch_data": batch_data,
                    "batch_size": len(batch_data),
                    "checkpoint": new_checkpoint,
                    "progress": progress,
                    "all_processed": all_processed,
                    "records_remaining": total_records - new_processed_count,
                    "total_records_processed": total_records_processed,
                    "final_batch_number": final_batch_number,
                    "processing_complete": all_processed,
                    "last_record_id": last_record_id,
                    "total_records": total_records,
                    "processed_count": new_processed_count,  # CRITICAL: pass this through the cycle
                    "converged": all_processed,
                }

        # Single node workflow
        workflow.add_node("batch_processor", BatchProcessorWithCheckpointsNode())

        # Create processing cycle
        workflow.connect(
            "batch_processor",
            "batch_processor",
            mapping={
                "total_records": "total_records",
                "batch_size": "batch_size",
                "processing_time": "processing_time",
                "processed_count": "processed_count",
            },
            cycle=True,
            max_iterations=50,  # Enough for 500 records with batch size 50
            convergence_check="converged == True",
        )

        # Execute batch processing
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "batch_processor": {
                    "total_records": 500,
                    "batch_size": 50,
                    "processing_time": 0.001,  # Fast processing for test
                }
            },
        )

        # Verify batch processing completed
        assert run_id is not None

        processor_result = results.get("batch_processor", {})
        assert processor_result.get("all_processed") is True
        assert processor_result.get("progress", 0) >= 1.0

        # Check aggregated results
        assert processor_result.get("total_records_processed") == 500
        assert processor_result.get("processing_complete") is True
        assert (
            processor_result.get("final_batch_number", 0) == 9
        )  # 500/50 = 10 batches (0-indexed)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
