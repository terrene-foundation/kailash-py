"""Simplified real-world scenario tests for cyclic workflows.

These tests demonstrate practical cyclic workflow patterns using
simplified implementations that work with the current architecture.
"""

import time
from typing import Any

from kailash import Workflow
from kailash.nodes.base import NodeParameter
from kailash.nodes.base_cycle_aware import CycleAwareNode
from kailash.runtime.local import LocalRuntime


class SimpleETLWithRetryNode(CycleAwareNode):
    """Simple ETL processor that demonstrates retry patterns."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "data_source": NodeParameter(
                name="data_source", type=str, required=False, default=""
            ),
            "max_retries": NodeParameter(
                name="max_retries", type=int, required=False, default=3
            ),
            "success_rate": NodeParameter(
                name="success_rate", type=float, required=False, default=0.3
            ),
        }

    def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Process data with simulated retry logic."""
        data_source = kwargs.get("data_source", "test_db")
        max_retries = kwargs.get("max_retries", 3)
        success_rate = kwargs.get("success_rate", 0.3)

        iteration = self.get_iteration(context)
        prev_state = self.get_previous_state(context)

        # Track retry history
        retry_history = prev_state.get("retry_history", [])

        # Simulate success after a few retries
        # Use iteration count to ensure deterministic test behavior
        if iteration >= 2 or iteration / max_retries > success_rate:
            # Success!
            success = True
            status = "completed"
            data = {"processed_records": 1000, "source": data_source}
            message = f"ETL succeeded after {iteration} retries"
        else:
            # Failure - need to retry
            success = False
            status = "failed"
            data = None
            message = f"ETL failed on attempt {iteration + 1}, retrying..."

        retry_history.append(
            {"attempt": iteration + 1, "success": success, "timestamp": time.time()}
        )

        self.set_cycle_state({"retry_history": retry_history})

        return {
            "success": success,
            "status": status,
            "data": data,
            "message": message,
            "retry_count": iteration + 1,
            "data_source": data_source,
            "max_retries": max_retries,
            "success_rate": success_rate,
            "converged": success or iteration >= max_retries - 1,
        }


class SimpleAPIPollerNode(CycleAwareNode):
    """Simple API poller that demonstrates polling patterns."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "endpoint": NodeParameter(
                name="endpoint", type=str, required=False, default=""
            ),
            "max_polls": NodeParameter(
                name="max_polls", type=int, required=False, default=10
            ),
            "target_status": NodeParameter(
                name="target_status", type=str, required=False, default="ready"
            ),
        }

    def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Poll API with simulated responses."""
        endpoint = kwargs.get("endpoint", "/api/status")
        max_polls = kwargs.get("max_polls", 10)
        target_status = kwargs.get("target_status", "ready")

        iteration = self.get_iteration(context)
        prev_state = self.get_previous_state(context)

        # Track polling history
        poll_history = prev_state.get("poll_history", [])

        # Simulate API becoming ready after a few polls
        if iteration >= 3:
            status = target_status
            ready = True
            data = {"result": "processed", "items": 42}
        else:
            status = "pending"
            ready = False
            data = None

        poll_history.append(
            {"poll_number": iteration + 1, "status": status, "timestamp": time.time()}
        )

        self.set_cycle_state({"poll_history": poll_history})

        return {
            "ready": ready,
            "status": status,
            "data": data,
            "poll_count": iteration + 1,
            "endpoint": endpoint,
            "max_polls": max_polls,
            "target_status": target_status,
            "converged": ready or iteration >= max_polls - 1,
        }


class SimpleDataQualityNode(CycleAwareNode):
    """Simple data quality improver that demonstrates iterative refinement."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[]),
            "target_quality": NodeParameter(
                name="target_quality", type=float, required=False, default=0.9
            ),
            "improvement_rate": NodeParameter(
                name="improvement_rate", type=float, required=False, default=0.2
            ),
        }

    def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Improve data quality iteratively."""
        data = kwargs.get("data", [])
        target_quality = kwargs.get("target_quality", 0.9)
        improvement_rate = kwargs.get("improvement_rate", 0.2)

        iteration = self.get_iteration(context)
        prev_state = self.get_previous_state(context)

        # Track quality history
        quality_history = prev_state.get("quality_history", [])

        # Simulate quality improvement
        base_quality = 0.4
        current_quality = min(base_quality + (iteration * improvement_rate), 1.0)

        # Simulate data cleaning
        if not data:
            cleaned_data = list(range(10))  # Default data
        else:
            # Remove "bad" data based on quality score
            threshold = int(len(data) * (1 - current_quality))
            cleaned_data = data[threshold:] if threshold < len(data) else data

        quality_history.append(
            {
                "iteration": iteration + 1,
                "quality_score": current_quality,
                "data_size": len(cleaned_data),
            }
        )

        self.set_cycle_state({"quality_history": quality_history})

        converged = current_quality >= target_quality or iteration >= 10

        return {
            "data": cleaned_data,
            "quality_score": current_quality,
            "iteration_count": iteration + 1,
            "quality_history": quality_history,
            "target_quality": target_quality,
            "improvement_rate": improvement_rate,
            "converged": converged,
        }


