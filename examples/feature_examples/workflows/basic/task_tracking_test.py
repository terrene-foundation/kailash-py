#!/usr/bin/env python3
"""
Task Tracking Example

This example demonstrates the task tracking capabilities of Kailash SDK.
"""

import random
import sys
import time
from pathlib import Path
from typing import Any

from examples.utils.paths import get_data_dir, get_output_dir

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.data.writers import CSVWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.tracking.manager import TaskManager
from kailash.tracking.models import RunSummary, TaskRun, TaskStatus, TaskSummary
from kailash.tracking.storage.filesystem import FileSystemStorage
from kailash.workflow.graph import Workflow


def demonstrate_basic_task_tracking():
    """Basic task tracking example."""

    print("\n=== Basic Task Tracking ===")

    # Create task manager
    task_manager = TaskManager()

    # Create a simple workflow
    workflow = Workflow(
        workflow_id="simple_data_processing", name="simple_data_processing"
    )

    # Create nodes
    reader = CSVReaderNode(
        name="read_data", file_path=str(get_data_dir() / "input.csv")
    )

    def transform_data(data: list) -> dict[str, Any]:
        """Simple data transformation."""
        transformed = []
        for record in data:
            new_record = record.copy()
            new_record["processed"] = True
            transformed.append(new_record)
        return {"result": transformed}

    transformer = PythonCodeNode.from_function(transform_data, name="transform_data")

    writer = CSVWriterNode(
        name="write_results", file_path=str(get_output_dir() / "output.csv")
    )

    # Add nodes to workflow
    workflow.add_node(
        node_id="reader",
        node_or_type=reader,
        config={"file_path": str(get_data_dir() / "input.csv")},
    )
    workflow.add_node(node_id="transformer", node_or_type=transformer)
    workflow.add_node(
        node_id="writer",
        node_or_type=writer,
        config={"file_path": str(get_output_dir() / "output.csv")},
    )

    # Connect nodes
    workflow.connect("reader", "transformer", {"data": "data"})
    workflow.connect("transformer", "writer", {"result": "data"})

    # Create sample data
    get_data_dir().mkdir(exist_ok=True)
    with open(str(get_data_dir() / "input.csv", "w")) as f:
        f.write("id,name,value\n")
        f.write("1,Item A,100\n")
        f.write("2,Item B,200\n")
        f.write("3,Item C,300\n")

    # Create a run for this workflow
    run_id = task_manager.create_run(
        workflow_name=workflow.name,
        metadata={
            "description": "Basic data processing example",
            "requested_by": "user@example.com",
        },
    )

    print(f"Created run: {run_id}")

    # Create tasks for each node
    reader_task = TaskRun(run_id=run_id, node_id="reader", node_type="CSVReaderNode")
    task_manager.save_task(reader_task)

    transformer_task = TaskRun(
        run_id=run_id, node_id="transformer", node_type="PythonCodeNode"
    )
    task_manager.save_task(transformer_task)

    writer_task = TaskRun(run_id=run_id, node_id="writer", node_type="CSVWriterNode")
    task_manager.save_task(writer_task)

    # Execute workflow with task tracking
    runner = LocalRuntime(debug=True)

    try:
        # Update run status
        task_manager.update_run_status(run_id, "running")

        # Simulate task execution with progress
        all_tasks = [reader_task, transformer_task, writer_task]

        for i, task in enumerate(all_tasks):
            # Update task status
            task.update_status(TaskStatus.RUNNING)
            task_manager.save_task(task)
            print(f"Executing task: {task.node_id}")

            # Simulate some work
            time.sleep(0.5)

            # Update task as completed
            task.update_status(
                TaskStatus.COMPLETED, result={"records_processed": (i + 1) * 10}
            )
            task_manager.save_task(task)
            print(f"Completed task: {task.node_id}")

        # Actually run the workflow
        results, execution_run_id = runner.execute(workflow)

        # Update run status
        task_manager.update_run_status(run_id, "completed")
        print("Workflow run completed successfully!")

    except Exception as e:
        # Handle errors
        task_manager.update_run_status(run_id, "failed", error=str(e))
        print(f"Workflow run failed: {e}")

    # Retrieve run details
    run = task_manager.get_run(run_id)
    summary = RunSummary.from_workflow_run(run, all_tasks)

    print("\nRun Summary:")
    print(f"  Run ID: {summary.run_id}")
    print(f"  Status: {summary.status}")
    print(
        f"  Duration: {summary.duration:.2f}s"
        if summary.duration
        else "  Duration: N/A"
    )
    print(f"  Tasks: {summary.task_count}")
    print(f"  Completed: {summary.completed_tasks}")
    print(f"  Failed: {summary.failed_tasks}")


