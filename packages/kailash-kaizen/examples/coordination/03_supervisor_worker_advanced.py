"""
Example 3: Supervisor-Worker Pattern - Advanced Usage

This example demonstrates advanced features of the SupervisorWorkerPattern,
including error handling, failure recovery, and task reassignment.

Learning Objectives:
- Error handling in distributed execution
- Task failure detection
- Task reassignment strategies
- Worker failure recovery
- Progress monitoring and intervention

Estimated time: 10 minutes
"""

from kaizen.agents.coordination import create_supervisor_worker_pattern
from kaizen.memory import SharedMemoryPool


def simulate_worker_failure(worker, task):
    """Simulate a worker failing to complete a task."""
    # In real scenarios, this could be:
    # - Network timeout
    # - LLM error
    # - Invalid response
    # - Resource exhaustion
    raise Exception(
        f"Worker {worker.agent_id} failed processing task {task['task_id']}"
    )


def main():
    print("=" * 70)
    print("Supervisor-Worker Pattern - Advanced Usage Example")
    print("=" * 70)
    print()

    # ==================================================================
    # STEP 1: Create Pattern with Persistent Shared Memory
    # ==================================================================
    print("Step 1: Creating pattern with persistent shared memory...")
    print("-" * 70)

    # Create shared memory that we control
    shared_memory = SharedMemoryPool()

    # Create pattern with our shared memory
    pattern = create_supervisor_worker_pattern(
        num_workers=4, shared_memory=shared_memory, model="gpt-4", temperature=0.5
    )

    print("✓ Pattern created!")
    print(f"  - Workers: {len(pattern.workers)}")
    print(f"  - Shared memory ID: {id(pattern.shared_memory)}")
    print(f"  - Same instance: {pattern.shared_memory is shared_memory}")
    print()

    # ==================================================================
    # STEP 2: Delegate High-Priority Tasks
    # ==================================================================
    print("Step 2: Delegating high-priority tasks...")
    print("-" * 70)

    request = "Process critical customer orders requiring immediate attention"
    num_tasks = 8  # More tasks than workers

    tasks = pattern.delegate(request, num_tasks=num_tasks)

    print(f"✓ Delegated {len(tasks)} tasks to {len(pattern.workers)} workers")
    print()

    # Display task distribution
    task_distribution = {}
    for task in tasks:
        worker_id = task["assigned_to"]
        task_distribution[worker_id] = task_distribution.get(worker_id, 0) + 1

    print("Task Distribution:")
    for worker_id, count in task_distribution.items():
        print(f"  - {worker_id}: {count} tasks")
    print()

    # ==================================================================
    # STEP 3: Workers Execute with Error Handling
    # ==================================================================
    print("Step 3: Workers executing with error handling...")
    print("-" * 70)

    request_id = tasks[0]["request_id"]
    successful_tasks = []
    failed_tasks = []

    # Simulate some workers failing
    worker_failure_indices = [1, 3]  # Workers 1 and 3 will fail

    for i, worker in enumerate(pattern.workers):
        assigned_tasks = worker.get_assigned_tasks()

        if assigned_tasks:
            print(f"\n{worker.agent_id} processing {len(assigned_tasks)} task(s)...")

            for task in assigned_tasks:
                try:
                    # Simulate failure for specific workers
                    if i in worker_failure_indices and len(failed_tasks) < 2:
                        simulate_worker_failure(worker, task)

                    # Execute task normally
                    result = worker.execute_task(task)

                    if result:
                        successful_tasks.append(task)
                        print(f"  ✓ Task {task['task_id']} completed successfully")

                except Exception as e:
                    failed_tasks.append(task)
                    print(f"  ✗ Task {task['task_id']} FAILED: {str(e)}")

    print()
    print("Execution Summary:")
    print(f"  - Successful: {len(successful_tasks)}")
    print(f"  - Failed: {len(failed_tasks)}")
    print()

    # ==================================================================
    # STEP 4: Detect Failures
    # ==================================================================
    print("Step 4: Detecting failures...")
    print("-" * 70)

    # Supervisor checks for failures
    failures = pattern.supervisor.check_failures(request_id)

    if failures:
        print(f"⚠ Detected {len(failures)} failed task(s):")
        for failure in failures:
            print(f"  - Task: {failure.get('task_id', 'unknown')}")
            print(f"    Original worker: {failure.get('assigned_to', 'unknown')}")
            print(f"    Error: {failure.get('error', 'N/A')[:50]}...")
    else:
        print("✓ No failures detected")

    print()

    # ==================================================================
    # STEP 5: Task Reassignment
    # ==================================================================
    print("Step 5: Reassigning failed tasks...")
    print("-" * 70)

    # Find available workers (those not in failure list)
    failed_worker_ids = [f.get("assigned_to") for f in failures]
    available_workers = [
        w for w in pattern.workers if w.agent_id not in failed_worker_ids
    ]

    print(f"Available workers for reassignment: {len(available_workers)}")

    if failures and available_workers:
        for i, failure in enumerate(failures):
            # Round-robin assignment to available workers
            new_worker = available_workers[i % len(available_workers)]

            # Supervisor reassigns task
            pattern.supervisor.reassign_task(failure, new_worker.agent_id)

            print(
                f"  ✓ Reassigned task {failure.get('task_id')} to {new_worker.agent_id}"
            )

        print()
        print("Reassignment complete! Now re-executing...")
        print()

        # Workers execute reassigned tasks
        for worker in available_workers:
            reassigned = worker.get_assigned_tasks()

            if reassigned:
                print(
                    f"{worker.agent_id} processing {len(reassigned)} reassigned task(s)..."
                )

                for task in reassigned:
                    try:
                        result = worker.execute_task(task)
                        if result:
                            print(f"  ✓ Task {task['task_id']} completed on retry")
                    except Exception as e:
                        print(f"  ✗ Task {task['task_id']} failed again: {str(e)}")

    print()

    # ==================================================================
    # STEP 6: Monitor Progress with Real-Time Updates
    # ==================================================================
    print("Step 6: Monitoring progress...")
    print("-" * 70)

    progress = pattern.monitor_progress()

    print("Progress Status:")
    print(f"  - Active workers: {progress.get('active_workers', [])}")
    print(f"  - Pending tasks: {progress.get('pending_tasks', 0)}")
    print(f"  - Completed tasks: {progress.get('completed_tasks', 0)}")
    print()

    # Check if all tasks completed
    all_completed = pattern.supervisor.check_all_tasks_completed(request_id)

    if all_completed:
        print("✓ All tasks completed successfully!")
    else:
        pending = progress.get("pending_tasks", 0)
        print(f"⚠ {pending} task(s) still pending")

    print()

    # ==================================================================
    # STEP 7: Aggregate Results with Error Summary
    # ==================================================================
    print("Step 7: Aggregating results...")
    print("-" * 70)

    final_result = pattern.aggregate_results(request_id)

    print("✓ Results aggregated!")
    print()
    print("Final Result:")
    print(f"  - Summary: {final_result.get('summary', 'N/A')[:100]}...")
    print(f"  - Task results: {len(final_result.get('task_results', []))}")
    print()

    # Display failure statistics
    if failed_tasks:
        print("Error Summary:")
        print(f"  - Initial failures: {len(failed_tasks)}")
        print(
            f"  - Successful reassignments: {len([f for f in failures if f.get('reassigned')])}"
        )
        print(
            f"  - Final success rate: {(len(successful_tasks) / len(tasks)) * 100:.1f}%"
        )
        print()

    # ==================================================================
    # STEP 8: Shared Memory Inspection
    # ==================================================================
    print("Step 8: Inspecting shared memory...")
    print("-" * 70)

    # Get insights from different segments
    task_insights = pattern.get_shared_insights(segment="tasks")
    result_insights = pattern.get_shared_insights(segment="results")
    error_insights = pattern.get_shared_insights(segment="errors")

    print("Shared Memory Contents:")
    print(f"  - Tasks segment: {len(task_insights)} insights")
    print(f"  - Results segment: {len(result_insights)} insights")
    print(f"  - Errors segment: {len(error_insights)} insights")
    print()

    # Display error insights
    if error_insights:
        print("Error Insights:")
        for err in error_insights[:3]:  # Show first 3
            print(f"  - {err.get('content', 'N/A')[:60]}...")
        print()

    # ==================================================================
    # STEP 9: Cleanup with Validation
    # ==================================================================
    print("Step 9: Cleanup with validation...")
    print("-" * 70)

    # Check what will be cleared
    total_insights_before = len(pattern.get_shared_insights())
    print(f"Total insights before cleanup: {total_insights_before}")

    # Clear shared memory
    pattern.clear_shared_memory()

    # Verify cleanup
    total_insights_after = len(pattern.get_shared_insights())
    print(f"Total insights after cleanup: {total_insights_after}")

    if total_insights_after == 0:
        print("✓ Shared memory cleared successfully")
    else:
        print(f"⚠ Warning: {total_insights_after} insights remain")

    print()

    # ==================================================================
    # Summary
    # ==================================================================
    print("=" * 70)
    print("Advanced Example Complete!")
    print("=" * 70)
    print()
    print("What you learned:")
    print("  ✓ How to handle worker failures gracefully")
    print("  ✓ How to detect failed tasks via supervisor")
    print("  ✓ How to reassign tasks to available workers")
    print("  ✓ How to monitor progress during execution")
    print("  ✓ How to inspect shared memory contents")
    print("  ✓ How to calculate success rates and error statistics")
    print("  ✓ How to validate cleanup operations")
    print()
    print("Advanced Patterns:")
    print("  → Retry logic: Implement exponential backoff for failures")
    print("  → Circuit breaker: Disable failing workers temporarily")
    print("  → Priority queues: Process high-priority tasks first")
    print("  → Load balancing: Dynamically adjust task distribution")
    print("  → Monitoring dashboard: Real-time progress visualization")
    print()


if __name__ == "__main__":
    main()
