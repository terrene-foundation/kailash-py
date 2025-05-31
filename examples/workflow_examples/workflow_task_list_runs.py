#!/usr/bin/env python3
"""
Task Manager List Runs Example

This example demonstrates how to list and query workflow runs using TaskManager.list_runs()
and shows best practices for handling run metadata and filtering.
"""

import sys
import time
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.tracking.manager import TaskManager
from kailash.workflow.graph import Workflow


def create_sample_workflow(workflow_id: str, description: str) -> Workflow:
    """Create a simple workflow for demonstration."""
    workflow = Workflow(workflow_id=workflow_id, name=workflow_id)
    workflow.description = description

    # Simple data generator node
    def generate_data() -> Dict[str, Any]:
        """Generate sample data."""
        return {"data": [{"id": i, "value": i * 10} for i in range(5)]}

    # Simple data processing node
    def process_data(data: list) -> Dict[str, Any]:
        """Process data with some delay."""
        time.sleep(0.1)  # Simulate processing
        return {
            "result": [
                {"id": item["id"], "processed": True, "value": item["value"] * 2}
                for item in data
            ]
        }

    generator = PythonCodeNode.from_function(generate_data, name="generator")
    processor = PythonCodeNode.from_function(process_data, name="processor")

    workflow.add_node("generate", generator)
    workflow.add_node("process", processor)
    workflow.connect("generate", "process", {"data": "data"})

    return workflow


def demonstrate_basic_list_runs():
    """Basic example of listing runs."""
    print("\n=== Basic List Runs Example ===")

    # Create task manager
    task_manager = TaskManager()
    runtime = LocalRuntime()

    # Create and run multiple workflows
    workflows = [
        ("data_pipeline", "Daily data processing pipeline"),
        ("ml_training", "Machine learning model training"),
        ("report_gen", "Report generation workflow"),
    ]

    print("\n1. Creating and running workflows...")
    run_ids = []

    for workflow_id, description in workflows:
        workflow = create_sample_workflow(workflow_id, description)

        # Execute with task manager to get proper run_id
        results, run_id = runtime.execute(workflow, task_manager=task_manager)

        if run_id:
            run_ids.append(run_id)
            print(f"   ✓ {workflow_id}: run_id={run_id[:8]}...")
        else:
            print(f"   ✗ {workflow_id}: No run_id generated")

    # Wait a bit to ensure all runs are saved
    time.sleep(0.5)

    print("\n2. Listing all runs...")
    try:
        all_runs = task_manager.list_runs()
        print(f"   Found {len(all_runs)} total runs")

        for run in all_runs[:5]:  # Show first 5
            print(f"   - {run.workflow_name}: {run.status} (started: {run.started_at})")
    except Exception as e:
        print(f"   Error listing runs: {e}")
        print("   Note: This may be due to timezone inconsistencies in stored runs")