def demonstrate_task_progress_tracking():
    """Demonstrate tracking task progress during execution."""

    print("\n=== Task Progress Tracking ===")

    task_manager = TaskManager()

    # Create a workflow with a long-running task
    workflow = Workflow(
        workflow_id="long_running_workflow", name="long_running_workflow"
    )

    def long_process(data: list) -> dict[str, Any]:
        """Simulate a long-running process."""
        results = []
        total = len(data)

        # This would normally be part of the node's execution
        for i, record in enumerate(data):
            # Simulate processing
            time.sleep(0.1)
            results.append({"id": record.get("id", i), "processed": True})

            # In actual implementation, this would be yielded or callback
            progress = (i + 1) / total * 100
            print(f"  Processing: {progress:.1f}%")

        return {"result": results}

    processor = PythonCodeNode.from_function(long_process, name="long_processor")

    # Create reader
    reader = CSVReaderNode(
        name="data_reader", file_path=str(get_data_dir() / "large_input.csv")
    )

    # Add nodes
    workflow.add_node(
        node_id="reader",
        node_or_type=reader,
        config={"file_path": str(get_data_dir() / "large_input.csv")},
    )
    workflow.add_node(node_id="processor", node_or_type=processor)

    # Connect nodes
    workflow.connect("reader", "processor", {"data": "data"})

    # Create sample data
    with open(str(get_data_dir() / "large_input.csv", "w")) as f:
        f.write("id,value\n")
        for i in range(10):
            f.write(f"{i},{i * 100}\n")

    # Create run
    run_id = task_manager.create_run(workflow_name=workflow.name)

    # Create task
    process_task = TaskRun(
        run_id=run_id, node_id="processor", node_type="PythonCodeNode"
    )
    task_manager.save_task(process_task)

    # Execute with progress tracking
    runner = LocalRuntime(debug=True)

    print("Starting long-running task...")
    process_task.update_status(TaskStatus.RUNNING)
    task_manager.save_task(process_task)

    try:
        results, _ = runner.execute(workflow)

        process_task.update_status(TaskStatus.COMPLETED, result={"success": True})
        task_manager.save_task(process_task)

        print("Task completed successfully!")

    except Exception as e:
        process_task.update_status(TaskStatus.FAILED, error=str(e))
        task_manager.save_task(process_task)
        print(f"Task failed: {e}")


def demonstrate_task_error_handling():
    """Demonstrate task error handling and recovery."""

    print("\n=== Task Error Handling ===")

    task_manager = TaskManager()

    # Create a workflow that might fail
    workflow = Workflow(workflow_id="unreliable_workflow", name="unreliable_workflow")

    def unreliable_process(data: list, failure_rate: float = 0.5) -> dict[str, Any]:
        """Process that randomly fails."""
        if random.random() < failure_rate:
            raise Exception("Random failure occurred")

        return {"data": [{"id": i, "processed": True} for i in range(len(data))]}

    processor = PythonCodeNode.from_function(
        unreliable_process, name="unreliable_processor"
    )

    # Add node
    workflow.add_node(
        node_id="processor", node_or_type=processor, config={"failure_rate": 0.5}
    )

    # Create run
    run_id = task_manager.create_run(workflow_name=workflow.name)

    # Simulate multiple attempts
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        # Create task for this attempt
        task = TaskRun(
            run_id=run_id,
            node_id="processor",
            node_type="PythonCodeNode",
            metadata={"attempt": attempt},
        )
        task_manager.save_task(task)

        print(f"\nAttempt {attempt}/{max_attempts}")

        # Update task status
        task.update_status(TaskStatus.RUNNING)
        task_manager.save_task(task)

        try:
            # Try to execute
            result = processor.run(data=[1, 2, 3])

            # Success
            task.update_status(TaskStatus.COMPLETED, result=result)
            task_manager.save_task(task)

            print("Task completed successfully!")
            break

        except Exception as e:
            # Failed
            task.update_status(TaskStatus.FAILED, error=str(e))
            task_manager.save_task(task)

            print(f"Attempt {attempt} failed: {e}")

            if attempt < max_attempts:
                print("Retrying...")
                time.sleep(1)  # Wait before retry
            else:
                print("All attempts failed!")
                task_manager.update_run_status(
                    run_id, "failed", error="Max attempts exceeded"
                )