class TestSimplifiedScenarios:
    """Test simplified real-world scenarios."""

    def test_etl_retry_pattern(self):
        """Test ETL with retry pattern using cycles."""
        workflow = Workflow("etl-retry-simple", "Simple ETL Retry")

        # Single node that handles ETL with retry logic
        workflow.add_node("etl", SimpleETLWithRetryNode())

        # Create retry cycle
        workflow.connect(
            "etl",
            "etl",
            mapping={
                "data_source": "data_source",
                "max_retries": "max_retries",
                "success_rate": "success_rate",
            },
            cycle=True,
            max_iterations=5,
            convergence_check="converged == True",
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "etl": {
                    "data_source": "production_db",
                    "max_retries": 5,
                    "success_rate": 0.3,
                }
            },
        )

        assert run_id is not None
        final_result = results["etl"]

        # Should succeed after a few retries
        assert final_result["success"] is True
        assert final_result["status"] == "completed"
        assert final_result["data"] is not None
        assert final_result["retry_count"] >= 1
        assert final_result["converged"] is True

    def test_api_polling_pattern(self):
        """Test API polling pattern using cycles."""
        workflow = Workflow("api-poll-simple", "Simple API Polling")

        # Single node that handles polling logic
        workflow.add_node("poller", SimpleAPIPollerNode())

        # Create polling cycle
        workflow.connect(
            "poller",
            "poller",
            mapping={
                "endpoint": "endpoint",
                "max_polls": "max_polls",
                "target_status": "target_status",
            },
            cycle=True,
            max_iterations=10,
            convergence_check="converged == True",
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "poller": {
                    "endpoint": "/api/job/123",
                    "max_polls": 10,
                    "target_status": "ready",
                }
            },
        )

        assert run_id is not None
        final_result = results["poller"]

        # Should become ready after a few polls
        assert final_result["ready"] is True
        assert final_result["status"] == "ready"
        assert final_result["data"] is not None
        assert final_result["poll_count"] >= 3
        assert final_result["converged"] is True

    def test_data_quality_improvement_pattern(self):
        """Test data quality improvement pattern using cycles."""
        workflow = Workflow("quality-improve-simple", "Simple Quality Improvement")

        # Single node that handles quality improvement
        workflow.add_node("improver", SimpleDataQualityNode())

        # Create improvement cycle
        workflow.connect(
            "improver",
            "improver",
            mapping={
                "data": "data",
                "target_quality": "target_quality",
                "improvement_rate": "improvement_rate",
            },
            cycle=True,
            max_iterations=10,
            convergence_check="converged == True",
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "improver": {
                    "data": list(range(100)),
                    "target_quality": 0.85,
                    "improvement_rate": 0.15,  # Slower improvement rate
                }
            },
        )

        assert run_id is not None
        final_result = results["improver"]

        # Should reach target quality
        assert final_result["quality_score"] >= 0.85
        assert final_result["converged"] is True
        # Quality history should have multiple entries (one per iteration)
        assert final_result["iteration_count"] > 1

        # Quality should improve over iterations (or at least be maintained)
        history = final_result["quality_history"]
        if len(history) > 1:
            assert history[-1]["quality_score"] >= history[0]["quality_score"]

    def test_batch_processing_with_checkpoints(self):
        """Test batch processing with checkpoint pattern."""
        workflow = Workflow("batch-checkpoint", "Batch Processing with Checkpoints")

        class BatchProcessorNode(CycleAwareNode):
            """Process data in batches with checkpoints."""

            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "total_items": NodeParameter(
                        name="total_items", type=int, required=False, default=1000
                    ),
                    "batch_size": NodeParameter(
                        name="batch_size", type=int, required=False, default=100
                    ),
                    "processed_count": NodeParameter(
                        name="processed_count", type=int, required=False, default=0
                    ),
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                total_items = kwargs.get("total_items", 1000)
                batch_size = kwargs.get("batch_size", 100)

                iteration = self.get_iteration(context)
                prev_state = self.get_previous_state(context)

                # Use passed processed_count from cycle, fallback to state
                if iteration > 0:
                    processed_count = kwargs.get("processed_count", 0)
                else:
                    processed_count = prev_state.get("processed_count", 0)

                # Process next batch
                batch_start = processed_count
                batch_end = min(batch_start + batch_size, total_items)

                # Simulate batch processing
                batch_data = list(range(batch_start, batch_end))
                processed_batch = [x * 2 for x in batch_data]

                new_processed_count = batch_end
                progress = new_processed_count / total_items

                self.set_cycle_state({"processed_count": new_processed_count})

                return {
                    "batch_number": iteration + 1,
                    "processed_batch": processed_batch,
                    "processed_count": new_processed_count,
                    "total_items": total_items,
                    "batch_size": batch_size,
                    "progress": progress,
                    "converged": new_processed_count >= total_items,
                }

        workflow.add_node("processor", BatchProcessorNode())

        # Create processing cycle
        workflow.connect(
            "processor",
            "processor",
            mapping={
                "total_items": "total_items",
                "batch_size": "batch_size",
                "processed_count": "processed_count",
            },
            cycle=True,
            max_iterations=20,
            convergence_check="converged == True",
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow, parameters={"processor": {"total_items": 500, "batch_size": 100}}
        )

        assert run_id is not None
        final_result = results["processor"]

        # Should process all items
        assert final_result["processed_count"] == 500
        assert final_result["progress"] == 1.0
        assert final_result["converged"] is True
        assert final_result["batch_number"] == 5  # 500 items / 100 per batch

    def test_resource_optimization_pattern(self):
        """Test resource optimization pattern using cycles."""
        workflow = Workflow("resource-optimize", "Resource Optimization")

        class ResourceOptimizerNode(CycleAwareNode):
            """Optimize resource allocation iteratively."""

            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "resources": NodeParameter(
                        name="resources", type=dict, required=False, default={}
                    ),
                    "target_efficiency": NodeParameter(
                        name="target_efficiency",
                        type=float,
                        required=False,
                        default=0.9,
                    ),
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                resources = kwargs.get("resources", {"cpu": 100, "memory": 1000})
                target_efficiency = kwargs.get("target_efficiency", 0.9)

                iteration = self.get_iteration(context)
                prev_state = self.get_previous_state(context)

                # Simulate efficiency improvement
                base_efficiency = 0.6
                current_efficiency = min(base_efficiency + (iteration * 0.1), 1.0)

                # Optimize resource allocation
                optimized_resources = {}
                for resource, amount in resources.items():
                    # Reduce allocation as efficiency improves
                    optimized_amount = int(amount * (1.1 - current_efficiency))
                    optimized_resources[resource] = max(
                        optimized_amount, 10
                    )  # Minimum allocation

                optimization_history = prev_state.get("optimization_history", [])
                optimization_history.append(
                    {
                        "iteration": iteration + 1,
                        "efficiency": current_efficiency,
                        "resources": optimized_resources.copy(),
                    }
                )

                self.set_cycle_state({"optimization_history": optimization_history})

                return {
                    "resources": optimized_resources,
                    "efficiency": current_efficiency,
                    "iteration_count": iteration + 1,
                    "target_efficiency": target_efficiency,
                    "optimization_history": optimization_history,
                    "converged": current_efficiency >= target_efficiency,
                }

        workflow.add_node("optimizer", ResourceOptimizerNode())

        # Create optimization cycle
        workflow.connect(
            "optimizer",
            "optimizer",
            mapping={
                "resources": "resources",
                "target_efficiency": "target_efficiency",
            },
            cycle=True,
            max_iterations=10,
            convergence_check="converged == True",
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "optimizer": {
                    "resources": {"cpu": 100, "memory": 1000, "storage": 500},
                    "target_efficiency": 0.85,
                }
            },
        )

        assert run_id is not None
        final_result = results["optimizer"]

        # Should reach target efficiency
        assert final_result["efficiency"] >= 0.85
        assert final_result["converged"] is True

        # Resources should be optimized (reduced)
        initial_resources = {"cpu": 100, "memory": 1000, "storage": 500}
        final_resources = final_result["resources"]
        for resource, initial_amount in initial_resources.items():
            assert final_resources[resource] < initial_amount