def demonstrate_filtered_list_runs():
    """Demonstrate filtering runs by status and workflow name."""
    print("\n=== Filtered List Runs Example ===")

    task_manager = TaskManager()
    runtime = LocalRuntime()

    # Create workflows with different outcomes
    print("\n1. Creating workflows with different statuses...")

    # Successful workflow
    success_workflow = create_sample_workflow("success_workflow", "Always succeeds")
    results, success_run_id = runtime.execute(
        success_workflow, task_manager=task_manager
    )
    if success_run_id:
        task_manager.update_run_status(success_run_id, "completed")
    print("   ✓ Created successful workflow run")

    # Failed workflow
    def failing_process(data: list) -> Dict[str, Any]:
        raise Exception("Intentional failure for demonstration")

    fail_workflow = Workflow("fail_workflow", name="fail_workflow")
    fail_node = PythonCodeNode.from_function(failing_process, name="fail_node")
    fail_workflow.add_node("fail", fail_node)

    fail_run_id = None
    try:
        results, fail_run_id = runtime.execute(
            fail_workflow,
            task_manager=task_manager,
            parameters={"fail": {"data": [1, 2, 3]}},
        )
    except Exception:
        if fail_run_id:
            task_manager.update_run_status(
                fail_run_id, "failed", error="Intentional failure"
            )
    print("   ✓ Created failed workflow run")

    # Running workflow (simulated)
    running_workflow = create_sample_workflow("running_workflow", "Long running")
    run_id = task_manager.create_run(workflow_name="running_workflow")
    task_manager.update_run_status(run_id, "running")
    print("   ✓ Created running workflow run")

    time.sleep(0.5)

    # Filter by status
    print("\n2. Filtering runs by status...")
    statuses = ["completed", "failed", "running"]

    for status in statuses:
        try:
            runs = task_manager.list_runs(status=status)
            print(f"   {status.upper()}: {len(runs)} runs")
            for run in runs[:2]:  # Show first 2
                print(f"      - {run.workflow_name} ({run.run_id[:8]}...)")
        except Exception as e:
            print(f"   Error listing {status} runs: {e}")

    # Filter by workflow name
    print("\n3. Filtering runs by workflow name...")
    try:
        success_runs = task_manager.list_runs(workflow_name="success_workflow")
        print(f"   success_workflow: {len(success_runs)} runs")

        fail_runs = task_manager.list_runs(workflow_name="fail_workflow")
        print(f"   fail_workflow: {len(fail_runs)} runs")
    except Exception as e:
        print(f"   Error filtering by workflow name: {e}")


def demonstrate_run_history_analysis():
    """Demonstrate analyzing run history and patterns."""
    print("\n=== Run History Analysis Example ===")

    task_manager = TaskManager()
    runtime = LocalRuntime()

    # Create multiple runs over time
    print("\n1. Creating run history...")
    workflow = create_sample_workflow("analytics_pipeline", "Analytics processing")

    run_stats = {
        "completed": 0,
        "failed": 0,
        "total_duration": 0.0,
    }

    for i in range(5):
        print(f"   Run {i+1}/5...", end="", flush=True)

        start_time = time.time()
        try:
            results, run_id = runtime.execute(workflow, task_manager=task_manager)
            duration = time.time() - start_time

            if run_id:
                # Simulate random failures
                if i % 3 == 0 and i > 0:  # Fail every 3rd run after first
                    task_manager.update_run_status(
                        run_id, "failed", error="Random failure"
                    )
                    run_stats["failed"] += 1
                    print(" FAILED")
                else:
                    task_manager.update_run_status(run_id, "completed")
                    run_stats["completed"] += 1
                    run_stats["total_duration"] += duration
                    print(" SUCCESS")
        except Exception as e:
            print(f" ERROR: {e}")

        time.sleep(0.2)  # Space out runs

    # Analyze run history
    print("\n2. Analyzing run history...")
    try:
        all_runs = task_manager.list_runs(workflow_name="analytics_pipeline")

        if all_runs:
            print(f"   Total runs: {len(all_runs)}")
            print(f"   Successful: {run_stats['completed']}")
            print(f"   Failed: {run_stats['failed']}")
            print(
                f"   Success rate: {run_stats['completed'] / len(all_runs) * 100:.1f}%"
            )

            if run_stats["completed"] > 0:
                avg_duration = run_stats["total_duration"] / run_stats["completed"]
                print(f"   Avg duration: {avg_duration:.2f}s")

            # Show recent runs
            print("\n   Recent runs:")
            for run in all_runs[:3]:
                status_icon = "✓" if run.status == "completed" else "✗"
                print(f"   {status_icon} {run.run_id[:8]}... - {run.status}")

    except Exception as e:
        print(f"   Error analyzing history: {e}")