def demonstrate_task_filtering_and_querying():
    """Demonstrate querying and filtering tasks."""

    print("\n=== Task Filtering and Querying ===")

    task_manager = TaskManager()

    # Create multiple runs and tasks
    workflows = ["data_pipeline", "ml_training", "report_generation"]
    statuses = [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.RUNNING]

    created_tasks = []

    for workflow_name in workflows:
        run_id = task_manager.create_run(workflow_name=workflow_name)

        # Create tasks for this run
        for i in range(3):
            task = TaskRun(
                run_id=run_id,
                node_id=f"node_{i}",
                node_type="DemoNode",
                status=random.choice(statuses),
            )
            task_manager.save_task(task)
            created_tasks.append(task)

    # Query tasks by status
    print("\nQuerying tasks by status:")
    for status in statuses:
        # Get tasks from storage
        tasks = task_manager.storage.get_tasks_by_run(created_tasks[0].run_id)
        filtered_tasks = [t for t in tasks if t.status == status]
        print(f"  {status}: {len(filtered_tasks)} tasks")

    # Get all runs
    print("\nAll workflow runs:")
    # Since we don't have a get_all_runs method, we'll just show what we created
    for workflow_name in workflows:
        print(f"  - {workflow_name}")

    # Show task details for one run
    print("\nTask details for first run:")
    run_id = created_tasks[0].run_id
    tasks = task_manager.storage.get_tasks_by_run(run_id)

    for task in tasks[:3]:  # Show first 3 tasks
        summary = TaskSummary.from_task_run(task)
        print(f"  Task {summary.task_id[:8]}: {summary.node_id} - {summary.status}")


def demonstrate_task_persistence():
    """Demonstrate task persistence across sessions."""

    print("\n=== Task Persistence ===")

    # Create task manager with filesystem storage
    storage_path = get_data_dir() / "task_storage"
    storage_path.mkdir(parents=True, exist_ok=True)

    task_manager = TaskManager(
        storage_backend=FileSystemStorage(base_path=str(storage_path))
    )

    # Create a run and task
    run_id = task_manager.create_run(
        workflow_name="persistent_workflow", metadata={"session": "first"}
    )

    task = TaskRun(
        run_id=run_id,
        node_id="persistent_node",
        node_type="DemoNode",
        metadata={"important_data": "This should persist"},
    )
    task_manager.save_task(task)

    print(f"Saved task: {task.task_id[:8]}")
    print(f"Metadata: {task.metadata}")

    # Simulate loading in a new session
    new_task_manager = TaskManager(
        storage_backend=FileSystemStorage(base_path=str(storage_path))
    )

    # Load the task
    loaded_task = new_task_manager.storage.get_task(task.task_id)

    if loaded_task:
        print(f"\nLoaded task: {loaded_task.task_id[:8]}")
        print(f"Metadata: {loaded_task.metadata}")
        print("Task successfully persisted and loaded!")
    else:
        print("Failed to load task")


def main():
    """Main entry point for task tracking examples."""

    print("=== Kailash Task Tracking Examples ===\n")

    # Create necessary directories
    get_data_dir() / "task_storage".mkdir(parents=True, exist_ok=True)

    examples = [
        ("Basic Task Tracking", demonstrate_basic_task_tracking),
        ("Task Progress Tracking", demonstrate_task_progress_tracking),
        ("Task Error Handling", demonstrate_task_error_handling),
        ("Task Filtering and Querying", demonstrate_task_filtering_and_querying),
        ("Task Persistence", demonstrate_task_persistence),
    ]

    for name, example_func in examples:
        print(f"\n{'='*50}")
        print(f"Running: {name}")
        print("=" * 50)

        try:
            example_func()
        except Exception as e:
            print(f"Example failed: {e}")
            import traceback

            traceback.print_exc()

    print("\n=== All examples completed ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
