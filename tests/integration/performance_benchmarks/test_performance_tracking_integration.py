"""Integration tests for performance tracking and visualization."""

import time
from typing import Any

import pytest

from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.tracking.manager import TaskManager
from kailash.tracking.models import TaskStatus
from kailash.tracking.storage.filesystem import FileSystemStorage
from kailash.visualization.performance import PerformanceVisualizer
from kailash.workflow.graph import Workflow
from kailash.workflow.visualization import WorkflowVisualizer


@pytest.mark.slow
@pytest.mark.integration
class TestPerformanceTrackingIntegration:
    """Test integration of performance tracking with workflow execution."""

    @pytest.fixture
    def simple_workflow(self):
        """Create a simple test workflow."""
        workflow = Workflow(workflow_id="perf_test", name="Performance Test")

        # Create input data source node
        def data_source() -> dict[str, Any]:
            """Provides initial data for the workflow."""
            return {"result": "test_data"}

        # Create nodes with different performance characteristics
        def fast_node(data: str) -> dict[str, Any]:
            """Fast executing node."""
            time.sleep(0.01)
            return {"result": f"fast_{data}"}

        def slow_node(data: str) -> dict[str, Any]:
            """Slow executing node."""
            time.sleep(0.1)
            return {"result": f"slow_{data}"}

        def cpu_intensive_node(data: str) -> dict[str, Any]:
            """CPU intensive node."""
            # Do some computation
            total = 0
            for i in range(100000):
                total += i
            return {"result": f"cpu_{data}_{total}"}

        # Create schemas
        source_schema = {
            "input": {},  # No inputs required
            "output": {"result": NodeParameter(name="result", type=str, required=True)},
        }

        process_schema = {
            "input": {"data": NodeParameter(name="data", type=str, required=True)},
            "output": {"result": NodeParameter(name="result", type=str, required=True)},
        }

        # Create nodes
        source = PythonCodeNode.from_function(
            data_source,
            name="source",
            input_schema=source_schema["input"],
            output_schema=source_schema["output"],
        )

        fast = PythonCodeNode.from_function(
            fast_node,
            name="fast",
            input_schema=process_schema["input"],
            output_schema=process_schema["output"],
        )

        slow = PythonCodeNode.from_function(
            slow_node,
            name="slow",
            input_schema=process_schema["input"],
            output_schema=process_schema["output"],
        )

        cpu = PythonCodeNode.from_function(
            cpu_intensive_node,
            name="cpu",
            input_schema=process_schema["input"],
            output_schema=process_schema["output"],
        )

        # Add nodes
        workflow.add_node("source_node", source)
        workflow.add_node("fast_node", fast)
        workflow.add_node("slow_node", slow)
        workflow.add_node("cpu_node", cpu)

        # Connect nodes
        workflow.connect("source_node", "fast_node", {"result": "data"})
        workflow.connect("fast_node", "slow_node", {"result": "data"})
        workflow.connect("slow_node", "cpu_node", {"result": "data"})

        return workflow

    def test_metrics_collection_during_execution(self, simple_workflow, tmp_path):
        """Test that metrics are collected during workflow execution."""
        # Setup
        storage = FileSystemStorage(base_path=str(tmp_path))
        task_manager = TaskManager(storage_backend=storage)
        runtime = LocalRuntime()

        # Execute workflow (runtime will create its own run)
        results, run_id = runtime.execute(
            workflow=simple_workflow,
            task_manager=task_manager,
        )

        # Verify execution completed
        assert "source_node" in results
        assert "fast_node" in results
        assert "slow_node" in results
        assert "cpu_node" in results

        # Get tasks and verify metrics
        tasks = task_manager.get_run_tasks(run_id)
        assert len(tasks) == 4

        for task in tasks:
            assert task.status == TaskStatus.COMPLETED
            assert task.metrics is not None
            assert task.metrics.duration > 0

            # Verify metrics based on node characteristics
            if task.node_id == "slow_node":
                assert task.metrics.duration >= 0.1
            elif task.node_id == "fast_node":
                assert task.metrics.duration < 0.1

    def test_performance_visualization_generation(self, simple_workflow, tmp_path):
        """Test generation of performance visualizations."""
        # Setup
        storage = FileSystemStorage(base_path=str(tmp_path))
        task_manager = TaskManager(storage_backend=storage)
        runtime = LocalRuntime()

        # Execute workflow (runtime will create its own run)
        results, run_id = runtime.execute(
            workflow=simple_workflow,
            task_manager=task_manager,
        )

        # Create performance visualizer
        perf_viz = PerformanceVisualizer(task_manager)

        # Generate visualizations
        output_dir = tmp_path / "performance"
        outputs = perf_viz.create_run_performance_summary(run_id, output_dir)

        # Verify outputs
        assert "execution_timeline" in outputs
        assert "resource_usage" in outputs
        assert "performance_comparison" in outputs
        assert "report" in outputs

        # Verify files exist
        for path in outputs.values():
            assert path.exists()

        # Verify report content
        report_path = outputs["report"]
        report_content = report_path.read_text()
        assert f"Run {run_id}" in report_content
        assert "Task Performance Details" in report_content

    def test_integrated_dashboard_creation(self, simple_workflow, tmp_path):
        """Test creation of integrated performance dashboard."""
        # Setup
        storage = FileSystemStorage(base_path=str(tmp_path))
        task_manager = TaskManager(storage_backend=storage)
        runtime = LocalRuntime()

        # Execute workflow (runtime will create its own run)
        results, run_id = runtime.execute(
            workflow=simple_workflow,
            task_manager=task_manager,
        )

        # Create workflow visualizer
        workflow_viz = WorkflowVisualizer(simple_workflow)

        # Generate dashboard
        output_dir = tmp_path / "dashboard"
        outputs = workflow_viz.create_performance_dashboard(
            run_id=run_id, task_manager=task_manager, output_dir=output_dir
        )

        # Verify outputs
        assert "dashboard" in outputs
        assert "workflow_graph" in outputs
        assert "execution_timeline" in outputs

        # Verify dashboard HTML
        dashboard_path = outputs["dashboard"]
        assert dashboard_path.exists()

        dashboard_content = dashboard_path.read_text()
        assert f"Run {run_id}" in dashboard_content
        assert "Performance Metrics" in dashboard_content
        assert "Workflow Execution" in dashboard_content

    def test_run_comparison(self, simple_workflow, tmp_path):
        """Test performance comparison between multiple runs."""
        # Setup
        storage = FileSystemStorage(base_path=str(tmp_path))
        task_manager = TaskManager(storage_backend=storage)
        runtime = LocalRuntime()

        # Execute workflow multiple times
        run_ids = []
        for i in range(3):
            results, run_id = runtime.execute(
                workflow=simple_workflow,
                task_manager=task_manager,
            )
            run_ids.append(run_id)
            time.sleep(0.05)  # Add some variance

        # Create performance visualizer
        perf_viz = PerformanceVisualizer(task_manager)

        # Compare runs
        comparison_path = tmp_path / "comparison.png"
        result_path = perf_viz.compare_runs(run_ids, comparison_path)

        # Verify comparison was created
        assert result_path.exists()

    def test_metrics_with_failed_nodes(self, tmp_path):
        """Test metrics collection when nodes fail."""
        # Create workflow with failing node
        workflow = Workflow(workflow_id="fail_test", name="Fail Test")

        def data_source() -> dict[str, Any]:
            """Provides initial data for the workflow."""
            return {"result": "test_data"}

        def failing_node(data: str) -> dict[str, Any]:
            """Node that fails after some processing."""
            time.sleep(0.05)
            raise RuntimeError("Simulated failure")

        source_schema = {
            "input": {},  # No inputs required
            "output": {"result": NodeParameter(name="result", type=str, required=True)},
        }

        fail_schema = {
            "input": {"data": NodeParameter(name="data", type=str, required=True)},
            "output": {"result": NodeParameter(name="result", type=str, required=True)},
        }

        source_node = PythonCodeNode.from_function(
            data_source,
            name="source",
            input_schema=source_schema["input"],
            output_schema=source_schema["output"],
        )

        fail_node = PythonCodeNode.from_function(
            failing_node,
            name="fail",
            input_schema=fail_schema["input"],
            output_schema=fail_schema["output"],
        )

        workflow.add_node("source_node", source_node)
        workflow.add_node("failing_node", fail_node)
        workflow.connect("source_node", "failing_node", {"result": "data"})

        # Execute with tracking
        storage = FileSystemStorage(base_path=str(tmp_path))
        task_manager = TaskManager(storage_backend=storage)
        runtime = LocalRuntime()

        # Execute workflow - failing node will fail but execution continues since it's a leaf node
        results, run_id = runtime.execute(
            workflow=workflow,
            task_manager=task_manager,
        )

        # Verify the failing node failed
        assert "failing_node" in results
        assert results["failing_node"].get("failed") is True

        # Get task and verify metrics were still collected
        tasks = task_manager.get_run_tasks(run_id)
        assert len(tasks) == 2  # source_node should complete, failing_node should fail

        # Find the failed task
        failed_task = next(task for task in tasks if task.node_id == "failing_node")
        assert failed_task.status == TaskStatus.FAILED
        assert failed_task.error is not None
        assert "Simulated failure" in failed_task.error

        # Verify timing information is available from task timestamps
        assert failed_task.started_at is not None
        assert failed_task.ended_at is not None
        duration = (failed_task.ended_at - failed_task.started_at).total_seconds()
        assert duration >= 0.05  # Should be at least 50ms due to sleep

    def test_custom_metrics_integration(self, tmp_path):
        """Test integration of custom metrics."""
        # Create workflow with custom metrics
        workflow = Workflow(workflow_id="custom_test", name="Custom Test")

        def data_source() -> list:
            """Provides initial data for the workflow."""
            return [10, 20, 60, 70, 80]

        def custom_metrics_node(data: list) -> dict[str, Any]:
            """Node that would report custom metrics."""
            processed = len(data)
            filtered = sum(1 for item in data if item > 50)

            # In real usage, these would be added to the metrics context
            result = {
                "data": [x * 2 for x in data],
                "_metrics": {
                    "records_processed": processed,
                    "records_filtered": filtered,
                    "filter_rate": filtered / processed if processed > 0 else 0,
                },
            }
            return result

        source_schema = {
            "input": {},  # No inputs required
            "output": {
                "result": NodeParameter(name="result", type=list, required=True)
            },
        }

        custom_schema = {
            "input": {"data": NodeParameter(name="data", type=list, required=True)},
            "output": {
                "result": NodeParameter(name="result", type=dict, required=True),
            },
        }

        source_node = PythonCodeNode.from_function(
            data_source,
            name="source",
            input_schema=source_schema["input"],
            output_schema=source_schema["output"],
        )

        custom_node = PythonCodeNode.from_function(
            custom_metrics_node,
            name="custom",
            input_schema=custom_schema["input"],
            output_schema=custom_schema["output"],
        )

        workflow.add_node("source_node", source_node)
        workflow.add_node("custom_node", custom_node)
        workflow.connect("source_node", "custom_node", {"result": "data"})

        # Execute
        storage = FileSystemStorage(base_path=str(tmp_path))
        task_manager = TaskManager(storage_backend=storage)
        runtime = LocalRuntime()

        results, run_id = runtime.execute(
            workflow=workflow,
            task_manager=task_manager,
        )

        # Verify custom metrics in results - now wrapped under "result"
        assert "result" in results["custom_node"]
        result_data = results["custom_node"]["result"]
        assert "_metrics" in result_data
        metrics = result_data["_metrics"]
        assert metrics["records_processed"] == 5
        assert metrics["records_filtered"] == 3
        assert metrics["filter_rate"] == 0.6

    def test_performance_tracking_with_parallel_execution(self, tmp_path):
        """Test performance tracking with parallel node execution."""
        # Create workflow with parallel branches
        workflow = Workflow(workflow_id="parallel_test", name="Parallel Test")

        def data_source() -> dict[str, Any]:
            """Provides initial data for the workflow."""
            return {"result": "test_data"}

        def process_branch(data: str, branch_id: int) -> dict[str, Any]:
            """Process data in a branch."""
            time.sleep(0.05 * branch_id)  # Different delays
            return {"result": f"{data}_branch_{branch_id}"}

        source_schema = {
            "input": {},  # No inputs required
            "output": {"result": NodeParameter(name="result", type=str, required=True)},
        }

        branch_schema = {
            "input": {"data": NodeParameter(name="data", type=str, required=True)},
            "output": {"result": NodeParameter(name="result", type=str, required=True)},
        }

        # Create source node
        source_node = PythonCodeNode.from_function(
            data_source,
            name="source",
            input_schema=source_schema["input"],
            output_schema=source_schema["output"],
        )
        workflow.add_node("source_node", source_node)

        # Create parallel branches - need to define separate functions to avoid closure issues
        def create_branch_function(branch_id):
            def branch_func(data):
                return process_branch(data, branch_id)

            return branch_func

        for i in range(3):
            branch_func = create_branch_function(i)
            node = PythonCodeNode.from_function(
                branch_func,
                name=f"branch_{i}",
                input_schema=branch_schema["input"],
                output_schema=branch_schema["output"],
            )
            workflow.add_node(f"branch_{i}", node)
            workflow.connect("source_node", f"branch_{i}", {"result": "data"})

        # Execute (nodes run in sequence in LocalRuntime, but metrics are collected)
        storage = FileSystemStorage(base_path=str(tmp_path))
        task_manager = TaskManager(storage_backend=storage)
        runtime = LocalRuntime()

        results, run_id = runtime.execute(
            workflow=workflow,
            task_manager=task_manager,
        )

        # Verify all branches have metrics
        tasks = task_manager.get_run_tasks(run_id)
        assert len(tasks) == 4  # source + 3 branches

        # Get only the branch tasks for timing verification
        branch_tasks = [task for task in tasks if task.node_id.startswith("branch_")]
        assert len(branch_tasks) == 3

        for i, task in enumerate(sorted(branch_tasks, key=lambda t: t.node_id)):
            assert task.metrics is not None
            # Verify relative durations
            if i > 0:
                assert task.metrics.duration >= 0.05 * i