def demonstrate_timezone_safe_list_runs():
    """Demonstrate a workaround for timezone issues in list_runs."""
    print("\n=== Timezone-Safe List Runs Example ===")

    task_manager = TaskManager()

    print("\n1. Direct list_runs may fail with timezone issues...")
    try:
        runs = task_manager.list_runs()
        print(f"   Success: Found {len(runs)} runs")
    except Exception as e:
        print(f"   Failed as expected: {e}")

    print("\n2. Workaround: Access runs directly from storage...")

    # Access storage directly (workaround for timezone issue)
    try:
        # Get all run files from storage
        if hasattr(task_manager.storage, "runs_dir"):
            runs_dir = Path(task_manager.storage.runs_dir)
            if runs_dir.exists():
                run_files = list(runs_dir.glob("*.json"))
                print(f"   Found {len(run_files)} run files in storage")

                # Load and display recent runs
                runs = []
                for run_file in run_files[:5]:  # First 5 runs
                    try:
                        import json

                        with open(run_file, "r") as f:
                            run_data = json.load(f)
                            print(
                                f"   - Run {run_data.get('run_id', 'unknown')[:8]}... "
                                f"({run_data.get('workflow_name', 'unknown')}): "
                                f"{run_data.get('status', 'unknown')}"
                            )
                    except Exception as e:
                        print(f"   - Error reading {run_file.name}: {e}")
        else:
            print("   Storage backend doesn't expose runs directory")

    except Exception as e:
        print(f"   Workaround also failed: {e}")

    print("\n3. Best practice: Handle timezone consistently...")
    print("   - Always use timezone-aware datetime objects")
    print("   - Use UTC for storage and convert for display")
    print("   - Consider upgrading SDK to fix timezone handling")


def demonstrate_run_cleanup():
    """Demonstrate cleaning up old runs."""
    print("\n=== Run Cleanup Example ===")

    task_manager = TaskManager()
    runtime = LocalRuntime()

    # Create some test runs
    print("\n1. Creating test runs...")
    workflow = create_sample_workflow("cleanup_test", "Test for cleanup")

    for i in range(3):
        results, run_id = runtime.execute(workflow, task_manager=task_manager)
        print(f"   Created run {i+1}: {run_id[:8] if run_id else 'No ID'}...")

    print("\n2. Listing runs before cleanup...")
    try:
        runs = task_manager.list_runs(workflow_name="cleanup_test")
        print(f"   Found {len(runs)} runs")
    except Exception as e:
        print(f"   Error listing runs: {e}")

    print("\n3. Cleanup old runs (demonstration only)...")
    print("   Note: TaskManager doesn't have built-in cleanup methods")
    print("   You would need to:")
    print("   - Implement a cleanup method in your storage backend")
    print("   - Or manually delete old run files from storage")
    print("   - Consider implementing retention policies")

    # Show how to access storage for manual cleanup
    if hasattr(task_manager.storage, "delete_run"):
        print("\n   Example cleanup code:")
        print("   ```python")
        print("   cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)")
        print("   for run in old_runs:")
        print("       if run.started_at < cutoff_date:")
        print("           task_manager.storage.delete_run(run.run_id)")
        print("   ```")


def main():
    """Main entry point for list_runs examples."""
    print("=== Kailash Task Manager List Runs Examples ===")
    print("\nNOTE: The list_runs() method may fail with timezone comparison errors.")
    print("This is a known issue in the current SDK version.")
    print("These examples demonstrate both the issue and potential workarounds.\n")

    # Create necessary directories
    Path("../data").mkdir(parents=True, exist_ok=True)

    examples = [
        ("Basic List Runs", demonstrate_basic_list_runs),
        ("Filtered List Runs", demonstrate_filtered_list_runs),
        ("Run History Analysis", demonstrate_run_history_analysis),
        ("Timezone-Safe List Runs", demonstrate_timezone_safe_list_runs),
        ("Run Cleanup", demonstrate_run_cleanup),
    ]

    for name, example_func in examples:
        print(f"\n{'='*60}")
        print(f"Running: {name}")
        print("=" * 60)

        try:
            example_func()
        except Exception as e:
            print(f"\nExample failed with error: {e}")
            import traceback

            traceback.print_exc()

    print("\n=== All examples completed ===")
    print("\nKey takeaways:")
    print("1. Always pass task_manager to runtime.execute() to get run_id")
    print("2. list_runs() may fail due to timezone issues in the SDK")
    print("3. Filter runs by status or workflow_name for better performance")
    print("4. Consider implementing cleanup strategies for old runs")
    print("5. Handle exceptions when using list_runs() until timezone issue is fixed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
