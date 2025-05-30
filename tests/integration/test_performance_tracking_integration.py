"""Integration tests for performance tracking and visualization."""

import time
from pathlib import Path
from typing import Any, Dict

import pytest

from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.tracking.manager import TaskManager
from kailash.tracking.models import TaskStatus
from kailash.visualization.performance import PerformanceVisualizer
from kailash.workflow.graph import Workflow
from kailash.workflow.visualization import WorkflowVisualizer


class TestPerformanceTrackingIntegration:
    """Test integration of performance tracking with workflow execution."""

    @pytest.fixture
    def simple_workflow(self):
        """Create a simple test workflow."""
        workflow = Workflow(workflow_id="perf_test", name="Performance Test")

        # Create nodes with different performance characteristics
        def fast_node(data: str) -> Dict[str, Any]:
            """Fast executing node."""
            time.sleep(0.01)
            return {"result": f"fast_{data}"}

        def slow_node(data: str) -> Dict[str, Any]:
            """Slow executing node."""
            time.sleep(0.1)
            return {"result": f"slow_{data}"}

        def cpu_intensive_node(data: str) -> Dict[str, Any]:
            """CPU intensive node."""
            # Do some computation
            total = 0
            for i in range(100000):
                total += i
            return {"result": f"cpu_{data}_{total}"}

        # Create schemas
        schema = {
            "input": {"data": NodeParameter(name="data", type=str, required=True)},
            "output": {"result": NodeParameter(name="result", type=str, required=True)},
        }

        # Create nodes
        fast = PythonCodeNode.from_function(
            fast_node,
            name="fast",
            input_schema=schema["input"],
            output_schema=schema["output"],
        )

        slow = PythonCodeNode.from_function(
            slow_node,
            name="slow",
            input_schema=schema["input"],
            output_schema=schema["output"],
        )

        cpu = PythonCodeNode.from_function(
            cpu_intensive_node,
            name="cpu",
            input_schema=schema["input"],
            output_schema=schema["output"],
        )

        # Add nodes
        workflow.add_node("fast_node", fast)
        workflow.add_node("slow_node", slow)
        workflow.add_node("cpu_node", cpu)

        # Connect nodes
        workflow.connect("fast_node", "slow_node", {"result": "data"})
        workflow.connect("slow_node", "cpu_node", {"result": "data"})

        return workflow

    def test_metrics_collection_during_execution(self, simple_workflow, tmp_path):
        """Test that metrics are collected during workflow execution."""
        # Setup
        task_manager = TaskManager(
            storage_backend="filesystem", storage_path=str(tmp_path)
        )
        runtime = LocalRuntime()

        # Create run
        run_id = task_manager.create_run(workflow_name=simple_workflow.name)

        # Execute workflow
        results, _ = runtime.execute(
            workflow=simple_workflow,
            task_manager=task_manager,
            parameters={"fast_node": {"data": "test"}},
        )

        # Verify execution completed
        assert "fast_node" in results
        assert "slow_node" in results
        assert "cpu_node" in results

        # Get tasks and verify metrics
        tasks = task_manager.get_run_tasks(run_id)
        assert len(tasks) == 3

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
        task_manager = TaskManager(
            storage_backend="filesystem", storage_path=str(tmp_path)
        )
        runtime = LocalRuntime()

        # Execute workflow
        run_id = task_manager.create_run(workflow_name=simple_workflow.name)
        runtime.execute(
            workflow=simple_workflow,
            task_manager=task_manager,
            parameters={"fast_node": {"data": "test"}},
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
        task_manager = TaskManager(
            storage_backend="filesystem", storage_path=str(tmp_path)
        )
        runtime = LocalRuntime()

        # Execute workflow
        run_id = task_manager.create_run(workflow_name=simple_workflow.name)
        runtime.execute(
            workflow=simple_workflow,
            task_manager=task_manager,
            parameters={"fast_node": {"data": "test"}},
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
        task_manager = TaskManager(
            storage_backend="filesystem", storage_path=str(tmp_path)
        )
        runtime = LocalRuntime()

        # Execute workflow multiple times
        run_ids = []
        for i in range(3):
            run_id = task_manager.create_run(workflow_name=simple_workflow.name)
            runtime.execute(
                workflow=simple_workflow,
                task_manager=task_manager,
                parameters={"fast_node": {"data": f"test_{i}"}},
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

        def failing_node(data: str) -> Dict[str, Any]:
            """Node that fails after some processing."""
            time.sleep(0.05)
            raise RuntimeError("Simulated failure")

        schema = {
            "input": {"data": NodeParameter(name="data", type=str, required=True)},
            "output": {"result": NodeParameter(name="result", type=str, required=True)},
        }

        fail_node = PythonCodeNode.from_function(
            failing_node,
            name="fail",
            input_schema=schema["input"],
            output_schema=schema["output"],
        )

        workflow.add_node("failing_node", fail_node)

        # Execute with tracking
        task_manager = TaskManager(
            storage_backend="filesystem", storage_path=str(tmp_path)
        )
        runtime = LocalRuntime()

        run_id = task_manager.create_run(workflow_name=workflow.name)

        with pytest.raises(Exception):
            runtime.execute(
                workflow=workflow,
                task_manager=task_manager,
                parameters={"failing_node": {"data": "test"}},
            )

        # Get task and verify metrics were still collected
        tasks = task_manager.get_run_tasks(run_id)
        assert len(tasks) == 1

        failed_task = tasks[0]
        assert failed_task.status == TaskStatus.FAILED
        assert failed_task.metrics is not None
        assert failed_task.metrics.duration >= 0.05

    def test_custom_metrics_integration(self, tmp_path):
        """Test integration of custom metrics."""
        # Create workflow with custom metrics
        workflow = Workflow(workflow_id="custom_test", name="Custom Test")

        def custom_metrics_node(data: list) -> Dict[str, Any]:
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

        schema = {
            "input": {"data": NodeParameter(name="data", type=list, required=True)},
            "output": {
                "data": NodeParameter(name="data", type=list, required=True),
                "_metrics": NodeParameter(name="_metrics", type=dict, required=False),
            },
        }

        custom_node = PythonCodeNode.from_function(
            custom_metrics_node,
            name="custom",
            input_schema=schema["input"],
            output_schema=schema["output"],
        )

        workflow.add_node("custom_node", custom_node)

        # Execute
        task_manager = TaskManager(
            storage_backend="filesystem", storage_path=str(tmp_path)
        )
        runtime = LocalRuntime()

        run_id = task_manager.create_run(workflow_name=workflow.name)
        results, _ = runtime.execute(
            workflow=workflow,
            task_manager=task_manager,
            parameters={"custom_node": {"data": [10, 20, 60, 70, 80]}},
        )

        # Verify custom metrics in results
        assert "_metrics" in results["custom_node"]
        metrics = results["custom_node"]["_metrics"]
        assert metrics["records_processed"] == 5
        assert metrics["records_filtered"] == 3
        assert metrics["filter_rate"] == 0.6

    def test_performance_tracking_with_parallel_execution(self, tmp_path):
        """Test performance tracking with parallel node execution."""
        # Create workflow with parallel branches
        workflow = Workflow(workflow_id="parallel_test", name="Parallel Test")

        def process_branch(data: str, branch_id: int) -> Dict[str, Any]:
            """Process data in a branch."""
            time.sleep(0.05 * branch_id)  # Different delays
            return {"result": f"{data}_branch_{branch_id}"}

        schema = {
            "input": {"data": NodeParameter(name="data", type=str, required=True)},
            "output": {"result": NodeParameter(name="result", type=str, required=True)},
        }

        # Create parallel branches
        for i in range(3):
            node = PythonCodeNode.from_function(
                lambda d, bid=i: process_branch(d, bid),
                name=f"branch_{i}",
                input_schema=schema["input"],
                output_schema=schema["output"],
            )
            workflow.add_node(f"branch_{i}", node)

        # Execute (nodes run in sequence in LocalRuntime, but metrics are collected)
        task_manager = TaskManager(
            storage_backend="filesystem", storage_path=str(tmp_path)
        )
        runtime = LocalRuntime()

        run_id = task_manager.create_run(workflow_name=workflow.name)
        runtime.execute(
            workflow=workflow,
            task_manager=task_manager,
            parameters={f"branch_{i}": {"data": "test"} for i in range(3)},
        )

        # Verify all branches have metrics
        tasks = task_manager.get_run_tasks(run_id)
        assert len(tasks) == 3

        for i, task in enumerate(sorted(tasks, key=lambda t: t.node_id)):
            assert task.metrics is not None
            # Verify relative durations
            if i > 0:
                assert task.metrics.duration >= 0.05 * i
