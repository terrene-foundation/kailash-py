"""
Example 1: Supervisor-Worker Pattern - Basic Usage

This example demonstrates the basic usage of the SupervisorWorkerPattern
with zero-configuration. The supervisor delegates tasks to workers who
execute them in parallel.

Learning Objectives:
- Zero-config pattern creation
- Task delegation
- Worker execution
- Result aggregation
- Progress monitoring

Estimated time: 5 minutes
"""

from kaizen.agents.coordination import create_supervisor_worker_pattern


def main():
    print("=" * 70)
    print("Supervisor-Worker Pattern - Basic Usage Example")
    print("=" * 70)
    print()

    # ==================================================================
    # STEP 1: Create Pattern (Zero-Config!)
    # ==================================================================
    print("Step 1: Creating supervisor-worker pattern...")
    print("-" * 70)

    # Create pattern with default settings
    # - 3 workers (default)
    # - Uses gpt-3.5-turbo (default model)
    # - Uses environment variables if set (KAIZEN_MODEL, etc.)
    pattern = create_supervisor_worker_pattern()

    print("✓ Pattern created successfully!")
    print(f"  - Supervisor: {pattern.supervisor.agent_id}")
    print(f"  - Workers: {[w.agent_id for w in pattern.workers]}")
    print(f"  - Coordinator: {pattern.coordinator.agent_id}")
    print(f"  - Shared Memory: {pattern.shared_memory is not None}")
    print()

    # ==================================================================
    # STEP 2: Validate Pattern
    # ==================================================================
    print("Step 2: Validating pattern initialization...")
    print("-" * 70)

    if pattern.validate_pattern():
        print("✓ Pattern validation passed!")
        print(f"  - All agents initialized: {len(pattern.get_agents())} agents")
        print(f"  - Unique agent IDs: {pattern.get_agent_ids()}")
        print("  - Shared memory configured: YES")
    else:
        print("✗ Pattern validation failed!")
        return

    print()

    # ==================================================================
    # STEP 3: Delegate Request to Workers
    # ==================================================================
    print("Step 3: Delegating request to workers...")
    print("-" * 70)

    # Supervisor breaks request into tasks and assigns to workers
    request = "Analyze customer feedback from 5 different product categories"
    num_tasks = 5  # One task per category

    print(f"Request: {request}")
    print(f"Number of tasks: {num_tasks}")
    print()

    tasks = pattern.delegate(request, num_tasks=num_tasks)

    print("✓ Tasks created and delegated!")
    print(f"  - Total tasks: {len(tasks)}")
    print()

    # Display task assignments
    for i, task in enumerate(tasks, 1):
        print(f"  Task {i}:")
        print(f"    - ID: {task['task_id']}")
        print(f"    - Assigned to: {task['assigned_to']}")
        print(f"    - Request ID: {task['request_id']}")
        print(f"    - Description: {task.get('description', 'N/A')[:60]}...")
        print()

    # ==================================================================
    # STEP 4: Workers Execute Tasks
    # ==================================================================
    print("Step 4: Workers executing assigned tasks...")
    print("-" * 70)

    # In a real scenario, workers would execute in parallel
    # For this example, we'll execute them sequentially to demonstrate

    request_id = tasks[0]["request_id"]
    executed_count = 0

    for worker in pattern.workers:
        # Each worker gets their assigned tasks
        assigned_tasks = worker.get_assigned_tasks()

        if assigned_tasks:
            print(f"\n{worker.agent_id} processing {len(assigned_tasks)} task(s)...")

            for task in assigned_tasks:
                try:
                    # Execute task
                    result = worker.execute_task(task)

                    if result:
                        executed_count += 1
                        print(f"  ✓ Task {task['task_id']} completed")
                        print(f"    Status: {result.get('status', 'unknown')}")
                except Exception as e:
                    print(f"  ✗ Task {task['task_id']} failed: {str(e)}")

    print()
    print(f"✓ All workers finished! ({executed_count} tasks executed)")
    print()

    # ==================================================================
    # STEP 5: Monitor Progress
    # ==================================================================
    print("Step 5: Monitoring progress...")
    print("-" * 70)

    progress = pattern.monitor_progress()

    print("Progress Status:")
    print(f"  - Active workers: {progress.get('active_workers', '[]')}")
    print(f"  - Pending tasks: {progress.get('pending_tasks', 0)}")
    print(f"  - Completed tasks: {progress.get('completed_tasks', 0)}")
    print()

    # ==================================================================
    # STEP 6: Aggregate Results
    # ==================================================================
    print("Step 6: Aggregating results from workers...")
    print("-" * 70)

    # Supervisor aggregates results from all workers
    final_result = pattern.aggregate_results(request_id)

    print("✓ Results aggregated!")
    print()
    print("Final Result:")
    print(f"  - Summary: {final_result.get('summary', 'N/A')[:100]}...")
    print(f"  - Task results included: {len(final_result.get('task_results', []))}")
    print()

    # Display individual task results
    if final_result.get("task_results"):
        print("Individual Task Results:")
        for tr in final_result["task_results"][:3]:  # Show first 3
            print(f"  - Task: {tr.get('task_id', 'N/A')}")
            print(f"    Worker: {tr.get('worker', 'N/A')}")
            print(f"    Result: {tr.get('result', 'N/A')[:60]}...")
            print()

    # ==================================================================
    # STEP 7: Cleanup (Optional)
    # ==================================================================
    print("Step 7: Cleanup (optional)...")
    print("-" * 70)

    # Clear shared memory if you want to reuse the pattern
    pattern.clear_shared_memory()
    print("✓ Shared memory cleared (pattern ready for next request)")
    print()

    # ==================================================================
    # Summary
    # ==================================================================
    print("=" * 70)
    print("Example Complete!")
    print("=" * 70)
    print()
    print("What you learned:")
    print("  ✓ How to create a supervisor-worker pattern (zero-config)")
    print("  ✓ How to delegate requests to workers")
    print("  ✓ How workers execute tasks via shared memory")
    print("  ✓ How to monitor progress during execution")
    print("  ✓ How to aggregate results from multiple workers")
    print("  ✓ How to cleanup shared memory for reuse")
    print()
    print("Next steps:")
    print("  → Try example 2: Progressive configuration")
    print("  → Try example 3: Real-world document processing")
    print("  → Try example 4: Advanced usage with custom configs")
    print()


if __name__ == "__main__":
    main()
